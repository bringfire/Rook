from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from pathlib import Path

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    initialize_graph,
)
from rook.learning.plan_graph_walker import walk_plan_graph


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _create_result() -> dict:
    """LM1D-shaped create result: component placed with compile errors."""
    return {
        "success": False,
        "message": "Component was created, but the target script component has compile errors.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {
                    "status": "created",
                    "method": "gh_create_component_then_script",
                    "component_guid": COMPONENT_GUID,
                    "note": None,
                },
                "verification": {
                    "status": "failed",
                    "method": "gh_errors",
                    "target_error_count": 1,
                },
                "repair_anchor": {
                    "component_guid": COMPONENT_GUID,
                    "language": "csharp",
                    "pins_out": [{"name": "A", "type": "double"}],
                },
            }
        },
    }


def _update_result() -> dict:
    """LM1D-shaped update result: same component repaired and usable."""
    return {
        "success": True,
        "message": "Script updated; component is usable.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "update",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {
                    "status": "written",
                    "method": "gh_script_write",
                    "component_guid": COMPONENT_GUID,
                    "note": None,
                },
                "verification": {
                    "status": "passed",
                    "method": "gh_errors",
                    "target_error_count": 0,
                },
                "repair_anchor": {
                    "component_guid": COMPONENT_GUID,
                    "language": "csharp",
                    "pins_out": [{"name": "A", "type": "Generic Data"}],
                },
            }
        },
    }


def _repair_fixture() -> PlanGraph:
    return PlanGraph(
        nodes={
            "create_script": PlanGraphNode(
                id="create_script",
                intent="Create C# script component",
                execution_ref="gh_create_csharp_script:v1",
            ),
            "repair_same_component": PlanGraphNode(
                id="repair_same_component",
                intent="Repair same component",
                execution_ref="gh_update_script:v1",
                is_terminal=True,
            ),
        },
        edges=[
            PlanGraphEdge(
                source="create_script",
                target="repair_same_component",
                kind="on_repair",
            ),
        ],
    )


def _orphan_create_graph() -> PlanGraph:
    return PlanGraph(nodes={"create": PlanGraphNode(id="create", intent="Create")})


def _single_terminal_graph() -> PlanGraph:
    return PlanGraph(
        nodes={"n": PlanGraphNode(id="n", intent="Node", is_terminal=True)}
    )


def _escalation_fixture() -> PlanGraph:
    # needs_escalation is never produced by the adapter/bridge; it enters the
    # graph from outside (a future verifier/repair-policy layer). The walker only
    # reflects it. Pre-seed it and drive an unrelated ready root.
    return PlanGraph(
        nodes={
            "ready_root": PlanGraphNode(id="ready_root", intent="Ready root"),
            "already_escalated": PlanGraphNode(
                id="already_escalated",
                intent="Pre-escalated",
                status="needs_escalation",
            ),
        },
    )


def test_full_create_repair_complete_replay_carries_memory_forward():
    report = walk_plan_graph(
        _repair_fixture(),
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert report.halted is False
    assert report.halt_reason is None
    assert report.remaining_steps == ()
    assert report.final_graph_status == "complete"
    assert [s.node_id for s in report.steps] == [
        "create_script",
        "repair_same_component",
    ]

    create_step = report.steps[0]
    assert create_step.applied is True
    assert create_step.runnable_before is True
    assert create_step.status_before == "ready"
    assert create_step.status_after == "needs_repair"
    assert create_step.graph_status_after == "running"
    assert create_step.memory_facts["component_guid"] == COMPONENT_GUID
    assert create_step.memory_facts["repair_anchor"]["component_guid"] == COMPONENT_GUID
    assert create_step.evidence is not None
    assert create_step.evidence.tool_status == "failed"
    assert create_step.evidence.has_repair_anchor is True
    assert create_step.reason is None

    repair_step = report.steps[1]
    assert repair_step.status_before == "ready"
    assert repair_step.status_after == "succeeded"
    assert repair_step.graph_status_after == "complete"
    assert repair_step.evidence is not None
    assert repair_step.evidence.tool_status == "success"

    assert report.final_memory_facts["component_guid"] == COMPONENT_GUID


def test_invalid_step_node_not_runnable_halts_without_mutating_input():
    graph = _repair_fixture()
    original = copy.deepcopy(graph)

    report = walk_plan_graph(graph, [("repair_same_component", _update_result())])

    assert len(report.steps) == 1
    step = report.steps[0]
    assert step.applied is False
    assert step.runnable_before is False
    assert step.reason == "node_not_runnable"
    assert step.status_before == "pending"
    assert step.evidence is None
    assert report.halted is True
    assert report.halt_reason == "invalid_step"
    assert report.remaining_steps == ()
    # input graph not mutated; final graph is merely the initialized form
    assert graph == original
    assert report.final_graph == initialize_graph(original)


def test_invalid_step_unknown_node_reports_unknown_node():
    report = walk_plan_graph(
        _repair_fixture(), [("does_not_exist", {"success": True})]
    )

    step = report.steps[0]
    assert step.applied is False
    assert step.reason == "unknown_node"
    assert step.status_before is None
    assert report.halted is True
    assert report.halt_reason == "invalid_step"


def test_remaining_steps_preserves_raw_result_tail_as_is():
    class _Uncopyable:
        def __deepcopy__(self, memo):
            raise AssertionError("remaining_steps must not deep-copy raw results")

    tail_payload = _Uncopyable()
    report = walk_plan_graph(
        _single_terminal_graph(),
        [("n", {"success": True}), ("later", tail_payload)],
    )

    assert report.halted is True
    assert report.halt_reason == "terminal_status"
    assert report.final_graph_status == "complete"
    assert len(report.remaining_steps) == 1
    node_id, payload = report.remaining_steps[0]
    assert node_id == "later"
    assert payload is tail_payload  # identity preserved, not copied


def test_walker_surfaces_pre_existing_escalation_and_halts_terminal():
    report = walk_plan_graph(
        _escalation_fixture(), [("ready_root", {"success": True})]
    )

    assert report.steps[0].applied is True
    assert report.final_graph_status == "needs_escalation"
    assert report.nodes_needing_escalation == ("already_escalated",)
    assert report.halted is True
    assert report.halt_reason == "terminal_status"


def test_needs_repair_without_repair_edge_reflected_and_blocks():
    report = walk_plan_graph(_orphan_create_graph(), [("create", _create_result())])

    assert report.steps[0].status_after == "needs_repair"
    assert report.nodes_needing_repair == ("create",)
    assert report.final_graph_status == "blocked"
    assert report.halted is True
    assert report.halt_reason == "terminal_status"


def test_non_dict_raw_result_blocks_via_adapter_without_raising():
    report = walk_plan_graph(_orphan_create_graph(), [("create", "plain string result")])

    step = report.steps[0]
    assert step.applied is True
    assert step.status_after == "blocked"
    assert report.final_graph_status == "blocked"
    assert report.halt_reason == "terminal_status"


def test_empty_steps_returns_initialized_graph_report():
    report = walk_plan_graph(_repair_fixture(), [])

    assert report.steps == ()
    assert report.halted is False
    assert report.halt_reason is None
    assert report.remaining_steps == ()
    assert report.final_graph == initialize_graph(_repair_fixture())
    assert report.final_runnable_node_ids == ("create_script",)


def test_input_graph_not_mutated_by_full_walk():
    graph = _repair_fixture()
    original = copy.deepcopy(graph)

    walk_plan_graph(
        graph,
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert graph == original


def test_initialize_graph_is_idempotent_for_already_initialized_graph():
    once = initialize_graph(_repair_fixture())
    twice = initialize_graph(once)

    assert twice == once


def test_memory_facts_snapshots_are_isolated_from_final_graph():
    report = walk_plan_graph(_orphan_create_graph(), [("create", _create_result())])

    report.final_memory_facts["repair_anchor"]["component_guid"] = "mutated"
    report.steps[0].memory_facts["component_guid"] = "mutated"

    assert (
        report.final_graph.memory.facts["repair_anchor"]["component_guid"]
        == COMPONENT_GUID
    )
    assert report.final_graph.memory.facts["component_guid"] == COMPONENT_GUID


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_walker_imports_only_pure_graph_modules():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_walker.py"
    )

    assert "rook.learning.plan_graph" in imports
    assert "rook.learning.plan_graph_bridge" in imports
    assert "rook.learning.plan_graph_outcomes" not in imports
    assert "rook.agent.chat.tool_result_view" not in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.agent.chat.chat_runner" not in imports
    assert "rook.server" not in imports


def test_importing_walker_does_not_load_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_walker\n"
        "if 'rook.agent.tool_dispatcher' in sys.modules:\n"
        "    raise SystemExit('rook.agent.tool_dispatcher loaded')\n"
        "if 'dspy' in sys.modules:\n"
        "    raise SystemExit('dspy loaded')\n"
        "if 'litellm' in sys.modules:\n"
        "    raise SystemExit('litellm loaded')\n"
    )

    subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        env=env,
    )
