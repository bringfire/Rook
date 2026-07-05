# LM5Z - Worker-Visible Source Routing Contract Design

- **Date:** 2026-07-05
- **Status:** Draft for review
- **Slice:** LM5Z
- **Type:** Design/spec artifact only

## 1. Purpose

LM5Y joined the acceptance-criteria evidence path into the probe runtime:

```text
real fixture objects -> LM5X extraction -> LM5W assembly -> legacy worker-visible projection
```

The post-merge LM5Y run preserved the LM5U behavior:

```text
absent: 0/5 action_request
present_v3: 5/5 action_request
```

and did not leak hidden repair answers or LM5W internal metadata.

The next missing seam is upstream declaration. LM5Z defines a standalone,
node-scoped source-routing declaration that tells validation and extraction
which upstream facts may become worker-visible for each worker node. It does
not contain acceptance-criteria prose, hidden answers, or model-facing
instructions.

Core doctrine:

```text
Contract declares what source facts a worker node may see.
Extractor resolves those facts.
Assembler turns resolved facts into worker-visible criteria/evidence.
```

## 2. Scope

LM5Z is design/spec only.

In scope:

- Define a standalone worker-visible source-routing artifact shape.
- Define v1 source classes, purposes, route fields, and validation rules.
- Define static/routability validation diagnostics.
- Define forbidden source-path policy.
- Include exactly two worked examples:
  - the proven LM5U repair fixture route set
  - a Grasshopper solve/error expectations pressure example
- Recommend the next implementation slice as a deterministic routing validator
  prototype.

Out of scope:

- No code.
- No tests.
- No live probe.
- No production behavior change.
- No `RookWorkflowContract` schema change.
- No Planner/compiler integration.
- No verifier implementation change.
- No worker-visible evidence packet change.
- No prompt, parser, transport, model, LM5R, LM5G, or LM5J changes.
- No hidden bind params, desired replacement code, or `PROBE_REPAIR_CODE` in
  worker-visible context.
- No LM5 proof-ladder capstone or north-star addendum.

## 3. Design Line

LM5Z defines source routing, not criteria text.

The routing artifact may say:

```text
repair_same_component may receive pin_contract from
create_script.initial_execution_params.pins_out
```

It must not say:

```text
Output A must be assigned.
```

That preserves ownership:

- Planner/compiler routes authority.
- Verifier owns expected outcomes.
- Receipts own observed failures.
- KG/conventions provide provenance-backed conventions.
- Source extractors resolve selected facts.
- Assemblers own worker-facing criterion text.
- Workers act only from the assembled visible surface.

LM5Z explicitly rejects:

```text
Put all criteria prose in RookWorkflowContract.
```

## 4. Artifact Shape

LM5Z specifies a standalone design artifact:

```yaml
schema: rook.worker_visible_source_routing:v1
routes:
  - node_id: repair_same_component
    visible_sources:
      - route_id: repair_pin_contract
        source_class: pin_contract
        source_path: create_script.initial_execution_params.pins_out
        purpose: acceptance_criteria
        required: true
```

The artifact is standalone in LM5Z. A future implementation may embed it in, or
reference it from, a workflow/task contract. LM5Z does not decide storage.

Top-level validation:

- `schema` is required.
- `schema` must equal `rook.worker_visible_source_routing:v1`.
- `routes` must be a list.
- Each route entry must have `node_id`.
- `node_id` must be unique across `routes`.
- `visible_sources` must be a non-empty list.

List form is deliberate: it lets validation catch duplicate `node_id` entries
instead of relying on mapping parser behavior.

## 5. Route Shape

Each visible source route has exactly these v1 fields:

```text
route_id
source_class
source_path
purpose
required
```

Field rules:

- `route_id` is required.
- `route_id` must be unique within a node.
- `route_id` must be stable lowercase snake_case.
- `route_id` is a human/debug identity, not authority.
- `source_class + source_path + purpose` defines what is actually routed.
- `required` is a boolean.

This route remains invalid even if the `route_id` looks legitimate:

```yaml
route_id: repair_answer
source_class: pin_contract
source_path: repair_same_component.bind.base_params.code
purpose: acceptance_criteria
required: true
```

because the source path is forbidden.

## 6. Source Classes

LM5Z v1 uses the same closed source-class vocabulary as LM5W/LM5X:

```text
pin_contract
verifier_outcome
receipt_diagnostic
convention
planner_user_intent
```

Owner category derives from `source_class`. LM5Z v1 does not add
`source_owner` or `provenance_label` because those labels can drift into prose.

Ownership mapping:

```text
pin_contract        -> compiler/task contract
verifier_outcome    -> verifier/workflow contract
receipt_diagnostic  -> receipt/evidence
convention          -> KG/convention/action contract
planner_user_intent -> planner/user intent
```

Unknown source classes are validation errors.

## 7. Purposes

`purpose` is a closed enum:

```text
acceptance_criteria
evidence_context
unresolved_intent
```

Semantics:

```text
acceptance_criteria
  This source may feed an acceptance-criteria assembler.

evidence_context
  This source may be shown as supporting evidence/context, but does not itself
  become a criterion.

unresolved_intent
  This source declares a known missing intent slot or planner/user-intent gap.
```

`purpose` must not contain model-facing instruction text, desired output prose,
or repair hints.

Unknown purposes are validation errors.

## 8. Source-Class / Purpose Compatibility

LM5Z v1 uses this compatibility matrix:

| Source class | Allowed purposes |
|---|---|
| `pin_contract` | `acceptance_criteria`, `evidence_context` |
| `verifier_outcome` | `acceptance_criteria`, `evidence_context` |
| `receipt_diagnostic` | `acceptance_criteria`, `evidence_context` |
| `convention` | `acceptance_criteria`, `evidence_context` |
| `planner_user_intent` | `unresolved_intent` only |

Therefore these are invalid in v1:

```text
planner_user_intent -> acceptance_criteria
planner_user_intent -> evidence_context
```

Even explicit user intent is not an acceptance-criteria source in v1. That can
be a v2 design after a real source trail exists.

## 9. Required And Optional Routes

`required` is a boolean:

```text
required: true
  source must resolve before the worker node is eligible.

required: false
  source may be routed if available; absence does not invalidate the workflow.
```

Validation behavior:

```text
required route unresolved -> error
optional route unresolved -> warning
unknown source_class -> error
unknown purpose -> error
source path forbidden by policy -> error
duplicate ambiguous route -> error
```

Forbidden paths fail validation even when `required: false`.

## 10. Canonical Source Paths

V1 uses exact canonical strings only.

Allowed in the LM5U repair fixture family:

```text
create_script.initial_execution_params.pins_out
workflow_contract.rules.verify_repair.expected_outcome
create_script.receipt.script_receipt.repair_anchor.target_errors
script_body_gotcha
planner.intent.desired_output_value
```

No selector language in v1:

```text
no globs
no JSONPath
no predicates
no selectors
no wildcards
no regex
```

`source_path` must be a non-empty canonical string from a resolver allowlist
for the declared `source_class`.

## 11. Resolver Ownership And Allowlist

`source_class` determines which resolver family may resolve a `source_path`.
`source_path` alone is not authority.

LM5Z v1 defines a bounded allowlist, not a global path registry.

### LM5U Repair Fixture Paths

| Source class | Resolver owner | Allowed source paths |
|---|---|---|
| `pin_contract` | compiler/task contract | `create_script.initial_execution_params.pins_out` |
| `verifier_outcome` | verifier/workflow contract | `workflow_contract.rules.verify_repair.expected_outcome` |
| `receipt_diagnostic` | receipt/evidence | `create_script.receipt.script_receipt.repair_anchor.target_errors` |
| `convention` | convention/KG/action convention source | `script_body_gotcha` |
| `planner_user_intent` | planner/user intent | `planner.intent.desired_output_value` |

### GH Solve/Error Pressure Paths

The GH paths below are schema pressure only. They are not evidence that this
route set is sufficient for live Grasshopper repair.

| Source class | Resolver owner | Allowed source paths |
|---|---|---|
| `verifier_outcome` | verifier/workflow contract | `workflow_contract.rules.gh_solve.expected_outcome` |
| `receipt_diagnostic` | receipt/evidence | `solve_grasshopper_definition.receipt.gh_receipt.solver_errors` |
| `pin_contract` | compiler/task contract | `solve_grasshopper_definition.initial_execution_params.pins_out` |
| `convention` | convention/KG/action convention source | `grasshopper_definition_style_convention` |

Out of scope for LM5Z:

- global path registry
- all possible workflow contract paths
- generic dotted-path resolver
- wildcard path system

## 12. Forbidden Source Paths

The routing validator must check both:

```text
Can this path resolve?
May this path ever be routed?
```

Forbidden source path families in v1:

- hidden bind/base params
- already-bound repair params
- future node execution params
- model-authored future outputs
- `PROBE_REPAIR_CODE` / fixture answer constants
- desired replacement literals as worker-visible acceptance/evidence sources;
  in v1, explicit planner/user intent may only be routed as `unresolved_intent`

Examples:

```text
repair_same_component.bind.base_params.code
BindStepSpec.base_params.code
future_node.execution_params.code
PROBE_REPAIR_CODE
A = 42.0
```

A forbidden path is a validation error even if it technically exists and even
if the route is optional.

## 13. Duplicate Semantics

`route_id` uniqueness and semantic route uniqueness are separate.

Within a node:

- `route_id` must be unique.
- `(source_class, source_path, purpose)` must be unique.

Allowed if `purpose` differs:

```yaml
- route_id: repair_target_errors_context
  source_class: receipt_diagnostic
  source_path: create_script.receipt.script_receipt.repair_anchor.target_errors
  purpose: evidence_context
  required: true

- route_id: repair_target_errors_criteria
  source_class: receipt_diagnostic
  source_path: create_script.receipt.script_receipt.repair_anchor.target_errors
  purpose: acceptance_criteria
  required: true
```

Rejected:

```text
same node_id + source_class + source_path + purpose appears more than once
```

even if `route_id` differs.

`visible_sources` order may be preserved for diagnostics, review, and stable
rendering. It must not determine ownership, extraction behavior,
source-class meaning, or worker authority.

## 14. workflow_validate Role

LM5Z defines `workflow_validate` as a static/routability fence, not a judge.

Allowed validation checks:

- `schema` presence and version.
- `routes` list shape.
- `node_id` exists and targets a worker node.
- `node_id` uniqueness across route entries.
- `visible_sources` non-empty list.
- `route_id` shape and uniqueness within node.
- source-class allowlist.
- purpose allowlist.
- source-class/purpose compatibility.
- source path can resolve from declared upstream publishers.
- required vs optional behavior.
- forbidden path policy.
- duplicate/ambiguous route resolution.
- source path owner matches source class.

Explicitly not checked:

- model will act
- criteria are sufficient
- repair is semantically correct
- user intent is complete
- convention is the right convention
- action input quality

`workflow_validate` is not a semantic judge. It proves the routing contract is
well-formed and resolvable.

## 15. Validation Diagnostics

LM5Z defines structured diagnostics as a design shape:

```yaml
severity: error
code: required_route_unresolved
node_id: repair_same_component
route_id: repair_target_diagnostics
source_class: receipt_diagnostic
source_path: create_script.receipt.script_receipt.repair_anchor.target_errors
purpose: acceptance_criteria
message: Required source path could not be resolved.
```

Fields:

```text
severity: error | warning
code: stable_snake_case
node_id
route_id
source_class
source_path
purpose
message
```

Rules:

- errors block validation success
- warnings do not block validation success
- missing required route -> error
- missing optional route -> warning
- forbidden source path -> error
- unknown source class or purpose -> error
- ambiguous duplicate route -> error

`message` is human-readable but non-authoritative. Tools and tests should key
on `code` plus the route fields.

The LM5Y absent-side `pass1_missing_question` result remains outside
`workflow_validate`. Future evidence tables should report pass-one structural
invalid rate as its own metric. N=5 remains valid for large effects, not small
reliability-rate claims.

## 16. Worked Example 1: Proven LM5U Repair Route Set

This example reflects the evidence-backed LM5U/LM5Y repair fixture.

```yaml
schema: rook.worker_visible_source_routing:v1
routes:
  - node_id: repair_same_component
    visible_sources:
      - route_id: repair_pin_contract
        source_class: pin_contract
        source_path: create_script.initial_execution_params.pins_out
        purpose: acceptance_criteria
        required: true
      - route_id: repair_expected_outcome
        source_class: verifier_outcome
        source_path: workflow_contract.rules.verify_repair.expected_outcome
        purpose: acceptance_criteria
        required: true
      - route_id: repair_target_diagnostics
        source_class: receipt_diagnostic
        source_path: create_script.receipt.script_receipt.repair_anchor.target_errors
        purpose: acceptance_criteria
        required: true
      - route_id: repair_body_mode_convention
        source_class: convention
        source_path: script_body_gotcha
        purpose: acceptance_criteria
        required: true
```

`repair_body_mode_convention` routes through `convention` in v1 because that is
the current evidence trail. LM5Z does not decide whether body-mode preservation
ultimately belongs to action contract, compiler node type, or KG-backed
convention.

## 17. Worked Example 2: GH Solve/Error Pressure Route Set

This example is schema pressure only. It is not evidence that the route set is
sufficient for live Grasshopper repair.

```yaml
schema: rook.worker_visible_source_routing:v1
routes:
  - node_id: solve_grasshopper_definition
    visible_sources:
      - route_id: gh_expected_solve_status
        source_class: verifier_outcome
        source_path: workflow_contract.rules.gh_solve.expected_outcome
        purpose: acceptance_criteria
        required: true
      - route_id: gh_solver_errors
        source_class: receipt_diagnostic
        source_path: solve_grasshopper_definition.receipt.gh_receipt.solver_errors
        purpose: acceptance_criteria
        required: true
      - route_id: gh_component_pin_contract
        source_class: pin_contract
        source_path: solve_grasshopper_definition.initial_execution_params.pins_out
        purpose: acceptance_criteria
        required: true
      - route_id: gh_convention_definition_style
        source_class: convention
        source_path: grasshopper_definition_style_convention
        purpose: evidence_context
        required: false
```

This example exists to prevent overfitting the routing shape to C# repair. It
does not add a new validated criterion family.

## 18. Unresolved Intent And Clarify/Resupply

`planner_user_intent` is allowed only with `purpose: unresolved_intent` in v1.

Allowed:

```yaml
- route_id: missing_desired_output_value
  source_class: planner_user_intent
  source_path: planner.intent.desired_output_value
  purpose: unresolved_intent
  required: false
```

Invalid in v1:

```yaml
- route_id: desired_output_value_criteria
  source_class: planner_user_intent
  source_path: planner.intent.desired_output_value
  purpose: acceptance_criteria
  required: true
```

`unresolved_intent` routes identify known missing intent slots that a future
clarify/resupply loop may use. LM5Z does not define that loop, prompt behavior,
retry semantics, or planner interaction protocol.

## 19. Relationship To Rook2

Rook2 remains a future consumer/export surface, not the semantic owner of
worker-visible source routing.

Rook2 may eventually expose or validate routing artifacts as part of
`workflow_validate`/`workflow_run`, but source ownership remains in the source
layers:

- Planner/compiler routes source visibility.
- Verifier owns expected outcomes.
- Receipts own observed failures.
- KG/conventions own conventions with provenance.
- Assemblers render worker-visible criteria/evidence.

This preserves the Rook2 direction as broker/export surface rather than a
semantic dumping ground.

## 20. Anti-Goals

LM5Z must not:

- add a broad `acceptance_criteria` prose field to `RookWorkflowContract`
- put all criteria in a single contract object
- invent a global source-path registry
- add path selectors, globs, regex, predicates, or JSONPath
- route hidden bind params or future model outputs
- route `PROBE_REPAIR_CODE`, `A = 42.0`, or desired replacement literals
- implement Planner/compiler behavior
- implement `workflow_validate`
- implement clarify/resupply
- update worker evidence packets
- add another LM5U-style evidence generation
- claim GH solve/error routing is empirically validated
- include an LM proof-ladder capstone

## 21. Recommended Next Slice

Next recommended slice:

```text
LM5AA = deterministic worker-visible source-routing validator prototype
```

LM5AA should prove:

```text
valid LM5U repair route set -> passes
missing required path -> error
missing optional path -> warning
forbidden bind/base_params path -> error
unknown source_class/purpose -> error
planner_user_intent used for acceptance_criteria -> error
duplicate route tuple -> error
```

LM5AA should be deterministic only:

- no live run
- no model calls
- no worker packet change
- no Planner/compiler mutation
- no evidence-shape experiment

Later slices can decide how Planner/compiler author or store routing
declarations once the validator shape has earned its keep.
