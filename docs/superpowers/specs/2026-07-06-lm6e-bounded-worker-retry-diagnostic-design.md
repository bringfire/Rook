# LM6E - Bounded Worker Retry Diagnostic Design

- **Date:** 2026-07-06
- **Status:** Draft for review
- **Slice:** LM6E
- **Type:** Diagnostic retry variant over the frozen bounded-worker protocol

## 1. Purpose

LM6E tests whether one receipted second worker turn can recover the clean
observation wobble seen in LM6C.

LM6A proved first live arrival. LM6C then repeated the frozen LM6B protocol:

```text
5/5 scheduled attempts reached the worker path.
4/5 accepted live repairs.
1/5 ended in a clean observation disposition.
0/5 leaked hidden-answer markers.
```

The non-accepted row was not a gate failure, publication failure, applier
rejection, live repair failure, or hidden-answer leak. It was a clean
`observation` disposition:

```text
LM5G-loadable
kind-preserved
no observation-action anomaly
no live repair dispatch
no verify_repair run
```

LM6E asks one narrow question:

```text
If a worker publishes a clean observation despite sufficient visible acceptance
criteria, can exactly one bounded retry recover action without changing the
evidence, model, applier, live dispatch, or core publication mechanics?
```

LM6E does not establish production retry policy.

## 2. Controlled Variable

LM6E adds exactly one receipted second worker turn after a clean observation
disposition.

Unchanged:

- source routing
- LM5AA routability gate
- LM5X extraction
- LM5W assembly
- LM5Y worker-visible acceptance-criteria legacy projection
- LM5S pass-one decision instruction
- pass-two formatter prompt
- `run_two_pass_worker_publication(...)` mechanics
- worker-action applier semantics
- live `gh_update_script` dispatch
- verifier semantics
- model default: `gemma4:12b-it-qat`
- direct Ollama provider path

Changed:

- LM6A may, when explicitly enabled, run a second worker publication turn after
  one clean observation.
- The retry turn receives the same request/evidence/actions plus one bounded
  retry-context packet.
- LM6C may explicitly pass the retry flag through to child LM6A runs and report
  retry metadata.

## 3. Scope

Expected implementation scope:

```text
docs/superpowers/specs/2026-07-06-lm6e-bounded-worker-retry-diagnostic-design.md
docs/superpowers/plans/2026-07-06-lm6e-bounded-worker-retry-diagnostic.md
scripts/lm6a_live_worker_splice_probe.py
scripts/lm6c_repeatability_probe.py
mcp_server/tests/test_lm6a_live_worker_splice_probe.py
mcp_server/tests/test_lm6c_repeatability_probe.py
```

No production `mcp_server/src` changes are expected.

No live run belongs in the implementation PR. Raw `probe_runs/` artifacts remain
ignored and uncommitted.

## 4. CLI Flags

LM6A retry is CLI-gated and default off.

Baseline LM6A:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6a_live_worker_splice_probe.py
```

LM6E diagnostic LM6A variant:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6a_live_worker_splice_probe.py `
  --retry-clean-observation
```

LM6C pass-through is also CLI-gated and default off.

Baseline LM6C remains unchanged:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6c_repeatability_probe.py
```

Canonical LM6E post-merge evidence command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6c_repeatability_probe.py `
  --lm6a-retry-clean-observation
```

The default LM6A and LM6C commands must continue to run the no-retry frozen
baseline behavior.

## 5. Retry Eligibility

LM6E retry eligibility is observation-only.

Retry exactly once only when all of these are true:

```text
LM6A Phase A passed
first worker publication status == published
first worker response kind == observation
observation_action_intent_anomaly == false
no hidden-answer leak
live_repair_dispatched == false
verify_repair_ran == false
```

The hidden-answer eligibility check is not a new scan surface. First-turn retry
eligibility is evaluated only after the existing LM6A hidden-answer gates pass.
If the first publication row or first response payload leaks a hidden-answer
marker, LM6A terminates exactly as the no-retry path does today:

```json
{
  "retry_attempted": false,
  "retry_count": 0
}
```

No retry is attempted.

Do not retry:

- `clarification_request`
- `refusal`
- `action_request`
- `gate_failed`
- `publication_failed`
- applier rejection
- live repair failure
- hidden-answer leak
- observation-action anomaly
- provider/subprocess wrapper errors

For non-eligible non-actions, keep the existing behavior:

```json
{
  "decision": "worker_declined",
  "retry_attempted": false,
  "retry_count": 0,
  "retry_eligibility_reason": "not_retry_eligible:<reason>"
}
```

Clarifications are excluded in LM6E because they are closer to real missing-info
states and belong to the future clarify/resupply path unless later evidence
shows they are also disposition wobble.

## 6. Retry Request

The retry turn must reuse `run_two_pass_worker_publication(...)` unchanged.

LM6A constructs a modified request payload for the retry turn:

```text
same original request envelope
same visible evidence
same allowed actions
same acceptance criteria
plus one retry-context packet
```

The retry packet is worker-visible, small, factual, and bounded:

```json
{
  "packet_id": "lm6e_bounded_retry_context",
  "kind": "retry_context",
  "fields": {
    "retry_count": 1,
    "max_retries": 1,
    "previous_response_kind": "observation",
    "previous_response_reason": "worker_observed",
    "previous_observation_message_excerpt": "...",
    "previous_observation_message_sha256": "sha256:...",
    "instruction": "Re-evaluate the same request after your prior observation. If the visible acceptance criteria are sufficient to draft repair parameters, publish action_request. If they are still insufficient, publish observation again."
  }
}
```

Bounds and exclusions:

- `previous_observation_message_excerpt` is capped by the existing
  `excerpt_chars` setting.
- `previous_observation_message_sha256` is computed over the full published
  observation message.
- Do not include raw provider content.
- Do not include raw thinking.
- Do not include the prior pass-one decision artifact.
- Do not include hidden answers.
- Do not suggest action input code.
- Do not change acceptance criteria.
- Do not alter the pass-one instruction or pass-two formatter.

## 7. Publication Artifacts

LM6A currently writes:

```text
worker_publication_row.json
```

LM6E adds an ordered multi-turn artifact:

```text
worker_publication_rows.json
```

`worker_publication_rows.json` is authoritative for multi-turn retry evidence.
It contains the initial publication row and, when attempted, the retry
publication row.

`worker_publication_row.json` remains the final-turn compatibility artifact:

```text
no retry:
  worker_publication_row.json == initial row

retry attempted:
  worker_publication_row.json == retry row
```

LM6A, not the shared helper, may add row metadata before writing artifacts:

```text
turn_index
turn_role: initial | retry
retry_context_present
```

The retry-context packet should be written as a bounded local artifact, for
example:

```text
retry_context.json
```

It must not contain hidden answers or action suggestions.

## 8. Decision Vocabulary

LM6E preserves the existing top-level LM6A decisions:

```text
accepted
rejected
worker_declined
publication_failed
gate_failed
```

Do not add:

```text
accepted_after_retry
worker_declined_after_retry
```

Retry appears as metadata in `decision.json`.

Common fields:

```text
retry_attempted
retry_count
retry_eligibility_reason
first_worker_response_kind
first_worker_decline_reason
final_worker_response_kind
```

No retry:

```json
{
  "retry_attempted": false,
  "retry_count": 0
}
```

Retry recovers action and live verification succeeds:

```json
{
  "decision": "accepted",
  "reason": "verify_repair_succeeded",
  "retry_attempted": true,
  "retry_count": 1,
  "first_worker_response_kind": "observation",
  "first_worker_decline_reason": "worker_observed",
  "final_worker_response_kind": "action_request"
}
```

Retry also publishes observation:

```json
{
  "decision": "worker_declined",
  "reason": "worker_observed_after_retry",
  "retry_attempted": true,
  "retry_count": 1,
  "first_worker_response_kind": "observation",
  "first_worker_decline_reason": "worker_observed",
  "final_worker_response_kind": "observation"
}
```

Retry publishes anomalous observation:

```json
{
  "decision": "worker_declined",
  "reason": "worker_observation_action_intent_anomaly_after_retry",
  "retry_attempted": true,
  "retry_count": 1
}
```

Retry publication fails:

```json
{
  "decision": "publication_failed",
  "reason": "retry_publication_failed:<status_or_reason>",
  "retry_attempted": true,
  "retry_count": 1
}
```

Retry publication hidden-answer leak:

```json
{
  "decision": "publication_failed",
  "reason": "retry_worker_publication_hidden_answer_leak",
  "retry_attempted": true,
  "retry_count": 1
}
```

That terminal outcome must preserve retry metadata and must not dispatch live
repair.

## 9. LM6C Pass-Through

LM6C remains the scheduler and measurement wrapper. It does not own retry
policy.

LM6C may add one explicit pass-through flag:

```powershell
--lm6a-retry-clean-observation
```

When false, LM6C child commands are unchanged.

When true, each child LM6A command adds:

```powershell
--retry-clean-observation
```

LM6C terminal accounting remains unchanged:

```text
accepted
rejected
worker_declined
publication_failed
gate_failed
wrapper_error
preflight_failed
```

LM6C may copy report-only retry metadata from child `decision.json` into
attempt rows:

```text
retry_attempted
retry_count
first_worker_response_kind
final_worker_response_kind
```

LM6C summary may add backward-compatible report-only counts:

```text
retry_attempted_count
retry_recovered_count
retry_declined_count
retry_publication_failed_count
```

Definitions:

```text
retry_recovered =
  retry_attempted == true
  and final_worker_response_kind == action_request

retry_declined =
  retry_attempted == true
  and terminal_category == worker_declined
```

These fields do not replace or reinterpret terminal categories.

## 10. Hidden-Answer Safety

LM6E must preserve the existing hidden-answer checks:

```text
PROBE_REPAIR_CODE
A = 42.0
BindStepSpec.base_params.code
```

The retry context must not include hidden answers, hand-authored repair diffs,
already-bound repair params, or action-input suggestions.

Legitimate worker-authored code may still appear only where LM6A already allows
it: ignored local worker-action artifacts plus bounded hashes/excerpts.

If a retry response leaks a hidden-answer marker, LM6A must not dispatch live
repair. The terminal decision should be classified under existing failure
semantics, with retry metadata preserved.

## 11. Non-Goals

LM6E does not add:

- production retry policy
- retry-until-success
- Planner integration
- KG retrieval
- prompt/evidence stuffing
- hidden answers
- new acceptance criteria
- changes to LM5W/LM5X/LM5Y evidence shape
- changes to `run_two_pass_worker_publication(...)`
- changes to the worker-action applier
- changes to live dispatch semantics
- clarification/resupply protocol
- broad model/provider comparison
- live run during implementation PR

## 12. Deterministic Tests

Implementation tests should use fakes only. No test may require Rhino,
Grasshopper, Ollama, or a live model.

LM6A tests should cover:

- default retry off preserves existing no-retry behavior
- clean observation is retry-eligible when flag is enabled
- clarification is not retry-eligible
- refusal is not retry-eligible
- observation-action anomaly is not retry-eligible
- hidden-answer leak is not retry-eligible and does not dispatch
- retry request includes exactly one retry-context packet
- retry request keeps original evidence/actions/acceptance criteria unchanged
- retry uses `run_two_pass_worker_publication(...)` unchanged
- `worker_publication_rows.json` is ordered
- `worker_publication_row.json` is the final turn
- retry recovery maps to `accepted` with retry metadata
- retry observation maps to `worker_declined` with retry-aware reason
- retry publication failure maps to `publication_failed`
- no live dispatch happens before retry action is available

LM6C tests should cover:

- default child LM6A command omits `--retry-clean-observation`
- pass-through flag adds `--retry-clean-observation`
- terminal category counts remain unchanged
- retry metadata is copied into attempt rows when present
- retry summary counts are backward-compatible
- existing no-retry fixtures still classify as before

Static checks:

- no production `mcp_server/src` diff expected
- no prompt/version drift in `scripts/lm_worker_two_pass_publication.py`
- no acceptance-criteria shape drift
- no applier semantic drift
- no raw `probe_runs/` artifacts committed
- `git diff --check main..HEAD`

## 13. Post-Merge Evidence

After the implementation PR merges, run the canonical LM6E evidence command from
synced `main` with Rhino and Grasshopper ready:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6c_repeatability_probe.py `
  --lm6a-retry-clean-observation
```

The evidence summary should compare:

```text
LM6C baseline:
  N=5 no retry
  4 accepted
  1 clean worker_declined observation

LM6E retry variant:
  N=5 retry-clean-observation enabled
  scheduled terminal counts
  worker-reached counts
  retry_attempted_count
  retry_recovered_count
  retry_declined_count
  leak_marker_match_count
```

If retry recovers clean observation wobble, the next slice can decide whether a
bounded retry policy deserves product/protocol promotion.

If retry does not help, the next pressure is not more evidence stuffing. It is
either the clarify/resupply pull-loop for real unresolved intent or a narrower
disposition-analysis slice.

## 14. Success Criteria

LM6E implementation succeeds when:

```text
LM6A default behavior remains no-retry.
LM6A retry flag enables exactly one retry for clean observation only.
The retry request adds only the bounded retry-context packet.
Both worker turns are receipted.
Top-level decisions remain unchanged.
Retry metadata makes recovery or decline visible.
LM6C default behavior remains no-retry.
LM6C retry flag passes through to child LM6A runs.
Implementation PR is deterministic-only.
```

LM6E evidence succeeds if the post-merge N=5 retry variant shows whether the
single receipted retry recovers the LM6C observation wobble without hidden-answer
leaks or protocol drift.
