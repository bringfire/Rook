from __future__ import annotations

import ast
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat import chat_runner as chat_runner_module
from rook.agent.chat import server as chat_server
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


def _decode_retained_tool_content(content: str):
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return ast.literal_eval(content)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "endpoint", "method", "native_data"),
    [
        ("gh_edit", {"epoch": 0}, "/gh/edit", "POST", ({"epoch": 0}, {"epoch": 0})),
        ("gh_snapshot", {}, "/gh/snapshot", "POST", (None, {})),
        ("gh_status", {}, "/gh/status", "GET", (None, None)),
        ("gh_errors", {}, "/gh/errors", "GET", (None, {})),
    ],
)
async def test_authoritative_grasshopper_results_match_direct_and_gateway_without_hints(
    monkeypatch,
    tool_name,
    arguments,
    endpoint,
    method,
    native_data,
):
    from rook import server as rook_server
    from rook.agent import tool_dispatcher as dispatcher_module
    from rook.agent.tool_dispatcher import ToolDispatcher

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    rook_server._reset_capability_index_cache()
    monkeypatch.setattr(
        rook_server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    native = {"success": True, "data": {"sentinel": tool_name}}
    target_calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        target_calls.append((endpoint, method, copy.deepcopy(data), port))
        return copy.deepcopy(native)

    async def forbidden_injection(*_args, **_kwargs):
        raise AssertionError("knowledge injection reached authoritative result")

    def forbidden_store():
        raise AssertionError("knowledge store reached authoritative result")

    monkeypatch.setattr(rook_server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(dispatcher_module, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(rook_server, "inject_knowledge", forbidden_injection)
    monkeypatch.setattr(rook_server, "get_unified_store", forbidden_store)
    monkeypatch.setattr(rook_server, "_record_gh_to_session", AsyncMock())
    monkeypatch.setattr(rook_server, "_record_observation", lambda *_args: None)

    direct_arguments = copy.deepcopy(arguments)
    gateway_arguments = copy.deepcopy(arguments)
    direct = await ToolDispatcher().dispatch(tool_name, direct_arguments)
    canonical = await rook_server.call_tool(
        "rook_tools_call",
        {"name": tool_name, "arguments": gateway_arguments},
        _public_mcp=True,
    )

    assert direct_arguments == arguments
    assert gateway_arguments == arguments
    assert canonical.structuredContent == direct
    assert direct["data"]["sentinel"] == tool_name
    assert "knowledge_hint" not in direct["data"]
    assert "gotchas" not in direct["data"]
    assert target_calls == [
        (endpoint, method, native_data[0], None),
        (endpoint, method, native_data[1], None),
    ]


def test_default_chat_service_runner_receives_real_scope_bound_gateway(
    monkeypatch,
):
    from rook import server as rook_server

    executor = AsyncMock()
    factory = MagicMock(return_value=executor)
    monkeypatch.setattr(chat_server, "_runner", None)
    monkeypatch.setattr(
        rook_server,
        "build_mcp_capability_gateway_executor",
        factory,
    )

    runner = chat_server._get_runner()

    factory.assert_called_once_with("full")
    assert runner._mcp_capability_executor is executor
    assert MCP_CAPABILITY_GATEWAY_NAMES <= set(_schema_map(runner))


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


async def _run_one_gateway_turn(
    conversation: Conversation,
    runner: ChatRunner,
    tool_name: str,
    arguments: dict,
):
    responses = iter(
        [
            _tool_response(tool_name, arguments, "one_gateway_call"),
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
            async for event in runner.run_turn(
                conversation,
                "Use the reviewed gateway",
                "Reviewed skill body",
            )
        ]

    result_event = next(event for event in events if event.type == "tool_result")
    return events, _decode_retained_tool_content(result_event.result)


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


@pytest.mark.asyncio
async def test_real_gateway_runs_complete_discovery_and_call_loop_without_contact(
    monkeypatch, conversation
):
    from types import SimpleNamespace

    from rook import server as rook_server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    rook_server._reset_capability_index_cache()
    monkeypatch.setattr(
        rook_server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    target_calls = []

    async def no_contact_target(name, arguments):
        target_calls.append((name, arguments))
        return {
            "success": True,
            "data": {"target": name, "arguments": arguments},
        }

    monkeypatch.setattr(
        rook_server,
        "_call_tool_dispatch",
        no_contact_target,
    )
    index = await rook_server._get_capability_index()
    library_search = {"query": "gh_library", "limit": 10}
    library_arguments = {"search": "series", "limit": 5}
    batch_search = {"query": "gh_batch_component_info", "limit": 10}
    batch_arguments = {"names": ["Series"]}
    expected_agent_results = [
        index.search("gh_library", limit=10),
        index.read("gh_library"),
        {"target": "gh_library", "arguments": library_arguments},
        index.search("gh_batch_component_info", limit=10),
        index.read("gh_batch_component_info"),
        {
            "target": "gh_batch_component_info",
            "arguments": batch_arguments,
        },
    ]
    direct_tool_executor = AsyncMock()
    runner = ChatRunner(
        tool_executor=direct_tool_executor,
        mcp_capability_executor=(
            rook_server.build_mcp_capability_gateway_executor("full")
        ),
    )
    responses = iter(
        [
            _tool_response("rook_tools_search", library_search, "search_library"),
            _tool_response(
                "rook_tools_read",
                {"name": "gh_library"},
                "read_library",
            ),
            _tool_response(
                "rook_tools_call",
                {"name": "gh_library", "arguments": library_arguments},
                "call_library",
            ),
            _tool_response(
                "rook_tools_search",
                batch_search,
                "search_batch_info",
            ),
            _tool_response(
                "rook_tools_read",
                {"name": "gh_batch_component_info"},
                "read_batch_info",
            ),
            _tool_response(
                "rook_tools_call",
                {
                    "name": "gh_batch_component_info",
                    "arguments": batch_arguments,
                },
                "call_batch_info",
            ),
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
            async for event in runner.run_turn(
                conversation,
                "Build with reviewed Grasshopper capabilities",
                "Reviewed skill body",
            )
        ]

    assert target_calls == [
        ("gh_library", library_arguments),
        ("gh_batch_component_info", batch_arguments),
    ]
    direct_tool_executor.assert_not_awaited()
    tool_messages = [
        message
        for message in conversation.messages
        if message.get("role") == "tool"
    ]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "search_library",
        "read_library",
        "call_library",
        "search_batch_info",
        "read_batch_info",
        "call_batch_info",
    ]
    assert [
        _decode_retained_tool_content(message["content"])
        for message in tool_messages
    ] == expected_agent_results
    assert events[-1].type == "done"


@pytest.mark.asyncio
async def test_real_gateway_preserves_ingress_and_canonical_rhino_targeting(
    monkeypatch, conversation
):
    from rook import bridge
    from rook import server as rook_server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    rook_server._reset_capability_index_cache()
    monkeypatch.setattr(
        rook_server.targeting,
        "_PANEL_TARGET_LOCK",
        rook_server.targeting.PanelTargetLock(
            mode="panel_locked",
            process_id=7101,
            document_serial_number=42,
        ),
    )
    monkeypatch.setattr(
        rook_server.targeting,
        "_PANEL_TARGET_CONFIG_ERROR",
        None,
    )
    monkeypatch.setattr(
        rook_server.targeting,
        "discover_instances",
        lambda: [
            {
                "host": "127.0.0.1",
                "port": 9950,
                "processId": 7101,
                "pluginType": "native",
                "documentName": "Gateway.3dm",
            }
        ],
    )
    target_dispatch = []

    async def no_contact_target(name, arguments):
        target_dispatch.append(
            (name, arguments, bridge.get_rhino_request_context())
        )
        return {"success": True, "data": {"targeted": True}}

    monkeypatch.setattr(
        rook_server,
        "_call_tool_dispatch",
        no_contact_target,
    )
    canonical = rook_server.build_mcp_capability_gateway_executor("full")
    ingress = []

    async def capturing_executor(name, arguments):
        ingress.append((name, arguments))
        return await canonical(name, arguments)

    direct = AsyncMock()
    runner = ChatRunner(
        tool_executor=direct,
        mcp_capability_executor=capturing_executor,
    )
    model_arguments = {
        "name": "gh_library",
        "arguments": {"search": "Point"},
        "tool_access": "readonly",
        "profile": "readonly",
        "mcp_capability_executor": "alternate",
    }

    events, result = await _run_one_gateway_turn(
        conversation,
        runner,
        "rook_tools_call",
        model_arguments,
    )

    assert ingress == [("rook_tools_call", model_arguments)]
    assert target_dispatch == [
        (
            "gh_library",
            {"search": "Point", "documentSerialNumber": 42},
            {
                "port": 9950,
                "process_id": 7101,
                "document_serial_number": 42,
            },
        )
    ]
    assert result == {"targeted": True}
    assert events[-1].type == "done"
    direct.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_access", "mcp_profile"),
    [
        ("readonly", "full"),
        ("readonly", "lean"),
        ("full", "readonly"),
    ],
)
async def test_real_gateway_profile_intersection_blocks_write_before_dispatch(
    monkeypatch, conversation, tool_access, mcp_profile
):
    from rook import server as rook_server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", mcp_profile)
    rook_server._reset_capability_index_cache()
    target_dispatch = AsyncMock()
    monkeypatch.setattr(
        rook_server,
        "_call_tool_dispatch",
        target_dispatch,
    )
    direct = AsyncMock()
    runner = ChatRunner(
        tool_executor=direct,
        tool_access=tool_access,
        mcp_capability_executor=(
            rook_server.build_mcp_capability_gateway_executor(tool_access)
        ),
    )

    _events, result = await _run_one_gateway_turn(
        conversation,
        runner,
        "rook_tools_call",
        {"name": "rhino_create", "arguments": {"bogus": True}},
    )

    assert result["success"] is False
    assert result["data"]["code"] == "tool_profile_blocked"
    target_dispatch.assert_not_awaited()
    direct.assert_not_awaited()


@pytest.mark.asyncio
async def test_real_gateway_invalid_profile_refuses_before_index_or_dispatch(
    monkeypatch, conversation
):
    from rook import server as rook_server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "invalid-profile")
    capability_index = AsyncMock()
    target_dispatch = AsyncMock()
    monkeypatch.setattr(
        rook_server,
        "_get_capability_index",
        capability_index,
    )
    monkeypatch.setattr(
        rook_server,
        "_call_tool_dispatch",
        target_dispatch,
    )
    direct = AsyncMock()
    runner = ChatRunner(
        tool_executor=direct,
        mcp_capability_executor=(
            rook_server.build_mcp_capability_gateway_executor("full")
        ),
    )

    _events, result = await _run_one_gateway_turn(
        conversation,
        runner,
        "rook_tools_search",
        {"query": "grid"},
    )

    assert result["success"] is False
    assert "Invalid ROOK_MCP_TOOL_PROFILE" in result["error"]
    capability_index.assert_not_awaited()
    target_dispatch.assert_not_awaited()
    direct.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "error_field", "error_code"),
    [
        (
            {"name": "rook_tools_ls"},
            "error",
            "meta_recursion_forbidden",
        ),
        (
            {"name": "spawn_agent"},
            "code",
            "legacy_semantic_tool_contained",
        ),
        (
            {"name": "definitely_not_a_tool"},
            "error",
            "not_mcp_dispatchable",
        ),
        (
            {"name": "rhino_instances", "arguments": "not-an-object"},
            "error",
            "invalid_arguments",
        ),
        (
            {"name": "gh_batch_component_info", "arguments": {}},
            "error",
            "invalid_arguments",
        ),
    ],
)
async def test_real_gateway_refusals_never_dispatch_or_fall_back(
    monkeypatch, conversation, arguments, error_field, error_code
):
    from rook import server as rook_server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    rook_server._reset_capability_index_cache()
    target_dispatch = AsyncMock()
    monkeypatch.setattr(
        rook_server,
        "_call_tool_dispatch",
        target_dispatch,
    )
    direct = AsyncMock()
    runner = ChatRunner(
        tool_executor=direct,
        mcp_capability_executor=(
            rook_server.build_mcp_capability_gateway_executor("full")
        ),
    )

    _events, result = await _run_one_gateway_turn(
        conversation,
        runner,
        "rook_tools_call",
        arguments,
    )

    assert result["success"] is False
    assert result["data"][error_field] == error_code
    target_dispatch.assert_not_awaited()
    direct.assert_not_awaited()
