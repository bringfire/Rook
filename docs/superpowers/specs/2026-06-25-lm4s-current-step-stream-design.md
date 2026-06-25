# LM4S - Caller-Fed Current-Step Stream Runner

**Date:** 2026-06-25
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push - execution pivot, rung 3
**Predecessors:** LM4N (#345) `propose_next_node` · LM4O (#352) `revalidate_proposal` · LM4P (#353) `map_accepted_proposal_to_step` · LM4Q (#354) `execute_mapped_step` · LM4R (#356) `run_current_mapped_step`

---

## 1. Goal

LM4S is the first bounded primitive that threads more than one LM4R current-step call
together while still refusing to become a scheduler.

LM4R gave the scaffold one audited current-step attempt:

```text
CurrentStepEnvelope(mapping)
  -> run_current_mapped_step(...)
  -> CurrentStepRecord + execution.graph
```

LM4S repeats that shape under a caller-fed provider:

```text
current graph + prior trace
  -> caller supplies next already-built CurrentStepEnvelope or HALT
  -> LM4S records supply decision
  -> LM4S delegates supplied envelope to LM4R
  -> LM4S records the CurrentStepRecord and threads graph
```

It creates a real multi-step trace, but selection authority stays outside LM4S. The
provider may call LM4N/O/P or any caller-owned policy before returning an envelope, but
LM4S does not know, call, validate, or substitute that policy. LM4S only records the
provider decision, delegates to LM4R, and stops under explicit loop-safety rules.

---

## 2. Containment Contract

- **Caller-fed, not self-selecting.** LM4S receives a provider callable. It never calls
  `propose_next_node`, `revalidate_proposal`, or `map_accepted_proposal_to_step`.
- **LM4R is the only execution delegate.** LM4S calls `run_current_mapped_step` for
  supplied envelopes. It never calls LM4Q directly and never runs producer/verifier/bind
  seams.
- **Provider is sync.** LM4S is async because LM4R is async, but the provider is a normal
  synchronous callable. Async provider support is out of scope.
- **Required positive step budget.** `max_steps` is a required `int`. `max_steps <= 0`
  stops immediately with `max_steps_invalid`; there is no default and no unbounded mode.
- **Trace before policy.** LM4S records provider decisions and LM4R current-step records.
  It does not decide whether those decisions were wise.
- **Loop safety is not success judgment.** `graph_not_advanced` means only that LM4R ran
  but returned the identical graph object, so LM4S will not keep asking for more
  envelopes against an unchanged graph. It does not classify the operation as success or
  failure.
- **Stop-event evidence is preserved.** For `execution_refused` and `graph_not_advanced`,
  append the `CurrentStepRecord` before stopping. For provider halt/invalid/error, append
  an `EnvelopeSupplyRecord` before stopping.
- **No hidden recovery.** No fallback, retry, remap, substitution, terminal `done`, model
  call, or expectation evaluation.

---

## 3. Architecture

One new agent-layer module:

```text
mcp_server/src/rook/agent/plan_graph_current_step_stream.py
```

This module composes LM4R. It is intentionally separate from LM4M:

- LM4M folds a caller-authored ordered list of typed `Step`s and computes `ok`.
- LM4R executes and records one already-mapped current-step artifact.
- LM4S repeatedly asks a caller-owned provider for the next current-step envelope, records
  each supply decision, delegates each supplied envelope to LM4R, and stops under bounded
  stream rules.

The new module should stay small. It owns only stream dataclasses, provider result shape
validation, provider metadata copying, provider exception capture, and graph threading.

---

## 4. Public Surface

```python
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
)

SupplyDecision = Literal["SUPPLY", "HALT"]

StopReason = Literal[
    "provider_halt",
    "provider_invalid",
    "provider_error",
    "execution_refused",
    "graph_not_advanced",
    "max_steps_reached",
    "max_steps_invalid",
]

SupplyInvalidReason = Literal[
    "supply_result_invalid",
    "supply_missing_envelope",
    "halt_with_envelope",
    "halt_missing_reason",
    "unknown_supply_decision",
]

@dataclass(frozen=True)
class EnvelopeSupplyResult:
    decision: SupplyDecision
    envelope: CurrentStepEnvelope | None
    reason: str | None
    metadata: Mapping[str, Any] | None = None

@dataclass(frozen=True)
class EnvelopeSupplyRecord:
    decision: str | None
    envelope: CurrentStepEnvelope | None
    reason: str | None
    metadata: dict[str, Any] | None
    metadata_status: Literal["absent", "copied", "invalid", "copy_failed"]
    metadata_error: str | None
    invalid_reason: SupplyInvalidReason | None = None
    error_class: str | None = None
    error_message: str | None = None

EnvelopeSource = Callable[
    [PlanGraph, tuple[CurrentStepRecord, ...], tuple[EnvelopeSupplyRecord, ...]],
    EnvelopeSupplyResult,
]

@dataclass(frozen=True)
class CurrentStepStreamResult:
    final_graph: PlanGraph
    records: tuple[CurrentStepRecord, ...]
    supply_records: tuple[EnvelopeSupplyRecord, ...]
    stop_reason: StopReason
    steps_attempted: int

async def run_current_step_stream(
    initial_graph: PlanGraph,
    envelope_source: EnvelopeSource,
    *,
    max_steps: int,
    runner: SupportsLiveProducerNode | None = None,
) -> CurrentStepStreamResult: ...
```

`max_steps` is required and keyword-only, with no default. `runner` may default to
`None`, matching LM4R's local style, but callers must always spell out the budget.

---

## 5. Provider Context

Each provider call receives:

```python
envelope_source(
    current_graph,
    tuple(records),
    tuple(supply_records),
)
```

LM4S owns the internal mutable accumulation lists. It passes tuple snapshots so the
provider cannot append/pop the runner's internal lists. This is containment, not deep
immutability: provider code can still mutate mutable objects inside the records if it has
references to them. LM4S does not deep-copy the whole history on each call; that would be
expensive and unnecessary for this boundary.

---

## 6. Supply Records

LM4S builds an `EnvelopeSupplyRecord` for every provider outcome:

- valid `SUPPLY`;
- valid `HALT`;
- provider-invalid shape;
- provider exception.

Provider metadata is snapshot-copied into the supply record using the same status values
as LM4R metadata:

- `metadata is None` -> `metadata_status="absent"`;
- non-`Mapping` metadata -> `metadata_status="invalid"`;
- copy succeeds -> `metadata_status="copied"`;
- copy raises -> `metadata_status="copy_failed"` plus `metadata_error`.

Metadata copy problems do not affect stop semantics. Provider metadata is audit context,
not policy.

### Alignment invariant

- For each executed step, there is exactly one preceding
  `EnvelopeSupplyRecord(decision="SUPPLY")`.
- For executed steps, `supply_records[i]` corresponds to `records[i]`.
- The final `supply_records` entry may be non-executed: a provider `HALT`, provider
  invalid record, or provider error record.
- If `max_steps_invalid` or `max_steps_reached` fires before asking the provider, no new
  supply record is appended for that stop.

---

## 7. Stop Semantics

Precedence is load-bearing:

1. **Invalid budget before provider call.**
   - If `max_steps <= 0`, return immediately:
     - `stop_reason="max_steps_invalid"`;
     - `final_graph is initial_graph`;
     - `records=()`;
     - `supply_records=()`;
     - provider is not called.

2. **Budget exhausted before asking for another step.**
   - At the top of each loop, if `len(records) >= max_steps`, stop:
     - `stop_reason="max_steps_reached"`;
     - no provider call for the extra step;
     - no new supply record.

3. **Provider exception.**
   - Catch exceptions from `envelope_source(...)`.
   - Append an `EnvelopeSupplyRecord` with:
     - `decision=None`;
     - `envelope=None`;
     - `invalid_reason=None`;
     - `error_class=<exception class name>`;
     - `error_message=<exception message>`;
     - metadata absent, unless a future provider result shape exists before the exception
       source can expose.
   - Stop with `stop_reason="provider_error"`.
   - Do not retry, substitute, or call the provider again.

4. **Provider invalid shape.**
   - Append an `EnvelopeSupplyRecord`.
   - Stop with `stop_reason="provider_invalid"`.
   - Explicit invalid reasons:
     - provider returns a value that is not an `EnvelopeSupplyResult` ->
       `supply_result_invalid`; LM4S records this before reading `.decision`,
       `.envelope`, `.reason`, or `.metadata`;
     - `decision=="SUPPLY"` and `envelope is None` -> `supply_missing_envelope`;
     - `decision=="HALT"` and `envelope is not None` -> `halt_with_envelope`;
     - `decision=="HALT"` and `reason is None` or empty -> `halt_missing_reason`;
     - decision not in `{"SUPPLY", "HALT"}` -> `unknown_supply_decision`.

5. **Provider halt.**
   - Valid `HALT` requires `envelope is None` and a non-empty `reason`.
   - Append supply record.
   - Stop with `stop_reason="provider_halt"`.
   - Append no `CurrentStepRecord`.

6. **Provider supply.**
   - Valid `SUPPLY` requires `envelope is not None`.
   - Append supply record before execution.
   - Call `run_current_mapped_step(envelope, graph, runner)`.

7. **Execution refused.**
   - If LM4R returns `record.ran is False`, append the `CurrentStepRecord`.
   - Stop with `stop_reason="execution_refused"`.
   - Do not ask provider again.

8. **Graph not advanced.**
   - If LM4R returns `record.ran is True` but `result.graph is graph`, append the
     `CurrentStepRecord`.
   - Stop with `stop_reason="graph_not_advanced"`.
   - This is loop safety only; LM4S does not classify the native seam result.

9. **Normal progress.**
   - Append record.
   - Set `graph = result.graph`.
   - Continue to the next loop iteration.

`steps_attempted` equals `len(records)`: the count of LM4R executions attempted, not the
count of provider calls.

---

## 8. Boundaries / Invariants

Allowed imports:

- `CurrentStepEnvelope`, `CurrentStepRecord`, `run_current_mapped_step` from
  `rook.agent.plan_graph_current_step_runner`;
- `SupportsLiveProducerNode` from `rook.agent.plan_graph_live_runner`;
- `PlanGraph` via `TYPE_CHECKING`;
- stdlib `copy`, `dataclasses`, `typing`, `collections.abc`.

Banned imports/references:

- `propose_next_node`, `revalidate_proposal`, `map_accepted_proposal_to_step`,
  `runnable_nodes`;
- `execute_mapped_step` (LM4S delegates to LM4R, not LM4Q directly);
- `apply_outcome`, `apply_verifier_step`, `apply_producer_result`,
  `apply_memory_bound_params`;
- `ProducerStep`, `VerifierStep`, `BindStep`, `Step`, `run_explicit_sequence`,
  `build_live_producer_record`;
- `select_template`;
- dispatcher/server/`base_agent`/LiteLLM/model imports.

Additional invariants:

- No `ok`, `passed`, `completed`, `should_continue`, or equivalent verdict field.
- No terminal `done` construction or graph-status completion check.
- No fallback from refused execution to a different envelope.
- No provider retry.
- No async provider support in LM4S.
- No hidden remapping: provider produces envelopes; LM4S does not inspect how.

---

## 9. Testing

Whole-branch implementation should add one production module plus focused tests. No live
Rhino test is required; LM4S composes LM4R with fake/provider-driven envelopes and uses
existing deterministic PlanGraph seams.

### Task 1 - Stream unit tests

`mcp_server/tests/test_plan_graph_current_step_stream.py`

Core cases:

- **max_steps_invalid:** `max_steps=0` returns `max_steps_invalid`; provider is not
  called; `final_graph is initial_graph`; records and supply records empty.
- **provider_halt:** provider returns `HALT` with a reason; append one supply record; no
  current-step record; final graph unchanged.
- **provider invalid taxonomy:** cover `supply_missing_envelope`, `halt_with_envelope`,
  `halt_missing_reason`, `unknown_supply_decision`, and `supply_result_invalid` from a
  provider returning `None` or `object()`; each appends a supply record and stops
  `provider_invalid`.
- **provider_error:** provider raises; append supply error record with class/message; no
  current-step record; final graph unchanged.
- **metadata copy statuses:** provider metadata absent/copied/invalid/copy_failed are
  recorded on supply records and do not affect stop semantics.
- **one supplied step:** provider supplies one envelope, then halt. Assert supply/record
  alignment, LM4R record preservation, graph threading, and final `provider_halt`.
- **execution_refused:** supplied envelope carries a refused mapping; append supply record
  and current-step record; stop `execution_refused`.
- **graph_not_advanced:** supplied envelope runs but LM4R returns the identical graph
  object with `record.ran is True`; append supply and current-step records; stop
  `graph_not_advanced`.
- **max_steps_reached:** provider supplies envelopes that advance the graph; with
  `max_steps=1`, stop before provider is called for a second step. Assert provider call
  count is exactly one and no final supply record is appended for budget exhaustion.
- **provider context tuples:** provider receives `tuple(records)` and
  `tuple(supply_records)`, not internal lists; second provider call sees the first record
  and first supply record.
- **import-boundary AST guard:** no selector/revalidator/mapper/LM4Q/lower seam/Step
  type/sequence/model/server imports or references.

### Task 2 - Chain stream guard

`mcp_server/tests/test_plan_graph_current_step_stream_chain.py`

Drive the real `gh_csharp_create_verify_repair_verify` template through multiple LM4S
iterations with a caller-owned provider that prepares artifacts outside LM4S:

1. Provider call 1 sees current graph with `create_script` ready and returns a mapped
   `ProducerStep("create_script")` envelope.
2. Provider call 2 sees current graph with `verify_create` ready and returns a mapped
   `VerifierStep("verify_create", "create_script")` envelope.
3. Provider call 3 returns `HALT` with reason `"chain_guard_stop_before_repair"` to keep
   LM4S short of a full scheduler/repair runner.

Assertions:

- `records` length is 2 and `supply_records` length is 3.
- Supply records 0 and 1 align with records 0 and 1.
- Final supply record is a non-executed `HALT`.
- Final graph has `repair_same_component` ready.
- LM4S did not apply terminal `done`.
- Provider call count is 3.

Honest scope: the test provider may call LM4N/O/P helpers outside LM4S to prepare
current-step artifacts. LM4S itself must not import those helpers.

---

## 10. Process / Gates

- Branch: `codex/lm4s-current-step-stream`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- Focused PlanGraph gate should include the new `test_plan_graph_current_step_stream*.py`
  files.
- No live acceptance gate for LM4S.
- After spec review approval, invoke `superpowers:writing-plans` before code.
- Stop at PR; no merge without explicit approval.

---

## 11. North-Star Fit

LM4S is the first multi-step pressure test for the north-star scaffold after LM4R. It
lets Rook collect an ordered trace of provider decisions and current-step execution
records, but still keeps planning, selection, revalidation, mapping, and currentness
outside the runner.

The model still does not remember the plan, mutate the graph directly, select the next
node, remap stale artifacts, fallback to another step, evaluate success, or own terminal
completion. LM4S is a bounded trace threader: caller supplies the current artifact, LM4S
records and delegates, and the step budget stops accidental unbounded loops.
