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


def test_normalize_closes_dynamic_map_without_an_explicit_allowlist():
    from rook.agent.chat.tool_contracts import normalize_litellm_tool_schema

    schema = {
        "type": "function",
        "function": {
            "name": "sample_dynamic_map",
            "description": "Dynamic map sample",
            "parameters": {
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "Shape varies by discriminator",
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
    assert params["properties"]["config"]["additionalProperties"] is False


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


def test_no_dynamic_schema_exception_remains():
    from rook.agent.chat.tool_contracts import DYNAMIC_NESTED_OBJECT_ALLOWLIST

    assert DYNAMIC_NESTED_OBJECT_ALLOWLIST == {}


@pytest.mark.asyncio
async def test_audit_accepts_public_mcp_script_creation_schema(monkeypatch):
    from rook import server
    from rook.agent.chat.tool_contracts import audit_litellm_tool_schema
    from rook.agent.tool_registry import mcp_tool_to_litellm

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    schema = mcp_tool_to_litellm(
        next(tool for tool in await server.list_tools() if tool.name == "gh_create_csharp_script")
    )

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


def test_normalize_tool_result_top_level_truth_precedence():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    top_failure = normalize_tool_result({
        "success": False,
        "data": {"success": True},
    })
    assert top_failure.status == "failed"

    top_success = normalize_tool_result({
        "success": True,
        "data": {"success": False, "error": "nested error"},
    })
    assert top_success.status == "success"
    assert top_success.error == "nested error"

    top_ok = normalize_tool_result({
        "ok": True,
        "data": {"ok": False},
    })
    assert top_ok.status == "success"


def test_normalize_tool_result_ignores_script_receipt_for_top_level_truth():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    view = normalize_tool_result({
        "success": False,
        "message": "Component was created, but the target script component has compile errors.",
        "data": {
            "component_guid": "created-guid",
            "script_receipt": {
                "version": 1,
                "artifact_status": "created_with_errors",
            },
        },
    })

    assert view.status == "failed"
    assert view.message == "Component was created, but the target script component has compile errors."


def test_tool_result_view_marks_csharp_preflight_failure_failed():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    view = normalize_tool_result({
        "success": False,
        "data": "C# script preflight failed: C# body-style code cannot contain top-level using directives.",
    })

    assert view.status == "failed"


def test_normalize_tool_result_nested_truth_and_error_fallbacks():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    nested_success = normalize_tool_result({"data": {"ok": True}})
    assert nested_success.status == "success"

    top_error = normalize_tool_result({"error": "bad input"})
    assert top_error.status == "failed"
    assert top_error.error == "bad input"

    nested_error = normalize_tool_result({"data": {"error": "nested bad input"}})
    assert nested_error.status == "failed"
    assert nested_error.error == "nested bad input"

    non_string_error = normalize_tool_result({"error": {"code": "bad_input"}})
    assert non_string_error.status == "failed"
    assert non_string_error.error is None


def test_normalize_tool_result_ignores_status_strings_and_truth_like_values():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    status_only = normalize_tool_result({"status": "loaded"})
    assert status_only.status is None

    string_truth_with_error = normalize_tool_result({
        "success": "false",
        "error": "bad",
    })
    assert string_truth_with_error.status == "failed"
    assert string_truth_with_error.error == "bad"

    integer_truth_values = normalize_tool_result({
        "success": 1,
        "data": {"ok": 0},
    })
    assert integer_truth_values.status is None


def test_normalize_tool_result_non_dict_returns_empty_view():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    view = normalize_tool_result("plain text result")

    assert view.status is None
    assert view.verified is None
    assert view.verification_note is None
    assert view.message is None
    assert view.error is None


def test_normalize_tool_result_does_not_mutate_input_dict():
    from copy import deepcopy

    from rook.agent.chat.tool_contracts import normalize_tool_result

    raw = {
        "success": True,
        "message": "top message",
        "data": {
            "success": False,
            "verified": False,
            "message": "nested message",
        },
    }
    original = deepcopy(raw)

    view = normalize_tool_result(raw)

    assert view.status == "success"
    assert view.verified is False
    assert raw == original


def test_normalize_tool_result_message_and_error_extraction_are_string_only():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    top_strings = normalize_tool_result({
        "message": "top message",
        "error": "top error",
        "data": {
            "message": "nested message",
            "error": "nested error",
        },
    })
    assert top_strings.message == "top message"
    assert top_strings.error == "top error"

    nested_strings = normalize_tool_result({
        "message": {"text": "not a string"},
        "error": ["not", "a", "string"],
        "data": {
            "message": "nested message",
            "error": "nested error",
        },
    })
    assert nested_strings.status == "failed"
    assert nested_strings.message == "nested message"
    assert nested_strings.error == "nested error"


def test_normalize_tool_result_verification_precedence_and_fallback():
    from rook.agent.chat.tool_contracts import normalize_tool_result

    top_verification = normalize_tool_result({
        "verified": True,
        "verification_note": "top note",
        "data": {
            "verified": False,
            "verification_note": "nested note",
            "message": "nested message",
        },
    })
    assert top_verification.verified is True
    assert top_verification.verification_note == "top note"

    nested_fallback = normalize_tool_result({
        "data": {
            "verified": False,
            "message": "No active Grasshopper canvas",
        },
    })
    assert nested_fallback.verified is False
    assert nested_fallback.verification_note == "No active Grasshopper canvas"

    top_message_is_not_verification_note = normalize_tool_result({
        "verified": False,
        "message": "This is an ordinary message",
    })
    assert top_message_is_not_verification_note.verified is False
    assert top_message_is_not_verification_note.verification_note is None

    non_string_top_note_falls_back_to_nested_note = normalize_tool_result({
        "verified": False,
        "verification_note": {"text": "not a string"},
        "data": {"verification_note": "nested note"},
    })
    assert non_string_top_note_falls_back_to_nested_note.verification_note == "nested note"
