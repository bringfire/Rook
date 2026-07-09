# LM8I Affine Publication Shape Support Design

Status: design checkpoint for review

Date: 2026-07-09

## 1. Purpose

LM8I is the next scalar-family slice after LM8H.

LM8H proved that the live affine scalar fixture and scalar runtime gate reached
the worker boundary:

```text
fixture: editable_value * factor_value + offset_value
editable value: 2.0
factor value: 2.0
offset value: 1.5
observed output: 5.5
expected output: 7.5
scalar_runtime_ready: true
worker_publication_ran: true
```

The canonical LM8H run then failed before pass 2:

```text
run_dir: probe_runs/lm8h-20260709T181451Z-3264198a/
decision: publication_failed
reason: pass1_decision_invalid:pass1_missing_action_id
pass1 payload: {"kind": "action_request"}
```

LM8I asks the next narrow question:

```text
Can one bounded, receipted publication-shape support turn recover the exact
LM8H skeletal action_request missing action_id failure, without autofill or
changing worker authority?
```

LM8I is a publication-shape support diagnostic. It is not a scalar fixture
change, not a tooling fix, not a retry policy, and not a repeatability run.

## 2. Baseline And Intervention

Baseline:

```text
LM8H = affine scalar depth pressure
support: none
terminal result: publication_failed / pass1_missing_action_id
```

Intervention:

```text
LM8I = same affine scalar fixture and worker model
support: exactly one publication-support turn, only if exact eligibility matches
```

The comparison key is:

```text
LM8H no-support canonical run
vs
LM8I one-support canonical run
```

LM8I should not add an on/off comparison flag. LM8H is the no-support baseline.
LM8I is the one-support intervention.

## 3. Scope

In scope:

- new sibling script design:

```text
scripts/lm8i_affine_publication_shape_support_probe.py
```

- copy/adapt the LM8H affine live probe shape for v1
- reuse existing neutral modules and helpers where already established
- use the same canonical affine fixture as LM8H
- use the same worker model:

```text
gemma4:12b-it-qat
```

- use direct Ollama worker path
- use the same worker action:

```text
draft_gh_set_value_params {"value": number}
```

- use the same two-pass worker publication helper unchanged
- add one LM8I-local publication-support packet only on the second publication
  turn
- preserve worker agency
- preserve verifier-floor acceptance after a valid final action
- write deterministic implementation plan and fake-tool tests later
- run one canonical live attempt after merge
- write a separate doc-only evidence summary after the live run

Out of scope:

- no action_id autofill
- no "only one action exists, so infer it" behavior
- no hidden derived value `3.0` in worker-visible/support artifacts
- no target GUID in worker-visible/support artifacts
- no worker-authored topology, wiring, GH tools, code, scripts, or `gh_edit`
- no shared two-pass helper semantic change
- no LM8H patch
- no retry loop
- no model panel
- no Planner model
- no N=5
- no live run in the implementation PR

## 4. Script Boundary

LM8I should be a sibling script, not a mode hidden inside LM8H.

Reason:

```text
LM8H is closed evidence.
LM8I is a pre-registered intervention.
```

The v1 implementation should copy/adapt LM8H rather than refactor shared
affine-live helpers first. A new shared affine helper layer would add an
abstraction variable to a publication-support experiment. Extraction can happen
later if LM8I and later scalar slices make the duplication painful.

Implementation may reuse existing neutral modules and helpers, including the
current worker-turn renderer, scalar applier, and two-pass publication helper.
It should not create a new shared publication policy or modify the existing
helper semantics.

## 5. Exact Support Eligibility

LM8I may attempt publication support exactly once, and only when the first
publication row matches the observed LM8H failure.

Eligible only when all are true:

```text
first publication status == pass1_decision_invalid
first publication failure_reason == pass1_missing_action_id
pass1_content_excerpt exactly equals the observed LM8H skeletal JSON string
pass1_content_sha256 is present
```

Eligibility is evaluated from the shared publication row, not raw provider
transcripts. The unchanged two-pass helper receipts invalid pass 1 output with
bounded fields:

```text
pass1_content_excerpt
pass1_content_sha256
```

LM8I may treat `pass1_content_excerpt` as eligible only when the bounded
excerpt exactly equals the observed LM8H skeletal JSON string:

```json
{"kind": "action_request"}
```

If the excerpt is truncated, ambiguous, compacted differently, whitespace-varied,
non-JSON, missing `pass1_content_sha256`, or contains any extra semantic field,
support is not eligible. `pass1_content_sha256` is recorded for audit.

LM8I must not change the shared two-pass helper and must not persist unbounded
raw pass-1 provider content only to make eligibility easier.

Eligible exact excerpt:

```json
{"kind": "action_request"}
```

Not eligible:

```json
{"kind": "action_request", "action_id": ""}
{"kind": "action_request", "action_id": "wrong_id"}
{"kind": "action_request", "input": {"value": 3.0}}
{"kind": "observation"}
"not json"
```

LM8I should not support other malformed pass-1 cases in v1. This is not a
general JSON repair layer.

If the first publication is not eligible, LM8I should proceed to the same
terminal outcome LM8H would have produced and record support metadata:

```json
{
  "publication_support_attempted": false,
  "publication_support_count": 0,
  "support_eligible": false,
  "support_not_attempted_reason": "first_publication_not_exact_skeletal_missing_action_id"
}
```

If the first publication publishes a valid action immediately, support is not
needed and the run continues normally to applier/live/verifier.

## 6. Publication Support Packet

If eligibility matches, LM8I should run a second publication attempt with the
same two-pass helper unchanged. The only request-surface change is a small
worker-visible publication-support packet added to the second request payload.

Suggested packet:

```json
{
  "packet_id": "lm8i_publication_support_context",
  "kind": "publication_support",
  "title": "Publication shape support",
  "fields": {
    "support_reason": "previous_pass1_missing_action_id",
    "previous_response_kind": "action_request",
    "previous_response_excerpt": "{\"kind\": \"action_request\"}",
    "previous_response_sha256": "sha256:...",
    "required_action_id": "draft_gh_set_value_params",
    "pass1_decision_required_fields_if_acting": ["kind", "action_id"],
    "instruction": "Your prior pass-1 response selected action_request but omitted the required action_id. Re-evaluate the same evidence. If action is still warranted, publish action_request with action_id draft_gh_set_value_params. If action is not warranted, publish a non-action response."
  }
}
```

Support packet requirements:

- include the prior pass-1 content only as bounded excerpt and hash
- include the required action id
- include the pass-1 required fields if acting
- preserve worker agency
- include no derived worker value `3.0`
- include no target GUID
- include no action input suggestion
- include no GH tool call instruction
- include no topology, wiring, code, script, or batch-edit authority

The support packet must not say "you must act." It should say that if action is
still warranted, the worker must include the exact action id.

## 7. Publication Flow

LM8I publication flow:

```text
run first worker publication attempt normally
read first publication row
if exact support eligibility matches:
  write publication_support_context.json
  run one second worker publication attempt with support packet
else:
  do not run support attempt
classify the final publication row
if final row contains a valid action_request:
  apply trusted GUID + worker-authored value
  dispatch gh_set_value
  run verifier floor
else:
  terminate with existing vocabulary
```

The support attempt is not a worker disposition retry. It is a publication-shape
support turn for one exact malformed pass-1 action header.

The support attempt must not reuse live side effects from a previous failed
publication because no live action has been dispatched at that point.

## 8. Artifacts

LM8I should use its own run directory:

```text
probe_runs/lm8i-<timestamp>-<sha>/
```

Expected scalar/live artifacts should mirror LM8H where applicable.

Publication artifacts:

```text
worker_publication_rows.json
worker_publication_row.json
publication_support_context.json
worker_action.json
```

Rules:

```text
worker_publication_rows.json = ordered audit list
worker_publication_row.json = final publication row compatibility artifact
publication_support_context.json = written only if support attempted
worker_action.json = written only after the final action_request passes scalar
action applier validation
```

Each entry in `worker_publication_rows.json` should include either the safe
shared helper row, or a redacted/hash-only publication row summary when the
helper row or response payload fails hidden-marker/raw-GUID safety checks.
LM8I annotations remain outside the shared helper output or redacted summary:

```text
turn_index
turn_role: initial | publication_support
publication_support_context_present: true|false
```

If support is not attempted, the list has one row. If support is attempted, the
list has two rows.

The final compatibility artifact should always represent the final publication
row:

```text
support not attempted -> initial row
support attempted -> support row
```

Hidden-marker/raw-GUID safety overrides raw row artifact compatibility. If a
publication row or response payload fails safety checks, LM8I should write
redacted/hash-only `worker_publication_rows.json` and `worker_publication_row.json`
entries with status, failure reason, content hashes, response hash, and turn
annotations, but must not persist the unsafe raw helper row or response payload.

## 9. Terminal Decisions

LM8I should keep the LM8H terminal vocabulary:

```text
accepted
rejected
worker_declined
publication_failed
gate_failed
preflight_failed
```

No new top-level terminal decisions:

```text
no accepted_after_support
no publication_recovered
no support_failed
```

Support is metadata, not a terminal category.

Decision metadata should include:

```text
publication_support_attempted
publication_support_count
support_eligible
support_not_attempted_reason
first_publication_status
first_publication_failure_reason
final_publication_status
final_publication_failure_reason
final_worker_response_kind
```

Outcome mapping:

```text
support publishes valid action -> continue to applier/live/verifier
support publishes valid non-action -> worker_declined
support repeats malformed/missing action_id -> publication_failed
support helper/provider fails -> publication_failed
support action has wrong action_id -> publication_failed
support action has forbidden content -> publication_failed
```

If support publishes a valid action and verifier succeeds, the top-level
decision remains:

```text
decision = accepted
reason = verify_scalar_output_succeeded
```

## 10. Hidden Value And Authority Policy

LM8I inherits the LM8H hidden derived value policy:

```text
3.0 is the correct affine editable value.
3.0 must not appear in worker-visible evidence, publication support context,
prompt text, pre-publication source artifacts, or deterministic criteria text.
3.0 may appear only after the worker authors it, such as in worker_action.json,
live set-value summaries, verifier summaries, and bounded decision fields.
```

The worker may see:

```text
current editable value: 2.0
factor value: 2.0
offset value: 1.5
current observed output: 5.5
expected observed output: 7.5
projection: observed_output = editable_value * factor_value + offset_value
required action id: draft_gh_set_value_params
action input schema: {"value": number}
```

The worker must not see or author:

```text
target GUID
GH tool calls
topology edits
wiring edits
component ids as mutation authority
code
scripts
batch edits
hidden repair markers
```

The trusted editable slider GUID remains applier-only.

## 11. Canonical Evidence

Canonical LM8I evidence is exactly one post-merge live attempt from synced
`main`.

Canonical shape:

```text
attempts = 1
model = gemma4:12b-it-qat
fixture = LM8H affine scalar fixture
support = always enabled
support_budget = 1
eligibility = exact-only skeletal action_request missing action_id
retry = no worker disposition retry
Planner = none
gh_edit = none
```

If the first publication does not match the exact eligibility condition,
support should not run. That is still evidence. LM8I measures what happens when
support is available under a pre-registered eligibility rule, not a forced
support exercise.

Do not replace failed attempts. Any terminal outcome is evidence if receipted.

## 12. Interpretation

If LM8I accepts after support:

```text
One bounded publication-shape support turn recovered the exact LM8H skeletal
action_request missing action_id failure and allowed the affine scalar worker
path to reach verifier-floor acceptance once.
```

If LM8I publishes a valid action on the first attempt without support:

```text
The affine scalar path reached action publication without needing support in
this run. LM8I remains interpretable because support availability was
pre-registered and not exercised.
```

If LM8I repeats the missing-action-id failure after support:

```text
The support packet did not repair the worker publication-shape failure.
The next pressure should not silently autofill action_id.
```

If LM8I fails after valid final action:

```text
Treat the result by the failing downstream stage: applier, live set-value, or
verifier floor.
```

LM8I does not prove:

- broad affine scalar reliability
- scalar transform repeatability
- Planner competence
- topology or wiring authorship
- batch edit competence
- that general malformed JSON repair is safe

## 13. Implementation Plan Targets

The implementation plan should cover:

- `scripts/lm8i_affine_publication_shape_support_probe.py`
- focused LM8I tests with fake GH tools and fake worker provider
- exact support eligibility tests
- support packet marker/authority tests
- ordered publication rows artifact tests
- compatibility final row tests
- no action_id autofill regression
- hidden `3.0` pre-publication leak tests
- terminal metadata tests
- deterministic no-live implementation PR

No live LM8I run should happen in the implementation PR.
