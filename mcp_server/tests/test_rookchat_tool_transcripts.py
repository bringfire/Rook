import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat.conversation_store import Conversation


class _ToolCall:
    def __init__(self, tool_id, name, arguments):
        self.id = tool_id
        self.name = name
        self.arguments = arguments

    def to_delta(self, index):
        return SimpleNamespace(
            index=index,
            id=self.id,
            function=SimpleNamespace(
                name=self.name,
                arguments=json.dumps(self.arguments),
            ),
        )


async def _stream_chunks(*chunks):
    for chunk in chunks:
        yield chunk


def _chunk(delta):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta)],
        usage=None,
    )


def _usage_chunk():
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
    )


def _tool_stream(*calls):
    delta = SimpleNamespace(
        content=None,
        tool_calls=[call.to_delta(index) for index, call in enumerate(calls)],
    )
    return _stream_chunks(_chunk(delta), _usage_chunk())


def _text_stream(text):
    delta = SimpleNamespace(content=text, tool_calls=None)
    return _stream_chunks(_chunk(delta), _usage_chunk())


def _runtime_facts_patch():
    return patch(
        "rook.agent.chat.chat_runner.collect_runtime_facts",
        AsyncMock(return_value={"verified_runtime_facts": []}),
    )


async def _collect_events(runner, completion_side_effects, user_message="make a box"):
    conv = Conversation(
        id="conv_tool_contract",
        persona="architect",
        model="ollama_chat/qwen3:14b",
        api_base="http://localhost:11434",
    )
    events = []
    with (
        patch(
            "rook.agent.chat.chat_runner.litellm.acompletion",
            AsyncMock(side_effect=completion_side_effects),
        ),
        _runtime_facts_patch(),
    ):
        async for event in runner.run_turn(conv, user_message, "system"):
            events.append(event)
    return events, conv


@pytest.mark.asyncio
async def test_clean_one_box_tool_sequence_is_reported_without_live_rhino():
    tool_results = {
        "gh_create_csharp_script": {
            "success": True,
            "data": {
                "component_guid": "script-guid",
                "name": "Box Maker",
                "pins_out": ["B:Brep"],
            },
        },
        "gh_errors": {
            "success": True,
            "data": {"errorCount": 0, "warningCount": 0},
        },
    }

    async def executor(name, params):
        if name == "request_tools":
            raise AssertionError("request_tools is handled internally")
        return tool_results[name]

    runner = ChatRunner(tool_executor=executor)
    responses = [
        _tool_stream(_ToolCall("call_request", "request_tools", {"group": "gh_canvas"})),
        _tool_stream(
            _ToolCall(
                "call_create",
                "gh_create_csharp_script",
                {
                    "code": (
                        "var box = new Rhino.Geometry.Box("
                        "Rhino.Geometry.Plane.WorldXY, "
                        "new Rhino.Geometry.Interval(0, 10), "
                        "new Rhino.Geometry.Interval(0, 10), "
                        "new Rhino.Geometry.Interval(0, 10)); "
                        "B = box.ToBrep();"
                    ),
                    "pins_in": [],
                    "pins_out": ["B:Brep"],
                    "name": "Box Maker",
                },
            )
        ),
        _tool_stream(_ToolCall("call_errors", "gh_errors", {})),
        _text_stream("Created Box Maker. gh_errors returned 0 errors and 0 warnings."),
    ]

    events, conv = await _collect_events(runner, responses)

    tool_result_events = [
        event for event in events
        if event.type == "tool_result"
    ]
    assert [event.name for event in tool_result_events] == [
        "request_tools",
        "gh_create_csharp_script",
        "gh_errors",
    ]
    assert tool_result_events[0].tool_status == "success"
    assert tool_result_events[1].tool_status == "success"
    assert tool_result_events[2].tool_status == "success"
    assert conv.messages[-1]["role"] == "assistant"
    assert "0 errors" in conv.messages[-1]["content"]


@pytest.mark.asyncio
async def test_bad_gh_errors_arguments_surface_actionable_failure_without_rhino(monkeypatch):
    from rook.agent import tool_dispatcher

    async def fake_call_rhino(endpoint, method, data=None, port=None):
        raise AssertionError("gh_errors with unexpected args must fail before call_rhino")

    monkeypatch.setattr(tool_dispatcher, "call_rhino", fake_call_rhino)

    runner = ChatRunner()
    responses = [
        _tool_stream(_ToolCall("call_request", "request_tools", {"group": "gh_canvas"})),
        _tool_stream(
            _ToolCall(
                "call_bad_errors",
                "gh_errors",
                {"code": "B = box.ToBrep();", "pins_out": ["B:Brep"]},
            )
        ),
        _text_stream("I need to call gh_create_csharp_script instead."),
    ]

    events, conv = await _collect_events(runner, responses)

    bad_result = [
        event for event in events
        if event.type == "tool_result" and event.name == "gh_errors"
    ][0]
    assert bad_result.tool_status == "failed"
    assert "unexpected_arguments" in bad_result.result
    assert "gh_create_csharp_script" in bad_result.result
    assert any(
        message["role"] == "tool" and "unexpected_arguments" in message["content"]
        for message in conv.messages
    )


@pytest.mark.asyncio
async def test_missing_code_create_call_surfaces_failed_tool_status():
    async def executor(name, params):
        if name == "gh_create_csharp_script":
            return {"success": False, "data": "Missing required parameter: code"}
        raise AssertionError(f"unexpected executor call: {name}")

    runner = ChatRunner(tool_executor=executor)
    responses = [
        _tool_stream(_ToolCall("call_request", "request_tools", {"group": "gh_canvas"})),
        _tool_stream(
            _ToolCall(
                "call_create",
                "gh_create_csharp_script",
                {"pins_out": ["B:Brep"], "name": "Box Maker"},
            )
        ),
        _text_stream("I need to retry with code."),
    ]

    events, _conv = await _collect_events(runner, responses)

    create_result = [
        event for event in events
        if event.type == "tool_result" and event.name == "gh_create_csharp_script"
    ][0]
    assert create_result.tool_status == "failed"
    assert "Missing required parameter: code" in create_result.result
