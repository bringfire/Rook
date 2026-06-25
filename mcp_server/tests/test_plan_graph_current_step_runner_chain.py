"""LM4R chain guard for one current mapped step plus refused stale mapping.

LM4R consumes the caller's already-mapped current step and records LM4Q execution
observations. Stale-proposal freshness is handled outside LM4R by re-running LM4P
against the advanced graph; LM4R only records the refused mapping and does not fall
back to the fresh node.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    run_current_mapped_step,
)
from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
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

_GUID = "lm4r-chain-guid"


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


def _assert_fields_none(record, field_names: tuple[str, ...]) -> None:
    assert {name: getattr(record, name) for name in field_names} == {
        name: None for name in field_names
    }


@pytest.mark.asyncio
async def test_current_step_runs_once_then_refused_mapping_records_no_fallback():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph

    proposal = propose_next_node(graph)
    assert proposal.selected_node_id == "verify_create"
    step_map = _chain_step_map()
    mapping = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert mapping.mapped is True

    result = await run_current_mapped_step(
        CurrentStepEnvelope(mapping, {"trace_id": "lm4r-chain"}), graph
    )

    record = result.record
    assert result.graph is record.execution.graph
    assert record.mapping is mapping
    assert record.revalidation is mapping.revalidation
    assert record.execution.mapping is mapping
    assert record.ran is True
    assert record.execution_kind == "verifier"
    assert record.execution_failure is None
    assert record.verifier_node_id == "verify_create"
    assert record.verifier_source_node_id == "create_script"
    assert record.verifier_applied is True
    assert record.verifier_outcome_status == "needs_repair"
    assert record.verifier_reason is None
    assert record.supplied_selected_node_id == "verify_create"
    assert record.fresh_selected_node_id == "verify_create"
    assert record.accepted_node_id == "verify_create"
    assert record.mapping_mapped is True
    assert record.mapping_failure is None
    assert record.mapped_step_target == "verify_create"
    _assert_fields_none(
        record,
        (
            "producer_node_id",
            "producer_tool_name",
            "producer_applied",
            "producer_outcome_status",
            "producer_reason",
            "bind_node_id",
            "bind_applied",
            "bind_reason",
        ),
    )
    assert propose_next_node(result.graph).selected_node_id == "repair_same_component"

    advanced = result.graph

    stale_mapping = map_accepted_proposal_to_step(proposal, advanced, step_map)
    assert stale_mapping.mapped is False
    assert stale_mapping.revalidation.reject_reason == "selected_not_ready"
    assert stale_mapping.revalidation.fresh_proposal.selected_node_id == (
        "repair_same_component"
    )

    stale_result = await run_current_mapped_step(
        CurrentStepEnvelope(stale_mapping), advanced
    )
    stale_record = stale_result.record
    assert stale_result.graph is advanced
    assert stale_record.execution.graph is advanced
    assert stale_record.mapping is stale_mapping
    assert stale_record.ran is False
    assert stale_record.execution_kind is None
    assert stale_record.execution_failure == "not_mapped"
    assert stale_record.mapped_step_target is None
    assert stale_record.supplied_selected_node_id == "verify_create"
    assert stale_record.fresh_selected_node_id == "repair_same_component"
    assert stale_record.accepted_node_id is None
    _assert_fields_none(
        stale_record,
        (
            "producer_node_id",
            "producer_tool_name",
            "producer_applied",
            "producer_outcome_status",
            "producer_reason",
            "verifier_node_id",
            "verifier_source_node_id",
            "verifier_applied",
            "verifier_outcome_status",
            "verifier_reason",
            "bind_node_id",
            "bind_applied",
            "bind_reason",
        ),
    )
