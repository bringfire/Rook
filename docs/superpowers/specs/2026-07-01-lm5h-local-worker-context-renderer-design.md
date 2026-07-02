# LM5H - Local Worker Context Renderer Design

**Date:** 2026-07-01
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker transport boundary
**Predecessors:** LM5A local worker turn context, LM5B response contract, LM5C response disposition, LM5D one-turn harness, LM5E deterministic scenario suite, LM5F scenario evaluation, LM5G response payload loader

---

## 1. Goal

LM5H adds the deterministic outbound transport boundary for the local worker
box.

LM5A already defines the frozen Python context artifact a future
local/internal worker may see. LM5G already defines the inbound loader from an
already-parsed response payload into an LM5B typed response. LM5H closes the
remaining transport asymmetry:

```text
LocalWorkerTurnContext
-> strict context payload
-> future external/local worker
-> response payload
-> LM5G loader
```

The public seam is:

```python
LOCAL_WORKER_TURN_CONTEXT_SCHEMA = "rook.local_worker_turn_context:v1"

def render_local_worker_turn_context_payload(
    context: LocalWorkerTurnContext,
) -> Mapping[str, Any]:
    ...
```

LM5H answers only:

```text
Can Rook render this already-constructed LocalWorkerTurnContext into a stable,
schema-tagged, JSON-ready worker-facing payload?
```

It does not answer:

```text
How should a prompt be written?
Which model should run?
What response schema should be shown?
Is a returned response admissible?
Should an action execute?
Should the stream continue?
```

Layer split:

```text
LM5A: Rook-owned artifacts -> LocalWorkerTurnContext
LM5H: LocalWorkerTurnContext -> context payload
future adapter: context payload -> worker/model transport
LM5G: response payload -> LocalWorkerTurnResponse
LM5B: context + response -> attempt record
LM5C: attempt -> disposition
LM5D: one-turn harness
LM5F: scenario evaluation
```

---

## 2. Production Scope

Modify one production module:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
```

Add one focused renderer test file:

```text
mcp_server/tests/test_local_worker_turn_context_renderer.py
```

Update the existing context public-surface test only if it pins `__all__`:

```text
mcp_server/tests/test_local_worker_turn_context.py
```

No new production module is added in LM5H. The renderer is specifically the
transport projection of the LM5A context artifact, so it belongs beside the
context dataclasses for this slice.

Do not edit:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
```

If implementation reveals a genuine bug in LM5A-G, treat that as a separate
finding rather than bundling a fix into LM5H.

---

## 3. Public Surface

Add exactly two public exports to `local_worker_turn_context.py`:

```python
LOCAL_WORKER_TURN_CONTEXT_SCHEMA = "rook.local_worker_turn_context:v1"

def render_local_worker_turn_context_payload(
    context: LocalWorkerTurnContext,
) -> Mapping[str, Any]:
    ...
```

Update `__all__` to include only these new names in addition to the existing
LM5A public surface.

Do not export:

```text
field key constants
section constants
payload dataclasses
schema registry
loader helpers
serializer helpers
formatter helpers
```

Field names are part of the schema contract and are pinned by spec/tests, not
by public Python constants.

---

## 4. Accepted Input

`render_local_worker_turn_context_payload(...)` accepts only a real
`LocalWorkerTurnContext`.

```text
context not LocalWorkerTurnContext -> TypeError
```

No duck typing, raw dictionaries, schema-less authoring surfaces, partial
context coercion, or mapping-to-context normalization are accepted.

LM5A owns context construction, validation, scaffold identity checks, current
node validation, graph summarization, history summarization, knowledge/action
duplicate checks, and context freezing. LM5H owns projection only.

---

## 5. Payload Shape

LM5H renders a strict flat schema envelope with top-level sections matching
LM5A context fields:

```python
{
    "schema": LOCAL_WORKER_TURN_CONTEXT_SCHEMA,
    "workflow": {...},
    "current_graph": {...},
    "current_node": {...} | None,
    "history": {...},
    "knowledge": [...],
    "allowed_actions": [...],
}
```

The top-level key set is exact. The payload does not include:

```text
response_schema
instructions
tools
capabilities
prompt
adapter
model
worker
context_id
fingerprint
timestamp
run_id
```

`current_node` is always present. When `context.current_node is None`, the
payload is:

```python
"current_node": None
```

Missing `current_node` would create a second dialect and is not allowed.

---

## 6. Field Projection

LM5H preserves LM5A field names exactly. It is a transport projection, not a
prompt adapter or UX layer.

No renames:

```text
current_graph -> not "graph"
allowed_actions -> not "tools"
execution_ref -> not "callable_tool"
input_schema -> not "parameters"
```

This distinction is load-bearing:

```text
current_node.execution_ref = observed graph fact
allowed_actions[*].action_id = only requestable action vocabulary
```

Capability Index metadata is not involved in LM5H.

LM5H renders all LM5A public context fields and nested summary fields:

### `workflow`

Exact keys:

```text
workflow_id
contract_schema
contract_fingerprint
compiler_id
provider_id
selected_template_id
max_steps
```

### `current_graph`

Exact keys:

```text
node_count
node_ids
ready_node_ids
terminal_node_ids
status_counts
```

### `current_node`

When present, exact keys:

```text
node_id
intent
role
status
execution_ref
is_terminal
has_execution_params
memory_keys
```

When absent, value is `None`.

### `history`

Exact keys:

```text
current_step_count
supply_count
last_accepted_node_id
last_execution_kind
last_stop_reason
recent_steps
recent_supplies
```

Each `recent_steps` entry has exact keys:

```text
accepted_node_id
execution_kind
ran
failure
```

Each `recent_supplies` entry has exact keys:

```text
decision
reason
selected_node_id
has_envelope
```

### `knowledge`

Each entry has exact keys:

```text
packet_id
kind
title
content
```

`content` is rendered faithfully as a JSON-ready copy.

### `allowed_actions`

Each entry has exact keys:

```text
action_id
kind
description
input_schema
```

`input_schema` is rendered faithfully as a JSON-ready copy.

LM5H does not invent a second visibility policy. If a field is too sensitive or
too broad to show a worker, that must be corrected before or inside LM5A context
construction, not hidden by the renderer.

---

## 7. JSON-Ready Transport Containers

LM5H returns fresh mutable JSON-ready Python containers:

```text
objects -> dict
arrays -> list
scalars -> str | bool | int | finite float | None
```

It does not return:

```text
MappingProxyType
tuples
dataclasses
canonical JSON strings
```

The returned payload is a transport copy. Downstream adapters may mutate it
without affecting the source context:

```python
payload["workflow"]["workflow_id"] = "changed"
payload["knowledge"][0]["content"]["note"] = "mutated"
```

Such mutations must not affect the original `LocalWorkerTurnContext`.

Mapping values like `knowledge.content`, `allowed_actions.input_schema`, and
`current_graph.status_counts` are copied into plain dictionaries. Sequence
values are copied into lists. LM5H does not sort arbitrary mappings or provide
canonical ordering. It preserves the order LM5A already stabilized:

- sorted node ids, ready ids, terminal ids;
- sorted memory keys;
- ordered history summaries;
- ordered knowledge packets;
- ordered allowed actions.

---

## 8. Local JSON Rendering Helper

LM5H uses a local private `_render_json_value(...)` helper. Even though LM5A
should already guarantee safe values, LM5H must defend its own transport
boundary so future drift fails loudly.

Helper behavior:

```python
def _render_json_value(value: object) -> Any:
    if isinstance(value, Mapping):
        require every key is str
        return {key: _render_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_render_json_value(item) for item in value]
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError
```

Rules:

- mapping keys must be strings;
- lists and tuples render to lists;
- strings are scalars, not sequences;
- integers are preserved exactly, including negative integers;
- `bool` is handled before `int`, so `True` remains `True`, not `1`;
- non-finite floats are rejected;
- arbitrary objects, callables, sets, dataclasses, and mapping values with
  non-string keys are rejected.

The helper returns mutable transport containers, not frozen artifacts.

---

## 9. Non-Canonical Stable Payload

LM5H promises:

```text
stable schema shape
stable field names
fresh JSON-ready containers
preserve LM5A-provided ordering
```

LM5H does not promise:

```text
canonical JSON
payload fingerprint
context id
run id
timestamp
hash/equality contract
sorted arbitrary mappings
report/storage format
```

Tests should assert shape and values directly. They must not assert serialized
JSON strings, cryptographic identities, or canonical output bytes.

---

## 10. No Reverse Loader

LM5H is renderer-only.

Do not add:

```python
load_local_worker_turn_context_payload(...)
```

Do not add:

```text
context payload -> LocalWorkerTurnContext
context round-trip tests
schema-less context authoring
dict-to-context coercion
model-supplied context acceptance
```

LM5A remains the only construction path for `LocalWorkerTurnContext`.

---

## 11. No Response Protocol In Context Payload

The rendered context payload contains only:

```text
schema
workflow
current_graph
current_node
history
knowledge
allowed_actions
```

It does not include:

```text
LOCAL_WORKER_TURN_RESPONSE_SCHEMA
allowed response kinds
response examples
JSON output instructions
"you must answer with ..."
model prompt text
adapter hints
```

A later adapter or prompt slice can compose:

```text
context payload
+ response schema
+ transport/prompt instructions
```

LM5H is only the outbound context artifact.

---

## 12. Import And Boundary Rules

Because LM5H lives in `local_worker_turn_context.py`, the existing module may
legitimately import LM4 types and builder-only dependencies. LM5H boundary
checks must therefore be function-scoped, not module-wide.

Guard target set:

- `render_local_worker_turn_context_payload`;
- private helpers whose names start with `_render_`.

Those function bodies must not call or reference:

```text
build_local_worker_turn_context
compile_workflow_contract
load_workflow_contract_payload
snapshot_workflow_contract
validate_local_worker_turn_response
load_local_worker_turn_response_payload
dispose_local_worker_turn_response
run_local_worker_turn
evaluate_local_worker_scenario_result
build_local_worker_scenario_report
LOCAL_WORKER_TURN_RESPONSE_SCHEMA
WorkerActionRequest
WorkerClarificationRequest
WorkerRefusal
WorkerObservation
LocalWorkerTurnResponse
json.loads
json.dumps
Path
open
model
RookChat
prompt
dispatcher
stream
runtime
Capability Index
live Rhino/GH surfaces
```

Production LM5H must not import LM5G symbols. Specifically it must not import
or reference:

```text
LOCAL_WORKER_TURN_RESPONSE_SCHEMA
load_local_worker_turn_response_payload
LM5B response dataclasses
LM5C disposition helpers
LM5D harness helpers
LM5F evaluation helpers
```

Integration tests may import LM5G/D/F to prove composition. Production may not.

---

## 13. Tests

Add:

```text
mcp_server/tests/test_local_worker_turn_context_renderer.py
```

Update:

```text
mcp_server/tests/test_local_worker_turn_context.py
```

only if required to keep the canonical `__all__` assertion exact.

### Unit Coverage

Tests should cover:

- public schema constant value;
- existing context module `__all__` includes the schema constant and renderer;
- renderer test has a small local public-surface smoke assertion;
- rendered payload has `payload["schema"] == LOCAL_WORKER_TURN_CONTEXT_SCHEMA`;
- wrong input type raises `TypeError`;
- top-level payload key set is exact;
- nested key sets are exact for workflow, current graph, current node, history,
  recent step, recent supply, knowledge, and allowed action entries;
- no response schema, instructions, tools, capabilities, prompt, model, worker,
  context id, timestamp, or run id fields exist;
- all LM5A public fields are rendered;
- `current_node is None` renders as `"current_node": None` with the key present;
- returned objects are plain `dict`;
- returned arrays are plain `list`;
- source tuple values render as lists;
- source mapping proxies render as dicts;
- nested `knowledge.content` and `allowed_actions.input_schema` render as
  faithful plain JSON-ready copies;
- mutating returned nested payload values does not alter the source context;
- `_render_json_value(...)` rejects non-string mapping keys;
- `_render_json_value(...)` rejects non-finite floats;
- `_render_json_value(...)` preserves bool and int values distinctly;
- function-scoped AST guard covers renderer and `_render_*` helpers only.

### Integration Coverage

Include one compact outbound/inbound integration proof:

```text
compiled repair workflow
-> build_local_worker_turn_context(...)
-> render_local_worker_turn_context_payload(context)
-> deterministic test adapter reads allowed_actions from payload
-> strict LM5G response payload
-> load_local_worker_turn_response_payload(...)
-> run_local_worker_turn(context, worker returning loaded response)
-> evaluate_local_worker_scenario_result(...)
```

The deterministic adapter is test-local only. It may read
`payload["allowed_actions"][0]["action_id"]` and return an `action_request`
response payload using `LOCAL_WORKER_TURN_RESPONSE_SCHEMA`.

Assertions should prove:

- real LM5A compiled repair workflow context renders successfully;
- adapter reads requestable action vocabulary from `allowed_actions`, not
  `current_node.execution_ref`;
- LM5G loads the adapter response payload;
- LM5D records a completed harness turn;
- LM5F evaluates the result as passed;
- no model, prompt, RookChat, stream, live Rhino/GH, file, JSON parser, or
  Capability Index binding is involved.

---

## 14. Verification

Targeted:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context_renderer.py
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
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py
```

Static/scope checks:

- `git diff --check`;
- production diff limited to
  `mcp_server/src/rook/agent/local_worker_turn_context.py`;
- new test file
  `mcp_server/tests/test_local_worker_turn_context_renderer.py`;
- existing `test_local_worker_turn_context.py` edit limited to public `__all__`
  expectation if needed;
- no LM5B-G production edits;
- no Capability Index production edits;
- no native/managed changes;
- function-scoped AST guard for renderer/helpers;
- no model, RookChat, prompt, dispatcher, stream, runtime, compiler, response
  loader, file, JSON parser, YAML, or Capability Index imports/calls in renderer
  helpers.

No live test. No model test. No RookChat test. No stream test. No file or JSON
parser test. No Capability Index test.

---

## 15. Explicit Non-Goals

LM5H does not add:

- context payload loader;
- response payload loader;
- response schema in the context payload;
- prompt rendering;
- model calls;
- model adapters;
- RookChat integration;
- Capability Index binding;
- gateway/tripwire logic;
- raw text parsing;
- JSON text parsing;
- JSON canonicalization;
- YAML parsing;
- file or path loading;
- schema files;
- context fingerprinting;
- run ids or timestamps;
- action catalog lookup;
- action execution;
- tool dispatch;
- graph mutation;
- stream continuation;
- disposition, harness, or scenario report helpers;
- scenario runners;
- retry, fallback, critic, or oversight loops;
- OpenProse dependencies.

LM5H is only the strict, deterministic renderer from an already-constructed
LM5A context artifact into a JSON-ready outbound context payload.
