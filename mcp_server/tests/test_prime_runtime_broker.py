from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from rook.agent.chat import prime_backend
from rook.agent.chat.prime_process import (
    PrimeControlTimeout,
    PrimeProcessLost,
    PrimeRuntimeState,
)
from rook.agent.chat.prime_registry import (
    PrimeConversationRecordV2,
    PrimeConversationRegistry,
    PrimeModelSelection,
    TargetFingerprintV2,
)
from rook.agent.chat.prime_runtime_contract import (
    build_runtime_contract,
    stage_product_package,
    write_package_manifest,
)


pytestmark = pytest.mark.asyncio
PID = 1234
START_TICKS = "638918000000000000"
MODEL = PrimeModelSelection("fixture", "model", None)
GH_DOCUMENT_ID = "01234567-89ab-cdef-0123-456789abcdef"


def _write_python_skill(root: Path, package: str) -> None:
    (root / "src" / package).mkdir(parents=True)
    (root / "SKILL.md").write_text(f"# {package}\n", encoding="utf-8", newline="\n")
    (root / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0.0.0'\n",
        encoding="utf-8",
        newline="\n",
    )
    (root / "src" / package / "__init__.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
        newline="\n",
    )
    if package == "rook_full":
        write_package_manifest(root)


def runtime_binding(tmp_path: Path, *, profile: str = "readonly"):
    source = tmp_path / "source-rook-full"
    goal = tmp_path / "goal"
    product_root = tmp_path / "product"
    kernel_root = tmp_path / "kernels"
    product_root.mkdir()
    _write_python_skill(source, "rook_full")
    _write_python_skill(goal, "goal")
    package = stage_product_package(source, product_root=product_root)
    contract = build_runtime_contract(
        prime_bundle_manifest_sha256="A" * 64,
        prime_git_commit_provenance="fixture-prime",
        goal_skill_root=goal,
        goal_skill_path_identity="packages/coding-agent/skills/goal",
        rook_package=package,
        capability_profile=profile,
        kernel_root=kernel_root,
        runtime_compatibility_version=1,
    )
    return prime_backend.PrimeRuntimeBinding(
        contract=contract,
        product_root=product_root,
        goal_skill_root=goal,
        kernel_root=kernel_root,
    )


def target() -> TargetFingerprintV2:
    return TargetFingerprintV2(PID, START_TICKS, 42, GH_DOCUMENT_ID)


class FakeRuntimeProcess:
    def __init__(
        self,
        root: Path,
        generation: int,
        model: PrimeModelSelection,
        resume_session_path: str | None,
        binding,
        locked_target: TargetFingerprintV2,
        registry: PrimeConversationRegistry,
        conversation_id: str,
        scenario: str,
    ) -> None:
        self.generation = generation
        self.model = model
        self.binding = binding
        self.locked_target = locked_target
        self.registry = registry
        self.conversation_id = conversation_id
        self.scenario = scenario
        self.session_path = Path(
            resume_session_path or root / f"runtime-session-{generation}.jsonl"
        ).absolute()
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.touch(exist_ok=True)
        self.session_id = self.session_path.stem
        self.commands: list[dict[str, Any]] = []
        self.command_timeouts: list[tuple[str, float | None]] = []
        self.listeners: list[Callable[[int, dict[str, Any]], None]] = []
        self.retired = False
        self.pending_seen_before_prepare = False

    async def start(self) -> PrimeRuntimeState:
        return PrimeRuntimeState(
            session_id=self.session_id,
            session_path=str(self.session_path),
            provider=self.model.provider,
            model_id=self.model.id,
            thinking=self.model.thinking,
        )

    def subscribe(self, listener):
        self.listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self.listeners:
                self.listeners.remove(listener)

        return unsubscribe

    async def command(
        self,
        command: dict[str, Any],
        *,
        expected_command: str,
        timeout_seconds: float | None = 10.0,
    ) -> dict[str, Any]:
        assert command["type"] == expected_command
        self.commands.append(dict(command))
        self.command_timeouts.append((expected_command, timeout_seconds))
        command = dict(command)
        command.setdefault("id", f"runtime-{len(self.commands)}")
        if self.scenario == expected_command + "_timeout":
            raise PrimeControlTimeout(expected_command)
        if self.scenario == "process_loss" and expected_command == "prepare_ipython_runtime":
            raise PrimeProcessLost("fake runtime process lost")
        if expected_command == "set_rlm_max_depth":
            pending = self.registry.load(self.conversation_id)
            self.pending_seen_before_prepare = (
                isinstance(pending, PrimeConversationRecordV2)
                and pending.runtime.preparation.status == "pending"
            )
            return self._response(command, {"maxDepth": 0, "source": "chat"})
        if expected_command == "get_rlm_max_depth_status":
            data = (
                {"maxDepth": 1, "source": "global"}
                if self.scenario == "wrong_depth"
                else {"maxDepth": 0, "source": "chat"}
            )
            return self._response(command, data)
        if expected_command == "prepare_ipython_runtime":
            if self.scenario == "prepare_failure":
                return {
                    "id": command["id"],
                    "type": "response",
                    "command": expected_command,
                    "success": False,
                    "error": "kernel bootstrap failed",
                }
            environment = self.binding.contract.kernel_environment_path
            interpreter = environment / "Scripts" / "python.exe"
            if self.scenario != "partial_environment":
                interpreter.parent.mkdir(parents=True, exist_ok=True)
                interpreter.touch(exist_ok=True)
            if self.scenario == "wrong_interpreter":
                interpreter = self.binding.kernel_root / "other" / "python.exe"
                interpreter.parent.mkdir(parents=True, exist_ok=True)
                interpreter.touch()
            rook_file = (
                self.binding.contract.rook_package.root
                / "src"
                / "rook_full"
                / "__init__.py"
            )
            goal_file = self.binding.goal_skill_root / "src" / "goal" / "__init__.py"
            if self.scenario == "wrong_rook_import":
                rook_file = self.binding.product_root / "other" / "rook_full.py"
                rook_file.parent.mkdir(parents=True, exist_ok=True)
                rook_file.touch()
            if self.scenario == "wrong_goal_import":
                goal_file = self.binding.product_root / "other" / "goal.py"
                goal_file.parent.mkdir(parents=True, exist_ok=True)
                goal_file.touch()
            callables = (
                {"search": True, "read": True, "call": False}
                if self.scenario == "wrong_callables"
                else {"search": True, "read": True, "call": True}
            )
            return self._response(
                command,
                {
                    "interpreterPath": str(interpreter),
                    "rookFullFile": str(rook_file),
                    "goalFile": str(goal_file),
                    "callables": callables,
                },
            )
        raise AssertionError(expected_command)

    @staticmethod
    def _response(command: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": command["id"],
            "type": "response",
            "command": command["type"],
            "success": True,
            "data": data,
        }

    async def retire(self, grace_seconds: float) -> None:
        self.retired = True


class RuntimeFactory:
    def __init__(
        self,
        root: Path,
        registry: PrimeConversationRegistry,
        *,
        scenario: str = "complete",
    ) -> None:
        self.root = root
        self.registry = registry
        self.scenario = scenario
        self.created: list[FakeRuntimeProcess] = []

    def for_conversation(self, conversation_id: str):
        def create(
            generation: int,
            model: PrimeModelSelection,
            resume_session_path: str | None,
            binding,
            locked_target: TargetFingerprintV2,
        ) -> FakeRuntimeProcess:
            process = FakeRuntimeProcess(
                self.root,
                generation,
                model,
                resume_session_path,
                binding,
                locked_target,
                self.registry,
                conversation_id,
                self.scenario,
            )
            self.created.append(process)
            return process

        return create


def _unexpected_v1_factory(*_args):
    raise AssertionError("v1 process factory was used for a v2 conversation")


async def _backend(
    tmp_path: Path,
    registry: PrimeConversationRegistry,
    factory: RuntimeFactory,
    conversation_id: str,
) -> prime_backend.PrimeChatBackend:
    return prime_backend.PrimeChatBackend(
        registry=registry,
        process_factory=_unexpected_v1_factory,
        default_model=MODEL,
        runtime_process_factory=factory.for_conversation(conversation_id),
        retirement_grace_seconds=0.01,
    )


async def test_first_use_persists_pending_then_prepares_before_prompt_admission(
    tmp_path: Path,
) -> None:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    binding = runtime_binding(tmp_path)
    assert not binding.kernel_root.exists()
    factory = RuntimeFactory(tmp_path / "sessions", registry)
    backend = await _backend(tmp_path, registry, factory, "conv_runtime")
    try:
        record = await backend.create_v2("conv_runtime", target(), binding)

        assert isinstance(record, PrimeConversationRecordV2)
        assert record.runtime.preparation.status == "prepared"
        assert record.runtime.contract_fingerprint_sha256 == binding.contract.fingerprint
        assert record.runtime.capability_profile == "readonly"
        assert record.target == target()
        process = factory.created[0]
        assert process.pending_seen_before_prepare is True
        assert [command["type"] for command in process.commands] == [
            "set_rlm_max_depth",
            "get_rlm_max_depth_status",
            "prepare_ipython_runtime",
        ]
        assert process.commands[0] == {
            "type": "set_rlm_max_depth",
            "maxDepth": 0,
            "global": False,
        }
        assert process.command_timeouts == [
            ("set_rlm_max_depth", 10.0),
            ("get_rlm_max_depth_status", 10.0),
            (
                "prepare_ipython_runtime",
                prime_backend.RUNTIME_PREPARATION_TIMEOUT_SECONDS,
            ),
        ]
        assert prime_backend.RUNTIME_PREPARATION_TIMEOUT_SECONDS == 150.0
    finally:
        await backend.shutdown()
        registry.close()


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("set_rlm_max_depth_timeout", "runtime_contract_unavailable"),
        ("wrong_depth", "runtime_contract_unavailable"),
        ("prepare_ipython_runtime_timeout", "runtime_contract_unavailable"),
        ("prepare_failure", "runtime_contract_unavailable"),
        ("partial_environment", "runtime_contract_unavailable"),
        ("process_loss", "runtime_contract_unavailable"),
        ("wrong_interpreter", "runtime_contract_unavailable"),
        ("wrong_rook_import", "runtime_contract_unavailable"),
        ("wrong_goal_import", "runtime_contract_unavailable"),
        ("wrong_callables", "runtime_contract_unavailable"),
    ],
)
async def test_first_use_failure_is_terminal_retired_and_never_replayed(
    tmp_path: Path,
    scenario: str,
    expected_code: str,
) -> None:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    binding = runtime_binding(tmp_path)
    factory = RuntimeFactory(tmp_path / "sessions", registry, scenario=scenario)
    backend = await _backend(tmp_path, registry, factory, "conv_failure")
    try:
        with pytest.raises(prime_backend.PrimeBackendError) as caught:
            await backend.create_v2("conv_failure", target(), binding)

        assert caught.value.code == expected_code
        assert len(factory.created) == 1
        assert factory.created[0].retired is True
        failed = registry.load("conv_failure")
        assert isinstance(failed, PrimeConversationRecordV2)
        assert failed.runtime.preparation.status == "pending"
        assert failed.last_lifecycle.state == "failed"
        assert failed.last_lifecycle.reason == "runtime_contract_unavailable"
        if scenario == "prepare_ipython_runtime_timeout":
            assert factory.created[0].command_timeouts[-1] == (
                "prepare_ipython_runtime",
                prime_backend.RUNTIME_PREPARATION_TIMEOUT_SECONDS,
            )
    finally:
        await backend.shutdown()
        registry.close()


async def test_reopen_verifies_existing_environment_without_repairing_depth(
    tmp_path: Path,
) -> None:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    binding = runtime_binding(tmp_path)
    first_factory = RuntimeFactory(tmp_path / "sessions", registry)
    first_backend = await _backend(tmp_path, registry, first_factory, "conv_reopen")
    await first_backend.create_v2("conv_reopen", target(), binding)
    await first_backend.shutdown()

    reopen_factory = RuntimeFactory(tmp_path / "sessions", registry)
    reopened_backend = await _backend(tmp_path, registry, reopen_factory, "conv_reopen")
    try:
        reopened = await reopened_backend.reopen_v2("conv_reopen", target(), binding)

        assert reopened.runtime.preparation.status == "prepared"
        assert len(reopen_factory.created) == 1
        assert [command["type"] for command in reopen_factory.created[0].commands] == [
            "get_rlm_max_depth_status",
            "prepare_ipython_runtime",
        ]
    finally:
        await reopened_backend.shutdown()
        registry.close()


async def test_reopen_missing_environment_refuses_before_process_creation(
    tmp_path: Path,
) -> None:
    registry = PrimeConversationRegistry(tmp_path / "registry", PID, START_TICKS)
    binding = runtime_binding(tmp_path)
    first_factory = RuntimeFactory(tmp_path / "sessions", registry)
    first_backend = await _backend(tmp_path, registry, first_factory, "conv_missing")
    await first_backend.create_v2("conv_missing", target(), binding)
    await first_backend.shutdown()
    shutil.rmtree(binding.contract.kernel_environment_path)

    reopen_factory = RuntimeFactory(tmp_path / "sessions", registry)
    reopened_backend = await _backend(tmp_path, registry, reopen_factory, "conv_missing")
    try:
        with pytest.raises(prime_backend.PrimeBackendError) as caught:
            await reopened_backend.reopen_v2("conv_missing", target(), binding)

        assert caught.value.code == "runtime_contract_unavailable"
        assert reopen_factory.created == []
    finally:
        await reopened_backend.shutdown()
        registry.close()
