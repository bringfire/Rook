"""LM4Q unit tests for execute_mapped_step -- the agent-layer single mapped-step executor.
It consumes an LM4P StepMappingResult and, only if mapped, dispatches exactly that one Step
to its existing seam (producer/verifier/bind), returning the advanced graph + native seam
result. Raw dispatch-and-report: no evaluation, no fallback, no loop. In the focused
PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import rook.agent.plan_graph_step_executor as step_executor
from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_executor import execute_mapped_step
from rook.agent.plan_graph_step_mapping import StepMappingResult, map_accepted_proposal_to_step
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node


# --- helpers ---------------------------------------------------------------

def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={nid: _node(nid, st) for nid, st in id_status})


def _proposal(node_id: str) -> NodeSelectionProposal:
    return NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id=node_id,
        candidate_node_ids=(node_id,),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )


def _accept_revalidation(node_id: str) -> RevalidationResult:
    p = _proposal(node_id)
    return RevalidationResult(
        decision="ACCEPT",
        accepted_node_id=node_id,
        reject_reason=None,
        reason="sentinel accept",
        proposal=p,
        fresh_proposal=p,
        expected_selector_ids=("unique_ready_node:v1",),
    )


def _hand_mapping(step, accepted: str | None, *, mapped: bool) -> StepMappingResult:
    """Hand-build a StepMappingResult for forged/edge cases (decoupled from the real mapper)."""
    return StepMappingResult(
        mapped=mapped,
        step=step,
        accepted_node_id=accepted,
        failure=None if mapped else "revalidation_rejected",
        reason="hand-built",
        revalidation=_accept_revalidation(accepted or "x"),
    )


class FakeProducerRunner:
    """A SupportsLiveProducerNode that records its call args and returns a canned result."""

    def __init__(self, result: LiveProducerResult) -> None:
        self._result = result
        self.calls: list[tuple] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append((graph, node_id))
        return self._result


class PoisonRunner:
    """Every attribute access raises -- proves verifier/bind never touch the runner."""

    def __getattribute__(self, name):
        raise AssertionError(f"runner attribute accessed on a non-producer step: {name!r}")


class Poison:
    """Every attribute access raises -- proves expectation fields are never read."""

    def __getattribute__(self, name):
        raise AssertionError(f"poisoned expectation field accessed: {name!r}")


# --- mapped happy paths ----------------------------------------------------

@pytest.mark.asyncio
async def test_mapped_producer_step_delegates_exact_graph_and_node():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)  # SELECT_NODE("a")
    mapping = map_accepted_proposal_to_step(proposal, graph, {"a": ProducerStep("a")})
    assert mapping.mapped is True

    advanced = _graph(("a", "succeeded"))  # a distinct graph object the fake returns
    fake = FakeProducerRunner(
        LiveProducerResult(
            graph=advanced, applied=True, node_id="a",
            tool_name="gh_create_csharp_script", outcome_status="succeeded", reason=None,
        )
    )
    result = await execute_mapped_step(mapping, graph, runner=fake)

    assert result.ran is True
    assert result.kind == "producer"
    assert result.producer_result is fake._result
    assert result.graph is advanced            # advanced graph threaded through
    assert result.graph is result.producer_result.graph
    assert result.failure is None
    assert result.verifier_result is None and result.bind_result is None
    # delegation-arg pin: the fake saw the ORIGINAL input graph object + the mapped node id.
    assert fake.calls == [(graph, "a")]
    assert fake.calls[0][0] is graph


@pytest.mark.asyncio
async def test_mapped_verifier_step_runs_via_apply_verifier_step():
    # Source "a" must carry the producer role BEFORE apply_producer_result, or it returns
    # role_missing (no evidence captured) and the verifier would not apply.
    from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
    from rook.learning.plan_graph_runner import apply_producer_result

    graph = _graph(("a", "ready"), ("v", "ready"))
    graph.nodes["a"].metadata[OUTCOME_PROJECTION_ROLE_KEY] = "artifact_producer"
    raw = {"success": True, "data": {"script_receipt": {"version": 1, "operation": "create",
            "language": "csharp", "artifact_status": "usable",
            "mutation": {"status": "created", "component_guid": "g"},
            "verification": {"status": "passed", "target_error_count": 0}}}}
    graph = apply_producer_result(graph, "a", raw).graph
    assert graph.nodes["a"].evidence is not None  # role set -> evidence captured
    mapping = _hand_mapping(VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True)
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is True
    assert result.kind == "verifier"
    assert result.verifier_result is not None
    assert result.verifier_result.applied is True  # genuine happy path (evidence present)
    assert result.producer_result is None and result.bind_result is None


@pytest.mark.asyncio
async def test_mapped_bind_step_runs_via_apply_memory_bound_params():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(BindStep(node_id="a", base_params={}, bindings={}), "a", mapped=True)
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is True
    assert result.kind == "bind"
    assert result.bind_result is not None
    assert result.bind_result.applied is True


# --- ran=True even when the seam result is not-applied (no reinterpretation) ----

@pytest.mark.asyncio
async def test_verifier_seam_not_applied_still_ran():
    # source "a" has NO evidence -> apply_verifier_step returns applied=False.
    graph = _graph(("a", "ready"), ("v", "ready"))
    mapping = _hand_mapping(VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True)
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is True                       # LM4Q delegated -> ran
    assert result.failure is None
    assert result.verifier_result.applied is False  # native truth carried, not converted


@pytest.mark.asyncio
async def test_bind_seam_not_applied_still_ran():
    # bindings reference a memory fact path that does not exist -> applied=False.
    graph = _graph(("a", "ready"))
    step = BindStep(node_id="a", base_params={}, bindings={"guid": ("missing_fact", "x")})
    mapping = _hand_mapping(step, "a", mapped=True)
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is True
    assert result.failure is None
    assert result.bind_result.applied is False


# --- pre-execution refusals (the ONLY LM4Q failures) -----------------------

@pytest.mark.asyncio
async def test_not_mapped_when_mapping_not_accepted():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(None, None, mapped=False)
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is False
    assert result.kind is None
    assert result.failure == "not_mapped"
    assert result.graph is graph                    # input graph unchanged object
    assert result.producer_result is None
    assert result.verifier_result is None
    assert result.bind_result is None


@pytest.mark.asyncio
async def test_not_mapped_when_step_is_none():
    # forged: mapped=True but step is None.
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(None, "a", mapped=True)
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is False
    assert result.failure == "not_mapped"
    assert result.graph is graph


@pytest.mark.asyncio
async def test_mapping_invalid_for_non_step_value():
    # forged: mapped=True, step is not a real Step -> structural check refuses, NO crash.
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(object(), "a", mapped=True)
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is False
    assert result.kind is None
    assert result.failure == "mapping_invalid"
    assert result.graph is graph


@pytest.mark.asyncio
async def test_runner_required_for_producer_without_runner():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(ProducerStep("a"), "a", mapped=True)
    result = await execute_mapped_step(mapping, graph, runner=None)
    assert result.ran is False
    assert result.kind is None
    assert result.failure == "runner_required"
    assert result.graph is graph
    assert result.producer_result is None


# --- the runner is never touched on verifier/bind --------------------------

@pytest.mark.asyncio
async def test_runner_not_touched_for_verifier_and_bind():
    graph = _graph(("a", "ready"), ("v", "ready"))
    poison = PoisonRunner()
    vmap = _hand_mapping(VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True)
    vresult = await execute_mapped_step(vmap, graph, runner=poison)
    assert vresult.ran is True  # PoisonRunner never accessed

    bmap = _hand_mapping(BindStep(node_id="a", base_params={}, bindings={}), "a", mapped=True)
    bresult = await execute_mapped_step(bmap, graph, runner=poison)
    assert bresult.ran is True


# --- expectation fields are never read -------------------------------------

@pytest.mark.asyncio
async def test_poison_expectation_never_read():
    graph = _graph(("a", "ready"))
    advanced = _graph(("a", "succeeded"))
    fake = FakeProducerRunner(
        LiveProducerResult(graph=advanced, applied=True, node_id="a",
                           tool_name="t", outcome_status="succeeded", reason=None)
    )
    pmap = _hand_mapping(ProducerStep("a", expectation=Poison()), "a", mapped=True)
    presult = await execute_mapped_step(pmap, graph, runner=fake)
    assert presult.ran is True  # producer ran; .expectation never accessed

    vgraph = _graph(("a", "ready"), ("v", "ready"))
    vmap = _hand_mapping(
        VerifierStep(verifier_node_id="v", source_node_id="a", expected_outcome=Poison()),
        "v", mapped=True,
    )
    vresult = await execute_mapped_step(vmap, vgraph)
    assert vresult.ran is True  # verifier ran; .expected_outcome never accessed


# --- mapping audit + purity ------------------------------------------------

@pytest.mark.asyncio
async def test_mapping_carried_in_every_result():
    graph = _graph(("a", "ready"))
    refusal = _hand_mapping(None, None, mapped=False)
    r_refused = await execute_mapped_step(refusal, graph)
    assert r_refused.mapping is refusal

    run = _hand_mapping(BindStep(node_id="a", base_params={}, bindings={}), "a", mapped=True)
    r_ran = await execute_mapped_step(run, graph)
    assert r_ran.mapping is run


@pytest.mark.asyncio
async def test_pure_inputs_unchanged():
    graph = _graph(("a", "ready"), ("v", "ready"))
    before = {nid: n.status for nid, n in graph.nodes.items()}
    mapping = _hand_mapping(VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True)
    await execute_mapped_step(mapping, graph)
    assert {nid: n.status for nid, n in graph.nodes.items()} == before  # input not mutated


# --- containment guards ----------------------------------------------------

def test_module_does_not_construct_steps():
    tree = ast.parse(pathlib.Path(step_executor.__file__).read_text(encoding="utf-8"))
    ctor_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id in {"ProducerStep", "VerifierStep", "BindStep"}
    ]
    assert ctor_calls == [], "LM4Q must not construct Steps -- it returns mapping.step"


def test_import_boundary():
    src = pathlib.Path(step_executor.__file__).read_text(encoding="utf-8")
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
    # required, allowed imports
    assert "rook.agent.plan_graph_step_mapping" in imported, imported
    assert "rook.agent.plan_graph_sequence_runner" in imported, imported
    assert "rook.agent.plan_graph_live_runner" in imported, imported
    assert "rook.agent.plan_graph_param_apply" in imported, imported
    # banned imports
    assert "rook.agent.base_agent" not in imported, imported
    assert not any(m.startswith("rook.server") for m in imported), imported
    assert not any("dispatch" in m for m in imported), imported
    assert not any("litellm" in m for m in imported), imported
    # banned referenced names (rebuild-the-ladder / select / terminal / evaluate)
    for banned in (
        "propose_next_node",
        "revalidate_proposal",
        "map_accepted_proposal_to_step",
        "runnable_nodes",
        "apply_outcome",
        "select_template",
        "run_explicit_sequence",
        "build_live_producer_record",
    ):
        assert banned not in referenced, banned
    # required referenced names (the execution seams LM4Q legitimately uses)
    assert "run_live_producer_node" in referenced
    assert "apply_verifier_step" in referenced
    assert "apply_memory_bound_params" in referenced
