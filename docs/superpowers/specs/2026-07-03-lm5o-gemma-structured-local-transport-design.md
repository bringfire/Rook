# LM5O Gemma Structured Local Transport Design

**Date:** 2026-07-03

**Campaign:** Rook local/internal models north-star, LM5 worker transport boundary

**Status:** design approved for planning

## 1. Purpose

LM5O tests whether Ollama structured output can make Gemma enter the strict LM5
worker response spine without changing the worker's decision authority.

The governing sentence:

```text
LM5O constrains response envelope validity while preserving worker disposition
freedom.
```

The slice must not force Gemma to emit `action_request`. It must constrain only
the response envelope so Gemma can emit any valid LM5B response union member:

```text
action_request | clarification_request | refusal | observation
```

The empirical question is:

```text
Can Ollama structured output make Gemma strict-loadable while preserving the
paired LM5N behavior:
  evidence_absent -> restraint
  evidence_present -> action
and preserving semantic repair quality for manual review?
```

## 2. Context

LM5N showed that bounded evidence-push moved qwen3 and Sonnet from restraint to
action while preserving action authority. Gemma showed similar action intent in
the evidence-present run, but failed strict response-envelope discipline:

```text
response_payload_invalid=10/10
```

The observed Gemma failures were malformed LM5G response envelopes, especially a
missing `schema` field or a `schema` object where LM5G requires the literal
string:

```text
rook.local_worker_turn_response:v1
```

LM5O therefore targets transport shape, not prompt text, parser leniency,
evidence content, action authorization, or semantic repair execution.

## 3. High-Level Shape

LM5O has two phases inside one slice:

```text
Phase A: feasibility spike
Phase B: opt-in structured local transport mode
```

Phase B is conditional. It must not begin unless Phase A proves that the actual
provider path can carry the full LM5 response-union schema:

```text
LiteLLM -> Ollama -> Gemma
```

A failing spike is a successful LM5O outcome if it produces clear evidence.

## 4. Phase A: Feasibility Spike

Add one committed spike script:

```text
scripts/lm5o_structured_output_spike.py
```

Phase A scope:

```text
add spike script only
no production module changes
no probe runner changes
no prompt changes
no evidence packet changes
no parser changes
no committed raw outputs
```

The spike script builds the full LM5B response-union JSON Schema locally and
calls Gemma through the same LiteLLM/Ollama style intended for the transport:

```python
litellm.completion(..., format=<full_union_schema>)
```

The spike runs two minimal prompts:

- evidence-absent-like: should allow clarification or refusal;
- evidence-present-like: should allow action.

The prompts may be minimal, but they must not force a single response kind. The
point is to prove the provider can constrain envelope shape while preserving
choice.

The script prints compact status for each prompt:

```text
provider call succeeded
raw content received
JSON parsed
LM5G loaded
loaded response kind
```

It exits nonzero on:

```text
provider error
missing/non-text content
invalid JSON
LM5G loader failure
output forced into only one kind unexpectedly
```

Raw outputs remain local. If Phase A evidence is later worth preserving, create a
separate curated evidence summary. Do not commit raw spike artifacts as part of
LM5O.

## 5. Phase A Schema Requirements

The spike schema must be the full LM5 response union, not action-only.

Root:

```text
oneOf with exactly four object variants
```

Every variant has:

```text
"schema": {"const": "rook.local_worker_turn_response:v1"}
"kind": {"const": <variant kind>}
exact required field set
additionalProperties: false
```

Variant fields:

```text
action_request:
  schema, kind, action_id, rationale, input
  input is object

clarification_request:
  schema, kind, question, rationale
  rationale is required and nullable

refusal:
  schema, kind, category, reason
  category enum mirrors LM5B refusal categories

observation:
  schema, kind, message, data
  data is required and object|null
```

The schema privately encodes the LM5G v1 envelope contract. Do not widen LM5G
exports just to derive it mechanically.

## 6. Phase A Stop Conditions

If Phase A fails, LM5O stops after recording local/manual evidence.

Do not:

```text
implement structured mode
weaken the schema in-place
fall back to action-only
loosen LM5G
change prompt text
change evidence packets
add parser leniency
add model-specific rescue behavior
```

If `oneOf + const` fails, the next decision is a new design question, such as:

```text
supported provider-compatible union representation
direct Ollama client
assistant prefill
provider-specific tool call
```

## 7. Phase B: Opt-In Structured Local Transport Mode

Phase B may execute only after Phase A passes.

Add a private schema builder near the LiteLLM transport:

```text
mcp_server/src/rook/agent/local_worker_model_transport.py
```

Private helper:

```python
def _local_worker_response_union_schema() -> dict[str, Any]:
    ...
```

The helper is:

```text
private
unexported
default-off
fresh-copy safe
not a public response-schema API
```

It privately encodes the LM5G v1 envelope contract and tests pin it against
LM5G loader behavior.

`LiteLLMWorkerTransport` gains a top-level transport option:

```python
LiteLLMWorkerTransport(
    model: str,
    profile_api_base: str | None = None,
    generation_params: Mapping[str, Any] | None = None,
    structured_response_schema: Mapping[str, Any] | None = None,
    timeout_s: float = 120.0,
)
```

Send-time behavior:

```python
kwargs = {
    "model": self.model,
    "messages": ...,
    "timeout": self.timeout_s,
}
kwargs.update(self.generation_params)

if self.structured_response_schema is not None:
    kwargs["format"] = <fresh JSON-shaped copy of schema>
```

The split is:

```text
generation_params = sampling behavior
structured_response_schema / format = transport contract
transport_mode = experiment identity
```

Rules:

- `structured_response_schema=None` by default.
- Free-text mode sends no `format`.
- Structured mode sends `format` only when the probe runner selects local
  structured mode.
- Reject `generation_params` containing `format` when
  `structured_response_schema` is set.
- Validate/copy the structured schema as JSON-shaped data.
- Copy the schema per call so provider/client mutation cannot leak across
  attempts.
- Provider rejection is not caught specially; the existing adapter records it as
  transport error.

Because the constructor is production-visible, document this as supported but
experimental/provider-scoped in LM5O. The probe runner is the only intended
caller for now.

## 8. Probe Runner Activation

Structured mode is a probe-controlled local/Ollama experiment, not a general
provider abstraction.

Add a runner option:

```text
--local-transport-mode free_text|structured
```

Rules:

- Default is `free_text`.
- The option applies only to the local slot.
- `structured` is allowed only for Ollama-shaped local models:
  - `ollama_chat/...`
  - `ollama/...`
- `structured` with a skipped or unavailable local slot fails clearly.
- `structured` with a non-Ollama local model fails clearly.
- Cheap and ceiling slots always use `free_text` in LM5O.

Manifest and attempt records must include:

```text
transport_mode
```

Comparison keys include `transport_mode`.

## 9. Testing

No live provider tests run in the implementation PR.

Transport unit tests in:

```text
mcp_server/tests/test_local_worker_model_transport.py
```

Required coverage:

- Free-text call does not pass `format`.
- Structured call passes `format`.
- `format` contains the full four-kind union, not action-only.
- `schema.const == LOCAL_WORKER_TURN_RESPONSE_SCHEMA`.
- Captured schema mutation after call 1 does not affect call 2.
- `generation_params={"format": ...}` plus `structured_response_schema` raises
  at construction.
- Non-mapping or non-JSON-shaped schema raises.
- Provider content return path is unchanged.

Probe runner tests in:

```text
mcp_server/tests/test_lm5k_worker_probe.py
```

Required coverage:

- `--local-transport-mode` defaults to `free_text`.
- `structured` is accepted only for local Ollama-shaped models.
- Structured with skipped/unavailable/non-Ollama local slot fails clearly.
- Cheap and ceiling always record `transport_mode="free_text"`.
- Manifest panel records `transport_mode`.
- Attempt rows record `transport_mode`.
- Factory passes schema only for local structured mode.

The spike script may have static tests if useful, but its live provider run is a
manual evidence step, not CI.

## 10. Post-Merge Runbook

After Phase B merges, run the local-only canonical LM5O evidence set.

Use the exact local Gemma model name reported by:

```powershell
ollama list
```

Canonical commands use `--skip cheap --skip ceiling`.

Run four commands:

```text
Gemma free_text evidence_absent
Gemma free_text evidence_present
Gemma structured evidence_absent
Gemma structured evidence_present
```

Expected interpretation:

- `free_text` remains mostly or fully `response_payload_invalid`: confirms the
  LM5N Gemma baseline.
- `structured absent` becomes strict-loadable restraint: good.
- `structured present` becomes strict-loadable `candidate_action_request`: good.
- `structured absent` forced action: bad; structured output harmed judgment or
  interacted poorly with prompt/context.
- `structured present` loads but has poor repair code: transport solved,
  semantic evidence remains separate.
- Provider rejects `format`: transport feasibility failed; stop.

The LM5O evidence summary must state:

```text
LM5O is not a new model-quality ranking.
It is a transport-mode comparison for one local model.
```

## 11. Anti-Goals

LM5O does not change:

```text
LM5G response loader strictness
LM5J prompt text
LM5I request envelope
LM5N evidence packets
LM5F evaluation semantics
action authorization
graph mutation
stream execution
tool dispatch
semantic repair scoring
```

LM5O does not add:

```text
action-only schema
parser leniency
markdown fence unwrapping
Haiku/Anthropic structured mode
OpenAI structured-output mode
model-specific branches outside local/Ollama probe validation
provider ranking
raw-output artifact commits
```

## 12. Verification Scope

Targeted:

```text
mcp_server/tests/test_local_worker_model_transport.py
mcp_server/tests/test_lm5k_worker_probe.py
```

Nearby:

```text
mcp_server/tests/test_local_worker_adapter.py
mcp_server/tests/test_local_worker_turn_response_loader.py
mcp_server/tests/test_local_worker_turn_request.py
```

Focused:

```text
mcp_server/tests/test_plan_graph*.py
mcp_server/tests/test_local_worker*.py
mcp_server/tests/test_lm5k_worker_probe.py
```

Static:

```text
git diff --check
production diff limited to local_worker_model_transport.py if Phase B runs
probe runner diff limited to scripts/lm5k_worker_probe.py if Phase B runs
spike script diff limited to scripts/lm5o_structured_output_spike.py in Phase A
no prompt artifact diff
no LM5G loader diff
no evidence packet/schema diff
no raw probe artifact tracking
```

Live:

```text
Phase A manual spike only
Phase B post-merge runbook only
```

No live provider call is required for the implementation PR test gate.
