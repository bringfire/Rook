# LM9B-P Evaluator-Only Continuation Design

- **Date:** 2026-07-22
- **Status:** Approved design captured for written-spec review; no implementation or provider contact authorized
- **Base:** `origin/main` at `abf4b514d46ad3eb91a2779f82b4784be92b5e79`
- **Branch:** `codex/lm9b-p-evaluator-only-continuation-design`
- **Scope:** One separately sealed derivative evaluator observation over the exact recipe bytes preserved by the historical LM9B-P visibility-intervention attempt

## 1. Purpose

The historical visibility-intervention attempt permanently established this official result:

```text
probe_inconclusive
```

That result is not repaired, recovered, replaced, or rewritten. The evaluator-only continuation is a derivative observation whose sole empirical question is:

> Under the corrected evaluator contract and authority boundary, is the exact mechanically accepted recipe semantically faithful, semantically unfaithful, or inconclusive?

The falsifiable prediction is:

```text
semantically_faithful
+ exact recipe has nonempty unresolved_intent
-> probe_candidate_blocked
```

Other valid observations are `semantically_unfaithful` and `evaluation_inconclusive`. Provider failure, timeout, or malformed evaluator output may also produce a sealed `probe_inconclusive` when the attempt evidence is complete and trustworthy.

There is no Planner call, compiler handoff, compiler provider call, compiler construction, checkpoint-2 attempt, or Rhino, Grasshopper, compiler, or mutation execution path in this continuation.

## 2. Governing invariant

> Models propose and judge meaning. Deterministic authority decides what the system knows, what it may do, and whether it may advance.

The evaluator may judge semantic fidelity only. It cannot override explicit recipe state, issue readiness, authorize compilation, or classify the probe directly.

The continuation preserves three separate kinds of truth:

```text
scientific source:
  the immutable historical archive and exact recipe bytes

evaluation instrument:
  corrected rubric and code-owned evaluator protocol at one reviewed commit

attempt identity:
  one unique, destination-bound opportunity for conditional evaluator dispatch
```

### 2.1 Serialized artifact identities

Each top-level serialized state has one exact versioned `schema_id`:

| Serialized state | Required `schema_id` |
|---|---|
| No-contact preflight record | `rook.lm9b_p.evaluator_continuation_preflight:v1` |
| Official sealed derivative identity | `rook.lm9b_p.evaluator_continuation_derivative:v1` |
| Retained forensic staging marker | `rook.lm9b_p.evaluator_continuation_post_dispatch_unsealed:v1` |

Preflight, sealed-derivative, and forensic-staging verifiers require the corresponding `schema_id` in addition to their closed record shapes and file memberships. Directory shape alone never establishes artifact type or validity.

## 3. Historical source binding

The preserved source is read-only:

```text
C:\Users\bring\rook-lm9b-p-attempts\2026-07-22-visibility-intervention
```

The continuation pins these identities:

| Evidence | Required identity |
|---|---|
| Root `SHA256-MANIFEST.txt` | `AC7716B7D5A61E2E6359BC0E01E145D7D17E0871FF03D1D5329710541D274C90` |
| Historical checkpoint aggregate | `sha256:c57c88c61715588a2071d97d73e65f41447754868d18dc8517708734d92a081e` |
| Historical code commit | `15df78ee665cf8ff433a4af20e364365b779143b` |
| Historical official classification | `probe_inconclusive` |
| Historical checkpoint 2 | `not_evaluated` |
| Exact recipe raw SHA-256 | `sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af` |
| Ratified recipe fingerprint | `sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a` |
| Historical recipe fingerprint | `sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a` |

The source verifier must:

1. Hash the root manifest bytes and require the pinned digest.
2. Parse a closed, duplicate-free manifest with safe relative paths.
3. Rehash every listed source file and reject missing, extra, traversal, or mismatched records. The manifest file itself is the sole expected file not listed within itself.
4. Use the existing checkpoint-seal verifier with the pinned checkpoint aggregate identity.
5. Verify the historical commit, classification, checkpoint-2 state, input manifest, final recipe identity, and exact recipe bytes.
6. Expose only bytes that passed those checks.

The continuation never writes inside the historical source directory.

## 4. Constructive source-to-instrument delta

The source archive contains the historical evaluator rubric with the old recommendation vocabulary. That rubric remains immutable evidence of the historical attempt and is **not sent in the continuation**. It was, of course, part of the historical attempt.

The current corrected rubric is the sole evaluator rubric sent by the continuation. The permitted transformation is constructive and closed:

```text
verified archived source inputs
- historical evaluator rubric
+ corrected evaluator rubric from reviewed code
+ current code-owned evaluator protocol
= continuation instrument inputs
```

The continuation must use verified archived input bytes for every source input. It must not silently replace them with current fixture-directory copies.

### 4.1 Shared input validation

The existing frozen-input loader currently combines file reads with input validation. Implementation may factor one record-level constructor from that loader so:

- the normal path reads fixture records and delegates to the shared constructor;
- the continuation supplies verified archived records, substituting only the corrected rubric record, then delegates to the same constructor.

This is a reuse refactor, not a shadow validator. All existing authority, freshness, session, schema, normalization, contract, rubric, and fingerprint checks remain single-sourced.

### 4.2 Allowed-delta manifest

The instrument emits one closed row per archived input:

```text
role
relative_path
source_raw_sha256
source_canonical_fingerprint
instrument_raw_sha256
instrument_canonical_fingerprint
disposition = byte_identical | replaced_evaluator_rubric
```

Exactly one role may use `replaced_evaluator_rubric`. Every other row must be byte-identical. Both rubric raw hashes and canonical fingerprints enter the instrument evidence. Any additional difference is a pre-contact refusal.

## 5. Reusable boundaries and justified extractions

The merged code already provides:

- exact-byte mechanical gate evaluation;
- frozen authority and input validation;
- corrected evaluator request rendering;
- semantic-only parser schema and recommendation meanings;
- one-call evaluator runner;
- explicit-blocker projection;
- deterministic checkpoint classification;
- provider-attempt evidence structures;
- checksum-closed archive patterns;
- readiness route derivation and verification.

There is no evaluator-only continuation entry point. Two small hidden transitions must be factored so the normal and derivative paths share them honestly.

### 5.1 Shared evaluated-recipe decision helper

One pure helper owns the final accepted-recipe equations. Its logical inputs are the semantic evaluator result and verified final recipe bytes. It invokes the existing explicit-blocker projection internally.

| Evaluator state | Explicit blocker | Classification |
|---|---:|---|
| `semantically_faithful` | present | `probe_candidate_blocked` |
| `semantically_faithful` | absent | `probe_candidate_ready` |
| `semantically_unfaithful` | either | `probe_planner_failure` |
| `evaluation_inconclusive` | either | `probe_inconclusive` |
| absent, malformed, provider failure, or sealable timeout | either | `probe_inconclusive` |

The existing normal checkpoint classifier continues to:

1. classify mechanical rejection and non-accepted sessions as today;
2. validate its genuine live `PlannerSessionResult`;
3. validate the independent `checkpoint_gate` and retained accepted-turn gate;
4. prove exact accepted-byte agreement;
5. delegate the accepted-recipe decision to the shared helper.

The derivative continuation:

1. validates the historical source seal;
2. independently recomputes the gate under the assembled frozen inputs;
3. proves the recomputed gate binds the exact sealed recipe bytes;
4. delegates to the same helper.

It never fabricates or reconstructs a Planner session.

### 5.2 Shared provider-call request builder

One pure builder becomes the sole construction path for the evaluator request at Rook's provider-adapter boundary:

```text
rendered semantic evaluator request
+ fixed evaluator system prompt
+ evaluator tool schema
+ fixed tool choice
+ fixed generation limits
-> canonical provider-call request bytes
```

The builder contains no clock, randomness, environment reads, mutable shared object identity, or provider contact.

The preflight stores the canonical bytes. Execution rebuilds and compares them, materializes a fresh request object from the staged canonical bytes, and passes that object exactly once to the provider adapter. Provider-side mutation cannot alter the retained preflight or evidence bytes.

These are bytes at Rook's provider-adapter boundary. LiteLLM may transform them internally. The continuation does not claim they are the provider's final HTTP wire bytes.

## 6. Instrument and attempt identities

The reviewed implementation commit participates in the stable instrument identity because it is the practical identity for the renderer, parser, classifier, builder, and seal code.

```text
instrument_fingerprint = fingerprint(
  verified source identity,
  allowed delta,
  corrected rubric,
  renderer/parser/report-schema/recommendation-meaning identities,
  blocker and classifier contracts,
  provider-call builder and archive contracts,
  model/profile/route/temperature/limits,
  reviewed commit,
  rendered evaluator request bytes,
  canonical provider-call request bytes
)

attempt_fingerprint = fingerprint(
  instrument_fingerprint,
  attempt_id,
  canonical destination
)
```

Two equivalent observations at the same reviewed instrument share an instrument fingerprint but cannot share an attempt fingerprint.

The `attempt_id` grammar is closed and bounded:

```text
^[a-z0-9]+(?:[._-][a-z0-9]+)*$
length: 1..64 characters
```

The attempt ID and destination never enter the evaluator request.

## 7. Destination and atomic reservation

The approved derivative run root is an explicit preflight input. The final destination must be:

- an absolute canonical Windows path;
- strictly contained within the approved derivative run root;
- represented without unresolved traversal;
- reached only through existing ancestors verified not to be reparse points;
- absent at preflight and immediately before reservation;
- on the same filesystem/volume as staging.

Checking path absence is not sufficient. After every pre-contact verification passes, execution atomically creates its staging/reservation directory with `exist_ok=False`.

No staging directory or sealed archive may be overwritten, resumed, or promoted under another identity.

## 8. No-contact preflight

A clean worktree at the reviewed merge SHA emits a checksum-closed preflight record without constructing or contacting a provider. It binds:

- verified source identities;
- exact archived recipe and input identities;
- closed allowed-delta manifest;
- historical and corrected rubric identities;
- independent mechanical-gate result;
- reviewed commit and clean-checkout state;
- renderer, parser, report schema, recommendation meanings, classifier, builder, and seal identities;
- GPT-5.4 evaluator model, `litellm.completion.tool_calling.no_parallel:v1` profile, temperature, limits, and route;
- exact rendered evaluator-request bytes;
- exact canonical provider-call request bytes;
- approved derivative run root;
- attempt ID, canonical destination, instrument fingerprint, and attempt fingerprint.

The deterministic preflight remains valid while its commit, inputs, identities, requests, and destination conditions remain exact.

## 9. Invocation, readiness, and dispatch

Operator approval names the exact preflight fingerprint outside the scientific archive. Unless a signed or otherwise authenticated receipt exists, the harness cannot independently prove human authorization.

The execution archive therefore records only invocation facts under:

```text
launch/invocation-binding.json
```

That record may state:

- the preflight fingerprint supplied at launch;
- the explicit transmit flag;
- the reviewed commit;
- readiness record identity;
- instrument and attempt identities.

### 9.1 Existing readiness protocol

After approval, a fresh content-free readiness canary reuses the existing readiness protocol with one role:

```text
planner_evaluator -> gpt-5.4
```

The readiness route binds:

- adapter path;
- provider;
- model;
- credential-source declaration;
- member role.

It also binds the reviewed commit, canary protocol, request fingerprint, route manifest, observation time, completion time, and existing 600-second freshness window.

Readiness does **not** attest the LM9B-P provider-profile identity. The profile is independently reverified against the preflight instrument and the constructed evaluator adapter. The readiness protocol is not extended merely to claim otherwise.

A failed readiness canary consumes no evaluator observation.

### 9.2 Final pre-dispatch verification

Immediately after readiness passes, execution reverifies:

- `HEAD == preflight.reviewed_commit`;
- checkout remains clean;
- source archive and checkpoint seal remain exact;
- allowed-delta and instrument inputs remain exact;
- independently recomputed gate remains exact;
- rendered evaluator-request bytes remain exact;
- canonical provider-call request bytes remain exact;
- readiness route, model, commit, and freshness match;
- provider-profile identity matches the preflight instrument and constructed evaluator adapter;
- destination remains valid and absent.

### 9.3 Frozen post-verification snapshot

After final verification, execution freezes one in-memory snapshot. After atomic reservation it persists and rereads the exact preflight bytes, verified source/input snapshot, readiness record bytes, and canonical request bytes into staging.

From reservation onward, execution uses only:

- the verified in-memory snapshot;
- the exact preflight and snapshot bytes copied into staging;
- the request freshly rematerialized from staged canonical bytes.

It must not reread the external historical archive or current fixture files after reservation. At seal time it proves that staged snapshot identities still equal the preflight and instrument identities.

### 9.4 Dispatch boundary

Execution then:

1. materializes a fresh provider-call request from staged canonical bytes;
2. validates the fresh value against the staged and preflight fingerprints;
3. persists and rereads `dispatch/dispatch_started.json`;
4. invokes the evaluator adapter exactly once.

`dispatch_started` proves only that the harness crossed its irreversible dispatch boundary. It does not prove HTTP contact, completed adapter entry, or provider receipt.

The attempt ID is conservatively consumed once `dispatch_started` is durable.

## 10. Attempt state machine

### 10.1 Pre-contact failure

```text
dispatch_started absent
evaluator adapter not invoked
no observation consumed
no derivative result
```

The content-free readiness canary may already have contacted its readiness route; this state says only that the evaluator observation was not dispatched. Staging may be removed. Before `dispatch_started`, the same preflight and attempt identity may be reused only with fresh explicit approval and fresh readiness, and only when neither the final destination nor staging residue exists. Once `dispatch_started` is durable, the attempt identity is permanently burned and any later evaluator contact requires a new attempt ID, destination, preflight identity, explicit approval, and fresh readiness.

### 10.2 `post_dispatch_unsealed`

This state is reserved for an attempt where `dispatch_started` is durable but evidence integrity, persistence, classification derivation, checksum closure, or finalization is not trustworthy.

External contact may or may not have occurred. The attempt ID is burned, no automatic retry is allowed, and no classification or architectural claim is issued.

The retained staging directory must carry an unmistakable `post_dispatch_unsealed` marker and retain, best-effort:

- attempt ID and attempt fingerprint;
- instrument and preflight fingerprints;
- canonical destination;
- exact readiness record bytes;
- dispatch marker;
- canonical pre-call request bytes;
- captured adapter request, response/error, usage, timing, metadata, and tool arguments when available;
- failure locus;
- per-file partial forensic hashes.

Partial hashes are explicitly not checksum closure and do not create an official derivative archive identity. Retained staging is outside the official sealed-archive namespace and can never be loaded as a valid continuation result.

### 10.3 Sealed derivative

A sealed derivative requires complete trustworthy evidence and verified checksum closure. It may contain either:

- one valid semantic recommendation and its deterministically derived classification; or
- one completely captured evaluator/provider failure producing `probe_inconclusive`.

A timeout is complete and quiescent only when the evaluator adapter has terminally returned or raised and every owned execution context has been joined. A still-live or otherwise ambiguous timeout becomes `post_dispatch_unsealed`.

## 11. Derivative scientific archive

The official archive is self-contained for the continuation inputs while binding the complete external historical archive by its pinned root manifest and checkpoint identities.

```text
derivative-archive/
|- identity.json
|- source/
|  |- binding.json
|  |- SHA256-MANIFEST.txt
|  |- checkpoint-checksums.json
|  |- original-identity.json
|  |- original-classification.json
|  |- final-recipe.json
|  |- final-recipe-identity.json
|  `- inputs/                         exact verified archived input bytes
|- instrument/
|  |- allowed-delta-manifest.json
|  |- corrected-evaluator-rubric.json
|  |- protocol-identity.json
|  `- mechanical-gate.json
|- preflight/
|  |- record.json
|  |- rendered-evaluator-request.json
|  `- provider-call-request.json
|- launch/
|  `- invocation-binding.json
|- readiness/
|  |- readiness-record.json
|  |- credential-preflight.json
|  `- verification.json              verification time and pure launch decision
|- dispatch/
|  `- dispatch-started.json
|- evaluator/
|  |- attempt/
|  |  |- capture.json
|  |  |- provider-call-request.json
|  |  |- adapter-request.bin          when available; not claimed HTTP wire bytes
|  |  |- response.bin                 when available
|  |  |- error.bin                    when available
|  |  |- usage.json                   when available
|  |  |- assistant-message.json       normalized adapter evidence when returned
|  |  `- tool-arguments/              when available
|  `- result.json
|- decision/
|  `- classification.json
|- boundary.json
`- checksums.json
```

The archive establishes only:

- evaluator termination and captured evidence;
- deterministic classification when evidence permits one;
- boundary facts and non-claims.

It contains no successor recommendation, authenticated-authorization claim, Planner session, compiler evidence, execution authority, or hidden chain-of-thought.

`boundary.json` records that Planner entry is absent, compiler entry is absent, checkpoint 2 is `not_evaluated`, execution is not permitted, and the archive is a derivative observation that does not replace the historical result.

## 12. Evidence capture

The continuation preserves:

- exact semantic evaluator request bytes;
- exact canonical provider-call request bytes before dispatch;
- exact adapter-produced request capture when available, labeled as adapter/LiteLLM evidence rather than HTTP wire evidence;
- raw response or error bytes when available;
- normalized assistant-message evidence when the adapter returns;
- evaluator tool arguments when available;
- parsed evaluator termination, recommendation, and visible evidence;
- usage, timing, model response identity, provider metadata, and profile identity when available;
- readiness record and route identities;
- the exact readiness verification time, supplied credential-presence evidence, and pure launch decision;
- all deterministic gate, blocker, classification, and archive inputs.

The sealed verifier reconstructs the evaluator result from the normalized assistant message and exact archived tool arguments through the same pure parser used by live evaluation. It reruns the readiness contract from the archived record, route, verification time, and credential-presence evidence; validates invocation and dispatch records against the preflight, attempt, request, and readiness identities; then derives classification from the reconstructed evaluator result and exact recipe bytes. A checksummed authored claim is never accepted as its own authority.

No request asks for hidden chain-of-thought. Visible criterion findings are the semantic evidence contract.

## 13. Outcome and failure matrix

| Condition | Dispatch crossed | Attempt consumed | Result |
|---|---:|---:|---|
| Readiness failure | No | No | Readiness evidence only; no derivative observation |
| Pre-contact source, identity, request, or destination failure | No | No | Refusal; removable pre-dispatch staging if present |
| Provider exception with complete evidence | Yes | Yes | Sealed `probe_inconclusive` |
| Complete, quiescent provider timeout | Yes | Yes | Sealed `probe_inconclusive` |
| Still-live or evidentially ambiguous timeout | Yes | Yes | Retained `post_dispatch_unsealed`; no classification |
| Malformed evaluator report with complete evidence | Yes | Yes | Sealed `probe_inconclusive` |
| `semantically_faithful` with unresolved intent | Yes | Yes | Sealed `probe_candidate_blocked` |
| `semantically_faithful` without explicit blocker | Yes | Yes | Sealed `probe_candidate_ready` in the shared normal-path contract; not predicted for these bytes |
| `semantically_unfaithful` | Yes | Yes | Sealed `probe_planner_failure` |
| `evaluation_inconclusive` | Yes | Yes | Sealed `probe_inconclusive` |
| Interruption after `dispatch_started` | Unknown external contact | Yes | Retained `post_dispatch_unsealed` |
| Post-dispatch evidence corruption or identity mismatch | Unknown/possible | Yes | Retained `post_dispatch_unsealed` |
| Classification derivation failure | Unknown/possible | Yes | Retained `post_dispatch_unsealed` |
| Checksum verification failure | Unknown/possible | Yes | Retained `post_dispatch_unsealed` |
| Unreconciled final rename state | Unknown/possible | Yes | Retain all material; no result |

Provider/evaluator failure is not sealing failure. Complete trustworthy failure evidence produces a sealed inconclusive derivative. `post_dispatch_unsealed` is reserved for the absence of trustworthy evidence closure or result derivation.

## 14. Atomic finalization and rename reconciliation

The final archive is checksum- and identity-verified with a private staging verifier, then renamed on the same filesystem to the exact destination. The public official verifier additionally requires the runtime archive path to equal the preflight-bound canonical destination; a copied archive is not an official result.

If rename reports an exception:

1. Inspect the final destination.
2. If it exists and verifies against the exact expected checksums and derivative identity, treat it as sealed.
3. If staging remains and the destination is absent or invalid, retain staging as `post_dispatch_unsealed`. If only an invalid destination remains, best-effort write the unsealed marker there.
4. If both exist or state remains ambiguous, retain all material and issue no result.

The harness never deletes already-written post-dispatch evidence during cleanup. Filesystem-related retention remains best-effort, but absence of retention cannot be promoted into a classification.

## 15. Compiler isolation

The continuation may reuse generic provider types and adapter machinery historically located under LM9B-C filenames. Import location is not compiler entry.

The continuation entry point must not:

- accept Planner or compiler provider arguments;
- load compiler controls;
- construct a compiler-role provider;
- call a compiler session or compiler evaluator function;
- build or accept a compiler handoff destination;
- accept compiler fixtures, identities, or inputs;
- emit compiler evidence paths;
- enter checkpoint 2.

Tests patch the actual compiler-specific construction and entry functions to raise, and prove they remain untouched. Closed derivative archive membership rejects compiler evidence as a second structural proof.

## 16. Deterministic verification strategy

All implementation tests use fake providers and temporary directories. No real readiness canary or model contact occurs.

The suite remains compact:

1. **One vertical witness** through the actual continuation entry point:
   verified source fixture -> one-rubric delta -> independent gate -> preflight -> matching invocation -> fresh fake readiness -> atomic reservation -> one faithful evaluator call -> `probe_candidate_blocked` -> verified derivative seal.
2. **One parameterized outcome table** covering the complete shared classifier truth table, malformed/provider failure outcomes, and preservation of the existing ready path.
3. **One parameterized pre-contact mutation table** covering source, manifest, rubric delta, prompt, renderer, parser schema, meanings, tool schema, limits, builder, route, model, profile, commit, destination, request, readiness, and reparse/containment drift; every row proves zero evaluator calls.
4. **One post-dispatch fault-injection table** covering provider mutation, provider exception, quiescent and ambiguous timeouts, interruption after the dispatch marker, evidence corruption, identity mismatch, classification failure, and checksum failure.
5. **One rename-reconciliation table** covering rename-success-then-exception, failure-before-move, invalid destination, and simultaneous/ambiguous staging and destination states.

Additional structural assertions prove:

- the provider-call builder is pure and single-sourced;
- provider mutation cannot alter preflight or retained request bytes;
- instrument fingerprint changes with reviewed commit;
- attempt fingerprint changes with attempt ID or destination;
- atomic reservation admits only one concurrent claimant;
- post-verification execution performs no source archive or fixture rereads;
- staged snapshot identities equal preflight and instrument identities at seal time;
- unsealed staging cannot pass the official archive verifier;
- a consumed attempt cannot be resumed, overwritten, or rebound;
- no compiler-specific entry point or evidence namespace is reachable;
- the original source archive remains byte-identical.

The complete LM9B-P test family, Python compilation checks, and `git diff --check` remain required before implementation review.

## 17. Post-merge operational sequence

No provider contact is authorized by this design or its implementation review.

After implementation is reviewed and merged:

1. Create a clean worktree at the reviewed merge SHA.
2. Emit the no-contact preflight record.
3. Obtain fresh user authorization naming the exact preflight fingerprint.
4. Run the existing content-free readiness canary for only the GPT-5.4 evaluator route.
5. If and only if readiness passes, immediately reverify commit, checkout cleanliness, source, delta, gate, rendered request, provider-call request, readiness route/model/commit/freshness, independently verified provider profile, and destination.
6. Atomically reserve staging, freeze and persist the execution snapshot, write `dispatch_started`, make at most one evaluator call, and seal or retain evidence according to the state machine.

Before `dispatch_started`, the same preflight and attempt identity may be reused only under the exact Section 10.1 conditions. After `dispatch_started`, any later evaluator contact requires a new attempt ID, destination, preflight identity, explicit authorization, and fresh readiness. There is no automatic retry or resume of a dispatched attempt.

## 18. Result interpretation outside the scientific archive

The scientific archive carries no successor policy. A separately reviewed result note may interpret the derivative observation:

- `semantically_faithful -> probe_candidate_blocked`: next design pressure is one governed-resolution vertical slice using explicit user clarification, preserving the blocked recipe and producing a distinct authority-backed revision before unchanged LM9B-C.
- `semantically_unfaithful -> probe_planner_failure`: investigate the exact Planner semantic defect before designing resolution.
- `evaluation_inconclusive` or another sealed `probe_inconclusive`: treat it as an observation/instrument result and make no architectural claim.
- `post_dispatch_unsealed`: the attempt was conservatively consumed, but no trustworthy scientific result exists.

This document does not design the resolution slice.

## 19. Scope and stop conditions

### In scope

- derivative source verification;
- constructive rubric-only delta;
- shared input-validation factoring;
- shared evaluated-recipe decision equations;
- shared pure provider-call request builder;
- no-contact preflight and two-level identities;
- one-route readiness reuse;
- canonical Windows destination and atomic reservation;
- frozen execution snapshot;
- at most one evaluator dispatch;
- derivative evidence, unsealed retention, sealing, and verification;
- deterministic fake-provider tests.

### Out of scope

- Planner calls or reconstructed Planner sessions;
- compiler controls, handoff, construction, calls, or changes;
- checkpoint-2 execution;
- LM9A-S;
- governed-resolution implementation;
- new semantic vocabulary or blocker classes;
- generalized replay machinery;
- a new readiness protocol;
- a new provider adapter or provider ownership refactor;
- live Rhino or Grasshopper work;
- real provider contact during design or implementation;
- hidden chain-of-thought capture.

Stop if implementation requires recipe repair, normalization, translation, reserialization, source-archive mutation, an additional input delta, a shadow gate/classifier, compiler involvement, a second evaluator call, or a claim that incomplete evidence supports a result.

## 20. Acceptance criteria

The implementation is reviewable when deterministic evidence proves:

1. The exact sealed recipe bytes are consumed unchanged.
2. Every source input except the historical rubric is byte-identical in the instrument.
3. Only the corrected rubric and merged evaluator protocol are sent.
4. The independent mechanical gate accepts under the frozen assembled inputs.
5. Preflight freezes the exact reviewed source, instrument, commit, rendered request, provider-call request, attempt ID, and destination.
6. Readiness reuses the existing one-route protocol without claiming provider-profile attestation.
7. The final execution snapshot is frozen and source files are not reread after reservation.
8. Exactly one evaluator adapter invocation is possible.
9. Every complete evaluator/provider outcome seals with the correct deterministic classification.
10. Every post-dispatch integrity or sealing failure retains clearly unsealed evidence and issues no result.
11. Atomic rename ambiguity is reconciled before result issuance.
12. Planner and compiler entry remain structurally absent.
13. The original `probe_inconclusive` archive remains untouched.
14. No model, readiness, compiler, Rhino, or Grasshopper contact occurs before separate post-merge authorization.
