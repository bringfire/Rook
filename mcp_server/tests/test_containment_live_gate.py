from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib
import inspect
import io
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rook.gh_status_contract import normalize_gh_status_result


EXPECTED_RED = "EXPECTED_RED:T8:LIVE_GATE"
RUN_ID = "1" * 32
NONCE = "2" * 32
PROCESS_TOKEN = "3" * 32
SPHERE_ID = "11111111-1111-4111-8111-111111111111"
POINT_ID = "22222222-2222-4222-8222-222222222222"
GH_DOCUMENT_ID = "33333333-3333-4333-8333-333333333333"
GH_BOOTSTRAP_DOCUMENT_ID = "44444444-4444-4444-8444-444444444444"

try:
    live = importlib.import_module("rook.containment_live_gate")
except ModuleNotFoundError as exc:
    if exc.name != "rook.containment_live_gate":
        raise
    live = None


requires_live_gate = pytest.mark.skipif(
    live is None,
    reason="installed containment live gate is not implemented",
)


def test_containment_live_gate_contract_is_available() -> None:
    assert live is not None, f"{EXPECTED_RED} rook.containment_live_gate is not implemented"


@requires_live_gate
def test_literal_contract_tables_are_exact_and_closed() -> None:
    assert live.SCENARIOS == ("rhino", "grasshopper")
    assert live.FAILURE_LABELS == (
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
    assert live.RHINO_TOOL_ALLOWLIST == frozenset(
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
    assert live.GRASSHOPPER_TOOL_ALLOWLIST == frozenset(
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
    assert live.SPHERE_COMPONENT_GUID == "dabc854d-f50e-408a-b001-d043c7de151d"
    assert live.FIXTURE_SIZE == 2708
    assert live.FIXTURE_SHA256 == "2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df"
    assert set(live.CONTAINED_IDENTITIES) == {
        "gh_execute_intent",
        "rhino_execute_intent",
        "plan_and_execute",
        "spawn_agent",
        "gh_explore_workflow",
        "gh_replay_recipe",
    }


@requires_live_gate
def test_cli_parser_is_closed_and_has_no_autoauthorization_surface(tmp_path: Path) -> None:
    parser = live._build_parser()
    rhino = tmp_path / "Rhino.exe"
    artifact = tmp_path / "artifacts"
    parsed = parser.parse_args(
        [
            "run",
            "--scenario",
            "rhino",
            "--rhino-exe",
            str(rhino),
            "--artifact-dir",
            str(artifact),
        ]
    )
    assert vars(parsed) == {
        "command": "run",
        "scenario": "rhino",
        "rhino_exe": str(rhino),
        "artifact_dir": str(artifact),
    }
    rejected = (
        ["run", "--scenario", "bogus", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact)],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact), "--yes"],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact), "--authorization", "x"],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact), "--authorization-env", "X"],
        ["run", "--scenario", "rhino", "--rhino-exe", str(rhino)],
        ["rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(artifact)],
    )
    for argv in rejected:
        with pytest.raises(SystemExit):
            parser.parse_args(argv)

    signature = inspect.signature(live.run_live_scenario)
    assert list(signature.parameters) == ["scenario", "rhino_exe", "artifact_dir"]
    assert all(item.kind is inspect.Parameter.KEYWORD_ONLY for item in signature.parameters.values())
    source = inspect.getsource(live.run_live_scenario)
    for forbidden in ("authorization_reader", "executor=", "autoapprove", "--yes"):
        assert forbidden not in source


@requires_live_gate
def test_authorization_protocol_is_canonical_exact_and_one_shot(tmp_path: Path) -> None:
    target = {
        "label": "Rook containment Rhino scratch document",
        "process_id": 9001,
        "port": 19001,
        "scratch_path": str((tmp_path / f"RookContainmentRhino-{RUN_ID}.3dm").resolve()),
    }
    record = live._build_authorization_challenge(
        scenario="rhino",
        run_id=RUN_ID,
        nonce=NONCE,
        target=target,
    )
    assert set(record) == {
        "type",
        "schema_version",
        "scenario",
        "run_id",
        "nonce",
        "target",
        "target_sha256",
        "mutation",
        "mutation_sha256",
        "verification",
        "verification_sha256",
        "restoration",
        "restoration_sha256",
        "required_response",
    }
    assert record["type"] == "authorization_required"
    assert record["schema_version"] == 1
    assert record["target"] == target
    assert record["required_response"] == (
        f"AUTHORIZE scenario=rhino run={RUN_ID} nonce={NONCE} "
        f"target={record['target_sha256']} mutation={record['mutation_sha256']} "
        f"verify={record['verification_sha256']} restore={record['restoration_sha256']}"
    )
    encoded = live._canonical_json_bytes(record)
    assert encoded == json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert b"\n" not in encoded

    assert live._authorization_matches(record, record["required_response"] + "\n")
    assert live._authorization_matches(record, record["required_response"] + "\r\n")
    for rejected in (
        "",
        record["required_response"],
        record["required_response"] + " \n",
        record["required_response"].lower() + "\n",
        record["required_response"] + "\nEXTRA\n",
    ):
        assert not live._authorization_matches(record, rejected)


@requires_live_gate
def test_stdin_seam_reads_exactly_one_bounded_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("alpha\r\nbeta\n"))
    assert live._read_authorization_line() == "alpha\r\n"
    assert sys.stdin.read() == "beta\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO("x" * 8193 + "\n"))
    with pytest.raises(live.LiveGateError, match="authorization line"):
        live._read_authorization_line()


@requires_live_gate
def test_fixture_bytes_hash_xml_counts_and_package_lookup() -> None:
    path = live._fixture_resource_path()
    payload = path.read_bytes()
    assert len(payload) == 2708
    assert hashlib.sha256(payload).hexdigest() == live.FIXTURE_SHA256
    assert not payload.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in payload
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    root = ET.fromstring(payload.decode("utf-8"))
    assert root.tag == "Archive"
    object_count = root.find("./chunks/chunk[@name='Definition']/chunks/chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']")
    assert object_count is not None and object_count.text == "0"
    definition_objects = root.find("./chunks/chunk[@name='Definition']/chunks/chunk[@name='DefinitionObjects']/chunks")
    assert definition_objects is not None and definition_objects.attrib == {"count": "0"}
    assert live._validate_fixture_bytes(payload) is None
    for corrupt in (payload[:-1], payload + b"\n", b"\xef\xbb\xbf" + payload, payload.replace(b"\n", b"\r\n")):
        with pytest.raises(live.LiveGateError, match="fixture"):
            live._validate_fixture_bytes(corrupt)


@requires_live_gate
def test_fixture_cached_attribute_and_blob_preserve_exact_lf_bytes() -> None:
    root = Path(__file__).resolve().parents[2]
    fixture = "mcp_server/src/rook/resources/containment_empty.ghx"
    attribute_lines = (root / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert attribute_lines == [
        "third_party/ffmpeg/ffmpeg.exe filter=lfs diff=lfs merge=lfs -text",
        f"{fixture} -text",
    ]

    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    assert git("check-attr", "--cached", "text", "--", fixture) == (
        f"{fixture}: text: unset"
    )
    assert git("hash-object", "--", fixture) == git("rev-parse", f":{fixture}")
    eol = git("ls-files", "--eol", "--", fixture)
    assert re.search(r"(^|\s)i/lf\s+w/lf\s+attr/-text(\s|$)", eol)


@requires_live_gate
@pytest.mark.parametrize("case", ["missing-parent", "nonempty", "symlink", "owned"])
def test_artifact_preownership_rejection_is_zero_write(
    tmp_path: Path,
    case: str,
) -> None:
    if case == "missing-parent":
        artifact = tmp_path / "missing" / "artifacts"
        before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))
    elif case == "nonempty":
        artifact = tmp_path / "artifacts"
        artifact.mkdir()
        (artifact / "existing.txt").write_text("keep", encoding="utf-8")
        before = {path.name: path.read_bytes() for path in artifact.iterdir()}
    elif case == "owned":
        artifact = tmp_path / "artifacts"
        artifact.mkdir()
        (artifact / live.OWNERSHIP_MARKER).write_text("owned", encoding="utf-8")
        before = {path.name: path.read_bytes() for path in artifact.iterdir()}
    else:
        target = tmp_path / "target"
        target.mkdir()
        artifact = tmp_path / "artifacts"
        try:
            artifact.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks unavailable")
        before = sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*"))

    with pytest.raises(live.PreOwnershipBlocked):
        live._claim_artifact_directory(artifact, RUN_ID)

    if isinstance(before, dict):
        assert {path.name: path.read_bytes() for path in artifact.iterdir()} == before
    else:
        assert sorted(str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*")) == before


@requires_live_gate
def test_artifact_claim_is_atomic_and_marker_is_canonical(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts"
    claim = live._claim_artifact_directory(artifact, RUN_ID)
    assert claim == artifact.resolve()
    marker = artifact / live.OWNERSHIP_MARKER
    payload = marker.read_bytes()
    decoded = json.loads(payload)
    assert decoded == {"process_id": os.getpid(), "run_id": RUN_ID, "schema_version": 1}
    assert payload == live._canonical_json_bytes(decoded)
    with pytest.raises(live.PreOwnershipBlocked):
        live._claim_artifact_directory(artifact, RUN_ID)


@requires_live_gate
def test_runtime_serial_and_point_parsers_require_one_exact_line() -> None:
    assert live._parse_runtime_serial("ROOK_DOC_RUNTIME_SERIAL=17\n") == 17
    assert live._parse_point_id(f"ROOK_POINT_ID={POINT_ID}\n") == POINT_ID
    for output in (
        "",
        "ROOK_DOC_RUNTIME_SERIAL=0",
        "ROOK_DOC_RUNTIME_SERIAL=-1",
        "x ROOK_DOC_RUNTIME_SERIAL=2",
        "ROOK_DOC_RUNTIME_SERIAL=2\nROOK_DOC_RUNTIME_SERIAL=3",
    ):
        with pytest.raises(live.LiveGateError):
            live._parse_runtime_serial(output)
    for output in (
        "",
        "ROOK_POINT_ID=not-a-guid",
        f"ROOK_POINT_ID={POINT_ID}\nROOK_POINT_ID={POINT_ID}",
    ):
        with pytest.raises(live.LiveGateError):
            live._parse_point_id(output)


@dataclass
class _Record:
    pid: int
    port: int
    path: Path
    raw: dict[str, Any]
    host: str = "127.0.0.1"


class _Discovery:
    def __init__(self, record: _Record):
        self.record = record
        self.removed = False

    def read_owned_record(self, pid: int) -> _Record:
        if self.removed or pid != self.record.pid:
            raise RuntimeError("discovery missing")
        return self.record


@requires_live_gate
def test_bound_adapter_rechecks_pid_port_preserves_envelope_and_injects_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    record_path = tmp_path / "instance-9001-native.json"
    record_path.write_text("{}", encoding="utf-8")
    discovery = _Discovery(_Record(9001, 19001, record_path, {"processId": 9001, "port": 19001}))
    seen: list[tuple[str, dict[str, Any], dict[str, int | None]]] = []
    envelope = {"success": True, "data": {"pong": True}}

    async def dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from rook.bridge import get_rhino_request_context

        seen.append((name, dict(arguments), get_rhino_request_context()))
        return envelope

    monkeypatch.setattr(live, "_new_owned_discovery", lambda: discovery)
    monkeypatch.setattr(live, "_dispatch_installed_tool", dispatch)
    adapter = live.BoundInstalledToolAdapter(port=19001, process_id=9001)
    result = asyncio.run(adapter.call("rhino_ping", {}))
    assert result is envelope
    assert seen == [
        (
            "rhino_ping",
            {"port": 19001},
            {"port": 19001, "process_id": 9001, "document_serial_number": None},
        )
    ]
    with pytest.raises(live.LiveGateError, match="allowlist"):
        asyncio.run(adapter.call("gh_execute_intent", {}))
    with pytest.raises(live.LiveGateError, match="argument"):
        asyncio.run(adapter.call("rhino_ping", {"port": 9}))
    discovery.record = _Record(9001, 19002, record_path, {"processId": 9001, "port": 19002})
    with pytest.raises(live.OwnershipAmbiguous):
        asyncio.run(adapter.call("rhino_ping", {}))


class _Store:
    def __init__(self, *, events: list[dict[str, Any]] | None = None):
        self.events = list(events or [])
        self.token = "a" * 32

    def get_containment_denials_snapshot(self) -> dict[str, Any]:
        return {
            "process_id": os.getpid(),
            "process_start_token": self.token,
            "events": copy.deepcopy(self.events),
        }


class _Process:
    def __init__(self, pid: int):
        self.pid = pid
        self.returncode = None
        self.killed = False
        self.closed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.closed = True
        self.returncode = 0
        return 0

    def kill(self):
        self.killed = True
        self.returncode = -9


def _success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


class _RhinoAdapter:
    def __init__(self, scratch_path: Path):
        self.scratch_path = scratch_path
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.serial = 41
        self.saved = False
        self.objects: dict[str, dict[str, Any]] = {}
        self.modified = False

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "rhino_ping":
            return _success({"pong": True})
        if name == "rhino_execute" and arguments == {"code": live.RUNTIME_SERIAL_CODE}:
            return _success({"output": f"ROOK_DOC_RUNTIME_SERIAL={self.serial}\n"})
        if name == "rhino_document":
            return _success(
                {
                    "name": self.scratch_path.name if self.saved else "Untitled",
                    "path": str(self.scratch_path) if self.saved else "",
                    "objectCount": len(self.objects),
                    "modified": self.modified,
                }
            )
        if name == "rhino_objects":
            return _success({"objects": list(self.objects.values()), "count": len(self.objects)})
        if name == "rhino_document_ops":
            assert arguments == {"action": "save", "path": str(self.scratch_path)}
            self.saved = True
            self.modified = False
            self.scratch_path.write_bytes(b"fake-3dm")
            return _success({"saved": True, "path": str(self.scratch_path)})
        if name == "rhino_create":
            expected = live._rhino_sphere_arguments(RUN_ID)
            assert arguments == expected
            self.objects[SPHERE_ID] = {
                "id": SPHERE_ID,
                "name": expected["name"],
                "type": "Brep",
            }
            self.modified = True
            return _success({"id": SPHERE_ID})
        if name == "rhino_execute":
            assert arguments == {"code": live._rhino_point_script(RUN_ID)}
            self.objects[POINT_ID] = {
                "id": POINT_ID,
                "name": f"RookContainmentPoint-{RUN_ID}",
                "type": "Point",
            }
            self.modified = True
            return _success({"output": f"ROOK_POINT_ID={POINT_ID}\n"})
        if name == "rhino_geometry":
            object_id = arguments["id"]
            if object_id == SPHERE_ID:
                return _success(
                    {
                        "id": SPHERE_ID,
                        "name": f"RookContainmentSphere-{RUN_ID}",
                        "type": "Brep",
                        "bbox": {"min": [-4, -4, -4], "max": [4, 4, 4]},
                        "geometry": {
                            "type": "Brep",
                            "faceCount": 1,
                            "edgeCount": 0,
                            "vertexCount": 0,
                            "isSolid": True,
                            "isManifold": True,
                        },
                    }
                )
            return _success(
                {
                    "id": POINT_ID,
                    "name": f"RookContainmentPoint-{RUN_ID}",
                    "type": "Point",
                    "bbox": {"min": [10, 0, 0], "max": [10, 0, 0]},
                    "geometry": {"type": "Point", "location": [10, 0, 0]},
                }
            )
        if name == "rhino_delete":
            assert arguments["ids"] and set(arguments["ids"]).issubset({SPHERE_ID, POINT_ID})
            for object_id in arguments["ids"]:
                self.objects.pop(object_id, None)
            self.modified = True
            return _success({"deleted": 2})
        raise AssertionError((name, arguments))


class _GrasshopperAdapter:
    def __init__(self, scratch_path: Path):
        self.scratch_path = scratch_path
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.bootstrapped = False
        self.opened = False
        self.edited = False
        self.undo_count = 0

    def _status(self) -> dict[str, Any]:
        if not self.bootstrapped:
            raw = {
                "available": False,
                "assemblyVersion": "",
                "hasActiveCanvas": False,
                "hasActiveDocument": False,
                "documentId": None,
                "documentPath": "",
                "objectCount": 0,
                "readyForEdit": False,
                "warnings": ["Grasshopper assembly is not loaded."],
                "solverEnabled": None,
                "solverStateKnown": False,
                "solutionState": None,
            }
        else:
            raw = {
                "available": True,
                "assemblyVersion": "8.0",
                "hasActiveCanvas": True,
                "hasActiveDocument": True,
                "documentId": GH_DOCUMENT_ID if self.opened else GH_BOOTSTRAP_DOCUMENT_ID,
                "documentPath": str(self.scratch_path) if self.opened else "",
                "objectCount": 2 if self.edited else 0,
                "readyForEdit": True,
                "warnings": [],
                "solverEnabled": True,
                "solverStateKnown": True,
                "solutionState": "PostProcess",
            }
        normalized = normalize_gh_status_result(_success(raw))
        assert normalized["success"] is True and isinstance(normalized["data"], dict)
        return normalized["data"]

    def _snapshot(self) -> dict[str, Any]:
        if not self.edited:
            return {
                "version": "1.0.0",
                "document": {"name": self.scratch_path.name, "path": str(self.scratch_path)},
                "epoch": 7 + self.undo_count,
                "components": [],
                "flows": [],
                "diagnostics": {"total": 0, "errors": 0, "warnings": 0, "error_ids": None, "warning_ids": None},
            }
        return {
            "version": "1.0.0",
            "document": {"name": self.scratch_path.name, "path": str(self.scratch_path)},
            "epoch": 8,
            "components": [
                {
                    "id": "C1",
                    "type": "NumberSlider",
                    "nick": f"RookContainmentRadius-{RUN_ID}",
                    "pos": [100, 100],
                    "is_param": True,
                    "value": {"type": "slider", "val": 4, "min": 1, "max": 9},
                },
                {
                    "id": "C2",
                    "type": "Component",
                    "name": "Sphere",
                    "componentGuid": live.SPHERE_COMPONENT_GUID,
                    "pos": [400, 100],
                    "inputs": [{"idx": 0, "name": "Base"}, {"idx": 1, "name": "Radius", "sources": 1}],
                    "outputs": [
                        {
                            "idx": 0,
                            "name": "Sphere",
                            "type": "Sphere",
                            "data": {
                                "structure": "single",
                                "count": 1,
                                "preview": ["Sphere"],
                            },
                        }
                    ],
                },
            ],
            "flows": ["C1.O0>C2.I1"],
            "diagnostics": {"total": 2, "errors": 0, "warnings": 0, "error_ids": None, "warning_ids": None},
        }

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(arguments)))
        if name == "rhino_ping":
            return _success({"pong": True})
        if name == "rhino_document":
            return _success({"name": "Untitled", "path": "", "objectCount": 0, "modified": False})
        if name == "gh_status":
            return _success(self._status())
        if name == "rhino_command":
            assert arguments == {"command": "_Grasshopper", "echo": False}
            self.bootstrapped = True
            return _success({"executed": True})
        if name == "gh_document_open":
            assert arguments == {"path": str(self.scratch_path)}
            assert self.scratch_path.read_bytes() == live._fixture_resource_path().read_bytes()
            self.opened = True
            return _success({"opened": True, "path": str(self.scratch_path), "fileName": self.scratch_path.name, "objectCount": 0})
        if name == "gh_snapshot":
            return _success(self._snapshot())
        if name == "gh_errors":
            return _success({"totalComponents": 2 if self.edited else 0, "errorCount": 0, "warningCount": 0, "errors": [], "warnings": []})
        if name == "gh_library":
            assert arguments == {"search": "Sphere", "exact": True}
            return _success({"count": 1, "components": [{"name": "Sphere", "guid": live.SPHERE_COMPONENT_GUID}]})
        if name == "gh_edit":
            assert arguments == live._grasshopper_edit_arguments(RUN_ID, 7)
            self.edited = True
            result = self._snapshot()
            result["edit_summary"] = {
                "created": 2,
                "connected": 1,
                "solve_scheduled": True,
                "solver_locked": False,
                "solver_state_known": True,
                "verification_deferred": True,
                "errors": None,
            }
            return _success(result)
        if name == "gh_undo":
            self.undo_count += 1
            self.edited = False
            return _success({"message": "Undo successful", "epoch": 8 + self.undo_count, "snapshot": self._snapshot()})
        raise AssertionError((name, arguments))


@requires_live_gate
def test_gh_status_projection_consumes_exact_server_normalized_wire_shape() -> None:
    normalized = normalize_gh_status_result(
        _success(
            {
                "available": True,
                "assemblyVersion": "8.0",
                "hasActiveCanvas": True,
                "hasActiveDocument": True,
                "documentId": GH_DOCUMENT_ID,
                "documentPath": r"C:\scratch\containment.ghx",
                "objectCount": 2,
                "readyForEdit": True,
                "warnings": [],
                "solverEnabled": True,
                "solverStateKnown": True,
                "solutionState": "PostProcess",
            }
        )
    )
    data = normalized["data"]
    assert "hasActiveCanvas" not in data and data["has_active_canvas"] is True
    assert "documentId" not in data and data["document_id"] == GH_DOCUMENT_ID
    assert data["solverEnabled"] is True
    assert data["solverStateKnown"] is True
    assert data["solutionState"] == "PostProcess"
    assert live._gh_status_projection(data) == {
        "available": True,
        "has_active_canvas": True,
        "has_active_document": True,
        "document_id": GH_DOCUMENT_ID,
        "document_path": r"C:\scratch\containment.ghx",
        "object_count": 2,
        "ready_for_edit": True,
        "solver_enabled": True,
        "solver_state_known": True,
        "solution_state": "PostProcess",
    }


def _runtime_evidence(tmp_path: Path) -> dict[str, Any]:
    root = (tmp_path / "installed").resolve()
    root.mkdir(exist_ok=True)
    return {
        "python_executable": str((root / "python.exe").resolve()),
        "installed_root": str(root),
        "cwd": str((tmp_path / "run").resolve()),
        "sys_path": [str(root)],
        "rook_origins": {
            "rook": str(root / "rook" / "__init__.py"),
            "rook.containment_live_gate": str(root / "rook" / "containment_live_gate.py"),
        },
    }


def _install_fake_scenario(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    scenario: str,
    store: _Store | None = None,
    authorization: str = "valid",
    drift: bool = False,
    graceful_forced: bool = False,
):
    artifact = tmp_path / f"artifacts-{scenario}"
    rhino_exe = tmp_path / "Rhino.exe"
    rhino_exe.write_bytes(b"fake")
    process = _Process(9001 if scenario == "rhino" else 9002)
    record_path = tmp_path / f"instance-{process.pid}-native.json"
    record_path.write_text(
        json.dumps({"processId": process.pid, "port": 19001 if scenario == "rhino" else 19002, "pluginType": "native"}),
        encoding="utf-8",
    )
    record_sha256 = hashlib.sha256(record_path.read_bytes()).hexdigest()
    record = _Record(process.pid, 19001 if scenario == "rhino" else 19002, record_path, json.loads(record_path.read_text()))
    discovery = _Discovery(record)
    scratch_suffix = "3dm" if scenario == "rhino" else "ghx"
    scratch_prefix = "RookContainmentRhino" if scenario == "rhino" else "RookContainmentGH"
    scratch = (artifact / f"{scratch_prefix}-{RUN_ID}.{scratch_suffix}").resolve()
    adapter = _RhinoAdapter(scratch) if scenario == "rhino" else _GrasshopperAdapter(scratch)
    store = store or _Store()
    trace: list[str] = []

    monkeypatch.setattr(live, "_new_run_id", lambda: RUN_ID)
    monkeypatch.setattr(live, "_new_nonce", lambda: NONCE)
    monkeypatch.setattr(live, "_collect_and_validate_runtime_evidence", lambda: _runtime_evidence(tmp_path))
    monkeypatch.setattr(live, "_get_metrics_store", lambda: store)
    monkeypatch.setattr(live, "_build_launch_environment", lambda: {"env": {}, "report": {}})

    def start(*, rhino_exe: Path, launch: dict[str, Any]):
        assert store.get_containment_denials_snapshot()
        trace.append("launch")
        return SimpleNamespace(process=process, pid=process.pid, started_wall=100.0)

    monkeypatch.setattr(live, "_start_owned_rhino", start)
    monkeypatch.setattr(live, "_new_owned_discovery", lambda: discovery)
    monkeypatch.setattr(live, "_wait_for_owned_readiness", lambda started, owned: record)
    monkeypatch.setattr(live, "_owned_process_start_token", lambda started: PROCESS_TOKEN)
    monkeypatch.setattr(live, "_new_bound_adapter", lambda port, process_id: adapter)

    close_calls: list[int] = []

    def close(proc, diagnostics):
        close_calls.append(proc.pid)
        proc.wait()
        discovery.removed = True
        try:
            record_path.unlink()
        except FileNotFoundError:
            pass
        return graceful_forced

    monkeypatch.setattr(live, "_request_graceful_close", close)
    monkeypatch.setattr(live, "_force_owned_cleanup", lambda proc, diagnostics: False)
    fake_clock = {"now": 0.0}
    monkeypatch.setattr(live, "_monotonic", lambda: fake_clock["now"])
    monkeypatch.setattr(
        live,
        "_sleep",
        lambda seconds: fake_clock.__setitem__(
            "now", fake_clock["now"] + seconds
        ),
    )

    challenge_target = {
        "label": live.AUTHORIZATION_LABELS[scenario],
        "process_id": process.pid,
        "port": record.port,
        "scratch_path": str(scratch),
    }
    expected_challenge = live._build_authorization_challenge(
        scenario=scenario,
        run_id=RUN_ID,
        nonce=NONCE,
        target=challenge_target,
    )
    if authorization == "valid":
        line = expected_challenge["required_response"] + "\n"
    elif authorization == "eof":
        line = ""
    else:
        line = "WRONG\n"
    monkeypatch.setattr(live, "_read_authorization_line", lambda: line)

    if drift:
        original = adapter.call
        drift_name = "rhino_document" if scenario == "rhino" else "gh_status"
        seen_preflight = 0

        async def drifting_call(name, arguments):
            nonlocal seen_preflight
            result = await original(name, arguments)
            if name == drift_name:
                seen_preflight += 1
                if seen_preflight >= 2 and result["success"]:
                    result = copy.deepcopy(result)
                    result["data"][
                        "objectCount" if scenario == "rhino" else "object_count"
                    ] = 99
            return result

        adapter.call = drifting_call

    return SimpleNamespace(
        artifact=artifact,
        rhino_exe=rhino_exe,
        process=process,
        record=record,
        record_sha256=record_sha256,
        discovery=discovery,
        adapter=adapter,
        store=store,
        trace=trace,
        close_calls=close_calls,
        scratch=scratch,
        challenge=expected_challenge,
    )


def _load_final_artifact(artifact: Path, scenario: str) -> dict[str, Any]:
    path = artifact / f"{scenario}-scenario.json"
    payload = path.read_bytes()
    assert payload == live._canonical_json_bytes(json.loads(payload))
    digest = hashlib.sha256(payload).hexdigest()
    assert (artifact / f"{scenario}-scenario.sha256").read_bytes() == f"{digest}\n".encode()
    return json.loads(payload)


@requires_live_gate
def test_grasshopper_output_contract_uses_structured_fields_not_preview(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.edited = True
    snapshot = harness.adapter._snapshot()

    projection = live._verify_gh_edit(snapshot, RUN_ID)

    output = projection["components"][1]["outputs"][0]
    assert output["idx"] == 0
    assert output["name"] == "Sphere"
    assert output["type"] == "Sphere"
    assert output["data"]["structure"] == "single"
    assert output["data"]["count"] == 1
    assert output["data"]["preview"] == ["Sphere"]


@requires_live_gate
def test_grasshopper_output_contract_rejects_misleading_digit_preview(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.edited = True
    snapshot = harness.adapter._snapshot()
    output = snapshot["components"][1]["outputs"][0]
    output["type"] = "Integer"
    output["data"]["preview"] = ["misleading radius 4"]

    with pytest.raises(live._ScenarioFailure, match="output"):
        live._verify_gh_edit(snapshot, RUN_ID)


@requires_live_gate
@pytest.mark.parametrize("case", ["wrong_slider_value", "empty_output"])
def test_grasshopper_output_contract_rejects_wrong_value_or_empty_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    harness.adapter.edited = True
    snapshot = harness.adapter._snapshot()
    if case == "wrong_slider_value":
        snapshot["components"][0]["value"]["val"] = 5
    else:
        snapshot["components"][1]["outputs"][0]["data"] = {
            "structure": "empty",
            "count": 0,
            "preview": ["misleading radius 4"],
        }

    with pytest.raises(live._ScenarioFailure):
        live._verify_gh_edit(snapshot, RUN_ID)


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_successful_fake_host_scenarios_emit_exact_evidence_and_restore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    result = live.run_live_scenario(
        scenario=scenario,
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is True
    assert result.failure_label is None
    stdout = capsys.readouterr().out.encode("utf-8")
    lines = stdout.splitlines(keepends=True)
    assert len(lines) == 2 and all(line.endswith(b"\n") for line in lines)
    records = [json.loads(line) for line in lines]
    assert records[0] == harness.challenge
    assert records[1]["type"] == "scenario_result"
    assert records[1]["success"] is True and records[1]["failure_label"] is None
    assert set(records[1]) == {
        "type", "schema_version", "scenario", "run_id", "success", "failure_label", "evidence_path", "evidence_sha256"
    }

    artifact = _load_final_artifact(harness.artifact, scenario)
    assert set(artifact) == set(live.RESULT_FIELDS)
    assert artifact["success"] is True
    assert artifact["runtime"] == _runtime_evidence(tmp_path)
    assert artifact["target"]["process_id"] == harness.process.pid
    assert artifact["target"]["port"] == harness.record.port
    assert artifact["target"]["process_start_token"] == PROCESS_TOKEN
    assert artifact["target"]["discovery_record_sha256"] == harness.record_sha256
    assert artifact["authorization"]["state_unchanged"] is True
    assert artifact["verification"]["passed"] is True
    assert artifact["restoration"] == {
        "ownership_certain": True,
        "attempted": True,
        "verified": True,
        "in_process_projection_matches_declared": True,
        "prior_identity_or_absence_restored": True,
        "scratch_disposed": True,
        "discovery_removed": True,
    }
    assert artifact["telemetry"]["delta_count"] == 0
    assert artifact["telemetry"]["events_added"] == []
    assert not harness.scratch.exists()
    assert harness.process.closed and not harness.process.killed
    assert harness.close_calls == [harness.process.pid]
    assert artifact["operations"]
    assert not any(item["name"] in live.CONTAINED_IDENTITIES for item in artifact["operations"])
    for operation in artifact["operations"]:
        for kind in ("arguments", "result"):
            path = harness.artifact / operation[f"{kind}_path"]
            payload = path.read_bytes()
            assert hashlib.sha256(payload).hexdigest() == operation[f"{kind}_sha256"]
            assert payload == live._canonical_json_bytes(json.loads(payload))
            assert any(item["relative_path"] == operation[f"{kind}_path"] for item in artifact["artifacts"])
    live._validate_scenario_artifacts(harness.artifact, scenario=scenario)

    names = [name for name, _ in harness.adapter.calls]
    if scenario == "rhino":
        assert ("rhino_create", live._rhino_sphere_arguments(RUN_ID)) in harness.adapter.calls
        assert ("rhino_execute", {"code": live._rhino_point_script(RUN_ID)}) in harness.adapter.calls
        assert names.index("rhino_delete") < names.index("rhino_document_ops", names.index("rhino_delete"))
        dirty_checks = [
            args for name, args in harness.adapter.calls if name == "rhino_document"
        ]
        assert dirty_checks
    else:
        assert ("rhino_command", {"command": "_Grasshopper", "echo": False}) in harness.adapter.calls
        assert ("gh_library", {"search": "Sphere", "exact": True}) in harness.adapter.calls
        edit_calls = [args for name, args in harness.adapter.calls if name == "gh_edit"]
        assert edit_calls == [live._grasshopper_edit_arguments(RUN_ID, 7)]
        assert 1 <= names.count("gh_undo") <= 4
        assert "gh_solve" not in names and "gh_document_new" not in names


@requires_live_gate
def test_grasshopper_settle_waits_past_real_deferred_dispatch_delay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_call = harness.adapter.call
    clock = {"now": 0.0}
    edited_status_times: list[float] = []

    async def delayed_settle(name, arguments):
        result = await original_call(name, arguments)
        if name == "gh_status" and harness.adapter.edited:
            edited_status_times.append(clock["now"])
            if clock["now"] < 5.25:
                result = copy.deepcopy(result)
                result["data"]["solutionState"] = "PreProcess"
        return result

    harness.adapter.call = delayed_settle
    monkeypatch.setattr(live, "_monotonic", lambda: clock["now"], raising=False)
    monkeypatch.setattr(
        live,
        "_sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )

    assert live.GH_SOLVE_SETTLE_TIMEOUT_SECONDS > 5.0
    assert result.success is True
    assert edited_status_times[0] == 0.0
    assert max(edited_status_times) >= 5.25
    assert max(edited_status_times) <= live.GH_SOLVE_SETTLE_TIMEOUT_SECONDS


@requires_live_gate
def test_keyboard_interrupt_before_authorization_closes_owned_target_and_exits_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")

    def interrupt_authorization() -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(live, "_read_authorization_line", interrupt_authorization)
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        exit_code = live.main(
            [
                "run",
                "--scenario",
                "rhino",
                "--rhino-exe",
                str(harness.rhino_exe),
                "--artifact-dir",
                str(harness.artifact),
            ]
        )

    names = [name for name, _ in harness.adapter.calls]
    assert exit_code == 130
    assert not {
        "rhino_document_ops",
        "rhino_create",
        "rhino_delete",
    }.intersection(names)
    assert harness.process.closed and not harness.process.killed
    assert harness.close_calls == [harness.process.pid]
    assert not Path(harness.record.path).exists()
    assert not harness.scratch.exists()
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["success"] is False
    assert evidence["failure_label"] == "authorization_rejected"
    assert evidence["restoration"]["attempted"] is False
    assert evidence["restoration"]["verified"] is False
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_keyboard_interrupt_during_restoration_retries_safely_then_exits_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_call = harness.adapter.call
    undo_attempts = 0

    async def interrupt_first_undo(name, arguments):
        nonlocal undo_attempts
        if name == "gh_undo":
            undo_attempts += 1
            if undo_attempts == 1:
                raise KeyboardInterrupt
        return await original_call(name, arguments)

    harness.adapter.call = interrupt_first_undo
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        exit_code = live.main(
            [
                "run",
                "--scenario",
                "grasshopper",
                "--rhino-exe",
                str(harness.rhino_exe),
                "--artifact-dir",
                str(harness.artifact),
            ]
        )

    assert exit_code == 130
    assert undo_attempts == 2
    assert harness.adapter.undo_count == 1
    assert harness.adapter.edited is False
    assert harness.process.closed and not harness.process.killed
    assert harness.close_calls == [harness.process.pid]
    assert not Path(harness.record.path).exists()
    assert not harness.scratch.exists()
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["success"] is False
    assert evidence["failure_label"] == "mutation_failed"
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["verified"] is True
    live._validate_scenario_artifacts(harness.artifact, scenario="grasshopper")


@requires_live_gate
def test_keyboard_interrupt_retry_never_exceeds_total_four_undo_attempts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_call = harness.adapter.call
    undo_attempts = 0

    async def interrupt_fourth_undo(name, arguments):
        nonlocal undo_attempts
        if name == "gh_undo":
            undo_attempts += 1
            if undo_attempts < 4:
                harness.adapter.calls.append((name, copy.deepcopy(arguments)))
                return _success(
                    {
                        "message": "Undo reported without restoration",
                        "epoch": 8 + undo_attempts,
                        "snapshot": harness.adapter._snapshot(),
                    }
                )
            if undo_attempts == 4:
                raise KeyboardInterrupt
        return await original_call(name, arguments)

    harness.adapter.call = interrupt_fourth_undo
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        exit_code = live.main(
            [
                "run",
                "--scenario",
                "grasshopper",
                "--rhino-exe",
                str(harness.rhino_exe),
                "--artifact-dir",
                str(harness.artifact),
            ]
        )

    assert exit_code == 130
    assert undo_attempts == 4
    assert harness.adapter.edited is True
    assert harness.process.closed and not harness.process.killed
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["success"] is False
    assert evidence["failure_label"] == "restoration_failed"
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["verified"] is False
    live._validate_scenario_artifacts(harness.artifact, scenario="grasshopper")


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
@pytest.mark.parametrize("authorization", ["eof", "wrong"])
def test_authorization_rejection_blocks_all_forward_mutation_and_is_not_green(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    authorization: str,
) -> None:
    harness = _install_fake_scenario(
        monkeypatch,
        tmp_path,
        scenario=scenario,
        authorization=authorization,
    )
    result = live.run_live_scenario(scenario=scenario, rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "authorization_rejected"
    artifact = _load_final_artifact(harness.artifact, scenario)
    names = [name for name, _ in harness.adapter.calls]
    mutation_names = {"rhino_document_ops", "rhino_create", "rhino_delete", "rhino_command", "gh_document_open", "gh_edit", "gh_undo"}
    assert not mutation_names.intersection(names)
    assert artifact["operations"] == []
    assert not any(item["kind"].startswith("operation_") for item in artifact["artifacts"])
    assert artifact["authorization"]["authorized_at"] is None
    assert artifact["restoration"]["attempted"] is False
    assert artifact["success"] is False


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_preflight_blocked_has_no_operation_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    original = harness.adapter.call

    async def block_preflight(name, arguments):
        result = await original(name, arguments)
        if scenario == "rhino" and name == "rhino_document":
            result = copy.deepcopy(result)
            result["data"]["objectCount"] = 1
        if scenario == "grasshopper" and name == "gh_status":
            result = copy.deepcopy(result)
            result["data"].update(
                {
                    "available": True,
                    "has_active_canvas": True,
                    "has_active_document": True,
                    "document_id": GH_BOOTSTRAP_DOCUMENT_ID,
                    "ready_for_edit": True,
                    "object_count": 1,
                }
            )
        return result

    harness.adapter.call = block_preflight
    result = live.run_live_scenario(
        scenario=scenario,
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "preflight_blocked"
    artifact = _load_final_artifact(harness.artifact, scenario)
    assert artifact["authorization"] is None
    assert artifact["operations"] == []
    assert not any(item["kind"].startswith("operation_") for item in artifact["artifacts"])


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_malformed_preflight_is_classified_as_blocked_without_operations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario)
    original = harness.adapter.call

    async def malformed_preflight(name, arguments):
        if (scenario == "rhino" and name == "rhino_document") or (
            scenario == "grasshopper" and name == "gh_status"
        ):
            harness.adapter.calls.append((name, copy.deepcopy(arguments)))
            return {"success": True, "data": []}
        return await original(name, arguments)

    harness.adapter.call = malformed_preflight
    result = live.run_live_scenario(
        scenario=scenario,
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "preflight_blocked"
    evidence = _load_final_artifact(harness.artifact, scenario)
    assert evidence["operations"] == []
    assert evidence["authorization"] is None


@requires_live_gate
def test_invalid_packaged_fixture_is_classified_before_authorization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    invalid = tmp_path / "invalid.ghx"
    invalid.write_bytes(b"not-the-approved-fixture\n")
    monkeypatch.setattr(live, "_fixture_resource_path", lambda: invalid)
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "fixture_invalid"
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["authorization"] is None
    assert evidence["pre_state"] is None
    assert evidence["operations"] == []


@requires_live_gate
@pytest.mark.parametrize("scenario", ["rhino", "grasshopper"])
def test_pre_mutation_state_drift_invalidates_authorization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario=scenario, drift=True)
    result = live.run_live_scenario(scenario=scenario, rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "state_drift"
    names = [name for name, _ in harness.adapter.calls]
    assert not {"rhino_document_ops", "rhino_create", "rhino_command", "gh_document_open", "gh_edit"}.intersection(names)


@requires_live_gate
def test_telemetry_baseline_precedes_launch_seed_before_allowed_seed_after_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    old_event = {"tool": "spawn_agent", "disposition": "suspended", "origin": "rook_agent", "timestamp": "2026-07-16T00:00:00.000000Z"}
    store = _Store(events=[old_event])
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino", store=store)
    passed = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert passed.success is True

    second_root = tmp_path / "second"
    second_root.mkdir()
    store2 = _Store(events=[old_event])
    harness2 = _install_fake_scenario(monkeypatch, second_root, scenario="rhino", store=store2)
    original_close = live._request_graceful_close

    def close_and_add(proc, diagnostics):
        value = original_close(proc, diagnostics)
        store2.events.append({**old_event, "tool": "gh_execute_intent"})
        return value

    monkeypatch.setattr(live, "_request_graceful_close", close_and_add)
    failed = live.run_live_scenario(scenario="rhino", rhino_exe=harness2.rhino_exe, artifact_dir=harness2.artifact)
    assert failed.success is False and failed.failure_label == "telemetry_changed"


@requires_live_gate
def test_telemetry_process_token_or_accessor_replacement_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = _Store()
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino", store=store)
    original_close = live._request_graceful_close

    def close_and_drift(proc, diagnostics):
        value = original_close(proc, diagnostics)
        store.token = "b" * 32
        return value

    monkeypatch.setattr(live, "_request_graceful_close", close_and_drift)
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "telemetry_changed"


@requires_live_gate
def test_force_cleanup_can_never_turn_success_green(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino", graceful_forced=True)
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label == "cleanup_failed"
    assert _load_final_artifact(harness.artifact, "rhino")["restoration"]["verified"] is False


@requires_live_gate
def test_stale_discovery_record_is_not_deleted_or_reported_as_restored(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")

    def close_without_discovery_cleanup(proc, diagnostics):
        proc.wait()
        return False

    monkeypatch.setattr(live, "_request_graceful_close", close_without_discovery_cleanup)
    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "cleanup_failed"
    assert Path(harness.record.path).is_file()
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["restoration"]["discovery_removed"] is False
    assert evidence["restoration"]["verified"] is False


@requires_live_gate
def test_cleanup_exception_uses_force_only_as_failed_diagnostic_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    force_calls: list[int] = []

    def close_raises(proc, diagnostics):
        raise RuntimeError("close transport failed")

    def force_cleanup(proc, diagnostics):
        force_calls.append(proc.pid)
        proc.kill()
        harness.discovery.removed = True
        Path(harness.record.path).unlink()
        return True

    monkeypatch.setattr(live, "_request_graceful_close", close_raises)
    monkeypatch.setattr(live, "_force_owned_cleanup", force_cleanup)
    result = live.run_live_scenario(
        scenario="rhino",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "cleanup_failed"
    assert force_calls == [harness.process.pid]
    assert harness.process.killed
    evidence = _load_final_artifact(harness.artifact, "rhino")
    assert evidence["restoration"]["verified"] is False


@requires_live_gate
def test_rhino_restoration_refuses_unvalidated_object_id_without_deletion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    unexpected_id = "55555555-5555-4555-8555-555555555555"
    harness.artifact.mkdir(parents=True)
    harness.scratch.write_bytes(b"fake-3dm")
    harness.adapter.saved = True
    harness.adapter.modified = True
    harness.adapter.objects = {
        SPHERE_ID: {
            "id": SPHERE_ID,
            "name": f"RookContainmentSphere-{RUN_ID}",
            "type": "Brep",
        },
        unexpected_id: {
            "id": unexpected_id,
            "name": "Unexpected",
            "type": "Point",
        },
    }
    result = live._new_result("rhino", RUN_ID, live._utc_now())
    result.pre_state = {
        "host_projection": None,
        "host_sha256": None,
        "scratch_projection": {
            "runtime_serial": 41,
            "path": str(harness.scratch),
            "modified": False,
            "object_count": 0,
            "object_ids": [],
        },
        "scratch_sha256": None,
    }
    state = live._RunState(
        scenario="rhino",
        run_id=RUN_ID,
        artifact_dir=harness.artifact,
        rhino_exe=harness.rhino_exe,
        started_at=result.started_at,
        result=result,
        adapter=harness.adapter,
        scratch_path=harness.scratch,
        created_rhino_ids=[SPHERE_ID],
    )

    with pytest.raises(live.OwnershipAmbiguous, match="object"):
        asyncio.run(live._restore_rhino(state, live._OperationRecorder(state)))

    assert "rhino_delete" not in [name for name, _ in harness.adapter.calls]
    assert set(harness.adapter.objects) == {SPHERE_ID, unexpected_id}


@requires_live_gate
def test_grasshopper_restoration_never_exceeds_four_undo_calls(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def undo_without_restoring(name, arguments):
        if name == "gh_undo":
            harness.adapter.calls.append((name, copy.deepcopy(arguments)))
            harness.adapter.undo_count += 1
            return _success(
                {
                    "message": "Undo successful",
                    "epoch": 8 + harness.adapter.undo_count,
                    "snapshot": harness.adapter._snapshot(),
                }
            )
        return await original(name, arguments)

    harness.adapter.call = undo_without_restoring
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "restoration_failed"
    names = [name for name, _ in harness.adapter.calls]
    assert names.count("gh_undo") == 4


@requires_live_gate
def test_grasshopper_requires_a_fresh_post_edit_epoch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_snapshot = harness.adapter._snapshot

    def stale_snapshot():
        snapshot = original_snapshot()
        if harness.adapter.edited:
            snapshot["epoch"] = 7
        return snapshot

    harness.adapter._snapshot = stale_snapshot
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "verification_failed"


@requires_live_gate
@pytest.mark.parametrize(
    "case",
    ["solve_not_scheduled", "deferred_false", "deferred_missing"],
)
def test_grasshopper_requires_exact_deferred_edit_solve_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: str,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def invalid_edit_solve_evidence(name, arguments):
        result = await original(name, arguments)
        if name == "gh_edit":
            result = copy.deepcopy(result)
            summary = result["data"]["edit_summary"]
            if case == "solve_not_scheduled":
                summary["solve_scheduled"] = False
            elif case == "deferred_false":
                summary["verification_deferred"] = False
            else:
                summary.pop("verification_deferred")
        return result

    harness.adapter.call = invalid_edit_solve_evidence
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "verification_failed"
    undo_count = [name for name, _ in harness.adapter.calls].count("gh_undo")
    assert 1 <= undo_count <= 4
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["in_process_projection_matches_declared"] is True
    assert evidence["restoration"]["verified"] is True
    assert evidence["success"] is False


@requires_live_gate
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("solverEnabled", False),
        ("solverStateKnown", False),
        ("solutionState", "PreProcess"),
    ],
)
def test_grasshopper_requires_known_enabled_postprocess_solver_after_edit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def non_solved_status(name, arguments):
        result = await original(name, arguments)
        if name == "gh_status" and harness.adapter.edited:
            result = copy.deepcopy(result)
            result["data"][field] = value
        return result

    harness.adapter.call = non_solved_status
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "verification_failed"


@requires_live_gate
def test_partial_successful_gh_edit_is_undone_before_failure_is_reported(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original = harness.adapter.call

    async def partial_edit(name, arguments):
        result = await original(name, arguments)
        if name == "gh_edit":
            result = copy.deepcopy(result)
            result["success"] = False
            result["partial_success"] = True
            result["verified"] = False
            result["data"]["edit_summary"]["errors"] = ["bounded edit partially applied"]
        return result

    harness.adapter.call = partial_edit
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "mutation_failed"
    names = [name for name, _ in harness.adapter.calls]
    assert 1 <= names.count("gh_undo") <= 4
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["restoration"]["attempted"] is True
    assert evidence["restoration"]["in_process_projection_matches_declared"] is True
    assert evidence["restoration"]["verified"] is True
    assert evidence["success"] is False
    edit_operation = next(item for item in evidence["operations"] if item["name"] == "gh_edit")
    assert edit_operation["success"] is False


@requires_live_gate
def test_post_dispatch_gh_edit_result_write_failure_inspects_and_undoes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="grasshopper")
    original_write = live._atomic_write_bytes

    def fail_edit_result(path: Path, payload: bytes) -> None:
        if path.name.endswith("-gh_edit-result.json"):
            raise OSError("result evidence disk failure")
        original_write(path, payload)

    monkeypatch.setattr(live, "_atomic_write_bytes", fail_edit_result)
    result = live.run_live_scenario(
        scenario="grasshopper",
        rhino_exe=harness.rhino_exe,
        artifact_dir=harness.artifact,
    )
    assert result.success is False and result.failure_label == "mutation_failed"
    names = [name for name, _ in harness.adapter.calls]
    assert "gh_edit" in names
    assert 1 <= names.count("gh_undo") <= 4
    evidence = _load_final_artifact(harness.artifact, "grasshopper")
    assert evidence["restoration"]["in_process_projection_matches_declared"] is True
    assert evidence["restoration"]["verified"] is True
    assert evidence["success"] is False
    assert not any(item["name"] == "gh_edit" for item in evidence["operations"])
    orphan_arguments = [
        item
        for item in evidence["artifacts"]
        if item["relative_path"].endswith("-gh_edit-arguments.json")
    ]
    assert len(orphan_arguments) == 1
    assert not any(
        item["relative_path"].endswith("-gh_edit-result.json")
        for item in evidence["artifacts"]
    )


@requires_live_gate
def test_forward_mutation_failure_restores_only_when_ownership_is_certain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original = harness.adapter.call

    async def fail_point(name, arguments):
        if name == "rhino_execute" and arguments != {"code": live.RUNTIME_SERIAL_CODE}:
            return {"success": False, "data": "point failed"}
        return await original(name, arguments)

    harness.adapter.call = fail_point
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False and result.failure_label in {"mutation_failed", "restoration_failed"}
    names = [name for name, _ in harness.adapter.calls]
    assert "rhino_delete" in names
    assert "rhino_document_ops" in names

    second = tmp_path / "ambiguous"
    second.mkdir()
    harness2 = _install_fake_scenario(monkeypatch, second, scenario="rhino")
    original2 = harness2.adapter.call

    async def ambiguous(name, arguments):
        if name == "rhino_create":
            harness2.discovery.removed = True
            raise live.OwnershipAmbiguous("lost owned discovery")
        return await original2(name, arguments)

    harness2.adapter.call = ambiguous
    result2 = live.run_live_scenario(scenario="rhino", rhino_exe=harness2.rhino_exe, artifact_dir=harness2.artifact)
    assert result2.success is False and result2.failure_label == "ownership_ambiguous"
    names2 = [name for name, _ in harness2.adapter.calls]
    assert "rhino_delete" not in names2


@requires_live_gate
def test_operation_artifact_write_failure_stops_forward_work_and_cannot_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original = live._atomic_write_bytes

    def fail_on_create(path: Path, payload: bytes):
        if "rhino_create-arguments" in path.name:
            raise OSError("disk full")
        return original(path, payload)

    monkeypatch.setattr(live, "_atomic_write_bytes", fail_on_create)
    result = live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    assert result.success is False
    names = [name for name, _ in harness.adapter.calls]
    assert "rhino_create" not in names


@requires_live_gate
def test_consumer_rejects_missing_tampered_noncanonical_and_escaping_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    assert live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact).success
    live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
    evidence_path = harness.artifact / "rhino-scenario.json"
    evidence = json.loads(evidence_path.read_bytes())
    operation_path = harness.artifact / evidence["operations"][0]["arguments_path"]
    original = operation_path.read_bytes()

    operation_path.unlink()
    with pytest.raises(live.LiveGateError, match="artifact"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
    operation_path.write_bytes(original + b" ")
    with pytest.raises(live.LiveGateError, match="artifact"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")
    operation_path.write_bytes(original)

    evidence["operations"][0]["arguments_path"] = "../escape.json"
    live._write_final_evidence_pair(harness.artifact, "rhino", evidence)
    with pytest.raises(live.LiveGateError, match="path"):
        live._validate_scenario_artifacts(harness.artifact, scenario="rhino")


@requires_live_gate
def test_final_evidence_write_failure_emits_no_fabricated_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    harness = _install_fake_scenario(monkeypatch, tmp_path, scenario="rhino")
    original = live._atomic_write_bytes

    def fail_final(path: Path, payload: bytes):
        if path.name == "rhino-scenario.json":
            raise OSError("final disk failure")
        return original(path, payload)

    monkeypatch.setattr(live, "_atomic_write_bytes", fail_final)
    with pytest.raises(live.FinalEvidenceWriteError):
        live.run_live_scenario(scenario="rhino", rhino_exe=harness.rhino_exe, artifact_dir=harness.artifact)
    stdout = capsys.readouterr().out
    assert "scenario_result" not in stdout
    assert not (harness.artifact / "rhino-scenario.json").exists()
    assert not (harness.artifact / "rhino-scenario.sha256").exists()


@requires_live_gate
def test_main_exit_codes_and_bounded_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rhino = tmp_path / "Rhino.exe"
    rhino.write_bytes(b"fake")
    missing_parent = tmp_path / "missing" / "artifacts"
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        assert live.main(["run", "--scenario", "rhino", "--rhino-exe", str(rhino), "--artifact-dir", str(missing_parent)]) == 2
    assert 0 < len(stderr.getvalue()) <= 1200

    success_root = tmp_path / "success"
    success_root.mkdir()
    harness = _install_fake_scenario(monkeypatch, success_root, scenario="rhino")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        assert live.main(["run", "--scenario", "rhino", "--rhino-exe", str(harness.rhino_exe), "--artifact-dir", str(harness.artifact)]) == 0

    blocked_root = tmp_path / "blocked"
    blocked_root.mkdir()
    harness2 = _install_fake_scenario(monkeypatch, blocked_root, scenario="rhino", authorization="wrong")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        assert live.main(["run", "--scenario", "rhino", "--rhino-exe", str(harness2.rhino_exe), "--artifact-dir", str(harness2.artifact)]) == 2


@requires_live_gate
def test_early_failure_null_invariants(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rhino = tmp_path / "Rhino.exe"
    rhino.write_bytes(b"fake")
    artifact = tmp_path / "origin"
    monkeypatch.setattr(live, "_new_run_id", lambda: RUN_ID)
    monkeypatch.setattr(live, "_collect_and_validate_runtime_evidence", lambda: (_ for _ in ()).throw(live.LiveGateError("bad origin")))
    result = live.run_live_scenario(scenario="rhino", rhino_exe=rhino, artifact_dir=artifact)
    evidence = _load_final_artifact(artifact, "rhino")
    assert result.failure_label == "runtime_origin_invalid"
    assert evidence["target"] is None
    assert evidence["authorization"] is None
    assert evidence["pre_state"] is None
    assert evidence["telemetry"] is None


@requires_live_gate
def test_cli_is_absent_from_mcp_model_and_contained_surfaces() -> None:
    from rook import server

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert "containment_live_gate" not in names
    assert "run_live_scenario" not in names
    assert not hasattr(server, "containment_live_gate")
    source = Path(live.__file__).read_text(encoding="utf-8")
    for contained in live.CONTAINED_IDENTITIES:
        assert re.search(rf"[\"']{re.escape(contained)}[\"']", source) is None
    for forbidden in ("gh_solve", "gh_document_new"):
        assert re.search(rf"[\"']{re.escape(forbidden)}[\"']", source) is None
