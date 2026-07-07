# LM7B Request-Driven Live Splice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic LM7B sibling live probe that validates the canonical LM7A `PlannerWorkerContractRequest`, materializes its contract/routing, and drives the frozen one-turn worker splice to a receipted terminal outcome.

**Architecture:** Add a new script-local integration runner, not a new LM6A mode. LM7B owns request provenance, `workflow_validate`, materialization, runtime routability, and LM7B artifacts, while reusing existing LM6A helper functions for bounded summaries, worker publication decisions, leak checks, action application, and live repair/verify dispatch.

**Tech Stack:** Python 3.10, pytest, existing Rook MCP server agent modules, existing LM6A script helpers, direct Ollama two-pass worker publication helper.

---

## File Structure

Create:

- `scripts/lm7b_request_driven_live_splice_probe.py`
  - Sibling probe script.
  - Owns canonical planner request, authoring validation gate, materialization call, runtime routability gate, LM7B run directory, LM7B manifest, and LM7B decision records.
  - Imports LM6A helpers where clean; does not alter LM6A behavior.

- `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`
  - Faked deterministic script tests.
  - Must not require Rhino, Grasshopper, Ollama, or live model calls.

Create:

- `docs/superpowers/plans/2026-07-07-lm7b-request-driven-live-splice.md`
  - This implementation plan.

Already created in the spec branch:

- `docs/superpowers/specs/2026-07-07-lm7b-request-driven-live-splice-design.md`

Do not modify by default:

- `scripts/lm6a_live_worker_splice_probe.py`
- `scripts/lm_worker_two_pass_publication.py`
- `mcp_server/src/rook/**/*.py`

Contingency only:

- If direct LM6A helper reuse is blocked by a concrete implementation failure, stop and report the blocker before extracting helpers.
- If a helper extraction is approved, add focused LM6A preservation tests before changing behavior. The default plan assumes no helper extraction.

---

## Task 1: Script Skeleton, Canonical Request, CLI, Fingerprints

**Files:**

- Create: `scripts/lm7b_request_driven_live_splice_probe.py`
- Create: `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`

- [ ] **Step 1: Write the failing script-load, CLI, and canonical request tests**

Create `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py` with:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from rook.agent.planner_worker_contract_request import (
    LM7A_TEMPLATE_ID,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    materialize_planner_worker_contract_request,
)
from rook.agent.workflow_validate import validate_planner_worker_contract_request


def _script_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "lm7b_request_driven_live_splice_probe.py"
    )


def _load_script():
    path = _script_path()
    spec = importlib.util.spec_from_file_location(
        "lm7b_request_driven_live_splice_probe",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROBE = _load_script()


def test_cli_defaults_are_canonical() -> None:
    args = PROBE._args([])

    assert args.model == "gemma4:12b-it-qat"
    assert args.endpoint == "http://localhost:11434/api/chat"
    assert args.temperature == 0
    assert args.timeout_s == 120
    assert args.excerpt_chars == 1200
    assert args.run_dir == "probe_runs"


def test_cli_forbids_request_phase_and_retry_options() -> None:
    with pytest.raises(SystemExit):
        PROBE._args(["--request-json", "request.json"])
    with pytest.raises(SystemExit):
        PROBE._args(["--phase", "receipt_recon"])
    with pytest.raises(SystemExit):
        PROBE._args(["--retry-clean-observation"])


def test_canonical_planner_request_matches_lm7a_schema_and_validates() -> None:
    request = PROBE._canonical_planner_request()

    assert request["schema"] == PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA
    assert request["template_id"] == LM7A_TEMPLATE_ID
    assert request["initial_params"] == {
        "create_script": {"pins_out": ["A:double"]}
    }
    assert request["intent_slots"] == [
        {
            "intent_id": "desired_output_value",
            "status": "unresolved",
            "source_path": "planner.intent.desired_output_value",
            "description": "Desired output value was not provided.",
        }
    ]

    report = validate_planner_worker_contract_request(request)
    assert report["valid"] is True

    materialization = materialize_planner_worker_contract_request(request)
    assert materialization.diagnostics == ()
    assert materialization.workflow_contract_payload is not None
    assert materialization.resolved_routing_artifact is not None
    assert materialization.worker_node_ids == ("repair_same_component",)


def test_fingerprint_is_stable_against_dict_order() -> None:
    request = PROBE._canonical_planner_request()
    reordered = {
        "intent_slots": request["intent_slots"],
        "routing_delta": request["routing_delta"],
        "initial_params": request["initial_params"],
        "template_id": request["template_id"],
        "schema": request["schema"],
    }

    assert PROBE._fingerprint(request) == PROBE._fingerprint(reordered)
    assert PROBE._fingerprint(request).startswith("sha256:")


def test_manifest_records_request_driven_identity() -> None:
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        request_fingerprint="sha256:req",
        workflow_validate_report_fingerprint="sha256:report",
    )

    assert manifest["script_schema"] == "rook.lm7b_request_driven_live_splice_probe:v1"
    assert manifest["planner_request_source"] == "script_local_canonical_lm7a_request"
    assert manifest["worker_retry_enabled"] is False
    assert manifest["request_fingerprint"] == "sha256:req"
    assert manifest["workflow_validate_report_fingerprint"] == "sha256:report"
```

- [ ] **Step 2: Run the new tests and verify they fail because the script does not exist**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  -q
```

Expected: fail during import with `FileNotFoundError` for `scripts/lm7b_request_driven_live_splice_probe.py`.

- [ ] **Step 3: Create the minimal LM7B script skeleton**

Create `scripts/lm7b_request_driven_live_splice_probe.py`:

```python
#!/usr/bin/env python
"""LM7B request-driven live worker splice probe.

LM7B validates the canonical LM7A PlannerWorkerContractRequest, materializes
its workflow contract and worker-visible source routing, then drives the frozen
one-turn LM6 worker splice with that provenance head.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
for _path in (str(_SCRIPT_DIR), str(_REPO_ROOT), str(_MCP_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from lm6a_live_worker_splice_probe import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_EXCERPT_CHARS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_S,
)
from rook.agent.planner_worker_contract_request import (  # noqa: E402
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
)


SCRIPT_SCHEMA = "rook.lm7b_request_driven_live_splice_probe:v1"
PLANNER_REQUEST_SOURCE = "script_local_canonical_lm7a_request"


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LM7B request-driven live worker splice probe."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--excerpt-chars", type=int, default=DEFAULT_EXCERPT_CHARS)
    parser.add_argument("--run-dir", default="probe_runs")
    return parser.parse_args(argv)


def _canonical_planner_request() -> dict[str, Any]:
    return {
        "schema": PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
        "template_id": LM7A_TEMPLATE_ID,
        "initial_params": {
            "create_script": {
                "pins_out": ["A:double"],
            },
        },
        "routing_delta": {
            "enable_routes": [],
            "disable_routes": [],
            "set_required": {},
            "add_unresolved_intent_routes": [
                {
                    "route_id": "missing_desired_output_value",
                    "source_class": "planner_user_intent",
                    "source_path": PLANNER_INTENT_SOURCE_PATH,
                    "purpose": "unresolved_intent",
                    "required": False,
                }
            ],
        },
        "intent_slots": [
            {
                "intent_id": DESIRED_OUTPUT_VALUE_INTENT_ID,
                "status": "unresolved",
                "source_path": PLANNER_INTENT_SOURCE_PATH,
                "description": "Desired output value was not provided.",
            }
        ],
    }


def _canonical_json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def _fingerprint(value: Any) -> str:
    rendered = json.dumps(
        _canonical_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_json_value(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _git_short_sha() -> str:
    import subprocess

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
    run_dir = Path(run_root) / f"lm7b-{timestamp}-{_git_short_sha()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def _manifest(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    request_fingerprint: str | None,
    workflow_validate_report_fingerprint: str | None,
) -> dict[str, Any]:
    return {
        "script_schema": SCRIPT_SCHEMA,
        "git_commit": _git_short_sha(),
        "planner_request_source": PLANNER_REQUEST_SOURCE,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "model": model,
        "endpoint": endpoint,
        "temperature": temperature,
        "worker_retry_enabled": False,
        "raw_artifacts": "local evidence under probe_runs; do not commit",
    }
```

- [ ] **Step 4: Run the Task 1 tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  -q
```

Expected: `5 passed`.

---

## Task 2: Authoring Gate, Materialization, and `rejected_by_validate`

**Files:**

- Modify: `scripts/lm7b_request_driven_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`

- [ ] **Step 1: Add failing tests for Gate 1**

Append these tests:

```python
def test_authoring_gate_rejects_invalid_workflow_validate_without_live_calls(
    monkeypatch,
    tmp_path: Path,
) -> None:
    live_called = False

    def fake_live(*args, **kwargs):
        nonlocal live_called
        live_called = True
        return {}

    monkeypatch.setattr(
        PROBE,
        "validate_planner_worker_contract_request",
        lambda payload: {
            "schema": "rook.workflow_validate_report:v1",
            "valid": False,
            "request_fingerprint": "sha256:req",
            "report_fingerprint": "sha256:report",
            "phases": {"request": {"diagnostics": [{"code": "invalid_schema"}]}},
            "resolved": {},
        },
    )
    monkeypatch.setattr(PROBE, "_run_live_create_and_verify", fake_live)

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert live_called is False
    assert decision["decision"] == "rejected_by_validate"
    assert decision["reason"] == "workflow_validate_failed"
    assert decision["workflow_validate_valid"] is False
    assert decision["workflow_validate_report_fingerprint"] == "sha256:report"
    assert decision["runtime_routing_valid"] is None
    assert decision["runtime_routability_evaluated"] is False
    assert (run_dir / "planner_request.json").exists()
    assert (run_dir / "workflow_validate_report.json").exists()
    assert not (run_dir / "live_create_summary.json").exists()


def test_materialization_uses_same_emitted_planner_request_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured_payloads = []

    def fake_validate(payload):
        captured_payloads.append(("validate", json.loads(json.dumps(payload))))
        return {
            "schema": "rook.workflow_validate_report:v1",
            "valid": True,
            "request_fingerprint": "sha256:req",
            "report_fingerprint": "sha256:report",
            "phases": {},
            "resolved": {},
        }

    class _Materialization:
        workflow_contract_payload = {"schema": "rook.workflow_contract:v1"}
        resolved_routing_artifact = {"schema": "rook.worker_visible_source_routing:v1"}
        worker_node_ids = ("repair_same_component",)
        diagnostics = ()

    def fake_materialize(payload):
        captured_payloads.append(("materialize", json.loads(json.dumps(payload))))
        return _Materialization()

    monkeypatch.setattr(PROBE, "validate_planner_worker_contract_request", fake_validate)
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        fake_materialize,
    )
    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        lambda *args, **kwargs: {
            "decision": {"decision": "gate_failed", "reason": "stop_for_test"}
        },
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    emitted = json.loads((run_dir / "planner_request.json").read_text(encoding="utf-8"))
    assert captured_payloads == [("validate", emitted), ("materialize", emitted)]
```

- [ ] **Step 2: Run the two new tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_authoring_gate_rejects_invalid_workflow_validate_without_live_calls `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_materialization_uses_same_emitted_planner_request_payload `
  -q
```

Expected: fail because `_run_probe` and Gate 1 are not implemented.

- [ ] **Step 3: Implement Gate 1 and the base decision record**

Add imports near the existing imports in `scripts/lm7b_request_driven_live_splice_probe.py`:

```python
from rook.agent.planner_worker_contract_request import (  # noqa: E402
    DESIRED_OUTPUT_VALUE_INTENT_ID,
    LM7A_TEMPLATE_ID,
    PLANNER_INTENT_SOURCE_PATH,
    PLANNER_WORKER_CONTRACT_REQUEST_SCHEMA,
    materialize_planner_worker_contract_request,
)
from rook.agent.workflow_validate import (  # noqa: E402
    validate_planner_worker_contract_request,
)
```

Update the existing planner import rather than duplicating it.

Add:

```python
DECISIONS = (
    "accepted",
    "rejected",
    "worker_declined",
    "gate_failed",
    "publication_failed",
    "rejected_by_validate",
)


def _decision_record(
    *,
    decision: str,
    reason: str,
    phase: str,
    request_fingerprint: str | None,
    workflow_validate_valid: bool | None,
    workflow_validate_report_fingerprint: str | None,
    runtime_routing_valid: bool | None = None,
    runtime_routability_evaluated: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"unknown LM7B decision: {decision}")
    record = {
        "schema": "rook.lm7b_decision:v1",
        "decision": decision,
        "reason": reason,
        "phase": phase,
        "request_fingerprint": request_fingerprint,
        "workflow_validate_valid": workflow_validate_valid,
        "workflow_validate_report_fingerprint": workflow_validate_report_fingerprint,
        "runtime_routing_valid": runtime_routing_valid,
        "runtime_routability_evaluated": runtime_routability_evaluated,
        "worker_retry_enabled": False,
        "live_repair_dispatched": False,
        "verify_repair_ran": False,
    }
    record.update(extra)
    return record
```

Add a temporary test seam `_run_live_create_and_verify` used by tests and later tasks:

```python
def _run_live_create_and_verify(*, agent: Any, workflow_contract: Any) -> dict[str, Any]:
    raise NotImplementedError("live create/verify is implemented in Task 3")
```

Add `_run_probe` with Gate 1:

```python
def _run_probe(
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    run_root: str | Path,
    agent: Any,
) -> Path:
    run_dir = _new_run_dir(run_root)
    request_payload = _canonical_planner_request()
    request_fingerprint = _fingerprint(request_payload)
    _write_json(run_dir / "planner_request.json", request_payload)

    workflow_report = validate_planner_worker_contract_request(request_payload)
    workflow_validate_valid = bool(workflow_report.get("valid") is True)
    workflow_report_fingerprint = workflow_report.get("report_fingerprint")
    workflow_report_fingerprint = (
        str(workflow_report_fingerprint)
        if workflow_report_fingerprint is not None
        else None
    )
    _write_json_value(run_dir / "workflow_validate_report.json", workflow_report)
    _write_json(
        run_dir / "manifest.json",
        _manifest(
            model=model,
            endpoint=endpoint,
            temperature=temperature,
            request_fingerprint=request_fingerprint,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
        ),
    )

    if workflow_validate_valid is not True:
        decision = _decision_record(
            decision="rejected_by_validate",
            reason="workflow_validate_failed",
            phase="request_authoring_validate",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=False,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    materialization = materialize_planner_worker_contract_request(request_payload)
    live = _run_live_create_and_verify(
        agent=agent,
        workflow_contract=materialization.workflow_contract_payload,
    )
    if isinstance(live.get("decision"), Mapping):
        _write_json(run_dir / "decision.json", dict(live["decision"]))
        return run_dir

    decision = _decision_record(
        decision="gate_failed",
        reason="runtime_not_implemented",
        phase="runtime_routability_validate",
        request_fingerprint=request_fingerprint,
        workflow_validate_valid=True,
        workflow_validate_report_fingerprint=workflow_report_fingerprint,
    )
    _write_json(run_dir / "decision.json", decision)
    return run_dir
```

- [ ] **Step 4: Run the Task 2 tests and verify they pass**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  -q
```

Expected: all current LM7B tests pass.

---

## Task 3: Contract-Driven Live Create/Verify and Runtime Routing Gate

**Files:**

- Modify: `scripts/lm7b_request_driven_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`

- [ ] **Step 1: Add failing tests for the runtime gate**

Append:

```python
from rook.agent.local_worker_source_routing_validator import (
    SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
    SourceRoutingDiagnostic,
    WorkerVisibleSourceRoutingValidationReport,
)


def _valid_workflow_report() -> dict:
    request = PROBE._canonical_planner_request()
    report = validate_planner_worker_contract_request(request)
    assert report["valid"] is True
    return report


def _materialization():
    return materialize_planner_worker_contract_request(PROBE._canonical_planner_request())


def test_runtime_routability_not_evaluated_gate_fails(monkeypatch, tmp_path: Path) -> None:
    materialization = _materialization()

    class _Report:
        schema = SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA
        valid = True
        routability_evaluated = False
        static_diagnostics = ()
        routability_diagnostics = ()

    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        lambda *args, **kwargs: {
            "workflow_contract": object(),
            "scaffold": object(),
            "graph": object(),
            "convention_packets": (),
            "anchor_binding": {"component_guid": "GUID-1", "language": "csharp"},
            "live_create_summary": {"repair_anchor": {"component_guid": "GUID-1"}},
            "verify_create_summary": {},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *args, **kwargs: _Report(),
    )
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        lambda payload: materialization,
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_routability_not_evaluated"
    assert decision["runtime_routing_valid"] is True
    assert decision["runtime_routability_evaluated"] is False
    assert not (run_dir / "worker_publication_row.json").exists()


def test_runtime_routability_error_gate_fails(monkeypatch, tmp_path: Path) -> None:
    materialization = _materialization()

    error = SourceRoutingDiagnostic(
        severity="error",
        code="required_route_unresolved",
        node_id="repair_same_component",
        route_id="repair_target_diagnostics",
        source_class="receipt_diagnostic",
        source_path="create_script.receipt.script_receipt.repair_anchor.target_errors",
        purpose="acceptance_criteria",
        message="Missing route.",
    )
    report = WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=False,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(error,),
    )

    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        lambda *args, **kwargs: {
            "workflow_contract": object(),
            "scaffold": object(),
            "graph": object(),
            "convention_packets": (),
            "anchor_binding": {"component_guid": "GUID-1", "language": "csharp"},
            "live_create_summary": {"repair_anchor": {"component_guid": "GUID-1"}},
            "verify_create_summary": {},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *args, **kwargs: report,
    )
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        lambda payload: materialization,
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    routing = json.loads(
        (run_dir / "runtime_routing_validation.json").read_text(encoding="utf-8")
    )
    assert decision["decision"] == "gate_failed"
    assert decision["reason"] == "runtime_routability_failed"
    assert decision["runtime_routing_valid"] is False
    assert decision["runtime_routability_evaluated"] is True
    assert routing["routability_diagnostics"][0]["code"] == "required_route_unresolved"


def test_optional_unresolved_intent_warning_does_not_fail_runtime_gate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    materialization = _materialization()

    warning = SourceRoutingDiagnostic(
        severity="warning",
        code="optional_route_unresolved",
        node_id="repair_same_component",
        route_id="missing_desired_output_value",
        source_class="planner_user_intent",
        source_path="planner.intent.desired_output_value",
        purpose="unresolved_intent",
        message="Optional unresolved intent is not routable by LM5X.",
    )
    report = WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=True,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(warning,),
    )
    worker_called = False

    def fake_worker_context(*args, **kwargs):
        nonlocal worker_called
        worker_called = True
        return {
            "request_payload": {"context": {"knowledge": [], "allowed_actions": []}},
            "acceptance_criteria_packet": {"criteria": []},
            "legacy_acceptance_criteria": {"source": "x", "criteria": []},
        }

    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        lambda *args, **kwargs: {
            "workflow_contract": object(),
            "scaffold": object(),
            "graph": object(),
            "convention_packets": (),
            "anchor_binding": {"component_guid": "GUID-1", "language": "csharp"},
            "live_create_summary": {"repair_anchor": {"component_guid": "GUID-1"}},
            "verify_create_summary": {},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *args, **kwargs: report,
    )
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        lambda payload: materialization,
    )
    monkeypatch.setattr(PROBE, "_build_worker_context", fake_worker_context)
    monkeypatch.setattr(
        PROBE,
        "run_two_pass_worker_publication",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "row": {
                    "status": "published",
                    "observation_action_intent_anomaly": False,
                    "observation_action_intent_reasons": [],
                },
                "response_payload": {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "observation",
                    "message": "Observed.",
                },
            },
        )(),
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert worker_called is True
    assert decision["decision"] == "worker_declined"
    assert decision["runtime_routing_valid"] is True
    assert decision["runtime_routability_evaluated"] is True
```

- [ ] **Step 2: Run the new runtime gate tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_runtime_routability_not_evaluated_gate_fails `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_runtime_routability_error_gate_fails `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_optional_unresolved_intent_warning_does_not_fail_runtime_gate `
  -q
```

Expected: fail because runtime gate and worker context are not implemented.

- [ ] **Step 3: Add runtime gate imports and helpers**

Add imports:

```python
from lm6a_live_worker_splice_probe import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_EXCERPT_CHARS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_S,
    _await,
    _extract_script_receipt,
    _hidden_answer_leaks,
    _live_result_summary,
    _phase_a_recon_summary,
    _routing_report_json,
)
from lm5k_worker_probe import _script_body_gotcha_packet  # noqa: E402
from rook.agent.local_worker_source_routing_validator import (  # noqa: E402
    validate_worker_visible_source_routing,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY  # noqa: E402
from rook.agent.plan_graph_workflow_contract import (  # noqa: E402
    compile_workflow_contract,
    load_workflow_contract_payload,
)
from rook.learning.plan_graph_runner import apply_verifier_step  # noqa: E402
```

Add:

```python
def _routing_report_has_errors(report: Any) -> bool:
    diagnostics = tuple(report.static_diagnostics) + tuple(report.routability_diagnostics)
    return any(diagnostic.severity == "error" for diagnostic in diagnostics)
```

- [ ] **Step 4: Replace the temporary live create test seam**

Replace `_run_live_create_and_verify`:

```python
def _run_live_create_and_verify(*, agent: Any, workflow_contract: Any) -> dict[str, Any]:
    scaffold = compile_workflow_contract(workflow_contract)
    graph = scaffold.graph
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = dict(
        workflow_contract.initial_params[0].execution_params
    )

    create_result = _await(agent.run_live_producer_node(graph, "create_script"))
    graph = create_result.graph
    verify_create = apply_verifier_step(graph, "verify_create", "create_script")
    graph = verify_create.graph
    receipt = _extract_script_receipt(graph, "create_script")
    create_evidence = graph.nodes["create_script"].evidence
    live_create_summary = _live_result_summary(
        node_id="create_script",
        tool_name=create_result.tool_name,
        node_status=graph.nodes["create_script"].status,
        outcome_status=str(create_result.outcome_status),
        verified=create_evidence.verified if create_evidence is not None else None,
        receipt=receipt,
    )
    verify_create_summary = {
        "verifier_node_id": "verify_create",
        "source_node_id": "create_script",
        "applied": verify_create.applied,
        "outcome_status": verify_create.outcome_status,
    }
    anchor = receipt.get("repair_anchor") if isinstance(receipt, Mapping) else None
    anchor_binding = {
        "component_guid": (
            anchor.get("component_guid") if isinstance(anchor, Mapping) else None
        ),
        "language": anchor.get("language") if isinstance(anchor, Mapping) else None,
    }
    return {
        "workflow_contract": workflow_contract,
        "scaffold": scaffold,
        "graph": graph,
        "convention_packets": (_script_body_gotcha_packet(),),
        "anchor_binding": anchor_binding,
        "live_create_summary": live_create_summary,
        "verify_create_summary": verify_create_summary,
    }
```

- [ ] **Step 5: Add runtime gate logic to `_run_probe`**

In `_run_probe`, after materialization, load the contract payload:

```python
    materialization = materialize_planner_worker_contract_request(request_payload)
    workflow_contract = load_workflow_contract_payload(
        materialization.workflow_contract_payload
    )
    routing_artifact = materialization.resolved_routing_artifact
    live = _run_live_create_and_verify(
        agent=agent,
        workflow_contract=workflow_contract,
    )
```

Then write live summaries and run LM5AA:

```python
    _write_json(run_dir / "live_create_summary.json", live["live_create_summary"])
    _write_json(run_dir / "verify_create_summary.json", live["verify_create_summary"])
    _write_json(run_dir / "phase_a_recon.json", _phase_a_recon_summary(live))

    if _hidden_answer_leaks(live["live_create_summary"]) or _hidden_answer_leaks(
        live["verify_create_summary"]
    ):
        decision = _decision_record(
            decision="gate_failed",
            reason="phase_a_hidden_answer_leak",
            phase="runtime_routability_validate",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    routing_report = validate_worker_visible_source_routing(
        routing_artifact,
        workflow_contract=live["workflow_contract"],
        graph=live["graph"],
        convention_packets=live["convention_packets"],
        worker_node_ids=tuple(materialization.worker_node_ids),
    )
    _write_json(
        run_dir / "runtime_routing_validation.json",
        _routing_report_json(routing_report),
    )

    if routing_report.routability_evaluated is not True:
        decision = _decision_record(
            decision="gate_failed",
            reason="runtime_routability_not_evaluated",
            phase="runtime_routability_validate",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
            runtime_routing_valid=bool(routing_report.valid),
            runtime_routability_evaluated=False,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    if _routing_report_has_errors(routing_report):
        decision = _decision_record(
            decision="gate_failed",
            reason="runtime_routability_failed",
            phase="runtime_routability_validate",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
            runtime_routing_valid=False,
            runtime_routability_evaluated=True,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir
```

Leave a call to `_build_worker_context(...)` before publication. That function is implemented in Task 4:

```python
    worker_context = _build_worker_context(live=live)
    request_payload = worker_context["request_payload"]
```

- [ ] **Step 6: Add a temporary `_build_worker_context` test seam**

Add:

```python
def _build_worker_context(*, live: Mapping[str, Any]) -> dict[str, Any]:
    raise NotImplementedError("worker context is implemented in Task 4")
```

- [ ] **Step 7: Run the runtime gate tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  -q
```

Expected: runtime gate failure tests pass. The optional warning test may still fail at publication until Task 5 fills in publication flow; keep it failing if the failure is only publication flow absence.

---

## Task 4: Acceptance Criteria Artifacts and Worker-Visible Request

**Files:**

- Modify: `scripts/lm7b_request_driven_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`

- [ ] **Step 1: Add failing tests for artifact-only packet and legacy projection**

Append:

```python
def test_worker_context_builds_request_from_lm7b_generated_acceptance_packet(
    monkeypatch,
    tmp_path: Path,
) -> None:
    packet = {
        "schema": "rook.acceptance_criteria_packet:v1",
        "source_set": {"source_classes": ["pin_contract"], "source_paths": ["x"]},
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned by LM7B.",
                "source": "create_script.initial_execution_params.pins_out",
                "source_class": "pin_contract",
            }
        ],
        "unresolved_intent": [],
        "fingerprint": "sha256:packet",
    }
    captured = {}
    monkeypatch.setattr(
        PROBE,
        "extract_acceptance_criteria_sources",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        PROBE,
        "assemble_acceptance_criteria_packet",
        lambda sources: packet,
    )
    monkeypatch.setattr(
        PROBE,
        "_require_receipt_mapping",
        lambda graph: {
            "language": "csharp",
            "repair_anchor": {
                "target_errors": [
                    "The name 'DefinitelyMissingSymbol' does not exist in the current context [14:13]"
                ]
            },
        },
    )
    monkeypatch.setattr(
        PROBE,
        "_require_create_execution_params",
        lambda graph: {
            "code": "A = DefinitelyMissingSymbol;",
            "pins_in": [],
            "pins_out": ["A:double"],
        },
    )
    monkeypatch.setattr(
        PROBE,
        "_stable_repair_anchor_value",
        lambda repair_anchor: {"component_guid": "GUID-1", "language": "csharp"},
    )
    monkeypatch.setattr(
        PROBE,
        "_acceptance_pin_contract_from_params",
        lambda params: {
            "source": "create_script.initial_execution_params.pins_out",
            "value": {"pins_out": ["A:double"], "output_requirements": []},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "_expected_repair_outcome_from_contract",
        lambda workflow_contract: "succeeded",
    )

    def fake_build_context(*args, **kwargs):
        captured["knowledge"] = kwargs["knowledge"]
        captured["allowed_actions"] = kwargs["allowed_actions"]
        return "context"

    def fake_render_request(context):
        knowledge = captured["knowledge"]
        acceptance_criteria = knowledge[1].content["fields"]["acceptance_criteria"]
        return {
            "context": {
                "knowledge": [
                    {
                        "packet_id": knowledge[1].packet_id,
                        "acceptance_criteria": {
                            "source": acceptance_criteria["source"],
                            "criteria": [
                                dict(item)
                                for item in acceptance_criteria["criteria"]
                            ],
                        },
                    }
                ],
                "allowed_actions": [{"action_id": "draft_repair_params"}],
            },
        }

    monkeypatch.setattr(PROBE, "build_local_worker_turn_context", fake_build_context)
    monkeypatch.setattr(
        PROBE,
        "render_local_worker_turn_request_payload",
        fake_render_request,
    )

    result = PROBE._build_worker_context(
        live={
            "workflow_contract": object(),
            "graph": object(),
            "convention_packets": (),
            "scaffold": object(),
            "repair_anchor": {"component_guid": "GUID-1", "language": "csharp"},
        },
        run_dir=tmp_path,
    )

    visible = json.loads(
        (tmp_path / "worker_visible_acceptance_criteria.json").read_text(
            encoding="utf-8"
        )
    )
    full_packet = json.loads(
        (tmp_path / "acceptance_criteria_packet.json").read_text(encoding="utf-8")
    )
    assert full_packet["schema"] == "rook.acceptance_criteria_packet:v1"
    assert visible == {
        "source": PROBE.ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
        "criteria": [
            {
                "criterion_id": "output_a_assigned",
                "description": "Output A must be assigned by LM7B.",
                "source": "create_script.initial_execution_params.pins_out",
            }
        ],
    }
    rendered_visible = json.dumps(visible, sort_keys=True)
    assert "source_class" not in rendered_visible
    assert "source_set" not in rendered_visible
    assert "fingerprint" not in rendered_visible
    request_rendered = json.dumps(result["request_payload"], sort_keys=True)
    assert "Output A must be assigned by LM7B." in request_rendered
    assert result["request_payload"]["context"]["allowed_actions"][0]["action_id"] == (
        "draft_repair_params"
    )


def test_worker_context_hidden_answer_leak_gate_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        PROBE,
        "extract_acceptance_criteria_sources",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        PROBE,
        "assemble_acceptance_criteria_packet",
        lambda sources: {
            "criteria": [
                {
                    "criterion_id": "leaky",
                    "description": "A = 42.0",
                    "source": "x",
                    "source_class": "pin_contract",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="worker context hidden answer leak"):
        PROBE._build_worker_context(
            live={
                "workflow_contract": object(),
                "graph": object(),
                "convention_packets": (),
                "scaffold": object(),
            },
            run_dir=tmp_path,
        )
```

- [ ] **Step 2: Run the new worker context tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_worker_context_builds_request_from_lm7b_generated_acceptance_packet `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_worker_context_hidden_answer_leak_gate_fails `
  -q
```

Expected: fail because `_build_worker_context` is still a test seam.

- [ ] **Step 3: Import acceptance criteria helpers and direct worker request renderers**

Expand the existing `from lm5k_worker_probe import _script_body_gotcha_packet`
import into:

```python
from lm5k_worker_probe import (  # noqa: E402
    ACCEPTANCE_CRITERIA_EVIDENCE_PACKET_ID,
    ACCEPTANCE_CRITERIA_LEGACY_SOURCE,
    _acceptance_pin_contract_from_params,
    _bounded_current_code,
    _bounded_target_diagnostics,
    _require_create_execution_params,
    _require_receipt_mapping,
    _script_body_gotcha_packet,
    _stable_repair_anchor_value,
)
```

Expand the existing `from lm6a_live_worker_splice_probe import (...)` import
block into:

```python
from lm6a_live_worker_splice_probe import (  # noqa: E402
    DEFAULT_ENDPOINT,
    DEFAULT_EXCERPT_CHARS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_S,
    _await,
    _extract_script_receipt,
    _hidden_answer_leaks,
    _legacy_acceptance_criteria_projection,
    _live_result_summary,
    _phase_a_recon_summary,
    _routing_report_json,
)
```

Add these new imports:

```python
from rook.agent.local_worker_acceptance_criteria import (  # noqa: E402
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (  # noqa: E402
    extract_acceptance_criteria_sources,
)
from rook.agent.local_worker_turn_context import (  # noqa: E402
    WorkerAllowedAction,
    WorkerKnowledgePacket,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_request import (  # noqa: E402
    render_local_worker_turn_request_payload,
)
```

Keep a single combined import block from `lm6a_live_worker_splice_probe`; do not duplicate names.

Do not import or call LM6A's `_worker_request_payload(...)` in LM7B. That helper
rebuilds the acceptance-criteria packet through the LM5K probe-contract path and
is not neutral for LM7B.

- [ ] **Step 4: Implement `_build_worker_context`**

Replace the test seam:

```python
def _expected_repair_outcome_from_contract(workflow_contract: Any) -> str:
    for rule in workflow_contract.rules:
        if rule.node_id != "verify_repair":
            continue
        for step in rule.steps_by_seen_count:
            expected = getattr(step, "expected_outcome", None)
            if isinstance(expected, str) and expected:
                return expected
    raise RuntimeError("verify_repair expected outcome missing")


def _lm7b_worker_evidence_packet(
    *,
    live: Mapping[str, Any],
    packet: Mapping[str, Any],
    visible: Mapping[str, Any],
) -> WorkerKnowledgePacket:
    graph = live["graph"]
    receipt = _require_receipt_mapping(graph)
    params = _require_create_execution_params(graph)
    receipt_repair_anchor = receipt.get("repair_anchor")
    if not isinstance(receipt_repair_anchor, Mapping):
        raise ValueError("receipt repair anchor missing")
    repair_anchor = live.get("repair_anchor")
    if not isinstance(repair_anchor, Mapping):
        facts = getattr(getattr(graph, "memory", None), "facts", {})
        repair_anchor = facts.get("repair_anchor") if isinstance(facts, Mapping) else None
    if not isinstance(repair_anchor, Mapping):
        raise ValueError("repair anchor missing")

    diagnostic_fields = {}
    if "target_errors" in receipt_repair_anchor:
        diagnostic_fields["target_errors"] = _bounded_target_diagnostics(
            receipt_repair_anchor.get("target_errors"),
            source=(
                "create_script.receipt.script_receipt.repair_anchor."
                "target_errors"
            ),
        )
    if "target_warnings" in receipt_repair_anchor:
        diagnostic_fields["target_warnings"] = _bounded_target_diagnostics(
            receipt_repair_anchor.get("target_warnings"),
            source=(
                "create_script.receipt.script_receipt.repair_anchor."
                "target_warnings"
            ),
        )
    if not diagnostic_fields:
        raise ValueError("target diagnostics missing")

    content = {
        "source": "planner_worker_contract_request",
        "trust": "high",
        "state": "post_verify_pre_worker",
        "fields": {
            "current_code": _bounded_current_code(params.get("code")),
            "language": {
                "value": receipt.get("language"),
                "source": "create_script.receipt.script_receipt.language",
            },
            "recommended_mode": {
                "value": "body",
                "source": "script_body_gotcha",
                "derivation": "existing worker-visible gotcha convention",
            },
            "repair_anchor": {
                "value": _stable_repair_anchor_value(repair_anchor),
                "source": "graph.memory.facts.repair_anchor",
            },
            "pin_contract": _acceptance_pin_contract_from_params(params),
            "target_diagnostics": {
                "source": (
                    "create_script.receipt.script_receipt.repair_anchor"
                ),
                "fields": diagnostic_fields,
            },
            "expected_repair_outcome": {
                "value": _expected_repair_outcome_from_contract(
                    live["workflow_contract"]
                ),
                "source": (
                    "workflow_contract.rules.verify_repair."
                    "expected_outcome"
                ),
            },
            "acceptance_criteria": dict(visible),
        },
    }
    return WorkerKnowledgePacket(
        packet_id=ACCEPTANCE_CRITERIA_EVIDENCE_PACKET_ID,
        kind="evidence",
        title="Acceptance-criteria repair evidence",
        content=content,
    )


def _render_lm7b_worker_turn_request(
    *,
    live: Mapping[str, Any],
    acceptance_packet: Mapping[str, Any],
    visible_acceptance_criteria: Mapping[str, Any],
) -> dict[str, Any]:
    evidence_packet = _lm7b_worker_evidence_packet(
        live=live,
        packet=acceptance_packet,
        visible=visible_acceptance_criteria,
    )
    context = build_local_worker_turn_context(
        live["scaffold"],
        live["graph"],
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(
            _script_body_gotcha_packet(),
            evidence_packet,
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={"type": "object", "required": ["code", "mode"]},
            ),
        ),
    )
    return dict(render_local_worker_turn_request_payload(context))


def _build_worker_context(
    *,
    live: Mapping[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    sources = extract_acceptance_criteria_sources(
        workflow_contract=live["workflow_contract"],
        graph=live["graph"],
        convention_packets=live["convention_packets"],
    )
    packet = assemble_acceptance_criteria_packet(sources)
    visible = _legacy_acceptance_criteria_projection(packet)
    if _hidden_answer_leaks(packet) or _hidden_answer_leaks(visible):
        raise ValueError("worker context hidden answer leak")

    request_payload = _render_lm7b_worker_turn_request(
        live=live,
        acceptance_packet=packet,
        visible_acceptance_criteria=visible,
    )
    if _hidden_answer_leaks(request_payload):
        raise ValueError("worker context hidden answer leak")

    _write_json_value(run_dir / "acceptance_criteria_packet.json", packet)
    _write_json(run_dir / "worker_visible_acceptance_criteria.json", visible)
    return {
        "acceptance_criteria_packet": packet,
        "legacy_acceptance_criteria": visible,
        "request_payload": request_payload,
    }
```

- [ ] **Step 5: Update `_run_probe` to handle worker context failures**

Replace the direct call:

```python
    worker_context = _build_worker_context(live=live)
```

with:

```python
    try:
        worker_context = _build_worker_context(live=live, run_dir=run_dir)
    except Exception as exc:
        reason = (
            "phase_a_hidden_answer_leak"
            if "hidden answer leak" in str(exc)
            else f"worker_context_failed:{type(exc).__name__}"
        )
        decision = _decision_record(
            decision="gate_failed",
            reason=reason,
            phase="runtime_routability_validate",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
            runtime_routing_valid=True,
            runtime_routability_evaluated=True,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir
    request_payload = worker_context["request_payload"]
```

- [ ] **Step 6: Run LM7B tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  -q
```

Expected: worker context tests pass. End-to-end publication tests are added in Task 5.

---

## Task 5: One-Turn Worker Publication, Action Apply, Dispatch, Decisions

**Files:**

- Modify: `scripts/lm7b_request_driven_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`

- [ ] **Step 1: Add failing tests for publication terminal paths**

Append:

```python
def _published_payload(kind: str, **extra) -> dict:
    payload = {"schema": "rook.local_worker_turn_response:v1", "kind": kind}
    payload.update(extra)
    return payload


def _patch_successful_gates(monkeypatch, *, response_payload, publication_row=None):
    materialization = _materialization()
    warning = SourceRoutingDiagnostic(
        severity="warning",
        code="optional_route_unresolved",
        node_id="repair_same_component",
        route_id="missing_desired_output_value",
        source_class="planner_user_intent",
        source_path="planner.intent.desired_output_value",
        purpose="unresolved_intent",
        message="Optional unresolved intent is not routable by LM5X.",
    )
    report = WorkerVisibleSourceRoutingValidationReport(
        schema=SOURCE_ROUTING_VALIDATION_REPORT_SCHEMA,
        valid=True,
        routability_evaluated=True,
        static_diagnostics=(),
        routability_diagnostics=(warning,),
    )
    monkeypatch.setattr(
        PROBE,
        "materialize_planner_worker_contract_request",
        lambda payload: materialization,
    )
    monkeypatch.setattr(
        PROBE,
        "_run_live_create_and_verify",
        lambda *args, **kwargs: {
            "workflow_contract": object(),
            "scaffold": object(),
            "graph": object(),
            "convention_packets": (),
            "anchor_binding": {"component_guid": "GUID-1", "language": "csharp"},
            "live_create_summary": {"repair_anchor": {"component_guid": "GUID-1"}},
            "verify_create_summary": {},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "validate_worker_visible_source_routing",
        lambda *args, **kwargs: report,
    )
    monkeypatch.setattr(
        PROBE,
        "_build_worker_context",
        lambda *args, **kwargs: {
            "request_payload": {"context": {"knowledge": [], "allowed_actions": []}},
            "acceptance_criteria_packet": {"criteria": []},
            "legacy_acceptance_criteria": {"source": "x", "criteria": []},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "run_two_pass_worker_publication",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "row": publication_row
                or {
                    "status": "published",
                    "observation_action_intent_anomaly": False,
                    "observation_action_intent_reasons": [],
                },
                "response_payload": response_payload,
            },
        )(),
    )


def test_publication_failure_writes_publication_failed(monkeypatch, tmp_path: Path) -> None:
    _patch_successful_gates(
        monkeypatch,
        response_payload=None,
        publication_row={"status": "pass2_lm5g_invalid", "failure_reason": "bad json"},
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    row = json.loads((run_dir / "worker_publication_row.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "publication_failed"
    assert decision["reason"] == "bad json"
    assert row["status"] == "pass2_lm5g_invalid"
    assert decision["worker_retry_enabled"] is False


def test_worker_declined_observation_has_no_retry_artifacts(monkeypatch, tmp_path: Path) -> None:
    _patch_successful_gates(
        monkeypatch,
        response_payload=_published_payload("observation", message="Observed."),
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "worker_declined"
    assert decision["reason"] == "worker_observed"
    assert not (run_dir / "retry_context.json").exists()
    assert not (run_dir / "worker_publication_rows.json").exists()
    assert (run_dir / "worker_publication_row.json").exists()


def test_worker_action_apply_rejection_writes_rejected(monkeypatch, tmp_path: Path) -> None:
    class _ApplyResult:
        applied = False
        reason = "invalid_mode"
        params_sha256 = None

    _patch_successful_gates(
        monkeypatch,
        response_payload={
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_repair_params",
            "rationale": "Acting.",
            "input": {"code": "A = 0.0;", "mode": "bad"},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "apply_worker_action_to_node",
        lambda *args, **kwargs: _ApplyResult(),
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "rejected"
    assert decision["reason"] == "worker_action_apply_failed:invalid_mode"
    assert decision["worker_action_input_sha256"].startswith("sha256:")
    assert (run_dir / "worker_action.json").exists()
    assert not (run_dir / "live_repair_summary.json").exists()


def test_action_accepted_path_delegates_live_repair_and_verify(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _ApplyResult:
        applied = True
        reason = None
        params_sha256 = "sha256:params"
        graph = object()

    _patch_successful_gates(
        monkeypatch,
        response_payload={
            "schema": "rook.local_worker_turn_response:v1",
            "kind": "action_request",
            "action_id": "draft_repair_params",
            "rationale": "Acting.",
            "input": {"code": "A = 0.0;", "mode": "body"},
        },
    )
    monkeypatch.setattr(
        PROBE,
        "apply_worker_action_to_node",
        lambda *args, **kwargs: _ApplyResult(),
    )
    monkeypatch.setattr(
        PROBE,
        "_dispatch_repair_and_verify",
        lambda **kwargs: {
            "decision": {
                "schema": "rook.lm7b_decision:v1",
                "decision": "accepted",
                "reason": "verify_repair_succeeded",
                "phase": "verify_repair",
                "request_fingerprint": "sha256:req",
                "workflow_validate_valid": True,
                "workflow_validate_report_fingerprint": "sha256:report",
                "runtime_routing_valid": True,
                "runtime_routability_evaluated": True,
                "worker_retry_enabled": False,
                "live_repair_dispatched": True,
                "verify_repair_ran": True,
            }
        },
    )

    run_dir = PROBE._run_probe(
        model="gemma4:12b-it-qat",
        endpoint="http://fake.local/api/chat",
        temperature=0,
        timeout_s=9,
        excerpt_chars=500,
        run_root=tmp_path,
        agent=None,
    )

    decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "accepted"
    assert decision["reason"] == "verify_repair_succeeded"
    assert (run_dir / "worker_action.json").exists()
```

- [ ] **Step 2: Run the new publication tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_publication_failure_writes_publication_failed `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_worker_declined_observation_has_no_retry_artifacts `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_worker_action_apply_rejection_writes_rejected `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_action_accepted_path_delegates_live_repair_and_verify `
  -q
```

Expected: fail because publication/action flow is not implemented.

- [ ] **Step 3: Add publication/action imports**

Add to the LM6A import block:

```python
    _decision_from_worker_action_apply,
    _decision_from_worker_publication,
    _dispatch_repair_and_verify,
    _pass1_decision_hidden_answer_failure,
    _worker_action_context,
```

Add:

```python
from lm_worker_two_pass_publication import run_two_pass_worker_publication  # noqa: E402
from rook.agent.plan_graph_worker_action_apply import (  # noqa: E402
    apply_worker_action_to_node,
)
```

- [ ] **Step 4: Add a decision metadata helper**

Add:

```python
def _with_lm7b_metadata(
    decision: Mapping[str, Any],
    *,
    request_fingerprint: str,
    workflow_validate_report_fingerprint: str | None,
    runtime_routing_valid: bool,
    runtime_routability_evaluated: bool,
) -> dict[str, Any]:
    copied = dict(decision)
    copied["schema"] = "rook.lm7b_decision:v1"
    copied["request_fingerprint"] = request_fingerprint
    copied["workflow_validate_valid"] = True
    copied["workflow_validate_report_fingerprint"] = (
        workflow_validate_report_fingerprint
    )
    copied["runtime_routing_valid"] = runtime_routing_valid
    copied["runtime_routability_evaluated"] = runtime_routability_evaluated
    copied["worker_retry_enabled"] = False
    copied["retry_attempted"] = False
    copied["retry_count"] = 0
    return copied
```

- [ ] **Step 5: Implement one-turn worker publication and dispatch in `_run_probe`**

After `request_payload = worker_context["request_payload"]`, add:

```python
    publication = run_two_pass_worker_publication(
        request_payload,
        model=model,
        endpoint=endpoint,
        temperature=temperature,
        timeout_s=timeout_s,
        excerpt_chars=excerpt_chars,
        decision_guard=_pass1_decision_hidden_answer_failure,
    )
    publication_row = dict(publication.row)
    if _hidden_answer_leaks(publication_row) or _hidden_answer_leaks(
        publication.response_payload
    ):
        decision = _decision_record(
            decision="publication_failed",
            reason="worker_publication_hidden_answer_leak",
            phase="worker_publication",
            request_fingerprint=request_fingerprint,
            workflow_validate_valid=True,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
            runtime_routing_valid=True,
            runtime_routability_evaluated=True,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir
    _write_json(run_dir / "worker_publication_row.json", publication_row)

    first_decision = _decision_from_worker_publication(
        publication_row=publication_row,
        response_payload=publication.response_payload,
    )
    if first_decision is not None:
        decision = _with_lm7b_metadata(
            first_decision,
            request_fingerprint=request_fingerprint,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
            runtime_routing_valid=True,
            runtime_routability_evaluated=True,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    response_payload = publication.response_payload
    action_input = response_payload["input"]
    action_context = _worker_action_context(
        response_payload=response_payload,
        run_dir=run_dir,
        excerpt_chars=excerpt_chars,
    )
    _write_json(run_dir / "worker_action.json", response_payload)
    apply_result = apply_worker_action_to_node(
        live["graph"],
        "repair_same_component",
        action_id=response_payload["action_id"],
        action_input=action_input,
        anchor_binding=live["anchor_binding"],
    )
    if apply_result.applied is not True:
        decision = _with_lm7b_metadata(
            _decision_from_worker_action_apply(
                apply_result,
                action_context=action_context,
            ),
            request_fingerprint=request_fingerprint,
            workflow_validate_report_fingerprint=workflow_report_fingerprint,
            runtime_routing_valid=True,
            runtime_routability_evaluated=True,
        )
        _write_json(run_dir / "decision.json", decision)
        return run_dir

    final = _dispatch_repair_and_verify(
        graph=apply_result.graph,
        agent=agent,
        params_sha256=apply_result.params_sha256,
        run_dir=run_dir,
        action_context=action_context,
    )
    decision = _with_lm7b_metadata(
        final["decision"],
        request_fingerprint=request_fingerprint,
        workflow_validate_report_fingerprint=workflow_report_fingerprint,
        runtime_routing_valid=True,
        runtime_routability_evaluated=True,
    )
    _write_json(run_dir / "decision.json", decision)
    return run_dir
```

Remove the temporary `runtime_not_implemented` decision path.

- [ ] **Step 6: Run LM7B tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  -q
```

Expected: LM7B tests pass.

---

## Task 6: Main Entrypoint, Static Guards, and Artifact Shape

**Files:**

- Modify: `scripts/lm7b_request_driven_live_splice_probe.py`
- Modify: `mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py`

- [ ] **Step 1: Add failing tests for `main`, hidden-answer guards, and no retry/request override**

Append:

```python
def test_main_prints_run_dir_and_decision(monkeypatch, tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "lm7b-demo"
    run_dir.mkdir()
    (run_dir / "decision.json").write_text(
        json.dumps({"decision": "accepted", "reason": "verify_repair_succeeded"}),
        encoding="utf-8",
    )
    seen = {}

    def fake_run_probe(**kwargs):
        seen.update(kwargs)
        return run_dir

    monkeypatch.setattr(PROBE, "_run_probe", fake_run_probe)

    assert PROBE.main(["--run-dir", str(tmp_path), "--model", "gemma4:12b-it-qat"]) == 0
    output = capsys.readouterr().out
    assert "LM7B request-driven live splice probe complete" in output
    assert f"run_dir={run_dir}" in output
    assert "decision=accepted" in output
    assert seen["model"] == "gemma4:12b-it-qat"
    assert seen["agent"] is not None


def test_lm7b_script_does_not_enable_retry_or_request_override() -> None:
    source = Path(PROBE.__file__).read_text(encoding="utf-8")

    for forbidden in [
        "--request-json",
        "--phase",
        "--retry-clean-observation",
        "lm6e_bounded_retry_context",
        "_retry_context_packet",
        "_request_payload_with_retry_context",
        "_worker_request_payload",
        "_acceptance_criteria_evidence_packet",
    ]:
        assert forbidden not in source
    assert '"worker_retry_enabled": False' in source


def test_hidden_answer_markers_are_not_in_canonical_request_or_manifest() -> None:
    request = PROBE._canonical_planner_request()
    manifest = PROBE._manifest(
        model="gemma4:12b-it-qat",
        endpoint="http://localhost:11434/api/chat",
        temperature=0,
        request_fingerprint="sha256:req",
        workflow_validate_report_fingerprint="sha256:report",
    )
    rendered = json.dumps({"request": request, "manifest": manifest}, sort_keys=True)

    for marker in [
        "PROBE_REPAIR_CODE",
        "A = 42.0",
        "BindStepSpec.base_params.code",
        "BindStepSpec.base_params",
        "repair_same_component.bind.base_params",
    ]:
        assert marker not in rendered
```

- [ ] **Step 2: Run the static tests and verify they fail**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_main_prints_run_dir_and_decision `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_lm7b_script_does_not_enable_retry_or_request_override `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py::test_hidden_answer_markers_are_not_in_canonical_request_or_manifest `
  -q
```

Expected: `main` test fails until main/build-agent are added. Static tests may already pass; keep them as guards.

- [ ] **Step 3: Add `_build_agent` and `main`**

Add:

```python
def _build_agent() -> Any:
    from rook.agent.base_agent import RookAgent
    from rook.server import _mcp_tool_executor

    return RookAgent(tool_executor=_mcp_tool_executor)


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    run_dir = _run_probe(
        model=args.model,
        endpoint=args.endpoint,
        temperature=args.temperature,
        timeout_s=args.timeout_s,
        excerpt_chars=args.excerpt_chars,
        run_root=args.run_dir,
        agent=_build_agent(),
    )
    decision_path = run_dir / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    print(
        "LM7B request-driven live splice probe complete: "
        f"run_dir={run_dir} decision={decision['decision']} "
        f"reason={decision['reason']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the full LM7B test file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  -q
```

Expected: all LM7B tests pass.

---

## Task 7: Nearby Seam Verification and Drift Gates

**Files:**

- Validate only; do not edit files unless a command exposes a real failure.

- [ ] **Step 1: Run focused and nearby seam tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_planner_worker_contract_request.py `
  mcp_server\tests\test_workflow_validate.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm7b_request_driven_live_splice_probe.py `
  mcp_server\tests\test_lm7b_request_driven_live_splice_probe.py
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Run whitespace/diff check**

Run:

```powershell
git diff --check main..HEAD
```

Expected: no output.

- [ ] **Step 4: Confirm exact diff scope**

Run:

```powershell
$expected = @(
  "docs/superpowers/plans/2026-07-07-lm7b-request-driven-live-splice.md",
  "docs/superpowers/specs/2026-07-07-lm7b-request-driven-live-splice-design.md",
  "mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py",
  "scripts/lm7b_request_driven_live_splice_probe.py"
)
$actual = git diff --name-only main..HEAD
Compare-Object $expected $actual
```

Expected: no output.

- [ ] **Step 5: Confirm no raw artifacts are staged or created**

Run:

```powershell
git status --short
git status --short --ignored probe_runs
```

Expected:

- no staged or unstaged `probe_runs/` artifacts
- known unrelated local dirt may remain:
  - `knowledge/gh/operations_knowledge.json`
  - `.understand-anything/`
  - unrelated Rook2 docs

- [ ] **Step 6: Confirm no prompt/publication/schema drift outside LM7B**

Run:

```powershell
git diff main..HEAD -- scripts\lm_worker_two_pass_publication.py scripts\lm6a_live_worker_splice_probe.py
```

Expected: no output.

- [ ] **Step 7: Confirm the LM7B script does not contain forbidden live-run variants**

Run:

```powershell
Select-String -Path scripts\lm7b_request_driven_live_splice_probe.py `
  -Pattern "--request-json","--phase","--retry-clean-observation","lm6e_bounded_retry_context"
```

Expected: no matches.

---

## Task 8: Implementation PR Handoff Notes

**Files:**

- No edits unless verification exposes drift.

- [ ] **Step 1: Summarize deterministic result**

Prepare the PR summary with:

```text
LM7B adds a request-driven live splice sibling script.

- Canonical script-local PlannerWorkerContractRequest is emitted and fingerprinted.
- workflow_validate is Gate 1 and rejects before live work.
- materialize_planner_worker_contract_request(...) is called on the same emitted request.
- Materialized routing artifact is used for runtime LM5AA routability.
- Worker-visible evidence remains LM5Y legacy projection.
- Retry is unavailable/default-off; one worker publication turn only.
- No live run in the implementation PR.
```

- [ ] **Step 2: Summarize verification**

Include the exact command results from Task 7.

- [ ] **Step 3: State post-merge runbook**

Record the post-merge command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm7b_request_driven_live_splice_probe.py
```

State that Rhino/Grasshopper must be open and ready, and that the live run is a
separate evidence step from synced `main`.

---

## Self-Review Checklist

- Spec coverage:
  - new sibling script: Task 1
  - canonical script-local request: Task 1
  - no request JSON/phase/retry CLI: Tasks 1 and 6
  - Gate 1 `workflow_validate`: Task 2
  - materialization from same emitted payload: Task 2
  - runtime LM5AA routability: Task 3
  - optional unresolved-intent warning does not fail gate: Task 3
  - artifact-only LM5W packet and legacy worker projection: Task 4
  - one-turn worker publication, action apply, dispatch decisions: Task 5
  - separate LM7B run dir and artifacts: Tasks 1, 2, 3, 4, 5
  - no live run in PR: Tasks 7 and 8
  - no LM6A/helper drift by default: Task 7

- Red-flag scan:
  - no unfinished markers or undefined behavior remains.

- Type consistency:
  - `request_fingerprint`, `workflow_validate_report_fingerprint`,
    `runtime_routing_valid`, and `runtime_routability_evaluated` are present in
    LM7B decision records.
  - `worker_retry_enabled` is always `False`.
  - `PlannerWorkerContractRequest` includes `intent_slots[].description`.
