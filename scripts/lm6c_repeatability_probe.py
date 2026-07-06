#!/usr/bin/env python
"""LM6C repeatability wrapper for the frozen LM6A live splice protocol."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


SCRIPT_SCHEMA = "rook.lm6c_repeatability_probe:v1"
DEFAULT_ATTEMPTS = 5
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_RUN_DIR = "probe_runs"
DEFAULT_ATTEMPT_TIMEOUT_S = 600
EXCERPT_CHARS = 2000
LEAK_MARKERS = (
    "PROBE_REPAIR_CODE",
    "A = 42.0",
    "BindStepSpec.base_params.code",
)
TERMINAL_CATEGORIES = (
    "preflight_failed",
    "gate_failed",
    "accepted",
    "rejected",
    "worker_declined",
    "publication_failed",
    "wrapper_error",
)
WORKER_TERMINAL_CATEGORIES = (
    "accepted",
    "rejected",
    "worker_declined",
    "publication_failed",
)


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LM6C repeatability probe.")
    parser.add_argument("--attempts", type=_positive_int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--run-dir", default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--attempt-timeout-s",
        type=_positive_int,
        default=DEFAULT_ATTEMPT_TIMEOUT_S,
    )
    return parser.parse_args(argv)


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
    run_dir = Path(run_root) / f"lm6c-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _canonical_evidence(*, attempts: int, model: str) -> bool:
    return attempts == DEFAULT_ATTEMPTS and model == DEFAULT_MODEL


def _excerpt(text: str | None, *, limit: int = EXCERPT_CHARS) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit]
