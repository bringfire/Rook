from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from mcp import types as mcp_types

from rook import server


async def _public_call(name: str, arguments: dict[str, Any]):
    handler = server.mcp.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    return (await handler(request)).root


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "legacy_text"),
    [
        ({"value": 3}, '{\n  "value": 3\n}'),
        (["a", 2], '[\n  "a",\n  2\n]'),
        ("plain text", '"plain text"'),
        (7, "7"),
        (True, "true"),
        (None, "null"),
    ],
)
async def test_public_direct_success_retains_text_and_adds_exact_envelope(
    monkeypatch, data, legacy_text
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    envelope = {"success": True, "data": data}
    retained = AsyncMock(return_value=envelope)
    monkeypatch.setattr(server.targeting, "instances_result", retained)

    result = await _public_call("rhino_instances", {})

    assert len(result.content) == 1
    assert result.content[0].text == legacy_text
    assert result.structuredContent == envelope
    assert result.isError is False
    retained.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "legacy_text"),
    [
        ({"error": "blocked"}, 'Error: {\n  "error": "blocked"\n}'),
        ("plain failure", "Error: plain failure"),
    ],
)
async def test_public_direct_failure_retains_text_and_sets_mcp_error(
    monkeypatch, data, legacy_text
):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    envelope = {"success": False, "data": data}
    retained = AsyncMock(return_value=envelope)
    monkeypatch.setattr(server.targeting, "instances_result", retained)

    result = await _public_call("rhino_instances", {})

    assert len(result.content) == 1
    assert result.content[0].text == legacy_text
    assert result.structuredContent == envelope
    assert result.isError is True
    retained.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_rook_tools_call_exposes_target_envelope_without_double_wrap(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    server._reset_capability_index_cache()
    envelope = {"success": True, "data": ["native", 4]}
    retained = AsyncMock(return_value=envelope)
    monkeypatch.setattr(server.targeting, "instances_result", retained)

    result = await _public_call(
        "rook_tools_call", {"name": "rhino_instances", "arguments": {}}
    )

    assert result.content[0].text == '[\n  "native",\n  4\n]'
    assert result.structuredContent == envelope
    assert result.isError is False
    retained.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_gateway_owned_refusal_is_structured_and_marked_error(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")

    result = await _public_call(
        "rook_tools_call", {"name": "rook_tools_ls", "arguments": {}}
    )

    assert result.content[0].text == (
        'Error: {\n'
        '  "error": "meta_recursion_forbidden",\n'
        '  "name": "rook_tools_ls"\n'
        '}'
    )
    assert result.structuredContent == {
        "success": False,
        "data": {"error": "meta_recursion_forbidden", "name": "rook_tools_ls"},
    }
    assert result.isError is True


@pytest.mark.asyncio
async def test_public_handler_passes_decoded_arguments_to_canonical_ingress(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    seen = []
    envelope = {"success": True, "data": {"matched": 1}}

    async def retained_call_tool(name, arguments, *, _public_mcp=False):
        seen.append((name, arguments, _public_mcp))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text='{\n  "matched": 1\n}')],
            structuredContent=envelope,
            isError=False,
        )

    monkeypatch.setattr(server, "call_tool", retained_call_tool)
    arguments = {"query": "gh_snapshot", "limit": 3}

    result = await _public_call("rook_tools_search", arguments)

    assert seen == [("rook_tools_search", arguments, True)]
    assert result.structuredContent == envelope


@pytest.mark.asyncio
async def test_sdk_validation_error_retains_sdk_owned_shape():
    result = await _public_call("rook_tools_search", {"query": []})

    assert result.isError is True
    assert result.structuredContent is None
    assert "Input validation error" in result.content[0].text


@pytest.mark.asyncio
async def test_pre_envelope_exception_retains_sdk_owned_shape(monkeypatch):
    async def raise_before_envelope(_name, _arguments, *, _public_mcp=False):
        raise RuntimeError("pre-envelope failure")

    monkeypatch.setattr(server, "call_tool", raise_before_envelope)

    result = await _public_call("rhino_instances", {})

    assert result.isError is True
    assert result.structuredContent is None
    assert result.content[0].text == "pre-envelope failure"
