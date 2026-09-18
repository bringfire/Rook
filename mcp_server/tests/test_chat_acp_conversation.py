from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from acp import PROTOCOL_VERSION
from acp.schema import ImageContentBlock, PromptResponse

from rook.agent.chat.acp_client import RookChatAcpClient
from rook.agent.chat.acp_images import ValidatedImage
from rook.agent.chat.acp_conversation import (
    ActivePromptSupervisor,
    AcpConversationManager,
    CloseResult,
    ConversationBusy,
    ConversationNotOpen,
    CreateConversationRequest,
    DirectAcpProcessFactory,
    PromptInput,
    PromptResult,
)
from rook.agent.chat.acp_presentation import PresentationCache, ProjectedEvent, PromptGeneration
from rook.agent.chat.acp_process import InitializedAcp, RetirementResult
from rook.agent.chat.acp_storage import AssociationStore, OpenClaim, RookBinding, SessionRecoveryRequired
from rook.agent.chat.prime_runtime import PrimeLaunchError, PrimeRuntimeContract
from rook.runtime_paths import AcpDataPaths, RuntimePaths


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != 'nt', reason='Windows storage admission')
@pytest.mark.parametrize('reopen', [False, True])
@pytest.mark.parametrize('commit', ['c2055d6aff5891b918a24accf584a76852676445', 'dacbeab26b705e7d07b55ae6f8cd3e95ceb5458b'])
async def test_privacy_refusal_releases_prechild_claim(tmp_path, monkeypatch, reopen, commit):
    from .test_chat_configuration_storage import storage, set_acl
    s = storage()
    contract = replace(_contract(tmp_path), compatibility_patch_commit=commit)
    paths = _paths(tmp_path)
    data = tmp_path / 'data'
    provisional = AssociationStore(paths).reserve_provisional(binding=_binding(), runtime_id=contract.runtime_id,
        working_directory=tmp_path, requested_model=None, requested_reasoning=None)
    prepared = DirectAcpProcessFactory({'ROOK_DATA_DIR':str(data)}).prepare(contract, provisional, reopen)
    root = data / 'prime-config'
    assert not root.exists()  # launch preparation is pure
    root.mkdir()
    sid = s._Windows().user_sid
    set_acl(root, f'D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;;FR;;;WD)')
    called = []
    async def forbidden(*args, **kwargs):
        called.append(True)
        raise AssertionError('privacy refusal must precede SDK acquisition')
    monkeypatch.setattr('rook.agent.chat.acp_conversation.OwnedAcpProcess.start', forbidden)
    claim = OpenClaim.acquire(paths.claims_root, provisional.session_path)
    with pytest.raises(s.ConfigurationStorageRefused):
        await prepared.start(claim, launch_generation=1)
    assert not called and not claim.path.exists()
    assert root.exists()


def _paths(tmp_path: Path) -> AcpDataPaths:
    runtime = RuntimePaths(
        mode="dev",
        install_root=tmp_path / "app",
        data_root=tmp_path / "data",
        logs_root=tmp_path / "logs",
        runtime_root=tmp_path,
        mcp_server_dir=tmp_path / "app/mcp_server",
        repo_root=tmp_path / "app",
    )
    paths = AcpDataPaths.from_runtime_paths(runtime)
    paths.create_roots()
    return paths


def _contract(tmp_path: Path, runtime_id: str = "A" * 64) -> PrimeRuntimeContract:
    executable = tmp_path / "prime.exe"
    executable.write_bytes(b"prime")
    goal = tmp_path / "goal"
    rook = tmp_path / "rook-full"
    goal.mkdir(exist_ok=True)
    rook.mkdir(exist_ok=True)
    uv = tmp_path / "tools/uv/uv.exe"
    uv.parent.mkdir(parents=True, exist_ok=True)
    uv.write_bytes(b"fixture uv")
    return PrimeRuntimeContract(
        schema_version=1,
        runtime_id=runtime_id,
        platform=platform.system().lower(),
        architecture=platform.machine().lower(),
        upstream_commit="upstream",
        compatibility_patch_commit="patch",
        manifest_sha256=runtime_id,
        acp_protocol_version=PROTOCOL_VERSION,
        python_acp_sdk_version="0.12.1",
        executable_path=executable,
        goal_skill_path=goal,
        rook_skill_path=rook,
        rook_skill_manifest_sha256="B" * 64,
        rook_skill_system_prompt="# Rook\n",
        uv_version="0.12.3",
        uv_executable_path=uv,
        prime_agent_runtime_path=tmp_path / "dist/prime-agent-runtime",
        prime_agent_runtime_manifest_sha256="C" * 64,
        claim_key_version=1,
    )


class FakeRuntimeCatalog:
    def __init__(self, contract: PrimeRuntimeContract, events: list[str] | None = None) -> None:
        self.contract = contract
        self.latest_calls = 0
        self.events = events

    def latest(self) -> PrimeRuntimeContract:
        self.latest_calls += 1
        return self.contract

    def get(self, runtime_id: str) -> PrimeRuntimeContract:
        if self.events is not None:
            self.events.append("runtime")
        assert runtime_id == self.contract.runtime_id
        return self.contract


class NullSink:
    def __init__(self, *, drain_result: bool = True) -> None:
        self.events: list[ProjectedEvent] = []
        self.drain_result = drain_result

    async def write(self, event: ProjectedEvent) -> None:
        self.events.append(event)

    async def drain(self, deadline_seconds: float) -> bool:
        assert deadline_seconds > 0
        return self.drain_result


class FakeOwnedProcess:
    def __init__(self, association, claim, factory: "FakeProcessFactory", generation: int) -> None:
        self.association = association
        self.claim = claim
        self.factory = factory
        self.launch_generation = generation
        self.session_id = f"acp-{factory.launch_count}"
        self.image_supported = factory.image_supported
        self.client = RookChatAcpClient()
        self.client.reset_for_session(launch_generation=generation, acp_session_id=self.session_id)
        self.prompt_count = 0
        self.cancel_count = 0
        self.prompt_started = asyncio.Event()
        self.release_prompt = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.initialize_started = asyncio.Event()
        self.release_initialize = asyncio.Event()
        self.new_session_started = asyncio.Event()
        self.release_new_session = asyncio.Event()
        self.retire_started = asyncio.Event()
        self.retire_finished = asyncio.Event()
        self.release_retire = asyncio.Event()
        if not factory.block_initialize:
            self.release_initialize.set()
        if not factory.block_new_session:
            self.release_new_session.set()
        self.release_retire.set()
        self.transport_failure = asyncio.Event()
        self.new_session_calls = 0
        self.retire_send_close: list[bool] = []
        self.retire_error: Exception | None = None
        self.child_exit_observed = False

    async def initialize(self) -> InitializedAcp:
        self.initialize_started.set()
        await self.release_initialize.wait()
        return InitializedAcp(image_supported=self.image_supported)

    async def new_session(self, *, cwd, mcp_servers) -> str:
        self.new_session_started.set()
        await self.release_new_session.wait()
        assert str(Path(cwd).resolve()) == self.association.working_directory
        assert [server.name for server in mcp_servers] == ["rook"]
        self.new_session_calls += 1
        return self.session_id

    async def prompt(self, content_blocks, *, generation, projection) -> PromptResponse:
        self.prompt_count += 1
        self.prompt_started.set()
        if self.factory.raise_prompt:
            raise ConnectionError("fixture ACP transport failure")
        for ordinal in range(self.factory.updates_before_wait):
            await projection.accept_source_update(
                ordinal,
                ProjectedEvent(ordinal, "tool_call_update", f"tool-{ordinal}", None, {"status": "running"}),
                generation=generation,
            )
        if self.factory.block_prompt:
            cancel_wait = asyncio.create_task(self.cancelled.wait())
            release_wait = asyncio.create_task(self.release_prompt.wait())
            done, pending = await asyncio.wait(
                {cancel_wait, release_wait}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if self.factory.raise_after_wait:
                raise ConnectionError("fixture ACP transport failure after cancellation")
            stop_reason = "cancelled" if cancel_wait in done else self.factory.stop_reason
        else:
            stop_reason = self.factory.stop_reason
        if self.factory.materialize:
            path = Path(self.association.session_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "type": "session",
                        "version": 3,
                        "id": self.factory.prime_session_id,
                        "cwd": self.association.working_directory,
                    },
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
        if not self.factory.updates_before_wait:
            await projection.accept_source_update(
                0,
                ProjectedEvent(0, "agent_message_chunk", "answer", "answer", None),
                generation=generation,
            )
        return PromptResponse(stop_reason=stop_reason)

    async def cancel(self) -> None:
        self.cancel_count += 1
        self.cancelled.set()

    async def retire(self, *, send_close: bool = True, release_claim: bool = True) -> RetirementResult:
        self.retire_send_close.append(send_close)
        self.retire_started.set()
        await self.release_retire.wait()
        if self.retire_error is not None:
            self.retire_finished.set()
            raise self.retire_error
        if release_claim:
            self.claim.release_after_observed_exit()
        self.child_exit_observed = True
        self.retire_finished.set()
        return RetirementResult(
            clean=send_close,
            child_exit_observed=True,
            stderr_total_bytes=0,
            stderr_truncated=False,
            stderr_failure_code=None,
        )


class FakeProcessFactory:
    def __init__(
        self,
        *,
        materialize: bool = True,
        block_prompt: bool = False,
        stop_reason: str = "end_turn",
        events: list[str] | None = None,
        raise_prompt: bool = False,
        raise_after_wait: bool = False,
        updates_before_wait: int = 0,
        block_initialize: bool = False,
        block_new_session: bool = False,
        image_supported: bool = True,
    ) -> None:
        self.materialize = materialize
        self.block_prompt = block_prompt
        self.stop_reason = stop_reason
        self.prime_session_id = "durable-prime-session"
        self.launch_count = 0
        self.processes: list[FakeOwnedProcess] = []
        self.process_created = asyncio.Event()
        self.events = events
        self.raise_prompt = raise_prompt
        self.raise_after_wait = raise_after_wait
        self.updates_before_wait = updates_before_wait
        self.block_initialize = block_initialize
        self.block_new_session = block_new_session
        self.image_supported = image_supported

    def prepare(self, contract, association, reopen):
        del contract, reopen
        return FakePreparedLaunch(self, association)


class FakePreparedLaunch:
    def __init__(self, factory: FakeProcessFactory, association) -> None:
        self.factory = factory
        self.association = association

    async def start(self, claim, *, launch_generation):
        factory = self.factory
        association = self.association
        if factory.events is not None:
            factory.events.append("launch")
        factory.launch_count += 1
        process = FakeOwnedProcess(association, claim, factory, launch_generation)
        factory.processes.append(process)
        factory.process_created.set()
        return process


def _binding() -> RookBinding:
    return RookBinding(
        profile="full",
        host_generation_id=str(uuid.UUID("a66f624c-cc08-4c76-a8f9-cd999b11b7a4")),
        rhino_document_serial=17,
        route_process_id=4242,
    )


def _manager(tmp_path: Path, *, factory: FakeProcessFactory | None = None):
    paths = _paths(tmp_path)
    store = AssociationStore(paths)
    contract = _contract(tmp_path)
    catalog = FakeRuntimeCatalog(contract)
    process_factory = factory or FakeProcessFactory()
    manager = AcpConversationManager(
        store,
        catalog,
        process_factory,
        PresentationCache(paths.presentation_root),
    )
    return manager, store, catalog, process_factory, paths


@pytest.mark.asyncio
async def test_task7_idle_snapshot_reaches_next_prompt_without_durable_settings(tmp_path):
    from .test_chat_acp_client import _settings_update
    manager, store, _, factory, paths = _manager(tmp_path)
    try:
        view = await manager.create(CreateConversationRequest(_binding(), None, "requested/b", "high"))
        assert getattr(view, "effective_settings", None) == {"provider": None, "model": None, "reasoning": None}
        process = factory.processes[0]
        latest = {"provider": "actual", "model": "c", "reasoning": "off"}
        await process.client.session_update(process.session_id, _settings_update(latest))
        sink = NullSink()
        supervisor = await manager.start_prompt(view.conversation_id, PromptInput("hello", ()), sink)
        result = await supervisor.result_task
        assert result.outcome == "settled"
        assert sink.events[0].kind == "session_status"
        assert sink.events[0].effective_settings == latest
        record = store.get(view.conversation_id)
        assert record.requested_initial_model == "requested/b"
        assert not hasattr(record, "effective_settings")
        history = PresentationCache(paths.presentation_path(view.conversation_id)).load()
        assert "effectiveSettings" not in json.dumps(history.turns)
        await manager.close(view.conversation_id)
        reopened = await manager.reopen(view.conversation_id)
        assert reopened.effective_settings == dict.fromkeys(latest)
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_first_prompt_is_the_only_provisional_turn(tmp_path: Path):
    factory = FakeProcessFactory(block_prompt=True)
    manager, store, catalog, _, paths = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    assert store.list() == ()
    assert catalog.latest_calls == 1

    first = await manager.start_prompt(view.conversation_id, PromptInput("hello", ()), NullSink())
    await factory.processes[0].prompt_started.wait()
    with pytest.raises(ConversationBusy):
        await manager.start_prompt(view.conversation_id, PromptInput("second", ()), NullSink())
    factory.processes[0].release_prompt.set()
    result = await first.result_task

    assert result.outcome == "settled"
    assert store.get(view.conversation_id).prime_session_id == factory.prime_session_id
    assert PresentationCache(paths.presentation_path(view.conversation_id)).load().turns[0]["assistantText"] == "answer"


@pytest.mark.asyncio
async def test_failed_first_publication_is_never_adopted_or_replayed(tmp_path: Path):
    factory = FakeProcessFactory(materialize=False)
    manager, store, _, _, paths = _manager(tmp_path, factory=factory)
    view = await manager.create(CreateConversationRequest(_binding(), None, None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("hello", ()), NullSink())
    result = await supervisor.result_task

    assert result.outcome == "error"
    assert store.list() == ()
    assert factory.processes[0].prompt_count == 1
    assert PresentationCache(paths.presentation_path(view.conversation_id)).load().turns == ()
    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(view.conversation_id, PromptInput("again", ()), NullSink())


@pytest.mark.asyncio
async def test_valid_materialization_with_failed_registry_publication_is_not_cached_or_adopted(tmp_path: Path):
    paths = _paths(tmp_path)

    class FailingPublishStore(AssociationStore):
        def publish(self, provisional, header):
            raise RuntimeError("injected publication failure")

    store = FailingPublishStore(paths)
    factory = FakeProcessFactory()
    manager = AcpConversationManager(
        store,
        FakeRuntimeCatalog(_contract(tmp_path)),
        factory,
        PresentationCache(paths.presentation_root),
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())

    assert (await supervisor.result_task).outcome == "error"
    assert store.list() == ()
    assert PresentationCache(paths.presentation_path(view.conversation_id)).load().turns == ()
    assert factory.processes[0].retire_send_close == [True]
    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(view.conversation_id, PromptInput("again", ()), NullSink())


@pytest.mark.asyncio
async def test_unsaved_working_directory_is_exact_product_workspace(tmp_path: Path):
    manager, store, _, factory, paths = _manager(tmp_path)
    view = await manager.create(CreateConversationRequest(_binding(), None, None, None))
    expected = paths.workspace_path(view.conversation_id).resolve()
    assert expected.is_dir()
    assert Path(factory.processes[0].association.working_directory) == expected
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("hello", ()), NullSink())
    await supervisor.result_task
    assert Path(store.get(view.conversation_id).working_directory) == expected


@pytest.mark.asyncio
async def test_saved_working_directory_must_be_absolute_and_present(tmp_path: Path):
    manager, _, _, _, _ = _manager(tmp_path)
    with pytest.raises(Exception, match="working_directory_unavailable"):
        await manager.create(CreateConversationRequest(_binding(), "relative", None, None))
    with pytest.raises(Exception, match="working_directory_unavailable"):
        await manager.create(CreateConversationRequest(_binding(), str(tmp_path / "missing"), None, None))


@pytest.mark.asyncio
async def test_create_requires_target_before_runtime_selection_or_launch(tmp_path: Path):
    paths = _paths(tmp_path)
    store = AssociationStore(paths)
    catalog = FakeRuntimeCatalog(_contract(tmp_path))
    factory = FakeProcessFactory()
    manager = AcpConversationManager(
        store,
        catalog,
        factory,
        PresentationCache(paths.presentation_root),
        target_available=lambda _binding: False,
    )

    with pytest.raises(RuntimeError, match="target_unavailable"):
        await manager.create(CreateConversationRequest(_binding(), str(tmp_path), None, None))

    assert catalog.latest_calls == 0
    assert factory.launch_count == 0
    assert store.list() == ()


@pytest.mark.asyncio
async def test_stop_cancels_current_prompt_but_preserves_prime_goal_projection(tmp_path: Path):
    factory = FakeProcessFactory(block_prompt=True)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    process = factory.processes[0]
    process.client.observe_prime_meta({"goal": {"status": "active", "objective": "repair"}})
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("work", ()), NullSink())
    await process.prompt_started.wait()

    assert await manager.request_cancel(view.conversation_id, "panel_stop")
    assert not await manager.request_cancel(view.conversation_id, "duplicate")
    result = await supervisor.result_task

    assert result.outcome == "cancelled"
    assert process.cancel_count == 1
    assert manager.goal_projection(view.conversation_id) == {"status": "active", "objective": "repair"}


@pytest.mark.asyncio
async def test_cancelled_observer_does_not_cancel_service_owned_prompt(tmp_path: Path):
    factory = FakeProcessFactory(block_prompt=True)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("work", ()), NullSink())
    await factory.processes[0].prompt_started.wait()

    observer = asyncio.ensure_future(supervisor.result_task)
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await observer
    with pytest.raises(ConversationBusy):
        await manager.start_prompt(view.conversation_id, PromptInput("too early", ()), NullSink())

    factory.processes[0].release_prompt.set()
    assert (await supervisor.result_task).outcome == "settled"


@pytest.mark.asyncio
async def test_projection_overflow_uses_the_prompt_owner_cancel_path(tmp_path: Path, monkeypatch):
    from rook.agent.chat import acp_conversation
    from rook.agent.chat.acp_presentation import BoundedPromptProjection, PresentationQueue

    monkeypatch.setattr(
        acp_conversation,
        "PresentationQueue",
        lambda: PresentationQueue(max_events=1, max_utf8_bytes=4096),
    )
    monkeypatch.setattr(
        acp_conversation,
        "BoundedPromptProjection",
        lambda **kwargs: BoundedPromptProjection(**kwargs, callback_deadline_seconds=0.05),
    )
    monkeypatch.setattr(acp_conversation, "PRESENTATION_DRAIN_SECONDS", 0.05)
    factory = FakeProcessFactory(block_prompt=True, updates_before_wait=3)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()

    class SlowSink(NullSink):
        async def write(self, event):
            await asyncio.sleep(0.2)

    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("work", ()), SlowSink())
    result = await asyncio.wait_for(supervisor.result_task, timeout=1.0)

    assert result.outcome == "cancelled"
    assert result.presentation_outcome == "stream_failed"
    assert factory.processes[0].cancel_count == 1


@pytest.mark.asyncio
async def test_panel_disconnect_uses_the_prompt_owner_cancel_path(tmp_path: Path):
    factory = FakeProcessFactory(block_prompt=True, updates_before_wait=1)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()

    class DisconnectedSink(NullSink):
        async def write(self, event):
            raise ConnectionError("panel disconnected")

    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("work", ()), DisconnectedSink())
    result = await asyncio.wait_for(supervisor.result_task, timeout=1.0)

    assert result.outcome == "cancelled"
    assert result.presentation_outcome == "stream_failed"
    assert factory.processes[0].cancel_count == 1


@pytest.mark.asyncio
async def test_close_detaches_before_waiting_for_prompt_or_retirement(tmp_path: Path):
    factory = FakeProcessFactory(block_prompt=True)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    process = factory.processes[0]
    process.release_retire.clear()
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("work", ()), NullSink())
    await process.prompt_started.wait()
    close_task = asyncio.create_task(manager.close(view.conversation_id))
    await process.cancelled.wait()
    await process.retire_started.wait()

    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(view.conversation_id, PromptInput("late", ()), NullSink())
    process.release_retire.set()
    close_result = await close_task
    prompt_result = await supervisor.result_task
    assert close_result == CloseResult("clean", True)
    assert prompt_result.outcome == "cancelled"
    assert process.cancel_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_stage", ["initialize", "new_session"])
async def test_cancelled_create_retires_claimed_process(tmp_path: Path, blocked_stage: str):
    factory = FakeProcessFactory(
        block_initialize=blocked_stage == "initialize",
        block_new_session=blocked_stage == "new_session",
    )
    manager, _, _, _, paths = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    create_task = asyncio.create_task(
        manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    )
    await factory.process_created.wait()
    process = factory.processes[0]
    stage_started = process.initialize_started if blocked_stage == "initialize" else process.new_session_started
    stage_release = process.release_initialize if blocked_stage == "initialize" else process.release_new_session
    await stage_started.wait()

    create_task.cancel()
    stage_release.set()
    with pytest.raises(asyncio.CancelledError):
        await create_task

    await asyncio.wait_for(process.retire_finished.wait(), timeout=0.2)
    assert process.retire_send_close == [False]
    assert not list(paths.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "reopen"])
@pytest.mark.parametrize("after_insert", [False, True])
async def test_cancelled_resident_publication_retires_exact_process(
    tmp_path: Path,
    operation: str,
    after_insert: bool,
):
    manager, _, _, factory, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    conversation_id = None
    if operation == "reopen":
        view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
        prompt = await manager.start_prompt(view.conversation_id, PromptInput("materialize", ()), NullSink())
        await prompt.result_task
        await manager.close(view.conversation_id)
        conversation_id = view.conversation_id

    inserted = asyncio.Event()
    if after_insert:
        original_insert = manager._insert_resident

        async def insert_then_block(resident):
            await original_insert(resident)
            inserted.set()
            await asyncio.Event().wait()

        manager._insert_resident = insert_then_block
    else:
        await manager._admission_lock.acquire()

    factory.process_created.clear()
    task = asyncio.create_task(
        manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
        if operation == "create"
        else manager.reopen(conversation_id)
    )
    await factory.process_created.wait()
    process = factory.processes[-1]
    while process.new_session_calls == 0:
        await asyncio.sleep(0)
    if after_insert:
        await inserted.wait()

    task.cancel()
    if not after_insert:
        manager._admission_lock.release()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.wait_for(process.retire_finished.wait(), timeout=0.2)
    assert process.retire_send_close == [True]
    assert not manager._resident
    assert not list(paths.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
async def test_invalid_creation_launch_is_refused_before_claim_acquisition(tmp_path: Path, monkeypatch):
    paths = _paths(tmp_path)
    manager = AcpConversationManager(
        AssociationStore(paths),
        FakeRuntimeCatalog(_contract(tmp_path)),
        DirectAcpProcessFactory({"PATH": "C:/approved", "ROOK_DATA_DIR": str(tmp_path / "data")}),
        PresentationCache(paths.presentation_root),
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    claim_attempted = False

    def unexpected_claim(*_args, **_kwargs):
        nonlocal claim_attempted
        claim_attempted = True
        raise AssertionError("invalid launch reached claim acquisition")

    monkeypatch.setattr(OpenClaim, "acquire", unexpected_claim)

    with pytest.raises(PrimeLaunchError, match="invalid_reasoning"):
        await manager.create(CreateConversationRequest(_binding(), str(saved), None, "none"))
    assert not claim_attempted


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_source", ["argv_nul", "environment_name", "environment_value"])
async def test_deterministically_invalid_launch_refuses_before_claim_acquisition(
    tmp_path: Path,
    monkeypatch,
    invalid_source: str,
):
    paths = _paths(tmp_path)
    contract = _contract(tmp_path)
    environment = {"PATH": "C:/approved"}
    if invalid_source == "argv_nul":
        contract = replace(contract, rook_skill_system_prompt="valid\0invalid")
    elif invalid_source == "environment_name":
        environment = {"INVALID=NAME": "value"}
    else:
        environment = {"PATH": "valid\0invalid"}
    manager = AcpConversationManager(
        AssociationStore(paths),
        FakeRuntimeCatalog(contract),
        DirectAcpProcessFactory(environment),
        PresentationCache(paths.presentation_root),
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    claim_attempted = False

    def unexpected_claim(*_args, **_kwargs):
        nonlocal claim_attempted
        claim_attempted = True
        raise AssertionError("invalid launch reached claim acquisition")

    monkeypatch.setattr(OpenClaim, "acquire", unexpected_claim)

    with pytest.raises(PrimeLaunchError):
        await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    assert not claim_attempted


@pytest.mark.asyncio
async def test_image_prompt_refuses_before_session_prompt_when_capability_is_absent(tmp_path: Path):
    factory = FakeProcessFactory(image_supported=False)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    image = ValidatedImage(
        file_name="one.png",
        mime_type="image/png",
        binary_bytes=8,
        width=1,
        height=1,
        sha256="A" * 64,
        acp_block=ImageContentBlock(type="image", data="iVBORw0KGgo=", mime_type="image/png"),
    )

    with pytest.raises(RuntimeError, match="image_unsupported"):
        await manager.start_prompt(view.conversation_id, PromptInput("inspect", (image,)), NullSink())
    assert factory.processes[0].prompt_count == 0
    await manager.close(view.conversation_id)


@pytest.mark.asyncio
async def test_close_retirement_continues_after_close_waiter_is_cancelled(tmp_path: Path):
    manager, _, _, factory, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    process = factory.processes[0]
    process.release_retire.clear()

    close_task = asyncio.create_task(manager.close(view.conversation_id))
    await process.retire_started.wait()
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task

    process.release_retire.set()
    await asyncio.wait_for(process.retire_finished.wait(), timeout=0.2)
    assert not list(paths.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
async def test_reopen_uses_fresh_acp_session_without_prompt(tmp_path: Path):
    manager, store, catalog, factory, _ = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await supervisor.result_task
    original_session = factory.processes[0].session_id
    factory.processes[0].client.observe_prime_meta({"goal": {"status": "active"}})
    await manager.close(view.conversation_id)

    reopened = await manager.reopen(view.conversation_id)

    assert reopened.durable
    assert factory.processes[-1].session_id != original_session
    assert factory.processes[-1].prompt_count == 0
    assert manager.goal_projection(view.conversation_id) is None
    assert catalog.latest_calls == 1
    assert store.get(view.conversation_id).runtime_id == catalog.contract.runtime_id


@pytest.mark.asyncio
async def test_missing_reopen_working_directory_refuses_before_launch_and_releases_claim(tmp_path: Path):
    manager, _, _, _, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    prompt = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await prompt.result_task
    await manager.close(view.conversation_id)
    saved.rmdir()

    replacement_factory = FakeProcessFactory()
    replacement = AcpConversationManager(
        AssociationStore(paths),
        FakeRuntimeCatalog(_contract(tmp_path)),
        replacement_factory,
        PresentationCache(paths.presentation_root),
    )
    with pytest.raises(Exception, match="working_directory_unavailable"):
        await replacement.reopen(view.conversation_id)
    assert replacement_factory.launch_count == 0

    saved.mkdir()
    await replacement.reopen(view.conversation_id)
    assert replacement_factory.launch_count == 1
    await replacement.close(view.conversation_id)


@pytest.mark.asyncio
async def test_reopen_claim_precedes_authoritative_revalidation_and_launch(tmp_path: Path):
    manager, _, _, factory, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    prompt = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await prompt.result_task
    await manager.close(view.conversation_id)
    events: list[str] = []

    class TrackingStore(AssociationStore):
        def locate_session(self, conversation_id: str) -> str:
            events.append("locate")
            return super().locate_session(conversation_id)

        def get(self, conversation_id: str):
            events.append("get")
            session_path = self.locate_session(conversation_id)
            digest = __import__("hashlib").sha256(session_path.encode("utf-8")).hexdigest()
            assert (self.paths.claims_root / f"{digest}.open.claim").exists()
            return super().get(conversation_id)

    tracking_factory = FakeProcessFactory(events=events)
    reopened = AcpConversationManager(
        TrackingStore(paths),
        FakeRuntimeCatalog(_contract(tmp_path), events),
        tracking_factory,
        PresentationCache(paths.presentation_root),
    )
    await reopened.reopen(view.conversation_id)
    assert events[:4] == ["locate", "get", "locate", "runtime"]
    assert events[-1] == "launch"
    await reopened.close(view.conversation_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("reopen", [False, True])
async def test_prepared_launch_carries_association_cwd_through_real_sdk(tmp_path, monkeypatch, reopen):
    contract = _contract(tmp_path)
    paths = _paths(tmp_path)
    saved = tmp_path / "association-working-directory"
    saved.mkdir()
    provisional = AssociationStore(paths).reserve_provisional(
        binding=_binding(), runtime_id=contract.runtime_id, working_directory=saved,
        requested_model=None, requested_reasoning=None)
    output = tmp_path / "observed-cwd.txt"
    # Replace only the executable behavior; retain factory -> prepared launch -> SDK subprocess.
    argv = (sys.executable, "-I", "-c",
            f"from pathlib import Path; Path({str(output)!r}).write_text(str(Path.cwd()), encoding='utf-8')")
    monkeypatch.setattr("rook.agent.chat.acp_conversation.build_prime_argv", lambda *_: argv)
    prepared = DirectAcpProcessFactory({"PATH": str(Path(sys.executable).parent),
        "ROOK_DATA_DIR": str(tmp_path / "data")}).prepare(contract, provisional, reopen)
    claim = OpenClaim.acquire(paths.claims_root, provisional.session_path)
    process = await prepared.start(claim, launch_generation=2 if reopen else 1)
    try:
        await asyncio.wait_for(process.process.wait(), timeout=5)
        assert output.read_text(encoding="utf-8") == str(saved.resolve())
    finally:
        result = await process.retire(send_close=False)
        assert result.child_exit_observed
        assert not claim.path.exists()


@pytest.mark.asyncio
async def test_direct_factory_reopen_drops_creation_time_model_overrides(tmp_path: Path, monkeypatch):
    contract = _contract(tmp_path)
    paths = _paths(tmp_path)
    store = AssociationStore(paths)
    saved = tmp_path / "saved"
    saved.mkdir()
    provisional = store.reserve_provisional(
        binding=_binding(),
        runtime_id=contract.runtime_id,
        working_directory=saved,
        requested_model="anthropic/claude-x",
        requested_reasoning="high",
    )
    claim = __import__("rook.agent.chat.acp_storage", fromlist=["OpenClaim"]).OpenClaim.acquire(
        paths.claims_root, provisional.session_path
    )
    observed = {}

    async def fake_start(launch, received_claim, *, launch_generation):
        observed["argv"] = launch.argv
        observed["environment"] = dict(launch.environment)
        received_claim.release_no_child_created()
        return object()

    monkeypatch.setattr("rook.agent.chat.acp_conversation.OwnedAcpProcess.start", fake_start)
    forbidden = ["PI_PACKAGE_DIR", "PRIME_AGENT_KERNEL_PYTHON", "PRIME_AGENT_KERNEL_VENV", "PRIME_AGENT_INSTALL_UV",
                 "VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX",
                 "UV_INDEX", "UV_OFFLINE", "UV_FUTURE_SETTING"]
    base = {variant: "must-not-reach-child" for name in forbidden for variant in (name, name.lower(), name.title())}
    base.update({"PATH": "C:/approved", "ROOK_DATA_DIR": str(tmp_path / "data"), "ANTHROPIC_API_KEY": "user-owned"})
    factory = DirectAcpProcessFactory(base)
    prepared = factory.prepare(contract, provisional, True)
    await prepared.start(claim, launch_generation=2)
    assert "--model" not in observed["argv"]
    assert "--thinking" not in observed["argv"]
    environment = observed["environment"]
    assert not any(value == "must-not-reach-child" for value in environment.values())
    assert environment == {
        "PATH": str(contract.uv_executable_path.parent) + ";C:/approved",
        "ROOK_DATA_DIR": str(tmp_path / "data"), "ANTHROPIC_API_KEY": "user-owned",
        "UV_CACHE_DIR": str(tmp_path / "data/rookchat/acp/v1/prime-uv/cache"),
        "UV_PYTHON_INSTALL_DIR": str(tmp_path / "data/rookchat/acp/v1/prime-uv/python"),
        "UV_PYTHON_PREFERENCE": "only-managed", "UV_PYTHON_NO_REGISTRY": "1",
        "UV_PYTHON_INSTALL_REGISTRY": "0", "UV_NO_CONFIG": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


@pytest.mark.asyncio
async def test_stalled_panel_sink_is_bounded_independently_of_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("rook.agent.chat.acp_conversation.PRESENTATION_DRAIN_SECONDS", 0.05)
    manager, store, _, _, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))

    class SlowSink(NullSink):
        async def write(self, event):
            await asyncio.sleep(0.2)

    started = asyncio.get_running_loop().time()
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), SlowSink())
    result = await supervisor.result_task
    elapsed = asyncio.get_running_loop().time() - started
    assert elapsed < 0.15
    assert result.presentation_outcome == "stream_failed"
    assert result.cache_published
    assert store.get(view.conversation_id)
    assert PresentationCache(paths.presentation_path(view.conversation_id)).load().turns
    await manager.close(view.conversation_id)


@pytest.mark.asyncio
async def test_raw_cache_failure_never_reclassifies_settled_prime_result(tmp_path: Path, monkeypatch):
    manager, store, _, _, _ = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()

    def fail_publish(*_args, **_kwargs):
        raise PermissionError("injected cache failure")

    monkeypatch.setattr(PresentationCache, "publish", fail_publish)
    monkeypatch.setattr(PresentationCache, "publish_fallback", fail_publish)
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    result = await supervisor.result_task

    assert result.outcome == "settled"
    assert result.stop_reason == "end_turn"
    assert not result.cache_published
    assert store.get(view.conversation_id).prime_session_id == "durable-prime-session"
    await manager.close(view.conversation_id)


@pytest.mark.asyncio
async def test_live_delete_keeps_claim_until_record_and_artifacts_are_removed(tmp_path: Path):
    manager, store, _, _, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    prompt = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await prompt.result_task
    association = store.get(view.conversation_id)
    result = await manager.delete(view.conversation_id)
    assert result.association_removed
    assert result.artifacts_removed
    assert not paths.conversation_path(view.conversation_id).exists()
    assert not Path(association.session_path).exists()
    assert not list(paths.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
async def test_live_delete_of_provisional_conversation_removes_owned_artifacts(tmp_path: Path):
    manager, store, _, _, paths = _manager(tmp_path)
    view = await manager.create(CreateConversationRequest(_binding(), None, None, None))
    resident = manager._resident[view.conversation_id]
    session = Path(resident.association.session_path)
    workspace = Path(resident.association.working_directory)
    session.write_text("provisional", encoding="utf-8")
    (workspace / "owned.txt").write_text("owned", encoding="utf-8")

    result = await manager.delete(view.conversation_id)

    assert not result.association_removed
    assert result.artifacts_removed
    assert not session.exists()
    assert not workspace.exists()
    assert not paths.conversation_path(view.conversation_id).exists()
    assert not list(paths.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
async def test_live_delete_of_provisional_conversation_reports_artifact_failure_truthfully(tmp_path: Path):
    manager, _, _, _, paths = _manager(tmp_path)
    view = await manager.create(CreateConversationRequest(_binding(), None, None, None))
    resident = manager._resident[view.conversation_id]
    session = Path(resident.association.session_path)
    session.mkdir()

    result = await manager.delete(view.conversation_id)

    assert not result.association_removed
    assert not result.artifacts_removed
    assert session.is_dir()
    assert not list(paths.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
async def test_live_delete_continues_after_delete_waiter_is_cancelled(tmp_path: Path):
    manager, store, _, factory, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    prompt = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await prompt.result_task
    process = factory.processes[0]
    process.release_retire.clear()

    delete_task = asyncio.create_task(manager.delete(view.conversation_id))
    await process.retire_started.wait()
    delete_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await delete_task

    process.release_retire.set()
    await asyncio.wait_for(process.retire_finished.wait(), timeout=0.2)

    async def wait_for_delete_publication() -> None:
        while paths.conversation_path(view.conversation_id).exists():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_delete_publication(), timeout=0.2)
    with pytest.raises(Exception, match="association is missing"):
        store.get(view.conversation_id)
    assert not list(paths.claims_root.glob("*.open.claim"))


@pytest.mark.asyncio
async def test_transport_failure_retires_resident_without_replay(tmp_path: Path):
    factory = FakeProcessFactory()
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    first = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await first.result_task
    factory.raise_prompt = True
    failed = await manager.start_prompt(view.conversation_id, PromptInput("second", ()), NullSink())
    result = await failed.result_task

    assert result.outcome == "error"
    assert factory.processes[0].prompt_count == 2
    assert factory.processes[0].retire_started.is_set()


@pytest.mark.asyncio
async def test_idle_transport_failure_detaches_and_retires_without_acp_close(tmp_path: Path):
    manager, _, _, factory, _ = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    process = factory.processes[0]

    process.transport_failure.set()
    await asyncio.wait_for(process.retire_started.wait(), timeout=0.5)

    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(view.conversation_id, PromptInput("work", ()), NullSink())
    assert process.retire_send_close == [False]


@pytest.mark.asyncio
async def test_active_transport_failure_retires_without_sending_cancel_or_close(tmp_path: Path):
    factory = FakeProcessFactory(block_prompt=True, raise_after_wait=True)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    process = factory.processes[0]
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("work", ()), NullSink())
    await process.prompt_started.wait()

    process.transport_failure.set()
    await asyncio.wait_for(process.retire_started.wait(), timeout=0.5)
    process.release_prompt.set()
    result = await supervisor.result_task

    assert result.outcome == "error"
    assert process.cancel_count == 0
    assert process.retire_send_close == [False]
    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(view.conversation_id, PromptInput("no replay", ()), NullSink())


@pytest.mark.asyncio
async def test_close_sends_no_further_acp_after_uncertain_prompt_failure(tmp_path: Path):
    factory = FakeProcessFactory(block_prompt=True, raise_after_wait=True)
    manager, _, _, _, _ = _manager(tmp_path, factory=factory)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    supervisor = await manager.start_prompt(view.conversation_id, PromptInput("work", ()), NullSink())
    await factory.processes[0].prompt_started.wait()

    closed = await manager.close(view.conversation_id)
    result = await supervisor.result_task

    assert result.outcome == "error"
    assert closed.outcome == "unclean"
    assert factory.processes[0].retire_send_close == [False]


@pytest.mark.asyncio
async def test_settled_error_outcome_does_not_masquerade_as_transport_uncertainty(tmp_path: Path):
    manager, _, _, factory, _ = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    resident = await manager.detach_resident_for_retirement(view.conversation_id)
    supervisor = ActivePromptSupervisor(PromptGeneration(1, factory.processes[0].session_id, "prompt-test"))

    async def settled_error():
        return PromptResult("error", "unknown_stop_reason", "delivered", False)

    supervisor.start(settled_error())
    resident.active_prompt = supervisor

    result = await manager._retire_detached(resident)

    assert result.outcome == "clean"
    assert factory.processes[0].retire_send_close == [True]


@pytest.mark.asyncio
async def test_target_unavailability_does_not_block_reopen_or_change_binding(tmp_path: Path):
    manager, _, _, _, paths = _manager(tmp_path)
    saved = tmp_path / "saved"
    saved.mkdir()
    view = await manager.create(CreateConversationRequest(_binding(), str(saved), None, None))
    first = await manager.start_prompt(view.conversation_id, PromptInput("first", ()), NullSink())
    await first.result_task
    await manager.close(view.conversation_id)
    factory = FakeProcessFactory()
    reopened_manager = AcpConversationManager(
        AssociationStore(paths),
        FakeRuntimeCatalog(_contract(tmp_path)),
        factory,
        PresentationCache(paths.presentation_root),
        target_available=lambda _binding: False,
    )
    reopened = await reopened_manager.reopen(view.conversation_id)
    assert not reopened.target_available
    assert factory.processes[0].association.binding == _binding()
    await reopened_manager.close(view.conversation_id)


@pytest.mark.asyncio
async def test_shutdown_detaches_all_residents_before_retirement(tmp_path: Path):
    manager, _, _, factory, _ = _manager(tmp_path)
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    first = await manager.create(CreateConversationRequest(_binding(), str(one), None, None))
    second = await manager.create(CreateConversationRequest(_binding(), str(two), None, None))

    results = await manager.shutdown()

    assert len(results) == 2
    assert all(result.child_exit_observed for result in results)
    assert all(process.retire_started.is_set() for process in factory.processes)
    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(first.conversation_id, PromptInput("late", ()), NullSink())
    with pytest.raises(ConversationNotOpen):
        await manager.start_prompt(second.conversation_id, PromptInput("late", ()), NullSink())


@pytest.mark.asyncio
async def test_shutdown_attempts_every_retirement_when_one_fails(tmp_path: Path):
    manager, _, _, factory, _ = _manager(tmp_path)
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    await manager.create(CreateConversationRequest(_binding(), str(one), None, None))
    await manager.create(CreateConversationRequest(_binding(), str(two), None, None))
    factory.processes[0].retire_error = RuntimeError("fixture retirement failure")

    results = await manager.shutdown()

    assert results[0] == CloseResult("unclean", False)
    assert results[1] == CloseResult("clean", True)
    assert factory.processes[1].retire_finished.is_set()
