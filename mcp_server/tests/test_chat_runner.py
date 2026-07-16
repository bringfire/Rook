"""Tests for ChatRunner — the conversation turn loop."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from rook.agent.chat import chat_runner as chat_runner_module
from rook.agent.chat.conversation_store import Conversation
from rook.agent.chat.chat_runner import ChatRunner, ChatEvent, MAX_META_ONLY_ROUNDS
from rook.agent.chat.tool_contracts import ToolResultView
from rook.agent.tool_registry import ToolRegistry
from rook.tool_lifecycle import contained_names


@pytest.fixture
def conversation():
    return Conversation(id="conv_test", persona="worker", model="test-model")


def _make_minimal_registry() -> ToolRegistry:
    """Build a minimal ToolRegistry for testing (avoids ToolDispatcher init)."""
    catalog = {
        "rhino_objects": {
            "type": "function",
            "function": {
                "name": "rhino_objects",
                "description": "Query objects",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        "rhino_ping": {
            "type": "function",
            "function": {
                "name": "rhino_ping",
                "description": "Check if Rhino is responsive",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        "knowledge_query": {
            "type": "function",
            "function": {
                "name": "knowledge_query",
                "description": "Query knowledge store",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    }
    return ToolRegistry(catalog=catalog, agent_mode=True)


def _dirty_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


def _visible_schema_names(schemas) -> set[str]:
    return {
        schema.get("function", {}).get("name")
        for schema in schemas
        if isinstance(schema, dict)
    }


def _chat_telemetry_store(monkeypatch, tmp_path):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    return store


class _DirtyInjectedRegistry:
    def get_active_schemas(self):
        return [
            _dirty_schema("safe_tool"),
            _dirty_schema("spawn_agent"),
        ]

    def is_meta_tool(self, name):
        return False

    def get_group_names(self):
        return []

    def get_active_count(self):
        return 2


@pytest.fixture
def runner():
    """ChatRunner with a mock executor and minimal registry (no ToolDispatcher)."""
    mock_executor = AsyncMock(return_value={"ok": True})
    return ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )


def test_cached_catalog_is_revalidated_before_chatrunner_registry(
    monkeypatch,
    tmp_path,
):
    store = _chat_telemetry_store(monkeypatch, tmp_path)
    dirty = {
        "safe_tool": _dirty_schema("safe_tool"),
        "plan_and_execute": _dirty_schema("safe_embedded"),
        "safe_raw_hidden_embedded": _dirty_schema("gh_replay_recipe"),
    }
    monkeypatch.setattr(
        chat_runner_module,
        "load_catalog_from_cache",
        lambda: dirty,
    )
    before = store.get_containment_denials_snapshot()
    runner = ChatRunner(tool_executor=AsyncMock())
    after = store.get_containment_denials_snapshot()

    assert (
        set(runner._registry._catalog).isdisjoint(contained_names())
        and "safe_raw_hidden_embedded" not in runner._registry._catalog
        and after == before
    ), "EXPECTED_RED:T2:PYTEST cached RookChat catalog admits contained records"


def test_fallback_catalog_filters_contained_route_names(
    monkeypatch,
    tmp_path,
):
    store = _chat_telemetry_store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        chat_runner_module,
        "BRIDGE_ROUTES",
        {"safe_bridge": object(), "gh_explore_workflow": object()},
    )
    monkeypatch.setattr(
        chat_runner_module,
        "TRANSFORM_FUNCTIONS",
        {"safe_transform": object(), "gh_replay_recipe": object()},
    )
    before = store.get_containment_denials_snapshot()
    catalog = chat_runner_module._build_fallback_catalog()
    after = store.get_containment_denials_snapshot()

    assert (
        {"safe_bridge", "safe_transform"} <= set(catalog)
        and contained_names().isdisjoint(catalog)
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookChat fallback catalog admits contained routes"


def test_fallback_startup_guidance_does_not_recommend_spawn_agent(
    monkeypatch,
    caplog,
):
    caplog.set_level("INFO", logger="rook.agent.chat.chat_runner")
    monkeypatch.setattr(
        chat_runner_module,
        "load_catalog_from_cache",
        lambda: None,
    )

    ChatRunner(tool_executor=AsyncMock())

    assert "spawn_agent" not in caplog.text, (
        "EXPECTED_RED:T2:PYTEST RookChat still recommends contained cache refresh"
    )


def test_local_catalog_filters_contained_registration_names(
    monkeypatch,
    tmp_path,
):
    store = _chat_telemetry_store(monkeypatch, tmp_path)
    before = store.get_containment_denials_snapshot()
    catalog = chat_runner_module._build_local_tool_catalog(
        {"safe_local": object(), "rhino_execute_intent": object()}
    )
    after = store.get_containment_denials_snapshot()

    assert (
        set(catalog) == {"safe_local"}
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookChat local catalog admits contained name"


def test_model_overlay_is_revalidated_before_registry_construction(
    monkeypatch,
    tmp_path,
):
    store = _chat_telemetry_store(monkeypatch, tmp_path)
    monkeypatch.setattr(chat_runner_module, "load_catalog_from_cache", lambda: {
        "safe_tool": _dirty_schema("safe_tool"),
    })
    monkeypatch.setattr(
        chat_runner_module,
        "_CHAT_MODEL_TOOL_SCHEMAS",
        {
            "safe_overlay": _dirty_schema("safe_overlay"),
            "spawn_agent": _dirty_schema("safe_embedded"),
            "safe_raw_hidden_embedded": _dirty_schema("plan_and_execute"),
        },
    )
    before = store.get_containment_denials_snapshot()
    runner = ChatRunner(tool_executor=AsyncMock())
    after = store.get_containment_denials_snapshot()

    assert (
        set(runner._registry._catalog) == {"safe_tool", "safe_overlay"}
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookChat model overlay admits contained records"


def test_tool_section_filters_injected_registry_schemas_without_telemetry(
    monkeypatch,
    tmp_path,
):
    store = _chat_telemetry_store(monkeypatch, tmp_path)
    runner = ChatRunner(
        tool_executor=AsyncMock(),
        registry=_DirtyInjectedRegistry(),
    )
    before = store.get_containment_denials_snapshot()
    section = runner._build_tool_section()
    after = store.get_containment_denials_snapshot()

    assert (
        "safe_tool" in section
        and "spawn_agent" not in section
        and after == before
    ), "EXPECTED_RED:T2:PYTEST RookChat tool section exposes contained identity"


@pytest.mark.asyncio
async def test_final_litellm_tools_filter_injected_registry_schemas(
    monkeypatch,
    tmp_path,
    conversation,
):
    store = _chat_telemetry_store(monkeypatch, tmp_path)
    runner = ChatRunner(
        tool_executor=AsyncMock(),
        registry=_DirtyInjectedRegistry(),
    )
    captured = {}

    async def capture_acompletion(**kwargs):
        captured.update(kwargs)
        return _make_text_response("done")

    before = store.get_containment_denials_snapshot()
    with patch(
        "litellm.acompletion",
        side_effect=capture_acompletion,
    ), _runtime_facts_patch():
        async for _ in runner.run_turn(
            conversation,
            "inspect",
            system_prompt="test",
        ):
            pass
    after = store.get_containment_denials_snapshot()
    names = _visible_schema_names(captured["tools"])

    assert (
        names == {"safe_tool"}
        and after == before
    ), "EXPECTED_RED:T2:PYTEST final LiteLLM projection exposes contained identity"


def _make_text_response(text, prompt_tokens=10, completion_tokens=5):
    """Helper: return an async streaming generator with a single text chunk."""
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = text
        chunk.choices[0].delta.tool_calls = None
        chunk.usage = None
        yield chunk
        # Final usage chunk
        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        yield final
    return _gen()


def _make_tool_response(tool_name, tool_args, tool_call_id="call_123",
                        text=None, prompt_tokens=10, completion_tokens=5):
    """Helper: return an async streaming generator that requests a tool call."""
    async def _gen():
        if text:
            text_chunk = MagicMock()
            text_chunk.choices = [MagicMock()]
            text_chunk.choices[0].delta.content = text
            text_chunk.choices[0].delta.tool_calls = None
            text_chunk.usage = None
            yield text_chunk
        # Tool call chunk
        tc_chunk = MagicMock()
        tc_chunk.choices = [MagicMock()]
        tc_chunk.choices[0].delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = tool_call_id
        tc_delta.function.name = tool_name
        tc_delta.function.arguments = json.dumps(tool_args)
        tc_chunk.choices[0].delta.tool_calls = [tc_delta]
        tc_chunk.usage = None
        yield tc_chunk
        # Final usage chunk
        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        yield final
    return _gen()


def _make_two_tool_response():
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
        calls = []
        for idx, name, call_id, args in [
            (0, "request_tools", "call_request", {"group": "gh_canvas"}),
            (1, "gh_errors", "call_errors", {}),
        ]:
            tc_delta = MagicMock()
            tc_delta.index = idx
            tc_delta.id = call_id
            tc_delta.function.name = name
            tc_delta.function.arguments = json.dumps(args)
            calls.append(tc_delta)
        chunk.choices[0].delta.tool_calls = calls
        chunk.usage = None
        yield chunk

        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        yield final
    return _gen()


def _make_two_tool_response_reusing_stream_index():
    async def _gen():
        for name, call_id, args in [
            ("request_tools", "call_request", {"group": "gh_canvas"}),
            ("gh_errors", "call_errors", {}),
        ]:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = None
            tc_delta = MagicMock()
            tc_delta.index = 0
            tc_delta.id = call_id
            tc_delta.function.name = name
            tc_delta.function.arguments = json.dumps(args)
            chunk.choices[0].delta.tool_calls = [tc_delta]
            chunk.usage = None
            yield chunk

        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        yield final
    return _gen()


def test_chat_event_creation():
    event = ChatEvent("text_delta", content="hello")
    assert event.type == "text_delta"
    assert event.content == "hello"
    assert event.to_dict() == {"type": "text_delta", "content": "hello"}


def test_chat_event_tool_start():
    event = ChatEvent("tool_start", name="rhino_objects", params={"layer": "Default"})
    d = event.to_dict()
    assert d["type"] == "tool_start"
    assert d["name"] == "rhino_objects"


def _runtime_facts_patch():
    return patch(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        new=AsyncMock(return_value={
            "rhino": {"connected": True},
            "prompt": {"available": True},
            "verified_runtime_facts": [
                "Rhino bridge is connected and tool execution is available."
            ],
        }),
    )


@pytest.mark.asyncio
async def test_run_turn_appends_user_message(runner, conversation):
    """Verify user message is added to conversation history."""
    async def mock_acompletion(**kwargs):
        return _make_text_response("Hello!")

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "Hi there", system_prompt="You are helpful"):
            events.append(event)

    # User message should be in history
    assert any(m["role"] == "user" and m["content"] == "Hi there" for m in conversation.messages)
    # Assistant response should be in history
    assert any(m["role"] == "assistant" for m in conversation.messages)
    # Should have text_delta + done events
    types = [e.type for e in events]
    assert "text_delta" in types
    assert "done" in types


@pytest.mark.asyncio
async def test_run_turn_tool_dispatch_roundtrip(conversation):
    """Verify the LLM -> tool call -> tool result -> LLM -> text flow."""
    mock_executor = AsyncMock(return_value={"objects": [{"id": "abc", "type": "Brep"}]})
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    # First LLM call returns a tool call, second returns text
    tool_response = _make_tool_response(
        "rhino_objects", {"layer": "Default"}, tool_call_id="call_001"
    )
    text_response = _make_text_response("Found 1 Brep on the Default layer.")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "What objects?", system_prompt="test"):
            events.append(event)

    types = [e.type for e in events]

    # Should see: tool_start, tool_result, text_delta, done
    assert "tool_start" in types
    assert "tool_result" in types
    assert "text_delta" in types
    assert "done" in types

    # Tool executor was called with correct args
    mock_executor.assert_awaited_once_with("rhino_objects", {"layer": "Default"})

    # Conversation history should contain: user, assistant (tool call), tool result, assistant (text)
    roles = [m["role"] for m in conversation.messages]
    assert roles == ["user", "assistant", "tool", "assistant"]

    # Tool result message should reference the tool call ID
    tool_msg = conversation.messages[2]
    assert tool_msg["tool_call_id"] == "call_001"
    assert "Brep" in tool_msg["content"]


@pytest.mark.asyncio
async def test_run_turn_emits_distinct_tool_start_names_for_multiple_tool_calls(conversation):
    mock_executor = AsyncMock(return_value={"success": True})
    registry = _make_minimal_registry()
    registry._catalog["gh_errors"] = {
        "type": "function",
        "function": {
            "name": "gh_errors",
            "description": "GH errors",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry._active.add("gh_errors")
    runner = ChatRunner(tool_executor=mock_executor, registry=registry)

    text_response = _make_text_response("Checked.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return _make_two_tool_response() if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "check gh", system_prompt="test"):
            events.append(event)

    starts = [e for e in events if e.type == "tool_start"]
    assert [e.name for e in starts[:2]] == ["request_tools", "gh_errors"]


@pytest.mark.asyncio
async def test_run_turn_keeps_sequential_tool_calls_distinct_when_stream_reuses_index(conversation):
    mock_executor = AsyncMock(return_value={"success": True})
    registry = _make_minimal_registry()
    registry._catalog["gh_errors"] = {
        "type": "function",
        "function": {
            "name": "gh_errors",
            "description": "GH errors",
            "parameters": {"type": "object", "properties": {}},
        },
    }
    registry._active.add("gh_errors")
    runner = ChatRunner(tool_executor=mock_executor, registry=registry)

    text_response = _make_text_response("Checked.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return _make_two_tool_response_reusing_stream_index() if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "check gh", system_prompt="test"):
            events.append(event)

    starts = [e for e in events if e.type == "tool_start"]
    assert [e.name for e in starts[:2]] == ["request_tools", "gh_errors"]
    assert mock_executor.await_args_list[0].args == ("gh_errors", {})


@pytest.mark.asyncio
async def test_tool_result_event_marks_application_failure_separately(conversation):
    mock_executor = AsyncMock(return_value={
        "success": False,
        "error": "Grasshopper is not currently available",
    })
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    tool_response = _make_tool_response(
        "rhino_ping", {}, tool_call_id="call_fail"
    )
    text_response = _make_text_response("I will ask you to open Grasshopper.")
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        return tool_response if call_count == 1 else text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "make a script", system_prompt="test"):
            events.append(event)

    result = next(e for e in events if e.type == "tool_result")
    assert result.tool_status == "failed"
    assert result.verified is None


@pytest.mark.asyncio
async def test_run_turn_max_rounds_guard(conversation):
    """Verify the runaway loop guard triggers after MAX_TOOL_ROUNDS."""
    mock_executor = AsyncMock(return_value={"ok": True})
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    # LLM always returns a tool call (never text-only)
    async def always_tool(**kwargs):
        return _make_tool_response("rhino_ping", {}, tool_call_id="call_loop")

    events = []
    with patch("litellm.acompletion", side_effect=always_tool), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "loop", system_prompt="test"):
            events.append(event)

    types = [e.type for e in events]
    # Should get an error about too many tool calls, plus done
    assert "error" in types
    error_event = next(e for e in events if e.type == "error")
    assert "too many" in error_event.content.lower()
    assert "done" in types


@pytest.mark.asyncio
async def test_meta_tool_request_tools(conversation):
    """Verify request_tools meta-tool is handled internally, not dispatched."""
    # Build a registry with gh_canvas tools in the catalog
    catalog = {
        "rhino_objects": {"type": "function", "function": {"name": "rhino_objects", "description": "Query objects", "parameters": {"type": "object", "properties": {}}}},
        "rhino_ping": {"type": "function", "function": {"name": "rhino_ping", "description": "Ping", "parameters": {"type": "object", "properties": {}}}},
        "knowledge_query": {"type": "function", "function": {"name": "knowledge_query", "description": "Query knowledge", "parameters": {"type": "object", "properties": {}}}},
        "gh_snapshot": {"type": "function", "function": {"name": "gh_snapshot", "description": "Read the canvas", "parameters": {"type": "object", "properties": {}}}},
        "gh_edit": {"type": "function", "function": {"name": "gh_edit", "description": "Mutate the canvas", "parameters": {"type": "object", "properties": {}}}},
        "gh_undo": {"type": "function", "function": {"name": "gh_undo", "description": "Undo last edit", "parameters": {"type": "object", "properties": {}}}},
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    mock_executor = AsyncMock(return_value={"ok": True})
    runner = ChatRunner(tool_executor=mock_executor, registry=registry)

    # Initial active count (Tier 0 tools from catalog + meta-tools)
    initial_count = registry.get_active_count()

    # LLM calls request_tools("gh_canvas") then gives a text response
    tool_response = _make_tool_response(
        "request_tools", {"group": "gh_canvas"}, tool_call_id="call_rt"
    )
    text_response = _make_text_response("GH canvas tools loaded!")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "I need GH tools", system_prompt="test"):
            events.append(event)

    # Meta-tool should NOT have been dispatched to the executor
    mock_executor.assert_not_awaited()

    # Registry should now have more active tools than before
    assert registry.get_active_count() > initial_count

    # The tool_result event should contain success info
    result_events = [e for e in events if e.type == "tool_result"]
    assert len(result_events) == 1
    result_data = json.loads(result_events[0].result)
    assert result_data["success"] is True
    assert "gh_canvas" in result_data.get("group", "")


def test_request_tools_reports_already_loaded_group():
    catalog = {
        "gh_status": {
            "type": "function",
            "function": {
                "name": "gh_status",
                "description": "GH status",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        "gh_errors": {
            "type": "function",
            "function": {
                "name": "gh_errors",
                "description": "GH errors",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    }
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    runner = ChatRunner(tool_executor=AsyncMock(), registry=registry)

    first = runner._handle_meta_tool("request_tools", {"group": "gh_canvas"})
    second = runner._handle_meta_tool("request_tools", {"group": "gh_canvas"})

    assert first["success"] is True
    assert first["status"] == "loaded"
    assert second["success"] is True
    assert second["status"] == "already_loaded"
    assert second["loaded"] == []
    assert "already loaded" in second["message"].lower()
    assert "call the needed Grasshopper tool" in second["next_action"]


@pytest.mark.asyncio
async def test_done_event_includes_active_tools(runner, conversation):
    """Verify the done event reports active tool count."""
    mock_response = _make_text_response("Done!")

    async def mock_acompletion(**kwargs):
        return _make_text_response("Done!")

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "test", system_prompt="test"):
            events.append(event)

    done_events = [e for e in events if e.type == "done"]
    assert len(done_events) == 1
    assert "active_tools" in done_events[0].usage
    assert done_events[0].usage["active_tools"] > 0


@pytest.mark.asyncio
async def test_meta_only_loop_detection(conversation):
    """Verify consecutive meta-only rounds trigger early stop."""
    mock_executor = AsyncMock(return_value={"ok": True})
    registry = _make_minimal_registry()
    runner = ChatRunner(tool_executor=mock_executor, registry=registry)

    # LLM always calls request_tools (meta-tool), never a real tool
    async def always_meta(**kwargs):
        return _make_tool_response(
            "request_tools", {"group": "rhino_geometry"}, tool_call_id="call_meta"
        )

    events = []
    with patch("litellm.acompletion", side_effect=always_meta), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "loop meta", system_prompt="test"):
            events.append(event)

    types = [e.type for e in events]
    assert "error" in types
    error_event = next(e for e in events if e.type == "error")
    assert "stuck" in error_event.content.lower()
    assert "done" in types

    # Should have stopped well before MAX_TOOL_ROUNDS (20)
    tool_starts = [e for e in events if e.type == "tool_start"]
    assert len(tool_starts) == MAX_META_ONLY_ROUNDS


@pytest.mark.asyncio
async def test_system_prompt_includes_tool_section(runner, conversation):
    """Verify the system prompt sent to LLM includes dynamic tool documentation."""
    captured_messages = []

    async def capture_acompletion(**kwargs):
        captured_messages.append(kwargs.get("messages", []))
        return _make_text_response("Hello!")

    with patch("litellm.acompletion", side_effect=capture_acompletion), _runtime_facts_patch():
        async for _ in runner.run_turn(conversation, "test", system_prompt="Base prompt."):
            pass

    assert len(captured_messages) == 1
    system_msg = captured_messages[0][0]
    assert system_msg["role"] == "system"
    # Should contain the dynamic tool section
    assert "## Available Tools" in system_msg["content"]
    assert "## Loading More Tools" in system_msg["content"]
    assert "request_tools" in system_msg["content"]
    assert "search_tools" in system_msg["content"]
    # Should still start with the base prompt
    assert system_msg["content"].startswith("Base prompt.")


@pytest.mark.asyncio
async def test_sonnet_5_chat_turn_omits_temperature(runner, conversation):
    """Sonnet 5 rejects non-default sampling params; RookChat must not send 0.7."""
    conversation.model = "anthropic/claude-sonnet-5"
    captured_kwargs = []

    async def capture_acompletion(**kwargs):
        captured_kwargs.append(kwargs)
        return _make_text_response("Hello!")

    with patch("litellm.acompletion", side_effect=capture_acompletion), _runtime_facts_patch():
        async for _ in runner.run_turn(conversation, "test", system_prompt="Base prompt."):
            pass

    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["model"] == "anthropic/claude-sonnet-5"
    assert "temperature" not in captured_kwargs[0]
    assert captured_kwargs[0]["max_tokens"] == 2048


def test_chat_event_ui_block_serialization():
    """Verify ChatEvent serializes all adaptive UI fields."""
    event = ChatEvent(
        "ui_block",
        block_id="blk_abc12345",
        block_type="slider",
        block_config={"title": "Height", "min": 1, "max": 50},
    )
    d = event.to_dict()
    assert d["type"] == "ui_block"
    assert d["block_id"] == "blk_abc12345"
    assert d["block_type"] == "slider"
    assert d["block_config"]["title"] == "Height"
    # Fields not set should be absent
    assert "verified" not in d
    assert "content" not in d


def test_chat_event_tool_call_id_serialization():
    """Verify tool_call_id is serialized on tool_start/tool_result events."""
    event = ChatEvent(
        "tool_start", name="rhino_create",
        params={"type": "box"}, tool_call_id="call_xyz",
    )
    d = event.to_dict()
    assert d["tool_call_id"] == "call_xyz"

    result_event = ChatEvent(
        "tool_result", name="rhino_create",
        result='{"success": true}', tool_call_id="call_xyz",
        verified=True, verification_note="objectsCreated=1",
    )
    d2 = result_event.to_dict()
    assert d2["tool_call_id"] == "call_xyz"
    assert d2["verified"] is True
    assert d2["verification_note"] == "objectsCreated=1"


@pytest.mark.asyncio
async def test_run_turn_ui_block_intercept(monkeypatch, conversation):
    """Verify ui_block tool calls are intercepted and yield ui_block events."""
    mock_executor = AsyncMock(return_value={"ok": True})

    # Registry that includes ui_block
    catalog = {
        "rhino_ping": {"type": "function", "function": {"name": "rhino_ping", "description": "Ping", "parameters": {"type": "object", "properties": {}}}},
        "ui_block": {"type": "function", "function": {"name": "ui_block", "description": "UI block", "parameters": {"type": "object", "properties": {}}}},
    }
    registry = ToolRegistry(catalog=catalog, tier0={"rhino_ping", "ui_block"}, agent_mode=True)
    runner = ChatRunner(tool_executor=mock_executor, registry=registry)

    def fail_if_ui_block_uses_result_view(result):
        raise AssertionError("ui_block must not use ToolResultView in LM1B")

    monkeypatch.setattr(
        chat_runner_module,
        "normalize_tool_result",
        fail_if_ui_block_uses_result_view,
    )

    # LLM calls ui_block, then returns text
    tool_response = _make_tool_response(
        "ui_block",
        {"block_type": "slider", "config": {"title": "Height", "min": 1, "max": 50}},
        tool_call_id="call_ui",
    )
    text_response = _make_text_response("I've shown you a slider.")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "Set height", system_prompt="test"):
            events.append(event)

    # ui_block should NOT have been dispatched to the executor
    mock_executor.assert_not_awaited()

    # Should have a ui_block event (not tool_start/tool_result)
    types = [e.type for e in events]
    assert "ui_block" in types
    assert "tool_result" not in types
    assert "done" in types

    ui_event = next(e for e in events if e.type == "ui_block")
    assert ui_event.block_type == "slider"
    assert ui_event.block_id is not None
    assert ui_event.block_id.startswith("blk_")
    assert ui_event.block_config["title"] == "Height"

    # Conversation history should have a tool message with block_id
    tool_msgs = [m for m in conversation.messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    tool_content = json.loads(tool_msgs[0]["content"])
    assert tool_content["block_id"] == ui_event.block_id
    assert tool_content["status"] == "rendered"


@pytest.mark.asyncio
async def test_run_turn_verification_hoisting(conversation):
    """Verify verified/verification_note fields appear on tool_result events."""
    # Executor returns a result with verification fields (as added by execution_policy)
    mock_executor = AsyncMock(return_value={
        "success": True,
        "data": {"objectsCreated": 1},
        "verified": True,
        "verification_note": "objectsCreated=1, Rhino idle",
    })
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    # LLM calls rhino_objects (a non-verification tool), then returns text
    tool_response = _make_tool_response(
        "rhino_objects", {"layer": "Default"}, tool_call_id="call_v"
    )
    text_response = _make_text_response("Done.")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "check", system_prompt="test"):
            events.append(event)

    result_events = [e for e in events if e.type == "tool_result"]
    assert len(result_events) == 1
    assert result_events[0].verified is True
    assert result_events[0].verification_note == "objectsCreated=1, Rhino idle"
    assert result_events[0].tool_call_id == "call_v"


@pytest.mark.asyncio
async def test_run_turn_verification_hoisting_from_nested_data(conversation):
    """Verify nested readiness failures still drive frontend verification state."""
    mock_executor = AsyncMock(return_value={
        "success": False,
        "data": {
            "error": "grasshopper_not_ready",
            "message": "No active Grasshopper canvas",
            "ready_for_edit": False,
            "verified": False,
        },
    })
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    tool_response = _make_tool_response(
        "gh_snapshot", {}, tool_call_id="call_gh_not_ready"
    )
    text_response = _make_text_response("Grasshopper is not ready.")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "snapshot", system_prompt="test"):
            events.append(event)

    result_events = [e for e in events if e.type == "tool_result"]
    assert len(result_events) == 1
    assert result_events[0].verified is False
    assert result_events[0].verification_note == "No active Grasshopper canvas"


@pytest.mark.asyncio
async def test_run_turn_uses_nested_legacy_readiness_verification_note(conversation):
    """Legacy GH route readiness failures preserve explicit nested notes."""
    mock_executor = AsyncMock(return_value={
        "success": False,
        "data": {
            "error": "grasshopper_not_ready",
            "message": "No active Grasshopper canvas",
            "verified": False,
            "verification_note": "Call gh_status to inspect readiness.",
        },
    })
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    tool_response = _make_tool_response(
        "gh_create_slider", {}, tool_call_id="call_gh_legacy_not_ready"
    )
    text_response = _make_text_response("Grasshopper is not ready.")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "create slider", system_prompt="test"):
            events.append(event)

    result_events = [e for e in events if e.type == "tool_result"]
    assert len(result_events) == 1
    assert result_events[0].verified is False
    assert result_events[0].verification_note == "Call gh_status to inspect readiness."


@pytest.mark.asyncio
async def test_run_turn_verification_hoisting_on_error(conversation):
    """Verify verification hoisting handles exception path (result=None)."""
    mock_executor = AsyncMock(side_effect=RuntimeError("Bridge timeout"))
    runner = ChatRunner(
        tool_executor=mock_executor,
        registry=_make_minimal_registry(),
    )

    tool_response = _make_tool_response(
        "rhino_objects", {}, tool_call_id="call_err"
    )
    text_response = _make_text_response("That failed.")

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return tool_response
        return text_response

    events = []
    with patch("litellm.acompletion", side_effect=mock_acompletion), _runtime_facts_patch():
        async for event in runner.run_turn(conversation, "fail", system_prompt="test"):
            events.append(event)

    # Should not crash; dispatch exceptions become structured failed results.
    result_events = [e for e in events if e.type == "tool_result"]
    assert len(result_events) == 1
    assert json.loads(result_events[0].result) == {
        "success": False,
        "error": "Bridge timeout",
    }
    assert result_events[0].tool_status == "failed"
    # Verification fields should stay separate from application failure.
    assert result_events[0].verified is None
    assert result_events[0].verification_note is None


def test_tool_registry_lru_eviction():
    """Verify LRU eviction frees slots when the cap is hit."""
    # Build a catalog with enough tools to fill and exceed a small cap
    catalog = {}
    for i in range(10):
        name = f"tool_{i}"
        catalog[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": f"Tool number {i}",
                "parameters": {"type": "object", "properties": {}},
            },
        }

    # Tiny cap of 5, no tier0 to keep things simple
    reg = ToolRegistry(catalog=catalog, max_active=5, tier0=set())

    # Manually activate tools 0-4, simulating early-turn usage
    for i in range(5):
        reg._active.add(f"tool_{i}")
        reg._last_used[f"tool_{i}"] = i  # staggered usage turns

    assert reg.get_active_count() == 5

    # Now try to load a group that includes tool_5, tool_6
    # We need to add them to a group first
    from rook.agent.tool_groups import TOOL_GROUPS
    # Use request directly via _evict_lru + manual load to test eviction
    freed = reg._evict_lru(2)
    assert freed == 2
    assert reg.get_active_count() == 3

    # The evicted tools should be the oldest (turn 0, turn 1) = tool_0, tool_1
    assert "tool_0" not in reg._active
    assert "tool_1" not in reg._active
    # Recent tools should survive
    assert "tool_4" in reg._active
    assert "tool_3" in reg._active


def test_tool_registry_lru_eviction_protects_tier0():
    """Verify LRU eviction never removes always-active (Tier 0) tools."""
    catalog = {}
    for i in range(6):
        name = f"tool_{i}"
        catalog[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": f"Tool number {i}",
                "parameters": {"type": "object", "properties": {}},
            },
        }

    tier0 = {"tool_0", "tool_1"}
    reg = ToolRegistry(catalog=catalog, max_active=4, tier0=tier0)

    # Tier 0 tools are auto-activated; add 2 more to fill cap
    reg._active.add("tool_2")
    reg._last_used["tool_2"] = 0
    reg._active.add("tool_3")
    reg._last_used["tool_3"] = 1
    assert reg.get_active_count() == 4

    # Evict 2 — should only evict tool_2 and tool_3, never tier0
    freed = reg._evict_lru(2)
    assert freed == 2
    assert "tool_0" in reg._active  # tier0 protected
    assert "tool_1" in reg._active  # tier0 protected
    assert "tool_2" not in reg._active
    assert "tool_3" not in reg._active

    # Now with only tier0 left, eviction should fail
    freed = reg._evict_lru(1)
    assert freed == 0


def _assistant_with_tool_calls(*tool_call_ids):
    """Build an assistant message with the given tool_call_ids."""
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": "rhino_ping", "arguments": "{}"},
            }
            for tc_id in tool_call_ids
        ],
    }


def _tool_result(tool_call_id, content="ok"):
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def test_patch_orphans_returns_zero_when_history_is_valid():
    """No-op: every tool_call has a matching tool_result already."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        {"role": "user", "content": "hi"},
        _assistant_with_tool_calls("tc1"),
        _tool_result("tc1"),
    ]
    before = list(messages)
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 0
    assert messages == before


def test_patch_orphans_appends_at_end_when_no_following_message():
    """Last assistant has [tc1, tc2], only tc1 has a result."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        {"role": "user", "content": "hi"},
        _assistant_with_tool_calls("tc1", "tc2"),
        _tool_result("tc1"),
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 1
    assert len(messages) == 4
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "tc2"
    assert json.loads(messages[3]["content"]) == {"error": "cancelled by user"}


def test_patch_orphans_inserts_multiple_at_end_in_order():
    """Last assistant has [tc1, tc2, tc3], only tc1 result present."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        _assistant_with_tool_calls("tc1", "tc2", "tc3"),
        _tool_result("tc1"),
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 2
    assert messages[2]["tool_call_id"] == "tc2"
    assert messages[3]["tool_call_id"] == "tc3"


def test_patch_orphans_inserts_before_user_message_not_after():
    """Synthetic tool_results must precede any following user message."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        _assistant_with_tool_calls("tc1", "tc2", "tc3"),
        _tool_result("tc1"),
        {"role": "user", "content": "follow-up"},
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 2
    assert [m.get("role") for m in messages] == ["assistant", "tool", "tool", "tool", "user"]
    assert messages[1]["tool_call_id"] == "tc1"
    assert messages[2]["tool_call_id"] == "tc2"
    assert messages[3]["tool_call_id"] == "tc3"
    assert messages[4]["content"] == "follow-up"


def test_patch_orphans_repairs_multiple_cancelled_turns():
    """Two prior cancelled turns, each with orphans, are both repaired."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [
        _assistant_with_tool_calls("tc1", "tc2"),
        _tool_result("tc1"),
        {"role": "user", "content": "first follow-up"},
        _assistant_with_tool_calls("tc3"),
        {"role": "user", "content": "second follow-up"},
    ]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 2
    assert [m.get("role") for m in messages] == [
        "assistant", "tool", "tool", "user",
        "assistant", "tool", "user",
    ]
    assert messages[2]["tool_call_id"] == "tc2"
    assert messages[5]["tool_call_id"] == "tc3"


def test_patch_orphans_synthetic_content_is_valid_json():
    """Synthetic content must round-trip through json.loads."""
    from rook.agent.chat.chat_runner import _patch_orphaned_tool_calls

    messages = [_assistant_with_tool_calls("tc1")]
    patched = _patch_orphaned_tool_calls(messages)
    assert patched == 1
    assert messages[1]["role"] == "tool"
    assert json.loads(messages[1]["content"]) == {"error": "cancelled by user"}


def test_run_turn_repairs_history_when_executor_raises_cancelled(conversation, runner):
    """CancelledError during tool dispatch still leaves valid history."""
    import asyncio

    async def _exercise():
        async def _stream():
            chunk = MagicMock()
            delta = MagicMock()
            delta.content = None
            tc_delta = MagicMock()
            tc_delta.index = 0
            tc_delta.id = "toolu_test_001"
            tc_delta.function.name = "rhino_ping"
            tc_delta.function.arguments = "{}"
            delta.tool_calls = [tc_delta]
            choice = MagicMock()
            choice.delta = delta
            chunk.choices = [choice]
            chunk.usage = None
            yield chunk

            usage_chunk = MagicMock()
            usage_chunk.choices = []
            usage_chunk.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            yield usage_chunk

        async def _cancelling_executor(name, params):
            raise asyncio.CancelledError()

        runner._tool_executor = _cancelling_executor

        with patch(
            "rook.agent.chat.chat_runner.litellm.acompletion",
            new=AsyncMock(return_value=_stream()),
        ), patch(
            "rook.agent.chat.chat_runner.collect_runtime_facts",
            new=AsyncMock(return_value={"rhino": {"connected": False}, "prompt": {"available": False}}),
        ):
            async for _ in runner.run_turn(conversation, "test message", "system"):
                pass

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_exercise())

    assistant_indices = [
        i for i, m in enumerate(conversation.messages)
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert len(assistant_indices) == 1
    asst_idx = assistant_indices[0]
    assert conversation.messages[asst_idx + 1]["role"] == "tool"
    assert conversation.messages[asst_idx + 1]["tool_call_id"] == "toolu_test_001"
    assert json.loads(conversation.messages[asst_idx + 1]["content"]) == {
        "error": "cancelled by user"
    }


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


def test_run_turn_repairs_prior_history_before_appending_new_user(conversation, runner):
    """Top-of-run repair inserts synthetic results before the new user turn."""
    import asyncio

    conversation.messages = [
        _assistant_with_tool_calls("tc1", "tc2"),
        _tool_result("tc1"),
    ]

    async def _exercise():
        with patch(
            "rook.agent.chat.chat_runner.litellm.acompletion",
            new=AsyncMock(return_value=_make_text_response("recovered")),
        ), _runtime_facts_patch():
            async for _ in runner.run_turn(conversation, "new question", "system"):
                pass

    asyncio.run(_exercise())

    assert [m.get("role") for m in conversation.messages[:4]] == [
        "assistant", "tool", "tool", "user",
    ]
    assert conversation.messages[2]["tool_call_id"] == "tc2"
    assert conversation.messages[3]["content"] == "new question"


def test_run_turn_repairs_history_when_generator_closes_at_tool_start(conversation, runner):
    """Client disconnect at a yielded tool_start repairs without close noise."""
    import asyncio

    async def _exercise():
        async def _stream():
            chunk = MagicMock()
            delta = MagicMock()
            delta.content = None
            tc_delta = MagicMock()
            tc_delta.index = 0
            tc_delta.id = "toolu_close_001"
            tc_delta.function.name = "rhino_ping"
            tc_delta.function.arguments = "{}"
            delta.tool_calls = [tc_delta]
            choice = MagicMock()
            choice.delta = delta
            chunk.choices = [choice]
            chunk.usage = None
            yield chunk

            usage_chunk = MagicMock()
            usage_chunk.choices = []
            usage_chunk.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
            yield usage_chunk

        with patch(
            "rook.agent.chat.chat_runner.litellm.acompletion",
            new=AsyncMock(return_value=_stream()),
        ), _runtime_facts_patch():
            gen = runner.run_turn(conversation, "test message", "system")
            event = await anext(gen)
            assert event.type == "tool_start"
            assert event.tool_call_id == "toolu_close_001"
            await gen.aclose()

    asyncio.run(_exercise())

    assistant_indices = [
        i for i, m in enumerate(conversation.messages)
        if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert len(assistant_indices) == 1
    asst_idx = assistant_indices[0]
    assert conversation.messages[asst_idx + 1]["role"] == "tool"
    assert conversation.messages[asst_idx + 1]["tool_call_id"] == "toolu_close_001"
    assert json.loads(conversation.messages[asst_idx + 1]["content"]) == {
        "error": "cancelled by user"
    }
