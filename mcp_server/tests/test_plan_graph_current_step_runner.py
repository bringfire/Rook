"""LM4R unit tests for run_current_mapped_step.

LM4R consumes one current-step StepMappingResult, delegates exactly once to LM4Q,
and records a flattened non-authoritative audit record. It does not propose,
revalidate, map, select, loop, evaluate, or mark terminal nodes.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import fields

import pytest

import rook.agent.plan_graph_current_step_runner as current_step
from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
    run_current_mapped_step,
)
from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import (
    StepMappingResult,
    map_accepted_proposal_to_step,
)
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node


_RECORD_FIELD_NAMES = [
    "metadata",
    "metadata_status",
    "metadata_error",
    "mapping",
    "revalidation",
    "execution",
    "supplied_selected_node_id",
    "fresh_selected_node_id",
    "accepted_node_id",
    "mapping_mapped",
    "mapping_failure",
    "mapped_step_target",
    "ran",
    "execution_kind",
    "execution_failure",
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
]

_PRODUCER_FIELDS = (
    "producer_node_id",
    "producer_tool_name",
    "producer_applied",
    "producer_outcome_status",
    "producer_reason",
)
_VERIFIER_FIELDS = (
    "verifier_node_id",
    "verifier_source_node_id",
    "verifier_applied",
    "verifier_outcome_status",
    "verifier_reason",
)
_BIND_FIELDS = ("bind_node_id", "bind_applied", "bind_reason")


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(
        nodes={node_id: _node(node_id, status) for node_id, status in id_status}
    )


def _proposal(node_id: str) -> NodeSelectionProposal:
    return NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id=node_id,
        candidate_node_ids=(node_id,),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )


def _accept_revalidation(node_id: str) -> RevalidationResult:
    proposal = _proposal(node_id)
    return RevalidationResult(
        decision="ACCEPT",
        accepted_node_id=node_id,
        reject_reason=None,
        reason="sentinel accept",
        proposal=proposal,
        fresh_proposal=proposal,
        expected_selector_ids=("unique_ready_node:v1",),
    )


def _reject_revalidation(node_id: str = "a") -> RevalidationResult:
    proposal = _proposal(node_id)
    fresh = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="fresh",
        candidate_node_ids=("fresh",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    return RevalidationResult(
        decision="REJECT",
        accepted_node_id=None,
        reject_reason="selected_not_ready",
        reason="a different node is uniquely ready now",
        proposal=proposal,
        fresh_proposal=fresh,
        expected_selector_ids=("unique_ready_node:v1",),
    )


def _hand_mapping(step, accepted: str | None, *, mapped: bool) -> StepMappingResult:
    return StepMappingResult(
        mapped=mapped,
        step=step,
        accepted_node_id=accepted,
        failure=None if mapped else "revalidation_rejected",
        reason="hand-built",
        revalidation=(
            _accept_revalidation(accepted or "a") if mapped else _reject_revalidation()
        ),
    )


def _assert_fields_none(record: CurrentStepRecord, field_names: tuple[str, ...]) -> None:
    assert {name: getattr(record, name) for name in field_names} == {
        name: None for name in field_names
    }


class _FakeProducerRunner:
    def __init__(self, result: LiveProducerResult) -> None:
        self.result = result
        self.calls: list[tuple] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append((graph, node_id))
        return self.result


class _Undeepcopyable:
    def __deepcopy__(self, memo):
        raise RuntimeError("cannot deepcopy metadata value")


@pytest.mark.asyncio
async def test_happy_producer_record_preserves_canonical_objects_and_flattens():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    step = ProducerStep("a")
    mapping = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert mapping.mapped is True

    advanced = _graph(("a", "succeeded"))
    producer_result = LiveProducerResult(
        graph=advanced,
        applied=True,
        node_id="a",
        tool_name="gh_create_csharp_script",
        outcome_status="succeeded",
        reason=None,
    )
    runner = _FakeProducerRunner(producer_result)

    metadata = {"trace_id": "lm4r-1", "nested": {"step": 1}}
    result = await run_current_mapped_step(
        CurrentStepEnvelope(mapping, metadata), graph, runner
    )

    assert result.graph is result.record.execution.graph
    assert result.graph is advanced
    assert result.record.mapping is mapping
    assert result.record.revalidation is mapping.revalidation
    assert result.record.execution.mapping is mapping
    assert result.record.metadata == {"trace_id": "lm4r-1", "nested": {"step": 1}}
    assert result.record.metadata_status == "copied"
    assert result.record.metadata_error is None
    assert result.record.supplied_selected_node_id == "a"
    assert result.record.fresh_selected_node_id == "a"
    assert result.record.accepted_node_id == "a"
    assert result.record.mapping_mapped is True
    assert result.record.mapping_failure is None
    assert result.record.mapped_step_target == "a"
    assert result.record.ran is True
    assert result.record.execution_kind == "producer"
    assert result.record.execution_failure is None
    assert result.record.producer_node_id == "a"
    assert result.record.producer_tool_name == "gh_create_csharp_script"
    assert result.record.producer_applied is True
    assert result.record.producer_outcome_status == "succeeded"
    assert result.record.producer_reason is None
    _assert_fields_none(result.record, _VERIFIER_FIELDS)
    _assert_fields_none(result.record, _BIND_FIELDS)
    assert runner.calls == [(graph, "a")]


@pytest.mark.asyncio
async def test_happy_verifier_record_flattens_verifier_only():
    from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
    from rook.learning.plan_graph_runner import apply_producer_result

    graph = _graph(("a", "ready"), ("v", "ready"))
    graph.nodes["a"].metadata[OUTCOME_PROJECTION_ROLE_KEY] = "artifact_producer"
    raw = {
        "success": True,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": "g"},
                "verification": {"status": "passed", "target_error_count": 0},
            }
        },
    }
    graph = apply_producer_result(graph, "a", raw).graph
    mapping = _hand_mapping(
        VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True
    )

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is result.record.execution.graph
    assert result.record.metadata is None
    assert result.record.metadata_status == "absent"
    assert result.record.metadata_error is None
    assert result.record.mapped_step_target == "v"
    assert result.record.ran is True
    assert result.record.execution_kind == "verifier"
    assert result.record.verifier_node_id == "v"
    assert result.record.verifier_source_node_id == "a"
    assert result.record.verifier_applied is True
    assert result.record.verifier_outcome_status == "succeeded"
    assert result.record.verifier_reason is None
    _assert_fields_none(result.record, _PRODUCER_FIELDS)
    _assert_fields_none(result.record, _BIND_FIELDS)


@pytest.mark.asyncio
async def test_happy_bind_record_flattens_bind_only():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(
        BindStep(node_id="a", base_params={}, bindings={}), "a", mapped=True
    )

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is result.record.execution.graph
    assert result.record.mapped_step_target == "a"
    assert result.record.ran is True
    assert result.record.execution_kind == "bind"
    assert result.record.bind_node_id == "a"
    assert result.record.bind_applied is True
    assert result.record.bind_reason is None
    _assert_fields_none(result.record, _PRODUCER_FIELDS)
    _assert_fields_none(result.record, _VERIFIER_FIELDS)


@pytest.mark.asyncio
async def test_refused_mapping_still_records_lm4q_not_mapped():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(None, None, mapped=False)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is graph
    assert result.record.execution.graph is graph
    assert result.record.mapping is mapping
    assert result.record.revalidation.reject_reason == "selected_not_ready"
    assert result.record.mapping_mapped is False
    assert result.record.mapping_failure == "revalidation_rejected"
    assert result.record.mapped_step_target is None
    assert result.record.ran is False
    assert result.record.execution_kind is None
    assert result.record.execution_failure == "not_mapped"
    _assert_fields_none(result.record, _PRODUCER_FIELDS)
    _assert_fields_none(result.record, _VERIFIER_FIELDS)
    _assert_fields_none(result.record, _BIND_FIELDS)


@pytest.mark.asyncio
async def test_forged_malformed_mapping_records_mapping_invalid_without_field_read_crash():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(object(), "a", mapped=True)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is graph
    assert result.record.mapped_step_target is None
    assert result.record.ran is False
    assert result.record.execution_kind is None
    assert result.record.execution_failure == "mapping_invalid"
    _assert_fields_none(result.record, _PRODUCER_FIELDS)
    _assert_fields_none(result.record, _VERIFIER_FIELDS)
    _assert_fields_none(result.record, _BIND_FIELDS)


@pytest.mark.asyncio
async def test_runner_required_refusal_records_without_producer_result():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(ProducerStep("a"), "a", mapped=True)

    result = await run_current_mapped_step(
        CurrentStepEnvelope(mapping), graph, runner=None
    )

    assert result.graph is graph
    assert result.record.ran is False
    assert result.record.execution_kind is None
    assert result.record.execution_failure == "runner_required"
    _assert_fields_none(result.record, _PRODUCER_FIELDS)
    _assert_fields_none(result.record, _VERIFIER_FIELDS)
    _assert_fields_none(result.record, _BIND_FIELDS)


@pytest.mark.asyncio
async def test_native_not_applied_is_recorded_not_reinterpreted():
    graph = _graph(("a", "ready"), ("v", "ready"))
    mapping = _hand_mapping(
        VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True
    )

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.record.ran is True
    assert result.record.execution_kind == "verifier"
    assert result.record.execution_failure is None
    assert result.record.verifier_applied is False
    assert result.record.verifier_reason == "source_evidence_missing"
    assert not hasattr(result.record, "ok")
    assert not hasattr(result.record, "passed")


@pytest.mark.asyncio
async def test_metadata_snapshot_copy_and_copy_failures_are_observations():
    graph = _graph(("a", "ready"))
    copied_mapping = _hand_mapping(
        BindStep(node_id="a", base_params={}, bindings={}), "a", mapped=True
    )
    metadata = {"nested": {"value": 1}}

    copied = await run_current_mapped_step(
        CurrentStepEnvelope(copied_mapping, metadata), graph
    )
    metadata["nested"]["value"] = 99
    assert copied.record.metadata == {"nested": {"value": 1}}
    assert copied.record.metadata_status == "copied"
    assert copied.record.metadata_error is None

    invalid = await run_current_mapped_step(
        CurrentStepEnvelope(copied_mapping, ["not", "mapping"]), graph
    )
    assert invalid.record.metadata is None
    assert invalid.record.metadata_status == "invalid"
    assert invalid.record.metadata_error is None

    bad_metadata = {"bad": _Undeepcopyable()}
    failed = await run_current_mapped_step(
        CurrentStepEnvelope(copied_mapping, bad_metadata), graph
    )
    assert failed.record.metadata is None
    assert failed.record.metadata_status == "copy_failed"
    assert "RuntimeError: cannot deepcopy metadata value" in failed.record.metadata_error


@pytest.mark.asyncio
async def test_nullable_flattened_fields_are_none_when_not_applicable():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(None, None, mapped=False)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.record.mapped_step_target is None
    assert result.record.execution_kind is None
    _assert_fields_none(result.record, _PRODUCER_FIELDS)
    _assert_fields_none(result.record, _VERIFIER_FIELDS)
    _assert_fields_none(result.record, _BIND_FIELDS)


def test_record_shape_has_no_authority_verdict_fields():
    record_fields = [field.name for field in fields(CurrentStepRecord)]
    assert record_fields == _RECORD_FIELD_NAMES
    assert set(record_fields).isdisjoint(
        {"ok", "passed", "completed", "should_continue", "graph_status"}
    )


def test_import_boundary_and_no_step_construction_or_sequence_fold():
    tree = ast.parse(pathlib.Path(current_step.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    referenced: set[str] = set()
    constructor_calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            referenced.update((alias.asname or alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            referenced.update((alias.asname or alias.name) for alias in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"ProducerStep", "VerifierStep", "BindStep"}:
                constructor_calls.append(node.func.id)

    assert constructor_calls == []
    assert [node for node in ast.walk(tree) if isinstance(node, (ast.For, ast.While))] == []
    assert "rook.agent.plan_graph_step_mapping" in imported
    assert "rook.agent.plan_graph_step_executor" in imported
    assert "rook.agent.plan_graph_sequence_runner" in imported
    assert "rook.agent.base_agent" not in imported
    assert not any(module.startswith("rook.server") for module in imported)
    assert not any("dispatch" in module for module in imported)
    assert not any("litellm" in module for module in imported)
    for banned in (
        "propose_next_node",
        "revalidate_proposal",
        "map_accepted_proposal_to_step",
        "runnable_nodes",
        "apply_outcome",
        "apply_verifier_step",
        "apply_producer_result",
        "apply_memory_bound_params",
        "run_explicit_sequence",
        "build_live_producer_record",
        "select_template",
        "dispatcher",
        "base_agent",
        "LiteLLM",
        "model",
    ):
        assert banned not in referenced, banned
