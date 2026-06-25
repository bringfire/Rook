"""LM4T live vertical proof for caller-fed current-step streams.

This test drives the full current-step ladder through LM4S with a test-local provider:
LM4N proposes, LM4P maps with embedded LM4O revalidation, LM4Q executes, LM4R records,
and LM4S threads the stream. The same-node repair turn is the pressure point: the
provider maps the first repair_same_component proposal to BindStep, then the second to
ProducerStep, deriving that switch from LM4S-provided CurrentStepRecord history.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH is unavailable. Run from repo root:
    pytest -m requires_rhino mcp_server/tests/test_live_current_step_stream_vertical_live.py
Then restore knowledge/gh/operations_knowledge.json if the live run dirties it:
    git restore knowledge/gh/operations_knowledge.json
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_current_step_runner import CurrentStepEnvelope
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_CREATE_EXPECTATION = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    tool_status="failed",
    verified=False,
    artifact_status="created_with_errors",
)
_REPAIR_EXPECTATION = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    verified=True,
    artifact_status="usable",
)


async def _ensure_gh_document() -> None:
    """Establish an active Grasshopper document or skip with evidence."""
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


@dataclass(frozen=True)
class _StepCatalog:
    create: ProducerStep
    verify_create: VerifierStep
    repair_bind: BindStep
    repair_producer: ProducerStep
    verify_repair: VerifierStep


class _CurrentStepLiveProvider:
    def __init__(self, catalog: _StepCatalog) -> None:
        self.catalog = catalog
        self.proposals = []
        self.mappings = []
        self.mapped_step_types: list[str] = []
        self.step_map_views: list[dict[str, object]] = []
        self.records_lengths: list[int] = []

    def _repair_seen(self, records) -> int:
        return sum(
            1
            for record in records
            if record.accepted_node_id == "repair_same_component"
        )

    def _step_map_for(self, selected_node_id: str, records) -> dict[str, object]:
        if selected_node_id == "create_script":
            return {"create_script": self.catalog.create}
        if selected_node_id == "verify_create":
            return {"verify_create": self.catalog.verify_create}
        if selected_node_id == "repair_same_component":
            repair_seen = self._repair_seen(records)
            if repair_seen == 0:
                return {"repair_same_component": self.catalog.repair_bind}
            if repair_seen == 1:
                return {"repair_same_component": self.catalog.repair_producer}
            raise AssertionError(f"unexpected third repair turn: {repair_seen}")
        if selected_node_id == "verify_repair":
            return {"verify_repair": self.catalog.verify_repair}
        if selected_node_id == "done":
            return {}
        raise AssertionError(f"unexpected selected node: {selected_node_id!r}")

    def __call__(self, current_graph, records, supply_records):
        self.records_lengths.append(len(records))
        proposal = propose_next_node(current_graph)
        self.proposals.append(proposal)

        if proposal.selected_node_id == "done":
            return EnvelopeSupplyResult("HALT", None, "done_ready")

        step_map = self._step_map_for(proposal.selected_node_id, records)
        self.step_map_views.append(dict(step_map))
        mapping = map_accepted_proposal_to_step(
            proposal,
            current_graph,
            step_map,
        )
        self.mappings.append(mapping)
        self.mapped_step_types.append(type(mapping.step).__name__)
        return EnvelopeSupplyResult(
            "SUPPLY",
            CurrentStepEnvelope(mapping, {"provider_call": len(self.proposals)}),
            f"caller supplied {proposal.selected_node_id}",
        )


def _build_catalog() -> _StepCatalog:
    return _StepCatalog(
        create=ProducerStep("create_script"),
        verify_create=VerifierStep(
            "verify_create",
            "create_script",
            expected_outcome="needs_repair",
        ),
        repair_bind=BindStep(
            "repair_same_component",
            {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
            {"guid": ("repair_anchor", "component_guid")},
        ),
        repair_producer=ProducerStep("repair_same_component"),
        verify_repair=VerifierStep(
            "verify_repair",
            "repair_same_component",
            expected_outcome="succeeded",
        ),
    )


async def test_live_current_step_stream_reaches_done_boundary(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    assert selection.graph.nodes["create_script"].execution_ref == (
        "gh_create_csharp_script:v1"
    )
    assert selection.graph.nodes["repair_same_component"].execution_ref == (
        "gh_update_script:v1"
    )

    graph = initialize_graph(selection.graph)
    assert graph.nodes["create_script"].status == "ready"
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4TCurrentStepStreamLive",
        "x": 350,
        "y": 880,
    }

    provider = _CurrentStepLiveProvider(_build_catalog())
    agent = RookAgent(tool_executor=_mcp_tool_executor)

    result = await run_current_step_stream(
        graph,
        provider,
        max_steps=6,
        runner=agent,
    )

    assert result.stop_reason == "provider_halt"
    assert len(result.records) == 5
    assert len(result.supply_records) == 6
    assert result.steps_attempted == 5
    assert provider.records_lengths == [0, 1, 2, 3, 4, 5]
    assert [proposal.selected_node_id for proposal in provider.proposals] == [
        "create_script",
        "verify_create",
        "repair_same_component",
        "repair_same_component",
        "verify_repair",
        "done",
    ]

    for index in range(5):
        assert result.supply_records[index].decision == "SUPPLY"
        assert result.supply_records[index].envelope is not None
        assert result.supply_records[index].envelope.mapping is result.records[
            index
        ].mapping

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "done_ready"

    expected_nodes = [
        "create_script",
        "verify_create",
        "repair_same_component",
        "repair_same_component",
        "verify_repair",
    ]
    expected_kinds = ["producer", "verifier", "bind", "producer", "verifier"]
    assert [record.accepted_node_id for record in result.records] == expected_nodes
    assert [record.execution_kind for record in result.records] == expected_kinds
    assert provider.mapped_step_types == [
        "ProducerStep",
        "VerifierStep",
        "BindStep",
        "ProducerStep",
        "VerifierStep",
    ]

    for record in result.records:
        assert record.ran is True
        assert record.execution_failure is None
        assert record.mapping_mapped is True
        assert record.revalidation.decision == "ACCEPT"
        assert record.mapping.revalidation is record.revalidation
        assert record.supplied_selected_node_id == record.accepted_node_id
        assert record.fresh_selected_node_id == record.accepted_node_id

    bind_record = result.records[2]
    repair_record = result.records[3]
    assert bind_record.accepted_node_id == "repair_same_component"
    assert repair_record.accepted_node_id == "repair_same_component"
    assert bind_record.execution_kind == "bind"
    assert repair_record.execution_kind == "producer"
    assert result.records[1].verifier_applied is True
    assert result.records[1].verifier_outcome_status == "needs_repair"
    assert bind_record.bind_applied is True
    assert result.records[4].verifier_applied is True
    assert result.records[4].verifier_outcome_status == "succeeded"
    assert bind_record.bind_result is not None
    assert bind_record.bind_result.applied is True

    create_producer = result.records[0].execution.producer_result
    repair_producer = result.records[3].execution.producer_result
    assert create_producer is not None
    assert repair_producer is not None

    create_record = build_live_producer_record(create_producer, _CREATE_EXPECTATION)
    assert create_record.tool_name == "gh_create_csharp_script"
    assert create_record.artifact_status == "created_with_errors"
    assert create_record.verified is False
    assert create_record.repair_anchor_guid is not None
    assert create_record.evaluated is True
    assert create_record.passed is True, f"mismatches={create_record.mismatches!r}"

    assert bind_record.bind_result.binding is not None
    assert bind_record.bind_result.binding.params["guid"] == (
        create_record.repair_anchor_guid
    )

    repair_live_record = build_live_producer_record(
        repair_producer,
        _REPAIR_EXPECTATION,
    )
    assert repair_live_record.tool_name == "gh_update_script"
    assert repair_live_record.artifact_status == "usable"
    assert repair_live_record.verified is True
    assert repair_live_record.tool_status is None
    assert repair_live_record.evaluated is True
    assert repair_live_record.passed is True, (
        f"mismatches={repair_live_record.mismatches!r}"
    )

    assert result.final_graph.nodes["done"].status == "ready"
    assert result.final_graph.nodes["done"].is_terminal is True
    assert graph_status(result.final_graph) != "complete"

    completed = apply_outcome(
        result.final_graph,
        "done",
        NodeOutcome(status="succeeded"),
    )
    assert graph_status(completed) == "complete"
