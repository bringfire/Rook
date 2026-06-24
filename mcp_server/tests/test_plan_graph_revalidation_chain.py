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
