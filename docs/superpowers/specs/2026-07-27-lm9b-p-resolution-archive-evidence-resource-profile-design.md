# LM9B-P Resolution Archive-Evidence Resource Profile Design

- **Date:** 2026-07-27
- **Status:** Approved design captured for written-spec review; no implementation, readiness, provider, retry, checkpoint promotion, compiler, Rhino, Grasshopper, or mutation contact authorized
- **Base:** `origin/main` at `e81b12cca0eb750a7f3e730d2376085a915d43dd`
- **Branch:** `codex/lm9b-p-resolution-archive-evidence-profile-design`
- **Scope:** One governed-resolution-only archive-evidence resource profile, future checkpoint writer/verifier integration, and one no-contact forensic derivative over the exact retained replacement candidate

## 1. Purpose

The governed-resolution replacement observation completed the intended model and
deterministic transitions through isolation:

```text
six complete Planner calls
-> mechanically accepted successor recipe
-> deterministic isolation rejection
-> provisional probe_resolution_isolation_failure
```

It did not produce an official scientific checkpoint. Checkpoint sealing routed
the cumulative `call-ledger.json` and `planner-session.json` members through
`parse_archive_json()`, whose 1 MiB limit belongs to a single recipe-shaped
input. Both cumulative members legitimately exceeded that limit, and sealing
failed with `StrictJsonError: recipe_input_bytes_exceeded`.

The correct durable state remains:

```text
original attempt state: post_dispatch_unsealed
official scientific checkpoint: absent
ready proof: prohibited
compiler eligibility: false
```

This slice repairs the instrument's archive resource model without changing the
observation, the recipe contract, or any model-facing behavior. It also adds a
separate read-only forensic path that can preserve the independently
reconstructed facts without pretending the original sealing transaction
succeeded.

The governing invariant remains:

> Models propose and judge meaning. Deterministic authority decides what the
> system knows, what it may do, and whether it may advance.

For this slice, that invariant has a physical-evidence corollary:

> A forensic reconstruction may establish facts about retained evidence, but
> it cannot retroactively create the checkpoint that the original transaction
> failed to seal.

## 2. Established observation and pinned evidence

### 2.1 Observed replacement attempt

| Item | Identity or fact |
|---|---|
| Observed implementation commit | `e81b12cca0eb750a7f3e730d2376085a915d43dd` |
| Replacement preflight | `sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856` |
| Observed instrument | `sha256:0b57f30954c375df34b28ba394f2ef281c09388c209e688586187d8759f26d11` |
| Attempt ID | `governed-resolution-e81b12cca0eb-replacement-01` |
| Attempt fingerprint | `sha256:bd350d895f0e34a67aa7ebe59e1e8c4b3b5b3f4e715aa6d81d5874561af10e42` |
| Retained staging | `C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/.governed-resolution-e81b12cca0eb-replacement-01.staging` |
| Reserved destination | `C:/Users/bring/rook-lm9b-p-attempts/2026-07-27-governed-resolution-operational/governed-resolution-e81b12cca0eb-replacement-01` |
| Durable attempt state | `post_dispatch_unsealed` |
| Failure locus | `checkpoint_seal_failure:StrictJsonError` |
| Forensic hashes | 45 retained rows, independently size/hash verified |
| Candidate membership | 15 closed members, independently checksum verified |
| Planner calls | 6 complete request/response rows |
| Evaluator calls | 0 |
| Compiler calls | 0 |

The reserved destination is absent. The retained staging and its
`.archive-candidate` are immutable source evidence for this slice.

### 2.2 Demonstrated resource mismatch

| Candidate member | Exact retained size | Historical parser ceiling |
|---|---:|---:|
| `call-ledger.json` | 1,545,674 bytes | 1,048,576 bytes |
| `planner-session.json` | 1,549,257 bytes | 1,048,576 bytes |

Every other candidate JSON member passes the historical strict archive parser.
The two failures are cumulative evidence members: each contains up to six
bounded call rows, not one model-submitted recipe.

### 2.3 Independently visible provisional facts

The incomplete candidate records, and read-only reconstruction must prove
without trusting those records, that:

```text
Planner termination: mechanically_accepted
isolation status: isolation_rejected
reconstructed candidate classification: probe_resolution_isolation_failure
checkpoint 2: not_evaluated
```

Isolation rejected two additions outside the permitted delta. The candidate
added `minimum_height` and `maximum_height` task-envelope references to the
inherited postcondition. That postcondition was required to remain unchanged.

These facts are meaningful but not yet an official checkpoint result. The
original attempt remains unsealed even if forensic reconstruction succeeds.

## 3. Scope and non-scope

### 3.1 In scope

- one profile with ID
  `rook.archive_evidence_resource_profile:lm9b_resolution_v1`;
- governed-resolution checkpoint writing and public verification only;
- read-only forensic verification of governed-resolution archive candidates;
- the existing closed governed-resolution member paths and roles;
- explicit bounds for evidence fields already retained by the call ledger;
- maximum-cardinality pre-parse and authenticated-count post-parse ceilings;
- future preflight/instrument identity binding for the profile and helper;
- one historical-preflight compatibility verifier pinned to the observed
  `e81b12cc` lineage;
- one separate content-addressed forensic report and public verifier;
- deterministic fake-provider, mutation, fault, cross-checkout, exact-limit,
  and exact-retained-specimen tests.

### 3.2 Out of scope

- changing `MAX_RECIPE_BYTES` or recipe admission;
- changing the default `parse_archive_json()` contract or source identity;
- changing preflight, historical, evaluator-only, carrier-qualification, or
  other archive parsers;
- a general archive-profile registry, plugin mechanism, expression language,
  migration framework, or caller-supplied arbitrary limit;
- sharding or changing governed-resolution checkpoint membership;
- truncation, compression, omission, lossy summaries, normalization, repair,
  or semantic interpretation in the resource layer;
- changing prompts, rubrics, models, provider profiles, timeouts, token limits,
  call limits, mechanical gates, isolation equations, classification equations,
  readiness, or retry policy;
- resealing, renaming, promoting, copying, or modifying the retained candidate;
- issuing a checkpoint or ready-proof carrier from forensic evidence;
- a new Planner/evaluator observation or any compiler continuation.

## 4. Selected architecture

### 4.1 Dedicated governed-resolution evidence layer — selected

The selected design adds:

1. one closed JSON resource-profile contract;
2. one pure governed-resolution archive-evidence helper;
3. narrow integration in the future checkpoint writer and verifier;
4. one separate forensic report module and public verifier.

The existing shared recipe/archive parser remains byte-for-byte and
identity-for-identity unchanged.

### 4.2 Rejected: parameterize the shared archive parser

Adding a profile or limit parameter to `parse_archive_json()` would change a
widely reused historical surface and would force unrelated archive identities
to move. The demonstrated defect does not justify that blast radius.

### 4.3 Rejected: shard cumulative evidence

Splitting the call ledger or Planner session into per-turn members would change
the checkpoint schema and could not verify the exact retained candidate. The
current cumulative representation is valid; only its parser budget is wrong.

## 5. Component boundary

### 5.1 Code-owned profile contract

Add:

```text
scripts/lm9b_p_governed_resolution_contracts/
  archive_evidence_resource_profile.json
```

The contract is strict JSON and contains:

- profile schema and profile ID;
- governed-resolution checkpoint schema ID;
- exact path-to-role snapshot;
- maximum Planner and evaluator cardinalities;
- retained-field byte constants;
- fixed formula IDs;
- serializer, escaping, UTF-8, and base64 identities/constants;
- path-specific fixed-member ceilings;
- profile fingerprint.

The JSON contains constants and closed formula IDs, never executable formula
strings. Unknown fields, duplicate keys, checkpoint schemas, paths, roles,
formula IDs, or fingerprints fail.

The exact profile path-to-role snapshot must equal
`RESOLUTION_ARCHIVE_MEMBERS`. Neither the Python map nor the JSON contract may
drift independently.

### 5.2 Pure archive-evidence helper

Add:

```text
scripts/lm9b_p_governed_resolution_archive_evidence.py
```

Its contract ID is:

```text
lm9b_p.governed_resolution_archive_evidence:v1
```

It owns only:

- strict profile admission and fingerprint recomputation;
- formula-ID dispatch;
- retained-field byte checks;
- indexed call-row ceiling derivation;
- pre-parse and post-parse member ceiling derivation;
- governed-resolution member parsing under the selected profile.

It performs no I/O, environment lookup, provider contact, model behavior,
semantic validation, classification, repair, or policy recommendation.

Profile selection is structural:

```text
known governed-resolution checkpoint schema
+ exact closed member path
+ exact closed member role
-> one fixed formula ID
```

No public API accepts a raw numeric ceiling.

### 5.3 Existing checkpoint writer and public verifier

`lm9b_p_governed_resolution_artifacts.py` remains the owner of checkpoint
membership, evidence reconstruction, checksum closure, identity, publication,
and ready-proof issuance. It delegates only governed-resolution checkpoint
member resource admission to the new helper.

The future writer and verifier consume the same admitted profile carrier. The
profile bytes, fingerprint, member map, helper contract/source identity,
serializer identity, checkpoint schema, and reviewed commit enter the future
instrument manifest before the preflight fingerprint is derived.

### 5.4 Forensic module

Add a separate module:

```text
scripts/lm9b_p_governed_resolution_forensics.py
```

It owns:

- the historical-preflight compatibility verifier;
- physical snapshot and movement checks for the retained source;
- exact candidate checksum and provenance reconstruction;
- forensic report writing, atomic publication, reconciliation, and public
  verification;
- one dedicated forensic carrier type.

It cannot import or call execution orchestration, provider construction,
checkpoint sealing, ready-proof issuance, or compiler continuation functions.
The operational APIs reject its carrier by exact type.

## 6. Parser contract and equivalence

### 6.1 Default parser remains unchanged

The following remain unchanged:

```text
MAX_RECIPE_BYTES = 1_048_576
parse_strict_json()
parse_archive_json()
```

The new parser directly delegates to `parse_archive_json()` whenever the raw
member is at most 1 MiB. This makes under-limit behavior constructive rather
than merely similar.

For larger admitted governed-resolution members, it uses the same existing
grammar helpers and policies:

- strict UTF-8;
- no BOM;
- duplicate-key rejection;
- the same bounded integer-token parser;
- finite floats only;
- the same non-finite-constant rejection;
- the same maximum JSON depth;
- the same JSON decoder behavior.

Its only intentional behavioral difference is the profile-derived raw-byte
ceiling for a known governed-resolution member.

### 6.2 Equivalence claim

For every input of at most 1 MiB, equivalence means either:

```text
identical parsed Python value
```

or:

```text
identical exception type
+ identical stable rejection ID
```

Incidental exception-message text is not part of the equivalence contract.

The new resource layer performs no semantic validation and does not require
canonical input formatting. Canonical serialization is identity-bound for
writer output and budget arithmetic, not added as a new parser rejection.

## 7. Resource profile

### 7.1 Closed member formulas

Every existing checkpoint path has exactly one existing role and one formula
ID:

| Path or role | Formula ID |
|---|---|
| `candidate-recipe.json` | `recipe_member_v1` |
| `call-ledger.json` | `call_ledger_v1` |
| `planner-session.json` | `planner_session_v1` |
| `evaluator.json` | `evaluator_member_v1` |
| Every other closed path | `fixed_member_v1` with a path-specific ceiling |

`recipe_member_v1` remains exactly `MAX_RECIPE_BYTES`. It does not inherit a
larger archive ceiling.

`fixed_member_v1` must look up an explicit path-specific integer ceiling. It
is not one blanket fallback. Unknown paths or duplicate map rows fail.

### 7.2 Retained per-call fields

The profile bounds only fields already retained by the call ledger:

- canonical provider-call request bytes;
- adapter request bytes;
- raw response or raw error bytes;
- assistant/tool projection bytes;
- usage bytes;
- provider metadata bytes;
- fixed row fields and deadline state.

The profile also binds the existing limits and cardinalities that shape those
fields:

```text
MAX_PLANNER_CALLS = 6
MAX_EVALUATOR_CALLS = 1
```

It introduces no new evidence taxonomy and does not change model/provider
limits. Its reviewed integer constants are independent evidence-retention
bounds. Request or response evidence outside those bounds is preserved in
staging but is ineligible for an official checkpoint.

### 7.3 Encoding equations

The helper owns fixed equations selected by formula ID.

Base64 expansion is exact:

```text
base64_ceiling(n) = 4 * ceil(n / 3)
```

JSON string ceilings include quotes and the profile-bound worst-case escaping
for the applicable already-valid UTF-8 field. Object/array framing, field-name
bytes, commas, colons, `null` branches, returned/error branches, and the
canonical serializer configuration are fixed inputs to the formula identity.

The serializer identity is exactly:

```text
json.dumps(
  value,
  ensure_ascii=False,
  sort_keys=True,
  separators=(",", ":"),
).encode("utf-8")
```

### 7.4 Per-call row equations

Planner request ceilings depend on the turn index because later requests
contain bounded prior assistant and mechanical-feedback messages.

For Planner turn `i`:

```text
planner_row_ceiling(i) =
  fixed Planner-row framing
  + json_string_ceiling(canonical_request_ceiling(i))
  + base64_ceiling(adapter_request_ceiling(i))
  + max(
      base64_ceiling(raw_response_ceiling(i)),
      base64_ceiling(raw_error_ceiling(i))
    )
  + assistant_projection_ceiling(i)
  + usage_ceiling
  + provider_metadata_ceiling
```

The evaluator uses the corresponding fixed single-call equation:

```text
evaluator_row_ceiling(1)
```

`evaluator_member_v1` has a closed presence and projection rule:

```text
E = 0
-> evaluator.json is absent
-> evaluator_member_v1 is not evaluated

E = 1
-> evaluator.json is the exact projection of authenticated evaluator row 1
   + the bounded parsed PlannerEvaluationResult
-> evaluator_member_ceiling(1) =
     evaluator-member framing
     + evaluator_row_projection_ceiling(1)
     + parsed_evaluation_result_ceiling
```

The projection includes the duplicated canonical request, adapter request,
raw response or error, assistant/tool projection, usage, metadata,
termination, quiescence, recommendation, and bounded semantic evidence already
retained by the existing member contract. Its request/response branches must
equal the authenticated ledger row byte-for-byte. Its parsed result must be
derived through the existing evaluator parser and bounded by the closed report
schema and generation limits. `E` may only be `0` or `1`; presence must equal
`E == 1`, and a missing, extra, or unexpected evaluator member form fails.

The `max(response, error)` branch is legal only after parsed evidence proves:

- exactly one branch is populated;
- its outcome/exception/termination fields agree;
- the opposite branch and incompatible projections are `null`;
- the branch is one of the existing closed ledger outcomes.

Both populated, contradictory termination, partial branch evidence, or an
unknown branch fails.

### 7.5 Aggregate equations

For authenticated Planner count `P` and evaluator count `E`:

```text
call_ledger_ceiling(P, E) =
  ledger framing
  + sum(i=1..P, planner_row_ceiling(i))
  + sum(j=1..E, evaluator_row_ceiling(j))
  + exact separator bytes
```

```text
planner_session_ceiling(P) =
  session framing
  + sum(i=1..P,
      planner_row_ceiling(i)
      + turn_summary_ceiling(i)
    )
  + exact separator bytes
```

The helper never multiplies one generic row maximum across all turns.

### 7.6 Two-stage parsing

Member parsing cannot trust an authored call count. It therefore proceeds in
two stages:

```text
pre-parse ceiling:
  derive with P=6, E=1

strictly parse call-ledger.json under its absolute ceiling

closed structural validation of call rows:
  exact fields, indexes, roles, ordering, branch exclusivity,
  and per-call terminal/quiescent evidence

issue closure-owned VerifiedResolutionCallShape:
  authenticated P/E
  ordered role/index projection
  response/error branch projection
  terminal/quiescence projection

strictly parse planner-session.json and evaluator.json under their
maximum-cardinality absolute ceilings using that exact carrier

post-parse ceiling:
  derive with carrier-authenticated P/E

require raw member size <= post-parse ceiling
require member shape/count projections == carrier projections
```

The raw call-shape issuer is closure-local. The only public producer accepts
the strictly parsed ledger and completes the closed structural validation
before issuing `VerifiedResolutionCallShape`. Plain integers, dictionaries,
caller-constructed instances, copied/replaced carriers, or carriers from a
different profile/instrument snapshot are rejected at consumption.

`planner-session.json` authored `call_count` never grants budget. It is checked
only after the call ledger carrier establishes `P`. `evaluator.json` cannot
author `E` or its branch shape. Full request, transcript, gate, provider
provenance, derived attempt-terminal state, and the prohibition on calls after
an attempt terminal remain the later governed-resolution artifact verifier's
responsibility. Per-call `terminal` means owned adapter execution completed; it
is not an attempt-terminal claim. The carrier proves only the structural facts
needed to select and tighten parsing budgets without circular trust.

## 8. Future writer and verifier integration

### 8.1 Preflight and initial request

"Provider dispatch" in this design means governed-resolution Planner or
evaluator dispatch, not the unchanged readiness canary.

Future preflight construction validates the exact initial Planner request
against the profile. Execution reconstructs and rechecks it before the first
Planner dispatch.

The future instrument manifest adds an archive-resource section containing:

- exact profile raw SHA-256 and profile fingerprint;
- profile ID and checkpoint schema;
- exact member-role map and map fingerprint;
- formula IDs and constants fingerprint;
- canonical serializer/escaping/base64 contract identity;
- evaluator-member projection, report-schema/parser, generation-limit, and
  parsed-result-ceiling fingerprint;
- pure profile/parser/budget-helper source fingerprint;
- writer and public-verifier source fingerprints;
- reviewed future implementation commit.

These fields constructively change the future instrument, attempt, and
preflight identities. The original `e81b12cc` instrument did not contain the
profile and is never described as if it did.

### 8.2 Pre-dispatch checks

Before each Planner/evaluator dispatch:

```text
build canonical provider-call request
-> derive exact adapter request
-> apply role/turn field ceilings
-> persist and reread exact bytes
-> write dispatch_started
-> enter adapter
```

If the initial Planner request exceeds its bound, execution refuses before any
governed-resolution dispatch and does not consume the attempt. If a
response-dependent later request exceeds its bound after an earlier dispatch,
the attempt is already consumed and becomes `post_dispatch_unsealed`.

### 8.3 Post-dispatch capture precedes admission

Returned response/error bytes are captured exactly before archive-profile
admission. An oversized response or error is retained as opaque staging
evidence with exact size and hash, then yields `post_dispatch_unsealed`.

A bounds failure must never discard, truncate, summarize, or overwrite
already-captured evidence.

The writer validates retained fields before aggregate serialization, writes the
candidate no-clobber, rereads every member, applies profile-aware parsing, and
then runs the existing provenance/classification verifier.

### 8.4 Public checkpoint verification

The public verifier:

1. captures the same non-following physical snapshot;
2. selects the one profile from the known checkpoint schema and member path;
3. proves profile/member-map/instrument identity;
4. applies maximum-cardinality pre-parse ceilings;
5. authenticates the complete call ledger;
6. applies actual-count post-parse ceilings and field bounds;
7. runs the unchanged provenance, mechanical, isolation, evaluator, and
   classification reconstruction;
8. issues the existing checkpoint carrier only if every existing and new
   equation passes.

Nested `canonical_request_json` values use the role/turn evidence parser
ceiling. They do not fall back to the 1 MiB default archive parser.

## 9. Failure semantics

| Failure locus | Result |
|---|---|
| Invalid/missing profile during future preflight | Pre-contact refusal; no attempt consumed |
| First Planner request over bound | Pre-dispatch refusal; no attempt consumed |
| Later request over bound after prior dispatch | Retained `post_dispatch_unsealed` |
| Returned response/error over bound | Capture exact opaque bytes, then retained `post_dispatch_unsealed` |
| Contradictory/partial response-error branch | Retained `post_dispatch_unsealed` |
| Aggregate member over authenticated-count ceiling | Retained `post_dispatch_unsealed` |
| Public archive profile/resource mismatch | Verification refusal; no carrier |
| Forensic source movement or reconstruction failure | No forensic report |

No profile failure creates `probe_inconclusive`, changes a Planner result, or
authorizes retry.

## 10. Historical-preflight compatibility

### 10.1 Temporal boundary

The two preflight verifiers have distinct meanings:

```text
verify_resolution_preflight()
  -> current operational eligibility

verify_historical_resolution_preflight_forensics()
  -> historical provenance of one already consumed attempt
```

The compatibility verifier is a separate function/module, never a mode flag on
the operational verifier.

### 10.2 Closed historical scope

It accepts only:

- the pinned `e81b12cc` governed-resolution preflight schema and instrument
  lineage;
- the independently supplied expected preflight fingerprint
  `sha256:897337de3d20e126a143576de707ec3b1377033eab49465ac38d793afd97a856`;
- the exact observed attempt/destination/staging bindings;
- an exact historical-object manifest naming required Git blobs.

It reads and hashes Git blobs from `e81b12cc` without importing or executing
historical Python. It reconstructs the historical source inputs, instrument
manifest, initial request, instrument fingerprint, attempt fingerprint,
preflight record, checksums, and preflight fingerprint.

Archive checksum agreement alone is insufficient.

The resulting closure-issued carrier is accepted only by the forensic writer.
Execution, reservation, sealing, ready-proof, retry, evaluator, and compiler
APIs reject it by exact type.

The compatibility verifier source fingerprint and the exact historical-object
manifest enter the repaired forensic instrument identity.

## 11. Forensic derivative

### 11.1 Source snapshot

The forensic source consists of:

- independently verified physical historical preflight;
- exact `post_dispatch_unsealed.json` bytes and fingerprint;
- exact `.archive-candidate` member bytes;
- candidate checksum ledger and physical membership;
- observed staging and reserved-destination paths/state;
- observed attempt/instrument identities;
- required `e81b12cc` Git blobs.

All paths are absolute canonical Windows paths. Reparse components, unexpected
members, non-files, path escapes, source movement, or destination presence
outside the pinned observation fail.

The loader captures before/after non-following identities and bytes for the
preflight, marker, candidate, staging state, and reserved destination state. Any
movement issues no report.

### 11.2 Reconstruction

The forensic verifier never accepts an authored aggregate as its causal root.
It uses three explicit layers:

```text
retained runtime roots
-> verified causal call projection
-> mechanically reconstructed candidate and isolation result

authored aggregate
-> preserved operational accounting
-> explicitly unverified

combined forensic report
-> no official checkpoint or scientific outcome
```

The verified call projection excludes only the closed authored paths
`calls[*].elapsed_ms`, `calls[*].usage.cost_usd`, and their duplicated
Planner-session projections. Every other runtime-derived field must equal the
authored ledger exactly. A closure-issued `VerifiedRuntimeCallProjection`
carries that comparison. The authored timing and cost values and hashes remain
preserved, but are not inputs to causal reconstruction.

From that projection the verifier reconstructs:

```text
six physical dispatches and exact retained requests/raw responses
-> exact assistant projections from raw responses
-> exact Planner submissions
-> exact mechanical gates and feedback transcript
-> final mechanically accepted recipe
-> exact isolation-policy evaluation
-> classification equations
```

For the pinned specimen, reconstruction must derive, not assume:

```text
mechanically accepted
isolation rejected
probe_resolution_isolation_failure
```

Authored `checkpoint-gate.json`, `isolation.json`, and `classification.json` are
then compared to independently reconstructed values. They cannot establish
those values.

The classification is explicitly a **candidate-level deterministic
projection**, not an official scientific checkpoint outcome. Because elapsed
timing and exact cost cannot be recovered causally from this specimen, the
report must state that full controller conformance, exact timing, cost
accounting, and cost-stop compliance are not verified. No invented timing,
zero cost, reconstructed price, or full-ledger verifier input is permitted.

This separates the epistemic plane (authority, model evidence, mechanical and
isolation gates, and candidate-level classification) from the operational
plane (elapsed time, cost, rate limits, and infrastructure availability).
Operational controls govern whether observation continues; causally derived
evidence and deterministic semantic rules govern what the candidate means.

Future governed-resolution attempts must persist terminal per-call evidence
that binds elapsed timing and either (a) exact cost together with the frozen
pricing/calculator identity and inputs, or (b) immutable inputs sufficient to
recompute the exact cost-stop decision. This forward rule does not retrofit or
estimate the absent historical provenance.

### 11.3 Report schema and membership

The report schema is:

```text
rook.lm9b_p.governed_resolution_forensic_report:v1
```

Its closed members are:

| Path | Role |
|---|---|
| `record.json` | report identity and canonical destination |
| `observed-instrument.json` | original commit/preflight/instrument/attempt/staging/marker bindings |
| `forensic-instrument.json` | repaired commit, profile, helper, compatibility, reconstruction, report contracts |
| `source-snapshot.json` | exact physical member sizes/hashes and movement proof |
| `reconstruction.json` | reconstructed calls, gate, isolation, provisional classification, comparison fingerprints |
| `boundary.json` | original state and explicit non-claims |
| `checksums.json` | closed member checksum aggregate |

`boundary.json` must state:

```text
original_attempt_state: post_dispatch_unsealed
official_scientific_checkpoint: absent
reconstructed_candidate_classification: probe_resolution_isolation_failure
ready_proof: prohibited
compiler_eligibility: false
provider_contact_by_forensic_instrument: false
```

The report contains no policy recommendation and no automatic retry or next
attempt identity.

### 11.4 Observed and forensic identities

The report preserves two independent identity domains.

Observed instrument identity binds:

- original `e81b12cc` commit;
- preflight, instrument, attempt, destination, and staging identities;
- exact marker bytes/fingerprint;
- exact candidate member bytes and checksum closure.

Forensic instrument identity binds:

- reviewed repair commit;
- exact profile bytes/fingerprint;
- compatibility verifier and historical-object manifest;
- parser/budget helper and formula identities;
- reconstruction/classification contracts;
- physical snapshot contract;
- report schema, writer, public verifier, and publication equations.

The report records a destination-independent content fingerprint over exactly
the five substantive evidence members:

```text
observed-instrument.json
forensic-instrument.json
source-snapshot.json
reconstruction.json
boundary.json
```

It then writes `record.json` with a destination-bound report identity over:

```text
content fingerprint
+ canonical report destination
+ reviewed repair merge SHA
```

Finally, `checksums.json` covers exactly those five substantive members plus
`record.json`. It excludes itself. The content fingerprint excludes both
`record.json` and `checksums.json`; the report identity therefore has no
recursive checksum or identity dependency.

The public verifier requires its physical path to equal that canonical
destination, recomputes the five-member content fingerprint, reconstructs the
record identity, and verifies the six-member checksum ledger independently.

### 11.5 Publication and reconciliation

The post-merge report uses a new destination outside both the retained staging
and the reserved checkpoint destination. The destination is bound to the exact
repair merge SHA and must not exist before publication. Publication and public
verification independently require the exact reviewed base and feature-head
SHAs, then derive this ordered Git topology:

```text
repair merge SHA
-> exactly two parents
-> parent 1 == independently supplied reviewed base SHA
-> parent 2 == independently supplied reviewed feature-head SHA
```

The derived topology and its fingerprint enter the forensic instrument. A
clean feature HEAD can reconstruct the retained candidate read-only, but cannot
publish or publicly authenticate a report.

Publication is:

```text
write/reread/verify sibling report candidate
-> same-filesystem no-clobber atomic directory rename
-> public destination verification
```

After rename begins, the destination is immutable. Reconciliation never repairs
or marks it.

```text
destination verifies and candidate is absent
-> issue VerifiedResolutionForensicReport

destination absent and candidate remains
-> unpublished forensic evidence; no report carrier

every mixed, unverifiable, or ambiguous state
-> forensic publication indeterminate; no report carrier
```

"Candidate is absent" means non-following entry absence: `lexists(candidate)`
is false. A regular file, directory, symlink, reparse point, or entry appearing
during verification is mixed state. Candidate reservation is inside this total
publication state machine, so a reservation race also yields publication
indeterminate rather than escaping as an exception.

A reported write/rename/verification exception does not defeat a physically
verified destination. Conversely, unresolved ambiguity never issues a carrier.

The forensic carrier is a distinct exact type. It is structurally inadmissible
to checkpoint sealing, ready-proof issuance, or compiler continuation.

## 12. Identity closure

Future governed-resolution instruments bind the resource profile directly.
At minimum, `instrument_fingerprint` and preflight reconstruction include:

- raw profile SHA-256 and profile fingerprint;
- exact member map and map fingerprint;
- formula IDs and constants fingerprint;
- parser/helper contract ID and source fingerprint;
- canonical serializer/escaping/base64 identity;
- evaluator-member projection, report-schema/parser, generation-limit, and
  parsed-result-ceiling identity;
- checkpoint schema identity;
- writer/public-verifier source fingerprints;
- reviewed implementation commit.

Execution drift tests mutate each identity independently and require refusal
before governed-resolution dispatch.

The forensic instrument separately binds:

- historical compatibility verifier source;
- exact required `e81b12cc` Git-object manifest;
- physical snapshot algorithm;
- resource profile and helper;
- reconstruction functions;
- report schema/writer/verifier/publication equations;
- reviewed repair commit.

No field is accepted merely because it is checksummed and self-consistent.

## 13. Deterministic test strategy

### 13.1 Parser equivalence table

One parameterized corpus compares `parse_archive_json()` with the new parser
for inputs at or below 1 MiB:

- valid objects, arrays, scalars, finite floats, and Unicode;
- duplicate keys;
- invalid UTF-8 and UTF-8 BOM;
- invalid JSON;
- non-finite numbers and overflow float literals;
- overlong integer tokens;
- depth exhaustion;
- exact 1 MiB behavior.

Assertions compare identical parsed values or identical exception type and
stable rejection ID.

A separate boundary-divergence table covers 1 MiB plus one byte. The historical
parser must reject it under the unchanged default limit. The new parser must
then follow the structurally selected member formula: reject for
`recipe_member_v1` or an insufficient selected ceiling, and continue strict
parsing only for a known governed-resolution role whose admitted ceiling is
large enough. No equivalence claim applies above 1 MiB.

### 13.2 Profile-admission table

Fully reclosed mutations cover:

- wrong profile/checkpoint schema/fingerprint;
- missing, extra, duplicate, reordered, or changed member-role rows;
- unknown role or formula ID;
- changed call cardinality;
- changed fixed member ceiling;
- changed field bound, serializer, escape, or base64 constant;
- Python helper/profile drift;
- caller attempts to supply a numeric ceiling.

### 13.3 Indexed resource table

For every Planner turn `1..6` and evaluator call `1`, test:

- each retained field at exact bound and bound plus one;
- returned and error branch exclusivity;
- pre-parse maximum-cardinality admission;
- actual-count post-parse tightening;
- authored `call_count` substitutions;
- `E=0` exact no-evaluator form and `E=1` exact evaluator-row/result
  projection at their member ceilings;
- evaluator-member termination, quiescence, recommendation, evidence, or
  projection substitutions after full downstream checksum reclosure;
- plain `P/E`, caller-constructed, copied/replaced, cross-profile, and
  mutated `VerifiedResolutionCallShape` refusals;
- missing, duplicate, skipped, reordered, post-terminal, or unregistered calls;
- exact aggregate limit and aggregate limit plus one for ledger and session.

### 13.4 Future six-turn vertical witness

One fake-provider witness traverses the real future path:

```text
preflight profile admission
-> six Planner dispatch/capture rows
-> cumulative members above 1 MiB
-> mechanical acceptance or closed terminal outcome
-> profile-aware writer
-> atomic publication
-> public reconstruction
```

It proves future maximum-turn evidence seals without weakening the recipe
limit.

### 13.5 Overflow and retention table

Cover:

- initial-request overflow with zero governed-resolution dispatches;
- later request overflow after a prior dispatch;
- returned raw response at exact bound and bound plus one;
- provider raw error at exact bound and bound plus one;
- assistant, usage, and metadata bound mutations;
- successful opaque preservation before oversized-evidence refusal;
- write failure while preserving captured oversized evidence;
- aggregate serialization/reread/profile failures.

Every post-dispatch case proves retained exact bytes and
`post_dispatch_unsealed`, never truncation or `probe_inconclusive`.

### 13.6 Forensic provenance table

Use fully reclosed adversarial mutations of:

- preflight identity and bytes;
- historical Git blobs/manifest;
- marker bytes, attempt, or failure locus;
- staging/destination paths or state;
- candidate membership and checksum closure;
- raw response versus assistant projection;
- request versus dispatch marker;
- Planner call count/order/termination;
- mechanical gate, isolation, or classification claims;
- profile/helper/repaired-commit identities;
- reparse points, unexpected files/directories, or source movement.

The verifier must refuse even when every authored downstream checksum and
fingerprint is recomputed.

### 13.7 Publication/reconciliation table

Cover:

- successful no-clobber atomic publication;
- destination race before rename;
- reported rename exception after successful publication;
- transient destination verification failure followed by successful
  reconciliation;
- destination plus candidate mixed state;
- destination absent plus candidate retained;
- destination/staging evidence loss;
- cleanup or forensic-marker failure;
- every ordinary verification exception during reconciliation.

Only a physically verified destination with no remaining candidate issues the
forensic carrier.

Report-identity cases additionally mutate each of the five substantive members,
the destination-bound `record.json`, and the six-entry `checksums.json` ledger
with every downstream checksum reclosed. Public verification must reconstruct
the five-member content fingerprint and reject any circular, self-including,
missing, extra, or reordered checksum membership.

### 13.8 Exact retained specimen

Before PR completion, the exact retained staging crosses the full read-only
compatibility, profile, checksum, call-ledger, mechanical, isolation, and
classification reconstruction path at feature `HEAD`.

This witness requires:

- byte-for-byte before/after physical snapshot equality;
- destination remains absent;
- no report publication;
- no provider/readiness/compiler contact;
- reconstructed `probe_resolution_isolation_failure` recorded only as
  development verification output.

After merge, the exact merge-SHA forensic instrument repeats reconstruction and
publishes the new report to a fresh no-clobber destination bound to that merge
SHA.

## 14. Implementation and operational sequence

### 14.1 Reviewable implementation

Implementation must occur in a fresh isolated `codex/` branch/worktree from the
reviewed `origin/main` commit. It should proceed in this order:

1. profile contract and pure parser/budget helper;
2. under-limit parser equivalence and exact-limit tables;
3. future writer/public-verifier integration and identity binding;
4. overflow capture/retention paths;
5. historical-preflight compatibility verifier;
6. forensic reconstruction and report publication/verifier;
7. fake six-turn vertical witness;
8. exact retained-specimen read-only feature-HEAD witness;
9. full LM9B-P regression and PR review.

The new profile contract directory already has LF coverage. Any new raw-hashed
source must receive an explicit LF checkout rule and cross-checkout identity
test.

### 14.2 Post-merge no-contact operation

Only after independent review and merge:

1. create a clean detached checkout at the repair merge SHA;
2. independently supply and verify the exact reviewed base/head parent SHAs;
3. rerun all no-contact public reconstruction checks;
4. choose a fresh absolute forensic-report root/destination outside staging and
   the reserved checkpoint destination;
5. bind that destination, merge SHA, and reviewed topology into the report;
6. snapshot and reconstruct the exact retained candidate;
7. publish no-clobber and publicly verify the forensic report;
8. independently review the report identity and non-claims.

No readiness canary, Planner, evaluator, compiler, Rhino, Grasshopper, or
mutation contact is part of this operation.

## 15. Success criteria and supported claims

This slice succeeds when:

- future governed-resolution checkpoint members use the reviewed resource
  profile while recipe/default archive parsers remain unchanged;
- maximum-turn cumulative evidence above 1 MiB can seal and publicly verify;
- every retained evidence field and aggregate is constructively bounded;
- profile identity constructively changes future instrument/preflight identity;
- the exact retained candidate reconstructs read-only without source movement;
- the post-merge forensic derivative publicly verifies under its repaired
  forensic instrument;
- the original staging and absent destination remain unchanged.

The supported scientific statement is limited to:

> The retained replacement evidence reconstructs a mechanically accepted
> successor recipe that failed the governed-resolution isolation gate because
> it added two task-envelope references to an inherited postcondition.

The forensic report does not establish that the original checkpoint sealed. It
does not change `post_dispatch_unsealed`, authorize retry, issue readiness or a
ready proof, establish evaluator fidelity, or create compiler eligibility.

## 16. Stop condition

Stop after the repaired merge-SHA forensic report is published and
independently verified. Do not run another model attempt, redesign Planner
guidance, relax isolation, or begin compiler continuation as part of this
slice.
