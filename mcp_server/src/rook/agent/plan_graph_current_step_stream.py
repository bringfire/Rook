"""LM4S caller-fed current-step stream runner."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
    run_current_mapped_step,
)
from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


SupplyDecision = Literal["SUPPLY", "HALT"]
StopReason = Literal[
    "max_steps_invalid",
    "max_steps_reached",
    "provider_error",
    "provider_invalid",
    "provider_halt",
    "execution_refused",
    "graph_not_advanced",
]
SupplyInvalidReason = Literal[
    "supply_result_invalid",
    "supply_missing_envelope",
    "halt_with_envelope",
    "halt_missing_reason",
    "unknown_supply_decision",
]
MetadataCopyStatus = Literal["absent", "copied", "invalid", "copy_failed"]


@dataclass(frozen=True)
class EnvelopeSupplyResult:
    decision: SupplyDecision
    envelope: CurrentStepEnvelope | None
    reason: str | None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class EnvelopeSupplyRecord:
    decision: str | None
    envelope: CurrentStepEnvelope | None
    reason: str | None
    metadata: dict[str, Any] | None = None
    metadata_status: MetadataCopyStatus = "absent"
    metadata_error: str | None = None
    invalid_reason: SupplyInvalidReason | None = None
    error_class: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class CurrentStepStreamResult:
    final_graph: "PlanGraph"
    records: tuple[CurrentStepRecord, ...]
    supply_records: tuple[EnvelopeSupplyRecord, ...]
    stop_reason: StopReason
    steps_attempted: int


EnvelopeSource = Callable[
    [
        "PlanGraph",
        tuple[CurrentStepRecord, ...],
        tuple[EnvelopeSupplyRecord, ...],
    ],
    EnvelopeSupplyResult,
]


def _copy_metadata(metadata: Any) -> tuple[dict[str, Any] | None, MetadataCopyStatus, str | None]:
    if metadata is None:
        return None, "absent", None
    if not isinstance(metadata, Mapping):
        return None, "invalid", None
    try:
        return deepcopy(dict(metadata)), "copied", None
    except Exception as exc:
        return None, "copy_failed", f"{exc.__class__.__name__}: {exc}"


def _supply_record(
    result: EnvelopeSupplyResult,
    invalid_reason: SupplyInvalidReason | None = None,
) -> EnvelopeSupplyRecord:
    metadata, metadata_status, metadata_error = _copy_metadata(result.metadata)
    return EnvelopeSupplyRecord(
        decision=result.decision,
        envelope=result.envelope,
        reason=result.reason,
        metadata=metadata,
        metadata_status=metadata_status,
        metadata_error=metadata_error,
        invalid_reason=invalid_reason,
    )


def _invalid_reason(result: EnvelopeSupplyResult) -> SupplyInvalidReason | None:
    if result.decision == "SUPPLY":
        if result.envelope is None:
            return "supply_missing_envelope"
        return None
    if result.decision == "HALT":
        if result.envelope is not None:
            return "halt_with_envelope"
        if not result.reason:
            return "halt_missing_reason"
        return None
    return "unknown_supply_decision"


async def run_current_step_stream(
    initial_graph: "PlanGraph",
    envelope_source: EnvelopeSource,
    *,
    max_steps: int,
    runner: SupportsLiveProducerNode | None = None,
) -> CurrentStepStreamResult:
    if max_steps <= 0:
        return CurrentStepStreamResult(
            final_graph=initial_graph,
            records=(),
            supply_records=(),
            stop_reason="max_steps_invalid",
            steps_attempted=0,
        )

    graph = initial_graph
    records: list[CurrentStepRecord] = []
    supply_records: list[EnvelopeSupplyRecord] = []

    while True:
        if len(records) >= max_steps:
            return CurrentStepStreamResult(
                final_graph=graph,
                records=tuple(records),
                supply_records=tuple(supply_records),
                stop_reason="max_steps_reached",
                steps_attempted=len(records),
            )

        try:
            supplied = envelope_source(graph, tuple(records), tuple(supply_records))
        except Exception as exc:
            supply_records.append(
                EnvelopeSupplyRecord(
                    decision=None,
                    envelope=None,
                    reason=None,
                    invalid_reason=None,
                    error_class=exc.__class__.__name__,
                    error_message=str(exc),
                )
            )
            return CurrentStepStreamResult(
                final_graph=graph,
                records=tuple(records),
                supply_records=tuple(supply_records),
                stop_reason="provider_error",
                steps_attempted=len(records),
            )

        if not isinstance(supplied, EnvelopeSupplyResult):
            supply_records.append(
                EnvelopeSupplyRecord(
                    decision=None,
                    envelope=None,
                    reason=None,
                    invalid_reason="supply_result_invalid",
                )
            )
            return CurrentStepStreamResult(
                final_graph=graph,
                records=tuple(records),
                supply_records=tuple(supply_records),
                stop_reason="provider_invalid",
                steps_attempted=len(records),
            )

        invalid_reason = _invalid_reason(supplied)
        supply_records.append(_supply_record(supplied, invalid_reason))
        if invalid_reason is not None:
            return CurrentStepStreamResult(
                final_graph=graph,
                records=tuple(records),
                supply_records=tuple(supply_records),
                stop_reason="provider_invalid",
                steps_attempted=len(records),
            )

        if supplied.decision == "HALT":
            return CurrentStepStreamResult(
                final_graph=graph,
                records=tuple(records),
                supply_records=tuple(supply_records),
                stop_reason="provider_halt",
                steps_attempted=len(records),
            )

        step_result = await run_current_mapped_step(supplied.envelope, graph, runner)
        records.append(step_result.record)

        if not step_result.record.ran:
            return CurrentStepStreamResult(
                final_graph=graph,
                records=tuple(records),
                supply_records=tuple(supply_records),
                stop_reason="execution_refused",
                steps_attempted=len(records),
            )

        if step_result.graph is graph:
            return CurrentStepStreamResult(
                final_graph=graph,
                records=tuple(records),
                supply_records=tuple(supply_records),
                stop_reason="graph_not_advanced",
                steps_attempted=len(records),
            )

        graph = step_result.graph
