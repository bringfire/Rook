"""LM4K live proof -- the repair guid is SOURCED FROM graph.memory.facts (not from
evidence) and drives the real gh_update_script repair, with the declared-ref chain
from LM4J (no producer overrides) to graph_status=="complete".

create.evidence.repair_anchor.component_guid is captured ONLY as a CONTROL: the test
asserts the memory-sourced guid equals it, proving graph.memory.facts is the source of
truth carrying the right repair target. Automatic propagation INTO a runner is still
out of scope -- the test performs the assignment.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_memory_sourced_live.py
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
from rook.learning.plan_graph_param_binding import bind_params_from_memory
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
    """Establish an ACTIVE Grasshopper document; skip (never silently ignore) when GH
    cannot provide one. The `_Grasshopper` window open is not sufficient, and
    fresh_document resets only the Rhino document."""
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_memory_sourced_repair_guid_drives_live_repair(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # No ref override; set ONLY create execution_params (omit 'language' -- csharp alias).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4KMemorySourcedLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)

    # --- Live dispatch 1: declared-ref create (broken) -> created_with_errors. ---
    create_result = await agent.run_live_producer_node(graph, "create_script")
    assert create_result.tool_name == "gh_create_csharp_script"
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
    assert graph.nodes["verify_create"].status == "ready"

    # CONTROL only: the evidence guid we expect memory to also carry.
    repair_guid_control = graph.nodes["create_script"].evidence.repair_anchor[
        "component_guid"
    ]
    assert isinstance(repair_guid_control, str) and repair_guid_control

    # --- Verifier step -> needs_repair, unlock repair. ---
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # --- SOURCE the repair guid FROM graph.memory.facts (not evidence). ---
    binding = bind_params_from_memory(
        {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
        graph,
        {"guid": ("repair_anchor", "component_guid")},
    )
    assert binding.findings == ()
    assert binding.params["guid"] == repair_guid_control  # memory == evidence control
    graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] = binding.params

    # --- Live dispatch 2: declared-ref repair, guid sourced from memory -> usable. ---
    repair_result = await agent.run_live_producer_node(graph, "repair_same_component")
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
    assert repair_record.tool_status is None  # unwrapped success (LM4I/J finding)

    graph = repair_result.graph
    assert graph.nodes["verify_repair"].status == "ready"

    # --- Verifier step -> succeeded, unlock done; terminal -> complete. ---
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
