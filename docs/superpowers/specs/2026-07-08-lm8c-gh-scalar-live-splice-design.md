# LM8C GH Scalar Live Splice Design

Status: design checkpoint for review

Date: 2026-07-08

## 1. Purpose

LM8C is the first live probe for the second tiny task family introduced by
LM8A and prototyped deterministically by LM8B:

```text
GH-native scalar solve/output expectation
```

The controlled claim is:

```text
A deterministic scalar-family request/template source can create a live GH
scalar fixture, assemble worker-visible criteria from source-owned scalar
facts, let the bounded worker publish draft_gh_set_value_params, stage trusted
GUID + worker value through the scalar applier, dispatch the live scalar
mutation, and reach a receipted verify_scalar_output terminal outcome.
```

LM8C tests second-family live transfer. It does not test complexity scaling,
Planner-model authorship, router behavior, retry policy, topology repair, or
batch editing.

## 2. Proven Inputs

LM8C starts from these already-landed seams:

- LM5/LM6/LM7 worker protocol:
  - neutral worker-turn context rendering
  - two-pass worker publication
  - one-turn worker action/refusal/observation discipline
  - hidden-answer publication guard
- LM8A design:
  - expected scalar value is `expected_output_contract`
  - observed scalar value is `receipt_observation`
  - editable target context is `fixture_anchor`
  - trusted target GUID is applier-only
- LM8B deterministic prototype:
  - static source routing support for `expected_output_contract`,
    `receipt_observation`, and `fixture_anchor`
  - `extract_gh_scalar_expectation_sources(...)`
  - `assemble_gh_scalar_expectation_packet(...)`
  - `project_gh_scalar_expectation_legacy(...)`
  - `apply_gh_scalar_value_action_to_node(...)`

LM8C should consume these seams rather than reimplementing them.

## 3. Scope

In scope:

- new sibling live script:

```text
scripts/lm8c_gh_scalar_expectation_live_probe.py
```

- script-owned live preflight:
  - `rhino_ping`
  - `gh_document_new`
- direct GH scalar tools:
  - `gh_create_slider`
  - `gh_get_value`
  - `gh_set_value`
  - `gh_solve`, only if implementation needs a solve tick before verification
- identity scalar fixture:
  - one Number Slider
  - initial value `0.0`
  - expected output value `7.5`
  - editable scalar value equals observed output value
- static source-routing validation
- scalar runtime readiness gate
- scalar worker-visible evidence packet
- one Gemma QAT worker publication turn
- scalar applier staging
- live scalar mutation
- verifier-floor scalar acceptance
- bounded local run artifacts
- deterministic tests and fakes in the implementation PR

Out of scope:

- no Planner model
- no model-authored template selection
- no `PlannerWorkerContractRequest` schema changes
- no production workflow-template integration
- no generic PlanGraph runner
- no LM5X routability claim for scalar routes
- no retry
- no N=5
- no `gh_edit`
- no wiring or topology mutation
- no script repair
- no worker prompt/protocol change
- no new worker model panel
- no live run in the implementation PR

## 4. Script Shape

LM8C should be a new sibling script, not a mode of LM6A, LM7B, or LM7E.

Reason:

```text
LM6/LM7 scripts own the C# repair family and Planner-request provenance chain.
LM8C owns the scalar family live fixture, scalar runtime readiness gate, scalar
worker evidence, scalar action apply, live gh_set_value dispatch, and scalar
decision record.
```

LM8C may reuse neutral helpers:

- `build_local_worker_turn_context(...)`
- `render_local_worker_turn_request_payload(...)`
- `run_two_pass_worker_publication(...)`

LM8C must not call repair-family helpers that rebuild C# repair evidence or
acceptance criteria.

## 5. Canonical Run

Canonical LM8C evidence is exactly one attempt.

Canonical parameters:

```text
worker model: gemma4:12b-it-qat
provider path: direct Ollama /api/chat
attempts: 1
initial slider value: 0.0
expected_output_value: 7.5
identity_projection: true
retry: disabled
gh_edit: disabled
Planner model: absent
```

The CLI may allow operational overrides such as `--model`, `--endpoint`, and
`--run-dir`, but canonical evidence is true only when the default canonical
shape is used:

```text
model == gemma4:12b-it-qat
direct Ollama worker path
attempts == 1
identity scalar fixture
expected_output_value == 7.5
initial slider value == 0.0
no retry
no gh_edit
no Planner model
```

## 6. Live Fixture

LM8C v1 uses direct GH scalar tools. The fixture is intentionally small:

```text
rhino_ping
gh_document_new
gh_create_slider(value=0.0, nickname=...)
gh_get_value(slider_guid)
```

The script then constructs a scalar receipt and anchor from live tool results.

The scalar receipt should be shaped so LM8B extraction can consume it:

```json
{
  "observed_output_value": 0.0,
  "scalar_anchor": {
    "component_guid": "<trusted-live-guid>",
    "editable_value_contract": {
      "label": "Expected scalar value",
      "value_type": "number",
      "current_value": 0.0,
      "identity_projection": true
    }
  }
}
```

The raw `component_guid` is trusted runtime authority. It must not be copied
into worker-visible source facts.

The corresponding workflow/task contract payload should include the source-owned
expected value:

```json
{
  "rules": {
    "verify_scalar_output": {
      "expected_output_value": 7.5
    }
  }
}
```

The exact fixture construction may use existing GH slider tool return fields,
but the authority split must remain:

```text
expected value -> workflow/task contract
observed value -> live scalar receipt
editable target context -> scalar anchor contract
trusted GUID -> applier-only runtime binding
worker -> {"value": number}
```

## 7. Scalar Runtime Readiness

LM8C must call this gate `scalar_runtime_ready`, not routability.

Reason:

```text
LM5AA routability is backed by LM5X repair-family extraction. LM8C scalar
routes are statically valid, but they are not LM5X-routable. The honest live
gate is whether the scalar fixture produces the exact source facts LM8B knows
how to extract and assemble.
```

Definition:

```text
scalar_runtime_ready =
  static source routing valid
  and live scalar receipt/anchor constructed
  and extract_gh_scalar_expectation_sources(...) succeeds
  and assemble_gh_scalar_expectation_packet(...) succeeds
```

Static routing validation uses:

```text
validate_worker_visible_source_routing(artifact)
```

with no real-object routability inputs. Expected:

```text
routability_evaluated == false
```

That is correct for LM8C v1.

Rejected interpretations:

- do not require `routability_evaluated == true`
- do not add scalar LM5X resolver behavior in LM8C
- do not call the scalar gate LM5AA routability
- do not pretend repair-family extraction proves scalar source availability

## 8. Source Routing

LM8C uses the LM8A route set for worker node `set_scalar_value`:

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

`fixture_anchor` remains evidence context only. It cannot become acceptance
criteria authority.

## 9. Worker-Visible Evidence

LM8C builds a scalar `WorkerKnowledgePacket` locally and passes it through the
neutral worker-turn renderer.

Recommended packet:

```text
packet_id: gh_scalar_expectation_evidence
kind: evidence
title: GH scalar expectation evidence
```

Content fields:

```text
current_observed_output
expected_output_value
editable_value_contract
acceptance_criteria
recommended_action_id
```

The full LM8B packet is artifact evidence. The worker-visible request may use
the legacy projection:

```text
source
criteria[{criterion_id, description, source}]
```

Worker-visible artifacts must not contain:

- full source packet metadata when the legacy projection is intended
- raw trusted GUID
- `gh_set_value` tool call arguments beyond the action schema
- topology or wiring instructions
- script repair instructions

Worker-visible artifacts may contain:

- `guid_present: true`
- `guid_sha256: sha256:...`
- `editable_value_contract.label`
- `editable_value_contract.value_type`
- `editable_value_contract.current_value`
- `editable_value_contract.identity_projection`

## 10. Worker Action

Allowed action:

```text
draft_gh_set_value_params
```

Action input schema:

```json
{
  "type": "object",
  "required": ["value"],
  "properties": {
    "value": {
      "type": "number"
    }
  },
  "additionalProperties": false
}
```

The worker must not provide:

- `guid`
- `component_guid`
- tool names
- code
- script fields
- topology edits
- wiring edits

LM8C should use `apply_gh_scalar_value_action_to_node(...)` to stage:

```json
{
  "guid": "<trusted anchor guid>",
  "value": "<worker-authored number>"
}
```

The trusted GUID comes from the live scalar anchor. The worker-authored value
comes from `action_input.value`.

## 11. Live Dispatch And Verification

If the applier succeeds, LM8C dispatches:

```text
gh_set_value(guid=<trusted-guid>, value=<worker-value>)
```

Then LM8C verifies with:

```text
gh_get_value(guid=<trusted-guid>)
```

Acceptance is verifier-floor only:

```text
accepted iff abs(observed_output_after - expected_output_value) <= scalar_tolerance
```

V1 tolerance:

```text
1e-9
```

LM8C must not add a separate semantic rule:

```text
worker_action_input.value == expected_output_value
```

In the identity fixture those should coincide naturally, but the authority
remains the live verifier floor.

Decision metadata should record:

- worker action value
- expected output value
- observed output before
- observed output after
- scalar tolerance
- match result

## 12. Terminal Decisions

LM8C terminal vocabulary:

```text
preflight_failed
gate_failed
publication_failed
worker_declined
rejected
accepted
```

Definitions:

```text
preflight_failed
  Rhino/GH surface setup failed before scalar fixture creation.

gate_failed
  Preflight passed, but fixture creation, initial gh_get_value, static routing,
  scalar extraction, or scalar packet assembly failed before worker publication.

publication_failed
  Worker publication failed, was not LM5G-loadable, or hidden marker gate failed.

worker_declined
  Worker published a valid non-action response.

rejected
  Worker action existed but applier rejected, gh_set_value failed, or final
  observed scalar output did not match expected value.

accepted
  gh_set_value dispatched and final gh_get_value matched expected_output_value
  within tolerance.
```

Preflight decision shape:

```json
{
  "decision": "preflight_failed",
  "reason": "rhino_ping_failed",
  "phase": "preflight",
  "live_fixture_created": false,
  "worker_publication_ran": false,
  "live_set_value_dispatched": false,
  "verify_scalar_output_ran": false
}
```

`gh_document_new_failed` is the corresponding reason when document creation
fails.

## 13. Artifacts

LM8C writes one run directory:

```text
probe_runs/lm8c-<timestamp>-<sha>/
```

Suggested artifact layout:

```text
manifest.json
scalar_fixture_contract.json
scalar_source_routing.json
static_routing_validation.json
scalar_sources.json
acceptance_criteria_packet.json
worker_visible_acceptance_criteria.json
worker_request_payload.json
worker_publication_row.json              # if worker reached
worker_action.json                       # only if action_request
live_create_scalar_summary.json
live_set_value_summary.json              # only if dispatched
verify_scalar_output_summary.json        # if verifier ran
decision.json
```

No full graph or canvas dumps:

- no full `gh_snapshot`
- no canvas image
- no raw model transcript beyond bounded publication telemetry
- no raw Planner model artifact because there is no Planner model

Bounded summary expectations:

```text
live_create_scalar_summary:
  tool_name
  created
  component_guid
  component_guid_sha256
  nickname
  initial_value
  observed_value
  receipt_sha256

live_set_value_summary:
  tool_name
  component_guid
  component_guid_sha256
  worker_action_value
  success
  receipt_sha256

verify_scalar_output_summary:
  tool_name
  component_guid_sha256
  expected_output_value
  observed_output_value
  tolerance
  matched
  receipt_sha256
```

`decision.json` should use `component_guid_sha256` / `guid_present`, not the
raw GUID.

## 14. GUID Policy

Worker-visible/source artifacts must not contain the full trusted slider GUID:

```text
scalar_sources.json
acceptance_criteria_packet.json
worker_visible_acceptance_criteria.json
worker_request_payload.json
```

Runtime/audit artifacts may include the full GUID only where they audit target
creation or mutation:

```text
live_create_scalar_summary.json
live_set_value_summary.json
```

`verify_scalar_output_summary.json` and `decision.json` must use
`component_guid_sha256` / `guid_present` only. The verifier proves the scalar
floor result; it does not need to restate the raw target authority.

Hard rule:

```text
The worker never authors or sees the live target GUID. LM8C may persist the
GUID only in ignored local runtime artifacts used to audit target creation or
mutation. Curated evidence, worker-visible artifacts, verifier summaries, and
decision records use presence/hash only.
```

## 15. Hidden Marker And Drift Policy

LM8C should inherit the worker publication hidden-answer guard used by the
frozen worker line.

Scalar-family worker output should also fail closed if it attempts to smuggle
disallowed fields:

- `guid`
- `component_guid`
- `code`
- script bodies
- tool names
- topology or wiring edits

LM8C must not add C# repair hidden answers to worker-visible scalar evidence.
The scalar family does not use `PROBE_REPAIR_CODE`, `A = 42.0`, or
`BindStepSpec.base_params`.

Direct marker scans in tests should ensure the new scalar script does not drift
into:

- `gh_edit`
- script repair helpers
- `gh_update_script`
- C# repair hidden-answer strings
- worker-visible raw GUID propagation

## 16. Implementation PR Boundaries

The implementation PR should include:

- LM8C spec
- LM8C plan
- `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- focused deterministic tests/fakes

The implementation PR should not include:

- live probe runs
- `probe_runs/`
- production workflow template changes
- Planner model changes
- worker prompt changes
- LM5X scalar routability
- `gh_edit` integration
- Rhino/GH-dependent tests in normal gates

Tests should use fake tool executors, fake worker publication responses, and
fake GH value receipts.

No test should require Rhino, Grasshopper, Ollama, or a live model.

## 17. Post-Merge Evidence

After the implementation PR merges and `main` is synced, run one canonical live
attempt:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8c_gh_scalar_expectation_live_probe.py
```

Rhino and Grasshopper must be open and responsive, but LM8C owns
`gh_document_new`.

Inspect:

```text
decision.json
static_routing_validation.json
scalar_sources.json
acceptance_criteria_packet.json
worker_publication_row.json
worker_action.json
live_create_scalar_summary.json
live_set_value_summary.json
verify_scalar_output_summary.json
```

Then write a separate doc-only evidence summary PR.

## 18. Interpretation

If LM8C ends `accepted`:

```text
The bounded worker protocol transferred once to a second tiny live task family.
```

That does not claim:

- broad GH scalar reliability
- topology repair ability
- batch edit readiness
- router readiness
- Planner-model generalization
- complexity scaling

If LM8C gate-fails after preflight:

```text
The scalar family source/fixture boundary is not live-ready yet.
```

If LM8C reaches worker publication and declines or rejects:

```text
The worker protocol was exercised on scalar evidence, but the scalar action path
did not reach verifier-floor success.
```

If LM8C passes, the next pressure should deepen the same GH scalar family before
adding a third family, such as:

- non-identity scalar relation
- numeric tolerance
- multiple candidate scalar targets
- multi-fact scalar criteria
- repeatability under the same scalar fixture

Do not jump directly to missing-wire repair, component replacement, `gh_edit`
batches, or a broad router unless LM8C exposes a cross-family protocol defect.
