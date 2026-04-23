"""MCP-layer tests for the Vision tools (PR-6).

Scope:
- Pin that all 8 Vision tools are registered in server.list_tools().
- Pin that call_tool() dispatches each to the correct /vision/* endpoint
  with the correct HTTP method and body/query shape.
- Pin that path-param tools (get, approve, delete) URL-encode
  artifact_id so '/', '?', '#' cannot alter routing before reaching
  managed RequireArtifactId.
- Pin tool_groups.py: "vision" and "vision_readonly" exist, hold the
  right tools, and are registered in MCP_ONLY_GROUPS until agent-side
  dispatch is added.

Does NOT cover:
- The native /vision/* route contract itself (that's
  test_vision_routes_live.py, live-Rhino, skips without Rhino).
- Response shape transformations — call_tool is a pass-through that
  serializes result["data"] on success and prefixes "Error: " on
  failure; the envelope shape assertions belong to the live tests.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Mirror the shim used by test_bridge.py so `rook.*` imports resolve
# against the checked-out source tree.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server
from rook.agent import tool_groups


VISION_TOOL_NAMES = [
    "rhino_render_view",
    "rhino_enhance_prompt",
    "rhino_capture_depth",
    "rhino_vision_artifacts",
    "rhino_vision_get_artifact",
    "rhino_vision_approve",
    "rhino_vision_delete_artifact",
    "rhino_vision_consume_approved",
]


VISION_READONLY_TOOL_NAMES = [
    "rhino_vision_artifacts",
    "rhino_vision_get_artifact",
    "rhino_vision_consume_approved",
]


# ─── list_tools() discovery ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_vision_tools_registered():
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    for name in VISION_TOOL_NAMES:
        assert name in tool_names, (
            f"Vision tool {name!r} missing from list_tools(). "
            f"Registered vision tools: "
            f"{sorted(n for n in tool_names if 'vision' in n or n.startswith('rhino_render') or n.startswith('rhino_enhance') or n.startswith('rhino_capture'))}"
        )


@pytest.mark.asyncio
async def test_each_vision_tool_has_nonempty_description_and_schema():
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}
    for name in VISION_TOOL_NAMES:
        tool = by_name[name]
        assert tool.description, f"{name} description is empty"
        assert tool.inputSchema, f"{name} inputSchema is empty"
        assert tool.inputSchema.get("type") == "object"


@pytest.mark.asyncio
async def test_vision_tool_required_fields_match_native_contract():
    """Each tool's 'required' list must match what VisionHandler.cs
    enforces — if managed requires a field, the MCP schema must declare
    it required too, so agents get the validation error at schema
    level instead of seeing a 400 from managed."""
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}

    # (tool_name, expected_required_set)
    expected = {
        "rhino_render_view": {"prompt", "input_image_path"},
        "rhino_enhance_prompt": {"prompt"},
        "rhino_capture_depth": set(),
        "rhino_vision_artifacts": set(),
        "rhino_vision_get_artifact": {"artifact_id"},
        "rhino_vision_approve": {"artifact_id"},
        "rhino_vision_delete_artifact": {"artifact_id"},
        "rhino_vision_consume_approved": set(),
    }
    for name, want in expected.items():
        got = set(by_name[name].inputSchema.get("required", []))
        assert got == want, f"{name} required={got}, expected {want}"


# ─── call_tool() dispatch — endpoint + method ─────────────────────────


@pytest.mark.asyncio
async def test_render_view_dispatches_to_generate_post():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifact_id": "X"}}
        await server.call_tool(
            "rhino_render_view",
            {"prompt": "p", "input_image_path": "C:/x.png"},
        )
    args, kwargs = mock.call_args
    assert args[0] == "/vision/generate"
    assert args[1] == "POST"
    # The whole argument dict (minus port) is forwarded as the body.
    assert args[2] == {"prompt": "p", "input_image_path": "C:/x.png"}


@pytest.mark.asyncio
async def test_enhance_prompt_dispatches_to_enhance_prompt_post():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifact_id": "X"}}
        await server.call_tool("rhino_enhance_prompt", {"prompt": "p"})
    args, _ = mock.call_args
    assert args[0] == "/vision/enhance-prompt"
    assert args[1] == "POST"


@pytest.mark.asyncio
async def test_capture_depth_dispatches_to_capture_depth_post():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifact_id": "X"}}
        await server.call_tool("rhino_capture_depth", {"max_edge": 512})
    args, _ = mock.call_args
    assert args[0] == "/vision/capture-depth"
    assert args[1] == "POST"
    assert args[2] == {"max_edge": 512}


@pytest.mark.asyncio
async def test_consume_approved_dispatches_post_with_body():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifact": None}}
        await server.call_tool(
            "rhino_vision_consume_approved", {"kind": "generated_image"},
        )
    args, _ = mock.call_args
    assert args[0] == "/vision/artifacts/consume-approved"
    assert args[1] == "POST"
    assert args[2] == {"kind": "generated_image"}


# ─── call_tool() dispatch — query-param folding ───────────────────────


@pytest.mark.asyncio
async def test_list_artifacts_folds_filters_into_query_string():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifacts": [], "count": 0}}
        await server.call_tool(
            "rhino_vision_artifacts",
            {"kind": "generated_image", "approved": True, "limit": 50},
        )
    args, _ = mock.call_args
    endpoint = args[0]
    assert endpoint.startswith("/vision/artifacts?")
    # Order of query params is insertion-order by urlencode; assert
    # by membership rather than exact string so we don't bind to
    # a particular ordering.
    assert "kind=generated_image" in endpoint
    assert "approved=true" in endpoint
    assert "limit=50" in endpoint


@pytest.mark.asyncio
async def test_list_artifacts_approved_false_lowercase():
    """Python bool repr is 'True'/'False'; the native route expects
    lowercase 'true'/'false'. Dispatcher must normalize."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifacts": [], "count": 0}}
        await server.call_tool(
            "rhino_vision_artifacts", {"approved": False},
        )
    endpoint = mock.call_args[0][0]
    assert "approved=false" in endpoint
    assert "approved=False" not in endpoint  # the Python-repr bug canary


@pytest.mark.asyncio
async def test_list_artifacts_approved_string_false_not_flipped_by_truthiness():
    """If an LLM passes the string 'false' (despite the inputSchema
    declaring a bool — no server-side schema enforcement is
    guaranteed), Python truthiness would turn it into 'true' under
    a naive ternary. The dispatcher must only apply true/false
    mapping to actual bool instances; other values pass through
    as-is for native to validate.

    Regression gate for Codex PR-6 round 2 finding on approved
    truthiness."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifacts": [], "count": 0}}
        await server.call_tool(
            "rhino_vision_artifacts", {"approved": "false"},
        )
    endpoint = mock.call_args[0][0]
    # Passes through as-is — native accepts "false" and "true" per the
    # PR-5b native query folding (VisionHandler.cpp). The dispatcher
    # must NOT silently flip this to "true" via Python truthiness.
    assert "approved=false" in endpoint
    assert "approved=true" not in endpoint


@pytest.mark.asyncio
async def test_list_artifacts_approved_bogus_string_passes_through():
    """Non-bool, non-'true'/'false' values pass through unchanged;
    native is the validator and will return a structured error."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifacts": [], "count": 0}}
        await server.call_tool(
            "rhino_vision_artifacts", {"approved": "bogus"},
        )
    endpoint = mock.call_args[0][0]
    assert "approved=bogus" in endpoint


@pytest.mark.asyncio
async def test_list_artifacts_approved_zero_int_passes_through():
    """int 0 is Python-falsy but not a bool — must pass through as
    '0' (native accepts '0' per the PR-5b review-round fix), not
    get auto-mapped to 'false' via the bool ternary branch."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifacts": [], "count": 0}}
        await server.call_tool(
            "rhino_vision_artifacts", {"approved": 0},
        )
    endpoint = mock.call_args[0][0]
    assert "approved=0" in endpoint


@pytest.mark.asyncio
async def test_list_artifacts_no_filters_hits_bare_endpoint():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"artifacts": [], "count": 0}}
        await server.call_tool("rhino_vision_artifacts", {})
    endpoint = mock.call_args[0][0]
    assert endpoint == "/vision/artifacts"


# ─── call_tool() dispatch — path-param URL encoding ───────────────────


@pytest.mark.asyncio
async def test_get_artifact_encodes_path_id_valid_guid():
    guid = "12345678-1234-1234-1234-123456789abc"
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(
            "rhino_vision_get_artifact", {"artifact_id": guid},
        )
    args, _ = mock.call_args
    assert args[0] == f"/vision/artifacts/{guid}"


@pytest.mark.asyncio
async def test_get_artifact_rejects_slash_before_http():
    """cpp-httplib decodes %2F to '/' BEFORE route matching
    (vendor/httplib/httplib.h line 6390), so quote()-encoded
    slashes misroute to a generic 404 with no X-Rook-Vision-Op
    header. The MCP layer must reject these pre-HTTP so callers
    still get a structured Rook envelope."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(
            "rhino_vision_get_artifact", {"artifact_id": "bad/segment"},
        )
    # call_rhino was never invoked — the MCP layer rejected first.
    mock.assert_not_called()
    # Tool result surfaces the error envelope. call_tool stringifies
    # failure data with "Error: " prefix per server.py:17150 convention.
    assert len(result) == 1
    assert "Error:" in result[0].text
    assert "'/'" in result[0].text and "artifact_id" in result[0].text


@pytest.mark.asyncio
async def test_get_artifact_rejects_backslash_before_http():
    """Windows-style path separators are also blocked defensively —
    cpp-httplib may or may not normalize them, but the MCP boundary
    shouldn't need to know. Uniform rejection of both separators."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(
            "rhino_vision_get_artifact", {"artifact_id": r"bad\segment"},
        )
    mock.assert_not_called()
    assert "Error:" in result[0].text


@pytest.mark.asyncio
async def test_get_artifact_rejects_path_traversal_attempt():
    # ../../etc/passwd is a '/'-bearing string; the MCP layer rejects
    # it explicitly before URL construction.
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(
            "rhino_vision_get_artifact", {"artifact_id": "../../etc/passwd"},
        )
    mock.assert_not_called()
    assert "Error:" in result[0].text


@pytest.mark.asyncio
async def test_get_artifact_rejects_empty_id():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(
            "rhino_vision_get_artifact", {"artifact_id": ""},
        )
    mock.assert_not_called()
    assert "Error:" in result[0].text


@pytest.mark.asyncio
async def test_get_artifact_encodes_query_separator_in_path_id():
    """'?' is safe to url-encode: httplib strips fragments on the
    raw target BEFORE decoding and divides on literal '?' — encoded
    '%3F' survives both stages and reaches the regex as part of the
    path segment, so it routes to managed and rejects as non-GUID
    there. Verified by tracing httplib lines 6380–6393."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(
            "rhino_vision_get_artifact", {"artifact_id": "bad?x=1"},
        )
    endpoint = mock.call_args[0][0]
    assert "?" not in endpoint
    assert endpoint == "/vision/artifacts/bad%3Fx%3D1"


@pytest.mark.asyncio
async def test_get_artifact_encodes_fragment_in_path_id():
    """'#' is also safe to url-encode: the fragment strip at
    httplib line 6381 only removes literal '#', not '%23'."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(
            "rhino_vision_get_artifact", {"artifact_id": "bad#frag"},
        )
    endpoint = mock.call_args[0][0]
    assert "#" not in endpoint
    assert endpoint == "/vision/artifacts/bad%23frag"


@pytest.mark.asyncio
async def test_approve_artifact_rejects_slash_before_http():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(
            "rhino_vision_approve", {"artifact_id": "bad/segment"},
        )
    mock.assert_not_called()
    assert "Error:" in result[0].text


@pytest.mark.asyncio
async def test_approve_artifact_encodes_non_slash_chars():
    """Non-slash special chars still survive round-trip through
    httplib's decode and reach managed, so they're encoded on our
    side rather than pre-rejected."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(
            "rhino_vision_approve", {"artifact_id": "bad?x=1"},
        )
    args, _ = mock.call_args
    assert args[0] == "/vision/artifacts/bad%3Fx%3D1/approve"
    assert args[1] == "POST"


@pytest.mark.asyncio
async def test_delete_artifact_rejects_slash_before_http():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(
            "rhino_vision_delete_artifact", {"artifact_id": "bad/segment"},
        )
    mock.assert_not_called()
    assert "Error:" in result[0].text


@pytest.mark.asyncio
async def test_delete_artifact_encodes_non_slash_chars():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(
            "rhino_vision_delete_artifact", {"artifact_id": "bad?x=1"},
        )
    args, _ = mock.call_args
    assert args[0] == "/vision/artifacts/bad%3Fx%3D1"
    assert args[1] == "DELETE"


# ─── port pass-through ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_port_extracted_and_forwarded_to_call_rhino():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool(
            "rhino_capture_depth", {"max_edge": 256, "port": 9950},
        )
    _, kwargs = mock.call_args
    assert kwargs.get("port") == 9950


# ─── tool_groups.py catalog contract ──────────────────────────────────


def test_tool_groups_vision_group_contains_all_eight():
    assert "vision" in tool_groups.TOOL_GROUPS
    got = set(tool_groups.TOOL_GROUPS["vision"])
    want = set(VISION_TOOL_NAMES)
    assert got == want, f"vision group = {got}, expected {want}"


def test_tool_groups_vision_readonly_excludes_mutators():
    assert "vision_readonly" in tool_groups.TOOL_GROUPS
    got = set(tool_groups.TOOL_GROUPS["vision_readonly"])
    want = set(VISION_READONLY_TOOL_NAMES)
    assert got == want, f"vision_readonly = {got}, expected {want}"
    # Sanity: readonly is a proper subset of the full group.
    assert got.issubset(set(tool_groups.TOOL_GROUPS["vision"]))
    # Sanity: mutators are excluded.
    mutators = {
        "rhino_render_view", "rhino_enhance_prompt", "rhino_capture_depth",
        "rhino_vision_approve", "rhino_vision_delete_artifact",
    }
    assert not (got & mutators), (
        f"vision_readonly leaked mutators: {got & mutators}"
    )


def test_tool_groups_vision_is_mcp_only():
    """Agents don't dispatch through the MCP path — they use the HTTP
    bridge directly per CLAUDE.md. Vision tools don't have
    BRIDGE_ROUTES entries in tool_dispatcher.py, so the groups must
    be blocked from agent request. This test fails if someone moves
    vision out of MCP_ONLY_GROUPS without adding the dispatcher
    routes — the regression gate demanded by Codex PR-6 scope review.
    """
    assert "vision" in tool_groups.MCP_ONLY_GROUPS
    assert "vision_readonly" in tool_groups.MCP_ONLY_GROUPS


def test_tool_groups_vision_entries_match_list_tools():
    """Every tool in the vision / vision_readonly groups must be a
    real MCP tool. Guards against typos in tool_groups.py."""
    import asyncio
    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}
    for group in ("vision", "vision_readonly"):
        for name in tool_groups.TOOL_GROUPS[group]:
            assert name in tool_names, (
                f"tool_groups['{group}'] references {name!r} which is "
                f"not registered in list_tools()"
            )
