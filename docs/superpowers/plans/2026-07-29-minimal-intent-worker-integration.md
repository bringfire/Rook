# Minimal Intent-to-Worker Product Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one internal product path from an exact bounded user intent through one concrete Planner adapter call into the existing minimal C# repair handoff and its native terminal result.

**Architecture:** One new module owns the immutable Planner prompt snapshot, a concrete one-shot adapter over an injected structural transport, strict JSON-object decoding, exact draft admission, and a thin async compositor. It delegates all workflow, worker, tool, receipt, and terminal behavior unchanged to `run_minimal_csharp_repair_handoff()` and adds no public registration or durable evidence system.

**Tech Stack:** Python 3.12, standard-library `json`/`dataclasses`/`typing`, existing Rook agent contracts, `pytest`, and `pytest-asyncio`; no new dependencies.

## Global Constraints

- Work only in `C:/UDEV/Rook/.worktrees/minimal-intent-worker-integration-design` on `codex/minimal-intent-worker-integration-design`.
- The reviewed base is `f0acdbdb7a9b15adcdb970183e75dd27fedd78c7`; preserve the primary checkout and unrelated worktrees.
- Add exactly one production module and one test module. Do not modify the merged minimal handoff or shared model transport unless a new independent review explicitly changes scope.
- The intent boundary requires `type(intent) is str`, nonblank content, valid UTF-8, and at most 16,384 UTF-8 bytes.
- The Planner response boundary requires `type(raw_response) is str`, valid UTF-8, and at most 65,536 UTF-8 bytes before parsing or retention.
- The runner accepts only `type(planner_adapter) is MinimalPlannerDraftAdapter`; only `MinimalPlannerTransport` remains structural and injectable.
- The concrete adapter renders the code-owned prompt and invokes its transport exactly once. It catches ordinary `Exception`, never `BaseException`.
- Strict decoding rejects duplicate keys, nonfinite numbers, trailing content, non-object roots, markdown extraction, coercion, defaults, and repair.
- Semantic admission remains exclusively `load_minimal_csharp_repair_draft(decoded_object)` followed by exact `draft.goal == intent`.
- One Planner call maximum; zero or one existing worker call; no retries, fallbacks, alternate models, prompt repair, or deterministic draft patching.
- Planner and worker cannot author workflow topology. Repair code remains worker-authored; component identity remains receipt-derived.
- Provider/model/generation construction stays outside the new module. Do not rename, refactor, import, or generalize `LiteLLMWorkerTransport`.
- Add no Chat registration, MCP tool, CLI, capability registry, archive, readiness protocol, attempt identity, fingerprint framework, or scientific harness.
- All fakes remain test-only. No provider, worker-box, Rhino, or Grasshopper contact is authorized during implementation or review.
- The result is ephemeral and validates only its own stage equations; do not reconstruct `MinimalCSharpRepairHandoffResult` internals.

---

## File Map

### Create

- `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
  - Owns bounded intent validation, prompt snapshot/materialization, Planner response schema, structural transport protocol, exact concrete adapter, strict decoder, adapter record, thin async runner, and ephemeral result.
- `mcp_server/tests/test_minimal_intent_worker_integration.py`
  - Owns all fake Planner/worker/tool capabilities, adapter boundary vectors, the real handoff vertical, stop propagation, information-boundary checks, and aggregate-state mutations.

### Reuse unchanged

- `mcp_server/src/rook/agent/minimal_csharp_repair_handoff.py`
  - Sole semantic draft loader and sole owner of workflow/worker/tool/receipt lineage.
- `mcp_server/src/rook/agent/local_worker_adapter.py`
  - Existing worker transport protocol and real worker adapter.
- `mcp_server/src/rook/agent/local_worker_model_transport.py`
  - Existing structural one-call LiteLLM transport; not imported by the new module.
- `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Existing production typed-tool bridge; injected only by a future composition root.

### Documentation

- `docs/superpowers/specs/2026-07-29-minimal-intent-worker-integration-design.md`
  - Approved design; do not amend during implementation without review.
- `docs/superpowers/plans/2026-07-29-minimal-intent-worker-integration.md`
  - Track execution checkboxes and final verified counts.

---

### Task 1: Concrete One-Shot Planner Adapter

**Files:**

- Create: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
- Create: `mcp_server/tests/test_minimal_intent_worker_integration.py`

**Interfaces:**

- Consumes:

  ```python
  class MinimalPlannerTransport(Protocol):
      def send(self, prompt_artifact: Mapping[str, Any]) -> str: ...
  ```

- Produces:

  ```python
  MAX_INTENT_UTF8_BYTES = 16_384
  MAX_PLANNER_RESPONSE_UTF8_BYTES = 65_536

  def build_minimal_planner_draft_response_schema() -> dict[str, Any]: ...

  @dataclass(frozen=True, slots=True)
  class MinimalPlannerPromptSnapshot:
      system_content: str
      user_content: str

      def materialize(self) -> dict[str, Any]: ...

  @dataclass(frozen=True, slots=True)
  class MinimalPlannerDraftAdapterRecord:
      prompt_snapshot: MinimalPlannerPromptSnapshot
      status: Literal["decoded", "transport_failed", "response_invalid"]
      raw_response: str | None
      decoded_object: dict[str, Any] | None
      failure_reason: str | None
      transport_error_type: str | None

  class MinimalPlannerDraftAdapter:
      def __init__(self, transport: MinimalPlannerTransport) -> None: ...
      def produce(self, intent: str) -> MinimalPlannerDraftAdapterRecord: ...
  ```

- Later tasks must use the exact names and types above. Do not add a producer protocol.

- [ ] **Step 1: Add valid-red tests for the real adapter path**

Create the test module with test-only helpers and a first successful adapter witness:

```python
from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest

import rook.agent.minimal_intent_worker_integration as integration
from rook.agent.minimal_intent_worker_integration import (
    MAX_PLANNER_RESPONSE_UTF8_BYTES,
    MinimalPlannerDraftAdapter,
    MinimalPlannerDraftAdapterRecord,
    build_minimal_planner_draft_response_schema,
)


_INTENT = "Create a Grasshopper C# component with one A:double output and compile cleanly."


def _planner_payload(goal: str = _INTENT) -> dict[str, Any]:
    return {
        "goal": goal,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
        "acceptance": "clean_compile_receipt",
    }


class _RecordingPlannerTransport:
    def __init__(self, raw_response: object) -> None:
        self.raw_response = raw_response
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self.raw_response  # type: ignore[return-value]


def test_concrete_adapter_owns_prompt_and_exactly_one_transport_call() -> None:
    raw = json.dumps(_planner_payload(), sort_keys=True, separators=(",", ":"))
    transport = _RecordingPlannerTransport(raw)
    adapter = MinimalPlannerDraftAdapter(transport)

    record = adapter.produce(_INTENT)

    assert record.status == "decoded"
    assert record.raw_response == raw
    assert record.decoded_object == _planner_payload()
    assert record.failure_reason is None
    assert record.transport_error_type is None
    assert len(transport.calls) == 1
    assert transport.calls[0] == record.prompt_snapshot.materialize()
    assert json.loads(transport.calls[0]["messages"][1]["content"]) == {
        "user_intent": _INTENT
    }
```

Also assert `build_minimal_planner_draft_response_schema()` returns equal but independent fresh dictionaries and that mutating one result does not affect the next.

- [ ] **Step 2: Run the adapter witness and confirm a valid RED**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_integration.py::test_concrete_adapter_owns_prompt_and_exactly_one_transport_call -q
```

Expected: collection fails because `rook.agent.minimal_intent_worker_integration` does not exist. An import/attribute typo after the module is created is not valid-red evidence.

- [ ] **Step 3: Implement the immutable prompt snapshot and closed response schema**

Start the production module with no LiteLLM/provider import:

```python
"""One-shot user-intent to minimal Planner-draft product integration."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from rook.agent.local_worker_adapter import LocalWorkerTransport
from rook.agent.minimal_csharp_repair_handoff import (
    MinimalCSharpRepairHandoffResult,
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
    run_minimal_csharp_repair_handoff,
)

MAX_INTENT_UTF8_BYTES = 16_384
MAX_PLANNER_RESPONSE_UTF8_BYTES = 65_536

__all__ = (
    "MAX_INTENT_UTF8_BYTES",
    "MAX_PLANNER_RESPONSE_UTF8_BYTES",
    "MinimalPlannerTransport",
    "MinimalPlannerPromptSnapshot",
    "MinimalPlannerDraftAdapterRecord",
    "MinimalPlannerDraftAdapter",
    "build_minimal_planner_draft_response_schema",
)

_SYSTEM_CONTENT = (
    "You are Rook's bounded intent-to-draft Planner.\n"
    "Treat the supplied user intent as immutable authority and copy it exactly into goal.\n"
    "Return exactly one JSON object and no prose or markdown.\n"
    "The object fields are exactly goal, capability, interface, and acceptance.\n"
    "capability must be grasshopper_csharp_component.\n"
    "interface.inputs must be an empty array.\n"
    "interface.outputs must be exactly one object with name A and type double.\n"
    "acceptance must be clean_compile_receipt."
)


class MinimalPlannerTransport(Protocol):
    def send(self, prompt_artifact: Mapping[str, Any]) -> str: ...


@dataclass(frozen=True, slots=True)
class MinimalPlannerPromptSnapshot:
    system_content: str
    user_content: str

    def materialize(self) -> dict[str, Any]:
        return {
            "messages": [
                {"role": "system", "content": self.system_content},
                {"role": "user", "content": self.user_content},
            ]
        }
```

Implement `build_minimal_planner_draft_response_schema()` as a fresh closed JSON-shaped dictionary with:

```python
{
    "type": "object",
    "additionalProperties": False,
    "required": ["goal", "capability", "interface", "acceptance"],
    "properties": {
        "goal": {"type": "string"},
        "capability": {"const": "grasshopper_csharp_component"},
        "interface": {
            "type": "object",
            "additionalProperties": False,
            "required": ["inputs", "outputs"],
            "properties": {
                "inputs": {"type": "array", "maxItems": 0},
                "outputs": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "type"],
                        "properties": {
                            "name": {"const": "A"},
                            "type": {"const": "double"},
                        },
                    },
                },
            },
        },
        "acceptance": {"const": "clean_compile_receipt"},
    },
}
```

Render `user_content` only as:

```python
json.dumps(
    {"user_intent": intent},
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
)
```

The adapter record retains the frozen snapshot. Call `snapshot.materialize()` once to produce a fresh transport request.

- [ ] **Step 4: Implement strict intent and response decoding**

Use closed internal exceptions for duplicate keys and nonfinite constants:

```python
class _DuplicateKeyError(ValueError):
    pass


class _NonFiniteNumberError(ValueError):
    pass


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKeyError(key)
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise _NonFiniteNumberError(value)
```

Validate intent by exact built-in type, nonblank content, UTF-8 encoding, and the 16,384-byte bound while returning the original string unchanged.

Decode bounded raw responses with:

```python
json.loads(
    raw_response,
    object_pairs_hook=_object_pairs,
    parse_constant=_reject_constant,
)
```

Classify `json.JSONDecodeError` with message `Extra data` as `response_trailing_content`; classify other JSON/recursion errors as `response_invalid_json`. Require `type(decoded) is dict` after parsing. Do not strip, extract fences, or search substrings.

- [ ] **Step 5: Implement the closed adapter record and concrete adapter**

Use these exact statuses and failure reasons:

```python
AdapterStatus = Literal["decoded", "transport_failed", "response_invalid"]
AdapterFailureReason = Literal[
    "transport_failed",
    "response_not_string",
    "response_not_utf8",
    "response_too_large",
    "response_invalid_json",
    "response_duplicate_key",
    "response_nonfinite_number",
    "response_trailing_content",
    "response_not_object",
]
```

In `MinimalPlannerDraftAdapterRecord.__post_init__`, require exact class/type relationships:

- `decoded`: exact snapshot, exact bounded raw string, `type(decoded_object) is dict`, no failure/error fields.
- `transport_failed`: exact snapshot, no raw/object, reason `transport_failed`, exact nonblank built-in error-type string.
- `response_invalid`: exact snapshot, no object/error type, one response refusal reason; raw is absent for not-string, unencodable, and oversized output, and is the exact bounded string for all parse/root refusals.

Implement `MinimalPlannerDraftAdapter` with `__slots__ = ("_transport",)`. Validate a callable `send` in `__init__`. In `produce()`:

1. revalidate the exact intent;
2. render the immutable snapshot;
3. materialize a fresh request;
4. invoke `send()` exactly once inside `except Exception` only;
5. enforce raw type/UTF-8/byte bounds before retention;
6. strictly decode; and
7. return one valid typed record.

Do not catch `KeyboardInterrupt`, `SystemExit`, or any other `BaseException`.

- [ ] **Step 6: Add the complete adapter boundary table**

Add parameterized tests for:

```python
[
    (42, "response_not_string", None),
    ("\ud800", "response_not_utf8", None),
    ("x" * (MAX_PLANNER_RESPONSE_UTF8_BYTES + 1), "response_too_large", None),
    ("not json", "response_invalid_json", "not json"),
    ('{"a":1,"a":2}', "response_duplicate_key", '{"a":1,"a":2}'),
    ('{"outer":{"a":1,"a":2}}', "response_duplicate_key", '{"outer":{"a":1,"a":2}}'),
    ('{"value":NaN}', "response_nonfinite_number", '{"value":NaN}'),
    ("{} {}", "response_trailing_content", "{} {}"),
    ("[]", "response_not_object", "[]"),
    ("```json\n{}\n```", "response_invalid_json", "```json\n{}\n```"),
]
```

Every case must make exactly one transport call and return no decoded object.

Add:

- exact 65,536-byte valid-object and 65,537-byte refusal tests using a computed JSON padding string;
- a transport `RuntimeError` test producing `transport_failed` and the exact class name;
- a `KeyboardInterrupt` test proving propagation;
- record mutation tests using `dataclasses.replace()` for every cross-state combination; and
- a transport that mutates its received request, proving the retained snapshot rematerializes to the original request.

- [ ] **Step 7: Run Task 1 tests and complete the review checkpoint**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_integration.py -q
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall `
  mcp_server\src\rook\agent\minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py
git diff --check
```

Expected: all Task 1 tests pass; compilation and diff checks exit zero.

Before committing, inspect that the production module has no import of `litellm`, `local_worker_model_transport`, Chat, MCP, CLI, DSPy, scripts, or live Rhino code.

- [ ] **Step 8: Commit Task 1**

```powershell
git add `
  mcp_server/src/rook/agent/minimal_intent_worker_integration.py `
  mcp_server/tests/test_minimal_intent_worker_integration.py
git commit -m "feat: add one-shot minimal planner draft adapter"
```

Stop for a focused independent review of the exact adapter type, prompt lineage, one-call behavior, response bounds, strict decoder, and record-state equations before Task 2.

---

### Task 2: Thin Intent Runner and Real Handoff Vertical

**Files:**

- Modify: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_integration.py`

**Interfaces:**

- Consumes:

  ```python
  MinimalPlannerDraftAdapter.produce(intent: str) -> MinimalPlannerDraftAdapterRecord
  load_minimal_csharp_repair_draft(payload: Mapping[str, Any]) -> ValidatedPlannerDraft
  run_minimal_csharp_repair_handoff(
      draft: ValidatedPlannerDraft,
      *,
      worker_transport: LocalWorkerTransport,
      tool_executor: Callable[[str, dict[str, Any]], Any],
  ) -> MinimalCSharpRepairHandoffResult
  ```

- Produces:

  ```python
  @dataclass(frozen=True, slots=True)
  class MinimalIntentWorkerIntegrationResult:
      intent: str
      planner_adapter_record: MinimalPlannerDraftAdapterRecord
      validated_draft: ValidatedPlannerDraft | None
      handoff_result: MinimalCSharpRepairHandoffResult | None
      terminal_stage: str
      terminal_reason: str

  async def run_minimal_intent_worker_integration(
      intent: str,
      *,
      planner_adapter: MinimalPlannerDraftAdapter,
      worker_transport: LocalWorkerTransport,
      tool_executor: Callable[[str, dict[str, Any]], Any],
  ) -> MinimalIntentWorkerIntegrationResult: ...
  ```

  Extend the Task 1 `__all__` tuple with exactly
  `MinimalIntentWorkerIntegrationResult` and
  `run_minimal_intent_worker_integration`.

- [ ] **Step 1: Write the failing real vertical test**

Add a fake Planner transport that returns `_planner_payload(_INTENT)`, a worker transport that traverses the real worker adapter, and a causally responsive typed executor.

The worker transport must parse the real serialized worker request, assert the receipt diagnostic is present, then return:

```python
{
    "schema": "rook.local_worker_turn_response:v1",
    "kind": "action_request",
    "action_id": "draft_repair_params",
    "rationale": "Author a complete replacement body for the declared A:double interface.",
    "input": {"code": "A = 42.0;", "mode": "body"},
}
```

The fake executor must accept only this causal sequence:

```text
gh_create_csharp_script
  code == A = DefinitelyMissingSymbol;
  pins_in == ()
  pins_out == (A:double,)
-> created_with_errors receipt containing one diagnostic and component GUID

gh_update_script
  guid == GUID from the create receipt
  code == A = 42.0;
  mode == body
  language == csharp
-> usable clean update receipt for the same GUID
```

Use these exact receipt shapes in the test fake:

```python
def _created_with_errors(received_body: object) -> dict[str, Any]:
    assert received_body == "A = DefinitelyMissingSymbol;"
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {
                    "status": "created",
                    "component_guid": "minimal-intent-component-guid",
                },
                "verification": {
                    "status": "failed",
                    "target_error_count": 1,
                },
                "repair_anchor": {
                    "component_guid": "minimal-intent-component-guid",
                    "language": "csharp",
                    "target_errors": [
                        "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
                    ],
                },
            }
        },
    }


def _updated_clean() -> dict[str, Any]:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {
                "status": "written",
                "component_guid": "minimal-intent-component-guid",
            },
            "verification": {
                "status": "passed",
                "target_error_count": 0,
            },
            "repair_anchor": {
                "component_guid": "minimal-intent-component-guid",
                "language": "csharp",
                "target_errors": [],
            },
        }
    }
```

The success assertions are:

```python
result = await run_minimal_intent_worker_integration(
    _INTENT,
    planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
    worker_transport=worker_transport,
    tool_executor=tool_executor,
)

assert len(planner_transport.calls) == 1
assert len(worker_transport.calls) == 1
assert [name for name, _ in tool_executor.calls] == [
    "gh_create_csharp_script",
    "gh_update_script",
]
assert result.intent == _INTENT
assert result.planner_adapter_record.raw_response == planner_transport.raw_response
assert result.validated_draft == result.handoff_result.draft
assert result.validated_draft.goal == _INTENT
assert result.terminal_stage == "terminal"
assert result.terminal_reason == "terminal_node_selected:done"
assert result.terminal_stage == result.handoff_result.terminal_stage
assert result.terminal_reason == result.handoff_result.terminal_reason
assert result.handoff_result.final_graph.nodes["done"].status == "ready"
```

- [ ] **Step 2: Run the vertical test and confirm valid RED**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_integration.py::test_exact_intent_walks_real_handoff_to_native_terminal -q
```

Expected: fail because `run_minimal_intent_worker_integration` and its result type do not exist. A fake receipt assertion failure is not the intended RED.

- [ ] **Step 3: Implement the aggregate state equations**

In `MinimalIntentWorkerIntegrationResult.__post_init__`, require exact built-in strings and exact record/result classes, then enforce only:

```text
adapter stop:
  adapter status != decoded
  validated_draft is None
  handoff_result is None
  terminal_stage == planner_adapter
  terminal_reason == adapter failure_reason

draft stop:
  adapter status == decoded
  validated_draft is None
  handoff_result is None
  terminal_stage == draft_admission
  terminal_reason in {draft_payload_rejected, goal_mismatch}

handoff reached:
  adapter status == decoded
  validated_draft is present
  handoff_result is present
  validated_draft == handoff_result.draft
  terminal_stage == handoff_result.terminal_stage
  terminal_reason == handoff_result.terminal_reason
```

Do not inspect the handoff graph, worker records, action result, receipts, or tool records in this validator.

- [ ] **Step 4: Implement the exact concrete-adapter runner**

At the top of the runner, before any capability invocation:

```python
intent = _require_exact_intent(intent)
if type(planner_adapter) is not MinimalPlannerDraftAdapter:
    raise TypeError("planner_adapter must be the exact MinimalPlannerDraftAdapter")
if not callable(getattr(worker_transport, "send", None)):
    raise TypeError("worker_transport must provide callable send")
if not callable(tool_executor):
    raise TypeError("tool_executor must be callable")
```

Then:

```python
adapter_record = planner_adapter.produce(intent)
if adapter_record.status != "decoded":
    assert adapter_record.failure_reason is not None
    return MinimalIntentWorkerIntegrationResult(
        intent=intent,
        planner_adapter_record=adapter_record,
        validated_draft=None,
        handoff_result=None,
        terminal_stage="planner_adapter",
        terminal_reason=adapter_record.failure_reason,
    )

assert adapter_record.decoded_object is not None
try:
    draft = load_minimal_csharp_repair_draft(adapter_record.decoded_object)
except (TypeError, ValueError):
    return _draft_stop(intent, adapter_record, "draft_payload_rejected")

if draft.goal != intent:
    return _draft_stop(intent, adapter_record, "goal_mismatch")

handoff = await run_minimal_csharp_repair_handoff(
    draft,
    worker_transport=worker_transport,
    tool_executor=tool_executor,
)
return MinimalIntentWorkerIntegrationResult(
    intent=intent,
    planner_adapter_record=adapter_record,
    validated_draft=draft,
    handoff_result=handoff,
    terminal_stage=handoff.terminal_stage,
    terminal_reason=handoff.terminal_reason,
)
```

The local assertion narrows the already-closed adapter record; it is not a default or repair. Do not catch exceptions raised by the handoff.

- [ ] **Step 5: Prove exact adapter-type and goal-authority refusal**

Add:

```python
class _AdapterSubclass(MinimalPlannerDraftAdapter):
    pass


class _SubstituteProducer:
    def produce(self, intent: str) -> MinimalPlannerDraftAdapterRecord:
        raise AssertionError("substitute producer must not be invoked")
```

Parameterize both values through `planner_adapter` with type-ignore comments. Assert `TypeError` before Planner transport, worker transport, or tool executor calls.

Add two one-call Planner cases:

- valid object with an extra field -> `draft_admission / draft_payload_rejected`;
- otherwise valid object whose goal differs by one character or whitespace -> `draft_admission / goal_mismatch`.

Both must return `validated_draft is None`, `handoff_result is None`, one Planner call, and zero worker/tool calls.

Add a third regression whose raw response is produced with:

```python
json.dumps(_planner_payload("\ud800"), ensure_ascii=True)
```

The raw response is valid bounded ASCII JSON, decoding produces a built-in
string containing a lone surrogate, and the existing draft loader accepts its
shape. Require the runner to return `draft_admission / goal_mismatch` after one
Planner call with zero worker/tool calls. The test must fail if the runner
attempts to UTF-8 encode the decoded goal.

- [ ] **Step 6: Prove the Planner information boundary**

Inspect both `record.prompt_snapshot` fields and its materialized mapping. Require the user message to decode exactly to `{"user_intent": _INTENT}`.

Assert no prompt string contains any of these exact downstream values:

```text
A = DefinitelyMissingSymbol;
A = 42.0;
repair_same_component
draft_repair_params
gh_create_csharp_script
gh_update_script
minimal-intent-component-guid
CS0103
```

Assert the system message contains only the closed field vocabulary and no example JSON object. Assert the response schema is not inserted into the user intent envelope.

- [ ] **Step 7: Run Task 2 focused and inherited seam tests**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py -q
git diff --check
```

Expected: all selected tests pass and the diff check exits zero.

- [ ] **Step 8: Commit Task 2**

```powershell
git add `
  mcp_server/src/rook/agent/minimal_intent_worker_integration.py `
  mcp_server/tests/test_minimal_intent_worker_integration.py
git commit -m "feat: connect exact intent to minimal worker handoff"
```

---

### Task 3: Boundary and Operational-Stop Hardening

**Files:**

- Modify: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_integration.py`

**Interfaces:**

- Consumes the exact Task 1 adapter and Task 2 runner/result interfaces.
- Produces complete adversarial coverage without adding a new production type or outcome vocabulary.

- [ ] **Step 1: Add intent-byte and capability-order tests**

Parameterize caller inputs:

```python
[
    7,
    _EqualitySpoof("different intent"),
    "",
    "   ",
    "\ud800",
    "é" * 8_193,
]
```

Each must raise before Planner, worker, or tool invocation. Add an exact-bound case using `"é" * 8_192`; it must reach one Planner call and preserve the exact intent in the prompt.

Pass invalid worker transport and tool executor objects with a valid Planner adapter. Require caller-contract `TypeError` before the Planner transport is invoked.

- [ ] **Step 2: Add adapter-to-runner refusal coverage**

Run the complete Task 1 response-invalid table through `run_minimal_intent_worker_integration()`. For every case assert:

```text
Planner calls == 1
worker calls == 0
tool calls == 0
terminal_stage == planner_adapter
terminal_reason == adapter_record.failure_reason
validated_draft is None
handoff_result is None
```

Add the transport `RuntimeError` case with the same downstream-zero equations. Do not convert `KeyboardInterrupt` into a result.

- [ ] **Step 3: Add representative native worker/tool stop projections**

Use the real handoff with one valid Planner response and parameterize:

| Case | Expected native stage | Expected native reason | Worker calls | Tool names |
|---|---|---|---:|---|
| create executor raises | `create` | `dispatch_failed` | 0 | `gh_create_csharp_script` |
| worker transport raises declared `TransportError` | `worker_adapter` | `transport_error:declared` | 1 | `gh_create_csharp_script` |
| worker returns invalid JSON | `worker_adapter` | `raw_output_invalid:json_decode` | 1 | `gh_create_csharp_script` |
| worker clarification | `worker_disposition` | `clarification_needed` | 1 | `gh_create_csharp_script` |
| worker refusal | `worker_disposition` | `refusal_recorded` | 1 | `gh_create_csharp_script` |
| unknown action ID | `worker_disposition` | `blocked:unknown_action_id:other_action` | 1 | `gh_create_csharp_script` |
| invalid action mode | `action_apply` | `invalid_mode` | 1 | `gh_create_csharp_script` |
| repair executor raises | `repair` | `dispatch_failed` | 1 | create, update |
| reverify remains broken | `verify_repair` | `selector_halt:none_ready` | 1 | create, update |

For every case assert exactly one Planner call and exact equality:

```python
assert result.validated_draft == result.handoff_result.draft
assert result.terminal_stage == result.handoff_result.terminal_stage
assert result.terminal_reason == result.handoff_result.terminal_reason
```

Do not recreate the handoff's internal optional-record or graph validations.

- [ ] **Step 4: Add aggregate mutation tests**

Using one adapter-stop, one draft-stop, and one successful result, use `dataclasses.replace()` to reject:

- adapter stop with a draft or handoff;
- adapter stop with a reason different from its record;
- draft stop with a retained draft;
- draft stop with any reason outside the two-value vocabulary;
- handoff result without a draft;
- validated draft different from `handoff_result.draft`;
- terminal stage or reason different from the handoff; and
- caller-authored mapping substituted for the adapter record.

Monkeypatch `run_minimal_csharp_repair_handoff()` to raise one `RuntimeError` after successful Planner/draft admission. Assert that exact exception escapes; the runner must not manufacture an operational result.

- [ ] **Step 5: Run the hardened module tests**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_local_worker_adapter.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py -q
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall `
  mcp_server\src\rook\agent\minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py
git diff --check
```

Expected: all tests pass; compile and diff checks exit zero.

- [ ] **Step 6: Commit Task 3**

```powershell
git add `
  mcp_server/src/rook/agent/minimal_intent_worker_integration.py `
  mcp_server/tests/test_minimal_intent_worker_integration.py
git commit -m "test: harden minimal intent worker integration"
```

---

### Task 4: Full Verification, Surface Audit, and Plan Reconciliation

**Files:**

- Verify: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
- Verify: `mcp_server/tests/test_minimal_intent_worker_integration.py`
- Modify: `docs/superpowers/plans/2026-07-29-minimal-intent-worker-integration.md`

**Interfaces:**

- Consumes the complete implementation from Tasks 1–3.
- Produces fresh verification evidence and an accurate durable execution ledger; no live integration.

- [ ] **Step 1: Run the complete focused seam**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_workflow_contract.py `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_gh_edit_contract.py `
  mcp_server\tests\test_plan_graph_workflow_contract_chain.py `
  mcp_server\tests\test_plan_graph_live_dispatch.py `
  mcp_server\tests\test_plan_graph_current_step_stream.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py `
  mcp_server\tests\test_local_worker_adapter.py `
  mcp_server\tests\test_local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py -q
```

Record exact passed, failed, skipped, and warning counts. The inherited portion was 492 tests at specification time; do not claim a new total until this fresh command finishes.

- [ ] **Step 2: Run the broader relevant Python-agent family**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests -q `
  -k "plan_graph or local_worker or workflow_contract or gh_edit_contract or minimal_csharp_repair_handoff or minimal_intent_worker_integration"
```

Use a bounded practical timeout. If it times out, report that state honestly and rely only on the completed focused evidence.

- [ ] **Step 3: Audit the product surface and exact merge diff**

Run:

```powershell
git diff --name-only f0acdbdb7a9b15adcdb970183e75dd27fedd78c7...HEAD
rg -n "litellm|local_worker_model_transport|rook\.agent\.chat|dspy|scripts\.|readiness|argparse|click|mcp\.tool|Fake|Rhino|Grasshopper" `
  mcp_server/src/rook/agent/minimal_intent_worker_integration.py
rg -n "def send|class MinimalPlannerDraftAdapter|run_minimal_intent_worker_integration|load_minimal_csharp_repair_draft|run_minimal_csharp_repair_handoff" `
  mcp_server/src/rook/agent/minimal_intent_worker_integration.py
```

Interpret expected semantic words carefully: the prompt's allowed capability contains `grasshopper_csharp_component`, so that occurrence is permitted. There must be no provider construction/import, fake implementation, Chat/MCP/CLI registration, new tool/template/action, or scripts dependency.

Expected implementation merge scope:

```text
docs/superpowers/specs/2026-07-29-minimal-intent-worker-integration-design.md
docs/superpowers/plans/2026-07-29-minimal-intent-worker-integration.md
mcp_server/src/rook/agent/minimal_intent_worker_integration.py
mcp_server/tests/test_minimal_intent_worker_integration.py
```

- [ ] **Step 4: Inspect the exact success transaction**

From the deterministic vertical's retained in-memory records, verify:

```text
exact intent
-> code-owned prompt snapshot
-> one materialized request and one Planner transport call
-> exact bounded raw response
-> strict decoded object
-> existing strict draft loader
-> exact goal equality
-> existing workflow compiler
-> create receipt diagnostic and GUID
-> one real worker-adapter call
-> worker-authored repair code
-> receipt-derived GUID in the update request
-> clean native receipt
-> terminal_node_selected:done
-> thin aggregate with native stage/reason unchanged
```

Confirm the Planner prompt contains no private fixture, topology, worker action, diagnostic, GUID, receipt, or expected repair code.

- [ ] **Step 5: Verify compilation and repository state**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall `
  mcp_server\src\rook\agent\minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py
git diff --check
git status --short
```

No provider, worker-box, Rhino, or Grasshopper process may be constructed or contacted by any verification command.

- [ ] **Step 6: Reconcile the execution ledger**

Update every completed checkbox in this plan. Append an `Execution reconciliation` section containing:

- exact base and final implementation HEAD;
- exact focused and broader test counts;
- compile/diff/worktree results;
- exact four-file merge scope;
- explicit statement that the result is ephemeral;
- explicit statement that no live contact occurred; and
- any bounded deviation approved during review.

Run a checkbox count and require zero operational unchecked steps before the final docs commit:

```powershell
$plan = Get-Content docs/superpowers/plans/2026-07-29-minimal-intent-worker-integration.md
"checked=$((($plan | Select-String '^- \[x\]').Count))"
"unchecked=$((($plan | Select-String '^- \[ \]').Count))"
```

- [ ] **Step 7: Commit only the reconciliation**

```powershell
git add docs/superpowers/plans/2026-07-29-minimal-intent-worker-integration.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: reconcile minimal intent integration plan"
```

The staged name list must contain only the plan.

- [ ] **Step 8: Stop for independent implementation review**

Request review against base `f0acdbdb7a9b15adcdb970183e75dd27fedd78c7`. Do not push, open a PR, merge, construct a real provider transport, run the worker box, or contact Rhino/Grasshopper as part of implementation completion.

---

## Completion Criteria

- [ ] Exact invalid/oversized intent stops before all capability invocation.
- [ ] Exact concrete Planner adapter is the only runner input; subclasses and substitute producers are refused.
- [ ] The concrete adapter owns the code-authored prompt and exactly one structural transport call.
- [ ] Prompt snapshot remains immutable while transport receives a fresh mutable mapping.
- [ ] Planner raw response is bounded before parsing/retention and retained exactly when admitted.
- [ ] Duplicate keys, nonfinite values, trailing content, non-object roots, markdown, coercion, defaults, and repair are refused.
- [ ] Only the existing draft loader grants semantic admission.
- [ ] Validated draft goal equals the original intent exactly.
- [ ] A JSON-escaped lone-surrogate goal produces typed `goal_mismatch`, never an encoding exception.
- [ ] Malformed Planner output and Planner failure produce typed adapter/draft stops with zero worker/tool calls.
- [ ] The successful path traverses the real merged handoff, real worker adapter, and native terminal result.
- [ ] Planner calls equal one and worker calls are zero or one; no retry/fallback exists.
- [ ] Worker repair code remains the sole repair-code source and the update GUID remains receipt-derived.
- [ ] Planner prompt excludes fixture code, diagnostics, topology, worker action, GUID, receipt, and expected repair code.
- [ ] Existing worker/tool stop stages and reasons pass through unchanged.
- [ ] The aggregate validates only its own ownership equations and remains ephemeral.
- [ ] No new public registration, provider construction, shared transport refactor, fake production executor, or durable evidence layer exists.
- [ ] Focused and broader relevant tests are freshly reported; compile and diff checks pass.
- [ ] No provider, worker-box, Rhino, or Grasshopper contact occurred.

---

## Deferred Post-Merge Smoke Tests

These are proposals only and are not authorized by implementation, review, PR, or merge.

1. **Model-composition smoke:** separately authorize one real Planner call and at most one real worker-box call while retaining a strict operator/test-only fake typed executor. Success proves model-to-model contract compliance only.
2. **Live tool smoke:** after the first smoke is understood, separately authorize replacement of the fake executor with the unchanged real typed tool bridge and live Rhino/Grasshopper.

Neither smoke permits retry, fallback, automatic prompt changes, or production fake behavior.
