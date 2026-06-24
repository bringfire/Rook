"""LM4N chain observation guard -- propose_next_node tracks the 5-node repair chain's
unique-ready property at every transition, and refuses on a fork.

The reducer drives the graph (apply_producer_result / apply_verifier_step / apply_outcome);
the selector merely OBSERVES each resulting snapshot. HONEST SCOPE: nothing consumes the
proposal -- the selector only proposes; there is no dispatch or mutation driven by it. In
the focused PlanGraph gate. Run from repo root. Separate file from
test_plan_graph_selector.py.
"""

from __future__ import annotations

from rook.learning.plan_graph import (
    NodeOutcome,
    PlanGraph,
    PlanGraphNode,
    apply_outcome,
    initialize_graph,
)
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4n-chain-guid"


def _wrapped_failure_create_raw() -> dict:
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": _GUID},
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
            }
        },
    }


def _unwrapped_success_repair_raw() -> dict:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "written", "component_guid": _GUID},
            "verification": {"status": "passed", "target_error_count": 0},
            "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
        }
    }


def _selected(graph) -> str | None:
    p = propose_next_node(graph)
    assert p.decision == "SELECT_NODE", p
    return p.selected_node_id


def test_selector_tracks_linear_chain_unique_ready():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # Root: only create_script is ready.
    assert _selected(graph) == "create_script"

    # create -> only verify_create ready.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph
    assert _selected(graph) == "verify_create"

    # verify_create -> needs_repair -> only repair_same_component ready.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert _selected(graph) == "repair_same_component"

    # repair -> only verify_repair ready.
    repair = apply_producer_result(
        graph, "repair_same_component", _unwrapped_success_repair_raw()
    )
    assert repair.outcome_status == "succeeded"
    graph = repair.graph
    assert _selected(graph) == "verify_repair"

    # verify_repair -> succeeded -> only done ready.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert _selected(graph) == "done"

    # terminal done -> no ready node -> HALT_NONE_READY.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    p = propose_next_node(graph)
    assert p.decision == "HALT_NONE_READY"
    assert p.candidate_node_ids == ()


def test_fork_graph_halts_ambiguous():
    # Two ready nodes -> the selector refuses to choose.
    graph = PlanGraph(
        nodes={
            "left": PlanGraphNode(id="left", intent="x", status="ready"),
            "right": PlanGraphNode(id="right", intent="x", status="ready"),
        }
    )
    p = propose_next_node(graph)
    assert p.decision == "HALT_AMBIGUOUS_READY"
    assert p.selected_node_id is None
    assert p.candidate_node_ids == ("left", "right")
    assert p.ready_count == 2
