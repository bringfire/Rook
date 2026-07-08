# LM8D Scalar Action Affordance Clarity Design

Status: design checkpoint for review

Date: 2026-07-08

## 1. Purpose

LM8D is a tiny follow-up slice after the first canonical LM8C live run.

LM8C proved the second-family scalar path reached the worker boundary:

```text
preflight passed
live scalar fixture created
static routing valid
scalar_runtime_ready true
scalar sources assembled
expected value 7.5 visible
current value 0.0 visible
worker publication ran
```

It then failed at worker publication:

```json
{"kind": "action_request"}
```

The worker selected an action disposition but omitted the action handle:

```text
action_id = draft_gh_set_value_params
```

LM8D tests whether making the scalar action affordance explicit in the
scalar worker-visible packet lets the same frozen one-turn publication
protocol reach the next boundary. It does not change scalar runtime,
verification, worker publication rules, or action staging semantics.

## 2. Controlled Claim

```text
A scalar worker-visible packet with an explicit action-selection contract can
make the required scalar action handle legible without changing the frozen
worker protocol or letting the harness infer missing action fields.
```

LM8D is not a prompt-tuning sweep, retry policy, or model reliability claim.
It is a single deterministic affordance-clarity correction to the scalar
family request surface.

## 3. Scope

In scope:

- update the LM8C scalar `WorkerKnowledgePacket` content
- add an explicit `action_selection_contract`
- keep the existing allowed action:

```text
draft_gh_set_value_params
```

- keep the existing action input schema:

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

- update deterministic LM8C tests for worker-visible packet shape
- rerun exactly one canonical LM8C live attempt after merge

Out of scope:

- no action id autofill
- no "only one action, so infer it" behavior
- no shared two-pass publication helper changes
- no shared repair-worker prompt or protocol changes
- no worker retry
- no N=5
- no `gh_edit`
- no topology, wiring, or batch edit affordance
- no scalar runtime readiness changes
- no verifier changes
- no Planner model
- no live run in the implementation PR

## 4. Design Boundary

LM8D changes only the scalar worker-visible packet/request surface.

Keep unchanged:

- LM8C preflight
- live slider fixture
- scalar source routing artifact
- static source-routing validation
- `extract_gh_scalar_expectation_sources(...)`
- `assemble_gh_scalar_expectation_packet(...)`
- scalar runtime readiness definition
- neutral worker-turn renderer
- `run_two_pass_worker_publication(...)`
- `apply_gh_scalar_value_action_to_node(...)`
- `gh_set_value`
- `gh_get_value`
- terminal decision vocabulary

The harness must still reject malformed worker publication. If the worker again
publishes `{"kind": "action_request"}` without `action_id`, LM8C should still
end:

```text
decision = publication_failed
reason = pass1_decision_invalid:pass1_missing_action_id
```

## 5. Action Selection Contract

LM8D adds this field under the scalar knowledge packet `fields` object:

```json
{
  "action_selection_contract": {
    "contract_id": "gh_scalar_action_selection:v1",
    "worker_agency": "If the acceptance criteria are sufficient and action is warranted, publish action_request with the exact required_action_id. If action is not warranted, publish a non-action response.",
    "required_response_kind_if_acting": "action_request",
    "required_action_id": "draft_gh_set_value_params",
    "pass1_decision_required_fields_if_acting": [
      "kind",
      "action_id"
    ],
    "final_action_request_required_fields": [
      "schema",
      "kind",
      "action_id",
      "rationale",
      "input"
    ],
    "action_input_schema": {
      "type": "object",
      "required": ["value"],
      "properties": {
        "value": {"type": "number"}
      },
      "additionalProperties": false
    },
    "authority_limits": [
      "do not author target GUID",
      "do not call GH tools directly",
      "do not author topology, code, or batch edits"
    ]
  }
}
```

The pass-1 decision shape and final LM5G action response shape must remain
separate. Pass 1 only needs to classify the disposition and preserve the action
handle. The final loadable action response is where `input` appears.

The wording must preserve worker agency. It must not say "you must act" or
otherwise convert scalar evidence into an unconditional command. The point is
to clarify the action handle when the worker independently chooses an action
request.

## 6. Worker-Visible Packet Shape

LM8C currently exposes scalar evidence fields:

```text
current_observed_output
expected_output_value
editable_value_contract
acceptance_criteria
recommended_action_id
```

LM8D adds:

```text
action_selection_contract
```

`recommended_action_id` may remain for backward readability, but
`action_selection_contract.required_action_id` is the explicit affordance the
model should use when publishing an action request.

Worker-visible artifacts still must not contain:

- raw trusted GUID
- `component_guid`
- tool names as callable instructions
- code
- script repair fields
- topology edits
- wiring edits
- batch edit requests
- hidden bind params
- `PROBE_REPAIR_CODE`
- `A = 42.0`

The scalar packet may include:

- expected scalar value `7.5`
- current observed scalar value `0.0`
- editable target label/type/current value
- identity projection flag
- action id string `draft_gh_set_value_params`
- action input schema for `{"value": number}`

That is not action id leakage. It is the visible action affordance the worker
must cite if it chooses to act.

## 7. No Autofill Rule

LM8D must explicitly reject deterministic completion of malformed action
requests.

Forbidden behavior:

```text
if kind == action_request and only one allowed action exists:
  fill missing action_id
```

Reason:

```text
LM8C discovered a worker-boundary failure. The model must publish the action
id. The harness must not complete it for the model.
```

The two-pass publication row remains authoritative for publication validity.

## 8. Artifacts

The implementation should keep LM8C's artifact layout. Relevant expected
changes:

```text
worker_request_payload.json
  includes fields.action_selection_contract

worker_publication_row.json
  unchanged shape

decision.json
  unchanged terminal vocabulary
```

No new run directory family is required. LM8D changes LM8C behavior, so the
post-merge evidence run remains:

```text
probe_runs/lm8c-<timestamp>-<sha>/
```

## 9. Deterministic Proof Targets

The implementation PR should prove:

- scalar worker evidence contains `action_selection_contract`
- contract includes exact `required_action_id`
- contract includes exact numeric-only input schema
- contract preserves worker agency language
- worker-visible artifacts still omit raw GUID
- worker-visible artifacts still omit repair/script/topology/batch affordances
- malformed action request with missing `action_id` is still publication failed
- no action-id autofill path exists
- default LM8C canonical behavior remains otherwise unchanged
- existing LM8B scalar source/assembler/applier tests remain green
- existing nearby worker publication tests remain green

Suggested focused verification:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  mcp_server\tests\test_plan_graph_gh_scalar_value_apply.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  -q

py -3.10 -m py_compile `
  scripts\lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
```

## 10. Post-Merge Evidence

After deterministic implementation merges to `main`, run exactly one canonical
LM8C live attempt from synced `main`:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8c_gh_scalar_expectation_live_probe.py
```

Do not replace the attempt. Do not run N=5. Do not enable retry.

If the run again ends:

```text
publication_failed / pass1_missing_action_id
```

then action affordance clarity did not solve the scalar family publication
shape miss.

If the run reaches pass 2, action apply, live `gh_set_value`, or verifier
failure, that is new boundary evidence.

If the run ends:

```text
accepted / verify_scalar_output_succeeded
```

then the scalar family has reached first live arrival through the existing
bounded-worker protocol.

## 11. Interpretation

LM8D should be interpreted narrowly:

```text
LM8D tests whether scalar action affordance clarity repairs a malformed
action-handle publication in the second tiny task family.
```

It must not be interpreted as:

- proof of scalar family repeatability
- proof of complexity scaling
- a new production worker retry policy
- a reason to weaken publication validation
- a reason to infer action ids from context

The clean result is a better receipt, not guaranteed success.
