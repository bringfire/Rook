import pytest

from rook.agent.chat.tool_contracts import audit_litellm_tool_schema
from rook.agent.tool_registry import ToolRegistry


def _schema_by_name(schemas):
    return {
        schema.get("function", {}).get("name"): schema
        for schema in schemas
    }


def test_active_registry_schemas_are_audited_closed_at_exposure_boundary():
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
    assert schemas["request_tools"]["function"]["parameters"]["additionalProperties"] is False
    assert schemas["search_tools"]["function"]["parameters"]["additionalProperties"] is False


def test_fallback_catalog_gh_canvas_critical_tools_are_closed():
    from rook.agent.chat.chat_runner import _build_fallback_catalog
    from rook.agent.tool_groups import TOOL_GROUPS

    catalog = _build_fallback_catalog()

    critical = {
        "gh_errors",
        "gh_update_script",
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
    }
    for tool_name in critical & set(TOOL_GROUPS["gh_canvas"]):
        params = catalog[tool_name]["function"]["parameters"]
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        assert audit_litellm_tool_schema(catalog[tool_name]) == []


def test_local_catalog_unknown_tools_are_closed_by_default():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"local_experimental": object()})

    params = catalog["local_experimental"]["function"]["parameters"]
    assert params == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


CRITICAL_PARITY_TOOLS = (
    "gh_create_script",
    "gh_create_python_script",
    "gh_create_csharp_script",
    "gh_errors",
    "request_tools",
    "search_tools",
    "gh_update_script",
)


@pytest.mark.parametrize("tool_name", CRITICAL_PARITY_TOOLS)
def test_critical_active_tool_schemas_are_closed_and_named(tool_name):
    from rook.agent.chat.chat_runner import _build_local_tool_catalog
    from rook.agent.tool_registry import ToolRegistry

    local_catalog = _build_local_tool_catalog({
        "gh_create_script": object(),
        "gh_create_python_script": object(),
        "gh_create_csharp_script": object(),
        "gh_update_script": object(),
    })
    if tool_name == "gh_errors":
        from rook.agent.chat.chat_runner import _build_fallback_catalog
        local_catalog.update({"gh_errors": _build_fallback_catalog()["gh_errors"]})

    registry = ToolRegistry(
        catalog=local_catalog,
        tier0=set(CRITICAL_PARITY_TOOLS),
        agent_mode=True,
    )
    schemas = _schema_by_name(registry.get_active_schemas())

    schema = schemas[tool_name]
    assert schema["function"]["name"] == tool_name
    assert schema["function"]["parameters"]["type"] == "object"
    assert schema["function"]["parameters"]["additionalProperties"] is False


def test_strict_no_argument_dispatcher_tools_have_zero_argument_schemas():
    from rook.agent.chat.chat_runner import _build_fallback_catalog
    from rook.agent.tool_dispatcher import STRICT_NO_ARGUMENT_BRIDGE_TOOLS

    catalog = _build_fallback_catalog()

    for tool_name in STRICT_NO_ARGUMENT_BRIDGE_TOOLS:
        assert catalog[tool_name]["function"]["parameters"] == {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }


@pytest.mark.asyncio
async def test_local_gh_create_required_fields_match_server_mcp_contract():
    from rook import server
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    local_catalog = _build_local_tool_catalog({
        "gh_create_script": object(),
        "gh_create_python_script": object(),
        "gh_create_csharp_script": object(),
    })
    server_tools = {tool.name: tool for tool in await server.list_tools()}

    assert (
        local_catalog["gh_create_script"]["function"]["parameters"]["required"]
        == server_tools["gh_create_script"].inputSchema["required"]
        == ["language", "code"]
    )
    for tool_name in ("gh_create_python_script", "gh_create_csharp_script"):
        assert (
            local_catalog[tool_name]["function"]["parameters"]["required"]
            == server_tools[tool_name].inputSchema["required"]
            == ["code", "pins_in", "pins_out"]
        )
