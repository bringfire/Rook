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
