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
import math
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
GH_DEFERRED_DISPATCH_DELAY_SECONDS = 5.0
GH_SOLVE_ALLOWANCE_SECONDS = 10.0
GH_SOLVE_SETTLE_TIMEOUT_SECONDS = (
    GH_DEFERRED_DISPATCH_DELAY_SECONDS + GH_SOLVE_ALLOWANCE_SECONDS
)
GH_SOLVE_POLL_INTERVAL_SECONDS = 0.25
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
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_UTC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"\.[0-9]{1,6}Z$",
    re.ASCII,
)
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
    gh_edit_may_have_applied: bool = False
    gh_undo_attempts: int = 0
    cleanup_live_at_entry: bool | None = None


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


def _rhino_sphere_probe_script(object_id: str) -> str:
    if type(object_id) is not str or _GUID_RE.fullmatch(object_id) is None:
        raise LiveGateError("invalid sphere probe object identifier")
    object_id = object_id.lower()
    return (
        "import json\n"
        "import Rhino\n"
        "import System\n"
        "import scriptcontext as sc\n"
        f'object_id = System.Guid("{object_id}")\n'
        "rhino_object = sc.doc.Objects.FindId(object_id)\n"
        "geometry = rhino_object.Geometry if rhino_object is not None else None\n"
        "brep = geometry if isinstance(geometry, Rhino.Geometry.Brep) else None\n"
        "surface = brep.Faces[0].UnderlyingSurface() if brep is not None and brep.Faces.Count == 1 else None\n"
        "success, sphere = surface.TryGetSphere() if surface is not None else (False, None)\n"
        'payload = {"center": [float(sphere.Center.X), float(sphere.Center.Y), float(sphere.Center.Z)] if success else None, '
        '"id": str(rhino_object.Id) if rhino_object is not None else None, "is_sphere": bool(success), '
        '"radius": float(sphere.Radius) if success else None}\n'
        'print("ROOK_SPHERE_GEOMETRY={0}".format(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)))'
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


def _read_authorization_line() -> bytes:
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None or not callable(getattr(stream, "readline", None)):
        raise LiveGateError("binary authorization input is unavailable")
    line = stream.readline(_MAX_AUTHORIZATION_BYTES + 2)
    if type(line) is not bytes:
        raise LiveGateError("authorization input did not return bytes")
    if len(line) > _MAX_AUTHORIZATION_BYTES + 1:
        raise LiveGateError("authorization line exceeds the bounded protocol")
    return line


def _authorization_matches(challenge: Mapping[str, Any], raw_line: bytes) -> bool:
    if type(raw_line) is not bytes or raw_line == b"":
        return False
    if raw_line.endswith(b"\r\n"):
        candidate = raw_line[:-2]
    elif raw_line.endswith(b"\n"):
        candidate = raw_line[:-1]
    else:
        return False
    if b"\n" in candidate or b"\r" in candidate:
        return False
    expected = challenge.get("required_response")
    if type(expected) is not str:
        return False
    try:
        expected_bytes = expected.encode("ascii")
    except UnicodeEncodeError:
        return False
    return candidate == expected_bytes


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


def _parse_sphere_probe(output: object, *, expected_id: str) -> dict[str, Any]:
    if type(output) is not str:
        raise _ScenarioFailure("verification_failed", "sphere probe output is not text")
    matches = re.findall(r"(?m)^ROOK_SPHERE_GEOMETRY=(\{[^\r\n]*\})$", output)
    if len(matches) != 1:
        raise _ScenarioFailure(
            "verification_failed", "sphere probe output must contain exactly one marker"
        )
    try:
        payload = json.loads(matches[0])
        canonical = _canonical_json_bytes(payload).decode("utf-8")
    except Exception as exc:
        raise _ScenarioFailure("verification_failed", "sphere probe output is malformed") from exc
    if matches[0] != canonical or not isinstance(payload, Mapping):
        raise _ScenarioFailure("verification_failed", "sphere probe output is noncanonical")
    if set(payload) != {"center", "id", "is_sphere", "radius"}:
        raise _ScenarioFailure("verification_failed", "sphere probe schema mismatch")
    observed_id = _validate_guid(payload["id"], "observed sphere ID")
    center = payload["center"]
    radius = payload["radius"]
    if (
        observed_id != expected_id
        or payload["is_sphere"] is not True
        or not isinstance(center, list)
        or len(center) != 3
        or any(type(value) not in (int, float) for value in center)
        or any(not math.isfinite(float(value)) for value in center)
        or [float(value) for value in center] != [0.0, 0.0, 0.0]
        or type(radius) not in (int, float)
        or not math.isfinite(float(radius))
        or float(radius) != 4.0
    ):
        raise _ScenarioFailure("verification_failed", "observed sphere geometry mismatch")
    return {
        "center": [float(value) for value in center],
        "id": observed_id,
        "is_sphere": True,
        "radius": float(radius),
    }


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


def _monotonic() -> float:
    return time.monotonic()


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
        "has_active_canvas": _ci_get(
            data, "has_active_canvas", _ci_get(data, "hasActiveCanvas")
        ),
        "has_active_document": _ci_get(
            data, "has_active_document", _ci_get(data, "hasActiveDocument")
        ),
        "document_id": _ci_get(data, "document_id", _ci_get(data, "documentId")),
        "document_path": _ci_get(
            data, "document_path", _ci_get(data, "documentPath", "")
        ),
        "object_count": _ci_get(data, "object_count", _ci_get(data, "objectCount")),
        "ready_for_edit": _ci_get(
            data, "ready_for_edit", _ci_get(data, "readyForEdit")
        ),
        "solver_enabled": _ci_get(
            data, "solverEnabled", _ci_get(data, "solver_enabled")
        ),
        "solver_state_known": _ci_get(
            data, "solverStateKnown", _ci_get(data, "solver_state_known")
        ),
        "solution_state": _ci_get(
            data, "solutionState", _ci_get(data, "solution_state")
        ),
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
    sphere_probe_result = await recorder.call(
        "rhino_execute",
        {"code": _rhino_sphere_probe_script(sphere_id)},
    )
    sphere_observation = _parse_sphere_probe(
        _script_output(sphere_probe_result, "rhino_execute"),
        expected_id=sphere_id,
    )
    geometry["sphere"]["center"] = sphere_observation["center"]
    geometry["sphere"]["radius"] = sphere_observation["radius"]
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
    has_active_canvas: bool,
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
    if type(has_active_canvas) is not bool:
        raise LiveGateError("Grasshopper canvas observation is malformed")
    token = _sha256_value(
        [process_id, process_token, port, has_active_canvas, document_id]
    )
    return {
        "document_id": document_id,
        "has_active_canvas": has_active_canvas,
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


def _gh_edit_solve_projection(data: Mapping[str, Any]) -> dict[str, Any]:
    summary = _ci_get(data, "edit_summary")
    if not isinstance(summary, Mapping):
        raise _ScenarioFailure(
            "verification_failed", "Grasshopper edit solve evidence is absent"
        )
    return {
        "solve_scheduled": _ci_get(
            summary, "solve_scheduled", _ci_get(summary, "solveScheduled")
        ),
        "solver_locked": _ci_get(
            summary, "solver_locked", _ci_get(summary, "solverLocked")
        ),
        "solver_state_known": _ci_get(
            summary, "solver_state_known", _ci_get(summary, "solverStateKnown")
        ),
        "verification_deferred": _ci_get(
            summary,
            "verification_deferred",
            _ci_get(summary, "verificationDeferred"),
        ),
    }


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
    if not isinstance(outputs, list) or len(outputs) != 1:
        raise _ScenarioFailure("verification_failed", "Sphere output is absent")
    output = outputs[0]
    data = _ci_get(output, "data") if isinstance(output, Mapping) else None
    if (
        not isinstance(output, Mapping)
        or _ci_get(output, "idx") != 0
        or _ci_get(output, "name") != "Sphere"
        or _ci_get(output, "type") != "Sphere"
        or not isinstance(data, Mapping)
        or _ci_get(data, "structure") != "single"
        or _ci_get(data, "count") != 1
    ):
        raise _ScenarioFailure(
            "verification_failed", "Sphere output projection mismatch"
        )
    if _ci_get(diagnostics, "errors", 0) != 0 or _ci_get(diagnostics, "warnings", 0) != 0:
        raise _ScenarioFailure("verification_failed", "Grasshopper snapshot contains diagnostics")
    return {"components": components, "flows": flows, "diagnostics": dict(diagnostics)}


async def _run_grasshopper_forward(state: _RunState, recorder: _OperationRecorder) -> None:
    try:
        payload = _fixture_resource_path().read_bytes()
        _validate_fixture_bytes(payload)
        _atomic_write_bytes(state.scratch_path, payload)
        _register_artifact(
            state.result,
            state.scratch_path,
            state.artifact_dir,
            "scratch",
        )
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
        status_after_open["available"] is not True
        or status_after_open["has_active_canvas"] is not True
        or status_after_open["has_active_document"] is not True
        or status_after_open["ready_for_edit"] is not True
        or type(document_id) is not str
        or document_id == bootstrap_document_id
        or status_after_open["document_path"] != str(state.scratch_path)
        or status_after_open["object_count"] != 0
    ):
        raise _ScenarioFailure(
            "fixture_invalid",
            "opened Grasshopper canvas or document projection mismatch",
        )
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
        has_active_canvas=status_after_open["has_active_canvas"],
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
    state.gh_edit_may_have_applied = True
    edit_result = await recorder.call(
        "gh_edit", _grasshopper_edit_arguments(state.run_id, epoch)
    )
    edit_solve = _gh_edit_solve_projection(_data(edit_result, "gh_edit"))
    if not (
        edit_solve["solve_scheduled"] is True
        and edit_solve["solver_locked"] is False
        and edit_solve["solver_state_known"] is True
        and edit_solve["verification_deferred"] is True
    ):
        raise _ScenarioFailure(
            "verification_failed",
            "Grasshopper edit did not schedule the expected deferred solve",
        )

    solved_snapshot: Mapping[str, Any] | None = None
    solved_status: dict[str, Any] | None = None
    final_errors: list[Any] = []
    final_warnings: list[Any] = []
    settle_deadline = _monotonic() + GH_SOLVE_SETTLE_TIMEOUT_SECONDS
    while True:
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
        solve_settled = (
            status["ready_for_edit"] is True
            and status["solver_state_known"] is True
            and status["solver_enabled"] is True
            and status["solution_state"] == "PostProcess"
        )
        if verified is not None and not errors and not warnings and solve_settled:
            solved_snapshot = candidate
            solved_status = status
            final_errors, final_warnings = errors, warnings
            break
        remaining = settle_deadline - _monotonic()
        if remaining <= 0:
            break
        _sleep(min(GH_SOLVE_POLL_INTERVAL_SECONDS, remaining))
    if solved_snapshot is None:
        raise _ScenarioFailure("verification_failed", "Grasshopper edit did not settle to the expected solved projection")
    verified_projection = _verify_gh_edit(solved_snapshot, state.run_id)
    verification_projection = {
        **verified_projection,
        "solve": {"edit": edit_solve, "status": solved_status},
    }
    state.result.verification = {
        "passed": True,
        "projection": verification_projection,
        "projection_sha256": _sha256_value(verification_projection),
        "errors": final_errors,
        "warnings": final_warnings,
    }


async def _validate_rhino_restoration_target(
    state: _RunState,
    recorder: _OperationRecorder,
) -> tuple[dict[str, Any], list[str]]:
    expected = (
        state.result.pre_state.get("scratch_projection")
        if isinstance(state.result.pre_state, Mapping)
        else None
    )
    expected_keys = {
        "runtime_serial",
        "path",
        "modified",
        "object_count",
        "object_ids",
    }
    if (
        not isinstance(expected, Mapping)
        or set(expected) != expected_keys
        or type(expected["runtime_serial"]) is not int
        or expected["runtime_serial"] <= 0
        or type(expected["path"]) is not str
        or expected["path"] != str(state.scratch_path)
    ):
        raise OwnershipAmbiguous("Rhino restoration scratch identity is unknown")
    raw_validated_ids = state.created_rhino_ids
    if not isinstance(raw_validated_ids, list) or any(
        type(item) is not str or _GUID_RE.fullmatch(item) is None
        for item in raw_validated_ids
    ):
        raise OwnershipAmbiguous("Rhino restoration created-object identity is unknown")
    validated_ids = {item.lower() for item in raw_validated_ids}
    if len(validated_ids) != len(raw_validated_ids):
        raise OwnershipAmbiguous("Rhino restoration created-object identity is ambiguous")
    try:
        serial_result = await recorder.call(
            "rhino_execute", {"code": RUNTIME_SERIAL_CODE}
        )
        serial = _parse_runtime_serial(
            _script_output(serial_result, "rhino_execute")
        )
        document = _rhino_document_projection(
            _data(await recorder.call("rhino_document", {}), "rhino_document")
        )
        current_ids = _rhino_object_ids(
            _data(
                await recorder.call(
                    "rhino_objects", {"limit": 500, "offset": 0}
                ),
                "rhino_objects",
            )
        )
    except OwnershipAmbiguous:
        raise
    except Exception as exc:
        raise OwnershipAmbiguous(
            "Rhino restoration target identity could not be revalidated"
        ) from exc
    if (
        serial != expected["runtime_serial"]
        or document["path"] != expected["path"]
        or document["object_count"] != len(current_ids)
        or len(set(current_ids)) != len(current_ids)
    ):
        raise OwnershipAmbiguous("Rhino restoration scratch identity drift")
    if not set(current_ids).issubset(validated_ids):
        raise OwnershipAmbiguous(
            "Rhino restoration observed an unvalidated object identity"
        )
    return document, current_ids


async def _restore_rhino(state: _RunState, recorder: _OperationRecorder) -> bool:
    state.result.restoration["attempted"] = True
    _, current_ids = await _validate_rhino_restoration_target(state, recorder)
    remaining_gate_ids = sorted(current_ids)
    if remaining_gate_ids:
        await recorder.call("rhino_delete", {"ids": remaining_gate_ids})
    dirty, current_ids = await _validate_rhino_restoration_target(state, recorder)
    if current_ids:
        return False
    if remaining_gate_ids and dirty["modified"] is not True:
        return False
    await recorder.call("rhino_document_ops", {"action": "save", "path": str(state.scratch_path)})
    document, ids = await _validate_rhino_restoration_target(state, recorder)
    expected = state.result.pre_state.get("scratch_projection") if state.result.pre_state else None
    restored = {
        "runtime_serial": expected["runtime_serial"],
        "path": document["path"],
        "modified": document["modified"],
        "object_count": document["object_count"],
        "object_ids": ids,
    }
    matches = isinstance(expected, Mapping) and restored == dict(expected)
    state.result.restoration["in_process_projection_matches_declared"] = matches
    return matches and state.scratch_path.is_file()


async def _observe_grasshopper_restoration(
    state: _RunState, recorder: _OperationRecorder
) -> tuple[dict[str, Any], bool]:
    expected = (
        state.result.pre_state.get("scratch_projection")
        if isinstance(state.result.pre_state, Mapping)
        else None
    )
    expected_keys = {
        "document_id",
        "has_active_canvas",
        "gate_canvas_token",
        "path",
        "object_count",
        "component_ids",
        "wires",
        "errors",
        "warnings",
    }
    target = state.result.target
    if (
        not isinstance(expected, Mapping)
        or set(expected) != expected_keys
        or type(expected["document_id"]) is not str
        or expected["has_active_canvas"] is not True
        or type(expected["gate_canvas_token"]) is not str
        or type(expected["path"]) is not str
        or expected["path"] != str(state.scratch_path)
        or type(expected["object_count"]) is not int
        or expected["object_count"] != 0
        or expected["component_ids"] != []
        or expected["wires"] != []
        or not isinstance(target, Mapping)
        or type(target.get("process_start_token")) is not str
    ):
        raise OwnershipAmbiguous(
            "Grasshopper restoration scratch identity is unknown"
        )
    try:
        snapshot = _data(await recorder.call("gh_snapshot", {}), "gh_snapshot")
        errors, warnings = _errors_projection(
            _data(await recorder.call("gh_errors", {}), "gh_errors")
        )
        status = _gh_status_projection(
            _data(await recorder.call("gh_status", {}), "gh_status")
        )
        document_id = status["document_id"]
        if type(document_id) is not str:
            raise LiveGateError("Grasshopper restoration target identity is absent")
        projection = _snapshot_projection(
            snapshot,
            process_id=state.record.pid,
            process_token=target["process_start_token"],
            port=state.record.port,
            document_id=document_id,
            has_active_canvas=status["has_active_canvas"],
        )
        components = _ci_get(snapshot, "components")
        flows = _ci_get(snapshot, "flows")
        if not isinstance(components, list) or not isinstance(flows, list):
            raise LiveGateError("Grasshopper restoration state is malformed")
    except OwnershipAmbiguous:
        raise
    except Exception as exc:
        raise OwnershipAmbiguous(
            "Grasshopper restoration target could not be revalidated"
        ) from exc
    if not (
        status["has_active_canvas"] is True
        and status["has_active_document"] is True
        and document_id == expected["document_id"]
        and status["document_path"] == expected["path"]
        and projection["document_id"] == expected["document_id"]
        and projection["gate_canvas_token"] == expected["gate_canvas_token"]
        and projection["path"] == expected["path"]
        and type(status["object_count"]) is int
        and type(projection["object_count"]) is int
        and status["object_count"] == len(components)
        and projection["object_count"] == len(components)
    ):
        raise OwnershipAmbiguous("Grasshopper restoration scratch identity drift")

    by_id: dict[str, Mapping[str, Any]] = {}
    for component in components:
        component_id = _ci_get(component, "id") if isinstance(component, Mapping) else None
        if (
            type(component_id) is not str
            or component_id not in {"C1", "C2"}
            or component_id in by_id
        ):
            raise OwnershipAmbiguous(
                "Grasshopper restoration observed an unknown component"
            )
        by_id[component_id] = component
    if flows not in ([], ["C1.O0>C2.I1"]):
        raise OwnershipAmbiguous(
            "Grasshopper restoration observed an unknown wire"
        )
    wired = flows == ["C1.O0>C2.I1"]
    if wired and set(by_id) != {"C1", "C2"}:
        raise OwnershipAmbiguous(
            "Grasshopper restoration wire endpoints are incomplete"
        )
    slider = by_id.get("C1")
    if slider is not None:
        value = _ci_get(slider, "value")
        if not (
            _ci_get(slider, "type") == "NumberSlider"
            and _ci_get(slider, "nick")
            == f"RookContainmentRadius-{state.run_id}"
            and _ci_get(slider, "pos") == [100, 100]
            and isinstance(value, Mapping)
            and _ci_get(value, "type") == "slider"
            and _ci_get(value, "min") == 1
            and _ci_get(value, "max") == 9
            and _ci_get(value, "val") == 4
        ):
            raise OwnershipAmbiguous(
                "Grasshopper restoration observed an altered slider"
            )
    sphere = by_id.get("C2")
    if sphere is not None:
        inputs = _ci_get(sphere, "inputs")
        radius_input = next(
            (
                item
                for item in inputs
                if isinstance(item, Mapping) and _ci_get(item, "idx") == 1
            ),
            None,
        ) if isinstance(inputs, list) else None
        if not (
            _ci_get(sphere, "type") == "Component"
            and str(_ci_get(sphere, "componentGuid", "")).lower()
            == SPHERE_COMPONENT_GUID
            and _ci_get(sphere, "name") == "Sphere"
            and _ci_get(sphere, "pos") == [400, 100]
            and isinstance(radius_input, Mapping)
            and _ci_get(radius_input, "name") == "Radius"
            and _ci_get(radius_input, "sources") == (1 if wired else 0)
        ):
            raise OwnershipAmbiguous(
                "Grasshopper restoration observed an altered Sphere"
            )
    return projection, not errors and not warnings


async def _restore_grasshopper(state: _RunState, recorder: _OperationRecorder) -> bool:
    state.result.restoration["attempted"] = True
    expected = state.result.pre_state.get("scratch_projection") if state.result.pre_state else None
    if not isinstance(expected, Mapping):
        return False
    if state.gh_edit_may_have_applied:
        while True:
            observed, clean = await _observe_grasshopper_restoration(state, recorder)
            matched = clean and observed == dict(expected)
            if matched or state.gh_undo_attempts >= 4:
                break
            state.gh_undo_attempts += 1
            await recorder.call("gh_undo", {})
        state.result.restoration["in_process_projection_matches_declared"] = matched
        return matched
    state.result.restoration["in_process_projection_matches_declared"] = True
    return True


def _cleanup_owned_target(state: _RunState, diagnostics: list[str]) -> bool:
    if state.process is None:
        return False
    owned_process = getattr(state.process, "process", state.process)
    live_at_entry = owned_process.poll() is None
    state.cleanup_live_at_entry = live_at_entry
    graceful_confirmed = False
    forced = False
    if not live_at_entry:
        diagnostics.append(
            f"owned process pid {owned_process.pid} had already exited before cleanup"
        )
    else:
        try:
            forced = _request_graceful_close(owned_process, diagnostics)
            graceful_confirmed = not forced and owned_process.poll() is not None
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
            scratch_relative = state.scratch_path.relative_to(
                state.artifact_dir
            ).as_posix()
            state.result.artifacts = [
                item
                for item in state.result.artifacts
                if item["relative_path"] != scratch_relative
            ]
        except OSError:
            scratch_disposed = False
    state.result.restoration["prior_identity_or_absence_restored"] = True
    state.result.restoration["scratch_disposed"] = scratch_disposed
    state.result.restoration["discovery_removed"] = discovery_removed
    return (
        live_at_entry
        and graceful_confirmed
        and not forced
        and scratch_disposed
        and discovery_removed
    )


def _restoration_is_verified(state: _RunState, *, cleanup_ok: bool) -> bool:
    restoration = state.result.restoration
    return bool(
        cleanup_ok
        and restoration["ownership_certain"] is True
        and restoration["attempted"] is True
        and restoration["in_process_projection_matches_declared"] is True
        and restoration["prior_identity_or_absence_restored"] is True
        and restoration["scratch_disposed"] is True
        and restoration["discovery_removed"] is True
    )


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
    started_at = _utc_now()
    result = _new_result(scenario, run_id, started_at)
    rhino_path = Path(rhino_exe).expanduser().resolve()
    owned_dir = _claim_artifact_directory(Path(artifact_dir), run_id)
    state = _RunState(
        scenario=scenario,
        run_id=run_id,
        artifact_dir=owned_dir,
        rhino_exe=rhino_path,
        started_at=started_at,
        result=result,
    )
    failure: _ScenarioFailure | None = None
    interruption: BaseException | None = None
    interruption_label: str | None = None
    diagnostics: list[str] = []
    try:
        try:
            _register_artifact(
                result,
                owned_dir / OWNERSHIP_MARKER,
                owned_dir,
                "ownership_marker",
            )
        except Exception as exc:
            raise _ScenarioFailure(
                "runtime_origin_invalid",
                "artifact ownership marker evidence registration failed",
            ) from exc

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
    except BaseException as exc:
        interruption = exc
        interruption_label = (
            "authorization_rejected"
            if not state.authorized
            else "mutation_failed"
            if state.mutation_started
            else "verification_failed"
        )

    if failure is not None or interruption is not None:
        if not state.authorized and result.operations:
            try:
                _discard_pre_authorization_operations(state)
            except Exception as discard_exc:
                if failure is not None:
                    failure = _ScenarioFailure(
                        "cleanup_failed", _bounded_detail(discard_exc)
                    )
                else:
                    _record_diagnostic(
                        state, "cleanup", "cleanup_failed", discard_exc
                    )
        result.success = False
        if failure is not None:
            result.failure_label = failure.label
            _record_diagnostic(state, "scenario", failure.label, failure)
        if interruption is not None:
            if result.failure_label is None:
                result.failure_label = interruption_label
            _record_diagnostic(state, "scenario", "interrupted", interruption)

    if (
        state.ownership_certain
        and state.process is not None
        and state.authorized
        and state.mutation_started
        and result.restoration["in_process_projection_matches_declared"] is not True
        and (
            interruption is not None
            or result.restoration["attempted"] is not True
        )
    ):
        for restore_attempt in range(2):
            try:
                recorder = _OperationRecorder(state)
                restored = asyncio.run(
                    _restore_rhino(state, recorder)
                    if scenario == "rhino"
                    else _restore_grasshopper(state, recorder)
                )
                if not restored and result.failure_label != "ownership_ambiguous":
                    result.failure_label = "restoration_failed"
                break
            except OwnershipAmbiguous:
                state.ownership_certain = False
                result.failure_label = "ownership_ambiguous"
                break
            except Exception as restore_exc:
                if result.failure_label != "ownership_ambiguous":
                    result.failure_label = "restoration_failed"
                _record_diagnostic(state, "restoration", result.failure_label, restore_exc)
                break
            except BaseException as restore_interrupt:
                if interruption is None:
                    interruption = restore_interrupt
                    interruption_label = "restoration_failed"
                    if result.failure_label is None:
                        result.failure_label = interruption_label
                _record_diagnostic(
                    state, "restoration", "interrupted", restore_interrupt
                )
                if restore_attempt == 1:
                    break

    result.restoration["ownership_certain"] = state.ownership_certain
    cleanup_ok = False
    if state.process is not None and state.ownership_certain:
        for cleanup_attempt in range(2):
            try:
                cleanup_ok = _cleanup_owned_target(state, diagnostics)
                break
            except Exception as cleanup_exc:
                diagnostics.append(
                    f"owned cleanup failed: {_bounded_detail(cleanup_exc)}"
                )
                cleanup_ok = False
                break
            except BaseException as cleanup_interrupt:
                if interruption is None:
                    interruption = cleanup_interrupt
                    interruption_label = "cleanup_failed"
                    if result.failure_label is None:
                        result.failure_label = interruption_label
                _record_diagnostic(
                    state, "cleanup", "interrupted", cleanup_interrupt
                )
                if cleanup_attempt == 1:
                    break
        if not cleanup_ok:
            if state.cleanup_live_at_entry is False:
                result.failure_label = "cleanup_failed"
            elif result.failure_label not in {"ownership_ambiguous", "restoration_failed"}:
                result.failure_label = "cleanup_failed"
            result.success = False
    elif state.process is None:
        cleanup_ok = True

    result.restoration["verified"] = _restoration_is_verified(
        state, cleanup_ok=cleanup_ok
    )

    if diagnostics:
        _record_diagnostic(state, "cleanup", "cleanup_failed" if not cleanup_ok else "cleanup_notes", LiveGateError("; ".join(diagnostics)))

    if state.metrics_store is not None:
        try:
            _finalize_telemetry(state)
        except _ScenarioFailure as telemetry_failure:
            result.success = False
            result.failure_label = telemetry_failure.label
            _record_diagnostic(state, "telemetry", telemetry_failure.label, telemetry_failure)
        except BaseException as telemetry_interrupt:
            if interruption is None:
                interruption = telemetry_interrupt
                interruption_label = "telemetry_changed"
                if result.failure_label is None:
                    result.failure_label = interruption_label
            _record_diagnostic(
                state, "telemetry", "interrupted", telemetry_interrupt
            )

    if interruption is not None:
        result.success = False
        if result.failure_label is None:
            result.failure_label = interruption_label or "verification_failed"
    elif failure is None and result.failure_label is None:
        result.success = True
        if not result.restoration["verified"]:
            result.success = False
            result.failure_label = "restoration_failed"
    else:
        result.success = False
        if result.failure_label is None:
            result.failure_label = failure.label if failure is not None else "cleanup_failed"

    if state.scratch_path is not None and state.scratch_path.is_file():
        _register_artifact(
            result,
            state.scratch_path,
            owned_dir,
            "scratch",
        )

    if not any(
        item.get("relative_path") == OWNERSHIP_MARKER
        for item in result.artifacts
        if isinstance(item, Mapping)
    ):
        try:
            _register_artifact(
                result,
                owned_dir / OWNERSHIP_MARKER,
                owned_dir,
                "ownership_marker",
            )
        except Exception as marker_exc:
            result.success = False
            if result.failure_label is None:
                result.failure_label = "runtime_origin_invalid"
            _record_diagnostic(
                state,
                "evidence",
                result.failure_label,
                marker_exc,
            )

    result.ended_at = _utc_now()
    path, digest = _write_final_evidence_pair(owned_dir, scenario, result.to_dict())
    if path.name != f"{scenario}-scenario.json":
        raise FinalEvidenceWriteError("final evidence path drift")
    _emit_jsonl(_scenario_result_record(result, digest))
    if interruption is not None:
        raise interruption
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


def _closed_mapping(
    value: object,
    keys: set[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise LiveGateError(f"{label} schema drift")
    return value


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _is_utc_timestamp(value: object) -> bool:
    if type(value) is not str or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def _validate_runtime_result(value: object) -> Mapping[str, Any] | None:
    if value is None:
        return None
    runtime = _closed_mapping(
        value,
        {"python_executable", "installed_root", "cwd", "sys_path", "rook_origins"},
        "runtime evidence",
    )
    if not all(
        type(runtime[key]) is str
        for key in ("python_executable", "installed_root", "cwd")
    ):
        raise LiveGateError("runtime evidence path type drift")
    sys_path = runtime["sys_path"]
    origins = runtime["rook_origins"]
    if (
        not isinstance(sys_path, list)
        or not all(type(item) is str for item in sys_path)
        or not isinstance(origins, Mapping)
        or not all(
            type(key) is str and type(origin) is str
            for key, origin in origins.items()
        )
    ):
        raise LiveGateError("runtime evidence collection type drift")
    return runtime


def _validate_target_result(value: object) -> Mapping[str, Any] | None:
    if value is None:
        return None
    target = _closed_mapping(
        value,
        {
            "process_id",
            "port",
            "process_start_token",
            "discovery_record_sha256",
            "scratch_path",
            "ownership_certain",
        },
        "target evidence",
    )
    if (
        type(target["process_id"]) is not int
        or target["process_id"] <= 0
        or type(target["port"]) is not int
        or not 1 <= target["port"] <= 65535
        or type(target["process_start_token"]) is not str
        or _TOKEN_RE.fullmatch(target["process_start_token"]) is None
        or not _is_sha256(target["discovery_record_sha256"])
        or type(target["scratch_path"]) is not str
        or not target["scratch_path"]
        or type(target["ownership_certain"]) is not bool
    ):
        raise LiveGateError("target evidence type drift")
    return target


def _validate_authorization_result(
    value: object,
    *,
    scenario: str,
    run_id: str,
    target: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if value is None:
        return None
    authorization = _closed_mapping(
        value,
        {
            "nonce",
            "challenge_sha256",
            "authorized_at",
            "preflight_sha256",
            "pre_mutation_sha256",
            "state_unchanged",
        },
        "authorization evidence",
    )
    authorized_at = authorization["authorized_at"]
    pre_mutation = authorization["pre_mutation_sha256"]
    if (
        type(authorization["nonce"]) is not str
        or _TOKEN_RE.fullmatch(authorization["nonce"]) is None
        or not _is_sha256(authorization["challenge_sha256"])
        or (authorized_at is not None and not _is_utc_timestamp(authorized_at))
        or not _is_sha256(authorization["preflight_sha256"])
        or (pre_mutation is not None and not _is_sha256(pre_mutation))
        or type(authorization["state_unchanged"]) is not bool
    ):
        raise LiveGateError("authorization evidence type drift")
    if target is None:
        raise LiveGateError("authorization evidence has no bound target")
    expected_challenge = _build_authorization_challenge(
        scenario=scenario,
        run_id=run_id,
        nonce=authorization["nonce"],
        target={
            "label": AUTHORIZATION_LABELS[scenario],
            "process_id": target["process_id"],
            "port": target["port"],
            "scratch_path": target["scratch_path"],
        },
    )
    if authorization["challenge_sha256"] != _sha256_value(expected_challenge):
        raise LiveGateError("authorization challenge digest mismatch")
    state_unchanged = authorization["state_unchanged"]
    if authorized_at is None:
        relationship_valid = pre_mutation is None and state_unchanged is False
    elif pre_mutation is None:
        relationship_valid = state_unchanged is False
    else:
        relationship_valid = state_unchanged is (
            pre_mutation == authorization["preflight_sha256"]
        )
    if not relationship_valid:
        raise LiveGateError("authorization state relationship drift")
    return authorization


def _validate_host_projection(
    value: object,
    *,
    scenario: str,
) -> Mapping[str, Any]:
    if scenario == "rhino":
        projection = _closed_mapping(
            value,
            {
                "prior_active_document_runtime_serial",
                "prior_path",
                "prior_modified",
            },
            "Rhino host projection",
        )
        if (
            type(projection["prior_active_document_runtime_serial"]) is not int
            or projection["prior_active_document_runtime_serial"] <= 0
            or type(projection["prior_path"]) is not str
            or type(projection["prior_modified"]) is not bool
        ):
            raise LiveGateError("Rhino host projection type drift")
        return projection
    projection = _closed_mapping(
        value,
        {"has_active_canvas", "document_id"},
        "Grasshopper host projection",
    )
    if (
        type(projection["has_active_canvas"]) is not bool
        or projection["has_active_canvas"] is not False
        or projection["document_id"] is not None
    ):
        raise LiveGateError("Grasshopper host projection type drift")
    return projection


def _validate_scratch_projection(
    value: object,
    *,
    scenario: str,
) -> Mapping[str, Any]:
    if scenario == "rhino":
        projection = _closed_mapping(
            value,
            {"runtime_serial", "path", "modified", "object_count", "object_ids"},
            "Rhino scratch projection",
        )
        object_ids = projection["object_ids"]
        if (
            type(projection["runtime_serial"]) is not int
            or projection["runtime_serial"] <= 0
            or type(projection["path"]) is not str
            or type(projection["modified"]) is not bool
            or type(projection["object_count"]) is not int
            or projection["object_count"] < 0
            or not isinstance(object_ids, list)
            or not all(
                type(item) is str and _GUID_RE.fullmatch(item) is not None
                for item in object_ids
            )
            or projection["object_count"] != len(object_ids)
        ):
            raise LiveGateError("Rhino scratch projection type drift")
        return projection
    projection = _closed_mapping(
        value,
        {
            "document_id",
            "has_active_canvas",
            "gate_canvas_token",
            "path",
            "object_count",
            "component_ids",
            "wires",
            "errors",
            "warnings",
        },
        "Grasshopper scratch projection",
    )
    component_ids = projection["component_ids"]
    wires = projection["wires"]
    if (
        type(projection["document_id"]) is not str
        or not projection["document_id"]
        or projection["has_active_canvas"] is not True
        or not _is_sha256(projection["gate_canvas_token"])
        or type(projection["path"]) is not str
        or type(projection["object_count"]) is not int
        or projection["object_count"] < 0
        or not isinstance(component_ids, list)
        or not all(type(item) is str for item in component_ids)
        or projection["object_count"] != len(component_ids)
        or not isinstance(wires, list)
        or not all(type(item) is str for item in wires)
        or type(projection["errors"]) is not int
        or projection["errors"] < 0
        or type(projection["warnings"]) is not int
        or projection["warnings"] < 0
    ):
        raise LiveGateError("Grasshopper scratch projection type drift")
    return projection


def _validate_pre_state_result(
    value: object,
    *,
    scenario: str,
) -> Mapping[str, Any] | None:
    if value is None:
        return None
    pre_state = _closed_mapping(
        value,
        {"host_projection", "host_sha256", "scratch_projection", "scratch_sha256"},
        "pre-state evidence",
    )
    host = _validate_host_projection(pre_state["host_projection"], scenario=scenario)
    if (
        not _is_sha256(pre_state["host_sha256"])
        or pre_state["host_sha256"] != _sha256_value(host)
    ):
        raise LiveGateError("pre-state host projection digest drift")
    scratch = pre_state["scratch_projection"]
    scratch_sha = pre_state["scratch_sha256"]
    if scratch is None:
        if scratch_sha is not None:
            raise LiveGateError("pre-state scratch nullability drift")
    else:
        scratch_projection = _validate_scratch_projection(
            scratch,
            scenario=scenario,
        )
        if not _is_sha256(scratch_sha) or scratch_sha != _sha256_value(
            scratch_projection
        ):
            raise LiveGateError("pre-state scratch projection digest drift")
    return pre_state


def _validate_verification_result(value: object) -> Mapping[str, Any]:
    verification = _closed_mapping(
        value,
        {"passed", "projection", "projection_sha256", "errors", "warnings"},
        "verification evidence",
    )
    projection = verification["projection"]
    projection_sha = verification["projection_sha256"]
    if (
        type(verification["passed"]) is not bool
        or not isinstance(verification["errors"], list)
        or not isinstance(verification["warnings"], list)
    ):
        raise LiveGateError("verification evidence type drift")
    if projection is None:
        if projection_sha is not None:
            raise LiveGateError("verification projection nullability drift")
    elif (
        not isinstance(projection, Mapping)
        or not _is_sha256(projection_sha)
        or projection_sha != _sha256_value(projection)
    ):
        raise LiveGateError("verification projection digest drift")
    return verification


def _validate_restoration_result(value: object) -> Mapping[str, Any]:
    restoration = _closed_mapping(
        value,
        {
            "ownership_certain",
            "attempted",
            "verified",
            "in_process_projection_matches_declared",
            "prior_identity_or_absence_restored",
            "scratch_disposed",
            "discovery_removed",
        },
        "restoration evidence",
    )
    if not all(type(item) is bool for item in restoration.values()):
        raise LiveGateError("restoration evidence type drift")
    return restoration


def _validate_telemetry_result(value: object) -> Mapping[str, Any] | None:
    if value is None:
        return None
    telemetry = _closed_mapping(
        value,
        {
            "process_id",
            "process_start_token",
            "before_sha256",
            "after_sha256",
            "delta_count",
            "events_added",
        },
        "telemetry evidence",
    )
    if (
        type(telemetry["process_id"]) is not int
        or telemetry["process_id"] <= 0
        or type(telemetry["process_start_token"]) is not str
        or _TOKEN_RE.fullmatch(telemetry["process_start_token"]) is None
        or not _is_sha256(telemetry["before_sha256"])
    ):
        raise LiveGateError("telemetry evidence type drift")
    after = telemetry["after_sha256"]
    delta = telemetry["delta_count"]
    events = telemetry["events_added"]
    if after is None or delta is None or events is None:
        if not (after is None and delta is None and events is None):
            raise LiveGateError("telemetry evidence nullability drift")
    elif (
        not _is_sha256(after)
        or type(delta) is not int
        or delta < 0
        or not isinstance(events, list)
        or delta != len(events)
    ):
        raise LiveGateError("telemetry final evidence type drift")
    return telemetry


def _validate_diagnostics_result(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise LiveGateError("diagnostic evidence is malformed")
    diagnostics: list[Mapping[str, Any]] = []
    for item in value:
        diagnostic = _closed_mapping(
            item,
            {"stage", "label", "relative_path", "sha256"},
            "diagnostic evidence entry",
        )
        if (
            type(diagnostic["stage"]) is not str
            or type(diagnostic["label"]) is not str
            or type(diagnostic["relative_path"]) is not str
            or not _is_sha256(diagnostic["sha256"])
        ):
            raise LiveGateError("diagnostic evidence entry type drift")
        diagnostics.append(diagnostic)
    return diagnostics


def _validate_nested_scenario_result(
    evidence: Mapping[str, Any],
    *,
    scenario: str,
) -> list[Mapping[str, Any]]:
    if (
        type(evidence["schema_version"]) is not int
        or evidence["schema_version"] != SCHEMA_VERSION
        or type(evidence["scenario"]) is not str
        or evidence["scenario"] != scenario
        or type(evidence["run_id"]) is not str
        or _TOKEN_RE.fullmatch(evidence["run_id"]) is None
        or not _is_utc_timestamp(evidence["started_at"])
        or not _is_utc_timestamp(evidence["ended_at"])
        or evidence["ended_at"] < evidence["started_at"]
    ):
        raise LiveGateError("final evidence scalar type drift")
    runtime = _validate_runtime_result(evidence["runtime"])
    target = _validate_target_result(evidence["target"])
    authorization = _validate_authorization_result(
        evidence["authorization"],
        scenario=scenario,
        run_id=evidence["run_id"],
        target=target,
    )
    pre_state = _validate_pre_state_result(evidence["pre_state"], scenario=scenario)
    verification = _validate_verification_result(evidence["verification"])
    restoration = _validate_restoration_result(evidence["restoration"])
    telemetry = _validate_telemetry_result(evidence["telemetry"])
    diagnostics = _validate_diagnostics_result(evidence["diagnostics"])
    if runtime is None and any(
        item is not None for item in (target, authorization, pre_state, telemetry)
    ):
        raise LiveGateError("runtime evidence nullability drift")
    if target is None and any(
        item is not None for item in (authorization, pre_state)
    ):
        raise LiveGateError("target evidence nullability drift")
    if authorization is not None and (target is None or pre_state is None):
        raise LiveGateError("authorization evidence nullability drift")
    if pre_state is not None and target is None:
        raise LiveGateError("pre-state evidence nullability drift")
    failure_label = evidence["failure_label"]
    if failure_label == "runtime_origin_invalid" and any(
        item is not None for item in (target, authorization, pre_state, telemetry)
    ):
        raise LiveGateError("runtime-origin failure contains downstream evidence")
    if failure_label == "launch_failed" and any(
        item is not None for item in (target, authorization, pre_state)
    ):
        raise LiveGateError("launch failure contains downstream evidence")
    if failure_label == "readiness_failed" and any(
        item is not None for item in (authorization, pre_state)
    ):
        raise LiveGateError("readiness failure contains downstream evidence")
    if failure_label in {"preflight_blocked", "authorization_rejected"} and evidence[
        "operations"
    ] != []:
        raise LiveGateError("pre-authorization failure contains operation evidence")
    if evidence["success"]:
        if any(
            item is None
            for item in (runtime, target, authorization, pre_state, telemetry)
        ):
            raise LiveGateError("successful evidence contains a null required section")
        if (
            authorization["authorized_at"] is None
            or authorization["pre_mutation_sha256"] is None
            or authorization["state_unchanged"] is not True
            or verification["passed"] is not True
            or verification["projection"] is None
            or restoration["verified"] is not True
            or not all(restoration.values())
            or telemetry["after_sha256"] is None
            or telemetry["delta_count"] != 0
            or telemetry["events_added"] != []
        ):
            raise LiveGateError("successful evidence state relationship drift")
    return diagnostics


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
    success = evidence["success"]
    failure_label = evidence["failure_label"]
    if type(success) is not bool or (success and failure_label is not None) or (
        not success
        and (type(failure_label) is not str or failure_label not in FAILURE_LABELS)
    ):
        raise LiveGateError("final evidence success/failure relationship drift")
    diagnostics = _validate_nested_scenario_result(evidence, scenario=scenario)
    artifacts = evidence["artifacts"]
    if not isinstance(artifacts, list):
        raise LiveGateError("artifact inventory is malformed")
    inventory: dict[str, Mapping[str, Any]] = {}
    for item in artifacts:
        if not isinstance(item, Mapping) or set(item) != {"kind", "relative_path", "sha256", "size"}:
            raise LiveGateError("artifact inventory entry is malformed")
        if (
            type(item["kind"]) is not str
            or type(item["relative_path"]) is not str
            or not _is_sha256(item["sha256"])
            or type(item["size"]) is not int
            or item["size"] < 0
            or item["relative_path"] in inventory
        ):
            raise LiveGateError("artifact inventory entry type drift")
        path = _safe_relative(root, item["relative_path"])
        if not path.is_file():
            raise LiveGateError("artifact inventory file is missing")
        content = path.read_bytes()
        if _sha256_bytes(content) != item["sha256"] or len(content) != item["size"]:
            raise LiveGateError("artifact inventory digest mismatch")
        inventory[str(item["relative_path"])] = item
    marker = inventory.get(OWNERSHIP_MARKER)
    if marker is None or marker["kind"] != "ownership_marker":
        raise LiveGateError("ownership marker inventory binding mismatch")
    marker_content = (root / OWNERSHIP_MARKER).read_bytes()
    try:
        marker_payload = json.loads(marker_content)
    except Exception as exc:
        raise LiveGateError("ownership marker is malformed") from exc
    if (
        marker_content != _canonical_json_bytes(marker_payload)
        or not isinstance(marker_payload, Mapping)
        or set(marker_payload) != {"process_id", "run_id", "schema_version"}
        or type(marker_payload["process_id"]) is not int
        or marker_payload["process_id"] <= 0
        or marker_payload["run_id"] != evidence["run_id"]
        or type(marker_payload["schema_version"]) is not int
        or marker_payload["schema_version"] != SCHEMA_VERSION
        or (
            evidence["telemetry"] is not None
            and marker_payload["process_id"]
            != evidence["telemetry"]["process_id"]
        )
    ):
        raise LiveGateError("ownership marker content binding mismatch")
    for diagnostic in diagnostics:
        relative = diagnostic["relative_path"]
        if relative not in inventory:
            raise LiveGateError("diagnostic artifact is not enumerated")
        if inventory[relative]["sha256"] != diagnostic["sha256"]:
            raise LiveGateError("diagnostic artifact digest mismatch")
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
        if (
            not isinstance(operation, Mapping)
            or set(operation) != expected_keys
            or type(operation["index"]) is not int
            or operation["index"] != expected_index
            or type(operation["name"]) is not str
            or type(operation["arguments_path"]) is not str
            or not _is_sha256(operation["arguments_sha256"])
            or type(operation["result_path"]) is not str
            or not _is_sha256(operation["result_sha256"])
            or type(operation["success"]) is not bool
        ):
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
    declared_files = {
        f"{scenario}-scenario.json",
        f"{scenario}-scenario.sha256",
        *inventory.keys(),
    }
    actual_files = {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file()
    }
    if actual_files != declared_files:
        raise LiveGateError("artifact directory contains unenumerated files")
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
