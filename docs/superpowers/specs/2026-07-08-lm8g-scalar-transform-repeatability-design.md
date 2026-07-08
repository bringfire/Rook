# LM8G Scalar Transform Repeatability Design

Status: design checkpoint for review

Date: 2026-07-08

## 1. Purpose

LM8F proved one live GH-native scalar transform depth arrival:

```text
editable slider 2.0
+ offset 1.5
-> Addition R initially 3.5
-> worker derives editable value 6.0
-> verifier observes Addition R = 7.5
```

LM8G measures whether that same scalar transform path repeats.

Core question:

```text
Was LM8F a one-off arrival, or does the scalar relationship path hold
repeatedly under the same fixture, model, action, verifier, and protocol?
```

LM8G is repeatability evidence. It does not increase scalar difficulty, add a
third family, or change the worker protocol.

## 2. Relationship To LM8F

LM8F remains the canonical single-attempt scalar transform live probe.

LM8G is only a scheduler and accountant around LM8F:

```text
LM8F = one canonical scalar-transform attempt
LM8G = repeatability wrapper for LM8F
```

LM8G must run LM8F as a subprocess. It must not import LM8F internals or
reimplement LM8F live behavior.

LM8F owns:

- `rhino_ping`
- `gh_document_new`
- deterministic scalar transform fixture creation
- static scalar routing/extraction/assembly
- worker-visible scalar transform request
- one-turn Gemma worker publication
- scalar applier staging trusted GUID + worker value
- `gh_set_value`
- verifier settle over `gh_inspect_output Addition R`
- child `decision.json`

LM8G owns:

- scheduled attempt count
- child LM8F subprocess invocation
- child run directory discovery
- terminal category classification
- combined `attempts.jsonl`
- combined `summary.json`
- bounded stdout/stderr excerpts
- report-only leak scans

## 3. Scope

In scope:

- new deterministic wrapper script:

```text
scripts/lm8g_scalar_transform_repeatability_probe.py
```

- focused deterministic tests with fake subprocesses and fake child run dirs
- five scheduled attempts by default
- no replacement attempts
- child LM8F runs under a single LM8G run directory
- wrapper-level summary accounting
- post-merge single canonical N=5 live run from synced `main`
- later doc-only evidence summary after the live run

Out of scope:

- no LM8F behavior changes, except a tiny CLI/run-dir compatibility fix if tests
  prove one is needed
- no LM8F imports
- no worker prompt changes
- no worker protocol changes
- no scalar evidence shape changes
- no scalar applier changes
- no retry
- no Planner model
- no `gh_edit`
- no topology authored by the worker
- no harder scalar transform
- no live run in the implementation PR
- no raw `probe_runs/` artifacts committed

## 4. Canonical Command

Canonical LM8G evidence command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8g_scalar_transform_repeatability_probe.py
```

Canonical settings:

```text
attempts: 5
model: gemma4:12b-it-qat
run_dir: probe_runs
attempt_timeout_s: 600
```

`canonical_evidence` is true only when:

```text
attempts == 5
model == "gemma4:12b-it-qat"
```

Ad hoc smoke runs may use `--attempts 1`, but they must not be cited as LM8G
repeatability evidence.

## 5. CLI

LM8G v1 CLI:

```text
--attempts
  positive integer, default 5

--model
  default gemma4:12b-it-qat

--run-dir
  default probe_runs

--attempt-timeout-s
  positive integer seconds, default 600
```

No retry flags, Planner flags, `gh_edit` flags, request overrides, or scenario
selectors are allowed in LM8G v1.

## 6. Attempt Boundary

LM8G uses five independent scheduled attempts.

Each scheduled attempt:

```text
invoke LM8F as a subprocess
discover the newly created child lm8f-* run dir
read child decision.json
classify terminal_category
append one attempts.jsonl row
continue regardless of outcome
```

LM8G must not run separate preflight calls. LM8F already owns `rhino_ping` and
`gh_document_new`. Adding wrapper preflight would create an extra document
boundary and would measure `wrapper preflight + LM8F`, not repeatability of the
LM8F attempt.

LM8G must not replace failed scheduled attempts.

If attempt 3 fails, the evidence is:

```text
attempt 3 failed
attempts 4 and 5 still run
scheduled denominator remains 5
```

## 7. Subprocess Invocation

LM8G invokes LM8F with `sys.executable`.

Command shape:

```python
[
    sys.executable,
    "scripts/lm8f_scalar_transform_depth_probe.py",
    "--model",
    model,
    "--run-dir",
    str(lm8g_run_dir / "lm8f_runs"),
]
```

LM8G may add no LM8F flags beyond the model and run-dir needed for canonical
repeatability accounting.

Full stdout/stderr are not stored in v1. Attempt rows store bounded excerpts.
Suggested excerpt bound:

```text
2000 characters each for stdout_excerpt and stderr_excerpt
```

## 8. Child Run Discovery

Before each LM8F invocation, LM8G snapshots existing child directories:

```text
lm8g_run_dir/lm8f_runs/lm8f-*
```

After the subprocess exits or times out, LM8G snapshots again and computes the
new child run dirs for that attempt.

Expected normal case:

```text
exactly one new lm8f-* child run dir
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
exists, LM8G should still record that path, run report-only marker scanning on
it, and include bounded excerpts. The wrapper terminal category remains
`wrapper_error`.

LM8G must not parse stdout as the source of truth for child run discovery.

## 9. Terminal Categories

LM8G scheduled terminal categories:

- `accepted`
- `rejected`
- `worker_declined`
- `publication_failed`
- `gate_failed`
- `preflight_failed`
- `wrapper_error`

Classification from child LM8F `decision.json`:

```text
accepted -> accepted
rejected -> rejected
worker_declined -> worker_declined
publication_failed -> publication_failed
gate_failed -> gate_failed
preflight_failed -> preflight_failed
```

`wrapper_error` covers:

- LM8F subprocess timeout
- LM8F subprocess nonzero return code
- missing child run dir
- ambiguous child run dir
- missing `decision.json`
- unreadable `decision.json`
- invalid JSON in `decision.json`
- non-mapping `decision.json`
- child decision value outside the known LM8F vocabulary

Subprocess health is wrapper evidence, not worker evidence. If LM8F exits
nonzero:

```text
terminal_category = wrapper_error
failure_reason = lm8f_nonzero_returncode:<code>
```

This applies even if partial child artifacts exist.

Timeout classification:

```text
terminal_category = wrapper_error
failure_reason = lm8f_timeout
```

No wrapper error should be reclassified as `rejected`, because `rejected` is an
LM8F terminal decision after live mutation or verification semantics.

## 10. Attempt Row Fields

Each `attempts.jsonl` row should include at least:

```text
attempt_index
scheduled_attempt_id
lm8f_invoked
lm8f_returncode
lm8f_run_dir
lm8f_decision
lm8f_reason
terminal_category
failure_reason
stdout_excerpt
stderr_excerpt
worker_publication_ran
live_fixture_created
live_set_value_dispatched
verify_scalar_output_ran
scalar_runtime_ready
worker_action_value
verifier_attempt_count
observed_output_after
leak_check_performed
leak_marker_matches
leak_marker_match_count
```

`worker_action_value` is read from child `worker_action.json` or from the
bounded `decision.json` action excerpt only when available and parseable. If the
value is unavailable, the field should be `null`; the row should not fail merely
because an action value cannot be summarized.

`verifier_attempt_count` comes from child `verify_scalar_output_summary.json`
when present. If the verifier did not run, it should be `null`.

## 11. Summary Fields

`summary.json` should include at least:

```text
schema
scheduled_attempts
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
leak_marker_match_count
attempt_run_dirs
worker_action_values
verifier_attempt_counts
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

## 12. Leak Scan

LM8G performs report-only marker scanning over each child LM8F run directory.

Markers:

```text
PROBE_REPAIR_CODE
A = 42.0
BindStepSpec.base_params
repair_same_component.bind.base_params
```

Marker scanning must not override LM8F terminal classification. LM8F child
decisions remain authoritative for worker/live outcomes. LM8G reports marker
matches in attempt rows and aggregate summary only.

## 13. Artifact Layout

LM8G writes:

```text
probe_runs/lm8g-<timestamp>-<sha>/
  manifest.json
  attempts.jsonl
  summary.json
  lm8f_runs/
    lm8f-<timestamp>-<sha>/
    lm8f-<timestamp>-<sha>/
    lm8f-<timestamp>-<sha>/
    lm8f-<timestamp>-<sha>/
    lm8f-<timestamp>-<sha>/
```

LM8G must not copy raw LM8F model transcripts or duplicate child artifacts into
top-level summaries. The child LM8F run dirs remain the source of detailed
evidence.

## 14. Interpretation

LM8G success reads:

```text
5/5 or 4/5 accepted:
  scalar transform family is stable enough to consider a deeper scalar pressure
  slice.

mixed accepted/rejected:
  inspect whether failures are worker arithmetic, publication shape, fixture
  timing, verifier settle, or tool readiness.

worker_declined/publication_failed:
  scalar evidence or action affordance may still need worker-facing polish.

gate_failed/preflight_failed/wrapper_error:
  fixture/tooling/wrapper readiness is not stable enough to interpret scalar
  worker repeatability cleanly.
```

LM8G must not claim:

- broad scalar reasoning reliability
- topology/wiring authorship
- batch edit competence
- Planner competence
- third-family transfer
- complexity scaling beyond the LM8F fixture

If LM8G is stable, the next capability-pressure candidate is a separate slice,
for example:

```text
LM8H affine scalar transform:
observed_output = editable_value * 2.0 + 1.5
expected_output = 7.5
worker-derived editable value = 3.0
```

LM8H must not be folded into LM8G.

## 15. Deterministic Test Targets

Implementation tests should use monkeypatched subprocess runners and synthetic
child run dirs. Tests must not require Rhino, Grasshopper, Ollama, or live
models.

Required deterministic coverage:

- default CLI produces canonical LM8G shape
- `--attempts` must be positive
- non-default model makes `canonical_evidence` false
- subprocess command uses `sys.executable`
- child LM8F run dir is discovered from filesystem delta, not stdout
- accepted child decision classifies as `accepted`
- rejected child decision classifies as `rejected`
- `gate_failed`, `preflight_failed`, `publication_failed`, and
  `worker_declined` classify directly from child `decision.json`
- nonzero LM8F return code becomes `wrapper_error`
- timeout becomes `wrapper_error`
- missing decision file becomes `wrapper_error`
- invalid decision JSON becomes `wrapper_error`
- non-mapping decision JSON becomes `wrapper_error`
- missing child run dir becomes `wrapper_error`
- ambiguous child run dir becomes `wrapper_error`
- worker_reached_count derives from `worker_publication_ran`
- worker action values are summarized when available
- verifier attempt counts are summarized when available
- leak marker scan is report-only and does not alter terminal category
- implementation PR does not run live LM8G

## 16. Post-Merge Evidence Run

After the implementation PR merges and local `main` is synced, run one
canonical LM8G evidence attempt:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8g_scalar_transform_repeatability_probe.py
```

Prerequisites:

- Rhino open and responsive
- Grasshopper open and responsive
- LM8F direct GH tools available
- Ollama model `gemma4:12b-it-qat` available

After the run, inspect:

```text
manifest.json
attempts.jsonl
summary.json
each child LM8F decision.json
leak_marker_match_count
accepted/rejected/declined/publication/gate/preflight/wrapper counts
worker_action_values
verifier_attempt_counts
```

Do not replace failed attempts. Any scheduled outcome is evidence.
