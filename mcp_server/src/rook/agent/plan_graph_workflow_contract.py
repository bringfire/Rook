"""LM4W declarative workflow contract compiler.

This module validates a Python contract and compiles it into the existing
PlanGraph scaffold objects. It prepares artifacts only; callers decide when to
run a compiled scaffold.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, TypeAlias, get_args

from rook.agent.plan_graph_current_step_provider import (
    CATALOG_CURRENT_STEP_PROVIDER_ID,
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
StepKindTag = Literal["producer", "verifier", "bind"]

WORKFLOW_CONTRACT_SCHEMA = "rook.workflow_contract:v1"
WORKFLOW_CONTRACT_COMPILER_ID = "rook_workflow_contract_compiler:v1"
CONTRACT_FINGERPRINT_ALGORITHM = "sha256"

_OUTCOME_STATUSES = frozenset(get_args(OutcomeStatus))
_WORKFLOW_PAYLOAD_FIELDS = frozenset(
    {
        "schema",
        "workflow_id",
        "template",
        "initial_params",
        "rules",
        "terminal_node_ids",
        "expected_refs",
        "max_steps",
        "metadata",
    }
)
_TEMPLATE_PAYLOAD_FIELDS = frozenset({"descriptor", "expected_template_id"})
_INITIAL_PARAM_PAYLOAD_FIELDS = frozenset({"node_id", "execution_params"})
_RULE_PAYLOAD_FIELDS = frozenset({"node_id", "steps_by_seen_count"})
_EXPECTED_REF_PAYLOAD_FIELDS = frozenset({"node_id", "execution_ref"})
_PRODUCER_STEP_PAYLOAD_FIELDS = frozenset({"kind", "node_id"})
_VERIFIER_STEP_PAYLOAD_FIELDS = frozenset(
    {"kind", "verifier_node_id", "source_node_id", "expected_outcome"}
)
_BIND_STEP_PAYLOAD_FIELDS = frozenset(
    {"kind", "node_id", "base_params", "bindings"}
)


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
class WorkflowContractSnapshot:
    workflow_id: str
    normalized_contract: Mapping[str, Any]
    contract_fingerprint: str


@dataclass(frozen=True)
class WorkflowCompileRecord:
    workflow_id: str
    compiler_id: str
    contract_schema: str
    contract_fingerprint_algorithm: str
    contract_fingerprint: str
    provider_id: str
    expected_template_id: str
    selected_template_id: str
    graph_node_ids: tuple[str, ...]
    initial_param_node_ids: tuple[str, ...]
    rule_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[tuple[str, str], ...]
    step_kinds_by_rule: tuple[tuple[str, tuple[str, ...]], ...]
    max_steps: int


@dataclass(frozen=True)
class _NormalizedWorkflowTemplateRef:
    descriptor: Mapping[str, str]
    expected_template_id: str


@dataclass(frozen=True)
class _NormalizedInitialNodeParams:
    node_id: str
    execution_params: Mapping[str, Any]


@dataclass(frozen=True)
class _NormalizedProducerStepSpec:
    kind: StepKindTag
    node_id: str


@dataclass(frozen=True)
class _NormalizedVerifierStepSpec:
    kind: StepKindTag
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None


@dataclass(frozen=True)
class _NormalizedBindStepSpec:
    kind: StepKindTag
    node_id: str
    base_params: Mapping[str, Any]
    bindings: Mapping[str, tuple[str, ...]]


NormalizedStepSpec: TypeAlias = (
    "_NormalizedProducerStepSpec | _NormalizedVerifierStepSpec | _NormalizedBindStepSpec"
)


@dataclass(frozen=True)
class _NormalizedWorkflowNodeRule:
    node_id: str
    steps_by_seen_count: tuple[NormalizedStepSpec, ...]


@dataclass(frozen=True)
class _NormalizedExpectedNodeRef:
    node_id: str
    execution_ref: str


@dataclass(frozen=True)
class _NormalizedWorkflowContract:
    workflow_id: str
    template: _NormalizedWorkflowTemplateRef
    initial_params: tuple[_NormalizedInitialNodeParams, ...]
    rules: tuple[_NormalizedWorkflowNodeRule, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[_NormalizedExpectedNodeRef, ...]
    max_steps: int
    metadata: Mapping[str, Any]
    normalized_contract: Mapping[str, Any]


@dataclass(frozen=True)
class CompiledWorkflowScaffold:
    workflow_id: str
    graph: PlanGraph
    provider: CatalogCurrentStepProvider
    max_steps: int
    metadata: Mapping[str, Any]
    rules: tuple[NodeStepRule, ...]
    steps: tuple[Step, ...]
    contract_snapshot: WorkflowContractSnapshot
    compile_record: WorkflowCompileRecord


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

    def __deepcopy__(self, memo: dict[int, Any]) -> dict:
        return copy.deepcopy(dict(self._items), memo)


def snapshot_workflow_contract(
    contract: RookWorkflowContract,
) -> WorkflowContractSnapshot:
    """Snapshot and fingerprint a graph-free workflow contract artifact."""
    normalized = _normalize_workflow_contract(contract)
    return _snapshot_from_normalized(normalized)


def load_workflow_contract_payload(payload: Mapping[str, Any]) -> RookWorkflowContract:
    """Load an already-parsed LM4X workflow contract payload."""
    payload = _require_mapping(payload, "workflow contract payload")
    _require_fields(
        payload,
        required=_WORKFLOW_PAYLOAD_FIELDS,
        context="workflow contract payload",
    )
    schema = payload["schema"]
    if schema != WORKFLOW_CONTRACT_SCHEMA:
        raise ValueError(f"unsupported workflow contract schema: {schema!r}")

    contract = RookWorkflowContract(
        workflow_id=payload["workflow_id"],
        template=_load_template_ref_payload(payload["template"]),
        initial_params=tuple(
            _load_initial_param_payload(item)
            for item in _require_sequence(
                payload["initial_params"],
                "initial_params",
            )
        ),
        rules=tuple(
            _load_rule_payload(item)
            for item in _require_sequence(payload["rules"], "rules")
        ),
        terminal_node_ids=tuple(
            _require_sequence(payload["terminal_node_ids"], "terminal_node_ids")
        ),
        expected_refs=tuple(
            _load_expected_ref_payload(item)
            for item in _require_sequence(payload["expected_refs"], "expected_refs")
        ),
        max_steps=payload["max_steps"],
        metadata=_copy_required_mapping(payload["metadata"], "metadata"),
    )
    snapshot_workflow_contract(contract)
    return contract


def _snapshot_from_normalized(
    normalized: _NormalizedWorkflowContract,
) -> WorkflowContractSnapshot:
    fingerprint = _fingerprint_normalized_contract(normalized.normalized_contract)
    return WorkflowContractSnapshot(
        workflow_id=normalized.workflow_id,
        normalized_contract=normalized.normalized_contract,
        contract_fingerprint=fingerprint,
    )


def _fingerprint_normalized_contract(normalized_contract: Mapping[str, Any]) -> str:
    canonical_json = json.dumps(
        _plain_json_tree(normalized_contract),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compile_workflow_contract(contract: RookWorkflowContract) -> CompiledWorkflowScaffold:
    """Compile a declarative contract into provider-ready workflow scaffold data."""
    normalized = _normalize_workflow_contract(contract)
    snapshot = _snapshot_from_normalized(normalized)

    descriptor = dict(normalized.template.descriptor)
    selection = select_template(descriptor)
    if selection.selected_template_id != normalized.template.expected_template_id:
        raise ValueError(
            "selected template id does not match expected template id: "
            f"{selection.selected_template_id!r} != "
            f"{normalized.template.expected_template_id!r}"
        )
    if selection.graph is None:
        raise ValueError("selected template did not provide a graph")

    graph = initialize_graph(selection.graph)
    _validate_expected_refs(graph, normalized.expected_refs)
    _stage_initial_params(graph, normalized.initial_params)
    rules, steps = _compile_rules(graph, normalized.rules)
    terminal_node_ids = _validate_terminal_node_ids(
        graph,
        normalized.terminal_node_ids,
        {rule.node_id for rule in rules},
    )
    provider = CatalogCurrentStepProvider(
        rules,
        terminal_node_ids=frozenset(terminal_node_ids),
    )
    compile_record = _build_compile_record(
        normalized,
        snapshot,
        selected_template_id=selection.selected_template_id,
        graph=graph,
    )

    return CompiledWorkflowScaffold(
        workflow_id=normalized.workflow_id,
        graph=graph,
        provider=provider,
        max_steps=normalized.max_steps,
        metadata=normalized.metadata,
        rules=rules,
        steps=steps,
        contract_snapshot=snapshot,
        compile_record=compile_record,
    )


def _load_template_ref_payload(payload: Any) -> WorkflowTemplateRef:
    payload = _require_mapping(payload, "template")
    _require_fields(
        payload,
        required=_TEMPLATE_PAYLOAD_FIELDS,
        context="template",
    )
    descriptor = _copy_required_mapping(payload["descriptor"], "template.descriptor")
    return WorkflowTemplateRef(
        descriptor=descriptor,
        expected_template_id=payload["expected_template_id"],
    )


def _load_initial_param_payload(payload: Any) -> InitialNodeParams:
    payload = _require_mapping(payload, "initial_params entry")
    _require_fields(
        payload,
        required=_INITIAL_PARAM_PAYLOAD_FIELDS,
        context="initial_params entry",
    )
    return InitialNodeParams(
        node_id=payload["node_id"],
        execution_params=_copy_required_mapping(
            payload["execution_params"],
            "initial_params.execution_params",
        ),
    )


def _load_rule_payload(payload: Any) -> WorkflowNodeRule:
    payload = _require_mapping(payload, "rules entry")
    _require_fields(payload, required=_RULE_PAYLOAD_FIELDS, context="rules entry")
    return WorkflowNodeRule(
        node_id=payload["node_id"],
        steps_by_seen_count=tuple(
            _load_step_spec_payload(item)
            for item in _require_sequence(
                payload["steps_by_seen_count"],
                "rules.steps_by_seen_count",
            )
        ),
    )


def _load_step_spec_payload(payload: Any) -> WorkflowStepSpec:
    payload = _require_mapping(payload, "step spec")
    if "kind" not in payload:
        raise ValueError("step spec missing required fields: ['kind']")
    kind = payload["kind"]
    if not isinstance(kind, str):
        raise ValueError(f"step spec kind must be a string: {kind!r}")

    if kind == "producer":
        _require_fields(
            payload,
            required=_PRODUCER_STEP_PAYLOAD_FIELDS,
            context="producer step",
        )
        return ProducerStepSpec(node_id=payload["node_id"])

    if kind == "verifier":
        _require_fields(
            payload,
            required=_VERIFIER_STEP_PAYLOAD_FIELDS,
            context="verifier step",
        )
        return VerifierStepSpec(
            verifier_node_id=payload["verifier_node_id"],
            source_node_id=payload["source_node_id"],
            expected_outcome=payload["expected_outcome"],
        )

    if kind == "bind":
        _require_fields(
            payload,
            required=_BIND_STEP_PAYLOAD_FIELDS,
            context="bind step",
        )
        return BindStepSpec(
            node_id=payload["node_id"],
            base_params=_copy_required_mapping(
                payload["base_params"],
                "bind.base_params",
            ),
            bindings=_load_bindings_payload(payload["bindings"]),
        )

    raise ValueError(f"unknown step spec kind: {kind!r}")


def _load_expected_ref_payload(payload: Any) -> ExpectedNodeRef:
    payload = _require_mapping(payload, "expected_refs entry")
    _require_fields(
        payload,
        required=_EXPECTED_REF_PAYLOAD_FIELDS,
        context="expected_refs entry",
    )
    return ExpectedNodeRef(
        node_id=payload["node_id"],
        execution_ref=payload["execution_ref"],
    )


def _load_bindings_payload(payload: Any) -> Mapping[str, tuple[str, ...]]:
    payload = _require_mapping(payload, "bind.bindings")
    bindings: dict[str, tuple[str, ...]] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("bind.bindings keys must be strings")
        bindings[key] = tuple(_require_sequence(value, f"bind.bindings[{key!r}]"))
    return bindings


def _copy_required_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    copied = _copy_json_payload(value)
    if not isinstance(copied, Mapping):
        raise TypeError(f"{context} must be a mapping")
    return copied


def _copy_json_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        copied: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON mapping keys must be strings")
            copied[key] = _copy_json_payload(item)
        return copied
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json_payload(item) for item in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("JSON float values must be finite")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"value is not JSON-safe: {type(value).__name__}")


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{context} keys must be strings")
    return value


def _require_sequence(value: Any, context: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{context} must be a list or tuple")
    return tuple(value)


def _require_fields(
    payload: Mapping[str, Any],
    *,
    required: frozenset[str],
    context: str,
) -> None:
    keys = set(payload)
    missing = required - keys
    extra = keys - required
    if missing:
        raise ValueError(f"{context} missing required fields: {sorted(missing)!r}")
    if extra:
        raise ValueError(f"{context} has unknown fields: {sorted(extra)!r}")


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


def _normalize_workflow_contract(
    contract: RookWorkflowContract,
) -> _NormalizedWorkflowContract:
    workflow_id = _require_non_empty_str(contract.workflow_id, "workflow_id")
    max_steps = _validate_max_steps(contract.max_steps)
    template = _normalize_template(contract.template)
    metadata = _snapshot_metadata(contract.metadata)
    initial_params = _normalize_initial_params(contract.initial_params)
    rules = _normalize_rules(contract.rules)
    terminal_node_ids = _normalize_terminal_node_ids(contract.terminal_node_ids)
    expected_refs = _normalize_expected_refs(contract.expected_refs)
    _reject_terminal_rule_overlap(terminal_node_ids, rules)

    normalized_contract = _ImmutableJsonMapping(
        {
            "schema": WORKFLOW_CONTRACT_SCHEMA,
            "workflow_id": workflow_id,
            "template": _ImmutableJsonMapping(
                {
                    "descriptor": template.descriptor,
                    "expected_template_id": template.expected_template_id,
                }
            ),
            "initial_params": tuple(
                _normalized_initial_param_payload(entry) for entry in initial_params
            ),
            "rules": tuple(_normalized_rule_payload(rule) for rule in rules),
            "terminal_node_ids": terminal_node_ids,
            "expected_refs": tuple(
                _ImmutableJsonMapping(
                    {
                        "node_id": ref.node_id,
                        "execution_ref": ref.execution_ref,
                    }
                )
                for ref in expected_refs
            ),
            "max_steps": max_steps,
            "metadata": metadata,
        }
    )

    return _NormalizedWorkflowContract(
        workflow_id=workflow_id,
        template=template,
        initial_params=initial_params,
        rules=rules,
        terminal_node_ids=terminal_node_ids,
        expected_refs=expected_refs,
        max_steps=max_steps,
        metadata=metadata,
        normalized_contract=normalized_contract,
    )


def _normalize_template(template: Any) -> _NormalizedWorkflowTemplateRef:
    if not isinstance(template, WorkflowTemplateRef):
        raise TypeError("contract.template must be WorkflowTemplateRef")
    descriptor = _snapshot_descriptor(template.descriptor)
    expected_template_id = _require_non_empty_str(
        template.expected_template_id,
        "WorkflowTemplateRef.expected_template_id",
    )
    return _NormalizedWorkflowTemplateRef(
        descriptor=_ImmutableJsonMapping(descriptor),
        expected_template_id=expected_template_id,
    )


def _normalize_initial_params(
    initial_params: tuple[InitialNodeParams, ...],
) -> tuple[_NormalizedInitialNodeParams, ...]:
    seen: set[str] = set()
    normalized: list[_NormalizedInitialNodeParams] = []
    for entry in tuple(initial_params):
        if not isinstance(entry, InitialNodeParams):
            raise TypeError("initial_params entries must be InitialNodeParams")
        node_id = _require_non_empty_str(entry.node_id, "InitialNodeParams.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate InitialNodeParams.node_id: {node_id!r}")
        seen.add(node_id)
        if not isinstance(entry.execution_params, Mapping):
            raise TypeError("InitialNodeParams.execution_params must be a mapping")
        normalized.append(
            _NormalizedInitialNodeParams(
                node_id=node_id,
                execution_params=_immutable_json_snapshot(entry.execution_params),
            )
        )
    return tuple(normalized)


def _normalize_rules(
    rules: tuple[WorkflowNodeRule, ...],
) -> tuple[_NormalizedWorkflowNodeRule, ...]:
    rule_tuple = tuple(rules)
    if not rule_tuple:
        raise ValueError("rules must contain at least one WorkflowNodeRule")
    seen: set[str] = set()
    normalized: list[_NormalizedWorkflowNodeRule] = []
    for rule in rule_tuple:
        if not isinstance(rule, WorkflowNodeRule):
            raise TypeError("rules entries must be WorkflowNodeRule")
        node_id = _require_non_empty_str(rule.node_id, "WorkflowNodeRule.node_id")
        if node_id in seen:
            raise ValueError(f"duplicate WorkflowNodeRule.node_id: {node_id!r}")
        seen.add(node_id)
        steps = tuple(rule.steps_by_seen_count)
        if not steps:
            raise ValueError(
                "WorkflowNodeRule.steps_by_seen_count must be non-empty for "
                f"{node_id!r}"
            )
        normalized.append(
            _NormalizedWorkflowNodeRule(
                node_id=node_id,
                steps_by_seen_count=tuple(
                    _normalize_step_spec(node_id, spec) for spec in steps
                ),
            )
        )
    return tuple(normalized)


def _normalize_step_spec(
    rule_node_id: str,
    spec: WorkflowStepSpec,
) -> NormalizedStepSpec:
    if isinstance(spec, ProducerStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "ProducerStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(
                f"ProducerStepSpec for {rule_node_id!r} targets {node_id!r}"
            )
        return _NormalizedProducerStepSpec(kind="producer", node_id=node_id)

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
        if (
            spec.expected_outcome is not None
            and spec.expected_outcome not in _OUTCOME_STATUSES
        ):
            raise ValueError(
                "invalid VerifierStepSpec.expected_outcome: "
                f"{spec.expected_outcome!r}"
            )
        return _NormalizedVerifierStepSpec(
            kind="verifier",
            verifier_node_id=verifier_node_id,
            source_node_id=source_node_id,
            expected_outcome=spec.expected_outcome,
        )

    if isinstance(spec, BindStepSpec):
        node_id = _require_non_empty_str(spec.node_id, "BindStepSpec.node_id")
        if node_id != rule_node_id:
            raise ValueError(f"BindStepSpec for {rule_node_id!r} targets {node_id!r}")
        if not isinstance(spec.base_params, Mapping):
            raise TypeError("BindStepSpec.base_params must be a mapping")
        return _NormalizedBindStepSpec(
            kind="bind",
            node_id=node_id,
            base_params=_immutable_json_snapshot(spec.base_params),
            bindings=_compile_bindings(spec.bindings),
        )

    raise TypeError("WorkflowNodeRule.steps_by_seen_count contains a non-step spec")


def _normalize_terminal_node_ids(terminal_node_ids: tuple[str, ...]) -> tuple[str, ...]:
    terminal_ids = tuple(terminal_node_ids)
    if not terminal_ids:
        raise ValueError("terminal_node_ids must contain at least one node")
    seen: set[str] = set()
    normalized: list[str] = []
    for node_id in terminal_ids:
        node_id = _require_non_empty_str(node_id, "terminal_node_ids")
        if node_id in seen:
            raise ValueError(f"duplicate terminal node id: {node_id!r}")
        seen.add(node_id)
        normalized.append(node_id)
    return tuple(normalized)


def _normalize_expected_refs(
    expected_refs: tuple[ExpectedNodeRef, ...],
) -> tuple[_NormalizedExpectedNodeRef, ...]:
    seen: set[str] = set()
    normalized: list[_NormalizedExpectedNodeRef] = []
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
        normalized.append(
            _NormalizedExpectedNodeRef(
                node_id=node_id,
                execution_ref=execution_ref,
            )
        )
    return tuple(normalized)


def _reject_terminal_rule_overlap(
    terminal_node_ids: tuple[str, ...],
    rules: tuple[_NormalizedWorkflowNodeRule, ...],
) -> None:
    rule_node_ids = {rule.node_id for rule in rules}
    for node_id in terminal_node_ids:
        if node_id in rule_node_ids:
            raise ValueError(
                f"terminal node id must not also have a rule: {node_id!r}"
            )


def _normalized_initial_param_payload(
    entry: _NormalizedInitialNodeParams,
) -> Mapping[str, Any]:
    return _ImmutableJsonMapping(
        {
            "node_id": entry.node_id,
            "execution_params": entry.execution_params,
        }
    )


def _normalized_rule_payload(rule: _NormalizedWorkflowNodeRule) -> Mapping[str, Any]:
    return _ImmutableJsonMapping(
        {
            "node_id": rule.node_id,
            "steps_by_seen_count": tuple(
                _normalized_step_payload(step) for step in rule.steps_by_seen_count
            ),
        }
    )


def _normalized_step_payload(step: NormalizedStepSpec) -> Mapping[str, Any]:
    if isinstance(step, _NormalizedProducerStepSpec):
        return _ImmutableJsonMapping(
            {
                "kind": step.kind,
                "node_id": step.node_id,
            }
        )
    if isinstance(step, _NormalizedVerifierStepSpec):
        return _ImmutableJsonMapping(
            {
                "kind": step.kind,
                "verifier_node_id": step.verifier_node_id,
                "source_node_id": step.source_node_id,
                "expected_outcome": step.expected_outcome,
            }
        )
    if isinstance(step, _NormalizedBindStepSpec):
        return _ImmutableJsonMapping(
            {
                "kind": step.kind,
                "node_id": step.node_id,
                "base_params": step.base_params,
                "bindings": step.bindings,
            }
        )
    raise TypeError("unknown normalized step spec")


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


def _snapshot_metadata(metadata: Any) -> Mapping[str, Any]:
    if metadata is None:
        return _immutable_json_snapshot({})
    if not isinstance(metadata, Mapping):
        raise TypeError("RookWorkflowContract.metadata must be a mapping")
    return _immutable_json_snapshot(metadata)


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
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, (str, int, bool))


def _stage_initial_params(
    graph: PlanGraph,
    initial_params: tuple[_NormalizedInitialNodeParams, ...],
) -> None:
    for entry in initial_params:
        node_id = entry.node_id
        if node_id not in graph.nodes:
            raise ValueError(f"unknown initial-param node: {node_id!r}")
        graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = _plain_json_tree(
            entry.execution_params
        )


def _compile_rules(
    graph: PlanGraph,
    rules: tuple[_NormalizedWorkflowNodeRule, ...],
) -> tuple[tuple[NodeStepRule, ...], tuple[Step, ...]]:
    compiled_rules: list[NodeStepRule] = []
    compiled_steps: list[Step] = []
    for rule in rules:
        if rule.node_id not in graph.nodes:
            raise ValueError(f"unknown workflow rule node: {rule.node_id!r}")
        steps = tuple(_compile_step_spec(graph, spec) for spec in rule.steps_by_seen_count)
        compiled_rules.append(NodeStepRule(rule.node_id, steps))
        compiled_steps.extend(steps)
    return tuple(compiled_rules), tuple(compiled_steps)


def _compile_step_spec(
    graph: PlanGraph,
    spec: NormalizedStepSpec,
) -> Step:
    if isinstance(spec, _NormalizedProducerStepSpec):
        return ProducerStep(spec.node_id)

    if isinstance(spec, _NormalizedVerifierStepSpec):
        if spec.source_node_id not in graph.nodes:
            raise ValueError(f"unknown verifier source node: {spec.source_node_id!r}")
        return VerifierStep(
            spec.verifier_node_id,
            spec.source_node_id,
            expected_outcome=spec.expected_outcome,
        )

    if isinstance(spec, _NormalizedBindStepSpec):
        return BindStep(spec.node_id, spec.base_params, spec.bindings)

    raise TypeError("unknown normalized step spec")


def _compile_bindings(bindings: Any) -> Mapping[str, tuple[str, ...]]:
    if not isinstance(bindings, Mapping):
        raise TypeError("BindStepSpec.bindings must be a mapping")
    compiled: dict[str, tuple[str, ...]] = {}
    for param_key, path in bindings.items():
        if not isinstance(param_key, str):
            raise TypeError("binding param keys must be strings")
        if not param_key:
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
    for node_id in terminal_node_ids:
        if node_id not in graph.nodes:
            raise ValueError(f"unknown terminal node id: {node_id!r}")
        if node_id in rule_node_ids:
            raise ValueError(
                f"terminal node id must not also have a rule: {node_id!r}"
            )
        if not graph.nodes[node_id].is_terminal:
            raise ValueError(f"declared terminal node is not terminal: {node_id!r}")
    return terminal_node_ids


def _validate_expected_refs(
    graph: PlanGraph,
    expected_refs: tuple[_NormalizedExpectedNodeRef, ...],
) -> None:
    for expected in expected_refs:
        if expected.node_id not in graph.nodes:
            raise ValueError(f"unknown expected-ref node: {expected.node_id!r}")
        actual_ref = graph.nodes[expected.node_id].execution_ref
        if actual_ref != expected.execution_ref:
            raise ValueError(
                f"execution_ref mismatch for {expected.node_id!r}: "
                f"expected {expected.execution_ref!r}, got {actual_ref!r}"
            )


def _build_compile_record(
    normalized: _NormalizedWorkflowContract,
    snapshot: WorkflowContractSnapshot,
    *,
    selected_template_id: str,
    graph: PlanGraph,
) -> WorkflowCompileRecord:
    return WorkflowCompileRecord(
        workflow_id=normalized.workflow_id,
        compiler_id=WORKFLOW_CONTRACT_COMPILER_ID,
        contract_schema=WORKFLOW_CONTRACT_SCHEMA,
        contract_fingerprint_algorithm=CONTRACT_FINGERPRINT_ALGORITHM,
        contract_fingerprint=snapshot.contract_fingerprint,
        provider_id=CATALOG_CURRENT_STEP_PROVIDER_ID,
        expected_template_id=normalized.template.expected_template_id,
        selected_template_id=selected_template_id,
        graph_node_ids=tuple(sorted(graph.nodes)),
        initial_param_node_ids=tuple(
            entry.node_id for entry in normalized.initial_params
        ),
        rule_node_ids=tuple(rule.node_id for rule in normalized.rules),
        terminal_node_ids=normalized.terminal_node_ids,
        expected_refs=tuple(
            (ref.node_id, ref.execution_ref) for ref in normalized.expected_refs
        ),
        step_kinds_by_rule=tuple(
            (
                rule.node_id,
                tuple(step.kind for step in rule.steps_by_seen_count),
            )
            for rule in normalized.rules
        ),
        max_steps=normalized.max_steps,
    )
