#!/usr/bin/env python
"""LM8J repeatability wrapper for LM8I affine support-enabled live probe."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT_SCHEMA = "rook.lm8j_affine_support_repeatability_probe:v1"
DEFAULT_ATTEMPTS = 20
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_RUN_DIR = "probe_runs"
DEFAULT_ATTEMPT_TIMEOUT_S = 600
EXCERPT_CHARS = 2000
LEAK_MARKERS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "BindStepSpec.base_params",
    "repair_same_component.bind.base_params",
)
TERMINAL_CATEGORIES = (
    "accepted",
    "rejected",
    "worker_declined",
    "publication_failed",
    "gate_failed",
    "preflight_failed",
    "wrapper_error",
)


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


def _canonical_evidence(*, attempts: int, model: str, attempt_timeout_s: int) -> bool:
    return (
        attempts == DEFAULT_ATTEMPTS
        and model == DEFAULT_MODEL
        and attempt_timeout_s == DEFAULT_ATTEMPT_TIMEOUT_S
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


def _new_run_dir(run_root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = Path(run_root) / f"lm8j-{timestamp}-{_git_short_sha()}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}-{suffix:02d}")
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _manifest(*, attempts: int, model: str, attempt_timeout_s: int) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "attempts": attempts,
        "model": model,
        "attempt_timeout_s": attempt_timeout_s,
        "canonical_evidence": _canonical_evidence(
            attempts=attempts,
            model=model,
            attempt_timeout_s=attempt_timeout_s,
        ),
        "child_probe": "lm8i_affine_publication_shape_support_probe.py",
        "child_probe_invocation": "subprocess",
        "support_mode": "lm8i_default_support_enabled",
        "replacement_attempts": False,
    }


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


def _lm8i_command(*, model: str, lm8i_runs_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "lm8i_affine_publication_shape_support_probe.py"),
        "--model",
        model,
        "--run-dir",
        str(lm8i_runs_dir),
    ]


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
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _read_decision(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "lm8i_missing_decision_json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "lm8i_invalid_decision_json"
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
    worker_action = _read_json_mapping(run_dir / "worker_action.json")
    if worker_action is not None:
        action_input = worker_action.get("input")
        if isinstance(action_input, Mapping):
            value = action_input.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row["worker_action_value"] = value
        if row.get("publication_support_attempted") is True:
            row["support_recovered"] = True

    verify_summary = _read_json_mapping(run_dir / "verify_scalar_output_summary.json")
    if verify_summary is not None:
        attempt_count = verify_summary.get("attempt_count")
        if isinstance(attempt_count, int) and not isinstance(attempt_count, bool):
            row["verifier_attempt_count"] = attempt_count
        observed_value = verify_summary.get("observed_output_value")
        if isinstance(observed_value, (int, float)) and not isinstance(observed_value, bool):
            row["observed_output_after"] = observed_value
