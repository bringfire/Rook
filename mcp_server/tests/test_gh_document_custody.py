import asyncio
import json
from types import SimpleNamespace

import pytest
from mcp import types as mcp_types

from rook import server
from rook.gh_document_custody import (
    EXPECTED_GH_DOCUMENT_ID_ARGUMENT,
    INTERNAL_GH_DISPATCH_ARGUMENT,
    GhDispatchContext,
    GhToolClassification,
    classify_gh_tool,
    current_gh_dispatch_context,
    gh_dispatch_scope,
    observe_gh_document_id,
    project_current_gh_document_id,
)


@pytest.mark.parametrize(
    ("name", "scope"),
    [
        ("gh_component_search", "document_independent"),
        ("gh_status", "observation"),
        ("gh_snapshot", "observation"),
        ("gh_set_value", "mutation"),
        ("gh_update_script", "mutation"),
        ("gh_document_open", "transition"),
        ("gh_document_new", "transition"),
        ("gh_learn_directory", "transition"),
    ],
)
def test_gh_classification_has_one_owner(name, scope):
    assert classify_gh_tool(name).value == scope


def _result_payload(result):
    text = result[0].text
    if text.startswith("Error: "):
        return False, json.loads(text.removeprefix("Error: "))
    return True, json.loads(text)


async def _public_call(name: str, arguments: dict):
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    return (await handler(request)).root


@pytest.mark.asyncio
async def test_every_live_gh_mutation_advertises_required_expected_document_id():
    tools = await server._all_live_tools()

    mutations = [
        tool
        for tool in tools
        if classify_gh_tool(tool.name) is GhToolClassification.MUTATION
    ]
    assert mutations
    for tool in mutations:
        expected = tool.inputSchema["properties"][EXPECTED_GH_DOCUMENT_ID_ARGUMENT]
        assert expected == {
            "type": "string",
            "description": (
                "Canonical Grasshopper DocumentID observed immediately before "
                "this mutation."
            ),
        }
        assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT in tool.inputSchema["required"]


@pytest.mark.parametrize(
    "name",
    [
        "gh_status",
        "gh_snapshot",
        "gh_component_search",
        "gh_library",
        "gh_document_open",
        "gh_document_new",
        "gh_learn_directory",
    ],
)
@pytest.mark.asyncio
async def test_non_mutating_gh_schemas_do_not_advertise_expected_document_id(name):
    tools = {tool.name: tool for tool in await server._all_live_tools()}
    if name not in tools:
        return

    schema = tools[name].inputSchema
    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in schema.get("properties", {})
    assert EXPECTED_GH_DOCUMENT_ID_ARGUMENT not in schema.get("required", [])


@pytest.mark.asyncio
async def test_rook_tools_read_returns_the_same_augmented_mutation_schema(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()

    direct = {
        tool.name: tool for tool in await server._all_live_tools()
    }["gh_update_script"].inputSchema
    success, gateway = _result_payload(
        await server.call_tool("rook_tools_read", {"name": "gh_update_script"})
    )

    assert success is True
    assert gateway["input_schema"] == direct


@pytest.mark.parametrize(
    "outer",
    [
        ("gh_update_script", {"guid": "C1", "code": "x = 1"}),
        (
            "rook_tools_call",
            {
                "name": "gh_update_script",
                "arguments": {"guid": "C1", "code": "x = 1"},
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_missing_expected_document_id_refuses_before_routing(monkeypatch, outer):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    routed = False

    def policy(_name):
        nonlocal routed
        routed = True
        return SimpleNamespace(requires_rhino=False)

    monkeypatch.setattr(server.targeting, "policy_for_tool", policy)
    success, payload = _result_payload(await server.call_tool(*outer))

    assert success is False
    assert payload["error"] == "gh_target_required"
    assert routed is False


@pytest.mark.asyncio
async def test_direct_mcp_missing_expected_document_id_uses_stable_rook_refusal(
    monkeypatch,
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")

    result = await _public_call(
        "gh_update_script",
        {"guid": "C1", "code": "x = 1"},
    )

    assert result.isError is True
    assert result.structuredContent["data"]["error"] == "gh_target_required"


@pytest.mark.parametrize(
    "value",
    [
        "not-a-guid",
        "00000000-0000-0000-0000-000000000000",
        "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        "{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}",
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_noncanonical_expected_document_id_is_invalid_arguments(
    monkeypatch, value
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    success, payload = _result_payload(
        await server.call_tool(
            "gh_update_script",
            {
                "guid": "C1",
                "code": "x = 1",
                EXPECTED_GH_DOCUMENT_ID_ARGUMENT: value,
            },
        )
    )

    assert success is False
    assert payload["error"] == "invalid_arguments"
    assert payload["name"] == "gh_update_script"


@pytest.mark.asyncio
async def test_valid_expected_document_id_is_service_context_not_tool_argument(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    async def inspect_dispatch(name, arguments):
        context = current_gh_dispatch_context()
        return {
            "success": True,
            "data": {
                "name": name,
                "arguments": arguments,
                "scope": context.classification.value,
                "expected": context.expected_gh_document_id,
            },
        }

    monkeypatch.setattr(server, "_call_tool_dispatch", inspect_dispatch)
    expected = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    success, payload = _result_payload(
        await server.call_tool(
            "gh_update_script",
            {
                "guid": "C1",
                "code": "x = 1",
                EXPECTED_GH_DOCUMENT_ID_ARGUMENT: expected,
            },
        )
    )

    assert success is True
    assert payload == {
        "name": "gh_update_script",
        "arguments": {"guid": "C1", "code": "x = 1"},
        "scope": "mutation",
        "expected": expected,
    }


@pytest.mark.asyncio
async def test_gateway_mutation_reenters_the_same_service_owned_dispatch(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )

    async def inspect_dispatch(name, arguments):
        context = current_gh_dispatch_context()
        return {
            "success": True,
            "data": {
                "arguments": arguments,
                "scope": context.classification.value,
                "expected": context.expected_gh_document_id,
            },
        }

    monkeypatch.setattr(server, "_call_tool_dispatch", inspect_dispatch)
    expected = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    success, payload = _result_payload(
        await server.call_tool(
            "rook_tools_call",
            {
                "name": "gh_update_script",
                "arguments": {
                    "guid": "C1",
                    "code": "x = 1",
                    EXPECTED_GH_DOCUMENT_ID_ARGUMENT: expected,
                },
            },
        )
    )

    assert success is True
    assert payload == {
        "arguments": {"guid": "C1", "code": "x = 1"},
        "scope": "mutation",
        "expected": expected,
    }


@pytest.mark.asyncio
async def test_service_context_never_enters_authoring_or_routing_arguments(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    observed = []

    def inspect_authoring(_name, arguments):
        observed.append(dict(arguments))
        return None

    monkeypatch.setattr(server, "model_facing_script_handoff", inspect_authoring)
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    monkeypatch.setattr(
        server,
        "_call_tool_dispatch",
        lambda _name, _arguments: asyncio.sleep(
            0, result={"success": True, "data": {}}
        ),
    )

    await server.call_tool(
        "gh_update_script",
        {
            "guid": "C1",
            "code": "x = 1",
            EXPECTED_GH_DOCUMENT_ID_ARGUMENT: (
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
            ),
        },
    )

    assert observed
    assert observed[0][EXPECTED_GH_DOCUMENT_ID_ARGUMENT] == (
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )
    assert INTERNAL_GH_DISPATCH_ARGUMENT not in observed[0]


@pytest.mark.asyncio
async def test_model_cannot_supply_service_owned_dispatch_envelope(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    success, payload = _result_payload(
        await server.call_tool(
            "gh_status",
            {"_rookGhDispatchScope": "mutation"},
        )
    )

    assert success is False
    assert payload["error"] == "invalid_arguments"
    assert payload["name"] == "gh_status"


def test_composite_transition_projects_final_nested_document_identity():
    context = GhDispatchContext(GhToolClassification.TRANSITION, None)
    document_id = "11111111-1111-1111-1111-111111111111"

    with gh_dispatch_scope(context):
        observe_gh_document_id(
            {"success": True, "data": {"ghDocumentId": document_id}}
        )
        result = project_current_gh_document_id(
            {"success": True, "data": {"processed": 1}}, context
        )

    assert result["data"]["ghDocumentId"] == document_id


def test_document_identity_observation_is_scoped_and_ignores_untrusted_shapes():
    context = GhDispatchContext(GhToolClassification.OBSERVATION, None)
    with gh_dispatch_scope(context):
        observe_gh_document_id(
            {"success": True, "data": {"ghDocumentId": "not-canonical"}}
        )
        assert project_current_gh_document_id({"success": True}, context) == {
            "success": True
        }

    with gh_dispatch_scope(context):
        assert project_current_gh_document_id({"success": True}, context) == {
            "success": True
        }
