# LM4M — Explicit Live Mixed-Step Sequence Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agent-layer `run_explicit_sequence` that left-folds a caller-authored ordered list of typed steps (`ProducerStep`/`VerifierStep`/`BindStep`) over a `PlanGraph` — calling LM4L's `apply_memory_bound_params` as the bind step — and prove (offline + live) it drives the repair chain to the brink of `complete` without choosing the path.

**Architecture:** One new agent-layer module `agent/plan_graph_sequence_runner.py`. The live, mixed-step sibling of LM3A's pure `plan_graph_walker.py`: each step kind delegates to an existing seam (live producer via the LM4G `SupportsLiveProducerNode` Protocol, pure `apply_verifier_step`, LM4L `apply_memory_bound_params`). Stop-on-first-failure, no node selection, no terminal construction. Three test deliverables: unit tests (`_FakeRunner`), an offline chain guard, and a `requires_rhino` live proof.

**Tech Stack:** Python 3.12, pytest (+ `pytest-asyncio`, `requires_rhino`), Rook `learning`/`agent` packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

From the spec (`docs/superpowers/specs/2026-06-24-lm4m-explicit-sequence-runner-design.md`).

- **`run_explicit_sequence` is agent-layer.** Imports: `apply_memory_bound_params` + `MemoryParamApplyResult` (LM4L `plan_graph_param_apply`); `build_live_producer_record` + `LiveProducerExpectation` + `LiveProducerRecord` + `SupportsLiveProducerNode` (LM4G `plan_graph_live_runner`); `apply_verifier_step` + `VerifierStepResult` (learning `plan_graph_runner`); `OutcomeStatus` + `PlanGraph` (learning `plan_graph`, `PlanGraph` `TYPE_CHECKING`-quoted); stdlib `dataclass`/`typing`/`collections.abc`.
- **AST guard bans:** `runnable_nodes` (no selection), `apply_outcome` (no terminal construction), `rook.agent.base_agent`, `rook.server`, any `dispatch` module. The runner arrives only as a structural Protocol.
- **`completed` means SEQUENCE-completed, NOT `graph_status == "complete"`.** The terminal `done` marker stays outside the runner; tests assert `completed` and `done` readiness separately, then apply the terminal.
- **Stop-on-first-failure.** Thread `graph = <step>.graph` always; on the first `ok is False`, return immediately with `stopped_at=index`, executed `step_results` (incl. the failing one), and `remaining_steps = steps[index+1:]`. No rollback. On a producer that **applies but fails its expectation**, `SequenceResult.graph` is the **advanced** graph.
- **No-expectation producer:** `ok = result.applied` means "step applied", not "artifact good". LM4M's own chains always pass a `LiveProducerExpectation` on producer steps.
- **`VerifierStep.expected_outcome` is `OutcomeStatus | None`** (compared against `VerifierStepResult.outcome_status`).
- **Production change is EXACTLY one new module:** `mcp_server/src/rook/agent/plan_graph_sequence_runner.py`. No edits to any existing `src/` file; `base_agent.py` byte-stable; LM4G/LM4L modules and the walker untouched. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- **No producer ref overrides in the live proof; create params omit `language`;** keep `_ensure_gh_document`; restore `knowledge/gh/operations_knowledge.json` after live runs.
- **Whole-branch diff = spec + plan + 1 module + 3 test files.**

## Seam reference (already merged — consume, do not modify)

- `PlanGraph`, `PlanGraphNode`, `GraphMemory`, `NodeOutcome`, `OutcomeStatus`, `apply_outcome`, `graph_status`, `initialize_graph` — `rook.learning.plan_graph`.
- `apply_producer_result(graph, node_id, raw) -> ProducerStepResult` (`.graph`, `.applied`, `.node_id`, `.outcome_status`, `.reason`); `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult` (`.graph`, `.applied`, `.verifier_node_id`, `.source_node_id`, `.outcome_status`, `.reason`) — `rook.learning.plan_graph_runner`.
- `select_template(descriptor) -> .selected_template_id/.graph` — `rook.learning.plan_graph_templates`.
- `LiveProducerResult(graph, applied, node_id, tool_name, outcome_status, reason)` — `rook.agent.plan_graph_live`.
- `RookAgent(tool_executor=…).run_live_producer_node(graph, node_id) -> LiveProducerResult` — `rook.agent.base_agent`.
- `build_live_producer_record(result, expectation) -> LiveProducerRecord` (`.passed`, `.tool_status`, `.mismatches`, `.evaluated`); `LiveProducerExpectation(applied, outcome_status, node_status, tool_status, verified, artifact_status, reason)`; `SupportsLiveProducerNode` Protocol — `rook.agent.plan_graph_live_runner`.
- `apply_memory_bound_params(graph, node_id, base_params, bindings) -> MemoryParamApplyResult` (`.graph`, `.applied`, `.node_id`, `.binding`, `.reason`) — `rook.agent.plan_graph_param_apply`.
- `EXECUTION_PARAMS_KEY` — `rook.agent.plan_graph_live`. `_mcp_tool_executor` — `rook.server`. `fresh_document` + `_is_error` — `mcp_server/tests/conftest.py`.

---

### Task 1: Sequence runner module + unit tests (TDD — tests first)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_sequence_runner.py`
- Create: `mcp_server/src/rook/agent/plan_graph_sequence_runner.py`

**Interfaces:**
- Consumes: LM4L `apply_memory_bound_params`/`MemoryParamApplyResult`, LM4G `build_live_producer_record`/`LiveProducerExpectation`/`LiveProducerRecord`/`SupportsLiveProducerNode`, learning `apply_verifier_step`/`VerifierStepResult`/`OutcomeStatus`/`apply_producer_result`/`select_template`/`initialize_graph`, `LiveProducerResult`.
- Produces: `ProducerStep`, `VerifierStep`, `BindStep`, `Step`, `StepOutcome`, `SequenceResult`, `run_explicit_sequence(runner, graph, steps)`. Consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_sequence_runner.py` with exactly this content:

```python
"""LM4M unit tests for run_explicit_sequence -- the agent-layer runner that left-folds a
caller-authored ordered list of typed steps over a PlanGraph, stopping on first failure.

A _FakeRunner implements SupportsLiveProducerNode by applying a pre-seeded raw-result
dict through the REAL apply_producer_result (offline, deterministic, faithful to the live
projection). In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_runner import LiveProducerExpectation
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    VerifierStep,
    run_explicit_sequence,
)
from rook.learning.plan_graph import graph_status, initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_templates import select_template


pytestmark = pytest.mark.asyncio

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4m-seq-guid"
_BASE_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}

_CREATE_EXPECT = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    tool_status="failed",
    verified=False,
    artifact_status="created_with_errors",
)
_REPAIR_EXPECT = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    verified=True,
    artifact_status="usable",
)


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


def _unwrapped_success_repair_raw() -> dict:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "written", "component_guid": _GUID},
            "verification": {"status": "passed", "target_error_count": 0},
            "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
        }
    }


class _FakeRunner:
    """Offline SupportsLiveProducerNode: applies a pre-seeded raw-result dict (keyed by
    node_id) through the REAL apply_producer_result and wraps it as a LiveProducerResult.
    Deterministic + faithful: evidence/status come from the real reducer/projection path,
    so build_live_producer_record evaluates expectations exactly as live."""

    def __init__(self, raws: dict[str, dict]) -> None:
        self._raws = raws

    async def run_live_producer_node(self, graph, node_id):
        inner = apply_producer_result(graph, node_id, self._raws[node_id])
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name="fake_producer",
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


def _ready_template_graph():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)
    assert graph.nodes["create_script"].status == "ready"
    return graph


async def test_happy_three_step_sequence():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        BindStep(
            "repair_same_component",
            _BASE_REPAIR_PARAMS,
            {"guid": ("repair_anchor", "component_guid")},
        ),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is True
    assert result.stopped_at is None
    assert result.remaining_steps == ()
    assert [s.kind for s in result.step_results] == ["producer", "verifier", "bind"]
    assert all(s.ok for s in result.step_results)
    # the bind step staged the memory-sourced guid onto the repair node.
    bind_outcome = result.step_results[2]
    assert bind_outcome.bind_result.binding.params["guid"] == _GUID
    assert (
        result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == _GUID
    )


async def test_stop_at_verifier_mismatch():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        # create actually unlocks needs_repair; demand the wrong outcome -> mismatch.
        VerifierStep("verify_create", "create_script", expected_outcome="succeeded"),
        BindStep("repair_same_component", _BASE_REPAIR_PARAMS, {"guid": ("repair_anchor", "component_guid")}),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 1
    assert [s.kind for s in result.step_results] == ["producer", "verifier"]
    assert result.step_results[1].ok is False
    assert result.step_results[1].verifier_result.outcome_status == "needs_repair"
    # the bind step (index 2) never ran -> repair node has no execution_params.
    assert len(result.remaining_steps) == 1
    assert EXECUTION_PARAMS_KEY not in result.graph.nodes["repair_same_component"].metadata


async def test_stop_at_bind_missing_fact():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        # path points at an absent memory fact -> binding_failed.
        BindStep("repair_same_component", _BASE_REPAIR_PARAMS, {"guid": ("absent_key",)}),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 2
    bind_outcome = result.step_results[2]
    assert bind_outcome.ok is False
    assert bind_outcome.bind_result.reason == "binding_failed"
    assert EXECUTION_PARAMS_KEY not in result.graph.nodes["repair_same_component"].metadata


async def test_stop_at_producer_applied_but_expectation_fails():
    graph = _ready_template_graph()
    before = graph.nodes["create_script"].status
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    # create APPLIES (created_with_errors) but the expectation demands usable -> fail.
    bad_expect = LiveProducerExpectation(
        applied=True, node_status="succeeded", artifact_status="usable"
    )
    steps = [ProducerStep("create_script", expectation=bad_expect)]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 0
    assert result.step_results[0].ok is False
    # graph is the producer's ADVANCED graph, not the pre-step graph: a failed
    # expectation can still mean the graph mutated/advanced.
    assert before == "ready"
    assert result.graph is not graph  # a NEW graph (the dispatch advanced it)
    assert result.graph.nodes["create_script"].status == "succeeded"


async def test_producer_not_applied_graph_unchanged():
    # create_script is PENDING (no initialize_graph) -> apply_producer_result not-applied.
    selection = select_template(_DESCRIPTOR)
    graph = selection.graph
    assert graph.nodes["create_script"].status == "pending"
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [ProducerStep("create_script")]  # no expectation -> ok = applied
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 0
    assert result.step_results[0].ok is False
    assert result.graph.nodes["create_script"].status == "pending"  # unchanged


async def test_order_preserved_no_reorder():
    # A verifier placed BEFORE its source is ready not-applies and halts: the runner runs
    # the list in author order and never reorders to satisfy dependencies.
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is False
    assert result.stopped_at == 0
    assert result.step_results[0].kind == "verifier"
    assert result.step_results[0].ok is False
    assert result.step_results[0].verifier_result.applied is False
    # the producer step (index 1) never ran.
    assert len(result.remaining_steps) == 1
    assert result.graph.nodes["create_script"].status == "ready"


async def test_completed_is_not_graph_complete():
    graph = _ready_template_graph()
    runner = _FakeRunner({"create_script": _wrapped_failure_create_raw()})
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is True  # sequence-completed
    assert graph_status(result.graph) != "complete"  # but graph is NOT complete
    assert result.graph.nodes["repair_same_component"].status == "ready"


async def test_empty_sequence():
    graph = _ready_template_graph()
    runner = _FakeRunner({})
    result = await run_explicit_sequence(runner, graph, [])
    assert result.completed is True
    assert result.stopped_at is None
    assert result.step_results == ()
    assert result.remaining_steps == ()
    assert result.graph is graph  # runner never copies on its own


def test_sequence_runner_import_boundary():
    # The module folds existing seams; it must NOT import a selector (runnable_nodes), a
    # terminal builder (apply_outcome), the dispatcher, server, or base_agent.
    import rook.agent.plan_graph_sequence_runner as mod

    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            referenced.update((a.asname or a.name) for a in node.names)
    assert "rook.agent.base_agent" not in imported, imported
    assert not any(m.startswith("rook.server") for m in imported), imported
    assert not any("dispatch" in m for m in imported), imported
    assert "runnable_nodes" not in referenced, referenced
    assert "apply_outcome" not in referenced, referenced
```

- [ ] **Step 2: Run the tests to verify they fail (module missing)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_sequence_runner.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.plan_graph_sequence_runner'`.

- [ ] **Step 3: Write the sequence runner module**

Create `mcp_server/src/rook/agent/plan_graph_sequence_runner.py` with exactly this content:

```python
"""LM4M explicit live mixed-step sequence runner (agent layer).

run_explicit_sequence left-folds a CALLER-AUTHORED ordered list of typed steps
(ProducerStep / VerifierStep / BindStep) over a PlanGraph, threading the graph and
stopping at the first failed/not-applied step. Each step kind delegates to an existing
seam: live producer (run_live_producer_node via the LM4G SupportsLiveProducerNode
Protocol), pure apply_verifier_step (learning), LM4L apply_memory_bound_params (agent).

The LIVE, agent-layer, mixed-step sibling of LM3A's pure plan_graph_walker.py (which
replays one (node_id, raw_result) kind via apply_tool_result). Like the walker, this is
NOT a scheduler: it never selects a node, branches, loops, inspects topology to choose,
or constructs terminal outcomes. The caller dictates the exact sequence; the terminal
`done` marker stays OUTSIDE this runner. ``completed`` means SEQUENCE-completed (all
supplied steps ran and passed), NOT graph_status == "complete".

Boundary: agent -> {agent LM4G/LM4L, learning}, one way. NO runnable_nodes import (the
clean no-selection proof), NO apply_outcome import (no terminal construction), NO
base_agent/server/dispatcher import (the runner arrives only as a structural Protocol).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    LiveProducerRecord,
    SupportsLiveProducerNode,
    build_live_producer_record,
)
from rook.agent.plan_graph_param_apply import (
    MemoryParamApplyResult,
    apply_memory_bound_params,
)
from rook.learning.plan_graph import OutcomeStatus
from rook.learning.plan_graph_runner import VerifierStepResult, apply_verifier_step

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


@dataclass(frozen=True)
class ProducerStep:
    node_id: str
    expectation: LiveProducerExpectation | None = None


@dataclass(frozen=True)
class VerifierStep:
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None = None


@dataclass(frozen=True)
class BindStep:
    node_id: str
    base_params: Mapping
    bindings: Mapping[str, tuple[str, ...]]


Step = ProducerStep | VerifierStep | BindStep


@dataclass(frozen=True)
class StepOutcome:
    kind: Literal["producer", "verifier", "bind"]
    label: str
    ok: bool
    producer_record: LiveProducerRecord | None = None
    verifier_result: VerifierStepResult | None = None
    bind_result: MemoryParamApplyResult | None = None


@dataclass(frozen=True)
class SequenceResult:
    graph: "PlanGraph"
    completed: bool
    stopped_at: int | None
    step_results: tuple[StepOutcome, ...]
    remaining_steps: tuple[Step, ...]


async def run_explicit_sequence(
    runner: SupportsLiveProducerNode,
    graph: "PlanGraph",
    steps: "Sequence[Step]",
) -> SequenceResult:
    """Left-fold an explicit, caller-authored step list over ``graph``.

    Threads the graph through each step (every delegated seam returns a graph: advanced
    on apply, input-unchanged on not-applied), stopping at the first step whose ``ok`` is
    False. ``completed`` means SEQUENCE-completed (all supplied steps ran and passed), NOT
    ``graph_status == "complete"`` -- the terminal ``done`` marker stays outside this
    runner. No node selection, no branching/looping beyond the linear fold + early stop,
    no rollback. A producer step that applies but fails its expectation still advances the
    graph (the returned graph reflects the dispatch).
    """
    executed: list[StepOutcome] = []

    for index, step in enumerate(steps):
        if isinstance(step, ProducerStep):
            result = await runner.run_live_producer_node(graph, step.node_id)
            graph = result.graph
            record = build_live_producer_record(result, step.expectation)
            ok = (
                record.passed is True
                if step.expectation is not None
                else result.applied is True
            )
            executed.append(
                StepOutcome(
                    kind="producer",
                    label=step.node_id,
                    ok=ok,
                    producer_record=record,
                )
            )
        elif isinstance(step, VerifierStep):
            vres = apply_verifier_step(
                graph, step.verifier_node_id, step.source_node_id
            )
            graph = vres.graph
            ok = vres.applied and (
                step.expected_outcome is None
                or vres.outcome_status == step.expected_outcome
            )
            executed.append(
                StepOutcome(
                    kind="verifier",
                    label=step.verifier_node_id,
                    ok=ok,
                    verifier_result=vres,
                )
            )
        else:  # BindStep -- the closed taxonomy's third and final kind
            bres = apply_memory_bound_params(
                graph, step.node_id, step.base_params, step.bindings
            )
            graph = bres.graph
            ok = bres.applied
            executed.append(
                StepOutcome(
                    kind="bind",
                    label=step.node_id,
                    ok=ok,
                    bind_result=bres,
                )
            )

        if not ok:
            return SequenceResult(
                graph=graph,
                completed=False,
                stopped_at=index,
                step_results=tuple(executed),
                remaining_steps=tuple(steps[index + 1 :]),
            )

    return SequenceResult(
        graph=graph,
        completed=True,
        stopped_at=None,
        step_results=tuple(executed),
        remaining_steps=(),
    )
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_sequence_runner.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 5: Confirm the production change is exactly one module, then commit**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected status: `?? mcp_server/src/rook/agent/plan_graph_sequence_runner.py` + `?? mcp_server/tests/test_plan_graph_sequence_runner.py` (+ spec/plan if uncommitted). `operations_knowledge.json` NOT listed.

Commit:
```
git add mcp_server/src/rook/agent/plan_graph_sequence_runner.py mcp_server/tests/test_plan_graph_sequence_runner.py
git commit -m "feat(lm4m): explicit live mixed-step sequence runner + unit tests

run_explicit_sequence left-folds a caller-authored ordered list of typed steps
(ProducerStep/VerifierStep/BindStep) over a PlanGraph, calling LM4L
apply_memory_bound_params as the bind step. Stop-on-first-failure, threads graph =
<step>.graph, completed == sequence-completed (NOT graph complete). No node selection
(no runnable_nodes import), no terminal (no apply_outcome), runner via Protocol
(base_agent untouched). 9 unit tests w/ an offline _FakeRunner (real apply_producer_result)
incl. advanced-graph-on-producer-mismatch + order-preserved + AST import-boundary guard.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Offline chain guard (full 5-step sequence to the brink of complete)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_sequence_runner_chain.py`

**Interfaces:**
- Consumes: `run_explicit_sequence`/`ProducerStep`/`VerifierStep`/`BindStep` (Task 1), the `_FakeRunner` pattern + raw-envelope helpers, `apply_outcome`/`graph_status`/`NodeOutcome`/`initialize_graph`, `select_template`, `EXECUTION_PARAMS_KEY`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_sequence_runner_chain.py` with exactly this content:

```python
"""LM4M offline chain guard -- run_explicit_sequence drives the full 5-step sequence
(create -> verify_create -> bind -> repair -> verify_repair) with an offline _FakeRunner,
then the TEST applies the terminal `done` marker to reach graph_status == "complete".

HONEST SCOPE: producer steps are faked via apply_producer_result (raw-dict projection),
so this proves SEQUENCING + applier-mid-sequence + composition to the brink of complete,
NOT live dispatch. Live dispatch is the requires_rhino proof
(test_live_sequence_runner_chain_live.py). In the focused PlanGraph gate. Run from repo
root. Separate file from test_plan_graph_sequence_runner.py.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_runner import LiveProducerExpectation
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    VerifierStep,
    run_explicit_sequence,
)
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_templates import select_template


pytestmark = pytest.mark.asyncio

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4m-chain-guid"
_BASE_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}

_CREATE_EXPECT = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    tool_status="failed",
    verified=False,
    artifact_status="created_with_errors",
)
_REPAIR_EXPECT = LiveProducerExpectation(
    applied=True,
    outcome_status="succeeded",
    node_status="succeeded",
    verified=True,
    artifact_status="usable",
)


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


def _unwrapped_success_repair_raw() -> dict:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "written", "component_guid": _GUID},
            "verification": {"status": "passed", "target_error_count": 0},
            "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
        }
    }


class _FakeRunner:
    def __init__(self, raws: dict[str, dict]) -> None:
        self._raws = raws

    async def run_live_producer_node(self, graph, node_id):
        inner = apply_producer_result(graph, node_id, self._raws[node_id])
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name="fake_producer",
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


async def test_sequence_runner_drives_full_chain_then_terminal_to_complete():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    runner = _FakeRunner(
        {
            "create_script": _wrapped_failure_create_raw(),
            "repair_same_component": _unwrapped_success_repair_raw(),
        }
    )
    steps = [
        ProducerStep("create_script", expectation=_CREATE_EXPECT),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        BindStep(
            "repair_same_component",
            _BASE_REPAIR_PARAMS,
            {"guid": ("repair_anchor", "component_guid")},
        ),
        ProducerStep("repair_same_component", expectation=_REPAIR_EXPECT),
        VerifierStep("verify_repair", "repair_same_component", expected_outcome="succeeded"),
    ]
    result = await run_explicit_sequence(runner, graph, steps)
    assert result.completed is True
    assert result.stopped_at is None
    assert [s.kind for s in result.step_results] == [
        "producer", "verifier", "bind", "producer", "verifier",
    ]
    assert all(s.ok for s in result.step_results)
    # the bind step staged the memory-sourced guid mid-sequence.
    assert result.step_results[2].bind_result.binding.params["guid"] == _GUID
    assert (
        result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == _GUID
    )

    # SEQUENCE-completed but graph not complete: done is ready, the test applies terminal.
    graph = result.graph
    assert graph.nodes["done"].status == "ready"
    assert graph_status(graph) != "complete"
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Run the test and verify it passes**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_sequence_runner_chain.py -v
```
Expected: `1 passed`. If it fails, capture the exact assertion and report — do not weaken it.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_plan_graph_sequence_runner_chain.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_plan_graph_sequence_runner_chain.py
git commit -m "test(lm4m): offline chain guard -- 5-step sequence to the brink of complete

run_explicit_sequence drives create->verify->bind->repair->verify with an offline
_FakeRunner (real apply_producer_result); completed True + done ready, then the test
applies the terminal apply_outcome(done) -> graph_status==complete. Honest scope:
producer steps faked via raw projection -> proves sequencing + applier-mid-sequence +
composition, NOT live dispatch.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Live proof (requires_rhino — the runner drives the live chain via the applier)

**Files:**
- Create: `mcp_server/tests/test_live_sequence_runner_chain_live.py`

**Interfaces:**
- Consumes: `run_explicit_sequence`/`ProducerStep`/`VerifierStep`/`BindStep` (Task 1), `RookAgent`, `_mcp_tool_executor`, `EXECUTION_PARAMS_KEY`, `select_template`, `apply_outcome`/`graph_status`/`NodeOutcome`, `LiveProducerExpectation`, `_is_error`, `fresh_document`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_live_sequence_runner_chain_live.py` with exactly this content:

```python
"""LM4M live proof -- run_explicit_sequence drives the declared-ref repair chain LIVE with
a real RookAgent runner, calling LM4L apply_memory_bound_params as the BindStep mid-
sequence. The runner threads create -> verify_create -> bind -> repair -> verify_repair;
the test asserts the sequence completed and `done` is ready, then applies the terminal
marker to reach graph_status == "complete".

create.evidence.repair_anchor.component_guid is a CONTROL: the bind StepOutcome's
memory-sourced guid must equal it. No producer ref overrides (declared
gh_create_csharp_script:v1 / gh_update_script:v1).

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_sequence_runner_chain_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import LiveProducerExpectation
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    VerifierStep,
    run_explicit_sequence,
)
from rook.learning.plan_graph import NodeOutcome, apply_outcome, graph_status
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
    """Establish an ACTIVE Grasshopper document; skip (never silently ignore) when GH
    cannot provide one. The `_Grasshopper` window open is not sufficient, and
    fresh_document resets only the Rhino document."""
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_sequence_runner_drives_live_repair_chain(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # No ref override; set ONLY create execution_params directly (author-supplied, not
    # memory-sourced; omit 'language' -- the csharp alias forces it).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4MSequenceRunnerLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)

    create_expect = LiveProducerExpectation(
        applied=True,
        outcome_status="succeeded",
        node_status="succeeded",
        tool_status="failed",
        verified=False,
        artifact_status="created_with_errors",
    )
    repair_expect = LiveProducerExpectation(
        applied=True,
        outcome_status="succeeded",
        node_status="succeeded",
        verified=True,
        artifact_status="usable",
    )
    steps = [
        ProducerStep("create_script", expectation=create_expect),
        VerifierStep("verify_create", "create_script", expected_outcome="needs_repair"),
        BindStep(
            "repair_same_component",
            {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
            {"guid": ("repair_anchor", "component_guid")},
        ),
        ProducerStep("repair_same_component", expectation=repair_expect),
        VerifierStep("verify_repair", "repair_same_component", expected_outcome="succeeded"),
    ]

    result = await run_explicit_sequence(agent, graph, steps)
    assert result.completed is True, (
        f"stopped_at={result.stopped_at} "
        f"results={[(s.kind, s.ok) for s in result.step_results]}"
    )
    assert result.stopped_at is None
    assert [s.kind for s in result.step_results] == [
        "producer", "verifier", "bind", "producer", "verifier",
    ]

    # the create producer step dispatched the DECLARED ref live (no override).
    assert result.step_results[0].producer_record.tool_name == "gh_create_csharp_script"

    # CONTROL: the bind step's memory-sourced guid equals the create evidence guid.
    create_record = result.step_results[0].producer_record
    repair_guid_control = create_record.repair_anchor_guid
    assert isinstance(repair_guid_control, str) and repair_guid_control
    bind_outcome = result.step_results[2]
    assert bind_outcome.bind_result.binding.params["guid"] == repair_guid_control

    # the repair producer step dispatched gh_update_script; unwrapped success -> None.
    repair_record = result.step_results[3].producer_record
    assert repair_record.tool_name == "gh_update_script"
    assert repair_record.tool_status is None  # unwrapped success (LM4I/J finding)

    # SEQUENCE-completed but graph not complete: done is ready, then apply terminal.
    graph = result.graph
    assert graph.nodes["done"].status == "ready"
    assert graph_status(graph) != "complete"
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Verify collection + import (Rhino-independent)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_live_sequence_runner_chain_live.py --collect-only -q
```
Expected: collects `test_sequence_runner_drives_live_repair_chain` with no import errors.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_live_sequence_runner_chain_live.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_live_sequence_runner_chain_live.py
git commit -m "test(lm4m): live proof -- run_explicit_sequence drives the live repair chain via the applier

Declared-ref chain (no overrides) driven by run_explicit_sequence with a real RookAgent
runner over the 5-step list; the BindStep calls LM4L apply_memory_bound_params mid-
sequence (memory-sourced guid == create evidence control). completed True + done ready,
then the test applies the terminal marker -> graph_status==complete. repair producer
tool_status is None (unwrapped-success finding).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Live acceptance (run only with Rhino + Grasshopper open)** — PAUSE POINT

Authoritative live proof, run during a live acceptance pass. Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server/tests/test_live_sequence_runner_chain_live.py -v
```
Expected: `1 passed`. Creates a `LM4MSequenceRunnerLive` C# component via the declared ref, drives create→verify→bind→repair→verify through `run_explicit_sequence`, then the test applies the terminal marker to reach `complete`. Mutates `knowledge/gh/operations_knowledge.json`.

**If it fails:** capture the exact assertion + `result.stopped_at` + `[(s.kind, s.ok) for s in result.step_results]` + the failing step's record/result and report; do NOT weaken the test.

After the live run, restore the runtime mutation:
```
git restore knowledge/gh/operations_knowledge.json
git status --short
```
Expected after restore: clean (or only intended files).

---

## Final verification (whole-branch)

- [ ] **Focused gate green (Rhino-independent):** PowerShell does not expand the glob; enumerate explicitly:
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_sequence_runner.py` (9) and `test_plan_graph_sequence_runner_chain.py` (1) — gate rises from the LM4L baseline of 280 by 10 to 290.

- [ ] **Production change is exactly one module:**
```
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: a single line for `mcp_server/src/rook/agent/plan_graph_sequence_runner.py` and nothing else.

- [ ] **`base_agent.py` byte-stable:**
```
git diff --numstat main...HEAD -- mcp_server/src/rook/agent/base_agent.py
```
Expected: empty (no output).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly six paths — the spec, this plan, the runner module, and the three test files. No `operations_knowledge.json`.

## Self-Review

**Spec coverage:**
- Step taxonomy (`ProducerStep`/`VerifierStep`/`BindStep`, `Step`), `StepOutcome`, `SequenceResult`, `run_explicit_sequence` → Task 1 module.
- Left-fold + per-kind `ok` + thread-graph-always + stop-on-first-failure + no rollback → Task 1 module + tests (happy, stop-at-verifier/bind/producer).
- `completed` ≠ graph complete → Task 1 `test_completed_is_not_graph_complete` + Task 2 (terminal applied by the test).
- Advanced-graph-on-producer-mismatch (P3) → Task 1 `test_stop_at_producer_applied_but_expectation_fails`; not-applied producer → `test_producer_not_applied_graph_unchanged`.
- No-selection (no reorder) → Task 1 `test_order_preserved_no_reorder`; empty sequence → `test_empty_sequence`.
- AST import-boundary (no `runnable_nodes`/`apply_outcome`/`base_agent`/server/dispatcher) → Task 1 `test_sequence_runner_import_boundary`.
- `VerifierStep.expected_outcome: OutcomeStatus | None` → Task 1 module signature.
- Live proof: runner drives the live chain via the applier, `done` ready then terminal, `tool_status is None`, control guid → Task 3.
- One-module production diff, `base_agent.py` byte-stable, restore `operations_knowledge.json` → Global Constraints + Final verification + Task 3.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `run_explicit_sequence(runner, graph, steps) -> SequenceResult(.graph, .completed, .stopped_at, .step_results, .remaining_steps)`; `StepOutcome(.kind, .label, .ok, .producer_record, .verifier_result, .bind_result)`; `ProducerStep(node_id, expectation)`, `VerifierStep(verifier_node_id, source_node_id, expected_outcome)`, `BindStep(node_id, base_params, bindings)`; `LiveProducerResult(graph, applied, node_id, tool_name, outcome_status, reason)`; `build_live_producer_record(result, expectation).passed/.tool_status/.tool_name/.repair_anchor_guid`; `apply_verifier_step(...).applied/.outcome_status/.graph`; `apply_memory_bound_params(...).applied/.binding/.reason/.graph`. Consistent across all tasks and matching merged modules.
```

*Note:* `LiveProducerRecord` exposes `tool_name` and `repair_anchor_guid` (LM4G fields used by Task 3's control assertions); confirmed present in `plan_graph_live_runner.LiveProducerRecord`.
