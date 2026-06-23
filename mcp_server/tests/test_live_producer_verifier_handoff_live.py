"""LM4H live proof — real captured producer evidence drives the verifier handoff.

Drives a real RookAgent(_mcp_tool_executor) through run_live_producer_node against
the live gh_create_script tool on the registered 3-node gh_csharp_create_verify_repair
template, then hands the graph-bearing LiveProducerResult to LM3E's apply_verifier_step
and asserts the on_repair unlock into repair_same_component.

The slice's only live variable is the handoff. The live test overrides ONLY the
producer dispatch ref to the LM4E/LM4G-proven gh_create_script — it does NOT prove
gh_create_csharp_script live dispatch compatibility (a separate future slice). The
registered gh_create_csharp_script:v1 ref is asserted before the override so the
override is deliberate and template drift is caught.

requires_rhino: deselected from normal CI; fresh_document skips when Rhino is
unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_producer_verifier_handoff_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair",
    "language": "csharp",
}


async def test_live_producer_evidence_drives_verifier_handoff(fresh_document):
    # Registry path + template contract pinned before the deliberate override.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"

    # LM4H overrides ONLY the producer dispatch ref to reuse the proven
    # gh_create_script contract. It does NOT prove gh_create_csharp_script live.
    graph.nodes["create_script"].execution_ref = "gh_create_script"
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "language": "csharp",
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4HHandoffLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)
    producer_result = await agent.run_live_producer_node(graph, "create_script")

    # Durable producer record (LM4G) — the two-successes seam, live.
    expectation = LiveProducerExpectation(
        outcome_status="succeeded",
        node_status="succeeded",
        tool_status="failed",
        verified=False,
        artifact_status="created_with_errors",
    )
    producer_record = build_live_producer_record(producer_result, expectation)
    assert producer_record.evaluated is True
    assert producer_record.passed is True, f"mismatches={producer_record.mismatches!r}"
    assert producer_record.tool_status == "failed"
    assert producer_record.outcome_status == "succeeded"
    assert producer_record.node_status == "succeeded"
    assert producer_record.verified is False
    assert producer_record.artifact_status == "created_with_errors"

    # Handoff on producer_result.graph BEFORE the verifier step.
    assert producer_result.graph.nodes["create_script"].status == "succeeded"
    assert producer_result.graph.nodes["verify_create"].status == "ready"

    # LM3E verifier step over LIVE producer evidence -> on_repair unlock.
    verifier_step = apply_verifier_step(
        producer_result.graph, "verify_create", "create_script"
    )
    assert verifier_step.applied is True
    assert verifier_step.outcome_status == "needs_repair"
    assert verifier_step.graph.nodes["verify_create"].status == "needs_repair"
    assert verifier_step.graph.nodes["repair_same_component"].status == "ready"
