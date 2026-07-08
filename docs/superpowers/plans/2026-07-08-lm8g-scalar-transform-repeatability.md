# LM8G Scalar Transform Repeatability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic N=5 repeatability wrapper around the existing LM8F scalar transform live probe.

**Architecture:** LM8G is a subprocess scheduler and accountant, not a second LM8F implementation path. It invokes `scripts/lm8f_scalar_transform_depth_probe.py` with `sys.executable`, discovers the child `lm8f-*` run dir from the filesystem, reads child artifacts, classifies one scheduled attempt row, and writes aggregate repeatability summaries. LM8F owns all live behavior; LM8G owns only scheduling, child-run discovery, classification, bounded diagnostics, leak scans, and summary accounting.

**Tech Stack:** Python 3.10, pytest, `subprocess.run`, JSON/JSONL probe artifacts, existing LM8F CLI surface.

## Global Constraints

- New implementation files are limited to `scripts/lm8g_scalar_transform_repeatability_probe.py` and `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`.
- No LM8F behavior changes unless tests expose a tiny CLI/run-dir compatibility bug; current expected path requires no LM8F change.
- No imports from `scripts/lm8f_scalar_transform_depth_probe.py`.
- No live Rhino/GH run in the implementation PR.
- Tests must use fake subprocess runners and synthetic child run dirs; no Rhino, Grasshopper, Ollama, or live model dependency.
- LM8G invokes LM8F via `sys.executable`.
- Default attempts is `5`; attempts must be a positive integer.
- Default model is `gemma4:12b-it-qat`.
- Default run root is `probe_runs`.
- Default per-attempt timeout is `600` seconds.
- `canonical_evidence` is true only when `attempts == 5` and `model == "gemma4:12b-it-qat"`.
- LM8G must not run separate `rhino_ping` or `gh_document_new`; LM8F owns preflight and fresh GH document setup.
- LM8G must not replace failed attempts.
- LM8G must not alter child LM8F terminal decisions based on marker scans.
- LM8G must not add retry, Planner, `gh_edit`, request override, or scenario-selection flags.
- LM8G must not store full stdout/stderr; attempt rows store bounded excerpts only.

---

## File Structure

Create:

- `scripts/lm8g_scalar_transform_repeatability_probe.py`
  - CLI parsing, manifest/run-dir helpers, LM8F subprocess command builder, child-run discovery, child artifact readers, attempt row classification, report-only leak scan, summary accounting, JSON/JSONL writers, and `main(...)`.

- `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`
  - Imports the script as a module.
  - Uses fake subprocess runners and synthetic child LM8F run dirs.
  - Verifies CLI, command shape, filesystem child discovery, classification, wrapper errors, leak scan, summary accounting, and integration artifact writing.

Do not modify:

- `scripts/lm8f_scalar_transform_depth_probe.py`
- `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- `scripts/lm6c_repeatability_probe.py`
- `scripts/lm_worker_two_pass_publication.py`
- `mcp_server/src/rook/**/*.py`
- existing LM8F tests except for import-only compatibility if implementation proves unavoidable

---

### Task 1: CLI, Manifest, Run Directory, And Command Builder

**Files:**
- Create: `scripts/lm8g_scalar_transform_repeatability_probe.py`
- Create: `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`

**Interfaces:**
- Produces constants:
  - `SCRIPT_SCHEMA = "rook.lm8g_scalar_transform_repeatability_probe:v1"`
  - `DEFAULT_ATTEMPTS = 5`
  - `DEFAULT_MODEL = "gemma4:12b-it-qat"`
  - `DEFAULT_RUN_DIR = "probe_runs"`
  - `DEFAULT_ATTEMPT_TIMEOUT_S = 600`
  - `EXCERPT_CHARS = 2000`
- Produces functions:
  - `_args(argv: list[str] | None) -> argparse.Namespace`
  - `_positive_int(raw: str) -> int`
  - `_canonical_evidence(*, attempts: int, model: str) -> bool`
  - `_git_short_sha() -> str`
  - `_new_run_dir(run_root: str | Path) -> Path`
  - `_manifest(*, attempts: int, model: str) -> dict[str, Any]`
  - `_lm8f_command(*, model: str, lm8f_runs_dir: Path) -> list[str]`

- [ ] **Step 1: Write failing CLI and command tests**

Create `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm8g_scalar_transform_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8g_scalar_transform_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_lm8g_shape():
    args = PROBE._args([])

    assert args.attempts == 5
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600
    assert PROBE._canonical_evidence(attempts=args.attempts, model=args.model) is True


def test_cli_rejects_non_positive_attempts():
    for value in ("0", "-1"):
        with pytest.raises(SystemExit):
            PROBE._args(["--attempts", value])


def test_canonical_evidence_only_for_five_gemma_attempts():
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=1, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=5, model="qwen3:14b") is False


def test_cli_rejects_non_lm8g_surfaces():
    forbidden = (
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
        ["--phase", "receipt_recon"],
    )
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8g_identity():
    manifest = PROBE._manifest(attempts=5, model="gemma4:12b-it-qat")

    assert manifest["schema"] == "rook.lm8g_scalar_transform_repeatability_probe:v1"
    assert manifest["attempts"] == 5
    assert manifest["model"] == "gemma4:12b-it-qat"
    assert manifest["canonical_evidence"] is True


def test_lm8f_command_uses_sys_executable_and_child_run_dir(tmp_path: Path):
    runs_dir = tmp_path / "lm8f_runs"

    command = PROBE._lm8f_command(
        model="gemma4:12b-it-qat",
        lm8f_runs_dir=runs_dir,
    )

    assert command == [
        sys.executable,
        str(Path.cwd() / "scripts" / "lm8f_scalar_transform_depth_probe.py"),
        "--model",
        "gemma4:12b-it-qat",
        "--run-dir",
        str(runs_dir),
    ]
    assert "--retry-clean-observation" not in command
    assert "--gh-edit" not in command
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: import failure because `scripts/lm8g_scalar_transform_repeatability_probe.py` does not exist.

- [ ] **Step 3: Implement CLI and command scaffold**

Create `scripts/lm8g_scalar_transform_repeatability_probe.py` with:

```python
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
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: the Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add scripts\lm8g_scalar_transform_repeatability_probe.py mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py
git commit -m "feat(lm8g): scaffold scalar repeatability wrapper"
```

---

### Task 2: Child Run Discovery And Decision Classification

**Files:**
- Modify: `scripts/lm8g_scalar_transform_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`

**Interfaces:**
- Produces:
  - `_scheduled_attempt_id(attempt_index: int) -> str`
  - `_base_attempt_row(*, attempt_index: int) -> dict[str, Any]`
  - `_discover_child_run_dirs(lm8f_runs_dir: Path, before: set[Path]) -> list[Path]`
  - `_read_decision(path: Path) -> tuple[dict[str, Any] | None, str | None]`
  - `_classify_decision(decision: Mapping[str, Any]) -> tuple[str, str | None]`

- [ ] **Step 1: Add failing tests for discovery and decision classification**

Append:

```python
def test_scheduled_attempt_id_is_stable():
    assert PROBE._scheduled_attempt_id(1) == "attempt-001"
    assert PROBE._scheduled_attempt_id(12) == "attempt-012"


def test_base_attempt_row_has_lm8g_fields():
    row = PROBE._base_attempt_row(attempt_index=1)

    assert row["attempt_index"] == 1
    assert row["scheduled_attempt_id"] == "attempt-001"
    assert row["lm8f_invoked"] is False
    assert row["lm8f_returncode"] is None
    assert row["lm8f_run_dir"] is None
    assert row["terminal_category"] is None
    assert row["leak_check_performed"] is False
    assert row["leak_marker_match_count"] == 0


def test_discover_child_run_dirs_uses_filesystem_delta(tmp_path: Path):
    runs_dir = tmp_path / "lm8f_runs"
    runs_dir.mkdir()
    existing = runs_dir / "lm8f-existing"
    existing.mkdir()
    before = set(runs_dir.glob("lm8f-*"))
    child = runs_dir / "lm8f-new"
    child.mkdir()

    assert PROBE._discover_child_run_dirs(runs_dir, before) == [child]


def test_read_decision_handles_missing_invalid_and_non_mapping(tmp_path: Path):
    missing, missing_error = PROBE._read_decision(tmp_path / "missing.json")
    assert missing is None
    assert missing_error == "lm8f_missing_decision_json"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{bad", encoding="utf-8")
    invalid, invalid_error = PROBE._read_decision(invalid_path)
    assert invalid is None
    assert invalid_error == "lm8f_invalid_decision_json"

    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    non_mapping, non_mapping_error = PROBE._read_decision(list_path)
    assert non_mapping is None
    assert non_mapping_error == "lm8f_decision_not_mapping"


def test_classify_decision_preserves_known_lm8f_categories():
    for decision in (
        "accepted",
        "rejected",
        "worker_declined",
        "publication_failed",
        "gate_failed",
        "preflight_failed",
    ):
        assert PROBE._classify_decision({"decision": decision}) == (decision, None)


def test_classify_decision_rejects_unknown_or_missing_value():
    assert PROBE._classify_decision({}) == (
        "wrapper_error",
        "lm8f_missing_decision",
    )
    assert PROBE._classify_decision({"decision": "strange"}) == (
        "wrapper_error",
        "lm8f_unknown_decision:strange",
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: failures for missing helper functions.

- [ ] **Step 3: Implement discovery and classification helpers**

Add:

```python
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
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: all current LM8G tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add scripts\lm8g_scalar_transform_repeatability_probe.py mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py
git commit -m "feat(lm8g): classify child lm8f decisions"
```

---

### Task 3: Attempt Rows For Completed, Timed Out, And Failed Subprocesses

**Files:**
- Modify: `scripts/lm8g_scalar_transform_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`

**Interfaces:**
- Produces:
  - `_completed_text(value: object) -> str`
  - `_excerpt(text: str | None, *, limit: int = EXCERPT_CHARS) -> str`
  - `_row_from_completed_lm8f(...) -> dict[str, Any]`
  - `_timeout_row(...) -> dict[str, Any]`
  - `_subprocess_error_row(...) -> dict[str, Any]`

- [ ] **Step 1: Add failing tests for completed attempt rows**

Append:

```python
import subprocess


def _write_child_decision(child: Path, payload: dict) -> None:
    child.mkdir(parents=True, exist_ok=True)
    (child / "decision.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def test_row_from_completed_accepted_lm8f_child(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    _write_child_decision(
        child,
        {
            "decision": "accepted",
            "reason": "verify_scalar_output_succeeded",
            "worker_publication_ran": True,
            "live_fixture_created": True,
            "live_set_value_dispatched": True,
            "verify_scalar_output_ran": True,
            "scalar_runtime_ready": True,
            "observed_output_after": 7.5,
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="run_dir=child decision=accepted",
        stderr="",
    )

    row = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["lm8f_invoked"] is True
    assert row["lm8f_returncode"] == 0
    assert row["lm8f_run_dir"] == str(child)
    assert row["lm8f_decision"] == "accepted"
    assert row["lm8f_reason"] == "verify_scalar_output_succeeded"
    assert row["terminal_category"] == "accepted"
    assert row["failure_reason"] is None
    assert row["worker_publication_ran"] is True
    assert row["live_set_value_dispatched"] is True
    assert row["verify_scalar_output_ran"] is True
    assert row["scalar_runtime_ready"] is True
    assert row["observed_output_after"] == 7.5


def test_row_from_completed_nonzero_returncode_is_wrapper_error(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    _write_child_decision(child, {"decision": "accepted"})
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="partial stdout",
        stderr="partial stderr",
    )

    row = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8f_nonzero_returncode:2"
    assert row["child_run_dir_error"] is None
    assert row["lm8f_run_dir"] == str(child)
    assert row["stdout_excerpt"] == "partial stdout"
    assert row["stderr_excerpt"] == "partial stderr"


def test_row_from_completed_nonzero_returncode_keeps_subprocess_reason_if_child_missing():
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="partial stdout",
        stderr="partial stderr",
    )

    row = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8f_nonzero_returncode:2"
    assert row["child_run_dir_error"] == "child_run_dir_missing"
    assert row["lm8f_run_dir"] is None


def test_row_from_completed_missing_and_ambiguous_child_dirs_are_wrapper_errors(tmp_path: Path):
    completed = subprocess.CompletedProcess(args=["python"], returncode=0, stdout="", stderr="")

    missing = PROBE._row_from_completed_lm8f(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[],
    )
    assert missing["terminal_category"] == "wrapper_error"
    assert missing["failure_reason"] == "child_run_dir_missing"

    first = tmp_path / "lm8f-a"
    second = tmp_path / "lm8f-b"
    first.mkdir()
    second.mkdir()
    ambiguous = PROBE._row_from_completed_lm8f(
        attempt_index=2,
        completed=completed,
        child_run_dirs=[first, second],
    )
    assert ambiguous["terminal_category"] == "wrapper_error"
    assert ambiguous["failure_reason"] == "child_run_dir_ambiguous"


def test_timeout_and_subprocess_error_rows_preserve_child_dir_when_present(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    child.mkdir()
    timeout = subprocess.TimeoutExpired(
        cmd=["python"],
        timeout=600,
        output="stdout before timeout",
        stderr="stderr before timeout",
    )

    timeout_row = PROBE._timeout_row(
        attempt_index=1,
        exc=timeout,
        child_run_dirs=[child],
    )
    assert timeout_row["terminal_category"] == "wrapper_error"
    assert timeout_row["failure_reason"] == "lm8f_timeout"
    assert timeout_row["child_run_dir_error"] is None
    assert timeout_row["lm8f_run_dir"] == str(child)

    error_row = PROBE._subprocess_error_row(
        attempt_index=2,
        exc=OSError("launch failed"),
        child_run_dirs=[child],
    )
    assert error_row["terminal_category"] == "wrapper_error"
    assert error_row["failure_reason"] == "lm8f_subprocess_error:OSError"
    assert error_row["child_run_dir_error"] is None
    assert error_row["lm8f_run_dir"] == str(child)


def test_timeout_and_subprocess_error_keep_primary_reason_when_child_missing():
    timeout = subprocess.TimeoutExpired(cmd=["python"], timeout=600)

    timeout_row = PROBE._timeout_row(
        attempt_index=1,
        exc=timeout,
        child_run_dirs=[],
    )
    assert timeout_row["terminal_category"] == "wrapper_error"
    assert timeout_row["failure_reason"] == "lm8f_timeout"
    assert timeout_row["child_run_dir_error"] == "child_run_dir_missing"
    assert timeout_row["lm8f_run_dir"] is None

    error_row = PROBE._subprocess_error_row(
        attempt_index=2,
        exc=OSError("launch failed"),
        child_run_dirs=[],
    )
    assert error_row["terminal_category"] == "wrapper_error"
    assert error_row["failure_reason"] == "lm8f_subprocess_error:OSError"
    assert error_row["child_run_dir_error"] == "child_run_dir_missing"
    assert error_row["lm8f_run_dir"] is None
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: missing row builder functions.

- [ ] **Step 3: Implement row builders**

Add:

```python
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
            "stdout_excerpt": _excerpt(_completed_text(exc.stdout)),
            "stderr_excerpt": _excerpt(_completed_text(exc.stderr)),
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
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: all current tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add scripts\lm8g_scalar_transform_repeatability_probe.py mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py
git commit -m "feat(lm8g): receipt lm8f subprocess outcomes"
```

---

### Task 4: Leak Scan, Child Artifact Summaries, And Aggregate Summary

**Files:**
- Modify: `scripts/lm8g_scalar_transform_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`

**Interfaces:**
- Produces:
  - `_scan_leak_markers(run_dir: Path) -> list[dict[str, Any]]`
  - `_apply_leak_scan(row: dict[str, Any]) -> None`
  - `_read_json_mapping(path: Path) -> Mapping[str, Any] | None`
  - `_copy_child_artifact_summaries(row: dict[str, Any]) -> None`
  - `_build_summary(rows: Sequence[Mapping[str, Any]], *, attempts: int, model: str) -> dict[str, Any]`

- [ ] **Step 1: Add failing tests for marker scan and child summaries**

Append:

```python
def test_leak_scan_reports_markers_without_changing_terminal_category(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    child.mkdir()
    (child / "decision.json").write_text(
        json.dumps({"decision": "accepted", "worker_publication_ran": True}),
        encoding="utf-8",
    )
    (child / "worker_action.json").write_text(
        '{"note": "PROBE_REPAIR_CODE"}',
        encoding="utf-8",
    )
    row = {
        "lm8f_run_dir": str(child),
        "terminal_category": "accepted",
        "leak_check_performed": False,
        "leak_marker_matches": [],
        "leak_marker_match_count": 0,
    }

    PROBE._apply_leak_scan(row)

    assert row["terminal_category"] == "accepted"
    assert row["leak_check_performed"] is True
    assert row["leak_marker_match_count"] == 1
    assert row["leak_marker_matches"][0]["marker"] == "PROBE_REPAIR_CODE"


def test_copy_child_artifact_summaries_reads_worker_value_and_verifier_attempts(tmp_path: Path):
    child = tmp_path / "lm8f-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        json.dumps({"input": {"value": 6.0}}),
        encoding="utf-8",
    )
    (child / "verify_scalar_output_summary.json").write_text(
        json.dumps({"attempt_count": 2}),
        encoding="utf-8",
    )
    row = PROBE._base_attempt_row(attempt_index=1)
    row["lm8f_run_dir"] = str(child)

    PROBE._copy_child_artifact_summaries(row)

    assert row["worker_action_value"] == 6.0
    assert row["verifier_attempt_count"] == 2


def test_build_summary_counts_scheduled_and_worker_denominators(tmp_path: Path):
    rows = [
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "lm8f_run_dir": "run-a",
            "worker_action_value": 6.0,
            "verifier_attempt_count": 1,
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "rejected",
            "worker_publication_ran": True,
            "lm8f_run_dir": "run-b",
            "worker_action_value": 5.5,
            "verifier_attempt_count": 3,
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "gate_failed",
            "worker_publication_ran": False,
            "lm8f_run_dir": "run-c",
            "worker_action_value": None,
            "verifier_attempt_count": None,
            "leak_marker_match_count": 1,
        },
    ]

    summary = PROBE._build_summary(
        rows,
        attempts=5,
        model="gemma4:12b-it-qat",
    )

    assert summary["scheduled_attempts"] == 5
    assert summary["canonical_evidence"] is True
    assert summary["terminal_category_counts"] == {
        "accepted": 1,
        "gate_failed": 1,
        "rejected": 1,
    }
    assert summary["accepted_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["gate_failed_count"] == 1
    assert summary["worker_reached_count"] == 2
    assert summary["worker_terminal_counts"] == {"accepted": 1, "rejected": 1}
    assert summary["leak_marker_match_count"] == 1
    assert summary["attempt_run_dirs"] == ["run-a", "run-b", "run-c"]
    assert summary["worker_action_values"] == [6.0, 5.5]
    assert summary["verifier_attempt_counts"] == [1, 3]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: missing summary helper functions.

- [ ] **Step 3: Implement leak scan and summary helpers**

Add:

```python
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
                matches.append({"path": str(path), "marker": marker})
    return matches


def _apply_leak_scan(row: dict[str, Any]) -> None:
    run_dir = row.get("lm8f_run_dir")
    if not run_dir:
        return
    matches = _scan_leak_markers(Path(str(run_dir)))
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
    action = _read_json_mapping(run_dir / "worker_action.json")
    if action is not None:
        action_input = action.get("input")
        if isinstance(action_input, Mapping):
            value = action_input.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row["worker_action_value"] = value
    verify = _read_json_mapping(run_dir / "verify_scalar_output_summary.json")
    if verify is not None:
        attempt_count = verify.get("attempt_count")
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
    terminal_counts = Counter(str(row.get("terminal_category")) for row in rows)
    worker_rows = [row for row in rows if row.get("worker_publication_ran") is True]
    worker_counts = Counter(str(row.get("terminal_category")) for row in worker_rows)
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
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: all current tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add scripts\lm8g_scalar_transform_repeatability_probe.py mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py
git commit -m "feat(lm8g): summarize child lm8f artifacts"
```

---

### Task 5: Full Wrapper Run, Artifacts, And Main Entrypoint

**Files:**
- Modify: `scripts/lm8g_scalar_transform_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`

**Interfaces:**
- Produces:
  - `_write_json(path: Path, payload: Mapping[str, Any]) -> None`
  - `_append_jsonl(path: Path, payload: Mapping[str, Any]) -> None`
  - `_run_probe(..., run_subprocess: Callable[..., subprocess.CompletedProcess] | None = None) -> Path`
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Add failing integration tests with fake subprocess runner**

Append:

```python
class FakeSubprocessRunner:
    def __init__(self, child_decisions: list[dict]):
        self.child_decisions = list(child_decisions)
        self.calls: list[dict] = []

    def __call__(self, command, *, cwd, capture_output, text, timeout):
        self.calls.append(
            {
                "command": command,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "timeout": timeout,
            }
        )
        run_dir = Path(command[command.index("--run-dir") + 1])
        decision = self.child_decisions.pop(0)
        child = run_dir / f"lm8f-child-{len(self.calls):03d}"
        child.mkdir(parents=True)
        (child / "decision.json").write_text(
            json.dumps(decision, sort_keys=True),
            encoding="utf-8",
        )
        if decision.get("worker_action_value") is not None:
            (child / "worker_action.json").write_text(
                json.dumps({"input": {"value": decision["worker_action_value"]}}),
                encoding="utf-8",
            )
        if decision.get("verifier_attempt_count") is not None:
            (child / "verify_scalar_output_summary.json").write_text(
                json.dumps({"attempt_count": decision["verifier_attempt_count"]}),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=f"run_dir={child}",
            stderr="",
        )


def test_run_probe_writes_manifest_attempts_and_summary(tmp_path: Path):
    runner = FakeSubprocessRunner(
        [
            {
                "decision": "accepted",
                "reason": "verify_scalar_output_succeeded",
                "worker_publication_ran": True,
                "live_fixture_created": True,
                "live_set_value_dispatched": True,
                "verify_scalar_output_ran": True,
                "scalar_runtime_ready": True,
                "observed_output_after": 7.5,
                "worker_action_value": 6.0,
                "verifier_attempt_count": 1,
            },
            {
                "decision": "rejected",
                "reason": "verify_scalar_output_failed",
                "worker_publication_ran": True,
                "worker_action_value": 5.5,
                "verifier_attempt_count": 3,
            },
        ]
    )

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=runner,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert manifest["attempts"] == 2
    assert manifest["canonical_evidence"] is False
    assert [row["terminal_category"] for row in rows] == ["accepted", "rejected"]
    assert rows[0]["worker_action_value"] == 6.0
    assert rows[1]["verifier_attempt_count"] == 3
    assert summary["accepted_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["worker_reached_count"] == 2
    assert summary["worker_action_values"] == [6.0, 5.5]
    assert summary["verifier_attempt_counts"] == [1, 3]
    assert len(runner.calls) == 2
    assert all(call["timeout"] == 600 for call in runner.calls)


def test_run_probe_continues_after_wrapper_error(tmp_path: Path):
    calls = []

    def fake_runner(command, *, cwd, capture_output, text, timeout):
        calls.append(command)
        run_dir = Path(command[command.index("--run-dir") + 1])
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")
        child = run_dir / "lm8f-child-002"
        child.mkdir(parents=True)
        (child / "decision.json").write_text(
            json.dumps({"decision": "accepted", "worker_publication_ran": True}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")

    run_dir = PROBE._run_probe(
        attempts=2,
        model="gemma4:12b-it-qat",
        run_root=tmp_path,
        attempt_timeout_s=600,
        run_subprocess=fake_runner,
    )
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert [row["terminal_category"] for row in rows] == ["wrapper_error", "accepted"]
    assert rows[0]["failure_reason"] == "child_run_dir_missing"
    assert len(calls) == 2


def test_main_prints_run_dir_and_returns_zero(monkeypatch, tmp_path: Path, capsys):
    def fake_run_probe(**kwargs):
        run_dir = tmp_path / "lm8g-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"accepted_count": 1}),
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--attempts", "1", "--run-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "LM8G scalar transform repeatability probe complete" in output
    assert "run_dir=" in output
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: missing `_run_probe` and `main`.

- [ ] **Step 3: Implement writers, run loop, and main**

Add:

```python
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
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    print(
        "LM8G scalar transform repeatability probe complete "
        f"run_dir={run_dir} "
        f"accepted={summary.get('accepted_count')} "
        f"scheduled={summary.get('scheduled_attempts')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: all LM8G tests pass.

- [ ] **Step 5: Commit Task 5**

```powershell
git add scripts\lm8g_scalar_transform_repeatability_probe.py mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py
git commit -m "feat(lm8g): run repeatability attempts"
```

---

### Task 6: Hygiene Guards And Final Verification

**Files:**
- Modify: `mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py`

**Interfaces:**
- Consumes final script.
- Produces verification evidence only.

- [ ] **Step 1: Add static guard tests for LM8G boundaries**

Append:

```python
import inspect


def test_lm8g_source_does_not_import_lm8f_or_live_tooling():
    source = inspect.getsource(PROBE)

    forbidden = (
        "import lm8f_scalar_transform_depth_probe",
        "from lm8f_scalar_transform_depth_probe",
        "_mcp_tool_executor",
        "rhino_ping",
        "gh_document_new",
        "gh_set_value",
        "gh_inspect_output",
        "run_two_pass_worker_publication",
        "apply_gh_scalar_value_action_to_node",
        "--retry-clean-observation",
        "--gh-edit",
        "--planner-provider-command",
    )
    for fragment in forbidden:
        assert fragment not in source


def test_lm8g_source_contains_lm8f_subprocess_script_path_only():
    source = inspect.getsource(PROBE)

    assert "lm8f_scalar_transform_depth_probe.py" in source
    assert "lm8f_scalar_transform_depth_probe" not in source.replace(
        "lm8f_scalar_transform_depth_probe.py",
        "",
    )
```

- [ ] **Step 2: Run focused tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py -q
```

Expected: all LM8G tests pass.

- [ ] **Step 3: Run nearby seam tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Compile scripts and tests**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm8g_scalar_transform_repeatability_probe.py `
  mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py
```

Expected: exit code 0.

- [ ] **Step 5: Check diff hygiene**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected diff scope:

```text
docs/superpowers/plans/2026-07-08-lm8g-scalar-transform-repeatability.md
scripts/lm8g_scalar_transform_repeatability_probe.py
mcp_server/tests/test_lm8g_scalar_transform_repeatability_probe.py
```

The implementation PR should not contain `probe_runs/` artifacts or changes to
`knowledge/gh/operations_knowledge.json`.

- [ ] **Step 6: Commit final hygiene changes**

If Task 6 added only tests:

```powershell
git add mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py
git commit -m "test(lm8g): guard repeatability wrapper boundaries"
```

If no changes remain after verification, do not create an empty commit.

---

## Final Implementation PR Checklist

Before opening or marking the implementation PR ready:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py `
  mcp_server\tests\test_lm8f_scalar_transform_depth_probe.py `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  -q

py -3.10 -m py_compile `
  scripts\lm8g_scalar_transform_repeatability_probe.py `
  mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py

git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected:

```text
all selected tests pass
compile passes
diff-check clean
diff scope limited to LM8G plan/script/tests
no live LM8G run
no probe_runs artifacts committed
no knowledge telemetry drift staged
```

After merge and synced `main`, run one canonical LM8G evidence pass:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8g_scalar_transform_repeatability_probe.py
```

Any scheduled outcome is evidence. Do not replace failed attempts.
