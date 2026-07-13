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
implementation scope.

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

LM9A implements or specifies for deterministic implementation:

- `rook.planner_graph_recipe:v1`;
- `rook.planner_graph_recipe_validation_report:v1`;
- deterministic canonicalization and fingerprinting;
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
deterministic task envelope
+ declared authority companions
+ validation-context companions
+ raw recipe bytes
-> recipe validator
-> validation report
```

When later compilation exists, its output receives a separate fingerprint that
links to the recipe fingerprint. A compiled fingerprint never replaces or
redefines semantic recipe identity.

The boot skill or task-envelope hook remains the mandatory mechanical ingress
gate. LM9A consumes a deterministic task envelope; boot routing is outside this
slice.

### 4.1 Closed Validation Input

Validation is invoked with exact raw recipe bytes plus one closed companion
object:

```yaml
schema: rook.planner_graph_recipe_validation_input:v1

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

The raw recipe bytes are a separate required invocation argument so their hash
is not changed by embedding them in another JSON artifact. The validation-input
object and every companion payload are supplied in full, not by excerpt.

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

Schema documents are supplied in full and validated against the exact declared
JSON Schema dialect. Remote references, network resolution, custom executable
keywords, and schemas absent from the registry are forbidden. Local `$ref`
targets must remain within the same schema document. The registry lets fixture
and future product payload schemas remain domain-specific data without
hardcoding them into the LM9A validator.

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

The pre-confirmation subject fingerprint is computed over the canonical recipe
excluding `recipe_fingerprint`, with every required `confirmation_ref` value
replaced by `null` rather than removed.

An assumption confirmation receipt is issued only by a trusted mechanical
gateway and binds:

- receipt and issuer identity;
- task-envelope fingerprint;
- confirmation-subject fingerprint;
- assumption ID;
- exact typed-value fingerprint, unit, and scope;
- user/task session;
- decision, issue time, expiry, and receipt fingerprint.

The Planner and compile delegates cannot issue receipts. Rejected, expired,
revoked, wrong-session, stale-value, or fingerprint-mismatched receipts never
make a recipe compile-ready. Changing semantics or an authority artifact
invalidates prior receipts; changing only confirmation-reference values does
not move the subject fingerprint.

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

`worker_slots.entries: []` absolutely forbids worker request creation. Every
canonical LM9A proof fixture is workerless.

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

The deterministic report answers two separate questions:

```text
Is this an honest, valid semantic contract?
Is it presently authorized and sufficiently resolved to enter compilation?
```

```yaml
schema: rook.planner_graph_recipe_validation_report:v1

input_payload_sha256: sha256:...
claimed_recipe_fingerprint: sha256:...
computed_recipe_fingerprint: sha256:...

validator:
  implementation_version: lm9a.recipe_validator:v1
  ruleset_fingerprint: sha256:...
  canonicalization_version: rook.canonical_json:v1

validation_context:
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

`input_payload_sha256` is the hash of exact bytes received before parsing. The
validation ingress must retain those bytes. A conforming LM9A validation report
cannot be issued when ingress cannot supply the raw bytes.

Malformed input may still have an input hash while
`computed_recipe_fingerprint` is `null`; `claimed_recipe_fingerprint` may also
be `null` when parsing cannot recover it. Claimed and independently computed
fingerprints remain separate.

Validator rules, canonicalization, and every vocabulary are identified by
fingerprint as well as version. Exact input payloads without exact validation
rules are not replayable evidence.

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

`recipe_binding_paths` contains the normalized recipe JSON Pointers that bind
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

Missing required descriptors, extra descriptors, duplicate stable identities,
descriptor/companion kind disagreement, or a claimed/computed fingerprint
mismatch is a `companion_artifacts` error.

### 8.3 Validation-Context Fingerprint

`validation_context_fingerprint` is SHA-256 over this exact canonical
projection:

```yaml
schema: rook.planner_graph_recipe_validation_context_projection:v1

validator:
  implementation_version: lm9a.recipe_validator:v1
  ruleset_fingerprint: sha256:...
  canonicalization_version: rook.canonical_json:v1

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
fingerprints. The validator identity is copied exactly from the report header.

The projection excludes derived descriptor fields `session_status`,
`freshness_status`, `validation_status`, and `entry_count`. It excludes the raw
recipe, recipe fingerprint, diagnostics, blockers, phase status, report
fingerprint, and `validation_context_fingerprint` itself. Companion content is
represented by claimed and computed content hashes rather than embedded again.

The projection uses the set ordering in Section 9 and is canonicalized with
`rook.canonical_json:v1`. A `null` computed fingerprint caused by malformed
input remains an explicit `null`, so invalid contexts still receive stable
context identities when a conforming report can otherwise be issued.

### 8.4 Valid And Compile-Ready

Both statuses are derived:

```text
valid = no error diagnostics

compile_ready =
  valid
  and no compile blockers
```

Diagnostics have closed severity values `error`, `warning`, and `information`.
Warnings and informational diagnostics do not affect `valid`. Each issue is
either a diagnostic or a compile blocker, never both.

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

Required phases and their exact dependencies are:

| Phase | Dependencies |
|---|---|
| `schema` | none; this phase includes JSON parsing and schema validation |
| `fingerprint` | `schema` |
| `companion_artifacts` | `schema` |
| `provenance` | `companion_artifacts` |
| `clause_graph` | `schema`, `companion_artifacts` |
| `derived_facts` | `companion_artifacts`, `provenance`, `clause_graph` |
| `assumptions` | `companion_artifacts`, `provenance`, `clause_graph` |
| `unresolved_intent` | `companion_artifacts`, `provenance`, `clause_graph`, `assumptions` |
| `shape` | `companion_artifacts`, `clause_graph` |
| `capabilities` | `companion_artifacts`, `clause_graph`, `shape` |
| `worker_slots` | `companion_artifacts`, `clause_graph`, `shape` |
| `readiness` | every preceding phase |

A fingerprint mismatch does not suppress independent structural diagnostics in
other branches of the graph. It does prevent `readiness` from passing.

Each phase has one mechanically derived status:

```text
not_evaluated  at least one dependency is failed or not_evaluated
failed         evaluated and an error diagnostic exists
blocked        evaluated without error, but a blocker exists
passed         evaluated with no errors or blockers
```

`blocked` dependencies do not suppress downstream evaluation. Only `failed` and
`not_evaluated` dependencies do. Within an evaluated phase, `failed` takes
precedence over `blocked`. The `readiness` phase is `blocked` when any compile
blocker exists anywhere in the report; it does not duplicate that blocker.

A missing task envelope or malformed authority artifact fails
`companion_artifacts`; dependent phases become `not_evaluated` according to the
table. A report with `valid=false` does not invent speculative blockers from
unevaluated phases.

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
schema validation and schema-defined set sorting
-> Unicode NFC and LF normalization
-> RFC 8785-compatible JSON serialization
-> UTF-8 bytes without BOM
-> SHA-256
```

Hash strings use lowercase hexadecimal with a `sha256:` prefix.

Rules:

- identifiers, paths, codes, and schema references reject surrounding
  whitespace;
- semantic prose normalizes Unicode to NFC and line endings to LF;
- semantic prose rejects leading and trailing whitespace;
- interior spaces, punctuation, paragraph breaks, and line wrapping remain
  fingerprint-material;
- no generic trimming or whitespace collapsing occurs;
- duplicate identities are rejected before sorting;
- ordering semantics are declared by schema, never inferred dynamically;
- `null`, absent, and explicit empty collections remain distinct;
- external artifacts appear through trusted fingerprints rather than embedded
  payloads.

String components in sort keys compare by Unicode scalar value after NFC
normalization. The exhaustive v1 set-order table is:

| Collection | Canonical sort key |
|---|---|
| recipe and validation-input `authority_artifacts` | `artifact_id` |
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
| vocabulary descriptor `recipe_binding_paths` | normalized JSON Pointer |
| issue `related_paths` | normalized JSON Pointer |
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

## 12. Deterministic Proof Targets

### 12.1 Positive Proofs

LM9A must prove:

- canonical recipe and report payloads validate under closed schemas;
- claimed and independently computed fingerprints match;
- canonicalization is deterministic across semantically set-ordered input;
- raw input and normalized payload hashes remain distinct;
- every report companion descriptor records its closed stable identity plus
  claimed and independently computed fingerprints;
- the validation-context fingerprint recomputes from the exact Section 8.3
  projection and is deterministic under reordered set-like descriptors;
- source pointers resolve against exact companion payloads;
- every artifact-value reference resolves through exactly one payload-relative
  authority binding;
- fixture payloads validate through the supplied payload-schema registry rather
  than production validator branches;
- derived element count recomputes exactly;
- the ready radial recipe is `valid=true`, `compile_ready=true`;
- the unresolved radial recipe is `valid=true`, `compile_ready=false`;
- both radial reports are deterministic under the same fixed context;
- the pair differs only by the stable-ID allowlist;
- the non-radial control is `valid=true`, `compile_ready=true`;
- every canonical fixture is workerless;
- no compiler, worker, tool, or executable artifact is emitted by validation.

### 12.2 Negative Proofs

Focused negative fixtures cover at least:

- unknown top-level and nested properties;
- duplicate stable IDs before sorting;
- dangling, malformed, stale, wrong-schema, wrong-session, and fingerprint-
  mismatched source references;
- artifact-value pointers missing a binding, matching duplicate binding
  pointers, or resolving outside the companion payload;
- missing, duplicate, fingerprint-mismatched, remote-reference, or wrong-dialect
  payload-schema registry entries;
- missing or extra required report descriptors, duplicate report descriptor
  identities, and descriptor/companion kind disagreement;
- mismatch among recipe-claimed, companion-claimed, and computed companion
  fingerprints, including a registry or vocabulary mismatch;
- validation-context fingerprint mismatch and context-fingerprint movement when
  trusted validation time, session identity, registry identity, registry
  content, vocabulary content, validator ruleset, canonicalization version, or
  companion fingerprint evidence changes;
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
