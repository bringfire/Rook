"""LM4H pure composition guard — CI contract over the live producer→verifier handoff.

Constructs producer-applied state through `apply_outcome` (SYNTHETIC evidence, not
live capture) on the registered 3-node gh_csharp_create_verify_repair template,
proves the requires-edge unlock into verify_create, then composes LM4G's record
builder with LM3E's verifier step and asserts the on_repair unlock into repair.

This is a composition contract: the registered template topology + LM4G record
builder + LM3E verifier step still compose as LM4H expects. It is NOT a live-capture
proof — the live truth is test_live_producer_verifier_handoff_live.py.

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph import NodeEvidence, NodeOutcome, apply_outcome
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair",
    "language": "csharp",
}


def _broken_producer_evidence() -> NodeEvidence:
    """Synthetic evidence mirroring a live created_with_errors capture shape."""
    return NodeEvidence(
        tool_status="failed",
        verified=False,
        receipt={"artifact_status": "created_with_errors"},
        repair_anchor={"component_guid": "pure-guard-guid"},
    )


def test_live_handoff_composition_contract():
    # Registry path + template contract pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"

    # Construct producer-applied state THROUGH the reducer (proves requires unlock).
    applied = apply_outcome(
        graph,
        "create_script",
        NodeOutcome(status="succeeded", evidence=_broken_producer_evidence()),
    )
    assert applied.nodes["create_script"].status == "succeeded"
    assert applied.nodes["verify_create"].status == "ready"  # requires-edge unlock

    # LM4G record builder over the graph-bearing synthetic result.
    result = LiveProducerResult(
        graph=applied,
        applied=True,
        node_id="create_script",
        tool_name="gh_create_script",
        outcome_status="succeeded",
        reason=None,
    )
    expectation = LiveProducerExpectation(
        outcome_status="succeeded",
        node_status="succeeded",
        tool_status="failed",
        verified=False,
        artifact_status="created_with_errors",
    )
    record = build_live_producer_record(result, expectation)
    assert record.evaluated is True
    assert record.passed is True, f"mismatches={record.mismatches!r}"
    assert record.tool_status == "failed"
    assert record.artifact_status == "created_with_errors"

    # LM3E verifier step over the producer evidence -> on_repair unlock.
    verifier_step = apply_verifier_step(applied, "verify_create", "create_script")
    assert verifier_step.applied is True
    assert verifier_step.outcome_status == "needs_repair"
    assert verifier_step.graph.nodes["verify_create"].status == "needs_repair"
    assert verifier_step.graph.nodes["repair_same_component"].status == "ready"
