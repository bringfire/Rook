"""Campaign-specific proof of the installed containment boundary.

This file is staged beside release diagnostics and executed with the installed
Rook virtual environment.  It is deliberately not part of the Rook package or
MCP surface.  Expected values, probe assignments, and result adapters are all
literal here; callers provide release identity and filesystem locations only.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import contextvars
import csv
import dataclasses
import hashlib
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Literal


SCHEMA_VERSION = 1
PROFILES = ("full", "lean", "readonly")
CONTAINED_TOOLS = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)
DISCOVERY_COUNTS = {
    "unprofiled": 422,
    "interactive-full": 425,
    "lean": 20,
    "readonly": 148,
}
TRANSPORT_INGRESSES = ("public_mcp", "progressive_meta")

EXPECTED_DENIALS = {
    "gh_execute_intent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_execute_intent",
        "disposition": "retired",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper surface; inspect state and "
            "components, then use explicit gh_edit or supported script tools "
            "and verify solve state, outputs, and errors."
        ),
    },
    "rhino_execute_intent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "rhino_execute_intent",
        "disposition": "retired",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Rhino surface; use explicit typed Rhino "
            "tools, rhino_execute, or a sanctioned preflighted rhino_command, "
            "then verify the host result."
        ),
    },
    "plan_and_execute": {
        "code": "legacy_semantic_tool_contained",
        "tool": "plan_and_execute",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current surface and perform bounded steps through "
            "explicit admitted tools; autonomous plan execution is suspended."
        ),
    },
    "spawn_agent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "spawn_agent",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current surface and use the connected model to call "
            "explicit admitted tools directly; autonomous agent spawning is "
            "suspended."
        ),
    },
    "gh_explore_workflow": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_explore_workflow",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper inspection surface and use "
            "explicit snapshot, component, or knowledge tools; semantic "
            "workflow exploration is suspended."
        ),
    },
    "gh_replay_recipe": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_replay_recipe",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper surface and apply reviewed "
            "explicit gh_edit operations; recipe replay is suspended."
        ),
    },
}


@dataclass(frozen=True)
class InternalProbe:
    seam: str
    tool: str
    origin: str
    result_adapter: str


INTERNAL_PROBES = tuple(
    InternalProbe(*row)
    for row in (
        ("server._call_tool_dispatch", "gh_execute_intent", "server_dispatch", "dictionary_envelope"),
        ("server._mcp_tool_executor", "rhino_execute_intent", "server_dispatch", "dictionary_envelope"),
        ("ToolDispatcher.dispatch", "plan_and_execute", "tool_dispatcher", "dictionary_envelope"),
        ("ToolDispatcher._dispatch_inner", "spawn_agent", "tool_dispatcher", "dictionary_envelope"),
        ("ToolDispatcher._call_local", "gh_explore_workflow", "tool_dispatcher", "dictionary_envelope"),
        ("ToolDispatcher._dispatch_with_knowledge", "gh_replay_recipe", "tool_dispatcher", "dictionary_envelope"),
        ("RookAgent._run_loop", "gh_execute_intent", "rook_agent", "rook_agent_protocol"),
        ("RookAgent._execute_tool", "rhino_execute_intent", "rook_agent", "dictionary_envelope"),
        ("RookAgent._execute_local_tool", "plan_and_execute", "rook_agent", "dictionary_envelope"),
        ("ChatRunner.run_turn", "spawn_agent", "rook_chat", "rook_chat_protocol"),
        ("rook.agent.plan_graph_live.apply_live_producer_node", "gh_explore_workflow", "plan_graph", "plan_graph_refusal"),
        ("BootstrapRunner.run_test", "gh_replay_recipe", "internal_handler", "bootstrap_test_result"),
        ("BootstrapRunner._mock_executor", "gh_execute_intent", "internal_handler", "dictionary_envelope"),
        ("bootstrap.HttpExecutor.execute", "rhino_execute_intent", "internal_handler", "dictionary_envelope"),
        ("bootstrap.create_mock_executor.callable", "plan_and_execute", "internal_handler", "dictionary_envelope"),
        ("learning.create_tool_executor.callable", "spawn_agent", "internal_handler", "dictionary_envelope"),
        ("Investigator.investigate_tool", "gh_explore_workflow", "internal_handler", "investigation_result"),
        ("Investigator.investigate_gap", "gh_replay_recipe", "internal_handler", "investigation_result"),
        ("Investigator.investigate_workflow", "gh_execute_intent", "internal_handler", "investigation_result"),
        ("Investigator._run_experiment", "rhino_execute_intent", "internal_handler", "experiment_result"),
        ("HybridInvestigator.investigate_tool", "plan_and_execute", "internal_handler", "hybrid_investigation_result"),
        ("HybridInvestigator.investigate_gap", "spawn_agent", "internal_handler", "hybrid_investigation_result"),
        ("LearningSession.run_investigation_cycle.tool_target", "gh_explore_workflow", "internal_handler", "investigation_result"),
        ("explorer.HttpExecutor.execute", "gh_replay_recipe", "internal_handler", "explorer_execution_result"),
        ("explorer.HttpExecutor.execute_sync", "gh_execute_intent", "internal_handler", "explorer_execution_result"),
        ("explorer.MockExecutor.execute", "rhino_execute_intent", "internal_handler", "explorer_execution_result"),
        ("explorer.MockExecutor.execute_sync", "plan_and_execute", "internal_handler", "explorer_execution_result"),
        ("server._handle_spawn_agent", "spawn_agent", "internal_handler", "dictionary_envelope"),
        ("server._handle_plan_and_execute", "plan_and_execute", "internal_handler", "dictionary_envelope"),
    )
)


@dataclass(frozen=True)
class RuntimeInputs:
    expected_release_sha: str
    expected_version: str
    expected_python: Path
    expected_venv: Path
    expected_package_root: Path
    packaged_runtime_manifest: Path
    installed_runtime_manifest: Path
    install_state: Path
    packaged_wheelhouse: Path
    forbidden_source_roots: tuple[Path, ...]
    staged_script_path: Path


class ProbeError(RuntimeError):
    """The installed runtime failed a release acceptance assertion."""


_SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$", re.ASCII)
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$", re.ASCII)
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$",
    re.ASCII,
)
_CONTROLLED_EXACT = frozenset(
    {
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUSERBASE",
        "PYTHONNOUSERSITE",
        "DSPY_MODEL",
        "DSPY_CACHEDIR",
        "CHIRP_HOME",
    }
)
_PROCESS_KEYS = {
    "executable",
    "cwd",
    "sys_path",
    "rook_origins",
    "process_id",
    "process_start_token",
}
_TELEMETRY_KEYS = {"process_id", "process_start_token", "events"}


def _canonical_path(value: str | os.PathLike[str]) -> Path:
    return Path(value).expanduser().resolve()


def _casefold_lookup(base: Mapping[str, str], name: str) -> str | None:
    if name in base:
        return str(base[name])
    matches = [str(value) for key, value in base.items() if key.casefold() == name.casefold()]
    if len(matches) == 1:
        return matches[0]
    return None


def build_installed_child_environment(
    base: Mapping[str, str],
    *,
    profile: str | None = None,
    interactive: bool = False,
) -> dict[str, str]:
    """Scrub inherited Python/Rook controls and add one closed release map."""
    if profile is not None and profile not in PROFILES:
        raise ProbeError(f"invalid child profile: {profile!r}")
    if interactive and profile != "full":
        raise ProbeError("interactive child requires explicit full profile")

    required: dict[str, str] = {}
    for name in ("ROOK_INSTALL_ROOT", "ROOK_DATA_DIR", "DSPY_CACHEDIR"):
        raw = _casefold_lookup(base, name)
        if not raw:
            raise ProbeError(f"missing code-owned child environment value: {name}")
        path = _canonical_path(raw)
        if not path.is_absolute():
            raise ProbeError(f"child environment path is not absolute: {name}")
        required[name] = str(path)
    chirp_raw = _casefold_lookup(base, "CHIRP_HOME")
    if chirp_raw:
        required["CHIRP_HOME"] = str(_canonical_path(chirp_raw))

    cleaned: dict[str, str] = {}
    for raw_name, raw_value in base.items():
        name = str(raw_name)
        folded = name.upper()
        if folded in _CONTROLLED_EXACT or folded.startswith("ROOK_"):
            continue
        cleaned[name] = str(raw_value)
    cleaned.update(
        {
            "PYTHONNOUSERSITE": "1",
            "ROOK_INSTALL_ROOT": required["ROOK_INSTALL_ROOT"],
            "ROOK_DATA_DIR": required["ROOK_DATA_DIR"],
            "ROOK_MODE": "release",
            "ROOK_DSPY_RESTRICT_PICKLE": "1",
            "DSPY_CACHEDIR": required["DSPY_CACHEDIR"],
        }
    )
    if "CHIRP_HOME" in required:
        cleaned["CHIRP_HOME"] = required["CHIRP_HOME"]
    if profile is not None:
        cleaned["ROOK_MCP_TOOL_PROFILE"] = profile
    if interactive:
        cleaned["ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING"] = "1"
    return cleaned


def _absolute_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("path must be absolute")
    return path.resolve()


def _release_sha(raw: str) -> str:
    if _SHA40_RE.fullmatch(raw) is None:
        raise argparse.ArgumentTypeError("release SHA must be exactly 40 hex")
    return raw.lower()


def _version(raw: str) -> str:
    if _VERSION_RE.fullmatch(raw) is None:
        raise argparse.ArgumentTypeError("version must be X.Y.Z")
    return raw


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="installed_probe.py")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run")
    run.add_argument("--expected-release-sha", required=True, type=_release_sha)
    run.add_argument("--expected-version", required=True, type=_version)
    run.add_argument("--expected-python", required=True, type=_absolute_path)
    run.add_argument("--expected-venv", required=True, type=_absolute_path)
    run.add_argument("--expected-package-root", required=True, type=_absolute_path)
    run.add_argument("--packaged-runtime-manifest", required=True, type=_absolute_path)
    run.add_argument("--installed-runtime-manifest", required=True, type=_absolute_path)
    run.add_argument("--install-state", required=True, type=_absolute_path)
    run.add_argument("--packaged-wheelhouse", required=True, type=_absolute_path)
    run.add_argument("--forbidden-source-root", action="append", required=True, type=_absolute_path)
    run.add_argument("--output", required=True, type=_absolute_path)

    discovery = commands.add_parser("_child-discovery")
    discovery.add_argument("--surface", required=True, choices=tuple(DISCOVERY_COUNTS))
    discovery.add_argument("--output", required=True, type=_absolute_path)

    transport = commands.add_parser("_child-transport")
    transport.add_argument("--profile", required=True, choices=PROFILES)
    transport.add_argument("--output", required=True, type=_absolute_path)

    internal = commands.add_parser("_child-internal")
    internal.add_argument("--probe-index", required=True, type=int, choices=range(1, 30))
    internal.add_argument("--output", required=True, type=_absolute_path)
    return parser


def _is_reparse(path: Path) -> bool:
    try:
        stat = path.lstat()
    except OSError as exc:
        raise ProbeError(f"could not inspect path: {path}") from exc
    attributes = getattr(stat, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & 0x400)


def _require_file(path: Path, label: str) -> Path:
    path = _canonical_path(path)
    if not path.is_file() or _is_reparse(path):
        raise ProbeError(f"{label} must be a non-reparse file: {path}")
    return path


def _require_directory(path: Path, label: str) -> Path:
    path = _canonical_path(path)
    if not path.is_dir() or _is_reparse(path):
        raise ProbeError(f"{label} must be a non-reparse directory: {path}")
    return path


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"{label} is not valid UTF-8 JSON") from exc
    if type(value) is not dict:
        raise ProbeError(f"{label} must contain one JSON object")
    return value


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _record_hash(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")


def _normalized_project(raw: object) -> str:
    if type(raw) is not str:
        return ""
    return re.sub(r"[-_.]+", "-", raw).casefold()


def _validate_rook_wheel(wheel: Path, package_root: Path) -> list[str]:
    try:
        with zipfile.ZipFile(wheel) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise ProbeError("wheel contains duplicate members")
            if any(
                Path(name).is_absolute()
                or ".." in Path(name).parts
                or "\\" in name
                for name in names
            ):
                raise ProbeError("wheel contains an unsafe member path")
            record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
            if len(record_names) != 1:
                raise ProbeError("Rook wheel must contain exactly one RECORD")
            record_name = record_names[0]
            record_bytes = archive.read(record_name)
            try:
                rows = list(csv.reader(record_bytes.decode("utf-8").splitlines()))
            except (UnicodeError, csv.Error) as exc:
                raise ProbeError("wheel RECORD is malformed") from exc
            if any(len(row) != 3 for row in rows):
                raise ProbeError("wheel RECORD row shape drift")
            by_name: dict[str, tuple[str, str]] = {}
            for name, digest, size in rows:
                if name in by_name:
                    raise ProbeError("wheel RECORD contains duplicate paths")
                by_name[name] = (digest, size)
            if set(by_name) != set(names):
                raise ProbeError("wheel RECORD membership does not match wheel")
            for name in names:
                digest, raw_size = by_name[name]
                data = archive.read(name)
                if name == record_name:
                    if digest != "" or raw_size != "":
                        raise ProbeError("wheel RECORD self-entry must be unhashed")
                    continue
                if digest != f"sha256={_record_hash(data)}" or raw_size != str(len(data)):
                    raise ProbeError(f"wheel RECORD hash/size drift: {name}")

            rook_files = sorted(
                name
                for name in names
                if name.startswith("rook/")
                and not name.endswith("/")
                and "__pycache__" not in Path(name).parts
                and not name.endswith((".pyc", ".pyo"))
            )
            if not rook_files:
                raise ProbeError("Rook wheel contains no rook package files")
            installed_files = sorted(
                "rook/" + path.relative_to(package_root).as_posix()
                for path in package_root.rglob("*")
                if path.is_file()
                and not _is_reparse(path)
                and "__pycache__" not in path.relative_to(package_root).parts
                and path.suffix not in {".pyc", ".pyo"}
            )
            if installed_files != rook_files:
                raise ProbeError("installed Rook file membership does not match wheel")
            for name in rook_files:
                installed = package_root / Path(name).relative_to("rook")
                if installed.read_bytes() != archive.read(name):
                    raise ProbeError(f"installed Rook file does not match wheel: {name}")
            return rook_files
    except (OSError, zipfile.BadZipFile) as exc:
        raise ProbeError(f"could not validate Rook wheel: {wheel}") from exc


def validate_installed_runtime(inputs: RuntimeInputs) -> dict[str, object]:
    """Validate immutable release identity before any child is launched."""
    if _SHA40_RE.fullmatch(inputs.expected_release_sha) is None:
        raise ProbeError("expected release SHA is malformed")
    if _VERSION_RE.fullmatch(inputs.expected_version) is None:
        raise ProbeError("expected version is malformed")
    expected_python = _require_file(inputs.expected_python, "installed Python")
    expected_venv = _require_directory(inputs.expected_venv, "installed venv")
    package_root = _require_directory(inputs.expected_package_root, "installed package root")
    if not _path_within(expected_python, expected_venv):
        raise ProbeError("installed Python escaped expected venv")
    if not _path_within(package_root, expected_venv):
        raise ProbeError("installed package root escaped expected venv")
    packaged_manifest = _require_file(inputs.packaged_runtime_manifest, "packaged runtime manifest")
    installed_manifest = _require_file(inputs.installed_runtime_manifest, "installed runtime manifest")
    install_state = _require_file(inputs.install_state, "install state")
    wheelhouse = _require_directory(inputs.packaged_wheelhouse, "packaged wheelhouse")
    _require_file(inputs.staged_script_path, "staged installed probe")

    packaged_bytes = packaged_manifest.read_bytes()
    installed_bytes = installed_manifest.read_bytes()
    if packaged_bytes != installed_bytes:
        raise ProbeError("packaged and installed runtime manifests differ")
    manifest_sha = _sha256_bytes(packaged_bytes)
    manifest = _load_json_object(packaged_manifest, "runtime manifest")
    if manifest.get("schema_version") != 1:
        raise ProbeError("runtime manifest schema drift")
    if manifest.get("release_version") != inputs.expected_version:
        raise ProbeError("runtime manifest version drift")
    raw_sha = manifest.get("rook_git_sha")
    if type(raw_sha) is not str or raw_sha.casefold() != inputs.expected_release_sha.casefold():
        raise ProbeError("runtime manifest release SHA drift")

    state = _load_json_object(install_state, "install state")
    if state.get("schema_version") != 1:
        raise ProbeError("install state schema drift")
    python_state = state.get("python")
    rook_state = state.get("rook")
    if type(python_state) is not dict or type(rook_state) is not dict:
        raise ProbeError("install state runtime records are malformed")
    if _canonical_path(str(python_state.get("runtime_manifest_path"))) != installed_manifest:
        raise ProbeError("install state runtime manifest path drift")
    for label, value in (
        ("python.runtime_manifest_sha256", python_state.get("runtime_manifest_sha256")),
        ("python.identity_hash", python_state.get("identity_hash")),
        ("rook.python_identity_hash", rook_state.get("python_identity_hash")),
    ):
        if type(value) is not str or value.casefold() != manifest_sha:
            raise ProbeError(f"install state manifest identity drift: {label}")
    if _canonical_path(str(rook_state.get("venv_path"))) != expected_venv:
        raise ProbeError("install state Rook venv path drift")
    if _canonical_path(str(rook_state.get("python_path"))) != expected_python:
        raise ProbeError("install state Rook Python path drift")

    wheelhouse_record = manifest.get("wheelhouse")
    if type(wheelhouse_record) is not dict or type(wheelhouse_record.get("wheels")) is not list:
        raise ProbeError("runtime manifest wheelhouse record is malformed")
    wheel_records = wheelhouse_record["wheels"]
    wheel_files = sorted(path for path in wheelhouse.glob("*.whl") if path.is_file())
    if len(wheel_records) != len(wheel_files) or not wheel_files:
        raise ProbeError("runtime manifest wheel membership drift")
    records_by_file: dict[str, dict[str, object]] = {}
    for raw_record in wheel_records:
        if type(raw_record) is not dict or set(raw_record) != {"file", "project", "version", "sha256", "tags"}:
            raise ProbeError("runtime manifest wheel record shape drift")
        name = raw_record["file"]
        if type(name) is not str or Path(name).name != name or name in records_by_file:
            raise ProbeError("runtime manifest wheel filename drift")
        records_by_file[name] = raw_record
    if set(records_by_file) != {path.name for path in wheel_files}:
        raise ProbeError("runtime manifest wheel filenames drift")

    wheel_hashes: dict[str, str] = {}
    rook_wheels: list[Path] = []
    for wheel in wheel_files:
        if _is_reparse(wheel):
            raise ProbeError(f"wheel is a reparse point: {wheel}")
        actual = _sha256_file(wheel)
        declared = records_by_file[wheel.name].get("sha256")
        if type(declared) is not str or declared.casefold() != actual:
            raise ProbeError(f"wheel hash drift: {wheel.name}")
        wheel_hashes[wheel.name] = actual
        record = records_by_file[wheel.name]
        if _normalized_project(record.get("project")) == "rook-mcp":
            if record.get("version") != inputs.expected_version:
                raise ProbeError("Rook wheel version drift")
            rook_wheels.append(wheel)
    if len(rook_wheels) != 1:
        raise ProbeError("runtime manifest must identify exactly one Rook wheel")
    rook_files = _validate_rook_wheel(rook_wheels[0], package_root)
    return {
        "release_sha": inputs.expected_release_sha.lower(),
        "version": inputs.expected_version,
        "python": str(expected_python),
        "venv": str(expected_venv),
        "package_root": str(package_root),
        "runtime_manifest_sha256": manifest_sha,
        "wheel_hashes": wheel_hashes,
        "rook_record_files": rook_files,
    }


def _expected_denial(tool: str) -> dict[str, object]:
    if tool not in EXPECTED_DENIALS:
        raise ProbeError(f"unexpected contained tool: {tool!r}")
    return {"success": False, "data": EXPECTED_DENIALS[tool]}


def _validate_denial(tool: str, value: object) -> None:
    expected = _expected_denial(tool)
    if type(value) is not dict or set(value) != {"success", "data"} or value["success"] is not False:
        raise ProbeError(f"stable denial drift: {tool}")
    data = value["data"]
    expected_data = expected["data"]
    if type(data) is not dict or type(expected_data) is not dict or set(data) != set(expected_data):
        raise ProbeError(f"stable denial payload shape drift: {tool}")
    for name, expected_value in expected_data.items():
        if type(data[name]) is not type(expected_value) or data[name] != expected_value:
            raise ProbeError(f"stable denial payload field drift: {tool}.{name}")


def _validate_event(event: object, tool: str, origin: str) -> None:
    if type(event) is not dict or set(event) != {"tool", "disposition", "origin", "timestamp"}:
        raise ProbeError("telemetry event shape drift")
    if event["tool"] != tool or event["origin"] != origin:
        raise ProbeError("telemetry identity drift")
    if event["disposition"] != EXPECTED_DENIALS[tool]["disposition"]:
        raise ProbeError("telemetry disposition drift")
    timestamp = event["timestamp"]
    if type(timestamp) is not str or _TIMESTAMP_RE.fullmatch(timestamp) is None:
        raise ProbeError("telemetry timestamp format drift")
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise ProbeError("telemetry timestamp is not a real UTC timestamp") from exc


def _validate_record_telemetry(
    value: object,
    *,
    process_id: int,
    process_start_token: str,
    tool: str,
    origin: str,
) -> None:
    if type(value) is not dict or set(value) != {"process_id", "process_start_token", "event"}:
        raise ProbeError("record telemetry shape drift")
    if value["process_id"] != process_id or value["process_start_token"] != process_start_token:
        raise ProbeError("record and telemetry process identity differ")
    _validate_event(value["event"], tool, origin)


def _validate_snapshot(snapshot: object) -> None:
    if type(snapshot) is not dict or set(snapshot) != _TELEMETRY_KEYS:
        raise ProbeError("telemetry snapshot shape drift")
    if type(snapshot["process_id"]) is not int or snapshot["process_id"] <= 0:
        raise ProbeError("telemetry PID drift")
    token = snapshot["process_start_token"]
    if type(token) is not str or _TOKEN_RE.fullmatch(token) is None:
        raise ProbeError("telemetry start token drift")
    if type(snapshot["events"]) is not list or len(snapshot["events"]) > 50:
        raise ProbeError("telemetry ring drift")


def _one_event_delta(before: object, after: object, tool: str, origin: str) -> dict[str, object]:
    _validate_snapshot(before)
    _validate_snapshot(after)
    assert isinstance(before, dict) and isinstance(after, dict)
    if before["process_id"] != after["process_id"] or before["process_start_token"] != after["process_start_token"]:
        raise ProbeError("telemetry process identity changed")
    old = before["events"]
    new = after["events"]
    assert isinstance(old, list) and isinstance(new, list)
    if len(old) < 50:
        if len(new) != len(old) + 1 or new[:-1] != old:
            raise ProbeError("telemetry did not append exactly one event")
    elif len(new) != 50 or new[:-1] != old[1:]:
        raise ProbeError("telemetry ring append/eviction drift")
    event = new[-1]
    _validate_event(event, tool, origin)
    assert isinstance(event, dict)
    return dict(event)


def _history(tool: str, call_id: str, *, chat: bool = False) -> list[dict[str, object]]:
    assistant: dict[str, object] = {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": tool, "arguments": '{"probe":true}'},
            }
        ],
    }
    if not chat:
        assistant["content"] = None
    return [
        {"role": "user", "content": "exercise installed containment"},
        assistant,
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(_expected_denial(tool), separators=(",", ":")),
        },
        {"role": "assistant", "content": "continued after containment"},
    ]


def _expected_adapter_evidence(adapter: str, tool: str, index: int) -> dict[str, object]:
    if adapter == "dictionary_envelope":
        return {"outer_type": "builtins.dict", "value": _expected_denial(tool)}
    if adapter == "rook_agent_protocol":
        return {
            "outer_type": "builtins.NoneType",
            "return_is_none": True,
            "history": _history(tool, f"probe-agent-{index}"),
            "loop": {
                "tool_calls": 1,
                "successful_tools": 0,
                "tool_start_events": 0,
                "tool_end_events": 0,
                "adaptations": 0,
                "observations": 0,
                "failure_count_entries": 0,
            },
        }
    if adapter == "rook_chat_protocol":
        return {
            "outer_type": "builtins.async_generator",
            "history": _history(tool, f"probe-chat-{index}", chat=True),
            "events": ["text_delta", "done"],
            "loop": {
                "tool_calls": 1,
                "successful_tools": 0,
                "tool_start_events": 0,
                "tool_result_events": 0,
                "error_events": 0,
                "tools_used": [],
                "surface_adaptations": 0,
                "meta_only_diagnoses": 0,
                "stuck_diagnoses": 0,
            },
        }
    if adapter == "plan_graph_refusal":
        return {
            "outer_type": "rook.agent.plan_graph_live.LiveProducerResult",
            "graph_unchanged": True,
            "applied": False,
            "node_id": "containment-producer",
            "tool_name": tool,
            "outcome_status": None,
            "reason": "tool_lifecycle_denied",
        }
    if adapter == "bootstrap_test_result":
        return {
            "outer_type": "rook.bootstrap.runner.TestResult",
            "test_id": f"containment:{tool}",
            "tool": tool,
            "params": {},
            "expected": "either",
            "actual": "error",
            "response": _expected_denial(tool),
            "error_message": "legacy_semantic_tool_contained",
            "duration_ms": 0.0,
            "timestamp_valid": True,
            "created_object_ids": [],
            "completed_tests": [],
        }
    if adapter == "investigation_result":
        return {
            "outer_type": "rook.learning.investigator.InvestigationResult",
            "gap_id": None,
            "tool": tool,
            "patterns_discovered": [],
            "antipatterns_discovered": [],
            "experiments": [],
            "gap_resolved": False,
            "resolution": None,
            "new_gaps": [],
            "insights": [],
            "containment_denial": _expected_denial(tool),
        }
    if adapter == "experiment_result":
        return {
            "outer_type": "rook.learning.investigator.ExperimentResult",
            "tool": tool,
            "params": {},
            "success": False,
            "response": _expected_denial(tool),
            "error": "legacy_semantic_tool_contained",
            "error_category": "unknown",
            "execution_time_ms": 0,
        }
    if adapter == "hybrid_investigation_result":
        return {
            "outer_type": "rook.learning.hybrid_investigator.HybridInvestigationResult",
            "tool": tool,
            "success": False,
            "hypotheses_generated": [],
            "diagnosis": None,
            "reasoning_trace": [],
            "hypothesis_selected": None,
            "fix_selected": None,
            "patterns_discovered": [],
            "antipatterns_discovered": [],
            "insights": [],
            "consolidation_action": None,
            "workflow_detected": None,
            "nuanced_reward": None,
            "visually_verified": False,
            "visual_description": None,
            "viewport_hash_before": None,
            "viewport_hash_after": None,
            "gap_id": None,
            "gap_resolved": False,
            "resolution": None,
            "new_gaps": [],
            "attempts": 0,
            "time_ms": 0,
            "containment_denial": _expected_denial(tool),
            "serialized_containment_denial": _expected_denial(tool),
        }
    if adapter == "explorer_execution_result":
        return {
            "outer_type": "rook.explorer.executor.ExecutionResult",
            "tool_name": tool,
            "params": {},
            "success": False,
            "response": _expected_denial(tool),
            "error": "legacy_semantic_tool_contained",
            "duration_ms": 0,
        }
    raise ProbeError(f"unexpected result adapter: {adapter}")


def _validate_adapter_evidence(adapter: str, tool: str, index: int, value: object) -> None:
    expected = _expected_adapter_evidence(adapter, tool, index)
    if type(value) is not dict or value != expected:
        raise ProbeError(f"internal result adapter drift: {adapter}")


def _validate_startup_refresh(value: object) -> None:
    expected_keys = {
        "status",
        "persisted",
        "refresh_requested",
        "retained_names",
        "cache_bytes_unchanged",
        "cache_path_unchanged",
        "unlink_calls",
        "rmtree_calls",
        "telemetry_unchanged",
        "normal_status",
        "normal_catalog_count",
    }
    if type(value) is not dict or set(value) != expected_keys:
        raise ProbeError("startup refresh evidence shape drift")
    if value != {
        "status": "degraded_cache",
        "persisted": False,
        "refresh_requested": True,
        "retained_names": ["safe_cached"],
        "cache_bytes_unchanged": True,
        "cache_path_unchanged": True,
        "unlink_calls": 0,
        "rmtree_calls": 0,
        "telemetry_unchanged": True,
        "normal_status": "fresh",
        "normal_catalog_count": DISCOVERY_COUNTS["unprofiled"],
    }:
        raise ProbeError("startup refresh retention drift")


def _validate_names(value: object, expected_count: int, label: str) -> list[str]:
    if type(value) is not list or len(value) != expected_count or not all(type(item) is str for item in value):
        raise ProbeError(f"{label} name list/count drift")
    if len(set(value)) != len(value):
        raise ProbeError(f"{label} contains duplicate names")
    leaked = set(value).intersection(CONTAINED_TOOLS)
    if leaked:
        raise ProbeError(f"{label} leaked contained names: {sorted(leaked)}")
    return value


def _validate_discovery_snapshots(snapshots: object) -> None:
    if type(snapshots) is not list or len(snapshots) != 4:
        raise ProbeError("discovery snapshot count drift")
    expected_keys = {
        "surface",
        "process",
        "profile_env_present",
        "interactive_env_present",
        "catalog_names",
        "rook_agent_names",
        "rook_chat_names",
        "telemetry_before",
        "telemetry_after",
        "startup_refresh",
    }
    for snapshot, (surface, count) in zip(snapshots, DISCOVERY_COUNTS.items(), strict=True):
        if type(snapshot) is not dict or set(snapshot) != expected_keys or snapshot["surface"] != surface:
            raise ProbeError("discovery snapshot order/shape drift")
        expected_profile_present = surface != "unprofiled"
        expected_interactive = surface == "interactive-full"
        if type(snapshot["profile_env_present"]) is not bool or snapshot["profile_env_present"] is not expected_profile_present:
            raise ProbeError("discovery profile environment presence drift")
        if type(snapshot["interactive_env_present"]) is not bool or snapshot["interactive_env_present"] is not expected_interactive:
            raise ProbeError("discovery interactive environment presence drift")
        catalog = _validate_names(snapshot["catalog_names"], count, "catalog")
        agent = _validate_names(snapshot["rook_agent_names"], count, "RookAgent projection")
        chat = _validate_names(snapshot["rook_chat_names"], count, "RookChat projection")
        if set(agent) != set(catalog) or set(chat) != set(catalog):
            raise ProbeError("model projection membership drift")
        _validate_snapshot(snapshot["telemetry_before"])
        _validate_snapshot(snapshot["telemetry_after"])
        if snapshot["telemetry_before"] != snapshot["telemetry_after"]:
            raise ProbeError("discovery emitted containment telemetry")
        process = snapshot["process"]
        if type(process) is not dict or set(process) != _PROCESS_KEYS:
            raise ProbeError("discovery process evidence shape drift")
        if process["process_id"] != snapshot["telemetry_before"]["process_id"] or process["process_start_token"] != snapshot["telemetry_before"]["process_start_token"]:
            raise ProbeError("discovery process/telemetry identity drift")
        if surface == "unprofiled":
            _validate_startup_refresh(snapshot["startup_refresh"])
        elif snapshot["startup_refresh"] is not None:
            raise ProbeError("startup retention subprobe ran outside unprofiled child")


def _validate_transport_records(records: object) -> None:
    if type(records) is not list or len(records) != 36:
        raise ProbeError("transport record count drift")
    expected_keys = {
        "index",
        "profile",
        "ingress",
        "tool",
        "origin",
        "denial",
        "wire",
        "process_id",
        "process_start_token",
        "telemetry",
        "downstream",
    }
    expected: list[tuple[str, str, str]] = [
        (profile, ingress, tool)
        for profile in PROFILES
        for ingress in TRANSPORT_INGRESSES
        for tool in CONTAINED_TOOLS
    ]
    identities: set[tuple[str, str, str]] = set()
    for index, (record, identity) in enumerate(zip(records, expected, strict=True), 1):
        if type(record) is not dict or set(record) != expected_keys:
            raise ProbeError("transport record shape drift")
        profile, ingress, tool = identity
        if (record["index"], record["profile"], record["ingress"], record["tool"]) != (index, profile, ingress, tool):
            raise ProbeError("transport record order/identity drift")
        identities.add((profile, ingress, tool))
        origin = "public_mcp" if ingress == "public_mcp" else "progressive_meta"
        if record["origin"] != origin:
            raise ProbeError("transport origin drift")
        _validate_denial(tool, record["denial"])
        expected_wire = {
            "content_count": 1,
            "content_types": ["text"],
            "is_error": False,
            "text": "Error: " + json.dumps(EXPECTED_DENIALS[tool], indent=2),
        }
        if type(record["wire"]) is not dict or record["wire"] != expected_wire:
            raise ProbeError("transport wire protocol drift")
        if type(record["process_id"]) is not int or record["process_id"] <= 0:
            raise ProbeError("transport PID drift")
        if type(record["process_start_token"]) is not str or _TOKEN_RE.fullmatch(record["process_start_token"]) is None:
            raise ProbeError("transport process token drift")
        _validate_record_telemetry(
            record["telemetry"],
            process_id=record["process_id"],
            process_start_token=record["process_start_token"],
            tool=tool,
            origin=origin,
        )
        if record["downstream"] != []:
            raise ProbeError("transport reached a downstream spy")
    if len(identities) != 36:
        raise ProbeError("transport tuples are not unique")


def _validate_internal_records(records: object) -> None:
    if type(records) is not list or len(records) != 29:
        raise ProbeError("internal record count drift")
    expected_keys = {
        "index",
        "seam",
        "tool",
        "origin",
        "result_adapter",
        "adapter",
        "process_id",
        "process_start_token",
        "telemetry",
        "downstream",
        "primary_model_calls",
        "dormant_model_calls",
    }
    seen: set[str] = set()
    for index, (record, expected) in enumerate(zip(records, INTERNAL_PROBES, strict=True), 1):
        if type(record) is not dict or set(record) != expected_keys:
            raise ProbeError("internal record shape drift")
        if (
            record["index"],
            record["seam"],
            record["tool"],
            record["origin"],
            record["result_adapter"],
        ) != (index, expected.seam, expected.tool, expected.origin, expected.result_adapter):
            raise ProbeError("internal record order/identity drift")
        if expected.seam in seen:
            raise ProbeError("internal seam names are not unique")
        seen.add(expected.seam)
        _validate_adapter_evidence(expected.result_adapter, expected.tool, index, record["adapter"])
        if type(record["process_id"]) is not int or record["process_id"] <= 0:
            raise ProbeError("internal PID drift")
        if type(record["process_start_token"]) is not str or _TOKEN_RE.fullmatch(record["process_start_token"]) is None:
            raise ProbeError("internal process token drift")
        _validate_record_telemetry(
            record["telemetry"],
            process_id=record["process_id"],
            process_start_token=record["process_start_token"],
            tool=expected.tool,
            origin=expected.origin,
        )
        if record["downstream"] != [] or record["dormant_model_calls"] != 0:
            raise ProbeError("internal probe reached downstream/dormant work")
        expected_primary = 2 if index in {7, 10} else 0
        if record["primary_model_calls"] != expected_primary:
            raise ProbeError("internal primary model call count drift")


def _looks_like_source(path: Path) -> bool:
    normalized = path.as_posix().casefold()
    if "/.worktrees/" in normalized or normalized.endswith("/mcp_server/src"):
        return True
    return any(
        ((candidate / ".git").exists() and (candidate / "Rook.sln").is_file() and (candidate / "mcp_server" / "src" / "rook").is_dir())
        for candidate in (path, *path.parents)
    )


def _validate_process_evidence(
    evidence: object,
    inputs: RuntimeInputs,
    *,
    allowed_roots: Iterable[Path] = (),
) -> None:
    if type(evidence) is not dict or set(evidence) != _PROCESS_KEYS:
        raise ProbeError("process evidence shape drift")
    expected_python = _canonical_path(inputs.expected_python)
    if _canonical_path(str(evidence["executable"])) != expected_python:
        raise ProbeError("installed child executable drift")
    if type(evidence["process_id"]) is not int or evidence["process_id"] <= 0:
        raise ProbeError("installed child PID drift")
    token = evidence["process_start_token"]
    if type(token) is not str or _TOKEN_RE.fullmatch(token) is None:
        raise ProbeError("installed child start token drift")
    forbidden = [_canonical_path(root) for root in inputs.forbidden_source_roots]
    allowed = [_canonical_path(root) for root in allowed_roots]
    cwd = _canonical_path(str(evidence["cwd"]))
    if any(_path_within(cwd, root) for root in forbidden) or _looks_like_source(cwd):
        raise ProbeError("installed child cwd is source-contaminated")
    if _path_within(cwd, _canonical_path(inputs.expected_venv)):
        raise ProbeError("installed child cwd is inside installed venv")
    raw_sys_path = evidence["sys_path"]
    if type(raw_sys_path) is not list or not all(type(item) is str for item in raw_sys_path):
        raise ProbeError("installed child sys.path evidence is malformed")
    for raw in raw_sys_path:
        path = _canonical_path(raw)
        if any(_path_within(path, root) for root in forbidden) or _looks_like_source(path):
            raise ProbeError(f"installed child sys.path is source-contaminated: {path}")
        if any(_path_within(path, root) for root in allowed):
            continue
    origins = evidence["rook_origins"]
    if type(origins) is not dict or "rook" not in origins or "rook.server" not in origins:
        raise ProbeError("installed child Rook origins are incomplete")
    package_root = _canonical_path(inputs.expected_package_root)
    for name, raw in origins.items():
        if type(name) is not str or type(raw) is not str or not _path_within(_canonical_path(raw), package_root):
            raise ProbeError(f"loaded Rook module escaped installed package root: {name}")


def _atomic_write_json(path: Path, value: object) -> None:
    path = Path(path)
    if not path.is_absolute():
        raise ProbeError("output path must be absolute")
    if path.exists():
        raise ProbeError("output path must be new")
    parent = _require_directory(path.parent, "output parent")
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temporary = parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise ProbeError("output path appeared during atomic write")
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _read_child_output(path: Path) -> dict[str, object]:
    path = _require_file(path, "child output")
    return _load_json_object(path, "child output")


def _current_control_projection(environment: Mapping[str, str]) -> dict[str, str]:
    return {
        name: str(value)
        for name, value in environment.items()
        if name.upper() in _CONTROLLED_EXACT or name.upper().startswith("ROOK_")
    }


def _assert_current_child_environment(*, profile: str | None, interactive: bool) -> None:
    expected = build_installed_child_environment(
        os.environ,
        profile=profile,
        interactive=interactive,
    )
    actual_projection = _current_control_projection(os.environ)
    expected_projection = _current_control_projection(expected)
    if actual_projection != expected_projection:
        raise ProbeError("installed child environment is not the closed code-owned map")
    if not sys.flags.no_user_site:
        raise ProbeError("installed child did not disable the user site")


def _loaded_rook_origins() -> dict[str, str]:
    origins: dict[str, str] = {}
    for raw_name, module in sorted(sys.modules.items()):
        name = raw_name
        if raw_name == "__main__":
            spec_name = getattr(getattr(module, "__spec__", None), "name", None)
            if type(spec_name) is str:
                name = spec_name
        if name != "rook" and not name.startswith("rook."):
            continue
        raw_file = getattr(module, "__file__", None)
        if raw_file is not None:
            origins[name] = str(_canonical_path(raw_file))
    return origins


def _normalized_sys_path() -> list[str]:
    cwd = Path.cwd()
    normalized: list[str] = []
    for raw in sys.path:
        path = cwd if raw == "" else Path(raw)
        try:
            normalized.append(str(_canonical_path(path)))
        except (OSError, RuntimeError):
            normalized.append(str(path))
    return normalized


def _collect_process_evidence() -> dict[str, object]:
    from rook.learning.metrics_store import get_metrics_store

    snapshot = get_metrics_store().get_containment_denials_snapshot()
    return {
        "executable": str(_canonical_path(sys.executable)),
        "cwd": str(_canonical_path(Path.cwd())),
        "sys_path": _normalized_sys_path(),
        "rook_origins": _loaded_rook_origins(),
        "process_id": snapshot["process_id"],
        "process_start_token": snapshot["process_start_token"],
    }


def _tool_record(tool: object) -> dict[str, object]:
    if isinstance(tool, Mapping):
        record = dict(tool)
    elif hasattr(tool, "model_dump"):
        record = tool.model_dump(by_alias=True, exclude_none=True)
    else:
        record = {
            "name": getattr(tool, "name", None),
            "description": getattr(tool, "description", None),
            "inputSchema": getattr(tool, "inputSchema", None),
        }
    if "input_schema" in record and "inputSchema" not in record:
        record["inputSchema"] = record.pop("input_schema")
    if type(record.get("name")) is not str:
        raise ProbeError("discovered tool name is malformed")
    return record


def _litellm_schema(tool: object) -> dict[str, object]:
    record = _tool_record(tool)
    return {
        "type": "function",
        "function": {
            "name": record["name"],
            "description": record.get("description") or "",
            "parameters": record.get("inputSchema")
            or {"type": "object", "properties": {}},
        },
    }


class _AllSchemasRegistry:
    def __init__(self, schemas: list[dict[str, object]]) -> None:
        self._schemas = schemas

    def get_active_schemas(self) -> list[dict[str, object]]:
        return list(self._schemas)

    def is_meta_tool(self, _name: str) -> bool:
        return False

    def get_group_names(self) -> list[str]:
        return []

    def get_active_count(self) -> int:
        return len(self._schemas)


def _projection_names(schemas: Iterable[object]) -> list[str]:
    names: list[str] = []
    for schema in schemas:
        if not isinstance(schema, Mapping):
            raise ProbeError("model projection schema is malformed")
        function = schema.get("function")
        if not isinstance(function, Mapping) or type(function.get("name")) is not str:
            raise ProbeError("model projection function is malformed")
        names.append(function["name"])
    if len(names) != len(set(names)):
        raise ProbeError("model projection contains duplicate names")
    if set(names).intersection(CONTAINED_TOOLS):
        raise ProbeError("model projection leaked a contained name")
    return sorted(names)


def _collect_model_projections(tools: Iterable[object]) -> tuple[list[str], list[str]]:
    from rook.agent.base_agent import RookAgent
    from rook.agent.chat.chat_runner import ChatRunner
    from rook.agent.config import AgentConfig

    schemas = [_litellm_schema(tool) for tool in tools]

    async def inert_executor(_name: str, _arguments: dict[str, object]) -> dict[str, object]:
        raise ProbeError("model projection executor was invoked")

    agent = RookAgent(
        config=AgentConfig(
            knowledge_injection=False,
            parameter_correction=False,
            observation_recording=False,
            tool_surface_adaptation=False,
        ),
        tool_executor=inert_executor,
        tool_schemas=schemas,
    )
    chat = ChatRunner(
        tool_executor=inert_executor,
        registry=_AllSchemasRegistry(schemas),
    )
    return (
        _projection_names(agent._get_tool_schemas()),
        _projection_names(chat._active_schemas()),
    )


def _cache_schema(name: str) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "release acceptance cache record",
            "parameters": {"type": "object", "properties": {}},
        },
    }


async def _startup_refresh_probe(server: object, cache_path: Path) -> dict[str, object]:
    from rook.agent import tool_registry
    from rook.learning.metrics_store import get_metrics_store

    store = get_metrics_store()
    cache_payload = {
        "lifecycle_fingerprint": tool_registry.lifecycle_fingerprint(),
        "catalog": {
            "safe_cached": _cache_schema("safe_cached"),
            "spawn_agent": _cache_schema("safe_embedded"),
            "safe_hidden_embedded": _cache_schema("gh_replay_recipe"),
        },
    }
    cache_bytes = (json.dumps(cache_payload, indent=2) + "\n").encode("utf-8")
    with cache_path.open("xb") as stream:
        stream.write(cache_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    cache_identity = cache_path.resolve()
    before = store.get_containment_denials_snapshot()
    calls = {"unlink": 0, "rmtree": 0}
    original_unlink = Path.unlink
    original_rmtree = shutil.rmtree

    def guarded_unlink(path: Path, *args, **kwargs):
        if Path(path).resolve() == cache_identity:
            calls["unlink"] += 1
            raise ProbeError("startup refresh attempted to unlink its cache")
        return original_unlink(path, *args, **kwargs)

    def guarded_rmtree(path, *args, **kwargs):
        target = Path(path).resolve()
        if target == cache_identity or _path_within(cache_identity, target):
            calls["rmtree"] += 1
            raise ProbeError("startup refresh attempted recursive cache deletion")
        return original_rmtree(path, *args, **kwargs)

    async def failing_loader():
        raise RuntimeError("release acceptance injected construction failure")

    Path.unlink = guarded_unlink
    shutil.rmtree = guarded_rmtree
    try:
        degraded = await tool_registry.refresh_catalog_at_startup(
            failing_loader,
            cache_path=cache_path,
        )
    finally:
        Path.unlink = original_unlink
        shutil.rmtree = original_rmtree
    after = store.get_containment_denials_snapshot()
    retained = sorted((degraded.catalog or {}).keys())
    evidence = {
        "status": degraded.status,
        "persisted": degraded.persisted,
        "refresh_requested": degraded.refresh_requested,
        "retained_names": retained,
        "cache_bytes_unchanged": cache_path.read_bytes() == cache_bytes,
        "cache_path_unchanged": cache_path.resolve() == cache_identity,
        "unlink_calls": calls["unlink"],
        "rmtree_calls": calls["rmtree"],
        "telemetry_unchanged": after == before,
        "normal_status": None,
        "normal_catalog_count": 0,
    }
    if (
        degraded.status != "degraded_cache"
        or degraded.persisted is not False
        or degraded.refresh_requested is not True
        or retained != ["safe_cached"]
        or cache_path.read_bytes() != cache_bytes
        or cache_path.resolve() != cache_identity
        or after != before
        or calls != {"unlink": 0, "rmtree": 0}
    ):
        raise ProbeError("failed startup refresh did not retain only the safe cache")

    normal = await tool_registry.refresh_catalog_at_startup(
        server._all_live_tools,
        cache_path=cache_path,
    )
    if normal.status != "fresh" or normal.persisted is not True or normal.refresh_requested is not False:
        raise ProbeError("normal installed startup refresh did not persist a fresh catalog")
    normal_names = sorted((normal.catalog or {}).keys())
    if len(normal_names) != DISCOVERY_COUNTS["unprofiled"] or set(normal_names).intersection(CONTAINED_TOOLS):
        raise ProbeError("normal startup refresh catalog drift")
    evidence["normal_status"] = normal.status
    evidence["normal_catalog_count"] = len(normal_names)
    _validate_startup_refresh(evidence)
    return evidence


async def _discovery_child(surface: str, output: Path) -> None:
    if output.exists():
        raise ProbeError("discovery child output must be new")
    if surface == "unprofiled":
        profile = None
        interactive = False
    elif surface == "interactive-full":
        profile = "full"
        interactive = True
    else:
        profile = surface
        interactive = False
    _assert_current_child_environment(profile=profile, interactive=interactive)

    from rook import server
    from rook.agent.tool_registry import refresh_catalog_at_startup
    from rook.learning.metrics_store import get_metrics_store

    store = get_metrics_store()
    telemetry_before = store.get_containment_denials_snapshot()
    startup: dict[str, object] | None = None
    cache_path = Path.cwd() / f"catalog-{surface}-{uuid.uuid4().hex}.json"
    if surface == "unprofiled":
        startup = await _startup_refresh_probe(server, cache_path)
    else:
        normal = await refresh_catalog_at_startup(server._all_live_tools, cache_path=cache_path)
        if normal.status != "fresh" or not normal.catalog:
            raise ProbeError(f"{surface} startup refresh failed")
    tools = await server.list_tools()
    names = [_tool_record(tool)["name"] for tool in tools]
    if not all(type(name) is str for name in names):
        raise ProbeError("discovery returned a malformed tool name")
    agent_names, chat_names = _collect_model_projections(tools)
    telemetry_after = store.get_containment_denials_snapshot()
    process = _collect_process_evidence()
    snapshot = {
        "surface": surface,
        "process": process,
        "profile_env_present": "ROOK_MCP_TOOL_PROFILE" in os.environ,
        "interactive_env_present": "ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING" in os.environ,
        "catalog_names": names,
        "rook_agent_names": agent_names,
        "rook_chat_names": chat_names,
        "telemetry_before": telemetry_before,
        "telemetry_after": telemetry_after,
        "startup_refresh": startup,
    }
    expected_count = DISCOVERY_COUNTS[surface]
    _validate_names(names, expected_count, f"{surface} catalog")
    _validate_names(agent_names, expected_count, f"{surface} RookAgent projection")
    _validate_names(chat_names, expected_count, f"{surface} RookChat projection")
    if set(names) != set(agent_names) or set(names) != set(chat_names):
        raise ProbeError(f"{surface} projection membership drift")
    if telemetry_before != telemetry_after:
        raise ProbeError(f"{surface} discovery emitted containment telemetry")
    if process["process_id"] != telemetry_before["process_id"] or process["process_start_token"] != telemetry_before["process_start_token"]:
        raise ProbeError(f"{surface} discovery process identity drift")
    _atomic_write_json(output, snapshot)


def _fresh_child_workspace(inputs: RuntimeInputs, label: str) -> tempfile.TemporaryDirectory[str]:
    temporary = tempfile.TemporaryDirectory(prefix=f"rook-containment-{label}-")
    root = _canonical_path(temporary.name)
    excluded = [
        _canonical_path(inputs.expected_venv),
        _canonical_path(inputs.expected_package_root),
        *(_canonical_path(path) for path in inputs.forbidden_source_roots),
    ]
    data_root = _casefold_lookup(os.environ, "ROOK_DATA_DIR")
    install_root = _casefold_lookup(os.environ, "ROOK_INSTALL_ROOT")
    for raw in (data_root, install_root):
        if raw:
            excluded.append(_canonical_path(raw))
    if any(_path_within(root, item) or _path_within(item, root) for item in excluded):
        temporary.cleanup()
        raise ProbeError("fresh child workspace overlaps a protected runtime/source root")
    return temporary


def _run_subprocess_child(
    inputs: RuntimeInputs,
    *,
    label: str,
    arguments: list[str],
    profile: str | None,
    interactive: bool = False,
) -> tuple[dict[str, object], Path]:
    with _fresh_child_workspace(inputs, label) as raw_workspace:
        workspace = _canonical_path(raw_workspace)
        output = workspace / "child-output.json"
        environment = build_installed_child_environment(
            os.environ,
            profile=profile,
            interactive=interactive,
        )
        command = [
            str(_canonical_path(inputs.expected_python)),
            str(_canonical_path(inputs.staged_script_path)),
            *arguments,
            "--output",
            str(output),
        ]
        child = subprocess.Popen(
            command,
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            stdout, stderr = child.communicate(timeout=900)
        except subprocess.TimeoutExpired as exc:
            child.kill()
            child.communicate()
            raise ProbeError(f"{label} child timed out") from exc
        if child.returncode != 0:
            raise ProbeError(f"{label} child failed ({child.returncode}): {stderr[-2000:]}")
        if stdout != "":
            raise ProbeError(f"{label} child wrote an unexpected stdout machine channel")
        if "Traceback (most recent call last)" in stderr:
            raise ProbeError(f"{label} child emitted a traceback")
        value = _read_child_output(output)
        process = value.get("process")
        _validate_process_evidence(
            process,
            inputs,
            allowed_roots=(workspace, _canonical_path(inputs.staged_script_path).parent),
        )
        if type(process) is not dict or process.get("process_id") != child.pid:
            raise ProbeError(f"{label} artifact does not match launched child PID")
        return value, workspace


def run_discovery_snapshots(inputs: RuntimeInputs) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    for surface in DISCOVERY_COUNTS:
        if surface == "unprofiled":
            profile = None
            interactive = False
        elif surface == "interactive-full":
            profile = "full"
            interactive = True
        else:
            profile = surface
            interactive = False
        value, _workspace = _run_subprocess_child(
            inputs,
            label=f"discovery-{surface}",
            arguments=["_child-discovery", "--surface", surface],
            profile=profile,
            interactive=interactive,
        )
        snapshots.append(value)
    _validate_discovery_snapshots(snapshots)
    return snapshots


@dataclass(frozen=True)
class _Patchpoint:
    identifier: str
    kind: Literal["sync", "async"]


_PATCHPOINTS = tuple(
    _Patchpoint(*item)
    for item in (
        ("rook.server.validate_arguments", "sync"),
        ("mcp.server.lowlevel.server.Server._get_cached_tool_definition", "async"),
        ("mcp.server.lowlevel.server.jsonschema.validate", "sync"),
        ("rook.server.tool_blocked", "sync"),
        ("rook.server._get_capability_index", "async"),
        ("rook.server.inject_knowledge", "async"),
        ("rook.agent.base_agent.RookAgent._call_model", "async"),
        ("rook.server.targeting.policy_for_tool", "sync"),
        ("httpx.AsyncClient.get", "async"),
        ("httpx.AsyncClient.post", "async"),
        ("httpx.AsyncClient.request", "async"),
        ("rook.bootstrap.executor.urllib.request.urlopen", "sync"),
        ("rook.server.call_rhino", "async"),
        ("rook.server._record_observation", "sync"),
        ("rook.server.get_phase_tracker", "sync"),
        ("rook.server.build_script_receipt", "sync"),
    )
)


@dataclass(frozen=True)
class _ResolvedPatchpoint:
    spec: _Patchpoint
    owner: object
    attribute: str
    descriptor: object
    original: Callable[..., Any]


def _resolve_owner(identifier: str) -> tuple[object, str]:
    parts = identifier.split(".")
    for boundary in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:boundary])
        try:
            owner: object = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name and not module_name.startswith(f"{exc.name}."):
                raise
            continue
        for part in parts[boundary:-1]:
            if not hasattr(owner, part):
                raise ProbeError(f"missing downstream spy owner: {identifier}")
            owner = getattr(owner, part)
        return owner, parts[-1]
    raise ProbeError(f"could not resolve downstream spy: {identifier}")


def _resolve_patchpoint(spec: _Patchpoint) -> _ResolvedPatchpoint:
    owner, attribute = _resolve_owner(spec.identifier)
    try:
        descriptor = inspect.getattr_static(owner, attribute)
        original = getattr(owner, attribute)
    except AttributeError as exc:
        raise ProbeError(f"missing downstream spy target: {spec.identifier}") from exc
    if not callable(original):
        raise ProbeError(f"downstream spy target is not callable: {spec.identifier}")
    actual_kind = "async" if inspect.iscoroutinefunction(original) else "sync"
    if actual_kind != spec.kind:
        raise ProbeError(f"downstream spy kind drift: {spec.identifier}")
    return _ResolvedPatchpoint(spec, owner, attribute, descriptor, original)


def _descriptor_wrapper(descriptor: object, wrapper: Callable[..., Any]) -> object:
    if isinstance(descriptor, staticmethod):
        return staticmethod(wrapper)
    if isinstance(descriptor, classmethod):
        return classmethod(wrapper)
    return wrapper


@dataclass
class _DownstreamSpyController:
    active: contextvars.ContextVar[bool]
    entries: list[str]

    @contextlib.contextmanager
    def phase(self) -> Iterator[None]:
        token = self.active.set(True)
        try:
            yield
        finally:
            self.active.reset(token)


@contextlib.contextmanager
def _downstream_spies() -> Iterator[_DownstreamSpyController]:
    active = contextvars.ContextVar("installed_probe_downstream_active", default=False)
    entries: list[str] = []
    controller = _DownstreamSpyController(active=active, entries=entries)
    resolved = [_resolve_patchpoint(spec) for spec in _PATCHPOINTS]
    installed: list[_ResolvedPatchpoint] = []
    try:
        for item in resolved:
            if item.spec.kind == "async":
                async def async_wrapper(*args, __item=item, **kwargs):
                    if active.get():
                        entries.append(__item.spec.identifier)
                        raise ProbeError(f"downstream spy reached: {__item.spec.identifier}")
                    return await __item.original(*args, **kwargs)

                wrapper = async_wrapper
            else:
                def sync_wrapper(*args, __item=item, **kwargs):
                    if active.get():
                        entries.append(__item.spec.identifier)
                        raise ProbeError(f"downstream spy reached: {__item.spec.identifier}")
                    return __item.original(*args, **kwargs)

                wrapper = sync_wrapper
            setattr(item.owner, item.attribute, _descriptor_wrapper(item.descriptor, wrapper))
            installed.append(item)

        yield controller
    finally:
        for item in reversed(installed):
            setattr(item.owner, item.attribute, item.descriptor)


def _spy_phase(controller: _DownstreamSpyController) -> contextlib.AbstractContextManager[None]:
    return controller.phase()


def _classify_call_request(request: object) -> tuple[str, str, str]:
    try:
        raw_name = request.params.name
    except AttributeError as exc:
        raise ProbeError("call-tool request shape drift") from exc
    if raw_name in CONTAINED_TOOLS:
        return "public_mcp", raw_name, "public_mcp"
    if raw_name != "rook_tools_call":
        raise ProbeError(f"unexpected call-tool request: {raw_name!r}")
    arguments = request.params.arguments
    if type(arguments) is not dict or set(arguments) != {"name", "arguments"}:
        raise ProbeError("progressive call-tool arguments drift")
    target = arguments["name"]
    if target not in CONTAINED_TOOLS or arguments["arguments"] != {}:
        raise ProbeError("progressive call-tool target drift")
    return "progressive_meta", target, "progressive_meta"


async def _transport_child(profile: str, output: Path) -> None:
    if output.exists():
        raise ProbeError("transport child output must be new")
    _assert_current_child_environment(profile=profile, interactive=False)

    from mcp import types as mcp_types
    from mcp.server.stdio import stdio_server
    from rook import server
    from rook.learning.metrics_store import get_metrics_store

    process = _collect_process_evidence()
    retained_handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    expected_calls = [
        (ingress, tool)
        for ingress in TRANSPORT_INGRESSES
        for tool in CONTAINED_TOOLS
    ]
    records: list[dict[str, object]] = []
    with _downstream_spies() as spies:
        async def probe_handler(request):
            index = len(records) + 1
            if index > len(expected_calls):
                raise ProbeError("transport received an extra call-tool request")
            ingress, tool, origin = _classify_call_request(request)
            if (ingress, tool) != expected_calls[index - 1]:
                raise ProbeError("transport call-tool ordering drift")
            store = get_metrics_store()
            before = store.get_containment_denials_snapshot()
            try:
                with _spy_phase(spies):
                    result = await retained_handler(request)
            finally:
                after = store.get_containment_denials_snapshot()
            event = _one_event_delta(before, after, tool, origin)
            if spies.entries:
                raise ProbeError("transport reached downstream work")
            records.append(
                {
                    "index": index,
                    "ingress": ingress,
                    "tool": tool,
                    "origin": origin,
                    "process_id": before["process_id"],
                    "process_start_token": before["process_start_token"],
                    "telemetry": {
                        "process_id": before["process_id"],
                        "process_start_token": before["process_start_token"],
                        "event": event,
                    },
                    "downstream": list(spies.entries),
                }
            )
            return result

        server.mcp.request_handlers[mcp_types.CallToolRequest] = probe_handler
        try:
            async with stdio_server() as (read_stream, write_stream):
                await server.mcp.run(
                    read_stream,
                    write_stream,
                    server.mcp.create_initialization_options(),
                )
        finally:
            server.mcp.request_handlers[mcp_types.CallToolRequest] = retained_handler
    if len(records) != 12:
        raise ProbeError(f"transport child completed after {len(records)} calls")
    final_process = _collect_process_evidence()
    if (
        final_process["process_id"] != process["process_id"]
        or final_process["process_start_token"] != process["process_start_token"]
    ):
        raise ProbeError("transport child process identity changed")
    _atomic_write_json(
        output,
        {
            "mode": "transport",
            "profile": profile,
            "process": final_process,
            "records": records,
        },
    )


def _parse_wire_result(tool: str, result: object) -> tuple[dict[str, object], dict[str, object]]:
    contents = getattr(result, "content", None)
    if type(contents) is not list or len(contents) != 1:
        raise ProbeError("public MCP denial must contain exactly one content item")
    content = contents[0]
    if type(getattr(content, "type", None)) is not str or content.type != "text":
        raise ProbeError("public MCP denial must contain TextContent")
    text = getattr(content, "text", None)
    expected_text = "Error: " + json.dumps(EXPECTED_DENIALS[tool], indent=2)
    if type(text) is not str or text != expected_text:
        raise ProbeError("public MCP denial text drift")
    try:
        payload = json.loads(text[len("Error: "):])
    except json.JSONDecodeError as exc:
        raise ProbeError("public MCP denial is not JSON") from exc
    denial = {"success": False, "data": payload}
    _validate_denial(tool, denial)
    wire = {
        "content_count": 1,
        "content_types": [content.type],
        "is_error": bool(getattr(result, "isError", False)),
        "text": text,
    }
    if wire["is_error"] is not False:
        raise ProbeError("public MCP handler changed the established isError protocol")
    return denial, wire


async def _run_transport_profile(inputs: RuntimeInputs, profile: str) -> list[dict[str, object]]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    with _fresh_child_workspace(inputs, f"transport-{profile}") as raw_workspace:
        workspace = _canonical_path(raw_workspace)
        output = workspace / "transport-output.json"
        environment = build_installed_child_environment(os.environ, profile=profile)
        parameters = StdioServerParameters(
            command=str(_canonical_path(inputs.expected_python)),
            args=[
                str(_canonical_path(inputs.staged_script_path)),
                "_child-transport",
                "--profile",
                profile,
                "--output",
                str(output),
            ],
            env=environment,
            cwd=str(workspace),
            encoding_error_handler="replace",
        )
        wire_results: list[tuple[dict[str, object], dict[str, object]]] = []
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errlog:
            async with stdio_client(parameters, errlog=errlog) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    for ingress in TRANSPORT_INGRESSES:
                        for tool in CONTAINED_TOOLS:
                            if ingress == "public_mcp":
                                result = await session.call_tool(tool, {})
                            else:
                                result = await session.call_tool(
                                    "rook_tools_call",
                                    {"name": tool, "arguments": {}},
                                )
                            wire_results.append(_parse_wire_result(tool, result))
            errlog.seek(0)
            stderr_text = errlog.read()
        if "Traceback (most recent call last)" in stderr_text:
            raise ProbeError("transport child emitted a traceback")
        artifact = _read_child_output(output)
        if type(artifact) is not dict or set(artifact) != {"mode", "profile", "process", "records"}:
            raise ProbeError("transport child artifact shape drift")
        if artifact["mode"] != "transport" or artifact["profile"] != profile:
            raise ProbeError("transport child artifact identity drift")
        _validate_process_evidence(
            artifact["process"],
            inputs,
            allowed_roots=(workspace, _canonical_path(inputs.staged_script_path).parent),
        )
        child_records = artifact["records"]
        if type(child_records) is not list or len(child_records) != 12:
            raise ProbeError("transport child record count drift")
        records: list[dict[str, object]] = []
        expected_child_keys = {
            "index",
            "ingress",
            "tool",
            "origin",
            "process_id",
            "process_start_token",
            "telemetry",
            "downstream",
        }
        for local_index, (child, wire_pair) in enumerate(zip(child_records, wire_results, strict=True), 1):
            if type(child) is not dict or set(child) != expected_child_keys or child["index"] != local_index:
                raise ProbeError("transport child record shape/order drift")
            denial, wire = wire_pair
            records.append(
                {
                    "index": 0,
                    "profile": profile,
                    "ingress": child["ingress"],
                    "tool": child["tool"],
                    "origin": child["origin"],
                    "denial": denial,
                    "wire": wire,
                    "process_id": child["process_id"],
                    "process_start_token": child["process_start_token"],
                    "telemetry": child["telemetry"],
                    "downstream": child["downstream"],
                }
            )
        return records


def run_transport_probes(inputs: RuntimeInputs) -> list[dict[str, object]]:
    async def run_profiles() -> list[dict[str, object]]:
        combined: list[dict[str, object]] = []
        for profile in PROFILES:
            combined.extend(await _run_transport_profile(inputs, profile))
        return combined

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        records = asyncio.run(run_profiles())
    else:
        raise ProbeError("transport parent cannot run inside an active event loop")
    for index, record in enumerate(records, 1):
        record["index"] = index
    _validate_transport_records(records)
    return records


class _InternalPoison:
    def __init__(self, label: str) -> None:
        self.label = label

    def _fail(self, action: str):
        raise ProbeError(f"internal probe reached forbidden {self.label} via {action}")

    def __getattr__(self, name: str):
        return self._fail(f"attribute {name}")

    def __call__(self, *args, **kwargs):
        return self._fail("call")

    def __bool__(self) -> bool:
        return self._fail("truth test")

    def __iter__(self):
        return self._fail("iteration")

    def __len__(self) -> int:
        return self._fail("length")

    def __getitem__(self, key: object):
        return self._fail(f"item {key!r}")


class _InternalPoisonMapping(Mapping[str, object]):
    def _fail(self, action: str):
        raise ProbeError(f"internal probe accessed parameters via {action}")

    def __getitem__(self, key: str) -> object:
        return self._fail(f"item {key!r}")

    def __iter__(self):
        return self._fail("iteration")

    def __len__(self) -> int:
        return self._fail("length")

    def __bool__(self) -> bool:
        return self._fail("truth test")

    def get(self, key: str, default: object = None) -> object:
        return self._fail(f"get {key!r}")

    def items(self):
        return self._fail("items")

    def keys(self):
        return self._fail("keys")

    def values(self):
        return self._fail("values")

    def copy(self):
        return self._fail("copy")

    def __copy__(self):
        return self._fail("shallow copy")

    def __deepcopy__(self, _memo):
        return self._fail("deep copy")


class _InternalToolOnly:
    def __init__(self, tool: str, label: str) -> None:
        self._tool = tool
        self._label = label

    @property
    def tool(self) -> str:
        return self._tool

    def __getattr__(self, name: str):
        raise ProbeError(f"internal probe read {self._label}.{name} after tool identity")


def _require_causal_history(history: object, *, tool: str, call_id: str) -> None:
    expected_tool_message = {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps(_expected_denial(tool), separators=(",", ":")),
    }
    if type(history) is not list or sum(type(message) is dict and message == expected_tool_message for message in history) != 1:
        raise ProbeError("primary continuation lacks the exact causal denial")


def _agent_response(*, tool: str | None = None, call_id: str = "", content: str | None = None) -> SimpleNamespace:
    calls: list[SimpleNamespace] = []
    if tool is not None:
        calls.append(
            SimpleNamespace(
                id=call_id,
                type="function",
                function=SimpleNamespace(name=tool, arguments='{"probe":true}'),
            )
        )
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(role="assistant", content=content, tool_calls=calls)
            )
        ],
        usage=None,
    )


def _chat_tool_stream(tool: str, call_id: str):
    async def stream():
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id=call_id,
                                function=SimpleNamespace(name=tool, arguments='{"probe":true}'),
                            )
                        ],
                    )
                )
            ],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )

    return stream()


def _chat_text_stream():
    async def stream():
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="continued after containment",
                        tool_calls=None,
                    )
                )
            ],
            usage=None,
        )
        yield SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )

    return stream()


def _internal_agent_config():
    from rook.agent.config import AgentConfig

    return AgentConfig(
        max_turns=3,
        max_tool_calls_per_turn=2,
        knowledge_injection=False,
        parameter_correction=False,
        observation_recording=False,
        tool_surface_adaptation=False,
    )


@dataclass(frozen=True)
class _PreparedInternalProbe:
    invoke: Callable[[], object]
    is_async: bool
    primary_model_calls: Callable[[], int] | None
    serialize: Callable[[object], dict[str, object]]


def _qualified_type(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _serialize_dictionary(value: object, tool: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ProbeError("dictionary adapter returned a non-dict outer type")
    _validate_denial(tool, value)
    return {"outer_type": "builtins.dict", "value": value}


def _serialize_investigation(value: object, tool: str) -> dict[str, object]:
    from rook.learning.investigator import InvestigationResult

    if type(value) is not InvestigationResult:
        raise ProbeError("investigation adapter outer type drift")
    evidence = {
        "outer_type": _qualified_type(value),
        "gap_id": value.gap_id,
        "tool": value.tool,
        "patterns_discovered": value.patterns_discovered,
        "antipatterns_discovered": value.antipatterns_discovered,
        "experiments": value.experiments,
        "gap_resolved": value.gap_resolved,
        "resolution": value.resolution,
        "new_gaps": value.new_gaps,
        "insights": value.insights,
        "containment_denial": value.containment_denial,
    }
    _validate_denial(tool, evidence["containment_denial"])
    return evidence


def _serialize_experiment(value: object, tool: str) -> dict[str, object]:
    from rook.learning.investigator import ExperimentResult

    if type(value) is not ExperimentResult:
        raise ProbeError("experiment adapter outer type drift")
    evidence = {
        "outer_type": _qualified_type(value),
        "tool": value.tool,
        "params": value.params,
        "success": value.success,
        "response": value.response,
        "error": value.error,
        "error_category": value.error_category,
        "execution_time_ms": value.execution_time_ms,
    }
    _validate_denial(tool, evidence["response"])
    return evidence


def _serialize_hybrid(value: object, tool: str) -> dict[str, object]:
    from rook.learning.hybrid_investigator import HybridInvestigationResult

    if type(value) is not HybridInvestigationResult:
        raise ProbeError("hybrid investigation adapter outer type drift")
    serialized = value.to_dict()
    evidence = {
        "outer_type": _qualified_type(value),
        "tool": value.tool,
        "success": value.success,
        "hypotheses_generated": value.hypotheses_generated,
        "diagnosis": value.diagnosis,
        "reasoning_trace": value.reasoning_trace,
        "hypothesis_selected": value.hypothesis_selected,
        "fix_selected": value.fix_selected,
        "patterns_discovered": value.patterns_discovered,
        "antipatterns_discovered": value.antipatterns_discovered,
        "insights": value.insights,
        "consolidation_action": value.consolidation_action,
        "workflow_detected": value.workflow_detected,
        "nuanced_reward": value.nuanced_reward,
        "visually_verified": value.visually_verified,
        "visual_description": value.visual_description,
        "viewport_hash_before": value.viewport_hash_before,
        "viewport_hash_after": value.viewport_hash_after,
        "gap_id": value.gap_id,
        "gap_resolved": value.gap_resolved,
        "resolution": value.resolution,
        "new_gaps": value.new_gaps,
        "attempts": value.attempts,
        "time_ms": value.time_ms,
        "containment_denial": value.containment_denial,
        "serialized_containment_denial": serialized.get("containment_denial"),
    }
    _validate_denial(tool, evidence["containment_denial"])
    _validate_denial(tool, evidence["serialized_containment_denial"])
    return evidence


def _serialize_explorer(value: object, tool: str) -> dict[str, object]:
    from rook.explorer.executor import ExecutionResult

    if type(value) is not ExecutionResult:
        raise ProbeError("explorer adapter outer type drift")
    evidence = {
        "outer_type": _qualified_type(value),
        "tool_name": value.tool_name,
        "params": value.params,
        "success": value.success,
        "response": value.response,
        "error": value.error,
        "duration_ms": value.duration_ms,
    }
    _validate_denial(tool, evidence["response"])
    return evidence


@contextlib.contextmanager
def _prepare_internal_probe(
    spec: InternalProbe,
    index: int,
    *,
    loop: asyncio.AbstractEventLoop,
    server: object,
) -> Iterator[_PreparedInternalProbe]:
    seam = spec.seam
    tool = spec.tool
    poison = _InternalPoisonMapping()

    async def inert_executor(_name: str, _params: object):
        raise ProbeError("internal probe reached its inert executor")

    with contextlib.ExitStack() as stack:
        if seam == "server._call_tool_dispatch":
            async def invoke():
                return await server._call_tool_dispatch(tool, poison)

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam == "server._mcp_tool_executor":
            async def invoke():
                return await server._mcp_tool_executor(tool, poison)

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam.startswith("ToolDispatcher."):
            from rook.agent.tool_dispatcher import ToolDispatcher

            dispatcher = ToolDispatcher()
            method_name = seam.split(".", 1)[1]

            async def invoke():
                method = getattr(dispatcher, method_name)
                if method_name == "dispatch":
                    return await method(tool, poison)
                return await method(tool, poison, None)

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam in {"RookAgent._execute_tool", "RookAgent._execute_local_tool"}:
            from rook.agent.base_agent import RookAgent

            agent = RookAgent(config=_internal_agent_config(), tool_executor=inert_executor)
            method_name = seam.split(".", 1)[1]

            async def invoke():
                return await getattr(agent, method_name)(tool, poison)

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam == "RookAgent._run_loop":
            from rook.agent.base_agent import RookAgent

            agent = RookAgent(config=_internal_agent_config(), tool_executor=inert_executor)
            agent.messages.append({"role": "user", "content": "exercise installed containment"})
            call_id = f"probe-agent-{index}"
            calls = {"count": 0}
            causal = {"valid": False}
            event_types: list[str] = []
            unsubscribe = agent.subscribe(lambda event: event_types.append(event.type))
            stack.callback(unsubscribe)

            async def primary_model(context):
                calls["count"] += 1
                if calls["count"] == 1:
                    return _agent_response(tool=tool, call_id=call_id)
                if calls["count"] == 2:
                    _require_causal_history(context, tool=tool, call_id=call_id)
                    causal["valid"] = True
                    return _agent_response(content="continued after containment")
                raise ProbeError("RookAgent primary model exceeded two calls")

            agent._call_model = primary_model
            agent._track_usage = lambda _response: None

            async def invoke():
                return await agent._run_loop()

            def serialize(value: object) -> dict[str, object]:
                if value is not None or calls["count"] != 2 or not causal["valid"]:
                    raise ProbeError("RookAgent loop protocol drift")
                evidence = {
                    "outer_type": "builtins.NoneType",
                    "return_is_none": True,
                    "history": agent.messages,
                    "loop": {
                        "tool_calls": 1,
                        "successful_tools": 0,
                        "tool_start_events": sum(item == "tool_execution_start" for item in event_types),
                        "tool_end_events": sum(item == "tool_execution_end" for item in event_types),
                        "adaptations": 0,
                        "observations": 0,
                        "failure_count_entries": len(agent._failure_counts),
                    },
                }
                _validate_adapter_evidence(spec.result_adapter, tool, index, evidence)
                return evidence

            yield _PreparedInternalProbe(invoke, True, lambda: calls["count"], serialize)
            return

        if seam == "ChatRunner.run_turn":
            from rook.agent.chat import chat_runner as chat_runner_module
            from rook.agent.chat.chat_runner import ChatRunner
            from rook.agent.chat.conversation_store import Conversation

            runner = ChatRunner(tool_executor=inert_executor, registry=_AllSchemasRegistry([]))
            conversation = Conversation(id=f"probe-chat-{index}", persona="worker", model="probe-model")
            call_id = f"probe-chat-{index}"
            calls = {"count": 0}
            causal = {"valid": False}
            events: list[str] = []

            async def primary_provider(**kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    return _chat_tool_stream(tool, call_id)
                if calls["count"] == 2:
                    _require_causal_history(kwargs.get("messages"), tool=tool, call_id=call_id)
                    causal["valid"] = True
                    return _chat_text_stream()
                raise ProbeError("RookChat primary model exceeded two calls")

            async def runtime_facts(**_kwargs):
                return {
                    "rhino": {"connected": False},
                    "prompt": {"available": False},
                    "verified_runtime_facts": [],
                }

            original_provider = chat_runner_module.litellm.acompletion
            original_facts = chat_runner_module.collect_runtime_facts
            chat_runner_module.litellm.acompletion = primary_provider
            chat_runner_module.collect_runtime_facts = runtime_facts
            stack.callback(setattr, chat_runner_module.litellm, "acompletion", original_provider)
            stack.callback(setattr, chat_runner_module, "collect_runtime_facts", original_facts)

            async def invoke():
                stream = runner.run_turn(
                    conversation,
                    "exercise installed containment",
                    system_prompt="release acceptance",
                )
                if not inspect.isasyncgen(stream):
                    raise ProbeError("RookChat run_turn did not return an async generator")
                async for event in stream:
                    events.append(event.type)
                return stream

            def serialize(value: object) -> dict[str, object]:
                if not inspect.isasyncgen(value) or calls["count"] != 2 or not causal["valid"]:
                    raise ProbeError("RookChat loop protocol drift")
                evidence = {
                    "outer_type": "builtins.async_generator",
                    "history": conversation.messages,
                    "events": events,
                    "loop": {
                        "tool_calls": 1,
                        "successful_tools": 0,
                        "tool_start_events": events.count("tool_start"),
                        "tool_result_events": events.count("tool_result"),
                        "error_events": events.count("error"),
                        "tools_used": [],
                        "surface_adaptations": 0,
                        "meta_only_diagnoses": 0,
                        "stuck_diagnoses": 0,
                    },
                }
                _validate_adapter_evidence(spec.result_adapter, tool, index, evidence)
                return evidence

            yield _PreparedInternalProbe(invoke, True, lambda: calls["count"], serialize)
            return

        if seam == "rook.agent.plan_graph_live.apply_live_producer_node":
            from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult, apply_live_producer_node
            from rook.learning.plan_graph import PlanGraph, PlanGraphNode
            from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY

            node_id = "containment-producer"
            node = PlanGraphNode(
                id=node_id,
                intent="exercise installed containment",
                execution_ref=f"{tool}:v1",
                metadata={OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer", EXECUTION_PARAMS_KEY: poison},
            )
            node.status = "ready"
            graph = PlanGraph(nodes={node_id: node})

            async def forbidden_dispatch(_name: str, _params: dict):
                raise ProbeError("plan graph containment reached dispatch")

            async def invoke():
                return await apply_live_producer_node(graph, node_id, forbidden_dispatch)

            def serialize(value: object) -> dict[str, object]:
                if type(value) is not LiveProducerResult:
                    raise ProbeError("plan graph adapter outer type drift")
                evidence = {
                    "outer_type": _qualified_type(value),
                    "graph_unchanged": value.graph is graph,
                    "applied": value.applied,
                    "node_id": value.node_id,
                    "tool_name": value.tool_name,
                    "outcome_status": value.outcome_status,
                    "reason": value.reason,
                }
                _validate_adapter_evidence(spec.result_adapter, tool, index, evidence)
                return evidence

            yield _PreparedInternalProbe(invoke, True, None, serialize)
            return

        if seam in {"server._handle_spawn_agent", "server._handle_plan_and_execute"}:
            method = getattr(server, seam.split(".", 1)[1])

            async def invoke():
                return await method(poison)

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam in {"BootstrapRunner.run_test", "BootstrapRunner._mock_executor"}:
            from rook.bootstrap.runner import BootstrapRunner, TestResult

            runner = object.__new__(BootstrapRunner)
            runner.tool_executor = _InternalPoison("bootstrap tool executor")
            runner.completed_tests = set()
            if seam == "BootstrapRunner.run_test":
                def invoke():
                    return runner.run_test(_InternalToolOnly(tool, "bootstrap test"))

                def serialize(value: object) -> dict[str, object]:
                    if type(value) is not TestResult:
                        raise ProbeError("bootstrap adapter outer type drift")
                    timestamp_valid = False
                    if type(value.timestamp) is str and _TIMESTAMP_RE.fullmatch(value.timestamp):
                        try:
                            datetime.strptime(value.timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
                            timestamp_valid = True
                        except ValueError:
                            pass
                    evidence = {
                        "outer_type": _qualified_type(value),
                        "test_id": value.test_id,
                        "tool": value.tool,
                        "params": value.params,
                        "expected": value.expected.value,
                        "actual": value.actual.value,
                        "response": value.response,
                        "error_message": value.error_message,
                        "duration_ms": value.duration_ms,
                        "timestamp_valid": timestamp_valid,
                        "created_object_ids": value.created_object_ids,
                        "completed_tests": sorted(runner.completed_tests),
                    }
                    _validate_adapter_evidence(spec.result_adapter, tool, index, evidence)
                    return evidence

                yield _PreparedInternalProbe(invoke, False, None, serialize)
            else:
                def invoke():
                    return runner._mock_executor(tool, poison)

                yield _PreparedInternalProbe(invoke, False, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam == "bootstrap.HttpExecutor.execute":
            from rook.bootstrap.executor import HttpExecutor

            executor = HttpExecutor(base_url="http://127.0.0.1:9")

            def invoke():
                return executor.execute(tool, poison)

            yield _PreparedInternalProbe(invoke, False, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam == "bootstrap.create_mock_executor.callable":
            from rook.bootstrap.executor import create_mock_executor

            executor = create_mock_executor()

            def invoke():
                return executor(tool, poison)

            yield _PreparedInternalProbe(invoke, False, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam == "learning.create_tool_executor.callable":
            from rook.learning.agent import create_tool_executor

            executor = loop.run_until_complete(create_tool_executor())

            async def invoke():
                return await executor(tool, poison)

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_dictionary(value, tool))
            return

        if seam.startswith("Investigator."):
            from rook.learning.investigator import Investigator

            investigator = object.__new__(Investigator)
            investigator.kg = _InternalPoison("investigator knowledge graph")
            investigator.executor = _InternalPoison("investigator executor")
            investigator.context = _InternalPoison("investigator exploration context")
            investigator._current_phase = _InternalPoison("investigator phase")
            method_name = seam.split(".", 1)[1]

            async def invoke():
                if method_name == "investigate_tool":
                    return await investigator.investigate_tool(tool)
                if method_name == "investigate_gap":
                    return await investigator.investigate_gap(_InternalToolOnly(tool, "investigator gap"))
                if method_name == "investigate_workflow":
                    return await investigator.investigate_workflow(
                        [("rhino_ping", poison), (tool, poison)],
                        "exercise installed containment",
                    )
                return await investigator._run_experiment(tool, poison)

            serializer = _serialize_experiment if spec.result_adapter == "experiment_result" else _serialize_investigation
            yield _PreparedInternalProbe(invoke, True, None, lambda value: serializer(value, tool))
            return

        if seam.startswith("HybridInvestigator."):
            from rook.learning.hybrid_investigator import HybridInvestigator

            investigator = object.__new__(HybridInvestigator)
            investigator.kg = _InternalPoison("hybrid investigator knowledge graph")
            investigator.executor = _InternalPoison("hybrid investigator executor")
            investigator.use_dspy = True
            investigator.use_visual_verification = True
            investigator.verifier = _InternalPoison("hybrid viewport verifier")
            investigator._geometry_ids = _InternalPoisonMapping()
            investigator._init_dspy_modules = _InternalPoison("hybrid DSPy initialization")
            investigator.hypothesis_selector = _InternalPoison("hybrid hypothesis selector")
            investigator.fix_selector = _InternalPoison("hybrid fix selector")
            investigator.training_buffer = _InternalPoison("hybrid training buffer")
            method_name = seam.split(".", 1)[1]

            async def invoke():
                if method_name == "investigate_tool":
                    return await investigator.investigate_tool(tool)
                return await investigator.investigate_gap(_InternalToolOnly(tool, "hybrid gap"))

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_hybrid(value, tool))
            return

        if seam == "LearningSession.run_investigation_cycle.tool_target":
            from rook.learning.session import LearningSession

            session = object.__new__(LearningSession)
            session.use_hybrid = False
            session.progress = _InternalPoison("learning progress")
            session.reporter = _InternalPoison("learning reporter")
            session.investigator = _InternalPoison("learning investigator")
            session.hybrid_investigator = _InternalPoison("hybrid learning investigator")
            session.kg = _InternalPoison("learning knowledge graph")

            async def invoke():
                return await session.run_investigation_cycle(f"tool:{tool}")

            yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_investigation(value, tool))
            return

        if seam.startswith("explorer."):
            from rook.explorer.executor import HttpExecutor, MockExecutor

            executor = HttpExecutor(base_url="http://127.0.0.1:9") if ".HttpExecutor." in seam else MockExecutor()
            method_name = seam.rsplit(".", 1)[1]
            if method_name == "execute":
                async def invoke():
                    return await executor.execute(tool, poison)

                yield _PreparedInternalProbe(invoke, True, None, lambda value: _serialize_explorer(value, tool))
            else:
                def invoke():
                    return executor.execute_sync(tool, poison)

                yield _PreparedInternalProbe(invoke, False, None, lambda value: _serialize_explorer(value, tool))
            return

        raise ProbeError(f"unsupported internal seam: {seam}")


def _internal_child(probe_index: int, output: Path) -> None:
    if output.exists():
        raise ProbeError("internal child output must be new")
    if probe_index < 1 or probe_index > len(INTERNAL_PROBES):
        raise ProbeError("internal probe index is out of range")
    _assert_current_child_environment(profile=None, interactive=False)

    from rook import server
    from rook.learning.metrics_store import get_metrics_store

    spec = INTERNAL_PROBES[probe_index - 1]
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with _downstream_spies() as spies:
            with _prepare_internal_probe(spec, probe_index, loop=loop, server=server) as prepared:
                store = get_metrics_store()
                before = store.get_containment_denials_snapshot()
                with _spy_phase(spies):
                    if prepared.is_async:
                        value = loop.run_until_complete(prepared.invoke())
                    else:
                        value = prepared.invoke()
                    if inspect.isawaitable(value):
                        raise ProbeError("synchronous internal adapter returned an awaitable")
                    adapter = prepared.serialize(value)
                after = store.get_containment_denials_snapshot()
                event = _one_event_delta(before, after, spec.tool, spec.origin)
                if spies.entries:
                    raise ProbeError("internal probe reached downstream work")
                if prepared.primary_model_calls is None:
                    primary_calls = sum(
                        entry == "rook.agent.base_agent.RookAgent._call_model"
                        for entry in spies.entries
                    )
                else:
                    primary_calls = prepared.primary_model_calls()
                dormant_calls = len(spies.entries)
    finally:
        asyncio.set_event_loop(None)
        loop.close()
    process = _collect_process_evidence()
    if process["process_id"] != before["process_id"] or process["process_start_token"] != before["process_start_token"]:
        raise ProbeError("internal child process identity changed")
    record = {
        "index": probe_index,
        "seam": spec.seam,
        "tool": spec.tool,
        "origin": spec.origin,
        "result_adapter": spec.result_adapter,
        "adapter": adapter,
        "process_id": before["process_id"],
        "process_start_token": before["process_start_token"],
        "telemetry": {
            "process_id": before["process_id"],
            "process_start_token": before["process_start_token"],
            "event": event,
        },
        "downstream": [],
        "primary_model_calls": primary_calls,
        "dormant_model_calls": dormant_calls,
    }
    _validate_adapter_evidence(spec.result_adapter, spec.tool, probe_index, adapter)
    expected_primary = 2 if probe_index in {7, 10} else 0
    if primary_calls != expected_primary:
        raise ProbeError("internal primary model count drift")
    _atomic_write_json(
        output,
        {"mode": "internal", "process": process, "record": record},
    )


def run_internal_probes(inputs: RuntimeInputs) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for index in range(1, 30):
        value, _workspace = _run_subprocess_child(
            inputs,
            label=f"internal-{index:02d}",
            arguments=["_child-internal", "--probe-index", str(index)],
            profile=None,
        )
        if type(value) is not dict or set(value) != {"mode", "process", "record"} or value["mode"] != "internal":
            raise ProbeError("internal child artifact shape drift")
        record = value["record"]
        if type(record) is not dict or record.get("index") != index:
            raise ProbeError("internal child record identity drift")
        process = value["process"]
        if type(process) is not dict or record.get("process_id") != process.get("process_id"):
            raise ProbeError("internal record/process PID drift")
        if record.get("process_start_token") != process.get("process_start_token"):
            raise ProbeError("internal record/process start token drift")
        records.append(record)
    _validate_internal_records(records)
    return records


def run_all(inputs: RuntimeInputs, output_path: Path) -> dict[str, object]:
    """Run the fixed installed campaign and atomically publish only a pass."""
    output_path = Path(output_path)
    if not output_path.is_absolute():
        raise ProbeError("result output must be absolute")
    if output_path.exists():
        raise ProbeError("result output must be new")
    _require_directory(output_path.parent, "result output parent")
    runtime = validate_installed_runtime(inputs)
    discovery = run_discovery_snapshots(inputs)
    _validate_discovery_snapshots(discovery)
    transport = run_transport_probes(inputs)
    _validate_transport_records(transport)
    internal = run_internal_probes(inputs)
    _validate_internal_records(internal)
    result = {
        "schema_version": SCHEMA_VERSION,
        "success": True,
        "runtime": runtime,
        "discovery": discovery,
        "transport": transport,
        "internal": internal,
    }
    _atomic_write_json(output_path, result)
    return result


def _runtime_inputs_from_args(arguments: argparse.Namespace) -> RuntimeInputs:
    return RuntimeInputs(
        expected_release_sha=arguments.expected_release_sha,
        expected_version=arguments.expected_version,
        expected_python=arguments.expected_python,
        expected_venv=arguments.expected_venv,
        expected_package_root=arguments.expected_package_root,
        packaged_runtime_manifest=arguments.packaged_runtime_manifest,
        installed_runtime_manifest=arguments.installed_runtime_manifest,
        install_state=arguments.install_state,
        packaged_wheelhouse=arguments.packaged_wheelhouse,
        forbidden_source_roots=tuple(arguments.forbidden_source_root),
        staged_script_path=Path(__file__).resolve(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "run":
            run_all(_runtime_inputs_from_args(arguments), arguments.output)
        elif arguments.command == "_child-discovery":
            asyncio.run(_discovery_child(arguments.surface, arguments.output))
        elif arguments.command == "_child-transport":
            asyncio.run(_transport_child(arguments.profile, arguments.output))
        elif arguments.command == "_child-internal":
            _internal_child(arguments.probe_index, arguments.output)
        else:
            raise ProbeError(f"unsupported command: {arguments.command}")
    except (ProbeError, OSError, RuntimeError, ValueError) as exc:
        print(f"installed containment probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
