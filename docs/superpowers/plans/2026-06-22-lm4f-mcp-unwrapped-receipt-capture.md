# LM4F MCP-unwrapped Script Receipt Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `_extract_script_receipt` (the PlanGraph receipt consumer) to find `script_receipt` in both the wrapped dispatcher/MCP-failure shape (`result["data"]["script_receipt"]`) and the MCP success-unwrapped shape (top-level `result["script_receipt"]`), so a live producer node projects correctly regardless of envelope shape.

**Architecture:** A single additive change to one function in `mcp_server/src/rook/learning/plan_graph_outcomes.py`: nested-first, top-level fallback. The existing nested branch runs first and is byte-stable; the top-level read is a pure fallback. No change to `_mcp_tool_executor`, `_format_tool_result`, or `normalize_tool_result`.

**Tech Stack:** Python 3.12, pytest (synchronous unit tests — these are pure functions, no asyncio).

## Global Constraints

- **Production diff confined to ONE function:** `_extract_script_receipt` in `mcp_server/src/rook/learning/plan_graph_outcomes.py`. No other production file changes.
- **Do NOT change** `_mcp_tool_executor` / `_format_tool_result` (documented, load-bearing) or `normalize_tool_result`. No invented `tool_status == "success"` inference.
- **Precedence + re-gate:** nested-first; both-present → nested wins. The top-level fallback is accepted ONLY for the MCP success-unwrapped shape — a dict with **none** of the envelope markers `data` / `success` / `ok` / `error`. NOT "any top-level receipt"; internal-envelope-looking dicts keep the original guardrail.
- **Diff guard (final):** `git diff --name-only main` must list ONLY:
  - `mcp_server/src/rook/learning/plan_graph_outcomes.py`
  - `mcp_server/tests/test_plan_graph_outcomes.py`
  - `docs/superpowers/specs/2026-06-22-lm4f-mcp-unwrapped-receipt-capture-design.md`
  - `docs/superpowers/plans/2026-06-22-lm4f-mcp-unwrapped-receipt-capture.md`
  - **No `knowledge/**` files** (runtime knowledge mutation must not enter LM4F), no `server.py`, no `tool_result_view.py`.
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Focused PlanGraph gate runs from the **repo root** (purity probes use repo-root-relative paths).

---

### Task 1: Top-level receipt fallback in `_extract_script_receipt` (+ tests)

Single right-sized task: one additive function change with its full test set. TDD — write the tests first, watch the top-level cases fail, add the fallback, watch them pass.

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_outcomes.py:35-42` (`_extract_script_receipt`)
- Test: `mcp_server/tests/test_plan_graph_outcomes.py` (append new tests + imports)

**Interfaces:**
- Consumes (existing, unchanged signatures):
  - `node_evidence_from_tool_result(result) -> NodeEvidence` (fields `.tool_status`, `.verified`, `.receipt`, `.repair_anchor`).
  - `apply_producer_result(graph, node_id, raw) -> ProducerStepResult` (`from rook.learning.plan_graph_runner import apply_producer_result`); fields `.applied`, `.outcome_status`, `.graph`.
  - `PlanGraph`, `PlanGraphNode` (`from rook.learning.plan_graph import ...`); node has `.status`, `.evidence`.
  - `OUTCOME_PROJECTION_ROLE_KEY` (`from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY`).
  - `_extract_script_receipt(result) -> dict | None` (private; imported directly for the function-level tests).
- Produces: the modified `_extract_script_receipt` — no signature change.

- [ ] **Step 1: Add imports + write the six failing tests**

In `mcp_server/tests/test_plan_graph_outcomes.py`, add to the existing import block:

```python
from rook.learning.plan_graph_outcomes import (
    node_evidence_from_tool_result,
    node_outcome_from_tool_result,
    _extract_script_receipt,
)
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.learning.plan_graph_runner import apply_producer_result
```

(The first import line already exists for the two public functions — extend it with `_extract_script_receipt` rather than duplicating.)

Then append these tests and helpers at the end of the file:

```python
# --- LM4F: MCP success-unwrapped top-level script_receipt -------------------

def _nested_usable_result(component_guid="comp-nested"):
    """Wrapped dispatcher / MCP-failure shape: receipt under data."""
    return {
        "success": True,
        "data": {
            "marker": "nested",
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": component_guid},
                "repair_anchor": {"component_guid": component_guid},
            },
        },
    }


def _top_level_usable_result(component_guid="comp-top"):
    """MCP success-unwrapped shape: receipt at the top level, no success/data key."""
    return {
        "component_guid": component_guid,
        "name": "TopLevelUsable",
        "code_length": 120,
        "script_receipt": {
            "version": 1,
            "operation": "create",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "created", "component_guid": component_guid},
            "repair_anchor": {"component_guid": component_guid},
        },
    }


def _ready_producer_graph():
    node = PlanGraphNode(
        id="create",
        intent="create",
        metadata={OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer"},
        status="ready",
    )
    return PlanGraph(nodes={"create": node})


def test_extract_receipt_nested_shape_unchanged_and_deepcopied():
    """Regression: the wrapped data.script_receipt path still extracts and
    returns a deep copy (mutating the result must not touch the input)."""
    result = _nested_usable_result()
    receipt = _extract_script_receipt(result)
    assert isinstance(receipt, dict)
    assert receipt["artifact_status"] == "usable"
    receipt["artifact_status"] = "MUTATED"
    assert result["data"]["script_receipt"]["artifact_status"] == "usable"


def test_extract_receipt_top_level_shape_extracted_and_deepcopied():
    """The fix: a top-level script_receipt (no data key) is extracted and
    deep-copied."""
    result = _top_level_usable_result()
    receipt = _extract_script_receipt(result)
    assert isinstance(receipt, dict)
    assert receipt["artifact_status"] == "usable"
    receipt["artifact_status"] = "MUTATED"
    assert result["script_receipt"]["artifact_status"] == "usable"


def test_extract_receipt_both_present_nested_wins():
    """Precedence: when both locations carry a receipt, nested wins."""
    result = _nested_usable_result(component_guid="nested-guid")
    result["script_receipt"] = {
        "artifact_status": "usable",
        "mutation": {"status": "created", "component_guid": "top-guid"},
    }
    receipt = _extract_script_receipt(result)
    assert receipt["mutation"]["component_guid"] == "nested-guid"


def test_extract_receipt_non_dict_top_level_falls_through_to_none():
    """A non-dict top-level script_receipt is ignored; no data key -> None."""
    assert _extract_script_receipt({"script_receipt": "not a dict"}) is None
    assert _extract_script_receipt({"data": "err-string"}) is None


def test_node_evidence_from_top_level_usable_payload():
    """node_evidence_from_tool_result on the unwrapped usable shape captures the
    receipt + repair_anchor; tool_status/verified are None (the payload carries
    neither -- grounded, not over-asserted)."""
    evidence = node_evidence_from_tool_result(_top_level_usable_result())
    assert evidence.receipt is not None
    assert evidence.receipt["artifact_status"] == "usable"
    assert evidence.repair_anchor is not None
    assert evidence.repair_anchor["component_guid"] == "comp-top"
    assert evidence.tool_status is None
    assert evidence.verified is None


def test_apply_producer_result_top_level_usable_succeeds_end_to_end():
    """Payoff through the REAL consumer path LM4E uses:
    raw top-level MCP success payload -> node_evidence_from_tool_result ->
    producer projection -> reducer."""
    graph = _ready_producer_graph()
    result = apply_producer_result(graph, "create", _top_level_usable_result())

    assert result.applied is True
    assert result.outcome_status == "succeeded"
    node = result.graph.nodes["create"]
    assert node.status == "succeeded"
    assert node.evidence.verified is True
    # The top-level receipt survived capture -> projection -> reducer onto the node.
    assert node.evidence.receipt["artifact_status"] == "usable"
```

- [ ] **Step 2: Run the new tests; confirm the expected pre-fix failures**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_outcomes.py -k "top_level or nested_shape or both_present or non_dict" -v`
Expected pre-fix: `test_extract_receipt_top_level_shape_extracted_and_deepcopied`, `test_node_evidence_from_top_level_usable_payload`, and `test_apply_producer_result_top_level_usable_succeeds_end_to_end` **FAIL** (top-level receipt not found today). `test_extract_receipt_nested_shape_unchanged_and_deepcopied`, `test_extract_receipt_both_present_nested_wins`, and `test_extract_receipt_non_dict_top_level_falls_through_to_none` **PASS** (nested + non-dict already handled). This proves the new tests exercise the gap.

- [ ] **Step 3: Implement the additive fallback**

Replace `_extract_script_receipt` in `mcp_server/src/rook/learning/plan_graph_outcomes.py` with:

```python
def _extract_script_receipt(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    # Nested dispatcher / MCP-failure envelope FIRST (unchanged):
    #   result["data"]["script_receipt"].
    data = result.get("data")
    if isinstance(data, dict):
        receipt = data.get("script_receipt")
        if isinstance(receipt, dict):
            return deepcopy(receipt)
    # Top-level fallback ONLY for the MCP success-unwrapped payload shape: the
    # result IS the tool ``data`` itself, so it carries no internal-envelope
    # marker. If the dict still looks like an internal result envelope, do not
    # reinterpret a stray top-level ``script_receipt`` -- preserve the old
    # guardrail (e.g. ``{"success": True, "script_receipt": ...}`` is ignored).
    if "data" in result or "success" in result or "ok" in result or "error" in result:
        return None
    receipt = result.get("script_receipt")
    if isinstance(receipt, dict):
        return deepcopy(receipt)
    return None
```

**Re-gate note (narrowed fallback):** the top-level read is accepted ONLY when the
dict carries none of the envelope markers `data` / `success` / `ok` / `error`.
This preserves the original guardrail because `_extract_script_receipt` is shared
by the conservative `node_outcome_from_tool_result` path. A pre-existing test that
locked the old "ignore top-level" behavior is **renamed** (not deleted) to document
the refined rule with the same assertions —
`test_top_level_receipt_ignored_when_envelope_markers_present` (its scenario,
`{"success": True, "script_receipt": ...}`, still has a `success` marker so the
top-level receipt stays ignored: `succeeded` / `receipt None`).

- [ ] **Step 4: Run the LM4F tests; confirm all pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_outcomes.py -v`
Expected: all tests pass, including the six LM4F tests (the three previously-failing top-level cases now pass; the nested regression + precedence + non-dict tests remain green).

- [ ] **Step 5: Run the full focused PlanGraph gate (no regression)**

Run from repo root (PowerShell-expanded glob):

```powershell
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```

Expected: `≥ 236 passed` (LM4F's six new tests in `test_plan_graph_outcomes.py` add to the prior 236; no existing test regresses).

- [ ] **Step 6: `py_compile` the changed files**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_outcomes.py mcp_server/tests/test_plan_graph_outcomes.py`
Expected: exit 0, no output.

- [ ] **Step 7: Diff guard — confined scope, no knowledge/executor changes**

Run: `git add -A`
Then: `git diff --cached --name-only main`
Expected: EXACTLY these four paths and no others —
- `mcp_server/src/rook/learning/plan_graph_outcomes.py`
- `mcp_server/tests/test_plan_graph_outcomes.py`
- `docs/superpowers/specs/2026-06-22-lm4f-mcp-unwrapped-receipt-capture-design.md`
- `docs/superpowers/plans/2026-06-22-lm4f-mcp-unwrapped-receipt-capture.md`

Explicitly confirm there is **no `knowledge/` path** and **no `server.py` / `tool_result_view.py`** in the list. (PowerShell: `git diff --cached --name-only main | Select-String 'knowledge/|server.py|tool_result_view'` must return nothing.) If `knowledge/gh/operations_knowledge.json` reappears (runtime mutation), `git restore` it before committing.

- [ ] **Step 8: Commit**

```bash
git commit -m "fix(lm4f): accept top-level script_receipt from MCP success-unwrapped results"
```

(Body should note: nested-first / top-level fallback; both-present → nested wins; strictly additive; no change to `_mcp_tool_executor` / `_format_tool_result` / `normalize_tool_result`. End with the `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailer.)

## Self-Review

- **Spec coverage:** The single function change (Step 3) and all six spec tests (Step 1) are present; test #6 drives `apply_producer_result` and asserts `outcome_status=="succeeded"`, node `"succeeded"`, `evidence.verified is True`, **and** `evidence.receipt["artifact_status"] == "usable"` (the tightening). Gates cover focused suite (Step 5), `py_compile` (Step 6), and the diff guard incl. the knowledge-file exclusion (Step 7).
- **Placeholder scan:** none — every step carries concrete code/commands.
- **Type consistency:** `apply_producer_result` returns `ProducerStepResult` (`.applied`/`.outcome_status`/`.graph`); `node_evidence_from_tool_result` returns `NodeEvidence` (`.tool_status`/`.verified`/`.receipt`/`.repair_anchor`); `_extract_script_receipt` returns `dict | None`. All match the merged code.
