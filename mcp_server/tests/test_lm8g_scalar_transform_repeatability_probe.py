from __future__ import annotations

import importlib.util
import json
import sys
import subprocess
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8g_scalar_transform_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8g_scalar_transform_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_lm8g_shape():
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600
    assert PROBE._canonical_evidence(attempts=args.attempts, model=args.model) is True


def test_cli_rejects_non_positive_attempts():
    for value in ("0", "-1"):
        with pytest.raises(SystemExit):
            PROBE._args(["--attempts", value])


def test_canonical_evidence_only_for_five_gemma_attempts():
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=1, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=5, model="qwen3:14b") is False


def test_cli_rejects_non_lm8g_surfaces():
    forbidden = (
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
        ["--phase", "receipt_recon"],
    )
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8g_identity():
    manifest = PROBE._manifest(attempts=5, model="gemma4:12b-it-qat")

    assert manifest["schema"] == "rook.lm8g_scalar_transform_repeatability_probe:v1"
    assert manifest["attempts"] == 5
    assert manifest["model"] == "gemma4:12b-it-qat"
    assert manifest["canonical_evidence"] is True


def test_lm8f_command_uses_sys_executable_and_child_run_dir(tmp_path: Path, monkeypatch):
    runs_dir = tmp_path / "lm8f_runs"
    monkeypatch.chdir(tmp_path)

    command = PROBE._lm8f_command(
        model="gemma4:12b-it-qat",
        lm8f_runs_dir=runs_dir,
    )

    assert command == [
        sys.executable,
        str(PROBE._REPO_ROOT / "scripts" / "lm8f_scalar_transform_depth_probe.py"),
        "--model",
        "gemma4:12b-it-qat",
        "--run-dir",
        str(runs_dir),
    ]
    assert "--retry-clean-observation" not in command
    assert "--gh-edit" not in command


def test_scheduled_attempt_id_is_stable():
    assert PROBE._scheduled_attempt_id(1) == "attempt-001"
    assert PROBE._scheduled_attempt_id(12) == "attempt-012"


def test_base_attempt_row_has_lm8g_fields():
    row = PROBE._base_attempt_row(attempt_index=1)

    assert row["attempt_index"] == 1
    assert row["scheduled_attempt_id"] == "attempt-001"
    assert row["lm8f_invoked"] is False
    assert row["lm8f_returncode"] is None
    assert row["lm8f_run_dir"] is None
    assert row["terminal_category"] is None
    assert row["leak_check_performed"] is False
    assert row["leak_marker_match_count"] == 0


def test_discover_child_run_dirs_uses_filesystem_delta(tmp_path: Path):
    runs_dir = tmp_path / "lm8f_runs"
    runs_dir.mkdir()
    existing = runs_dir / "lm8f-existing"
    existing.mkdir()
    before = set(runs_dir.glob("lm8f-*"))
    child = runs_dir / "lm8f-new"
    child.mkdir()

    assert PROBE._discover_child_run_dirs(runs_dir, before) == [child]


def test_read_decision_handles_missing_invalid_and_non_mapping(tmp_path: Path):
    missing, missing_error = PROBE._read_decision(tmp_path / "missing.json")
    assert missing is None
    assert missing_error == "lm8f_missing_decision_json"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{bad", encoding="utf-8")
    invalid, invalid_error = PROBE._read_decision(invalid_path)
    assert invalid is None
    assert invalid_error == "lm8f_invalid_decision_json"

    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    non_mapping, non_mapping_error = PROBE._read_decision(list_path)
    assert non_mapping is None
    assert non_mapping_error == "lm8f_decision_not_mapping"


def test_classify_decision_preserves_known_lm8f_categories():
    for decision in (
        "accepted",
        "rejected",
        "worker_declined",
        "publication_failed",
        "gate_failed",
        "preflight_failed",
    ):
        assert PROBE._classify_decision({"decision": decision}) == (decision, None)


def test_classify_decision_rejects_unknown_or_missing_value():
    assert PROBE._classify_decision({}) == (
        "wrapper_error",
        "lm8f_missing_decision",
    )
    assert PROBE._classify_decision({"decision": "strange"}) == (
        "wrapper_error",
        "lm8f_unknown_decision:strange",
    )
def _write_child_decision(child: Path, payload: dict) -> None:
    child.mkdir(parents=True, exist_ok=True)
    (child / "decision.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def test_completed_text_and_excerpt_handle_bytes_none_and_length():
    assert PROBE._completed_text(None) == ""
    assert PROBE._completed_text(b"abc") == "abc"
    assert PROBE._completed_text("xyz") == "xyz"

    assert PROBE._excerpt(None) == ""
    assert PROBE._excerpt("") == ""
    assert PROBE._excerpt("abcdef", limit=4) == "abcd"
    assert PROBE._excerpt("abc", limit=4) == "abc"


def test_row_from_completed_accepted_lm8f_child(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    _write_child_decision(
        child,
        {
            "decision": "accepted",
            "reason": "verify_scalar_output_succeeded",
            "worker_publication_ran": True,
            "live_fixture_created": True,
            "live_set_value_dispatched": True,
            "verify_scalar_output_ran": True,
            "scalar_runtime_ready": True,
            "observed_output_after": 7.5,
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="run_dir=child decision=accepted",
        stderr="",
    )

    row = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["lm8f_invoked"] is True
    assert row["lm8f_returncode"] == 0
    assert row["lm8f_run_dir"] == str(child)
    assert row["lm8f_decision"] == "accepted"
    assert row["lm8f_reason"] == "verify_scalar_output_succeeded"
    assert row["terminal_category"] == "accepted"
    assert row["failure_reason"] is None
    assert row["worker_publication_ran"] is True
    assert row["live_set_value_dispatched"] is True
    assert row["verify_scalar_output_ran"] is True
    assert row["scalar_runtime_ready"] is True
    assert row["observed_output_after"] == 7.5


def test_row_from_completed_nonzero_returncode_is_wrapper_error(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    _write_child_decision(child, {"decision": "accepted"})
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="partial stdout",
        stderr="partial stderr",
    )

    row = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8f_nonzero_returncode:2"
    assert row["child_run_dir_error"] is None
    assert row["lm8f_run_dir"] == str(child)
    assert row["stdout_excerpt"] == "partial stdout"
    assert row["stderr_excerpt"] == "partial stderr"


def test_row_from_completed_nonzero_returncode_keeps_subprocess_reason_if_child_missing():
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="partial stdout",
        stderr="partial stderr",
    )

    row = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8f_nonzero_returncode:2"
    assert row["child_run_dir_error"] == "child_run_dir_missing"
    assert row["lm8f_run_dir"] is None


def test_row_from_completed_missing_and_ambiguous_child_dirs_are_wrapper_errors(tmp_path: Path):
    completed = subprocess.CompletedProcess(args=["python"], returncode=0, stdout="", stderr="")

    missing = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[],
    )
    assert missing["terminal_category"] == "wrapper_error"
    assert missing["failure_reason"] == "child_run_dir_missing"

    first = tmp_path / "lm8f-a"
    second = tmp_path / "lm8f-b"
    first.mkdir()
    second.mkdir()
    ambiguous = PROBE._row_from_completed_lm8f(
        attempt_index=2,
        completed=completed,
        child_run_dirs=[first, second],
    )
    assert ambiguous["terminal_category"] == "wrapper_error"
    assert ambiguous["failure_reason"] == "child_run_dir_ambiguous"


def test_timeout_and_subprocess_error_rows_preserve_child_dir_when_present(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    child.mkdir()
    timeout = subprocess.TimeoutExpired(
        cmd=["python"],
        timeout=600,
        output="stdout before timeout",
        stderr="stderr before timeout",
    )

    timeout_row = PROBE._timeout_row(
        attempt_index=1,
        exc=timeout,
        child_run_dirs=[child],
    )
    assert timeout_row["terminal_category"] == "wrapper_error"
    assert timeout_row["failure_reason"] == "lm8f_timeout"
    assert timeout_row["child_run_dir_error"] is None
    assert timeout_row["lm8f_run_dir"] == str(child)
    assert timeout_row["stdout_excerpt"] == "stdout before timeout"
    assert timeout_row["stderr_excerpt"] == "stderr before timeout"

    error_row = PROBE._subprocess_error_row(
        attempt_index=2,
        exc=OSError("launch failed"),
        child_run_dirs=[child],
    )
    assert error_row["terminal_category"] == "wrapper_error"
    assert error_row["failure_reason"] == "lm8f_subprocess_error:OSError"
    assert error_row["child_run_dir_error"] is None
    assert error_row["lm8f_run_dir"] == str(child)


def test_timeout_and_subprocess_error_keep_primary_reason_when_child_missing():
    timeout = subprocess.TimeoutExpired(cmd=["python"], timeout=600)

    timeout_row = PROBE._timeout_row(
        attempt_index=1,
        exc=timeout,
        child_run_dirs=[],
    )
    assert timeout_row["terminal_category"] == "wrapper_error"
    assert timeout_row["failure_reason"] == "lm8f_timeout"
    assert timeout_row["child_run_dir_error"] == "child_run_dir_missing"
    assert timeout_row["lm8f_run_dir"] is None

    error_row = PROBE._subprocess_error_row(
        attempt_index=2,
        exc=OSError("launch failed"),
        child_run_dirs=[],
    )
    assert error_row["terminal_category"] == "wrapper_error"
    assert error_row["failure_reason"] == "lm8f_subprocess_error:OSError"
    assert error_row["child_run_dir_error"] == "child_run_dir_missing"
    assert error_row["lm8f_run_dir"] is None
