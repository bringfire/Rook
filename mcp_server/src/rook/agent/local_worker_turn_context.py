"""LM5A local-worker turn context builder.

Packages an LM4 compiled scaffold, current graph snapshot, stream history,
caller-pushed knowledge, and allowed action descriptors into a frozen
worker-facing summary. This module does not select, map, execute, stream,
compile, load workflow payloads, call models, or expose raw runtime objects.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any

from rook.agent.plan_graph_current_step_runner import CurrentStepRecord
from rook.agent.plan_graph_current_step_stream import EnvelopeSupplyRecord
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import CompiledWorkflowScaffold
from rook.learning.plan_graph import PlanGraph
from rook.learning.plan_graph_projection import projection_role_for_node

__all__ = (
    "LocalWorkerTurnContext",
    "WorkerWorkflowSummary",
    "WorkerGraphSummary",
    "WorkerNodeSummary",
    "WorkerHistorySummary",
    "WorkerStepTraceSummary",
    "WorkerSupplyTraceSummary",
    "WorkerKnowledgePacket",
    "WorkerAllowedAction",
    "build_local_worker_turn_context",
)


@dataclass(frozen=True)
class WorkerWorkflowSummary:
    workflow_id: str
    contract_schema: str
    contract_fingerprint: str
    compiler_id: str
    provider_id: str
    selected_template_id: str
    max_steps: int

    def __post_init__(self) -> None:
        _require_non_empty_str(self.workflow_id, "workflow_id")
        _require_non_empty_str(self.contract_schema, "contract_schema")
        _require_non_empty_str(self.contract_fingerprint, "contract_fingerprint")
        _require_non_empty_str(self.compiler_id, "compiler_id")
        _require_non_empty_str(self.provider_id, "provider_id")
        _require_non_empty_str(self.selected_template_id, "selected_template_id")
        _require_positive_int(self.max_steps, "max_steps")


@dataclass(frozen=True)
class WorkerGraphSummary:
    node_count: int
    node_ids: tuple[str, ...]
    ready_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]
    status_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.node_count, "node_count")
        object.__setattr__(
            self,
            "node_ids",
            _freeze_str_tuple(self.node_ids, "node_ids"),
        )
        object.__setattr__(
            self,
            "ready_node_ids",
            _freeze_str_tuple(self.ready_node_ids, "ready_node_ids"),
        )
        object.__setattr__(
            self,
            "terminal_node_ids",
            _freeze_str_tuple(self.terminal_node_ids, "terminal_node_ids"),
        )
        object.__setattr__(
            self,
            "status_counts",
            _freeze_count_mapping(self.status_counts, "status_counts"),
        )


@dataclass(frozen=True)
class WorkerNodeSummary:
    node_id: str
    intent: str
    role: str | None
    status: str
    execution_ref: str | None
    is_terminal: bool
    has_execution_params: bool
    memory_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.node_id, "node_id")
        _require_str(self.intent, "intent")
        _require_optional_str(self.role, "role")
        _require_str(self.status, "status")
        _require_optional_str(self.execution_ref, "execution_ref")
        _require_bool(self.is_terminal, "is_terminal")
        _require_bool(self.has_execution_params, "has_execution_params")
        object.__setattr__(
            self,
            "memory_keys",
            _freeze_str_tuple(self.memory_keys, "memory_keys"),
        )


@dataclass(frozen=True)
class WorkerStepTraceSummary:
    accepted_node_id: str | None
    execution_kind: str | None
    ran: bool
    failure: str | None

    def __post_init__(self) -> None:
        _require_optional_str(self.accepted_node_id, "accepted_node_id")
        _require_optional_str(self.execution_kind, "execution_kind")
        _require_bool(self.ran, "ran")
        _require_optional_str(self.failure, "failure")


@dataclass(frozen=True)
class WorkerSupplyTraceSummary:
    decision: str | None
    reason: str | None
    selected_node_id: str | None
    has_envelope: bool

    def __post_init__(self) -> None:
        _require_optional_str(self.decision, "decision")
        _require_optional_str(self.reason, "reason")
        _require_optional_str(self.selected_node_id, "selected_node_id")
        _require_bool(self.has_envelope, "has_envelope")


@dataclass(frozen=True)
class WorkerHistorySummary:
    current_step_count: int
    supply_count: int
    last_accepted_node_id: str | None
    last_execution_kind: str | None
    last_stop_reason: str | None
    recent_steps: tuple[WorkerStepTraceSummary, ...]
    recent_supplies: tuple[WorkerSupplyTraceSummary, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.current_step_count, "current_step_count")
        _require_non_negative_int(self.supply_count, "supply_count")
        _require_optional_str(self.last_accepted_node_id, "last_accepted_node_id")
        _require_optional_str(self.last_execution_kind, "last_execution_kind")
        _require_optional_str(self.last_stop_reason, "last_stop_reason")
        object.__setattr__(
            self,
            "recent_steps",
            _freeze_instance_tuple(
                self.recent_steps,
                WorkerStepTraceSummary,
                "recent_steps",
            ),
        )
        object.__setattr__(
            self,
            "recent_supplies",
            _freeze_instance_tuple(
                self.recent_supplies,
                WorkerSupplyTraceSummary,
                "recent_supplies",
            ),
        )


@dataclass(frozen=True)
class WorkerKnowledgePacket:
    packet_id: str
    kind: str
    title: str | None
    content: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.packet_id, "packet_id")
        _require_non_empty_str(self.kind, "kind")
        _require_optional_str(self.title, "title")
        object.__setattr__(
            self,
            "content",
            _freeze_json_mapping(self.content, "content"),
        )


@dataclass(frozen=True)
class WorkerAllowedAction:
    action_id: str
    kind: str
    description: str
    input_schema: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.action_id, "action_id")
        _require_non_empty_str(self.kind, "kind")
        _require_non_empty_str(self.description, "description")
        object.__setattr__(
            self,
            "input_schema",
            _freeze_json_mapping(self.input_schema, "input_schema"),
        )


@dataclass(frozen=True)
class LocalWorkerTurnContext:
    workflow: WorkerWorkflowSummary
    current_graph: WorkerGraphSummary
    current_node: WorkerNodeSummary | None
    history: WorkerHistorySummary
    knowledge: tuple[WorkerKnowledgePacket, ...]
    allowed_actions: tuple[WorkerAllowedAction, ...]

    def __post_init__(self) -> None:
        _require_instance(self.workflow, WorkerWorkflowSummary, "workflow")
        _require_instance(self.current_graph, WorkerGraphSummary, "current_graph")
        if self.current_node is not None:
            _require_instance(self.current_node, WorkerNodeSummary, "current_node")
        _require_instance(self.history, WorkerHistorySummary, "history")
        object.__setattr__(
            self,
            "knowledge",
            _freeze_instance_tuple(
                self.knowledge,
                WorkerKnowledgePacket,
                "knowledge",
            ),
        )
        object.__setattr__(
            self,
            "allowed_actions",
            _freeze_instance_tuple(
                self.allowed_actions,
                WorkerAllowedAction,
                "allowed_actions",
            ),
        )


def build_local_worker_turn_context(
    scaffold: CompiledWorkflowScaffold,
    graph: PlanGraph,
    records: tuple[CurrentStepRecord, ...] | list[CurrentStepRecord],
    supply_records: tuple[EnvelopeSupplyRecord, ...] | list[EnvelopeSupplyRecord],
    *,
    current_node_id: str | None,
    knowledge: tuple[WorkerKnowledgePacket, ...] | list[WorkerKnowledgePacket],
    allowed_actions: tuple[WorkerAllowedAction, ...] | list[WorkerAllowedAction],
    history_limit: int = 5,
) -> LocalWorkerTurnContext:
    _require_instance(scaffold, CompiledWorkflowScaffold, "scaffold")
    _require_instance(graph, PlanGraph, "graph")
    records_tuple = _freeze_instance_tuple(records, CurrentStepRecord, "records")
    supply_records_tuple = _freeze_instance_tuple(
        supply_records,
        EnvelopeSupplyRecord,
        "supply_records",
    )
    knowledge_tuple = _freeze_instance_tuple(
        knowledge,
        WorkerKnowledgePacket,
        "knowledge",
    )
    allowed_actions_tuple = _freeze_instance_tuple(
        allowed_actions,
        WorkerAllowedAction,
        "allowed_actions",
    )
    _require_unique_ids(
        (packet.packet_id for packet in knowledge_tuple),
        "knowledge packet_id",
    )
    _require_unique_ids(
        (action.action_id for action in allowed_actions_tuple),
        "allowed action_id",
    )
    _require_positive_int(history_limit, "history_limit")
    _validate_scaffold_identity(scaffold)

    if current_node_id is not None and not isinstance(current_node_id, str):
        raise TypeError("current_node_id must be str or None")
    if current_node_id == "":
        raise ValueError("current_node_id must not be empty")
    if current_node_id is not None and current_node_id not in graph.nodes:
        raise ValueError(f"current_node_id not found in graph: {current_node_id!r}")

    return LocalWorkerTurnContext(
        workflow=_summarize_workflow(scaffold),
        current_graph=_summarize_graph(graph),
        current_node=(
            None
            if current_node_id is None
            else _summarize_node(graph, current_node_id)
        ),
        history=_summarize_history(
            records_tuple,
            supply_records_tuple,
            history_limit=history_limit,
        ),
        knowledge=knowledge_tuple,
        allowed_actions=allowed_actions_tuple,
    )


def _validate_scaffold_identity(scaffold: CompiledWorkflowScaffold) -> None:
    if scaffold.compile_record.workflow_id != scaffold.workflow_id:
        raise ValueError("scaffold workflow_id does not match compile record")
    if (
        scaffold.compile_record.contract_fingerprint
        != scaffold.contract_snapshot.contract_fingerprint
    ):
        raise ValueError(
            "scaffold contract fingerprint does not match contract snapshot"
        )
    snapshot_schema = scaffold.contract_snapshot.normalized_contract["schema"]
    if scaffold.compile_record.contract_schema != snapshot_schema:
        raise ValueError("scaffold contract schema does not match contract snapshot")


def _summarize_workflow(
    scaffold: CompiledWorkflowScaffold,
) -> WorkerWorkflowSummary:
    record = scaffold.compile_record
    return WorkerWorkflowSummary(
        workflow_id=record.workflow_id,
        contract_schema=record.contract_schema,
        contract_fingerprint=record.contract_fingerprint,
        compiler_id=record.compiler_id,
        provider_id=record.provider_id,
        selected_template_id=record.selected_template_id,
        max_steps=scaffold.max_steps,
    )


def _summarize_graph(graph: PlanGraph) -> WorkerGraphSummary:
    node_ids = tuple(
        sorted(_require_str(node_id, "graph node id") for node_id in graph.nodes)
    )
    ready_node_ids = tuple(
        sorted(
            node_id
            for node_id, node in graph.nodes.items()
            if _node_status(node) == "ready"
        )
    )
    terminal_node_ids = tuple(
        sorted(
            node_id
            for node_id, node in graph.nodes.items()
            if _node_terminal(node)
        )
    )

    status_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        status = _node_status(node)
        status_counts[status] = status_counts.get(status, 0) + 1

    return WorkerGraphSummary(
        node_count=len(graph.nodes),
        node_ids=node_ids,
        ready_node_ids=ready_node_ids,
        terminal_node_ids=terminal_node_ids,
        status_counts=status_counts,
    )


def _summarize_node(graph: PlanGraph, node_id: str) -> WorkerNodeSummary:
    node = graph.nodes[node_id]
    role = projection_role_for_node(node)
    if role is not None and not isinstance(role, str):
        role = str(role)

    metadata = node.metadata if isinstance(node.metadata, Mapping) else {}
    execution_params = metadata.get(EXECUTION_PARAMS_KEY)

    return WorkerNodeSummary(
        node_id=node_id,
        intent=_node_intent(node),
        role=role,
        status=_node_status(node),
        execution_ref=_node_execution_ref(node),
        is_terminal=_node_terminal(node),
        has_execution_params=(
            isinstance(execution_params, Mapping) and bool(execution_params)
        ),
        memory_keys=_graph_memory_keys(graph),
    )


def _summarize_history(
    records: tuple[CurrentStepRecord, ...],
    supply_records: tuple[EnvelopeSupplyRecord, ...],
    *,
    history_limit: int,
) -> WorkerHistorySummary:
    recent_records = records[-history_limit:]
    recent_supply_records = supply_records[-history_limit:]
    last_record = records[-1] if records else None
    last_supply = supply_records[-1] if supply_records else None

    return WorkerHistorySummary(
        current_step_count=len(records),
        supply_count=len(supply_records),
        last_accepted_node_id=(
            None if last_record is None else last_record.accepted_node_id
        ),
        last_execution_kind=(
            None if last_record is None else last_record.execution_kind
        ),
        last_stop_reason=(
            None if last_supply is None else _supply_reason(last_supply)
        ),
        recent_steps=tuple(_summarize_step(record) for record in recent_records),
        recent_supplies=tuple(
            _summarize_supply(record) for record in recent_supply_records
        ),
    )


def _summarize_step(record: CurrentStepRecord) -> WorkerStepTraceSummary:
    return WorkerStepTraceSummary(
        accepted_node_id=record.accepted_node_id,
        execution_kind=record.execution_kind,
        ran=record.ran,
        failure=record.execution_failure or record.mapping_failure,
    )


def _summarize_supply(record: EnvelopeSupplyRecord) -> WorkerSupplyTraceSummary:
    return WorkerSupplyTraceSummary(
        decision=record.decision,
        reason=_supply_reason(record),
        selected_node_id=_supply_selected_node_id(record),
        has_envelope=record.envelope is not None,
    )


def _supply_reason(record: EnvelopeSupplyRecord) -> str | None:
    return record.invalid_reason or record.reason or record.error_class


def _supply_selected_node_id(record: EnvelopeSupplyRecord) -> str | None:
    if not isinstance(record.metadata, Mapping):
        return None
    selected_node_id = record.metadata.get("selected_node_id")
    return selected_node_id if isinstance(selected_node_id, str) else None


def _graph_memory_keys(graph: PlanGraph) -> tuple[str, ...]:
    facts = graph.memory.facts
    if not isinstance(facts, Mapping):
        raise TypeError("graph.memory.facts must be a mapping")
    keys: list[str] = []
    for key in facts:
        if not isinstance(key, str):
            raise TypeError("graph.memory.facts keys must be strings")
        keys.append(key)
    return tuple(sorted(keys))


def _node_intent(node: Any) -> str:
    return _require_str(node.intent, "node.intent")


def _node_status(node: Any) -> str:
    return _require_str(node.status, "node.status")


def _node_execution_ref(node: Any) -> str | None:
    return _require_optional_str(node.execution_ref, "node.execution_ref")


def _node_terminal(node: Any) -> bool:
    return _require_bool(node.is_terminal, "node.is_terminal")


def _freeze_json_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    frozen = _freeze_json_value(value, field_name)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return frozen


def _freeze_json_value(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} mapping keys must be strings")
            copied[key] = _freeze_json_value(item, f"{field_name}.{key}")
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(item, f"{field_name}[]")
            for item in value
        )
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{field_name} float values must be finite")
        return value
    raise TypeError(f"{field_name} contains unsupported JSON value")


def _freeze_count_mapping(
    value: Mapping[str, int],
    field_name: str,
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be strings")
        copied[key] = _require_non_negative_int(item, f"{field_name}.{key}")
    return MappingProxyType(copied)


def _freeze_instance_tuple(
    value: tuple[object, ...] | list[object],
    expected_type: type,
    field_name: str,
) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    for item in value:
        _require_instance(item, expected_type, f"{field_name} item")
    return tuple(value)


def _freeze_str_tuple(
    value: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    return tuple(_require_str(item, f"{field_name} item") for item in value)


def _require_unique_ids(values: object, field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {field_name}: {value!r}")
        seen.add(value)


def _require_instance(value: object, expected_type: type, field_name: str) -> object:
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be {expected_type.__name__}")
    return value


def _require_non_empty_str(value: object, field_name: str) -> str:
    result = _require_str(value, field_name)
    if result == "":
        raise ValueError(f"{field_name} must not be empty")
    return result


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _require_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value
