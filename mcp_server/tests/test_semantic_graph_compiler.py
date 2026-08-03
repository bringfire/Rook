from __future__ import annotations

import dataclasses
import inspect
import json
from dataclasses import replace

import pytest

import rook.agent.semantic_graph as semantic_graph
import rook.agent.semantic_graph_compiler as compiler


def _slider(
    node_id: str,
    *,
    initial: int | float = 5,
    maximum: int | float = 10,
    parameters_order: tuple[str, ...] = ("label", "minimum", "maximum", "initial"),
) -> dict[str, object]:
    values: dict[str, object] = {
        "label": "Value",
        "minimum": 0,
        "maximum": maximum,
        "initial": initial,
    }
    return {
        "id": node_id,
        "primitive": "number_slider",
        "parameters": {name: values[name] for name in parameters_order},
    }


def _node(node_id: str, primitive: str) -> dict[str, object]:
    return {"id": node_id, "primitive": primitive, "parameters": {}}


def _csharp_node(
    node_id: str = "generated_value",
    *,
    goal: str = "Produce one numeric value.",
) -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": "csharp_script",
        "parameters": {
            "goal": goal,
            "interface": {
                "inputs": [],
                "outputs": [{"name": "A", "type": "double"}],
            },
        },
    }


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


def _load(
    nodes: list[dict[str, object]],
    edges: list[dict[str, str]],
) -> semantic_graph.SemanticGraph:
    raw = json.dumps(
        {
            "schema": semantic_graph.SEMANTIC_GRAPH_SCHEMA,
            "nodes": nodes,
            "edges": edges,
        },
        separators=(",", ":"),
    )
    loaded = semantic_graph.load_semantic_graph(raw)
    assert loaded.admitted is True
    assert loaded.graph is not None
    return loaded.graph


def _compile(
    nodes: list[dict[str, object]],
    edges: list[dict[str, str]],
) -> compiler.SemanticGraphCompileResult:
    return compiler.compile_semantic_graph(_load(nodes, edges))


def _assert_refused(
    nodes: list[dict[str, object]],
    edges: list[dict[str, str]],
    reason: str,
) -> None:
    result = _compile(nodes, edges)
    assert result == compiler.SemanticGraphCompileResult(
        admitted=False,
        plan=None,
        failure="graph_admission",
        reason=reason,
    )


def _partition(
    nodes: list[dict[str, object]],
    edges: list[dict[str, str]],
):
    return compiler.compile_semantic_graph_worker_leaf_partition(
        _load(nodes, edges)
    )


def test_partition_compiler_separates_one_worker_leaf_and_cross_edge() -> None:
    result = _partition(
        [_csharp_node(), _node("point", "construct_point")],
        [_edge("generated_value", "A", "point", "x")],
    )

    assert result.admitted is True
    partition = result.partition
    assert partition is not None
    assert partition.unresolved_leaf.node_id == "generated_value"
    assert partition.unresolved_leaf.goal == "Produce one numeric value."
    assert partition.unresolved_leaf.interface.outputs[0].name == "A"
    assert partition.cross_edge == compiler.WorkerLeafCrossEdge(
        source_node_id="generated_value",
        source_pin="A",
        source_output_index=1,
        target_node_id="point",
        target_pin="x",
        target_input_index=0,
    )
    assert partition.deterministic_plan.semantic_node_to_temp_id == (
        ("point", "T1"),
    )
    assert partition.deterministic_plan.connect == ()
    assert all(
        dict(instruction.fields).get("guid") != "csharp_script"
        for instruction in partition.deterministic_plan.create_instructions
    )


def test_partition_compiler_preserves_zero_leaf_slice1_plan() -> None:
    graph = _load([_node("point", "construct_point")], [])
    existing = compiler.compile_semantic_graph(graph)
    partitioned = compiler.compile_semantic_graph_worker_leaf_partition(graph)

    assert existing.admitted is True
    assert partitioned.admitted is True
    assert partitioned.partition is not None
    assert partitioned.partition.deterministic_plan == existing.plan
    assert partitioned.partition.unresolved_leaf is None
    assert partitioned.partition.cross_edge is None


def test_partition_types_are_exact_frozen_and_require_paired_leaf_edge() -> None:
    graph = _load([_csharp_node()], [])
    interface = dict(graph.nodes[0].parameters)["interface"]
    leaf = compiler.UnresolvedCSharpLeaf(
        node_id="generated_value",
        goal="Produce one numeric value.",
        interface=interface,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        leaf.goal = "changed"
    with pytest.raises(TypeError):
        compiler.UnresolvedCSharpLeaf(
            node_id="generated_value",
            goal="Produce one numeric value.",
            interface={"inputs": [], "outputs": []},
        )

    deterministic = compiler.compile_semantic_graph(
        _load([_node("point", "construct_point")], [])
    )
    assert deterministic.plan is not None
    with pytest.raises(TypeError):
        compiler.SemanticGraphWorkerLeafPartition(
            deterministic_plan=deterministic.plan,
            unresolved_leaf=leaf,
            cross_edge=None,
        )


def test_partition_compiler_defensively_refuses_two_typed_worker_leaves() -> None:
    first = _load([_csharp_node("first")], []).nodes[0]
    second = _load([_csharp_node("second")], []).nodes[0]
    target = _load([_node("point", "construct_point")], []).nodes[0]
    graph = semantic_graph.SemanticGraph(
        schema=semantic_graph.SEMANTIC_GRAPH_SCHEMA,
        nodes=(first, second, target),
        edges=(
            semantic_graph.SemanticGraphEdge("first", "A", "point", "x"),
        ),
    )

    result = compiler.compile_semantic_graph_worker_leaf_partition(graph)

    assert result.admitted is False
    assert result.partition is None
    assert result.reason == "multiple_worker_leaves"


@pytest.mark.parametrize(
    ("nodes", "edges", "reason"),
    [
        (
            [_slider("slider"), _csharp_node()],
            [_edge("slider", "value", "generated_value", "A")],
            "worker_leaf_has_incoming_edge",
        ),
        (
            [_csharp_node(), _node("point", "construct_point")],
            [],
            "worker_leaf_requires_one_outgoing_edge",
        ),
        (
            [_csharp_node(), _node("point", "construct_point")],
            [
                _edge("generated_value", "A", "point", "x"),
                _edge("generated_value", "A", "point", "y"),
            ],
            "worker_leaf_requires_one_outgoing_edge",
        ),
        (
            [_csharp_node(), _node("point", "construct_point")],
            [_edge("generated_value", "B", "point", "x")],
            "worker_leaf_source_pin_invalid",
        ),
        (
            [_csharp_node(), _node("point", "construct_point")],
            [_edge("generated_value", "A", "missing", "x")],
            "worker_leaf_target_invalid",
        ),
        (
            [_csharp_node(), _node("point", "construct_point")],
            [_edge("generated_value", "A", "point", "missing")],
            "worker_leaf_target_pin_invalid",
        ),
        (
            [_csharp_node(), _node("line", "polyline")],
            [_edge("generated_value", "A", "line", "vertices")],
            "worker_leaf_target_type_invalid",
        ),
        (
            [_csharp_node()],
            [_edge("generated_value", "A", "generated_value", "A")],
            "worker_leaf_has_incoming_edge",
        ),
        (
            [
                _csharp_node(),
                _node("a", "series"),
                _node("b", "series"),
            ],
            [
                _edge("generated_value", "A", "a", "start"),
                _edge("a", "values", "b", "start"),
                _edge("b", "values", "a", "step"),
            ],
            "cycle_detected",
        ),
        (
            [
                _csharp_node(),
                _slider("slider"),
                _node("point", "construct_point"),
            ],
            [
                _edge("generated_value", "A", "point", "x"),
                _edge("slider", "value", "point", "x"),
            ],
            "too_many_input_connections",
        ),
    ],
)
def test_partition_compiler_refuses_invalid_worker_leaf_graphs(
    nodes: list[dict[str, object]],
    edges: list[dict[str, str]],
    reason: str,
) -> None:
    result = _partition(nodes, edges)

    assert result.admitted is False
    assert result.partition is None
    assert result.failure == "graph_admission"
    assert result.reason == reason


@pytest.mark.parametrize(
    ("edge", "reason"),
    [
        (_edge("missing", "value", "point", "x"), "unknown_source_node"),
        (_edge("slider", "value", "missing", "x"), "unknown_target_node"),
        (_edge("slider", "missing", "point", "x"), "unknown_source_pin"),
        (_edge("slider", "Value", "point", "x"), "unknown_source_pin"),
        (_edge("slider", "value", "point", "missing"), "unknown_target_pin"),
        (_edge("slider", "value", "point", "X"), "unknown_target_pin"),
        (_edge("series", "start", "point", "x"), "unknown_source_pin"),
        (_edge("slider", "value", "point", "point"), "unknown_target_pin"),
    ],
)
def test_compile_refuses_unknown_nodes_pins_and_reversed_directions(
    edge: dict[str, str],
    reason: str,
) -> None:
    _assert_refused(
        [_slider("slider"), _node("series", "series"), _node("point", "construct_point")],
        [edge],
        reason,
    )


def test_compile_refuses_incompatible_element_types() -> None:
    _assert_refused(
        [_node("grid", "square_grid"), _node("line", "polyline")],
        [_edge("grid", "cells", "line", "vertices")],
        "incompatible_element_types",
    )


def test_compile_refuses_second_connection_to_one_input() -> None:
    _assert_refused(
        [_slider("a"), _slider("b"), _node("point", "construct_point")],
        [
            _edge("a", "value", "point", "x"),
            _edge("b", "value", "point", "x"),
        ],
        "too_many_input_connections",
    )


def test_compile_refuses_unconnected_required_input() -> None:
    _assert_refused(
        [_node("line", "polyline")],
        [],
        "required_input_unconnected",
    )


def test_compile_refuses_self_edge() -> None:
    _assert_refused(
        [_node("series", "series")],
        [_edge("series", "values", "series", "start")],
        "self_edge",
    )


@pytest.mark.parametrize(
    ("node_ids", "edges"),
    [
        (
            ("a", "b"),
            [
                _edge("a", "values", "b", "start"),
                _edge("b", "values", "a", "start"),
            ],
        ),
        (
            ("a", "b", "c"),
            [
                _edge("a", "values", "b", "start"),
                _edge("b", "values", "c", "start"),
                _edge("c", "values", "a", "start"),
            ],
        ),
    ],
)
def test_compile_refuses_cycles(
    node_ids: tuple[str, ...],
    edges: list[dict[str, str]],
) -> None:
    _assert_refused(
        [_node(node_id, "series") for node_id in node_ids],
        edges,
        "cycle_detected",
    )


@pytest.mark.parametrize(
    ("target_primitive", "target_pin"),
    [
        ("series", "count"),
        ("square_grid", "extent_x"),
        ("square_grid", "extent_y"),
    ],
)
@pytest.mark.parametrize("initial", [2.5, 0, 101])
def test_compile_refuses_slider_integer_input_outside_admitted_initial_range(
    target_primitive: str,
    target_pin: str,
    initial: int | float,
) -> None:
    _assert_refused(
        [
            _slider(
                "slider",
                initial=initial,
                maximum=200 if initial == 101 else 10,
            ),
            _node("target", target_primitive),
        ],
        [_edge("slider", "value", "target", target_pin)],
        "invalid_integer_input_initial",
    )


def test_compile_refuses_number_to_integer_from_non_slider() -> None:
    _assert_refused(
        [_node("source", "series"), _node("target", "series")],
        [_edge("source", "values", "target", "count")],
        "incompatible_element_types",
    )


@pytest.mark.parametrize(
    ("nodes", "edges"),
    [
        (
            [_node("series", "series"), _node("point", "construct_point")],
            [_edge("series", "values", "point", "x")],
        ),
        (
            [_node("grid", "square_grid"), _node("line", "polyline")],
            [_edge("grid", "points", "line", "vertices")],
        ),
    ],
)
def test_compile_leaves_access_data_matching_to_grasshopper(
    nodes: list[dict[str, object]],
    edges: list[dict[str, str]],
) -> None:
    result = _compile(nodes, edges)
    assert result.admitted is True
    assert result.plan is not None


def test_compile_canonicalizes_source_order_and_lowers_existing_edit_shapes() -> None:
    nodes_a = [
        _node("m_point", "construct_point"),
        _slider("a_slider"),
        _node("z_series", "series"),
    ]
    nodes_b = [
        _node("z_series", "series"),
        _slider(
            "a_slider",
            parameters_order=("initial", "maximum", "minimum", "label"),
        ),
        _node("m_point", "construct_point"),
    ]
    edges_a = [
        _edge("z_series", "values", "m_point", "x"),
        _edge("a_slider", "value", "z_series", "count"),
    ]
    edges_b = list(reversed(edges_a))

    first = _compile(nodes_a, edges_a)
    second = _compile(nodes_b, edges_b)

    assert first.admitted is True
    assert first.plan is not None
    assert second.plan == first.plan
    assert tuple(node.id for node in first.plan.canonical_graph.nodes) == (
        "a_slider",
        "m_point",
        "z_series",
    )
    assert tuple(
        (edge.from_node, edge.from_pin, edge.to_node, edge.to_pin)
        for edge in first.plan.canonical_graph.edges
    ) == (
        ("a_slider", "value", "z_series", "count"),
        ("z_series", "values", "m_point", "x"),
    )
    assert first.plan.canonical_graph.json_bytes == (
        b'{"edges":[{"from_node":"a_slider","from_pin":"value",'
        b'"to_node":"z_series","to_pin":"count"},{"from_node":"z_series",'
        b'"from_pin":"values","to_node":"m_point","to_pin":"x"}],'
        b'"nodes":[{"id":"a_slider","parameters":{"initial":5,"label":"Value",'
        b'"maximum":10,"minimum":0},"primitive":"number_slider"},{"id":"m_point",'
        b'"parameters":{},"primitive":"construct_point"},{"id":"z_series",'
        b'"parameters":{},"primitive":"series"}],"schema":"rook.gh_semantic_graph:v1"}'
    )
    assert first.plan.semantic_node_to_temp_id == (
        ("a_slider", "T1"),
        ("m_point", "T2"),
        ("z_series", "T3"),
    )
    assert first.plan.connect == (
        "T1.O0>T3.I2",
        "T3.O0>T2.I0",
    )
    assert first.plan.semantic_edge_to_flow == (
        (("a_slider", "value", "z_series", "count"), "T1.O0>T3.I2"),
        (("z_series", "values", "m_point", "x"), "T3.O0>T2.I0"),
    )

    request = compiler.materialize_gh_edit_request(first.plan, 7)
    assert request == {
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
            },
            {
                "temp_id": "T2",
                "guid": "3581f42a-9592-4549-bd6b-1c0fc39d067b",
                "pos": [580, 100],
            },
            {
                "temp_id": "T3",
                "guid": "e64c5fb1-845c-4ab1-8911-5f338516ba67",
                "pos": [340, 100],
            },
        ],
        "connect": ["T1.O0>T3.I2", "T3.O0>T2.I0"],
    }


def test_layout_uses_depth_then_node_id_within_each_depth() -> None:
    result = _compile(
        [
            _slider("b_slider"),
            _slider("a_slider"),
            _node("point", "construct_point"),
        ],
        [_edge("a_slider", "value", "point", "x")],
    )
    assert result.plan is not None
    request = compiler.materialize_gh_edit_request(result.plan, 1)
    positions = {
        node_id: tuple(create["pos"])
        for (node_id, _), create in zip(
            result.plan.semantic_node_to_temp_id,
            request["create"],
            strict=True,
        )
    }
    assert positions == {
        "a_slider": (100, 100),
        "b_slider": (100, 220),
        "point": (340, 100),
    }


@pytest.mark.parametrize(
    ("target_primitive", "target_pin"),
    [
        ("construct_point", "x"),
        ("square_grid", "cell_size"),
    ],
)
def test_compile_admits_small_non_witness_recombinations(
    target_primitive: str,
    target_pin: str,
) -> None:
    result = _compile(
        [_slider("control"), _node("target", target_primitive)],
        [_edge("control", "value", "target", target_pin)],
    )
    assert result.admitted is True
    assert result.plan is not None
    assert result.plan.connect == ("T1.O0>T2.I0" if target_pin == "x" else "T1.O0>T2.I1",)


def test_compiler_source_contains_no_witness_specific_program() -> None:
    source = inspect.getsource(compiler)
    for forbidden in (
        "phyllotaxis",
        "point_row",
        "square_grid_witness",
        "expected_witness_node_count",
        "construct_point.x",
        "Produce one numeric value",
        "gh_connect",
        "A = 7.0",
    ):
        assert forbidden not in source


def test_unknown_code_owned_lowering_kind_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    point = next(
        primitive
        for primitive in semantic_graph._PRIMITIVES
        if primitive.name == "construct_point"
    )
    forged = replace(point, lowering_kind="unknown")
    monkeypatch.setattr(
        semantic_graph,
        "_PRIMITIVES",
        tuple(
            forged if primitive is point else primitive
            for primitive in semantic_graph._PRIMITIVES
        ),
    )

    with pytest.raises(RuntimeError, match="unknown lowering kind"):
        _compile([_node("point", "construct_point")], [])


@pytest.mark.parametrize("epoch", [True, False, 0, -1, 1.0, "1", None])
def test_materialize_requires_exact_positive_integer_epoch(epoch: object) -> None:
    result = _compile([_slider("slider")], [])
    assert result.plan is not None
    with pytest.raises(ValueError, match="positive integer epoch"):
        compiler.materialize_gh_edit_request(result.plan, epoch)  # type: ignore[arg-type]


def test_materialize_returns_fresh_mutable_request_without_mutating_plan() -> None:
    result = _compile(
        [_slider("slider"), _node("point", "construct_point")],
        [_edge("slider", "value", "point", "x")],
    )
    assert result.plan is not None
    assert not hasattr(result.plan, "epoch")

    first = compiler.materialize_gh_edit_request(result.plan, 3)
    second = compiler.materialize_gh_edit_request(result.plan, 3)
    assert first == second
    assert first is not second
    assert first["create"] is not second["create"]
    assert first["connect"] is not second["connect"]
    first["create"][0]["pos"][0] = 999
    first["connect"].append("forged")
    assert second["create"][0]["pos"] == [340, 100]
    assert second["connect"] == ["T2.O0>T1.I0"]

    plan_text = repr(result.plan)
    for forbidden in ("epoch=", "C1", "instance_guid", "delete", "disconnect", "update", "group"):
        assert forbidden not in plan_text
