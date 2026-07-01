# LM5G - Local Worker Response Loader Design

**Date:** 2026-06-30
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker boundary
**Predecessors:** LM5A local worker turn context, LM5B response contract, LM5C response disposition, LM5D one-turn harness, LM5E deterministic scenario suite, LM5F scenario evaluation

---

## 1. Goal

LM5G adds the deterministic transport boundary from an already-parsed response
payload into the typed LM5B response artifact.

LM5B intentionally accepts typed dataclasses only. Before a real local/internal
model probe, Rook needs a narrow, deterministic loader for model-like structured
output that has already been parsed into Python mappings.

The public shape is:

```python
load_local_worker_turn_response_payload(
    payload: Mapping[str, Any],
) -> LocalWorkerTurnResponse
```

LM5G answers only:

```text
Can this strict response payload become a typed LocalWorkerTurnResponse?
```

It does not answer:

```text
Is this response admissible for a specific context?
What should Rook do with the response?
Did a scenario pass?
How should a context be rendered for a model?
```

Layer split:

```text
LM5G: parsed payload -> LocalWorkerTurnResponse
LM5B: context + response -> LocalWorkerTurnAttemptRecord
LM5C: attempt -> disposition
LM5D: one-turn harness
LM5F: scenario evaluation
```

---

## 2. Production Scope

Modify one production module:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
```

Add one focused test file:

```text
mcp_server/tests/test_local_worker_turn_response_loader.py
```

No new production module is added in LM5G. The loader is specifically a
transport boundary into LM5B's response dataclasses, so it belongs beside those
dataclasses for this slice.

Do not edit:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
```

If implementation reveals a genuine bug in LM5A-F, treat that as a separate
finding rather than bundling a fix into LM5G.

No package-level exports are added.

---

## 3. Public Surface

Add exactly two public exports to `local_worker_turn_response.py`:

```python
LOCAL_WORKER_TURN_RESPONSE_SCHEMA = "rook.local_worker_turn_response:v1"

def load_local_worker_turn_response_payload(
    payload: Mapping[str, Any],
) -> LocalWorkerTurnResponse:
    ...
```

Update `__all__` to include only these new names in addition to the existing
LM5B public surface.

Do not export:

```text
KIND_KEY
ACTION_ID_KEY
RATIONALE_KEY
INPUT_KEY
FIELD_SETS
kind constants
reason constants
loader helper constants
```

Field names are part of the schema contract and are pinned by spec/tests, not by
public Python constants.

---

## 4. Accepted Payload Shape

LM5G accepts a strict, schema-tagged, flat response envelope. It does not accept
schema-less authoring shortcuts or nested `"payload"` wrappers.

All payload variants require:

```python
{
    "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    "kind": <response kind>,
    ...
}
```

Accepted response kinds are exactly the LM5B response kinds:

```text
action_request
clarification_request
refusal
observation
```

No aliases are accepted:

```text
action
tool_call
clarify
question
note
message
```

The loader dispatches only from `"kind"`. It does not infer kind from fields.

### Action Request

Required exact field set:

```python
{
    "schema",
    "kind",
    "action_id",
    "rationale",
    "input",
}
```

Loads to:

```python
LocalWorkerTurnResponse(
    WorkerActionRequest(
        action_id=payload["action_id"],
        rationale=payload["rationale"],
        input=<copied mapping>,
    )
)
```

`input` is required and must be a `Mapping`. `input=None`, scalar values, lists,
tuples, sets, and arbitrary objects are rejected with `TypeError`.

Unknown `action_id` values are loader-valid if they are non-empty strings. Action
admissibility belongs to:

```python
validate_local_worker_turn_response(context, response)
```

LM5G does not know the allowed actions for a context.

### Clarification Request

Required exact field set:

```python
{
    "schema",
    "kind",
    "question",
    "rationale",
}
```

`rationale` is required in the payload shape and may be `None`. Missing
`rationale` is a schema-shape failure, not shorthand for `None`.

### Refusal

Required exact field set:

```python
{
    "schema",
    "kind",
    "category",
    "reason",
}
```

`category` is validated by the LM5B `WorkerRefusal` constructor. LM5G does not
define a second refusal taxonomy.

### Observation

Required exact field set:

```python
{
    "schema",
    "kind",
    "message",
    "data",
}
```

`data` is required in the payload shape and may be `None`. If present as a value
other than `None`, it must be a `Mapping`. Missing `data` is a schema-shape
failure, not shorthand for `None`.

---

## 5. Field Set Discipline

Every record uses exact field-set validation before constructing LM5B
dataclasses.

Examples:

```text
unknown top-level field -> ValueError
missing schema -> ValueError
missing kind -> ValueError
missing observation.data -> ValueError
missing clarification_request.rationale -> ValueError
```

The loader does not use `**payload` construction. Each field is read explicitly
after the exact field set is validated.

---

## 6. JSON-Shaped Copy Boundary

LM5G owns the external-payload no-alias boundary. It uses local private copy
helpers rather than importing LM5A/B private helpers.

Helper behavior:

```python
def _copy_json_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        require string keys
        return {key: _copy_json_payload(item) for ...}
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json_payload(item) for item in value)
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError
```

Rules:

- top-level `payload` must be a `Mapping`;
- mapping keys must be strings everywhere;
- nested mapping values may be any `Mapping` and are copied into plain dicts;
- nested list/tuple values are accepted and normalized to tuples;
- arbitrary iterables are rejected;
- strings are scalars, not sequences;
- arbitrary objects, callables, and sets are rejected;
- non-finite floats are rejected;
- caller mapping/list/tuple containers must not alias the returned response.

LM5B constructors still perform their own response artifact validation and
freezing. This is intentional duplication at two different boundaries:

```text
LM5G: external mapping shape and safe copy
LM5B: response dataclass validity and frozen artifact coherence
```

Example:

```python
payload = {
    "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    "kind": "action_request",
    "action_id": "draft_repair_params",
    "rationale": "Use known C# body gotcha.",
    "input": {
        "pins_out": ["A:double"],
    },
}
```

The loaded response has:

```python
response.payload.input["pins_out"] == ("A:double",)
```

---

## 7. Error Taxonomy

Use the same split as LM4Y and LM5A/B.

Raise `ValueError` for invalid known values or exact-schema contradictions:

- missing required field;
- unknown extra field;
- unsupported schema string;
- unknown kind string;
- empty strings, through LM5B constructors;
- invalid refusal category, through LM5B constructors.

Raise `TypeError` for malformed shape or wrong types:

- top-level payload is not a `Mapping`;
- non-string mapping keys anywhere;
- `schema` present but not `str`;
- `kind` present but not `str`;
- `action_request.input` not a `Mapping`;
- `observation.data` present and not `Mapping | None`;
- non-JSON-safe nested values.

Missing `schema` or `kind` is `ValueError`. Present-but-non-string `schema` or
`kind` is `TypeError`.

---

## 8. Context-Free Loader

LM5G is context-free.

The loader does not accept:

```python
LocalWorkerTurnContext
```

The loader does not call:

```python
validate_local_worker_turn_response(...)
dispose_local_worker_turn_response(...)
run_local_worker_turn(...)
evaluate_local_worker_scenario_result(...)
```

Consequences:

- unknown `action_id` values load successfully if they are non-empty strings;
- allowed-action membership is checked later by LM5B validation;
- no attempt record is returned;
- no disposition record is returned;
- no harness record is returned;
- no scenario evaluation is returned.

This preserves the chain:

```text
payload -> response
context + response -> attempt
attempt -> disposition
context + worker -> harness record
expectation + harness record -> scenario result
```

---

## 9. Import And Boundary Rules

Because LM5G lives in `local_worker_turn_response.py`, the existing module may
still legitimately import `LocalWorkerTurnContext` for LM5B validation. LM5G
boundary checks must therefore be function-scoped, not module-wide.

Guard target set:

- `load_local_worker_turn_response_payload`;
- private helpers whose names start with `_load_`;
- `_copy_json_payload`;
- `_require_fields`;
- `_require_mapping`;
- `_require_string_keys`;
- any equivalent private loader helper added during implementation.

Those function bodies must not call or reference:

```text
validate_local_worker_turn_response
LocalWorkerTurnContext
dispose_local_worker_turn_response
run_local_worker_turn
evaluate_local_worker_scenario_result
build_local_worker_scenario_report
json.loads
json.dumps
Path
open
compile_workflow_contract
run_current_step_stream
run_current_mapped_step
execute_mapped_step
map_accepted_proposal_to_step
revalidate_proposal
propose_next_node
RookChat
dispatcher
model
live runtime surfaces
```

Production LM5G must not import `json`, YAML, path/file loading helpers, model
providers, prompt renderers, RookChat surfaces, dispatchers, LM4 stream/runtime
surfaces, or OpenProse packages.

Tests also do not need `json`. Use plain Python dict/list fixtures to simulate
already-parsed payloads.

---

## 10. Tests

Add:

```text
mcp_server/tests/test_local_worker_turn_response_loader.py
```

### Loader-Focused Coverage

Tests should cover:

- public `__all__` includes `LOCAL_WORKER_TURN_RESPONSE_SCHEMA` and
  `load_local_worker_turn_response_payload`;
- schema constant has value `"rook.local_worker_turn_response:v1"`;
- each of the four variants loads to the correct LM5B payload dataclass;
- flat exact field sets are required for each variant;
- missing `schema` and missing `kind` raise `ValueError`;
- non-string `schema` and non-string `kind` raise `TypeError`;
- unsupported schema string raises `ValueError`;
- unknown kind string raises `ValueError`;
- unknown extra fields raise `ValueError`;
- missing nullable fields raise `ValueError`;
- nullable fields with `None` load correctly;
- `action_request.input` must be a mapping;
- `observation.data` must be `None` or a mapping;
- non-string mapping keys raise `TypeError`;
- nested list and tuple values normalize to tuples;
- non-finite floats and arbitrary objects raise `TypeError`;
- caller mutation after load does not affect response `input` or `data`;
- unknown action ids load as typed responses and fail only later during
  context-aware validation.

### Integration Coverage

Include one small offline integration proof:

```text
payload
-> load_local_worker_turn_response_payload
-> validate_local_worker_turn_response(context, response)
-> dispose_local_worker_turn_response(context, response)
-> run_local_worker_turn(context, worker returning loaded response)
-> evaluate_local_worker_scenario_result(...)
```

The test may reuse existing LM5A-F fixture patterns and the known repair
workflow contract fixture style.

Assertions should prove:

- the loaded response is accepted by LM5B validation when its action id is
  allowed by the context;
- LM5C produces the expected disposition;
- LM5D can run a deterministic worker that returns the loaded response;
- LM5F can evaluate the resulting harness record against a compact expectation;
- no stream, live Rhino/GH, model, prompt, RookChat, file, or JSON parsing is
  involved.

### Function-Scoped Boundary Guard

The test suite should parse `local_worker_turn_response.py` with `inspect` and
`ast`, identify the LM5G loader function and private loader helper functions,
and assert those function bodies do not reference banned names.

Do not use a module-wide guard that forbids `LocalWorkerTurnContext`, because
LM5B validation already uses it legitimately in the same module.

---

## 11. Verification

Targeted:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  -q
```

Nearby:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  -q
```

Focused PlanGraph/local-worker gate:

```powershell
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  -q
```

Static/scope checks:

- `git diff --check`;
- production diff limited to
  `mcp_server/src/rook/agent/local_worker_turn_response.py`;
- test diff adds only
  `mcp_server/tests/test_local_worker_turn_response_loader.py`;
- no LM5C/D/F production edits;
- function-scoped AST/import guard for loader helpers;
- no model, RookChat, prompt, dispatcher, stream, runtime, compiler, file,
  JSON, or YAML imports/calls in loader helpers.

No live test. No model test. No RookChat test. No stream test. No file or JSON
parser test.

---

## 12. Explicit Non-Goals

LM5G does not add:

- context rendering;
- prompt building;
- model calls;
- model adapters;
- RookChat integration;
- raw text parsing;
- JSON text parsing;
- JSON canonicalization;
- YAML parsing;
- file or path loading;
- schema files;
- context-aware validation;
- action catalog lookup;
- action input schema validation;
- disposition, harness, or scenario report helpers;
- scenario runners;
- retry, fallback, critic, or oversight loops;
- action dispatch or execution;
- graph mutation;
- stream continuation;
- ArchitectProposal or Director surfaces;
- published-state stores;
- OpenProse dependencies.

LM5G is only the strict, deterministic loader from an already-parsed Rook
response payload into the existing LM5B typed response artifact.
