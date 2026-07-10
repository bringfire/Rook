#!/usr/bin/env python
"""LM8J repeatability wrapper for LM8I affine support-enabled live probe."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT_SCHEMA = "rook.lm8j_affine_support_repeatability_probe:v1"
LM8M_SCRIPT_SCHEMA = "rook.lm8m_affine_managed_receipt_repeatability_probe:v1"
DEFAULT_ATTEMPTS = 20
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_RUN_DIR = "probe_runs"
DEFAULT_ATTEMPT_TIMEOUT_S = 600
SETTLE_VERIFIER_PROFILE = "settle_v1"
MANAGED_VERIFIER_PROFILE = "managed_receipt_v2"
VERIFIER_PROFILES = (SETTLE_VERIFIER_PROFILE, MANAGED_VERIFIER_PROFILE)
READINESS_WAIT_TIMEOUT_MS = 10_000
VERIFIER_MECHANISM = "managed_solve_readiness_receipt"
FIXTURE_READINESS_PROFILE = "lm8i_legacy_setup_v1"
LM8I_DECISION_SCHEMA = "rook.lm8i_affine_publication_shape_support_decision:v1"
GH_READINESS_RECEIPT_SCHEMA = "rook.gh_solve_readiness_receipt:v1"
MANAGED_MUTATION_SCHEMA = "rook.lm8l_managed_mutation_summary:v1"
MANAGED_WAIT_SCHEMA = "rook.lm8l_readiness_wait_summary:v1"
MANAGED_VERIFY_SCHEMA = "rook.lm8l_fenced_output_verification_summary:v1"
MANAGED_DECISION_SCHEMA = "rook.lm8l_managed_verifier_decision:v1"
READINESS_FAILURE_REASONS = {
    "readiness_receipt_missing",
    "readiness_receipt_malformed",
    "readiness_receipt_superseded",
    "readiness_receipt_stale_solution_run",
    "readiness_receipt_document_replaced",
    "readiness_receipt_solver_locked",
    "readiness_receipt_unknown",
    "readiness_receipt_expired",
    "readiness_receipt_not_found_or_evicted_or_process_restarted",
    "readiness_receipt_not_ready",
    "readiness_wait_already_active",
}
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
EXCERPT_CHARS = 2000
LEAK_MARKERS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "BindStepSpec.base_params",
    "repair_same_component.bind.base_params",
)
LEAK_SCAN_EXTENSIONS = (".json", ".jsonl", ".txt", ".md", ".log")
TERMINAL_CATEGORIES = (
    "accepted",
    "rejected",
    "worker_declined",
    "publication_failed",
    "gate_failed",
    "preflight_failed",
    "wrapper_error",
)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM8J affine support repeatability probe."
    )
    parser.add_argument("--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--run-dir", default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--attempt-timeout-s",
        type=_positive_int,
        default=DEFAULT_ATTEMPT_TIMEOUT_S,
    )
    parser.add_argument(
        "--verifier-profile",
        choices=VERIFIER_PROFILES,
        default=SETTLE_VERIFIER_PROFILE,
    )

    forbidden = {
        "--retry-clean-observation",
        "--planner-provider-command",
        "--prompt-profile",
        "--request-json",
        "--gh-edit",
        "--phase",
        "--support-disabled",
        "--support-forced",
    }
    if argv:
        for token in argv:
            if token in forbidden:
                parser.error(f"unsupported_lm8j_argument:{token}")
    return parser.parse_args(argv)


def _run_identity(verifier_profile: str) -> tuple[str, str]:
    if verifier_profile == SETTLE_VERIFIER_PROFILE:
        return "lm8j", SCRIPT_SCHEMA
    if verifier_profile == MANAGED_VERIFIER_PROFILE:
        return "lm8m", LM8M_SCRIPT_SCHEMA
    raise ValueError(f"unsupported_verifier_profile:{verifier_profile}")


def _canonical_evidence(
    *,
    attempts: int,
    model: str,
    attempt_timeout_s: int,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
) -> bool:
    if verifier_profile not in VERIFIER_PROFILES:
        return False
    return (
        attempts == DEFAULT_ATTEMPTS
        and model == DEFAULT_MODEL
        and attempt_timeout_s == DEFAULT_ATTEMPT_TIMEOUT_S
        and (
            verifier_profile != MANAGED_VERIFIER_PROFILE
            or READINESS_WAIT_TIMEOUT_MS == 10_000
        )
    )


def _git_short_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _new_run_dir(
    run_root: str | Path,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_prefix, _ = _run_identity(verifier_profile)
    base = Path(run_root) / f"{run_prefix}-{timestamp}-{_git_short_sha()}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}-{suffix:02d}")
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _manifest(
    *,
    attempts: int,
    model: str,
    attempt_timeout_s: int,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
) -> dict[str, Any]:
    _, schema = _run_identity(verifier_profile)
    manifest = {
        "schema": schema,
        "git_commit": _git_short_sha(),
        "attempts": attempts,
        "model": model,
        "attempt_timeout_s": attempt_timeout_s,
        "canonical_evidence": _canonical_evidence(
            attempts=attempts,
            model=model,
            attempt_timeout_s=attempt_timeout_s,
            verifier_profile=verifier_profile,
        ),
        "child_probe": "lm8i_affine_publication_shape_support_probe.py",
        "child_probe_invocation": "subprocess",
        "support_mode": "lm8i_default_support_enabled",
        "replacement_attempts": False,
    }
    if verifier_profile == MANAGED_VERIFIER_PROFILE:
        manifest.update(
            {
                "verifier_profile": MANAGED_VERIFIER_PROFILE,
                "verifier_mechanism": VERIFIER_MECHANISM,
                "fixture_readiness_profile": FIXTURE_READINESS_PROFILE,
                "readiness_wait_timeout_ms": READINESS_WAIT_TIMEOUT_MS,
            }
        )
    return manifest


def _scheduled_attempt_id(attempt_index: int) -> str:
    return f"attempt-{attempt_index:03d}"


def _base_attempt_row(*, attempt_index: int) -> dict[str, Any]:
    return {
        "attempt_index": attempt_index,
        "scheduled_attempt_id": _scheduled_attempt_id(attempt_index),
        "lm8i_invoked": False,
        "lm8i_returncode": None,
        "lm8i_run_dir": None,
        "lm8i_decision": None,
        "lm8i_reason": None,
        "terminal_category": None,
        "failure_reason": None,
        "child_run_dir_error": None,
        "stdout_excerpt": "",
        "stderr_excerpt": "",
        "worker_publication_ran": False,
        "live_fixture_created": False,
        "live_set_value_dispatched": False,
        "verify_scalar_output_ran": False,
        "scalar_runtime_ready": None,
        "publication_support_attempted": False,
        "publication_support_count": 0,
        "support_eligible": None,
        "support_not_attempted_reason": None,
        "first_publication_status": None,
        "first_publication_failure_reason": None,
        "final_publication_status": None,
        "final_publication_failure_reason": None,
        "final_worker_response_kind": None,
        "support_recovered": False,
        "worker_action_value": None,
        "verifier_attempt_count": None,
        "observed_output_after": None,
        "gate_failure_reason": None,
        "preflight_failure_reason": None,
        "leak_check_performed": False,
        "leak_marker_matches": [],
        "leak_marker_match_count": 0,
    }


def _managed_attempt_fields(*, child_attempt_timeout_s: int) -> dict[str, Any]:
    return {
        "verifier_profile": MANAGED_VERIFIER_PROFILE,
        "verifier_mechanism": VERIFIER_MECHANISM,
        "fixture_readiness_profile": FIXTURE_READINESS_PROFILE,
        "readiness_wait_timeout_ms": READINESS_WAIT_TIMEOUT_MS,
        "child_attempt_timeout_s": child_attempt_timeout_s,
        "readiness_wait_count": 0,
        "readiness_wait_status": None,
        "readiness_failure_reason": None,
        "fenced_output_read_count": 0,
        "settle_read_count": 0,
        "readiness_fenced": None,
        "managed_verifier_audit_performed": False,
        "managed_verifier_audit_valid": None,
        "managed_verifier_audit_failures": [],
        "receipt_id_hashes_match": None,
        "document_session_ids_match": None,
        "mutation_epochs_match": None,
        "solution_run_epochs_match": None,
        "post_mutation_solution_run_advanced": None,
    }


def _lm8i_command(
    *,
    model: str,
    lm8i_runs_dir: Path,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
) -> list[str]:
    _run_identity(verifier_profile)
    command = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "lm8i_affine_publication_shape_support_probe.py"),
        "--model",
        model,
        "--run-dir",
        str(lm8i_runs_dir),
    ]
    if verifier_profile == MANAGED_VERIFIER_PROFILE:
        command.extend(["--verifier-profile", MANAGED_VERIFIER_PROFILE])
    return command


def _discover_child_run_dirs(
    lm8i_runs_dir: Path, before: set[Path]
) -> list[Path]:
    after = {path for path in lm8i_runs_dir.glob("lm8i-*") if path.is_dir()}
    created = sorted(after - before, key=lambda path: path.stat().st_mtime)
    return created


def _completed_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _excerpt(text: str | None, *, limit: int = EXCERPT_CHARS) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit]


def _single_child_dir_error(
    child_run_dirs: Sequence[Path],
) -> tuple[Path | None, str | None]:
    if len(child_run_dirs) == 0:
        return None, "child_run_dir_missing"
    if len(child_run_dirs) > 1:
        return None, "child_run_dir_ambiguous"
    return child_run_dirs[0], None


def _timeout_row(
    *,
    attempt_index: int,
    exc: subprocess.TimeoutExpired,
    child_run_dirs: Sequence[Path],
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    child_run_dir, child_error = _single_child_dir_error(child_run_dirs)
    row.update(
        {
            "lm8i_invoked": True,
            "lm8i_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "terminal_category": "wrapper_error",
            "failure_reason": "lm8i_timeout",
            "child_run_dir_error": child_error,
            "stdout_excerpt": _excerpt(_completed_text(getattr(exc, "output", None))),
            "stderr_excerpt": _excerpt(_completed_text(getattr(exc, "stderr", None))),
        }
    )
    return row


def _subprocess_error_row(
    *,
    attempt_index: int,
    exc: Exception,
    child_run_dirs: Sequence[Path],
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    child_run_dir, child_error = _single_child_dir_error(child_run_dirs)
    row.update(
        {
            "lm8i_invoked": True,
            "lm8i_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "terminal_category": "wrapper_error",
            "failure_reason": f"lm8i_subprocess_error:{exc.__class__.__name__}",
            "child_run_dir_error": child_error,
        }
    )
    return row


def _read_json_mapping(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _is_int_not_bool(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number_not_bool(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_number(value: Any) -> float | None:
    if not _is_number_not_bool(value):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _managed_artifact(
    path: Path,
) -> tuple[Mapping[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"{path.stem}_missing"
    value = _read_json_mapping(path)
    if value is None:
        return None, f"{path.stem}_malformed"
    return value, None


def _empty_managed_audit() -> dict[str, Any]:
    return {
        "performed": False,
        "valid": None,
        "failures": [],
        "readiness_wait_count": 0,
        "readiness_wait_status": None,
        "readiness_failure_reason": None,
        "fenced_output_read_count": 0,
        "settle_read_count": 0,
        "readiness_fenced": None,
        "observed_output_value": None,
        "receipt_id_hashes_match": None,
        "document_session_ids_match": None,
        "mutation_epochs_match": None,
        "solution_run_epochs_match": None,
        "post_mutation_solution_run_advanced": None,
    }


def _audit_managed_child(run_dir: Path) -> dict[str, Any]:
    result = _empty_managed_audit()
    stage_artifact_paths = (
        run_dir / "live_set_value_summary.json",
        run_dir / "readiness_wait_summary.json",
        run_dir / "verify_scalar_output_summary.json",
    )
    stage_artifacts_present = any(path.exists() for path in stage_artifact_paths)
    decision, decision_artifact_error = _managed_artifact(run_dir / "decision.json")
    if (
        decision is not None
        and decision.get("decision") != "accepted"
        and decision.get("live_set_value_dispatched") is False
        and not stage_artifacts_present
    ):
        return result

    result["performed"] = True
    failures: list[str] = []

    def fail(reason: str) -> None:
        if reason not in failures:
            failures.append(reason)

    mutation_artifact, mutation_artifact_error = _managed_artifact(
        run_dir / "live_set_value_summary.json"
    )
    wait, wait_artifact_error = _managed_artifact(
        run_dir / "readiness_wait_summary.json"
    )
    read, read_artifact_error = _managed_artifact(
        run_dir / "verify_scalar_output_summary.json"
    )
    for artifact_error, missing_reason, malformed_reason in (
        (
            mutation_artifact_error,
            "mutation_artifact_missing",
            "mutation_artifact_malformed",
        ),
        (wait_artifact_error, "wait_artifact_missing", "wait_artifact_malformed"),
        (read_artifact_error, "read_artifact_missing", "read_artifact_malformed"),
        (
            decision_artifact_error,
            "decision_artifact_missing",
            "decision_artifact_malformed",
        ),
    ):
        if artifact_error is not None:
            fail(
                missing_reason
                if artifact_error.endswith("_missing")
                else malformed_reason
            )

    mutation: Mapping[str, Any] | None = None
    if mutation_artifact is not None:
        candidate = mutation_artifact.get("managed_mutation")
        if isinstance(candidate, Mapping):
            mutation = candidate
        else:
            fail("mutation_summary_missing")

    if mutation is not None:
        if mutation.get("schema") != MANAGED_MUTATION_SCHEMA:
            fail("mutation_schema_invalid")
        if mutation.get("receipt_schema") != GH_READINESS_RECEIPT_SCHEMA:
            fail("mutation_receipt_schema_invalid")
        if mutation.get("receipt_status") != "pending":
            fail("mutation_receipt_status_not_pending")
        mutation_epoch = mutation.get("mutation_epoch")
        if not _is_int_not_bool(mutation_epoch) or mutation_epoch <= 0:
            fail("mutation_epoch_not_positive")
        if mutation.get("solution_run_epoch") is not None:
            fail("pending_solution_run_epoch_not_null")
        prior_completed = mutation.get("completed_solution_run_epoch")
        if not _is_int_not_bool(prior_completed) or prior_completed < 0:
            fail("pending_completed_solution_run_epoch_invalid")

    wait_count_value: Any = None
    wait_status: Any = None
    if wait is not None:
        if wait.get("schema") != MANAGED_WAIT_SCHEMA:
            fail("wait_schema_invalid")
        if wait.get("receipt_schema") != GH_READINESS_RECEIPT_SCHEMA:
            fail("wait_receipt_schema_invalid")
        if (
            not _is_int_not_bool(wait.get("requested_timeout_ms"))
            or wait.get("requested_timeout_ms") != READINESS_WAIT_TIMEOUT_MS
        ):
            fail("readiness_wait_timeout_ms_invalid")
        wait_count_value = wait.get("readiness_wait_count")
        if not _is_int_not_bool(wait_count_value) or wait_count_value != 1:
            fail("readiness_wait_count_not_one")
        wait_status = wait.get("wait_status")
        if wait_status != "ready":
            fail("wait_status_not_ready")
        if wait.get("receipt_status") != "ready":
            fail("wait_receipt_status_not_ready")
        ready_run = wait.get("solution_run_epoch")
        if not _is_int_not_bool(ready_run) or ready_run < 0:
            fail("ready_solution_run_epoch_invalid")
        wait_completed = wait.get("completed_solution_run_epoch")
        if (
            not _is_int_not_bool(wait_completed)
            or not _is_int_not_bool(ready_run)
            or wait_completed != ready_run
        ):
            fail("wait_completed_solution_run_mismatch")

        result["readiness_wait_count"] = (
            wait_count_value
            if _is_int_not_bool(wait_count_value) and wait_count_value >= 0
            else 0
        )
        result["readiness_wait_status"] = (
            wait_status if isinstance(wait_status, str) else None
        )

    read_wait_count_value: Any = None
    fenced_read_count_value: Any = None
    settle_read_count_value: Any = None
    if read is not None:
        if read.get("schema") != MANAGED_VERIFY_SCHEMA:
            fail("read_schema_invalid")
        if read.get("verifier_profile") != MANAGED_VERIFIER_PROFILE:
            fail("read_verifier_profile_invalid")
        if (
            not _is_int_not_bool(read.get("readiness_wait_timeout_ms"))
            or read.get("readiness_wait_timeout_ms") != READINESS_WAIT_TIMEOUT_MS
        ):
            fail("readiness_wait_timeout_ms_invalid")
        read_wait_count_value = read.get("readiness_wait_count")
        if not _is_int_not_bool(read_wait_count_value) or read_wait_count_value != 1:
            fail("readiness_wait_count_mismatch")
        if wait is not None and read_wait_count_value != wait_count_value:
            fail("readiness_wait_count_mismatch")
        fenced_read_count_value = read.get("fenced_output_read_count")
        if (
            not _is_int_not_bool(fenced_read_count_value)
            or fenced_read_count_value != 1
        ):
            fail("fenced_output_read_count_not_one")
        settle_read_count_value = read.get("settle_read_count")
        if (
            not _is_int_not_bool(settle_read_count_value)
            or settle_read_count_value != 0
        ):
            fail("settle_read_count_not_zero")
        if read.get("readiness_fenced") is not True:
            fail("readiness_fenced_not_true")
        expected_output = read.get("expected_output_value")
        expected_output_number = _finite_number(expected_output)
        if (
            expected_output_number is None
            or not math.isclose(
                expected_output_number,
                EXPECTED_OUTPUT_VALUE,
                rel_tol=0.0,
                abs_tol=0.0,
            )
        ):
            fail("expected_output_value_mismatch")
        observed_output = read.get("observed_output_value")
        observed_output_number = _finite_number(observed_output)
        if (
            observed_output_number is None
            or not math.isclose(
                observed_output_number,
                EXPECTED_OUTPUT_VALUE,
                rel_tol=0.0,
                abs_tol=SCALAR_TOLERANCE,
            )
        ):
            fail("observed_output_value_mismatch")
        tolerance = read.get("tolerance")
        tolerance_number = _finite_number(tolerance)
        if (
            tolerance_number is None or tolerance_number != SCALAR_TOLERANCE
        ):
            fail("scalar_tolerance_invalid")

        result["fenced_output_read_count"] = (
            fenced_read_count_value
            if _is_int_not_bool(fenced_read_count_value)
            and fenced_read_count_value >= 0
            else 0
        )
        result["settle_read_count"] = (
            settle_read_count_value
            if _is_int_not_bool(settle_read_count_value)
            and settle_read_count_value >= 0
            else 0
        )
        result["readiness_fenced"] = (
            read.get("readiness_fenced")
            if isinstance(read.get("readiness_fenced"), bool)
            else None
        )
        result["observed_output_value"] = (
            observed_output
            if observed_output_number is not None
            else None
        )

    if wait is not None:
        normalized_reason = wait.get("normalized_reason")
        if isinstance(normalized_reason, str) and normalized_reason:
            result["readiness_failure_reason"] = normalized_reason
        elif wait_status != "ready" and decision is not None:
            decision_reason = decision.get("reason")
            if isinstance(decision_reason, str) and decision_reason:
                result["readiness_failure_reason"] = decision_reason
    elif (
        decision is not None
        and decision.get("phase") == "verifier_readiness"
        and decision.get("live_set_value_dispatched") is True
    ):
        decision_reason = decision.get("reason")
        if decision_reason in READINESS_FAILURE_REASONS:
            result["readiness_failure_reason"] = decision_reason

    if mutation is not None and wait is not None and read is not None:
        receipt_hashes = [
            mutation.get("receipt_id_sha256"),
            wait.get("receipt_id_sha256"),
            read.get("receipt_id_sha256"),
        ]
        receipt_hashes_valid = all(
            isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
            for value in receipt_hashes
        )
        if not receipt_hashes_valid:
            fail("receipt_id_sha256_invalid")
        result["receipt_id_hashes_match"] = receipt_hashes_valid and len(
            set(receipt_hashes)
        ) == 1
        if receipt_hashes_valid and not result["receipt_id_hashes_match"]:
            fail("receipt_id_sha256_mismatch")

        session_ids = [
            mutation.get("document_session_id"),
            wait.get("document_session_id"),
            read.get("document_session_id"),
        ]
        session_ids_valid = all(
            isinstance(value, str) and bool(value) for value in session_ids
        )
        if not session_ids_valid:
            fail("document_session_id_invalid")
        result["document_session_ids_match"] = session_ids_valid and len(
            set(session_ids)
        ) == 1
        if session_ids_valid and not result["document_session_ids_match"]:
            fail("document_session_id_mismatch")

        mutation_epochs = [
            mutation.get("mutation_epoch"),
            wait.get("mutation_epoch"),
            read.get("mutation_epoch"),
        ]
        mutation_epochs_valid = all(
            _is_int_not_bool(value) and value > 0 for value in mutation_epochs
        )
        if not mutation_epochs_valid and (
            _is_int_not_bool(mutation_epochs[0]) and mutation_epochs[0] > 0
        ):
            fail("mutation_epoch_invalid")
        result["mutation_epochs_match"] = mutation_epochs_valid and len(
            set(mutation_epochs)
        ) == 1
        if mutation_epochs_valid and not result["mutation_epochs_match"]:
            fail("mutation_epoch_mismatch")

    if mutation is not None and wait is not None:
        prior_completed = mutation.get("completed_solution_run_epoch")
        ready_run = wait.get("solution_run_epoch")
        run_values_valid = (
            _is_int_not_bool(prior_completed)
            and prior_completed >= 0
            and _is_int_not_bool(ready_run)
            and ready_run >= 0
        )
        result["post_mutation_solution_run_advanced"] = (
            run_values_valid and ready_run > prior_completed
        )
        if run_values_valid and not result["post_mutation_solution_run_advanced"]:
            fail("post_mutation_solution_run_not_advanced")

    if wait is not None and read is not None:
        ready_run = wait.get("solution_run_epoch")
        wait_completed = wait.get("completed_solution_run_epoch")
        read_run = read.get("solution_run_epoch")
        read_completed = read.get("completed_solution_run_epoch")
        solution_runs_valid = all(
            _is_int_not_bool(value) and value >= 0
            for value in (ready_run, wait_completed, read_run, read_completed)
        )
        result["solution_run_epochs_match"] = solution_runs_valid and len(
            {ready_run, wait_completed, read_run, read_completed}
        ) == 1
        if not _is_int_not_bool(read_run) or read_run != ready_run:
            fail("read_solution_run_mismatch")
        if not _is_int_not_bool(read_completed) or read_completed != ready_run:
            fail("read_completed_solution_run_mismatch")

    accepted_child = decision is not None and decision.get("decision") == "accepted"
    managed_decision: Mapping[str, Any] | None = None
    if decision is not None:
        if decision.get("schema") != LM8I_DECISION_SCHEMA:
            fail("decision_schema_invalid")
        if not accepted_child:
            fail("child_decision_not_accepted")
        else:
            if decision.get("reason") != "verify_scalar_output_succeeded":
                fail("decision_reason_invalid")
            if decision.get("phase") != "verify_scalar_output":
                fail("decision_phase_invalid")
            if decision.get("live_set_value_dispatched") is not True:
                fail("live_set_value_dispatched_not_true")
            if decision.get("worker_publication_ran") is not True:
                fail("worker_publication_ran_not_true")
        candidate = decision.get("managed_verifier")
        if isinstance(candidate, Mapping):
            managed_decision = candidate
        else:
            fail("managed_decision_missing")

    if managed_decision is not None:
        if managed_decision.get("schema") != MANAGED_DECISION_SCHEMA:
            fail("managed_decision_schema_invalid")
        if managed_decision.get("verifier_profile") != MANAGED_VERIFIER_PROFILE:
            fail("managed_decision_profile_invalid")
        if managed_decision.get("verifier_mechanism") != VERIFIER_MECHANISM:
            fail("managed_decision_mechanism_invalid")
        if (
            managed_decision.get("fixture_readiness_profile")
            != FIXTURE_READINESS_PROFILE
        ):
            fail("managed_decision_fixture_profile_invalid")

        decision_timeout = managed_decision.get("readiness_wait_timeout_ms")
        timeout_values = [decision_timeout]
        if wait is not None:
            timeout_values.append(wait.get("requested_timeout_ms"))
        if read is not None:
            timeout_values.append(read.get("readiness_wait_timeout_ms"))
        if (
            not all(_is_int_not_bool(value) for value in timeout_values)
            or len(set(timeout_values)) != 1
            or decision_timeout != READINESS_WAIT_TIMEOUT_MS
        ):
            fail("managed_decision_timeout_mismatch")

        decision_wait_count = managed_decision.get("readiness_wait_count")
        wait_count_values = [decision_wait_count]
        if wait is not None:
            wait_count_values.append(wait_count_value)
        if read is not None:
            wait_count_values.append(read_wait_count_value)
        if (
            not all(_is_int_not_bool(value) for value in wait_count_values)
            or len(set(wait_count_values)) != 1
        ):
            fail("managed_decision_readiness_wait_count_mismatch")

        decision_fenced_count = managed_decision.get("fenced_output_read_count")
        if read is not None and (
            not _is_int_not_bool(decision_fenced_count)
            or decision_fenced_count != fenced_read_count_value
        ):
            fail("managed_decision_fenced_output_read_count_mismatch")
        decision_settle_count = managed_decision.get("settle_read_count")
        if read is not None and (
            not _is_int_not_bool(decision_settle_count)
            or decision_settle_count != settle_read_count_value
        ):
            fail("managed_decision_settle_read_count_mismatch")

        failed_invariants = managed_decision.get("failed_invariants")
        if accepted_child and (
            not isinstance(failed_invariants, list) or failed_invariants
        ):
            fail("managed_decision_failed_invariants_not_empty")

    result["failures"] = failures
    result["valid"] = not failures
    return result


def _apply_managed_child_audit(row: dict[str, Any]) -> None:
    run_dir_value = row.get("lm8i_run_dir")
    if not run_dir_value:
        return
    audit = _audit_managed_child(Path(str(run_dir_value)))
    row.update(
        {
            "managed_verifier_audit_performed": audit["performed"],
            "managed_verifier_audit_valid": audit["valid"],
            "managed_verifier_audit_failures": audit["failures"],
            "readiness_wait_count": audit["readiness_wait_count"],
            "readiness_wait_status": audit["readiness_wait_status"],
            "readiness_failure_reason": audit["readiness_failure_reason"],
            "fenced_output_read_count": audit["fenced_output_read_count"],
            "settle_read_count": audit["settle_read_count"],
            "readiness_fenced": audit["readiness_fenced"],
            "receipt_id_hashes_match": audit["receipt_id_hashes_match"],
            "document_session_ids_match": audit["document_session_ids_match"],
            "mutation_epochs_match": audit["mutation_epochs_match"],
            "solution_run_epochs_match": audit["solution_run_epochs_match"],
            "post_mutation_solution_run_advanced": audit[
                "post_mutation_solution_run_advanced"
            ],
        }
    )
    if row.get("lm8i_decision") == "accepted" and not audit["valid"]:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = "accepted_child_managed_verifier_audit_failed"


def _read_decision(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "lm8i_missing_decision_json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "lm8i_invalid_decision_json"
    except UnicodeDecodeError:
        return None, "lm8i_unreadable_decision_json:UnicodeDecodeError"
    except OSError as exc:
        return None, f"lm8i_unreadable_decision_json:{exc.__class__.__name__}"
    if not isinstance(payload, dict):
        return None, "lm8i_decision_not_mapping"
    return payload, None


def _classify_decision(decision: Mapping[str, Any]) -> tuple[str, str | None]:
    value = decision.get("decision")
    if not isinstance(value, str):
        return "wrapper_error", "lm8i_missing_decision"
    if value not in TERMINAL_CATEGORIES:
        return "wrapper_error", f"lm8i_unknown_decision:{value}"
    if value == "wrapper_error":
        return "wrapper_error", "lm8i_unexpected_wrapper_error_decision"
    return value, None


def _copy_bool(row: dict[str, Any], decision: Mapping[str, Any], key: str) -> None:
    value = decision.get(key)
    if isinstance(value, bool):
        row[key] = value


def _copy_decision_metadata(row: dict[str, Any], decision: Mapping[str, Any]) -> None:
    for key in (
        "worker_publication_ran",
        "live_fixture_created",
        "live_set_value_dispatched",
        "verify_scalar_output_ran",
        "publication_support_attempted",
        "support_eligible",
    ):
        _copy_bool(row, decision, key)

    scalar_ready = decision.get("scalar_runtime_ready")
    if isinstance(scalar_ready, bool) or scalar_ready is None:
        row["scalar_runtime_ready"] = scalar_ready

    support_count = decision.get("publication_support_count")
    if isinstance(support_count, int) and not isinstance(support_count, bool):
        row["publication_support_count"] = support_count

    observed = decision.get("observed_output_after")
    if isinstance(observed, (int, float)) and not isinstance(observed, bool):
        row["observed_output_after"] = observed

    for key in (
        "support_not_attempted_reason",
        "first_publication_status",
        "first_publication_failure_reason",
        "final_publication_status",
        "final_publication_failure_reason",
        "final_worker_response_kind",
    ):
        value = decision.get(key)
        row[key] = value if isinstance(value, str) else None


def _worker_action_value_from_decision_excerpt(
    decision: Mapping[str, Any],
) -> int | float | None:
    excerpt = decision.get("worker_action_input_excerpt")
    if not isinstance(excerpt, str):
        return None
    try:
        payload = json.loads(excerpt)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, Mapping):
        return None

    candidate: object = None
    nested_input = payload.get("input")
    if isinstance(nested_input, Mapping):
        candidate = nested_input.get("value")
    if candidate is None:
        candidate = payload.get("value")

    if not isinstance(candidate, (int, float)) or isinstance(candidate, bool):
        return None
    if isinstance(candidate, float) and not math.isfinite(candidate):
        return None
    return candidate


def _copy_decision_identity(row: dict[str, Any], decision: Mapping[str, Any]) -> None:
    decision_value = decision.get("decision")
    reason_value = decision.get("reason")
    row["lm8i_decision"] = decision_value if isinstance(decision_value, str) else None
    row["lm8i_reason"] = reason_value if isinstance(reason_value, str) else None
    if row["lm8i_decision"] == "gate_failed":
        row["gate_failure_reason"] = row["lm8i_reason"]
    if row["lm8i_decision"] == "preflight_failed":
        row["preflight_failure_reason"] = row["lm8i_reason"]
    _copy_decision_metadata(row, decision)


def _row_from_completed_lm8i(
    *,
    attempt_index: int,
    completed: subprocess.CompletedProcess,
    child_run_dirs: Sequence[Path],
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    child_run_dir, child_error = _single_child_dir_error(child_run_dirs)
    row.update(
        {
            "lm8i_invoked": True,
            "lm8i_returncode": completed.returncode,
            "lm8i_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "stdout_excerpt": _excerpt(_completed_text(completed.stdout)),
            "stderr_excerpt": _excerpt(_completed_text(completed.stderr)),
        }
    )
    if completed.returncode != 0:
        if child_run_dir is not None:
            decision, read_error = _read_decision(child_run_dir / "decision.json")
            if read_error is None and decision is not None:
                _copy_decision_identity(row, decision)
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = f"lm8i_nonzero_returncode:{completed.returncode}"
        row["child_run_dir_error"] = child_error
        return row
    if child_error is not None:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = child_error
        return row

    assert child_run_dir is not None
    decision, read_error = _read_decision(child_run_dir / "decision.json")
    if read_error is not None:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = read_error
        return row

    assert decision is not None
    terminal_category, failure_reason = _classify_decision(decision)
    row["terminal_category"] = terminal_category
    row["failure_reason"] = failure_reason
    _copy_decision_identity(row, decision)
    return row


def _copy_child_artifact_summaries(row: dict[str, Any]) -> None:
    run_dir_value = row.get("lm8i_run_dir")
    if not run_dir_value:
        return

    run_dir = Path(str(run_dir_value))
    worker_action_path = run_dir / "worker_action.json"
    worker_action = _read_json_mapping(worker_action_path)
    if row.get("publication_support_attempted") is True and worker_action_path.exists():
        row["support_recovered"] = True
    if worker_action is not None:
        action_input = worker_action.get("input")
        if isinstance(action_input, Mapping):
            value = action_input.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row["worker_action_value"] = value
    if row.get("worker_action_value") is None:
        decision = _read_json_mapping(run_dir / "decision.json")
        if decision is not None:
            value = _worker_action_value_from_decision_excerpt(decision)
            if value is not None:
                row["worker_action_value"] = value

    verify_summary = _read_json_mapping(run_dir / "verify_scalar_output_summary.json")
    if verify_summary is not None:
        attempt_count = verify_summary.get("attempt_count")
        if isinstance(attempt_count, int) and not isinstance(attempt_count, bool):
            row["verifier_attempt_count"] = attempt_count
        observed_value = verify_summary.get("observed_output_value")
        if isinstance(observed_value, (int, float)) and not isinstance(observed_value, bool):
            row["observed_output_after"] = observed_value


def _scan_leak_markers(run_dir: Path) -> list[dict[str, Any]]:
    if not run_dir.exists() or not run_dir.is_dir():
        return []

    matches: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*"), key=lambda item: str(item)):
        if not path.is_file() or path.suffix.lower() not in LEAK_SCAN_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for marker in LEAK_MARKERS:
            if marker in text:
                matches.append({"path": str(path), "marker": marker})
    return matches


def _apply_leak_scan(row: dict[str, Any]) -> None:
    run_dir_value = row.get("lm8i_run_dir")
    if not run_dir_value:
        return
    matches = _scan_leak_markers(Path(str(run_dir_value)))
    row["leak_check_performed"] = True
    row["leak_marker_matches"] = matches
    row["leak_marker_match_count"] = len(matches)


def _compact_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter) if counter[key]}


def _reason_counts(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if isinstance(value, str) and value:
            counter[value] += 1
    return _compact_counts(counter)


def _number_values(rows: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(value)
    return values


def _int_values(rows: Sequence[Mapping[str, Any]], key: str) -> list[int]:
    values: list[int] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            values.append(value)
    return values


def _build_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    attempts: int,
    model: str,
    attempt_timeout_s: int,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
) -> dict[str, Any]:
    _, schema = _run_identity(verifier_profile)
    worker_summary_categories = {
        "accepted",
        "rejected",
        "worker_declined",
        "publication_failed",
    }

    terminal_counts: Counter[str] = Counter()
    for row in rows:
        category = row.get("terminal_category")
        if isinstance(category, str):
            terminal_counts[category] += 1

    worker_rows = [row for row in rows if row.get("worker_publication_ran") is True]
    worker_counts: Counter[str] = Counter()
    for row in worker_rows:
        category = row.get("terminal_category")
        if isinstance(category, str) and category in worker_summary_categories:
            worker_counts[category] += 1

    support_attempted_rows = [
        row for row in rows if row.get("publication_support_attempted") is True
    ]
    support_recovered_rows = [
        row for row in rows if row.get("support_recovered") is True
    ]
    accepted_support_rows = [
        row
        for row in rows
        if row.get("terminal_category") == "accepted"
        and row.get("publication_support_attempted") is True
    ]
    accepted_without_support_rows = [
        row
        for row in rows
        if row.get("terminal_category") == "accepted"
        and row.get("publication_support_attempted") is not True
    ]
    canonical_evidence = _canonical_evidence(
        attempts=attempts,
        model=model,
        attempt_timeout_s=attempt_timeout_s,
        verifier_profile=verifier_profile,
    )
    leak_marker_match_count = sum(
        int(row.get("leak_marker_match_count") or 0) for row in rows
    )
    worker_action_values = _number_values(rows, "worker_action_value")
    observed_values = _number_values(rows, "observed_output_after")

    summary = {
        "schema": schema,
        "scheduled_attempts": attempts,
        "attempt_timeout_s": attempt_timeout_s,
        "canonical_evidence": canonical_evidence,
        "terminal_category_counts": _compact_counts(terminal_counts),
        "accepted_count": terminal_counts["accepted"],
        "rejected_count": terminal_counts["rejected"],
        "worker_declined_count": terminal_counts["worker_declined"],
        "publication_failed_count": terminal_counts["publication_failed"],
        "gate_failed_count": terminal_counts["gate_failed"],
        "preflight_failed_count": terminal_counts["preflight_failed"],
        "wrapper_error_count": terminal_counts["wrapper_error"],
        "worker_reached_count": len(worker_rows),
        "worker_terminal_counts": _compact_counts(worker_counts),
        "publication_support_attempted_count": len(support_attempted_rows),
        "publication_support_recovered_count": len(support_recovered_rows),
        "accepted_without_support_count": len(accepted_without_support_rows),
        "support_eligible_count": sum(
            1 for row in rows if row.get("support_eligible") is True
        ),
        "support_accepted_count": len(accepted_support_rows),
        "gate_failure_reasons": _reason_counts(rows, "gate_failure_reason"),
        "preflight_failure_reasons": _reason_counts(rows, "preflight_failure_reason"),
        "leak_marker_match_count": leak_marker_match_count,
        "attempt_run_dirs": [
            str(row["lm8i_run_dir"]) for row in rows if row.get("lm8i_run_dir")
        ],
        "worker_action_values": worker_action_values,
        "verifier_attempt_counts": _int_values(rows, "verifier_attempt_count"),
        "observed_output_values_after": observed_values,
    }

    if verifier_profile != MANAGED_VERIFIER_PROFILE:
        return summary

    managed_rows = [
        row
        for row in rows
        if row.get("verifier_profile") == MANAGED_VERIFIER_PROFILE
    ]
    total_waits = sum(
        int(row.get("readiness_wait_count") or 0) for row in managed_rows
    )
    total_fenced_reads = sum(
        int(row.get("fenced_output_read_count") or 0) for row in managed_rows
    )
    total_settle_reads = sum(
        int(row.get("settle_read_count") or 0) for row in managed_rows
    )
    managed_audit_pass_count = sum(
        1
        for row in managed_rows
        if row.get("managed_verifier_audit_valid") is True
    )
    managed_audit_failure_count = sum(
        1
        for row in managed_rows
        if row.get("managed_verifier_audit_performed") is True
        and row.get("managed_verifier_audit_valid") is False
    )
    accepted_child_contradictions = sum(
        1
        for row in managed_rows
        if row.get("failure_reason")
        == "accepted_child_managed_verifier_audit_failed"
    )
    comparison_success = (
        canonical_evidence is True
        and verifier_profile == MANAGED_VERIFIER_PROFILE
        and attempts == 20
        and terminal_counts["accepted"] == 20
        and managed_audit_pass_count == 20
        and total_waits == 20
        and total_fenced_reads == 20
        and total_settle_reads == 0
        and accepted_child_contradictions == 0
        and worker_action_values == [3.0] * 20
        and all(
            math.isclose(value, EXPECTED_OUTPUT_VALUE, abs_tol=SCALAR_TOLERANCE)
            for value in observed_values
        )
        and leak_marker_match_count == 0
    )
    summary.update(
        {
            "verifier_profile": MANAGED_VERIFIER_PROFILE,
            "verifier_mechanism": VERIFIER_MECHANISM,
            "fixture_readiness_profile": FIXTURE_READINESS_PROFILE,
            "readiness_wait_timeout_ms": READINESS_WAIT_TIMEOUT_MS,
            "child_attempt_timeout_s": attempt_timeout_s,
            "readiness_ready_count": sum(
                1
                for row in managed_rows
                if row.get("readiness_wait_status") == "ready"
            ),
            "readiness_failure_reason_counts": _reason_counts(
                managed_rows, "readiness_failure_reason"
            ),
            "total_readiness_wait_count": total_waits,
            "total_fenced_output_read_count": total_fenced_reads,
            "total_settle_read_count": total_settle_reads,
            "managed_verifier_audit_pass_count": managed_audit_pass_count,
            "managed_verifier_audit_failure_count": managed_audit_failure_count,
            "managed_verifier_invariant_violation_count": sum(
                1
                for row in managed_rows
                if row.get("managed_verifier_audit_failures")
            ),
            "post_mutation_run_advance_failure_count": sum(
                1
                for row in managed_rows
                if "post_mutation_solution_run_not_advanced"
                in row.get("managed_verifier_audit_failures", [])
            ),
            "accepted_child_audit_contradiction_count": (
                accepted_child_contradictions
            ),
            "comparison_success": comparison_success,
        }
    )
    return summary


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(payload), sort_keys=True) + "\n")


def _run_probe(
    *,
    attempts: int,
    model: str,
    run_root: str | Path,
    attempt_timeout_s: int,
    verifier_profile: str = SETTLE_VERIFIER_PROFILE,
    run_subprocess=None,
) -> Path:
    runner = run_subprocess or subprocess.run
    run_dir = _new_run_dir(run_root, verifier_profile=verifier_profile)
    lm8i_runs_dir = run_dir / "lm8i_runs"
    lm8i_runs_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        run_dir / "manifest.json",
        _manifest(
            attempts=attempts,
            model=model,
            attempt_timeout_s=attempt_timeout_s,
            verifier_profile=verifier_profile,
        ),
    )

    rows: list[dict[str, Any]] = []
    for attempt_index in range(1, attempts + 1):
        before = {path for path in lm8i_runs_dir.glob("lm8i-*") if path.is_dir()}
        command = _lm8i_command(
            model=model,
            lm8i_runs_dir=lm8i_runs_dir,
            verifier_profile=verifier_profile,
        )
        try:
            completed = runner(
                command,
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=attempt_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            child_run_dirs = _discover_child_run_dirs(lm8i_runs_dir, before)
            row = _timeout_row(
                attempt_index=attempt_index,
                exc=exc,
                child_run_dirs=child_run_dirs,
            )
        except Exception as exc:
            child_run_dirs = _discover_child_run_dirs(lm8i_runs_dir, before)
            row = _subprocess_error_row(
                attempt_index=attempt_index,
                exc=exc,
                child_run_dirs=child_run_dirs,
            )
        else:
            child_run_dirs = _discover_child_run_dirs(lm8i_runs_dir, before)
            row = _row_from_completed_lm8i(
                attempt_index=attempt_index,
                completed=completed,
                child_run_dirs=child_run_dirs,
            )
        if verifier_profile == MANAGED_VERIFIER_PROFILE:
            row.update(
                _managed_attempt_fields(
                    child_attempt_timeout_s=attempt_timeout_s,
                )
            )
        _copy_child_artifact_summaries(row)
        if verifier_profile == MANAGED_VERIFIER_PROFILE:
            _apply_managed_child_audit(row)
        _apply_leak_scan(row)
        rows.append(row)
        _append_jsonl(run_dir / "attempts.jsonl", row)

    _write_json(
        run_dir / "summary.json",
        _build_summary(
            rows,
            attempts=attempts,
            model=model,
            attempt_timeout_s=attempt_timeout_s,
            verifier_profile=verifier_profile,
        ),
    )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    run_dir = _run_probe(
        attempts=args.attempts,
        model=args.model,
        run_root=args.run_dir,
        attempt_timeout_s=args.attempt_timeout_s,
        verifier_profile=args.verifier_profile,
    )
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    print(
        "LM8J affine support repeatability probe complete "
        f"run_dir={run_dir} "
        f"accepted={summary.get('accepted_count')} "
        f"scheduled={summary.get('scheduled_attempts')} "
        f"support_attempted={summary.get('publication_support_attempted_count')} "
        f"support_recovered={summary.get('publication_support_recovered_count')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
