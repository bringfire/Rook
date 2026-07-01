# LM5G Local Worker Response Loader Plan

## Goal

Implement LM5G as a narrow transport boundary:

```text
already-parsed Mapping payload
-> load_local_worker_turn_response_payload(...)
-> LocalWorkerTurnResponse
```

The loader accepts only the strict schema-tagged, flat response envelope defined in the LM5G spec. It constructs the existing LM5B typed response dataclasses, remains context-free, and does not validate action admissibility against `LocalWorkerTurnContext`.

## Scope

Production change:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
```

Test change:

```text
mcp_server/tests/test_local_worker_turn_response_loader.py
```

Docs already present on branch:

```text
docs/superpowers/specs/2026-06-30-lm5g-local-worker-response-loader-design.md
docs/superpowers/plans/2026-06-30-lm5g-local-worker-response-loader.md
```

No changes to:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
mcp_server/tests/test_local_worker_turn_response.py
mcp_server/tests/test_local_worker_turn_scenarios.py
src/Rook/**
src/RookNative/**
operations_knowledge.json
```

## Boundaries

LM5G must not add:

```text
model calls
prompt rendering
RookChat integration
scenario runners
worker harness execution helpers
context validation
disposition helpers
scenario evaluation helpers
action execution
tool dispatch
graph mutation
stream execution
workflow compile/load/snapshot helpers
file/path loaders
JSON/YAML text parsing
package-level export churn
```

Unknown `action_id` values are loader-valid when they are non-empty strings. Action admissibility remains owned by:

```python
validate_local_worker_turn_response(context, response)
```

## Pre-Implementation Gate

Run from the isolated worktree:

```powershell
Set-Location C:\Users\bring\.config\superpowers\worktrees\Rook\lm5g-local-worker-transport-boundary
git status --short --branch
git diff --name-status origin/main..HEAD
git diff --check origin/main..HEAD
```

Expected branch diff before implementation:

```text
A       docs/superpowers/specs/2026-06-30-lm5g-local-worker-response-loader-design.md
A       docs/superpowers/plans/2026-06-30-lm5g-local-worker-response-loader.md
```

If `git diff --name-status main..HEAD` shows unrelated files, do not use that as the scope gate in this worktree. The local `main` ref may be stale; use `origin/main..HEAD`.

## Task 1: Add Loader Tests First

Create:

```text
mcp_server/tests/test_local_worker_turn_response_loader.py
```

Use plain Python dictionaries and lists. Do not import `json`.

Test file:

```python
from __future__ import annotations

import ast
from collections.abc import Mapping
import inspect

import pytest

from rook.agent import local_worker_turn_response as response_module
from rook.agent.local_worker_scenario_evaluation import (
    LocalWorkerScenarioExpectation,
    evaluate_local_worker_scenario_result,
)
from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    WorkerGraphSummary,
    WorkerHistorySummary,
    WorkerWorkflowSummary,
)
from rook.agent.local_worker_turn_disposition import (
    dispose_local_worker_turn_response,
)
from rook.agent.local_worker_turn_harness import run_local_worker_turn
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerObservation,
    WorkerRefusal,
    load_local_worker_turn_response_payload,
    validate_local_worker_turn_response,
)


def _action_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": "Use the explicit repair action.",
        "input": {
            "mode": "body",
            "pins_out": ["A:double"],
            "nested": {"values": [1, 2]},
        },
    }
    payload.update(overrides)
    return payload


def _clarification_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "clarification_request",
        "question": "Which component should be repaired?",
        "rationale": None,
    }
    payload.update(overrides)
    return payload


def _refusal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "refusal",
        "category": "out_of_scope",
        "reason": "The requested operation is outside this worker turn.",
    }
    payload.update(overrides)
    return payload


def _observation_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "observation",
        "message": "The terminal node is already visible.",
        "data": {"node_id": "done", "flags": ["terminal"]},
    }
    payload.update(overrides)
    return payload


def _context(*, action_id: str = "draft_repair_params") -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="repair_component",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="fingerprint-123",
            compiler_id="rook.workflow_contract.compiler:v1",
            provider_id="rook.catalog_current_step_provider:v1",
            selected_template_id="gh_repair_component:v1",
            max_steps=5,
        ),
        current_graph=WorkerGraphSummary(
            node_count=1,
            node_ids=("repair_same_component",),
            ready_node_ids=("repair_same_component",),
            terminal_node_ids=("done",),
            status_counts={"READY": 1},
        ),
        current_node=None,
        history=WorkerHistorySummary(
            current_step_count=0,
            supply_count=0,
            last_accepted_node_id=None,
            last_execution_kind=None,
            last_stop_reason=None,
            recent_steps=(),
            recent_supplies=(),
        ),
        knowledge=(),
        allowed_actions=(
            WorkerAllowedAction(
                action_id=action_id,
                kind="draft_params",
                description="Draft repair params.",
                input_schema={"type": "object"},
            ),
        ),
    )


def test_schema_constant_and_public_exports_are_present() -> None:
    assert LOCAL_WORKER_TURN_RESPONSE_SCHEMA == "rook.local_worker_turn_response:v1"
    assert "LOCAL_WORKER_TURN_RESPONSE_SCHEMA" in response_module.__all__
    assert "load_local_worker_turn_response_payload" in response_module.__all__


def test_loads_action_request_payload_and_normalizes_nested_lists() -> None:
    response = load_local_worker_turn_response_payload(_action_payload())

    assert isinstance(response, LocalWorkerTurnResponse)
    assert isinstance(response.payload, WorkerActionRequest)
    assert response.payload.action_id == "draft_repair_params"
    assert response.payload.rationale == "Use the explicit repair action."
    assert response.payload.input["mode"] == "body"
    assert response.payload.input["pins_out"] == ("A:double",)
    nested = response.payload.input["nested"]
    assert isinstance(nested, Mapping)
    assert nested["values"] == (1, 2)


def test_loads_unknown_action_id_without_context_admissibility() -> None:
    response = load_local_worker_turn_response_payload(
        _action_payload(action_id="not_declared_here")
    )

    assert isinstance(response.payload, WorkerActionRequest)
    assert response.payload.action_id == "not_declared_here"

    attempt = validate_local_worker_turn_response(_context(), response)
    assert attempt.valid is False
    assert attempt.failure == "unknown_action_id"
    assert attempt.reason == "unknown_action_id:not_declared_here"


def test_loads_clarification_request_with_required_none_rationale() -> None:
    response = load_local_worker_turn_response_payload(_clarification_payload())

    assert isinstance(response.payload, WorkerClarificationRequest)
    assert response.payload.question == "Which component should be repaired?"
    assert response.payload.rationale is None


def test_loads_refusal_payload() -> None:
    response = load_local_worker_turn_response_payload(_refusal_payload())

    assert isinstance(response.payload, WorkerRefusal)
    assert response.payload.category == "out_of_scope"
    assert response.payload.reason == "The requested operation is outside this worker turn."


def test_loads_observation_payload_with_required_mapping_data() -> None:
    response = load_local_worker_turn_response_payload(_observation_payload())

    assert isinstance(response.payload, WorkerObservation)
    assert response.payload.message == "The terminal node is already visible."
    assert response.payload.data is not None
    assert response.payload.data["flags"] == ("terminal",)


def test_loads_observation_payload_with_required_none_data() -> None:
    response = load_local_worker_turn_response_payload(_observation_payload(data=None))

    assert isinstance(response.payload, WorkerObservation)
    assert response.payload.data is None


@pytest.mark.parametrize(
    ("payload_factory", "missing_field"),
    [
        (_action_payload, "input"),
        (_clarification_payload, "rationale"),
        (_refusal_payload, "reason"),
        (_observation_payload, "data"),
    ],
)
def test_rejects_missing_variant_fields(
    payload_factory: object,
    missing_field: str,
) -> None:
    payload = payload_factory()
    assert isinstance(payload, dict)
    payload.pop(missing_field)

    with pytest.raises(ValueError, match="missing required fields"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize(
    "payload_factory",
    [
        _action_payload,
        _clarification_payload,
        _refusal_payload,
        _observation_payload,
    ],
)
def test_rejects_unknown_variant_fields(payload_factory: object) -> None:
    payload = payload_factory(extra="nope")
    assert isinstance(payload, dict)

    with pytest.raises(ValueError, match="unknown fields"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize("field", ["schema", "kind"])
def test_rejects_missing_top_level_dispatch_fields(field: str) -> None:
    payload = _action_payload()
    payload.pop(field)

    with pytest.raises(ValueError, match="missing required fields"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", 123),
        ("kind", 123),
    ],
)
def test_rejects_non_string_top_level_dispatch_fields(
    field: str,
    value: object,
) -> None:
    payload = _action_payload(**{field: value})

    with pytest.raises(TypeError):
        load_local_worker_turn_response_payload(payload)


def test_rejects_unsupported_schema() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        load_local_worker_turn_response_payload(_action_payload(schema="other:v1"))


def test_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown"):
        load_local_worker_turn_response_payload(_action_payload(kind="action"))


def test_rejects_non_mapping_top_level_payload() -> None:
    with pytest.raises(TypeError, match="mapping"):
        load_local_worker_turn_response_payload(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_rejects_non_string_top_level_mapping_keys() -> None:
    payload: dict[object, object] = dict(_action_payload())
    payload[1] = "bad"

    with pytest.raises(TypeError, match="string keys"):
        load_local_worker_turn_response_payload(payload)  # type: ignore[arg-type]


def test_rejects_non_string_nested_mapping_keys() -> None:
    payload = _action_payload(input={"ok": 1, 2: "bad"})

    with pytest.raises(TypeError, match="string keys"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize(
    "bad_input",
    [
        None,
        ["not", "mapping"],
        "not mapping",
    ],
)
def test_rejects_action_input_that_is_not_mapping(bad_input: object) -> None:
    with pytest.raises(TypeError, match="mapping"):
        load_local_worker_turn_response_payload(_action_payload(input=bad_input))


@pytest.mark.parametrize(
    "bad_data",
    [
        ["not", "mapping"],
        "not mapping",
        42,
    ],
)
def test_rejects_observation_data_that_is_not_mapping_or_none(
    bad_data: object,
) -> None:
    with pytest.raises(TypeError, match="mapping"):
        load_local_worker_turn_response_payload(_observation_payload(data=bad_data))


@pytest.mark.parametrize(
    "bad_value",
    [
        float("inf"),
        float("-inf"),
        float("nan"),
        object(),
        {"bad", "set"},
        lambda: None,
    ],
)
def test_rejects_non_json_safe_nested_values(bad_value: object) -> None:
    with pytest.raises(TypeError):
        load_local_worker_turn_response_payload(
            _action_payload(input={"bad": bad_value})
        )


def test_caller_payload_mutation_after_load_does_not_affect_response() -> None:
    payload = _action_payload()
    input_payload = payload["input"]
    assert isinstance(input_payload, dict)
    pins_out = input_payload["pins_out"]
    nested = input_payload["nested"]
    assert isinstance(pins_out, list)
    assert isinstance(nested, dict)

    response = load_local_worker_turn_response_payload(payload)

    pins_out.append("B:int")
    nested["values"].append(3)
    input_payload["mode"] = "class"

    assert isinstance(response.payload, WorkerActionRequest)
    assert response.payload.input["mode"] == "body"
    assert response.payload.input["pins_out"] == ("A:double",)
    assert response.payload.input["nested"] == {"values": (1, 2)}


def test_loaded_response_composes_with_lm5b_lm5c_lm5d_and_lm5f() -> None:
    context = _context()
    response = load_local_worker_turn_response_payload(_action_payload())

    attempt = validate_local_worker_turn_response(context, response)
    assert attempt.valid is True
    assert attempt.action_id == "draft_repair_params"

    disposition = dispose_local_worker_turn_response(context, response)
    assert disposition.disposition == "candidate_action_request"

    harness_record = run_local_worker_turn(context, lambda received: response)
    assert harness_record.status == "completed"
    assert harness_record.response is response
    assert harness_record.disposition is not None
    assert harness_record.disposition.disposition == "candidate_action_request"

    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="loaded_response_chain",
            category="loader_integration",
            expected_status="completed",
            expected_disposition="candidate_action_request",
            expected_attempt_valid=True,
            expected_action_id="draft_repair_params",
            expected_response_kind="action_request",
            expected_workflow_id=context.workflow.workflow_id,
            expected_contract_fingerprint=context.workflow.contract_fingerprint,
        ),
        harness_record,
    )
    assert result.passed is True


def test_loader_function_body_boundary_guard() -> None:
    source = inspect.getsource(response_module)
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    target_names = {
        name
        for name in functions
        if name == "load_local_worker_turn_response_payload"
        or name.startswith("_load_")
        or name
        in {
            "_copy_json_payload",
            "_copy_json_mapping",
            "_require_fields",
            "_require_mapping",
            "_require_present",
            "_require_string_keys",
        }
    }

    assert "load_local_worker_turn_response_payload" in target_names
    assert "_copy_json_payload" in target_names

    banned_names = {
        "LocalWorkerTurnContext",
        "validate_local_worker_turn_response",
        "dispose_local_worker_turn_response",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
        "build_local_worker_scenario_report",
        "Path",
        "open",
        "compile_workflow_contract",
        "run_current_step_stream",
        "RookAgent",
        "base_agent",
        "RookChat",
        "dispatcher",
        "json",
        "loads",
        "model",
        "prompt",
        "dumps",
        "yaml",
    }
    banned_attributes = {"loads", "dumps"}

    for target_name in sorted(target_names):
        node = functions[target_name]
        referenced_names = {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        referenced_attributes = {
            child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)
        }

        assert not (referenced_names & banned_names), target_name
        assert not (referenced_attributes & banned_attributes), target_name
```

Expected RED:

```text
ImportError: cannot import name 'LOCAL_WORKER_TURN_RESPONSE_SCHEMA'
ImportError: cannot import name 'load_local_worker_turn_response_payload'
```

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_turn_response_loader.py
```

## Task 2: Add Production Loader

Edit:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
```

### Update `__all__`

Add only the new schema constant and public loader:

```python
__all__ = (
    "LOCAL_WORKER_TURN_RESPONSE_SCHEMA",
    "LocalWorkerTurnResponse",
    "LocalWorkerTurnAttemptRecord",
    "WorkerActionRequest",
    "WorkerClarificationRequest",
    "WorkerRefusal",
    "WorkerObservation",
    "WorkerResponseKind",
    "WorkerRefusalCategory",
    "WorkerResponseValidationFailure",
    "load_local_worker_turn_response_payload",
    "validate_local_worker_turn_response",
)
```

### Add schema constant and private field sets

Place near the literal aliases:

```python
LOCAL_WORKER_TURN_RESPONSE_SCHEMA = "rook.local_worker_turn_response:v1"

_ACTION_REQUEST_PAYLOAD_FIELDS = frozenset(
    {"schema", "kind", "action_id", "rationale", "input"}
)
_CLARIFICATION_REQUEST_PAYLOAD_FIELDS = frozenset(
    {"schema", "kind", "question", "rationale"}
)
_REFUSAL_PAYLOAD_FIELDS = frozenset({"schema", "kind", "category", "reason"})
_OBSERVATION_PAYLOAD_FIELDS = frozenset(
    {"schema", "kind", "message", "data"}
)
```

These are private implementation details. Do not export field names or kind constants.

### Add public loader

Place after `LocalWorkerTurnResponse` / `LocalWorkerTurnAttemptRecord`, before the LM5B validator or in a nearby response-construction section:

```python
def load_local_worker_turn_response_payload(
    payload: Mapping[str, Any],
) -> LocalWorkerTurnResponse:
    record = _require_mapping(payload, "local worker turn response payload")
    _require_present(record, "schema", "local worker turn response payload")
    _require_present(record, "kind", "local worker turn response payload")

    schema = record["schema"]
    if not isinstance(schema, str):
        raise TypeError("local worker turn response payload schema must be a string")
    if schema != LOCAL_WORKER_TURN_RESPONSE_SCHEMA:
        raise ValueError(f"unsupported local worker turn response schema: {schema!r}")

    kind = record["kind"]
    if not isinstance(kind, str):
        raise TypeError("local worker turn response payload kind must be a string")

    if kind == "action_request":
        return LocalWorkerTurnResponse(_load_action_request_payload(record))
    if kind == "clarification_request":
        return LocalWorkerTurnResponse(_load_clarification_request_payload(record))
    if kind == "refusal":
        return LocalWorkerTurnResponse(_load_refusal_payload(record))
    if kind == "observation":
        return LocalWorkerTurnResponse(_load_observation_payload(record))

    raise ValueError(f"unknown local worker response kind: {kind!r}")
```

### Add variant loaders

```python
def _load_action_request_payload(
    payload: Mapping[str, Any],
) -> WorkerActionRequest:
    _require_fields(
        payload,
        required=_ACTION_REQUEST_PAYLOAD_FIELDS,
        context="action_request payload",
    )
    return WorkerActionRequest(
        action_id=payload["action_id"],
        rationale=payload["rationale"],
        input=_copy_json_mapping(payload["input"], "action_request.input"),
    )


def _load_clarification_request_payload(
    payload: Mapping[str, Any],
) -> WorkerClarificationRequest:
    _require_fields(
        payload,
        required=_CLARIFICATION_REQUEST_PAYLOAD_FIELDS,
        context="clarification_request payload",
    )
    return WorkerClarificationRequest(
        question=payload["question"],
        rationale=payload["rationale"],
    )


def _load_refusal_payload(payload: Mapping[str, Any]) -> WorkerRefusal:
    _require_fields(
        payload,
        required=_REFUSAL_PAYLOAD_FIELDS,
        context="refusal payload",
    )
    return WorkerRefusal(
        category=payload["category"],
        reason=payload["reason"],
    )


def _load_observation_payload(payload: Mapping[str, Any]) -> WorkerObservation:
    _require_fields(
        payload,
        required=_OBSERVATION_PAYLOAD_FIELDS,
        context="observation payload",
    )
    data = payload["data"]
    if data is not None:
        data = _copy_json_mapping(data, "observation.data")
    return WorkerObservation(
        message=payload["message"],
        data=data,
    )
```

Do not validate `action_id` against a context. Do not validate `input` against `WorkerAllowedAction.input_schema`.

### Add loader helpers

Use loader-specific helpers even though LM5B already has response-freezing helpers. The loader helper returns plain copied dictionaries and tuple-normalized arrays before LM5B freezes the constructed response.

```python
def _require_mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    _require_string_keys(value, context)
    return value


def _require_string_keys(value: Mapping[object, object], context: str) -> None:
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{context} must have string keys")


def _require_present(
    payload: Mapping[str, Any],
    field: str,
    context: str,
) -> None:
    if field not in payload:
        raise ValueError(f"{context} missing required fields: {[field]!r}")


def _require_fields(
    payload: Mapping[str, Any],
    *,
    required: frozenset[str],
    context: str,
) -> None:
    keys = set(payload)
    missing = required - keys
    extra = keys - required
    if missing:
        raise ValueError(f"{context} missing required fields: {sorted(missing)!r}")
    if extra:
        raise ValueError(f"{context} has unknown fields: {sorted(extra)!r}")


def _copy_json_mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    copied = _copy_json_payload(value, context)
    if not isinstance(copied, dict):
        raise TypeError(f"{context} must be a mapping")
    return copied


def _copy_json_payload(value: object, context: str) -> Any:
    if isinstance(value, Mapping):
        _require_string_keys(value, context)
        return {
            key: _copy_json_payload(item, f"{context}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json_payload(item, context) for item in value)
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"{context} contains a non-JSON-safe value")
```

If existing helper names conflict, keep the loader-specific behavior and adjust names consistently with the tests. Do not call `json.loads` or `json.dumps`.

## Task 3: Run Targeted Tests

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_turn_response_loader.py
```

Expected: all LM5G loader tests pass.

## Task 4: Run Nearby Regression

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py
```

Expected: all nearby LM5B-G tests pass.

## Task 5: Run Focused PlanGraph / Local-Worker Gate

Use the repo’s current focused PlanGraph/local-worker file list pattern. At minimum:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph*.py `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py
```

Expected: focused gate passes.

## Task 6: Static Scope and Boundary Checks

Run:

```powershell
git status --short
git diff --check origin/main
git diff --name-status origin/main
```

Before staging, `git status --short` may show the new test file as untracked. It must be the only untracked file introduced by LM5G:

```text
 M mcp_server/src/rook/agent/local_worker_turn_response.py
?? mcp_server/tests/test_local_worker_turn_response_loader.py
```

After staging or committing the intended implementation files, the full branch diff should be:

```text
A       docs/superpowers/specs/2026-06-30-lm5g-local-worker-response-loader-design.md
A       docs/superpowers/plans/2026-06-30-lm5g-local-worker-response-loader.md
M       mcp_server/src/rook/agent/local_worker_turn_response.py
A       mcp_server/tests/test_local_worker_turn_response_loader.py
```

Production diff must be limited to:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
```

No changes to LM5C/D/F production modules.

Quick production scans:

```powershell
rg -n "json\.loads|json\.dumps|from json|import json|Path\(|open\(" mcp_server\src\rook\agent\local_worker_turn_response.py
rg -n "compile_workflow_contract|run_current_step_stream|run_local_worker_turn|evaluate_local_worker_scenario_result|build_local_worker_scenario_report|dispose_local_worker_turn_response" mcp_server\src\rook\agent\local_worker_turn_response.py
```

The first scan should produce no output. The second scan may show existing or test-planned names only if the module already legitimately contains them; the authoritative guard is the function-scoped AST test in `test_local_worker_turn_response_loader.py`, which must pass.

Also verify guarded areas remain untouched:

```powershell
git diff --name-only origin/main..HEAD -- src/Rook src/RookNative operations_knowledge.json
```

Expected: no output.

## Task 7: Self-Review Checklist

Before requesting review, confirm:

- Loader accepts only already-parsed `Mapping` payloads.
- Loader requires `schema == LOCAL_WORKER_TURN_RESPONSE_SCHEMA`.
- Loader uses flat variant records and exact field sets.
- Loader rejects unknown response kinds.
- Loader requires nullable fields to be present where specified.
- Loader copies nested JSON-shaped payloads before LM5B construction.
- Loader does not alias caller payload containers.
- Loader does not validate `action_id` against context or allowed actions.
- Loader does not parse JSON text, read files, import YAML, call models, render prompts, dispatch actions, run workers, or evaluate scenarios.
- Function-scoped AST guard covers loader helpers and does not falsely fail on existing LM5B context imports elsewhere in the module.
- Branch diff uses `origin/main..HEAD` because local `main` may be stale in this worktree.

## Completion Recommendation

After successful verification, use `superpowers:finishing-a-development-branch` and prefer the normal PR stop:

```text
Push and create a Pull Request.
```
