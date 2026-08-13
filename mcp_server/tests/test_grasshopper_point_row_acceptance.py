"""Compatibility checks for the reviewed point-row acceptance report."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from rook.gh_behavioral_acceptance import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "grasshopper_point_row_acceptance.py"
ACCEPTANCE_PATH = ROOT / "scripts" / "grasshopper_point_row_acceptance.json"


def _evaluator():
    spec = importlib.util.spec_from_file_location(
        "grasshopper_point_row_acceptance_for_tests",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _criterion(criterion_id: str, status: str) -> dict:
    return {
        "criterion_id": criterion_id,
        "status": status,
        "failure_ids": [] if status == "pass" else [criterion_id],
        "evidence_refs": ["baseline"],
    }


def _common_result(statuses: dict[str, str]) -> dict:
    order = [
        "adjustable_start_present",
        "adjustable_step_present",
        "adjustable_count_present",
        "point_count_equals_count",
        "x_values_equal_start_step_count",
        "all_y_zero",
        "all_z_zero",
        "no_runtime_errors",
    ]
    return {
        "schema": "rook.gh_behavioral_evaluation:v1",
        "status": "fail" if "fail" in statuses.values() else "incomplete" if "unproven" in statuses.values() else "pass",
        "criteria": [_criterion(criterion_id, statuses[criterion_id]) for criterion_id in order],
        "probe": {"status": "complete", "baseline": {}, "controls": [], "error": None},
        "source": {},
    }


def _retained_legacy_evaluation(*, opus: bool) -> dict:
    if opus:
        return {
            "snapshot_sha256": "BD25176EC4C7AF7C7A4559C87F97FA4F092FB394E0D30D38A57D5529FAC92F48",
            "criteria": {
                "adjustable_controls_present": {"status": "pass", "missing": []},
                "point_count_equals_count": {"status": "pass"},
                "first_x_equals_start": {"status": "pass"},
                "successive_x_difference_equals_step": {"status": "pass"},
                "all_yz_zero": {"status": "pass"},
                "no_runtime_errors": {"status": "pass"},
            },
        }
    return {
        "snapshot_sha256": "4B3E44B853D7EEC44D6052D2C4442BEB4CEE46BD3E728C14781FCDDB43C87AE8",
        "criteria": {
            "adjustable_controls_present": {"status": "fail", "missing": ["Step"]},
            "point_count_equals_count": {"status": "fail"},
            "first_x_equals_start": {"status": "unproven"},
            "successive_x_difference_equals_step": {"status": "unproven"},
            "all_yz_zero": {"status": "pass"},
            "no_runtime_errors": {"status": "pass"},
        },
    }


def _common_result_from_retained_legacy(value: dict) -> dict:
    legacy = value["criteria"]
    missing = set(legacy["adjustable_controls_present"]["missing"])
    x_status = (
        "fail"
        if "fail" in {
            legacy["first_x_equals_start"]["status"],
            legacy["successive_x_difference_equals_step"]["status"],
        }
        else "unproven"
        if "unproven" in {
            legacy["first_x_equals_start"]["status"],
            legacy["successive_x_difference_equals_step"]["status"],
        }
        else "pass"
    )
    return _common_result(
        {
            "adjustable_start_present": "fail" if "Start" in missing else "pass",
            "adjustable_step_present": "fail" if "Step" in missing else "pass",
            "adjustable_count_present": "fail" if "Count" in missing else "pass",
            "point_count_equals_count": legacy["point_count_equals_count"]["status"],
            "x_values_equal_start_step_count": x_status,
            "all_y_zero": legacy["all_yz_zero"]["status"],
            "all_z_zero": legacy["all_yz_zero"]["status"],
            "no_runtime_errors": legacy["no_runtime_errors"]["status"],
        }
    )


def test_frozen_artifact_is_canonical_closed_and_preserves_exact_intent():
    evaluator = _evaluator()
    artifact = evaluator.load_acceptance(ACCEPTANCE_PATH)

    assert ACCEPTANCE_PATH.read_bytes() == canonical_json_bytes(artifact)
    assert artifact["schema"] == "rook.gh_behavioral_acceptance:v1"
    assert artifact["intent"] == (
        "Create a Grasshopper definition that generates a row of points along "
        "the X axis using adjustable Start, Step, and Count controls, with Y "
        "and Z fixed at zero."
    )
    assert [control["role"] for control in artifact["controls"]] == [
        "Start",
        "Step",
        "Count",
    ]
    assert [criterion["id"] for criterion in artifact["criteria"]] == [
        "adjustable_start_present",
        "adjustable_step_present",
        "adjustable_count_present",
        "point_count_equals_count",
        "x_values_equal_start_step_count",
        "all_y_zero",
        "all_z_zero",
        "no_runtime_errors",
    ]


def test_authentic_opus_expectation_maps_to_six_passes():
    retained = _retained_legacy_evaluation(opus=True)
    assert retained["snapshot_sha256"] == "BD25176EC4C7AF7C7A4559C87F97FA4F092FB394E0D30D38A57D5529FAC92F48"
    report = _evaluator().compatibility_report(
        _common_result_from_retained_legacy(retained)
    )

    assert report["overall"] == "pass"
    assert report["failure_ids"] == []
    assert [item["status"] for item in report["criteria"]] == ["pass"] * 6


def test_authentic_qwen_expectation_fails_exactly_step_and_cardinality():
    retained = _retained_legacy_evaluation(opus=False)
    assert retained["snapshot_sha256"] == "4B3E44B853D7EEC44D6052D2C4442BEB4CEE46BD3E728C14781FCDDB43C87AE8"
    report = _evaluator().compatibility_report(
        _common_result_from_retained_legacy(retained)
    )
    by_id = {item["criterion_id"]: item for item in report["criteria"]}

    assert report["overall"] == "fail"
    assert report["failure_ids"] == [
        "adjustable_step_present",
        "point_count_equals_count",
    ]
    assert by_id["adjustable_controls_present"]["status"] == "fail"
    assert by_id["point_count_equals_count"]["status"] == "fail"
    assert by_id["successive_x_difference_equals_step"]["status"] == "unproven"
    assert by_id["all_yz_zero"]["status"] == "pass"
    assert by_id["no_runtime_errors"]["status"] == "pass"


def test_unproven_compatibility_items_do_not_become_failure_ids():
    statuses = {
        "adjustable_start_present": "pass",
        "adjustable_step_present": "pass",
        "adjustable_count_present": "pass",
        "point_count_equals_count": "pass",
        "x_values_equal_start_step_count": "unproven",
        "all_y_zero": "pass",
        "all_z_zero": "pass",
        "no_runtime_errors": "pass",
    }
    report = _evaluator().compatibility_report(_common_result(statuses))
    assert report["overall"] == "incomplete"
    assert report["failure_ids"] == []


def test_compatibility_mapping_rejects_missing_or_extra_common_criterion():
    result = _common_result(
        {
            "adjustable_start_present": "pass",
            "adjustable_step_present": "pass",
            "adjustable_count_present": "pass",
            "point_count_equals_count": "pass",
            "x_values_equal_start_step_count": "pass",
            "all_y_zero": "pass",
            "all_z_zero": "pass",
            "no_runtime_errors": "pass",
        }
    )
    result["criteria"].pop()
    with pytest.raises(ValueError, match="invalid_point_row_criteria"):
        _evaluator().compatibility_report(result)


def test_duplicate_key_or_pretty_acceptance_is_refused(tmp_path):
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"one","schema":"two"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate_json_key"):
        _evaluator().load_acceptance(duplicate)

    pretty = tmp_path / "pretty.json"
    pretty.write_text(ACCEPTANCE_PATH.read_text(encoding="utf-8").replace(",", ", ", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="noncanonical_json"):
        _evaluator().load_acceptance(pretty)


def test_cli_is_a_thin_common_evaluator_and_report_mapping(tmp_path, monkeypatch):
    evaluator = _evaluator()
    artifact = evaluator.load_acceptance(ACCEPTANCE_PATH)
    authoring = {"schema": "authoring-fixture"}
    probe = {"schema": "probe-fixture"}
    authoring_path = tmp_path / "authoring.json"
    probe_path = tmp_path / "probe.json"
    authoring_path.write_bytes(canonical_json_bytes(authoring))
    probe_path.write_bytes(canonical_json_bytes(probe))
    statuses = {
        criterion["id"]: "pass"
        for criterion in artifact["criteria"]
    }
    calls: list[tuple[dict, dict, dict]] = []

    def fake_common(received_artifact, received_authoring, received_probe):
        calls.append((received_artifact, received_authoring, received_probe))
        return _common_result(statuses)

    monkeypatch.setattr(evaluator, "evaluate_behavioral_probe", fake_common)
    report = evaluator.evaluate(artifact, authoring_path, probe_path)

    assert calls == [(artifact, authoring, probe)]
    assert report["overall"] == "pass"
