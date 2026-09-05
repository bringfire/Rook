from __future__ import annotations

import pytest

from rook.agent.chat.tool_contracts import audit_litellm_tool_schema
from rook.agent.tool_registry import ToolRegistry, mcp_tool_to_litellm


def _schema_by_name(schemas: list[dict]) -> dict[str, dict]:
    return {schema.get("function", {}).get("name"): schema for schema in schemas}


async def _public_schemas(monkeypatch, profile: str = "full") -> dict[str, dict]:
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    return _schema_by_name([mcp_tool_to_litellm(tool) for tool in await server.list_tools()])


def test_active_registry_schemas_are_audited_closed_at_exposure_boundary() -> None:
    registry = ToolRegistry(
        catalog={
            "gh_errors": {
                "type": "function",
                "function": {
                    "name": "gh_errors",
                    "description": "Get errors",
                    "parameters": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "additionalProperties": True,
                    },
                },
            }
        },
        tier0={"gh_errors", "request_tools", "search_tools"},
        agent_mode=True,
    )

    schemas = _schema_by_name(registry.get_active_schemas())

    assert schemas["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert audit_litellm_tool_schema(schemas["gh_errors"]) == []


@pytest.mark.asyncio
async def test_full_acp_surface_has_closed_critical_authoring_schemas(monkeypatch) -> None:
    schemas = await _public_schemas(monkeypatch)
    critical = {
        "gh_errors",
        "gh_update_script",
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
        "rhino_create",
        "rhino_command",
        "rhino_execute",
        "rook_tools_search",
        "rook_tools_read",
        "rook_tools_call",
    }

    assert critical <= set(schemas)
    for name in critical:
        parameters = schemas[name]["function"]["parameters"]
        assert parameters["type"] == "object"
        assert parameters["additionalProperties"] is False
        assert audit_litellm_tool_schema(schemas[name]) == []


@pytest.mark.asyncio
async def test_full_acp_rhino_authoring_schemas_are_actionable(monkeypatch) -> None:
    schemas = await _public_schemas(monkeypatch)

    create = schemas["rhino_create"]["function"]["parameters"]
    assert create["required"] == ["type"]
    assert "BOX" in create["properties"]["type"]["description"]
    for field in ("origin", "width", "depth", "height", "corner1", "corner2"):
        assert field in create["properties"]

    command = schemas["rhino_command"]["function"]["parameters"]
    assert command["required"] == ["command"]
    assert command["properties"]["command"]["pattern"] == "^\\s*_"

    execute = schemas["rhino_execute"]["function"]["parameters"]
    assert execute["required"] == ["code"]
    assert execute["properties"]["code"]["type"] == "string"


@pytest.mark.asyncio
async def test_full_acp_script_family_matches_public_contract(monkeypatch) -> None:
    schemas = await _public_schemas(monkeypatch)

    assert schemas["gh_create_script"]["function"]["parameters"]["required"] == [
        "language",
        "code",
    ]
    for name in ("gh_create_python_script", "gh_create_csharp_script"):
        assert schemas[name]["function"]["parameters"]["required"] == [
            "code",
            "pins_in",
            "pins_out",
        ]

    csharp_text = str(schemas["gh_create_csharp_script"])
    assert "RhinoCode C# Script" in csharp_text
    assert "gh_create_script" in csharp_text


@pytest.mark.asyncio
async def test_strict_no_argument_tools_expose_closed_empty_schemas(monkeypatch) -> None:
    from rook.agent.tool_dispatcher import STRICT_NO_ARGUMENT_BRIDGE_TOOLS

    schemas = await _public_schemas(monkeypatch)
    for name in STRICT_NO_ARGUMENT_BRIDGE_TOOLS & set(schemas):
        assert schemas[name]["function"]["parameters"] == {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }


@pytest.mark.asyncio
async def test_acp_profiles_omit_retired_chat_and_contained_tools(monkeypatch) -> None:
    from rook.tool_lifecycle import CONTAINED_TOOLS

    full = await _public_schemas(monkeypatch, "full")
    readonly = await _public_schemas(monkeypatch, "readonly")
    forbidden = {entry.name for entry in CONTAINED_TOOLS} | {
        "ui_block",
        "list_chat_models",
        "set_chat_model",
    }

    assert forbidden.isdisjoint(full)
    assert forbidden.isdisjoint(readonly)
    assert "gh_edit" in full
    assert "gh_edit" not in readonly
    assert "gh_errors" in readonly
