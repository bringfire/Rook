# Minimal Intent/Worker Live Flight Recorder Design

**Date:** 2026-07-30

**Status:** Approved design; specification-only

**Base:** `619ca24e8a34cb83a02db828d37d1dc7a3c8d2e3`

## 1. Purpose

The real compile smoke currently reports a bounded operator summary but does not
retain the local values that produced it. The first corrected live observation
reached Rhino, prepared a fresh Grasshopper document, admitted one Planner
draft, and dispatched `gh_create_csharp_script`, then returned:

```text
create / selector_halt:none_ready
```

The summary could not show the raw create response, extracted receipt,
producer outcome, graph transition, or ready-node set. The next slice adds one
private append-only JSONL flight recorder to the existing operator script so a
local operator can diagnose that boundary without changing product behavior.

The target diagnostic chain is:

```text
raw create response
-> returned normalized receipt
-> returned producer outcome
-> returned graph node states
-> returned ready-node set
-> selector_halt:none_ready
```

The trace is diagnostic telemetry. Existing typed receipts, native records,
graphs, and terminal results remain the only behavioral authority.

## 2. Scope and non-goals

Implementation remains private to:

- `scripts/minimal_intent_worker_real_compile_smoke.py`; and
- `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`.

The specification and later plan are the only additional files. Product
modules remain unchanged.

This slice does not add:

- a shared tracing API, observer callback, registry, database, or service;
- a manifest, checksums, fingerprints, sealing, public verification, or
  authority claims;
- retries, fallback, alternate models, extra tools, or changed model behavior;
- HTTP-wire capture, headers, credentials, or LiteLLM internals;
- a CLI path override, retention manager, trace reader, or replay facility;
- a new attempt or evidence-lifecycle vocabulary; or
- any product registration or synthetic-smoke behavior.

No provider, worker box, Rhino, or Grasshopper contact is authorized during
specification, planning, implementation, or review.

## 3. Approach

Use one private recorder plus transparent script-local boundary wrappers.

```text
record request + flush
-> delegate exactly once
-> record raw response or exception + flush
-> return or raise the original value unchanged
```

Transparency holds only while trace writes succeed. A trace failure after a
completed call supersedes return or exception propagation, preserves the call
as completed in local accounting, and prevents every subsequent external call.

Product observer hooks are deliberately excluded. Returned-record projections
are appended only after the existing integration function returns normally.
They are never backdated or presented as real-time observations.

## 4. File creation and ownership

The exact live flag remains the only route into live behavior. After argument
admission and before role resolution, discovery, transport construction, or
tool contact, the script creates one file under:

```text
%LOCALAPPDATA%\Rook\traces\
```

The filename contains a UTC timestamp, process ID, and a small random collision
suffix. This is filename uniqueness only, not an attempt identity. The path is
not caller-configurable.

The file is opened with exclusive creation in UTF-8 text/binary-compatible
append order. The recorder never seeks, rewrites, truncates, or reopens it.
One recorder instance owns the file until close.

If `%LOCALAPPDATA%`, directory creation, exclusive open, `run_started` write,
or its flush fails, the smoke refuses with `trace_write_failed` and zero
external calls. If a file was created, stdout reports its absolute path even
when its header was not completed; otherwise `trace_path` is `null`.

## 5. JSONL row contract

Every successful row has exactly:

```json
{
  "sequence": 1,
  "recorded_at_utc": "2026-07-30T21:30:00.123456Z",
  "event": "run_started",
  "payload": {}
}
```

Rules:

- `sequence` starts at `1` and increases monotonically across preparation,
  Planner, execution tools, and Worker.
- Sequence advances only after the complete row is written and flushed.
- JSON uses UTF-8, `ensure_ascii=True`, `allow_nan=False`, compact separators,
  and exactly one trailing newline.
- Captured payloads are exact adapter-boundary values serialized into JSON.
  They are not original HTTP wire bytes.
- Each row is flushed immediately with the owned file handle.
- No `fsync`, checksum, post-write verification, or durability claim is added.

The private event vocabulary is closed:

```text
run_started
tool_request
tool_response
tool_exception
planner_request
planner_response
planner_exception
worker_request
worker_response
worker_exception
planner_admission
compiled_workflow
native_step_projection
final_native_result
handoff_raised
event_rejected
event_serialization_failed
run_finished
```

`run_started` contains only the fixed intent, fixed profile name, and the two
code-owned expected model identities. It does not claim that profile resolution,
discovery, or contact succeeded. `run_finished` contains the bounded final
operator status/reason and safely known call counts; detailed native fields
remain in `final_native_result` when that owning result exists.

`run_finished` appears only when the logical event stream is complete: every
preceding event and the final native projection were written successfully. It
is written and flushed last. Close must then succeed before stdout may report
an ordinarily successful operator result. A close failure after that flush may
leave `run_finished` in the file, but the operator still reports
`trace_write_failed`; the row claims logical event-stream completion, not close
or durability success. A stream that fails before `run_finished` ends at its
last successfully flushed row and never receives the event later.

## 6. Bounds

Constants are private and code-owned:

```text
maximum complete JSONL row, including newline: 256 KiB
maximum actual bytes written per trace:         4 MiB
reserved rejection tail:                       4 KiB
maximum exception-message JSON string:         16 KiB
```

Normal rows may consume at most `4 MiB - 4 KiB`. Only one rejection row may
consume the 4 KiB reserve. Total accounting uses the actual encoded bytes
successfully written.

The exception-message limit is measured from the exact `ensure_ascii=True`
JSON-string encoding, not from direct UTF-8 encoding. This admits valid escaped
surrogates without an encoding crash.

There is no truncation, compression, substitute hash, or lossy summary inside
the trace.

If an attempted event cannot be serialized, exceeds the complete-row bound,
would exceed the normal total allowance, or carries an over-limit exception
message, the recorder writes and flushes one small rejection row. It contains:

- the attempted event name; and
- exactly one fixed rejection reason:
  `json_serialization_failed`, `row_size_exceeded`,
  `total_size_exceeded`, or `exception_message_size_exceeded`.

The trace is then incomplete and no further external call occurs. If the
rejection row itself cannot be written or flushed, the partial trace simply
ends at the preceding successfully flushed row.

## 7. Boundary wrappers

### 7.1 Tool boundaries

Preparation uses a private recording dispatcher wrapper. Existing restricted
execution uses the same recorder around the already-approved restricted tool
executor. Every tool event includes:

```text
phase: preparation | execution
call_index: positive integer local to that phase
tool_name
```

Request events additionally contain the exact parameter object. Response
events contain the exact returned object before interpretation. Exception
events contain the exact exception class name and bounded local
`exception_message`, without a traceback.

The existing allowed contact sequence and port restrictions do not change:

```text
preparation: gh_status -> gh_document_new -> gh_status
execution:   gh_create_csharp_script -> optional gh_update_script
```

### 7.2 Planner and Worker boundaries

Each existing transport is wrapped independently. Model events include:

```text
role: planner | worker
call_index: positive integer local to that role
```

The request event contains the exact prompt artifact supplied to `send()`. The
response event contains the exact returned local string before parsing. The
exception event contains exception type and bounded message before the original
exception is re-raised.

No provider kwargs, API headers, credentials, HTTP response object, token
telemetry, or LiteLLM internal metadata enters the trace.

## 8. Write-failure semantics

Every request event must flush before its call. Every response or exception
event must flush before any subsequent call.

```text
request trace failure
-> delegate is not called
-> trace_write_failed

response/exception trace failure
-> completed call remains truthfully counted
-> original return/exception is not propagated
-> no next external call
-> trace_write_failed
```

If an ordinary wrapped exception is recorded successfully, the wrapper raises
the original exception object unchanged. If a return value is recorded
successfully, the wrapper returns the original object unchanged.

OS write/flush failures may make a rejection row impossible. The recorder does
not attempt repair, reopen, retry, or a second file. The existing bounded stdout
summary reports `trace_write_failed` without exception text.

If `run_finished` flush or final close fails after a native result exists,
stdout preserves the native stage, safely projected reason, and wrapper/native
call counts already known at that boundary. Fields not established by the
returned objects remain `null`. In every such case:

```text
operator_status = failed
operator_reason = trace_write_failed
```

The run is never reported as successfully traced.

## 9. Returned-record projections

Returned projections are explicit script-local functions over exact existing
objects. They do not rerun compilation, receipt extraction, graph reduction,
selection, or worker interpretation.

### 9.1 Planner admission

Append `planner_admission` only when
`MinimalIntentWorkerIntegrationResult.validated_draft` exists. Its payload is
the exact four admitted draft fields projected from that typed object.

A Planner adapter or draft-admission stop produces no placeholder admitted
draft, workflow, receipt, or graph event.

### 9.2 Compiled workflow

Append `compiled_workflow` only when `handoff_result` exists. Project the
existing `WorkflowCompileRecord` fields required to identify the compiled
workflow plus the scaffold's ordered node IDs, terminal IDs, selected template,
provider, compiler, and `max_steps`. Do not serialize the full graph topology or
reconstruct a contract.

### 9.3 Native steps and graph

Append one `native_step_projection` for each existing returned
`CurrentStepRecord`. Pair it only with the supply record at the same execution
index and the graph returned by that step. Each projection contains, where
owned by the record:

- accepted node ID, execution kind, ran/failure fields;
- producer/verifier application, outcome, and reason fields;
- the normalized receipt retained in returned node evidence;
- returned node IDs and statuses after that step;
- ready-node IDs from the existing `runnable_nodes()` function; and
- the corresponding execution-supply decision and reason.

A terminal/control supply record that has no executed step is not forced into
a step projection. The last such existing record's decision and reason are
projected by `final_native_result` alongside the final graph statuses and ready
set.

For the observed returned stop, the deterministic projection must show:

```text
raw gh_create_csharp_script response
-> create record receipt
-> create producer_applied / producer_outcome_status / producer_reason
-> returned graph node statuses
-> ready_node_ids == []
-> terminal supply reason == selector_halt:none_ready
```

The trace does not claim that these post-return projection events occurred at
the earlier logical time. Their event sequence reflects when the script learned
and wrote them.

### 9.4 Worker and final result

Worker request/response events exist only if the Worker transport is actually
called. Returned worker status is projected only when its native adapter record
exists.

`final_native_result` contains the exact returned integration terminal stage and
reason plus bounded call counts already derivable from the script's wrappers
and native records.

If the integration raises before returning, append `handoff_raised` with the
exception type and bounded message. Retain prior request/response/exception
events, but emit no admitted-draft, scaffold, receipt, graph, or terminal-result
claim that lacks its owning returned object.

## 10. Stdout contract

The existing bounded one-line JSON summary remains the operator interface. Add
only:

```text
trace_path: absolute local path | null
```

No prompt, model response, worker code, rationale, tool parameters, raw tool
response, receipt, diagnostic, exception message, credential, or trace payload
appears on stdout.

Live invocations report the trace path whenever a file was successfully
created, including incomplete traces. Non-live argument refusals create no file
and report `trace_path = null`.

## 11. Deterministic test strategy

All tests remain offline and inject local fakes through existing script seams.
No test launches the script with a real live transport.

### 11.1 Recorder mechanics

Prove:

- exclusive file creation and path placement;
- one global increasing sequence;
- exact JSON serialization and newline accounting;
- flush after every row and close before success output;
- 256 KiB exact-bound and bound-plus-one behavior;
- 4 MiB actual-byte accounting with an exact 4 KiB reserve;
- one rejection row maximum;
- serialization failure and all fixed rejection reasons;
- escaped-surrogate exception-message measurement through
  `ensure_ascii=True` JSON-string encoding;
- ordinary write/flush/close failure behavior; and
- absence of `run_finished` from every incomplete trace.

### 11.2 Wrapper transparency and ordering

For preparation, execution, Planner, and Worker wrappers, prove:

- request row flush precedes delegate entry;
- delegate is called exactly once;
- response/exception row flush precedes any next call;
- original result identity and original exception identity survive only when
  recording succeeds;
- request failure yields zero delegate calls;
- response/exception recording failure counts the completed call and blocks the
  next call;
- tool `phase` and phase-local call index are exact; and
- model role and role-local call index are exact.

### 11.3 Returned stop witness

Run the existing deterministic integration with a create response that retains
a receipt but projects the producer into a state with no ready successor.
Require the native result to be exactly:

```text
terminal_stage = create
terminal_reason = selector_halt:none_ready
worker calls = 0
```

Read the JSONL file and prove the complete diagnostic chain is present and
ordered:

```text
tool_response(raw create)
native_step_projection(normalized receipt, producer outcome,
                       node statuses, empty ready set)
final_native_result(selector_halt:none_ready)
run_finished
```

### 11.4 Ownership and safe output

Prove that Planner rejection, draft rejection, early create stop, Worker stop,
integration exception, and trace failure emit only projections whose owning
objects exist. Prove stdout contains the existing safe summary plus
`trace_path` and none of the captured local content.

Finally rerun the complete existing focused seam. Implementation and review do
not execute `--execute-live` against a real system.

## 12. Stop condition

This slice ends when the private recorder and deterministic tests are merged.
A later live retry requires separate authorization. The recorder remains private
until a second product path demonstrates a concrete need for shared tracing.
