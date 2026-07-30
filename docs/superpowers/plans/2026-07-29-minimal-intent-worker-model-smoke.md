# Minimal Intent-to-Worker Model Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one operator-only, separately authorized smoke that connects the fixed admitted intent to the exact frontier-Planner/local-worker hierarchy and a causal synthetic typed-tool boundary.

**Architecture:** One new script owns the operational guard, exact `hybrid` role resolution, construction of two unchanged `LiteLLMWorkerTransport` instances, the private causal fake executor, and bounded summary rendering. It delegates semantic and workflow behavior to `MinimalPlannerDraftAdapter` and `run_minimal_intent_worker_integration()`; one test module proves the path with monkeypatched transports and no external contact.

**Tech Stack:** Python 3.12, `asyncio`, `re`, `json`, existing Rook agent modules, LiteLLM transport construction, pytest.

## Global Constraints

- Base commit is `2e9faf0dd3df16bb14e7d6c024b09136fef752d0`.
- Create only `scripts/minimal_intent_worker_model_smoke.py` and `mcp_server/tests/test_minimal_intent_worker_model_smoke.py`; product modules remain unchanged.
- Fixed intent is exactly `Create a Grasshopper C# component with one A:double output and compile cleanly.`
- Resolve only `get_models("hybrid")`; require Planner `anthropic/claude-opus-4-6` and Worker `ollama_chat/qwen3-coder:30b-a3b-q8_0` before constructing either transport.
- Planner schema is exactly `build_minimal_planner_draft_response_schema()`, wrapped in a code-owned LiteLLM `response_format`; Planner `structured_response_schema` is `None` so no top-level `format` is emitted.
- Worker schema is exactly the private `_local_worker_response_union_schema()` passed through `structured_response_schema`; do not copy or promote it.
- Both transports use temperature zero, `max_tokens=1024`, `max_retries=0`, and `timeout_s=120.0`; no prompt-only fallback.
- One Planner call maximum; zero or one worker call; no retry, fallback, prompt repair, alternate model, model override, or deterministic output patch.
- No `ToolDispatcher`, real typed-tool bridge, Chat, MCP, Chirp, DSPy, product CLI registration, archive, preflight, readiness, attempt, checksum, or fingerprint machinery.
- Summary fields contain no raw prompt, response, worker code, rationale, diagnostic, credential, provider metadata, tool parameter, GUID, receipt, or LiteLLM telemetry.
- Call counts derive from control flow and native records, never telemetry or a counting wrapper.
- Do not launch the script with `--execute-live` during implementation, tests, review, or verification. One in-process Task 2 regression may call `main(["--execute-live"])` only with an exact valid Planner, invalid Worker, and fail-if-reached constructor/run sentinels; it must prove zero transport construction. No test may let that flag reach `_run_live_once` or an external capability.
- No provider, worker box, Rhino, or Grasshopper contact is authorized.

---

## File Structure

### `scripts/minimal_intent_worker_model_smoke.py`

Owns fixed constants, closed argument classification, exact role validation, two transport constructors, the private causal fake, delegation to the merged runner, native-record projections, and bounded JSON output. Product code never imports it.

### `mcp_server/tests/test_minimal_intent_worker_model_smoke.py`

Loads the script with `importlib.util.spec_from_file_location`, supplies deterministic transport doubles, and owns all vertical, refusal, causal-fake, summary, and static-surface coverage.

---

### Task 1: Build the smallest no-contact walking vertical

**Files:**
- Create: `scripts/minimal_intent_worker_model_smoke.py`
- Create: `mcp_server/tests/test_minimal_intent_worker_model_smoke.py`
- Reference: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py:76-305`
- Reference: `mcp_server/src/rook/agent/local_worker_model_transport.py:51-174`
- Reference: `mcp_server/tests/test_minimal_intent_worker_integration.py:35-376`

**Interfaces:**
- Consumes: `get_models("hybrid")`, `LiteLLMWorkerTransport`, `_local_worker_response_union_schema()`, `MinimalPlannerDraftAdapter`, `build_minimal_planner_draft_response_schema()`, and `run_minimal_intent_worker_integration()`.
- Produces: private `_classify_arguments(argv)`, `_resolve_hybrid_roles()`, `_run_live_once(roles)`, `_CausalFakeToolExecutor`, `_summary_from_result(roles, live_run)`, and script `main(argv=None) -> int`.

- [ ] **Step 1: Add the valid-red script loader and walking vertical**

Create the test file with the existing script-import pattern:

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
_SCRIPT = _ROOT / "scripts" / "minimal_intent_worker_model_smoke.py"

def _load_smoke():
    spec = importlib.util.spec_from_file_location(
        "minimal_intent_worker_model_smoke", _SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

SMOKE = _load_smoke()
```

Add a recording structural transport whose `send()` deep-copies the request and returns a supplied raw string. Planner output is exactly:

```python
{
    "goal": SMOKE._FIXED_INTENT,
    "capability": "grasshopper_csharp_component",
    "interface": {
        "inputs": [],
        "outputs": [{"name": "A", "type": "double"}],
    },
    "acceptance": "clean_compile_receipt",
}
```

Worker output is exactly:

```python
{
    "schema": "rook.local_worker_turn_response:v1",
    "kind": "action_request",
    "action_id": "draft_repair_params",
    "rationale": "Provide one bounded replacement body.",
    "input": {"code": "A = 42.0;", "mode": "body"},
}
```

Monkeypatch `SMOKE.LiteLLMWorkerTransport` with a factory that returns the Planner transport on construction one and Worker transport on construction two while retaining the exact kwargs.

Add:

```python
@pytest.mark.asyncio
async def test_internal_live_composition_reaches_native_terminal_without_contact(
    monkeypatch,
) -> None:
    roles = SMOKE._ResolvedRoles(
        profile="hybrid",
        planner_model="anthropic/claude-opus-4-6",
        worker_model="ollama_chat/qwen3-coder:30b-a3b-q8_0",
        profile_api_base=None,
    )
    live_run = await SMOKE._run_live_once(roles)
    assert len(planner_transport.calls) == 1
    assert len(worker_transport.calls) == 1
    assert live_run.result.terminal_stage == "terminal"
    assert live_run.result.terminal_reason == "terminal_node_selected:done"
    assert live_run.executor.tool_call_count == 2
    summary = SMOKE._summary_from_result(roles, live_run)
    assert summary["operator_status"] == "completed"
    assert summary["operator_reason"] == "native_terminal"
    assert summary["planner_calls"] == 1
    assert summary["worker_calls"] == 1
```

Call the internal composition directly. Do not call `main()` with the live flag.

- [ ] **Step 2: Run the walking test and confirm valid RED**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py::test_internal_live_composition_reaches_native_terminal_without_contact -q
```

Expected: collection fails because the script does not exist. An import typo after the script exists is not valid-red evidence.

- [ ] **Step 3: Implement constants, private types, and argument classification**

Create the script with these imports and constants:

```python
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

from rook.agent.local_worker_model_transport import (
    LiteLLMWorkerTransport,
    _local_worker_response_union_schema,
)  # noqa: E402
from rook.agent.minimal_intent_worker_integration import (
    MinimalIntentWorkerIntegrationResult,
    MinimalPlannerDraftAdapter,
    build_minimal_planner_draft_response_schema,
    run_minimal_intent_worker_integration,
)  # noqa: E402
from rook.agent.model_profiles import get_models  # noqa: E402

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
_MAX_BODY_UTF8_BYTES = 128
_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_FAKE_COMPONENT_GUID = "minimal-intent-model-smoke-component-guid"
_INITIAL_BODY_PATTERN = re.compile(
    r"[ \t]*A[ \t]*=[ \t]*(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)[ \t]*;[ \t]*",
    re.ASCII,
)
_UPDATE_BODY_PATTERN = re.compile(
    r"[ \t]*A[ \t]*=[ \t]*-?(?:0|[1-9][0-9]{0,8})"
    r"(?:\.[0-9]{1,16})?[dD]?[ \t]*;[ \t]*",
    re.ASCII,
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

Add:

```python
@dataclass(frozen=True, slots=True)
class _ResolvedRoles:
    profile: str
    planner_model: str
    worker_model: str
    profile_api_base: str | None

_ArgumentDecision = Literal[
    "live_execution_not_requested", "invalid_arguments", "execute_live"
]

def _classify_arguments(argv: Sequence[str]) -> _ArgumentDecision:
    supplied = list(argv)
    if supplied == []:
        return "live_execution_not_requested"
    if supplied == [_LIVE_FLAG]:
        return "execute_live"
    return "invalid_arguments"
```

- [ ] **Step 4: Implement exact role validation before construction**

```python
class _ProfileRefusal(ValueError):
    def __init__(self, reason: str, planner: str | None, worker: str | None):
        super().__init__(reason)
        self.reason = reason
        self.planner_model = planner
        self.worker_model = worker

def _bounded_identity(value: object) -> str | None:
    if type(value) is not str or not value or not value.isascii():
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
    return _ResolvedRoles(_PROFILE, planner, worker, models.api_base)
```

No `LiteLLMWorkerTransport` expression may run before this returns successfully.

- [ ] **Step 5: Implement the causal executor's successful path**

```python
class _SyntheticToolContractError(ValueError):
    pass

class _CausalFakeToolExecutor:
    def __init__(self) -> None:
        self.contract_failed = False
        self._call_markers: list[None] = []
        self._issued_guid: str | None = None

    @property
    def tool_call_count(self) -> int:
        return len(self._call_markers)

    def _fail(self) -> None:
        self.contract_failed = True
        raise _SyntheticToolContractError("synthetic tool contract rejected")

    def __call__(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        self._call_markers.append(None)
        if len(self._call_markers) == 1:
            return self._create(tool_name, params)
        if len(self._call_markers) == 2:
            return self._update(tool_name, params)
        self._fail()
```

Require the first call to equal:

```python
(
    "gh_create_csharp_script",
    {
        "code": _INITIAL_BODY,
        "pins_in": (),
        "pins_out": ("A:double",),
        "name": "RookMinimalRepairHandoff",
        "x": 375,
        "y": 1080,
    },
)
```

Full-match the body, capture `identifier`, and construct the diagnostic only as:

```python
diagnostic = (
    f"CS0103: The name '{identifier}' does not exist in the current context."
)
```

Issue `_FAKE_COMPONENT_GUID` in the existing create receipt. On update, require exact keys, the issued GUID, `mode == "body"`, `language == "csharp"`, exact built-in ASCII code no longer than 128 bytes, and `_UPDATE_BODY_PATTERN.fullmatch(code)`. Return the existing clean update receipt shape from `test_minimal_intent_worker_integration.py:286-340` with the issued GUID. Every rejection calls `_fail()` and retains no submitted value.

- [ ] **Step 6: Implement the internal composition and first summary projection**

Define `_LiveRun` after the executor:

```python
@dataclass(frozen=True, slots=True)
class _LiveRun:
    result: MinimalIntentWorkerIntegrationResult
    executor: _CausalFakeToolExecutor
```

Construct exactly:

```python
async def _run_live_once(roles: _ResolvedRoles) -> _LiveRun:
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
    executor = _CausalFakeToolExecutor()
    result = await run_minimal_intent_worker_integration(
        _FIXED_INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=executor,
    )
    return _LiveRun(result, executor)
```

Define the exact thirteen `_SUMMARY_FIELDS`. For a returned result derive Planner count `1`; derive Worker count `1` only when `result.handoff_result.adapter_record` exists. Classify `contract_failed` first, exact native terminal second, and other native stops third.

- [ ] **Step 7: Prove constructor values and actual LiteLLM materialization offline**

Capture both constructor calls from the walking vertical and exact-compare:

```python
assert planner_kwargs == {
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
assert worker_kwargs == {
    "model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
    "profile_api_base": admitted_api_base,
    "generation_params": {
        "temperature": 0,
        "max_tokens": 1024,
        "max_retries": 0,
    },
    "structured_response_schema":
        SMOKE._local_worker_response_union_schema(),
    "timeout_s": 120.0,
}
```

Store the original `LiteLLMWorkerTransport` class before replacing the script's constructor for the walking vertical. Recreate each real transport from the captured kwargs. Monkeypatch only `rook.agent.local_worker_model_transport.litellm.completion` with a capturing callable that returns a minimal response object, then call each real transport's `send()` with a deterministic prompt artifact.

Require:

```python
assert planner_call["response_format"] == SMOKE._planner_response_format()
assert planner_call["max_tokens"] == 1024
assert planner_call["max_retries"] == 0
assert planner_call["temperature"] == 0
assert "format" not in planner_call

assert worker_call["format"] == SMOKE._local_worker_response_union_schema()
assert worker_call["max_tokens"] == 1024
assert worker_call["max_retries"] == 0
assert worker_call["temperature"] == 0
assert "response_format" not in worker_call
```

Require exactly one schema-bearing key per call. Mutate each captured schema and prove a later composition builds a fresh code-owned value. The test stops at the monkeypatched `litellm.completion` boundary and makes no provider contact.

- [ ] **Step 8: Run the vertical and inherited seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py -q

& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall -f `
  scripts\minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py

git diff --check
```

Expected: all selected tests pass; compilation and diff checks exit zero; no command invokes the live flag.

- [ ] **Step 9: Commit Task 1 and stop for walking-vertical review**

```powershell
git add scripts/minimal_intent_worker_model_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_model_smoke.py
git diff --cached --check
git commit -m "feat: add minimal intent worker model smoke"
```

Stop for independent review of the traversal, constructor configs, causal fake, and absence of contact before Task 2.

---

### Task 2: Close the pre-contact guard and exact transport configuration

**Files:**
- Modify: `scripts/minimal_intent_worker_model_smoke.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_model_smoke.py`
- Reference: `mcp_server/src/rook/agent/model_profiles.py:47-73`
- Reference: `mcp_server/src/rook/agent/model_profiles.py:444-474`
- Reference: `mcp_server/src/rook/agent/local_worker_model_transport.py:113-174`

**Interfaces:**
- Consumes: the Task 1 argument classifier, role resolver, transport constructors, and summary projection.
- Produces: a closed pre-contact CLI boundary and constructor-argument evidence; no live execution.

- [ ] **Step 1: Add valid-red argument and zero-construction cases**

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

Test `main([])` and `main(["--unknown"])` while monkeypatching `get_models`, `LiteLLMWorkerTransport`, and `_run_live_once` to raise if touched. Parse the single JSON line and assert the exact thirteen-field refusal summary. Do not call `main(["--execute-live"])`.

- [ ] **Step 2: Add valid-red profile and role substitution cases**

Supply exact `ModelSet`-shaped values for:

- the admitted `hybrid` pair;
- wrong Planner only;
- wrong Worker only;
- both wrong;
- empty, non-ASCII, non-string, and 257-byte Planner or Worker identities.

For every refusal, replace `LiteLLMWorkerTransport` with a constructor that fails the test if invoked. Require `profile_identity_invalid` for malformed identities and `profile_role_mismatch` for well-formed substitutions. Prove no partial construction: a valid Planner identity plus bad Worker still constructs neither transport.

For that last equation, call the final `main(["--execute-live"])` entry in
process with the real resolver and a fail-if-reached constructor. Require the
bounded `profile_role_mismatch` summary and zero constructor calls. This is the
only permitted in-process live-flag invocation; it cannot reach
`_run_live_once`.

- [ ] **Step 3: Implement the refusal summaries and operator entry point**

Add closed helpers rather than a generic result framework:

```python
def _refusal_summary(
    reason: Literal[
        "live_execution_not_requested",
        "invalid_arguments",
        "profile_identity_invalid",
        "profile_role_mismatch",
    ],
    *,
    planner_model: str | None = None,
    worker_model: str | None = None,
) -> dict[str, object]:
    return {
        "operator_status": "refused",
        "operator_reason": reason,
        "intent": _FIXED_INTENT,
        "profile": _PROFILE,
        "planner_model": planner_model,
        "worker_model": worker_model,
        "planner_calls": 0,
        "worker_calls": 0,
        "tool_calls": 0,
        "terminal_stage": None,
        "terminal_reason": None,
        "planner_adapter_status": None,
        "worker_adapter_status": None,
    }

def _summary_from_result(
    roles: _ResolvedRoles,
    live_run: _LiveRun,
) -> dict[str, object]:
    result = live_run.result
    handoff = result.handoff_result
    worker_status = (
        handoff.adapter_record.status
        if handoff is not None and handoff.adapter_record is not None
        else None
    )
    if live_run.executor.contract_failed:
        status, reason = "failed", "synthetic_tool_contract_failure"
    elif (
        result.terminal_stage == "terminal"
        and result.terminal_reason == "terminal_node_selected:done"
    ):
        status, reason = "completed", "native_terminal"
    else:
        status, reason = "failed", "native_stop"
    return {
        "operator_status": status,
        "operator_reason": reason,
        "intent": _FIXED_INTENT,
        "profile": roles.profile,
        "planner_model": roles.planner_model,
        "worker_model": roles.worker_model,
        "planner_calls": 1,
        "worker_calls": int(
            handoff is not None and handoff.adapter_record is not None
        ),
        "tool_calls": live_run.executor.tool_call_count,
        "terminal_stage": result.terminal_stage,
        "terminal_reason": result.terminal_reason,
        "planner_adapter_status": result.planner_adapter_record.status,
        "worker_adapter_status": worker_status,
    }

def _internal_error_summary(roles: _ResolvedRoles) -> dict[str, object]:
    return {
        "operator_status": "failed",
        "operator_reason": "operator_internal_error",
        "intent": _FIXED_INTENT,
        "profile": roles.profile,
        "planner_model": roles.planner_model,
        "worker_model": roles.worker_model,
        "planner_calls": None,
        "worker_calls": None,
        "tool_calls": None,
        "terminal_stage": None,
        "terminal_reason": None,
        "planner_adapter_status": None,
        "worker_adapter_status": None,
    }

def _write_summary(summary: dict[str, object]) -> None:
    if tuple(summary) != _SUMMARY_FIELDS:
        raise RuntimeError("operator summary fields differ")
    print(json.dumps(summary, ensure_ascii=True, separators=(",", ":")))

def _exit_code(summary: dict[str, object]) -> int:
    if summary["operator_reason"] in {
        "live_execution_not_requested",
        "native_terminal",
    }:
        return 0
    return 1

def main(argv: Sequence[str] | None = None) -> int:
    supplied = tuple(sys.argv[1:] if argv is None else argv)
    decision = _classify_arguments(supplied)
    if decision != "execute_live":
        summary = _refusal_summary(decision)
        _write_summary(summary)
        return _exit_code(summary)
    try:
        roles = _resolve_hybrid_roles()
    except _ProfileRefusal as exc:
        summary = _refusal_summary(
            exc.reason,
            planner_model=exc.planner_model,
            worker_model=exc.worker_model,
        )
        _write_summary(summary)
        return _exit_code(summary)
    try:
        live_run = asyncio.run(_run_live_once(roles))
        summary = _summary_from_result(roles, live_run)
    except Exception:
        summary = _internal_error_summary(roles)
    _write_summary(summary)
    return _exit_code(summary)
```

`_write_summary()` canonically renders one compact JSON object with the exact thirteen fields and no extra diagnostics. Catch ordinary `Exception`, never `BaseException`. The implementation must not add argument parsing, environment overrides, retries, or alternate execution paths.

- [ ] **Step 4: Prove the operator surface is bounded without invoking live execution**

Add a subprocess test for no arguments and one for `--invalid-argument`. Assert exit behavior, exact summary shape, and absence of stderr secrets. Do not launch the script with `--execute-live`; only the pure classifier test may pass that string.

Search the script source in the test and reject `argparse`, `click`, model-override names, retry/fallback loops, `ToolDispatcher`, and product registration imports. Permit only the one literal live flag.

- [ ] **Step 5: Run and commit Task 2**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py -q

& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall -f `
  scripts\minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py

git diff --check
git add scripts/minimal_intent_worker_model_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_model_smoke.py
git diff --cached --check
git commit -m "test: close model smoke contact boundary"
```

Expected: all tests pass without constructing a real transport or invoking a provider, worker box, Rhino, or Grasshopper.

---

### Task 3: Prove causal synthetic execution and truthful summaries

**Files:**
- Modify: `scripts/minimal_intent_worker_model_smoke.py`
- Modify: `mcp_server/tests/test_minimal_intent_worker_model_smoke.py`
- Reference: `mcp_server/tests/test_minimal_intent_worker_integration.py:211-340`
- Reference: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py:261-305`

**Interfaces:**
- Consumes: actual typed-tool calls made by the merged handoff and native integration records returned by the runner.
- Produces: a fail-closed operator-only fake and an exact bounded summary; no production fake or new native outcome.

- [ ] **Step 1: Add exact numeric-body grammar boundaries**

Parameterize accepted bodies:

```python
(
    "A = 0;",
    "A=-1;",
    "A = 999999999;",
    "A = 0.5;",
    "A = -123456789.1234567890123456D;",
    (" " * 124) + "A=0;",  # exactly 128 UTF-8 bytes
)
```

Parameterize refused bodies:

```python
(
    object(),
    "A = 1m;",
    "A = 1f;",
    "A = 1000000000;",      # ten integral digits
    "A = 1e3;",
    "A = 1 + 2;",
    "A = Math.Sin(1);",
    "A = 1; B = 2;",
    "A = 1;\n",
    "A = ١;",
    (" " * 125) + "A=0;",  # 129 UTF-8 bytes
)
```

Each refused case must set `contract_failed`, raise `_SyntheticToolContractError`, retain no rejected value or violation detail, and make no later tool call. This is a full-match grammar; no substring extraction, trimming, normalization, or numeric conversion is allowed.

- [ ] **Step 2: Prove the create diagnostic and GUID are causally derived**

Test the first tool call directly and through the vertical:

- the exact received initial body is full-matched by `_INITIAL_BODY_PATTERN`;
- the diagnostic contains the captured identifier and changes when a test-only accepted identifier mutation is passed to the pure diagnostic helper;
- the full diagnostic is not a standalone code-owned constant;
- the create receipt issues `_FAKE_COMPONENT_GUID`;
- the second call must use that exact GUID;
- a different GUID, a second create, a third call, or update-before-create fails closed.

Keep the operational create contract itself exact: the real vertical still admits only `_INITIAL_BODY` and the fixed create name, position, and pins.

- [ ] **Step 3: Close every synthetic tool parameter boundary**

Add direct refusal tests for wrong tool name, call order, exact key set, initial body, name, `x`, `y`, `pins_in`, `pins_out`, update GUID, `mode`, `language`, and non-exact built-in body type. Prove rejected mappings are not retained. Do not add a fake registry or generic dispatcher.

- [ ] **Step 4: Prove native conversion and summary precedence**

Run the real integration with a worker response whose action body is syntactically invalid for the private fake. Require:

```python
assert live_run.executor.contract_failed is True
assert live_run.result.terminal_reason == "dispatch_failed"
assert summary["operator_status"] == "failed"
assert summary["operator_reason"] == "synthetic_tool_contract_failure"
```

Then produce an ordinary native stop without a fake-contract rejection and require `failed / native_stop`. Do not change or wrap the native `dispatch_failed` meaning.

- [ ] **Step 5: Prove call counts from control flow and native records**

Cover this closed matrix:

| Reached boundary | Planner | Worker | Tool |
|---|---:|---:|---:|
| Planner response/draft rejected | 1 | 0 | 0 |
| exact-goal mismatch | 1 | 0 | 0 |
| worker refusal/clarification | 1 | 1 | 1 |
| synthetic update rejection | 1 | 1 | 2 |
| native terminal success | 1 | 1 | 2 |
| unexpected exception without returned integration result | `null` | `null` | `null` |

For returned results, derive Planner count as one because the concrete adapter was invoked. Derive Worker count from `handoff_result.adapter_record` only. Derive tool count from the private executor's call markers. Supply contradictory fake transport telemetry and prove it cannot affect any count.

- [ ] **Step 6: Close the thirteen-field summary and exclusions**

Assert exact key order and set:

```python
(
    "operator_status",
    "operator_reason",
    "intent",
    "profile",
    "planner_model",
    "worker_model",
    "planner_calls",
    "worker_calls",
    "tool_calls",
    "terminal_stage",
    "terminal_reason",
    "planner_adapter_status",
    "worker_adapter_status",
)
```

Search serialized summaries for sentinel prompt, response, worker code, rationale, diagnostic, GUID, credential, provider metadata, telemetry, tool parameters, and receipt content; none may appear. Exact intent and resolved role identities must appear when known.

- [ ] **Step 7: Run and commit Task 3**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_integration.py `
  mcp_server\tests\test_minimal_csharp_repair_handoff.py -q

git diff --check
git add scripts/minimal_intent_worker_model_smoke.py `
  mcp_server/tests/test_minimal_intent_worker_model_smoke.py
git diff --cached --check
git commit -m "test: harden causal model smoke boundary"
```

---

### Task 4: Final no-contact verification and plan reconciliation

**Files:**
- Verify: `scripts/minimal_intent_worker_model_smoke.py`
- Verify: `mcp_server/tests/test_minimal_intent_worker_model_smoke.py`
- Modify: `docs/superpowers/plans/2026-07-29-minimal-intent-worker-model-smoke.md`

**Interfaces:**
- Consumes: the completed operator script and deterministic tests.
- Produces: fresh no-contact verification evidence and an accurate execution ledger; no live smoke.

- [ ] **Step 1: Run the new tests and inherited 573-test seam**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
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

Record exact passed, failed, skipped, warning, and elapsed results. The inherited set was 573 tests at design time; the new total is not known until this command completes.

- [ ] **Step 2: Run compilation and safe operator refusals only**

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m compileall -f `
  scripts\minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py

& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe `
  scripts\minimal_intent_worker_model_smoke.py

& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe `
  scripts\minimal_intent_worker_model_smoke.py --invalid-argument
```

The first script command must emit `live_execution_not_requested`; the second must emit `invalid_arguments`. Do not invoke `--execute-live`.

- [ ] **Step 3: Audit the exact surface and transaction**

```powershell
git diff --name-only 2e9faf0dd3df16bb14e7d6c024b09136fef752d0...HEAD
git diff --check
rg -n "ToolDispatcher|rook\.agent\.chat|dspy|mcp\.tool|readiness|preflight|checksum|fingerprint" `
  scripts\minimal_intent_worker_model_smoke.py
rg -n -- "--execute-live" `
  scripts\minimal_intent_worker_model_smoke.py `
  mcp_server\tests\test_minimal_intent_worker_model_smoke.py
```

Require exactly the approved four-file merge scope: specification, plan, operator script, and its test. Inspect the successful retained in-memory path and confirm exact role resolution precedes both constructors; one concrete Planner adapter call precedes strict admission; the merged runner owns compilation/worker/native results; the create receipt owns the GUID; the worker body owns the update code; and the summary derives counts from control flow/native records.

The `--execute-live` search may find the constant, pure classifier cases, and the single controlled Task 2 pre-construction refusal. It must find no command that launches the script with the flag and no test that allows the flag to reach `_run_live_once` or transport construction.

- [ ] **Step 4: Reconcile this plan with fresh evidence**

Mark every completed checkbox. Append an execution record containing:

- base and final feature HEAD;
- exact four-file scope;
- exact focused and broader test counts actually observed;
- compile and diff-check results;
- the two safe refusal command results;
- confirmation that no provider, worker box, Rhino, or Grasshopper contact occurred; and
- confirmation that `--execute-live` was never invoked.

Commit only the plan reconciliation:

```powershell
git add docs/superpowers/plans/2026-07-29-minimal-intent-worker-model-smoke.md
git diff --cached --check
git commit -m "docs: reconcile minimal model smoke plan"
```

- [ ] **Step 5: Stop for final independent implementation review**

Do not push, open a PR, merge, or request/run the live smoke until the implementation and execution ledger receive independent review.

---

## Completion Criteria

- [ ] Exactly one operator script and one test module implement the slice; merged product modules remain unchanged.
- [ ] The no-flag and invalid-argument paths construct no transports.
- [ ] Only the exact `hybrid` role pair can reach construction, and both roles are validated first.
- [ ] Planner uses only `response_format`, Worker uses only `format`, and both calls use temperature zero, `max_tokens=1024`, `max_retries=0`, and the 120-second timeout.
- [ ] The deterministic vertical traverses the real Planner adapter and merged intent/handoff path with one Planner call and one Worker call.
- [ ] The private fake derives the create diagnostic and GUID causally, accepts only the safe bounded numeric-body grammar, and reports contract failure truthfully.
- [ ] Call counts derive only from control flow, native records, and fake call markers.
- [ ] The thirteen-field summary contains no disallowed raw or sensitive evidence.
- [ ] The inherited 573-test seam plus new smoke tests pass at final verification.
- [ ] No provider, worker box, Rhino, or Grasshopper contact occurs during implementation or review.
- [ ] `--execute-live` remains uninvoked pending separate post-merge authorization.

## Separately Authorized Post-Merge Operation

After merge and only after explicit authorization, an operator may run exactly:

```powershell
& C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe `
  scripts\minimal_intent_worker_model_smoke.py --execute-live
```

That later operation permits one Planner call, zero or one Worker call, and zero Rhino/Grasshopper calls. It stops after the first returned result and authorizes no retry, fallback, alternate model, or real typed-tool execution.
