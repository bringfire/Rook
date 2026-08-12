"""Deterministic tests for the reviewed point-row acceptance artifact."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
EVALUATOR_PATH = ROOT / "scripts" / "grasshopper_point_row_acceptance.py"
ACCEPTANCE_PATH = ROOT / "scripts" / "grasshopper_point_row_acceptance.json"
SERIES_GUID = "e64c5fb1-845c-4ab1-8911-5f338516ba67"
POINT_GUID = "3581f42a-9592-4549-bd6b-1c0fc39d067b"


def _evaluator():
    spec = importlib.util.spec_from_file_location(
        "grasshopper_point_row_acceptance_for_tests",
        EVALUATOR_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _slider(component_id: str, nickname: str, value: float) -> dict:
    return {
        "id": component_id,
        "type": "NumberSlider",
        "nick": nickname,
        "is_param": True,
        "value": {"type": "slider", "val": value, "min": -100, "max": 100},
    }


def _input(index: int, sources: int) -> dict:
    return {"idx": index, "sources": sources}


def _output(index: int, kind: str, count: int, preview: list[str]) -> dict:
    return {
        "idx": index,
        "type": kind,
        "data": {"structure": "list", "count": count, "preview": preview},
    }


def _opus_snapshot() -> dict:
    return {
        "version": "1.0.0",
        "epoch": 4,
        "components": [
            _slider("C1", "Start", 0),
            _slider("C2", "Step", 5),
            _slider("C3", "Count", 10),
            {
                "id": "C4",
                "type": "Component_Series",
                "name": "Series",
                "componentGuid": SERIES_GUID,
                "inputs": [_input(0, 1), _input(1, 1), _input(2, 1)],
                "outputs": [_output(0, "Number", 10, ["0", "5", "10"])],
            },
            {
                "id": "C5",
                "type": "Component_ConstructPoint",
                "name": "Construct Point",
                "componentGuid": POINT_GUID,
                "inputs": [_input(0, 1), _input(1, 0), _input(2, 0)],
                "outputs": [
                    _output(0, "Point", 10, ["0,0,0", "5,0,0", "10,0,0"])
                ],
            },
        ],
        "flows": [
            "C4.O0>C5.I0",
            "C1.O0>C4.I0",
            "C2.O0>C4.I1",
            "C3.O0>C4.I2",
        ],
        "diagnostics": {"total": 5, "errors": 0, "warnings": 0},
    }


def _qwen_snapshot() -> dict:
    return {
        "version": "1.0.0",
        "epoch": 39,
        "components": [
            _slider("C15", "Start", 0),
            _slider("C16", "EndX", 100),
            _slider("C17", "Count", 10),
            {
                "id": "C18",
                "type": "Component_ConstructDomain",
                "componentGuid": "d1a28e95-cf96-4936-bf34-8bf142d731bf",
                "inputs": [_input(0, 1), _input(1, 1)],
                "outputs": [_output(0, "Domain", 1, ["0,100"])],
            },
            {
                "id": "C19",
                "type": "Component_Range",
                "componentGuid": "9445ca40-cc73-4861-a455-146308676855",
                "inputs": [_input(0, 1), _input(1, 1)],
                "outputs": [_output(0, "Number", 11, ["0", "10", "20"])],
            },
            {
                "id": "C20",
                "type": "Panel",
                "is_param": True,
                "value": {"type": "panel", "val": "0"},
            },
            {
                "id": "C21",
                "type": "Panel",
                "is_param": True,
                "value": {"type": "panel", "val": "0"},
            },
            {
                "id": "C22",
                "type": "Component_ConstructPoint",
                "name": "Construct Point",
                "componentGuid": POINT_GUID,
                "inputs": [_input(0, 1), _input(1, 1), _input(2, 1)],
                "outputs": [
                    _output(0, "Point", 11, ["0,0,0", "10,0,0", "20,0,0"])
                ],
            },
        ],
        "flows": [
            "C19.O0>C22.I0",
            "C20.O0>C22.I1",
            "C21.O0>C22.I2",
            "C18.O0>C19.I0",
            "C17.O0>C19.I1",
            "C15.O0>C18.I0",
            "C16.O0>C18.I1",
        ],
        "diagnostics": {"total": 8, "errors": 0, "warnings": 0},
    }


def _write_snapshot(path: Path, snapshot: dict) -> None:
    rows = [
        {
            "kind": "request",
            "payload": {
                "name": "gh_snapshot",
                "arguments": {"include_data": True, "max_preview_items": 3},
            },
        },
        {"kind": "result", "payload": {"success": True, "data": snapshot}},
    ]
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _evaluate(tmp_path: Path, snapshot: dict) -> dict:
    snapshot_path = tmp_path / "snapshot.jsonl"
    _write_snapshot(snapshot_path, snapshot)
    evaluator = _evaluator()
    acceptance = evaluator.load_acceptance(ACCEPTANCE_PATH)
    return evaluator.evaluate(acceptance, snapshot_path)


def _acceptance_document() -> dict:
    return json.loads(ACCEPTANCE_PATH.read_text(encoding="utf-8"))


def _evaluate_with_acceptance(tmp_path: Path, snapshot: dict, acceptance: dict) -> dict:
    acceptance_path = tmp_path / "acceptance.json"
    acceptance_path.write_text(json.dumps(acceptance), encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.jsonl"
    _write_snapshot(snapshot_path, snapshot)
    evaluator = _evaluator()
    return evaluator.evaluate(evaluator.load_acceptance(acceptance_path), snapshot_path)


def _criteria(result: dict) -> dict[str, dict]:
    return {item["criterion_id"]: item for item in result["criteria"]}


def test_reviewed_artifact_has_six_topology_neutral_criteria_and_guid_semantics():
    evaluator = _evaluator()
    artifact = evaluator.load_acceptance(ACCEPTANCE_PATH)

    assert [criterion["id"] for criterion in artifact["criteria"]] == [
        "adjustable_controls_present",
        "point_count_equals_count",
        "first_x_equals_start",
        "successive_x_difference_equals_step",
        "all_yz_zero",
        "no_runtime_errors",
    ]
    assert set(artifact["reviewed_primitive_semantics"]) == {
        SERIES_GUID,
        POINT_GUID,
    }
    assert artifact["reviewed_primitive_semantics"][SERIES_GUID]["kind"] == "series"
    assert (
        artifact["reviewed_primitive_semantics"][POINT_GUID]["kind"]
        == "construct_point"
    )


def test_opus_snapshot_passes_all_six_criteria(tmp_path):
    result = _evaluate(tmp_path, _opus_snapshot())

    assert result["overall"] == "pass"
    assert result["failure_ids"] == []
    assert [item["status"] for item in result["criteria"]] == ["pass"] * 6


def test_qwen_snapshot_fails_step_and_cardinality_without_guessing_step_semantics(
    tmp_path,
):
    result = _evaluate(tmp_path, _qwen_snapshot())
    criteria = _criteria(result)

    assert result["overall"] == "fail"
    assert result["failure_ids"] == [
        "adjustable_step_present",
        "point_count_equals_count",
    ]
    assert criteria["adjustable_controls_present"]["status"] == "fail"
    assert criteria["point_count_equals_count"]["status"] == "fail"
    assert criteria["successive_x_difference_equals_step"]["status"] == "unproven"
    assert criteria["all_yz_zero"]["status"] == "pass"
    assert criteria["no_runtime_errors"]["status"] == "pass"


def test_component_name_cannot_substitute_for_reviewed_guid(tmp_path):
    snapshot = _opus_snapshot()
    series = next(item for item in snapshot["components"] if item["id"] == "C4")
    series["componentGuid"] = "00000000-0000-0000-0000-000000000001"
    assert series["name"] == "Series"

    result = _evaluate(tmp_path, snapshot)

    assert _criteria(result)["successive_x_difference_equals_step"]["status"] == (
        "unproven"
    )
    assert result["overall"] == "incomplete"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda series: series["facts"].pop("output_count_equals_count"),
        lambda series: series["facts"].update(
            successive_difference_equals_step="true"
        ),
        lambda series: series.update(unreviewed_claim=True),
        lambda series: series["inputs"].update(extra=3),
    ],
)
def test_malformed_or_open_series_semantics_are_refused(tmp_path, mutation):
    artifact = _acceptance_document()
    series = artifact["reviewed_primitive_semantics"][SERIES_GUID]
    mutation(series)
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid_series_semantics"):
        _evaluator().load_acceptance(path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda point: point["facts"].pop("unconnected_y_default"),
        lambda point: point["facts"].update(unconnected_z_default="0"),
        lambda point: point.update(unreviewed_claim=True),
        lambda point: point["outputs"].update(extra=1),
    ],
)
def test_malformed_or_open_point_semantics_are_refused(tmp_path, mutation):
    artifact = _acceptance_document()
    point = artifact["reviewed_primitive_semantics"][POINT_GUID]
    mutation(point)
    path = tmp_path / "acceptance.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid_construct_point_semantics"):
        _evaluator().load_acceptance(path)


def test_false_series_fact_withholds_every_series_causal_claim(tmp_path):
    artifact = _acceptance_document()
    artifact["reviewed_primitive_semantics"][SERIES_GUID]["facts"][
        "first_value_equals_start"
    ] = False

    result = _evaluate_with_acceptance(tmp_path, _opus_snapshot(), artifact)
    criteria = _criteria(result)

    assert result["overall"] == "incomplete"
    assert criteria["point_count_equals_count"]["status"] == "unproven"
    assert criteria["first_x_equals_start"]["status"] == "unproven"
    assert criteria["successive_x_difference_equals_step"]["status"] == "unproven"
    assert all(
        criteria[criterion]["evidence"]["reviewed_causal_path"] is False
        for criterion in (
            "point_count_equals_count",
            "first_x_equals_start",
            "successive_x_difference_equals_step",
        )
    )


def test_altered_series_port_semantics_do_not_match_observed_wiring(tmp_path):
    artifact = _acceptance_document()
    artifact["reviewed_primitive_semantics"][SERIES_GUID]["inputs"]["step"] = 9

    result = _evaluate_with_acceptance(tmp_path, _opus_snapshot(), artifact)

    assert result["overall"] == "incomplete"
    assert (
        _criteria(result)["successive_x_difference_equals_step"]["status"]
        == "unproven"
    )


def test_reviewed_series_path_overrides_rounded_preview_decimals(tmp_path):
    snapshot = _opus_snapshot()
    next(item for item in snapshot["components"] if item["id"] == "C2")["value"][
        "val"
    ] = 1 / 3
    series = next(item for item in snapshot["components"] if item["id"] == "C4")
    series["outputs"][0]["data"]["preview"] = ["0", "0.333", "0.667"]
    point = next(item for item in snapshot["components"] if item["id"] == "C5")
    point["outputs"][0]["data"]["preview"] = [
        "0,0,0",
        "0.333,0,0",
        "0.667,0,0",
    ]

    result = _evaluate(tmp_path, snapshot)

    assert result["overall"] == "pass"
    assert _criteria(result)["first_x_equals_start"]["status"] == "pass"
    assert (
        _criteria(result)["successive_x_difference_equals_step"]["status"]
        == "pass"
    )


def test_preview_mismatch_without_reviewed_path_is_a_failure(tmp_path):
    snapshot = _opus_snapshot()
    series = next(item for item in snapshot["components"] if item["id"] == "C4")
    series["componentGuid"] = "00000000-0000-0000-0000-000000000001"
    point = next(item for item in snapshot["components"] if item["id"] == "C5")
    point["outputs"][0]["data"]["preview"] = [
        "1,0,0",
        "7,0,0",
        "13,0,0",
    ]

    result = _evaluate(tmp_path, snapshot)
    criteria = _criteria(result)

    assert criteria["first_x_equals_start"]["status"] == "fail"
    assert criteria["successive_x_difference_equals_step"]["status"] == "fail"


def test_unknown_point_component_keeps_yz_semantics_unproven(tmp_path):
    snapshot = _opus_snapshot()
    point = next(item for item in snapshot["components"] if item["id"] == "C5")
    point["componentGuid"] = "00000000-0000-0000-0000-000000000002"

    result = _evaluate(tmp_path, snapshot)

    assert _criteria(result)["all_yz_zero"]["status"] == "unproven"
    assert result["overall"] == "incomplete"


def test_missing_diagnostics_is_unproven_not_success(tmp_path):
    snapshot = _opus_snapshot()
    del snapshot["diagnostics"]

    result = _evaluate(tmp_path, snapshot)

    assert _criteria(result)["no_runtime_errors"]["status"] == "unproven"
    assert result["overall"] == "incomplete"


def test_nonzero_point_preview_fails_yz_even_without_reviewed_component(tmp_path):
    snapshot = _opus_snapshot()
    point = next(item for item in snapshot["components"] if item["id"] == "C5")
    point["componentGuid"] = "00000000-0000-0000-0000-000000000002"
    point["outputs"][0]["data"]["preview"][1] = "5,1,0"

    result = _evaluate(tmp_path, snapshot)

    assert _criteria(result)["all_yz_zero"]["status"] == "fail"
    assert "all_yz_zero" in result["failure_ids"]


def test_duplicate_json_key_in_snapshot_is_refused(tmp_path):
    path = tmp_path / "duplicate.jsonl"
    path.write_text(
        '{"kind":"request","kind":"result","payload":{}}\n',
        encoding="utf-8",
    )
    evaluator = _evaluator()
    acceptance = evaluator.load_acceptance(ACCEPTANCE_PATH)

    with pytest.raises(ValueError, match="duplicate_json_key"):
        evaluator.evaluate(acceptance, path)
