from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
SCENARIOS = ("rhino", "grasshopper")
SPHERE_COMPONENT_GUID = "dabc854d-f50e-408a-b001-d043c7de151d"
FIXTURE_SIZE = 2708
FIXTURE_SHA256 = "2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df"
RESULT_FIELDS = (
    "schema_version",
    "scenario",
    "success",
    "run_id",
    "target",
    "authorization",
    "pre_state",
    "operations",
    "verification",
    "restoration",
    "telemetry",
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

_TOKEN_RE = re.compile(r"[0-9a-f]{32}")
_GUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_RUNTIME_SERIAL_CODE = (
    "import scriptcontext as sc\n"
    'print("ROOK_DOC_RUNTIME_SERIAL={0}".format(sc.doc.RuntimeSerialNumber))'
)
_DESCRIPTIONS = {
    "rhino": {
        "mutation": (
            "Save a fresh Rhino scratch document, create one named radius-4 sphere "
            "and one named scripted point at (10,0,0)."
        ),
        "verification": (
            "Observe exact object identities, names, geometry, bounding boxes, area, "
            "volume, point location, and document dirty state."
        ),
        "restoration": (
            "Delete only the two gate-owned objects, save the declared empty scratch "
            "state, restore the prior active-document absence by gracefully closing "
            "the gate-owned process, and dispose the scratch file."
        ),
    },
    "grasshopper": {
        "mutation": (
            "Open the exact empty staged GHX in a fresh gate-owned process, create "
            "one Number Slider (1..9, value 4), create the exact Sphere component, "
            "and connect T1.O0>T2.I1."
        ),
        "verification": (
            "Observe the exact component GUID, settings, topology, settled solve, "
            "Sphere output, and zero errors or warnings."
        ),
        "restoration": (
            "Use at most four gh_undo calls while ownership remains certain, restore "
            "the declared empty definition, gracefully close the gate-owned process "
            "to restore prior canvas absence, and dispose the scratch file."
        ),
    },
}


class LiveGateError(RuntimeError):
    pass


class OwnershipAmbiguous(LiveGateError):
    pass


@dataclass(frozen=True)
class ScenarioInputs:
    rhino_exe: Path
    expected_python: Path
    expected_package_root: Path
    forbidden_source_roots: tuple[Path, ...]
    output: Path


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _sha256_value(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "containment_empty.ghx"


def _validate_fixture() -> bytes:
    payload = _fixture_path().read_bytes()
    if len(payload) != FIXTURE_SIZE or hashlib.sha256(payload).hexdigest() != FIXTURE_SHA256:
        raise LiveGateError("fixture length or SHA-256 drift")
    if payload.startswith(b"\xef\xbb\xbf") or b"\r" in payload:
        raise LiveGateError("fixture encoding or newline drift")
    if not payload.endswith(b"\n") or payload.endswith(b"\n\n"):
        raise LiveGateError("fixture final newline drift")
    return payload


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
    *, scenario: str, run_id: str, nonce: str, target: Mapping[str, Any]
) -> dict[str, Any]:
    if (
        scenario not in SCENARIOS
        or _TOKEN_RE.fullmatch(run_id) is None
        or _TOKEN_RE.fullmatch(nonce) is None
    ):
        raise LiveGateError("invalid authorization identity")
    target_copy = dict(target)
    if set(target_copy) != {"label", "process_id", "port", "scratch_path"}:
        raise LiveGateError("authorization target schema drift")
    descriptions = _DESCRIPTIONS[scenario]
    hashes = {key: _sha256_value(value) for key, value in descriptions.items()}
    target_hash = _sha256_value(target_copy)
    response = (
        f"AUTHORIZE scenario={scenario} run={run_id} nonce={nonce} "
        f"target={target_hash} mutation={hashes['mutation']} "
        f"verify={hashes['verification']} restore={hashes['restoration']}"
    )
    return {
        "type": "authorization_required",
        "schema_version": SCHEMA_VERSION,
        "scenario": scenario,
        "run_id": run_id,
        "nonce": nonce,
        "target": target_copy,
        "target_sha256": target_hash,
        "mutation": descriptions["mutation"],
        "mutation_sha256": hashes["mutation"],
        "verification": descriptions["verification"],
        "verification_sha256": hashes["verification"],
        "restoration": descriptions["restoration"],
        "restoration_sha256": hashes["restoration"],
        "required_response": response,
    }


def _authorization_matches(challenge: Mapping[str, Any], raw_line: bytes) -> bool:
    if type(raw_line) is not bytes or not raw_line.endswith((b"\n", b"\r\n")):
        return False
    candidate = raw_line[:-2] if raw_line.endswith(b"\r\n") else raw_line[:-1]
    if b"\r" in candidate or b"\n" in candidate:
        return False
    expected = challenge.get("required_response")
    if type(expected) is not str:
        return False
    try:
        return candidate == expected.encode("ascii")
    except UnicodeEncodeError:
        return False


def _read_authorization_line() -> bytes:
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        raise LiveGateError("binary authorization input is unavailable")
    line = stream.readline(8194)
    if type(line) is not bytes or len(line) > 8193:
        raise LiveGateError("authorization line exceeds the bounded protocol")
    return line


def _new_result(scenario: str, run_id: str) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "scenario": scenario,
        "success": False,
        "run_id": run_id,
        "target": None,
        "authorization": None,
        "pre_state": None,
        "operations": [],
        "verification": None,
        "restoration": {
            "ownership_certain": True,
            "attempted": False,
            "verified": False,
            "manual_restoration_required": False,
            "scratch_disposed": False,
            "prior_state_restored": False,
        },
        "telemetry": None,
        "diagnostics": [],
    }


def _resolved_absolute(raw: str, label: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        raise LiveGateError(f"{label} must be absolute")
    return path.resolve()


def _inputs_from_namespace(args: argparse.Namespace) -> ScenarioInputs:
    inputs = ScenarioInputs(
        rhino_exe=_resolved_absolute(args.rhino_exe, "Rhino executable"),
        expected_python=_resolved_absolute(args.expected_python, "expected Python"),
        expected_package_root=_resolved_absolute(
            args.expected_package_root, "expected package root"
        ),
        forbidden_source_roots=tuple(
            _resolved_absolute(value, "forbidden source root")
            for value in args.forbidden_source_root
        ),
        output=_resolved_absolute(args.output, "output"),
    )
    if inputs.output.exists():
        raise LiveGateError("output must be a new file")
    if not inputs.output.parent.is_dir():
        raise LiveGateError("output parent must exist")
    return inputs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="live_gate.py")
    subs = parser.add_subparsers(dest="command", required=True)
    run = subs.add_parser("run")
    run.add_argument("--scenario", required=True, choices=SCENARIOS)
    run.add_argument("--rhino-exe", required=True)
    run.add_argument("--expected-python", required=True)
    run.add_argument("--expected-package-root", required=True)
    run.add_argument("--forbidden-source-root", required=True, action="append")
    run.add_argument("--output", required=True)
    return parser


def _beneath(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _validate_runtime_evidence(
    evidence: Mapping[str, Any],
    *,
    expected_python: Path,
    expected_package_root: Path,
    forbidden_source_roots: tuple[Path, ...],
) -> None:
    try:
        executable = Path(evidence["python_executable"]).resolve()
        sys_path = [Path(item).resolve() for item in evidence["sys_path"] if item]
        origins = {
            str(name): Path(path).resolve()
            for name, path in dict(evidence["rook_origins"]).items()
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveGateError("runtime evidence is malformed") from exc
    if executable != expected_python.resolve():
        raise LiveGateError("Python executable origin mismatch")
    for entry in sys_path:
        if any(_beneath(entry, root) or _beneath(root, entry) for root in forbidden_source_roots):
            raise LiveGateError("forbidden source root is present on sys.path")
    if not origins or any(not _beneath(origin, expected_package_root) for origin in origins.values()):
        raise LiveGateError("loaded rook module origin mismatch")


def _collect_runtime_evidence(inputs: ScenarioInputs) -> dict[str, Any]:
    if Path(sys.executable).resolve() != inputs.expected_python.resolve():
        raise LiveGateError("Python executable origin mismatch")
    for name in ("rook", "rook.server", "rook.rhino_launch", "rook.bridge"):
        importlib.import_module(name)
    origins: dict[str, str] = {}
    for name, module in tuple(sys.modules.items()):
        if name == "rook" or name.startswith("rook."):
            origin = getattr(module, "__file__", None)
            if origin:
                origins[name] = str(Path(origin).resolve())
    evidence = {
        "python_executable": str(Path(sys.executable).resolve()),
        "sys_path": [str(Path(item).resolve()) for item in sys.path if item],
        "rook_origins": origins,
    }
    _validate_runtime_evidence(
        evidence,
        expected_python=inputs.expected_python,
        expected_package_root=inputs.expected_package_root,
        forbidden_source_roots=inputs.forbidden_source_roots,
    )
    return evidence


def _data(envelope: object, tool: str) -> Mapping[str, Any]:
    if not isinstance(envelope, Mapping) or envelope.get("success") is not True:
        raise LiveGateError(f"{tool} failed")
    value = envelope.get("data")
    if not isinstance(value, Mapping):
        raise LiveGateError(f"{tool} returned malformed data")
    return value


def _get(mapping: Mapping[str, Any], name: str, default: Any = None) -> Any:
    folded = name.casefold()
    for key, value in mapping.items():
        if isinstance(key, str) and key.casefold() == folded:
            return value
    return default


class _InstalledSession:
    def __init__(self, started: Any, record: Any, process_token: str):
        self.started = started
        self.process = started.process
        self.record = record
        self.process_token = process_token
        self.record_path = Path(record.path).resolve()
        self.record_bytes = self.record_path.read_bytes()

    def _check(self) -> None:
        if (
            self.process.poll() is not None
            or self.started.pid != self.process.pid
            or self.record.pid != self.process.pid
            or Path(self.record.path).resolve() != self.record_path
            or self.record_path.read_bytes() != self.record_bytes
        ):
            raise OwnershipAmbiguous("owned Rhino process or discovery identity drift")

    async def call(self, name: str, arguments: Mapping[str, Any], allowlist: frozenset[str]):
        if name not in allowlist or "port" in arguments:
            raise LiveGateError("tool is outside the admitted scenario contract")
        self._check()
        from rook import server
        from rook.bridge import rhino_request_context

        bound = dict(arguments)
        bound["port"] = self.record.port
        try:
            with rhino_request_context(port=self.record.port, process_id=self.record.pid):
                return await server._call_tool_dispatch(name, bound)
        finally:
            self._check()


class _Recorder:
    def __init__(self, session: _InstalledSession, result: dict[str, object], allowlist: frozenset[str]):
        self.session = session
        self.result = result
        self.allowlist = allowlist

    async def call(self, name: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        envelope = await self.session.call(name, arguments, self.allowlist)
        operations = self.result["operations"]
        assert isinstance(operations, list)
        operations.append(
            {
                "index": len(operations) + 1,
                "name": name,
                "arguments": dict(arguments),
                "success": isinstance(envelope, Mapping) and envelope.get("success") is True,
            }
        )
        return envelope


def _document(data: Mapping[str, Any]) -> dict[str, Any]:
    path = _get(data, "path", "")
    count = _get(data, "objectCount")
    modified = _get(data, "modified")
    if type(path) is not str or type(count) is not int or type(modified) is not bool:
        raise LiveGateError("Rhino document projection is malformed")
    return {"path": path, "object_count": count, "modified": modified}


def _object_ids(data: Mapping[str, Any]) -> list[str]:
    objects = _get(data, "objects")
    if not isinstance(objects, list):
        raise LiveGateError("Rhino object projection is malformed")
    ids = []
    for item in objects:
        value = _get(item, "id") if isinstance(item, Mapping) else None
        if type(value) is not str or _GUID_RE.fullmatch(value) is None:
            raise LiveGateError("Rhino object identity is malformed")
        ids.append(value.lower())
    return sorted(ids)


def _script_output(envelope: object, tool: str) -> str:
    data = _data(envelope, tool)
    for key in ("output", "stdout", "result"):
        value = _get(data, key)
        if type(value) is str:
            return value
    raise LiveGateError(f"{tool} returned no output")


def _runtime_serial(output: str) -> int:
    matches = re.findall(r"(?m)^ROOK_DOC_RUNTIME_SERIAL=([1-9][0-9]*)$", output)
    if len(matches) != 1:
        raise LiveGateError("runtime serial marker mismatch")
    return int(matches[0])


async def _rhino_preflight(recorder: _Recorder) -> dict[str, Any]:
    await recorder.call("rhino_ping", {})
    serial = _runtime_serial(
        _script_output(
            await recorder.call("rhino_execute", {"code": _RUNTIME_SERIAL_CODE}),
            "rhino_execute",
        )
    )
    document = _document(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    ids = _object_ids(
        _data(
            await recorder.call("rhino_objects", {"limit": 500, "offset": 0}),
            "rhino_objects",
        )
    )
    if document != {"path": "", "object_count": 0, "modified": False} or ids:
        raise LiveGateError("fresh Rhino document is not empty and clean")
    return {"runtime_serial": serial, **document, "object_ids": ids}


def _gh_status(data: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "available": _get(data, "available"),
        "has_canvas": _get(data, "has_active_canvas", _get(data, "hasActiveCanvas")),
        "has_document": _get(data, "has_active_document", _get(data, "hasActiveDocument")),
        "document_id": _get(data, "document_id", _get(data, "documentId")),
        "document_path": _get(data, "document_path", _get(data, "documentPath", "")),
        "object_count": _get(data, "object_count", _get(data, "objectCount")),
        "ready": _get(data, "ready_for_edit", _get(data, "readyForEdit")),
        "solver_enabled": _get(data, "solverEnabled", _get(data, "solver_enabled")),
        "solver_known": _get(data, "solverStateKnown", _get(data, "solver_state_known")),
        "solution_state": _get(data, "solutionState", _get(data, "solution_state")),
    }
    if (
        not all(type(value[key]) is bool for key in ("available", "has_canvas", "has_document", "ready", "solver_known"))
        or type(value["object_count"]) is not int
        or type(value["document_path"]) is not str
    ):
        raise LiveGateError("Grasshopper status projection is malformed")
    return value


async def _grasshopper_preflight(recorder: _Recorder) -> dict[str, Any]:
    await recorder.call("rhino_ping", {})
    rhino = _document(_data(await recorder.call("rhino_document", {}), "rhino_document"))
    status = _gh_status(_data(await recorder.call("gh_status", {}), "gh_status"))
    if rhino != {"path": "", "object_count": 0, "modified": False}:
        raise LiveGateError("fresh Rhino host document is not empty and clean")
    if not (
        status["available"] is False
        and status["has_canvas"] is False
        and status["has_document"] is False
        and status["document_id"] is None
        and status["object_count"] == 0
        and status["ready"] is False
    ):
        raise LiveGateError("Grasshopper is already present in the owned process")
    return {"rhino": rhino, "grasshopper": status}


def _guid(value: object, label: str) -> str:
    if type(value) is not str or _GUID_RE.fullmatch(value) is None:
        raise LiveGateError(f"{label} is invalid")
    return value.lower()


def _verify_rhino_geometry(
    sphere: Mapping[str, Any], point: Mapping[str, Any], run_id: str, sphere_id: str, point_id: str
) -> dict[str, Any]:
    sphere_geometry = _get(sphere, "geometry")
    point_geometry = _get(point, "geometry")
    expected_sphere = {
        "id": sphere_id,
        "name": f"RookContainmentSphere-{run_id}",
        "type": "Brep",
        "bbox": {"min": [-4, -4, -4], "max": [4, 4, 4]},
    }
    if not isinstance(sphere_geometry, Mapping) or any(
        _get(sphere, key) != value for key, value in expected_sphere.items()
    ):
        raise LiveGateError("sphere identity or bounds mismatch")
    if not (
        _get(sphere_geometry, "type") == "Brep"
        and _get(sphere_geometry, "faceCount") == 1
        and _get(sphere_geometry, "edgeCount") == 1
        and _get(sphere_geometry, "vertexCount") == 2
        and _get(sphere_geometry, "isSolid") is True
        and _get(sphere_geometry, "isManifold") is True
        and abs(float(_get(sphere_geometry, "area")) - 201.0619) <= 0.001
        and abs(float(_get(sphere_geometry, "volume")) - 268.0826) <= 0.001
    ):
        raise LiveGateError("sphere geometry mismatch")
    if not (
        _get(point, "id") == point_id
        and _get(point, "name") == f"RookContainmentPoint-{run_id}"
        and _get(point, "type") == "Point"
        and isinstance(point_geometry, Mapping)
        and _get(point_geometry, "location") == [10, 0, 0]
    ):
        raise LiveGateError("point geometry mismatch")
    return {"sphere": dict(sphere), "point": dict(point)}


def _verify_gh_snapshot(snapshot: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    components = _get(snapshot, "components")
    flows = _get(snapshot, "flows")
    diagnostics = _get(snapshot, "diagnostics")
    if not isinstance(components, list) or len(components) != 2 or flows != ["C1.O0>C2.I1"]:
        raise LiveGateError("Grasshopper topology mismatch")
    slider = next((x for x in components if isinstance(x, Mapping) and _get(x, "type") == "NumberSlider"), None)
    sphere = next((x for x in components if isinstance(x, Mapping) and str(_get(x, "componentGuid", "")).lower() == SPHERE_COMPONENT_GUID), None)
    if not isinstance(slider, Mapping) or not isinstance(sphere, Mapping):
        raise LiveGateError("Grasshopper identities mismatch")
    value = _get(slider, "value")
    inputs = _get(sphere, "inputs")
    radius = next((x for x in inputs if isinstance(x, Mapping) and _get(x, "idx") == 1), None) if isinstance(inputs, list) else None
    outputs = _get(sphere, "outputs")
    output = outputs[0] if isinstance(outputs, list) and len(outputs) == 1 else None
    output_data = _get(output, "data") if isinstance(output, Mapping) else None
    if not (
        _get(slider, "id") == "C1"
        and _get(slider, "nick") == f"RookContainmentRadius-{run_id}"
        and isinstance(value, Mapping)
        and (_get(value, "min"), _get(value, "max"), _get(value, "val")) == (1, 9, 4)
        and _get(sphere, "id") == "C2"
        and _get(sphere, "name") == "Sphere"
        and isinstance(radius, Mapping)
        and _get(radius, "sources") == 1
        and isinstance(output_data, Mapping)
        and _get(output_data, "structure") == "single"
        and _get(output_data, "count") == 1
        and isinstance(diagnostics, Mapping)
        and _get(diagnostics, "errors", 0) == 0
        and _get(diagnostics, "warnings", 0) == 0
    ):
        raise LiveGateError("Grasshopper solve or output mismatch")
    return {"components": components, "flows": flows, "diagnostics": dict(diagnostics)}


def _telemetry_snapshot() -> tuple[Any, Mapping[str, Any]]:
    from rook.learning.metrics_store import get_metrics_store

    store = get_metrics_store()
    value = store.get_containment_denials_snapshot()
    if not isinstance(value, Mapping) or not isinstance(value.get("events"), list):
        raise LiveGateError("containment telemetry snapshot malformed")
    return store, value


def _telemetry_result(store: Any, before: Mapping[str, Any]) -> dict[str, Any]:
    after = store.get_containment_denials_snapshot()
    if not isinstance(after, Mapping) or after.get("events") != before.get("events"):
        raise LiveGateError("containment telemetry changed")
    return {
        "before_sha256": _sha256_value(before),
        "after_sha256": _sha256_value(after),
        "delta_count": 0,
        "events_added": [],
    }


def _launch_owned(inputs: ScenarioInputs) -> tuple[Any, Any, str]:
    from rook.rhino_launch import (
        OwnedRhinoDiscovery,
        build_launch_env,
        start_rhino_process,
        wait_for_rook_readiness,
    )

    launch = build_launch_env()
    discovery = OwnedRhinoDiscovery()
    started = start_rhino_process(
        inputs.rhino_exe,
        requested_scheme=None,
        env=launch.env,
        launch_env_report=launch.report,
    )
    readiness = wait_for_rook_readiness(started, discovery=discovery)
    if not readiness.outcome.ok or readiness.record is None:
        raise LiveGateError(readiness.outcome.message or "owned Rhino did not become ready")
    record = readiness.record
    if record.pid != started.pid or started.process.pid != started.pid:
        raise OwnershipAmbiguous("launch and discovery PID mismatch")
    record_info = Path(record.path).stat()
    if record_info.st_mtime + 0.001 < float(started.started_wall):
        raise OwnershipAmbiguous("owned discovery record predates this Rhino launch")
    token = _sha256_value([int(started.pid), float(started.started_wall)])[:32]
    return started, record, token


def _graceful_close(process: Any, diagnostics: list[object]) -> bool:
    from rook.runtime_harness import close_windows_for_pid, describe_windows_for_pid

    windows_before = describe_windows_for_pid(process.pid)
    posted = close_windows_for_pid(process.pid)
    try:
        process.wait(timeout=15.0)
    except Exception as exc:
        diagnostics.append(
            f"graceful close timed out for pid {process.pid}; posted={posted}; "
            f"windows_before={windows_before}; detail={str(exc)[:200]}"
        )
        return False
    return process.poll() is not None


async def _run_rhino(
    recorder: _Recorder, result: dict[str, object], run_id: str, scratch: Path
) -> tuple[list[str], bool]:
    before = await _rhino_preflight(recorder)
    result["pre_state"] = {"host": before, "scratch": None}
    challenge = _build_authorization_challenge(
        scenario="rhino",
        run_id=run_id,
        nonce=uuid.uuid4().hex,
        target=result["target"],
    )
    result["authorization"] = challenge
    print(_canonical_json_bytes(challenge).decode("utf-8"), flush=True)
    if not _authorization_matches(challenge, _read_authorization_line()):
        raise LiveGateError("authorization response did not match")
    repeated = await _rhino_preflight(recorder)
    if repeated != before:
        raise LiveGateError("Rhino state drifted after authorization")
    restoration = result["restoration"]
    assert isinstance(restoration, dict)
    restoration["attempted"] = True
    owned_ids: list[str] = []
    try:
        await recorder.call("rhino_document_ops", {"action": "save", "path": str(scratch)})
        sphere_id = _guid(
            _get(
                _data(
                    await recorder.call(
                        "rhino_create", _rhino_sphere_arguments(run_id)
                    ),
                    "rhino_create",
                ),
                "id",
            ),
            "sphere ID",
        )
        owned_ids.append(sphere_id)
        point_output = _script_output(
            await recorder.call(
                "rhino_execute", {"code": _rhino_point_script(run_id)}
            ),
            "rhino_execute",
        )
        points = re.findall(r"(?im)^ROOK_POINT_ID=([0-9a-f-]{36})$", point_output)
        if len(points) != 1:
            raise LiveGateError("point identity marker mismatch")
        point_id = _guid(points[0], "point ID")
        owned_ids.append(point_id)
        ids = _object_ids(
            _data(
                await recorder.call(
                    "rhino_objects", {"limit": 500, "offset": 0}
                ),
                "rhino_objects",
            )
        )
        if ids != sorted(owned_ids):
            raise LiveGateError("Rhino object identity set mismatch")
        geometry = _verify_rhino_geometry(
            _data(
                await recorder.call("rhino_geometry", {"id": sphere_id}),
                "rhino_geometry",
            ),
            _data(
                await recorder.call("rhino_geometry", {"id": point_id}),
                "rhino_geometry",
            ),
            run_id,
            sphere_id,
            point_id,
        )
        result["verification"] = {
            "passed": True,
            "objects": geometry,
            "object_ids": ids,
        }
    finally:
        current = _object_ids(
            _data(
                await recorder.call(
                    "rhino_objects", {"limit": 500, "offset": 0}
                ),
                "rhino_objects",
            )
        )
        if not set(current).issubset(set(owned_ids)):
            raise OwnershipAmbiguous(
                "Rhino restoration observed an object without a proven gate identity"
            )
        if current:
            await recorder.call("rhino_delete", {"ids": current})
        await recorder.call(
            "rhino_document_ops", {"action": "save", "path": str(scratch)}
        )
        empty = _object_ids(
            _data(
                await recorder.call(
                    "rhino_objects", {"limit": 500, "offset": 0}
                ),
                "rhino_objects",
            )
        )
        restoration["verified"] = not empty
    return owned_ids, restoration["verified"] is True


async def _run_grasshopper(
    recorder: _Recorder, result: dict[str, object], run_id: str, scratch: Path
) -> tuple[int, bool]:
    payload = _validate_fixture()
    before = await _grasshopper_preflight(recorder)
    result["pre_state"] = {"host": before, "scratch": None}
    challenge = _build_authorization_challenge(
        scenario="grasshopper",
        run_id=run_id,
        nonce=uuid.uuid4().hex,
        target=result["target"],
    )
    result["authorization"] = challenge
    print(_canonical_json_bytes(challenge).decode("utf-8"), flush=True)
    if not _authorization_matches(challenge, _read_authorization_line()):
        raise LiveGateError("authorization response did not match")
    repeated = await _grasshopper_preflight(recorder)
    if repeated != before:
        raise LiveGateError("Grasshopper state drifted after authorization")
    restoration = result["restoration"]
    assert isinstance(restoration, dict)
    restoration["attempted"] = True
    scratch_opened = False
    edit_may_have_applied = False
    undo_count = 0
    try:
        with scratch.open("xb") as stream:
            stream.write(payload)
        await recorder.call(
            "rhino_command", {"command": "_Grasshopper", "echo": False}
        )
        ready = None
        for _ in range(20):
            status = _gh_status(
                _data(await recorder.call("gh_status", {}), "gh_status")
            )
            if status["ready"] and status["has_canvas"] and status["has_document"]:
                ready = status
                break
            time.sleep(0.25)
        if ready is None:
            raise LiveGateError("Grasshopper did not become ready")
        bootstrap_id = ready["document_id"]
        await recorder.call("gh_document_open", {"path": str(scratch)})
        scratch_opened = True
        status = _gh_status(
            _data(await recorder.call("gh_status", {}), "gh_status")
        )
        if (
            status["document_id"] in (None, bootstrap_id)
            or status["document_path"] != str(scratch)
        ):
            raise LiveGateError("Grasshopper scratch identity mismatch")
        empty = _data(await recorder.call("gh_snapshot", {}), "gh_snapshot")
        if _get(empty, "components") != [] or _get(empty, "flows") != []:
            raise LiveGateError("Grasshopper fixture is not empty")
        result["pre_state"] = {"host": before, "scratch": dict(empty)}
        library = _data(
            await recorder.call("gh_library", {"search": "Sphere", "exact": True}),
            "gh_library",
        )
        components = _get(library, "components")
        if (
            _get(library, "count") != 1
            or not isinstance(components, list)
            or len(components) != 1
            or str(_get(components[0], "guid", "")).lower()
            != SPHERE_COMPONENT_GUID
        ):
            raise LiveGateError("exact Sphere library GUID mismatch")
        base = _data(await recorder.call("gh_snapshot", {}), "gh_snapshot")
        epoch = _get(base, "epoch")
        if type(epoch) is not int:
            raise LiveGateError("Grasshopper snapshot epoch is invalid")
        edit_may_have_applied = True
        await recorder.call("gh_edit", _grasshopper_edit_arguments(run_id, epoch))
        solved = None
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            candidate = _data(
                await recorder.call("gh_snapshot", {}), "gh_snapshot"
            )
            errors = _data(
                await recorder.call("gh_errors", {}), "gh_errors"
            )
            status = _gh_status(
                _data(await recorder.call("gh_status", {}), "gh_status")
            )
            try:
                projection = _verify_gh_snapshot(candidate, run_id)
            except LiveGateError:
                projection = None
            if (
                projection is not None
                and _get(errors, "errorCount") == 0
                and _get(errors, "warningCount") == 0
                and status["solver_enabled"] is True
                and status["solver_known"] is True
                and status["solution_state"] == "PostProcess"
            ):
                solved = projection
                break
            time.sleep(0.2)
        if solved is None:
            raise LiveGateError("Grasshopper edit did not settle")
        result["verification"] = {"passed": True, **solved}
    finally:
        if scratch_opened:
            while undo_count <= 4:
                snapshot = _data(
                    await recorder.call("gh_snapshot", {}), "gh_snapshot"
                )
                components = _get(snapshot, "components")
                flows = _get(snapshot, "flows")
                if components == [] and flows == []:
                    restoration["verified"] = True
                    break
                try:
                    _verify_gh_snapshot(snapshot, run_id)
                except LiveGateError as exc:
                    raise OwnershipAmbiguous(
                        "Grasshopper restoration observed an unproven partial state"
                    ) from exc
                if not edit_may_have_applied or undo_count == 4:
                    break
                await recorder.call("gh_undo", {})
                undo_count += 1
    return undo_count, restoration["verified"] is True


def _run_scenario(inputs: ScenarioInputs, scenario: str) -> dict[str, object]:
    if scenario not in SCENARIOS:
        raise LiveGateError("unsupported scenario")
    run_id = uuid.uuid4().hex
    result = _new_result(scenario, run_id)
    diagnostics = result["diagnostics"]
    restoration = result["restoration"]
    assert isinstance(diagnostics, list) and isinstance(restoration, dict)
    started = None
    scratch = inputs.output.parent / (
        f"RookContainmentRhino-{run_id}.3dm"
        if scenario == "rhino"
        else f"RookContainmentGH-{run_id}.ghx"
    )
    ownership_certain = True
    telemetry_store = None
    telemetry_before = None
    try:
        _collect_runtime_evidence(inputs)
        telemetry_store, telemetry_before = _telemetry_snapshot()
        started, record, process_token = _launch_owned(inputs)
        session = _InstalledSession(started, record, process_token)
        result["target"] = {
            "label": (
                "Rook containment Rhino scratch document"
                if scenario == "rhino"
                else "Rook containment Grasshopper scratch definition"
            ),
            "process_id": record.pid,
            "port": record.port,
            "scratch_path": str(scratch),
        }
        recorder = _Recorder(
            session,
            result,
            RHINO_TOOL_ALLOWLIST if scenario == "rhino" else GRASSHOPPER_TOOL_ALLOWLIST,
        )
        if scenario == "rhino":
            _, restored = asyncio.run(_run_rhino(recorder, result, run_id, scratch))
        else:
            _, restored = asyncio.run(_run_grasshopper(recorder, result, run_id, scratch))
        if not restored:
            raise LiveGateError("declared scratch state was not restored")
    except OwnershipAmbiguous as exc:
        ownership_certain = False
        restoration["ownership_certain"] = False
        restoration["manual_restoration_required"] = True
        diagnostics.append(str(exc)[:800])
    except (KeyboardInterrupt, Exception) as exc:
        diagnostics.append(str(exc)[:800] or type(exc).__name__)
        if isinstance(exc, KeyboardInterrupt):
            raise
    finally:
        if started is not None:
            if ownership_certain:
                closed = _graceful_close(started.process, diagnostics)
                restoration["prior_state_restored"] = closed
            else:
                restoration["manual_restoration_required"] = True
        if ownership_certain and scratch.exists():
            try:
                scratch.unlink()
            except OSError as exc:
                diagnostics.append(f"scratch disposal failed: {exc}"[:800])
        restoration["scratch_disposed"] = not scratch.exists()
        if telemetry_store is not None and telemetry_before is not None:
            try:
                result["telemetry"] = _telemetry_result(telemetry_store, telemetry_before)
            except LiveGateError as exc:
                diagnostics.append(str(exc))
    result["success"] = bool(
        result["verification"]
        and restoration["verified"]
        and restoration["prior_state_restored"]
        and restoration["scratch_disposed"]
        and isinstance(result["telemetry"], Mapping)
        and result["telemetry"].get("delta_count") == 0
        and not restoration["manual_restoration_required"]
    )
    return result


def run_rhino_scenario(inputs: ScenarioInputs) -> dict[str, object]:
    return _run_scenario(inputs, "rhino")


def run_grasshopper_scenario(inputs: ScenarioInputs) -> dict[str, object]:
    return _run_scenario(inputs, "grasshopper")


def _write_result(path: Path, result: Mapping[str, object]) -> None:
    if tuple(result) != RESULT_FIELDS:
        raise LiveGateError("scenario result schema drift")
    payload = _canonical_json_bytes(result) + b"\n"
    with path.open("xb") as stream:
        stream.write(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        inputs = _inputs_from_namespace(args)
        result = (
            run_rhino_scenario(inputs)
            if args.scenario == "rhino"
            else run_grasshopper_scenario(inputs)
        )
        _write_result(inputs.output, result)
    except KeyboardInterrupt:
        print("containment live gate interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"containment live gate failed: {str(exc)[:800]}", file=sys.stderr)
        return 3
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
