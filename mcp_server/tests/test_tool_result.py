import json

import pytest
from mcp.types import TextContent

from rook.tool_result import (
    is_error_result,
    parse_call_tool_data,
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
