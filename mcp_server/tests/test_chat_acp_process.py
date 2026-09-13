from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from acp import PROTOCOL_VERSION
from acp.schema import TextContentBlock

from rook.agent.chat.acp_client import RookChatAcpClient
from rook.agent.chat.acp_presentation import BoundedPromptProjection, PresentationQueue, PromptGeneration
from rook.agent.chat.acp_process import AcpCapabilityError, OwnedAcpProcess, PrimeLaunch
from rook.agent.chat.acp_storage import OpenClaim
from rook.agent.chat import service_main


FAKE_AGENT = Path(__file__).parent / "fixtures" / "fake_acp_agent.py"


@pytest.mark.asyncio
@pytest.mark.parametrize("update_first", [False, True])
async def test_task7_session_response_cannot_overwrite_newer_update(tmp_path, update_first):
    from acp.schema import NewSessionResponse
    from .test_chat_acp_client import _settings_update
    client = RookChatAcpClient()
    initial = {"provider": "actual", "model": "initial", "reasoning": "low"}
    latest = {**initial, "model": "latest"}
    async def new_session(**kwargs):
        if update_first:
            await client.session_update("acp-session", _settings_update(latest, 1))
        return NewSessionResponse.model_validate({"sessionId": "acp-session", "_meta": {
            "ai.primeintellect.prime-agent": {"effectiveSettings": initial}}})
    owner = OwnedAcpProcess(PrimeLaunch(("synthetic",), {}, tmp_path), None, 3, client,
                            None, SimpleNamespace(new_session=new_session), None)
    await owner.new_session(cwd=tmp_path, mcp_servers=[])
    assert getattr(client, "effective_settings", None) == (latest if update_first else initial)


def _read_journal(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _fake_launch(tmp_path: Path, **scenario_overrides) -> tuple[PrimeLaunch, Path]:
    scenario = {
        "session_id": "fake-session",
        "stop_reason": "end_turn",
        "updates": [{"kind": "agent_message_chunk", "text": "done"}],
        **scenario_overrides,
    }
    scenario_path = tmp_path / "scenario.json"
    journal_path = tmp_path / "journal.jsonl"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    argv = (
        sys.executable,
        str(FAKE_AGENT),
        "--scenario",
        str(scenario_path),
        "--journal",
        str(journal_path),
        "--skill",
        "C:/runtime/rook-full",
        "--append-system-prompt",
        "# Exact Rook Full body\n",
    )
    return PrimeLaunch(argv=argv, environment=dict(os.environ), cwd=tmp_path), journal_path


async def _start(tmp_path: Path, launch: PrimeLaunch) -> tuple[OwnedAcpProcess, OpenClaim]:
    claim = OpenClaim.acquire(tmp_path / "claims", str(tmp_path / "session.jsonl"))
    process = await OwnedAcpProcess.start(launch, claim, launch_generation=1)
    return process, claim


@pytest.mark.asyncio
async def test_fake_agent_lifecycle_uses_exact_argv_and_drains_large_stderr(tmp_path: Path):
    launch, journal = _fake_launch(tmp_path, stderr_bytes=2 * 1024 * 1024)
    process, claim = await _start(tmp_path, launch)
    initialized = await process.initialize()
    assert initialized.image_supported
    await process.new_session(cwd=tmp_path, mcp_servers=[])
    generation = PromptGeneration(1, process.session_id, "prompt-1")
    projection = BoundedPromptProjection(generation=generation, queue=PresentationQueue(), user_text="hello")

    response = await process.prompt(
        [TextContentBlock(type="text", text="hello")], generation=generation, projection=projection
    )
    result = await process.retire()

    assert response.stop_reason == "end_turn"
    assert result.clean
    assert result.child_exit_observed
    assert result.stderr_total_bytes == 2 * 1024 * 1024
    assert result.stderr_truncated
    assert not claim.path.exists()
    assert await process.retire() == result
    started = _read_journal(journal)[0]
    assert started == {
        "event": "process_start",
        "argv": ["--skill", "C:/runtime/rook-full", "--append-system-prompt", "# Exact Rook Full body\n"],
    }


@pytest.mark.asyncio
async def test_actual_sdk_callbacks_overlap_but_projection_replays_wire_order(tmp_path: Path):
    updates = [{"kind": "agent_message_chunk", "text": f"{index},"} for index in range(64)]
    launch, journal = _fake_launch(tmp_path, updates=updates)
    process, _ = await _start(tmp_path, launch)
    await process.initialize()
    await process.new_session(cwd=tmp_path, mcp_servers=[])
    generation = PromptGeneration(1, process.session_id, "prompt-overlap")
    overlap_observed = asyncio.Event()
    arrivals: list[int] = []

    class StalledFirstProjection(BoundedPromptProjection):
        async def accept_source_update(self, source_ordinal, update, *, generation=None):
            arrivals.append(source_ordinal)
            if source_ordinal == 0:
                await asyncio.wait_for(overlap_observed.wait(), timeout=2)
            else:
                overlap_observed.set()
            return await super().accept_source_update(source_ordinal, update, generation=generation)

    projection = StalledFirstProjection(
        generation=generation,
        queue=PresentationQueue(),
        user_text="overlap",
    )
    response = await process.prompt(
        [TextContentBlock(type="text", text="overlap")], generation=generation, projection=projection
    )
    await process.retire()

    wire = [
        row["sourceOrdinal"]
        for row in _read_journal(journal)
        if row.get("event") == "session_update"
    ]
    projected = [row.source_ordinal for row in projection.queue.snapshot()]
    assert response.stop_reason == "end_turn"
    assert arrivals[:2] == [0, 1]
    assert wire == list(range(64))
    assert projected == wire


@pytest.mark.asyncio
async def test_one_process_admits_only_one_acp_session(tmp_path: Path):
    launch, _ = _fake_launch(tmp_path)
    process, _ = await _start(tmp_path, launch)
    await process.initialize()
    await process.new_session(cwd=tmp_path, mcp_servers=[])
    with pytest.raises(RuntimeError, match="already exists"):
        await process.new_session(cwd=tmp_path, mcp_servers=[])
    await process.retire()


@pytest.mark.asyncio
async def test_stderr_drain_failure_signals_the_process_owner(tmp_path: Path):
    launch, _ = _fake_launch(tmp_path, updates=[])
    process, _ = await _start(tmp_path, launch)
    assert process._stderr_task is not None
    process._stderr_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await process._stderr_task

    class BrokenReader:
        async def read(self, _size: int):
            raise OSError("fixture read failure")

    process._stderr_task = asyncio.create_task(process._drain_stderr(BrokenReader()))
    await process._stderr_task
    assert process.transport_failure.is_set()
    result = await process.retire(send_close=False)
    assert result.stderr_failure_code == "stderr_drain_failed"
    assert not result.clean


@pytest.mark.asyncio
async def test_initialize_refuses_missing_close_capability(tmp_path: Path):
    launch, _ = _fake_launch(tmp_path, advertise_close=False)
    process, claim = await _start(tmp_path, launch)
    with pytest.raises(AcpCapabilityError, match="session_close_required"):
        await process.initialize()
    result = await process.retire(send_close=False)
    assert result.child_exit_observed
    assert not claim.path.exists()


@pytest.mark.asyncio
async def test_initialize_refuses_wrong_protocol(tmp_path: Path):
    launch, _ = _fake_launch(tmp_path, protocol_version=PROTOCOL_VERSION + 1)
    process, _ = await _start(tmp_path, launch)
    with pytest.raises(AcpCapabilityError, match="protocol_version_mismatch"):
        await process.initialize()
    await process.retire(send_close=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_key", ["null_agent_capabilities", "null_session_capabilities"])
async def test_initialize_refuses_null_required_capabilities(tmp_path: Path, scenario_key: str):
    launch, _ = _fake_launch(tmp_path, **{scenario_key: True})
    process, _ = await _start(tmp_path, launch)
    with pytest.raises(AcpCapabilityError, match="session_close_required"):
        await process.initialize()
    await process.retire(send_close=False)


@pytest.mark.asyncio
async def test_initialize_treats_null_optional_prompt_capabilities_as_no_image_support(tmp_path: Path):
    launch, _ = _fake_launch(tmp_path, null_prompt_capabilities=True)
    process, _ = await _start(tmp_path, launch)
    initialized = await process.initialize()
    assert not initialized.image_supported
    await process.retire(send_close=False)


@pytest.mark.asyncio
async def test_cancel_is_sent_by_prompt_owner_outside_callback(tmp_path: Path):
    launch, journal = _fake_launch(tmp_path, hang_prompt=True, updates=[])
    process, _ = await _start(tmp_path, launch)
    await process.initialize()
    await process.new_session(cwd=tmp_path, mcp_servers=[])
    generation = PromptGeneration(1, process.session_id, "prompt-1")
    projection = BoundedPromptProjection(generation=generation, queue=PresentationQueue(), user_text="hello")
    prompt_task = asyncio.create_task(
        process.prompt([TextContentBlock(type="text", text="hello")], generation=generation, projection=projection)
    )
    await asyncio.sleep(0.1)
    await process.cancel()
    response = await asyncio.wait_for(prompt_task, timeout=5)
    result = await process.retire()

    assert response.stop_reason == "cancelled"
    assert result.clean
    assert [row["method"] for row in _read_journal(journal) if "method" in row].count("session/cancel") == 1


@pytest.mark.asyncio
async def test_cancel_latches_when_it_races_prompt_startup(tmp_path: Path):
    launch, journal = _fake_launch(tmp_path, hang_prompt=True, updates=[])
    process, _ = await _start(tmp_path, launch)
    await process.initialize()
    await process.new_session(cwd=tmp_path, mcp_servers=[])
    generation = PromptGeneration(1, process.session_id, "prompt-race")
    projection = BoundedPromptProjection(generation=generation, queue=PresentationQueue(), user_text="hello")
    prompt_task = asyncio.create_task(
        process.prompt([TextContentBlock(type="text", text="hello")], generation=generation, projection=projection)
    )
    await process.cancel()
    try:
        response = await asyncio.wait_for(prompt_task, timeout=2)
    finally:
        await process.retire()

    assert response.stop_reason == "cancelled"
    assert [row["method"] for row in _read_journal(journal) if "method" in row].count("session/cancel") == 1


@pytest.mark.asyncio
async def test_close_failure_is_unclean_but_exact_child_is_retired(tmp_path: Path):
    launch, _ = _fake_launch(tmp_path, close_error=True, updates=[])
    process, claim = await _start(tmp_path, launch)
    await process.initialize()
    await process.new_session(cwd=tmp_path, mcp_servers=[])
    result = await process.retire()
    assert not result.clean
    assert result.child_exit_observed
    assert not claim.path.exists()


@pytest.mark.asyncio
async def test_uncertain_prompt_retirement_sends_no_close_request(tmp_path: Path):
    launch, journal = _fake_launch(tmp_path, hang_prompt=True, updates=[])
    process, _ = await _start(tmp_path, launch)
    await process.initialize()
    await process.new_session(cwd=tmp_path, mcp_servers=[])
    result = await process.retire(send_close=False)
    methods = [row["method"] for row in _read_journal(journal) if "method" in row]
    assert "session/close" not in methods
    assert not result.clean
    assert result.child_exit_observed


@pytest.mark.asyncio
async def test_unobserved_exit_is_bounded_and_preserves_claim(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("rook.agent.chat.acp_process.ACP_RETIRE_TIMEOUT_SECONDS", 0.01)
    claim = OpenClaim.acquire(tmp_path / "claims", str(tmp_path / "session.jsonl"))

    class HangingContext:
        async def __aexit__(self, *_args):
            await asyncio.Event().wait()

    class HangingProcess:
        returncode = None
        stderr = None

        def __init__(self):
            self.terminate_calls = 0
            self.kill_calls = 0

        def terminate(self):
            self.terminate_calls += 1

        def kill(self):
            self.kill_calls += 1

        async def wait(self):
            await asyncio.Event().wait()

    child = HangingProcess()
    process = OwnedAcpProcess(
        PrimeLaunch(argv=(sys.executable,), environment={}, cwd=tmp_path),
        claim,
        1,
        RookChatAcpClient(),
        HangingContext(),
        SimpleNamespace(),
        child,
    )

    result = await asyncio.wait_for(process.retire(send_close=False), timeout=0.2)

    assert not result.clean
    assert not result.child_exit_observed
    assert child.terminate_calls == 1
    assert child.kill_calls == 1
    assert claim.path.exists()


@pytest.mark.asyncio
async def test_positive_spawn_failure_releases_claim_and_uncertain_failure_preserves_it(tmp_path: Path):
    missing = PrimeLaunch(argv=(str(tmp_path / "missing.exe"),), environment={}, cwd=tmp_path)
    first_claim = OpenClaim.acquire(tmp_path / "claims", str(tmp_path / "one.jsonl"))
    with pytest.raises(FileNotFoundError):
        await OwnedAcpProcess.start(missing, first_claim, launch_generation=1)
    assert not first_claim.path.exists()

    second_claim = OpenClaim.acquire(tmp_path / "claims", str(tmp_path / "two.jsonl"))

    class UncertainContext:
        async def __aenter__(self):
            raise RuntimeError("unknown spawn state")

        async def __aexit__(self, *args):
            return None

    with pytest.raises(RuntimeError, match="unknown spawn state"):
        await OwnedAcpProcess.start(
            PrimeLaunch(argv=(sys.executable,), environment={}, cwd=tmp_path),
            second_claim,
            launch_generation=2,
            spawn_context_factory=lambda *_args, **_kwargs: UncertainContext(),
        )
    assert second_claim.path.exists()


@pytest.mark.asyncio
async def test_cancelled_spawn_attempt_closes_context_without_releasing_uncertain_claim(tmp_path: Path):
    claim = OpenClaim.acquire(tmp_path / "claims", str(tmp_path / "session.jsonl"))
    entered = asyncio.Event()
    closed = asyncio.Event()

    class BlockedContext:
        async def __aenter__(self):
            entered.set()
            await asyncio.Event().wait()

        async def __aexit__(self, *_args):
            closed.set()

    task = asyncio.create_task(
        OwnedAcpProcess.start(
            PrimeLaunch(argv=(sys.executable,), environment={}, cwd=tmp_path),
            claim,
            launch_generation=1,
            spawn_context_factory=lambda *_args, **_kwargs: BlockedContext(),
        )
    )
    await entered.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(closed.wait(), timeout=0.2)
    assert claim.path.exists()


@pytest.mark.asyncio
async def test_retirement_continues_after_waiter_cancellation(tmp_path: Path):
    claim = OpenClaim.acquire(tmp_path / "claims", str(tmp_path / "session.jsonl"))
    exit_started = asyncio.Event()
    release_exit = asyncio.Event()
    child_exited = asyncio.Event()

    class ControlledProcess:
        stderr = None

        def __init__(self):
            self.returncode = None

        async def wait(self):
            await child_exited.wait()
            return self.returncode

        def terminate(self):
            raise AssertionError("graceful context exit should settle the child")

        def kill(self):
            raise AssertionError("graceful context exit should settle the child")

    child = ControlledProcess()

    class ControlledContext:
        async def __aexit__(self, *_args):
            exit_started.set()
            await release_exit.wait()
            child.returncode = 0
            child_exited.set()

    process = OwnedAcpProcess(
        PrimeLaunch(argv=(sys.executable,), environment={}, cwd=tmp_path),
        claim,
        1,
        RookChatAcpClient(),
        ControlledContext(),
        SimpleNamespace(),
        child,
    )
    waiter = asyncio.create_task(process.retire(send_close=False))
    await exit_started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    release_exit.set()
    result = await asyncio.wait_for(process.retire(send_close=False), timeout=0.2)
    assert result.clean
    assert result.child_exit_observed
    assert not claim.path.exists()


@pytest.mark.asyncio
async def test_cancel_send_has_own_deadline_and_is_never_retried(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("rook.agent.chat.acp_process.ACP_CANCEL_SEND_TIMEOUT_SECONDS", 0.01)
    claim = OpenClaim.acquire(tmp_path / "claims", str(tmp_path / "session.jsonl"))

    class HangingConnection:
        def __init__(self):
            self.cancel_calls = 0

        async def cancel(self, _session_id):
            self.cancel_calls += 1
            await asyncio.Event().wait()

    connection = HangingConnection()
    process = OwnedAcpProcess(
        PrimeLaunch(argv=(sys.executable,), environment={}, cwd=tmp_path),
        claim,
        1,
        RookChatAcpClient(),
        SimpleNamespace(),
        connection,
        SimpleNamespace(returncode=None, stderr=None),
    )
    process.session_id = "acp-session"
    process._active_cancel = asyncio.Event()

    with pytest.raises(RuntimeError, match="session_cancel_uncertain"):
        await asyncio.wait_for(process.cancel(), timeout=0.05)
    await process.cancel()

    assert connection.cancel_calls == 1
    assert process.transport_failure.is_set()


def test_service_captures_prime_environment_before_loading_dotenv(monkeypatch):
    observed: dict[str, object] = {}
    monkeypatch.setenv("PRE_DOTENV", "original")

    def load_env():
        os.environ["DOTENV_ONLY"] = "added"
        return "fixture.env"

    async def start_chat_server(**kwargs):
        observed.update(kwargs)

    async def wait_for_chat_server():
        return None

    async def stop_chat_server():
        return None

    monkeypatch.setattr(service_main, "_load_env", load_env)
    args = SimpleNamespace(port=0, include_gh_health=False, owner="test", rhino_process_id=41)
    monkeypatch.setattr(service_main, "_parse_args", lambda: args)
    monkeypatch.setattr(service_main, "_load_env", load_env)
    monkeypatch.setattr(service_main, "start_chat_server", start_chat_server)
    monkeypatch.setattr(service_main, "wait_for_chat_server", wait_for_chat_server)
    monkeypatch.setattr(service_main, "stop_chat_server", stop_chat_server)

    service_main.main()

    prime_environment = observed["prime_base_environment"]
    assert prime_environment["PRE_DOTENV"] == "original"
    assert "DOTENV_ONLY" not in prime_environment
