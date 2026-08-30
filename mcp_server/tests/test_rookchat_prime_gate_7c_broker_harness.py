from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rook.agent.chat.prime_process import (
    OwnedCleanupResult,
    PrimeRpcProcess,
    PrimeRuntimeState,
)
from rook.agent.chat.prime_registry import PrimeModelSelection, TargetFingerprintV2
from rook.agent.chat.prime_runtime_contract import (
    write_package_manifest,
    write_prime_bundle_manifest,
)
from scripts import rookchat_prime_gate_7c_broker_harness as gate7c


pytestmark = pytest.mark.asyncio


def _skill(root: Path, package: str, *, manifest: bool) -> None:
    (root / "src" / package).mkdir(parents=True)
    (root / "SKILL.md").write_text(f"# {package}\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='fixture'\nversion='0.0.0'\n",
        encoding="utf-8",
    )
    (root / "src" / package / "__init__.py").write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )
    if manifest:
        write_package_manifest(root)


def configuration(tmp_path: Path) -> gate7c.Gate7CConfiguration:
    node = tmp_path / "node.exe"
    uv = tmp_path / "uv.exe"
    node.write_bytes(b"node")
    uv.write_bytes(b"uv")
    dist = tmp_path / "dist"
    (dist / "bundle").mkdir(parents=True)
    (dist / "skills" / "goal").mkdir(parents=True)
    (dist / "bundle" / "cli.js").write_text("// cli", encoding="utf-8")
    (dist / "skills" / "goal" / "SKILL.md").write_text(
        "goal", encoding="utf-8"
    )
    bundle_manifest = tmp_path / "prime-bundle-manifest.json"
    bundle = write_prime_bundle_manifest(dist, bundle_manifest)
    goal = tmp_path / "goal"
    rook = tmp_path / "rook-full"
    _skill(goal, "goal", manifest=False)
    _skill(rook, "rook_full", manifest=True)
    roots = {
        name: tmp_path / name
        for name in (
            "product",
            "kernels",
            "registry",
            "sessions",
            "agent",
        )
    }
    return gate7c.Gate7CConfiguration(
        node_path=node.absolute(),
        node_sha256=gate7c._sha256_file(node),
        prime_dist_root=dist.absolute(),
        prime_bundle_manifest_path=bundle_manifest.absolute(),
        prime_bundle_manifest_sha256=bundle.manifest_sha256,
        prime_git_commit="fixture-prime",
        goal_skill_root=goal.absolute(),
        rook_package_source_root=rook.absolute(),
        product_root=roots["product"].absolute(),
        kernel_root=roots["kernels"].absolute(),
        registry_root=roots["registry"].absolute(),
        session_dir=roots["sessions"].absolute(),
        agent_root=roots["agent"].absolute(),
        uv_path=uv.absolute(),
        uv_sha256=gate7c._sha256_file(uv),
        result_path=(tmp_path / "result.json").absolute(),
        model=PrimeModelSelection("fixture", "model", None),
        capability_profile="readonly",
        target=TargetFingerprintV2(
            1234,
            "638918000000000000",
            42,
            "01234567-89ab-cdef-0123-456789abcdef",
        ),
        conversation_id="conv_0123456789abcdef0123456789abcdef",
        base_environment={"SystemRoot": "C:/Windows", "OPENAI_API_KEY": "no"},
    )


class FakePrimeProcess:
    instances: list["FakePrimeProcess"] = []
    fail_prepare = False

    def __init__(self, **kwargs: Any) -> None:
        self.inner = PrimeRpcProcess(**kwargs)
        self.generation = self.inner.generation
        self.session_dir = Path(kwargs["session_dir"])
        self.runtime_launch = kwargs["runtime_launch"]
        self.provider = kwargs["provider"]
        self.model_id = kwargs["model_id"]
        self.thinking = kwargs["thinking"]
        self._command_types: list[str] = []
        self._cleanup_result: OwnedCleanupResult | None = None
        type(self).instances.append(self)

    @property
    def argv(self) -> list[str]:
        return self.inner.argv

    @property
    def launch_environment(self) -> dict[str, str]:
        return self.inner.launch_environment

    @property
    def command_types(self) -> tuple[str, ...]:
        return tuple(self._command_types)

    @property
    def cleanup_result(self) -> OwnedCleanupResult | None:
        return self._cleanup_result

    async def start(self) -> PrimeRuntimeState:
        self._command_types.append("get_state")
        path = (self.session_dir / "session.jsonl").absolute()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return PrimeRuntimeState(
            "session",
            str(path),
            self.provider,
            self.model_id,
            self.thinking,
        )

    def subscribe(self, _listener):
        return lambda: None

    async def command(
        self,
        command: dict[str, Any],
        *,
        expected_command: str,
        timeout_seconds: float | None = 10.0,
    ) -> dict[str, Any]:
        self._command_types.append(expected_command)
        if expected_command == "prepare_ipython_runtime" and self.fail_prepare:
            return {
                "id": "fake",
                "type": "response",
                "command": expected_command,
                "success": False,
                "error": "fixture failure",
            }
        if expected_command in {"set_rlm_max_depth", "get_rlm_max_depth_status"}:
            data = {"maxDepth": 0, "source": "chat"}
        elif expected_command == "prepare_ipython_runtime":
            environment = Path(
                self.launch_environment["PRIME_AGENT_KERNEL_VENV"]
            )
            interpreter = environment / "Scripts" / "python.exe"
            interpreter.parent.mkdir(parents=True, exist_ok=True)
            interpreter.touch()
            data = {
                "interpreterPath": str(interpreter),
                "rookFullFile": str(
                    self.runtime_launch.rook_skill_path.parent
                    / "src"
                    / "rook_full"
                    / "__init__.py"
                ),
                "goalFile": str(
                    self.runtime_launch.goal_skill_path.parent
                    / "src"
                    / "goal"
                    / "__init__.py"
                ),
                "callables": {"search": True, "read": True, "call": True},
            }
        else:
            raise AssertionError(expected_command)
        return {
            "id": "fake",
            "type": "response",
            "command": expected_command,
            "success": True,
            "data": data,
        }

    async def retire(self, _grace_seconds: float) -> None:
        self._cleanup_result = OwnedCleanupResult(
            True,
            False,
            "Prime direct child exited gracefully",
        )


async def test_gate_7c_runs_one_broker_generation_without_prompt_or_retry(
    tmp_path: Path,
) -> None:
    FakePrimeProcess.instances = []
    FakePrimeProcess.fail_prepare = False
    config = configuration(tmp_path)

    result = await gate7c.run_gate_7c(config, process_class=FakePrimeProcess)

    assert result["status"] == "passed"
    assert len(FakePrimeProcess.instances) == 1
    process = FakePrimeProcess.instances[0]
    assert process.command_types == (
        "get_state",
        "set_rlm_max_depth",
        "get_rlm_max_depth_status",
        "prepare_ipython_runtime",
    )
    assert "prompt_and_wait" not in process.command_types
    assert process.launch_environment["ROOK_MCP_TOOL_PROFILE"] == "readonly"
    assert process.launch_environment["ROOK_MCP_TARGET_PROCESS_ID"] == "1234"
    assert "OPENAI_API_KEY" not in process.launch_environment
    assert json.loads(config.result_path.read_text(encoding="ascii")) == result


async def test_gate_7c_failure_is_absorbing_and_retains_one_failed_result(
    tmp_path: Path,
) -> None:
    FakePrimeProcess.instances = []
    FakePrimeProcess.fail_prepare = True
    config = configuration(tmp_path)

    with pytest.raises(gate7c.Gate7CFailure, match="runtime_contract_unavailable"):
        await gate7c.run_gate_7c(config, process_class=FakePrimeProcess)

    assert len(FakePrimeProcess.instances) == 1
    assert FakePrimeProcess.instances[0].cleanup_result is not None
    retained = json.loads(config.result_path.read_text(encoding="ascii"))
    assert retained["status"] == "failed"
    assert retained["preparedRecord"] is None


async def test_gate_7c_rechecks_node_hash_at_process_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakePrimeProcess.instances = []
    FakePrimeProcess.fail_prepare = False
    config = configuration(tmp_path)
    stage = gate7c.stage_product_package

    def stage_then_drift(*args, **kwargs):
        package = stage(*args, **kwargs)
        config.node_path.write_bytes(b"changed after admission")
        return package

    monkeypatch.setattr(gate7c, "stage_product_package", stage_then_drift)

    with pytest.raises(gate7c.Gate7CFailure, match="Node executable differs"):
        await gate7c.run_gate_7c(config, process_class=FakePrimeProcess)

    assert FakePrimeProcess.instances == []
    retained = json.loads(config.result_path.read_text(encoding="ascii"))
    assert retained["status"] == "failed"
    assert retained["processes"] == []
