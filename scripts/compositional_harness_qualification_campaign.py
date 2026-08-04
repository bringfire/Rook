from __future__ import annotations

import sys
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = ROOT / "mcp_server"
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))


from rook.agent.local_worker_model_transport import (  # noqa: E402
    build_local_worker_response_schema,
)
from rook.agent.semantic_graph import (  # noqa: E402
    SemanticGraph,
    build_semantic_graph_response_schema,
    build_worker_leaf_semantic_graph_response_schema,
)
from rook.agent.semantic_graph_compiler import CanonicalSemanticGraph  # noqa: E402


_PLANNER_MAX_TOKENS = 8192
_WORKER_MAX_TOKENS = 1024
_MAX_RETRIES = 0
_TEMPERATURE = 0
_TIMEOUT_S = 120.0
_MAX_RESULT_BYTES = 4 * 1024 * 1024

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


_CASES = {
    "minimum_deterministic": _Case(
        case_id="minimum_deterministic",
        intent=(
            "Create a Grasshopper semantic graph containing exactly one "
            "Number Slider and no edges."
        ),
        worker_leaf=False,
        node_count=1,
        edge_count=0,
        maximum_depth=0,
        primitive_counts=(("number_slider", 1),),
        weak_component_count=None,
    ),
    "minimum_worker_leaf": _Case(
        case_id="minimum_worker_leaf",
        intent=(
            "Create a Grasshopper semantic graph containing exactly one C# "
            "script leaf and one Construct Point. The C# leaf goal is to "
            "produce one finite numeric value for a point coordinate. Use the "
            "exact [] -> A:double interface, connect A to one compatible "
            "Number input, and use exactly two nodes and one edge."
        ),
        worker_leaf=True,
        node_count=2,
        edge_count=1,
        maximum_depth=1,
        primitive_counts=(("construct_point", 1), ("csharp_script", 1)),
        weak_component_count=None,
    ),
    "medium_deterministic": _Case(
        case_id="medium_deterministic",
        intent=(
            "Create one connected Grasshopper semantic graph containing "
            "exactly three Number Sliders, one Series, one Construct Point, "
            "one Polyline, and one Square Grid. Use exactly seven nodes, six "
            "edges, and maximum topological depth three. Satisfy every "
            "compiler-required input and choose any wiring admitted by the "
            "listed pin contracts."
        ),
        worker_leaf=False,
        node_count=7,
        edge_count=6,
        maximum_depth=3,
        primitive_counts=(
            ("construct_point", 1),
            ("number_slider", 3),
            ("polyline", 1),
            ("series", 1),
            ("square_grid", 1),
        ),
        weak_component_count=1,
    ),
    "medium_worker_leaf": _Case(
        case_id="medium_worker_leaf",
        intent=(
            "Create one connected Grasshopper semantic graph containing "
            "exactly three Number Sliders, one Series, one Construct Point, "
            "one Polyline, one Square Grid, and one C# script leaf. The C# "
            "leaf goal is to produce one finite numeric value used by the "
            "deterministic graph. Use the exact [] -> A:double interface with "
            "no incoming edge and exactly one outgoing edge to a compatible "
            "Number input. Use exactly eight nodes, seven edges, and maximum "
            "topological depth three. Satisfy every compiler-required input "
            "and choose any other wiring admitted by the listed pin contracts."
        ),
        worker_leaf=True,
        node_count=8,
        edge_count=7,
        maximum_depth=3,
        primitive_counts=(
            ("construct_point", 1),
            ("csharp_script", 1),
            ("number_slider", 3),
            ("polyline", 1),
            ("series", 1),
            ("square_grid", 1),
        ),
        weak_component_count=1,
    ),
    "maximum_deterministic": _Case(
        case_id="maximum_deterministic",
        intent=(
            "Create one Grasshopper semantic DAG containing exactly six "
            "Number Sliders, three Series components, four Construct Points, "
            "two Square Grids, and one Polyline. Use exactly sixteen nodes, "
            "twenty-four edges, and maximum topological depth five. Satisfy "
            "every compiler-required input and choose any wiring admitted by "
            "the listed pin contracts."
        ),
        worker_leaf=False,
        node_count=16,
        edge_count=24,
        maximum_depth=5,
        primitive_counts=(
            ("construct_point", 4),
            ("number_slider", 6),
            ("polyline", 1),
            ("series", 3),
            ("square_grid", 2),
        ),
        weak_component_count=None,
    ),
    "maximum_worker_leaf": _Case(
        case_id="maximum_worker_leaf",
        intent=(
            "Create one Grasshopper semantic DAG containing exactly five "
            "Number Sliders, one C# script leaf, three Series components, "
            "four Construct Points, two Square Grids, and one Polyline. The "
            "C# leaf goal is to produce one finite numeric value used by the "
            "deterministic graph. Use the exact [] -> A:double interface with "
            "no incoming edge and exactly one outgoing edge to a compatible "
            "Number input. Use exactly sixteen nodes, twenty-four edges, and "
            "maximum topological depth five. Satisfy every compiler-required "
            "input and choose any other wiring admitted by the listed pin "
            "contracts."
        ),
        worker_leaf=True,
        node_count=16,
        edge_count=24,
        maximum_depth=5,
        primitive_counts=(
            ("construct_point", 4),
            ("csharp_script", 1),
            ("number_slider", 5),
            ("polyline", 1),
            ("series", 3),
            ("square_grid", 2),
        ),
        weak_component_count=None,
    ),
}


_FIXED_ROWS = {
    "stage_a.minimum_deterministic": _Row(
        "stage_a.minimum_deterministic", "A", "minimum_deterministic",
        _OPUS, None, "none", "fake",
    ),
    "stage_a.minimum_worker_leaf": _Row(
        "stage_a.minimum_worker_leaf", "A", "minimum_worker_leaf",
        _OPUS, _QWEN_CODER, "model", "fake",
    ),
    "stage_a.medium_deterministic": _Row(
        "stage_a.medium_deterministic", "A", "medium_deterministic",
        _OPUS, None, "none", "fake",
    ),
    "stage_a.medium_worker_leaf": _Row(
        "stage_a.medium_worker_leaf", "A", "medium_worker_leaf",
        _OPUS, _QWEN_CODER, "model", "fake",
    ),
    "stage_a.maximum_deterministic": _Row(
        "stage_a.maximum_deterministic", "A", "maximum_deterministic",
        _OPUS, None, "none", "fake",
    ),
    "stage_a.maximum_worker_leaf": _Row(
        "stage_a.maximum_worker_leaf", "A", "maximum_worker_leaf",
        _OPUS, _QWEN_CODER, "model", "fake",
    ),
    "stage_b.qwen36.medium_deterministic": _Row(
        "stage_b.qwen36.medium_deterministic", "B", "medium_deterministic",
        _QWEN36, None, "none", "fake",
    ),
    "stage_b.qwen36.medium_worker_leaf": _Row(
        "stage_b.qwen36.medium_worker_leaf", "B", "medium_worker_leaf",
        _QWEN36, None, "fake", "fake",
    ),
    "stage_b.gpt_oss.medium_deterministic": _Row(
        "stage_b.gpt_oss.medium_deterministic", "B", "medium_deterministic",
        _GPT_OSS, None, "none", "fake",
    ),
    "stage_b.gpt_oss.medium_worker_leaf": _Row(
        "stage_b.gpt_oss.medium_worker_leaf", "B", "medium_worker_leaf",
        _GPT_OSS, None, "fake", "fake",
    ),
    "stage_b.qwen14.medium_deterministic": _Row(
        "stage_b.qwen14.medium_deterministic", "B", "medium_deterministic",
        _QWEN14, None, "none", "fake",
    ),
    "stage_b.qwen14.medium_worker_leaf": _Row(
        "stage_b.qwen14.medium_worker_leaf", "B", "medium_worker_leaf",
        _QWEN14, None, "fake", "fake",
    ),
    "stage_c.qwen_coder": _Row(
        "stage_c.qwen_coder", "C", "medium_worker_leaf",
        None, _QWEN_CODER, "model", "fake",
    ),
    "stage_c.north_mini": _Row(
        "stage_c.north_mini", "C", "medium_worker_leaf",
        None, _NORTH_MINI, "model", "fake",
    ),
    "stage_c.gemma4": _Row(
        "stage_c.gemma4", "C", "medium_worker_leaf",
        None, _GEMMA4, "model", "fake",
    ),
}


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
