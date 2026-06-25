# LM4S Current-Step Stream Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build LM4S, a caller-fed current-step stream runner that composes LM4R over a required bounded step budget without owning selection, mapping, fallback, model calls, or success judgment.

**Architecture:** Add one focused agent module, `plan_graph_current_step_stream.py`, that accepts a sync provider returning typed envelope supply results. The module records every provider decision, delegates supplied envelopes exactly once to LM4R, appends LM4R records, threads `graph = result.graph`, and stops under explicit non-authoritative stop reasons.

**Tech Stack:** Python 3, frozen dataclasses, pytest with `pytest.mark.asyncio`, existing PlanGraph/LM4N-O-P-Q-R helpers, no new dependencies.

---

## File Structure

- Create: `mcp_server/src/rook/agent/plan_graph_current_step_stream.py`
  - Owns LM4S public dataclasses, provider result validation, provider metadata copying, provider exception capture, stream stop semantics, and graph threading.
  - Imports LM4R `run_current_mapped_step` and does not import selector, revalidator, mapper, LM4Q, Step constructors, sequence runner, server, dispatcher, or model surfaces.
- Create: `mcp_server/tests/test_plan_graph_current_step_stream.py`
  - Focused unit coverage for provider shape validation, provider exceptions, metadata copying, stop precedence, supply/current-step alignment, max-step call count, provider context tuple containment, graph threading, execution refusal, graph-not-advanced, and import-boundary AST guard.
- Create: `mcp_server/tests/test_plan_graph_current_step_stream_chain.py`
  - Real PlanGraph chain guard using a caller-owned provider that prepares current artifacts outside LM4S, then lets LM4S thread two LM4R calls and halt before repair.
- Do not modify unrelated dirty files:
  - `installer/RookSetup.iss`
  - `scripts/tests/release-installer-guards.tests.ps1`

---

## Task 1: Stream Unit Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph_current_step_stream.py`

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_current_step_stream.py` with this content:

```python
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
```

- [ ] **Step 2: Run the unit tests to verify they fail for the missing module**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_stream.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'rook.agent.plan_graph_current_step_stream'`.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add -- mcp_server\tests\test_plan_graph_current_step_stream.py
git commit -m "test(lm4s): cover current-step stream contract"
```

---

## Task 2: Stream Module

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_current_step_stream.py`
- Test: `mcp_server/tests/test_plan_graph_current_step_stream.py`

- [ ] **Step 1: Implement the LM4S module**

Create `mcp_server/src/rook/agent/plan_graph_current_step_stream.py` with this content:

```python
"""LM4S caller-fed current-step stream runner.

Consumes caller-supplied current-step envelopes one at a time, records every provider
decision, delegates supplied envelopes exactly once to LM4R, and threads the returned
graph under a required step budget. No selection, freshness checking, step translation,
direct lower-level execution, fallback, retry, success judgment, terminal construction,
or model authority lives here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
    run_current_mapped_step,
)
from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


SupplyDecision = Literal["SUPPLY", "HALT"]
StopReason = Literal[
    "provider_halt",
    "provider_invalid",
    "provider_error",
    "execution_refused",
    "graph_not_advanced",
    "max_steps_reached",
    "max_steps_invalid",
]
SupplyInvalidReason = Literal[
    "supply_result_invalid",
    "supply_missing_envelope",
    "halt_with_envelope",
    "halt_missing_reason",
    "unknown_supply_decision",
]
MetadataStatus = Literal["absent", "copied", "invalid", "copy_failed"]


@dataclass(frozen=True)
class EnvelopeSupplyResult:
    decision: SupplyDecision
    envelope: CurrentStepEnvelope | None
    reason: str | None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class EnvelopeSupplyRecord:
    decision: str | None
    envelope: CurrentStepEnvelope | None
    reason: str | None
    metadata: dict[str, Any] | None
    metadata_status: MetadataStatus
    metadata_error: str | None
    invalid_reason: SupplyInvalidReason | None = None
    error_class: str | None = None
    error_message: str | None = None


EnvelopeSource = Callable[
    ["PlanGraph", tuple[CurrentStepRecord, ...], tuple[EnvelopeSupplyRecord, ...]],
    EnvelopeSupplyResult,
]


@dataclass(frozen=True)
class CurrentStepStreamResult:
    final_graph: "PlanGraph"
    records: tuple[CurrentStepRecord, ...]
    supply_records: tuple[EnvelopeSupplyRecord, ...]
    stop_reason: StopReason
    steps_attempted: int


def _copy_metadata(metadata: Any) -> tuple[dict[str, Any] | None, MetadataStatus, str | None]:
    if metadata is None:
        return None, "absent", None
    if not isinstance(metadata, Mapping):
        return None, "invalid", None
    try:
        return deepcopy(dict(metadata)), "copied", None
    except Exception as exc:
        return None, "copy_failed", f"{exc.__class__.__name__}: {exc}"


def _record_supply(
    *,
    decision: str | None,
    envelope: CurrentStepEnvelope | None,
    reason: str | None,
    metadata: Any = None,
    invalid_reason: SupplyInvalidReason | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
) -> EnvelopeSupplyRecord:
    copied_metadata, metadata_status, metadata_error = _copy_metadata(metadata)
    return EnvelopeSupplyRecord(
        decision=decision,
        envelope=envelope,
        reason=reason,
        metadata=copied_metadata,
        metadata_status=metadata_status,
        metadata_error=metadata_error,
        invalid_reason=invalid_reason,
        error_class=error_class,
        error_message=error_message,
    )


def _stream_result(
    *,
    graph: "PlanGraph",
    records: list[CurrentStepRecord],
    supply_records: list[EnvelopeSupplyRecord],
    stop_reason: StopReason,
) -> CurrentStepStreamResult:
    return CurrentStepStreamResult(
        final_graph=graph,
        records=tuple(records),
        supply_records=tuple(supply_records),
        stop_reason=stop_reason,
        steps_attempted=len(records),
    )


def _is_blank_reason(reason: str | None) -> bool:
    return reason is None or reason == ""


async def run_current_step_stream(
    initial_graph: "PlanGraph",
    envelope_source: EnvelopeSource,
    *,
    max_steps: int,
    runner: SupportsLiveProducerNode | None = None,
) -> CurrentStepStreamResult:
    """Run caller-supplied current-step envelopes through LM4R until a stop reason fires."""
    graph = initial_graph
    records: list[CurrentStepRecord] = []
    supply_records: list[EnvelopeSupplyRecord] = []

    if max_steps <= 0:
        return _stream_result(
            graph=graph,
            records=records,
            supply_records=supply_records,
            stop_reason="max_steps_invalid",
        )

    while True:
        if len(records) >= max_steps:
            return _stream_result(
                graph=graph,
                records=records,
                supply_records=supply_records,
                stop_reason="max_steps_reached",
            )

        try:
            supply = envelope_source(graph, tuple(records), tuple(supply_records))
        except Exception as exc:
            supply_records.append(
                _record_supply(
                    decision=None,
                    envelope=None,
                    reason=None,
                    error_class=exc.__class__.__name__,
                    error_message=str(exc),
                )
            )
            return _stream_result(
                graph=graph,
                records=records,
                supply_records=supply_records,
                stop_reason="provider_error",
            )

        if not isinstance(supply, EnvelopeSupplyResult):
            supply_records.append(
                _record_supply(
                    decision=None,
                    envelope=None,
                    reason=None,
                    invalid_reason="supply_result_invalid",
                )
            )
            return _stream_result(
                graph=graph,
                records=records,
                supply_records=supply_records,
                stop_reason="provider_invalid",
            )

        if supply.decision not in ("SUPPLY", "HALT"):
            supply_records.append(
                _record_supply(
                    decision=supply.decision,
                    envelope=supply.envelope,
                    reason=supply.reason,
                    metadata=supply.metadata,
                    invalid_reason="unknown_supply_decision",
                )
            )
            return _stream_result(
                graph=graph,
                records=records,
                supply_records=supply_records,
                stop_reason="provider_invalid",
            )

        if supply.decision == "SUPPLY" and supply.envelope is None:
            supply_records.append(
                _record_supply(
                    decision=supply.decision,
                    envelope=supply.envelope,
                    reason=supply.reason,
                    metadata=supply.metadata,
                    invalid_reason="supply_missing_envelope",
                )
            )
            return _stream_result(
                graph=graph,
                records=records,
                supply_records=supply_records,
                stop_reason="provider_invalid",
            )

        if supply.decision == "HALT":
            if supply.envelope is not None:
                supply_records.append(
                    _record_supply(
                        decision=supply.decision,
                        envelope=supply.envelope,
                        reason=supply.reason,
                        metadata=supply.metadata,
                        invalid_reason="halt_with_envelope",
                    )
                )
                return _stream_result(
                    graph=graph,
                    records=records,
                    supply_records=supply_records,
                    stop_reason="provider_invalid",
                )
            if _is_blank_reason(supply.reason):
                supply_records.append(
                    _record_supply(
                        decision=supply.decision,
                        envelope=supply.envelope,
                        reason=supply.reason,
                        metadata=supply.metadata,
                        invalid_reason="halt_missing_reason",
                    )
                )
                return _stream_result(
                    graph=graph,
                    records=records,
                    supply_records=supply_records,
                    stop_reason="provider_invalid",
                )

            supply_records.append(
                _record_supply(
                    decision=supply.decision,
                    envelope=None,
                    reason=supply.reason,
                    metadata=supply.metadata,
                )
            )
            return _stream_result(
                graph=graph,
                records=records,
                supply_records=supply_records,
                stop_reason="provider_halt",
            )

        supply_records.append(
            _record_supply(
                decision=supply.decision,
                envelope=supply.envelope,
                reason=supply.reason,
                metadata=supply.metadata,
            )
        )
        step_result = await run_current_mapped_step(supply.envelope, graph, runner)
        records.append(step_result.record)

        if step_result.record.ran is False:
            return _stream_result(
                graph=step_result.graph,
                records=records,
                supply_records=supply_records,
                stop_reason="execution_refused",
            )

        if step_result.graph is graph:
            return _stream_result(
                graph=step_result.graph,
                records=records,
                supply_records=supply_records,
                stop_reason="graph_not_advanced",
            )

        graph = step_result.graph
```

- [ ] **Step 2: Run the stream unit tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_stream.py -q
```

Expected: PASS for every test in `test_plan_graph_current_step_stream.py`.

- [ ] **Step 3: Commit the stream module**

```powershell
git add -- mcp_server\src\rook\agent\plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_stream.py
git commit -m "feat(lm4s): add current-step stream runner"
```

---

## Task 3: Chain Stream Guard

**Files:**
- Create: `mcp_server/tests/test_plan_graph_current_step_stream_chain.py`
- Test: `mcp_server/src/rook/agent/plan_graph_current_step_stream.py`

- [ ] **Step 1: Write the real chain guard**

Create `mcp_server/tests/test_plan_graph_current_step_stream_chain.py` with this content:

```python
"""LM4S chain guard for caller-fed current-step streams.

The provider prepares current-step artifacts outside LM4S. LM4S records supply
decisions, delegates to LM4R, threads the graph, and halts before becoming a repair
runner or scheduler.
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
        "create_script": ProducerStep("create_script"),
        "verify_create": VerifierStep(
            verifier_node_id="verify_create",
            source_node_id="create_script",
            expected_outcome="needs_repair",
        ),
        "repair_same_component": ProducerStep(
            node_id="repair_same_component", expectation=None
        ),
    }


class _CreateRunner:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append((graph, node_id))
        assert node_id == "create_script"
        applied = apply_producer_result(graph, node_id, _wrapped_failure_create_raw())
        return LiveProducerResult(
            graph=applied.graph,
            applied=True,
            node_id=node_id,
            tool_name="gh_create_csharp_script",
            outcome_status=applied.outcome_status,
            reason=applied.reason,
        )


@pytest.mark.asyncio
async def test_current_step_stream_threads_create_verify_then_provider_halts():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)
    step_map = _chain_step_map()
    runner = _CreateRunner()
    provider_calls = []

    def provider(current_graph, records, supply_records):
        provider_calls.append((current_graph, records, supply_records))
        if len(provider_calls) == 3:
            proposal = propose_next_node(current_graph)
            assert proposal.selected_node_id == "repair_same_component"
            return EnvelopeSupplyResult(
                "HALT", None, "chain_guard_stop_before_repair"
            )

        proposal = propose_next_node(current_graph)
        mapping = map_accepted_proposal_to_step(proposal, current_graph, step_map)
        assert mapping.mapped is True
        return EnvelopeSupplyResult(
            "SUPPLY",
            CurrentStepEnvelope(mapping, {"provider_call": len(provider_calls)}),
            f"supplied {proposal.selected_node_id}",
        )

    result = await run_current_step_stream(
        graph, provider, max_steps=3, runner=runner
    )

    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 2
    assert len(result.records) == 2
    assert len(result.supply_records) == 3
    assert len(provider_calls) == 3
    assert len(runner.calls) == 1

    assert result.supply_records[0].decision == "SUPPLY"
    assert result.supply_records[0].envelope is not None
    assert result.supply_records[0].envelope.mapping is result.records[0].mapping
    assert result.records[0].ran is True
    assert result.records[0].execution_kind == "producer"
    assert result.records[0].producer_node_id == "create_script"
    assert result.records[0].producer_tool_name == "gh_create_csharp_script"

    assert result.supply_records[1].decision == "SUPPLY"
    assert result.supply_records[1].envelope is not None
    assert result.supply_records[1].envelope.mapping is result.records[1].mapping
    assert result.records[1].ran is True
    assert result.records[1].execution_kind == "verifier"
    assert result.records[1].verifier_node_id == "verify_create"
    assert result.records[1].verifier_source_node_id == "create_script"
    assert result.records[1].verifier_outcome_status == "needs_repair"

    assert result.supply_records[2].decision == "HALT"
    assert result.supply_records[2].envelope is None
    assert result.supply_records[2].reason == "chain_guard_stop_before_repair"

    final_proposal = propose_next_node(result.final_graph)
    assert final_proposal.selected_node_id == "repair_same_component"
    assert result.final_graph.nodes["done"].status == "pending"
    assert result.final_graph.nodes["done"].is_terminal is True
```

- [ ] **Step 2: Run the chain guard**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_stream_chain.py -q
```

Expected: PASS for `test_current_step_stream_threads_create_verify_then_provider_halts`.

- [ ] **Step 3: Run the new LM4S tests together**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_stream_chain.py -q
```

Expected: PASS for both LM4S test files.

- [ ] **Step 4: Commit the chain guard**

```powershell
git add -- mcp_server\tests\test_plan_graph_current_step_stream_chain.py
git commit -m "test(lm4s): guard caller-fed chain stream"
```

---

## Task 4: Focused Gate, Diff Review, PR

**Files:**
- Review: `mcp_server/src/rook/agent/plan_graph_current_step_stream.py`
- Review: `mcp_server/tests/test_plan_graph_current_step_stream.py`
- Review: `mcp_server/tests/test_plan_graph_current_step_stream_chain.py`

- [ ] **Step 1: Run the focused PlanGraph gate**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_selector.py `
  mcp_server\tests\test_plan_graph_selector_chain.py `
  mcp_server\tests\test_plan_graph_revalidation.py `
  mcp_server\tests\test_plan_graph_revalidation_chain.py `
  mcp_server\tests\test_plan_graph_step_mapping.py `
  mcp_server\tests\test_plan_graph_step_mapping_chain.py `
  mcp_server\tests\test_plan_graph_step_executor.py `
  mcp_server\tests\test_plan_graph_step_executor_chain.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py `
  mcp_server\tests\test_plan_graph_current_step_runner_chain.py `
  mcp_server\tests\test_plan_graph_current_step_stream.py `
  mcp_server\tests\test_plan_graph_current_step_stream_chain.py `
  -q
```

Expected: PASS for the focused LM4N-S gate. If a pre-existing unrelated test fails, capture the exact failing test and stop for review before changing unrelated files.

- [ ] **Step 2: Run whitespace check for the branch diff**

Run:

```powershell
git diff --check main..HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 3: Review production boundary mechanically**

Run:

```powershell
git diff --name-status main..HEAD
rg -n "propose_next_node|revalidate_proposal|map_accepted_proposal_to_step|execute_mapped_step|run_explicit_sequence|ProducerStep|VerifierStep|BindStep|base_agent|LiteLLM|should_continue|\\bok\\b|passed|completed" mcp_server\src\rook\agent\plan_graph_current_step_stream.py
```

Expected:
- Production diff includes exactly `mcp_server/src/rook/agent/plan_graph_current_step_stream.py`.
- The `rg` command returns no matches in the production module.
- Test and docs files may contain those names because providers and AST guards intentionally mention them outside LM4S production code.

- [ ] **Step 4: Commit any verification-only fixes**

If Task 4 surfaced a scoped LM4S fix, commit only LM4S files:

```powershell
git add -- mcp_server\src\rook\agent\plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_stream_chain.py
git commit -m "fix(lm4s): tighten current-step stream boundary"
```

If Task 4 made no file changes, do not create an empty commit.

- [ ] **Step 5: Create a draft PR and stop**

Run:

```powershell
git status --short
git push -u origin codex/lm4s-current-step-stream
gh pr create --draft --title "LM4S current-step stream runner" --body "Adds LM4S, a caller-fed current-step stream runner over LM4R with typed provider supply records, bounded max_steps, provider halt/invalid/error stop reasons, execution_refused and graph_not_advanced loop-safety stops, and focused PlanGraph coverage. Stops at PR for review."
```

Expected:
- Only unrelated local files remain unstaged if they were dirty before LM4S.
- PR is draft.
- Do not merge the PR.

---

## Self-Review Checklist

- Spec coverage:
  - Required positive `max_steps`: Task 1 tests `max_steps_invalid`, Task 2 implements it, Task 4 gates it.
  - Provider typed result and invalid taxonomy: Task 1 covers `supply_result_invalid`, `supply_missing_envelope`, `halt_with_envelope`, `halt_missing_reason`, and `unknown_supply_decision`; Task 2 implements validation before field reads.
  - Provider exceptions: Task 1 covers `provider_error`; Task 2 catches and records without retry.
  - Metadata copy semantics: Task 1 covers absent, copied, invalid, and copy failed; Task 2 uses deepcopy and records status.
  - Supply/current-step alignment: Task 1 covers one supplied step and provider context; Task 3 covers real chain alignment.
  - Stop reasons: Task 1 covers provider halt, invalid, error, execution refusal, graph not advanced, max reached, and invalid max; Task 3 covers real provider halt after two executions.
  - Boundary: Task 1 AST guard and Task 4 production scan block selectors, mappers, LM4Q direct execution, sequence runner, Step constructors, server, dispatcher, model, and judgment fields.
  - Chain guard: Task 3 drives create then verify, confirms repair is ready, and halts before repair.
- Placeholder scan:
  - Run a red-flag phrase search against this plan file using the exact forbidden
    patterns from the writing-plans skill.
  - Expected: no matches.
- Type consistency:
  - `EnvelopeSupplyResult`, `EnvelopeSupplyRecord`, `CurrentStepStreamResult`, `run_current_step_stream`, `SupplyInvalidReason`, and `StopReason` names match the spec.
  - `run_current_step_stream(initial_graph, envelope_source, *, max_steps, runner=None)` keeps `max_steps` required and keyword-only.
  - `steps_attempted == len(records)` in every result path.

---

## Execution Choice

Plan complete and saved to `docs/superpowers/plans/2026-06-25-lm4s-current-step-stream.md`. Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.
