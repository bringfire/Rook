from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest
import pytest_asyncio

from rook.agent.chat.prime_backend import (
    PendingAbort,
    PrimeBackendError,
    PrimeChatBackend,
    PromptSubscription,
    PromptSubscriptionBuffer,
)
from rook.agent.chat.prime_process import (
    PrimeControlTimeout,
    PrimeLaunchConfiguration,
    PrimeProcessLost,
    PrimeRuntimeState,
)
from rook.agent.chat.prime_registry import (
    LifecycleRecord,
    PrimeConversationRecord,
    PrimeConversationRecordV2,
    PrimeConversationRegistry,
    PrimeModelSelection,
    RegistryLockError,
    TargetFingerprint,
    TargetFingerprintV2,
)
from rook.agent.chat.prime_runtime_contract import (
    PrimeRuntimeContractOwner,
    build_runtime_contract,
    stage_product_package,
)


pytestmark = pytest.mark.asyncio
PID = 1234
START_TICKS = "638918000000000000"
DEFAULT_MODEL = PrimeModelSelection("fixture", "model", None)
GH_ID = "12345678-1234-1234-1234-1234567890ab"


def target(*, pid: int = PID, ticks: str = START_TICKS, serial: int = 42) -> TargetFingerprint:
    return TargetFingerprint(pid, ticks, serial)


def target_v2(
    *,
    pid: int = PID,
    ticks: str = START_TICKS,
    serial: int = 42,
    grasshopper_document_id: str | None = GH_ID,
) -> TargetFingerprintV2:
    return TargetFingerprintV2(pid, ticks, serial, grasshopper_document_id)


def runtime_owner(tmp_path: Path, *, profile: str = "readonly") -> PrimeRuntimeContractOwner:
    source = tmp_path / "rook-source"
    (source / "src" / "rook_full").mkdir(parents=True)
    (source / "references").mkdir()
    (source / "SKILL.md").write_text("Rook contract", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname='rook-full'\n", encoding="utf-8")
    (source / "src" / "rook_full" / "__init__.py").write_text(
        "async def search(query): return query\n"
        "async def read(name): return name\n"
        "async def call(name, arguments): return arguments\n",
        encoding="utf-8",
    )
    (source / "references" / "grasshopper.md").write_text("GH", encoding="utf-8")
    product_root = tmp_path / "product"
    package = stage_product_package(source, product_root=product_root)

    prime_root = tmp_path / "prime"
    goal_root = prime_root / "packages" / "coding-agent" / "skills" / "goal"
    (goal_root / "src" / "goal").mkdir(parents=True)
    (goal_root / "SKILL.md").write_text("Goal", encoding="utf-8")
    (goal_root / "pyproject.toml").write_text("[project]\nname='goal'\n", encoding="utf-8")
    (goal_root / "src" / "goal" / "__init__.py").write_text("async def get(): return None\n", encoding="utf-8")
    bundle_manifest = prime_root / "bundle-manifest.json"
    bundle_manifest.write_bytes(b"prime-bundle")
    bundle_sha = hashlib.sha256(bundle_manifest.read_bytes()).hexdigest().upper()
    kernel_root = tmp_path / "kernels"
    contract = build_runtime_contract(
        prime_bundle_manifest_sha256=bundle_sha,
        prime_git_commit_provenance="prime-test-commit",
        goal_skill_root=goal_root,
        goal_skill_path_identity="packages/coding-agent/skills/goal",
        rook_package=package,
        capability_profile=profile,
        kernel_root=kernel_root,
        runtime_compatibility_version=1,
    )
    installed = tmp_path / "installed"
    mcp_python = installed / "venv" / "Scripts" / "python.exe"
    mcp_workdir = installed / "app" / "mcp_server"
    data_root = installed / "data"
    for directory in (
        mcp_python.parent,
        mcp_workdir,
        data_root / "dspy-cache",
        installed / "app" / "chirp",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    mcp_python.touch()
    return PrimeRuntimeContractOwner(
        contract=contract,
        prime_root=prime_root,
        prime_bundle_manifest_path=bundle_manifest,
        prime_git_commit_provenance="prime-test-commit",
        goal_skill_root=goal_root,
        product_root=product_root,
        kernel_root=kernel_root,
        product_environment={
            "ROOK_MCP_PYTHON_EXECUTABLE": str(mcp_python),
            "ROOK_MCP_WORKING_DIRECTORY": str(mcp_workdir),
            "ROOK_INSTALL_ROOT": str(installed / "app"),
            "ROOK_DATA_DIR": str(data_root),
            "DSPY_CACHEDIR": str(data_root / "dspy-cache"),
            "CHIRP_HOME": str(installed / "app" / "chirp"),
            "ROOK_MODE": "release",
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
        },
    )


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class FakePrimeProcess:
    def __init__(
        self,
        root: Path,
        generation: int,
        model: PrimeModelSelection,
        resume_session_path: str | None,
        launch_configuration: PrimeLaunchConfiguration | None,
    ) -> None:
        self.generation = generation
        self.model = model
        self.launch_configuration = launch_configuration
        self.session_path = Path(resume_session_path or root / f"session-{generation}.jsonl")
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.touch(exist_ok=True)
        self.session_id = self.session_path.stem
        self.listeners: list[Callable[[int, dict[str, Any]], None]] = []
        self.commands: list[dict[str, Any]] = []
        self.prompt_future: asyncio.Future[dict[str, Any]] | None = None
        self.prompt_id: str | None = None
        self.retired = False
        self.retire_grace: list[float] = []
        self.complete_on_abort = False
        self.abort_gate: asyncio.Event | None = None
        self.set_model_error: Exception | None = None
        self.set_thinking_error: Exception | None = None
        self.get_state_error: Exception | None = None
        self.models_error: Exception | None = None
        self.control_error: dict[str, Exception] = {}

    async def start(self) -> PrimeRuntimeState:
        self.commands.append({"type": "get_state"})
        return self.runtime_state()

    def runtime_state(self) -> PrimeRuntimeState:
        return PrimeRuntimeState(
            session_id=self.session_id,
            session_path=str(self.session_path.absolute()),
            provider=self.model.provider,
            model_id=self.model.id,
            thinking=self.model.thinking,
        )

    def subscribe(self, listener: Callable[[int, dict[str, Any]], None]):
        self.listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    def emit(self, event: dict[str, Any], *, generation: int | None = None) -> None:
        for listener in tuple(self.listeners):
            listener(self.generation if generation is None else generation, event)

    async def command(
        self,
        command: dict[str, Any],
        *,
        expected_command: str,
        timeout_seconds: float | None = 10.0,
    ) -> dict[str, Any]:
        if self.retired:
            raise PrimeProcessLost("fake process retired")
        assert command["type"] == expected_command
        command = dict(command)
        command.setdefault("id", f"fake-{len(self.commands) + 1}")
        self.commands.append(command)
        if expected_command in self.control_error:
            raise self.control_error[expected_command]
        if expected_command == "set_rlm_max_depth":
            return self.response(
                command,
                success=True,
                data={"maxDepth": command["maxDepth"], "source": "chat"},
            )
        if expected_command == "get_rlm_max_depth_status":
            return self.response(
                command,
                success=True,
                data={"maxDepth": 0, "source": "chat"},
            )
        if expected_command == "prepare_ipython_runtime":
            assert self.launch_configuration is not None
            launch = self.launch_configuration
            interpreter = launch.kernel_environment_path / "Scripts" / "python.exe"
            interpreter.parent.mkdir(parents=True, exist_ok=True)
            interpreter.touch()
            return self.response(
                command,
                success=True,
                data={
                    "interpreterPath": str(interpreter),
                    "rookFullFile": str(
                        launch.rook_skill_path / "src" / "rook_full" / "__init__.py"
                    ),
                    "goalFile": str(
                        launch.goal_skill_path / "src" / "goal" / "__init__.py"
                    ),
                    "callables": {"search": True, "read": True, "call": True},
                },
            )
        if expected_command == "prompt_and_wait":
            self.prompt_id = command["id"]
            self.prompt_future = asyncio.get_running_loop().create_future()
            return await self.prompt_future
        if expected_command == "abort":
            if self.complete_on_abort:
                self.settle("completed")
            if self.abort_gate is not None:
                await self.abort_gate.wait()
            return self.response(command, success=True)
        if expected_command == "get_state":
            if self.get_state_error is not None:
                raise self.get_state_error
            state = self.runtime_state()
            return self.response(
                command,
                success=True,
                data={
                    "sessionId": state.session_id,
                    "sessionFile": state.session_path,
                    "model": {"provider": state.provider, "id": state.model_id},
                    "thinkingLevel": state.thinking,
                },
            )
        if expected_command == "get_available_models":
            if self.models_error is not None:
                raise self.models_error
            return self.response(
                command,
                success=True,
                data={
                    "models": [
                        {
                            "provider": "fixture",
                            "id": "model",
                            "contextWindow": 1000,
                            "reasoning": True,
                        }
                    ]
                },
            )
        if expected_command == "set_model":
            if self.set_model_error is not None:
                raise self.set_model_error
            self.model = PrimeModelSelection(
                command["provider"], command["modelId"], self.model.thinking
            )
            return self.response(command, success=True, data={})
        if expected_command == "set_thinking_level":
            if self.set_thinking_error is not None:
                raise self.set_thinking_error
            self.model = PrimeModelSelection(
                self.model.provider, self.model.id, command["level"]
            )
            return self.response(command, success=True)
        raise AssertionError(f"unsupported fake command: {expected_command}")

    @staticmethod
    def response(
        command: dict[str, Any],
        *,
        success: bool,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": command["id"],
            "type": "response",
            "command": command["type"],
            "success": success,
        }
        if data is not None:
            result["data"] = data
        return result

    def settle(self, outcome: str) -> None:
        assert self.prompt_future is not None and self.prompt_id is not None
        if not self.prompt_future.done():
            self.prompt_future.set_result(
                {
                    "id": self.prompt_id,
                    "type": "response",
                    "command": "prompt_and_wait",
                    "success": True,
                    "data": {"outcome": outcome},
                }
            )

    def fail_prompt(self, code: str = "execution_failed") -> None:
        assert self.prompt_future is not None and self.prompt_id is not None
        if not self.prompt_future.done():
            self.prompt_future.set_result(
                {
                    "id": self.prompt_id,
                    "type": "response",
                    "command": "prompt_and_wait",
                    "success": False,
                    "error": {"code": code, "message": "fake prompt failure"},
                }
            )

    def lose(self) -> None:
        assert self.prompt_future is not None
        if not self.prompt_future.done():
            self.prompt_future.set_exception(PrimeProcessLost("fake process lost"))

    async def retire(self, grace_seconds: float) -> None:
        self.retire_grace.append(grace_seconds)
        self.retired = True
        if self.prompt_future is not None and not self.prompt_future.done():
            self.prompt_future.set_exception(PrimeProcessLost("fake process retired"))


class FakeProcessFactory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.created: list[FakePrimeProcess] = []

    def __call__(
        self,
        generation: int,
        model: PrimeModelSelection,
        resume_session_path: str | None,
        launch_configuration: PrimeLaunchConfiguration | None = None,
    ) -> FakePrimeProcess:
        process = FakePrimeProcess(
            self.root,
            generation,
            model,
            resume_session_path,
            launch_configuration,
        )
        self.created.append(process)
        return process


@dataclass
class Harness:
    backend: PrimeChatBackend
    registry: PrimeConversationRegistry
    factory: FakeProcessFactory
    clock: FakeClock


@pytest_asyncio.fixture
async def harness(tmp_path: Path):
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    factory = FakeProcessFactory(tmp_path / "sessions")
    clock = FakeClock()
    backend = PrimeChatBackend(
        registry=registry,
        process_factory=factory,
        default_model=DEFAULT_MODEL,
        clock=clock,
        retirement_grace_seconds=0.01,
    )
    value = Harness(backend, registry, factory, clock)
    try:
        yield value
    finally:
        await backend.shutdown()
        registry.close()


async def wait_for_prompt(process: FakePrimeProcess) -> None:
    for _ in range(100):
        if process.prompt_future is not None:
            return
        await asyncio.sleep(0)
    raise AssertionError("prompt command was not dispatched")


async def drain(subscription: PromptSubscription) -> list[dict[str, Any]]:
    return [row async for row in subscription]


def runtime_harness(tmp_path: Path, *, profile: str = "readonly") -> Harness:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    factory = FakeProcessFactory(tmp_path / "sessions")
    clock = FakeClock()
    backend = PrimeChatBackend(
        registry=registry,
        process_factory=factory,
        default_model=DEFAULT_MODEL,
        runtime_contract_owner=runtime_owner(tmp_path, profile=profile),
        clock=clock,
        retirement_grace_seconds=0.01,
    )
    return Harness(backend, registry, factory, clock)


async def test_first_use_promotes_pending_runtime_only_after_fixed_preflight(
    tmp_path: Path,
) -> None:
    harness = runtime_harness(tmp_path)
    try:
        record = await harness.backend.create("conv_v2", target_v2())
        process = harness.factory.created[-1]

        assert isinstance(record, PrimeConversationRecordV2)
        assert record.runtime.preparation.status == "prepared"
        assert [row["type"] for row in process.commands] == [
            "get_state",
            "set_rlm_max_depth",
            "get_rlm_max_depth_status",
            "prepare_ipython_runtime",
        ]
        assert process.commands[1] == {
            "type": "set_rlm_max_depth",
            "maxDepth": 0,
            "global": False,
            "id": "fake-2",
        }
        assert Path(record.runtime.preparation.interpreter_path).is_file()

        subscription = await harness.backend.start_prompt("conv_v2", "hello")
        await wait_for_prompt(process)
        process.settle("completed")
        assert (await drain(subscription))[-1]["type"] == "done"
    finally:
        await harness.backend.shutdown()
        harness.registry.close()


async def test_failed_first_use_preflight_never_admits_a_prompt(
    tmp_path: Path,
) -> None:
    harness = runtime_harness(tmp_path)
    original = harness.factory.__call__

    def failing_factory(*args, **kwargs):
        process = original(*args, **kwargs)
        process.control_error["prepare_ipython_runtime"] = PrimeControlTimeout(
            "prepare_ipython_runtime"
        )
        return process

    harness.backend.process_factory = failing_factory
    try:
        with pytest.raises(PrimeBackendError) as caught:
            await harness.backend.create("conv_failed", target_v2())

        assert caught.value.code == "runtime_contract_unavailable"
        record = harness.registry.load("conv_failed")
        assert isinstance(record, PrimeConversationRecordV2)
        assert record.runtime.preparation.status == "pending"
        assert record.last_lifecycle.state == "failed"
        assert all(
            row["type"] != "prompt_and_wait"
            for row in harness.factory.created[-1].commands
        )
        assert harness.factory.created[-1].retired is True
    finally:
        await harness.backend.shutdown()
        harness.registry.close()


async def test_reopen_verifies_prepared_runtime_without_repairing_depth(
    tmp_path: Path,
) -> None:
    first = runtime_harness(tmp_path)
    owner = first.backend.runtime_contract_owner
    await first.backend.create("conv_reopen_v2", target_v2())
    await first.backend.shutdown()
    first.registry.close()

    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    factory = FakeProcessFactory(tmp_path / "sessions")
    backend = PrimeChatBackend(
        registry,
        factory,
        DEFAULT_MODEL,
        runtime_contract_owner=owner,
        retirement_grace_seconds=0.01,
    )
    try:
        record = await backend.reopen("conv_reopen_v2", target_v2())
        process = factory.created[-1]

        assert isinstance(record, PrimeConversationRecordV2)
        assert [row["type"] for row in process.commands] == [
            "get_state",
            "get_rlm_max_depth_status",
            "prepare_ipython_runtime",
        ]
    finally:
        await backend.shutdown()
        registry.close()


async def test_reopen_missing_prepared_environment_fails_before_launch(
    tmp_path: Path,
) -> None:
    first = runtime_harness(tmp_path)
    owner = first.backend.runtime_contract_owner
    record = await first.backend.create("conv_missing_env", target_v2())
    await first.backend.shutdown()
    first.registry.close()
    assert isinstance(record, PrimeConversationRecordV2)
    Path(record.runtime.kernel_environment_path).rename(tmp_path / "removed-kernel")

    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    factory = FakeProcessFactory(tmp_path / "sessions")
    backend = PrimeChatBackend(
        registry,
        factory,
        DEFAULT_MODEL,
        runtime_contract_owner=owner,
        retirement_grace_seconds=0.01,
    )
    try:
        with pytest.raises(PrimeBackendError) as caught:
            await backend.reopen("conv_missing_env", target_v2())

        assert caught.value.code == "runtime_contract_unavailable"
        assert factory.created == []
    finally:
        await backend.shutdown()
        registry.close()


def saved_record(
    tmp_path: Path,
    conversation_id: str,
    state: str,
    *,
    fingerprint: TargetFingerprint | None = None,
) -> PrimeConversationRecord:
    session_path = tmp_path / f"{conversation_id}.jsonl"
    session_path.touch()
    return PrimeConversationRecord(
        schema_version=1,
        conversation_id=conversation_id,
        prime_session_id=session_path.stem,
        prime_session_path=str(session_path),
        model=DEFAULT_MODEL,
        target=fingerprint or target(),
        last_lifecycle=LifecycleRecord(
            state=state,
            reason=None,
            updated_at_utc="2026-08-26T12:00:00Z",
        ),
    )


async def test_one_prompt_has_one_correlated_settlement(harness: Harness) -> None:
    await harness.backend.create("conv_one", target())
    subscription = await harness.backend.start_prompt("conv_one", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)

    process.settle("completed")
    rows = await drain(subscription)

    assert rows[-1] == {"type": "done", "reason": "completed"}
    assert sum(row["type"] == "done" for row in rows) == 1
    assert harness.registry.load("conv_one").last_lifecycle.state == "idle"


@pytest.mark.parametrize(
    "message",
    [
        "/goal",
        "/goal status",
        "/goal pause",
        "/goal resume",
        "/goal clear",
        "/goal stop",
        "  \t/goal status",
        "ordinary conversation",
    ],
)
async def test_panel_prompt_admits_only_goal_slash_family(
    harness: Harness, message: str
) -> None:
    await harness.backend.create("conv_command", target())

    subscription = await harness.backend.start_prompt("conv_command", message)
    process = harness.factory.created[-1]
    await wait_for_prompt(process)

    assert process.commands[-1]["message"] == message
    process.settle("completed")
    assert (await drain(subscription))[-1]["type"] == "done"


@pytest.mark.parametrize(
    "message",
    [
        "/compact",
        "/refine",
        "/autonomous",
        "/rlm-max-depth 0",
        "/goalkeeper",
        "/GOAL status",
        "/goal/status",
        "/future-command",
    ],
)
async def test_panel_prompt_refuses_other_slash_commands_before_state_or_dispatch(
    harness: Harness, message: str
) -> None:
    await harness.backend.create("conv_refused", target())
    process = harness.factory.created[-1]

    with pytest.raises(PrimeBackendError) as caught:
        await harness.backend.start_prompt("conv_refused", message)

    assert caught.value.code == "prime_command_not_admitted"
    assert harness.registry.load("conv_refused").last_lifecycle.state == "idle"
    assert all(row["type"] != "prompt_and_wait" for row in process.commands)


async def test_multiple_agent_end_events_do_not_settle_prompt(harness: Harness) -> None:
    await harness.backend.create("conv_segments", target())
    subscription = await harness.backend.start_prompt("conv_segments", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)
    process.emit({"type": "agent_end", "messages": []})
    process.emit({"type": "agent_end", "messages": []})
    await asyncio.sleep(0)

    assert harness.registry.load("conv_segments").last_lifecycle.state == "running"
    assert subscription.buffer.terminal_count == 0

    process.settle("completed")
    assert (await drain(subscription))[-1]["type"] == "done"


async def test_cancel_stays_requested_until_aborted_settlement(harness: Harness) -> None:
    await harness.backend.create("conv_cancel", target())
    subscription = await harness.backend.start_prompt("conv_cancel", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)

    lifecycle = await harness.backend.cancel("conv_cancel")
    assert lifecycle.state == "cancel_requested"
    assert harness.registry.load("conv_cancel").last_lifecycle.state == "cancel_requested"

    process.settle("aborted")
    assert (await drain(subscription))[-1] == {
        "type": "cancelled",
        "reason": "aborted",
    }
    assert harness.registry.load("conv_cancel").last_lifecycle.state == "idle"


async def test_natural_completion_wins_cancel_race_once(harness: Harness) -> None:
    await harness.backend.create("conv_race", target())
    subscription = await harness.backend.start_prompt("conv_race", "hello")
    process = harness.factory.created[-1]
    process.complete_on_abort = True
    process.abort_gate = asyncio.Event()
    await wait_for_prompt(process)

    cancel_task = asyncio.create_task(harness.backend.cancel("conv_race"))
    await asyncio.sleep(0)
    pending = harness.backend.pending_abort("conv_race")
    assert pending == PendingAbort(
        abort_request_id=pending.abort_request_id,
        prompt_request_id=process.prompt_id,
        launch_generation=process.generation,
    )
    for _ in range(20):
        if harness.registry.load("conv_race").last_lifecycle.state == "idle":
            break
        await asyncio.sleep(0)
    assert harness.registry.load("conv_race").last_lifecycle.reason == "completed_before_abort"

    process.abort_gate.set()
    await cancel_task
    rows = await drain(subscription)
    assert rows[-1] == {"type": "done", "reason": "completed_before_abort"}
    assert subscription.buffer.terminal_count == 1


async def test_process_loss_marks_failed_without_replay(harness: Harness) -> None:
    await harness.backend.create("conv_loss", target())
    subscription = await harness.backend.start_prompt("conv_loss", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)

    process.lose()
    rows = await drain(subscription)

    assert rows[-1]["type"] == "error"
    assert rows[-1]["code"] == "settlement_unknown"
    assert harness.registry.load("conv_loss").last_lifecycle.state == "failed"
    assert len([row for row in process.commands if row["type"] == "prompt_and_wait"]) == 1


async def _assert_saved_interrupted_state_rehydrates_failed(
    tmp_path: Path,
    state: str,
) -> None:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    registry.write(saved_record(tmp_path, "conv_saved", state))
    backend = PrimeChatBackend(
        registry=registry,
        process_factory=FakeProcessFactory(tmp_path / "sessions"),
        default_model=DEFAULT_MODEL,
    )
    try:
        loaded = registry.load("conv_saved")
        assert loaded.last_lifecycle.state == "failed"
        assert loaded.last_lifecycle.reason == "broker_restart_interrupted"
    finally:
        await backend.shutdown()
        registry.close()


async def test_saved_running_rehydrates_failed(tmp_path: Path) -> None:
    await _assert_saved_interrupted_state_rehydrates_failed(tmp_path, "running")


async def test_saved_cancel_requested_rehydrates_failed(tmp_path: Path) -> None:
    await _assert_saved_interrupted_state_rehydrates_failed(tmp_path, "cancel_requested")


async def test_failed_requires_explicit_reopen(harness: Harness) -> None:
    await harness.backend.create("conv_failed", target())
    subscription = await harness.backend.start_prompt("conv_failed", "hello")
    first = harness.factory.created[-1]
    await wait_for_prompt(first)
    first.lose()
    await drain(subscription)

    with pytest.raises(PrimeBackendError, match="explicit reopen"):
        await harness.backend.start_prompt("conv_failed", "again")

    reopened = await harness.backend.reopen("conv_failed", target())
    assert reopened.last_lifecycle.state == "idle"
    assert len(harness.factory.created) == 2


async def test_pid_reuse_with_new_start_ticks_is_rejected(
    tmp_path: Path,
) -> None:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    registry.write(saved_record(tmp_path, "conv_target", "idle"))
    factory = FakeProcessFactory(tmp_path / "sessions")
    backend = PrimeChatBackend(registry, factory, DEFAULT_MODEL)
    try:
        with pytest.raises(PrimeBackendError, match="target_mismatch"):
            await backend.reopen(
                "conv_target",
                target(ticks=str(int(START_TICKS) + 1)),
            )
        assert factory.created == []
    finally:
        await backend.shutdown()
        registry.close()


async def test_document_serial_mismatch_is_rejected(tmp_path: Path) -> None:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    registry.write(saved_record(tmp_path, "conv_target", "idle"))
    factory = FakeProcessFactory(tmp_path / "sessions")
    backend = PrimeChatBackend(registry, factory, DEFAULT_MODEL)
    try:
        with pytest.raises(PrimeBackendError, match="target_mismatch"):
            await backend.reopen("conv_target", target(serial=99))
        assert factory.created == []
    finally:
        await backend.shutdown()
        registry.close()


async def test_second_registry_writer_refuses(tmp_path: Path) -> None:
    first = PrimeConversationRegistry(tmp_path, PID, START_TICKS)
    try:
        with pytest.raises(RegistryLockError):
            PrimeConversationRegistry(tmp_path, PID, START_TICKS)
    finally:
        first.close()


async def test_sibling_registry_updates_are_independent(harness: Harness) -> None:
    await harness.backend.create("conv_a", target())
    await harness.backend.create("conv_b", target())
    sibling_path = harness.registry.namespace / "conv_b.json"
    before = sibling_path.read_bytes()

    await harness.backend.close("conv_a")

    assert sibling_path.read_bytes() == before


async def test_stale_launch_generation_event_is_ignored(harness: Harness) -> None:
    await harness.backend.create("conv_old", target())
    old = harness.factory.created[-1]
    harness.clock.value = 1.0
    single_capacity = harness.backend
    single_capacity.max_residents = 1
    await single_capacity.create("conv_other", target())
    await single_capacity.reopen("conv_old", target())
    subscription = await single_capacity.start_prompt("conv_old", "hello")

    old.emit(
        {
            "type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "delta": "stale"},
        }
    )
    await asyncio.sleep(0)
    assert subscription.buffer.rows == ()

    current = harness.factory.created[-1]
    await wait_for_prompt(current)
    current.settle("completed")
    await drain(subscription)


async def test_atomic_registry_failure_preserves_previous_record(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await harness.backend.create("conv_atomic", target())
    path = harness.registry.namespace / "conv_atomic.json"
    before = path.read_bytes()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            "rook.agent.chat.prime_registry.os.replace",
            lambda _source, _target: (_ for _ in ()).throw(OSError("replace failed")),
        )

        with pytest.raises(OSError, match="replace failed"):
            await harness.backend.close("conv_atomic")

    assert path.read_bytes() == before


async def test_capacity_retires_lru_idle_only(harness: Harness) -> None:
    harness.backend.max_residents = 2
    await harness.backend.create("conv_lru", target())
    first = harness.factory.created[-1]
    harness.clock.value = 1.0
    await harness.backend.create("conv_recent", target())
    harness.clock.value = 2.0

    await harness.backend.create("conv_new", target())

    assert first.retired is True
    assert harness.registry.load("conv_lru").last_lifecycle.state == "idle"


async def test_capacity_refuses_when_every_child_is_active(harness: Harness) -> None:
    harness.backend.max_residents = 1
    await harness.backend.create("conv_busy", target())
    await harness.backend.start_prompt("conv_busy", "hello")

    with pytest.raises(PrimeBackendError, match="capacity_exhausted"):
        await harness.backend.create("conv_refused", target())
    await harness.backend.close("conv_busy")


async def test_idle_retirement_preserves_session_record(harness: Harness) -> None:
    await harness.backend.create("conv_idle", target())
    process = harness.factory.created[-1]
    harness.clock.value = 2_000.0

    await harness.backend.retire_idle()

    assert process.retired is True
    assert harness.registry.load("conv_idle").last_lifecycle.state == "idle"


async def test_tab_close_cancels_and_closes(harness: Harness) -> None:
    await harness.backend.create("conv_close", target())
    subscription = await harness.backend.start_prompt("conv_close", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)

    lifecycle = await harness.backend.close("conv_close")

    assert lifecycle.state == "closed"
    assert process.retired is True
    assert harness.registry.load("conv_close").last_lifecycle.state == "closed"
    with pytest.raises(StopAsyncIteration):
        await subscription.__anext__()


async def test_close_remains_closed_after_late_completion(harness: Harness) -> None:
    await harness.backend.create("conv_late", target())
    subscription = await harness.backend.start_prompt("conv_late", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)
    pending = process.prompt_future

    await harness.backend.close("conv_late")
    assert pending is not None
    if not pending.done():
        process.settle("completed")
    await asyncio.sleep(0)

    assert harness.registry.load("conv_late").last_lifecycle.state == "closed"
    assert subscription.buffer.terminal_count == 0


async def test_close_remains_closed_after_process_loss(harness: Harness) -> None:
    await harness.backend.create("conv_lost_close", target())
    subscription = await harness.backend.start_prompt("conv_lost_close", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)

    await harness.backend.close("conv_lost_close")
    process.lose()
    await asyncio.sleep(0)

    assert harness.registry.load("conv_lost_close").last_lifecycle.state == "closed"
    assert subscription.buffer.terminal_count == 0


async def test_document_retirement_never_rebinds_target(harness: Harness) -> None:
    harness.backend.max_residents = 1
    await harness.backend.create("conv_document", target())
    await harness.backend.create("conv_dormant", target())
    await harness.backend.create("conv_other_document", target(serial=43))

    await harness.backend.retire_document(target())

    assert harness.registry.load("conv_document").last_lifecycle.state == "closed"
    assert harness.registry.load("conv_dormant").last_lifecycle.state == "closed"
    with pytest.raises(PrimeBackendError):
        await harness.backend.reopen("conv_document", target(serial=99))


async def test_shutdown_uses_one_global_ten_second_deadline(harness: Harness) -> None:
    harness.backend.SHUTDOWN_TIMEOUT_SECONDS = 0.05
    await harness.backend.create("conv_shutdown_a", target())
    await harness.backend.create("conv_shutdown_b", target())
    await harness.backend.start_prompt("conv_shutdown_a", "still running")
    processes = list(harness.factory.created)

    await harness.backend.shutdown()

    assert all(process.retired for process in processes)
    assert all(
        len(process.retire_grace) == 1 and 0 <= process.retire_grace[0] <= 10
        for process in processes
    )
    assert harness.registry.load("conv_shutdown_a").last_lifecycle.state == "failed"
    assert harness.registry.load("conv_shutdown_b").last_lifecycle.state == "idle"


async def test_slow_subscriber_coalesces_text_without_blocking_settlement(
    harness: Harness,
) -> None:
    await harness.backend.create("conv_slow", target())
    subscription = await harness.backend.start_prompt("conv_slow", "hello")
    process = harness.factory.created[-1]
    await wait_for_prompt(process)
    for number in range(1_000):
        process.emit(
            {
                "type": "message_update",
                "assistantMessageEvent": {
                    "type": "text_delta",
                    "delta": f"{number},",
                },
            }
        )
        if number % 5 == 0:
            process.emit({"type": "agent_end", "messages": []})
    process.settle("completed")

    for _ in range(100):
        if harness.registry.load("conv_slow").last_lifecycle.state == "idle":
            break
        await asyncio.sleep(0)

    assert process.prompt_future is not None and process.prompt_future.done()
    assert len(subscription.buffer) <= 128
    rows = await drain(subscription)
    assert "".join(row.get("content", "") for row in rows) == "".join(
        f"{number}," for number in range(1_000)
    )
    assert sum(row["type"] == "done" for row in rows) == 1


async def test_close_wakes_waiting_subscription() -> None:
    buffer = PromptSubscriptionBuffer()
    waiter = asyncio.create_task(buffer.next())
    await asyncio.sleep(0)

    buffer.close()

    with pytest.raises(StopAsyncIteration):
        await waiter


async def test_late_rows_after_terminal_are_ignored() -> None:
    buffer = PromptSubscriptionBuffer()
    buffer.publish({"type": "done", "reason": "completed"})
    buffer.publish({"type": "text_delta", "content": "late"})
    buffer.publish({"type": "error", "code": "late", "message": "late"})

    assert buffer.rows == ({"type": "done", "reason": "completed"},)
    assert buffer.terminal_count == 1


async def test_partial_model_update_reconciles_actual_runtime_state(harness: Harness) -> None:
    await harness.backend.create("conv_model", target())
    process = harness.factory.created[-1]
    process.set_thinking_error = RuntimeError("thinking refused")

    with pytest.raises(PrimeBackendError) as caught:
        await harness.backend.set_model(
            "conv_model",
            "fixture",
            "new-model",
            "high",
        )

    assert caught.value.code == "model_update_failed_reconciled"
    assert caught.value.actual_model == PrimeModelSelection("fixture", "new-model", None)
    persisted = harness.registry.load("conv_model")
    assert persisted.model == caught.value.actual_model
    assert persisted.last_lifecycle.state == "idle"


async def test_failed_model_reconciliation_marks_conversation_failed(harness: Harness) -> None:
    await harness.backend.create("conv_model_fail", target())
    process = harness.factory.created[-1]
    process.set_thinking_error = RuntimeError("thinking refused")
    process.get_state_error = RuntimeError("state unavailable")

    with pytest.raises(PrimeBackendError, match="model_reconciliation_failed"):
        await harness.backend.set_model(
            "conv_model_fail",
            "fixture",
            "new-model",
            "high",
        )

    assert harness.registry.load("conv_model_fail").last_lifecycle.state == "failed"
    assert process.retired is True


async def test_stalled_control_response_fails_boundedly(harness: Harness) -> None:
    await harness.backend.create("conv_control", target())
    process = harness.factory.created[-1]
    process.models_error = PrimeControlTimeout("get_available_models")

    with pytest.raises(PrimeControlTimeout):
        await asyncio.wait_for(harness.backend.models("conv_control"), timeout=0.1)
