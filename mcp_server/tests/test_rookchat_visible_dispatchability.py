from __future__ import annotations

import pytest

from rook.agent.capability_inventory import INTERNAL_AGENT_META_TOOLS
from rook.agent.chat.tool_contracts import (
    DispatchContext,
    audit_visible_tool_dispatchability,
    normalize_litellm_tool_schema,
)
from rook.agent.tool_registry import mcp_tool_to_litellm
from rook.mcp_capability_gateway_contract import build_mcp_capability_gateway_tools


REMOVED_CHAT_PSEUDO_TOOLS = {"ui_block", "list_chat_models", "set_chat_model"}


def _stub_schema(name: str) -> dict:
    return normalize_litellm_tool_schema(
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"Synthetic schema for {name}",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    )


def test_dispatchability_audit_reports_malformed_duplicate_and_missing_paths() -> None:
    context = DispatchContext(
        intercepted_names=frozenset(),
        local_tool_names=frozenset({"local_ok"}),
        transform_names=frozenset(),
        bridge_names=frozenset(),
        excluded_names=frozenset(),
        strict_no_argument_names=frozenset({"strict_zero"}),
    )
    schemas = [
        {"type": "function", "function": {"description": "Missing name", "parameters": {}}},
        _stub_schema("local_ok"),
        _stub_schema("local_ok"),
        _stub_schema("missing_tool"),
        {
            "type": "function",
            "function": {
                "name": "strict_zero",
                "description": "Drifted no-argument tool",
                "parameters": {
                    "type": "object",
                    "properties": {"unexpected": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        },
    ]

    findings = audit_visible_tool_dispatchability(schemas, context)

    assert {finding.code for finding in findings} == {
        "missing_function_name",
        "duplicate_visible_name",
        "not_dispatchable",
        "strict_no_arg_schema_drift",
    }


def test_gateway_schemas_use_owner_neutral_internal_agent_intercepts() -> None:
    schemas = [mcp_tool_to_litellm(tool) for tool in build_mcp_capability_gateway_tools()]
    context = DispatchContext(
        intercepted_names=INTERNAL_AGENT_META_TOOLS,
        local_tool_names=frozenset(),
        transform_names=frozenset(),
        bridge_names=frozenset(),
        excluded_names=frozenset(),
        strict_no_argument_names=frozenset(),
    )

    assert audit_visible_tool_dispatchability(schemas, context) == []


@pytest.mark.asyncio
async def test_full_acp_mcp_surface_has_gateway_and_no_chat_pseudo_tools(monkeypatch) -> None:
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    names = {tool.name for tool in await server.list_tools()}

    assert {"rook_tools_search", "rook_tools_read", "rook_tools_call"} <= names
    assert {"gh_edit", "rhino_execute"} <= names
    assert REMOVED_CHAT_PSEUDO_TOOLS.isdisjoint(names)


@pytest.mark.asyncio
async def test_readonly_acp_mcp_surface_preserves_gateway_and_profile_wall(monkeypatch) -> None:
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    names = {tool.name for tool in await server.list_tools()}

    assert {"rook_tools_search", "rook_tools_read", "rook_tools_call"} <= names
    assert "gh_snapshot" in names
    assert "gh_edit" not in names
    assert REMOVED_CHAT_PSEUDO_TOOLS.isdisjoint(names)
