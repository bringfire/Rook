"""LM4W declarative workflow contract compiler.

This module validates a Python contract and compiles it into the existing
PlanGraph scaffold objects. It prepares artifacts only; callers decide when to
run a compiled scaffold.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, TypeAlias, get_args

from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    Step,
    VerifierStep,
)
from rook.learning.plan_graph import OutcomeStatus, PlanGraph, initialize_graph
from rook.learning.plan_graph_templates import select_template


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | Mapping[str, "JsonValue"] | Sequence["JsonValue"]
WorkflowStepSpec: TypeAlias = "ProducerStepSpec | VerifierStepSpec | BindStepSpec"

_OUTCOME_STATUSES = frozenset(get_args(OutcomeStatus))


@dataclass(frozen=True)
class WorkflowTemplateRef:
    descriptor: Mapping[str, str]
    expected_template_id: str


@dataclass(frozen=True)
class InitialNodeParams:
    node_id: str
    execution_params: Mapping[str, Any]


@dataclass(frozen=True)
class ProducerStepSpec:
    node_id: str


@dataclass(frozen=True)
class VerifierStepSpec:
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None = None


@dataclass(frozen=True)
class BindStepSpec:
    node_id: str
    base_params: Mapping[str, Any]
    bindings: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class WorkflowNodeRule:
    node_id: str
    steps_by_seen_count: tuple[WorkflowStepSpec, ...]


@dataclass(frozen=True)
class ExpectedNodeRef:
    node_id: str
    execution_ref: str


@dataclass(frozen=True)
class RookWorkflowContract:
    workflow_id: str
    template: WorkflowTemplateRef
    initial_params: tuple[InitialNodeParams, ...]
    rules: tuple[WorkflowNodeRule, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[ExpectedNodeRef, ...]
    max_steps: int
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CompiledWorkflowScaffold:
    workflow_id: str
    graph: PlanGraph
    provider: CatalogCurrentStepProvider
    max_steps: int
    metadata: Mapping[str, Any]
    rules: tuple[NodeStepRule, ...]
    steps: tuple[Step, ...]


class _ImmutableJsonMapping(Mapping):
    def __init__(self, items: Mapping[str, Any]) -> None:
        self._items = MappingProxyType(dict(items))

    def __getitem__(self, key: str) -> Any:
        return self._items[key]

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return False

    def __repr__(self) -> str:
        return repr(dict(self._items))


def compile_workflow_contract(contract: RookWorkflowContract) -> CompiledWorkflowScaffold:
    """Compile a declarative contract into provider-ready workflow scaffold data."""
    workflow_id = _require_non_empty_str(contract.workflow_id, "workflow_id")
    max_steps = _validate_max_steps(contract.max_steps)
    metadata = _immutable_json_snapshot(contract.metadata or {})

    descriptor = _snapshot_descriptor(contract.template.descriptor)
    expected_template_id = _require_non_empty_str(
        contract.template.expected_template_id,
        "WorkflowTemplateRef.expected_template_id",
    )
    selection = select_template(descriptor)
    if selection.selected_template_id != expected_template_id:
        raise ValueError(
            "selected template id does not match expected template id: "
            f"{selection.selected_template_id!r} != {expected_template_id!r}"
        )
    if selection.graph is None:
        raise ValueError("selected template did not provide a graph")

    graph = initialize_graph(selection.graph)
    _validate_expected_refs(graph, contract.expected_refs)
    _stage_initial_params(graph, contract.initial_params)
    rules, steps = _compile_rules(graph, contract.rules)
    terminal_node_ids = _validate_terminal_node_ids(
        graph,
        contract.terminal_node_ids,
        {rule.node_id for rule in rules},
    )
    provider = CatalogCurrentStepProvider(
        rules,
        terminal_node_ids=frozenset(terminal_node_ids),
    )

    return CompiledWorkflowScaffold(
        workflow_id=workflow_id,
        graph=graph,
        provider=provider,
        max_steps=max_steps,
        metadata=metadata,
        rules=rules,
        steps=steps,
    )


def _validate_max_steps(max_steps: Any) -> int:
    if isinstance(max_steps, bool) or not isinstance(max_steps, int):
        raise TypeError("max_steps must be an int")
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    return max_steps


def _require_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _snapshot_descriptor(descriptor: Any) -> dict[str, str]:
    if not isinstance(descriptor, Mapping):
        raise TypeError("WorkflowTemplateRef.descriptor must be a mapping")
    snap: dict[str, str] = {}
    for key, value in descriptor.items():
        if not isinstance(key, str):
            raise TypeError("WorkflowTemplateRef.descriptor keys must be strings")
        if not isinstance(value, str):
            raise TypeError("WorkflowTemplateRef.descriptor values must be strings")
        snap[key] = value
    return snap


def _immutable_json_snapshot(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _ImmutableJsonMapping(
            {key: _immutable_json_snapshot(item) for key, item in _mapping_items(value)}
        )
    if _is_sequence(value):
        return tuple(_immutable_json_snapshot(item) for item in value)
    if _is_json_scalar(value):
        return value
    raise TypeError(f"value is not JSON-safe: {type(value).__name__}")


def _plain_json_tree(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_json_tree(item) for key, item in _mapping_items(value)}
    if _is_sequence(value):
        return tuple(_plain_json_tree(item) for item in value)
    if _is_json_scalar(value):
        return value
    raise TypeError(f"value is not JSON-safe: {type(value).__name__}")


def _mapping_items(value: Mapping) -> tuple[tuple[str, Any], ...]:
    items: list[tuple[str, Any]] = []
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("JSON mapping keys must be strings")
        items.append((key, item))
    return tuple(items)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _stage_initial_params(
    graph: PlanGraph,
    initial_params: tuple[InitialNodeParams, ...],
) -> None:
    seen: set[str] = set()
    for entry in tuple(initial_params):
        if not isinstance(entry, InitialNodeParams):
            raise TypeError("initial_params entries must be InitialNodeParams")
        node_id = _require_non_empty_str(entry.node_id, "InitialNodeParams.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate InitialNodeParams.node_id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown initial-param node: {node_id!r}")
        if not isinstance(entry.execution_params, Mapping):
            raise TypeError("InitialNodeParams.execution_params must be a mapping")
        graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = _plain_json_tree(
            entry.execution_params
        )


def _compile_rules(
    graph: PlanGraph,
    rules: tuple[WorkflowNodeRule, ...],
) -> tuple[tuple[NodeStepRule, ...], tuple[Step, ...]]:
    seen: set[str] = set()
    compiled_rules: list[NodeStepRule] = []
    compiled_steps: list[Step] = []
    for rule in tuple(rules):
        if not isinstance(rule, WorkflowNodeRule):
            raise TypeError("rules entries must be WorkflowNodeRule")
        node_id = _require_non_empty_str(rule.node_id, "WorkflowNodeRule.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate WorkflowNodeRule.node_id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown workflow rule node: {node_id!r}")
        steps_by_seen_count = tuple(rule.steps_by_seen_count)
        if not steps_by_seen_count:
            raise ValueError(
                "WorkflowNodeRule.steps_by_seen_count must be non-empty for "
                f"{node_id!r}"
            )
        steps = tuple(
            _compile_step_spec(graph, node_id, spec)
            for spec in steps_by_seen_count
        )
        compiled_rules.append(NodeStepRule(node_id, steps))
        compiled_steps.extend(steps)
    return tuple(compiled_rules), tuple(compiled_steps)


def _compile_step_spec(
    graph: PlanGraph,
    rule_node_id: str,
    spec: WorkflowStepSpec,
) -> Step:
    if isinstance(spec, ProducerStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "ProducerStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(
                f"ProducerStepSpec for {rule_node_id!r} targets {node_id!r}"
            )
        return ProducerStep(node_id)

    if isinstance(spec, VerifierStepSpec):
        verifier_node_id = _require_non_empty_str(
            spec.verifier_node_id,
            "VerifierStepSpec.verifier_node_id",
        )
        if verifier_node_id != rule_node_id:
            raise ValueError(
                f"VerifierStepSpec for {rule_node_id!r} targets {verifier_node_id!r}"
            )
        source_node_id = _require_non_empty_str(
            spec.source_node_id,
            "VerifierStepSpec.source_node_id",
        )
        if source_node_id not in graph.nodes:
            raise ValueError(f"unknown verifier source node: {source_node_id!r}")
        if (
            spec.expected_outcome is not None
            and spec.expected_outcome not in _OUTCOME_STATUSES
        ):
            raise ValueError(
                "invalid VerifierStepSpec.expected_outcome: "
                f"{spec.expected_outcome!r}"
            )
        return VerifierStep(
            verifier_node_id,
            source_node_id,
            expected_outcome=spec.expected_outcome,
        )

    if isinstance(spec, BindStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "BindStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(f"BindStepSpec for {rule_node_id!r} targets {node_id!r}")
        if not isinstance(spec.base_params, Mapping):
            raise TypeError("BindStepSpec.base_params must be a mapping")
        base_params = _immutable_json_snapshot(spec.base_params)
        bindings = _compile_bindings(spec.bindings)
        return BindStep(node_id, base_params, bindings)

    raise TypeError("WorkflowNodeRule.steps_by_seen_count contains a non-step spec")


def _compile_bindings(bindings: Any) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(bindings, Mapping):
        raise TypeError("BindStepSpec.bindings must be a mapping")
    compiled: dict[str, tuple[str, ...]] = {}
    for param_key, path in bindings.items():
        if not isinstance(param_key, str) or not param_key:
            raise ValueError("binding param keys must be non-empty strings")
        if not isinstance(path, (list, tuple)) or not path:
            raise ValueError(f"binding path for {param_key!r} must be non-empty")
        path_tuple = tuple(path)
        if any(not isinstance(part, str) or not part for part in path_tuple):
            raise ValueError(f"binding path for {param_key!r} must contain strings")
        compiled[param_key] = path_tuple
    return _ImmutableJsonMapping(compiled)


def _validate_terminal_node_ids(
    graph: PlanGraph,
    terminal_node_ids: tuple[str, ...],
    rule_node_ids: set[str],
) -> tuple[str, ...]:
    terminal_ids = tuple(terminal_node_ids)
    if not terminal_ids:
        raise ValueError("terminal_node_ids must contain at least one node")
    seen: set[str] = set()
    for node_id in terminal_ids:
        node_id = _require_non_empty_str(node_id, "terminal_node_ids")
        if node_id in seen:
            raise ValueError(f"duplicate terminal node id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown terminal node id: {node_id!r}")
        if node_id in rule_node_ids:
            raise ValueError(
                f"terminal node id must not also have a rule: {node_id!r}"
            )
        if not graph.nodes[node_id].is_terminal:
            raise ValueError(f"declared terminal node is not terminal: {node_id!r}")
    return terminal_ids


def _validate_expected_refs(
    graph: PlanGraph,
    expected_refs: tuple[ExpectedNodeRef, ...],
) -> None:
    seen: set[str] = set()
    for expected in tuple(expected_refs):
        if not isinstance(expected, ExpectedNodeRef):
            raise TypeError("expected_refs entries must be ExpectedNodeRef")
        node_id = _require_non_empty_str(expected.node_id, "ExpectedNodeRef.node_id")
        execution_ref = _require_non_empty_str(
            expected.execution_ref,
            "ExpectedNodeRef.execution_ref",
        )
        if node_id in seen:
            raise ValueError(f"duplicate ExpectedNodeRef.node_id: {node_id!r}")
        seen.add(node_id)
        if node_id not in graph.nodes:
            raise ValueError(f"unknown expected-ref node: {node_id!r}")
        actual_ref = graph.nodes[node_id].execution_ref
        if actual_ref != execution_ref:
            raise ValueError(
                f"execution_ref mismatch for {node_id!r}: "
                f"expected {execution_ref!r}, got {actual_ref!r}"
            )
