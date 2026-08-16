# Acceptance Reviewer Phase B Qualification Design

**Date:** 2026-08-15

**Status:** Phase B-only qualification design

**Repository baseline:** `d353e718f1a0aeb370922b92f4997aa47d85e632`

**Product changes:** None

## Purpose

Phase A qualified a closed deterministic compiler boundary. Phase B tests only
whether one fixed Reviewer configuration adds useful residual semantic
judgment after that compiler has admitted an artifact.

The qualification uses six fresh Reviewer sessions:

```text
one coherent control
+ one requirement omission
+ one invented assumption
+ one material weakening
+ one authority misrouting
+ one hidden unresolved risk
```

Every artifact must compile under the exact Phase A V4 manifest and compiler
immediately before contact. Mechanical defects never reach the Reviewer.

Phase B may qualify sensitivity and restraint only for this frozen corpus,
prompt, model, and configuration. It does not qualify general semantic
competence, runtime evaluation, the production router, or product readiness.

## Exclusions

This slice adds no production schema, router, prompt, model profile, evidence
operation, Rook tool, Rhino or Grasshopper behavior, or persistent corpus. It
performs no Constructor call, repair, continuation, retry, fallback, prompt
tuning, live host contact, or mutation.

No result, including six favorable judgments, automatically authorizes
production implementation.

## Frozen Phase A Authority

The Phase B public bundle contains exact copies of the V4:

- semantic manifest;
- contract schema;
- deterministic compiler;
- evidence vocabulary derived from the manifest's admitted role kinds, fields,
  operations, precision, error, and budget rules; and
- original point-row intent.

The manifest SHA-256 is:

```text
D80D10393BFA7250B217C8636739EF4287E3AFBBE6E3C6A63834D99D4D51B30C
```

The public residual-review authority contract also provides the frozen intent
decomposition:

| Requirement | Authoritative meaning |
|---|---|
| `R1` | Generate a row of points. |
| `R2` | The points lie along the X axis. |
| `R3` | Expose independently adjustable Start, Step, and Count controls. |
| `R4` | Every point has Y and Z fixed at zero. |

This registry lets findings cite requirement IDs even though the Phase A
contract schema does not contain requirement objects.

## Coherent Control

The human-reviewed control uses one compiler-valid point-row artifact. Its
claims, in this exact order, are:

| Index | Claim ID | Authority | Meaning |
|---:|---|---|---|
| 0 | `point_count_equals_count` | `deterministic_required` | Complete point count equals the Count control value. |
| 1 | `all_y_zero` | `deterministic_required` | Every retained point has Y equal to zero within `1e-9`. |
| 2 | `x_progression_matches_start_step` | `judgment_required` | Ordered X values follow Start plus index times Step. |
| 3 | `controls_are_independently_adjustable` | `judgment_required` | Start, Step, and Count are independently adjustable controls. |
| 4 | `all_z_zero` | `deterministic_required` | Every retained point has Z equal to zero within `1e-9`. |

The two judgment-required claims have null expressions. The control's
`intentSummary` explicitly says that the V4 vocabulary cannot mechanically
express indexed X progression or structural adjustability. Those limitations
are honest residuals, not defects requiring correction.

The control policy lists all five claim IDs as required. Its roles and every
deterministic expression use only the frozen V4 vocabulary.

## Closed Reviewer Category Ontology

The same category definitions are visible to the Reviewer and the adjudicator.
They are not specimen labels.

| Category | Exact ownership |
|---|---|
| `requirement_omission` | A material part of the authoritative intent has no admitted claim and is not honestly retained as a residual. |
| `invented_assumption` | The artifact adds a material constraint, fact, or decision not supported by the intent and not presented for the required external authority. |
| `material_weakening` | The artifact retains a requirement's identity but changes its threshold or meaning so materially weaker results can pass. |
| `authority_misrouting` | A claim is assigned to an authority that cannot truthfully establish it, changing who is allowed to decide or prove it. |
| `hidden_unresolved_risk` | The artifact presents a material relationship as covered although its expression or evidence cannot establish it, and the gap is not honestly disclosed. |

Category precedence is closed for this corpus:

1. Removing coverage is `requirement_omission`.
2. Adding a new unsupported constraint is `invented_assumption`.
3. Relaxing an admitted numeric or semantic threshold is
   `material_weakening`.
4. Assigning an otherwise identifiable claim to the wrong owner is
   `authority_misrouting`.
5. Substituting unrelated evidence while concealing the resulting gap is
   `hidden_unresolved_risk`.

Each mutation has exactly one independently reviewed primary category. No
aliases or additional acceptable categories may be added after contact. If
pre-contact independent review finds genuine category ambiguity, it must list
the complete acceptable category set in the sealed adjudication file before
contact or refuse the corpus.

The initial oracle uses a singleton acceptable-category set containing only
the table's primary category, and an empty `supportedAdditionalFindings` list,
for every mutation. The control has neither an acceptable defect category nor
a supported additional finding. Changing either set requires renewed
pre-contact review and resealing; it is forbidden after the first call.

## Six Blinded Cases

Public case IDs, filenames, `contractId` values, session labels, and execution
labels are opaque. The canonical IDs are `phaseb.c01` through `phaseb.c06`.
Nothing public maps an ID to `control`, a mutation class, or an expected result.

The private oracle owns this mapping:

| Case | Private meaning | Primary category | Affected IDs |
|---|---|---|---|
| `phaseb.c01` | coherent control | none | residual claims at indices 2 and 3 |
| `phaseb.c02` | remove Z-zero coverage | `requirement_omission` | `R4`, `all_z_zero` |
| `phaseb.c03` | add Count-equals-five constraint | `invented_assumption` | `R3`, `count_must_equal_five` |
| `phaseb.c04` | weaken Y tolerance from `1e-9` to `1.0` | `material_weakening` | `R4`, `all_y_zero` |
| `phaseb.c05` | route Z-zero to user authority | `authority_misrouting` | `R4`, `all_z_zero` |
| `phaseb.c06` | conceal indexed-X gap behind count equality | `hidden_unresolved_risk` | `R1`, `R3`, `x_progression_matches_start_step` |

The execution order is frozen before contact as:

```text
phaseb.c04
phaseb.c01
phaseb.c06
phaseb.c02
phaseb.c05
phaseb.c03
```

The Reviewer receives only the opaque case's artifact and ordinary shared
inputs. It never receives this mapping, mutation labels, expected findings,
Constructor reasoning, prior Reviewer results, or another case's context.

## Structural-Difference Custody

Before contact, a strict canonical-JSON differ compares every sibling with the
control and records every changed RFC 6901 JSON Pointer, old value, and new
value. Each sibling necessarily changes `/contractId`; that custody-only
difference is admitted for all five mutations.

The only additional admitted differences are:

| Case | Exact semantic pointer changes |
|---|---|
| `phaseb.c02` | remove `/claims/4`; remove `/policy/requiredClaimIds/4` |
| `phaseb.c03` | append `/claims/5`; append `/policy/requiredClaimIds/5` |
| `phaseb.c04` | replace `/claims/1/expression/expression/absoluteTolerance/value` |
| `phaseb.c05` | replace `/claims/4/authority`; replace `/claims/4/expression` |
| `phaseb.c06` | replace `/claims/2/authority`; replace `/claims/2/expression`; replace `/intentSummary` |

Multi-pointer changes are permitted only where one semantic mutation requires
closed internal consistency. Any unlisted difference refuses corpus freezing.
The structural-diff audit and the independent primary-category review are
sealed before contact.

## Mechanically Inaccessible Oracle

The public Reviewer bundle and private adjudication bundle are separate roots.
The Reviewer call is a direct provider request with no tool definitions,
filesystem, shell, network, Prime, Rook, or shared-session authority. The
private root is never named in a request, prompt, public manifest, session
label, artifact, or provider metadata.

The contact runner reads only the public bundle. A separate post-contact
auditor reads retained public evidence plus the private oracle. Tests must
prove that:

- request bytes contain no private path, case meaning, expected category,
  oracle digest, or expected affected-ID tuple;
- public names and ordering are opaque;
- the contact runner has no oracle input parameter or import; and
- adjudication cannot begin until the six retained prefixes are closed or the
  campaign stops for custody/runtime invalidation.

## Reviewer Input And Output

Every fresh session receives exactly:

1. the identical Reviewer system prompt;
2. the original intent and frozen requirement registry;
3. one compiler-accepted artifact and its SHA-256;
4. the exact shared semantic manifest and SHA-256;
5. the admitted evidence vocabulary;
6. the residual-review authority contract and closed category ontology; and
7. the identical closed response schema.

The response contains separate arrays:

```json
{
  "findings": [],
  "acknowledgedResiduals": [],
  "disposition": "adequate"
}
```

`findings` are defects requiring correction. Every finding has a closed
category, `material | non_material` severity, free-form statement and impact,
and requirement and claim ID citations. Exact wording is never scored.

`acknowledgedResiduals` are honestly disclosed limitations that do not require
correction. Each entry cites one claim ID and uses the closed classification
`honestly_disclosed`. Findings and acknowledged residuals cannot cite the same
claim in one response.

For the coherent control, a semantically attentive response must acknowledge:

```text
x_progression_matches_start_step
controls_are_independently_adjustable
```

Recognizing those residuals is not a finding and does not force a non-adequate
disposition.

## Fixed Model Configuration

All six calls use the same current, reverified local identity and these frozen
settings inherited from the prior Reviewer qualification:

```text
model                 qwen3.8:27b
reasoning             medium
stream                false
keep_alive            5m
seed                   2026081502
temperature            0.0
top_p                  0.9
num_ctx                32768
num_predict            8192
timeout per call       900 seconds
maximum response bytes 131072
retry limit            0
```

The request uses one system message and one user message. `tools` is absent.
Every case starts from a fresh no-shared-context session and makes exactly one
provider request. The current Ollama executable, tag manifest, content-addressed
digests, exact blob sizes, and blob presence are frozen and rechecked before
the first and each subsequent call.

## Per-Case Admission And Adjudication

Immediately before each provider request, the contact runner must:

1. rehash the complete public bundle;
2. reverify model/runtime identity;
3. strict-parse the artifact with duplicate-key and nonfinite refusal;
4. run the exact V4 schema and compiler;
5. require the frozen artifact hash and opaque execution order; and
6. prove no prior context or additional message is present.

Compiler refusal, public custody drift, model/runtime identity drift, or an
unclosed prior call prefix stops the campaign. Semantic misses do not. A
malformed or schema-invalid Reviewer response is retained as that case's
`incomplete` result and later cases still run unless it reveals shared
runtime/custody invalidation.

Control restraint is evaluated independently:

```text
material findings == 0
acknowledged residual claim IDs == exact declared residual set
unsupported additional findings == 0
```

Mutation sensitivity is evaluated independently for each mutation:

```text
at least one material finding
and finding category == predeclared primary or predeclared acceptable category
and citation intersects the sealed affected requirement/claim IDs
```

Every additional finding is compared with the pre-contact oracle. An
unsupported additional finding is a separate restraint failure even when the
intended defect is found. A missed defect and a false positive are never
collapsed into one outcome.

The six classifications are reported independently. There is no aggregate
score, weighted score, pass percentage, or threshold that can conceal a
control false positive or a mutation false negative.

## Evidence And Failure Custody

The public pre-contact manifest covers all shared inputs, six artifacts,
settings, model identity, compiler, schemas, prompts, case order, contact
runner, and tests. The private manifest separately covers the oracle,
structural-diff audit, primary-category review, and post-contact auditor.

For each call, retain:

- exact request bytes and SHA-256;
- exact HTTP status and response bytes;
- a parsed model artifact exactly when strict extraction and parsing succeed;
- an explicit parse or extraction failure record otherwise;
- closed-schema validation;
- prompt and generated token telemetry;
- provider duration;
- terminal outcome; and
- an append-only call-ledger event.

Evidence-prefix closure is first-class. A stop after any call preserves and
audits the completed prefix without fabricating missing responses. Post-contact
adjudication retains each case's sensitivity, restraint, residual recognition,
and unsupported-additional-finding outcomes plus the exact oracle hash used.

## Required No-Contact Tests

Before any model call, inert tests must causally prove:

- all six artifacts compile with the exact V4 manifest/compiler;
- the control and five mutations have only their reviewed structural diffs;
- all public case names and order are opaque;
- the contact runner cannot read or name the private oracle;
- request construction cannot leak expected categories or affected IDs;
- all six requests differ only in opaque case identity, artifact bytes, and
  artifact hash;
- prompt, model configuration, manifest, vocabulary, authority contract, and
  schema bytes are identical;
- each session contains exactly one system and one user message and no tools;
- control findings and residuals are adjudicated separately;
- exact-category sensitivity and affected-ID citation are both required;
- unsupported additional findings produce an independent restraint failure;
- malformed Reviewer output cannot stop later semantic cases;
- custody/runtime drift stops before the next request; and
- complete and incomplete evidence prefixes audit exactly.

One independent no-contact review must reproduce the tests, manifest hashes,
compiler admission, structural-diff audit, oracle isolation, and absence of
model/live evidence. Only then may one explicit authorization cover the six
ordered Reviewer calls.

## Bounded Conclusion

A favorable Phase B result supports only:

> Under the frozen Qwen3.8:27b Reviewer configuration, the Reviewer showed
> restraint on one coherent point-row contract and sensitivity to the five
> frozen residual semantic defect classes.

An unfavorable result is equally valid evidence. Neither outcome changes the
Phase A compiler result, triggers prompt tuning inside this qualification, or
decides whether a production acceptance router should be implemented.
