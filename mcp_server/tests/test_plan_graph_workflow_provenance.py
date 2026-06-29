"""LM4Z tests for workflow provenance over current-step envelope sources."""

from __future__ import annotations

import ast
import pathlib
from dataclasses import replace
from typing import Any

import pytest

import rook.agent.plan_graph_workflow_provenance as provenance_module
from rook.agent.plan_graph_current_step_runner import CurrentStepEnvelope
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyRecord,
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_sequence_runner import BindStep
from rook.agent.plan_graph_step_mapping import StepMappingResult
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
    load_workflow_contract_payload,
    snapshot_workflow_contract,
)
from rook.agent.plan_graph_workflow_provenance import (
    WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON,
    WORKFLOW_PROVENANCE_METADATA_INVALID_REASON,
    WORKFLOW_PROVENANCE_METADATA_KEY,
    WorkflowProvenanceEnvelopeSource,
)
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_selector import NodeSelectionProposal


_GUID = "lm4z-workflow-provenance-guid"
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
            assert params["name"] == "LM4ZWorkflowProvenance"
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
        workflow_id="lm4z_repair_contract",
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
                    "name": "LM4ZWorkflowProvenance",
                    "x": 380,
                    "y": 1120,
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
        metadata={"trace_id": "lm4z-chain", "workflow": "repair"},
    )


def _compiled_scaffold():
    return compile_workflow_contract(_repair_contract())


@pytest.fixture
def scaffold():
    return _compiled_scaffold()


def _expected_provenance(scaffold) -> dict:
    record = scaffold.compile_record
    return {
        "workflow_id": record.workflow_id,
        "contract_schema": record.contract_schema,
        "contract_fingerprint": record.contract_fingerprint,
        "compiler_id": record.compiler_id,
        "provider_id": record.provider_id,
        "selected_template_id": record.selected_template_id,
    }


def _node(node_id: str, status: str = "ready") -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph() -> PlanGraph:
    return PlanGraph(nodes={"a": _node("a")})


def _proposal(node_id: str = "a") -> NodeSelectionProposal:
    return NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id=node_id,
        candidate_node_ids=(node_id,),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )


def _mapping(node_id: str = "a") -> StepMappingResult:
    proposal = _proposal(node_id)
    revalidation = RevalidationResult(
        decision="ACCEPT",
        accepted_node_id=node_id,
        reject_reason=None,
        reason="sentinel accept",
        proposal=proposal,
        fresh_proposal=proposal,
        expected_selector_ids=("unique_ready_node:v1",),
    )
    return StepMappingResult(
        mapped=True,
        step=BindStep(node_id=node_id, base_params={}, bindings={}),
        accepted_node_id=node_id,
        failure=None,
        reason="hand-built",
        revalidation=revalidation,
    )


def _envelope(metadata: Any | None = None) -> CurrentStepEnvelope:
    return CurrentStepEnvelope(_mapping(), metadata)


def _with_compile_record(scaffold, **changes):
    return replace(
        scaffold,
        compile_record=replace(scaffold.compile_record, **changes),
    )


def test_constructor_defaults_source_to_scaffold_provider(scaffold):
    source = WorkflowProvenanceEnvelopeSource(scaffold)

    assert source.source is scaffold.provider


def test_constructor_rejects_wrong_scaffold_type():
    with pytest.raises(TypeError):
        WorkflowProvenanceEnvelopeSource(object())


def test_constructor_rejects_non_callable_source(scaffold):
    with pytest.raises(TypeError):
        WorkflowProvenanceEnvelopeSource(scaffold, source=object())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda scaffold: _with_compile_record(
            scaffold,
            contract_fingerprint="0" * 64,
        ),
        lambda scaffold: _with_compile_record(
            scaffold,
            contract_schema="rook.workflow_contract:v999",
        ),
        lambda scaffold: replace(scaffold, workflow_id="different_workflow"),
        lambda scaffold: replace(
            scaffold,
            contract_snapshot=replace(
                scaffold.contract_snapshot,
                workflow_id="different_workflow",
            ),
        ),
        lambda scaffold: _with_compile_record(
            scaffold,
            provider_id="wrong_provider:v1",
        ),
    ],
    ids=[
        "fingerprint",
        "schema",
        "workflow-id-scaffold",
        "workflow-id-snapshot",
        "provider-id",
    ],
)
def test_constructor_rejects_inconsistent_scaffold_receipts(scaffold, mutate):
    with pytest.raises(ValueError):
        WorkflowProvenanceEnvelopeSource(mutate(scaffold))


def test_delegates_exact_stream_context_and_enriches_halt(scaffold):
    graph = _graph()
    records = ()
    supply_records = (EnvelopeSupplyRecord("HALT", None, "prior"),)
    calls = []

    def source(current_graph, current_records, current_supply_records):
        calls.append((current_graph, current_records, current_supply_records))
        return EnvelopeSupplyResult("HALT", None, "stop", {"provider": "test"})

    wrapper = WorkflowProvenanceEnvelopeSource(scaffold, source=source)

    result = wrapper(graph, records, supply_records)

    assert calls == [(graph, records, supply_records)]
    assert result.decision == "HALT"
    assert result.envelope is None
    assert result.reason == "stop"
    assert result.metadata["provider"] == "test"
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


def test_enriches_supply_and_envelope_metadata_without_mutating_source(scaffold):
    source_metadata = {"provider": "test", "nested": {"value": 1}}
    envelope_metadata = {"node": "a", "nested": {"value": 2}}
    envelope = _envelope(envelope_metadata)
    delegated = EnvelopeSupplyResult(
        "SUPPLY",
        envelope,
        "selected",
        source_metadata,
    )

    def source(graph, records, supply_records):
        return delegated

    wrapper = WorkflowProvenanceEnvelopeSource(scaffold, source=source)

    result = wrapper(_graph(), (), ())

    assert result is not delegated
    assert result.decision == "SUPPLY"
    assert result.reason == "selected"
    assert result.envelope is not envelope
    assert result.envelope.mapping is envelope.mapping
    assert source_metadata == {"provider": "test", "nested": {"value": 1}}
    assert envelope_metadata == {"node": "a", "nested": {"value": 2}}

    expected = _expected_provenance(scaffold)
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
    assert result.envelope.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] is not (
        result.envelope.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]
    )

    result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]["workflow_id"] = "mutated"
    assert result.envelope.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected


def test_enriches_delegated_invalid_supply_without_envelope(scaffold):
    def source(graph, records, supply_records):
        return EnvelopeSupplyResult(
            "SUPPLY",
            None,
            "no_step_rule_for_node:a",
            {"provider": "test"},
        )

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == "no_step_rule_for_node:a"
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


def test_invalid_halt_with_envelope_preserves_envelope_reference(scaffold):
    envelope = _envelope({"node": "a"})

    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("HALT", envelope, "bad halt", {"provider": "test"})

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "HALT"
    assert result.envelope is envelope
    assert result.envelope.metadata == {"node": "a"}
    assert WORKFLOW_PROVENANCE_METADATA_KEY not in result.envelope.metadata
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


def test_unknown_decision_preserves_envelope_reference(scaffold):
    envelope = _envelope({"node": "a"})

    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("SURPRISE", envelope, "unknown", {"provider": "test"})

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SURPRISE"
    assert result.envelope is envelope
    assert result.envelope.metadata == {"node": "a"}
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


@pytest.mark.parametrize(
    "metadata,reason,error,collision_key",
    [
        (["bad"], WORKFLOW_PROVENANCE_METADATA_INVALID_REASON, "metadata_invalid", None),
        (
            {WORKFLOW_PROVENANCE_METADATA_KEY: {"fake": True}},
            WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON,
            "metadata_collision",
            WORKFLOW_PROVENANCE_METADATA_KEY,
        ),
    ],
    ids=["invalid", "collision"],
)
def test_refuses_invalid_or_colliding_supply_metadata(
    scaffold,
    metadata,
    reason,
    error,
    collision_key,
):
    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("HALT", None, "stop", metadata)

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == reason
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )
    assert result.metadata["workflow_provenance_error"] == error
    assert result.metadata["workflow_provenance_error_location"] == "supply"
    if collision_key is None:
        assert "workflow_provenance_collision_key" not in result.metadata
    else:
        assert result.metadata["workflow_provenance_collision_key"] == collision_key


@pytest.mark.parametrize(
    "metadata,reason,error,collision_key",
    [
        (["bad"], WORKFLOW_PROVENANCE_METADATA_INVALID_REASON, "metadata_invalid", None),
        (
            {WORKFLOW_PROVENANCE_METADATA_KEY: {"fake": True}},
            WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON,
            "metadata_collision",
            WORKFLOW_PROVENANCE_METADATA_KEY,
        ),
    ],
    ids=["invalid", "collision"],
)
def test_refuses_invalid_or_colliding_envelope_metadata(
    scaffold,
    metadata,
    reason,
    error,
    collision_key,
):
    envelope = _envelope(metadata)

    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("SUPPLY", envelope, "selected", {"provider": "test"})

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == reason
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )
    assert result.metadata["workflow_provenance_error"] == error
    assert result.metadata["workflow_provenance_error_location"] == "envelope"
    if collision_key is None:
        assert "workflow_provenance_collision_key" not in result.metadata
    else:
        assert result.metadata["workflow_provenance_collision_key"] == collision_key


def test_passes_non_envelope_supply_result_through_unchanged(scaffold):
    sentinel = object()

    def source(graph, records, supply_records):
        return sentinel

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result is sentinel


def test_delegated_source_exceptions_propagate(scaffold):
    def source(graph, records, supply_records):
        raise RuntimeError("source exploded")

    wrapper = WorkflowProvenanceEnvelopeSource(scaffold, source=source)

    with pytest.raises(RuntimeError, match="source exploded"):
        wrapper(_graph(), (), ())


def test_no_public_provenance_property(scaffold):
    wrapper = WorkflowProvenanceEnvelopeSource(scaffold)

    assert not hasattr(wrapper, "provenance")


@pytest.mark.asyncio
async def test_loaded_workflow_stream_records_carry_compile_provenance():
    source_snapshot = snapshot_workflow_contract(_repair_contract())
    loaded = load_workflow_contract_payload(source_snapshot.normalized_contract)
    loaded_snapshot = snapshot_workflow_contract(loaded)
    scaffold = compile_workflow_contract(loaded)
    runner = _OfflineProducerRunner()
    source = WorkflowProvenanceEnvelopeSource(scaffold)

    result = await run_current_step_stream(
        scaffold.graph,
        source,
        max_steps=scaffold.max_steps,
        runner=runner,
    )

    expected = _expected_provenance(scaffold)
    assert loaded_snapshot.contract_fingerprint == source_snapshot.contract_fingerprint
    assert scaffold.contract_snapshot.contract_fingerprint == (
        source_snapshot.contract_fingerprint
    )
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
        assert supply.metadata is not None
        assert record.metadata is not None
        assert supply.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
        assert record.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
        assert set(
            supply.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]
        ) == set(expected)
        assert set(
            record.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]
        ) == set(expected)
        assert record.ran is True
        assert record.execution_failure is None
        assert record.mapping_mapped is True
        assert record.revalidation.decision == "ACCEPT"

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
    assert final_supply.metadata["selected_node_id"] == "done"

    assert result.final_graph.nodes["done"].status == "ready"
    assert result.final_graph.nodes["done"].is_terminal is True


def test_workflow_provenance_module_stays_metadata_bridge_only():
    source = pathlib.Path(provenance_module.__file__).read_text()
    tree = ast.parse(source)

    allowed_imports = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "typing",
        "rook.agent.plan_graph_current_step_provider",
        "rook.agent.plan_graph_current_step_runner",
        "rook.agent.plan_graph_current_step_stream",
        "rook.agent.plan_graph_workflow_contract",
        "rook.learning.plan_graph",
    }
    banned_names = {
        "run_current_step_stream",
        "run_current_mapped_step",
        "execute_mapped_step",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "propose_next_node",
        "compile_workflow_contract",
        "snapshot_workflow_contract",
        "load_workflow_contract_payload",
        "run_explicit_sequence",
        "run_live_producer_node",
        "build_live_producer_record",
        "LiveProducerExpectation",
        "LiveProducerRecord",
        "LiveProducerResult",
        "LiveProducerReason",
        "SupportsLiveProducerNode",
        "run_and_record_live_producer_node",
        "apply_outcome",
        "NodeOutcome",
        "RookAgent",
        "dispatcher",
        "base_agent",
        "server",
        "LiteLLM",
        "model",
        "json",
        "yaml",
        "open",
        "Path",
    }

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    assert imported_modules <= allowed_imports
    assert imported_names.isdisjoint(banned_names)

    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert referenced_names.isdisjoint(banned_names)
    assert referenced_attrs.isdisjoint(banned_names)
