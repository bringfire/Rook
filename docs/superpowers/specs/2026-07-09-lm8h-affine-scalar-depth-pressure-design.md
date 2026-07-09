# LM8H Affine Scalar Depth Pressure Design

Status: design checkpoint for review

Date: 2026-07-09

## 1. Purpose

LM8H is the next same-family pressure slice after LM8G.

The scalar line now has:

- LM8C: GH-native scalar identity arrival once.
- LM8F: one non-identity scalar transform arrival once:

```text
observed_output = editable_value + 1.5
expected_output = 7.5
worker-derived editable value = 6.0
```

- LM8G: repeatability of the LM8F fixture:

```text
5/5 accepted
worker action values all 6.0
no hidden repair marker matches
```

LM8H keeps the same scalar family, same worker model, same worker action, same
trusted applier boundary, and same verifier-floor doctrine. It increases only
the scalar relationship depth:

```text
observed_output = editable_value * factor_value + offset_value
```

The controlled claim is:

```text
The bounded GH-native scalar worker can infer one affine scalar edit value from
source-owned relationship evidence and reach verifier-floor acceptance, while
topology remains deterministic and worker authority remains one scalar value
only.
```

LM8H is not a new family, not topology authorship, not `gh_edit`, not Planner
competence, not a math benchmark, and not repeatability evidence.

## 2. Relationship To LM8F And LM8G

LM8H is a scalar-depth pressure slice, not a repeatability wrapper.

```text
LM8F = one additive scalar relationship
LM8G = N=5 repeatability of LM8F
LM8H = one affine scalar relationship
```

LM8H must not be folded into LM8G. LM8G remains the repeatability record for
the additive LM8F fixture.

LM8H should reuse the scalar-family protocol shape proven by LM8C/LM8F:

```text
script-owned live fixture
-> scalar runtime readiness
-> worker-visible scalar evidence
-> one Gemma worker publication turn
-> draft_gh_set_value_params {"value": number}
-> scalar applier binds trusted editable slider GUID
-> gh_set_value
-> gh_solve / verifier settle
-> gh_inspect_output verifier floor
```

## 3. Scope

In scope:

- same-family affine scalar pressure
- deterministic script-owned GH fixture topology
- direct GH tools:
  - `rhino_ping`
  - `gh_document_new`
  - `gh_library` search for Multiplication and Addition
  - `gh_create_slider`
  - `gh_create_component`
  - `gh_connect`
  - `gh_solve`
  - `gh_get_value`, for editable/factor/offset slider prechecks only
  - `gh_inspect_output`
  - `gh_set_value`
- one editable slider
- one factor slider/constant source
- one offset slider/constant source
- one Multiplication component
- one Addition component
- one observed output: final Addition output `R`
- scalar runtime readiness gate
- affine-aware scalar evidence packet
- one Gemma QAT worker publication turn
- scalar applier staging trusted editable slider GUID + worker value
- verifier-floor acceptance via `gh_inspect_output Addition R`
- deterministic implementation plan and fake-tool tests later
- post-merge single canonical live run later
- separate doc-only evidence summary PR after the live run

Out of scope:

- no Planner model
- no model-authored template selection
- no worker-authored topology, components, wires, tools, code, scripts, or GUIDs
- no `gh_edit`
- no retry
- no N=5
- no model panel
- no script repair
- no third task family
- no topology repair
- no batch edit competence
- no broad arithmetic benchmark framing
- no live run in the implementation PR
- no raw `probe_runs/` artifacts committed

If direct GH tools cannot build the affine fixture, LM8H stops as
gate/tooling evidence. Any `gh_edit` fixture fallback belongs to a separate
reviewed slice.

## 4. Canonical Fixture

Canonical LM8H fixture:

```text
editable slider value: 2.0
factor slider value: 2.0
offset slider value: 1.5
projection: observed_output = editable_value * factor_value + offset_value
current observed output: 5.5
expected observed output: 7.5
hidden expected worker value: 3.0
```

The hidden expected worker value is for deterministic test/oracle analysis
only. It must not appear in worker-visible acceptance criteria or prompt text
as an instruction.

The deterministic live setup is:

```text
rhino_ping
gh_document_new
gh_library(search="multiplication")
gh_library(search="addition")
gh_create_slider(nickname="LM8H_Editable", value=2.0)
gh_create_slider(nickname="LM8H_Factor", value=2.0)
gh_create_slider(nickname="LM8H_Offset", value=1.5)
gh_create_component(Multiplication)
gh_create_component(Addition)
gh_connect editable slider -> Multiplication A
gh_connect factor slider -> Multiplication B
gh_connect Multiplication R -> Addition A
gh_connect offset slider -> Addition B
gh_solve
gh_get_value editable slider
gh_get_value factor slider
gh_get_value offset slider
gh_inspect_output Addition R
```

`gh_library(search="multiplication")` must resolve to an exact, active,
non-deprecated Multiplication component. If the library result has no active
exact Multiplication match, LM8H should stop as:

```text
decision = gate_failed
reason = affine_fixture_failed:active_multiplication_component_missing
```

The implementation plan should include a deterministic regression for
deprecated-first Multiplication library results, using the existing
Multiplication active/deprecated alias coverage pattern in
`mcp_server/tests/test_server_component_deprecation.py`.

`gh_get_value` is allowed only to confirm the three scalar source values before
worker publication. `gh_inspect_output Addition R` is the observed scalar floor.
LM8H must not use `gh_get_value` as the final verifier because the output under
test is the downstream affine result, not any source slider value.

## 5. Direct-Tool Fixture Gate

LM8H v1 should build the real affine fixture using direct GH tools:

```text
editable slider -> Multiplication A
factor slider -> Multiplication B
Multiplication R -> Addition A
offset slider -> Addition B
Addition R -> observed output
```

Rejected alternatives:

- virtual relationship with no live Multiplication/Addition fixture
- worker-authored topology or wiring
- `gh_edit` fixture construction
- script component that hides the affine relationship
- verifier that reads the editable slider rather than Addition `R`

Reason:

```text
LM8H should test scalar relationship interpretation against a live GH-native
floor, not a prompt-only formula and not a topology-authoring task.
```

## 6. Topology Boundary

LM8H may create and wire the affine fixture deterministically.

LM8H must not expose topology authorship to the worker.

The worker sees only scalar relationship evidence and may publish only:

```json
{
  "action_id": "draft_gh_set_value_params",
  "input": {
    "value": "<finite number>"
  }
}
```

That JSON shows the allowed action shape, not the expected value.

The worker action schema remains:

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
- scripts
- `gh_edit` batches

## 7. Source Facts

Worker-visible facts should be source-owned and bounded:

```text
current_editable_value = 2.0
factor_value = 2.0
offset_value = 1.5
projection = observed_output = editable_value * factor_value + offset_value
current_observed_output = 5.5
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

factor_value
  source_class: expected_output_contract
  owner: workflow/template/task contract
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

The implementation plan should decide whether to extend the existing
`gh_scalar_transform_expectation` source packet or introduce an affine-specific
packet. Either way, source paths for `factor_value`, `offset_value`,
`projection`, `current_editable_value`, and `current_observed_output` must be
bounded and exact.

The trusted editable target GUID remains applier-only runtime authority.
`fixture_anchor` remains evidence context only and must not become acceptance
criteria authority.

The factor and offset values are source-owned task facts. The live factor and
offset sliders are deterministic fixture carriers for those facts. If
`gh_get_value` observes a factor or offset value that does not match the
task-contract fact, LM8H should stop at `gate_failed` before worker
publication.

## 8. Worker-Visible Evidence

LM8H should use an affine-aware scalar evidence packet rather than the LM8F
additive packet unchanged.

Packet fields should include:

```text
current_editable_value
factor_value
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
  "projection_id": "editable_times_factor_plus_offset",
  "description": "observed_output = editable_value * factor_value + offset_value",
  "editable_variable": "editable_value",
  "factor_variable": "factor_value",
  "offset_variable": "offset_value",
  "output_variable": "observed_output"
}
```

Worker-visible acceptance criteria may say:

```text
Set the editable scalar value so the inspected GH output equals the
source-owned expected output value.

Use the source-owned scalar projection relationship:
observed_output = editable_value * factor_value + offset_value.
```

Worker-visible acceptance criteria must not say:

```text
set editable value to 3.0
use 3.0
expected worker value is 3.0
7.5 - 1.5 divided by 2.0 is 3.0
```

The derived editable target value belongs in deterministic test expectations
and evidence interpretation, not in the worker-visible criteria.

## 9. Scalar Runtime Readiness

LM8H should keep the scalar-family gate name:

```text
scalar_runtime_ready
```

Definition:

```text
scalar_runtime_ready =
  static source routing valid
  and Multiplication fixture created
  and Addition fixture created
  and editable slider + factor slider connected to Multiplication A/B
  and Multiplication R connected to Addition A
  and offset slider connected to Addition B
  and gh_solve completed or was scheduled successfully
  and gh_get_value editable slider yields current_editable_value 2.0
  and gh_get_value factor slider yields factor_value 2.0
  and gh_get_value offset slider yields offset_value 1.5
  and gh_inspect_output Addition R yields current_observed_output 5.5
  and initial projection invariant holds:
      observed_output ~= current_editable_value * factor_value + offset_value
  and affine scalar source extraction succeeds
  and affine scalar packet assembly succeeds
```

Fixture or tool setup failure is:

```text
decision = gate_failed
```

and is not worker evidence.

LM8H must not claim LM5X routability for scalar routes. As in LM8C and LM8F,
scalar runtime readiness is the honest live gate.

## 10. Worker And Action Flow

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
scripts, topology fields, and extra action input keys.

## 11. Verifier

After a staged worker action:

```text
gh_set_value(editable_slider_guid, worker_value)
gh_solve, if needed
poll gh_inspect_output(addition_guid, param="R") using the bounded settle policy
```

Acceptance:

```text
accepted iff inspected final Addition R output == 7.5 within tolerance
```

V1 tolerance:

```text
1e-9
```

`gh_set_value` receipt success is diagnostic. As established by LM8C/LM8E and
LM8F/LM8G, verifier-floor observation is the acceptance authority after a
completed set attempt.

Decision metadata should record:

- worker action value
- factor value
- offset value
- expected output value
- observed output before
- observed output after
- scalar tolerance
- verifier attempt count
- match result

## 12. Terminal Decisions

LM8H should reuse LM8C/LM8F terminal categories:

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
  extraction, packet assembly, or initial Addition `R` inspection failed before
  the worker path.
- `publication_failed`: worker publication failed or hidden marker gate failed.
- `worker_declined`: worker published a valid non-action response.
- `rejected`: action existed but applier rejected, live set/solve/inspect could
  not complete, or final inspected output did not match `7.5`.
- `accepted`: final inspected Addition `R` output matched `7.5` within
  tolerance.

## 13. Artifact Policy

Use a separate run directory:

```text
probe_runs/lm8h-<timestamp>-<sha>/
```

Suggested artifacts:

```text
manifest.json
fixture_setup_summary.json
fixture_failure_summary.json, only if fixture setup fails
scalar_sources.json
acceptance_criteria_packet.json
worker_visible_acceptance_criteria.json
worker_request_payload.json
worker_publication_row.json, if worker reached
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
- verifier summaries: GUID presence/hash only
- curated docs: no raw GUIDs

Marker policy:

- no `PROBE_REPAIR_CODE`
- no `A = 42.0`
- no repair bind-param markers
- no C# repair tool leakage
- no `gh_update_script`
- no worker-visible raw GUID
- no `gh_edit`

Derived-value policy for `3.0`:

- `3.0` is the hidden deterministic expected worker value for the canonical
  fixture.
- `3.0` must not appear in pre-publication worker-visible/source/request
  artifacts:
  - `scalar_sources.json`
  - `acceptance_criteria_packet.json`
  - `worker_visible_acceptance_criteria.json`
  - `worker_request_payload.json`
- `3.0` is allowed after worker publication if the model authors it:
  - `worker_action.json`
  - `live_set_value_summary.json`
  - `verify_scalar_output_summary.json`
  - bounded `decision.json` worker-action/value fields
- A pre-publication occurrence of `3.0` should fail deterministic tests because
  it would leak the derived answer into the worker-facing surface.

LM8H may record worker-authored scalar values in local ignored artifacts and
bounded decision excerpts.

## 14. Canonical Evidence

Canonical LM8H evidence is exactly one post-merge live attempt from synced
`main`.

Canonical conditions:

```text
model == gemma4:12b-it-qat
direct Ollama worker path
attempts == 1
editable initial value == 2.0
factor value == 2.0
offset value == 1.5
current observed output == 5.5
expected output == 7.5
projection == editable_value * factor_value + offset_value
worker retry disabled
Planner model absent
worker topology authority absent
gh_edit absent
```

No live run belongs in the implementation PR.

## 15. Interpretation

If LM8H passes:

```text
The scalar family handles one affine relationship once.
```

If LM8H fails after `scalar_runtime_ready` and worker publication:

```text
Treat it as scalar affine-depth evidence.
```

If LM8H fails before the worker path:

```text
Treat it as fixture/runtime gate evidence, not worker evidence.
```

LM8H does not prove:

- repeatability
- third-family generalization
- topology or wiring repair
- batch edit reliability
- Planner competence
- broad arithmetic or symbolic reasoning
- general math benchmark performance
- complexity scaling

It only asks whether the existing bounded worker protocol can survive one
same-family affine scalar relationship where the worker's action value differs
from the expected output value and requires using both factor and offset facts.

## 16. Next Steps

After spec approval:

1. Write an implementation plan.
2. Implement deterministic tests and a sibling live script only if the plan
   justifies reuse without blurring LM8F/LM8G identity.
3. Run no live attempt in the implementation PR.
4. After merge, run one canonical LM8H live attempt from synced `main`.
5. Write a separate doc-only evidence summary PR.
