# LM3G Role Adoption + Verifier-Mediated Template Revival Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt the LM3F projection role on the graph node (via `node.metadata`), add a producer-restricted runner primitive that consumes it, register a 3-node verifier-mediated template, and prove end-to-end (non-live) that a `created_with_errors` producer node unlocks a downstream verifier through the reducer's `requires` edge.

**Architecture:** Three small additive production changes — a role accessor in `plan_graph_projection.py`, `apply_producer_step` in `plan_graph_runner.py`, and a second `DEFAULT_REGISTRY` template in `plan_graph_templates.py` — plus a test-only explicit composition proof. No core-dataclass change, no production sequencer.

**Tech Stack:** Python 3.12, stdlib `dataclasses`/`typing`, pytest. Test runner: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.

## Global Constraints

- **Role lives in `node.metadata`** keyed by `OUTCOME_PROJECTION_ROLE_KEY`, read by `projection_role_for_node`. No typed `PlanGraphNode` field.
- **`projection_role_for_node` never raises** — node metadata is graph data. Invalid role surfaces as a runner not-applied diagnostic.
- **`apply_producer_step` is producer-restricted, no default.** Requires the node's declared role to be exactly `artifact_producer`. Distinct reasons: `role_missing` / `role_invalid` / `role_not_producer`. Never accepts `artifact_verifier` / `direct_task`.
- **`runnable_nodes(graph)` is the sole readiness authority.** Guard order is fixed: `unknown_node` → `node_not_runnable` → `evidence_missing` → role checks. A pending node with an invalid role returns `node_not_runnable` (readiness precedes data diagnostics).
- **Never mutates the input graph.** Every not-applied path returns the input graph object unchanged (`result.graph is graph`); applied returns `apply_outcome`'s fresh graph.
- **Second template is additive.** `gh_csharp_create_repair` stays untouched. New `gh_csharp_create_verify_repair`, criteria differ only by `operation="create_verify_repair"` (structured exact-match; no inference from `verify=true`/free text).
- **Honest naming.** Terminal `repair_same_component` = "repair step returned `usable` through the bridge," NOT "reverified clean."
- **`plan_graph_templates` does NOT import `plan_graph_projection`.** It uses literal metadata strings; a test pins them to the projection constant.
- **Test-only composition.** No production `run_*` sequencer. The end-to-end proof drives the repair node via `apply_tool_result` ONLY; producer/verifier nodes via their dedicated primitives; `initialize_graph` is called exactly once, before any step, never after mutation.
- **No change** to `walk_plan_graph`, LM1F (`plan_graph_outcomes.py`), or LM3F's `project_receipt_outcome` logic. No live tools, no model calls, no `planner.py`, no `needs_escalation`.

---

## File Structure

- **Modify:** `mcp_server/src/rook/learning/plan_graph_projection.py` — add `OUTCOME_PROJECTION_ROLE_KEY` + `projection_role_for_node`; add `PlanGraphNode` to the existing `plan_graph` import.
- **Modify:** `mcp_server/src/rook/learning/plan_graph_runner.py` — add `ProducerStepReason`, `ProducerStepResult`, `apply_producer_step`; import projection symbols.
- **Modify:** `mcp_server/src/rook/learning/plan_graph_templates.py` — add `_build_gh_csharp_create_verify_repair` + second registry entry.
- **Modify:** `mcp_server/tests/test_plan_graph_projection.py` — helper tests.
- **Modify:** `mcp_server/tests/test_plan_graph_runner.py` — allowlist update, producer-step tests, end-to-end composition test.
- **Modify:** `mcp_server/tests/test_plan_graph_templates.py` — selection / disjointness / metadata-pin tests.

---

### Task 1: Role accessor (`plan_graph_projection.py`)

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_projection.py`
- Test: `mcp_server/tests/test_plan_graph_projection.py`

**Interfaces:**
- Consumes: `PlanGraphNode` from `rook.learning.plan_graph`; existing `OutcomeProjectionRole` + `_VALID_ROLES` (module-local).
- Produces: `OUTCOME_PROJECTION_ROLE_KEY: str` and `projection_role_for_node(node: PlanGraphNode) -> OutcomeProjectionRole | None`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_plan_graph_projection.py`:

```python
from rook.learning.plan_graph import PlanGraphNode
from rook.learning.plan_graph_projection import (
    OUTCOME_PROJECTION_ROLE_KEY,
    projection_role_for_node,
)


def _node_with_role(role_value):
    metadata = {} if role_value is _ABSENT else {OUTCOME_PROJECTION_ROLE_KEY: role_value}
    return PlanGraphNode(id="n", intent="x", metadata=metadata)


_ABSENT = object()


def test_role_helper_absent_returns_none():
    assert projection_role_for_node(PlanGraphNode(id="n", intent="x")) is None


@pytest.mark.parametrize("role", ["direct_task", "artifact_producer", "artifact_verifier"])
def test_role_helper_valid_returns_role(role):
    assert projection_role_for_node(_node_with_role(role)) == role


def test_role_helper_invalid_returns_none():
    assert projection_role_for_node(_node_with_role("banana")) is None


def test_role_helper_non_string_value_returns_none_no_raise():
    assert projection_role_for_node(_node_with_role(123)) is None


def test_role_key_constant_value():
    assert OUTCOME_PROJECTION_ROLE_KEY == "outcome_projection_role"
```

(`pytest` is already imported at the top of the file; place `_ABSENT` above `_node_with_role` if your linter requires definition-before-use — the helper only evaluates it at call time, so either order runs.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_projection.py -p no:cacheprovider -q`
Expected: FAIL — `ImportError: cannot import name 'OUTCOME_PROJECTION_ROLE_KEY'` (collection error).

- [ ] **Step 3: Add the accessor**

In `mcp_server/src/rook/learning/plan_graph_projection.py`, add `PlanGraphNode` to the existing import:

```python
from rook.learning.plan_graph import NodeEvidence, NodeOutcome, PlanGraphNode
```

Then, immediately after the `_MUTATION_DONE = frozenset(...)` line (i.e. after the module constants, before `_component_guid`), add:

```python
OUTCOME_PROJECTION_ROLE_KEY = "outcome_projection_role"


def projection_role_for_node(node: PlanGraphNode) -> OutcomeProjectionRole | None:
    """Return the node's declared projection role if present AND valid, else None.

    Reads ``node.metadata[OUTCOME_PROJECTION_ROLE_KEY]`` and validates it against
    the LM3F role set. Never raises -- node metadata is graph data, not API misuse
    (the raise stays in ``project_receipt_outcome`` for direct misuse).
    """
    value = node.metadata.get(OUTCOME_PROJECTION_ROLE_KEY)
    return value if value in _VALID_ROLES else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_projection.py -p no:cacheprovider -q`
Expected: PASS (all prior LM3F projection tests + the 5 new helper tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_projection.py mcp_server/tests/test_plan_graph_projection.py
git commit -m "feat(lm3g): role accessor (OUTCOME_PROJECTION_ROLE_KEY + projection_role_for_node)"
```

---

### Task 2: Producer step (`plan_graph_runner.py`)

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_runner.py`
- Test: `mcp_server/tests/test_plan_graph_runner.py`

**Interfaces:**
- Consumes: `PlanGraph`, `OutcomeStatus`, `apply_outcome`, `runnable_nodes` (already imported); `OUTCOME_PROJECTION_ROLE_KEY`, `project_receipt_outcome`, `projection_role_for_node` from `rook.learning.plan_graph_projection` (Task 1 + LM3F).
- Produces: `ProducerStepReason`, `ProducerStepResult`, `apply_producer_step(graph, node_id) -> ProducerStepResult`.

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_plan_graph_runner.py` (the file already imports `ast`, `os`, `subprocess`, `sys`, `Path`, `pytest`; add the imports below if not already present):

```python
from rook.learning.plan_graph import (
    NodeEvidence,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
)
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.learning.plan_graph_runner import apply_producer_step


def _created_with_errors_receipt(component_guid="g1"):
    return {
        "artifact_status": "created_with_errors",
        "mutation": {"status": "created", "component_guid": component_guid},
        "repair_anchor": {"component_guid": component_guid, "target_errors": ["e1"]},
    }


def _evidence(receipt):
    return NodeEvidence(
        tool_status="success",
        receipt=receipt,
        repair_anchor=receipt.get("repair_anchor") if receipt else None,
    )


_ROLE_ABSENT = object()


def _producer_verifier_graph(
    *, role="artifact_producer", create_status="ready", evidence=None
):
    metadata = {} if role is _ROLE_ABSENT else {OUTCOME_PROJECTION_ROLE_KEY: role}
    create = PlanGraphNode(
        id="create",
        intent="create",
        metadata=metadata,
        status=create_status,
        evidence=evidence,
    )
    verify = PlanGraphNode(id="verify", intent="verify", status="pending")
    return PlanGraph(
        nodes={"create": create, "verify": verify},
        edges=[PlanGraphEdge(source="create", target="verify", kind="requires")],
    )


def test_producer_step_happy_unlocks_verifier():
    g = _producer_verifier_graph(evidence=_evidence(_created_with_errors_receipt()))
    r = apply_producer_step(g, "create")
    assert r.applied
    assert r.outcome_status == "succeeded"
    assert r.graph.nodes["create"].status == "succeeded"
    assert r.graph.nodes["create"].evidence.verified is False
    assert r.graph.nodes["verify"].status == "ready"


def test_producer_step_no_mutation_evidence_applies_blocked():
    receipt = {"artifact_status": "created_with_errors", "mutation": {"status": "skipped"}}
    g = _producer_verifier_graph(evidence=NodeEvidence(tool_status="success", receipt=receipt))
    r = apply_producer_step(g, "create")
    assert r.applied
    assert r.outcome_status == "blocked"
    assert r.graph.nodes["verify"].status == "pending"


def test_producer_unknown_node_returns_input_graph():
    g = _producer_verifier_graph(evidence=_evidence(_created_with_errors_receipt()))
    r = apply_producer_step(g, "nope")
    assert not r.applied and r.reason == "unknown_node" and r.graph is g


def test_producer_node_not_runnable_returns_input_graph():
    g = _producer_verifier_graph(
        create_status="pending", evidence=_evidence(_created_with_errors_receipt())
    )
    r = apply_producer_step(g, "create")
    assert not r.applied and r.reason == "node_not_runnable" and r.graph is g


def test_producer_evidence_missing_returns_input_graph():
    g = _producer_verifier_graph(evidence=None)
    r = apply_producer_step(g, "create")
    assert not r.applied and r.reason == "evidence_missing" and r.graph is g


def test_producer_role_missing_returns_input_graph():
    g = _producer_verifier_graph(
        role=_ROLE_ABSENT, evidence=_evidence(_created_with_errors_receipt())
    )
    r = apply_producer_step(g, "create")
    assert not r.applied and r.reason == "role_missing" and r.graph is g


def test_producer_role_invalid_returns_input_graph():
    g = _producer_verifier_graph(
        role="banana", evidence=_evidence(_created_with_errors_receipt())
    )
    r = apply_producer_step(g, "create")
    assert not r.applied and r.reason == "role_invalid" and r.graph is g


def test_producer_role_not_producer_returns_input_graph():
    g = _producer_verifier_graph(
        role="artifact_verifier", evidence=_evidence(_created_with_errors_receipt())
    )
    r = apply_producer_step(g, "create")
    assert not r.applied and r.reason == "role_not_producer" and r.graph is g


def test_producer_guard_precedence_runnable_before_role():
    # pending AND invalid role -> readiness wins
    g = _producer_verifier_graph(
        role="banana",
        create_status="pending",
        evidence=_evidence(_created_with_errors_receipt()),
    )
    r = apply_producer_step(g, "create")
    assert r.reason == "node_not_runnable"
```

Also update the import-allowlist assertion in `test_runner_imports_only_plan_graph_layer` (currently the exact set `{"rook.learning.plan_graph", "rook.learning.plan_graph_verifiers"}`) to:

```python
    assert rook_or_relative == {
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_verifiers",
        "rook.learning.plan_graph_projection",
    }
```

Leave the negative assertions (`tool_dispatcher`/`plan_graph_walker`/`planner` not in imports) and the subprocess heavy-module probe unchanged.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_runner.py -p no:cacheprovider -q`
Expected: FAIL — `ImportError: cannot import name 'apply_producer_step'`.

- [ ] **Step 3: Add the producer step**

In `mcp_server/src/rook/learning/plan_graph_runner.py`, add the projection import after the existing `plan_graph_verifiers` import:

```python
from rook.learning.plan_graph_projection import (
    OUTCOME_PROJECTION_ROLE_KEY,
    project_receipt_outcome,
    projection_role_for_node,
)
```

Then append (after `apply_verifier_step`):

```python
ProducerStepReason = Literal[
    "unknown_node",
    "node_not_runnable",
    "evidence_missing",
    "role_missing",
    "role_invalid",
    "role_not_producer",
]


@dataclass(frozen=True)
class ProducerStepResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    outcome_status: OutcomeStatus | None
    reason: ProducerStepReason | None


def _producer_not_applied(
    graph: PlanGraph, node_id: str, reason: ProducerStepReason
) -> ProducerStepResult:
    return ProducerStepResult(
        graph=graph,
        applied=False,
        node_id=node_id,
        outcome_status=None,
        reason=reason,
    )


def apply_producer_step(graph: PlanGraph, node_id: str) -> ProducerStepResult:
    """Apply one producer node's outcome, projected from its OWN captured evidence.

    Producer-restricted: the node must declare
    ``metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_producer"``. Reads the
    node's own ``NodeEvidence``, projects it through the LM3F producer projection,
    and applies the result via the reducer. ``runnable_nodes`` is the sole
    readiness authority; the guard order is fixed (existence -> runnable ->
    evidence -> role) so readiness precedes data diagnostics. Never mutates the
    input graph: not-applied returns the input unchanged; applied returns the
    reducer's fresh graph.
    """
    if node_id not in graph.nodes:
        return _producer_not_applied(graph, node_id, "unknown_node")

    runnable_ids = {node.id for node in runnable_nodes(graph)}
    if node_id not in runnable_ids:
        return _producer_not_applied(graph, node_id, "node_not_runnable")

    node = graph.nodes[node_id]
    if node.evidence is None:
        return _producer_not_applied(graph, node_id, "evidence_missing")

    present = OUTCOME_PROJECTION_ROLE_KEY in node.metadata
    role = projection_role_for_node(node)
    if not present:
        return _producer_not_applied(graph, node_id, "role_missing")
    if role is None:
        return _producer_not_applied(graph, node_id, "role_invalid")
    if role != "artifact_producer":
        return _producer_not_applied(graph, node_id, "role_not_producer")

    outcome = project_receipt_outcome(node.evidence, "artifact_producer")
    new_graph = apply_outcome(graph, node_id, outcome)
    return ProducerStepResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        outcome_status=outcome.status,
        reason=None,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_runner.py -p no:cacheprovider -q`
Expected: PASS (existing LM3E runner tests + the new producer-step tests + updated allowlist).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_runner.py mcp_server/tests/test_plan_graph_runner.py
git commit -m "feat(lm3g): apply_producer_step (producer-restricted, runnable-gated)"
```

---

### Task 3: Verifier-mediated template + end-to-end proof

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph_templates.py`
- Test: `mcp_server/tests/test_plan_graph_templates.py`
- Test: `mcp_server/tests/test_plan_graph_runner.py` (end-to-end composition)

**Interfaces:**
- Consumes: existing `PlanGraph`, `PlanGraphNode`, `PlanGraphEdge`, `TemplateEntry`, `BindingSpec`, `_make_entry`, `select_template`, `select_and_bind` (templates); `initialize_graph`, `graph_status` (plan_graph); `apply_producer_step` (Task 2), `apply_verifier_step` (LM3E), `apply_tool_result` (LM1G bridge).
- Produces: `_build_gh_csharp_create_verify_repair`, a second `DEFAULT_REGISTRY` entry `gh_csharp_create_verify_repair`.

- [ ] **Step 1: Write the failing template tests**

Append to `mcp_server/tests/test_plan_graph_templates.py`:

```python
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY

_CREATE_REPAIR = {"domain": "grasshopper", "operation": "create_repair", "language": "csharp"}
_CREATE_VERIFY_REPAIR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair",
    "language": "csharp",
}


def test_select_create_verify_repair():
    sel = select_template(_CREATE_VERIFY_REPAIR)
    assert sel.selected_template_id == "gh_csharp_create_verify_repair"


def test_select_create_repair_still_selects_two_node():
    sel = select_template(_CREATE_REPAIR)
    assert sel.selected_template_id == "gh_csharp_create_repair"


def test_registry_disjoint_via_evaluation_trail():
    # canonical create_repair -> verify template mismatches on `operation`
    sel = select_template(_CREATE_REPAIR)
    assert sel.selected_template_id == "gh_csharp_create_repair"
    other = next(
        e for e in sel.evaluations if e.template_id == "gh_csharp_create_verify_repair"
    )
    assert not other.matched
    op = next(c for c in other.criteria if c.field == "operation")
    assert op.outcome == "value_mismatch"

    # canonical create_verify_repair -> 2-node template mismatches on `operation`
    sel2 = select_template(_CREATE_VERIFY_REPAIR)
    assert sel2.selected_template_id == "gh_csharp_create_verify_repair"
    other2 = next(
        e for e in sel2.evaluations if e.template_id == "gh_csharp_create_repair"
    )
    assert not other2.matched
    op2 = next(c for c in other2.criteria if c.field == "operation")
    assert op2.outcome == "value_mismatch"


def test_template_role_metadata_pinned_to_projection_constant():
    graph = select_template(_CREATE_VERIFY_REPAIR).graph
    assert graph.nodes["create_script"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_producer"
    assert graph.nodes["verify_create"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_verifier"


def test_create_verify_repair_topology():
    graph = select_template(_CREATE_VERIFY_REPAIR).graph
    assert set(graph.nodes) == {"create_script", "verify_create", "repair_same_component"}
    assert graph.nodes["repair_same_component"].is_terminal is True
    kinds = {(e.source, e.target): e.kind for e in graph.edges}
    assert kinds[("create_script", "verify_create")] == "requires"
    assert kinds[("verify_create", "repair_same_component")] == "on_repair"
```

- [ ] **Step 2: Run to verify failure**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_templates.py -p no:cacheprovider -q`
Expected: FAIL — `gh_csharp_create_verify_repair` not selected (no such registry entry).

- [ ] **Step 3: Add the template + registry entry**

In `mcp_server/src/rook/learning/plan_graph_templates.py`, add the builder after `_build_gh_csharp_create_repair`:

```python
def _build_gh_csharp_create_verify_repair() -> PlanGraph:
    """Verifier-mediated GH C# create -> verify -> repair (LM3G).

    create_script (artifact_producer) lands ``succeeded`` from a
    ``created_with_errors`` receipt via the producer projection, unlocking
    verify_create through the ``requires`` edge; verify_create maps the same
    evidence to ``needs_repair``, routing to the in-place repair node via
    ``on_repair``. Terminal means the repair step returned ``usable`` through the
    bridge -- NOT that a second verifier reverified the artifact clean.
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
        ],
    )
```

Then add the second entry to `DEFAULT_REGISTRY` (after the existing `gh_csharp_create_repair` entry, inside the tuple):

```python
    _make_entry(
        "gh_csharp_create_verify_repair",
        {
            "domain": "grasshopper",
            "operation": "create_verify_repair",
            "language": "csharp",
        },
        _build_gh_csharp_create_verify_repair,
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

Do NOT import `plan_graph_projection` into this module — the metadata uses the literal strings `"outcome_projection_role"` / `"artifact_producer"` / `"artifact_verifier"`, pinned to the projection constant by the test above.

- [ ] **Step 4: Run template tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_templates.py -p no:cacheprovider -q`
Expected: PASS (existing LM3B/LM3C template tests + the new selection/disjointness/metadata/topology tests).

- [ ] **Step 5: Write the failing end-to-end composition test**

Append to `mcp_server/tests/test_plan_graph_runner.py` (add imports if not already present):

```python
from rook.learning.plan_graph import graph_status, initialize_graph
from rook.learning.plan_graph_bridge import apply_tool_result
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_and_bind


def _usable_raw_result(component_guid="g1"):
    return {
        "success": True,
        "data": {
            "script_receipt": {
                "artifact_status": "usable",
                "mutation": {"status": "updated", "component_guid": component_guid},
            }
        },
    }


def test_create_verify_repair_end_to_end_non_live():
    descriptor = {
        "domain": "grasshopper",
        "operation": "create_verify_repair",
        "language": "csharp",
    }
    bound = select_and_bind(descriptor)
    graph = bound.binding.graph
    assert graph is not None

    # initialize_graph EXACTLY ONCE, before any step, never after mutation
    graph = initialize_graph(graph)
    assert graph.nodes["create_script"].status == "ready"

    # inject the producer node's created_with_errors evidence (with mutation evidence)
    graph.nodes["create_script"].evidence = _evidence(_created_with_errors_receipt())

    # 1. producer step: created_with_errors -> succeeded, unlocks the verifier
    pr = apply_producer_step(graph, "create_script")
    assert pr.applied and pr.outcome_status == "succeeded"
    graph = pr.graph
    assert graph.nodes["create_script"].evidence.verified is False
    assert graph.nodes["verify_create"].status == "ready"

    # 2. verifier step: same evidence -> needs_repair, unlocks repair via on_repair
    vr = apply_verifier_step(graph, "verify_create", "create_script")
    assert vr.applied and vr.outcome_status == "needs_repair"
    graph = vr.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # 3. repair via the LM1G bridge ONLY (not the walker)
    graph = apply_tool_result(graph, "repair_same_component", _usable_raw_result())
    assert graph.nodes["repair_same_component"].status == "succeeded"

    # 4. terminal repair succeeded -> graph complete
    assert graph_status(graph) == "complete"
```

- [ ] **Step 6: Run to verify failure, then it should pass once Task 3 Step 3 is in**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_runner.py::test_create_verify_repair_end_to_end_non_live -p no:cacheprovider -q`
Expected: PASS (Task 2 + Task 3 Step 3 provide everything; the template, producer step, verifier step, and bridge compose to `complete`). If it fails on selection, confirm Task 3 Step 3 registry entry landed.

- [ ] **Step 7: Run the full PlanGraph suite + py_compile**

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
Expected: PASS (all). Then: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_projection.py mcp_server/src/rook/learning/plan_graph_runner.py mcp_server/src/rook/learning/plan_graph_templates.py` (silent).

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_templates.py \
        mcp_server/tests/test_plan_graph_templates.py \
        mcp_server/tests/test_plan_graph_runner.py
git commit -m "feat(lm3g): verifier-mediated 3-node template + end-to-end producer-unlock proof"
```

---

## Self-Review

- **Spec coverage:** role accessor (Task 1), producer-restricted step with fixed guard order + not-applied identity (Task 2), additive second template with honest naming + literal metadata (Task 3 Steps 1-4), end-to-end proof using producer/verifier primitives + bridge-only repair + single `initialize_graph` (Task 3 Step 5), runner allowlist update (Task 2), disjointness via evaluation trail (Task 3 Step 1), purity (allowlist + unchanged templates `{plan_graph}` boundary). All spec sections mapped to a task.
- **Watchpoints:** disjointness asserted via each canonical descriptor's evaluation trail showing the OTHER template's `operation` `value_mismatch` (no impossible both/neither descriptor); end-to-end calls `initialize_graph` exactly once before any step (asserted in Task 3 Step 5).
- **Placeholder scan:** none — every code step carries full code or an exact command.
- **Type consistency:** `ProducerStepResult`/`ProducerStepReason`/`apply_producer_step`, `OUTCOME_PROJECTION_ROLE_KEY`/`projection_role_for_node`, and template ids/criteria are spelled identically across tasks and match the spec.

## Execution Handoff

Three tasks (1 → 2 → 3; Task 3's end-to-end depends on 1+2). Recommended: subagent-driven-development — haiku implementer per task (transcription-plus-testing; the plan carries full code), sonnet task reviewer per task, opus final whole-branch review. Final reviewer EXTRA instructions:
(a) `apply_producer_step` uses `runnable_nodes` as the sole readiness authority; guard order existence → runnable → evidence → role is preserved (the precedence test proves pending+invalid-role → `node_not_runnable`).
(b) the producer step never defaults the role and never accepts `artifact_verifier` / `direct_task` (all three role reasons tested).
(c) every not-applied path returns the original graph object (`result.graph is graph`) — all six reasons tested.
(d) `plan_graph_templates` does NOT import `plan_graph_projection`; role metadata is literal, pinned to the constant by a test that imports the constant.
(e) the end-to-end proof drives the repair node with `apply_tool_result` ONLY, the producer/verifier nodes via their dedicated primitives, and calls `initialize_graph` exactly once before any step (never after mutation).
(f) imports: `plan_graph_runner` allowlist is exactly `{plan_graph, plan_graph_verifiers, plan_graph_projection}`; `plan_graph_projection` still only imports `plan_graph` + `plan_graph_outcomes`; no `walk_plan_graph` / LM1F / `project_receipt_outcome`-logic change; no `needs_escalation`.
