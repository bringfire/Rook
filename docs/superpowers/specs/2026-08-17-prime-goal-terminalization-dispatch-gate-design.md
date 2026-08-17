# Prime Goal Terminalization And Rook Dispatch Gate

**Status:** Design ready for independent review

**Date:** 2026-08-17

**Rook baseline:** `8435758116adbfd0672ef5d5fc91a49b84002445`

**Prime baseline:** `c98941a2a5cf40faecf9b4648ac3c304abf48fd3`

**Parent architecture:**
`docs/superpowers/2026-08-17-coordinating-intelligence-candidate-architectures.md`

## Purpose

Qualify the smallest executable terminalization boundary required by Candidate A:

```text
active Prime goal
-> admitted Rook calls use goal-scoped dispatch leases
-> pre-completion checkpoint authorizes exact current evidence
-> Prime closes the dispatch gate to new leases
-> goal.complete persists one terminal record
-> the goal is complete and the admitted Rook adapter remains closed
```

The slice combines two mechanisms because neither proves the required property alone:

1. Prime owns goal lifecycle, completion authorization, dispatch-gate state,
   persistence, terminalization, and rehydration.
2. Rook owns a durable, versioned `rook_full.search/read/call` adapter that preserves
   the qualified payload-first, structured-error, and source-evidence contracts while
   cooperating with Prime's gate.

This is a lifecycle and capability-admission slice. It is not the full Candidate A
runtime, the pre-completion semantic checkpoint, a Rook deployment, or general Python
containment.

## Triggering Evidence

Prime currently makes `goal.complete()` terminal immediately. The Python wrapper then
returns normally, so later Python in the same IPython cell can still execute. Current
`rook_full` qualification adapters open MCP sessions directly from Python and have no
Prime-owned admission gate. Therefore this sequence is possible today:

```python
await goal.complete()
await rook_full.call("gh_edit", {...})
```

The first call terminalizes the goal, while the second can still reach Rook. Candidate A
requires the second call to refuse before transport entry.

The current Prime persistence path also updates in-memory goal state before persistence
and does not use `SessionManager.appendCustomEntryWithRollback()`. A failed completion
write can therefore leave memory and the session file disagreeing. The terminal path must
reverse that ownership order.

## Declared Failure And Security Model

### Included failure model

The design guarantees recovery from:

- a Prime process exit between any specified protocol phases;
- a persistence call that throws;
- a torn trailing JSONL record handled by Prime's established session loader;
- a lost host response after a successful terminal record;
- stale, duplicate, cross-goal, or cross-generation cooperative protocol calls; and
- adapter, transport, or evidence-recorder failures on the unmodified adapter path.

The linearization point is:

> Successful persistence through Prime's established session persistence contract.

No stronger storage claim is made. This slice adds no custom `fsync`, directory sync,
write-ahead log, database, or second journal. It does not claim survival from power loss,
kernel failure, controller-cache loss, filesystem corruption, or storage hardware failure.

The Rook evidence recorder retains its already-qualified flush behavior. That evidence
behavior does not upgrade Prime's session persistence claim.

### Cooperative containment boundary

The dispatch protocol qualifies the unmodified durable adapter path. It is not a security
boundary against hostile model-controlled Python.

The public model-facing API remains exactly:

```text
rook_full.search
rook_full.read
rook_full.call
```

The adapter uses internal Prime host requests to open and close dispatch leases. Those
operations are absent from the public `rook_full` API, but a caller that knows Prime's
generic `rlm.host_request` surface may invoke them directly. Exact identifiers prevent
accidental, stale, duplicate, and cross-goal misuse. They cannot prove that trusted adapter
code, rather than arbitrary Python, closed a lease after transport quiesced.

A determined caller could monkeypatch the adapter, call a raw transport, or issue an early
lease close. Preventing those behaviors requires host-owned transport or stronger kernel,
process, and network containment. Those are explicit adoption gaps, not properties of this
slice.

## Audited Existing Ownership

### Prime

Prime already owns:

- `GoalState`, goal identity, accounting, and continuation policy;
- typed IPython-to-host requests;
- session append, rewrite, flush, and branch rehydration;
- `goal.get`, `goal.create`, and `goal.complete`; and
- the terminal `complete` status that stops same-goal continuation.

Prime's `SessionManager.appendCustomEntryWithRollback()` is the selected persistence
primitive. It appends through the existing session path and removes the in-memory entry if
persistence fails. It does not call `fsync`, and this design does not add one.

### Rook

Rook already owns:

- the canonical capability gateway and Rook MCP transport configuration;
- payload-first model-facing results;
- exact structured MCP failure custody;
- one canonical source event per attempted gateway call;
- source-event validation and persistence; and
- target, mutation, receipt, and fenced-evidence truth.

The reviewed V5 `rook_full` adapter is currently disposable qualification code. Promotion
means placing a versioned source owner in the Rook repository and testing it as production
code. Installer wiring and general skill discovery remain outside this slice.

## Considered Approaches

### 1. Prime-owned gate plus Rook-owned cooperative adapter - selected

Prime persists goal-scoped lease and terminal state. The Rook adapter obtains a lease
before opening transport, records evidence before closing it, and refuses a result if the
close cannot be persisted. This preserves current ownership and proves the same-cell fence
over the admitted path without moving Rook transport into Prime.

### 2. Move Rook transport into the Prime host - rejected for this slice

Host-owned transport could attest that lease closure follows actual transport quiescence
and would create a stronger containment boundary. It would also couple Prime to Rook,
replace the qualified adapter path, broaden MCP session ownership, and require a larger
deployment decision. It remains a possible future containment layer.

### 3. Adapter-local file gate or remote Rook revocation - rejected

An adapter-local gate cannot make Prime terminal state authoritative. Remote revocation
would create a distributed transition across Prime and Rook with no shared linearization
point. Either approach recreates the crash ambiguity this slice exists to remove.

## Selected Owners

| Concern | Owner |
|---|---|
| Goal identity, generation, status, accounting | Prime `AgentSession` |
| Completion admission interface and pending state | Prime `AgentSession` plus an injected integration admission controller |
| Dispatch gate and lease registry | Prime `AgentSession`-owned controller |
| Lifecycle persistence and rehydration | Prime `SessionManager` and `AgentSession` |
| Model-facing `rook_full` API and transport | Rook-owned adapter |
| Capability result projection and source evidence | Rook-owned adapter and existing Rook evidence helpers |
| Rhino/Grasshopper mutation, solve, receipt, and fenced evidence | Existing Rook owners, unchanged |
| Semantic checkpoint implementation | Outside this slice; represented by a strict injected test controller |
| Arbitrary Python/process/network containment | Outside this slice |

Prime contains no Rook capability names, result schemas, receipt semantics, or source-event
classifications. The Rook adapter contains no goal-state transition or persistence logic.

## Conditional Activation And Compatibility

Terminalization enforcement is opt-in through an injected Prime execution controller.

```text
controller absent
-> existing Prime goal.get/create/complete behavior remains unchanged
-> internal lease and completion-preparation handlers are not registered
-> no terminalization qualification is claimed

controller present
-> a new active goal receives a persisted execution generation and open gate
-> goal.complete requires host-owned completion_pending authorization
-> every promoted rook_full operation requires a dispatch lease
```

The Rook adapter refuses before transport when the controller or lease handlers are absent.
It never falls back to an ungated MCP call. A configured controller encountering an existing
active goal without a persisted compatible execution state enters `recovery_required`; it
does not silently synthesize an open gate.

Starting a goal after a previously completed goal creates a new goal ID and execution
generation. Existing non-Rook Prime sessions, skills, and MCP integrations do not acquire a
dependency on Rook or on this gate.

## Prime State Model

Goal terminalization adds an execution state adjacent to, but not confused with,
`GoalState`:

```text
goal status:
  active | paused | budget_limited | complete | error | ...existing states

execution gate:
  open | completion_pending | recovery_required | closed
```

`completion_pending` is not a new terminal goal status. The goal remains `active` until
the terminal record persists successfully.

Each execution state is bound to:

```text
goalId
goalGeneration
transitionSequence
discreteUsageEpoch
gateState
openLeases[]
pendingAuthorization | null
terminalRecordId | null
```

`goalGeneration` is host-generated and changes when a new goal supersedes an earlier goal.
It prevents a lease or authorization from following a goal ID through restored or replaced
execution state.

### Persisted transition records

Prime persists closed, versioned records for these state changes:

```text
lease_opened
lease_closed
completion_authorized
completion_aborted
goal_terminalized
```

Every record contains the goal ID, generation, monotonically increasing transition
sequence, and the state required to replay that transition. Rehydration derives current
execution state only from a valid ordered prefix. Unknown versions, gaps, contradictory
transitions, or impossible state combinations produce `recovery_required`; they are never
repaired by guessing.

All transition methods follow one ownership rule:

```text
derive candidate next state
-> append with SessionManager.appendCustomEntryWithRollback
-> successful established persistence
-> install candidate in memory
-> emit state update
```

No method installs candidate goal or gate state before persistence succeeds.

## Cooperative Dispatch Lease Protocol

### Lease opening

Immediately before transport, the unmodified adapter requests a lease using a newly
generated call ID and a closed operation descriptor:

```text
adapter call entry
-> capture immutable target and arguments snapshot
-> internal lease begin request
-> Prime validates active goal, generation, and open gate
-> Prime persists lease_opened
-> adapter receives opaque lease identity
-> open exactly one MCP transport/session invocation
```

If begin validation or persistence fails, transport entry count is exactly zero.

The lease identity is bound to:

```text
goalId
goalGeneration
callId
leaseId
transitionSequenceOpened
operationKind
```

Operation descriptions support audit and correlation; they do not grant authority to a
different capability or prove semantic correctness.

### Lease closing

The adapter applies this order exactly:

```text
transport returns or raises
-> project the authentic result or exception
-> append and flush exactly one Rook source event
-> internal lease end request with source-event identity
-> Prime persists lease_closed
-> adapter returns payload or re-raises the authentic exception
```

Closing requires the exact active lease identity and permits one close. Stale, unknown,
duplicate, cross-goal, cross-generation, or mismatched-call closes refuse without changing
state.

If transport entered but source recording fails, the adapter does not close the lease. If
source recording succeeds but lease-close persistence fails, the adapter does not return a
successful payload to the model. In both cases the persisted open lease blocks completion
and makes recovery explicit.

The protocol is cooperative. Prime proves that its lease records are ordered and that the
unmodified adapter invokes them in the qualified order. Prime does not attest that arbitrary
Python refrained from forging an early close.

### Concurrency

Lease begin is serialized by the Prime-owned controller. Multiple admitted calls may be in
flight while the gate is `open`. Entering `completion_pending` requires zero open leases and
prevents all new lease opens.

This closes both races:

```text
begin wins first
-> lease is open
-> completion authorization refuses

authorization wins first
-> gate is completion_pending
-> begin refuses before transport
```

No timeout silently closes an open lease or reopens a gate.

## Pre-Completion Authorization

The slice introduces a generic Prime admission-controller interface and a strict fake
controller for qualification. It does not implement Candidate A's complete evidence and
semantic checkpoint.

The configured goal skill adds one model-facing wrapper:

```python
await goal.prepare_completion(candidate)
```

The wrapper requires one candidate object and sends it to a registered typed host handler.
The model does not supply goal ID, generation, transition sequence, usage epoch, deadline,
or authorization ID. Prime obtains its own lifecycle fields, and the injected controller
validates and enriches the candidate with integration-owned evidence bindings. Rejection or
malformed input leaves the active goal and open gate unchanged.

`goal.get()` remains an observational status operation while authorization is pending.
`goal.complete()` is the only admitted model-controlled state transition from
`completion_pending`. Other state-changing goal requests refuse or persistently abort the
authorization according to their existing semantics.

An admitted authorization is host-owned and contains:

```text
authorizationId
goalId and supersession chain
goalGeneration
target identity
source-trace epoch and prefix identity
latest receipt identity, when applicable
cited evidence identities
budget policy identity and version
fixed budget limits
discrete usage epoch
completion deadline
requested disposition
```

The authorization request refuses unless:

- the goal is active;
- the gate is open;
- no dispatch lease is open;
- the integration controller admits the exact candidate; and
- persistence of `completion_authorized` succeeds.

On success, Prime installs `completion_pending` and denies new leases. The authorization is
not returned as a model-visible bearer token. The model receives only a disposition and may
call `goal.complete()`.

The authorization is one-use. Steering, goal supersession, a discrete usage-epoch change,
or another admitted host transition aborts it through a persisted `completion_aborted`
record. Passage of wall-clock time alone does not alter the bound state, but completion
refuses after the explicit deadline.

Continuously changing `timeUsedSeconds` is not compared byte-for-byte. Completion evaluates
the bound budget policy against current accounting at the final transition.

## Terminalization Protocol

`goal.complete()` is authorized only when:

- the goal is active and matches the pending authorization;
- goal generation and discrete usage epoch match;
- the gate is `completion_pending`;
- no lease is open;
- the deadline has not passed;
- the completion-time budget predicate passes; and
- every bound checkpoint identity still matches.

Prime then derives one terminal state and persists one `goal_terminalized` record containing:

```text
consumed authorization identity
goal state: active=false, status=complete
dispatch gate: closed
goalId and goalGeneration
terminal transition sequence
final discrete usage epoch
completion-time accounting projection
```

Successful persistence of this record through Prime's existing session persistence contract
is the sole linearization point. Only after it succeeds does Prime install the complete goal
and closed gate in memory.

If persistence throws:

- rollback removes the failed record from Prime's in-memory session index;
- the authorization remains pending;
- the goal remains active;
- the gate remains `completion_pending`; and
- no successful completion response is returned.

Once persistence succeeds:

- the authorization is consumed;
- duplicate completion refuses;
- all later adapter lease begins for that goal and generation refuse before transport; and
- Python may continue in the same cell, but the admitted Rook capability path remains closed.

The terminal record replaces a separate complete-goal append. Rehydration must treat it as
authoritative for both goal completion and gate closure so those facts cannot diverge.

## Recovery Contract

| Last valid persisted state | Rehydrated goal | Rehydrated gate | Required action |
|---|---|---|---|
| Open, no unresolved lease or authorization | Active | Open | Continue normally |
| Open lease without matching close | Active | `recovery_required` | Orient current state; fresh checkpoint before capability reissue |
| Completion authorized, no terminal record | Active | `recovery_required` | Invalidate old authorization; orient current state; run fresh checkpoint |
| Torn trailing terminal record after valid authorization | Active | `recovery_required` | Treat torn record as absent; no completion claim |
| Valid terminal record | Complete | Closed | Never reissue same-goal capability |
| Invalid transition prefix or unsupported version | Active or existing terminal truth | `recovery_required` or closed | Fail closed; no inferred repair |

Process termination before the terminal record therefore never rehydrates a completed goal.
Process termination after the terminal record always rehydrates the goal complete with the
gate closed.

If the terminal record persists but its host response is lost, a retry observes the
persisted terminal state and refuses as duplicate completion. It does not append a second
terminal record.

Capability reissuance after `recovery_required` is outside automatic rehydration. It
requires current-state orientation and a fresh pre-completion checkpoint or a linked new
goal, depending on the observed state. No possibly committed call is replayed.

## Rook Adapter Promotion Contract

The promoted adapter preserves the qualified V5 surface:

```text
search(query)
read(name)
call(name, arguments)
```

For each operation it preserves:

- exact successful `{success, data}` envelope admission;
- exact payload object return with no normalization or copy;
- exact structured `McpToolError` evidence and same-object re-raise;
- refusal of malformed, open, or returned-failure envelopes;
- exactly one source event for every transport-entered call;
- immutable recorded evidence despite later payload mutation; and
- zero retry or fallback transport.

The only new behavior is the cooperative lease wrapper around transport and evidence
recording. Lease metadata does not enter the model-facing payload. Rook source events retain
their existing schemas and ownership.

Failure precedence remains closed:

```text
begin refusal or begin persistence failure
-> raise that lifecycle error; zero transport entry

transport success, then recorder or lease-close failure
-> retain any successfully written source prefix
-> raise a closed adapter-lifecycle error; do not return the payload

transport exception, then recorder or lease-close failure
-> retain any successfully written source prefix
-> leave the lease open
-> re-raise the same transport exception object
```

The last rule preserves the qualified `McpToolError` contract. The unresolved persisted
lease, not exception replacement, makes later completion and recovery fail closed. Secondary
recorder or close failures may be attached as diagnostics outside the exception text, but
must not mutate the authentic exception or synthesize a lease close.

The adapter source is versioned and owned by the Rook repository. Tests import that source
directly. Installer integration, automatic Prime skill discovery, and migration of prior
disposable campaign roots are not included.

## Host Request Admission

Internal lease requests use closed schemas and reject unknown fields before state access.
They are registered only when the goal dispatch controller is configured. Their exact names
and payloads are implementation details of the adapter/Prime integration, not additions to
the documented model API.

Because `rlm.host_request` is itself model-callable, this is API minimization rather than a
security claim. Tests must prove the following distinction:

```text
unmodified adapter path
-> qualified cooperative ordering and fail-closed behavior

direct host request, monkeypatch, or raw transport
-> explicit unqualified containment bypass
```

No test may describe obscurity of the internal request names as authorization.

## Error Behavior

Closed error codes distinguish at least:

```text
goal_missing
goal_not_active
goal_generation_mismatch
gate_not_open
completion_not_pending
lease_in_flight
lease_unknown
lease_mismatch
lease_already_closed
authorization_stale
authorization_expired
budget_not_admissible
persistence_failed
recovery_required
duplicate_completion
```

Human-readable messages may accompany codes but are not parsed for custody or recovery.
Errors do not expose a capability-bearing authorization value.

## Qualification Strategy

All qualification is offline. It uses Prime session fixtures, a strict injected completion
controller, the production Rook adapter source, a fake MCP transport, and fault injection.
No model, Rhino, Grasshopper, Rook MCP server, deployment, network, or provider contact is
authorized.

### Prime causal tests

Tests must prove:

- persisted lease open precedes fake transport entry;
- begin refusal produces zero fake-transport entry;
- an open lease blocks completion authorization;
- `completion_pending` blocks new leases;
- successful close removes exactly the matching lease;
- stale, duplicate, wrong-goal, wrong-generation, and wrong-call close refuse;
- authorization persistence failure leaves the gate open and goal active;
- terminal persistence failure leaves authorization pending and goal active;
- successful terminal persistence makes the goal complete and gate closed;
- same-cell adapter use after completion refuses before fake transport;
- duplicate completion after a lost response appends no second terminal record;
- continuously advancing wall-clock time does not invalidate authorization before deadline;
- the deadline and completion-time budget predicate are enforced;
- steering, supersession, and discrete usage changes invalidate pending authorization; and
- a new goal receives a new generation and cannot inherit old leases or authorization.

### Adapter causal tests

Tests must prove exact ordering:

```text
begin persisted
-> one fake transport call
-> one source event durably recorded
-> end persisted
-> payload return or same-exception re-raise
```

Mutations of the adapter should cause tests to fail when they:

- enter transport before begin succeeds;
- return before source recording or lease close;
- close after a source-recorder failure;
- normalize or copy the payload;
- replace `McpToolError`;
- retry transport;
- bypass the gate for any of `search`, `read`, or `call`; or
- permit a post-completion fake transport call.

### Persistence and rehydration tests

Tests must inject failure or termination at every persisted transition and prove:

- write failure rolls back the candidate session entry and in-memory transition;
- a torn trailing terminal record rehydrates as pre-terminal;
- termination before terminal persistence rehydrates the goal active;
- unresolved leases and pre-terminal authorization rehydrate `recovery_required`;
- termination after terminal persistence rehydrates complete with the gate closed;
- lost terminal response followed by retry returns `duplicate_completion`; and
- no recovery path automatically replays transport, evidence writing, or completion.

### Boundary tests

Tests must state, rather than conceal, that direct `rlm.host_request`, monkeypatching, and raw
transport are outside the qualified claim. No hostile-Python test is permitted to pass merely
because internal protocol names are obscure.

## Production Scope

Expected production owners are limited to:

```text
Prime AgentSession goal/host-request integration
Prime goal and execution-state types
Prime SessionManager rollback-capable persistence use
Prime goal Python skill completion-preparation wrapper
Rook-owned durable rook_full adapter source
```

Focused tests may add fixtures and fake transports in both repositories. Exact file paths and
packaging mechanics are selected in the implementation plan after independent design review.

No changes are admitted to:

- Rhino or Grasshopper handlers;
- Rook receipts or fenced snapshots;
- behavioral predicate vocabularies;
- PlanGraph, Worker, Reviewer, or policy routing;
- MCP result schemas;
- Rook deployment scripts;
- Prime provider adapters;
- arbitrary IPython filesystem, subprocess, or network authority; or
- current campaign evidence.

## Stop Conditions

Stop and return for design review if implementation requires:

- moving Rook transport into Prime;
- remote Rook revocation or a distributed commit protocol;
- custom `fsync`, a database, or another journal;
- parsing exception or error text;
- changing Rook mutation or receipt semantics;
- introducing a second goal orchestrator;
- claiming protection from direct hostile Python; or
- implementing the full semantic checkpoint to qualify terminalization.

## Adoption Claim

A passing slice may establish only:

> On the unmodified durable `rook_full` adapter path, Prime admits Rook transport through
> persisted goal-scoped cooperative leases, terminalizes an authorized goal at one
> Prime-owned persistence linearization point, recovers consistently from the declared
> process-crash cases, and refuses later same-goal adapter calls before transport.

It may not establish:

- power-loss durability;
- secure containment of model-controlled Python;
- correctness of the completion checkpoint's semantic judgment;
- complete Candidate A orchestration;
- live Rook/Rhino behavior; or
- production deployment readiness.
