# LM6C Repeatability Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic LM6C wrapper that runs scheduled LM6A repeatability attempts with explicit live preflight accounting, without changing the frozen LM6B protocol.

**Architecture:** Add one script-local measurement harness, `scripts/lm6c_repeatability_probe.py`, that owns preflight calls, LM6A subprocess invocation, terminal classification, leak-marker summaries, and combined artifacts. The wrapper treats LM6A as a child process, discovers child run directories from the filesystem, and never imports or mutates LM6A internals. Tests monkeypatch preflight/subprocess/filesystem seams and require no Rhino, Grasshopper, Ollama, or live model.

**Tech Stack:** Python 3.10 standard library (`argparse`, `json`, `subprocess`, `sys`, `datetime`, `pathlib`, `hashlib`), existing PowerShell/pytest verification, no new dependencies.

---

## Files

Create:

- `scripts/lm6c_repeatability_probe.py`
- `mcp_server/tests/test_lm6c_repeatability_probe.py`

Already created in spec phase:

- `docs/superpowers/specs/2026-07-06-lm6c-repeatability-probe-design.md`

Create in planning phase:

- `docs/superpowers/plans/2026-07-06-lm6c-repeatability-probe.md`

Allowed only if a test proves a real blocker:

- `scripts/lm6a_live_worker_splice_probe.py` for a tiny CLI/run-dir compatibility fix

Do not modify:

- production `mcp_server/src/**`
- LM5/LM6 prompt text
- LM6A behavior, unless the allowed compatibility exception is proven
- raw `probe_runs/**`

## Design Notes

The wrapper should be implemented as mostly pure helpers plus a small CLI:

```python
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
```

Use this shape for attempt rows:

```python
{
    "attempt_index": 1,
    "scheduled_attempt_id": "attempt-001",
    "preflight_status": "passed",
    "lm6a_invoked": True,
    "lm6a_returncode": 0,
    "lm6a_run_dir": "probe_runs/lm6c-.../lm6a_runs/lm6a-...",
    "lm6a_decision": "accepted",
    "lm6a_reason": "verify_repair_succeeded",
    "terminal_category": "accepted",
    "stdout_excerpt": "...",
    "stderr_excerpt": "",
    "failure_reason": None,
    "leak_check_performed": True,
    "leak_marker_matches": [],
    "leak_marker_match_count": 0,
}
```

Use this summary shape:

```python
{
    "schema": SCRIPT_SCHEMA,
    "scheduled_attempts": 5,
    "terminal_category_counts": {"accepted": 5},
    "preflight_failed_count": 0,
    "lm6a_invoked_count": 5,
    "gate_failed_count": 0,
    "worker_reached_count": 5,
    "worker_terminal_counts": {"accepted": 5},
    "accepted_count": 5,
    "leak_marker_match_count": 0,
    "attempt_run_dirs": ["probe_runs/lm6c-.../lm6a_runs/lm6a-..."],
    "canonical_evidence": True,
}
```

Preflight should use the live Rook tool executor through a small wrapper function that tests can monkeypatch:

```python
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
```

Keep `_tool_result_ok(...)` conservative. It should accept normal Rook tool responses that are mappings without an obvious failure marker:

```python
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
```

This is only preflight health, not protocol semantics.

## Task 1: CLI, Run Directory, JSONL, and Summary Skeleton

**Files:**

- Create: `scripts/lm6c_repeatability_probe.py`
- Create: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Write failing tests for CLI defaults and validation**

Create `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm6c_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm6c_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical() -> None:
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600


def test_cli_rejects_non_positive_attempts() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--attempts", "0"])


def test_canonical_evidence_only_for_five_gemma_qat_attempts() -> None:
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=1, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=5, model="qwen3:14b") is False
```

- [ ] **Step 2: Run tests and verify they fail because the script is missing**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
FileNotFoundError or import failure for scripts/lm6c_repeatability_probe.py
```

- [ ] **Step 3: Add the minimal script with CLI helpers**

Create `scripts/lm6c_repeatability_probe.py`:

```python
#!/usr/bin/env python
"""LM6C repeatability wrapper for the frozen LM6A live splice protocol."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
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
```

- [ ] **Step 4: Run Task 1 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
git commit -m "test(lm6c): add repeatability wrapper skeleton"
```

## Task 2: Preflight Accounting

**Files:**

- Modify: `scripts/lm6c_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add failing tests for preflight pass/fail behavior**

Append to `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
def test_tool_result_ok_accepts_successful_mapping() -> None:
    assert PROBE._tool_result_ok({"ok": True}) is True
    assert PROBE._tool_result_ok({"status": "ready"}) is True


def test_tool_result_ok_rejects_failure_shapes() -> None:
    assert PROBE._tool_result_ok(None) is False
    assert PROBE._tool_result_ok({"ok": False}) is False
    assert PROBE._tool_result_ok({"success": False}) is False
    assert PROBE._tool_result_ok({"status": "error"}) is False
    assert PROBE._tool_result_ok({"status": "failed"}) is False
    assert PROBE._tool_result_ok({"error": "bad"}) is False
    assert PROBE._tool_result_ok({"errors": ["bad"]}) is False


def test_preflight_failed_row_does_not_invoke_lm6a() -> None:
    row = PROBE._preflight_failed_row(
        attempt_index=1,
        reason="gh_document_new_failed",
    )

    assert row["attempt_index"] == 1
    assert row["scheduled_attempt_id"] == "attempt-001"
    assert row["preflight_status"] == "failed"
    assert row["lm6a_invoked"] is False
    assert row["lm6a_returncode"] is None
    assert row["lm6a_run_dir"] is None
    assert row["lm6a_decision"] is None
    assert row["lm6a_reason"] is None
    assert row["terminal_category"] == "preflight_failed"
    assert row["failure_reason"] == "gh_document_new_failed"
    assert row["leak_check_performed"] is False
    assert row["leak_marker_match_count"] == 0
```

- [ ] **Step 2: Run tests and verify the new tests fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
FAIL for missing _tool_result_ok and _preflight_failed_row
```

- [ ] **Step 3: Implement preflight helpers and row constructor**

Append to `scripts/lm6c_repeatability_probe.py` after `_excerpt(...)`:

```python
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
```

- [ ] **Step 4: Run Task 2 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
6 passed
```

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
git commit -m "feat(lm6c): account for live preflight"
```

## Task 3: LM6A Child Run Discovery and Decision Classification

**Files:**

- Modify: `scripts/lm6c_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add failing tests for child run discovery and terminal classification**

Append to `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
def test_discover_child_run_dir_uses_new_directory_not_stdout(tmp_path: Path) -> None:
    runs = tmp_path / "lm6a_runs"
    runs.mkdir()
    before = set(runs.glob("lm6a-*"))
    child = runs / "lm6a-20260706T000000Z-abc123"
    child.mkdir()

    assert PROBE._discover_child_run_dir(runs, before) == child


def test_discover_child_run_dir_rejects_missing_or_ambiguous(tmp_path: Path) -> None:
    runs = tmp_path / "lm6a_runs"
    runs.mkdir()
    before = set(runs.glob("lm6a-*"))
    assert PROBE._discover_child_run_dir(runs, before) is None
    (runs / "lm6a-a").mkdir()
    (runs / "lm6a-b").mkdir()
    assert PROBE._discover_child_run_dir(runs, before) is None


def test_classify_decision_preserves_lm6a_terminal_categories() -> None:
    assert PROBE._classify_decision({"decision": "accepted"}) == (
        "accepted",
        None,
    )
    assert PROBE._classify_decision({"decision": "gate_failed"}) == (
        "gate_failed",
        None,
    )
    assert PROBE._classify_decision({"decision": "publication_failed"}) == (
        "publication_failed",
        None,
    )


def test_classify_decision_rejects_unknown_decision() -> None:
    assert PROBE._classify_decision({"decision": "strange"}) == (
        "wrapper_error",
        "lm6a_unknown_decision:strange",
    )
    assert PROBE._classify_decision({}) == (
        "wrapper_error",
        "lm6a_missing_decision",
    )
```

- [ ] **Step 2: Run tests and verify failures**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
FAIL for missing _discover_child_run_dir and _classify_decision
```

- [ ] **Step 3: Implement child run discovery and classification**

Append to `scripts/lm6c_repeatability_probe.py`:

```python
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
```

- [ ] **Step 4: Run Task 3 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
10 passed
```

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
git commit -m "feat(lm6c): classify lm6a child runs"
```

## Task 4: Subprocess Attempt Rows and Wrapper Errors

**Files:**

- Modify: `scripts/lm6c_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add failing tests for subprocess outcomes**

Append to `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
import subprocess


def test_attempt_row_for_nonzero_lm6a_returncode(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        '{"decision": "accepted", "reason": "verify_repair_succeeded"}',
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="some stdout",
        stderr="some stderr",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm6a_nonzero_returncode:2"
    assert row["lm6a_returncode"] == 2
    assert row["lm6a_invoked"] is True
    assert row["lm6a_run_dir"] == str(child)


def test_attempt_row_for_missing_decision_json(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="done",
        stderr="",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm6a_missing_decision_json"


def test_attempt_row_for_non_mapping_decision_json(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        '["not", "a", "mapping"]',
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="done",
        stderr="",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm6a_decision_not_mapping"


def test_attempt_row_for_successful_lm6a_decision(tmp_path: Path) -> None:
    child = tmp_path / "lm6a_runs" / "lm6a-child"
    child.mkdir(parents=True)
    (child / "decision.json").write_text(
        '{"decision": "accepted", "reason": "verify_repair_succeeded"}',
        encoding="utf-8",
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="x" * 2500,
        stderr="",
    )

    row = PROBE._row_from_completed_lm6a(
        attempt_index=1,
        completed=completed,
        child_run_dir=child,
    )

    assert row["terminal_category"] == "accepted"
    assert row["lm6a_decision"] == "accepted"
    assert row["lm6a_reason"] == "verify_repair_succeeded"
    assert len(row["stdout_excerpt"]) == 2000
```

- [ ] **Step 2: Run tests and verify failures**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
FAIL for missing _row_from_completed_lm6a
```

- [ ] **Step 3: Implement subprocess row conversion**

Append to `scripts/lm6c_repeatability_probe.py`:

```python
def _read_decision(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "lm6a_missing_decision_json"
    except json.JSONDecodeError as exc:
        return None, f"lm6a_invalid_decision_json:{exc.__class__.__name__}"
    if not isinstance(payload, dict):
        return None, "lm6a_decision_not_mapping"
    return payload, None


def _row_from_completed_lm6a(
    *,
    attempt_index: int,
    completed: subprocess.CompletedProcess[str],
    child_run_dir: Path | None,
) -> dict[str, Any]:
    row = _base_attempt_row(attempt_index=attempt_index)
    row.update(
        {
            "preflight_status": "passed",
            "lm6a_invoked": True,
            "lm6a_returncode": completed.returncode,
            "lm6a_run_dir": str(child_run_dir) if child_run_dir is not None else None,
            "stdout_excerpt": _excerpt(completed.stdout),
            "stderr_excerpt": _excerpt(completed.stderr),
        }
    )
    if completed.returncode != 0:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = f"lm6a_nonzero_returncode:{completed.returncode}"
        return row
    if child_run_dir is None:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = "lm6a_child_run_dir_not_found"
        return row
    decision, error = _read_decision(child_run_dir / "decision.json")
    if error is not None:
        row["terminal_category"] = "wrapper_error"
        row["failure_reason"] = error
        return row
    terminal_category, failure_reason = _classify_decision(decision)
    row.update(
        {
            "lm6a_decision": decision.get("decision"),
            "lm6a_reason": decision.get("reason"),
            "terminal_category": terminal_category,
            "failure_reason": failure_reason,
        }
    )
    return row
```

- [ ] **Step 4: Run Task 4 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
14 passed
```

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
git commit -m "feat(lm6c): record lm6a subprocess outcomes"
```

## Task 5: Leak Marker Scanning

**Files:**

- Modify: `scripts/lm6c_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add failing tests for report-only leak scanning**

Append to `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
def test_leak_scan_reports_markers_without_changing_decision(tmp_path: Path) -> None:
    child = tmp_path / "lm6a-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        '{"code": "A = 42.0;", "name": "PROBE_REPAIR_CODE"}',
        encoding="utf-8",
    )
    (child / "nested").mkdir()
    (child / "nested" / "decision.json").write_text(
        '{"note": "BindStepSpec.base_params.code"}',
        encoding="utf-8",
    )

    matches = PROBE._scan_leak_markers(child)

    assert len(matches) == 3
    assert {match["marker"] for match in matches} == {
        "A = 42.0",
        "PROBE_REPAIR_CODE",
        "BindStepSpec.base_params.code",
    }


def test_apply_leak_scan_updates_row_report_only(tmp_path: Path) -> None:
    child = tmp_path / "lm6a-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        '{"code": "A = 42.0;"}',
        encoding="utf-8",
    )
    row = PROBE._base_attempt_row(attempt_index=1)
    row["terminal_category"] = "accepted"
    row["lm6a_run_dir"] = str(child)

    PROBE._apply_leak_scan(row)

    assert row["terminal_category"] == "accepted"
    assert row["leak_check_performed"] is True
    assert row["leak_marker_match_count"] == 1
```

- [ ] **Step 2: Run tests and verify failures**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
FAIL for missing _scan_leak_markers and _apply_leak_scan
```

- [ ] **Step 3: Implement report-only leak scanning**

Append to `scripts/lm6c_repeatability_probe.py`:

```python
def _scan_leak_markers(run_dir: Path) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if not run_dir.exists():
        return matches
    for path in sorted(run_dir.rglob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
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
```

- [ ] **Step 4: Run Task 5 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
16 passed
```

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
git commit -m "feat(lm6c): summarize leak markers"
```

## Task 6: Summary Aggregation

**Files:**

- Modify: `scripts/lm6c_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add failing tests for summary aggregation and denominators**

Append to `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
def test_build_summary_separates_scheduled_and_worker_denominators() -> None:
    rows = [
        {
            **PROBE._base_attempt_row(attempt_index=1),
            "terminal_category": "accepted",
            "lm6a_invoked": True,
            "lm6a_run_dir": "run-a",
            "leak_marker_match_count": 0,
        },
        {
            **PROBE._base_attempt_row(attempt_index=2),
            "terminal_category": "gate_failed",
            "lm6a_invoked": True,
            "lm6a_run_dir": "run-b",
            "leak_marker_match_count": 1,
        },
        {
            **PROBE._base_attempt_row(attempt_index=3),
            "terminal_category": "preflight_failed",
            "lm6a_invoked": False,
            "leak_marker_match_count": 0,
        },
        {
            **PROBE._base_attempt_row(attempt_index=4),
            "terminal_category": "wrapper_error",
            "lm6a_invoked": True,
            "leak_marker_match_count": 0,
        },
        {
            **PROBE._base_attempt_row(attempt_index=5),
            "terminal_category": "worker_declined",
            "lm6a_invoked": True,
            "lm6a_run_dir": "run-e",
            "leak_marker_match_count": 0,
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=5,
        model="gemma4:12b-it-qat",
    )

    assert summary["scheduled_attempts"] == 5
    assert summary["terminal_category_counts"] == {
        "accepted": 1,
        "gate_failed": 1,
        "preflight_failed": 1,
        "worker_declined": 1,
        "wrapper_error": 1,
    }
    assert summary["preflight_failed_count"] == 1
    assert summary["lm6a_invoked_count"] == 4
    assert summary["gate_failed_count"] == 1
    assert summary["worker_reached_count"] == 2
    assert summary["worker_terminal_counts"] == {
        "accepted": 1,
        "worker_declined": 1,
    }
    assert summary["accepted_count"] == 1
    assert summary["leak_marker_match_count"] == 1
    assert summary["attempt_run_dirs"] == ["run-a", "run-b", "run-e"]
    assert summary["canonical_evidence"] is True
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
FAIL for missing _build_summary
```

- [ ] **Step 3: Implement summary aggregation**

Append to `scripts/lm6c_repeatability_probe.py`:

```python
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
```

- [ ] **Step 4: Run Task 6 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
17 passed
```

- [ ] **Step 5: Commit Task 6**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
git commit -m "feat(lm6c): aggregate repeatability outcomes"
```

## Task 7: Orchestration Without Live Dependencies In Tests

**Files:**

- Modify: `scripts/lm6c_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add failing orchestration tests using monkeypatches**

Append to `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
def test_run_probe_records_preflight_failure_without_lm6a(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def fake_preflight():
        return False, "rhino_ping_failed"

    monkeypatch.setattr(PROBE, "_run_preflight", fake_preflight)

    run_dir = PROBE._run_probe(
        attempts=1,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("LM6A should not be invoked")
        ),
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["terminal_category"] == "preflight_failed"
    assert rows[0]["lm6a_invoked"] is False
    assert summary["preflight_failed_count"] == 1
    assert summary["lm6a_invoked_count"] == 0


def test_run_probe_invokes_lm6a_after_preflight(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def fake_preflight():
        return True, None

    def fake_run_subprocess(command, **kwargs):
        lm6a_runs_dir = Path(command[-1])
        child = lm6a_runs_dir / "lm6a-child"
        child.mkdir(parents=True)
        (child / "decision.json").write_text(
            '{"decision": "accepted", "reason": "verify_repair_succeeded"}',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="LM6A complete",
            stderr="",
        )

    monkeypatch.setattr(PROBE, "_run_preflight", fake_preflight)

    run_dir = PROBE._run_probe(
        attempts=1,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_run_subprocess,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["terminal_category"] == "accepted"
    assert rows[0]["lm6a_invoked"] is True
    assert summary["accepted_count"] == 1
    assert summary["worker_reached_count"] == 1


def test_run_probe_timeout_discovers_child_run_and_scans_leaks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    async def fake_preflight():
        return True, None

    def fake_run_subprocess(command, **kwargs):
        lm6a_runs_dir = Path(command[-1])
        child = lm6a_runs_dir / "lm6a-child"
        child.mkdir(parents=True)
        (child / "worker_action.json").write_text(
            '{"code": "A = 42.0;"}',
            encoding="utf-8",
        )
        raise subprocess.TimeoutExpired(
            cmd=command,
            timeout=kwargs["timeout"],
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(PROBE, "_run_preflight", fake_preflight)

    run_dir = PROBE._run_probe(
        attempts=1,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_run_subprocess,
    )

    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["terminal_category"] == "wrapper_error"
    assert rows[0]["failure_reason"] == "lm6a_timeout"
    assert rows[0]["lm6a_run_dir"].endswith("lm6a-child")
    assert rows[0]["leak_check_performed"] is True
    assert rows[0]["leak_marker_match_count"] == 1
    assert summary["terminal_category_counts"] == {"wrapper_error": 1}
    assert summary["leak_marker_match_count"] == 1
```

- [ ] **Step 2: Run tests and verify orchestration failures**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
FAIL for missing _run_probe
```

- [ ] **Step 3: Implement orchestration**

Append to `scripts/lm6c_repeatability_probe.py`:

```python
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


def _run_probe(
    *,
    attempts: int,
    model: str,
    run_root: str | Path,
    attempt_timeout_s: int,
    run_subprocess=subprocess.run,
) -> Path:
    run_dir = _new_run_dir(run_root)
    lm6a_runs_dir = run_dir / "lm6a_runs"
    lm6a_runs_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "manifest.json", _manifest(attempts=attempts, model=model))

    rows: list[dict[str, Any]] = []
    attempts_path = run_dir / "attempts.jsonl"
    for attempt_index in range(1, attempts + 1):
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
            row = _base_attempt_row(attempt_index=attempt_index)
            row.update(
                {
                    "preflight_status": "passed",
                    "lm6a_invoked": True,
                    "lm6a_run_dir": str(child_run_dir)
                    if child_run_dir is not None
                    else None,
                    "terminal_category": "wrapper_error",
                    "stdout_excerpt": _excerpt(exc.stdout if isinstance(exc.stdout, str) else ""),
                    "stderr_excerpt": _excerpt(exc.stderr if isinstance(exc.stderr, str) else ""),
                    "failure_reason": "lm6a_timeout",
                }
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
```

- [ ] **Step 4: Run Task 7 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
20 passed
```

- [ ] **Step 5: Commit Task 7**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
git commit -m "feat(lm6c): orchestrate repeatability attempts"
```

## Task 8: CLI Main and Final Static Guards

**Files:**

- Modify: `scripts/lm6c_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm6c_repeatability_probe.py`

- [ ] **Step 1: Add final tests for CLI main and forbidden scope drift**

Append to `mcp_server/tests/test_lm6c_repeatability_probe.py`:

```python
def test_main_prints_run_dir(monkeypatch, tmp_path: Path, capsys) -> None:
    def fake_run_probe(**kwargs):
        run_dir = tmp_path / "lm6c-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            '{"terminal_category_counts": {"accepted": 1}}',
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--attempts", "1", "--run-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "LM6C repeatability probe complete" in output
    assert f"run_dir={tmp_path / 'lm6c-demo'}" in output


def test_lm6c_script_does_not_import_lm6a_internals() -> None:
    source = PROBE._script_path().read_text(encoding="utf-8")

    assert "import lm6a_live_worker_splice_probe" not in source
    assert "from lm6a_live_worker_splice_probe" not in source
    assert "_run_probe(" in source
    assert "subprocess.run" in source
```

- [ ] **Step 2: Add script path helper and main**

Append to `scripts/lm6c_repeatability_probe.py`:

```python
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
        f"run_dir={run_dir} terminal_category_counts="
        f"{summary['terminal_category_counts']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run LM6C targeted tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q
```

Expected:

```text
22 passed
```

- [ ] **Step 4: Run nearby no-live seam gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 5: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py
```

Expected:

```text
exit code 0
```

- [ ] **Step 6: Run final static scope checks**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
git status --short --branch
```

Expected diff scope:

```text
docs/superpowers/specs/2026-07-06-lm6c-repeatability-probe-design.md
docs/superpowers/plans/2026-07-06-lm6c-repeatability-probe.md
scripts/lm6c_repeatability_probe.py
mcp_server/tests/test_lm6c_repeatability_probe.py
```

Expected status may still show unrelated local dirt:

```text
 M knowledge/gh/operations_knowledge.json
?? .understand-anything/
?? docs/superpowers/plans/2026-07-04-rook2-minimal-base-roadmap.md
?? docs/superpowers/probes/2026-07-04-rook20-v01-hermes-plugin-validation.md
?? docs/superpowers/specs/2026-07-03-rook-2.0-minimal-iteration-design.md
```

Do not stage those unrelated files.

- [ ] **Step 7: Commit Task 8**

Run:

```powershell
git add scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  docs\superpowers\plans\2026-07-06-lm6c-repeatability-probe.md
git commit -m "feat(lm6c): add repeatability wrapper"
```

## Task 9: PR-Ready Review Checklist

**Files:**

- No new edits expected

- [ ] **Step 1: Confirm no live run was executed**

Run:

```powershell
git status --short --ignored probe_runs
```

Expected:

```text
probe_runs/ appears ignored only if local artifacts already exist; no probe_runs path appears in git diff --name-only main..HEAD
```

- [ ] **Step 2: Re-run final verification if any file changed after Task 8**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  -q

py -3.10 -m py_compile `
  scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py

git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected:

```text
all selected tests pass
compile exits 0
diff-check exits 0
diff scope matches Task 8 expected scope
```

- [ ] **Step 3: Prepare PR summary**

Use this PR summary:

```markdown
## Summary
- Add the LM6C repeatability wrapper script for five scheduled LM6A attempts.
- Record explicit preflight, LM6A child-run, terminal-category, denominator, and leak-marker accounting.
- Keep LM6A and the frozen LM6B protocol unchanged; no live run in this PR.

## Verification
- `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm6c_repeatability_probe.py mcp_server\tests\test_lm6a_live_worker_splice_probe.py mcp_server\tests\test_lm_worker_two_pass_publication.py mcp_server\tests\test_plan_graph_worker_action_apply.py -q`
- `py -3.10 -m py_compile scripts\lm6c_repeatability_probe.py mcp_server\tests\test_lm6c_repeatability_probe.py`
- `git diff --check main..HEAD`

## Notes
- No live LM6C run was performed.
- `probe_runs/` artifacts remain local/ignored.
```

## Plan Self-Review

Spec coverage:

- Five independent scheduled attempts: Task 7 orchestration.
- Fresh `rhino_ping` + `gh_document_new`: Task 2 preflight and Task 7 orchestration.
- No replacement attempts: Task 7 loops exactly `attempts` times.
- Split denominators: Task 6 summary.
- `preflight_failed`, `gate_failed`, worker decisions, `wrapper_error`: Tasks 2, 3, 4, 6.
- `sys.executable` LM6A invocation: Task 7 `_lm6a_command`.
- Nonzero LM6A return code: Task 4.
- Child run discovery from filesystem, not stdout: Task 3.
- Report-only leak checks: Task 5.
- No live dependencies in tests: every test uses local helpers, temp dirs, monkeypatches, or fake subprocesses.
- No live run in PR: Task 9.

Placeholder scan:

- No `TBD`, `TODO`, or vague "add tests" steps are intentionally present.

Type consistency:

- `terminal_category` values match the spec.
- `attempt_timeout_s` uses integer seconds consistently.
- `lm6a_run_dir` is string-or-null in rows and string list in summaries.
