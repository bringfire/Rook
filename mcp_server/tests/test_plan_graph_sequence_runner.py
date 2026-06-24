"""LM4M unit tests for run_explicit_sequence -- the agent-layer runner that left-folds a
caller-authored ordered list of typed steps over a PlanGraph, stopping on first failure.

A _FakeRunner implements SupportsLiveProducerNode by applying a pre-seeded raw-result
dict through the REAL apply_producer_result (offline, deterministic, faithful to the live
projection). In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_runner import LiveProducerExpectation
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    VerifierStep,
    run_explicit_sequence,
)
from rook.learning.plan_graph import graph_status, initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4m-seq-guid"
_BASE_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}

_CREATE_EXPECT = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    tool_status="failed",
    verified=False,
    artifact_status="created_with_errors",
)


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


class _FakeRunner:
    """Offline SupportsLiveProducerNode: applies a pre-seeded raw-result dict (keyed by
    node_id) through the REAL apply_producer_result and wraps it as a LiveProducerResult.
    Deterministic + faithful: evidence/status come from the real reducer/projection path,
    so build_live_producer_record evaluates expectations exactly as live."""

    def __init__(self, raws: dict[str, dict]) -> None:
        self._raws = raws

    async def run_live_producer_node(self, graph, node_id):
        inner = apply_producer_result(graph, node_id, self._raws[node_id])
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name="fake_producer",
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


def _ready_template_graph():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)
    assert graph.nodes["create_script"].status == "ready"
    return graph


@pytest.mark.asyncio
async def test_happy_three_step_sequence():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        BindStep(
            "repair_same_component",
            _BASE_REPAIR_PARAMS,
            {"guid": ("repair_anchor", "component_guid")},
        ),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is True
    assert result.stopped_at is None
    assert result.remaining_steps == ()
    assert [s.kind for s in result.step_results] == ["producer", "verifier", "bind"]
    assert all(s.ok for s in result.step_results)
    # the bind step staged the memory-sourced guid onto the repair node.
    bind_outcome = result.step_results[2]
    assert bind_outcome.bind_result.binding.params["guid"] == _GUID
    assert (
        result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == _GUID
    )


@pytest.mark.asyncio
async def test_stop_at_verifier_mismatch():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        # create actually unlocks needs_repair; demand the wrong outcome -> mismatch.
        VerifierStep("verify_create", "create_script", expected_outcome="succeeded"),
        BindStep("repair_same_component", _BASE_REPAIR_PARAMS, {"guid": ("repair_anchor", "component_guid")}),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 1
    assert [s.kind for s in result.step_results] == ["producer", "verifier"]
    assert result.step_results[1].ok is False
    assert result.step_results[1].verifier_result.outcome_status == "needs_repair"
    # the bind step (index 2) never ran -> repair node has no execution_params.
    assert len(result.remaining_steps) == 1
    assert EXECUTION_PARAMS_KEY not in result.graph.nodes["repair_same_component"].metadata


@pytest.mark.asyncio
async def test_stop_at_bind_missing_fact():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        # path points at an absent memory fact -> binding_failed.
        BindStep("repair_same_component", _BASE_REPAIR_PARAMS, {"guid": ("absent_key",)}),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 2
    bind_outcome = result.step_results[2]
    assert bind_outcome.ok is False
    assert bind_outcome.bind_result.reason == "binding_failed"
    assert EXECUTION_PARAMS_KEY not in result.graph.nodes["repair_same_component"].metadata


@pytest.mark.asyncio
async def test_stop_at_producer_applied_but_expectation_fails():
    graph = _ready_template_graph()
    before = graph.nodes["create_script"].status
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    # create APPLIES (created_with_errors) but the expectation demands usable -> fail.
    bad_expect = LiveProducerExpectation(
        applied=True, node_status="succeeded", artifact_status="usable"
    )
    steps = [ProducerStep("create_script", expectation=bad_expect)]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 0
    assert result.step_results[0].ok is False
    # graph is the producer's ADVANCED graph, not the pre-step graph: a failed
    # expectation can still mean the graph mutated/advanced.
    assert before == "ready"
    assert result.graph is not graph  # a NEW graph (the dispatch advanced it)
    assert result.graph.nodes["create_script"].status == "succeeded"


@pytest.mark.asyncio
async def test_producer_not_applied_graph_unchanged():
    # create_script is PENDING (no initialize_graph) -> apply_producer_result not-applied.
    selection = select_template(_DESCRIPTOR)
    graph = selection.graph
    assert graph.nodes["create_script"].status == "pending"
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [ProducerStep("create_script")]  # no expectation -> ok = applied
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 0
    assert result.step_results[0].ok is False
    assert result.graph.nodes["create_script"].status == "pending"  # unchanged


@pytest.mark.asyncio
async def test_order_preserved_no_reorder():
    # A verifier placed BEFORE its source is ready not-applies and halts: the runner runs
    # the list in author order and never reorders to satisfy dependencies.
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 0
    assert result.step_results[0].kind == "verifier"
    assert result.step_results[0].ok is False
    assert result.step_results[0].verifier_result.applied is False
    # the producer step (index 1) never ran.
    assert len(result.remaining_steps) == 1
    assert result.graph.nodes["create_script"].status == "ready"


@pytest.mark.asyncio
async def test_completed_is_not_graph_complete():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is True  # sequence-completed
    assert graph_status(result.graph) != "complete"  # but graph is NOT complete
    assert result.graph.nodes["repair_same_component"].status == "ready"


@pytest.mark.asyncio
async def test_empty_sequence():
    graph = _ready_template_graph()
    runner = _FakeRunner({})
    result = await run_explicit_sequence(runner, graph, [])
    assert result.completed is True
    assert result.stopped_at is None
    assert result.step_results == ()
    assert result.remaining_steps == ()
    assert result.graph is graph  # runner never copies on its own


def test_sequence_runner_import_boundary():
    # The module folds existing seams; it must NOT import a selector (runnable_nodes), a
    # terminal builder (apply_outcome), the dispatcher, server, or base_agent.
    import rook.agent.plan_graph_sequence_runner as mod

    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            referenced.update((a.asname or a.name) for a in node.names)
    assert "rook.agent.base_agent" not in imported, imported
    assert not any(m.startswith("rook.server") for m in imported), imported
    assert not any("dispatch" in m for m in imported), imported
    assert "runnable_nodes" not in referenced, referenced
    assert "apply_outcome" not in referenced, referenced
