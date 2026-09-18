from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.agent.base_agent import RookAgent  # noqa: E402
from rook.agent.config import AgentConfig  # noqa: E402
from rook.agent.tool_registry import (  # noqa: E402
    ToolRegistry,
    build_catalog_from_mcp_tools,
    load_catalog_from_cache,
    save_catalog_to_cache,
)
from rook.tool_lifecycle import (  # noqa: E402
    CONTAINED_TOOLS,
    ROADCREATOR_TOOL_NAMES,
    ToolDisposition,
    resolve_contained_tool,
)


CONTAINED = {entry.name for entry in CONTAINED_TOOLS}
NATIVE_INTERSECTION_TOOLS = (
    "road_intersection_candidates",
    "road_intersection_resolve",
)


@pytest.mark.asyncio
async def test_raw_schema_inventory_equals_pinned_roadcreator_names() -> None:
    from rook import server

    raw_names = {
        tool.name
        for tool in await server._all_tool_schemas()
        if tool.name.startswith("rc_")
    }
    registered = {
        entry.name: entry
        for entry in CONTAINED_TOOLS
        if entry.name.startswith("rc_")
    }
    assert raw_names == ROADCREATOR_TOOL_NAMES == set(registered)
    assert len(raw_names) == 40
    assert all(
        entry.disposition is ToolDisposition.SUSPENDED
        for entry in registered.values()
    )


@pytest.mark.asyncio
async def test_future_rc_namespace_is_hidden_by_central_live_filter(monkeypatch) -> None:
    from rook import server

    async def raw_tools():
        return [
            server.Tool(name="safe_probe", description="safe", inputSchema={}),
            server.Tool(name="rc_future_probe", description="contained", inputSchema={}),
        ]

    monkeypatch.setattr(server, "_all_tool_schemas", raw_tools)
    assert [tool.name for tool in await server._all_live_tools()] == ["safe_probe"]

    entry = resolve_contained_tool("rc_future_probe")
    assert entry is not None
    assert entry.name == "rc_future_probe"
    assert entry.disposition is ToolDisposition.SUSPENDED
    assert "explicit lifecycle entry" in entry.recovery


def _assert_no_contained_text(value: object) -> None:
    rendered = json.dumps(value, default=str, sort_keys=True)
    assert not {name for name in CONTAINED if name in rendered}


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"schema for {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _schema_names(schemas: list[dict]) -> set[str]:
    return {schema["function"]["name"] for schema in schemas}


@pytest.mark.asyncio
async def test_public_unprofiled_surface_physically_omits_contained_tools() -> None:
    from rook import server

    names = {tool.name for tool in await server._all_live_tools()}
    assert CONTAINED.isdisjoint(names)
    assert {"gh_snapshot", "gh_edit", "rhino_execute"}.issubset(names)


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["full", "lean", "readonly"])
async def test_model_visible_tool_text_omits_contained_identities(monkeypatch, profile: str) -> None:
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    tools = await server.list_tools()
    _assert_no_contained_text([
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema,
        }
        for tool in tools
    ])


@pytest.mark.asyncio
async def test_progressive_tool_read_omits_contained_identities(monkeypatch) -> None:
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    index = await server._get_capability_index()
    _assert_no_contained_text([
        index.read(record.name)
        for record in index.records
        if record.mcp_dispatchable
    ])
    result = await server.call_tool("rook_tools_read", {"name": "gh_session_history"})
    _assert_no_contained_text(json.loads(result[0].text))


@pytest.mark.asyncio
async def test_native_intersection_tools_remain_readable_and_mcp_dispatchable() -> None:
    from rook import server

    server._reset_capability_index_cache()
    index = await server._get_capability_index()
    for name in NATIVE_INTERSECTION_TOOLS:
        record = index.read(name)
        assert record is not None
        assert record["name"] == name
        assert record["mcp_dispatchable"] is True


def test_catalog_ingresses_filter_mapping_and_embedded_identities(tmp_path: Path) -> None:
    dirty = {
        "safe_tool": _schema("safe_tool"),
        "spawn_agent": _schema("safe_embedded"),
        "masked_tool": _schema("gh_replay_recipe"),
    }

    registry = ToolRegistry(catalog=dirty, tier0=set(dirty))
    assert set(registry._catalog) == {"safe_tool"}
    assert _schema_names(registry.get_active_schemas()) == {"safe_tool"}

    registry.register_local_catalog({
        "safe_local": _schema("safe_local"),
        "gh_execute_intent": _schema("safe_alias"),
        "masked_local": _schema("plan_and_execute"),
    })
    assert set(registry._catalog) == {"safe_tool", "safe_local"}

    cache = tmp_path / "catalog.json"
    save_catalog_to_cache(dirty, cache)
    assert set(json.loads(cache.read_text(encoding="utf-8"))) == {"safe_tool"}
    assert set(load_catalog_from_cache(cache) or {}) == {"safe_tool"}


def test_fresh_mcp_catalog_filters_contained_names() -> None:
    tools = [
        SimpleNamespace(name="safe_tool", description="safe", inputSchema={}),
        SimpleNamespace(name="rhino_execute_intent", description="contained", inputSchema={}),
    ]
    assert set(build_catalog_from_mcp_tools(tools)) == {"safe_tool"}


@pytest.mark.asyncio
async def test_internal_agent_projection_filters_injected_schemas() -> None:
    async def executor(_name: str, _arguments: dict) -> dict:
        return {"success": True}

    injected = [_schema("gh_edit"), _schema("gh_execute_intent")]
    agent = RookAgent(
        config=AgentConfig(knowledge_injection=False),
        tool_executor=executor,
        tool_schemas=injected,
    )
    assert _schema_names(agent._get_tool_schemas()) == {"gh_edit"}
    agent.set_tool_schemas([_schema("rhino_execute"), _schema("spawn_agent")])
    assert _schema_names(agent._get_tool_schemas()) == {"rhino_execute"}

def _strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        result: set[str] = set()
        for key, item in value.items():
            result.update(_strings(key))
            result.update(_strings(item))
        return result
    if isinstance(value, (set, frozenset, list, tuple)):
        result: set[str] = set()
        for item in value:
            result.update(_strings(item))
        return result
    return set()


def test_profiles_groups_and_targeting_have_no_contained_memberships() -> None:
    from rook import mcp_tool_profiles, targeting
    from rook.agent import tool_groups

    for module in (mcp_tool_profiles, targeting, tool_groups):
        active_strings: set[str] = set()
        for name, value in vars(module).items():
            if name.isupper():
                active_strings.update(_strings(value))
        assert CONTAINED.isdisjoint(active_strings), module.__name__
        assert not {value for value in active_strings if value.startswith("rc_")}, module.__name__
