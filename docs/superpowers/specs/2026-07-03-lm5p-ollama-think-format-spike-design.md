# LM5P Ollama Think + Format Compatibility Spike Design

## 1. Purpose

LM5P is a diagnostic spike-only slice.

It asks one provider-mechanics question:

```text
Can direct Ollama preserve thinking/deliberation metadata while enforcing the
full LM5 response envelope with format=<LM5 response union schema>?
```

LM5O showed that Gemma free-text output can show better intent but invalid LM5
envelopes, while structured output fixes the envelope and collapses completion
tokens. The suspected failure mode is that grammar-constrained decoding from
token zero suppresses or bypasses the model's thinking path.

LM5P diagnoses that suspicion. It does not implement a new production transport
policy.

## 2. Non-Goals

LM5P does not change:

```text
LM5G response loader
LM5J prompt text
LM5N evidence packets
LM5K probe runner
LiteLLM transport
parser strictness
allowed action authority
```

LM5P does not add:

```text
two-pass transport
llama.cpp integration
Anthropic/Haiku/Sonnet comparison
model-specific production branches
action-only schema
live Rhino/GH execution
tool dispatch
graph mutation
curated evidence doc update during implementation
```

Raw spike artifacts stay local under ignored `probe_runs/`.

## 3. Artifact

Add one committed script:

```text
scripts/lm5p_ollama_think_format_spike.py
```

The script is a manual live diagnostic. It is not CI and it is not a production
module.

It writes local evidence:

```text
probe_runs/lm5p-<YYYYMMDDTHHMMSSZ>-<git_sha>/
  manifest.json
  attempts.jsonl
```

It also prints a compact table to stdout.

Do not commit the run directory.

## 4. Direct Ollama Transport

LM5P uses stdlib REST only:

```text
urllib.request
urllib.error
json
time
hashlib
argparse
subprocess
datetime
pathlib
collections
```

No:

```text
requests
httpx
ollama Python client
LiteLLM
```

Endpoint:

```text
POST http://localhost:11434/api/chat
```

Base request:

```json
{
  "model": "...",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "stream": false,
  "options": {"temperature": 0}
}
```

Format modes add:

```json
"format": <full LM5 response union schema>
```

Think modes add:

```json
"think": true
```

or:

```json
"think": false
```

When omitted, `think` is not present in the request.

## 5. Real LM5N Prompt Envelopes

LM5P should use the same LM5J prompt artifact shape that the model adapter sees.

Allowed imports from the LM5K probe script:

```text
_SCENARIOS
build_probe_context
```

Allowed Rook imports:

```text
render_local_worker_turn_request_payload(...)
render_local_worker_prompt_artifact(...)
load_local_worker_turn_response_payload(...)
LOCAL_WORKER_TURN_RESPONSE_SCHEMA
```

Flow:

```text
_SCENARIOS["evidence_absent"]
-> build_probe_context(...)
-> render_local_worker_turn_request_payload(...)
-> render_local_worker_prompt_artifact(...)
-> artifact["messages"]
-> direct Ollama /api/chat
```

And the same for `evidence_present`.

LM5P must not call:

```text
run_probe
run_candidate
_default_transport_factory
LiteLLMWorkerTransport
run_local_worker_adapter
run_local_worker_turn
evaluate_local_worker_scenario_result
LM5D harness helpers
LM5F evaluation helpers
```

This gives LM5P real LM5N absent/present envelopes without duplicating fragile
probe fixture setup or running the LM5K model panel.

## 6. Full LM5 Response Union Schema

The format schema must be the full LM5G response envelope contract, not
action-only.

Root:

```text
oneOf with exactly four variants
```

Each variant has:

```text
schema const = rook.local_worker_turn_response:v1
kind const
required exact field set
additionalProperties: false
```

Variants:

```text
action_request:
  schema, kind, action_id, rationale, input

clarification_request:
  schema, kind, question, rationale

refusal:
  schema, kind, category, reason

observation:
  schema, kind, message, data
```

The refusal category enum mirrors LM5B's current category vocabulary:

```text
unsafe
insufficient_context
unsupported_action
out_of_scope
```

## 7. Matrix

Canonical default model:

```text
gemma4:12b-it-qat
```

`gemma4:12b` remains available through explicit `--model gemma4:12b` as an
optional challenger. It is not part of the canonical default because the LM5P
implementation run observed local Ollama instability/hanging before the model
wrote its first row. That partial hang is non-canonical evidence, not a blocker
for LM5P completion.

Scenarios:

```text
evidence_absent_like
evidence_present_like
```

Modes:

```text
free_default
free_think_true
format_default
format_think_true
format_think_false
```

Private mode table:

```python
_MODES = {
    "free_default": {"format": False, "think": "omitted"},
    "free_think_true": {"format": False, "think": True},
    "format_default": {"format": True, "think": "omitted"},
    "format_think_true": {"format": True, "think": True},
    "format_think_false": {"format": True, "think": False},
}
```

`think_requested` in evidence rows is one of:

```text
omitted
true
false
```

`format_enabled` is boolean.

Default attempts:

```text
1
```

Default call count:

```text
1 model * 2 scenarios * 5 modes * 1 attempt = 10 calls
```

`--attempts` may increase attempts per cell for manual follow-up, and
`--model` may add or replace explicit challenger models when a non-canonical
comparison is desired.

## 8. Evidence Fields

Each `attempts.jsonl` row records:

```text
run_id
git_commit
ollama_version
model
model_id
model_quantization
scenario
mode
attempt_index
format_enabled
think_requested
provider_status
provider_json_valid
content_json_valid
content_is_mapping
schema_literal
lm5g_loadable
response_kind
message_content_excerpt
message_content_sha256
thinking_present
thinking_chars
thinking_excerpt
thinking_sha256
prompt_eval_count
eval_count
total_duration
load_duration
prompt_eval_duration
eval_duration
done_reason
failure_reason
```

Bounded excerpts:

```text
message_content_excerpt: first 500 chars
thinking_excerpt: first 500 chars
```

The full content and thinking strings should not be copied into JSONL. Store
hashes and bounded excerpts only.

Record separate facts:

```text
provider_json_valid:
  Ollama returned a usable response JSON object.

content_json_valid:
  message.content parsed as JSON.

lm5g_loadable:
  parsed content loaded through LM5G.
```

Free modes may produce non-JSON or non-LM5G output. That is expected evidence,
not a spike failure.

## 9. Manifest

`manifest.json` records:

```text
run_id
timestamp_utc
git_commit
ollama_version
models
scenarios
modes
attempts_per_cell
endpoint
temperature
script_schema/version
```

The manifest should state:

```text
raw artifacts are local evidence and are not committed
```

## 10. Failure Handling

The script should continue across matrix cells when a provider call fails.

Provider call failures record:

```text
provider_status = error
failure_reason = provider_error:<ClassName>
```

HTTP error responses record:

```text
provider_status = error
failure_reason = http_error:<status>
```

Provider JSON parse failures record:

```text
provider_json_valid = false
failure_reason = provider_json_invalid:<ClassName>
```

Content JSON and LM5G loader failures are row-level evidence, not process
failures.

The process should exit nonzero only for setup errors such as:

```text
invalid CLI arguments
unable to create run directory
unable to build LM5N request envelopes
```

## 11. Interpretation

LM5P answers provider compatibility questions:

```text
Does this model expose thinking without format?
Does format suppress thinking by default?
Does format + think=true preserve thinking metadata?
Does format + think=true still return LM5G-loadable content?
Does think=false look like the compressed structured-output behavior from LM5O?
```

Success/failure reads:

```text
format + think=true preserves thinking and LM5G-loadable content:
  future slice may design a small production option.

format always suppresses thinking:
  next design is likely two-pass transport.

direct Ollama works but LiteLLM does not:
  the issue is transport path, not Gemma.

neither Gemma variant preserves thinking under format:
  stop chasing Gemma variants for this variable.
```

LM5P does not score scenario correctness, semantic repair quality, or model
rankings. It records mechanics.

## 12. Testing And Verification

Add targeted deterministic tests for the script:

```text
schema has full four-kind union
mode table exactness
request body construction for format/think combinations
bounded excerpt/hash behavior
row classification for content JSON and LM5G loadability
static guard forbids banned imports/calls
```

Suggested path:

```text
mcp_server/tests/test_lm5p_ollama_think_format_spike.py
```

No live Ollama test belongs in CI.

Static guard should verify the script does not import or call:

```text
requests
httpx
ollama
litellm
run_probe
run_candidate
_default_transport_factory
LiteLLMWorkerTransport
run_local_worker_adapter
run_local_worker_turn
evaluate_local_worker_scenario_result
```

Manual runbook:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5p_ollama_think_format_spike.py
```

Before running, confirm:

```powershell
ollama --version
ollama list
ollama show gemma4:12b-it-qat
```

`ollama show gemma4:12b` is optional challenger preflight only. A hang or
instability in that model does not block the canonical LM5P read.

Do not update the curated probe evidence doc until after the spike results are
reviewed.
