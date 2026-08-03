from __future__ import annotations

import copy
import json
from dataclasses import replace
from typing import Any

import pytest

import rook.agent.semantic_graph_runner as runner
from rook.agent.semantic_graph import (
    SEMANTIC_GRAPH_SCHEMA,
    build_semantic_graph_response_schema,
    semantic_primitive_prompt_projection,
)
from rook.bridge import get_rhino_request_context, rhino_request_context
from rook.learning.plan_graph import PlanGraphEdge


_INTENT = "Create a small parametric Grasshopper definition."


def _slider(
    node_id: str = "control",
    *,
    label: str = "Value",
    minimum: int | float = 0,
    maximum: int | float = 10,
    initial: int | float = 5,
) -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": "number_slider",
        "parameters": {
            "label": label,
            "minimum": minimum,
            "maximum": maximum,
            "initial": initial,
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
async def test_valid_raw_graph_crosses_loader_and_compiler_before_snapshot() -> None:
    transport = _RecordingTransport(
        _raw_graph(
            nodes=[_slider(), _node("point", "construct_point")],
            edges=[_edge("control", "value", "point", "x")],
        )
    )
    tools = _ToolCalls()

    result = await runner.run_semantic_graph_transaction(
        _INTENT,
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=tools,
    )

    assert len(transport.calls) == 1
    assert tools.calls == [
        ("gh_snapshot", {"include_data": False, "max_preview_items": 0})
    ]
    assert result.terminal_stage == "snapshot"
    assert result.terminal_reason == "snapshot_dispatch_failed"


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
    assert graph.nodes["create_edit"].metadata == {
        "outcome_projection_role": "artifact_producer",
        "execution_params": request,
    }
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


_QUALIFIED_TYPES = {
    "e64c5fb1-845c-4ab1-8911-5f338516ba67": "Component_Series",
    "3581f42a-9592-4549-bd6b-1c0fc39d067b": "Component_ConstructPoint",
    "71b5b089-500a-4ea6-81c5-2f960441a0e8": "Component_Polyline",
    "717a1e25-a075-4530-bc80-d43ecc2500d9": "Component_SquareGrid",
}


def _valid_raw_graph() -> str:
    return _raw_graph(
        nodes=[_slider(), _node("point", "construct_point")],
        edges=[_edge("control", "value", "point", "x")],
    )


def _point_row_raw_graph() -> str:
    return _raw_graph(
        nodes=[
            _slider("start_control", label="Start", minimum=-10, initial=0),
            _slider("step_control", label="Step", minimum=-10, initial=1),
            _slider("count_control", label="Count", maximum=20, initial=8),
            _node("series_values", "series"),
            _node("points", "construct_point"),
            _node("path", "polyline"),
        ],
        edges=[
            _edge("start_control", "value", "series_values", "start"),
            _edge("step_control", "value", "series_values", "step"),
            _edge("count_control", "value", "series_values", "count"),
            _edge("series_values", "values", "points", "x"),
            _edge("points", "point", "path", "vertices"),
        ],
    )


def _square_grid_raw_graph() -> str:
    return _raw_graph(
        nodes=[
            _slider("cell_size", label="Cell Size", minimum=1, initial=5),
            _slider("x_extent", label="X Extent", minimum=1, maximum=20, initial=8),
            _slider("y_extent", label="Y Extent", minimum=1, maximum=20, initial=6),
            _node("grid", "square_grid"),
        ],
        edges=[
            _edge("cell_size", "value", "grid", "cell_size"),
            _edge("x_extent", "value", "grid", "extent_x"),
            _edge("y_extent", "value", "grid", "extent_y"),
        ],
    )


def _cyclic_point_row_raw_graph() -> str:
    return _raw_graph(
        nodes=[
            _slider("start_control", label="Start", minimum=-10, initial=0),
            _slider("step_control", label="Step", minimum=-10, initial=1),
            _slider("count_control", label="Count", maximum=20, initial=8),
            _node("series_values", "series"),
            _node("series_loop", "series"),
            _node("points", "construct_point"),
            _node("path", "polyline"),
        ],
        edges=[
            _edge("start_control", "value", "series_loop", "step"),
            _edge("step_control", "value", "series_values", "step"),
            _edge("count_control", "value", "series_values", "count"),
            _edge("series_values", "values", "series_loop", "start"),
            _edge("series_loop", "values", "series_values", "start"),
            _edge("series_values", "values", "points", "x"),
            _edge("points", "point", "path", "vertices"),
        ],
    )


def _mapped_flow(flow: str, temp_id_map: dict[str, str]) -> str:
    source, target = flow.split(">", 1)
    source_id, output = source.split(".", 1)
    target_id, input_pin = target.split(".", 1)
    return f"{temp_id_map[source_id]}.{output}>{temp_id_map[target_id]}.{input_pin}"


class _CausalSnapshotEditExecutor:
    def __init__(
        self,
        *,
        snapshot_response: object | None = None,
        snapshot_error: Exception | None = None,
        edit_error: Exception | None = None,
        edit_mutation: str | None = None,
    ) -> None:
        self.snapshot_response = snapshot_response
        self.snapshot_error = snapshot_error
        self.edit_error = edit_error
        self.edit_mutation = edit_mutation
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.contexts: list[dict[str, int | None]] = []
        self.returned_edit: dict[str, object] | None = None

    def __call__(self, name: str, params: dict[str, object]) -> object:
        self.calls.append((name, copy.deepcopy(params)))
        self.contexts.append(get_rhino_request_context())
        if len(self.calls) == 1:
            if name != "gh_snapshot":
                raise AssertionError("first call must be gh_snapshot")
            if params != {"include_data": False, "max_preview_items": 0}:
                raise AssertionError("snapshot request changed")
            if self.snapshot_error is not None:
                raise self.snapshot_error
            if self.snapshot_response is not None:
                return self.snapshot_response
            return {
                "success": True,
                "data": {
                    "version": "1.0.0",
                    "epoch": 11,
                    "components": [],
                    "flows": [],
                    "diagnostics": {"total": 0, "errors": 0, "warnings": 0},
                },
            }
        if len(self.calls) != 2 or name != "gh_edit":
            raise AssertionError("only one gh_snapshot followed by one gh_edit is allowed")
        if params.get("epoch") != 11:
            raise AssertionError("edit did not use the admitted snapshot epoch")
        if self.edit_error is not None:
            raise self.edit_error
        result = self._derive_edit_result(params)
        _mutate_edit_result(result, self.edit_mutation)
        self.returned_edit = result
        return result

    def _derive_edit_result(self, params: dict[str, object]) -> dict[str, object]:
        create = params.get("create")
        connect = params.get("connect")
        if type(create) is not list or type(connect) is not list:
            raise AssertionError("edit request lacks canonical create/connect arrays")
        temp_id_map: dict[str, str] = {}
        instance_guids: dict[str, str] = {}
        components: list[dict[str, object]] = []
        for index, raw_entry in enumerate(create, start=1):
            if type(raw_entry) is not dict:
                raise AssertionError("create entry must be a mapping")
            entry = raw_entry
            temp_id = entry.get("temp_id")
            if type(temp_id) is not str:
                raise AssertionError("create entry lacks temp_id")
            component_id = f"C{index}"
            temp_id_map[temp_id] = component_id
            instance_guids[temp_id] = f"00000000-0000-0000-0000-{index:012d}"
            component: dict[str, object] = {
                "id": component_id,
                "pos": copy.deepcopy(entry.get("pos")),
            }
            if "guid" in entry:
                guid = entry["guid"]
                if guid not in _QUALIFIED_TYPES:
                    raise AssertionError("unqualified component GUID")
                component.update(
                    {"type": _QUALIFIED_TYPES[guid], "componentGuid": guid}
                )
            elif entry.get("type") == "slider":
                component.update(
                    {
                        "type": "NumberSlider",
                        "value": {
                            "type": "slider",
                            "val": entry.get("value"),
                            "min": entry.get("min"),
                            "max": entry.get("max"),
                        },
                    }
                )
            else:
                raise AssertionError("unqualified create representation")
            components.append(component)
        flows = [_mapped_flow(flow, temp_id_map) for flow in connect]
        return {
            "success": True,
            "data": {
                "version": "1.0.0",
                "epoch": 12,
                "components": components,
                "flows": flows,
                "diagnostics": {
                    "total": len(components),
                    "errors": 0,
                    "warnings": 0,
                },
                "edit_summary": {
                    "created": len(create),
                    "deleted": 0,
                    "values_set": 0,
                    "connected": len(connect),
                    "disconnected": 0,
                    "errors": None,
                    "temp_id_map": temp_id_map,
                    "instance_guids": instance_guids,
                },
            },
        }


def _mutate_edit_result(result: dict[str, object], mutation: str | None) -> None:
    if mutation is None:
        return
    data = result["data"]
    assert type(data) is dict
    summary = data["edit_summary"]
    assert type(summary) is dict
    temp_id_map = summary["temp_id_map"]
    instance_guids = summary["instance_guids"]
    components = data["components"]
    flows = data["flows"]
    assert type(temp_id_map) is dict
    assert type(instance_guids) is dict
    assert type(components) is list
    assert type(flows) is list
    if mutation == "top_failure":
        result["success"] = False
    elif mutation == "stale_epoch":
        result["success"] = False
        data["error"] = "stale_epoch"
    elif mutation == "top_partial":
        result["partial_success"] = True
    elif mutation == "nested_partial":
        data["partial_success"] = True
    elif mutation == "edit_errors":
        summary["errors"] = ["sentinel edit error"]
    elif mutation == "shortfall_with_errors":
        summary["created"] = 0
        summary["errors"] = ["create shortfall"]
        result["success"] = False
        result["partial_success"] = True
        data["partial_success"] = True
    elif mutation == "temp_keys":
        temp_id_map.pop("T1")
    elif mutation == "guid_keys":
        instance_guids.pop("T1")
    elif mutation == "empty_c_id":
        temp_id_map["T1"] = ""
    elif mutation == "empty_instance_guid":
        instance_guids["T1"] = ""
    elif mutation == "duplicate_c_id":
        temp_id_map["T2"] = temp_id_map["T1"]
    elif mutation == "duplicate_instance_guid":
        instance_guids["T2"] = instance_guids["T1"]
    elif mutation == "missing_component":
        components.pop(0)
    elif mutation == "wrong_component_guid":
        regular = next(item for item in components if "componentGuid" in item)
        regular["componentGuid"] = "forged"
    elif mutation == "wrong_slider_type":
        slider = next(item for item in components if item.get("type") == "NumberSlider")
        slider["type"] = "Panel"
    elif mutation == "created_count":
        summary["created"] = 1
    elif mutation == "connected_count":
        summary["connected"] = 0
    elif mutation == "missing_wire":
        flows.clear()
    elif mutation == "extra_new_wire":
        flows.append("C2.O0>C1.I0")
    elif mutation == "preexisting_to_new":
        flows.append("C90.O0>C1.I0")
    elif mutation == "new_to_preexisting":
        flows.append("C1.O0>C90.I0")
    elif mutation == "malformed_incident_wire":
        flows.append("C1.not-a-flow")
    elif mutation == "malformed_target_endpoint":
        flows.append("C90.O0>C1")
    elif mutation == "malformed_source_endpoint":
        flows.append("C1>C90.I0")
    elif mutation == "unrelated_wire":
        flows.append("C90.O0>C91.I0")
    else:
        raise AssertionError(f"unknown test mutation: {mutation}")


async def _run_task4(
    executor: _CausalSnapshotEditExecutor,
) -> runner.SemanticGraphExecutionResult:
    return await runner.run_semantic_graph_transaction(
        _INTENT,
        planner_adapter=runner.SemanticGraphPlannerAdapter(
            _RecordingTransport(_valid_raw_graph())
        ),
        tool_executor=executor,
    )


@pytest.mark.asyncio
async def test_snapshot_exception_stops_before_edit_and_retains_request() -> None:
    executor = _CausalSnapshotEditExecutor(
        snapshot_error=TimeoutError("sentinel snapshot secret")
    )

    result = await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot"]
    assert result.terminal_stage == "snapshot"
    assert result.snapshot_request == {
        "include_data": False,
        "max_preview_items": 0,
    }
    assert result.snapshot_response is None
    assert "sentinel" not in repr(result)


@pytest.mark.parametrize(
    "snapshot_response",
    [
        [],
        {"success": False, "data": {"epoch": 11}},
        {"success": 1, "data": {"epoch": 11}},
        {"success": True},
        {"success": True, "data": {}},
        {"success": True, "data": {"epoch": True}},
        {"success": True, "data": {"epoch": 0}},
        {"success": True, "data": {"epoch": -1}},
        {"success": True, "data": {"epoch": 1.5}},
        {"success": True, "data": {"epoch": "11"}},
    ],
    ids=(
        "non_mapping",
        "failed",
        "truthy_non_bool",
        "missing_data",
        "missing_epoch",
        "bool_epoch",
        "zero_epoch",
        "negative_epoch",
        "float_epoch",
        "string_epoch",
    ),
)
@pytest.mark.asyncio
async def test_snapshot_contract_refuses_before_edit(snapshot_response: object) -> None:
    executor = _CausalSnapshotEditExecutor(snapshot_response=snapshot_response)

    result = await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot"]
    assert result.terminal_stage == "snapshot"
    assert result.snapshot_response is snapshot_response
    assert result.edit_request is None


@pytest.mark.asyncio
async def test_snapshot_and_edit_share_frozen_context_and_materialize_epoch_once() -> None:
    executor = _CausalSnapshotEditExecutor()

    with rhino_request_context(
        port=19101,
        process_id=4201,
        document_serial_number=73,
    ):
        result = await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert executor.contexts == [
        {"port": 19101, "process_id": 4201, "document_serial_number": 73},
        {"port": 19101, "process_id": 4201, "document_serial_number": 73},
    ]
    assert result.edit_request == executor.calls[1][1]
    assert result.edit_request["epoch"] == 11


@pytest.mark.asyncio
async def test_context_drift_raises_before_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = _CausalSnapshotEditExecutor()
    contexts = iter(
        (
            {"port": 19101, "process_id": 4201, "document_serial_number": 73},
            {"port": 19102, "process_id": 4201, "document_serial_number": 73},
        )
    )
    monkeypatch.setattr(runner, "get_rhino_request_context", lambda: next(contexts))

    with pytest.raises(RuntimeError, match="Rhino context changed"):
        await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot"]


@pytest.mark.parametrize(
    "mutation",
    (
        "top_failure",
        "stale_epoch",
        "top_partial",
        "nested_partial",
        "shortfall_with_errors",
    ),
)
@pytest.mark.asyncio
async def test_edit_contract_stops_without_retry_or_verification(mutation: str) -> None:
    executor = _CausalSnapshotEditExecutor(edit_mutation=mutation)

    result = await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "edit"
    assert result.edit_response is executor.returned_edit
    assert result.structural_correlation is None
    assert tuple(record.accepted_node_id for record in result.step_records) == (
        "create_edit",
    )


@pytest.mark.asyncio
async def test_nonempty_edit_errors_stop_even_when_edit_reports_success() -> None:
    executor = _CausalSnapshotEditExecutor(edit_mutation="edit_errors")

    result = await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "edit"
    assert result.structural_correlation is None


@pytest.mark.asyncio
async def test_edit_exception_stops_without_retry_and_without_response() -> None:
    executor = _CausalSnapshotEditExecutor(
        edit_error=TimeoutError("sentinel edit secret")
    )

    result = await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "edit"
    assert result.edit_response is None
    assert "sentinel" not in repr(result)


@pytest.mark.parametrize(
    "mutation",
    (
        "temp_keys",
        "guid_keys",
        "empty_c_id",
        "empty_instance_guid",
        "duplicate_c_id",
        "duplicate_instance_guid",
        "missing_component",
        "wrong_component_guid",
        "wrong_slider_type",
        "created_count",
        "connected_count",
    ),
)
@pytest.mark.asyncio
async def test_mapping_or_identity_disagreement_is_verification_stop(
    mutation: str,
) -> None:
    executor = _CausalSnapshotEditExecutor(edit_mutation=mutation)

    result = await _run_task4(executor)

    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "verification"
    assert result.structural_correlation is None
    assert tuple(record.accepted_node_id for record in result.step_records) == (
        "create_edit",
        "verify_edit",
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_wire",
        "extra_new_wire",
        "preexisting_to_new",
        "new_to_preexisting",
        "malformed_incident_wire",
    ),
)
@pytest.mark.asyncio
async def test_exact_incident_wiring_disagreement_is_verification_stop(
    mutation: str,
) -> None:
    result = await _run_task4(
        _CausalSnapshotEditExecutor(edit_mutation=mutation)
    )

    assert result.terminal_stage == "verification"
    assert result.structural_correlation is None


@pytest.mark.parametrize(
    "mutation",
    ("malformed_target_endpoint", "malformed_source_endpoint"),
)
@pytest.mark.asyncio
async def test_malformed_returned_flow_is_verification_stop(mutation: str) -> None:
    result = await _run_task4(
        _CausalSnapshotEditExecutor(edit_mutation=mutation)
    )

    assert result.terminal_stage == "verification"
    assert result.structural_correlation is None


@pytest.mark.asyncio
async def test_unrelated_preexisting_wire_is_ignored() -> None:
    result = await _run_task4(
        _CausalSnapshotEditExecutor(edit_mutation="unrelated_wire")
    )

    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"


@pytest.mark.asyncio
async def test_terminal_result_retains_native_records_and_exact_correlation() -> None:
    executor = _CausalSnapshotEditExecutor()

    result = await _run_task4(executor)

    assert result.terminal_stage == "terminal"
    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert tuple(record.accepted_node_id for record in result.step_records) == (
        "create_edit",
        "verify_edit",
    )
    assert tuple(record.execution_kind for record in result.step_records) == (
        "producer",
        "verifier",
    )
    assert tuple(record.decision for record in result.supply_records) == (
        "SUPPLY",
        "SUPPLY",
        "HALT",
    )
    assert result.supply_records[-1].reason == "terminal_node_selected:done"
    assert result.final_graph.nodes["create_edit"].status == "succeeded"
    assert result.final_graph.nodes["verify_edit"].status == "succeeded"
    assert result.final_graph.nodes["done"].status == "ready"
    assert result.structural_correlation == (
        ("control", "C1", "00000000-0000-0000-0000-000000000001"),
        ("point", "C2", "00000000-0000-0000-0000-000000000002"),
    )


@pytest.mark.asyncio
async def test_result_stage_presence_is_immediate_not_replayed() -> None:
    snapshot_result = await _run_task4(
        _CausalSnapshotEditExecutor(snapshot_response={"success": False})
    )
    edit_result = await _run_task4(
        _CausalSnapshotEditExecutor(edit_mutation="top_failure")
    )
    verification_result = await _run_task4(
        _CausalSnapshotEditExecutor(edit_mutation="temp_keys")
    )
    terminal_result = await _run_task4(_CausalSnapshotEditExecutor())

    with pytest.raises(ValueError):
        replace(snapshot_result, snapshot_request=None)
    with pytest.raises(ValueError):
        replace(edit_result, execution_graph=None)
    with pytest.raises(ValueError):
        replace(verification_result, edit_response=None)
    with pytest.raises(ValueError):
        replace(terminal_result, structural_correlation=None)


@pytest.mark.asyncio
async def test_point_row_witness_runs_complete_existing_transaction() -> None:
    raw = _point_row_raw_graph()
    transport = _RecordingTransport(raw)
    executor = _CausalSnapshotEditExecutor()

    result = await runner.run_semantic_graph_transaction(
        "Build a point row from three numeric controls.",
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=executor,
    )

    assert len(transport.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"
    assert result.planner_record.raw_response is raw
    assert result.edit_plan is not None
    assert result.edit_plan.semantic_node_to_temp_id == (
        ("count_control", "T1"),
        ("path", "T2"),
        ("points", "T3"),
        ("series_values", "T4"),
        ("start_control", "T5"),
        ("step_control", "T6"),
    )
    assert result.edit_plan.connect == (
        "T1.O0>T4.I2",
        "T3.O0>T2.I0",
        "T4.O0>T3.I0",
        "T5.O0>T4.I0",
        "T6.O0>T4.I1",
    )
    assert result.canonical_graph is not None
    canonical_nodes = {node.id: node for node in result.canonical_graph.nodes}
    assert tuple(canonical_nodes) == (
        "count_control",
        "path",
        "points",
        "series_values",
        "start_control",
        "step_control",
    )
    assert tuple(
        (node.id, node.primitive, dict(node.parameters))
        for node in result.canonical_graph.nodes
    ) == (
        (
            "count_control",
            "number_slider",
            {"initial": 8, "label": "Count", "maximum": 20, "minimum": 0},
        ),
        ("path", "polyline", {}),
        ("points", "construct_point", {}),
        ("series_values", "series", {}),
        (
            "start_control",
            "number_slider",
            {"initial": 0, "label": "Start", "maximum": 10, "minimum": -10},
        ),
        (
            "step_control",
            "number_slider",
            {"initial": 1, "label": "Step", "maximum": 10, "minimum": -10},
        ),
    )
    assert tuple(
        (edge.from_node, edge.from_pin, edge.to_node, edge.to_pin)
        for edge in result.canonical_graph.edges
    ) == (
        ("count_control", "value", "series_values", "count"),
        ("points", "point", "path", "vertices"),
        ("series_values", "values", "points", "x"),
        ("start_control", "value", "series_values", "start"),
        ("step_control", "value", "series_values", "step"),
    )
    assert "guid" not in raw and "temp_id" not in raw and "pos" not in raw
    assert result.edit_request is not None
    create = result.edit_request["create"]
    assert type(create) is list
    assert all(type(entry) is dict for entry in create)
    assert [entry["temp_id"] for entry in create] == [
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
    ]
    assert [entry.get("type", entry.get("guid")) for entry in create] == [
        "slider",
        "71b5b089-500a-4ea6-81c5-2f960441a0e8",
        "3581f42a-9592-4549-bd6b-1c0fc39d067b",
        "e64c5fb1-845c-4ab1-8911-5f338516ba67",
        "slider",
        "slider",
    ]
    assert all("pos" in entry for entry in create)
    assert result.structural_correlation == (
        ("count_control", "C1", "00000000-0000-0000-0000-000000000001"),
        ("path", "C2", "00000000-0000-0000-0000-000000000002"),
        ("points", "C3", "00000000-0000-0000-0000-000000000003"),
        ("series_values", "C4", "00000000-0000-0000-0000-000000000004"),
        ("start_control", "C5", "00000000-0000-0000-0000-000000000005"),
        ("step_control", "C6", "00000000-0000-0000-0000-000000000006"),
    )


@pytest.mark.asyncio
async def test_square_grid_witness_runs_complete_existing_transaction() -> None:
    raw = _square_grid_raw_graph()
    transport = _RecordingTransport(raw)
    executor = _CausalSnapshotEditExecutor()

    result = await runner.run_semantic_graph_transaction(
        "Build a square grid from size and extent controls.",
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=executor,
    )

    assert len(transport.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"
    assert result.edit_plan is not None
    assert result.edit_plan.semantic_node_to_temp_id == (
        ("cell_size", "T1"),
        ("grid", "T2"),
        ("x_extent", "T3"),
        ("y_extent", "T4"),
    )
    assert result.edit_plan.connect == (
        "T1.O0>T2.I1",
        "T3.O0>T2.I2",
        "T4.O0>T2.I3",
    )
    assert result.canonical_graph is not None
    assert tuple(
        (node.id, node.primitive, dict(node.parameters))
        for node in result.canonical_graph.nodes
    ) == (
        (
            "cell_size",
            "number_slider",
            {"initial": 5, "label": "Cell Size", "maximum": 10, "minimum": 1},
        ),
        ("grid", "square_grid", {}),
        (
            "x_extent",
            "number_slider",
            {"initial": 8, "label": "X Extent", "maximum": 20, "minimum": 1},
        ),
        (
            "y_extent",
            "number_slider",
            {"initial": 6, "label": "Y Extent", "maximum": 20, "minimum": 1},
        ),
    )
    assert tuple(
        (edge.from_node, edge.from_pin, edge.to_node, edge.to_pin)
        for edge in result.canonical_graph.edges
    ) == (
        ("cell_size", "value", "grid", "cell_size"),
        ("x_extent", "value", "grid", "extent_x"),
        ("y_extent", "value", "grid", "extent_y"),
    )
    assert result.edit_request is not None
    create = result.edit_request["create"]
    assert type(create) is list
    assert [entry.get("type", entry.get("guid")) for entry in create] == [
        "slider",
        "717a1e25-a075-4530-bc80-d43ecc2500d9",
        "slider",
        "slider",
    ]
    assert result.structural_correlation == (
        ("cell_size", "C1", "00000000-0000-0000-0000-000000000001"),
        ("grid", "C2", "00000000-0000-0000-0000-000000000002"),
        ("x_extent", "C3", "00000000-0000-0000-0000-000000000003"),
        ("y_extent", "C4", "00000000-0000-0000-0000-000000000004"),
    )


@pytest.mark.parametrize(
    "raw",
    (
        _valid_raw_graph(),
        _raw_graph(
            nodes=[_slider("size"), _node("grid", "square_grid")],
            edges=[_edge("size", "value", "grid", "cell_size")],
        ),
    ),
    ids=("slider_to_construct_point_x", "slider_to_square_grid_cell_size"),
)
@pytest.mark.asyncio
async def test_non_witness_recombination_runs_full_transaction(raw: str) -> None:
    transport = _RecordingTransport(raw)
    executor = _CausalSnapshotEditExecutor()

    result = await runner.run_semantic_graph_transaction(
        "Compose a small legal graph.",
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=executor,
    )

    assert len(transport.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "terminal"
    assert result.terminal_reason == "terminal_node_selected:done"


@pytest.mark.asyncio
async def test_cyclic_point_row_stops_at_graph_admission_without_gh_calls() -> None:
    transport = _RecordingTransport(_cyclic_point_row_raw_graph())
    executor = _CausalSnapshotEditExecutor()

    result = await runner.run_semantic_graph_transaction(
        "Build a point row with an invalid cyclic dependency.",
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=executor,
    )

    assert len(transport.calls) == 1
    assert executor.calls == []
    assert result.terminal_stage == "graph_admission"
    assert result.terminal_reason == "cycle_detected"


@pytest.mark.asyncio
async def test_square_grid_snapshot_failure_stops_before_edit() -> None:
    transport = _RecordingTransport(_square_grid_raw_graph())
    executor = _CausalSnapshotEditExecutor(
        snapshot_response={"success": False, "data": {"epoch": 11}}
    )

    result = await runner.run_semantic_graph_transaction(
        "Build a square grid from size and extent controls.",
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=executor,
    )

    assert len(transport.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_snapshot"]
    assert result.terminal_stage == "snapshot"


@pytest.mark.asyncio
async def test_point_row_partial_edit_stops_without_another_call() -> None:
    transport = _RecordingTransport(_point_row_raw_graph())
    executor = _CausalSnapshotEditExecutor(edit_mutation="top_partial")

    result = await runner.run_semantic_graph_transaction(
        "Build a point row from three numeric controls.",
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=executor,
    )

    assert len(transport.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "edit"


@pytest.mark.asyncio
async def test_square_grid_extra_new_to_preexisting_wire_stops_verification() -> None:
    transport = _RecordingTransport(_square_grid_raw_graph())
    executor = _CausalSnapshotEditExecutor(edit_mutation="new_to_preexisting")

    result = await runner.run_semantic_graph_transaction(
        "Build a square grid from size and extent controls.",
        planner_adapter=runner.SemanticGraphPlannerAdapter(transport),
        tool_executor=executor,
    )

    assert len(transport.calls) == 1
    assert [name for name, _ in executor.calls] == ["gh_snapshot", "gh_edit"]
    assert result.terminal_stage == "verification"
