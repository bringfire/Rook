"""LM4O unit tests for revalidate_proposal -- the pure learning-layer gate that distrusts
a supplied NodeSelectionProposal and revalidates it against the current graph by
re-deriving via propose_next_node and requiring full equality. In the focused PlanGraph
gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import rook.learning.plan_graph_revalidation as revalidation
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node
from rook.learning.plan_graph_revalidation import revalidate_proposal


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={nid: _node(nid, st) for nid, st in id_status})


def test_accept_when_proposal_equals_fresh():
    graph = _graph(("a", "ready"), ("b", "pending"))
    proposal = propose_next_node(graph)  # SELECT_NODE("a")
    assert proposal.decision == "SELECT_NODE" and proposal.selected_node_id == "a"
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "ACCEPT"
    assert result.accepted_node_id == "a"
    assert result.reject_reason is None
    assert result.fresh_proposal == proposal
    assert result.expected_selector_ids == ("unique_ready_node:v1",)


def test_reject_untrusted_selector_skips_rederive():
    graph = _graph(("a", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="other:v9",
    )
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "untrusted_selector"
    assert result.accepted_node_id is None
    assert result.fresh_proposal is None  # re-derivation skipped: provenance untrusted


def test_reject_not_a_selection():
    graph = _graph(("a", "ready"), ("b", "ready"))
    halt = propose_next_node(graph)  # HALT_AMBIGUOUS_READY
    assert halt.decision == "HALT_AMBIGUOUS_READY"
    result = revalidate_proposal(halt, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "not_a_selection"
    assert result.accepted_node_id is None


def test_reject_none_ready_when_graph_advanced():
    # Supplied a SELECT("a") from an earlier snapshot; current graph has nothing ready.
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    graph = _graph(("a", "succeeded"), ("b", "pending"))  # zero ready
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "none_ready"
    assert result.fresh_proposal is not None
    assert result.fresh_proposal.decision == "HALT_NONE_READY"


def test_reject_no_longer_unique_when_forked():
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    graph = _graph(("a", "ready"), ("b", "ready"))  # forked
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "no_longer_unique"
    assert result.fresh_proposal.decision == "HALT_AMBIGUOUS_READY"


def test_reject_selected_not_ready_no_fallback():
    # Current graph's unique ready node is "b", not the supplied "a". No fallback: the gate
    # rejects rather than substituting the (valid) fresh selection of "b".
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    graph = _graph(("a", "succeeded"), ("b", "ready"))  # unique ready is "b"
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "selected_not_ready"
    assert result.accepted_node_id is None
    assert result.fresh_proposal.selected_node_id == "b"  # present, but NOT substituted


def test_reject_proposal_mismatch_candidates_and_count():
    # P2: same selected node, but the supplied proposal's candidate_node_ids/ready_count
    # do not match the fresh re-derivation -> whole-proposal distrust rejects it.
    graph = _graph(("x", "ready"))  # fresh: SELECT("x"), candidates ("x",), ready_count 1
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="x",
        candidate_node_ids=("x", "y"),
        ready_count=2,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "proposal_mismatch"
    assert result.accepted_node_id is None


def test_reject_proposal_mismatch_selector_not_laundered():
    # P3: "custom:v1" is in expected_selector_ids (clears the untrusted gate), but the
    # fresh re-derivation's selector_id is "unique_ready_node:v1", so proposal != fresh.
    graph = _graph(("x", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="x",
        candidate_node_ids=("x",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="custom:v1",
    )
    result = revalidate_proposal(
        proposal, graph, expected_selector_ids=("custom:v1", "unique_ready_node:v1")
    )
    assert result.decision == "REJECT"
    assert result.reject_reason == "proposal_mismatch"
    assert result.accepted_node_id is None


def test_reject_proposal_mismatch_tampered_reason():
    graph = _graph(("x", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="x",
        candidate_node_ids=("x",),
        ready_count=1,
        reason="trust me",  # tampered audit field
        selector_id="unique_ready_node:v1",
    )
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "proposal_mismatch"


def test_rederive_seam_is_used(monkeypatch):
    # The load-bearing pin: the gate re-derives via the module-level propose_next_node seam
    # and received the EXACT graph object. Patch it to a sentinel; make the supplied
    # proposal equal the sentinel so the run ACCEPTs, proving the sentinel drove the result.
    received = []
    sentinel = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="sentinel",
        candidate_node_ids=("sentinel",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )

    def _fake_propose_next_node(graph):
        received.append(graph)
        return sentinel

    monkeypatch.setattr(revalidation, "propose_next_node", _fake_propose_next_node)
    sentinel_graph = object()  # gate must only route this through propose_next_node
    result = revalidate_proposal(sentinel, sentinel_graph)
    assert result.decision == "ACCEPT"
    assert result.accepted_node_id == "sentinel"
    assert result.fresh_proposal is sentinel
    assert len(received) == 1 and received[0] is sentinel_graph


def test_default_expected_rejects_foreign_selector_as_untrusted():
    graph = _graph(("a", "ready"))
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="custom:v1",
    )
    # Default expected does NOT include "custom:v1" -> untrusted (distinct from the P3 path
    # where it IS in expected but still fails full equality).
    result = revalidate_proposal(proposal, graph)
    assert result.decision == "REJECT"
    assert result.reject_reason == "untrusted_selector"
    assert result.fresh_proposal is None


def test_frozen_pure_inputs_unchanged():
    graph = _graph(("a", "ready"), ("b", "pending"))
    node_a = graph.nodes["a"]
    before = {nid: n.status for nid, n in graph.nodes.items()}
    proposal = propose_next_node(graph)
    r1 = revalidate_proposal(proposal, graph)
    r2 = revalidate_proposal(proposal, graph)
    assert {nid: n.status for nid, n in graph.nodes.items()} == before
    assert graph.nodes["a"] is node_a  # graph not rebuilt
    assert r1 == r2  # deterministic


def test_revalidation_import_boundary():
    # Pure learning-layer: no agent/dispatcher/server/model import, and no transition
    # reducer referenced (the gate never mutates the graph).
    import rook.learning.plan_graph_revalidation as mod

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
