# LM4O — Proposal Revalidation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure learning-layer `revalidate_proposal(proposal, graph, expected_selector_ids)` that honors LM4N's snapshot-validity contract — it re-derives a fresh proposal via `propose_next_node(current_graph)` and ACCEPTs only when the supplied proposal *equals* the fresh one, else returns a typed REJECT. No fallback, no execution.

**Architecture:** One new pure module `learning/plan_graph_revalidation.py`, beside `plan_graph_selector.py`. It re-runs the canonical selector against the current graph and compares — distrusting policy by re-deriving the same rule, never hand-rolling readiness. No mutation, no dispatch, no typed-`Step`, no loop, no agent import. Two test deliverables: unit tests and an offline chain revalidation guard. No live test (pure gate).

**Tech Stack:** Python 3.12, pytest, Rook `learning` package (editable-installed in `mcp_server/.venv`).

## Global Constraints

From the spec (`docs/superpowers/specs/2026-06-24-lm4o-proposal-revalidation-design.md`).

- **Pure learning-layer gate.** Reads the graph only via `propose_next_node` (→ `runnable_nodes`); never mutates the `proposal` or the `graph`; never transitions/dispatches.
- **Re-derive, don't re-implement.** Revalidation calls the **module-level** `propose_next_node(graph)` (imported `from rook.learning.plan_graph_selector import propose_next_node`, so it is monkeypatchable as `plan_graph_revalidation.propose_next_node`). It must NOT hand-roll a readiness check.
- **No fallback acceptance.** A stale/mismatched supplied proposal is REJECTED even when a fresh proposal would be acceptable. `accepted_node_id` is *only ever* `proposal.selected_node_id` on ACCEPT — never `fresh.selected_node_id`. `fresh_proposal` rides along for audit but is never substituted.
- **Full-equality ACCEPT (whole-proposal distrust).** ACCEPT requires `proposal == fresh` (all fields of the frozen `NodeSelectionProposal`: `decision`, `selected_node_id`, `candidate_node_ids`, `ready_count`, `reason`, `selector_id`), not merely a matching `selected_node_id`.
- **No selector laundering.** Membership in `expected_selector_ids` is necessary but not sufficient; the supplied `selector_id` must also equal the freshly re-derived one (enforced by `proposal == fresh`, since `fresh.selector_id == "unique_ready_node:v1"`).
- **Reject reasons:** `untrusted_selector`, `not_a_selection`, `none_ready`, `no_longer_unique`, `selected_not_ready`, `proposal_mismatch`.
- **Imports:** `propose_next_node` + `NodeSelectionProposal` from `rook.learning.plan_graph_selector` (runtime, module-level); `PlanGraph` `TYPE_CHECKING`-quoted; stdlib `dataclass`/`typing`. **No `rook.agent.*`, no dispatcher/server, no `apply_outcome`/`apply_verifier_step`/`apply_producer_result`, no LiteLLM/model.**
- **Production change is EXACTLY one new module:** `mcp_server/src/rook/learning/plan_graph_revalidation.py`. No edits to any existing `src/` file; `base_agent.py` byte-stable; LM4N selector + LM4K/L/M modules + `plan_graph_walker.py` untouched. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- **No live test.** Pure gate; whole-branch diff = spec + plan + 1 module + 2 test files (5 paths).

## Seam reference (already merged — consume, do not modify)

- `propose_next_node(graph) -> NodeSelectionProposal` and `NodeSelectionProposal(decision, selected_node_id, candidate_node_ids, ready_count, reason, selector_id)` (frozen) and `_SELECTOR_ID = "unique_ready_node:v1"` — `rook.learning.plan_graph_selector`. Decisions: `SELECT_NODE` / `HALT_NONE_READY` / `HALT_AMBIGUOUS_READY`. On `SELECT_NODE`, `candidate_node_ids == (selected_node_id,)` and `ready_count == 1`; reason `"exactly one admissible ready node"`.
- `PlanGraph`, `PlanGraphNode`, `NodeOutcome`, `initialize_graph` — `rook.learning.plan_graph`. `PlanGraphNode(id, intent, status=...)` (status defaults `"pending"`, settable by kwarg). `PlanGraph(nodes={id: node})`.
- `apply_producer_result(graph, node_id, raw) -> .graph/.outcome_status`; `apply_verifier_step(graph, verifier_node_id, source_node_id) -> .graph/.outcome_status` — `rook.learning.plan_graph_runner`.
- `select_template(descriptor) -> .selected_template_id/.graph` — `rook.learning.plan_graph_templates`. The `gh_csharp_create_verify_repair_verify` template nodes: `create_script`, `verify_create`, `repair_same_component`, `verify_repair`, `done`.

---

### Task 1: Revalidation module + pure unit tests (TDD — tests first)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_revalidation.py`
- Create: `mcp_server/src/rook/learning/plan_graph_revalidation.py`

**Interfaces:**
- Consumes: `propose_next_node`, `NodeSelectionProposal` (LM4N selector); `PlanGraph`, `PlanGraphNode` (learning).
- Produces: `RevalidationDecision`, `RejectReason`, `RevalidationResult(decision, accepted_node_id, reject_reason, reason, proposal, fresh_proposal, expected_selector_ids)`, `revalidate_proposal(proposal, graph, expected_selector_ids=("unique_ready_node:v1",)) -> RevalidationResult`. Consumed by Task 2.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_revalidation.py` with exactly this content:

```python
"""LM4O unit tests for revalidate_proposal -- the pure learning-layer gate that distrusts
a supplied NodeSelectionProposal and revalidates it against the current graph by
re-deriving via propose_next_node and requiring full equality. In the focused PlanGraph
gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import rook.learning.plan_graph_revalidation as revalidation
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node
from rook.learning.plan_graph_revalidation import revalidate_proposal


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={nid: _node(nid, st) for nid, st in id_status})


def test_accept_when_proposal_equals_fresh():
    graph = _graph(("a", "ready"), ("b", "pending"))
    proposal = propose_next_node(graph)  # SELECT_NODE("a")
    assert proposal.decision == "SELECT_NODE" and proposal.selected_node_id == "a"
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "ACCEPT"
    assert result.accepted_node_id == "a"
    assert result.reject_reason is None
    assert result.fresh_proposal == proposal
    assert result.expected_selector_ids == ("unique_ready_node:v1",)


def test_reject_untrusted_selector_skips_rederive():
    graph = _graph(("a", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="other:v9",
    )
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "untrusted_selector"
    assert result.accepted_node_id is None
    assert result.fresh_proposal is None  # re-derivation skipped: provenance untrusted


def test_reject_not_a_selection():
    graph = _graph(("a", "ready"), ("b", "ready"))
    halt = propose_next_node(graph)  # HALT_AMBIGUOUS_READY
    assert halt.decision == "HALT_AMBIGUOUS_READY"
    result = revalidate_proposal(halt, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "not_a_selection"
    assert result.accepted_node_id is None


def test_reject_none_ready_when_graph_advanced():
    # Supplied a SELECT("a") from an earlier snapshot; current graph has nothing ready.
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    graph = _graph(("a", "succeeded"), ("b", "pending"))  # zero ready
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "none_ready"
    assert result.fresh_proposal is not None
    assert result.fresh_proposal.decision == "HALT_NONE_READY"


def test_reject_no_longer_unique_when_forked():
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    graph = _graph(("a", "ready"), ("b", "ready"))  # forked
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "no_longer_unique"
    assert result.fresh_proposal.decision == "HALT_AMBIGUOUS_READY"


def test_reject_selected_not_ready_no_fallback():
    # Current graph's unique ready node is "b", not the supplied "a". No fallback: the gate
    # rejects rather than substituting the (valid) fresh selection of "b".
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    graph = _graph(("a", "succeeded"), ("b", "ready"))  # unique ready is "b"
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "selected_not_ready"
    assert result.accepted_node_id is None
    assert result.fresh_proposal.selected_node_id == "b"  # present, but NOT substituted


def test_reject_proposal_mismatch_candidates_and_count():
    # P2: same selected node, but the supplied proposal's candidate_node_ids/ready_count
    # do not match the fresh re-derivation -> whole-proposal distrust rejects it.
    graph = _graph(("x", "ready"))  # fresh: SELECT("x"), candidates ("x",), ready_count 1
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="x",
        candidate_node_ids=("x", "y"),
        ready_count=2,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "proposal_mismatch"
    assert result.accepted_node_id is None


def test_reject_proposal_mismatch_selector_not_laundered():
    # P3: "custom:v1" is in expected_selector_ids (clears the untrusted gate), but the
    # fresh re-derivation's selector_id is "unique_ready_node:v1", so proposal != fresh.
    graph = _graph(("x", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="x",
        candidate_node_ids=("x",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="custom:v1",
    )
    result = revalidate_proposal(
        proposal, graph, expected_selector_ids=("custom:v1", "unique_ready_node:v1")
    )
    assert result.decision == "REJECT"
    assert result.reject_reason == "proposal_mismatch"
    assert result.accepted_node_id is None


def test_reject_proposal_mismatch_tampered_reason():
    graph = _graph(("x", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="x",
        candidate_node_ids=("x",),
        ready_count=1,
        reason="trust me",  # tampered audit field
        selector_id="unique_ready_node:v1",
    )
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "proposal_mismatch"


def test_rederive_seam_is_used(monkeypatch):
    # The load-bearing pin: the gate re-derives via the module-level propose_next_node seam
    # and received the EXACT graph object. Patch it to a sentinel; make the supplied
    # proposal equal the sentinel so the run ACCEPTs, proving the sentinel drove the result.
    received = []
    sentinel = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="sentinel",
        candidate_node_ids=("sentinel",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )

    def _fake_propose_next_node(graph):
        received.append(graph)
        return sentinel

    monkeypatch.setattr(revalidation, "propose_next_node", _fake_propose_next_node)
    sentinel_graph = object()  # gate must only route this through propose_next_node
    result = revalidate_proposal(sentinel, sentinel_graph)
    assert result.decision == "ACCEPT"
    assert result.accepted_node_id == "sentinel"
    assert result.fresh_proposal is sentinel
    assert len(received) == 1 and received[0] is sentinel_graph


def test_default_expected_rejects_foreign_selector_as_untrusted():
    graph = _graph(("a", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="custom:v1",
    )
    # Default expected does NOT include "custom:v1" -> untrusted (distinct from the P3 path
    # where it IS in expected but still fails full equality).
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "untrusted_selector"
    assert result.fresh_proposal is None


def test_frozen_pure_inputs_unchanged():
    graph = _graph(("a", "ready"), ("b", "pending"))
    node_a = graph.nodes["a"]
    before = {nid: n.status for nid, n in graph.nodes.items()}
    proposal = propose_next_node(graph)
    r1 = revalidate_proposal(proposal, graph)
    r2 = revalidate_proposal(proposal, graph)
    assert {nid: n.status for nid, n in graph.nodes.items()} == before
    assert graph.nodes["a"] is node_a  # graph not rebuilt
    assert r1 == r2  # deterministic


def test_revalidation_import_boundary():
    # Pure learning-layer: no agent/dispatcher/server/model import, and no transition
    # reducer referenced (the gate never mutates the graph).
    import rook.learning.plan_graph_revalidation as mod

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
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_revalidation.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_revalidation'`.

- [ ] **Step 3: Write the revalidation module**

Create `mcp_server/src/rook/learning/plan_graph_revalidation.py` with exactly this content:

```python
"""LM4O proposal revalidation gate (learning layer).

revalidate_proposal distrusts a supplied NodeSelectionProposal and verifies it against the
CURRENT graph: it re-derives a fresh proposal via propose_next_node(graph) and ACCEPTs only
when the supplied proposal EQUALS the fresh one (full frozen-dataclass equality). Otherwise
it returns a typed REJECT. This honors LM4N's snapshot-validity contract -- a proposal is
data about the snapshot it observed, not authority; the scaffold revalidates before acting.

Containment (load-bearing):
- re-derive, don't re-implement: the gate calls the module-level propose_next_node (never a
  hand-rolled readiness check), so it distrusts policy by re-running the SAME canonical rule.
- no fallback acceptance: a stale/mismatched supplied proposal is REJECTED even when a fresh
  proposal would be acceptable; accepted_node_id is ONLY ever proposal.selected_node_id, and
  fresh_proposal is audit-only -- never substituted. Validation must not become selection.
- whole-proposal distrust: ACCEPT requires proposal == fresh on ALL fields (NodeSelectionProposal
  is public data), not merely a matching selected_node_id.
- no selector laundering: membership in expected_selector_ids is necessary but not sufficient;
  the supplied selector_id must also equal the freshly re-derived one (enforced by proposal == fresh).

Pure: reads the graph only via propose_next_node; never mutates the proposal or the graph.
Imports only propose_next_node / NodeSelectionProposal from plan_graph_selector + PlanGraph
(TYPE_CHECKING) + stdlib. NO agent/dispatcher/server import, NO apply_outcome / apply_*_step
(it never transitions), NO model import.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


RevalidationDecision = Literal["ACCEPT", "REJECT"]
RejectReason = Literal[
    "untrusted_selector",
    "not_a_selection",
    "none_ready",
    "no_longer_unique",
    "selected_not_ready",
    "proposal_mismatch",
]

_DEFAULT_EXPECTED_SELECTOR_IDS = ("unique_ready_node:v1",)


@dataclass(frozen=True)
class RevalidationResult:
    decision: RevalidationDecision
    accepted_node_id: str | None
    reject_reason: RejectReason | None
    reason: str
    proposal: NodeSelectionProposal
    fresh_proposal: NodeSelectionProposal | None
    expected_selector_ids: tuple[str, ...]


def _reject(
    reject_reason: RejectReason,
    reason: str,
    proposal: NodeSelectionProposal,
    fresh_proposal: NodeSelectionProposal | None,
    expected_selector_ids: tuple[str, ...],
) -> RevalidationResult:
    return RevalidationResult(
        decision="REJECT",
        accepted_node_id=None,
        reject_reason=reject_reason,
        reason=reason,
        proposal=proposal,
        fresh_proposal=fresh_proposal,
        expected_selector_ids=expected_selector_ids,
    )


def revalidate_proposal(
    proposal: NodeSelectionProposal,
    graph: "PlanGraph",
    expected_selector_ids: tuple[str, ...] = _DEFAULT_EXPECTED_SELECTOR_IDS,
) -> RevalidationResult:
    """Revalidate ``proposal`` against the current ``graph`` by re-deriving and comparing.

    Re-runs ``propose_next_node(graph)`` and ACCEPTs only when the supplied proposal EQUALS
    the fresh one (full equality). No fallback: a stale/mismatched proposal is rejected even
    if a fresh proposal would be valid; the fresh proposal is audit-only and never
    substituted. Pure: never mutates ``proposal`` or ``graph``.
    """
    # 1. Trust provenance first -- do not even re-derive for an untrusted selector.
    if proposal.selector_id not in expected_selector_ids:
        return _reject(
            "untrusted_selector",
            f"proposal selector_id {proposal.selector_id!r} is not in "
            f"expected_selector_ids {expected_selector_ids!r}",
            proposal,
            None,
            expected_selector_ids,
        )

    # 2. Re-derive the fresh proposal through the canonical selector seam.
    fresh = propose_next_node(graph)

    # 3. Only a SELECT proposal is actionable.
    if proposal.decision != "SELECT_NODE":
        return _reject(
            "not_a_selection",
            f"supplied proposal decision {proposal.decision!r} is not actionable",
            proposal,
            fresh,
            expected_selector_ids,
        )

    # 4. Classify against the fresh re-derivation.
    if fresh.decision == "HALT_NONE_READY":
        return _reject(
            "none_ready",
            "no node is admissible in the current graph",
            proposal,
            fresh,
            expected_selector_ids,
        )
    if fresh.decision == "HALT_AMBIGUOUS_READY":
        return _reject(
            "no_longer_unique",
            "the current graph has multiple admissible nodes",
            proposal,
            fresh,
            expected_selector_ids,
        )

    # fresh.decision == "SELECT_NODE"
    if proposal.selected_node_id != fresh.selected_node_id:
        return _reject(
            "selected_not_ready",
            f"a different node {fresh.selected_node_id!r} is uniquely ready now",
            proposal,
            fresh,
            expected_selector_ids,
        )
    if proposal != fresh:
        return _reject(
            "proposal_mismatch",
            "selected node matches but the supplied proposal differs from the fresh one",
            proposal,
            fresh,
            expected_selector_ids,
        )

    return RevalidationResult(
        decision="ACCEPT",
        accepted_node_id=proposal.selected_node_id,
        reject_reason=None,
        reason="supplied proposal still equals the freshly re-derived proposal",
        proposal=proposal,
        fresh_proposal=fresh,
        expected_selector_ids=expected_selector_ids,
    )
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_revalidation.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 5: Confirm the production change is exactly one module, then commit**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected status: `?? mcp_server/src/rook/learning/plan_graph_revalidation.py` + `?? mcp_server/tests/test_plan_graph_revalidation.py` (+ spec/plan if uncommitted). The numstat lists only `plan_graph_revalidation.py`.

Commit:
```
git add mcp_server/src/rook/learning/plan_graph_revalidation.py mcp_server/tests/test_plan_graph_revalidation.py
git commit -m "feat(lm4o): proposal revalidation gate + unit tests

revalidate_proposal(proposal, graph, expected_selector_ids) re-derives a fresh proposal
via propose_next_node and ACCEPTs only when the supplied proposal EQUALS the fresh one
(full frozen-dataclass equality); else typed REJECT (untrusted_selector / not_a_selection
/ none_ready / no_longer_unique / selected_not_ready / proposal_mismatch). No fallback:
fresh proposal is audit-only, never substituted. Pure learning-layer; re-derive seam
monkeypatch-pinned. 13 unit tests incl. P2 whole-proposal distrust, P3 no selector
laundering, no-fallback, and AST import-boundary guard.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Chain revalidation guard (accept fresh, reject stale across a real transition)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_revalidation_chain.py`

**Interfaces:**
- Consumes: `revalidate_proposal` (Task 1), `propose_next_node`/`NodeSelectionProposal` (selector), `select_template`, `initialize_graph`, `apply_producer_result`, `apply_verifier_step`, `PlanGraph`, `PlanGraphNode`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_revalidation_chain.py` with exactly this content:

```python
"""LM4O chain revalidation guard -- a fresh proposal ACCEPTs against the graph it was
derived from, and the SAME proposal REJECTs once the graph advances one real transition
(no fallback even though another node is now validly unique). Plus a fork -> no_longer_unique.

The reducer drives the graph (apply_producer_result / apply_verifier_step); the gate only
judges whether a snapshot-time proposal still holds. HONEST SCOPE: no dispatch, no step
construction, no loop. In the focused PlanGraph gate. Run from repo root. Separate file
from test_plan_graph_revalidation.py.
"""

from __future__ import annotations

from rook.learning.plan_graph import PlanGraph, PlanGraphNode, initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_revalidation import revalidate_proposal
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4o-chain-guid"


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


def test_accept_fresh_then_reject_stale_after_transition():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # Advance so verify_create is the uniquely-ready node.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph

    proposal = propose_next_node(graph)
    assert proposal.decision == "SELECT_NODE"
    assert proposal.selected_node_id == "verify_create"

    # Fresh against the SAME graph -> ACCEPT.
    accept = revalidate_proposal(proposal, graph)
    assert accept.decision == "ACCEPT"
    assert accept.accepted_node_id == "verify_create"

    # Advance one real transition: verify_create -> needs_repair unlocks repair_same_component.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    advanced = step.graph
    assert propose_next_node(advanced).selected_node_id == "repair_same_component"

    # Revalidate the OLD verify_create proposal against the advanced graph -> REJECT,
    # NO fallback: the fresh repair_same_component selection is present but not substituted.
    stale = revalidate_proposal(proposal, advanced)
    assert stale.decision == "REJECT"
    assert stale.reject_reason == "selected_not_ready"
    assert stale.accepted_node_id is None
    assert stale.fresh_proposal.selected_node_id == "repair_same_component"
    assert stale.fresh_proposal != proposal  # fresh is a DIFFERENT proposal, not substituted


def test_fork_graph_rejects_no_longer_unique():
    # A SELECT proposal for "left" revalidated against a 2-ready fork -> no_longer_unique.
    fork = PlanGraph(
        nodes={
            "left": PlanGraphNode(id="left", intent="x", status="ready"),
            "right": PlanGraphNode(id="right", intent="x", status="ready"),
        }
    )
    proposal = propose_next_node(
        PlanGraph(nodes={"left": PlanGraphNode(id="left", intent="x", status="ready")})
    )
    assert proposal.decision == "SELECT_NODE" and proposal.selected_node_id == "left"
    result = revalidate_proposal(proposal, fork)
    assert result.decision == "REJECT"
    assert result.reject_reason == "no_longer_unique"
    assert result.accepted_node_id is None
```

- [ ] **Step 2: Run the test and verify it passes**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_revalidation_chain.py -v
```
Expected: `2 passed`. If it fails, capture the exact assertion and report — do not weaken it.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_plan_graph_revalidation_chain.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_plan_graph_revalidation_chain.py
git commit -m "test(lm4o): chain revalidation guard -- accept fresh, reject stale across a real transition

Drives the real 5-node chain to where verify_create is uniquely ready; revalidating the
fresh proposal against the same graph ACCEPTs; after apply_verifier_step advances the
graph (repair_same_component now uniquely ready), revalidating the OLD verify_create
proposal REJECTs selected_not_ready with the fresh repair selection present but NOT
substituted (no fallback). A 2-ready fork -> no_longer_unique. Honest scope: no
dispatch/step/loop; reducer drives, gate only judges.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (whole-branch)

- [ ] **Focused gate green:** PowerShell does not expand the glob; enumerate explicitly:
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_revalidation.py` (13) and `test_plan_graph_revalidation_chain.py` (2) — gate rises from the LM4N baseline of 301 by 15 to 316.

- [ ] **Production change is exactly one module:**
```
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: a single line for `mcp_server/src/rook/learning/plan_graph_revalidation.py` and nothing else.

- [ ] **`base_agent.py` byte-stable:**
```
git diff --numstat main...HEAD -- mcp_server/src/rook/agent/base_agent.py
```
Expected: empty (no output).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly five paths — the spec, this plan, the revalidation module, and the two test files. No `operations_knowledge.json`.

## Self-Review

**Spec coverage:**
- `RevalidationResult` shape + `revalidate_proposal` + all 6 reject reasons + ACCEPT → Task 1 module.
- Re-derive-and-compare via `propose_next_node`; full-equality ACCEPT; no fallback → Task 1 module + `test_accept_when_proposal_equals_fresh`, `test_reject_selected_not_ready_no_fallback`, `test_rederive_seam_is_used`.
- P2 whole-proposal distrust → `test_reject_proposal_mismatch_candidates_and_count`, `test_reject_proposal_mismatch_tampered_reason`.
- P3 no selector laundering → `test_reject_proposal_mismatch_selector_not_laundered` (in expected but != fresh) + `test_default_expected_rejects_foreign_selector_as_untrusted` (not in expected).
- `untrusted_selector` skips re-derive (`fresh_proposal is None`) → `test_reject_untrusted_selector_skips_rederive`.
- `not_a_selection` / `none_ready` / `no_longer_unique` → dedicated Task 1 tests.
- frozen/pure inputs → `test_frozen_pure_inputs_unchanged`.
- AST import-boundary → `test_revalidation_import_boundary`.
- Deterministic stale-across-transition (verify_create → repair_same_component, REJECT selected_not_ready, no fallback) + fork → Task 2.
- One-module production diff, `base_agent.py` byte-stable, no live test → Global Constraints + Final verification.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `revalidate_proposal(proposal, graph, expected_selector_ids=("unique_ready_node:v1",)) -> RevalidationResult(.decision, .accepted_node_id, .reject_reason, .reason, .proposal, .fresh_proposal, .expected_selector_ids)`; `RevalidationDecision ∈ {"ACCEPT","REJECT"}`; `RejectReason` 6-member literal; consumes `NodeSelectionProposal(decision, selected_node_id, candidate_node_ids, ready_count, reason, selector_id)` + `propose_next_node` from `plan_graph_selector`; `PlanGraphNode(id, intent, status=...)`; `apply_producer_result(...).graph/.outcome_status`; `apply_verifier_step(...).graph/.outcome_status`; `select_template(...).selected_template_id/.graph`. Consistent across both tasks and matching merged modules.
