"""Tests for ChatRunner conversation-aware chat model pseudo-tools."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rook.agent.chat import chat_runner as chat_runner_module
from rook.agent.chat.conversation_store import Conversation
from rook.agent.chat.model_status import ModelOverrideResolution
from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat.tool_contracts import ToolResultView
from rook.agent.tool_registry import ToolRegistry


def _make_text_response(text: str):
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = text
        chunk.choices[0].delta.tool_calls = None
        chunk.usage = None
        yield chunk

        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        yield final

    return _gen()


def _make_tool_response(tool_name: str, tool_args: dict, tool_call_id: str):
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = tool_call_id
        tc_delta.function.name = tool_name
        tc_delta.function.arguments = json.dumps(tool_args)
        chunk.choices[0].delta.tool_calls = [tc_delta]
        chunk.usage = None
        yield chunk

        final = MagicMock()
        final.choices = []
        final.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        yield final

    return _gen()


def _runtime_facts_patch():
    return patch(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        new=AsyncMock(
            return_value={
                "rhino": {"connected": False},
                "prompt": {"available": False},
                "verified_runtime_facts": [],
            }
        ),
    )


def _qwen_resolution() -> ModelOverrideResolution:
    return ModelOverrideResolution(
        model_override="ollama_chat/qwen3:30b",
        api_base="",
        routing="local",
        provider="ollama_chat",
        api_base_source="none",
    )


@pytest.mark.asyncio
async def test_set_chat_model_stages_pending_and_does_not_change_current_turn():
    conv = Conversation(id="conv_test", persona="worker", model="anthropic/current", api_base="")
    runner = ChatRunner(tool_executor=AsyncMock())
    llm_models = []

    async def mock_acompletion(**kwargs):
        llm_models.append(kwargs["model"])
        if len(llm_models) == 1:
            return _make_tool_response(
                "set_chat_model",
                {
                    "model_override": "ollama_chat/qwen3:30b",
                    "reason": "Use local Qwen for the next turn.",
                },
                "call_set_model",
            )
        return _make_text_response("Qwen will be used next.")

    resolver = AsyncMock(return_value=_qwen_resolution())

    events = []
    with (
        patch("rook.agent.chat.chat_runner.litellm.acompletion", side_effect=mock_acompletion),
        patch("rook.agent.chat.model_status.resolve_allowed_model_override", resolver),
        _runtime_facts_patch(),
    ):
        async for event in runner.run_turn(conv, "use qwen", "system"):
            events.append(event)

    assert llm_models == ["anthropic/current", "anthropic/current"]
    assert conv.model == "ollama_chat/qwen3:30b"
    assert conv.pending_model == ""

    model_updates = [event for event in events if event.type == "model_update"]
    assert any(
        event.model == "ollama_chat/qwen3:30b" and event.applies_to == "next_turn"
        and event.content == "Model override staged for the next turn."
        for event in model_updates
    )
    assert any(
        event.model == "ollama_chat/qwen3:30b" and event.applies_to == "active"
        and event.content
        == "Model switch applied. Future turns in this conversation will use ollama_chat/qwen3:30b."
        for event in model_updates
    )


@pytest.mark.asyncio
async def test_set_chat_model_applies_pending_even_when_turn_aborts():
    conv = Conversation(id="conv_test", persona="worker", model="anthropic/current", api_base="")
    runner = ChatRunner(tool_executor=AsyncMock())

    async def mock_acompletion(**kwargs):
        return _make_tool_response(
            "set_chat_model",
            {
                "model_override": "ollama_chat/qwen3:30b",
                "reason": "Use local Qwen for the next turn.",
            },
            "call_set_model",
        )

    events = []
    with (
        patch("rook.agent.chat.chat_runner.litellm.acompletion", side_effect=mock_acompletion),
        patch(
            "rook.agent.chat.model_status.resolve_allowed_model_override",
            new=AsyncMock(return_value=_qwen_resolution()),
        ),
        _runtime_facts_patch(),
    ):
        async for event in runner.run_turn(conv, "use qwen", "system"):
            events.append(event)
            if event.type == "model_update" and event.applies_to == "next_turn":
                conv.abort_event.set()

    assert conv.model == "ollama_chat/qwen3:30b"
    assert conv.pending_model == ""
    assert conv.active_run_id is None
    assert any(
        event.type == "model_update"
        and event.model == "ollama_chat/qwen3:30b"
        and event.applies_to == "active"
        and event.content
        == "Model switch applied. Future turns in this conversation will use ollama_chat/qwen3:30b."
        for event in events
    )


@pytest.mark.asyncio
async def test_set_chat_model_rejects_api_base_without_staging_or_resolving():
    conv = Conversation(id="conv_test", persona="worker", model="anthropic/current", api_base="")
    runner = ChatRunner(tool_executor=AsyncMock())

    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                "set_chat_model",
                {
                    "model_override": "ollama_chat/qwen3:30b",
                    "api_base": "http://127.0.0.1:11434",
                },
                "call_set_model",
            )
        return _make_text_response("I cannot set api_base.")

    resolver = AsyncMock(return_value=_qwen_resolution())
    events = []
    with (
        patch("rook.agent.chat.chat_runner.litellm.acompletion", side_effect=mock_acompletion),
        patch("rook.agent.chat.model_status.resolve_allowed_model_override", resolver),
        _runtime_facts_patch(),
    ):
        async for event in runner.run_turn(conv, "use qwen with api base", "system"):
            events.append(event)

    resolver.assert_not_awaited()
    assert conv.model == "anthropic/current"
    assert conv.pending_model == ""
    assert not any(
        event.type == "model_update" and event.applies_to == "next_turn"
        for event in events
    )

    tool_results = [
        event for event in events
        if event.type == "tool_result" and event.name == "set_chat_model"
    ]
    assert len(tool_results) == 1
    result = json.loads(tool_results[0].result)
    assert result["success"] is False
    assert result["data"]["code"] == "api_base_not_allowed"


@pytest.mark.asyncio
async def test_set_chat_model_applies_pending_even_when_later_llm_call_errors():
    conv = Conversation(id="conv_test", persona="worker", model="anthropic/current", api_base="")
    runner = ChatRunner(tool_executor=AsyncMock())
    call_count = 0

    async def mock_acompletion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_tool_response(
                "set_chat_model",
                {
                    "model_override": "ollama_chat/qwen3:30b",
                    "reason": "Use local Qwen for the next turn.",
                },
                "call_set_model",
            )
        raise RuntimeError("forced llm failure")

    events = []
    with (
        patch("rook.agent.chat.chat_runner.litellm.acompletion", side_effect=mock_acompletion),
        patch(
            "rook.agent.chat.model_status.resolve_allowed_model_override",
            new=AsyncMock(return_value=_qwen_resolution()),
        ),
        _runtime_facts_patch(),
    ):
        async for event in runner.run_turn(conv, "use qwen", "system"):
            events.append(event)

    assert conv.model == "ollama_chat/qwen3:30b"
    assert conv.pending_model == ""
    assert any(
        event.type == "error" and event.content == "LLM error: forced llm failure"
        for event in events
    )
    assert any(
        event.type == "model_update"
        and event.model == "ollama_chat/qwen3:30b"
        and event.applies_to == "active"
        and event.content
        == "Model switch applied. Future turns in this conversation will use ollama_chat/qwen3:30b."
        for event in events
    )


@pytest.mark.asyncio
async def test_list_chat_models_returns_inline_tool_result():
    conv = Conversation(id="conv_test", persona="worker", model="anthropic/current", api_base="")
    payload = {
        "allowed_model_overrides": ["anthropic/current", "ollama_chat/qwen3:30b"],
        "local_providers": {"ollama": {"available": False, "models": []}},
    }
    builder = AsyncMock(return_value=payload)
    runner = ChatRunner(tool_executor=AsyncMock())

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

    tool_messages = [message for message in conv.messages if message.get("role") == "tool"]
    assert len(tool_messages) == 1
    tool_payload = json.loads(tool_messages[0]["content"])
    assert tool_payload["allowed_model_overrides"] == payload["allowed_model_overrides"]
    assert tool_payload == payload
    assert any(
        event.type == "tool_result" and event.name == "list_chat_models"
        for event in events
    )
    builder.assert_awaited_once()


def test_chat_model_tools_are_offered_in_fresh_runner_active_schemas():
    runner = ChatRunner(tool_executor=AsyncMock())

    active_names = {
        schema.get("function", {}).get("name")
        for schema in runner._registry.get_active_schemas()
    }

    assert "list_chat_models" in active_names
    assert "set_chat_model" in active_names


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
