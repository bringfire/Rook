"""LM4W offline chain guard for compiled workflow contracts."""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_current_step_provider import CatalogCurrentStepProvider
from rook.agent.plan_graph_current_step_stream import run_current_step_stream
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    ExpectedNodeRef,
    InitialNodeParams,
    ProducerStepSpec,
    RookWorkflowContract,
    VerifierStepSpec,
    WorkflowNodeRule,
    WorkflowTemplateRef,
    compile_workflow_contract,
)
from rook.learning.plan_graph_runner import apply_producer_result


_GUID = "lm4w-workflow-contract-guid"
_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


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


def _unwrapped_success_repair_raw() -> dict:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "written", "component_guid": _GUID},
            "verification": {"status": "passed", "target_error_count": 0},
            "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
        }
    }


class _OfflineProducerRunner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append(node_id)
        if node_id == "create_script":
            assert graph.nodes["create_script"].execution_ref == (
                "gh_create_csharp_script:v1"
            )
            params = graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
            assert params["pins_out"] == ("A:double",)
            assert params["name"] == "LM4WWorkflowContract"
        elif node_id == "repair_same_component":
            assert graph.nodes["repair_same_component"].execution_ref == (
                "gh_update_script:v1"
            )
        raw = {
            "create_script": _wrapped_failure_create_raw(),
            "repair_same_component": _unwrapped_success_repair_raw(),
        }[node_id]
        tool_name = {
            "create_script": "gh_create_csharp_script",
            "repair_same_component": "gh_update_script",
        }[node_id]
        inner = apply_producer_result(graph, node_id, raw)
        assert inner.graph is not graph
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name=tool_name,
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm4w_repair_contract",
        template=WorkflowTemplateRef(
            descriptor=dict(_DESCRIPTOR),
            expected_template_id="gh_csharp_create_verify_repair_verify",
        ),
        initial_params=(
            InitialNodeParams(
                "create_script",
                {
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM4WWorkflowContract",
                    "x": 375,
                    "y": 1080,
                },
            ),
        ),
        rules=(
            WorkflowNodeRule("create_script", (ProducerStepSpec("create_script"),)),
            WorkflowNodeRule(
                "verify_create",
                (
                    VerifierStepSpec(
                        "verify_create",
                        "create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                "repair_same_component",
                (
                    BindStepSpec(
                        "repair_same_component",
                        {
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        {"guid": ("repair_anchor", "component_guid")},
                    ),
                    ProducerStepSpec("repair_same_component"),
                ),
            ),
            WorkflowNodeRule(
                "verify_repair",
                (
                    VerifierStepSpec(
                        "verify_repair",
                        "repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=("done",),
        expected_refs=(
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
            ExpectedNodeRef("repair_same_component", "gh_update_script:v1"),
        ),
        max_steps=6,
        metadata={"trace_id": "lm4w-chain", "workflow": "repair"},
    )


@pytest.mark.asyncio
async def test_compiled_workflow_contract_runs_offline_repair_stream_to_done_halt():
    scaffold = compile_workflow_contract(_repair_contract())
    runner = _OfflineProducerRunner()

    result = await run_current_step_stream(
        scaffold.graph,
        scaffold.provider,
        max_steps=scaffold.max_steps,
        runner=runner,
    )

    assert isinstance(scaffold.provider, CatalogCurrentStepProvider)
    assert scaffold.max_steps == 6
    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 5
    assert runner.calls == ["create_script", "repair_same_component"]
    assert len(result.records) == 5
    assert len(result.supply_records) == 6

    assert [record.accepted_node_id for record in result.records] == [
        "create_script",
        "verify_create",
        "repair_same_component",
        "repair_same_component",
        "verify_repair",
    ]
    assert [record.execution_kind for record in result.records] == [
        "producer",
        "verifier",
        "bind",
        "producer",
        "verifier",
    ]

    for index, record in enumerate(result.records):
        supply = result.supply_records[index]
        assert supply.decision == "SUPPLY"
        assert supply.envelope is not None
        assert supply.envelope.mapping is record.mapping
        assert record.ran is True
        assert record.execution_failure is None
        assert record.mapping_mapped is True
        assert record.revalidation.decision == "ACCEPT"

    bind_record = result.records[2]
    assert bind_record.bind_node_id == "repair_same_component"
    assert bind_record.bind_applied is True
    assert bind_record.execution.bind_result is not None
    assert bind_record.execution.bind_result.binding is not None
    assert bind_record.execution.bind_result.binding.params["guid"] == _GUID

    assert result.records[0].producer_tool_name == "gh_create_csharp_script"
    assert result.records[0].producer_outcome_status == "succeeded"
    assert result.records[1].verifier_outcome_status == "needs_repair"
    assert result.records[3].producer_tool_name == "gh_update_script"
    assert result.records[3].producer_outcome_status == "succeeded"
    assert result.records[4].verifier_outcome_status == "succeeded"

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata["selected_node_id"] == "done"

    assert result.final_graph.nodes["done"].status == "ready"
    assert result.final_graph.nodes["done"].is_terminal is True
