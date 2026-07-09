# LM8J Affine Support Repeatability Design

Status: design checkpoint for review

Date: 2026-07-09

## 1. Purpose

LM8J is the repeatability pressure slice after LM8I.

LM8I produced a live affine scalar arrival with publication support available:

```text
observed_output = editable_value * 2.0 + 1.5
expected_output = 7.5
worker-authored editable value = 3.0
decision = accepted / verify_scalar_output_succeeded
publication_support_attempted = false
```

LM8I did not exercise the support turn because the worker published a valid
first-turn action. LM8J keeps the same fixture and support-enabled path, then
measures whether the result is stable over a larger scheduled sample.

Core question:

```text
Does the affine scalar support-enabled path remain stable across twenty
independent scheduled LM8I attempts, with no replacement attempts?
```

LM8J can prove affine repeatability for this fixture. It can only
opportunistically observe support recovery if the exact LM8H-style
`pass1_missing_action_id` failure naturally recurs.

## 2. Relationship To LM8I

LM8I remains the canonical single-attempt affine publication-shape support live
probe.

LM8J is only a scheduler and accountant around LM8I:

```text
LM8I = one canonical affine scalar attempt with support available
LM8J = N=20 repeatability wrapper for LM8I
```

LM8J must run LM8I as a subprocess. It must not import LM8I internals or
reimplement LM8I live behavior.

LM8I owns:

- `rhino_ping`
- `gh_document_new`
- deterministic affine fixture creation
- static affine source routing/extraction/assembly
- worker-visible affine scalar request
- exact-only publication support eligibility
- optional support publication turn
- one scalar action authority: `draft_gh_set_value_params {"value": number}`
- scalar applier staging trusted GUID + worker value
- `gh_set_value`
- verifier settle over `gh_inspect_output Addition R`
- child `decision.json`

LM8J owns:

- scheduled attempt count
- child LM8I subprocess invocation
- child run directory discovery
- terminal category classification
- support/reporting counters
- combined `attempts.jsonl`
- combined `summary.json`
- bounded stdout/stderr excerpts
- report-only leak scans

## 3. Scope

In scope:

- new deterministic wrapper script:

```text
scripts/lm8j_affine_support_repeatability_probe.py
```

- focused deterministic tests with fake subprocesses and fake child run dirs
- twenty scheduled attempts by default
- no replacement attempts
- child LM8I runs under a single LM8J run directory
- wrapper-level summary accounting
- post-merge single canonical N=20 live run from synced `main`
- later doc-only evidence summary after the live run

Out of scope:

- no LM8I behavior changes, except a tiny CLI/run-dir compatibility fix if tests
  prove one is needed
- no LM8I imports
- no worker prompt changes
- no worker protocol changes
- no support forcing
- no support-on/off comparison flag
- no scalar evidence shape changes
- no scalar applier changes
- no retry loop
- no Planner model
- no `gh_edit`
- no topology authored by the worker
- no harder scalar transform
- no live run in the implementation PR
- no raw `probe_runs/` artifacts committed

## 4. Canonical Command

Canonical LM8J evidence command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8j_affine_support_repeatability_probe.py
```

Canonical settings:

```text
attempts: 20
model: gemma4:12b-it-qat
run_dir: probe_runs
attempt_timeout_s: 600
support: enabled by LM8I, not forced by LM8J
```

`canonical_evidence` is true only when:

```text
attempts == 20
model == "gemma4:12b-it-qat"
attempt_timeout_s == 600
LM8I default support-enabled behavior is used
```

Ad hoc smoke runs may use smaller `--attempts` or non-default timeouts, but
they must not be cited as LM8J canonical repeatability evidence.

## 5. CLI

LM8J v1 CLI:

```text
--attempts
  positive integer, default 20

--model
  default gemma4:12b-it-qat

--run-dir
  default probe_runs

--attempt-timeout-s
  positive integer seconds, default 600
```

No retry flags, Planner flags, `gh_edit` flags, request overrides, support
forcing flags, support disabling flags, or scenario selectors are allowed in
LM8J v1.

## 6. Attempt Boundary

LM8J uses twenty independent scheduled attempts.

Each scheduled attempt:

```text
invoke LM8I as a subprocess
discover the newly created child lm8i-* run dir
read child decision.json
classify terminal_category
append one attempts.jsonl row
continue regardless of outcome
```

LM8J must not run separate preflight calls. LM8I already owns `rhino_ping` and
`gh_document_new`. Wrapper preflight would create an extra document boundary and
would measure `wrapper preflight + LM8I`, not repeatability of LM8I attempts.

LM8J must not replace failed scheduled attempts.

If attempt 7 fails, the evidence is:

```text
attempt 7 failed
attempts 8 through 20 still run
scheduled denominator remains 20
```

## 7. Subprocess Invocation

LM8J invokes LM8I with `sys.executable`.

Command shape:

```python
[
    sys.executable,
    "scripts/lm8i_affine_publication_shape_support_probe.py",
    "--model",
    model,
    "--run-dir",
    str(lm8j_run_dir / "lm8i_runs"),
]
```

LM8J may add no LM8I flags beyond the model and run-dir needed for canonical
repeatability accounting.

Full stdout/stderr are not stored in v1. Attempt rows store bounded excerpts.
Suggested excerpt bound:

```text
2000 characters each for stdout_excerpt and stderr_excerpt
```

## 8. Child Run Discovery

Before each LM8I invocation, LM8J snapshots existing child directories:

```text
lm8j_run_dir/lm8i_runs/lm8i-*
```

After the subprocess exits or times out, LM8J snapshots again and computes the
new child run dirs for that attempt.

Expected normal case:

```text
exactly one new lm8i-* child run dir
```

Classification:

```text
no new child dir:
  terminal_category = wrapper_error
  failure_reason = child_run_dir_missing

more than one new child dir:
  terminal_category = wrapper_error
  failure_reason = child_run_dir_ambiguous
```

If the child subprocess times out or exits nonzero but exactly one child run dir
exists, LM8J should still record that path, run report-only marker scanning on
it, and include bounded excerpts. The wrapper terminal category remains
`wrapper_error`.

LM8J must not parse stdout as the source of truth for child run discovery.

## 9. Terminal Categories

LM8J scheduled terminal categories:

- `accepted`
- `rejected`
- `worker_declined`
- `publication_failed`
- `gate_failed`
- `preflight_failed`
- `wrapper_error`

Classification from child LM8I `decision.json`:

```text
accepted -> accepted
rejected -> rejected
worker_declined -> worker_declined
publication_failed -> publication_failed
gate_failed -> gate_failed
preflight_failed -> preflight_failed
```

`wrapper_error` covers:

- LM8I subprocess timeout
- LM8I subprocess nonzero return code
- missing child run dir
- ambiguous child run dir
- missing `decision.json`
- unreadable `decision.json`
- invalid JSON in `decision.json`
- non-mapping `decision.json`
- child decision value outside the known LM8I vocabulary

Subprocess health is wrapper evidence, not worker evidence. If LM8I exits
nonzero:

```text
terminal_category = wrapper_error
failure_reason = lm8i_nonzero_returncode:<code>
```

Timeout classification:

```text
terminal_category = wrapper_error
failure_reason = lm8i_timeout
```

No wrapper error should be reclassified as `rejected`, because `rejected` is an
LM8I terminal decision after publication, applier, live mutation, or verifier
semantics.

## 10. Support Accounting

LM8J must not force support. It only records what each child LM8I run did.

Per child decision fields:

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

Derived support counters:

```text
publication_support_attempted_count:
  count(child.publication_support_attempted == true)

support_eligible_count:
  count(child.support_eligible == true)

accepted_without_support_count:
  count(child.decision == accepted and child.publication_support_attempted != true)

publication_support_recovered_count:
  count(child.publication_support_attempted == true
       and child.final_publication_status == published
       and child.final_worker_response_kind == action_request
       and child worker_action.json exists)
```

`publication_support_recovered_count` means the support turn recovered the
publication-shape path to a validated scalar action receipt. It does not by
itself mean the live verifier accepted. Accepted support recoveries are visible
by the intersection of:

```text
child.decision == accepted
child.publication_support_attempted == true
```

If support never triggers in N=20, LM8J should say support remains unproven
while also reporting that the LM8H missing-action-id recurrence was not observed
under this prompt/fixture/model sample.

## 11. Attempt Row Fields

Each `attempts.jsonl` row should include at least:

```text
attempt_index
scheduled_attempt_id
lm8i_invoked
lm8i_returncode
lm8i_run_dir
lm8i_decision
lm8i_reason
terminal_category
failure_reason
stdout_excerpt
stderr_excerpt
worker_publication_ran
live_fixture_created
live_set_value_dispatched
verify_scalar_output_ran
scalar_runtime_ready
publication_support_attempted
publication_support_count
support_eligible
support_not_attempted_reason
first_publication_status
first_publication_failure_reason
final_publication_status
final_publication_failure_reason
final_worker_response_kind
support_recovered
worker_action_value
verifier_attempt_count
observed_output_after
gate_failure_reason
preflight_failure_reason
leak_check_performed
leak_marker_matches
leak_marker_match_count
```

`worker_action_value` is read from child `worker_action.json` or from the
bounded `decision.json` action excerpt only when available and parseable. If the
value is unavailable, the field should be `null`; the row should not fail merely
because an action value cannot be summarized.

`support_recovered` is true only when support was attempted and child
`worker_action.json` exists after the support turn. It must not be inferred from
`final_worker_response_kind == action_request` alone, because a malformed action
request may still fail LM8I's scalar action validation.

`verifier_attempt_count` comes from child `verify_scalar_output_summary.json`
when present. If the verifier did not run, it should be `null`.

Gate/preflight failure reasons are copied from child `decision.json.reason` only
when the terminal category is `gate_failed` or `preflight_failed`.

## 12. Summary Fields

`summary.json` should include at least:

```text
schema
scheduled_attempts
attempt_timeout_s
canonical_evidence
terminal_category_counts
accepted_count
rejected_count
worker_declined_count
publication_failed_count
gate_failed_count
preflight_failed_count
wrapper_error_count
worker_reached_count
worker_terminal_counts
publication_support_attempted_count
publication_support_recovered_count
accepted_without_support_count
support_eligible_count
support_accepted_count
gate_failure_reasons
preflight_failure_reasons
leak_marker_match_count
attempt_run_dirs
worker_action_values
verifier_attempt_counts
observed_output_values_after
```

`worker_reached_count` is counted from child `decision.json`:

```text
worker_publication_ran == true
```

Worker terminal counts use the worker-reached denominator:

```text
accepted
rejected
worker_declined
publication_failed
```

`gate_failed`, `preflight_failed`, and `wrapper_error` count in the scheduled
denominator but not the worker denominator.

`support_accepted_count` is:

```text
count(child.decision == accepted and child.publication_support_attempted == true)
```

## 13. Leak Scan

LM8J performs report-only marker scanning over each child LM8I run directory.

Markers:

```text
PROBE_REPAIR_CODE
A = 42.0
BindStepSpec.base_params
repair_same_component.bind.base_params
```

Marker scanning must not override LM8I terminal classification. LM8I child
decisions remain authoritative for worker/live outcomes. LM8J reports marker
matches in attempt rows and aggregate summary only.

The affine hidden derived value `3.0` is not part of the global leak marker scan.
LM8I owns the local policy that keeps `3.0` out of pre-worker source/request
artifacts while allowing it in post-authoring audit/action artifacts.

## 14. Artifact Layout

LM8J writes:

```text
probe_runs/lm8j-<timestamp>-<sha>/
  manifest.json
  attempts.jsonl
  summary.json
  lm8i_runs/
    lm8i-<timestamp>-<sha>/
    lm8i-<timestamp>-<sha>-01/
    lm8i-<timestamp>-<sha>-02/
```

There should be twenty child `lm8i-*` directories in the normal canonical case.

LM8J must not copy raw LM8I model transcripts or duplicate child artifacts into
top-level summaries. The child LM8I run dirs remain the source of detailed
evidence.

## 15. Interpretation

LM8J reads:

```text
20/20 accepted:
  affine scalar path is genuinely stable for this controlled fixture sample.

support triggers and recovers:
  first natural support-recovery evidence.

support never triggers:
  support remains unproven, but the LM8H missing-action-id recurrence looks
  uncommon under this prompt/fixture/model sample.

verifier settle appears repeatedly:
  quantify live canvas solve/read latency as an operational seam.

canvas readiness/gate failures appear:
  scheduled operational evidence, not replacement attempts.
```

Mixed accepted/rejected results should be classified by failing seam:

```text
worker arithmetic/value selection
publication shape
support eligibility/recovery
fixture timing/readiness
verifier settle/readiness
tool wrapper health
```

LM8J must not claim:

- support reliability if support never triggers
- support recovery if support was not attempted
- broad affine scalar reasoning reliability
- topology/wiring authorship
- batch edit competence
- Planner competence
- third-family transfer
- complexity scaling beyond the LM8I fixture

## 16. Deterministic Test Targets

Implementation tests should use monkeypatched subprocess runners and synthetic
child run dirs. Tests must not require Rhino, Grasshopper, Ollama, or live
models.

Required deterministic coverage:

- default CLI produces canonical LM8J shape
- `--attempts` must be positive
- `--attempt-timeout-s` must be positive
- non-default model makes `canonical_evidence` false
- non-default timeout makes `canonical_evidence` false
- subprocess command uses `sys.executable`
- child LM8I run dir is discovered from filesystem delta, not stdout
- accepted child decision classifies as `accepted`
- rejected child decision classifies as `rejected`
- `gate_failed`, `preflight_failed`, `publication_failed`, and
  `worker_declined` classify directly from child `decision.json`
- nonzero LM8I return code becomes `wrapper_error`
- timeout becomes `wrapper_error`
- missing decision file becomes `wrapper_error`
- invalid decision JSON becomes `wrapper_error`
- non-mapping decision JSON becomes `wrapper_error`
- missing child run dir becomes `wrapper_error`
- ambiguous child run dir becomes `wrapper_error`
- worker_reached_count derives from `worker_publication_ran`
- support attempted, eligible, recovered, accepted-with-support, and
  accepted-without-support counters are summarized correctly
- support recovery requires a child `worker_action.json` receipt, but does not
  require verifier acceptance unless counted as `support_accepted_count`
- worker action values are summarized when available
- verifier attempt counts are summarized when available
- gate/preflight failure reasons are summarized
- leak marker scan is report-only and does not alter terminal category
- unsupported LM8I-affecting flags are rejected or not present
- implementation PR does not run live LM8J

## 17. Post-Merge Evidence Run

After the implementation PR merges and local `main` is synced, run one
canonical LM8J evidence attempt:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8j_affine_support_repeatability_probe.py
```

Prerequisites:

- Rhino open and responsive
- Grasshopper open and responsive
- Grasshopper canvas visibly ready for edit
- LM8I direct GH tools available
- Ollama model `gemma4:12b-it-qat` available

After the run, inspect:

```text
manifest.json
attempts.jsonl
summary.json
each child LM8I decision.json
accepted/rejected/declined/publication/gate/preflight/wrapper counts
publication_support_attempted_count
publication_support_recovered_count
accepted_without_support_count
support_eligible_count
worker_action_values
verifier_attempt_counts
gate/preflight failure reasons
leak_marker_match_count
```

Do not replace failed attempts. Any scheduled outcome is evidence.
