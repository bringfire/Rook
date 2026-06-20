from __future__ import annotations

import copy

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    graph_status,
    initialize_graph,
    runnable_nodes,
)


def test_initialize_graph_marks_root_nodes_ready_without_mutating_original():
    graph = PlanGraph(
        nodes={
            "root": PlanGraphNode(id="root", intent="Root node"),
            "child": PlanGraphNode(id="child", intent="Child node"),
        },
        edges=[PlanGraphEdge(source="root", target="child", kind="requires")],
    )

    initialized = initialize_graph(graph)

    assert graph.nodes["root"].status == "pending"
    assert graph.nodes["child"].status == "pending"
    assert initialized.nodes["root"].status == "ready"
    assert initialized.nodes["child"].status == "pending"


def test_initialize_graph_marks_all_roots_ready():
    graph = PlanGraph(
        nodes={
            "a": PlanGraphNode(id="a", intent="Root A"),
            "b": PlanGraphNode(id="b", intent="Root B"),
            "c": PlanGraphNode(id="c", intent="Child C"),
        },
        edges=[PlanGraphEdge(source="a", target="c", kind="requires")],
    )

    initialized = initialize_graph(graph)

    assert {node.id for node in runnable_nodes(initialized)} == {"a", "b"}
    assert initialized.nodes["c"].status == "pending"


def test_runnable_nodes_is_read_only():
    graph = initialize_graph(
        PlanGraph(
            nodes={"root": PlanGraphNode(id="root", intent="Root node")},
        )
    )
    before = copy.deepcopy(graph)

    first = runnable_nodes(graph)
    second = runnable_nodes(graph)

    assert [node.id for node in first] == ["root"]
    assert [node.id for node in second] == ["root"]
    assert graph == before


def test_graph_with_cycle_and_no_roots_initializes_blocked_not_pending():
    graph = PlanGraph(
        nodes={
            "a": PlanGraphNode(id="a", intent="A"),
            "b": PlanGraphNode(id="b", intent="B"),
        },
        edges=[
            PlanGraphEdge(source="a", target="b", kind="requires"),
            PlanGraphEdge(source="b", target="a", kind="requires"),
        ],
    )

    initialized = initialize_graph(graph)

    assert runnable_nodes(initialized) == []
    assert graph_status(initialized) == "blocked"


def test_graph_status_is_complete_when_all_terminal_nodes_finished():
    graph = PlanGraph(
        nodes={
            "root": PlanGraphNode(id="root", intent="Root", status="succeeded"),
            "done": PlanGraphNode(
                id="done",
                intent="Done",
                status="skipped",
                is_terminal=True,
            ),
        },
        edges=[PlanGraphEdge(source="root", target="done", kind="requires")],
    )

    assert graph_status(graph) == "complete"


def test_default_factories_do_not_share_mutable_state():
    first = PlanGraphNode(id="first", intent="First")
    second = PlanGraphNode(id="second", intent="Second")
    first.metadata["x"] = {"nested": 1}
    first.retry.attempts = 1

    assert second.metadata == {}
    assert second.retry.attempts == 0

    graph_a = PlanGraph()
    graph_b = PlanGraph()
    graph_a.memory.facts["component_guid"] = "abc"

    assert graph_b.memory.facts == {}
