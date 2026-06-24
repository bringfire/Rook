"""LM4J memory-substrate pure guard — producer projection writes the repair target
into graph.memory.facts through the REAL apply_producer_result path.

Drives the registered 5-node gh_csharp_create_verify_repair_verify chain to
graph_status==complete using RAW tool-result dicts routed through the LM3I projection
entry apply_producer_result (NOT hand-built NodeOutcomes -- that path, used by the LM4I
pure guard, bypasses project_receipt_outcome's memory_updates). Pins:
  - memory_updates -> graph.memory.facts (component_guid / repair_anchor) on producer
    success, via _producer_success -> _merge_memory;
  - live-faithful raw envelopes: WRAPPED FAILURE create (success:False) ->
    tool_status="failed"; MCP-UNWRAPPED SUCCESS repair (top-level script_receipt) ->
    tool_status=None;
  - role-aware verified projection: created_with_errors -> verified=False,
    usable -> verified=True (NO top-level verified field in the raw).

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4j-pure-guard-guid"


def _wrapped_failure_create_raw() -> dict:
    """Live-faithful create envelope: success:False, nested data.script_receipt
    (created_with_errors with mutation + repair_anchor)."""
    return {
        "success": False,
        "message": "Component created with compile errors.",
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
    """Live-faithful repair envelope: MCP-unwrapped success -- the result IS the tool
    data, top-level script_receipt, NO data/success/ok/error markers, NO top-level
    verified (the producer projection derives verified=True from artifact_status)."""
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


def test_memory_substrate_through_real_projection_path():
    # Registry path + both declared producer refs pinned before any mutation.
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # Roots are 'pending' after selection; apply_producer_result gates on runnable_nodes
    # (ready). initialize_graph promotes the root create_script -> ready.
    graph = initialize_graph(graph)
    assert graph.nodes["create_script"].status == "ready"

    # 1) create producer via the REAL projection path (wrapped-failure raw).
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.applied is True
    assert create.outcome_status == "succeeded"
    graph = create.graph
    create_node = graph.nodes["create_script"]
    assert create_node.status == "succeeded"
    assert create_node.evidence is not None
    assert create_node.evidence.tool_status == "failed"
    assert create_node.evidence.verified is False
    # The substrate claim: producer projection wrote the repair target into memory.
    assert graph.memory.facts["component_guid"] == _GUID
    assert graph.memory.facts["repair_anchor"]["component_guid"] == _GUID
    assert graph.nodes["verify_create"].status == "ready"

    # 2) verify_create re-judges -> needs_repair, unlock repair.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.applied is True
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # 3) repair producer via the REAL projection path (unwrapped-success raw).
    repair = apply_producer_result(
        graph, "repair_same_component", _unwrapped_success_repair_raw()
    )
    assert repair.applied is True
    assert repair.outcome_status == "succeeded"
    graph = repair.graph
    repair_node = graph.nodes["repair_same_component"]
    assert repair_node.status == "succeeded"
    assert repair_node.evidence is not None
    # Unwrapped success carries no envelope marker -> tool_status None (LM4I finding);
    # verified=True is derived by the role projection from artifact_status="usable".
    assert repair_node.evidence.tool_status is None
    assert repair_node.evidence.verified is True
    assert graph.memory.facts["component_guid"] == _GUID
    assert graph.nodes["verify_repair"].status == "ready"

    # 4) verify_repair confirms clean -> done unlocks.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.applied is True
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"

    # 5) terminal done marker -> graph complete.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph.nodes["done"].status == "succeeded"
    assert graph_status(graph) == "complete"
