# LM4I — Live Repair Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove — live, end-to-end — that the 5-node `gh_csharp_create_verify_repair_verify` graph runs `create → verify → repair → reverify → done` to a terminal `complete` state via **two** live producer dispatches, without the model remembering the plan.

**Architecture:** Test-only inline hand-composition over already-merged seams (LM4A/C/D dispatch path, LM3D/E verifier steps, LM4G record builder, LM1E reducer). Two new test files, **zero production code**. The repair node is itself an `artifact_producer`, so the same role-agnostic `run_live_producer_node` (LM4D) that drove `create` drives `repair`; the only new live variable vs LM4H is the second dispatch + the reverify-to-`done`.

**Tech Stack:** Python 3.12, pytest (+ `pytest-asyncio`, `requires_rhino` marker), Rook `agent`/`learning` packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

Copied verbatim from the spec (`docs/superpowers/specs/2026-06-23-lm4i-live-repair-node-design.md`). Every task implicitly includes these.

- **5-node template only:** `gh_csharp_create_verify_repair_verify`, descriptor `{"domain": "grasshopper", "operation": "create_verify_repair_verify", "language": "csharp"}`.
- **Zero production code.** Only two new test files (+ this plan, + the already-committed spec). No edits under `mcp_server/src/`, `src/`, or `knowledge/`.
- **Assert declared refs before any mutation (drift guard):** `create_script.execution_ref == "gh_create_csharp_script:v1"`, `repair_same_component.execution_ref == "gh_update_script:v1"`.
- **Override ONLY the create ref** to the proven `gh_create_script`. **Leave the repair ref unchanged** — `_resolve_tool_name` strips `:v1` → the proven `gh_update_script`; set only the repair node's `execution_params`.
- **Hand-wire the repair guid** from the create node's captured `evidence.repair_anchor["component_guid"]`.
- **Repair `execution_params` exactly:** `{"guid": repair_guid, "code": "A = 42.0;", "mode": "body", "language": "csharp"}` (no `pins_*` — `gh_update_script` reads current pins).
- **`done` is a terminal marker only:** `apply_outcome(graph, "done", NodeOutcome(status="succeeded"))`, then assert `graph_status(graph) == "complete"`. Do not dispatch or verify it.
- **Keep the GH-document guard** (`_ensure_gh_document` via `gh_document_new` + `_is_error`/skip); live dispatch needs an active GH doc, not just the `_Grasshopper` window.
- **Restore `knowledge/gh/operations_knowledge.json`** (`git restore`) after every live run; never commit it.
- **Diff gate:** the whole branch touches exactly four paths — the spec, this plan, and the two test files. `git diff --stat main...HEAD` must show nothing else (especially no `src/` module and no `operations_knowledge.json`).
- **Honest non-goals:** does NOT prove `gh_create_csharp_script` live; does NOT prove automatic rolling-memory propagation of the repair target (hand-wired); no scheduler / runner / node-selection policy.

## Seam reference (already merged — consume, do not modify)

- `select_template(descriptor) -> TemplateSelection` with `.selected_template_id: str | None`, `.graph: PlanGraph | None` — `rook.learning.plan_graph_templates`.
- `apply_outcome(graph, node_id, NodeOutcome) -> PlanGraph` — `rook.learning.plan_graph`.
- `graph_status(graph) -> GraphStatus` — returns `"complete"` iff all `is_terminal` nodes are `succeeded`/`skipped` (`rook.learning.plan_graph`).
- `NodeOutcome(status, evidence=None, ...)` — rejects `pending`/`ready`/`running`; `NodeEvidence(tool_status, verified, receipt, repair_anchor, ...)` — `rook.learning.plan_graph`.
- `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult` with `.applied`, `.outcome_status`, `.graph` — `rook.learning.plan_graph_runner`. Projects the source node's evidence via `artifact_verifier`: `created_with_errors → needs_repair`, `usable → succeeded`.
- `RookAgent(tool_executor=...).run_live_producer_node(graph, node_id) -> LiveProducerResult` — `rook.agent.base_agent`. Admissibility needs `node.status == "ready"`, role `artifact_producer`, resolvable `execution_ref`, Mapping `execution_params`.
- `LiveProducerResult(graph, applied, node_id, tool_name, outcome_status, reason)` and `EXECUTION_PARAMS_KEY` — `rook.agent.plan_graph_live`.
- `build_live_producer_record(result, expectation) -> LiveProducerRecord` (`.evaluated`, `.passed`, `.mismatches`); `LiveProducerExpectation(outcome_status, node_status, tool_status, verified, artifact_status, ...)` — `rook.agent.plan_graph_live_runner`.
- `_mcp_tool_executor` — `rook.server`. `fresh_document` fixture + `_is_error` — `mcp_server/tests/conftest.py`.

---

### Task 1: Pure composition guard (Rhino-independent, in the focused gate)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_live_repair_chain.py`
- Test: itself (composition over merged seams; runs in CI)

**Interfaces:**
- Consumes: every seam in the seam reference except `RookAgent`/`_mcp_tool_executor` (synthetic, not live).
- Produces: nothing consumed by Task 2 (independent file). Named `test_plan_graph_live_repair_chain.py` so it lands in the `test_plan_graph*` focused gate.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_live_repair_chain.py` with exactly this content:

```python
"""LM4I pure composition guard — CI contract over the full repair CHAIN.

Composes the registered 5-node gh_csharp_create_verify_repair_verify template to a
terminal `complete` graph status using SYNTHETIC evidence (not live capture):
create-producer (created_with_errors) -> verify_create -> repair-producer (usable)
-> verify_repair -> done. Interleaves LM4G's build_live_producer_record for BOTH
producer dispatches (the two-successes seam for create; the clean seam for repair).

This is a composition contract: the 5-node topology + reducer + LM3E verifier steps
+ LM4G record builder still compose to a reverified-clean terminal state. It is NOT a
live-capture proof -- the live truth is test_live_repair_chain_live.py.

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph import (
    NodeEvidence,
    NodeOutcome,
    apply_outcome,
    graph_status,
)
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "pure-guard-guid"


def _created_with_errors_evidence() -> NodeEvidence:
    """Synthetic evidence mirroring a live created_with_errors producer capture."""
    return NodeEvidence(
        tool_status="failed",
        verified=False,
        receipt={"artifact_status": "created_with_errors"},
        repair_anchor={"component_guid": _GUID},
    )


def _usable_evidence() -> NodeEvidence:
    """Synthetic evidence mirroring a live usable repair-producer capture.

    tool_status is None (not "success"): a successful gh_update_script result is
    MCP-unwrapped with no top-level success/ok marker, so the live capture reports
    tool_status=None. This synthetic shape mirrors that live truth (LM4I finding).
    """
    return NodeEvidence(
        tool_status=None,
        verified=True,
        receipt={"artifact_status": "usable"},
        repair_anchor={"component_guid": _GUID},
    )


def test_live_repair_chain_composition_contract():
    # Registry path + both declared producer refs pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # 1) create producer succeeds (created_with_errors) -> verify_create unlocks.
    graph = apply_outcome(
        graph,
        "create_script",
        NodeOutcome(status="succeeded", evidence=_created_with_errors_evidence()),
    )
    assert graph.nodes["create_script"].status == "succeeded"
    assert graph.nodes["verify_create"].status == "ready"

    create_record = build_live_producer_record(
        LiveProducerResult(
            graph=graph,
            applied=True,
            node_id="create_script",
            tool_name="gh_create_script",
            outcome_status="succeeded",
            reason=None,
        ),
        LiveProducerExpectation(
            outcome_status="succeeded",
            node_status="succeeded",
            tool_status="failed",
            verified=False,
            artifact_status="created_with_errors",
        ),
    )
    assert create_record.evaluated is True
    assert create_record.passed is True, f"mismatches={create_record.mismatches!r}"

    # 2) verify_create re-judges the producer evidence -> needs_repair, unlock repair.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.applied is True
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["verify_create"].status == "needs_repair"
    assert graph.nodes["repair_same_component"].status == "ready"

    # 3) repair producer succeeds (usable) -> verify_repair unlocks.
    graph = apply_outcome(
        graph,
        "repair_same_component",
        NodeOutcome(status="succeeded", evidence=_usable_evidence()),
    )
    assert graph.nodes["repair_same_component"].status == "succeeded"
    assert graph.nodes["verify_repair"].status == "ready"

    repair_record = build_live_producer_record(
        LiveProducerResult(
            graph=graph,
            applied=True,
            node_id="repair_same_component",
            tool_name="gh_update_script",
            outcome_status="succeeded",
            reason=None,
        ),
        LiveProducerExpectation(
            outcome_status="succeeded",
            node_status="succeeded",
            verified=True,
            artifact_status="usable",
        ),
    )
    assert repair_record.evaluated is True
    assert repair_record.passed is True, f"mismatches={repair_record.mismatches!r}"
    # Mirrors the live truth: unwrapped success carries no envelope marker.
    assert repair_record.tool_status is None

    # 4) verify_repair confirms clean -> done unlocks.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.applied is True
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["verify_repair"].status == "succeeded"
    assert graph.nodes["done"].status == "ready"

    # 5) terminal `done` marker -> graph complete.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Run the test and verify it passes**

Run (from repo root):
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_live_repair_chain.py -v
```
Expected: `1 passed`. This composition runs entirely over merged, correct seams, so it should be green on first run. **If it fails, that is a real integration finding** (a template/role/projection mismatch) — capture the exact assertion + any `record.mismatches` and report; do not weaken the assertions to pass.

- [ ] **Step 3: Confirm no stray runtime mutation, then commit**

Run:
```
git status --short
```
Expected: exactly `?? mcp_server/tests/test_plan_graph_live_repair_chain.py` (plus this plan if not yet committed). Confirm `knowledge/gh/operations_knowledge.json` is NOT listed (the pure guard does no live I/O, so it must not appear).

Commit:
```
git add mcp_server/tests/test_plan_graph_live_repair_chain.py
git commit -m "test(lm4i): pure composition guard for full live repair chain

Composes the 5-node gh_csharp_create_verify_repair_verify template to
graph_status==complete over merged seams (reducer + LM3E verifier steps +
LM4G record builder), synthetic evidence. CI contract for the live proof.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Live proof (requires_rhino, outside the focused gate)

**Files:**
- Create: `mcp_server/tests/test_live_repair_chain_live.py`
- Test: itself (live, `requires_rhino`)

**Interfaces:**
- Consumes: `RookAgent`, `_mcp_tool_executor`, `EXECUTION_PARAMS_KEY`, `select_template`, `apply_verifier_step`, `apply_outcome`, `graph_status`, `build_live_producer_record`, `LiveProducerExpectation`, `_is_error`, `fresh_document`.
- Produces: nothing. Named OUTSIDE the `test_plan_graph*` glob so it stays out of the focused gate; `requires_rhino` keeps it out of normal CI.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_live_repair_chain_live.py` with exactly this content:

```python
"""LM4I live proof -- two live producer dispatches drive the repair chain to complete.

Drives a real RookAgent(_mcp_tool_executor) through run_live_producer_node TWICE on
the registered 5-node gh_csharp_create_verify_repair_verify template: a live create
(broken body -> created_with_errors), then a live REPAIR (corrected body -> usable),
with pure LM3E verifier steps between/after, reaching terminal graph_status ==
"complete".

Live overrides: ONLY the create ref is swapped to the LM4E/LM4G-proven gh_create_script
(its declared gh_create_csharp_script is not proven live). The repair node keeps its
real declared ref gh_update_script:v1 -- _resolve_tool_name strips :v1 to the proven
gh_update_script -- so only its execution_params are hand-set, with the corrected body
and the repair target guid hand-wired from the live create evidence. This does NOT
prove gh_create_csharp_script live, nor automatic rolling-memory propagation.

requires_rhino: deselected from normal CI; fresh_document + _ensure_gh_document skip
when Rhino/GH are unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_live.py
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

    gh_create_script needs a GH document to place the component in; the
    `_Grasshopper` window being open is NOT sufficient, and `fresh_document`
    resets only the *Rhino* document. Skip (do not hard-fail, never silently
    ignore) when GH cannot provide a document.
    """
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_live_repair_chain_drives_to_complete(fresh_document):
    # Establish the live precondition explicitly (active GH document).
    await _ensure_gh_document()

    # Registry path + both declared producer refs pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # Override ONLY the create ref to the proven gh_create_script; broken body.
    graph.nodes["create_script"].execution_ref = "gh_create_script"
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "language": "csharp",
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4IRepairChainLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)

    # --- Live dispatch 1: create (broken) -> created_with_errors / succeeded. ---
    create_result = await agent.run_live_producer_node(graph, "create_script")
    # Direct claim: the create override resolved to the proven tool.
    assert create_result.tool_name == "gh_create_script"
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

    # --- Pure verifier step: verify_create -> needs_repair, unlock repair. ---
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.applied is True
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # --- Hand-wire the repair target guid from the live create evidence. ---
    create_anchor = graph.nodes["create_script"].evidence.repair_anchor
    assert create_anchor is not None
    repair_guid = create_anchor.get("component_guid")
    assert isinstance(repair_guid, str) and repair_guid

    # Repair node keeps its real declared ref (gh_update_script:v1 -> gh_update_script);
    # set only execution_params with the corrected body + the live target guid.
    graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] = {
        "guid": repair_guid,
        "code": "A = 42.0;",
        "mode": "body",
        "language": "csharp",
    }

    # --- Live dispatch 2: repair (corrected) -> usable / succeeded. ---
    repair_result = await agent.run_live_producer_node(graph, "repair_same_component")
    # Direct claim: the unchanged repair ref gh_update_script:v1 resolved (:v1
    # stripped) to the proven gh_update_script -- no override needed.
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
    # LM4I live finding: a SUCCESSFUL gh_update_script result is MCP-unwrapped
    # (no top-level success/ok marker), so normalize_tool_result reports
    # tool_status=None. Repair success is carried by verified/artifact_status/
    # node_status -- not the transport-envelope tool_status (cf. LM4F).
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

    # --- Terminal `done` marker -> graph complete. ---
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Verify collection + import (Rhino-independent)**

The live test is gated behind `requires_rhino`, so it deselects without Rhino. Confirm it imports cleanly and collects (no syntax/import error):
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_live_repair_chain_live.py --collect-only -q
```
Expected: collects `test_live_repair_chain_drives_to_complete` with no import errors. Running it without Rhino yields a clean `skip` (via `fresh_document`/`_ensure_gh_document`), not a failure.

- [ ] **Step 3: Confirm no stray runtime mutation, then commit**

Run:
```
git status --short
```
Expected: exactly `?? mcp_server/tests/test_live_repair_chain_live.py` (plus this plan if not yet committed). `operations_knowledge.json` must NOT be listed (no live run yet at this step).

Commit:
```
git add mcp_server/tests/test_live_repair_chain_live.py
git commit -m "test(lm4i): live proof -- two live dispatches drive repair chain to complete

Real RookAgent(_mcp_tool_executor) -> run_live_producer_node x2 over the 5-node
template: live create (broken -> created_with_errors) then live repair
(corrected -> usable, guid hand-wired from create evidence), pure verifier
steps between/after, terminal done -> graph_status==complete. Override only the
create ref; repair keeps gh_update_script:v1 (resolves to the proven tool).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Live acceptance (run only with Rhino + Grasshopper open)**

This is the authoritative live proof, run during a live acceptance pass (Rhino + Grasshopper open, Rook loaded), not in normal CI. Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_live.py -v
```
Expected: `1 passed`. The live run creates a `LM4IRepairChainLive` C# component on the canvas, then repairs it in place, and mutates `knowledge/gh/operations_knowledge.json`.

**If the live run fails** (most likely at the repair record — the gh_update_script live receipt shape is the slice's genuine live variable): capture the exact assertion + `repair_record.mismatches` / node statuses and report. Do NOT adjust the test to pass — a mismatch is a real finding about live `gh_update_script` capture.

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
Expected: all pass, including `test_plan_graph_live_repair_chain.py` (gate count rises by 1 from the LM4H/LM4G baseline of 256).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly four paths and nothing else — the spec (`docs/superpowers/specs/2026-06-23-lm4i-live-repair-node-design.md`), this plan (`docs/superpowers/plans/2026-06-23-lm4i-live-repair-node.md`), and the two test files. Especially: no `src/` module, no `mcp_server/src/`, no `operations_knowledge.json`.

- [ ] **Production-path numstat is zero:** confirm no production code changed:
```
git diff --numstat main...HEAD -- mcp_server/src src knowledge
```
Expected: empty output (zero lines).

## Self-Review

**Spec coverage:**
- Goal (live 5-node to `complete`) → Tasks 1 (pure) + 2 (live), both assert `graph_status == "complete"`.
- 5-node template + descriptor → both tasks pin `selected_template_id == "gh_csharp_create_verify_repair_verify"`.
- Assert both declared refs before mutation → both tasks assert `gh_create_csharp_script:v1` + `gh_update_script:v1` first.
- Override only create; repair keeps declared ref → Task 2 overrides `create_script.execution_ref` only; repair node only gets `execution_params`. The resolution is asserted **directly**: `create_result.tool_name == "gh_create_script"` and `repair_result.tool_name == "gh_update_script"` (the unchanged `:v1` ref resolved by `_resolve_tool_name`), with `applied=True` in both live expectations.
- Hand-wire repair guid from create evidence → Task 2 reads `graph.nodes["create_script"].evidence.repair_anchor["component_guid"]`.
- Repair params exact `{guid, code:"A = 42.0;", mode:"body", language:"csharp"}` → Task 2 Step 1 verbatim.
- `done` terminal marker via `apply_outcome` + `graph_status == "complete"` → both tasks, final steps.
- Keep `_ensure_gh_document` guard → Task 2 includes it.
- Restore `operations_knowledge.json` → Task 2 Step 4.
- Diff/numstat gate → Final verification.
- Non-goals (no production code, no scheduler, no `gh_create_csharp_script` live, no auto rolling-memory) → Global Constraints + zero `src/` edits + Task 2 docstring.
- Two-successes seam (create) + clean seam (repair) record evaluation → both tasks build both records with explicit expectations.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `select_template(...).selected_template_id`/`.graph`; `apply_outcome(graph, node_id, NodeOutcome(status=..., evidence=...))`; `NodeEvidence(tool_status=, verified=, receipt=, repair_anchor=)`; `apply_verifier_step(graph, verifier_node_id, source_node_id)` (arg order matches `plan_graph_runner.py`) → `.applied`/`.outcome_status`/`.graph`; `build_live_producer_record(result, expectation)` → `.evaluated`/`.passed`/`.mismatches`; `LiveProducerResult(graph, applied, node_id, tool_name, outcome_status, reason)`; `LiveProducerExpectation(outcome_status, node_status, tool_status, verified, artifact_status)`; `RookAgent(tool_executor=...).run_live_producer_node(graph, node_id)`; `graph_status(graph) == "complete"`. All match the merged modules and are consistent across both tasks.
