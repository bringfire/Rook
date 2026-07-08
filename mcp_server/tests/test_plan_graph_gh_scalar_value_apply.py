import ast
import math
import pathlib
from types import MappingProxyType

from rook.agent.plan_graph_gh_scalar_value_apply import (
    GhScalarValueApplyResult,
    apply_gh_scalar_value_action_to_node,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import GraphMemory, PlanGraph, PlanGraphNode


ACTION_ID = "draft_gh_set_value_params"
NODE_ID = "set_scalar_value"


class _NoDeepcopy:
    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def _node(node_id: str, **metadata):
    return PlanGraphNode(id=node_id, intent="x", metadata=dict(metadata))


def _graph(nodes):
    return PlanGraph(nodes={node.id: node for node in nodes}, memory=GraphMemory())


def _valid_action_input():
    return {"value": 7.5}


def _valid_anchor():
    return {"component_guid": "GUID-1"}


def _apply(graph, *, action_id=ACTION_ID, action_input=None, anchor_binding=None):
    return apply_gh_scalar_value_action_to_node(
        graph,
        NODE_ID,
        action_id=action_id,
        action_input=_valid_action_input() if action_input is None else action_input,
        anchor_binding=_valid_anchor() if anchor_binding is None else anchor_binding,
    )


def _assert_rejected(result, graph, reason):
    assert result.applied is False
    assert result.reason == reason
    assert result.graph is graph
    assert result.params_sha256 is None
    assert EXECUTION_PARAMS_KEY not in graph.nodes[NODE_ID].metadata


def test_success_stages_gh_set_value_params_copy_on_write():
    graph = _graph([_node(NODE_ID)])

    result = _apply(graph)

    assert isinstance(result, GhScalarValueApplyResult)
    assert result.applied is True
    assert result.reason is None
    assert result.graph is not graph
    assert result.params_sha256 is not None
    assert EXECUTION_PARAMS_KEY not in graph.nodes[NODE_ID].metadata
    assert result.graph.nodes[NODE_ID].metadata[EXECUTION_PARAMS_KEY] == {
        "guid": "GUID-1",
        "value": 7.5,
    }


def test_accepts_non_dict_mappings_without_aliasing():
    action_input = {"value": 7.5}
    anchor = {"component_guid": "GUID-1"}
    graph = _graph([_node(NODE_ID)])

    result = apply_gh_scalar_value_action_to_node(
        graph,
        NODE_ID,
        action_id=ACTION_ID,
        action_input=MappingProxyType(action_input),
        anchor_binding=MappingProxyType(anchor),
    )

    action_input["value"] = 0.0
    anchor["component_guid"] = "MUTATED"
    assert result.graph.nodes[NODE_ID].metadata[EXECUTION_PARAMS_KEY] == {
        "guid": "GUID-1",
        "value": 7.5,
    }


def test_invalid_action_id_and_unknown_node_reject():
    graph = _graph([_node(NODE_ID)])

    invalid_action = _apply(graph, action_id="other")
    unknown_node = apply_gh_scalar_value_action_to_node(
        graph,
        "missing",
        action_id=ACTION_ID,
        action_input=_valid_action_input(),
        anchor_binding=_valid_anchor(),
    )

    _assert_rejected(invalid_action, graph, "invalid_action_id")
    assert unknown_node.reason == "unknown_node"
    assert unknown_node.graph is graph


def test_action_input_validation_rejects_extra_keys_guid_and_non_numbers():
    graph = _graph([_node(NODE_ID)])

    cases = [
        (["bad"], "invalid_action_input"),
        ({}, "missing_value"),
        ({"value": "7.5"}, "invalid_value"),
        ({"value": True}, "invalid_value"),
        ({"value": math.inf}, "invalid_value"),
        ({"value": 7.5, "guid": "BAD"}, "unexpected_action_input_key"),
        ({"value": 7.5, "tool_name": "gh_set_value"}, "unexpected_action_input_key"),
    ]

    for action_input, reason in cases:
        result = _apply(graph, action_input=action_input)
        _assert_rejected(result, graph, reason)


def test_anchor_validation_rejects_extra_keys_and_missing_guid():
    graph = _graph([_node(NODE_ID)])

    cases = [
        (["bad"], "invalid_anchor_binding"),
        ({}, "missing_component_guid"),
        ({"component_guid": ""}, "invalid_component_guid"),
        ({"component_guid": 123}, "invalid_component_guid"),
        ({"component_guid": "GUID-1", "value": 7.5}, "unexpected_anchor_binding_key"),
    ]

    for anchor, reason in cases:
        result = _apply(graph, anchor_binding=anchor)
        _assert_rejected(result, graph, reason)


def test_graph_copy_failed_rejects():
    graph = _graph([_node(NODE_ID), _node("other", bad=_NoDeepcopy())])

    result = _apply(graph)

    _assert_rejected(result, graph, "graph_copy_failed")


def test_applier_import_boundary():
    import rook.agent.plan_graph_gh_scalar_value_apply as module

    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")

    forbidden = {
        "rook.agent.plan_graph_param_apply",
        "BindStepSpec",
        "rook.server",
        "yaml",
    }
    assert imports.isdisjoint(forbidden)
    assert "base_params" not in source
    assert "gh_edit" not in source
    assert "code" not in source
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "base_params"
        for node in ast.walk(tree)
    )
