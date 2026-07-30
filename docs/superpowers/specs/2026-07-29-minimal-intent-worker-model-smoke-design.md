# Minimal Intent-to-Worker Model Smoke Design

**Date:** 2026-07-29

**Status:** Approved design for specification review

**Base:** `2e9faf0dd3df16bb14e7d6c024b09136fef752d0`

## 1. Purpose

PR #514 established this internal product path with deterministic fakes:

```text
exact intent
-> one Planner draft
-> strict existing draft admission
-> deterministic workflow compiler
-> one bounded worker repair
-> typed execution
-> native terminal result
```

This slice adds the smallest operator-only composition needed for a later,
separately authorized model smoke:

```text
exact fixed intent
-> real frontier Planner transport
-> MinimalPlannerDraftAdapter
-> run_minimal_intent_worker_integration()
-> existing real local-worker transport
-> strict operator-only causal fake typed-tool executor
-> native handoff result
```

The smoke tests model-to-model composition and contract compliance. It does not
test Rhino, Grasshopper, or real C# compilation.

## 2. Falsifiable claim

With one existing named model hierarchy and one fixed admitted intent:

- the frontier Planner can return the existing four-field draft in one call;
- deterministic code can compile that draft without model-authored topology;
- the existing local worker can return one admitted repair action in at most
  one call; and
- the native handoff can reach its existing terminal result against a causal
  synthetic typed-tool boundary.

Any profile mismatch, malformed Planner output, worker stop, action rejection,
unexpected tool call, or synthetic-tool contract violation stops without
retry, fallback, repair, or substitution.

## 3. Scope and files

Implementation adds exactly:

```text
scripts/minimal_intent_worker_model_smoke.py
mcp_server/tests/test_minimal_intent_worker_model_smoke.py
```

No product module changes are required. In particular, this slice does not
modify:

- `minimal_intent_worker_integration.py`;
- `minimal_csharp_repair_handoff.py`;
- Planner draft admission;
- workflow compilation or topology;
- worker prompt, response, action, or disposition contracts;
- `LiteLLMWorkerTransport`;
- typed-tool or receipt contracts; or
- Chat, MCP, Chirp, DSPy, or CLI product registration.

The new script is an operator-only smoke entry point, not a product runtime.

## 4. Fixed inputs

### 4.1 Intent

The script owns this exact private constant:

```text
Create a Grasshopper C# component with one A:double output and compile cleanly.
```

It has no command-line or environment override. The existing Planner adapter
still requires the admitted draft's `goal` to equal these exact characters.

### 4.2 Model hierarchy

The script calls:

```python
get_models("hybrid")
```

and refuses before transport construction unless the two exact role identities
are:

```text
Planner: anthropic/claude-opus-4-6
Worker:  ollama_chat/qwen3-coder:30b-a3b-q8_0
```

Both identities are resolved and validated before either transport is
constructed. There are no model overrides, fallback profiles, role
substitutions, or alternate paths.

## 5. Operational guard

The script accepts only these argument states:

```text
no arguments
-> live_execution_not_requested
-> construct neither transport

exactly ["--execute-live"]
-> resolve and validate the fixed hierarchy
-> construct transports
-> run once

anything else
-> invalid_arguments
-> construct neither transport
```

`--execute-live` is only an accidental-contact guard. It does not authenticate
human authorization and does not replace the explicit approval required before
the post-merge smoke.

The operator script must not be launched with the live flag during
specification, planning, implementation, or review. Tests may exercise exactly
this closed three-case matrix by calling `main(["--execute-live"])` in process:

1. profile loading raises before role resolution; transport construction is a
   fail-if-reached sentinel;
2. role resolution returns the exact Planner and an invalid Worker; transport
   construction is a fail-if-reached sentinel; and
3. both roles validate, but `_run_live_once` is replaced with a bounded
   fail-before-construction stub to prove ordinary internal failures are
   summarized without leaking exception text.

The first two cases prove zero transport construction. The third reaches only
the monkeypatched stub, not the real `_run_live_once`, either transport
constructor, or an external capability. No test launches the operator script
with the live flag. These controlled in-process guard exercises are not live
script execution and do not authorize contact.

## 6. Transport construction

After both roles pass exact validation, construct two unchanged
`LiteLLMWorkerTransport` instances.

Planner:

```text
model: anthropic/claude-opus-4-6
profile_api_base: hybrid profile api_base
generation_params:
  temperature: 0
  max_tokens: 1024
  max_retries: 0
  response_format:
    type: json_schema
    json_schema:
      name: minimal_planner_draft
      strict: true
      schema: build_minimal_planner_draft_response_schema()
structured_response_schema: null
timeout_s: 120
```

The Planner schema deliberately travels through LiteLLM's
`response_format` parameter. For the pinned Anthropic model, LiteLLM 1.89.4
maps that supported OpenAI-compatible request shape to Anthropic
`output_format`. It must not travel through the transport's
`structured_response_schema` argument, because that argument materializes as
top-level `format`, which is the existing Ollama path rather than the
Anthropic structured-output path.

Worker:

```text
model: ollama_chat/qwen3-coder:30b-a3b-q8_0
profile_api_base: hybrid profile api_base
generation_params:
  temperature: 0
  max_tokens: 1024
  max_retries: 0
structured_response_schema:
  _local_worker_response_union_schema()
timeout_s: 120
```

The worker schema builder remains private. The operator-only script imports and
calls that exact code-owned helper, following the existing LM5K probe. It does
not copy the schema or promote the helper to a public API.

If either provider cannot honor its schema, the existing transport/adapter path
produces its ordinary stop. There is no prompt-only fallback.

The 1,024-token limits bound generated output before the existing byte-bounded
response loaders run. `max_retries: 0` makes the one-call limit explicit at
the LiteLLM boundary. Neither setting changes semantic admission, response
contracts, or the existing 120-second call timeout.

## 7. Composition flow

The execution branch performs one direct composition:

```text
fixed intent
-> resolve exact hybrid roles
-> build Planner transport and MinimalPlannerDraftAdapter
-> build worker transport
-> build private causal fake executor
-> await run_minimal_intent_worker_integration(...)
-> retain native MinimalIntentWorkerIntegrationResult
-> render bounded operator summary
```

Provider and model construction stays outside the merged product module. The
merged runner remains the sole owner of Planner admission, deterministic
compilation, worker invocation, action application, receipt interpretation,
and native terminal state.

## 8. Causal synthetic typed-tool executor

The fake exists only in the operator script and its tests. It is not exported,
registered, or placed in a production fake registry.

### 8.1 Create call

The first and only admitted initial call is:

```text
tool: gh_create_csharp_script
code: exact private invalid specimen body compiled by the existing handoff
pins_in: empty
pins_out: exactly A:double
name/x/y: exact existing compiled values
```

The fake full-matches the received initial body with a private ASCII grammar
that captures the missing identifier. It constructs the CS0103 diagnostic from
that captured identifier. The complete diagnostic is not independently
hardcoded.

The fake originates one component GUID in its create receipt and retains that
issued value internally for the update check. No Planner, worker, compiler, or
operator summary field supplies the GUID.

### 8.2 Update body admission

The update body must be an exact built-in `str`, ASCII, and at most 128 UTF-8
bytes. One private code-owned compiled regular expression uses `fullmatch`:

```regex
[ \t]*A[ \t]*=[ \t]*-?(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,16})?[dD]?[ \t]*;[ \t]*
```

This deliberately narrow subset admits a bounded integer or ordinary decimal
double assignment to `A` without prescribing a specific constant. The
nine-digit integral ceiling stays within C# `int` literal range, and the
optional `d`/`D` suffix remains assignable to `double`. It rejects decimal and
float suffixes (`m`/`M`, `f`/`F`), exponents, oversized integral literals,
multiline bodies, identifiers, expressions, calls, additional statements,
non-ASCII text, and oversized text.

This grammar is synthetic smoke admission only. Passing it is not evidence of
C# compilation.

### 8.3 Update call

The second call, when reached, must be exactly:

```text
tool: gh_update_script
guid: exact GUID issued by the create receipt
code: exact worker-authored body admitted above
mode: body
language: csharp
```

Only after these checks does the fake return a clean synthetic update receipt.
Every unexpected tool, order, parameter, pin, body, GUID, or third call fails
closed.

The executor owns one private boolean, initialized as:

```text
contract_failed = false
```

Immediately before raising for any synthetic contract rejection, it sets that
boolean to `true`. It retains no rejected body, parameter value, diagnostic, or
detailed violation. This flag exists only because the existing live-dispatch
seam correctly converts executor exceptions into the native
`dispatch_failed` result.

## 9. Call-count authority

LiteLLM telemetry is observational and never establishes execution counts. No
counting transport wrapper is introduced.

Counts derive only from control flow and existing native records:

```text
pre-contact refusal
-> planner_calls = 0
-> worker_calls = 0

returned MinimalIntentWorkerIntegrationResult
-> planner_calls = 1

handoff_result is absent
or handoff_result.adapter_record is absent
-> worker_calls = 0

handoff_result.adapter_record is present
-> worker_calls = 1
```

The fake executor owns its own bounded `tool_calls` list, so its count is the
number of exact calls it directly received.

If an unexpected internal exception prevents a native result from returning,
the summary reports call counts as `null` rather than inventing certainty.

## 10. Bounded operator summary

The script writes one compact JSON object containing only:

```text
operator_status
operator_reason
intent
profile
planner_model
worker_model
planner_calls
worker_calls
tool_calls
terminal_stage
terminal_reason
planner_adapter_status
worker_adapter_status
```

Fields that do not exist at the reached stage are `null`. A resolved model
identity must be an exact built-in `str`, ASCII, nonblank, and at most 256
UTF-8 bytes before it may enter the summary or transport construction.
Otherwise the script refuses with no transport construction.

The operator vocabulary is closed:

| `operator_status` | `operator_reason` |
|---|---|
| `refused` | `live_execution_not_requested`, `invalid_arguments`, `profile_identity_invalid`, or `profile_role_mismatch` |
| `completed` | `native_terminal` |
| `failed` | `native_stop`, `synthetic_tool_contract_failure`, or `operator_internal_error` |

`completed / native_terminal` requires the existing native terminal stage and
reason. Ordinary returned Planner, draft, worker, action, or receipt stops use
`failed / native_stop` while retaining their native terminal fields. After a
native result returns, `contract_failed == true` takes precedence and yields
`failed / synthetic_tool_contract_failure`; otherwise the ordinary native-stop
classification applies. An unexpected exception that prevents a native result
uses `failed / operator_internal_error` with all unprovable call counts `null`.

The summary never includes:

- raw prompts or responses;
- worker code or rationale;
- diagnostics or component GUIDs;
- credentials;
- provider-returned metadata;
- LiteLLM telemetry; or
- tool parameters or receipts.

The output is an ordinary ephemeral operator result. It is not an archive,
checkpoint, readiness record, attempt record, or scientific evidence object.

## 11. Stops and exit behavior

Expected states remain ordinary and one-shot:

| Boundary | Result |
|---|---|
| no live flag | `live_execution_not_requested`, zero contacts |
| invalid arguments | `invalid_arguments`, zero contacts |
| invalid or mismatched profile roles | pre-contact profile refusal |
| Planner transport/response failure | existing Planner adapter stop |
| draft admission or goal mismatch | existing draft stop |
| worker transport/response failure | existing native handoff stop |
| worker refusal/clarification/action rejection | existing native handoff stop |
| fake tool contract violation | native `dispatch_failed`, summarized as `synthetic_tool_contract_failure`; no further call |
| clean native terminal state | completed smoke summary |

No state triggers retry, fallback, prompt repair, deterministic draft patching,
model substitution, worker substitution, or real tool dispatch.

## 12. Deterministic verification

The test module uses no provider, worker box, Rhino, or Grasshopper.

### 12.1 Contact guards

Prove:

- no arguments and every unknown/additional argument classify as pre-contact
  refusal;
- neither transport is constructed for those refusals;
- Planner mismatch, worker mismatch, malformed role identity, or wrong profile
  result constructs neither transport; and
- argument tests never invoke the live execution branch.

### 12.2 Exact transport configuration

Monkeypatch transport construction and call the internal one-run composition
directly. Prove both constructors receive the exact role, profile API base,
temperature, 1,024-token output limit, zero-retry setting, timeout, and
independently rebuilt code-owned schema.

In a separate offline materialization test, use the actual
`LiteLLMWorkerTransport` and replace only `litellm.completion` with a capturing
callable. Prove the exact kwargs at that boundary:

- Planner contains the code-owned `response_format`, `max_tokens: 1024`, and
  `max_retries: 0`, with no `format` key; and
- Worker contains the code-owned `format`, `max_tokens: 1024`, and
  `max_retries: 0`, with no `response_format` key or duplicate schema.

The transport doubles then pass raw strings through the real
`MinimalPlannerDraftAdapter`, real local-worker adapter, and merged integration
runner.

### 12.3 Vertical witness

One deterministic vertical proves:

```text
fixed intent
-> one fake-backed Planner transport call
-> real strict Planner adapter and draft loader
-> merged deterministic compiler and handoff
-> one fake-backed worker transport call
-> real worker adapter/action path
-> causal synthetic typed-tool create/update
-> native terminal result
-> bounded summary
```

Assert the native result owns the terminal stage and reason, the create receipt
originates the GUID, the update uses it, and the update body equals the worker
action's admitted body.

### 12.4 Adversarial fake coverage

Directly reject:

- wrong tool name or call order;
- extra calls;
- wrong fixture body, name, position, or pins;
- initial body that cannot yield one missing identifier;
- wrong update GUID, mode, or language;
- non-string, non-ASCII, multiline, oversized, expression, multi-statement, or
  identifier-valued update bodies; and
- a second create or update.

Add exact-limit and limit-plus-one body tests and representative accepted
numeric assignments. Explicitly refuse `A = 1m;`, an integral literal longer
than nine digits, exponent notation, expressions, and multiple statements.
Every contract-refusal case must prove `contract_failed` becomes true without
retaining the rejected value.

### 12.5 Surface audit

Prove the operator script introduces no import or construction of:

- `ToolDispatcher` or the real typed-tool bridge;
- Chat, MCP, Chirp, or DSPy;
- an archive, readiness, preflight, attempt, checksum, or fingerprint system;
- a production fake registry; or
- changes to the merged product modules.

The existing 573-test seam remains the focused regression baseline.

## 13. Live execution boundary

Specification, planning, implementation, and review perform no external
contact and do not launch the operator script with `--execute-live`. The only
in-process uses of the flag are the closed three-case guard matrix in Section
5; none reaches the real live composition path.

After implementation review and merge, a separate explicit authorization may
permit exactly one command with that flag. That operation may make:

```text
Planner calls: exactly 1
Worker calls: 0 or 1
Rhino/Grasshopper calls: 0
```

Before that authorization is exercised, the operator must identify the exact
Python interpreter that will run the command, record its installed LiteLLM
distribution version, and rerun the offline Planner/Worker materialization
test with that same interpreter. That test must also require LiteLLM to report
`supports_response_schema(model="anthropic/claude-opus-4-6") is True` and to
include `response_format` among the model's supported parameters. The shared
test venv reported LiteLLM 1.89.4 during design while `mcp_server/uv.lock`
resolved 1.92.0; neither version may stand in for the actual execution runtime.
A missing or failing same-runtime capability or materialization check stops
before the smoke.

The authorized smoke stops after its first result, whether completed or failed.
No second attempt is implied.

## 14. Deliberate non-claims

This slice does not prove:

- real C# compilation;
- Rhino or Grasshopper behavior;
- arbitrary user intents, interfaces, or capabilities;
- a general Planner/worker runtime;
- production operator registration;
- transport readiness or credential validity before contact;
- retry or fallback behavior;
- provider identity beyond the requested model configuration; or
- durable or scientific evidence.

It adds one narrow, operator-only splice for the already-defined first
post-merge engineering smoke.

## 15. Delivery boundary

This specification authorizes no implementation and no live execution.

After independent specification review:

1. use `superpowers:writing-plans` to create an implementation plan;
2. stop for plan review;
3. implement and review with deterministic no-contact tests only;
4. merge separately; and
5. request separate authorization before invoking `--execute-live`.
