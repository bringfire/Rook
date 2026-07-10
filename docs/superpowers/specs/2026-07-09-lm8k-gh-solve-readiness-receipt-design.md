# LM8K Grasshopper Solve-Readiness Receipt Design

**Status:** Draft for review
**Date:** 2026-07-09
**Scope:** Product-level Grasshopper mutation/read readiness receipt; design only

## 1. Purpose

LM8K replaces probe-local settle polling with an authoritative product receipt
for Grasshopper mutation/read readiness.

The narrow claim is:

```text
A successful managed gh_set_value mutation can issue a document-scoped
readiness receipt, wait for an authoritative post-mutation solution completion,
and fence one gh_inspect_output read so the returned output is known to belong
to that exact latest managed mutation.
```

LM8K addresses the operational seam measured by LM8G and LM8J. LM8J accepted
all 20 affine scalar attempts, but 9 of 20 required a second verifier read.
That is evidence that a completed scheduling call is not an authoritative claim
that a downstream output is ready to read.

LM8K is not a scalar-reasoning, Worker, Planner, topology-authoring, or
repeatability slice.

## 2. Current Boundary and Gap

The managed Grasshopper layer already owns facts Python cannot know:

```text
active canvas and document
canvas edit readiness
solver enablement and lock state
safe post-mutation asynchronous scheduling
document SolutionState telemetry
```

`GrasshopperHandler.RequestPostMutationSolve(...)` deliberately schedules an
asynchronous solution without requesting synchronous recompute. The current
`GhSolveReadinessCoordinator` repairs solver enablement during Rook-managed
document transitions, but does not track post-mutation solution completion.
`gh_solve` reports that a solution was scheduled; it does not report that the
scheduled solution completed. `SolutionState` remains telemetry only.

LM8F, LM8I, and LM8J therefore contain bounded read-after-solve loops. Those
loops are useful evidence, but they are not the durable product contract. They
remain unchanged in LM8K.

## 3. Design Decision

LM8K uses a managed lifecycle-completion receipt as the authoritative source
of truth.

```text
Managed Grasshopper companion / bridge
  owns document sessions, lifecycle subscription, mutation and solution-run
  epochs, receipt state, waiter signaling, supersession, and bounded retention

Native callback bridge
  exposes the managed operations through the existing native HTTP surface

Python MCP server
  advertises and forwards the readiness operations; it does not poll, sleep,
  infer readiness, or interpret solver state

Probe scripts
  are future consumers of the product receipt; they do not own new readiness
  policy in this slice
```

The implementation adds a focused managed component:

```text
GhSolveReceiptRegistry
```

and a focused `GrasshopperHandler` readiness partial. It must not add a large
polling or timing subsystem to `mcp_server/src/rook/server.py` or expand the
existing monolithic `GrasshopperHandler.cs` unnecessarily.

## 4. Authoritative Lifecycle Correlation

### 4.1 Required signals

`SolutionState == idle`, an elapsed delay, or a successful scheduling response
is never proof of output freshness.

A receipt may become `ready` only from an authoritative managed lifecycle
completion signal such as `SolutionEnd`, correlated to a post-schedule solution
start or an equivalent schedule-bound execution signal verified against the
Grasshopper runtime API during implementation.

The registry tracks independent monotonic sequences per managed document
session:

```text
mutation_epoch
solution_run_epoch
completed_solution_run_epoch
```

### 4.2 Race-safe transition

For mutation epoch 13, the required transition is:

```text
confirm lifecycle subscription and managed document session
-> register pending mutation epoch 13
-> perform the value mutation
-> schedule one safe asynchronous solution
-> observe an authoritative post-schedule solution start
-> bind solution_run_epoch 42 to receipt 13
-> observe matching authoritative completion for run 42
-> advance completed_solution_run_epoch to 42
-> mark receipt 13 ready and signal waiters
```

The pending mutation registration occurs before mutation/scheduling so a fast
completion cannot be missed. However, a `SolutionEnd` observed without a
matching post-schedule start is ignored for that receipt. In particular, an
older solution that was already in flight when mutation 13 was registered may
not satisfy mutation 13.

If lifecycle subscription, callback ordering, run identity, or start/end
correlation is missing or ambiguous, the receipt resolves `unknown`. Duplicate
and out-of-order callbacks never advance a receipt.

The lifecycle callback is brief and runs on the Grasshopper thread. It updates
registry state and signals waiters only; it performs no output read, HTTP work,
or additional solve.

Waiter continuations must run asynchronously from the lifecycle callback. A
completion signal must never resume HTTP work inline on the Grasshopper thread.

## 5. Receipt Contract

### 5.1 Opaque public authority

Public callers supply only:

```json
{
  "readiness_receipt_id": "opaque-id"
}
```

The managed registry generates a cryptographically random, non-derivable
identifier of at least 128 bits. It is a capability-shaped lookup, not an
authentication mechanism; existing transport and tool authorization continue
to apply.

Callers must not provide or reconstruct authority from document or epoch
fields. The registry resolves the opaque ID for every status, wait, and fenced
read operation.

### 5.2 Receipt snapshot

Every receipt/status response uses this schema:

```json
{
  "schema": "rook.gh_solve_readiness_receipt:v1",
  "receipt_id": "opaque-id",
  "document_session_id": "...",
  "mutation_epoch": 13,
  "solution_run_epoch": 42,
  "completed_solution_run_epoch": 42,
  "status": "ready",
  "reason": null,
  "completion_signal": "solution_end",
  "issued_at": "2026-07-09T00:00:00Z",
  "completed_at": "2026-07-09T00:00:01Z"
}
```

Before a post-schedule run starts, `solution_run_epoch` is `null`. Before the
matching run completes, `completed_solution_run_epoch` reflects the most
recent completed run for the document and cannot satisfy the receipt.

Receipt states are exactly:

```text
pending
ready
superseded
document_replaced
solver_locked
unknown
```

`timeout` is deliberately not a receipt state. It is an outcome of one wait
operation; a pending receipt may be inspected or waited on later while it
remains valid.

Terminal non-ready snapshots carry a stable `reason`, for example
`receipt_expired`, `schedule_unavailable`, or
`lifecycle_correlation_ambiguous`. The reason explains a terminal state; it
does not change the outer operation envelope.

## 6. Document Lifetime, Bounds, and Supersession

Receipts are process-local and valid only for one managed GH document session.
Each attachment to an active managed document gets a generated
`document_session_id`; epochs restart in each new session.

On same-process document open, close, new, or replacement:

```text
pending waiters are signaled
existing receipts become document_replaced
no receipt is rebound to a new document
```

On companion restart, the former process has no registry state or waiters to
signal. A pre-restart opaque ID is absent in the new process and therefore
returns the unknown-ID operation failure
`readiness_receipt_not_found_or_evicted_or_process_restarted`. This is
semantically unknown, not a synthetic receipt record; it must never be rebound
to a new document session.

The registry has fixed process-wide bounds:

```text
active/pending receipts: 64
pending expiry: 10 minutes -> unknown / receipt_expired
terminal receipt and tombstone capacity: 256
terminal/tombstone expiry: 15 minutes
```

`ready` is a terminal record and remains available for its terminal retention
window so a fenced read can consume it. Before registering a mutation, the
registry rejects exhaustion with:

```text
readiness_registry_capacity_exceeded
```

It must reject before mutating any live value.

Active and terminal pressure are handled separately and deterministically:

```text
1. Purge expired terminal records.
2. Transition expired pending records to terminal unknown / receipt_expired.
3. Re-check active capacity; only 64 active/pending records rejects a mutation.
4. Before inserting a terminal record, purge again and, if needed, evict the
   oldest terminal record by monotonic terminalized-at time, then insertion
   order as the stable tie-breaker.
```

Terminal-store pressure never rejects a new mutation. It may shorten a terminal
record's nominal 15-minute retention window. An ID whose terminal record was
evicted is absent and returns
`readiness_receipt_not_found_or_evicted_or_process_restarted`; it is not
silently rebound or treated as ready.

Supersession occurs immediately when a newer managed mutation epoch is issued,
not when that mutation completes:

```text
issue mutation epoch 13
-> receipt for mutation epoch 12 becomes superseded immediately
```

The registry reports supplied and current epochs as bounded provenance, without
exposing unrelated document internals.

## 7. Public Operations

### 7.1 Common operation envelopes

A registry lookup that resolves an existing receipt record is an operation
success, regardless of whether the record is terminal:

```json
{
  "success": true,
  "data": {
    "receipt": {
      "schema": "rook.gh_solve_readiness_receipt:v1",
      "status": "superseded"
    }
  }
}
```

Thus `ready`, `pending`, `superseded`, `document_replaced`, `solver_locked`,
and `unknown` are receipt states, not transport failures. A syntactically
invalid request, invalid timeout, unknown/evicted ID, or duplicate active wait
is an operation failure with a stable error code. For example:

```json
{
  "success": false,
  "data": {
    "error": "readiness_receipt_not_found_or_evicted_or_process_restarted"
  }
}
```

`gh_wait_for_solve_readiness` uses exactly these wait outcomes:

```text
ready     - receipt was ready at entry or became ready while waiting
timeout   - caller deadline elapsed; receipt remains pending
terminal  - receipt was or became superseded, document_replaced, solver_locked,
            or unknown
```

Every successful wait response carries a receipt snapshot. The terminal
receipt state, rather than a second wait-specific error vocabulary, explains
why `wait_status` is `terminal`.

### 7.2 `gh_set_value` receipt emission

LM8K instruments only the measured `gh_set_value` mutation path. The registry
is generic for later mutators, but `gh_connect`, `gh_delete`, `gh_edit`,
script writes, and other mutations do not emit receipts in v1.

For a valid value mutation:

```text
validate target and document
-> enforce registry capacity before mutating
-> establish the document session and attempt authoritative lifecycle subscription
-> issue the new mutation epoch and opaque receipt ID
-> supersede older receipt records for that session
-> perform the mutation
-> request one existing safe asynchronous post-mutation solution
-> return a readiness receipt snapshot
```

The returned receipt is `pending` only when lifecycle subscription is
authoritative and scheduling is accepted. If lifecycle subscription is
unavailable or ambiguous, `gh_set_value` preserves its existing mutation
behavior but returns a terminal `unknown` receipt; it makes no freshness claim.
If mutation fails after reservation, the reserved receipt terminates as
`unknown` and can never remain pending. If the solver is locked, the receipt
terminates as `solver_locked`. If scheduling cannot be confirmed or later
lifecycle correlation becomes unavailable, the receipt terminates as `unknown`.

LM8K does not add a second solve call after `gh_set_value`; the existing
managed safe-solve policy remains the only scheduling authority.

The existing `gh_set_value` success meaning remains unchanged. On a successful
mutation, its existing data fields gain one additive nested field:

```json
{
  "Guid": "existing-guid-shape",
  "Type": "slider",
  "NewValue": 7.5,
  "solve_readiness_receipt": {
    "schema": "rook.gh_solve_readiness_receipt:v1",
    "status": "pending"
  }
}
```

If the mutation itself fails after an internal reservation, the outer operation
retains its existing failure semantics and error shape. The registry terminates
the internal reservation as `unknown`, but does not expose it as authority in a
successful mutation response.

### 7.3 `gh_solve_readiness`

This new operation resolves an opaque receipt ID immediately. It never waits,
sleeps, polls, reads output, or starts a solve.

For a known receipt, it returns the successful common envelope with a
`rook.gh_solve_readiness_receipt:v1` snapshot. Absent, expired-and-evicted, or
post-restart IDs use the common unknown-ID operation failure envelope.

### 7.4 `gh_wait_for_solve_readiness`

This new operation accepts:

```json
{
  "readiness_receipt_id": "opaque-id",
  "timeout_ms": 10000
}
```

Timeout bounds are:

```text
default: 10,000 ms
minimum: 1 ms
maximum: 300,000 ms
```

Invalid values fail before waiting. The wait occurs off the Rhino/GH UI thread
on a managed completion signal; it does not sleep-poll, infer time, read
output, or initiate another solve.

One active wait is allowed per pending receipt:

```text
terminal receipt: return immediately; no waiter ownership
pending receipt without a waiter: atomically acquire ownership and wait
pending receipt with a waiter: reject readiness_wait_already_active
```

Timeout, exception, observable client disconnect, document replacement,
supersession, and completion all release waiter ownership. Immediate status
lookups are always allowed and never acquire it.

The wait response separates wait outcome from receipt state:

```json
{
  "schema": "rook.gh_solve_readiness_wait_result:v1",
  "wait_status": "ready",
  "receipt": { "schema": "rook.gh_solve_readiness_receipt:v1" }
}
```

`wait_status: "timeout"` returns the still-pending receipt snapshot.

### 7.5 Receipt-fenced `gh_inspect_output`

`gh_inspect_output` remains backward compatible without a
`readiness_receipt_id`:

```text
existing behavior remains unchanged
output freshness is not certified
```

With an opaque `readiness_receipt_id`, managed receipt validation and output
extraction occur together on the Grasshopper thread. The read requires:

```text
receipt exists
receipt status is ready
receipt document session matches the active managed document session
receipt mutation epoch equals the current managed mutation epoch
receipt solution-run epoch equals the latest completed solution-run epoch
no newer solution run is active, pending completion, or already completed
```

If any later solution run is active or completed, the fenced read fails closed
with `readiness_receipt_stale_solution_run` and performs no output extraction.
It reports only bounded supplied/current run provenance. The read never reports
run 42 provenance after run 43 has started or completed.

LM8K's exactness claim is intentionally limited to the managed mutation and
observed solution lifecycle stream for the current document session. It cannot
certify the absence of arbitrary out-of-band document changes that neither
register a managed mutation nor produce an observable lifecycle run. Such
changes are outside the v1 claim and must not be described as globally detected
document freshness.

The response adds bounded provenance:

```json
{
  "readiness_fenced": true,
  "readiness_receipt_id": "opaque-id",
  "document_session_id": "...",
  "mutation_epoch": 13,
  "solution_run_epoch": 42,
  "completed_solution_run_epoch": 42
}
```

The fenced read never waits implicitly and never falls back to an unfenced
read. Callers explicitly wait first.

For a known but non-ready receipt, a fenced read is an operation failure and
returns no output data. Its bounded error envelope includes the receipt
snapshot:

```json
{
  "success": false,
  "data": {
    "error": "readiness_receipt_superseded",
    "receipt": {
      "schema": "rook.gh_solve_readiness_receipt:v1",
      "status": "superseded"
    }
  }
}
```

The error mapping is exact: `pending` maps to
`readiness_receipt_not_ready`; `superseded`, `document_replaced`, and
`solver_locked` map to their same-named receipt errors; `unknown` maps to
`readiness_receipt_unknown` except when `reason == receipt_expired`, which maps
to `readiness_receipt_expired`.

Public failure/reason codes include:

```text
readiness_receipt_not_ready
readiness_receipt_superseded
readiness_receipt_document_replaced
readiness_receipt_solver_locked
readiness_receipt_unknown
readiness_receipt_expired
readiness_receipt_not_found_or_evicted_or_process_restarted
readiness_receipt_stale_solution_run
readiness_registry_capacity_exceeded
readiness_wait_already_active
```

## 8. Native and Python Exposure

The native/managed callback ABI must expose the new status and wait operations
and preserve registration parity. The current generic native bridge
`ExecuteApiResponseCallback(...)` marshals its operation to the GH UI thread
and blocks there for completion. LM8K must not use that helper for
`gh_wait_for_solve_readiness`.

Instead, LM8K adds a dedicated worker-path bridge callback for readiness waits:

```text
HTTP worker -> managed registry wait -> managed completion signal -> HTTP worker
```

That callback may occupy an HTTP worker thread, but it must never invoke the
main-thread dispatcher, run the wait on the Rhino/GH UI thread, or block the
lifecycle callback that signals it. Receipt-fenced `gh_inspect_output` remains
a managed GH-thread operation because its validation and extraction are one
atomic read gate.

Python adds thin tool schemas and direct dispatch for:

```text
gh_solve_readiness
gh_wait_for_solve_readiness
```

Python forwards the optional `readiness_receipt_id` for
`gh_inspect_output`. It must not add polling, `asyncio.sleep`, solver-state
inference, receipt interpretation, or a broad `server.py` refactor.

For `gh_wait_for_solve_readiness`, Python must also pass an explicit per-call
HTTP transport timeout of requested `timeout_ms` plus a fixed bounded response
grace (LM8K v1: 5 seconds). The global bridge read timeout is not sufficient
for a valid 300,000 ms receipt wait. This transport budget prevents Python from
truncating the managed wait; it does not alter receipt status, add a retry, or
become a second readiness policy.

## 9. Deterministic Proof Surface

The implementation PR uses managed lifecycle fakes and transport fakes only; it
makes no live Rhino/GH evidence run.

One pre-registry exception is allowed because LM8K's core correlation contract
depends on real companion lifecycle ordering: after Task 0's adapter is built,
an implementer may perform one local, debug-deployed, non-evidence lifecycle
preflight before beginning registry work. It must use a temporary DEBUG-only
attachment hook that resolves the active canvas/document, attaches the Task 0
solution and canvas adapters, records callback ordering for one existing
`gh_solve`, disposes both subscriptions, and is removed before the Task 0
commit. It creates no public route, no `probe_runs` artifacts, no curated
evidence, and establishes no product success claim. Its only purpose is to
confirm the installed lifecycle contract and stop implementation if the
required schedule-return/start ordering does not hold.

Required deterministic coverage includes:

```text
pending -> correlated start -> matching completion -> ready
completion without matching post-schedule start does not satisfy a receipt
duplicate and out-of-order callbacks cannot advance readiness
later solution run started or completed rejects a fenced read as stale-run
waiter signaled by matching completion
wait timeout leaves the receipt pending
one active waiter per pending receipt; ownership releases on every exit path
wait callback never enters the GH main-thread dispatcher or UI invocation path
waiter completion resumes asynchronously rather than inline on the lifecycle callback
document replacement signals waiters and tombstones old receipts
solver locked
lifecycle subscription or correlation unavailable -> unknown
mutation failure cannot leak a pending receipt
new mutation supersedes an older receipt immediately
capacity exhaustion rejects before mutation
active and terminal expiry use monotonic elapsed time
terminal capacity evicts the deterministic oldest terminal record without blocking mutation
known terminal receipt status uses a successful lookup envelope
wait uses exactly ready, timeout, and terminal outcome envelopes
successful gh_set_value keeps its existing success meaning and nests one receipt snapshot
same-session ready receipt permits a fenced read
cross-session, pending, unknown, superseded, and expired receipts reject reads
receipt validation and output extraction occur on the GH thread
unfenced gh_inspect_output remains compatible
native/managed ABI registration and native route mapping stay in parity
Python tool schemas and dispatch remain thin
```

## 10. Post-Merge Live Smoke

No live run occurs in the implementation PR.

Post-merge evidence is one dedicated deterministic smoke with no Worker,
Planner, model call, or LM8F/I/J behavior change:

```text
fresh GH document
-> create editable slider at 0.0 and offset slider at 0.0
-> create Addition and wire editable -> A, offset -> B
-> establish baseline fixture solve/readiness separately
-> gh_set_value(editable, 7.5) returns a pending receipt
-> gh_wait_for_solve_readiness(receipt) returns ready
-> one receipt-fenced gh_inspect_output(Addition R, receipt) returns 7.5
```

Baseline fixture readiness is setup-only. The LM8K evidence claim starts at the
receipted `gh_set_value` mutation.

Canonical smoke success requires:

```text
gh_set_value emits a pending receipt
wait returns ready from the correlated solution run
one receipt-fenced gh_inspect_output succeeds on its first read
observed output is 7.5
freshness provenance matches the latest mutation, session, and run epochs
no polling or sleep occurs after gh_set_value
```

## 11. Scope and Interpretation

LM8K intentionally excludes:

```text
LM8F, LM8I, and LM8J behavior changes
Worker or Planner changes
scalar reasoning changes
new GH mutation migrations beyond gh_set_value
gh_edit changes
probe-level retry or replacement attempts
server.py timing loops or broad server refactors
live validation in the implementation PR
```

If the post-merge smoke passes, it proves one managed `gh_set_value` path can
produce a document-scoped, lifecycle-correlated receipt that fences one output
read. It does not prove receipt coverage for every GH mutation, readiness for
large definitions, or any Worker/Planner capability.

If it fails, the result is readiness-receipt product evidence. It must not be
reframed as scalar reasoning or worker behavior.
