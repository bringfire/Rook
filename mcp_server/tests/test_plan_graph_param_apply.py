"""LM4L unit tests for apply_memory_bound_params -- the agent-layer applier that stages
memory-sourced params onto ONE named node's execution_params (copy-on-write).

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_param_apply import apply_memory_bound_params
from rook.learning.plan_graph import GraphMemory, PlanGraph, PlanGraphNode


_BASE = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}
_NESTED = {"guid": ("repair_anchor", "component_guid")}


class _NoDeepcopy:
    """A value whose deepcopy raises -- exercises graph_copy_failed."""

    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def _node(node_id: str, **meta) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", metadata=dict(meta))


def _graph(nodes, facts) -> PlanGraph:
    return PlanGraph(nodes={n.id: n for n in nodes}, memory=GraphMemory(facts=facts))


def test_success_copy_on_write():
    graph = _graph(
        [_node("repair_same_component")],
        {"repair_anchor": {"component_guid": "GUID-1"}},
    )
    result = apply_memory_bound_params(graph, "repair_same_component", _BASE, _NESTED)
    assert result.applied is True
    assert result.reason is None
    assert result.node_id == "repair_same_component"
    assert result.binding is not None and result.binding.findings == ()
    assert result.binding.params["guid"] == "GUID-1"
    # copy-on-write: new graph object; original node untouched, returned node staged.
    assert result.graph is not graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata
    assert (
        result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == "GUID-1"
    )


def test_unknown_node():
    graph = _graph([_node("repair_same_component")], {"component_guid": "GUID-1"})
    result = apply_memory_bound_params(
        graph, "absent", _BASE, {"guid": ("component_guid",)}
    )
    assert result.applied is False
    assert result.binding is None
    assert result.reason == "unknown_node"
    assert result.node_id == "absent"
    assert result.graph is graph  # no copy on failure


def test_binding_failed_missing_fact():
    graph = _graph(
        [_node("repair_same_component")], {"repair_anchor": {"language": "csharp"}}
    )
    result = apply_memory_bound_params(graph, "repair_same_component", _BASE, _NESTED)
    assert result.applied is False
    assert result.reason == "binding_failed"
    assert result.binding is not None
    assert [f.code for f in result.binding.findings] == ["memory_fact_missing"]
    assert result.graph is graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata


def test_graph_copy_failed():
    # bind reads only memory.facts (succeeds); deepcopy(graph) fails on an UNRELATED node.
    graph = _graph(
        [
            _node("repair_same_component"),
            _node("other", bad=_NoDeepcopy()),
        ],
        {"repair_anchor": {"component_guid": "GUID-1"}},
    )
    result = apply_memory_bound_params(graph, "repair_same_component", _BASE, _NESTED)
    assert result.applied is False
    assert result.reason == "graph_copy_failed"
    assert result.binding is not None and result.binding.findings == ()
    assert result.binding.params["guid"] == "GUID-1"  # binding succeeded before the copy
    assert result.graph is graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata


def test_immutability_of_inputs_on_success():
    facts = {"repair_anchor": {"component_guid": "GUID-1"}}
    base = dict(_BASE)
    graph = _graph([_node("repair_same_component")], facts)
    result = apply_memory_bound_params(graph, "repair_same_component", base, _NESTED)
    assert result.applied is True
    # original graph + memory untouched; base untouched.
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata
    assert graph.memory.facts == {"repair_anchor": {"component_guid": "GUID-1"}}
    assert base == _BASE
    # staged params are independent from memory: mutating them does not touch facts.
    result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY][
        "guid"
    ] = "MUTATED"
    assert graph.memory.facts["repair_anchor"]["component_guid"] == "GUID-1"


def test_applier_import_boundary():
    # The applier may import learning + plan_graph_live, but NOT server / base_agent /
    # a dispatcher; and learning's helper must NOT import the applier (agent->learning).
    import rook.agent.plan_graph_param_apply as applier
    import rook.learning.plan_graph_param_binding as helper

    def _imported_modules(path: str) -> set[str]:
        mods: set[str] = set()
        for node in ast.walk(ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                mods.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.add(node.module or "")
        return mods

    applier_imports = _imported_modules(applier.__file__)
    assert not any(m.startswith("rook.server") for m in applier_imports), applier_imports
    assert "rook.agent.base_agent" not in applier_imports, applier_imports
    assert not any("dispatch" in m for m in applier_imports), applier_imports

    helper_imports = _imported_modules(helper.__file__)
    assert "rook.agent.plan_graph_param_apply" not in helper_imports, helper_imports
