from __future__ import annotations

import importlib.util
import json
import subprocess
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
    assert args.lm6a_retry_clean_observation is False


def test_cli_retry_pass_through_default_off(monkeypatch, tmp_path: Path) -> None:
    seen_kwargs = {}

    def fake_run_probe(**kwargs):
        seen_kwargs.update(kwargs)
        run_dir = tmp_path / "lm6c-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            '{"terminal_category_counts": {"accepted": 1}}',
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--attempts", "1", "--run-dir", str(tmp_path)]) == 0
    assert seen_kwargs["lm6a_retry_clean_observation"] is False


def test_cli_retry_pass_through_flag(monkeypatch, tmp_path: Path) -> None:
    seen_kwargs = {}

    def fake_run_probe(**kwargs):
        seen_kwargs.update(kwargs)
        run_dir = tmp_path / "lm6c-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            '{"terminal_category_counts": {"accepted": 1}}',
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert (
        PROBE.main(
            [
                "--attempts",
                "1",
                "--run-dir",
                str(tmp_path),
                "--lm6a-retry-clean-observation",
            ]
        )
        == 0
    )
    assert seen_kwargs["lm6a_retry_clean_observation"] is True


def test_cli_rejects_non_positive_attempts() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--attempts", "0"])


def test_canonical_evidence_only_for_five_gemma_qat_attempts() -> None:
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=1, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=5, model="qwen3:14b") is False


def test_lm6a_command_adds_retry_flag_only_when_enabled(tmp_path: Path) -> None:
    base_command = PROBE._lm6a_command(
        model="gemma4:12b-it-qat",
        lm6a_runs_dir=tmp_path,
        retry_clean_observation=False,
    )
    retry_command = PROBE._lm6a_command(
        model="gemma4:12b-it-qat",
        lm6a_runs_dir=tmp_path,
        retry_clean_observation=True,
    )

    assert "--retry-clean-observation" not in base_command
    assert retry_command[-1] == "--retry-clean-observation"
    assert retry_command[:-1] == base_command


def test_manifest_records_retry_pass_through_flag() -> None:
    manifest = PROBE._manifest(
        attempts=5,
        model="gemma4:12b-it-qat",
        lm6a_retry_clean_observation=True,
    )

    assert manifest["lm6a_retry_clean_observation"] is True


def test_tool_result_ok_accepts_successful_mapping() -> None:
    assert PROBE._tool_result_ok("some_tool", {"ok": True}) is True
    assert PROBE._tool_result_ok("some_tool", {"status": "ready"}) is True


def test_tool_result_ok_accepts_real_preflight_success_shapes() -> None:
    assert PROBE._tool_result_ok("rhino_ping", "pong") is True
    assert PROBE._tool_result_ok("rhino_ping", {"success": True, "data": "pong"}) is True
    assert PROBE._tool_result_ok("gh_document_new", {"created": True}) is True


def test_tool_result_ok_rejects_failure_shapes() -> None:
    assert PROBE._tool_result_ok("some_tool", None) is False
    assert PROBE._tool_result_ok("some_tool", {"ok": False}) is False
    assert PROBE._tool_result_ok("some_tool", {"success": False}) is False
    assert PROBE._tool_result_ok("some_tool", {"status": "error"}) is False
    assert PROBE._tool_result_ok("some_tool", {"status": "failed"}) is False
    assert PROBE._tool_result_ok("some_tool", {"error": "bad"}) is False
    assert PROBE._tool_result_ok("some_tool", {"errors": ["bad"]}) is False
    assert PROBE._tool_result_ok("rhino_ping", "not-pong") is False
    assert PROBE._tool_result_ok("rhino_ping", {"success": True, "data": "not-pong"}) is False
    assert PROBE._tool_result_ok("gh_document_new", {"created": False}) is False


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


def test_attempt_row_for_nonzero_lm6a_returncode(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        '{"decision": "accepted", "reason": "verify_repair_succeeded"}',
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="some stdout",
        stderr="some stderr",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm6a_nonzero_returncode:2"
    assert row["lm6a_returncode"] == 2
    assert row["lm6a_invoked"] is True
    assert row["lm6a_run_dir"] == str(child)
    assert row["stdout_excerpt"] == "some stdout"
    assert row["stderr_excerpt"] == "some stderr"


def test_attempt_row_for_missing_decision_json(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="done",
        stderr="",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm6a_missing_decision_json"
    assert row["lm6a_decision"] is None
    assert row["lm6a_reason"] is None


def test_attempt_row_for_non_mapping_decision_json(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        '["accepted"]',
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="done",
        stderr="",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm6a_decision_not_mapping"
    assert row["lm6a_decision"] is None
    assert row["lm6a_reason"] is None


def test_attempt_row_for_successful_lm6a_decision(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        '{"decision": "accepted", "reason": "verify_repair_succeeded"}',
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="x" * 2100,
        stderr="y" * 2100,
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["preflight_status"] == "passed"
    assert row["lm6a_invoked"] is True
    assert row["lm6a_returncode"] == 0
    assert row["lm6a_run_dir"] == str(child)
    assert row["lm6a_decision"] == "accepted"
    assert row["lm6a_reason"] == "verify_repair_succeeded"
    assert row["terminal_category"] == "accepted"
    assert row["failure_reason"] is None
    assert len(row["stdout_excerpt"]) == 2000
    assert len(row["stderr_excerpt"]) == 2000


def test_attempt_row_copies_retry_metadata_from_lm6a_decision(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        json.dumps(
            {
                "decision": "worker_declined",
                "reason": "worker_refused_task",
                "retry_attempted": True,
                "retry_count": 1,
                "first_worker_response_kind": "invalid_json",
                "first_worker_decline_reason": "missing_action_request",
                "final_worker_response_kind": "decline",
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="done",
        stderr="",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "worker_declined"
    assert row["retry_attempted"] is True
    assert row["retry_count"] == 1
    assert row["first_worker_response_kind"] == "invalid_json"
    assert row["first_worker_decline_reason"] == "missing_action_request"
    assert row["final_worker_response_kind"] == "decline"


def test_leak_scan_reports_markers_without_changing_decision(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    nested = child / "nested"
    nested.mkdir(parents=True)
    (child / "decision.json").write_text(
        '{"decision": "accepted", "reason": "verify_repair_succeeded"}',
        encoding="utf-8",
    )
    (nested / "trace.json").write_text(
        '{"repair": "PROBE_REPAIR_CODE", "code": "A = 42.0"}',
        encoding="utf-8",
    )
    (nested / "notes.txt").write_text(
        "BindStepSpec.base_params.code",
        encoding="utf-8",
    )

    matches = PROBE._scan_leak_markers(child)

    assert len(matches) == 2
    assert {match["marker"] for match in matches} == {
        "PROBE_REPAIR_CODE",
        "A = 42.0",
    }
    assert all(match["path"].endswith(".json") for match in matches)
    assert json.loads((child / "decision.json").read_text(encoding="utf-8"))[
        "decision"
    ] == "accepted"
    assert PROBE._scan_leak_markers(tmp_path / "missing-run") == []


def test_apply_leak_scan_updates_row_report_only(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "worker.json").write_text(
        '{"bind": "BindStepSpec.base_params.code"}',
        encoding="utf-8",
    )
    row = PROBE._base_attempt_row(attempt_index=1)
    row["terminal_category"] = "accepted"
    row["lm6a_run_dir"] = str(child)

    PROBE._apply_leak_scan(row)

    assert row["terminal_category"] == "accepted"
    assert row["leak_check_performed"] is True
    assert row["leak_marker_match_count"] == 1
    assert row["leak_marker_matches"][0]["marker"] == "BindStepSpec.base_params.code"

    no_run_row = PROBE._base_attempt_row(attempt_index=2)
    PROBE._apply_leak_scan(no_run_row)
    assert no_run_row["leak_check_performed"] is False
    assert no_run_row["leak_marker_match_count"] == 0


def test_build_summary_separates_scheduled_and_worker_denominators() -> None:
    rows = [
        {
            **PROBE._base_attempt_row(attempt_index=1),
            "terminal_category": "accepted",
            "lm6a_invoked": True,
            "lm6a_run_dir": "run-a",
            "leak_marker_match_count": 0,
        },
        {
            **PROBE._base_attempt_row(attempt_index=2),
            "terminal_category": "gate_failed",
            "lm6a_invoked": True,
            "lm6a_run_dir": "run-b",
            "leak_marker_match_count": 1,
        },
        {
            **PROBE._base_attempt_row(attempt_index=3),
            "terminal_category": "preflight_failed",
            "lm6a_invoked": False,
            "leak_marker_match_count": 0,
        },
        {
            **PROBE._base_attempt_row(attempt_index=4),
            "terminal_category": "wrapper_error",
            "lm6a_invoked": True,
            "leak_marker_match_count": 0,
        },
        {
            **PROBE._base_attempt_row(attempt_index=5),
            "terminal_category": "worker_declined",
            "lm6a_invoked": True,
            "lm6a_run_dir": "run-e",
            "leak_marker_match_count": 0,
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=5,
        model="gemma4:12b-it-qat",
    )

    assert summary["scheduled_attempts"] == 5
    assert summary["terminal_category_counts"] == {
        "accepted": 1,
        "gate_failed": 1,
        "preflight_failed": 1,
        "worker_declined": 1,
        "wrapper_error": 1,
    }
    assert summary["preflight_failed_count"] == 1
    assert summary["lm6a_invoked_count"] == 4
    assert summary["gate_failed_count"] == 1
    assert summary["worker_reached_count"] == 2
    assert summary["worker_terminal_counts"] == {
        "accepted": 1,
        "worker_declined": 1,
    }
    assert summary["accepted_count"] == 1
    assert summary["leak_marker_match_count"] == 1
    assert summary["attempt_run_dirs"] == ["run-a", "run-b", "run-e"]
    assert summary["canonical_evidence"] is True


def test_build_summary_adds_retry_report_counts() -> None:
    rows = [
        {
            **PROBE._base_attempt_row(attempt_index=1),
            "terminal_category": "accepted",
            "retry_attempted": True,
            "final_worker_response_kind": "action_request",
        },
        {
            **PROBE._base_attempt_row(attempt_index=2),
            "terminal_category": "rejected",
            "retry_attempted": True,
            "final_worker_response_kind": "action_request",
        },
        {
            **PROBE._base_attempt_row(attempt_index=3),
            "terminal_category": "publication_failed",
            "retry_attempted": True,
            "final_worker_response_kind": "action_request",
        },
        {
            **PROBE._base_attempt_row(attempt_index=4),
            "terminal_category": "worker_declined",
            "retry_attempted": True,
            "final_worker_response_kind": "decline",
        },
        {
            **PROBE._base_attempt_row(attempt_index=5),
            "terminal_category": "accepted",
            "retry_attempted": False,
            "final_worker_response_kind": "action_request",
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=5,
        model="gemma4:12b-it-qat",
    )

    assert summary["retry_attempted_count"] == 4
    assert summary["retry_recovered_count"] == 2
    assert summary["retry_declined_count"] == 1
    assert summary["retry_publication_failed_count"] == 1
    assert summary["terminal_category_counts"] == {
        "accepted": 2,
        "publication_failed": 1,
        "rejected": 1,
        "worker_declined": 1,
    }
    assert summary["worker_reached_count"] == 5


def test_run_probe_records_preflight_failure_without_lm6a(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def fake_preflight():
        return False, "rhino_ping_failed"

    monkeypatch.setattr(PROBE, "_run_preflight", fake_preflight)

    run_dir = PROBE._run_probe(
        attempts=1,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("LM6A should not be invoked")
        ),
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["terminal_category"] == "preflight_failed"
    assert rows[0]["lm6a_invoked"] is False
    assert (run_dir / "lm6a_runs" / "attempt-001").is_dir()
    assert summary["preflight_failed_count"] == 1
    assert summary["lm6a_invoked_count"] == 0


def test_run_probe_invokes_lm6a_after_preflight(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def fake_preflight():
        return True, None

    def fake_run_subprocess(command, **kwargs):
        lm6a_runs_dir = Path(command[-1])
        assert lm6a_runs_dir.name == "attempt-001"
        assert lm6a_runs_dir.parent.name == "lm6a_runs"
        child = lm6a_runs_dir / "lm6a-child"
        child.mkdir(parents=True)
        (child / "decision.json").write_text(
            '{"decision": "accepted", "reason": "verify_repair_succeeded"}',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="LM6A complete",
            stderr="",
        )

    monkeypatch.setattr(PROBE, "_run_preflight", fake_preflight)

    run_dir = PROBE._run_probe(
        attempts=1,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_run_subprocess,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["terminal_category"] == "accepted"
    assert rows[0]["lm6a_invoked"] is True
    assert Path(rows[0]["lm6a_run_dir"]).parent.name == "attempt-001"
    assert summary["accepted_count"] == 1
    assert summary["worker_reached_count"] == 1


def test_run_probe_timeout_discovers_child_run_and_scans_leaks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def fake_preflight():
        return True, None

    def fake_run_subprocess(command, **kwargs):
        lm6a_runs_dir = Path(command[-1])
        assert lm6a_runs_dir.name == "attempt-001"
        assert lm6a_runs_dir.parent.name == "lm6a_runs"
        child = lm6a_runs_dir / "lm6a-child"
        child.mkdir(parents=True)
        (child / "worker_action.json").write_text(
            '{"code": "A = 42.0;"}',
            encoding="utf-8",
        )
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout"],
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(PROBE, "_run_preflight", fake_preflight)

    run_dir = PROBE._run_probe(
        attempts=1,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_run_subprocess,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["terminal_category"] == "wrapper_error"
    assert rows[0]["failure_reason"] == "lm6a_timeout"
    assert rows[0]["lm6a_run_dir"].endswith("lm6a-child")
    assert Path(rows[0]["lm6a_run_dir"]).parent.name == "attempt-001"
    assert rows[0]["leak_check_performed"] is True
    assert rows[0]["leak_marker_match_count"] == 1
    assert summary["terminal_category_counts"] == {"wrapper_error": 1}
    assert summary["leak_marker_match_count"] == 1


def test_run_probe_subprocess_error_discovers_child_run_and_continues(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def fake_preflight():
        return True, None

    def fake_run_subprocess(command, **kwargs):
        lm6a_runs_dir = Path(command[-1])
        assert lm6a_runs_dir.name == "attempt-001"
        child = lm6a_runs_dir / "lm6a-child"
        child.mkdir(parents=True)
        (child / "worker_action.json").write_text(
            '{"code": "PROBE_REPAIR_CODE"}',
            encoding="utf-8",
        )
        raise RuntimeError("boom")

    monkeypatch.setattr(PROBE, "_run_preflight", fake_preflight)

    run_dir = PROBE._run_probe(
        attempts=1,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_run_subprocess,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["terminal_category"] == "wrapper_error"
    assert rows[0]["failure_reason"] == "lm6a_subprocess_error:RuntimeError"
    assert rows[0]["lm6a_run_dir"].endswith("lm6a-child")
    assert rows[0]["leak_check_performed"] is True
    assert rows[0]["leak_marker_match_count"] == 1
    assert summary["terminal_category_counts"] == {"wrapper_error": 1}
    assert summary["leak_marker_match_count"] == 1


def test_main_prints_run_dir(monkeypatch, tmp_path: Path, capsys) -> None:
    def fake_run_probe(**kwargs):
        run_dir = tmp_path / "lm6c-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            '{"terminal_category_counts": {"accepted": 1}}',
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--attempts", "1", "--run-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "LM6C repeatability probe complete" in output
    assert f"run_dir={tmp_path / 'lm6c-demo'}" in output


def test_lm6c_script_does_not_import_lm6a_internals() -> None:
    source = PROBE._script_path().read_text(encoding="utf-8")

    assert "--retry-clean-observation" in source
    assert "import lm6a_live_worker_splice_probe" not in source
    assert "from lm6a_live_worker_splice_probe" not in source
    assert "run_two_pass_worker_publication" not in source
    assert "apply_worker_action_to_node" not in source
    assert "_run_probe(" in source
    assert "subprocess.run" in source
