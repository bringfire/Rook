# ChatRunner Headless Qualification Recorder Design

**Date:** 2026-08-04
**Baseline:** `9a963e823632a160e1cfaf4e70660f8646da28fa`
**Status:** Proposed

## Purpose

Add the smallest durable local evidence surface needed to qualify the existing
`ChatRunner` one explicitly selected live row at a time.

The operator consumes the existing asynchronous `ChatEvent` stream and writes
the observed events to one append-only local JSONL file. It does not create a
new agent runner, tool path, event protocol, conversation store, trace service,
or outcome system.

One independent product defect is closed first:

```text
no model text
+ no model tool calls
-> no empty assistant-history append
-> one existing Chat error event
-> normal ChatRunner cleanup and done event
```

The two changes are sequential slices with separate ownership:

1. the empty-completion correction in `ChatRunner`;
2. the operator-only headless qualification recorder.

## Baseline and observed evidence gap

The baseline includes the canonical MCP capability-parity bridge merged through
PR #545. The focused no-contact baseline is:

```text
166 passed
11 pre-existing warnings
```

The retained live evidence under:

```text
C:/Users/bring/AppData/Local/Rook/traces/
qwen-unskilled-row-points-20260804T211613/
```

shows that the existing generic ChatRunner loop can drive a capable local model
through progressive discovery and the canonical MCP gateway to a correct live
Grasshopper definition. It also exposes the missing evidence boundary:

- the Grasshopper session recorder retained three canonical `gh_edit`
  mutations;
- the panel transcript rendered many earlier failed direct `gh_edit` calls but
  truncated their parameters;
- the service log retained their failure responses but not their exact
  arguments; and
- two later requests ended with tiny successful HTTP responses and no logged
  LLM exception, consistent with ChatRunner's current silent empty-completion
  behavior.

The needed evidence already crosses the public Python boundary as `ChatEvent`
objects. `tool_start` is yielded before dispatch, and `tool_result` is yielded
after dispatch. An external async-generator consumer can therefore persist the
exact existing boundary without changing ChatRunner.

## Architectural decision

Use one operator-only script:

```text
one reviewed row JSON
-> validate and freeze model, intent, skill, and Rhino target
-> open and flush one JSONL trace
-> existing PromptBuilder and ChatRunner
-> existing direct ToolDispatcher and canonical MCP gateway
-> consume, write, and flush each existing ChatEvent
-> optionally perform the one fixed final inspection required below
-> finish and close the trace
-> bounded stdout result
```

Rejected alternatives are:

- adding recording hooks to ChatRunner;
- proxying or recording the aiohttp stream;
- modifying the HTTP event vocabulary;
- extracting or promoting the private live-smoke flight recorder;
- wrapping both tool executors with another targeting or dispatch policy; and
- reconstructing provider wire traffic or hidden reasoning.

The existing live-smoke recorder supplies a proven local pattern—exclusive
creation, ordered JSONL, immediate flush, bounded rows, and truthful incomplete
prefixes—but its implementation remains private and is not imported, extracted,
or copied wholesale.

## Slice A: empty-completion correction

### Existing defect

After a model stream completes, `ChatRunner.run_turn()` currently builds and
appends an assistant message before checking whether the response has tool
calls. When both text and tool calls are absent, it appends an empty assistant
message and exits the model loop silently. Cleanup still emits `done`.

### Required behavior

For exactly:

```text
full_text == ""
AND tool_calls_list == []
```

ChatRunner must:

1. append no assistant message for that response;
2. emit exactly one existing `ChatEvent(type="error")` with a fixed code-owned
   message;
3. end the model loop without another model call;
4. retain the already appended user message;
5. perform its existing `finally` cleanup;
6. clear the active run ID; and
7. emit the ordinary `done` event with existing usage and timing fields.

This does not change the HTTP vocabulary, server streaming, panel rendering,
conversation persistence, tool loop, exception formatting, cancellation, or
any nonempty model response.

### Required regressions

- Empty text plus no tool calls emits `error`, then `done`.
- It appends no empty assistant history entry.
- It performs exactly one model call and zero tool calls.
- The active run ID is cleared normally.
- A normal text-only completion is unchanged.
- A tool-call response with no accompanying text is unchanged.

## Slice B: operator row ownership

### Sole input

The operator accepts exactly one command-line argument: the path to one reviewed
UTF-8 JSON row. Missing or additional arguments refuse before trace creation or
external contact.

The JSON object is closed and contains exactly:

```json
{
  "model": "ollama_chat/qwen3.6:35b",
  "api_base": "http://127.0.0.1:11434",
  "intent": "<exact user intent>",
  "skill_path": "C:/UDEV/Rook/.agents/skills/execute-grasshopper/SKILL.md",
  "rhino_target": {
    "port": 0,
    "process_id": 0,
    "document_serial_number": 0
  }
}
```

The displayed zero target values are structural placeholders only. Admission
requires exact built-in positive integers.

Admission rules are:

- reject malformed UTF-8, malformed JSON, duplicate keys, unknown keys, missing
  keys, and non-exact field types;
- `model` is nonblank and retained exactly;
- `api_base` is an explicit credential-free loopback HTTP or HTTPS URL;
- reject URL user information, query, and fragment components;
- `intent` is nonblank and retained exactly, including its interior and edge
  whitespace;
- `skill_path` resolves to one readable regular file and is retained as the
  resolved absolute path;
- each Rhino target value is an exact positive integer; and
- the fully admitted `run_started` row must fit the recorder's row bound.

The row is the sole authority for these values. No CLI flag, environment
variable, model profile, model picker, persona model resolution, API-base
detection, active Rhino target, or discovery fallback may replace or override
an admitted field.

"No profile resolution" applies to model and API-route selection. The canonical
MCP gateway continues using its existing active MCP profile and policy
intersection. The recorder observes that profile; it does not replace it.

## Model and prompt custody

The operator creates one ephemeral `Conversation` with:

- the exact admitted model;
- the exact admitted API base;
- a code-owned qualification conversation ID;
- code-owned persona `architect`;
- the admitted document serial number; and
- initially empty in-memory message history.

It does not use model profile resolution, chat model override resolution, or
model-picker state.

The caller-supplied system prompt is code-owned composition of:

1. `PromptBuilder.build_system("architect")`; and
2. the exact decoded reviewed skill body under one fixed separator.

The trace retains:

- the resolved skill path;
- SHA-256 of the exact skill file bytes; and
- SHA-256 of the exact caller-supplied `system_prompt` string passed to
  `ChatRunner.run_turn()`.

It does not call that hash the complete or effective model prompt. ChatRunner
adds verified runtime facts and the dynamic tool section internally on every
round. No hook is added to observe or hash those internal prompt variants.

The exact admitted intent is passed unchanged as `user_message`.

## Runtime and repository identity

Before external contact, `run_started` records ordinary local identity facts:

- qualification-row absolute path and SHA-256;
- Git HEAD and clean/dirty status;
- Python executable and version;
- resolved Rook module path;
- installed LiteLLM version;
- exact selected model and API base;
- the active MCP profile observed at startup;
- exact admitted intent;
- skill path and hashes described above; and
- the complete admitted Rhino target triple.

These are diagnostic identity facts, not provenance proofs. The trace contains
sensitive model/tool content and is disposable local telemetry.

## Rhino target custody

The complete frozen target is:

```text
port
process_id
document_serial_number
```

Before starting the async generator, the operator:

1. stores the existing process-local active target for later restoration;
2. sets the existing active target to the admitted port and process ID;
3. enters the existing `rhino_request_context()` with the complete triple; and
4. verifies the active target and request context equal the admitted values.

The same context remains active across ChatRunner, all direct and canonical tool
calls, and the final inspection. The existing direct ToolDispatcher is
constructed with the admitted port. The existing canonical gateway executor is
constructed once and the same callable is supplied to ChatRunner and used for
final inspection.

No new executor wrapper, target registry, target-selection mechanism, or gateway
policy is introduced.

### Generator-boundary enforcement

For every yielded Chat event:

```text
receive event
-> write and flush exact event
-> verify active target and Rhino request context
-> inspect tool_start when applicable
-> request the next event
```

Requesting the next async-generator event permits ChatRunner to proceed past a
yielded `tool_start` and enter dispatch. Therefore target inspection occurs
before dispatch without changing either executor.

For direct tool events, inspect only:

- the exact tool name; and
- top-level `port`, `session`, and `documentSerialNumber` parameters.

For `rook_tools_call`, inspect only:

- `params.name`;
- `params.arguments.port`;
- `params.arguments.session`; and
- `params.arguments.documentSerialNumber`.

Refuse `rhino_set_active_instance` and `rhino_clear_active_instance` whether
called directly or through `rook_tools_call`.

Do not recursively scan arbitrary payloads. A nested domain value named
`session`, `port`, or `documentSerialNumber` outside the exact routing positions
has no targeting meaning here.

When forbidden targeting is observed:

1. the already flushed `tool_start` remains exact evidence;
2. write and flush one `qualification_refusal` row with a fixed reason;
3. close the async generator while it is still suspended;
4. permit zero dispatch for that tool;
5. perform no final snapshot; and
6. emit no `run_finished`.

After a returned event, target or context disagreement is recorded as
`target_drift` when the recorder is still healthy. The generator is closed and
no subsequent model, tool, or inspection call occurs.

## JSONL contract

Each complete row has exactly:

```json
{
  "sequence": 1,
  "recorded_at_utc": "2026-08-04T22:00:00.000000Z",
  "kind": "run_started",
  "payload": {}
}
```

Serialization rules are:

- UTF-8;
- `ensure_ascii=True`;
- `allow_nan=False`;
- compact separators;
- exactly one trailing newline;
- monotonically increasing sequence beginning at `1`; and
- sequence advances only after the complete row is written and flushed.

The closed row vocabulary is:

```text
run_started
chat_event
qualification_refusal
stream_exception
run_cancelled
target_drift
snapshot_request
snapshot_result
run_finished
```

For a `chat_event` row, `payload` is exactly `ChatEvent.to_dict()` with no
projection, redaction, augmentation, interpretation, or additional wrapper.
This retains exact adapter-boundary values serialized into JSON, not provider
wire bytes or hidden reasoning.

`stream_exception` records the ordinary exception type and message without a
traceback. It is local sensitive telemetry and is never copied to stdout.

`run_finished` proves only that the planned row sequence through
`run_finished` was completely written and flushed. It does not prove successful
file close, overall operator success, that the model satisfied the intent, that
tools succeeded, or that the final snapshot was healthy. Its payload reports
directly observed facts, including:

- normal Chat stream exhaustion;
- `done` observed;
- whether one or more Chat `error` events were observed;
- final `done` usage when present;
- final inspection attempted;
- final inspection result recorded; and
- total operator elapsed time.

It does not convert those facts into a new task outcome taxonomy.

The absence of `run_finished` means the trace is incomplete.

## File lifecycle and byte bounds

The operator creates one file beneath:

```text
%LOCALAPPDATA%/Rook/traces/
```

The filename uses a UTC timestamp, process ID, and a small random collision
suffix. The path is not configurable by the row or CLI.

The file is opened with exclusive binary creation and unbuffered writes. The
operator never seeks, truncates, reopens, retries, or repairs it.

Before any model, Rhino, Grasshopper, provider, Ollama, or MCP contact, the
operator must successfully:

1. create the trace directory;
2. exclusively open the file;
3. serialize `run_started`;
4. write the complete row; and
5. flush it.

Failure at any of those steps produces zero external calls.

Exact limits are:

```text
maximum complete encoded row including newline: 256 KiB
maximum actual bytes written to the trace:       4 MiB
```

Serialization and both limits are checked before a write. Actual successful
write counts own total-file accounting.

There is:

- no truncation;
- no retry;
- no reopen;
- no reserved tail;
- no rejection row;
- no checksum or post-write verification;
- no `fsync` claim; and
- no repair of a partial final row.

Serialization failure, row overflow, total overflow, write exception, invalid
write count, short write, or flush failure stops immediately.

If a `tool_start` row fails, the generator remains suspended and that tool is
never dispatched. If a `tool_result` row fails, the completed call remains an
observed fact through its preceding `tool_start`, but closing the generator
prevents every subsequent model, tool, or inspection call.

An OS short write may leave a partial final JSON row. Count the actual bytes
written, make no repair attempt, and stop.

Closing is attempted at most once. A close failure makes the operator report
`trace_write_failed` even if `run_finished` was previously flushed.

## Final qualification inspection

Exactly one final inspection is eligible under the direct equation:

```text
trace healthy
AND Chat stream exhausted normally
AND done observed
AND frozen active target unchanged
AND frozen Rhino request context unchanged
```

An emitted Chat `error` followed by normal exhaustion and `done` remains
eligible.

When eligible:

1. serialize, write, and flush `snapshot_request` containing exactly:

   ```json
   {
     "name": "gh_snapshot",
     "arguments": {
       "include_data": false,
       "max_preview_items": 0
     }
   }
   ```

2. invoke the same canonical executor supplied to ChatRunner as:

   ```text
   rook_tools_call(gh_snapshot)
   ```

3. verify the active target and request context again; and
4. write and flush the exact returned value as `snapshot_result`.

The inspection is a qualification operation, not a Chat event. It does not
enter conversation history and does not alter the HTTP vocabulary.

A returned operational failure is still an exact `snapshot_result` and may be
followed by `run_finished`. It is not reclassified.

Recorder failure, stream exception, cancellation, missing `done`, targeting
refusal, or context drift before inspection means zero inspection calls.

If the final call begins and then raises or context drifts, the already flushed
`snapshot_request` truthfully proves the call boundary was entered. No
`snapshot_result` or `run_finished` is emitted.

No second snapshot, retry, cleanup, or fallback is permitted.

## Stdout contract

Stdout contains one bounded JSON object with only:

- `status`, from a small closed vocabulary such as `completed`, `refused`, or
  `trace_write_failed`; and
- `trace_path`, as the absolute path or `null` when no file exists.

Stdout never contains intent, skill content, model responses, tool parameters,
tool results, snapshot content, exception text, credentials, or trace excerpts.
Stderr remains empty for ordinary bounded refusals and trace failures.

## No-contact test strategy

### Empty completion

- empty response emits `error` then `done`;
- no empty assistant message is appended;
- normal text and tool-call completions remain unchanged; and
- cleanup and exact call counts remain correct.

### Input and identity

- exactly one row-file argument is required;
- duplicate keys, unknown keys, missing keys, bad types, blank fields, invalid
  targets, and credential-bearing or non-loopback API bases refuse before
  contact;
- model and API base enter the ephemeral Conversation exactly;
- environment/profile model values cannot override them;
- skill bytes, path, and hashes are exact; and
- the recorded prompt hash covers only the caller-supplied prompt.

### Event recording

- every fake `ChatEvent.to_dict()` is retained exactly and in order;
- sequence is monotonic;
- UTC timestamps are wall-clock observations and are not required to be
  monotonic;
- elapsed duration uses a monotonic clock;
- `tool_start` is flushed before the fake generator proceeds to simulated
  dispatch;
- `tool_result`, Chat errors, `done` usage, and timing are retained;
- normal completion with Chat errors may still finish; and
- no content reaches stdout.

One no-contact vertical uses the real `ChatRunner` with a fake LiteLLM stream,
fake direct executor, and one fake canonical executor. The model-authored first
round calls `rook_tools_call`; the second round returns ordinary text. The test
then performs the operator-owned final snapshot through the same canonical
callable. It proves:

- the real ChatRunner produces the existing ordered `tool_start`, `tool_result`,
  text, and `done` events;
- those exact events reach the JSONL recorder unchanged;
- the fake direct executor is not substituted for the gateway call;
- the same canonical callable handles both the model-authored gateway call and
  the fixed final snapshot; and
- all model, direct-tool, canonical-tool, Rhino, and Grasshopper effects remain
  causal fakes with no external contact.

### Targeting

- direct targeting fields refuse before fake dispatch;
- the exact canonical nested targeting fields refuse before fake dispatch;
- target-control tools refuse on both surfaces;
- unrelated nested domain fields are not recursively rejected;
- active-target or context drift stops before the next generator request; and
- the previous active target is restored during operator cleanup.

### Recorder failures

- serialization, row-size, total-size, write, short-write, flush, and close
  failures follow the equations above;
- a partial short-written row is retained without repair;
- failure before `tool_start` flush causes zero dispatch;
- failure after a completed tool call causes zero later calls; and
- incomplete traces contain no `run_finished` unless it was already flushed
  before a close failure.

### Final inspection

- it uses the same injected canonical executor and frozen context;
- it occurs once only after healthy normal exhaustion with `done`;
- Chat error plus `done` remains eligible;
- each disqualifying condition causes zero inspection calls;
- request and result are separate qualification rows; and
- an operationally failed returned snapshot may still be followed by
  `run_finished`.

All tests use causal fake async generators, streams, clocks, executors, and
contexts. They contact no model, provider, Ollama, MCP service, Rhino, or
Grasshopper.

## Exact implementation scope

Slice A changes only:

```text
mcp_server/src/rook/agent/chat/chat_runner.py
mcp_server/tests/test_chat_runner.py
```

Slice B changes only:

```text
scripts/chatrunner_headless_qualification.py
mcp_server/tests/test_chatrunner_headless_qualification.py
```

The specification and later one-purpose plans are documentation only. The two
implementation slices remain separately committed and reviewed.

## Explicit non-claims

This design does not claim or add:

- task success scoring;
- semantic-fidelity evaluation;
- automatic skill selection;
- model or API-route discovery;
- general Worker delegation;
- deterministic semantic-graph execution;
- provider wire capture or hidden-reasoning access;
- replay or resumption;
- conversation durability;
- a trace database, index, retention manager, archive, or system of record;
- a new receipt or outcome taxonomy;
- a product UI, button, route, or HTTP event;
- repeatability across models or intents; or
- permission for a live qualification run.

Live contact remains ineligible until both implementation slices are planned,
implemented, independently reviewed, merged, deployed from a clean merge SHA,
and separately authorized for one reviewed row.

## Anti-quagmire stop

Every mandatory implementation review reports:

- nonblank production lines in the operator script;
- additions in each changed production file; and
- cumulative production additions across both sequential slices.

The recorder returns for renewed design review before further implementation if
the operator script would exceed 350 nonblank lines or if the recorder would
require any production module beyond its one operator script. No safety or
scope exception is authorized in advance.

Stop before implementation expansion if the work requires:

- changing ChatRunner's execution loop beyond the exact empty-completion branch;
- adding a ChatRunner observer or recorder hook;
- changing ToolDispatcher, the canonical gateway, targeting, HTTP streaming, or
  conversation persistence;
- adding an executor wrapper or parallel targeting policy;
- adding more than the two files assigned to either implementation slice;
- extracting the private flight recorder;
- reconstructing raw provider traffic; or
- introducing a generalized observability, evaluation, or archive abstraction.

Such a finding is a scope decision, not authorization to add abstractions.
