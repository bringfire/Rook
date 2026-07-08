from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.learning.plan_graph import PlanGraph


EXPECTED_OUTPUT_SOURCE_PATH = (
    "workflow_contract.rules.verify_scalar_output.expected_output_value"
)
OBSERVED_OUTPUT_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.observed_output_value"
)
FIXTURE_ANCHOR_SOURCE_PATH = (
    "create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract"
)
CONVENTION_SOURCE_PATH = "gh_set_value_scalar_convention"


@dataclass(frozen=True)
class GhScalarExpectationSource:
    source_class: str
    source_path: str
    value: Any


@dataclass(frozen=True)
class GhScalarExpectationSources:
    expected_output_contract: GhScalarExpectationSource
    receipt_observation: GhScalarExpectationSource
    fixture_anchor: GhScalarExpectationSource
    convention: GhScalarExpectationSource | None = None


def extract_gh_scalar_expectation_sources(
    *,
    workflow_contract_payload: Mapping[str, Any],
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarExpectationSources:
    return GhScalarExpectationSources(
        expected_output_contract=GhScalarExpectationSource(
            source_class="expected_output_contract",
            source_path=EXPECTED_OUTPUT_SOURCE_PATH,
            value=_expected_output_value(workflow_contract_payload),
        ),
        receipt_observation=GhScalarExpectationSource(
            source_class="receipt_observation",
            source_path=OBSERVED_OUTPUT_SOURCE_PATH,
            value=_observed_output_value(graph),
        ),
        fixture_anchor=GhScalarExpectationSource(
            source_class="fixture_anchor",
            source_path=FIXTURE_ANCHOR_SOURCE_PATH,
            value=_editable_value_contract(graph),
        ),
        convention=_convention_source(convention_packets),
    )


def _expected_output_value(payload: Mapping[str, Any]) -> float | int:
    rules = payload.get("rules")
    if not isinstance(rules, Mapping):
        raise ValueError(f"{EXPECTED_OUTPUT_SOURCE_PATH} rules missing")
    verify = rules.get("verify_scalar_output")
    if not isinstance(verify, Mapping):
        raise ValueError(f"{EXPECTED_OUTPUT_SOURCE_PATH} rule missing")
    return _finite_number(
        verify.get("expected_output_value"), EXPECTED_OUTPUT_SOURCE_PATH
    )


def _receipt(graph: PlanGraph) -> Mapping[str, Any]:
    if "create_scalar_expectation" not in graph.nodes:
        raise ValueError(f"{OBSERVED_OUTPUT_SOURCE_PATH} node missing")
    evidence = graph.nodes["create_scalar_expectation"].evidence
    if evidence is None or not isinstance(evidence.receipt, Mapping):
        raise ValueError(f"{OBSERVED_OUTPUT_SOURCE_PATH} receipt missing")
    return evidence.receipt


def _observed_output_value(graph: PlanGraph) -> float | int:
    return _finite_number(
        _receipt(graph).get("observed_output_value"), OBSERVED_OUTPUT_SOURCE_PATH
    )


def _editable_value_contract(graph: PlanGraph) -> dict[str, Any]:
    receipt = _receipt(graph)
    anchor = receipt.get("scalar_anchor")
    if not isinstance(anchor, Mapping):
        raise ValueError(f"{FIXTURE_ANCHOR_SOURCE_PATH} scalar_anchor missing")
    contract = anchor.get("editable_value_contract")
    if not isinstance(contract, Mapping):
        raise ValueError(f"{FIXTURE_ANCHOR_SOURCE_PATH} missing")
    copied = dict(contract)
    if "component_guid" in copied or "guid" in copied:
        raise ValueError(f"{FIXTURE_ANCHOR_SOURCE_PATH} must not expose guid")
    return copied


def _convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> GhScalarExpectationSource | None:
    matches = [
        packet
        for packet in convention_packets
        if getattr(packet, "packet_id", None) == CONVENTION_SOURCE_PATH
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"{CONVENTION_SOURCE_PATH} ambiguous")
    packet = matches[0]
    return GhScalarExpectationSource(
        source_class="convention",
        source_path=CONVENTION_SOURCE_PATH,
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
    "GhScalarExpectationSource",
    "GhScalarExpectationSources",
    "EXPECTED_OUTPUT_SOURCE_PATH",
    "OBSERVED_OUTPUT_SOURCE_PATH",
    "FIXTURE_ANCHOR_SOURCE_PATH",
    "CONVENTION_SOURCE_PATH",
    "extract_gh_scalar_expectation_sources",
)
