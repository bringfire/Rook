from __future__ import annotations

import copy

import pytest

from rook.learning.plan_graph import (
    NodeEvidence,
    NodeOutcome,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    apply_outcome,
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


def test_apply_outcome_updates_node_evidence_retry_and_unlocked_requires_target():
    graph = initialize_graph(
        PlanGraph(
            nodes={
                "create": PlanGraphNode(id="create", intent="Create"),
                "verify": PlanGraphNode(id="verify", intent="Verify"),
            },
            edges=[PlanGraphEdge(source="create", target="verify", kind="requires")],
        )
    )
    evidence = NodeEvidence(
        tool_status="success",
        verified=True,
        receipt={"version": 1, "artifact_status": "usable"},
        repair_anchor={"component_guid": "abc"},
    )

    updated = apply_outcome(
        graph,
        "create",
        NodeOutcome(
            status="succeeded",
            evidence=evidence,
            memory_updates={
                "facts": {"component_guid": "abc"},
                "node_summary": "created component abc",
            },
        ),
    )

    assert graph.nodes["create"].status == "ready"
    assert graph.nodes["verify"].status == "pending"
    assert updated.nodes["create"].status == "succeeded"
    assert updated.nodes["create"].evidence == evidence
    assert updated.nodes["create"].retry.attempts == 1
    assert updated.nodes["create"].retry.retry_exhausted is True
    assert updated.nodes["verify"].status == "ready"
    assert updated.memory.facts["component_guid"] == "abc"
    assert updated.memory.node_summaries["create"] == "created component abc"


def test_apply_outcome_deep_copies_evidence_and_memory_updates():
    graph = initialize_graph(
        PlanGraph(
            nodes={
                "create": PlanGraphNode(
                    id="create",
                    intent="Create",
                    metadata={"pins_out": [{"name": "B"}]},
                ),
            },
        )
    )
    outcome = NodeOutcome(
        status="needs_repair",
        evidence=NodeEvidence(
            receipt={"script_receipt": {"artifact_status": "created_with_errors"}},
            repair_anchor={"pins_out": [{"name": "B"}]},
        ),
        memory_updates={
            "facts": {"repair_anchor": {"component_guid": "abc"}},
            "node_summary": "needs repair",
        },
    )

    updated = apply_outcome(graph, "create", outcome)
    outcome.evidence.receipt["script_receipt"]["artifact_status"] = "mutated"
    outcome.evidence.repair_anchor["pins_out"][0]["name"] = "Mutated"
    outcome.memory_updates["facts"]["repair_anchor"]["component_guid"] = "mutated"
    graph.nodes["create"].metadata["pins_out"][0]["name"] = "MutatedGraph"

    assert (
        updated.nodes["create"].evidence.receipt["script_receipt"]["artifact_status"]
        == "created_with_errors"
    )
    assert updated.nodes["create"].evidence.repair_anchor["pins_out"][0]["name"] == "B"
    assert updated.memory.facts["repair_anchor"]["component_guid"] == "abc"
    assert updated.nodes["create"].metadata["pins_out"][0]["name"] == "B"


def test_apply_outcome_raises_for_unknown_node_id():
    graph = PlanGraph(nodes={"known": PlanGraphNode(id="known", intent="Known")})

    with pytest.raises(ValueError, match="Unknown PlanGraph node"):
        apply_outcome(graph, "missing", NodeOutcome(status="succeeded"))


def test_apply_outcome_raises_for_unknown_edge_endpoint():
    graph = initialize_graph(
        PlanGraph(
            nodes={"source": PlanGraphNode(id="source", intent="Source")},
            edges=[PlanGraphEdge(source="source", target="missing", kind="requires")],
        )
    )

    with pytest.raises(ValueError, match="unknown target"):
        apply_outcome(graph, "source", NodeOutcome(status="succeeded"))


@pytest.mark.parametrize(
    "edge_kind,outcome_status,unlocks",
    [
        ("on_success", "succeeded", True),
        ("on_repair", "needs_repair", True),
        ("on_failure", "failed", True),
        ("on_failure", "blocked", True),
        ("on_escalation", "needs_escalation", True),
        ("on_repair", "failed", False),
        ("on_success", "needs_repair", False),
        ("on_escalation", "failed", False),
    ],
)
def test_transition_edges_unlock_only_for_matching_outcomes(
    edge_kind, outcome_status, unlocks
):
    graph = initialize_graph(
        PlanGraph(
            nodes={
                "source": PlanGraphNode(id="source", intent="Source"),
                "target": PlanGraphNode(id="target", intent="Target"),
            },
            edges=[PlanGraphEdge(source="source", target="target", kind=edge_kind)],
        )
    )

    updated = apply_outcome(graph, "source", NodeOutcome(status=outcome_status))

    assert updated.nodes["target"].status == ("ready" if unlocks else "pending")


def test_unlock_waits_for_all_requires_dependencies():
    graph = initialize_graph(
        PlanGraph(
            nodes={
                "a": PlanGraphNode(id="a", intent="A"),
                "b": PlanGraphNode(id="b", intent="B"),
                "target": PlanGraphNode(id="target", intent="Target"),
            },
            edges=[
                PlanGraphEdge(source="a", target="target", kind="requires"),
                PlanGraphEdge(source="b", target="target", kind="requires"),
            ],
        )
    )

    after_a = apply_outcome(graph, "a", NodeOutcome(status="succeeded"))
    after_b = apply_outcome(after_a, "b", NodeOutcome(status="succeeded"))

    assert after_a.nodes["target"].status == "pending"
    assert after_b.nodes["target"].status == "ready"


def test_unlock_does_not_change_non_pending_target():
    graph = initialize_graph(
        PlanGraph(
            nodes={
                "source": PlanGraphNode(id="source", intent="Source"),
                "target": PlanGraphNode(
                    id="target", intent="Target", status="blocked"
                ),
            },
            edges=[PlanGraphEdge(source="source", target="target", kind="requires")],
        )
    )

    updated = apply_outcome(graph, "source", NodeOutcome(status="succeeded"))

    assert updated.nodes["target"].status == "blocked"
