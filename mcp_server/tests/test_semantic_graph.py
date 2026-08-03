from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import rook.agent.semantic_graph as semantic_graph
from rook.agent.semantic_graph_compiler import compile_semantic_graph


_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "gh_semantic_graph_slice1_primitives_snapshot.json"
)

_EXPECTED_REGULAR_PINS = {
    "e64c5fb1-845c-4ab1-8911-5f338516ba67": {
        "inputs": (
            (0, "Number", "item", False),
            (1, "Number", "item", False),
            (2, "Integer", "item", False),
        ),
        "outputs": ((0, "Number", "list", False),),
    },
    "3581f42a-9592-4549-bd6b-1c0fc39d067b": {
        "inputs": (
            (0, "Number", "item", False),
            (1, "Number", "item", False),
            (2, "Number", "item", False),
        ),
        "outputs": ((0, "Point", "item", False),),
    },
    "71b5b089-500a-4ea6-81c5-2f960441a0e8": {
        "inputs": (
            (0, "Point", "list", False),
            (1, "Boolean", "item", False),
        ),
        "outputs": ((0, "Curve", "item", False),),
    },
    "717a1e25-a075-4530-bc80-d43ecc2500d9": {
        "inputs": (
            (0, "Plane", "item", False),
            (1, "Number", "item", False),
            (2, "Integer", "item", False),
            (3, "Integer", "item", False),
        ),
        "outputs": (
            (0, "Rectangle", "item", False),
            (1, "Point", "tree", False),
        ),
    },
}


def _pin_projection(pin: object) -> tuple[object, ...]:
    return (
        pin.index,
        pin.element_type,
        pin.access,
        pin.gh_optional,
    )


def test_qualified_fixture_matches_private_primitive_tuple() -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["request"] == {
        "include_data": False,
        "max_preview_items": 0,
    }
    body = fixture["snapshot_body"]
    assert body["epoch"] == 3
    assert len(body["components"]) == 5
    assert body["flows"] == []

    physical_by_guid = {
        component["componentGuid"].lower(): component
        for component in body["components"]
        if "componentGuid" in component
    }
    assert set(physical_by_guid) == set(_EXPECTED_REGULAR_PINS)
    for guid, directions in _EXPECTED_REGULAR_PINS.items():
        component = physical_by_guid[guid]
        for direction, expected in directions.items():
            actual = tuple(
                (
                    pin["idx"],
                    pin["type"],
                    pin["access"],
                    pin["optional"],
                )
                for pin in component[direction]
            )
            assert actual == expected

    primitive_by_guid = {
        primitive.component_guid: primitive
        for primitive in semantic_graph._PRIMITIVES
        if primitive.component_guid is not None
    }
    assert set(primitive_by_guid) == set(physical_by_guid)
    for guid, component in physical_by_guid.items():
        primitive = primitive_by_guid[guid]
        assert tuple(_pin_projection(pin) for pin in primitive.inputs) == tuple(
            (
                pin["idx"],
                pin["type"],
                pin["access"],
                pin["optional"],
            )
            for pin in component["inputs"]
        )
        assert tuple(_pin_projection(pin) for pin in primitive.outputs) == tuple(
            (
                pin["idx"],
                pin["type"],
                pin["access"],
                pin["optional"],
            )
            for pin in component["outputs"]
        )

    slider_component = next(
        component for component in body["components"] if component["type"] == "NumberSlider"
    )
    slider_value = slider_component["value"]
    assert slider_value["type"] == "slider"
    assert all(
        type(slider_value[name]) in {int, float}
        and math.isfinite(slider_value[name])
        for name in ("min", "val", "max")
    )
    assert slider_value["min"] <= slider_value["val"] <= slider_value["max"]

    primitive_by_name = {
        primitive.name: primitive for primitive in semantic_graph._PRIMITIVES
    }
    assert set(primitive_by_name) == {
        "number_slider",
        "series",
        "construct_point",
        "polyline",
        "square_grid",
    }
    slider = primitive_by_name["number_slider"]
    assert slider.lowering_kind == "slider"
    assert slider.snapshot_type == "NumberSlider"
    assert tuple(_pin_projection(pin) for pin in slider.outputs) == (
        (0, "Number", "item", None),
    )
    assert all(pin.max_connections == 1 for primitive in semantic_graph._PRIMITIVES for pin in primitive.inputs)
    assert {
        (primitive.name, pin.name)
        for primitive in semantic_graph._PRIMITIVES
        for pin in primitive.inputs
        if pin.connection_required
    } == {("polyline", "vertices")}

    assert primitive_by_name["construct_point"].inputs[0].name == "x"
    assert physical_by_guid["3581f42a-9592-4549-bd6b-1c0fc39d067b"]["inputs"][0]["name"] == "X coordinate"
    assert primitive_by_name["square_grid"].outputs[0].name == "cells"
    assert physical_by_guid["717a1e25-a075-4530-bc80-d43ecc2500d9"]["name"] == "Square"

    production_tree = ast.parse(inspect.getsource(semantic_graph))
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(production_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called_names = {
        node.func.id
        for node in ast.walk(production_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert imported_roots.isdisjoint({"pathlib", "tests", "fixtures"})
    assert called_names.isdisjoint({"open", "Path"})


class _StringSubclass(str):
    pass


def _slider_node(
    *,
    node_id: object = "slider",
    primitive: object = "number_slider",
    parameters: object | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": primitive,
        "parameters": (
            {
                "label": "Value",
                "minimum": 0,
                "maximum": 10,
                "initial": 5,
            }
            if parameters is None
            else parameters
        ),
    }


def _component_node(
    node_id: str = "point",
    primitive: str = "construct_point",
) -> dict[str, object]:
    return {"id": node_id, "primitive": primitive, "parameters": {}}


def _csharp_node(
    node_id: str = "generated_value",
    *,
    goal: object = "Produce one numeric value.",
    interface: object | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": "csharp_script",
        "parameters": {
            "goal": goal,
            "interface": (
                {
                    "inputs": [],
                    "outputs": [{"name": "A", "type": "double"}],
                }
                if interface is None
                else interface
            ),
        },
    }


def _edge(
    *,
    from_node: object = "slider",
    from_pin: object = "value",
    to_node: object = "point",
    to_pin: object = "x",
) -> dict[str, object]:
    return {
        "from_node": from_node,
        "from_pin": from_pin,
        "to_node": to_node,
        "to_pin": to_pin,
    }


def _payload(
    *,
    schema: object = semantic_graph.SEMANTIC_GRAPH_SCHEMA,
    nodes: object | None = None,
    edges: object | None = None,
) -> dict[str, object]:
    return {
        "schema": schema,
        "nodes": [_slider_node()] if nodes is None else nodes,
        "edges": [] if edges is None else edges,
    }


def _raw(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _assert_refused(raw_response: object, reason: str) -> None:
    result = semantic_graph.load_semantic_graph(raw_response)  # type: ignore[arg-type]
    assert result.admitted is False
    assert result.graph is None
    assert result.failure is not None
    assert result.reason == reason


def _walk_schema(value: object):
    yield value
    if type(value) is dict:
        for child in value.values():
            yield from _walk_schema(child)
    elif type(value) is list:
        for child in value:
            yield from _walk_schema(child)


def test_loader_materializes_owned_immutable_csharp_interface() -> None:
    payload = _payload(nodes=[_csharp_node()], edges=[])
    source_interface = payload["nodes"][0]["parameters"]["interface"]

    graph = semantic_graph._load_graph_object(payload)
    node = graph.nodes[0]
    parameters = dict(node.parameters)
    interface = parameters["interface"]

    assert type(interface) is semantic_graph.SemanticCSharpInterface
    assert interface.inputs == ()
    assert type(interface.outputs) is tuple
    assert interface.outputs == (
        semantic_graph.SemanticCSharpOutput(name="A", type="double"),
    )
    source_interface["outputs"][0]["name"] = "B"
    source_interface["outputs"].append({"name": "B", "type": "integer"})
    assert interface.outputs[0].name == "A"
    assert len(interface.outputs) == 1


def test_csharp_interface_rejects_mutable_or_wrong_nested_carriers() -> None:
    output = semantic_graph.SemanticCSharpOutput(name="A", type="double")
    with pytest.raises(TypeError):
        semantic_graph.SemanticCSharpInterface(inputs=[], outputs=(output,))
    with pytest.raises(TypeError):
        semantic_graph.SemanticCSharpInterface(
            inputs=(),
            outputs=({"name": "A", "type": "double"},),
        )

    interface = semantic_graph.SemanticCSharpInterface(
        inputs=(),
        outputs=(output,),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        interface.outputs = ()


@pytest.mark.parametrize(
    ("parameters", "reason"),
    [
        ({"interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}]}}, "invalid_csharp_parameters"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}]}, "extra": True}, "invalid_csharp_parameters"),
        ({"goal": 1, "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}] }}, "invalid_csharp_goal"),
        ({"goal": "   ", "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}] }}, "invalid_csharp_goal"),
        ({"goal": "a" * 4_097, "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}] }}, "invalid_csharp_goal"),
        ({"goal": "😀" * 4_097, "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}] }}, "invalid_csharp_goal"),
        ({"goal": "Value", "interface": {"outputs": [{"name": "A", "type": "double"}]}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}], "extra": True}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": {}, "outputs": [{"name": "A", "type": "double"}]}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [{}], "outputs": [{"name": "A", "type": "double"}]}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": {}}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": []}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double"}, {"name": "B", "type": "double"}]}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": [{"name": "A"}]}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": [{"name": "A", "type": "double", "extra": True}]}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": [{"name": "B", "type": "double"}]}}, "invalid_csharp_interface"),
        ({"goal": "Value", "interface": {"inputs": [], "outputs": [{"name": "A", "type": "integer"}]}}, "invalid_csharp_interface"),
    ],
)
def test_loader_rejects_invalid_csharp_parameters(
    parameters: dict[str, object],
    reason: str,
) -> None:
    node = _csharp_node()
    node["parameters"] = parameters
    _assert_refused(_raw(_payload(nodes=[node])), reason)


def test_loader_rejects_more_than_one_csharp_script() -> None:
    _assert_refused(
        _raw(
            _payload(
                nodes=[
                    _csharp_node("first"),
                    _csharp_node("second"),
                ]
            )
        ),
        "multiple_worker_leaves",
    )


def test_loader_rejects_escaped_lone_surrogate_csharp_goal() -> None:
    raw_response = json.dumps(
        _payload(nodes=[_csharp_node(goal=chr(0xD800))]),
        ensure_ascii=True,
        separators=(",", ":"),
    )
    _assert_refused(raw_response, "invalid_csharp_goal")


def test_worker_leaf_schema_uses_provider_qualified_anyof_only() -> None:
    schema = semantic_graph.build_worker_leaf_semantic_graph_response_schema()
    Draft202012Validator.check_schema(schema)
    walked = tuple(_walk_schema(schema))
    assert not any(type(value) is dict and "oneOf" in value for value in walked)
    alternatives = schema["properties"]["nodes"]["items"]["anyOf"]
    assert any(
        item["properties"]["primitive"] == {"const": "csharp_script"}
        for item in alternatives
    )
    serialized = json.dumps(schema, sort_keys=True)
    assert "maxItems" not in serialized
    assert "minItems" not in serialized
    assert "maxLength" not in serialized


def test_worker_leaf_schema_and_projection_are_fresh_without_mutating_slice1() -> None:
    original_schema = semantic_graph.build_semantic_graph_response_schema()
    original_projection = semantic_graph.semantic_primitive_prompt_projection()

    worker_schema = semantic_graph.build_worker_leaf_semantic_graph_response_schema()
    worker_projection = semantic_graph.semantic_worker_leaf_prompt_projection()
    worker_schema["required"].append("forged")
    worker_projection[-1]["primitive"] = "forged"

    assert semantic_graph.build_semantic_graph_response_schema() == original_schema
    assert semantic_graph.semantic_primitive_prompt_projection() == original_projection
    assert "forged" not in semantic_graph.build_worker_leaf_semantic_graph_response_schema()["required"]
    assert semantic_graph.semantic_worker_leaf_prompt_projection()[-1]["primitive"] == "csharp_script"


def test_loader_admits_smallest_graph_and_canonicalizes_parameter_order() -> None:
    result = semantic_graph.load_semantic_graph(
        _raw(
            _payload(
                nodes=[
                    _slider_node(
                        parameters={
                            "maximum": 10,
                            "initial": 5,
                            "label": "Value",
                            "minimum": 0,
                        }
                    )
                ]
            )
        )
    )

    assert result == semantic_graph.SemanticGraphLoadResult(
        admitted=True,
        graph=semantic_graph.SemanticGraph(
            schema="rook.gh_semantic_graph:v1",
            nodes=(
                semantic_graph.SemanticGraphNode(
                    id="slider",
                    primitive="number_slider",
                    parameters=(
                        ("initial", 5),
                        ("label", "Value"),
                        ("maximum", 10),
                        ("minimum", 0),
                    ),
                ),
            ),
            edges=(),
        ),
        failure=None,
        reason="admitted",
    )


@pytest.mark.parametrize(
    ("raw_response", "reason"),
    [
        (42, "response_not_string"),
        (_StringSubclass("{}"), "response_not_string"),
        (chr(0xD800), "response_not_utf8"),
        ("x" * 65_537, "response_too_large"),
        ("not json", "response_invalid_json"),
        ('{"schema":"a","schema":"b"}', "response_duplicate_key"),
        (
            '{"schema":"rook.gh_semantic_graph:v1","nodes":[],"edges":[],"extra":{"a":1,"a":2}}',
            "response_duplicate_key",
        ),
        ('{"value":NaN}', "response_nonfinite_number"),
        ('{"value":Infinity}', "response_nonfinite_number"),
        ('{"value":-Infinity}', "response_nonfinite_number"),
        ('{"value":1e400}', "response_nonfinite_number"),
        ('{"value":-1e400}', "response_nonfinite_number"),
        ('{"value":' + ("9" * 5_000) + "}", "response_invalid_json"),
        (_raw(_payload()) + " {}", "response_trailing_content"),
        ("[]", "response_not_object"),
        ("```json\n{}\n```", "response_invalid_json"),
    ],
    ids=[
        "non_string",
        "string_subclass",
        "unencodable_surrogate",
        "over_byte_limit",
        "malformed_json",
        "duplicate_root_key",
        "duplicate_nested_key",
        "nan",
        "positive_infinity",
        "negative_infinity",
        "positive_exponent_overflow",
        "negative_exponent_overflow",
        "over_limit_integer_token",
        "trailing_content",
        "non_object_root",
        "markdown_fence",
    ],
)
def test_loader_returns_typed_parser_refusals(
    raw_response: object,
    reason: str,
) -> None:
    _assert_refused(raw_response, reason)


@pytest.mark.parametrize("missing", ["schema", "nodes", "edges"])
def test_loader_rejects_missing_root_fields(missing: str) -> None:
    payload = _payload()
    del payload[missing]
    _assert_refused(_raw(payload), "invalid_root_fields")


def test_loader_rejects_unknown_root_field() -> None:
    payload = _payload()
    payload["unknown"] = True
    _assert_refused(_raw(payload), "invalid_root_fields")


@pytest.mark.parametrize("schema", ["rook.gh_semantic_graph:v2", 1, True, None])
def test_loader_rejects_invalid_schema(schema: object) -> None:
    _assert_refused(_raw(_payload(schema=schema)), "invalid_schema")


@pytest.mark.parametrize(
    ("nodes", "reason"),
    [
        ([], "invalid_node_count"),
        ([_slider_node(node_id=f"n{index}") for index in range(17)], "invalid_node_count"),
        ({}, "invalid_nodes"),
    ],
)
def test_loader_rejects_invalid_node_collection(
    nodes: object,
    reason: str,
) -> None:
    _assert_refused(_raw(_payload(nodes=nodes)), reason)


@pytest.mark.parametrize(
    ("edges", "reason"),
    [
        ([_edge() for _ in range(25)], "invalid_edge_count"),
        ({}, "invalid_edges"),
    ],
)
def test_loader_rejects_invalid_edge_collection(
    edges: object,
    reason: str,
) -> None:
    _assert_refused(_raw(_payload(edges=edges)), reason)


@pytest.mark.parametrize("missing", ["id", "primitive", "parameters"])
def test_loader_rejects_missing_node_fields(missing: str) -> None:
    node = _slider_node()
    del node[missing]
    _assert_refused(_raw(_payload(nodes=[node])), "invalid_node_fields")


def test_loader_rejects_unknown_node_field() -> None:
    node = _slider_node()
    node["unknown"] = True
    _assert_refused(_raw(_payload(nodes=[node])), "invalid_node_fields")


@pytest.mark.parametrize("missing", ["from_node", "from_pin", "to_node", "to_pin"])
def test_loader_rejects_missing_edge_fields(missing: str) -> None:
    edge = _edge()
    del edge[missing]
    _assert_refused(
        _raw(_payload(nodes=[_slider_node(), _component_node()], edges=[edge])),
        "invalid_edge_fields",
    )


def test_loader_rejects_unknown_edge_field() -> None:
    edge = _edge()
    edge["unknown"] = True
    _assert_refused(
        _raw(_payload(nodes=[_slider_node(), _component_node()], edges=[edge])),
        "invalid_edge_fields",
    )


@pytest.mark.parametrize(
    "node_id",
    ["", "A", "1node", "node-name", "node name", "a" * 49, 1, True, None],
)
def test_loader_rejects_invalid_node_id(node_id: object) -> None:
    _assert_refused(
        _raw(_payload(nodes=[_slider_node(node_id=node_id)])),
        "invalid_node_id",
    )


def test_loader_rejects_duplicate_node_ids() -> None:
    _assert_refused(
        _raw(
            _payload(
                nodes=[
                    _slider_node(node_id="same"),
                    _component_node(node_id="same"),
                ]
            )
        ),
        "duplicate_node_id",
    )


def test_loader_rejects_duplicate_exact_edges() -> None:
    edge = _edge()
    _assert_refused(
        _raw(
            _payload(
                nodes=[_slider_node(), _component_node()],
                edges=[edge, dict(edge)],
            )
        ),
        "duplicate_edge",
    )


@pytest.mark.parametrize("primitive", ["unknown", 1, True, None])
def test_loader_rejects_unknown_or_invalid_primitive(primitive: object) -> None:
    _assert_refused(
        _raw(_payload(nodes=[_slider_node(primitive=primitive)])),
        "unknown_primitive",
    )


@pytest.mark.parametrize(
    ("parameters", "reason"),
    [
        ({"label": "Value", "minimum": 0, "maximum": 10}, "invalid_parameters"),
        (
            {
                "label": "Value",
                "minimum": 0,
                "maximum": 10,
                "initial": 5,
                "unknown": 1,
            },
            "invalid_parameters",
        ),
        ([], "invalid_parameters"),
        (
            {"label": 1, "minimum": 0, "maximum": 10, "initial": 5},
            "invalid_slider_label",
        ),
        (
            {"label": "Value", "minimum": False, "maximum": 10, "initial": 5},
            "invalid_slider_number",
        ),
    ],
)
def test_loader_rejects_invalid_slider_parameters(
    parameters: object,
    reason: str,
) -> None:
    _assert_refused(
        _raw(_payload(nodes=[_slider_node(parameters=parameters)])),
        reason,
    )


@pytest.mark.parametrize("label", ["", "   ", "a" * 65, "😀" * 65])
def test_loader_rejects_invalid_slider_label_bounds(label: str) -> None:
    _assert_refused(
        _raw(
            _payload(
                nodes=[
                    _slider_node(
                        parameters={
                            "label": label,
                            "minimum": 0,
                            "maximum": 10,
                            "initial": 5,
                        }
                    )
                ]
            )
        ),
        "invalid_slider_label",
    )


@pytest.mark.parametrize(
    "parameters",
    [
        {"label": "Value", "minimum": -1_000_001, "maximum": 10, "initial": 5},
        {"label": "Value", "minimum": 0, "maximum": 1_000_001, "initial": 5},
        {"label": "Value", "minimum": 0, "maximum": 10, "initial": 1_000_001},
        {"label": "Value", "minimum": 0, "maximum": 10**400, "initial": 5},
        {"label": "Value", "minimum": 6, "maximum": 10, "initial": 5},
        {"label": "Value", "minimum": 0, "maximum": 4, "initial": 5},
    ],
)
def test_loader_rejects_invalid_slider_number_bounds(
    parameters: dict[str, object],
) -> None:
    _assert_refused(
        _raw(_payload(nodes=[_slider_node(parameters=parameters)])),
        "invalid_slider_number",
    )


def test_loader_rejects_parameters_on_non_slider_primitive() -> None:
    node = _component_node()
    node["parameters"] = {"x": 1}
    _assert_refused(_raw(_payload(nodes=[node])), "invalid_parameters")


@pytest.mark.parametrize(
    ("edge_field", "value"),
    [
        ("from_node", 1),
        ("from_pin", True),
        ("to_node", None),
        ("to_pin", []),
    ],
)
def test_loader_rejects_non_string_edge_fields(
    edge_field: str,
    value: object,
) -> None:
    edge = _edge()
    edge[edge_field] = value
    _assert_refused(
        _raw(_payload(nodes=[_slider_node(), _component_node()], edges=[edge])),
        "invalid_edge_value",
    )


def test_response_schema_is_fresh_closed_provider_compatible_and_identity_free() -> None:
    first = semantic_graph.build_semantic_graph_response_schema()
    second = semantic_graph.build_semantic_graph_response_schema()

    assert first == second
    assert first is not second
    assert first["type"] == "object"
    assert first["additionalProperties"] is False
    assert first["required"] == ["schema", "nodes", "edges"]
    assert first["properties"]["schema"] == {
        "const": "rook.gh_semantic_graph:v1"
    }
    nodes = first["properties"]["nodes"]
    assert nodes == {
        "type": "array",
        "items": nodes["items"],
    }
    assert len(nodes["items"]["anyOf"]) == 5
    for node_shape in nodes["items"]["anyOf"]:
        assert node_shape["additionalProperties"] is False
        assert node_shape["required"] == ["id", "primitive", "parameters"]
        assert node_shape["properties"]["id"] == {"type": "string"}
        for parameter_shape in node_shape["properties"]["parameters"][
            "properties"
        ].values():
            assert parameter_shape in ({"type": "string"}, {"type": "number"})
    edges = first["properties"]["edges"]
    assert edges == {
        "type": "array",
        "items": edges["items"],
    }
    assert edges["items"]["additionalProperties"] is False
    assert edges["items"]["required"] == [
        "from_node",
        "from_pin",
        "to_node",
        "to_pin",
    ]
    assert all(
        field_schema == {"type": "string"}
        for field_schema in edges["items"]["properties"].values()
    )

    serialized = json.dumps(first, sort_keys=True)
    for unsupported in ('"oneOf"', '"pattern"', '"minLength"', '"maxLength"'):
        assert unsupported not in serialized
    for forbidden in (
        "guid",
        "index",
        "access",
        "layout",
        "epoch",
        '"T1"',
        '"C1"',
        "PlanGraph",
        "phyllotaxis",
        "square_grid_witness",
        "knowledge",
        "Worker",
        "expected_graph",
    ):
        assert forbidden not in serialized

    first["required"].append("forged")
    assert "forged" not in second["required"]


@pytest.mark.parametrize("invalid_identifier", ["!!slider!!", "slider\n"])
@pytest.mark.parametrize("field", ["node_id", "from_node", "to_node"])
def test_local_admission_still_rejects_ids_omitted_from_provider_schema(
    field: str,
    invalid_identifier: str,
) -> None:
    payload = _payload(
        nodes=[_slider_node(), _component_node()],
        edges=[_edge()],
    )
    if field == "node_id":
        payload["nodes"][0]["id"] = invalid_identifier
    else:
        payload["edges"][0][field] = invalid_identifier

    assert Draft202012Validator(
        semantic_graph.build_semantic_graph_response_schema()
    ).is_valid(payload)
    loaded = semantic_graph.load_semantic_graph(_raw(payload))
    if field == "node_id":
        assert loaded.admitted is False
        assert loaded.reason == "invalid_node_id"
        return
    assert loaded.admitted is True
    assert loaded.graph is not None
    compiled = compile_semantic_graph(loaded.graph)
    assert compiled.admitted is False
    assert compiled.reason == (
        "unknown_source_node" if field == "from_node" else "unknown_target_node"
    )


def test_slider_parameter_admission_follows_lowering_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slider = next(
        primitive
        for primitive in semantic_graph._PRIMITIVES
        if primitive.lowering_kind == "slider"
    )
    renamed = replace(slider, name="numeric_control")
    monkeypatch.setattr(
        semantic_graph,
        "_PRIMITIVES",
        tuple(
            renamed if primitive is slider else primitive
            for primitive in semantic_graph._PRIMITIVES
        ),
    )

    result = semantic_graph.load_semantic_graph(
        _raw(_payload(nodes=[_slider_node(primitive="numeric_control")]))
    )

    assert result.admitted is True
    assert result.graph is not None
    assert dict(result.graph.nodes[0].parameters) == {
        "initial": 5,
        "label": "Value",
        "maximum": 10,
        "minimum": 0,
    }


def test_slider_prompt_guidance_follows_lowering_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slider = next(
        primitive
        for primitive in semantic_graph._PRIMITIVES
        if primitive.lowering_kind == "slider"
    )
    renamed = replace(slider, name="numeric_control")
    monkeypatch.setattr(semantic_graph, "_PRIMITIVES", (renamed,))

    projection = semantic_graph.semantic_primitive_prompt_projection()

    assert projection[0]["primitive"] == "numeric_control"
    assert projection[0]["integer_input_compatibility"] == {
        "initial_must_be_integral": True,
        "minimum_initial": 1,
        "maximum_initial": 100,
    }


def test_semantic_prompt_projection_is_fresh_and_planner_facing_only() -> None:
    first = semantic_graph.semantic_primitive_prompt_projection()
    second = semantic_graph.semantic_primitive_prompt_projection()

    assert first == second
    assert first is not second
    assert tuple(item["primitive"] for item in first) == (
        "number_slider",
        "series",
        "construct_point",
        "polyline",
        "square_grid",
    )
    assert next(item for item in first if item["primitive"] == "polyline")[
        "inputs"
    ][0] == {
        "name": "vertices",
        "element_type": "Point",
        "connection_required": True,
        "max_connections": 1,
    }
    assert next(item for item in first if item["primitive"] == "construct_point")[
        "inputs"
    ][1] == {
        "name": "y",
        "element_type": "Number",
        "connection_required": False,
        "max_connections": 1,
    }
    assert next(item for item in first if item["primitive"] == "square_grid")[
        "outputs"
    ][1] == {"name": "points", "element_type": "Point"}
    slider = next(item for item in first if item["primitive"] == "number_slider")
    assert tuple(parameter["name"] for parameter in slider["parameters"]) == (
        "label",
        "minimum",
        "maximum",
        "initial",
    )
    assert slider["integer_input_compatibility"] == {
        "initial_must_be_integral": True,
        "minimum_initial": 1,
        "maximum_initial": 100,
    }

    serialized = json.dumps(first, sort_keys=True)
    for forbidden in (
        "guid",
        "index",
        "access",
        "gh_optional",
        "lowering_kind",
        "layout",
        "epoch",
        '"T1"',
        '"C1"',
        "PlanGraph",
        "phyllotaxis",
        "square_grid_witness",
        "knowledge",
        "Worker",
        "expected_graph",
    ):
        assert forbidden not in serialized
