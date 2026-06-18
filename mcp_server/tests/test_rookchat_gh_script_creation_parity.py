import pytest


def test_build_local_tools_registers_script_creation_tools():
    from rook.agent.tool_dispatcher import build_local_tools

    local_tools = build_local_tools()

    assert "gh_create_script" in local_tools
    assert "gh_create_python_script" in local_tools
    assert "gh_create_csharp_script" in local_tools


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


def _local_tool_schema(tool_name):
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({tool_name: object()})
    return catalog[tool_name]["function"]["parameters"]


def test_fallback_gh_errors_schema_rejects_arguments():
    from rook.agent.chat.chat_runner import _build_fallback_catalog

    schema = _build_fallback_catalog()["gh_errors"]["function"]["parameters"]

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


def test_local_catalog_schema_for_unified_create_script_matches_server_contract():
    schema = _local_tool_schema("gh_create_script")

    assert schema["required"] == ["language", "code"]
    assert schema["properties"]["language"]["enum"] == ["python", "csharp"]
    assert "pins_in" in schema["properties"]
    assert "pins_out" in schema["properties"]
    assert schema.get("additionalProperties") is not True


@pytest.mark.parametrize("tool_name", ["gh_create_python_script", "gh_create_csharp_script"])
def test_local_catalog_schema_for_create_aliases_matches_server_required_fields(tool_name):
    schema = _local_tool_schema(tool_name)

    assert schema["required"] == ["code", "pins_in", "pins_out"]
    assert "language" not in schema["properties"]
    assert "name" in schema["properties"]
    assert "x" in schema["properties"]
    assert "y" in schema["properties"]
    assert schema.get("additionalProperties") is not True


def test_local_csharp_alias_schema_teaches_rhinocode_script_contract():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"gh_create_csharp_script": object()})
    text = _schema_text(catalog["gh_create_csharp_script"])

    assert "RhinoCode C# Script" in text
    assert "body" in text and "RunScript" in text
    assert "GH_Component" in text and "do not" in text.lower()
    assert "B:Brep" in text


def test_local_unified_schema_teaches_csharp_contract_when_language_is_csharp():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"gh_create_script": object()})
    text = _schema_text(catalog["gh_create_script"])

    assert "language=\"csharp\"" in text or "language: csharp" in text
    assert "RhinoCode C# Script" in text
    assert "body" in text and "RunScript" in text
    assert "GH_Component" in text and "do not" in text.lower()


def test_local_csharp_schema_tells_model_to_update_after_errors():
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({"gh_create_csharp_script": object()})
    text = _schema_text(catalog["gh_create_csharp_script"])

    assert "gh_errors" in text
    assert "gh_update_script" in text
    assert "do not just paste" in text.lower()


@pytest.mark.asyncio
async def test_local_create_script_required_fields_match_mcp_server_schemas():
    from rook import server
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    local_catalog = _build_local_tool_catalog(
        {
            "gh_create_script": object(),
            "gh_create_python_script": object(),
            "gh_create_csharp_script": object(),
        }
    )
    mcp_tools = {tool.name: tool for tool in await server.list_tools()}

    for tool_name in (
        "gh_create_script",
        "gh_create_python_script",
        "gh_create_csharp_script",
    ):
        local_schema = local_catalog[tool_name]["function"]["parameters"]
        server_schema = mcp_tools[tool_name].inputSchema
        assert local_schema["required"] == server_schema["required"]

    local_language = local_catalog["gh_create_script"]["function"]["parameters"]["properties"]["language"]
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
