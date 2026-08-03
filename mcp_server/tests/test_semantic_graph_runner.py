from __future__ import annotations

import copy
import json
from typing import Any

import pytest

import rook.agent.semantic_graph_runner as runner
from rook.agent.semantic_graph import (
    SEMANTIC_GRAPH_SCHEMA,
    build_semantic_graph_response_schema,
    semantic_primitive_prompt_projection,
)
from rook.learning.plan_graph import PlanGraphEdge


_INTENT = "Create a small parametric Grasshopper definition."


def _slider(node_id: str = "control") -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": "number_slider",
        "parameters": {
            "label": "Value",
            "minimum": 0,
            "maximum": 10,
            "initial": 5,
        },
    }


def _node(node_id: str, primitive: str) -> dict[str, object]:
    return {"id": node_id, "primitive": primitive, "parameters": {}}


def _edge(
    from_node: str,
    from_pin: str,
    to_node: str,
    to_pin: str,
) -> dict[str, str]:
    return {
        "from_node": from_node,
        "from_pin": from_pin,
        "to_node": to_node,
        "to_pin": to_pin,
    }


def _raw_graph(
    nodes: list[dict[str, object]] | None = None,
    edges: list[dict[str, str]] | None = None,
) -> str:
    return json.dumps(
        {
            "schema": SEMANTIC_GRAPH_SCHEMA,
            "nodes": [_slider()] if nodes is None else nodes,
            "edges": [] if edges is None else edges,
        },
        separators=(",", ":"),
    )


class _RecordingTransport:
    def __init__(
        self,
        response: object = None,
        *,
        error: Exception | None = None,
        mutate_request: bool = False,
    ) -> None:
        self.response = _raw_graph() if response is None else response
        self.error = error
        self.mutate_request = mutate_request
        self.calls: list[dict[str, object]] = []
        self.observed: list[dict[str, object]] = []

    def send(self, prompt_artifact: dict[str, object]) -> str:
        self.calls.append(prompt_artifact)
        self.observed.append(copy.deepcopy(prompt_artifact))
        if self.mutate_request:
            prompt_artifact["messages"][0]["content"] = "mutated"
        if self.error is not None:
            raise self.error
        return self.response  # type: ignore[return-value]


class _ToolCalls:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, tool_name: str, params: dict[str, object]) -> object:
        self.calls.append((tool_name, params))
        raise AssertionError("Task 3 must not reach a GH tool")


@pytest.mark.parametrize(
    ("intent", "error_type"),
    [
        (123, TypeError),
        (type("Intent", (str,), {})("valid"), TypeError),
        ("", ValueError),
        (" \t\r\n", ValueError),
        ("é" * 8193, ValueError),
        ("\ud800", ValueError),
    ],
    ids=("not_string", "string_subclass", "empty", "blank", "too_large", "not_utf8"),
)
def test_planner_refuses_invalid_intent_before_prompt_or_call(
    intent: object,
    error_type: type[Exception],
) -> None:
    transport = _RecordingTransport()
    adapter = runner.SemanticGraphPlannerAdapter(transport)

    with pytest.raises(error_type):
        adapter.produce(intent)  # type: ignore[arg-type]

    assert transport.calls == []


def test_planner_prompt_is_fresh_semantic_only_and_called_once() -> None:
    transport = _RecordingTransport(mutate_request=True)
    adapter = runner.SemanticGraphPlannerAdapter(transport)

    record = adapter.produce(_INTENT)

    assert len(transport.calls) == 1
    assert record.status == "response_received"
    assert record.raw_response == _raw_graph()
    assert record.failure_reason is None
    assert record.transport_error_type is None
    assert record.prompt_snapshot.user_content == json.dumps(
        {"user_intent": _INTENT},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    system_content = record.prompt_snapshot.system_content
    assert json.dumps(
        build_semantic_graph_response_schema(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ) in system_content
    assert json.dumps(
        semantic_primitive_prompt_projection(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ) in system_content

    serialized = json.dumps(transport.observed[0], sort_keys=True)
    for forbidden in (
        "e64c5fb1-845c-4ab1-8911-5f338516ba67",
        "3581f42a-9592-4549-bd6b-1c0fc39d067b",
        "71b5b089-500a-4ea6-81c5-2f960441a0e8",
        "717a1e25-a075-4530-bc80-d43ecc2500d9",
        "gh_optional",
        "lowering_kind",
        "component_guid",
        "pin_index",
        "layout",
        "epoch",
        '"T1"',
        '"C1"',
        "PlanGraph",
        "phyllotaxis",
        "solar",
        "knowledge",
        "Worker",
        "expected_graph",
    ):
        assert forbidden not in serialized

    rematerialized = record.prompt_snapshot.materialize()
    assert rematerialized == transport.observed[0]
    assert rematerialized is not transport.calls[0]
    assert rematerialized["messages"] is not transport.calls[0]["messages"]


def test_planner_retains_exact_raw_response_without_decoding() -> None:
    raw = '{"schema":"first","schema":"second"}'
    transport = _RecordingTransport(raw)

    record = runner.SemanticGraphPlannerAdapter(transport).produce(_INTENT)

    assert record.status == "response_received"
    assert record.raw_response is raw
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_planner_transport_failure_stops_before_tool_call() -> None:
    transport = _RecordingTransport(error=TimeoutError("sentinel secret"))
    tools = _ToolCalls()

    result = await runner.run_semantic_graph_transaction(
        _INTENT,
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=tools,
    )

    assert len(transport.calls) == 1
    assert tools.calls == []
    assert result.terminal_stage == "planner"
    assert result.terminal_reason == "transport_failed"
    assert result.planner_record.status == "transport_failed"
    assert result.planner_record.raw_response is None
    assert result.planner_record.transport_error_type == "TimeoutError"
    assert "sentinel" not in repr(result)
    assert result.canonical_graph is None
    assert result.edit_plan is None


@pytest.mark.asyncio
async def test_runner_requires_exact_adapter_before_any_capability_call() -> None:
    transport = _RecordingTransport()
    tools = _ToolCalls()

    class _SubstituteAdapter(runner.SemanticGraphPlannerAdapter):
        pass

    with pytest.raises(TypeError, match="exact SemanticGraphPlannerAdapter"):
        await runner.run_semantic_graph_transaction(
            _INTENT,
            planner_adapter=_SubstituteAdapter(transport),
            tool_executor=tools,
        )

    assert transport.calls == []
    assert tools.calls == []


@pytest.mark.parametrize(
    "raw_response",
    [
        '{"schema":"rook.gh_semantic_graph:v1","schema":"duplicate","nodes":[],"edges":[]}',
        _raw_graph() + " trailing",
        "[]",
        _raw_graph(nodes=[_node("bad", "unknown")]),
        _raw_graph(
            nodes=[_node("a", "series"), _node("b", "series")],
            edges=[
                _edge("a", "values", "b", "start"),
                _edge("b", "values", "a", "start"),
            ],
        ),
        _raw_graph(
            nodes=[_slider(), _node("point", "construct_point")],
            edges=[_edge("control", "value", "missing", "x")],
        ),
    ],
)
@pytest.mark.asyncio
async def test_graph_admission_stops_invalid_raw_response_before_tools(
    raw_response: str,
) -> None:
    transport = _RecordingTransport(raw_response)
    tools = _ToolCalls()

    result = await runner.run_semantic_graph_transaction(
        _INTENT,
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=tools,
    )

    assert len(transport.calls) == 1
    assert tools.calls == []
    assert result.terminal_stage == "graph_admission"
    assert result.planner_record.raw_response is raw_response
    assert result.canonical_graph is None
    assert result.edit_plan is None
    assert result.snapshot_request is None
    assert result.execution_graph is None


@pytest.mark.asyncio
async def test_runner_passes_retained_raw_response_unchanged_to_strict_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _raw_graph() + " trailing"
    observed: list[object] = []
    real_loader = runner.load_semantic_graph

    def _observing_loader(value: object):
        observed.append(value)
        return real_loader(value)  # type: ignore[arg-type]

    monkeypatch.setattr(runner, "load_semantic_graph", _observing_loader)
    tools = _ToolCalls()
    result = await runner.run_semantic_graph_transaction(
        _INTENT,
        planner_adapter=runner.SemanticGraphPlannerAdapter(
            _RecordingTransport(raw)
        ),
        tool_executor=tools,
    )

    assert observed == [raw]
    assert observed[0] is raw
    assert result.terminal_stage == "graph_admission"
    assert tools.calls == []


@pytest.mark.asyncio
async def test_valid_raw_graph_crosses_loader_and_compiler_before_execution_skeleton() -> None:
    transport = _RecordingTransport(
        _raw_graph(
            nodes=[_slider(), _node("point", "construct_point")],
            edges=[_edge("control", "value", "point", "x")],
        )
    )
    tools = _ToolCalls()

    with pytest.raises(NotImplementedError):
        await runner.run_semantic_graph_transaction(
            _INTENT,
            planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
            tool_executor=tools,
        )

    assert len(transport.calls) == 1
    assert tools.calls == []


def test_execution_graph_is_fixed_create_verify_done_and_copies_request() -> None:
    request: dict[str, object] = {
        "epoch": 7,
        "create": [
            {
                "temp_id": "T1",
                "type": "slider",
                "nick": "Value",
                "min": 0,
                "max": 10,
                "value": 5,
                "pos": [100, 100],
            }
        ],
        "connect": [],
    }
    original = copy.deepcopy(request)

    graph = runner._build_execution_graph(request)

    assert request == original
    assert tuple(graph.nodes) == ("create_edit", "verify_edit", "done")
    assert graph.nodes["create_edit"].status == "ready"
    assert graph.nodes["create_edit"].execution_ref == "gh_edit:v1"
    assert graph.nodes["create_edit"].metadata == {"execution_params": request}
    assert graph.nodes["create_edit"].metadata["execution_params"] is not request
    assert graph.nodes["verify_edit"].status == "pending"
    assert graph.nodes["verify_edit"].execution_ref is None
    assert graph.nodes["verify_edit"].metadata == {}
    assert graph.nodes["done"].status == "pending"
    assert graph.nodes["done"].execution_ref is None
    assert graph.nodes["done"].metadata == {}
    assert graph.nodes["done"].is_terminal is True
    assert graph.edges == [
        PlanGraphEdge("create_edit", "verify_edit", "requires"),
        PlanGraphEdge("verify_edit", "done", "requires"),
    ]

    graph.nodes["create_edit"].metadata["execution_params"]["create"][0][
        "pos"
    ][0] = 999
    assert request == original
