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
