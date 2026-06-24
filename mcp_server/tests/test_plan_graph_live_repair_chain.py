"""LM4I pure composition guard — CI contract over the full repair CHAIN.

Composes the registered 5-node gh_csharp_create_verify_repair_verify template to a
terminal `complete` graph status using SYNTHETIC evidence (not live capture):
create-producer (created_with_errors) -> verify_create -> repair-producer (usable)
-> verify_repair -> done. Interleaves LM4G's build_live_producer_record for BOTH
producer dispatches (the two-successes seam for create; the clean seam for repair).

This is a composition contract: the 5-node topology + reducer + LM3E verifier steps
+ LM4G record builder still compose to a reverified-clean terminal state. It is NOT a
live-capture proof -- the live truth is test_live_repair_chain_live.py.

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph import (
    NodeEvidence,
    NodeOutcome,
    apply_outcome,
    graph_status,
)
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "pure-guard-guid"


def _created_with_errors_evidence() -> NodeEvidence:
    """Synthetic evidence mirroring a live created_with_errors producer capture."""
    return NodeEvidence(
        tool_status="failed",
        verified=False,
        receipt={"artifact_status": "created_with_errors"},
        repair_anchor={"component_guid": _GUID},
    )


def _usable_evidence() -> NodeEvidence:
    """Synthetic evidence mirroring a live usable repair-producer capture.

    tool_status is None (not "success"): a successful gh_update_script result is
    MCP-unwrapped with no top-level success/ok marker, so the live capture reports
    tool_status=None. This synthetic shape mirrors that live truth (LM4I finding).
    """
    return NodeEvidence(
        tool_status=None,
        verified=True,
        receipt={"artifact_status": "usable"},
        repair_anchor={"component_guid": _GUID},
    )


def test_live_repair_chain_composition_contract():
    # Registry path + both declared producer refs pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # 1) create producer succeeds (created_with_errors) -> verify_create unlocks.
    graph = apply_outcome(
        graph,
        "create_script",
        NodeOutcome(status="succeeded", evidence=_created_with_errors_evidence()),
    )
    assert graph.nodes["create_script"].status == "succeeded"
    assert graph.nodes["verify_create"].status == "ready"

    create_record = build_live_producer_record(
        LiveProducerResult(
            graph=graph,
            applied=True,
            node_id="create_script",
            tool_name="gh_create_script",
            outcome_status="succeeded",
            reason=None,
        ),
        LiveProducerExpectation(
            outcome_status="succeeded",
            node_status="succeeded",
            tool_status="failed",
            verified=False,
            artifact_status="created_with_errors",
        ),
    )
    assert create_record.evaluated is True
    assert create_record.passed is True, f"mismatches={create_record.mismatches!r}"

    # 2) verify_create re-judges the producer evidence -> needs_repair, unlock repair.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.applied is True
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["verify_create"].status == "needs_repair"
    assert graph.nodes["repair_same_component"].status == "ready"

    # 3) repair producer succeeds (usable) -> verify_repair unlocks.
    graph = apply_outcome(
        graph,
        "repair_same_component",
        NodeOutcome(status="succeeded", evidence=_usable_evidence()),
    )
    assert graph.nodes["repair_same_component"].status == "succeeded"
    assert graph.nodes["verify_repair"].status == "ready"

    repair_record = build_live_producer_record(
        LiveProducerResult(
            graph=graph,
            applied=True,
            node_id="repair_same_component",
            tool_name="gh_update_script",
            outcome_status="succeeded",
            reason=None,
        ),
        LiveProducerExpectation(
            outcome_status="succeeded",
            node_status="succeeded",
            verified=True,
            artifact_status="usable",
        ),
    )
    assert repair_record.evaluated is True
    assert repair_record.passed is True, f"mismatches={repair_record.mismatches!r}"
    # Mirrors the live truth: unwrapped success carries no envelope marker.
    assert repair_record.tool_status is None

    # 4) verify_repair confirms clean -> done unlocks.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.applied is True
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["verify_repair"].status == "succeeded"
    assert graph.nodes["done"].status == "ready"

    # 5) terminal `done` marker -> graph complete.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
