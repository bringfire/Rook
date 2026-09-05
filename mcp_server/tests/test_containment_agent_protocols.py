from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.agent.base_agent import RookAgent  # noqa: E402
from rook.agent.config import AgentConfig  # noqa: E402
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, apply_live_producer_node  # noqa: E402
from rook.learning.plan_graph import PlanGraph, PlanGraphNode  # noqa: E402
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY  # noqa: E402
from rook.tool_lifecycle import CONTAINED_TOOLS  # noqa: E402


CONTAINED = [entry.name for entry in CONTAINED_TOOLS]


def _call(name: str, arguments: str = "{invalid-json"):
    return SimpleNamespace(
        id="denied-call",
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _response(*calls, content=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            role="assistant", content=content, tool_calls=list(calls)
        ))],
        usage=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CONTAINED)
async def test_rook_agent_internal_execution_denies_without_executor(name: str) -> None:
    calls = []

    async def executor(*args):
        calls.append(args)
        return {"success": True}

    agent = RookAgent(
        config=AgentConfig(knowledge_injection=False, observation_recording=False),
        tool_executor=executor,
    )
    result = await agent._execute_tool(name, {"must_not": "dispatch"})
    assert result["code"] == "legacy_semantic_tool_contained"
    assert result["tool"] == name
    assert calls == []


@pytest.mark.asyncio
async def test_rook_agent_model_loop_records_denial_without_decoding_and_continues(monkeypatch) -> None:
    executor_calls = []
    agent = RookAgent(
        config=AgentConfig(
            max_turns=3,
            knowledge_injection=False,
            observation_recording=False,
            tool_surface_adaptation=False,
        ),
        tool_executor=lambda *args: executor_calls.append(args),
    )
    responses = [_response(_call("gh_execute_intent")), _response(content="continued")]

    async def model(_context):
        return responses.pop(0)

    agent._call_model = model
    agent._track_usage = lambda _response: None
    await agent.prompt("test containment")

    protocol = [m for m in agent.messages if m.get("tool_call_id") == "denied-call"]
    assert len(protocol) == 1
    assert json.loads(protocol[0]["content"])["code"] == "legacy_semantic_tool_contained"
    assert executor_calls == []
    assert any(m.get("content") == "continued" for m in agent.messages)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CONTAINED)
async def test_plan_graph_denies_before_params_or_dispatch(name: str) -> None:
    node = PlanGraphNode(
        id="producer",
        intent="contained",
        execution_ref=f"{name}:v1",
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: {"must_not": "copy"},
        },
    )
    node.status = "ready"
    graph = PlanGraph(nodes={"producer": node})
    calls = []

    async def dispatch(*args):
        calls.append(args)
        return {"success": True}

    result = await apply_live_producer_node(graph, "producer", dispatch)
    assert result.applied is False
    assert result.reason == "tool_lifecycle_denied"
    assert result.graph is graph
    assert calls == []


@pytest.mark.asyncio
async def test_transport_wrapper_tombstones_missing_schema_before_sdk_validation(
    monkeypatch,
) -> None:
    from mcp import types as mcp_types
    from rook import server

    dispatch = AsyncMock()
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)

    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(
            name="gh_execute_intent",
            arguments={"malformed": object()},
        )
    )
    result = await handler(request)
    text = result.root.content[0].text
    assert text == (
        'Error: {\n  "code": "legacy_semantic_tool_contained",\n'
        '  "tool": "gh_execute_intent",\n  "verified": false,\n'
        '  "retryable": false,\n  "disposition": "retired",\n'
        '  "recovery": "Rediscover the current tool surface; use explicit '
        'Grasshopper inspection, editing, solve, error, and output-verification tools."\n}'
    )
    direct_payload = json.loads(text.removeprefix("Error: "))
    assert direct_payload["tool"] == "gh_execute_intent"
    assert result.root.structuredContent == {
        "success": False,
        "data": direct_payload,
    }
    assert result.root.isError is True

    progressive = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(
            name="rook_tools_call",
            arguments={"name": "gh_replay_recipe", "arguments": "not-an-object"},
        )
    )
    nested_result = await handler(progressive)
    nested_text = nested_result.root.content[0].text
    assert nested_text == (
        'Error: {\n  "code": "legacy_semantic_tool_contained",\n'
        '  "tool": "gh_replay_recipe",\n  "verified": false,\n'
        '  "retryable": false,\n  "disposition": "suspended",\n'
        '  "recovery": "Rediscover the current tool surface; inspect recipe '
        'data and use explicit mutation only after bounded validation."\n}'
    )
    nested_payload = json.loads(nested_text.removeprefix("Error: "))
    assert nested_payload["tool"] == "gh_replay_recipe"
    assert nested_result.root.structuredContent == {
        "success": False,
        "data": nested_payload,
    }
    assert nested_result.root.isError is True
    dispatch.assert_not_awaited()
