import pytest


def test_closed_no_arg_schema_shape():
    from rook.agent.chat.tool_contracts import closed_no_arg_parameters

    schema = closed_no_arg_parameters()

    assert schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_normalize_function_schema_closes_missing_parameters():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "gh_errors",
            "description": "Get errors and warnings from Grasshopper",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    assert normalized["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    assert schema["function"]["parameters"].get("additionalProperties") is None


def test_zero_argument_tool_override_rejects_open_schema():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "gh_errors",
            "description": "Get errors and warnings from Grasshopper",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "additionalProperties": True,
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    params = normalized["function"]["parameters"]
    assert params["properties"] == {}
    assert params["additionalProperties"] is False
    assert "Takes no arguments" in normalized["function"]["description"]


def test_explicit_dynamic_allowlist_preserves_open_map():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "ui_block",
            "description": "Present UI",
            "parameters": {
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "Shape varies by block_type",
                        "additionalProperties": True,
                    }
                },
                "required": ["config"],
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    params = normalized["function"]["parameters"]
    assert params["additionalProperties"] is False
    assert params["properties"]["config"]["additionalProperties"] is True


def test_normalize_closes_unallowlisted_nested_objects_recursively():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_nested_tool",
            "description": "Nested object sample",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "object",
                        "properties": {
                            "inner": {
                                "type": "object",
                                "properties": {},
                            }
                        },
                    }
                },
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)

    payload = normalized["function"]["parameters"]["properties"]["payload"]
    inner = payload["properties"]["inner"]
    assert normalized["function"]["parameters"]["additionalProperties"] is False
    assert payload["additionalProperties"] is False
    assert inner["additionalProperties"] is False


def test_normalize_closes_array_item_object_schemas():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_array_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                            },
                        },
                    }
                },
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)
    item_schema = normalized["function"]["parameters"]["properties"]["rows"]["items"]

    assert item_schema["additionalProperties"] is False


def test_normalize_closes_composition_object_schemas():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_union_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {"id": {"type": "string"}},
                            },
                        ],
                    },
                    "scope": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {"layer": {"type": "string"}},
                                "additionalProperties": True,
                            }
                        ],
                    },
                    "options": {
                        "allOf": [
                            {
                                "type": "object",
                                "properties": {"hidden": {"type": "boolean"}},
                            }
                        ],
                    },
                },
            },
        },
    }

    normalized = normalize_litellm_tool_schema(schema)
    target_object = (
        normalized["function"]["parameters"]["properties"]["target"]["oneOf"][1]
    )
    scope_object = normalized["function"]["parameters"]["properties"]["scope"]["anyOf"][0]
    options_object = (
        normalized["function"]["parameters"]["properties"]["options"]["allOf"][0]
    )

    assert target_object["additionalProperties"] is False
    assert scope_object["additionalProperties"] is False
    assert options_object["additionalProperties"] is False


def test_zero_argument_policy_matches_dispatcher_strict_set():
    from rook.agent.chat.tool_contracts import ZERO_ARGUMENT_TOOLS
    from rook.agent.tool_dispatcher import STRICT_NO_ARGUMENT_BRIDGE_TOOLS

    assert ZERO_ARGUMENT_TOOLS == STRICT_NO_ARGUMENT_BRIDGE_TOOLS


def test_audit_reports_open_root_parameter_objects():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "legacy_open_tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_root_parameters",
            "tool": "legacy_open_tool",
            "path": "function.parameters.additionalProperties",
            "message": "Root tool parameters allow arbitrary keys.",
        }
    ]


def test_audit_reports_omitted_root_additional_properties_as_open():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "legacy_implicit_open_tool",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_root_parameters",
            "tool": "legacy_implicit_open_tool",
            "path": "function.parameters.additionalProperties",
            "message": "Root tool parameters allow arbitrary keys.",
        }
    ]


def test_audit_reports_unallowlisted_nested_open_objects():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_nested_open_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "payload": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_nested_object",
            "tool": "sample_nested_open_tool",
            "path": "function.parameters.properties.payload.additionalProperties",
            "message": "Nested object allows arbitrary keys without an explicit allowlist entry.",
        }
    ]


def test_audit_reports_open_array_item_object_schemas():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_array_open_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {},
                        },
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_nested_object",
            "tool": "sample_array_open_tool",
            "path": "function.parameters.properties.rows.items.additionalProperties",
            "message": "Nested object allows arbitrary keys without an explicit allowlist entry.",
        }
    ]


def test_audit_reports_open_composition_object_schemas():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_union_open_tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "oneOf": [
                            {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": True,
                            }
                        ],
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    findings = audit_litellm_tool_schema(schema)

    assert findings == [
        {
            "code": "open_nested_object",
            "tool": "sample_union_open_tool",
            "path": "function.parameters.properties.target.oneOf.0.additionalProperties",
            "message": "Nested object allows arbitrary keys without an explicit allowlist entry.",
        }
    ]


def test_audit_allows_named_dynamic_nested_object_maps():
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "ui_block",
            "parameters": {
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    }
                },
                "additionalProperties": False,
            },
        },
    }

    assert audit_litellm_tool_schema(schema) == []


def test_audit_accepts_closed_script_creation_schema():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema

    schema = _build_local_tool_catalog({"gh_create_csharp_script": object()})[
        "gh_create_csharp_script"
    ]

    assert audit_litellm_tool_schema(schema) == []


def test_mcp_tool_to_litellm_closes_root_parameters_when_server_omits_flag():
    from types import SimpleNamespace

    from rook.agent.tool_registry import mcp_tool_to_litellm

    tool = SimpleNamespace(
        name="sample_tool",
        description="Sample tool",
        inputSchema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    )

    schema = mcp_tool_to_litellm(tool)

    assert schema["function"]["parameters"]["additionalProperties"] is False


def test_load_catalog_from_cache_normalizes_zero_arg_schema(tmp_path):
    import json

    from rook.agent.tool_registry import load_catalog_from_cache

    cache = tmp_path / "agent_tool_catalog.json"
    cache.write_text(
        json.dumps({
            "gh_errors": {
                "type": "function",
                "function": {
                    "name": "gh_errors",
                    "description": "Get errors and warnings from Grasshopper",
                    "parameters": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "additionalProperties": True,
                    },
                },
            }
        }),
        encoding="utf-8",
    )

    catalog = load_catalog_from_cache(cache)

    assert catalog["gh_errors"]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_meta_tool_schemas_are_closed():
    from rook.agent.tool_registry import ToolRegistry

    registry = ToolRegistry(catalog={})
    schemas = {
        schema["function"]["name"]: schema
        for schema in registry.get_active_schemas()
    }

    for name in ("request_tools", "search_tools"):
        params = schemas[name]["function"]["parameters"]
        assert params["additionalProperties"] is False
