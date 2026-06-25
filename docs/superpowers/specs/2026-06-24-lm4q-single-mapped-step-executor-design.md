# LM4Q — Single Mapped-Step Executor (first gated execution authority)

**Date:** 2026-06-24
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push — execution pivot, rung 1
**Predecessors:** LM4N (#345) `propose_next_node` · LM4O (#352) `revalidate_proposal` · LM4P (#353) `map_accepted_proposal_to_step`

---

## 1. Goal

The **propose → distrust → consume** ladder (LM4N/O/P) ends with a decision already
translated into runner language: an LM4P `StepMappingResult` whose `step` is the caller's
prebuilt LM4M `Step`, validated and node-targeted. Every rung so far has withheld execution
authority.

LM4Q grants the **smallest possible execution authority**: given an already-mapped
`StepMappingResult` and the current graph, it executes **exactly that one Step** by delegating
to the existing seam for its kind, and returns the advanced graph plus the native seam result.

LM4Q answers one question only — *"am I allowed to run this already-mapped Step?"* — never
*"what should I run?"*. It **consumes the ladder's artifact**; it does not rebuild the ladder.

The ladder, extended:
- **LM4N:** policy may *propose*.
- **LM4O:** proposals are *distrusted and revalidated*.
- **LM4P:** an accepted selection is *mapped* to a typed Step the caller pre-authored.
- **LM4Q:** an already-mapped Step is *executed* — once, with no selection/mapping/loop.

---

## 2. Containment Contract (load-bearing)

- **Execute the artifact, never rebuild the ladder.** LM4Q consumes a `StepMappingResult`. It
  does **not** propose (`propose_next_node`), revalidate (`revalidate_proposal`), map
  (`map_accepted_proposal_to_step`), or select (`runnable_nodes`). AST-guarded: none of those
  names are imported or referenced.
- **One step, no loop, no fold.** LM4Q runs exactly `mapping.step`. No iteration, no
  branching beyond kind dispatch, no early-stop fold, no `run_explicit_sequence`
  (no length-1-sequence smuggling — the public contract is one gated mapped-step execution).
- **No terminal construction.** No `apply_outcome`; LM4Q never marks `done` / constructs a
  terminal outcome.
- **No fallback / no substitution.** A refused mapping runs nothing — even when a *different*,
  now-correct Step exists. LM4Q never substitutes a "fresh correct step".
- **Execute, don't evaluate.** LM4Q returns the native seam result and never computes
  pass/fail. It does **not** read `ProducerStep.expectation` or `VerifierStep.expected_outcome`
  (those are LM4G-record / LM4M-fold concerns). Enforced by poison-expectation test objects.
- **Distrust the public artifact's shape.** `StepMappingResult` is public runtime data. Before
  dispatch, LM4Q does a minimal structural check: if `mapping.step` is not a real
  `ProducerStep` / `VerifierStep` / `BindStep`, it refuses (`mapping_invalid`) rather than
  crashing or misdispatching. This validates *artifact shape only* — it does **not** re-run
  LM4P's target-node validation.
- **Honest dependency.** Only `ProducerStep` needs the async live runner; `VerifierStep` /
  `BindStep` must not touch it. A missing runner for a producer step is a clean refusal
  (`runner_required`), not a crash.

---

## 3. Architecture

One new **agent-layer** module:

```
mcp_server/src/rook/agent/plan_graph_step_executor.py
```

Agent-layer is *forced*: LM4Q delegates to the three seams LM4M already uses — the live
producer runner (agent `plan_graph_live_runner` Protocol), pure `apply_verifier_step`
(learning), and LM4L `apply_memory_bound_params` (agent) — and consumes the LM4P
`StepMappingResult` (agent) carrying LM4M `Step` types (agent). Import direction stays one-way
(`agent → {agent, learning}`).

It is the first rung with execution authority, but a *minimal* one: the producer branch
delegates to the **already-live-proven** `run_live_producer_node` seam (LM4H/I/J/M); LM4Q's
own novelty is the **gate around dispatch**, which is pure logic.

`execute_mapped_step` is `async` because the producer branch awaits
`runner.run_live_producer_node(...)`. The verifier/bind branches are synchronous and run
inside the coroutine without awaiting.

---

## 4. Public Surface

```python
from typing import Literal
from dataclasses import dataclass

StepExecutionFailure = Literal[
    "not_mapped",       # mapping.mapped is not True OR mapping.step is None
    "mapping_invalid",  # mapping.step is not a ProducerStep/VerifierStep/BindStep
    "runner_required",  # mapped ProducerStep but runner is None
]

@dataclass(frozen=True)
class StepExecutionResult:
    ran: bool
    kind: Literal["producer", "verifier", "bind"] | None
    graph: "PlanGraph"                       # advanced on run; INPUT graph (unchanged) on refusal
    failure: StepExecutionFailure | None     # set iff not ran (a pre-execution refusal)
    reason: str                              # human/audit string
    mapping: StepMappingResult               # ALWAYS carried, for audit
    producer_result: LiveProducerResult | None = None
    verifier_result: VerifierStepResult | None = None
    bind_result: MemoryParamApplyResult | None = None

async def execute_mapped_step(
    mapping: StepMappingResult,
    graph: PlanGraph,
    runner: SupportsLiveProducerNode | None = None,
) -> StepExecutionResult: ...
```

`mapping` is always populated (the audit spine). Exactly one of the three `*_result` fields is
non-None when `ran=True`; all three are `None` on a refusal. The producer branch returns the
native `LiveProducerResult` (no record/eval wrapping).

---

## 5. Logic (gate → structural check → dispatch; one step, never evaluate, never fallback)

1. **Gate: mapping must be a green light.** If `mapping.mapped is not True` **or**
   `mapping.step is None` → `ran=False`, `kind=None`, `graph is <input>`,
   `failure="not_mapped"`, all `*_result` None, `mapping` carried.
2. **Structural check: distrust the artifact's shape.** `step = mapping.step`. If **not**
   `isinstance(step, (ProducerStep, VerifierStep, BindStep))` (explicit tuple form — never
   `isinstance(step, Step)` and never the `Step` union alias at runtime) → `ran=False`,
   `kind=None`, `graph is <input>`, `failure="mapping_invalid"`. Checked **before** reading any
   field of `step`, so a forged `mapped=True, step=object()` cannot crash or fall into a branch.
3. **Dispatch with explicit per-kind branches (no final else-as-bind).**
   - `isinstance(step, ProducerStep)`:
     - if `runner is None` → `ran=False`, `kind=None`, `graph is <input>`,
       `failure="runner_required"`.
     - else `result = await runner.run_live_producer_node(graph, step.node_id)`;
       `graph = result.graph`; `kind="producer"`; `producer_result=result`.
   - `elif isinstance(step, VerifierStep)`:
     `vres = apply_verifier_step(graph, step.verifier_node_id, step.source_node_id)`;
     `graph = vres.graph`; `kind="verifier"`; `verifier_result=vres`.
   - `elif isinstance(step, BindStep)`:
     `bres = apply_memory_bound_params(graph, step.node_id, step.base_params, step.bindings)`;
     `graph = bres.graph`; `kind="bind"`; `bind_result=bres`.
   The three `isinstance` arms are exhaustive because step 2 already guaranteed membership; an
   explicit chain (not an `else`) keeps the bind branch from silently swallowing a future
   fourth kind.
4. **Report, don't judge.** On any dispatched branch → `ran=True`, `failure=None`,
   `reason="executed <kind> step <label>"`. `ran=True` holds **even if** the seam result says
   not-applied/failed (e.g. `vres.applied is False`, `bres.applied is False`, a producer that
   dispatched but did not verify). The native seam result carries that truth; LM4Q never
   reinterprets it. LM4Q's only failures are the three pre-execution refusals in steps 1–2 and
   the producer `runner_required` in step 3.

LM4Q never reads `step.expectation` / `step.expected_outcome` anywhere.

---

## 6. Boundaries / Invariants

- **Execution authority, bounded:** dispatches exactly one Step via the existing seams; no
  selection, no loop, no terminal `done`, no graph mutation beyond what the delegated seam
  performs (producer/verifier/bind each return the graph — advanced on apply, input-unchanged
  on not-applied).
- **Pure-of-policy:** never mutates `mapping`; on refusal `result.graph is graph` (the input
  object). Verifier/bind never touch `runner`.
- **Imports:** `StepMappingResult` (the *artifact type*) from agent `plan_graph_step_mapping`;
  `ProducerStep` + `VerifierStep` + `BindStep` from agent `plan_graph_sequence_runner`;
  `SupportsLiveProducerNode` from agent `plan_graph_live_runner`; `LiveProducerResult` from
  agent `plan_graph_live`; `VerifierStepResult` + `apply_verifier_step` from learning
  `plan_graph_runner`; `MemoryParamApplyResult` + `apply_memory_bound_params` from agent
  `plan_graph_param_apply`; `PlanGraph` `TYPE_CHECKING`-quoted; stdlib
  `dataclass`/`typing`. **Banned (and AST-guarded):** `map_accepted_proposal_to_step`,
  `revalidate_proposal`, `propose_next_node` (consume the artifact, don't rebuild the ladder);
  `runnable_nodes` (no selection); `apply_outcome` (no terminal construction); `select_template`;
  `run_explicit_sequence` (no length-1 smuggling); `build_live_producer_record` (no evaluation);
  `rook.agent.base_agent`, dispatcher, server, LiteLLM/model.
- **AST guards:** (a) **no constructor call** to `ProducerStep`/`VerifierStep`/`BindStep` in the
  module (LM4Q returns `mapping.step`, never builds one — isinstance + annotations allowed);
  (b) the banned-name import/reference guard above.
- Production change = **exactly** one new module
  (`git diff --numstat main...HEAD -- mcp_server/src` lists only
  `agent/plan_graph_step_executor.py`); `base_agent.py` byte-stable; LM4M/LM4N/LM4O/LM4P
  modules + the LM3A walker untouched.

---

## 7. Testing

Whole-branch diff = this spec + the plan + **1 module + 2 automated test files + 1 live test
file = 6 paths**.

### Task 1 — real TDD (the prod module)
`mcp_server/tests/test_plan_graph_step_executor.py` (focused `test_plan_graph*.py` gate).
Failing tests first, then the module. Build minimal graphs via
`PlanGraph(nodes={id: PlanGraphNode(...)})`; mappings via the real
`map_accepted_proposal_to_step` for accept cases and hand-built `StepMappingResult` for
refusal/forged cases; Step objects via the real LM4M constructors **in the test** (allowed in
tests). Use a `FakeProducerRunner` implementing `SupportsLiveProducerNode` that returns a
canned `LiveProducerResult` (no Rhino).

- **mapped ProducerStep (fake runner):** mapping with `step=ProducerStep("X")`,
  `runner=FakeProducerRunner(...)` → `ran=True`, `kind=="producer"`,
  `result.producer_result is` the fake's returned result, `result.graph is` the fake result's
  graph (advanced), `failure is None`, `verifier_result`/`bind_result` None.
- **mapped VerifierStep:** delegates to `apply_verifier_step` → `ran=True`, `kind=="verifier"`,
  `verifier_result` is the native `VerifierStepResult`, graph advanced.
- **mapped BindStep:** delegates to `apply_memory_bound_params` → `ran=True`, `kind=="bind"`,
  `bind_result` is the native `MemoryParamApplyResult`.
- **seam result not reinterpreted (verifier):** a VerifierStep whose `apply_verifier_step`
  returns `applied=False` (e.g. unknown source/verifier wiring) → still `ran=True`,
  `failure is None`, `verifier_result.applied is False` (LM4Q reports, does not convert to a
  failure).
- **seam result not reinterpreted (bind):** a BindStep whose `apply_memory_bound_params`
  returns `applied=False` (e.g. `unknown_node`) → `ran=True`, `bind_result.applied is False`,
  `failure is None`.
- **not_mapped — mapped False:** hand-built `StepMappingResult(mapped=False, step=None, …)` →
  `ran=False`, `kind is None`, `failure=="not_mapped"`, `result.graph is graph`, all
  `*_result` None, `mapping` carried.
- **not_mapped — step None:** forged `StepMappingResult(mapped=True, step=None, …)` →
  `not_mapped` (the `step is None` arm).
- **mapping_invalid:** forged `StepMappingResult(mapped=True, step=object(), …)` → `ran=False`,
  `kind is None`, `failure=="mapping_invalid"`, `result.graph is graph`, **no crash** (proves
  the structural check precedes any field read / branch).
- **runner_required:** mapped `ProducerStep("X")`, `runner=None` → `ran=False`, `kind is None`,
  `failure=="runner_required"`, `result.graph is graph`, `producer_result is None`.
- **runner-not-touched seam pin:** a `PoisonRunner` whose **every attribute access raises**
  passed as `runner` to a mapped VerifierStep **and** a mapped BindStep → both `ran=True`
  (LM4Q never touches `runner` on the non-producer branches).
- **poison-expectation guard:** a `ProducerStep(node_id="X", expectation=<PoisonExpectation
  that raises on attribute access>)` (fake runner) and a `VerifierStep(verifier_node_id="X",
  source_node_id="s", expected_outcome=<poison>)` → both `ran=True`, no access to the poisoned
  fields (LM4Q executes, never evaluates).
- **mapping carried everywhere:** `result.mapping is` the passed mapping in every run and every
  refusal case.
- **frozen / pure:** `mapping` and `graph` unchanged after a call; the sync (verifier/bind)
  paths yield equal results on two calls; on every refusal `result.graph is graph`.
- **no-Step-construction AST guard:** parse the module; assert there is **no `ast.Call` whose
  callee name is `ProducerStep`/`VerifierStep`/`BindStep`** (isinstance + annotations allowed).
- **import-boundary AST guard:** the module imports no `rook.agent.base_agent`, no
  dispatcher/server, no LiteLLM/model; references **none** of `propose_next_node`,
  `revalidate_proposal`, `map_accepted_proposal_to_step`, `runnable_nodes`, `apply_outcome`,
  `select_template`, `run_explicit_sequence`, `build_live_producer_record`.

### Task 2 — chain execution guard
`mcp_server/tests/test_plan_graph_step_executor_chain.py` (focused gate). Drive the real
5-node `gh_csharp_create_verify_repair_verify` template to where `verify_create` is uniquely
ready (`select_template` → `initialize_graph` → `apply_producer_result(create_script,
wrapped-failure-create raw)` — reuse the exact wrapped-failure raw dict helper from the
LM4K/L/M/N/O/P chain tests). Build a caller `step_map` keyed by chain node id, each value a
prebuilt Step targeting its own node (`verify_create → VerifierStep("verify_create",
"create_script", expected_outcome="needs_repair")`, `repair_same_component →
ProducerStep("repair_same_component")`).

- **gate → map → execute one step:** `proposal = propose_next_node(graph)`
  (`SELECT_NODE("verify_create")`); `mapping = map_accepted_proposal_to_step(proposal, graph,
  step_map)` (`mapped=True`); `execute_mapped_step(mapping, graph)` →
  `ran=True`, `kind=="verifier"`, `verifier_result.applied is True`, graph advanced
  (`verify_create` → needs_repair, `repair_same_component` now uniquely ready). No runner is
  needed (verifier branch).
- **stale mapping → nothing runs, no fallback:** take the **old** `verify_create` proposal,
  re-map against the *advanced* graph → LM4P returns `mapped=False`
  (`revalidation.reject_reason == "selected_not_ready"`); `execute_mapped_step(stale_mapping,
  advanced_graph)` → `ran=False`, `failure=="not_mapped"`, `result.graph is advanced_graph`,
  nothing runs — **even though `step_map` holds a valid `repair_same_component` entry.** The
  no-fallback proof at the execution layer.

Honest scope: LM4Q executes **one** step; these guards never loop to run the next step, never
construct a terminal `done`, and never drive the chain to `graph_status == "complete"`.

### Task 3 — live producer smoke (`requires_rhino`)
`mcp_server/tests/test_live_step_executor_producer_live.py` (**outside** the `test_plan_graph*`
glob; not in the focused gate). One mapped **ProducerStep** through a real
`RookAgent(_mcp_tool_executor)` → `execute_mapped_step(mapping, graph, runner=agent)` reaching
the **real declared create producer**. Using the 5-node template root `create_script` node, the
declared ref is `gh_create_csharp_script:v1`, which resolves **live** to
`gh_create_csharp_script` (LM4J) — **no producer override**; supply the create node's
execution_params (a simple valid C# body, e.g. `A = 42.0;` with `["A:double"]`, mirroring prior
live producer tests). Drive `select_template` → `initialize_graph` so `create_script` is
uniquely ready → `propose_next_node` SELECT → `map_accepted_proposal_to_step` with
`{create_script: ProducerStep("create_script")}` → `execute_mapped_step(mapping, graph,
runner=agent)`.

- Assert the mapped Step reaches a real `RookAgent.run_live_producer_node`.
- Assert `ran is True`, `kind == "producer"`, `producer_result is not None`, and an advanced
  graph is returned (`result.graph is producer_result.graph`).
- **Narrow:** ProducerStep only — **no** full chain, **no** verifier/bind live, **no**
  expectation evaluation.
- `_ensure_gh_document()` guard (GH must have an active document — window ≠ doc); GH + Rhino
  open with Rook loaded.
- **Restore `knowledge/gh/operations_knowledge.json`** after the run (live runs dirty it;
  `git restore` it — never commit).

---

## 8. Process / Gates

- `codex/lm4q-single-mapped-step-executor` branch off `main`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- PowerShell glob gotcha: enumerate the focused gate via `Get-ChildItem`.
- Focused PlanGraph gate green (rises from 330).
- **Pause before the Task 3 live acceptance** (requires Rhino + Grasshopper open with Rook
  loaded) for explicit go-ahead.
- Merge to `main` **always** needs explicit user approval.
- Execution: **Subagent-Driven**.

---

## 9. North-Star Fit

The north-star scheduler eventually "validates [a proposal] against known contracts… inserts
it if safe" (§574–575). LM4N–LM4P built *propose → validate → translate*. LM4Q builds the
first sliver of *insert/run*: it takes an already-validated, already-translated Step and
**executes exactly that one step** through the existing seams — but withholds everything that
would make it a scheduler. It selects nothing (it consumes a mapping), loops over nothing,
constructs no terminal `done`, evaluates nothing, and falls back to nothing. The execution
authority it grants is the minimum that is still real: one Step, dispatched, reported. The
next rung (its own design) would be the first thing that *threads* gate → map → execute across
more than one step — a bounded runner that reports into LM4G records — and remains out of LM4Q
scope.
