from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import tiktoken

from rook.agent import semantic_graph, semantic_graph_compiler


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "compositional_harness_qualification_campaign.py"


def _load_campaign():
    spec = importlib.util.spec_from_file_location(
        "compositional_harness_qualification_campaign",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CAMPAIGN = _load_campaign()


def _slider(node_id: str) -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": "number_slider",
        "parameters": {
            "label": node_id,
            "minimum": 0,
            "maximum": 100,
            "initial": 2,
        },
    }


def _node(node_id: str, primitive: str) -> dict[str, object]:
    return {"id": node_id, "primitive": primitive, "parameters": {}}


def _leaf() -> dict[str, object]:
    return {
        "id": "code_leaf",
        "primitive": "csharp_script",
        "parameters": {
            "goal": "Produce one finite numeric value for the connected control input.",
            "interface": {
                "inputs": [],
                "outputs": [{"name": "A", "type": "double"}],
            },
        },
    }


def _edge(
    source: str,
    output: str,
    target: str,
    input_name: str,
) -> dict[str, str]:
    return {
        "from_node": source,
        "from_pin": output,
        "to_node": target,
        "to_pin": input_name,
    }


def _payload(
    nodes: list[dict[str, object]],
    edges: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "schema": semantic_graph.SEMANTIC_GRAPH_SCHEMA,
        "nodes": nodes,
        "edges": edges,
    }


def _medium_edges() -> list[dict[str, str]]:
    return [
        _edge("s1", "value", "series1", "start"),
        _edge("s2", "value", "series1", "step"),
        _edge("s3", "value", "series1", "count"),
        _edge("series1", "values", "p1", "x"),
        _edge("p1", "point", "poly1", "vertices"),
        _edge("s1", "value", "grid1", "cell_size"),
    ]


def _medium_nodes(*, worker_leaf: bool) -> list[dict[str, object]]:
    nodes = [
        _slider("s1"),
        _slider("s2"),
        _slider("s3"),
        _node("series1", "series"),
        _node("p1", "construct_point"),
        _node("poly1", "polyline"),
        _node("grid1", "square_grid"),
    ]
    return [_leaf(), *nodes] if worker_leaf else nodes


def _maximum_deterministic_edges() -> list[dict[str, str]]:
    return [
        _edge("s1", "value", "series1", "start"),
        _edge("s2", "value", "series1", "step"),
        _edge("s3", "value", "series1", "count"),
        _edge("series1", "values", "series2", "start"),
        _edge("s4", "value", "series2", "step"),
        _edge("s5", "value", "series2", "count"),
        _edge("series2", "values", "series3", "start"),
        _edge("s5", "value", "series3", "step"),
        _edge("s6", "value", "series3", "count"),
        _edge("series1", "values", "p1", "x"),
        _edge("s1", "value", "p1", "y"),
        _edge("s2", "value", "p1", "z"),
        _edge("series2", "values", "p2", "x"),
        _edge("s3", "value", "p2", "y"),
        _edge("s4", "value", "p2", "z"),
        _edge("series3", "values", "p3", "x"),
        _edge("s5", "value", "p3", "y"),
        _edge("s6", "value", "p3", "z"),
        _edge("series3", "values", "p4", "x"),
        _edge("s1", "value", "p4", "y"),
        _edge("s2", "value", "p4", "z"),
        _edge("s3", "value", "grid1", "cell_size"),
        _edge("s4", "value", "grid2", "cell_size"),
        _edge("p4", "point", "poly1", "vertices"),
    ]


def _maximum_worker_leaf_edges() -> list[dict[str, str]]:
    edges = _maximum_deterministic_edges()
    replacements = {
        ("s5", "series3", "step"): _edge("s4", "value", "series3", "step"),
        ("s6", "series3", "count"): _edge("s5", "value", "series3", "count"),
        ("s6", "p3", "z"): _edge("s1", "value", "p3", "z"),
        ("s2", "p4", "z"): _edge("code_leaf", "A", "p4", "z"),
    }
    return [
        replacements.get((edge["from_node"], edge["to_node"], edge["to_pin"]), edge)
        for edge in edges
    ]


def _maximum_nodes(*, worker_leaf: bool) -> list[dict[str, object]]:
    slider_count = 5 if worker_leaf else 6
    nodes = [
        *[_slider(f"s{index}") for index in range(1, slider_count + 1)],
        *[_node(f"series{index}", "series") for index in range(1, 4)],
        *[_node(f"p{index}", "construct_point") for index in range(1, 5)],
        _node("grid1", "square_grid"),
        _node("grid2", "square_grid"),
        _node("poly1", "polyline"),
    ]
    return [*nodes[:slider_count], _leaf(), *nodes[slider_count:]] if worker_leaf else nodes


def _reference_payloads() -> dict[str, dict[str, object]]:
    medium_edges = _medium_edges()
    return {
        "minimum_deterministic": _payload([_slider("s1")], []),
        "minimum_worker_leaf": _payload(
            [_leaf(), _node("p1", "construct_point")],
            [_edge("code_leaf", "A", "p1", "x")],
        ),
        "medium_deterministic": _payload(
            _medium_nodes(worker_leaf=False),
            medium_edges,
        ),
        "medium_worker_leaf": _payload(
            _medium_nodes(worker_leaf=True),
            [*medium_edges, _edge("code_leaf", "A", "p1", "y")],
        ),
        "maximum_deterministic": _payload(
            _maximum_nodes(worker_leaf=False),
            _maximum_deterministic_edges(),
        ),
        "maximum_worker_leaf": _payload(
            _maximum_nodes(worker_leaf=True),
            _maximum_worker_leaf_edges(),
        ),
    }


def _load(payload: dict[str, object]) -> semantic_graph.SemanticGraph:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    result = semantic_graph.load_semantic_graph(raw)
    assert result.admitted is True, result
    assert result.graph is not None
    return result.graph


def test_catalog_is_exact_and_has_fifteen_fixed_stage_a_to_c_rows() -> None:
    assert tuple(CAMPAIGN._CASES) == (
        "minimum_deterministic",
        "minimum_worker_leaf",
        "medium_deterministic",
        "medium_worker_leaf",
        "maximum_deterministic",
        "maximum_worker_leaf",
    )
    assert len(CAMPAIGN._FIXED_ROWS) == 15
    assert CAMPAIGN._PLANNER_PRIORITY == (
        "ollama_chat/qwen3.6:35b",
        "ollama_chat/gpt-oss:20b",
        "ollama_chat/qwen3:14b",
        "anthropic/claude-opus-4-6",
    )
    assert CAMPAIGN._WORKER_PRIORITY == (
        "ollama_chat/north-mini-code-1.0:q4_K_M",
        "ollama_chat/gemma4:12b-it-qat",
        "ollama_chat/qwen3-coder:30b-a3b-q4_K_M",
    )


def test_case_intents_are_exact() -> None:
    assert {case_id: case.intent for case_id, case in CAMPAIGN._CASES.items()} == {
        "minimum_deterministic": (
            "Create a Grasshopper semantic graph containing exactly one Number "
            "Slider and no edges."
        ),
        "minimum_worker_leaf": (
            "Create a Grasshopper semantic graph containing exactly one C# script "
            "leaf and one Construct Point. The C# leaf goal is to produce one "
            "finite numeric value for a point coordinate. Use the exact [] -> "
            "A:double interface, connect A to one compatible Number input, and "
            "use exactly two nodes and one edge."
        ),
        "medium_deterministic": (
            "Create one connected Grasshopper semantic graph containing exactly "
            "three Number Sliders, one Series, one Construct Point, one Polyline, "
            "and one Square Grid. Use exactly seven nodes, six edges, and maximum "
            "topological depth three. Satisfy every compiler-required input and "
            "choose any wiring admitted by the listed pin contracts."
        ),
        "medium_worker_leaf": (
            "Create one connected Grasshopper semantic graph containing exactly "
            "three Number Sliders, one Series, one Construct Point, one Polyline, "
            "one Square Grid, and one C# script leaf. The C# leaf goal is to "
            "produce one finite numeric value used by the deterministic graph. "
            "Use the exact [] -> A:double interface with no incoming edge and "
            "exactly one outgoing edge to a compatible Number input. Use exactly "
            "eight nodes, seven edges, and maximum topological depth three. "
            "Satisfy every compiler-required input and choose any other wiring "
            "admitted by the listed pin contracts."
        ),
        "maximum_deterministic": (
            "Create one Grasshopper semantic DAG containing exactly six Number "
            "Sliders, three Series components, four Construct Points, two Square "
            "Grids, and one Polyline. Use exactly sixteen nodes, twenty-four "
            "edges, and maximum topological depth five. Satisfy every compiler-"
            "required input and choose any wiring admitted by the listed pin "
            "contracts."
        ),
        "maximum_worker_leaf": (
            "Create one Grasshopper semantic DAG containing exactly five Number "
            "Sliders, one C# script leaf, three Series components, four Construct "
            "Points, two Square Grids, and one Polyline. The C# leaf goal is to "
            "produce one finite numeric value used by the deterministic graph. "
            "Use the exact [] -> A:double interface with no incoming edge and "
            "exactly one outgoing edge to a compatible Number input. Use exactly "
            "sixteen nodes, twenty-four edges, and maximum topological depth "
            "five. Satisfy every compiler-required input and choose any other "
            "wiring admitted by the listed pin contracts."
        ),
    }


def test_fixed_row_table_is_exact() -> None:
    assert tuple(
        (
            row.row_id,
            row.stage,
            row.case_id,
            row.planner_model,
            row.worker_model,
            row.worker_mode,
            row.tool_mode,
        )
        for row in CAMPAIGN._FIXED_ROWS.values()
    ) == (
        ("stage_a.minimum_deterministic", "A", "minimum_deterministic", "anthropic/claude-opus-4-6", None, "none", "fake"),
        ("stage_a.minimum_worker_leaf", "A", "minimum_worker_leaf", "anthropic/claude-opus-4-6", "ollama_chat/qwen3-coder:30b-a3b-q4_K_M", "model", "fake"),
        ("stage_a.medium_deterministic", "A", "medium_deterministic", "anthropic/claude-opus-4-6", None, "none", "fake"),
        ("stage_a.medium_worker_leaf", "A", "medium_worker_leaf", "anthropic/claude-opus-4-6", "ollama_chat/qwen3-coder:30b-a3b-q4_K_M", "model", "fake"),
        ("stage_a.maximum_deterministic", "A", "maximum_deterministic", "anthropic/claude-opus-4-6", None, "none", "fake"),
        ("stage_a.maximum_worker_leaf", "A", "maximum_worker_leaf", "anthropic/claude-opus-4-6", "ollama_chat/qwen3-coder:30b-a3b-q4_K_M", "model", "fake"),
        ("stage_b.qwen36.medium_deterministic", "B", "medium_deterministic", "ollama_chat/qwen3.6:35b", None, "none", "fake"),
        ("stage_b.qwen36.medium_worker_leaf", "B", "medium_worker_leaf", "ollama_chat/qwen3.6:35b", None, "fake", "fake"),
        ("stage_b.gpt_oss.medium_deterministic", "B", "medium_deterministic", "ollama_chat/gpt-oss:20b", None, "none", "fake"),
        ("stage_b.gpt_oss.medium_worker_leaf", "B", "medium_worker_leaf", "ollama_chat/gpt-oss:20b", None, "fake", "fake"),
        ("stage_b.qwen14.medium_deterministic", "B", "medium_deterministic", "ollama_chat/qwen3:14b", None, "none", "fake"),
        ("stage_b.qwen14.medium_worker_leaf", "B", "medium_worker_leaf", "ollama_chat/qwen3:14b", None, "fake", "fake"),
        ("stage_c.qwen_coder", "C", "medium_worker_leaf", None, "ollama_chat/qwen3-coder:30b-a3b-q4_K_M", "model", "fake"),
        ("stage_c.north_mini", "C", "medium_worker_leaf", None, "ollama_chat/north-mini-code-1.0:q4_K_M", "model", "fake"),
        ("stage_c.gemma4", "C", "medium_worker_leaf", None, "ollama_chat/gemma4:12b-it-qat", "model", "fake"),
    )


def test_stage_b_rows_freeze_worker_ownership() -> None:
    rows = [row for row in CAMPAIGN._FIXED_ROWS.values() if row.stage == "B"]
    assert len(rows) == 6
    deterministic = [row for row in rows if not CAMPAIGN._CASES[row.case_id].worker_leaf]
    worker_leaf = [row for row in rows if CAMPAIGN._CASES[row.case_id].worker_leaf]
    assert len(deterministic) == 3
    assert len(worker_leaf) == 3
    assert all(row.worker_mode == "none" for row in deterministic)
    assert all(row.worker_mode == "fake" for row in worker_leaf)
    assert all(row.worker_model is None for row in rows)


@pytest.mark.parametrize("case_id", tuple(CAMPAIGN._CASES))
def test_reference_graph_is_legal_and_attains_its_structural_tier(case_id: str) -> None:
    case = CAMPAIGN._CASES[case_id]
    graph = _load(_reference_payloads()[case_id])
    compiled = (
        semantic_graph_compiler.compile_semantic_graph_worker_leaf_partition(graph)
        if case.worker_leaf
        else semantic_graph_compiler.compile_semantic_graph(graph)
    )
    assert compiled.admitted is True, compiled
    assert CAMPAIGN._structural_tier_attained(case, graph) is True
    if not case.worker_leaf:
        assert compiled.plan is not None
        assert CAMPAIGN._structural_tier_attained(
            case,
            compiled.plan.canonical_graph,
        ) is True


def test_reference_graph_budget_has_uniform_planner_headroom() -> None:
    encoder = tiktoken.get_encoding("cl100k_base")
    measurements = []
    for payload in _reference_payloads().values():
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        measurements.append((len(raw.encode("utf-8")), len(encoder.encode(raw))))
    assert max(size for size, _ in measurements) <= 4096
    maximum_tokens = max(tokens for _, tokens in measurements)
    assert maximum_tokens <= 1024
    assert CAMPAIGN._PLANNER_MAX_TOKENS == 8192
    assert CAMPAIGN._PLANNER_MAX_TOKENS >= 8 * maximum_tokens


def test_structural_tier_rejects_count_depth_primitive_and_cross_edge_drift() -> None:
    medium_case = CAMPAIGN._CASES["medium_deterministic"]
    medium = _reference_payloads()["medium_deterministic"]

    removed_node = copy.deepcopy(medium)
    removed_node["nodes"] = [node for node in removed_node["nodes"] if node["id"] != "grid1"]
    removed_node["edges"] = [edge for edge in removed_node["edges"] if edge["to_node"] != "grid1"]
    assert CAMPAIGN._structural_tier_attained(medium_case, _load(removed_node)) is False

    removed_edge = copy.deepcopy(medium)
    removed_edge["edges"] = removed_edge["edges"][:-1]
    assert CAMPAIGN._structural_tier_attained(medium_case, _load(removed_edge)) is False

    reduced_depth = copy.deepcopy(medium)
    reduced_depth["edges"][3] = _edge("s1", "value", "p1", "x")
    assert CAMPAIGN._structural_tier_attained(medium_case, _load(reduced_depth)) is False

    changed_primitive = copy.deepcopy(medium)
    changed_primitive["nodes"][-1] = _node("grid1", "construct_point")
    changed_primitive["edges"][-1] = _edge("s1", "value", "grid1", "x")
    assert CAMPAIGN._structural_tier_attained(medium_case, _load(changed_primitive)) is False

    leaf_case = CAMPAIGN._CASES["minimum_worker_leaf"]
    missing_cross_edge = copy.deepcopy(_reference_payloads()["minimum_worker_leaf"])
    missing_cross_edge["edges"] = []
    assert CAMPAIGN._structural_tier_attained(leaf_case, _load(missing_cross_edge)) is False


def test_medium_tier_requires_one_weak_component_but_not_reference_edges() -> None:
    case = CAMPAIGN._CASES["medium_deterministic"]
    disconnected = copy.deepcopy(_reference_payloads()["medium_deterministic"])
    disconnected["edges"][-1] = _edge("s2", "value", "p1", "y")
    assert CAMPAIGN._structural_tier_attained(case, _load(disconnected)) is False

    alternative = copy.deepcopy(_reference_payloads()["medium_deterministic"])
    alternative["edges"][3] = _edge("series1", "values", "p1", "z")
    alternative["edges"][-1] = _edge("s2", "value", "grid1", "extent_x")
    assert CAMPAIGN._structural_tier_attained(case, _load(alternative)) is True


@pytest.mark.parametrize(
    "model",
    (
        "anthropic/claude-opus-4-6",
        "ollama_chat/qwen3.6:35b",
        "ollama_chat/gpt-oss:20b",
        "ollama_chat/qwen3:14b",
    ),
)
@pytest.mark.parametrize("worker_leaf", (False, True))
def test_planner_transport_kwargs_use_exact_provider_schema_path(
    model: str,
    worker_leaf: bool,
) -> None:
    expected_schema = (
        semantic_graph.build_worker_leaf_semantic_graph_response_schema()
        if worker_leaf
        else semantic_graph.build_semantic_graph_response_schema()
    )
    kwargs = CAMPAIGN._planner_transport_kwargs(model, worker_leaf=worker_leaf)
    assert kwargs["model"] == model
    assert kwargs["timeout_s"] == 120.0
    assert kwargs["generation_params"]["temperature"] == 0
    assert kwargs["generation_params"]["max_tokens"] == 8192
    assert kwargs["generation_params"]["max_retries"] == 0
    if model.startswith("anthropic/"):
        assert kwargs["structured_response_schema"] is None
        response_format = kwargs["generation_params"]["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["name"] == (
            "rook_semantic_graph_worker_leaf"
            if worker_leaf
            else "rook_semantic_graph"
        )
        assert response_format["json_schema"]["strict"] is True
        assert response_format["json_schema"]["schema"] == expected_schema
    else:
        assert "response_format" not in kwargs["generation_params"]
        assert kwargs["structured_response_schema"] == expected_schema


@pytest.mark.parametrize(
    "model",
    (
        "ollama_chat/qwen3-coder:30b-a3b-q4_K_M",
        "ollama_chat/north-mini-code-1.0:q4_K_M",
        "ollama_chat/gemma4:12b-it-qat",
    ),
)
def test_worker_transport_kwargs_are_exact(model: str) -> None:
    kwargs = CAMPAIGN._worker_transport_kwargs(model)
    assert kwargs == {
        "model": model,
        "generation_params": {
            "temperature": 0,
            "max_tokens": 1024,
            "max_retries": 0,
        },
        "structured_response_schema": CAMPAIGN.build_local_worker_response_schema(),
        "timeout_s": 120.0,
    }


def test_transport_schema_builders_return_fresh_values() -> None:
    first_planner = CAMPAIGN._planner_transport_kwargs(
        "ollama_chat/qwen3.6:35b",
        worker_leaf=True,
    )
    first_planner["structured_response_schema"].clear()
    second_planner = CAMPAIGN._planner_transport_kwargs(
        "ollama_chat/qwen3.6:35b",
        worker_leaf=True,
    )
    assert second_planner["structured_response_schema"] == (
        semantic_graph.build_worker_leaf_semantic_graph_response_schema()
    )

    first_worker = CAMPAIGN._worker_transport_kwargs(
        "ollama_chat/qwen3-coder:30b-a3b-q4_K_M"
    )
    first_worker["structured_response_schema"].clear()
    second_worker = CAMPAIGN._worker_transport_kwargs(
        "ollama_chat/qwen3-coder:30b-a3b-q4_K_M"
    )
    assert second_worker["structured_response_schema"] == (
        CAMPAIGN.build_local_worker_response_schema()
    )


def test_transport_kwargs_refuse_unscored_models() -> None:
    with pytest.raises(ValueError, match="planner_model_not_scored"):
        CAMPAIGN._planner_transport_kwargs("ollama_chat/reserve", worker_leaf=False)
    with pytest.raises(ValueError, match="worker_model_not_scored"):
        CAMPAIGN._worker_transport_kwargs("ollama_chat/reserve")
