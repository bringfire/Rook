# LM8C GH Scalar Live Splice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first live GH-native scalar expectation splice probe, using the LM8B deterministic scalar seams and the frozen one-turn worker protocol.

**Architecture:** Add a new sibling script, `scripts/lm8c_gh_scalar_expectation_live_probe.py`, that owns scalar live preflight, direct GH slider fixture creation, scalar runtime readiness, worker publication, scalar action apply, `gh_set_value`, and verifier-floor scalar decision records. The implementation reuses neutral worker-turn rendering and shared two-pass publication, but does not import repair-specific LM6/LM7 request builders or introduce LM5X scalar routability.

**Tech Stack:** Python 3.10, pytest, existing `PlanGraph` dataclasses, LM8B scalar source/criteria/applier modules, existing local-worker context/request renderer, existing `lm_worker_two_pass_publication.py`, fake tool executors for tests.

## Global Constraints

- Deterministic implementation PR only.
- No live Rhino/GH run in the implementation PR.
- No `probe_runs/` committed.
- No Planner model.
- No model-authored template selection.
- No `PlannerWorkerContractRequest` schema changes.
- No production workflow-template integration.
- No generic PlanGraph runner.
- No LM5X routability claim for scalar routes.
- No retry.
- No N=5.
- No `gh_edit`.
- No wiring or topology mutation.
- No script repair.
- No worker prompt/protocol change.
- No new worker model panel.
- Canonical worker model is `gemma4:12b-it-qat`.
- Canonical provider path is direct Ollama `/api/chat`.
- Canonical fixture has `initial_value == 0.0`, `expected_output_value == 7.5`, and `identity_projection == true`.
- LM8C gate name is `scalar_runtime_ready`, not routability.
- Worker action id is `draft_gh_set_value_params`.
- Worker action input is exactly `{"value": number}`.
- Worker-visible/source artifacts must not contain the raw trusted slider GUID.
- Full GUID is allowed only in ignored local runtime audit artifacts for target creation and mutation: `live_create_scalar_summary.json` and `live_set_value_summary.json`.
- `verify_scalar_output_summary.json` and `decision.json` use GUID hash/presence only.
- No package-level re-export from `rook.agent`.

---

## File Structure

Create:

- `scripts/lm8c_gh_scalar_expectation_live_probe.py`
  - Owns LM8C CLI, run directory, preflight, scalar fixture creation, scalar runtime readiness, worker request construction, worker publication, scalar action apply, live `gh_set_value`, verification, summaries, and terminal decision record.
  - Imports LM8B scalar modules and neutral worker-turn helpers.
  - Does not import LM6A/LM7B/LM7E worker-request builders or repair-specific live dispatch helpers.

- `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`
  - Imports the script as a module.
  - Uses fake tool executors and fake publication functions only.
  - Verifies CLI defaults, canonical constraints, preflight, fixture creation, scalar runtime readiness, GUID policy, worker request shape, terminal decisions, hidden/drift guards, and final happy-path fake flow.

Modify:

- No production `mcp_server/src` files expected.
- No LM5/LM6/LM7 scripts expected.
- No live tests expected.

---

## Shared Script Interfaces

The script should expose these helpers for focused tests:

```python
SCRIPT_SCHEMA = "rook.lm8c_gh_scalar_expectation_live_probe:v1"
DECISION_SCHEMA = "rook.lm8c_decision:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
INITIAL_SCALAR_VALUE = 0.0
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
WORKER_NODE_ID = "set_scalar_value"
CREATE_NODE_ID = "create_scalar_expectation"
VERIFY_NODE_ID = "verify_scalar_output"
ACTION_ID = "draft_gh_set_value_params"
```

Required helper signatures:

```python
def _args(argv: list[str] | None) -> argparse.Namespace: ...

def _canonical_evidence_is_valid(args: argparse.Namespace) -> bool: ...

def _new_run_dir(run_root: str | Path) -> Path: ...

def _fingerprint_json(value: Any) -> str: ...

def _sha256_text(value: str) -> str: ...

def _guid_sha256(guid: str | None) -> str | None: ...

def _write_json(path: Path, payload: Mapping[str, Any]) -> None: ...

def _write_json_value(path: Path, payload: Any) -> None: ...

def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    canonical_evidence: bool,
    scalar_runtime_ready: bool | None = None,
    live_fixture_created: bool = False,
    worker_publication_ran: bool = False,
    live_set_value_dispatched: bool = False,
    verify_scalar_output_ran: bool = False,
    component_guid: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...

async def _run_preflight(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> tuple[bool, str | None, dict[str, Any]]: ...

async def _create_scalar_fixture(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> dict[str, Any]: ...

def _scalar_source_routing_artifact() -> dict[str, Any]: ...

def _scalar_contract_payload() -> dict[str, Any]: ...

def _graph_from_scalar_receipt(receipt: Mapping[str, Any]) -> PlanGraph: ...

def _scalar_runtime_context(
    *,
    graph: PlanGraph,
    workflow_contract_payload: Mapping[str, Any],
    convention_packets: tuple[WorkerKnowledgePacket, ...],
) -> dict[str, Any]: ...

def _build_worker_request_payload(
    *,
    graph: PlanGraph,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> dict[str, Any]: ...

async def _dispatch_set_value_and_verify(
    *,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
    component_guid: str,
    worker_value: float | int,
    expected_value: float | int,
) -> dict[str, Any]: ...

def _run_probe(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    canonical_evidence: bool,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]] | None = None,
    publication_runner: Callable[..., Any] | None = None,
) -> Path: ...
```

The exact implementation may add private helpers, but tests should use the
above seam names where practical.

---

### Task 1: Script Skeleton, CLI, Run Artifacts, And Decision Records

**Files:**
- Create: `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- Create: `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`

**Interfaces:**
- Produces: CLI defaults, canonical evidence gate, run directory naming, JSON writers, fingerprints, decision record helper.
- Consumed by later tasks: `_run_probe(...)`, `_decision_record(...)`, `_write_json(...)`, `_fingerprint_json(...)`, constants.

- [ ] **Step 1: Add script import/load test and CLI default tests**

Create `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`:

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
        / "lm8c_gh_scalar_expectation_live_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm8c_gh_scalar_expectation_live_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical_worker_shape() -> None:
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"
    assert args.canonical_evidence is True


def test_cli_overrides_are_exploratory_unless_explicitly_marked_canonical() -> None:
    args = PROBE._args(["--model", "qwen3:14b"])
    assert args.canonical_evidence is False


def test_cli_rejects_non_lm8c_surfaces() -> None:
    forbidden = [
        ["--phase", "receipt_recon"],
        ["--attempts", "5"],
        ["--retry-clean-observation"],
        ["--planner-provider-command", "x"],
        ["--prompt-profile", "shape_guidance_v2"],
        ["--request-json", "request.json"],
    ]
    for argv in forbidden:
        with pytest.raises(SystemExit):
            PROBE._args(argv)


def test_canonical_evidence_requires_default_shape() -> None:
    args = PROBE._args(["--canonical-evidence"])
    assert PROBE._canonical_evidence_is_valid(args) is True

    for argv in (
        ["--canonical-evidence", "--model", "qwen3:14b"],
        ["--canonical-evidence", "--endpoint", "http://example.invalid/chat"],
        ["--canonical-evidence", "--temperature", "0.2"],
    ):
        assert PROBE._canonical_evidence_is_valid(PROBE._args(argv)) is False
```

- [ ] **Step 2: Run tests to verify import failure**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py -q
```

Expected:

```text
FileNotFoundError
```

or module import failure for missing `scripts/lm8c_gh_scalar_expectation_live_probe.py`.

- [ ] **Step 3: Add minimal script with constants, CLI, and canonical check**

Create `scripts/lm8c_gh_scalar_expectation_live_probe.py`:

```python
#!/usr/bin/env python
"""LM8C GH scalar expectation live splice probe."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


SCRIPT_SCHEMA = "rook.lm8c_gh_scalar_expectation_live_probe:v1"
DECISION_SCHEMA = "rook.lm8c_decision:v1"
DEFAULT_MODEL = "gemma4:12b-it-qat"
DEFAULT_ENDPOINT = "http://localhost:11434/api/chat"
DEFAULT_TEMPERATURE = 0
DEFAULT_TIMEOUT_S = 120
DEFAULT_EXCERPT_CHARS = 1200
INITIAL_SCALAR_VALUE = 0.0
EXPECTED_OUTPUT_VALUE = 7.5
SCALAR_TOLERANCE = 1e-9
WORKER_NODE_ID = "set_scalar_value"
CREATE_NODE_ID = "create_scalar_expectation"
VERIFY_NODE_ID = "verify_scalar_output"
ACTION_ID = "draft_gh_set_value_params"
DECISIONS = {
    "preflight_failed",
    "gate_failed",
    "publication_failed",
    "worker_declined",
    "rejected",
    "accepted",
}


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM8C GH scalar expectation live splice probe."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--run-dir", default="probe_runs")
    parser.add_argument("--canonical-evidence", action="store_true")
    args = parser.parse_args(argv)
    if args.excerpt_chars < 0:
        parser.error("excerpt_chars_must_be_non_negative")
    if not args.canonical_evidence:
        args.canonical_evidence = (
            args.model == DEFAULT_MODEL
            and args.endpoint == DEFAULT_ENDPOINT
            and args.temperature == DEFAULT_TEMPERATURE
        )
    return args


def _canonical_evidence_is_valid(args: argparse.Namespace) -> bool:
    if not args.canonical_evidence:
        return True
    return (
        args.model == DEFAULT_MODEL
        and args.endpoint == DEFAULT_ENDPOINT
        and args.temperature == DEFAULT_TEMPERATURE
    )


def _git_short_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _new_run_dir(run_root: str | Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(run_root) / f"lm8c-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _fingerprint_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _guid_sha256(guid: str | None) -> str | None:
    return None if guid is None else _sha256_text(guid)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_json_value(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    canonical_evidence: bool,
    scalar_runtime_ready: bool | None = None,
    live_fixture_created: bool = False,
    worker_publication_ran: bool = False,
    live_set_value_dispatched: bool = False,
    verify_scalar_output_ran: bool = False,
    component_guid: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"Unsupported LM8C decision: {decision}")
    record = {
        "schema": DECISION_SCHEMA,
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "canonical_evidence": canonical_evidence,
        "scalar_runtime_ready": scalar_runtime_ready,
        "live_fixture_created": live_fixture_created,
        "worker_publication_ran": worker_publication_ran,
        "live_set_value_dispatched": live_set_value_dispatched,
        "verify_scalar_output_ran": verify_scalar_output_ran,
        "guid_present": component_guid is not None,
        "component_guid_sha256": _guid_sha256(component_guid),
    }
    if extra:
        record.update(dict(extra))
    return record


def _manifest(*, model: str, endpoint: str, temperature: float, canonical_evidence: bool) -> dict[str, Any]:
    return {
        "schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "model": model,
        "endpoint": endpoint,
        "temperature": temperature,
        "canonical_evidence": canonical_evidence,
        "attempts": 1,
        "initial_scalar_value": INITIAL_SCALAR_VALUE,
        "expected_output_value": EXPECTED_OUTPUT_VALUE,
        "identity_projection": True,
        "worker_retry_enabled": False,
        "planner_model": None,
        "gh_edit_enabled": False,
    }
```

- [ ] **Step 4: Add decision and writer tests**

Append to `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`:

```python
def test_decision_record_hashes_guid_without_raw_guid() -> None:
    decision = PROBE._decision_record(
        decision="accepted",
        reason="verify_scalar_output_succeeded",
        phase="verify_scalar_output",
        canonical_evidence=True,
        scalar_runtime_ready=True,
        live_fixture_created=True,
        worker_publication_ran=True,
        live_set_value_dispatched=True,
        verify_scalar_output_ran=True,
        component_guid="GUID-SECRET",
        extra={"observed_output_after": 7.5},
    )

    rendered = json.dumps(decision, sort_keys=True)
    assert decision["component_guid_sha256"].startswith("sha256:")
    assert decision["guid_present"] is True
    assert "GUID-SECRET" not in rendered
    assert decision["decision"] == "accepted"


def test_manifest_records_lm8c_identity() -> None:
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        canonical_evidence=True,
    )

    assert manifest["schema"] == "rook.lm8c_gh_scalar_expectation_live_probe:v1"
    assert manifest["attempts"] == 1
    assert manifest["expected_output_value"] == 7.5
    assert manifest["initial_scalar_value"] == 0.0
    assert manifest["worker_retry_enabled"] is False
    assert manifest["planner_model"] is None
    assert manifest["gh_edit_enabled"] is False
```

- [ ] **Step 5: Run Task 1 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py -q
```

Expected:

```text
6 passed
```

- [ ] **Step 6: Commit Task 1**

```powershell
git add scripts\lm8c_gh_scalar_expectation_live_probe.py mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
git commit -m "feat: add LM8C scalar live probe shell"
```

---

### Task 2: Preflight And Direct GH Scalar Fixture Creation

**Files:**
- Modify: `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- Modify: `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`

**Interfaces:**
- Consumes: Task 1 constants, decision helpers, writers.
- Produces:
  - `_run_preflight(...)`
  - `_create_scalar_fixture(...)`
  - `_coerce_scalar_value(...)`
  - `_tool_result_failed(...)`
  - `_tool_data(...)`
  - `_tool_field(...)`
  - `_guid_from_result(...)`
  - live fixture summaries with GUID policy.

- [ ] **Step 1: Add fake executor and preflight tests**

Append to `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`:

```python
class FakeToolExecutor:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    async def __call__(self, tool_name, args):
        self.calls.append((tool_name, dict(args)))
        value = self.responses[tool_name]
        if isinstance(value, Exception):
            raise value
        return value


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_preflight_accepts_pong_and_document_created() -> None:
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
        }
    )

    ok, reason, summaries = _run(PROBE._run_preflight(executor))

    assert ok is True
    assert reason is None
    assert summaries["rhino_ping"] == "pong"
    assert summaries["gh_document_new"] == {"success": True, "data": {"Created": True}}
    assert executor.calls == [("rhino_ping", {}), ("gh_document_new", {})]


def test_preflight_classifies_ping_and_document_failures() -> None:
    ping_failed = FakeToolExecutor(
        {
            "rhino_ping": {"success": False, "error": "offline"},
            "gh_document_new": {"created": True},
        }
    )
    ok, reason, _summaries = _run(PROBE._run_preflight(ping_failed))
    assert ok is False
    assert reason == "rhino_ping_failed"
    assert ping_failed.calls == [("rhino_ping", {})]

    document_failed = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"created": False},
        }
    )
    ok, reason, _summaries = _run(PROBE._run_preflight(document_failed))
    assert ok is False
    assert reason == "gh_document_new_failed"
```

- [ ] **Step 2: Implement preflight helpers**

Add to `scripts/lm8c_gh_scalar_expectation_live_probe.py` after `_manifest`:

```python
def _tool_result_failed(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, Mapping):
        if result.get("success") is False:
            return True
        if result.get("error"):
            return True
        data = result.get("data")
        if isinstance(data, str) and data.startswith("Error:"):
            return True
    return False


def _preflight_ping_ok(result: Any) -> bool:
    if result == "pong":
        return True
    if isinstance(result, Mapping):
        return result.get("success") is True and result.get("data") == "pong"
    return False


def _document_new_ok(result: Any) -> bool:
    if not isinstance(result, Mapping):
        return False
    data = result.get("data")
    if result.get("created") is True or result.get("Created") is True:
        return True
    if isinstance(data, Mapping):
        return data.get("created") is True or data.get("Created") is True
    return False


async def _run_preflight(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> tuple[bool, str | None, dict[str, Any]]:
    summaries: dict[str, Any] = {}
    try:
        ping = await tool_executor("rhino_ping", {})
    except Exception as exc:
        summaries["rhino_ping"] = {"exception": type(exc).__name__}
        return False, "rhino_ping_failed", summaries
    summaries["rhino_ping"] = ping
    if _tool_result_failed(ping) or not _preflight_ping_ok(ping):
        return False, "rhino_ping_failed", summaries

    try:
        document = await tool_executor("gh_document_new", {})
    except Exception as exc:
        summaries["gh_document_new"] = {"exception": type(exc).__name__}
        return False, "gh_document_new_failed", summaries
    summaries["gh_document_new"] = document
    if _tool_result_failed(document) or not _document_new_ok(document):
        return False, "gh_document_new_failed", summaries
    return True, None, summaries
```

- [ ] **Step 3: Add scalar fixture creation tests**

Append:

```python
def test_create_scalar_fixture_uses_direct_slider_tools_and_hashes_guid() -> None:
    executor = FakeToolExecutor(
        {
            "gh_create_slider": {
                "success": True,
                "data": {
                    "Created": True,
                    "Guid": "SLIDER-GUID-1",
                    "NickName": "LM8C_Target",
                },
            },
            "gh_get_value": {
                "success": True,
                "data": {
                    "Guid": "SLIDER-GUID-1",
                    "Value": "0.0",
                },
            },
        }
    )

    fixture = _run(PROBE._create_scalar_fixture(executor))

    assert executor.calls == [
        (
            "gh_create_slider",
            {
                "nickname": "LM8C_Target",
                "min": 0,
                "max": 10,
                "value": 0.0,
                "x": 20,
                "y": 80,
            },
        ),
        ("gh_get_value", {"guid": "SLIDER-GUID-1"}),
    ]
    assert fixture["component_guid"] == "SLIDER-GUID-1"
    assert fixture["observed_output_value"] == 0.0
    assert fixture["receipt"]["scalar_anchor"]["component_guid"] == "SLIDER-GUID-1"
    assert "component_guid" not in fixture["receipt"]["scalar_anchor"]["editable_value_contract"]
    rendered_sources = json.dumps(fixture["visible_receipt"], sort_keys=True)
    assert "SLIDER-GUID-1" not in rendered_sources
    assert fixture["live_create_scalar_summary"]["component_guid"] == "SLIDER-GUID-1"
    assert fixture["live_create_scalar_summary"]["component_guid_sha256"].startswith("sha256:")


@pytest.mark.parametrize("bad_value", ["not-number", True, None])
def test_create_scalar_fixture_rejects_bad_initial_get_value(bad_value) -> None:
    executor = FakeToolExecutor(
        {
            "gh_create_slider": {"success": True, "data": {"Created": True, "Guid": "SLIDER-GUID-1"}},
            "gh_get_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": bad_value}},
        }
    )

    with pytest.raises(ValueError, match="live scalar value"):
        _run(PROBE._create_scalar_fixture(executor))
```

- [ ] **Step 4: Implement scalar fixture helpers**

Add:

```python
def _coerce_scalar_value(value: Any) -> float | int:
    import math

    if isinstance(value, bool):
        raise ValueError("live scalar value must be a finite number")
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("live scalar value must be a finite number")
        return value
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ValueError("live scalar value must be a finite number") from exc
        if not math.isfinite(parsed):
            raise ValueError("live scalar value must be a finite number")
        return parsed
    raise ValueError("live scalar value must be a finite number")


def _tool_data(result: Any) -> Any:
    if isinstance(result, Mapping) and isinstance(result.get("data"), Mapping):
        return result["data"]
    return result


def _tool_field(result: Any, *names: str) -> Any:
    payload = _tool_data(result)
    if not isinstance(payload, Mapping):
        return None
    for name in names:
        if name in payload:
            return payload[name]
    return None


def _guid_from_result(result: Any) -> str:
    guid = _tool_field(result, "guid", "Guid", "component_guid")
    if not isinstance(guid, str) or not guid.strip():
        raise ValueError("tool result guid missing")
    return guid


def _receipt_sha256(result: Any) -> str:
    return _fingerprint_json(result)


async def _create_scalar_fixture(
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
) -> dict[str, Any]:
    create_args = {
        "nickname": "LM8C_Target",
        "min": 0,
        "max": 10,
        "value": INITIAL_SCALAR_VALUE,
        "x": 20,
        "y": 80,
    }
    create_result = await tool_executor("gh_create_slider", create_args)
    if _tool_result_failed(create_result):
        raise ValueError("gh_create_slider_failed")
    component_guid = _guid_from_result(create_result)

    get_result = await tool_executor("gh_get_value", {"guid": component_guid})
    if _tool_result_failed(get_result):
        raise ValueError("gh_get_value_failed")
    if not isinstance(_tool_data(get_result), Mapping):
        raise ValueError("gh_get_value_result_invalid")
    observed = _coerce_scalar_value(_tool_field(get_result, "value", "Value"))

    editable_contract = {
        "label": "LM8C_Target",
        "value_type": "number",
        "current_value": observed,
        "identity_projection": True,
    }
    receipt = {
        "observed_output_value": observed,
        "scalar_anchor": {
            "component_guid": component_guid,
            "editable_value_contract": dict(editable_contract),
        },
    }
    visible_receipt = {
        "observed_output_value": observed,
        "scalar_anchor": {
            "guid_present": True,
            "component_guid_sha256": _guid_sha256(component_guid),
            "editable_value_contract": dict(editable_contract),
        },
    }
    live_summary = {
        "tool_name": "gh_create_slider",
        "created": True,
        "component_guid": component_guid,
        "component_guid_sha256": _guid_sha256(component_guid),
        "nickname": create_args["nickname"],
        "initial_value": INITIAL_SCALAR_VALUE,
        "observed_value": observed,
        "receipt_sha256": _receipt_sha256(
            {"create": create_result, "get_value": get_result}
        ),
    }
    return {
        "component_guid": component_guid,
        "observed_output_value": observed,
        "receipt": receipt,
        "visible_receipt": visible_receipt,
        "live_create_scalar_summary": live_summary,
    }
```

- [ ] **Step 5: Run Task 2 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py -q
```

Expected:

```text
10 passed
```

- [ ] **Step 6: Commit Task 2**

```powershell
git add scripts\lm8c_gh_scalar_expectation_live_probe.py mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
git commit -m "feat: add LM8C scalar preflight and fixture"
```

---

### Task 3: Scalar Runtime Readiness And Worker Request Construction

**Files:**
- Modify: `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- Modify: `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`

**Interfaces:**
- Consumes: LM8B `validate_worker_visible_source_routing`, `extract_gh_scalar_expectation_sources`, `assemble_gh_scalar_expectation_packet`, `project_gh_scalar_expectation_legacy`.
- Produces:
  - `_scalar_source_routing_artifact()`
  - `_scalar_contract_payload()`
  - `_graph_from_scalar_receipt(...)`
  - `_scalar_runtime_context(...)`
  - `_build_worker_request_payload(...)`

- [ ] **Step 1: Add scalar runtime readiness tests**

Append:

```python
def _valid_fixture():
    return {
        "component_guid": "SLIDER-GUID-1",
        "observed_output_value": 0.0,
        "receipt": {
            "observed_output_value": 0.0,
            "scalar_anchor": {
                "component_guid": "SLIDER-GUID-1",
                "editable_value_contract": {
                    "label": "LM8C_Target",
                    "value_type": "number",
                    "current_value": 0.0,
                    "identity_projection": True,
                },
            },
        },
        "visible_receipt": {},
        "live_create_scalar_summary": {},
    }


def test_scalar_runtime_context_static_validates_without_lm5x_routability() -> None:
    graph = PROBE._graph_from_scalar_receipt(_valid_fixture()["receipt"])
    context = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_contract_payload(),
        convention_packets=(),
    )

    routing_report = context["static_routing_report"]
    assert routing_report["valid"] is True
    assert routing_report["routability_evaluated"] is False
    assert context["scalar_runtime_ready"] is True
    assert context["sources"].expected_output_contract.value == 7.5
    assert context["sources"].receipt_observation.value == 0.0
    assert context["packet"]["fields"]["expected_output_value"] == 7.5
    assert context["worker_visible"]["source"] == "gh_scalar_expectation"


def test_scalar_runtime_context_fails_when_live_receipt_missing_observation() -> None:
    receipt = _valid_fixture()["receipt"]
    receipt.pop("observed_output_value")
    graph = PROBE._graph_from_scalar_receipt(receipt)

    with pytest.raises(ValueError, match="observed_output_value"):
        PROBE._scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=PROBE._scalar_contract_payload(),
            convention_packets=(),
        )
```

- [ ] **Step 2: Implement scalar routing/context helpers**

Add imports near the top of `scripts/lm8c_gh_scalar_expectation_live_probe.py`:

```python
from lm_worker_two_pass_publication import run_two_pass_worker_publication  # noqa: E402
from rook.agent.gh_scalar_expectation_acceptance_criteria import (  # noqa: E402
    assemble_gh_scalar_expectation_packet,
    project_gh_scalar_expectation_legacy,
)
from rook.agent.gh_scalar_expectation_sources import (  # noqa: E402
    CONVENTION_SOURCE_PATH,
    EXPECTED_OUTPUT_SOURCE_PATH,
    FIXTURE_ANCHOR_SOURCE_PATH,
    OBSERVED_OUTPUT_SOURCE_PATH,
    extract_gh_scalar_expectation_sources,
)
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
)
from rook.agent.local_worker_turn_context import (  # noqa: E402
    WorkerAllowedAction,
    WorkerKnowledgePacket,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_request import (  # noqa: E402
    render_local_worker_turn_request_payload,
)
from rook.agent.plan_graph_workflow_contract import (  # noqa: E402
    CompiledWorkflowScaffold,
    WorkflowCompileRecord,
    WorkflowContractSnapshot,
)
from rook.learning.plan_graph import (  # noqa: E402
    GraphMemory,
    NodeEvidence,
    PlanGraph,
    PlanGraphNode,
)
```

Add:

```python
def _routing_report_json(report: Any) -> dict[str, Any]:
    return {
        "schema": report.schema,
        "valid": report.valid,
        "routability_evaluated": report.routability_evaluated,
        "static_diagnostics": [
            {
                "severity": item.severity,
                "code": item.code,
                "node_id": item.node_id,
                "route_id": item.route_id,
                "source_class": item.source_class,
                "source_path": item.source_path,
                "purpose": item.purpose,
                "message": item.message,
            }
            for item in report.static_diagnostics
        ],
        "routability_diagnostics": [
            {
                "severity": item.severity,
                "code": item.code,
                "node_id": item.node_id,
                "route_id": item.route_id,
                "source_class": item.source_class,
                "source_path": item.source_path,
                "purpose": item.purpose,
                "message": item.message,
            }
            for item in report.routability_diagnostics
        ],
    }


def _scalar_source_routing_artifact() -> dict[str, Any]:
    return {
        "schema": "rook.worker_visible_source_routing:v1",
        "routes": [
            {
                "node_id": WORKER_NODE_ID,
                "visible_sources": [
                    {
                        "route_id": "scalar_expected_output_value",
                        "source_class": "expected_output_contract",
                        "source_path": EXPECTED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_current_output",
                        "source_class": "receipt_observation",
                        "source_path": OBSERVED_OUTPUT_SOURCE_PATH,
                        "purpose": "acceptance_criteria",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_editable_target_contract",
                        "source_class": "fixture_anchor",
                        "source_path": FIXTURE_ANCHOR_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": True,
                    },
                    {
                        "route_id": "scalar_set_value_convention",
                        "source_class": "convention",
                        "source_path": CONVENTION_SOURCE_PATH,
                        "purpose": "evidence_context",
                        "required": False,
                    },
                ],
            }
        ],
    }


def _scalar_contract_payload() -> dict[str, Any]:
    return {
        "rules": {
            VERIFY_NODE_ID: {
                "expected_output_value": EXPECTED_OUTPUT_VALUE,
            }
        }
    }


def _graph_from_scalar_receipt(receipt: Mapping[str, Any]) -> PlanGraph:
    return PlanGraph(
        nodes={
            CREATE_NODE_ID: PlanGraphNode(
                id=CREATE_NODE_ID,
                intent="Create GH scalar expectation fixture",
                status="succeeded",
                evidence=NodeEvidence(
                    tool_status="success",
                    verified=True,
                    receipt=dict(receipt),
                ),
            ),
            WORKER_NODE_ID: PlanGraphNode(
                id=WORKER_NODE_ID,
                intent="Set editable GH scalar value",
                execution_ref="gh_set_value:v1",
                status="ready",
            ),
            VERIFY_NODE_ID: PlanGraphNode(
                id=VERIFY_NODE_ID,
                intent="Verify GH scalar output",
                verifier_ref="gh_get_value:v1",
                status="pending",
                is_terminal=True,
            ),
        },
        memory=GraphMemory(),
    )


def _scalar_runtime_context(
    *,
    graph: PlanGraph,
    workflow_contract_payload: Mapping[str, Any],
    convention_packets: tuple[WorkerKnowledgePacket, ...],
) -> dict[str, Any]:
    routing_artifact = _scalar_source_routing_artifact()
    static_report = validate_worker_visible_source_routing(routing_artifact)
    static_report_json = _routing_report_json(static_report)
    if static_report.valid is not True:
        return {
            "scalar_runtime_ready": False,
            "routing_artifact": routing_artifact,
            "static_routing_report": static_report_json,
        }
    sources = extract_gh_scalar_expectation_sources(
        workflow_contract_payload=workflow_contract_payload,
        graph=graph,
        convention_packets=convention_packets,
    )
    packet = assemble_gh_scalar_expectation_packet(sources)
    worker_visible = project_gh_scalar_expectation_legacy(packet)
    return {
        "scalar_runtime_ready": True,
        "routing_artifact": routing_artifact,
        "static_routing_report": static_report_json,
        "sources": sources,
        "packet": packet,
        "worker_visible": worker_visible,
    }
```

- [ ] **Step 3: Add worker request shape tests**

Append:

```python
def test_worker_request_uses_scalar_knowledge_and_never_exposes_raw_guid() -> None:
    fixture = _valid_fixture()
    graph = PROBE._graph_from_scalar_receipt(fixture["receipt"])
    runtime = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_contract_payload(),
        convention_packets=(),
    )

    payload = PROBE._build_worker_request_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
    )

    rendered = json.dumps(payload, sort_keys=True)
    assert payload["schema"] == "rook.local_worker_turn_request:v1"
    assert "gh_scalar_expectation_evidence" in rendered
    assert "draft_gh_set_value_params" in rendered
    assert '"value"' in rendered
    assert "SLIDER-GUID-1" not in rendered
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
```

- [ ] **Step 4: Implement worker request helpers**

Add:

```python
def _scalar_scaffold(graph: PlanGraph) -> CompiledWorkflowScaffold:
    normalized_contract = {
        "schema": "rook.workflow_contract:v1",
        "workflow_id": "lm8c-gh-scalar-expectation",
    }
    contract_fingerprint = _fingerprint_json(normalized_contract).removeprefix("sha256:")
    snapshot = WorkflowContractSnapshot(
        workflow_id="lm8c-gh-scalar-expectation",
        normalized_contract=normalized_contract,
        contract_fingerprint=contract_fingerprint,
    )
    compile_record = WorkflowCompileRecord(
        workflow_id="lm8c-gh-scalar-expectation",
        compiler_id="lm8c.script_local_scalar_scaffold:v1",
        contract_schema="rook.workflow_contract:v1",
        contract_fingerprint_algorithm="sha256",
        contract_fingerprint=contract_fingerprint,
        provider_id="lm8c.script_local_provider:v1",
        expected_template_id="gh_scalar_value_expectation",
        selected_template_id="gh_scalar_value_expectation",
        graph_node_ids=tuple(sorted(graph.nodes)),
        initial_param_node_ids=(),
        rule_node_ids=(WORKER_NODE_ID, VERIFY_NODE_ID),
        terminal_node_ids=(VERIFY_NODE_ID,),
        expected_refs=((WORKER_NODE_ID, "gh_set_value:v1"),),
        step_kinds_by_rule=(),
        max_steps=4,
    )
    return CompiledWorkflowScaffold(
        workflow_id="lm8c-gh-scalar-expectation",
        graph=graph,
        provider=object(),
        max_steps=4,
        metadata={},
        rules=(),
        steps=(),
        contract_snapshot=snapshot,
        compile_record=compile_record,
    )


def _scalar_worker_evidence_packet(
    *,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> WorkerKnowledgePacket:
    fields = packet["fields"]
    editable = dict(fields["editable_value_contract"])
    return WorkerKnowledgePacket(
        packet_id="gh_scalar_expectation_evidence",
        kind="evidence",
        title="GH scalar expectation evidence",
        content={
            "source": "gh_scalar_expectation",
            "trust": "high",
            "state": "post_scalar_fixture_pre_worker",
            "fields": {
                "current_observed_output": fields["current_observed_output"],
                "expected_output_value": fields["expected_output_value"],
                "editable_value_contract": editable,
                "acceptance_criteria": dict(worker_visible),
                "recommended_action_id": ACTION_ID,
            },
        },
    )


def _scalar_allowed_action() -> WorkerAllowedAction:
    return WorkerAllowedAction(
        action_id=ACTION_ID,
        kind="stage_params",
        description="Draft the scalar value to apply to the trusted editable GH target.",
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
    )


def _build_worker_request_payload(
    *,
    graph: PlanGraph,
    packet: Mapping[str, Any],
    worker_visible: Mapping[str, Any],
) -> dict[str, Any]:
    context = build_local_worker_turn_context(
        _scalar_scaffold(graph),
        graph,
        records=(),
        supply_records=(),
        current_node_id=WORKER_NODE_ID,
        knowledge=(
            _scalar_worker_evidence_packet(
                packet=packet,
                worker_visible=worker_visible,
            ),
        ),
        allowed_actions=(_scalar_allowed_action(),),
    )
    return dict(render_local_worker_turn_request_payload(context))
```

- [ ] **Step 5: Run Task 3 tests plus LM8B source/criteria tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 6: Commit Task 3**

```powershell
git add scripts\lm8c_gh_scalar_expectation_live_probe.py mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
git commit -m "feat: add LM8C scalar runtime readiness"
```

---

### Task 4: Worker Publication, Scalar Action Apply, Live Set, And Verification

**Files:**
- Modify: `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- Modify: `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`

**Interfaces:**
- Consumes: Task 3 worker request payload, LM8B scalar applier, shared two-pass publication helper.
- Produces:
  - `_decision_from_publication(...)`
  - `_worker_action_context(...)`
  - `_dispatch_set_value_and_verify(...)`
  - complete `_run_probe(...)`.

- [ ] **Step 1: Add fake publication result and worker decision tests**

Append:

```python
class FakePublication:
    def __init__(self, row, response_payload=None):
        self.row = row
        self.response_payload = response_payload


def test_publication_non_action_maps_to_worker_declined() -> None:
    row = {
        "status": "published",
        "pass2_response_kind": "observation",
        "observation_action_intent_anomaly": False,
    }
    payload = {"schema": "rook.local_worker_turn_response:v1", "kind": "observation", "message": "not acting", "data": None}

    decision = PROBE._decision_from_publication(row, payload)

    assert decision == {
        "decision": "worker_declined",
        "reason": "worker_observed",
        "phase": "worker_publication",
        "final_worker_response_kind": "observation",
    }


def test_publication_failure_maps_to_publication_failed() -> None:
    decision = PROBE._decision_from_publication(
        {"status": "pass2_lm5g_invalid", "failure_reason": "bad-json"},
        None,
    )

    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "pass2_lm5g_invalid:bad-json"
```

- [ ] **Step 2: Implement publication decision helper**

Add imports:

```python
from rook.agent.plan_graph_gh_scalar_value_apply import (  # noqa: E402
    apply_gh_scalar_value_action_to_node,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY  # noqa: E402
```

Add:

```python
def _decision_from_publication(
    publication_row: Mapping[str, Any],
    response_payload: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    status = publication_row.get("status")
    if status != "published":
        reason = str(publication_row.get("failure_reason") or status or "unknown")
        return {
            "decision": "publication_failed",
            "reason": f"{status}:{reason}",
            "phase": "worker_publication",
        }
    if not isinstance(response_payload, Mapping):
        return {
            "decision": "publication_failed",
            "reason": "published_response_missing",
            "phase": "worker_publication",
        }
    kind = response_payload.get("kind")
    if kind == "action_request":
        return None
    if publication_row.get("observation_action_intent_anomaly") is True:
        return {
            "decision": "worker_declined",
            "reason": "worker_observation_action_intent_anomaly",
            "phase": "worker_publication",
            "final_worker_response_kind": kind,
        }
    reasons = {
        "clarification_request": "worker_clarified",
        "refusal": "worker_refused",
        "observation": "worker_observed",
    }
    return {
        "decision": "worker_declined",
        "reason": reasons.get(str(kind), "worker_non_action"),
        "phase": "worker_publication",
        "final_worker_response_kind": kind,
    }


def _hidden_marker_leaks(value: Any) -> bool:
    rendered = json.dumps(value, sort_keys=True, default=str)
    forbidden = (
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    )
    return any(marker in rendered for marker in forbidden)
```

- [ ] **Step 3: Add dispatch/verify tests**

Append:

```python
def test_dispatch_set_value_and_verify_accepts_live_observed_match() -> None:
    executor = FakeToolExecutor(
        {
            "gh_set_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "NewValue": 7.5}},
            "gh_get_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": "7.5"}},
        }
    )

    result = _run(
        PROBE._dispatch_set_value_and_verify(
            tool_executor=executor,
            component_guid="SLIDER-GUID-1",
            worker_value=7.5,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "accepted"
    assert result["decision"]["reason"] == "verify_scalar_output_succeeded"
    assert result["live_set_value_summary"]["component_guid"] == "SLIDER-GUID-1"
    assert result["verify_scalar_output_summary"]["component_guid_sha256"].startswith("sha256:")
    assert "component_guid" not in result["verify_scalar_output_summary"]


def test_dispatch_set_value_and_verify_rejects_live_observed_mismatch() -> None:
    executor = FakeToolExecutor(
        {
            "gh_set_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "NewValue": 0.0}},
            "gh_get_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": "0.0"}},
        }
    )

    result = _run(
        PROBE._dispatch_set_value_and_verify(
            tool_executor=executor,
            component_guid="SLIDER-GUID-1",
            worker_value=7.5,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_failed"


def test_dispatch_set_value_and_verify_receipts_invalid_final_value() -> None:
    executor = FakeToolExecutor(
        {
            "gh_set_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "NewValue": 7.5}},
            "gh_get_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": "not-number"}},
        }
    )

    result = _run(
        PROBE._dispatch_set_value_and_verify(
            tool_executor=executor,
            component_guid="SLIDER-GUID-1",
            worker_value=7.5,
            expected_value=7.5,
        )
    )

    assert result["decision"]["decision"] == "rejected"
    assert result["decision"]["reason"] == "verify_scalar_output_invalid_value"
    assert result["verify_scalar_output_summary"]["matched"] is False
```

- [ ] **Step 4: Implement dispatch/verify helper**

Add:

```python
async def _dispatch_set_value_and_verify(
    *,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]],
    component_guid: str,
    worker_value: float | int,
    expected_value: float | int,
) -> dict[str, Any]:
    set_result = await tool_executor(
        "gh_set_value",
        {"guid": component_guid, "value": worker_value},
    )
    set_summary = {
        "tool_name": "gh_set_value",
        "component_guid": component_guid,
        "component_guid_sha256": _guid_sha256(component_guid),
        "worker_action_value": worker_value,
        "success": not _tool_result_failed(set_result),
        "receipt_sha256": _receipt_sha256(set_result),
    }
    if _tool_result_failed(set_result):
        return {
            "live_set_value_summary": set_summary,
            "verify_scalar_output_summary": None,
            "decision": {
                "decision": "rejected",
                "reason": "gh_set_value_failed",
                "phase": "live_set_value",
            },
        }

    get_result = await tool_executor("gh_get_value", {"guid": component_guid})
    invalid_value = False
    if _tool_result_failed(get_result) or not isinstance(_tool_data(get_result), Mapping):
        observed = None
        matched = False
    else:
        try:
            observed = _coerce_scalar_value(_tool_field(get_result, "value", "Value"))
        except ValueError:
            observed = None
            matched = False
            invalid_value = True
        else:
            matched = abs(float(observed) - float(expected_value)) <= SCALAR_TOLERANCE
    verify_summary = {
        "tool_name": "gh_get_value",
        "component_guid_sha256": _guid_sha256(component_guid),
        "expected_output_value": expected_value,
        "observed_output_value": observed,
        "tolerance": SCALAR_TOLERANCE,
        "matched": matched,
        "receipt_sha256": _receipt_sha256(get_result),
    }
    return {
        "live_set_value_summary": set_summary,
        "verify_scalar_output_summary": verify_summary,
        "decision": {
            "decision": "accepted" if matched else "rejected",
            "reason": (
                "verify_scalar_output_succeeded"
                if matched
                else "verify_scalar_output_invalid_value"
                if invalid_value
                else "verify_scalar_output_failed"
            ),
            "phase": "verify_scalar_output",
            "expected_output_value": expected_value,
            "observed_output_after": observed,
            "scalar_tolerance": SCALAR_TOLERANCE,
        },
    }
```

- [ ] **Step 5: Add end-to-end fake run tests**

Append:

```python
def test_run_probe_happy_path_writes_bounded_artifacts(tmp_path: Path) -> None:
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
            "gh_create_slider": {"success": True, "data": {"Created": True, "Guid": "SLIDER-GUID-1"}},
            "gh_get_value": [
                {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": "0.0"}},
                {"success": True, "data": {"Guid": "SLIDER-GUID-1", "Value": "7.5"}},
            ],
            "gh_set_value": {"success": True, "data": {"Guid": "SLIDER-GUID-1", "NewValue": 7.5}},
        }
    )

    async def sequence_executor(tool_name, args):
        value = executor.responses[tool_name]
        executor.calls.append((tool_name, dict(args)))
        if isinstance(value, list):
            return value.pop(0)
        return value

    def fake_publication_runner(*_args, **_kwargs):
        return FakePublication(
            row={"status": "published", "pass2_response_kind": "action_request"},
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "rationale": "Set to the expected scalar value.",
                "input": {"value": 7.5},
            },
        )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=sequence_executor,
        publication_runner=fake_publication_runner,
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    worker_payload = (run_dir / "worker_request_payload.json").read_text()
    verify_summary = json.loads((run_dir / "verify_scalar_output_summary.json").read_text())

    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_scalar_output_succeeded"
    assert decision["scalar_runtime_ready"] is True
    assert decision["live_fixture_created"] is True
    assert decision["worker_publication_ran"] is True
    assert decision["live_set_value_dispatched"] is True
    assert decision["verify_scalar_output_ran"] is True
    assert "SLIDER-GUID-1" not in worker_payload
    assert "component_guid" not in verify_summary
    assert verify_summary["matched"] is True


def test_run_probe_preflight_failure_writes_terminal_decision(tmp_path: Path) -> None:
    executor = FakeToolExecutor({"rhino_ping": {"success": False, "error": "offline"}})

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=executor,
        publication_runner=lambda *_args, **_kwargs: pytest.fail("worker called"),
    )

    decision = json.loads((run_dir / "decision.json").read_text())
    assert decision["decision"] == "preflight_failed"
    assert decision["reason"] == "rhino_ping_failed"
    assert decision["worker_publication_ran"] is False
```

Important: update `FakeToolExecutor` so list-valued responses are popped, or use the `sequence_executor` wrapper shown above.

- [ ] **Step 6: Implement `_run_probe(...)` and `main(...)`**

Add:

```python
def _action_context(response_payload: Mapping[str, Any], excerpt_chars: int) -> dict[str, Any]:
    action_input = response_payload.get("input")
    rendered = json.dumps(action_input, sort_keys=True, default=str)
    return {
        "worker_action_input_sha256": _sha256_text(rendered),
        "worker_action_input_excerpt": rendered[:excerpt_chars],
    }


def _run_probe(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    canonical_evidence: bool,
    tool_executor: Callable[[str, Mapping[str, Any]], Awaitable[Any]] | None = None,
    publication_runner: Callable[..., Any] | None = None,
) -> Path:
    run_dir = _new_run_dir(run_root)
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            model=model,
            endpoint=endpoint,
            temperature=temperature,
            canonical_evidence=canonical_evidence,
        ),
    )
    if tool_executor is None:
        from rook.server import _mcp_tool_executor

        tool_executor = _mcp_tool_executor
    publisher = publication_runner or run_two_pass_worker_publication

    ok, preflight_reason, preflight_summaries = asyncio.run(_run_preflight(tool_executor))
    if not ok:
        _write_json_value(run_dir / "preflight_summary.json", preflight_summaries)
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="preflight_failed",
                reason=str(preflight_reason),
                phase="preflight",
                canonical_evidence=canonical_evidence,
            ),
        )
        return run_dir

    try:
        fixture = asyncio.run(_create_scalar_fixture(tool_executor))
    except Exception as exc:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"scalar_fixture_failed:{type(exc).__name__}",
                phase="live_fixture",
                canonical_evidence=canonical_evidence,
            ),
        )
        return run_dir

    component_guid = fixture["component_guid"]
    _write_json(run_dir / "live_create_scalar_summary.json", fixture["live_create_scalar_summary"])
    _write_json_value(run_dir / "scalar_fixture_contract.json", _scalar_contract_payload())

    graph = _graph_from_scalar_receipt(fixture["receipt"])
    try:
        runtime = _scalar_runtime_context(
            graph=graph,
            workflow_contract_payload=_scalar_contract_payload(),
            convention_packets=(),
        )
    except Exception as exc:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason=f"scalar_runtime_readiness_failed:{type(exc).__name__}",
                phase="scalar_runtime_ready",
                canonical_evidence=canonical_evidence,
                live_fixture_created=True,
                component_guid=component_guid,
            ),
        )
        return run_dir

    _write_json_value(run_dir / "scalar_source_routing.json", runtime["routing_artifact"])
    _write_json(run_dir / "static_routing_validation.json", runtime["static_routing_report"])
    if runtime["scalar_runtime_ready"] is not True:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="gate_failed",
                reason="scalar_runtime_not_ready",
                phase="scalar_runtime_ready",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=False,
                live_fixture_created=True,
                component_guid=component_guid,
            ),
        )
        return run_dir

    _write_json_value(run_dir / "scalar_sources.json", {
        "expected_output_contract": runtime["sources"].expected_output_contract.__dict__,
        "receipt_observation": runtime["sources"].receipt_observation.__dict__,
        "fixture_anchor": runtime["sources"].fixture_anchor.__dict__,
    })
    _write_json_value(run_dir / "acceptance_criteria_packet.json", runtime["packet"])
    _write_json(run_dir / "worker_visible_acceptance_criteria.json", runtime["worker_visible"])
    request_payload = _build_worker_request_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
    )
    _write_json_value(run_dir / "worker_request_payload.json", request_payload)

    publication = publisher(
        request_payload,
        model=model,
        endpoint=endpoint,
        temperature=temperature,
        timeout_s=timeout_s,
        excerpt_chars=excerpt_chars,
    )
    if _hidden_marker_leaks(publication.row) or _hidden_marker_leaks(publication.response_payload):
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="publication_failed",
                reason="worker_publication_hidden_answer_leak",
                phase="worker_publication",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=component_guid,
            ),
        )
        return run_dir

    _write_json(run_dir / "worker_publication_row.json", publication.row)
    worker_decision = _decision_from_publication(publication.row, publication.response_payload)
    if worker_decision is not None:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision=worker_decision["decision"],
                reason=worker_decision["reason"],
                phase=worker_decision["phase"],
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=component_guid,
                extra={
                    key: value
                    for key, value in worker_decision.items()
                    if key not in {"decision", "reason", "phase"}
                },
            ),
        )
        return run_dir

    response_payload = publication.response_payload
    _write_json(run_dir / "worker_action.json", response_payload)
    action_context = _action_context(response_payload, excerpt_chars)
    apply_result = apply_gh_scalar_value_action_to_node(
        graph,
        WORKER_NODE_ID,
        action_id=str(response_payload.get("action_id") or ""),
        action_input=response_payload.get("input"),
        anchor_binding={"component_guid": component_guid},
    )
    if apply_result.applied is not True:
        _write_json(
            run_dir / "decision.json",
            _decision_record(
                decision="rejected",
                reason=f"worker_action_apply_failed:{apply_result.reason}",
                phase="worker_action_apply",
                canonical_evidence=canonical_evidence,
                scalar_runtime_ready=True,
                live_fixture_created=True,
                worker_publication_ran=True,
                component_guid=component_guid,
                extra=action_context,
            ),
        )
        return run_dir

    params = apply_result.graph.nodes[WORKER_NODE_ID].metadata[EXECUTION_PARAMS_KEY]
    dispatch = asyncio.run(
        _dispatch_set_value_and_verify(
            tool_executor=tool_executor,
            component_guid=str(params["guid"]),
            worker_value=params["value"],
            expected_value=EXPECTED_OUTPUT_VALUE,
        )
    )
    _write_json(run_dir / "live_set_value_summary.json", dispatch["live_set_value_summary"])
    if dispatch["verify_scalar_output_summary"] is not None:
        _write_json(
            run_dir / "verify_scalar_output_summary.json",
            dispatch["verify_scalar_output_summary"],
        )
    final = dispatch["decision"]
    _write_json(
        run_dir / "decision.json",
        _decision_record(
            decision=final["decision"],
            reason=final["reason"],
            phase=final["phase"],
            canonical_evidence=canonical_evidence,
            scalar_runtime_ready=True,
            live_fixture_created=True,
            worker_publication_ran=True,
            live_set_value_dispatched=True,
            verify_scalar_output_ran=dispatch["verify_scalar_output_summary"] is not None,
            component_guid=component_guid,
            extra={**action_context, **final},
        ),
    )
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    if not _canonical_evidence_is_valid(args):
        print("invalid_canonical_evidence", file=sys.stderr)
        raise SystemExit(2)
    run_dir = _run_probe(
        model=args.model,
        endpoint=args.endpoint,
        temperature=args.temperature,
        timeout_s=args.timeout_s,
        excerpt_chars=args.excerpt_chars,
        run_root=args.run_dir,
        canonical_evidence=args.canonical_evidence,
    )
    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    print(
        "LM8C GH scalar expectation live splice probe complete "
        f"run_dir={run_dir} "
        f"decision={decision.get('decision')} "
        f"reason={decision.get('reason')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

This keeps the live dispatch handoff aligned with the scalar applier contract.

- [ ] **Step 7: Run Task 4 tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 8: Commit Task 4**

```powershell
git add scripts\lm8c_gh_scalar_expectation_live_probe.py mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
git commit -m "feat: add LM8C scalar worker live splice"
```

---

### Task 5: Guardrails, Drift Tests, And Verification

**Files:**
- Modify: `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`
- Modify only if needed: `scripts/lm8c_gh_scalar_expectation_live_probe.py`

**Interfaces:**
- Consumes: completed LM8C script.
- Produces: static/import/drift tests and final verification commands.

- [ ] **Step 1: Add static drift and artifact GUID-policy tests**

Append:

```python
def test_script_static_guard_forbids_repair_and_batch_surfaces() -> None:
    import ast

    source = _script_path().read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_import_fragments = [
        "lm6a_live_worker_splice_probe",
        "lm7b_request_driven_live_splice_probe",
        "lm7e_model_authored_live_splice_probe",
        "planner_worker_contract_request",
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for marker in forbidden_import_fragments:
                assert marker not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                for marker in forbidden_import_fragments:
                    assert marker not in alias.name

    dispatched_tools = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        first_arg = node.args[0]
        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
            dispatched_tools.append(first_arg.value)

    forbidden_dispatched_tools = [
        "gh_edit",
        "gh_update_script",
        "gh_create_csharp_script",
    ]
    for marker in forbidden_dispatched_tools:
        assert marker not in dispatched_tools

    forbidden_call_names = [
        "_worker_request_payload",
        "materialize_planner_worker_contract_request",
        "validate_planner_worker_contract_request",
        "retry_clean_observation",
        "lm6e_bounded_retry_context",
    ]
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            for marker in forbidden_call_names:
                assert marker not in name

    assert "repair_same_component" not in dispatched_tools


def test_source_and_worker_artifacts_do_not_contain_raw_guid(tmp_path: Path) -> None:
    executor = FakeToolExecutor(
        {
            "rhino_ping": "pong",
            "gh_document_new": {"success": True, "data": {"Created": True}},
            "gh_create_slider": {
                "success": True,
                "data": {"Created": True, "Guid": "SLIDER-GUID-SECRET"},
            },
            "gh_get_value": [
                {"success": True, "data": {"Guid": "SLIDER-GUID-SECRET", "Value": "0.0"}},
                {"success": True, "data": {"Guid": "SLIDER-GUID-SECRET", "Value": "7.5"}},
            ],
            "gh_set_value": {
                "success": True,
                "data": {"Guid": "SLIDER-GUID-SECRET", "NewValue": 7.5},
            },
        }
    )

    async def sequence_executor(tool_name, args):
        value = executor.responses[tool_name]
        executor.calls.append((tool_name, dict(args)))
        if isinstance(value, list):
            return value.pop(0)
        return value

    def fake_publication_runner(*_args, **_kwargs):
        return FakePublication(
            row={"status": "published", "pass2_response_kind": "action_request"},
            response_payload={
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_gh_set_value_params",
                "rationale": "Set to expected value.",
                "input": {"value": 7.5},
            },
        )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        timeout_s=120,
        excerpt_chars=1200,
        run_root=tmp_path,
        canonical_evidence=True,
        tool_executor=sequence_executor,
        publication_runner=fake_publication_runner,
    )

    no_guid_files = [
        "scalar_sources.json",
        "acceptance_criteria_packet.json",
        "worker_visible_acceptance_criteria.json",
        "worker_request_payload.json",
        "verify_scalar_output_summary.json",
        "decision.json",
    ]
    for name in no_guid_files:
        assert "SLIDER-GUID-SECRET" not in (run_dir / name).read_text()

    assert "SLIDER-GUID-SECRET" in (run_dir / "live_create_scalar_summary.json").read_text()
    assert "SLIDER-GUID-SECRET" in (run_dir / "live_set_value_summary.json").read_text()
```

- [ ] **Step 2: Add main function smoke test**

Append:

```python
def test_main_runs_probe_and_prints_completion(tmp_path: Path, monkeypatch, capsys) -> None:
    run_dir = tmp_path / "lm8c-test"
    run_dir.mkdir()
    (run_dir / "decision.json").write_text(
        json.dumps({"decision": "accepted", "reason": "verify_scalar_output_succeeded"}),
        encoding="utf-8",
    )
    captured = {}

    def fake_run_probe(**kwargs):
        captured.update(kwargs)
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    result = PROBE.main(
        [
            "--model",
            "test-model",
            "--endpoint",
            "http://example.invalid/chat",
            "--temperature",
            "0.25",
            "--timeout-s",
            "3",
            "--excerpt-chars",
            "17",
            "--run-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert captured["model"] == "test-model"
    assert captured["endpoint"] == "http://example.invalid/chat"
    assert captured["temperature"] == 0.25
    assert captured["timeout_s"] == 3
    assert captured["excerpt_chars"] == 17
    assert captured["run_root"] == str(tmp_path)
    assert captured["canonical_evidence"] is False
    assert "LM8C GH scalar expectation live splice probe complete" in output
    assert f"run_dir={run_dir}" in output
    assert "decision=accepted" in output
```

- [ ] **Step 3: Run focused LM8C and LM8B tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Run nearby worker publication/turn renderer tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_request.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 5: Compile changed Python files**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
```

Expected:

```text
no output, exit code 0
```

- [ ] **Step 6: Run forbidden real-coupling drift scan**

Run:

```powershell
Select-String -Path scripts\lm8c_gh_scalar_expectation_live_probe.py `
  -Pattern 'lm6a_live_worker_splice_probe','lm7b_request_driven_live_splice_probe','lm7e_model_authored_live_splice_probe','_worker_request_payload','tool_executor\("gh_edit"','tool_executor\("gh_update_script"','tool_executor\("gh_create_csharp_script"','retry_clean_observation'
```

Expected:

```text
no matches
```

Policy strings such as `gh_edit_enabled`, hidden-answer markers, and
`repair_same_component.bind.base_params` may appear only as manifest/policy data
and are covered by the AST/static guard test rather than this raw scan.

- [ ] **Step 7: Check exact diff scope**

Run:

```powershell
git diff --name-only main..HEAD
```

Expected tracked scope:

```text
docs/superpowers/plans/2026-07-08-lm8c-gh-scalar-live-splice.md
docs/superpowers/specs/2026-07-08-lm8c-gh-scalar-live-splice-design.md
mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py
scripts/lm8c_gh_scalar_expectation_live_probe.py
```

Run:

```powershell
git diff --check main..HEAD
```

Expected:

```text
no output, exit code 0
```

- [ ] **Step 8: Commit Task 5**

If Task 5 changed tests or script:

```powershell
git add scripts\lm8c_gh_scalar_expectation_live_probe.py mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
git commit -m "test: cover LM8C scalar live splice guards"
```

If Task 5 only verified existing commits, do not create an empty commit.

---

## Post-Merge Live Runbook

Do not run this during the implementation PR.

After merge and synced `main`, with Rhino and Grasshopper open:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8c_gh_scalar_expectation_live_probe.py
```

The bare command uses the canonical default shape and records
`canonical_evidence: true`. Any model, endpoint, temperature, fixture, or retry
override is exploratory and must not be cited as canonical LM8C evidence.

Inspect the printed run dir:

```powershell
$run = "C:\UDEV\Rook\probe_runs\<printed-run-dir-name>"

Get-Content "$run\decision.json"
Get-Content "$run\static_routing_validation.json"
Get-Content "$run\scalar_sources.json"
Get-Content "$run\acceptance_criteria_packet.json"
Get-Content "$run\worker_publication_row.json" -ErrorAction SilentlyContinue
Get-Content "$run\worker_action.json" -ErrorAction SilentlyContinue
Get-Content "$run\live_create_scalar_summary.json"
Get-Content "$run\live_set_value_summary.json" -ErrorAction SilentlyContinue
Get-Content "$run\verify_scalar_output_summary.json" -ErrorAction SilentlyContinue
```

Leak/GUID checks:

```powershell
Select-String -Path "$run\scalar_sources.json","$run\acceptance_criteria_packet.json","$run\worker_visible_acceptance_criteria.json","$run\worker_request_payload.json","$run\verify_scalar_output_summary.json","$run\decision.json" `
  -Pattern "SLIDER-GUID","PROBE_REPAIR_CODE","A = 42.0","BindStepSpec.base_params","gh_edit","gh_update_script"
```

Expected hidden-marker matches:

```text
none
```

Raw GUID may appear only in:

```text
live_create_scalar_summary.json
live_set_value_summary.json
```

Then write a separate doc-only evidence summary PR.

---

## Self-Review Checklist

- LM8C uses a new sibling script, not LM6A/LM7B/LM7E modes.
- Direct scalar tools only: `rhino_ping`, `gh_document_new`, `gh_create_slider`, `gh_get_value`, `gh_set_value`.
- No `gh_edit`, wiring, topology, script repair, or Planner model.
- Scalar gate is named `scalar_runtime_ready`.
- LM5AA routing validation is static-only and expects `routability_evaluated == false`.
- Runtime scalar readiness is proven by live receipt/anchor construction plus LM8B extraction/assembly.
- Worker request uses neutral `build_local_worker_turn_context(...)` and `render_local_worker_turn_request_payload(...)`.
- Worker publication uses `run_two_pass_worker_publication(...)` unchanged.
- Worker action is exactly `draft_gh_set_value_params` with `{"value": number}`.
- Trusted GUID comes only from live fixture anchor and applier/runtime binding.
- Worker-visible/source artifacts do not contain raw GUID.
- Full GUID appears only in `live_create_scalar_summary.json` and `live_set_value_summary.json`.
- `verify_scalar_output_summary.json` and `decision.json` are GUID hash/presence only.
- Acceptance is verifier-floor: final `gh_get_value` within `1e-9` of `7.5`.
- No live run in implementation PR.
