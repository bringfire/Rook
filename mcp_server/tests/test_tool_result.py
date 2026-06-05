import asyncio
import json

import pytest
from mcp.types import TextContent

from rook import server
from rook.tool_result import (
    call_tool_data,
    is_error_result,
    parse_call_tool_data,
    parse_call_tool_error,
    text_from_call_tool_result,
)


def _wire(text: str) -> list[TextContent]:
    """Build a call_tool()-shaped result list carrying exactly `text`."""
    return [TextContent(type="text", text=text)]


def test_text_from_result_returns_payload():
    assert text_from_call_tool_result(_wire("hello")) == "hello"


def test_text_from_empty_result_is_blank():
    assert text_from_call_tool_result([]) == ""


def test_is_error_result_true_on_error_prefix():
    assert is_error_result(_wire("Error: boom")) is True


def test_is_error_result_false_on_success_text():
    assert is_error_result(_wire(json.dumps({"ok": 1}))) is False


def test_parse_data_returns_success_dict():
    assert parse_call_tool_data(_wire(json.dumps({"a": 1, "b": [2]}))) == {"a": 1, "b": [2]}


def test_parse_data_raises_on_error_result():
    with pytest.raises(ValueError):
        parse_call_tool_data(_wire("Error: nope"))


def test_parse_data_raises_on_non_json():
    with pytest.raises(ValueError):
        parse_call_tool_data(_wire("not json at all"))


def test_parse_data_raises_on_non_dict_json():
    # success text that parses to a JSON list/str/number is a contract violation
    with pytest.raises(ValueError):
        parse_call_tool_data(_wire(json.dumps([1, 2, 3])))


def test_parse_error_returns_dict_for_json_error():
    res = _wire("Error: " + json.dumps({"code": "rhino_session_not_found", "retryable": False}))
    assert parse_call_tool_error(res) == {"code": "rhino_session_not_found", "retryable": False}


def test_parse_error_returns_raw_string_for_plain_error():
    assert parse_call_tool_error(_wire("Error: boom")) == "boom"


def test_parse_error_returns_raw_string_for_brace_non_json():
    # the tricky case: looks JSON-ish (has a brace) but is not valid JSON -> raw, no raise
    assert parse_call_tool_error(_wire("Error: {not json")) == "{not json"


def test_parse_error_raises_on_success_result():
    with pytest.raises(ValueError):
        parse_call_tool_error(_wire(json.dumps({"ok": 1})))


def test_call_tool_data_returns_success_dict():
    async def fake_call_tool(name, arguments):
        assert name == "some_tool" and arguments == {"x": 1}
        return _wire(json.dumps({"ok": True}))

    assert asyncio.run(call_tool_data(fake_call_tool, "some_tool", {"x": 1})) == {"ok": True}


def test_call_tool_data_propagates_error_as_valueerror():
    async def fake_call_tool(name, arguments):
        return _wire("Error: boom")

    with pytest.raises(ValueError):
        asyncio.run(call_tool_data(fake_call_tool, "some_tool", {}))


# --- Contract: parsers are the inverse of server._format_tool_result -----------------

def test_contract_success_dict_roundtrips():
    data = {"artifacts": [{"path": "p"}], "n": 1}
    rendered = server._format_tool_result({"success": True, "data": data})
    assert not is_error_result(rendered)
    assert parse_call_tool_data(rendered) == data


def test_contract_error_dict_roundtrips():
    data = {"code": "rhino_session_not_found", "retryable": False}
    rendered = server._format_tool_result({"success": False, "data": data})
    assert is_error_result(rendered)
    assert parse_call_tool_error(rendered) == data


def test_contract_error_string_roundtrips():
    rendered = server._format_tool_result({"success": False, "data": "boom"})
    assert is_error_result(rendered)
    assert parse_call_tool_error(rendered) == "boom"


def test_contract_success_parser_rejects_error_envelope():
    rendered = server._format_tool_result({"success": False, "data": {"code": "x"}})
    with pytest.raises(ValueError):
        parse_call_tool_data(rendered)


def test_contract_error_parser_rejects_success_envelope():
    rendered = server._format_tool_result({"success": True, "data": {"k": 1}})
    with pytest.raises(ValueError):
        parse_call_tool_error(rendered)
