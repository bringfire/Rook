from __future__ import annotations

import json
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
    "pearson_v2_smoke",
    "roof_uplift_vertical_test_chunk_001",
    "a28cbdb5-51fa-46b2-b18b-ab880b54ded7",
    "C:\\Users\\bring",
    "C:/Users/bring",
    "OneDrive\\Desktop\\Pearson",
    "OneDrive/Desktop/Pearson",
}


PEARSON_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "canvas_director_templates"


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


def test_pearson_fixture_contains_project_bindings_and_valid_template_refs() -> None:
    pack = templates.load_template_pack()
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
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
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    plan = templates.build_instantiation_plan(fixture)
    tool_names = [call["tool"] for call in plan["calls"]]

    assert tool_names.count("gh_create_script") == 8
    assert "gh_snapshot" in tool_names
    assert "gh_edit" in tool_names
    assert set(tool_names) <= {"gh_create_script", "gh_snapshot", "gh_edit"}
    assert plan["extract_tool"] == "rhino_director_canvas_extract"


def test_instantiation_plan_connects_typed_payload_outputs_to_export_marker() -> None:
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    plan = templates.build_instantiation_plan(fixture)
    connections = plan["deferred_edit"]["connect"]

    assert "actors_v2.O1>export_marker.I0" in connections
    assert "transform.O0>export_marker.I1" in connections
    assert "camera_controller.O1>export_marker.I2" in connections
    assert "TFpsControl.O0>export_marker.I3" in connections
    assert "TFrameCountControl.O0>export_marker.I4" in connections
    assert "TExportIdControl.O0>export_marker.I5" in connections
    assert "TProposalIdControl.O0>export_marker.I6" in connections
    assert "TResolutionControl.O0>export_marker.I7" in connections


def test_gh_edit_temp_ids_are_supported_t_ids() -> None:
    fixture = templates.load_fixture_binding("pearson_v2_smoke", fixture_root=PEARSON_FIXTURE_ROOT)
    plan = templates.build_instantiation_plan(fixture)
    temp_ids = [entry["temp_id"] for entry in plan["deferred_edit"]["create"]]
    assert temp_ids
    assert all(temp_id.startswith("T") for temp_id in temp_ids)
    assert all(temp_id[1:2].isupper() for temp_id in temp_ids)


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

    import subprocess
    import sys

    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(wheelhouse), "mcp_server"],
        cwd=Path(__file__).resolve().parents[2],
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
