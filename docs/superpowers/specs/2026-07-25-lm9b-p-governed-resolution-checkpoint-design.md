# LM9B-P Governed-Resolution Checkpoint Design

- **Date:** 2026-07-25
- **Status:** Approved design captured for written-spec review; no implementation, readiness, provider, compiler, Rhino, Grasshopper, or mutation contact authorized
- **Base:** `origin/main` at `d6330a61a21d56abf16af6ba3b8f1678ede2c3ec`
- **Branch:** `codex/lm9b-p-governed-resolution-checkpoint-design`
- **Scope:** One separately sealed governed-resolution checkpoint that tests whether explicit successor task authority lets one bounded Planner revision turn the exact faithful blocked parent into an exact isolated faithful-ready successor

## 1. Purpose

The LM9B-P campaign has established the intended distinction between semantic
competence and missing authority:

```text
frontier Planner
-> mechanically accepted recipe
-> semantically faithful
-> explicit unresolved intent
-> deterministic probe_candidate_blocked
```

The Planner did not fail by refusing to invent five material values. The
system correctly refused to advance because those values were not established
by task authority.

The generic task-local typed-fact carrier is now implemented, merged, and
post-merge qualified. It can carry the clarification without adding radial
field names to production contracts or teaching deterministic code what those
names mean.

This slice tests the next falsifiable hypothesis:

> Given the immutable blocked parent recipe and a successor task envelope
> containing explicit user-authoritative values for exactly its complete
> unresolved-key set, one bounded Planner revision can emit a complete
> successor recipe that preserves all unrelated semantics, consumes the new
> facts through exact authority references, removes exactly the resolved
> uncertainty, and introduces no unauthorized change.

The governing invariant remains:

> Models propose artifacts and judge meaning. Deterministic authority decides
> what the system knows, what it may do, and whether it may advance.

## 2. Established evidence and prerequisite identities

| Evidence | Identity |
|---|---|
| Historical visibility attempt | `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-visibility-intervention` |
| Historical source-manifest SHA-256 | `sha256:ac7716b7d5a61e2e6359bc0e01e145d7d17e0871ff03d1d5329710541d274c90` |
| Exact blocked recipe raw SHA-256 | `sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af` |
| Blocked recipe fingerprint | `sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a` |
| Parent task-envelope fingerprint | `sha256:34ce903bafb24774f5c97568ba7da0d28f7fa99eefe844a329ab2a685793758d` |
| Evaluator-only derivative identity | `sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94` |
| Evaluator result | `semantically_faithful` |
| Deterministic parent classification | `probe_candidate_blocked` |
| Typed-fact carrier merge commit | `d6330a61a21d56abf16af6ba3b8f1678ede2c3ec` |
| Post-merge carrier qualification | `sha256:ad12f0cec491b64f51982b7069acfa1301c1d577071cff9498cf7fba260446e1` |
| Forward payload schema | `rook.planner_task_typed_facts_payload:v1` / `sha256:83d350bf82588b650b5ded99a7bb95b2f4548c214b2b2f10a9e73731cb356064` |
| Semantic-value registry | `rook.semantic_value_schema_registry:v2` / `sha256:da050bc62130c299e0007b87e43f428c1cab76e07e0748e32196c4a4d531848e` |
| Scientific schema profile | `rook.json_schema_profile:lm9_typed_fact_v1` / `sha256:a77df00e33e02c7521c54d8da409e2881e503b21994a90513a9edb7b030fecea` |
| Typed-value helper contract | `rook.lm9.semantic_typed_values:v1` / exact source and runtime identity bound by the post-merge qualification |
| Qualified radial successor-envelope fingerprint | `sha256:3a3caf0498327c3c75f4a1e60bd7277fb88b352cd212fb433d59fba481da3808` |

The official historical attempt remains permanently `probe_inconclusive`.
The evaluator-only derivative remains a separate observation. This slice does
not rewrite, recover, replace, normalize, or reserialize either archive.

The carrier qualification is a prerequisite instrument observation, not user
authority and not a model observation. The archived `probe_candidate_blocked`
inside it is a reconstructed historical-parent control.

## 3. Experimental fixture

The radial fixture supplies these exact values:

| Semantic key | Value | Schema | Unit |
|---|---:|---|---|
| `box_footprint_x` | `"1"` | `rook.semantic_scalar:v1` | `model_unit` |
| `box_footprint_y` | `"1"` | `rook.semantic_scalar:v1` | `model_unit` |
| `grid_spacing` | `"2"` | `rook.semantic_scalar:v1` | `model_unit` |
| `minimum_height` | `"1"` | `rook.semantic_scalar:v1` | `model_unit` |
| `maximum_height` | `"10"` | `rook.semantic_scalar:v1` | `model_unit` |

Each typed value uses the exact environment unit-context reference:

```yaml
unit_context_ref:
  kind: artifact_value
  artifact_id: environment_snapshot
  json_pointer: /document/unit_context
```

Each corresponding binding has `authority_kind: user_fact`. The controlled
fixture uses already-qualified `deterministic_fixture` provenance; this slice
does not add trusted-ingress product behavior. Values, radial names, the
expected count of five, and radial clause expectations exist only in fixture
oracles and sealed policy-instance evidence.

The obsolete `permitted_assumption_outcomes` field in the historical recipe is
not consumed and grants no authority.

## 4. Scope and non-scope

### 4.1 In scope

- physical verification of the exact historical source, faithful derivative,
  carrier qualification, code-owned contracts, and successor fixture;
- pure assembly of one verified parent/successor authority transition;
- one dedicated versioned Planner revision request protocol;
- one shared fingerprinted isolation-policy definition and derived instance;
- one bounded GPT-5.4 Planner revision session using the existing controller;
- the existing mechanical gate and mechanical-only within-session feedback;
- one deterministic isolation gate before evaluator contact;
- at most one independent GPT-5.4 semantic evaluator call;
- deterministic resolution-checkpoint classification;
- one closed preflight, attempt lifecycle, sealed archive, retained forensic
  state, and public constructive verifier;
- one sealed ready-output interface for a separately authorized later LM9B-C
  continuation;
- fake-provider, mutation, fault, race, and exact-specimen no-contact proofs.

### 4.2 Out of scope

- deterministic recipe patching, repair, translation, or expected-successor
  construction;
- isolation or semantic feedback to the Planner;
- a second Planner attempt, automatic retry, or changed-input resume;
- a generic clarification artifact, resolution receipt, issuer catalog, or new
  semantic authority vocabulary;
- changes to the typed-value registry/profile or generic carrier semantics;
- a new recipe dialect, normalization profile, Planner controller, evaluator
  recommendation vocabulary, provider adapter, readiness protocol, classifier,
  or compiler representation;
- LM9A implementation or any claim of authoritative `valid`, `blocked`, or
  `compile_ready` product state;
- compiler readiness, compiler provider contact, compiler evaluation, Rhino,
  Grasshopper, mutation, or execution;
- policy-selected values, Planner assumptions, derived values, confirmation
  receipts, or the superseded assumption-outcome field as resolution authority;
- a generalized replay, replanning, or product interaction framework.

## 5. Selected architecture

### 5.1 Approach 1: thin governed-resolution checkpoint layer — selected

The new layer owns only:

- revision request rendering;
- isolation-policy instantiation and deterministic comparison;
- resolution preflight and bounded orchestration;
- resolution-specific evidence and archive verification;
- a sealed ready-output interface.

It composes the qualified carrier, existing Planner controller, mechanical
gate, evaluator parser/builder, deterministic classifier, readiness verifier,
and later LM9B-C join.

### 5.2 Rejected: revision mode in the first-authorship checkpoint

This would couple immutable historical first-authorship behavior and archive
verification to a materially different parent/successor transition. It would
increase regression and identity risk while obscuring the missing boundary.

### 5.3 Rejected: generic replanning framework

This would prematurely introduce event types, authority channels, and
product-like orchestration before the single clarification hypothesis is
tested. Runtime replanning remains later work.

## 6. Component boundary

```text
physical evidence loaders and public verifiers
-> immutable proof carriers and exact bytes
-> pure VerifiedResolutionInputs assembler
-> pure revision renderer
-> existing bounded Planner controller
-> independent mechanical gate
-> deterministic isolation gate
-> independent semantic evaluator
-> deterministic resolution classification
-> sealed resolution checkpoint
-> separately authorized future compiler continuation
```

### 6.1 Physical evidence layer

Read-only loaders independently verify:

- the production-pinned historical source;
- the sealed evaluator-only derivative and parser-derived recommendation;
- the post-merge carrier qualification;
- current code-owned carrier contracts and source identities;
- exact successor-envelope bytes;
- reviewed checkout commit and cleanliness.

They return immutable verified proof carriers and exact bytes. Downstream pure
components receive no paths and do not reread archives, fixtures, Git state,
or external files.

### 6.2 Pure resolution-input assembler

The assembler accepts only verified proof carriers and exact bytes. It neither
loads evidence nor issues authority. It returns one `VerifiedResolutionInputs`
carrier containing:

- exact parent recipe and current successor authority;
- verified representation-migration ledger;
- verified semantic-authority partition;
- closed carrier-support instrument delta;
- value-free clarification correspondence;
- shared isolation-policy instance;
- current frozen Planner inputs;
- recomputable component identities.

The current Planner authority snapshot is a verified closed composition of
existing authority plus the permitted successor-envelope replacement. It is
not a new authority issuer.

## 7. Authority-transition equations

Let:

```text
P = parent established task-fact keys
U = complete parent unresolved-key set
S = successor task-fact keys
```

Production logic derives all sets from verified artifacts. Only the radial
fixture oracle asserts that `|U| == 5`.

Before set derivation, the successor envelope must retain the exact
`rook.planner_task_envelope:v1` schema, reserved `artifact_id: task_envelope`,
and parent `task_session_id`, while carrying its own independently recomputed
artifact fingerprint. The current semantic authority contains exactly one
task-envelope artifact. Parent envelope bytes and identity remain immutable.

The assembler requires:

```text
P intersection U = empty
S = P union U
successor retained keys = P
successor authority-delta keys = U
```

Exact fact/binding bijection additionally proves no missing, duplicate, or
extra successor fact.

For every `u` in `U`:

```text
parent unresolved semantic_key
  == successor binding semantic_key

parent expected value_schema
  == successor binding value_schema
  == successor typed-value schema

parent expected task-envelope artifact and pointer
  == successor binding artifact and pointer

parent required unit-context reference
  == successor complete typed-value unit-context reference

user_fact is permitted by the parent unresolved row
successor binding authority_kind == user_fact
```

Null unit-context values compare literally; null is never a wildcard.

### 7.1 Retained representation migration

For every key in `P`, the migration ledger requires:

- exact canonical complete typed-value bytes;
- exact schema, value type and spelling, unit, and unit-context reference;
- exact authority kind and provenance;
- exact semantic key and binding coverage;
- independently verified fingerprints.

No coercion, normalization, default insertion, unit conversion, or semantic
equivalence is permitted.

### 7.2 Authority and instrument partition

The composition is partitioned explicitly:

```text
semantic authority:
  environment bytes unchanged
  planning-policy bytes unchanged
  task envelope replaced exactly once

carrier-support instrument:
  only the exact post-merge-qualified payload-schema/registry delta

everything else:
  byte-identical and descriptor-identical
```

Code-owned carrier schemas and registry documents remain instrument context.
They are not inserted into semantic authority or presented as an authority
artifact. The semantic artifact-ID set remains closed and unchanged.

### 7.3 Value-free correspondence

Each derived row contains only:

- parent unresolved-intent ID;
- semantic key;
- expected schema and unit-context reference;
- expected source artifact and pointer;
- successor envelope identity;
- successor binding ID and pointer.

It contains no value, typed-value fingerprint, clause suggestion, edit path,
copied prose, or interpretation. Rows use the ratified UTF-16 semantic-key
ordering. The map describes correspondence and carries no authority.

### 7.4 Transition lineage ledger

Lineage is scientific evidence, not task authority. The transition ledger
binds:

- parent recipe fingerprint;
- parent task-envelope fingerprint;
- successor task-envelope fingerprint;
- exact authority-partition and correspondence fingerprints;
- successor recipe fingerprint when a candidate is mechanically accepted.

No lineage field is inserted into semantic facts, value bindings, recipe
meaning, or the Planner authority snapshot.

## 8. Revision request protocol

The dedicated request schema is a new protocol, not a new recipe dialect or
controller. Its renderer is pure, versioned, fingerprinted, and canonical.

Model-visible inputs are limited to:

- exact original governed brief;
- exact immutable parent recipe;
- verified successor authority;
- value-free correspondence map;
- unchanged recipe schema and authoring contract;
- complete value-free revision/isolation obligations;
- unchanged terminal submission contract.

The original brief supplies semantic context but no authority. The Planner
must dereference material values from the successor task envelope.

The obligations state generically:

- emit one complete successor `rook.planner_graph_recipe:v1`, not a patch;
- consume supplied facts through their actual authority references;
- resolve exactly the mapped unresolved entries;
- preserve every unrelated normalized semantic element;
- introduce no additional material change.

The request hides R01, compiler information, expected topology, evaluator
feedback, expected classification, and expected successor structure.

## 9. Required shared Planner-request extraction

`run_planner_session()` currently constructs turn requests inline. This slice
must factor one pure builder:

```text
transcript state
+ fixed system prompt
+ Planner tool schema and choice
+ generation controls
+ dynamically computed call timeout
-> canonical provider-adapter request value and bytes
```

The builder becomes the sole construction path for:

- existing first-authorship execution;
- governed-resolution execution;
- response-dependent request reconstruction by public verifiers.

It performs no clock read, randomness, environment lookup, filesystem access,
or provider contact. The controller computes the remaining call timeout and
passes it as an explicit builder input.

The existing mechanical-feedback renderer remains the sole feedback path and
must also be reusable by reconstruction. The extraction changes no controller
policy, request value, parameter, diagnostic, or budget.

Compatibility proves exact preservation of:

- provider-request values and canonical bytes;
- feedback messages;
- session behavior and classifications;
- value-derived protocol and request fingerprints.

Historical archives remain immutable. Commit-bound attempt and archive
identities are not claimed to remain equal after a code change.

## 10. Planner controls and actual terminal semantics

Both roles retain the historical controls:

| Control | Value |
|---|---|
| Planner model | `gpt-5.4` |
| Evaluator model | `gpt-5.4` |
| Provider profile | `litellm.completion.tool_calling.no_parallel:v1` |
| Planner maximum turns | `6` |
| Planner max completion tokens per call | `16,384` |
| Planner provider timeout | `180s` |
| Planner overall deadline | `600s` |
| Planner token stop threshold | `120,000` |
| Planner cost stop threshold | `$10.00` |
| Evaluator maximum calls | `1` |
| Evaluator max completion tokens | `8,192` |
| Evaluator provider timeout | `180s` |
| Temperature | existing `0.0` role configuration |

Tool protocol and no-parallel behavior remain unchanged. Four historical
Planner calls are evidence, not a new maximum.

The existing controller semantics are preserved exactly:

```text
maximum turns, token stop, or cost stop after rejected submissions
-> mechanically_rejected session
-> probe_mechanically_rejected

provider failure or terminal timeout
-> probe_inconclusive when evidence is complete and quiescent

ambiguous or still-live execution
-> post_dispatch_unsealed
```

No fallback model, profile substitution, automatic retry, parameter adaptation,
or second attempt is permitted. Returned provider/model metadata is retained
because equal requested model strings do not prove equal hosted weights.

The existing controller terminates the session on the first mechanically
accepted submission. Independent mechanical reevaluation and isolation occur
after that terminal submission; isolation rejection cannot produce another
turn or another attempt.

## 11. Isolation policy and deterministic gate

One shared policy definition has two projections:

- a model projection containing complete procedural obligations;
- a gate projection containing named equations and residual comparison rules.

One derived policy instance binds exact parent, successor, correspondence,
normalization, clause-location, and reference identities. Renderer and gate
must consume the same policy-instance fingerprint.

Let `N(parent)` and `N(candidate)` be independently normalized under the same
frozen normalization profile.

### 11.1 Source descriptor equation

Every `source_task` field remains identical except:

```text
parent task-envelope fingerprint
-> verified successor task-envelope fingerprint
```

### 11.2 Unresolved-row equation

Candidate unresolved intent equals parent unresolved intent minus exactly the
rows whose semantic keys are in `U`. Because `U` is the complete parent
unresolved set, candidate `unresolved_intent` must be empty. No altered or new
row is permitted.

### 11.3 Goal-projection equation

Candidate `goal.projected_into.unresolved_intent_ids` equals the parent
collection minus exactly the resolved rows' intent IDs. Every other goal field
remains identical unless separately owned by another named equation.

### 11.4 Clause ownership equation

Each authenticated parent `affected_clause_id` resolves to exactly one parent
clause occurrence, category, and canonical pointer. The same candidate clause
ID must occur at the same category and structural location. Only that exact
occurrence's `source_refs` field may be equation-owned.

Neutral isolation logic does not hardcode `maintains`, radial keys, or clause
IDs. The radial policy-instance oracle requires its derived categories to be
`maintains`, seals that fact, and makes the procedural requirement visible to
the Planner.

Unresolved or multiply resolved parent ownership, overlapping equation
ownership, or malformed policy instances are control failures. Candidate
movement or category change is a completed isolation rejection.

### 11.5 Authority-reference equation

For each affected clause `c`, let:

```text
A_c = canonical parent source references
R_c = exact successor references required by resolved parent rows
C_c = canonical candidate source references
```

Require:

```text
A_c intersection R_c = empty
C_c = A_c union R_c
|C_c| = |A_c| + |R_c|
unique(C_c) under canonical reference identity
canonical_order(C_c)
```

Each added reference is exactly:

```yaml
kind: artifact_value
artifact_id: task_envelope
json_pointer: <verified successor binding pointer>
```

Coverage is bidirectionally exact. Each resolved key contributes its required
reference exactly once to every derived affected clause, and no other
reference is added, removed, duplicated, reordered, or changed.

### 11.6 Affected-clause residual equation

Apart from the already-proven `source_refs` equation, every field of each
affected clause remains identical. Statements, IDs, edges, assumptions,
derived facts, synthesis, canonicalization, inherited support, and
postconditions do not move.

### 11.7 Recipe-fingerprint equation

The candidate's claimed fingerprint equals the independently recomputed
fingerprint of its normalized projection. Fingerprint movement is recorded
separately and is not treated as semantic change.

### 11.8 Residual equality

Only after a changed region passes exactly one named equation may that exact
location be removed from both comparison projections. Canonical bytes of the
remaining normalized projections must be identical.

There is no path-prefix masking, subtree wildcard, patch construction, repair,
or expected-successor object. Every erased location is enumerated, uniquely
owned, consumed, and evidenced.

### 11.9 Isolation result boundary

```text
mechanical acceptance
+ completed isolation comparison
+ observed normalized delta differs from permitted delta
-> probe_resolution_isolation_failure
```

The evaluator is not contacted. The exact candidate bytes and bounded
difference evidence are sealed. The result attributes falsification to the
Planner revision under this experiment, not to recipe grammar or semantic
authority.

Parse, proof-carrier, normalization, policy-instance, ownership, or verifier
integrity failure produces no scientific outcome.

The gate emits evidence and a verdict only. Submitted candidate bytes remain
unchanged and are the only bytes eligible for sealing or later handoff.

## 12. Independent semantic evaluator

The evaluator is dispatched only after independent mechanical acceptance and
isolation success. Those successes are controller preconditions and archived
evidence; they are not model-visible approvals.

Evaluator-visible inputs are limited to:

- exact original brief;
- exact verified successor semantic authority;
- exact isolated successor recipe;
- new versioned semantic-evaluation rubric;
- unchanged report schema and recommendation meanings.

The evaluator does not see the parent recipe, correspondence map, isolation
policy/report, expected classification, Planner session, compiler context, or
mechanical/isolation approval statements.

The new rubric states generically:

> Values present in verified successor authority are supplied facts, not
> unresolved intent or Planner inventions.

The historical rubric remains immutable. Recommendation vocabulary remains:

```text
semantically_faithful
semantically_unfaithful
evaluation_inconclusive
```

The evaluator judges meaning only. Deterministic authority derives advancement.

## 13. Resolution outcome projection

The closed scientific checkpoint outcomes are:

```text
all submitted candidates mechanically rejected until an existing stop bound
-> probe_mechanically_rejected

mechanically accepted + completed isolation rejection
-> probe_resolution_isolation_failure

isolation passed + semantically unfaithful
-> probe_planner_failure

isolation passed + semantically faithful
-> probe_candidate_ready

provider/evaluator failure, timeout, or malformed evaluator evidence
with complete quiescent evidence
-> probe_inconclusive
```

Successful isolation requires every parent unresolved row to be resolved,
forbids new unresolved rows, and permits no unrelated change. Therefore
`probe_candidate_blocked` is unreachable. If the shared classifier returns it
after isolation passed, the instrument equations disagree: this is an
integrity failure with no scientific outcome.

`probe_candidate_ready` means experimental eligibility for the inert compiler
experiment only. It is not LM9A `compile_ready` or product authorization.

## 14. Preflight identities and authorization envelope

The no-contact preflight uses exact versioned top-level identities:

| State | `schema_id` |
|---|---|
| Resolution preflight | `rook.lm9b_p.governed_resolution_preflight:v1` |
| Sealed checkpoint | `rook.lm9b_p.governed_resolution_checkpoint:v1` |
| Retained forensic marker | `rook.lm9b_p.governed_resolution_post_dispatch_unsealed:v1` |

Define:

```text
instrument_fingerprint =
  verified historical source and derivative
  + carrier qualification and exact carrier-support delta
  + successor-envelope identity
  + revision renderer and exact initial semantic request
  + Planner controller, request builder, feedback protocol, and bounds
  + isolation policy definition and instance
  + evaluator renderer, rubric, report contract, parser, and request builder
  + model/profile/control identities
  + reviewed commit

attempt_fingerprint =
  instrument_fingerprint
  + bounded attempt_id
  + canonical destination
```

The closed attempt-ID grammar is:

```text
^[a-z0-9]+(?:[._-][a-z0-9]+)*$
length: 1..64 characters
```

The attempt ID and destination remain out of model requests.

One explicit invocation may cover this closed contact envelope:

```text
Planner calls: 1..N within one bounded session
Evaluator calls: 0..1 under the exact conditional predicate
Compiler calls: 0
```

The Planner preflight binds exact initial semantic request bytes plus the
controller, system prompt, tool schema, dynamic request builder, feedback
renderer, diagnostic vocabulary, and turn/call/token/time/cost limits.

The evaluator preflight binds its conditional dispatch predicate, renderer,
rubric, report contract, provider-request builder, route/profile/model, and
one-call limit. Its response-dependent request bytes are not knowable before a
candidate exists.

Launch evidence records the supplied approved-preflight fingerprint, explicit
transmit flag, reviewed commit, readiness identity, and attempt identity. It
claims only that the harness was invoked with those values; it does not claim
to authenticate human authorization.

## 15. Readiness, reservation, and snapshot freeze

After an invocation names the exact preflight:

1. Reuse the existing content-free readiness protocol.
2. Deduplicate equal transport routes while retaining Planner/evaluator member
   roles.
3. Require route, provider, model, credential source, commit, and freshness to
   match; independently reverify provider-profile identity against preflight
   and constructed adapters.
4. Reverify source, derivative, carrier qualification, successor authority,
   carrier-support delta, initial request, policy instance, checkout
   cleanliness, and absent output paths.
5. Atomically create a direct-child staging/reservation directory with
   `exist_ok=False` under the approved resolution root.
6. Persist and reread preflight, attempt identity, readiness bytes, and initial
   canonical request bytes.
7. Freeze execution to the verified in-memory snapshot and staged bytes.

The canonical destination is an absolute Windows path, a direct child of the
approved root, free of traversal and reparse-point ambiguity, and on the same
filesystem as staging.

A preflight may be reused only before the first scientific dispatch, while
destination and staging remain absent and every input remains exact, under a
renewed explicit invocation and fresh readiness. There is no automatic
readiness retry. The first dispatch permanently consumes the preflight and
attempt ID.

## 16. Per-call dispatch protocol

For each Planner turn and the conditional evaluator call:

1. Construct canonical provider-adapter request bytes through the shared pure
   builder.
2. Bind the request to the exact preceding transcript, gate state, dynamic
   timeout, role configuration, and call index.
3. Persist and reread the canonical bytes.
4. Materialize a fresh mutable request object from those bytes.
5. Persist the per-call `dispatch_started` marker.
6. Enter the configured role adapter exactly once.
7. Preserve returned response/error, assistant message, tool arguments, usage,
   timing, requested identity, and returned provider/model metadata.

These bytes freeze the request at Rook's provider-adapter boundary. LiteLLM or
the upstream provider may transform it internally; the archive does not claim
to preserve final HTTP wire bytes.

`dispatch_started` proves the harness crossed its irreversible dispatch
boundary, not confirmed HTTP delivery. A crash after the marker conservatively
consumes the attempt.

Subsequent Planner requests derive only from:

- staged initial snapshot;
- captured prior assistant messages;
- existing mechanical gate results;
- existing mechanical-feedback renderer.

Isolation and semantic evidence never return to the Planner. A provider that
mutates its input cannot alter retained canonical bytes.

## 17. Evidence lifecycle

### 17.1 Pre-dispatch refusal

No provider invocation occurs and no observation is consumed. Staging may be
removed. Any later contact still requires an exact invocation and fresh
readiness under the pre-dispatch reuse rule.

### 17.2 Sealed scientific checkpoint

A checkpoint may seal when complete trustworthy evidence supports one closed
outcome, including complete quiescent provider/evaluator failures that produce
`probe_inconclusive`.

### 17.3 Post-dispatch unsealed

Control, reconstruction, evidence-integrity, classification, persistence, or
sealing failures after dispatch retain staging with:

- attempt ID and attempt fingerprint;
- preflight and instrument fingerprints;
- staged readiness bytes;
- dispatch markers and canonical requests;
- captured provider evidence;
- failure locus;
- best-effort per-file forensic hashes.

These hashes are partial forensic evidence, never checksum closure. The state
has no scientific outcome and no official derivative identity. It is never
loaded as a valid result, resumed, retried, overwritten, or promoted under
another identity.

A timeout is complete and quiescent only when the adapter terminally returns
or raises and every owned execution context has joined. Otherwise it is
ambiguous and unsealed.

### 17.4 Atomic finalization

Finalization uses Windows `Path.rename()` on the same filesystem as the
no-clobber atomic operation; `Path.replace()` is forbidden. After a rename
exception:

1. If the exact destination exists and verifies completely, treat it as sealed.
2. If staging remains and destination is absent or invalid, retain staging.
3. If both exist or state is ambiguous, retain all evidence and issue no
   result.

No destination is ever replaced. If invalid evidence exists only at the final
destination, best-effort marking writes the forensic
`post_dispatch_unsealed` marker at that retained physical location.

## 18. Closed resolution archive

The official archive establishes only scientific observation, deterministic
classification, invocation facts, boundary facts, and non-claims. It contains
no successor-development recommendation.

Its closed membership includes conceptual groups for:

- identity and checksum closure;
- launch invocation binding;
- source and prerequisite bindings;
- instrument and protocol identities;
- frozen semantic authority and carrier-support composition;
- representation migration and authority partition;
- value-free correspondence and isolation-policy instance;
- readiness evidence;
- Planner call ledger, exact requests, responses, usage, and gates;
- exact candidate bytes and independent mechanical gate;
- isolation equations, canonical residual evidence, bounded differences, and
  verdict;
- conditional evaluator call and parser-derived result;
- deterministic classification and boundary facts;
- explicit compiler non-entry.

Before checksum closure and finalization, the writer rereads staged evidence
and proves that source, snapshot, preflight, instrument, attempt, request, and
readiness identities still equal the values verified before dispatch.

Every file and role is closed. Unknown archive members fail verification.

## 19. Public constructive verification

The public verifier proves a closed derivation graph rather than a checksum
story. It independently reconstructs:

- historical and derivative provenance;
- carrier qualification and code-owned contract identities;
- authority composition, key-set closure, migration, and correspondence;
- initial and response-dependent Planner requests;
- parser-derived submissions from captured tool arguments;
- independent mechanical gate results;
- policy instance, clause ownership, reference equations, residual equality,
  and isolation verdict;
- evaluator request from current successor evidence only;
- parser-derived evaluator recommendation;
- deterministic classification;
- invocation, attempt, checksum, identity, and physical destination equations.

The complete call ledger must prove:

- contiguous call indexes and legal role ordering;
- exactly `1..N` Planner calls;
- evaluator calls exactly `0` or `1` according to isolation and Planner
  termination;
- no call after a terminal condition;
- every dispatch marker binds its request and preceding transcript/gate state;
- aggregate usage remains within all attempt budgets;
- no unregistered role or compiler call exists.

Checksums close storage. Independent reconstruction establishes provenance.

## 20. Sealed continuation interface

Only a publicly verified sealed `probe_candidate_ready` archive may issue a
resolution-ready proof carrier containing:

- exact submitted successor recipe bytes;
- independently recomputed recipe fingerprint;
- exact authenticated successor semantic authority records;
- mechanical and isolation proof identities;
- sealed resolution-checkpoint identity.

It exposes no parent recipe, correspondence map, isolation report, evaluator
report, repair information, or compiler suggestion to LM9B-C.

Compiler continuation is a separate proposition:

```text
sealed probe_candidate_ready
-> separate reviewed preflight
-> separate explicit authorization and readiness
-> exact successor recipe and authenticated successor authority
-> unchanged LM9B-C path
```

Compiler failure cannot invalidate or rewrite the resolution checkpoint. No
compiler feedback returns to resolution.

## 21. Deterministic test strategy

### 21.1 Task-1 vertical witness

The first implementation task must walk the real reversible transition:

```text
pinned production source and derivative
-> exact qualified radial successor envelope
-> authority composition and value-free map
-> resolution preflight
-> fresh fake readiness through the real readiness verifier
-> atomic reservation
-> fake Planner turn 1: mechanically invalid submission
-> exact existing mechanical feedback
-> reconstructed turn-2 request
-> fake Planner turn 2: static reviewed accepted successor fixture
-> independent mechanical gate
-> exact isolation pass
-> fake evaluator: semantically_faithful
-> probe_candidate_ready
-> sealed checkpoint
-> public reconstruction
```

The static candidate is test evidence only. Production code contains no recipe
constructor or patcher. Compiler-specific entry points are patched to raise and
must remain untouched. An independent review stop follows this witness.

### 21.2 Parameterized outcome table

Cover:

- maximum-turn, token-stop, and cost-stop mechanical rejection;
- provider failure and terminal timeout;
- ambiguous/still-live timeout;
- isolation rejection;
- faithful-ready and semantically unfaithful;
- evaluator-inconclusive, malformed, and provider failure;
- blocked-after-isolation integrity failure.

### 21.3 Authority mutation table

Fully reclosed mutations cover:

- missing, extra, duplicate, or overlapping `P`, `U`, and `S` keys;
- wrong schema, context, pointer, task session, authority kind, or provenance;
- retained value, type, spelling, unit, context, authority, or coverage drift;
- extra carrier-support delta;
- changed environment, policy, descriptor, or unrelated authority.

### 21.4 Isolation mutation table

Cover every permitted region plus unauthorized changes to statements, IDs,
edges, assumptions, invariants, capabilities, shape, worker slots, references,
descriptor fields, moved/category-changed clauses, duplicate or noncanonical
references, new unresolved rows, and altered fingerprints.

### 21.5 Request/control mutation table

Cover system prompt, initial request, tool schema, feedback renderer,
diagnostic vocabulary, model/profile, dynamic timeout, bounds, isolation
policy, evaluator rubric/report contract, and response-dependent reconstruction.

Pre-dispatch cases additionally cover:

- wrong or dirty reviewed commit;
- stale, missing, extra-role, wrong-model, or wrong-route readiness;
- altered preflight or qualification identity;
- invalid or reused attempt ID;
- destination outside the approved root;
- existing destination or staging residue;
- reparse-point or filesystem mismatch;
- invocation fingerprint mismatch.

Every pre-dispatch case proves zero Planner/evaluator dispatches and no consumed
attempt ID.

### 21.6 Post-dispatch fault table

Cover provider request mutation, provider exception, quiescent and ambiguous
timeout, interruption after dispatch marker, evidence corruption, parser
failure, classifier inconsistency, checksum failure, and persistence failure.

### 21.7 Rename reconciliation table

Cover destination race, successful-but-reported-failed rename, invalid
destination-only material, both staging and destination present, and no-clobber
behavior.

### 21.8 Constructive provenance attacks

After fully reclosing downstream fingerprints and checksums, substitute:

- successor authority;
- revision request;
- captured Planner tool arguments;
- isolation verdict;
- evaluator tool arguments;
- call order;
- physical archive destination.

Public verification must reject each because the authored claim disagrees with
its authority source.

### 21.9 Structural compiler isolation

The resolution entry point:

- accepts Planner and evaluator role providers only;
- accepts no compiler provider, fixture, handoff, or compiler run destination;
- never constructs a compiler-role adapter;
- never invokes compiler session/evaluator functions;
- cannot emit compiler evidence paths;
- rejects archive membership outside the closed resolution schema.

Historically located generic provider types may be reused. Isolation concerns
compiler behavior and evidence, not Python module filenames.

### 21.10 Exact-specimen qualification

Before PR review, the completed no-contact path traverses the pinned production
source, exact derivative, exact carrier qualification, and exact successor
fixture. It emits a clearly non-operational development preflight bound to
feature `HEAD`. Synthetic tests harden this real witness; they do not replace
it.

After merge, a new operational preflight is generated under the reviewed merge
SHA. Neither development nor post-merge preflight generation authorizes
readiness or provider contact.

## 22. Completion stages

### 22.1 Implementation and PR completion

Implementation/PR completion requires:

1. Task-1 two-turn vertical witness and independent review.
2. All deterministic tables and structural guards passing.
3. Existing Planner-transfer, evaluator-continuation, typed-carrier, and full
   LM9B-P family regressions passing.
4. Production-backed no-contact development preflight verifying at feature
   `HEAD`.
5. Clean worktree, clean diff, reviewed implementation, and approved PR.

This stage ends before merge-SHA operational preflight, readiness, or contact.

### 22.2 Post-merge operational preparation

Only after merge:

1. Create a clean checkout at the reviewed merge SHA.
2. Regenerate and publicly verify the operational preflight.
3. Review its exact fingerprint.
4. Separately authorize readiness and the closed Planner/conditional-evaluator
   contact envelope.

Unavailable readiness stops before the attempt. Provider contact is never
implied by implementation, review, merge, or preflight generation.

## 23. Success, falsification, and non-claims

### 23.1 Positive result

```text
verified successor user authority
+ one bounded Planner revision
-> mechanically accepted
-> exactly isolated
-> semantically faithful
-> probe_candidate_ready
```

### 23.2 Attributable alternatives

- `probe_resolution_isolation_failure`: inspect exact Planner delta; do not
  repair or rerun.
- `probe_planner_failure`: investigate the successor's semantic defect.
- `probe_mechanically_rejected`: preserve the bounded controller outcome.
- `probe_inconclusive`: treat as provider/evaluator observation.
- control/integrity failure: no scientific result; preserve forensic evidence.

### 23.3 Non-claims

This slice does not prove:

- LM9A validity or product compile readiness;
- repeatability or generality beyond the tested transition;
- local-model capability;
- compiler success or representation sufficiency;
- execution authorization or runtime correctness;
- trusted-ingress product behavior;
- that equal requested model names identify unchanged hosted weights.

After the sealed resolution observation and optional separately authorized
compiler continuation, empirical harness expansion stops. The next durable
architectural obligation is the separately reviewed LM9A semantic contribution.

## 24. Final design closure

The missing transition is now explicit:

```text
faithful blocked parent
+ verified successor user authority
-> intelligent complete re-authorship
-> mechanical admission
-> deterministic exact isolation
-> independent semantic judgment
-> deterministic experimental eligibility
-> immutable sealed result
```

The design adds one scientific transition boundary without adding a second
authority system, shadow validator, deterministic Planner, compiler coupling,
or premature product replanning framework.
