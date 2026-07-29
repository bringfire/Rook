"""MCP-layer tests for the RookBIM Phase 1 tool surface."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import context, server, targeting
from rook.agent import tool_dispatcher, tool_groups


ROOKBIM_TOOL_ROUTES = {
    "rookbim_status": ("/bim/status", "GET"),
    "rookbim_active_document": ("/bim/active-document", "GET"),
    "rookbim_list_categories": ("/bim/categories", "GET"),
    "rookbim_query_elements": ("/bim/query-elements", "POST"),
    "rookbim_element_info": ("/bim/element-info", "POST"),
    "rookbim_element_parameters": ("/bim/element-parameters", "POST"),
    "rookbim_select_elements": ("/bim/select-elements", "POST"),
    "rookbim_clear_selection": ("/bim/clear-selection", "POST"),
    "rookbim_export_elements": ("/bim/export-elements", "POST"),
    "rookbim_export_preset": ("/bim/export-preset", "POST"),
}

ROOKBIM_READONLY_TOOLS = [
    "rookbim_status",
    "rookbim_active_document",
    "rookbim_list_categories",
    "rookbim_query_elements",
    "rookbim_element_info",
    "rookbim_element_parameters",
]

IDENTITY_FIELDS = {
    "source",
    "documentKey",
    "documentKeySource",
    "documentGuid",
    "documentGuidSource",
    "documentTitle",
    "documentPath",
    "elementId",
    "uniqueId",
    "fullUniqueId",
    "linked",
    "linkInstanceId",
    "linkInstanceUniqueId",
    "linkedDocumentGuid",
    "linkedElementId",
    "linkedElementUniqueId",
    "resolved",
    "confidence",
}

PORT_SCHEMA = {"type": "integer", "description": "Specific Rhino port to target."}


@pytest.fixture(autouse=True)
def fake_rhino_discovery(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])


async def _tools_by_name():
    tools = await server.list_tools()
    return {tool.name: tool for tool in tools}


def _normalize_call_rhino_args(call_args) -> tuple:
    args = list(call_args.args)
    kwargs = dict(call_args.kwargs)
    endpoint = args[0]
    method = args[1] if len(args) >= 2 else kwargs.get("method", "GET")
    data = args[2] if len(args) >= 3 else kwargs.get("data", None)
    port = args[3] if len(args) >= 4 else kwargs.get("port", None)
    return (endpoint, method, data, port)


@pytest.mark.asyncio
async def test_all_rookbim_tools_registered():
    tools = await _tools_by_name()

    for name in ROOKBIM_TOOL_ROUTES:
        assert name in tools


@pytest.mark.asyncio
async def test_rookbim_status_active_document_and_clear_selection_have_port_only_closed_schemas():
    tools = await _tools_by_name()

    for name in ("rookbim_status", "rookbim_active_document", "rookbim_list_categories", "rookbim_clear_selection"):
        assert tools[name].inputSchema == {
            "type": "object",
            "properties": {"port": PORT_SCHEMA},
            "required": [],
            "additionalProperties": False,
        }


@pytest.mark.asyncio
async def test_rookbim_query_elements_schema_matches_phase1_contract():
    schema = (await _tools_by_name())["rookbim_query_elements"].inputSchema

    assert schema["type"] == "object"
    assert schema["required"] == []
    assert schema["additionalProperties"] is False
    assert schema["properties"]["port"] == PORT_SCHEMA
    assert schema["properties"]["scope"] == {
        "type": "string",
        "enum": ["active_view", "document"],
        "default": "active_view",
    }
    assert schema["properties"]["category"]["type"] == "string"
    assert schema["properties"]["limit"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 1000,
        "default": 100,
    }

    filters = schema["properties"]["filters"]
    assert filters["type"] == "array"
    assert filters["default"] == []
    item = filters["items"]
    assert item["type"] == "object"
    assert item["required"] == ["parameter", "operation"]
    assert item["additionalProperties"] is False
    assert item["properties"]["parameter"]["type"] == "string"
    assert item["properties"]["operation"] == {
        "type": "string",
        "enum": ["equals", "not_equals", "contains", "is_empty", "is_not_empty"],
    }
    assert item["properties"]["value"]["type"] == "string"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["rookbim_element_info", "rookbim_element_parameters"])
async def test_rookbim_identity_tool_schema_matches_phase1_contract(name):
    schema = (await _tools_by_name())[name].inputSchema

    assert schema["type"] == "object"
    assert schema["required"] == ["identity"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["port"] == PORT_SCHEMA

    identity = schema["properties"]["identity"]
    assert identity["type"] == "object"
    assert set(identity["properties"]) == IDENTITY_FIELDS
    assert "port" not in identity["properties"]
    assert "documentGuidSource" in identity["required"]
    assert identity["additionalProperties"] is False
    assert identity["properties"]["source"] == {"const": "revit"}
    assert identity["properties"]["documentKey"] == {"type": ["string", "null"]}
    assert identity["properties"]["documentKeySource"] == {
        "type": "string",
        "enum": [
            "revit_creation_guid_central_path_v1",
            "revit_creation_guid_document_path_v1",
            "unavailable",
        ],
    }
    assert "documentKey" not in identity["required"]
    assert "documentKeySource" not in identity["required"]
    assert identity["required"] == ["documentGuidSource"]
    assert "pattern" not in identity["properties"]["documentKey"]
    assert identity["properties"]["documentGuid"]["type"] == ["string", "null"]
    assert identity["properties"]["documentGuidSource"] == {
        "type": "string",
        "enum": ["revit_persistent_guid", "path_fallback", "unavailable"],
    }
    assert identity["properties"]["documentPath"]["type"] == ["string", "null"]
    assert identity["properties"]["elementId"]["type"] == ["integer", "null"]
    assert identity["properties"]["linked"]["type"] == "boolean"
    assert identity["properties"]["confidence"] == {
        "type": "string",
        "enum": ["exact", "inferred", "unresolved", "unsupported"],
    }


@pytest.mark.asyncio
async def test_rookbim_select_elements_schema_matches_phase1_contract():
    schema = (await _tools_by_name())["rookbim_select_elements"].inputSchema

    assert schema["type"] == "object"
    assert schema["required"] == ["identities"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["port"] == PORT_SCHEMA
    identities = schema["properties"]["identities"]
    assert identities["type"] == "array"
    assert identities["minItems"] == 1
    assert identities["maxItems"] == 1000
    assert identities["items"]["type"] == "object"
    assert identities["items"]["additionalProperties"] is False
    assert set(identities["items"]["properties"]) == IDENTITY_FIELDS
    assert "port" not in identities["items"]["properties"]


@pytest.mark.parametrize("name", ROOKBIM_READONLY_TOOLS)
def test_rookbim_readonly_tools_have_rhino_read_targeting_policies(name):
    policy = targeting.policy_for_tool(name)

    assert policy.requires_rhino is True
    assert policy.risk == "read"


@pytest.mark.parametrize("name", ["rookbim_select_elements", "rookbim_clear_selection"])
def test_rookbim_selection_tools_have_rhino_mutate_targeting_policies(name):
    policy = targeting.policy_for_tool(name)

    assert policy.requires_rhino is True
    assert policy.risk == "mutate"


@pytest.mark.parametrize("name,expected", list(ROOKBIM_TOOL_ROUTES.items()))
def test_rookbim_tools_in_bridge_routes(name, expected):
    assert tool_dispatcher.BRIDGE_ROUTES[name] == expected
    assert name not in tool_dispatcher.TRANSFORM_FUNCTIONS


@pytest.mark.asyncio
@pytest.mark.parametrize("name,route", list(ROOKBIM_TOOL_ROUTES.items()))
async def test_rookbim_server_dispatches_to_expected_bridge_route(name, route):
    endpoint, method = route
    body = {
        "rookbim_query_elements": {"category": "Walls"},
        "rookbim_element_info": {"identity": {"documentGuidSource": "unavailable"}},
        "rookbim_element_parameters": {"identity": {"documentGuidSource": "unavailable"}},
        "rookbim_select_elements": {
            "identities": [{"documentGuidSource": "unavailable"}],
        },
        "rookbim_export_elements": {
            "output": {"directory": "C:\\fixtures", "name": "walls"},
        },
        "rookbim_export_preset": {
            "preset": "architectural_shell",
            "output": {"directory": "C:\\fixtures", "name": "shell"},
        },
    }.get(name, {})

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(name, dict(body))

    expected_body = body if body and method == "POST" else None
    assert _normalize_call_rhino_args(mock.call_args) == (
        endpoint,
        method,
        expected_body,
        None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,container",
    [
        ("rookbim_element_info", "identity"),
        ("rookbim_element_parameters", "identity"),
        ("rookbim_select_elements", "identities"),
        ("rookbim_export_elements", "identities"),
    ],
)
async def test_rookbim_identity_consumers_forward_strong_identity_dictionary_byte_exactly(
    name, container
):
    identity = {
        "source": "revit",
        "documentKey": "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac",
        "documentKeySource": "revit_creation_guid_central_path_v1",
        "documentGuid": None,
        "documentGuidSource": "unavailable",
        "documentTitle": "Mødel A",
        "documentPath": "C:\\Models\\A.rvt",
        "elementId": 42,
        "uniqueId": "element-unique-id",
        "fullUniqueId": "element-unique-id",
        "linked": False,
        "resolved": True,
        "confidence": "exact",
    }
    body = {container: identity if container == "identity" else [identity]}
    if name == "rookbim_export_elements":
        body["output"] = {"directory": "C:\\fixtures", "name": "walls"}

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(name, body)

    forwarded = _normalize_call_rhino_args(mock.call_args)[2]
    forwarded_identity = (
        forwarded[container]
        if container == "identity"
        else forwarded[container][0]
    )
    before = json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    after = json.dumps(forwarded_identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert forwarded_identity == identity
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize("name,route", list(ROOKBIM_TOOL_ROUTES.items()))
async def test_rookbim_dispatcher_dispatches_to_expected_bridge_route(name, route):
    endpoint, method = route
    body = {
        "rookbim_query_elements": {"category": "Walls"},
        "rookbim_element_info": {"identity": {"documentGuidSource": "unavailable"}},
        "rookbim_element_parameters": {"identity": {"documentGuidSource": "unavailable"}},
        "rookbim_select_elements": {
            "identities": [{"documentGuidSource": "unavailable"}],
        },
        "rookbim_export_elements": {
            "output": {"directory": "C:\\fixtures", "name": "walls"},
        },
        "rookbim_export_preset": {
            "preset": "architectural_shell",
            "output": {"directory": "C:\\fixtures", "name": "shell"},
        },
    }.get(name, {})

    with patch.object(tool_dispatcher, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await tool_dispatcher.ToolDispatcher(port=9950).dispatch(name, dict(body))

    expected_body = body if body and method == "POST" else None
    assert _normalize_call_rhino_args(mock.call_args) == (
        endpoint,
        method,
        expected_body,
        9950,
    )


def test_rookbim_tool_groups_match_phase1_scope():
    expected_rookbim = list(ROOKBIM_TOOL_ROUTES) + ["rookbim_export_preset_to_rhino"]
    assert tool_groups.TOOL_GROUPS["rookbim"] == expected_rookbim
    assert tool_groups.TOOL_GROUPS["rookbim_readonly"] == ROOKBIM_READONLY_TOOLS
    assert "rookbim_select_elements" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]
    assert "rookbim_clear_selection" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]
    assert "rookbim_readonly" in tool_groups.READONLY_ALLOWED_GROUPS
    assert "rookbim" not in tool_groups.MCP_ONLY_GROUPS
    assert "rookbim_readonly" not in tool_groups.MCP_ONLY_GROUPS


def test_rookbim_workflow_tool_is_not_raw_bridge_route():
    assert "rookbim_export_preset_to_rhino" not in ROOKBIM_TOOL_ROUTES
    assert "rookbim_export_preset_to_rhino" in tool_groups.TOOL_GROUPS["rookbim"]


def test_rookbim_context_categories_registered():
    for name in ROOKBIM_READONLY_TOOLS:
        assert context.get_tool_category(name) == "document"
    assert context.get_tool_category("rookbim_select_elements") == "select"
    assert context.get_tool_category("rookbim_clear_selection") == "select"
