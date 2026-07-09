# LM8J Affine Support Repeatability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/lm8j_affine_support_repeatability_probe.py`, a deterministic N=20 subprocess wrapper that schedules LM8I affine support-enabled attempts and writes repeatability accounting artifacts.

**Architecture:** LM8J is a scheduler and accountant only. It invokes `scripts/lm8i_affine_publication_shape_support_probe.py` as a subprocess, discovers the child `lm8i-*` run directory by filesystem delta, reads child artifacts, classifies terminal outcomes, and writes `manifest.json`, `attempts.jsonl`, and `summary.json`. LM8I continues to own Rhino/GH preflight, affine fixture construction, scalar runtime readiness, worker publication, optional support turn, scalar applier dispatch, verifier settle, and child `decision.json`.

**Tech Stack:** Python 3.10 standard library (`argparse`, `json`, `pathlib`, `subprocess`, `sys`, `collections.Counter`), pytest deterministic fakes, existing `probe_runs/` artifact conventions.

## Global Constraints

- Create `scripts/lm8j_affine_support_repeatability_probe.py`.
- Create `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`.
- LM8J must run LM8I as a subprocess and must not import LM8I internals.
- LM8J must not reimplement LM8I live behavior.
- Canonical attempts are exactly `20`.
- Canonical model is exactly `gemma4:12b-it-qat`.
- Default timeout is exactly `600` seconds per child attempt.
- No replacement attempts.
- No support forcing or support disabling flags.
- No retry flags, Planner flags, `gh_edit` flags, request overrides, or scenario selectors.
- `publication_support_recovered_count` requires `publication_support_attempted == true` and child `worker_action.json` exists.
- Leak marker scanning is report-only and must not change terminal classification.
- Leak markers are exactly `PROBE_REPAIR_CODE`, `A = 42.0`, `BindStepSpec.base_params`, and `repair_same_component.bind.base_params`.
- The affine derived value `3.0` is not a global LM8J leak marker.
- No live LM8J run in the implementation PR.

---

## File Structure

- Create `scripts/lm8j_affine_support_repeatability_probe.py`
  - CLI parsing and canonical evidence flag.
  - LM8J run directory allocation.
  - LM8I subprocess command construction.
  - Filesystem-delta child run discovery.
  - Child `decision.json`, `worker_action.json`, and `verify_scalar_output_summary.json` summarization.
  - Attempt row construction and wrapper error classification.
  - Report-only child artifact marker scanning.
  - `manifest.json`, `attempts.jsonl`, and `summary.json` writers.
  - `main()` entrypoint.

- Create `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`
  - Imports the script with `importlib.util.spec_from_file_location`.
  - Uses synthetic child run directories and fake subprocess runners.
  - Covers CLI, command shape, filesystem discovery, wrapper errors, support counters, marker scanning, summary accounting, and orchestration.

- No expected modification to `scripts/lm8i_affine_publication_shape_support_probe.py`.
  - Only allow a tiny LM8I CLI/run-dir compatibility patch if deterministic tests prove the existing script cannot be invoked as specified.

---

### Task 1: CLI, Identity, And Run Directory Scaffolding

**Files:**
- Create: `scripts/lm8j_affine_support_repeatability_probe.py`
- Create: `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`

**Interfaces:**
- Produces:
  - `SCRIPT_SCHEMA = "rook.lm8j_affine_support_repeatability_probe:v1"`
  - `DEFAULT_ATTEMPTS = 20`
  - `DEFAULT_MODEL = "gemma4:12b-it-qat"`
  - `DEFAULT_RUN_DIR = "probe_runs"`
  - `DEFAULT_ATTEMPT_TIMEOUT_S = 600`
  - `_args(argv: list[str] | None) -> argparse.Namespace`
  - `_canonical_evidence(*, attempts: int, model: str) -> bool`
  - `_git_short_sha() -> str`
  - `_new_run_dir(run_root: str | Path) -> Path`
  - `_manifest(*, attempts: int, model: str) -> dict[str, Any]`
  - `_scheduled_attempt_id(attempt_index: int) -> str`
  - `_base_attempt_row(*, attempt_index: int) -> dict[str, Any>`
- Consumes: no code from later tasks.

- [ ] **Step 1: Write the failing import and CLI tests**

Create `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py` with:

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
        / "lm8j_affine_support_repeatability_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8j_affine_support_repeatability_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_lm8j_shape():
    args = PROBE._args([])

    assert args.attempts == 20
    assert args.model == "gemma4:12b-it-qat"
    assert args.run_dir == "probe_runs"
    assert args.attempt_timeout_s == 600
    assert PROBE._canonical_evidence(attempts=args.attempts, model=args.model) is True


def test_cli_rejects_non_positive_attempts_and_timeout():
    for argv in (
        ["--attempts", "0"],
        ["--attempts", "-1"],
        ["--attempt-timeout-s", "0"],
        ["--attempt-timeout-s", "-2"],
    ):
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_canonical_evidence_only_for_twenty_default_gemma_attempts():
    assert PROBE._canonical_evidence(attempts=20, model="gemma4:12b-it-qat") is True
    assert PROBE._canonical_evidence(attempts=5, model="gemma4:12b-it-qat") is False
    assert PROBE._canonical_evidence(attempts=20, model="qwen3:14b") is False


def test_cli_rejects_non_lm8j_surfaces():
    forbidden = (
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
        ["--gh-edit"],
        ["--phase", "receipt_recon"],
        ["--support-disabled"],
        ["--support-forced"],
    )
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_manifest_records_lm8j_identity():
    manifest = PROBE._manifest(attempts=20, model="gemma4:12b-it-qat")

    assert manifest["schema"] == "rook.lm8j_affine_support_repeatability_probe:v1"
    assert manifest["attempts"] == 20
    assert manifest["model"] == "gemma4:12b-it-qat"
    assert manifest["canonical_evidence"] is True
    assert manifest["child_probe"] == "lm8i_affine_publication_shape_support_probe.py"
    assert manifest["child_probe_invocation"] == "subprocess"
    assert manifest["support_mode"] == "lm8i_default_support_enabled"


def test_scheduled_attempt_id_is_stable():
    assert PROBE._scheduled_attempt_id(1) == "attempt-001"
    assert PROBE._scheduled_attempt_id(20) == "attempt-020"


def test_base_attempt_row_has_lm8j_fields():
    row = PROBE._base_attempt_row(attempt_index=1)

    assert row["attempt_index"] == 1
    assert row["scheduled_attempt_id"] == "attempt-001"
    assert row["lm8i_invoked"] is False
    assert row["lm8i_returncode"] is None
    assert row["lm8i_run_dir"] is None
    assert row["terminal_category"] is None
    assert row["publication_support_attempted"] is False
    assert row["publication_support_count"] == 0
    assert row["support_eligible"] is None
    assert row["support_recovered"] is False
    assert row["leak_check_performed"] is False
    assert row["leak_marker_match_count"] == 0
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
```

Expected: collection or test failure because `scripts/lm8j_affine_support_repeatability_probe.py` does not exist.

- [ ] **Step 3: Add the script scaffold and CLI implementation**

Create `scripts/lm8j_affine_support_repeatability_probe.py` with:

```python
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
    base = Path(run_root) / f"lm8j-{timestamp}-{_git_short_sha()}"
    candidate = base
    suffix = 1
    while candidate.exists():
        candidate = Path(f"{base}-{suffix:02d}")
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _manifest(*, attempts: int, model: str) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "attempts": attempts,
        "model": model,
        "canonical_evidence": _canonical_evidence(attempts=attempts, model=model),
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
```

- [ ] **Step 4: Run the CLI tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
```

Expected: the tests added in Task 1 pass. Later-task tests are not present yet.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add scripts\lm8j_affine_support_repeatability_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py
git commit -m "feat(lm8j): scaffold affine support repeatability wrapper"
```

---

### Task 2: LM8I Subprocess Command And Child Run Discovery

**Files:**
- Modify: `scripts/lm8j_affine_support_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`

**Interfaces:**
- Consumes:
  - `_REPO_ROOT`
  - `_base_attempt_row(attempt_index: int) -> dict[str, Any]`
  - `EXCERPT_CHARS`
- Produces:
  - `_lm8i_command(*, model: str, lm8i_runs_dir: Path) -> list[str]`
  - `_discover_child_run_dirs(lm8i_runs_dir: Path, before: set[Path]) -> list[Path]`
  - `_completed_text(value: object) -> str`
  - `_excerpt(text: str | None, *, limit: int = EXCERPT_CHARS) -> str`
  - `_single_child_dir_error(child_run_dirs: Sequence[Path]) -> tuple[Path | None, str | None]`
  - `_timeout_row(*, attempt_index: int, exc: subprocess.TimeoutExpired, child_run_dirs: Sequence[Path]) -> dict[str, Any]`
  - `_subprocess_error_row(*, attempt_index: int, exc: Exception, child_run_dirs: Sequence[Path]) -> dict[str, Any]`

- [ ] **Step 1: Add failing subprocess and discovery tests**

Append to `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`:

```python
import subprocess


def test_lm8i_command_uses_sys_executable_and_child_run_dir(tmp_path: Path):
    runs_dir = tmp_path / "lm8i_runs"

    command = PROBE._lm8i_command(
        model="gemma4:12b-it-qat",
        lm8i_runs_dir=runs_dir,
    )

    assert command == [
        sys.executable,
        str(PROBE._REPO_ROOT / "scripts" / "lm8i_affine_publication_shape_support_probe.py"),
        "--model",
        "gemma4:12b-it-qat",
        "--run-dir",
        str(runs_dir),
    ]
    assert "--retry-clean-observation" not in command
    assert "--gh-edit" not in command
    assert "--support-forced" not in command
    assert "--support-disabled" not in command


def test_discover_child_run_dirs_uses_filesystem_delta(tmp_path: Path):
    runs_dir = tmp_path / "lm8i_runs"
    runs_dir.mkdir()
    existing = runs_dir / "lm8i-existing"
    existing.mkdir()
    ignored_file = runs_dir / "lm8i-file"
    ignored_file.write_text("not a run dir", encoding="utf-8")
    before = {path for path in runs_dir.glob("lm8i-*") if path.is_dir()}

    child = runs_dir / "lm8i-new"
    child.mkdir()

    assert PROBE._discover_child_run_dirs(runs_dir, before) == [child]


def test_completed_text_and_excerpt_handle_bytes_none_and_length():
    assert PROBE._completed_text(None) == ""
    assert PROBE._completed_text(b"abc") == "abc"
    assert PROBE._completed_text("xyz") == "xyz"

    assert PROBE._excerpt(None) == ""
    assert PROBE._excerpt("") == ""
    assert PROBE._excerpt("abcdef", limit=4) == "abcd"
    assert PROBE._excerpt("abc", limit=4) == "abc"


def test_single_child_dir_error_classifies_missing_and_ambiguous(tmp_path: Path):
    assert PROBE._single_child_dir_error([]) == (None, "child_run_dir_missing")

    first = tmp_path / "lm8i-a"
    second = tmp_path / "lm8i-b"
    first.mkdir()
    second.mkdir()

    assert PROBE._single_child_dir_error([first, second]) == (
        None,
        "child_run_dir_ambiguous",
    )
    assert PROBE._single_child_dir_error([first]) == (first, None)


def test_timeout_and_subprocess_error_rows_preserve_child_dir_when_present(tmp_path: Path):
    child = tmp_path / "lm8i-child"
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
    assert timeout_row["failure_reason"] == "lm8i_timeout"
    assert timeout_row["child_run_dir_error"] is None
    assert timeout_row["lm8i_run_dir"] == str(child)
    assert timeout_row["stdout_excerpt"] == "stdout before timeout"
    assert timeout_row["stderr_excerpt"] == "stderr before timeout"

    error_row = PROBE._subprocess_error_row(
        attempt_index=2,
        exc=OSError("launch failed"),
        child_run_dirs=[child],
    )
    assert error_row["terminal_category"] == "wrapper_error"
    assert error_row["failure_reason"] == "lm8i_subprocess_error:OSError"
    assert error_row["child_run_dir_error"] is None
    assert error_row["lm8i_run_dir"] == str(child)
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_lm8i_command_uses_sys_executable_and_child_run_dir mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_discover_child_run_dirs_uses_filesystem_delta mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_timeout_and_subprocess_error_rows_preserve_child_dir_when_present -q
```

Expected: failures because the subprocess and row helpers are not implemented.

- [ ] **Step 3: Implement subprocess command and discovery helpers**

Add to `scripts/lm8j_affine_support_repeatability_probe.py` after `_base_attempt_row`:

```python
def _lm8i_command(*, model: str, lm8i_runs_dir: Path) -> list[str]:
    return [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "lm8i_affine_publication_shape_support_probe.py"),
        "--model",
        model,
        "--run-dir",
        str(lm8i_runs_dir),
    ]


def _discover_child_run_dirs(lm8i_runs_dir: Path, before: set[Path]) -> list[Path]:
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


def _single_child_dir_error(child_run_dirs: Sequence[Path]) -> tuple[Path | None, str | None]:
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
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
```

Expected: all currently written tests pass.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add scripts\lm8j_affine_support_repeatability_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py
git commit -m "feat(lm8j): schedule lm8i subprocess attempts"
```

---

### Task 3: Child Decision Classification And Artifact Summaries

**Files:**
- Modify: `scripts/lm8j_affine_support_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`

**Interfaces:**
- Consumes:
  - `TERMINAL_CATEGORIES`
  - `_base_attempt_row`
  - `_single_child_dir_error`
  - `_completed_text`
  - `_excerpt`
- Produces:
  - `_read_json_mapping(path: Path) -> Mapping[str, Any] | None`
  - `_read_decision(path: Path) -> tuple[dict[str, Any] | None, str | None]`
  - `_classify_decision(decision: Mapping[str, Any]) -> tuple[str, str | None]`
  - `_copy_decision_identity(row: dict[str, Any], decision: Mapping[str, Any]) -> None`
  - `_copy_child_artifact_summaries(row: dict[str, Any]) -> None`
  - `_row_from_completed_lm8i(*, attempt_index: int, completed: subprocess.CompletedProcess, child_run_dirs: Sequence[Path]) -> dict[str, Any]`

- [ ] **Step 1: Add failing decision and child artifact tests**

Append to `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`:

```python
import json


def _write_child_decision(child: Path, payload: dict) -> None:
    child.mkdir(parents=True, exist_ok=True)
    (child / "decision.json").write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def test_read_decision_handles_missing_invalid_and_non_mapping(tmp_path: Path):
    missing, missing_error = PROBE._read_decision(tmp_path / "missing.json")
    assert missing is None
    assert missing_error == "lm8i_missing_decision_json"

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{bad", encoding="utf-8")
    invalid, invalid_error = PROBE._read_decision(invalid_path)
    assert invalid is None
    assert invalid_error == "lm8i_invalid_decision_json"

    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    non_mapping, non_mapping_error = PROBE._read_decision(list_path)
    assert non_mapping is None
    assert non_mapping_error == "lm8i_decision_not_mapping"


def test_classify_decision_preserves_known_lm8i_categories():
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
        "lm8i_missing_decision",
    )
    assert PROBE._classify_decision({"decision": "strange"}) == (
        "wrapper_error",
        "lm8i_unknown_decision:strange",
    )


def test_row_from_completed_accepted_lm8i_child_copies_support_metadata(tmp_path: Path):
    child = tmp_path / "lm8i-child"
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
            "publication_support_attempted": True,
            "publication_support_count": 1,
            "support_eligible": True,
            "support_not_attempted_reason": None,
            "first_publication_status": "pass1_decision_invalid",
            "first_publication_failure_reason": "pass1_missing_action_id",
            "final_publication_status": "published",
            "final_publication_failure_reason": None,
            "final_worker_response_kind": "action_request",
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=0,
        stdout="run_dir=child decision=accepted",
        stderr="",
    )

    row = PROBE._row_from_completed_lm8i(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["lm8i_invoked"] is True
    assert row["lm8i_returncode"] == 0
    assert row["lm8i_run_dir"] == str(child)
    assert row["lm8i_decision"] == "accepted"
    assert row["lm8i_reason"] == "verify_scalar_output_succeeded"
    assert row["terminal_category"] == "accepted"
    assert row["failure_reason"] is None
    assert row["worker_publication_ran"] is True
    assert row["live_set_value_dispatched"] is True
    assert row["verify_scalar_output_ran"] is True
    assert row["scalar_runtime_ready"] is True
    assert row["observed_output_after"] == 7.5
    assert row["publication_support_attempted"] is True
    assert row["publication_support_count"] == 1
    assert row["support_eligible"] is True
    assert row["first_publication_failure_reason"] == "pass1_missing_action_id"
    assert row["final_publication_status"] == "published"
    assert row["final_worker_response_kind"] == "action_request"
    assert row["support_recovered"] is False


def test_row_from_completed_nonzero_returncode_is_wrapper_error(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    _write_child_decision(
        child,
        {
            "decision": "accepted",
            "reason": "verify_scalar_output_succeeded",
            "worker_publication_ran": True,
        },
    )
    completed = subprocess.CompletedProcess(
        args=["python"],
        returncode=2,
        stdout="partial stdout",
        stderr="partial stderr",
    )

    row = PROBE._row_from_completed_lm8i(
        attempt_index=1,
        completed=completed,
        child_run_dirs=[child],
    )

    assert row["terminal_category"] == "wrapper_error"
    assert row["failure_reason"] == "lm8i_nonzero_returncode:2"
    assert row["child_run_dir_error"] is None
    assert row["lm8i_run_dir"] == str(child)
    assert row["lm8i_decision"] == "accepted"
    assert row["worker_publication_ran"] is True
    assert row["stdout_excerpt"] == "partial stdout"
    assert row["stderr_excerpt"] == "partial stderr"


def test_copy_child_artifact_summaries_reads_worker_verifier_and_support_recovery(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "worker_action.json").write_text(
        json.dumps({"input": {"value": 3.0}}),
        encoding="utf-8",
    )
    (child / "verify_scalar_output_summary.json").write_text(
        json.dumps({"attempt_count": 2, "observed_output_value": 7.5}),
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "support_recovered": False,
        "worker_action_value": None,
        "verifier_attempt_count": None,
        "observed_output_after": None,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["worker_action_value"] == 3.0
    assert row["verifier_attempt_count"] == 2
    assert row["observed_output_after"] == 7.5
    assert row["support_recovered"] is True


def test_support_recovered_requires_worker_action_receipt(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    row = {
        "lm8i_run_dir": str(child),
        "publication_support_attempted": True,
        "final_publication_status": "published",
        "final_worker_response_kind": "action_request",
        "support_recovered": False,
    }

    PROBE._copy_child_artifact_summaries(row)

    assert row["support_recovered"] is False
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_row_from_completed_accepted_lm8i_child_copies_support_metadata mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_copy_child_artifact_summaries_reads_worker_verifier_and_support_recovery mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_support_recovered_requires_worker_action_receipt -q
```

Expected: failures because the child decision and artifact helpers are not implemented.

- [ ] **Step 3: Implement decision parsing, classification, and artifact summaries**

Add to `scripts/lm8j_affine_support_repeatability_probe.py` after `_subprocess_error_row`:

```python
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
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
```

Expected: all currently written tests pass.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add scripts\lm8j_affine_support_repeatability_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py
git commit -m "feat(lm8j): classify lm8i child artifacts"
```

---

### Task 4: Report-Only Marker Scan And Summary Accounting

**Files:**
- Modify: `scripts/lm8j_affine_support_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`

**Interfaces:**
- Consumes:
  - `LEAK_MARKERS`
  - `_read_json_mapping`
  - row fields from Task 3
- Produces:
  - `_scan_leak_markers(run_dir: Path) -> list[dict[str, Any]]`
  - `_apply_leak_scan(row: dict[str, Any]) -> None`
  - `_compact_counts(counter: Counter[str]) -> dict[str, int]`
  - `_build_summary(rows: Sequence[Mapping[str, Any]], *, attempts: int, model: str) -> dict[str, Any]`

- [ ] **Step 1: Add failing leak scan and summary tests**

Append to `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`:

```python
def test_scan_and_apply_leak_markers_are_report_only(tmp_path: Path):
    child = tmp_path / "lm8i-child"
    child.mkdir()
    (child / "notes.json").write_text(
        json.dumps(
            {
                "marker": "PROBE_REPAIR_CODE",
                "nested": {"value": "A = 42.0"},
            }
        ),
        encoding="utf-8",
    )
    row = {
        "lm8i_run_dir": str(child),
        "terminal_category": "accepted",
        "leak_check_performed": False,
        "leak_marker_matches": [],
        "leak_marker_match_count": 0,
    }

    matches = PROBE._scan_leak_markers(child)
    assert matches == [
        {"path": str(child / "notes.json"), "marker": "PROBE_REPAIR_CODE"},
        {"path": str(child / "notes.json"), "marker": "A = 42.0"},
    ]

    PROBE._apply_leak_scan(row)

    assert row["terminal_category"] == "accepted"
    assert row["leak_check_performed"] is True
    assert row["leak_marker_match_count"] == 2
    assert row["leak_marker_matches"] == matches


def test_compact_counts_removes_zero_entries_and_sorts_keys():
    from collections import Counter

    counts = Counter({"rejected": 2, "accepted": 1, "gate_failed": 0})

    assert PROBE._compact_counts(counts) == {"accepted": 1, "rejected": 2}


def test_build_summary_counts_support_and_worker_denominators():
    rows = [
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "publication_support_attempted": False,
            "support_eligible": False,
            "support_recovered": False,
            "lm8i_run_dir": "run-a",
            "leak_marker_match_count": 1,
            "worker_action_value": 3.0,
            "verifier_attempt_count": 1,
            "observed_output_after": 7.5,
        },
        {
            "terminal_category": "accepted",
            "worker_publication_ran": True,
            "publication_support_attempted": True,
            "support_eligible": True,
            "support_recovered": True,
            "lm8i_run_dir": "run-b",
            "leak_marker_match_count": 0,
            "worker_action_value": 3.0,
            "verifier_attempt_count": 2,
            "observed_output_after": 7.5,
        },
        {
            "terminal_category": "publication_failed",
            "worker_publication_ran": True,
            "publication_support_attempted": True,
            "support_eligible": True,
            "support_recovered": False,
            "lm8i_run_dir": "run-c",
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "gate_failed",
            "worker_publication_ran": False,
            "publication_support_attempted": False,
            "support_eligible": None,
            "support_recovered": False,
            "gate_failure_reason": "affine_fixture_failed:gh_connect_failed",
            "lm8i_run_dir": "run-d",
            "leak_marker_match_count": 0,
        },
        {
            "terminal_category": "preflight_failed",
            "worker_publication_ran": False,
            "publication_support_attempted": False,
            "support_eligible": None,
            "support_recovered": False,
            "preflight_failure_reason": "rhino_ping_failed",
            "lm8i_run_dir": "run-e",
            "leak_marker_match_count": 0,
        },
    ]

    summary = PROBE._build_summary(rows, attempts=20, model="gemma4:12b-it-qat")

    assert summary["schema"] == "rook.lm8j_affine_support_repeatability_probe:v1"
    assert summary["scheduled_attempts"] == 20
    assert summary["canonical_evidence"] is True
    assert summary["terminal_category_counts"] == {
        "accepted": 2,
        "gate_failed": 1,
        "preflight_failed": 1,
        "publication_failed": 1,
    }
    assert summary["accepted_count"] == 2
    assert summary["publication_failed_count"] == 1
    assert summary["gate_failed_count"] == 1
    assert summary["preflight_failed_count"] == 1
    assert summary["worker_reached_count"] == 3
    assert summary["worker_terminal_counts"] == {"accepted": 2, "publication_failed": 1}
    assert summary["publication_support_attempted_count"] == 2
    assert summary["publication_support_recovered_count"] == 1
    assert summary["accepted_without_support_count"] == 1
    assert summary["support_eligible_count"] == 2
    assert summary["support_accepted_count"] == 1
    assert summary["gate_failure_reasons"] == {"affine_fixture_failed:gh_connect_failed": 1}
    assert summary["preflight_failure_reasons"] == {"rhino_ping_failed": 1}
    assert summary["leak_marker_match_count"] == 1
    assert summary["attempt_run_dirs"] == ["run-a", "run-b", "run-c", "run-d", "run-e"]
    assert summary["worker_action_values"] == [3.0, 3.0]
    assert summary["verifier_attempt_counts"] == [1, 2]
    assert summary["observed_output_values_after"] == [7.5, 7.5]
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_scan_and_apply_leak_markers_are_report_only mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_build_summary_counts_support_and_worker_denominators -q
```

Expected: failures because marker scanning and summary aggregation are not implemented.

- [ ] **Step 3: Implement marker scanning and summary accounting**

Add to `scripts/lm8j_affine_support_repeatability_probe.py` after `_copy_child_artifact_summaries`:

```python
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
        "publication_support_attempted_count": len(support_attempted_rows),
        "publication_support_recovered_count": len(support_recovered_rows),
        "accepted_without_support_count": len(accepted_without_support_rows),
        "support_eligible_count": sum(
            1 for row in rows if row.get("support_eligible") is True
        ),
        "support_accepted_count": len(accepted_support_rows),
        "gate_failure_reasons": _reason_counts(rows, "gate_failure_reason"),
        "preflight_failure_reasons": _reason_counts(rows, "preflight_failure_reason"),
        "leak_marker_match_count": sum(
            int(row.get("leak_marker_match_count") or 0) for row in rows
        ),
        "attempt_run_dirs": [
            str(row["lm8i_run_dir"]) for row in rows if row.get("lm8i_run_dir")
        ],
        "worker_action_values": _number_values(rows, "worker_action_value"),
        "verifier_attempt_counts": _int_values(rows, "verifier_attempt_count"),
        "observed_output_values_after": _number_values(rows, "observed_output_after"),
    }
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
```

Expected: all currently written tests pass.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add scripts\lm8j_affine_support_repeatability_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py
git commit -m "feat(lm8j): summarize affine support repeatability"
```

---

### Task 5: Run Orchestration, Artifacts, And Guard Tests

**Files:**
- Modify: `scripts/lm8j_affine_support_repeatability_probe.py`
- Modify: `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`

**Interfaces:**
- Consumes:
  - `_new_run_dir`
  - `_manifest`
  - `_lm8i_command`
  - `_discover_child_run_dirs`
  - `_row_from_completed_lm8i`
  - `_timeout_row`
  - `_subprocess_error_row`
  - `_copy_child_artifact_summaries`
  - `_apply_leak_scan`
  - `_build_summary`
- Produces:
  - `_write_json(path: Path, payload: Mapping[str, Any]) -> None`
  - `_append_jsonl(path: Path, payload: Mapping[str, Any]) -> None`
  - `_run_probe(*, attempts: int, model: str, run_root: str | Path, attempt_timeout_s: int, run_subprocess=None) -> Path`
  - `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Add failing orchestration and guard tests**

Append to `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`:

```python
import inspect


def test_write_json_and_append_jsonl_are_stable_and_structured(tmp_path: Path):
    json_path = tmp_path / "artifact.json"
    jsonl_path = tmp_path / "artifact.jsonl"

    PROBE._write_json(json_path, {"b": 2, "a": 1})
    PROBE._append_jsonl(jsonl_path, {"b": 2, "a": 1})
    PROBE._append_jsonl(jsonl_path, {"c": 3})

    assert json_path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'
    assert jsonl_path.read_text(encoding="utf-8").splitlines() == [
        '{"a": 1, "b": 2}',
        '{"c": 3}',
    ]


class FakeLm8iRunner:
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
        child = run_dir / f"lm8i-child-{len(self.calls):03d}"
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
                json.dumps(
                    {
                        "attempt_count": decision["verifier_attempt_count"],
                        "observed_output_value": decision.get("observed_output_after"),
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=f"run_dir={child}",
            stderr="",
        )


def test_run_probe_writes_manifest_attempts_and_summary(tmp_path: Path):
    runner = FakeLm8iRunner(
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
                "publication_support_attempted": False,
                "publication_support_count": 0,
                "support_eligible": False,
                "worker_action_value": 3.0,
                "verifier_attempt_count": 1,
            },
            {
                "decision": "publication_failed",
                "reason": "pass1_decision_invalid:pass1_missing_action_id",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
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
    assert [row["terminal_category"] for row in rows] == [
        "accepted",
        "publication_failed",
    ]
    assert rows[0]["worker_action_value"] == 3.0
    assert rows[0]["support_recovered"] is False
    assert rows[1]["publication_support_attempted"] is True
    assert rows[1]["support_recovered"] is False
    assert summary["accepted_count"] == 1
    assert summary["publication_failed_count"] == 1
    assert summary["worker_reached_count"] == 2
    assert summary["publication_support_attempted_count"] == 1
    assert summary["publication_support_recovered_count"] == 0
    assert summary["accepted_without_support_count"] == 1
    assert summary["worker_action_values"] == [3.0]
    assert summary["verifier_attempt_counts"] == [1]
    assert summary["observed_output_values_after"] == [7.5]
    assert len(runner.calls) == 2
    assert all(call["timeout"] == 600 for call in runner.calls)
    assert all(call["capture_output"] is True for call in runner.calls)
    assert all(call["text"] is True for call in runner.calls)


def test_run_probe_continues_after_wrapper_error(tmp_path: Path):
    calls = []

    def fake_runner(command, *, cwd, capture_output, text, timeout):
        calls.append(command)
        run_dir = Path(command[command.index("--run-dir") + 1])
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, returncode=0, stdout="", stderr="")
        child = run_dir / "lm8i-child-002"
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


def test_run_probe_counts_support_recovery_only_when_worker_action_exists(tmp_path: Path):
    runner = FakeLm8iRunner(
        [
            {
                "decision": "accepted",
                "reason": "verify_scalar_output_succeeded",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
                "final_publication_status": "published",
                "final_worker_response_kind": "action_request",
                "worker_action_value": 3.0,
            },
            {
                "decision": "publication_failed",
                "reason": "worker_action_apply_failed:invalid_input",
                "worker_publication_ran": True,
                "publication_support_attempted": True,
                "publication_support_count": 1,
                "support_eligible": True,
                "final_publication_status": "published",
                "final_worker_response_kind": "action_request",
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
    rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))

    assert rows[0]["support_recovered"] is True
    assert rows[1]["support_recovered"] is False
    assert summary["publication_support_attempted_count"] == 2
    assert summary["publication_support_recovered_count"] == 1
    assert summary["support_accepted_count"] == 1


def test_main_prints_run_dir_and_returns_zero(monkeypatch, tmp_path: Path, capsys):
    def fake_run_probe(**kwargs):
        run_dir = tmp_path / "lm8j-demo"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"accepted_count": 1, "scheduled_attempts": 1}),
            encoding="utf-8",
        )
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--attempts", "1", "--run-dir", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "LM8J affine support repeatability probe complete" in output
    assert "run_dir=" in output


def test_lm8j_source_does_not_import_lm8i_or_live_tooling():
    source = inspect.getsource(PROBE)

    forbidden = (
        "import lm8i_affine_publication_shape_support_probe",
        "from lm8i_affine_publication_shape_support_probe",
        "_mcp_tool_executor",
        '"rhino_ping"',
        '"gh_document_new"',
        '"gh_set_value"',
        '"gh_inspect_output"',
        "run_two_pass_worker_publication",
        "apply_gh_scalar_value_action_to_node",
    )
    for fragment in forbidden:
        assert fragment not in source
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_run_probe_writes_manifest_attempts_and_summary mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py::test_run_probe_counts_support_recovery_only_when_worker_action_exists -q
```

Expected: failures because `_run_probe`, writers, and `main` are not implemented.

- [ ] **Step 3: Implement artifact writers, run loop, and entrypoint**

Add to `scripts/lm8j_affine_support_repeatability_probe.py` after `_build_summary`:

```python
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
    lm8i_runs_dir = run_dir / "lm8i_runs"
    lm8i_runs_dir.mkdir(parents=True, exist_ok=True)

    _write_json(run_dir / "manifest.json", _manifest(attempts=attempts, model=model))

    rows: list[dict[str, Any]] = []
    for attempt_index in range(1, attempts + 1):
        before = {path for path in lm8i_runs_dir.glob("lm8i-*") if path.is_dir()}
        command = _lm8i_command(model=model, lm8i_runs_dir=lm8i_runs_dir)
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
```

- [ ] **Step 4: Run the complete focused test file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py -q
```

Expected: all LM8J tests pass.

- [ ] **Step 5: Run adjacent wrapper and child-probe tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py `
  mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py `
  mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py `
  -q
```

Expected: all selected tests pass. This is deterministic only; it must not open Rhino, Grasshopper, Ollama, or live model calls.

- [ ] **Step 6: Run Python compile checks**

Run:

```powershell
py -3.10 -m py_compile scripts\lm8j_affine_support_repeatability_probe.py
```

Expected: command exits 0.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add scripts\lm8j_affine_support_repeatability_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py
git commit -m "feat(lm8j): orchestrate affine support repeatability runs"
```

---

### Task 6: Final Verification And PR Scope Check

**Files:**
- Verify: `docs/superpowers/specs/2026-07-09-lm8j-affine-support-repeatability-design.md`
- Verify: `docs/superpowers/plans/2026-07-09-lm8j-affine-support-repeatability.md`
- Verify: `scripts/lm8j_affine_support_repeatability_probe.py`
- Verify: `mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py`

**Interfaces:**
- Consumes: all earlier task deliverables.
- Produces: merge-ready deterministic implementation branch.

- [ ] **Step 1: Run the deterministic LM8J and adjacent gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py `
  mcp_server\tests\test_lm8g_scalar_transform_repeatability_probe.py `
  mcp_server\tests\test_lm8i_affine_publication_shape_support_probe.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run compile check**

Run:

```powershell
py -3.10 -m py_compile scripts\lm8j_affine_support_repeatability_probe.py
```

Expected: command exits 0.

- [ ] **Step 3: Check whitespace and diff scope**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
```

Expected `git diff --check main..HEAD`: no output.

Expected tracked branch diff:

```text
docs/superpowers/specs/2026-07-09-lm8j-affine-support-repeatability-design.md
docs/superpowers/plans/2026-07-09-lm8j-affine-support-repeatability.md
scripts/lm8j_affine_support_repeatability_probe.py
mcp_server/tests/test_lm8j_affine_support_repeatability_probe.py
```

- [ ] **Step 4: Run source drift guard manually**

Run:

```powershell
Select-String -Path scripts\lm8j_affine_support_repeatability_probe.py -Pattern "_mcp_tool_executor","rhino_ping","gh_document_new","gh_set_value","gh_inspect_output","run_two_pass_worker_publication","apply_gh_scalar_value_action_to_node"
```

Expected: no matches.

The strings `--retry-clean-observation`, `--planner-provider-command`, `--request-json`, `--gh-edit`, `--support-disabled`, and `--support-forced` may appear only in `_args` rejection tests or `_args` rejection code. They must not appear in `_lm8i_command` or any subprocess command-building test as forwarded arguments.

- [ ] **Step 5: Confirm no live artifacts are staged**

Run:

```powershell
git status --short
```

Expected: no tracked or staged `probe_runs/` artifacts. Known unrelated local telemetry/draft dirt may remain unstaged and must not be included.

- [ ] **Step 6: Commit final verification notes if Task 6 changed files**

If Task 6 only ran commands and changed no files, do not create a commit. If Task 6 required a documentation or test correction, run:

```powershell
git add docs\superpowers\plans\2026-07-09-lm8j-affine-support-repeatability.md scripts\lm8j_affine_support_repeatability_probe.py mcp_server\tests\test_lm8j_affine_support_repeatability_probe.py
git commit -m "test(lm8j): harden repeatability wrapper verification"
```

---

## Post-Merge Live Evidence Runbook

After the implementation PR merges and `main` is synced, run exactly one canonical LM8J evidence command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8j_affine_support_repeatability_probe.py
```

Prerequisites:

- Rhino open and responsive.
- Grasshopper open and responsive.
- Grasshopper canvas visibly ready for edit.
- LM8I direct GH tools available.
- Ollama model `gemma4:12b-it-qat` available.

After the run, inspect:

```powershell
$run = "C:\UDEV\Rook\probe_runs\<printed-lm8j-run-dir>"
Get-Content "$run\manifest.json"
Get-Content "$run\summary.json"
Get-Content "$run\attempts.jsonl"
```

Then inspect child LM8I outcomes:

```powershell
Get-ChildItem "$run\lm8i_runs" -Directory | ForEach-Object {
  Write-Host $_.Name
  Get-Content "$($_.FullName)\decision.json"
}
```

Do not replace failed attempts. Any scheduled terminal outcome is evidence.

## Self-Review Checklist

- Spec coverage:
  - N=20 canonical scheduled denominator is in Task 1 and Task 5.
  - LM8I subprocess-only boundary is in Task 2, Task 5, and Task 6.
  - Filesystem-delta child discovery is in Task 2 and Task 5.
  - Wrapper error categories are in Task 2 and Task 3.
  - Support counters, including worker-action-receipt recovery, are in Task 3 and Task 4.
  - Report-only leak scanning is in Task 4.
  - No live run in implementation PR is in Task 6 and the runbook separation.
- Placeholder scan:
  - No placeholder markers or unspecified validation steps should remain.
- Type consistency:
  - Child run fields use `lm8i_*` consistently.
  - Summary names match the LM8J spec.
  - Support recovery uses `worker_action.json`, not only `final_worker_response_kind`.
