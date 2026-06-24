"""LM4K pure chain guard — bind the repair guid from graph.memory.facts, then compose
the 5-node chain to complete.

HONEST SCOPE: apply_producer_result consumes a RAW tool-result dict, NOT the node's
execution_params. So this guard proves (a) the helper sources the guid from the runtime
memory substrate into a real execution_params assignment, and (b) the graph still
composes to complete. It does NOT prove the bound guid drives a real repair dispatch --
only the live proof (test_live_repair_chain_memory_sourced_live.py) does that.

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root. Separate file
from test_plan_graph_live_repair_memory.py (LM4J), which stays untouched.
"""

from __future__ import annotations

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_param_binding import bind_params_from_memory
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4k-chain-guid"
_BASE_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}


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


def test_memory_sourced_repair_params_then_compose_to_complete():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)
    assert graph.nodes["create_script"].status == "ready"

    # create producer -> memory.facts populated.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph
    assert graph.memory.facts["component_guid"] == _GUID

    # verify_create -> needs_repair, unlock repair.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # SOURCE the repair guid from memory (nested path) and assign into execution_params.
    binding = bind_params_from_memory(
        _BASE_REPAIR_PARAMS, graph, {"guid": ("repair_anchor", "component_guid")}
    )
    assert binding.findings == ()
    assert binding.params["guid"] == _GUID
    graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] = binding.params
    assert (
        graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == _GUID
    )

    # repair producer (raw-dict projection) -> succeeded, unlock verify_repair.
    repair = apply_producer_result(
        graph, "repair_same_component", _unwrapped_success_repair_raw()
    )
    assert repair.outcome_status == "succeeded"
    graph = repair.graph
    assert graph.nodes["verify_repair"].status == "ready"

    # verify_repair -> succeeded, unlock done.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"

    # terminal done -> complete.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
