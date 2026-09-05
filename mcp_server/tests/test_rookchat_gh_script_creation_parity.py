import pytest


class _TuplePins(tuple):
    pass


def test_build_local_tools_registers_script_creation_tools():
    from rook.agent.tool_dispatcher import build_local_tools

    local_tools = build_local_tools()

    assert "gh_create_script" in local_tools
    assert "gh_create_python_script" in local_tools
    assert "gh_create_csharp_script" in local_tools


@pytest.mark.asyncio
async def test_csharp_create_preflight_rejects_before_create_component(monkeypatch):
    from rook import server

    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"guid": "created-guid"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_create_script(
        "csharp",
        {
            "code": "public class MyComponent : GH_Component { }",
            "pins_in": [],
            "pins_out": ["A:object"],
        },
        port=9876,
        tool_name="gh_create_csharp_script",
    )

    assert result["success"] is False
    assert result["data"].startswith("C# script preflight failed:")
    assert calls == []


@pytest.mark.asyncio
async def test_unified_csharp_create_preflight_rejects_before_create_component(monkeypatch):
    from rook import server

    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"guid": "created-guid"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._execute_gh_create_script(
        "csharp",
        {
            "language": "csharp",
            "code": "using Rhino.Geometry;\nA = Point3d.Origin;",
            "pins_in": [],
            "pins_out": ["A:Point3d"],
        },
        port=9876,
        tool_name="gh_create_script",
    )

    assert result["success"] is False
    assert "top-level using" in result["data"]
    assert calls == []


@pytest.mark.asyncio
async def test_python_create_path_is_not_csharp_preflighted(monkeypatch):
    from rook import server

    calls = []
    receipt = {
        "schema": "rook.gh_solve_readiness_receipt:v1",
        "receipt_id": "python-create-receipt",
        "document_session_id": "session-1",
        "mutation_epoch": 1,
        "solution_run_epoch": None,
        "completed_solution_run_epoch": 0,
        "status": "pending",
        "reason": None,
        "completion_signal": None,
        "issued_at": "2026-08-12T12:00:00+00:00",
        "completed_at": None,
    }

    async def fake_call_rhino(endpoint, method, data=None, port=None, **_kwargs):
        calls.append((endpoint, method, data))
        if endpoint == "/gh/create-component":
            return {"success": True, "data": {"guid": "python-guid"}}
        if endpoint == "/gh/script":
            return {"success": True, "data": {
                "solve_relevant_mutation_committed": True,
                "solve_readiness_receipt": receipt,
            }}
        if endpoint == "/gh/wait-for-solve-readiness":
            ready = dict(receipt)
            ready.update({
                "solution_run_epoch": 1,
                "completed_solution_run_epoch": 1,
                "status": "ready",
                "completion_signal": "solution_end",
                "completed_at": "2026-08-12T12:00:01+00:00",
            })
            return {"success": True, "data": {
                "schema": "rook.gh_solve_readiness_wait_result:v1",
                "wait_status": "ready",
                "receipt": ready,
            }}
        if endpoint == "/gh/errors":
            return {"success": True, "data": {"errors": [], "warnings": []}}
        return {"success": True, "data": {}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._execute_gh_create_script(
        "python",
        {
            "language": "python",
            "code": "A = 1",
            "pins_in": [],
            "pins_out": ["A:int"],
        },
        port=9876,
        tool_name="gh_create_script",
    )

    assert result["success"] is True
    assert calls[0][0] == "/gh/create-component"


@pytest.mark.asyncio
async def test_dispatcher_unified_gh_create_script_reaches_server_helper(monkeypatch):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append(
            {
                "language": language,
                "arguments": dict(arguments),
                "port": port,
                "tool_name": tool_name,
            }
        )
        return {
            "success": True,
            "data": {
                "component_guid": "script-guid",
                "name": "Script",
                "pins_in": arguments.get("pins_in", []),
                "pins_out": arguments.get("pins_out", []),
            },
        }

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    dispatcher = ToolDispatcher(port=9876, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "A = 1;",
            "pins_in": [],
            "pins_out": ["A:int"],
            "name": "Unified C#",
        },
    )

    assert result["success"] is True
    assert calls == [
        {
            "language": "csharp",
            "arguments": {
                "language": "csharp",
                "code": "A = 1;",
                "pins_in": [],
                "pins_out": ["A:int"],
                "name": "Unified C#",
            },
            "port": 9876,
            "tool_name": "gh_create_script",
        }
    ]


@pytest.mark.parametrize(
    ("tool_name", "expected_language"),
    [
        ("gh_create_python_script", "python"),
        ("gh_create_csharp_script", "csharp"),
    ],
)
@pytest.mark.asyncio
async def test_dispatcher_aliases_force_language_and_preserve_tool_name(
    monkeypatch,
    tool_name,
    expected_language,
):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append(
            {
                "language": language,
                "arguments": dict(arguments),
                "port": port,
                "tool_name": tool_name,
            }
        )
        return {"success": True, "data": {"component_guid": f"{language}-guid"}}

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        tool_name,
        {
            "code": "A = 1;",
            "pins_in": ["R:double"],
            "pins_out": ["A:int"],
            "name": "Alias Script",
        },
    )

    assert result["success"] is True
    assert calls == [
        {
            "language": expected_language,
            "arguments": {
                "code": "A = 1;",
                "pins_in": ["R:double"],
                "pins_out": ["A:int"],
                "name": "Alias Script",
            },
            "port": 9877,
            "tool_name": tool_name,
        }
    ]


@pytest.mark.parametrize(
    ("tool_name", "expected_language"),
    [
        ("gh_create_script", "csharp"),
        ("gh_create_python_script", "python"),
        ("gh_create_csharp_script", "csharp"),
    ],
)
@pytest.mark.asyncio
async def test_dispatcher_create_scripts_materialize_contract_pin_tuples_as_lists(
    monkeypatch,
    tool_name,
    expected_language,
):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append((language, arguments, port, tool_name))
        return {"success": True, "data": {"component_guid": "script-guid"}}

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    owned_pins_in = ("X:double",)
    owned_pins_out = ("A:double",)
    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        tool_name,
        {
            "language": "csharp",
            "code": "A = 1.0;",
            "pins_in": owned_pins_in,
            "pins_out": owned_pins_out,
        },
    )

    assert result["success"] is True
    assert len(calls) == 1
    language, arguments, port, dispatched_tool_name = calls[0]
    assert language == expected_language
    assert port == 9877
    assert dispatched_tool_name == tool_name
    assert type(arguments["pins_in"]) is list
    assert type(arguments["pins_out"]) is list
    assert arguments["pins_in"] == ["X:double"]
    assert arguments["pins_out"] == ["A:double"]
    assert arguments["pins_in"] is not owned_pins_in
    assert arguments["pins_out"] is not owned_pins_out
    assert owned_pins_in == ("X:double",)
    assert owned_pins_out == ("A:double",)


@pytest.mark.asyncio
async def test_dispatcher_create_script_preserves_valid_pin_lists_without_mutation(monkeypatch):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append(arguments)
        return {"success": True, "data": {"component_guid": "script-guid"}}

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    owned_pins_in = ["X:double"]
    owned_pins_out = ["A:double"]
    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        "gh_create_csharp_script",
        {
            "code": "A = 1.0;",
            "pins_in": owned_pins_in,
            "pins_out": owned_pins_out,
        },
    )

    assert result["success"] is True
    assert len(calls) == 1
    assert type(calls[0]["pins_in"]) is list
    assert type(calls[0]["pins_out"]) is list
    assert calls[0]["pins_in"] == ["X:double"]
    assert calls[0]["pins_out"] == ["A:double"]
    assert owned_pins_in == ["X:double"]
    assert owned_pins_out == ["A:double"]


@pytest.mark.parametrize(
    "unsupported_pins",
    [
        "A:double",
        {"name": "A", "type": "double"},
        {"A:double"},
        frozenset({"A:double"}),
        _TuplePins(("A:double",)),
    ],
)
@pytest.mark.asyncio
async def test_dispatcher_create_script_does_not_coerce_unsupported_pin_shapes(
    monkeypatch,
    unsupported_pins,
):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append(arguments)
        return {"success": True, "data": {"component_guid": "script-guid"}}

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        "gh_create_csharp_script",
        {
            "code": "A = 1.0;",
            "pins_in": unsupported_pins,
            "pins_out": unsupported_pins,
        },
    )

    assert result["success"] is True
    assert len(calls) == 1
    assert calls[0]["pins_in"] is unsupported_pins
    assert calls[0]["pins_out"] is unsupported_pins


@pytest.mark.asyncio
async def test_dispatcher_csharp_alias_normalizes_common_model_argument_aliases(monkeypatch):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_execute(language, arguments, port, *, tool_name="gh_create_script"):
        calls.append(
            {
                "language": language,
                "arguments": dict(arguments),
                "port": port,
                "tool_name": tool_name,
            }
        )
        return {"success": True, "data": {"component_guid": "csharp-guid"}}

    monkeypatch.setattr(server, "_execute_gh_create_script", fake_execute)

    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        "gh_create_csharp_script",
        {
            "language": "csharp",
            "params": {
                "script": "var box = new Box();",
                "pins_out": [{"name": "Box", "type": "Brep"}],
            },
            "name": "Box Creator",
        },
    )

    assert result["success"] is True
    assert calls[0]["language"] == "csharp"
    assert calls[0]["tool_name"] == "gh_create_csharp_script"
    assert calls[0]["arguments"]["code"] == "var box = new Box();"
    assert calls[0]["arguments"]["pins_out"] == [{"name": "Box", "type": "Brep"}]
    assert calls[0]["arguments"]["name"] == "Box Creator"


@pytest.mark.asyncio
async def test_dispatcher_csharp_alias_normalized_script_reaches_preflight(monkeypatch):
    from rook import server
    from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools

    calls = []

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"guid": "created-guid"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    dispatcher = ToolDispatcher(port=9877, local_tools=build_local_tools())
    result = await dispatcher.dispatch(
        "gh_create_csharp_script",
        {
            "params": {
                "script": "public class MyComponent : GH_Component { }",
                "pins_out": [{"name": "A", "type": "object"}],
            },
            "name": "Invalid Component",
        },
    )

    assert result["success"] is False
    assert result["data"].startswith("C# script preflight failed:")
    assert calls == []


def test_gh_set_script_transform_remains_raw_escape_hatch():
    from rook.agent.tool_dispatcher import _transform_gh_set_script

    endpoint, method, payload = _transform_gh_set_script(
        {
            "guid": "script-guid",
            "script": "public class MyComponent : GH_Component { }",
        }
    )

    assert endpoint == "/gh/script"
    assert method == "POST"
    assert payload == {
        "guid": "script-guid",
        "script": "public class MyComponent : GH_Component { }",
    }


def _public_tool_catalog():
    import asyncio

    from rook import server
    from rook.agent.tool_registry import build_catalog_from_mcp_tools

    return build_catalog_from_mcp_tools(asyncio.run(server.list_tools()))


def _public_tool_schema(tool_name):
    return _public_tool_catalog()[tool_name]["function"]["parameters"]


def test_public_gh_errors_schema_rejects_arguments():
    schema = _public_tool_schema("gh_errors")

    assert schema["type"] == "object"
    assert schema["properties"] == {}
    assert schema["additionalProperties"] is False


def _schema_text(schema: dict) -> str:
    fn = schema["function"]
    params = fn["parameters"]
    pieces = [fn.get("description", "")]
    for prop in params.get("properties", {}).values():
        if isinstance(prop, dict):
            pieces.append(prop.get("description", ""))
    return "\n".join(pieces)


def test_public_schema_for_unified_create_script_matches_server_contract():
    schema = _public_tool_schema("gh_create_script")

    assert schema["required"] == ["language", "code"]
    assert schema["properties"]["language"]["enum"] == ["python", "csharp"]
    assert "pins_in" in schema["properties"]
    assert "pins_out" in schema["properties"]
    assert schema.get("additionalProperties") is not True


@pytest.mark.parametrize("tool_name", ["gh_create_python_script", "gh_create_csharp_script"])
def test_public_schema_for_create_aliases_matches_server_required_fields(tool_name):
    schema = _public_tool_schema(tool_name)

    assert schema["required"] == ["code", "pins_in", "pins_out"]
    assert "language" not in schema["properties"]
    assert "name" in schema["properties"]
    assert "x" in schema["properties"]
    assert "y" in schema["properties"]
    assert schema.get("additionalProperties") is not True


def test_public_csharp_alias_schema_identifies_rhinocode_contract():
    catalog = _public_tool_catalog()
    text = _schema_text(catalog["gh_create_csharp_script"])

    assert "RhinoCode C# Script" in text
    assert "gh_create_script" in text


def test_gh_create_pin_objects_match_server_pin_contract_without_arbitrary_keys():
    catalog = _public_tool_catalog()
    pin_item = (
        catalog["gh_create_csharp_script"]["function"]["parameters"]
        ["properties"]["pins_out"]["items"]["oneOf"][1]
    )

    assert pin_item["additionalProperties"] is False
    assert set(pin_item["properties"]) == {
        "name",
        "type",
        "nick",
        "access",
        "optional",
        "description",
        "hidden",
    }


def test_public_unified_schema_advertises_csharp_language():
    catalog = _public_tool_catalog()
    language = catalog["gh_create_script"]["function"]["parameters"]["properties"]["language"]

    assert language["enum"] == ["python", "csharp"]


def test_public_surface_includes_script_error_inspection_and_update_tools():
    catalog = _public_tool_catalog()

    assert "gh_errors" in catalog
    assert "gh_update_script" in catalog
    assert catalog["gh_update_script"]["function"]["parameters"]["required"] == [
        "guid",
        "code",
    ]


@pytest.mark.asyncio
async def test_public_create_script_required_fields_match_mcp_server_schemas():
    from rook import server
    from rook.agent.tool_registry import build_catalog_from_mcp_tools

    mcp_tools = {tool.name: tool for tool in await server.list_tools()}
    public_catalog = build_catalog_from_mcp_tools(list(mcp_tools.values()))

    for tool_name in (
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
    ):
        local_schema = public_catalog[tool_name]["function"]["parameters"]
        server_schema = mcp_tools[tool_name].inputSchema
        assert local_schema["required"] == server_schema["required"]

    local_language = public_catalog["gh_create_script"]["function"]["parameters"]["properties"]["language"]
    server_language = mcp_tools["gh_create_script"].inputSchema["properties"]["language"]
    assert local_language["enum"] == server_language["enum"]


def test_gh_canvas_script_create_tools_are_dispatcher_reachable():
    from rook.agent.tool_dispatcher import BRIDGE_ROUTES, TRANSFORM_FUNCTIONS, build_local_tools
    from rook.agent.tool_groups import TOOL_GROUPS

    local_tools = build_local_tools()
    dispatchable = set(local_tools) | set(TRANSFORM_FUNCTIONS) | set(BRIDGE_ROUTES)
    script_create_tools = {
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
    }

    assert script_create_tools <= set(TOOL_GROUPS["gh_canvas"])
    assert script_create_tools <= dispatchable


@pytest.mark.asyncio
async def test_gh_errors_rejects_script_creation_arguments(monkeypatch):
    from rook.agent import tool_dispatcher
    from rook.agent.tool_dispatcher import ToolDispatcher

    called = False

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        nonlocal called
        called = True
        return {"success": True, "data": {"errorCount": 0, "warningCount": 0}}

    monkeypatch.setattr(tool_dispatcher, "call_rhino", fake_call_rhino)

    dispatcher = ToolDispatcher(port=9876)
    result = await dispatcher.dispatch(
        "gh_errors",
        {
            "code": "B = box.ToBrep();",
            "pins_out": ["B:Brep"],
        },
    )

    assert called is False
    assert result["success"] is False
    assert result["error"] == "unexpected_arguments"
    assert "gh_create_csharp_script" in result["message"]
