"""LM4Q chain execution guard -- drive the real 5-node chain through gate -> map -> execute
ONE step, then prove a stale mapping runs NOTHING (no fallback even though step_map holds a
valid entry for the now-correct node).

The reducer drives the graph (apply_producer_result / apply_verifier_step); propose_next_node
selects, map_accepted_proposal_to_step gates+translates, execute_mapped_step runs exactly one
mapped Step. HONEST SCOPE: LM4Q executes ONE step; nothing here loops to the next step, builds
a terminal `done`, or drives graph_status to "complete". In the focused PlanGraph gate. Run
from repo root. Separate file from test_plan_graph_step_executor.py.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
from rook.agent.plan_graph_step_executor import execute_mapped_step
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4q-chain-guid"


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


@pytest.mark.asyncio
async def test_execute_one_step_then_stale_mapping_runs_nothing():
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

    # gate -> map -> execute ONE verifier step (no runner needed for the verifier branch).
    mapping = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert mapping.mapped is True
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is True
    assert result.kind == "verifier"
    assert result.verifier_result.applied is True
    assert result.verifier_result.outcome_status == "needs_repair"

    # the executed step advanced the graph: repair_same_component is now uniquely ready.
    advanced = result.graph
    assert propose_next_node(advanced).selected_node_id == "repair_same_component"

    # STALE: re-map the OLD verify_create proposal against the advanced graph -> LM4P refuses;
    # execute_mapped_step runs NOTHING -- no fallback to the now-correct repair step even
    # though step_map HAS a repair_same_component entry.
    stale_mapping = map_accepted_proposal_to_step(proposal, advanced, step_map)
    assert stale_mapping.mapped is False
    assert stale_mapping.revalidation.reject_reason == "selected_not_ready"
    stale_result = await execute_mapped_step(stale_mapping, advanced)
    assert stale_result.ran is False
    assert stale_result.failure == "not_mapped"
    assert stale_result.graph is advanced  # unchanged input graph
    assert stale_result.producer_result is None
    assert stale_result.verifier_result is None
    assert stale_result.bind_result is None
