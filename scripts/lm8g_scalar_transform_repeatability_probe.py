#!/usr/bin/env python
"""LM8G repeatability wrapper for the LM8F scalar transform live probe."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT_SCHEMA = "rook.lm8g_scalar_transform_repeatability_probe:v1"
DEFAULT_ATTEMPTS = 5
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_RUN_DIR = "probe_runs"
DEFAULT_ATTEMPT_TIMEOUT_S = 600
EXCERPT_CHARS = 2000
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
        description="LM8G scalar transform repeatability probe."
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
    }
    if argv:
        for token in argv:
            if token in forbidden:
                parser.error(f"unsupported_lm8g_argument:{token}")
    return parser.parse_args(argv)


def _canonical_evidence(*, attempts: int, model: str) -> bool:
    return attempts == DEFAULT_ATTEMPTS and model == DEFAULT_MODEL


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
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(run_root) / f"lm8g-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _manifest(*, attempts: int, model: str) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "attempts": attempts,
        "model": model,
        "canonical_evidence": _canonical_evidence(attempts=attempts, model=model),
        "child_probe": "lm8f_scalar_transform_depth_probe",
        "child_probe_invocation": "subprocess",
    }


def _lm8f_command(*, model: str, lm8f_runs_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "lm8f_scalar_transform_depth_probe.py"),
        "--model",
        model,
        "--run-dir",
        str(lm8f_runs_dir),
    ]


def _scheduled_attempt_id(attempt_index: int) -> str:
    return f"attempt-{attempt_index:03d}"


def _base_attempt_row(*, attempt_index: int) -> dict[str, Any]:
    return {
        "attempt_index": attempt_index,
        "scheduled_attempt_id": _scheduled_attempt_id(attempt_index),
        "lm8f_invoked": False,
        "lm8f_returncode": None,
        "lm8f_run_dir": None,
        "lm8f_decision": None,
        "lm8f_reason": None,
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
        "worker_action_value": None,
        "verifier_attempt_count": None,
        "observed_output_after": None,
        "leak_check_performed": False,
        "leak_marker_matches": [],
        "leak_marker_match_count": 0,
    }


def _discover_child_run_dirs(lm8f_runs_dir: Path, before: set[Path]) -> list[Path]:
    after = set(lm8f_runs_dir.glob("lm8f-*"))
    created = sorted(after - before, key=lambda path: path.stat().st_mtime)
    return created


def _read_decision(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "lm8f_missing_decision_json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "lm8f_invalid_decision_json"
    except OSError as exc:
        return None, f"lm8f_unreadable_decision_json:{exc.__class__.__name__}"
    if not isinstance(payload, dict):
        return None, "lm8f_decision_not_mapping"
    return payload, None


def _classify_decision(decision: Mapping[str, Any]) -> tuple[str, str | None]:
    value = decision.get("decision")
    if not isinstance(value, str):
        return "wrapper_error", "lm8f_missing_decision"
    if value not in TERMINAL_CATEGORIES:
        return "wrapper_error", f"lm8f_unknown_decision:{value}"
    if value == "wrapper_error":
        return "wrapper_error", "lm8f_unexpected_wrapper_error_decision"
    return value, None
