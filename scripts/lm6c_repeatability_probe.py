#!/usr/bin/env python
"""LM6C repeatability wrapper for the frozen LM6A live splice protocol."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
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


def _scan_leak_markers(run_dir: Path) -> list[dict[str, Any]]:
    if not run_dir.exists() or not run_dir.is_dir():
        return []

    matches: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for marker in LEAK_MARKERS:
            if marker in text:
                matches.append(
                    {
                        "path": str(path),
                        "marker": marker,
                    }
                )
    return matches


def _apply_leak_scan(row: dict[str, Any]) -> None:
    run_dir = row.get("lm6a_run_dir")
    if not run_dir:
        return

    matches = _scan_leak_markers(Path(run_dir))
    row["leak_check_performed"] = True
    row["leak_marker_matches"] = matches
    row["leak_marker_match_count"] = len(matches)


def _compact_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter) if counter[key]}


def _build_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    attempts: int,
    model: str,
) -> dict[str, Any]:
    terminal_counts = Counter(str(row.get("terminal_category")) for row in rows)
    worker_rows = [
        row
        for row in rows
        if row.get("terminal_category") in WORKER_TERMINAL_CATEGORIES
    ]
    worker_counts = Counter(str(row.get("terminal_category")) for row in worker_rows)
    return {
        "schema": SCRIPT_SCHEMA,
        "scheduled_attempts": attempts,
        "terminal_category_counts": _compact_counts(terminal_counts),
        "preflight_failed_count": terminal_counts["preflight_failed"],
        "lm6a_invoked_count": sum(1 for row in rows if row.get("lm6a_invoked")),
        "gate_failed_count": terminal_counts["gate_failed"],
        "worker_reached_count": len(worker_rows),
        "worker_terminal_counts": _compact_counts(worker_counts),
        "accepted_count": terminal_counts["accepted"],
        "leak_marker_match_count": sum(
            int(row.get("leak_marker_match_count") or 0) for row in rows
        ),
        "attempt_run_dirs": [
            str(row["lm6a_run_dir"]) for row in rows if row.get("lm6a_run_dir")
        ],
        "canonical_evidence": _canonical_evidence(attempts=attempts, model=model),
    }


def _scheduled_attempt_id(attempt_index: int) -> str:
    return f"attempt-{attempt_index:03d}"


def _tool_result_ok(result: object) -> bool:
    if not isinstance(result, Mapping):
        return False
    if result.get("ok") is False:
        return False
    if result.get("success") is False:
        return False
    if result.get("status") in {"error", "failed"}:
        return False
    if result.get("error") or result.get("errors"):
        return False
    return True


async def _run_preflight() -> tuple[bool, str | None]:
    from rook.server import _mcp_tool_executor

    for tool_name in ("rhino_ping", "gh_document_new"):
        try:
            result = await _mcp_tool_executor(tool_name, {})
        except Exception as exc:
            return False, f"{tool_name}_exception:{exc.__class__.__name__}"
        if not _tool_result_ok(result):
            return False, f"{tool_name}_failed"
    return True, None


def _base_attempt_row(*, attempt_index: int) -> dict[str, Any]:
    return {
        "attempt_index": attempt_index,
        "scheduled_attempt_id": _scheduled_attempt_id(attempt_index),
        "preflight_status": None,
        "lm6a_invoked": False,
        "lm6a_returncode": None,
        "lm6a_run_dir": None,
        "lm6a_decision": None,
        "lm6a_reason": None,
        "terminal_category": None,
        "stdout_excerpt": "",
        "stderr_excerpt": "",
        "failure_reason": None,
        "leak_check_performed": False,
        "leak_marker_matches": [],
        "leak_marker_match_count": 0,
    }


def _preflight_failed_row(*, attempt_index: int, reason: str) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    row.update(
        {
            "preflight_status": "failed",
            "terminal_category": "preflight_failed",
            "failure_reason": reason,
        }
    )
    return row


def _discover_child_run_dir(lm6a_runs_dir: Path, before: set[Path]) -> Path | None:
    after = set(lm6a_runs_dir.glob("lm6a-*"))
    created = sorted(after - before, key=lambda path: path.stat().st_mtime)
    if len(created) != 1:
        return None
    return created[0]


def _classify_decision(decision: Mapping[str, Any]) -> tuple[str, str | None]:
    value = decision.get("decision")
    if not isinstance(value, str):
        return "wrapper_error", "lm6a_missing_decision"
    if value not in TERMINAL_CATEGORIES:
        return "wrapper_error", f"lm6a_unknown_decision:{value}"
    if value == "preflight_failed":
        return "wrapper_error", "lm6a_unexpected_preflight_failed_decision"
    if value == "wrapper_error":
        return "wrapper_error", "lm6a_unexpected_wrapper_error_decision"
    return value, None


def _read_decision(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "lm6a_missing_decision_json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, "lm6a_invalid_decision_json"
    except OSError as exc:
        return None, f"lm6a_unreadable_decision_json:{exc.__class__.__name__}"
    if not isinstance(payload, dict):
        return None, "lm6a_decision_not_mapping"
    return payload, None


def _completed_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _row_from_completed_lm6a(
    *,
    attempt_index: int,
    completed: subprocess.CompletedProcess,
    child_run_dir: Path | None,
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    row.update(
        {
            "preflight_status": "passed",
            "lm6a_invoked": True,
            "lm6a_returncode": completed.returncode,
            "lm6a_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "stdout_excerpt": _excerpt(_completed_text(completed.stdout)),
            "stderr_excerpt": _excerpt(_completed_text(completed.stderr)),
        }
    )

    if completed.returncode != 0:
        row.update(
            {
                "terminal_category": "wrapper_error",
                "failure_reason": f"lm6a_nonzero_returncode:{completed.returncode}",
            }
        )
        return row

    if child_run_dir is None:
        row.update(
            {
                "terminal_category": "wrapper_error",
                "failure_reason": "lm6a_missing_child_run_dir",
            }
        )
        return row

    decision, read_error = _read_decision(child_run_dir / "decision.json")
    if read_error is not None:
        row.update(
            {
                "terminal_category": "wrapper_error",
                "failure_reason": read_error,
            }
        )
        return row

    assert decision is not None
    terminal_category, failure_reason = _classify_decision(decision)
    decision_value = decision.get("decision")
    reason_value = decision.get("reason")
    row.update(
        {
            "lm6a_decision": decision_value if isinstance(decision_value, str) else None,
            "lm6a_reason": reason_value if isinstance(reason_value, str) else None,
            "terminal_category": terminal_category,
            "failure_reason": failure_reason,
        }
    )
    return row


def _manifest(*, attempts: int, model: str) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "attempts": attempts,
        "model": model,
        "canonical_evidence": _canonical_evidence(attempts=attempts, model=model),
    }


def _lm6a_command(*, model: str, lm6a_runs_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "lm6a_live_worker_splice_probe.py"),
        "--model",
        model,
        "--run-dir",
        str(lm6a_runs_dir),
    ]


def _timeout_row(
    *,
    attempt_index: int,
    exc: subprocess.TimeoutExpired,
    child_run_dir: Path | None,
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    row.update(
        {
            "preflight_status": "passed",
            "lm6a_invoked": True,
            "lm6a_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "terminal_category": "wrapper_error",
            "stdout_excerpt": _excerpt(_completed_text(exc.stdout)),
            "stderr_excerpt": _excerpt(_completed_text(exc.stderr)),
            "failure_reason": "lm6a_timeout",
        }
    )
    return row


def _subprocess_error_row(
    *,
    attempt_index: int,
    exc: Exception,
    child_run_dir: Path | None,
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    row.update(
        {
            "preflight_status": "passed",
            "lm6a_invoked": True,
            "lm6a_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "terminal_category": "wrapper_error",
            "failure_reason": f"lm6a_subprocess_error:{type(exc).__name__}",
        }
    )
    return row


def _run_probe(
    *,
    attempts: int,
    model: str,
    run_root: str | Path,
    attempt_timeout_s: int,
    run_subprocess=subprocess.run,
) -> Path:
    run_dir = _new_run_dir(run_root)
    lm6a_runs_root = run_dir / "lm6a_runs"
    lm6a_runs_root.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "manifest.json", _manifest(attempts=attempts, model=model))

    rows: list[dict[str, Any]] = []
    attempts_path = run_dir / "attempts.jsonl"
    for attempt_index in range(1, attempts + 1):
        lm6a_runs_dir = lm6a_runs_root / _scheduled_attempt_id(attempt_index)
        lm6a_runs_dir.mkdir(parents=True, exist_ok=True)
        ok, reason = asyncio.run(_run_preflight())
        if not ok:
            row = _preflight_failed_row(
                attempt_index=attempt_index,
                reason=reason or "preflight_failed",
            )
            rows.append(row)
            _append_jsonl(attempts_path, row)
            continue

        before = set(lm6a_runs_dir.glob("lm6a-*"))
        command = _lm6a_command(model=model, lm6a_runs_dir=lm6a_runs_dir)
        try:
            completed = run_subprocess(
                command,
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=attempt_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            child_run_dir = _discover_child_run_dir(lm6a_runs_dir, before)
            row = _timeout_row(
                attempt_index=attempt_index,
                exc=exc,
                child_run_dir=child_run_dir,
            )
            _apply_leak_scan(row)
            rows.append(row)
            _append_jsonl(attempts_path, row)
            continue
        except Exception as exc:
            child_run_dir = _discover_child_run_dir(lm6a_runs_dir, before)
            row = _subprocess_error_row(
                attempt_index=attempt_index,
                exc=exc,
                child_run_dir=child_run_dir,
            )
            _apply_leak_scan(row)
            rows.append(row)
            _append_jsonl(attempts_path, row)
            continue

        child_run_dir = _discover_child_run_dir(lm6a_runs_dir, before)
        row = _row_from_completed_lm6a(
            attempt_index=attempt_index,
            completed=completed,
            child_run_dir=child_run_dir,
        )
        _apply_leak_scan(row)
        rows.append(row)
        _append_jsonl(attempts_path, row)

    _write_json(
        run_dir / "summary.json",
        _build_summary(rows, attempts=attempts, model=model),
    )
    return run_dir


def _script_path() -> Path:
    return Path(__file__).resolve()


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    run_dir = _run_probe(
        attempts=args.attempts,
        model=args.model,
        run_root=args.run_dir,
        attempt_timeout_s=args.attempt_timeout_s,
    )
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    print(
        "LM6C repeatability probe complete: "
        f"run_dir={run_dir} "
        f"terminal_category_counts={summary['terminal_category_counts']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
