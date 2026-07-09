from __future__ import annotations

import inspect
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


def test_support_recovered_with_malformed_worker_action_file(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        "{not valid json}",
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "support_recovered": False,
        "worker_action_value": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["support_recovered"] is True
    assert row["worker_action_value"] is None


def test_scan_and_apply_leak_markers_are_report_only(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "notes.json").write_text(
        json.dumps(
            {
                "marker": "PROBE_REPAIR_CODE",
                "nested": {"value": "A = 42.0"},
            }
        ),
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "terminal_category": "accepted",
        "leak_check_performed": False,
        "leak_marker_matches": [],
        "leak_marker_match_count": 0,
    }

    matches = PROBE._scan_leak_markers(child)
    assert matches == [
        {"path": str(child / "notes.json"), "marker": "PROBE_REPAIR_CODE"},
        {"path": str(child / "notes.json"), "marker": "A = 42.0"},
    ]

    PROBE._apply_leak_scan(row)

    assert row["terminal_category"] == "accepted"
    assert row["leak_check_performed"] is True
    assert row["leak_marker_match_count"] == 2
    assert row["leak_marker_matches"] == matches


def test_compact_counts_removes_zero_entries_and_sorts_keys():
    from collections import Counter

    counts = Counter({"rejected": 2, "accepted": 1, "gate_failed": 0})

    assert PROBE._compact_counts(counts) == {"accepted": 1, "rejected": 2}


def test_build_summary_counts_support_and_worker_denominators():
    rows = [
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "publication_support_attempted": False,
            "support_eligible": False,
            "support_recovered": False,
            "lm8i_run_dir": "run-a",
            "leak_marker_match_count": 1,
            "worker_action_value": 3.0,
            "verifier_attempt_count": 1,
            "observed_output_after": 7.5,
        },
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "publication_support_attempted": True,
            "support_eligible": True,
            "support_recovered": True,
            "lm8i_run_dir": "run-b",
            "leak_marker_match_count": 0,
            "worker_action_value": 3.0,
            "verifier_attempt_count": 2,
            "observed_output_after": 7.5,
        },
        {
            "terminal_category": "publication_failed",
            "worker_publication_ran": True,
            "publication_support_attempted": True,
            "support_eligible": True,
            "support_recovered": False,
            "lm8i_run_dir": "run-c",
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "gate_failed",
            "worker_publication_ran": False,
            "publication_support_attempted": False,
            "support_eligible": None,
            "support_recovered": False,
            "gate_failure_reason": "affine_fixture_failed:gh_connect_failed",
            "lm8i_run_dir": "run-d",
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "preflight_failed",
            "worker_publication_ran": False,
            "publication_support_attempted": False,
            "support_eligible": None,
            "support_recovered": False,
            "preflight_failure_reason": "rhino_ping_failed",
            "lm8i_run_dir": "run-e",
            "leak_marker_match_count": 0,
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=20,
        model="gemma4:12b-it-qat",
        attempt_timeout_s=600,
    )

    assert summary["schema"] == "rook.lm8j_affine_support_repeatability_probe:v1"
    assert summary["scheduled_attempts"] == 20
    assert summary["attempt_timeout_s"] == 600
    assert summary["canonical_evidence"] is True
    assert summary["terminal_category_counts"] == {
        "accepted": 2,
        "gate_failed": 1,
        "preflight_failed": 1,
        "publication_failed": 1,
    }
    assert summary["accepted_count"] == 2
    assert summary["publication_failed_count"] == 1
    assert summary["gate_failed_count"] == 1
    assert summary["preflight_failed_count"] == 1
    assert summary["worker_reached_count"] == 3
    assert summary["worker_terminal_counts"] == {"accepted": 2, "publication_failed": 1}
    assert summary["publication_support_attempted_count"] == 2
    assert summary["publication_support_recovered_count"] == 1
    assert summary["accepted_without_support_count"] == 1
    assert summary["support_eligible_count"] == 2
    assert summary["support_accepted_count"] == 1
    assert summary["gate_failure_reasons"] == {"affine_fixture_failed:gh_connect_failed": 1}
    assert summary["preflight_failure_reasons"] == {"rhino_ping_failed": 1}
    assert summary["leak_marker_match_count"] == 1
    assert summary["attempt_run_dirs"] == ["run-a", "run-b", "run-c", "run-d", "run-e"]
    assert summary["worker_action_values"] == [3.0, 3.0]
    assert summary["verifier_attempt_counts"] == [1, 2]
    assert summary["observed_output_values_after"] == [7.5, 7.5]


def test_write_json_and_append_jsonl_are_stable_and_structured(tmp_path: Path):
    json_path = tmp_path / "artifact.json"
    jsonl_path = tmp_path / "artifact.jsonl"

    PROBE._write_json(json_path, {"b": 2, "a": 1})
    PROBE._append_jsonl(jsonl_path, {"b": 2, "a": 1})
    PROBE._append_jsonl(jsonl_path, {"c": 3})

    assert json_path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'
    assert jsonl_path.read_text(encoding="utf-8").splitlines() == [
        '{"a": 1, "b": 2}',
        '{"c": 3}',
    ]


class FakeLm8iRunner:
    def __init__(self, child_decisions: list[dict]):
        self.child_decisions = list(child_decisions)
        self.calls: list[dict] = []

    def __call__(self, command, *, cwd, capture_output, text, timeout):
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )
        run_dir = Path(command[command.index("--run-dir") + 1])
        decision = self.child_decisions.pop(0)
        child = run_dir / f"lm8i-child-{len(self.calls):03d}"
        child.mkdir(parents=True)
        (child / "decision.json").write_text(
            json.dumps(decision, sort_keys=True),
            encoding="utf-8",
        )
        if decision.get("worker_action_value") is not None:
            (child / "worker_action.json").write_text(
                json.dumps({"input": {"value": decision["worker_action_value"]}}),
                encoding="utf-8",
            )
        if decision.get("verifier_attempt_count") is not None:
            (child / "verify_scalar_output_summary.json").write_text(
                json.dumps(
                    {
                        "attempt_count": decision["verifier_attempt_count"],
                        "observed_output_value": decision.get("observed_output_after"),
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=f"run_dir={child}",
            stderr="",
        )


def test_run_probe_writes_manifest_attempts_and_summary(tmp_path: Path):
    runner = FakeLm8iRunner(
        [
            {
                "decision": "accepted",
                "reason": "verify_scalar_output_succeeded",
                "worker_publication_ran": True,
                "live_fixture_created": True,
                "live_set_value_dispatched": True,
                "verify_scalar_output_ran": True,
                "scalar_runtime_ready": True,
                "observed_output_after": 7.5,
                "publication_support_attempted": False,
                "publication_support_count": 0,
                "support_eligible": False,
                "worker_action_value": 3.0,
                "verifier_attempt_count": 1,
            },
            {
                "decision": "publication_failed",
                "reason": "pass1_decision_invalid:pass1_missing_action_id",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
            },
        ]
    )

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=runner,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert manifest["attempts"] == 2
    assert manifest["attempt_timeout_s"] == 600
    assert manifest["canonical_evidence"] is False
    assert [row["terminal_category"] for row in rows] == [
        "accepted",
        "publication_failed",
    ]
    assert rows[0]["worker_action_value"] == 3.0
    assert rows[0]["support_recovered"] is False
    assert rows[1]["publication_support_attempted"] is True
    assert rows[1]["support_recovered"] is False
    assert summary["accepted_count"] == 1
    assert summary["publication_failed_count"] == 1
    assert summary["attempt_timeout_s"] == 600
    assert summary["worker_reached_count"] == 2
    assert summary["publication_support_attempted_count"] == 1
    assert summary["publication_support_recovered_count"] == 0
    assert summary["accepted_without_support_count"] == 1
    assert summary["worker_action_values"] == [3.0]
    assert summary["verifier_attempt_counts"] == [1]
    assert summary["observed_output_values_after"] == [7.5]
    assert len(runner.calls) == 2
    assert all(call["timeout"] == 600 for call in runner.calls)
    assert all(call["capture_output"] is True for call in runner.calls)
    assert all(call["text"] is True for call in runner.calls)


def test_run_probe_continues_after_wrapper_error(tmp_path: Path):
    calls = []

    def fake_runner(command, *, cwd, capture_output, text, timeout):
        calls.append(command)
        run_dir = Path(command[command.index("--run-dir") + 1])
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")
        child = run_dir / "lm8i-child-002"
        child.mkdir(parents=True)
        (child / "decision.json").write_text(
            json.dumps({"decision": "accepted", "worker_publication_ran": True}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_runner,
    )
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert [row["terminal_category"] for row in rows] == ["wrapper_error", "accepted"]
    assert rows[0]["failure_reason"] == "child_run_dir_missing"
    assert len(calls) == 2


def test_run_probe_counts_support_recovery_only_when_worker_action_exists(tmp_path: Path):
    runner = FakeLm8iRunner(
        [
            {
                "decision": "accepted",
                "reason": "verify_scalar_output_succeeded",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
                "final_publication_status": "published",
                "final_worker_response_kind": "action_request",
                "worker_action_value": 3.0,
            },
            {
                "decision": "publication_failed",
                "reason": "worker_action_apply_failed:invalid_input",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
                "final_publication_status": "published",
                "final_worker_response_kind": "action_request",
            },
        ]
    )

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=runner,
    )
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert rows[0]["support_recovered"] is True
    assert rows[1]["support_recovered"] is False
    assert summary["publication_support_attempted_count"] == 2
    assert summary["publication_support_recovered_count"] == 1
    assert summary["support_accepted_count"] == 1


def test_main_prints_run_dir_and_returns_zero(monkeypatch, tmp_path: Path, capsys):
    def fake_run_probe(**kwargs):
        run_dir = tmp_path / "lm8j-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"accepted_count": 1, "scheduled_attempts": 1}),
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--attempts", "1", "--run-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "LM8J affine support repeatability probe complete" in output
    assert "run_dir=" in output


def test_lm8j_source_does_not_import_lm8i_or_live_tooling():
    source = inspect.getsource(PROBE)

    forbidden = (
        "import lm8i_affine_publication_shape_support_probe",
        "from lm8i_affine_publication_shape_support_probe",
        "_mcp_tool_executor",
        '"rhino_ping"',
        '"gh_document_new"',
        '"gh_set_value"',
        '"gh_inspect_output"',
        "run_two_pass_worker_publication",
        "apply_gh_scalar_value_action_to_node",
    )
    for fragment in forbidden:
        assert fragment not in source
