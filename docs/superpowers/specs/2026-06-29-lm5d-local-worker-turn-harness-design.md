# LM5D - Local Worker Turn Harness Design

**Date:** 2026-06-29
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 worker boundary
**Predecessors:** LM5A local worker turn context, LM5B local worker response contract, LM5C local worker response disposition

---

## 1. Goal

LM5D introduces the smallest production seam that runs one deterministic local
worker turn.

LM5A defined what a future local/internal worker may see. LM5B defined what a
worker may say back and how Rook records admissibility. LM5C defined the
deterministic disposition of that admissibility attempt.

LM5D answers:

```text
How does Rook invoke one bounded worker callable and record the activation
outcome without becoming an orchestration loop?
```

The target shape is:

```text
LocalWorkerTurnContext
-> LocalWorkerTurnWorker(context)
-> LocalWorkerTurnResponse
-> dispose_local_worker_turn_response(context, response)
-> LocalWorkerTurnHarnessRecord
```

The hinge is strict: **one worker call exactly once**.

LM5D is model-free. It does not render prompts, call RookChat, dispatch tools,
mutate graphs, continue streams, retry, fallback, ask a critic, perform
oversight, authorize actions, or execute actions. It names the future worker
activation boundary and records what happened in one turn.

---

## 2. Production Scope

Add one production module:

```text
mcp_server/src/rook/agent/local_worker_turn_harness.py
```

Add one focused test file:

```text
mcp_server/tests/test_local_worker_turn_harness.py
```

Do not edit:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
```

If implementation reveals a genuine LM5A, LM5B, or LM5C bug, treat it as a
separate finding. Do not bundle source changes to those modules casually into
LM5D.

No package-level exports are added.

---

## 3. Public Surface

The module exports exactly:

```python
__all__ = (
    "HarnessStatus",
    "LocalWorkerTurnWorker",
    "LocalWorkerTurnHarnessRecord",
    "run_local_worker_turn",
)
```

Do not export canned workers, helper functions, reason constants, status
constants, or an enum in LM5D. The tested string literals are the contract for
this slice. Constants can be promoted later only if a real worker ledger,
dispatcher, or evaluation harness consumes them enough to justify widening the
public surface.

---

## 4. Harness Status

Use lowercase schema-style strings:

```python
HarnessStatus = Literal[
    "completed",
    "invalid_response",
    "worker_error",
]
```

Status meaning:

```text
completed
  The worker callable returned a LocalWorkerTurnResponse. LM5D called LM5C and
  recorded the resulting disposition. The LM5C disposition may itself be
  "blocked"; that is still a completed harness activation.

invalid_response
  The worker callable returned, but the returned object was not a
  LocalWorkerTurnResponse. LM5D records the type failure without preserving the
  raw object and without fabricating an LM5B attempt or LM5C disposition.

worker_error
  The worker callable raised Exception. LM5D records the exception class name
  without preserving the message, traceback, or payload, and without fabricating
  an LM5B attempt or LM5C disposition.
```

`KeyboardInterrupt`, `SystemExit`, and other `BaseException` subclasses are not
harness worker errors. They propagate.

---

## 5. Worker Type

Expose the worker seam as a type alias:

```python
LocalWorkerTurnWorker = Callable[
    [LocalWorkerTurnContext],
    LocalWorkerTurnResponse,
]
```

The type alias describes a proper worker. The runtime harness still defensively
handles a callable that returns the wrong type.

No production canned workers are exported. Tests may define deterministic worker
fixtures that request a known action, request an unknown action, ask for
clarification, refuse, observe, return the wrong type, or raise.

---

## 6. Harness Record

The harness record is a compact frozen receipt:

```python
@dataclass(frozen=True)
class LocalWorkerTurnHarnessRecord:
    status: HarnessStatus
    response: LocalWorkerTurnResponse | None
    disposition: LocalWorkerTurnDispositionRecord | None
    failure: str | None
    reason: str
    context_workflow_id: str
    context_contract_fingerprint: str
```

The context anchors are copied from `context.workflow.workflow_id` and
`context.workflow.contract_fingerprint` before invoking the worker. They exist so
`invalid_response` and `worker_error` records can still point back to the
workflow artifact even though they have no LM5B attempt or LM5C disposition.

For completed turns, the record preserves the exact typed response object:

```python
record.response is response
```

The record also preserves the exact `LocalWorkerTurnDispositionRecord` returned
by LM5C:

```python
record.disposition is disposition
```

The record deliberately does not include:

- full `LocalWorkerTurnContext`;
- raw invalid worker output;
- worker callable;
- worker name or worker id;
- model id;
- run id;
- attempt id;
- context fingerprint;
- timestamp;
- duration;
- deadline or timeout;
- action id convenience field;
- response kind convenience field;
- action input;
- action rationale;
- clarification question;
- refusal reason;
- observation message or data;
- retry/fallback/critic/oversight/escalation hints;
- route-to-user or route-to-dispatcher hints;
- action authorization or execution permission.

Consumers that need response-kind or action-id details for completed turns can
read them through:

```python
record.disposition.attempt.response_kind
record.disposition.attempt.action_id
```

---

## 7. Reason Strings

Reason strings are exact and compact:

```text
completed:<disposition>
response_type_invalid:<TypeName>
worker_exception:<ExceptionClassName>
```

Examples:

```text
completed:candidate_action_request
completed:blocked
response_type_invalid:dict
response_type_invalid:NoneType
response_type_invalid:unknown_type
worker_exception:ValueError
worker_exception:unknown_exception
```

Do not append suffixes, exception messages, object reprs, tracebacks, raw worker
payload fragments, context details, or response payload details.

The `<TypeName>` / `<ExceptionClassName>` payload must be a non-empty compact
name containing only ASCII letters, digits, or underscores. Builtin and normal
Python class names therefore remain exact, for example `dict`, `NoneType`, and
`ValueError`.

If a dynamic return type has an unsafe class name, LM5D records:

```text
response_type_invalid:unknown_type
```

If a dynamic exception class has an unsafe class name, LM5D records:

```text
worker_exception:unknown_exception
```

Unsafe names must not make the harness raise while recording worker outcomes,
and they must not leak colons, whitespace, newlines, reprs, messages, or
traceback fragments into the reason.

---

## 8. Record Coherence

`LocalWorkerTurnHarnessRecord.__post_init__` enforces coherence. A public record
constructor is allowed, but impossible harness receipts are rejected.

Validation order:

```text
1. status type check
2. response type-or-None check
3. disposition type-or-None check
4. failure type-or-None check
5. reason non-empty string check
6. context_workflow_id non-empty string check
7. context_contract_fingerprint non-empty string check
8. status literal check
9. status-specific coherence
```

Error taxonomy:

```text
TypeError:
- status is not str
- response is neither LocalWorkerTurnResponse nor None
- disposition is neither LocalWorkerTurnDispositionRecord nor None
- failure is neither str nor None
- reason is not str
- context_workflow_id is not str
- context_contract_fingerprint is not str

ValueError:
- reason is empty
- context_workflow_id is empty
- context_contract_fingerprint is empty
- status is an unknown string
- fields contradict the status-specific coherence rules
```

### Completed Records

If `status == "completed"`:

```text
response is LocalWorkerTurnResponse
disposition is LocalWorkerTurnDispositionRecord
failure is None
reason == f"completed:{disposition.disposition}"
disposition.attempt.context_workflow_id == context_workflow_id
disposition.attempt.context_contract_fingerprint == context_contract_fingerprint
```

Do not require `disposition.disposition != "blocked"`. A blocked LM5C
disposition means the typed response was deterministically refused by the gate;
the worker activation itself completed.

### Invalid Response Records

If `status == "invalid_response"`:

```text
response is None
disposition is None
failure == "response_type_invalid"
reason == "response_type_invalid:<TypeName>"
```

`<TypeName>` is the returned object's class name when that class name is a safe
reason payload, for example `dict`, `NoneType`, or `object`. Unsafe dynamic type
names normalize to `unknown_type`. The reason must not include a repr or payload.

### Worker Error Records

If `status == "worker_error"`:

```text
response is None
disposition is None
failure == "worker_exception"
reason == "worker_exception:<ExceptionClassName>"
```

`<ExceptionClassName>` is the raised exception class name when that class name
is a safe reason payload. Unsafe dynamic exception class names normalize to
`unknown_exception`. The reason must not include the exception message or
traceback.

---

## 9. Harness Function

Expose one public activation function:

```python
def run_local_worker_turn(
    context: LocalWorkerTurnContext,
    worker: LocalWorkerTurnWorker,
) -> LocalWorkerTurnHarnessRecord:
    ...
```

Validation before invocation:

```text
context is not LocalWorkerTurnContext -> TypeError
worker is not callable -> TypeError
```

Runtime flow:

```python
workflow_id = context.workflow.workflow_id
contract_fingerprint = context.workflow.contract_fingerprint

try:
    response = worker(context)
except Exception as exc:
    return worker_error_record(...)

if not isinstance(response, LocalWorkerTurnResponse):
    return invalid_response_record(...)

disposition = dispose_local_worker_turn_response(context, response)
return completed_record(...)
```

Pins:

- read context anchors before invoking the worker;
- call `worker(context)` exactly once;
- pass the exact context object to the worker;
- catch only `Exception` from the worker call;
- do not catch `BaseException`;
- do not place LM5C inside the worker-exception `try` block;
- if `dispose_local_worker_turn_response(...)` raises after a typed response,
  LM5D lets the exception propagate;
- do not fabricate an LM5B attempt or LM5C disposition for worker exceptions or
  non-response returns.

This catch boundary is deliberate:

```text
worker raises Exception -> worker_error
worker returns junk -> invalid_response
LM5C/LM5B raises after typed response -> propagate
```

LM5D records worker activation outcomes. It does not hide harness integration
bugs as worker failures.

No public partial helpers are added. Do not expose:

- `classify_worker_result(...)`;
- `record_worker_exception(...)`;
- `harness_record_from_response(...)`;
- any attempt-only or response-only harness helper.

Private helpers may exist to keep the implementation readable.

---

## 10. Imports And Boundary

Allowed production imports:

```python
from dataclasses import dataclass
from typing import Callable, Literal

from rook.agent.local_worker_turn_context import LocalWorkerTurnContext
from rook.agent.local_worker_turn_response import LocalWorkerTurnResponse
from rook.agent.local_worker_turn_disposition import (
    LocalWorkerTurnDispositionRecord,
    dispose_local_worker_turn_response,
)
```

`typing.Any` is allowed only if the implementation needs a temporary annotation
for the raw worker return before classification. The harness record must never
store raw invalid worker output.

Production LM5D must not import:

- LM4 workflow/compiler/provenance modules;
- `compile_workflow_contract`;
- `snapshot_workflow_contract`;
- `load_workflow_contract_payload`;
- current-step stream, runner, selector, mapper, revalidator, or executor
  modules/functions;
- `CatalogCurrentStepProvider`;
- `WorkflowProvenanceEnvelopeSource`;
- `PlanGraph`;
- `CurrentStepRecord`;
- `EnvelopeSupplyRecord`;
- `WorkerAllowedAction`;
- RookChat, model, LiteLLM, OpenAI, server, dispatcher, or base agent surfaces;
- MCP/Rhino/Grasshopper live execution surfaces;
- `json`, `yaml`, `Path`, `open`, or file/text parsing helpers;
- timing, asyncio, threading, retry, fallback, critic, or oversight machinery.

Tests may import LM4 workflow compiler/context fixtures for the integration
proof. Production may not.

---

## 11. Tests

Add:

```text
mcp_server/tests/test_local_worker_turn_harness.py
```

### Unit Coverage

Unit tests should use minimal hand-built `LocalWorkerTurnContext` values for most
branches.

Required cases:

- public `__all__` exports exactly the four LM5D names;
- `LocalWorkerTurnHarnessRecord` is frozen and has exactly the seven fields;
- coherent direct construction succeeds for:
  - completed candidate action;
  - completed blocked disposition;
  - invalid response;
  - worker error;
- incoherent direct construction rejects:
  - wrong scalar/object field types;
  - unknown status;
  - completed without response;
  - completed without disposition;
  - completed with failure;
  - completed reason mismatch;
  - completed anchor mismatch against disposition attempt;
  - invalid-response with response or disposition;
  - invalid-response wrong failure;
  - invalid-response wrong reason shape;
  - invalid-response reason with colon, whitespace, or newline payload;
  - worker-error with response or disposition;
  - worker-error wrong failure;
  - worker-error wrong reason shape;
  - worker-error reason with colon, whitespace, or newline payload;
- bad harness API inputs raise `TypeError`:
  - non-`LocalWorkerTurnContext` context;
  - non-callable worker;
- worker is called exactly once with the exact context object;
- allowed-action worker returns typed response:
  - `status == "completed"`;
  - disposition is `candidate_action_request`;
  - reason is `completed:candidate_action_request`;
  - `record.response is response`;
- unknown-action worker returns typed response:
  - `status == "completed"`;
  - disposition is `blocked`;
  - reason is `completed:blocked`;
- clarification/refusal/observation workers complete with matching LM5C
  dispositions and reason strings;
- non-response returns produce:
  - `status == "invalid_response"`;
  - `failure == "response_type_invalid"`;
  - exact reason such as `response_type_invalid:dict`;
  - no raw invalid output stored;
- unsafe non-response type names produce
  `reason == "response_type_invalid:unknown_type"` and do not leak the unsafe
  name;
- worker `Exception` produces:
  - `status == "worker_error"`;
  - `failure == "worker_exception"`;
  - exact reason such as `worker_exception:ValueError`;
  - no exception message or traceback stored;
- unsafe worker exception class names produce
  `reason == "worker_exception:unknown_exception"` and do not leak the unsafe
  name;
- `KeyboardInterrupt` and `SystemExit` propagate;
- monkeypatched LM5C returns a known disposition and the harness preserves the
  exact disposition object;
- monkeypatched LM5C raises after a typed response and the exception propagates;
- AST/import boundary proves production LM5D imports only the allowed surfaces
  and contains no model/chat/prompt, compiler, stream/runtime, dispatch/tool,
  graph mutation, retry/fallback/critic/oversight, JSON/YAML/file, timing, or
  payload-freezing machinery.

### Integration Proof

Include one small offline integration test:

```text
RookWorkflowContract
-> compile_workflow_contract
-> build_local_worker_turn_context
-> deterministic worker returns allowed WorkerActionRequest
-> run_local_worker_turn
```

Assertions:

- status is `completed`;
- disposition is `candidate_action_request`;
- `record.response` is the exact worker response;
- `record.disposition.attempt.context_workflow_id` equals
  `context.workflow.workflow_id`;
- `record.disposition.attempt.context_contract_fingerprint` equals
  `context.workflow.contract_fingerprint`;
- `record.context_workflow_id` and `record.context_contract_fingerprint` match
  the same context anchors.

No stream runner, live Rhino/GH, RookChat, or model is involved.

---

## 12. Verification

Targeted:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_harness.py -q
```

Nearby LM5 regression:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_harness.py `
  mcp_server/tests/test_local_worker_turn_disposition.py `
  mcp_server/tests/test_local_worker_turn_response.py `
  mcp_server/tests/test_local_worker_turn_context.py `
  -q
```

Focused PlanGraph/local-worker gate:

```powershell
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' | Sort-Object Name | ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  -q
```

Static/scope checks:

- `git diff --check`;
- production diff is exactly
  `mcp_server/src/rook/agent/local_worker_turn_harness.py`;
- no LM5A/B/C production source diffs;
- no `base_agent.py`, `src/Rook`, `src/RookNative`, or
  `knowledge/gh/operations_knowledge.json` drift;
- AST/import guard over `local_worker_turn_harness.py`.

No live test, model test, RookChat test, or stream test belongs to LM5D.

---

## 13. Non-Goals

LM5D does not add:

- local model calls;
- prompt rendering;
- RookChat integration;
- raw worker payload parsing;
- response serialization;
- action input schema validation;
- action authorization;
- action dispatch or execution;
- graph mutation;
- stream continuation;
- retry-with-learning;
- fallback-chain;
- worker-critic;
- oversight;
- timing, timeouts, or budgets;
- worker IDs, model IDs, run IDs, attempt IDs, or harness record fingerprints;
- canned production workers;
- edits to LM5A, LM5B, or LM5C production source.

LM5D is only the deterministic one-turn harness around a callable worker and the
already-landed LM5A/B/C artifacts.
