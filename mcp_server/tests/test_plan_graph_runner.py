from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from pathlib import Path

from rook.learning.plan_graph import (
    NodeEvidence,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
)
from rook.learning.plan_graph_runner import apply_verifier_step


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _receipt(artifact_status: str) -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": artifact_status,
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "verification": {"status": "failed", "target_error_count": 1},
        "repair_anchor": {
            "component_guid": COMPONENT_GUID,
            "pins_out": [{"name": "A", "type": "double"}],
        },
    }


def _fixture(
    artifact_status: str = "created_with_errors", *, verify_status: str = "ready"
) -> PlanGraph:
    receipt = _receipt(artifact_status)
    return PlanGraph(
        nodes={
            "source": PlanGraphNode(
                id="source",
                intent="Fixture source evidence node",
                status="succeeded",
                evidence=NodeEvidence(
                    tool_status="failed",
                    verified=False,
                    receipt=receipt,
                    repair_anchor=receipt["repair_anchor"],
                ),
            ),
            "verify": PlanGraphNode(id="verify", intent="Verify", status=verify_status),
            "repair": PlanGraphNode(id="repair", intent="Repair", is_terminal=True),
        },
        edges=[
            # Documentary: in a real run a producer step would unlock `verify`;
            # here `verify` is pre-seeded ready (producer semantics -> LM3F).
            PlanGraphEdge(source="source", target="verify", kind="requires"),
            PlanGraphEdge(source="verify", target="repair", kind="on_repair"),
        ],
    )


def test_happy_path_needs_repair_unlocks_repair_node():
    graph = _fixture("created_with_errors")

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "needs_repair"
    assert result.graph.nodes["verify"].status == "needs_repair"
    # WATCHPOINT: the verifier's on_repair edge unlocks the repair node via the
    # reducer -- proves composition through apply_outcome, not just status storage.
    assert result.graph.nodes["repair"].status == "ready"
    # verifier node carries the receipt forward (via the LM3D adapter)
    assert result.graph.nodes["verify"].evidence is not None
    assert (
        result.graph.nodes["verify"].evidence.receipt["artifact_status"]
        == "created_with_errors"
    )


def test_usable_source_produces_succeeded():
    graph = _fixture("usable")

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is True
    assert result.outcome_status == "succeeded"
    assert result.graph.nodes["verify"].status == "succeeded"
    # on_repair does not fire on succeeded -> repair stays pending
    assert result.graph.nodes["repair"].status == "pending"


def test_unknown_verifier_node_not_applied():
    graph = _fixture()

    result = apply_verifier_step(graph, "missing", "source")

    assert result.applied is False
    assert result.reason == "unknown_verifier_node"
    assert result.outcome_status is None
    assert result.graph is graph  # input returned unchanged


def test_unknown_source_node_not_applied():
    graph = _fixture()

    result = apply_verifier_step(graph, "verify", "missing")

    assert result.applied is False
    assert result.reason == "unknown_source_node"
    assert result.graph is graph


def test_source_evidence_missing_not_applied():
    graph = _fixture()
    graph.nodes["source"].evidence = None

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is False
    assert result.reason == "source_evidence_missing"
    assert result.graph is graph


def test_verifier_not_runnable_not_applied():
    graph = _fixture(verify_status="pending")

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is False
    assert result.reason == "verifier_not_runnable"
    assert result.graph is graph


def test_input_graph_not_mutated_on_apply():
    graph = _fixture("created_with_errors")
    before = copy.deepcopy(graph)

    apply_verifier_step(graph, "verify", "source")

    assert graph == before


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


def test_runner_imports_only_plan_graph_layer():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_runner.py"
    )
    rook_or_relative = {
        m for m in imports if m.startswith("rook.") or m.startswith(".")
    }
    assert rook_or_relative == {
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_verifiers",
    }
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.learning.plan_graph_walker" not in imports
    assert "rook.agent.planner" not in imports


def test_importing_runner_does_not_load_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_runner\n"
        "for mod in ('rook.agent.tool_dispatcher', 'dspy', 'litellm'):\n"
        "    if mod in sys.modules:\n"
        "        raise SystemExit(mod + ' loaded')\n"
    )

    subprocess.run([sys.executable, "-c", probe], check=True, env=env)
