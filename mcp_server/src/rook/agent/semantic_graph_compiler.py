from __future__ import annotations

import heapq
import json
from dataclasses import dataclass

from . import semantic_graph as _semantic_graph
from .semantic_graph import SemanticGraph, SemanticGraphEdge, SemanticGraphNode


_LAYOUT_ORIGIN_X = 100
_LAYOUT_ORIGIN_Y = 100
_LAYOUT_HORIZONTAL_SPACING = 240
_LAYOUT_VERTICAL_SPACING = 120
_LOWERING_KINDS = frozenset({"component_guid", "slider"})


@dataclass(frozen=True, slots=True)
class CanonicalSemanticGraph:
    nodes: tuple[SemanticGraphNode, ...]
    edges: tuple[SemanticGraphEdge, ...]
    json_bytes: bytes


@dataclass(frozen=True, slots=True)
class SemanticCreateInstruction:
    temp_id: str
    fields: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class EpochFreeEditPlan:
    canonical_graph: CanonicalSemanticGraph
    create_instructions: tuple[SemanticCreateInstruction, ...]
    connect: tuple[str, ...]
    semantic_node_to_temp_id: tuple[tuple[str, str], ...]
    semantic_edge_to_flow: tuple[
        tuple[tuple[str, str, str, str], str], ...
    ]


@dataclass(frozen=True, slots=True)
class SemanticGraphCompileResult:
    admitted: bool
    plan: EpochFreeEditPlan | None
    failure: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class UnresolvedCSharpLeaf:
    node_id: str
    goal: str
    interface: _semantic_graph.SemanticCSharpInterface

    def __post_init__(self) -> None:
        if type(self.node_id) is not str or not self.node_id:
            raise TypeError("Worker leaf node_id must be an exact nonblank string")
        if type(self.goal) is not str or not self.goal:
            raise TypeError("Worker leaf goal must be an exact nonblank string")
        if type(self.interface) is not _semantic_graph.SemanticCSharpInterface:
            raise TypeError("Worker leaf interface must be the exact interface type")


@dataclass(frozen=True, slots=True)
class WorkerLeafCrossEdge:
    source_node_id: str
    source_pin: str
    source_output_index: int
    target_node_id: str
    target_pin: str
    target_input_index: int

    def __post_init__(self) -> None:
        for value in (
            self.source_node_id,
            self.source_pin,
            self.target_node_id,
            self.target_pin,
        ):
            if type(value) is not str or not value:
                raise TypeError("Worker cross-edge names must be exact strings")
        if type(self.source_output_index) is not int or self.source_output_index < 0:
            raise TypeError("Worker source index must be an exact nonnegative integer")
        if type(self.target_input_index) is not int or self.target_input_index < 0:
            raise TypeError("Worker target index must be an exact nonnegative integer")


@dataclass(frozen=True, slots=True)
class SemanticGraphWorkerLeafPartition:
    deterministic_plan: EpochFreeEditPlan
    unresolved_leaf: UnresolvedCSharpLeaf | None
    cross_edge: WorkerLeafCrossEdge | None

    def __post_init__(self) -> None:
        if type(self.deterministic_plan) is not EpochFreeEditPlan:
            raise TypeError("deterministic_plan must be the exact plan type")
        if self.unresolved_leaf is not None and type(self.unresolved_leaf) is not UnresolvedCSharpLeaf:
            raise TypeError("unresolved_leaf must be the exact leaf type")
        if self.cross_edge is not None and type(self.cross_edge) is not WorkerLeafCrossEdge:
            raise TypeError("cross_edge must be the exact edge type")
        if (self.unresolved_leaf is None) != (self.cross_edge is None):
            raise TypeError("Worker leaf and cross-edge must be present together")


@dataclass(frozen=True, slots=True)
class SemanticGraphWorkerLeafPartitionCompileResult:
    admitted: bool
    partition: SemanticGraphWorkerLeafPartition | None
    failure: str | None
    reason: str

    def __post_init__(self) -> None:
        if type(self.admitted) is not bool:
            raise TypeError("admitted must be an exact boolean")
        if type(self.reason) is not str or not self.reason:
            raise TypeError("reason must be an exact nonblank string")
        if self.admitted:
            if type(self.partition) is not SemanticGraphWorkerLeafPartition:
                raise TypeError("admitted result requires an exact partition")
            if self.failure is not None or self.reason != "admitted":
                raise ValueError("admitted partition result fields disagree")
            return
        if self.partition is not None:
            raise ValueError("refused partition result cannot retain a partition")
        if type(self.failure) is not str or not self.failure:
            raise TypeError("refused partition result requires a failure")


def compile_semantic_graph(graph: SemanticGraph) -> SemanticGraphCompileResult:
    primitives = {primitive.name: primitive for primitive in _semantic_graph._PRIMITIVES}
    nodes = {node.id: node for node in graph.nodes}

    for node in graph.nodes:
        primitive = primitives.get(node.primitive)
        if primitive is None:
            return _refused("unknown_primitive")
        if primitive.lowering_kind not in _LOWERING_KINDS:
            raise RuntimeError(
                f"unknown lowering kind: {primitive.lowering_kind}"
            )

    connections: dict[tuple[str, str], int] = {}
    successors: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    predecessors: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    pin_pairs: dict[
        tuple[str, str, str, str],
        tuple[_semantic_graph._PrimitivePin, _semantic_graph._PrimitivePin],
    ] = {}

    for edge in graph.edges:
        source_node = nodes.get(edge.from_node)
        if source_node is None:
            return _refused("unknown_source_node")
        target_node = nodes.get(edge.to_node)
        if target_node is None:
            return _refused("unknown_target_node")
        if edge.from_node == edge.to_node:
            return _refused("self_edge")

        source_primitive = primitives[source_node.primitive]
        target_primitive = primitives[target_node.primitive]
        source_pin = _pin_by_name(source_primitive.outputs, edge.from_pin)
        if source_pin is None:
            return _refused("unknown_source_pin")
        target_pin = _pin_by_name(target_primitive.inputs, edge.to_pin)
        if target_pin is None:
            return _refused("unknown_target_pin")
        compatibility_failure = _compatibility_failure(
            source_node,
            source_primitive,
            source_pin,
            target_pin,
        )
        if compatibility_failure is not None:
            return _refused(compatibility_failure)

        target_key = (edge.to_node, edge.to_pin)
        next_count = connections.get(target_key, 0) + 1
        if (
            target_pin.max_connections is not None
            and next_count > target_pin.max_connections
        ):
            return _refused("too_many_input_connections")
        connections[target_key] = next_count

        successors[edge.from_node].add(edge.to_node)
        predecessors[edge.to_node].add(edge.from_node)
        pin_pairs[_edge_identity(edge)] = (source_pin, target_pin)

    for node in graph.nodes:
        primitive = primitives[node.primitive]
        for input_pin in primitive.inputs:
            if (
                input_pin.connection_required is True
                and connections.get((node.id, input_pin.name), 0) == 0
            ):
                return _refused("required_input_unconnected")

    depths = _topological_depths(nodes, successors, predecessors)
    if depths is None:
        return _refused("cycle_detected")

    canonical_nodes = tuple(sorted(graph.nodes, key=lambda node: node.id))
    canonical_edges = tuple(sorted(graph.edges, key=_edge_identity))
    canonical_graph = CanonicalSemanticGraph(
        nodes=canonical_nodes,
        edges=canonical_edges,
        json_bytes=_canonical_graph_json(canonical_nodes, canonical_edges),
    )


    node_to_temp_id = tuple(
        (node.id, f"T{index}")
        for index, node in enumerate(canonical_nodes, start=1)
    )
    temp_ids = dict(node_to_temp_id)
    positions = _layout_positions(depths)
    instructions = tuple(
        _lower_node(
            node,
            primitives[node.primitive],
            temp_ids[node.id],
            positions[node.id],
        )
        for node in canonical_nodes
    )

    semantic_edge_to_flow: list[
        tuple[tuple[str, str, str, str], str]
    ] = []
    for edge in canonical_edges:
        identity = _edge_identity(edge)
        source_pin, target_pin = pin_pairs[identity]
        flow = (
            f"{temp_ids[edge.from_node]}.O{source_pin.index}>"
            f"{temp_ids[edge.to_node]}.I{target_pin.index}"
        )
        semantic_edge_to_flow.append((identity, flow))

    edge_correlations = tuple(semantic_edge_to_flow)
    return SemanticGraphCompileResult(
        admitted=True,
        plan=EpochFreeEditPlan(
            canonical_graph=canonical_graph,
            create_instructions=instructions,
            connect=tuple(flow for _, flow in edge_correlations),
            semantic_node_to_temp_id=node_to_temp_id,
            semantic_edge_to_flow=edge_correlations,
        ),
        failure=None,
        reason="admitted",
    )


def materialize_gh_edit_request(
    plan: EpochFreeEditPlan,
    epoch: int,
) -> dict[str, object]:
    if type(epoch) is not int or epoch <= 0:
        raise ValueError("epoch must be an exact positive integer epoch")
    return {
        "epoch": epoch,
        "create": [
            _materialize_create(instruction)
            for instruction in plan.create_instructions
        ],
        "connect": list(plan.connect),
    }


def _refused(reason: str) -> SemanticGraphCompileResult:
    return SemanticGraphCompileResult(
        admitted=False,
        plan=None,
        failure="graph_admission",
        reason=reason,
    )


def _partition_refused(
    reason: str,
) -> SemanticGraphWorkerLeafPartitionCompileResult:
    return SemanticGraphWorkerLeafPartitionCompileResult(
        admitted=False,
        partition=None,
        failure="graph_admission",
        reason=reason,
    )


def _admitted_partition(
    plan: EpochFreeEditPlan,
    leaf: UnresolvedCSharpLeaf | None,
    cross_edge: WorkerLeafCrossEdge | None,
) -> SemanticGraphWorkerLeafPartitionCompileResult:
    return SemanticGraphWorkerLeafPartitionCompileResult(
        admitted=True,
        partition=SemanticGraphWorkerLeafPartition(
            deterministic_plan=plan,
            unresolved_leaf=leaf,
            cross_edge=cross_edge,
        ),
        failure=None,
        reason="admitted",
    )


def compile_semantic_graph_worker_leaf_partition(
    graph: SemanticGraph,
) -> SemanticGraphWorkerLeafPartitionCompileResult:
    worker_nodes = tuple(
        node for node in graph.nodes if node.primitive == "csharp_script"
    )
    if len(worker_nodes) > 1:
        return _partition_refused("multiple_worker_leaves")
    if not worker_nodes:
        deterministic = compile_semantic_graph(graph)
        if not deterministic.admitted:
            return _partition_refused(deterministic.reason)
        if deterministic.plan is None:
            raise RuntimeError("admitted deterministic compilation lacks a plan")
        return _admitted_partition(deterministic.plan, None, None)

    worker_node = worker_nodes[0]
    incoming = tuple(
        edge for edge in graph.edges if edge.to_node == worker_node.id
    )
    outgoing = tuple(
        edge for edge in graph.edges if edge.from_node == worker_node.id
    )
    if incoming:
        return _partition_refused("worker_leaf_has_incoming_edge")
    if len(outgoing) != 1:
        return _partition_refused("worker_leaf_requires_one_outgoing_edge")
    cross = outgoing[0]
    if cross.from_pin != "A":
        return _partition_refused("worker_leaf_source_pin_invalid")

    deterministic_nodes = tuple(
        node for node in graph.nodes if node.id != worker_node.id
    )
    target_node = next(
        (node for node in deterministic_nodes if node.id == cross.to_node),
        None,
    )
    if target_node is None:
        return _partition_refused("worker_leaf_target_invalid")
    primitives = {
        primitive.name: primitive for primitive in _semantic_graph._PRIMITIVES
    }
    target_primitive = primitives.get(target_node.primitive)
    if target_primitive is None:
        return _partition_refused("worker_leaf_target_invalid")
    target_pin = _pin_by_name(target_primitive.inputs, cross.to_pin)
    if target_pin is None:
        return _partition_refused("worker_leaf_target_pin_invalid")
    if target_pin.element_type != "Number":
        return _partition_refused("worker_leaf_target_type_invalid")

    occupancy = sum(
        1
        for edge in graph.edges
        if edge.to_node == cross.to_node and edge.to_pin == cross.to_pin
    )
    if (
        target_pin.max_connections is not None
        and occupancy > target_pin.max_connections
    ):
        return _partition_refused("too_many_input_connections")

    deterministic_edges = tuple(edge for edge in graph.edges if edge is not cross)
    deterministic_graph = SemanticGraph(
        schema=graph.schema,
        nodes=deterministic_nodes,
        edges=deterministic_edges,
    )
    deterministic = compile_semantic_graph(deterministic_graph)
    if not deterministic.admitted:
        return _partition_refused(deterministic.reason)
    if deterministic.plan is None:
        raise RuntimeError("admitted deterministic compilation lacks a plan")

    parameters = dict(worker_node.parameters)
    interface = parameters["interface"]
    if type(interface) is not _semantic_graph.SemanticCSharpInterface:
        raise RuntimeError("admitted Worker interface changed type")
    return _admitted_partition(
        deterministic.plan,
        UnresolvedCSharpLeaf(
            node_id=worker_node.id,
            goal=parameters["goal"],
            interface=interface,
        ),
        WorkerLeafCrossEdge(
            source_node_id=worker_node.id,
            source_pin="A",
            source_output_index=0,
            target_node_id=cross.to_node,
            target_pin=cross.to_pin,
            target_input_index=target_pin.index,
        ),
    )


def _pin_by_name(
    pins: tuple[_semantic_graph._PrimitivePin, ...],
    name: str,
) -> _semantic_graph._PrimitivePin | None:
    for pin in pins:
        if pin.name == name:
            return pin
    return None


def _compatibility_failure(
    source_node: SemanticGraphNode,
    source_primitive: _semantic_graph._Primitive,
    source_pin: _semantic_graph._PrimitivePin,
    target_pin: _semantic_graph._PrimitivePin,
) -> str | None:
    if source_pin.element_type == target_pin.element_type:
        return None
    if source_pin.element_type != "Number" or target_pin.element_type != "Integer":
        return "incompatible_element_types"
    if source_primitive.lowering_kind != "slider":
        return "incompatible_element_types"

    initial = dict(source_node.parameters)["initial"]
    if (
        type(initial) not in {int, float}
        or not float(initial).is_integer()
        or initial < _semantic_graph._MIN_INTEGER_INPUT_INITIAL
        or initial > _semantic_graph._MAX_INTEGER_INPUT_INITIAL
    ):
        return "invalid_integer_input_initial"
    return None


def _edge_identity(edge: SemanticGraphEdge) -> tuple[str, str, str, str]:
    return (edge.from_node, edge.from_pin, edge.to_node, edge.to_pin)


def _topological_depths(
    nodes: dict[str, SemanticGraphNode],
    successors: dict[str, set[str]],
    predecessors: dict[str, set[str]],
) -> dict[str, int] | None:
    remaining = {
        node_id: len(predecessors[node_id])
        for node_id in nodes
    }
    depths = {node_id: 0 for node_id in nodes}
    ready = [node_id for node_id, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    visited = 0

    while ready:
        node_id = heapq.heappop(ready)
        visited += 1
        for target_id in sorted(successors[node_id]):
            depths[target_id] = max(depths[target_id], depths[node_id] + 1)
            remaining[target_id] -= 1
            if remaining[target_id] == 0:
                heapq.heappush(ready, target_id)
    return depths if visited == len(nodes) else None


def _canonical_graph_json(
    nodes: tuple[SemanticGraphNode, ...],
    edges: tuple[SemanticGraphEdge, ...],
) -> bytes:
    payload = {
        "schema": _semantic_graph.SEMANTIC_GRAPH_SCHEMA,
        "nodes": [
            {
                "id": node.id,
                "primitive": node.primitive,
                "parameters": dict(node.parameters),
            }
            for node in nodes
        ],
        "edges": [
            {
                "from_node": edge.from_node,
                "from_pin": edge.from_pin,
                "to_node": edge.to_node,
                "to_pin": edge.to_pin,
            }
            for edge in edges
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _layout_positions(depths: dict[str, int]) -> dict[str, tuple[int, int]]:
    by_depth: dict[int, list[str]] = {}
    for node_id, depth in depths.items():
        by_depth.setdefault(depth, []).append(node_id)
    return {
        node_id: (
            _LAYOUT_ORIGIN_X + depth * _LAYOUT_HORIZONTAL_SPACING,
            _LAYOUT_ORIGIN_Y + index * _LAYOUT_VERTICAL_SPACING,
        )
        for depth, node_ids in by_depth.items()
        for index, node_id in enumerate(sorted(node_ids))
    }


def _lower_node(
    node: SemanticGraphNode,
    primitive: _semantic_graph._Primitive,
    temp_id: str,
    position: tuple[int, int],
) -> SemanticCreateInstruction:
    if primitive.lowering_kind == "component_guid":
        if type(primitive.component_guid) is not str or not primitive.component_guid:
            raise RuntimeError("component_guid lowering lacks a component GUID")
        fields: tuple[tuple[str, object], ...] = (
            ("guid", primitive.component_guid),
            ("pos", position),
        )
    elif primitive.lowering_kind == "slider":
        parameters = dict(node.parameters)
        fields = (
            ("type", "slider"),
            ("nick", parameters["label"]),
            ("min", parameters["minimum"]),
            ("max", parameters["maximum"]),
            ("value", parameters["initial"]),
            ("pos", position),
        )
    else:
        raise RuntimeError(f"unknown lowering kind: {primitive.lowering_kind}")
    return SemanticCreateInstruction(temp_id=temp_id, fields=fields)


def _materialize_create(
    instruction: SemanticCreateInstruction,
) -> dict[str, object]:
    result: dict[str, object] = {"temp_id": instruction.temp_id}
    for name, value in instruction.fields:
        result[name] = list(value) if name == "pos" else value
    return result
