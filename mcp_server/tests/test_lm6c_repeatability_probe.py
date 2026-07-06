from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm6c_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm6c_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical() -> None:
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600


def test_cli_rejects_non_positive_attempts() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--attempts", "0"])


def test_canonical_evidence_only_for_five_gemma_qat_attempts() -> None:
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=1, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=5, model="qwen3:14b") is False


def test_tool_result_ok_accepts_successful_mapping() -> None:
    assert PROBE._tool_result_ok({"ok": True}) is True
    assert PROBE._tool_result_ok({"status": "ready"}) is True


def test_tool_result_ok_rejects_failure_shapes() -> None:
    assert PROBE._tool_result_ok(None) is False
    assert PROBE._tool_result_ok({"ok": False}) is False
    assert PROBE._tool_result_ok({"success": False}) is False
    assert PROBE._tool_result_ok({"status": "error"}) is False
    assert PROBE._tool_result_ok({"status": "failed"}) is False
    assert PROBE._tool_result_ok({"error": "bad"}) is False
    assert PROBE._tool_result_ok({"errors": ["bad"]}) is False


def test_preflight_failed_row_does_not_invoke_lm6a() -> None:
    row = PROBE._preflight_failed_row(
        attempt_index=1,
        reason="gh_document_new_failed",
    )

    assert row["attempt_index"] == 1
    assert row["scheduled_attempt_id"] == "attempt-001"
    assert row["preflight_status"] == "failed"
    assert row["lm6a_invoked"] is False
    assert row["lm6a_returncode"] is None
    assert row["lm6a_run_dir"] is None
    assert row["lm6a_decision"] is None
    assert row["lm6a_reason"] is None
    assert row["terminal_category"] == "preflight_failed"
    assert row["failure_reason"] == "gh_document_new_failed"
    assert row["leak_check_performed"] is False
    assert row["leak_marker_match_count"] == 0


def test_discover_child_run_dir_uses_new_directory_not_stdout(tmp_path: Path) -> None:
    runs = tmp_path / "lm6a_runs"
    runs.mkdir()
    before = set(runs.glob("lm6a-*"))
    child = runs / "lm6a-20260706T000000Z-abc123"
    child.mkdir()

    assert PROBE._discover_child_run_dir(runs, before) == child


def test_discover_child_run_dir_rejects_missing_or_ambiguous(tmp_path: Path) -> None:
    runs = tmp_path / "lm6a_runs"
    runs.mkdir()
    before = set(runs.glob("lm6a-*"))
    assert PROBE._discover_child_run_dir(runs, before) is None
    (runs / "lm6a-a").mkdir()
    (runs / "lm6a-b").mkdir()
    assert PROBE._discover_child_run_dir(runs, before) is None


def test_classify_decision_preserves_lm6a_terminal_categories() -> None:
    assert PROBE._classify_decision({"decision": "accepted"}) == (
        "accepted",
        None,
    )
    assert PROBE._classify_decision({"decision": "gate_failed"}) == (
        "gate_failed",
        None,
    )
    assert PROBE._classify_decision({"decision": "publication_failed"}) == (
        "publication_failed",
        None,
    )


def test_classify_decision_rejects_unknown_decision() -> None:
    assert PROBE._classify_decision({"decision": "strange"}) == (
        "wrapper_error",
        "lm6a_unknown_decision:strange",
    )
    assert PROBE._classify_decision({}) == (
        "wrapper_error",
        "lm6a_missing_decision",
    )
