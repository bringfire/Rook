# LM7D - Planner Shape Guidance Probe Design

- **Date:** 2026-07-07
- **Status:** Draft for review
- **Slice:** LM7D
- **Type:** Planner-side offline prompt-shape guidance probe

## 1. Purpose and LM7C Baseline

LM7C exercised the first Planner-model authoring surface:

```text
brief + template menu + sparse authoring prompt
  -> one model output
  -> strict JSON parse
  -> workflow_validate
  -> intent_decision classification
```

Canonical LM7C evidence used `codex-cli-chatgpt` / `gpt-5.5`, five attempts
per scenario, and the sparse prompt:

```text
prompt_profile: sparse_v1
prompt_version: lm7c.planner_authoring_prompt:v1
```

LM7C result:

```text
parse_success_count: 10/10
workflow_validate_valid_count: 0/10
canonical_success_count: 0/10
intent_complete: 5/5 correct_declared
intent_incomplete: 5/5 not_classifiable
invented_count: 0/10
over_declared_count: 0/10
hidden marker matches: 0
```

The interpretation was narrow:

```text
LM7C was a request-surface learnability failure, not a Planner safety failure.
```

GPT-5.5 obeyed the strict JSON envelope and did not invent missing intent, but
the sparse prompt did not teach the exact `PlannerWorkerContractRequest:v1`
container shape.

LM7D asks the next offline question:

```text
Can prompt field-shape guidance make PlannerWorkerContractRequest:v1 learnable
without increasing invention or over-declaration?
```

LM7D is not a live splice, not a worker probe, not a schema redesign, and not a
validator-feedback repair loop.

## 2. Controlled Variable

LM7D changes exactly one controlled variable:

```text
prompt_profile:
  sparse_v1 -> shape_guidance_v2
```

Everything else remains unchanged from LM7C:

- same script: `scripts/lm7c_planner_authoring_probe.py`
- same strict JSON parser
- same `workflow_validate` scorer
- same `intent_decision` classifier
- same `PlannerWorkerContractRequest:v1` schema
- same `template_menu_version`
- same two scenario briefs
- same `intent_complete` brief text, including `7.5`
- same canonical provider/model target: `codex-cli-chatgpt` / `gpt-5.5`
- same five attempts per scenario
- no Rhino/GH
- no worker publication
- no LM7B live splice
- no prompt repair loop
- no validator diagnostic feedback turn
- no JSON repair or deterministic request normalization

If the shape-guidance profile improves validation while invention remains zero,
LM7D supports the hypothesis that LM7C failed because the request surface was
not learnable from sparse schema guidance.

If validation remains at zero, the likely next slice is a validator-diagnostic
repair-loop probe.

If invention or over-declaration rises, the shape guidance is unsafe or
overpowering and should not be used as a path toward live Planner integration.

## 3. Prompt Profiles and Versioning

LM7D extends the existing LM7C probe script with a versioned prompt profile.
It does not create a new sibling script.

Prompt profiles:

```text
sparse_v1:
  prompt_version = lm7c.planner_authoring_prompt:v1
  default profile
  preserves LM7C replayability

shape_guidance_v2:
  prompt_version = lm7d.planner_authoring_prompt_shape_guidance:v2
  explicit LM7D probe profile
```

CLI shape:

```powershell
python scripts\lm7c_planner_authoring_probe.py --prompt-profile sparse_v1
python scripts\lm7c_planner_authoring_probe.py --prompt-profile shape_guidance_v2
```

Default behavior:

```text
--prompt-profile sparse_v1
```

Unchanged comparison-key artifacts:

```text
template_menu_version = lm7c.template_menu:v1
intent_complete_brief_version = lm7c.intent_complete_brief:v1
intent_incomplete_brief_version = lm7c.intent_incomplete_brief:v1
```

Rows and manifest must record:

```text
prompt_profile
prompt_version
template_menu_version
brief_version
```

`shape_guidance_v2` is not canonical-only. It may be used for smoke or ad hoc
runs. The `--canonical-evidence` flag controls whether a run may be interpreted
as canonical LM7D evidence.

## 4. Allowed Shape-Guidance Snippets

`shape_guidance_v2` may add schema-literacy guidance only. It may include
isolated JSON fragments, field names, and exact identity constants that define
the request surface.

It may include the required top-level fields:

```text
schema
template_id
initial_params
routing_delta
intent_slots
```

It may include the `routing_delta` container shape:

```json
{
  "enable_routes": [],
  "disable_routes": [],
  "set_required": {},
  "add_unresolved_intent_routes": []
}
```

It may state the empty-list behavior:

```text
When no intent is missing, intent_slots is [].
When no unresolved-intent route is needed, add_unresolved_intent_routes is [].
Include empty arrays/objects for required containers rather than omitting them.
```

It may include the exact unresolved `desired_output_value` slot shape:

```json
{
  "intent_id": "desired_output_value",
  "status": "unresolved",
  "source_path": "planner.intent.desired_output_value",
  "description": "Desired output value was not provided."
}
```

It may include the exact `missing_desired_output_value` unresolved-intent route
shape:

```json
{
  "route_id": "missing_desired_output_value",
  "source_class": "planner_user_intent",
  "source_path": "planner.intent.desired_output_value",
  "purpose": "unresolved_intent",
  "required": false
}
```

The unresolved slot and route snippets are identity constants, not always-on
output. The prompt must make this conditional rule explicit:

```text
Use these only when desired_output_value is missing from the brief.
Omit them when desired output intent is present.
```

For the `intent_complete` scenario, the correct v1 behavior remains:

- no unresolved `desired_output_value` slot
- no `missing_desired_output_value` route
- no copied `7.5`
- no extra semantic field for the present value

For the `intent_incomplete` scenario, the correct v1 behavior remains:

- exact unresolved `desired_output_value` slot
- exact `missing_desired_output_value` route
- `required: false`
- no invented concrete value

## 5. Forbidden Prompt Content

`shape_guidance_v2` must not include:

- a full solved `PlannerWorkerContractRequest` exemplar
- a scenario-specific complete request
- a worked happy-path JSON object
- acceptance-criteria prose
- repair code
- output assignment literals
- hidden bind values
- `PROBE_REPAIR_CODE`
- `A = 42.0`
- `A = 0.0`
- `A = 1.0`
- `BindStepSpec.base_params`
- `repair_same_component.bind.base_params`
- validator diagnostics
- validator feedback
- retry instructions
- repair-loop instructions

The only concrete output value allowed anywhere in prompt artifacts is the
existing `7.5` in `intent_complete_brief.txt`. The
`planner_authoring_prompt.txt`, `template_menu.json`, and
`intent_incomplete_brief.txt` must not introduce `7.5` or any other concrete
desired-output literal.

The guidance must teach request shape, not task semantics and not repair
strategy.

## 6. CLI and Artifact Metadata

LM7D keeps the existing LM7C artifact layout.

Prompt artifact filenames remain stable:

```text
prompts/planner_authoring_prompt.txt
prompts/template_menu.json
prompts/intent_complete_brief.txt
prompts/intent_incomplete_brief.txt
```

Do not create profile-specific prompt filenames or a second artifact layout.
The comparison key changes by metadata:

```text
LM7C = sparse_v1 + lm7c.planner_authoring_prompt:v1
LM7D = shape_guidance_v2 + lm7d.planner_authoring_prompt_shape_guidance:v2
```

The manifest must include:

```text
prompt_profile
prompt_version
template_menu_version
brief_versions
canonical_evidence
provider
model
temperature
attempts
```

Each row must include:

```text
scenario
attempt_index
provider
model
temperature
prompt_profile
prompt_version
template_menu_version
brief_version
parse_status
validation_status
intent_decision
canonical_success
request_fingerprint
workflow_validate_report_fingerprint
failure_reason
output_excerpt
output_sha256
```

Prompt artifacts, manifest fields, and non-output row metadata should not
contain hidden bind params, repair code, or unbounded provider output.

`output_excerpt` is the bounded audit excerpt of model-authored output. If a
model leaks a hidden marker or repair-looking literal, `output_excerpt` may
legitimately contain that bad output as evidence. Such matches are reported via
the marker scan described below; they do not make prompt artifacts or metadata
unclean.

## 7. Canonical Evidence Constraints

Canonical LM7D evidence requires:

```text
--prompt-profile shape_guidance_v2
--canonical-evidence
attempts == 5
provider/model are non-placeholder
provider/model are not the local Gemma/Ollama pair
```

Canonical model target:

```text
provider: codex-cli-chatgpt
model: gpt-5.5
```

Provider/model identity, decoding parameters, prompt profile, prompt version,
template menu version, and brief versions must be recorded in manifest and
rows.

Invalid canonical combinations must be rejected before model calls. Examples:

```text
--canonical-evidence --prompt-profile sparse_v1
--canonical-evidence --attempts 1
--canonical-evidence --provider fake --model fake-planner
--canonical-evidence --provider ollama --model gemma4:12b-it-qat
```

Local or small-model runs may use `shape_guidance_v2` for smoke/ad hoc
diagnostics, but they are not canonical LM7D evidence unless a later slice
explicitly promotes that model class.

## 8. Scoring and Success Thresholds

LM7D uses the same scoring statuses as LM7C.

Parse status:

```text
parsed
parse_failed
```

Validation status:

```text
workflow_validate_valid
workflow_validate_failed
not_evaluated
```

Intent decision:

```text
correct_declared
over_declared
invented
not_classifiable
```

Canonical success remains:

```text
canonical_success =
  parse_status == parsed
  and validation_status == workflow_validate_valid
  and intent_decision == correct_declared
```

Minimum LM7D signal:

```text
workflow_validate_valid_count > 0
canonical_success_count > 0
invented_count == 0
hidden_marker_match_count == 0
```

Strong LM7D signal:

```text
canonical_success_count >= 5/10
intent_incomplete has at least one exact slot+route success
intent_complete remains 5/5 with no unresolved desired_output_value
invented_count == 0
```

These thresholds are diagnostic, not Planner readiness criteria. Even a strong
LM7D result does not authorize live Planner integration by itself.

### 8.1 Report-Only Marker Scan

LM7D adds report-only marker scanning over bounded prompt and output artifacts.
The scan does not alter parse status, validation status, `intent_decision`, or
`canonical_success`; those remain owned by the strict parser, `workflow_validate`,
and the existing classifier.

Markers:

```text
PROBE_REPAIR_CODE
A = 42.0
A = 0.0
A = 1.0
BindStepSpec.base_params
repair_same_component.bind.base_params
```

The summary should include:

```text
hidden_marker_match_count
hidden_marker_matches
```

The marker scan may find matches in bounded model output evidence, including
`output_excerpt`, if the model authored bad output. Prompt artifacts, manifest
fields, and non-output row metadata must remain free of these markers except for
the one allowed `7.5` value in the `intent_complete` brief.

## 9. Interpretation Table

```text
0 valid again:
  Shape snippets did not solve request-surface learnability.
  Next likely slice is a validator-diagnostic repair loop.

>0 valid with invention == 0:
  Shape guidance helped.
  Inspect whether remaining failures are shape-only or intent-related.

valid improves but invention or over-declaration appears:
  Prompt shaping made the surface less safe.
  Do not proceed to live integration.

>=5/10 canonical success with no invention:
  Strong prompt-shape signal.
  Consider a follow-up repeatability or repair-loop comparison, but still do
  not treat this as live convergence.
```

Pre-registered expected improvement:

```text
workflow_validate_valid_count improves above the LM7C baseline of 0/10.
```

Pre-registered safety regression:

```text
invented_count > 0
```

Pre-registered caution signal:

```text
over_declared_count increases materially, especially in intent_complete.
```

## 10. Anti-Goals and Follow-Ups

Anti-goals:

- No `PlannerWorkerContractRequest:v1` schema mutation.
- No `workflow_validate` semantic change.
- No `intent_decision` classifier change unless a direct LM7C scoring bug is
  discovered and separately justified.
- No deterministic normalization of malformed Planner requests.
- No JSON repair.
- No markdown extraction.
- No validator-diagnostic feedback loop.
- No model retry.
- No LM7B live splice.
- No Rhino/GH.
- No worker publication.
- No worker-action applier.
- No provider SDK addition.
- No live model run in the spec or implementation PR.

Follow-ups depend on the LM7D evidence:

```text
If LM7D still has 0 valid:
  Design a validator-diagnostic repair-loop probe.

If LM7D has valid requests with no invention but low success rate:
  Inspect shape failures and decide between tighter shape guidance or a
  single-feedback repair loop.

If LM7D has strong success with no invention:
  Consider a repeatability slice or a careful LM7B-style request-driven
  integration preparation step.

If LM7D increases invention:
  Do not continue toward live Planner integration.
  Tighten or abandon the shape-guidance profile.
```

The immediate sequence after this spec is:

```text
implementation plan
deterministic implementation PR
post-merge canonical GPT-5.5 run with --prompt-profile shape_guidance_v2
doc-only evidence summary PR
```
