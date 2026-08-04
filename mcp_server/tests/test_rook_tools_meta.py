import asyncio
from unittest.mock import AsyncMock

import pytest

from rook import server


def test_dispatchable_names_include_meta_and_a_known_native():
    names = server._dispatchable_tool_names()
    assert server.META_TOOL_NAMES <= names            # meta-tools unioned in (P1b)
    assert "rhino_objects" in names                    # a known dispatcher case label


def test_dispatchable_names_include_or_case_arms():
    # server.py has: case "rhino_command_knowledge" | "rhino_knowledge_query":
    names = server._dispatchable_tool_names()
    assert "rhino_command_knowledge" in names and "rhino_knowledge_query" in names


def test_capability_index_covers_full_unprofiled_surface(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    idx = asyncio.run(server._get_capability_index())
    live = {t.name for t in asyncio.run(server._all_live_tools())}
    assert {r.name for r in idx.records} == live
    assert idx.by_name["rhino_objects"].mcp_dispatchable is True
    assert "rhino_director_preview_motion" not in idx.by_name


def test_index_survives_lm2a_failure(monkeypatch):
    server._reset_capability_index_cache()  # test hook (Step 3)
    import rook.agent.capability_inventory as inv
    monkeypatch.setattr(inv, "collect_live_sources", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    idx = asyncio.run(server._get_capability_index())
    assert all(r.agent_record is None for r in idx.records)  # tolerated -> agent_records = {}
    server._reset_capability_index_cache()  # don't leak the degraded index to later tests


def test_dispatch_origin_defaults_native_and_is_readable():
    from rook.server import _dispatch_origin
    assert _dispatch_origin.get() == "native"
    tok = _dispatch_origin.set("meta")
    try:
        assert _dispatch_origin.get() == "meta"
    finally:
        _dispatch_origin.reset(tok)


import json


def _text(name, args=None):
    return asyncio.run(server.call_tool(name, args or {}))[0].text


def _stub_dispatch(monkeypatch):
    # requires_rhino=False routes call_tool straight to _call_tool_dispatch (no Rhino/route
    # resolution needed), so the meta re-entry actually reaches the stub.
    from types import SimpleNamespace
    monkeypatch.setattr(server.targeting, "policy_for_tool",
                        lambda name: SimpleNamespace(requires_rhino=False))
    async def ok(name, arguments):
        return {"success": True, "data": {"dispatched": name, "origin": server._dispatch_origin.get()}}
    monkeypatch.setattr(server, "_call_tool_dispatch", ok)


def test_lean_reaches_hidden_tool_via_search_read_call(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    _stub_dispatch(monkeypatch)
    found = json.loads(_text("rook_tools_search", {"query": "gh_status"}))
    assert any(entry["name"] == "gh_status" for entry in found)
    schema = json.loads(_text("rook_tools_read", {"name": "gh_status"}))
    assert "input_schema" in schema
    called = json.loads(
        _text("rook_tools_call", {"name": "gh_status", "arguments": {}})
    )
    assert called == {"dispatched": "gh_status", "origin": "meta"}


def test_readonly_block_wall_before_validation(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    _stub_dispatch(monkeypatch)
    text = _text(
        "rook_tools_call",
        {"name": "rhino_create", "arguments": {"bogus": 1}},
    )
    assert "tool_profile_blocked" in text


def test_recursion_guard(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    assert "error" in _text("rook_tools_call", {"name": "rook_tools_ls"}).lower()


def test_non_dispatchable_refused(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    _stub_dispatch(monkeypatch)
    assert "error" in _text("rook_tools_call", {"name": "definitely_not_a_tool"}).lower()


def test_meta_layer_never_self_records(monkeypatch):
    # Meta tools are intercepted BEFORE _call_tool_dispatch's recording tail, so they must never
    # appear as observations. (Target-under-real-name + origin=meta is covered by test_lean_reach:
    # the stub reads _dispatch_origin at dispatch time; the real recording tail is exercised by a
    # requires_rhino integration run, out of scope for this unit suite.)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    _stub_dispatch(monkeypatch)
    recorded = []
    monkeypatch.setattr(server, "_record_observation", lambda name, *a, **k: recorded.append(name))
    _text("rook_tools_search", {"query": "objects"})
    _text("rook_tools_read", {"name": "rhino_objects"})
    _text("rook_tools_call", {"name": "rhino_objects", "arguments": {}})
    assert "rook_tools_call" not in recorded
    assert "rook_tools_search" not in recorded and "rook_tools_read" not in recorded


def test_meta_dispatch_records_target_once_with_origin_meta(monkeypatch):
    # Real non-Rhino target: rhino_instances -> targeting.instances_result() needs no live Rhino, so the
    # REAL _call_tool_dispatch recording tail runs. Do NOT stub dispatch.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    recorded = []
    monkeypatch.setattr(server, "_record_observation",
                        lambda name, *a, **k: recorded.append((name, server._dispatch_origin.get())))
    _text("rook_tools_call", {"name": "rhino_instances", "arguments": {}})
    assert recorded == [("rhino_instances", "meta")]   # one record, target name, tagged meta


def test_readonly_blocked_meta_call_has_no_side_effects(monkeypatch):
    # Mirror test_blocked_readonly_call_has_no_side_effects for the meta path.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    flags = {"observed": False, "dispatched": False}
    monkeypatch.setattr(server, "_record_observation", lambda *a, **k: flags.__setitem__("observed", True))
    async def _spy(*a, **k): flags["dispatched"] = True; return {"success": True, "data": {}}
    monkeypatch.setattr(server, "_call_tool_dispatch", _spy)
    assert "tool_profile_blocked" in _text("rook_tools_call",
                                           {"name": "rhino_create", "arguments": {}})
    assert flags == {"observed": False, "dispatched": False}


def test_rook_tools_call_rejects_non_object_arguments(monkeypatch):
    # Malformed 'arguments' must return a structured error, not raise (dict("abc") would ValueError).
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    text = _text("rook_tools_call", {"name": "rhino_instances", "arguments": "abc"})
    assert "invalid_arguments" in text


def test_rook_tools_ls_tolerates_malformed_depth(monkeypatch):
    # A non-int depth must fall back to the default, not raise int('nope').
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    out = json.loads(_text("rook_tools_ls", {"path": "/rhino", "depth": "nope"}))
    assert "entries" in out


def test_rook_tools_search_tolerates_malformed_limit(monkeypatch):
    # A non-int limit must fall back to the default, not raise int('nope').
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    found = json.loads(_text("rook_tools_search", {"query": "objects", "limit": "nope"}))
    assert isinstance(found, list)


DG009_GH_TOOL_NAMES = (
    "gh_update_script",
    "gh_set_script_pins",
    "gh_status",
    "gh_create_csharp_script",
    "gh_snapshot",
)


def _lean_tool_descriptions(monkeypatch):
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    return {tool.name: tool.description for tool in asyncio.run(server.list_tools())}


def test_lean_gateway_metadata_contains_dg009_exact_gh_aliases(monkeypatch):
    descriptions = _lean_tool_descriptions(monkeypatch)
    for gateway in ("rook_tools_search", "rook_tools_read", "rook_tools_call"):
        assert gateway in descriptions
        desc = descriptions[gateway]
        for tool_name in DG009_GH_TOOL_NAMES:
            assert tool_name in desc


def test_rook_tools_search_exact_dg009_gh_names_resolve_real_records(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    for tool_name in DG009_GH_TOOL_NAMES:
        found = json.loads(_text("rook_tools_search", {"query": tool_name, "limit": 10}))
        assert any(entry["name"] == tool_name for entry in found), tool_name


def test_rook_tools_read_exact_dg009_gh_names_return_schemas(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    for tool_name in DG009_GH_TOOL_NAMES:
        record = json.loads(_text("rook_tools_read", {"name": tool_name}))
        assert record["name"] == tool_name
        assert record["domain"] == "gh"
        assert record["mcp_dispatchable"] is True
        assert isinstance(record["input_schema"], dict)
        assert record["input_schema"].get("type") == "object"


EXPECTED_GATEWAY_SCHEMA_SHAPES = {
    "rook_tools_ls": {
        "properties": {"path", "depth"},
        "required": [],
    },
    "rook_tools_search": {
        "properties": {"query", "domain", "readonly_safe", "limit"},
        "required": ["query"],
    },
    "rook_tools_read": {
        "properties": {"name"},
        "required": ["name"],
    },
    "rook_tools_call": {
        "properties": {"name", "arguments"},
        "required": ["name"],
    },
}


def _gateway_tool_projection(tool):
    return {
        "description": tool.description,
        "input_schema": tool.inputSchema,
    }


def test_gateway_contract_owns_exact_existing_schema_shapes():
    from rook.mcp_capability_gateway_contract import (
        MCP_CAPABILITY_GATEWAY_NAMES,
        build_mcp_capability_gateway_tools,
    )

    tools = build_mcp_capability_gateway_tools()

    assert MCP_CAPABILITY_GATEWAY_NAMES == frozenset(
        EXPECTED_GATEWAY_SCHEMA_SHAPES
    )
    assert tuple(tool.name for tool in tools) == tuple(
        EXPECTED_GATEWAY_SCHEMA_SHAPES
    )
    for tool in tools:
        expected = EXPECTED_GATEWAY_SCHEMA_SHAPES[tool.name]
        assert isinstance(tool.description, str) and tool.description.strip()
        assert tool.inputSchema["type"] == "object"
        assert set(tool.inputSchema["properties"]) == expected["properties"]
        assert tool.inputSchema["required"] == expected["required"]


def test_live_mcp_surface_uses_shared_gateway_contract():
    from rook.mcp_capability_gateway_contract import (
        build_mcp_capability_gateway_tools,
    )

    expected = {
        tool.name: _gateway_tool_projection(tool)
        for tool in build_mcp_capability_gateway_tools()
    }
    live = {
        tool.name: _gateway_tool_projection(tool)
        for tool in asyncio.run(server._all_live_tools())
        if tool.name in EXPECTED_GATEWAY_SCHEMA_SHAPES
    }

    assert live == expected


def test_gateway_contract_returns_fresh_schema_objects():
    from rook.mcp_capability_gateway_contract import (
        build_mcp_capability_gateway_tools,
    )

    first = build_mcp_capability_gateway_tools()
    first[0].inputSchema["properties"]["path"]["type"] = "integer"
    second = build_mcp_capability_gateway_tools()

    assert second[0].inputSchema["properties"]["path"]["type"] == "string"


@pytest.mark.parametrize(
    ("tool_access", "mcp_profile", "effective"),
    [
        ("readonly", "full", server.Profile.READONLY),
        ("readonly", "lean", server.Profile.READONLY),
        ("readonly", "readonly", server.Profile.READONLY),
        ("full", "full", server.Profile.FULL),
        ("full", "lean", server.Profile.LEAN),
        ("full", "readonly", server.Profile.READONLY),
    ],
)
def test_scope_bound_executor_intersects_authority(
    monkeypatch, tool_access, mcp_profile, effective
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", mcp_profile)
    seen = []

    async def retained_handler(name, arguments, profile):
        seen.append((name, arguments, profile))
        return server._format_tool_result(
            {"success": True, "data": {"effective": profile.value}}
        )

    monkeypatch.setattr(server, "_handle_meta_tool", retained_handler)
    executor = server.build_mcp_capability_gateway_executor(tool_access)
    arguments = {"query": "component", "limit": 7}
    result = asyncio.run(executor("rook_tools_search", arguments))

    assert seen == [("rook_tools_search", arguments, effective)]
    assert seen[0][1] is arguments
    assert result == {"effective": effective.value}


def test_invalid_mcp_profile_fails_before_handler_or_dispatch(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "invalid-profile")
    handler = AsyncMock()
    dispatch = AsyncMock()
    monkeypatch.setattr(server, "_handle_meta_tool", handler)
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)

    executor = server.build_mcp_capability_gateway_executor("full")
    result = asyncio.run(executor("rook_tools_search", {"query": "grid"}))

    assert result["success"] is False
    assert "Invalid ROOK_MCP_TOOL_PROFILE" in result["error"]
    assert handler.await_count == 0
    assert dispatch.await_count == 0


def test_invalid_chatrunner_scope_refuses_at_factory():
    with pytest.raises(ValueError, match="tool_access"):
        server.build_mcp_capability_gateway_executor("lean")


def test_scope_bound_executor_refuses_non_gateway_before_handler(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    handler = AsyncMock()
    monkeypatch.setattr(server, "_handle_meta_tool", handler)

    executor = server.build_mcp_capability_gateway_executor("full")
    result = asyncio.run(executor("gh_library", {}))

    assert result["success"] is False
    assert "Unsupported MCP capability gateway tool" in result["error"]
    assert handler.await_count == 0


@pytest.mark.parametrize(
    ("wire_text", "expected"),
    [
        ('{"value":3}', {"value": 3}),
        ('["a",2]', ["a", 2]),
        ("7", 7),
        ("plain text", {"success": True, "data": "plain text"}),
        (
            'Error: {"code":"blocked"}',
            {"success": False, "data": {"code": "blocked"}},
        ),
        ("Error: plain failure", {"success": False, "data": "plain failure"}),
    ],
)
def test_agent_conversion_is_shared_by_internal_and_gateway_executors(
    monkeypatch, wire_text, expected
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    contents = [server.TextContent(type="text", text=wire_text)]

    async def retained_call_tool(_name, _arguments):
        return contents

    async def retained_handler(_name, _arguments, _profile):
        return contents

    monkeypatch.setattr(server, "call_tool", retained_call_tool)
    monkeypatch.setattr(server, "_handle_meta_tool", retained_handler)

    direct = server._mcp_contents_to_agent_result(contents)
    internal = asyncio.run(server._mcp_tool_executor("rhino_ping", {}))
    gateway = asyncio.run(
        server.build_mcp_capability_gateway_executor("full")(
            "rook_tools_read", {"name": "gh_library"}
        )
    )

    assert direct == expected
    assert internal == expected
    assert gateway == expected


def test_scope_bound_gateway_discovers_reads_and_dispatches_required_gh_tools(
    monkeypatch,
):
    from types import SimpleNamespace

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    dispatched = []

    async def retained_dispatch(name, arguments):
        dispatched.append((name, arguments))
        return {"success": True, "data": {"name": name, "arguments": arguments}}

    monkeypatch.setattr(server, "_call_tool_dispatch", retained_dispatch)
    executor = server.build_mcp_capability_gateway_executor("full")

    for target, target_arguments in (
        ("gh_library", {"search": "Series", "limit": 3}),
        ("gh_batch_component_info", {"names": ["Series", "Range"]}),
    ):
        found = asyncio.run(
            executor("rook_tools_search", {"query": target, "limit": 10})
        )
        assert any(entry["name"] == target for entry in found)
        schema = asyncio.run(executor("rook_tools_read", {"name": target}))
        assert schema["name"] == target
        assert schema["input_schema"]["type"] == "object"

        call_arguments = {"name": target, "arguments": target_arguments}
        result = asyncio.run(executor("rook_tools_call", call_arguments))
        assert result == {"name": target, "arguments": target_arguments}

    assert dispatched == [
        ("gh_library", {"search": "Series", "limit": 3}),
        ("gh_batch_component_info", {"names": ["Series", "Range"]}),
    ]


def test_scope_bound_gateway_retains_canonical_targeting_transformations(
    monkeypatch,
):
    from types import SimpleNamespace

    from rook import bridge

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=True),
    )
    monkeypatch.setattr(
        server.targeting,
        "resolve_tool_route",
        lambda *_args, **_kwargs: SimpleNamespace(
            success=True,
            target=SimpleNamespace(port=9950, process_id=7101),
            document_serial_number=42,
        ),
    )
    monkeypatch.setattr(
        server.targeting,
        "apply_locked_document_context",
        lambda arguments: {**arguments, "documentSerialNumber": 42},
    )
    monkeypatch.setattr(
        server.targeting,
        "attach_route_metadata",
        lambda result, _route: result,
    )
    seen = []

    async def retained_dispatch(name, arguments):
        seen.append((name, arguments, bridge.get_rhino_request_context()))
        return {"success": True, "data": {"targeted": True}}

    monkeypatch.setattr(server, "_call_tool_dispatch", retained_dispatch)
    executor = server.build_mcp_capability_gateway_executor("full")

    result = asyncio.run(
        executor(
            "rook_tools_call",
            {"name": "gh_library", "arguments": {"search": "Point"}},
        )
    )

    assert result == {"targeted": True}
    assert seen == [
        (
            "gh_library",
            {"search": "Point", "documentSerialNumber": 42},
            {"port": 9950, "process_id": 7101, "document_serial_number": 42},
        )
    ]


def test_scope_bound_gateway_records_real_no_contact_target_once(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    recorded = []
    monkeypatch.setattr(
        server,
        "_record_observation",
        lambda name, *_args, **_kwargs: recorded.append(
            (name, server._dispatch_origin.get())
        ),
    )
    executor = server.build_mcp_capability_gateway_executor("full")

    asyncio.run(
        executor(
            "rook_tools_call",
            {"name": "rhino_instances", "arguments": {}},
        )
    )

    assert recorded == [("rhino_instances", "meta")]


@pytest.mark.parametrize(
    ("tool_access", "mcp_profile"),
    [
        ("readonly", "full"),
        ("readonly", "lean"),
        ("readonly", "readonly"),
        ("full", "readonly"),
    ],
)
def test_scope_bound_readonly_discovery_and_call_keep_canonical_wall(
    monkeypatch, tool_access, mcp_profile
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", mcp_profile)
    server._reset_capability_index_cache()
    dispatch = AsyncMock()
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    executor = server.build_mcp_capability_gateway_executor(tool_access)

    found = asyncio.run(
        executor("rook_tools_search", {"query": "rhino_create", "limit": 10})
    )
    refused = asyncio.run(
        executor(
            "rook_tools_call",
            {"name": "rhino_create", "arguments": {"bogus": True}},
        )
    )

    assert not any(entry["name"] == "rhino_create" for entry in found)
    assert refused["success"] is False
    assert refused["data"]["code"] == "tool_profile_blocked"
    assert dispatch.await_count == 0


@pytest.mark.parametrize(
    ("arguments", "error_field", "error_code"),
    [
        ({"name": "rook_tools_ls"}, "error", "meta_recursion_forbidden"),
        ({"name": "spawn_agent"}, "code", "legacy_semantic_tool_contained"),
        ({"name": "definitely_not_a_tool"}, "error", "not_mcp_dispatchable"),
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
def test_scope_bound_gateway_preserves_canonical_refusals(
    monkeypatch, arguments, error_field, error_code
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    dispatch = AsyncMock()
    monkeypatch.setattr(server, "_call_tool_dispatch", dispatch)
    executor = server.build_mcp_capability_gateway_executor("full")

    result = asyncio.run(executor("rook_tools_call", arguments))

    assert result["success"] is False
    assert result["data"][error_field] == error_code
    assert dispatch.await_count == 0


def test_scope_bound_full_with_lean_keeps_advertisement_only_call_behavior(
    monkeypatch,
):
    from types import SimpleNamespace

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    server._reset_capability_index_cache()
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    dispatched = []

    async def retained_dispatch(name, arguments):
        dispatched.append((name, arguments))
        return {"success": True, "data": {"called": name}}

    monkeypatch.setattr(server, "_call_tool_dispatch", retained_dispatch)
    executor = server.build_mcp_capability_gateway_executor("full")

    result = asyncio.run(
        executor(
            "rook_tools_call",
            {"name": "gh_library", "arguments": {"search": "Point"}},
        )
    )

    assert result == {"called": "gh_library"}
    assert dispatched == [("gh_library", {"search": "Point"})]
