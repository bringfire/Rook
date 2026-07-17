"""Authorized release-acceptance preservation checks for supported host tools.

This module is an installed command-line gate.  It is deliberately absent from
MCP registration and model catalogs.  Each invocation owns a fresh Rhino
process and scratch target, asks for one byte-exact authorization response, and
emits canonical evidence for the bounded supported-tool workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .tool_lifecycle import contained_names


SCHEMA_VERSION = 1
SCENARIOS = ("rhino", "grasshopper")
FAILURE_LABELS = (
    "runtime_origin_invalid",
    "launch_failed",
    "readiness_failed",
    "fixture_invalid",
    "preflight_blocked",
    "authorization_rejected",
    "state_drift",
    "mutation_failed",
    "verification_failed",
    "ownership_ambiguous",
    "restoration_failed",
    "telemetry_changed",
    "cleanup_failed",
)
RESULT_FIELDS = (
    "schema_version",
    "scenario",
    "success",
    "failure_label",
    "run_id",
    "started_at",
    "ended_at",
    "runtime",
    "target",
    "authorization",
    "pre_state",
    "operations",
    "verification",
    "restoration",
    "telemetry",
    "artifacts",
    "diagnostics",
)
RHINO_TOOL_ALLOWLIST = frozenset(
    {
        "rhino_ping",
        "rhino_document",
        "rhino_objects",
        "rhino_geometry",
        "rhino_document_ops",
        "rhino_create",
        "rhino_execute",
        "rhino_delete",
    }
)
GRASSHOPPER_TOOL_ALLOWLIST = frozenset(
    {
        "rhino_ping",
        "rhino_document",
        "rhino_command",
        "gh_status",
        "gh_document_open",
        "gh_library",
        "gh_snapshot",
        "gh_edit",
        "gh_errors",
        "gh_undo",
    }
)
ADMITTED_TOOL_NAMES = RHINO_TOOL_ALLOWLIST | GRASSHOPPER_TOOL_ALLOWLIST
CONTAINED_IDENTITIES = tuple(sorted(contained_names()))
SPHERE_COMPONENT_GUID = "dabc854d-f50e-408a-b001-d043c7de151d"
FIXTURE_SIZE = 2708
FIXTURE_SHA256 = "2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df"
OWNERSHIP_MARKER = ".rook-containment-owner.json"
RUNTIME_SERIAL_CODE = (
    "import Rhino\n"
    "print('ROOK_DOC_RUNTIME_SERIAL={0}'.format("
    "Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber))"
)
AUTHORIZATION_LABELS = {
    "rhino": "Rook containment Rhino scratch document",
    "grasshopper": "Rook containment Grasshopper scratch definition",
}
_DESCRIPTIONS = {
    "rhino": {
        "mutation": "Save the fresh owned Rhino document, create one radius-4 sphere and one marked point using admitted typed and scripted tools.",
        "verification": "Verify exact object identities, names, types, coordinates, sphere radius and bounds, and clean document state.",
        "restoration": "Delete only the two gate-owned objects, save the empty scratch document, close the owned process gracefully, and remove the scratch file and discovery record.",
    },
    "grasshopper": {
        "mutation": "Bootstrap Grasshopper in the fresh owned Rhino process, open the packaged empty scratch definition, and create one configured radius slider wired to one built-in Sphere.",
        "verification": "Verify exact component identities, slider settings, wire topology, solved sphere output, and zero Grasshopper errors or warnings.",
        "restoration": "Undo only the gate-owned edit to the declared empty projection, close the owned process, and remove the scratch definition and discovery record.",
    },
}
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.ASCII | re.IGNORECASE,
)
_MAX_AUTHORIZATION_BYTES = 8192


class LiveGateError(RuntimeError):
    """The live preservation contract could not be satisfied."""


class PreOwnershipBlocked(LiveGateError):
    """The artifact path was rejected before the gate claimed it."""


class OwnershipAmbiguous(LiveGateError):
    """The gate can no longer prove that a host belongs to this run."""


class FinalEvidenceWriteError(LiveGateError):
    """The final evidence pair could not be persisted atomically."""


class _ScenarioFailure(LiveGateError):
    def __init__(self, label: str, detail: str):
        if label not in FAILURE_LABELS:
            raise ValueError(f"invalid failure label: {label}")
        self.label = label
        super().__init__(detail)


@dataclass
class LiveScenarioResult:
    schema_version: int
    scenario: str
    success: bool
    failure_label: str | None
    run_id: str
    started_at: str
    ended_at: str
    runtime: dict[str, Any] | None
    target: dict[str, Any] | None
    authorization: dict[str, Any] | None
    pre_state: dict[str, Any] | None
    operations: list[dict[str, Any]]
    verification: dict[str, Any]
    restoration: dict[str, Any]
    telemetry: dict[str, Any] | None
    artifacts: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _RunState:
    scenario: str
    run_id: str
    artifact_dir: Path
    rhino_exe: Path
    started_at: str
    result: LiveScenarioResult
    process: Any = None
    discovery: Any = None
    record: Any = None
    adapter: Any = None
    scratch_path: Path | None = None
    metrics_store: Any = None
    telemetry_before: dict[str, Any] | None = None
    authorized: bool = False
    mutation_started: bool = False
    ownership_certain: bool = True
    created_rhino_ids: list[str] | None = None
    gh_edit_applied: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_run_id() -> str:
    return uuid.uuid4().hex


def _new_nonce() -> str:
    return uuid.uuid4().hex


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_value(payload: object) -> str:
    return _sha256_bytes(_canonical_json_bytes(payload))


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _emit_jsonl(payload: Mapping[str, Any]) -> None:
    line = _canonical_json_bytes(dict(payload)) + b"\n"
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(line)
        buffer.flush()
    else:
        sys.stdout.write(line.decode("utf-8"))
        sys.stdout.flush()


def _bounded_detail(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".replace("\r", " ").replace("\n", " ")
    return text if len(text) <= 1000 else text[:997] + "..."


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _claim_artifact_directory(path: Path, run_id: str) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raise PreOwnershipBlocked("artifact directory must be absolute")
    parent = raw.parent
    if not parent.is_dir() or _is_reparse(parent):
        raise PreOwnershipBlocked("artifact directory parent is missing or reparse-backed")
    if raw.exists() and (_is_reparse(raw) or not raw.is_dir()):
        raise PreOwnershipBlocked("artifact directory is not a plain directory")
    created = False
    if not raw.exists():
        try:
            raw.mkdir()
            created = True
        except OSError as exc:
            raise PreOwnershipBlocked("artifact directory could not be created") from exc
    try:
        if any(raw.iterdir()):
            raise PreOwnershipBlocked("artifact directory must be new and empty")
        marker = raw / OWNERSHIP_MARKER
        payload = _canonical_json_bytes(
            {"process_id": os.getpid(), "run_id": run_id, "schema_version": SCHEMA_VERSION}
        )
        try:
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise PreOwnershipBlocked("artifact directory ownership claim failed") from exc
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if set(raw.iterdir()) != {marker}:
            try:
                marker.unlink()
            except OSError:
                pass
            raise PreOwnershipBlocked("artifact directory changed during ownership claim")
        return raw.resolve()
    except BaseException:
        if created:
            try:
                raw.rmdir()
            except OSError:
                pass
        raise


def _artifact_record(path: Path, root: Path, kind: str) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise LiveGateError("artifact path escapes the owned directory") from exc
    payload = resolved.read_bytes()
    return {
        "kind": kind,
        "relative_path": relative,
        "sha256": _sha256_bytes(payload),
        "size": len(payload),
    }


def _register_artifact(result: LiveScenarioResult, path: Path, root: Path, kind: str) -> None:
    record = _artifact_record(path, root, kind)
    result.artifacts = [
        item for item in result.artifacts if item["relative_path"] != record["relative_path"]
    ]
    result.artifacts.append(record)


def _fixture_resource_path() -> Path:
    return Path(__file__).resolve().parent / "resources" / "containment_empty.ghx"


def _validate_fixture_bytes(payload: bytes) -> None:
    if len(payload) != FIXTURE_SIZE or _sha256_bytes(payload) != FIXTURE_SHA256:
        raise LiveGateError("fixture length or SHA-256 drift")
    if payload.startswith(b"\xef\xbb\xbf") or b"\r" in payload:
        raise LiveGateError("fixture encoding or newline drift")
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise LiveGateError("fixture final newline drift")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LiveGateError("fixture is not UTF-8") from exc
    if (
        '<chunk name="DefinitionObjects">' not in text
        or '<item name="ObjectCount" type_name="gh_int32" type_code="3">0</item>' not in text
        or '<chunks count="0"></chunks>' not in text
    ):
        raise LiveGateError("fixture empty XML projection drift")


def _rhino_sphere_arguments(run_id: str) -> dict[str, Any]:
    if _TOKEN_RE.fullmatch(run_id) is None:
        raise LiveGateError("invalid run identifier")
    return {
        "type": "SPHERE",
        "center": [0, 0, 0],
        "radius": 4,
        "name": f"RookContainmentSphere-{run_id}",
    }


def _rhino_point_script(run_id: str) -> str:
    if _TOKEN_RE.fullmatch(run_id) is None:
        raise LiveGateError("invalid run identifier")
    return (
        "import Rhino\n"
        "import scriptcontext as sc\n"
        "point = Rhino.Geometry.Point3d(10.0, 0.0, 0.0)\n"
        "attributes = Rhino.DocObjects.ObjectAttributes()\n"
        f'attributes.Name = "RookContainmentPoint-{run_id}"\n'
        "object_id = sc.doc.Objects.AddPoint(point, attributes)\n"
        "sc.doc.Views.Redraw()\n"
        'print("ROOK_POINT_ID={0}".format(object_id))'
    )


def _grasshopper_edit_arguments(run_id: str, epoch: int) -> dict[str, Any]:
    if _TOKEN_RE.fullmatch(run_id) is None or type(epoch) is not int:
        raise LiveGateError("invalid Grasshopper edit identity")
    return {
        "epoch": epoch,
        "create": [
            {
                "temp_id": "T1",
                "type": "slider",
                "nick": f"RookContainmentRadius-{run_id}",
                "min": 1,
                "max": 9,
                "value": 4,
                "pos": [100, 100],
            },
            {
                "temp_id": "T2",
                "guid": SPHERE_COMPONENT_GUID,
                "pos": [400, 100],
            },
        ],
        "connect": ["T1.O0>T2.I1"],
    }


def _build_authorization_challenge(
    *,
    scenario: str,
    run_id: str,
    nonce: str,
    target: Mapping[str, Any],
) -> dict[str, Any]:
    if scenario not in SCENARIOS or _TOKEN_RE.fullmatch(run_id) is None or _TOKEN_RE.fullmatch(nonce) is None:
        raise LiveGateError("invalid authorization identity")
    expected_target_keys = {"label", "process_id", "port", "scratch_path"}
    target_copy = dict(target)
    if set(target_copy) != expected_target_keys:
        raise LiveGateError("authorization target schema drift")
    descriptions = _DESCRIPTIONS[scenario]
    target_sha = _sha256_value(target_copy)
    mutation_sha = _sha256_bytes(descriptions["mutation"].encode("utf-8"))
    verification_sha = _sha256_bytes(descriptions["verification"].encode("utf-8"))
    restoration_sha = _sha256_bytes(descriptions["restoration"].encode("utf-8"))
    response = (
        f"AUTHORIZE scenario={scenario} run={run_id} nonce={nonce} "
        f"target={target_sha} mutation={mutation_sha} "
        f"verify={verification_sha} restore={restoration_sha}"
    )
    return {
        "type": "authorization_required",
        "schema_version": SCHEMA_VERSION,
        "scenario": scenario,
        "run_id": run_id,
        "nonce": nonce,
        "target": target_copy,
        "target_sha256": target_sha,
        "mutation": descriptions["mutation"],
        "mutation_sha256": mutation_sha,
        "verification": descriptions["verification"],
        "verification_sha256": verification_sha,
        "restoration": descriptions["restoration"],
        "restoration_sha256": restoration_sha,
        "required_response": response,
    }


def _read_authorization_line() -> str:
    line = sys.stdin.readline(_MAX_AUTHORIZATION_BYTES + 2)
    if len(line.encode("utf-8")) > _MAX_AUTHORIZATION_BYTES + 1:
        raise LiveGateError("authorization line exceeds the bounded protocol")
    return line


def _authorization_matches(challenge: Mapping[str, Any], raw_line: str) -> bool:
    if not isinstance(raw_line, str) or raw_line == "":
        return False
    if raw_line.endswith("\r\n"):
        candidate = raw_line[:-2]
    elif raw_line.endswith("\n"):
        candidate = raw_line[:-1]
    else:
        return False
    if "\n" in candidate or "\r" in candidate:
        return False
    return candidate == challenge.get("required_response")


def _parse_runtime_serial(output: object) -> int:
    if type(output) is not str:
        raise LiveGateError("runtime serial output is not text")
    matches = re.findall(r"(?m)^ROOK_DOC_RUNTIME_SERIAL=([1-9][0-9]*)$", output)
    if len(matches) != 1:
        raise LiveGateError("runtime serial output must contain exactly one marker")
    return int(matches[0])


def _parse_point_id(output: object) -> str:
    if type(output) is not str:
        raise LiveGateError("point output is not text")
    matches = re.findall(r"(?im)^ROOK_POINT_ID=([0-9a-f-]{36})$", output)
    if len(matches) != 1 or _GUID_RE.fullmatch(matches[0]) is None:
        raise LiveGateError("point output must contain exactly one GUID marker")
    return matches[0].lower()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rook.containment_live_gate")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--scenario", required=True, choices=SCENARIOS)
    run.add_argument("--rhino-exe", required=True)
    run.add_argument("--artifact-dir", required=True)
    return parser


def _collect_and_validate_runtime_evidence() -> dict[str, Any]:
    from .containment_acceptance import _validate_current_installed_process

    evidence = _validate_current_installed_process(
        required_rook_modules=("rook", "rook.containment_live_gate")
    )
    return {
        "python_executable": str(evidence["executable"]),
        "installed_root": str(evidence["installed_root"]),
        "cwd": str(evidence["cwd"]),
        "sys_path": list(evidence["sys_path"]),
        "rook_origins": dict(evidence["rook_origins"]),
    }


def _get_metrics_store():
    from .learning.metrics_store import get_metrics_store

    return get_metrics_store()


def _build_launch_environment() -> dict[str, Any]:
    from .rhino_launch import build_launch_env

    launch = build_launch_env()
    return {"env": launch.env, "report": launch.report}


def _start_owned_rhino(*, rhino_exe: Path, launch: Mapping[str, Any]):
    from .rhino_launch import start_rhino_process

    return start_rhino_process(
        rhino_exe,
        requested_scheme=None,
        env=launch["env"],
        launch_env_report=dict(launch["report"]),
    )


def _new_owned_discovery():
    from .rhino_launch import OwnedRhinoDiscovery

    return OwnedRhinoDiscovery()


def _wait_for_owned_readiness(started: Any, owned: Any):
    from .rhino_launch import wait_for_rook_readiness

    readiness = wait_for_rook_readiness(started, discovery=owned)
    if not readiness.outcome.ok or readiness.record is None:
        raise LiveGateError(readiness.outcome.message or "owned Rhino did not become ready")
    return readiness.record


def _owned_process_start_token(started: Any) -> str:
    value = [int(started.pid), float(started.started_wall)]
    return _sha256_value(value)[:32]


async def _dispatch_installed_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from . import server

    return await server._call_tool_dispatch(name, arguments)


class BoundInstalledToolAdapter:
    """Dispatch admitted tools only to one PID/port pair."""

    def __init__(self, port: int, process_id: int):
        if type(port) is not int or port <= 0 or type(process_id) is not int or process_id <= 0:
            raise LiveGateError("bound adapter identity is invalid")
        self.port = port
        self.process_id = process_id
        self._discovery = _new_owned_discovery()

    def _check_owned_record(self) -> None:
        try:
            record = self._discovery.read_owned_record(self.process_id)
        except Exception as exc:
            raise OwnershipAmbiguous("owned discovery record is unavailable") from exc
        if record.pid != self.process_id or record.port != self.port:
            raise OwnershipAmbiguous("owned discovery PID/port drift")

    async def call(
        self,
        name: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        if type(name) is not str or name not in ADMITTED_TOOL_NAMES:
            raise LiveGateError("tool is outside the live-gate allowlist")
        if not isinstance(arguments, Mapping) or not all(type(key) is str for key in arguments):
            raise LiveGateError("tool arguments must be a string-keyed mapping")
        if "port" in arguments:
            raise LiveGateError("tool arguments may not override the bound port")
        self._check_owned_record()
        bound_arguments = dict(arguments)
        bound_arguments["port"] = self.port
        from .bridge import rhino_request_context

        with rhino_request_context(port=self.port, process_id=self.process_id):
            result = await _dispatch_installed_tool(name, bound_arguments)
        self._check_owned_record()
        return result


def _new_bound_adapter(port: int, process_id: int) -> BoundInstalledToolAdapter:
    return BoundInstalledToolAdapter(port=port, process_id=process_id)


def _request_graceful_close(process: Any, diagnostics: list[str]) -> bool:
    from .runtime_harness import request_external_graceful_close

    return request_external_graceful_close(
        process,
        timeout_seconds=15.0,
        diagnostics=diagnostics,
    )


def _force_owned_cleanup(process: Any, diagnostics: list[str]) -> bool:
    from .runtime_harness import force_owned_process_cleanup

    return force_owned_process_cleanup(process, diagnostics)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _validate_snapshot(snapshot: object) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping) or set(snapshot) != {
        "process_id",
        "process_start_token",
        "events",
    }:
        raise LiveGateError("containment telemetry snapshot schema drift")
    value = dict(snapshot)
    if value["process_id"] != os.getpid() or _TOKEN_RE.fullmatch(str(value["process_start_token"])) is None:
        raise LiveGateError("containment telemetry process identity drift")
    if not isinstance(value["events"], list):
        raise LiveGateError("containment telemetry events are malformed")
    return value


def _data(envelope: object, name: str) -> Mapping[str, Any]:
    if not isinstance(envelope, Mapping) or envelope.get("success") is not True:
        raise LiveGateError(f"{name} returned a failed or malformed envelope")
    data = envelope.get("data")
    if not isinstance(data, Mapping):
        raise LiveGateError(f"{name} returned non-object data")
    return data


def _ci_get(mapping: Mapping[str, Any], name: str, default: Any = None) -> Any:
    folded = name.casefold()
    for key, value in mapping.items():
        if type(key) is str and key.casefold() == folded:
            return value
    return default


def _script_output(envelope: object, name: str) -> str:
    data = _data(envelope, name)
    for key in ("output", "stdout", "result"):
        value = _ci_get(data, key)
        if type(value) is str:
            return value
    raise LiveGateError(f"{name} returned no script output")


class _OperationRecorder:
    def __init__(self, state: _RunState):
        self.state = state
        self.directory = state.artifact_dir / "operations"

    async def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in (
            RHINO_TOOL_ALLOWLIST
            if self.state.scenario == "rhino"
            else GRASSHOPPER_TOOL_ALLOWLIST
        ):
            raise LiveGateError("scenario attempted a tool outside its allowlist")
        index = len(self.state.result.operations) + 1
        stem = f"{index:03d}-{name}"
        args_path = self.directory / f"{stem}-arguments.json"
        result_path = self.directory / f"{stem}-result.json"
        try:
            _atomic_write_bytes(args_path, _canonical_json_bytes(dict(arguments)))
            _register_artifact(self.state.result, args_path, self.state.artifact_dir, "operation_arguments")
        except Exception as exc:
            raise _ScenarioFailure("mutation_failed", "operation argument evidence write failed") from exc
        try:
            envelope = await self.state.adapter.call(name, dict(arguments))
        except OwnershipAmbiguous:
            self.state.ownership_certain = False
            raise
        try:
            _atomic_write_bytes(result_path, _canonical_json_bytes(envelope))
            _register_artifact(self.state.result, result_path, self.state.artifact_dir, "operation_result")
        except Exception as exc:
            raise _ScenarioFailure("mutation_failed", "operation result evidence write failed") from exc
        operation = {
            "index": index,
            "name": name,
            "arguments_path": args_path.relative_to(self.state.artifact_dir).as_posix(),
            "arguments_sha256": _sha256_bytes(args_path.read_bytes()),
            "result_path": result_path.relative_to(self.state.artifact_dir).as_posix(),
            "result_sha256": _sha256_bytes(result_path.read_bytes()),
            "success": isinstance(envelope, Mapping) and envelope.get("success") is True,
        }
        self.state.result.operations.append(operation)
        if not operation["success"]:
            raise _ScenarioFailure("mutation_failed", f"{name} returned failure")
        return envelope


def _discard_pre_authorization_operations(state: _RunState) -> None:
    paths: list[Path] = []
    for operation in state.result.operations:
        for key in ("arguments_path", "result_path"):
            raw = operation.get(key)
            if type(raw) is str:
                paths.append(state.artifact_dir / raw)
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise LiveGateError("pre-authorization operation evidence could not be discarded") from exc
    state.result.operations.clear()
    state.result.artifacts = [
        item
        for item in state.result.artifacts
        if not str(item.get("kind", "")).startswith("operation_")
    ]
    try:
        (state.artifact_dir / "operations").rmdir()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise LiveGateError("pre-authorization operation directory was not empty") from exc


def _rhino_document_projection(data: Mapping[str, Any]) -> dict[str, Any]:
    path = _ci_get(data, "path", "")
    count = _ci_get(data, "objectCount")
    modified = _ci_get(data, "modified")
    if type(path) is not str or type(count) is not int or type(modified) is not bool:
        raise LiveGateError("Rhino document projection is malformed")
    return {"path": path, "object_count": count, "modified": modified}


def _rhino_object_ids(data: Mapping[str, Any]) -> list[str]:
    objects = _ci_get(data, "objects")
    if not isinstance(objects, list):
        raise LiveGateError("Rhino object projection is malformed")
    ids: list[str] = []
    for item in objects:
        if not isinstance(item, Mapping) or type(_ci_get(item, "id")) is not str:
            raise LiveGateError("Rhino object identity is malformed")
        ids.append(str(_ci_get(item, "id")).lower())
    return sorted(ids)


async def _rhino_preflight(recorder: _OperationRecorder) -> tuple[dict[str, Any], dict[str, Any]]:
    await recorder.call("rhino_ping", {})
    serial_result = await recorder.call("rhino_execute", {"code": RUNTIME_SERIAL_CODE})
    serial = _parse_runtime_serial(_script_output(serial_result, "rhino_execute"))
    document = _rhino_document_projection(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    object_ids = _rhino_object_ids(
        _data(await recorder.call("rhino_objects", {"limit": 500, "offset": 0}), "rhino_objects")
    )
    if document != {"path": "", "object_count": 0, "modified": False} or object_ids:
        raise _ScenarioFailure("preflight_blocked", "fresh Rhino document is not empty and clean")
    full = {"runtime_serial": serial, **document, "object_ids": object_ids}
    host = {
        "prior_active_document_runtime_serial": serial,
        "prior_path": "",
        "prior_modified": False,
    }
    return full, host


def _gh_status_projection(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "available": _ci_get(data, "available"),
        "has_active_canvas": _ci_get(data, "hasActiveCanvas"),
        "has_active_document": _ci_get(data, "hasActiveDocument"),
        "document_id": _ci_get(data, "documentId"),
        "document_path": _ci_get(data, "documentPath", ""),
        "object_count": _ci_get(data, "objectCount"),
        "ready_for_edit": _ci_get(data, "readyForEdit"),
    }


async def _grasshopper_preflight(recorder: _OperationRecorder) -> tuple[dict[str, Any], dict[str, Any]]:
    await recorder.call("rhino_ping", {})
    rhino = _rhino_document_projection(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    status = _gh_status_projection(_data(await recorder.call("gh_status", {}), "gh_status"))
    if rhino != {"path": "", "object_count": 0, "modified": False}:
        raise _ScenarioFailure("preflight_blocked", "fresh Rhino host document is not empty and clean")
    if not (
        status["available"] is False
        and status["has_active_canvas"] is False
        and status["has_active_document"] is False
        and status["document_id"] is None
        and status["object_count"] == 0
        and status["ready_for_edit"] is False
    ):
        raise _ScenarioFailure("preflight_blocked", "Grasshopper is already present in the owned process")
    full = {"rhino": rhino, "grasshopper": status}
    host = {"has_active_canvas": False, "document_id": None}
    return full, host


def _new_result(scenario: str, run_id: str, started_at: str) -> LiveScenarioResult:
    return LiveScenarioResult(
        schema_version=SCHEMA_VERSION,
        scenario=scenario,
        success=False,
        failure_label=None,
        run_id=run_id,
        started_at=started_at,
        ended_at=started_at,
        runtime=None,
        target=None,
        authorization=None,
        pre_state=None,
        operations=[],
        verification={"passed": False, "projection": None, "projection_sha256": None, "errors": [], "warnings": []},
        restoration={
            "ownership_certain": True,
            "attempted": False,
            "verified": False,
            "in_process_projection_matches_declared": False,
            "prior_identity_or_absence_restored": False,
            "scratch_disposed": False,
            "discovery_removed": False,
        },
        telemetry=None,
        artifacts=[],
        diagnostics=[],
    )


def _record_diagnostic(state: _RunState, stage: str, label: str, exc: BaseException) -> None:
    index = len(state.result.diagnostics) + 1
    path = state.artifact_dir / "diagnostics" / f"{index:03d}-{label}.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "label": label,
        "detail": _bounded_detail(exc),
    }
    try:
        _atomic_write_bytes(path, _canonical_json_bytes(payload))
        sidecar = path.with_suffix(path.suffix + ".sha256")
        _atomic_write_bytes(sidecar, f"{_sha256_bytes(path.read_bytes())}\n".encode("ascii"))
        _register_artifact(state.result, path, state.artifact_dir, "diagnostic")
        _register_artifact(state.result, sidecar, state.artifact_dir, "diagnostic_sidecar")
        state.result.diagnostics.append(
            {
                "stage": stage,
                "label": label,
                "relative_path": path.relative_to(state.artifact_dir).as_posix(),
                "sha256": _sha256_bytes(path.read_bytes()),
            }
        )
    except Exception:
        return


def _target_dict(state: _RunState, process_token: str) -> dict[str, Any]:
    raw = Path(state.record.path).read_bytes()
    return {
        "process_id": int(state.record.pid),
        "port": int(state.record.port),
        "process_start_token": process_token,
        "discovery_record_sha256": _sha256_bytes(raw),
        "scratch_path": str(state.scratch_path),
        "ownership_certain": True,
    }


def _challenge_target(state: _RunState) -> dict[str, Any]:
    return {
        "label": AUTHORIZATION_LABELS[state.scenario],
        "process_id": int(state.record.pid),
        "port": int(state.record.port),
        "scratch_path": str(state.scratch_path),
    }


def _validate_guid(value: object, label: str) -> str:
    if type(value) is not str or _GUID_RE.fullmatch(value) is None:
        raise _ScenarioFailure("verification_failed", f"{label} is not a valid GUID")
    return value.lower()


def _verify_rhino_geometry(
    sphere: Mapping[str, Any],
    point: Mapping[str, Any],
    *,
    run_id: str,
    sphere_id: str,
    point_id: str,
) -> dict[str, Any]:
    sphere_geometry = _ci_get(sphere, "geometry")
    point_geometry = _ci_get(point, "geometry")
    sphere_bbox = _ci_get(sphere, "bbox")
    expected_bbox = {"min": [-4, -4, -4], "max": [4, 4, 4]}
    if (
        str(_ci_get(sphere, "id", "")).lower() != sphere_id
        or _ci_get(sphere, "name") != f"RookContainmentSphere-{run_id}"
        or _ci_get(sphere, "type") != "Brep"
        or sphere_bbox != expected_bbox
        or not isinstance(sphere_geometry, Mapping)
        or _ci_get(sphere_geometry, "type") != "Brep"
        or _ci_get(sphere_geometry, "isSolid") is not True
    ):
        raise _ScenarioFailure("verification_failed", "sphere projection mismatch")
    if (
        str(_ci_get(point, "id", "")).lower() != point_id
        or _ci_get(point, "name") != f"RookContainmentPoint-{run_id}"
        or _ci_get(point, "type") != "Point"
        or not isinstance(point_geometry, Mapping)
        or _ci_get(point_geometry, "type") != "Point"
        or _ci_get(point_geometry, "location") != [10, 0, 0]
    ):
        raise _ScenarioFailure("verification_failed", "point projection mismatch")
    return {
        "sphere": {
            "id": sphere_id,
            "name": f"RookContainmentSphere-{run_id}",
            "type": "Brep",
            "center": [0, 0, 0],
            "radius": 4,
            "bbox": expected_bbox,
            "is_solid": True,
        },
        "point": {
            "id": point_id,
            "name": f"RookContainmentPoint-{run_id}",
            "type": "Point",
            "location": [10, 0, 0],
        },
    }


async def _run_rhino_forward(state: _RunState, recorder: _OperationRecorder) -> None:
    try:
        initial, host = await _rhino_preflight(recorder)
    except _ScenarioFailure:
        raise
    except Exception as exc:
        raise _ScenarioFailure("preflight_blocked", "Rhino preflight evidence was malformed") from exc
    preflight_sha = _sha256_value(initial)
    state.result.pre_state = {
        "host_projection": host,
        "host_sha256": _sha256_value(host),
        "scratch_projection": None,
        "scratch_sha256": None,
    }
    challenge = _build_authorization_challenge(
        scenario="rhino",
        run_id=state.run_id,
        nonce=_new_nonce(),
        target=_challenge_target(state),
    )
    state.result.authorization = {
        "nonce": challenge["nonce"],
        "challenge_sha256": _sha256_value(challenge),
        "authorized_at": None,
        "preflight_sha256": preflight_sha,
        "pre_mutation_sha256": None,
        "state_unchanged": False,
    }
    _emit_jsonl(challenge)
    try:
        raw_authorization = _read_authorization_line()
    except Exception as exc:
        raise _ScenarioFailure("authorization_rejected", "authorization input was unavailable") from exc
    if not _authorization_matches(challenge, raw_authorization):
        raise _ScenarioFailure("authorization_rejected", "authorization response did not match")
    state.result.authorization["authorized_at"] = _utc_now()
    try:
        repeated, _ = await _rhino_preflight(recorder)
    except Exception as exc:
        raise _ScenarioFailure("state_drift", "Rhino preflight state drifted after authorization") from exc
    repeated_sha = _sha256_value(repeated)
    state.result.authorization["pre_mutation_sha256"] = repeated_sha
    state.result.authorization["state_unchanged"] = repeated_sha == preflight_sha
    if repeated_sha != preflight_sha:
        raise _ScenarioFailure("state_drift", "Rhino preflight state drifted after authorization")
    state.authorized = True

    state.mutation_started = True
    await recorder.call(
        "rhino_document_ops",
        {"action": "save", "path": str(state.scratch_path)},
    )
    serial_result = await recorder.call("rhino_execute", {"code": RUNTIME_SERIAL_CODE})
    serial = _parse_runtime_serial(_script_output(serial_result, "rhino_execute"))
    doc = _rhino_document_projection(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    ids = _rhino_object_ids(_data(await recorder.call("rhino_objects", {"limit": 500, "offset": 0}), "rhino_objects"))
    scratch = {
        "runtime_serial": serial,
        "path": doc["path"],
        "modified": doc["modified"],
        "object_count": doc["object_count"],
        "object_ids": ids,
    }
    expected_scratch = {
        "runtime_serial": initial["runtime_serial"],
        "path": str(state.scratch_path),
        "modified": False,
        "object_count": 0,
        "object_ids": [],
    }
    if scratch != expected_scratch or not state.scratch_path.is_file():
        raise _ScenarioFailure("mutation_failed", "scratch Rhino document save projection mismatch")
    state.result.pre_state["scratch_projection"] = scratch
    state.result.pre_state["scratch_sha256"] = _sha256_value(scratch)

    sphere_result = _data(
        await recorder.call("rhino_create", _rhino_sphere_arguments(state.run_id)),
        "rhino_create",
    )
    sphere_id = _validate_guid(_ci_get(sphere_result, "id"), "sphere ID")
    state.created_rhino_ids = [sphere_id]
    point_result = await recorder.call(
        "rhino_execute",
        {"code": _rhino_point_script(state.run_id)},
    )
    point_id = _parse_point_id(_script_output(point_result, "rhino_execute"))
    state.created_rhino_ids.append(point_id)

    objects = _data(await recorder.call("rhino_objects", {"limit": 500, "offset": 0}), "rhino_objects")
    ids = _rhino_object_ids(objects)
    if ids != sorted([sphere_id, point_id]):
        raise _ScenarioFailure("verification_failed", "Rhino object identity set mismatch")
    sphere = _data(await recorder.call("rhino_geometry", {"id": sphere_id}), "rhino_geometry")
    point = _data(await recorder.call("rhino_geometry", {"id": point_id}), "rhino_geometry")
    geometry = _verify_rhino_geometry(
        sphere,
        point,
        run_id=state.run_id,
        sphere_id=sphere_id,
        point_id=point_id,
    )
    doc_after = _rhino_document_projection(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    if doc_after["object_count"] != 2 or doc_after["modified"] is not True:
        raise _ScenarioFailure("verification_failed", "Rhino document did not report the two mutations")
    projection = {"document": doc_after, "objects": geometry, "object_ids": ids}
    state.result.verification = {
        "passed": True,
        "projection": projection,
        "projection_sha256": _sha256_value(projection),
        "errors": [],
        "warnings": [],
    }


def _snapshot_projection(
    snapshot: Mapping[str, Any],
    *,
    process_id: int,
    process_token: str,
    port: int,
    document_id: str,
) -> dict[str, Any]:
    document = _ci_get(snapshot, "document")
    components = _ci_get(snapshot, "components")
    flows = _ci_get(snapshot, "flows")
    diagnostics = _ci_get(snapshot, "diagnostics")
    if not isinstance(document, Mapping) or not isinstance(components, list) or not isinstance(flows, list) or not isinstance(diagnostics, Mapping):
        raise LiveGateError("Grasshopper snapshot projection is malformed")
    component_ids = []
    for item in components:
        if not isinstance(item, Mapping) or type(_ci_get(item, "id")) is not str:
            raise LiveGateError("Grasshopper component identity is malformed")
        component_ids.append(str(_ci_get(item, "id")))
    errors = _ci_get(diagnostics, "errors", 0)
    warnings = _ci_get(diagnostics, "warnings", 0)
    token = _sha256_value([process_id, process_token, port, True, document_id])
    return {
        "document_id": document_id,
        "has_active_canvas": True,
        "gate_canvas_token": token,
        "path": str(_ci_get(document, "path", "")),
        "object_count": len(components),
        "component_ids": component_ids,
        "wires": list(flows),
        "errors": errors,
        "warnings": warnings,
    }


def _assert_empty_gh_projection(projection: Mapping[str, Any], scratch_path: Path) -> None:
    if not (
        projection["path"] == str(scratch_path)
        and projection["object_count"] == 0
        and projection["component_ids"] == []
        and projection["wires"] == []
        and projection["errors"] == 0
        and projection["warnings"] == 0
    ):
        raise _ScenarioFailure("fixture_invalid", "opened Grasshopper fixture is not empty")


def _errors_projection(data: Mapping[str, Any]) -> tuple[list[Any], list[Any]]:
    errors = _ci_get(data, "errors", [])
    warnings = _ci_get(data, "warnings", [])
    error_count = _ci_get(data, "errorCount", len(errors) if isinstance(errors, list) else None)
    warning_count = _ci_get(data, "warningCount", len(warnings) if isinstance(warnings, list) else None)
    if not isinstance(errors, list) or not isinstance(warnings, list) or error_count != len(errors) or warning_count != len(warnings):
        raise LiveGateError("Grasshopper error projection is malformed")
    return errors, warnings


def _verify_gh_edit(snapshot: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    components = _ci_get(snapshot, "components")
    flows = _ci_get(snapshot, "flows")
    diagnostics = _ci_get(snapshot, "diagnostics")
    if not isinstance(components, list) or len(components) != 2 or flows != ["C1.O0>C2.I1"] or not isinstance(diagnostics, Mapping):
        raise _ScenarioFailure("verification_failed", "Grasshopper topology mismatch")
    slider = next((item for item in components if isinstance(item, Mapping) and _ci_get(item, "type") == "NumberSlider"), None)
    sphere = next((item for item in components if isinstance(item, Mapping) and str(_ci_get(item, "componentGuid", "")).lower() == SPHERE_COMPONENT_GUID), None)
    if slider is None or sphere is None:
        raise _ScenarioFailure("verification_failed", "Grasshopper component identities mismatch")
    value = _ci_get(slider, "value")
    inputs = _ci_get(sphere, "inputs")
    radius_input = next(
        (
            item
            for item in inputs
            if isinstance(item, Mapping) and _ci_get(item, "idx") == 1
        ),
        None,
    ) if isinstance(inputs, list) else None
    if (
        _ci_get(slider, "id") != "C1"
        or _ci_get(slider, "nick") != f"RookContainmentRadius-{run_id}"
        or _ci_get(slider, "pos") != [100, 100]
        or not isinstance(value, Mapping)
        or _ci_get(value, "min") != 1
        or _ci_get(value, "max") != 9
        or _ci_get(value, "val") != 4
        or _ci_get(sphere, "id") != "C2"
        or _ci_get(sphere, "name") != "Sphere"
        or _ci_get(sphere, "pos") != [400, 100]
        or not isinstance(radius_input, Mapping)
        or _ci_get(radius_input, "name") != "Radius"
        or _ci_get(radius_input, "sources") != 1
    ):
        raise _ScenarioFailure("verification_failed", "Grasshopper component settings mismatch")
    outputs = _ci_get(sphere, "outputs")
    if not isinstance(outputs, list) or not outputs:
        raise _ScenarioFailure("verification_failed", "Sphere output is absent")
    data = _ci_get(outputs[0], "data") if isinstance(outputs[0], Mapping) else None
    preview = _ci_get(data, "preview") if isinstance(data, Mapping) else None
    if not isinstance(data, Mapping) or _ci_get(data, "count") != 1 or not isinstance(preview, list) or not any("4" in str(item) for item in preview):
        raise _ScenarioFailure("verification_failed", "Sphere radius-4 output was not observed")
    if _ci_get(diagnostics, "errors", 0) != 0 or _ci_get(diagnostics, "warnings", 0) != 0:
        raise _ScenarioFailure("verification_failed", "Grasshopper snapshot contains diagnostics")
    return {"components": components, "flows": flows, "diagnostics": dict(diagnostics)}


async def _run_grasshopper_forward(state: _RunState, recorder: _OperationRecorder) -> None:
    try:
        payload = _fixture_resource_path().read_bytes()
        _validate_fixture_bytes(payload)
        _atomic_write_bytes(state.scratch_path, payload)
        if state.scratch_path.read_bytes() != payload:
            raise LiveGateError("scratch fixture copy mismatch")
    except Exception as exc:
        raise _ScenarioFailure("fixture_invalid", "packaged Grasshopper fixture is invalid") from exc

    try:
        initial, host = await _grasshopper_preflight(recorder)
    except _ScenarioFailure:
        raise
    except Exception as exc:
        raise _ScenarioFailure("preflight_blocked", "Grasshopper preflight evidence was malformed") from exc
    preflight_sha = _sha256_value(initial)
    state.result.pre_state = {
        "host_projection": host,
        "host_sha256": _sha256_value(host),
        "scratch_projection": None,
        "scratch_sha256": None,
    }
    challenge = _build_authorization_challenge(
        scenario="grasshopper",
        run_id=state.run_id,
        nonce=_new_nonce(),
        target=_challenge_target(state),
    )
    state.result.authorization = {
        "nonce": challenge["nonce"],
        "challenge_sha256": _sha256_value(challenge),
        "authorized_at": None,
        "preflight_sha256": preflight_sha,
        "pre_mutation_sha256": None,
        "state_unchanged": False,
    }
    _emit_jsonl(challenge)
    try:
        raw_authorization = _read_authorization_line()
    except Exception as exc:
        raise _ScenarioFailure("authorization_rejected", "authorization input was unavailable") from exc
    if not _authorization_matches(challenge, raw_authorization):
        raise _ScenarioFailure("authorization_rejected", "authorization response did not match")
    state.result.authorization["authorized_at"] = _utc_now()
    try:
        repeated, _ = await _grasshopper_preflight(recorder)
    except Exception as exc:
        raise _ScenarioFailure("state_drift", "Grasshopper preflight state drifted after authorization") from exc
    repeated_sha = _sha256_value(repeated)
    state.result.authorization["pre_mutation_sha256"] = repeated_sha
    state.result.authorization["state_unchanged"] = repeated_sha == preflight_sha
    if repeated_sha != preflight_sha:
        raise _ScenarioFailure("state_drift", "Grasshopper preflight state drifted after authorization")
    state.authorized = True

    state.mutation_started = True
    await recorder.call("rhino_command", {"command": "_Grasshopper", "echo": False})
    ready_status: dict[str, Any] | None = None
    for _ in range(20):
        status = _gh_status_projection(_data(await recorder.call("gh_status", {}), "gh_status"))
        if status["ready_for_edit"] is True and status["has_active_canvas"] is True and status["has_active_document"] is True:
            ready_status = status
            break
        _sleep(0.25)
    if ready_status is None or type(ready_status["document_id"]) is not str:
        raise _ScenarioFailure("readiness_failed", "Grasshopper did not become ready")
    bootstrap_document_id = ready_status["document_id"]
    await recorder.call("gh_document_open", {"path": str(state.scratch_path)})
    status_after_open = _gh_status_projection(_data(await recorder.call("gh_status", {}), "gh_status"))
    document_id = status_after_open["document_id"]
    if (
        type(document_id) is not str
        or document_id == bootstrap_document_id
        or status_after_open["object_count"] != 0
    ):
        raise _ScenarioFailure("fixture_invalid", "opened Grasshopper document identity drift")
    empty_snapshot = _data(await recorder.call("gh_snapshot", {}), "gh_snapshot")
    empty_errors, empty_warnings = _errors_projection(_data(await recorder.call("gh_errors", {}), "gh_errors"))
    if empty_errors or empty_warnings:
        raise _ScenarioFailure("fixture_invalid", "empty fixture contains diagnostics")
    projection = _snapshot_projection(
        empty_snapshot,
        process_id=state.record.pid,
        process_token=state.result.target["process_start_token"],
        port=state.record.port,
        document_id=document_id,
    )
    _assert_empty_gh_projection(projection, state.scratch_path)
    state.result.pre_state["scratch_projection"] = projection
    state.result.pre_state["scratch_sha256"] = _sha256_value(projection)

    library = _data(await recorder.call("gh_library", {"search": "Sphere", "exact": True}), "gh_library")
    components = _ci_get(library, "components")
    if (
        _ci_get(library, "count") != 1
        or not isinstance(components, list)
        or len(components) != 1
    ):
        raise _ScenarioFailure("verification_failed", "exact Sphere library lookup was not unique")
    component = components[0]
    if not isinstance(component, Mapping) or str(_ci_get(component, "guid", "")).lower() != SPHERE_COMPONENT_GUID:
        raise _ScenarioFailure("verification_failed", "exact Sphere library GUID mismatch")
    edit_base = _data(await recorder.call("gh_snapshot", {}), "gh_snapshot")
    epoch = _ci_get(edit_base, "epoch")
    if type(epoch) is not int:
        raise _ScenarioFailure("verification_failed", "Grasshopper snapshot epoch is invalid")
    await recorder.call("gh_edit", _grasshopper_edit_arguments(state.run_id, epoch))
    state.gh_edit_applied = True

    solved_snapshot: Mapping[str, Any] | None = None
    final_errors: list[Any] = []
    final_warnings: list[Any] = []
    for _ in range(20):
        candidate = _data(await recorder.call("gh_snapshot", {}), "gh_snapshot")
        errors, warnings = _errors_projection(_data(await recorder.call("gh_errors", {}), "gh_errors"))
        status = _gh_status_projection(_data(await recorder.call("gh_status", {}), "gh_status"))
        candidate_epoch = _ci_get(candidate, "epoch")
        try:
            verified = (
                _verify_gh_edit(candidate, state.run_id)
                if type(candidate_epoch) is int and candidate_epoch > epoch
                else None
            )
        except _ScenarioFailure:
            verified = None
        if verified is not None and not errors and not warnings and status["ready_for_edit"] is True:
            solved_snapshot = candidate
            final_errors, final_warnings = errors, warnings
            break
        _sleep(0.25)
    if solved_snapshot is None:
        raise _ScenarioFailure("verification_failed", "Grasshopper edit did not settle to the expected solved projection")
    verified_projection = _verify_gh_edit(solved_snapshot, state.run_id)
    state.result.verification = {
        "passed": True,
        "projection": verified_projection,
        "projection_sha256": _sha256_value(verified_projection),
        "errors": final_errors,
        "warnings": final_warnings,
    }


async def _restore_rhino(state: _RunState, recorder: _OperationRecorder) -> bool:
    state.result.restoration["attempted"] = True
    if state.created_rhino_ids:
        await recorder.call("rhino_delete", {"ids": list(state.created_rhino_ids)})
    dirty = _rhino_document_projection(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    if state.created_rhino_ids and dirty["modified"] is not True:
        return False
    await recorder.call("rhino_document_ops", {"action": "save", "path": str(state.scratch_path)})
    serial_result = await recorder.call("rhino_execute", {"code": RUNTIME_SERIAL_CODE})
    serial = _parse_runtime_serial(_script_output(serial_result, "rhino_execute"))
    document = _rhino_document_projection(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    ids = _rhino_object_ids(_data(await recorder.call("rhino_objects", {"limit": 500, "offset": 0}), "rhino_objects"))
    expected = state.result.pre_state.get("scratch_projection") if state.result.pre_state else None
    restored = {
        "runtime_serial": serial,
        "path": document["path"],
        "modified": document["modified"],
        "object_count": document["object_count"],
        "object_ids": ids,
    }
    matches = isinstance(expected, Mapping) and restored == dict(expected)
    state.result.restoration["in_process_projection_matches_declared"] = matches
    return matches and state.scratch_path.is_file()


async def _restore_grasshopper(state: _RunState, recorder: _OperationRecorder) -> bool:
    state.result.restoration["attempted"] = True
    expected = state.result.pre_state.get("scratch_projection") if state.result.pre_state else None
    if not isinstance(expected, Mapping):
        return False
    if state.gh_edit_applied:
        matched = False
        for _ in range(4):
            await recorder.call("gh_undo", {})
            snapshot = _data(await recorder.call("gh_snapshot", {}), "gh_snapshot")
            errors, warnings = _errors_projection(_data(await recorder.call("gh_errors", {}), "gh_errors"))
            status = _gh_status_projection(_data(await recorder.call("gh_status", {}), "gh_status"))
            if type(status["document_id"]) is not str or errors or warnings:
                continue
            projection = _snapshot_projection(
                snapshot,
                process_id=state.record.pid,
                process_token=state.result.target["process_start_token"],
                port=state.record.port,
                document_id=status["document_id"],
            )
            if projection == dict(expected):
                matched = True
                break
        state.result.restoration["in_process_projection_matches_declared"] = matched
        return matched
    state.result.restoration["in_process_projection_matches_declared"] = True
    return True


def _cleanup_owned_target(state: _RunState, diagnostics: list[str]) -> bool:
    if state.process is None:
        return False
    owned_process = getattr(state.process, "process", state.process)
    forced = False
    try:
        forced = _request_graceful_close(owned_process, diagnostics)
    except Exception as exc:
        diagnostics.append(f"graceful cleanup failed for pid {owned_process.pid}: {_bounded_detail(exc)}")
        forced = True
    if owned_process.poll() is None:
        forced = True
        try:
            _force_owned_cleanup(owned_process, diagnostics)
        except Exception as exc:
            diagnostics.append(f"force cleanup failed for pid {owned_process.pid}: {_bounded_detail(exc)}")
    if owned_process.poll() is None:
        return False
    record_path = Path(state.record.path) if state.record is not None else None
    discovery_removed = record_path is None
    if record_path is not None:
        for _ in range(20):
            if not record_path.exists():
                discovery_removed = True
                break
            _sleep(0.25)
    scratch_disposed = True
    if state.scratch_path is not None and state.scratch_path.exists():
        try:
            state.scratch_path.unlink()
        except OSError:
            scratch_disposed = False
    state.result.restoration["prior_identity_or_absence_restored"] = True
    state.result.restoration["scratch_disposed"] = scratch_disposed
    state.result.restoration["discovery_removed"] = discovery_removed
    return not forced and scratch_disposed and discovery_removed


def _finalize_telemetry(state: _RunState) -> None:
    if state.metrics_store is None or state.telemetry_before is None:
        return
    try:
        current_store = _get_metrics_store()
        after = _validate_snapshot(current_store.get_containment_denials_snapshot())
    except Exception as exc:
        raise _ScenarioFailure("telemetry_changed", "containment telemetry accessor failed") from exc
    before = state.telemetry_before
    if current_store is not state.metrics_store:
        raise _ScenarioFailure("telemetry_changed", "containment telemetry accessor was replaced")
    if (
        after["process_id"] != before["process_id"]
        or after["process_start_token"] != before["process_start_token"]
    ):
        raise _ScenarioFailure("telemetry_changed", "containment telemetry process identity drift")
    before_events = before["events"]
    after_events = after["events"]
    added = after_events[len(before_events) :] if after_events[: len(before_events)] == before_events else after_events
    delta = len(added) if after_events != before_events else 0
    state.result.telemetry = {
        "process_id": before["process_id"],
        "process_start_token": before["process_start_token"],
        "before_sha256": _sha256_value(before),
        "after_sha256": _sha256_value(after),
        "delta_count": delta,
        "events_added": added,
    }
    if delta != 0:
        raise _ScenarioFailure("telemetry_changed", "supported workflow emitted containment telemetry")


def _write_final_evidence_pair(
    artifact_dir: Path,
    scenario: str,
    evidence: Mapping[str, Any],
) -> tuple[Path, str]:
    path = artifact_dir / f"{scenario}-scenario.json"
    sidecar = artifact_dir / f"{scenario}-scenario.sha256"
    try:
        payload = _canonical_json_bytes(dict(evidence))
        _atomic_write_bytes(path, payload)
        digest = _sha256_bytes(payload)
        _atomic_write_bytes(sidecar, f"{digest}\n".encode("ascii"))
        return path, digest
    except Exception as exc:
        for candidate in (path, sidecar):
            try:
                candidate.unlink()
            except OSError:
                pass
        raise FinalEvidenceWriteError("final evidence pair could not be persisted") from exc


def _scenario_result_record(result: LiveScenarioResult, evidence_sha256: str) -> dict[str, Any]:
    return {
        "type": "scenario_result",
        "schema_version": SCHEMA_VERSION,
        "scenario": result.scenario,
        "run_id": result.run_id,
        "success": result.success,
        "failure_label": result.failure_label,
        "evidence_path": f"{result.scenario}-scenario.json",
        "evidence_sha256": evidence_sha256,
    }


async def _execute_scenario(state: _RunState) -> None:
    recorder = _OperationRecorder(state)
    if state.scenario == "rhino":
        await _run_rhino_forward(state, recorder)
    else:
        await _run_grasshopper_forward(state, recorder)

    if not state.ownership_certain:
        raise OwnershipAmbiguous("owned target identity was lost")
    restored = (
        await _restore_rhino(state, recorder)
        if state.scenario == "rhino"
        else await _restore_grasshopper(state, recorder)
    )
    if not restored:
        raise _ScenarioFailure("restoration_failed", "declared in-process projection was not restored")


def run_live_scenario(
    *,
    scenario: Literal["rhino", "grasshopper"],
    rhino_exe: Path,
    artifact_dir: Path,
) -> LiveScenarioResult:
    if scenario not in SCENARIOS:
        raise PreOwnershipBlocked("unsupported scenario")
    run_id = _new_run_id()
    if _TOKEN_RE.fullmatch(run_id) is None:
        raise LiveGateError("run identifier generator drift")
    owned_dir = _claim_artifact_directory(Path(artifact_dir), run_id)
    started_at = _utc_now()
    result = _new_result(scenario, run_id, started_at)
    state = _RunState(
        scenario=scenario,
        run_id=run_id,
        artifact_dir=owned_dir,
        rhino_exe=Path(rhino_exe).expanduser().resolve(),
        started_at=started_at,
        result=result,
    )
    _register_artifact(result, owned_dir / OWNERSHIP_MARKER, owned_dir, "ownership_marker")
    failure: _ScenarioFailure | None = None
    diagnostics: list[str] = []
    try:
        try:
            if not state.rhino_exe.is_file() or _is_reparse(state.rhino_exe):
                raise LiveGateError("Rhino executable is missing or reparse-backed")
            result.runtime = _collect_and_validate_runtime_evidence()
        except Exception as exc:
            raise _ScenarioFailure("runtime_origin_invalid", "installed runtime origin validation failed") from exc

        try:
            state.metrics_store = _get_metrics_store()
            state.telemetry_before = _validate_snapshot(
                state.metrics_store.get_containment_denials_snapshot()
            )
            result.telemetry = {
                "process_id": state.telemetry_before["process_id"],
                "process_start_token": state.telemetry_before["process_start_token"],
                "before_sha256": _sha256_value(state.telemetry_before),
                "after_sha256": None,
                "delta_count": None,
                "events_added": None,
            }
        except Exception as exc:
            raise _ScenarioFailure("runtime_origin_invalid", "containment telemetry baseline failed") from exc

        try:
            launch = _build_launch_environment()
            state.process = _start_owned_rhino(rhino_exe=state.rhino_exe, launch=launch)
        except Exception as exc:
            raise _ScenarioFailure("launch_failed", "owned Rhino launch failed") from exc
        try:
            state.discovery = _new_owned_discovery()
            state.record = _wait_for_owned_readiness(state.process, state.discovery)
        except Exception as exc:
            raise _ScenarioFailure("readiness_failed", "owned Rhino readiness failed") from exc

        state.scratch_path = owned_dir / (
            f"RookContainmentRhino-{run_id}.3dm"
            if scenario == "rhino"
            else f"RookContainmentGH-{run_id}.ghx"
        )
        process_token = _owned_process_start_token(state.process)
        result.target = _target_dict(state, process_token)
        state.adapter = _new_bound_adapter(state.record.port, state.record.pid)
        asyncio.run(_execute_scenario(state))
    except OwnershipAmbiguous as exc:
        state.ownership_certain = False
        failure = _ScenarioFailure("ownership_ambiguous", str(exc))
    except _ScenarioFailure as exc:
        failure = exc
    except Exception as exc:
        failure = _ScenarioFailure("verification_failed", _bounded_detail(exc))

    if failure is not None:
        if not state.authorized and result.operations:
            try:
                _discard_pre_authorization_operations(state)
            except Exception as discard_exc:
                failure = _ScenarioFailure("cleanup_failed", _bounded_detail(discard_exc))
        result.success = False
        result.failure_label = failure.label
        _record_diagnostic(state, "scenario", failure.label, failure)
        if (
            state.ownership_certain
            and state.process is not None
            and state.authorized
            and state.mutation_started
            and not result.restoration["attempted"]
        ):
            try:
                recorder = _OperationRecorder(state)
                restored = asyncio.run(
                    _restore_rhino(state, recorder)
                    if scenario == "rhino"
                    else _restore_grasshopper(state, recorder)
                )
                if not restored and failure.label not in {"ownership_ambiguous", "restoration_failed"}:
                    result.failure_label = "restoration_failed"
            except OwnershipAmbiguous:
                state.ownership_certain = False
                result.failure_label = "ownership_ambiguous"
            except Exception as restore_exc:
                if failure.label != "ownership_ambiguous":
                    result.failure_label = "restoration_failed"
                _record_diagnostic(state, "restoration", result.failure_label, restore_exc)

    result.restoration["ownership_certain"] = state.ownership_certain
    cleanup_ok = False
    if state.process is not None and state.ownership_certain:
        cleanup_ok = _cleanup_owned_target(state, diagnostics)
        if not cleanup_ok:
            if result.failure_label not in {"ownership_ambiguous", "restoration_failed"}:
                result.failure_label = "cleanup_failed"
            result.success = False
            result.restoration["verified"] = False
    elif state.process is None:
        cleanup_ok = True

    if diagnostics:
        _record_diagnostic(state, "cleanup", "cleanup_failed" if not cleanup_ok else "cleanup_notes", LiveGateError("; ".join(diagnostics)))

    if state.metrics_store is not None:
        try:
            _finalize_telemetry(state)
        except _ScenarioFailure as telemetry_failure:
            result.success = False
            result.failure_label = telemetry_failure.label
            _record_diagnostic(state, "telemetry", telemetry_failure.label, telemetry_failure)

    if failure is None and cleanup_ok and result.failure_label is None:
        result.success = True
        result.restoration["verified"] = (
            result.restoration["in_process_projection_matches_declared"]
            and result.restoration["prior_identity_or_absence_restored"]
            and result.restoration["scratch_disposed"]
            and result.restoration["discovery_removed"]
        )
        if not result.restoration["verified"]:
            result.success = False
            result.failure_label = "restoration_failed"
    else:
        result.success = False
        if result.failure_label is None:
            result.failure_label = failure.label if failure is not None else "cleanup_failed"

    result.ended_at = _utc_now()
    path, digest = _write_final_evidence_pair(owned_dir, scenario, result.to_dict())
    if path.name != f"{scenario}-scenario.json":
        raise FinalEvidenceWriteError("final evidence path drift")
    _emit_jsonl(_scenario_result_record(result, digest))
    return result


def _safe_relative(root: Path, raw: object) -> Path:
    if type(raw) is not str:
        raise LiveGateError("artifact path is not a string")
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise LiveGateError("artifact path escapes the owned directory")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise LiveGateError("artifact path escapes the owned directory") from exc
    return candidate


def _validate_scenario_artifacts(artifact_dir: Path, *, scenario: str) -> dict[str, Any]:
    root = Path(artifact_dir).resolve()
    if scenario not in SCENARIOS:
        raise LiveGateError("scenario evidence identity is invalid")
    evidence_path = root / f"{scenario}-scenario.json"
    sidecar = root / f"{scenario}-scenario.sha256"
    try:
        payload = evidence_path.read_bytes()
        evidence = json.loads(payload)
    except Exception as exc:
        raise LiveGateError("final evidence artifact is missing or malformed") from exc
    if payload != _canonical_json_bytes(evidence):
        raise LiveGateError("final evidence artifact is noncanonical")
    digest = _sha256_bytes(payload)
    if sidecar.read_bytes() != f"{digest}\n".encode("ascii"):
        raise LiveGateError("final evidence sidecar mismatch")
    if not isinstance(evidence, Mapping) or set(evidence) != set(RESULT_FIELDS):
        raise LiveGateError("final evidence schema drift")
    if evidence["scenario"] != scenario or evidence["schema_version"] != SCHEMA_VERSION:
        raise LiveGateError("final evidence scenario drift")
    success = evidence["success"]
    failure_label = evidence["failure_label"]
    if type(success) is not bool or (success and failure_label is not None) or (
        not success and failure_label not in FAILURE_LABELS
    ):
        raise LiveGateError("final evidence success/failure relationship drift")
    artifacts = evidence["artifacts"]
    if not isinstance(artifacts, list):
        raise LiveGateError("artifact inventory is malformed")
    inventory: dict[str, Mapping[str, Any]] = {}
    for item in artifacts:
        if not isinstance(item, Mapping) or set(item) != {"kind", "relative_path", "sha256", "size"}:
            raise LiveGateError("artifact inventory entry is malformed")
        path = _safe_relative(root, item["relative_path"])
        if not path.is_file():
            raise LiveGateError("artifact inventory file is missing")
        content = path.read_bytes()
        if _sha256_bytes(content) != item["sha256"] or len(content) != item["size"]:
            raise LiveGateError("artifact inventory digest mismatch")
        inventory[str(item["relative_path"])] = item
    operations = evidence["operations"]
    if not isinstance(operations, list):
        raise LiveGateError("operation evidence is malformed")
    for expected_index, operation in enumerate(operations, 1):
        expected_keys = {
            "index",
            "name",
            "arguments_path",
            "arguments_sha256",
            "result_path",
            "result_sha256",
            "success",
        }
        if not isinstance(operation, Mapping) or set(operation) != expected_keys or operation["index"] != expected_index:
            raise LiveGateError("operation evidence schema or order drift")
        if operation["name"] not in (RHINO_TOOL_ALLOWLIST if scenario == "rhino" else GRASSHOPPER_TOOL_ALLOWLIST):
            raise LiveGateError("operation tool is outside the scenario allowlist")
        for kind in ("arguments", "result"):
            relative = operation[f"{kind}_path"]
            path = _safe_relative(root, relative)
            if relative not in inventory or not path.is_file():
                raise LiveGateError("operation artifact is not enumerated")
            content = path.read_bytes()
            try:
                decoded = json.loads(content)
            except Exception as exc:
                raise LiveGateError("operation artifact is malformed") from exc
            if content != _canonical_json_bytes(decoded):
                raise LiveGateError("operation artifact is noncanonical")
            if _sha256_bytes(content) != operation[f"{kind}_sha256"]:
                raise LiveGateError("operation artifact digest mismatch")
    return dict(evidence)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_live_scenario(
            scenario=args.scenario,
            rhino_exe=Path(args.rhino_exe),
            artifact_dir=Path(args.artifact_dir),
        )
    except PreOwnershipBlocked as exc:
        print(f"containment live gate blocked: {_bounded_detail(exc)}", file=sys.stderr)
        return 2
    except FinalEvidenceWriteError as exc:
        print(f"containment live gate failed: {_bounded_detail(exc)}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("containment live gate interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"containment live gate failed: {_bounded_detail(exc)}", file=sys.stderr)
        return 3
    if result.success:
        return 0
    if result.failure_label in {
        "runtime_origin_invalid",
        "launch_failed",
        "readiness_failed",
        "fixture_invalid",
        "preflight_blocked",
        "authorization_rejected",
        "state_drift",
    } and not result.restoration["attempted"]:
        return 2
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
