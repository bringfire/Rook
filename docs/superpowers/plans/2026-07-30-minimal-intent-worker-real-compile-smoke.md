# Minimal Intent-to-Worker Real Grasshopper Compile Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one operator-only, separately authorized smoke that runs the fixed Claude-Planner/Qwen-worker hierarchy through the existing real `ToolDispatcher` and stops after the native Grasshopper compile result.

**Architecture:** One new sibling script owns the live guard, exact model hierarchy, single-instance discovery, destructive empty-document preparation, restricted create/update executor, and bounded output. It delegates Planner admission, deterministic compilation, worker behavior, tool handling, receipts, and terminal meaning to existing product components; one new test module proves the orchestration without external contact.

**Tech Stack:** Python 3.12, `asyncio`, existing `LiteLLMWorkerTransport`, existing `ToolDispatcher`, existing Rook agent modules, pytest.

## Global Constraints

- Implementation base is `2bb2b5a7d7c708b738252ed96a4d0b547fbe45a2`; PR #515's merge is already an ancestor.
- Create only `scripts/minimal_intent_worker_real_compile_smoke.py` and `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`; modify only this plan for final reconciliation.
- Do not modify product modules, the synthetic smoke, its tests, model profiles, prompts, schemas, workflow contracts, topology, actions, tool handlers, or receipt contracts.
- Fixed intent is exactly `Create a Grasshopper C# component with one A:double output and compile cleanly.`
- Resolve only `get_models("hybrid")`; require Planner `anthropic/claude-opus-4-6` and Worker `ollama_chat/qwen3-coder:30b-a3b-q8_0` before discovery or live contact.
- Accept only no arguments, exact `--execute-live`, or refusal; no environment configuration, model override, port override, retry control, alternate intent, fallback, or second attempt.
- Discovery accepts exactly one surviving `pluginType == "native"` record with exact positive integer `processId` and `port`; PID is recorded identity only and constructor port owns transport targeting.
- Preparation is exactly `gh_status -> gh_document_new -> gh_status` on one dispatcher and frozen port, before either model transport is constructed.
- The pre-existing canvas must be ready, active, empty, and unsaved. The new document must be active, ready, empty, unsaved, and have a different document ID.
- The integration executor admits only the incomplete prefixes `[]`, `[gh_create_csharp_script]`, and `[gh_create_csharp_script, gh_update_script]`.
- Reject any execution parameter mapping containing `port` before prefix mutation or dispatcher entry.
- One Planner call maximum; zero or one Worker call; no retry, fallback, prompt repair, deterministic model-output patch, alternate model, save, cleanup, restoration, or additional tool.
- The new script contains no fake executor or synthetic receipt producer.
- Implementation, tests, review, and merge make no provider, worker-box, Rhino, or Grasshopper contact and never launch the script with `--execute-live`.
- Output contains no discovery paths, document IDs, prompts, responses, code, rationale, diagnostics, GUIDs, receipts, parameters, credentials, provider metadata, exception text, or LiteLLM telemetry.
- The result is ephemeral operator output, not an archive, checkpoint, preflight, readiness record, attempt identity, fingerprint, or scientific instrument.

## File Structure

### `scripts/minimal_intent_worker_real_compile_smoke.py`

Owns only:

- the exact live flag, intent, profile, roles, and model parameters;
- exact role validation;
- exact one-instance discovery and frozen target;
- dispatcher construction and three-call document preparation;
- the restricted create/update executor;
- delegation to `run_minimal_intent_worker_integration()`; and
- bounded summary and exit-code projection.

It imports and reuses:

```python
from rook.agent.local_worker_model_transport import (
    LiteLLMWorkerTransport,
    _local_worker_response_union_schema,
)
from rook.agent.minimal_intent_worker_integration import (
    MinimalIntentWorkerIntegrationResult,
    MinimalPlannerDraftAdapter,
    build_minimal_planner_draft_response_schema,
    run_minimal_intent_worker_integration,
)
from rook.agent.model_profiles import get_models
from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools
from rook.bridge import discover_instances
```

### `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

Loads the script by file path, supplies test-only scripted discovery,
dispatcher, Planner, and Worker responses, and verifies the complete operator
boundary without external contact. It does not add a reusable fake executor or
claim that scripted receipts prove real compilation.

---

### Task 1: No-contact walking vertical through the real composition seam

**Files:**
- Create: `scripts/minimal_intent_worker_real_compile_smoke.py`
- Create: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

**Interfaces:**
- Consumes: `get_models()`, `discover_instances()`, `ToolDispatcher`, `build_local_tools()`, `LiteLLMWorkerTransport`, `MinimalPlannerDraftAdapter`, and `run_minimal_intent_worker_integration()`.
- Produces: `_ProfileRefusal`, `_TargetRefusal`, `_ResolvedRoles`, `_ResolvedRhinoTarget`, `_PreparedDocument`, `_RestrictedRealToolExecutor`, `_LiveRun`, `_run_live_once()`, and the first bounded successful summary path.

- [ ] **Step 1: Add the valid-red script loader and walking-vertical fixtures**

Create the test module with an import-by-path loader. The loader must fail
because the script does not yet exist; an import typo after creation is not a
valid red state.

```python
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "minimal_intent_worker_real_compile_smoke.py"
_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_PRE_DOCUMENT_ID = "pre-document"
_POST_DOCUMENT_ID = "post-document"
_COMPONENT_GUID = "real-compile-smoke-test-component"


def _load_smoke():
    spec = importlib.util.spec_from_file_location(
        "minimal_intent_worker_real_compile_smoke",
        _SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke()
```

Add exact payload helpers:

```python
def _planner_payload() -> dict[str, Any]:
    return {
        "goal": _INTENT,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
        "acceptance": "clean_compile_receipt",
    }


def _worker_payload(body: str = "A = 42.0;") -> dict[str, Any]:
    return {
        "schema": "rook.local_worker_turn_response:v1",
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": "Provide one bounded replacement body.",
        "input": {"code": body, "mode": "body"},
    }


class _RawTransport:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self._raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        self.calls: list[dict[str, Any]] = []

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.calls.append(copy.deepcopy(dict(prompt_artifact)))
        return self._raw
```

Add one test-only dispatcher whose `dispatch()` returns, in order, the two
status rows, document-new row, and the existing receipt shapes used by the
merged handoff. Keep every response derived from its received call and reject
unexpected order or parameters in the test double.

```python
class _ScriptedDispatcher:
    def __init__(self, *, port: int, local_tools: dict[str, Any]) -> None:
        self.port = port
        self.local_tools = local_tools
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def dispatch(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, copy.deepcopy(params)))
        index = len(self.calls)
        if index == 1 and name == "gh_status" and params == {}:
            return _status(_PRE_DOCUMENT_ID)
        if index == 2 and name == "gh_document_new" and params == {}:
            return {"success": True, "data": {"Created": True}}
        if index == 3 and name == "gh_status" and params == {}:
            return _status(_POST_DOCUMENT_ID)
        if index == 4 and name == "gh_create_csharp_script":
            assert params["code"] == "A = DefinitelyMissingSymbol;"
            assert params["pins_in"] == ()
            assert params["pins_out"] == ("A:double",)
            diagnostic = (
                "CS0103: The name 'DefinitelyMissingSymbol' does not exist "
                "in the current context."
            )
            return {
                "success": True,
                "data": {
                    "script_receipt": {
                        "version": 1,
                        "operation": "create",
                        "language": "csharp",
                        "artifact_status": "created_with_errors",
                        "mutation": {
                            "status": "created",
                            "component_guid": _COMPONENT_GUID,
                        },
                        "verification": {
                            "status": "failed",
                            "target_error_count": 1,
                        },
                        "repair_anchor": {
                            "component_guid": _COMPONENT_GUID,
                            "language": "csharp",
                            "target_errors": [diagnostic],
                        },
                    }
                },
            }
        if index == 5 and name == "gh_update_script":
            assert params == {
                "guid": _COMPONENT_GUID,
                "code": "A = 42.0;",
                "mode": "body",
                "language": "csharp",
            }
            return {
                "script_receipt": {
                    "version": 1,
                    "operation": "update",
                    "language": "csharp",
                    "artifact_status": "usable",
                    "mutation": {
                        "status": "written",
                        "component_guid": _COMPONENT_GUID,
                    },
                    "verification": {
                        "status": "passed",
                        "target_error_count": 0,
                    },
                    "repair_anchor": {
                        "component_guid": _COMPONENT_GUID,
                        "language": "csharp",
                        "target_errors": [],
                    },
                }
            }
        raise AssertionError(f"unexpected scripted dispatch {index}: {name}")


def _status(document_id: str) -> dict[str, Any]:
    return {
        "success": True,
        "data": {
            "available": True,
            "ready_for_edit": True,
            "has_active_document": True,
            "document_id": document_id,
            "object_count": 0,
            "document_path": "",
        },
    }
```

- [ ] **Step 2: Run the loader test and verify the intended red state**

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py -q
```

Expected: collection fails because
`scripts/minimal_intent_worker_real_compile_smoke.py` does not exist.

- [ ] **Step 3: Add the script constants, exact types, and pure builders**

Create the script with the same repository-path bootstrap and fixed model
construction constants as the synthetic sibling. Do not import that sibling.

```python
#!/usr/bin/env python
"""Operator-only real Grasshopper compile smoke for the minimal handoff."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

from rook.agent.local_worker_model_transport import (  # noqa: E402
    LiteLLMWorkerTransport,
    _local_worker_response_union_schema,
)
from rook.agent.minimal_intent_worker_integration import (  # noqa: E402
    MinimalIntentWorkerIntegrationResult,
    MinimalPlannerDraftAdapter,
    build_minimal_planner_draft_response_schema,
    run_minimal_intent_worker_integration,
)
from rook.agent.model_profiles import get_models  # noqa: E402
from rook.agent.tool_dispatcher import (  # noqa: E402
    ToolDispatcher,
    build_local_tools,
)
from rook.bridge import discover_instances  # noqa: E402

_FIXED_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_PROFILE = "hybrid"
_PLANNER_MODEL = "anthropic/claude-opus-4-6"
_WORKER_MODEL = "ollama_chat/qwen3-coder:30b-a3b-q8_0"
_LIVE_FLAG = "--execute-live"
_TIMEOUT_S = 120.0
_MAX_OUTPUT_TOKENS = 1024
_MAX_RETRIES = 0
_MAX_MODEL_ID_UTF8_BYTES = 256
```

Define exact data carriers:

```python
@dataclass(frozen=True, slots=True)
class _ResolvedRoles:
    profile: str
    planner_model: str
    worker_model: str
    profile_api_base: str | None


@dataclass(frozen=True, slots=True)
class _ResolvedRhinoTarget:
    process_id: int
    port: int


@dataclass(frozen=True, slots=True)
class _PreparedDocument:
    state: Literal["fresh_document_verified"]
    tool_calls: int


@dataclass(frozen=True, slots=True)
class _LiveRun:
    result: MinimalIntentWorkerIntegrationResult
    target: _ResolvedRhinoTarget
    preparation: _PreparedDocument
    executor: _RestrictedRealToolExecutor
```

Because `_LiveRun` refers to the later executor class, either place `_LiveRun`
after `_RestrictedRealToolExecutor` or use a quoted annotation. Do not weaken
the exact runtime type checks to accommodate declaration order.

Define the two refusal types before either resolver:

```python
class _ProfileRefusal(ValueError):
    def __init__(
        self,
        reason: str,
        planner_model: str | None,
        worker_model: str | None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.planner_model = planner_model
        self.worker_model = worker_model


class _TargetRefusal(ValueError):
    def __init__(
        self,
        reason: str,
        process_id: int | None,
        port: int | None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.process_id = process_id
        self.port = port
```

Implement the fixed role and Planner-schema equations directly in the new
script:

```python
def _bounded_identity(value: object) -> str | None:
    if type(value) is not str or not value.strip() or not value.isascii():
        return None
    if len(value.encode("utf-8")) > _MAX_MODEL_ID_UTF8_BYTES:
        return None
    return value


def _resolve_hybrid_roles() -> _ResolvedRoles:
    models = get_models(_PROFILE)
    planner = _bounded_identity(models.planner)
    worker = _bounded_identity(models.worker)
    if planner is None or worker is None:
        raise _ProfileRefusal("profile_identity_invalid", planner, worker)
    if planner != _PLANNER_MODEL or worker != _WORKER_MODEL:
        raise _ProfileRefusal("profile_role_mismatch", planner, worker)
    return _ResolvedRoles(
        profile=_PROFILE,
        planner_model=planner,
        worker_model=worker,
        profile_api_base=models.api_base,
    )


def _planner_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "minimal_planner_draft",
            "strict": True,
            "schema": build_minimal_planner_draft_response_schema(),
        },
    }
```

The response schemas are rebuilt freshly by
`build_minimal_planner_draft_response_schema()` and
`_local_worker_response_union_schema()` at transport construction. The new
script owns this intentional operator-level duplication; it imports no private
helper from the synthetic smoke.

- [ ] **Step 4: Implement the happy-path target, preparation, and restricted executor**

Add pure target validation:

```python
def _resolve_single_rhino_target(
    instances: object,
) -> _ResolvedRhinoTarget:
    if type(instances) is not list:
        raise _TargetRefusal("rooknative_identity_invalid", None, None)
    native = [
        row
        for row in instances
        if type(row) is dict and row.get("pluginType") == "native"
    ]
    if not native:
        raise _TargetRefusal("rooknative_instance_absent", None, None)
    if len(native) != 1:
        raise _TargetRefusal("rooknative_instance_ambiguous", None, None)
    row = native[0]
    process_id = row.get("processId")
    port = row.get("port")
    if (
        type(process_id) is not int
        or process_id <= 0
        or type(port) is not int
        or port <= 0
    ):
        raise _TargetRefusal(
            "rooknative_identity_invalid",
            process_id if type(process_id) is int else None,
            port if type(port) is int else None,
        )
    return _ResolvedRhinoTarget(process_id=process_id, port=port)
```

Add strict status and document-new parsers. Use `type(value) is ...` before
every comparison. The status parser returns the exact nonblank document ID;
the post parser takes the pre-ID and rejects equality.

```python
def _require_status(
    result: object,
    *,
    previous_document_id: str | None,
) -> str:
    if type(result) is not dict or result.get("success") is not True:
        raise ValueError("status rejected")
    data = result.get("data")
    if type(data) is not dict:
        raise ValueError("status data rejected")
    document_id = data.get("document_id")
    object_count = data.get("object_count")
    if (
        data.get("available") is not True
        or data.get("ready_for_edit") is not True
        or data.get("has_active_document") is not True
        or type(document_id) is not str
        or not document_id
        or type(object_count) is not int
        or object_count != 0
        or type(data.get("document_path")) is not str
        or data.get("document_path") != ""
        or (
            previous_document_id is not None
            and document_id == previous_document_id
        )
    ):
        raise ValueError("status equations rejected")
    return document_id


def _require_document_new(result: object) -> None:
    if type(result) is not dict or result.get("success") is not True:
        raise ValueError("document new rejected")
    data = result.get("data")
    if type(data) is not dict or data.get("Created") is not True:
        raise ValueError("document new data rejected")
```

Implement the happy-path `_prepare_fresh_document()` with exact order and no
polling. Task 2 replaces direct exceptions with typed, state-bearing failures.

```python
async def _prepare_fresh_document(
    dispatcher: ToolDispatcher,
) -> _PreparedDocument:
    pre = await dispatcher.dispatch("gh_status", {})
    pre_id = _require_status(pre, previous_document_id=None)
    created = await dispatcher.dispatch("gh_document_new", {})
    _require_document_new(created)
    post = await dispatcher.dispatch("gh_status", {})
    _require_status(post, previous_document_id=pre_id)
    return _PreparedDocument(
        state="fresh_document_verified",
        tool_calls=3,
    )
```

Define the executor so the port check and prefix check both precede mutation:

```python
class _RestrictedRealToolExecutor:
    __slots__ = ("_dispatch", "_calls")

    def __init__(self, dispatch: Any) -> None:
        if not callable(dispatch):
            raise TypeError("dispatch must be callable")
        self._dispatch = dispatch
        self._calls: list[str] = []

    @property
    def call_names(self) -> tuple[str, ...]:
        return tuple(self._calls)

    async def __call__(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if type(tool_name) is not str or type(params) is not dict:
            raise TypeError("restricted tool call shape differs")
        if "port" in params:
            raise ValueError("restricted tool parameters contain port")
        expected = (
            "gh_create_csharp_script"
            if not self._calls
            else "gh_update_script"
            if self._calls == ["gh_create_csharp_script"]
            else None
        )
        if expected is None or tool_name != expected:
            raise ValueError("restricted tool sequence differs")
        self._calls.append(tool_name)
        result = self._dispatch(tool_name, params)
        if hasattr(result, "__await__"):
            result = await result
        if type(result) is not dict:
            raise TypeError("dispatcher result must be an exact object")
        return result
```

The executor records a legitimate dispatch attempt before awaiting it. It
must not append anything for a port, shape, or prefix refusal.

- [ ] **Step 5: Implement the happy-path live composition**

Construct the dispatcher and finish preparation before constructing either
model transport:

```python
async def _run_live_once(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
) -> _LiveRun:
    dispatcher = ToolDispatcher(
        port=target.port,
        local_tools=build_local_tools(),
    )
    preparation = await _prepare_fresh_document(dispatcher)

    planner_transport = LiteLLMWorkerTransport(
        model=roles.planner_model,
        profile_api_base=roles.profile_api_base,
        generation_params={
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "max_retries": _MAX_RETRIES,
            "response_format": _planner_response_format(),
        },
        structured_response_schema=None,
        timeout_s=_TIMEOUT_S,
    )
    worker_transport = LiteLLMWorkerTransport(
        model=roles.worker_model,
        profile_api_base=roles.profile_api_base,
        generation_params={
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "max_retries": _MAX_RETRIES,
        },
        structured_response_schema=_local_worker_response_union_schema(),
        timeout_s=_TIMEOUT_S,
    )
    executor = _RestrictedRealToolExecutor(dispatcher.dispatch)
    result = await run_minimal_intent_worker_integration(
        _FIXED_INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=executor,
    )
    return _LiveRun(
        result=result,
        target=target,
        preparation=preparation,
        executor=executor,
    )
```

Implement the initial `_summary_from_result()` so completed status requires:

```python
completed = (
    live_run.preparation.state == "fresh_document_verified"
    and live_run.executor.call_names
    == ("gh_create_csharp_script", "gh_update_script")
    and result.terminal_stage == "terminal"
    and result.terminal_reason == "terminal_node_selected:done"
)
```

All other returned native results use `failed / native_stop`; Task 3 hardens
redaction and all summary states.

- [ ] **Step 6: Add and run the walking vertical**

Monkeypatch, in order:

- `SMOKE.ToolDispatcher` to `_ScriptedDispatcher`;
- `SMOKE.build_local_tools` to return a mapping containing exact create/update
  keys;
- `SMOKE.LiteLLMWorkerTransport` to return the Planner then Worker raw
  transports.

Call `_run_live_once()` directly with exact roles and target. Assert:

```python
assert live_run.result.terminal_stage == "terminal"
assert live_run.result.terminal_reason == "terminal_node_selected:done"
assert live_run.preparation.state == "fresh_document_verified"
assert live_run.preparation.tool_calls == 3
assert live_run.executor.call_names == (
    "gh_create_csharp_script",
    "gh_update_script",
)
assert dispatcher.calls == [
    ("gh_status", {}),
    ("gh_document_new", {}),
    ("gh_status", {}),
    ("gh_create_csharp_script", expected_create_params),
    ("gh_update_script", expected_update_params),
]
```

Also assert the create response originates `_COMPONENT_GUID`, the update call
uses that exact GUID, and the update body equals the Worker response body.

Run:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py::test_no_contact_walking_vertical_reaches_native_terminal -q
```

Expected: `1 passed`; no external contact.

- [ ] **Step 7: Run the inherited compositor seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 1 and stop for a vertical review checkpoint**

```powershell
git add scripts/minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
git commit -m "feat: add real compile smoke walking vertical"
```

Stop for independent review of the real transaction ordering before Task 2.

---

### Task 2: Close argument, role, discovery, and document-preparation boundaries

**Files:**
- Modify: `scripts/minimal_intent_worker_real_compile_smoke.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

**Interfaces:**
- Consumes: Task 1's role/target refusals, roles, target, dispatcher construction, and preparation functions.
- Produces: `_PreparationFailure`, complete `_prepare_fresh_document()`, `_classify_arguments()`, and pre-model `main()` outcomes.

- [ ] **Step 1: Add valid-red argument and profile-order tests**

Parameterize `_classify_arguments()` over:

```python
(
    ([], "live_execution_not_requested"),
    (["--execute-live"], "execute_live"),
    (["--unknown"], "invalid_arguments"),
    (["--execute-live", "extra"], "invalid_arguments"),
    (["--execute-live", "--execute-live"], "invalid_arguments"),
)
```

For no arguments and invalid arguments, replace `get_models`,
`discover_instances`, `ToolDispatcher`, and `_run_live_once` with
fail-if-reached sentinels. Require zero contact and the exact refusal summary.

For `main(["--execute-live"])`, add profile-load failure, malformed role,
Planner substitution, Worker substitution, and valid-Planner/invalid-Worker
cases. Require discovery and dispatcher construction to remain zero.

- [ ] **Step 2: Add valid-red discovery tests**

Use exact rows:

```python
{"pluginType": "native", "processId": 4001, "port": 9877}
```

Cover:

- no rows;
- roadcreator-only rows;
- two valid native rows;
- missing, boolean, zero, negative, string, and equality-spoof process ID;
- missing, boolean, zero, negative, string, and equality-spoof port; and
- one valid native plus unrelated roadcreator rows.

Every refusal must prove zero `ToolDispatcher` and model transport
construction. The valid row must produce exact `_ResolvedRhinoTarget(4001,
9877)`. No environment mutation may change it.

- [ ] **Step 3: Add valid-red strict pre-status and post-status tables**

Start from:

```python
{
    "success": True,
    "data": {
        "available": True,
        "ready_for_edit": True,
        "has_active_document": True,
        "document_id": "document-1",
        "object_count": 0,
        "document_path": "",
    },
}
```

Mutate independently:

- result and data to subclasses/non-dicts;
- `success`, `available`, `ready_for_edit`, and `has_active_document` to every
  non-`True` or equality-spoof value;
- document ID to missing, empty, non-string, and equality-spoof values;
- object count to missing, `False`, `True`, `-1`, `1`, float, string, and
  equality-spoof values;
- document path to missing, non-string, saved path, and equality-spoof values;
  and
- post document ID to the exact pre document ID.

Require pre-status mutations to stop after one preparation call with
`status_rejected`. Require post-status mutations to stop after three calls
with `document_new_started`. Both construct zero model transports.

- [ ] **Step 4: Add valid-red document-new response tests**

The admitted row is exactly:

```python
{"success": True, "data": {"Created": True}}
```

Reject result/data subclasses, false or equality-spoof success, missing data,
missing `Created`, false `Created`, and equality-spoof `Created`. Require two
preparation calls, `document_new_started`, and zero model construction.

- [ ] **Step 5: Add all preparation exception and timeout cases**

Parameterize `RuntimeError("PREPARATION_SENTINEL")` and `TimeoutError(
"PREPARATION_SENTINEL")` at each call. Assert:

```text
pre-status:     state=status_rejected,       calls=1
document-new:   state=document_new_started,  calls=2
post-status:    state=document_new_started,  calls=3
```

For every case, parse stdout and prove `PREPARATION_SENTINEL` is absent, both
model constructors are untouched, and no later dispatcher call occurs.

- [ ] **Step 6: Implement typed failure carriers and exact preparation flow**

Add:

```python
class _PreparationFailure(RuntimeError):
    def __init__(
        self,
        reason: str,
        state: Literal["status_rejected", "document_new_started"],
        tool_calls: int,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.state = state
        self.tool_calls = tool_calls
```

Implement preparation without a loop:

```python
async def _prepare_fresh_document(
    dispatcher: ToolDispatcher,
) -> _PreparedDocument:
    calls = 1
    try:
        pre = await dispatcher.dispatch("gh_status", {})
    except Exception as exc:
        raise _PreparationFailure(
            "pre_status_exception", "status_rejected", calls
        ) from exc
    try:
        pre_id = _require_status(pre, previous_document_id=None)
    except (TypeError, ValueError) as exc:
        raise _PreparationFailure(
            "pre_status_rejected", "status_rejected", calls
        ) from exc

    calls = 2
    try:
        created = await dispatcher.dispatch("gh_document_new", {})
    except Exception as exc:
        raise _PreparationFailure(
            "document_new_exception", "document_new_started", calls
        ) from exc
    try:
        _require_document_new(created)
    except (TypeError, ValueError) as exc:
        raise _PreparationFailure(
            "document_new_rejected", "document_new_started", calls
        ) from exc

    calls = 3
    try:
        post = await dispatcher.dispatch("gh_status", {})
    except Exception as exc:
        raise _PreparationFailure(
            "post_status_exception", "document_new_started", calls
        ) from exc
    try:
        _require_status(post, previous_document_id=pre_id)
    except (TypeError, ValueError) as exc:
        raise _PreparationFailure(
            "post_status_rejected", "document_new_started", calls
        ) from exc
    return _PreparedDocument(
        state="fresh_document_verified",
        tool_calls=calls,
    )
```

The internal successful pre-status branch is `status_verified`; no observable
failure may label it `status_rejected`. Set `document_new_started` before the
second await, as represented by every second/third-call failure carrier.

- [ ] **Step 7: Implement pre-contact and preparation summaries in `main()`**

Order the live branch exactly:

```python
roles = _resolve_hybrid_roles()
target = _resolve_single_rhino_target(discover_instances())
live_run = asyncio.run(_run_live_once(roles, target))
```

Profile and target refusals return `operator_status="refused"` with
`document_preparation_status="not_started"` and
`preparation_tool_calls=0`. `_PreparationFailure` returns
`operator_status="preparation_failed"`, the carried safe reason/state/count,
the frozen process ID/port, and zero Planner/Worker calls. Generic exceptions
use `operator_internal_error` without exception text.

- [ ] **Step 8: Run Task 2 tests and inherited guard tests**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py -q
```

Expected: all tests pass; no external contact.

- [ ] **Step 9: Commit Task 2**

```powershell
git add scripts/minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
git commit -m "test: close real compile smoke preparation"
```

---

### Task 3: Close restricted-executor lineage and bounded output

**Files:**
- Modify: `scripts/minimal_intent_worker_real_compile_smoke.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`

**Interfaces:**
- Consumes: Task 1's restricted executor and native integration result; Task 2's target and preparation carriers.
- Produces: exact prefix enforcement, zero-dispatch port protection, complete summary validation, safe reason projection, and truthful incomplete-prefix handling.

- [ ] **Step 1: Add exact restricted-prefix tests**

Use a recording async dispatch callable. Prove these prefixes do not fail
merely because they are incomplete:

```python
()
("gh_create_csharp_script",)
("gh_create_csharp_script", "gh_update_script")
```

For each accepted call, require exact parameter object equality at the
recording dispatcher. Directly reject:

- update before create;
- second create;
- second update;
- substituted tool;
- third call; and
- any call after update.

Require every rejected prefix to leave both `executor.call_names` and the
recording dispatcher's calls unchanged from their pre-call snapshots.

- [ ] **Step 2: Add zero-dispatch per-call port override tests**

Parameterize both allowed tools with mappings containing:

```python
{"port": 12345}
{"port": None}
{"port": 0}
{"port": object()}
```

For update cases, first complete the admitted create. Snapshot both ledgers,
then assert the port-bearing call raises before either ledger changes. Use a
dispatch callable that fails the test if invoked by the mutated call. Zero calls
from each override attempt may reach the dispatcher.

- [ ] **Step 3: Prove incomplete create prefix remains a native stop**

Run the real merged integration with:

- valid Planner payload;
- scripted create receipt that needs repair; and
- this exact admitted local-worker refusal response:

```python
{
    "schema": "rook.local_worker_turn_response:v1",
    "kind": "refusal",
    "category": "insufficient_context",
    "reason": "A repair cannot be determined.",
}
```

Require:

```python
assert live_run.executor.call_names == ("gh_create_csharp_script",)
assert live_run.result.terminal_stage == "worker_disposition"
assert summary["operator_status"] == "failed"
assert summary["operator_reason"] == "native_stop"
assert summary["execution_tool_calls"] == 1
```

Use the exact existing worker response schema and disposition vocabulary; do
not invent a new refusal meaning.

- [ ] **Step 4: Add completion-prefix mismatch tests**

Retain a valid native terminal result from the Task 1 vertical. Pair it with a
fresh executor whose ledger is `[]` and then `[create]`. `_summary_from_result`
must raise an internal-contract error rather than print `completed`. The exact
`[create, update]` ledger must produce `completed / native_terminal`.

- [ ] **Step 5: Add bounded-summary and sentinel tests**

Require the exact ordered field tuple:

```python
(
    "operator_status",
    "operator_reason",
    "intent",
    "profile",
    "planner_model",
    "worker_model",
    "rooknative_process_id",
    "rooknative_port",
    "document_preparation_status",
    "preparation_tool_calls",
    "planner_calls",
    "worker_calls",
    "execution_tool_calls",
    "terminal_stage",
    "terminal_reason",
    "planner_adapter_status",
    "worker_adapter_status",
)
```

Inject `SENSITIVE_SENTINEL` separately through discovery paths, preparation
exceptions, Planner response text, Worker response/rationale/code, tool
diagnostics, GUIDs, receipts, and unknown terminal reasons. Serialize the
summary and assert the sentinel is absent. Unknown terminal reasons must map to
`native_reason_unclassified`.

- [ ] **Step 6: Implement exact summary validation and safe projection**

Define the complete safe native-reason vocabulary in this script; do not
import a private helper from the synthetic smoke:

```python
_SAFE_TERMINAL_REASON_TOKENS = frozenset(
    {
        "clarification_needed",
        "dispatch_failed",
        "draft_payload_rejected",
        "executed verifier step 'verify_create'",
        "goal_mismatch",
        "invalid_code",
        "invalid_mode",
        "observation_recorded",
        "refusal_recorded",
        "response_duplicate_key",
        "response_invalid_json",
        "response_nonfinite_number",
        "response_not_object",
        "response_not_string",
        "response_not_utf8",
        "response_too_large",
        "response_trailing_content",
        "selector_halt:none_ready",
        "terminal_node_selected:done",
        "transport_failed",
        "unexpected_action_input_key",
    }
)
_TERMINAL_REASON_CATEGORY_PREFIXES = (
    ("transport_error:", "worker_transport_error"),
    ("raw_output_invalid:", "worker_raw_output_invalid"),
    ("response_payload_invalid:", "worker_response_payload_invalid"),
    ("blocked:", "worker_response_blocked"),
)


def _project_terminal_reason(reason: object) -> str:
    if type(reason) is not str:
        return "native_reason_unclassified"
    if reason in _SAFE_TERMINAL_REASON_TOKENS:
        return reason
    for prefix, category in _TERMINAL_REASON_CATEGORY_PREFIXES:
        if reason.startswith(prefix):
            return category
    return "native_reason_unclassified"
```

Derive counts exactly:

```python
handoff = result.handoff_result
worker_calls = int(
    handoff is not None and handoff.adapter_record is not None
)
execution_tool_calls = len(live_run.executor.call_names)
```

`planner_calls=1` is emitted only for a returned
`MinimalIntentWorkerIntegrationResult`. Generic exceptions before a returned
result use `None` for unprovable model/execution counts.

Validate every summary before writing:

```python
if tuple(summary) != _SUMMARY_FIELDS:
    raise RuntimeError("operator summary fields differ")
```

Print with:

```python
json.dumps(summary, ensure_ascii=True, separators=(",", ":"))
```

No helper may accept arbitrary additional output fields.

- [ ] **Step 7: Run Task 3 tests and the complete handoff seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py `
  mcp_server\tests\test_plan_graph_current_step_runner.py -q
```

Expected: all selected tests pass; no external contact.

- [ ] **Step 8: Commit Task 3**

```powershell
git add scripts/minimal_intent_worker_real_compile_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py
git commit -m "test: harden real compile smoke boundary"
```

---

### Task 4: Verify the operator surface and prepare the reviewed handoff

**Files:**
- Modify: `mcp_server/tests/test_minimal_intent_worker_real_compile_smoke.py`
- Modify: `docs/superpowers/plans/2026-07-30-minimal-intent-worker-real-compile-smoke.md`
- Verify: `scripts/minimal_intent_worker_real_compile_smoke.py`

**Interfaces:**
- Consumes: completed script and deterministic test module.
- Produces: no-contact transport/materialization evidence, safe CLI evidence, complete focused regression evidence, and an accurate plan execution ledger.

- [ ] **Step 1: Add exact constructor and provider-materialization tests**

Capture both `LiteLLMWorkerTransport` constructor calls after successful
preparation. Exact-compare Planner kwargs:

```python
{
    "model": "anthropic/claude-opus-4-6",
    "profile_api_base": admitted_api_base,
    "generation_params": {
        "temperature": 0,
        "max_tokens": 1024,
        "max_retries": 0,
        "response_format": SMOKE._planner_response_format(),
    },
    "structured_response_schema": None,
    "timeout_s": 120.0,
}
```

Exact-compare Worker kwargs:

```python
{
    "model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
    "profile_api_base": admitted_api_base,
    "generation_params": {
        "temperature": 0,
        "max_tokens": 1024,
        "max_retries": 0,
    },
    "structured_response_schema": _local_worker_response_union_schema(),
    "timeout_s": 120.0,
}
```

Recreate real transports from those kwargs and monkeypatch only
`rook.agent.local_worker_model_transport.litellm.completion`. Assert actual
materialization emits Planner `response_format` with no `format`, Worker
`format` with no duplicate `response_format`, and the exact token/retry values.

Also require the executing runtime to report:

```python
litellm.supports_response_schema(
    model="anthropic/claude-opus-4-6"
) is True
```

and `response_format` in the model's supported OpenAI parameters. This test is
offline because `litellm.completion` is replaced before transport send.

- [ ] **Step 2: Prove dispatcher construction uses existing product seams**

Instantiate the actual `build_local_tools()` without dispatching. Require
exact callable entries for `gh_create_csharp_script` and `gh_update_script`.
Capture `ToolDispatcher` construction in the walking vertical and prove it
receives the frozen port and that exact local-tools mapping.

Search the new script and fail review if it imports `_mcp_tool_executor`,
creates a fake executor, defines receipt fabrication, or calls any tool name
outside the four-name vocabulary.

- [ ] **Step 3: Add safe subprocess refusal tests**

Run the script with no arguments and with `--invalid-argument`. Parse exactly
one stdout JSON line, require empty stderr, and assert:

```text
no arguments:       exit 0, refused/live_execution_not_requested
invalid arguments:  exit 1, refused/invalid_arguments
```

Both must report `document_preparation_status=not_started`, zero preparation,
Planner, Worker, and execution calls, and null RookNative identity.

Do not launch a subprocess with `--execute-live`.

- [ ] **Step 4: Run the new tests and complete prior 654-test seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
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

Expected: the prior 654 tests plus the new module's collected tests all pass.
Record the exact fresh count; do not preserve `654` as the new total.

- [ ] **Step 5: Run compilation, diff, and source-surface checks**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall -f `
  scripts\minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py

git diff --check
git diff --name-only 2bb2b5a7d7c708b738252ed96a4d0b547fbe45a2...HEAD
rg -n "ToolDispatcher|build_local_tools|gh_status|gh_document_new|gh_create_csharp_script|gh_update_script" `
  scripts\minimal_intent_worker_real_compile_smoke.py
rg -n "ToolDispatcher|_mcp_tool_executor|synthetic|fake.*executor|script_receipt|ToolDispatcher\(" `
  scripts\minimal_intent_worker_real_compile_smoke.py
rg -n -- "--execute-live" `
  scripts\minimal_intent_worker_real_compile_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_real_compile_smoke.py
```

Review the search results rather than treating presence alone as failure:

- `ToolDispatcher` and `build_local_tools` must appear only in real
  construction/imports;
- the four exact tool names may appear only in preparation, restricted
  execution, summary/tests, and closed assertions;
- `_mcp_tool_executor`, a synthetic/fake executor class, and receipt production
  must be absent from the operator script;
- the live flag may appear in its constant, pure classifier, controlled
  in-process no-contact tests, and documentation; and
- no command or test may launch the real live branch.

The merge diff must contain exactly the approved four files: spec, plan,
operator script, and its test.

- [ ] **Step 6: Exercise only safe operator commands**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe `
  scripts\minimal_intent_worker_real_compile_smoke.py

& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe `
  scripts\minimal_intent_worker_real_compile_smoke.py --invalid-argument
```

Require the exact bounded refusal summaries and expected exit codes. Do not
invoke `--execute-live`.

- [ ] **Step 7: Reconcile this plan with fresh execution evidence**

Mark every operational checkbox complete and append an execution record with:

- implementation HEAD;
- exact focused test count and duration;
- compilation and diff-check results;
- exact four-file scope;
- safe refusal results;
- same-runtime Python and LiteLLM versions used for offline materialization;
- confirmation that no provider, worker box, Rhino, or Grasshopper contact
  occurred; and
- confirmation that the operator script was never launched with
  `--execute-live`.

Commit the documentation-only reconciliation separately:

```powershell
git add docs/superpowers/plans/2026-07-30-minimal-intent-worker-real-compile-smoke.md
git commit -m "docs: reconcile real compile smoke plan"
```

- [ ] **Step 8: Stop for final independent implementation review**

Do not push, open a PR, merge, or request/run the live smoke until the complete
four-file branch and fresh evidence receive independent review.

---

## Completion Criteria

- [ ] Exactly one sibling operator script and one test module are added; product modules and the synthetic smoke remain unchanged.
- [ ] Exact arguments and fixed model hierarchy stop every alternate path before discovery or contact.
- [ ] Exactly one native discovery record freezes one positive integer port; PID is recorded identity only.
- [ ] Preparation proves the existing canvas and replacement document are active, ready, empty, and unsaved before model construction.
- [ ] Preparation exceptions preserve truthful mutation state and expose no exception text.
- [ ] Per-call `port` parameters are rejected before executor-prefix mutation or dispatcher entry.
- [ ] Legitimate executor prefixes remain valid, including native stops after create without update.
- [ ] Only the existing native terminal plus exact create/update prefix produces completed status.
- [ ] Output is bounded and excludes all sensitive/model/tool evidence listed in the specification.
- [ ] The complete focused regression, compilation, diff, and source audit pass without external contact.
- [ ] No implementation or review command launches `--execute-live`.

## Post-merge live boundary

This plan does not authorize live execution. After merge and separate explicit
approval, use one clean merge-SHA checkout and the exact interpreter that
passes the same-runtime LiteLLM materialization test. The operator must first
provide exactly one live RookNative Rhino instance with Grasshopper already
loaded and an empty unsaved active canvas.

The only authorized command would then be:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe `
  scripts\minimal_intent_worker_real_compile_smoke.py --execute-live
```

That future operation permits one fixed transaction and no retry, fallback,
save, cleanup, restoration, alternate model, or second attempt. It leaves the
resulting Grasshopper document open and unsaved for operator inspection.
