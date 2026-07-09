from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import PlanGraph


AFFINE_EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.expected_output_value"
)
AFFINE_FACTOR_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.factor_value"
)
AFFINE_OFFSET_VALUE_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.offset_value"
)
AFFINE_PROJECTION_SOURCE_PATH = (
    "workflow_contract.rules.verify_affine_scalar_transform_output.projection"
)
AFFINE_OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.observed_output_value"
)
AFFINE_EDITABLE_VALUE_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.editable_value"
)
AFFINE_FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_affine_scalar_transform.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
AFFINE_CONVENTION_SOURCE_PATH = "gh_affine_scalar_transform_set_value_convention"

EXPECTED_AFFINE_PROJECTION = {
    "projection_id": "editable_times_factor_plus_offset",
    "description": "observed_output = editable_value * factor_value + offset_value",
    "editable_variable": "editable_value",
    "factor_variable": "factor_value",
    "offset_variable": "offset_value",
    "output_variable": "observed_output",
}


@dataclass(frozen=True)
class GhAffineScalarTransformExpectationSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class GhAffineScalarTransformExpectationSources:
    expected_output_contract: GhAffineScalarTransformExpectationSource
    factor_contract: GhAffineScalarTransformExpectationSource
    offset_contract: GhAffineScalarTransformExpectationSource
    projection_contract: GhAffineScalarTransformExpectationSource
    observed_output: GhAffineScalarTransformExpectationSource
    editable_observation: GhAffineScalarTransformExpectationSource
    fixture_anchor: GhAffineScalarTransformExpectationSource
    convention: GhAffineScalarTransformExpectationSource | None = None


def extract_gh_affine_scalar_transform_expectation_sources(
    *,
    workflow_contract_payload: Mapping[str, Any],
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhAffineScalarTransformExpectationSources:
    return GhAffineScalarTransformExpectationSources(
        expected_output_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
            _rule_number(
                workflow_contract_payload,
                "expected_output_value",
                AFFINE_EXPECTED_OUTPUT_SOURCE_PATH,
            ),
        ),
        factor_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_FACTOR_VALUE_SOURCE_PATH,
            _rule_number(
                workflow_contract_payload,
                "factor_value",
                AFFINE_FACTOR_VALUE_SOURCE_PATH,
            ),
        ),
        offset_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_OFFSET_VALUE_SOURCE_PATH,
            _rule_number(
                workflow_contract_payload,
                "offset_value",
                AFFINE_OFFSET_VALUE_SOURCE_PATH,
            ),
        ),
        projection_contract=GhAffineScalarTransformExpectationSource(
            "expected_output_contract",
            AFFINE_PROJECTION_SOURCE_PATH,
            _projection(workflow_contract_payload),
        ),
        observed_output=GhAffineScalarTransformExpectationSource(
            "receipt_observation",
            AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
            _finite_number(
                _receipt(graph).get("observed_output_value"),
                AFFINE_OBSERVED_OUTPUT_SOURCE_PATH,
            ),
        ),
        editable_observation=GhAffineScalarTransformExpectationSource(
            "receipt_observation",
            AFFINE_EDITABLE_VALUE_SOURCE_PATH,
            _finite_number(
                _receipt(graph).get("editable_value"),
                AFFINE_EDITABLE_VALUE_SOURCE_PATH,
            ),
        ),
        fixture_anchor=GhAffineScalarTransformExpectationSource(
            "fixture_anchor",
            AFFINE_FIXTURE_ANCHOR_SOURCE_PATH,
            _editable_value_contract(graph),
        ),
        convention=_convention_source(convention_packets),
    )


def _rule(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    rules = payload.get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError(f"{AFFINE_EXPECTED_OUTPUT_SOURCE_PATH} rules missing")
    verify = rules.get("verify_affine_scalar_transform_output")
    if not isinstance(verify, Mapping):
        raise ValueError(f"{AFFINE_EXPECTED_OUTPUT_SOURCE_PATH} rule missing")
    return verify


def _rule_number(payload: Mapping[str, Any], key: str, path: str) -> float | int:
    return _finite_number(_rule(payload).get(key), path)


def _projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projection = _rule(payload).get("projection")
    if not isinstance(projection, Mapping):
        raise ValueError(f"{AFFINE_PROJECTION_SOURCE_PATH} missing")
    copied = dict(projection)
    if copied != EXPECTED_AFFINE_PROJECTION:
        raise ValueError(f"{AFFINE_PROJECTION_SOURCE_PATH} invalid")
    return copied


def _receipt(graph: PlanGraph) -> Mapping[str, Any]:
    if "create_affine_scalar_transform" not in graph.nodes:
        raise ValueError(f"{AFFINE_OBSERVED_OUTPUT_SOURCE_PATH} node missing")
    evidence = graph.nodes["create_affine_scalar_transform"].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        raise ValueError(f"{AFFINE_OBSERVED_OUTPUT_SOURCE_PATH} receipt missing")
    return evidence.receipt


def _editable_value_contract(graph: PlanGraph) -> dict[str, Any]:
    anchor = _receipt(graph).get("scalar_anchor")
    if not isinstance(anchor, Mapping):
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} scalar_anchor missing")
    _trusted_anchor_guid(anchor)
    contract = anchor.get("editable_value_contract")
    if not isinstance(contract, Mapping):
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} missing")
    copied = dict(contract)
    if "component_guid" in copied or "guid" in copied:
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} must not expose guid")
    required = {"label", "value_type", "current_value", "projection_id"}
    if set(copied) != required:
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} invalid fields")
    if copied["value_type"] != "number":
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} value_type invalid")
    _finite_number(copied["current_value"], AFFINE_FIXTURE_ANCHOR_SOURCE_PATH)
    if copied["projection_id"] != EXPECTED_AFFINE_PROJECTION["projection_id"]:
        raise ValueError(f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} projection_id invalid")
    return copied


def _trusted_anchor_guid(anchor: Mapping[str, Any]) -> str:
    component_guid_present = "component_guid" in anchor
    internal_guid_present = "internal_component_guid" in anchor
    if component_guid_present == internal_guid_present:
        raise ValueError(
            f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} trusted anchor guid invalid"
        )
    guid = (
        anchor["component_guid"]
        if component_guid_present
        else anchor["internal_component_guid"]
    )
    if not isinstance(guid, str) or not guid.strip():
        raise ValueError(
            f"{AFFINE_FIXTURE_ANCHOR_SOURCE_PATH} trusted anchor guid invalid"
        )
    return guid


def _convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhAffineScalarTransformExpectationSource | None:
    matches = [
        packet
        for packet in convention_packets
        if getattr(packet, "packet_id", None) == AFFINE_CONVENTION_SOURCE_PATH
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"{AFFINE_CONVENTION_SOURCE_PATH} ambiguous")
    packet = matches[0]
    return GhAffineScalarTransformExpectationSource(
        source_class="convention",
        source_path=AFFINE_CONVENTION_SOURCE_PATH,
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
    "AFFINE_EXPECTED_OUTPUT_SOURCE_PATH",
    "AFFINE_FACTOR_VALUE_SOURCE_PATH",
    "AFFINE_OFFSET_VALUE_SOURCE_PATH",
    "AFFINE_PROJECTION_SOURCE_PATH",
    "AFFINE_OBSERVED_OUTPUT_SOURCE_PATH",
    "AFFINE_EDITABLE_VALUE_SOURCE_PATH",
    "AFFINE_FIXTURE_ANCHOR_SOURCE_PATH",
    "AFFINE_CONVENTION_SOURCE_PATH",
    "EXPECTED_AFFINE_PROJECTION",
    "GhAffineScalarTransformExpectationSource",
    "GhAffineScalarTransformExpectationSources",
    "extract_gh_affine_scalar_transform_expectation_sources",
)
