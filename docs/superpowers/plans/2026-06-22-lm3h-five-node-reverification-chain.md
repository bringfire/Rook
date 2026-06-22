# LM3H Full 5-node Re-verification Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the full linear re-verification chain `create → verify → repair → reverify → done` as a third additive template, and prove (non-live, test-only) that deterministic primitives drive it to `complete` — the capstone of non-live PlanGraph semantics.

**Architecture:** One additive template builder + registry entry in `plan_graph_templates.py`. NO new production primitives — the chain is driven by `apply_producer_step` (both producers), `apply_verifier_step` (both verifiers), and one explicit `apply_outcome` finalizing the terminal `done` marker, all in a test.

**Tech Stack:** Python 3.12, stdlib, pytest. Test runner: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.

## Global Constraints

- **Third additive template.** `gh_csharp_create_verify_repair_verify` (`operation="create_verify_repair_verify"`) is added beside the BYTE-STABLE 2-node (`gh_csharp_create_repair`) and 3-node (`gh_csharp_create_verify_repair`) entries. Do not touch their builders, criteria, or bindings.
- **No new production primitives.** The ONLY production change is the new template builder + registry entry. No reducer/walker/runner/projection/verifier logic change.
- **`plan_graph_templates.py` adds NO new imports.** Role metadata is literal strings (`"artifact_producer"`/`"artifact_verifier"`), pinned to `OUTCOME_PROJECTION_ROLE_KEY` by a test that imports the constant. Do not import `plan_graph_projection` into the templates module.
- **Linear chain, no re-entry.** No cyclic/on_repair-back/retry edge. No reverify-still-broken handling, no `needs_escalation`.
- **`done` is a terminal marker only.** `is_terminal=True`, NO `execution_ref`, NO `verifier_ref`, NO `outcome_projection_role`. It is finalized ONLY by an explicit test `apply_outcome` (no `apply_tool_result`, no fake receipt, no reducer auto-complete).
- **Repair is visibly repair-as-producer.** In the end-to-end test, `repair_same_component` is driven by `apply_producer_step` from injected `usable` evidence — NOT `apply_tool_result`. Assert `repair_same_component.evidence.verified is True` and `verify_repair` becomes `ready`.
- **`initialize_graph` called exactly once**, before any step, never after mutation.

---

## File Structure

- **Modify:** `mcp_server/src/rook/learning/plan_graph_templates.py` — add `_build_gh_csharp_create_verify_repair_verify` + third `DEFAULT_REGISTRY` entry.
- **Modify:** `mcp_server/tests/test_plan_graph_templates.py` — selection / three-way disjointness / topology / role-pin / `done`-marker-only tests (reuses the LM3G `_CREATE_REPAIR`, `_CREATE_VERIFY_REPAIR` constants and the `OUTCOME_PROJECTION_ROLE_KEY` import already in the file).
- **Modify:** `mcp_server/tests/test_plan_graph_runner.py` — the 5-node end-to-end chain proof (adds `NodeOutcome`/`apply_outcome` to the existing `plan_graph` import + a `_usable_receipt` helper).

---

### Task 1: Register the 5-node chain template

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_templates.py`
- Test: `mcp_server/tests/test_plan_graph_templates.py`

**Interfaces:**
- Consumes: `PlanGraph`, `PlanGraphNode`, `PlanGraphEdge`, `TemplateEntry`, `BindingSpec`, `_make_entry`, `select_template` (existing in the module); `OUTCOME_PROJECTION_ROLE_KEY` + `_CREATE_REPAIR` + `_CREATE_VERIFY_REPAIR` (already in the test file from LM3G).
- Produces: `_build_gh_csharp_create_verify_repair_verify`, registry entry `gh_csharp_create_verify_repair_verify`.

- [ ] **Step 1: Write the failing template tests**

Append to `mcp_server/tests/test_plan_graph_templates.py` (the `OUTCOME_PROJECTION_ROLE_KEY` import and `_CREATE_REPAIR`/`_CREATE_VERIFY_REPAIR` constants already exist from LM3G — reuse them):

```python
_CREATE_VERIFY_REPAIR_VERIFY = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


def test_select_create_verify_repair_verify():
    sel = select_template(_CREATE_VERIFY_REPAIR_VERIFY)
    assert sel.selected_template_id == "gh_csharp_create_verify_repair_verify"


def test_registry_three_way_disjoint_via_evaluation_trail():
    cases = [
        (_CREATE_REPAIR, "gh_csharp_create_repair"),
        (_CREATE_VERIFY_REPAIR, "gh_csharp_create_verify_repair"),
        (_CREATE_VERIFY_REPAIR_VERIFY, "gh_csharp_create_verify_repair_verify"),
    ]
    all_ids = {tid for _, tid in cases}
    for descriptor, selected in cases:
        sel = select_template(descriptor)
        assert sel.selected_template_id == selected
        for other_id in all_ids - {selected}:
            other = next(e for e in sel.evaluations if e.template_id == other_id)
            assert not other.matched
            op = next(c for c in other.criteria if c.field == "operation")
            assert op.outcome == "value_mismatch"


def test_create_verify_repair_verify_topology():
    graph = select_template(_CREATE_VERIFY_REPAIR_VERIFY).graph
    assert set(graph.nodes) == {
        "create_script",
        "verify_create",
        "repair_same_component",
        "verify_repair",
        "done",
    }
    assert graph.nodes["done"].is_terminal is True
    assert graph.nodes["repair_same_component"].is_terminal is False
    kinds = {(e.source, e.target): e.kind for e in graph.edges}
    assert kinds[("create_script", "verify_create")] == "requires"
    assert kinds[("verify_create", "repair_same_component")] == "on_repair"
    assert kinds[("repair_same_component", "verify_repair")] == "requires"
    assert kinds[("verify_repair", "done")] == "requires"


def test_create_verify_repair_verify_role_metadata_pinned():
    graph = select_template(_CREATE_VERIFY_REPAIR_VERIFY).graph
    assert graph.nodes["create_script"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_producer"
    assert graph.nodes["repair_same_component"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_producer"
    assert graph.nodes["verify_create"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_verifier"
    assert graph.nodes["verify_repair"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_verifier"


def test_done_is_terminal_marker_only():
    done = select_template(_CREATE_VERIFY_REPAIR_VERIFY).graph.nodes["done"]
    assert done.is_terminal is True
    assert done.execution_ref is None
    assert done.verifier_ref is None
    assert OUTCOME_PROJECTION_ROLE_KEY not in done.metadata
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_templates.py -p no:cacheprovider -q`
Expected: FAIL — `gh_csharp_create_verify_repair_verify` not selected (no such registry entry).

- [ ] **Step 3: Add the builder + registry entry**

In `mcp_server/src/rook/learning/plan_graph_templates.py`, add the builder after `_build_gh_csharp_create_verify_repair`:

```python
def _build_gh_csharp_create_verify_repair_verify() -> PlanGraph:
    """Full linear RE-VERIFICATION CHAIN: create -> verify -> repair -> reverify -> done (LM3H).

    NOT a retry loop -- the reducer unlocks only pending targets, so the chain runs
    forward exactly once. create_script (artifact_producer) -> verify_create
    (artifact_verifier) routes a created_with_errors receipt to repair via
    on_repair; repair_same_component (artifact_producer, NOT terminal) produces a
    usable artifact that verify_repair (artifact_verifier) confirms clean,
    unlocking the terminal ``done`` marker. Terminal ``done`` means reverified clean.
    """
    return PlanGraph(
        nodes={
            "create_script": PlanGraphNode(
                id="create_script",
                intent="Create C# script component",
                execution_ref="gh_create_csharp_script:v1",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
                repair_policy_ref="repair_same_component_once:v1",
                metadata={"outcome_projection_role": "artifact_producer"},
            ),
            "verify_create": PlanGraphNode(
                id="verify_create",
                intent="Verify the created component's receipt",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
                metadata={"outcome_projection_role": "artifact_verifier"},
            ),
            "repair_same_component": PlanGraphNode(
                id="repair_same_component",
                intent="Repair the same component in place",
                execution_ref="gh_update_script:v1",
                repair_policy_ref="repair_same_component_once:v1",
                metadata={"outcome_projection_role": "artifact_producer"},
            ),
            "verify_repair": PlanGraphNode(
                id="verify_repair",
                intent="Re-verify the repaired component's receipt",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
                metadata={"outcome_projection_role": "artifact_verifier"},
            ),
            "done": PlanGraphNode(
                id="done",
                intent="Finalize: artifact reverified clean",
                is_terminal=True,
            ),
        },
        edges=[
            PlanGraphEdge(
                source="create_script", target="verify_create", kind="requires"
            ),
            PlanGraphEdge(
                source="verify_create",
                target="repair_same_component",
                kind="on_repair",
            ),
            PlanGraphEdge(
                source="repair_same_component",
                target="verify_repair",
                kind="requires",
            ),
            PlanGraphEdge(
                source="verify_repair", target="done", kind="requires"
            ),
        ],
    )
```

Then add the third entry to `DEFAULT_REGISTRY` (after the `gh_csharp_create_verify_repair` entry, inside the tuple):

```python
    _make_entry(
        "gh_csharp_create_verify_repair_verify",
        {
            "domain": "grasshopper",
            "operation": "create_verify_repair_verify",
            "language": "csharp",
        },
        _build_gh_csharp_create_verify_repair_verify,
        bindings=(
            BindingSpec("goal", "memory_fact", "goal"),
            BindingSpec(
                "component_name",
                "node_metadata",
                "component_name",
                node_id="create_script",
            ),
        ),
    ),
```

Do NOT add any import to this module — the metadata uses literal strings. Do NOT modify the existing two builders or their registry entries.

- [ ] **Step 4: Run template tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_templates.py -p no:cacheprovider -q`
Expected: PASS (existing LM3B/LM3C/LM3G template tests + the 5 new tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_templates.py mcp_server/tests/test_plan_graph_templates.py
git commit -m "feat(lm3h): register gh_csharp_create_verify_repair_verify 5-node chain template"
```

---

### Task 2: End-to-end 5-node chain proof

**Files:**
- Test: `mcp_server/tests/test_plan_graph_runner.py`

**Interfaces:**
- Consumes: `select_and_bind` (templates), `initialize_graph`/`graph_status`/`NodeOutcome`/`apply_outcome` (plan_graph), `apply_producer_step`/`apply_verifier_step` (runner), and the existing `_created_with_errors_receipt` / `_evidence` helpers already in the test file.
- Produces: `test_create_verify_repair_verify_chain_end_to_end_non_live`, `_usable_receipt` helper.

- [ ] **Step 1: Write the failing end-to-end test**

In `mcp_server/tests/test_plan_graph_runner.py`, add `NodeOutcome` and `apply_outcome` to the existing `from rook.learning.plan_graph import (...)` block:

```python
from rook.learning.plan_graph import (
    NodeEvidence,
    NodeOutcome,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    apply_outcome,
    graph_status,
    initialize_graph,
)
```

Then append the helper + test (the `_created_with_errors_receipt` and `_evidence` helpers already exist in this file from LM3G):

```python
def _usable_receipt(component_guid="g1"):
    return {
        "artifact_status": "usable",
        "mutation": {"status": "updated", "component_guid": component_guid},
    }


def test_create_verify_repair_verify_chain_end_to_end_non_live():
    descriptor = {
        "domain": "grasshopper",
        "operation": "create_verify_repair_verify",
        "language": "csharp",
    }
    bound = select_and_bind(descriptor)
    graph = bound.binding.graph
    assert graph is not None

    # initialize_graph EXACTLY ONCE, before any step, never after mutation
    graph = initialize_graph(graph)
    assert graph.nodes["create_script"].status == "ready"

    # 1. producer step: create_script (created_with_errors -> succeeded)
    graph.nodes["create_script"].evidence = _evidence(_created_with_errors_receipt())
    pr = apply_producer_step(graph, "create_script")
    assert pr.applied and pr.outcome_status == "succeeded"
    graph = pr.graph
    assert graph.nodes["create_script"].evidence.verified is False
    assert graph.nodes["verify_create"].status == "ready"

    # 2. verifier step: verify_create -> needs_repair, unlocks repair via on_repair
    vr = apply_verifier_step(graph, "verify_create", "create_script")
    assert vr.applied and vr.outcome_status == "needs_repair"
    graph = vr.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # 3. REPAIR-AS-PRODUCER (apply_producer_step, NOT apply_tool_result):
    #    inject usable evidence, drive via the producer primitive.
    graph.nodes["repair_same_component"].evidence = _evidence(_usable_receipt())
    rp = apply_producer_step(graph, "repair_same_component")
    assert rp.applied and rp.outcome_status == "succeeded"
    graph = rp.graph
    assert graph.nodes["repair_same_component"].evidence.verified is True   # repair-as-producer
    assert graph.nodes["verify_repair"].status == "ready"                   # requires unlock

    # 4. second verifier step: verify_repair -> succeeded (usable), unlocks done
    vr2 = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert vr2.applied and vr2.outcome_status == "succeeded"
    graph = vr2.graph
    assert graph.nodes["done"].status == "ready"

    # 5. finalize done with an EXPLICIT test outcome (no receipt, no bridge)
    assert graph.nodes["done"].status == "ready"   # watchpoint: ready BEFORE finalize
    graph = apply_outcome(
        graph,
        "done",
        NodeOutcome(status="succeeded", message="done: reverified clean"),
    )
    assert graph.nodes["done"].status == "succeeded"

    # 6. terminal done succeeded -> graph complete
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_runner.py::test_create_verify_repair_verify_chain_end_to_end_non_live -p no:cacheprovider -q`
Expected: PASS (Task 1's registered template + the existing primitives compose to `complete`). If it fails on selection, confirm Task 1 landed.

- [ ] **Step 3: Run the full PlanGraph suite + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider \
  mcp_server/tests/test_plan_graph.py \
  mcp_server/tests/test_plan_graph_outcomes.py \
  mcp_server/tests/test_plan_graph_bridge.py \
  mcp_server/tests/test_plan_graph_walker.py \
  mcp_server/tests/test_plan_graph_templates.py \
  mcp_server/tests/test_plan_graph_verifiers.py \
  mcp_server/tests/test_plan_graph_runner.py \
  mcp_server/tests/test_plan_graph_projection.py -q
```
Expected: PASS (all). Then: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_templates.py` (silent).

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tests/test_plan_graph_runner.py
git commit -m "test(lm3h): end-to-end 5-node re-verification chain proof (repair-as-producer)"
```

---

## Self-Review

- **Spec coverage:** third additive template + registry entry (Task 1 Step 3), three-way disjointness via evaluation trail (Task 1 test), topology + role-pin + `done` marker-only (Task 1 tests), end-to-end chain with repair-as-producer assertion cluster + single `initialize_graph` + explicit `done` outcome (Task 2). All spec sections mapped.
- **Watchpoint:** Task 2 step 3 drives `repair_same_component` via `apply_producer_step` from injected `usable` evidence (NOT `apply_tool_result`) and asserts `verified is True` + `verify_repair` `ready` — the proof cannot fall back to bridge semantics for repair.
- **Placeholder scan:** none — every step carries full code or an exact command.
- **Type consistency:** node ids, `operation="create_verify_repair_verify"`, edge kinds, and helper names match across Task 1 and Task 2 and the spec.

## Execution Handoff

Two tasks (1 → 2; Task 2's proof depends on Task 1's registered template). Recommended: subagent-driven-development — haiku implementer per task (transcription-plus-testing; full code provided), sonnet task reviewer per task, opus final whole-branch review. Final reviewer EXTRA instructions:
(a) the ONLY production diff is `plan_graph_templates.py` (new builder + registry entry); no reducer/walker/runner/projection/verifier logic change.
(b) the 2-node (`gh_csharp_create_repair`) and 3-node (`gh_csharp_create_verify_repair`) builders, criteria, and bindings are BYTE-STABLE (only registry-tuple adjacency changed).
(c) `plan_graph_templates.py` adds NO new imports (role metadata is literal strings, test-pinned to `OUTCOME_PROJECTION_ROLE_KEY`).
(d) `done` is a terminal marker: `is_terminal=True`, no `execution_ref`, no `verifier_ref`, no role metadata; it is finalized ONLY by the test's explicit `apply_outcome` (no `apply_tool_result`, no fake receipt, no reducer auto-complete).
(e) the end-to-end test drives `repair_same_component` via `apply_producer_step` (asserts `verified is True` + `verify_repair` ready), drives both verifiers via `apply_verifier_step`, calls `initialize_graph` exactly once before any step, and reaches `graph_status == "complete"`.
(f) linear chain — no cyclic/on_repair-back/retry edge; no `needs_escalation`; no production sequencer.
