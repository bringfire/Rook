from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import PlanGraph


TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.expected_output_value"
)
TRANSFORM_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.offset_value"
)
TRANSFORM_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_transform_output.projection"
)
TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.observed_output_value"
)
TRANSFORM_EDITABLE_VALUE_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.editable_value"
)
TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
TRANSFORM_CONVENTION_SOURCE_PATH = "gh_scalar_transform_set_value_convention"

EXPECTED_PROJECTION = {
    "projection_id": "editable_plus_offset",
    "description": "observed_output = editable_value + offset_value",
    "editable_variable": "editable_value",
    "offset_variable": "offset_value",
    "output_variable": "observed_output",
}


@dataclass(frozen=True)
class GhScalarTransformExpectationSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class GhScalarTransformExpectationSources:
    expected_output_contract: GhScalarTransformExpectationSource
    offset_contract: GhScalarTransformExpectationSource
    projection_contract: GhScalarTransformExpectationSource
    observed_output: GhScalarTransformExpectationSource
    editable_observation: GhScalarTransformExpectationSource
    fixture_anchor: GhScalarTransformExpectationSource
    convention: GhScalarTransformExpectationSource | None = None


def extract_gh_scalar_transform_expectation_sources(
    *,
    workflow_contract_payload: Mapping[str, Any],
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarTransformExpectationSources:
    return GhScalarTransformExpectationSources(
        expected_output_contract=GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
            value=_expected_output_value(workflow_contract_payload),
        ),
        offset_contract=GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
            value=_offset_value(workflow_contract_payload),
        ),
        projection_contract=GhScalarTransformExpectationSource(
            source_class="expected_output_contract",
            source_path=TRANSFORM_PROJECTION_SOURCE_PATH,
            value=_projection(workflow_contract_payload),
        ),
        observed_output=GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
            value=_observed_output_value(graph),
        ),
        editable_observation=GhScalarTransformExpectationSource(
            source_class="receipt_observation",
            source_path=TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
            value=_editable_value(graph),
        ),
        fixture_anchor=GhScalarTransformExpectationSource(
            source_class="fixture_anchor",
            source_path=TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH,
            value=_editable_value_contract(graph),
        ),
        convention=_convention_source(convention_packets),
    )


def _rule(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    rules = payload.get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError(f"{TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH} rules missing")
    verify = rules.get("verify_scalar_transform_output")
    if not isinstance(verify, Mapping):
        raise ValueError(f"{TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH} rule missing")
    return verify


def _expected_output_value(payload: Mapping[str, Any]) -> float | int:
    return _finite_number(
        _rule(payload).get("expected_output_value"),
        TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH,
    )


def _offset_value(payload: Mapping[str, Any]) -> float | int:
    return _finite_number(
        _rule(payload).get("offset_value"),
        TRANSFORM_OFFSET_VALUE_SOURCE_PATH,
    )


def _projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projection = _rule(payload).get("projection")
    if not isinstance(projection, Mapping):
        raise ValueError(f"{TRANSFORM_PROJECTION_SOURCE_PATH} missing")
    copied = dict(projection)
    if copied != EXPECTED_PROJECTION:
        raise ValueError(f"{TRANSFORM_PROJECTION_SOURCE_PATH} invalid")
    return copied


def _receipt(graph: PlanGraph) -> Mapping[str, Any]:
    if "create_scalar_transform" not in graph.nodes:
        raise ValueError(f"{TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH} node missing")
    evidence = graph.nodes["create_scalar_transform"].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        raise ValueError(f"{TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH} receipt missing")
    return evidence.receipt


def _observed_output_value(graph: PlanGraph) -> float | int:
    return _finite_number(
        _receipt(graph).get("observed_output_value"),
        TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH,
    )


def _editable_value(graph: PlanGraph) -> float | int:
    return _finite_number(
        _receipt(graph).get("editable_value"),
        TRANSFORM_EDITABLE_VALUE_SOURCE_PATH,
    )


def _editable_value_contract(graph: PlanGraph) -> dict[str, Any]:
    receipt = _receipt(graph)
    anchor = receipt.get("scalar_anchor")
    if not isinstance(anchor, Mapping):
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} scalar_anchor missing")
    contract = anchor.get("editable_value_contract")
    if not isinstance(contract, Mapping):
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} missing")
    copied = dict(contract)
    if "component_guid" in copied or "guid" in copied:
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} must not expose guid")
    required = {
        "label",
        "value_type",
        "current_value",
        "projection_id",
    }
    if set(copied) != required:
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} invalid fields")
    if copied["value_type"] != "number":
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} value_type invalid")
    _finite_number(copied["current_value"], TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH)
    if copied["projection_id"] != "editable_plus_offset":
        raise ValueError(f"{TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH} projection_id invalid")
    return copied


def _convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarTransformExpectationSource | None:
    matches = [
        packet
        for packet in convention_packets
        if getattr(packet, "packet_id", None) == TRANSFORM_CONVENTION_SOURCE_PATH
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"{TRANSFORM_CONVENTION_SOURCE_PATH} ambiguous")
    packet = matches[0]
    return GhScalarTransformExpectationSource(
        source_class="convention",
        source_path=TRANSFORM_CONVENTION_SOURCE_PATH,
        value=(
            dict(packet.content)
            if isinstance(packet.content, Mapping)
            else packet.content
        ),
    )


def _finite_number(value: Any, source_path: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{source_path} must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{source_path} must be a finite number")
    return value


__all__ = (
    "TRANSFORM_EXPECTED_OUTPUT_SOURCE_PATH",
    "TRANSFORM_OFFSET_VALUE_SOURCE_PATH",
    "TRANSFORM_PROJECTION_SOURCE_PATH",
    "TRANSFORM_OBSERVED_OUTPUT_SOURCE_PATH",
    "TRANSFORM_EDITABLE_VALUE_SOURCE_PATH",
    "TRANSFORM_FIXTURE_ANCHOR_SOURCE_PATH",
    "TRANSFORM_CONVENTION_SOURCE_PATH",
    "GhScalarTransformExpectationSource",
    "GhScalarTransformExpectationSources",
    "extract_gh_scalar_transform_expectation_sources",
)
