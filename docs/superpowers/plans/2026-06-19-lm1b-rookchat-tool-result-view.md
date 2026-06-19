# LM1B RookChat Tool Result View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared internal `ToolResultView` adapter for model-visible tool outcomes and have ChatRunner use it for `tool_result` event decoration without changing dispatcher behavior, raw conversation history, or public MCP wire shape.

**Architecture:** The adapter lives in `mcp_server/src/rook/agent/chat/tool_contracts.py`, broadening that module to cover model-visible tool contracts. ChatRunner imports `normalize_tool_result(...)` and uses it only after the raw result has been serialized and stored. `ToolDispatcher.dispatch()` and `server._format_tool_result()` remain untouched.

**Tech Stack:** Python 3, dataclasses, `typing.Literal`, pytest, existing RookChat `ChatRunner`/`ToolRegistry` tests.

---

## File Structure

- Modify `mcp_server/tests/test_rookchat_tool_contracts.py`
  - Add adapter unit tests first. These tests define the result-truth precedence contract before implementation.

- Modify `mcp_server/src/rook/agent/chat/tool_contracts.py`
  - Add `ToolResultView`, `normalize_tool_result(...)`, and small private extraction helpers.
  - Keep existing schema and dispatchability helpers intact.

- Modify `mcp_server/tests/test_chat_runner.py`
  - Add ChatRunner tests for meta-tool, dispatcher-tool, exception-result, raw-history, and `ui_block` behavior.
  - Reuse existing `_make_tool_response`, `_make_text_response`, `_runtime_facts_patch`, and `_make_minimal_registry` helpers.

- Modify `mcp_server/tests/test_chat_runner_model_tools.py`
  - Add a chat-model pseudo-tool test proving `list_chat_models` `tool_result` events use the adapter.

- Modify `mcp_server/src/rook/agent/chat/chat_runner.py`
  - Import `normalize_tool_result`.
  - Remove `_classify_tool_status(...)` as an independent truth system or reduce it to adapter delegation.
  - Use the adapter for `tool_result` event decoration only.

No dispatcher files should change. No public MCP server files should change.

---

### Task 1: Add Failing Adapter Unit Tests

**Files:**
- Modify: `mcp_server/tests/test_rookchat_tool_contracts.py`

- [ ] **Step 1: Append result-view unit tests**

Append this block to `mcp_server/tests/test_rookchat_tool_contracts.py`:

```python
def test_normalize_tool_result_top_level_truth_precedence():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    top_failure = normalize_tool_result({
        "success": False,
        "data": {"success": True},
    })
    assert top_failure.status == "failed"

    top_success = normalize_tool_result({
        "success": True,
        "data": {"success": False, "error": "nested error"},
    })
    assert top_success.status == "success"
    assert top_success.error == "nested error"

    top_ok = normalize_tool_result({
        "ok": True,
        "data": {"ok": False},
    })
    assert top_ok.status == "success"


def test_normalize_tool_result_nested_truth_and_error_fallbacks():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    nested_success = normalize_tool_result({"data": {"ok": True}})
    assert nested_success.status == "success"

    top_error = normalize_tool_result({"error": "bad input"})
    assert top_error.status == "failed"
    assert top_error.error == "bad input"

    nested_error = normalize_tool_result({"data": {"error": "nested bad input"}})
    assert nested_error.status == "failed"
    assert nested_error.error == "nested bad input"

    non_string_error = normalize_tool_result({"error": {"code": "bad_input"}})
    assert non_string_error.status == "failed"
    assert non_string_error.error is None


def test_normalize_tool_result_ignores_status_strings_and_truth_like_values():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    status_only = normalize_tool_result({"status": "loaded"})
    assert status_only.status is None

    string_truth_with_error = normalize_tool_result({
        "success": "false",
        "error": "bad",
    })
    assert string_truth_with_error.status == "failed"
    assert string_truth_with_error.error == "bad"

    integer_truth_values = normalize_tool_result({
        "success": 1,
        "data": {"ok": 0},
    })
    assert integer_truth_values.status is None


def test_normalize_tool_result_non_dict_returns_empty_view():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    view = normalize_tool_result("plain text result")

    assert view.status is None
    assert view.verified is None
    assert view.verification_note is None
    assert view.message is None
    assert view.error is None


def test_normalize_tool_result_does_not_mutate_input_dict():
    from copy import deepcopy

    from rook.agent.chat.tool_contracts import normalize_tool_result

    raw = {
        "success": True,
        "message": "top message",
        "data": {
            "success": False,
            "verified": False,
            "message": "nested message",
        },
    }
    original = deepcopy(raw)

    view = normalize_tool_result(raw)

    assert view.status == "success"
    assert view.verified is False
    assert raw == original


def test_normalize_tool_result_message_and_error_extraction_are_string_only():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    top_strings = normalize_tool_result({
        "message": "top message",
        "error": "top error",
        "data": {
            "message": "nested message",
            "error": "nested error",
        },
    })
    assert top_strings.message == "top message"
    assert top_strings.error == "top error"

    nested_strings = normalize_tool_result({
        "message": {"text": "not a string"},
        "error": ["not", "a", "string"],
        "data": {
            "message": "nested message",
            "error": "nested error",
        },
    })
    assert nested_strings.status == "failed"
    assert nested_strings.message == "nested message"
    assert nested_strings.error == "nested error"


def test_normalize_tool_result_verification_precedence_and_fallback():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    top_verification = normalize_tool_result({
        "verified": True,
        "verification_note": "top note",
        "data": {
            "verified": False,
            "verification_note": "nested note",
            "message": "nested message",
        },
    })
    assert top_verification.verified is True
    assert top_verification.verification_note == "top note"

    nested_fallback = normalize_tool_result({
        "data": {
            "verified": False,
            "message": "No active Grasshopper canvas",
        },
    })
    assert nested_fallback.verified is False
    assert nested_fallback.verification_note == "No active Grasshopper canvas"

    top_message_is_not_verification_note = normalize_tool_result({
        "verified": False,
        "message": "This is an ordinary message",
    })
    assert top_message_is_not_verification_note.verified is False
    assert top_message_is_not_verification_note.verification_note is None

    non_string_top_note_falls_back_to_nested_note = normalize_tool_result({
        "verified": False,
        "verification_note": {"text": "not a string"},
        "data": {"verification_note": "nested note"},
    })
    assert non_string_top_note_falls_back_to_nested_note.verification_note == "nested note"
```

- [ ] **Step 2: Run the new adapter tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookchat_tool_contracts.py -q
```

Expected: FAIL with an import error similar to:

```text
ImportError: cannot import name 'normalize_tool_result'
```

- [ ] **Step 3: Leave the red tests uncommitted**

Do not commit the red tests by default. They become green and commit with Task 2.

---

### Task 2: Implement ToolResultView Adapter

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/tool_contracts.py`
- Modify: `mcp_server/tests/test_rookchat_tool_contracts.py`

- [ ] **Step 1: Add `Literal` to imports**

In `mcp_server/src/rook/agent/chat/tool_contracts.py`, change the typing import to:

```python
from typing import Any, Iterable, Literal
```

- [ ] **Step 2: Add the result-view dataclass and adapter helpers**

Place this block after `DispatchabilityFinding`:

```python
@dataclass(frozen=True)
class ToolResultView:
    status: Literal["success", "failed"] | None = None
    verified: bool | None = None
    verification_note: str | None = None
    message: str | None = None
    error: str | None = None


def _dict_field(mapping: dict[str, Any], key: str) -> dict[str, Any] | None:
    value = mapping.get(key)
    return value if isinstance(value, dict) else None


def _bool_field(mapping: dict[str, Any] | None, key: str) -> bool | None:
    if not isinstance(mapping, dict):
        return None
    value = mapping.get(key)
    return value if isinstance(value, bool) else None


def _first_bool_field(
    mapping: dict[str, Any] | None,
    keys: tuple[str, ...],
) -> bool | None:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = _bool_field(mapping, key)
        if value is not None:
            return value
    return None


def _string_field(mapping: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(mapping, dict):
        return None
    value = mapping.get(key)
    return value if isinstance(value, str) else None


def _truthy_field(mapping: dict[str, Any] | None, key: str) -> bool:
    return isinstance(mapping, dict) and bool(mapping.get(key))


def normalize_tool_result(result: Any) -> ToolResultView:
    """Normalize legacy tool result dicts for model-visible event decoration.

    This does not execute tools, call Rhino, format MCP wire output, or mutate
    the input result. It is an internal view over today's result shapes.
    """
    if not isinstance(result, dict):
        return ToolResultView()

    data = _dict_field(result, "data")

    truth = _first_bool_field(result, ("success", "ok"))
    if truth is None:
        truth = _first_bool_field(data, ("success", "ok"))

    if truth is True:
        status: Literal["success", "failed"] | None = "success"
    elif truth is False:
        status = "failed"
    elif _truthy_field(result, "error") or _truthy_field(data, "error"):
        status = "failed"
    else:
        status = None

    top_verified = _bool_field(result, "verified")
    nested_verified = _bool_field(data, "verified")
    verified = top_verified if top_verified is not None else nested_verified

    verification_note = _string_field(result, "verification_note")
    nested_verification_note = _string_field(data, "verification_note")
    if verification_note is None:
        verification_note = nested_verification_note
    if (
        verification_note is None
        and top_verified is None
        and nested_verified is False
    ):
        verification_note = _string_field(data, "message")

    message = _string_field(result, "message")
    if message is None:
        message = _string_field(data, "message")

    error = _string_field(result, "error")
    if error is None:
        error = _string_field(data, "error")

    return ToolResultView(
        status=status,
        verified=verified,
        verification_note=verification_note,
        message=message,
        error=error,
    )
```

- [ ] **Step 3: Run adapter tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_rookchat_tool_contracts.py -q
```

Expected: PASS for the full file.

- [ ] **Step 4: Run Python syntax check**

Run:

```powershell
python -m py_compile mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/tests/test_rookchat_tool_contracts.py
```

Expected: no output and exit code 0.

- [ ] **Step 5: Commit the adapter and unit tests**

Run:

```powershell
git add -- mcp_server/src/rook/agent/chat/tool_contracts.py mcp_server/tests/test_rookchat_tool_contracts.py
git commit -m "Add RookChat tool result view adapter"
```

Expected: commit succeeds. Do not stage `knowledge/contextual_mab.pkl` or `knowledge/substrate_observations.jsonl`.

---

### Task 3: Add Failing ChatRunner Adapter-Consumption Tests

**Files:**
- Modify: `mcp_server/tests/test_chat_runner.py`
- Modify: `mcp_server/tests/test_chat_runner_model_tools.py`

- [ ] **Step 1: Add ChatRunner module and view imports to `test_chat_runner.py`**

In `mcp_server/tests/test_chat_runner.py`, add these imports next to the existing Rook imports:

```python
from rook.agent.chat import chat_runner as chat_runner_module
from rook.agent.chat.tool_contracts import ToolResultView
```

- [ ] **Step 2: Append meta-tool, dispatcher-tool, and exception-path tests**

Append this block to `mcp_server/tests/test_chat_runner.py`:

```python
@pytest.mark.asyncio
async def test_meta_tool_result_event_uses_tool_result_view(monkeypatch, conversation):
    normalized_inputs = []

    def fake_normalize(result):
        normalized_inputs.append(result)
        return ToolResultView(
            status="failed",
            verified=False,
            verification_note="adapter meta",
            message=None,
            error=None,
        )

    monkeypatch.setattr(chat_runner_module, "normalize_tool_result", fake_normalize)
    runner = ChatRunner(tool_executor=AsyncMock(), registry=_make_minimal_registry())

    tool_response = _make_tool_response(
        "request_tools",
        {"group": "missing_group"},
        tool_call_id="call_meta",
    )
    text_response = _make_text_response("No tools loaded.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_response if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "load tools", system_prompt="test"):
            events.append(event)

    result_event = next(event for event in events if event.type == "tool_result")
    assert result_event.name == "request_tools"
    assert result_event.tool_status == "failed"
    assert result_event.verified is False
    assert result_event.verification_note == "adapter meta"
    assert normalized_inputs == [json.loads(result_event.result)]


@pytest.mark.asyncio
async def test_dispatcher_tool_result_event_uses_tool_result_view(monkeypatch, conversation):
    raw_result = {
        "success": True,
        "data": {"verified": False, "message": "legacy nested message"},
    }
    normalized_inputs = []

    def fake_normalize(result):
        normalized_inputs.append(result)
        return ToolResultView(
            status="success",
            verified=False,
            verification_note="adapter dispatcher",
            message=None,
            error=None,
        )

    async def executor(name, params):
        assert name == "rhino_objects"
        assert params == {"layer": "Default"}
        return raw_result

    monkeypatch.setattr(chat_runner_module, "normalize_tool_result", fake_normalize)
    runner = ChatRunner(tool_executor=executor, registry=_make_minimal_registry())

    tool_response = _make_tool_response(
        "rhino_objects",
        {"layer": "Default"},
        tool_call_id="call_dispatcher",
    )
    text_response = _make_text_response("Done.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_response if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "query objects", system_prompt="test"):
            events.append(event)

    result_event = next(event for event in events if event.type == "tool_result")
    assert result_event.name == "rhino_objects"
    assert result_event.tool_status == "success"
    assert result_event.verified is False
    assert result_event.verification_note == "adapter dispatcher"
    assert normalized_inputs == [raw_result]


@pytest.mark.asyncio
async def test_exception_tool_result_event_uses_tool_result_view(monkeypatch, conversation):
    normalized_inputs = []

    def fake_normalize(result):
        normalized_inputs.append(result)
        return ToolResultView(
            status="failed",
            verified=False,
            verification_note="adapter exception",
            message=None,
            error="Bridge timeout",
        )

    mock_executor = AsyncMock(side_effect=RuntimeError("Bridge timeout"))
    monkeypatch.setattr(chat_runner_module, "normalize_tool_result", fake_normalize)
    runner = ChatRunner(tool_executor=mock_executor, registry=_make_minimal_registry())

    tool_response = _make_tool_response(
        "rhino_objects",
        {},
        tool_call_id="call_exception",
    )
    text_response = _make_text_response("That failed.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_response if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "fail", system_prompt="test"):
            events.append(event)

    result_event = next(event for event in events if event.type == "tool_result")
    assert result_event.tool_status == "failed"
    assert result_event.verified is False
    assert result_event.verification_note == "adapter exception"
    assert normalized_inputs == [{"success": False, "error": "Bridge timeout"}]
```

- [ ] **Step 3: Add ChatRunner module and view imports to `test_chat_runner_model_tools.py`**

In `mcp_server/tests/test_chat_runner_model_tools.py`, add:

```python
from rook.agent.chat import chat_runner as chat_runner_module
from rook.agent.chat.tool_contracts import ToolResultView
from rook.agent.tool_registry import ToolRegistry
```

- [ ] **Step 4: Append chat-model pseudo-tool adapter test**

Append this block to `mcp_server/tests/test_chat_runner_model_tools.py`:

```python
@pytest.mark.asyncio
async def test_chat_model_tool_result_event_uses_tool_result_view(monkeypatch):
    conv = Conversation(id="conv_test", persona="worker", model="anthropic/current", api_base="")
    payload = {
        "allowed_model_overrides": ["anthropic/current", "ollama_chat/qwen3:30b"],
        "local_providers": {"ollama": {"available": False, "models": []}},
    }
    builder = AsyncMock(return_value=payload)
    runner = ChatRunner(
        tool_executor=AsyncMock(),
        registry=ToolRegistry(catalog={}, agent_mode=True),
    )
    normalized_inputs = []

    def fake_normalize(result):
        normalized_inputs.append(result)
        return ToolResultView(
            status="failed",
            verified=False,
            verification_note="adapter pseudo",
            message=None,
            error=None,
        )

    monkeypatch.setattr(chat_runner_module, "normalize_tool_result", fake_normalize)
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response("list_chat_models", {}, "call_list_models")
        return _make_text_response("Here are the available models.")

    events = []
    with (
        patch("rook.agent.chat.chat_runner.litellm.acompletion", side_effect=mock_acompletion),
        _runtime_facts_patch(),
    ):
        async for event in runner.run_turn(
            conv,
            "what models can I use?",
            "system",
            model_payload_builder=builder,
        ):
            events.append(event)

    result_event = next(
        event for event in events
        if event.type == "tool_result" and event.name == "list_chat_models"
    )
    assert result_event.tool_status == "failed"
    assert result_event.verified is False
    assert result_event.verification_note == "adapter pseudo"
    assert normalized_inputs == [payload]
```

- [ ] **Step 5: Run the new ChatRunner tests and confirm they fail**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_chat_runner.py::test_meta_tool_result_event_uses_tool_result_view `
  mcp_server/tests/test_chat_runner.py::test_dispatcher_tool_result_event_uses_tool_result_view `
  mcp_server/tests/test_chat_runner.py::test_exception_tool_result_event_uses_tool_result_view `
  mcp_server/tests/test_chat_runner_model_tools.py::test_chat_model_tool_result_event_uses_tool_result_view `
  -q
```

Expected: FAIL before ChatRunner imports and uses `normalize_tool_result`.

- [ ] **Step 6: Leave the red ChatRunner tests uncommitted**

Do not commit the red tests by default. They become green and commit with Task 4.

---

### Task 4: Wire ChatRunner Event Decoration Through ToolResultView

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/tests/test_chat_runner.py`
- Modify: `mcp_server/tests/test_chat_runner_model_tools.py`

- [ ] **Step 1: Import `normalize_tool_result`**

In `mcp_server/src/rook/agent/chat/chat_runner.py`, change:

```python
from .tool_contracts import closed_no_arg_parameters, normalize_catalog
```

to:

```python
from .tool_contracts import (
    closed_no_arg_parameters,
    normalize_catalog,
    normalize_tool_result,
)
```

- [ ] **Step 2: Remove the independent status classifier**

Replace `_classify_tool_status(...)` with adapter delegation:

```python
def _classify_tool_status(result: Any) -> Optional[str]:
    return normalize_tool_result(result).status
```

This keeps compatibility for any tests or code that still imports the helper, but removes it as a second truth system.

- [ ] **Step 3: Update chat-model pseudo-tool `tool_result` events**

In the `_CHAT_MODEL_TOOL_SCHEMAS` branch, keep raw serialization first, then derive the view after appending the raw tool message:

```python
result_str = json.dumps(result)

conversation.messages.append({
    "role": "tool",
    "tool_call_id": tc.id,
    "content": result_str,
})

result_view = normalize_tool_result(result)

yield ChatEvent(
    "tool_result",
    name=tool_name,
    result=result_str,
    tool_call_id=tc.id,
    tool_status=result_view.status,
    verified=result_view.verified,
    verification_note=result_view.verification_note,
)
```

Leave the existing `set_chat_model` `model_update` condition unchanged:

```python
if tool_name == "set_chat_model" and result.get("success"):
```

- [ ] **Step 4: Replace ad hoc verification hoisting for meta and dispatcher paths**

In the main tool-result path, remove the local `_verified`, `_verification_note`, and `_tool_status` extraction block. Keep substrate persistence unchanged. After `result_str` is computed, preserve the raw history write and then derive the view:

```python
conversation.messages.append({
    "role": "tool",
    "tool_call_id": tc.id,
    "content": result_str,
})

result_view = normalize_tool_result(result)

yield ChatEvent(
    "tool_result",
    name=tool_name,
    result=result_str,
    tool_call_id=tc.id,
    verified=result_view.verified,
    verification_note=result_view.verification_note,
    tool_status=result_view.status,
)
```

The important ordering is:

```text
raw result -> result_str -> conversation history -> ToolResultView -> ChatEvent decoration
```

- [ ] **Step 5: Run the ChatRunner adapter-consumption tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_chat_runner.py::test_meta_tool_result_event_uses_tool_result_view `
  mcp_server/tests/test_chat_runner.py::test_dispatcher_tool_result_event_uses_tool_result_view `
  mcp_server/tests/test_chat_runner.py::test_exception_tool_result_event_uses_tool_result_view `
  mcp_server/tests/test_chat_runner_model_tools.py::test_chat_model_tool_result_event_uses_tool_result_view `
  -q
```

Expected: PASS.

- [ ] **Step 6: Run existing ChatRunner verification-result tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_chat_runner.py::test_run_turn_verification_hoisting `
  mcp_server/tests/test_chat_runner.py::test_run_turn_verification_hoisting_from_nested_data `
  mcp_server/tests/test_chat_runner.py::test_run_turn_uses_nested_legacy_readiness_verification_note `
  mcp_server/tests/test_chat_runner.py::test_run_turn_verification_hoisting_on_error `
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit ChatRunner adapter wiring**

Run:

```powershell
git add -- mcp_server/src/rook/agent/chat/chat_runner.py mcp_server/tests/test_chat_runner.py mcp_server/tests/test_chat_runner_model_tools.py
git commit -m "Use tool result view in RookChat events"
```

Expected: commit succeeds. Do not stage `knowledge/contextual_mab.pkl` or `knowledge/substrate_observations.jsonl`.

---

### Task 5: Add Raw-History And ui_block Regression Checks

**Files:**
- Modify: `mcp_server/tests/test_chat_runner.py`

- [ ] **Step 1: Add raw-history serialization regression**

Append this test to `mcp_server/tests/test_chat_runner.py`:

```python
@pytest.mark.asyncio
async def test_tool_result_view_cannot_change_raw_history_serialization(monkeypatch, conversation):
    raw_result = {"success": True, "data": {"value": 1}}

    async def executor(name, params):
        assert name == "rhino_objects"
        return dict(raw_result)

    def mutating_normalize(result):
        result["mutated_by_adapter_spy"] = True
        return ToolResultView(
            status="success",
            verified=None,
            verification_note=None,
            message=None,
            error=None,
        )

    monkeypatch.setattr(chat_runner_module, "normalize_tool_result", mutating_normalize)
    runner = ChatRunner(tool_executor=executor, registry=_make_minimal_registry())

    tool_response = _make_tool_response(
        "rhino_objects",
        {},
        tool_call_id="call_raw_history",
    )
    text_response = _make_text_response("Done.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_response if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "query objects", system_prompt="test"):
            events.append(event)

    result_event = next(event for event in events if event.type == "tool_result")
    tool_message = next(
        message for message in conversation.messages
        if message.get("tool_call_id") == "call_raw_history"
    )

    assert json.loads(result_event.result) == raw_result
    assert tool_message["content"] == result_event.result
    assert "mutated_by_adapter_spy" not in result_event.result
```

- [ ] **Step 2: Strengthen the existing ui_block intercept test**

Change the existing function signature:

```python
async def test_run_turn_ui_block_intercept(conversation):
```

to:

```python
async def test_run_turn_ui_block_intercept(monkeypatch, conversation):
```

Add this block immediately after `runner = ChatRunner(...)` in that test:

```python
    def fail_if_ui_block_uses_result_view(result):
        raise AssertionError("ui_block must not use ToolResultView in LM1B")

    monkeypatch.setattr(
        chat_runner_module,
        "normalize_tool_result",
        fail_if_ui_block_uses_result_view,
    )
```

Add this assertion next to the existing event-type assertions:

```python
    assert "tool_result" not in types
```

- [ ] **Step 3: Run raw-history and ui_block regression tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_chat_runner.py::test_tool_result_view_cannot_change_raw_history_serialization `
  mcp_server/tests/test_chat_runner.py::test_run_turn_ui_block_intercept `
  -q
```

Expected: PASS.

- [ ] **Step 4: Commit the regressions**

Run:

```powershell
git add -- mcp_server/tests/test_chat_runner.py
git commit -m "Pin RookChat result history and ui_block behavior"
```

Expected: commit succeeds. Do not stage `knowledge/contextual_mab.pkl` or `knowledge/substrate_observations.jsonl`.

---

### Task 6: Focused LM1B Verification

**Files:**
- Verify: `mcp_server/src/rook/agent/chat/tool_contracts.py`
- Verify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Verify: `mcp_server/tests/test_rookchat_tool_contracts.py`
- Verify: `mcp_server/tests/test_chat_runner.py`
- Verify: `mcp_server/tests/test_chat_runner_model_tools.py`

- [ ] **Step 1: Run focused RookChat tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_chat_runner_model_tools.py `
  mcp_server/tests/test_rookchat_tool_transcripts.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_rookchat_tool_schema_golden.py `
  -q
```

Expected: PASS.

- [ ] **Step 2: Run Python syntax checks**

Run:

```powershell
python -m py_compile `
  mcp_server/src/rook/agent/chat/tool_contracts.py `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_chat_runner_model_tools.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Check diff hygiene**

Run:

```powershell
git diff --check
git status --short
```

Expected:

```text
git diff --check exits 0
```

`git status --short` may still show the pre-existing runtime artifacts:

```text
 M knowledge/contextual_mab.pkl
 M knowledge/substrate_observations.jsonl
```

Those files must remain unstaged unless the user explicitly asks for them.

- [ ] **Step 4: Report implementation summary**

Report:

- adapter tests added and passing;
- `ToolResultView` adapter added;
- ChatRunner event decoration uses the adapter;
- raw conversation history unchanged;
- `ui_block` behavior unchanged;
- dispatcher and public MCP wire shape unchanged;
- exact test command results.

Do not claim Rhino/live verification. This slice has no Rhino live dependency.
