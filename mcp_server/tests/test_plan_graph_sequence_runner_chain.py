"""LM4M offline chain guard -- run_explicit_sequence drives the full 5-step sequence
(create -> verify_create -> bind -> repair -> verify_repair) with an offline _FakeRunner,
then the TEST applies the terminal `done` marker to reach graph_status == "complete".

HONEST SCOPE: producer steps are faked via apply_producer_result (raw-dict projection),
so this proves SEQUENCING + applier-mid-sequence + composition to the brink of complete,
NOT live dispatch. Live dispatch is the requires_rhino proof
(test_live_sequence_runner_chain_live.py). In the focused PlanGraph gate. Run from repo
root. Separate file from test_plan_graph_sequence_runner.py.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_runner import LiveProducerExpectation
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    VerifierStep,
    run_explicit_sequence,
)
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_templates import select_template


pytestmark = pytest.mark.asyncio

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4m-chain-guid"
_BASE_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}

_CREATE_EXPECT = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    tool_status="failed",
    verified=False,
    artifact_status="created_with_errors",
)
_REPAIR_EXPECT = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    verified=True,
    artifact_status="usable",
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


class _FakeRunner:
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


async def test_sequence_runner_drives_full_chain_then_terminal_to_complete():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    runner = _FakeRunner(
        {
            "create_script": _wrapped_failure_create_raw(),
            "repair_same_component": _unwrapped_success_repair_raw(),
        }
    )
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        BindStep(
            "repair_same_component",
            _BASE_REPAIR_PARAMS,
            {"guid": ("repair_anchor", "component_guid")},
        ),
        ProducerStep("repair_same_component", expectation=_REPAIR_EXPECT),
        VerifierStep("verify_repair", "repair_same_component", expected_outcome="succeeded"),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is True
    assert result.stopped_at is None
    assert [s.kind for s in result.step_results] == [
        "producer", "verifier", "bind", "producer", "verifier",
    ]
    assert all(s.ok for s in result.step_results)
    # the bind step staged the memory-sourced guid mid-sequence.
    assert result.step_results[2].bind_result.binding.params["guid"] == _GUID
    assert (
        result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == _GUID
    )

    # SEQUENCE-completed but graph not complete: done is ready, the test applies terminal.
    graph = result.graph
    assert graph.nodes["done"].status == "ready"
    assert graph_status(graph) != "complete"
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
