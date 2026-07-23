# LM9 Generic Task-Local Typed-Fact Carrier Design

- **Date:** 2026-07-23
- **Status:** Approved for implementation planning; no implementation or provider contact authorized
- **Main baseline:** `8a5013bd61b4954b92e4cb654da9cd99e61b551e`
- **Architecture accounting:** `923e653375e3d0fab77d8d1d77f8e23b10ee3514`
- **Scope:** One scientific-instrument prerequisite that proves an open task-local fact carrier over closed typed-value contracts before the governed-resolution Planner experiment

## 1. Purpose

The evaluator-only continuation established one faithful but blocked Planner
recipe. Five material values were absent from trusted task authority and remained
explicitly unresolved:

```text
box_footprint_x
box_footprint_y
grid_spacing
minimum_height
maximum_height
```

The next semantic intervention will add those values as explicit user facts in
a newly issued task envelope. The existing scenario-specific
`rook.lm9b_c.r01_task_payload:v1` cannot carry them without adding radial field
names to the permanent payload contract.

This prerequisite tests a more general hypothesis first:

> Existing task-envelope authority can carry schema-admitted task-local facts
> across the four registered forward variants through open semantic-key
> identities and closed typed-value shapes without a global semantic-key catalog
> or scenario-specific validation code.

This is a tactical change in work order, not a change to the governing
architecture:

```text
generic task-local typed-fact carrier
-> radial and unrelated deterministic witnesses
-> governed-resolution Planner revision
-> exact parent/successor isolation
-> unchanged downstream path only if ready
```

The governing invariant remains:

> Models propose artifacts and judge meaning. Deterministic authority decides
> what the system knows, what it may do, and whether it may advance.

## 2. Established evidence and source binding

The carrier design is grounded in these preserved identities:

| Evidence | Identity |
|---|---|
| Historical visibility attempt | `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-visibility-intervention` |
| Historical source-manifest SHA-256 | `sha256:ac7716b7d5a61e2e6359bc0e01e145d7d17e0871ff03d1d5329710541d274c90` |
| Exact blocked recipe raw SHA-256 | `sha256:5c5dba9def1ffc3002240f3154f02f36e60134019659d5e6a9d546b0317965af` |
| Blocked recipe fingerprint | `sha256:eb70994fa9ead99fbe75f6f25e81327045258389d46e91474cc5b581befc068a` |
| Evaluator-only derivative identity | `sha256:48bcdcb36fb3ccee49fe358335f577ffabcb83b0f74e9f84d96951d6b3950b94` |
| Evaluator result | `semantically_faithful` |
| Deterministic classification | `probe_candidate_blocked` |

The historical attempt remains permanently `probe_inconclusive`. The
derivative does not replace it. Neither archive may be changed by this work.

## 3. Scope and non-scope

### 3.1 In scope

- one generic forward task-payload contract with open task-local fact keys;
- one versioned semantic-value schema registry with closed schema documents;
- one sealed scientific JSON Schema profile;
- one pure shared typed-value helper under `scripts/`;
- exact task fact-to-binding bijection and fingerprint equations;
- proof-carrying external unit-context resolution;
- an outcome-neutral registry migration witness over the exact blocked recipe;
- one radial forward-envelope witness;
- one unrelated drawing-annotation envelope witness;
- adversarial deterministic negative coverage;
- a checksum-closed, no-contact post-merge qualification witness.

### 3.2 Out of scope

- any Planner, evaluator, compiler, readiness, Rhino, or Grasshopper call;
- the governed-resolution Planner revision itself;
- deterministic recipe patching or semantic repair;
- a generic clarification or resolution artifact;
- a deployed compatibility layer for historical fixture formats;
- LM9A `ValidationProgramContribution` work;
- product Planner integration;
- authoritative `valid`, `blocked`, or `compile_ready` reports;
- validation-kernel changes;
- global semantic-key vocabulary;
- policy defaults, selections, or assumption confirmation;
- product routing, UI, or user authentication integration.

## 4. Architecture boundary

The work separates three layers:

```text
durable contracts:
  registry identities and schema documents
  generic typed-fact payload schema
  validation and fingerprint equations
  experimental findings

disposable scientific machinery:
  shared pure typed-value validator under scripts/
  historical comparison adapter
  radial and annotation fixtures
  probe-local evidence and isolation gates

deferred product authority:
  LM9A ValidationProgramContribution
  product Planner integration
  authoritative valid/blocked/compile_ready reports
```

The scientific helper is evidence for a later production implementation. It is
not itself product authority. Product code must never import it. LM9A must later
adopt the reviewed durable contracts through a separately designed production
contribution and prove conformance against the same vectors.

## 5. Selected approach and rejected alternatives

### 5.1 Selected: registry-owned typed-value shapes

The generic task payload owns the open `facts` container and minimum typed-value
shell. The semantic-value registry owns type-specific closed schema documents.
One deterministic helper resolves and applies those documents for both recipe
typed values and forward task-envelope facts.

This keeps the distinctions exact:

```text
payload typed value = what was established
value binding       = who established it and where it is bound
registry document   = the admitted shape of that value
semantic key        = a task-local join identity
```

### 5.2 Rejected: payload-owned type union

Embedding type-specific `oneOf` definitions independently in task and recipe
schemas would create duplicate value contracts and drift risk. It would also
make every future value-shape change require coordinated copies.

### 5.3 Rejected: raw values plus parallel binding metadata

Leaving raw primitives in `facts` and putting unit and context material beside
authority metadata would separate the value from material parts of its
identity. It cannot satisfy the required complete typed-value fingerprint.

## 6. Contract identities

The forward contracts use these exact identities:

| Contract | Identity |
|---|---|
| Semantic-value registry schema | `rook.semantic_value_schema_registry:v2` |
| Semantic-value registry version | `rook.semantic_value_schemas:v2` |
| Forward task payload | `rook.planner_task_typed_facts_payload:v1` |
| Sealed schema profile | `rook.json_schema_profile:lm9_typed_fact_v1` |
| Scientific helper contract | `rook.lm9.semantic_typed_values:v1` |
| Qualification witness | `rook.lm9.typed_fact_carrier_qualification:v1` |

The task authority artifact remains `rook.planner_task_envelope:v1`. The
payload schema changes because the task envelope already delegates payload
shape to an exact registered schema and fingerprint. No new authority kind or
task-envelope artifact kind is introduced.

## 7. Versioned semantic-value registry

### 7.1 Closed registry shape

The registry has this closed top-level shape:

```yaml
schema: rook.semantic_value_schema_registry:v2
registry_id: semantic_value_schema_registry
registry_version: rook.semantic_value_schemas:v2
json_schema_dialect: https://json-schema.org/draft/2020-12/schema
schema_evaluator_profile: rook.json_schema_profile:lm9_typed_fact_v1
schema_evaluator_profile_fingerprint: sha256:...
entries: []
registry_fingerprint: sha256:...
```

Each entry is closed:

```yaml
schema_id: rook.semantic_string:v1
schema_fingerprint: sha256:...
schema_document: {}
```

Registry verification requires:

1. Exact top-level and entry shapes.
2. Entries sorted by `schema_id` using the ratified UTF-16 comparator.
3. Unique schema IDs and fingerprints.
4. `schema_document.$schema` equal to the exact Draft 2020-12 dialect.
5. `schema_document.$id` equal to `schema_id`.
6. Each schema fingerprint recomputed from the exact parsed schema document.
7. Profile admission of every document before any instance evaluation.
8. The registry fingerprint recomputed over the complete registry excluding
   only `registry_fingerprint`.

Unknown, duplicate, malformed, unadmitted, or fingerprint-mismatched entries
fail closed. Registry schemas establish value shape only. They neither grant
authority nor interpret semantic-key meaning.

The old registry bytes and fingerprint remain historical inputs. The new
registry is a separate versioned scientific-instrument input, not an in-place
rewrite.

## 8. Complete typed-value contracts

### 8.1 Common identity

A complete forward typed value contains:

```yaml
schema: rook.semantic_scalar:v1
value: "2"
unit: model_unit
unit_context_ref:
  kind: artifact_value
  artifact_id: environment_snapshot
  json_pointer: /document/unit_context
```

The complete typed-value fingerprint is:

```text
sha256(canonical_json(exact parsed typed-value object))
```

The fingerprint covers `schema`, exact value type and spelling, `unit`, and
`unit_context_ref`. It does not cover semantic key, authority kind, or
provenance. The enclosing artifact fingerprint binds the key-to-value and
authority association.

Canonical serialization never alters the parsed value. Noncanonical value
spellings are rejected rather than normalized.

### 8.2 Occurrence-specific presence

Registry documents own all type-specific constraints and remain closed.
Container schemas retain their occurrence-specific presence rules:

- forward task facts require all four fields explicitly;
- current assumption typed values retain their existing four-field requirement;
- current derived-fact typed values may retain their existing `schema` and
  `value`-only form;
- string, integer, and boolean registry documents require `schema` and `value`;
  if `unit` or `unit_context_ref` appears, it must be `null`;
- scalar registry documents require all four fields.

This preserves exact accepted recipe occurrences while making every forward
task fact complete.

### 8.3 Forward user-fact variants

The v2 registry entry set for this scientific instrument is exactly the four
schema IDs below. Environment unit-context authority remains on the separate
path defined in Section 13 and is not another registry-admitted task fact.

The four variants admitted for forward task-envelope user facts are:

| Schema | Value | Unit | Unit-context reference |
|---|---|---|---|
| `rook.semantic_string:v1` | JSON string | `null` | `null` |
| `rook.semantic_integer:v1` | safe JSON integer | `null` | `null` |
| `rook.semantic_boolean:v1` | JSON boolean | `null` | `null` |
| `rook.semantic_scalar:v1` | canonical decimal string | `model_unit` | required external `artifact_value` reference |

Safe integers lie in the inclusive range
`-9007199254740991..9007199254740991`. Boolean and integer validation use an
exact JSON type policy: `true` is not integer `1`.

The scalar value contract is:

```text
maxLength: 1024
pattern: ^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$
not:
  const: "-0"
```

It admits:

```text
0
2
-2
0.5
-0.5
2.5
```

It rejects negative zero, leading `+`, exponent notation, leading zeros,
missing integer or fractional parts, trailing fractional zeros, whitespace,
and every alternate spelling such as `"2.0"` or `"2.50"`.

The 1,024-character bound reuses LM9A's existing
`maximum_number_token_chars` value. It is a lexical and resource-safety bound,
not a claim that every downstream representation can execute every admitted
magnitude or precision. Later policy, compilation, and execution layers may
refuse more narrowly but may not round or rewrite.

`rook.semantic_unit_context:v1` is not a fifth forward user-fact variant. A
scalar schema validates only the reference shape. The referenced context value
is independently validated through the environment artifact's payload schema,
value binding, artifact identity, session, freshness, and fingerprint.

## 9. Generic forward task payload

The payload is a closed object whose sole member is `facts`:

```yaml
facts:
  some_task_local_key:
    schema: rook.semantic_string:v1
    value: some exact value
    unit: null
    unit_context_ref: null
```

The payload schema requires:

- exactly one top-level `facts` object;
- 1..256 fact properties;
- property names of length 1..245 matching the ratified machine-identifier
  grammar `^[a-z0-9]+(?:[._:-][a-z0-9]+)*$`;
- one closed minimum typed-value shell per property;
- all four typed-value fields explicitly present;
- no payload field outside `facts` and no typed-value shell field outside the
  four named fields.

The machine-key grammar excludes `/` and `~`. Therefore the exact pointer to a
fact is `/facts/<semantic_key>` without an RFC 6901 escape transformation.
Strict JSON parsing rejects duplicate fact property names before schema
validation.

Production-neutral contract sources never enumerate task-local keys. The schema
and deterministic helper compare identifiers but do not interpret their domain
meaning.

## 10. Task fact and authority-binding bijection

Every fact has exactly one binding, and every binding resolves exactly one fact.
No unbound value, extra binding, duplicate pointer, duplicate semantic key, or
duplicate binding ID is admitted.

For each fact key `K` and typed value `V`:

```text
binding.binding_id == "task-value." + K
binding.semantic_key == K
binding.json_pointer == "/facts/" + K
binding.value_schema == V.schema
binding.typed_value_fingerprint == sha256(canonical_json(V))
```

The semantic-key limit is 245 because the fixed `task-value.` prefix is 11
characters. The derived binding ID therefore remains within the ratified
256-character machine-identifier limit for every admitted key.

Bindings are sorted by `semantic_key` using the already-ratified UTF-16 ordering.

Authority remains binding-only:

```yaml
authority_kind: user_fact | task_fact
provenance:
  issuer_kind: trusted_ingress | deterministic_fixture
  issuer_id: ...
```

Authority kind and provenance are independently validated. They never appear
inside the typed value and never change its fingerprint.

The five clarified radial values must use `authority_kind: user_fact`. Retained
facts preserve their exact prior authority kind and provenance in the
representation-migration comparison.

## 11. Sealed scientific JSON Schema profile

### 11.1 Identity and ownership

```text
profile_id: rook.json_schema_profile:lm9_typed_fact_v1
dialect:    https://json-schema.org/draft/2020-12/schema
ownership:  scientific instrument only
```

The profile is not a validation-kernel extension and cannot issue LM9A
authority.

### 11.2 Exact keyword set

The profile permits exactly:

```text
$schema
$id
type
const
properties
required
additionalProperties
propertyNames
pattern
not
minProperties
maxProperties
minLength
maxLength
minimum
maximum
```

Every unlisted keyword fails admission before instance evaluation.

The profile explicitly forbids:

```text
$ref
$dynamicRef
$recursiveRef
$defs
definitions
$anchor
$dynamicAnchor
```

Remote or filesystem retrieval, custom formats, extension vocabularies,
defaults, conditional schemas, and all other composition machinery are absent.
`$schema` and `$id` serve only dialect and document identity.

The instrument composes schemas explicitly:

```text
payload shell validation
-> iterate facts
-> resolve schema discriminator through registry
-> validate each complete value against its self-contained schema document
```

### 11.3 Pattern allowlist

Only the two reviewed ASCII-compatible expressions are admitted:

1. the machine-identifier pattern from Section 9;
2. the scalar pattern from Section 8.3.

Any other pattern fails schema admission. `pattern` contributes ordinary JSON
nodes to `schema_nodes`; it creates no child-schema edge or synthetic expansion.

### 11.4 Resource manifest

| Resource | Limit |
|---|---:|
| Raw registry bytes | 4,194,304 |
| Raw instance-envelope bytes | 1,048,576 |
| Embedded schema-document canonical bytes | 65,536 |
| Schema depth | 32 |
| Schema nodes | 4,096 |
| Members/items in any schema collection | 256 |
| UTF-8 bytes in one schema string | 65,536 |
| Instance depth | 32 |
| Members/items in any instance collection | 256 |
| UTF-8 bytes in one instance string | 65,536 |
| Scalar characters | 1,024 |
| Bounded issues | 1,024 |
| Evaluation expansion units | 32,768 |
| Per-evaluation shape units | 2,000,000 |
| Aggregate envelope shape units | 16,000,000 |

The raw registry and raw instance-envelope byte limits are checked before
strict parsing. Embedded schema documents do not have independent original
source bytes. Their canonical byte size is checked after strict parsing and
before schema admission or evaluation. Canonical schema bytes are derived
evidence and are never described as original source bytes.

Any admission, budget, evaluator, or evidence failure is an instrument failure,
never partial validity.

### 11.5 Expansion and work accounting

Expansion uses LM9A's structural-reachability calculation, restricted to the
profile's finite schema tree. Child-schema edges are created for:

- each schema-valued `properties` member;
- schema-valued `additionalProperties`;
- `propertyNames`;
- `not`.

References and alternative combinators are forbidden. For every node in reverse
topological order:

```text
expansion(node) = max(1, sum(expansion(child)))
```

Arithmetic saturates at `32,769`. A root result above `32,768` fails admission.

Evaluation shape uses the landed LM9A metric:

```text
metric_id:
  rook.schema_evaluation_shape:max_schema_or_expansion_times_instance:v1

formula:
  max(schema_nodes, evaluation_expansion_units) * instance_nodes
```

Work is reserved before evaluator invocation. Per-evaluation or aggregate
exhaustion fails the instrument without issuing partial validity.

### 11.6 Evaluator identity

The profile identity binds:

- Draft 2020-12 metaschema identity and fingerprint;
- `jsonschema.validators.Draft202012Validator`;
- the exact `jsonschema` distribution version, currently `4.26.0` in the
  designated environment;
- the exact qualification interpreter's `sys.implementation` identity;
- the full Python version;
- exact JSON/Python type-checker policy, including boolean versus integer;
- structural admission and expansion-algorithm identities;
- no-format and no-reference policies;
- allowed and forbidden keywords;
- pattern allowlist;
- every limit and work formula;
- deterministic issue projection and ordering.

The `sys.implementation` projection contains its implementation name,
cache tag, complete implementation-version tuple, and hex version. The runtime
record also carries `sys.version_info` and the full `sys.version` string. These
values are evidence identities, not user-selectable labels.

The designated Rook environment currently reports Python `3.12.12`. The
qualification witness records the exact interpreter actually used rather than
assuming portability. Execution refuses when runtime identity differs from the
preflight or qualification identity. A Python 3.11 qualification would be a
different witness.

Issues sort by:

```text
instance JSON Pointer
schema JSON Pointer
failed keyword
bounded detail fingerprint
```

More than 1,024 issues is an instrument failure. No truncated issue set is
accepted as validation evidence.

## 12. Pure scientific helper

One neutral module, `scripts/lm9_semantic_typed_values.py`, owns only pure
scientific operations:

- verify the registry and schema-document fingerprints;
- admit schema documents under the exact sealed profile;
- resolve one discriminator to exactly one registry entry;
- validate an already-parsed typed value;
- serialize it canonically without altering it;
- derive its typed-value fingerprint;
- build and consume a proof-carrying unit-context index.

The module contains no:

- file or environment reads;
- mutation, repair, coercion, normalization, or default insertion;
- model, provider, report-policy, or product-routing behavior;
- semantic-key interpretation;
- radial or annotation names or values.

The helper may reuse existing canonical JSON and schema-evaluation primitives,
but the validation kernel is not modified. Product code must not import the
helper.

Its exact identity binds:

```text
contract ID
module-source SHA-256
profile fingerprint
registry fingerprint
payload-schema fingerprint
runtime and evaluator identities
reviewed commit
```

The preflight and qualification verifier independently recompute the module
source fingerprint from the reviewed checkout. A caller-authored helper
identity is not accepted as its own authority.

## 13. Proof-carrying unit-context authority

The helper never trusts an arbitrary mapping or a Boolean such as
`fresh: true`. A verified index derives constructively from:

```text
frozen environment artifact
+ registered and validated environment payload schema
+ validated environment value bindings
+ frozen task/environment session identities
+ evaluated_at
-> VerifiedUnitContextIndex
```

Construction verifies:

- environment artifact fingerprint;
- payload schema ID and fingerprint;
- exact payload-schema validation;
- environment session binding;
- trusted issuer identity;
- observation and expiry bounds at `evaluated_at`;
- binding uniqueness and pointer resolution;
- referenced `rook.semantic_unit_context:v1` schema;
- referenced value fingerprint.

The helper either builds the issued proof value itself or independently
reconstructs and compares it. It cannot accept an arbitrary dictionary in its
place.

A scalar reference then requires exactly one matching proof entry. The scalar
schema validates reference shape; the proof index establishes external
authority. No unit conversion occurs.

## 14. Historical source versus forward contract

There is no deployed legacy format and no permanent compatibility promise.
The correct terms are:

```text
sealed historical source format
generic typed-fact format
parent authority artifact
successor authority artifact
```

The sealed historical task envelope remains byte-for-byte unchanged and is
verified through its existing historical verifier and schema. It is outside the
forward carrier contract.

A probe-local, read-only comparison adapter reconstructs complete typed-value
views solely for migration evidence:

```text
historical_typed_value =
  reconstruct_exactly(historical_raw_value, historical_binding, historical_schema)

canonical_json(historical_typed_value)
==
canonical_json(successor_typed_value)
```

The adapter performs no default insertion, numeric coercion, unit conversion,
or semantic normalization. Unitless historical values reconstruct with exact
`unit: null` and `unit_context_ref: null` fields. Both reconstructed and
successor objects validate independently before their canonical bytes are
compared.

Therefore:

```text
"2" != "2.0"
"model_unit" != "millimeter"
2 != "2"
```

Comparison fingerprints may be retained as evidence, but verification compares
the canonical bytes themselves. The comparison adapter cannot emit a forward
task envelope or grant authority.

## 15. Mechanical migration and authority partitions

The instrument derives its partitions without knowing radial key names:

```text
parent_keys =
  semantic keys already established by parent task authority

successor_keys =
  semantic keys established by successor task authority

migration_keys = parent_keys

authority_delta_keys = successor_keys - parent_keys

required_delta_keys =
  parent unresolved-intent semantic keys
```

It requires:

```text
parent_keys subset successor_keys
authority_delta_keys == required_delta_keys
```

For every migration key, verification requires:

- exact canonical typed-value equality;
- exact registered value schema;
- exact authority kind;
- exact provenance;
- exact fact/binding coverage.

For every authority-delta key, verification requires:

- one matching parent unresolved-intent row;
- exact expected value schema;
- exact expected unit-context relationship;
- one successor fact and binding;
- `authority_kind: user_fact`;
- trusted-ingress or deterministic-fixture provenance;
- no assumption, policy value, receipt, derived value, or inferred value as a
  substitute.

The number five is only a radial fixture expectation. It is not present in
generic helper logic.

## 16. Deterministic witnesses

### 16.1 Outcome-neutral blocked-parent witness

The exact blocked recipe bytes are validated under the new registry instrument.
The witness requires:

- exact recipe bytes and fingerprints unchanged;
- the sealed historical task envelope verified by its existing path;
- the mechanical gate still `mechanically_accepted`;
- the same five explicit unresolved rows and blocker projection;
- the public derivative verifier still reconstructing
  `semantically_faithful`;
- the shared deterministic classifier still producing
  `probe_candidate_blocked`;
- no evaluator or provider call.

The registry and instrument identities move. The recipe meaning, bytes,
authority, and disposition do not.

The outcome-neutral migration suite also binds the existing accepted control
fixtures that contain assumption and derived-fact typed values. It proves their
current occurrence-specific field-presence rules remain accepted through the
same registry validator, including the two-field derived-value form. Those
controls establish representation compatibility; only the exact sealed parent
supports the unchanged blocked-disposition claim.

### 16.2 Radial forward-envelope witness

The radial forward envelope uses the generic carrier for all retained parent
facts and the five newly supplied facts. The frozen clarification data is:

| Semantic key | Schema | Value | Unit |
|---|---|---:|---|
| `box_footprint_x` | `rook.semantic_scalar:v1` | `"1"` | `model_unit` |
| `box_footprint_y` | `rook.semantic_scalar:v1` | `"1"` | `model_unit` |
| `grid_spacing` | `rook.semantic_scalar:v1` | `"2"` | `model_unit` |
| `minimum_height` | `rook.semantic_scalar:v1` | `"1"` | `model_unit` |
| `maximum_height` | `rook.semantic_scalar:v1` | `"10"` | `model_unit` |

Each scalar carries:

```yaml
unit_context_ref:
  kind: artifact_value
  artifact_id: environment_snapshot
  json_pointer: /document/unit_context
```

That context currently resolves `model_unit` to millimeters. The values remain
`model_unit` values; no conversion to the string `millimeter` occurs.

All five bindings use `authority_kind: user_fact`. Trusted ingress computes
their fingerprints. For this deterministic witness, `deterministic_fixture` may
stand in for the later trusted ingress while carrying no product-authority
claim.

Radial names and values appear only in fixture and test data.

### 16.3 Unrelated drawing-annotation witness

The unrelated envelope uses exactly the same payload schema, registry, loader,
validator, binding equations, fingerprinting, and unit-context proof path:

| Semantic key | Schema | Exact fixture value | Unit |
|---|---|---|---|
| `annotation_text` | `rook.semantic_string:v1` | `"revision_note"` | `null` |
| `annotation_count` | `rook.semantic_integer:v1` | `3` | `null` |
| `leaders_enabled` | `rook.semantic_boolean:v1` | `true` | `null` |
| `text_height` | `rook.semantic_scalar:v1` | `"2.5"` | `model_unit` |

Each fact has one `user_fact` binding. String, integer, and Boolean values carry
explicit `unit: null` and `unit_context_ref: null`. `text_height` uses the same
authenticated external unit-context mechanism as the radial scalars.

This witness exercises every typed-value variant admitted for forward
task-envelope user facts. It creates no recipe, policy, Planner request,
evaluator request, or model call.

## 17. Deterministic negative matrix

The test suite remains compact and parameterized.

### 17.1 Registry and profile mutations

- duplicate or unknown schema ID;
- missing, extra, malformed, or reordered registry field;
- schema-document, entry, profile, or registry fingerprint mismatch;
- wrong dialect or `$id`;
- unlisted keyword;
- forbidden reference or definition keyword;
- non-allowlisted pattern;
- remote retrieval or custom format attempt;
- schema byte, depth, node, expansion, or work-limit excess;
- evaluator/runtime/type-policy identity mismatch.

### 17.2 Typed-value mutations

- wrong JSON value type;
- Boolean supplied where integer is required;
- unsafe integer;
- scalar exponent, leading zero, negative zero, whitespace, missing component,
  or trailing fractional zero;
- scalar over 1,024 characters;
- missing required scalar field;
- inappropriate non-null unit fields on string, integer, or Boolean;
- scalar with missing, null, or wrong unit-context reference;
- extra typed-value field;
- unknown discriminator;
- canonical typed-value fingerprint mismatch.

### 17.3 Fact and binding mutations

- duplicate JSON fact property;
- invalid or overlength semantic key;
- missing or extra binding;
- duplicate binding ID, semantic key, or pointer;
- unsorted bindings;
- binding ID formula mismatch;
- noncanonical pointer or pointer mismatch;
- value-schema mismatch;
- invalid authority kind or provenance;
- unbound fact or binding;
- artifact fingerprint mismatch.

### 17.4 Unit-context mutations

- caller-authored dictionary in place of a proof value;
- wrong environment artifact or payload schema identity;
- stale, wrong-session, or wrong-issuer context;
- missing, duplicate, or wrong-schema environment binding;
- pointer or typed-value fingerprint mismatch.

### 17.5 Migration and genericity mutations

- changed retained value type or spelling;
- changed retained unit or unit-context reference;
- changed retained authority kind or provenance;
- removed parent fact;
- added authority key not present in parent unresolved intent;
- omitted required unresolved key;
- policy, assumption, derived value, or receipt used for a delta key;
- radial or annotation semantic keys appearing in the neutral carrier module or
  forward schema/contract sources, excluding fixtures;
- unrelated annotation witness requiring any key-specific branch.

Mutation tests reclose caller-authored outer fingerprints where applicable. A
self-consistent mutated story must still fail when it disagrees with code-owned
contracts or authoritative source evidence.

The unrelated witness is the primary constructive proof of domain neutrality.
The source scan is secondary defense.

## 18. Qualification witness and identity closure

After implementation review and merge, a clean worktree at the reviewed merge
SHA emits one no-contact qualification witness with schema:

```text
rook.lm9.typed_fact_carrier_qualification:v1
```

The witness binds:

- reviewed commit and clean-checkout state;
- exact helper contract and module-source SHA-256;
- exact runtime `sys.implementation` identity and full Python version;
- exact `jsonschema` distribution version and evaluator identity;
- profile value and fingerprint;
- registry bytes, entries, and fingerprint;
- generic payload schema and fingerprint;
- exact historical source and derivative identities;
- exact blocked recipe bytes and unchanged disposition;
- accepted assumption/derived-value control-fixture identities and unchanged
  outcomes;
- verified unit-context proof identity;
- radial and annotation fixture identities and results;
- migration and authority-delta partitions;
- complete required negative-case-set fingerprint and one result per case;
- absence of model, provider, readiness, evaluator, compiler, Rhino,
  Grasshopper, and product-authority activity;
- per-file checksums and aggregate witness identity.

The qualification runtime is the exact interpreter used by the post-merge
witness. The witness runner refuses if its actual runtime differs from its
preflight runtime identity. A qualification cannot be copied to another runtime
and treated as equivalent merely because its tests happen to pass.

The qualification verifier independently reconstructs the registry, schemas,
profile, helper source identity, unit-context proof, typed-value results,
migration partitions, and witness aggregate. Checksums alone never establish a
claim's provenance.

The development witness on a feature commit is review evidence only. The
post-merge witness is regenerated under the reviewed merge SHA and is the one
later governed-resolution preflight may bind.

## 19. Failure semantics and stop conditions

Every failure is pre-provider. Failure emits no repaired value, accepted
envelope, Planner request, readiness claim, or product-authority result.

Stop this slice if any implementation requires:

- radial or annotation key interpretation in neutral code;
- a global semantic-key registry;
- mutation of historical evidence;
- a permanent historical-format compatibility profile;
- normalization, coercion, default insertion, unit conversion, or semantic
  equivalence;
- an arbitrary caller-supplied authority index;
- validation-kernel or product-code modification;
- product import of the scientific helper;
- a model, provider, evaluator, compiler, or live runtime call;
- a claim of authoritative LM9A validity or compile readiness.

## 20. Acceptance criteria

The prerequisite is ready for independent review when deterministic evidence
proves:

1. Registry v2 and every schema document have exact recomputable identities.
2. The sealed profile admits only its fixed schemas and enforces every budget.
3. Recipe and forward task-envelope values use one shared type-specific
   validation path.
4. The exact blocked parent recipe remains byte-identical, mechanically
   accepted, and `probe_candidate_blocked` under the migrated instrument.
5. The historical task envelope and archives remain unchanged.
6. The radial forward envelope carries all retained authority plus exactly the
   mechanically derived unresolved-key delta.
7. The unrelated annotation envelope exercises all four forward user-fact
   variants through the same path.
8. Fact-to-binding coverage is bijective and canonically ordered.
9. Unit-context authority is constructively proven from frozen artifacts and
   attempt context.
10. Historical representation migration compares exact canonical bytes, while
    the authority delta is separately derived.
11. Every adversarial negative row fails closed, including after consistent
    outer-fingerprint reclosure.
12. Neutral carrier and forward contract sources contain no fixture semantic
    keys.
13. The helper, runtime, profile, registry, schema, commit, and witness
    identities are independently recomputable.
14. No provider or product-authority activity occurs.

## 21. Supported claim and non-claims

If the qualification passes, the supported claim is:

> The LM9 scientific instrument can carry schema-admitted task-local user and
> task facts across the four registered forward variants through one open-key,
> closed-value, authority-bound task-envelope contract, demonstrated by radial
> and unrelated fixtures without scenario branches, while preserving the exact
> blocked parent as immutable evidence.

It does not establish:

- governed Planner resolution;
- a faithful or ready successor recipe;
- authoritative LM9A validation;
- compiler transfer or execution;
- product integration;
- cross-runtime portability;
- general model reliability;
- any product compatibility obligation for historical fixture formats.

## 22. Ordered continuation

The required order after written-spec approval is:

1. Write and review a deterministic implementation plan for this prerequisite.
2. Implement and test the carrier without provider contact.
3. Independently review and merge it.
4. Regenerate and review the no-contact qualification witness at the merge SHA.
5. Resume governed-resolution brainstorming from the already locked decisions:
   immutable parent, successor task-envelope authority, one bounded Planner
   revision, complete successor recipe, and exact isolation gate.
6. Authorize no model contact until that separate design, implementation, merge,
   preflight, and explicit authorization sequence completes.
7. After the governed-resolution observation, stop expanding the probe system
   and design the LM9A semantic contribution separately.
