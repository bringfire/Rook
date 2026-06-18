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
