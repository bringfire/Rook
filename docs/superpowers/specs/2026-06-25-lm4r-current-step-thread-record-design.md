# LM4R - Current-Step Thread-And-Record Primitive

**Date:** 2026-06-25
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push - execution pivot, rung 2
**Predecessors:** LM4N (#345) `propose_next_node` · LM4O (#352) `revalidate_proposal` · LM4P (#353) `map_accepted_proposal_to_step` · LM4Q (#354) `execute_mapped_step`

---

## 1. Goal

LM4R records the completed proposal ladder without extending its authority.

LM4N/O/P/Q established the bounded ladder:

1. policy may propose a unique ready node;
2. the proposal is distrusted and revalidated against the current graph;
3. an accepted node is mapped by lookup to a caller-authored `Step`;
4. the already-mapped `Step` is executed exactly once.

LM4R adds the smallest useful observability layer over that ladder: a current-step
thread-and-record primitive. It consumes one canonical current-step artifact envelope,
delegates exactly once to LM4Q, and returns the advanced graph plus a flattened audit
record. It does not propose, revalidate, map, select, loop, evaluate, continue, repair,
or mark `done`.

The practical point is durable auditability: later tooling should not need to spelunk
through nested dataclasses just to answer "what proposal was acted on, what mapping was
used, what ran, and what did the native seam report?" But audit is not policy. The record
is non-authoritative and cannot bless a next step.

---

## 2. Containment Contract

- **Artifact consumer, not ladder caller.** LM4R consumes a `StepMappingResult`; it does
  not call `propose_next_node`, `revalidate_proposal`, or
  `map_accepted_proposal_to_step`.
- **One current graph snapshot per call.** The caller supplies the mapping for the graph
  snapshot being acted on now. Multi-step behavior is represented by repeated external
  calls with fresh current-step artifacts, not by LM4R accepting a predeclared bundle of
  future artifacts.
- **Delegate execution to LM4Q.** LM4R calls `execute_mapped_step(mapping, graph, runner)`
  exactly once. It does not run producer/verifier/bind seams directly.
- **Graph identity is load-bearing.** `CurrentStepResult.graph` is exactly
  `record.execution.graph`. LM4R never independently mutates, repairs, advances,
  rolls back, or reinterprets the graph.
- **Preserve canonical objects.** The record keeps the original `mapping`,
  `mapping.revalidation`, and `execution` objects. Flattened fields are convenience
  observations only, never replacements for canonical truth.
- **Record, do not judge.** LM4R computes no `ok`, `passed`, `completed`,
  `should_continue`, expectation mismatch evaluation, or terminal graph status.
- **Records are non-authoritative.** A `CurrentStepRecord` is a log of one attempt, not a
  token authorizing a future step.
- **Refusals are recordable.** A refused mapping, malformed mapping, missing runner, or
  not-applied native seam result still produces a record. Flattened fields are nullable
  when unavailable.

---

## 3. Architecture

One new agent-layer module:

```text
mcp_server/src/rook/agent/plan_graph_current_step_runner.py
```

Agent-layer is forced because LM4R consumes agent-layer `StepMappingResult` / LM4Q
execution artifacts and delegates to `execute_mapped_step`. Import direction remains
one-way (`agent -> {agent, learning}` through the existing artifacts). Learning modules do
not import LM4R.

LM4R is intentionally not a replacement for LM4M. LM4M is a caller-authored ordered
sequence fold that computes `ok` and stops on failure. LM4R is a one-current-step audit
wrapper around the LM4N/O/P/Q ladder. Future multi-step orchestration may call LM4R
repeatedly, but that orchestration is outside LM4R.

---

## 4. Public Surface

```python
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

MetadataStatus = Literal["absent", "copied", "invalid", "copy_failed"]

@dataclass(frozen=True)
class CurrentStepEnvelope:
    mapping: StepMappingResult
    metadata: Mapping[str, Any] | None = None

@dataclass(frozen=True)
class CurrentStepRecord:
    # caller/audit metadata, snapshot-copied when possible
    metadata: dict[str, Any] | None
    metadata_status: MetadataStatus
    metadata_error: str | None

    # canonical audit objects
    mapping: StepMappingResult
    revalidation: RevalidationResult
    execution: StepExecutionResult

    # flattened proposal/revalidation/mapping/execution observations
    supplied_selected_node_id: str | None
    fresh_selected_node_id: str | None
    accepted_node_id: str | None
    mapping_mapped: bool
    mapping_failure: str | None
    mapped_step_target: str | None
    ran: bool
    execution_kind: str | None
    execution_failure: str | None

    # nullable native seam observations
    producer_node_id: str | None
    producer_tool_name: str | None
    producer_applied: bool | None
    producer_outcome_status: str | None
    producer_reason: str | None
    verifier_node_id: str | None
    verifier_source_node_id: str | None
    verifier_applied: bool | None
    verifier_outcome_status: str | None
    verifier_reason: str | None
    bind_node_id: str | None
    bind_applied: bool | None
    bind_reason: str | None

@dataclass(frozen=True)
class CurrentStepResult:
    graph: PlanGraph
    record: CurrentStepRecord

async def run_current_mapped_step(
    envelope: CurrentStepEnvelope,
    graph: PlanGraph,
    runner: SupportsLiveProducerNode | None = None,
) -> CurrentStepResult: ...
```

The exact field order may change during implementation if tests show a clearer layout,
but the contract does not: the canonical objects remain attached, flattened fields are
nullable observations, and no verdict fields are added.

---

## 5. Logic

1. **Snapshot-copy metadata.**
   - `metadata is None` -> `metadata=None`, `metadata_status="absent"`.
   - `metadata` is not a `Mapping` -> `metadata=None`, `metadata_status="invalid"`.
   - `metadata` is a `Mapping` and `deepcopy(dict(metadata))` succeeds ->
     `metadata=<copied dict>`, `metadata_status="copied"`.
   - Copy fails -> `metadata=None`, `metadata_status="copy_failed"`,
     `metadata_error=<exception class/message>`.

   Metadata copy problems do not prevent recording. They are observations on the record.
   This avoids a mutability leak while keeping the audit path tolerant.

2. **Delegate once.**
   - `execution = await execute_mapped_step(envelope.mapping, graph, runner)`.
   - LM4R does not call any lower producer/verifier/bind seam directly.

3. **Build a flattened record from canonical objects.**
   - `mapping = envelope.mapping`.
   - `revalidation = mapping.revalidation`.
   - `execution = execution`.
   - Proposal fields are read through `mapping.revalidation.proposal` and
     `mapping.revalidation.fresh_proposal`.
   - Mapping fields are read through `mapping`.
   - Execution fields are read through `execution` and the one native seam result that is
     present, if any.

4. **Return the execution graph.**
   - `CurrentStepResult.graph is execution.graph`.
   - `CurrentStepResult.record.execution is execution`.
   - No graph status is computed and no terminal node is applied.

### Mapped-step target flattening

`mapped_step_target` is an observation, not validation. It is populated only when
`mapping.step` is a real `ProducerStep`, `VerifierStep`, or `BindStep`, using the same
target convention as LM4P:

- `ProducerStep` -> `node_id`;
- `VerifierStep` -> `verifier_node_id`;
- `BindStep` -> `node_id`.

If the mapping is refused, `mapping.step` is `None`, or a forged mapping carries a
non-Step object, `mapped_step_target=None`. LM4R must check the structural type before
reading any step field so it can record malformed mappings without crashing.

---

## 6. Boundaries / Invariants

Allowed imports:

- `StepMappingResult` from `rook.agent.plan_graph_step_mapping`;
- `execute_mapped_step`, `StepExecutionResult` from
  `rook.agent.plan_graph_step_executor`;
- `ProducerStep`, `VerifierStep`, `BindStep` from
  `rook.agent.plan_graph_sequence_runner` for nullable target flattening only;
- `SupportsLiveProducerNode` from `rook.agent.plan_graph_live_runner`;
- `RevalidationResult` from `rook.learning.plan_graph_revalidation` for typing;
- `PlanGraph` via `TYPE_CHECKING`;
- stdlib `copy`, `dataclasses`, `typing`, `collections.abc`.

Banned imports/references:

- `propose_next_node`, `revalidate_proposal`, `map_accepted_proposal_to_step`,
  `runnable_nodes`;
- `apply_outcome`, `apply_verifier_step`, `apply_producer_result`,
  `apply_memory_bound_params`;
- `run_explicit_sequence`, `build_live_producer_record`;
- `select_template`;
- dispatcher/server/`base_agent`/LiteLLM/model imports.

Additional invariants:

- No `ProducerStep(...)`, `VerifierStep(...)`, or `BindStep(...)` constructor calls in the
  LM4R module. It may use those classes only for `isinstance` checks and annotations.
- No loops over envelopes or mappings. The module may have small fixed-field helper logic,
  but it must not implement a sequence fold.
- No field named `ok`, `passed`, `completed`, `should_continue`, or equivalent verdict.
- LM4R never mutates the envelope, mapping, execution, or input graph.

---

## 7. Testing

Whole-branch implementation should be one production module plus focused tests. No live
test is required for LM4R because LM4Q already has the live producer smoke; LM4R's novelty
is the audit wrapper around LM4Q, which is deterministic with fake/native seam results.

### Task 1 - Current-step record unit tests

`mcp_server/tests/test_plan_graph_current_step_runner.py`

- **happy producer record:** a mapped `ProducerStep` with a fake LM4Q-style producer
  runner returns a `CurrentStepResult`; assert `result.graph is result.record.execution.graph`,
  canonical `mapping` / `revalidation` / `execution` object identity is preserved, and
  flattened producer observations are populated.
- **happy verifier record:** mapped `VerifierStep` records verifier node/source,
  `verifier_applied`, `verifier_outcome_status`, and leaves producer/bind observations
  `None`.
- **happy bind record:** mapped `BindStep` records bind node/applied/reason and leaves
  producer/verifier observations `None`.
- **refused mapping still records:** `StepMappingResult(mapped=False, step=None, ...)`
  delegates to LM4Q, records `ran=False`, `execution_failure="not_mapped"`, nullable
  target/seam fields, and returns the input graph through LM4Q's refusal graph.
- **forged malformed mapping still records:** `mapped=True` with `step=object()` records
  `mapped_step_target is None` and LM4Q's `mapping_invalid` refusal without crashing.
- **runner-required refusal records:** mapped producer with `runner=None` records
  `execution_failure="runner_required"`, no producer result.
- **native not-applied is not reinterpreted:** verifier or bind seam returns
  `applied=False`; LM4R still records `ran=True`, `execution_failure is None`, and the
  native applied/reason fields. No `ok` or `passed` field exists.
- **metadata absent/copied/invalid/copy_failed:** metadata is snapshot-copied when
  possible; mutating the caller metadata after the call does not change
  `record.metadata`; invalid/copy-failed metadata produces a record with the matching
  metadata status and no exception.
- **nullable flattened fields:** every non-applicable flattened seam field is `None`.
- **non-authoritative record shape:** dataclass fields do not include `ok`, `passed`,
  `completed`, `should_continue`, or graph-status/terminal verdict fields.
- **import-boundary AST guard:** banned imports/references are absent; no Step
  constructors are called; `run_explicit_sequence` and `build_live_producer_record` are
  not referenced.

### Task 2 - Chain composition guard

`mcp_server/tests/test_plan_graph_current_step_runner_chain.py`

Drive the real 5-node template to where `verify_create` is uniquely ready, as in the
LM4P/Q chain tests:

1. Build a fresh `verify_create` proposal/mapping outside LM4R.
2. Call `run_current_mapped_step(CurrentStepEnvelope(mapping), graph)`.
3. Assert one verifier step ran, graph advanced, record preserves mapping/revalidation/
   execution, and `repair_same_component` is now uniquely ready when observed by the test
   outside LM4R.
4. Attempt the old proposal against the advanced graph by calling LM4P outside LM4R,
   producing a fresh not-mapped `StepMappingResult`; pass that refused mapping to LM4R
   and assert it records LM4Q's refusal and runs nothing.

Honest scope: the test may call selector/mapping functions to prepare artifacts, but LM4R
does not. LM4R is never asked to run a second step from the first record. LM4R does not
detect stale-but-still-mapped artifacts; current-snapshot validity is the caller's
contract.

---

## 8. Process / Gates

- Branch: `codex/lm4r-current-step-record`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- Focused PlanGraph gate should include the new `test_plan_graph_current_step_runner*.py`
  files.
- No live acceptance gate for LM4R unless implementation unexpectedly changes the
  execution seam boundary.
- After spec review approval, invoke `superpowers:writing-plans` before code.
- Stop at PR; no merge without explicit approval.

---

## 9. North-Star Fit

The campaign north star says local/internal models are bounded node resolvers inside a
Rook-owned scaffold. The scaffold owns contracts, PlanGraph state, verifier gates, repair
anchors, memory propagation, mapping, policy, and execution authority.

LM4R strengthens that scaffold by making the already-built policy/mapping/execution chain
inspectable as a single current-step audit record. It deliberately does not add future-path
authority. The model still does not remember the plan, own graph mutation, select nodes,
construct steps, remap stale artifacts, or decide continuation. LM4R records one attempt
against one graph snapshot and hands the resulting graph back to the caller.
