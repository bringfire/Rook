from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any


SEMANTIC_GRAPH_SCHEMA = "rook.gh_semantic_graph:v1"

_MAX_RESPONSE_UTF8_BYTES = 65_536
_MAX_NODES = 16
_MAX_EDGES = 24
_MAX_SLIDER_LABEL_CHARACTERS = 64
_MAX_SLIDER_LABEL_UTF8_BYTES = 256
_MIN_SLIDER_VALUE = -1_000_000
_MAX_SLIDER_VALUE = 1_000_000
_MIN_INTEGER_INPUT_INITIAL = 1
_MAX_INTEGER_INPUT_INITIAL = 100
_NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


@dataclass(frozen=True, slots=True)
class SemanticGraphNode:
    id: str
    primitive: str
    parameters: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class SemanticGraphEdge:
    from_node: str
    from_pin: str
    to_node: str
    to_pin: str


@dataclass(frozen=True, slots=True)
class SemanticGraph:
    schema: str
    nodes: tuple[SemanticGraphNode, ...]
    edges: tuple[SemanticGraphEdge, ...]


@dataclass(frozen=True, slots=True)
class SemanticGraphLoadResult:
    admitted: bool
    graph: SemanticGraph | None
    failure: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class _PrimitivePin:
    name: str
    index: int
    element_type: str
    access: str
    gh_optional: bool | None
    max_connections: int | None
    connection_required: bool | None


@dataclass(frozen=True, slots=True)
class _PrimitiveParameter:
    name: str
    value_kind: str
    minimum: float | None = None
    maximum: float | None = None
    max_characters: int | None = None
    max_utf8_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class _Primitive:
    name: str
    lowering_kind: str
    component_guid: str | None
    snapshot_type: str | None
    inputs: tuple[_PrimitivePin, ...]
    outputs: tuple[_PrimitivePin, ...]
    parameters: tuple[_PrimitiveParameter, ...]


def _input_pin(
    name: str,
    index: int,
    element_type: str,
    access: str,
    *,
    connection_required: bool = False,
) -> _PrimitivePin:
    return _PrimitivePin(
        name=name,
        index=index,
        element_type=element_type,
        access=access,
        gh_optional=False,
        max_connections=1,
        connection_required=connection_required,
    )


def _output_pin(
    name: str,
    index: int,
    element_type: str,
    access: str,
    *,
    gh_optional: bool | None = False,
) -> _PrimitivePin:
    return _PrimitivePin(
        name=name,
        index=index,
        element_type=element_type,
        access=access,
        gh_optional=gh_optional,
        max_connections=None,
        connection_required=None,
    )


_PRIMITIVES: tuple[_Primitive, ...] = (
    _Primitive(
        name="number_slider",
        lowering_kind="slider",
        component_guid=None,
        snapshot_type="NumberSlider",
        inputs=(),
        outputs=(
            _output_pin(
                "value",
                0,
                "Number",
                "item",
                gh_optional=None,
            ),
        ),
        parameters=(
            _PrimitiveParameter(
                name="label",
                value_kind="string",
                max_characters=_MAX_SLIDER_LABEL_CHARACTERS,
                max_utf8_bytes=_MAX_SLIDER_LABEL_UTF8_BYTES,
            ),
            _PrimitiveParameter(
                name="minimum",
                value_kind="number",
                minimum=_MIN_SLIDER_VALUE,
                maximum=_MAX_SLIDER_VALUE,
            ),
            _PrimitiveParameter(
                name="maximum",
                value_kind="number",
                minimum=_MIN_SLIDER_VALUE,
                maximum=_MAX_SLIDER_VALUE,
            ),
            _PrimitiveParameter(
                name="initial",
                value_kind="number",
                minimum=_MIN_SLIDER_VALUE,
                maximum=_MAX_SLIDER_VALUE,
            ),
        ),
    ),
    _Primitive(
        name="series",
        lowering_kind="component_guid",
        component_guid="e64c5fb1-845c-4ab1-8911-5f338516ba67",
        snapshot_type=None,
        inputs=(
            _input_pin("start", 0, "Number", "item"),
            _input_pin("step", 1, "Number", "item"),
            _input_pin("count", 2, "Integer", "item"),
        ),
        outputs=(_output_pin("values", 0, "Number", "list"),),
        parameters=(),
    ),
    _Primitive(
        name="construct_point",
        lowering_kind="component_guid",
        component_guid="3581f42a-9592-4549-bd6b-1c0fc39d067b",
        snapshot_type=None,
        inputs=(
            _input_pin("x", 0, "Number", "item"),
            _input_pin("y", 1, "Number", "item"),
            _input_pin("z", 2, "Number", "item"),
        ),
        outputs=(_output_pin("point", 0, "Point", "item"),),
        parameters=(),
    ),
    _Primitive(
        name="polyline",
        lowering_kind="component_guid",
        component_guid="71b5b089-500a-4ea6-81c5-2f960441a0e8",
        snapshot_type=None,
        inputs=(
            _input_pin(
                "vertices",
                0,
                "Point",
                "list",
                connection_required=True,
            ),
            _input_pin("closed", 1, "Boolean", "item"),
        ),
        outputs=(_output_pin("curve", 0, "Curve", "item"),),
        parameters=(),
    ),
    _Primitive(
        name="square_grid",
        lowering_kind="component_guid",
        component_guid="717a1e25-a075-4530-bc80-d43ecc2500d9",
        snapshot_type=None,
        inputs=(
            _input_pin("plane", 0, "Plane", "item"),
            _input_pin("cell_size", 1, "Number", "item"),
            _input_pin("extent_x", 2, "Integer", "item"),
            _input_pin("extent_y", 3, "Integer", "item"),
        ),
        outputs=(
            _output_pin("cells", 0, "Rectangle", "item"),
            _output_pin("points", 1, "Point", "tree"),
        ),
        parameters=(),
    ),
)


class _DuplicateKeyError(ValueError):
    pass


class _NonFiniteNumberError(ValueError):
    pass


class _AdmissionError(ValueError):
    def __init__(self, failure: str, reason: str) -> None:
        super().__init__(reason)
        self.failure = failure
        self.reason = reason


def load_semantic_graph(raw_response: str) -> SemanticGraphLoadResult:
    if type(raw_response) is not str:
        return _refused("response", "response_not_string")
    try:
        encoded = raw_response.encode("utf-8")
    except UnicodeEncodeError:
        return _refused("response", "response_not_utf8")
    if len(encoded) > _MAX_RESPONSE_UTF8_BYTES:
        return _refused("response", "response_too_large")

    try:
        decoded = _decode_one_json_value(raw_response)
    except _DuplicateKeyError:
        return _refused("response", "response_duplicate_key")
    except _NonFiniteNumberError:
        return _refused("response", "response_nonfinite_number")
    except _AdmissionError as exc:
        return _refused(exc.failure, exc.reason)
    except (json.JSONDecodeError, RecursionError, ValueError):
        return _refused("response", "response_invalid_json")

    if type(decoded) is not dict:
        return _refused("response", "response_not_object")
    try:
        graph = _load_graph_object(decoded)
    except _AdmissionError as exc:
        return _refused(exc.failure, exc.reason)
    return SemanticGraphLoadResult(
        admitted=True,
        graph=graph,
        failure=None,
        reason="admitted",
    )


def _decode_one_json_value(raw_response: str) -> object:
    decoder = json.JSONDecoder(
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
        parse_float=_parse_finite_float,
    )
    start = 0
    while start < len(raw_response) and raw_response[start] in " \t\r\n":
        start += 1
    decoded, end = decoder.raw_decode(raw_response, start)
    if any(character not in " \t\r\n" for character in raw_response[end:]):
        raise _AdmissionError("response", "response_trailing_content")
    return decoded


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise _NonFiniteNumberError(value)


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _NonFiniteNumberError(value)
    return parsed


def _load_graph_object(decoded: dict[str, Any]) -> SemanticGraph:
    if set(decoded) != {"schema", "nodes", "edges"}:
        raise _AdmissionError("graph", "invalid_root_fields")
    if type(decoded["schema"]) is not str or decoded["schema"] != SEMANTIC_GRAPH_SCHEMA:
        raise _AdmissionError("graph", "invalid_schema")
    nodes_value = decoded["nodes"]
    if type(nodes_value) is not list:
        raise _AdmissionError("graph", "invalid_nodes")
    if not 1 <= len(nodes_value) <= _MAX_NODES:
        raise _AdmissionError("graph", "invalid_node_count")
    edges_value = decoded["edges"]
    if type(edges_value) is not list:
        raise _AdmissionError("graph", "invalid_edges")
    if len(edges_value) > _MAX_EDGES:
        raise _AdmissionError("graph", "invalid_edge_count")

    nodes: list[SemanticGraphNode] = []
    node_ids: set[str] = set()
    for value in nodes_value:
        node = _load_node(value)
        if node.id in node_ids:
            raise _AdmissionError("node", "duplicate_node_id")
        node_ids.add(node.id)
        nodes.append(node)

    edges: list[SemanticGraphEdge] = []
    edge_values: set[tuple[str, str, str, str]] = set()
    for value in edges_value:
        edge = _load_edge(value)
        identity = (edge.from_node, edge.from_pin, edge.to_node, edge.to_pin)
        if identity in edge_values:
            raise _AdmissionError("edge", "duplicate_edge")
        edge_values.add(identity)
        edges.append(edge)
    return SemanticGraph(
        schema=SEMANTIC_GRAPH_SCHEMA,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def _load_node(value: object) -> SemanticGraphNode:
    if type(value) is not dict or set(value) != {"id", "primitive", "parameters"}:
        raise _AdmissionError("node", "invalid_node_fields")
    node_id = value["id"]
    if type(node_id) is not str or _NODE_ID_PATTERN.fullmatch(node_id) is None:
        raise _AdmissionError("node", "invalid_node_id")
    primitive_name = value["primitive"]
    primitive = _find_primitive(primitive_name)
    parameters = _load_parameters(primitive, value["parameters"])
    return SemanticGraphNode(
        id=node_id,
        primitive=primitive.name,
        parameters=parameters,
    )


def _find_primitive(value: object) -> _Primitive:
    if type(value) is str:
        for primitive in _PRIMITIVES:
            if primitive.name == value:
                return primitive
    raise _AdmissionError("node", "unknown_primitive")


def _load_parameters(
    primitive: _Primitive,
    value: object,
) -> tuple[tuple[str, object], ...]:
    if type(value) is not dict:
        raise _AdmissionError("parameters", "invalid_parameters")
    expected_names = {parameter.name for parameter in primitive.parameters}
    if set(value) != expected_names:
        raise _AdmissionError("parameters", "invalid_parameters")
    if primitive.lowering_kind != "slider":
        return ()

    label = value["label"]
    if type(label) is not str or not label.strip() or len(label) > _MAX_SLIDER_LABEL_CHARACTERS:
        raise _AdmissionError("parameters", "invalid_slider_label")
    try:
        label_bytes = label.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _AdmissionError("parameters", "invalid_slider_label") from exc
    if len(label_bytes) > _MAX_SLIDER_LABEL_UTF8_BYTES:
        raise _AdmissionError("parameters", "invalid_slider_label")

    numbers: dict[str, int | float] = {}
    for name in ("minimum", "maximum", "initial"):
        number = value[name]
        if type(number) not in {int, float}:
            raise _AdmissionError("parameters", "invalid_slider_number")
        if type(number) is float and not math.isfinite(number):
            raise _AdmissionError("parameters", "invalid_slider_number")
        if number < _MIN_SLIDER_VALUE or number > _MAX_SLIDER_VALUE:
            raise _AdmissionError("parameters", "invalid_slider_number")
        numbers[name] = number
    if not numbers["minimum"] <= numbers["initial"] <= numbers["maximum"]:
        raise _AdmissionError("parameters", "invalid_slider_number")
    return tuple(sorted(value.items()))


def _load_edge(value: object) -> SemanticGraphEdge:
    expected = {"from_node", "from_pin", "to_node", "to_pin"}
    if type(value) is not dict or set(value) != expected:
        raise _AdmissionError("edge", "invalid_edge_fields")
    if any(type(value[name]) is not str or not value[name] for name in expected):
        raise _AdmissionError("edge", "invalid_edge_value")
    return SemanticGraphEdge(
        from_node=value["from_node"],
        from_pin=value["from_pin"],
        to_node=value["to_node"],
        to_pin=value["to_pin"],
    )


def _refused(failure: str, reason: str) -> SemanticGraphLoadResult:
    return SemanticGraphLoadResult(
        admitted=False,
        graph=None,
        failure=failure,
        reason=reason,
    )


def build_semantic_graph_response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema", "nodes", "edges"],
        "properties": {
            "schema": {"const": SEMANTIC_GRAPH_SCHEMA},
            "nodes": {
                "type": "array",
                "minItems": 1,
                "maxItems": _MAX_NODES,
                "items": {
                    "oneOf": [_node_schema(primitive) for primitive in _PRIMITIVES]
                },
            },
            "edges": {
                "type": "array",
                "minItems": 0,
                "maxItems": _MAX_EDGES,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["from_node", "from_pin", "to_node", "to_pin"],
                    "properties": {
                        "from_node": {
                            "type": "string",
                            "pattern": _NODE_ID_PATTERN.pattern,
                        },
                        "from_pin": {"type": "string", "minLength": 1},
                        "to_node": {
                            "type": "string",
                            "pattern": _NODE_ID_PATTERN.pattern,
                        },
                        "to_pin": {"type": "string", "minLength": 1},
                    },
                },
            },
        },
    }


def _node_schema(primitive: _Primitive) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "primitive", "parameters"],
        "properties": {
            "id": {"type": "string", "pattern": _NODE_ID_PATTERN.pattern},
            "primitive": {"const": primitive.name},
            "parameters": _parameter_schema(primitive),
        },
    }


def _parameter_schema(primitive: _Primitive) -> dict[str, object]:
    properties: dict[str, object] = {}
    for parameter in primitive.parameters:
        if parameter.value_kind == "string":
            properties[parameter.name] = {
                "type": "string",
                "minLength": 1,
                "maxLength": parameter.max_characters,
            }
        else:
            properties[parameter.name] = {
                "type": "number",
                "minimum": parameter.minimum,
                "maximum": parameter.maximum,
            }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [parameter.name for parameter in primitive.parameters],
        "properties": properties,
    }


def semantic_primitive_prompt_projection() -> tuple[dict[str, object], ...]:
    projection: list[dict[str, object]] = []
    for primitive in _PRIMITIVES:
        entry: dict[str, object] = {
            "primitive": primitive.name,
            "inputs": tuple(
                {
                    "name": pin.name,
                    "element_type": pin.element_type,
                    "connection_required": pin.connection_required,
                    "max_connections": pin.max_connections,
                }
                for pin in primitive.inputs
            ),
            "outputs": tuple(
                {"name": pin.name, "element_type": pin.element_type}
                for pin in primitive.outputs
            ),
            "parameters": tuple(
                _parameter_prompt_projection(parameter)
                for parameter in primitive.parameters
            ),
        }
        if primitive.lowering_kind == "slider":
            entry["integer_input_compatibility"] = {
                "initial_must_be_integral": True,
                "minimum_initial": _MIN_INTEGER_INPUT_INITIAL,
                "maximum_initial": _MAX_INTEGER_INPUT_INITIAL,
            }
        projection.append(entry)
    return tuple(projection)


def _parameter_prompt_projection(
    parameter: _PrimitiveParameter,
) -> dict[str, object]:
    result: dict[str, object] = {
        "name": parameter.name,
        "value_kind": parameter.value_kind,
        "required": True,
    }
    if parameter.value_kind == "string":
        result.update(
            {
                "nonblank": True,
                "max_characters": parameter.max_characters,
                "max_utf8_bytes": parameter.max_utf8_bytes,
            }
        )
    else:
        result.update(
            {
                "minimum": parameter.minimum,
                "maximum": parameter.maximum,
            }
        )
    return result
