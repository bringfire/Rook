"""LM3E verifier-step runner -- first composition layer over the PlanGraph primitives.

A single cross-node primitive that drives one verifier node by reading a source
node's already-captured evidence, projecting it through the LM3D verifier adapter
(``script_receipt_verifier_outcome``), and applying the result through the LM1E
reducer (``apply_outcome``).

It is not a scheduler and not a sequencer: it applies exactly one verifier step.
``runnable_nodes`` is the sole readiness authority -- the runner never inspects
edges or requires ``source.status == "succeeded"``; the source node only needs to
exist and carry evidence. The walker and LM1F are untouched; receipt
interpretation stays in LM3D.

Imports only ``rook.learning.plan_graph`` (types + reducer) and
``rook.learning.plan_graph_verifiers`` (the verifier adapter).
"""

from dataclasses import dataclass
from typing import Literal

from rook.learning.plan_graph import (
    OutcomeStatus,
    PlanGraph,
    apply_outcome,
    runnable_nodes,
)
from rook.learning.plan_graph_projection import (
    OUTCOME_PROJECTION_ROLE_KEY,
    project_receipt_outcome,
    projection_role_for_node,
)
from rook.learning.plan_graph_verifiers import script_receipt_verifier_outcome


VerifierStepReason = Literal[
    "unknown_verifier_node",
    "unknown_source_node",
    "source_evidence_missing",
    "verifier_not_runnable",
]


@dataclass(frozen=True)
class VerifierStepResult:
    graph: PlanGraph
    applied: bool
    verifier_node_id: str
    source_node_id: str
    outcome_status: OutcomeStatus | None
    reason: VerifierStepReason | None


def _not_applied(
    graph: PlanGraph,
    verifier_node_id: str,
    source_node_id: str,
    reason: VerifierStepReason,
) -> VerifierStepResult:
    return VerifierStepResult(
        graph=graph,
        applied=False,
        verifier_node_id=verifier_node_id,
        source_node_id=source_node_id,
        outcome_status=None,
        reason=reason,
    )


def apply_verifier_step(
    graph: PlanGraph, verifier_node_id: str, source_node_id: str
) -> VerifierStepResult:
    """Apply one verifier node's outcome, derived from a source node's evidence.

    Reads ``source_node_id``'s captured ``NodeEvidence``, projects it through the
    LM3D verifier adapter, and applies the result to ``verifier_node_id`` via the
    reducer. ``runnable_nodes`` is the sole readiness authority. Never mutates the
    input graph: a not-applied result returns the input unchanged; an applied
    result returns the reducer's fresh graph.
    """
    if verifier_node_id not in graph.nodes:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "unknown_verifier_node"
        )
    if source_node_id not in graph.nodes:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "unknown_source_node"
        )

    source_evidence = graph.nodes[source_node_id].evidence
    if source_evidence is None:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "source_evidence_missing"
        )

    runnable_ids = {node.id for node in runnable_nodes(graph)}
    if verifier_node_id not in runnable_ids:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "verifier_not_runnable"
        )

    outcome = script_receipt_verifier_outcome(source_evidence)
    new_graph = apply_outcome(graph, verifier_node_id, outcome)
    return VerifierStepResult(
        graph=new_graph,
        applied=True,
        verifier_node_id=verifier_node_id,
        source_node_id=source_node_id,
        outcome_status=outcome.status,
        reason=None,
    )


ProducerStepReason = Literal[
    "unknown_node",
    "node_not_runnable",
    "evidence_missing",
    "role_missing",
    "role_invalid",
    "role_not_producer",
]


@dataclass(frozen=True)
class ProducerStepResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    outcome_status: OutcomeStatus | None
    reason: ProducerStepReason | None


def _producer_not_applied(
    graph: PlanGraph, node_id: str, reason: ProducerStepReason
) -> ProducerStepResult:
    return ProducerStepResult(
        graph=graph,
        applied=False,
        node_id=node_id,
        outcome_status=None,
        reason=reason,
    )


def apply_producer_step(graph: PlanGraph, node_id: str) -> ProducerStepResult:
    """Apply one producer node's outcome, projected from its OWN captured evidence.

    Producer-restricted: the node must declare
    ``metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_producer"``. Reads the
    node's own ``NodeEvidence``, projects it through the LM3F producer projection,
    and applies the result via the reducer. ``runnable_nodes`` is the sole
    readiness authority; the guard order is fixed (existence -> runnable ->
    evidence -> role) so readiness precedes data diagnostics. Never mutates the
    input graph: not-applied returns the input unchanged; applied returns the
    reducer's fresh graph.
    """
    if node_id not in graph.nodes:
        return _producer_not_applied(graph, node_id, "unknown_node")

    runnable_ids = {node.id for node in runnable_nodes(graph)}
    if node_id not in runnable_ids:
        return _producer_not_applied(graph, node_id, "node_not_runnable")

    node = graph.nodes[node_id]
    if node.evidence is None:
        return _producer_not_applied(graph, node_id, "evidence_missing")

    present = OUTCOME_PROJECTION_ROLE_KEY in node.metadata
    role = projection_role_for_node(node)
    if not present:
        return _producer_not_applied(graph, node_id, "role_missing")
    if role is None:
        return _producer_not_applied(graph, node_id, "role_invalid")
    if role != "artifact_producer":
        return _producer_not_applied(graph, node_id, "role_not_producer")

    outcome = project_receipt_outcome(node.evidence, "artifact_producer")
    new_graph = apply_outcome(graph, node_id, outcome)
    return ProducerStepResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        outcome_status=outcome.status,
        reason=None,
    )
