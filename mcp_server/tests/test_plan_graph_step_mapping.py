"""LM4P unit tests for map_accepted_proposal_to_step -- the agent-layer gated lookup that
delegates to LM4O revalidate_proposal and, only if ACCEPTED, returns the caller-authored
prebuilt Step for the accepted node. In the focused PlanGraph gate (test_plan_graph*.py).
Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import rook.agent.plan_graph_step_mapping as step_mapping
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={nid: _node(nid, st) for nid, st in id_status})


def _select(node_id: str) -> NodeSelectionProposal:
    return NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id=node_id,
        candidate_node_ids=(node_id,),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )


def test_mapped_producer_step():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)  # SELECT_NODE("a")
    step = ProducerStep("a", expectation=None)
    result = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert result.mapped is True
    assert result.step is step  # exact caller object
    assert result.accepted_node_id == "a"
    assert result.failure is None
    assert result.revalidation.decision == "ACCEPT"


def test_mapped_verifier_step_targets_via_verifier_node_id():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    step = VerifierStep(verifier_node_id="a", source_node_id="src")
    result = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert result.mapped is True
    assert result.step is step


def test_mapped_bind_step():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    step = BindStep(node_id="a", base_params={}, bindings={})
    result = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert result.mapped is True
    assert result.step is step


def test_revalidation_rejected_stale():
    # Supplied SELECT("a") but the current graph's unique-ready node is "b".
    proposal = _select("a")
    graph = _graph(("a", "succeeded"), ("b", "ready"))
    result = map_accepted_proposal_to_step(proposal, graph, {"a": ProducerStep("a")})
    assert result.mapped is False
    assert result.failure == "revalidation_rejected"
    assert result.step is None
    assert result.accepted_node_id is None
    assert result.revalidation.reject_reason == "selected_not_ready"


def test_revalidation_rejected_untrusted():
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="other:v9",
    )
    graph = _graph(("a", "ready"))
    result = map_accepted_proposal_to_step(proposal, graph, {"a": ProducerStep("a")})
    assert result.mapped is False
    assert result.failure == "revalidation_rejected"
    assert result.revalidation.reject_reason == "untrusted_selector"


def test_no_step_for_node():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    result = map_accepted_proposal_to_step(proposal, graph, {})  # no entry for "a"
    assert result.mapped is False
    assert result.failure == "no_step_for_node"
    assert result.accepted_node_id == "a"
    assert result.step is None


def test_step_map_invalid_non_step_value():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    result = map_accepted_proposal_to_step(proposal, graph, {"a": object()})
    assert result.mapped is False
    assert result.failure == "step_map_invalid"
    assert result.step is None
    assert result.accepted_node_id == "a"


def test_step_node_mismatch_producer():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    # The map entry for "a" is a Step that targets a DIFFERENT node "Y".
    result = map_accepted_proposal_to_step(proposal, graph, {"a": ProducerStep("Y")})
    assert result.mapped is False
    assert result.failure == "step_node_mismatch"
    assert result.step is None  # mismatched step is not returned


def test_step_node_mismatch_verifier():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    result = map_accepted_proposal_to_step(
        proposal, graph, {"a": VerifierStep(verifier_node_id="Y", source_node_id="Z")}
    )
    assert result.mapped is False
    assert result.failure == "step_node_mismatch"
    assert result.step is None


def test_revalidate_seam_is_used(monkeypatch):
    # The load-bearing pin: LM4P delegates to LM4O's revalidate_proposal seam and passes
    # through the EXACT (proposal, graph, expected_selector_ids). Patch it to a sentinel
    # ACCEPT; with a matching step_map the run maps, proving the sentinel drove the result.
    received = {}
    supplied = _select("s")
    sentinel = RevalidationResult(
        decision="ACCEPT",
        accepted_node_id="s",
        reject_reason=None,
        reason="sentinel accept",
        proposal=supplied,
        fresh_proposal=supplied,
        expected_selector_ids=("unique_ready_node:v1",),
    )

    def _fake_revalidate(proposal, graph, expected_selector_ids):
        received["args"] = (proposal, graph, expected_selector_ids)
        return sentinel

    monkeypatch.setattr(step_mapping, "revalidate_proposal", _fake_revalidate)
    sentinel_graph = object()  # LM4P must not inspect the graph itself
    step = ProducerStep("s")
    result = map_accepted_proposal_to_step(
        supplied, sentinel_graph, {"s": step}, expected_selector_ids=("unique_ready_node:v1",)
    )
    assert result.mapped is True
    assert result.step is step
    assert result.revalidation is sentinel
    assert received["args"][0] is supplied
    assert received["args"][1] is sentinel_graph
    assert received["args"][2] == ("unique_ready_node:v1",)


def test_frozen_pure_inputs_unchanged():
    graph = _graph(("a", "ready"), ("b", "pending"))
    node_a = graph.nodes["a"]
    before = {nid: n.status for nid, n in graph.nodes.items()}
    proposal = propose_next_node(graph)
    step = ProducerStep("a")
    step_map = {"a": step}
    r1 = map_accepted_proposal_to_step(proposal, graph, step_map)
    r2 = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert {nid: n.status for nid, n in graph.nodes.items()} == before
    assert graph.nodes["a"] is node_a
    assert step_map == {"a": step}
    assert r1 == r2
    assert r1.step is step  # same object, not rebuilt


def test_module_does_not_construct_steps():
    # Containment pin: the module must be LOOKUP-only -- no constructor CALL to a Step type.
    # isinstance(...) uses the classes as args (not a call to them) and annotations are fine.
    import rook.agent.plan_graph_step_mapping as mod

    tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
    step_ctor_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"ProducerStep", "VerifierStep", "BindStep"}
    ]
    assert step_ctor_calls == [], "LM4P must not construct Steps -- lookup only"


def test_import_boundary():
    import rook.agent.plan_graph_step_mapping as mod

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
    # Importing plan_graph_sequence_runner for the Step types is REQUIRED and allowed; the
    # guard bans forbidden runner/dispatch NAMES, never that whole module.
    assert "rook.agent.plan_graph_sequence_runner" in imported, imported
    assert "rook.agent.base_agent" not in imported, imported
    assert not any(m.startswith("rook.server") for m in imported), imported
    assert not any("dispatch" in m for m in imported), imported
    assert not any("litellm" in m for m in imported), imported
    for banned in (
        "propose_next_node",
        "run_explicit_sequence",
        "run_live_producer_node",
        "SupportsLiveProducerNode",
        "apply_outcome",
        "apply_verifier_step",
        "apply_producer_result",
    ):
        assert banned not in referenced, banned
