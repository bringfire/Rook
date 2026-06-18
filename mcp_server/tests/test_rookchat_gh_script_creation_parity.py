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
