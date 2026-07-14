# LM9A Planner Graph Recipe Design

Status: design draft for review

Date: 2026-07-13

## 1. Purpose

LM9A defines the first generic Planner-authored semantic contract for graph-
building tasks:

```text
rook.planner_graph_recipe:v1
```

The controlled claim is:

> A graph-building user intent can be represented as a validated,
> Planner-authored semantic contract without exposing execution mechanics or
> requiring the Planner or a bounded worker to author `gh_edit`.

LM9A proves the artifact and deterministic validation boundary only. It does
not call a Planner model, compile a recipe, create worker requests, execute
tools, or run Rhino or Grasshopper.

The architectural chain constrained by this design is:

```text
mechanical ingress
-> Planner-authored semantic contract
-> deterministic recipe validation
-> bounded intelligent compile
-> deterministic compile-output structural validation
-> independent semantic evaluation
-> trusted semantic-review receipt issuance
-> deterministic executable-IR authorization validation
-> mechanical execution
-> authoritative runtime verification
```

Only the first three stages through deterministic recipe validation are LM9A
scope. Implementation is deliberately split into the generic kernel defined by
`2026-07-13-lm9a-validation-kernel-design.md` and the semantic extension defined
by this document.

## 2. Course Correction And Architectural Grounding

LM9A follows the compile/run split grounded in the local OpenProse source at
`D:\prose` and the Rook architecture notes. The important correction is:

```text
Not:
  Planner-authored recipe
  -> deterministic compiler
  -> deterministic runtime

Instead:
  Planner-authored semantic contract
  -> bounded intelligent compile
  -> deterministic validation of compiled IR
  -> mechanical runtime
  -> authoritative verification
```

The compiler program is fixed and constrained, but compile steps may use model
judgment to select representation, resolve semantic relationships, construct
topology, or author bounded implementation artifacts. Compile delegates receive
narrower context and narrower output schemas than the Planner. Their output is
inert until deterministic validation accepts it.

Semantic clauses are authoritative. Typed backing is their machine-checkable
projection at material boundaries, not a competing source of truth and not an
excuse to build a universal domain ontology.

The recipe is above executable workflow contracts. It may describe a task with
no worker at all, so it does not extend or inherit the worker-specific
`PlannerWorkerContractRequest:v1` shape.

## 3. Scope Boundary

### 3.1 Implemented By LM9A

LM9A-Semantics implements or specifies for deterministic implementation:

- `rook.planner_graph_recipe:v1`;
- `rook.planner_graph_recipe_validation_report:v1`;
- one fixed LM9A semantic contribution sealed into the validation program;
- authority and provenance validation;
- deterministic derived-fact validation;
- assumption authorization and confirmation binding validation;
- structural clause, projection, shape, capability, and worker-slot validation;
- independent derivation of `valid` and `compile_ready`;
- generic, versioned vocabularies used by the recipe validator;
- deterministic fixture companion artifacts;
- a paired ready/unresolved proof fixture;
- one structurally different orthogonal control fixture;
- negative and anti-overfitting proof targets.

LM9A-Kernel separately owns raw byte ingress, the fixed kernel budget, owned
immutable JSON values, sealed-program composition, the restricted schema
evaluator, typed phase execution, issue authorization, canonical JSON
primitives, and the non-circular report seal. This spec may constrain their
semantic use but must not reimplement them.

### 3.2 Future Architecture Constrained But Not Implemented

LM9A constrains, but does not implement:

- bounded intelligent compilation;
- compile delegate or worker invocation;
- compiled topology, tool, verifier, or `gh_edit` IR;
- compile-output structural validation;
- semantic review input bundles, evaluator reports, or trusted receipts;
- executable-IR authorization;
- execution, mutation, readiness choreography, or runtime verification;
- boot-skill routing or task-envelope ingress implementation.

The future contracts in this document prevent later slices from crossing the
authority boundary. They are not LM9A deliverables.

### 3.3 Hard Anti-Goals

LM9A has:

- no Planner model;
- no worker model;
- no live Rhino or Grasshopper;
- no `gh_edit`;
- no compiler implementation;
- no concrete C# generator or Grasshopper representation choice;
- no component GUIDs, object GUIDs, short IDs, temporary IDs, epochs, wiring,
  connection strings, batches, or tool calls;
- no router;
- no model panel;
- no change to LM5, LM6, LM7, or LM8 worker protocols;
- no expansion of `PlannerWorkerContractRequest:v1`;
- no expansion of `RookWorkflowContract` or `TaskSpec`;
- no live run in the spec or implementation PR.

### 3.4 Implementation Sequence And Program Composition

There is no executable combined LM9A plan. The implementation sequence is:

```text
review LM9A-Kernel design
-> write and execute a kernel-only implementation plan
-> merge the generic kernel
-> write and execute an LM9A-Semantics implementation plan
-> run the offline semantic fixtures
```

LM9A-Semantics contributes recipe schemas, exact phase specifications, trusted
runner bindings, immutable export validators, issue codes, and one report
projection to the trusted composition builder. The builder combines that
contribution with the kernel and returns one
`SealedValidationProgram`. The contribution cannot validate artifacts, remain
open after sealing, or mutate a running program.

The sealed program manifest fingerprints the budget, parser and canonicalizer,
schema-evaluator profile, every schema and phase, exact named dataflow, runner
source identities, issue vocabulary, export types, report projection, and
runtime dependencies. Validation accepts that sealed program only. No mutable
registry, plugin lookup, or monkeypatch is a second source of validation
authority.

LM9A-Semantics may not implement its own parser, budget ledger, scheduler,
canonicalizer, schema evaluator, issue engine, or report seal.

The managed-readiness migration for future `gh_edit` execution remains a later
prerequisite and does not block LM9A.

## 4. Artifact Boundary And Data Flow

LM9A introduces two sibling schemas:

```text
rook.planner_graph_recipe:v1
rook.planner_graph_recipe_validation_report:v1
```

The recipe is Planner output and compiler input. The report is deterministic
validator output. Neither artifact contains compiled operations.

```text
untrusted Planner-authored raw recipe bytes
+ trusted host/ingress-assembled task envelope
+ trusted host/ingress-assembled authority companions
+ trusted host/ingress-assembled validation-context companions
+ sealed LM9A validation program
-> validation invocation preflight
-> recipe validator, only when preflight succeeds
-> validation report
```

A preflight failure does not enter the artifact flow above. It returns a typed
in-process control result to the mechanical caller and no
`rook.planner_graph_recipe_validation_report:v1` exists for that invocation.

When later compilation exists, its output receives a separate fingerprint that
links to the recipe fingerprint. A compiled fingerprint never replaces or
redefines semantic recipe identity.

The boot skill or task-envelope hook remains the mandatory mechanical ingress
gate. LM9A consumes a deterministic task envelope; boot routing is outside this
slice.

### 4.1 Closed Validation Bundle

Validation is invoked internally with exact untrusted raw recipe bytes plus one
trusted-host-issued carrier containing exact raw bytes for a closed companion
bundle:

```text
validate_planner_graph_recipe(
  raw_recipe_bytes: bytes,
  trusted_validation_bundle: TrustedValidationBundleInput,
)
```

```yaml
schema: rook.planner_graph_recipe_validation_bundle:v1

task_envelope: {}
authority_artifacts: []

validation_context:
  evaluated_at: ...
  trusted_clock_source: ...
  task_session_id: ...
  environment_session_id: null
  capability_registry_session_id: ...
  environment_snapshots: []
  policy_registries: []
  payload_schema_registry: {}
  capability_registry: {}
  vocabularies:
    semantic_authority_codes: {}
    semantic_capability_codes: {}
    worker_slot_codes: {}
    semantic_materiality_codes: {}
    semantic_value_schemas: {}
```

The recipe bytes and `TrustedValidationBundleInput.raw_bytes` are exact built-in
`bytes`; no caller-owned `Mapping` or parsed Python object is accepted. The
carrier is a transitively immutable kernel type issued only by trusted ingress
or deterministic fixture assembly. It binds the exact sealed profile defined by
the kernel spec:

```yaml
schema: rook.trusted_bundle_assembler_profile:v1
profile_id: ...
assembler_kind: trusted_host_ingress | deterministic_fixture
assembler_id: ...
assembler_version: ...
implementation_fingerprint: sha256:...
permitted_program_ids:
  - lm9a.planner_graph_recipe:v1
permitted_clock_sources:
  - trusted_system_clock | deterministic_fixture
profile_fingerprint: sha256:...
```

The fixed kernel host path seals this content-addressed profile and only that
sealed profile can issue a carrier through its opaque in-process capability.
There is no mutable assembler registry and no profile lookup named by bundle
JSON. A serialized profile or matching fingerprint alone has no authority.
Preflight verifies the issuer binding, exact profile fingerprint, permitted
program ID, and permitted clock source.

The profile fields are not parsed from the bundle and cannot be self-asserted by
the Planner or a future endpoint client. The trusted application supplies the
already sealed LM9A program as a separate invocation authority. A future public
endpoint accepts an untrusted task/recipe request and builds the validation
bundle internally from authenticated sessions, trusted registries, policy, and
receipts; it never forwards client-selected bundle bytes into this carrier.

Both underlying byte artifacts still receive identical hostile-input defenses.
Before scanning, copying, or hashing either, the kernel checks both lengths
against `rook.validation_budget:lm9a_v1`. If either is over limit, invocation
stops and neither raw hash is claimed. Admitted inputs are copied, hashed, and
bounded-parsed into owned transitively immutable values. Trust in the assembler
authorizes the bundle's role as authority context; it does not assert that its
contents are well formed, fresh, mutually consistent, or schema valid. The
complete bundle and every companion payload are supplied in full, not by
excerpt.

LM9A tests use one sealed `deterministic_fixture` assembler profile whose
profile and implementation fingerprints are fixed and campaign-bound. It emits
the same closed bundle schema and passes companions through the same production
authority-resolution and validation path. It has no shortcut for manufacturing
a valid companion, confirmation, policy match, or session result.

The report binds both the exact raw bundle hash and its canonical owned-value
fingerprint:

```text
validation_bundle_input_payload_sha256
validation_bundle_fingerprint
```

Before a report may be attempted, the owned bundle must contain this minimal
report-constructability envelope:

```text
/task_envelope                                      object
/authority_artifacts                                array
/validation_context                                 object
/validation_context/environment_snapshots           array
/validation_context/policy_registries                array
/validation_context/payload_schema_registry          object
/validation_context/capability_registry              object
/validation_context/vocabularies                     object
/validation_context/vocabularies/semantic_authority_codes     object
/validation_context/vocabularies/semantic_capability_codes    object
/validation_context/vocabularies/worker_slot_codes             object
/validation_context/vocabularies/semantic_materiality_codes    object
/validation_context/vocabularies/semantic_value_schemas        object
```

These are descriptor shells, not claims that their contents are valid. Their
fixed positions provide enough stable discriminator information to construct
`source_task`, both singleton registry descriptors, and all required vocabulary
descriptors with nullable evidence and failed/not-evaluated statuses. Missing
or wrong-container shells are invocation failures. Missing fields, unknown
fields, bad fingerprints, malformed payloads, and other defects inside present
shells remain `companion_artifacts` evidence.

Every recipe-declared authority artifact matches exactly one full companion by
`artifact_id`, schema, and fingerprint. Missing, duplicate, undeclared, or
fingerprint-mismatched recipe-bound companions invalidate validation context.
Validation-context artifacts occur only in the named validation-context fields;
they cannot be inserted into `authority_artifacts` to move recipe identity.
Artifact IDs are unique across recipe-bound and validation-context companions;
the same payload cannot be supplied in both roles.

The trusted task, environment, and capability-registry session IDs in
`validation_context` are the comparison authority for companion session checks.
Companion artifacts cannot declare themselves current merely by repeating their
own session IDs.

All companion schemas below are closed. A companion's fingerprint covers its
canonical payload excluding only its own fingerprint field.

### 4.2 Task Envelope

The minimal task authority contract is:

```yaml
schema: rook.planner_task_envelope:v1
artifact_id: task_envelope
task_session_id: ...

payload_schema: rook.fixture_or_product_task_payload:v1
payload_schema_fingerprint: sha256:...
payload: {}

value_bindings:
  - binding_id: task-value.some_fact
    json_pointer: /facts/some_fact
    semantic_key: some_fact
    value_schema: rook.semantic_string:v1
    typed_value_fingerprint: sha256:...
    authority_kind: user_fact | task_fact
    provenance:
      issuer_kind: trusted_ingress | deterministic_fixture
      issuer_id: ...

issued_at: ...
artifact_fingerprint: sha256:...
```

`payload` is validated under its exact registered payload schema. The generic
task-envelope validator does not know domain fact names. `value_bindings` is a
complete authority index for every task value a recipe may cite. Its JSON
Pointer is relative to the root of `payload`, the resolved value validates under
`value_schema`, and its canonical typed-value fingerprint must match.

Every binding JSON Pointer is unique within the companion. Duplicate pointers,
even under different binding IDs or semantic keys, are invalid.

`authority_kind` comes from the trusted envelope and is closed to `user_fact`
or `task_fact`; the recipe cannot choose it. The deterministic fixtures use
`deterministic_fixture`, while production ingress uses its trusted issuer.

### 4.3 Environment Snapshot

The minimal environment-observation contract is:

```yaml
schema: rook.environment_snapshot:v1
artifact_id: environment_snapshot
environment_session_id: ...

payload_schema: rook.registered_environment_payload:v1
payload_schema_fingerprint: sha256:...
payload: {}

value_bindings:
  - binding_id: environment-value.some_observation
    json_pointer: /observations/some_observation
    semantic_key: some_observation
    value_schema: rook.semantic_string:v1
    typed_value_fingerprint: sha256:...
    authority_kind: environment_observation

observed_at: ...
expires_at: ...
issuer:
  kind: trusted_environment_gateway
  authority_id: ...

artifact_fingerprint: sha256:...
```

An environment reference is valid only when the snapshot is unexpired at the
trusted validation time and its environment session matches every applicable
session binding. An expired or wrong-session snapshot is invalid authority, not
a compile-readiness guess. Environment observations describe current state and
do not become desired user state.

Environment binding JSON Pointers are likewise payload-relative and unique.

### 4.4 Payload Schema Registry

The generic validator receives complete payload schemas through one
fingerprinted validation-context registry:

```yaml
schema: rook.payload_schema_registry:v1
registry_id: payload_schema_registry
registry_version: lm9a.payload_schemas:v1
json_schema_dialect: https://json-schema.org/draft/2020-12/schema
schema_evaluator_profile: rook.json_schema_profile:lm9a_payload_v1

entries:
  - schema_id: rook.fixture_or_product_task_payload:v1
    schema_fingerprint: sha256:...
    schema_document: {}

registry_fingerprint: sha256:...
```

Entries are sorted by `schema_id`; duplicate IDs are invalid. Each task or
environment companion's `payload_schema` and `payload_schema_fingerprint` must
match exactly one entry. The validator verifies the schema-document fingerprint
before validating the payload.

Schema documents are supplied in full and validated against the exact dialect
and the sealed evaluator profile in Section 7 of the kernel spec. The profile is
a deliberately restricted Draft 2020-12 subset, not permission to execute an
arbitrary Draft 2020-12 schema. It permits closed structural, collection,
string-length, numeric-bound, enum/const, and local acyclic `$defs`/`$ref`
validation. It forbids remote or dynamic references, retrieval, regex and format
callbacks, conditionals, combinators, unevaluated/dependent/contains semantics,
content keywords, and custom executable keywords.

Each embedded schema is limited to 4,096 nodes, 256 local references, local
reference depth 16, and a conservative
`schema_nodes * instance_nodes <= 2,000,000` evaluation shape. Both node counts,
the exact evaluated instance root, checked multiplication, repeated-evaluation
charging, and cache independence use the normative kernel Section 4 rules.
Unknown keywords fail profile validation rather than being ignored. The exact
evaluator package, metaschema, keyword allowlist, reference rules, limits, type
checker, and trusted core schemas are fingerprinted into the sealed validation
program. A richer payload schema requires a new reviewed profile version.

The registry lets fixture and future product payload schemas remain domain-
specific data without hardcoding those domains into LM9A semantic runners.

The registry fingerprint is validation context and appears in the validation
report. The exact payload-schema fingerprint is also bound into its task or
environment companion and therefore into any recipe that references that
companion.

### 4.5 Planning Policy

The minimal policy contract is:

```yaml
schema: rook.planning_policy:v1
artifact_id: planning_policy
policy_registry_id: ...

rules:
  rule.some_semantic_value:
    rule_id: rule.some_semantic_value
    semantic_key: some_semantic_value
    effect: allow | default | prohibit
    value_schema: rook.semantic_scalar:v1
    unit: domain_unit | null
    unit_context_ref: null
    task_scope: create_new
    target_scope: task_created_objects
    operation_kind: create
    value_constraint:
      kind: exact | closed_range
      exact_value: null
      minimum: "1.0"
      maximum: "10.0"
      minimum_inclusive: true
      maximum_inclusive: true

issued_at: ...
expires_at: ...
issuer:
  kind: trusted_policy_registry
  authority_id: ...

artifact_fingerprint: sha256:...
```

`rules` is a schema-constrained map keyed by stable `rule_id`; each key must
equal the nested `rule_id`. A policy-rule reference uses a JSON Pointer such as
`/rules/rule.some_semantic_value`, never an array index. `default` requires an
exact value. `allow` and `prohibit` may use exact or closed-range constraints.
Units and unit-context references are mandatory whenever the semantic value is
unit-sensitive.

Policy-registry validation rejects overlapping rules for one semantic key and
scope within a registry. Exact matching evaluates semantic key, value schema,
unit context, task scope, target scope, operation kind, and value constraint.

### 4.6 Assumption Confirmation And Deferred Receipt Kinds

The assumption-confirmation companion is:

```yaml
schema: rook.planner_assumption_confirmation_receipt:v1
artifact_id: confirmation.assumption.some_value
receipt_id: ...

issuer:
  kind: trusted_confirmation_gateway
  authority_id: ...

task_envelope_fingerprint: sha256:...
confirmation_subject_fingerprint: sha256:...
assumption_id: assumption.some_value
typed_value_fingerprint: sha256:...
user_task_session_id: ...
decision: confirmed | rejected

issued_at: ...
expires_at: ...
receipt_fingerprint: sha256:...
```

LM9A v1 accepts no target-selection or privileged-authority receipt companion.
When a recipe needs either boundary, validation derives
`trusted_selection_required` or `privileged_authorization_required`, keeps the
recipe non-compile-ready, and rejects any attempted receipt artifact as an
unknown v1 artifact kind.

The future schema names are reserved identifiers only:

```text
rook.trusted_target_selection_receipt:v1
rook.privileged_authority_receipt:v1
```

A later dedicated design must define their complete envelopes, trusted issuer
authentication, target-token semantics, scope intersection, expiry, revocation,
and session behavior before adding either artifact kind. Until then, no raw
GUID, conversational confirmation, or self-described scope can satisfy these
blockers.

The Planner, compiler, delegates, and workers cannot issue trusted companions.
Issuer authenticity is resolved through the existing trusted registry or an
equivalent authenticated gateway mechanism; a self-asserted issuer field has no
authority.

### 4.7 Capability Registry And Vocabulary Companions

The environment capability registry is validation context, not semantic
authority:

```yaml
schema: rook.environment_capability_registry:v1
registry_id: capability_registry
registry_session_id: ...
observed_at: ...
expires_at: ...
entries:
  - capability_code: construct_parametric_geometry
    availability: available | unavailable
    implementation_refs: []
    constraints_fingerprint: sha256:...
registry_fingerprint: sha256:...
```

Its v1 entries are sorted by `capability_code`; duplicates are invalid. It can
prove reported availability but cannot grant delegation or mutation authority.
An `available` entry requires at least one implementation reference; an
`unavailable` entry requires none. The registry must be unexpired and match the
trusted capability-registry session.

Every vocabulary companion has `schema`, `vocabulary_version`, `entries`, and
`vocabulary_fingerprint`. The exact companion identities and minimum closed v1
entries are:

| Companion schema | `vocabulary_version` | Required v1 entries |
|---|---|---|
| `rook.semantic_authority_code_vocabulary:v1` | `rook.semantic_authority_codes:v1` | `select_representation`, `construct_topology`, `lower_verification`, `instantiate_worker_slot` |
| `rook.semantic_capability_code_vocabulary:v1` | `rook.semantic_capability_codes:v1` | `construct_parametric_geometry`, `manage_document_layers` |
| `rook.worker_slot_code_vocabulary:v1` | `rook.worker_slot_codes:v1` | `author_formula_realization` |
| `rook.semantic_materiality_code_vocabulary:v1` | `rook.semantic_materiality_codes:v1` | `tool_arguments`, `geometry_state`, `document_state`, `target_identity`, `topology`, `execution_branching`, `verifier_predicate`, `verifier_threshold`, `fingerprint`, `canonicalization`, `capability_authority`, `mutation_authority` |
| `rook.semantic_value_schema_registry:v1` | `rook.semantic_value_schemas:v1` | `rook.semantic_integer:v1`, `rook.semantic_scalar:v1`, `rook.semantic_string:v1`, `rook.semantic_boolean:v1`, `rook.semantic_unit_context:v1` |

Entry shapes are closed by vocabulary kind:

```text
authority code:
  code, allowed_shape_sections, allowed_delegate_kinds,
  requires_worker_slot

capability code:
  code, permitted_supporting_clause_kinds

worker-slot code:
  code, allowed_output_schemas, allowed_input_kinds,
  required_shape_authority_code

materiality code:
  code

semantic value schema:
  schema
```

Authority-code entries declare permitted shape sections and delegate kinds.
`select_representation`, `construct_topology`, and `lower_verification` permit
`compile_phase`; `instantiate_worker_slot` additionally requires an explicit
worker-slot ID.

Capability-code entries declare permitted supporting clause kinds. Both v1
capabilities may support `maintains`; `manage_document_layers` may also support
an invariant about layer mutation scope.

The `author_formula_realization` slot entry allows only the exact output schema
`rook.worker_formula_realization:v1`, input kinds `clause`, `artifact_value`,
`assumption`, and `derived_fact`, and the shape authority code
`instantiate_worker_slot`. It grants no tool, target, topology, or mutation
authority. No canonical LM9A fixture instantiates it.

Unknown vocabulary entries and missing or mismatched vocabulary fingerprints
are validation errors. Adding a new tool or Grasshopper component does not by
itself justify a new semantic capability code.

## 5. Core Semantic Rules

### 5.1 Materiality

A decision or value is material when it affects any of:

- tool arguments;
- geometry or document state;
- target identity;
- topology or execution branching;
- verifier predicates or thresholds;
- fingerprints or canonicalization;
- capability or mutation authority.

Typed backing is required when a concrete value crosses one of those
boundaries. Bounded semantic prose may remain prose until intelligent compile
lowers it, provided the recipe does not disguise an invented concrete value as
authoritative data.

### 5.2 Honest Limits Of Deterministic Validation

A generic deterministic validator can prove:

> No concrete material value in a typed material field lacks recognized
> authority.

It cannot prove that prose entails its cited sources, contains no hidden
unsourced number, or faithfully expresses the user's meaning. Therefore:

```text
valid = true
```

means the recipe contains no deterministically detectable schema, authority,
provenance, or consistency error. It does not claim prose entailment, complete
semantic fidelity, or successful future compilation.

### 5.3 Stable Clause Identity

Every semantic clause has a stable `clause_id`. Clause IDs are globally unique
across goal, requirements, maintained truth, nested canonicalization clauses,
nested postconditions, and invariants.

Renaming a clause moves the recipe fingerprint because traceability identity is
material.

### 5.4 One Discriminated Reference Union

Every semantic or authority reference uses one closed
`RookSemanticReferenceV1` union. No colon-delimited strings, bare paths, or
recipe-local reference aliases are permitted:

```yaml
# Artifact value
kind: artifact_value
artifact_id: task_envelope
json_pointer: /facts/requested_name

# Policy rule
kind: policy_rule
artifact_id: planning_policy
json_pointer: /rules/rule.some_semantic_value

# Trusted receipt
kind: receipt
artifact_id: confirmation.assumption.some_value
receipt_id: ...
receipt_fingerprint: sha256:...

# Recipe identities
kind: clause | assumption | derived_fact | unresolved_intent |
      shape | capability | worker_slot
<matching_id_field>: ...
```

The matching ID fields are `clause_id`, `assumption_id`, `derived_fact_id`,
`intent_id`, `shape_id`, `capability_id`, and `worker_slot_id` respectively.
Each variant rejects fields belonging to another variant.

In LM9A v1, the `receipt` variant may resolve only
`rook.planner_assumption_confirmation_receipt:v1`. Reserved future target or
privileged receipts are not accepted reference targets.

An `artifact_value` JSON Pointer is always relative to the root of the resolved
companion's `payload`, never to the companion envelope. It must equal the JSON
Pointer of exactly one `value_bindings` entry. Zero matches, multiple matches,
or a resolved value whose schema or fingerprint disagrees with that binding is
invalid. A `policy_rule` JSON Pointer is the only reference pointer resolved
against a companion envelope; it resolves from the root of the policy artifact
to exactly one rule in its stable `rules` map.

All semantic-reference, value-binding, policy-rule, vocabulary-binding, and
issue-path pointers use RFC 6901 JSON Pointer string syntax. URI-fragment form
is forbidden. Semantic references and value bindings require a nonempty pointer
whose first character is `/`; the empty whole-document pointer is invalid.
Pointer escape sequences use only RFC 6901 `~0` and `~1`, resolution uses exact
string property names, and neither pointer strings nor resolved property names
are Unicode-normalized. Diagnostic `path` may be the empty pointer to identify
the whole submitted recipe; `related_paths` entries, when present, are nonempty.

Homogeneous structural collections such as `affected_clause_ids` and
`maintains_clause_ids` remain explicit ID lists because their field names fix
the target type. Every heterogeneous or authority-bearing reference uses the
discriminated union above.

### 5.5 Source References

External source references use payload-relative JSON Pointer and resolve through
exact companion value bindings supplied to validation:

```yaml
source_refs:
  - kind: artifact_value
    artifact_id: task_envelope
    json_pointer: /facts/requested_name
```

`task_envelope` is the reserved task authority. Optional environment, policy,
selection, confirmation, and other authority artifacts are declared separately.

The recipe cannot invent an artifact classification. Schema, fingerprint,
session, issuer, and freshness facts come from the companion artifact and its
trusted registry.

Invalid paths, missing values, mismatched schemas or fingerprints, stale
environment sessions, and wrong-session references are validation errors.

### 5.6 Common Clause Fields And Synthesis

Goal, requirement, maintains, postcondition, and invariant clauses all contain:

```yaml
clause_id: ...
statement: ...
source_refs: []
assumption_refs: []
derived_fact_refs: []
synthesis: null
```

`source_refs` permits only `artifact_value`, `assumption_refs` only
`assumption`, and `derived_fact_refs` only `derived_fact`. A clause with none of
those references must use a non-null, clause-kind-appropriate synthesis code.
Canonicalization clauses intentionally omit `derived_fact_refs`; they classify
their immediate parent maintains clause and may inherit that parent's support
only through `inherited_support_from`.

The closed synthesis codes are:

| Clause kind | Permitted non-null `synthesis.kind` |
|---|---|
| goal | `planner_goal_synthesis` |
| requires | `planner_requirement_synthesis` |
| maintains | `planner_semantic_synthesis` |
| canonicalization | `planner_semantic_classification` |
| postcondition | `planner_postcondition_projection` |
| invariant | `planner_invariant_projection` |

`synthesis` is either `null` or an object containing only `kind`. A synthesis
code permitted for one clause kind is invalid on another.

### 5.7 Closed Semantic Coverage Traversal

A clause may use authority only from:

- references declared directly by that clause;
- assumptions and, where the clause schema permits, derived facts explicitly
  referenced by that clause;
- `requires` entries explicitly connected through `supports_clause_ids`;
- immediate parent-maintains references for nested canonicalization and
  postcondition clauses when `inherited_support_from` names that actual parent.

Authority cannot be borrowed from the goal, sibling clauses, arbitrary
ancestors, unrelated graph entries, or general graph reachability.

## 6. Planner Graph Recipe Contract

The top-level object and every nested product object are closed with
`additionalProperties: false`:

```yaml
schema: rook.planner_graph_recipe:v1

source_task:
  artifact_id: task_envelope
  artifact_kind: task_envelope
  schema: rook.planner_task_envelope:v1
  fingerprint: sha256:...

authority_artifacts: []

goal: {}
requires: []
maintains: []
assumptions: []
derived_facts: []
unresolved_intent: []
invariants: []

shape:
  vocabulary_version: rook.semantic_authority_codes:v1
  vocabulary_fingerprint: sha256:...
  self: []
  delegates: []
  prohibited: []

required_capabilities:
  vocabulary_version: rook.semantic_capability_codes:v1
  vocabulary_fingerprint: sha256:...
  entries: []

worker_slots:
  vocabulary_version: rook.worker_slot_codes:v1
  vocabulary_fingerprint: sha256:...
  entries: []

recipe_fingerprint: sha256:...
```

Empty collections remain explicit. `null`, absent, and empty values remain
distinct according to the schema.

### 6.1 Source Task And Authority Artifacts

The raw task brief is not copied into the recipe. It remains in the separately
receipted task envelope.

```yaml
source_task:
  artifact_id: task_envelope
  artifact_kind: task_envelope
  schema: rook.planner_task_envelope:v1
  fingerprint: sha256:...

authority_artifacts:
  - artifact_id: environment_snapshot
    artifact_kind: environment_snapshot
    schema: rook.environment_snapshot:v1
    fingerprint: sha256:...
```

Every authority artifact has a unique stable `artifact_id`. The validator
receives complete companion payloads separately and checks every declaration.
Descriptor `fingerprint` must equal the companion schema's terminal fingerprint
field: `artifact_fingerprint`, `receipt_fingerprint`, or the corresponding
registry/vocabulary fingerprint. The descriptor never substitutes for the full
companion.

Recipe-bound `artifact_kind` is closed to `task_envelope`,
`environment_snapshot`, `planning_policy`, and `confirmation_receipt` in LM9A
v1. Target-selection and privileged-authority artifacts are explicitly deferred
by Section 4.6.

`task_envelope` appears exactly once in `source_task` and is forbidden in the
`authority_artifacts` collection.

Recipe-bound artifacts are those explicitly referenced by recipe content:

- the task envelope;
- authority artifacts cited by clauses;
- confirmation receipts;
- exact policy artifacts cited by assumptions;
- explicitly referenced environment observations.

Their trusted fingerprints participate in recipe identity. Validation-context
artifacts that the recipe does not reference are recorded only in the report.
Every declared `authority_artifacts` entry must be referenced by a clause,
assumption, unresolved authorization context, confirmation, or other
schema-defined recipe field. Unused authority declarations are invalid rather
than an alternate way to smuggle validation context into recipe identity.

### 6.2 Goal

The recipe contains exactly one goal clause:

```yaml
goal:
  clause_id: goal.primary
  statement: ...
  source_refs: []
  assumption_refs: []
  derived_fact_refs: []
  synthesis: null
  projected_into:
    maintains_clause_ids: []
    invariant_clause_ids: []
    unresolved_intent_ids: []
```

The goal says why the task exists and broadly what it is intended to achieve.
It never grants mutation authority.

A valid goal projects into at least one `maintains` clause or unresolved-intent
entry. An invariant may supplement that projection but cannot be the goal's
only projection. A goal that projects only into unresolved intent may be valid,
but is not compile-ready.

Future material mutation IR must cite at least one `maintains` clause. Goal,
facts, assumptions, and invariants may support that authority but cannot replace
it. Read-only observation IR may instead trace to `requires` or an invariant.

### 6.3 Requires

`requires` describes current or input truth that must be known or checked to
satisfy maintained truth or invariants. It does not name tool parameters,
upstream nodes, providers, or implementation strategies.

```yaml
requires:
  - clause_id: required.document_unit_context
    statement: ...
    source_refs: []
    assumption_refs: []
    derived_fact_refs: []
    synthesis: null
    supports_clause_ids:
      - maintained.some_result
    evidence_requirement:
      semantic_key: document_unit_context
      value_schema: rook.semantic_unit_context:v1
      freshness_required: true
      session_binding_required: true
```

A requirement must support at least one maintains or invariant clause. Orphan
requirements are invalid. A requirement cannot be satisfied circularly by the
output being created.

Planner synthesis may organize or relate sourced meanings, but cannot itself
supply required evidence. A material requirement must ultimately resolve
through:

- an authoritative referenced artifact;
- a receipt-backed observation selected during compile; or
- an explicitly authorized assumption.

An intentionally unbound observation requirement may remain valid when bounded
compile could emit an authorized observation and freshness gate. Observation
failure is later operational readiness evidence, not unresolved user intent.

A fixture uses `requires: []` when no authentic current-state dependency exists;
it does not invent a dependency merely to exercise the field.

Future compile coverage keeps source resolution and enforcement orthogonal:

```yaml
requirement_resolution:
  clause_id: required.document_unit_context
  source_resolution:
    kind: authority_bound | compiled_observation | unavailable
  enforcement:
    phase: compile_time | pre_execution
  status: covered | unsupported
  emitted_ir_refs: []
```

An unsupported material requirement forbids executable IR.

### 6.4 Maintains

`maintains` describes semantic truth that must hold in the accepted task result
and any artifact published by that run. LM9A does not create subscriptions,
reactive maintenance, or long-lived world-model ownership.

Every maintains clause is a material semantic obligation by default:

```yaml
maintains:
  - clause_id: maintained.some_result
    statement: ...
    source_refs: []
    derived_fact_refs: []
    assumption_refs: []
    synthesis: null
    canonicalization: []
    postconditions: []
```

A source-free semantic clause is allowed only when it explicitly declares
Planner synthesis:

```yaml
synthesis:
  kind: planner_semantic_synthesis
```

Synthesis can state or organize semantic relationships. It cannot label an
invented concrete value as a user fact, environment observation, or policy
value.

#### Canonicalization Clauses

Canonicalization describes which observable distinctions do and do not change
already-authorized maintained truth:

```yaml
canonicalization:
  - clause_id: canonicalization.collection_order
    statement: Ordering of otherwise equivalent elements is immaterial.
    applies_to_clause_ids:
      - maintained.some_result
    source_refs: []
    assumption_refs: []
    inherited_support_from:
      - maintained.some_result
    synthesis:
      kind: planner_semantic_classification
```

Canonicalization may classify representation distinctions as material or
immaterial. It cannot introduce desired truth, mark an explicit user
requirement immaterial, weaken an invariant, or weaken a postcondition.

#### Postcondition Clauses

Postconditions are testable semantic projections of maintained truth, not a
second source of meaning:

```yaml
postconditions:
  - clause_id: postcondition.some_property
    statement: ...
    source_refs: []
    derived_fact_refs: []
    assumption_refs: []
    synthesis: null
    inherited_support_from:
      - maintained.some_result
```

Canonicalization and postconditions remain bounded prose in LM9A. Typed field
selectors, verifier predicates, tolerances, tools, and observation choreography
belong to future compiled IR.

Every material maintains clause must later receive an explicit compile-time
verification disposition:

```text
deterministic_verifier
receipt_backed_observation
semantic_review_required
render_attested
unsupported
```

The recipe does not select the disposition or verifier tool.

### 6.5 Assumptions

Explicit Planner assumptions are the only new concrete material values authored
directly in the recipe.

```yaml
assumptions:
  - assumption_id: assumption.some_semantic_value
    semantic_key: some_semantic_value
    statement: ...
    typed_value:
      schema: rook.semantic_scalar:v1
      value: "1.25"
      unit: domain_unit
      unit_context_ref:
        kind: artifact_value
        artifact_id: environment_snapshot
        json_pointer: /unit_contexts/applicable
    affects:
      - document_state
    basis_refs: []
    authorization_refs:
      policy_refs:
        - kind: policy_rule
          artifact_id: planning_policy
          json_pointer: /rules/rule.some_semantic_value
      confirmation_ref: null
```

Each policy reference is a `policy_rule` reference. The recipe's authority-
artifact declaration supplies the exact policy fingerprint, while the reference
supplies its stable rule JSON Pointer. A non-null confirmation reference is a
`receipt` reference and therefore carries artifact ID, receipt ID, and receipt
fingerprint. `basis_refs` uses the same semantic-reference union.

`affects` uses a closed generic vocabulary. Typed value schemas and units are
registered and generic. Values requiring precision outside interoperable JSON
number behavior use schema-defined decimal strings.

The Planner does not author an authoritative authorization mode. The validator
derives one of:

```text
policy_auto
confirmation_required
confirmed
trusted_selection_required
privileged_authorization_required
policy_prohibited
policy_ambiguous
```

Rules include:

- a Planner assumption cannot override contradictory user/task facts, trusted
  selections, privileged scope, or an applicable policy prohibition;
- environment observations describe current state and may differ from desired
  state;
- policy defaults apply only when the semantic value is absent;
- a policy range permits a Planner selection but does not itself supply one;
- one exact applicable allow rule, or one matching exact default, is required
  only for the derived `policy_auto` outcome;
- no applicable allow, default, or prohibition yields `confirmation_required`;
- an applicable prohibition yields `policy_prohibited`, preserving the requested
  intent while blocking compile;
- multiple applicable rules from otherwise valid supplied policy artifacts
  yield `policy_ambiguous`;
- statement and typed value disagreement is invalid when deterministically
  detectable;
- overlapping policy rules for the same semantic key and scope invalidate the
  policy registry;
- unit-sensitive authorization binds the exact unit context;
- semantic policy is checked provisionally here and rechecked against exact
  resolved targets and operations during future IR authorization.

#### Authority Classes

Ordinary semantic design choices may use confirmation receipts. Target,
document, layer, or object selection requires a trusted selection receipt and
cannot be represented as an unsourced GUID assumption. Mutation-authority
expansion and external or cross-scope side effects require a privileged
authority receipt. Hard legal, compliance, safety, verification, and capability
prohibitions are not overridden by ordinary confirmation.

In LM9A v1, trusted selection and privileged authorization remain blocker
outcomes because their receipt companions are deferred by Section 4.6.

#### Confirmation Subject And Receipt

The pre-confirmation subject fingerprint is computed over a closed projection of
the canonical recipe:

1. remove the top-level `recipe_fingerprint` field;
2. replace every selected `confirmation_ref` value with `null` rather than
   removing the field;
3. remove from `authority_artifacts` exactly the `confirmation_receipt`
   descriptor named by each selected non-null confirmation reference; and
4. canonicalize and hash the remaining projection with
   `rook.canonical_json:v1`.

The validator determines that replacement set only after policy and assumption
evaluation that ignores confirmation-receipt effects. Every assumption whose
pre-receipt outcome is `confirmation_required` belongs to the set. It remains
in the same set after an authentic receipt changes its final outcome to
`confirmed`. A non-null `confirmation_ref` on an assumption whose pre-receipt
outcome is `policy_auto`, `trusted_selection_required`,
`privileged_authorization_required`, `policy_prohibited`, or
`policy_ambiguous` is invalid. Gratuitous receipts are never ignored or folded
into a different subject.

Each selected non-null reference must resolve to exactly one full
`rook.planner_assumption_confirmation_receipt:v1` companion and exactly one
matching recipe descriptor. That receipt binds the same assumption ID. One
descriptor cannot satisfy multiple assumptions. A confirmation-receipt
descriptor not selected through an eligible assumption is an unused authority
artifact and invalid; it is not removed from the subject projection merely
because its `artifact_kind` says `confirmation_receipt`.

The pre-receipt recipe with null references and no receipt descriptors and the
post-receipt recipe with selected references plus their matching descriptors
therefore have the same confirmation-subject fingerprint. Their ordinary recipe
fingerprints differ. Changing any semantic clause, typed assumption value,
assumption scope, task envelope, cited policy, or other recipe-bound authority
artifact changes the subject fingerprint and invalidates the old receipt.

An assumption confirmation receipt is issued only by a trusted mechanical
gateway and binds:

- receipt and issuer identity;
- task-envelope fingerprint;
- confirmation-subject fingerprint;
- assumption ID;
- exact typed-value fingerprint, including unit and unit-context material;
- assumption scope through the bound confirmation-subject fingerprint;
- user/task session;
- decision, issue time, expiry, and receipt fingerprint.

The Planner and compile delegates cannot issue receipts. Rejected, expired,
revoked, wrong-session, stale-value, or fingerprint-mismatched receipts never
make a recipe compile-ready. Changing semantics or an authority artifact
invalidates prior receipts; changing only confirmation-reference values does
not move the subject fingerprint when the matching selected receipt descriptors
are added or removed by the projection above.

### 6.6 Derived Facts

A deterministic derived fact introduces no semantic authority:

```yaml
derived_facts:
  - derived_fact_id: derived.total_count
    typed_value:
      schema: rook.semantic_integer:v1
      value: 12
    derivation:
      operator: multiply
      input_refs:
        - kind: artifact_value
          artifact_id: task_envelope
          json_pointer: /facts/group_count
        - kind: artifact_value
          artifact_id: task_envelope
          json_pointer: /facts/items_per_group
```

LM9A permits only a tiny registered allowlist of deterministic derivations that
the validator can recompute exactly. It does not introduce a general expression
language. A mismatched value, unsupported operator, invalid input, incompatible
type, or overflow is invalid.

### 6.7 Unresolved Intent

Unresolved intent represents absent semantic meaning honestly:

```yaml
unresolved_intent:
  - intent_id: unresolved.some_semantic_value
    semantic_key: some_semantic_value
    statement: ...
    affected_clause_ids: []
    value_schema: rook.semantic_scalar:v1
    resolution_authority:
      permitted_kinds:
        - user_fact
        - planner_assumption
      permitted_assumption_outcomes:
        - policy_auto
        - confirmed
    authorization_context_refs:
      policy_refs:
        - kind: policy_rule
          artifact_id: planning_policy
          json_pointer: /rules/rule.some_semantic_value
    expected_source_location:
      artifact_id: task_envelope
      json_pointer: /facts/some_semantic_value
    unit_context_ref: null
```

`expected_source_location` is a closed `{artifact_id, json_pointer}` resolution
hint, not a semantic reference and not authority. It is excluded from authority
coverage traversal but remains fingerprint-material.

In v1, any unresolved intent blocks executable compilation:

```text
valid = true
compile_ready = false
compiler request creation = forbidden
worker request creation = forbidden
executable IR = forbidden
mutation = forbidden
```

Validation and clarification may still occur.

An exact policy default makes a matching unresolved entry redundant and
invalid. A policy range does not supply a value. A value awaiting confirmation
is an assumption with `confirmation_required`, not unresolved intent. Trusted
selection, privileged authorization, environment readiness, and delegated
implementation choice remain separate classifications.

An unresolved entry may cite the exact policy rule that constrains a future
resolution. Such a reference supplies authorization context, never the absent
semantic value.

Duplicate unresolved entries for one semantic key are invalid. A stale entry is
invalid when cited authority already supplies the value. Affected clauses must
exist and be reachable from the goal projection. Resolution updates authority,
revises the recipe, moves its fingerprint, and reruns validation. Compiler and
worker artifacts can never resolve intent.

### 6.8 Invariants

Invariants describe task-specific truth that no observable execution path may
violate, including failed and partial paths:

```yaml
invariants:
  - clause_id: invariant.preserve_existing_content
    statement: Existing content outside task scope is not modified.
    source_refs: []
    assumption_refs: []
    derived_fact_refs: []
    synthesis: null
```

LM9A validates invariant declaration, provenance, clause identity, and
authority. It does not implement preventive enforcement.

Future compile output must provide preventive invariant coverage. At least one
of these mechanism classes is required:

```text
static IR check
pre-execution guard
commit guard
failure containment
```

Execution receipts and final verifiers provide detection and audit evidence but
cannot preserve an invariant alone. If execution may partially mutate state,
coverage must describe atomic commit, staged publication, rollback, or bounded
failure containment. Unsupported preventive coverage forbids executable IR.

External policy remains independently enforced. A recipe invariant may project
policy or task constraints for traceability but cannot activate, narrow, or
replace external policy.

### 6.9 Shape

`shape` is a closed-world, narrowing-only semantic authority manifest:

```yaml
shape:
  vocabulary_version: rook.semantic_authority_codes:v1
  vocabulary_fingerprint: sha256:...
  self: []
  delegates:
    - shape_id: shape.delegate.representation
      delegate_kind: compile_phase
      authority_code: select_representation
      worker_slot_id: null
      statement: ...
  prohibited: []
```

Rules:

- the versioned external vocabulary defines valid codes and delegate kinds;
- absent from `delegates` means not delegated;
- present in `self` means retained and nondelegable;
- overlap between `self` and `delegates` is invalid;
- overlap between `delegates` and `prohibited` is invalid;
- unknown codes are invalid;
- prose wider than the associated closed code is invalid when deterministically
  detectable;
- universal restrictions remain external and need not be repeated;
- every future compile decision cites its applicable `shape_id`;
- a delegate using `instantiate_worker_slot` requires a non-null
  `worker_slot_id`; every other delegate code requires `worker_slot_id: null`;
- worker delegation requires exact bidirectional linkage between one delegate
  entry and one explicit worker slot.

Representation authority is not execution authority. `construct_topology`
permits a compiler to describe topology in inert compiled IR; it does not grant
tool, target, or mutation authority.

Effective authority is the intersection of:

```text
task-envelope authority
and external policy
and trusted target receipts
and capability registry
and fixed compiler-program authority
and recipe delegation
and worker-slot bounds
```

Recipe prohibitions may narrow it further. Shape never substitutes for a
maintains clause as semantic outcome authority.

### 6.10 Required Capabilities

Capability codes describe stable, coarse semantic abilities, not tools,
providers, models, component names, or command strings:

```yaml
required_capabilities:
  vocabulary_version: rook.semantic_capability_codes:v1
  vocabulary_fingerprint: sha256:...
  entries:
    - capability_id: capability.construct_parametric_geometry
      capability_code: construct_parametric_geometry
      statement: ...
      supports_clause_ids:
        - maintained.some_result
```

Two external concepts remain separate:

```text
semantic capability vocabulary
  stable codes and permitted clause categories

environment capability registry
  receipted inventory of available implementations, versions,
  constraints, and operational dependencies
```

The vocabulary cannot claim an implementation exists. The environment registry
cannot grant semantic or mutation authority.

Result observation is not a v1 recipe-declared semantic capability. It is a
mandatory future support dependency derived mechanically from verification
coverage. For every material maintains clause with an executable verification
disposition, bounded compile must emit at least one support dependency:

```yaml
support_dependency_id: support.observe.some_result
dependency_kind: observe_maintained_truth
maintained_clause_id: maintained.some_result
verification_coverage_ref: verification.some_result
implementation_ref: ...
authorization_refs: []
```

Deterministic compile-output validation requires the observation dependency to
be resolved, authorized, and traceable to that maintained clause. Semantic
review, a final claimed value, or a verifier label cannot substitute for it. If
no authoritative observation mechanism is available, coverage is `unsupported`
and executable IR is forbidden. This rule prevents every Planner recipe from
repeating verification plumbing while still making observation mandatory.
Every emitted verifier IR reference must cite the support dependency it uses;
unused or uncited observation dependencies are invalid.

LM9A validates code existence, clause-reference integrity, and permitted clause
categories. A trusted report of unavailable or unauthorized required capability
is a compile blocker. `compile_ready=true` means bounded compile may be
attempted; it does not guarantee successful capability resolution or compile.

Future capability resolution keeps implementation availability and authority
orthogonal:

```text
resolution_status:
  resolved | unavailable | ambiguous | unsupported

authorization_status:
  authorized | unauthorized | not_evaluated
```

Executable IR requires both `resolved` and `authorized`. Every operation must
trace to a resolved semantic capability or a validated support dependency of
its implementation.

### 6.11 Worker Slots

Worker slots are permission-only semantic delegation envelopes:

```yaml
worker_slots:
  vocabulary_version: rook.worker_slot_codes:v1
  vocabulary_fingerprint: sha256:...
  entries:
    - worker_slot_id: worker_slot.formula_realization
      slot_code: author_formula_realization
      output_schema: rook.worker_formula_realization:v1
      permitted_under_shape_id: shape.delegate.formula_realization
      supports_clause_ids:
        - maintained.some_result
      input_refs:
        - kind: clause
          clause_id: maintained.some_result
```

The slot registry constrains each `slot_code` to an allowlist of exact output
schemas and input-reference kinds. Unknown codes, disallowed schemas, unknown
inputs, or prose wider than the code/schema are invalid.

Every worker slot must name exactly one `permitted_under_shape_id` whose shape
delegate uses `authority_code: instantiate_worker_slot` and points back through
the same `worker_slot_id`. Every such delegate must resolve to exactly one slot.
Missing, duplicate, one-way, or mismatched links are invalid.

The matching delegate shape is:

```yaml
shape_id: shape.delegate.formula_realization
delegate_kind: compile_phase
authority_code: instantiate_worker_slot
worker_slot_id: worker_slot.formula_realization
statement: Bounded compile may instantiate this exact declared slot.
```

`supports_clause_ids` is nonempty and contains only existing maintains clause
IDs. It states which semantic outcome may consume validated worker content;
input references do not imply this authority.

Inputs use a closed discriminated reference list, including clause, source fact,
assumption, and derived fact references. A future compiler may narrow the
context but cannot add undeclared semantic inputs. Every instantiated request
records a fingerprinted context manifest.

Compilation and scheduling remain separate. A bounded compiler decides whether
to instantiate a permitted slot and emits an exact request. A trusted scheduler
selects provider and model under external policy. Provider identity and model
availability never enter the recipe.

Worker output is inert typed content. It cannot directly execute or publish
`gh_edit`, originate semantic constants, expand authority, or repair its own
invalid output. Incorporation into compiled IR requires a valid output report,
matching request and slot fingerprints, applicable shape delegation, supporting
maintained truth, and resolved authorized capability.

Future slot accounting keeps three state dimensions independent:

```text
instantiation_status:
  unused | instantiated | unsupported

execution_status:
  not_run | published | declined | failed

output_validation_status:
  not_evaluated | valid | invalid
```

`worker_slots.entries: []` absolutely forbids worker request creation. The
campaign fixtures identified in Sections 11.2 and 11.3 remain workerless. A
separate focused conformance fixture may declare one inert slot solely to prove
positive schema and linkage validation; LM9A still creates no worker request.

## 7. Authority And Conflict Matrix

Authorization is role-based rather than a total precedence ladder:

| Role | Meaning | Conflict rule |
|---|---|---|
| User or task fact | Source-owned desired or contextual fact | Planner assumptions cannot contradict it. |
| Environment observation | Fresh, session-bound current state | May differ from desired user state without conflict. |
| Derived semantic fact | Deterministic recomputation from authority | Cannot introduce authority or use unsupported derivation. |
| Planner assumption | Explicit proposed concrete semantic value | Requires derived authorization and cannot contradict authority. |
| Policy default | Exact value supplied by applicable policy | Applies only when the semantic value is absent. |
| Policy constraint | Independent allow, deny, scope, or range | May block intent but does not rewrite it. |
| Unresolved intent | Honest absence of required semantic meaning | May be valid but always blocks compilation in v1. |
| Trusted selection | Mechanically receipted target identity | Cannot be replaced by conversational assumption. |
| Privileged authorization | Mechanically receipted authority expansion | Cannot be replaced by ordinary confirmation. |
| Compiler representation decision | Future implementation choice | Cannot add or contradict material semantic outcomes. |

A concrete material value in the recipe must be exactly one of:

- a reference to an authority artifact;
- a deterministically recomputable derived fact;
- an authorized Planner assumption;
- a policy-authorized default represented as an assumption;
- a user-confirmed assumption.

A concrete value with neither authority nor authorization is invalid. An absent
value declared as unresolved may be valid but blocks compile when required.

## 8. Validation Report Contract

### 8.0 Validation Invocation Preflight

The ordinary validation report can exist only after the LM9A validation kernel
establishes the evidence needed to construct it truthfully. The preflight runs
before semantic phase evaluation or report assembly and checks, in this exact
precedence order:

1. one `SealedValidationProgram` resolves with exact manifest/runtime bindings;
2. the recipe is exact built-in `bytes` and the bundle is a valid trusted-host-
   issued `TrustedValidationBundleInput` whose `raw_bytes` is exact built-in
   `bytes`;
3. the carrier issuer capability binds one valid sealed assembler profile whose
   fingerprint recomputes and whose permitted-program set contains the selected
   `program_id`;
4. both byte lengths are at or below the sealed inclusive limits;
5. both admitted inputs are copied and their exact SHA-256 hashes are computed;
6. the validation bundle parses into one owned immutable value;
7. every mandatory report-constructability shell from Section 4.1 exists with
   the required container type;
8. the owned bundle contains valid trusted `evaluated_at`,
   `trusted_clock_source`, `task_session_id`, nullable
   `environment_session_id`, and `capability_registry_session_id` values; and
9. the captured `trusted_clock_source` is permitted by the sealed assembler
   profile and matches its closed assembler-kind rule; and
10. recipe parsing yields either an owned immutable value or one bounded schema-
   phase failure under the same `rook.validation_budget:lm9a_v1` ledger.

`evaluated_at` uses the closed UTC RFC 3339 timestamp schema already used by
LM9A companions. `trusted_clock_source` is exactly `deterministic_fixture` in
tests or `trusted_system_clock` in production. Session values use the LM9A
machine-identifier grammar; only `environment_session_id` may be `null`.
`deterministic_fixture` requires an assembler of the same kind;
`trusted_system_clock` requires `trusted_host_ingress`. The assembler ID and
version use the machine-identifier grammar. Profile ID, assembler ID, and
version are each limited to 128 ASCII characters. Profile and implementation
fingerprints use exact lowercase `sha256:<hex>` form. None of these values may be
replaced by parsed bundle content after capture.

Unknown or extra validation-bundle fields do not fail preflight when the
constructability envelope and trusted context projection above are intact. They
remain reportable `companion_artifacts` structural errors. Malformed content
inside a present mandatory shell likewise remains reportable. A missing or
wrong-container mandatory shell does not: the validator could not populate the
closed report shape truthfully, so invocation stops before report construction.

The kernel invocation boundary has this closed non-artifact control result:

```yaml
kind: invocation_failure
failure_stage: preflight | validation
code: validation_input_invalid |
      validation_budget_exceeded |
      validation_constructability_failed |
      validator_identity_unavailable |
      validator_integrity_failure |
      validator_internal_failure
artifact_role: validation_program | recipe | validation_bundle | combined |
               phase_engine | report_seal
program_id: lm9a.planner_graph_recipe:v1 | null
program_fingerprint: sha256:... | null
recipe_input_payload_sha256: sha256:... | null
validation_bundle_input_payload_sha256: sha256:... | null
validation_bundle_fingerprint: sha256:... | null
subject_path: /json/pointer | null
metadata: {}
message: bounded text
```

The message is at most 512 Unicode code points and contains no unbounded input
or exception text. `program_id` and `program_fingerprint` are non-null only after
the sealed program passes its manifest/runtime check. The two raw-input hashes
are non-null only after both inputs pass type and byte-cap admission. If either
argument is over limit, neither is copied or hashed; bounded metadata records
both observed lengths and the exceeded limit. `validation_bundle_fingerprint`
is non-null only after bounded parsing completes. `subject_path` identifies the
first deterministic failing path and is otherwise `null`. Budget failures use
the exact bounded metadata fields from the kernel spec rather than adding one
public code per budget dimension.
This result has no Rook schema, artifact fingerprint,
phase rows, `valid`, `compile_ready`, trusted time, or session claim. It is not
a partial validation report and cannot enter compilation. A future mechanical
ingress may wrap it in its own authenticated operation receipt; LM9A does not
invent that receipt.

`validator_integrity_failure` and `validator_internal_failure` always use
`failure_stage: validation`. Byte-type, parse, constructability, trusted-context,
and pre-phase budget failures use `failure_stage: preflight`. Budget exhaustion
during phase evaluation or report assembly uses `failure_stage: validation`.
The stable external code and closed metadata identify the boundary without
promoting every parser or schema branch into a permanent public code.

The internal validator returns either a conforming
`rook.planner_graph_recipe_validation_report:v1` or this typed invocation
failure. Missing/invalid trusted validation context and unavailable validator
identity are always invocation failures. Raw byte-cap failure occurs before
hashing and is always an invocation failure. After byte admission and bundle
constructability, recipe syntax, UTF-8, Unicode, local depth/width/token/number,
and product-schema failures may remain ordinary schema-phase report outcomes.
Invocation-wide parsed-node, decoded-string, or tokenizer/parser-work exhaustion
is always a `preflight` failure with `artifact_role: combined`, including when
the crossing occurs while parsing the recipe after a constructable bundle. It
cannot be recast as a recipe-local schema diagnostic.

After preflight, a ruleset/code/classification integrity assertion prevents
report issuance and becomes `validation / validator_integrity_failure` at the
public boundary. Any other caught validator implementation exception likewise
becomes `validation / validator_internal_failure`; the control result contains
only a stable bounded message, never exception text. Unit-level integrity
helpers may raise their typed exceptions so tests can prove the exact fault,
but those exceptions cannot escape the kernel invocation boundary or be
mistaken for semantic validation outcomes.

The complete earliest-honest-result matrix is:

| Failure location | Public result |
|---|---|
| sealed program identity or runtime bindings cannot be established | preflight invocation failure |
| recipe is not exact bytes, or bundle carrier/assembler binding is untrusted or malformed | preflight invocation failure with no raw hashes |
| either raw input exceeds its byte cap | preflight invocation failure with bounded length evidence and no raw hashes |
| admitted validation-bundle bytes cannot be parsed | preflight invocation failure |
| invocation-wide parsed-node, decoded-string, or parser-work budget is exhausted at either parse stage | combined preflight invocation failure |
| fixed validation budget is exceeded before report completion | preflight or validation invocation failure, according to exhaustion stage |
| mandatory report descriptor shell is missing or has the wrong container type | preflight invocation failure |
| ruleset integrity assertion or validator implementation fault before report completion | validation invocation failure |
| admitted recipe depth, width, number, UTF-8, JSON, Unicode, or recipe-schema failure with a constructable bundle | conforming report with `schema=failed` |
| malformed content inside present companion shells, or companion identity, freshness, schema, or fingerprint failure | conforming report with `companion_artifacts=failed` |
| deterministic semantic invalidity or readiness blocker | conforming report with exact phase diagnostic/blocker |

No terminal path may emit a partial report or require a report to validate the
trusted inputs needed to construct that same report.

The deterministic report answers two separate questions:

```text
Is this an honest, valid semantic contract?
Is it presently authorized and sufficiently resolved to enter compilation?
```

```yaml
schema: rook.planner_graph_recipe_validation_report:v1

recipe_input_payload_sha256: sha256:...
validation_bundle_input_payload_sha256: sha256:...
validation_bundle_fingerprint: sha256:...
claimed_recipe_fingerprint: sha256:... | null
computed_recipe_fingerprint: sha256:... | null

validator:
  program_id: lm9a.planner_graph_recipe:v1
  program_fingerprint: sha256:...
  implementation_version: lm9a.recipe_validator:v1
  ruleset_fingerprint: sha256:...
  canonicalization_version: rook.canonical_json:v1

validation_budget:
  budget_profile: rook.validation_budget:lm9a_v1
  limits_fingerprint: sha256:...
  observed: {}

validation_context:
  bundle_assembler:
    profile_id: ...
    profile_fingerprint: sha256:...
    assembler_kind: trusted_host_ingress | deterministic_fixture
    assembler_id: ...
    assembler_version: ...
    implementation_fingerprint: sha256:...
  evaluated_at: ...
  trusted_clock_source: ...
  task_session_id: ...
  environment_session_id: null
  capability_registry_session_id: ...
  validation_context_fingerprint: sha256:...

source_task:
  descriptor_kind: recipe_authority
  artifact_id: task_envelope
  artifact_kind: task_envelope
  schema: rook.planner_task_envelope:v1
  recipe_claimed_fingerprint: sha256:...
  companion_claimed_fingerprint: sha256:...
  computed_fingerprint: sha256:...
  task_session_id: ...
  environment_session_id: null
  session_status: matched
  freshness_status: not_applicable
  validation_status: passed

authority_artifacts: []

validation_context_artifacts:
  environment_snapshots: []
  policy_registries: []
  payload_schema_registry:
    descriptor_kind: registry
    registry_id: payload_schema_registry
    registry_kind: payload_schema
    schema: rook.payload_schema_registry:v1
    companion_claimed_fingerprint: sha256:...
    computed_fingerprint: sha256:...
    registry_session_id: null
    session_status: not_applicable
    freshness_status: not_applicable
    validation_status: passed
  capability_registry:
    descriptor_kind: registry
    registry_id: capability_registry
    registry_kind: capability
    schema: rook.environment_capability_registry:v1
    companion_claimed_fingerprint: sha256:...
    computed_fingerprint: sha256:...
    registry_session_id: ...
    session_status: matched
    freshness_status: fresh
    validation_status: passed

vocabularies:
  - descriptor_kind: vocabulary
    schema: rook.semantic_authority_code_vocabulary:v1
    vocabulary_version: rook.semantic_authority_codes:v1
    recipe_binding_paths:
      - /shape/vocabulary_fingerprint
    recipe_claimed_fingerprint: sha256:...
    companion_claimed_fingerprint: sha256:...
    computed_fingerprint: sha256:...
    entry_count: 4
    validation_status: passed
  - descriptor_kind: vocabulary
    schema: rook.semantic_capability_code_vocabulary:v1
    vocabulary_version: rook.semantic_capability_codes:v1
    recipe_binding_paths:
      - /required_capabilities/vocabulary_fingerprint
    recipe_claimed_fingerprint: sha256:...
    companion_claimed_fingerprint: sha256:...
    computed_fingerprint: sha256:...
    entry_count: 2
    validation_status: passed
  - descriptor_kind: vocabulary
    schema: rook.worker_slot_code_vocabulary:v1
    vocabulary_version: rook.worker_slot_codes:v1
    recipe_binding_paths:
      - /worker_slots/vocabulary_fingerprint
    recipe_claimed_fingerprint: sha256:...
    companion_claimed_fingerprint: sha256:...
    computed_fingerprint: sha256:...
    entry_count: 1
    validation_status: passed
  - descriptor_kind: vocabulary
    schema: rook.semantic_materiality_code_vocabulary:v1
    vocabulary_version: rook.semantic_materiality_codes:v1
    recipe_binding_paths: []
    recipe_claimed_fingerprint: null
    companion_claimed_fingerprint: sha256:...
    computed_fingerprint: sha256:...
    entry_count: 12
    validation_status: passed
  - descriptor_kind: vocabulary
    schema: rook.semantic_value_schema_registry:v1
    vocabulary_version: rook.semantic_value_schemas:v1
    recipe_binding_paths: []
    recipe_claimed_fingerprint: null
    companion_claimed_fingerprint: sha256:...
    computed_fingerprint: sha256:...
    entry_count: 5
    validation_status: passed

phases: []
diagnostics: []
compile_blockers: []

valid: true
compile_ready: false
report_fingerprint: sha256:...
```

The report and every nested report object are closed with
`additionalProperties: false`.

### 8.1 Raw Input And Validator Identity

`recipe_input_payload_sha256` and
`validation_bundle_input_payload_sha256` are hashes of the exact admitted bytes
before parsing. Admission first checks both byte lengths without scanning. If
either exceeds its limit, neither input is copied or hashed and no conforming
LM9A report can be issued. A report likewise cannot be issued when bundle bytes
are unavailable or cannot be bounded-parsed into the descriptor source needed
to construct it.

Recipe input bytes must decode as strict UTF-8 and must not begin with a UTF-8
BOM. Invalid UTF-8 or a BOM still permits hashing the received bytes, but the
`schema` phase fails and `computed_recipe_fingerprint` is `null`.

All byte, depth, width, node, decoded-string, number-token, reference, issue,
and work limits come from the fixed `rook.validation_budget:lm9a_v1` profile in
the kernel spec. The bounded tokenizer and iterative parser charge limits before
allocating or appending values. LM9A does not accept a parsed mapping and does
not use `json.loads` followed by an unbounded post-parse walk.

An admitted recipe parse or local parser-limit failure retains the exact recipe
byte hash, sets `computed_recipe_fingerprint` to `null`, fails `schema`, and
makes semantic dependents `not_evaluated` when the validation bundle is
constructable. A raw byte-cap failure is earlier and has no input hash or report.
Validation-bundle parse/budget failure cannot produce a semantic report.
Phase-engine or one-shot report-seal budget failure produces a validation-stage
kernel control result, never a partial report.

An integer outside the product safe range but still inside the finite binary64
domain remains legal inside an embedded schema document, as established by
Section 9. Product payloads still reject such integers where their own schema or
product-number policy requires it. Bounded parsing rejects values that cannot
enter the finite JCS number domain at all.

Malformed input may still have an input hash while
`computed_recipe_fingerprint` is `null`; `claimed_recipe_fingerprint` may also
be `null` when parsing cannot recover it. Claimed and independently computed
fingerprints remain separate.

The report's `validator.program_fingerprint` is the authority for the complete
sealed validation machine: budget, parser/canonicalizer, schema profile,
schemas, exact phase dataflow, runners, issue vocabulary, export types, report
projection, and runtime dependencies. Component versions and fingerprints,
including `ruleset_fingerprint`, remain audit provenance but cannot substitute
for the sealed program identity. Exact inputs without that program identity are
not replayable evidence.

`ruleset_fingerprint` is computed by the trusted program seal over the closed
LM9A-Semantics submanifest: semantic schemas, full `PhaseSpec` entries, runner
and transitive rule-helper source fingerprints, issue vocabulary, semantic
export validators, and semantic report projection. It excludes only its own
field. It is not authored by a runner or recomputed from whatever modules happen
to be imported at invocation time. A semantic rule change therefore moves both
the ruleset and whole-program fingerprints.

### 8.2 Companion Evidence Descriptors

The report uses four closed descriptor shapes. Fingerprint fields are nullable
only when malformed input prevents recovery or canonicalization.

#### Recipe-Bound Authority Descriptor

`source_task` and every `authority_artifacts` entry use:

```yaml
descriptor_kind: recipe_authority
artifact_id: ...
artifact_kind: task_envelope | environment_snapshot | planning_policy |
               confirmation_receipt
schema: ...

recipe_claimed_fingerprint: sha256:...
companion_claimed_fingerprint: sha256:...
computed_fingerprint: sha256:...

task_session_id: null
environment_session_id: null
session_status: matched | mismatched | not_applicable | not_evaluated
freshness_status: fresh | expired | not_applicable | not_evaluated
validation_status: passed | failed | not_evaluated
```

`recipe_claimed_fingerprint` comes from the recipe descriptor,
`companion_claimed_fingerprint` from the supplied companion's terminal
fingerprint field, and `computed_fingerprint` from independent canonicalization
of the full companion. All three remain distinct.

#### Validation-Context Artifact Descriptor

Unreferenced environment snapshots and general policy registries use:

```yaml
descriptor_kind: validation_artifact
artifact_id: ...
artifact_kind: environment_snapshot | planning_policy
schema: ...

companion_claimed_fingerprint: sha256:...
computed_fingerprint: sha256:...

task_session_id: null
environment_session_id: null
session_status: matched | mismatched | not_applicable | not_evaluated
freshness_status: fresh | expired | not_applicable | not_evaluated
validation_status: passed | failed | not_evaluated
```

These artifacts have no recipe-claimed fingerprint because they are not part of
recipe identity.

#### Registry Descriptor

`payload_schema_registry` and `capability_registry` use:

```yaml
descriptor_kind: registry
registry_id: payload_schema_registry | capability_registry
registry_kind: payload_schema | capability
schema: rook.payload_schema_registry:v1 |
        rook.environment_capability_registry:v1

companion_claimed_fingerprint: sha256:...
computed_fingerprint: sha256:...

registry_session_id: null
session_status: matched | mismatched | not_applicable | not_evaluated
freshness_status: fresh | expired | not_applicable | not_evaluated
validation_status: passed | failed | not_evaluated
```

The payload-schema registry has `registry_session_id: null` with
`session_status: not_applicable`. The capability registry records its supplied
session and compares it with the trusted validation-context session.

Descriptor discriminator combinations are closed:

| Descriptor | Stable identity | Exact schema | Companion fingerprint field |
|---|---|---|---|
| recipe authority `task_envelope` | `task_envelope` | `rook.planner_task_envelope:v1` | `artifact_fingerprint` |
| recipe or validation artifact `environment_snapshot` | `artifact_id` | `rook.environment_snapshot:v1` | `artifact_fingerprint` |
| recipe or validation artifact `planning_policy` | `artifact_id` | `rook.planning_policy:v1` | `artifact_fingerprint` |
| recipe authority `confirmation_receipt` | `artifact_id` | `rook.planner_assumption_confirmation_receipt:v1` | `receipt_fingerprint` |
| registry `payload_schema_registry` | `payload_schema_registry` | `rook.payload_schema_registry:v1` | `registry_fingerprint` |
| registry `capability_registry` | `capability_registry` | `rook.environment_capability_registry:v1` | `registry_fingerprint` |

`source_task` is the sole task-envelope descriptor. The task envelope and
confirmation receipt require `task_session_id`; environment snapshots require
`environment_session_id`; inapplicable session fields are explicit `null`.
Policy and confirmation expiry, environment freshness, and capability-registry
freshness derive from their companion fields at the trusted validation time.
No descriptor may select a different schema or claimed-fingerprint field for
its discriminator.

#### Vocabulary Descriptor

Every `vocabularies` entry uses:

```yaml
descriptor_kind: vocabulary
schema: ...
vocabulary_version: ...
recipe_binding_paths: []
recipe_claimed_fingerprint: null
companion_claimed_fingerprint: sha256:...
computed_fingerprint: sha256:...
entry_count: 0
validation_status: passed | failed | not_evaluated
```

`recipe_binding_paths` contains the exact RFC 6901 recipe JSON Pointers that bind
the shape, capability, or worker-slot vocabulary; it is empty for
validation-context-only vocabularies. `recipe_claimed_fingerprint` is non-null
exactly when that list is nonempty, and every bound path must claim the same
fingerprint.

The four descriptor discriminators have these stable identities and no other
identity rule:

| Descriptor kind | Stable identity |
|---|---|
| `recipe_authority` | `artifact_id` |
| `validation_artifact` | `artifact_id` |
| `registry` | `registry_id` |
| `vocabulary` | `(schema, vocabulary_version)` |

Stable identities are unique across their containing collection. Artifact IDs
remain globally unique across recipe-bound and validation-context artifact
descriptors. The two registry IDs are fixed singletons and cannot appear in an
artifact collection. Vocabulary identity must match one exact companion row in
Section 4.7.

The report structure is therefore:

```text
source_task
  one recipe-bound authority descriptor

authority_artifacts
  zero or more recipe-bound authority descriptors

validation_context_artifacts
  environment_snapshots: validation-context artifact descriptors
  policy_registries: validation-context artifact descriptors
  payload_schema_registry: one registry descriptor
  capability_registry: one registry descriptor

vocabularies
  exactly one descriptor for each required v1 vocabulary
```

Preflight guarantees the fixed `source_task`, singleton registry, and required
vocabulary descriptor shells. If their contents are malformed, constructors use
the fixed slot discriminator/identity, explicit nullable evidence fields, and a
failed or not-evaluated status. Recipe-declared variable authority companions
that are missing, extra, duplicated, kind-mismatched, or fingerprint-mismatched
remain `companion_artifacts` errors. A supplied variable-list item whose stable
identity cannot be recovered produces a path-addressed diagnostic and no
descriptor row; the complete item remains bound by
`validation_bundle_fingerprint`.

### 8.3 Validation-Context Fingerprint

`validation_context_fingerprint` is SHA-256 over this exact canonical
projection:

```yaml
schema: rook.planner_graph_recipe_validation_context_projection:v1

validator:
  program_id: lm9a.planner_graph_recipe:v1
  program_fingerprint: sha256:...
  implementation_version: lm9a.recipe_validator:v1
  ruleset_fingerprint: sha256:...
  canonicalization_version: rook.canonical_json:v1

validation_budget:
  budget_profile: rook.validation_budget:lm9a_v1
  limits_fingerprint: sha256:...

validation_bundle_input_payload_sha256: sha256:...
validation_bundle_fingerprint: sha256:...

bundle_assembler:
  profile_id: ...
  profile_fingerprint: sha256:...
  assembler_kind: trusted_host_ingress | deterministic_fixture
  assembler_id: ...
  assembler_version: ...
  implementation_fingerprint: sha256:...

evaluated_at: ...
trusted_clock_source: ...
task_session_id: ...
environment_session_id: null
capability_registry_session_id: ...

source_task:
  descriptor_kind: recipe_authority
  artifact_id: ...
  artifact_kind: ...
  schema: ...
  recipe_claimed_fingerprint: ...
  companion_claimed_fingerprint: ...
  computed_fingerprint: ...
  task_session_id: ...
  environment_session_id: null

authority_artifacts: []

validation_context_artifacts:
  environment_snapshots: []
  policy_registries: []
  payload_schema_registry:
    descriptor_kind: registry
    registry_id: payload_schema_registry
    registry_kind: payload_schema
    schema: rook.payload_schema_registry:v1
    companion_claimed_fingerprint: ...
    computed_fingerprint: ...
    registry_session_id: null
  capability_registry:
    descriptor_kind: registry
    registry_id: capability_registry
    registry_kind: capability
    schema: rook.environment_capability_registry:v1
    companion_claimed_fingerprint: ...
    computed_fingerprint: ...
    registry_session_id: ...

vocabularies:
  - descriptor_kind: vocabulary
    schema: ...
    vocabulary_version: ...
    recipe_binding_paths: []
    recipe_claimed_fingerprint: null
    companion_claimed_fingerprint: ...
    computed_fingerprint: ...
```

Authority-artifact projections contain the same discriminator, identity,
schema, three fingerprints, and session fields shown for `source_task`.
Validation-context artifact projections contain their discriminator and omit
`recipe_claimed_fingerprint`. Registry projections contain `descriptor_kind`,
`registry_id`, `registry_kind`, `schema`, both companion/computed fingerprints,
and `registry_session_id`. Vocabulary projections contain `descriptor_kind`,
`schema`, `vocabulary_version`, `recipe_binding_paths`, and all three applicable
fingerprints. The validator identity, budget profile/limits identity, raw
validation-bundle hash, canonical bundle fingerprint, and trusted invocation
assembler-profile identity and implementation fingerprint are copied exactly
from the report's sealed identity and invocation-context fields. The profile
comes from the host-issued carrier's opaque issuer binding, never the parsed
bundle. Observed budget consumption is report evidence but not part of the
validation-context projection.

The projection excludes derived descriptor fields `session_status`,
`freshness_status`, `validation_status`, and `entry_count`. It excludes the raw
recipe, recipe fingerprint, diagnostics, blockers, phase status, report
fingerprint, and `validation_context_fingerprint` itself. Companion content is
represented by claimed and computed content hashes rather than embedded again.

The projection copies the sealed program identity and all component validator
identity fields exactly from the report header. The projection uses the set
ordering in Section 9 and is canonicalized with
`rook.canonical_json:v1`. A `null` computed fingerprint caused by malformed
input remains an explicit `null`, so invalid contexts still receive stable
context identities when a conforming report can otherwise be issued.

Identical bundle bytes admitted through a different sealed assembler profile
preserve the raw bundle hash and canonical bundle fingerprint but move the
validation-context and report fingerprints. Principal identity is therefore
auditable without pretending it changes the bundle payload itself.

### 8.4 Valid And Compile-Ready

Both statuses are derived:

```text
valid = no error diagnostics

compile_ready =
  valid
  and no compile blockers
  and every phase in report_projection.required_for_compile_phases
      has status == passed
```

Diagnostics have closed severity values `error`, `warning`, and `information`.
Warnings and informational diagnostics do not affect `valid`. Each issue is
either a diagnostic or a compile blocker, never both.

For `lm9a.planner_graph_recipe:v1`, the sealed report projection owns this exact
set-like allowlist:

```text
schema
fingerprint
companion_artifacts
provenance
clause_graph
derived_facts
assumptions
unresolved_intent
shape
capabilities
worker_slots
```

The program seal validates these names against the phase manifest and
fingerprints the normalized allowlist as report-projection material. No phase
runner may alter it. A future phase is optional for compilation only when a
reviewed projection deliberately omits it; mere absence of a diagnostic or
blocker cannot make an unevaluated required phase compile-ready.

`compile_ready=true` means the validated contract may enter bounded intelligent
compile. It does not guarantee that compilation, semantic review, authorization,
execution, or verification will succeed.

Examples:

- stale or wrong-session claimed authority is invalid;
- hard policy prohibition may preserve an honest recipe as valid while making
  it not compile-ready;
- confirmation-required assumption is valid but blocked;
- unresolved intent is valid but blocked;
- trusted capability unavailability may be a blocker rather than an invalid
  recipe;
- malformed policy or authority artifacts invalidate validation context.

### 8.5 Phase Model

LM9A phases are immutable `PhaseSpec` entries inside the sealed validation
program. A spec names exact inputs, producers, output names, export types,
cardinalities, status-dependent output requirements, runner identity, and issue
permissions. There is no separately authored dependency table. The kernel
derives the DAG and report order from exact input bindings.

This table is the normative human-readable projection of the v1 phase manifest.
All named inputs and outputs have cardinality `exactly_one`. Bracketed statuses
are both the permitted and mandatory statuses for that output in v1; an output
on any other status is forbidden.

| Phase | `ordering_after` | Exact named inputs | Exact provided outputs |
|---|---|---|---|
| `schema` | none | `invocation.recipe_parse_evidence`; `program.recipe_schema` | `schema_evidence` `[passed, failed]`; `parsed_recipe` `[passed]` |
| `fingerprint` | `schema` | `schema.parsed_recipe`; `program.recipe_fingerprint_projection` | `fingerprint_evidence` `[passed, failed]` |
| `companion_artifacts` | `fingerprint` | `invocation.validation_bundle`; `program.companion_schemas`; `program.schema_evaluator_profiles` | `companion_evidence` `[passed, blocked, failed]`; `companion_index` `[passed, blocked]` |
| `provenance` | `companion_artifacts` | `schema.parsed_recipe`; `companion_artifacts.companion_index` | `recipe_semantic_index` `[passed, blocked]` |
| `clause_graph` | `provenance` | `schema.parsed_recipe`; `companion_artifacts.companion_index` | `clause_index` `[passed, blocked]` |
| `derived_facts` | `clause_graph` | `companion_artifacts.companion_index`; `provenance.recipe_semantic_index`; `clause_graph.clause_index` | `derived_fact_resolution` `[passed, blocked]` |
| `assumptions` | `derived_facts` | `schema.parsed_recipe`; `companion_artifacts.companion_index`; `provenance.recipe_semantic_index`; `clause_graph.clause_index`; `derived_facts.derived_fact_resolution` | `assumption_resolution` `[passed, blocked]` |
| `unresolved_intent` | `assumptions` | `companion_artifacts.companion_index`; `provenance.recipe_semantic_index`; `clause_graph.clause_index`; `assumptions.assumption_resolution` | `unresolved_intent_resolution` `[passed, blocked]` |
| `shape` | `unresolved_intent` | `companion_artifacts.companion_index`; `provenance.recipe_semantic_index`; `clause_graph.clause_index` | `shape_resolution` `[passed, blocked]` |
| `capabilities` | `shape` | `companion_artifacts.companion_index`; `provenance.recipe_semantic_index`; `clause_graph.clause_index`; `shape.shape_resolution` | `capability_resolution` `[passed, blocked]` |
| `worker_slots` | `capabilities` | `companion_artifacts.companion_index`; `provenance.recipe_semantic_index`; `clause_graph.clause_index`; `shape.shape_resolution` | `worker_slot_resolution` `[passed, blocked]` |

The manifest holds these as full `input_bindings` and `provided_outputs`, not as
strings parsed from this table. `schema` consumes kernel parse evidence because
bounded parsing occurs before semantic phases. `companion_artifacts` remains
independent of recipe schema validity. `fingerprint` and
`companion_artifacts` retain bounded evidence even when they diagnose a mismatch
and fail; semantic indexes are exposed only when their provider passed or
blocked.

The `ordering_after` chain fixes budget and evidence order but does not create
data authority or failure suppression. For example, a failed or not-evaluated
`fingerprint` reaches a terminal status and `companion_artifacts` still runs,
because the latter binds no fingerprint output.

A fingerprint mismatch therefore does not suppress independent companion
diagnostics. Recipe parse/schema failure likewise does not suppress
`companion_artifacts`. Both can fail in one report; phases requiring unavailable
indexes become `not_evaluated`. `provenance` cannot run without both a schema-
valid recipe and an accepted companion index.

`assumptions` binds `schema.parsed_recipe` directly because confirmation-subject
projection covers the complete canonical recipe; it cannot recover that input
through `RecipeSemanticIndex`. `shape` binds
`companion_artifacts.companion_index` directly because authority-vocabulary
identity, fingerprint, and entries are companion evidence; it cannot infer them
from prose or an index built for another phase.

There is deliberately no semantic `readiness` runner. `valid` and
`compile_ready` are deterministic report projections over accepted phase issues
under Section 8.4. Keeping that derivation in the report seal avoids a redundant
phase whose status would restate the same blocker ledger.

Each declared phase has one mechanically derived status:

```text
not_evaluated  at least one exact bound input is legitimately unavailable
failed         evaluated and an error diagnostic exists
blocked        evaluated without error, but a blocker exists
passed         evaluated with no errors or blockers
```

An output explicitly required on `blocked` remains available downstream. An
output absent because its provider failed or was not evaluated makes its
consumer `not_evaluated`. A passed or blocked provider that omits an output
required for that status is validator corruption and terminates with
`validator_integrity_failure`; it must never be normalized into downstream
`not_evaluated`. Within an evaluated phase, `failed` takes precedence over
`blocked`.

A missing task envelope or malformed authority artifact fails
`companion_artifacts`; phases bound to `companion_index` become
`not_evaluated`. A report with `valid=false` does not invent speculative
blockers from unevaluated phases.

All phase inputs, results, and outputs are transitively immutable values accepted
by export validators sealed into the program.
`CompanionIndex` and `RecipeSemanticIndex` may contain only immutable identities,
paths, tuples, and references to immutable owned JSON values. A frozen dataclass
containing a mutable mapping does not satisfy this contract.

Runners return only diagnostics, blockers, and named output values. They cannot
author phase status, dependencies, work counts, output types, or report fields.
The engine validates issue permissions, output names, cardinality, deep
immutability, and required-on-status rules before retaining a result.

Diagnostics use this closed shape:

```yaml
severity: error | warning | information
phase: ...
code: ...
subject_id: ...
path: ...
related_paths: []
message: ...
```

Compile blockers use this separate closed shape:

```yaml
phase: ...
code: ...
subject_id: ...
path: ...
related_paths: []
message: ...
```

Messages are bounded explanatory text, not the stable identity of an issue.
An evaluated phase containing only warning or informational diagnostics and no
blocker is `passed`.

## 9. Canonicalization And Fingerprints

`rook.canonical_json:v1` is normative:

```text
schema validation
-> schema-directed Unicode NFC and LF normalization
-> schema-defined set sorting using RFC 8785 UTF-16 code-unit comparison
-> exact RFC 8785 JSON Canonicalization Scheme serialization
-> UTF-8 bytes without BOM
-> SHA-256
```

Hash strings use lowercase hexadecimal with a `sha256:` prefix.

This is a new fingerprint regime for the LM9 artifact family. It intentionally
does not reuse the legacy `_fingerprint_normalized_contract` helper in
`plan_graph_workflow_contract.py`, whose `json.dumps(sort_keys=True,
ensure_ascii=True)` encoding and bare digest are not RFC 8785. LM9A must not
call, wrap, copy, or imitate that helper. No migration of existing LM4X, LM5, or
LM8 fingerprints is implied.

An LM9A implementation must use a vetted exact RFC 8785 implementation or a
conformance adapter proved against the RFC 8785 serialization samples and the
official JSON Canonicalization Scheme reference vectors. The proof suite covers
Unicode object-key ordering, control and non-ASCII string serialization,
number serialization in embedded schema documents, and rejection of invalid
Unicode input. Passing only ordinary ASCII fixtures is insufficient.

Rules:

- every schema-designated machine identifier, code, semantic key, vocabulary
  version, and Rook schema identifier matches
  `^[a-z0-9]+(?:[._:-][a-z0-9]+)*$` exactly;
- this machine grammar applies to all `*_id` fields, `semantic_key`, closed
  vocabulary codes, issuer and authority codes, and task, environment,
  registry, and receipt session identifiers;
- fingerprints, timestamps, JSON Pointers, prose, and externally defined
  implementation references use their own schemas and are not machine
  identifiers under this rule;
- semantic prose normalizes Unicode to NFC and line endings to LF;
- semantic prose rejects leading and trailing whitespace;
- interior spaces, punctuation, paragraph breaks, and line wrapping remain
  fingerprint-material;
- JSON Pointer strings and the property names they address are not Unicode-
  normalized because reference equality is exact;
- duplicate JSON object member names and parsed strings containing unpaired
  Unicode surrogates are invalid before canonicalization;
- no generic trimming or whitespace collapsing occurs;
- duplicate machine identities are rejected by exact ASCII string equality
  before sorting;
- ordering semantics are declared by schema, never inferred dynamically;
- `null`, absent, and explicit empty collections remain distinct;
- external artifacts appear through trusted fingerprints rather than embedded
  payloads.

Every string component in every set sort key compares as an unescaped sequence
of UTF-16 code units using the ordering defined by RFC 8785 Section 3.2.3. This
comparison occurs after schema-directed normalization. ASCII machine identities
therefore have the same identity and ordering bytes everywhere, while JSON
Pointers, diagnostic messages, `related_paths`, and other permitted Unicode
strings use the same UTF-16 comparison as RFC 8785 object keys. The exhaustive
v1 set-order table is:

Compound sort keys compare tuple fields from left to right; the first unequal
field determines order. Numeric rank fields compare by ascending integer value.
String fields use the UTF-16 comparison above. A list-valued tuple field compares
lexicographically from its first element using that element's declared
comparator; when one list is an exact prefix of the other, the shorter list
sorts first. `related_paths` is first canonicalized by sorting its RFC 6901
strings, then participates in the enclosing diagnostic or blocker tuple under
this list rule. No host-language tuple or list comparison semantics are
implicit.

| Collection | Canonical sort key |
|---|---|
| recipe and validation-bundle `authority_artifacts` | `artifact_id` |
| validation-context `environment_snapshots` and `policy_registries` | `artifact_id` |
| task/environment `value_bindings` | `binding_id` |
| payload-schema registry `entries` | `schema_id` |
| environment capability-registry `entries` | `capability_code` |
| every vocabulary `entries` | `code`; semantic-value schemas use `schema` |
| `requires`, `maintains`, and `invariants` | `clause_id` |
| nested `canonicalization` and `postconditions` | `clause_id` |
| every `source_refs`, `assumption_refs`, `derived_fact_refs`, `basis_refs`, policy-reference, derivation `input_refs`, and worker `input_refs` collection | semantic-reference key below |
| goal projection ID lists | referenced stable ID |
| `supports_clause_ids`, `applies_to_clause_ids`, `inherited_support_from`, and `affected_clause_ids` | clause ID |
| `assumptions` | `assumption_id` |
| assumption `affects` | materiality code |
| `derived_facts` | `derived_fact_id` |
| `unresolved_intent` | `intent_id` |
| unresolved permitted authority and outcome lists | closed enum code |
| shape `self`, `delegates`, and `prohibited` | `shape_id` |
| required-capability `entries` | `capability_id` |
| worker-slot `entries` | `worker_slot_id` |
| vocabulary allowed-section, delegate-kind, input-kind, output-schema, and clause-kind lists | closed code or schema string |
| capability-registry `implementation_refs` | implementation reference string |
| report `authority_artifacts` | `artifact_id` |
| report `validation_context_artifacts.environment_snapshots` | `artifact_id` |
| report `validation_context_artifacts.policy_registries` | `artifact_id` |
| report and validation-context projection `vocabularies` | `(schema, vocabulary_version)` |
| vocabulary descriptor `recipe_binding_paths` | exact RFC 6901 string |
| issue `related_paths` | exact RFC 6901 string |
| future review-bundle `required_clause_ids` | clause ID |

Policy `rules` is a map keyed by `rule_id`, not a set-like array. RFC 8785
object-key ordering applies. The report's payload-schema and capability-registry
descriptors are fixed singleton object fields identified by `registry_id`, not
set-like collections. Report `phases` uses the fixed phase order from Section
8.5 and is never dynamically sorted.

Semantic references sort by the following fixed variant rank and tuple:

| Rank | `kind` | Remaining tuple fields |
|---|---|---|
| 0 | `artifact_value` | `(artifact_id, json_pointer)` |
| 1 | `policy_rule` | `(artifact_id, json_pointer)` |
| 2 | `receipt` | `(artifact_id, receipt_id, receipt_fingerprint)` |
| 3 | `clause` | `(clause_id)` |
| 4 | `assumption` | `(assumption_id)` |
| 5 | `derived_fact` | `(derived_fact_id)` |
| 6 | `unresolved_intent` | `(intent_id)` |
| 7 | `shape` | `(shape_id)` |
| 8 | `capability` | `(capability_id)` |
| 9 | `worker_slot` | `(worker_slot_id)` |

Duplicate semantic-reference tuples within one collection are invalid before
sorting.

### 9.1 Numeric And Typed-Value Rules

Decimal semantic values use this exact string grammar:

```text
^-?(0|[1-9][0-9]*)(\.[0-9]+)?$
```

Leading `+`, exponent notation, leading integer zeros, a missing integer or
fractional part, and every negative-zero representation are invalid. Trailing
fractional zeros are permitted and remain fingerprint-material. Authorization,
range, equality, and derivation checks parse with exact decimal arithmetic:
`"2"`, `"2.0"`, and `"2.00"` compare as the same mathematical value while
retaining distinct fingerprints. Binary floating-point comparison is forbidden.

Every JSON integer in an LM9A recipe, report, or companion lies in the inclusive
interoperable range `-9007199254740991` through `9007199254740991`. Semantic
non-integer values use decimal strings; non-integer JSON numbers are forbidden
in LM9A product fields. Embedded registered JSON Schema documents are the sole
v1 exception and are serialized by the exact RFC 8785 implementation and its
number conformance tests.

For an assumption or derived fact, the validator computes
`typed_value_fingerprint` as SHA-256 over the complete normalized `typed_value`
object under `rook.canonical_json:v1`; schema, value, unit, unit-context
reference, and every other schema-permitted field are inside the fingerprint.
No typed-value unit or unit-context field may sit outside that object and
silently escape its identity. Assumption scope such as `affects` remains
separate recipe material covered by the recipe and confirmation-subject
fingerprints.

For a task or environment `value_bindings` entry, the fingerprint subject is
the closed object `{schema: value_schema, value: <exact resolved payload
value>}`. If a value is unit-sensitive, its registered resolved payload value
schema must contain the unit and unit-context information inside `value`; a
parallel unbound unit field is invalid. Confirmation receipts bind the exact
assumption `typed_value_fingerprint`; they do not recompute a smaller subset.

### 9.2 Final Ordering And Fingerprint Scope

Diagnostics sort by `(phase_rank, severity_rank, code, subject_id, path,
related_paths, message)`, where severity rank is `error`, `warning`, then
`information`. Compile blockers sort by `(phase_rank, code, subject_id, path,
related_paths, message)`. `phase_rank` is the fixed order in Section 8.5.

Any array not named in this table is ordered and remains fingerprint-material
in received order. Adding another set-like collection requires a new
canonicalization version; an implementation cannot infer set semantics.

The recipe fingerprint covers the complete normalized recipe except
`recipe_fingerprint` itself. It covers normalized clauses, nested clauses,
assumptions, derived facts, unresolved intent, shape, required capabilities,
worker slots, and every recipe-bound external fingerprint.

Validation-context fingerprints belong only in the validation report. A change
to provider availability, an unreferenced environment snapshot, or the set of
available Grasshopper implementations must not move semantic recipe identity.

The report fingerprint covers the complete normalized report except
`report_fingerprint` itself.

## 10. Future Compile And Review Constraints

This section constrains later architecture and is not implemented by LM9A.

### 10.1 Intelligent Compile Output

Bounded intelligent compile may:

- resolve available capabilities;
- choose representation under shape delegation;
- construct topology in inert compiled IR;
- derive exact verifier coverage;
- instantiate permitted worker slots;
- emit exact tool and support-dependency IR;
- return unsupported or ambiguous lowering diagnostics.

Every decision record carries bounded rationale and cites applicable clause,
assumption, source, capability, and shape identities. It never stores raw model
reasoning.

The compile evidence records compiler program identity, model/profile where
used, prompt/program version, request hash, output hash, and deterministic
validation bindings.

### 10.2 Structural Compile Validation

Deterministic compile-output validation asks whether the compilation artifact
is complete, well-formed, and traceable. It checks, among other rules:

- every material maintained clause has one explicit verification disposition;
- every executable verification disposition has at least one resolved,
  authorized
  `observe_maintained_truth` support dependency;
- every requirement has a legal resolution record;
- every invariant has preventive coverage;
- every operation traces to maintained truth and authorized capability;
- every worker artifact matches a declared slot and validated request;
- unsupported coverage never produces executable IR;
- no semantic clause is structurally omitted;
- no verifier adds typed thresholds or semantics absent from contract authority.

Structural validation detects structurally omitted coverage. The existence of a
coverage record does not prove its semantic judgment is correct.

### 10.3 Independent Semantic Evaluation

A future compiler may attest:

```text
supported
partially_supported
ambiguous
unsupported
```

That is a judgment, not proof. `partially_supported`, `ambiguous`, or
`unsupported` forbids executable IR. Even `supported` may require independent
review under policy.

`rook.compile_semantic_review_input_bundle:v1` is a content-addressed manifest
whose trusted immutable references resolve to complete payloads, not excerpts:

- recipe;
- task envelope;
- recipe-bound authority artifacts;
- recipe validation report;
- compile result;
- compile-output validation report;
- semantic coverage;
- exact rubric;
- exact required material clause IDs.

Missing, extra, duplicate, or fingerprint-mismatched content invalidates the
bundle. The evaluator invocation fingerprint covers the exact resolved bundle
and rendered evaluator request.

An independent model or human emits
`rook.compile_semantic_review_report:v1`, containing one review for every
required clause. Clause statuses are closed to `accepted`, `rejected`,
`ambiguous`, and `not_evaluated`. The report uses closed issue codes, bounded
rationale, an overall recommendation, and a report fingerprint. The
recommendation is evidence, not authority.

A trusted review gateway validates exact clause coverage, recommendation
consistency, evaluator independence, report identity, invocation identity,
policy, and artifact bindings. It then derives and authenticates
`rook.compile_semantic_review_receipt:v1`, whose decision is closed to
`accepted`, `rejected`, or `clarification_required`. The compiler, delegates,
evaluator, and workers cannot issue or amend the receipt.

The receipt binds the recipe, recipe validation report, compile result,
compile-output report, semantic coverage, review bundle, review report, rubric,
review policy, evaluator invocation, trusted issuer, decision, and time.

### 10.4 Final Authorization

Final executable-IR authorization separately asks whether the exact compiled
artifact may execute now. It verifies:

- the semantic-review receipt is authentic and accepted;
- every bound fingerprint still matches;
- review policy still applies;
- targets, sessions, capabilities, and mutation authority remain current;
- preventive invariant coverage is present;
- no reviewed artifact changed after review.

A missing, rejected, stale, forged, expired, or `clarification_required`
receipt forbids execution. The receipt is necessary evidence, never an
execution grant by itself.

The final verifier proves that compiled postconditions occurred. It cannot
independently prove that those postconditions faithfully represent original
intent; that is why semantic evaluation remains separate.

## 11. Deterministic Proof Fixtures

Fixture data demonstrates the generic contract. It does not define product
schema, capability vocabulary, shape vocabulary, validator branches, policy
machinery, or compiler interfaces.

### 11.1 Generic Fixture Rule

Any material semantic value absent from the task envelope but required for a
compile-ready fixture must appear as an explicit, authority-valid assumption.

Paired fixtures share every such assumption except their controlled variable.
The exact assumption list and values live only in fixture payloads and rubrics.

### 11.2 Radial Ready/Unresolved Pair

Both radial recipes use the same source request:

```text
Create a 10 x 10 array of boxes whose heights are lowest near the center
and rise with radial distance from the center.
```

The task envelope supplies only facts honestly captured by ingress, including:

- grid count X;
- grid count Y;
- element kind;
- radial height relationship.

The maintained radial clause cites all four facts. `100` elements is a
deterministic derived fact, not an assumption.

Both fixture variants share:

- task-envelope fingerprint;
- environment-snapshot fingerprint;
- policy-artifact fingerprint;
- vocabulary fingerprints;
- trusted deterministic validation time;
- shared authority-context fingerprint;
- every fixture-specific material assumption other than the controlled value;
- `worker_slots.entries: []`.

The ready assumption and unresolved entry both cite the same spacing policy
artifact and exact range rule. In the unresolved recipe that citation is
authorization context only and does not supply spacing.

The spacing policy says only:

```text
Planner may select any typed value within the authorized range.
```

It contains no exact default, preferred value, midpoint rule, favored candidate
list, or language implying that `2` is canonical.

#### Ready Variant

The ready recipe authors an explicit typed assumption:

```text
grid_spacing = 2 model units
```

One exact policy rule authorizes that semantic key, schema, unit context, task
scope, target scope, operation, and value range. The validator derives
`policy_auto`.

Expected result:

```text
valid = true
compile_ready = true
unresolved_intent = []
worker_slots.entries = []
```

#### Unresolved Variant

The unresolved recipe does not author a spacing value. It contains
`unresolved.grid_spacing` with the permitted resolution authority.

The policy range authorizes a future Planner selection but supplies no value.

Expected result:

```text
valid = true
compile_ready = false
worker request creation = forbidden
compiler request creation = forbidden
executable artifact creation = forbidden
```

The two recipe fingerprints and validation report fingerprints differ.

#### Pair Manifest

A test-only manifest, not a product artifact, controls fixture drift:

```yaml
controlled_semantic_key: grid_spacing
shared_authority_context_fingerprint: sha256:...

allowed_recipe_differences:
  - assumption.grid_spacing
  - unresolved.grid_spacing
  - clause references affected by grid_spacing
  - goal projection references affected by grid_spacing
  - recipe_fingerprint
```

Comparison operates by stable identities, never array positions. Any other
semantic difference fails the fixture proof.

`shared_authority_context_fingerprint` is the canonical test-only hash of the
task envelope, all supplied authority and validation-context artifact
fingerprints, vocabulary fingerprints, evaluated time, and trusted clock source.
It excludes either recipe payload and either validation report.

### 11.3 Non-Radial Control Fixture

The control request is:

```text
Create a document layer named "Analysis".
Do not modify existing geometry or existing layers.
```

This fixture exercises:

- user facts;
- one goal;
- maintained desired truth;
- invariant declaration and authority validation;
- one generic semantic capability;
- shape delegation;
- no assumptions;
- no unresolved intent;
- no workers.

LM9A does not provide preventive invariant enforcement. That remains a future
compile-output requirement.

Expected result:

```text
valid = true
compile_ready = true
assumptions = []
unresolved_intent = []
worker_slots.entries = []
```

This is not a second domain campaign. It proves that the same grammar and
validator accept a structurally different contract without radial-specific
logic.

### 11.4 Deterministic Validation Clock

Tests inject trusted validation time:

```yaml
bundle_assembler:
  profile_id: lm9a.fixture_assembler:v1
  profile_fingerprint: sha256:...
  assembler_kind: deterministic_fixture
  assembler_id: lm9a.fixture_assembler
  assembler_version: v1
  implementation_fingerprint: sha256:...

validation_context:
  evaluated_at: 2026-07-12T12:00:00Z
  trusted_clock_source: deterministic_fixture
  task_session_id: fixture-task-session
  environment_session_id: fixture-environment-session
  capability_registry_session_id: fixture-capability-session
```

Production later uses a trusted clock. Evaluation time and clock source are
recorded and included in the validation-context fingerprint. Both radial
reports use the same fixed context.

### 11.5 Focused Positive Conformance Fixtures

Two additional model-free fixtures prevent rejection-only validator coverage.
They are focused contract fixtures and mandatory conformance-campaign cases, but
not additional user-domain scenarios.

The worker-slot conformance fixture declares one inert
`author_formula_realization` slot, its exact matching
`instantiate_worker_slot` shape delegate, one allowed output schema, valid
declared inputs, and nonempty maintained-clause support. Validation must return
`valid=true` and `compile_ready=true`, and must not instantiate a request, invoke
a worker, or emit worker output. This proves the positive shape-to-slot link,
slot-code output allowlist, input-kind, and support-clause paths.

The confirmation conformance fixture contains one otherwise valid material
assumption whose pre-receipt authorization outcome is
`confirmation_required`. A trusted, unexpired, same-session confirmation
receipt binds the exact task envelope, assumption ID, complete typed-value
fingerprint, and recomputed confirmation-subject fingerprint. Validation must
derive `confirmed`, return `valid=true` and `compile_ready=true`, and emit no
compiler, worker, or executable artifact.

Both fixtures use the deterministic validation clock and closed generic
vocabularies. Neither fixture adds a model, worker execution, confirmation UI,
compiler, or runtime behavior to LM9A.

### 11.6 Sealed-Program Budget Feasibility Campaign

LM9A-Semantics publishes one
`rook.validation_conformance_campaign:v1` under the kernel contract. Its
`campaign_id` is `lm9a.planner_graph_recipe:conformance_v1`, and it binds one
exact sealed semantic `program_fingerprint`, one required release-owned gate-
profile fingerprint, and one expanded content-addressed required-case set. The
campaign cannot name or select a gate implementation. Trusted release
composition independently supplies the `SealedConformanceGateProfile`; the
campaign binding is checked by that already selected gate.

The required set contains exactly:

- one `core_schema_positive:<schema_id>` case for every schema entry in the
  sealed program whose evaluator profile is `lm9a_core_v1`; and
- these five semantic-fixture case IDs:

```text
semantic_fixture:radial_ready
semantic_fixture:radial_unresolved
semantic_fixture:layer_control
semantic_fixture:confirmed_assumption
semantic_fixture:worker_slot_declared
```

The core-schema mapping is evaluated once against the already sealed program
manifest, not through source-tree or test discovery. Every core case binds one
complete positive instance and immutable content reference. Every semantic case
binds one immutable fixture manifest containing the exact raw recipe hash, raw
validation-bundle hash, expected result/status claims, content references, and
the exact `lm9a.fixture_assembler:v1` sealed profile fingerprint from Section
11.4. Each uses the kernel's closed
`rook.validation_conformance_fixture:v1` shape. All five required LM9A semantic
fixtures expect `result_kind: published_report`; a control failure cannot satisfy
their release cases. Each case and the aggregate campaign receive their own canonical
fingerprints under the kernel schema.

The exact case count is therefore `sealed_core_schema_count + 5`. The campaign's
`required_case_set_fingerprint` covers the sorted exact case-ID/fingerprint
pairs, and trusted release composition supplies that immutable campaign input
independently of the eventual report. Omitting a core schema, omitting any named
fixture, discovering an extra test file, or executing a case twice cannot
silently redefine the campaign. It either changes the campaign fingerprint
before execution or appears as missing, extra, duplicate, or mismatched evidence
in
`rook.validation_conformance_report:v1`.

The trusted conformance gate records every schema evaluation row defined by the
kernel, including complete-schema node count, exact instance-root node count,
checked product, and aggregate reservation. Every core-schema instance must fit
its applicable per-evaluation bound, and every named fixture invocation must fit
the shared 16,000,000-unit schema-shape cap.

This requirement does not promise that every maximum-size syntactically
admissible input succeeds; aggregate budget rejection remains valid. It proves
that the actual LM9A program and mandatory conformance campaign are usable.
Changing a core schema, fixture, or fixture assembler invalidates prior release
evidence. A changed case that exceeds either cap fails the release gate; it does
not justify silently increasing the profile.

LM9A deployment requires one aggregate
`rook.validation_conformance_report:v1` that resolves this exact campaign and
program, recomputes the campaign and required-case-set fingerprints, matches the
independently supplied campaign input, binds the independently supplied sealed
gate profile, satisfies `campaign_integrity`, contains exactly one matching row
per required case with no extras, and derives `decision=passed`. The schema may
retain duplicate indexed rows in a failed report; exact-once is a passing
completeness condition. Individually passing rows, caller-supplied report JSON,
an invocation failure, or an incomplete report are not deployment evidence.

## 12. Deterministic Proof Targets

### 12.1 Positive Proofs

LM9A must prove:

- canonical recipe and report payloads validate under closed schemas;
- claimed and independently computed fingerprints match;
- exact RFC 8785 and JSON Canonicalization Scheme reference vectors pass,
  including non-ASCII key ordering and embedded-schema number serialization;
- LM9A fingerprints use the `sha256:` exact-JCS regime and never call or imitate
  the legacy `_fingerprint_normalized_contract` helper;
- canonicalization is deterministic across semantically set-ordered input;
- compound diagnostic and blocker keys compare left-to-right, with
  `related_paths` using deterministic lexicographic and shorter-prefix-first
  ordering across runtimes;
- raw input and normalized payload hashes remain distinct;
- one sealed program manifest and its exact immutable runtime bindings produce
  one program fingerprint; changing any schema, profile, phase binding, runner,
  issue vocabulary, export validator, report projection, budget, input binding,
  or ordering edge moves that fingerprint;
- an unsealed builder, mutable registry, or missing/extra runtime binding cannot
  enter validation, and replacing a registry after seal cannot change the
  callable already selected for an invocation;
- both underlying artifacts enter as raw bytes and no mutable caller object
  graph can enter semantic validation;
- the recipe bytes are untrusted Planner output, while only trusted host ingress
  or one sealed deterministic fixture assembler profile may issue the validation-
  bundle carrier; plain profile JSON, a matching fingerprint, and bundle content
  cannot forge the issuer capability;
- sealed assembler profiles reject a wrong program, clock source, assembler kind,
  or profile fingerprint before semantic evidence is produced;
- a simulated public endpoint cannot promote client-selected bundle bytes or a
  self-asserted assembler descriptor into authority context;
- byte caps are checked before copying or hashing either input; exact-cap inputs
  are hashed, while any over-cap admission failure reports bounded lengths and
  `null` raw hashes;
- every exact and limit-plus-one kernel budget boundary is proven by the kernel
  suite before LM9A semantic tests run;
- local admitted-recipe depth/width/token/number failures produce schema
  evidence, while shared node/string/parser-work exhaustion produces a combined
  preflight invocation failure even when the recipe crosses the limit;
- each registered core schema positive instance and all five named semantic
  fixture cases record schema-shape units against the exact
  program/case/assembler-profile fingerprints and pass the sealed-program
  release gate;
- the release-owned sealed gate profile is supplied independently, and the
  campaign's required-profile binding cannot select its own certifier;
- the content-addressed campaign binds the complete mandatory case set, and one
  passing aggregate report proves one matching row per case, no extras or
  duplicates, matching gate/program/campaign identities, and `decision=passed`;
- malformed or identity-inconsistent campaigns produce only the bounded gate
  invocation failure, while constructable program/profile/coverage mismatches
  produce failed aggregate reports with zero case rows;
- unavailable case content produces zero schema-attempt rows, reservation
  rejection records before/null-after accounting without invoking the evaluator,
  and completed reservations record exact nonrefunded totals;
- report sealing reserves one fixed fingerprinted allowance, runners cannot
  author work counts, and repeated sealing does not change the frozen budget
  receipt;
- the closed payload schema profile accepts the required structural fixtures and
  rejects forbidden keywords, remote/dynamic references, cycles, and every
  static complexity-limit excess before evaluation;
- all phase inputs, semantic indexes, phase outputs, and report inputs are
  transitively immutable;
- attempted mutation through both `CompanionIndex` and `RecipeSemanticIndex`
  cannot alter the value observed by a later phase;
- identical validation-bundle object members in a different source order move
  only the raw bundle hash, not the canonical bundle fingerprint;
- malformed recipe bytes with otherwise valid companion shells still evaluate
  `companion_artifacts`, including the combined recipe/companion failure case;
- a schema-failed recipe leaves `provenance=not_evaluated`;
- the exact named phase bindings derive the execution DAG with no second
  dependency map;
- `assumptions` directly binds `schema.parsed_recipe`, and `shape` directly binds
  `companion_artifacts.companion_index`;
- a passed or blocked provider supplies every output required for that status;
  omission, extra output, wrong cardinality, wrong type, or mutable output
  produces `validator_integrity_failure`, never ordinary downstream
  `not_evaluated`;
- every report companion descriptor records its closed stable identity plus
  claimed and independently computed fingerprints;
- the validation-context fingerprint recomputes from the exact Section 8.3
  projection and is deterministic under reordered set-like descriptors;
- source pointers resolve against exact companion payloads;
- every artifact-value reference resolves through exactly one payload-relative
  authority binding;
- fixture payloads validate through the supplied payload-schema registry rather
  than production validator branches;
- complete typed-value fingerprints move when value, unit, or unit-context
  material changes;
- canonical decimal strings compare by exact decimal value while distinct valid
  spellings such as `"2"` and `"2.0"` remain fingerprint-distinct;
- derived element count recomputes exactly;
- the ready radial recipe is `valid=true`, `compile_ready=true`;
- the unresolved radial recipe is `valid=true`, `compile_ready=false`;
- both radial reports are deterministic under the same fixed context;
- the pair differs only by the stable-ID allowlist;
- the non-radial control is `valid=true`, `compile_ready=true`;
- the radial pair and non-radial campaign fixture remain workerless;
- the focused worker-slot fixture validates one permitted, bidirectionally
  linked inert slot as `valid=true`, `compile_ready=true` without creating a
  worker request;
- the focused confirmation fixture recomputes the subject fingerprint, validates
  the trusted receipt, derives `confirmed`, and reaches `compile_ready=true`;
- every phase in the report projection's exact required-for-compile set is
  `passed` for each compile-ready fixture;
- adding an eligible confirmation reference and its exact receipt descriptor
  changes the recipe fingerprint but leaves the confirmation-subject fingerprint
  unchanged, while changing semantic or cited-policy material moves both;
- no compiler, worker, tool, or executable artifact is emitted by validation.

### 12.2 Negative Proofs

Focused negative fixtures cover at least:

- unknown top-level and nested properties;
- invalid UTF-8 recipe bytes and UTF-8 BOM input;
- exact/over-limit recipe and validation-bundle byte, container-depth, width,
  node, decoded-string, reference, issue, work, and number-token boundaries;
- an over-cap raw byte argument producing a preflight invocation failure without
  scanning, copying, or hashing either input;
- numeric tokens that overflow to non-finite host floats and integer tokens
  that would exceed host conversion limits;
- validation-bundle non-finite numbers and integers outside the finite JCS
  domain;
- wide shallow, deep narrow, and aggregate string/reference/work amplification
  inputs;
- a missing or wrong-container mandatory report shell producing a preflight
  invocation failure, including when recipe bytes are independently malformed;
- missing or malformed trusted validation context producing a typed invocation
  failure rather than a partial validation report;
- non-ASCII, uppercase, whitespace-bearing, or malformed machine identities,
  codes, and semantic keys;
- duplicate stable IDs before sorting;
- dangling, malformed, stale, wrong-schema, wrong-session, and fingerprint-
  mismatched source references;
- artifact-value pointers missing a binding, matching duplicate binding
  pointers, or resolving outside the companion payload;
- empty semantic-reference pointers, URI-fragment pointers, malformed RFC 6901
  escapes, and attempted Unicode normalization that changes exact pointer or
  property-name identity;
- duplicate JSON object member names and escaped unpaired Unicode surrogates;
- missing, duplicate, fingerprint-mismatched, remote-reference, or wrong-dialect
  payload-schema registry entries;
- embedded payload schemas using dynamic references, retrieval identifiers,
  regex/format callbacks, combinators, custom keywords, cyclic/deep local
  references, or excessive schema/instance complexity;
- unsealed validation programs, manifest/runtime binding mismatch, duplicate
  phase input/output names, dataflow cycles, and producer/consumer type or
  cardinality mismatch;
- phase runners returning undeclared, duplicate, missing-required, mutable,
  wrong-typed, or wrong-cardinality outputs;
- missing or extra recipe-declared variable descriptors, duplicate report
  descriptor identities, and descriptor/companion kind disagreement;
- mismatch among recipe-claimed, companion-claimed, and computed companion
  fingerprints, including a registry or vocabulary mismatch;
- validation-context fingerprint mismatch and context-fingerprint movement when
  the validation-bundle fingerprint, sealed bundle-assembler profile, trusted
  validation time, session identity, registry identity, registry
  content, vocabulary content, validator ruleset, canonicalization version, or
  companion fingerprint evidence changes;
- conformance evidence with an omitted, extra, duplicated, or case-fingerprint-
  mismatched row, a mismatched required-case-set fingerprint, a wrong gate
  profile/implementation binding, a caller-supplied aggregate report, or a
  non-passing aggregate decision;
- a campaign attempting to nominate a gate implementation, an unsealed or
  runtime-mismatched gate profile, every pre-report invocation-failure code, and
  any invocation failure that incorrectly emits a report/result capability;
- case content/fingerprint failures that emit schema-attempt rows, reservation
  rejection that claims evaluator invocation or completed reservation, and
  completed/evaluator-failed attempts with inconsistent aggregate equations;
- source coverage borrowed from siblings, goal, or arbitrary graph reachability;
- invalid goal projections;
- orphan requirements;
- material typed values without authority;
- deterministically detectable statement/typed-value mismatch;
- incorrect or unsupported derived facts;
- assumption conflicting with task facts or policy;
- no policy match, multiple policy matches, exact prohibition, and wrong unit
  context;
- confirmation receipt mismatch, expiry, revocation, and wrong task session;
- missing, duplicate, wrong-assumption, shared, or unselected confirmation-
  receipt descriptors in the confirmation-subject projection;
- gratuitous confirmation references on `policy_auto` and every other
  non-confirmable derived authorization outcome;
- malformed decimal strings, negative zero, unsafe JSON integers, non-integer
  JSON numbers in product fields, and binary-float comparison drift;
- unresolved value coexisting with an assumption for the same semantic key;
- unresolved value already supplied by the task envelope;
- duplicate unresolved semantic keys;
- unknown shape code, invalid overlaps, and invalid delegate kind;
- unknown capability code and invalid clause category;
- unknown worker slot code, disallowed output schema, or undeclared input;
- missing, duplicate, one-way, or mismatched shape-to-worker-slot links;
- target-selection or privileged-authority receipt artifacts rejected as
  deferred v1 artifact kinds;
- recipe fingerprint mismatch;
- malformed input with `computed_recipe_fingerprint: null`;
- deterministic phase `not_evaluated` propagation;
- a required-for-compile phase that is `not_evaluated` with no issue still
  forcing `compile_ready=false`, while an explicitly optional synthetic phase
  does not affect the result;
- the same issue appearing in both diagnostics and blockers;
- value `2` produces `confirmation_required`, `valid=true`, and
  `compile_ready=false` when no applicable allow rule or prohibition remains;
- value `2` produces `policy_prohibited`, `valid=true`, and
  `compile_ready=false` when an applicable prohibition covers it;
- any unapproved semantic delta between the radial fixture pair.

### 12.3 Anti-Overfitting Proof

No production LM9A module may contain radial, box-array, grid-spacing,
height-falloff, or other fixture-specific validation logic.

Fixture terminology is permitted only in fixture payloads, test-only pair
manifests, scenario rubrics, tests, and documentation. Product schemas,
validator branches, generic vocabularies, policy machinery, and future compiler
interfaces remain domain-neutral.

The implementation plan must include a deterministic source guard or equivalent
structural proof for this boundary. The guard should target production LM9A
modules rather than documentation or fixture files.

## 13. Relationship To Existing Rook Artifacts

### `PlannerWorkerContractRequest:v1`

Unchanged. It remains a worker-oriented request artifact. A graph recipe may be
entirely workerless and therefore does not inherit it.

### `RookWorkflowContract`

Unchanged. It is operational workflow structure below future compilation. The
recipe must not pretend semantic intent is already executable workflow IR.

### `TaskSpec`

Unchanged. `TaskSpec` remains macro orchestration context. An optional future
worker request or compiled workflow may appear beneath macro orchestration, but
LM9A does not create a `TaskSpec` from a worker slot.

### `workflow_validate`

Unchanged. LM9A introduces recipe validation above future compiled workflow and
tool artifacts. Later compilation may feed existing or new operational
validators, but recipe validation does not call `workflow_validate` or claim
LM5X routability.

## 14. Interpretation

If LM9A deterministic tests pass, the supported claim is:

> Rook has one generic, fingerprinted Planner semantic-contract surface whose
> deterministic validator can distinguish an authority-valid, compile-ready
> workerless recipe from an equally valid recipe that honestly leaves material
> intent unresolved, while also accepting a structurally different non-radial
> contract without fixture-specific production logic.

LM9A does not prove:

- Planner-model authorship;
- prose entailment or semantic fidelity;
- bounded intelligent compilation;
- compiler-model competence;
- semantic review quality;
- executable IR correctness or authorization;
- Grasshopper graph construction;
- `gh_edit` readiness;
- worker competence;
- live execution or verification;
- repeatability of any model path.

The immediate later sequence is expected to be:

```text
LM9A deterministic recipe surface and validator
-> offline bounded intelligent compile probe with recorded/fake outputs
-> deterministic compile-output structural validation
-> independent semantic evaluation evidence
-> managed gh_edit readiness migration
-> first separately reviewed live compiled execution
```

Each arrow requires its own reviewed spec and must preserve the authority chain
defined here.
