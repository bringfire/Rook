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


def _local_tool_schema(tool_name):
    from rook.agent.chat.chat_runner import _build_local_tool_catalog

    catalog = _build_local_tool_catalog({tool_name: object()})
    return catalog[tool_name]["function"]["parameters"]


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
