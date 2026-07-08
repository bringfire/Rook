# LM8A Second Template Family Design

Status: design checkpoint for review

Date: 2026-07-08

## 1. Purpose

LM8A designs the first family-transfer slice after LM7E.

LM7E proved the joined chain once for the original task family:

```text
Planner model-authored request
-> strict parse
-> workflow_validate
-> materialization
-> runtime routability
-> worker-visible evidence
-> Gemma worker action
-> live gh_update_script
-> verify_repair_succeeded
```

The current proven family is:

```text
C# script repair from compiler diagnostic
```

LM8A changes the task family while keeping complexity roughly flat:

```text
GH-native scalar solve/output expectation
```

Core claim for the future implementation slice:

```text
The bounded-worker protocol can support a second tiny task family without
special-casing the original C# repair fixture.
```

LM8A is a spec-only design. It does not implement the family, run a model, or
run live Rhino/Grasshopper.

## 2. Scope

In scope:

- choose the second task family
- define the minimum viable fixture
- define source facts and source ownership
- define the worker-visible acceptance/evidence shape
- define the worker action surface
- define the verifier target
- define what remains unchanged from LM7E
- define interpretation rules for pass/fail in the later implementation slice

Out of scope:

- no code
- no implementation plan
- no live run
- no Planner-model run
- no worker-model run
- no router implementation
- no retry or pull loop
- no model panel
- no new prompt experiment
- no `gh_edit` batch
- no wiring or topology repair
- no script repair
- no broad workflow orchestration
- no generic difficulty taxonomy
- no change to the LM7E canonical chain

## 3. Family Choice

LM8A chooses:

```text
GH-native scalar solve/output expectation
```

The family-transfer variable is domain, not complexity.

The move is:

```text
from:
  C# compiler diagnostic repair

to:
  Grasshopper-native scalar value correction
```

Held roughly constant:

- one template
- one worker node
- one worker action/decision surface
- one trusted target anchor
- one expected fact
- one verifier
- one live terminal outcome
- no topology edit
- no batch edit
- no multi-step worker plan

LM8A deliberately does not choose a missing-wire, topology, or GH edit-batch
fixture. Those are more product-relevant later, but they mix family transfer
with complexity growth.

## 4. Minimum Fixture

The v1 fixture is a tiny Grasshopper-native scalar expectation:

```text
one editable GH scalar value starts wrong
one observed scalar output is wrong
one source-owned expected scalar output value is known
the worker may propose the new scalar value
the applier supplies the trusted target GUID
the verifier checks the live output
```

Example fixture shape, without locking implementation details:

```text
Number Slider or Panel value -> identity GH-native output projection -> inspected output
```

The fixture may use any deterministic GH-native construction that gives the
same surface:

- a single editable scalar source
- a stable output to inspect
- a wrong initial scalar value
- a known expected scalar output value
- a trusted live anchor for the editable scalar source

V1 pins the output path to identity scalar projection:

```text
editable scalar value == observed scalar output value
```

The worker is not being tested on inverse reasoning. If the output path applies
a transform, the slice stops being a family-transfer test and starts measuring
reasoning/complexity. Transformed scalar expectations belong to a later family
or complexity slice.

The worker must not create components, rewire components, edit scripts, or
author a topology change.

## 5. Expected Value Ownership

The expected scalar value is source-owned. It is not worker-invented and is not
free-floating prompt prose.

LM8A locks this v1 source ownership:

```text
source_class: expected_output_contract
owner: workflow template / task contract / verifier expectation
purpose: acceptance_criteria
```

Recommended v1 source path:

```text
workflow_contract.rules.verify_scalar_output.expected_output_value
```

The exact storage can be refined by the implementation plan, but the authority
cannot move:

- the Planner may select the template and bind initial fixture params
- the template/task contract owns the expected scalar output fact
- the verifier owns observed success/failure
- the worker may only author the value to stage for the trusted target

This route is intentionally different from `planner_user_intent`. In LM7A,
`planner_user_intent` was limited to `unresolved_intent`. LM8A needs a
source-owned concrete expectation, so the design reserves
`expected_output_contract` rather than smuggling the scalar through unresolved
intent or worker prose.

## 6. Source Facts

The worker node needs only bounded, auditable facts:

```text
expected scalar output value
  owner: workflow/template/task contract
  source_class: expected_output_contract

current observed scalar output
  owner: live receipt / verifier precheck
  source_class: receipt_observation

editable scalar target contract
  owner: create receipt scalar anchor
  source_class: fixture_anchor

set-value convention
  owner: convention/KG or template-local convention packet
  source_class: convention
```

The trusted target GUID is not a worker-authored source fact. It is an anchor
binding consumed by the applier. The worker-visible editable value contract may
come from the create receipt's scalar anchor, but the GUID itself remains
applier-only.

The worker-visible packet may describe the target by stable label, role, type,
and current value. It must not ask the worker to provide the GUID.

## 7. Routing Shape

LM8A's future implementation should use a node-scoped routing artifact in the
LM5Z/LM5AA style.

Illustrative v1 route set:

```yaml
schema: rook.worker_visible_source_routing:v1
routes:
  - node_id: set_scalar_value
    visible_sources:
      - route_id: scalar_expected_output_value
        source_class: expected_output_contract
        source_path: workflow_contract.rules.verify_scalar_output.expected_output_value
        purpose: acceptance_criteria
        required: true

      - route_id: scalar_current_output
        source_class: receipt_observation
        source_path: create_scalar_expectation.receipt.gh_receipt.observed_output_value
        purpose: acceptance_criteria
        required: true

      - route_id: scalar_editable_target_contract
        source_class: fixture_anchor
        source_path: create_scalar_expectation.receipt.gh_receipt.scalar_anchor.editable_value_contract
        purpose: evidence_context
        required: true

      - route_id: scalar_set_value_convention
        source_class: convention
        source_path: gh_set_value_scalar_convention
        purpose: evidence_context
        required: false
```

The new `expected_output_contract`, `receipt_observation`, and `fixture_anchor`
source classes are part of the LM8A design. A later implementation must either:

- add them as bounded source-class extensions with exact path allowlists, or
- explicitly justify an equivalent existing source class without weakening
  ownership.

V1 source-class / purpose compatibility:

```text
expected_output_contract -> acceptance_criteria | evidence_context
receipt_observation      -> acceptance_criteria | evidence_context
fixture_anchor           -> evidence_context only
```

`fixture_anchor` is not criteria authority. It may identify the editable target
role and visible target contract, but it must not become the source of the
expected scalar value or observed success condition.

It must not represent the expected scalar as worker prompt prose, hidden bind
params, or a Planner `unresolved_intent` value. It must not represent the
observed scalar output as a receipt diagnostic unless the future fixture is
explicitly redesigned around an error-shaped diagnostic.

## 8. Worker-Visible Evidence

LM8A should preserve the LM7E discipline:

```text
full resolved source artifacts are auditable artifacts
worker prompt receives only the bounded visible surface
```

The family-specific evidence envelope may be named:

```text
gh_scalar_expectation_evidence
```

Worker-visible fields should include:

```text
current_observed_output
expected_output_value
editable_value_contract
recommended_action_id
acceptance_criteria
```

The `acceptance_criteria` section should use the same legacy projection idea
proven by LM5Y/LM7B:

```json
{
  "source": "gh_scalar_expectation",
  "criteria": [
    {
      "criterion_id": "set_scalar_to_match_expected_output",
      "description": "Set the editable scalar value so the inspected GH output equals the source-owned expected scalar value.",
      "source": "scalar_expected_output_value"
    }
  ]
}
```

This criterion text is assembler-owned. The contract/routing artifact declares
source facts; it does not contain this prose.

The worker-visible request must not contain:

- full routing validator reports
- source-set internals
- fingerprints
- hidden bind params
- target GUID as worker-authored authority
- `gh_edit` batch instructions
- topology or wiring instructions
- C# repair references

## 9. Worker Action

LM8A introduces a new worker action surface:

```text
draft_gh_set_value_params
```

V1 action input:

```json
{
  "value": 7.5
}
```

Rules:

- `value` is required.
- `value` must be a finite JSON number.
- no extra keys
- no `guid`
- no `tool_name`
- no `expected_output_value`
- no script/code field
- no batch edit list
- no topology intent

The worker authors only the scalar value. The trusted target GUID comes from
the live fixture anchor and is merged by a future applier.

The applier seam should be separate from the LM6 worker-action applier unless
the implementation proves a shared abstraction is genuinely behavior-preserving.
The conceptual seam is:

```text
model-authored scalar value + trusted target anchor -> gh_set_value params
```

The applier must never read hidden bind params or invent the scalar value.

## 10. Verifier

The verifier checks the live GH floor, not the worker's text.

V1 verifier responsibility:

```text
after gh_set_value dispatch:
  run/observe GH solve
  inspect the target output
  compare observed scalar output to the source-owned expected scalar value
  reject relevant solver errors
```

Acceptance:

```text
observed output equals expected scalar value within the fixture's numeric
comparison rule, and the live GH artifact is usable/verified
```

LM8A should prefer a deterministic scalar fixture whose expected value avoids
floating-point ambiguity. If numeric tolerance is needed, the verifier owns that
tolerance; the worker does not.

The v1 verifier should treat the editable scalar value as the inspected output
value. Any future inverse relationship between editable value and output value
must be introduced by a later spec.

## 11. Template Sketch

Suggested template id:

```text
gh_scalar_value_expectation
```

Suggested node identities:

```text
create_scalar_expectation
set_scalar_value
verify_scalar_output
```

The template owns:

- fixture construction
- expected scalar output fact
- default source-routing artifact
- worker node identity
- trusted target anchor extraction
- verifier rule

The Planner/request layer may later select the template and bind allowed
initial fixture params. LM8A does not design a Planner-model prompt for this
second family.

## 12. Unchanged Protocol Seams

LM8A intentionally preserves the proven protocol shape:

```text
PlannerWorkerContractRequest or deterministic request source
-> workflow_validate
-> materialized workflow contract + source routing
-> LM5AA-style routing validation
-> source extraction
-> assembler-owned worker-visible criteria
-> frozen worker publication/action discipline
-> action applier
-> live dispatch
-> verifier-floor result
```

Unchanged from LM7E:

- strict validation before live work
- source routing as the visibility fence
- no hidden bind-answer path
- full source artifacts are artifacts, not prompt stuffing
- worker-visible criteria are assembled from routed facts
- worker action is bounded and schema-checked
- worker does not choose live target authority
- all terminal outcomes are receipted

Changed by LM8A:

- task family
- source paths and bounded source-class extensions:
  `expected_output_contract`, `receipt_observation`, and `fixture_anchor`
- worker action id/input
- verifier domain
- fixture construction domain

## 13. Failure Interpretation

Future LM8 implementation results should be read carefully.

If the future implementation passes:

```text
The bounded-worker protocol generalizes to a second tiny task family.
```

It does not prove:

- complexity scaling
- topology repair
- GH edit-batch competence
- broad Planner reliability
- general Grasshopper design ability

If request/routing validation fails:

```text
Treat it as a source-ownership or family-transfer seam finding.
```

If live fixture creation or receipt shape fails before the worker:

```text
Treat it as a pre-worker gate finding, not model evidence.
```

If the worker reaches action but the verifier rejects:

```text
Treat it as family-transfer evidence after lower-level gates passed.
```

Do not replace failed attempts in the future evidence run unless a later spec
pre-registers repeatability accounting.

## 14. Deterministic Proof Targets For The Next Slice

LM8A's recommended next implementation slice should remain deterministic first.

Proof targets:

- valid default routing artifact for `gh_scalar_value_expectation`
- `expected_output_contract`, `receipt_observation`, and `fixture_anchor` path
  allowlists are bounded and exact
- expected scalar value is source-owned, not worker-authored prose
- routed sources can assemble a worker-visible criteria packet
- worker action schema rejects `guid`, extra keys, non-numeric values, and
  script/code fields
- applier merges trusted target GUID with worker-authored scalar value
- verifier comparison rule is explicit
- no full graph dump
- no hidden bind params
- no `gh_edit` batch
- no wiring/topology edit
- no live run in implementation PR

## 15. Follow-Ups

Likely ladder:

```text
LM8A: spec-only second family design
LM8B: deterministic source-routing / assembler / action-applier prototype
LM8C: single live GH-native scalar expectation run
LM8D: doc-only evidence summary
```

Only after the second tiny family is receipted should the project consider a
more complex GH family such as missing-wire repair, component replacement, or
small edit batches.
