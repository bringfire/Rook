"""LM4S real chain stream guard for caller-fed current-step envelopes.

LM4S consumes only caller-supplied envelopes and must ask the caller again after
each graph advance. This test drives the real create -> verify portion of the
5-node chain, then proves the caller can observe repair readiness and stop before
LM4S runs that repair step.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_current_step_runner import CurrentStepEnvelope
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import LiveProducerResult
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

_GUID = "lm4s-chain-guid"


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
        "create_script": ProducerStep(node_id="create_script", expectation=None),
        "verify_create": VerifierStep(
            verifier_node_id="verify_create",
            source_node_id="create_script",
            expected_outcome="needs_repair",
        ),
        "repair_same_component": ProducerStep(
            node_id="repair_same_component", expectation=None
        ),
    }


class _CreateOnlyRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append(node_id)
        assert node_id == "create_script"
        inner = apply_producer_result(graph, node_id, _wrapped_failure_create_raw())
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name="gh_create_csharp_script",
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


@pytest.mark.asyncio
async def test_current_step_stream_stops_before_caller_observed_repair_node():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)
    step_map = _chain_step_map()
    runner = _CreateOnlyRunner()
    provider_calls = 0

    def provider(current_graph, records, supply_records):
        nonlocal provider_calls
        provider_calls += 1

        proposal = propose_next_node(current_graph)
        mapping = map_accepted_proposal_to_step(proposal, current_graph, step_map)

        if provider_calls == 1:
            assert proposal.selected_node_id == "create_script"
            return EnvelopeSupplyResult(
                "SUPPLY",
                CurrentStepEnvelope(mapping, {"call": provider_calls}),
                "caller supplied create_script",
            )

        if provider_calls == 2:
            assert proposal.selected_node_id == "verify_create"
            return EnvelopeSupplyResult(
                "SUPPLY",
                CurrentStepEnvelope(mapping, {"call": provider_calls}),
                "caller supplied verify_create",
            )

        assert provider_calls == 3
        assert proposal.selected_node_id == "repair_same_component"
        assert records[0].producer_node_id == "create_script"
        assert records[1].verifier_node_id == "verify_create"
        assert len(supply_records) == 2
        return EnvelopeSupplyResult(
            "HALT",
            None,
            "chain_guard_stop_before_repair",
        )

    result = await run_current_step_stream(
        graph, provider, max_steps=3, runner=runner
    )

    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 2
    assert len(result.records) == 2
    assert len(result.supply_records) == 3
    assert provider_calls == 3
    assert runner.calls == ["create_script"]

    assert result.supply_records[0].decision == "SUPPLY"
    assert result.supply_records[1].decision == "SUPPLY"
    assert result.supply_records[0].envelope.mapping is result.records[0].mapping
    assert result.supply_records[1].envelope.mapping is result.records[1].mapping

    create_record = result.records[0]
    assert create_record.execution_kind == "producer"
    assert create_record.producer_node_id == "create_script"
    assert create_record.producer_tool_name == "gh_create_csharp_script"

    verify_record = result.records[1]
    assert verify_record.execution_kind == "verifier"
    assert verify_record.verifier_node_id == "verify_create"
    assert verify_record.verifier_source_node_id == "create_script"
    assert verify_record.verifier_outcome_status == "needs_repair"

    final_supply = result.supply_records[2]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "chain_guard_stop_before_repair"

    assert propose_next_node(result.final_graph).selected_node_id == (
        "repair_same_component"
    )
    assert result.final_graph.nodes["done"].status == "pending"
    assert result.final_graph.nodes["done"].is_terminal is True
