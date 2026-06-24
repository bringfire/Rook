# LM4N — Bounded Node-Selection Proposal Primitive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure learning-layer `propose_next_node(graph)` that observes the canonical `runnable_nodes` seam and proposes a next node only when exactly one is ready (else `HALT_NONE_READY` / `HALT_AMBIGUOUS_READY`), emitting an auditable proposal with a stable `selector_id` — the first policy-shaped artifact, with no authority.

**Architecture:** One new pure module `learning/plan_graph_selector.py`, mirroring LM3A's `plan_graph_walker.py` (pure, learning-layer, reads `runnable_nodes`, "not a scheduler"). It returns data, never mutates/dispatches/transitions, and nothing consumes it this slice. Two test deliverables: unit tests and an offline chain observation guard. No live test (pure primitive).

**Tech Stack:** Python 3.12, pytest, Rook `learning` package (editable-installed in `mcp_server/.venv`).

## Global Constraints

From the spec (`docs/superpowers/specs/2026-06-24-lm4n-node-selection-proposal-design.md`).

- **Pure learning-layer primitive.** Reads only the graph via the **module-level** `runnable_nodes`; never mutates the input graph; never transitions or dispatches.
- **Observe-not-bypass:** the selector MUST call the module-level `runnable_nodes(graph)` (imported as `from rook.learning.plan_graph import runnable_nodes`, so it is monkeypatchable as `plan_graph_selector.runnable_nodes`). It must NOT reimplement `status == "ready"`.
- **Proposal is data, not execution.** No graph mutation, no dispatch, no `apply_*` calls, no typed-`Step` construction, no LLM.
- **Snapshot-validity:** `NodeSelectionProposal` describes the observed snapshot only; it is not authority. (Documented in the module docstring; there is no consumer in LM4N.)
- **Selector identity:** `selector_id == "unique_ready_node:v1"` stamped on every decision.
- **Imports:** `runnable_nodes` from `rook.learning.plan_graph` (runtime, module-level); `PlanGraph` `TYPE_CHECKING`-quoted; stdlib `dataclass`/`typing`. **No `rook.agent.*`, no dispatcher/server, no `apply_outcome`/`apply_verifier_step`/`apply_producer_result` reference, no LiteLLM/model import.**
- **Production change is EXACTLY one new module:** `mcp_server/src/rook/learning/plan_graph_selector.py`. No edits to any existing `src/` file; `base_agent.py` byte-stable; LM4K/L/M modules and `plan_graph_walker.py` untouched. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- **No live test.** Pure primitive; whole-branch diff = spec + plan + 1 module + 2 test files (5 paths).

## Seam reference (already merged — consume, do not modify)

- `PlanGraph`, `PlanGraphNode`, `NodeOutcome`, `runnable_nodes`, `apply_outcome`, `initialize_graph` — `rook.learning.plan_graph`. `PlanGraphNode(id, intent, status=...)` (status defaults `"pending"`; settable by kwarg). `PlanGraph(nodes={id: node})`.
- `apply_producer_result(graph, node_id, raw) -> .graph/.outcome_status`; `apply_verifier_step(graph, verifier_node_id, source_node_id) -> .graph/.outcome_status` — `rook.learning.plan_graph_runner`.
- `select_template(descriptor) -> .selected_template_id/.graph` — `rook.learning.plan_graph_templates`. The `gh_csharp_create_verify_repair_verify` template has nodes `create_script`, `verify_create`, `repair_same_component`, `verify_repair`, `done`.

---

### Task 1: Selector module + pure unit tests (TDD — tests first)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_selector.py`
- Create: `mcp_server/src/rook/learning/plan_graph_selector.py`

**Interfaces:**
- Consumes: `runnable_nodes`, `PlanGraph`, `PlanGraphNode` (learning).
- Produces: `SelectionDecision`, `NodeSelectionProposal(decision, selected_node_id, candidate_node_ids, ready_count, reason, selector_id)`, `propose_next_node(graph) -> NodeSelectionProposal`, `_SELECTOR_ID = "unique_ready_node:v1"`. Consumed by Task 2.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_selector.py` with exactly this content:

```python
"""LM4N unit tests for propose_next_node -- the pure learning-layer node-selection
proposal primitive. Observes the canonical runnable_nodes seam; proposes a node ONLY when
exactly one is ready; else halts. In the focused PlanGraph gate (test_plan_graph*.py).
Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import rook.learning.plan_graph_selector as selector
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_selector import propose_next_node


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={nid: _node(nid, st) for nid, st in id_status})


def test_exactly_one_ready_selects():
    graph = _graph(("a", "ready"), ("b", "pending"))
    p = propose_next_node(graph)
    assert p.decision == "SELECT_NODE"
    assert p.selected_node_id == "a"
    assert p.candidate_node_ids == ("a",)
    assert p.ready_count == 1
    assert p.selector_id == "unique_ready_node:v1"
    assert p.reason == "exactly one admissible ready node"


def test_zero_ready_halts_none():
    graph = _graph(("a", "pending"), ("b", "succeeded"))
    p = propose_next_node(graph)
    assert p.decision == "HALT_NONE_READY"
    assert p.selected_node_id is None
    assert p.candidate_node_ids == ()
    assert p.ready_count == 0
    assert p.selector_id == "unique_ready_node:v1"


def test_multiple_ready_halts_ambiguous():
    graph = _graph(("a", "ready"), ("b", "ready"))
    p = propose_next_node(graph)
    assert p.decision == "HALT_AMBIGUOUS_READY"
    assert p.selected_node_id is None
    assert p.candidate_node_ids == ("a", "b")
    assert p.ready_count == 2
    assert p.reason == "2 admissible ready nodes; refusing to choose"


def test_candidate_sorting_determinism():
    # Insert ready nodes out of lexical order -> candidates come back sorted.
    graph = _graph(("m", "ready"), ("a", "ready"), ("z", "ready"))
    p = propose_next_node(graph)
    assert p.candidate_node_ids == ("a", "m", "z")
    assert p.decision == "HALT_AMBIGUOUS_READY"


def test_observe_not_bypass_outcome():
    # Only the ready node is a candidate; needs_repair/pending/running are excluded.
    graph = _graph(
        ("r", "ready"),
        ("nr", "needs_repair"),
        ("p", "pending"),
        ("run", "running"),
    )
    p = propose_next_node(graph)
    assert p.candidate_node_ids == ("r",)
    assert p.decision == "SELECT_NODE"
    assert p.selected_node_id == "r"


def test_uses_runnable_nodes_seam(monkeypatch):
    # The load-bearing pin: candidates derive from the canonical runnable_nodes seam, not
    # from a private status check. Patch the seam to return sentinels with UNSORTED ids and
    # assert (a) candidates come from the patched return (sorted), (b) the patched function
    # received the EXACT graph object. An impl that filtered status=="ready" would fail.
    received = []

    class _Sentinel:
        def __init__(self, id_: str) -> None:
            self.id = id_

    def _fake_runnable_nodes(graph):
        received.append(graph)
        return [_Sentinel("z"), _Sentinel("a"), _Sentinel("m")]

    monkeypatch.setattr(selector, "runnable_nodes", _fake_runnable_nodes)
    sentinel_graph = object()  # selector must only route this through runnable_nodes
    p = propose_next_node(sentinel_graph)
    assert p.candidate_node_ids == ("a", "m", "z")
    assert p.ready_count == 3
    assert p.decision == "HALT_AMBIGUOUS_READY"
    assert len(received) == 1 and received[0] is sentinel_graph


def test_frozen_snapshot():
    graph = _graph(("a", "ready"), ("b", "pending"))
    node_a = graph.nodes["a"]
    before = {nid: n.status for nid, n in graph.nodes.items()}
    p1 = propose_next_node(graph)
    p2 = propose_next_node(graph)
    # input graph unchanged (statuses + node identity), and the call is deterministic.
    assert {nid: n.status for nid, n in graph.nodes.items()} == before
    assert graph.nodes["a"] is node_a  # the selector did not replace/rebuild the node
    assert p1 == p2


def test_selector_id_on_all_decisions():
    select = propose_next_node(_graph(("a", "ready")))
    none = propose_next_node(_graph(("a", "pending")))
    ambig = propose_next_node(_graph(("a", "ready"), ("b", "ready")))
    assert select.decision == "SELECT_NODE"
    assert none.decision == "HALT_NONE_READY"
    assert ambig.decision == "HALT_AMBIGUOUS_READY"
    for p in (select, none, ambig):
        assert p.selector_id == "unique_ready_node:v1"


def test_selector_import_boundary():
    # Pure learning-layer: no agent/dispatcher/server/model import, and no transition
    # helper referenced (the selector never mutates the graph).
    import rook.learning.plan_graph_selector as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    assert not any(m.startswith("rook.agent") for m in imported), imported
    assert not any(m.startswith("rook.server") for m in imported), imported
    assert not any("dispatch" in m for m in imported), imported
    assert not any("litellm" in m for m in imported), imported
    for banned in ("apply_outcome", "apply_verifier_step", "apply_producer_result"):
        assert banned not in referenced, banned
```

- [ ] **Step 2: Run the tests to verify they fail (module missing)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_selector.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_selector'`.

- [ ] **Step 3: Write the selector module**

Create `mcp_server/src/rook/learning/plan_graph_selector.py` with exactly this content:

```python
"""LM4N bounded node-selection proposal primitive (learning layer).

propose_next_node observes a frozen PlanGraph snapshot via the canonical runnable_nodes
seam and PROPOSES a next node ONLY when exactly one node is ready. Zero ready and multiple
ready are both halts. It is the first policy-shaped artifact in the campaign: it NAMES a
selection rule (selector_id) without giving policy any authority.

Containment (load-bearing):
- policy governs scaffold transition PROPOSALS, not model reasoning; no LLM.
- admissible nodes are OBSERVED, not bypassed: this calls the module-level runnable_nodes
  (never reimplements status == "ready"), so the readiness authority stays single-sourced.
- the proposal is DATA, not execution: no graph mutation, no dispatch, no transition.
- snapshot-validity: a NodeSelectionProposal describes the snapshot observed at call time;
  it is NOT authority -- any future consumer MUST revalidate against the current graph
  before acting on it.

Pure: reads only the graph via runnable_nodes; never mutates it. Imports only
runnable_nodes / PlanGraph from plan_graph + stdlib. NO agent/dispatcher/server import, NO
apply_outcome / apply_*_step (it never transitions), NO model import. LM3A's
plan_graph_walker.py is the analogous pure-read precedent ("not a scheduler").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.learning.plan_graph import runnable_nodes

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


SelectionDecision = Literal["SELECT_NODE", "HALT_NONE_READY", "HALT_AMBIGUOUS_READY"]

_SELECTOR_ID = "unique_ready_node:v1"


@dataclass(frozen=True)
class NodeSelectionProposal:
    decision: SelectionDecision
    selected_node_id: str | None
    candidate_node_ids: tuple[str, ...]
    ready_count: int
    reason: str
    selector_id: str


def propose_next_node(graph: "PlanGraph") -> NodeSelectionProposal:
    """Propose the next node iff exactly one node is admissible (ready).

    Observes admissibility through the canonical ``runnable_nodes`` seam (never a private
    status check). Returns an auditable proposal carrying the sorted candidate set, a
    reason, and the stable ``selector_id``. Pure: never mutates ``graph``; never transitions
    or dispatches. SNAPSHOT-VALIDITY: the proposal describes the observed snapshot only and
    is not authority -- a consumer must revalidate before acting.
    """
    candidate_node_ids = tuple(sorted(node.id for node in runnable_nodes(graph)))
    ready_count = len(candidate_node_ids)

    if ready_count == 1:
        return NodeSelectionProposal(
            decision="SELECT_NODE",
            selected_node_id=candidate_node_ids[0],
            candidate_node_ids=candidate_node_ids,
            ready_count=ready_count,
            reason="exactly one admissible ready node",
            selector_id=_SELECTOR_ID,
        )
    if ready_count == 0:
        return NodeSelectionProposal(
            decision="HALT_NONE_READY",
            selected_node_id=None,
            candidate_node_ids=candidate_node_ids,
            ready_count=ready_count,
            reason="no admissible ready node",
            selector_id=_SELECTOR_ID,
        )
    return NodeSelectionProposal(
        decision="HALT_AMBIGUOUS_READY",
        selected_node_id=None,
        candidate_node_ids=candidate_node_ids,
        ready_count=ready_count,
        reason=f"{ready_count} admissible ready nodes; refusing to choose",
        selector_id=_SELECTOR_ID,
    )
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_selector.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 5: Confirm the production change is exactly one module, then commit**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected status: `?? mcp_server/src/rook/learning/plan_graph_selector.py` + `?? mcp_server/tests/test_plan_graph_selector.py` (+ spec/plan if uncommitted). The numstat lists only `plan_graph_selector.py`.

Commit:
```
git add mcp_server/src/rook/learning/plan_graph_selector.py mcp_server/tests/test_plan_graph_selector.py
git commit -m "feat(lm4n): pure node-selection proposal primitive + unit tests

propose_next_node(graph) observes the canonical runnable_nodes seam and proposes a
node ONLY when exactly one is ready (SELECT_NODE); zero -> HALT_NONE_READY, >=2 ->
HALT_AMBIGUOUS_READY. Auditable NodeSelectionProposal (sorted candidates + reason +
selector_id 'unique_ready_node:v1'). Pure: no mutation, no dispatch, no transition, no
agent/model import. 9 unit tests incl. the uses-runnable_nodes seam pin (monkeypatch)
+ frozen-snapshot + AST import-boundary guard.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Chain observation guard (selector tracks the linear chain, refuses on a fork)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_selector_chain.py`

**Interfaces:**
- Consumes: `propose_next_node` (Task 1), `select_template`, `initialize_graph`, `apply_producer_result`, `apply_verifier_step`, `apply_outcome`, `NodeOutcome`, `PlanGraph`, `PlanGraphNode`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_selector_chain.py` with exactly this content:

```python
"""LM4N chain observation guard -- propose_next_node tracks the 5-node repair chain's
unique-ready property at every transition, and refuses on a fork.

The reducer drives the graph (apply_producer_result / apply_verifier_step / apply_outcome);
the selector merely OBSERVES each resulting snapshot. HONEST SCOPE: nothing consumes the
proposal -- the selector only proposes; there is no dispatch or mutation driven by it. In
the focused PlanGraph gate. Run from repo root. Separate file from
test_plan_graph_selector.py.
"""

from __future__ import annotations

from rook.learning.plan_graph import (
    NodeOutcome,
    PlanGraph,
    PlanGraphNode,
    apply_outcome,
    initialize_graph,
)
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4n-chain-guid"


def _wrapped_failure_create_raw() -> dict:
    return {
        "success": False,
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


def _selected(graph) -> str | None:
    p = propose_next_node(graph)
    assert p.decision == "SELECT_NODE", p
    return p.selected_node_id


def test_selector_tracks_linear_chain_unique_ready():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # Root: only create_script is ready.
    assert _selected(graph) == "create_script"

    # create -> only verify_create ready.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph
    assert _selected(graph) == "verify_create"

    # verify_create -> needs_repair -> only repair_same_component ready.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert _selected(graph) == "repair_same_component"

    # repair -> only verify_repair ready.
    repair = apply_producer_result(
        graph, "repair_same_component", _unwrapped_success_repair_raw()
    )
    assert repair.outcome_status == "succeeded"
    graph = repair.graph
    assert _selected(graph) == "verify_repair"

    # verify_repair -> succeeded -> only done ready.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert _selected(graph) == "done"

    # terminal done -> no ready node -> HALT_NONE_READY.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    p = propose_next_node(graph)
    assert p.decision == "HALT_NONE_READY"
    assert p.candidate_node_ids == ()


def test_fork_graph_halts_ambiguous():
    # Two ready nodes -> the selector refuses to choose.
    graph = PlanGraph(
        nodes={
            "left": PlanGraphNode(id="left", intent="x", status="ready"),
            "right": PlanGraphNode(id="right", intent="x", status="ready"),
        }
    )
    p = propose_next_node(graph)
    assert p.decision == "HALT_AMBIGUOUS_READY"
    assert p.selected_node_id is None
    assert p.candidate_node_ids == ("left", "right")
    assert p.ready_count == 2
```

- [ ] **Step 2: Run the test and verify it passes**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_selector_chain.py -v
```
Expected: `2 passed`. If it fails, capture the exact assertion and report — do not weaken it.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_plan_graph_selector_chain.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_plan_graph_selector_chain.py
git commit -m "test(lm4n): chain observation guard -- tracks unique-ready chain, refuses on fork

Drives the real 5-node gh_csharp_create_verify_repair_verify template through the
reducer and asserts propose_next_node proposes the unique next node at each transition
(create -> verify_create -> repair -> verify_repair -> done), then HALT_NONE_READY at the
terminal; a hand-built 2-ready fork -> HALT_AMBIGUOUS_READY. Honest scope: the selector
only proposes; the reducer drives the graph, nothing consumes the proposal.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (whole-branch)

- [ ] **Focused gate green:** PowerShell does not expand the glob; enumerate explicitly:
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_selector.py` (9) and `test_plan_graph_selector_chain.py` (2) — gate rises from the LM4M baseline of 290 by 11 to 301.

- [ ] **Production change is exactly one module:**
```
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: a single line for `mcp_server/src/rook/learning/plan_graph_selector.py` and nothing else.

- [ ] **`base_agent.py` byte-stable:**
```
git diff --numstat main...HEAD -- mcp_server/src/rook/agent/base_agent.py
```
Expected: empty (no output).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly five paths — the spec, this plan, the selector module, and the two test files. No `operations_knowledge.json`.

## Self-Review

**Spec coverage:**
- `NodeSelectionProposal` shape + `propose_next_node` + `_SELECTOR_ID` + the three decisions → Task 1 module.
- Trivial-case logic (1 → SELECT, 0 → HALT_NONE, ≥2 → HALT_AMBIGUOUS), sorted candidates, `selector_id` on every path → Task 1 module + tests.
- Observe-not-bypass OUTCOME + the load-bearing SEAM pin (monkeypatch `runnable_nodes`) → Task 1 `test_observe_not_bypass_outcome` + `test_uses_runnable_nodes_seam`.
- Frozen-snapshot purity → Task 1 `test_frozen_snapshot`.
- AST import-boundary (no agent/dispatcher/server/model; no `apply_*` transition reference) → Task 1 `test_selector_import_boundary`.
- Linear-chain unique-ready tracking + fork refusal → Task 2.
- Snapshot-validity contract → module docstring (no consumer exists in LM4N to enforce it against).
- One-module production diff, `base_agent.py` byte-stable, no live test → Global Constraints + Final verification.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `propose_next_node(graph) -> NodeSelectionProposal(.decision, .selected_node_id, .candidate_node_ids, .ready_count, .reason, .selector_id)`; `SelectionDecision ∈ {"SELECT_NODE","HALT_NONE_READY","HALT_AMBIGUOUS_READY"}`; `_SELECTOR_ID == "unique_ready_node:v1"`; `PlanGraphNode(id, intent, status=...)`; `apply_producer_result(...).graph/.outcome_status`; `apply_verifier_step(...).graph/.outcome_status`; `apply_outcome(graph, node_id, NodeOutcome(status=...))`; `select_template(...).selected_template_id/.graph`. Consistent across both tasks and matching merged modules.
