from __future__ import annotations

import asyncio

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"
PROBE_TOOL_NAME = "lm4d_live_producer_probe"
_DECLARED_PARAMS = {"language": "csharp", "code": "// noop", "component_name": "C"}


def _usable_raw() -> dict:
    return {
        "success": True,
        "data": {
            "verified": True,
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
                "repair_anchor": {"component_guid": COMPONENT_GUID},
            },
        },
    }


def _producer_graph(declared_params: dict) -> PlanGraph:
    node = PlanGraphNode(
        id="create_script",
        intent="Create C# script component via RookAgent live producer method",
        execution_ref=PROBE_TOOL_NAME,
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: declared_params,
        },
    )
    graph = PlanGraph(nodes={"create_script": node})
    node.status = "ready"
    return graph


class _SyncSpy:
    """A plain (non-async) ToolExecutor that records calls and returns a dict."""

    def __init__(self, raw: dict):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw

    def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        return self._raw


class _AsyncSpy:
    """An async ToolExecutor that records calls and returns a dict."""

    def __init__(self, raw: dict):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw

    async def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        return self._raw


def test_construction_does_not_invoke_executor():
    """RookAgent(tool_executor=spy) must not call the executor or build a
    dispatcher at construction -- the executor is only used when the method runs."""
    spy = _SyncSpy(_usable_raw())
    RookAgent(tool_executor=spy)
    assert spy.calls == []


def test_method_drives_node_via_sync_executor():
    spy = _SyncSpy(_usable_raw())
    agent = RookAgent(tool_executor=spy)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    # Applied path returns a fresh reducer graph (NOT identity).
    assert result.graph is not graph
    # Proves the method reached self._tool_executor with the node's tool + params.
    assert spy.calls == [(PROBE_TOOL_NAME, _DECLARED_PARAMS)]


def test_method_drives_node_via_async_executor():
    spy = _AsyncSpy(_usable_raw())
    agent = RookAgent(tool_executor=spy)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    assert result.graph is not graph
    assert spy.calls == [(PROBE_TOOL_NAME, _DECLARED_PARAMS)]


def test_method_raising_executor_is_dispatch_failed():
    def executor(name, params):
        raise RuntimeError("transport down")

    agent = RookAgent(tool_executor=executor)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is False
    assert result.reason == "dispatch_failed"
    assert result.outcome_status is None
    assert result.tool_name == PROBE_TOOL_NAME
    # Not-applied -> the input graph object is returned unchanged.
    assert result.graph is graph
