from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rook import server, targeting
from rook.agent import tool_dispatcher, tool_groups


HYGIENE_TOOLS = {
    "rhino_object_visibility": ("/objects/visibility", "POST"),
    "rhino_object_set_layer": ("/objects/set-layer", "POST"),
    "rhino_object_usertext_set_batch": ("/usertext/object-set-batch", "POST"),
}


@pytest.fixture(autouse=True)
def fake_rhino_discovery(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setattr(
        targeting,
        "discover_instances",
        lambda: [
            {
                "host": "127.0.0.1",
                "port": 9950,
                "processId": 7101,
                "pluginType": "native",
            }
        ],
    )
    yield
    targeting.reset_targeting_state_for_tests()


@pytest.mark.asyncio
async def test_hygiene_tools_registered_with_exact_schemas():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}

    assert set(HYGIENE_TOOLS).issubset(by_name)

    visibility = by_name["rhino_object_visibility"].inputSchema
    assert visibility["type"] == "object"
    assert visibility["additionalProperties"] is False
    assert visibility["required"] == ["object_ids", "visible"]
    assert set(visibility["properties"]) == {
        "object_ids",
        "visible",
        "redraw",
        "documentSerialNumber",
    }
    assert visibility["properties"]["object_ids"]["type"] == "array"
    assert visibility["properties"]["object_ids"]["maxItems"] == 500
    assert visibility["properties"]["object_ids"]["minItems"] == 1
    assert visibility["properties"]["object_ids"]["items"] == {"type": "string"}
    assert visibility["properties"]["visible"]["type"] == "boolean"
    assert visibility["properties"]["redraw"]["type"] == "boolean"
    assert visibility["properties"]["documentSerialNumber"]["type"] == "integer"

    set_layer = by_name["rhino_object_set_layer"].inputSchema
    assert set_layer["type"] == "object"
    assert set_layer["additionalProperties"] is False
    assert set_layer["required"] == ["object_ids", "layer"]
    assert set(set_layer["properties"]) == {
        "object_ids",
        "layer",
        "redraw",
        "documentSerialNumber",
    }
    assert set_layer["properties"]["object_ids"]["type"] == "array"
    assert set_layer["properties"]["object_ids"]["maxItems"] == 500
    assert set_layer["properties"]["object_ids"]["minItems"] == 1
    assert set_layer["properties"]["object_ids"]["items"] == {"type": "string"}
    assert set_layer["properties"]["layer"]["type"] == "string"
    assert set_layer["properties"]["redraw"]["type"] == "boolean"
    assert set_layer["properties"]["documentSerialNumber"]["type"] == "integer"

    batch = by_name["rhino_object_usertext_set_batch"].inputSchema
    assert batch["type"] == "object"
    assert batch["additionalProperties"] is False
    assert batch["required"] == ["items"]
    assert set(batch["properties"]) == {"items", "redraw", "documentSerialNumber"}
    assert batch["properties"]["items"]["type"] == "array"
    assert batch["properties"]["items"]["maxItems"] == 500
    assert batch["properties"]["items"]["minItems"] == 1
    assert batch["properties"]["redraw"]["type"] == "boolean"
    assert batch["properties"]["documentSerialNumber"]["type"] == "integer"
    item_schema = batch["properties"]["items"]["items"]
    assert item_schema["type"] == "object"
    assert item_schema["additionalProperties"] is False
    assert item_schema["required"] == ["id", "userStrings"]
    assert set(item_schema["properties"]) == {"id", "userStrings"}
    assert item_schema["properties"]["id"]["type"] == "string"
    assert item_schema["properties"]["userStrings"]["type"] == "object"
    assert item_schema["properties"]["userStrings"]["additionalProperties"] == {
        "type": "string",
        "minLength": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,route", sorted(HYGIENE_TOOLS.items()))
async def test_server_call_tool_dispatches_to_native_route(tool_name, route):
    from rook.bridge import get_rhino_request_context

    body = {
        "rhino_object_visibility": {
            "object_ids": ["11111111-1111-1111-1111-111111111111"],
            "visible": False,
        },
        "rhino_object_set_layer": {
            "object_ids": ["11111111-1111-1111-1111-111111111111"],
            "layer": "Animation::Actors",
        },
        "rhino_object_usertext_set_batch": {
            "items": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "userStrings": {"Director::role": "actor"},
                }
            ],
        },
    }[tool_name]

    captured_context = {}

    async def fake_call_rhino(endpoint, method, data=None, **kwargs):
        captured_context.update(get_rhino_request_context())
        captured_context["kwargs"] = kwargs
        return {"success": True, "data": {"ok": True}}

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.side_effect = fake_call_rhino
        await server.call_tool(tool_name, body)

    assert mock.call_args is not None, f"{tool_name} did not dispatch to call_rhino"
    args, kwargs = mock.call_args
    assert args == (route[0], route[1], body)
    assert kwargs == {}
    assert captured_context["kwargs"] == {}
    assert captured_context["port"] == 9950
    assert captured_context["process_id"] == 7101


@pytest.mark.parametrize("tool_name,route", sorted(HYGIENE_TOOLS.items()))
def test_dispatcher_bridge_routes(tool_name, route):
    assert tool_name in tool_dispatcher.BRIDGE_ROUTES
    assert tool_dispatcher.BRIDGE_ROUTES[tool_name] == route


@pytest.mark.parametrize("tool_name", sorted(HYGIENE_TOOLS))
def test_targeting_policy_is_rhino_mutating(tool_name):
    assert tool_name in targeting.TOOL_POLICIES
    assert targeting.policy_for_tool(tool_name) == targeting.RhinoToolPolicy(
        True, "mutate"
    )


def test_object_hygiene_group_is_mutating_only_and_dispatchable():
    assert "object_hygiene" in tool_groups.TOOL_GROUPS
    assert set(tool_groups.TOOL_GROUPS["object_hygiene"]) == set(HYGIENE_TOOLS)
    assert "object_hygiene" not in tool_groups.READONLY_ALLOWED_GROUPS
    assert "object_hygiene" not in tool_groups.MCP_ONLY_GROUPS

    for tool_name in tool_groups.TOOL_GROUPS["object_hygiene"]:
        assert tool_name in tool_dispatcher.BRIDGE_ROUTES


def test_hygiene_tools_do_not_leak_into_readonly_groups():
    leaked = []
    for group in tool_groups.READONLY_ALLOWED_GROUPS:
        for tool_name in tool_groups.TOOL_GROUPS.get(group, []):
            if tool_name in HYGIENE_TOOLS:
                leaked.append((group, tool_name))
    assert leaked == []


def test_object_set_layer_is_also_available_from_layers_mutating_group():
    assert "rhino_object_set_layer" in tool_groups.TOOL_GROUPS["layers"]
    assert "rhino_object_set_layer" not in tool_groups.TOOL_GROUPS["layers_readonly"]
