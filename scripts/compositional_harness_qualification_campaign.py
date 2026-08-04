from __future__ import annotations

import copy
import inspect
import json
import os
import subprocess
import sys
import uuid
from collections import Counter, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = ROOT / "mcp_server"
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))


from rook.agent.local_worker_model_transport import (  # noqa: E402
    LiteLLMWorkerTransport,
    build_local_worker_response_schema,
)
from rook.agent.semantic_graph import (  # noqa: E402
    SemanticGraph,
    build_semantic_graph_response_schema,
    build_worker_leaf_semantic_graph_response_schema,
)
from rook.agent.semantic_graph_compiler import CanonicalSemanticGraph  # noqa: E402
from rook.agent.semantic_graph_runner import (  # noqa: E402
    SemanticGraphPlannerAdapter,
    run_semantic_graph_transaction,
)
from rook.agent.semantic_graph_worker_leaf_runner import (  # noqa: E402
    run_semantic_graph_single_worker_leaf_transaction,
)


_PLANNER_MAX_TOKENS = 8192
_WORKER_MAX_TOKENS = 1024
_MAX_RETRIES = 0
_TEMPERATURE = 0
_TIMEOUT_S = 120.0
_MAX_RESULT_BYTES = 4 * 1024 * 1024
_FROZEN_FAKE_WORKER_CODE = "A = 1.0;"
_FAKE_LEAF_GUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

_PLANNER_PRIORITY = (
    "ollama_chat/qwen3.6:35b",
    "ollama_chat/gpt-oss:20b",
    "ollama_chat/qwen3:14b",
    "anthropic/claude-opus-4-6",
)
_WORKER_PRIORITY = (
    "ollama_chat/north-mini-code-1.0:q4_K_M",
    "ollama_chat/gemma4:12b-it-qat",
    "ollama_chat/qwen3-coder:30b-a3b-q4_K_M",
)


@dataclass(frozen=True, slots=True)
class _Case:
    case_id: str
    intent: str
    worker_leaf: bool
    node_count: int
    edge_count: int
    maximum_depth: int
    primitive_counts: tuple[tuple[str, int], ...]
    weak_component_count: int | None


@dataclass(frozen=True, slots=True)
class _Row:
    row_id: str
    stage: str
    case_id: str
    planner_model: str | None
    worker_model: str | None
    worker_mode: Literal["none", "fake", "model"]
    tool_mode: Literal["fake", "live"]


_OPUS = "anthropic/claude-opus-4-6"
_QWEN36 = "ollama_chat/qwen3.6:35b"
_GPT_OSS = "ollama_chat/gpt-oss:20b"
_QWEN14 = "ollama_chat/qwen3:14b"
_QWEN_CODER = "ollama_chat/qwen3-coder:30b-a3b-q4_K_M"
_NORTH_MINI = "ollama_chat/north-mini-code-1.0:q4_K_M"
_GEMMA4 = "ollama_chat/gemma4:12b-it-qat"


def _case(
    case_id: str, intent: str, worker_leaf: bool, node_count: int, edge_count: int,
    maximum_depth: int, primitive_counts: tuple[tuple[str, int], ...],
    weak_component_count: int | None = None,
) -> _Case:
    return _Case(case_id, intent, worker_leaf, node_count, edge_count, maximum_depth,
                 primitive_counts, weak_component_count)


_CASES = {case.case_id: case for case in (
    _case("minimum_deterministic", "Create a Grasshopper semantic graph containing exactly one Number Slider and no edges.", False, 1, 0, 0, (("number_slider", 1),)),
    _case("minimum_worker_leaf", "Create a Grasshopper semantic graph containing exactly one C# script leaf and one Construct Point. The C# leaf goal is to produce one finite numeric value for a point coordinate. Use the exact [] -> A:double interface, connect A to one compatible Number input, and use exactly two nodes and one edge.", True, 2, 1, 1, (("construct_point", 1), ("csharp_script", 1))),
    _case("medium_deterministic", "Create one connected Grasshopper semantic graph containing exactly three Number Sliders, one Series, one Construct Point, one Polyline, and one Square Grid. Use exactly seven nodes, six edges, and maximum topological depth three. Satisfy every compiler-required input and choose any wiring admitted by the listed pin contracts.", False, 7, 6, 3, (("construct_point", 1), ("number_slider", 3), ("polyline", 1), ("series", 1), ("square_grid", 1)), 1),
    _case("medium_worker_leaf", "Create one connected Grasshopper semantic graph containing exactly three Number Sliders, one Series, one Construct Point, one Polyline, one Square Grid, and one C# script leaf. The C# leaf goal is to produce one finite numeric value used by the deterministic graph. Use the exact [] -> A:double interface with no incoming edge and exactly one outgoing edge to a compatible Number input. Use exactly eight nodes, seven edges, and maximum topological depth three. Satisfy every compiler-required input and choose any other wiring admitted by the listed pin contracts.", True, 8, 7, 3, (("construct_point", 1), ("csharp_script", 1), ("number_slider", 3), ("polyline", 1), ("series", 1), ("square_grid", 1)), 1),
    _case("maximum_deterministic", "Create one Grasshopper semantic DAG containing exactly six Number Sliders, three Series components, four Construct Points, two Square Grids, and one Polyline. Use exactly sixteen nodes, twenty-four edges, and maximum topological depth five. Satisfy every compiler-required input and choose any wiring admitted by the listed pin contracts.", False, 16, 24, 5, (("construct_point", 4), ("number_slider", 6), ("polyline", 1), ("series", 3), ("square_grid", 2))),
    _case("maximum_worker_leaf", "Create one Grasshopper semantic DAG containing exactly five Number Sliders, one C# script leaf, three Series components, four Construct Points, two Square Grids, and one Polyline. The C# leaf goal is to produce one finite numeric value used by the deterministic graph. Use the exact [] -> A:double interface with no incoming edge and exactly one outgoing edge to a compatible Number input. Use exactly sixteen nodes, twenty-four edges, and maximum topological depth five. Satisfy every compiler-required input and choose any other wiring admitted by the listed pin contracts.", True, 16, 24, 5, (("construct_point", 4), ("csharp_script", 1), ("number_slider", 5), ("polyline", 1), ("series", 3), ("square_grid", 2))),
)}


_FIXED_ROWS = {row.row_id: row for row in (
    _Row("stage_a.minimum_deterministic", "A", "minimum_deterministic", _OPUS, None, "none", "fake"),
    _Row("stage_a.minimum_worker_leaf", "A", "minimum_worker_leaf", _OPUS, _QWEN_CODER, "model", "fake"),
    _Row("stage_a.medium_deterministic", "A", "medium_deterministic", _OPUS, None, "none", "fake"),
    _Row("stage_a.medium_worker_leaf", "A", "medium_worker_leaf", _OPUS, _QWEN_CODER, "model", "fake"),
    _Row("stage_a.maximum_deterministic", "A", "maximum_deterministic", _OPUS, None, "none", "fake"),
    _Row("stage_a.maximum_worker_leaf", "A", "maximum_worker_leaf", _OPUS, _QWEN_CODER, "model", "fake"),
    _Row("stage_b.qwen36.medium_deterministic", "B", "medium_deterministic", _QWEN36, None, "none", "fake"),
    _Row("stage_b.qwen36.medium_worker_leaf", "B", "medium_worker_leaf", _QWEN36, None, "fake", "fake"),
    _Row("stage_b.gpt_oss.medium_deterministic", "B", "medium_deterministic", _GPT_OSS, None, "none", "fake"),
    _Row("stage_b.gpt_oss.medium_worker_leaf", "B", "medium_worker_leaf", _GPT_OSS, None, "fake", "fake"),
    _Row("stage_b.qwen14.medium_deterministic", "B", "medium_deterministic", _QWEN14, None, "none", "fake"),
    _Row("stage_b.qwen14.medium_worker_leaf", "B", "medium_worker_leaf", _QWEN14, None, "fake", "fake"),
    _Row("stage_c.qwen_coder", "C", "medium_worker_leaf", None, _QWEN_CODER, "model", "fake"),
    _Row("stage_c.north_mini", "C", "medium_worker_leaf", None, _NORTH_MINI, "model", "fake"),
    _Row("stage_c.gemma4", "C", "medium_worker_leaf", None, _GEMMA4, "model", "fake"),
)}


def _structural_tier_attained(
    case: _Case,
    owned_graph: SemanticGraph | CanonicalSemanticGraph,
) -> bool:
    if type(case) is not _Case:
        raise TypeError("case must be the exact campaign case type")
    if type(owned_graph) not in (SemanticGraph, CanonicalSemanticGraph):
        raise TypeError("owned_graph must be an admitted or canonical semantic graph")

    nodes = owned_graph.nodes
    edges = owned_graph.edges
    if len(nodes) != case.node_count or len(edges) != case.edge_count:
        return False
    primitive_counts = tuple(sorted(Counter(node.primitive for node in nodes).items()))
    if primitive_counts != case.primitive_counts:
        return False
    if _maximum_depth(nodes, edges) != case.maximum_depth:
        return False

    leaf_ids = {node.id for node in nodes if node.primitive == "csharp_script"}
    if case.worker_leaf:
        if len(leaf_ids) != 1:
            return False
        leaf_id = next(iter(leaf_ids))
        if sum(edge.from_node == leaf_id for edge in edges) != 1:
            return False
        if any(edge.to_node == leaf_id for edge in edges):
            return False
    elif leaf_ids:
        return False

    return (
        case.weak_component_count is None
        or _weak_component_count(nodes, edges) == case.weak_component_count
    )


def _maximum_depth(nodes: tuple[object, ...], edges: tuple[object, ...]) -> int | None:
    outgoing = {node.id: [] for node in nodes}
    indegree = {node.id: 0 for node in nodes}
    for edge in edges:
        outgoing[edge.from_node].append(edge.to_node)
        indegree[edge.to_node] += 1
    depths = {node.id: 0 for node in nodes}
    queue = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
    visited = 0
    while queue:
        node_id = queue.popleft()
        visited += 1
        for target in outgoing[node_id]:
            depths[target] = max(depths[target], depths[node_id] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return max(depths.values()) if visited == len(nodes) else None


def _weak_component_count(nodes: tuple[object, ...], edges: tuple[object, ...]) -> int:
    neighbors = {node.id: set() for node in nodes}
    for edge in edges:
        neighbors[edge.from_node].add(edge.to_node)
        neighbors[edge.to_node].add(edge.from_node)
    remaining = set(neighbors)
    components = 0
    while remaining:
        components += 1
        queue = deque([remaining.pop()])
        while queue:
            current = queue.popleft()
            for neighbor in neighbors[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
    return components


def _planner_transport_kwargs(model: str, *, worker_leaf: bool) -> dict[str, Any]:
    if type(model) is not str or model not in (_OPUS, _QWEN36, _GPT_OSS, _QWEN14):
        raise ValueError("planner_model_not_scored")
    if type(worker_leaf) is not bool:
        raise TypeError("worker_leaf must be an exact boolean")
    schema = (
        build_worker_leaf_semantic_graph_response_schema()
        if worker_leaf
        else build_semantic_graph_response_schema()
    )
    generation_params: dict[str, Any] = {
        "temperature": _TEMPERATURE,
        "max_tokens": _PLANNER_MAX_TOKENS,
        "max_retries": _MAX_RETRIES,
    }
    structured_response_schema: dict[str, Any] | None = schema
    if model == _OPUS:
        generation_params["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": (
                    "rook_semantic_graph_worker_leaf"
                    if worker_leaf
                    else "rook_semantic_graph"
                ),
                "strict": True,
                "schema": schema,
            },
        }
        structured_response_schema = None
    return {
        "model": model,
        "generation_params": generation_params,
        "structured_response_schema": structured_response_schema,
        "timeout_s": _TIMEOUT_S,
    }


def _worker_transport_kwargs(model: str) -> dict[str, Any]:
    if type(model) is not str or model not in (_QWEN_CODER, _NORTH_MINI, _GEMMA4):
        raise ValueError("worker_model_not_scored")
    return {
        "model": model,
        "generation_params": {
            "temperature": _TEMPERATURE,
            "max_tokens": _WORKER_MAX_TOKENS,
            "max_retries": _MAX_RETRIES,
        },
        "structured_response_schema": build_local_worker_response_schema(),
        "timeout_s": _TIMEOUT_S,
    }


class _RecordingTransport:
    def __init__(self, delegate: object, role: str, model_call: bool) -> None:
        if not callable(getattr(delegate, "send", None)):
            raise TypeError("recorded transport delegate must provide send")
        self.delegate = delegate
        self.role = role
        self.model_call = model_call
        self.calls: list[dict[str, object]] = []
        self.responses: list[str] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        response = self.delegate.send(prompt_artifact)
        self.responses.append(response)
        return response


class _FakeWorkerTransport:
    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        return json.dumps(
            {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Draft the requested numeric body.",
                "input": {"code": _FROZEN_FAKE_WORKER_CODE},
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


class _CausalFakeTools:
    def __init__(self, fail_at: str | None = None) -> None:
        if fail_at is not None and fail_at not in {
            "gh_create_csharp_script", "gh_snapshot", "gh_edit", "gh_connect",
        }:
            raise ValueError("unknown fake failure boundary")
        self.fail_at = fail_at
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.responses: list[object] = []
        self._finished = False
        self._mode: str | None = None
        self._deterministic_guids: set[str] = set()

    def __call__(self, name: str, params: dict[str, object]) -> object:
        if self._finished or "port" in params:
            raise AssertionError("fake tool call refused")
        self.calls.append((name, copy.deepcopy(params)))
        call_index = len(self.calls)
        if call_index == 1 and name == "gh_create_csharp_script":
            self._mode = "worker_leaf"
            response = _fake_create(params)
        elif call_index == 1 and name == "gh_snapshot":
            self._mode = "deterministic"
            response = _snapshot_for_request(params, [])
        elif self._mode == "worker_leaf" and call_index == 2 and name == "gh_snapshot":
            response = _snapshot_for_request(params, [_fake_leaf_component()])
        elif (
            name == "gh_edit"
            and (
                (self._mode == "deterministic" and call_index == 2)
                or (self._mode == "worker_leaf" and call_index == 3)
            )
        ):
            existing = [] if self._mode == "deterministic" else [_fake_leaf_component()]
            response = _fake_edit(params, existing_components=existing)
            summary = response["data"]["edit_summary"]
            self._deterministic_guids = set(summary["instance_guids"].values())
            self._finished = self._mode == "deterministic"
        elif self._mode == "worker_leaf" and call_index == 4 and name == "gh_connect":
            response = _fake_connect(params, self._deterministic_guids)
            self._finished = True
        else:
            raise AssertionError("unexpected fake tool call order")
        if name == self.fail_at:
            response = {"success": False, "error": "injected_failure"}
            self._finished = True
        self.responses.append(copy.deepcopy(response))
        return response


def _snapshot_for_request(
    params: dict[str, object],
    components: list[dict[str, object]],
) -> dict[str, object]:
    if params != {"include_data": False, "max_preview_items": 0}:
        raise AssertionError("snapshot request changed")
    return {
        "success": True,
        "data": {
            "version": "1.0.0",
            "epoch": 11,
            "components": copy.deepcopy(components),
            "flows": [],
            "diagnostics": {
                "total": len(components),
                "errors": 0,
                "warnings": 0,
            },
        },
    }


def _fake_create(params: dict[str, object]) -> dict[str, object]:
    expected = {
        "pins_in": (),
        "pins_out": ("A:double",),
        "name": "RookMinimalInitialBodyHandoff",
        "x": 375,
        "y": 1080,
    }
    if {key: params.get(key) for key in expected} != expected:
        raise AssertionError("C# create contract changed")
    if type(params.get("code")) is not str or not params["code"].strip():
        raise AssertionError("C# create lacks Worker-authored code")
    return {
        "success": True,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": _FAKE_LEAF_GUID},
                "verification": {"status": "passed", "target_error_count": 0},
                "repair_anchor": {
                    "component_guid": _FAKE_LEAF_GUID,
                    "language": "csharp",
                    "target_errors": [],
                },
            }
        },
    }


def _fake_leaf_component() -> dict[str, object]:
    return {
        "id": "C1",
        "type": "CSharpScript",
        "outputs": [{"idx": 0, "name": "out"}, {"idx": 1, "name": "A"}],
    }


def _fake_connect(params: dict[str, object], target_guids: set[str]) -> dict[str, object]:
    if (
        params.get("sourceGuid") != _FAKE_LEAF_GUID
        or params.get("sourceIndex") != 1
        or params.get("targetGuid") not in target_guids
        or type(params.get("targetIndex")) is not int
    ):
        raise AssertionError("connect request is not receipt/correlation derived")
    return {
        "success": True,
        "data": {
            "connected": True,
            "source": {
                "guid": params["sourceGuid"],
                "param": "A",
                "index": params["sourceIndex"],
            },
            "target": {
                "guid": params["targetGuid"],
                "param": "target",
                "index": params["targetIndex"],
            },
        },
    }


def _fake_edit(
    params: dict[str, object],
    *,
    existing_components: list[dict[str, object]],
) -> dict[str, object]:
    if params.get("epoch") != 11:
        raise AssertionError("edit did not use snapshot epoch")
    create = params.get("create")
    connect = params.get("connect")
    if type(create) is not list or type(connect) is not list:
        raise AssertionError("edit request lacks create/connect lists")
    offset = len(existing_components)
    temp_id_map: dict[str, str] = {}
    instance_guids: dict[str, str] = {}
    components = copy.deepcopy(existing_components)
    for index, entry in enumerate(create, start=1):
        if type(entry) is not dict or type(entry.get("temp_id")) is not str:
            raise AssertionError("create instruction changed")
        temp_id = entry["temp_id"]
        component_id = f"C{offset + index}"
        instance_guid = f"00000000-0000-0000-0000-{offset + index:012d}"
        temp_id_map[temp_id] = component_id
        instance_guids[temp_id] = instance_guid
        component: dict[str, object] = {
            "id": component_id,
            "pos": copy.deepcopy(entry.get("pos")),
        }
        if "guid" in entry:
            component["componentGuid"] = entry["guid"]
        elif entry.get("type") == "slider":
            component["type"] = "NumberSlider"
            component["value"] = {
                "type": "slider",
                "val": entry.get("value"),
                "min": entry.get("min"),
                "max": entry.get("max"),
            }
        else:
            raise AssertionError("create representation changed")
        components.append(component)
    flows = [_map_fake_flow(flow, temp_id_map) for flow in connect]
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


def _map_fake_flow(flow: object, temp_id_map: dict[str, str]) -> str:
    if type(flow) is not str:
        raise AssertionError("flow must be a string")
    source, target = flow.split(">", 1)
    source_id, output = source.split(".", 1)
    target_id, input_pin = target.split(".", 1)
    return f"{temp_id_map[source_id]}.{output}>{temp_id_map[target_id]}.{input_pin}"


async def _run_row_once(
    row: _Row,
    *,
    planner_transport: object,
    worker_transport: object | None,
    tool_executor: Callable[[str, dict[str, object]], object],
) -> dict[str, object]:
    if type(row) is not _Row or row.case_id not in _CASES:
        raise TypeError("row must be an exact known campaign row")
    case = _CASES[row.case_id]
    if not case.worker_leaf and worker_transport is not None:
        raise TypeError("deterministic rows cannot receive a Worker transport")
    if case.worker_leaf and not callable(getattr(worker_transport, "send", None)):
        raise TypeError("Worker-leaf rows require a Worker transport")
    planner = _RecordingTransport(
        planner_transport,
        "planner",
        type(planner_transport) is LiteLLMWorkerTransport,
    )
    tool_records: list[dict[str, object]] = []

    async def recorded_tool(name: str, params: dict[str, object]) -> object:
        record: dict[str, object] = {
            "name": name,
            "request": copy.deepcopy(params),
            "response": None,
            "exception_type": None,
        }
        tool_records.append(record)
        try:
            response = tool_executor(name, params)
            if inspect.isawaitable(response):
                response = await response
        except Exception as exc:
            record["exception_type"] = type(exc).__name__
            raise
        record["response"] = copy.deepcopy(response)
        return response

    worker = None
    if case.worker_leaf:
        worker = _RecordingTransport(
            worker_transport,
            "worker",
            type(worker_transport) is LiteLLMWorkerTransport,
        )
        native_result = await run_semantic_graph_single_worker_leaf_transaction(
            case.intent,
            planner_adapter=SemanticGraphPlannerAdapter(planner),
            worker_transport=worker,
            tool_executor=recorded_tool,
        )
        loaded = native_result.graph_load_result
        graph = None if loaded is None or not loaded.admitted else loaded.graph
    else:
        native_result = await run_semantic_graph_transaction(
            case.intent,
            planner_adapter=SemanticGraphPlannerAdapter(planner),
            tool_executor=recorded_tool,
        )
        graph = native_result.canonical_graph
    call_counts = _call_counts(planner, worker, tool_records)
    return {
        "row": row,
        "case": case,
        "native_result": native_result,
        "planner_transport": planner,
        "worker_transport": worker,
        "tool_records": tool_records,
        "call_counts": call_counts,
        "structural_tier_attained": (
            False if graph is None else _structural_tier_attained(case, graph)
        ),
    }


def _call_counts(
    planner: _RecordingTransport,
    worker: _RecordingTransport | None,
    tool_records: list[dict[str, object]],
) -> dict[str, int]:
    names = Counter(record["name"] for record in tool_records)
    return {
        "planner_transport": len(planner.calls),
        "planner_model": len(planner.calls) if planner.model_call else 0,
        "worker_transport": 0 if worker is None else len(worker.calls),
        "worker_model": 0 if worker is None or not worker.model_call else len(worker.calls),
        "gh_create_csharp_script": names["gh_create_csharp_script"],
        "gh_snapshot": names["gh_snapshot"],
        "gh_edit": names["gh_edit"],
        "gh_connect": names["gh_connect"],
    }


def _json_value(value: object) -> object:
    if value is None or type(value) in (str, int, float, bool):
        return value
    if type(value) is bytes:
        return value.decode("utf-8")
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"value is not JSON-shaped: {type(value).__name__}")


def _project_graph(graph: object | None) -> object | None:
    if graph is None:
        return None
    return {
        "nodes": [
            {"id": node.id, "primitive": node.primitive,
             "parameters": {key: _json_value(value) for key, value in node.parameters}}
            for node in graph.nodes
        ],
        "edges": [
            {"from_node": edge.from_node, "from_pin": edge.from_pin,
             "to_node": edge.to_node, "to_pin": edge.to_pin}
            for edge in graph.edges
        ],
    }


def _project_edit_plan(plan: object | None) -> object | None:
    if plan is None:
        return None
    return {
        "canonical_graph": _project_graph(plan.canonical_graph),
        "create": [
            {"temp_id": item.temp_id,
             "fields": {key: _json_value(value) for key, value in item.fields}}
            for item in plan.create_instructions
        ],
        "connect": list(plan.connect),
        "semantic_node_to_temp_id": _json_value(plan.semantic_node_to_temp_id),
        "semantic_edge_to_flow": _json_value(plan.semantic_edge_to_flow),
    }


def _project_planner_record(record: object, transport: _RecordingTransport) -> dict[str, object]:
    return {
        "status": record.status,
        "failure_reason": record.failure_reason,
        "transport_error_type": record.transport_error_type,
        "prompt": copy.deepcopy(transport.calls[0]) if transport.calls else None,
        "raw_response": _json_value(record.raw_response),
    }


def _project_worker_handoff(result: object | None, transport: _RecordingTransport | None) -> object | None:
    if result is None:
        return None
    adapter = result.adapter_record
    worker = result.worker_record
    action = result.action_apply_result
    return {
        "terminal_stage": result.terminal_stage,
        "terminal_reason": result.terminal_reason,
        "prompt": None if transport is None or not transport.calls else copy.deepcopy(transport.calls[0]),
        "raw_response": None if transport is None or not transport.responses else transport.responses[0],
        "adapter": {"status": adapter.status, "failure_reason": adapter.failure_reason,
                    "raw_output_excerpt": adapter.raw_output_excerpt},
        "worker_record": None if worker is None else {
            "status": worker.status, "failure": worker.failure, "reason": worker.reason,
        },
        "action_apply": None if action is None else {
            "applied": action.applied, "node_id": action.node_id,
            "reason": action.reason, "params_sha256": action.params_sha256,
        },
    }


def _project_deterministic(result: object | None) -> object | None:
    if result is None:
        return None
    return {
        "terminal_stage": result.terminal_stage,
        "terminal_reason": result.terminal_reason,
        "canonical_graph": _project_graph(result.canonical_graph),
        "edit_plan": _project_edit_plan(result.edit_plan),
        "snapshot_request": _json_value(result.snapshot_request),
        "snapshot_response": _json_value(result.snapshot_response),
        "edit_request": _json_value(result.edit_request),
        "edit_response": _json_value(result.edit_response),
        "structural_correlation": _json_value(result.structural_correlation),
    }


def _project_worker_leaf(result: object, worker: _RecordingTransport | None) -> dict[str, object]:
    loaded = result.graph_load_result
    compiled = result.partition_compile_result
    partition = None if compiled is None else compiled.partition
    return {
        "graph_load": None if loaded is None else {
            "admitted": loaded.admitted, "failure": loaded.failure,
            "reason": loaded.reason, "graph": _project_graph(loaded.graph),
        },
        "partition_compile": None if compiled is None else {
            "admitted": compiled.admitted, "failure": compiled.failure,
            "reason": compiled.reason, "partition": _json_value(partition),
        },
        "worker_handoff": _project_worker_handoff(result.worker_handoff_result, worker),
        "deterministic_execution": _project_deterministic(result.deterministic_execution_result),
        "connect": None if result.connect_request is None else {
            "request": _json_value(result.connect_request),
            "response": _json_value(result.connect_response),
        },
    }


def _campaign_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()


def _project_run_result(capture: dict[str, object]) -> dict[str, object]:
    row = capture["row"]
    case = capture["case"]
    native = capture["native_result"]
    planner = capture["planner_transport"]
    worker = capture["worker_transport"]
    if case.worker_leaf:
        owned = _project_worker_leaf(native, worker)
        completed = native.completed
    else:
        owned = {
            "graph_load": None, "partition_compile": None, "worker_handoff": None,
            "deterministic_execution": _project_deterministic(native), "connect": None,
        }
        completed = (
            native.terminal_stage == "terminal"
            and native.terminal_reason == "terminal_node_selected:done"
        )
    return {
        "schema": "rook.compositional_harness_qualification_row:v1",
        "campaign_sha": _campaign_sha(), "row_id": row.row_id,
        "repetition": capture.get("repetition", 1), "stage": row.stage,
        "case_id": row.case_id, "tool_mode": row.tool_mode, "intent": case.intent,
        "planner_model": row.planner_model, "worker_model": row.worker_model,
        "generation_settings": {
            "planner": {"temperature": _TEMPERATURE, "max_tokens": _PLANNER_MAX_TOKENS,
                        "max_retries": _MAX_RETRIES, "timeout_s": _TIMEOUT_S},
            "worker": None if row.worker_mode == "none" else {
                "temperature": _TEMPERATURE, "max_tokens": _WORKER_MAX_TOKENS,
                "max_retries": _MAX_RETRIES, "timeout_s": _TIMEOUT_S,
            },
        },
        "provider_materialization": {
            "planner": "response_format" if row.planner_model == _OPUS else "structured_response_schema",
            "worker": None if row.worker_mode == "none" else (
                "frozen_fake" if row.worker_mode == "fake" else "structured_response_schema"
            ),
        },
        "planner": _project_planner_record(native.planner_record, planner),
        "worker_graph_load": owned["graph_load"],
        "worker_partition_compile": owned["partition_compile"],
        "worker_handoff": owned["worker_handoff"],
        "deterministic_execution": owned["deterministic_execution"],
        "connect": owned["connect"], "completed": completed,
        "call_counts": copy.deepcopy(capture["call_counts"]),
        "structural_tier_attained": capture["structural_tier_attained"],
        "transport_telemetry": {
            "planner": _json_value(getattr(planner.delegate, "last_call_info", None)),
            "worker": None if worker is None else _json_value(getattr(worker.delegate, "last_call_info", None)),
        },
        "tool_records": copy.deepcopy(capture["tool_records"]),
        "raised_exception_type": capture.get("raised_exception_type"),
    }


def _bounded_summary(
    payload: dict[str, object], result_path: Path | None,
    operator_status: str = "result_written",
) -> dict[str, object]:
    native = payload.get("deterministic_execution")
    native = native if type(native) is dict else {}
    return {
        "row_id": payload.get("row_id"), "stage": payload.get("stage"),
        "case_id": payload.get("case_id"), "operator_status": operator_status,
        "native_terminal_stage": native.get("terminal_stage"),
        "native_terminal_reason": native.get("terminal_reason"),
        "completed": payload.get("completed"),
        "structural_tier_attained": payload.get("structural_tier_attained"),
        "call_counts": copy.deepcopy(payload.get("call_counts")),
        "result_path": None if result_path is None else str(result_path),
    }


def _result_filename() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"compositional-harness-qualification-{stamp}-p{os.getpid()}-{uuid.uuid4().hex[:8]}.json"


def _write_local_result(payload: dict[str, object]) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if type(local_app_data) is not str or not local_app_data.strip():
        raise ValueError("LOCALAPPDATA must be an exact nonblank string")
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > _MAX_RESULT_BYTES:
        raise ValueError("result exceeds 4 MiB")
    directory = (Path(local_app_data) / "Rook" / "traces").resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = (directory / _result_filename()).resolve()
    stream = None
    close_attempted = False
    try:
        stream = open(path, "xb", buffering=0)
        if stream.write(encoded) != len(encoded):
            raise RuntimeError("short result write")
        stream.flush()
        close_attempted = True
        stream.close()
    except Exception:
        if stream is not None and not close_attempted:
            close_attempted = True
            try:
                stream.close()
            except Exception:
                pass
        raise
    return path
