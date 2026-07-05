from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rook.agent.local_worker_acceptance_criteria import (
    AcceptanceCriteriaSource,
    AcceptanceCriteriaSources,
)
from rook.agent.local_worker_turn_context import WorkerKnowledgePacket
from rook.agent.plan_graph_workflow_contract import (
    RookWorkflowContract,
    VerifierStepSpec,
)
from rook.learning.plan_graph import PlanGraph


PIN_SOURCE_PATH = "create_script.initial_execution_params.pins_out"
VERIFY_SOURCE_PATH = "workflow_contract.rules.verify_repair.expected_outcome"
DIAGNOSTIC_SOURCE_PATH = (
    "create_script.receipt.script_receipt.repair_anchor.target_errors"
)
CONVENTION_SOURCE_PATH = "script_body_gotcha"


def extract_acceptance_criteria_sources(
    *,
    workflow_contract: RookWorkflowContract,
    graph: PlanGraph,
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> AcceptanceCriteriaSources:
    return AcceptanceCriteriaSources(
        pin_contract=_extract_pin_contract_source(workflow_contract),
        verifier_outcome=_extract_verifier_outcome_source(workflow_contract),
        receipt_diagnostic=_extract_receipt_diagnostic_source(graph),
        convention=_extract_convention_source(convention_packets),
        unresolved_intent=(),
    )


def _extract_pin_contract_source(
    workflow_contract: RookWorkflowContract,
) -> AcceptanceCriteriaSource:
    matches = [
        initial
        for initial in workflow_contract.initial_params
        if initial.node_id == "create_script"
    ]
    if len(matches) != 1:
        raise ValueError(f"{PIN_SOURCE_PATH} missing or ambiguous")
    params = matches[0].execution_params
    if not isinstance(params, Mapping):
        raise ValueError(f"{PIN_SOURCE_PATH} params not mapping")
    pins_out = params.get("pins_out")
    if not isinstance(pins_out, list) or not all(
        isinstance(pin, str) for pin in pins_out
    ):
        raise ValueError(f"{PIN_SOURCE_PATH} not list[str]")
    return AcceptanceCriteriaSource(
        source_class="pin_contract",
        source_path=PIN_SOURCE_PATH,
        value={"pins_out": list(pins_out)},
    )


def _extract_verifier_outcome_source(
    workflow_contract: RookWorkflowContract,
) -> AcceptanceCriteriaSource:
    rules = [rule for rule in workflow_contract.rules if rule.node_id == "verify_repair"]
    if len(rules) != 1:
        raise ValueError(f"{VERIFY_SOURCE_PATH} missing or ambiguous")
    verifier_steps = [
        step for step in rules[0].steps_by_seen_count if isinstance(step, VerifierStepSpec)
    ]
    expected_outcomes = [
        step.expected_outcome
        for step in verifier_steps
        if step.expected_outcome is not None
    ]
    if len(expected_outcomes) != 1:
        raise ValueError(f"{VERIFY_SOURCE_PATH} missing or ambiguous")
    expected = expected_outcomes[0]
    if not isinstance(expected, str) or not expected:
        raise ValueError(f"{VERIFY_SOURCE_PATH} not non-empty string")
    return AcceptanceCriteriaSource(
        source_class="verifier_outcome",
        source_path=VERIFY_SOURCE_PATH,
        value=expected,
    )


def _extract_receipt_diagnostic_source(graph: PlanGraph) -> AcceptanceCriteriaSource:
    if "create_script" not in graph.nodes:
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} create_script missing")
    evidence = graph.nodes["create_script"].evidence
    if evidence is None:
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} evidence missing")
    receipt = getattr(evidence, "receipt", None)
    if not isinstance(receipt, Mapping):
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} receipt missing")
    repair_anchor = receipt.get("repair_anchor")
    if not isinstance(repair_anchor, Mapping):
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} repair_anchor missing")
    target_errors = repair_anchor.get("target_errors")
    if not isinstance(target_errors, list) or not all(
        isinstance(item, str) for item in target_errors
    ):
        raise ValueError(f"{DIAGNOSTIC_SOURCE_PATH} not list[str]")
    return AcceptanceCriteriaSource(
        source_class="receipt_diagnostic",
        source_path=DIAGNOSTIC_SOURCE_PATH,
        value=list(target_errors),
    )


def _extract_convention_source(
    convention_packets: Sequence[WorkerKnowledgePacket],
) -> AcceptanceCriteriaSource:
    candidates = [
        packet
        for packet in convention_packets
        if packet.packet_id == "script_body_gotcha"
    ]
    if len(candidates) != 1:
        raise ValueError(f"{CONVENTION_SOURCE_PATH} missing or ambiguous")
    packet = candidates[0]
    if packet.kind != "gotcha":
        raise ValueError(f"{CONVENTION_SOURCE_PATH} unexpected kind")
    if packet.title != "C# script components use body-style code":
        raise ValueError(f"{CONVENTION_SOURCE_PATH} unexpected title")
    return AcceptanceCriteriaSource(
        source_class="convention",
        source_path=CONVENTION_SOURCE_PATH,
        value={"mode": "body"},
    )


__all__ = ("extract_acceptance_criteria_sources",)
