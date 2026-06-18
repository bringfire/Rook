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
