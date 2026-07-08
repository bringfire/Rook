#!/usr/bin/env python
"""LM8G repeatability wrapper for the LM8F scalar transform live probe."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]

SCRIPT_SCHEMA = "rook.lm8g_scalar_transform_repeatability_probe:v1"
DEFAULT_ATTEMPTS = 5
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_RUN_DIR = "probe_runs"
DEFAULT_ATTEMPT_TIMEOUT_S = 600
EXCERPT_CHARS = 2000


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
