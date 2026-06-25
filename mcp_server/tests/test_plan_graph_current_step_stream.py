"""LM4S caller-fed current-step stream tests.

LM4S asks a caller-owned sync provider for one current-step envelope at a time,
records each provider decision, delegates supplied envelopes to LM4R, threads the
returned graph, and stops under bounded stream rules. It must not select,
revalidate, map, execute LM4Q directly, retry, fallback, judge, or mark terminal
completion.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import rook.agent.plan_graph_current_step_stream as stream
from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
    CurrentStepResult,
)
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_sequence_runner import BindStep
from rook.agent.plan_graph_step_executor import StepExecutionResult
from rook.agent.plan_graph_step_mapping import StepMappingResult
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_selector import NodeSelectionProposal


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


def _revalidation(node_id: str) -> RevalidationResult:
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


def _mapping(node_id: str = "a", *, mapped: bool = True) -> StepMappingResult:
    return StepMappingResult(
        mapped=mapped,
        step=BindStep(node_id=node_id, base_params={}, bindings={}) if mapped else None,
        accepted_node_id=node_id if mapped else None,
        failure=None if mapped else "revalidation_rejected",
        reason="hand-built",
        revalidation=_revalidation(node_id),
    )


def _record(graph: PlanGraph, mapping: StepMappingResult, *, ran: bool) -> CurrentStepRecord:
    execution = StepExecutionResult(
        ran=ran,
        kind="bind" if ran else None,
        graph=graph,
        failure=None if ran else "not_mapped",
        reason="sentinel",
        mapping=mapping,
    )
    return CurrentStepRecord(
        metadata=None,
        metadata_status="absent",
        metadata_error=None,
        mapping=mapping,
        revalidation=mapping.revalidation,
        execution=execution,
        supplied_selected_node_id=mapping.revalidation.proposal.selected_node_id,
        fresh_selected_node_id=mapping.revalidation.fresh_proposal.selected_node_id,
        accepted_node_id=mapping.accepted_node_id,
        mapping_mapped=mapping.mapped,
        mapping_failure=mapping.failure,
        mapped_step_target=mapping.accepted_node_id,
        ran=ran,
        execution_kind="bind" if ran else None,
        execution_failure=None if ran else "not_mapped",
        producer_node_id=None,
        producer_tool_name=None,
        producer_applied=None,
        producer_outcome_status=None,
        producer_reason=None,
        verifier_node_id=None,
        verifier_source_node_id=None,
        verifier_applied=None,
        verifier_outcome_status=None,
        verifier_reason=None,
        bind_node_id=mapping.accepted_node_id if ran else None,
        bind_applied=True if ran else None,
        bind_reason=None,
    )


def _envelope(node_id: str = "a", *, mapped: bool = True) -> CurrentStepEnvelope:
    return CurrentStepEnvelope(_mapping(node_id, mapped=mapped), {"node": node_id})


async def _install_fake_lm4r(monkeypatch, results: list[CurrentStepResult]) -> list[tuple]:
    calls: list[tuple] = []

    async def fake_run_current_mapped_step(envelope, graph, runner=None):
        calls.append((envelope, graph, runner))
        return results.pop(0)

    monkeypatch.setattr(stream, "run_current_mapped_step", fake_run_current_mapped_step)
    return calls


class _Undeepcopyable:
    def __deepcopy__(self, memo):
        raise RuntimeError("cannot deepcopy supply metadata")


class _ExplodingSupplyResult:
    def __init__(self):
        self.accessed: list[str] = []

    def __getattr__(self, name: str):
        self.accessed.append(name)
        raise AssertionError(f"unexpected supply result attribute read: {name}")


@pytest.mark.asyncio
async def test_max_steps_invalid_returns_before_provider_call():
    graph = _graph(("a", "ready"))
    calls = 0

    def provider(current_graph, records, supply_records):
        nonlocal calls
        calls += 1
        return EnvelopeSupplyResult("HALT", None, "not reached")

    result = await run_current_step_stream(graph, provider, max_steps=0)

    assert calls == 0
    assert result.final_graph is graph
    assert result.records == ()
    assert result.supply_records == ()
    assert result.stop_reason == "max_steps_invalid"
    assert result.steps_attempted == 0


@pytest.mark.asyncio
async def test_provider_halt_records_supply_without_execution():
    graph = _graph(("a", "ready"))

    def provider(current_graph, records, supply_records):
        assert current_graph is graph
        assert records == ()
        assert supply_records == ()
        return EnvelopeSupplyResult(
            "HALT", None, "caller stopped", {"trace_id": "halt-1"}
        )

    result = await run_current_step_stream(graph, provider, max_steps=1)

    assert result.final_graph is graph
    assert result.records == ()
    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 0
    assert len(result.supply_records) == 1
    supply = result.supply_records[0]
    assert supply.decision == "HALT"
    assert supply.envelope is None
    assert supply.reason == "caller stopped"
    assert supply.metadata == {"trace_id": "halt-1"}
    assert supply.metadata_status == "copied"
    assert supply.metadata_error is None
    assert supply.invalid_reason is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_result", "invalid_reason"),
    [
        (None, "supply_result_invalid"),
        (object(), "supply_result_invalid"),
        (_ExplodingSupplyResult(), "supply_result_invalid"),
        (EnvelopeSupplyResult("SUPPLY", None, None), "supply_missing_envelope"),
        (EnvelopeSupplyResult("HALT", _envelope(), "bad halt"), "halt_with_envelope"),
        (EnvelopeSupplyResult("HALT", None, None), "halt_missing_reason"),
        (EnvelopeSupplyResult("HALT", None, ""), "halt_missing_reason"),
        (EnvelopeSupplyResult("UNKNOWN", None, None), "unknown_supply_decision"),
    ],
)
async def test_provider_invalid_taxonomy_records_shape_failure(
    provider_result, invalid_reason
):
    graph = _graph(("a", "ready"))

    def provider(current_graph, records, supply_records):
        return provider_result

    result = await run_current_step_stream(graph, provider, max_steps=1)

    assert result.final_graph is graph
    assert result.records == ()
    assert result.stop_reason == "provider_invalid"
    assert result.steps_attempted == 0
    assert len(result.supply_records) == 1
    assert result.supply_records[0].invalid_reason == invalid_reason
    if invalid_reason == "supply_result_invalid":
        if isinstance(provider_result, _ExplodingSupplyResult):
            assert provider_result.accessed == []
        assert result.supply_records[0].decision is None
        assert result.supply_records[0].envelope is None
        assert result.supply_records[0].reason is None


@pytest.mark.asyncio
async def test_provider_error_records_exception_and_preserves_trace():
    graph = _graph(("a", "ready"))

    def provider(current_graph, records, supply_records):
        raise RuntimeError("provider exploded")

    result = await run_current_step_stream(graph, provider, max_steps=1)

    assert result.final_graph is graph
    assert result.records == ()
    assert result.stop_reason == "provider_error"
    assert result.steps_attempted == 0
    assert len(result.supply_records) == 1
    supply = result.supply_records[0]
    assert supply.decision is None
    assert supply.envelope is None
    assert supply.invalid_reason is None
    assert supply.error_class == "RuntimeError"
    assert supply.error_message == "provider exploded"
    assert supply.metadata_status == "absent"


@pytest.mark.asyncio
async def test_provider_metadata_copy_statuses_are_observations():
    graph = _graph(("a", "ready"))

    copied_metadata = {"nested": {"value": 1}}

    async def run_provider(provider):
        return await run_current_step_stream(graph, provider, max_steps=1)

    copied = await run_provider(
        lambda current_graph, records, supply_records: EnvelopeSupplyResult(
            "HALT", None, "stop", copied_metadata
        )
    )
    copied_metadata["nested"]["value"] = 99
    assert copied.supply_records[0].metadata == {"nested": {"value": 1}}
    assert copied.supply_records[0].metadata_status == "copied"
    assert copied.supply_records[0].metadata_error is None

    absent = await run_provider(
        lambda current_graph, records, supply_records: EnvelopeSupplyResult(
            "HALT", None, "stop"
        )
    )
    assert absent.supply_records[0].metadata is None
    assert absent.supply_records[0].metadata_status == "absent"

    invalid = await run_provider(
        lambda current_graph, records, supply_records: EnvelopeSupplyResult(
            "HALT", None, "stop", ["not", "a", "mapping"]
        )
    )
    assert invalid.supply_records[0].metadata is None
    assert invalid.supply_records[0].metadata_status == "invalid"
    assert invalid.supply_records[0].metadata_error is None

    failed = await run_provider(
        lambda current_graph, records, supply_records: EnvelopeSupplyResult(
            "HALT", None, "stop", {"bad": _Undeepcopyable()}
        )
    )
    assert failed.supply_records[0].metadata is None
    assert failed.supply_records[0].metadata_status == "copy_failed"
    assert "RuntimeError: cannot deepcopy supply metadata" in failed.supply_records[
        0
    ].metadata_error


@pytest.mark.asyncio
async def test_one_supplied_step_then_halt_aligns_supply_and_current_records(monkeypatch):
    graph = _graph(("a", "ready"))
    advanced = _graph(("a", "succeeded"), ("b", "ready"))
    envelope = _envelope("a")
    record = _record(advanced, envelope.mapping, ran=True)
    runner = object()
    calls = await _install_fake_lm4r(
        monkeypatch, [CurrentStepResult(graph=advanced, record=record)]
    )
    provider_calls = 0

    def provider(current_graph, records, supply_records):
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls == 1:
            assert current_graph is graph
            assert records == ()
            assert supply_records == ()
            return EnvelopeSupplyResult(
                "SUPPLY", envelope, "current artifact", {"trace_id": "supply-1"}
            )
        assert current_graph is advanced
        assert records == (record,)
        assert len(supply_records) == 1
        assert supply_records[0].decision == "SUPPLY"
        return EnvelopeSupplyResult("HALT", None, "done for test")

    result = await run_current_step_stream(
        graph, provider, max_steps=2, runner=runner
    )

    assert calls == [(envelope, graph, runner)]
    assert result.final_graph is advanced
    assert result.records == (record,)
    assert len(result.supply_records) == 2
    assert result.supply_records[0].decision == "SUPPLY"
    assert result.supply_records[0].envelope is envelope
    assert result.supply_records[0].metadata == {"trace_id": "supply-1"}
    assert result.supply_records[1].decision == "HALT"
    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 1


@pytest.mark.asyncio
async def test_execution_refused_appends_record_before_stop(monkeypatch):
    graph = _graph(("a", "ready"))
    envelope = _envelope("a", mapped=False)
    record = _record(graph, envelope.mapping, ran=False)
    await _install_fake_lm4r(
        monkeypatch, [CurrentStepResult(graph=graph, record=record)]
    )

    def provider(current_graph, records, supply_records):
        return EnvelopeSupplyResult("SUPPLY", envelope, "refused artifact")

    result = await run_current_step_stream(graph, provider, max_steps=2)

    assert result.final_graph is graph
    assert result.records == (record,)
    assert len(result.supply_records) == 1
    assert result.stop_reason == "execution_refused"
    assert result.steps_attempted == 1


@pytest.mark.asyncio
async def test_graph_not_advanced_appends_record_before_stop(monkeypatch):
    graph = _graph(("a", "ready"))
    envelope = _envelope("a")
    record = _record(graph, envelope.mapping, ran=True)
    await _install_fake_lm4r(
        monkeypatch, [CurrentStepResult(graph=graph, record=record)]
    )

    def provider(current_graph, records, supply_records):
        return EnvelopeSupplyResult("SUPPLY", envelope, "ran unchanged")

    result = await run_current_step_stream(graph, provider, max_steps=2)

    assert result.final_graph is graph
    assert result.records == (record,)
    assert len(result.supply_records) == 1
    assert result.stop_reason == "graph_not_advanced"
    assert result.steps_attempted == 1


@pytest.mark.asyncio
async def test_max_steps_reached_does_not_call_provider_for_extra_step(monkeypatch):
    graph = _graph(("a", "ready"))
    advanced = _graph(("a", "succeeded"))
    envelope = _envelope("a")
    record = _record(advanced, envelope.mapping, ran=True)
    await _install_fake_lm4r(
        monkeypatch, [CurrentStepResult(graph=advanced, record=record)]
    )
    provider_calls = 0

    def provider(current_graph, records, supply_records):
        nonlocal provider_calls
        provider_calls += 1
        return EnvelopeSupplyResult("SUPPLY", envelope, "only budgeted step")

    result = await run_current_step_stream(graph, provider, max_steps=1)

    assert provider_calls == 1
    assert result.final_graph is advanced
    assert result.records == (record,)
    assert len(result.supply_records) == 1
    assert result.supply_records[0].decision == "SUPPLY"
    assert result.stop_reason == "max_steps_reached"
    assert result.steps_attempted == 1


@pytest.mark.asyncio
async def test_provider_context_uses_tuple_history_not_internal_lists(monkeypatch):
    graph = _graph(("a", "ready"))
    advanced = _graph(("a", "succeeded"), ("b", "ready"))
    envelope = _envelope("a")
    record = _record(advanced, envelope.mapping, ran=True)
    await _install_fake_lm4r(
        monkeypatch, [CurrentStepResult(graph=advanced, record=record)]
    )
    seen_types = []

    def provider(current_graph, records, supply_records):
        seen_types.append((type(records), type(supply_records), records, supply_records))
        if not records:
            return EnvelopeSupplyResult("SUPPLY", envelope, "current")
        return EnvelopeSupplyResult("HALT", None, "seen prior trace")

    result = await run_current_step_stream(graph, provider, max_steps=2)

    assert result.stop_reason == "provider_halt"
    assert seen_types[0][0] is tuple
    assert seen_types[0][1] is tuple
    assert seen_types[0][2] == ()
    assert seen_types[0][3] == ()
    assert seen_types[1][0] is tuple
    assert seen_types[1][1] is tuple
    assert seen_types[1][2] == (record,)
    assert len(seen_types[1][3]) == 1
    assert seen_types[1][3][0].decision == "SUPPLY"


def test_import_boundary_and_no_authority_fields():
    tree = ast.parse(pathlib.Path(stream.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    referenced: set[str] = set()

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

    assert "rook.agent.plan_graph_current_step_runner" in imported
    assert "rook.agent.plan_graph_step_executor" not in imported
    assert "rook.agent.plan_graph_step_mapping" not in imported
    assert "rook.agent.plan_graph_revalidation" not in imported
    assert "rook.learning.plan_graph_selector" not in imported
    assert "rook.agent.plan_graph_sequence_runner" not in imported
    assert "rook.agent.base_agent" not in imported
    assert not any(module.startswith("rook.server") for module in imported)
    assert not any("dispatch" in module for module in imported)
    assert not any("litellm" in module for module in imported)
    for banned in (
        "propose_next_node",
        "revalidate_proposal",
        "map_accepted_proposal_to_step",
        "runnable_nodes",
        "execute_mapped_step",
        "apply_outcome",
        "apply_verifier_step",
        "apply_producer_result",
        "apply_memory_bound_params",
        "ProducerStep",
        "VerifierStep",
        "BindStep",
        "Step",
        "run_explicit_sequence",
        "build_live_producer_record",
        "select_template",
        "dispatcher",
        "base_agent",
        "LiteLLM",
        "model",
        "ok",
        "passed",
        "completed",
        "should_continue",
    ):
        assert banned not in referenced, banned
