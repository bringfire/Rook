"""LM4M live proof -- run_explicit_sequence drives the declared-ref repair chain LIVE with
a real RookAgent runner, calling LM4L apply_memory_bound_params as the BindStep mid-
sequence. The runner threads create -> verify_create -> bind -> repair -> verify_repair;
the test asserts the sequence completed and `done` is ready, then applies the terminal
marker to reach graph_status == "complete".

create.evidence.repair_anchor.component_guid is a CONTROL: the bind StepOutcome's
memory-sourced guid must equal it. No producer ref overrides (declared
gh_create_csharp_script:v1 / gh_update_script:v1).

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_sequence_runner_chain_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import LiveProducerExpectation
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    VerifierStep,
    run_explicit_sequence,
)
from rook.learning.plan_graph import NodeOutcome, apply_outcome, graph_status
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


async def test_sequence_runner_drives_live_repair_chain(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # No ref override; set ONLY create execution_params directly (author-supplied, not
    # memory-sourced; omit 'language' -- the csharp alias forces it).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4MSequenceRunnerLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)

    create_expect = LiveProducerExpectation(
        applied=True,
        outcome_status="succeeded",
        node_status="succeeded",
        tool_status="failed",
        verified=False,
        artifact_status="created_with_errors",
    )
    repair_expect = LiveProducerExpectation(
        applied=True,
        outcome_status="succeeded",
        node_status="succeeded",
        verified=True,
        artifact_status="usable",
    )
    steps = [
        ProducerStep("create_script", expectation=create_expect),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        BindStep(
            "repair_same_component",
            {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
            {"guid": ("repair_anchor", "component_guid")},
        ),
        ProducerStep("repair_same_component", expectation=repair_expect),
        VerifierStep("verify_repair", "repair_same_component", expected_outcome="succeeded"),
    ]

    result = await run_explicit_sequence(agent, graph, steps)
    assert result.completed is True, (
        f"stopped_at={result.stopped_at} "
        f"results={[(s.kind, s.ok) for s in result.step_results]}"
    )
    assert result.stopped_at is None
    assert [s.kind for s in result.step_results] == [
        "producer", "verifier", "bind", "producer", "verifier",
    ]

    # the create producer step dispatched the DECLARED ref live (no override).
    assert result.step_results[0].producer_record.tool_name == "gh_create_csharp_script"

    # CONTROL: the bind step's memory-sourced guid equals the create evidence guid.
    create_record = result.step_results[0].producer_record
    repair_guid_control = create_record.repair_anchor_guid
    assert isinstance(repair_guid_control, str) and repair_guid_control
    bind_outcome = result.step_results[2]
    assert bind_outcome.bind_result.binding.params["guid"] == repair_guid_control

    # the repair producer step dispatched gh_update_script; unwrapped success -> None.
    repair_record = result.step_results[3].producer_record
    assert repair_record.tool_name == "gh_update_script"
    assert repair_record.tool_status is None  # unwrapped success (LM4I/J finding)

    # SEQUENCE-completed but graph not complete: done is ready, then apply terminal.
    graph = result.graph
    assert graph.nodes["done"].status == "ready"
    assert graph_status(graph) != "complete"
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
