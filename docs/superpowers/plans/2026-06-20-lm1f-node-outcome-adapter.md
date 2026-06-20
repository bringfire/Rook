# LM1F NodeOutcome Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, non-live adapter that converts existing tool result dictionaries plus optional LM1D `script_receipt` evidence into prepared LM1E `NodeOutcome` objects.

**Architecture:** Create `rook.learning.plan_graph_outcomes` as the bridge between LM1B `ToolResultView` and LM1E `PlanGraph`. Keep `ToolResultView` and `normalize_tool_result(...)` in pure `rook.agent.chat.tool_result_view`; `tool_contracts.py` only re-exports them for compatibility. The adapter imports the pure result view, extracts only `result["data"]["script_receipt"]`, applies a tiny artifact-status mapping, packages `NodeEvidence`, and emits narrow deterministic `memory_updates`.

**Tech Stack:** Python 3, dataclasses already defined in `rook.learning.plan_graph`, pytest, `copy.deepcopy`.

---

## Scope Guardrails

This plan implements only the approved LM1F spec:

- No ChatRunner integration.
- No PlanGraph execution, state walking, graph mutation, or scheduler behavior.
- No ToolDispatcher changes.
- No server/MCP wire-shape changes.
- No individual tool migration.
- No verifier calls.
- No Rhino/GH live dependency.
- No retry policy beyond returning a prepared `NodeOutcome`.
- No escalation policy beyond the explicit status mapping.
- No generic result ontology.
- No LM2 capability registry.
- No parsing GUIDs, messages, errors, or free-form text.
- No Claude/RookChat presentation-layer heuristics.
- No arbitrary external MCP result presentation support in V0.

If implementation pressure points toward any of those, stop and ask for review.

## File Structure

- Create `mcp_server/src/rook/learning/plan_graph_outcomes.py`
  - Owns the public helper:
    `node_outcome_from_tool_result(result: Any) -> NodeOutcome`.
  - Owns private helpers for receipt extraction, status mapping, evidence
    packaging, and memory updates.
  - Imports only:
    - `copy.deepcopy`
    - `typing.Any`
    - `rook.agent.chat.tool_result_view.ToolResultView`
    - `rook.agent.chat.tool_result_view.normalize_tool_result`
    - `rook.learning.plan_graph.NodeOutcome`
    - `rook.learning.plan_graph.NodeEvidence`

- Create `mcp_server/src/rook/agent/chat/tool_result_view.py`
  - Owns `ToolResultView`, `normalize_tool_result(...)`, and the result-view
    helper functions.
  - Imports only `dataclasses.dataclass`, `typing.Any`, and `typing.Literal`.

- Update `mcp_server/src/rook/agent/chat/tool_contracts.py`
  - Re-export `ToolResultView` and `normalize_tool_result(...)` from
    `.tool_result_view` for existing ChatRunner/tests.

- Create `mcp_server/tests/test_plan_graph_outcomes.py`
  - Pure, non-live tests using canned result dictionaries.
  - Verifies mapping, evidence, memory updates, copy behavior, and import
    boundaries.

- Do not modify:
  - `mcp_server/src/rook/learning/plan_graph.py`
  - ChatRunner, ToolDispatcher, server, registry, or any Rhino/GH code.

## Task 1: Add Failing Adapter Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph_outcomes.py`

- [ ] **Step 1: Create the failing test file**

Create `mcp_server/tests/test_plan_graph_outcomes.py` with this content:

```python
from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest

from rook.learning.plan_graph_outcomes import node_outcome_from_tool_result


def _receipt_result(
    artifact_status: str | None,
    *,
    success: bool = False,
    message: str | None = "script result message",
    error: str | None = None,
    mutation_guid: str | None = "component-guid",
    repair_guid: str | None = "repair-guid",
    repair_anchor: object | None = None,
):
    if repair_anchor is None:
        repair_anchor = {
            "component_guid": repair_guid,
            "pins_out": [{"name": "B", "type": "Brep"}],
        }
    receipt = {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "mutation": {
            "status": "created",
            "method": "gh_create_component_then_script",
            "component_guid": mutation_guid,
            "note": None,
        },
        "verification": {
            "status": "failed",
            "method": "gh_errors",
            "target_error_count": 1,
            "target_warning_count": 0,
            "unrelated_error_count": 0,
            "unrelated_warning_count": 0,
            "note": None,
        },
        "repair_anchor": repair_anchor,
    }
    if artifact_status is not None:
        receipt["artifact_status"] = artifact_status

    result = {
        "success": success,
        "data": {
            "script_receipt": receipt,
        },
    }
    if message is not None:
        result["message"] = message
    if error is not None:
        result["error"] = error
    return result


@pytest.mark.parametrize(
    "artifact_status,expected_status,expected_summary",
    [
        ("usable", "succeeded", "artifact usable"),
        ("created_with_errors", "needs_repair", "artifact needs repair"),
        ("written_with_errors", "needs_repair", "artifact needs repair"),
        ("verification_pending", "blocked", "verification pending"),
        ("unknown", "blocked", "verification unknown"),
    ],
)
def test_artifact_status_maps_to_node_outcome_status(
    artifact_status, expected_status, expected_summary
):
    outcome = node_outcome_from_tool_result(_receipt_result(artifact_status))

    assert outcome.status == expected_status
    assert outcome.memory_updates == {
        "facts": {
            "component_guid": "component-guid",
            "repair_anchor": {
                "component_guid": "repair-guid",
                "pins_out": [{"name": "B", "type": "Brep"}],
            },
        },
        "node_summary": expected_summary,
    }


@pytest.mark.parametrize(
    "result,expected_status,expected_summary",
    [
        ({"success": True, "message": "ok"}, "succeeded", "tool succeeded"),
        ({"success": False, "error": "bad input"}, "failed", "tool failed"),
        ({"status": "loaded"}, "blocked", "tool blocked"),
    ],
)
def test_missing_receipt_falls_back_to_tool_result_view(
    result, expected_status, expected_summary
):
    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == expected_status
    assert outcome.evidence.receipt is None
    assert outcome.evidence.repair_anchor is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": expected_summary,
    }


@pytest.mark.parametrize("artifact_status", [None, "future_status"])
def test_missing_or_unrecognized_artifact_status_falls_back_but_carries_receipt(
    artifact_status,
):
    result = _receipt_result(artifact_status, success=True)

    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == "succeeded"
    assert outcome.evidence.receipt == result["data"]["script_receipt"]
    assert outcome.evidence.repair_anchor == result["data"]["script_receipt"]["repair_anchor"]
    assert outcome.memory_updates["node_summary"] == "tool succeeded"
    assert outcome.memory_updates["facts"]["component_guid"] == "component-guid"


def test_evidence_preserves_tool_result_view_fields_and_verification_note():
    result = {
        "success": False,
        "data": {
            "verified": False,
            "verification_note": "verification failed note",
        },
    }

    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == "failed"
    assert outcome.evidence.tool_status == "failed"
    assert outcome.evidence.verified is False
    assert outcome.evidence.message == "verification failed note"
    assert outcome.evidence.error is None
    assert outcome.message is None
    assert outcome.error is None


def test_message_wins_over_verification_note_and_error_is_preserved():
    result = {
        "success": False,
        "message": "top message",
        "error": "top error",
        "data": {
            "verified": False,
            "message": "nested verification note",
        },
    }

    outcome = node_outcome_from_tool_result(result)

    assert outcome.evidence.message == "top message"
    assert outcome.evidence.error == "top error"
    assert outcome.message == "top message"
    assert outcome.error == "top error"


def test_memory_component_guid_falls_back_to_repair_anchor_guid():
    result = _receipt_result(
        "created_with_errors",
        mutation_guid=None,
        repair_guid="anchor-guid",
    )

    outcome = node_outcome_from_tool_result(result)

    assert outcome.memory_updates["facts"]["component_guid"] == "anchor-guid"


def test_memory_ignores_non_dict_repair_anchor_and_does_not_parse_messages():
    result = _receipt_result(
        "created_with_errors",
        message="Use component 11111111-1111-1111-1111-111111111111",
        mutation_guid=None,
        repair_anchor="not a dict",
    )

    outcome = node_outcome_from_tool_result(result)

    assert outcome.evidence.repair_anchor is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": "artifact needs repair",
    }


def test_non_dict_result_is_blocked_with_empty_evidence_fields():
    outcome = node_outcome_from_tool_result("plain string result")

    assert outcome.status == "blocked"
    assert outcome.evidence.tool_status is None
    assert outcome.evidence.verified is None
    assert outcome.evidence.receipt is None
    assert outcome.evidence.repair_anchor is None
    assert outcome.evidence.message is None
    assert outcome.evidence.error is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": "tool blocked",
    }


def test_adapter_deep_copies_receipt_repair_anchor_and_memory_facts():
    result = _receipt_result("created_with_errors")

    outcome = node_outcome_from_tool_result(result)

    result["data"]["script_receipt"]["artifact_status"] = "mutated"
    result["data"]["script_receipt"]["repair_anchor"]["pins_out"][0]["name"] = "Mutated"

    assert outcome.evidence.receipt["artifact_status"] == "created_with_errors"
    assert outcome.evidence.repair_anchor["pins_out"][0]["name"] == "B"
    assert outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] == "B"

    outcome.evidence.receipt["repair_anchor"]["pins_out"][0]["name"] = "ReceiptOnly"
    assert outcome.evidence.repair_anchor["pins_out"][0]["name"] == "B"
    assert outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] == "B"

    outcome.evidence.repair_anchor["pins_out"][0]["name"] = "EvidenceOnly"
    assert outcome.evidence.receipt["repair_anchor"]["pins_out"][0]["name"] == "ReceiptOnly"
    assert outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] == "B"

    outcome.memory_updates["facts"]["repair_anchor"]["pins_out"][0]["name"] = "MemoryOnly"
    assert outcome.evidence.receipt["repair_anchor"]["pins_out"][0]["name"] == "ReceiptOnly"
    assert outcome.evidence.repair_anchor["pins_out"][0]["name"] == "EvidenceOnly"


def test_receipt_extraction_only_uses_internal_data_script_receipt_location():
    result = {
        "success": True,
        "script_receipt": {
            "artifact_status": "created_with_errors",
            "repair_anchor": {"component_guid": "top-level"},
        },
    }

    outcome = node_outcome_from_tool_result(result)

    assert outcome.status == "succeeded"
    assert outcome.evidence.receipt is None
    assert outcome.memory_updates == {
        "facts": {},
        "node_summary": "tool succeeded",
    }


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_plan_graph_outcomes_uses_pure_tool_result_view_boundary():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_outcomes.py"
    )

    assert "rook.agent.chat.tool_result_view" in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.learning.plan_graph" in imports


def test_tool_result_view_stays_pure():
    imports = _direct_import_modules("mcp_server/src/rook/agent/chat/tool_result_view.py")

    assert imports <= {"dataclasses", "typing"}


def test_importing_plan_graph_outcomes_does_not_load_tool_dispatcher():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_outcomes\n"
        "if 'rook.agent.tool_dispatcher' in sys.modules:\n"
        "    raise SystemExit('rook.agent.tool_dispatcher loaded')\n"
    )

    subprocess.run([sys.executable, "-c", probe], check=True, env=env)


def test_core_modules_do_not_import_adapter_or_each_other():
    tool_contracts_imports = _direct_import_modules(
        "mcp_server/src/rook/agent/chat/tool_contracts.py"
    )
    plan_graph_imports = _direct_import_modules("mcp_server/src/rook/learning/plan_graph.py")

    assert "rook.learning.plan_graph" not in tool_contracts_imports
    assert "rook.learning.plan_graph_outcomes" not in tool_contracts_imports
    assert "rook.agent.chat.tool_contracts" not in plan_graph_imports
    assert "rook.learning.plan_graph_outcomes" not in plan_graph_imports
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_outcomes.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rook.learning.plan_graph_outcomes'`.

Do not commit yet. These tests are intentionally red until Task 2.

## Task 2: Implement NodeOutcome Adapter

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph_outcomes.py`
- Test: `mcp_server/tests/test_plan_graph_outcomes.py`

- [ ] **Step 1: Create the adapter module**

Create `mcp_server/src/rook/learning/plan_graph_outcomes.py` with this content:

```python
from copy import deepcopy
from typing import Any

from rook.agent.chat.tool_result_view import ToolResultView, normalize_tool_result
from rook.learning.plan_graph import NodeEvidence, NodeOutcome


_ARTIFACT_STATUS_TO_OUTCOME = {
    "usable": "succeeded",
    "created_with_errors": "needs_repair",
    "written_with_errors": "needs_repair",
    "verification_pending": "blocked",
    "unknown": "blocked",
}

_ARTIFACT_STATUS_TO_SUMMARY = {
    "usable": "artifact usable",
    "created_with_errors": "artifact needs repair",
    "written_with_errors": "artifact needs repair",
    "verification_pending": "verification pending",
    "unknown": "verification unknown",
}

_TOOL_STATUS_TO_OUTCOME = {
    "success": "succeeded",
    "failed": "failed",
}

_TOOL_STATUS_TO_SUMMARY = {
    "success": "tool succeeded",
    "failed": "tool failed",
}


def _extract_script_receipt(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if not isinstance(data, dict):
        return None
    receipt = data.get("script_receipt")
    return deepcopy(receipt) if isinstance(receipt, dict) else None


def _artifact_status(receipt: dict[str, Any] | None) -> str | None:
    if not isinstance(receipt, dict):
        return None
    value = receipt.get("artifact_status")
    return value if isinstance(value, str) else None


def _repair_anchor(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(receipt, dict):
        return None
    value = receipt.get("repair_anchor")
    return deepcopy(value) if isinstance(value, dict) else None


def _outcome_status(view: ToolResultView, receipt: dict[str, Any] | None) -> str:
    artifact_status = _artifact_status(receipt)
    mapped = _ARTIFACT_STATUS_TO_OUTCOME.get(artifact_status)
    if mapped is not None:
        return mapped
    return _TOOL_STATUS_TO_OUTCOME.get(view.status, "blocked")


def _node_summary(view: ToolResultView, receipt: dict[str, Any] | None) -> str:
    artifact_status = _artifact_status(receipt)
    mapped = _ARTIFACT_STATUS_TO_SUMMARY.get(artifact_status)
    if mapped is not None:
        return mapped
    return _TOOL_STATUS_TO_SUMMARY.get(view.status, "tool blocked")


def _component_guid_from_receipt(
    receipt: dict[str, Any] | None,
    repair_anchor: dict[str, Any] | None,
) -> str | None:
    if isinstance(receipt, dict):
        mutation = receipt.get("mutation")
        if isinstance(mutation, dict):
            component_guid = mutation.get("component_guid")
            if isinstance(component_guid, str) and component_guid:
                return component_guid
    if isinstance(repair_anchor, dict):
        component_guid = repair_anchor.get("component_guid")
        if isinstance(component_guid, str) and component_guid:
            return component_guid
    return None


def _memory_updates(
    view: ToolResultView,
    receipt: dict[str, Any] | None,
    repair_anchor: dict[str, Any] | None,
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    component_guid = _component_guid_from_receipt(receipt, repair_anchor)
    if component_guid is not None:
        facts["component_guid"] = component_guid
    if repair_anchor is not None:
        facts["repair_anchor"] = deepcopy(repair_anchor)
    return {
        "facts": facts,
        "node_summary": _node_summary(view, receipt),
    }


def node_outcome_from_tool_result(result: Any) -> NodeOutcome:
    view = normalize_tool_result(result)
    receipt = _extract_script_receipt(result)
    repair_anchor = _repair_anchor(receipt)
    evidence = NodeEvidence(
        tool_status=view.status,
        verified=view.verified,
        receipt=deepcopy(receipt) if receipt is not None else None,
        repair_anchor=deepcopy(repair_anchor) if repair_anchor is not None else None,
        message=view.message or view.verification_note,
        error=view.error,
    )
    return NodeOutcome(
        status=_outcome_status(view, receipt),
        evidence=evidence,
        memory_updates=_memory_updates(view, receipt, repair_anchor),
        message=view.message,
        error=view.error,
    )
```

- [ ] **Step 2: Run the adapter tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_outcomes.py -q
```

Expected: PASS.

- [ ] **Step 3: Run adjacent focused tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py mcp_server/tests/test_rookchat_tool_contracts.py -q
```

Expected: PASS.

- [ ] **Step 4: Run compile check**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/agent/chat/tool_result_view.py mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/src/rook/learning/plan_graph_outcomes.py
```

Expected: no output and exit code `0`.

- [ ] **Step 5: Run boundary greps**

Run:

```powershell
rg -n "tool_contracts" mcp_server/src/rook/learning/plan_graph_outcomes.py
rg -n "plan_graph" mcp_server/src/rook/agent/chat/tool_contracts.py
rg -n "tool_contracts|plan_graph_outcomes" mcp_server/src/rook/learning/plan_graph.py
```

Expected: all three commands return no matches. `rg` may exit with code `1`
for no matches; that is expected.

- [ ] **Step 6: Commit the adapter**

Run:

```powershell
git add mcp_server/src/rook/learning/plan_graph_outcomes.py mcp_server/tests/test_plan_graph_outcomes.py
git commit -m "feat: add PlanGraph outcome adapter"
```

## Task 3: Final Verification And Hygiene

**Files:**
- Verify: `mcp_server/src/rook/learning/plan_graph_outcomes.py`
- Verify: `mcp_server/src/rook/learning/plan_graph.py`
- Verify: `mcp_server/src/rook/agent/chat/tool_contracts.py`
- Verify: `mcp_server/tests/test_plan_graph_outcomes.py`
- Verify: `mcp_server/tests/test_plan_graph.py`
- Verify: `mcp_server/tests/test_rookchat_tool_contracts.py`

- [ ] **Step 1: Run the focused LM1F suite**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph.py mcp_server/tests/test_rookchat_tool_contracts.py -q
```

Expected: PASS.

- [ ] **Step 2: Run compile checks**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/agent/chat/tool_result_view.py mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/src/rook/learning/plan_graph_outcomes.py
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Run boundary checks**

Run:

```powershell
rg -n "tool_contracts" mcp_server/src/rook/learning/plan_graph_outcomes.py
rg -n "plan_graph" mcp_server/src/rook/agent/chat/tool_contracts.py
rg -n "tool_contracts|plan_graph_outcomes" mcp_server/src/rook/learning/plan_graph.py
```

Expected: all three commands return no matches. `rg` may exit with code `1`
for no matches; that is expected.

- [ ] **Step 4: Run diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

- `git diff --check` exits `0`.
- `git status --short --branch` shows only the LM1F branch and no unstaged
  runtime artifacts.

- [ ] **Step 5: Commit final fixes if any were needed**

If Task 3 required code or test fixes, commit only those fixes:

```powershell
git add mcp_server/src/rook/learning/plan_graph_outcomes.py mcp_server/tests/test_plan_graph_outcomes.py
git commit -m "test: verify LM1F outcome adapter"
```

If no fixes were needed and the working tree is clean, do not create an empty
commit.

## Review Checkpoints

Use review checkpoints after:

- Task 2: adapter implementation and focused tests are green.
- Task 3: final verification and hygiene are complete.

At each checkpoint, confirm:

- `plan_graph_outcomes.py` is pure and non-live.
- `node_outcome_from_tool_result(result: Any) -> NodeOutcome` is the only public
  helper.
- Receipts are extracted only from `result["data"]["script_receipt"]`.
- Receipt interpretation is limited to the explicit `artifact_status` mapping.
- Unknown or missing `artifact_status` falls back to `ToolResultView.status`
  while carrying receipt evidence.
- `verification_note` is preserved through `NodeEvidence.message` fallback.
- `memory_updates` facts come only from structured receipt fields.
- No text parsing, ChatRunner integration, dispatcher/server changes, public MCP
  changes, PlanGraph execution, verifier calls, or capability registry work.

## Self-Review Notes

Spec coverage:

- Public API: Task 2.
- Module boundary/import direction: Tasks 2 and 3.
- Receipt extraction location: Task 2 tests and implementation.
- Outcome status mapping: Task 1 tests and Task 2 implementation.
- Evidence packaging, including verification-note fallback: Task 1 tests and
  Task 2 implementation.
- Narrow memory updates and deterministic summaries: Task 1 tests and Task 2
  implementation.
- Deep-copy/no-alias behavior: Task 1 tests and Task 2 implementation.
- Non-live/no-integration guardrails: boundary tests and greps in Tasks 1-3.

Completeness scan:

- No unresolved markers.

Type consistency:

- The plan uses `NodeOutcome`, `NodeEvidence`, `ToolResultView`, and
  `normalize_tool_result(...)` exactly as defined in current source.
- The public helper name matches the LM1F spec exactly.
