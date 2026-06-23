"""LM4E — opt-in live producer smoke (Stage 5).

Drives a REAL RookAgent wired to the production MCP executor through
`agent.run_live_producer_node` against the live `gh_create_script` tool, proving
the receipt travels the production executor seam and projects correctly by role.

Two independent ONE-NODE smokes:
  1. clean component  -> artifact_status "usable"          -> producer succeeded
  2. B = new Box()    -> success:False + "created_with_errors" (created but bad)
                      -> producer STILL succeeded / verified False  (the live
                         "two successes" seam; `needs_repair` here would mean the
                         producer projection was bypassed for conservative/
                         direct-task semantics)

Test-only: no production code is touched. `requires_rhino` keeps the module out
of normal CI by deselection; `fresh_document` makes it skip cleanly when Rhino is
unreachable.

Run (from repo root, with Rhino open and Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_base_agent_live_producer_live.py

IMPORTANT: the `fresh_document` fixture REPLACES the active Rhino document. Run in
a throwaway Rhino session.
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


NODE_ID = "create_script"
GH_CREATE_SCRIPT = "gh_create_script"


def _producer_graph(declared_params: dict) -> PlanGraph:
    """One ready `artifact_producer` node whose execution_ref is the real tool."""
    node = PlanGraphNode(
        id=NODE_ID,
        intent="Create C# script component via RookAgent live producer method",
        execution_ref=GH_CREATE_SCRIPT,
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: declared_params,
        },
    )
    graph = PlanGraph(nodes={NODE_ID: node})
    node.status = "ready"
    return graph


async def test_clean_component_live_producer_succeeds(fresh_document):
    """Live happy path: a valid C# component -> artifact_status 'usable' ->
    the producer node projects to succeeded / verified True."""
    declared_params = {
        "language": "csharp",
        "code": "A = Convert.ToDouble(R) * 2.0;",
        "pins_in": ["R:double"],
        "pins_out": ["A:double"],
        "name": "LM4ECleanLive",
        "x": 350,
        "y": 650,
    }
    graph = _producer_graph(declared_params)
    agent = RookAgent(tool_executor=_mcp_tool_executor)

    result = await agent.run_live_producer_node(graph, NODE_ID)

    assert result.applied is True, f"expected applied; got {result!r}"
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == GH_CREATE_SCRIPT
    # Applied path returns a fresh reducer graph (NOT identity).
    assert result.graph is not graph

    node = result.graph.nodes[NODE_ID]
    assert node.status == "succeeded"
    assert node.evidence is not None
    assert node.evidence.receipt is not None
    assert node.evidence.receipt["artifact_status"] == "usable"
    assert node.evidence.verified is True
    # Component identity captured on the repair anchor.
    assert node.evidence.repair_anchor is not None
    component_guid = node.evidence.repair_anchor.get("component_guid")
    assert isinstance(component_guid, str) and component_guid


async def test_broken_csharp_live_producer_two_successes_seam(fresh_document):
    """Live two-successes seam: `A = DefinitelyMissingSymbol;` is created but
    fails to compile (undefined-symbol error). The raw envelope is success:False,
    yet because the node is an artifact_producer the graph node still succeeds
    with verified False. A `needs_repair` landing here would mean the producer
    projection was bypassed for conservative/direct-task semantics.

    Body note: empirically confirmed on this RhinoCode build (8.33) to yield
    artifact_status == "created_with_errors". `B = new Box();` does NOT error on
    this build (it previews a Box), so it cannot serve as the seam body."""
    declared_params = {
        "language": "csharp",
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4EBrokenLive",
        "x": 350,
        "y": 760,
    }
    graph = _producer_graph(declared_params)
    agent = RookAgent(tool_executor=_mcp_tool_executor)

    result = await agent.run_live_producer_node(graph, NODE_ID)

    assert result.applied is True, f"expected applied; got {result!r}"
    assert result.reason is None
    assert result.graph is not graph

    node = result.graph.nodes[NODE_ID]
    assert node.evidence is not None
    # The tool failed functionally: the raw envelope was success:False.
    assert node.evidence.tool_status == "failed"
    assert node.evidence.receipt is not None
    assert node.evidence.receipt["artifact_status"] == "created_with_errors"
    # The producer hinge: created-but-bad -> succeeded / verified False.
    assert result.outcome_status == "succeeded"
    assert node.status == "succeeded"
    assert node.evidence.verified is False
