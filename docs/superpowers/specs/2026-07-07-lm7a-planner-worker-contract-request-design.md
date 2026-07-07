# LM7A - Planner Worker Contract Request Design

- **Date:** 2026-07-07
- **Status:** Draft for review
- **Slice:** LM7A
- **Type:** Planner-side deterministic design/spec first

## 1. Purpose

LM6 closed the worker line for the controlled repair fixture:

```text
routed source facts -> acceptance criteria -> two-pass local worker publication
-> worker-action applier -> live gh_update_script -> verify_repair
```

The next missing seam is Planner-side authoring.

LM7A defines the first Planner-authored artifact that can feed the proven worker
protocol without asking a Planner model to write arbitrary workflows.

Core frame:

```text
select -> bind -> delta -> declare
```

Meaning:

- select a known workflow template
- bind declared initial params
- apply a bounded delta to template-derived worker-visible source routing
- declare unresolved intent slots instead of guessing missing intent

LM7A is not a live Planner model probe. It is not free workflow authoring. It is
the deterministic contract surface a future Planner model must learn to produce.

## 2. Scope

LM7A should be implemented only after this spec is reviewed.

Spec scope:

```text
docs/superpowers/specs/2026-07-07-lm7a-planner-worker-contract-request-design.md
```

Expected later deterministic implementation scope:

```text
PlannerWorkerContractRequest v1 loader/validator/materializer
template bundle fixture for repair_same_component_from_create_error
workflow_validate v1 report composer
deterministic tests
```

Out of scope:

- No Planner model.
- No live Rhino/GH.
- No worker prompt changes.
- No LM5/LM6 worker protocol changes.
- No `run_two_pass_worker_publication(...)` changes.
- No worker-action applier changes.
- No runtime dispatch.
- No RookChat integration.
- No MCP tool exposure unless a later slice explicitly designs it.
- No free node/edge authoring.
- No broad template catalog.
- No hidden bind params.
- No acceptance-criteria prose authored by the Planner.
- No capability metadata implying execution authority.

## 3. Design Line

LM7A defines:

```text
rook.planner_worker_contract_request:v1
```

The Planner request is a proposal, not authority. It becomes actionable only
after `workflow_validate` materializes and validates it.

The Planner owns:

```text
template_id
initial_params
routing_delta
intent_slots
```

The template/compiler layer owns:

```text
workflow contract defaults
worker-visible source-routing defaults
worker node ids
source ownership expectations
```

The validator owns:

```text
request validation
template lookup validation
workflow contract load/compile validation
resolved source-routing static validation through LM5AA
intent-slot compatibility validation
```

The worker receives only validated routed sources/criteria later. It never sees
Planner deltas, hidden defaults, or template internals directly.

## 4. Why Routing Defaults Plus Delta

LM7A explicitly chooses:

```text
template-derived routing defaults + planner-authored delta
```

Rejected alternatives:

```text
Planner embeds the whole worker-visible source-routing artifact.
Planner only declares intent slots and never touches routing.
```

The chosen shape preserves ownership:

- For known templates, source routing should be mechanically derivable.
- The Planner should not copy a giant routing blob it does not own.
- The Planner should not be too weak to countersign/narrow visibility.
- The Planner's authority is bounded route operation proposals.
- LM5AA remains the fence for the resolved route artifact.

Core doctrine:

```text
Planner proposes task shape and visibility changes.
Compiler/template owns defaults.
Authoring-time validation proves the resolved worker-visible routing artifact is legal.
Runtime gates prove receipt-backed routes are routable when receipts exist.
Assembler owns worker-facing acceptance-criteria prose.
```

## 5. Planner Request Shape

The LM7A artifact shape is:

```yaml
schema: rook.planner_worker_contract_request:v1
template_id: repair_same_component_from_create_error

initial_params:
  create_script:
    pins_out:
      - A:double

routing_delta:
  enable_routes: []
  disable_routes: []
  set_required: {}
  add_unresolved_intent_routes:
    - route_id: missing_desired_output_value
      source_class: planner_user_intent
      source_path: planner.intent.desired_output_value
      purpose: unresolved_intent
      required: false

intent_slots:
  - intent_id: desired_output_value
    status: unresolved
    source_path: planner.intent.desired_output_value
    description: Desired output value was not provided.
```

Top-level rules:

- `schema` must equal `rook.planner_worker_contract_request:v1`.
- `template_id` must name a known template bundle.
- `initial_params` may bind only params declared by the template bundle.
- `routing_delta` must be present and v1-shaped, even when empty.
- `intent_slots` must be present as a list, even when empty.
- Unknown top-level fields are validation errors.

LM7A uses direct `template_id`. It does not ask the old
`WorkflowTemplateRef.descriptor` selector to infer a template. That avoids
mixing two questions:

```text
Can the Planner author a bounded worker-contract request?
Can the template selector infer the right workflow from a descriptor?
```

LM7A tests the first question only.

## 6. Template Bundle Defaults

The deterministic LM7A fixture template is:

```text
repair_same_component_from_create_error
```

The template bundle provides:

- a workflow contract payload or deterministic workflow contract factory
- default worker-visible source routing
- worker node ids
- declared initial param schema
- allowed routing-delta surface

The template bundle must be worker-splice-compatible. It must not include hidden
repair bind output such as:

```text
PROBE_REPAIR_CODE
A = 42.0;
BindStepSpec.base_params.code
```

The repair worker remains the binder. Any live execution later must still use
the worker-action applier to stage repair params.

Hard rule:

```text
repair_same_component must have no BindStepSpec.
```

More generally, contract-phase validation must reject any `BindStepSpec` for a
worker-authored node. This is true even when `base_params` is empty or contains
no hidden repair literal. A bind step on the repair worker would recreate the
LM6A overwrite risk by giving the workflow a non-worker path to execution params.

### 6.1 Default Source Routing

The template default routing owns the four LM5U/LM6 proven worker-visible
routes. They are enabled and required by default:

```text
repair_pin_contract
repair_expected_outcome
repair_target_diagnostics
repair_body_mode_convention
```

Default artifact shape after template lookup:

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

The Planner happy path does not need to restate these routes.

For the LM7A repair fixture, these four routes are locked:

```text
non_disableable_routes:
  repair_pin_contract
  repair_expected_outcome
  repair_target_diagnostics
  repair_body_mode_convention
```

Future templates may expose a broader or narrower delta surface, but they must
declare it explicitly per route. A route being present in template defaults does
not automatically mean the Planner may disable it.

## 7. Routing Delta

`routing_delta` uses stable operations keyed by `route_id`.

Shape:

```yaml
routing_delta:
  enable_routes: []
  disable_routes: []
  set_required: {}
  add_unresolved_intent_routes: []
```

Allowed operations:

- disable a default route only when the template declares that route
  disableable
- re-enable a default route only when the template declares that route
  planner-toggleable
- override `required` for an enabled default route only when the template
  declares that route's requiredness planner-settable
- add `planner_user_intent -> unresolved_intent` routes only

Rules:

- `enable_routes` is a list of route ids.
- `disable_routes` is a list of route ids.
- `set_required` is a mapping of `route_id -> bool`.
- `add_unresolved_intent_routes` is a list of route objects.
- `enable_routes` and `disable_routes` must not contain the same `route_id`.
- Existing route operations may target only template-default route ids.
- Existing route operations must be allowed by the template's per-route
  allowed-delta surface.
- Added route ids must not collide with template-default route ids.
- Added route ids must be unique within the delta.
- `set_required` may target only routes enabled in the resolved routing artifact:
  - enabled default routes
  - unresolved-intent routes added by this delta
- `set_required` on a disabled route is an error.
- In the LM7A fixture, disabling any of the four LM6-proven acceptance routes is
  an error.
- `routing_delta` must not contain acceptance-criteria prose.
- `routing_delta` must not contain hidden answers, repair literals, or model
  instructions.

### 7.1 Added Unresolved-Intent Routes

LM7A permits added routes only in this form:

```yaml
- route_id: missing_desired_output_value
  source_class: planner_user_intent
  source_path: planner.intent.desired_output_value
  purpose: unresolved_intent
  required: false
```

Invalid in LM7A:

```yaml
source_class: planner_user_intent
purpose: acceptance_criteria
```

Planner intent may not feed acceptance criteria in LM7A. It can only declare
known missing intent to future consumers.

## 8. Intent Slots

`intent_slots` records Planner-side restraint.

LM7A validates unresolved slots:

```yaml
- intent_id: desired_output_value
  status: unresolved
  source_path: planner.intent.desired_output_value
  description: Desired output value was not provided.
```

Field rules:

- `intent_id` is required and unique.
- `intent_id` is stable lowercase snake_case.
- `status` must be `unresolved` in LM7A.
- `source_path` must be a non-empty canonical planner intent path.
- `description` is human-readable and non-authoritative.
- Unknown fields are validation errors.

LM7A intentionally does not model provided intent values. That is a later slice,
because provided user intent may become worker-visible evidence only after a
separate source trail and routing rule exist.

Intent/routing compatibility:

```text
unresolved_intent route without matching intent_slot -> error
intent_slot without matching route -> warning
```

Diagnostic codes:

```text
unresolved_intent_route_missing_slot -> error
intent_slot_not_routed -> warning
```

Reason:

```text
worker-visible unresolved intent must be backed by an explicit Planner-owned slot
```

but:

```text
Planner may track missing intent internally without routing it to the worker yet
```

Warnings do not block report validity.

## 9. Materialization Chain

LM7A materializes a request as:

```text
PlannerWorkerContractRequest
  -> known template bundle lookup
  -> RookWorkflowContract payload
  -> load_workflow_contract_payload
  -> compile_workflow_contract
  -> default WorkerVisibleSourceRouting
  -> apply routing_delta
  -> resolved routing artifact
  -> LM5AA static routing validation
  -> intent slot validation
  -> unified workflow_validate report
```

`WorkflowTemplateRef.descriptor` stays internal to template lookup/materialized
contract payload, if needed. It is not authored directly in the LM7A Planner
request.

The materializer must copy resolved artifacts into fresh containers. A Planner
payload must never alias mutable template defaults.

### 9.1 Authoring-Time Validation vs Runtime Routability

LM7A `workflow_validate` is an authoring-time fence. It validates that the
Planner request can materialize a legal workflow contract and a legal
worker-visible source-routing artifact.

It does **not** require live receipt values.

That distinction matters because the proven repair route set includes:

```text
create_script.receipt.script_receipt.repair_anchor.target_errors
```

That value exists only after the create step has run and produced a receipt.
Therefore LM7A must not reject the happy-path Planner request merely because the
live create receipt does not exist yet.

LM7A's routing phase should call LM5AA in static-only mode for the resolved
routing artifact:

```text
validate_worker_visible_source_routing(resolved_routing_artifact)
```

The embedded/source-routing report should preserve that routability was not
evaluated at authoring time. Runtime LM6A Phase A remains responsible for
running LM5AA routability once live create receipts and convention packets
exist.

The implementation plan may add a separate deterministic fixture-routability
anchor if it can supply synthetic graph/receipt objects cleanly, but that anchor
must not change the authoring-time `workflow_validate` semantics.

## 10. workflow_validate v1 Report

LM7A defines one unified validation report:

```text
rook.workflow_validate_report:v1
```

Shape:

```yaml
schema: rook.workflow_validate_report:v1
valid: true
request_schema: rook.planner_worker_contract_request:v1
template_id: repair_same_component_from_create_error
request_fingerprint: sha256:...
report_fingerprint: sha256:...

phases:
  request:
    valid: true
    diagnostics: []
  template:
    valid: true
    diagnostics: []
  contract:
    valid: true
    diagnostics: []
  routing:
    valid: true
    diagnostics: []
    source_routing_report:
      schema: rook.worker_visible_source_routing_validation_report:v1
      valid: true
      routability_evaluated: false
  intent:
    valid: true
    diagnostics: []

resolved:
  workflow_contract_schema: rook.workflow_contract:v1
  workflow_contract_id: lm7a_repair_same_component_from_create_error
  workflow_contract_fingerprint: sha256:...
  routing_schema: rook.worker_visible_source_routing:v1
  routing_fingerprint: sha256:...
  worker_nodes:
    - repair_same_component
```

Rules:

- `valid` is false if any phase has an error diagnostic.
- Warnings do not block validity.
- `request_fingerprint` is computed over canonical request JSON.
- `report_fingerprint` is computed over canonical report JSON with
  `report_fingerprint` omitted.
- The report may include summaries/fingerprints of resolved artifacts.
- The report must not include hidden bind params.
- The report must not include full workflow graph dumps.
- The report must not include raw worker prompts, model output, or live receipts.

`routing.source_routing_report` may embed or summarize the LM5AA report. LM7A
must not invent a second routing validator.

## 11. Diagnostic Shape

LM7A diagnostics follow the LM5AA spirit:

```yaml
severity: error
code: unresolved_intent_route_missing_slot
phase: intent
path: routing_delta.add_unresolved_intent_routes[0]
template_id: repair_same_component_from_create_error
route_id: missing_desired_output_value
intent_id: desired_output_value
source_class: planner_user_intent
source_path: planner.intent.desired_output_value
purpose: unresolved_intent
message: Unresolved-intent route has no matching intent slot.
```

Fields:

```text
severity: error | warning
code: stable_snake_case
phase: request | template | contract | routing | intent
path
template_id
node_id
route_id
intent_id
source_class
source_path
purpose
message
```

Only `severity`, `code`, `phase`, and `message` are always required. Other
fields are included when relevant.

`message` is human-readable but non-authoritative. Tests and future Planner
repair loops should key on stable diagnostic codes and fields.

## 12. Phase Responsibilities

### 12.1 Request Phase

Validates the Planner-authored payload itself:

- schema
- top-level field set
- `template_id`
- `initial_params` shape
- `routing_delta` shape
- `intent_slots` shape
- duplicate ids
- hidden-answer strings in Planner-authored fields

It does not look up templates.

### 12.2 Template Phase

Validates template bundle lookup:

- `template_id` exists
- template bundle declares initial params
- template bundle declares worker node ids
- template bundle declares default source routing
- template bundle has no hidden repair answer defaults

It does not validate source routability against live graph objects.

### 12.3 Contract Phase

Materializes and validates the workflow contract:

- derive `RookWorkflowContract` payload
- load via `load_workflow_contract_payload`
- compile via `compile_workflow_contract`
- record contract fingerprint
- reject hidden bind params in the materialized worker-splice contract

It does not execute the graph.

### 12.4 Routing Phase

Materializes and validates source routing:

- derive default routing from template
- apply `routing_delta`
- reject illegal delta operations
- call `validate_worker_visible_source_routing` in static-only mode
- include LM5AA report or summary
- record routing fingerprint

It must not implement a parallel routing validator.
It must not require live receipt values.

### 12.5 Intent Phase

Validates Planner restraint:

- intent slot shape
- unresolved slot source paths
- route/slot compatibility
- route without slot -> error
- slot without route -> warning

It does not produce acceptance criteria.

## 13. Deterministic Fixture

The canonical LM7A fixture request is intentionally small:

```yaml
schema: rook.planner_worker_contract_request:v1
template_id: repair_same_component_from_create_error

initial_params:
  create_script:
    pins_out:
      - A:double

routing_delta:
  enable_routes: []
  disable_routes: []
  set_required: {}
  add_unresolved_intent_routes:
    - route_id: missing_desired_output_value
      source_class: planner_user_intent
      source_path: planner.intent.desired_output_value
      purpose: unresolved_intent
      required: false

intent_slots:
  - intent_id: desired_output_value
    status: unresolved
    source_path: planner.intent.desired_output_value
    description: Desired output value was not provided.
```

Expected validation:

```text
request phase: valid
template phase: valid
contract phase: valid
routing phase: valid, LM5AA routability_evaluated false
intent phase: valid
overall: valid
```

Expected resolved routing:

```text
four template-default acceptance_criteria routes
one planner_user_intent unresolved_intent route
```

Expected worker criteria:

```text
unchanged from LM6 proven path
```

The unresolved intent route is not acceptance criteria and must not change the
LM6 worker-visible criteria text.

## 14. Negative Proof Targets

The later implementation plan should include deterministic tests for:

- unknown schema
- unknown `template_id`
- unknown top-level field
- missing declared initial param
- undeclared initial param
- hidden repair literal in Planner-authored payload
- `enable_routes` and `disable_routes` contain the same route id
- route operation targets unknown route id
- route operation targets a template route whose allowed-delta surface forbids
  that operation
- delta disables one of the four locked LM6-proven fixture routes
- `set_required` targets disabled route
- duplicate added route id
- added route uses `planner_user_intent` with `acceptance_criteria`
- added route uses forbidden source path
- unresolved-intent route missing matching intent slot
- intent slot not routed emits warning
- malformed intent slot
- materialized contract contains hidden bind/base params
- materialized contract contains any `BindStepSpec` for `repair_same_component`
  or another worker-authored node
- LM5AA routing failure is surfaced in the routing phase

No test should require Rhino, Grasshopper, Ollama, a live model, or a live
worker run.

## 15. Relationship To Existing Layers

### 15.1 RookWorkflowContract

LM7A does not require the Planner request to be a `RookWorkflowContract`.

The Planner request materializes to a workflow contract payload after template
lookup. This preserves the contract compiler as the type-checker while avoiding
free-form Planner node authoring in Stage 1.

### 15.2 LM5AA

LM7A consumes LM5AA. It does not replace it.

The resolved routing artifact must be validated through
`validate_worker_visible_source_routing`.

### 15.3 LM5W/LM5X/LM5Y

LM7A does not change acceptance-criteria assembly, source extraction, or the
legacy worker-visible projection. It proves the Planner can author the upstream
request shape that eventually feeds those seams.

### 15.4 Capability Metadata

Capability metadata may inform future Planner authoring, but it does not
authorize execution.

LM7A template selection is explicit by `template_id`. Capability discovery is a
future LM7B concern.

## 16. Anti-Goals

LM7A must not:

- ask a Planner model to write workflows
- expose a live `workflow_validate` MCP tool before the deterministic seam is
  proven
- make `RookWorkflowContract` absorb routing deltas or intent slots
- put acceptance-criteria prose in Planner payloads
- let planner/user intent feed acceptance criteria in v1
- route hidden bind params
- route desired replacement literals
- change the worker protocol
- dispatch live Rhino/GH tools
- add prompt text
- add retry, clarify, or resupply behavior
- generalize to arbitrary templates
- claim Planner competence

## 17. Recommended Next Slice

After this spec is approved, the next slice should be a deterministic
implementation plan for:

```text
LM7A = PlannerWorkerContractRequest v1 + workflow_validate v1
```

Implementation should prove the canonical fixture and negative validation cases
without live model calls or live Rhino/GH.

Expected implementation artifacts may include:

```text
mcp_server/src/rook/agent/planner_worker_contract_request.py
mcp_server/src/rook/agent/workflow_validate.py
mcp_server/tests/test_planner_worker_contract_request.py
mcp_server/tests/test_workflow_validate.py
```

Exact module naming belongs to the implementation plan.

## 18. Success Criteria

LM7A design succeeds when it defines a Planner-authored request that:

```text
selects a known template
binds declared initial params
applies a bounded route delta
declares unresolved intent slots
materializes a workflow contract
resolves template-owned worker-visible source routing
validates routing statically through LM5AA
returns one unified workflow_validate report
does not write criteria prose
does not route hidden answers
does not dispatch runtime work
```

The first Planner model probe, LM7B, should happen only after this deterministic
artifact shape is implemented and tested.
