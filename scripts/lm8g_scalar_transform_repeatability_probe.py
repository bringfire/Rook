#!/usr/bin/env python
"""LM8G repeatability wrapper for the LM8F scalar transform live probe."""

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

SCRIPT_SCHEMA = "rook.lm8g_scalar_transform_repeatability_probe:v1"
DEFAULT_ATTEMPTS = 5
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


def _single_child_dir_error(child_run_dirs: Sequence[Path]) -> tuple[Path | None, str | None]:
    if len(child_run_dirs) == 0:
        return None, "child_run_dir_missing"
    if len(child_run_dirs) > 1:
        return None, "child_run_dir_ambiguous"
    return child_run_dirs[0], None


def _copy_decision_metadata(row: dict[str, Any], decision: Mapping[str, Any]) -> None:
    for key in (
        "worker_publication_ran",
        "live_fixture_created",
        "live_set_value_dispatched",
        "verify_scalar_output_ran",
    ):
        value = decision.get(key)
        if isinstance(value, bool):
            row[key] = value
    scalar_ready = decision.get("scalar_runtime_ready")
    if isinstance(scalar_ready, bool) or scalar_ready is None:
        row["scalar_runtime_ready"] = scalar_ready
    observed = decision.get("observed_output_after")
    if isinstance(observed, (int, float)) and not isinstance(observed, bool):
        row["observed_output_after"] = observed


def _row_from_completed_lm8f(
    *,
    attempt_index: int,
    completed: subprocess.CompletedProcess,
    child_run_dirs: Sequence[Path],
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    child_run_dir, child_error = _single_child_dir_error(child_run_dirs)
    row.update(
        {
            "lm8f_invoked": True,
            "lm8f_returncode": completed.returncode,
            "lm8f_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "stdout_excerpt": _excerpt(_completed_text(completed.stdout)),
            "stderr_excerpt": _excerpt(_completed_text(completed.stderr)),
        }
    )
    if completed.returncode != 0:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = f"lm8f_nonzero_returncode:{completed.returncode}"
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
    decision_value = decision.get("decision")
    reason_value = decision.get("reason")
    row["lm8f_decision"] = decision_value if isinstance(decision_value, str) else None
    row["lm8f_reason"] = reason_value if isinstance(reason_value, str) else None
    _copy_decision_metadata(row, decision)
    return row


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
            "lm8f_invoked": True,
            "lm8f_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "terminal_category": "wrapper_error",
            "failure_reason": "lm8f_timeout",
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
            "lm8f_invoked": True,
            "lm8f_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "terminal_category": "wrapper_error",
            "failure_reason": f"lm8f_subprocess_error:{exc.__class__.__name__}",
            "child_run_dir_error": child_error,
        }
    )
    return row


def _scan_leak_markers(run_dir: Path) -> list[dict[str, Any]]:
    if not run_dir.exists() or not run_dir.is_dir():
        return []

    matches: list[dict[str, Any]] = []
    for path in sorted(run_dir.rglob("*.json"), key=lambda item: str(item)):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for marker in LEAK_MARKERS:
            if marker in text:
                matches.append({"path": str(path), "marker": marker})
    return matches


def _apply_leak_scan(row: dict[str, Any]) -> None:
    run_dir_value = row.get("lm8f_run_dir")
    if not run_dir_value:
        return
    matches = _scan_leak_markers(Path(str(run_dir_value)))
    row["leak_check_performed"] = True
    row["leak_marker_matches"] = matches
    row["leak_marker_match_count"] = len(matches)


def _read_json_mapping(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _copy_child_artifact_summaries(row: dict[str, Any]) -> None:
    run_dir_value = row.get("lm8f_run_dir")
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

    verify_summary = _read_json_mapping(run_dir / "verify_scalar_output_summary.json")
    if verify_summary is not None:
        attempt_count = verify_summary.get("attempt_count")
        if isinstance(attempt_count, int) and not isinstance(attempt_count, bool):
            row["verifier_attempt_count"] = attempt_count


def _compact_counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter) if counter[key]}


def _build_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    attempts: int,
    model: str,
) -> dict[str, Any]:
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

    return {
        "schema": SCRIPT_SCHEMA,
        "scheduled_attempts": attempts,
        "canonical_evidence": _canonical_evidence(attempts=attempts, model=model),
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
        "leak_marker_match_count": sum(
            int(row.get("leak_marker_match_count") or 0) for row in rows
        ),
        "attempt_run_dirs": [
            str(row["lm8f_run_dir"]) for row in rows if row.get("lm8f_run_dir")
        ],
        "worker_action_values": [
            row["worker_action_value"]
            for row in rows
            if isinstance(row.get("worker_action_value"), (int, float))
            and not isinstance(row.get("worker_action_value"), bool)
        ],
        "verifier_attempt_counts": [
            row["verifier_attempt_count"]
            for row in rows
            if isinstance(row.get("verifier_attempt_count"), int)
            and not isinstance(row.get("verifier_attempt_count"), bool)
        ],
    }


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
    run_subprocess=None,
) -> Path:
    runner = run_subprocess or subprocess.run
    run_dir = _new_run_dir(run_root)
    lm8f_runs_dir = run_dir / "lm8f_runs"
    lm8f_runs_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "manifest.json", _manifest(attempts=attempts, model=model))

    rows: list[dict[str, Any]] = []
    for attempt_index in range(1, attempts + 1):
        before = set(lm8f_runs_dir.glob("lm8f-*"))
        command = _lm8f_command(model=model, lm8f_runs_dir=lm8f_runs_dir)
        try:
            completed = runner(
                command,
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=attempt_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            child_run_dirs = _discover_child_run_dirs(lm8f_runs_dir, before)
            row = _timeout_row(
                attempt_index=attempt_index,
                exc=exc,
                child_run_dirs=child_run_dirs,
            )
        except Exception as exc:
            child_run_dirs = _discover_child_run_dirs(lm8f_runs_dir, before)
            row = _subprocess_error_row(
                attempt_index=attempt_index,
                exc=exc,
                child_run_dirs=child_run_dirs,
            )
        else:
            child_run_dirs = _discover_child_run_dirs(lm8f_runs_dir, before)
            row = _row_from_completed_lm8f(
                attempt_index=attempt_index,
                completed=completed,
                child_run_dirs=child_run_dirs,
            )
        _copy_child_artifact_summaries(row)
        _apply_leak_scan(row)
        rows.append(row)
        _append_jsonl(run_dir / "attempts.jsonl", row)

    _write_json(
        run_dir / "summary.json",
        _build_summary(rows, attempts=attempts, model=model),
    )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    run_dir = _run_probe(
        attempts=args.attempts,
        model=args.model,
        run_root=args.run_dir,
        attempt_timeout_s=args.attempt_timeout_s,
    )
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    print(
        "LM8G scalar transform repeatability probe complete "
        f"run_dir={run_dir} "
        f"accepted={summary.get('accepted_count')} "
        f"scheduled={summary.get('scheduled_attempts')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
