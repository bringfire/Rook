from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "containment_release" / "live_gate.py"
FIXTURE_PATH = (
    ROOT
    / "scripts"
    / "containment_release"
    / "fixtures"
    / "containment_empty.ghx"
)
EXPECTED_RED = "EXPECTED_RED:containment-release-live:missing"
FIXTURE_SHA256 = "2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df"
RUN_ID = "1" * 32


def _load_live_gate():
    if not MODULE_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location("containment_release_live_gate", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


live = _load_live_gate()
requires_live_gate = pytest.mark.skipif(live is None, reason="external live gate is missing")


def test_external_live_gate_exists() -> None:
    assert live is not None, EXPECTED_RED


@requires_live_gate
def test_public_contract_is_exact_and_thin() -> None:
    assert live.SCENARIOS == ("rhino", "grasshopper")
    assert live.SPHERE_COMPONENT_GUID == "dabc854d-f50e-408a-b001-d043c7de151d"
    assert live.FIXTURE_SIZE == 2708
    assert live.FIXTURE_SHA256 == FIXTURE_SHA256
    assert live.RESULT_FIELDS == (
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
    assert list(inspect.signature(live.run_rhino_scenario).parameters) == ["inputs"]
    assert list(inspect.signature(live.run_grasshopper_scenario).parameters) == ["inputs"]
    assert list(inspect.signature(live.main).parameters) == ["argv"]


@requires_live_gate
def test_staged_fixture_is_exact_empty_lf_xml() -> None:
    payload = FIXTURE_PATH.read_bytes()
    assert len(payload) == 2708
    assert hashlib.sha256(payload).hexdigest() == FIXTURE_SHA256
    assert not payload.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in payload
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    root = ET.fromstring(payload.decode("utf-8"))
    object_count = root.find(
        "./chunks/chunk[@name='Definition']/chunks/"
        "chunk[@name='DefinitionObjects']/items/item[@name='ObjectCount']"
    )
    objects = root.find(
        "./chunks/chunk[@name='Definition']/chunks/"
        "chunk[@name='DefinitionObjects']/chunks"
    )
    assert object_count is not None and object_count.text == "0"
    assert objects is not None and objects.attrib == {"count": "0"}
    assert live._fixture_path() == FIXTURE_PATH


@requires_live_gate
def test_cli_is_closed_and_requires_absolute_fresh_paths(tmp_path: Path) -> None:
    parser = live._build_parser()
    rhino = (tmp_path / "Rhino.exe").resolve()
    python = (tmp_path / "venv" / "python.exe").resolve()
    package = (tmp_path / "site-packages" / "rook").resolve()
    forbidden = (tmp_path / "source").resolve()
    output = (tmp_path / "result.json").resolve()
    args = [
        "run",
        "--scenario",
        "rhino",
        "--rhino-exe",
        str(rhino),
        "--expected-python",
        str(python),
        "--expected-package-root",
        str(package),
        "--forbidden-source-root",
        str(forbidden),
        "--output",
        str(output),
    ]
    parsed = parser.parse_args(args)
    inputs = live._inputs_from_namespace(parsed)
    assert inputs == live.ScenarioInputs(
        rhino_exe=rhino,
        expected_python=python,
        expected_package_root=package,
        forbidden_source_roots=(forbidden,),
        output=output,
    )
    assert parsed.scenario == "rhino"

    rejected = (
        [*args, "--yes"],
        [*args, "--authorization", "anything"],
        [*args[:2], "bogus", *args[3:]],
    )
    for argv in rejected:
        with pytest.raises(SystemExit):
            parser.parse_args(argv)

    relative = parser.parse_args([*args[:-1], "result.json"])
    with pytest.raises(live.LiveGateError, match="absolute"):
        live._inputs_from_namespace(relative)
    output.write_text("owned by caller", encoding="utf-8")
    with pytest.raises(live.LiveGateError, match="new"):
        live._inputs_from_namespace(parsed)


@requires_live_gate
def test_authorization_is_exact_scenario_and_run_bound() -> None:
    target = {
        "label": "Rook containment Rhino scratch document",
        "process_id": 9001,
        "port": 19001,
        "scratch_path": rf"C:\scratch\RookContainmentRhino-{RUN_ID}.3dm",
    }
    challenge = live._build_authorization_challenge(
        scenario="rhino", run_id=RUN_ID, nonce="2" * 32, target=target
    )
    assert challenge["type"] == "authorization_required"
    assert challenge["scenario"] == "rhino"
    assert challenge["run_id"] == RUN_ID
    assert challenge["target"] == target
    assert "radius-4" in challenge["mutation"]
    assert "scripted point" in challenge["mutation"]
    assert "only the two gate-owned objects" in challenge["restoration"]
    required = challenge["required_response"]
    assert required.startswith(f"AUTHORIZE scenario=rhino run={RUN_ID} ")
    assert live._authorization_matches(challenge, (required + "\n").encode("ascii"))
    for rejected in (
        required.encode("ascii"),
        (required + " \n").encode("ascii"),
        (required.lower() + "\n").encode("ascii"),
        (required + "\nEXTRA\n").encode("ascii"),
    ):
        assert not live._authorization_matches(challenge, rejected)

    second = live._build_authorization_challenge(
        scenario="rhino", run_id="3" * 32, nonce="4" * 32, target=target
    )
    gh_target = dict(target, label="Rook containment Grasshopper scratch definition")
    grasshopper = live._build_authorization_challenge(
        scenario="grasshopper", run_id=RUN_ID, nonce="5" * 32, target=gh_target
    )
    assert second["required_response"] != required
    assert grasshopper["required_response"] != required


@requires_live_gate
def test_exact_mutation_argument_contracts() -> None:
    sphere = live._rhino_sphere_arguments(RUN_ID)
    assert sphere == {
        "type": "SPHERE",
        "center": [0, 0, 0],
        "radius": 4,
        "name": f"RookContainmentSphere-{RUN_ID}",
    }
    point = live._rhino_point_script(RUN_ID)
    assert point.count("RookContainmentPoint-") == 1
    assert f"RookContainmentPoint-{RUN_ID}" in point
    assert "Point3d(10.0, 0.0, 0.0)" in point
    assert "ROOK_POINT_ID=" in point

    edit = live._grasshopper_edit_arguments(RUN_ID, 7)
    assert edit == {
        "epoch": 7,
        "create": [
            {
                "temp_id": "T1",
                "type": "slider",
                "nick": f"RookContainmentRadius-{RUN_ID}",
                "min": 1,
                "max": 9,
                "value": 4,
                "pos": [100, 100],
            },
            {
                "temp_id": "T2",
                "guid": "dabc854d-f50e-408a-b001-d043c7de151d",
                "pos": [400, 100],
            },
        ],
        "connect": ["T1.O0>T2.I1"],
    }


@requires_live_gate
def test_runtime_origin_preflight_rejects_source_paths_and_wrong_rook_origins(
    tmp_path: Path,
) -> None:
    installed = (tmp_path / "installed" / "site-packages" / "rook").resolve()
    expected_python = (tmp_path / "installed" / "python.exe").resolve()
    source = (tmp_path / "source").resolve()
    clean = {
        "python_executable": str(expected_python),
        "sys_path": [str(installed.parent)],
        "rook_origins": {
            "rook": str(installed / "__init__.py"),
            "rook.server": str(installed / "server.py"),
        },
    }
    live._validate_runtime_evidence(
        clean,
        expected_python=expected_python,
        expected_package_root=installed,
        forbidden_source_roots=(source,),
    )
    dirty_path = dict(clean, sys_path=[str(source), str(installed.parent)])
    with pytest.raises(live.LiveGateError, match="sys.path"):
        live._validate_runtime_evidence(
            dirty_path,
            expected_python=expected_python,
            expected_package_root=installed,
            forbidden_source_roots=(source,),
        )
    wrong_origin = dict(clean, rook_origins={"rook": str(source / "rook" / "__init__.py")})
    with pytest.raises(live.LiveGateError, match="origin"):
        live._validate_runtime_evidence(
            wrong_origin,
            expected_python=expected_python,
            expected_package_root=installed,
            forbidden_source_roots=(source,),
        )


@requires_live_gate
def test_source_contains_no_legacy_framework_or_contained_tool_calls() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_framework = (
        "RetainedPathLease",
        "_ArtifactRootClaim",
        "OWNERSHIP_MARKER",
        "immutable_sidecar",
        "force_kill",
        ".kill(",
        "taskkill",
    )
    for forbidden in forbidden_framework:
        assert forbidden not in source
    for contained in (
        "gh_execute_intent",
        "rhino_execute_intent",
        "plan_and_execute",
        "spawn_agent",
        "gh_explore_workflow",
        "gh_replay_recipe",
        "gh_solve",
        "gh_document_new",
    ):
        assert re.search(rf"[\"']{re.escape(contained)}[\"']", source) is None


@requires_live_gate
def test_atomic_result_shape_is_closed() -> None:
    result = live._new_result("rhino", RUN_ID)
    assert tuple(result) == live.RESULT_FIELDS
    assert result["schema_version"] == 1
    assert result["scenario"] == "rhino"
    assert result["run_id"] == RUN_ID
    assert result["success"] is False
    assert result["operations"] == []
    assert isinstance(result["diagnostics"], list)
