from __future__ import annotations

import importlib.util
import sys
import subprocess
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
