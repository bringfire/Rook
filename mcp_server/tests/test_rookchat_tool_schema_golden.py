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


def test_fallback_catalog_rhino_geometry_create_schema_is_actionable():
    from rook.agent.chat.chat_runner import _build_fallback_catalog
    from rook.agent.tool_groups import TOOL_GROUPS

    catalog = _build_fallback_catalog()

    assert "rhino_create" in TOOL_GROUPS["rhino_geometry"]
    params = catalog["rhino_create"]["function"]["parameters"]
    assert params["type"] == "object"
    assert params["required"] == ["type"]
    assert params["additionalProperties"] is False
    assert "type" in params["properties"]
    assert "BOX" in params["properties"]["type"]["description"]
    for box_field in ("origin", "width", "depth", "height", "corner1", "corner2"):
        assert box_field in params["properties"]
    assert audit_litellm_tool_schema(catalog["rhino_create"]) == []


def test_fallback_catalog_rhino_command_schemas_are_actionable():
    from rook.agent.chat.chat_runner import _build_fallback_catalog

    catalog = _build_fallback_catalog()

    command_params = catalog["rhino_command"]["function"]["parameters"]
    assert command_params["type"] == "object"
    assert command_params["required"] == ["command"]
    assert command_params["additionalProperties"] is False
    assert "command" in command_params["properties"]
    assert command_params["properties"]["command"]["pattern"] == "^\\s*_"
    assert audit_litellm_tool_schema(catalog["rhino_command"]) == []


def test_fallback_catalog_rhino_execute_schema_is_actionable():
    from rook.agent.chat.chat_runner import _build_fallback_catalog

    catalog = _build_fallback_catalog()

    params = catalog["rhino_execute"]["function"]["parameters"]
    assert params["type"] == "object"
    assert params["required"] == ["code"]
    assert params["additionalProperties"] is False
    assert params["properties"]["code"]["type"] == "string"
    assert audit_litellm_tool_schema(catalog["rhino_execute"]) == []


def test_local_catalog_rhino_execute_intent_schema_is_actionable():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"rhino_execute_intent": object()})

    intent_params = catalog["rhino_execute_intent"]["function"]["parameters"]
    assert intent_params["type"] == "object"
    assert intent_params["required"] == ["intent"]
    assert intent_params["additionalProperties"] is False
    assert "intent" in intent_params["properties"]
    assert audit_litellm_tool_schema(catalog["rhino_execute_intent"]) == []


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


def _active_schemas_after_requesting_gh_canvas():
    from rook.agent.chat.chat_runner import _build_fallback_catalog, _build_local_tool_catalog
    from rook.agent.tool_dispatcher import build_local_tools
    from rook.agent.tool_registry import ToolRegistry

    catalog = _build_fallback_catalog()
    catalog.update(_build_local_tool_catalog(build_local_tools()))
    registry = ToolRegistry(catalog=catalog, agent_mode=True)
    result = registry.request_group("gh_canvas", turn=1)
    assert result["success"] is True
    return _schema_by_name(registry.get_active_schemas())


def test_model_visible_gh_canvas_schema_has_distinct_script_tools():
    schemas = _active_schemas_after_requesting_gh_canvas()

    for name in ("gh_create_script", "gh_create_python_script", "gh_create_csharp_script"):
        assert schemas[name]["function"]["name"] == name

    assert (
        schemas["gh_create_script"]["function"]["parameters"]["required"]
        == ["language", "code"]
    )
    assert (
        schemas["gh_create_csharp_script"]["function"]["parameters"]["required"]
        == ["code", "pins_in", "pins_out"]
    )


def test_model_visible_gh_canvas_schema_has_no_unallowlisted_open_roots():
    schemas = _active_schemas_after_requesting_gh_canvas()
    findings = []
    for schema in schemas.values():
        findings.extend(audit_litellm_tool_schema(schema))

    assert findings == []


def test_model_visible_gh_canvas_schema_keeps_zero_arg_tools_empty():
    schemas = _active_schemas_after_requesting_gh_canvas()

    assert schemas["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_model_visible_gh_canvas_csharp_creation_guidance_survives_registry_path():
    schemas = _active_schemas_after_requesting_gh_canvas()
    text = str(schemas["gh_create_csharp_script"])

    assert "RhinoCode C# Script" in text
    assert "GH_Component" in text
    assert "body" in text and "RunScript" in text


def _initial_agent_schemas():
    from rook.agent.chat.chat_runner import ChatRunner

    return _schema_by_name(ChatRunner()._registry.get_active_schemas())


def test_initial_agent_schemas_include_csharp_script_creation_affordance():
    schemas = _initial_agent_schemas()

    assert "gh_create_csharp_script" in schemas
    csharp_params = schemas["gh_create_csharp_script"]["function"]["parameters"]
    assert csharp_params["additionalProperties"] is False
    assert csharp_params["required"] == ["code", "pins_in", "pins_out"]


def test_initial_agent_schemas_keep_gh_errors_zero_argument():
    schemas = _initial_agent_schemas()

    assert schemas["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_initial_agent_schemas_include_script_create_update_family():
    schemas = _initial_agent_schemas()

    for tool_name in (
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
        "gh_update_script",
    ):
        assert tool_name in schemas
        assert schemas[tool_name]["function"]["parameters"]["additionalProperties"] is False
