# Prime JSON Event-Stream Storage Efficiency

**Status:** USER-APPROVED; INDEPENDENT REVIEW PENDING; IMPLEMENTATION UNSTARTED AND UNQUALIFIED

**Date:** 2026-08-20

**Rook baseline:** `dc18970a10492e7219e42dd77b6ecaf2708bc307`

**Prime baseline:** `739400844f8f3f280414b0c7b9c65797208815d3`

**Triggering specimen:**
`C:/UDEV/RookEvidence/2026-08-20-qwen38-multimodal-vessel-massing-v5/MV1/operator/prime.jsonl`

**Triggering specimen SHA-256:**
`F79FF8A329993C9770B7E103B3F10620A6E118C5AD58E6184E9777EDFBFCAA3B`

## Purpose

Replace the campaign runner's default retention of Prime's cumulative JSON
stream with a bounded, incremental retained representation while preserving the
evidence needed for lifecycle, compaction, tool, result, error, terminal, and
Rook authoring-trace qualification.

The target flow is:

```text
Prime --mode json stdout
-> runner consumes the complete live byte stream
-> runner hashes exact original stdout bytes incrementally
-> normal monitoring consumes parsed live events
-> non-streaming events are retained byte-for-byte
-> message_update events are retained as bounded deltas
-> a separate capture-custody record binds original and retained streams
```

This is a captured-telemetry storage correction. It does not change Qwen's
context, Prime's durable session store, Prime compaction, Rook source events,
Grasshopper behavior, or semantic evaluation.

## Triggering Evidence

The sealed Vessel V5 campaign retained this Prime JSON event stream:

```text
rows                                  74,473
bytes                          3,543,087,572
message_update rows                   74,143
message_update bytes           3,521,830,701   99.40%
thinking_delta rows                   71,686
thinking_delta bytes           3,439,477,024
all delta string bytes                 306,219
serialized partial bytes       1,755,936,928
image-bearing row bytes           20,054,395     0.57%
```

Every retained `message_update` contains the growing assistant message as both
top-level `message` and nested `assistantMessageEvent.partial`. The small new
delta is therefore accompanied by two cumulative copies. Exact duplicate rows
are rare; ordinary file deduplication is not the issue.

The original V5 evidence and the separately closed compaction-aware V2 trace
admission remain immutable. This design does not edit:

```text
mcp_server/src/rook/gh_behavioral_acceptance.py
mcp_server/src/rook/gh_behavioral_acceptance_v2.py
C:/UDEV/RookEvidence/2026-08-20-qwen38-multimodal-vessel-massing-v5
C:/UDEV/RookEvidence/2026-08-20-prime-compaction-trace-reconciliation-v1
```

## Classification

This is a bounded architectural change because it introduces a versioned
retained-event format and a custody contract consumed by qualification tooling.
It is not a new product runtime, model supervisor, orchestration layer, semantic
acceptance system, or Prime lifecycle mechanism.

The finite vocabulary in this design is justified by Prime's versioned event
transport. It classifies transport records, not open-ended user intent.

## Ownership Audit

### Producer

Prime print mode owns the live JSON event API. In JSON mode it subscribes to
session events and writes every event using `JSON.stringify`:

```text
D:/prime-agent/.worktrees/rook-upstream-evaluation/
packages/coding-agent/src/modes/print-mode.ts
```

The underlying agent loop emits `message_update` with a cumulative
`message` and a streaming `assistantMessageEvent` whose `partial` field refers
to the same cumulative assistant state.

Prime already contains a relevant transport precedent:

```text
packages/coding-agent/src/modes/daemon/compact-session-stream.ts
```

Daemon transport emits `assistant_stream_delta` records without cumulative
`partial` and reconstructs legacy assistant state client-side. Its tests prove
that payload size remains independent of growing assistant text.

### Capture owner

The Rook campaign runner chooses what becomes durable experiment evidence:

```text
scripts/qwen38_self_termination_campaign_runner.py
```

Its current `_reader()` copies each stdout line directly into
`operator/prime.jsonl`. The runner therefore owns the 3.54 GB retained file.
Prime owns the live event, but Rook owns this campaign-specific persistence
decision, manifests, evidence roots, and downstream qualification handoff.

### Persisted formats

Three distinct formats must remain conceptually separate:

1. Prime's live `--mode json` stdout event stream.
2. Prime's durable session JSONL under the campaign's `agent/sessions` root.
3. Rook's captured `operator/prime.jsonl` telemetry artifact.

Only the third format changes in this slice.

### Consumer inventory

| Consumer | Evidence used | Compact impact |
|---|---|---|
| Live budget monitor | Complete `message_end.message.usage` | Retained exactly and consumed from the original parsed event immediately after that row is persisted |
| Goal-context preflight | `goal_update`, `message_start`, `message_end`, session actions | Retained exactly |
| Model-load check | First assistant `message_end` | Retained exactly |
| Multimodal attachment audit | `tool_execution_start`, `tool_execution_end` | Retained exactly |
| Row telemetry | Complete `message_end` usage | Retained exactly |
| V1/V2 trace admission | Session, agent, compaction, IPython checkpoint, session-action, terminal rows; runtime hash | Retained exactly; compact deltas project to no lifecycle evidence |
| Tool/result/error history | Tool execution start/update/end and complete message checkpoints | Retained exactly |
| Efficiency attribution | `message_update` sizes and deltas | Updated to understand compact deltas and capture custody |
| Historical reconciliation | Sealed raw V5 stream | Unchanged; remains raw-only historical tooling |
| External Prime JSON clients | Prime live stdout | Unchanged because Prime output does not change |

No inspected normal qualification consumer requires the repeated cumulative
`message` or `partial` value on every streaming delta.

## Owner Decision

The smallest correct owner is the **Rook campaign capture layer**.

Reasons:

- The runner created and owns the durable amplification.
- Prime's live JSON stream is a documented general API with consumers beyond
  Rook.
- Prime already demonstrates that delta transport is semantically sufficient,
  but changing or adding a Prime mode would expand fork maintenance.
- Capture-side compaction leaves model execution, session persistence,
  compaction, and live event semantics unchanged.
- Existing V2 admission can consume the compact path without modifying its
  closed lifecycle rules.

## Approaches Considered

### 1. Runner-owned compact persistence - selected

The runner consumes Prime's complete live stdout, hashes the exact bytes, and
persists bounded delta records for recognized assistant updates. All other
events remain byte-identical.

Advantages:

- fixes the structural retained-size problem at its owner;
- changes no Prime API or product runtime;
- preserves complete non-streaming evidence;
- follows Prime's existing daemon delta precedent;
- supports offline replay against the exact sealed specimen; and
- can fall back to raw retention for unfamiliar valid update shapes.

Limitation: Prime still serializes and sends the cumulative stream to the
runner. This slice reduces persisted storage and downstream parsing, not Prime
producer or pipe traffic.

### 2. Prime compact JSON output mode - deferred

Prime could expose a new compact print mode or change JSON mode. This could
also reduce producer-side serialization and pipe traffic.

It is not selected because it changes the live execution protocol, expands the
Prime fork, and is unnecessary to qualify the storage correction. It becomes a
future comparison only if retained compaction leaves measured producer or pipe
cost material.

### 3. Compression-only containment - rejected

The runner could gzip the raw stream.

Compression preserves exact bytes and would exploit repetition, but it retains
quadratic serialization, forces downstream decompression and parsing of 74,143
cumulative snapshots, and leaves the evidence representation structurally
misaligned with streaming semantics. Compression may be an optional raw-debug
transport, not the default correction.

Independent design review measured gzip level 6 directly over the sealed source
without writing a retained artifact:

```text
source bytes                    3,543,087,572
gzip level 6 bytes                727,134,876
reduction                              79.48%
elapsed                                68.8 s
```

This measurement is descriptive review evidence, not a new custody artifact.
It materially misses the required 95% persisted-size reduction and confirms
that compression-only containment does not satisfy this slice.

## Scope

### In scope

- one runner-owned streaming capture utility;
- a versioned compact retained-event schema;
- exact incremental source-byte custody;
- deterministic compact output;
- explicit raw fallback for unfamiliar valid updates;
- optional protocol-frozen full raw diagnostic capture;
- a capture-custody sidecar and verifier;
- runner integration behind an explicit protocol field;
- offline replay against the sealed Vessel stream; and
- consumer and corruption qualification.

### Out of scope

- modifying Prime;
- modifying V1 or V2 behavioral acceptance;
- changing Prime's durable session JSONL;
- changing model prompts, skills, thinking, or context;
- changing Rook source-log, receipt, or mutation semantics;
- Rhino, Grasshopper, Vessel, Ollama, or Qwen contact;
- semantic evaluation or acceptance vocabulary;
- a supervisor, cache, compactor service, database, or general event bus;
- producer-side Prime JSON serialization optimization; and
- power-loss or storage-hardware durability.

## Protocol Admission

New campaign protocols opt in with a closed object:

```json
{
  "primeEventCapture": {
    "schema": "rook.prime_event_capture_config:v1",
    "mode": "compact",
    "retainedPath": "operator/prime-events.compact.jsonl",
    "custodyPath": "operator/prime-event-capture-custody.json",
    "rawDebugPath": null
  }
}
```

The only modes are:

```text
compact
compact_with_raw_debug
```

For `compact_with_raw_debug`, `rawDebugPath` is required and must be a distinct
relative path inside the row's operator directory. For `compact`, it must be
`null`. All objects are closed. Absolute paths, parent traversal, aliases,
unknown fields, and ambient environment overrides refuse before process launch.

Historical protocols without this field retain their historical behavior and
hashes. After qualification, new experiment protocols use `compact` explicitly;
no historical artifact is rewritten.

## Binary Ingress And Live Monitoring

Prime stdout is opened in binary mode. Three runner-owned constants are frozen
for V1 and are not caller-configurable:

```text
MAX_SOURCE_ROW_BYTES       67,108,864 bytes  (64 MiB, including LF)
SOURCE_READ_CHUNK_BYTES        65,536 bytes  (64 KiB)
MONITOR_QUEUE_MAX_EVENTS            1 event
```

The row ceiling is more than seventeen times the sealed Vessel maximum row of
3,806,566 bytes. It is a resource boundary, not a semantic claim. A future
legitimate event exceeding it requires a separately reviewed schema version;
the limit cannot be raised through a campaign protocol or environment variable.

The capture reader never calls unbounded `readline()`. It reads at most
`SOURCE_READ_CHUNK_BYTES`, searches incrementally for LF, and refuses as soon
as the current row would exceed `MAX_SOURCE_ROW_BYTES`, whether or not a later
chunk might contain LF. Bytes following the first complete LF remain framed for
the next row without combining the rows.

For each admitted raw row, the capture owner:

1. receives the exact bytes from the pipe;
2. updates one cumulative SHA-256 and byte count before decoding;
3. requires a terminating LF;
4. decodes strict UTF-8 without replacement;
5. parses exactly one JSON object while rejecting duplicate object keys;
6. writes exactly one retained row; and
7. publishes the parsed original event to the existing live monitor.

The reader publishes parsed stdout events through
`queue.Queue(maxsize=1)`. A full queue blocks the reader before it reads another
stdout chunk, allowing the operating-system pipe to provide backpressure to
Prime. The queue contains the parsed event only, never an additional raw-byte
or decoded-line copy. At most one event is queued while one event is being
framed or blocked while publishing. The reader may therefore hold at most one
parsed event while one earlier event occupies the queue; it cannot read a third
event or request another pipe chunk until the consumer advances. Bytes already
read ahead in the current fixed-size chunk remain bounded by
`SOURCE_READ_CHUNK_BYTES`; no third row is parsed, admitted, or persisted.
Stderr lines are written by their own
reader and are not placed on the stdout monitor queue. A separate bounded
control handoff carries only the closed signals `stdout_eof`, `stderr_eof`, and
`capture_error`, each at most once.

The live monitor therefore continues to enforce budgets and inspect goal or
model-load events from the complete Prime event, not from the compact retained
projection.

CRLF normalization, replacement decoding, blank rows, scalar JSON, duplicate
object keys, and multiple JSON values in one row are forbidden. The stderr path
remains a separate capture and is not compacted; this design makes no new
stderr custody claim.

## Compact Retained Stream

The compact file has exactly one output row for every admitted stdout row, in
the same order. It has no embedded header or trailer; the separate custody
record owns format version and closure. This preserves line correspondence and
does not append activity after Prime's terminal event.

### Exact passthrough

Every row whose type is not a recognized compactable `message_update` is
written byte-for-byte, including its original LF.

This includes:

```text
session
goal_update
agent_start / agent_end
turn_start / turn_end
compaction_start / compaction_end
session_action_update
message_start / message_end
tool_execution_start / tool_execution_update / tool_execution_end
unknown future event types
```

Complete terminal messages, tool results, errors, images, IPython state
checkpoints, goal contexts, usage, and lifecycle details therefore remain exact.

### Compactable assistant update

A `message_update` is compactable only when all of these are true:

- the root has exactly `type`, `message`, and `assistantMessageEvent`;
- `message.role` is `assistant`;
- `assistantMessageEvent.partial` exists and is structurally equal to
  `message`;
- the subtype and its fields match one of the closed shapes below;
- after removing the required `partial`, the source subtype has exactly the
  retained `assistantMessageEvent` keys defined below;
- `contentIndex` is a nonnegative integer and resolves to the required content
  kind in `message`; and
- no non-finite JSON number is present.

Recognized subtypes are:

```text
text_start       text_delta       text_end
thinking_start   thinking_delta   thinking_end
toolcall_start   toolcall_delta   toolcall_end
```

The retained row is canonical JSON plus LF:

```json
{
  "assistantMessageEvent": {
    "contentIndex": 0,
    "delta": "next bytes",
    "type": "thinking_delta"
  },
  "schema": "rook.prime_assistant_stream_delta:v1",
  "sourceBytes": 48173,
  "sourceRow": 127,
  "type": "assistant_stream_delta"
}
```

Canonical encoding is UTF-8 produced with `ensure_ascii=False`,
`allow_nan=False`, sorted object keys, compact separators, and one final LF.
This matches the repository's existing trace-custody encoding without making
the frozen V1 or V2 module an implementation dependency.

`sourceRow` is one-based. `sourceBytes` includes the original LF. These fields
support attribution and line correspondence; they do not establish the content
of discarded bytes independently of the capture owner.

### Closed delta-record shapes

Every compact record has these required common fields and no other common
fields:

```text
schema                         exact string rook.prime_assistant_stream_delta:v1
type                           exact string assistant_stream_delta
sourceRow                      JSON integer >= 1
sourceBytes                    JSON integer in [1, MAX_SOURCE_ROW_BYTES]
assistantMessageEvent          one closed subtype object below
```

Start records additionally require `contentStart`. Delta and end records
forbid it. There are no optional root fields.

The exact subtype matrix is:

| Subtype | Exact `assistantMessageEvent` keys | Exact root keys beyond common | Forbidden subtype fields |
|---|---|---|---|
| `text_start` | `type`, `contentIndex` | `contentStart` as closed text start | `delta`, `content`, `toolCall`, `partial` |
| `thinking_start` | `type`, `contentIndex` | `contentStart` as closed thinking start | `delta`, `content`, `toolCall`, `partial` |
| `toolcall_start` | `type`, `contentIndex` | `contentStart` as closed tool-call start | `delta`, `content`, `toolCall`, `partial` |
| `text_delta` | `type`, `contentIndex`, `delta` | none | `content`, `toolCall`, `partial` |
| `thinking_delta` | `type`, `contentIndex`, `delta` | none | `content`, `toolCall`, `partial` |
| `toolcall_delta` | `type`, `contentIndex`, `delta` | none | `content`, `toolCall`, `partial` |
| `text_end` | `type`, `contentIndex`, `content` | none | `delta`, `toolCall`, `partial` |
| `thinking_end` | `type`, `contentIndex`, `content` | none | `delta`, `toolCall`, `partial` |
| `toolcall_end` | `type`, `contentIndex`, `toolCall` | none | `delta`, `content`, `partial` |

For every subtype, `type` is the exact row's subtype and `contentIndex` is a
nonnegative JSON integer. Booleans are not integers. `delta` and `content` are
JSON strings. Empty strings remain valid because Prime's transport type permits
them.

The three closed `contentStart` variants are:

```text
text start
  required keys: type, text
  optional keys: textSignature
  invariants: type == text; text == ""; textSignature is a string when present

thinking start
  required keys: type, thinking
  optional keys: thinkingSignature, redacted
  invariants: type == thinking; thinking == "";
              thinkingSignature is a string when present;
              redacted is a JSON boolean when present

tool-call start
  required keys: type, id, name, arguments
  optional keys: thoughtSignature
  invariants: type == toolCall; id and name are nonempty strings;
              arguments == {};
              thoughtSignature is a string when present
```

No other `contentStart` key is admitted. Optional means any subset of the named
optional keys, not an open object.

The pinned Prime build may expose two transient provider scratch fields on the
source message's tool-call content block during streaming:

```text
partialArgs                   JSON string
streamIndex                   nonnegative JSON integer; booleans forbidden
```

For source admission, a tool-call start block has the stable required and
optional fields above plus either or both of these exact optional scratch
fields, and no others. The retained `contentStart` deliberately omits
`partialArgs` and `streamIndex`; Prime itself removes them before the final
`toolcall_end`. Text and thinking source blocks have exactly the corresponding
required and optional `contentStart` keys above. Any additional source-content
key takes raw fallback rather than being silently discarded.

A streaming, read-only shape audit of all 74,143 sealed V5 update rows confirmed:

```text
root key sets                         1 (assistantMessageEvent,message,type)
assistant event key sets              9 (the nine declared source subtypes)
message/partial structural mismatches 0
text-start content keys               text,type
thinking-start content keys           thinking,thinkingSignature,type
tool-start content keys               arguments,id,name,partialArgs,streamIndex,type
tool-end value keys                   arguments,id,name,type
```

This specimen evidence justifies the V1 shapes; the optional typed fields also
preserve the pinned Prime interfaces when absent from this particular run.

The closed `toolCall` value on `toolcall_end` has required keys `type`, `id`,
`name`, and `arguments`, with optional `thoughtSignature` only. `type` must be
`toolCall`; `id` and `name` must be nonempty strings; `arguments` must be a JSON
object; and `thoughtSignature`, when present, must be a string. No other key is
admitted.

At the compact-record root, `message`, `partial`, `activeSessionId`, `meta`,
`toolCallArguments`, raw bytes, and any unlisted field are forbidden. Inside
`assistantMessageEvent`, `partial` and every field not named by its matrix row
are forbidden.

Start records follow Prime's daemon compaction principle: dynamic text or
thinking is replaced by `""`, tool arguments are replaced by `{}`, and the two
known provider scratch fields above are excluded from the retained semantic
record.
Delta records retain the exact delta string. End records retain the complete
`content` or `toolCall` already present in `assistantMessageEvent`. No cumulative
tool-argument snapshot is retained; the complete `toolcall_end` and
`message_end` are authoritative.

### Raw fallback

If a syntactically valid JSON object is not exactly compactable, the original
row is retained byte-for-byte. The custody record increments
`rawFallbackMessageUpdates` when the root type is `message_update`.

This is evidence-preserving forward compatibility, not silent acceptance of a
new schema. Qualification against a pinned Prime build may require zero raw
fallback updates. A fallback never loses data, but it can reduce the size
benefit and must remain visible in reports.

## Capture Custody

After stdout EOF and successful compact-file close, the runner writes:

```json
{
  "schema": "rook.prime_event_capture_custody:v1",
  "status": "complete",
  "limits": {
    "maxSourceRowBytes": 67108864,
    "monitorQueueMaxEvents": 1,
    "sourceReadChunkBytes": 65536
  },
  "source": {
    "bytes": 3543087572,
    "maxRowBytes": 3806566,
    "rows": 74473,
    "sha256": "F79F...AA3B",
    "stdoutEof": true
  },
  "retained": {
    "bytes": 0,
    "compactedMessageUpdates": 74143,
    "path": "operator/prime-events.compact.jsonl",
    "rawFallbackMessageUpdates": 0,
    "rows": 74473,
    "sha256": "..."
  },
  "rawDebug": null
}
```

The final schema uses actual measured retained values; zero above illustrates
the field shape only. All custody objects are closed. `limits` must equal the
runner-owned V1 constants, and `source.maxRowBytes` is the largest admitted row
including LF. Post-run verification refuses if the observed maximum exceeds the
recorded limit or any applied limit differs from the compiled constants.

The custody record is deterministic: it contains no timestamp, PID, absolute
output path, random identifier, or host-dependent separator. Its relative paths
are fixed by the admitted protocol.

The raw SHA-256 proves that the capture owner observed a byte sequence matching
the declared digest. It does **not** prove the discarded cumulative fields to an
independent reviewer when the raw bytes are absent. That stronger claim is made
only during offline qualification against the separately retained source or in
explicit raw-debug mode.

For `compact_with_raw_debug`, the exact source bytes are also written to the
admitted path. The custody record includes its relative path, byte count, and
SHA-256 and requires equality with `source`. Raw debug is never enabled by an
ambient flag or added after execution.

The evidence manifest hashes the compact stream and custody record. In debug
mode it also hashes the raw file.

An unsuccessful capture never receives a complete custody record. When the
runner remains alive, it writes a separate best-effort diagnostic artifact:

```json
{
  "code": "stdout_missing_final_lf",
  "retainedPrefixBytes": 1234,
  "retainedPrefixRows": 8,
  "schema": "rook.prime_event_capture_failure:v1",
  "sourcePrefixBytes": 4567,
  "sourcePrefixRows": 9,
  "status": "incomplete",
  "stdoutEof": true
}
```

This artifact diagnoses an incomplete prefix; it never authorizes sealing. If
the runner dies before writing it, the missing complete custody record remains
sufficient to refuse the evidence.

## Reconstruction Contract

### Exactly retained and reconstructable

- original ordering and count of admitted stdout rows;
- exact bytes of every non-compact row;
- session, goal, agent, turn, and compaction lifecycle;
- session-action handoffs;
- tool execution start/update/end records;
- complete tool results and errors;
- complete `message_start` and `message_end` checkpoints;
- complete terminal assistant messages and usage;
- IPython checkpoint messages;
- images present in exact passthrough events;
- final tool calls from `toolcall_end`; and
- the source stream's total bytes, rows, and SHA-256 as observed by the capture
  owner.

### Semantically reconstructable

Given a complete `message_start`, ordered compact deltas, and the corresponding
complete `message_end`, a reconstructor can reproduce:

- assistant text and thinking content by content index;
- block starts and ends;
- final tool identity, arguments, and ordering; and
- the final assistant message value.

The reconstruction algorithm follows Prime's existing
`CompactAssistantStreamReconstructor` behavior. Content blocks may be
interleaved; association is always by `contentIndex`, never adjacency.

### Intentionally not reconstructable without raw debug

- byte-for-byte original `message_update` rows;
- original JSON key order or lexical number/string representation in compacted
  rows;
- each repeated cumulative top-level `message` serialization;
- each repeated nested `partial` serialization;
- transient best-effort partially parsed tool arguments before
  `toolcall_end`; and
- any unknown data in a malformed row, because malformed input makes capture
  incomplete rather than generating output.

Intermediate reconstructed values are semantic values, not claims about the
discarded original bytes. Offline replay against the sealed raw specimen proves
equivalence for that specimen only.

## Failure And Crash Contract

The capture is complete only when:

- the Prime process reaches stdout EOF;
- every observed row has LF, strict UTF-8, and one JSON object;
- every input row produces exactly one retained row;
- all compact writes and the final close succeed;
- retained row and byte hashes finalize successfully;
- the custody record is written successfully; and
- post-run verification matches the custody record.

The V1 failure codes are exactly:

```text
stdout_read_failed
stdout_invalid_utf8
stdout_missing_final_lf
stdout_row_too_large
stdout_json_invalid
stdout_json_object_required
stdout_json_duplicate_key
compact_transform_failed
compact_write_failed
compact_close_failed
raw_debug_write_failed
raw_debug_close_failed
capture_custody_write_failed
capture_custody_missing
capture_custody_mismatch
capture_row_count_mismatch
raw_debug_mismatch
```

An unfamiliar but valid event shape is not `compact_transform_failed`; it takes
the declared byte-exact raw fallback. `compact_transform_failed` is reserved for
an internal transformation invariant failing after exact compact admission.

The reader thread reports failures to the execution owner. The owner terminates
the process tree if still live, records the incomplete prefix when possible,
and refuses normal evidence sealing. If the runner process itself dies before
custody creation, the missing custody record makes the evidence unsealable on
restart.

Budget or wall-clock termination may produce a valid capture of the complete
stdout prefix emitted before EOF. It does not create a Prime terminal marker.
Lifecycle admission remains independently fail-closed.

No custom `fsync` is added. The claim is limited to successful writes, close,
process-visible EOF, custody verification, and the existing evidence-manifest
contract. Power loss, filesystem corruption, and storage hardware failure are
outside scope.

## Consumer Handoff

The runner gains one protocol-aware path resolver and one shared retained-event
iterator. The resolver is the sole owner of telemetry-path selection:

```text
resolve_prime_event_path(protocol, row_root)
  historical protocol without primeEventCapture
    -> row_root/operator/prime.jsonl
  admitted rook.prime_event_capture_config:v1
    -> row_root/<exact retainedPath>
```

The resolver never guesses from file existence, aliases a compact stream to the
historical filename, or accepts a caller-supplied path. Protocol admission has
already proved that `retainedPath` is a closed relative path inside the row's
operator directory. For a compact protocol, the resolver returns only after the
complete custody record verifies the retained relative path, hash, bytes, rows,
limits, and source/retained row equality. Every post-run consumer below receives
the resolver's result or the shared iterator; no compact-aware call site
independently joins `operator/prime.jsonl`.

Normal consumers receive exact passthrough events and skip
`assistant_stream_delta` unless they explicitly request stream reconstruction.

Specific handoffs are:

- the live monitor consumes original parsed events before compaction;
- post-run goal, usage, attachment, and telemetry readers consume exact
  passthrough rows;
- V2 receives the compact stream path directly and projects compact delta rows
  as irrelevant to lifecycle, without source modification;
- a separate reconstructor is used only by qualification or explicit forensic
  tools; and
- the historical V5 reconciliation script remains raw-only and unchanged.

The current filename `operator/prime.jsonl` remains historical. New protocols
name `operator/prime-events.compact.jsonl` explicitly so consumers cannot
mistake compact telemetry for Prime's native JSON mode.

Function-level parity is mandatory, not inferred from equivalent parsed data.
The test suite invokes each existing entry point once with a raw retained stream
and once with its compact replay:

| Entry point | Required parity |
|---|---|
| `RunMonitor.consume_prime_line` | Identical cumulative provider tokens and identical ceiling decision from exact passthrough `message_end` rows |
| `prime_log_proves_goal_context` | Identical goal-context result |
| `summarize_row_telemetry` through `_write_varied_row_records` | Identical per-turn usage, mutation/discovery attribution, and evidence-path selection |
| `audit_multimodal_attachment_sequence` | Identical attachment ordering, call identity, and image result |
| `admit_retained_smoke` | Identical budget, goal, process, semantic, and custody disposition |
| `_operator_normalize` | Identical lifecycle projection, normalized source events, and terminal-receipt selection; only the predeclared retained-stream path/hash representation may differ |
| `_operator_evaluate` | Identical final fenced snapshot selection, criteria/status, and reason; only the predeclared retained-stream path/hash representation may differ |

These are direct calls through the named functions, not tests of a substitute
parser. Tests also enumerate the runner's compact-aware call sites and fail if a
new protocol path bypasses `resolve_prime_event_path`. Historical branches keep
their existing path and byte behavior.

## Implementation Shape

The implementation should add one focused script module, for example:

```text
scripts/prime_json_event_capture.py
```

It owns:

- protocol validation for capture configuration;
- binary row admission;
- compact transformation;
- incremental source and retained hashing;
- optional raw-debug teeing;
- custody creation and verification; and
- semantic reconstruction used by offline qualification.

The campaign runner owns process policy and calls this module. The module does
not import Rook MCP, contact Prime, create model sessions, or know Grasshopper
semantics.

Tests live with existing Python campaign tests. No dependency is added.

## Offline Qualification Design

Implementation begins with test-driven development and synthetic fixtures, then
replays the sealed 3.54 GB stream before any live integration.

### Source admission

Before creating the qualification output root:

1. verify the sealed V5 global manifest;
2. verify the sealed MV1 row manifest;
3. verify the exact raw event-stream path, size, row count, and SHA-256;
4. verify the source log, process result, and V2 owner hashes; and
5. refuse if any source byte or manifest entry differs.

The output uses a fresh durable sibling. The source stream is opened read-only
and is never copied, truncated, moved, rewritten, or added to a new manifest.

### Synthetic causal tests

Tests cover:

- text, thinking, and tool-call start/delta/end;
- interleaved content indices;
- multiple assistant messages and turns;
- complete message and terminal checkpoints;
- tool results, errors, images, goals, lifecycle, and compaction passthrough;
- structurally unequal `message` and `partial` falling back raw;
- unknown update subtypes falling back raw;
- deterministic canonical delta output;
- compact and compact-with-raw-debug modes;
- protocol attempts to override any runner-owned ingress or queue limit;
- malformed JSON, invalid UTF-8, scalar JSON, blank rows, and missing LF;
- an LF-terminated row that exceeds `MAX_SOURCE_ROW_BYTES`, refused before
  parsing, retention, or monitor publication;
- an unterminated row that exceeds `MAX_SOURCE_ROW_BYTES`, refused immediately
  at the same byte boundary rather than waiting for EOF;
- a deliberately stalled monitor consumer proving the queue never exceeds one
  event, the reader holds at most one subsequent parsed event, read-ahead stays
  within one fixed chunk, and no third row is parsed, admitted, or persisted
  until the consumer advances;
- boundary rows of exactly `MAX_SOURCE_ROW_BYTES`, including LF, remaining
  admissible when their content is otherwise valid;
- injected write and close failures;
- missing or altered custody;
- removed, duplicated, reordered, or changed compact rows;
- truncated raw-debug output; and
- missing terminal checkpoints remaining lifecycle-incomplete.

Closed-schema tests cover every required, optional, and forbidden field for all
nine compact subtypes. They include boolean-as-integer refusal, invalid
`contentStart` placement, admitted and invalid tool-call scratch fields, open
nested content objects, and raw passthrough for otherwise valid but unfamiliar
source-update shapes.

### Current-consumer parity

Synthetic and sealed-replay tests exercise the exact seven entry points named
in **Consumer Handoff** against both representations. They prove the path
resolver preserves historical `operator/prime.jsonl` behavior, selects the
protocol-declared compact stream for the new schema, and refuses missing,
outside-root, or mismatched paths before a post-run disposition is produced.
The tests retain each function's raw and compact outputs so parity is auditable
at the function boundary.

### Vessel replay assertions

The offline replay must prove all of these:

```text
source rows                              74,473
source bytes                      3,543,087,572
source SHA-256                    F79FF8...AA3B
retained rows                            74,473
compacted message updates                74,143
raw fallback message updates                  0
```

Persisted-size reduction is defined as:

```text
(compact stream bytes + custody record bytes) / source stream bytes
```

Raw debug is disabled and excluded because it is not default retention. The
ratio must be at most `0.05`, proving at least 95% reduction.

For every source row, replay also proves:

- non-`message_update` retained bytes are exactly equal at the same row;
- update subtype, content index, delta, content end, and tool-call end values
  equal the source event;
- every reconstructed final assistant message equals the source
  `message_end.message` value;
- lifecycle and compaction projection equals the raw projection;
- tool execution and error history equals the raw history; and
- all expected terminal/checkpoint rows are present.

### V2 outcome parity

Qualification creates two fresh copies of the source-event prefix without its
historical closure:

1. one is sealed and normalized against the original raw stream;
2. one is sealed and normalized against the compact stream.

Using the unchanged V2 owner, the results must have:

- the same lifecycle/compaction classification;
- identical normalized source events;
- the same latest terminal receipt;
- the same final fenced snapshot selection;
- the same shadow evaluation status and reason; and
- different runtime-log hashes only where expected because the retained byte
  representations differ.

The historical source log and its closure remain untouched.

### Determinism

Two independent replays of the same admitted raw stream with the same protocol
must produce byte-identical compact streams and custody records. Output roots,
process IDs, timestamps, and random identifiers do not enter retained bytes.

### Resource behavior

The replay is streaming. It does not call `read_bytes()` or `read_text()` on the
3.54 GB source, retain all raw rows in memory, or materialize a second raw copy.
Peak-memory measurement may be reported, but code-path inspection and causal
large-row tests are the authority for bounded streaming ownership.

## Review And Contact Gates

The required order is:

```text
approved design
-> committed design specification
-> independent design review
-> writing-plans
-> TDD implementation
-> synthetic offline tests
-> sealed Vessel replay
-> deterministic and corruption qualification
-> committed implementation and evidence report
-> independent implementation review
-> optional single non-Rhino Prime/Qwen smoke only if still necessary
```

No model contact is authorized by design approval or offline implementation
approval. A live smoke requires separate explicit authorization and may use
Prime/Qwen only. It may not contact Rook mutation, Rhino, Grasshopper, or the
Vessel task.

## Acceptance Criteria

The correction is qualified only when retained evidence proves:

1. at least 95% default persisted-size reduction on the sealed Vessel stream;
2. exact source stream size, row count, and SHA-256 custody;
3. identical lifecycle and compaction classification;
4. identical tool, result, error, checkpoint, and terminal history required by
   current consumers;
5. identical reconstructed final assistant messages;
6. identical unchanged-V2 trace-admission outcome apart from the expected
   runtime-log digest;
7. deterministic compact stream and custody bytes;
8. bounded ingress under oversized terminated rows, oversized unterminated
   rows, and a stalled consumer;
9. function-level parity for goal context, budget monitoring, telemetry,
   attachments, retained-smoke admission, normalization, and evaluation;
10. fail-closed truncation, malformed-row, writer-failure, missing-custody, and
   missing-terminal behavior;
11. source and historical manifest preservation;
12. no Prime, V1, V2, model guidance, Rook mutation, Rhino, Grasshopper, or
   Vessel changes; and
13. a clean bounded worktree with exact implementation, test, protocol,
    evidence, and report hashes.

## Adoption Boundary

After qualification, compact capture becomes the explicit baseline for new
Rook/Prime experiments. Historical protocols and evidence remain on their
original formats. Full raw capture remains an exceptional, predeclared
diagnostic mode.

This qualification does not establish that Prime's producer-side cumulative
serialization is efficient. If later telemetry shows material CPU, memory, or
pipe cost after retained compaction, the next smallest comparison is a Prime
compact print mode based on Prime's existing daemon stream. That is a separate
design and cannot be inferred from storage qualification alone.
