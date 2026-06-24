"""LM4N unit tests for propose_next_node -- the pure learning-layer node-selection
proposal primitive. Observes the canonical runnable_nodes seam; proposes a node ONLY when
exactly one is ready; else halts. In the focused PlanGraph gate (test_plan_graph*.py).
Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import rook.learning.plan_graph_selector as selector
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_selector import propose_next_node


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={nid: _node(nid, st) for nid, st in id_status})


def test_exactly_one_ready_selects():
    graph = _graph(("a", "ready"), ("b", "pending"))
    p = propose_next_node(graph)
    assert p.decision == "SELECT_NODE"
    assert p.selected_node_id == "a"
    assert p.candidate_node_ids == ("a",)
    assert p.ready_count == 1
    assert p.selector_id == "unique_ready_node:v1"
    assert p.reason == "exactly one admissible ready node"


def test_zero_ready_halts_none():
    graph = _graph(("a", "pending"), ("b", "succeeded"))
    p = propose_next_node(graph)
    assert p.decision == "HALT_NONE_READY"
    assert p.selected_node_id is None
    assert p.candidate_node_ids == ()
    assert p.ready_count == 0
    assert p.selector_id == "unique_ready_node:v1"
    assert p.reason == "no admissible ready node"


def test_multiple_ready_halts_ambiguous():
    graph = _graph(("a", "ready"), ("b", "ready"))
    p = propose_next_node(graph)
    assert p.decision == "HALT_AMBIGUOUS_READY"
    assert p.selected_node_id is None
    assert p.candidate_node_ids == ("a", "b")
    assert p.ready_count == 2
    assert p.reason == "2 admissible ready nodes; refusing to choose"


def test_candidate_sorting_determinism():
    # Insert ready nodes out of lexical order -> candidates come back sorted.
    graph = _graph(("m", "ready"), ("a", "ready"), ("z", "ready"))
    p = propose_next_node(graph)
    assert p.candidate_node_ids == ("a", "m", "z")
    assert p.decision == "HALT_AMBIGUOUS_READY"


def test_observe_not_bypass_outcome():
    # Only the ready node is a candidate; needs_repair/pending/running are excluded.
    graph = _graph(
        ("r", "ready"),
        ("nr", "needs_repair"),
        ("p", "pending"),
        ("run", "running"),
    )
    p = propose_next_node(graph)
    assert p.candidate_node_ids == ("r",)
    assert p.decision == "SELECT_NODE"
    assert p.selected_node_id == "r"


def test_uses_runnable_nodes_seam(monkeypatch):
    # The load-bearing pin: candidates derive from the canonical runnable_nodes seam, not
    # from a private status check. Patch the seam to return sentinels with UNSORTED ids and
    # assert (a) candidates come from the patched return (sorted), (b) the patched function
    # received the EXACT graph object. An impl that filtered status=="ready" would fail.
    received = []

    class _Sentinel:
        def __init__(self, id_: str) -> None:
            self.id = id_

    def _fake_runnable_nodes(graph):
        received.append(graph)
        return [_Sentinel("z"), _Sentinel("a"), _Sentinel("m")]

    monkeypatch.setattr(selector, "runnable_nodes", _fake_runnable_nodes)
    sentinel_graph = object()  # selector must only route this through runnable_nodes
    p = propose_next_node(sentinel_graph)
    assert p.candidate_node_ids == ("a", "m", "z")
    assert p.ready_count == 3
    assert p.decision == "HALT_AMBIGUOUS_READY"
    assert len(received) == 1 and received[0] is sentinel_graph


def test_frozen_snapshot():
    graph = _graph(("a", "ready"), ("b", "pending"))
    node_a = graph.nodes["a"]
    before = {nid: n.status for nid, n in graph.nodes.items()}
    p1 = propose_next_node(graph)
    p2 = propose_next_node(graph)
    # input graph unchanged (statuses + node identity), and the call is deterministic.
    assert {nid: n.status for nid, n in graph.nodes.items()} == before
    assert graph.nodes["a"] is node_a  # the selector did not replace/rebuild the node
    assert p1 == p2


def test_selector_id_on_all_decisions():
    select = propose_next_node(_graph(("a", "ready")))
    none = propose_next_node(_graph(("a", "pending")))
    ambig = propose_next_node(_graph(("a", "ready"), ("b", "ready")))
    assert select.decision == "SELECT_NODE"
    assert none.decision == "HALT_NONE_READY"
    assert ambig.decision == "HALT_AMBIGUOUS_READY"
    for p in (select, none, ambig):
        assert p.selector_id == "unique_ready_node:v1"


def test_selector_import_boundary():
    # Pure learning-layer: no agent/dispatcher/server/model import, and no transition
    # helper referenced (the selector never mutates the graph).
    import rook.learning.plan_graph_selector as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    assert not any(m.startswith("rook.agent") for m in imported), imported
    assert not any(m.startswith("rook.server") for m in imported), imported
    assert not any("dispatch" in m for m in imported), imported
    assert not any("litellm" in m for m in imported), imported
    for banned in ("apply_outcome", "apply_verifier_step", "apply_producer_result"):
        assert banned not in referenced, banned
