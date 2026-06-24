# LM4M — Explicit Live Mixed-Step Sequence Runner

**Date:** 2026-06-24
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push — Stage 5 (live execution)
**Predecessors:** LM4I (#339) full live repair chain · LM4J (#340) declared-ref chain · LM4K (#341) `bind_params_from_memory` primitive · LM4L (#343) `apply_memory_bound_params` applier (first consumer)

---

## 1. Goal

Move one rung past LM4L: give the scaffold a **runner-shaped seam that calls
`apply_memory_bound_params`** inside an *explicitly supplied* ordered sequence of mixed
steps. The runner drives `Producer(create) → Verifier(verify_create) → Bind(repair) →
Producer(repair) → Verifier(verify_repair)` for **known node IDs** — but it never decides
the graph path. The caller authors the exact step list.

This is the **first live mixed-step sequence seam**. It is *not* the first sequence
runner of any kind: LM3A's pure learning-layer `plan_graph_walker.py` already replays a
caller-supplied `(node_id, raw_result)` list via `apply_tool_result` and is explicitly
"not a scheduler." LM4M is its live, agent-layer, heterogeneous-step sibling — cited as
precedent, **not reused** (the walker is pure, single-step-kind, and learning-layer;
LM4M is agent-layer, live-capable, and mixes live producer + pure verifier + agent
bind steps).

---

## 2. Non-Goals (guardrails)

- **No node selection.** The caller supplies the exact ordered list; the runner folds
  left over it. `runnable_nodes` is **not imported** (its absence is the clean
  "no selection" proof).
- **No branching, no looping, no retry/escalation policy.** Linear fold with a single
  early exit (stop-on-first-failure).
- **No terminal construction.** No `apply_outcome` import, no terminal step kind. The
  caller applies the final `done` marker after the sequence.
- **No graph-path decision / no "run until complete."** The runner runs the supplied
  steps, nothing more.
- **No dispatch ownership.** Producer steps reach the live tool only through the injected
  `SupportsLiveProducerNode` runner (LM4G Protocol). No dispatcher / server / `base_agent`
  import; `base_agent.py` byte-stable.
- **LM4G / LM4L / walker untouched and pure-as-built.** LM4M composes them.

---

## 3. Architecture

One new agent-layer module:

```
mcp_server/src/rook/agent/plan_graph_sequence_runner.py
```

It left-folds a caller-authored ordered list of typed steps over a `PlanGraph`,
threading the graph and stopping at the first failed/not-applied step. Each step kind
delegates to an existing seam:

| Step kind | Delegates to | Layer |
|---|---|---|
| `ProducerStep` | `runner.run_live_producer_node` (LM4G `SupportsLiveProducerNode` Protocol) → record via `build_live_producer_record` | live (injected) |
| `VerifierStep` | `apply_verifier_step` (LM3D/E reducer step) | pure learning |
| `BindStep` | `apply_memory_bound_params` (LM4L) | agent |

The runner arrives as a structural Protocol, so the module never imports `base_agent`.

---

## 4. Public Surface

```python
from typing import Literal
from collections.abc import Mapping, Sequence

# Step taxonomy (closed for LM4M) -- frozen dataclasses
@dataclass(frozen=True)
class ProducerStep:
    node_id: str
    expectation: LiveProducerExpectation | None = None

@dataclass(frozen=True)
class VerifierStep:
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None = None   # compared against
                                                    # VerifierStepResult.outcome_status

@dataclass(frozen=True)
class BindStep:
    node_id: str
    base_params: Mapping
    bindings: Mapping[str, tuple[str, ...]]

Step = ProducerStep | VerifierStep | BindStep

@dataclass(frozen=True)
class StepOutcome:
    kind: Literal["producer", "verifier", "bind"]
    label: str                                    # node_id (producer/bind) or
                                                  # verifier_node_id
    ok: bool
    producer_record: LiveProducerRecord | None = None
    verifier_result: VerifierStepResult | None = None
    bind_result: MemoryParamApplyResult | None = None

@dataclass(frozen=True)
class SequenceResult:
    graph: PlanGraph
    completed: bool                  # ALL supplied steps ran and passed
    stopped_at: int | None           # index of the failing step, else None
    step_results: tuple[StepOutcome, ...]   # executed steps only
    remaining_steps: tuple[Step, ...]       # unexecuted tail, as-is

async def run_explicit_sequence(
    runner: SupportsLiveProducerNode,
    graph: PlanGraph,
    steps: Sequence[Step],
) -> SequenceResult: ...
```

- **`completed` means sequence-completed, NOT `graph_status == "complete"`.** Because
  the terminal `done` marker stays outside the runner, `completed=True` only asserts that
  every supplied step ran and passed; the graph may merely have `done` *ready*. Tests
  assert `completed` and `done` readiness separately, then apply the terminal marker.
- `VerifierStep.expected_outcome` is typed `OutcomeStatus | None` (matching
  `VerifierStepResult.outcome_status`), not `str | None`.
- `StepOutcome` embeds the native per-step result so callers/tests assert on real types
  (reuses LM4G's `LiveProducerRecord`).

---

## 5. Data Flow (left-fold, stop-on-first-failure)

For each `step` at `index`, dispatch by kind, **always thread `graph = <step>.graph`**
(every seam returns a graph — advanced on apply, input-unchanged on not-applied), then
compute `ok`:

- **ProducerStep:** `result = await runner.run_live_producer_node(graph, node_id)`;
  `record = build_live_producer_record(result, step.expectation)`;
  `graph = result.graph`;
  `ok = (record.passed is True)` when `step.expectation` is provided, else
  `ok = (result.applied is True)`.
- **VerifierStep:** `vres = apply_verifier_step(graph, verifier_node_id, source_node_id)`;
  `graph = vres.graph`;
  `ok = vres.applied and (expected_outcome is None or vres.outcome_status == expected_outcome)`.
- **BindStep:** `bres = apply_memory_bound_params(graph, node_id, base_params, bindings)`;
  `graph = bres.graph`;
  `ok = bres.applied`.

Append the `StepOutcome`. On `not ok`: return immediately with `completed=False`,
`stopped_at=index`, `step_results=<executed>`, `remaining_steps=steps[index+1:]`, and
`graph` = the failed step's returned graph (= last-good graph for a not-applied step;
= the advanced graph for an applied-but-expectation-mismatch producer step). **No
rollback.** After the loop with no failure: `completed=True`, `stopped_at=None`,
`remaining_steps=()`.

### No-expectation producer semantics (explicit)
A `ProducerStep` **without** an expectation passes on `result.applied is True` — i.e.
"the producer step applied," **not** "the artifact is good." An applied producer can
still yield a non-happy outcome (e.g. `created_with_errors`). Acceptance-sensitive
producer steps **must** pass a `LiveProducerExpectation` so `ok` reflects the artifact
verdict (`record.passed`). LM4M's own live/offline chains always pass expectations on
their producer steps.

### Empty sequence
`steps == ()` → `completed=True`, `stopped_at=None`, `step_results=()`,
`remaining_steps=()`, `graph` returned as-is (the runner never copies on its own; it
threads only what the delegated seams return).

---

## 6. Boundaries / Invariants

- agent-layer; imports: `apply_memory_bound_params`, `MemoryParamApplyResult` (LM4L);
  `build_live_producer_record`, `LiveProducerExpectation`, `LiveProducerRecord`,
  `SupportsLiveProducerNode` (LM4G); `apply_verifier_step`, `VerifierStepResult`,
  `OutcomeStatus` (learning); `PlanGraph` `TYPE_CHECKING`-quoted.
- **AST import-boundary guard bans:** `runnable_nodes` (no selection), `apply_outcome`
  (no terminal construction), `rook.agent.base_agent`, `rook.server`, any `dispatch`
  module. Learning never imports this module.
- Production change = **exactly** the one new module
  (`git diff --numstat main...HEAD -- mcp_server/src` lists only
  `agent/plan_graph_sequence_runner.py`); `base_agent.py` byte-stable; LM4G/LM4L/walker
  untouched.

---

## 7. Testing

Whole-branch diff = this spec + the plan + **1 module + 3 test files**.

### Task 1 — real TDD (the prod module)
`mcp_server/tests/test_plan_graph_sequence_runner.py` (focused `test_plan_graph*.py`
gate). A `_FakeRunner` implements `SupportsLiveProducerNode` by applying a pre-seeded
raw-result dict (keyed by node_id) through the **real** `apply_producer_result`, then
wrapping it as a `LiveProducerResult` — offline, deterministic, and faithful to the live
projection. Cases:

- **happy 3-step run:** `Producer(create, expectation) → Verifier(verify_create, create,
  expected="needs_repair") → Bind(repair, base, {guid: path})` over an initialized
  template graph → `completed=True`, `stopped_at=None`, all `step_results` `ok`,
  `remaining_steps=()`, repair node staged with the memory-sourced guid.
- **stop-at-verifier:** a `VerifierStep` with a mismatching `expected_outcome` →
  `completed=False`, `stopped_at=index`, `remaining_steps` holds the tail, downstream
  steps NOT executed (assert their nodes unchanged).
- **stop-at-bind:** a `BindStep` whose binding references a missing memory fact →
  `bind_result.reason == "binding_failed"`, stop.
- **stop-at-producer:** `_FakeRunner` returns a result that fails the supplied
  expectation (or not-applied) → `ok=False`, stop.
- **order-preserved / no-reorder:** a `VerifierStep` placed **before** its source node is
  ready not-applies and halts — proving the runner runs the list in author order and does
  not reorder to satisfy dependencies (the "no selection" behavioral proof).
- **completed ≠ graph complete:** after a happy sequence that stops before `done`,
  assert `completed is True` while `graph_status(result.graph) != "complete"` and
  `done` is `ready`.
- **empty sequence:** `()` → `completed=True`, empty results, graph returned as-is.
- **AST import-boundary guard:** module imports no `runnable_nodes` / `apply_outcome` /
  `base_agent` / server / dispatcher.

### Task 2 — offline chain guard
`mcp_server/tests/test_plan_graph_sequence_runner_chain.py` (focused gate). Drive the full
5-step sequence `Producer(create) → Verifier(verify_create, create) → Bind(repair) →
Producer(repair) → Verifier(verify_repair, repair)` with the `_FakeRunner`; assert
`completed=True` and `done` is `ready`; **then the test applies the terminal**
`apply_outcome("done", NodeOutcome(status="succeeded"))` → `graph_status == "complete"`.
Honest scope: producer steps are faked via raw projection, so this proves
sequencing + applier-mid-sequence + composition to the brink of complete, **not** live
dispatch.

### Task 3 — live proof (`requires_rhino`, outside the glob)
`mcp_server/tests/test_live_sequence_runner_chain_live.py`. The LM4L declared-ref live
chain, but the middle is driven by `run_explicit_sequence` with a **real**
`RookAgent` runner over the 5-step list:

- `_ensure_gh_document()` guard; `fresh_document`; no producer ref overrides.
- Set create `execution_params` directly + `status="ready"` (author-supplied: code, pins,
  name, x/y; omit `language` — the csharp alias forces it; component `LM4MSequenceRunnerLive`).
- Build steps: `Producer("create_script", expectation=created_with_errors) →
  Verifier("verify_create", "create_script", expected="needs_repair") →
  Bind("repair_same_component", {code, mode, language}, {"guid": ("repair_anchor",
  "component_guid")}) → Producer("repair_same_component", expectation=usable) →
  Verifier("verify_repair", "repair_same_component", expected="succeeded")`.
- `result = await run_explicit_sequence(agent, graph, steps)`.
- Assert `result.completed is True`, `result.stopped_at is None`; the bind `StepOutcome`'s
  `bind_result.binding.params["guid"]` equals the create step's
  `evidence.repair_anchor["component_guid"]` (control — memory == evidence); the repair
  `producer_record.tool_status is None` (LM4I/J unwrapped-success finding).
- Assert `result.graph.nodes["done"].status == "ready"` and
  `graph_status(result.graph) != "complete"`, then apply the terminal
  `apply_outcome("done", NodeOutcome(status="succeeded"))` → `graph_status == "complete"`.

---

## 8. Process / Gates

- `codex/` branch off `main`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- PowerShell glob gotcha: enumerate the focused gate via `Get-ChildItem`.
- Focused PlanGraph gate green (rises from 280).
- **Pause before Task 3 live acceptance** (needs Rhino + Grasshopper open, Rook loaded).
- Restore `knowledge/gh/operations_knowledge.json` after live runs; never commit it.
- Merge to `main` **always** needs explicit user approval.

---

## 9. North-Star Fit

Stage 5 progressed: LM4A→G observability, LM4H handoff, LM4I full repair chain, LM4J
declared-ref dispatch, LM4K the memory→params primitive, LM4L the first consumer
(applier). LM4M is the first **runner-shaped** seam that calls that applier — a bounded,
caller-authored, linear sequence of live + pure + bind steps that drives the repair chain
to the brink of `complete` without choosing the path. The next rung beyond LM4M
(autonomous node **selection** reporting into LM4G records) remains explicitly out of
scope.
