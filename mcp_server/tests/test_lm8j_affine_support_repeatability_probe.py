from __future__ import annotations

import importlib.util
import sys
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
