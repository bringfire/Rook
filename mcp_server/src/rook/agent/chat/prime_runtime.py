"""Verify and launch one immutable Prime ACP runtime contract."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

from acp import PROTOCOL_VERSION
from acp.schema import EnvVariable, McpServerStdio

from .acp_storage import RookBinding
from .prime_runtime_artifact import ID_PATTERN, MAX_ROOT_SKILL_UTF8_BYTES, RuntimeUnavailable, verify_runtime_payload


MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS = 30_000
RUNTIME_SCHEMA_VERSION = 1
SUPPORTED_REASONING = frozenset({"off", "minimal", "low", "medium", "high", "xhigh", "max"})
# Adoption is a separate reviewed change. Never probe an older executable for support.
SUPPORTED_CONFIGURATION_COMMITS: frozenset[str] = frozenset({
    "c2055d6aff5891b918a24accf584a76852676445",
    "dacbeab26b705e7d07b55ae6f8cd3e95ceb5458b",
    "08c2610b4822af1b37350c8f03f3281a19311b59",
})
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
    uv_version: str
    uv_executable_path: Path
    prime_agent_runtime_path: Path
    prime_agent_runtime_manifest_sha256: str
    claim_key_version: int


def supports_configuration(contract: PrimeRuntimeContract) -> bool:
    return contract.compatibility_patch_commit in SUPPORTED_CONFIGURATION_COMMITS


class RuntimeCatalog(Protocol):
    def latest(self) -> PrimeRuntimeContract: ...

    def get(self, runtime_id: str) -> PrimeRuntimeContract: ...


def load_and_verify_runtime(install_root: Path, runtime_id: str) -> PrimeRuntimeContract:
    if type(runtime_id) is not str or not ID_PATTERN.fullmatch(runtime_id):
        raise RuntimeUnavailable("runtime_id is invalid")
    verified = verify_runtime_payload(install_root / "runtimes" / runtime_id, runtime_id)
    root, manifest = verified.root, verified.manifest
    if manifest["platform"] != platform.system().lower() or manifest["architecture"] != platform.machine().lower():
        raise RuntimeUnavailable("runtime platform or architecture differs from this host")
    if manifest["acpProtocolVersion"] != PROTOCOL_VERSION or manifest["pythonAcpSdkVersion"] != version("agent-client-protocol"):
        raise RuntimeUnavailable("ACP compatibility differs from the installed client")
    return PrimeRuntimeContract(
        schema_version=manifest["schemaVersion"], runtime_id=runtime_id,
        platform=manifest["platform"], architecture=manifest["architecture"],
        upstream_commit=manifest["upstreamCommit"], compatibility_patch_commit=manifest["compatibilityPatchCommit"],
        manifest_sha256=runtime_id, acp_protocol_version=manifest["acpProtocolVersion"],
        python_acp_sdk_version=manifest["pythonAcpSdkVersion"],
        executable_path=root / "pi.exe", goal_skill_path=root / "skills/goal",
        rook_skill_path=root / "skills/rook-full", rook_skill_manifest_sha256=manifest["rookSkillManifestSha256"],
        rook_skill_system_prompt=verified.rook_skill_system_prompt, uv_version=manifest["uv"]["version"],
        uv_executable_path=root / manifest["uv"]["executable"],
        prime_agent_runtime_path=root / manifest["pythonRuntime"]["root"],
        prime_agent_runtime_manifest_sha256=manifest["pythonRuntime"]["manifestSha256"],
        claim_key_version=manifest["claimKeyVersion"],
    )


def validate_windows_launch_argv(argv: tuple[str, ...]) -> None:
    if not argv or not argv[0] or any(type(value) is not str or "\0" in value for value in argv):
        raise PrimeLaunchError("invalid_launch_argument")
    try:
        rendered = subprocess.list2cmdline(argv)
        units = len(rendered.encode("utf-16-le")) // 2 + 1
    except (TypeError, UnicodeEncodeError) as exc:
        raise PrimeLaunchError("invalid_launch_argument") from exc
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
        "/" not in requested_model or any(not part.strip() for part in requested_model.split("/", 1))
    ):
        raise PrimeLaunchError("invalid_model")
    if requested_reasoning is not None and requested_reasoning not in SUPPORTED_REASONING:
        raise PrimeLaunchError("invalid_reasoning")

    values = [
        str(contract.executable_path),
        "--mode",
        "acp",
        "--no-daemon",
        "--no-approve",
        "--no-skills",
        "--no-extensions",
        "--no-context-files",
        "--no-prompt-templates",
        "--tools",
        "ipython",
        "--skill",
        str(contract.goal_skill_path),
        "--skill",
        str(contract.rook_skill_path),
        "--append-system-prompt",
        contract.rook_skill_system_prompt,
        "--resume",
        str(session_path),
    ]
    if supports_configuration(contract):
        values.extend(("--configuration-policy", "rookchat"))
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
    for key, value in base_environment.items():
        if (
            type(key) is not str
            or not key
            or "=" in key
            or "\0" in key
            or type(value) is not str
            or "\0" in value
        ):
            raise PrimeLaunchError("invalid_child_environment")
        try:
            key.encode("utf-16-le")
            value.encode("utf-16-le")
        except UnicodeEncodeError as exc:
            raise PrimeLaunchError("invalid_child_environment") from exc
    blocked = {"PI_OFFLINE", "PI_PACKAGE_DIR", "PRIME_AGENT_KERNEL_PYTHON", "PRIME_AGENT_KERNEL_VENV",
               "PRIME_AGENT_INSTALL_UV", "VIRTUAL_ENV", "PYTHONHOME", "PYTHONPATH",
               "PYTHONDONTWRITEBYTECODE", "PYTHONPYCACHEPREFIX"}
    environment = {key: value for key, value in base_environment.items()
                   if key.upper() not in blocked and not key.upper().startswith("UV_")}
    data_values = [value for key, value in environment.items() if key.upper() == "ROOK_DATA_DIR"]
    if len(data_values) != 1 or not Path(data_values[0]).is_absolute():
        raise PrimeLaunchError("invalid_child_environment")
    data = Path(data_values[0]) / "rookchat/acp/v1/prime-uv"
    path_values = [value for key, value in environment.items() if key.upper() == "PATH"]
    if len(path_values) > 1:
        raise PrimeLaunchError("invalid_child_environment")
    environment = {key: value for key, value in environment.items() if key.upper() != "PATH"}
    environment.update({
        "PATH": str(contract.uv_executable_path.parent) + (os.pathsep + path_values[0] if path_values and path_values[0] else ""),
        "UV_CACHE_DIR": str(data / "cache"),
        "UV_PYTHON_INSTALL_DIR": str(data / "python"),
        "UV_PYTHON_PREFERENCE": "only-managed", "UV_PYTHON_NO_REGISTRY": "1",
        "UV_PYTHON_INSTALL_REGISTRY": "0", "UV_NO_CONFIG": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return environment


def build_configuration_argv(contract: PrimeRuntimeContract) -> tuple[str, ...]:
    if not supports_configuration(contract):
        raise PrimeLaunchError("configuration_unavailable")
    argv = (str(contract.executable_path), "configuration", "--stdio", "--configuration-policy", "rookchat")
    validate_windows_launch_argv(argv)
    return argv


def build_configuration_env(base_environment: Mapping[str, str], contract: PrimeRuntimeContract, data_root: Path) -> dict[str, str]:
    if not data_root.is_absolute():
        raise PrimeLaunchError("invalid_child_environment")
    environment = {key: value for key, value in base_environment.items()
                   if key.upper() not in {"ROOK_DATA_DIR", "PRIME_AGENT_CODING_AGENT_DIR"}}
    environment["ROOK_DATA_DIR"] = str(data_root)
    environment = build_prime_child_env(environment, contract)
    environment["PRIME_AGENT_CODING_AGENT_DIR"] = str(data_root / "prime-config")
    return environment


def build_rook_mcp_server(binding: RookBinding) -> McpServerStdio:
    environment = {"PYTHONNOUSERSITE": "1"}
    environment.update(
        {
            "ROOK_MCP_TARGET_MODE": "panel_locked",
            "ROOK_MCP_TARGET_PROCESS_ID": str(binding.route_process_id),
            "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": str(binding.rhino_document_serial),
            "ROOK_MCP_TOOL_PROFILE": binding.profile,
            "ROOK_MCP_TARGET_HOST_GENERATION_ID": binding.host_generation_id,
        }
    )
    return McpServerStdio(
        name="rook",
        command=str(Path(sys.executable).resolve()),
        args=["-m", "rook"],
        env=[EnvVariable(name=key, value=value) for key, value in sorted(environment.items())],
    )
