# Minimal Intent-to-Worker Product Integration Design

- **Date:** 2026-07-29
- **Status:** Approved design captured for independent specification review; implementation planning has not begun
- **Base:** `origin/main` at `f0acdbdb7a9b15adcdb970183e75dd27fedd78c7`
- **Branch:** `codex/minimal-intent-worker-integration-design`
- **Scope:** One internal product composition from exact user intent through one Planner draft call into the existing minimal C# repair handoff
- **Authorization:** Specification work only. No provider, Planner, worker-box, Rhino, Grasshopper, MCP, CLI, or product execution is authorized

## 1. Purpose

Rook now has a merged, deterministic product seam that proves:

```text
ValidatedPlannerDraft
-> deterministic workflow compilation
-> create and verify
-> one bounded worker repair
-> typed tool execution
-> clean compile receipt
```

The public internal entry point is:

```python
run_minimal_csharp_repair_handoff(
    draft: ValidatedPlannerDraft,
    *,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> MinimalCSharpRepairHandoffResult
```

Planner invocation intentionally remains outside that function. The smallest
missing product boundary is therefore:

```text
exact user intent
-> one-shot Planner draft adapter
-> strict existing draft loader
-> existing minimal C# repair handoff
```

This slice adds only that boundary. It allows a richer Planner to produce a
very small semantic draft and delegates all workflow authorship, worker action
application, typed execution, and terminal truth to the already-proven
product components.

## 2. Falsifiable hypothesis

> An exact bounded user-intent string can pass through one structured Planner
> call, strict four-field draft admission, deterministic workflow compilation,
> one bounded worker repair, and existing typed tool execution to a native
> terminal result without allowing either model to author or alter workflow
> topology or silently replace the user's intent.

The hypothesis is falsified for this slice if the vertical requires any of:

- a Planner retry, fallback, prompt repair, or deterministic draft patch;
- a new workflow template, worker action, receipt type, or tool route;
- Planner- or worker-authored topology;
- inferred or normalized replacement of the original intent;
- Chat, DSPy, Chirp, MCP, CLI, archive, readiness, or attempt machinery; or
- duplicated validation of the existing handoff's internal lineage.

## 3. Read-only audit

### 3.1 Existing one-call provider transport

`LiteLLMWorkerTransport` already performs one synchronous structured
`litellm.completion()` call from an injected prompt artifact. It supports:

- externally selected model and provider profile;
- externally supplied generation parameters;
- an injected structured-response schema;
- one `send(prompt_artifact)` call returning exact text; and
- best-effort transport metadata.

It is reused only through structural one-call protocol conformance. This slice
does not use its worker prompt renderer, worker response contract, or worker
adapter for Planner semantics. It does not rename, refactor, subclass, or
generalize `LiteLLMWorkerTransport`.

### 3.2 Existing worker boundary

`LocalWorkerTransport`, `run_local_worker_adapter()`, the one-shot worker
harness, response disposition, and `apply_worker_action_to_node()` already
provide the required bounded worker path. The existing minimal handoff owns
their composition and remains unchanged.

### 3.3 Existing typed tool boundary

`ToolDispatcher.dispatch()` is the normal async Rook tool bridge.
`run_minimal_csharp_repair_handoff()` already accepts an injected sync-or-async
typed tool executor and routes it through the existing PlanGraph execution
seam. The new intent runner forwards that executor unchanged.

### 3.4 Chat, Chirp, and DSPy

These systems demonstrate useful rich-input/small-output interaction shapes,
but none is the runtime foundation for this slice:

- Chat owns streaming, multiple rounds, and tool loops.
- Chirp owns a live sidecar/component-creation boundary.
- DSPy introduces global model configuration, caching, and a broader
  declarative runtime.
- The broad historical Planner owns autonomous tools, retries, and multi-turn
  planning.

They remain design references only.

### 3.5 Existing handoff contract

`load_minimal_csharp_repair_draft()` remains the sole semantic admission path.
It accepts exactly:

```yaml
goal: string
capability: grasshopper_csharp_component
interface:
  inputs: []
  outputs:
    - name: A
      type: double
acceptance: clean_compile_receipt
```

`run_minimal_csharp_repair_handoff()` remains the sole owner of deterministic
contract construction, graph compilation, create/verify, worker repair,
action application, reverify, native records, and terminal truth.

## 4. Considered approaches

### 4.1 Approach 1: Planner-specific adapter plus thin runner — selected

Add one Planner-specific one-call adapter and one internal async composition
function. The adapter uses an injected structural transport; the composition
function feeds its decoded object through the existing strict draft loader and
then invokes the existing handoff unchanged.

This directly implements the missing boundary with no shared-transport
refactor.

### 4.2 Approach 2: generic structured LiteLLM transport — rejected

Extracting or renaming a role-neutral transport could improve naming, but it
would broaden this slice into shared provider refactoring and compatibility
work. Structural conformance is sufficient for the current need.

### 4.3 Approach 3: DSPy Planner module — rejected

A DSPy signature could express the four fields, but its global configuration,
caching, and runtime behavior complicate the exact one-call boundary. It adds
no value to this first composition.

## 5. Product surface

The implementation belongs in exactly one new focused module under
`mcp_server/src/rook/agent`:

```text
minimal_intent_worker_integration.py
```

It owns only:

- bounded exact intent validation;
- the Planner prompt artifact and response schema;
- one Planner transport call;
- strict JSON-object decoding;
- the typed Planner adapter record;
- semantic handoff to the existing strict draft loader;
- exact goal-authority comparison;
- delegation to the existing minimal handoff; and
- one thin ephemeral aggregate result.

It owns no provider/model construction, model selection, generation policy,
worker semantics, workflow compilation, graph mutation, tool routing, receipt
interpretation, persistence, or registration.

The module defines one narrow structural seam:

```python
class MinimalPlannerTransport(Protocol):
    def send(self, prompt_artifact: Mapping[str, Any]) -> str: ...
```

The concrete `MinimalPlannerDraftAdapter` owns prompt rendering, request
materialization, the one transport invocation, raw response capture, strict
decoding, and typed record construction over an injected
`MinimalPlannerTransport`. The integration runner accepts only that exact
concrete adapter type. Adapter subclasses, substitute producer callables, and
caller-authored adapter records are not runner inputs.

`LiteLLMWorkerTransport` satisfies only `MinimalPlannerTransport`
structurally.

## 6. Intent boundary

The internal runner accepts one user-intent value. Before prompt rendering or
invoking any Planner, worker, or tool capability, it requires:

```text
type(intent) is str
intent.strip() is nonempty
len(intent.encode("utf-8")) <= 16_384
```

An unencodable string, non-string value, blank string, or oversized UTF-8
representation raises at the caller contract boundary. The accepted string is
retained exactly. It is never trimmed, normalized, rewritten, or reparsed as
another authority representation.

## 7. Planner prompt and transport boundary

### 7.1 Planner-visible content

The Planner request contains only:

- the exact immutable user intent;
- the closed four-field output shape;
- allowed vocabulary and field meanings; and
- an instruction to return one JSON object.

It contains no examples and no downstream:

- private fixture body;
- compiler or template details;
- graph nodes, edges, rules, or execution parameters;
- worker requirement, response, action, or repair guidance;
- diagnostic or receipt data;
- component GUID;
- expected repair code; or
- Rhino/Grasshopper state.

### 7.2 Prompt snapshot

The adapter constructs one immutable, canonically ordered prompt snapshot from
the accepted intent and code-owned static instructions. The adapter record
retains that immutable snapshot.

Immediately before `transport.send()`, the adapter materializes a fresh mutable
request mapping from the snapshot. Neither the transport nor a caller receives
the retained snapshot object itself. The materialized mapping must represent
the snapshot exactly; mutation of that disposable mapping cannot alter the
recorded prompt.

This is ordinary in-process ownership, not durable evidence, a fingerprint
protocol, or an archive contract.

### 7.3 Planner response schema

The module owns one closed Planner-specific response schema matching the
four-field payload. Provider construction remains outside the adapter. A
caller that uses `LiteLLMWorkerTransport` configures it with this Planner
schema.

The transport schema guides provider output but grants no semantic admission.
Every decoded object still passes through
`load_minimal_csharp_repair_draft()`.

### 7.4 Call cardinality

The adapter calls `transport.send()` exactly once. It catches ordinary
`Exception` subclasses from that call and never catches `BaseException`.
There is no retry, fallback transport, alternate model, prompt rewrite, or
second response request.

Provider, model, credential, route, generation-parameter, and timeout
construction remain outside the adapter and runner.

## 8. Strict JSON-object decoding

The raw transport return must satisfy, before parsing or retention:

```text
type(raw_response) is str
len(raw_response.encode("utf-8")) <= 65_536
```

An unencodable, non-string, or oversized response becomes a typed
`response_invalid` adapter result. Oversized or non-string output is not
retained as raw response material.

For an admitted bounded string, decoding:

- parses the entire string exactly once;
- rejects duplicate object keys at every nesting level;
- rejects `NaN`, positive infinity, and negative infinity;
- rejects trailing non-whitespace content;
- rejects a non-object root;
- performs no markdown-fence extraction;
- performs no substring search for embedded JSON;
- performs no coercion, normalization, default insertion, or repair; and
- retains the exact bounded raw string.

JSON decoding establishes only that the response is one JSON object. It does
not establish that the object is an admissible Planner draft.

## 9. Planner adapter record

The adapter returns one frozen ephemeral record with:

```text
prompt_snapshot
status
raw_response | None
decoded_object | None
failure_reason | None
transport_error_type | None
```

The closed states are:

### 9.1 `decoded`

```text
prompt_snapshot: exact immutable snapshot
raw_response: exact bounded built-in string
decoded_object: decoded JSON object
failure_reason: None
transport_error_type: None
```

### 9.2 `transport_failed`

```text
prompt_snapshot: exact immutable snapshot
raw_response: None
decoded_object: None
failure_reason: transport_failed
transport_error_type: exact ordinary exception class name
```

### 9.3 `response_invalid`

```text
prompt_snapshot: exact immutable snapshot
raw_response: exact bounded string when safely available, otherwise None
decoded_object: None
failure_reason: one closed decoder refusal reason
transport_error_type: None
```

The closed decoder refusal reasons are:

```text
response_not_string
response_not_utf8
response_too_large
response_invalid_json
response_duplicate_key
response_nonfinite_number
response_trailing_content
response_not_object
```

The record validator enforces the state equations. Raw mappings cannot be
substituted for a typed adapter record at the integration boundary.

## 10. Semantic draft admission and intent authority

Only a `decoded` record can advance. Its decoded object is passed without
mutation to:

```python
load_minimal_csharp_repair_draft(decoded_object)
```

No other loader, patcher, default provider, or semantic validator is added.

If the existing loader rejects, the integration stops with:

```text
terminal_stage: draft_admission
terminal_reason: draft_payload_rejected
```

After the loader succeeds, the runner requires:

```text
validated_draft.goal == exact accepted user intent
```

Equality is byte-for-byte equality of the exact Python strings' UTF-8
encodings. The runner does not trim or normalize either side. A mismatch stops
with:

```text
terminal_stage: draft_admission
terminal_reason: goal_mismatch
```

The Planner therefore cannot silently paraphrase or replace the user's
authority in this first specimen.

## 11. Thin async composition

The internal async function has this ownership shape:

```python
async def run_minimal_intent_worker_integration(
    intent: str,
    *,
    planner_adapter: MinimalPlannerDraftAdapter,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> MinimalIntentWorkerIntegrationResult:
    ...
```

It accepts:

```text
exact user intent
exact concrete MinimalPlannerDraftAdapter
existing LocalWorkerTransport
existing typed tool executor
```

Its fixed sequence is:

```text
validate exact intent
-> require exact concrete Planner adapter type
-> call Planner adapter exactly once
-> stop on typed adapter failure
-> strict existing draft admission
-> exact goal-authority comparison
-> run_minimal_csharp_repair_handoff(
       validated_draft,
       worker_transport=worker_transport,
       tool_executor=tool_executor,
   )
-> return thin aggregate
```

The runner knows nothing about prompts beyond invoking the adapter, provider
identity, model selection, retries, worker request rendering, compiler
topology, actions, or receipts.

Invalid caller capabilities or impossible internal state raise. Expected
Planner, draft-admission, and existing handoff stops return ordinary typed
results.

The existing handoff may issue zero or one worker call. The new runner neither
wraps nor retries that call.

## 12. Ephemeral integration result

The frozen result contains exactly:

```text
intent: str
planner_adapter_record: MinimalPlannerDraftAdapterRecord
validated_draft: ValidatedPlannerDraft | None
handoff_result: MinimalCSharpRepairHandoffResult | None
terminal_stage: str
terminal_reason: str
```

It validates only these ownership equations.

### 12.1 Planner-adapter stop

```text
planner_adapter_record.status != decoded
validated_draft is None
handoff_result is None
terminal_stage == planner_adapter
terminal_reason == planner_adapter_record.failure_reason
```

### 12.2 Draft-admission stop

```text
planner_adapter_record.status == decoded
validated_draft is None
handoff_result is None
terminal_stage == draft_admission
terminal_reason in {draft_payload_rejected, goal_mismatch}
```

### 12.3 Handoff reached

```text
planner_adapter_record.status == decoded
validated_draft is present
handoff_result is present
validated_draft == handoff_result.draft
terminal_stage == handoff_result.terminal_stage
terminal_reason == handoff_result.terminal_reason
```

There is no returned state containing a validated draft without a handoff
result. If handoff invocation raises because of an internal contract breach,
the integration runner also raises.

The aggregate does not replay, reconstruct, or duplicate the handoff's native
lineage validation. `MinimalCSharpRepairHandoffResult` remains authoritative
for its own graph, worker, action, tool, record, and receipt relationships.

The aggregate is an ephemeral in-process convenience result. It is not a
durable record, immutable evidence artifact, authorization, receipt, or
readiness claim.

## 13. Deterministic test strategy

### 13.1 Main vertical witness

The main test traverses:

```text
exact user intent
-> fake one-call Planner transport
-> real Planner prompt renderer and adapter
-> real strict JSON-object decoding
-> real load_minimal_csharp_repair_draft()
-> real run_minimal_csharp_repair_handoff()
-> fake worker transport through the real worker adapter
-> fake typed tool executor with causally derived receipts
-> existing native terminal result
-> thin integration result
```

The fake Planner transport inspects the exact materialized prompt and returns
one exact JSON string. The fake worker transport inspects the real serialized
worker prompt before returning a response accepted by the existing worker
adapter. The fake typed executor derives every response from the actual tool
name, parameters, call order, pin declaration, code, and receipt-derived GUID.

The successful witness proves:

- exactly one Planner call;
- exactly one worker call;
- exact original intent in the prompt and validated draft;
- exact Planner prompt/raw-response retention;
- existing strict draft admission;
- unchanged deterministic compilation and workflow topology;
- worker repair code remains the sole repair-code source;
- component identity remains create-receipt-derived;
- unchanged native handoff terminal behavior; and
- aggregate stage/reason equality with the native handoff result.

### 13.2 Intent and Planner refusals

Tests cover:

- non-string, equality-spoof, blank, unencodable, and oversized intent;
- Planner adapter subclass and substitute producer object;
- Planner transport exception;
- non-string and unencodable transport output;
- response at the 65,536-byte boundary and one byte above it;
- empty or malformed JSON;
- duplicate keys at root and nested levels;
- `NaN` and infinities;
- trailing content;
- array, scalar, and null roots;
- markdown-wrapped or embedded JSON;
- missing, extra, malformed, and equality-spoof draft fields; and
- an otherwise valid draft with any goal difference, including whitespace.

Every pre-handoff refusal proves zero worker and typed-tool calls. Oversized
intent, adapter subclass, and substitute producer refusal prove zero Planner
calls as well. Planner transport behavior is tested only by injecting fake
transports through the real concrete adapter.

### 13.3 Prompt information boundary

Structural tests recursively inspect the immutable prompt snapshot and the
fresh materialized request. They require exact equality between them and prove
absence of:

- the private initial C# body;
- expected worker repair code;
- compiler, template, topology, action, and graph-rule material;
- component GUIDs;
- diagnostics and receipts; and
- worker request/response fields.

No examples are present. Mutating the disposable transport request cannot
alter the retained snapshot.

### 13.4 Adapter-record states

Tests construct each legitimate record state and reject every cross-state
combination, including:

- decoded without raw response or object;
- decoded with a failure reason;
- transport failure with raw response or decoded object;
- response invalid with a decoded object;
- oversized response retained in the record; and
- a caller-authored mapping substituted for the typed record.

### 13.5 Existing handoff stops

Focused integration tests project representative existing stops through the
new aggregate without renaming their native stage or reason:

- create or verify-create stop before worker dispatch;
- worker transport failure;
- worker refusal or clarification;
- malformed worker response;
- worker action rejection;
- repair failure; and
- reverify failure.

Each case proves the exact Planner and worker call counts and that no later
tool call occurs after the native terminal condition.

### 13.6 Baseline

Before implementation, the inherited minimal handoff seam passes 492 tests.
Implementation planning must record the exact focused command. The new suite
must include the existing minimal handoff, local-worker adapter/context/harness,
PlanGraph current-step runner, action application, workflow contract/compiler,
and typed receipt coverage.

No provider, worker-box, Rhino, or Grasshopper contact is part of deterministic
testing.

## 14. Post-merge engineering smoke sequence

No smoke is authorized by this design, implementation, review, or merge.

### 14.1 First separately authorized smoke

The first proposed smoke isolates the new model composition:

```text
real Planner adapter and provider
-> strict draft admission
-> real worker-box transport
-> causally responsive operator/test-only fake typed executor
-> native terminal result
```

The fake executor:

- exists only in test/operator code;
- derives responses from received parameters;
- refuses unexpected tool names, call order, pins, code, or GUIDs; and
- never enters production source or a production fixture registry.

The smoke allows one Planner call and at most one worker call, with no retry or
fallback. Failure returns the ordinary typed operational result. Success proves
model-to-model composition and contract compliance only; it does not prove C#
compilation or Rhino/Grasshopper behavior.

### 14.2 Second separately authorized smoke

Only after the first smoke is understood should a second authorization replace
the fake executor with the unchanged real typed-tool bridge and a live
Rhino/Grasshopper environment.

This separates model integration failure from desktop/plugin/tool failure
without introducing scientific one-shot machinery.

## 15. Deliberate non-claims

This slice does not establish:

- a general Planner contract or capability registry;
- arbitrary component interfaces or pin types;
- Planner-authored workflow topology;
- multi-turn Planner revision;
- retries, fallback models, or prompt repair;
- a general worker runtime;
- Chat, Chirp, DSPy, MCP, or CLI integration;
- provider/model/generation construction;
- durable evidence, archives, fingerprints, readiness, or attempt identity;
- live C# compilation; or
- Rhino/Grasshopper correctness.

It proves one narrow product composition:

```text
user intent
-> tiny Planner draft
-> deterministic compiler
-> bounded worker
-> typed tool execution
-> native receipt-owned terminal result
```

## 16. Delivery boundary

This specification authorizes no implementation or live contact.

After independent specification review:

1. use `superpowers:writing-plans` to create the implementation plan;
2. stop again for review before implementation;
3. implement through deterministic fake-backed tests only;
4. review and merge separately; and
5. request explicit authorization for each post-merge smoke.
