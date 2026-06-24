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
