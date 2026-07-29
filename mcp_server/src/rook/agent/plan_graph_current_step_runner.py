"""LM4R current-step thread-and-record primitive.

Consumes one canonical StepMappingResult for the current graph snapshot, delegates exactly
once to LM4Q execute_mapped_step, and returns execution.graph plus a flattened
non-authoritative audit record. No selection, revalidation, mapping, sequence fold,
evaluation, fallback, or terminal construction lives here.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_executor import StepExecutionResult, execute_mapped_step
from rook.agent.plan_graph_step_mapping import StepMappingResult
from rook.learning.plan_graph_revalidation import RevalidationResult

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


MetadataStatus = Literal["absent", "copied", "invalid", "copy_failed"]


@dataclass(frozen=True)
class CurrentStepEnvelope:
    mapping: StepMappingResult
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CurrentStepRecord:
    metadata: dict[str, Any] | None
    metadata_status: MetadataStatus
    metadata_error: str | None

    mapping: StepMappingResult
    revalidation: RevalidationResult
    execution: StepExecutionResult

    supplied_selected_node_id: str | None
    fresh_selected_node_id: str | None
    accepted_node_id: str | None
    mapping_mapped: bool
    mapping_failure: str | None
    mapped_step_target: str | None
    ran: bool
    execution_kind: str | None
    execution_failure: str | None

    producer_node_id: str | None
    producer_tool_name: str | None
    producer_applied: bool | None
    producer_outcome_status: str | None
    producer_reason: str | None
    verifier_node_id: str | None
    verifier_source_node_id: str | None
    verifier_applied: bool | None
    verifier_outcome_status: str | None
    verifier_reason: str | None
    bind_node_id: str | None
    bind_applied: bool | None
    bind_reason: str | None


@dataclass(frozen=True)
class CurrentStepResult:
    graph: "PlanGraph"
    record: CurrentStepRecord


def _copy_metadata(metadata: Any) -> tuple[dict[str, Any] | None, MetadataStatus, str | None]:
    if metadata is None:
        return None, "absent", None
    if not isinstance(metadata, Mapping):
        return None, "invalid", None
    try:
        return deepcopy(dict(metadata)), "copied", None
    except Exception as exc:
        return None, "copy_failed", f"{exc.__class__.__name__}: {exc}"


def _mapped_step_target(step: Any) -> str | None:
    if isinstance(step, VerifierStep):
        return step.verifier_node_id
    if isinstance(step, (ProducerStep, BindStep)):
        return step.node_id
    return None


def project_current_step_record(
    envelope: CurrentStepEnvelope,
    execution: StepExecutionResult,
) -> CurrentStepRecord:
    """Flatten one supplied mapping and its exact execution into the native record."""
    if type(envelope) is not CurrentStepEnvelope:
        raise TypeError("envelope must be the exact CurrentStepEnvelope type")
    if type(execution) is not StepExecutionResult:
        raise TypeError("execution must be the exact StepExecutionResult type")
    if execution.mapping is not envelope.mapping:
        raise ValueError("execution mapping must be the supplied envelope mapping")

    metadata, metadata_status, metadata_error = _copy_metadata(envelope.metadata)
    mapping = envelope.mapping
    revalidation = mapping.revalidation
    proposal = revalidation.proposal
    fresh = revalidation.fresh_proposal
    producer = execution.producer_result
    verifier = execution.verifier_result
    bind = execution.bind_result
    return CurrentStepRecord(
        metadata=metadata,
        metadata_status=metadata_status,
        metadata_error=metadata_error,
        mapping=mapping,
        revalidation=revalidation,
        execution=execution,
        supplied_selected_node_id=proposal.selected_node_id,
        fresh_selected_node_id=fresh.selected_node_id if fresh is not None else None,
        accepted_node_id=mapping.accepted_node_id,
        mapping_mapped=mapping.mapped,
        mapping_failure=mapping.failure,
        mapped_step_target=_mapped_step_target(mapping.step),
        ran=execution.ran,
        execution_kind=execution.kind,
        execution_failure=execution.failure,
        producer_node_id=producer.node_id if producer is not None else None,
        producer_tool_name=producer.tool_name if producer is not None else None,
        producer_applied=producer.applied if producer is not None else None,
        producer_outcome_status=(
            producer.outcome_status if producer is not None else None
        ),
        producer_reason=producer.reason if producer is not None else None,
        verifier_node_id=(
            verifier.verifier_node_id if verifier is not None else None
        ),
        verifier_source_node_id=(
            verifier.source_node_id if verifier is not None else None
        ),
        verifier_applied=verifier.applied if verifier is not None else None,
        verifier_outcome_status=(
            verifier.outcome_status if verifier is not None else None
        ),
        verifier_reason=verifier.reason if verifier is not None else None,
        bind_node_id=bind.node_id if bind is not None else None,
        bind_applied=bind.applied if bind is not None else None,
        bind_reason=bind.reason if bind is not None else None,
    )


async def run_current_mapped_step(
    envelope: CurrentStepEnvelope,
    graph: "PlanGraph",
    runner: SupportsLiveProducerNode | None = None,
) -> CurrentStepResult:
    """Run one already-mapped current step through LM4Q and record observations."""
    execution = await execute_mapped_step(envelope.mapping, graph, runner)
    record = project_current_step_record(envelope, execution)
    return CurrentStepResult(graph=execution.graph, record=record)
