"""LM4I live proof -- two live producer dispatches drive the repair chain to complete.

Drives a real RookAgent(_mcp_tool_executor) through run_live_producer_node TWICE on
the registered 5-node gh_csharp_create_verify_repair_verify template: a live create
(broken body -> created_with_errors), then a live REPAIR (corrected body -> usable),
with pure LM3E verifier steps between/after, reaching terminal graph_status ==
"complete".

Live overrides: ONLY the create ref is swapped to the LM4E/LM4G-proven gh_create_script
(its declared gh_create_csharp_script is not proven live). The repair node keeps its
real declared ref gh_update_script:v1 -- _resolve_tool_name strips :v1 to the proven
gh_update_script -- so only its execution_params are hand-set, with the corrected body
and the repair target guid hand-wired from the live create evidence. This does NOT
prove gh_create_csharp_script live, nor automatic rolling-memory propagation.

requires_rhino: deselected from normal CI; fresh_document + _ensure_gh_document skip
when Rhino/GH are unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph import NodeOutcome, apply_outcome, graph_status
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


async def _ensure_gh_document() -> None:
    """Establish an ACTIVE Grasshopper document for the live producer dispatches.

    gh_create_script needs a GH document to place the component in; the
    `_Grasshopper` window being open is NOT sufficient, and `fresh_document`
    resets only the *Rhino* document. Skip (do not hard-fail, never silently
    ignore) when GH cannot provide a document.
    """
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_live_repair_chain_drives_to_complete(fresh_document):
    # Establish the live precondition explicitly (active GH document).
    await _ensure_gh_document()

    # Registry path + both declared producer refs pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # Override ONLY the create ref to the proven gh_create_script; broken body.
    graph.nodes["create_script"].execution_ref = "gh_create_script"
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "language": "csharp",
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4IRepairChainLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)

    # --- Live dispatch 1: create (broken) -> created_with_errors / succeeded. ---
    create_result = await agent.run_live_producer_node(graph, "create_script")
    # Direct claim: the create override resolved to the proven tool.
    assert create_result.tool_name == "gh_create_script"
    create_record = build_live_producer_record(
        create_result,
        LiveProducerExpectation(
            applied=True,
            outcome_status="succeeded",
            node_status="succeeded",
            tool_status="failed",
            verified=False,
            artifact_status="created_with_errors",
        ),
    )
    assert create_record.evaluated is True
    assert create_record.passed is True, f"mismatches={create_record.mismatches!r}"
    graph = create_result.graph
    assert graph.nodes["create_script"].status == "succeeded"
    assert graph.nodes["verify_create"].status == "ready"

    # --- Pure verifier step: verify_create -> needs_repair, unlock repair. ---
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.applied is True
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # --- Hand-wire the repair target guid from the live create evidence. ---
    create_anchor = graph.nodes["create_script"].evidence.repair_anchor
    assert create_anchor is not None
    repair_guid = create_anchor.get("component_guid")
    assert isinstance(repair_guid, str) and repair_guid

    # Repair node keeps its real declared ref (gh_update_script:v1 -> gh_update_script);
    # set only execution_params with the corrected body + the live target guid.
    graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] = {
        "guid": repair_guid,
        "code": "A = 42.0;",
        "mode": "body",
        "language": "csharp",
    }

    # --- Live dispatch 2: repair (corrected) -> usable / succeeded. ---
    repair_result = await agent.run_live_producer_node(graph, "repair_same_component")
    # Direct claim: the unchanged repair ref gh_update_script:v1 resolved (:v1
    # stripped) to the proven gh_update_script -- no override needed.
    assert repair_result.tool_name == "gh_update_script"
    repair_record = build_live_producer_record(
        repair_result,
        LiveProducerExpectation(
            applied=True,
            outcome_status="succeeded",
            node_status="succeeded",
            verified=True,
            artifact_status="usable",
        ),
    )
    assert repair_record.evaluated is True
    assert repair_record.passed is True, f"mismatches={repair_record.mismatches!r}"
    # LM4I live finding: a SUCCESSFUL gh_update_script result is MCP-unwrapped
    # (wire text == data, no top-level success/ok marker), so normalize_tool_result
    # truthfully reports tool_status=None. Repair success is carried by
    # verified / artifact_status / node_status -- the transport-envelope tool_status
    # is None on the unwrapped success path (cf. LM4F). The failed CREATE path is
    # re-wrapped with success:False, which is why its tool_status is "failed".
    assert repair_record.tool_status is None
    graph = repair_result.graph
    assert graph.nodes["repair_same_component"].status == "succeeded"
    assert graph.nodes["verify_repair"].status == "ready"

    # --- Pure verifier step: verify_repair -> succeeded, unlock done. ---
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.applied is True
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"

    # --- Terminal `done` marker -> graph complete. ---
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
