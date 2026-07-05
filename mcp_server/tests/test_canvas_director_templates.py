from __future__ import annotations

from copy import deepcopy
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from rook import canvas_director_templates as templates


REQUIRED_TEMPLATE_IDS = {
    "canvas_director.export_marker",
    "canvas_director.clock",
    "canvas_director.timing_gate",
    "canvas_director.oscillator",
    "canvas_director.actors_v2",
    "canvas_director.transform",
    "canvas_director.camera_path",
    "canvas_director.camera_controller",
}


FORBIDDEN_GENERIC_STRINGS = {
    "pearson_animation_test",
    "pearson_canvas_director_prototype",
    "pearson_canvas_director_prototype_20260704_144510",
    "pearson_v2_smoke",
    "roof_uplift_vertical_test_chunk_001",
    "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
    "C:\\Users\\bring",
    "C:/Users/bring",
    "OneDrive\\Desktop\\Pearson",
    "OneDrive/Desktop/Pearson",
}


PEARSON_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "canvas_director_templates"
TEMPLATE_SCRIPTS_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "rook"
    / "canvas_director_templates"
    / "scripts"
)
JSON_STRING_EMITTER_SCRIPTS = {
    "actors_v2.cs",
    "camera_controller.cs",
    "camera_path.cs",
    "export_marker.cs",
    "timing_gate.cs",
    "transform.cs",
}
NUMERIC_JSON_SCRIPTS = {
    "camera_controller.cs",
    "camera_path.cs",
    "clock.cs",
    "oscillator.cs",
    "timing_gate.cs",
    "transform.cs",
}


def _pip_command() -> list[str]:
    candidates = [[sys.executable, "-m", "pip"]]
    py_launcher = shutil.which("py")
    if py_launcher:
        candidates.extend(
            [
                [py_launcher, "-3.10", "-m", "pip"],
                [py_launcher, "-3", "-m", "pip"],
            ]
        )
    python = shutil.which("python")
    if python and python != sys.executable:
        candidates.append([python, "-m", "pip"])

    for command in candidates:
        probe = subprocess.run(
            [*command, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if probe.returncode == 0:
            return command

    pytest.fail("No pip-capable Python interpreter available for wheel asset test")


def _minimal_template_pack(script_path: str, script_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "template_pack_id": "canvas_director.test_pack",
        "templates": [
            {
                "template_id": "canvas_director.clock",
                "template_version": "0.1.0",
                "role": "clock",
                "display_name": "Director Clock",
                "default_nick": "clock",
                "script": {
                    "language": "csharp",
                    "path": script_path,
                    "sha256": script_sha256,
                },
                "inputs": [
                    {
                        "name": "Frame",
                        "type": "integer",
                        "description": "Current frame.",
                    }
                ],
                "outputs": [
                    {
                        "name": "Clock",
                        "type": "json",
                        "description": "Director clock payload.",
                    }
                ],
                "expected_output_payload_kind": "director_clock_payload",
            }
        ],
    }


def _write_minimal_template_pack(
    root: Path,
    *,
    script_text: str = "// test script\n",
    manifest_extra: dict[str, object] | None = None,
) -> Path:
    script_path = root / "scripts" / "clock.cs"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script_text, encoding="utf-8")

    pack = _minimal_template_pack(
        "scripts/clock.cs",
        templates.compute_file_sha256(script_path),
    )
    if manifest_extra:
        pack.update(manifest_extra)

    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    return manifest_path


def _load_pearson_fixture() -> dict:
    return templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)


def test_template_pack_has_exact_promoted_template_ids() -> None:
    pack = templates.load_template_pack()
    ids = {entry["template_id"] for entry in pack["templates"]}
    assert ids == REQUIRED_TEMPLATE_IDS


def test_transform_is_promoted_and_band_peel_is_only_strategy() -> None:
    pack = templates.load_template_pack()
    ids = {entry["template_id"] for entry in pack["templates"]}
    assert "canvas_director.transform" in ids
    assert "canvas_director.band_peel_wave_preview" not in ids

    transform = templates.template_by_id(pack, "canvas_director.transform")
    assert transform["role"] == "transform"
    assert "band_peel_wave" in transform["strategies"]

    serialized = json.dumps(pack, sort_keys=True)
    assert "canvas_director.band_peel_wave_preview" not in serialized


def test_block_piece_preview_is_not_promoted() -> None:
    pack = templates.load_template_pack()
    ids = {entry["template_id"] for entry in pack["templates"]}
    assert "canvas_director.block_piece_preview" not in ids
    assert all("Block Piece Preview" not in entry.get("display_name", "") for entry in pack["templates"])


def test_template_pack_validates_hashes_and_pin_contracts() -> None:
    pack = templates.load_template_pack()
    assert templates.validate_template_pack(pack) == []

    for template_id in REQUIRED_TEMPLATE_IDS:
        entry = templates.template_by_id(pack, template_id)
        assert entry["template_version"] == "0.1.0"
        assert entry["script"]["language"] == "csharp"
        assert entry["script"]["path"].startswith("scripts/")
        assert entry["script"]["sha256"].startswith("sha256:")
        assert entry["inputs"]
        assert entry["outputs"]


def test_typed_authoring_payload_contracts_are_declared() -> None:
    pack = templates.load_template_pack()
    expected_payloads = {
        "canvas_director.clock": "director_clock_payload",
        "canvas_director.actors_v2": "director_actor_runtime_payload",
        "canvas_director.transform": "director_motion_payload",
        "canvas_director.camera_controller": "director_camera_state",
        "canvas_director.export_marker": "rook.canvas_director.export",
    }
    for template_id, payload_kind in expected_payloads.items():
        entry = templates.template_by_id(pack, template_id)
        assert entry["expected_output_payload_kind"] == payload_kind


def test_generic_template_assets_do_not_leak_pearson_bindings() -> None:
    root = templates.template_root()
    generic_paths = [
        root / "manifest.json",
        *sorted((root / "scripts").glob("*.cs")),
    ]
    for path in generic_paths:
        text = path.read_text(encoding="utf-8")
        leaked = sorted(value for value in FORBIDDEN_GENERIC_STRINGS if value in text)
        assert leaked == [], f"{path} leaked Pearson-only values: {leaked}"


def test_template_validation_detects_raw_and_escaped_manifest_leaks(tmp_path: Path) -> None:
    manifest_path = _write_minimal_template_pack(
        tmp_path,
        manifest_extra={
            "raw_forbidden_capture": "pearson_canvas_director_prototype_20260704_144510",
            "raw_forbidden_prototype": "pearson_canvas_director_prototype",
            "raw_forbidden_path": "C:/Users/bring",
            "escaped_forbidden_path": "C:\\Users\\bring",
        },
    )

    pack = templates.load_template_pack(manifest_path)
    errors = templates.validate_template_pack(pack)
    leak_errors = [error for error in errors if "manifest:forbidden_generic_string" in error]

    assert any("pearson_canvas_director_prototype_20260704_144510" in error for error in leak_errors)
    assert any("pearson_canvas_director_prototype" in error for error in leak_errors)
    assert any("C:/Users/bring" in error for error in leak_errors)
    assert any("C:\\Users\\bring" in error for error in leak_errors)


def test_template_validation_scans_double_underscore_manifest_metadata(tmp_path: Path) -> None:
    manifest_path = _write_minimal_template_pack(
        tmp_path,
        manifest_extra={"__notes": "C:/Users/bring"},
    )

    pack = templates.load_template_pack(manifest_path)
    errors = templates.validate_template_pack(pack)

    assert "manifest:forbidden_generic_string:C:/Users/bring" in errors


def test_template_validation_detects_escaped_script_leaks(tmp_path: Path) -> None:
    manifest_path = _write_minimal_template_pack(
        tmp_path,
        script_text='var path = "C:\\\\Users\\\\bring";\n',
    )

    pack = templates.load_template_pack(manifest_path)
    errors = templates.validate_template_pack(pack)

    assert any(
        "clock.cs:forbidden_generic_string" in error and "C:\\Users\\bring" in error
        for error in errors
    )


@pytest.mark.parametrize("script_name", sorted(JSON_STRING_EMITTER_SCRIPTS))
def test_json_string_emitter_scripts_escape_control_characters(script_name: str) -> None:
    text = (TEMPLATE_SCRIPTS_ROOT / script_name).read_text(encoding="utf-8")

    assert "case '\\b':" in text
    assert "case '\\f':" in text
    assert "case '\\n':" in text
    assert "case '\\r':" in text
    assert "case '\\t':" in text
    assert "ch < 0x20" in text
    assert '.ToString("X4", CultureInfo.InvariantCulture)' in text


@pytest.mark.parametrize("script_name", sorted(NUMERIC_JSON_SCRIPTS))
def test_numeric_json_scripts_guard_non_finite_values(script_name: str) -> None:
    text = (TEMPLATE_SCRIPTS_ROOT / script_name).read_text(encoding="utf-8")

    assert "double.IsNaN" in text
    assert "double.IsInfinity" in text


def test_actors_v2_contains_metadata_read_failures() -> None:
    text = (TEMPLATE_SCRIPTS_ROOT / "actors_v2.cs").read_text(encoding="utf-8")

    assert "catch (Exception ex)" in text
    assert "RuntimePayload = \"\";" in text
    assert "GroupCount = 0;" in text
    assert "Director Actors v2 error:" in text


def test_loaded_manifest_root_is_used_for_script_validation(tmp_path: Path) -> None:
    manifest_path = _write_minimal_template_pack(tmp_path)

    pack = templates.load_template_pack(manifest_path)

    assert templates.validate_template_pack(pack) == []


def test_loaded_manifest_root_is_used_for_script_hash_validation(tmp_path: Path) -> None:
    manifest_path = _write_minimal_template_pack(tmp_path, script_text="// before\n")
    pack = templates.load_template_pack(manifest_path)
    (tmp_path / "scripts" / "clock.cs").write_text("// after\n", encoding="utf-8")

    errors = templates.validate_template_pack(pack)

    assert "canvas_director.clock:script_sha256_mismatch" in errors
    assert "canvas_director.clock:missing_script_file" not in errors


def test_template_validation_reports_directory_script_path_without_raising(tmp_path: Path) -> None:
    script_dir = tmp_path / "scripts" / "clock.cs"
    script_dir.mkdir(parents=True)
    pack = _minimal_template_pack("scripts/clock.cs", "sha256:" + "0" * 64)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

    loaded_pack = templates.load_template_pack(manifest_path)
    errors = templates.validate_template_pack(loaded_pack)

    assert "canvas_director.clock:script_not_file" in errors


def test_pearson_fixture_contains_project_bindings_and_valid_template_refs() -> None:
    pack = templates.load_template_pack()
    fixture = _load_pearson_fixture()
    ids = {entry["template_id"] for entry in pack["templates"]}

    assert fixture["fixture_id"] == "pearson_v2_smoke"
    assert fixture["export_id"] == "pearson_animation_test"
    assert fixture["proposal_id"] == "pearson_v2_smoke"
    assert fixture["templates"] == sorted(REQUIRED_TEMPLATE_IDS)
    assert set(fixture["templates"]) <= ids
    assert fixture["actor_bindings"]["actor_set_ref"].endswith("roof_uplift_vertical_test_chunk_001.json")
    assert fixture["motion"]["strategy"] == "band_peel_wave"
    assert fixture["motion"]["max_height"] == 12000


def test_instantiation_plan_uses_existing_grasshopper_tools_only() -> None:
    fixture = _load_pearson_fixture()
    plan = templates.build_instantiation_plan(fixture)
    tool_names = [call["tool"] for call in plan["calls"]]

    assert tool_names.count("gh_create_script") == 8
    assert "gh_snapshot" in tool_names
    assert "gh_edit" in tool_names
    assert set(tool_names) <= {"gh_create_script", "gh_snapshot", "gh_edit"}
    assert plan["extract_tool"] == "rhino_director_canvas_extract"


def test_instantiation_plan_connects_typed_payload_outputs_to_export_marker() -> None:
    fixture = _load_pearson_fixture()
    plan = templates.build_instantiation_plan(fixture)
    connections = plan["deferred_edit"]["connect"]

    assert "actors_v2.O2>export_marker.I0" in connections
    assert "transform.O1>export_marker.I1" in connections
    assert "camera_controller.O2>export_marker.I2" in connections
    assert "TFpsControl.O0>export_marker.I3" in connections
    assert "TFrameCountControl.O0>export_marker.I4" in connections
    assert "TExportIdControl.O0>export_marker.I5" in connections
    assert "TProposalIdControl.O0>export_marker.I6" in connections
    assert "TResolutionControl.O0>export_marker.I7" in connections


def test_instantiation_plan_binds_export_marker_name_to_fixture_export_id() -> None:
    fixture = _load_pearson_fixture()
    plan = templates.build_instantiation_plan(fixture)
    export_call = next(call for call in plan["calls"] if call["alias"] == "export_marker")

    assert export_call["arguments"]["name"] == "CanvasDirector Export:pearson_animation_test"


def test_gh_edit_temp_ids_are_supported_t_ids() -> None:
    fixture = _load_pearson_fixture()
    plan = templates.build_instantiation_plan(fixture)
    temp_ids = [entry["temp_id"] for entry in plan["deferred_edit"]["create"]]
    assert temp_ids
    assert all(temp_id.startswith("T") for temp_id in temp_ids)
    assert all(temp_id[1:2].isupper() for temp_id in temp_ids)


@pytest.mark.parametrize(
    "broken_path, broken_value",
    [
        (("timeline", "fps"), None),
        (("layout", "origin"), [-1200]),
    ],
)
def test_instantiation_plan_rejects_invalid_fixture(
    broken_path: tuple[str, ...],
    broken_value: object,
) -> None:
    fixture = _load_pearson_fixture()
    parent = fixture
    for key in broken_path[:-1]:
        parent = parent[key]
    if broken_value is None:
        del parent[broken_path[-1]]
    else:
        parent[broken_path[-1]] = broken_value

    with pytest.raises(templates.CanvasDirectorTemplateError) as exc_info:
        templates.build_instantiation_plan(fixture)

    assert exc_info.value.code == "invalid_fixture"


@pytest.mark.asyncio
async def test_instantiate_fixture_executes_script_snapshot_and_edit_calls() -> None:
    calls: list[tuple[str, dict]] = []
    script_components: list[dict[str, object]] = []

    async def fake_call_tool(tool: str, arguments: dict) -> dict:
        calls.append((tool, arguments))
        if tool == "gh_create_script":
            script_components.append(
                {
                    "id": f"C{len(script_components) + 1}",
                    "nick": arguments["name"],
                    "pos": [arguments["x"], arguments["y"]],
                }
            )
            return {
                "success": True,
                "data": {
                    "component_guid": f"{arguments['name'].replace(' ', '_')}_guid",
                    "name": arguments["name"],
                    "position": {"x": arguments["x"], "y": arguments["y"]},
                },
            }
        if tool == "gh_snapshot":
            return {"success": True, "data": {"epoch": 17, "components": list(reversed(script_components))}}
        if tool == "gh_edit":
            assert arguments["epoch"] == 17
            assert arguments["connect"]
            return {"success": True, "data": {"ok": True}}
        raise AssertionError(f"unexpected tool {tool}")

    fixture = _load_pearson_fixture()
    result = await templates.instantiate_fixture(fixture, fake_call_tool)

    assert result["success"] is True
    assert [tool for tool, _ in calls].count("gh_create_script") == 8
    assert [tool for tool, _ in calls][-2:] == ["gh_snapshot", "gh_edit"]

    final_edit = calls[-1][1]
    final_flows = final_edit["connect"]
    joined = "\n".join(final_flows)
    assert "actors_v2." not in joined
    assert "transform." not in joined
    assert "camera_controller." not in joined
    assert "export_marker." not in joined
    assert "Director_Actors_guid" not in joined
    assert "Director_Transform_guid" not in joined
    assert "CanvasDirector_Export_guid" not in joined
    assert "C4.O2>C5.I0" in final_flows
    assert "C5.O1>C8.I1" in final_flows
    assert "C7.O2>C8.I2" in final_flows
    assert "TFpsControl.O0>C8.I3" in final_flows
    assert "TFrameCountControl.O0>C8.I4" in final_flows

    group_members = final_edit["groups"][0]["members"]
    assert "C4" in group_members
    assert "C5" in group_members
    assert "C8" in group_members
    assert "actors_v2" not in group_members
    assert "transform" not in group_members
    assert "export_marker" not in group_members

    plan_flows = result["plan"]["deferred_edit"]["connect"]
    assert "actors_v2.O2>transform.I0" in plan_flows
    assert "transform.O1>export_marker.I1" in plan_flows
    assert "camera_controller.O2>export_marker.I2" in plan_flows


@pytest.mark.asyncio
async def test_instantiate_fixture_waits_for_deferred_edit_solve_before_returning() -> None:
    calls: list[tuple[str, dict]] = []
    script_components: list[dict[str, object]] = []
    status_results = [
        {
            "success": True,
            "data": {
                "solverEnabled": False,
                "solutionState": "PreProcess",
                "ready_for_edit": True,
            },
        },
        {
            "success": True,
            "data": {
                "solverEnabled": True,
                "solutionState": "PostProcess",
                "ready_for_edit": True,
            },
        },
    ]

    async def fake_call_tool(tool: str, arguments: dict) -> dict:
        calls.append((tool, arguments))
        if tool == "gh_create_script":
            script_components.append(
                {
                    "id": f"C{len(script_components) + 1}",
                    "nick": arguments["name"],
                    "pos": [arguments["x"], arguments["y"]],
                }
            )
            return {
                "success": True,
                "data": {
                    "component_guid": f"{arguments['name'].replace(' ', '_')}_guid",
                    "name": arguments["name"],
                    "position": {"x": arguments["x"], "y": arguments["y"]},
                },
            }
        if tool == "gh_snapshot":
            return {"success": True, "data": {"epoch": 17, "components": list(reversed(script_components))}}
        if tool == "gh_edit":
            return {
                "success": True,
                "data": {
                    "edit_summary": {
                        "solve_scheduled": True,
                        "verification_deferred": True,
                    },
                },
            }
        if tool == "gh_status":
            return status_results.pop(0)
        raise AssertionError(f"unexpected tool {tool}")

    result = await templates.instantiate_fixture(_load_pearson_fixture(), fake_call_tool)

    assert result["success"] is True
    assert [tool for tool, _ in calls][-3:] == ["gh_edit", "gh_status", "gh_status"]
    assert result["results"]["post_edit_solve_ready"]["data"]["solutionState"] == "PostProcess"


@pytest.mark.parametrize(
    "status",
    [
        {"success": True, "data": {"ready_for_edit": True}},
        {
            "success": True,
            "data": {
                "ready_for_edit": True,
                "solverEnabled": None,
                "solutionState": "PostProcess",
            },
        },
        {
            "success": True,
            "data": {
                "ready_for_edit": True,
                "solverEnabled": True,
                "solutionState": None,
            },
        },
        {
            "success": True,
            "data": {
                "ready_for_edit": True,
                "solverEnabled": True,
                "solutionState": "unknown",
            },
        },
    ],
)
def test_deferred_solve_readiness_requires_known_enabled_solver_status(status: dict) -> None:
    assert templates.instantiator._status_is_solve_ready(status) is False


@pytest.mark.asyncio
async def test_deferred_solve_wait_times_out_when_status_never_becomes_known(monkeypatch) -> None:
    monkeypatch.setattr(templates.instantiator, "POST_EDIT_SOLVE_READY_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(templates.instantiator, "POST_EDIT_SOLVE_READY_POLL_SECONDS", 0.001)

    async def fake_call_tool(tool: str, arguments: dict) -> dict:
        assert tool == "gh_status"
        return {"success": True, "data": {"ready_for_edit": True}}

    with pytest.raises(templates.CanvasDirectorTemplateError) as exc_info:
        await templates.instantiator._wait_for_deferred_edit_solve(
            {
                "success": True,
                "data": {
                    "edit_summary": {
                        "solve_scheduled": True,
                        "verification_deferred": True,
                    },
                },
            },
            fake_call_tool,
        )

    assert exc_info.value.code == "gh_solve_not_ready"


@pytest.mark.asyncio
async def test_instantiate_fixture_surfaces_failed_tool_call() -> None:
    async def fake_call_tool(tool: str, arguments: dict) -> dict:
        if tool == "gh_create_script":
            return {"success": False, "data": "compile failed"}
        raise AssertionError(f"unexpected tool {tool}")

    with pytest.raises(templates.CanvasDirectorTemplateError) as exc_info:
        await templates.instantiate_fixture(_load_pearson_fixture(), fake_call_tool)

    assert exc_info.value.code == "tool_call_failed"


@pytest.mark.asyncio
async def test_instantiate_fixture_surfaces_missing_component_guid() -> None:
    async def fake_call_tool(tool: str, arguments: dict) -> dict:
        if tool == "gh_create_script":
            return {"success": True, "data": {}}
        raise AssertionError(f"unexpected tool {tool}")

    with pytest.raises(templates.CanvasDirectorTemplateError) as exc_info:
        await templates.instantiate_fixture(_load_pearson_fixture(), fake_call_tool)

    assert exc_info.value.code == "missing_component_guid"


@pytest.mark.asyncio
async def test_instantiate_fixture_does_not_mutate_stored_plan() -> None:
    calls: list[tuple[str, dict]] = []
    script_components: list[dict[str, object]] = []

    async def fake_call_tool(tool: str, arguments: dict) -> dict:
        calls.append((tool, arguments))
        if tool == "gh_create_script":
            script_components.append(
                {
                    "id": f"C{len(script_components) + 1}",
                    "nick": arguments["name"],
                    "pos": [arguments["x"], arguments["y"]],
                }
            )
            return {
                "success": True,
                "data": {
                    "component_guid": f"{arguments['name'].replace(' ', '_')}_guid",
                    "name": arguments["name"],
                    "position": {"x": arguments["x"], "y": arguments["y"]},
                },
            }
        if tool == "gh_snapshot":
            return {"success": True, "data": {"epoch": 17, "components": list(reversed(script_components))}}
        if tool == "gh_edit":
            return {"success": True, "data": {"ok": True}}
        raise AssertionError(f"unexpected tool {tool}")

    fixture = _load_pearson_fixture()
    plan_before = templates.build_instantiation_plan(deepcopy(fixture))
    result = await templates.instantiate_fixture(fixture, fake_call_tool)

    assert result["plan"]["deferred_edit"]["connect"] == plan_before["deferred_edit"]["connect"]
    assert "actors_v2.O2>transform.I0" in result["plan"]["deferred_edit"]["connect"]
    assert "transform.O1>export_marker.I1" in result["plan"]["deferred_edit"]["connect"]

    final_flows = calls[-1][1]["connect"]
    assert "C4.O2>C5.I0" in final_flows
    assert "C5.O1>C8.I1" in final_flows
    assert "actors_v2.O2>transform.I0" not in final_flows
    assert "transform.O1>export_marker.I1" not in final_flows


@pytest.mark.parametrize(
    "template_id",
    [
        "canvas_director.band_peel_wave_preview",
        "canvas_director.block_piece_preview",
    ],
)
def test_deferred_prototype_ids_are_not_resolvable(template_id: str) -> None:
    pack = templates.load_template_pack()
    with pytest.raises(templates.CanvasDirectorTemplateError, match="template_not_found"):
        templates.template_by_id(pack, template_id)


def test_template_assets_are_present_in_built_wheel(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    project_root = Path(__file__).resolve().parents[2]
    mcp_project = project_root / "mcp_server"

    subprocess.run(
        [*_pip_command(), "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), str(mcp_project)],
        cwd=project_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    wheels = sorted(wheelhouse.glob("rook_mcp-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())

    assert "rook/canvas_director_templates/manifest.json" in names
    assert "rook/canvas_director_templates/scripts/export_marker.cs" in names
    assert "rook/canvas_director_templates/fixtures/pearson_v2_smoke.json" not in names
