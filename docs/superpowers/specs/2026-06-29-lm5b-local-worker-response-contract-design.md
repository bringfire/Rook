# LM5B - Local Worker Response Contract Design

**Date:** 2026-06-29
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker boundary
**Predecessor:** LM5A local worker turn context, PR #376

---

## 1. Goal

LM5B defines the deterministic output side of the local/internal worker box.

LM5A answered:

```text
What may a future worker see?
```

LM5B answers:

```text
What may a future worker say back, and how does Rook record whether that response is structurally admissible?
```

The target conceptual shape is:

```text
LocalWorkerTurnContext
-> future worker reasoning, not implemented in LM5B
-> LocalWorkerTurnResponse
-> deterministic validation / attempt record
```

The worker response is evidence from one bounded transform. It is not authority
to execute, mutate a graph, continue a stream, retry, fallback, or declare
success. LM5B records admissibility only.

---

## 2. Production Scope

Add one production module:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
```

Add one focused test file:

```text
mcp_server/tests/test_local_worker_turn_response.py
```

Do not edit:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
```

If implementation reveals a genuine LM5A bug, treat it as a separate finding.
Do not bundle LM5A source changes casually into LM5B.

No package-level exports are added.

---

## 3. Public Surface

The module exports exactly:

```python
__all__ = (
    "LocalWorkerTurnResponse",
    "LocalWorkerTurnAttemptRecord",
    "WorkerActionRequest",
    "WorkerClarificationRequest",
    "WorkerRefusal",
    "WorkerObservation",
    "WorkerResponseKind",
    "WorkerRefusalCategory",
    "WorkerResponseValidationFailure",
    "validate_local_worker_turn_response",
)
```

`WorkerResponsePayload` may exist as a module-local or public type alias for
implementation readability, but it is not exported in `__all__` in LM5B.

Do not export stable reason constants in LM5B. Reason strings are part of the
tested contract, but exported constants can wait until a consumer needs them.

---

## 4. Response Kinds And Taxonomies

Use lowercase, schema-style vocabulary for audit fields. Do not use Python class
names in attempt records.

```python
WorkerResponseKind = Literal[
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
]

WorkerRefusalCategory = Literal[
    "unsafe",
    "insufficient_context",
    "unsupported_action",
    "out_of_scope",
]

WorkerResponseValidationFailure = Literal[
    "payload_invalid",
    "unknown_action_id",
    "action_input_invalid",
]
```

Response-kind mapping:

```text
WorkerActionRequest -> "action_request"
WorkerClarificationRequest -> "clarification_request"
WorkerRefusal -> "refusal"
WorkerObservation -> "observation"
```

`unknown_action_id` is the only normal invalid worker-content path. The other
failure values are defensive guards for post-construction corruption or bypassed
constructors.

---

## 5. Response Payload Dataclasses

All public dataclasses are frozen.

```python
@dataclass(frozen=True)
class WorkerActionRequest:
    action_id: str
    rationale: str
    input: Mapping[str, Any]


@dataclass(frozen=True)
class WorkerClarificationRequest:
    question: str
    rationale: str | None = None


@dataclass(frozen=True)
class WorkerRefusal:
    category: WorkerRefusalCategory
    reason: str


@dataclass(frozen=True)
class WorkerObservation:
    message: str
    data: Mapping[str, Any] | None = None


WorkerResponsePayload = (
    WorkerActionRequest
    | WorkerClarificationRequest
    | WorkerRefusal
    | WorkerObservation
)


@dataclass(frozen=True)
class LocalWorkerTurnResponse:
    payload: WorkerResponsePayload
```

### Constructor Responsibilities

Constructors validate and freeze ordinary shape safety. A response object should
be safe as soon as it exists, before the validator sees it.

`WorkerActionRequest.__post_init__`:

- `action_id`: non-empty string;
- `rationale`: non-empty string;
- `input`: JSON-shaped mapping, recursively frozen.

`WorkerClarificationRequest.__post_init__`:

- `question`: non-empty string;
- `rationale`: string or `None`.

No structured answer options are included in LM5B. Options introduce UI/form
semantics and should wait for a later interaction slice.

`WorkerRefusal.__post_init__`:

- `category`: one of `WorkerRefusalCategory`;
- `reason`: non-empty string.

No free-form refusal categories are allowed.

`WorkerObservation.__post_init__`:

- `message`: non-empty string;
- `data`: `None` or JSON-shaped mapping, recursively frozen.

`LocalWorkerTurnResponse.__post_init__`:

- `payload` must be exactly one of the closed response dataclasses;
- no raw dict;
- no list/tuple of responses;
- no `None`.

LM5B supports exactly one response item per worker turn.

---

## 6. Attempt Record

The response object is what the worker said. The attempt record is Rook's
deterministic validation receipt.

```python
@dataclass(frozen=True)
class LocalWorkerTurnAttemptRecord:
    valid: bool
    response_kind: WorkerResponseKind | None
    failure: WorkerResponseValidationFailure | None
    reason: str
    action_id: str | None
    context_workflow_id: str
    context_contract_fingerprint: str
```

The attempt record contains compact facts only.

It does not include:

- full response payload;
- action input copy;
- observation data copy;
- clarification question copy;
- refusal reason copy;
- selected template id;
- provider id;
- compiler id;
- max steps;
- attempt id;
- response fingerprint;
- timestamp;
- model id;
- worker id;
- run id;
- serialization schema.

`context_workflow_id` and `context_contract_fingerprint` anchor the attempt to
the workflow artifact. The caller still has the full `LocalWorkerTurnContext`
and `LocalWorkerTurnResponse` objects if more detail is needed.

---

## 7. Validator

Public validator:

```python
def validate_local_worker_turn_response(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnAttemptRecord:
    ...
```

The validator returns only the attempt record. It does not return a wrapper
containing the context or response.

### API Input Errors

Raise `TypeError` for malformed API inputs:

- `context` is not `LocalWorkerTurnContext`;
- `response` is not `LocalWorkerTurnResponse`.

### Worker-Content Validation

For worker-content invalidity, return an invalid attempt record rather than
raising.

Valid response records:

```text
WorkerActionRequest with known action_id:
  valid=True
  response_kind="action_request"
  failure=None
  reason="valid_action_request"
  action_id=<action_id>

WorkerClarificationRequest:
  valid=True
  response_kind="clarification_request"
  failure=None
  reason="valid_clarification_request"
  action_id=None

WorkerRefusal:
  valid=True
  response_kind="refusal"
  failure=None
  reason="valid_refusal"
  action_id=None

WorkerObservation:
  valid=True
  response_kind="observation"
  failure=None
  reason="valid_observation"
  action_id=None
```

Unknown action id:

```text
valid=False
response_kind="action_request"
failure="unknown_action_id"
reason="unknown_action_id:<action_id>"
action_id=<action_id>
```

Contexts with no allowed actions are valid validator inputs. In that case:

- clarification/refusal/observation can still be valid;
- every action request is invalid with `unknown_action_id:<id>`.

### Defensive Invalid Records

Constructors should catch ordinary shape errors. The validator still defensively
handles post-construction mutation or bypassed construction.

If `response.payload` is not one of the closed response dataclass types:

```text
valid=False
response_kind=None
failure="payload_invalid"
reason="payload_invalid:<detail>"
action_id=None
```

If a `WorkerActionRequest` payload exists but its `input` is no longer a mapping
or has become otherwise malformed after construction bypass:

```text
valid=False
response_kind="action_request"
failure="action_input_invalid"
reason="action_input_invalid:<detail>"
action_id=<action_id if string else None>
```

The validator does not validate action `input` against
`WorkerAllowedAction.input_schema`. LM5B records the requested input shape only.
Schema validation belongs in a later deterministic action-admissibility slice.

---

## 8. Action Request Semantics

`WorkerActionRequest.action_id` must reference an allowed action from the
provided `LocalWorkerTurnContext`.

Validation rule:

```python
action_id in {action.action_id for action in context.allowed_actions}
```

The worker may not:

- invent an action;
- name execution refs;
- name MCP tools;
- mutate graph state;
- treat an action request as execution permission.

`WorkerActionRequest.rationale` is observational only. It does not authorize the
request or grant execution authority.

`WorkerActionRequest.input` is a frozen JSON-shaped mapping. It is not executed,
not schema-validated, and not applied to graph state by LM5B.

---

## 9. JSON Freezing

LM5B uses a local private `_freeze_json_value(...)` helper. Do not import LM5A
private helpers.

Rules:

- mappings require string keys and return `types.MappingProxyType` around copied
  dictionaries;
- `list | tuple` values become tuples recursively;
- `str`, `bool`, `int`, finite `float`, and `None` are allowed;
- non-finite floats are rejected;
- arbitrary objects and callables are rejected.

Public mapping fields are typed as `Mapping[str, Any]`; the concrete immutable
mapping type is an implementation detail.

`WorkerActionRequest.input` and `WorkerObservation.data` must be detached from
caller-owned containers after construction.

---

## 10. Import And Authority Boundary

Allowed production imports:

- `collections.abc.Mapping`;
- `dataclasses`;
- `math`;
- `types.MappingProxyType`;
- typing helpers, including `Any` and `Literal`;
- `LocalWorkerTurnContext` from `rook.agent.local_worker_turn_context`.

Do not import `WorkerAllowedAction` unless implementation proves a type
annotation truly requires it. The validator should inspect
`context.allowed_actions` by field.

The production module must not import or call:

- `propose_next_node`;
- `map_accepted_proposal_to_step`;
- `revalidate_proposal`;
- `execute_mapped_step`;
- `run_current_mapped_step`;
- `run_current_step_stream`;
- `EnvelopeSupplyResult`;
- `CurrentStepRecord`;
- `EnvelopeSupplyRecord`;
- `PlanGraph`;
- `CompiledWorkflowScaffold`;
- `CatalogCurrentStepProvider`;
- `WorkflowProvenanceEnvelopeSource`;
- `compile_workflow_contract`;
- `load_workflow_contract_payload`;
- `snapshot_workflow_contract`;
- `RookAgent`;
- `base_agent`;
- RookChat surfaces;
- dispatcher or tool execution surfaces;
- live Rhino/GH runner surfaces;
- graph mutation helpers;
- file IO, `Path`, or `open`;
- `json`, `json.loads`, `json.dumps`, YAML, OpenAI, litellm, or model provider
  imports.

Integration tests may import LM5A builder and workflow compiler helpers.
Production may not.

---

## 11. Tests

Create:

```text
mcp_server/tests/test_local_worker_turn_response.py
```

### Unit Coverage

Tests should cover:

- public `__all__` surface;
- all public dataclasses are frozen;
- `WorkerActionRequest` validates non-empty fields and freezes/detaches `input`;
- `WorkerClarificationRequest` validates non-empty question and optional
  rationale type;
- `WorkerRefusal` validates closed category taxonomy and non-empty reason;
- `WorkerObservation` validates non-empty message and freezes/detaches optional
  data;
- `LocalWorkerTurnResponse` accepts exactly one closed payload dataclass;
- `LocalWorkerTurnResponse` rejects raw dict, list/tuple, `None`, and arbitrary
  objects;
- `validate_local_worker_turn_response` raises `TypeError` for wrong context or
  response API inputs;
- valid action request produces `valid_action_request`;
- unknown action id produces invalid record with `failure="unknown_action_id"`;
- a context with no allowed actions still validates clarification/refusal/
  observation and invalidates action requests;
- valid clarification/refusal/observation produce stable valid reasons;
- defensive post-construction payload corruption produces `payload_invalid`;
- defensive post-construction action input corruption produces
  `action_input_invalid`;
- attempt records include only compact fields and do not copy full response
  payloads;
- response kinds use lowercase schema-style strings;
- boundary/import guard forbids runtime/model/file/JSON/compile/stream surfaces.

### Offline Integration Test

Include one small deterministic integration proof:

```text
RookWorkflowContract
-> compile_workflow_contract
-> build_local_worker_turn_context
-> WorkerActionRequest
-> validate_local_worker_turn_response
```

The integration test may reuse the known repair workflow fixture style from
LM5A/LM4 tests.

Assert:

- valid action request references the action id from the real
  `LocalWorkerTurnContext.allowed_actions`;
- attempt record is valid;
- attempt record `context_workflow_id` equals `context.workflow.workflow_id`;
- attempt record `context_contract_fingerprint` equals
  `context.workflow.contract_fingerprint`;
- no stream, model, live Rhino/GH, RookChat, or dispatch occurs.

---

## 12. Verification And Gates

Targeted:

```text
pytest mcp_server/tests/test_local_worker_turn_response.py -q
```

Nearby:

```text
pytest \
  mcp_server/tests/test_local_worker_turn_response.py \
  mcp_server/tests/test_local_worker_turn_context.py \
  mcp_server/tests/test_plan_graph_workflow_contract.py \
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py \
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py \
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py \
  mcp_server/tests/test_plan_graph_workflow_provenance.py \
  -q
```

Focused:

```text
test_plan_graph*.py
test_local_worker_turn_context.py
test_local_worker_turn_response.py
```

Static:

- `git diff --check`;
- production diff is exactly
  `mcp_server/src/rook/agent/local_worker_turn_response.py`;
- no diff in `mcp_server/src/rook/agent/local_worker_turn_context.py`;
- no `base_agent.py`, chat panel, server, dispatcher, model, live Rhino/GH,
  stream-runner, or compiler/loader changes;
- AST/import guard over `local_worker_turn_response.py` for banned runtime,
  model, file, JSON/YAML, compile/load/snapshot, selector/mapper/revalidator/
  executor, graph, record, and stream surfaces.

No live test. No model test. No RookChat test.

---

## 13. Deliberate Non-Goals

LM5B does not add:

- model calls;
- prompt rendering;
- raw worker payload mapping loader;
- JSON text parser;
- YAML/file loader;
- RookChat integration;
- tool execution;
- graph mutation;
- stream continuation;
- selector/revalidator/mapper/executor calls;
- action acceptance as execution permission;
- action input schema validation;
- retry loop;
- critic loop;
- fallback chain;
- oversight loop;
- worker id/model id/run id;
- attempt id;
- response fingerprint;
- timestamp;
- serialization schema;
- edits to LM5A source.

LM5B defines only the typed worker response artifact and Rook's deterministic
admissibility record for one response against one `LocalWorkerTurnContext`.
