from __future__ import annotations

import importlib.util
import sys
import subprocess
import json
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8j_affine_support_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8j_affine_support_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_lm8j_shape():
    args = PROBE._args([])

    assert args.attempts == 20
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600
    assert (
        PROBE._canonical_evidence(
            attempts=args.attempts,
            model=args.model,
            attempt_timeout_s=args.attempt_timeout_s,
        )
        is True
    )


def test_cli_rejects_non_positive_attempts_and_timeout():
    for argv in (
        ["--attempts", "0"],
        ["--attempts", "-1"],
        ["--attempt-timeout-s", "0"],
        ["--attempt-timeout-s", "-2"],
    ):
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_canonical_evidence_only_for_twenty_default_gemma_default_timeout_attempts():
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=600,
        )
        is True
    )
    assert (
        PROBE._canonical_evidence(
            attempts=5,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=600,
        )
        is False
    )
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="qwen3:14b",
            attempt_timeout_s=600,
        )
        is False
    )
    assert (
        PROBE._canonical_evidence(
            attempts=20,
            model="gemma4:12b-it-qat",
            attempt_timeout_s=1,
        )
        is False
    )


def test_cli_rejects_non_lm8j_surfaces():
    forbidden = (
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
        ["--phase", "receipt_recon"],
        ["--support-disabled"],
        ["--support-forced"],
    )
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8j_identity():
    manifest = PROBE._manifest(
        attempts=20,
        model="gemma4:12b-it-qat",
        attempt_timeout_s=600,
    )

    assert manifest["schema"] == "rook.lm8j_affine_support_repeatability_probe:v1"
    assert manifest["attempts"] == 20
    assert manifest["model"] == "gemma4:12b-it-qat"
    assert manifest["attempt_timeout_s"] == 600
    assert manifest["canonical_evidence"] is True
    assert manifest["child_probe"] == "lm8i_affine_publication_shape_support_probe.py"
    assert manifest["child_probe_invocation"] == "subprocess"
    assert manifest["support_mode"] == "lm8i_default_support_enabled"


def test_scheduled_attempt_id_is_stable():
    assert PROBE._scheduled_attempt_id(1) == "attempt-001"
    assert PROBE._scheduled_attempt_id(20) == "attempt-020"


def test_base_attempt_row_has_lm8j_fields():
    row = PROBE._base_attempt_row(attempt_index=1)

    assert row["attempt_index"] == 1
    assert row["scheduled_attempt_id"] == "attempt-001"
    assert row["lm8i_invoked"] is False
    assert row["lm8i_returncode"] is None
    assert row["lm8i_run_dir"] is None
    assert row["terminal_category"] is None
    assert row["publication_support_attempted"] is False
    assert row["publication_support_count"] == 0
    assert row["support_eligible"] is None
    assert row["support_recovered"] is False
    assert row["leak_check_performed"] is False
    assert row["leak_marker_match_count"] == 0


def test_lm8i_command_uses_sys_executable_and_child_run_dir(tmp_path: Path):
    runs_dir = tmp_path / "lm8i_runs"

    command = PROBE._lm8i_command(
        model="gemma4:12b-it-qat",
        lm8i_runs_dir=runs_dir,
    )

    assert command == [
        sys.executable,
        str(PROBE._REPO_ROOT / "scripts" / "lm8i_affine_publication_shape_support_probe.py"),
        "--model",
        "gemma4:12b-it-qat",
        "--run-dir",
        str(runs_dir),
    ]
    assert "--retry-clean-observation" not in command
    assert "--gh-edit" not in command
    assert "--support-forced" not in command
    assert "--support-disabled" not in command


def test_discover_child_run_dirs_uses_filesystem_delta(tmp_path: Path):
    runs_dir = tmp_path / "lm8i_runs"
    runs_dir.mkdir()
    existing = runs_dir / "lm8i-existing"
    existing.mkdir()
    ignored_file = runs_dir / "lm8i-file"
    ignored_file.write_text("not a run dir", encoding="utf-8")
    before = {path for path in runs_dir.glob("lm8i-*") if path.is_dir()}

    child = runs_dir / "lm8i-new"
    child.mkdir()

    assert PROBE._discover_child_run_dirs(runs_dir, before) == [child]


def test_completed_text_and_excerpt_handle_bytes_none_and_length():
    assert PROBE._completed_text(None) == ""
    assert PROBE._completed_text(b"abc") == "abc"
    assert PROBE._completed_text("xyz") == "xyz"

    assert PROBE._excerpt(None) == ""
    assert PROBE._excerpt("") == ""
    assert PROBE._excerpt("abcdef", limit=4) == "abcd"
    assert PROBE._excerpt("abc", limit=4) == "abc"


def test_single_child_dir_error_classifies_missing_and_ambiguous(tmp_path: Path):
    assert PROBE._single_child_dir_error([]) == (None, "child_run_dir_missing")

    first = tmp_path / "lm8i-a"
    second = tmp_path / "lm8i-b"
    first.mkdir()
    second.mkdir()

    assert PROBE._single_child_dir_error([first, second]) == (
        None,
        "child_run_dir_ambiguous",
    )
    assert PROBE._single_child_dir_error([first]) == (first, None)


def test_timeout_and_subprocess_error_rows_preserve_child_dir_when_present(tmp_path: Path):
    child = tmp_path / "lm8i-child"
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
    assert timeout_row["failure_reason"] == "lm8i_timeout"
    assert timeout_row["child_run_dir_error"] is None
    assert timeout_row["lm8i_run_dir"] == str(child)
    assert timeout_row["stdout_excerpt"] == "stdout before timeout"
    assert timeout_row["stderr_excerpt"] == "stderr before timeout"

    error_row = PROBE._subprocess_error_row(
        attempt_index=2,
        exc=OSError("launch failed"),
        child_run_dirs=[child],
    )
    assert error_row["terminal_category"] == "wrapper_error"
    assert error_row["failure_reason"] == "lm8i_subprocess_error:OSError"
    assert error_row["child_run_dir_error"] is None
    assert error_row["lm8i_run_dir"] == str(child)


def _write_child_decision(child: Path, payload: dict) -> None:
    child.mkdir(parents=True, exist_ok=True)
    (child / "decision.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def test_read_decision_handles_missing_invalid_and_non_mapping(tmp_path: Path):
    missing, missing_error = PROBE._read_decision(tmp_path / "missing.json")
    assert missing is None
    assert missing_error == "lm8i_missing_decision_json"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{bad", encoding="utf-8")
    invalid, invalid_error = PROBE._read_decision(invalid_path)
    assert invalid is None
    assert invalid_error == "lm8i_invalid_decision_json"

    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    non_mapping, non_mapping_error = PROBE._read_decision(list_path)
    assert non_mapping is None
    assert non_mapping_error == "lm8i_decision_not_mapping"


def test_classify_decision_preserves_known_lm8i_categories():
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
        "lm8i_missing_decision",
    )
    assert PROBE._classify_decision({"decision": "strange"}) == (
        "wrapper_error",
        "lm8i_unknown_decision:strange",
    )


def test_row_from_completed_accepted_lm8i_child_copies_support_metadata(tmp_path: Path):
    child = tmp_path / "lm8i-child"
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
            "publication_support_attempted": True,
            "publication_support_count": 1,
            "support_eligible": True,
            "support_not_attempted_reason": None,
            "first_publication_status": "pass1_decision_invalid",
            "first_publication_failure_reason": "pass1_missing_action_id",
            "final_publication_status": "published",
            "final_publication_failure_reason": None,
            "final_worker_response_kind": "action_request",
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="run_dir=child decision=accepted",
        stderr="",
    )

    row = PROBE._row_from_completed_lm8i(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["lm8i_invoked"] is True
    assert row["lm8i_returncode"] == 0
    assert row["lm8i_run_dir"] == str(child)
    assert row["lm8i_decision"] == "accepted"
    assert row["lm8i_reason"] == "verify_scalar_output_succeeded"
    assert row["terminal_category"] == "accepted"
    assert row["failure_reason"] is None
    assert row["worker_publication_ran"] is True
    assert row["live_set_value_dispatched"] is True
    assert row["verify_scalar_output_ran"] is True
    assert row["scalar_runtime_ready"] is True
    assert row["observed_output_after"] == 7.5
    assert row["publication_support_attempted"] is True
    assert row["publication_support_count"] == 1
    assert row["support_eligible"] is True
    assert row["first_publication_failure_reason"] == "pass1_missing_action_id"
    assert row["final_publication_status"] == "published"
    assert row["final_worker_response_kind"] == "action_request"
    assert row["support_recovered"] is False


def test_row_from_completed_nonzero_returncode_is_wrapper_error(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    _write_child_decision(
        child,
        {
            "decision": "accepted",
            "reason": "verify_scalar_output_succeeded",
            "worker_publication_ran": True,
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="partial stdout",
        stderr="partial stderr",
    )

    row = PROBE._row_from_completed_lm8i(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8i_nonzero_returncode:2"
    assert row["child_run_dir_error"] is None
    assert row["lm8i_run_dir"] == str(child)
    assert row["lm8i_decision"] == "accepted"
    assert row["worker_publication_ran"] is True
    assert row["stdout_excerpt"] == "partial stdout"
    assert row["stderr_excerpt"] == "partial stderr"


def test_copy_child_artifact_summaries_reads_worker_verifier_and_support_recovery(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        json.dumps({"input": {"value": 3.0}}),
        encoding="utf-8",
    )
    (child / "verify_scalar_output_summary.json").write_text(
        json.dumps({"attempt_count": 2, "observed_output_value": 7.5}),
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "support_recovered": False,
        "worker_action_value": None,
        "verifier_attempt_count": None,
        "observed_output_after": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["worker_action_value"] == 3.0
    assert row["verifier_attempt_count"] == 2
    assert row["observed_output_after"] == 7.5
    assert row["support_recovered"] is True


def test_support_recovered_requires_worker_action_receipt(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "final_publication_status": "published",
        "final_worker_response_kind": "action_request",
        "support_recovered": False,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["support_recovered"] is False
