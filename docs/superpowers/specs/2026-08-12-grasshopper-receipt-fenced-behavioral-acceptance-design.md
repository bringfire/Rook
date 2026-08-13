# Grasshopper Receipt-Fenced Behavioral Acceptance

**Status:** Approved design, pending independent specification review
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

## Latest-Terminal Trace Admission

Behavioral acceptance consumes the complete retained model/tool trace, not a
receipt copied out of context.

For canonical gateway use, the trace record is interpreted as the target name
and arguments inside `rook_tools_call`; `rook_tools_search` and
`rook_tools_read` remain discovery observations. Direct-dispatch records use
their direct tool names. Both paths must yield the same ordered route view.

The admission algorithm is:

1. Parse the complete retained trace fail-closed.
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
7. Require the wait result and fenced snapshot to echo the selected receipt's
   identity and lifecycle epochs exactly.

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

### Successful response addition

A fenced success retains the existing snapshot fields and adds exactly:

```json
{
  "readiness_fence": {
    "readiness_receipt_id": "opaque",
    "document_session_id": "opaque",
    "mutation_epoch": 7,
    "solution_run_epoch": 12,
    "completed_solution_run_epoch": 12
  }
}
```

All values come from the allowed managed receipt. An unfenced snapshot omits
`readiness_fence` entirely.

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

The output selector must resolve exactly one terminal point output with a
complete count and complete point multiset. Truncated previews, multiple
eligible terminal point outputs, unknown data, or non-point values yield
`unproven`/`incomplete` as specified by the criterion. They never earn pass.

`terminal_points` means one point-typed output for which no retained flow uses
that exact component-output pair as a source. The snapshot request uses the
artifact's positive bounded `max_preview_items`. Completeness requires the
reported output count to equal the retained preview length and the preview to
contain that many valid points. A count larger than the bound is incomplete;
the evaluator does not issue a second read with a larger bound.

### One-control-at-a-time perturbation

For each declared control, in artifact order:

```text
record exact baseline value
-> gh_set_value(control, one frozen probe value)
-> require one exact managed perturbation receipt
-> gh_wait_for_solve_readiness(perturbation receipt)
-> gh_snapshot(readiness_receipt_id=perturbation receipt)
-> evaluate the complete observed effect
-> gh_set_value(control, exact original value)
-> require one exact managed restoration receipt
-> gh_wait_for_solve_readiness(restoration receipt)
-> gh_snapshot(readiness_receipt_id=restoration receipt)
-> require exact normalized restoration
```

Exactly one perturbation receipt and one restoration receipt are required per
control. The restoration is a new terminal mutation and therefore must use a
new receipt; the perturbation receipt cannot be reused.

No second control may be perturbed until restoration is proven. A failed
dispatch, missing receipt, non-ready wait, refused snapshot, incomplete output,
or restoration mismatch makes the evaluation `incomplete`. The evaluator does
not continue in a partially restored state and does not authorize Actor repair
from compromised probe evidence.

### Restoration equality

Restoration compares a closed normalized semantic projection, not incidental
serialization order or canvas display coordinates. The projection contains:

- bound control IDs, roles, values, minima, and maxima;
- component instance IDs and component-type GUIDs;
- flows;
- selected terminal output identity, complete point count, and complete
  normalized point multiset;
- diagnostics errors and warnings; and
- fence correlation epochs.

Fence receipt IDs and solution run epochs naturally differ after restoration
and are compared for internal validity, not equality to the baseline IDs.

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
      "evidence_refs": ["baseline", "perturbation:StartX"]
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

`probe.status` is `complete` or `incomplete`. `baseline` is null until admitted,
and otherwise has exactly the two shown string fields. Every successfully
bound control appears at most once in artifact order; `complete` requires every
declared control exactly once. `perturbation` and `restoration` are null until
their respective retained evidence exists, and otherwise use the exact shapes
shown. `source` has exactly the three uppercase SHA-256 fields shown. Partial
results accumulate monotonically; an incomplete later phase does not erase
earlier retained evidence.

`probe.error` is null or exactly one of:

```text
artifact_invalid
authoring_trace_invalid
latest_terminal_receipt_missing
later_unfenced_mutation
baseline_wait_failed
baseline_snapshot_failed
control_binding_failed
probe_value_invalid
output_incomplete
perturbation_dispatch_failed
perturbation_receipt_invalid
perturbation_wait_failed
perturbation_snapshot_failed
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
| one small pure Python behavioral-acceptance module | artifact validation, trace admission, probe orchestration through an injected executor, and deterministic predicates |

The existing `scripts/grasshopper_point_row_acceptance.py` may become a thin
compatibility CLI over the common module or be retired after its authentic
fixtures move to common tests. Its task-specific evaluation logic must not
remain as a second authority. No grid-specific or third bespoke evaluator is
added.

The acceptance module receives an injected async tool executor. It does not
construct a model, open an MCP transport, resolve a Rhino target, retry a call,
or own process lifecycle. Canonical and direct paths are exercised by their
existing dispatch owners and must expose equivalent receipts/results.

No fifth model-facing API, evaluator service, persistent registry, database,
or campaign runner is introduced.

## Compatibility

- A well-formed `gh_snapshot` without `readiness_receipt_id` retains its current
  request and response behavior. Malformed nonempty JSON now fails closed.
- `gh_edit` retains its current structural snapshot, `edit_summary`, partial
  errors, T*/C* identity correlation, and short-ID epoch behavior. The managed
  receipt is additive.
- `gh_set_value`, readiness status/wait, and fenced `gh_inspect_output` retain
  their existing receipt schemas.
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
- Pending, stale-solution, superseded, solver-locked, document-replaced,
  unknown, missing, evicted, and process-restarted receipts refuse fenced
  snapshots with no data read.
- A hostile snapshot fake proves `CheckFencedRead()` occurs before the first
  object, topology, diagnostic, value, or output-data access in the same
  callback.
- A successful fenced snapshot retains exact receipt/session/mutation/solution
  correlation.
- An unfenced snapshot retains its existing JSON shape.

### Script propagation tests

- Managed source reads issue no receipt.
- Managed source writes issue before mutation, schedule once, and return the
  exact receipt.
- Direct `gh_set_script` source writes preserve that receipt; source reads
  remain observational.
- Pin preparation alone is nonterminal.
- Failed or partial script pipelines without the final source-write receipt are
  incomplete.
- `gh_create_script`, both aliases, `gh_update_script`, and `chirp_create`
  preserve the exact managed receipt parsed JSON value.
- `script_receipt` and `solve_readiness_receipt` remain distinct siblings.
- Canonical MCP and direct `ToolDispatcher` expose identical receipt values and
  failure behavior.

### Trace and evaluator tests

- The latest covered terminal route receipt is admitted.
- A later successful preparatory or legacy mutation refuses the older receipt.
- A later covered terminal mutation replaces the eligible receipt.
- An unclassified later Grasshopper call fails closed.
- The evaluator refuses the structural snapshot embedded in `gh_edit` even if
  its topology and errors appear successful.
- Each behavioral control requires exactly one perturbation receipt and one
  restoration receipt.
- A perturbation receipt cannot fence the restoration snapshot.
- Every control changes alone; a second simultaneous change refuses.
- Restoration mismatch or any missing/failed call yields `incomplete`.
- Truncated point previews cannot establish complete count, sequence, or
  Cartesian-product predicates.
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
  task-specific evaluator appears.
- Literal script helper routes retain one final `/gh/script` receipt source.
- Native proxy forwarding remains body-transparent.
- Existing T*/C*, flow, edit, discovery, and Python script-receipt contracts do
  not change except for the approved additive receipt/fence fields.

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
+ exact managed receipt propagation
+ managed wait
+ same-callback fence-before-read snapshot
+ one-receipt perturbation and one-receipt restoration
+ deterministic artifact evaluation
```

The first live qualification must use a fresh disposable canvas and a frozen
artifact. It may allow at most one same-session Actor repair under separately
reviewed orchestration. A non-ready receipt, later unreceipted mutation,
incomplete probe, or failed restoration stops as `incomplete`; it does not
authorize cleanup, fallback, or another run.
