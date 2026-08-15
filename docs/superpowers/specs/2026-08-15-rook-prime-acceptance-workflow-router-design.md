# Rook–Prime Acceptance Workflow Router

**Status:** North Star architecture hypothesis — not implementation-ready
**Date:** 2026-08-15
**Baseline:** `4a2adfa39657118924d57468b77ec0aa1c4b8991`
**Qualified Prime runtime:** `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`
**Contained structured-error boundary:** `30a6621bca698ef14f64e5e45c5b1b6364148789`
**Related solve-fenced design:** `2026-08-12-grasshopper-receipt-fenced-behavioral-acceptance-design.md`
**Related validation-kernel design:** `2026-07-13-lm9a-validation-kernel-design.md`

## Objective

Turn the experimentally proven Actor, solve-fenced evidence, deterministic
evaluation, bounded repair, and attributed judgment pattern into one durable
production workflow boundary:

```text
Rook Workflow Router
-> authoritative workflow state, role authority, recovery, and policy

Prime Agent
-> persistent model sessions, reasoning, messages, continuations,
   model selection, token/cost telemetry, and retained model evidence

Rook capability owners
-> target custody, mutation, solve receipts, fenced observation,
   deterministic contract compilation/evaluation, and Policy Gate
```

The router contains no Grasshopper task noun, preferred topology, model prompt,
or domain-specific acceptance branch. Task meaning is supplied as a bounded,
content-addressed declarative contract. The router validates and routes closed
outcomes; it does not become another agent framework.

## Qualification Status

This document describes the intended ownership and routing direction. It does
not establish that the declared boundaries are effective. Production work is
blocked until evidence qualifies each handoff at the boundary that owns it.

The governing qualification invariant is:

> A declared boundary is not an effective boundary until its owner, admission
> rule, and causal handoff are mechanically demonstrated.

Four handoffs are presently unqualified:

1. **Generated contract -> independently admitted meaning.** No retained
   comparison yet proves that a Constructor can cover user intent honestly and
   that a separate Reviewer can detect omissions, invented assumptions,
   unsupported evidence, authority mistakes, vacuous claims, and material
   weakening.
2. **Prime protocol/configuration -> effective role runtime.** RPC/ACP features
   and declared role profiles do not prove that a live top-level session
   receives exactly the intended model, context, tools, and authority.
3. **Persisted dispatch -> exclusive live worker ownership.** An append-only
   intent and CAS design do not prove that only one worker can own and complete
   the correlated external operation across crashes and restarts.
4. **Operation name -> fully defined deterministic semantics.** A closed
   vocabulary label does not prove exact type, precision, evidence,
   completeness, error, and budget behavior for that operation.

The retained V1/V2 evidence qualifies one narrower fact: a Constructor can
consume an exact compiler diagnostic and return a reference-closed replacement
artifact. It does not qualify item 1 because the V2 Reviewer lacked the shared
expression semantic contract and produced a semantic false negative. Phase A
below therefore qualifies the machine-decidable subset of item 4 before any
new Reviewer call. Phase B later returns to item 1 using compiler-valid cases.
Neither phase may be used to infer items 2 or 3. None of the seven production
stages in the companion plan is authorized by this architecture hypothesis.

## Non-Goals

This slice does not:

- replace Prime's session runtime, messaging, goals, steering, continuation,
  model selection, image attachment, or subordinate reasoning;
- replace Rook's existing target, mutation, receipt, or fenced-read owners;
- build a second JSON parser, canonicalizer, budget engine, phase engine, or
  report sealer beside `rook.validation_kernel`;
- infer arbitrary human intent deterministically;
- make model judgment equivalent to deterministic proof;
- put helix, stair, tread, point-row, or XY-grid predicates in production code;
- add a semantic registry whose entries can execute arbitrary code;
- silently weaken a claim, tolerance, authority requirement, or evidence
  precision;
- adopt an unqualified Prime upstream revision;
- add Grasshopper geometry projection in this slice; or
- claim hostile-process security from an MCP profile or prompt alone.

The separately bounded `gh_snapshot` geometry-evidence slice may be delivered
in parallel or later. Its status and evidence envelopes must compose with this
workflow contract, but its implementation is not owned by the router.

## Evidence Behind The Boundary

The retained experiments establish the following production facts:

1. Prime can retain authentic model/tool/session evidence across a native
   session and a same-session continuation.
2. Rook can issue terminal mutation receipts, wait on the managed solution
   lifecycle, and fence a snapshot against the exact solved state.
3. Deterministic control perturbation and exact restoration can test causal
   behavior without prescribing a Grasshopper topology.
4. A local Actor can repair a deterministic failure when returned exact
   criterion evidence.
5. A separate model judgment can catch semantic defects that an Actor misses,
   but free-form judgment is not reliable enough to own completion.
6. An interrupted interactive parent can lose orchestration state even when
   Prime and Rook evidence prefixes survive.
7. Named task predicates do not scale. Task-specific meaning must be data
   compiled into a closed generic expression program.

The Qwen3.8 helix result is recorded separately as a durable milestone. It is
a conformance specimen and motivation, not a production fixture or required
model behavior.

## Governing Invariants

### 1. One authority per fact

```text
workflow transition and recovery decision -> Rook Workflow Router
model/session lifecycle                  -> Prime
target and mutation result               -> Rook capability owner
solve readiness and fenced state         -> managed Grasshopper owner
deterministic claim result               -> compiled evaluator
qualitative judgment                     -> attributed Judgment Agent/user
final workflow status                    -> deterministic Policy Gate
```

No layer may reconstruct another owner's fact from prose, elapsed time, file
presence, a plausible canvas, or model self-report.

### 2. Declared identity reaches its owning runtime boundary

```text
declared workflow/role/model/target/contract identity
-> runtime resolution by its owner
-> observation at that boundary
-> correlated retained evidence
```

Configured state is not treated as effective runtime state. A model tag is not
an immutable model artifact, a file on disk is not proof of a loaded plugin,
and a requested role is not proof that a session received only that role's
Rook authority.

### 3. Evidence accumulates monotonically

Representable observations remain attached to their exact phase, dispatch,
claim, and role. A later projection failure cannot erase an earlier authentic
observation. An artifact write failure may leave only an unsuccessful evidence
prefix; the router must not invent a fallback artifact or claim durable custody
of in-memory observations.

### 4. Mutation is never replayed ambiguously

Before any external dispatch, the router persists a dispatch intent. If a
crash leaves a mutation-capable dispatch without a conclusively correlated
outcome, recovery never repeats it automatically. The workflow becomes
`incomplete` or `awaiting_user_decision`.

### 5. Closed outcomes route; prose advises

Router transitions depend only on validated closed status envelopes. Model
prose, rationales, plans, and confidence may be retained as evidence but never
select a state transition directly.

### 6. Judgment cannot counterfeit proof

A Judgment Agent may resolve claims explicitly permitted to use judgment. It
cannot override:

- a deterministic `fail`;
- broken target, receipt, binding, process, or evidence custody;
- a compiler diagnostic;
- an authority-policy violation; or
- a missing material user decision.

### 7. Contract weakening changes identity

Any change to a claim expression, tolerance, required evidence precision,
claim authority, role binding rule, or policy requirement creates a new
contract fingerprint. Material weakening requires explicit user approval.

## Production Ownership

### Rook Workflow Router

The router owns:

- workflow IDs and the append-only workflow ledger;
- the state-transition table;
- dispatch intent and outcome correlation;
- attempt and budget consumption;
- per-role Rook profile selection;
- Prime session creation/resumption through the Prime adapter;
- crash/restart reconciliation;
- routing compiler diagnostics and claim results;
- invoking the deterministic Policy Gate; and
- emitting the final workflow status envelope.

The router does not implement model loops, geometry calculations, task-specific
claims, or Grasshopper mutations.

### Prime

Prime owns:

- provider/model execution;
- top-level session persistence;
- messages, prompts, steering, follow-ups, and continuation;
- model-native reasoning settings;
- token, cost, retry, and terminal lifecycle telemetry;
- session and process identity;
- retained model/tool events;
- image attachment for judgment; and
- `rlm.run` subordinate reasoning when shared authority is acceptable.

Production integration uses Prime's host control surface. Version 1 uses the
existing RPC interface because it exposes session creation, prompt, steer,
follow-up, abort, state, messages, statistics, fork/clone, and events needed by
the router. ACP remains a future-compatible standardized alternative; the
router contract does not depend on private in-process Prime imports.

### Rook Capability Owners

Existing Rook owners remain authoritative for:

- canonical gateway validation and dispatch;
- document targeting;
- Grasshopper authoring and component identity;
- solve-readiness receipts and mutation epochs;
- receipt waits and fenced snapshots;
- bounded evidence projection;
- controlled behavioral probes; and
- exact restoration evidence.

The deterministic acceptance compiler/evaluator and Policy Gate are Rook
owners because they decide what Rook may claim from Rook evidence.

## Workflow Control Surface

The router is an application service inside the Python Rook MCP process. It is
not a Prime child, prompt convention, disposable runner, or second model
runtime. The MCP server lifecycle starts one router service against the Rook
workflow database and performs the startup reconciliation scan before admitting
new workflow starts.

Version 1 exposes exactly three operator-facing tools:

```text
rook_acceptance_start
rook_acceptance_status
rook_acceptance_decide
```

`rook_acceptance_start` accepts exact target identity, intent text, budget
limits, and either reviewed contract bytes or null. It persists
`workflow_created` before returning. It returns workflow ID, state, nullable
status, and ledger-head hash. It never blocks for a complete model workflow.

`rook_acceptance_status` is read-only and returns the current state/status,
budget counters, pending decision schema when applicable, claim summaries,
evidence references, and ledger-head hash.

`rook_acceptance_decide` accepts workflow ID, expected ledger-head hash,
decision kind, and exact decision payload. It is admitted only in
`awaiting_user_decision`; the expected hash provides optimistic concurrency.
Decision kinds are exactly `approve_contract`, `revise_contract`,
`approve_execution`, `accept_judgment`, and `reject_workflow`. The decision
schema selected by the kind is closed and content-addressed.

All three tools re-enter the same profile, containment, schema, and canonical
gateway walls as other Rook tools. They do not expose raw SQLite records, Prime
RPC methods, arbitrary filesystem paths, or an unrestricted transition API.

## Security And Authority Boundary

Each production role uses a separate top-level Prime session and a separate
Rook MCP subprocess/configuration with a mechanically enforced role profile.
Prompt-only separation and `rlm.run` children are insufficient because Prime
children inherit the parent's tools and authority.

Prime's IPython kernel and workers are process-lifecycle isolation, not an OS
security sandbox. A normal model-facing path is constrained by its registered
tools and Rook profile, but a hostile process with the user's OS authority may
still attempt raw localhost access. This design therefore claims:

> Per-role Rook profiles mechanically enforce authority at canonical Rook
> dispatch boundaries used by the workflow.

It does not claim containment of hostile arbitrary local code. That stronger
claim would require an external OS sandbox or role-bound authentication on all
raw native and managed routes and is outside this slice.

## Closed Workflow State Machine

### States

The stored `state` is exactly one of:

```text
intent_received
contract_designing
contract_compiling
awaiting_user_decision
actor_running
evidence_collecting
evaluating
repairing
judging
policy_deciding
completed
rejected
incomplete
```

`completed`, `rejected`, and `incomplete` are terminal. No transition may leave
a terminal state.

### Admitted transitions

| From | To | Closed reason |
|---|---|---|
| none | `intent_received` | `workflow_created` |
| `intent_received` | `contract_designing` | `design_required` |
| `intent_received` | `contract_compiling` | `reviewed_contract_supplied` |
| `contract_designing` | `contract_compiling` | `contract_proposed` |
| `contract_designing` | `awaiting_user_decision` | `material_design_decision_required` |
| `contract_compiling` | `contract_designing` | `bounded_reformulation_required` |
| `contract_compiling` | `awaiting_user_decision` | `material_contract_change_required` |
| `contract_compiling` | `rejected` | `contract_invalid_and_not_revisable` |
| `contract_compiling` | `actor_running` | `contract_compiled` |
| `awaiting_user_decision` | `contract_designing` | `user_design_direction_received` |
| `awaiting_user_decision` | `contract_compiling` | `user_contract_approval_received` |
| `awaiting_user_decision` | `actor_running` | `user_execution_approval_received` |
| `awaiting_user_decision` | `policy_deciding` | `user_judgment_received` |
| `awaiting_user_decision` | `rejected` | `user_rejected` |
| `actor_running` | `evidence_collecting` | `actor_terminal_mutation_correlated` |
| `evidence_collecting` | `evaluating` | `required_evidence_complete` |
| `evidence_collecting` | `evidence_collecting` | `admissible_read_only_evidence_extension` |
| `evidence_collecting` | `awaiting_user_decision` | `material_evidence_substitution_required` |
| `evaluating` | `repairing` | `deterministic_failure_repairable` |
| `evaluating` | `evidence_collecting` | `admissible_evidence_gap` |
| `evaluating` | `judging` | `judgment_claims_pending` |
| `evaluating` | `policy_deciding` | `claim_evaluation_complete` |
| `repairing` | `actor_running` | `repair_dispatch_started` |
| `judging` | `policy_deciding` | `judgment_complete` |
| `judging` | `awaiting_user_decision` | `user_judgment_required` |
| `policy_deciding` | `completed` | `policy_verified` |
| `policy_deciding` | `completed` | `policy_accepted_with_judgment` |
| `policy_deciding` | `awaiting_user_decision` | `policy_needs_user_decision` |
| `policy_deciding` | `rejected` | `policy_rejected` |

From any nonterminal state, exactly these terminal error transitions are also
admitted:

```text
-> incomplete  reason = custody_failure
-> incomplete  reason = infrastructure_failure
-> incomplete  reason = budget_exhausted_without_resolution
-> incomplete  reason = ambiguous_consumed_mutation
-> rejected    reason = authority_violation
```

No other pair or reason is valid. A self-transition is admitted only for the
explicit `evidence_collecting` extension above; progress messages do not create
state transitions.

### Final workflow statuses

The public `status` is exactly one of:

```text
verified
accepted_with_judgment
needs_user_decision
rejected
incomplete
```

The state/status equation is:

```text
state == completed
  <=> status in {verified, accepted_with_judgment}

state == awaiting_user_decision
  <=> status == needs_user_decision

state == rejected
  <=> status == rejected

state == incomplete
  <=> status == incomplete

all other states
  -> status is null
```

`unsupported` is a compile diagnostic. `unproven` is a claim result. Neither is
a workflow status.

## Append-Only Workflow Ledger

### Storage

Version 1 uses one Rook-owned SQLite database in the configured Rook application
state directory. It uses transactional writes and WAL mode. It is not stored in
a Prime session directory, Grasshopper document, knowledge store, or disposable
experiment root.

Each workflow row is append-only. Updates append a new record using an
optimistic compare-and-swap against the preceding sequence and record hash.
There is no in-place state mutation, delete-on-success, or best-effort rewrite.

### Record kinds

`recordKind` is exactly one of:

```text
state_transition
dispatch_intent
dispatch_outcome
reconciliation
```

### Common record envelope

Every record has exactly these keys:

```json
{
  "schema": "rook.acceptance_workflow_record:v1",
  "workflowId": "01J...",
  "sequence": 17,
  "recordKind": "dispatch_intent",
  "recordedAtUtc": "2026-08-15T12:34:56.789Z",
  "previousRecordSha256": "0123...64 lowercase hex...",
  "stateBefore": "actor_running",
  "stateAfter": "actor_running",
  "contract": {
    "id": "point-row",
    "version": 1,
    "sha256": "0123...64 lowercase hex..."
  },
  "target": {
    "rhinoPid": 1234,
    "port": 5678,
    "documentSerialNumber": 268435457,
    "targetSha256": "0123...64 lowercase hex..."
  },
  "role": "actor",
  "attempts": {"used": 1, "limit": 2},
  "budgets": {
    "elapsedMillisecondsUsed": 0,
    "elapsedMillisecondsLimit": 1800000,
    "modelTurnsUsed": 0,
    "modelTurnsLimit": 2,
    "mutationDispatchesUsed": 0,
    "mutationDispatchesLimit": 1,
    "probeMutationsUsed": 0,
    "probeMutationsLimit": 12
  },
  "prime": {
    "runtimeCommit": "30a6621bca698ef14f64e5e45c5b1b6364148789",
    "processId": null,
    "sessionId": null,
    "childSessionIds": []
  },
  "rook": {
    "receiptId": null,
    "mutationEpoch": null
  },
  "reason": {
    "code": "actor_prompt_dispatch",
    "detailSha256": "0123...64 lowercase hex..."
  },
  "evidence": {
    "input": [],
    "output": []
  },
  "payload": {},
  "recordSha256": "0123...64 lowercase hex..."
}
```

All objects use closed schemas; examples above do not authorize arbitrary keys.
`payload` has a closed shape selected by `recordKind`. Hash values are lowercase
64-character hexadecimal strings. `workflowId` is a Rook-generated ULID.
`recordedAtUtc` is informational and never determines ordering; `sequence` and
the hash chain own ordering.

`recordSha256` is SHA-256 over the strict UTF-8 canonical JSON encoding of the
complete record with `recordSha256` omitted. Canonicalization is owned by the
existing validation kernel. The first record has
`previousRecordSha256 = null`; all later records equal the prior record hash.

### Evidence reference

Each `evidence.input` and `evidence.output` item has exactly:

```json
{
  "kind": "prime_session_jsonl",
  "owner": "prime",
  "uri": "file:///absolute/retained/path",
  "sha256": "0123...64 lowercase hex...",
  "byteLength": 12345
}
```

`owner` is exactly `rook | prime | user | operator`. `kind` is selected from a
versioned evidence-kind manifest sealed into the validation program; v1 admits
exactly `prime_session_jsonl`, `prime_event_stream`, `rook_gateway_source`,
`rook_receipt`, `rook_fenced_snapshot`, `rook_probe_trace`,
`deterministic_evaluation`, `model_judgment`, `user_decision`, and
`process_ledger`. An unknown evidence kind refuses before dispatch. A file URI is retained only for
operator access; equality and custody use hash plus byte length. Credentials,
raw user-object bytes, and model API keys are never ledger evidence.

### Dispatch intent

A `dispatch_intent` payload has exactly:

```json
{
  "operationId": "01J...",
  "effectClass": "reasoning_read",
  "owner": "prime_rpc",
  "method": "session/prompt",
  "requestSha256": "0123...64 lowercase hex...",
  "idempotency": "not_replayable_after_external_entry"
}
```

`effectClass` is exactly:

```text
reasoning_read
rook_read
rook_probe_mutation
rook_actor_mutation
user_decision
```

`idempotency` is exactly:

```text
replayable_if_no_external_entry
replayable_after_reconciliation
not_replayable_after_external_entry
```

For an Actor Prime turn, the router records one coarse `session/prompt` intent.
Prime's retained tool trace and Rook receipts own the model-authored operations
inside that turn. The router does not pretend it knew the tool sequence before
the model authored it.

### Dispatch outcome

A `dispatch_outcome` references exactly one prior `operationId` and records:

```json
{
  "operationId": "01J...",
  "outcome": "completed",
  "externalEntry": true,
  "responseSha256": "0123...64 lowercase hex...",
  "terminalLifecycleObserved": true,
  "correlatedReceiptId": "0123...32 lowercase hex...",
  "correlatedMutationEpoch": 42
}
```

`outcome` is exactly `completed | refused | failed | unknown`. Nullable fields
remain present with null. `externalEntry` is a fact from the owning adapter,
not inferred from an exception message.

## Persist-Before-Dispatch Protocol

For every external operation:

```text
validate current state and role authority
-> reserve budget by appending dispatch_intent transactionally
-> flush/commit ledger
-> invoke exactly once
-> retain owner evidence
-> append correlated dispatch_outcome
-> append admitted state transition when applicable
```

If intent persistence fails, external dispatch is forbidden. If outcome
persistence fails after external entry, the operation remains consumed and
recovery reconciles it; it is never repeated merely because the outcome row is
missing.

## Roles And Enforced Authority

`role` is exactly:

```text
acceptance_designer
actor
evidence_planner
evaluator
judgment_agent
policy_gate
```

| Role | Prime session | Rook authority | Mutation authority |
|---|---|---|---|
| Acceptance Designer | separate top-level | no Rook tools under `workflow_acceptance_designer`; only `rook_tools_search` and `rook_tools_read` under separately declared `workflow_acceptance_designer_schema` | none |
| Actor | separate top-level | scoped canonical authoring plus observational tools | actor-authoring scope only |
| Evidence Planner | separate top-level when reasoning is needed | schemas and retained evidence metadata only | none |
| Evaluator | no model required | receipt-fenced reads and frozen controlled probes | operator-owned value perturb/restore only |
| Judgment Agent | separate top-level | read-only retained evidence and approved images | none |
| Policy Gate | no Prime session | validated compiler/evaluator/judgment/user records only | none |

The router creates each model role as a separate top-level Prime session with a
distinct Rook profile. The exact production profile IDs are:

```text
workflow_acceptance_designer
workflow_acceptance_designer_schema
workflow_actor
workflow_evidence_planner
workflow_evaluator
workflow_judgment
```

Every profile is a sealed manifest containing exact admitted tool names,
argument-scope rules, manifest version, and SHA-256. `workflow_actor` is scoped
to the frozen target and the approved model-facing authoring allowlist.
`workflow_evaluator` is scoped to the frozen target, admitted receipt, bound
component/output identities, and the declared probe controls. The other four
profiles deny mutation. The Policy Gate has no MCP profile because it has no
model or Rook tool session.

The router may use `rlm.run` only for subordinate reasoning that
inherits the same authority as its parent. It never uses an Actor child under a
Designer or Judgment parent, or a Judgment child under an Actor.

The existing `lean` profile is advertisement-only and therefore cannot enforce
a role. Existing `readonly` is default-deny and may be reused where its admitted
tools exactly match. New role profiles are closed allowlists enforced at
canonical and direct ToolDispatcher boundaries. Unknown tools and future tools
are denied until classified.

Canonical and direct dispatch produce the same admission or refusal for the
same caller-owned request. Profile refusal occurs before target resolution,
document enrichment, model contact, managed/native dispatch, or mutation.

## Prime RPC Adapter

The production adapter is a small external client of Prime RPC. It owns:

- starting or attaching to the exact approved Prime runtime;
- capturing Prime process identity and creation time;
- creating one session with exact model/provider/reasoning/settings;
- sending `prompt`, `steer`, `follow_up`, or `abort` as routed;
- observing complete ordered Prime events;
- querying state, messages, and session statistics;
- retaining the session artifact and hashes; and
- proving terminal lifecycle and process exit/ownership.

It does not interpret Rook results, compile acceptance claims, decide repairs,
or synthesize workflow transitions.

Each RPC request has a stable router `operationId`. A Prime session record maps
that operation to exact Prime session and message IDs. The adapter validates
exactly one terminal semantic lifecycle per requested turn. Closed,
non-actionable Prime housekeeping after the semantic terminal event is retained
and hashed but cannot authorize another transition.

Prime automatic provider retries may remain only where Prime proves that no
tool execution or external mutation occurred. Actor and probe phases disable or
audit any turn-level replay that could repeat tool execution. The router never
reissues an Actor prompt after uncertain external entry.

The qualified Prime runtime remains pinned to merge
`27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`, which contains the reviewed
structured-error boundary commit
`30a6621bca698ef14f64e5e45c5b1b6364148789`, until a separate compatibility
review qualifies a later upstream version. The router records the effective
runtime commit and file hashes; it does not silently follow a branch or tag.

## Acceptance Contract

### Existing validation kernel is reused

The compiler is a sealed semantic contribution to `rook.validation_kernel`.
It reuses the kernel's:

- bounded raw-byte ingress;
- strict JSON parsing and duplicate-key rejection;
- owned transitively immutable JSON values;
- canonical JSON and fingerprints;
- budget accounting;
- typed phase engine;
- sealed program manifest; and
- deterministic report sealing.

No open registry or executable plugin is consulted during an invocation. A
failed seal produces no executable acceptance program.

### Contract envelope

The task contract has exactly:

```json
{
  "schema": "rook.acceptance_contract:v1",
  "contractId": "example.point_row",
  "contractVersion": 1,
  "intentSummary": "Adjustable point row along X with Y and Z fixed.",
  "vocabulary": {
    "id": "rook.acceptance_expression:v1",
    "sha256": "0123...64 lowercase hex..."
  },
  "roles": [],
  "dependencies": [],
  "probes": [],
  "claims": [],
  "policy": {
    "requiredClaimIds": [],
    "repairLimit": 1,
    "designerReformulationLimit": 1,
    "evidenceExtensionLimit": 1,
    "judgmentLimit": 1
  }
}
```

All object keys are exact and `additionalProperties` is false. Arrays preserve
order and reject duplicate IDs. `intentSummary` is retained explanatory text;
it is never executed. Limits are strict nonnegative integers, with booleans
rejected, and are capped by trusted server policy.

### Roles

A symbolic role has exactly:

```json
{
  "id": "points",
  "kind": "grasshopper_output",
  "valueType": "collection<point3>",
  "required": true
}
```

`kind` is exactly `grasshopper_output | grasshopper_number_control |
geometry_collection | external_evidence` in v1.
Role IDs are task-local labels. They do not authorize code branches.

`kind` identifies the binding mechanism. `valueType` identifies the semantic
meaning made available to the expression compiler. Neither substitutes for
the other. The shared semantic manifest owns their compatibility; the
contract schema admits only a lexical type reference, and the compiler
refuses an incompatible pair.

The typed contract schema defines `roleId` once as
`^[a-z][A-Za-z0-9]*$` with a maximum of 64 characters. Role declarations,
requirement references, claim references, evidence references, expression
references, and bindings all reuse that exact schema definition. No reference
site admits a broader string grammar than the declaration site.

The bounded Phase A qualification admits exactly:

| `kind` | admitted `valueType` | expression-visible field |
|---|---|---|
| `grasshopper_number_control` | `integer` | `value: integer` |
| `grasshopper_number_control` | `finite_scalar` | `value: finite_scalar` |
| `grasshopper_output` | `collection<point3>` | `value: collection<point3>` |

`geometry_collection` and `external_evidence` remain valid production role
kinds but are unavailable in Phase A. Using an unavailable kind produces
`unsupported`; using an admitted kind with a non-admitted `valueType`, an
unknown field, or an incompatible binding produces `invalid`. Phase A must
not infer a type from the role description, evidence request, claim text, or
task-specific role ID.

A `role` expression returns an internal
`role_ref<kind,valueType>`. It never silently unwraps a control or output.
The exact field `value` projects the declared semantic value. Thus the point
count expression is:

<!-- phase-a-valid-json id=point-count-expression kind=expression -->
```json
{
  "op": "equal",
  "args": [
    {
      "op": "collection_count",
      "args": [
        {
          "op": "field",
          "source": {"op":"role","role":"points"},
          "name": "value"
        }
      ]
    },
    {
      "op": "field",
      "source": {"op":"role","role":"countControl"},
      "name": "value"
    }
  ]
}
```
<!-- /phase-a-valid-json -->

Comparing `collection_count(points)` directly with a control role reference is
a compile-time type error. This projection rule is shared by the Constructor,
Reviewer, and deterministic validator; none may redefine it in prose.

### Actor binding

The Actor supplies a separate witness binding after implementation:

```json
{
  "schema": "rook.acceptance_binding:v1",
  "contractSha256": "0123...64 lowercase hex...",
  "actorReceiptId": "0123...32 lowercase hex...",
  "actorMutationEpoch": 42,
  "bindings": [
    {
      "role": "points",
      "kind": "grasshopper_output",
      "componentId": "C7",
      "outputIndex": 0
    },
    {
      "role": "countControl",
      "kind": "grasshopper_number_control",
      "componentId": "C3"
    }
  ]
}
```

Binding is admitted only when its Actor receipt equals the latest committed
terminal Actor mutation at binding admission. The binding is then frozen.
Operator-owned control perturbations issue newer probe receipts without
invalidating it; the evaluator revalidates the exact component/output IDs on
every phase. Any unowned or structural mutation invalidates the binding.

The Acceptance Designer defines symbolic roles but cannot invent `C*` IDs.
The Actor binds roles but cannot change claim expressions or policy.

## Closed Expression Language

### Types

The compiler supports exactly these type families in v1:

```text
boolean3
integer
finite_scalar
length
area
angle
point3
vector3
enum
string
identifier
collection<T>
evidence<T>
```

`boolean3` is `true | false | unproven`. `evidence<T>` is
`present | missing | unsupported | error` plus a value only when present.
Numeric values are finite. Physical dimensions are part of the static type;
for example, `length` cannot be compared with `angle`.

Exact equality is allowed only for integers, enums, strings, identifiers, and
exact restoration values. Floating or dimensional comparisons require an
explicit tolerance source in the expression or trusted contract policy.

### Expression node forms

Every expression is one of these closed forms:

```json
{"op":"literal","valueType":"integer","value":3}
```

```json
{"op":"role","role":"treads"}
```

```json
{"op":"current_item","name":"item"}
```

```json
{"op":"field","source":{"op":"current_item","name":"item"},"name":"area"}
```

```json
{"op":"phase","phase":"baseline","source":{"op":"role","role":"points"}}
```

```json
{
  "op":"external_evidence",
  "dependency":"approved_reference",
  "pointer":"/facts/value"
}
```

```json
{"op":"equal","args":[EXPRESSION,EXPRESSION]}
```

```json
{
  "op":"approx_equal",
  "args":[EXPRESSION,EXPRESSION],
  "absoluteTolerance":EXPRESSION,
  "relativeTolerance":EXPRESSION
}
```

```json
{
  "op":"for_all",
  "source":EXPRESSION,
  "variable":"item",
  "expression":EXPRESSION
}
```

Object keys are exact for the selected form. `EXPRESSION` means another owned,
bounded node. Quantifier variable names are lexical identifiers with bounded
nesting and may reference only their enclosing fixed binder. There are no user
functions, recursion, dynamic property names, arbitrary JSON pointers into
runtime objects, embedded code, or runtime-loaded operations.

### Primitive operations

The v1 operation vocabulary is exactly:

| Family | Operations |
|---|---|
| references | `literal`, `role`, `current_item`, `field`, `phase`, `external_evidence` |
| logic | `and`, `or`, `not` |
| arithmetic | `add`, `subtract`, `multiply`, `divide`, `abs` |
| comparison | `equal`, `approx_equal`, `greater_than`, `greater_or_equal`, `less_than`, `less_or_equal`, `one_of` |
| collections | `collection_count`, `for_all`, `any`, `map`, `sum`, `mean`, `min`, `max` |
| geometry math | `coordinate`, `dot`, `cross`, `norm`, `atan2` |
| evidence | `evidence_state`, `is_complete`, `precision` |

Each operation has a sealed arity, input-type rule, output type, evaluation
budget cost, and error rule in the trusted vocabulary manifest. Unknown
operations refuse compilation before Prime, Rook host, Rhino, or Grasshopper
contact.

### Shared semantic manifest

There is exactly one versioned, canonical-JSON semantic manifest for a sealed
language version. Constructor input, Reviewer input, schema validation, type
checking, compilation, and evaluation all cite the same manifest ID, byte
length, and SHA-256. A prose summary is explanatory only and cannot add or
change semantics.

The manifest contains these exact top-level sections:

```text
schema
id
version
types
roleKinds
fields
operations
quantifiers
authorityCompatibility
precisionRules
errorRules
budgetRules
```

Every `roleKinds` entry contains:

```text
id
availability
allowedValueTypes
bindingType
availableFields
unavailableOutcome
incompatibleOutcome
```

Every field entry contains:

```text
sourceTypePattern
name
resultTypeExpression
availability
missingBehavior
errorBehavior
budgetCost
```

Every operation entry contains:

```text
op
availability
arity
inputTypePatterns
outputTypeExpression
precision
missingBehavior
unsupportedBehavior
errorBehavior
budgetCost
```

An operation ID present with `availability=unavailable` compiles to
`unsupported`. An operation ID absent from the manifest is
`invalid/operation_unknown`; malformed syntax is `invalid/schema`. The same
distinction applies to known-unavailable versus unknown role kinds. This keeps
an honest capability gap separate from an open or fabricated contract.

Phase A `valueType` is not free-form text. It is exactly `integer`,
`finite_scalar`, `point3`, or the one-level constructor
`collection<point3>`. `role_ref<kind,valueType>` is an internal compiler type
and can never appear in contract JSON. Nested collections, unions, aliases,
implicit numeric widening, and task-defined types are unavailable in Phase A.

The Phase A operation subset is exact:

| Operation | Input | Output | Required semantics |
|---|---|---|---|
| `literal` | declared `integer` or `finite_scalar` literal | declared type | integers remain exact; scalars must be finite |
| `role` | admitted role ID | `role_ref<kind,valueType>` | no implicit value projection |
| `field` | admitted role reference plus `value`, or `point3` plus `x`, `y`, or `z` | manifest-declared field type | missing/inapplicable field is compile-time `invalid` |
| `current_item` | one in-scope quantifier binder | binder element type | unbound, shadowed, or out-of-scope name is `invalid` |
| `collection_count` | `collection<T>` | `integer` | exact retained complete count only; incomplete runtime evidence is `unproven` |
| `coordinate` | `point3` plus `x`, `y`, or `z` | `finite_scalar` | no collection broadcasting |
| `equal` | identical exact-comparable types | `boolean3` | allowed only for `integer`, `enum`, `string`, and `identifier` in Phase A |
| `approx_equal` | identical numeric types plus explicit finite nonnegative absolute and relative tolerances | `boolean3` | no default or inferred tolerance |
| `and` | 2 through 8 `boolean3` values | `boolean3` | strong Kleene logic |
| `for_all` | `collection<T>`, one lexical binder, and a `boolean3` body | `boolean3` | evaluates once per admitted item; empty is `true`; incomplete collection is `unproven` |

The manifest also freezes:

- maximum raw contract bytes: 131,072;
- maximum expression nodes: 128;
- maximum expression depth: 16;
- maximum quantifier depth: 4;
- maximum operation cost and collection visits as trusted policy values in the
  manifest, never caller-raised values;
- exact integers without float conversion;
- finite scalar admission only;
- missing, unsupported, runtime-error, truncation, and insufficient-precision
  propagation to `unproven`; and
- schema, reference, type, authority, binder, nonfinite, and budget violations
  as compiler `invalid`.

Phase A exercises compilation only; it does not invent runtime values for
these operations. A later evaluator must consume the same manifest rather
than duplicate the signatures in code.

### Derived macros

Reviewed macros are canonical source-to-source lowering only. They add no
runtime dispatch branch. Initial macros include:

```text
extent
delta_between_phases
invariant_across_phases
sequence_compare
monotonic
distance_to_axis
angle_about_axis
unwrap_angles
```

For example, `distance_to_axis(point, origin, direction)` lowers to vector
subtraction, dot, multiplication, subtraction, and norm. If a requested idea
cannot lower to the sealed vocabulary, compilation returns `unsupported`; the
runtime never invents an evaluator function.

A new primitive operation is admitted only when all are true:

1. it has no domain noun or task-specific role;
2. it is deterministic over existing admitted evidence;
3. it cannot be lowered without losing the required evidence semantics;
4. at least two credible non-isomorphic workflows need it;
5. its type, precision, error, and budget behavior are closed; and
6. mutation and hostile-input tests prove its boundary.

### Budget limits

Trusted policy caps:

- raw contract bytes;
- AST node count;
- AST depth;
- quantifier depth;
- total collection items visited;
- external evidence bytes;
- probe phases and probe mutations;
- compiled program bytes; and
- total deterministic evaluation work units.

The task contract may request lower limits but cannot raise trusted caps.

### Three-valued logic

The evaluator uses strong Kleene logic:

```text
true  AND unproven = unproven
false AND unproven = false
true  OR  unproven = true
false OR  unproven = unproven
NOT unproven       = unproven
```

For `for_all`:

- any `false` produces `false`;
- otherwise any `unproven` produces `unproven`;
- an empty collection produces `true`.

For `any`:

- any `true` produces `true`;
- otherwise any `unproven` produces `unproven`;
- an empty collection produces `false`.

Collection presence and non-emptiness therefore require their own claim when
material. Missing, unsupported, error, truncation, insufficient precision,
nonfinite data, division by zero, or exhausted work budget produces
`unproven`, never guessed success. Broken custody or infrastructure makes the
workflow `incomplete`, not an ordinary criterion result.

### Claims

A claim has exactly:

<!-- phase-a-valid-json id=point-count-claim kind=claim -->
```json
{
  "id": "point_count_equals_count",
  "authority": "deterministic_required",
  "expression": {
    "op": "equal",
    "args": [
      {
        "op": "collection_count",
        "args": [
          {
            "op": "field",
            "source": {"op":"role","role":"points"},
            "name": "value"
          }
        ]
      },
      {"op":"field","source":{"op":"role","role":"countControl"},"name":"value"}
    ]
  }
}
```
<!-- /phase-a-valid-json -->

`authority` is exactly:

```text
deterministic_required
judgment_allowed
judgment_required
user_required
```

The manifest owns this exact authority/expression compatibility matrix:

| Authority | Expression | Deterministic result | Additional authority |
|---|---|---|---|
| `deterministic_required` | required, compiled type `boolean3` | `false` fails; `unproven` routes for admissible evidence or remains unresolved; `true` satisfies | none |
| `judgment_allowed` | required, compiled type `boolean3` | `false` cannot be overridden; `true` satisfies; only `unproven` may route to attributed judgment | judgment is optional and bounded |
| `judgment_required` | optional; when present it must compile to `boolean3` | an expressed `false` cannot be overridden; `true` does not remove the judgment requirement | attributed judgment is always required |
| `user_required` | optional; when present it must compile to `boolean3` | an expressed `false` cannot be overridden; `true` does not remove the user decision | explicit correlated user decision is always required |

A null expression under `deterministic_required` or `judgment_allowed` is
compiler `invalid`. A model cannot use `user_required` to claim that an
implemented property exists; it denotes a material user decision or approval.
Changing authority or expression changes the contract hash. Reviewer judgment
cannot repair an incompatible authority/expression pair because that pair is
rejected before review.

Claim IDs are reporting and correlation labels only. Changing an ID without
changing the expression does not change execution. Changing the expression
changes the contract fingerprint. Production code contains no switch on claim
IDs.

### Dependencies

External evidence must be declared in `dependencies` with an exact schema ID,
hash, byte length, owner, and allowed JSON-pointer prefix. Filesystem paths,
URLs, or mutable process objects cannot be introduced by an expression. A
missing or mismatched dependency refuses program sealing.

## Compiler Outcomes And Routing

The compiler produces exactly:

```text
compiled
unsupported
invalid
```

`unsupported` means the closed contract is meaningful but requires an
unavailable operation or evidence kind. `invalid` means schema, type,
authority, budget, dependency, or internal-consistency failure.

Routing is:

| Condition | Route |
|---|---|
| unsupported expression | Acceptance Designer may propose one bounded reformulation |
| unsupported evidence kind | Evidence Planner may propose one bounded evidence source |
| material proxy or weaker tolerance | new contract hash and user approval |
| compiler invalid | reject or request corrected reviewed contract; no Actor contact |
| unproven from truncation/sampling | one additional read-only evidence extension when admissible |
| qualitative claim pending | attributed Judgment Agent or user |
| deterministic fail | Actor repair while budget remains |
| custody/infrastructure failure | `incomplete`; stop |

The Designer or Evidence Planner returns a proposed complete replacement
contract, not an imperative patch to a running program. The compiler validates
it from raw bytes again. A model cannot add an operation to the vocabulary.

## Probe Contract

Probes are declarative one-control-at-a-time phase programs. Each phase binds:

- one admitted control role;
- one exact original value;
- one reviewed perturbation value or derivation;
- expected receipt ownership;
- selected evidence roles;
- restoration to the exact original value; and
- post-restoration equality requirements.

For every perturbation and restoration:

```text
dispatch one controlled mutation
-> retain its exact receipt
-> wait for readiness
-> obtain receipt-fenced evidence
-> correlate binding and target
```

Any dispatch, wait, fence, evidence, or restoration failure makes the workflow
`incomplete`. A restoration may not be skipped because a criterion already
failed. Probes never consume `gh_edit`'s embedded pre-solve snapshot as
acceptance evidence.

## Claim Result Envelope

Each deterministic claim yields exactly:

```json
{
  "claimId": "point_count_equals_count",
  "result": "pass",
  "authority": "deterministic",
  "programSha256": "0123...64 lowercase hex...",
  "contractSha256": "0123...64 lowercase hex...",
  "bindingSha256": "0123...64 lowercase hex...",
  "evidenceSha256": ["0123...64 lowercase hex..."],
  "reasonCode": "equal",
  "detail": {}
}
```

`result` is exactly `pass | fail | unproven`. The `detail` schema is selected
by `reasonCode` and contains bounded values only. It never contains exception
text, arbitrary model prose, or mutable host objects.

## Judgment

Judgment is used only for claims whose authority permits it. The router starts
a separate read-only Prime session with exact approved evidence and images.
The Judgment Agent returns one closed record per claim:

```json
{
  "claimId": "visual_coherence",
  "result": "accept | reject | uncertain",
  "authority": "model_judgment",
  "model": "provider/model@immutable-identity",
  "sessionId": "...",
  "evidenceSha256": ["..."],
  "confidence": "low | medium | high",
  "rationaleSha256": "..."
}
```

The full rationale is retained as Prime evidence; only its hash enters the
closed record. Multimodal evidence is attached through Prime's existing image
mechanism. Missing image custody, malformed response, or uncertain judgment
cannot become acceptance.

## Deterministic Policy Gate

The Policy Gate has no model and no geometry mutation authority. It consumes
only validated contract, compiler, claim, judgment, user-decision, custody,
and budget records.

Precedence is:

1. Broken target, receipt, binding, process, artifact, or transition custody
   -> `incomplete`.
2. Authority violation -> `rejected`.
3. Any `deterministic_required` claim `fail` -> `rejected` when repair budget
   is exhausted, otherwise route to repair.
4. Any required claim `unproven` -> route to admissible evidence/judgment/user
   while budget and authority allow; otherwise `needs_user_decision` or
   `incomplete` according to policy.
5. Any `user_required` claim without a user decision ->
   `needs_user_decision`.
6. Any required judgment `reject` -> `rejected`.
7. All required claims deterministically pass and no judgment is required ->
   `verified`.
8. All deterministic requirements pass and all permitted required judgments
   accept -> `accepted_with_judgment`.

Judgment cannot override step 1, 2, or 3. No aggregate score hides an
individual result.

The final public envelope has exactly:

```json
{
  "schema": "rook.acceptance_workflow_result:v1",
  "workflowId": "01J...",
  "state": "completed",
  "status": "verified",
  "contractSha256": "...",
  "bindingSha256": "...",
  "claims": [],
  "judgments": [],
  "budgets": {},
  "latestReceiptId": "...",
  "latestMutationEpoch": 42,
  "evidence": [],
  "ledgerHeadSha256": "..."
}
```

The exact nested schemas are owned by their sections above; open keys are not
permitted.

## Crash And Restart Reconciliation

### Startup scan

On startup, the router scans nonterminal workflow heads. It validates the full
hash chain and current schemas before reading external state. A malformed or
broken chain is `incomplete` and no external operation is issued.

### Reconciliation inputs

For the last unmatched dispatch intent, the router obtains only owner facts:

- Prime process identity, session state, messages, events, and session-file
  hash from Prime RPC/session storage;
- current target identity and document serial from Rook;
- latest terminal receipt and mutation epoch from Rook's receipt owner; and
- retained source-trace and artifact hashes.

### Recovery matrix

| Last intent | Correlated evidence | Recovery |
|---|---|---|
| reasoning/read, no external entry | none | dispatch may be repeated with same operation ID |
| reasoning/read, conclusive completed response | yes | append recovered outcome and continue |
| reasoning/read, external entry but ambiguous terminal | partial | `incomplete` or user direction; no blind replay |
| Actor mutation-capable turn, conclusive Prime terminal and Rook receipt | yes | append recovered outcome and continue from evidence collection |
| Actor mutation-capable turn, any ambiguous consumption | partial/none | `incomplete`; never replay |
| controlled probe mutation, exact receipt and phase evidence | yes | continue from next not-yet-intended phase |
| controlled probe mutation, ambiguous commit/restoration | partial/none | `incomplete`; never replay or auto-restore |
| target or document replaced | any | `incomplete` |

Reconciliation itself is appended as a `reconciliation` record referencing the
unmatched operation ID and every consulted evidence hash. It cannot edit old
records.

### Duplicate prevention

- One workflow may have at most one open Actor operation.
- One probe phase may have at most one open mutation operation.
- Operation IDs are unique database keys.
- A Prime session/message ID may correlate to only one operation.
- A solve receipt may correlate to only one terminal mutation operation in a
  workflow.
- Compare-and-swap on ledger head prevents two router processes from advancing
  the same workflow concurrently.

## Geometry Evidence Compatibility

The future optional `gh_snapshot.geometry_evidence` projection remains a Rook
evidence vocabulary, not an Acceptance Designer generator. It must:

- admit the receipt fence before output enumeration or geometry calculation;
- select exact `(component_id, output_index)` pairs in request order;
- preserve tree path and item index;
- expose closed projected, null, unsupported, and error outcomes;
- report truthful examined/retained/truncated accounting;
- distinguish exact from sampled facts;
- use server caps for total items, sample points, compact UTF-8 bytes, and work;
  and
- contain no stair, tread, helix, aesthetic, or fabrication judgment.

The compiler consumes those facts through typed roles and fields. The task
contract may call a role `treads`; the geometry projector and evaluator do not.

## Generality And Migration Proof

Before the production evaluator replaces the experimental named predicates,
conformance must prove:

1. Point-row acceptance is expressed as one contract artifact and retains its
   authentic classification.
2. The reviewed Cartesian XY-grid specimen is expressed as another artifact
   and retains its authentic classification.
3. The symbolic stair contract compiles or reports exact unsupported claims
   without adding any stair-named production function.
4. All specimens use identical evaluator program bytes and vocabulary
   fingerprint.
5. Renaming a criterion ID changes reporting only.
6. Changing its expression changes the contract fingerprint and may change the
   result.
7. An unknown operation refuses before host contact.
8. Unsupported or unfamiliar semantics become `unproven` or a compile
   diagnostic; they never invite an ad hoc predicate.
9. No production dispatch switches on a criterion ID, intent string, role
   label such as `treads`, or model name.

After parity, the named predicate switch in
`mcp_server/src/rook/gh_behavioral_acceptance.py` is removed. Two evaluators do
not remain authoritative. That large module may be split only where source
custody, probe execution, and deterministic evaluation already have distinct
ownership; file movement alone is not a design objective.

## Expected Production Owners

The intended Rook files are:

```text
mcp_server/src/rook/acceptance_workflow_contract.py
mcp_server/src/rook/acceptance_workflow_store.py
mcp_server/src/rook/acceptance_workflow_router.py
mcp_server/src/rook/acceptance_expression.py
mcp_server/src/rook/acceptance_policy.py
mcp_server/src/rook/prime_rpc_adapter.py
mcp_server/src/rook/mcp_tool_profiles.py
mcp_server/src/rook/server.py
```

Existing validation-kernel files are extended only through their sealed
contribution interface. Existing receipt, snapshot, and behavioral probe owners
are reused. A new module is justified only by one of the explicit ownership
boundaries above; no `agents/`, semantic registry, campaign framework, or
task-specific evaluator package is introduced.

Prime changes, if any, remain in Prime and are limited to a generic RPC/session
contract gap proven against the pinned runtime. Rook-specific routing policy is
not added to Prime.

## Required Test Matrix

### Schema and transitions

- every admitted state/reason pair;
- every non-admitted transition;
- terminal-state immutability;
- exact state/status equations;
- closed keys, exact types, duplicate IDs, booleans-as-integers refusal;
- canonical record hashes and broken-chain refusal.

### Authority

- each role's complete allowed and denied tool set;
- unknown future tool denied;
- canonical/direct parity;
- refusal before routing, target resolution, enrichment, or dispatch;
- Actor cannot access Policy or Judgment authority;
- Judgment and Designer cannot mutate;
- Evaluator can mutate only declared probe controls and must restore.

### Compiler and evaluator

- every node form, operation, type rule, precision rule, and budget;
- strong Kleene truth tables and empty quantifiers;
- exact versus approximate numeric behavior, including integers beyond
  IEEE-754 exact range;
- unknown operation and unknown evidence field refusal before host access;
- dependency hash/schema/size enforcement;
- macro lowering equivalence;
- task fixtures with zero task-name branches;
- unsupported claims remain compile diagnostics or `unproven` as specified.

### Prime adapter

- fake RPC providers for complete, refused, failed, interrupted, duplicated,
  malformed, and housekeeping-suffix sessions;
- exact model/settings/session identity;
- separate top-level role sessions and profiles;
- no mutation replay after ambiguous terminal evidence;
- exact event and session-file retention;
- no silent Prime runtime upgrade.

### Recovery

- crash before intent commit;
- crash after intent but before external entry;
- crash after reasoning/read completion;
- crash during Actor tool execution;
- crash after mutation but before outcome persistence;
- crash during perturbation and restoration;
- duplicate router process CAS race;
- replaced document and target drift;
- corrupt Prime/Rook/ledger evidence;
- all idempotent resumes and all forbidden replays.

### Policy and judgment

- every precedence branch;
- deterministic fail cannot be overridden;
- judgment record attribution and image custody;
- uncertain/malformed judgment;
- material weakening requires a new contract hash and approval;
- no score collapses individual claims.

## Pre-Implementation Semantic Boundary Qualification

No production router, Prime adapter, role profile, or live workflow may be
implemented from this specification until the shared semantic boundary passes
two separately reviewed phases.

### Phase A: compiler qualification without a model

Phase A creates exactly one canonical semantic manifest, one typed contract
schema, one deterministic validator/compiler seam, one coherent point-row
artifact, and one isolated mutation corpus. The Constructor prompt template,
Reviewer prompt template, validator, and corpus all consume the same manifest
bytes and retain its hash. No Ollama, hosted model, Prime, Rook, Rhino, or
Grasshopper contact is permitted.

All Phase A implementation is disposable offline qualification code. It does
not add `acceptance_expression.py`, alter `validation_kernel`, expose a tool,
or start any production-router task. Passing Phase A authorizes only a later
Phase B design review.

The coherent point-row artifact uses these roles:

| Role | Kind | Value type |
|---|---|---|
| `startControl` | `grasshopper_number_control` | `finite_scalar` |
| `stepControl` | `grasshopper_number_control` | `finite_scalar` |
| `countControl` | `grasshopper_number_control` | `integer` |
| `points` | `grasshopper_output` | `collection<point3>` |

It demonstrates only compiler coherence:

- point count equals the projected integer value of `countControl`;
- every point Y is approximately zero through explicit `for_all`;
- every point Z is approximately zero through explicit `for_all`; and
- the indexed Start/Step relationship remains explicitly unresolved because
  the Phase A subset has no indexed-access operation.

Compiler coherence is not intent adequacy. An omitted or weakened requirement
may still compile and is reserved for Phase B review.

Each mutation changes exactly one mechanically decidable property and must
fail for its own stable compiler diagnostic:

| Mutation | Required compiler result |
|---|---|
| undeclared role reference | `invalid/reference_unknown` |
| incompatible role kind and `valueType` | `invalid/role_type_incompatible` |
| direct scalar comparison with an unprojected control role | `invalid/type_mismatch` |
| `coordinate` applied to `collection<point3>` without `for_all` | `invalid/type_mismatch` |
| unbound, shadowed, or out-of-scope quantifier variable | `invalid/binder_invalid` |
| null expression under `deterministic_required` | `invalid/authority_expression_incompatible` |
| null expression under `judgment_allowed` | `invalid/authority_expression_incompatible` |
| floating comparison without explicit admitted tolerances | `invalid/tolerance_required` |
| nonfinite literal or tolerance | `invalid/nonfinite` |
| AST node, depth, quantifier, or work-cost limit exceeded | `invalid/budget_exceeded` |

Each hostile fixture differs from the coherent fixture by exactly the named
mechanical mutation. Tests execute the real parser/type checker, require the
exact diagnostic, and prove that a mechanically invalid artifact produces no
Reviewer request. This is compiler behavior evidence, not source-text
presence checking.

Phase A is complete only when:

- every participant input cites the identical semantic-manifest hash;
- every specification JSON example enclosed by
  `<!-- phase-a-valid-json id=... kind=expression|claim -->` and
  `<!-- /phase-a-valid-json -->` has a unique ID, strict-parses, and compiles
  under the coherent point-row role environment; an unclosed marker, duplicate
  ID, parse failure, or compile failure refuses Phase A;
- the coherent artifact compiles;
- every isolated mechanical mutation refuses causally;
- unknown operations and unavailable role kinds return `unsupported` only
  where the manifest explicitly says so;
- the validator contains no point-row claim-ID or role-ID branch; and
- an independent no-contact review reproduces the corpus.

### Phase B: residual Reviewer qualification

Phase B is designed and authorized only after Phase A passes independently.
It uses compiler-valid artifacts exclusively. Mechanical defects never reach
the Reviewer.

The Reviewer receives:

- the exact original intent;
- the exact compiler-accepted artifact and hash;
- the exact shared semantic manifest and hash;
- the admitted evidence vocabulary;
- the residual-review authority contract; and
- its closed response schema.

It does not receive Constructor reasoning or mutation labels. Each case uses a
fresh no-shared-context Reviewer session.

The later controlled corpus contains one semantically coherent artifact and
isolated compiler-valid mutations for:

- omission of a material requirement;
- an invented material assumption;
- material weakening of a requirement or tolerance;
- misrouting a material choice away from required user authority; and
- suppressing or mischaracterizing a material unresolved semantic risk.

Reviewer ownership is limited to requirement coverage, assumption honesty,
material weakening, authority meaning that depends on user intent, and
unresolved semantic risk. It cannot approve a compiler-invalid artifact,
change an expression, add an operation, or reinterpret a deterministic result.

No grid, helix, live Grasshopper workflow, or production-router implementation
is admitted by either phase. Phase A qualifies the compiler boundary. Phase B
later qualifies residual semantic sensitivity.

## Delivery Sequence

Production implementation is staged:

1. closed status, authority, transition, ledger, and recovery schemas with
   inert tests;
2. deterministic compiler/evaluator contribution and Policy Gate;
3. Prime RPC role-session adapter with fake providers;
4. per-role Rook authority enforcement;
5. crash/restart reconciliation and idempotency;
6. multimodal Judgment Agent integration; and
7. separately authorized live qualification.

The geometry-evidence projection is its own bounded implementation slice. The
router may land before it, but stair claims that require geometry evidence
remain `unsupported` until that evidence owner is qualified.

## Success Criteria

This production boundary is complete only when:

- workflow state survives operator or Codex interruption;
- no ambiguous mutation or probe is automatically repeated;
- every model role has a mechanically enforced canonical Rook profile;
- every deterministic claim is compiled from the same sealed generic language;
- task-local additions require contract/binding data, not evaluator code;
- compiler diagnostics and claim results route to intelligence without being
  mistaken for final statuses;
- attributed judgment can complete permitted qualitative claims without
  overriding proof or custody;
- the Policy Gate alone emits final workflow status; and
- retained evidence independently reconstructs every transition and authority
  decision.
