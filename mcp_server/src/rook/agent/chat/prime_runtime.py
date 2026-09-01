"""Verify and launch one immutable Prime ACP runtime contract."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path, PurePosixPath
from typing import Protocol

from acp import PROTOCOL_VERSION
from acp.schema import EnvVariable, McpServerStdio

from .acp_storage import RookBinding


MAX_ROOT_SKILL_UTF8_BYTES = 16 * 1024
MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS = 30_000
RUNTIME_SCHEMA_VERSION = 1
SUPPORTED_REASONING = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
_RUNTIME_ID = re.compile(r"^[A-F0-9]{64}$")


class RuntimeUnavailable(RuntimeError):
    code = "runtime_unavailable"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


class PrimeLaunchError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PrimeRuntimeContract:
    schema_version: int
    runtime_id: str
    platform: str
    architecture: str
    upstream_commit: str
    compatibility_patch_commit: str | None
    manifest_sha256: str
    acp_protocol_version: int
    python_acp_sdk_version: str
    executable_path: Path
    goal_skill_path: Path
    rook_skill_path: Path
    rook_skill_manifest_sha256: str
    rook_skill_system_prompt: str
    rook_mcp_command: Path
    rook_mcp_args: tuple[str, ...]
    rook_mcp_environment: tuple[tuple[str, str], ...]
    claim_key_version: int


class RuntimeCatalog(Protocol):
    def latest(self) -> PrimeRuntimeContract: ...

    def get(self, runtime_id: str) -> PrimeRuntimeContract: ...


def _canonical_json(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _subtree_manifest_sha256(retained: Mapping[str, bytes], prefix: str) -> str:
    rows = [
        {
            "path": relative.removeprefix(prefix),
            "bytes": len(payload),
            "sha256": _sha256(payload),
        }
        for relative, payload in sorted(retained.items())
        if relative.startswith(prefix)
    ]
    return _sha256(_canonical_json({"files": rows}))


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        attributes = os.lstat(path).st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RuntimeUnavailable("manifest path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RuntimeUnavailable("manifest path is invalid")
    normalized = path.as_posix()
    if normalized != value:
        raise RuntimeUnavailable("manifest path is not canonical")
    return normalized


def _under_root(root: Path, relative: str) -> Path:
    candidate = (root / Path(*PurePosixPath(relative).parts)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeUnavailable("manifest path escapes runtime root") from exc
    return candidate


def _require_scalar(payload: Mapping[str, object], key: str, expected: type):
    value = payload.get(key)
    if type(value) is not expected or (expected is str and not value.strip()):
        raise RuntimeUnavailable(f"runtime field {key} is invalid")
    return value


def _require_runtime_path(root: Path, relative: object, *, directory: bool) -> Path:
    safe = _safe_relative_path(relative)
    target = _under_root(root, safe)
    if _is_reparse_or_symlink(target):
        raise RuntimeUnavailable("runtime path is a symlink or reparse point")
    if directory:
        if not target.is_dir():
            raise RuntimeUnavailable("required runtime directory is missing")
    else:
        try:
            mode = os.lstat(target).st_mode
        except OSError as exc:
            raise RuntimeUnavailable("required runtime file is missing") from exc
        if not stat.S_ISREG(mode):
            raise RuntimeUnavailable("required runtime path is not a regular file")
    return target


def _verify_manifest(root: Path, manifest: Mapping[str, object]) -> dict[str, bytes]:
    listed = manifest.get("files")
    if not isinstance(listed, list):
        raise RuntimeUnavailable("manifest file list is invalid")
    expected: dict[str, tuple[int, str]] = {}
    previous: str | None = None
    for row in listed:
        if not isinstance(row, dict):
            raise RuntimeUnavailable("manifest entry is invalid")
        relative = _safe_relative_path(row.get("path"))
        byte_count = row.get("bytes")
        digest = row.get("sha256")
        if (
            previous is not None
            and relative <= previous
            or not isinstance(byte_count, int)
            or byte_count < 0
            or not isinstance(digest, str)
            or not _RUNTIME_ID.fullmatch(digest)
        ):
            raise RuntimeUnavailable("manifest entry is not canonical")
        previous = relative
        expected[relative] = (byte_count, digest)

    actual_paths: list[str] = []
    for candidate in root.rglob("*"):
        if _is_reparse_or_symlink(candidate):
            raise RuntimeUnavailable("runtime contains a symlink or reparse point")
        if candidate.is_dir():
            continue
        try:
            mode = os.lstat(candidate).st_mode
        except OSError as exc:
            raise RuntimeUnavailable("runtime file cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise RuntimeUnavailable("runtime contains a non-regular file")
        relative = candidate.relative_to(root).as_posix()
        if relative != "runtime-manifest.json":
            actual_paths.append(relative)
    if sorted(actual_paths) != list(expected):
        raise RuntimeUnavailable("manifest file set differs from runtime")

    retained: dict[str, bytes] = {}
    for relative, (byte_count, digest) in expected.items():
        target = _under_root(root, relative)
        payload = target.read_bytes()
        if len(payload) != byte_count or _sha256(payload) != digest:
            raise RuntimeUnavailable(f"manifest mismatch for {relative}")
        retained[relative] = payload
    return retained


def load_and_verify_runtime(install_root: Path, runtime_id: str) -> PrimeRuntimeContract:
    if not isinstance(runtime_id, str) or not _RUNTIME_ID.fullmatch(runtime_id):
        raise RuntimeUnavailable("runtime_id is invalid")
    root = (install_root / "runtimes" / runtime_id).resolve(strict=False)
    expected_parent = (install_root / "runtimes").resolve(strict=False)
    if root.parent != expected_parent or not root.is_dir() or _is_reparse_or_symlink(root):
        raise RuntimeUnavailable("runtime root is unavailable")
    manifest_path = root / "runtime-manifest.json"
    if _is_reparse_or_symlink(manifest_path):
        raise RuntimeUnavailable("runtime manifest is not a direct file")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8", errors="strict"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeUnavailable("runtime manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest_bytes != _canonical_json(manifest):
        raise RuntimeUnavailable("runtime manifest is not canonical")
    manifest_sha = _sha256(manifest_bytes)
    if manifest_sha != runtime_id:
        raise RuntimeUnavailable("runtime manifest identity differs")
    if manifest.get("schemaVersion") != RUNTIME_SCHEMA_VERSION:
        raise RuntimeUnavailable("runtime schema is unsupported")

    retained = _verify_manifest(root, manifest)
    executable = _require_runtime_path(root, manifest.get("executable"), directory=False)
    goal_skill = _require_runtime_path(root, manifest.get("goalSkill"), directory=True)
    rook_skill = _require_runtime_path(root, manifest.get("rookSkill"), directory=True)
    _require_runtime_path(root, "LICENSE", directory=False)

    platform_name = _require_scalar(manifest, "platform", str)
    architecture = _require_scalar(manifest, "architecture", str)
    if platform_name != platform.system().lower() or architecture != platform.machine().lower():
        raise RuntimeUnavailable("runtime platform or architecture differs from this host")

    goal_root_relative = goal_skill.relative_to(root).as_posix() + "/"
    if f"{goal_root_relative}SKILL.md" not in retained:
        raise RuntimeUnavailable("Prime goal skill is absent from manifest")

    root_relative = (rook_skill / "SKILL.md").relative_to(root).as_posix()
    try:
        skill_bytes = retained[root_relative]
    except KeyError as exc:
        raise RuntimeUnavailable("root Rook skill is absent from manifest") from exc
    if len(skill_bytes) > MAX_ROOT_SKILL_UTF8_BYTES:
        raise RuntimeUnavailable("root_skill_too_large")
    try:
        system_prompt = skill_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeUnavailable("root_skill_invalid_utf8") from exc
    rook_root_relative = rook_skill.relative_to(root).as_posix() + "/"
    expected_rook_manifest = _require_scalar(manifest, "rookSkillManifestSha256", str)
    if not _RUNTIME_ID.fullmatch(expected_rook_manifest) or _subtree_manifest_sha256(
        retained, rook_root_relative
    ) != expected_rook_manifest:
        raise RuntimeUnavailable("Rook skill manifest identity differs")

    acp_version = _require_scalar(manifest, "acpProtocolVersion", int)
    sdk_version = _require_scalar(manifest, "pythonAcpSdkVersion", str)
    if acp_version != PROTOCOL_VERSION or sdk_version != version("agent-client-protocol"):
        raise RuntimeUnavailable("ACP compatibility differs from the installed client")
    command_value = _require_scalar(manifest, "rookMcpCommand", str)
    mcp_command = Path(command_value).expanduser().resolve(strict=False)
    if not Path(command_value).is_absolute() or not mcp_command.is_file():
        raise RuntimeUnavailable("Rook MCP command is unavailable")
    args = manifest.get("rookMcpArgs")
    environment = manifest.get("rookMcpEnvironment")
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        raise RuntimeUnavailable("Rook MCP arguments are invalid")
    if not isinstance(environment, dict) or not all(
        isinstance(key, str) and key and isinstance(value, str) for key, value in environment.items()
    ):
        raise RuntimeUnavailable("Rook MCP environment is invalid")
    claim_version = _require_scalar(manifest, "claimKeyVersion", int)
    if claim_version != 1:
        raise RuntimeUnavailable("claim-key version is unsupported")

    return PrimeRuntimeContract(
        schema_version=RUNTIME_SCHEMA_VERSION,
        runtime_id=runtime_id,
        platform=platform_name,
        architecture=architecture,
        upstream_commit=_require_scalar(manifest, "upstreamCommit", str),
        compatibility_patch_commit=manifest.get("compatibilityPatchCommit")
        if isinstance(manifest.get("compatibilityPatchCommit"), str)
        else None,
        manifest_sha256=manifest_sha,
        acp_protocol_version=acp_version,
        python_acp_sdk_version=sdk_version,
        executable_path=executable,
        goal_skill_path=goal_skill,
        rook_skill_path=rook_skill,
        rook_skill_manifest_sha256=expected_rook_manifest,
        rook_skill_system_prompt=system_prompt,
        rook_mcp_command=mcp_command,
        rook_mcp_args=tuple(args),
        rook_mcp_environment=tuple(sorted(environment.items())),
        claim_key_version=claim_version,
    )


def validate_windows_launch_argv(argv: tuple[str, ...]) -> None:
    rendered = subprocess.list2cmdline(argv)
    units = len(rendered.encode("utf-16-le")) // 2 + 1
    if units > MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS:
        raise PrimeLaunchError("runtime_command_line_too_long")


def build_prime_argv(
    contract: PrimeRuntimeContract,
    session_path: Path,
    requested_model: str | None,
    requested_reasoning: str | None,
    reopen: bool,
) -> tuple[str, ...]:
    if not session_path.is_absolute():
        session_path = session_path.resolve()
    if reopen and (requested_model is not None or requested_reasoning is not None):
        raise PrimeLaunchError("reopen_override_refused")
    if requested_model is not None and (
        requested_model.count("/") != 1 or any(not part.strip() for part in requested_model.split("/"))
    ):
        raise PrimeLaunchError("invalid_model")
    if requested_reasoning is not None and requested_reasoning not in SUPPORTED_REASONING:
        raise PrimeLaunchError("invalid_reasoning")

    values = [
        str(contract.executable_path),
        "--mode",
        "acp",
        "--no-daemon",
        "--no-skills",
        "--skill",
        str(contract.goal_skill_path),
        "--skill",
        str(contract.rook_skill_path),
        "--append-system-prompt",
        contract.rook_skill_system_prompt,
        "--resume",
        str(session_path),
    ]
    if requested_model is not None:
        values.extend(("--model", requested_model))
    if requested_reasoning is not None:
        values.extend(("--thinking", requested_reasoning))
    argv = tuple(values)
    if "--api-key" in argv or "--provider" in argv:
        raise PrimeLaunchError("forbidden_launch_argument")
    validate_windows_launch_argv(argv)
    return argv


def build_prime_child_env(
    base_environment: Mapping[str, str],
    contract: PrimeRuntimeContract,
) -> dict[str, str]:
    del contract
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in base_environment.items()):
        raise PrimeLaunchError("invalid_child_environment")
    return dict(base_environment)


def build_rook_mcp_server(contract: PrimeRuntimeContract, binding: RookBinding) -> McpServerStdio:
    environment = dict(contract.rook_mcp_environment)
    environment.update(
        {
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_PROCESS_ID": str(binding.route_process_id),
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": str(binding.rhino_document_serial),
            "ROOK_MCP_TOOL_PROFILE": binding.profile,
            "ROOK_PANEL_HOST_GENERATION_ID": binding.host_generation_id,
        }
    )
    return McpServerStdio(
        name="rook",
        command=str(contract.rook_mcp_command),
        args=list(contract.rook_mcp_args),
        env=[EnvVariable(name=key, value=value) for key, value in sorted(environment.items())],
    )
