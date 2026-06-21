from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    apply_outcome,
    graph_status,
    initialize_graph,
    runnable_nodes,
)
from rook.learning.plan_graph_outcomes import node_outcome_from_tool_result
from rook.learning.plan_graph_bridge import apply_tool_result


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _create_result() -> dict:
    """Canned LM1D-shaped create result: component placed with compile errors."""
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
                    "target_errors": [
                        "The name 'nonExistentSymbol' does not exist in the current context [14:13]"
                    ],
                },
            }
        },
    }


def _update_result() -> dict:
    """Canned LM1D-shaped update result: same component repaired and usable."""
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
                    "target_errors": [],
                },
            }
        },
    }


def _single_node_graph() -> PlanGraph:
    return initialize_graph(
        PlanGraph(nodes={"n": PlanGraphNode(id="n", intent="Node")})
    )


def test_apply_tool_result_equals_manual_adapter_then_reducer():
    graph = _single_node_graph()
    result = _create_result()

    via_bridge = apply_tool_result(graph, "n", result)
    via_manual = apply_outcome(graph, "n", node_outcome_from_tool_result(result))

    assert via_bridge == via_manual


def test_apply_tool_result_does_not_mutate_input_graph():
    graph = _single_node_graph()
    before = copy.deepcopy(graph)

    apply_tool_result(graph, "n", _create_result())

    assert graph == before


def test_apply_tool_result_deep_copies_against_post_call_mutation():
    graph = _single_node_graph()
    result = _create_result()

    updated = apply_tool_result(graph, "n", result)

    result["data"]["script_receipt"]["artifact_status"] = "mutated"
    result["data"]["script_receipt"]["repair_anchor"]["component_guid"] = "mutated"

    assert updated.nodes["n"].evidence.receipt["artifact_status"] == "created_with_errors"
    assert updated.memory.facts["repair_anchor"]["component_guid"] == COMPONENT_GUID


def test_apply_tool_result_raises_for_unknown_node_id():
    graph = PlanGraph(nodes={"known": PlanGraphNode(id="known", intent="Known")})

    with pytest.raises(ValueError, match="Unknown PlanGraph node"):
        apply_tool_result(graph, "missing", {"success": True})


def test_apply_tool_result_applies_blocked_for_non_dict_result_without_raising():
    graph = _single_node_graph()

    updated = apply_tool_result(graph, "n", "plain string result")

    assert updated.nodes["n"].status == "blocked"


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


def test_canned_create_repair_loop_reaches_complete_through_bridge():
    graph = initialize_graph(_repair_fixture())
    assert {node.id for node in runnable_nodes(graph)} == {"create_script"}

    create_receipt = _create_result()["data"]["script_receipt"]
    graph = apply_tool_result(graph, "create_script", _create_result())

    assert graph.nodes["create_script"].status == "needs_repair"
    assert graph.memory.facts["component_guid"] == COMPONENT_GUID
    assert graph.memory.facts["repair_anchor"] == create_receipt["repair_anchor"]
    assert {node.id for node in runnable_nodes(graph)} == {"repair_same_component"}
    assert graph_status(graph) == "running"

    graph = apply_tool_result(graph, "repair_same_component", _update_result())

    assert graph.nodes["repair_same_component"].status == "succeeded"
    assert graph.memory.facts["component_guid"] == COMPONENT_GUID
    repair_evidence = graph.nodes["repair_same_component"].evidence
    assert repair_evidence is not None
    assert repair_evidence.receipt["artifact_status"] == "usable"
    assert graph_status(graph) == "complete"


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


def test_plan_graph_bridge_imports_only_pure_graph_modules():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_bridge.py"
    )

    assert "rook.learning.plan_graph" in imports
    assert "rook.learning.plan_graph_outcomes" in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.agent.chat.chat_runner" not in imports
    assert "rook.server" not in imports


def test_importing_plan_graph_bridge_does_not_load_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_bridge\n"
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
