# LM5M Local Worker Prompt Text v2 Design

## Purpose

LM5M introduces `lm5m.prompt_text:v2` as a narrow prompt-artifact text
revision for the local worker model adapter.

The slice changes only the durable generic instruction text used by
`render_local_worker_prompt_artifact(...)`, plus the prompt text version
constant. It is the next controlled variable after LM5L fixed the LM5K golden
probe fixture and the round-2 evidence showed that the remaining failures are
likely prompt-framing issues rather than graph-state incoherence.

LM5M targets exactly two prompt themes:

1. Generic authoring-role framing for allowed action inputs.
2. Stronger raw JSON-only output discipline.

It does not add evidence push, model-specific branches, parser leniency,
context-payload changes, request-envelope changes, probe-runner changes, or a
live probe inside the implementation PR.

## Background

LM5J introduced the deterministic local-worker prompt artifact and adapter:

- `mcp_server/src/rook/agent/local_worker_prompt_artifact.py`
- `mcp_server/src/rook/agent/local_worker_adapter.py`

LM5K ran the first live model probe. LM5L then fixed the LM5K golden probe
fixture so the scenario is coherent:

- scenario id: `lm5k_golden_repair_v2`
- state: `post_verify_needs_repair`

The round-2 evidence is recorded in:

`docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md`

Round 2 showed:

- `qwen3:14b`: 5/5 strict-loadable, 0/5 spine-passing; all clarification.
- Haiku 4.5: 0/5 strict-loadable; fenced JSON 5/5.
- Sonnet 5: 5/5 strict-loadable, 1/5 spine-passing.

The single Sonnet spine-passing attempt was protocol-valid but semantically
weak. It guessed a repair input shape instead of demonstrating durable repair
quality. This means LM5L removed fixture incoherence as an absolute blocker,
but the next controlled variable should be prompt text rather than additional
worker-visible evidence.

## Production Scope

LM5M production changes are limited to:

`mcp_server/src/rook/agent/local_worker_prompt_artifact.py`

Only these two names may change:

```python
LOCAL_WORKER_PROMPT_TEXT_VERSION
_INSTRUCTION_TEXT
```

The version becomes:

```python
LOCAL_WORKER_PROMPT_TEXT_VERSION = "lm5m.prompt_text:v2"
```

No other production behavior changes in LM5M.

The following functions and behavior must remain unchanged:

- `render_local_worker_prompt_artifact(...)`
- `_require_request_envelope(...)`
- `_require_response_contract(...)`
- `_render_contract_text(...)`
- canonical JSON rendering of the user message
- request-envelope validation
- mechanical response-contract rendering
- adapter transport behavior
- response loading and strict parsing

## Prompt Text Requirements

The v2 instruction text must remain generic. It may strengthen wording, but it
must not become scenario-specific, model-specific, or a duplicated response
schema.

### Authoring Role

The prompt should explain that an allowed action's `input_schema` describes the
shape of the action input object the worker may author from visible context. It
is not a list of hidden values Rook is withholding.

The text should preserve the worker's right to clarify or refuse. The target is:

```text
author an allowed action input when visible context is sufficient;
clarify or refuse when it is not.
```

The prompt must not imply:

```text
always request an action;
always author action input;
invent hidden execution values;
ignore insufficient context.
```

### Raw JSON Discipline

The prompt should explicitly require exactly one raw JSON object and forbid:

- markdown fences
- backticks
- language labels
- explanatory text before the JSON object
- explanatory text after the JSON object

This is intended to test whether Haiku's stable fenced-output behavior can be
reduced by generic instruction text alone. LM5M does not loosen the parser or
accept fenced output.

## Prompt Literal Boundary

LM5J deliberately made `_INSTRUCTION_TEXT` separate from mechanical response
contract rendering. LM5M preserves that boundary.

`_INSTRUCTION_TEXT` may mention only minimal generic protocol concepts:

- `input_schema`
- action input object
- allowed action
- visible context
- clarify
- clarification
- refuse
- refusal
- markdown fences
- backticks
- language labels
- explanatory text

`_INSTRUCTION_TEXT` must not hand-list:

- response-envelope literals such as `action_request`,
  `clarification_request`, or `observation`
- response field-set literals such as `action_id`, `rationale`, `question`,
  `category`, `message`, or `data`
- refusal category literals
- action ids such as `draft_repair_params`
- scenario-specific field names such as `code`, `mode`, or `component_guid`
- scenario node ids such as `repair_same_component`
- repair-code conventions such as `RunScript`

The exact response kinds, field sets, required nullable fields, and refusal
categories continue to come only from `response_contract` via
`_render_contract_text(...)`.

The word `refusal` is allowed only as generic outcome vocabulary. Tests should
not blindly reject that word as a response kind literal; they should still ban
hand-listed response-envelope names, field-set names, refusal category values,
action ids, and scenario-specific literals.

## Anti-Goals

LM5M does not change:

- LM5A context construction
- LM5H context payload rendering
- LM5I request envelope rendering
- LM5G response payload loading
- LM5B admissibility validation
- LM5C disposition
- LM5D harness behavior
- LM5F evaluation records
- LM5K/LM5L probe runner behavior

LM5M does not add:

- evidence push
- current script body snippets
- error excerpts
- pin values
- component GUID values
- hidden execution parameter values
- model-specific prompt branches
- model-specific parsing branches
- parser leniency
- fence stripping
- live probe execution inside the implementation PR
- probe evidence summary updates inside the implementation PR

## Test Scope

Primary tests live in:

`mcp_server/tests/test_local_worker_prompt_artifact.py`

Tests should prove:

- `LOCAL_WORKER_PROMPT_TEXT_VERSION == "lm5m.prompt_text:v2"`
- prompt artifact shape and schemas remain unchanged
- user message remains canonical JSON of the request envelope
- response contract rendering remains mechanical from `response_contract`
- contract mutation still changes rendered system text
- `_INSTRUCTION_TEXT` contains generic authoring-role guidance
- `_INSTRUCTION_TEXT` contains raw JSON / no-fence guidance
- `_INSTRUCTION_TEXT` preserves clarification/refusal as valid outcomes
- `_INSTRUCTION_TEXT` does not contain response kind literals
- `_INSTRUCTION_TEXT` does not contain response field-set literals beyond the
  allowed generic `input_schema` term
- `_INSTRUCTION_TEXT` does not contain refusal category literals
- `_INSTRUCTION_TEXT` does not contain scenario-specific literals

Adapter tests may be updated only if they pin the old prompt text version.
Those updates should compare against `LOCAL_WORKER_PROMPT_TEXT_VERSION` or the
new literal. LM5M must not add adapter behavior assertions or change adapter
production code.

## Verification Scope

Targeted:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_local_worker_prompt_artifact.py -q
```

If adapter tests require a version expectation update:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_local_worker_adapter.py -q
```

Focused local-worker prompt/adapter gate:

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\test_local_worker_prompt_artifact.py `
  tests\test_local_worker_adapter.py `
  -q
```

Python 3.10 compatibility gate:

```powershell
cd C:\UDEV\Rook

py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_prompt_artifact.py `
  mcp_server\tests\test_local_worker_prompt_artifact.py `
  mcp_server\tests\test_local_worker_adapter.py
```

Static checks:

```powershell
cd C:\UDEV\Rook

git diff --check
git diff --name-status main..HEAD
```

Expected production diff:

```text
mcp_server/src/rook/agent/local_worker_prompt_artifact.py
```

Expected test diff:

```text
mcp_server/tests/test_local_worker_prompt_artifact.py
```

Optional test diff if version expectations require it:

```text
mcp_server/tests/test_local_worker_adapter.py
```

No live, model, RookChat, Rhino/GH, stream, or probe-runner gate is part of the
LM5M implementation PR.

## Post-Merge Runbook

After LM5M merges, run the same LM5K probe panel from the repo root:

```powershell
cd C:\UDEV\Rook

.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --capture-raw `
  --local "ollama_chat/qwen3:14b" `
  --cheap "anthropic/claude-haiku-4-5-20251001" `
  --ceiling "anthropic/claude-sonnet-5"
```

Comparison keys:

```text
scenario_id: lm5k_golden_repair_v2
state: post_verify_needs_repair
old prompt_text_version: lm5j.prompt_text:v1
new prompt_text_version: lm5m.prompt_text:v2
```

Compare:

- strict-loadable n/5
- spine-passing m/5
- Haiku fenced-output count
- qwen3 clarification/refusal/action distribution
- Sonnet clarification/refusal/action distribution
- semantic weakness of any spine-passing action input

The post-merge probe should produce evidence, not implementation changes.
Do not write or update the probe evidence summary until after that live run is
complete.
