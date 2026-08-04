from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat import chat_runner as chat_runner_module
from rook.agent.chat.conversation_store import Conversation
from rook.agent.tool_registry import ToolRegistry, build_catalog_from_mcp_tools
from rook.mcp_capability_gateway_contract import (
    MCP_CAPABILITY_GATEWAY_NAMES,
    build_mcp_capability_gateway_tools,
)


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="gateway_test", persona="worker", model="test-model")


@pytest.fixture
def minimal_registry() -> ToolRegistry:
    return ToolRegistry(
        catalog={
            "rhino_ping": {
                "type": "function",
                "function": {
                    "name": "rhino_ping",
                    "description": "Check Rhino connectivity.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
        },
        tier0={"rhino_ping", "request_tools", "search_tools"},
        agent_mode=True,
    )


def _schema_map(runner: ChatRunner) -> dict[str, dict]:
    return {
        schema["function"]["name"]: schema
        for schema in runner._get_active_tool_schemas()
    }


def test_bare_runner_does_not_advertise_canonical_gateway(minimal_registry):
    runner = ChatRunner(tool_executor=AsyncMock(), registry=minimal_registry)

    assert MCP_CAPABILITY_GATEWAY_NAMES.isdisjoint(_schema_map(runner))


def test_executor_presence_exposes_exact_normalized_canonical_schemas(
    minimal_registry,
):
    runner = ChatRunner(
        tool_executor=AsyncMock(),
        registry=minimal_registry,
        mcp_capability_executor=AsyncMock(),
    )
    expected = build_catalog_from_mcp_tools(
        list(build_mcp_capability_gateway_tools())
    )
    actual = _schema_map(runner)

    assert {name: actual[name] for name in MCP_CAPABILITY_GATEWAY_NAMES} == expected


def test_gateway_exposure_preserves_existing_direct_schema_order_and_values(
    minimal_registry,
):
    bare = ChatRunner(tool_executor=AsyncMock(), registry=minimal_registry)
    bridged = ChatRunner(
        tool_executor=AsyncMock(),
        registry=minimal_registry,
        mcp_capability_executor=AsyncMock(),
    )

    bare_schemas = bare._get_active_tool_schemas()
    bridged_direct = [
        schema
        for schema in bridged._get_active_tool_schemas()
        if schema["function"]["name"] not in MCP_CAPABILITY_GATEWAY_NAMES
    ]

    assert bridged_direct == bare_schemas


def test_chatrunner_rejects_unknown_tool_access_before_surface_construction(
    minimal_registry,
):
    with pytest.raises(ValueError, match="tool_access"):
        ChatRunner(
            tool_executor=AsyncMock(),
            registry=minimal_registry,
            tool_access="lean",
            mcp_capability_executor=AsyncMock(),
        )


@pytest.mark.parametrize("invalid_executor", [object(), False, 0])
def test_chatrunner_rejects_noncallable_gateway_before_surface_construction(
    minimal_registry, invalid_executor
):
    with pytest.raises(
        TypeError,
        match="mcp_capability_executor must be callable",
    ):
        ChatRunner(
            tool_executor=AsyncMock(),
            registry=minimal_registry,
            mcp_capability_executor=invalid_executor,
        )


def test_registry_gateway_copy_is_hidden_or_replaced_by_canonical_schema():
    rogue_schema = {
        "type": "function",
        "function": {
            "name": "rook_tools_search",
            "description": "Rogue duplicate.",
            "parameters": {
                "type": "object",
                "properties": {"wrong": {"type": "boolean"}},
            },
        },
    }
    registry = ToolRegistry(
        catalog={"rook_tools_search": rogue_schema},
        tier0={"rook_tools_search"},
        agent_mode=True,
    )

    bare = ChatRunner(tool_executor=AsyncMock(), registry=registry)
    bridged = ChatRunner(
        tool_executor=AsyncMock(),
        registry=registry,
        mcp_capability_executor=AsyncMock(),
    )
    expected = build_catalog_from_mcp_tools(
        list(build_mcp_capability_gateway_tools())
    )["rook_tools_search"]
    visible = bridged._get_active_tool_schemas()

    assert "rook_tools_search" not in _schema_map(bare)
    assert [
        schema["function"]["name"] for schema in visible
    ].count("rook_tools_search") == 1
    assert _schema_map(bridged)["rook_tools_search"] == expected


def _tool_response(name: str, arguments: dict, call_id: str = "gateway_call"):
    async def stream():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = None
        tool_delta = MagicMock()
        tool_delta.index = 0
        tool_delta.id = call_id
        tool_delta.function.name = name
        tool_delta.function.arguments = json.dumps(arguments)
        chunk.choices[0].delta.tool_calls = [tool_delta]
        chunk.usage = None
        yield chunk

    return stream()


def _text_response(text: str):
    async def stream():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = text
        chunk.choices[0].delta.tool_calls = None
        chunk.usage = None
        yield chunk

    return stream()


def _runtime_facts_patch():
    return patch(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        new=AsyncMock(
            return_value={
                "rhino": {"connected": True},
                "prompt": {"available": True},
                "verified_runtime_facts": [],
            }
        ),
    )


@pytest.mark.asyncio
async def test_gateway_call_uses_only_injected_executor(
    monkeypatch, conversation, minimal_registry
):
    direct = AsyncMock()
    gateway_result = {"matches": [{"name": "gh_library"}]}
    gateway = AsyncMock(return_value=gateway_result)
    substrate = MagicMock()
    monkeypatch.setattr(chat_runner_module, "extract_substrate_observation", substrate)
    runner = ChatRunner(
        tool_executor=direct,
        registry=minimal_registry,
        mcp_capability_executor=gateway,
    )
    responses = iter(
        [
            _tool_response("rook_tools_search", {"query": "component"}),
            _text_response("Finished"),
        ]
    )
    model_surfaces = []

    async def fake_acompletion(**kwargs):
        model_surfaces.append(
            {
                schema["function"]["name"]
                for schema in (kwargs.get("tools") or [])
            }
        )
        return next(responses)

    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        side_effect=fake_acompletion,
    ), _runtime_facts_patch():
        events = [
            event
            async for event in runner.run_turn(conversation, "intent", "skill")
        ]

    gateway.assert_awaited_once_with(
        "rook_tools_search", {"query": "component"}
    )
    direct.assert_not_awaited()
    substrate.assert_not_called()
    assert MCP_CAPABILITY_GATEWAY_NAMES <= model_surfaces[0]
    assert "rhino_ping" in model_surfaces[0]
    assert [event.type for event in events] == [
        "tool_start",
        "tool_result",
        "text_delta",
        "done",
    ]
    result_event = next(event for event in events if event.type == "tool_result")
    assert json.loads(result_event.result) == gateway_result
    retained = [
        message
        for message in conversation.messages
        if message.get("tool_call_id") == "gateway_call"
    ]
    assert len(retained) == 1
    assert json.loads(retained[0]["content"]) == gateway_result
    done_event = next(event for event in events if event.type == "done")
    assert done_event.usage["active_tools"] == 7


@pytest.mark.asyncio
async def test_hallucinated_gateway_without_executor_never_falls_back_to_direct(
    conversation, minimal_registry
):
    direct = AsyncMock(return_value={"wrong": "direct"})
    runner = ChatRunner(tool_executor=direct, registry=minimal_registry)
    responses = iter(
        [
            _tool_response(
                "rook_tools_call",
                {"name": "gh_library", "arguments": {}},
            ),
            _text_response("Stopped"),
        ]
    )

    async def fake_acompletion(**_kwargs):
        return next(responses)

    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        side_effect=fake_acompletion,
    ), _runtime_facts_patch():
        events = [
            event
            async for event in runner.run_turn(conversation, "intent", "skill")
        ]

    direct.assert_not_awaited()
    result = json.loads(
        next(event.result for event in events if event.type == "tool_result")
    )
    assert result == {
        "success": False,
        "error": "Canonical MCP capability gateway is unavailable.",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("rook_tools_ls", {"path": "/gh"}),
        ("rook_tools_search", {"query": "component"}),
        ("rook_tools_read", {"name": "gh_library"}),
    ],
)
async def test_gateway_discovery_calls_retain_meta_only_round_limit(
    monkeypatch, conversation, minimal_registry, tool_name, arguments
):
    monkeypatch.setattr(chat_runner_module, "MAX_META_ONLY_ROUNDS", 2)
    direct = AsyncMock()
    gateway = AsyncMock(return_value={"discovery": tool_name})
    runner = ChatRunner(
        tool_executor=direct,
        registry=minimal_registry,
        mcp_capability_executor=gateway,
    )
    model_calls = 0

    async def fake_acompletion(**_kwargs):
        nonlocal model_calls
        model_calls += 1
        return _tool_response(tool_name, arguments, f"discovery_{model_calls}")

    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        side_effect=fake_acompletion,
    ), _runtime_facts_patch():
        events = [
            event
            async for event in runner.run_turn(conversation, "intent", "skill")
        ]

    direct.assert_not_awaited()
    assert gateway.await_count == 2
    assert model_calls == 2
    assert any(
        event.type == "error" and "stuck loading tools" in event.content
        for event in events
    )


@pytest.mark.asyncio
async def test_gateway_execution_call_resets_discovery_only_round_count(
    monkeypatch, conversation, minimal_registry
):
    monkeypatch.setattr(chat_runner_module, "MAX_META_ONLY_ROUNDS", 2)
    direct = AsyncMock()
    gateway = AsyncMock(return_value={"success": True})
    runner = ChatRunner(
        tool_executor=direct,
        registry=minimal_registry,
        mcp_capability_executor=gateway,
    )
    responses = iter(
        [
            _tool_response("rook_tools_search", {"query": "component"}, "d1"),
            _tool_response(
                "rook_tools_call",
                {"name": "gh_library", "arguments": {}},
                "execute",
            ),
            _tool_response("rook_tools_read", {"name": "gh_library"}, "d2"),
            _text_response("Finished"),
        ]
    )

    async def fake_acompletion(**_kwargs):
        return next(responses)

    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        side_effect=fake_acompletion,
    ), _runtime_facts_patch():
        events = [
            event
            async for event in runner.run_turn(conversation, "intent", "skill")
        ]

    direct.assert_not_awaited()
    assert gateway.await_count == 3
    assert not any(event.type == "error" for event in events)
    assert [event.type for event in events][-2:] == ["text_delta", "done"]


@pytest.mark.asyncio
async def test_gateway_exception_is_retained_once_without_retry_or_fallback(
    conversation, minimal_registry
):
    direct = AsyncMock()
    gateway = AsyncMock(side_effect=RuntimeError("gateway sentinel"))
    runner = ChatRunner(
        tool_executor=direct,
        registry=minimal_registry,
        mcp_capability_executor=gateway,
    )
    responses = iter(
        [
            _tool_response("rook_tools_read", {"name": "gh_library"}),
            _text_response("Stopped"),
        ]
    )

    async def fake_acompletion(**_kwargs):
        return next(responses)

    with patch(
        "rook.agent.chat.chat_runner.litellm.acompletion",
        side_effect=fake_acompletion,
    ), _runtime_facts_patch():
        events = [
            event
            async for event in runner.run_turn(conversation, "intent", "skill")
        ]

    gateway.assert_awaited_once()
    direct.assert_not_awaited()
    result_event = next(event for event in events if event.type == "tool_result")
    assert json.loads(result_event.result) == {
        "success": False,
        "error": "gateway sentinel",
    }
    retained = [
        message
        for message in conversation.messages
        if message.get("tool_call_id") == "gateway_call"
    ]
    assert len(retained) == 1
    assert retained[0]["content"] == result_event.result
