# LM4J — Declared-Ref Live Chain + Memory-Substrate Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the 5-node `gh_csharp_create_verify_repair_verify` live chain runs `create→verify→repair→reverify→done` to `graph_status=="complete"` with **no producer execution refs overridden** (`create_script` dispatches its declared `gh_create_csharp_script:v1` live), plus a deterministic CI guard pinning that producer projection writes the repair target into `graph.memory.facts`.

**Architecture:** Test-only inline hand-composition over already-merged seams. Two new test files, **zero production code**. `gh_create_csharp_script` delegates to the same `_execute_gh_create_script("csharp", …)` as the proven `gh_create_script`, so the declared ref dispatches live with no new machinery. The pure guard drives the chain through the real `apply_producer_result` projection path (which populates `graph.memory.facts`), unlike the LM4I pure guard's hand-built `NodeOutcome`s.

**Tech Stack:** Python 3.12, pytest (+ `pytest-asyncio`, `requires_rhino` marker), Rook `agent`/`learning` packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

Copied from the spec (`docs/superpowers/specs/2026-06-24-lm4j-declared-ref-live-chain-design.md`). Every task implicitly includes these.

- **5-node template only:** `gh_csharp_create_verify_repair_verify`, descriptor `{"domain": "grasshopper", "operation": "create_verify_repair_verify", "language": "csharp"}`.
- **Zero production code.** Only two new test files (+ this plan, + the committed spec). No edits under `mcp_server/src/`, `src/`, or `knowledge/`.
- **No producer execution refs are overridden.** Both producers dispatch their declared refs: `create_script` → `gh_create_csharp_script:v1` (→ `gh_create_csharp_script`), `repair_same_component` → `gh_update_script:v1` (→ `gh_update_script`). Each `:vN` is stripped by `_resolve_tool_name`.
- **Create params omit `language`** (the `gh_create_csharp_script` alias forces csharp): `{code, pins_in, pins_out, name, x, y}`.
- **Repair params exact** `{"guid": repair_guid, "code": "A = 42.0;", "mode": "body", "language": "csharp"}`; repair guid **hand-wired from create's `evidence.repair_anchor["component_guid"]`**, NOT from `graph.memory.facts` (memory assertion is observational; auto-propagation deferred).
- **Live envelope fidelity in the pure guard:** create raw = WRAPPED FAILURE (`{success: False, data.script_receipt}` → `tool_status="failed"`); repair raw = MCP-UNWRAPPED SUCCESS (top-level `script_receipt`, no `data`/`success`/`ok`/`error` → `tool_status=None`). Do NOT add a top-level `verified` field to the unwrapped repair raw — the producer projection derives `verified=True` from `artifact_status="usable"`.
- **`done` is a terminal marker only:** `apply_outcome(graph, "done", NodeOutcome(status="succeeded"))`, then assert `graph_status(graph) == "complete"`.
- **Keep the GH-document guard** (`_ensure_gh_document`); live dispatch needs an active GH doc.
- **Restore `knowledge/gh/operations_knowledge.json`** (`git restore`) after every live run; never commit it.
- **Diff gate:** the whole branch touches exactly four paths — the spec, this plan, and the two test files. No `src/` and no `operations_knowledge.json`.

## Seam reference (already merged — consume, do not modify)

- `select_template(descriptor) -> TemplateSelection` (`.selected_template_id`, `.graph`) — `rook.learning.plan_graph_templates`.
- `initialize_graph(graph) -> PlanGraph` (promotes root `pending → ready`) — `rook.learning.plan_graph`.
- `apply_producer_result(graph, node_id, raw_result) -> ProducerStepResult` (`.applied`, `.outcome_status`, `.graph`) — `rook.learning.plan_graph_runner`. Routes a raw tool-result dict through `node_evidence_from_tool_result` + the `artifact_producer` projection; populates `graph.memory.facts` via `_merge_memory`.
- `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult` (`.applied`, `.outcome_status`, `.graph`) — `rook.learning.plan_graph_runner`. `created_with_errors → needs_repair`, `usable → succeeded`.
- `apply_outcome(graph, node_id, NodeOutcome) -> PlanGraph`; `graph_status(graph) -> GraphStatus` (`"complete"` iff all `is_terminal` nodes succeeded/skipped); `NodeOutcome(status, …)` — `rook.learning.plan_graph`.
- `RookAgent(tool_executor=…).run_live_producer_node(graph, node_id) -> LiveProducerResult` (`.graph`, `.tool_name`, …) — `rook.agent.base_agent`. Admissibility: `node.status == "ready"`, role `artifact_producer`, resolvable `execution_ref`, Mapping `execution_params`.
- `EXECUTION_PARAMS_KEY` — `rook.agent.plan_graph_live`.
- `build_live_producer_record(result, expectation) -> LiveProducerRecord` (`.evaluated`, `.passed`, `.mismatches`, `.tool_status`); `LiveProducerExpectation(applied, outcome_status, node_status, tool_status, verified, artifact_status, …)` — `rook.agent.plan_graph_live_runner`.
- `_mcp_tool_executor` — `rook.server`. `fresh_document` fixture + `_is_error` — `mcp_server/tests/conftest.py`.

---

### Task 1: Memory-substrate pure guard (Rhino-independent, in the focused gate)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_live_repair_memory.py`

**Interfaces:**
- Consumes: `select_template`, `initialize_graph`, `apply_producer_result`, `apply_verifier_step`, `apply_outcome`, `graph_status`, `NodeOutcome`.
- Produces: nothing consumed by Task 2 (independent file). Named `test_plan_graph_live_repair_memory.py` so it lands in the `test_plan_graph*` focused gate.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_live_repair_memory.py` with exactly this content:

```python
"""LM4J memory-substrate pure guard — producer projection writes the repair target
into graph.memory.facts through the REAL apply_producer_result path.

Drives the registered 5-node gh_csharp_create_verify_repair_verify chain to
graph_status==complete using RAW tool-result dicts routed through the LM3I projection
entry apply_producer_result (NOT hand-built NodeOutcomes -- that path, used by the LM4I
pure guard, bypasses project_receipt_outcome's memory_updates). Pins:
  - memory_updates -> graph.memory.facts (component_guid / repair_anchor) on producer
    success, via _producer_success -> _merge_memory;
  - live-faithful raw envelopes: WRAPPED FAILURE create (success:False) ->
    tool_status="failed"; MCP-UNWRAPPED SUCCESS repair (top-level script_receipt) ->
    tool_status=None;
  - role-aware verified projection: created_with_errors -> verified=False,
    usable -> verified=True (NO top-level verified field in the raw).

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4j-pure-guard-guid"


def _wrapped_failure_create_raw() -> dict:
    """Live-faithful create envelope: success:False, nested data.script_receipt
    (created_with_errors with mutation + repair_anchor)."""
    return {
        "success": False,
        "message": "Component created with compile errors.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": _GUID},
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
            }
        },
    }


def _unwrapped_success_repair_raw() -> dict:
    """Live-faithful repair envelope: MCP-unwrapped success -- the result IS the tool
    data, top-level script_receipt, NO data/success/ok/error markers, NO top-level
    verified (the producer projection derives verified=True from artifact_status)."""
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "written", "component_guid": _GUID},
            "verification": {"status": "passed", "target_error_count": 0},
            "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
        }
    }


def test_memory_substrate_through_real_projection_path():
    # Registry path + both declared producer refs pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # Roots are 'pending' after selection; apply_producer_result gates on runnable_nodes
    # (ready). initialize_graph promotes the root create_script -> ready.
    graph = initialize_graph(graph)
    assert graph.nodes["create_script"].status == "ready"

    # 1) create producer via the REAL projection path (wrapped-failure raw).
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.applied is True
    assert create.outcome_status == "succeeded"
    graph = create.graph
    create_node = graph.nodes["create_script"]
    assert create_node.status == "succeeded"
    assert create_node.evidence is not None
    assert create_node.evidence.tool_status == "failed"
    assert create_node.evidence.verified is False
    # The substrate claim: producer projection wrote the repair target into memory.
    assert graph.memory.facts["component_guid"] == _GUID
    assert graph.memory.facts["repair_anchor"]["component_guid"] == _GUID
    assert graph.nodes["verify_create"].status == "ready"

    # 2) verify_create re-judges -> needs_repair, unlock repair.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.applied is True
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # 3) repair producer via the REAL projection path (unwrapped-success raw).
    repair = apply_producer_result(
        graph, "repair_same_component", _unwrapped_success_repair_raw()
    )
    assert repair.applied is True
    assert repair.outcome_status == "succeeded"
    graph = repair.graph
    repair_node = graph.nodes["repair_same_component"]
    assert repair_node.status == "succeeded"
    assert repair_node.evidence is not None
    # Unwrapped success carries no envelope marker -> tool_status None (LM4I finding);
    # verified=True is derived by the role projection from artifact_status="usable".
    assert repair_node.evidence.tool_status is None
    assert repair_node.evidence.verified is True
    assert graph.memory.facts["component_guid"] == _GUID
    assert graph.nodes["verify_repair"].status == "ready"

    # 4) verify_repair confirms clean -> done unlocks.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.applied is True
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"

    # 5) terminal done marker -> graph complete.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Run the test and verify it passes**

Run (from repo root):
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_live_repair_memory.py -v
```
Expected: `1 passed`. This composes over merged, correct seams, so it should be green first run. **If it fails, that is a real finding** (memory substrate, projection, or template mismatch) — capture the exact assertion and report; do not weaken the assertions.

- [ ] **Step 3: Confirm no stray runtime mutation, then commit**

Run:
```
git status --short
```
Expected: exactly `?? mcp_server/tests/test_plan_graph_live_repair_memory.py` (plus this plan if not yet committed). `operations_knowledge.json` must NOT be listed.

Commit:
```
git add mcp_server/tests/test_plan_graph_live_repair_memory.py
git commit -m "test(lm4j): memory-substrate pure guard via real apply_producer_result path

Drives the 5-node chain through apply_producer_result (raw dict -> projection),
pinning memory_updates -> graph.memory.facts (component_guid/repair_anchor) and
the live-faithful envelopes (wrapped-failure create -> tool_status=failed,
unwrapped-success repair -> tool_status=None, verified derived by role).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Declared-ref live proof (requires_rhino, outside the focused gate)

**Files:**
- Create: `mcp_server/tests/test_live_repair_chain_declared_refs_live.py`

**Interfaces:**
- Consumes: `RookAgent`, `_mcp_tool_executor`, `EXECUTION_PARAMS_KEY`, `select_template`, `apply_verifier_step`, `apply_outcome`, `graph_status`, `NodeOutcome`, `build_live_producer_record`, `LiveProducerExpectation`, `_is_error`, `fresh_document`.
- Produces: nothing. Named OUTSIDE the `test_plan_graph*` glob so it stays out of the focused gate; `requires_rhino` keeps it out of normal CI.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_live_repair_chain_declared_refs_live.py` with exactly this content:

```python
"""LM4J live proof -- the full repair chain with NO producer ref overrides.

Drives a real RookAgent(_mcp_tool_executor) through the 5-node
gh_csharp_create_verify_repair_verify chain to graph_status=="complete" using the
template's DECLARED producer refs unchanged: create_script dispatches
gh_create_csharp_script:v1 -> gh_create_csharp_script (NOT overridden to
gh_create_script as LM4I did), and repair keeps gh_update_script:v1 -> gh_update_script.
This proves the declared gh_create_csharp_script:v1 PlanGraph live path and closes
LM4I's biggest non-goal.

Also pins the memory substrate live: after create, graph.memory.facts["component_guid"]
matches create's captured repair_anchor. The repair guid is still HAND-WIRED from
evidence (NOT sourced from memory.facts) -- automatic rolling-memory propagation is a
separate future slice.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_declared_refs_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph import NodeOutcome, apply_outcome, graph_status
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


async def _ensure_gh_document() -> None:
    """Establish an ACTIVE Grasshopper document for the live producer dispatches.

    gh_create_csharp_script needs a GH document to place the component in; the
    `_Grasshopper` window being open is NOT sufficient, and `fresh_document` resets
    only the *Rhino* document. Skip (never silently ignore) when GH cannot provide one.
    """
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_declared_ref_live_repair_chain_drives_to_complete(fresh_document):
    await _ensure_gh_document()

    # Registry path + both declared producer refs pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # NO ref override: leave create_script.execution_ref == gh_create_csharp_script:v1.
    # Set ONLY execution_params (omit 'language' -- the csharp alias forces it).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4JDeclaredRefLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)

    # --- Live dispatch 1: declared-ref create (broken) -> created_with_errors. ---
    create_result = await agent.run_live_producer_node(graph, "create_script")
    # The declared gh_create_csharp_script:v1 resolved & dispatched live (no override).
    assert create_result.tool_name == "gh_create_csharp_script"
    create_record = build_live_producer_record(
        create_result,
        LiveProducerExpectation(
            applied=True,
            outcome_status="succeeded",
            node_status="succeeded",
            tool_status="failed",
            verified=False,
            artifact_status="created_with_errors",
        ),
    )
    assert create_record.evaluated is True
    assert create_record.passed is True, f"mismatches={create_record.mismatches!r}"

    graph = create_result.graph
    assert graph.nodes["create_script"].status == "succeeded"
    assert graph.nodes["verify_create"].status == "ready"

    # --- Memory-substrate live assertion (observational; NOT used to source params). ---
    create_anchor = graph.nodes["create_script"].evidence.repair_anchor
    assert create_anchor is not None
    repair_guid = create_anchor.get("component_guid")
    assert isinstance(repair_guid, str) and repair_guid
    assert graph.memory.facts["component_guid"] == repair_guid
    assert graph.memory.facts["repair_anchor"]["component_guid"] == repair_guid

    # --- Pure verifier step: verify_create -> needs_repair, unlock repair. ---
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.applied is True
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # --- Hand-wire repair params from the evidence guid (NOT from memory.facts). ---
    # Repair ref UNCHANGED: gh_update_script:v1 -> gh_update_script (proven).
    graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] = {
        "guid": repair_guid,
        "code": "A = 42.0;",
        "mode": "body",
        "language": "csharp",
    }

    # --- Live dispatch 2: declared-ref repair (corrected) -> usable. ---
    repair_result = await agent.run_live_producer_node(graph, "repair_same_component")
    assert repair_result.tool_name == "gh_update_script"
    repair_record = build_live_producer_record(
        repair_result,
        LiveProducerExpectation(
            applied=True,
            outcome_status="succeeded",
            node_status="succeeded",
            verified=True,
            artifact_status="usable",
        ),
    )
    assert repair_record.evaluated is True
    assert repair_record.passed is True, f"mismatches={repair_record.mismatches!r}"
    # Unwrapped success carries no envelope marker -> tool_status None (LM4I finding).
    assert repair_record.tool_status is None

    graph = repair_result.graph
    assert graph.nodes["repair_same_component"].status == "succeeded"
    assert graph.nodes["verify_repair"].status == "ready"

    # --- Pure verifier step: verify_repair -> succeeded, unlock done. ---
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.applied is True
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"

    # --- Terminal done marker -> graph complete. ---
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Verify collection + import (Rhino-independent)**

```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_live_repair_chain_declared_refs_live.py --collect-only -q
```
Expected: collects `test_declared_ref_live_repair_chain_drives_to_complete` with no import errors. Running without Rhino yields a clean `skip`, not a failure.

- [ ] **Step 3: Confirm no stray runtime mutation, then commit**

Run:
```
git status --short
```
Expected: exactly `?? mcp_server/tests/test_live_repair_chain_declared_refs_live.py` (plus this plan if not yet committed). `operations_knowledge.json` must NOT be listed (no live run yet).

Commit:
```
git add mcp_server/tests/test_live_repair_chain_declared_refs_live.py
git commit -m "test(lm4j): live proof -- declared-ref repair chain, no producer overrides

Real RookAgent -> run_live_producer_node x2 over the 5-node template with the
DECLARED refs: create dispatches gh_create_csharp_script:v1 (no override),
repair keeps gh_update_script:v1; asserts resolved tool_name on both, the live
memory.facts repair target, repair_record.tool_status is None, and terminal
graph_status==complete.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Live acceptance (run only with Rhino + Grasshopper open)** — PAUSE POINT

This is the authoritative live proof, run during a live acceptance pass (Rhino + Grasshopper open, Rook loaded), not in normal CI. Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_declared_refs_live.py -v
```
Expected: `1 passed`. The live run creates a `LM4JDeclaredRefLive` C# component via the **declared** `gh_create_csharp_script` ref, repairs it to `usable`, and drives to `complete`; it mutates `knowledge/gh/operations_knowledge.json`.

**If the live run fails** (the genuine live variable is whether `gh_create_csharp_script` dispatches identically to `gh_create_script`): capture the exact assertion + `create_record.mismatches` / `repair_record.mismatches` / node statuses and report. Do NOT adjust the test to pass — a mismatch is a real finding about the declared-ref live path.

After the live run, restore the runtime mutation (never commit it):
```
git restore knowledge/gh/operations_knowledge.json
git status --short
```
Expected after restore: clean (or only intended files).

---

## Final verification (whole-branch)

- [ ] **Focused gate green (Rhino-independent):** from repo root, run the focused PlanGraph gate including the new pure guard. PowerShell does not expand `test_plan_graph*.py`, so enumerate the files explicitly (proven command):
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_live_repair_memory.py` (gate count rises by 1 from the LM4I baseline of 257 → 258).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly four paths — the spec (`docs/superpowers/specs/2026-06-24-lm4j-declared-ref-live-chain-design.md`), this plan (`docs/superpowers/plans/2026-06-24-lm4j-declared-ref-live-chain.md`), and the two test files. No `src/` module, no `operations_knowledge.json`.

- [ ] **Production-path numstat is zero:**
```
git diff --numstat main...HEAD -- mcp_server/src src knowledge
```
Expected: empty output.

## Self-Review

**Spec coverage:**
- Goal (declared `gh_create_csharp_script:v1` live path to `complete`) → Task 2 (live, no override, asserts `create_result.tool_name == "gh_create_csharp_script"`).
- Memory-substrate deterministic CI guard → Task 1 (`apply_producer_result` path, asserts `graph.memory.facts`).
- 5-node template + descriptor → both tasks pin `selected_template_id` + both declared refs.
- No producer overrides → Task 2 sets only `execution_params`, never `execution_ref`.
- Create params omit `language` → Task 2 Step 1 verbatim.
- Repair params exact + hand-wired guid from evidence (not memory) → Task 2 Step 1.
- Live envelope fidelity (wrapped failure / unwrapped success) + no top-level `verified` → Task 1 raw builders + comments.
- `verified` projection assertions (create False / repair True) → Task 1 Step 1.
- `done` terminal marker + `graph_status == "complete"` → both tasks, final steps.
- `_ensure_gh_document` guard → Task 2.
- Restore `operations_knowledge.json` → Task 2 Step 4.
- Diff/numstat gate → Final verification.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `select_template(...).selected_template_id`/`.graph`; `initialize_graph(graph)`; `apply_producer_result(graph, node_id, raw) -> .applied/.outcome_status/.graph`; `apply_verifier_step(graph, verifier_node_id, source_node_id) -> .applied/.outcome_status/.graph`; `apply_outcome(graph, node_id, NodeOutcome(status=...))`; `graph_status(graph) == "complete"`; `RookAgent(tool_executor=...).run_live_producer_node(graph, node_id) -> .graph/.tool_name`; `build_live_producer_record(result, expectation) -> .evaluated/.passed/.mismatches/.tool_status`; `LiveProducerExpectation(applied, outcome_status, node_status, tool_status, verified, artifact_status)`. Consistent across both tasks and matching the merged modules.
