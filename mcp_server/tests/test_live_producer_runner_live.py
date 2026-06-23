"""LM4G — clean-path live proof that the runner/eval harness records a real run.

ONE opt-in requires_rhino test: drive a clean producer node through
run_and_record_live_producer_node against the live gh_create_script tool and
assert the produced record + verdict. The broken/two-successes live seam is
already carried by LM4E; the exhaustive eval/not-applied matrix is in the pure
unit tests (test_plan_graph_live_runner.py).

Named OUTSIDE the test_plan_graph* glob so it stays out of the focused gate.

Run (from repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_producer_runner_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    run_and_record_live_producer_node,
)
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

NODE_ID = "create"


def _producer_graph() -> PlanGraph:
    node = PlanGraphNode(
        id=NODE_ID,
        intent="Create C# script via LM4G live runner",
        execution_ref="gh_create_script",
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: {
                "language": "csharp",
                "code": "A = Convert.ToDouble(R) * 2.0;",
                "pins_in": ["R:double"],
                "pins_out": ["A:double"],
                "name": "LM4GRunnerLive",
                "x": 360,
                "y": 980,
            },
        },
    )
    graph = PlanGraph(nodes={NODE_ID: node})
    node.status = "ready"
    return graph


async def test_run_and_record_clean_node_records_and_passes(fresh_document):
    agent = RookAgent(tool_executor=_mcp_tool_executor)
    expectation = LiveProducerExpectation(
        outcome_status="succeeded",
        node_status="succeeded",
        verified=True,
        artifact_status="usable",
    )

    record = await run_and_record_live_producer_node(
        agent, _producer_graph(), NODE_ID, expectation
    )

    # Assert the RECORD, not the implementation.
    assert record.evaluated is True
    assert record.passed is True
    assert record.mismatches == ()
    assert record.artifact_status == "usable"
    assert record.node_status == "succeeded"
    assert record.verified is True
    assert record.tool_name == "gh_create_script"
