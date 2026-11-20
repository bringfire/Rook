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
    "rookbim_run_transaction": ("/bim/run-transaction", "POST"),
    "rookbim_transaction_receipt": ("/bim/transaction-receipt", "POST"),
}

# Every rookbim_* tool except the one that writes the Revit model.
ROOKBIM_NON_WRITING_TOOLS = [
    name for name in ROOKBIM_TOOL_ROUTES if name != "rookbim_run_transaction"
] + ["rookbim_export_preset_to_rhino"]

ROOKBIM_READONLY_TOOLS = [
    "rookbim_status",
    "rookbim_active_document",
    "rookbim_list_categories",
    "rookbim_query_elements",
    "rookbim_element_info",
    "rookbim_element_parameters",
    "rookbim_transaction_receipt",
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
        "rookbim_run_transaction": {
            "name": "Rename Level 2",
            "code": "doc.GetElement(DB.ElementId(311)).Name = 'Level 02'",
        },
        "rookbim_transaction_receipt": {"transactionId": "tx-0123456789ab"},
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
        "rookbim_run_transaction": {
            "name": "Rename Level 2",
            "code": "doc.GetElement(DB.ElementId(311)).Name = 'Level 02'",
        },
        "rookbim_transaction_receipt": {"transactionId": "tx-0123456789ab"},
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


@pytest.mark.asyncio
async def test_rookbim_run_transaction_schema_requires_name_and_code():
    schema = (await _tools_by_name())["rookbim_run_transaction"].inputSchema

    assert schema["type"] == "object"
    assert schema["required"] == ["name", "code"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "name",
        "code",
        "timeoutSeconds",
        "documentKey",
        "port",
    }
    # documentKey is optional: an unsaved document may have none to pass.
    assert schema["properties"]["documentKey"]["type"] == "string"
    assert schema["properties"]["documentKey"]["maxLength"] == 300
    # A blank key must not pass as "guarded": only leaving it out is unguarded.
    assert schema["properties"]["documentKey"]["minLength"] == 1
    assert "do not send an empty string" in schema["properties"]["documentKey"]["description"]
    # The same limit the HTTP route enforces, so a schema-valid call is not
    # refused for length.
    assert schema["properties"]["code"]["maxLength"] == 200000
    assert schema["properties"]["port"] == PORT_SCHEMA
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["name"]["minLength"] == 1
    assert schema["properties"]["name"]["maxLength"] == 120
    assert schema["properties"]["code"]["type"] == "string"
    assert schema["properties"]["code"]["minLength"] == 1
    timeout = schema["properties"]["timeoutSeconds"]
    assert (timeout["type"], timeout["minimum"], timeout["maximum"], timeout["default"]) == (
        "integer",
        1,
        90,
        60,
    )


def test_rookbim_run_transaction_is_a_rhino_routed_mutation():
    policy = targeting.policy_for_tool("rookbim_run_transaction")

    assert policy.requires_rhino is True
    assert policy.risk == "mutate"
    assert context.get_tool_category("rookbim_run_transaction") == "document"


def test_rookbim_run_transaction_is_excluded_from_every_readonly_surface():
    from rook import mcp_tool_profiles

    assert "rookbim_run_transaction" in tool_groups.TOOL_GROUPS["rookbim"]
    assert "rookbim_run_transaction" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]
    assert "rookbim_run_transaction" not in mcp_tool_profiles.PUBLIC_READONLY_TOOL_NAMES
    assert (
        mcp_tool_profiles.tool_blocked(
            "rookbim_run_transaction", mcp_tool_profiles.Profile.READONLY
        )
        is True
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ROOKBIM_NON_WRITING_TOOLS)
async def test_rookbim_non_writing_tools_say_so_and_name_the_writing_tool(name):
    description = (await _tools_by_name())[name].description

    assert "never changes the revit model" in description.lower()
    assert "To change the model use rookbim_run_transaction." in description


@pytest.mark.asyncio
async def test_rookbim_run_transaction_description_states_contract_and_refusals():
    description = (await _tools_by_name())["rookbim_run_transaction"].description

    # What it is, and that it is the only one.
    assert "only RookBIM tool that writes the Revit model" in description
    assert "Rhino.Inside.Revit" in description
    # Synchronous, atomic, one undo entry.
    assert "answers in this same call" in description
    assert "committed only if the script runs to its end" in description
    assert "rolled back and the active document is unchanged" in description
    # One vocabulary for the outcome, with what each value lets the caller do.
    for status in ("committed", "rolled_back", "not_started", "open", "unresolved"):
        assert status in description
    assert "`transaction` {id, name, status} and `documentChanged`" in description
    assert "on a refusal they are in data.details" in description
    assert "call rookbim_transaction_receipt with transaction.id" in description
    assert "one entry called `name` in Revit's undo list" in description
    # Names bound for the script, and what the script must not do.
    for bound in ("doc", "uidoc", "uiapp", "app", "DB", "UI", "`result`"):
        assert bound in description
    assert "no DB.Transaction, no DB.TransactionGroup" in description
    # Every refusal the route can produce is named with what to do next.
    for code in (
        "revit_not_idle",
        "document_mismatch",
        "document_not_modifiable",
        "no_active_document",
        "invalid_request",
        "transaction_script_failed",
        "transaction_rolled_back",
        "transaction_timeout",
        "transaction_outcome_unknown",
    ):
        assert code in description
    # A timeout must not be described as a guaranteed stop, and an unknown
    # outcome must not be described as "not committed".
    assert "Rook cannot stop a running script" in description
    assert "do not run the script again" in description
    assert "transaction_timeout with status open" in description
    # What the rollback guarantee does not cover.
    assert "Do not edit another document" in description
    assert "do not schedule work for later" in description
    # How to use what comes back, exactly.
    assert "rookbim_element_info {identity: entry.identity}" in description
    assert "rookbim_select_elements {identities: [entry.identity]}" in description
    assert "the transaction status is never left out" in description
    assert "identityOmittedReason" in description
    assert "resultOmittedReason" in description
    assert "Pass `documentKey`" in description
    # Exclusions: what to use instead.
    assert "rookbim_query_elements" in description
    assert "Do not use rhino_execute to change Revit" in description


@pytest.mark.asyncio
async def test_rookbim_run_transaction_forwards_code_and_name_byte_exactly():
    body = {
        "name": "Sätt nivånamn",
        "code": "lvl = doc.GetElement(DB.ElementId(311))\nlvl.Name = 'Plan 02'\nresult = {'id': 311}\n",
        "timeoutSeconds": 30,
        "documentKey": "file-document-v1:50250fd46d4c96e14f57ff283d6fd21965d8525a34d638e5070eaf60df13a0ac",
    }

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool("rookbim_run_transaction", dict(body))

    assert _normalize_call_rhino_args(mock.call_args) == (
        "/bim/run-transaction",
        "POST",
        body,
        None,
    )


@pytest.mark.asyncio
async def test_rookbim_run_transaction_refusal_reaches_the_model_with_code_and_cause():
    refusal = {
        "success": False,
        "data": {
            "errorCode": "revit_not_idle",
            "message": (
                "Revit did not become idle within 10 s, so RookBIM operation "
                "'run_transaction' never ran and nothing was read or changed. The likely "
                "cause is an open dialog or an active command in Revit."
            ),
            "details": {"operation": "run_transaction", "waitedSeconds": 10, "workStarted": False},
        },
    }

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = refusal
        result = await server.call_tool(
            "rookbim_run_transaction", {"name": "Rename", "code": "pass"}
        )

    text = "".join(getattr(item, "text", "") for item in result)
    assert "revit_not_idle" in text
    assert "open dialog or an active command in Revit" in text
    assert "not_rhino_inside" not in text


@pytest.mark.asyncio
async def test_rhino_execute_points_revit_writes_at_rookbim_run_transaction():
    description = (await _tools_by_name())["rhino_execute"].description

    # The route a model actually took to write Revit on 2026-11-20.
    assert "Rhino.Inside.Revit" in description
    assert "cannot change the Revit model" in description
    assert "To change the Revit model use rookbim_run_transaction." in description
    # The existing guidance for ordinary Rhino scripting is kept.
    assert "import rhinoscriptsyntax as rs" in description


@pytest.mark.asyncio
async def test_rookbim_transaction_receipt_schema_takes_an_optional_id():
    schema = (await _tools_by_name())["rookbim_transaction_receipt"].inputSchema

    assert schema["type"] == "object"
    assert schema["required"] == []
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"transactionId", "port"}
    assert schema["properties"]["transactionId"]["type"] == "string"
    assert schema["properties"]["transactionId"]["minLength"] == 1
    assert schema["properties"]["port"] == PORT_SCHEMA


def test_rookbim_transaction_receipt_is_a_read_available_in_the_readonly_profile():
    from rook import mcp_tool_profiles

    policy = targeting.policy_for_tool("rookbim_transaction_receipt")
    assert policy.requires_rhino is True
    assert policy.risk == "read"
    assert "rookbim_transaction_receipt" in mcp_tool_profiles.PUBLIC_READONLY_TOOL_NAMES
    assert "rookbim_transaction_receipt" in tool_groups.TOOL_GROUPS["rookbim_readonly"]


@pytest.mark.asyncio
async def test_rookbim_transaction_receipt_description_says_when_and_what():
    description = (await _tools_by_name())["rookbim_transaction_receipt"].description

    assert "transaction.status open or unresolved" in description
    assert "works while Revit is busy" in description
    for status in ("committed", "rolled_back", "not_started", "open", "unresolved"):
        assert status in description
    assert "final (true once the status can no longer change)" in description
    # What it does not keep, and what to do then.
    assert "do not survive a restart of Revit" in description
    assert "transaction_receipt_not_found" in description
    assert "read the model back" in description


@pytest.mark.asyncio
async def test_rookbim_transaction_receipt_without_id_lists_recent_receipts():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"receipts": [], "kept": 64}}
        await server.call_tool("rookbim_transaction_receipt", {})

    endpoint, method, data, port = _normalize_call_rhino_args(mock.call_args)
    assert (endpoint, method, port) == ("/bim/transaction-receipt", "POST", None)
    assert not data
