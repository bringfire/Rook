# RookChat Prime Primary Backend Slice 0 Contract

**Status:** PROPOSED FOR INDEPENDENT REVIEW; UNIMPLEMENTED; UNQUALIFIED

**Date:** 2026-08-26

## Purpose

This contract defines the minimum lifecycle and custody boundary required before
RookChat replaces `ChatRunner` with Prime RPC. It narrows the recommended
RPC-first architecture; it does not authorize implementation.

The first implementation plan may cover Slices 1-2 only:

1. model-free Prime RPC backend; and
2. one text-only `AgentChatTab` streaming cutover.

Rook mutation, steering, images, web search, packaging, and product cutover
remain later work.

## Governing decision

One RookChat conversation maps to one saved Prime session. The existing C# panel
remains the user interface, the Python service becomes a narrow broker, Prime
owns model/session/tool-loop behavior, and Rook remains the sole owner of Rhino
and Grasshopper truth.

The first vertical is single-flight. No broker heuristic may infer that a Prime
prompt is finished.

## Owners

### C# panel

The panel owns:

- creation and retention of a stable RookChat conversation ID;
- the current Rhino target fingerprint supplied to the broker;
- rendering broker lifecycle and Prime event projections;
- disabling prompt submission while a turn is active or cancellation is
  pending; and
- initiating explicit prompt, cancel, reopen, and close actions.

The panel must not discard the stable conversation ID merely because the Python
service restarts.

### Python broker

The broker owns:

- a durable registry of atomic per-conversation files;
- one in-memory table of resident Prime RPC processes;
- strict command correlation and event projection;
- finite process residency and cleanup; and
- target-fingerprint checks before restoration or model contact.

The broker translates lifecycle and transport. It does not decide whether the
model's work is semantically complete.

### Prime

Prime owns:

- model/provider authentication and selection;
- the saved session and transcript;
- prompt execution, retries, compaction, tools, and continuation; and
- the authoritative prompt-settled boundary.

### Rook

Rook owns target identity enforcement, host mutation, receipts, solve readiness,
and authentic Rhino/Grasshopper observation. Nothing in this contract changes
that boundary.

## Durable conversation registry

Each Rhino process-generation namespace is a directory containing one atomic
file per conversation:

```text
<registry-root>/<rhinoPid>-<rhinoProcessStartUtcTicks>/<conversationId>.json
```

Each conversation file contains only this closed record:

```json
{
  "schemaVersion": 1,
  "conversationId": "rookchat UUID",
  "primeSessionId": "Prime session ID",
  "primeSessionPath": "absolute saved-session path",
  "model": {
    "provider": "provider ID",
    "id": "model ID",
    "thinking": "configured reasoning level or null"
  },
  "target": {
    "rhinoPid": 1234,
    "rhinoProcessStartUtcTicks": "638918000000000000",
    "documentRuntimeSerial": 42
  },
  "lastLifecycle": {
    "state": "idle",
    "reason": null,
    "updatedAtUtc": "2026-08-26T12:00:00Z"
  }
}
```

Allowed lifecycle states are:

```text
idle
running
cancel_requested
failed
closed
```

Each file is an atomically replaced identity/state record, not a transcript. It
contains no credentials, messages, process handles, pipe objects, or model
output. Updating one conversation must not rewrite, remove, or infer state for
any sibling file.

Each Rhino process generation has a separate registry namespace keyed by:

```text
Rhino PID + Rhino process-start UTC ticks
```

Exactly one broker instance may hold the writer lock for that namespace. All
conversation-file updates in the directory occur under that namespace-wide
lock. A second writer refuses startup rather than sharing or overwriting files.

## In-memory runtime ownership

Resident process state is never durable. The broker's in-memory table owns:

```text
Prime process handle
monotonic launch generation
stdin/stdout/stderr pipes
pending prompt command ID
last activity timestamp
shutdown/cancellation handles
```

Each launch receives a new generation. Events from an older or retired
generation cannot update the current conversation.

A persisted Prime PID, if ever retained for diagnostics, is observational only
and cannot recreate ownership after restart.

## Target identity

Rook authority is bound immutably to:

```text
Rhino PID
+ Rhino process-start UTC ticks
+ document runtime serial
```

The C# host obtains the process-start fingerprint from its own Rhino process and
sends the complete tuple when creating or reopening a conversation. PID plus
document serial is insufficient because Windows may reuse PIDs and document
serials are process-local. UTC ticks are serialized as a canonical decimal
string so the 64-bit value remains exact across C#, JSON, Python, and Node.

Restoration requires an exact tuple match. A mismatch may reopen the Prime
transcript only through a future explicitly read-only product flow; the first
vertical fails restoration and never rebinds Rook authority.

## Prompt-settled RPC boundary

Raw `agent_end` is an agent-segment boundary. Prime may legitimately emit it
before retry or compaction continuation. It must never produce RookChat `done`,
return a conversation to `idle`, or admit another prompt.

Slice 1 adds one public Prime RPC command backed by Prime's existing ACP
headless-turn sequence:

```json
{
  "id": "turn UUID",
  "type": "prompt_and_wait",
  "message": "user text",
  "images": []
}
```

Prime continues streaming ordinary events while this command is pending. The
command emits exactly one correlated terminal response only after this complete
Prime-owned sequence:

1. capture the pre-turn transcript boundary using ACP's message-identity and
   stable-message-key approach, not a message count;
2. call `AgentSession.promptAndWait()`;
3. call `waitForHeadlessCompletion()` so queued compaction continuations and
   autonomous headless work settle; and
4. inspect only transcript messages not present at the pre-turn boundary,
   classifying a terminal provider/model failure rather than treating normal
   `promptAndWait()` resolution as success.

The terminal response has this success shape:

```json
{
  "id": "turn UUID",
  "type": "response",
  "command": "prompt_and_wait",
  "success": true,
  "data": {
    "outcome": "completed"
  }
}
```

The only Prime successful terminal outcomes are `completed` and `aborted`.
Admission, transcript inspection, provider/model execution, protocol, or
settlement failure returns `success: false` with a stable error code. The broker
does not retry a prompt whose settlement is unknown. The result may include
Prime's bounded autonomous-status projection, but no broker heuristic may
replace transcript inspection or headless completion.

The existing `abort` command remains independently dispatchable while
`prompt_and_wait` is pending. An accepted abort response means cancellation was
requested; it does not settle the prompt. Only the correlated terminal
`prompt_and_wait` response does that.

`prompt_and_wait` shares Prime RPC's existing serialized prompt-command lane,
while ordinary stream events and independently dispatched `abort` remain live.
The implementation must not hold ordinary events until the terminal command
response.

The Prime patch must remain a small public-RPC exposure of the established ACP
headless-turn sequence. Prefer extracting or reusing its boundary and terminal
inspection helpers rather than implementing a second interpretation. It must
not add a Rook-specific lifecycle inside Prime.

## Lifecycle

The permitted runtime transitions are:

```text
create or explicit reopen -> idle
idle -> running                         prompt_and_wait dispatched
running -> idle                         outcome completed
running -> cancel_requested             user cancel accepted by broker
cancel_requested -> idle                outcome aborted
cancel_requested -> idle                outcome completed_before_abort
running -> failed                       settlement failure or process/protocol loss
cancel_requested -> failed              settlement failure or process/protocol loss
idle | failed -> closed                 explicit tab/conversation close
```

No prompt is admitted from `running`, `cancel_requested`, `failed`, or `closed`.

`completed_before_abort` is a broker lifecycle outcome, not a third Prime
semantic outcome. It occurs when the correlated `prompt_and_wait` response
reports `completed` after the broker accepted the user's cancel request but
before Prime's abort response settled that generation. The broker finalizes the
turn once, persists `idle` with reason `completed_before_abort`, and ignores any
later abort response carrying that completed command ID and launch generation.
It does not send another abort or reinterpret the completed turn as stopped.

On broker startup, a durable `running` or `cancel_requested` record is persisted
as `failed` with reason `broker_restart_interrupted`. It never becomes `idle` by
absence of a resident process. Recovery from `failed` requires an explicit
reopen action that reloads the exact Prime session and reports the interruption,
or creation of a new conversation.

Loss of the terminal response after unknown execution also produces `failed`.
The broker never automatically replays that prompt.

## Panel behavior

The panel projects:

| Input | UI effect |
|---|---|
| Prime text/tool/image events | Existing bounded stream rendering |
| `agent_end` | Optional segment status; never `done` |
| `prompt_and_wait` completed | Finalize stream, show `done`, enable input |
| user cancel | Show `cancel_requested`; keep input disabled |
| `prompt_and_wait` aborted | Show stopped state, enable input |
| completed prompt wins cancel race | Show completed-before-cancel status, enable input |
| settlement/process/protocol failure | Show failed state; require reopen/new conversation |

Local HTTP cancellation or a disconnected NDJSON reader cannot mark the
conversation idle.

Mid-run steering and follow-up are absent from this vertical.

## Process residency and cleanup

Initial defaults remain finite:

```text
maximum resident Prime children: 10 per broker
idle retirement: 30 minutes
service-shutdown drain: 10 seconds globally
```

Idle retirement closes the process/kernel and preserves the Prime session plus
durable registry record. At capacity the broker retires the least-recently-used
idle child; if every child is active or cancelling, it refuses the new launch.

Tab close marks the record `closed`, requests cancellation if necessary, and
retires the child. Document close retires the child and makes the target
unavailable without rebinding. Service shutdown persists registry state,
requests cancellation, drains within the global bound, and terminates remaining
owned process trees. Cleanup is idempotent.

Session retention is a separate product policy and is not coupled to process
residency.

## Qualification required before Slice 2

Slice 1 must pass model-free causal tests for:

1. one prompt producing one correlated settlement;
2. a compaction-created continuation running after the original
   `promptAndWait()` resolves, with no UI `done` before headless completion and
   the single terminal settlement;
3. a provider/model failure for which `promptAndWait()` resolves normally being
   returned as `success: false` from post-boundary transcript inspection;
4. multiple `agent_end` segments around retry/compaction producing no UI `done`
   before the single terminal settlement;
5. cancellation remaining `cancel_requested` until the aborted settlement;
6. natural completion racing cancellation producing `completed_before_abort`,
   with the later abort response ignored for that command generation;
7. settlement loss or process death producing `failed` with no replay;
8. saved `running` and `cancel_requested` restoring as `failed`;
9. explicit reopen being the only path from `failed` to `idle`;
10. PID reuse with a different process-start fingerprint being rejected;
11. document-serial mismatch being rejected;
12. one-writer registry enforcement;
13. two conversation files surviving independent atomic updates without sibling
    loss or rewrite;
14. stale process-generation events being ignored;
15. atomic registry write failure preserving the prior valid record; and
16. capacity, idle retirement, tab/document close, and bounded shutdown.

Use a fake Prime child for adversarial event ordering and branch-local Prime
tests for the new RPC command over the ACP headless-turn sequence. No model,
provider, Rhino, Grasshopper, Rook mutation, or network contact is required.

## Explicit non-goals

This contract does not add:

- Option B or `DaemonAgentConnection`;
- mid-run steering or follow-up;
- a supervisor or terminalization protocol;
- campaign evaluators or semantic acceptance;
- automatic prompt replay;
- image, web-search, Rook-mutation, or packaging work; or
- a plan beyond Slices 1-2.

## Implementation gate

Do not write the Slices 1-2 implementation plan until independent review agrees
that the prompt-settled RPC response is a valid Prime-owned completion boundary
and that the durable/in-memory custody split is closed. Do not implement until
that plan is separately approved.
