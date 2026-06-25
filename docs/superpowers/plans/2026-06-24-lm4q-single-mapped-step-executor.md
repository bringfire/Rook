# LM4Q — Single Mapped-Step Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agent-layer `execute_mapped_step(mapping, graph, runner=None)` that, given an already-mapped LM4P `StepMappingResult`, executes exactly that one Step through the existing seam for its kind (producer/verifier/bind) and returns the advanced graph plus the native seam result — the first bounded execution authority, never a scheduler.

**Architecture:** One new agent-layer module `agent/plan_graph_step_executor.py`. It consumes the ladder's artifact (`StepMappingResult`) and dispatches one Step: `ProducerStep → runner.run_live_producer_node`, `VerifierStep → apply_verifier_step`, `BindStep → apply_memory_bound_params`. `async` (the producer branch awaits). Raw dispatch-and-report: no selection, no mapping, no revalidation, no loop, no terminal `done`, no expectation evaluation, no fallback. Three test deliverables: pure unit tests, an offline chain execution guard, and one narrow `requires_rhino` live producer smoke.

**Tech Stack:** Python 3.12, pytest (+ pytest-asyncio), Rook `agent`/`learning` packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

From the spec (`docs/superpowers/specs/2026-06-24-lm4q-single-mapped-step-executor-design.md`).

- **Execute the artifact, never rebuild the ladder.** Consume a `StepMappingResult`; never propose, revalidate, map, or select. AST-guarded: `propose_next_node`, `revalidate_proposal`, `map_accepted_proposal_to_step`, `runnable_nodes` are neither imported nor referenced.
- **One step, no loop, no fold.** Run exactly `mapping.step`. No iteration, no `run_explicit_sequence` (no length-1-sequence smuggling — AST-guarded), no early-stop fold.
- **No terminal construction.** No `apply_outcome` (AST-guarded). Never marks `done`.
- **No fallback / no substitution.** A refused mapping runs nothing — even when a different, now-correct Step exists. Never substitute a "fresh correct step".
- **Execute, don't evaluate.** Return the native seam result; never compute pass/fail; **never read `ProducerStep.expectation` / `VerifierStep.expected_outcome`** (enforced by poison-expectation objects). `build_live_producer_record` is neither imported nor referenced (AST-guarded).
- **Distrust the public artifact's shape.** Before dispatch, a minimal structural check: if `mapping.step` is not a `ProducerStep`/`VerifierStep`/`BindStep` (explicit tuple `isinstance`, never the `Step` union alias at runtime), refuse with `mapping_invalid` — checked **before** reading any field of `step`. This validates artifact shape only; it does **not** re-run LM4P's target-node validation.
- **Honest runner dependency.** `runner: SupportsLiveProducerNode | None = None`. Only `ProducerStep` may touch it; verifier/bind must not. A mapped `ProducerStep` with `runner is None` → clean `runner_required` refusal (run nothing, graph unchanged).
- **LM4Q failures are ONLY pre-execution refusals:** `not_mapped`, `mapping_invalid`, `runner_required`. Once a seam is invoked, `ran=True` **even if** the seam result says not-applied/failed; the native seam result carries that truth and LM4Q never reinterprets it.
- **Imports:** `StepMappingResult` (agent `plan_graph_step_mapping`); `ProducerStep`/`VerifierStep`/`BindStep` (agent `plan_graph_sequence_runner`); `SupportsLiveProducerNode` (agent `plan_graph_live_runner`); `LiveProducerResult` (agent `plan_graph_live`); `VerifierStepResult` + `apply_verifier_step` (learning `plan_graph_runner`); `MemoryParamApplyResult` + `apply_memory_bound_params` (agent `plan_graph_param_apply`); `PlanGraph` `TYPE_CHECKING`-quoted; stdlib `dataclass`/`typing`. **Banned (AST-guarded):** `rook.agent.base_agent`, dispatcher/server, LiteLLM/model imports; the referenced names `propose_next_node`, `revalidate_proposal`, `map_accepted_proposal_to_step`, `runnable_nodes`, `apply_outcome`, `select_template`, `run_explicit_sequence`, `build_live_producer_record`. (`run_live_producer_node`, `apply_verifier_step`, `apply_memory_bound_params`, `SupportsLiveProducerNode` are REQUIRED and allowed.)
- **No Step construction.** The module contains no constructor call to `ProducerStep`/`VerifierStep`/`BindStep` (AST-guarded). It returns `mapping.step`, never builds one. (isinstance + annotations allowed.)
- **Pure-of-policy:** never mutates `mapping`; on every refusal `result.graph is graph` (the input object). Verifier/bind never touch `runner`.
- **Production change is EXACTLY one new module:** `mcp_server/src/rook/agent/plan_graph_step_executor.py`. No edits to any existing `src/` file; `base_agent.py` byte-stable; LM4M/LM4N/LM4O/LM4P modules + `plan_graph_walker.py` untouched. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- **One narrow live test** (`requires_rhino`, outside the `test_plan_graph*` glob). Whole-branch diff = spec + plan + 1 module + 2 automated test files + 1 live test file (6 paths).

## Seam reference (already merged — consume, do not modify)

- `StepMappingResult(mapped, step, accepted_node_id, failure, reason, revalidation)` (frozen) and `map_accepted_proposal_to_step(proposal, graph, step_map, expected_selector_ids=("unique_ready_node:v1",)) -> StepMappingResult` — `rook.agent.plan_graph_step_mapping`. `step` is non-None only on `mapped=True`.
- `Step = ProducerStep | VerifierStep | BindStep`; `ProducerStep(node_id, expectation=None)`; `VerifierStep(verifier_node_id, source_node_id, expected_outcome=None)`; `BindStep(node_id, base_params, bindings)` — all frozen — `rook.agent.plan_graph_sequence_runner`.
- `SupportsLiveProducerNode` Protocol with `async run_live_producer_node(self, graph, node_id) -> LiveProducerResult` — `rook.agent.plan_graph_live_runner`.
- `LiveProducerResult(graph, applied, node_id, tool_name, outcome_status, reason)` (frozen) — `rook.agent.plan_graph_live`. `EXECUTION_PARAMS_KEY = "execution_params"` is also here.
- `VerifierStepResult(graph, applied, verifier_node_id, source_node_id, outcome_status, reason)` (frozen) and `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult` — `rook.learning.plan_graph_runner`. Also `apply_producer_result(graph, node_id, raw) -> .graph/.outcome_status` (used in TESTS only).
- `MemoryParamApplyResult(graph, applied, node_id, binding, reason)` (frozen) and `apply_memory_bound_params(graph, node_id, base_params, bindings) -> MemoryParamApplyResult` — `rook.agent.plan_graph_param_apply`. `applied=False` with `reason="binding_failed"` when a binding path is missing.
- `propose_next_node(graph) -> NodeSelectionProposal(decision, selected_node_id, candidate_node_ids, ready_count, reason, selector_id)` — `rook.learning.plan_graph_selector` (used in TESTS to build real proposals / mappings).
- `RevalidationResult(decision, accepted_node_id, reject_reason, reason, proposal, fresh_proposal, expected_selector_ids)` — `rook.learning.plan_graph_revalidation` (used in TESTS to hand-build `StepMappingResult`s).
- `PlanGraph`, `PlanGraphNode`, `initialize_graph` — `rook.learning.plan_graph`. `PlanGraphNode(id, intent, status=...)` (status defaults `"pending"`). `initialize_graph` promotes root `pending → ready`.
- `select_template(descriptor) -> .selected_template_id/.graph` — `rook.learning.plan_graph_templates`. `gh_csharp_create_verify_repair_verify` nodes: `create_script` (`execution_ref="gh_create_csharp_script:v1"`), `verify_create`, `repair_same_component`, `verify_repair`, `done`.

---

### Task 1: Step-executor module + pure unit tests (TDD — tests first)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_step_executor.py`
- Create: `mcp_server/src/rook/agent/plan_graph_step_executor.py`

**Interfaces:**
- Consumes: `StepMappingResult` (LM4P), `ProducerStep`/`VerifierStep`/`BindStep` (LM4M), `SupportsLiveProducerNode`/`LiveProducerResult` (LM4A/G), `VerifierStepResult`/`apply_verifier_step` (learning), `MemoryParamApplyResult`/`apply_memory_bound_params` (LM4L), `PlanGraph`/`PlanGraphNode`.
- Produces: `StepExecutionFailure`, `StepExecutionResult(ran, kind, graph, failure, reason, mapping, producer_result=None, verifier_result=None, bind_result=None)`, `async execute_mapped_step(mapping, graph, runner=None) -> StepExecutionResult`. Consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_step_executor.py` with exactly this content:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail (module missing)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_step_executor.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.plan_graph_step_executor'`.

- [ ] **Step 3: Write the step-executor module**

Create `mcp_server/src/rook/agent/plan_graph_step_executor.py` with exactly this content:

```python
"""LM4Q single mapped-step executor (agent layer) -- first bounded execution authority.

execute_mapped_step consumes an LM4P StepMappingResult and, ONLY if the mapping is a green
light, dispatches exactly that one Step to the existing seam for its kind:
- ProducerStep -> runner.run_live_producer_node (the LM4A/G SupportsLiveProducerNode seam),
- VerifierStep -> apply_verifier_step (learning),
- BindStep     -> apply_memory_bound_params (LM4L).
It returns the advanced graph + the NATIVE seam result. It answers only "am I allowed to run
this already-mapped Step?", never "what should I run?".

Containment (load-bearing):
- execute the artifact, never rebuild the ladder: consumes a StepMappingResult; never imports
  or references propose_next_node / revalidate_proposal / map_accepted_proposal_to_step /
  runnable_nodes (AST-guarded).
- one step, no loop, no fold, no run_explicit_sequence (AST-guarded); no terminal apply_outcome.
- raw dispatch-and-report: never computes pass/fail, never reads ProducerStep.expectation /
  VerifierStep.expected_outcome, never imports build_live_producer_record. Once a seam is
  invoked, ran=True even if the seam result is not-applied/failed -- the native result carries
  that truth, LM4Q never reinterprets it.
- distrust the public artifact's shape: a forged mapped-but-not-a-Step value is refused
  (mapping_invalid) via an explicit-tuple isinstance BEFORE any field read -- never crashes,
  never misdispatches. (This is artifact-shape validation, NOT LM4P's target-node validation.)
- no fallback: a refused mapping runs nothing, even when a different, now-correct Step exists.

Failures are ONLY pre-execution refusals: not_mapped / mapping_invalid / runner_required. On
every refusal result.graph is the INPUT graph (unchanged). Pure-of-policy: never mutates the
mapping; verifier/bind never touch the runner. NO base_agent / dispatcher / server / model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode
from rook.agent.plan_graph_param_apply import (
    MemoryParamApplyResult,
    apply_memory_bound_params,
)
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import StepMappingResult
from rook.learning.plan_graph_runner import VerifierStepResult, apply_verifier_step

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


StepExecutionFailure = Literal["not_mapped", "mapping_invalid", "runner_required"]


@dataclass(frozen=True)
class StepExecutionResult:
    ran: bool
    kind: Literal["producer", "verifier", "bind"] | None
    graph: "PlanGraph"
    failure: StepExecutionFailure | None
    reason: str
    mapping: StepMappingResult
    producer_result: LiveProducerResult | None = None
    verifier_result: VerifierStepResult | None = None
    bind_result: MemoryParamApplyResult | None = None


def _refused(
    failure: StepExecutionFailure,
    reason: str,
    graph: "PlanGraph",
    mapping: StepMappingResult,
) -> StepExecutionResult:
    return StepExecutionResult(
        ran=False,
        kind=None,
        graph=graph,
        failure=failure,
        reason=reason,
        mapping=mapping,
    )


async def execute_mapped_step(
    mapping: StepMappingResult,
    graph: "PlanGraph",
    runner: SupportsLiveProducerNode | None = None,
) -> StepExecutionResult:
    """Execute exactly the one Step carried by an accepted ``mapping``.

    Gate -> structural check -> dispatch one Step to its existing seam -> report the native
    result + advanced graph. No selection, no evaluation, no loop, no terminal construction,
    no fallback. On any pre-execution refusal, returns the INPUT ``graph`` unchanged.
    """
    # 1. Gate: the mapping must be a green light.
    if mapping.mapped is not True or mapping.step is None:
        return _refused(
            "not_mapped",
            "mapping is not an accepted, step-carrying result",
            graph,
            mapping,
        )

    step = mapping.step

    # 2. Structural check: distrust the public artifact's shape BEFORE reading any field.
    #    Explicit tuple isinstance -- never the Step union alias at runtime.
    if not isinstance(step, (ProducerStep, VerifierStep, BindStep)):
        return _refused(
            "mapping_invalid",
            "mapping.step is not a ProducerStep/VerifierStep/BindStep",
            graph,
            mapping,
        )

    # 3. Dispatch with explicit per-kind branches (no final else-as-bind).
    if isinstance(step, ProducerStep):
        if runner is None:
            return _refused(
                "runner_required",
                f"ProducerStep {step.node_id!r} needs a runner but none was supplied",
                graph,
                mapping,
            )
        result = await runner.run_live_producer_node(graph, step.node_id)
        return StepExecutionResult(
            ran=True,
            kind="producer",
            graph=result.graph,
            failure=None,
            reason=f"executed producer step {step.node_id!r}",
            mapping=mapping,
            producer_result=result,
        )
    elif isinstance(step, VerifierStep):
        vres = apply_verifier_step(graph, step.verifier_node_id, step.source_node_id)
        return StepExecutionResult(
            ran=True,
            kind="verifier",
            graph=vres.graph,
            failure=None,
            reason=f"executed verifier step {step.verifier_node_id!r}",
            mapping=mapping,
            verifier_result=vres,
        )
    elif isinstance(step, BindStep):
        bres = apply_memory_bound_params(
            graph, step.node_id, step.base_params, step.bindings
        )
        return StepExecutionResult(
            ran=True,
            kind="bind",
            graph=bres.graph,
            failure=None,
            reason=f"executed bind step {step.node_id!r}",
            mapping=mapping,
            bind_result=bres,
        )
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_step_executor.py -v
```
Expected: all 15 tests PASS.

- [ ] **Step 5: Confirm the production change is exactly one module, then commit**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: the numstat lists only `mcp_server/src/rook/agent/plan_graph_step_executor.py`.

Commit:
```
git add mcp_server/src/rook/agent/plan_graph_step_executor.py mcp_server/tests/test_plan_graph_step_executor.py
git commit -m "feat(lm4q): single mapped-step executor + unit tests

execute_mapped_step consumes an LM4P StepMappingResult and, only if mapped, dispatches exactly
that one Step to its existing seam (producer -> run_live_producer_node, verifier ->
apply_verifier_step, bind -> apply_memory_bound_params), returning the advanced graph + native
seam result. Raw dispatch-and-report: no evaluation, no loop, no terminal done, no fallback.
Three pre-execution refusals: not_mapped / mapping_invalid (explicit-tuple isinstance before
any field read) / runner_required. ran=True once delegated even if the seam is not-applied.
15 unit tests incl. delegation-arg pin, runner-not-touched + poison-expectation guards, and
the no-Step-construction + import-boundary AST guards.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Chain execution guard (gate → map → execute one step; stale → nothing runs)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_step_executor_chain.py`

**Interfaces:**
- Consumes: `execute_mapped_step` (Task 1), `map_accepted_proposal_to_step` (LM4P), `ProducerStep`/`VerifierStep` (LM4M), `propose_next_node` (selector), `select_template`, `initialize_graph`, `apply_producer_result`, `apply_verifier_step`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_step_executor_chain.py` with exactly this content:

```python
"""LM4Q chain execution guard -- drive the real 5-node chain through gate -> map -> execute
ONE step, then prove a stale mapping runs NOTHING (no fallback even though step_map holds a
valid entry for the now-correct node).

The reducer drives the graph (apply_producer_result / apply_verifier_step); propose_next_node
selects, map_accepted_proposal_to_step gates+translates, execute_mapped_step runs exactly one
mapped Step. HONEST SCOPE: LM4Q executes ONE step; nothing here loops to the next step, builds
a terminal `done`, or drives graph_status to "complete". In the focused PlanGraph gate. Run
from repo root. Separate file from test_plan_graph_step_executor.py.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
from rook.agent.plan_graph_step_executor import execute_mapped_step
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4q-chain-guid"


def _wrapped_failure_create_raw() -> dict:
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": _GUID},
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
            }
        },
    }


def _chain_step_map():
    return {
        "verify_create": VerifierStep(
            verifier_node_id="verify_create",
            source_node_id="create_script",
            expected_outcome="needs_repair",
        ),
        "repair_same_component": ProducerStep(
            node_id="repair_same_component", expectation=None
        ),
    }


@pytest.mark.asyncio
async def test_execute_one_step_then_stale_mapping_runs_nothing():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # Advance so verify_create is uniquely ready.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph

    proposal = propose_next_node(graph)
    assert proposal.selected_node_id == "verify_create"
    step_map = _chain_step_map()

    # gate -> map -> execute ONE verifier step (no runner needed for the verifier branch).
    mapping = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert mapping.mapped is True
    result = await execute_mapped_step(mapping, graph)
    assert result.ran is True
    assert result.kind == "verifier"
    assert result.verifier_result.applied is True
    assert result.verifier_result.outcome_status == "needs_repair"

    # the executed step advanced the graph: repair_same_component is now uniquely ready.
    advanced = result.graph
    assert propose_next_node(advanced).selected_node_id == "repair_same_component"

    # STALE: re-map the OLD verify_create proposal against the advanced graph -> LM4P refuses;
    # execute_mapped_step runs NOTHING -- no fallback to the now-correct repair step even
    # though step_map HAS a repair_same_component entry.
    stale_mapping = map_accepted_proposal_to_step(proposal, advanced, step_map)
    assert stale_mapping.mapped is False
    assert stale_mapping.revalidation.reject_reason == "selected_not_ready"
    stale_result = await execute_mapped_step(stale_mapping, advanced)
    assert stale_result.ran is False
    assert stale_result.failure == "not_mapped"
    assert stale_result.graph is advanced  # unchanged input graph
    assert stale_result.producer_result is None
    assert stale_result.verifier_result is None
    assert stale_result.bind_result is None
```

- [ ] **Step 2: Run the test and verify it passes**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_step_executor_chain.py -v
```
Expected: `1 passed`. If it fails, capture the exact assertion and report — do not weaken it.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_plan_graph_step_executor_chain.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_plan_graph_step_executor_chain.py
git commit -m "test(lm4q): chain execution guard -- execute one step, stale mapping runs nothing

Drives the real 5-node chain to verify_create uniquely ready, then gate -> map -> execute one
verifier step (advances to repair_same_component ready). Re-mapping the OLD verify_create
proposal against the advanced graph yields a refused mapping; execute_mapped_step runs NOTHING
(not_mapped, graph unchanged) -- no fallback even though step_map holds a repair_same_component
entry. Honest scope: one step only; no loop, no terminal done.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Live producer smoke (`requires_rhino`) — PAUSE before live acceptance

**Files:**
- Create: `mcp_server/tests/test_live_step_executor_producer_live.py`

**Interfaces:**
- Consumes: `execute_mapped_step` (Task 1), `map_accepted_proposal_to_step` (LM4P), `ProducerStep` (LM4M), `propose_next_node`, `select_template`, `initialize_graph`, `EXECUTION_PARAMS_KEY`, `RookAgent`, `_mcp_tool_executor`, `_is_error` (conftest), `fresh_document` fixture.

- [ ] **Step 1: Write the live test file**

Create `mcp_server/tests/test_live_step_executor_producer_live.py` with exactly this content:

```python
"""LM4Q live proof -- execute_mapped_step drives ONE mapped ProducerStep LIVE through a real
RookAgent runner, reaching the real DECLARED create producer (gh_create_csharp_script:v1
resolving live to gh_create_csharp_script -- NO producer override). Narrow: ProducerStep only,
no chain, no verifier/bind live, no expectation evaluation.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when Rhino/GH
unreachable. Run (repo root, Rhino + Grasshopper open with Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_live_step_executor_producer_live.py
Then restore knowledge/gh/operations_knowledge.json (live runs dirty it):
    git restore knowledge/gh/operations_knowledge.json
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_sequence_runner import ProducerStep
from rook.agent.plan_graph_step_executor import execute_mapped_step
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import initialize_graph
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


async def _ensure_gh_document() -> None:
    """Establish an ACTIVE Grasshopper document; skip (never silently ignore) when GH cannot
    provide one. The `_Grasshopper` window open is not sufficient, and fresh_document resets
    only the Rhino document."""
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_execute_mapped_producer_step_reaches_live_declared_create(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # P3 pin: assert the DECLARED ref BEFORE setting execution params (no override-style proof).
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["create_script"].status == "ready"  # initialize_graph promoted the root

    # set the create node's execution params (author-supplied valid C# body; omit 'language' --
    # the csharp alias forces it).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = 42.0;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4QStepExecutorLive",
        "x": 350,
        "y": 880,
    }

    # gate -> map the uniquely-ready create_script to a caller-authored ProducerStep.
    proposal = propose_next_node(graph)
    assert proposal.selected_node_id == "create_script"
    mapping = map_accepted_proposal_to_step(
        proposal, graph, {"create_script": ProducerStep("create_script")}
    )
    assert mapping.mapped is True

    # execute ONE mapped ProducerStep through a real RookAgent runner.
    agent = RookAgent(tool_executor=_mcp_tool_executor)
    result = await execute_mapped_step(mapping, graph, runner=agent)

    assert result.ran is True
    assert result.kind == "producer"
    assert result.producer_result is not None
    assert result.graph is result.producer_result.graph  # advanced graph threaded through
    # P3 pin: the declared :v1 ref resolved live to the real tool (no override).
    assert result.producer_result.tool_name == "gh_create_csharp_script"
```

- [ ] **Step 2: Verify the file is collectible and skips without Rhino (offline)**

The live test must not break the offline suite. Confirm it is collected and (without Rhino) deselected/skipped, not errored:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_live_step_executor_producer_live.py --collect-only -q
```
Expected: collects `test_execute_mapped_producer_step_reaches_live_declared_create` with no import/collection error.

- [ ] **Step 3: Confirm one-module production diff is still intact, then commit the test**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: numstat still lists only `mcp_server/src/rook/agent/plan_graph_step_executor.py` (Task 3 adds no `src/` change). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_live_step_executor_producer_live.py
git commit -m "test(lm4q): live producer smoke -- mapped ProducerStep reaches live declared create

requires_rhino smoke: gate -> map -> execute_mapped_step(runner=RookAgent) drives ONE mapped
ProducerStep live, reaching the DECLARED create ref (gh_create_csharp_script:v1 resolving live
to gh_create_csharp_script, no override). Asserts the declared ref before setting params, then
ran=True / kind==producer / producer_result present / advanced graph / tool_name==
gh_create_csharp_script. Narrow: producer only, no chain, no verifier/bind live, no eval.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: PAUSE — live acceptance (requires Rhino + Grasshopper open)**

**Do not run this step autonomously.** The controller coordinates with the user, who must have Rhino + Grasshopper open with Rook loaded. When given the go-ahead, run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -m requires_rhino mcp_server/tests/test_live_step_executor_producer_live.py -v
```
Expected: `1 passed` (or `1 skipped` if GH has no active document / is unreachable — investigate, do not weaken). Then **restore the dirtied knowledge file**:
```
git restore knowledge/gh/operations_knowledge.json
git status --short
```
Expected after restore: no `operations_knowledge.json` change; tree clean except committed work.

---

## Final verification (whole-branch)

- [ ] **Focused gate green:** PowerShell does not expand the glob; enumerate explicitly:
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_step_executor.py` (15) and `test_plan_graph_step_executor_chain.py` (1) — the gate rises from the LM4P baseline of 330 by 16 to **346**. (The live test is outside this glob and not counted.) If the total differs, it must be explained by the added test count, not a regression.

- [ ] **Production change is exactly one module:**
```
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: a single line for `mcp_server/src/rook/agent/plan_graph_step_executor.py` and nothing else.

- [ ] **`base_agent.py` byte-stable:**
```
git diff --numstat main...HEAD -- mcp_server/src/rook/agent/base_agent.py
```
Expected: empty (no output).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly six paths — the spec, this plan, the step-executor module, the two automated test files, and the live test file. No `operations_knowledge.json`.

## Self-Review

**Spec coverage:**
- `StepExecutionResult` shape + `execute_mapped_step` + 3 failure reasons + async → Task 1 module.
- Gate (`not_mapped`) → Task 1 `test_not_mapped_when_mapping_not_accepted` / `_step_is_none`.
- Structural check `mapping_invalid` before field read, no crash → Task 1 `test_mapping_invalid_for_non_step_value` + module step 2.
- Explicit per-kind branches, no else-as-bind → module step 3.
- `runner_required` (producer, no runner) → Task 1 `test_runner_required_for_producer_without_runner`.
- Raw dispatch-and-report; `ran=True` even on not-applied seam → Task 1 `test_verifier_seam_not_applied_still_ran` / `test_bind_seam_not_applied_still_ran`.
- Never read expectation fields → Task 1 `test_poison_expectation_never_read`.
- Runner untouched on verifier/bind → Task 1 `test_runner_not_touched_for_verifier_and_bind`.
- Delegation-arg pin (original graph object + node id) → Task 1 `test_mapped_producer_step_delegates_exact_graph_and_node`.
- Mapping carried always; pure inputs → Task 1 `test_mapping_carried_in_every_result` / `test_pure_inputs_unchanged`.
- No Step construction; import boundary (consume-not-rebuild, no select/terminal/eval) → Task 1 `test_module_does_not_construct_steps` / `test_import_boundary`.
- Chain gate→map→execute one step; stale → nothing runs, no fallback → Task 2.
- Live declared-ref producer smoke (ref pin before params, tool_name after) → Task 3.
- One-module production diff, `base_agent.py` byte-stable, op-knowledge restore → Global Constraints + Final verification + Task 3 Step 4.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `execute_mapped_step(mapping, graph, runner=None) -> StepExecutionResult(.ran, .kind, .graph, .failure, .reason, .mapping, .producer_result, .verifier_result, .bind_result)`; `StepExecutionFailure` 3-member literal; consumes `StepMappingResult(.mapped, .step, .accepted_node_id, .revalidation)`, `LiveProducerResult(.graph, .applied, .node_id, .tool_name, .outcome_status, .reason)`, `VerifierStepResult(.graph, .applied, .outcome_status, …)`, `MemoryParamApplyResult(.graph, .applied, …)`; `ProducerStep(node_id, expectation=None)` / `VerifierStep(verifier_node_id, source_node_id, expected_outcome=None)` / `BindStep(node_id, base_params, bindings)`; `apply_verifier_step(graph, verifier_node_id, source_node_id)`, `apply_memory_bound_params(graph, node_id, base_params, bindings)`, `runner.run_live_producer_node(graph, node_id)`; test helpers build `NodeSelectionProposal`/`RevalidationResult`/`StepMappingResult` with the exact merged signatures. Consistent across all three tasks and matching merged modules.
```
