# LM5R Two-Pass Publication Probe Design

## 1. Purpose

LM5R is a diagnostic evidence-only probe.

LM5Q showed that direct Ollama structured output can preserve thinking while
still changing the published worker disposition:

```text
same exact thinking
different final response kind
because constrained full-union publication can alter the final choice
```

The doctrine for LM5R is:

```text
think free, decide free, publish constrained
```

LM5R tests whether separating the worker decision from strict publication lets a
local Gemma worker produce LM5G-loadable responses without letting the
constrained publication step re-decide the disposition.

The primary question is:

```text
If pass 1 freely decides the worker disposition, can pass 2 publish a strict
LM5G-loadable envelope while preserving that decision?
```

## 2. Scope

LM5R may add:

```text
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
docs/superpowers/specs/2026-07-04-lm5r-two-pass-publication-probe-design.md
docs/superpowers/plans/2026-07-04-lm5r-two-pass-publication-probe.md
```

LM5R must not change:

```text
mcp_server/src/rook/**/*.py
scripts/lm5k_worker_probe.py
scripts/lm5p_ollama_think_format_spike.py
LM5G response loader/parser behavior
LM5J prompt text
LM5N evidence packets
LM5K probe runner
production transport APIs
```

LM5R does not add:

```text
production adapter behavior
LiteLLM integration
schema ordering probe
prompt/schema wording experiment
LM5G parser leniency
evidence-push changes
semantic repair scoring
broad model panel
curated probe evidence doc update during implementation
```

Raw and summary artifacts remain local under ignored `probe_runs/`.

## 3. Probe Shape

LM5R uses a new sibling script:

```text
scripts/lm5r_two_pass_publication_probe.py
```

Reason: LM5P/LM5Q are matrix probes over provider mechanics. LM5R is a chained
two-call publication workflow with pass-1/pass-2 state. Keeping it separate
makes the evidence artifact easier to inspect and avoids overloading the LM5P
matrix script.

The probe uses direct Ollama REST only:

```text
POST http://localhost:11434/api/chat
```

It uses stdlib HTTP and JSON support only, following the LM5P pattern:

```text
urllib.request
urllib.error
json
argparse
hashlib
subprocess
datetime
pathlib
```

No `requests`, `httpx`, Ollama Python client, or LiteLLM belongs in LM5R.

## 4. Canonical Run

Canonical model:

```text
gemma4:12b-it-qat
```

Canonical scenarios:

```text
evidence_absent_like
evidence_present_like
```

Canonical attempts:

```text
5
```

Canonical call count:

```text
2 scenarios * 5 attempts * 2 passes = 20 provider calls
```

Canonical command:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --model "gemma4:12b-it-qat" `
  --scenario evidence_absent_like `
  --scenario evidence_present_like `
  --attempts 5 `
  --excerpt-chars 1200
```

No Anthropic key is required.

## 5. Pass 1: Free Decision

Pass 1 is the decision pass:

```text
direct Ollama /api/chat
no format
think=true
temperature=0
real LM5N request envelope
```

LM5R may import these LM5K probe helpers only:

```text
_SCENARIOS
build_probe_context
```

LM5R may then call:

```text
render_local_worker_turn_request_payload(...)
render_local_worker_prompt_artifact(...)
```

LM5R must not call:

```text
run_probe
run_candidate
_default_transport_factory
LiteLLMWorkerTransport
run_local_worker_adapter
run_local_worker_turn
evaluate_local_worker_scenario_result
```

Pass 1 uses the real LM5J prompt artifact for the scenario request, with an
added diagnostic instruction asking for a small decision JSON object. Pass 1 is
not grammar-constrained and is not expected to be LM5G-loadable.

## 6. Pass-1 Decision Artifact

Pass 1 is semi-structured but not strict LM5G. The script extracts the first
balanced JSON object from `message.content`.

Rules:

```text
surrounding prose is allowed
first balanced JSON object is extracted
extracted text must parse as JSON
parsed value must be a mapping
kind must be one of the four LM5 response kinds
no regex/prose classification fallback
```

If no valid decision object is found, the attempt stops before pass 2.

Required decision fields:

```text
all:
  kind

action_request:
  action_id

clarification_request:
  question

refusal:
  category
  reason

observation:
  message
```

Optional decision fields:

```text
rationale
intent
action_input_intent
known_inputs
data_intent
```

Optional decision field types are fail-closed:

```text
rationale: string
intent: string
action_input_intent: mapping|string
known_inputs: mapping
data_intent: mapping|string
```

Wrong optional field types make the pass-1 decision invalid before pass 2.

Validation is lightweight and local to the probe. Pass 1 is not run through
LM5G, LM5B, LM5C, LM5D, or LM5F.

Failure examples:

```text
pass1_no_json_object
pass1_json_invalid:<ExceptionClassName>
pass1_decision_not_mapping
pass1_unknown_kind
pass1_missing_action_id
pass1_missing_question
pass1_missing_refusal_category
pass1_missing_refusal_reason
pass1_missing_observation_message
```

## 7. Pass 2: Constrained Publication

Pass 2 is the publication pass:

```text
direct Ollama /api/chat
formatter-only prompt
format=<single-kind schema>
think=false
temperature=0
```

`think=false` is allowed only because pass 1 already chose the response kind and
pass 2 receives a single-kind schema. This is not the same as LM5O/LM5Q's
full-union `think=false`.

Pass 2 must not receive the LM5J worker prompt. It receives a smaller
formatter-only prompt:

```text
You are formatting an already-made Rook worker decision.
Do not change the decision kind.
Do not change action_id.
Return exactly one JSON object matching the provided single-kind schema.
Use the original request envelope only to fill fields needed by the chosen
decision.
If required information is missing, preserve the chosen kind and express that
within the chosen envelope where possible; do not switch kinds.
```

Pass 2 payload includes:

```text
request_envelope
decision
response_schema
kind
single_kind_schema
```

The original request envelope remains available so pass 2 can fill fields
needed by the chosen decision. Pass 2 may format or complete fields, but it may
not choose a different disposition or action identity.

## 8. Single-Kind Schemas

LM5R builds single-kind schemas explicitly inside the new script. It must not
dynamically narrow LM5P's full response union.

Reason:

```text
LM5R pass 2 encodes an already-made decision.
The schema must const-pin fields from pass 1.
Explicit builders are easier to test and less likely to retain multiple
branches by accident.
```

Function shape:

```python
def _single_kind_response_schema(decision: Mapping[str, Any]) -> dict[str, Any]:
    ...
```

Common pins:

```text
no oneOf
schema const = LOCAL_WORKER_TURN_RESPONSE_SCHEMA
kind const = pass-1 kind
additionalProperties: false
required field sets match LM5G
```

Variant pins:

```text
action_request:
  required schema, kind, action_id, rationale, input
  action_id const = pass-1 action_id
  input object

clarification_request:
  required schema, kind, question, rationale
  rationale string|null

refusal:
  required schema, kind, category, reason
  category const = pass-1 category

observation:
  required schema, kind, message, data
  data object|null
```

The schema should enforce what it can:

```text
kind cannot change
action_id cannot change for action_request
category cannot change for refusal
```

LM5R still checks invariants after parsing and LM5G loading, because provider
or schema behavior must not be trusted blindly.

## 9. Attempt Status Taxonomy

Each attempt has exactly one status:

```text
pass1_provider_error
pass1_decision_invalid
pass2_provider_error
pass2_lm5g_invalid
pass2_invariant_violation
published
```

Failure reason examples:

```text
pass1_http_error:<status>
pass1_provider_error:<ClassName>
pass1_no_json_object
pass1_json_invalid:<ClassName>
pass1_decision_not_mapping
pass1_unknown_kind
pass1_missing_action_id
pass1_missing_question
pass1_missing_refusal_category
pass1_missing_refusal_reason
pass1_missing_observation_message
pass2_http_error:<status>
pass2_provider_error:<ClassName>
pass2_content_json_invalid:<ClassName>
pass2_content_not_mapping
pass2_lm5g_load_failed:<ClassName>
pass2_kind_changed
pass2_action_id_changed
pass2_refusal_category_changed
```

Invariant order:

```text
parse pass-2 content
LM5G-load it if possible
then check LM5R invariants before status=published
```

A valid LM5G response with changed `kind`, changed `action_id`, or changed
refusal `category` is:

```text
status = pass2_invariant_violation
```

not:

```text
status = published
```

## 10. Attempt Rows

Each row in `attempts.jsonl` records:

```text
model
scenario
attempt
status
failure_reason

pass1_provider_status
pass1_kind
pass1_action_id
pass1_refusal_category
pass1_decision_sha256
pass1_content_excerpt
pass1_content_sha256
pass1_thinking_present
pass1_thinking_chars
pass1_thinking_sha256
pass1_prompt_eval_count
pass1_eval_count

pass2_provider_status
pass2_schema_kind
pass2_response_kind
pass2_action_id
pass2_refusal_category
pass2_content_excerpt
pass2_content_sha256
pass2_prompt_eval_count
pass2_eval_count

kind_preserved
action_id_preserved
refusal_category_preserved
lm5g_loadable
```

`action_id_preserved` is `None` for non-action decisions.
`refusal_category_preserved` is `None` for non-refusal decisions.

No full raw content or full thinking text is stored in JSONL. Excerpts are
bounded by `--excerpt-chars`.

## 11. Summary Artifact

LM5R writes local evidence under:

```text
probe_runs/lm5r-<timestamp>-<sha>/
  manifest.json
  attempts.jsonl
  summary.json
```

Top-level summary shape:

```text
run_id
git_commit
model
scenarios
attempts_per_scenario
groups
```

`groups` are grouped by:

```text
scenario
status
pass1_kind
pass2_response_kind
kind_preserved
action_id_preserved
refusal_category_preserved
```

Each group records:

```text
scenario
status
pass1_kind
pass2_response_kind
kind_preserved
action_id_preserved
refusal_category_preserved
attempts
lm5g_loadable_count
failure_reason_counts
```

No semantic scoring belongs in LM5R.

## 12. Deterministic Tests

Tests should cover the probe mechanics without live Ollama:

```text
first balanced JSON object extraction
pass1 JSON parse failure
pass1 non-mapping decision failure
pass1 unknown kind failure
pass1 missing action_id fails before pass 2
pass1 missing question fails before pass 2
pass1 missing refusal category/reason fails before pass 2
pass1 missing observation message fails before pass 2
single-kind schemas have no oneOf
single-kind schemas const-pin schema and kind
action schema const-pins action_id
refusal schema const-pins category
pass2 different kind -> pass2_invariant_violation
pass2 different action_id -> pass2_invariant_violation
pass2 different refusal category -> pass2_invariant_violation
pass2 LM5G load failure -> pass2_lm5g_invalid
pass2 valid same-kind response -> published
summary groups status/kind/preservation counts
no forbidden imports/calls
```

No live Ollama test belongs in CI.

Nearby gate:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  mcp_server\tests\test_local_worker_model_transport.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Compile gate:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
```

Static scope:

```text
production diff must be empty under mcp_server/src
no LM5K runner changes
no LM5P script changes
no parser/prompt/evidence-packet changes
git diff --check
```

## 13. Run Evidence

After deterministic gates pass, run the canonical live probe manually.

Report:

```text
run directory
git commit
Ollama version
model metadata
row count: 10
pass1 status/kind counts
pass2 status/kind counts
published count
LM5G-loadable count
kind_preserved count
action_id_preserved count for action decisions
representative bounded excerpts for absent and present scenarios
failure_reason counts
confirmation that probe_runs artifacts are ignored and uncommitted
```

Interpretation:

```text
evidence_absent_like pass1 chooses clarification_request and pass2 publishes
clarification_request:
  two-pass publication preserves restraint.

evidence_absent_like pass1 chooses clarification_request but pass2 changes kind:
  formatter still re-decides or schema/instruction is insufficient.

evidence_present_like pass1 chooses action_request and pass2 preserves action:
  two-pass publication can carry action decisions.

evidence_present_like pass1 chooses clarification_request and pass2 preserves
clarification_request:
  publication works, but evidence or decision quality remains the next question.
```

Do not update the curated probe evidence doc until after the LM5R run results
are reviewed.
