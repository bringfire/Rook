"""LM4Q live proof -- execute_mapped_step drives ONE mapped ProducerStep LIVE through a real
RookAgent runner, reaching the real DECLARED create producer (gh_create_csharp_script:v1
resolving live to gh_create_csharp_script -- NO producer override). Narrow: ProducerStep only,
no chain, no verifier/bind live, no expectation evaluation.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when Rhino/GH
unreachable. Run (repo root, Rhino + Grasshopper open with Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_live_step_executor_producer_live.py
Then restore knowledge/gh/operations_knowledge.json (live runs dirty it):
    git restore knowledge/gh/operations_knowledge.json
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_sequence_runner import ProducerStep
from rook.agent.plan_graph_step_executor import execute_mapped_step
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import initialize_graph
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


async def _ensure_gh_document() -> None:
    """Establish an ACTIVE Grasshopper document; skip (never silently ignore) when GH cannot
    provide one. The `_Grasshopper` window open is not sufficient, and fresh_document resets
    only the Rhino document."""
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_execute_mapped_producer_step_reaches_live_declared_create(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # P3 pin: assert the DECLARED ref BEFORE setting execution params (no override-style proof).
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["create_script"].status == "ready"  # initialize_graph promoted the root

    # set the create node's execution params (author-supplied valid C# body; omit 'language' --
    # the csharp alias forces it).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = 42.0;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4QStepExecutorLive",
        "x": 350,
        "y": 880,
    }

    # gate -> map the uniquely-ready create_script to a caller-authored ProducerStep.
    proposal = propose_next_node(graph)
    assert proposal.selected_node_id == "create_script"
    mapping = map_accepted_proposal_to_step(
        proposal, graph, {"create_script": ProducerStep("create_script")}
    )
    assert mapping.mapped is True

    # execute ONE mapped ProducerStep through a real RookAgent runner.
    agent = RookAgent(tool_executor=_mcp_tool_executor)
    result = await execute_mapped_step(mapping, graph, runner=agent)

    assert result.ran is True
    assert result.kind == "producer"
    assert result.producer_result is not None
    assert result.graph is result.producer_result.graph  # advanced graph threaded through
    # P3 pin: the declared :v1 ref resolved live to the real tool (no override).
    assert result.producer_result.tool_name == "gh_create_csharp_script"
