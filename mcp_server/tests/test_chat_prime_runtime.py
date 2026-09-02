from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from acp import PROTOCOL_VERSION
from importlib.metadata import version

from rook.agent.chat.acp_storage import RookBinding
from rook.agent.chat.prime_runtime import (
    MAX_ROOT_SKILL_UTF8_BYTES,
    MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS,
    PrimeLaunchError,
    RuntimeUnavailable,
    build_prime_argv,
    build_prime_child_env,
    build_rook_mcp_server,
    load_and_verify_runtime,
    validate_windows_launch_argv,
)


def _canonical_bytes(payload: object) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest().upper()


def _subtree_manifest_sha256(files: dict[str, bytes], prefix: str) -> str:
    rows = [
        {
            "path": relative.removeprefix(prefix),
            "bytes": len(payload),
            "sha256": _sha256(payload),
        }
        for relative, payload in sorted(files.items())
        if relative.startswith(prefix)
    ]
    return _sha256(_canonical_bytes({"files": rows}))


def _write_runtime(
    install_root: Path,
    *,
    skill_bytes: bytes = b"# Rook Full\n\nUse the rook MCP server.\n",
) -> tuple[str, Path]:
    staging = install_root / "staging"
    files = {
        "bin/prime-agent.exe": b"prime executable fixture",
        "LICENSE": b"MIT fixture\n",
        "skills/goal/SKILL.md": b"# Goal\n",
        "skills/rook-full/SKILL.md": skill_bytes,
        "skills/rook-full/references/grasshopper.md": b"# Grasshopper\n",
    }
    for relative, payload in files.items():
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    manifest = {
        "schemaVersion": 1,
        "platform": platform.system().lower(),
        "architecture": platform.machine().lower(),
        "upstreamCommit": "c718bf3c30fd8da206ed551837cbb54f7ad15948",
        "compatibilityPatchCommit": "9c25468b62c79fc4b1419d7800740e8e41e30467",
        "acpProtocolVersion": PROTOCOL_VERSION,
        "pythonAcpSdkVersion": version("agent-client-protocol"),
        "executable": "bin/prime-agent.exe",
        "goalSkill": "skills/goal",
        "rookSkill": "skills/rook-full",
        "rookSkillManifestSha256": _subtree_manifest_sha256(files, "skills/rook-full/"),
        "rookMcpCommand": sys.executable,
        "rookMcpArgs": ["-m", "rook"],
        "rookMcpEnvironment": {"PYTHONNOUSERSITE": "1"},
        "claimKeyVersion": 1,
        "files": [
            {"path": relative, "bytes": len(payload), "sha256": _sha256(payload)}
            for relative, payload in sorted(files.items())
        ],
    }
    runtime_id = _sha256(_canonical_bytes(manifest))
    runtime_root = install_root / "runtimes" / runtime_id
    runtime_root.parent.mkdir(parents=True)
    staging.rename(runtime_root)
    (runtime_root / "runtime-manifest.json").write_bytes(_canonical_bytes(manifest))
    return runtime_id, runtime_root


def _rewrite_manifest(runtime_root: Path, **changes: object) -> tuple[str, Path]:
    manifest_path = runtime_root / "runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(changes)
    manifest_bytes = _canonical_bytes(manifest)
    runtime_id = _sha256(manifest_bytes)
    replacement = runtime_root.parent / runtime_id
    runtime_root.rename(replacement)
    (replacement / "runtime-manifest.json").write_bytes(manifest_bytes)
    return runtime_id, replacement


@pytest.fixture
def verified_runtime(tmp_path: Path):
    install_root = tmp_path / "prime"
    runtime_id, runtime_root = _write_runtime(install_root)
    return load_and_verify_runtime(install_root, runtime_id), runtime_root


def _pair(argv: tuple[str, ...], option: str) -> str:
    index = argv.index(option)
    return argv[index + 1]


def _pairs(argv: tuple[str, ...], option: str) -> list[str]:
    return [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == option]


def test_new_launch_uses_exact_flags_and_reopen_has_no_model_override(verified_runtime, tmp_path: Path):
    contract, _ = verified_runtime
    session_path = tmp_path / "session.jsonl"
    new = build_prime_argv(contract, session_path, "anthropic/claude-x", "high", reopen=False)

    assert new == (
        str(contract.executable_path),
        "--mode",
        "acp",
        "--no-daemon",
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
        str(session_path.resolve()),
        "--model",
        "anthropic/claude-x",
        "--thinking",
        "high",
    )

    reopened = build_prime_argv(contract, session_path, None, None, reopen=True)
    assert "--model" not in reopened
    assert "--thinking" not in reopened
    assert _pair(reopened, "--append-system-prompt") == contract.rook_skill_system_prompt


@pytest.mark.parametrize("reasoning", ["off", "minimal", "low", "medium", "high", "xhigh", "max"])
def test_closed_reasoning_values_are_admitted(verified_runtime, tmp_path: Path, reasoning: str):
    contract, _ = verified_runtime
    argv = build_prime_argv(contract, tmp_path / "session.jsonl", None, reasoning, reopen=False)
    assert _pair(argv, "--thinking") == reasoning


def test_invalid_reasoning_and_reopen_overrides_refuse(verified_runtime, tmp_path: Path):
    contract, _ = verified_runtime
    with pytest.raises(PrimeLaunchError, match="invalid_reasoning"):
        build_prime_argv(contract, tmp_path / "a.jsonl", None, "turbo", reopen=False)
    with pytest.raises(PrimeLaunchError, match="invalid_reasoning"):
        build_prime_argv(contract, tmp_path / "a.jsonl", None, "none", reopen=False)
    with pytest.raises(PrimeLaunchError, match="reopen_override_refused"):
        build_prime_argv(contract, tmp_path / "b.jsonl", "anthropic/x", None, reopen=True)


def test_prime_child_environment_uses_pre_dotenv_snapshot(verified_runtime, monkeypatch):
    contract, _ = verified_runtime
    pre_dotenv = {"PATH": "C:/approved", "ANTHROPIC_API_KEY": "user-owned"}
    monkeypatch.setenv("ROOK_INSTALLED_DOTENV_SENTINEL", "must-not-pass")
    child = build_prime_child_env(pre_dotenv, contract)
    assert child == pre_dotenv


def test_complete_rendered_windows_argv_refuses_before_spawn(verified_runtime, tmp_path: Path):
    contract, _ = verified_runtime
    oversized = replace(contract, rook_skill_system_prompt="x" * MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS)
    with pytest.raises(PrimeLaunchError, match="runtime_command_line_too_long"):
        build_prime_argv(oversized, tmp_path / "session.jsonl", None, None, reopen=False)


def test_windows_argv_bound_counts_the_rendered_command_and_nul():
    argv = ("C:/Program Files/Prime/prime-agent.exe", "--append-system-prompt", 'say "hello"')
    rendered = subprocess.list2cmdline(argv)
    assert len(rendered.encode("utf-16-le")) // 2 + 1 < MAX_WINDOWS_COMMAND_LINE_UTF16_UNITS
    validate_windows_launch_argv(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ("prime-agent", "valid\0invalid"),
        ("prime-agent", 7),
    ],
)
def test_windows_argv_rejects_invalid_entries(argv):
    with pytest.raises(PrimeLaunchError, match="invalid_launch_argument"):
        validate_windows_launch_argv(argv)


@pytest.mark.parametrize(
    "environment",
    [
        {"": "value"},
        {"INVALID=NAME": "value"},
        {"VALID": "value\0suffix"},
        {"VALID\0NAME": "value"},
        {7: "value"},
        {"VALID": 7},
    ],
)
def test_prime_child_environment_rejects_invalid_entries(verified_runtime, environment):
    contract, _ = verified_runtime
    with pytest.raises(PrimeLaunchError, match="invalid_child_environment"):
        build_prime_child_env(environment, contract)


def test_runtime_manifest_replay_and_required_paths(verified_runtime):
    contract, runtime_root = verified_runtime
    assert contract.executable_path == (runtime_root / "bin/prime-agent.exe").resolve()
    assert contract.goal_skill_path == (runtime_root / "skills/goal").resolve()
    assert contract.rook_skill_path == (runtime_root / "skills/rook-full").resolve()
    assert contract.python_acp_sdk_version == "0.12.1"
    assert contract.rook_skill_system_prompt.startswith("# Rook Full")
    assert contract.rook_skill_manifest_sha256 == _subtree_manifest_sha256(
        {
            "skills/rook-full/SKILL.md": b"# Rook Full\n\nUse the rook MCP server.\n",
            "skills/rook-full/references/grasshopper.md": b"# Grasshopper\n",
        },
        "skills/rook-full/",
    )


def test_manifest_tamper_refuses_before_launch(tmp_path: Path):
    install_root = tmp_path / "prime"
    runtime_id, runtime_root = _write_runtime(install_root)
    (runtime_root / "skills/rook-full/SKILL.md").write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeUnavailable, match="manifest"):
        load_and_verify_runtime(install_root, runtime_id)


def test_manifest_refuses_unlisted_authority_file(tmp_path: Path):
    install_root = tmp_path / "prime"
    runtime_id, runtime_root = _write_runtime(install_root)
    (runtime_root / "ambient.js").write_text("authority", encoding="utf-8")
    with pytest.raises(RuntimeUnavailable, match="manifest"):
        load_and_verify_runtime(install_root, runtime_id)


def test_rook_skill_subtree_identity_is_reproduced(tmp_path: Path):
    install_root = tmp_path / "prime"
    _, runtime_root = _write_runtime(install_root)
    runtime_id, _ = _rewrite_manifest(runtime_root, rookSkillManifestSha256="A" * 64)
    with pytest.raises(RuntimeUnavailable, match="Rook skill manifest"):
        load_and_verify_runtime(install_root, runtime_id)


def test_runtime_platform_and_architecture_must_match_host(tmp_path: Path):
    install_root = tmp_path / "prime"
    _, runtime_root = _write_runtime(install_root)
    runtime_id, _ = _rewrite_manifest(runtime_root, platform="not-this-platform")
    with pytest.raises(RuntimeUnavailable, match="platform"):
        load_and_verify_runtime(install_root, runtime_id)


def test_runtime_integer_fields_reject_boolean_values(tmp_path: Path):
    install_root = tmp_path / "prime"
    _, runtime_root = _write_runtime(install_root)
    runtime_id, _ = _rewrite_manifest(runtime_root, claimKeyVersion=True)
    with pytest.raises(RuntimeUnavailable, match="claimKeyVersion"):
        load_and_verify_runtime(install_root, runtime_id)


def test_runtime_manifest_schema_rejects_extra_keys_and_invalid_optional_commit(tmp_path: Path):
    extra_root = tmp_path / "extra"
    _, runtime_root = _write_runtime(extra_root)
    runtime_id, _ = _rewrite_manifest(runtime_root, ambientAuthority=True)
    with pytest.raises(RuntimeUnavailable, match="manifest keys"):
        load_and_verify_runtime(extra_root, runtime_id)

    row_root = tmp_path / "row"
    _, runtime_root = _write_runtime(row_root)
    manifest = json.loads((runtime_root / "runtime-manifest.json").read_text(encoding="utf-8"))
    manifest["files"][0]["ambient"] = True
    runtime_id, _ = _rewrite_manifest(runtime_root, files=manifest["files"])
    with pytest.raises(RuntimeUnavailable, match="manifest entry"):
        load_and_verify_runtime(row_root, runtime_id)

    patch_root = tmp_path / "patch"
    _, runtime_root = _write_runtime(patch_root)
    runtime_id, _ = _rewrite_manifest(runtime_root, compatibilityPatchCommit=7)
    with pytest.raises(RuntimeUnavailable, match="compatibilityPatchCommit"):
        load_and_verify_runtime(patch_root, runtime_id)


def test_runtime_manifest_exact_integer_types_reject_boolean_schema_and_file_bytes(tmp_path: Path):
    schema_root = tmp_path / "schema"
    _, runtime_root = _write_runtime(schema_root)
    runtime_id, _ = _rewrite_manifest(runtime_root, schemaVersion=True)
    with pytest.raises(RuntimeUnavailable, match="schema"):
        load_and_verify_runtime(schema_root, runtime_id)

    row_root = tmp_path / "bytes"
    _, runtime_root = _write_runtime(row_root)
    manifest = json.loads((runtime_root / "runtime-manifest.json").read_text(encoding="utf-8"))
    manifest["files"][0]["bytes"] = True
    runtime_id, _ = _rewrite_manifest(runtime_root, files=manifest["files"])
    with pytest.raises(RuntimeUnavailable, match="manifest entry"):
        load_and_verify_runtime(row_root, runtime_id)


def test_root_skill_size_and_utf8_are_bounded(tmp_path: Path):
    oversized_root = tmp_path / "oversized"
    runtime_id, _ = _write_runtime(oversized_root, skill_bytes=b"x" * (MAX_ROOT_SKILL_UTF8_BYTES + 1))
    with pytest.raises(RuntimeUnavailable, match="root_skill_too_large"):
        load_and_verify_runtime(oversized_root, runtime_id)

    invalid_root = tmp_path / "invalid"
    runtime_id, _ = _write_runtime(invalid_root, skill_bytes=b"\xff")
    with pytest.raises(RuntimeUnavailable, match="root_skill_invalid_utf8"):
        load_and_verify_runtime(invalid_root, runtime_id)


def test_rook_mcp_declaration_is_contract_owned(verified_runtime):
    contract, _ = verified_runtime
    binding = RookBinding(
        profile="full",
        host_generation_id="f55bdd3f-d282-4c76-b89c-b32d7c705615",
        rhino_document_serial=41,
        route_process_id=2024,
    )
    server = build_rook_mcp_server(contract, binding)
    env = {item.name: item.value for item in server.env}

    assert server.name == "rook"
    assert server.command == str(Path(sys.executable).resolve())
    assert server.args == ["-m", "rook"]
    assert env == {
        "PYTHONNOUSERSITE": "1",
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "2024",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "41",
        "ROOK_MCP_TOOL_PROFILE": "full",
        "ROOK_PANEL_HOST_GENERATION_ID": "f55bdd3f-d282-4c76-b89c-b32d7c705615",
    }


def test_runtime_id_cannot_escape_install_root(tmp_path: Path):
    with pytest.raises(RuntimeUnavailable, match="runtime_id"):
        load_and_verify_runtime(tmp_path, "../outside")
