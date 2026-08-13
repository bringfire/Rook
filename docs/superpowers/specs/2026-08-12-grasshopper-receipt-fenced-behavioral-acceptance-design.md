# Grasshopper Receipt-Fenced Behavioral Acceptance

**Status:** Approved design, amended after independent specification and integration review
**Date:** 2026-08-12
**Baseline:** `bca57582f2f3fa18c72760ff8f068268ed9c11e9`
**Related authoring-routing merge:** `bc5c0b153e1f5828314032c07949d8674e7c0dae`

## Objective

Establish a durable, model-independent boundary for deciding whether a live
Grasshopper authoring result satisfies a reviewed behavioral contract:

```text
model-facing authoring route
-> authentic managed solve-readiness receipt
-> retained latest-terminal-route custody
-> managed wait
-> atomic receipt-fenced gh_snapshot
-> frozen artifact-driven behavioral evaluation
-> pass | fail | incomplete
```

The boundary must let stochastic Actors author and repair naturally while
keeping completion authority deterministic. It must work for ordinary
component graphs and dedicated script components without prescribing a
topology or adding task-specific prompt text.

This design extends the existing solve-receipt registry. It does not add a
second scheduler, receipt system, semantic registry, agent framework, model
Critic, or global mutation-budget mechanism.

## Motivation and Evidence

The retained point-row and XY-grid experiments established four facts:

1. A local Actor can create and repair authentic Grasshopper definitions.
2. A pre-solve structural snapshot can look plausible while output semantics
   are stale, incomplete, or wrong.
3. One-control-at-a-time behavioral probes distinguish a genuine parametric
   relationship from a baseline coincidence without requiring a preferred
   topology.
4. Repeating task-specific evaluators is not sustainable. The point-row and
   grid slices shared control binding, perturbation, restoration, terminal
   point extraction, diagnostics, and simple numeric predicates.

The bounded v1 vocabulary does **not** express the original four-control
`Rows`, `Columns`, `X Spacing`, and `Y Spacing` XY-grid specimen. Its reviewed
Cartesian sequence predicate requires explicit start, step, and count roles
for each axis; the topology-neutral six-control Cartesian test qualifies that
predicate only. It must not be represented as acceptance of the retained
four-control grid intent. That intent remains outside v1 until a separately
reviewed reusable primitive is justified; this amendment does not expand the
vocabulary.

The current product already contains the correct lifecycle authority:

- `GhSolveReceiptRegistry` issues per-document mutation receipts, binds an
  accepted schedule to exact solution lifecycle epochs, supersedes prior
  receipts, and fences reads against document replacement and stale solves.
- `gh_set_value` already returns `solve_readiness_receipt`.
- `gh_wait_for_solve_readiness` already waits on managed lifecycle evidence.
- `gh_inspect_output(readiness_receipt_id=...)` already checks the fence before
  reading volatile data.

The missing handoff is broader receipt production plus an atomic fenced
`gh_snapshot` suitable for topology-neutral behavioral evidence.

## Governing Invariants

### 1. Lifecycle authority stays managed

Only the managed Grasshopper companion may issue, finalize, supersede, or
fence a solve-readiness receipt. Python forwards the exact parsed receipt JSON
value and validates correlation; it does not infer readiness from elapsed time, output
appearance, a short-ID epoch, or an HTTP success value.

### 2. Fallible evidence stays with its phase

A managed terminal owner reserves a receipt before its first possible terminal
host mutation. If any covered mutation commits, later failure must not erase
that receipt or the committed-mutation facts. The owner finalizes the receipt
against the one resulting schedule when possible; otherwise it returns the
receipt in a truthful terminal non-ready state.

Composite script helpers may create a component and prepare pins before their
terminal managed `/gh/script` write. Those earlier operations are not
retroactively receipted. They become behaviorally admissible only when the
final source write returns a ready receipt whose scheduled solve covers the
resulting document. Without that final receipt the pipeline is `incomplete`.

Zero-commit and group-only edits cannot produce a ready receipt under the
unchanged solve policy.

### 3. Freshness is bounded by observed route custody

The registry mutation epoch advances only when `IssueMutation()` runs. A
legacy, preparatory, or out-of-band mutation that does not issue a receipt can
leave an older receipt apparently ready.

Acceptance therefore requires both:

```text
receipt from the latest terminal mutation in the retained tool trace
+ no later observed preparatory or legacy mutation
```

This design does not claim protection from unobserved out-of-band structural
changes. Registry-wide invalidation for all possible Grasshopper mutations is
a separate future slice.

### 4. Fence and read are one callback

`gh_snapshot(readiness_receipt_id=...)` must call `CheckFencedRead()` and
extract the snapshot in the same managed callback. No component, wire,
diagnostic, value, or preview may be read before the fence succeeds.

The structural snapshot embedded in the current `gh_edit` response is captured
before the scheduled solve. It remains a useful edit receipt but is never
behavioral-acceptance evidence.

### 5. Completion is mechanical

The Actor may report success and may receive one externally bounded repair
opportunity, but neither self-report nor a free-form model Critic owns the
verdict. Only admitted fenced evidence evaluated against the frozen acceptance
artifact can produce `pass`.

## Terms

### Solve-relevant mutation

A committed change that may alter topology, inputs, computation, or output and
therefore requires a solve before behavioral evidence is read. In the routes
covered here this includes component creation/deletion, wire connection or
disconnection, value changes, script source writes, and script-pin changes
once followed by the terminal source write.

### Terminal mutation route

A model-facing route that owns the final solve schedule for its committed
solve-relevant changes and returns the corresponding managed
`solve_readiness_receipt`.

### Preparatory mutation route

A route that changes state but intentionally does not establish acceptance
readiness. `gh_set_script_pins` is preparatory: the subsequent script-source
write is the terminal mutation.

### Legacy mutation route

A public mutation route that does not yet participate in this receipt
contract. It may remain product-compatible, but a later successful legacy
mutation makes an earlier receipt ineligible for acceptance.

### Latest terminal mutation

The last successful or partially successful terminal route in the complete
retained tool trace that committed at least one solve-relevant mutation. Its
exact returned receipt is the only receipt eligible for the next accepted
snapshot.

### Behaviorally admissible snapshot

A successful `gh_snapshot` result produced after an atomic managed fence using
the eligible latest-terminal receipt, with exact receipt correlation retained
in the response and trace.

## Closed Route Contract

| Model-facing route | Classification | Receipt owner |
|---|---|---|
| `gh_edit` | terminal only when at least one solve-relevant mutation commits | managed `ApplyEdit` |
| `gh_set_value` | terminal | existing managed `SetValue` path |
| `gh_set_script` without `script` | observational source read | none |
| `gh_set_script` with `script` | terminal | managed `SetScript` path |
| `gh_create_script` | terminal | final managed `/gh/script` write |
| `gh_create_python_script` | terminal alias | exact receipt from shared `gh_create_script` helper |
| `gh_create_csharp_script` | terminal alias | exact receipt from shared `gh_create_script` helper |
| `gh_update_script` | terminal | final managed `/gh/script` write |
| `chirp_create` | terminal | final managed `/gh/script` write reached through the shared script helper |
| `gh_set_script_pins` | preparatory | none; must be followed by `gh_update_script` |

Raw `/gh/create-component` remains a capability-neutral internal primitive and
does not gain policy or receipt exemptions. The dedicated script pipeline owns
the terminal receipt because it owns the final source write and schedule.

Other existing Grasshopper mutation tools are not silently upgraded by this
slice. If one appears after the latest terminal mutation in the retained trace,
acceptance is `incomplete` unless a later covered terminal route commits and
supersedes it with a new receipt.

## Managed Receipt Contract

The existing wire schema remains authoritative:

```json
{
  "schema": "rook.gh_solve_readiness_receipt:v1",
  "receipt_id": "opaque",
  "document_session_id": "opaque",
  "mutation_epoch": 7,
  "solution_run_epoch": 12,
  "completed_solution_run_epoch": 12,
  "status": "ready",
  "reason": null,
  "completion_signal": "solution_end",
  "issued_at": "<managed timestamp>",
  "completed_at": "<managed timestamp>"
}
```

No new receipt schema or Python-generated receipt ID is introduced.

Receipt correlation is intentionally two-stage because the authoring response
is produced before Grasshopper necessarily enters or completes the scheduled
solution:

```text
authoring result
-> authoritative receipt_id
-> authoritative document_session_id
-> authoritative mutation_epoch
-> solution_run_epoch and completed_solution_run_epoch may be null or pre-run

terminal gh_wait_for_solve_readiness result
-> same receipt_id
-> same document_session_id
-> same mutation_epoch
-> authoritative final solution_run_epoch
-> authoritative final completed_solution_run_epoch

fenced gh_snapshot readiness_fence
-> exact identity and epoch equality with the terminal wait receipt
```

The evaluator must not require the authoring-result lifecycle epochs to equal
the terminal values. It requires identity/session/mutation equality across all
three phases, treats the terminal wait receipt as the lifecycle authority, and
requires the fenced snapshot to echo that terminal value exactly.

Every covered terminal model-facing result exposes the managed parsed value at
the same path:

```text
result.data.solve_readiness_receipt
```

For `gh_edit`, the additive field is on the root snapshot-data object alongside
`edit_summary`; it is not buried inside the pre-solve structural snapshot
summary. For script helpers it is a sibling of `script_receipt`. A committed
partial/failure result retains the same path even when the top-level envelope
is unsuccessful. A group-only edit returns no such field. A zero-commit edit
may return its terminal non-ready receipt at that path, but the positive commit
equation still prevents its admission.

### General mutation lifecycle

For a covered managed terminal phase:

```text
validate terminal request and target
-> ensure readiness session
-> reserve receipt before the first mutation owned by that terminal phase
-> perform mutations while retaining committed-mutation facts
-> request exactly one post-mutation solve if any solve-relevant mutation committed
-> finalize exact receipt from schedule outcome
-> return exact receipt even when later route operations failed
```

If receipt reservation fails, no mutation owned by that terminal phase may
begin. For `gh_edit` and `gh_set_value`, that means zero route mutation. A
composite script helper may already have committed preparatory creation or pin
changes; it must preserve their failed-pipeline evidence and return
`incomplete`, never claim readiness.

If no solve-relevant mutation commits:

- the route must not request a solve solely to manufacture readiness;
- any reserved receipt becomes `unknown` with exact reason
  `no_solve_relevant_mutation_committed`;
- no ready receipt is returned; and
- acceptance remains `incomplete` unless a later terminal mutation succeeds.

If a mutation commits but schedule or lifecycle correlation fails, the receipt
is returned with the existing truthful `solver_locked` or `unknown` status and
reason. It cannot authorize a snapshot.

### Direct post-reservation failure shape

`gh_set_value` and direct `gh_set_script` source writes retain their existing
pre-validation and pre-reservation failure strings. Once receipt reservation
succeeds, any failure returns object data with exactly:

```json
{
  "error": "set_value_failed",
  "message": "exact host exception message",
  "solve_relevant_mutation_committed": true,
  "solve_readiness_receipt": {}
}
```

`error` is exactly `set_value_failed` or `set_script_failed` for its owner.
`message` is the exact managed `Exception.Message`, including an empty string;
no fallback or fabricated text is permitted. The commit value is
true when the value/source mutator returned successfully before the later
failure, false when the owner knows no mutation occurred, and null only when a
throwing host mutator leaves commitment unknowable. The receipt is the exact
managed object after reservation/finalization, or null only when receipt
projection itself failed. Null commit or receipt makes the route incomplete.

On known commit, the catch path requests the one post-mutation solve if it was
not already requested, finalizes the exact receipt, and returns it. On known
zero commit, it finalizes terminal non-ready with
`no_solve_relevant_mutation_committed`. On unknown commitment, it finalizes
terminal `unknown` with exact reason `mutation_commit_unknown`; it never claims
readiness. Success responses from both routes add
`solve_relevant_mutation_committed=true` and the exact receipt.

Changing post-reservation direct failures from string data to this object is a
deliberate bounded compatibility correction. Failure text remains in
`message`; pre-reservation errors and all unrelated routes keep their current
shape.

### `gh_edit` commitment rules

`gh_edit` tracks solve-relevant commits independently of top-level success:

```text
created
+ deleted
+ values_set
+ connected
+ disconnected
> 0
-> solve-relevant commit occurred
```

Group operations are deliberately absent from that equation. A group-only
edit retains current visual/group behavior but does not schedule a solve and
cannot produce a ready solve receipt.

A partially successful edit with a positive solve-relevant commit count must:

1. preserve all existing per-operation errors and partial-success semantics;
2. restore standalone solver ownership as today;
3. request the post-mutation solve exactly once;
4. finalize and include its exact managed receipt; and
5. remain eligible for a later fenced read only if that receipt becomes ready
   and no later disqualifying mutation occurs.

An exception after any solve-relevant commit must not collapse to a bare error
string. The failure response retains the committed counts, schedule outcome if
available, and exact receipt. If the route cannot establish a schedule, the
receipt becomes terminal non-ready.

The existing pre-solve structural snapshot and `edit_summary` remain for
compatibility. Their presence, `success`, `partial_success`, short-ID `epoch`,
or plausible topology does not satisfy behavioral evidence admission.

### Script mutation rules

`SetScript` distinguishes read from write exactly as today. Only a source write
issues a solve-readiness receipt.

For a source write:

1. validate the target and script capability;
2. reserve the receipt before changing source;
3. retain the exact component and metadata restoration behavior;
4. schedule once after source recompilation and metadata restoration;
5. finalize the exact receipt; and
6. include it in the managed `/gh/script` response.

`gh_set_script_pins` remains preparatory. It never claims terminal readiness.
The required next `gh_update_script` call writes source and owns the terminal
receipt. A pin-only pipeline, a failed source write, or a partially completed
script pipeline without a final managed receipt is `incomplete`.

Every composite script-helper failure after admission uses this closed data
shape rather than collapsing committed facts into an error string:

```json
{
  "error": "script_pipeline_incomplete",
  "phase": "component_creation",
  "committed_preparatory": {
    "component_created": false,
    "pins_configured": false
  },
  "component": {
    "guid": null,
    "short_id": null
  },
  "final_write": {
    "dispatched": false,
    "success": null,
    "solve_relevant_mutation_committed": null
  },
  "solve_readiness_receipt": null,
  "script_receipt": null
}
```

The object has exactly the keys shown. `phase` is exactly one of
`component_creation`, `pin_configuration`, `source_write`,
`solve_readiness`, or `post_write_verification`. The two committed flags and
`final_write.dispatched` are booleans. `final_write.success` and
`final_write.solve_relevant_mutation_committed` are null before dispatch and
otherwise are the exact booleans returned by the final managed write. Success
never substitutes for commitment: a failed final write may still report a
committed source mutation, and a successful zero-commit response may not claim
one.
Known component identities are nonblank exact host strings; unknown identities
are null. `solve_readiness_receipt` is null until the final managed source
write returns that field and otherwise is its exact parsed JSON value.
`script_receipt` is null until the existing Python summary is constructed and
otherwise retains that exact object. Later helper failure must not erase any
earlier committed fact, component identity, or final-write receipt.

Successful composite helpers expose the same exact
`solve_relevant_mutation_committed` boolean alongside their
`solve_readiness_receipt` and existing `script_receipt`. Failure phases after
the final write copy both fields from that managed response. A missing,
malformed, or contradictory managed commit field makes the pipeline result
incomplete; Python never derives it from the top-level success value.

Python wrappers for all script helpers must propagate the managed
`solve_readiness_receipt` parsed JSON value without rebuilding, reinterpreting,
nesting, or renaming it:

- `gh_create_script`;
- `gh_create_python_script`;
- `gh_create_csharp_script`;
- `gh_update_script`; and
- `chirp_create`.

The existing Python `script_receipt` remains unchanged and separate:

```text
script_receipt
-> pipeline/mutation/verification summary owned by Python

solve_readiness_receipt
-> managed document/solve lifecycle authority
```

Neither object may contain or masquerade as the other.

Post-write verification never uses a fixed sleep. If a helper requests eager
verification, it calls `gh_wait_for_solve_readiness` with the exact captured
managed receipt and proceeds only after a ready terminal result. A timeout or
terminal non-ready result produces the closed `solve_readiness` failure above.
If eager verification is disabled, the helper returns the receipt and defers
verification without sleeping. Existing helper delays are removed rather than
reclassified as readiness evidence.

## Latest-Terminal Trace Admission

Behavioral acceptance consumes the complete retained model/tool trace, not a
receipt copied out of context.

The evaluator accepts one closed projection, not provider-specific event logs:

```json
{
  "schema": "rook.gh_authoring_trace:v1",
  "source_closure": {
    "schema": "rook.gh_authoring_source_closure:v1",
    "owner": "prime_transaction_launcher",
    "row_emitter": "prime_rook_adapter",
    "source_event_count": 1,
    "final_source_sequence": 0,
    "source_log_sha256": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "runtime_log_sha256": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
    "terminal_marker": "agent_end",
    "closed": true
  },
  "events": [
    {
      "sequence": 0,
      "ingress": "canonical_gateway",
      "target": "gh_edit",
      "arguments": {},
      "result": {"success": true, "data": {}},
      "exception": null,
      "dispatch": {
        "status": "dispatched",
        "target_call_count": 1
      },
      "mutation": {
        "classification": "terminal",
        "commit_status": "committed",
        "commit_evidence": {},
        "solve_readiness_receipt": {}
      }
    }
  ]
}
```

The top-level object has exactly `schema`, `source_closure`, and `events`.
`source_closure` has exactly the nine shown fields. Its schema is the displayed
literal; owner is `prime_transaction_launcher` or
`direct_transaction_wrapper`; `row_emitter` is respectively
`prime_rook_adapter` or `direct_transaction_wrapper`; event count is a
nonnegative integer; final sequence is null exactly when the count is zero and
otherwise equals count minus one; both hashes match
`[0-9A-F]{64}`; and `closed` is exactly true. `terminal_marker` is `agent_end`
for Prime or `transaction_closed` for a caller-owned direct transaction and
must be the exact final semantic event in the hashed runtime log.

The accepted raw capability source format is
`rook.gh_authoring_source_log:v1`: strict UTF-8 JSONL without BOM. Its first
row has exactly `schema` and `row_emitter`; schema is the displayed literal and
row emitter is one of the two closed values above. Each following row before
closure is one exact event object shown below, serialized with the canonical
Python serializer. The final row is exactly
`{"type":"closure","source_closure":<the object above>}`.
`source_log_sha256` is computed over the header and event rows, including each
trailing LF but excluding the closure row to avoid circularity.
`runtime_log_sha256` is over the complete exact runtime-owned log bytes.

For Prime, the reviewed `rook_full.search/read/call` adapter wrapper emits each
capability row: it captures exact Python arguments at function ingress and the
exact parsed `{success,data}` value or raised exception at function egress
before returning control to model code. The adapter imports
`rook.gh_behavioral_acceptance` through that package identity and calls the
public `append_canonical_gateway_source_event()` owner; it does not load the
module anonymously, call a private classifier, or duplicate event projection.
It never emits the closure. Prime's
`--mode json` stdout JSONL is the separate runtime log. The outer Prime
transaction launcher observes process termination and stdout EOF, requires
exactly one `agent_end` as the final semantic event, requires all
qualification-owned adapter/kernel children to have exited, hashes both
now-immutable logs, and only then appends the closure row. After `agent_end`,
the only admitted physical suffix is either empty or the exact closed Prime
housekeeping sequence `message_start(ipython_state)`,
`message_end(ipython_state)`, `compaction_end`; the paired state messages must
be identical and every suffix row is included in `runtime_log_sha256`. Any
later user, assistant, tool-execution, mutation, unknown, malformed, or second
terminal event leaves the source log unclosed. Cancellation, forced
termination, missing EOF, missing semantic terminal, or lingering owned
children likewise leaves it unclosed. The Prime native session file and Rhino native session recorder are
corroborating evidence only; neither owns this trace and neither can substitute
for the adapter rows or `agent_end` stream.

For direct `ToolDispatcher` use, an explicit caller-owned transaction wrapper
performs the same ingress/egress capture. After the calling transaction has
irreversibly stopped admitting calls, it writes a separate direct runtime log
containing exactly one canonical JSONL row:

```json
{
  "schema": "rook.gh_direct_transaction_runtime:v1",
  "source_event_count": 1,
  "terminal_marker": "transaction_closed"
}
```

That row uses the canonical serializer and trailing LF. The wrapper hashes it
as `runtime_log_sha256`, hashes the immutable source header/event rows, and
requires its count to equal both the closure count and retained event length,
then appends the source closure. Any attempted call after the terminal marker
is a caller contract violation and invalidates custody.
`ToolDispatcher` remains recorder-free and cannot by itself qualify a trace.
Current Prime or ChatRunner evidence without the corresponding wrapper log
fails closed until that caller integration exists.

The acceptance owner receives both exact raw logs, verifies both hashes and
the runtime terminal marker, validates the source-log closure, and reruns the
reviewed normalizer. A self-reported closure or projection without those bytes
is invalid.

Each event has exactly the eight keys shown. `sequence` is the zero-based
source capability-event number; values are contiguous and strictly increasing
through `final_source_sequence`. `len(events)` must equal
`source_event_count`. A missing final event, valid prefix, duplicated event, or
event after the terminal marker therefore invalidates authoring custody.
`ingress` is exactly
`canonical_gateway`, `direct_dispatch`, or `operator_probe`. `target` is the
exact admitted model-facing or operator tool name. `arguments` is the exact
caller-supplied JSON object before target routing or panel-lock enrichment.
Duplicate JSON keys, non-object arguments, gaps, duplicates, or reordered
events make the trace invalid.

Exactly one of `result` and `exception` is nonnull. A result has exactly
`success` and `data`, where `success` is a boolean and `data` is the exact
normalized internal data value. An exception has exactly `type` and `message`,
both exact strings. For a Python exception, `type` is exactly
`exc.__class__.__module__ + "." + exc.__class__.__qualname__` and must be
nonblank; `message` is exactly `str(exc)`, including an empty string. The
wrapper records subclasses of `Exception` only. `asyncio.CancelledError`,
`KeyboardInterrupt`, `SystemExit`, and any other `BaseException` leave the
transaction unclosed and therefore incomplete. An exception event's dispatch
status is `unknown`, its target call count is null, and mutation
classification/commit status are both `unknown`. Any exception event
establishes complete custody but makes
behavioral admission incomplete; it can never prove zero dispatch or mutation.

Canonical MCP input uses
the target and arguments inside the admitted `rook_tools_call` envelope and
the target's structured `{success,data}` result. Direct dispatch uses its
direct name, exact parameters, and plain internal `{success,data}` result.
Operator probes use their retained exact request and internal result. Text-only
MCP output, a meta-tool result without its correlated target event, or any
normalization that cannot establish those exact values makes the trace
invalid. Every source capability invocation is projected. `rook_tools_search`
and `rook_tools_read` become observational events; an admitted
`rook_tools_call` is projected as its correlated target event. A model-runtime
code cell whose possible capability invocations cannot be fully classified by
the reviewed normalizer makes the trace invalid rather than disappearing.

`dispatch` has exactly `status` and `target_call_count`. Status is
`dispatched`, `refused_before_dispatch`, or `unknown`. Its count is respectively
the integer `1`, the integer `0`, or null. It is derived from retained runtime
dispatch evidence, not inferred from success text. A covered mutation event
with `unknown` dispatch is ineligible. A refusal is admissible after the latest
terminal mutation only when status is `refused_before_dispatch` and the
retained result is a recognized containment, profile, schema, or routing
refusal.

`mutation` has exactly `classification`, `commit_status`, `commit_evidence`,
and `solve_readiness_receipt`. Classification is `observational`, `terminal`,
`preparatory`, `legacy`, or `unknown`. Commit status is `none`, `committed`, or
`unknown`. `commit_evidence` is the exact route-specific object below or null.
The receipt is the exact result field for a terminal route or null; it is never
copied from a later wait result.

The closed route projection table is:

| Event | Classification | Commit evidence |
|---|---|---|
| covered terminal route with completed terminal phase | `terminal` | exact route-specific facts below |
| composite terminal-capable helper stopped after preparatory host mutation | `preparatory` | exact closed script-pipeline facts |
| `gh_set_script_pins` | `preparatory` | `{"success":<bool>,"target_dispatched":<bool>}` |
| public Grasshopper mutation outside the covered route table | `legacy` | `{"success":<bool>,"target_dispatched":<bool>}` |
| current readonly-profile Grasshopper tool, readiness read/wait, or fenced snapshot | `observational` | null |
| unrecognized or malformed Grasshopper event | `unknown` | null |

Covered terminal commit evidence is exact and route-owned:

- `gh_edit` uses exactly `created`, `deleted`, `values_set`, `connected`, and
  `disconnected`, copied as nonnegative integers from `edit_summary`. Commit is
  `committed` exactly when those five sum above zero; group-only or zero-commit
  is `none`; missing/malformed counts are `unknown`. Group-only classification
  also requires the exact caller `groups` array and zero five-counter result;
  no new `edit_summary` field is introduced merely for trace projection.
- `gh_set_value` and direct `gh_set_script` source writes add exactly
  `{"solve_relevant_mutation_committed":<bool>}` to their managed result.
  Missing/malformed evidence is `unknown`.
- Composite script helpers use exactly
  `{"component":{"guid":<string|null>,"short_id":<string|null>},
  "final_write":{"dispatched":<bool>,"success":<bool|null>,
  "solve_relevant_mutation_committed":<bool|null>}}`, copied from the closed
  success/failure fields. Commit is `committed` only when the final source
  write reports its managed commit boolean true and exact receipt. Preparatory
  creation or pins without that final write remain `preparatory`, not a
  successful terminal commit.

The Python acceptance owner encodes the trace for custody as the exact result
of `json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
separators=(",", ":")) + "\n"`, then strict UTF-8 without BOM.
`authoring_trace_sha256` is uppercase SHA-256 over those exact bytes. The
runtime-specific projector must retain its source event hashes separately;
this schema does not claim that canonical and direct raw logs are
byte-identical.

The operator-owned behavioral sequence uses the same event object contract in:

```json
{
  "schema": "rook.gh_probe_trace:v1",
  "termination": {"status": "complete", "error": null},
  "events": []
}
```

The top-level object has exactly those three keys. Every ingress is
`operator_probe`. Termination status is `complete` or `failed`. Error is null
exactly for complete and otherwise is one exact nonnull `probe.error` token.

The expected full sequence is the baseline wait and fenced snapshot followed
by, for each control in artifact order, one `gh_set_value` perturbation, one
wait, one fenced snapshot, one `gh_set_value` restoration, one wait, and one
fenced snapshot. A complete trace equals that sequence exactly. A failed trace
is the exact contiguous prefix through the first failed result or exception
event, or through the last successful event when deterministic local
validation fails before the next dispatch. The injected-executor wrapper must
catch an exception long enough to append the closed exception event and then
stop; it does not fabricate a host result or retry. Its termination error must
match that boundary, and no event may follow it. A retry, skipped middle event,
second failure, extra mutation, or additional snapshot is invalid. Thus
fail-fast evidence remains a valid monotonic prefix while only the full
sequence can yield `probe.status=complete`.
`probe_trace_sha256` uses the same canonical byte and hash equation.

The admission algorithm is:

1. Parse and validate the complete `rook.gh_authoring_trace:v1` artifact
   fail-closed.
2. Identify every covered terminal route result and its committed-mutation
   evidence.
3. Select the latest covered result with a positive solve-relevant commit.
4. Require exactly one structurally valid managed receipt in that result.
5. Reject any later admitted invocation of a Grasshopper route that may mutate
   and lacks a newer terminal receipt. This explicitly includes preparatory
   `gh_set_script_pins`, every legacy mutation route, and a nonterminal
   zero-commit or group-only `gh_edit`. A pre-target containment, profile,
   schema, or routing refusal may remain admissible only when its retained
   result causally proves zero target dispatch and zero mutation.
6. Allow later calls that are observational under the existing public readonly
   profile, plus `gh_solve_readiness` and
   `gh_wait_for_solve_readiness`.
7. Require the selected authoring result, terminal wait result, and fenced
   snapshot to satisfy the two-stage correlation equation: authoring identity,
   document session, and mutation epoch match; the fence exactly matches the
   terminal wait receipt's lifecycle epochs.

Unknown, malformed, truncated, or unclassified later Grasshopper calls make
admission `incomplete`; they are never assumed harmless. This is conservative
trace custody, not a second global mutation registry.

If another covered terminal mutation occurs later, its receipt supersedes the
prior candidate and becomes the only eligible receipt.

## Atomic `gh_snapshot` Fence

### Public request

`gh_snapshot` adds one optional field:

```json
{
  "include_data": true,
  "max_preview_items": 3,
  "readiness_receipt_id": "opaque"
}
```

Omission preserves current unfenced snapshot behavior and response shape.
An empty or whitespace-only value is invalid.

When `readiness_receipt_id` is present, `include_data` must be explicitly true
and `max_preview_items` must be a JSON integer in `1..1000` (not a boolean).
Missing/false data inclusion, zero, a negative value, an oversized value, or a
nonnumeric bound is a request validation failure before fence or snapshot
access. Fenced topology-only reads are deliberately not introduced in this
slice. Without a readiness receipt, existing `include_data` defaults and bounds
remain unchanged.

A nonempty request body must be a valid JSON object. Malformed or non-object
JSON fails before snapshot extraction. This is a deliberate fail-closed raw
endpoint correction; existing well-formed unfenced requests remain compatible.

### Managed callback ordering

When the field is present, the same managed callback must execute:

```text
parse options
-> resolve active Grasshopper document
-> CheckFencedRead(receipt, active document)
-> if refused, return existing structured readiness failure
-> only then enumerate document objects and read topology, values,
   diagnostics, volatile output data, and previews
-> append fence correlation evidence
-> return
```

No helper may precompute snapshot data before `CheckFencedRead()`. The native
proxy continues to forward the request body unchanged; it does not inspect or
reimplement the fence.

### Successful response additions

A fenced success retains the existing snapshot fields and adds exactly the
following two root fields:

```json
{
  "readiness_fence": {
    "readiness_receipt_id": "opaque",
    "document_session_id": "opaque",
    "mutation_epoch": 7,
    "solution_run_epoch": 12,
    "completed_solution_run_epoch": 12
  },
  "behavioral_point_outputs": [
    {
      "component_id": "C7",
      "output_index": 0,
      "output_name": "P",
      "count": 3,
      "complete": true,
      "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
      "error": null
    }
  ]
}
```

All fence values come from the terminal receipt admitted by
`CheckFencedRead()`. An unfenced snapshot omits both additions entirely and
retains its current string-preview behavior.

`behavioral_point_outputs` is the fenced-only typed evidence channel. Each
entry has exactly the seven keys shown. `component_id` is the existing exact
snapshot short ID, `output_index` is a zero-based nonnegative integer, and
`output_name` is the exact host string, including an empty string when the host
returns one. Entries are ordered by existing component order and then output
index.

The managed callback obtains each item from volatile data only after the fence
succeeds. A point item is admitted only when its host `Value` is an actual
`Rhino.Geometry.Point3d`; the three `X`, `Y`, and `Z` values must be finite
JSON numbers. No `ToString()`, culture-sensitive parse, rounding, arbitrary
conversion, or reflection-object serialization may supply a coordinate.
`count` is the exact nonnegative host `DataCount`. `points` retains typed
coordinate triples in host enumeration order up to the request's exact
`max_preview_items` bound.

`complete` is true exactly when `count <= max_preview_items`, enumeration
produces exactly `count` items, and every item is a finite `Point3d`. When
false, `error` is exactly the first applicable token in this precedence:

```text
data_unavailable
-> truncated
-> count_mismatch
-> non_point_item
-> nonfinite_coordinate
```

`truncated` applies whenever `count > max_preview_items`. `count_mismatch` is
considered only when `count <= max_preview_items` and full enumeration still
does not yield exactly `count` items, so ordinary truncation cannot be
misreported as a projection defect.

When complete, `error` is null. An output with no observed point item is not
projected as a point output. A missing candidate, an incomplete entry, or more
than one eligible terminal point output therefore cannot earn behavioral
success.

Pending, superseded, solver-locked, document-replaced, stale-solution,
unknown, expired, evicted, or process-restarted receipts preserve the existing
registry error ownership and return no snapshot data.

## Behavioral Probe Protocol

The first reusable slice supports numeric Grasshopper controls and terminal
point output. It is topology-neutral: it observes control/output behavior and
does not require Series, Cross Reference, Construct Point, a script component,
or any other particular component.

### Baseline admission

The evaluator requires one fenced baseline snapshot tied to the latest
terminal receipt. It binds each declared control role to exactly one admitted
canvas control using the artifact's exact role selector. Missing, duplicate,
malformed, nonadjustable, or out-of-domain controls yield `incomplete` or the
criterion-specific `fail` defined by the artifact; they never trigger a guess.

An admitted numeric control is exactly an existing snapshot component with a
nonblank `C[1-9][0-9]*` short ID, exact nickname selected by the artifact, and
this closed value object:

```json
{"type":"slider","val":0.0,"min":-10.0,"max":10.0}
```

The value object has exactly `type`, `val`, `min`, and `max`; `type` is
`slider`; the other values are finite JSON numbers and not booleans;
`min < max`; and `min <= val <= max`. Integer roles additionally require
mathematically integral `val`, `min`, `max`, and probe values. Missing, extra,
null, nonnumeric, nonfinite, inverted-range, or out-of-range values make
control binding incomplete.

The output selector must resolve exactly one terminal point output from
`behavioral_point_outputs` with `complete=true`, exact count, and complete
typed point multiset. Existing string previews are observational only and
never enter the evaluator. Truncated typed output, multiple eligible terminal
point outputs, unknown data, or non-point values yield
`unproven`/`incomplete` as specified by the criterion. They never earn pass.

`terminal_points` means one typed point output for which no retained flow uses
that exact component-output pair as a source. The snapshot request uses the
artifact's positive bounded `max_preview_items`. Completeness requires the
reported output count to equal the typed point-array length and the array to
contain that many valid point triples. A count larger than the bound is incomplete;
the evaluator does not issue a second read with a larger bound.

### One-control-at-a-time perturbation

For each declared control, in artifact order:

```text
record exact baseline value
-> gh_set_value(guid=bound component short ID, value=one frozen probe value)
-> require one exact managed perturbation receipt
-> gh_wait_for_solve_readiness(perturbation receipt)
-> gh_snapshot(readiness_receipt_id=perturbation receipt)
-> evaluate the complete observed effect
-> gh_set_value(guid=bound component short ID, value=exact original value)
-> require one exact managed restoration receipt
-> gh_wait_for_solve_readiness(restoration receipt)
-> gh_snapshot(readiness_receipt_id=restoration receipt)
-> require exact normalized restoration
```

Exactly one perturbation receipt and one restoration receipt are required per
control. The restoration is a new terminal mutation and therefore must use a
new receipt; the perturbation receipt cannot be reused.

The perturbation snapshot must show the target control's same component ID,
role nickname, minimum, and maximum, with `val` exactly equal to the frozen
probe value. Every other bound control must retain the same component ID,
nickname, minimum, maximum, and value as the immediately preceding restored
baseline. The restoration snapshot must return every bound control to those
exact baseline fields and values. Any mismatch makes the probe incomplete;
output changes alone do not prove that only one control changed.

No second control may be perturbed until restoration is proven. A failed
dispatch, missing receipt, non-ready wait, refused snapshot, incomplete output,
or restoration mismatch makes the evaluation `incomplete`. The evaluator does
not continue in a partially restored state and does not authorize Actor repair
from compromised probe evidence.

### Restoration equality

Restoration compares a closed normalized semantic projection, not incidental
serialization order or canvas display coordinates:

```json
{
  "schema": "rook.gh_behavioral_snapshot_projection:v1",
  "controls": [
    {
      "role": "StartX",
      "component_id": "C1",
      "type": "NumberSlider",
      "nickname": "Start X",
      "value": {"type": "slider", "val": 0.0, "min": -10.0, "max": 10.0}
    }
  ],
  "components": [
    {
      "component_id": "C1",
      "type": "NumberSlider",
      "nickname": "Start X",
      "component_type_guid": null
    }
  ],
  "flows": [],
  "groups": [],
  "relays": [],
  "terminal_output": {
    "component_id": "C7",
    "output_index": 0,
    "output_name": "P",
    "count": 3,
    "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
  },
  "diagnostics": {
    "total": 7,
    "errors": 0,
    "warnings": 0,
    "error_ids": [],
    "warning_ids": []
  }
}
```

The object and every nested object have exactly the shown keys. Controls are
in artifact order and use the admitted closed slider shape. Components are
ordered by numeric short ID and use existing snapshot `type`; nickname is the
exact existing `nick`, or existing `name` when `nick` is absent, or null when
neither is an actual string. `component_type_guid` is the canonical lowercase
D-format value from existing `componentGuid` or null for simple params and
other entries that do not expose it. No GUID is fabricated for a slider.

Flows are exact strings sorted by ordinal value. A group element has exactly
`id`, `nick`, `description`, `colour`, and `members`; the first four values
are strings or actual host null, and members is an ordinal-sorted short-ID
array. Groups are sorted by numeric group ID. Relays are ordinal-sorted exact
IDs. The terminal output is
the admitted complete typed point output with points sorted
lexicographically by numeric `x`, then `y`, then `z`. Diagnostics copy exact
nonnegative counts and normalize absent/null ID arrays to sorted arrays.
Invalid IDs, GUIDs, types, counts, strings, arrays, duplicate values where
uniqueness is required, or any projection exception makes the phase
incomplete.

Fence receipt IDs and solution epochs are deliberately absent from this
restoration-equality object because each restoration owns new values. Every
phase's fence is validated separately against its terminal wait receipt before
this projection is built. Baseline and restoration must have byte-identical
canonical projections under the trace serializer; perturbation uses the same
shape for control-isolation and criterion evaluation but is not equal to the
baseline by construction.

## Frozen Acceptance Artifact

Task semantics live in reviewed data rather than Python branches or Actor
prompts. The first production schema is closed:

```json
{
  "schema": "rook.gh_behavioral_acceptance:v1",
  "intent": "exact reviewed intent",
  "numeric_tolerance": 0.001,
  "controls": [
    {
      "role": "StartX",
      "selector": {"kind": "exact_nickname", "value": "Start X"},
      "value_kind": "number",
      "probe_value": 2.0
    }
  ],
  "output": {
    "kind": "terminal_points",
    "require_complete_multiset": true,
    "max_preview_items": 100
  },
  "criteria": [
    {
      "id": "no_runtime_errors",
      "predicate": "diagnostics_errors_equal",
      "arguments": {"value": 0}
    }
  ]
}
```

The top-level object has exactly `schema`, `intent`, `numeric_tolerance`,
`controls`, `output`, and `criteria`. `intent` is nonblank.
`numeric_tolerance` is a finite nonnegative JSON number used only for observed
point-coordinate comparisons. Counts, selector identities, control values,
receipt correlation, and restoration remain exact.

Numeric comparison preserves integer identity before applying tolerance. In
particular, distinct JSON integers such as `2**53` and `2**53 + 1` cannot
collapse through binary floating-point conversion at zero tolerance.

Each control has exactly `role`, `selector`, `value_kind`, and `probe_value`.
`selector` is exactly
`{"kind":"exact_nickname","value":"<nonblank>"}`. `value_kind` is exactly
`number` or `integer`; an integer probe value must be a JSON integer. The
output object has exactly the three keys shown above, and
`max_preview_items` is an integer in `1..1000`.

At baseline, each probe value must be inside the admitted control range and
must differ exactly from the admitted current value. Integer controls require
mathematically integral baseline and probe values. Failure is `incomplete`,
not a skipped probe.

Each criterion has exactly `id`, `predicate`, and `arguments`. Exact argument
shapes are:

```text
controls_present
-> {"roles": ["Role", ...]}

diagnostics_errors_equal
-> {"value": <nonnegative integer>}

point_count_equals_control
-> {"role": "IntegerRole"}

point_count_equals_product
-> {"roles": ["IntegerRoleA", "IntegerRoleB", ...]}

axis_values_equal_sequence
-> {
     "axis": "x|y|z",
     "start_role": "NumberRole",
     "step_role": "NumberRole",
     "count_role": "IntegerRole"
   }

axes_form_cartesian_product
-> {
     "sequences": [
       {
         "axis": "x|y|z",
         "start_role": "NumberRole",
         "step_role": "NumberRole",
         "count_role": "IntegerRole"
       },
       ...
     ]
   }

axis_equals_constant
-> {"axis": "x|y|z", "value": <finite number>}
```

Roles in criteria must resolve exactly to declared controls. Role arrays are
nonempty and duplicate-free. Cartesian sequence axes are duplicate-free.
Exact schema validation rejects duplicate JSON keys, extra keys, duplicate
roles, duplicate criterion IDs, unsupported selectors, incompatible role
types, nonfinite numbers, or unknown predicates.

Role IDs match `[A-Za-z][A-Za-z0-9_]{0,63}`. Criterion IDs match
`[a-z][a-z0-9_]{0,63}`. Selector values and `intent` are actual JSON strings,
not coerced values; after trimming they must be nonblank, while the retained
value remains byte-for-byte the caller's string. JSON booleans never satisfy a
numeric field. All counts and integer-role values remain within signed 32-bit
range so managed control dispatch and Python evaluation share one closed
domain.

Before model contact the acceptance artifact is written with the exact Python
canonical serializer defined for traces. `acceptance_sha256` is uppercase
SHA-256 over those exact bytes. A noncanonical or hash-mismatched artifact is
invalid rather than silently normalized.

The v1 predicate vocabulary is deliberately small:

| Predicate | Evidence |
|---|---|
| `controls_present` | exact unique role bindings and adjustable ranges |
| `diagnostics_errors_equal` | fenced snapshot diagnostics |
| `point_count_equals_control` | complete point count and one control value |
| `point_count_equals_product` | complete point count and declared control values |
| `axis_values_equal_sequence` | complete point multiset and a closed arithmetic sequence expression from artifact constants/control roles |
| `axes_form_cartesian_product` | complete point multiset and two closed arithmetic sequence expressions |
| `axis_equals_constant` | every complete point coordinate on one axis equals an artifact constant |

The artifact supplies role names, probe values, axes, constants, and arithmetic
relationships. The evaluator supplies only closed predicate semantics. Every
criterion is evaluated on the baseline and after perturbing each control role
referenced by its arguments. `controls_present`,
`diagnostics_errors_equal`, and `axis_equals_constant` are evaluated on every
admitted phase. A criterion passes only when it passes every applicable phase.
This is the causal perturbation rule; there is no separate open-ended
`control_perturbation_matches` predicate.

Adding a new task is data-only when this vocabulary can express it. An
unsupported relationship remains `unproven`; it does not justify hidden model
judgment.

Sequence and Cartesian predicates construct the expected finite coordinate
multiset from the admitted control values. Observed and expected point
multisets are sorted deterministically and matched one-to-one; corresponding
coordinates are equal when their absolute difference is at most
`numeric_tolerance`. No rounding or string equality is used. Counts and
multiplicity must still match exactly.

Reviewed component primitive semantics may remain in existing task artifacts
for static evidence compatibility, but behavioral pass does not require or
prefer those components. When primitive semantics are used, they remain bound
to authoritative component-type GUIDs.

## Evaluation Result

The deterministic result is closed:

```json
{
  "schema": "rook.gh_behavioral_evaluation:v1",
  "status": "pass",
  "criteria": [
    {
      "criterion_id": "no_runtime_errors",
      "status": "pass",
      "failure_ids": [],
      "evidence_refs": [
        "baseline",
        "perturbation:StartX",
        "restoration:StartX"
      ]
    }
  ],
  "probe": {
    "status": "complete",
    "baseline": {
      "readiness_receipt_id": "opaque",
      "snapshot_sha256": "UPPERCASE_SHA256"
    },
    "controls": [
      {
        "role": "StartX",
        "component_id": "C1",
        "original_value": 0.0,
        "probe_value": 2.0,
        "perturbation": {
          "readiness_receipt_id": "opaque",
          "snapshot_sha256": "UPPERCASE_SHA256"
        },
        "restoration": {
          "readiness_receipt_id": "opaque",
          "snapshot_sha256": "UPPERCASE_SHA256",
          "restored": true
        }
      }
    ],
    "error": null
  },
  "source": {
    "acceptance_sha256": "UPPERCASE_SHA256",
    "authoring_trace_sha256": "UPPERCASE_SHA256",
    "probe_trace_sha256": "UPPERCASE_SHA256"
  }
}
```

The result object has exactly `schema`, `status`, `criteria`, `probe`, and
`source`. Every criterion object has exactly `criterion_id`, `status`,
`failure_ids`, and `evidence_refs`; status is `pass`, `fail`, or `unproven`.
Evidence references are exact phase IDs (`baseline`, `perturbation:<role>`, or
`restoration:<role>`) whose retained snapshots contain the observed values.

Criterion objects appear in artifact order and each artifact criterion appears
exactly once. `criterion_id` is the exact artifact ID. `failure_ids` is exactly
`[]` for pass and exactly `[criterion_id]` for fail or unproven; it is never an
open diagnostic vocabulary. `evidence_refs` is an ordered, duplicate-free
array of exact phase IDs in execution order. It includes every phase actually
read for the predicate. Predicates evaluated on every admitted phase therefore
include baseline, each perturbation, and each restoration. A reference to an
absent, later, or unread phase makes the result invalid.

`probe.status` is `complete` or `incomplete`. `baseline` is null until admitted,
and otherwise has exactly the two shown string fields. Every successfully
bound control appears at most once in artifact order; `complete` requires every
declared control exactly once. `perturbation` and `restoration` are null until
their respective retained evidence exists, and otherwise use the exact shapes
shown. `source` has exactly the three uppercase SHA-256 fields shown. Partial
results accumulate monotonically; an incomplete later phase does not erase
earlier retained evidence.

Every receipt ID is an actual nonblank string retained exactly; its syntax is
opaque to Python. Component IDs match `C[1-9][0-9]*`. Roles match the artifact.
Original and probe values are finite JSON numbers, never booleans or null.
`restored` is exactly true whenever a restoration object exists; false is not
a complete restoration. All SHA-256 values match `[0-9A-F]{64}`. Nullability is
limited to `baseline`, `perturbation`, `restoration`, and `probe.error` exactly
as described; no other displayed field accepts null.

Each snapshot hash is over one exact canonical evidence object:

```json
{
  "schema": "rook.gh_fenced_snapshot_evidence:v1",
  "request": {
    "include_data": true,
    "max_preview_items": 100,
    "readiness_receipt_id": "opaque"
  },
  "result": {"success": true, "data": {}}
}
```

The request has exactly the three keys shown and exact artifact bound. The
result has exactly `success` and `data`; only `success=true` can be admitted.
Its fence receipt must equal the request and correlated terminal wait receipt.
The evidence object uses the same canonical UTF-8/sorted-key/no-whitespace/LF
serialization defined for traces. `snapshot_sha256` is uppercase SHA-256 over
those exact bytes. `acceptance_sha256`, `authoring_trace_sha256`, and
`probe_trace_sha256` use their respective canonical source bytes already
defined; source hashes cannot be computed from reconstructed or pretty-printed
objects.

`probe.error` is null or exactly one of:

```text
artifact_invalid
authoring_trace_invalid
probe_trace_invalid
latest_terminal_receipt_missing
later_unfenced_mutation
receipt_correlation_failed
baseline_wait_failed
baseline_snapshot_failed
control_binding_failed
probe_value_invalid
output_incomplete
perturbation_dispatch_failed
perturbation_receipt_invalid
perturbation_wait_failed
perturbation_snapshot_failed
perturbation_control_mismatch
restoration_dispatch_failed
restoration_receipt_invalid
restoration_wait_failed
restoration_snapshot_failed
restoration_mismatch
```

Top-level status is derived exactly:

```text
any evidence-admission, probe, or restoration failure
-> incomplete

otherwise any criterion fail
-> fail

otherwise any criterion unproven
-> incomplete

otherwise all criteria pass
-> pass
```

There is no score and no majority vote. Mechanical topology, semantic
behavior, diagnostics, and operational telemetry remain separately reportable.

Deterministic repair feedback is the exact ordered nonpassing criterion list
with retained evidence. It may describe required outcomes but must not
prescribe component GUIDs, topology, source code, or tool calls. An external
orchestration policy may permit one same-session Actor repair; the evaluator
does not own retries or continuation.

## Implementation Ownership

The expected production owners are limited to:

| Owner | Responsibility |
|---|---|
| `src/Rook/InternalBridge/GhSolveReceiptRegistry.cs` | existing receipt lifecycle and fence authority; no second registry |
| `src/Rook/Handlers/GrasshopperHandler.Readiness.cs` | shared receipt issue/finalize/projection helpers |
| `src/Rook/Handlers/GrasshopperHandler.cs` | `gh_edit`, script-write receipt production, and atomic fenced snapshot |
| `mcp_server/src/rook/server.py` | public schemas, exact script-receipt propagation, canonical dispatch |
| `mcp_server/src/rook/agent/tool_dispatcher.py` | direct-dispatch parity through the same helpers |
| one small pure Python behavioral-acceptance module | artifact validation, caller trace-sink/wrapper primitives, reviewed source normalization and closure checks, trace admission, probe orchestration through an injected executor, and deterministic predicates |
| required row-emitter integration: reviewed Prime `rook_full` adapter or direct transaction wrapper | emit exact capability source rows at function/dispatch ingress and egress; never self-close a Prime run; current callers without the wrapper fail closed; no new model-facing tool |
| required closure integration: outer Prime transaction launcher or direct transaction wrapper | after stdout/process/owned-child termination or direct transaction closure, emit the versioned runtime terminal log, hash both immutable raw logs, and append the exact closure row |

The existing `scripts/grasshopper_point_row_acceptance.py` may become a thin
compatibility CLI over the common module or be retired after its authentic
fixtures move to common tests. Its task-specific evaluation logic must not
remain as a second authority. No grid-specific or third bespoke evaluator is
added.

The acceptance module receives an injected async tool executor. It does not
construct a model, open an MCP transport, resolve a Rhino target, retry a call,
or own process lifecycle. Canonical and direct paths are exercised by their
existing dispatch owners and must expose equivalent receipts/results.
Source-normalizer functions live in this same module; they verify caller-owned
retained bytes and never become a runtime recorder or session owner.

No fifth model-facing API, evaluator service, persistent registry, database,
or campaign runner is introduced.

## Compatibility

- A well-formed `gh_snapshot` without `readiness_receipt_id` retains its current
  request and response behavior. Malformed nonempty JSON now fails closed.
- `gh_edit` retains its current structural snapshot, `edit_summary`, partial
  errors, T*/C* identity correlation, and short-ID epoch behavior. The managed
  receipt is additive.
- `gh_set_value` and script-source writes add the exact managed
  `solve_relevant_mutation_committed` boolean while preserving their existing
  fields. Readiness status/wait and fenced `gh_inspect_output` retain their
  existing receipt schemas.
- Post-reservation `gh_set_value` and direct script-write failures intentionally
  change from string data to the closed object above so committed state and
  receipt evidence survive; their pre-reservation failure strings remain
  unchanged.
- Python `script_receipt` is unchanged.
- `gh_create_script` aliases remain exact delegates.
- `gh_set_script_pins` remains callable and preparatory.
- Raw `/gh/create-component`, `gh_snapshot` shorthand identities, `gh_edit`
  flow strings, receipts unrelated to solve readiness, knowledge, discovery,
  and ChatRunner catalog behavior are outside this change.

## Failure Precedence

For a requested fenced snapshot:

```text
invalid request/body/receipt string
-> request validation failure

Grasshopper or target unavailable
-> existing target failure

receipt missing/evicted/process restarted
-> readiness receipt not found failure

receipt pending/terminal non-ready
-> readiness status failure

document/session/epoch/solution mismatch
-> managed fence failure

only after all gates pass
-> snapshot extraction
```

For evaluation:

```text
malformed/truncated trace or artifact
-> incomplete

no eligible latest terminal receipt
-> incomplete

later preparatory/legacy mutation
-> incomplete

wait or fenced snapshot refusal
-> incomplete

probe/restoration failure
-> incomplete

complete admitted evidence
-> evaluate criteria
```

Failures are retained; they are not repaired, retried, reclassified as semantic
failure, or converted into a guessed snapshot.

## Required Causal Tests

### Managed receipt and edit tests

- A partially successful `gh_edit` that commits a solve-relevant mutation
  retains and finalizes its receipt despite later operation errors.
- An exception after a committed edit preserves counts and its terminal or
  non-ready receipt.
- A zero-commit edit cannot return a ready receipt.
- A group-only edit does not request a solve or return a ready receipt.
- Reservation failure causes zero mutation.
- Direct `gh_set_value` and script-write exceptions after reservation retain
  the exact closed failure object. Known committed, known zero-commit, unknown
  commitment, and receipt-projection failure cases preserve their distinct
  boolean/null and terminal-reason equations.
- Pending, stale-solution, superseded, solver-locked, document-replaced,
  unknown, expired, missing, evicted, and process-restarted receipts refuse fenced
  snapshots with no data read.
- A hostile snapshot fake proves `CheckFencedRead()` occurs before the first
  object, topology, diagnostic, value, or output-data access in the same
  callback.
- A successful authoring result may retain null/pre-run lifecycle epochs; the
  terminal wait supplies final epochs, and a successful fenced snapshot
  matches that wait exactly while all phases retain identity/session/mutation
  correlation.
- Fenced typed point projection accepts only finite host `Point3d` values,
  reports exact counts/completeness, and rejects truncation, count mismatch,
  mixed/non-point items, and nonfinite coordinates without consulting string
  previews.
- A fenced request with omitted/false `include_data` or an invalid/nonpositive
  preview bound fails before fence and data access.
- An unfenced snapshot retains its existing JSON shape.

### Script propagation tests

- Managed source reads issue no receipt.
- Managed source writes issue before mutation, schedule once, and return the
  exact receipt.
- Direct `gh_set_script` source writes preserve that receipt; source reads
  remain observational.
- Pin preparation alone is nonterminal.
- Failed or partial script pipelines without the final source-write receipt are
  incomplete and retain the exact closed phase/commit/component/write object.
- A failed managed final write with a committed source mutation retains
  `solve_relevant_mutation_committed=true` and its exact receipt; success and
  commitment are independently tested.
- `gh_create_script`, both aliases, `gh_update_script`, and `chirp_create`
  preserve the exact managed receipt parsed JSON value.
- `script_receipt` and `solve_readiness_receipt` remain distinct siblings.
- Canonical MCP and direct `ToolDispatcher` expose identical receipt values and
  failure behavior.
- Post-write verification waits on the captured solve-readiness receipt or is
  explicitly deferred; no fixed sleep can authorize errors, snapshots, or
  completion.

### Trace and evaluator tests

- Canonical gateway, direct dispatch, and operator records project to the
  exact closed trace event schema without losing caller arguments, result
  envelopes, dispatch counts, route classification, or commit evidence.
- Prime adapter source rows capture exact `rook_full` function ingress and
  parsed egress; the separate Prime JSON event stream supplies exactly one
  final semantic `agent_end` and its optional closed housekeeping suffix. Rhino native session evidence cannot substitute for
  either. A direct caller wrapper closes only after `transaction_closed`.
- The Prime adapter cannot write its own closure. Only the outer launcher may
  close after process termination, stdout EOF, final semantic `agent_end`, its
  optional closed housekeeping suffix, and zero
  lingering owned children. A premature adapter closure refuses.
- The direct transaction runtime log has the exact one-row versioned shape,
  count, terminal marker, serialization, and hash; a call after closure
  invalidates it.
- Missing adapter/wrapper rows, a missing runtime log, hash mismatch, or a
  self-reported projection without both raw sources fails closed.
- A caller/executor exception is retained as the closed exception event with
  deterministic module-qualified Python type and exact possibly-empty message,
  unknown dispatch/mutation, and incomplete status without retry. Cancellation
  and other `BaseException` paths leave the transaction unclosed.
- A source closure with an incorrect hash/count/final sequence, missing or
  nonfinal runtime terminal marker, valid-prefix truncation, or unclosed direct
  dispatcher caller refuses admission. Direct dispatch with a caller-owned
  valid closure remains equivalent after normalization.
- Noncontiguous/duplicate sequences, duplicate JSON keys, text-only target
  results, unknown dispatch, malformed commit evidence, extra events, and
  canonical/direct substitution all fail closed.
- A fail-fast probe retains the exact prefix and specific terminal error; a
  middle omission or any event after failure invalidates the probe trace. Only
  the complete finite sequence may report complete.
- Canonical trace serialization and uppercase SHA-256 are stable across key
  order and reject nonfinite numbers or noncanonical source custody.
- The latest covered terminal route receipt is admitted using the exact
  route-specific positive-commit equation.
- A later successful preparatory or legacy mutation refuses the older receipt.
- A later covered terminal mutation replaces the eligible receipt.
- An unclassified later Grasshopper call fails closed.
- The evaluator refuses the structural snapshot embedded in `gh_edit` even if
  its topology and errors appear successful.
- Each behavioral control requires exactly one perturbation receipt and one
  restoration receipt.
- A perturbation receipt cannot fence the restoration snapshot.
- An admitted control has the exact slider value shape, finite ordered range,
  and role-appropriate integral constraints.
- Every control changes alone: the target exactly reaches its frozen probe,
  all other bound controls remain equal to the preceding restored baseline,
  and a second simultaneous change refuses.
- Restoration mismatch or any missing/failed call yields `incomplete`.
- Baseline/restoration equality uses the exact closed behavioral projection;
  slider identity relies on existing type/short-ID fields rather than a
  fabricated component GUID, and diagnostics/groups/relays have deterministic
  null and ordering rules.
- Existing string previews, truncated typed points, or incomplete typed data
  cannot establish complete count, sequence, or Cartesian-product predicates.
- Criterion results retain exact ordered phase references including every
  restoration phase used by diagnostics or other all-phase predicates;
  failure IDs, identifiers, nullability, and hash inputs obey the closed
  result contract.
- Unknown predicates refuse the artifact. Unknown components cannot supply
  static causal semantics, but a complete behavioral probe may still establish
  a topology-neutral predicate without identifying those components.
- Authentic retained point-row evidence continues to classify the reviewed
  Opus result as pass and the reviewed Qwen result with the two established
  failures.
- The retained failed XY-grid evidence remains nonpassing for the established
  Columns/Rows behavioral defects.
- No model, network, Rhino, Grasshopper, MCP process, or live canvas is needed
  for the pure contract tests.

### Structural boundary tests

- No second receipt registry, scheduler, sleep/poll readiness loop, or
  task-specific evaluator appears. ToolDispatcher gains no session recorder;
  caller-owned source closure remains mandatory.
- Literal script helper routes retain one final `/gh/script` receipt source.
- Native proxy forwarding remains body-transparent.
- Existing T*/C*, flow, edit, discovery, and Python script-receipt contracts do
  not change except for the approved additive receipt, commit, fenced typed
  evidence, and closed script-pipeline failure fields.

## Alternatives Considered

### 1. Existing managed receipts plus fenced snapshots — selected

This reuses the only owner that observes mutation issuance and Grasshopper
solution lifecycle. Trace custody closes the known gap for later observed
legacy/preparatory mutations.

### 2. Sleep, poll, or compare snapshot epochs — rejected

Elapsed time and the short-ID registry epoch do not prove that the requested
solution completed or that output data belongs to the latest mutation.

### 3. Synchronous solve inside mutation routes — rejected

It changes solver ownership, risks UI-thread reentrancy and Chirp timeouts, and
duplicates the established asynchronous lifecycle path.

### 4. Put all mutations behind a new transaction service — rejected

That is a new orchestration framework and receipt registry. The existing
managed lifecycle authority already provides the necessary primitive.

### 5. Model Critic as final judge — rejected

The isolated Critic experiment improved diagnosis but missed a cardinality
defect and failed protocol bookkeeping. Model intelligence may advise repair;
it does not own completion.

### 6. Continue adding bespoke evaluators — rejected

The XY-grid experiment demonstrated the cost. Frozen data plus a small closed
predicate vocabulary is the durable boundary.

## Explicit Non-Claims

This design does not prove or provide:

- protection from unobserved out-of-band Grasshopper mutations;
- registry-wide invalidation for every legacy route;
- acceptance from a runtime or direct-dispatch caller that cannot retain and
  close its complete source trace;
- universal semantic understanding of arbitrary Grasshopper definitions;
- automatic role discovery without reviewed selectors;
- completeness when output previews are truncated;
- a global authoring call budget or model-efficiency policy;
- a model Critic, planner/executor framework, campaign runner, or score;
- synchronous solving, session pooling, or latency optimization;
- a new public tool for acceptance; or
- success of any future live Actor run before separate qualification.

## Anti-Quagmire Stop Conditions

Stop and return for design review if implementation requires:

- a second receipt registry or mutation epoch;
- a new solve scheduler or synchronous-solve path;
- sleeps, blind polling, or output-change guessing for readiness;
- policy inside raw `/gh/create-component`;
- changes to T*/C*, edit flow, snapshot shorthand, discovery, or knowledge;
- a semantic component registry, embeddings, DSPy, or model judge;
- more than one common behavioral-acceptance module;
- a grid-specific, third bespoke, or prompt-tuned evaluator;
- a runtime-wide mutation budget in this slice; or
- live model/host contact before inert implementation review and separate
  authorization.

## Completion Boundary

The implementation is ready for live qualification only when inert tests prove:

```text
latest-terminal-route custody
+ source-log closure and complete normalized authoring trace
+ exact managed receipt propagation
+ managed wait
+ same-callback fence-before-read typed snapshot
+ one-receipt perturbation and one-receipt restoration
+ deterministic artifact evaluation
```

The first live qualification must use a fresh disposable canvas and a frozen
artifact. It may allow at most one same-session Actor repair under separately
reviewed orchestration. A non-ready receipt, later unreceipted mutation,
incomplete probe, or failed restoration stops as `incomplete`; it does not
authorize cleanup, fallback, or another run.
