from __future__ import annotations

import copy

import pytest

from rook.learning.plan_graph import (
    NodeEvidence,
    NodeOutcome,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    RetryState,
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
            nodes={
                "root": PlanGraphNode(
                    id="root",
                    intent="Root node",
                    metadata={"steps": [{"name": "original"}]},
                    evidence=NodeEvidence(
                        receipt={"artifact_status": "original"},
                    ),
                )
            },
        )
    )
    before = copy.deepcopy(graph)

    first = runnable_nodes(graph)
    second = runnable_nodes(graph)
    first[0].status = "running"
    first[0].metadata["steps"][0]["name"] = "mutated"
    first[0].evidence.receipt["artifact_status"] = "mutated"
    first[0].retry.attempts = 99

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


def test_retry_exhaustion_does_not_auto_escalate():
    graph = initialize_graph(
        PlanGraph(
            nodes={
                "node": PlanGraphNode(
                    id="node",
                    intent="Try once",
                    retry=RetryState(max_attempts=1),
                ),
            },
        )
    )

    updated = apply_outcome(
        graph,
        "node",
        NodeOutcome(status="failed", error="bad input"),
    )

    assert updated.nodes["node"].retry.attempts == 1
    assert updated.nodes["node"].retry.retry_exhausted is True
    assert updated.nodes["node"].retry.last_error == "bad input"
    assert updated.nodes["node"].status == "failed"
    assert graph_status(updated) == "failed"


def test_retry_last_error_falls_back_to_evidence_error():
    graph = initialize_graph(
        PlanGraph(
            nodes={"node": PlanGraphNode(id="node", intent="Node")},
        )
    )

    updated = apply_outcome(
        graph,
        "node",
        NodeOutcome(status="failed", evidence=NodeEvidence(error="evidence error")),
    )

    assert updated.nodes["node"].retry.last_error == "evidence error"


def test_graph_memory_last_writer_wins_for_facts_and_summary():
    graph = initialize_graph(
        PlanGraph(
            nodes={"node": PlanGraphNode(id="node", intent="Node")},
        )
    )
    first = apply_outcome(
        graph,
        "node",
        NodeOutcome(
            status="failed",
            memory_updates={
                "facts": {"component_guid": "first"},
                "node_summary": "first summary",
            },
        ),
    )
    second = apply_outcome(
        first,
        "node",
        NodeOutcome(
            status="needs_repair",
            memory_updates={
                "facts": {"component_guid": "second"},
                "node_summary": "second summary",
            },
        ),
    )

    assert second.memory.facts["component_guid"] == "second"
    assert second.memory.node_summaries["node"] == "second summary"


def test_graph_status_pending_running_complete_failed_blocked_and_escalation():
    pending_graph = PlanGraph(nodes={"root": PlanGraphNode(id="root", intent="Root")})
    assert graph_status(pending_graph) == "pending"
    assert graph_status(initialize_graph(pending_graph)) == "running"

    complete_graph = PlanGraph(
        nodes={
            "done": PlanGraphNode(
                id="done",
                intent="Done",
                status="succeeded",
                is_terminal=True,
            ),
        },
    )
    assert graph_status(complete_graph) == "complete"

    skipped_terminal = PlanGraph(
        nodes={
            "done": PlanGraphNode(
                id="done",
                intent="Done",
                status="skipped",
                is_terminal=True,
            ),
        },
    )
    assert graph_status(skipped_terminal) == "complete"

    failed_graph = PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node", status="failed")},
    )
    assert graph_status(failed_graph) == "failed"

    blocked_graph = PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node", status="blocked")},
    )
    assert graph_status(blocked_graph) == "blocked"

    escalation_graph = PlanGraph(
        nodes={
            "node": PlanGraphNode(
                id="node",
                intent="Node",
                status="needs_escalation",
            )
        },
    )
    assert graph_status(escalation_graph) == "needs_escalation"


def test_graph_status_complete_takes_precedence_over_runnable_nodes():
    graph = PlanGraph(
        nodes={
            "done": PlanGraphNode(
                id="done",
                intent="Done",
                status="succeeded",
                is_terminal=True,
            ),
            "cleanup": PlanGraphNode(
                id="cleanup",
                intent="Optional cleanup",
                status="ready",
            ),
        },
    )

    assert graph_status(graph) == "complete"


def test_needs_repair_without_unlocked_repair_edge_is_not_running():
    graph = PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node", status="needs_repair")},
    )

    assert runnable_nodes(graph) == []
    assert graph_status(graph) == "blocked"


@pytest.mark.parametrize("bad_status", ["pending", "ready", "running"])
def test_node_outcome_rejects_administrative_statuses(bad_status):
    with pytest.raises(ValueError, match="not an outcome state"):
        NodeOutcome(status=bad_status)
