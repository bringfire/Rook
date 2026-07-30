# Minimal Intent-to-Worker Real Grasshopper Compile Smoke Design

**Date:** 2026-07-30

**Status:** Approved design for specification review

**Base:** `2bb2b5a7d7c708b738252ed96a4d0b547fbe45a2`

## 1. Purpose

PR #515 established this operator-only hierarchy against a causal synthetic
tool boundary:

```text
fixed intent
-> real Claude Planner
-> strict four-field draft
-> deterministic workflow compiler
-> real Qwen worker
-> synthetic create/update receipts
-> native terminal result
```

The live observation reached both model roles and the typed-tool seam. It
stopped with an update-time synthetic contract failure. The retained bounded
summary did not establish which synthetic predicate failed. That observation
therefore did not test whether the worker-authored body compiles in
Grasshopper.

This slice replaces only the synthetic executor with the existing real tool
path:

```text
fixed intent
-> real Claude Planner
-> strict four-field draft
-> deterministic workflow compiler
-> real Qwen worker
-> existing ToolDispatcher
-> real Grasshopper create receipt
-> one worker repair
-> real Grasshopper compile receipt
-> stop
```

It is a one-attempt engineering smoke, not a scientific experiment or a new
product runtime.

## 2. Falsifiable claim

Given:

- one fixed admitted intent;
- the existing `hybrid` Planner/Worker hierarchy;
- exactly one discovered live RookNative instance;
- an operator-prepared empty, unsaved, ready Grasshopper canvas; and
- one fresh Grasshopper document created by the smoke;

the existing hierarchy can produce a C# component whose real update receipt
proves clean compilation after at most one worker repair.

Success requires the existing native terminal result. A preparation failure,
Planner stop, worker stop, dispatcher failure, authentic compile failure, or
internal contract violation stops without retry, fallback, repair outside the
worker, alternate model, or second attempt.

## 3. Scope and files

The complete slice adds exactly four files over its design and implementation
lifecycle:

```text
docs/superpowers/specs/2026-07-30-minimal-intent-worker-real-compile-smoke-design.md
docs/superpowers/plans/2026-07-30-minimal-intent-worker-real-compile-smoke.md
scripts/minimal_intent_worker_real_compile_smoke.py
mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
```

No product module changes are permitted. In particular, the slice does not
modify:

- `minimal_intent_worker_integration.py`;
- `minimal_csharp_repair_handoff.py`;
- Planner draft admission or prompts;
- workflow templates, compilation, topology, or actions;
- local-worker prompts, schemas, adapters, or transport;
- `ToolDispatcher`, Grasshopper tool handlers, or receipt contracts;
- the synthetic model smoke; or
- Chat, MCP, Chirp, DSPy, or any product registration surface.

The new script is a thin sibling of the synthetic smoke. Intentional local
duplication keeps both operator specimens isolated until the real path has
produced one successful observation.

## 4. Fixed inputs and contact guard

### 4.1 Intent and models

The exact intent remains:

```text
Create a Grasshopper C# component with one A:double output and compile cleanly.
```

The script calls only `get_models("hybrid")` and refuses unless it resolves
exactly:

```text
Planner: anthropic/claude-opus-4-6
Worker:  ollama_chat/qwen3-coder:30b-a3b-q8_0
```

There is no intent, profile, model, generation, port, or timeout override.
Role resolution and exact identity validation occur immediately after the
argument guard and before discovery, dispatcher construction, or tool contact.
A malformed or mismatched role refuses with zero live calls and zero transport
construction.

### 4.2 Arguments

The script accepts one optional operational flag:

```text
no arguments
-> live_execution_not_requested
-> refuse before discovery or contact

exactly ["--execute-live"]
-> enter the fixed one-attempt sequence

anything else
-> invalid_arguments
-> refuse before discovery or contact
```

The flag is only an accidental-contact guard. It does not authenticate or
record human authorization.

## 5. RookNative discovery and target custody

The script calls `discover_instances()` and filters to exact
`pluginType == "native"` records. It requires exactly one surviving record.
Zero records yield `rooknative_instance_absent`; two or more yield
`rooknative_instance_ambiguous`.

The selected record must satisfy `type(processId) is int` and
`type(port) is int`, with both values positive; booleans are rejected. The
script freezes both values for the entire transaction and creates one
dispatcher:

```python
ToolDispatcher(
    port=frozen_port,
    local_tools=build_local_tools(),
)
```

The process ID is recorded discovery identity only. `ToolDispatcher` transport
is bound by the frozen constructor port, not by process ID.

There is no `ROOK_RHINO_PORT`, CLI port, fallback port, panel selection,
automatic selection, or rediscovery-based substitution.

`discover_instances()` reads discovery records and performs local PID checks.
Under its existing behavior it may remove a stale dead-PID discovery record.
It does not make an HTTP/TCP liveness request, so discovery is not a tool
contact. The first pinned `gh_status` call establishes endpoint liveness and
Grasshopper readiness.

## 6. Destructive preparation boundary

The operator must manually provide an already loaded, ready, empty, unsaved
Grasshopper canvas. The script never launches Grasshopper, polls readiness, or
manages application lifecycle.

Preparation uses the same dispatcher and frozen port throughout:

```text
gh_status
-> gh_document_new
-> gh_status
-> only then construct model transports
```

### 6.1 Pre-status admission

The first normalized `gh_status` result must satisfy every equation:

```text
type(result) is dict
result.success is True
type(result.data) is dict
data.available is True
data.ready_for_edit is True
data.has_active_document is True
data.document_id is an exact nonblank string
data.object_count is an exact integer 0 (bool is rejected)
data.document_path is the exact empty string
```

The empty object count and empty path protect a populated or saved user canvas
from replacement. Failure stops before `gh_document_new` and before model
construction.

### 6.2 New-document admission

Immediately before dispatching `gh_document_new`, the preparation state moves
to `document_new_started`. The one response must satisfy the current existing
tool shape:

```text
type(result) is dict
result.success is True
type(result.data) is dict
data.Created is True
```

The post-status check, not the authored creation response alone, proves the
new document's actual state. No other operation occurs between admission of
the pre-status result and starting this dispatch.

### 6.3 Post-status admission

One immediate second `gh_status` call on the same dispatcher and port must
satisfy:

```text
type(result) is dict
result.success is True
type(result.data) is dict
data.available is True
data.ready_for_edit is True
data.has_active_document is True
data.document_id is an exact nonblank string
data.document_id != pre_status.document_id
data.object_count is an exact integer 0 (bool is rejected)
data.document_path is the exact empty string
```

The empty `document_path` is the existing normalized status contract's proof
that the new document is unsaved. Only a passing post-status moves preparation
to `fresh_document_verified` and permits model transport construction.

### 6.4 Preparation states and exceptions

The state machine is closed:

```text
not_started
├─ status_rejected
└─ status_verified
   └─ document_new_started
      ├─ failure remains document_new_started
      └─ fresh_document_verified
```

`status_rejected` is terminal for preparation. `status_verified` is the
successful pre-status branch immediately before document mutation; it is not
another name for pre-status failure.

Outcomes distinguish contact and mutation truthfully:

| Locus | Preparation state | Claim |
|---|---|---|
| argument or discovery failure | `not_started` | no live tool contact or mutation |
| pre-status rejection or ordinary exception/timeout | `status_rejected` | Rhino contacted; no document mutation claimed |
| document-new rejection or ordinary exception/timeout | `document_new_started` | replacement may have occurred |
| post-status rejection or ordinary exception/timeout | `document_new_started` | replacement may have occurred |
| post-status passes | `fresh_document_verified` | fresh empty unsaved document proven |

Every nonpassing preparation path constructs zero Planner and Worker
transports. Ordinary exceptions are caught as `Exception`, never
`BaseException`, and exception text is not retained or rendered.

The script performs no save, close, clear, restoration, or cleanup. A prepared
or partially prepared document remains visible to the operator.

## 7. Tool contact and restricted execution

The script's complete tool-level contact vocabulary is:

```text
gh_status
gh_document_new
gh_create_csharp_script
gh_update_script
```

The one successful-path sequence is:

```text
gh_status
-> gh_document_new
-> gh_status
-> gh_create_csharp_script
-> gh_update_script
```

The first three calls belong only to preparation. The integration runner
receives a private restricted executor over the pinned dispatcher's
`dispatch()` method. That executor permits only these legitimate incomplete
prefixes:

```text
[]
[gh_create_csharp_script]
[gh_create_csharp_script, gh_update_script]
```

It rejects update-before-create, repeated create, repeated update, substituted
tools, a third call, and any call after update. Before any prefix transition or
delegation, it also rejects every parameter mapping containing the key
`port`. This check occurs before `ToolDispatcher.dispatch()`, whose existing
implementation otherwise permits a caller-supplied port to override the
constructor port. A rejected `port` key produces zero dispatcher calls.

The executor does not require update at finalization: a Planner, worker,
action, create, or native stop may truthfully leave an incomplete prefix. Only
`completed` requires the full two-call prefix and the existing verified native
terminal result.

The restricted executor does not reinterpret or reconstruct tool parameters,
component identity, worker code, receipts, graph state, or terminal meaning.
The deterministic compiler, worker action path, `ToolDispatcher`, existing
Grasshopper handlers, and native handoff result retain those responsibilities.
The create receipt remains the sole source of the component GUID, and the
worker action remains the sole source of repair code.

The tool-level vocabulary does not imply one HTTP request per tool. The
existing create and update handlers may make their already-reviewed internal
bridge calls to configure pins, write code, settle the solution, and read
compiler errors.

## 8. Model construction and composition

Only after `fresh_document_verified` does the script construct the exact model
transports already reviewed in the synthetic smoke.

Planner:

```text
model: anthropic/claude-opus-4-6
temperature: 0
max_tokens: 1024
max_retries: 0
timeout_s: 120
response_format: code-owned minimal Planner JSON schema
structured_response_schema: null
```

Worker:

```text
model: ollama_chat/qwen3-coder:30b-a3b-q8_0
temperature: 0
max_tokens: 1024
max_retries: 0
timeout_s: 120
structured_response_schema: _local_worker_response_union_schema()
```

The live composition is exactly:

```python
await run_minimal_intent_worker_integration(
    FIXED_INTENT,
    planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
    worker_transport=worker_transport,
    tool_executor=restricted_real_executor,
)
```

No raw Planner mapping bypasses the existing adapter or draft loader. No
provider/model construction enters a product module. There is one Planner call
maximum, zero or one Worker call, and no retry, fallback, prompt repair,
deterministic model-output patch, alternate model, or second attempt.

## 9. Bounded operator result

The script prints one compact JSON object containing only:

```text
operator_status
operator_reason
intent
profile
planner_model
worker_model
rooknative_process_id
rooknative_port
document_preparation_status
preparation_tool_calls
planner_calls
worker_calls
execution_tool_calls
terminal_stage
terminal_reason
planner_adapter_status
worker_adapter_status
```

Unreached fields are `null`. The summary never contains discovery file paths,
document IDs, document names, prompts, model responses, worker code,
rationale, diagnostics, component GUIDs, receipts, tool parameters,
credentials, provider-returned metadata, or LiteLLM telemetry.

### 9.1 Status vocabulary

| `operator_status` | Meaning |
|---|---|
| `refused` | argument, profile, or discovery failure before `gh_status`; zero preparation calls |
| `preparation_failed` | Rhino was contacted but document preparation was not proven |
| `failed` | preparation passed and the existing model/handoff path returned a nonterminal result, or an internal contract failed |
| `completed` | existing native terminal result plus exact create/update prefix |

Closed reason tokens identify only the boundary, including:

```text
live_execution_not_requested
invalid_arguments
profile_identity_invalid
profile_role_mismatch
rooknative_instance_absent
rooknative_instance_ambiguous
rooknative_identity_invalid
pre_status_rejected
pre_status_exception
document_new_rejected
document_new_exception
post_status_rejected
post_status_exception
native_stop
operator_internal_error
native_terminal
```

Native terminal reasons use the same closed safe projector as the synthetic
smoke: known code-owned tokens/categories remain visible and unknown or
model-derived text collapses to `native_reason_unclassified`. Exception and
provider text never enters `operator_reason` or `terminal_reason`.

### 9.2 Count authority

Counts derive from owned control flow and native records, not telemetry:

- `preparation_tool_calls` increments immediately before each of the three
  preparation dispatches;
- `planner_calls` becomes one only when the concrete Planner adapter is
  invoked;
- `worker_calls` becomes one only when the returned native handoff retains its
  worker adapter record; and
- `execution_tool_calls` is the restricted executor's received prefix length.

If an unexpected exception prevents a native result from proving a later
count, the summary uses `null` rather than inventing certainty.

`completed / native_terminal` requires:

```text
document_preparation_status == fresh_document_verified
execution prefix == [create, update]
native terminal stage == terminal
native terminal reason == terminal_node_selected:done
```

The existing validated handoff result, not the operator script, owns the
clean-receipt and graph-lineage proof behind that terminal state.

The result is ephemeral operator output. It is not an archive, checkpoint,
readiness record, attempt identity, or scientific evidence object.

## 10. Deterministic no-contact verification

Implementation and review contact no provider, worker box, Rhino, or
Grasshopper. The test module may replace discovery, dispatcher construction,
dispatcher responses, model transports, and the integration runner. No fake
executor or synthetic receipt implementation is added to the operator script
or any product module.

### 10.1 Guard and discovery matrix

Prove:

- no argument and every unknown/additional argument stop before discovery;
- profile loading, malformed role identity, and role mismatch stop before
  discovery, dispatcher construction, or live contact;
- zero and multiple native records refuse with zero dispatcher/model
  construction;
- non-native records do not count;
- malformed process IDs or ports refuse;
- exactly one native record freezes one exact port; and
- no environment or argument can override the selected target.

### 10.2 Preparation equations

Mutate every pre-status and post-status equation independently. Require the
exact preparation state, call count, and zero model construction for each
failure. Include document-ID equality, populated document, saved document,
malformed object count, and boolean-as-integer cases.

At each of the three calls, cover ordinary exception and timeout behavior:

```text
pre-status exception
-> status_rejected
-> preparation_tool_calls == 1
-> no mutation claimed

document-new exception
-> document_new_started
-> preparation_tool_calls == 2
-> replacement may have occurred

post-status exception
-> document_new_started
-> preparation_tool_calls == 3
-> replacement may have occurred
```

Use sentinel exception text and prove it cannot reach the summary. Every
preparation failure constructs zero model transports.

The passing case exact-compares the call sequence and proves all calls use the
same dispatcher and frozen port. Model construction must be a fail-if-reached
sentinel until the post-status equations pass.

### 10.3 Restricted executor prefixes

Directly admit exactly:

```text
[]
[create]
[create, update]
```

Directly reject update-before-create, repeated create/update, substitution,
extra calls, calls after update, and a `port` key on either allowed tool. The
`port` mutation tests must prove zero calls reach the dispatcher. A returned
native worker refusal with prefix `[create]` must remain the native stop and
must not be relabeled as a restricted-executor failure. Completion must refuse
any prefix other than `[create, update]`.

### 10.4 Model and integration boundary

Reuse the synthetic smoke's exact offline transport assertions:

- fixed `hybrid` roles validate before either model constructor;
- Planner uses `response_format` and no top-level `format`;
- Worker uses `format` through the existing structured-schema path;
- both use temperature zero, 1,024 output tokens, zero retries, and 120-second
  timeout; and
- schemas are freshly derived from the existing code-owned builders.

One no-contact orchestration witness uses scripted dispatcher and transport
responses only to prove ordering and delegation. It does not claim real
receipt semantics; the merged compositor tests and later live observation own
those claims.

### 10.5 Output and surface audit

Inject sentinels through discovery paths, exceptions, diagnostics, model
responses, worker code, rationale, GUIDs, receipts, and provider errors. Prove
none enters stdout.

Prove the four-file scope and absence of product-module or synthetic-smoke
changes. The focused regression includes the complete prior 654-test seam plus
the new operator tests.

Tests may call `main(["--execute-live"])` only in process with discovery,
dispatcher, model transports, and integration fully replaced before contact.
No test launches the script with the live flag or reaches a real external
capability.

## 11. Separately authorized live boundary

Specification, planning, implementation, and review do not execute the live
flag. After merge, a separate explicit authorization may permit one command
from a clean merge-SHA checkout.

Before that command, the operator must manually ensure:

- exactly one RookNative Rhino instance is running;
- Grasshopper is already loaded and ready;
- the active Grasshopper document is empty and unsaved; and
- replacing that empty canvas is acceptable.

The same absolute Python interpreter used for execution must pass the offline
LiteLLM capability/materialization checks immediately beforehand. The command
then permits exactly one transaction and stops after its first result.

Permitted tool-level prefixes are:

```text
[]
[status]
[status, document_new]
[status, document_new, status]
[status, document_new, status, create]
[status, document_new, status, create, update]
```

No retry, second attempt, save, cleanup, restoration, alternate model, or
additional tool is authorized. The resulting Grasshopper document remains
open and unsaved for operator inspection.

## 12. Deliberate non-claims

This slice does not prove:

- arbitrary intent, interface, capability, or repair behavior;
- production Chat/MCP integration;
- a general Planner/worker/tool runtime;
- more than one Planner call or Worker repair;
- retries, fallback, cleanup, or document restoration;
- provider identity beyond requested configuration;
- correctness of arbitrary worker-authored C#; or
- durable or scientific evidence.

A successful observation proves only that this fixed hierarchy produced one
real clean Grasshopper compilation receipt through the existing product seam.

## 13. Delivery boundary

This specification authorizes no implementation and no live contact.

After independent specification review:

1. invoke `superpowers:writing-plans` and write the implementation plan;
2. stop for independent plan review;
3. implement and review with deterministic no-contact tests only;
4. merge separately; and
5. request separate authorization before any live execution.
