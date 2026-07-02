# LM5I - Local Worker Request Envelope Design

**Date:** 2026-07-02
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker transport boundary
**Predecessors:** LM5A local worker turn context, LM5B response contract, LM5C response disposition, LM5D one-turn harness, LM5E deterministic scenario suite, LM5F scenario evaluation, LM5G response payload loader, LM5H context payload renderer

---

## 1. Goal

LM5I adds the deterministic request-envelope boundary for the local worker box.

LM5H renders the worker-facing context payload:

```text
LocalWorkerTurnContext -> context payload
```

LM5G loads the worker-returned response payload:

```text
response payload -> LocalWorkerTurnResponse
```

LM5I composes those two transport halves into a single schema-tagged request
artifact:

```text
LM5H context payload
+
LM5G response schema identity / response contract description
=
LM5I request envelope
```

The public seam is:

```python
LOCAL_WORKER_TURN_REQUEST_SCHEMA = "rook.local_worker_turn_request:v1"

def render_local_worker_turn_request_payload(
    context: LocalWorkerTurnContext,
) -> Mapping[str, Any]:
    ...
```

LM5I answers only:

```text
Can Rook produce one machine-readable request payload that says what the worker
has received and what syntactic response envelopes it may return?
```

It does not answer:

```text
How should a prompt be written?
Which model should run?
How should raw model text be parsed?
Is a returned response admissible for this context?
Should an action execute?
Should the graph or stream continue?
```

Layer split:

```text
LM5A: Rook-owned artifacts -> LocalWorkerTurnContext
LM5H: LocalWorkerTurnContext -> context payload
LM5I: LocalWorkerTurnContext -> request envelope payload
future adapter: request envelope payload -> worker/model transport
LM5G: response payload -> LocalWorkerTurnResponse
LM5B: context + response -> attempt record
LM5C: attempt -> disposition
LM5D: one-turn harness
LM5F: scenario evaluation
```

LM5I is the first production layer allowed to compose the outbound context
schema with the inbound response schema. That composition is the point of the
slice. It does not make LM5I a worker adapter, prompt renderer, model harness,
or runtime.

---

## 2. Production Scope

Add one production module:

```text
mcp_server/src/rook/agent/local_worker_turn_request.py
```

Add one focused test file:

```text
mcp_server/tests/test_local_worker_turn_request.py
```

Do not edit:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
```

If implementation reveals a genuine LM5A-H bug, treat that as a separate
finding rather than bundling a fix into LM5I.

No package-level exports are added. Callers import explicitly from:

```python
rook.agent.local_worker_turn_request
```

---

## 3. Public Surface

The module exports exactly:

```python
__all__ = (
    "LOCAL_WORKER_TURN_REQUEST_SCHEMA",
    "render_local_worker_turn_request_payload",
)
```

Add:

```python
LOCAL_WORKER_TURN_REQUEST_SCHEMA = "rook.local_worker_turn_request:v1"

def render_local_worker_turn_request_payload(
    context: LocalWorkerTurnContext,
) -> Mapping[str, Any]:
    ...
```

Do not export:

```text
response contract helper functions
response field-set constants
response kind constants
schema registry constants
request field constants
payload dataclasses
serializer helpers
formatter helpers
```

The public artifact is the full request envelope. A standalone response-contract
helper would become a second integration point before a real consumer needs it.

---

## 4. Accepted Input

`render_local_worker_turn_request_payload(...)` accepts only a real
`LocalWorkerTurnContext`.

```text
context not LocalWorkerTurnContext -> TypeError
```

LM5I performs this type check before calling LM5H:

```python
if not isinstance(context, LocalWorkerTurnContext):
    raise TypeError("context must be LocalWorkerTurnContext")
```

This keeps the request seam's error surface explicit and local. LM5H still has
its own type check; duplication at public seams is intentional.

LM5I does not accept:

```text
raw dictionaries
context-like mappings
context payloads
schema-less authoring surfaces
model-supplied context objects
```

LM5A owns context construction. LM5H owns context projection. LM5I owns request
envelope composition.

---

## 5. Request Payload Shape

LM5I renders a strict schema-tagged request envelope:

```python
{
    "schema": LOCAL_WORKER_TURN_REQUEST_SCHEMA,
    "context": <LM5H context payload>,
    "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    "response_contract": {...},
}
```

The top-level key set is exact:

```text
schema
context
response_schema
response_contract
```

No aliases are accepted or rendered:

```text
context_schema
response
contract
output
protocol
instructions
prompt
adapter
model
worker
request_id
timestamp
run_id
context_id
fingerprint
```

There is no top-level `context_schema`. The nested LM5H context payload is a
complete artifact and carries its own schema:

```python
payload["context"]["schema"] == LOCAL_WORKER_TURN_CONTEXT_SCHEMA
```

Duplicating that schema at the request level would create a second truth source.

---

## 6. Context Payload Composition

LM5I calls LM5H exactly once:

```python
context_payload = render_local_worker_turn_context_payload(context)
return {
    "schema": LOCAL_WORKER_TURN_REQUEST_SCHEMA,
    "context": context_payload,
    "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    "response_contract": _render_response_contract(),
}
```

LM5I embeds the freshly rendered LM5H context payload directly. It does not
deep-copy the LM5H result a second time because:

- the context payload is freshly produced during the request render call;
- no external alias exists before the envelope is returned;
- mutating the returned envelope cannot mutate the source
  `LocalWorkerTurnContext`.

Tests should prove:

- LM5H renderer is called exactly once;
- the returned request `context` value is the exact object returned by a
  monkeypatched LM5H renderer;
- mutating a real request payload's nested context does not affect the original
  `LocalWorkerTurnContext`;
- two separate request renders return independent context payload objects.

LM5I production does not import `LOCAL_WORKER_TURN_CONTEXT_SCHEMA`. It trusts
LM5H as the renderer of the context artifact and does not revalidate the nested
context schema in production. Tests may import the context schema to assert the
public payload value.

---

## 7. Response Schema And Contract

LM5I includes the public LM5G response schema value:

```python
"response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA
```

It also includes a small explicit machine-readable response contract:

```python
"response_contract": {
    "kinds": [
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    ],
    "field_sets": {
        "action_request": ["schema", "kind", "action_id", "rationale", "input"],
        "clarification_request": ["schema", "kind", "question", "rationale"],
        "refusal": ["schema", "kind", "category", "reason"],
        "observation": ["schema", "kind", "message", "data"],
    },
    "required_nullable_fields": {
        "clarification_request": ["rationale"],
        "observation": ["data"],
    },
    "refusal_categories": [
        "unsafe",
        "insufficient_context",
        "unsupported_action",
        "out_of_scope",
    ],
}
```

This is deliberately more than a schema pointer. A pointer alone would force an
external worker or adapter to know the response protocol out of band, which is
the gap LM5I closes.

The response contract is descriptive transport structure, not validation
authority:

- LM5G remains the response payload loader.
- LM5B remains context-aware admissibility validation.
- LM5C remains disposition mapping.
- LM5D remains one-turn harness recording.
- LM5F remains scenario evaluation.

The request envelope says:

```text
these are the only syntactic response envelopes this transport accepts
```

It does not say:

```text
here is how Rook will interpret your reasoning
```

---

## 8. Structural / Vocabulary Only

`response_contract` includes only structural and vocabulary facts:

```text
response_schema
kinds
field_sets
required_nullable_fields
refusal_categories
```

It does not include semantic notes such as:

```text
action_id must match allowed_actions
input is not schema-validated here
unknown actions become blocked
refusal does not halt the workflow
observation has no continuation semantics
```

Those statements are true in downstream layers, but they belong to LM5B/C/D/F
behavior and future adapter or prompt documentation. Embedding them in LM5I
would turn the request envelope into a prompt-ish instruction surface and risk
duplicating downstream policy.

Also do not include:

```text
descriptions
examples
rationale
notes
instructions
"choose action_request when ..."
"ask clarification if ..."
"return JSON shaped like ..."
```

LM5I is a protocol envelope, not a prompt envelope.

---

## 9. JSON-Ready Transport Containers

LM5I returns fresh mutable JSON-ready Python containers:

```text
objects -> dict
arrays -> list
scalars -> str | bool | int | finite float | None
```

The response contract uses lists only, in deterministic order:

- `response_contract["kinds"]`;
- every `response_contract["field_sets"][kind]`;
- every `response_contract["required_nullable_fields"][kind]`;
- `response_contract["refusal_categories"]`.

LM5I does not return:

```text
MappingProxyType
tuples
frozensets
dataclasses
canonical JSON strings
```

Private module-level literals may use tuples or other immutable implementation
forms, but `_render_response_contract()` must render fresh dict/list containers
for callers. Mutating one request envelope must not affect later request
envelopes.

Example test:

```python
first = render_local_worker_turn_request_payload(context)
first["response_contract"]["kinds"].append("bad")
first["response_contract"]["field_sets"]["action_request"].append("bad")
first["response_contract"]["required_nullable_fields"]["observation"].append("bad")
first["response_contract"]["refusal_categories"].append("bad")

second = render_local_worker_turn_request_payload(context)
assert second["response_contract"]["kinds"] == [
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
]
```

This is a non-canonical transport payload. LM5I does not promise canonical JSON,
payload fingerprints, content hashes, sorted arbitrary mappings, report storage,
or durable run identity.

---

## 10. Import And Boundary Rules

Allowed production imports:

```python
from collections.abc import Mapping
from typing import Any

from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    render_local_worker_turn_context_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
)
```

`Mapping` and `Any` are allowed only for public type annotation convenience.

Do not import or reference:

```text
LOCAL_WORKER_TURN_CONTEXT_SCHEMA
load_local_worker_turn_response_payload
validate_local_worker_turn_response
WorkerActionRequest
WorkerClarificationRequest
WorkerRefusal
WorkerObservation
LocalWorkerTurnResponse
dispose_local_worker_turn_response
run_local_worker_turn
evaluate_local_worker_scenario_result
build_local_worker_scenario_report
build_local_worker_turn_context
compile_workflow_contract
load_workflow_contract_payload
snapshot_workflow_contract
run_current_step_stream
run_current_mapped_step
execute_mapped_step
map_accepted_proposal_to_step
revalidate_proposal
propose_next_node
json
yaml
Path
open
model
RookChat
prompt
dispatcher
CapabilityIndex
live Rhino/GH surfaces
tool execution surfaces
graph mutation helpers
stream continuation helpers
```

Because LM5I lives in a new tiny module, tests should use a module-level
AST/import/source guard rather than a function-scoped guard.

The old safety rail remains relevant:

```text
discoverable metadata != callable authority
```

LM5I may expose response vocabulary and nested context facts to a future worker.
It does not make any discovered metadata callable, dispatchable, authorized, or
safe to execute. Action authority remains downstream and Rook-owned.

---

## 11. Tests

Add:

```text
mcp_server/tests/test_local_worker_turn_request.py
```

### Unit Coverage

Tests should cover:

- public `__all__` is exactly
  `("LOCAL_WORKER_TURN_REQUEST_SCHEMA", "render_local_worker_turn_request_payload")`;
- schema constant value is `"rook.local_worker_turn_request:v1"`;
- wrong context input raises `TypeError`;
- top-level request key set is exact:
  `{"schema", "context", "response_schema", "response_contract"}`;
- no top-level `context_schema`, `instructions`, `prompt`, `adapter`, `model`,
  `worker`, `request_id`, `timestamp`, `run_id`, `context_id`, or
  `fingerprint`;
- request `schema` value matches `LOCAL_WORKER_TURN_REQUEST_SCHEMA`;
- nested `context["schema"]` value matches `LOCAL_WORKER_TURN_CONTEXT_SCHEMA`;
- `response_schema` value matches `LOCAL_WORKER_TURN_RESPONSE_SCHEMA`;
- `response_contract` key set is exact:
  `{"kinds", "field_sets", "required_nullable_fields", "refusal_categories"}`;
- response kinds are exact and ordered;
- each field set is exact and ordered according to LM5G flat payload specs;
- required nullable fields are exact and ordered;
- refusal categories are exact and ordered;
- `response_contract` contains no descriptions, examples, notes, instructions,
  or semantic policy fields;
- all rendered arrays are plain lists and objects are plain dicts;
- response contract containers are fresh/no-aliased across calls;
- request context payload is fresh/no-aliased across calls;
- mutating returned `payload["context"]` does not affect the source
  `LocalWorkerTurnContext`;
- monkeypatched LM5H renderer is called exactly once;
- monkeypatched LM5H context payload object is embedded directly in the request
  envelope;
- module-level AST/import guard keeps production narrow.

### Integration Coverage

Include one compact outbound/inbound integration proof:

```text
compiled repair workflow
-> build_local_worker_turn_context(...)
-> render_local_worker_turn_request_payload(context)
-> deterministic test adapter reads:
     request["context"]["allowed_actions"]
     request["response_schema"]
     request["response_contract"]["field_sets"]["action_request"]
-> strict LM5G response payload
-> load_local_worker_turn_response_payload(...)
-> run_local_worker_turn(context, worker returning loaded response)
-> evaluate_local_worker_scenario_result(...)
```

Assertions should prove:

- the real compiled repair workflow context renders into a request envelope;
- adapter reads the requestable action id from
  `request["context"]["allowed_actions"]`;
- adapter does not use `request["context"]["current_node"]["execution_ref"]` as
  an action id;
- adapter uses `request["response_schema"]` for the response payload schema;
- adapter sees the `action_request` field set expected by LM5G;
- LM5G loads the adapter response payload;
- LM5D records a completed harness turn;
- LM5F evaluates the result as passed;
- no model, prompt, RookChat, stream, live Rhino/GH, file, JSON parser, or
  Capability Index binding is involved.

---

## 12. Verification

Targeted:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_request.py
```

Nearby:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py
```

Focused PlanGraph/local-worker gate:

```powershell
$files = @(
  (Get-ChildItem -Path mcp_server\tests -Filter 'test_plan_graph*.py').FullName +
  (Get-ChildItem -Path mcp_server\tests -Filter 'test_local_worker*.py').FullName
)
mcp_server\.venv\Scripts\python.exe -m pytest @files
```

Static/scope checks:

- `git diff --check`;
- production diff exactly
  `mcp_server/src/rook/agent/local_worker_turn_request.py`;
- test diff exactly `mcp_server/tests/test_local_worker_turn_request.py`;
- spec/plan docs only in `docs/superpowers`;
- no LM5H/LM5G production edits;
- no package-level export edits;
- module-level AST/import guard;
- no model, RookChat, prompt, dispatcher, stream, runtime, compiler, response
  loader, file, JSON parser, YAML, Capability Index, graph mutation, or tool
  execution imports/calls.

No live test. No model test. No RookChat test. No stream test. No prompt test.
No Capability Index test. No file, JSON, or YAML parser test.

---

## 13. Explicit Non-Goals

LM5I does not add:

- prompt rendering;
- prompt prose;
- response examples;
- response semantic notes;
- model calls;
- model adapters;
- worker callables;
- raw text parsing;
- JSON text parsing;
- YAML parsing;
- file or path loading;
- context payload loader;
- response payload loader;
- response admissibility validation;
- disposition, harness, or scenario evaluation helpers;
- action input schema validation;
- action authorization;
- action dispatch or execution;
- Capability Index binding;
- RookChat integration;
- graph mutation;
- stream continuation;
- retry, fallback, critic, or oversight loops;
- request ids;
- timestamps;
- run ids;
- worker/model/session ids;
- payload fingerprints;
- package-level re-exports;
- OpenProse dependencies.

LM5I is only the strict, deterministic request envelope from an
already-constructed LM5A context into a JSON-ready transport payload that
contains the LM5H context payload and the structural LM5G response contract.
