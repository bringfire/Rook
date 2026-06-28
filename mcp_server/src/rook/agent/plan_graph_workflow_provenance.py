"""LM4Z workflow provenance overlay for current-step envelope sources.

This module bridges compiled workflow receipts into LM4S/LM4R metadata only.
It does not run streams, compile contracts, select nodes, map steps, execute
steps, mutate graphs, evaluate results, or apply terminal nodes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_current_step_provider import (
    CATALOG_CURRENT_STEP_PROVIDER_ID,
)
from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
)
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSource,
    EnvelopeSupplyRecord,
    EnvelopeSupplyResult,
)
from rook.agent.plan_graph_workflow_contract import CompiledWorkflowScaffold

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


WORKFLOW_PROVENANCE_METADATA_KEY = "workflow_provenance"
WORKFLOW_PROVENANCE_METADATA_INVALID_REASON = (
    "workflow_provenance_metadata_invalid"
)
WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON = (
    "workflow_provenance_metadata_collision:workflow_provenance"
)

_ERROR_KEY = "workflow_provenance_error"
_ERROR_LOCATION_KEY = "workflow_provenance_error_location"
_COLLISION_KEY = "workflow_provenance_collision_key"


@dataclass(frozen=True)
class WorkflowProvenanceEnvelopeSource:
    scaffold: CompiledWorkflowScaffold
    source: EnvelopeSource | None = None
    _provenance: Mapping[str, Any] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scaffold, CompiledWorkflowScaffold):
            raise TypeError("scaffold must be CompiledWorkflowScaffold")

        source = self.source if self.source is not None else self.scaffold.provider
        if not callable(source):
            raise TypeError("source must be callable")

        _validate_scaffold_receipt(self.scaffold)
        object.__setattr__(self, "source", source)
        object.__setattr__(
            self,
            "_provenance",
            _provenance_payload(self.scaffold),
        )

    def __call__(
        self,
        graph: "PlanGraph",
        records: tuple[CurrentStepRecord, ...],
        supply_records: tuple[EnvelopeSupplyRecord, ...],
    ) -> EnvelopeSupplyResult:
        supplied = self.source(graph, records, supply_records)
        if not isinstance(supplied, EnvelopeSupplyResult):
            return supplied

        supply_metadata, invalid = _merge_metadata(
            supplied.metadata,
            self._provenance,
            location="supply",
        )
        if invalid is not None:
            return invalid

        envelope = supplied.envelope
        if supplied.decision == "SUPPLY" and envelope is not None:
            envelope_metadata, invalid = _merge_metadata(
                envelope.metadata,
                self._provenance,
                location="envelope",
            )
            if invalid is not None:
                return invalid
            envelope = CurrentStepEnvelope(
                mapping=envelope.mapping,
                metadata=envelope_metadata,
            )

        return EnvelopeSupplyResult(
            supplied.decision,
            envelope,
            supplied.reason,
            supply_metadata,
        )


def _validate_scaffold_receipt(scaffold: CompiledWorkflowScaffold) -> None:
    record = scaffold.compile_record
    snapshot = scaffold.contract_snapshot
    if record.contract_fingerprint != snapshot.contract_fingerprint:
        raise ValueError("compile record fingerprint does not match snapshot")
    if record.contract_schema != snapshot.normalized_contract["schema"]:
        raise ValueError("compile record schema does not match snapshot")
    if record.workflow_id != scaffold.workflow_id:
        raise ValueError("compile record workflow_id does not match scaffold")
    if record.workflow_id != snapshot.workflow_id:
        raise ValueError("compile record workflow_id does not match snapshot")
    if record.provider_id != CATALOG_CURRENT_STEP_PROVIDER_ID:
        raise ValueError("compile record provider_id does not match catalog provider")


def _provenance_payload(scaffold: CompiledWorkflowScaffold) -> Mapping[str, Any]:
    record = scaffold.compile_record
    return {
        "workflow_id": record.workflow_id,
        "contract_schema": record.contract_schema,
        "contract_fingerprint": record.contract_fingerprint,
        "compiler_id": record.compiler_id,
        "provider_id": record.provider_id,
        "selected_template_id": record.selected_template_id,
    }


def _merge_metadata(
    metadata: Any,
    provenance: Mapping[str, Any],
    *,
    location: str,
) -> tuple[dict[str, Any], EnvelopeSupplyResult | None]:
    if metadata is None:
        return {WORKFLOW_PROVENANCE_METADATA_KEY: dict(provenance)}, None
    if not isinstance(metadata, Mapping):
        return {}, _invalid_metadata_result(
            provenance,
            error="metadata_invalid",
            location=location,
        )
    if WORKFLOW_PROVENANCE_METADATA_KEY in metadata:
        return {}, _invalid_metadata_result(
            provenance,
            error="metadata_collision",
            location=location,
        )

    merged = dict(metadata)
    merged[WORKFLOW_PROVENANCE_METADATA_KEY] = dict(provenance)
    return merged, None


def _invalid_metadata_result(
    provenance: Mapping[str, Any],
    *,
    error: str,
    location: str,
) -> EnvelopeSupplyResult:
    metadata = {
        WORKFLOW_PROVENANCE_METADATA_KEY: dict(provenance),
        _ERROR_KEY: error,
        _ERROR_LOCATION_KEY: location,
    }
    if error == "metadata_collision":
        metadata[_COLLISION_KEY] = WORKFLOW_PROVENANCE_METADATA_KEY

    reason = (
        WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON
        if error == "metadata_collision"
        else WORKFLOW_PROVENANCE_METADATA_INVALID_REASON
    )
    return EnvelopeSupplyResult("SUPPLY", None, reason, metadata)
