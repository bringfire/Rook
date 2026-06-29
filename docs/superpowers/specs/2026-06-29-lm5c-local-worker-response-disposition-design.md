# LM5C - Local Worker Response Disposition Design

**Date:** 2026-06-29
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker boundary
**Predecessors:** LM5A local worker turn context, LM5B local worker response contract

---

## 1. Goal

LM5C defines the deterministic disposition gate after a local/internal worker
response has been expressed through LM5B.

LM5A answered:

```text
What may a future worker see?
```

LM5B answered:

```text
What may a future worker say, and is it admissible for the context?
```

LM5C answers:

```text
What deterministic gate bucket records the result of that admissibility attempt?
```

The target shape is:

```text
LocalWorkerTurnContext
+ LocalWorkerTurnResponse
-> validate_local_worker_turn_response(context, response)
-> LocalWorkerTurnAttemptRecord
-> LocalWorkerTurnDispositionRecord
```

LM5C is a receipt layer. It records the deterministic disposition of the worker
response. It does not route, execute, retry, fallback, ask a critic, escalate,
authorize actions, or continue the workflow stream.

---

## 2. Production Scope

Add one production module:

```text
mcp_server/src/rook/agent/local_worker_turn_disposition.py
```

Add one focused test file:

```text
mcp_server/tests/test_local_worker_turn_disposition.py
```

Do not edit:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_response.py
```

If implementation reveals a genuine LM5A or LM5B bug, treat it as a separate
finding. Do not bundle context or response source changes casually into LM5C.

No package-level exports are added.

---

## 3. Public Surface

The module exports exactly:

```python
__all__ = (
    "WorkerResponseDisposition",
    "LocalWorkerTurnDispositionRecord",
    "dispose_local_worker_turn_response",
)
```

Do not export disposition constants, reason constants, or an enum in LM5C. The
tested string literals are the contract for this slice. Constants can be
promoted later if a real dispatcher, router, evaluator, or action gate consumes
them enough to justify widening the public surface.

---

## 4. Disposition Vocabulary

Use lowercase schema-style strings:

```python
WorkerResponseDisposition = Literal[
    "blocked",
    "candidate_action_request",
    "clarification_needed",
    "refusal_recorded",
    "observation_recorded",
]
```

`blocked` is the disposition for any returned LM5B attempt where
`attempt.valid is False`. There is no separate `invalid_response` disposition.
Invalidity is a source condition from LM5B; LM5C records the gate bucket.

The other dispositions are valid-attempt buckets:

```text
action_request -> candidate_action_request
clarification_request -> clarification_needed
refusal -> refusal_recorded
observation -> observation_recorded
```

---

## 5. Disposition Record

The disposition record is a compact frozen receipt:

```python
@dataclass(frozen=True)
class LocalWorkerTurnDispositionRecord:
    disposition: WorkerResponseDisposition
    attempt: LocalWorkerTurnAttemptRecord
    response_kind: WorkerResponseKind | None
    action_id: str | None
    reason: str
```

The nested `LocalWorkerTurnAttemptRecord` is the canonical LM5B admissibility
truth. LM5C owns the disposition truth.

The record deliberately does not include:

- `LocalWorkerTurnResponse`;
- `WorkerActionRequest`;
- action input;
- action rationale;
- action input schema;
- clarification question;
- refusal reason;
- observation message;
- observation data;
- `LocalWorkerTurnContext`;
- workflow/provider/compiler details beyond the nested attempt;
- `valid`, `allowed`, `should_continue`, or `actionable` booleans;
- retry/fallback/critic/oversight/escalation hints;
- route-to-user or route-to-dispatcher hints;
- attempt id;
- disposition id;
- response fingerprint;
- timestamp;
- model id;
- worker id;
- run id;
- serialization schema.

The caller still has the original context and response objects. LM5C does not
duplicate them into the gate receipt.

---

## 6. Record Coherence

`LocalWorkerTurnDispositionRecord.__post_init__` enforces coherence. A public
record constructor is allowed, but impossible disposition receipts are rejected.

Validation order:

```text
1. attempt type check
2. disposition type check
3. response_kind type-or-None check
4. action_id type-or-None check
5. reason non-empty string check
6. disposition literal check
7. mirror checks:
   response_kind == attempt.response_kind
   action_id == attempt.action_id
8. disposition/reason/action coherence by attempt.valid + attempt.response_kind
```

Error taxonomy:

```text
TypeError:
- attempt is not LocalWorkerTurnAttemptRecord
- disposition is not str
- response_kind is not str | None
- action_id is not str | None
- reason is not str

ValueError:
- reason is empty
- disposition is an unknown string
- response_kind does not match attempt.response_kind
- action_id does not match attempt.action_id
- disposition/reason contradict attempt.valid or attempt.response_kind
```

The mirror checks are required before disposition-specific checks. They preserve
the nested LM5B attempt as canonical truth:

```text
response_kind == attempt.response_kind
action_id == attempt.action_id
```

### Coherence Rules

If `attempt.valid is False`:

```text
disposition == "blocked"
response_kind == attempt.response_kind
action_id == attempt.action_id
reason == f"blocked:{attempt.reason}"
```

This preserves the LM5B source condition without interpretation. For example,
an unknown action remains visibly:

```text
blocked:unknown_action_id:<id>
```

If `attempt.valid is True` and `attempt.response_kind == "action_request"`:

```text
disposition == "candidate_action_request"
action_id is a non-empty string
reason == f"candidate_action_request:{action_id}"
```

If `attempt.valid is True` and `attempt.response_kind == "clarification_request"`:

```text
disposition == "clarification_needed"
action_id is None
reason == "clarification_needed"
```

If `attempt.valid is True` and `attempt.response_kind == "refusal"`:

```text
disposition == "refusal_recorded"
action_id is None
reason == "refusal_recorded"
```

If `attempt.valid is True` and `attempt.response_kind == "observation"`:

```text
disposition == "observation_recorded"
action_id is None
reason == "observation_recorded"
```

LM5B already enforces valid-attempt response-kind coherence. LM5C still treats an
unrecognized valid response kind as a `ValueError` if one is somehow supplied
through a future or bypassed attempt shape.

---

## 7. Public Function

The only public function is:

```python
def dispose_local_worker_turn_response(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnDispositionRecord:
    attempt = validate_local_worker_turn_response(context, response)
    return _disposition_from_attempt(attempt)
```

This is the only public disposition seam. LM5C does not expose a public
attempt-only disposal function, because accepting arbitrary attempt records would
allow callers to detach LM5C from the actual `(context, response)` pair.

The private helper may exist:

```python
def _disposition_from_attempt(
    attempt: LocalWorkerTurnAttemptRecord,
) -> LocalWorkerTurnDispositionRecord:
    # maps one validated attempt to one coherent disposition record
```

The private helper should lightly validate its input type:

```python
if not isinstance(attempt, LocalWorkerTurnAttemptRecord):
    raise TypeError("attempt must be LocalWorkerTurnAttemptRecord")
```

It remains private and is not exported.

---

## 8. Delegation And Error Handling

LM5C delegates all context-dependent admissibility to LM5B:

```python
attempt = validate_local_worker_turn_response(context, response)
```

LM5C must not inspect:

- `context.allowed_actions`;
- `context.workflow`;
- `context.current_node`;
- `context.current_graph`;
- `context.history`;
- `context.knowledge`.

LM5B owns action-id validation and workflow anchoring through its attempt record.
LM5C owns only attempt-to-disposition mapping.

If LM5B raises `TypeError` for malformed API inputs, LM5C lets the exception
propagate:

```text
dispose_local_worker_turn_response(bad_context, response)
-> TypeError from validate_local_worker_turn_response

dispose_local_worker_turn_response(context, bad_response)
-> TypeError from validate_local_worker_turn_response
```

LM5C does not catch and rewrap API errors, and it does not fabricate a `blocked`
record without a real LM5B attempt. `blocked` is for invalid worker responses
with a returned attempt record, not for bad API calls.

---

## 9. Reason Strings

LM5C reason strings are compact and stable:

```text
blocked:<attempt.reason>
candidate_action_request:<action_id>
clarification_needed
refusal_recorded
observation_recorded
```

Reason strings must not include:

- clarification question;
- refusal reason;
- observation message;
- action rationale;
- action input;
- input schema details;
- current node;
- workflow/provider/compiler details.

LM5C records enough to compose and audit the gate result. It does not duplicate
the original response or context.

---

## 10. Import And Authority Boundary

Allowed production imports:

- `dataclasses.dataclass`;
- `typing.Literal`;
- `LocalWorkerTurnContext` from LM5A;
- `LocalWorkerTurnAttemptRecord`, `LocalWorkerTurnResponse`,
  `WorkerResponseKind`, and `validate_local_worker_turn_response` from LM5B.

LM5C should not need:

- `Any`;
- `Mapping`;
- `MappingProxyType`;
- `math`;
- JSON/freezing helpers;
- serialization helpers.

The production module must not import or call:

- `WorkerAllowedAction`;
- LM4 compiler/load/snapshot functions;
- LM4 selector, mapper, revalidator, executor, stream runner, or provider;
- `PlanGraph`;
- current-step records or supply records;
- `EnvelopeSupplyResult`;
- `RookAgent`;
- `base_agent`;
- RookChat surfaces;
- dispatcher or tool execution surfaces;
- live Rhino/GH runner surfaces;
- graph mutation helpers;
- file IO, `Path`, or `open`;
- `json`, `json.loads`, `json.dumps`, YAML, OpenAI, litellm, or model provider
  imports.

No payload freezing machinery belongs in LM5C. LM5A and LM5B already own payload
immutability for their artifacts.

---

## 11. Tests

Create:

```text
mcp_server/tests/test_local_worker_turn_disposition.py
```

### Unit Coverage

Tests should cover:

- exact public `__all__` surface;
- public dataclass is frozen;
- valid action response maps to `candidate_action_request`;
- valid clarification response maps to `clarification_needed`;
- valid refusal response maps to `refusal_recorded`;
- valid observation response maps to `observation_recorded`;
- unknown action id flows through LM5B and maps to:

  ```text
  attempt.failure == "unknown_action_id"
  disposition == "blocked"
  reason == "blocked:unknown_action_id:<id>"
  ```

- blocked disposition preserves `attempt.response_kind` and `attempt.action_id`;
- `LocalWorkerTurnDispositionRecord` accepts coherent direct construction;
- direct construction rejects:
  - wrong attempt type;
  - wrong scalar types;
  - empty reason;
  - unknown disposition;
  - response-kind mismatch with attempt;
  - action-id mismatch with attempt;
  - invalid attempt with non-blocked disposition;
  - blocked record with wrong reason;
  - valid action with non-action disposition;
  - valid action with missing action id;
  - valid action with wrong reason;
  - valid non-action with action id;
  - valid non-action with wrong disposition or reason;
- monkeypatched validator receives the exact context and response objects;
- monkeypatched validator result is nested as the exact `attempt` object;
- LM5B `TypeError` from malformed context or response propagates;
- module import guard forbids runtime/model/chat/file/JSON/payload/freezing
  imports and LM4 authority seams.

### Integration Coverage

Include one tiny deterministic integration proof:

```text
RookWorkflowContract
-> compile_workflow_contract
-> build_local_worker_turn_context
-> WorkerActionRequest
-> dispose_local_worker_turn_response
```

Assert:

- the response uses the real allowed action id from the LM5A context;
- disposition is `candidate_action_request`;
- nested attempt is valid;
- nested attempt anchors to `context.workflow.workflow_id`;
- nested attempt anchors to `context.workflow.contract_fingerprint`.

No stream, model, live Rhino/GH, RookChat, dispatch, or action execution occurs.

---

## 12. Verification And Gates

Targeted:

```text
pytest mcp_server/tests/test_local_worker_turn_disposition.py -q
```

Nearby:

```text
pytest \
  mcp_server/tests/test_local_worker_turn_disposition.py \
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
test_local_worker_turn_disposition.py
```

Static:

- `git diff --check`;
- production diff is exactly
  `mcp_server/src/rook/agent/local_worker_turn_disposition.py`;
- no diff in:
  - `mcp_server/src/rook/agent/local_worker_turn_context.py`;
  - `mcp_server/src/rook/agent/local_worker_turn_response.py`;
- no `base_agent.py`, chat panel, server, dispatcher, model, live Rhino/GH,
  stream-runner, compiler/loader, file/JSON/YAML parser, or payload-freezing
  changes;
- AST/import guard over `local_worker_turn_disposition.py` for banned runtime,
  model, file, JSON/YAML, compile/load/snapshot, selector/mapper/revalidator/
  executor, graph, record, stream, and payload-freezing surfaces.

No live test. No model test. No RookChat test. No stream test.

---

## 13. Deliberate Non-Goals

LM5C does not add:

- model calls;
- prompt rendering;
- raw worker payload parsing;
- serialization helpers;
- JSON text parser;
- YAML/file loader;
- RookChat integration;
- tool dispatch;
- action authorization;
- action execution;
- action input schema validation;
- graph mutation;
- stream continuation;
- selector/revalidator/mapper/executor calls;
- workflow compiler/load/snapshot calls;
- retry policy;
- fallback-chain policy;
- worker-critic policy;
- oversight policy;
- escalation/routing hints;
- route-to-user behavior;
- route-to-dispatcher behavior;
- response payload logging;
- context payload logging;
- attempt/disposition ids;
- response/disposition fingerprints;
- timestamps;
- model/worker/run ids;
- edits to LM5A or LM5B source.

LM5C is only the deterministic disposition receipt for one LM5B-validated worker
response against one LM5A context.
