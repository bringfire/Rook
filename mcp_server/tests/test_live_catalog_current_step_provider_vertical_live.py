"""LM4V live proof for the production catalog current-step provider.

This requires_rhino test proves CatalogCurrentStepProvider can replace LM4T's
bespoke test provider in the full current-step repair stream. It is deselected
from normal CI; fresh_document plus _ensure_gh_document skip cleanly when
Rhino/GH is unavailable. Restore knowledge/gh/operations_knowledge.json if the
live run dirties it.
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_current_step_stream import run_current_step_stream
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
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
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


def _build_catalog_provider() -> CatalogCurrentStepProvider:
    return CatalogCurrentStepProvider(
        (
            NodeStepRule("create_script", (ProducerStep("create_script"),)),
            NodeStepRule(
                "verify_create",
                (
                    VerifierStep(
                        "verify_create",
                        "create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            NodeStepRule(
                "repair_same_component",
                (
                    BindStep(
                        "repair_same_component",
                        {
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        {"guid": ("repair_anchor", "component_guid")},
                    ),
                    ProducerStep("repair_same_component"),
                ),
            ),
            NodeStepRule(
                "verify_repair",
                (
                    VerifierStep(
                        "verify_repair",
                        "repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=frozenset({"done"}),
    )


async def test_catalog_current_step_provider_runs_live_repair_stream(
    fresh_document,
) -> None:
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = initialize_graph(selection.graph)
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"
    assert graph.nodes["create_script"].status == "ready"
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4VCatalogCurrentStepProviderLive",
        "x": 350,
        "y": 1040,
    }

    provider = _build_catalog_provider()
    agent = RookAgent(tool_executor=_mcp_tool_executor)

    result = await run_current_step_stream(
        graph,
        provider,
        max_steps=6,
        runner=agent,
    )

    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 5
    assert len(result.records) == 5
    assert len(result.supply_records) == 6

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

    for index, record in enumerate(result.records):
        supply = result.supply_records[index]
        assert supply.decision == "SUPPLY"
        assert supply.envelope is not None
        assert supply.envelope.mapping is record.mapping
        assert supply.metadata is not None
        assert supply.metadata["provider"] == "catalog_current_step_provider:v1"
        assert supply.metadata["selected_node_id"] == record.accepted_node_id
        assert supply.metadata["proposal_decision"] == "SELECT_NODE"
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
    assert bind_record.bind_applied is True
    assert bind_record.execution.bind_result is not None
    assert bind_record.execution.bind_result.applied is True
    assert result.supply_records[2].metadata is not None
    assert result.supply_records[2].metadata["seen_count"] == 0
    assert result.supply_records[2].metadata["step_kind"] == "bind"
    assert result.supply_records[3].metadata is not None
    assert result.supply_records[3].metadata["seen_count"] == 1
    assert result.supply_records[3].metadata["step_kind"] == "producer"

    assert result.records[1].verifier_applied is True
    assert result.records[1].verifier_outcome_status == "needs_repair"
    assert result.records[4].verifier_applied is True
    assert result.records[4].verifier_outcome_status == "succeeded"

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata["proposal_decision"] == "SELECT_NODE"
    assert final_supply.metadata["selected_node_id"] == "done"

    create_producer = result.records[0].execution.producer_result
    repair_producer = result.records[3].execution.producer_result
    assert create_producer is not None
    assert repair_producer is not None

    create_live_record = build_live_producer_record(
        create_producer,
        _CREATE_EXPECTATION,
    )
    assert create_live_record.tool_name == "gh_create_csharp_script"
    assert create_live_record.artifact_status == "created_with_errors"
    assert create_live_record.verified is False
    assert create_live_record.repair_anchor_guid is not None
    assert create_live_record.evaluated is True
    assert create_live_record.passed is True, (
        f"mismatches={create_live_record.mismatches!r}"
    )

    assert bind_record.execution.bind_result.binding is not None
    assert bind_record.execution.bind_result.binding.params["guid"] == (
        create_live_record.repair_anchor_guid
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
