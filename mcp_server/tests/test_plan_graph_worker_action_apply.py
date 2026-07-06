"""LM6A tests for staging worker-authored action params onto one graph node.

The production applier is intentionally not present in Task 1. This file is the
red TDD surface for Task 2: collection should fail on the missing import until
``rook.agent.plan_graph_worker_action_apply`` exists.
"""

from __future__ import annotations

import ast
import pathlib
from types import MappingProxyType

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_worker_action_apply import (
    WorkerActionApplyResult,
    apply_worker_action_to_node,
)
from rook.learning.plan_graph import GraphMemory, PlanGraph, PlanGraphNode


_ACTION_ID = "draft_repair_params"
_NODE_ID = "repair_same_component"
_CODE = "var radius = 12.0;"


class _NoDeepcopy:
    """A value whose deepcopy raises -- exercises graph_copy_failed."""

    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def _node(node_id: str, **meta) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", metadata=dict(meta))


def _graph(nodes, facts=None) -> PlanGraph:
    return PlanGraph(nodes={n.id: n for n in nodes}, memory=GraphMemory(facts=facts or {}))


def _valid_action_input() -> dict[str, str]:
    return {"code": _CODE, "mode": "body"}


def _valid_anchor() -> dict[str, str]:
    return {"component_guid": "GUID-1", "language": "csharp"}


def _apply(
    graph: PlanGraph,
    node_id: str = _NODE_ID,
    action_id: str = _ACTION_ID,
    action_input=None,
    anchor_binding=None,
) -> WorkerActionApplyResult:
    return apply_worker_action_to_node(
        graph,
        node_id,
        action_id=action_id,
        action_input=_valid_action_input() if action_input is None else action_input,
        anchor_binding=_valid_anchor() if anchor_binding is None else anchor_binding,
    )


def _assert_rejected(
    result: WorkerActionApplyResult,
    graph: PlanGraph,
    reason: str,
    node_id: str = _NODE_ID,
) -> None:
    assert result.applied is False
    assert result.reason == reason
    assert result.node_id == node_id
    assert result.graph is graph
    assert result.params_sha256 is None
    if node_id in graph.nodes:
        assert EXECUTION_PARAMS_KEY not in graph.nodes[node_id].metadata


def test_success_stages_exact_params_copy_on_write() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(graph)

    assert isinstance(result, WorkerActionApplyResult)
    assert result.applied is True
    assert result.reason is None
    assert result.node_id == _NODE_ID
    assert result.graph is not graph
    assert result.params_sha256 is not None
    assert EXECUTION_PARAMS_KEY not in graph.nodes[_NODE_ID].metadata
    assert result.graph.nodes[_NODE_ID].metadata[EXECUTION_PARAMS_KEY] == {
        "guid": "GUID-1",
        "code": _CODE,
        "mode": "body",
        "language": "csharp",
    }


def test_success_copies_inputs_without_aliasing() -> None:
    action_input = _valid_action_input()
    anchor = _valid_anchor()
    graph = _graph([_node(_NODE_ID)])

    result = _apply(graph, action_input=action_input, anchor_binding=anchor)

    action_input["code"] = "MUTATED"
    action_input["mode"] = "full_source"
    anchor["component_guid"] = "MUTATED"
    anchor["language"] = "python"
    staged = result.graph.nodes[_NODE_ID].metadata[EXECUTION_PARAMS_KEY]
    assert staged == {
        "guid": "GUID-1",
        "code": _CODE,
        "mode": "body",
        "language": "csharp",
    }


def test_success_accepts_non_dict_mappings() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(
        graph,
        action_input=MappingProxyType(_valid_action_input()),
        anchor_binding=MappingProxyType(_valid_anchor()),
    )

    assert result.applied is True
    assert result.reason is None
    assert result.graph.nodes[_NODE_ID].metadata[EXECUTION_PARAMS_KEY] == {
        "guid": "GUID-1",
        "code": _CODE,
        "mode": "body",
        "language": "csharp",
    }


def test_unknown_node() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(graph, node_id="absent")

    _assert_rejected(result, graph, "unknown_node", node_id="absent")


def test_graph_copy_failed() -> None:
    graph = _graph([_node(_NODE_ID), _node("other", bad=_NoDeepcopy())])

    result = _apply(graph)

    _assert_rejected(result, graph, "graph_copy_failed")


def test_invalid_action_id() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(graph, action_id="other_action")

    _assert_rejected(result, graph, "invalid_action_id")


def test_invalid_action_input_shape_rejected() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(graph, action_input=["not", "mapping"])

    _assert_rejected(result, graph, "invalid_action_input")


def test_unexpected_action_input_key_rejected() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(
        graph,
        action_input={"code": "A = 0.0;", "mode": "body", "guid": "BAD"},
    )

    _assert_rejected(result, graph, "unexpected_action_input_key")


def test_missing_code_and_invalid_code_rejected() -> None:
    graph = _graph([_node(_NODE_ID)])

    missing = _apply(graph, action_input={"mode": "body"})
    empty = _apply(graph, action_input={"code": "   ", "mode": "body"})
    non_string = _apply(graph, action_input={"code": 123, "mode": "body"})

    _assert_rejected(missing, graph, "missing_code")
    _assert_rejected(empty, graph, "invalid_code")
    _assert_rejected(non_string, graph, "invalid_code")


def test_invalid_mode() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(graph, action_input={"code": "A = 0.0;", "mode": "full_source"})

    _assert_rejected(result, graph, "invalid_mode")


def test_invalid_anchor_binding_shape_rejected() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(graph, anchor_binding=["not", "mapping"])

    _assert_rejected(result, graph, "invalid_anchor_binding")


def test_unexpected_anchor_binding_key_rejected() -> None:
    graph = _graph([_node(_NODE_ID)])

    result = _apply(
        graph,
        anchor_binding={
            "component_guid": "GUID-1",
            "language": "csharp",
            "target_errors": ["nope"],
        },
    )

    _assert_rejected(result, graph, "unexpected_anchor_binding_key")


def test_missing_component_guid_and_invalid_component_guid_rejected() -> None:
    graph = _graph([_node(_NODE_ID)])

    missing = _apply(graph, anchor_binding={"language": "csharp"})
    blank = _apply(graph, anchor_binding={"component_guid": "", "language": "csharp"})
    non_string = _apply(
        graph,
        anchor_binding={"component_guid": 123, "language": "csharp"},
    )

    _assert_rejected(missing, graph, "missing_component_guid")
    _assert_rejected(blank, graph, "invalid_component_guid")
    _assert_rejected(non_string, graph, "invalid_component_guid")


def test_missing_language_and_invalid_language_rejected() -> None:
    graph = _graph([_node(_NODE_ID)])

    missing = _apply(graph, anchor_binding={"component_guid": "GUID-1"})
    invalid = _apply(
        graph,
        anchor_binding={"component_guid": "GUID-1", "language": "python"},
    )
    non_string = _apply(
        graph,
        anchor_binding={"component_guid": "GUID-1", "language": 123},
    )

    _assert_rejected(missing, graph, "missing_language")
    _assert_rejected(invalid, graph, "invalid_language")
    _assert_rejected(non_string, graph, "invalid_language")


def test_applier_import_boundary() -> None:
    import rook.agent.plan_graph_worker_action_apply as applier

    def _imported_modules(path: str) -> set[str]:
        mods: set[str] = set()
        for node in ast.walk(ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                mods.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.add(node.module or "")
                mods.update(a.name for a in node.names)
        return mods

    source = pathlib.Path(applier.__file__).read_text(encoding="utf-8")
    imports = _imported_modules(applier.__file__)
    tree = ast.parse(source)

    assert "rook.agent.plan_graph_param_apply" not in imports
    assert "BindStepSpec" not in imports
    assert "base_params" not in source
    assert "PROBE_REPAIR_CODE" not in source
    assert "A = 42.0" not in source
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "base_params"
        for node in ast.walk(tree)
    )
