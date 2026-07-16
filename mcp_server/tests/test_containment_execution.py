from __future__ import annotations

import json
import builtins
from collections.abc import Iterator, Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import types as mcp_types
from mcp.server.lowlevel import server as mcp_lowlevel_server

from rook import server
from rook.agent import tool_dispatcher as dispatcher_module
from rook.agent.tool_dispatcher import ToolDispatcher
from rook.tool_lifecycle import (
    DispatchOrigin,
    containment_envelope,
    containment_payload,
    resolve_contained_identity,
)
from rook import tool_lifecycle_runtime


EXPECTED_RED = "EXPECTED_RED:T3:BOUNDARIES"
CONTAINED_NAMES = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)
PROFILES = ("full", "lean", "readonly")


def _entry(name: str):
    entry = resolve_contained_identity(name)
    assert entry is not None
    return entry


def _expected_public_text(name: str) -> str:
    return f"Error: {json.dumps(containment_payload(_entry(name)), indent=2)}"


def _assert_public_denial(contents: object, name: str) -> None:
    assert isinstance(contents, list), EXPECTED_RED
    assert len(contents) == 1, EXPECTED_RED
    content = contents[0]
    assert isinstance(content, mcp_types.TextContent), EXPECTED_RED
    assert content.text == _expected_public_text(name), EXPECTED_RED


def _assert_internal_denial(result: object, name: str) -> None:
    assert result == containment_envelope(_entry(name)), EXPECTED_RED


def _snapshot_delta(
    before: dict[str, object],
    after: dict[str, object],
) -> list[dict[str, str]]:
    assert before["process_id"] == after["process_id"], EXPECTED_RED
    assert (
        before["process_start_token"] == after["process_start_token"]
    ), EXPECTED_RED
    before_events = before["events"]
    after_events = after["events"]
    assert isinstance(before_events, list), EXPECTED_RED
    assert isinstance(after_events, list), EXPECTED_RED
    assert len(before_events) < 50, EXPECTED_RED
    assert after_events[: len(before_events)] == before_events, EXPECTED_RED
    return after_events[len(before_events):]


def _telemetry_probe(monkeypatch, tmp_path):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    attempts: list[tuple[str, str]] = []
    real_recorder = tool_lifecycle_runtime._record_containment_denial

    def recording_spy(entry, origin):
        attempts.append((entry.name, origin.value))
        return real_recorder(entry, origin)

    monkeypatch.setattr(
        tool_lifecycle_runtime,
        "_record_containment_denial",
        recording_spy,
    )
    return store, attempts


def _assert_one_denial_event(
    store,
    attempts: list[tuple[str, str]],
    before: dict[str, object],
    *,
    name: str,
    origin: DispatchOrigin,
) -> None:
    after = store.get_containment_denials_snapshot()
    assert attempts == [(name, origin.value)], EXPECTED_RED
    added = _snapshot_delta(before, after)
    assert len(added) == 1, EXPECTED_RED
    event = added[0]
    assert set(event) == {
        "tool",
        "disposition",
        "origin",
        "timestamp",
    }, EXPECTED_RED
    assert event["tool"] == name, EXPECTED_RED
    assert event["disposition"] == _entry(name).disposition.value, EXPECTED_RED
    assert event["origin"] == origin.value, EXPECTED_RED


class _PoisonMapping(Mapping[str, object]):
    def __init__(self, events: list[str], label: str = "arguments"):
        self._events = events
        self._label = label

    def _fail(self, action: str):
        self._events.append(f"{self._label}:{action}")
        raise AssertionError(
            f"{EXPECTED_RED} {self._label} was accessed via {action}"
        )

    def __getitem__(self, key: str) -> object:
        return self._fail(f"getitem:{key}")

    def __iter__(self) -> Iterator[str]:
        return self._fail("iter")

    def __len__(self) -> int:
        return self._fail("len")

    def __bool__(self) -> bool:
        return self._fail("bool")

    def get(self, key: str, default: object = None) -> object:
        return self._fail(f"get:{key}")

    def items(self):
        return self._fail("items")

    def keys(self):
        return self._fail("keys")

    def copy(self):
        return self._fail("copy")


class _OuterTargetMapping(Mapping[str, object]):
    """Mapping that permits only exact raw target-name reads."""

    def __init__(self, target: object, events: list[str]):
        self._target = target
        self._events = events

    def _fail(self, action: str):
        self._events.append(f"outer:{action}")
        raise AssertionError(
            f"{EXPECTED_RED} outer progressive arguments accessed via {action}"
        )

    def get(self, key: str, default: object = None) -> object:
        if key == "name":
            return self._target
        return self._fail(f"get:{key}")

    def __getitem__(self, key: str) -> object:
        if key == "name":
            return self._target
        return self._fail(f"getitem:{key}")

    def __iter__(self) -> Iterator[str]:
        return self._fail("iter")

    def __len__(self) -> int:
        return self._fail("len")

    def __bool__(self) -> bool:
        return self._fail("bool")


class _TrackingDirectParams:
    def __init__(self, name: str, events: list[str]):
        self.name = name
        self._events = events

    @property
    def arguments(self) -> dict[str, object]:
        self._events.append("transport:arguments")
        return {"unexpected": True}


class _PoisonLocalMapping(dict):
    def __init__(self, events: list[str]):
        super().__init__()
        self._events = events

    def __contains__(self, key: object) -> bool:
        self._events.append("local:contains")
        raise AssertionError(f"{EXPECTED_RED} local lookup reached")

    def __getitem__(self, key: object) -> object:
        self._events.append("local:getitem")
        raise AssertionError(f"{EXPECTED_RED} local handler lookup reached")


class _PoisonKnowledgeMapping(dict):
    def __init__(self, events: list[str]):
        super().__init__()
        self._events = events

    def __getitem__(self, key: object) -> object:
        self._events.append("knowledge:getitem")
        raise AssertionError(f"{EXPECTED_RED} knowledge lookup reached")


class _FakeCapabilityIndex:
    def read(self, _name: object, **_kwargs):
        return None


def _poison_private_handler_imports(monkeypatch, events: list[str]) -> None:
    real_import = builtins.__import__

    def import_spy(name, globals=None, locals=None, fromlist=(), level=0):
        if level == 1 and name in {
            "agent.spawn",
            "agent.planner",
            "agent.tool_registry",
        }:
            events.append(f"model-import:{name}")
            raise AssertionError(
                f"{EXPECTED_RED} private handler imported {name}"
            )
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_spy)


def _install_server_spies(monkeypatch, events: list[str]) -> None:
    def profile_spy(_env):
        events.append("profile")
        return server.Profile.FULL

    def target_spy(_name):
        events.append("target")
        return SimpleNamespace(requires_rhino=False)

    async def dispatch_spy(_name, _arguments):
        events.append("host")
        return {"success": True, "data": {"unexpected": "dispatch"}}

    async def capability_spy():
        events.append("capability")
        return _FakeCapabilityIndex()

    def validation_spy(_schema, _arguments):
        events.append("schema")
        return []

    def knowledge_spy(_name, _result):
        events.append("knowledge")
        return False

    def observation_spy(*_args, **_kwargs):
        events.append("observation")

    def receipt_spy(*_args, **_kwargs):
        events.append("receipt")
        return {}

    monkeypatch.setattr(server, "resolve_profile", profile_spy)
    monkeypatch.setattr(server.targeting, "policy_for_tool", target_spy)
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch_spy)
    monkeypatch.setattr(server, "_get_capability_index", capability_spy)
    monkeypatch.setattr(server, "validate_arguments", validation_spy)
    monkeypatch.setattr(server, "should_inject", knowledge_spy)
    monkeypatch.setattr(server, "_record_observation", observation_spy)
    monkeypatch.setattr(server, "build_script_receipt", receipt_spy)

    from rook.agent import substrate_analytics

    monkeypatch.setattr(
        substrate_analytics,
        "persist_substrate_observation",
        lambda *_args, **_kwargs: events.append("substrate"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("name", CONTAINED_NAMES)
async def test_direct_call_tool_denies_before_arguments_profile_or_dispatch(
    monkeypatch,
    tmp_path,
    profile: str,
    name: str,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []
    _install_server_spies(monkeypatch, events)
    before = store.get_containment_denials_snapshot()

    result = await server.call_tool(name, _PoisonMapping(events))

    _assert_public_denial(result, name)
    _assert_one_denial_event(
        store,
        attempts,
        before,
        name=name,
        origin=DispatchOrigin.PUBLIC_MCP,
    )
    assert events == [], EXPECTED_RED


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("name", CONTAINED_NAMES)
async def test_progressive_call_tool_denies_raw_target_before_nested_arguments(
    monkeypatch,
    tmp_path,
    profile: str,
    name: str,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []
    _install_server_spies(monkeypatch, events)
    before = store.get_containment_denials_snapshot()
    outer = _OuterTargetMapping(name, events)

    result = await server.call_tool("rook_tools_call", outer)

    _assert_public_denial(result, name)
    _assert_one_denial_event(
        store,
        attempts,
        before,
        name=name,
        origin=DispatchOrigin.PROGRESSIVE_META,
    )
    assert events == [], EXPECTED_RED


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("name", CONTAINED_NAMES)
async def test_registered_mcp_handler_denies_direct_calls_before_sdk_validation(
    monkeypatch,
    tmp_path,
    profile: str,
    name: str,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []
    _install_server_spies(monkeypatch, events)

    async def cached_definition_spy(_self, raw_name):
        events.append("sdk:cache")
        return mcp_types.Tool(
            name=raw_name,
            description="test",
            inputSchema={
                "type": "object",
                "required": ["required_value"],
                "properties": {"required_value": {"type": "string"}},
            },
        )

    real_validate = mcp_lowlevel_server.jsonschema.validate

    def sdk_validate_spy(*args, **kwargs):
        events.append("sdk:schema")
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(
        mcp_lowlevel_server.Server,
        "_get_cached_tool_definition",
        cached_definition_spy,
    )
    monkeypatch.setattr(mcp_lowlevel_server.jsonschema, "validate", sdk_validate_spy)
    request = SimpleNamespace(params=_TrackingDirectParams(name, events))
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    before = store.get_containment_denials_snapshot()

    transport = await handler(request)

    assert isinstance(transport, mcp_types.ServerResult), EXPECTED_RED
    result = transport.root
    assert isinstance(result, mcp_types.CallToolResult), EXPECTED_RED
    assert result.isError is False, EXPECTED_RED
    _assert_public_denial(result.content, name)
    _assert_one_denial_event(
        store,
        attempts,
        before,
        name=name,
        origin=DispatchOrigin.PUBLIC_MCP,
    )
    assert events == [], EXPECTED_RED


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("name", CONTAINED_NAMES)
async def test_registered_mcp_handler_denies_progressive_calls_before_sdk_validation(
    monkeypatch,
    tmp_path,
    profile: str,
    name: str,
) -> None:
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []
    _install_server_spies(monkeypatch, events)

    async def cached_definition_spy(_self, _raw_name):
        events.append("sdk:cache")
        return None

    def sdk_validate_spy(*_args, **_kwargs):
        events.append("sdk:schema")

    monkeypatch.setattr(
        mcp_lowlevel_server.Server,
        "_get_cached_tool_definition",
        cached_definition_spy,
    )
    monkeypatch.setattr(mcp_lowlevel_server.jsonschema, "validate", sdk_validate_spy)
    outer = _OuterTargetMapping(name, events)
    request = SimpleNamespace(
        params=SimpleNamespace(name="rook_tools_call", arguments=outer)
    )
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    before = store.get_containment_denials_snapshot()

    transport = await handler(request)

    assert isinstance(transport, mcp_types.ServerResult), EXPECTED_RED
    result = transport.root
    assert isinstance(result, mcp_types.CallToolResult), EXPECTED_RED
    assert result.isError is False, EXPECTED_RED
    _assert_public_denial(result.content, name)
    _assert_one_denial_event(
        store,
        attempts,
        before,
        name=name,
        origin=DispatchOrigin.PROGRESSIVE_META,
    )
    assert events == [], EXPECTED_RED


@pytest.mark.asyncio
async def test_registered_mcp_handler_delegates_admitted_validation_unchanged(
    monkeypatch,
    tmp_path,
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    monkeypatch.setitem(
        server.mcp._tool_cache,
        "rhino_create",
        mcp_types.Tool(
            name="rhino_create",
            description="test",
            inputSchema={
                "type": "object",
                "required": ["type"],
                "properties": {"type": {"type": "string"}},
            },
        ),
    )
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(
            name="rhino_create",
            arguments={},
        )
    )
    before = store.get_containment_denials_snapshot()

    transport = await handler(request)

    result = transport.root
    assert isinstance(result, mcp_types.CallToolResult)
    assert result.isError is True
    assert len(result.content) == 1
    assert "Input validation error" in result.content[0].text
    assert attempts == []
    assert store.get_containment_denials_snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_name", "arguments", "schema"),
    [
        (
            "spawn_agent ",
            {},
            {
                "type": "object",
                "required": ["required_value"],
                "properties": {"required_value": {"type": "string"}},
            },
        ),
        (
            "unknown_containment_probe",
            {},
            {
                "type": "object",
                "required": ["required_value"],
                "properties": {"required_value": {"type": "string"}},
            },
        ),
        (
            "rook_tools_call",
            {"name": ["spawn_agent"], "arguments": {}},
            {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        ),
    ],
)
async def test_registered_mcp_handler_delegates_non_exact_calls_to_sdk_validation(
    monkeypatch,
    tmp_path,
    raw_name: str,
    arguments: dict[str, object],
    schema: dict[str, object],
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []

    async def cached_definition_spy(_self, name):
        events.append(f"sdk:cache:{name}")
        return mcp_types.Tool(
            name=name,
            description="test",
            inputSchema=schema,
        )

    real_validate = mcp_lowlevel_server.jsonschema.validate

    def sdk_validate_spy(*args, **kwargs):
        events.append("sdk:schema")
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(
        mcp_lowlevel_server.Server,
        "_get_cached_tool_definition",
        cached_definition_spy,
    )
    monkeypatch.setattr(mcp_lowlevel_server.jsonschema, "validate", sdk_validate_spy)
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(
            name=raw_name,
            arguments=arguments,
        )
    )
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    before = store.get_containment_denials_snapshot()

    transport = await handler(request)

    result = transport.root
    assert isinstance(result, mcp_types.CallToolResult)
    assert result.isError is True
    assert len(result.content) == 1
    assert "Input validation error" in result.content[0].text
    assert events == [f"sdk:cache:{raw_name}", "sdk:schema"]
    assert attempts == []
    assert store.get_containment_denials_snapshot() == before


def test_transport_containment_wrapper_installation_is_idempotent() -> None:
    installer_name = "_install_mcp_call_tool_containment_wrapper"
    assert hasattr(server, installer_name), EXPECTED_RED
    installer = getattr(server, installer_name)
    before = server.mcp.request_handlers[mcp_types.CallToolRequest]

    installer()
    once = server.mcp.request_handlers[mcp_types.CallToolRequest]
    installer()
    twice = server.mcp.request_handlers[mcp_types.CallToolRequest]

    assert once is before, EXPECTED_RED
    assert twice is before, EXPECTED_RED


ARBITRARY_INTERNAL_SEAMS = (
    "handle_meta_tool",
    "call_tool_dispatch",
    "mcp_tool_executor",
    "dispatcher_dispatch",
    "dispatcher_inner",
    "dispatcher_local",
    "dispatcher_knowledge",
)
IDENTITY_INTERNAL_SEAMS = {
    "handle_spawn_agent": "spawn_agent",
    "handle_plan_and_execute": "plan_and_execute",
}
INTERNAL_BOUNDARY_CASES = tuple(
    (seam, name)
    for seam in ARBITRARY_INTERNAL_SEAMS
    for name in CONTAINED_NAMES
) + tuple(IDENTITY_INTERNAL_SEAMS.items())


def test_internal_boundary_matrix_keyset_is_complete() -> None:
    expected = {
        (seam, name)
        for seam in ARBITRARY_INTERNAL_SEAMS
        for name in CONTAINED_NAMES
    } | set(IDENTITY_INTERNAL_SEAMS.items())
    assert set(INTERNAL_BOUNDARY_CASES) == expected
    assert len(INTERNAL_BOUNDARY_CASES) == 44


@pytest.mark.asyncio
@pytest.mark.parametrize(("seam", "name"), INTERNAL_BOUNDARY_CASES)
async def test_internal_boundary_denials_are_independent_and_early(
    monkeypatch,
    tmp_path,
    seam: str,
    name: str,
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []
    before = store.get_containment_denials_snapshot()
    dispatcher = ToolDispatcher()

    if seam == "handle_meta_tool":
        async def capability_spy():
            events.append("capability")
            return _FakeCapabilityIndex()

        monkeypatch.setattr(server, "_get_capability_index", capability_spy)
        result = await server._handle_meta_tool(
            "rook_tools_call",
            _OuterTargetMapping(name, events),
            server.Profile.READONLY,
        )
        expected_origin = DispatchOrigin.PROGRESSIVE_META
        _assert_public_denial(result, name)
    elif seam == "call_tool_dispatch":
        result = await server._call_tool_dispatch(
            name,
            _PoisonMapping(events),
        )
        expected_origin = DispatchOrigin.SERVER_DISPATCH
        _assert_internal_denial(result, name)
    elif seam == "mcp_tool_executor":
        result = await server._mcp_tool_executor(
            name,
            _PoisonMapping(events),
        )
        expected_origin = DispatchOrigin.SERVER_DISPATCH
        _assert_internal_denial(result, name)
    elif seam == "handle_spawn_agent":
        _poison_private_handler_imports(monkeypatch, events)
        result = await server._handle_spawn_agent(_PoisonMapping(events))
        expected_origin = DispatchOrigin.INTERNAL_HANDLER
        _assert_internal_denial(result, name)
    elif seam == "handle_plan_and_execute":
        _poison_private_handler_imports(monkeypatch, events)
        result = await server._handle_plan_and_execute(_PoisonMapping(events))
        expected_origin = DispatchOrigin.INTERNAL_HANDLER
        _assert_internal_denial(result, name)
    elif seam == "dispatcher_dispatch":
        result = await dispatcher.dispatch(name, _PoisonMapping(events))
        expected_origin = DispatchOrigin.TOOL_DISPATCHER
        _assert_internal_denial(result, name)
    elif seam == "dispatcher_inner":
        dispatcher._local_tools = _PoisonLocalMapping(events)
        result = await dispatcher._dispatch_inner(
            name,
            _PoisonMapping(events),
            None,
        )
        expected_origin = DispatchOrigin.TOOL_DISPATCHER
        _assert_internal_denial(result, name)
    elif seam == "dispatcher_local":
        dispatcher._local_tools = _PoisonLocalMapping(events)
        result = await dispatcher._call_local(
            name,
            _PoisonMapping(events),
            None,
        )
        expected_origin = DispatchOrigin.TOOL_DISPATCHER
        _assert_internal_denial(result, name)
    elif seam == "dispatcher_knowledge":
        monkeypatch.setattr(
            dispatcher_module,
            "KNOWLEDGE_WRAPPED_TOOLS",
            _PoisonKnowledgeMapping(events),
        )
        result = await dispatcher._dispatch_with_knowledge(
            name,
            _PoisonMapping(events),
            None,
        )
        expected_origin = DispatchOrigin.TOOL_DISPATCHER
        _assert_internal_denial(result, name)
    else:  # pragma: no cover - keyset assertion above pins every seam.
        raise AssertionError(f"{EXPECTED_RED} unknown seam {seam}")

    _assert_one_denial_event(
        store,
        attempts,
        before,
        name=name,
        origin=expected_origin,
    )
    assert events == [], EXPECTED_RED


@pytest.mark.asyncio
async def test_structural_exact_once_keeps_sequential_and_sibling_attempts_distinct(
    monkeypatch,
    tmp_path,
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    dispatcher = ToolDispatcher()

    async def must_not_run(**_kwargs):
        raise AssertionError(f"{EXPECTED_RED} contaminated local handler ran")

    dispatcher._local_tools.update(
        {
            "spawn_agent": must_not_run,
            "gh_replay_recipe": must_not_run,
        }
    )
    before = store.get_containment_denials_snapshot()

    first = await dispatcher.dispatch("spawn_agent", {})
    second = await dispatcher.dispatch("spawn_agent", {})
    sibling = await dispatcher.dispatch("gh_replay_recipe", {})

    _assert_internal_denial(first, "spawn_agent")
    _assert_internal_denial(second, "spawn_agent")
    _assert_internal_denial(sibling, "gh_replay_recipe")
    after = store.get_containment_denials_snapshot()
    assert attempts == [
        ("spawn_agent", "tool_dispatcher"),
        ("spawn_agent", "tool_dispatcher"),
        ("gh_replay_recipe", "tool_dispatcher"),
    ], EXPECTED_RED
    added = _snapshot_delta(before, after)
    assert [event["tool"] for event in added] == [
        "spawn_agent",
        "spawn_agent",
        "gh_replay_recipe",
    ], EXPECTED_RED


@pytest.mark.asyncio
async def test_direct_deeper_dispatcher_call_is_a_new_attempt(
    monkeypatch,
    tmp_path,
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    dispatcher = ToolDispatcher()
    dispatcher._dispatch_inner = AsyncMock(
        return_value={"success": True, "data": "unexpected"}
    )
    before = store.get_containment_denials_snapshot()

    outer = await dispatcher.dispatch("plan_and_execute", {})
    assert dispatcher._dispatch_inner.await_count == 0, EXPECTED_RED

    dispatcher._dispatch_inner = ToolDispatcher._dispatch_inner.__get__(
        dispatcher,
        ToolDispatcher,
    )
    deeper = await dispatcher._dispatch_inner(
        "plan_and_execute",
        {},
        None,
    )

    _assert_internal_denial(outer, "plan_and_execute")
    _assert_internal_denial(deeper, "plan_and_execute")
    assert attempts == [
        ("plan_and_execute", "tool_dispatcher"),
        ("plan_and_execute", "tool_dispatcher"),
    ], EXPECTED_RED
    added = _snapshot_delta(
        before,
        store.get_containment_denials_snapshot(),
    )
    assert len(added) == 2, EXPECTED_RED


@pytest.mark.asyncio
async def test_nested_meta_denial_records_once_without_public_redispatch(
    monkeypatch,
    tmp_path,
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    events: list[str] = []
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    monkeypatch.setattr(
        server,
        "_call_tool_dispatch",
        AsyncMock(side_effect=AssertionError(
            f"{EXPECTED_RED} nested target redispatched"
        )),
    )
    before = store.get_containment_denials_snapshot()

    result = await server.call_tool(
        "rook_tools_call",
        _OuterTargetMapping("gh_execute_intent", events),
    )

    _assert_public_denial(result, "gh_execute_intent")
    assert server._call_tool_dispatch.await_count == 0, EXPECTED_RED
    _assert_one_denial_event(
        store,
        attempts,
        before,
        name="gh_execute_intent",
        origin=DispatchOrigin.PROGRESSIVE_META,
    )
    assert events == [], EXPECTED_RED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_target",
    [
        None,
        1,
        b"spawn_agent",
        "spawn_agent ",
        "Spawn_Agent",
        "spawn_agen",
    ],
)
async def test_progressive_near_matches_keep_existing_behavior_without_telemetry(
    monkeypatch,
    tmp_path,
    raw_target: object,
) -> None:
    store, attempts = _telemetry_probe(monkeypatch, tmp_path)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    before = store.get_containment_denials_snapshot()

    result = await server.call_tool(
        "rook_tools_call",
        {"name": raw_target, "arguments": {}},
    )

    assert len(result) == 1
    assert result[0].text.startswith("Error: ")
    assert "legacy_semantic_tool_contained" not in result[0].text
    assert attempts == []
    assert store.get_containment_denials_snapshot() == before
