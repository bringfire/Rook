# Task 8 Steps 1-4 Report

## Scope

Implemented only the reviewed pre-transmission surface:

- guarded CLI with explicit `--transmit`;
- clean committed-HEAD and unused-run-root requirements;
- archived Gemini compiler/evaluator identity and exact LM9B-C bounds;
- separately recorded Planner identities and bounds;
- production scope guards;
- deterministic dry-run summary;
- frozen Planner and compiler-control snapshots carried into execution;
- no canonical attempt, real provider contact, result archive, or result report.

## RED Evidence

Initial focused run:

```text
11 failed, 139 passed
```

All failures were the intended missing Task 8 interfaces: CLI parsing, checkout
and run-root guards, scope guards, frozen-control assertions, and dry-run
behavior.

Follow-up RED cycles demonstrated:

```text
3 failed, 3 passed
```

for forbidden tool/name coverage and Planner-control drift, followed by:

```text
3 failed, 154 deselected
```

for proof-authority continuity across the pre-transmission/checkpoint boundary,
and one isolated failure proving compiler controls were still reread after
Planner contact.

The first real direct dry run then exposed an entry-point bootstrap failure
before argument handling (`ModuleNotFoundError` for the validation-kernel
package). A subprocess regression reproduced it before the import-path order
was corrected. No provider was contacted and no run root was created.

## GREEN Evidence

Final focused probe file:

```text
158 passed
```

Task 8 Step 3 exact groups:

```text
LM9B-P:                341 passed
LM9B-C/kernel adjacent: 100 passed
Python 3.10 py_compile: passed
git diff --check:       passed
```

Dry-run and fake-boundary tests prove provider construction/invocation does not
occur without `--transmit`, and guard failures occur before provider creation.

## Self-Review

- The CLI adds no semantic validation and calls the existing checkpoint/join
  functions unchanged in meaning.
- The transmitted path reauthenticates the same clean HEAD immediately before
  creating the run root or providers.
- Planner inputs and rendered request are frozen during pre-transmission review
  and carried directly into Checkpoint 1; no fixture reread can change them.
- The three LM9B-C implementation/evaluation controls are snapshotted and
  hashed before provider contact, then copied from the snapshot into handoff.
- Compiler and compiler-evaluator model identities are fixed to the archived
  Gemini profile at temperature `0.0`; all LM9B-C bounds are asserted exactly.
- Planner and Planner-evaluator identities remain separately recorded.
- Scope guards reject product-agent, Rhino, Grasshopper, broad execution-tool,
  and private validation-kernel imports/references; matched-control access is
  confined to the existing post-freeze comparison function.
- The run root must not exist and is created atomically with overwrite refusal.
- `execution_permitted` remains false and no live tool is exposed.
- No provider was contacted, no canonical attempt was run, and no scientific
  result evidence was created.

## Status

Committed as `521b3dac` with the plan message. A direct clean-HEAD dry run of
the canonical command without `--transmit` succeeded, printed the frozen
summary bound to that SHA, and left the canonical run root absent.

Task 8 Steps 1-4 are ready for independent pre-transmission review. Steps 5-6
remain deliberately unexecuted.

## Pre-Transmission Evidence Amendment

Pre-transmission review found three evidence-continuity gaps. This focused
amendment closed them without running the canonical attempt or contacting a
provider.

### RED Evidence

The focused TDD cycles reproduced each gap before implementation:

```text
2 failed, 2 passed
```

for missing `ProviderCallFailure` type and transport bytes in sealed Planner
attempt captures;

```text
2 failed
```

for LiteLLM responses with no choices or no assistant message escaping as
generic exceptions without the already serialized response evidence; and

```text
4 failed
```

for Checkpoint 1 seal failure escaping after Planner-only or evaluator contact
and for compiler providers being constructed before the failed checkpoint was
reported.

A self-review mutation then produced one additional intentional failure,
showing that a returned attempt could be reauthenticated with invented
exception fields.

### GREEN Evidence

Focused transport, tamper, seal-failure, stop-path, and CLI-reporting tests:

```text
11 passed
```

Final Task 8 Step 3 groups after the last production change:

```text
LM9B-P:                 353 passed
LM9B-C/kernel adjacent: 102 passed
Python 3.10 py_compile: passed
git diff --check:       passed
```

### Amendment Review

- Raised `ProviderCallFailure` attempts now retain the exact sanitized raw
  request, serialized raw error, and specific failure type already supplied by
  the provider boundary. Generic exceptions cannot invent those bytes.
- The closed archive verifier rejects missing, extra, contradictory, or
  reauthenticated transport/exception evidence; raw request, raw error, and
  failure-type tampering have direct regressions.
- The shared LM9B-C LiteLLM adapter now represents malformed response shapes
  discovered after response serialization with the existing evidence-bearing
  `ProviderCallFailure`. Compiler and evaluator model identities, temperature,
  request rendering, tool schema, bounds, session behavior, evaluator logic,
  and decision logic remain held fixed. This is transport-evidence hardening
  only.
- A Checkpoint 1 seal, identity, or write failure after provider contact now
  yields an unsealed in-memory `probe_inconclusive` result retaining every
  observed Planner/evaluator attempt. It performs no retry and does not enter
  the join or construct compiler providers. Pre-contact failures still raise
  through their original boundary.
- CLI output can report the unsealed control failure without claiming a
  complete archive or fabricating a seal.
- Dry-run and fake-provider tests continue to prove zero real contact without
  explicit transmission. No canonical attempt, result archive, or scientific
  result report was created.

## Provider Construction Amendment

Final pre-transmission review found that provider-adapter construction could
fail outside both provider-attempt evidence and aggregate result handling. The
focused correction adds one in-memory terminal control-failure result; it does
not add or alter a production schema, archive, seal, or provider protocol.

### RED And GREEN Evidence

The initial role-parameterized test reproduced all four escaping failures:

```text
5 failed
```

The four constructor roles and deterministic CLI rendering then passed:

```text
5 passed
```

Final full gates after the production change:

```text
LM9B-P:                 358 passed
LM9B-C/kernel adjacent: 102 passed
Python 3.10 py_compile: passed
git diff --check:       passed
```

### Boundary Review

- Planner or Planner-evaluator constructor failure records the exact role,
  construction locus, exception type, and bounded message as aggregate
  `inconclusive`. It creates no Planner checkpoint or seal, calls no provider,
  requests no later constructor, and performs no retry.
- Compiler or compiler-evaluator constructor failure occurs only after the
  contacted Checkpoint 1 has completed and sealed. The in-memory terminal
  result retains that exact checkpoint and its Planner/evaluator attempt
  objects, creates no joined aggregate, calls no compiler provider, requests no
  later constructor, and performs no retry.
- Compiler-evaluator construction remains before compiler contact, preserving
  the reviewed execution order rather than changing the experiment.
- The already-created run root remains single-use after any constructor
  failure. A second execution refuses overwrite before requesting another
  constructor.
- CLI output handles the terminal variant directly and prints a null
  Checkpoint 1 only when no checkpoint exists. It does not fabricate a
  checkpoint, archive, joined aggregate, provider attempt, or seal.
- The canonical attempt remains unrun. All provider activity in verification
  used deterministic fakes; no real provider was contacted.

## Task 8 Step 6 Completion

The one canonical attempt ran once at `9959650f` and was not rerun, repaired,
or retransmitted. Its terminal observation was:

```text
Checkpoint 1: probe_inconclusive
Checkpoint 2: not_evaluated
aggregate: probe_inconclusive
Planner attempts: 1
Planner model turns: 0
Planner evaluator attempts: 0
compiler attempts: 0
execution: false
```

LiteLLM rejected the Planner call with an evidence-bearing
`InternalServerError` reporting missing OpenAI credentials. This environmental
provider-configuration failure occurred before model inference, so neither the
Planner-authorship nor joined-transfer counter-hypothesis was evaluated.

Step 6 verified the complete checkpoint archive with the production verifier
and independently recomputed the joined aggregate's exact file closure, record
hash, canonical identity, and checkpoint binding:

```text
checkpoint aggregate:
  sha256:ca782b786fe9f07072e50d07264623cfd0a825a05caf6794fb78be8bf39003cd
joined aggregate:
  sha256:8777701ebdd7a591f4d848964459c454f46a24821cf7cd04958edcff193b0acb
LM9B-P: 358 passed
LM9B-C/kernel adjacent: 102 passed
Python 3.10 py_compile: passed
git diff --check: passed
```

No final recipe existed, so R01 comparison was not applicable and was not
performed. Neither the canonical path nor Step 6 read an R01 recipe artifact.

The 33 evidence files and result report were committed without modifying the
attempt as `ab026a66` (`docs(lm9b): record planner recipe transfer result`). A
scoped repository transport attribute preserves exact evidence bytes across
Git checkouts without entering either scientific seal.

Task 8 is complete. Any subsequent Planner observation must use a new attempt
identity, unused run root, and newly reviewed committed SHA; it is not a retry
of this canonical attempt.
