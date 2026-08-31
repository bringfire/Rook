"""Absorbing admission wrapper for the reviewed Gate 7C broker harness."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


ROOK_ROOT = Path("C:/UDEV/Rook/.worktrees/task7-runtime-topology-recovery")
PRIME_ROOT = Path("D:/prime-agent/.worktrees/task7-runtime-topology-recovery")
APPROVED_PRIME_COMMIT = "46dbf2749d64446820fbf31e52d8766e5ee87be9"
HARNESS_PATH = ROOK_ROOT / "scripts/rookchat_prime_gate_7c_broker_harness.py"
HARNESS_SHA256 = "2A74120496C0B65AE4A9FBDDFAD056D65F7976B2E597500ADF8AF7F8F7E920EA"
CONFIGURATION_PATH = (
    ROOK_ROOT
    / "docs/superpowers/experiments/inputs/"
    "2026-08-30-rookchat-prime-gate-7c-broker-v1/config.json"
)
CONFIGURATION_SHA256 = "7AFBFCA08C970C0B87CF05717886A63F45D069FFF104694648A8166FF22B3BE4"
ADMITTED_ENVIRONMENT_KEYS = {
    "APPDATA",
    "COMSPEC",
    "LOCALAPPDATA",
    "PATHEXT",
    "PROGRAMDATA",
    "SystemRoot",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}
HOST_MODULE_PATHS = {
    "rook": Path("rook/__init__.py"),
    "rook.agent.chat.prime_backend": Path("rook/agent/chat/prime_backend.py"),
    "rook.agent.chat.prime_process": Path("rook/agent/chat/prime_process.py"),
}


class Gate7CAdmissionFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class Gate7CAdmission:
    rook_root: Path
    prime_root: Path
    approved_rook_commit: str
    approved_prime_commit: str
    wrapper_path: Path
    harness_path: Path
    harness_sha256: str
    configuration_path: Path
    configuration_sha256: str


@dataclass(frozen=True)
class FrozenGate7CConfiguration:
    evidence_root: Path
    approved_prime_commit: str
    host_python_interpreter: Path
    source_root: Path
    admitted_environment: Mapping[str, str]
    harness_arguments: tuple[str, ...]

    @property
    def result_path(self) -> Path:
        return self.evidence_root / "result.json"

    @property
    def admission_path(self) -> Path:
        return self.evidence_root / "admission.json"


@dataclass(frozen=True)
class HostRuntimeCustody:
    interpreter_path: str
    source_root: str
    isolated: bool
    module_origins: Mapping[str, str]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def inspect_repository(root: Path) -> tuple[str, str]:
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()
    status = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout
    return head, status


def _load_harness(path: Path) -> ModuleType:
    module_name = "reviewed_gate_7c_harness"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise Gate7CAdmissionFailure("unable to load reviewed Gate 7C harness")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
        raise
    return module


def invoke_harness(path: Path, arguments: Sequence[str]) -> int:
    module = _load_harness(path)
    main = getattr(module, "main", None)
    if not callable(main):
        raise Gate7CAdmissionFailure("reviewed Gate 7C harness has no main entry")
    return int(main(list(arguments)))


def _object(value: object, keys: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        raise Gate7CAdmissionFailure(f"frozen {label} has an invalid shape")
    return value


def _string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise Gate7CAdmissionFailure(f"frozen {label} must be a nonempty string")
    return value


def _integer(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise Gate7CAdmissionFailure(f"frozen {label} must be a positive integer")
    return value


def _path(value: object, label: str) -> Path:
    path = Path(_string(value, label))
    if not path.is_absolute():
        raise Gate7CAdmissionFailure(f"frozen {label} must be absolute")
    return path


def _digest(value: object, label: str) -> str:
    digest = _string(value, label)
    if not re.fullmatch(r"[0-9A-F]{64}", digest):
        raise Gate7CAdmissionFailure(f"frozen {label} must be canonical SHA-256")
    return digest


def _environment(value: object) -> dict[str, str]:
    environment = _object(value, ADMITTED_ENVIRONMENT_KEYS, "admitted environment")
    return {
        name: _string(environment[name], f"admitted environment {name}")
        for name in sorted(ADMITTED_ENVIRONMENT_KEYS)
    }


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decode_configuration(path: Path) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        text = raw.decode("ascii")
        parsed = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Gate7CAdmissionFailure("frozen Gate 7C configuration is unreadable") from error
    canonical = json.dumps(
        parsed,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    if raw not in {canonical, canonical + b"\n"}:
        raise Gate7CAdmissionFailure("frozen Gate 7C configuration is not canonical")
    return _object(
        parsed,
        {
            "schemaVersion",
            "evidenceRoot",
            "hostPython",
            "admittedEnvironment",
            "node",
            "prime",
            "rookPackageRoot",
            "runtime",
            "uv",
            "model",
            "capabilityProfile",
            "target",
            "conversationId",
        },
        "configuration",
    )


def load_frozen_configuration(path: Path) -> FrozenGate7CConfiguration:
    payload = _decode_configuration(path)
    if payload["schemaVersion"] != 1:
        raise Gate7CAdmissionFailure("unsupported frozen Gate 7C configuration")
    evidence_root = _path(payload["evidenceRoot"], "evidence root")
    host_python = _object(
        payload["hostPython"],
        {"interpreterPath", "sourceRoot"},
        "host Python",
    )
    host_python_interpreter = _path(
        host_python["interpreterPath"],
        "host Python interpreter",
    )
    source_root = _path(host_python["sourceRoot"], "Rook source root")
    admitted_environment = _environment(payload["admittedEnvironment"])
    node = _object(payload["node"], {"path", "sha256"}, "Node identity")
    prime = _object(
        payload["prime"],
        {
            "distRoot",
            "bundleManifestPath",
            "bundleManifestSha256",
            "commit",
            "goalSkillRoot",
        },
        "Prime identity",
    )
    runtime = _object(
        payload["runtime"],
        {
            "productRoot",
            "kernelRoot",
            "registryRoot",
            "sessionDirectory",
            "agentRoot",
        },
        "runtime roots",
    )
    uv = _object(payload["uv"], {"path", "sha256"}, "uv identity")
    model = _object(payload["model"], {"provider", "id", "thinking"}, "model")
    target = _object(
        payload["target"],
        {
            "rhinoPid",
            "processStartUtcTicks",
            "documentRuntimeSerial",
            "grasshopperDocumentId",
        },
        "target",
    )
    profile = _string(payload["capabilityProfile"], "capability profile")
    if profile not in {"readonly", "full"}:
        raise Gate7CAdmissionFailure("frozen capability profile is unsupported")
    ticks = _string(target["processStartUtcTicks"], "process start ticks")
    if not ticks.isdecimal() or ticks.startswith("0"):
        raise Gate7CAdmissionFailure("frozen process start ticks are not canonical")
    gh_document_id = _string(target["grasshopperDocumentId"], "GH document ID")
    if not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        gh_document_id,
    ):
        raise Gate7CAdmissionFailure("frozen GH document ID is not canonical")
    conversation_id = _string(payload["conversationId"], "conversation ID")
    if not re.fullmatch(r"conv_[0-9a-f]{32}", conversation_id):
        raise Gate7CAdmissionFailure("frozen conversation ID is not canonical")
    thinking = model["thinking"]
    if thinking is not None and type(thinking) is not str:
        raise Gate7CAdmissionFailure("frozen thinking level is invalid")

    result_path = evidence_root / "result.json"
    arguments = [
        "--node-path",
        str(_path(node["path"], "Node path")),
        "--node-sha256",
        _digest(node["sha256"], "Node SHA-256"),
        "--prime-dist-root",
        str(_path(prime["distRoot"], "Prime dist root")),
        "--prime-bundle-manifest",
        str(_path(prime["bundleManifestPath"], "Prime bundle manifest")),
        "--prime-bundle-sha256",
        _digest(prime["bundleManifestSha256"], "Prime bundle SHA-256"),
        "--prime-commit",
        _string(prime["commit"], "Prime commit"),
        "--goal-skill-root",
        str(_path(prime["goalSkillRoot"], "goal skill root")),
        "--rook-package-root",
        str(_path(payload["rookPackageRoot"], "Rook package root")),
        "--product-root",
        str(_path(runtime["productRoot"], "product root")),
        "--kernel-root",
        str(_path(runtime["kernelRoot"], "kernel root")),
        "--registry-root",
        str(_path(runtime["registryRoot"], "registry root")),
        "--session-dir",
        str(_path(runtime["sessionDirectory"], "session directory")),
        "--agent-root",
        str(_path(runtime["agentRoot"], "agent root")),
        "--uv-path",
        str(_path(uv["path"], "uv path")),
        "--uv-sha256",
        _digest(uv["sha256"], "uv SHA-256"),
        "--base-environment-json",
        _canonical_json(admitted_environment),
        "--result",
        str(result_path),
        "--provider",
        _string(model["provider"], "model provider"),
        "--model",
        _string(model["id"], "model ID"),
    ]
    if thinking is not None:
        arguments.extend(("--thinking", thinking))
    arguments.extend(
        (
            "--profile",
            profile,
            "--rhino-pid",
            str(_integer(target["rhinoPid"], "Rhino PID")),
            "--process-start-ticks",
            ticks,
            "--document-serial",
            str(_integer(target["documentRuntimeSerial"], "document serial")),
            "--grasshopper-document-id",
            gh_document_id,
            "--conversation-id",
            conversation_id,
        )
    )
    return FrozenGate7CConfiguration(
        evidence_root=evidence_root,
        approved_prime_commit=_string(prime["commit"], "Prime commit"),
        host_python_interpreter=host_python_interpreter,
        source_root=source_root,
        admitted_environment=admitted_environment,
        harness_arguments=tuple(arguments),
    )


def verify_host_runtime(
    config: FrozenGate7CConfiguration,
    *,
    executable: str | Path | None = None,
    isolated: bool | None = None,
    environment: Mapping[str, str] | None = None,
    module_loader: Callable[[str], Any] = importlib.import_module,
) -> HostRuntimeCustody:
    effective_environment = os.environ if environment is None else environment
    overrides = sorted(
        name
        for name in effective_environment
        if name.upper() in {"PYTHONHOME", "PYTHONPATH"}
    )
    if overrides:
        raise Gate7CAdmissionFailure(
            f"host Python override is not admitted: {', '.join(overrides)}"
        )
    effective_isolated = bool(sys.flags.isolated) if isolated is None else isolated
    if not effective_isolated:
        raise Gate7CAdmissionFailure("Gate 7C wrapper requires Python isolated mode")
    try:
        expected_interpreter = config.host_python_interpreter.resolve(strict=True)
        actual_interpreter = Path(executable or sys.executable).resolve(strict=True)
        source_root = config.source_root.resolve(strict=True)
    except OSError as error:
        raise Gate7CAdmissionFailure("host Python custody path is unavailable") from error
    if actual_interpreter != expected_interpreter:
        raise Gate7CAdmissionFailure("host Python interpreter differs from review")

    origins: dict[str, str] = {}
    for module_name, relative_path in HOST_MODULE_PATHS.items():
        module = module_loader(module_name)
        raw_origin = getattr(module, "__file__", None)
        if type(raw_origin) is not str or not raw_origin:
            raise Gate7CAdmissionFailure(
                f"host module import origin is missing: {module_name}"
            )
        try:
            origin = Path(raw_origin).resolve(strict=True)
            expected = (source_root / relative_path).resolve(strict=True)
        except OSError as error:
            raise Gate7CAdmissionFailure(
                f"host module import origin is unavailable: {module_name}"
            ) from error
        if origin != expected:
            raise Gate7CAdmissionFailure(
                f"host module import origin differs from review: {module_name}"
            )
        origins[module_name] = str(origin)

    return HostRuntimeCustody(
        interpreter_path=str(actual_interpreter),
        source_root=str(source_root),
        isolated=True,
        module_origins=origins,
    )


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    raw = json.dumps(
        payload,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    pending = path.parent / f".{path.name}.{uuid.uuid4().hex}.pending"
    try:
        with pending.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def execute_gate_7c(
    admission: Gate7CAdmission,
    *,
    repository_inspector: Callable[[Path], tuple[str, str]] = inspect_repository,
    file_hasher: Callable[[Path], str] = _sha256_file,
    harness_invoker: Callable[[Path, Sequence[str]], int] = invoke_harness,
    host_runtime_verifier: Callable[
        [FrozenGate7CConfiguration], HostRuntimeCustody
    ] = verify_host_runtime,
    utc_now: Callable[[], str] = _utc_now,
) -> dict[str, object]:
    for path, expected, label in (
        (
            admission.configuration_path,
            admission.configuration_sha256,
            "Gate 7C configuration",
        ),
        (admission.harness_path, admission.harness_sha256, "Gate 7C harness"),
    ):
        if not path.is_file():
            raise Gate7CAdmissionFailure(f"{label} is missing")
        if file_hasher(path) != expected:
            raise Gate7CAdmissionFailure(f"{label} differs from review")

    config = load_frozen_configuration(admission.configuration_path)
    if config.approved_prime_commit != admission.approved_prime_commit:
        raise Gate7CAdmissionFailure("frozen Prime commit differs from review")
    expected_interpreter = (
        admission.rook_root
        / "mcp_server"
        / ".venv"
        / "Scripts"
        / "python.exe"
    ).absolute()
    expected_source_root = (
        admission.rook_root / "mcp_server" / "src"
    ).absolute()
    if config.host_python_interpreter.absolute() != expected_interpreter:
        raise Gate7CAdmissionFailure("frozen host Python is outside the Rook worktree")
    if config.source_root.absolute() != expected_source_root:
        raise Gate7CAdmissionFailure("frozen Rook source root differs from review")
    if config.evidence_root.exists():
        raise Gate7CAdmissionFailure("Gate 7C evidence root already exists")
    for root, expected, label in (
        (admission.rook_root, admission.approved_rook_commit, "Rook"),
        (admission.prime_root, admission.approved_prime_commit, "Prime"),
    ):
        head, status = repository_inspector(root)
        if head != expected:
            raise Gate7CAdmissionFailure(f"{label} HEAD differs from review")
        if status:
            raise Gate7CAdmissionFailure(f"{label} worktree is dirty")

    host_runtime = host_runtime_verifier(config)
    admitted_environment = dict(config.admitted_environment)
    admitted_environment_sha256 = hashlib.sha256(
        _canonical_json(admitted_environment).encode("ascii")
    ).hexdigest().upper()
    wrapper_sha256 = file_hasher(admission.wrapper_path)
    config.evidence_root.mkdir(parents=True, exist_ok=False)
    record: dict[str, Any] = {
        "schemaVersion": 1,
        "wrapperSha256": wrapper_sha256,
        "harnessSha256": admission.harness_sha256,
        "configurationSha256": admission.configuration_sha256,
        "admittedEnvironment": admitted_environment,
        "admittedEnvironmentSha256": admitted_environment_sha256,
        "approvedCommits": {
            "rook": admission.approved_rook_commit,
            "prime": admission.approved_prime_commit,
        },
        "constructedInvocation": {
            "pythonExecutable": str(Path(sys.executable).resolve()),
            "wrapperPath": str(admission.wrapper_path),
            "harnessPath": str(admission.harness_path),
            "arguments": list(config.harness_arguments),
        },
        "hostRuntime": {
            "interpreterPath": host_runtime.interpreter_path,
            "sourceRoot": host_runtime.source_root,
            "isolated": host_runtime.isolated,
            "moduleOrigins": dict(host_runtime.module_origins),
        },
        "startedAtUtc": utc_now(),
        "endedAtUtc": None,
        "outcome": "running",
        "wrapperExitCode": None,
        "harnessExitCode": None,
        "resultPath": str(config.result_path),
        "resultSha256": None,
        "failure": None,
    }
    _write_json_atomic(config.admission_path, record)

    harness_exit_code: int | None = None
    try:
        harness_exit_code = harness_invoker(
            admission.harness_path,
            config.harness_arguments,
        )
        if harness_exit_code != 0:
            raise Gate7CAdmissionFailure(
                f"Gate 7C harness failed with exit code {harness_exit_code}; do not retry"
            )
        if not config.result_path.is_file():
            raise Gate7CAdmissionFailure("Gate 7C harness returned without a result")
        try:
            payload = json.loads(config.result_path.read_text(encoding="ascii"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise Gate7CAdmissionFailure("Gate 7C result is unreadable") from error
        if not isinstance(payload, dict) or payload.get("status") != "passed":
            raise Gate7CAdmissionFailure("Gate 7C result did not pass")
    except BaseException as error:
        record.update(
            {
                "endedAtUtc": utc_now(),
                "outcome": "failed",
                "wrapperExitCode": 1,
                "harnessExitCode": harness_exit_code,
                "resultSha256": (
                    file_hasher(config.result_path)
                    if config.result_path.is_file()
                    else None
                ),
                "failure": str(error),
            }
        )
        _write_json_atomic(config.admission_path, record)
        raise

    record.update(
        {
            "endedAtUtc": utc_now(),
            "outcome": "passed",
            "wrapperExitCode": 0,
            "harnessExitCode": harness_exit_code,
            "resultSha256": file_hasher(config.result_path),
        }
    )
    _write_json_atomic(config.admission_path, record)
    return payload


def production_admission(approved_rook_commit: str) -> Gate7CAdmission:
    return Gate7CAdmission(
        rook_root=ROOK_ROOT,
        prime_root=PRIME_ROOT,
        approved_rook_commit=approved_rook_commit,
        approved_prime_commit=APPROVED_PRIME_COMMIT,
        wrapper_path=Path(__file__).resolve(),
        harness_path=HARNESS_PATH,
        harness_sha256=HARNESS_SHA256,
        configuration_path=CONFIGURATION_PATH,
        configuration_sha256=CONFIGURATION_SHA256,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-rook-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    admission = production_admission(namespace.approved_rook_commit)
    try:
        execute_gate_7c(admission)
    except Exception as error:
        print(f"Gate 7C admission failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
