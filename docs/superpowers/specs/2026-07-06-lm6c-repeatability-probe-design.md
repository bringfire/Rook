# LM6C - Repeatability Probe Design

- **Date:** 2026-07-06
- **Status:** Draft for review
- **Slice:** LM6C
- **Type:** Deterministic wrapper design with post-merge live evidence run

## 1. Purpose

LM6B froze the v1 bounded-worker protocol shape after the LM6A arrival run.
LM6C measures whether that frozen protocol repeats.

Core question:

```text
Is the LM6A arrival path a stable primitive or a one-off?
```

LM6C does not change the protocol. It measures repeatability of the protocol
already frozen by LM6B:

```text
N=5 full LM6A arrival loops,
same fixture,
same model,
same protocol,
no code/prompt changes unless a deterministic wrapper/preflight harness defect
blocks interpretability.
```

LM6C is repeatability evidence, not a product-readiness declaration.

## 2. Scope

Implementation scope:

```text
docs/superpowers/specs/2026-07-06-lm6c-repeatability-probe-design.md
docs/superpowers/plans/2026-07-06-lm6c-repeatability-probe.md
scripts/lm6c_repeatability_probe.py
mcp_server/tests/test_lm6c_repeatability_probe.py
```

Allowed only if tests expose a real blocker:

```text
tiny LM6A CLI/run-dir compatibility fix
```

Default exclusions:

- no LM6A behavior changes
- no LM5/LM6 protocol changes
- no prompt changes
- no worker behavior changes
- no production `mcp_server/src` changes
- no live run in the implementation PR
- no `probe_runs/` artifacts committed
- no curated evidence summary in the implementation PR

Tests must monkeypatch or substitute preflight and subprocess calls. No test may
require Rhino, Grasshopper, Ollama, or a live model.

## 3. Canonical Command

Canonical LM6C evidence command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6c_repeatability_probe.py
```

Canonical settings:

```text
attempts = 5
model = gemma4:12b-it-qat
run_dir = probe_runs
attempt_timeout_s = 600
```

Ad hoc smoke runs may use `--attempts 1`, but they cannot be cited as LM6C
repeatability evidence.

`canonical_evidence` is true only when:

```text
attempts == 5
model == "gemma4:12b-it-qat"
```

## 4. Attempt Boundary

LM6C uses five independent scheduled attempts. Each attempt starts with a fresh
live document boundary.

Scheduled attempt:

```text
rhino_ping
gh_document_new
full LM6A invocation
terminal decision
```

There is no separate LM6A `--phase receipt_recon` step. Full LM6A already runs
Phase A internally. A separate recon would create an extra live component before
the real splice attempt and would measure `recon + splice`, not one clean splice.

Each scheduled attempt is independent:

- fresh GH document before the attempt
- separate LM6A child run directory
- no retry
- no replacement attempt
- no internal LM6A protocol change

## 5. Denominators

LM6C uses two denominators.

Scheduled denominator:

```text
5 scheduled attempts
```

Worker denominator:

```text
attempts where LM6A passes Phase A and reaches worker publication
```

This split preserves two truths:

- preflight and routing instability matter operationally
- preflight and routing failures are not worker/model behavior

LM6C must not hide gate failures by replacing attempts.

## 6. Terminal Categories

Scheduled terminal categories:

- `preflight_failed`
- `gate_failed`
- `accepted`
- `rejected`
- `worker_declined`
- `publication_failed`
- `wrapper_error`

Definitions:

```text
preflight_failed:
  rhino_ping or gh_document_new failed before LM6A invocation.

gate_failed:
  LM6A ran, but Phase A rejected receipt/routing/extraction/criteria readiness.

accepted:
  LM6A ended accepted.

rejected:
  LM6A ended rejected.

worker_declined:
  LM6A reached worker publication and the worker published a non-action terminal
  response.

publication_failed:
  LM6A failed in worker publication.

wrapper_error:
  LM6C could not classify the LM6A invocation because the subprocess crashed,
  timed out, omitted decision.json, or wrote invalid/unreadable decision JSON.
```

Classification from LM6A `decision.json`:

```text
accepted -> accepted
rejected -> rejected
worker_declined -> worker_declined
publication_failed -> publication_failed
gate_failed -> gate_failed
anything unreadable/missing -> wrapper_error
```

If LM6A returns a nonzero exit code:

```text
terminal_category = wrapper_error
failure_reason = lm6a_nonzero_returncode:<code>
```

This applies even if partial child artifacts exist. Subprocess health remains
separate from LM6A decision semantics.

Timeout classification:

```text
terminal_category = wrapper_error
failure_reason = lm6a_timeout
```

## 7. Wrapper Script

LM6C adds a small deterministic wrapper:

```text
scripts/lm6c_repeatability_probe.py
```

Responsibilities:

- run exactly `--attempts` scheduled attempts
- default to five attempts
- call `rhino_ping` and `gh_document_new` before each scheduled attempt
- skip LM6A when preflight fails
- invoke full LM6A as a subprocess after preflight passes
- read the child LM6A `decision.json`
- classify the scheduled terminal category
- write combined LM6C artifacts

The wrapper must invoke LM6A with `sys.executable`.

Subprocess command shape:

```python
[
    sys.executable,
    "scripts/lm6a_live_worker_splice_probe.py",
    "--model",
    model,
    "--run-dir",
    str(lm6c_run_dir / "lm6a_runs"),
]
```

LM6C does not import or mutate LM6A internals.

LM6C discovers the LM6A child run directory by inspecting the
`lm6c_run_dir / "lm6a_runs"` directory after the subprocess returns. For each
attempt, it uses the newest and only `lm6a-*` directory created under that
directory during the attempt. Stdout may be excerpted for diagnostics, but stdout
is not the source of truth for child run-dir discovery.

## 8. CLI

CLI options:

```text
--attempts
  positive integer
  default 5

--model
  default gemma4:12b-it-qat

--run-dir
  default probe_runs

--attempt-timeout-s
  default 600
```

Invalid CLI values fail before any live preflight call.

## 9. Artifacts

LM6C writes:

```text
probe_runs/lm6c-<timestamp>-<sha>/
  manifest.json
  attempts.jsonl
  summary.json
  lm6a_runs/
    ...
```

LM6A child run artifacts remain in their own ignored subdirectory. LM6C does not
copy raw model transcripts into the parent run.

The implementation PR must not include any `probe_runs/` artifacts.

## 10. Attempt Rows

Each `attempts.jsonl` row includes:

```text
attempt_index
scheduled_attempt_id
preflight_status
lm6a_invoked
lm6a_returncode
lm6a_run_dir
lm6a_decision
lm6a_reason
terminal_category
stdout_excerpt
stderr_excerpt
failure_reason
leak_check_performed
leak_marker_matches
leak_marker_match_count
```

Excerpt bounds:

```text
stdout_excerpt <= 2000 chars
stderr_excerpt <= 2000 chars
```

Full stdout/stderr are not stored in v1.

## 11. Summary

`summary.json` includes:

```text
scheduled_attempts
terminal_category_counts
preflight_failed_count
lm6a_invoked_count
gate_failed_count
worker_reached_count
worker_terminal_counts
accepted_count
leak_marker_match_count
attempt_run_dirs
canonical_evidence
```

`worker_terminal_counts` includes only attempts where LM6A reached worker
publication:

```text
accepted
rejected
worker_declined
publication_failed
```

`gate_failed`, `preflight_failed`, and `wrapper_error` are excluded from the
worker denominator.

## 12. Leak Checks

LM6C performs report-only leak checks against each LM6A child run directory.

Markers:

```text
PROBE_REPAIR_CODE
A = 42.0
BindStepSpec.base_params.code
```

Per-attempt fields:

```text
leak_check_performed
leak_marker_matches
leak_marker_match_count
```

Aggregate field:

```text
leak_marker_match_count
```

Semantics:

```text
LM6A owns leak enforcement.
LM6C only summarizes whether marker strings appeared in child run artifacts.
Leak marker matches do not override LM6A decision classification.
```

This matters because LM6A may intentionally record rejected hidden-answer-like
worker output in ignored local artifacts. LM6C reports that marker presence; it
does not reinterpret it.

## 13. Pre-Registered Interpretation

If worker-reached attempts are consistently accepted:

```text
LM6A arrival appears repeatable enough to move upstream to Planner/compiler
routing authorship.
```

If attempts frequently reach the worker but end in `worker_declined`,
`publication_failed`, or `rejected`:

```text
Design pull-loop and reliability instrumentation before moving upstream.
```

If attempts frequently end `preflight_failed`:

```text
Treat that as live-environment readiness evidence, not worker behavior.
```

If attempts frequently end `gate_failed`:

```text
Treat that as protocol/routability readiness evidence, not model behavior.
```

If wrapper errors occur:

```text
Treat them as harness defects or subprocess/runtime failures. Do not replace the
attempts.
```

## 14. Verification

Implementation PR verification:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm6c_repeatability_probe.py `
  -q

py -3.10 -m py_compile `
  scripts\lm6c_repeatability_probe.py `
  mcp_server\tests\test_lm6c_repeatability_probe.py

git diff --check main..HEAD
```

Static scope checks:

- no production `mcp_server/src` changes
- no LM6A changes unless a tiny CLI/run-dir compatibility blocker is proven
- no LM5/LM6 prompt changes
- no `probe_runs/` artifacts
- `knowledge/gh/operations_knowledge.json` remains unstaged unless a dedicated
  telemetry slice owns it

Post-merge live evidence:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6c_repeatability_probe.py
```

The live run happens only after implementation merges to synced `main`.

## 15. Next Step

After the post-merge canonical live run, write a separate doc-only evidence
summary PR. The evidence summary should report both denominators:

```text
scheduled outcome counts over 5 attempts
worker-reached outcome counts over attempts where worker publication was reached
```

LM6C must not update the LM6B protocol freeze unless repeatability exposes a
deterministic preflight or validator defect that prevents the run from being
interpretable.
