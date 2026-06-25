"""LM4P chain mapping guard -- a fresh proposal maps to the caller's Step for the
uniquely-ready node, and the SAME proposal yields NO step once the graph advances one real
transition (no fallback even though the map holds the now-correct node's Step).

The reducer drives the graph (apply_producer_result / apply_verifier_step); LM4P only
revalidates-then-looks-up. HONEST SCOPE: LM4P returns a Step object; nothing here dispatches
or runs it -- no loop, no graph mutation driven by the mapping. In the focused PlanGraph
gate. Run from repo root. Separate file from test_plan_graph_step_mapping.py.
"""

from __future__ import annotations

from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4p-chain-guid"


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


def _chain_step_map():
    return {
        "verify_create": VerifierStep(
            verifier_node_id="verify_create",
            source_node_id="create_script",
            expected_outcome="needs_repair",
        ),
        "repair_same_component": ProducerStep(
            node_id="repair_same_component", expectation=None
        ),
    }


def test_map_fresh_then_no_step_for_stale_after_transition():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # Advance so verify_create is uniquely ready.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph

    proposal = propose_next_node(graph)
    assert proposal.selected_node_id == "verify_create"
    step_map = _chain_step_map()

    # Fresh against the same graph -> mapped to the verify_create step.
    mapped = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert mapped.mapped is True
    assert mapped.step is step_map["verify_create"]
    assert mapped.accepted_node_id == "verify_create"

    # Advance one real transition: verify_create -> needs_repair unlocks repair_same_component.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    advanced = step.graph
    assert propose_next_node(advanced).selected_node_id == "repair_same_component"

    # Map the OLD verify_create proposal against the advanced graph -> NO step. No fallback:
    # even though step_map HAS a repair_same_component entry, LM4P returns nothing.
    stale = map_accepted_proposal_to_step(proposal, advanced, step_map)
    assert stale.mapped is False
    assert stale.failure == "revalidation_rejected"
    assert stale.revalidation.reject_reason == "selected_not_ready"
    assert stale.step is None
