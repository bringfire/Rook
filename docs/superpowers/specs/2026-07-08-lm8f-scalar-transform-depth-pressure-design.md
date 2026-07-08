# LM8F Scalar Transform Depth Pressure Design

Status: design checkpoint for review

Date: 2026-07-08

## 1. Purpose

LM8F is the first same-family pressure slice after LM8C/LM8D/LM8E.

LM8C proved one live GH-native scalar-family arrival:

```text
identity slider fixture
-> source-owned expected scalar value
-> Gemma worker publishes draft_gh_set_value_params
-> trusted applier binds slider GUID
-> gh_set_value
-> verifier-floor scalar observation succeeds
```

LM8F keeps the same family and worker action, but adds one small scalar
relationship:

```text
observed_output = editable_value + offset_value
```

The controlled claim is:

```text
The bounded worker protocol can handle one GH-native scalar transform where the
worker must infer an editable scalar value from source-owned relationship
evidence, while topology remains deterministic and worker authority remains one
scalar value only.
```

LM8F is not a new family, not topology authorship, not batch editing, and not
complexity scaling beyond one scalar relationship.

## 2. Context

The prior scalar line established:

- LM8A: GH-native scalar expectation as the second family.
- LM8B: deterministic scalar source/routing/assembler/applier seams.
- LM8C: first live identity scalar arrival.
- LM8D: scalar action affordance clarity for `draft_gh_set_value_params`.
- LM8E/PR #463: verifier-floor acceptance after completed `gh_set_value`
  attempts.
- PR #465: GH knowledge wrapper false-receipt fix for `gh_set_value`.

LM8F should consume those seams and change only the scalar task pressure.

## 3. Scope

In scope:

- same-family scalar transform pressure
- deterministic script-owned GH fixture topology
- direct GH tools:
  - `rhino_ping`
  - `gh_document_new`
  - `gh_library` search for Addition
  - `gh_create_slider`
  - `gh_create_component`
  - `gh_connect`
  - `gh_solve`
  - `gh_inspect_output`
  - `gh_get_value`, for editable-slider precheck only
  - `gh_set_value`
- one editable slider
- one offset slider/constant source
- one Addition component
- one observed output: Addition output `R`
- scalar runtime readiness gate
- transform-aware scalar evidence packet
- one Gemma QAT worker publication turn
- scalar applier staging trusted editable slider GUID + worker value
- verifier-floor acceptance via `gh_inspect_output Addition R`
- deterministic tests and fakes in the implementation PR
- post-merge single canonical live run
- separate doc-only evidence summary PR after the live run

Out of scope:

- no Planner model
- no model-authored template selection
- no worker-authored topology, components, wires, tools, code, or GUIDs
- no `gh_edit`
- no retry
- no N=5
- no worker model panel
- no script repair
- no third task family
- no missing-wire or topology repair
- no raw probe artifacts committed
- no live run in the implementation PR

## 4. Canonical Fixture

Canonical LM8F fixture:

```text
editable slider value: 2.0
offset slider value: 1.5
projection: observed_output = editable_value + offset_value
current observed output: 3.5
expected observed output: 7.5
hidden expected worker value: 6.0
```

The hidden expected worker value is for deterministic test/oracle analysis
only. It must not appear in worker-visible acceptance criteria or prompt text as
an instruction.

The deterministic live setup is:

```text
rhino_ping
gh_document_new
gh_library(search="addition")
gh_create_slider(nickname="LM8F_Editable", value=2.0)
gh_create_slider(nickname="LM8F_Offset", value=1.5)
gh_create_component(Addition)
gh_connect editable slider -> Addition A
gh_connect offset slider -> Addition B
gh_solve
gh_get_value editable slider
gh_inspect_output Addition R
```

`gh_get_value` is allowed only to confirm the editable slider's current value
for source extraction. `gh_inspect_output Addition R` is the observed scalar
floor. LM8F must not use `gh_get_value` as the verifier because the output
under test is no longer the slider value itself.

## 5. Topology Boundary

LM8F may create and wire the transform fixture deterministically.

LM8F must not expose topology authorship to the worker.

The worker sees only scalar relationship evidence and may publish only:

```json
{
  "action_id": "draft_gh_set_value_params",
  "input": {
    "value": "<finite number>"
  }
}
```

That JSON shows the allowed action shape, not the expected value. The worker
action schema remains:

```json
{
  "type": "object",
  "required": ["value"],
  "properties": {
    "value": {"type": "number"}
  },
  "additionalProperties": false
}
```

The worker must not author:

- target GUID
- component ids
- tool names
- wires
- topology edits
- code
- `gh_edit` batches

## 6. Source Facts

Worker-visible facts should be source-owned and bounded:

```text
current_editable_value = 2.0
offset_value = 1.5
projection = observed_output = editable_value + offset_value
current_observed_output = 3.5
expected_output_value = 7.5
editable target contract = trusted fixture anchor context, GUID omitted
```

Source ownership:

```text
expected_output_value
  source_class: expected_output_contract
  owner: workflow/template/task contract
  purpose: acceptance_criteria

current_observed_output
  source_class: receipt_observation
  owner: live Addition R precheck
  purpose: acceptance_criteria

current_editable_value
  source_class: receipt_observation
  owner: live editable slider precheck
  purpose: evidence_context

offset_value
  source_class: expected_output_contract
  owner: workflow/template/task contract
  purpose: evidence_context

projection
  source_class: expected_output_contract
  owner: workflow/template/task contract
  purpose: acceptance_criteria | evidence_context

editable target contract
  source_class: fixture_anchor
  owner: create receipt scalar anchor
  purpose: evidence_context only
```

The implementation plan should choose exact bounded source paths for
`current_editable_value`, `offset_value`, and `projection`, then add static
allowlist tests for those paths. `offset_value` and `projection` are
source-owned task facts, not fixture-anchor authority. The authority must not
move to worker prompt prose or hidden bind params.

## 7. Worker-Visible Evidence

LM8F should use a transform-aware scalar evidence packet rather than the LM8C
identity packet unchanged.

Packet fields should include:

```text
current_editable_value
offset_value
current_observed_output
expected_output_value
projection
editable_value_contract
recommended_action_id
action_selection_contract
acceptance_criteria
```

Allowed projection field:

```json
{
  "projection_id": "editable_plus_offset",
  "description": "observed_output = editable_value + offset_value",
  "editable_variable": "editable_value",
  "offset_variable": "offset_value",
  "output_variable": "observed_output"
}
```

Worker-visible acceptance criteria may say:

```text
Set the editable scalar value so the inspected GH output equals the
source-owned expected output value.

Use the source-owned scalar projection relationship:
observed_output = editable_value + offset_value.
```

Worker-visible acceptance criteria must not say:

```text
set editable value to 6.0
use 6.0
expected worker value is 6.0
```

The derived editable target value belongs in deterministic test expectations
and evidence interpretation, not in the worker-visible criteria.

## 8. Scalar Runtime Readiness

LM8F should keep the LM8C naming:

```text
scalar_runtime_ready
```

Definition:

```text
scalar_runtime_ready =
  static source routing valid
  and Addition fixture created
  and editable slider + offset slider connected to Addition A/B
  and gh_solve completed or was scheduled successfully
  and gh_get_value editable slider yields current_editable_value 2.0
  and gh_inspect_output Addition R yields current_observed_output 3.5
  and scalar transform source extraction succeeds
  and scalar transform packet assembly succeeds
```

Fixture or tool setup failure is:

```text
decision = gate_failed
```

and is not worker evidence.

If direct tools cannot build the deterministic transform fixture, LM8F stops as
gate/tooling evidence. Any `gh_edit` fallback belongs to a separate reviewed
slice.

LM8F must not claim LM5X routability for scalar routes. As in LM8C, scalar
runtime readiness is the honest live gate.

## 9. Worker And Action Flow

Canonical worker:

```text
model: gemma4:12b-it-qat
provider path: direct Ollama /api/chat
attempts: 1
retry: disabled
```

Allowed action:

```text
draft_gh_set_value_params
```

Allowed input:

```json
{"value": <finite number>}
```

The scalar applier binds:

```text
trusted editable slider GUID from live fixture anchor
worker-authored value from action input
```

The applier must continue to reject worker-authored GUIDs, tool names, code,
topology fields, and extra action input keys.

## 10. Verifier

After a staged worker action:

```text
gh_set_value(editable_slider_guid, worker_value)
gh_solve, if needed
gh_inspect_output(addition_guid, param="R")
```

Acceptance:

```text
accepted iff inspected Addition R output == 7.5 within tolerance
```

`gh_set_value` receipt success is diagnostic. As established by LM8E/PR #463
and PR #465, verifier-floor observation is the acceptance authority after a
completed set attempt.

## 11. Terminal Decisions

LM8F should reuse LM8C terminal categories:

```text
preflight_failed
gate_failed
publication_failed
worker_declined
rejected
accepted
```

Meanings:

- `preflight_failed`: Rhino/GH setup failed before fixture creation.
- `gate_failed`: deterministic fixture construction, static routing, source
  extraction, packet assembly, or initial `gh_inspect_output` failed before the
  worker path.
- `publication_failed`: worker publication failed or hidden marker gate failed.
- `worker_declined`: worker published a valid non-action response.
- `rejected`: action existed but applier rejected, live set/solve/inspect could
  not complete, or final inspected output did not match `7.5`.
- `accepted`: final inspected Addition `R` output matched `7.5` within
  tolerance.

## 12. Artifact Policy

Use a separate run directory:

```text
probe_runs/lm8f-<timestamp>-<sha>/
```

Suggested artifacts:

```text
manifest.json
fixture_setup_summary.json
scalar_sources.json
acceptance_criteria_packet.json
worker_visible_acceptance_criteria.json
worker_request_payload.json
worker_publication_row.json
worker_action.json, action only
live_set_value_summary.json, if dispatched
verify_scalar_output_summary.json, if verifier ran
decision.json
```

GUID policy:

- worker-visible/source artifacts: no raw trusted GUID
- `decision.json`: GUID presence/hash only
- live setup and set-value summaries: may include raw GUIDs for ignored local
  audit
- curated docs: no raw GUIDs

Marker policy:

- no `PROBE_REPAIR_CODE`
- no `A = 42.0`
- no repair bind-param markers
- no C# repair tool leakage
- no `gh_update_script`
- no worker-visible raw GUID

LM8F may record worker-authored scalar values in local ignored artifacts and
bounded decision excerpts.

## 13. Canonical Evidence

Canonical LM8F evidence is exactly one post-merge live attempt from synced
`main`.

Canonical conditions:

```text
model == gemma4:12b-it-qat
direct Ollama worker path
attempts == 1
editable initial value == 2.0
offset value == 1.5
current observed output == 3.5
expected output == 7.5
projection == editable_value + offset_value
worker retry disabled
Planner model absent
worker topology authority absent
gh_edit absent
```

No live run belongs in the implementation PR.

## 14. Interpretation

If LM8F passes:

```text
The scalar family handles one non-identity relationship once.
```

If LM8F fails after `scalar_runtime_ready` and worker publication:

```text
Treat it as scalar-depth evidence.
```

If LM8F fails before the worker path:

```text
Treat it as fixture/runtime gate evidence, not worker evidence.
```

LM8F does not prove:

- repeatability
- third-family generalization
- topology or wiring repair
- batch edit reliability
- Planner competence
- broad arithmetic or symbolic reasoning
- complexity scaling

It only asks whether the existing bounded worker protocol can survive one
same-family scalar relationship where the worker's action value differs from
the expected output value.

## 15. Next Steps

After spec approval:

1. Write an implementation plan.
2. Implement deterministic tests and a sibling live script or LM8C-profiled
   script only if the plan justifies reuse without blurring LM8C identity.
3. Run no live attempt in the implementation PR.
4. After merge, run one canonical LM8F live attempt from synced `main`.
5. Write a separate doc-only evidence summary PR.
