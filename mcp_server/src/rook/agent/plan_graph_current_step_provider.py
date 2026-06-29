"""LM4U catalog-backed current-step provider for LM4S."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
)
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyRecord,
    EnvelopeSupplyResult,
)
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    Step,
    VerifierStep,
)
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph_selector import (
    NodeSelectionProposal,
    propose_next_node,
)

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


ProviderId = Literal["catalog_current_step_provider:v1"]
StepKind = Literal["producer", "verifier", "bind"]

CATALOG_CURRENT_STEP_PROVIDER_ID: ProviderId = "catalog_current_step_provider:v1"
_PROVIDER_ID: ProviderId = CATALOG_CURRENT_STEP_PROVIDER_ID


class _ImmutableMapping(Mapping):
    def __init__(self, items: Mapping) -> None:
        self._items = MappingProxyType(dict(items))

    def __getitem__(self, key: Any) -> Any:
        return self._items[key]

    def __iter__(self) -> Iterator[Any]:
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
        return deepcopy(dict(self._items), memo)


@dataclass(frozen=True)
class NodeStepRule:
    node_id: str
    steps_by_seen_count: tuple[Step, ...]

    def __post_init__(self) -> None:
        steps_by_seen_count = tuple(self.steps_by_seen_count)
        for step in steps_by_seen_count:
            if isinstance(step, BindStep):
                _snapshot_bind_step_payloads(step)
        object.__setattr__(self, "steps_by_seen_count", steps_by_seen_count)


@dataclass(frozen=True)
class CatalogCurrentStepProvider:
    rules: tuple[NodeStepRule, ...]
    terminal_node_ids: frozenset[str] = frozenset()
    _rules_by_node_id: Mapping[str, NodeStepRule] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        object.__setattr__(self, "terminal_node_ids", frozenset(self.terminal_node_ids))
        if any(not node_id for node_id in self.terminal_node_ids):
            raise ValueError("terminal_node_ids must not contain empty ids")

        seen_node_ids: set[str] = set()
        rules_by_node_id: dict[str, NodeStepRule] = {}
        for rule in self.rules:
            if not rule.node_id:
                raise ValueError("NodeStepRule.node_id must be non-empty")
            if rule.node_id in seen_node_ids:
                raise ValueError(f"duplicate NodeStepRule.node_id: {rule.node_id!r}")
            seen_node_ids.add(rule.node_id)
            rules_by_node_id[rule.node_id] = rule

            if not rule.steps_by_seen_count:
                raise ValueError(
                    "NodeStepRule.steps_by_seen_count must be non-empty for "
                    f"{rule.node_id!r}"
                )
            for step in rule.steps_by_seen_count:
                if not isinstance(step, (ProducerStep, VerifierStep, BindStep)):
                    raise TypeError(
                        f"steps_by_seen_count for {rule.node_id!r} contains a "
                        "non-Step value"
                    )
                target_node_id = _step_target_node_id(step)
                if target_node_id != rule.node_id:
                    raise ValueError(
                        f"step for rule {rule.node_id!r} targets {target_node_id!r}"
                    )

        overlap = sorted(set(self.terminal_node_ids).intersection(seen_node_ids))
        if overlap:
            raise ValueError(
                "terminal_node_ids must not also have NodeStepRule entries: "
                + ", ".join(overlap)
            )
        object.__setattr__(
            self, "_rules_by_node_id", MappingProxyType(rules_by_node_id)
        )

    def __call__(
        self,
        current_graph: "PlanGraph",
        records: tuple[CurrentStepRecord, ...],
        supply_records: tuple[EnvelopeSupplyRecord, ...],
    ) -> EnvelopeSupplyResult:
        del supply_records

        proposal = propose_next_node(current_graph)

        if proposal.decision == "HALT_NONE_READY":
            return EnvelopeSupplyResult(
                "HALT",
                None,
                "selector_halt:none_ready",
                _metadata(proposal, None, None, None),
            )
        if proposal.decision == "HALT_AMBIGUOUS_READY":
            return EnvelopeSupplyResult(
                "HALT",
                None,
                "selector_halt:ambiguous_ready",
                _metadata(proposal, None, None, None),
            )

        selected_node_id = proposal.selected_node_id
        if selected_node_id in self.terminal_node_ids:
            return EnvelopeSupplyResult(
                "HALT",
                None,
                f"terminal_node_selected:{selected_node_id}",
                _metadata(proposal, None, None, None),
            )

        seen_count = sum(
            1 for record in records if record.accepted_node_id == selected_node_id
        )
        rule = self._rules_by_node_id.get(selected_node_id)
        if rule is None:
            return EnvelopeSupplyResult(
                "SUPPLY",
                None,
                f"no_step_rule_for_node:{selected_node_id}",
                _metadata(proposal, seen_count, None, None),
            )
        if seen_count >= len(rule.steps_by_seen_count):
            return EnvelopeSupplyResult(
                "SUPPLY",
                None,
                f"step_rule_exhausted:{selected_node_id}:{seen_count}",
                _metadata(proposal, seen_count, len(rule.steps_by_seen_count), None),
            )

        step = rule.steps_by_seen_count[seen_count]
        metadata = _metadata(
            proposal,
            seen_count,
            len(rule.steps_by_seen_count),
            _step_kind(step),
        )
        mapping = map_accepted_proposal_to_step(
            proposal,
            current_graph,
            {selected_node_id: step},
        )
        return EnvelopeSupplyResult(
            "SUPPLY",
            CurrentStepEnvelope(mapping, metadata),
            f"selected_node_mapped:{selected_node_id}:{seen_count}",
            metadata,
        )


def _step_target_node_id(step: Step) -> str:
    if isinstance(step, VerifierStep):
        return step.verifier_node_id
    return step.node_id


def _snapshot_bind_step_payloads(step: BindStep) -> None:
    try:
        base_params = _immutable_snapshot(step.base_params)
    except TypeError as exc:
        raise TypeError("BindStep.base_params contains non-snapshotable payload") from exc
    object.__setattr__(step, "base_params", base_params)
    object.__setattr__(step, "bindings", _snapshot_bindings(step.bindings))


def _immutable_snapshot(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _ImmutableMapping(
            {
                key: _immutable_snapshot(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_immutable_snapshot(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_immutable_snapshot(item) for item in value)
    try:
        return deepcopy(value)
    except Exception as exc:
        raise TypeError(
            f"cannot snapshot payload of type {type(value).__name__}"
        ) from exc


def _snapshot_bindings(bindings: Any) -> Any:
    if not isinstance(bindings, Mapping):
        return bindings
    return _ImmutableMapping(
        {
            param_key: _snapshot_binding_path(path)
            for param_key, path in bindings.items()
        }
    )


def _snapshot_binding_path(path: Any) -> Any:
    if isinstance(path, (list, tuple)):
        return tuple(path)
    return path


def _step_kind(step: Step) -> StepKind:
    if isinstance(step, ProducerStep):
        return "producer"
    if isinstance(step, VerifierStep):
        return "verifier"
    return "bind"


def _metadata(
    proposal: NodeSelectionProposal,
    seen_count: int | None,
    rule_step_count: int | None,
    step_kind: StepKind | None,
) -> Mapping[str, Any]:
    return {
        "provider": _PROVIDER_ID,
        "proposal_decision": proposal.decision,
        "selected_node_id": proposal.selected_node_id,
        "candidate_node_ids": tuple(proposal.candidate_node_ids),
        "ready_count": proposal.ready_count,
        "selector_id": proposal.selector_id,
        "seen_count": seen_count,
        "rule_step_count": rule_step_count,
        "step_kind": step_kind,
    }
