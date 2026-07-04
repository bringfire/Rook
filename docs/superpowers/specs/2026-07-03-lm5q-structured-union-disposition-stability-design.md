# LM5Q Structured Union Disposition Stability Design

## 1. Purpose

LM5Q is a diagnostic evidence-only slice.

LM5P answered the direct Ollama think/format compatibility question:

```text
Direct Ollama can preserve message.thinking while enforcing the full LM5
response envelope.
```

It also falsified the simpler diagnosis:

```text
Thinking preservation alone does not preserve evidence_absent restraint.
```

The key LM5P exhibit was that `evidence_absent_like` produced identical
thinking hashes across free and structured modes while final response kind
changed:

```text
free_think_true   -> clarification_request, not LM5G-loadable
format_default    -> action_request, LM5G-loadable
format_think_true -> action_request, LM5G-loadable
```

LM5Q repeats and isolates that phenomenon before any two-pass transport,
schema-ordering experiment, or production local-worker transport change.

The doctrine update is:

```text
think free, decide free, publish constrained
```

not merely:

```text
think free, publish constrained
```

LM5Q asks:

```text
Is Gemma's structured evidence_absent over-action stable across repeated direct
Ollama runs, and can exact repeated thinking hashes show final disposition
changes under constrained union output?
```

Gemma is the canonical witness model for LM5Q; this slice tests structured-union
disposition stability as a general transport phenomenon, not a Gemma-specific
policy.

## 2. Scope

LM5Q may change:

```text
scripts/lm5p_ollama_think_format_spike.py
mcp_server/tests/test_lm5p_ollama_think_format_spike.py
docs/superpowers/specs/2026-07-03-lm5q-structured-union-disposition-stability-design.md
docs/superpowers/plans/2026-07-03-lm5q-structured-union-disposition-stability.md
```

LM5Q must not change:

```text
mcp_server/src/rook/**/*.py
scripts/lm5k_worker_probe.py
LM5G response loader/parser behavior
LM5J prompt text
LM5N evidence packets
LM5K probe runner
LM5P response union schema
production transport APIs
```

LM5Q does not add:

```text
two-pass transport
schema ordering probe
prompt/schema wording experiment
llama.cpp integration
Anthropic/Haiku/Sonnet comparison
curated evidence doc update during implementation
semantic repair scoring
fuzzy thinking comparison
```

Raw and summary artifacts remain local under ignored `probe_runs/`.

## 3. Canonical Matrix

Canonical model:

```text
gemma4:12b-it-qat
```

Canonical scenarios:

```text
evidence_absent_like
evidence_present_like
```

Canonical modes:

```text
free_think_true
format_default
format_think_true
format_think_false
```

Canonical attempts:

```text
5
```

Canonical call count:

```text
1 model * 2 scenarios * 4 modes * 5 attempts = 40 rows
```

Canonical command:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5p_ollama_think_format_spike.py `
  --model "gemma4:12b-it-qat" `
  --scenario evidence_absent_like `
  --scenario evidence_present_like `
  --mode free_think_true `
  --mode format_default `
  --mode format_think_true `
  --mode format_think_false `
  --attempts 5 `
  --excerpt-chars 1200
```

`free_default` is intentionally excluded. LM5P already showed thinking appears
there, and LM5Q needs `free_think_true` as the clean free-decision baseline.

## 4. Script Changes

LM5P already supports:

```text
--model
--scenario
--mode
--attempts
```

LM5Q should add the smallest missing support:

```text
--excerpt-chars
```

Default remains:

```text
500
```

Canonical LM5Q run uses:

```text
1200
```

Reason: LM5P's 500-character content excerpt sometimes cut off before the
authored action input. LM5Q needs enough bounded final content to inspect
whether an action request copied failing code, authored a plausible repair, or
invented fields.

The script should continue to avoid storing full raw content or thinking in
JSONL. Increasing the excerpt length is a local diagnostic knob, not a raw
capture mode.

## 5. Local Summary Artifact

LM5Q adds a local summary file beside `attempts.jsonl`:

```text
probe_runs/lm5p-<timestamp>-<sha>/
  manifest.json
  attempts.jsonl
  summary.json
```

`summary.json` is local evidence only:

```text
not committed
not a curated doc
not a production report format
not LM5F
```

If `summary.json` cannot be written after attempts are written, the script
should fail loudly because the diagnostic artifact is incomplete.

## 6. Summary Shape

Top-level shape:

```text
run_id
git_commit
models
scenarios
modes
attempts_per_cell
groups
thinking_hash_groups
```

`groups` are grouped by:

```text
model
scenario
mode
```

Each group records:

```text
model
scenario
mode
attempts
provider_errors
lm5g_loadable_count
response_kind_counts
thinking_present_count
unique_thinking_hash_count
unique_content_hash_count
failure_reason_counts
```

Counts are derived only from `attempts.jsonl` rows already written.

No semantic scoring is allowed.

## 7. Thinking Hash Groups

`thinking_hash_groups` are exact-hash only.

Group key:

```text
model
scenario
thinking_sha256
```

Rows with:

```text
thinking_sha256 == null
```

are excluded.

Each thinking hash group records:

```text
model
scenario
thinking_sha256
thinking_chars
attempts
modes
response_kind_counts
lm5g_loadable_count
failure_reason_counts
```

The purpose is to make this question visible without manual row inspection:

```text
Did identical thinking produce different final response kinds under different
modes?
```

Sorting must be deterministic:

```text
groups sorted by model, scenario, mode
thinking_hash_groups sorted by model, scenario, thinking_sha256
modes sorted by first appearance according to run mode order, not alphabetically
count mappings sorted by key
```

No fuzzy comparison, similarity score, or "problem detected" boolean belongs in
LM5Q.

If exact thinking hashes mostly form singleton groups, that is also evidence.

## 8. Interpretation

LM5Q success is not:

```text
Gemma behaves correctly
```

LM5Q success is:

```text
The repeated diagnostic matrix produces clear evidence about whether structured
union output repeatedly changes absent/present disposition.
```

Reads:

```text
format modes repeatedly flip evidence_absent to action_request:
  single-pass constrained union is not safe as the durable publication
  mechanism.

format_think_false repeatedly preserves paired behavior:
  this is a lead, not a production policy, until explained.

thinking_hash_groups show identical thinking with different response_kind:
  final-answer publication is re-deciding or distorting the disposition.

thinking hashes are all unique:
  exact repeatability is absent, but response_kind distributions still matter.
```

Likely follow-up after LM5Q:

```text
two-pass formalization design
```

Possible follow-ups, not in LM5Q:

```text
schema/union ordering probe
prompt/schema interaction probe
formalizer constrained to an already-chosen kind
```

## 9. Testing

Deterministic tests should cover:

```text
--excerpt-chars default and custom values
excerpt length applied to message_content_excerpt
thinking_excerpt still uses the same configured excerpt length
summary.json written from attempt rows
group counts by model/scenario/mode
thinking_hash_groups exact-hash behavior
rows with null thinking_sha256 excluded from thinking_hash_groups
deterministic sorting
summary failure is not silently ignored
```

No live Ollama test belongs in CI.

Nearby gate:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Compile gate:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py
```

Static scope:

```text
production diff must be empty under mcp_server/src
no LM5K runner changes
no parser/prompt/evidence-packet changes
git diff --check
```

## 10. Run Evidence

After deterministic gates pass, run the canonical matrix manually.

Report:

```text
run directory
git commit
Ollama version
model metadata
row count: 40
summary group counts
thinking_hash_groups with multiple response_kind values
representative bounded excerpts for evidence_absent action_request rows
representative bounded excerpts for evidence_present action_request rows
failure_reason counts
confirmation that probe_runs artifacts are ignored and uncommitted
```

Do not update the curated probe evidence doc until after the LM5Q run results
are reviewed.
