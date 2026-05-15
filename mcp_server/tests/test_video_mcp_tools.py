"""MCP-layer tests for the Vision Video tools (PR-V4).

Scope:
- Pin all 7 video tools are registered in server.list_tools().
- Pin server.call_tool() dispatches each to the correct /vision/video/*
  endpoint with the correct HTTP method and body/query shape.
- Pin tool_dispatcher tier assignment: 3 in BRIDGE_ROUTES, 4 in
  TRANSFORM_FUNCTIONS. Pin the (endpoint, method, data) shape each
  transform returns.
- Pin server↔dispatcher PARITY: the same args produce the same raw
  call_rhino call_args via both paths. Patches BOTH module bindings
  (rook.server.call_rhino AND rook.agent.tool_dispatcher.call_rhino)
  because each module imports the symbol directly into its namespace.
- Pin path-param tools URL-encode job_id and pre-reject slash/backslash
  before any HTTP touch, on BOTH the server and dispatcher paths.
- Pin rhino_video_jobs limit handling preserves explicit None / empty /
  garbage end-to-end (call_rhino's GET-params builder would otherwise
  silently drop None and turn it into "absent → managed default 50").
- Pin tool_groups.py: 'video' / 'video_readonly' exist with the right
  contents and are NOT in MCP_ONLY_GROUPS (V4 ships agent-direct
  dispatch via BRIDGE_ROUTES + TRANSFORM_FUNCTIONS day-one).

Does NOT cover:
- The native /vision/video/* route contract itself — that's
  test_video_routes_live.py (live-Rhino, skips without Rhino).
- The C# managed limit-validation envelope shapes — those are
  Rook.Tests/Handlers/VideoOpHandlerTests.cs.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# Mirror the shim used by test_vision_mcp_tools.py so `rook.*` imports
# resolve against the checked-out source tree.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server, targeting
from rook.agent import tool_dispatcher, tool_groups


VIDEO_TOOL_NAMES = [
    "rhino_render_video",
    "rhino_video_status",
    "rhino_video_cancel",
    "rhino_video_result",
    "rhino_video_estimate",
    "rhino_video_jobs",
    "rhino_video_models",
]

VIDEO_READONLY_TOOL_NAMES = [
    "rhino_video_estimate",
    "rhino_video_status",
    "rhino_video_result",
    "rhino_video_jobs",
    "rhino_video_models",
]

# Tier assignment (locked by scope v3 §[v2] dispatcher tier table).
VIDEO_BRIDGE_TOOLS = {
    "rhino_render_video":   ("/vision/video/jobs", "POST"),
    "rhino_video_estimate": ("/vision/video/estimate", "POST"),
    "rhino_video_models":   ("/vision/video/models", "GET"),
}

VIDEO_TRANSFORM_TOOLS = {
    "rhino_video_status",
    "rhino_video_cancel",
    "rhino_video_result",
    "rhino_video_jobs",
}


@pytest.fixture(autouse=True)
def fake_rhino_discovery(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])


# ─── list_tools() registration ────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_video_tools_registered():
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    for name in VIDEO_TOOL_NAMES:
        assert name in tool_names, (
            f"Video tool {name!r} missing from list_tools(). "
            f"Registered video tools: "
            f"{sorted(n for n in tool_names if 'video' in n)}"
        )


@pytest.mark.asyncio
async def test_each_video_tool_has_nonempty_description_and_schema():
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}
    for name in VIDEO_TOOL_NAMES:
        tool = by_name[name]
        assert tool.description, f"{name} description is empty"
        assert tool.inputSchema, f"{name} inputSchema is empty"
        assert tool.inputSchema.get("type") == "object"


@pytest.mark.asyncio
async def test_video_tool_required_fields_match_managed_contract():
    """Each tool's 'required' list must match what VideoOpHandler.cs
    enforces — agents get the validation error at schema level instead
    of seeing a 400 from managed."""
    tools = await server.list_tools()
    by_name = {t.name: t for t in tools}

    expected = {
        # Submit + estimate share the same required-field set per
        # ParseGenerationRequest (model/mode/duration/resolution/
        # aspect_ratio/options).
        "rhino_render_video":   {"model", "mode", "duration_seconds",
                                 "resolution", "aspect_ratio", "options"},
        "rhino_video_estimate": {"model", "mode", "duration_seconds",
                                 "resolution", "aspect_ratio", "options"},
        "rhino_video_status":   {"job_id"},
        "rhino_video_cancel":   {"job_id"},
        "rhino_video_result":   {"job_id"},
        "rhino_video_jobs":     set(),
        "rhino_video_models":   set(),
    }
    for name, want in expected.items():
        got = set(by_name[name].inputSchema.get("required", []))
        assert got == want, f"{name} required={got}, expected {want}"


# ─── server.call_tool() dispatch — body-only / no-param ───────────────


@pytest.mark.asyncio
async def test_render_video_dispatches_post_with_body():
    args_in = {
        "model": "veo-3.0-fast-generate-001", "mode": "t2v",
        "duration_seconds": 8, "resolution": "720p",
        "aspect_ratio": "16:9",
        "options": {"person_generation": "dont_allow"},
        "prompt": "a sunset",
    }
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"job_id": "X", "state": "queued"}}
        await server.call_tool("rhino_render_video", args_in)
    args, kwargs = mock.call_args
    assert args == ("/vision/video/jobs", "POST", args_in)
    assert "port" in kwargs


@pytest.mark.asyncio
async def test_video_estimate_dispatches_post_with_body():
    args_in = {
        "model": "veo-3.0-fast-generate-001", "mode": "t2v",
        "duration_seconds": 8, "resolution": "720p",
        "aspect_ratio": "16:9",
        "options": {"person_generation": "dont_allow"},
    }
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"dollars_usd": 0.4}}
        await server.call_tool("rhino_video_estimate", args_in)
    args, _ = mock.call_args
    assert args == ("/vision/video/estimate", "POST", args_in)


@pytest.mark.asyncio
async def test_video_models_dispatches_get_no_body():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"models": []}}
        await server.call_tool("rhino_video_models", {})
    args, _ = mock.call_args
    assert args == ("/vision/video/models", "GET", None)


# ─── server.call_tool() dispatch — path-param ─────────────────────────


@pytest.mark.asyncio
async def test_video_status_encodes_path_id_valid_guid():
    guid = "12345678-1234-1234-1234-123456789abc"
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool("rhino_video_status", {"job_id": guid})
    args, _ = mock.call_args
    assert args == (f"/vision/video/jobs/{guid}", "GET", None)


@pytest.mark.asyncio
async def test_video_cancel_dispatches_post_with_empty_body():
    """Empty body must be {} not None — the dispatcher transform
    matches this exactly so the parity test holds (None would be
    accepted by call_rhino but document-context handling could
    synthesize a body, silently diverging from the MCP path)."""
    guid = "12345678-1234-1234-1234-123456789abc"
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool("rhino_video_cancel", {"job_id": guid})
    args, _ = mock.call_args
    assert args == (f"/vision/video/jobs/{guid}/cancel", "POST", {})


@pytest.mark.asyncio
async def test_video_result_encodes_path_id_valid_guid():
    guid = "12345678-1234-1234-1234-123456789abc"
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {}}
        await server.call_tool("rhino_video_result", {"job_id": guid})
    args, _ = mock.call_args
    assert args == (f"/vision/video/jobs/{guid}/result", "GET", None)


@pytest.mark.parametrize("tool_name,suffix", [
    ("rhino_video_status", ""),
    ("rhino_video_cancel", "/cancel"),
    ("rhino_video_result", "/result"),
])
@pytest.mark.asyncio
async def test_path_param_tools_reject_slash_before_http(tool_name, suffix):
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(tool_name, {"job_id": "bad/segment"})
    mock.assert_not_called()
    assert "Error:" in result[0].text
    assert "'/'" in result[0].text and "job_id" in result[0].text


@pytest.mark.parametrize("tool_name", [
    "rhino_video_status", "rhino_video_cancel", "rhino_video_result",
])
@pytest.mark.asyncio
async def test_path_param_tools_reject_backslash_before_http(tool_name):
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(tool_name, {"job_id": r"bad\segment"})
    mock.assert_not_called()
    assert "Error:" in result[0].text


@pytest.mark.parametrize("tool_name", [
    "rhino_video_status", "rhino_video_cancel", "rhino_video_result",
])
@pytest.mark.asyncio
async def test_path_param_tools_reject_empty_id(tool_name):
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(tool_name, {"job_id": ""})
    mock.assert_not_called()
    assert "Error:" in result[0].text


# ─── server.call_tool() dispatch — rhino_video_jobs limit folding ─────


@pytest.mark.asyncio
async def test_video_jobs_no_limit_hits_bare_endpoint():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"jobs": []}}
        await server.call_tool("rhino_video_jobs", {})
    args, _ = mock.call_args
    assert args == ("/vision/video/jobs", "GET", None)


@pytest.mark.asyncio
async def test_video_jobs_int_limit_folded_into_query():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"jobs": []}}
        await server.call_tool("rhino_video_jobs", {"limit": 25})
    args, _ = mock.call_args
    assert args == ("/vision/video/jobs?limit=25", "GET", None)


@pytest.mark.asyncio
async def test_video_jobs_explicit_none_limit_forwarded_as_empty():
    """If the caller passes limit=None explicitly, we must NOT silently
    drop it (call_rhino's GET-params builder would do that, then
    managed defaults to 50). Forward as empty string so managed
    rejects with InvalidRequest field='limit'."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": False, "data": {"code": "invalid_request"}}
        await server.call_tool("rhino_video_jobs", {"limit": None})
    args, _ = mock.call_args
    assert args == ("/vision/video/jobs?limit=", "GET", None)


@pytest.mark.asyncio
async def test_video_jobs_string_limit_forwarded_unchanged():
    """Bad shape — forward to managed verbatim so the typed
    InvalidRequest field='limit' envelope returns."""
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": False, "data": {"code": "invalid_request"}}
        await server.call_tool("rhino_video_jobs", {"limit": "abc"})
    args, _ = mock.call_args
    assert args == ("/vision/video/jobs?limit=abc", "GET", None)


# ─── tool_dispatcher tier assignment ──────────────────────────────────


@pytest.mark.parametrize("name,expected", list(VIDEO_BRIDGE_TOOLS.items()))
def test_video_bridge_tools_in_BRIDGE_ROUTES(name, expected):
    assert name in tool_dispatcher.BRIDGE_ROUTES, (
        f"{name!r} missing from BRIDGE_ROUTES — agents cannot dispatch it."
    )
    assert tool_dispatcher.BRIDGE_ROUTES[name] == expected


@pytest.mark.parametrize("name", sorted(VIDEO_TRANSFORM_TOOLS))
def test_video_transform_tools_in_TRANSFORM_FUNCTIONS(name):
    assert name in tool_dispatcher.TRANSFORM_FUNCTIONS, (
        f"{name!r} missing from TRANSFORM_FUNCTIONS — agents cannot dispatch it."
    )


def test_video_tools_partition_bridge_and_transform_exclusively():
    """Every video tool is in EXACTLY ONE of BRIDGE_ROUTES /
    TRANSFORM_FUNCTIONS — never both, never neither."""
    bridge = set(tool_dispatcher.BRIDGE_ROUTES.keys())
    transform = set(tool_dispatcher.TRANSFORM_FUNCTIONS.keys())
    for name in VIDEO_TOOL_NAMES:
        in_bridge = name in bridge
        in_transform = name in transform
        assert in_bridge ^ in_transform, (
            f"{name!r}: in BRIDGE_ROUTES={in_bridge}, "
            f"in TRANSFORM_FUNCTIONS={in_transform} — must be exactly one."
        )


# ─── tool_dispatcher transform shape ──────────────────────────────────


def test_transform_video_status_valid_guid():
    guid = "12345678-1234-1234-1234-123456789abc"
    endpoint, method, data = tool_dispatcher._video_status({"job_id": guid})
    assert endpoint == f"/vision/video/jobs/{guid}"
    assert method == "GET"
    assert data is None


def test_transform_video_cancel_valid_guid():
    guid = "12345678-1234-1234-1234-123456789abc"
    endpoint, method, data = tool_dispatcher._video_cancel({"job_id": guid})
    assert endpoint == f"/vision/video/jobs/{guid}/cancel"
    assert method == "POST"
    assert data == {}, "cancel body MUST be {} (matches server.call_tool path)"


def test_transform_video_result_valid_guid():
    guid = "12345678-1234-1234-1234-123456789abc"
    endpoint, method, data = tool_dispatcher._video_result({"job_id": guid})
    assert endpoint == f"/vision/video/jobs/{guid}/result"
    assert method == "GET"
    assert data is None


def test_transform_video_jobs_no_limit():
    endpoint, method, data = tool_dispatcher._video_jobs({})
    assert endpoint == "/vision/video/jobs"
    assert method == "GET"
    assert data is None


def test_transform_video_jobs_int_limit():
    endpoint, method, data = tool_dispatcher._video_jobs({"limit": 25})
    assert endpoint == "/vision/video/jobs?limit=25"
    assert method == "GET"
    assert data is None


def test_transform_video_jobs_explicit_none_limit():
    """Same end-to-end null preservation as the server.call_tool path."""
    endpoint, method, data = tool_dispatcher._video_jobs({"limit": None})
    assert endpoint == "/vision/video/jobs?limit="
    assert method == "GET"
    assert data is None


def test_transform_video_jobs_string_limit_forwarded():
    endpoint, method, data = tool_dispatcher._video_jobs({"limit": "abc"})
    assert endpoint == "/vision/video/jobs?limit=abc"
    assert data is None


@pytest.mark.parametrize("transform_name", [
    "_video_status", "_video_cancel", "_video_result",
])
def test_transform_path_param_rejects_slash(transform_name):
    fn = getattr(tool_dispatcher, transform_name)
    endpoint, method, data = fn({"job_id": "bad/segment"})
    assert endpoint is None, "slash-bearing job_id must pre-reject"
    assert isinstance(data, dict)
    assert data.get("success") is False
    assert data.get("_pre_dispatch_failure") is True, (
        "Pre-dispatch error must set _pre_dispatch_failure=True so "
        "ToolDispatcher's verification path skips prompt-poll annotation."
    )


@pytest.mark.parametrize("transform_name", [
    "_video_status", "_video_cancel", "_video_result",
])
def test_transform_path_param_rejects_backslash(transform_name):
    fn = getattr(tool_dispatcher, transform_name)
    endpoint, method, data = fn({"job_id": r"bad\segment"})
    assert endpoint is None
    assert data.get("_pre_dispatch_failure") is True


@pytest.mark.parametrize("transform_name", [
    "_video_status", "_video_cancel", "_video_result",
])
def test_transform_path_param_rejects_empty(transform_name):
    fn = getattr(tool_dispatcher, transform_name)
    endpoint, method, data = fn({"job_id": ""})
    assert endpoint is None
    assert data.get("_pre_dispatch_failure") is True


def test_transform_path_param_encodes_special_chars():
    """Non-slash special chars survive http decoding round-trip — encode
    rather than reject. Mirrors image-side _encode_vision_artifact_id
    posture."""
    endpoint, _, _ = tool_dispatcher._video_status({"job_id": "bad?x=1"})
    assert endpoint == "/vision/video/jobs/bad%3Fx%3D1"


# ─── server ↔ dispatcher PARITY ───────────────────────────────────────
#
# Codex round 2: patch BOTH module bindings. rook.server and
# rook.agent.tool_dispatcher each `from ..bridge import call_rhino`,
# so they hold separate references. Patching one alone misses the
# other.
#
# Normalization: server.call_tool passes port as a kwarg; the
# dispatcher passes port positionally. Both call call_rhino with the
# same (endpoint, method, data, port) but the call_args shape differs
# (kwarg vs positional). Normalize to (endpoint, method, data, port)
# tuples before comparing so the test asserts WIRE equivalence, not
# Python-call-shape equivalence (which is what the user's scope-pass
# caveat specifically warned about).


def _normalize_call_rhino_args(call_args) -> tuple:
    """Extract (endpoint, method, data, port) regardless of whether
    port was passed positionally or as a kwarg.

    call_rhino(endpoint, method='POST', data=None, port=None) — the
    first three are sometimes positional-only at the call site, port
    is sometimes positional and sometimes kwarg. Normalize both shapes
    to a 4-tuple so parity asserts the wire request, not the Python
    invocation style."""
    args = list(call_args.args)
    kwargs = dict(call_args.kwargs)

    # endpoint is always positional[0]
    endpoint = args[0]
    # method default 'GET' (matches call_rhino signature default in bridge.py)
    method = args[1] if len(args) >= 2 else kwargs.get("method", "GET")
    # data default None
    data = args[2] if len(args) >= 3 else kwargs.get("data", None)
    # port default None
    port = args[3] if len(args) >= 4 else kwargs.get("port", None)
    return (endpoint, method, data, port)


async def _both_paths_normalized(name: str, args_in: dict) -> tuple[tuple, tuple]:
    """Dispatch the same args via BOTH server.call_tool and
    ToolDispatcher.dispatch; return normalized 4-tuples for parity
    comparison."""
    server_mock = AsyncMock(return_value={"success": True, "data": {}})
    disp_mock = AsyncMock(return_value={"success": True, "data": {}})
    with patch.object(server, "call_rhino", new=server_mock), \
         patch.object(tool_dispatcher, "call_rhino", new=disp_mock):
        await server.call_tool(name, dict(args_in))
        await tool_dispatcher.ToolDispatcher().dispatch(name, dict(args_in))
    return (
        _normalize_call_rhino_args(server_mock.call_args),
        _normalize_call_rhino_args(disp_mock.call_args),
    )


def _assert_parity(server_tuple: tuple, dispatcher_tuple: tuple, name: str) -> None:
    assert server_tuple == dispatcher_tuple, (
        f"server↔dispatcher wire-request drift on {name}:\n"
        f"  server     = {server_tuple}\n"
        f"  dispatcher = {dispatcher_tuple}"
    )


@pytest.mark.asyncio
async def test_parity_render_video():
    args_in = {
        "model": "veo-3.0-fast-generate-001", "mode": "t2v",
        "duration_seconds": 8, "resolution": "720p",
        "aspect_ratio": "16:9",
        "options": {"person_generation": "dont_allow"},
    }
    s, d = await _both_paths_normalized("rhino_render_video", args_in)
    _assert_parity(s, d, "rhino_render_video")


@pytest.mark.asyncio
async def test_parity_video_estimate():
    args_in = {
        "model": "veo-3.0-fast-generate-001", "mode": "t2v",
        "duration_seconds": 8, "resolution": "720p",
        "aspect_ratio": "16:9",
        "options": {"person_generation": "dont_allow"},
    }
    s, d = await _both_paths_normalized("rhino_video_estimate", args_in)
    _assert_parity(s, d, "rhino_video_estimate")


@pytest.mark.asyncio
async def test_parity_video_models():
    s, d = await _both_paths_normalized("rhino_video_models", {})
    _assert_parity(s, d, "rhino_video_models")


@pytest.mark.asyncio
async def test_parity_video_status():
    guid = "12345678-1234-1234-1234-123456789abc"
    s, d = await _both_paths_normalized("rhino_video_status", {"job_id": guid})
    _assert_parity(s, d, "rhino_video_status")


@pytest.mark.asyncio
async def test_parity_video_cancel():
    guid = "12345678-1234-1234-1234-123456789abc"
    s, d = await _both_paths_normalized("rhino_video_cancel", {"job_id": guid})
    _assert_parity(s, d, "rhino_video_cancel")


@pytest.mark.asyncio
async def test_parity_video_result():
    guid = "12345678-1234-1234-1234-123456789abc"
    s, d = await _both_paths_normalized("rhino_video_result", {"job_id": guid})
    _assert_parity(s, d, "rhino_video_result")


@pytest.mark.asyncio
async def test_parity_video_jobs_no_limit():
    s, d = await _both_paths_normalized("rhino_video_jobs", {})
    _assert_parity(s, d, "rhino_video_jobs (no limit)")


@pytest.mark.asyncio
async def test_parity_video_jobs_int_limit():
    s, d = await _both_paths_normalized("rhino_video_jobs", {"limit": 25})
    _assert_parity(s, d, "rhino_video_jobs (int)")


@pytest.mark.asyncio
async def test_parity_video_jobs_none_limit():
    s, d = await _both_paths_normalized("rhino_video_jobs", {"limit": None})
    _assert_parity(s, d, "rhino_video_jobs (None)")


@pytest.mark.asyncio
async def test_parity_video_jobs_string_limit():
    s, d = await _both_paths_normalized("rhino_video_jobs", {"limit": "abc"})
    _assert_parity(s, d, "rhino_video_jobs (str)")


# ─── tool_groups.py catalog contract ──────────────────────────────────


def test_tool_groups_video_group_contains_all_seven():
    assert "video" in tool_groups.TOOL_GROUPS
    got = set(tool_groups.TOOL_GROUPS["video"])
    want = set(VIDEO_TOOL_NAMES)
    assert got == want, f"video group = {got}, expected {want}"


def test_tool_groups_video_readonly_excludes_mutators():
    assert "video_readonly" in tool_groups.TOOL_GROUPS
    got = set(tool_groups.TOOL_GROUPS["video_readonly"])
    want = set(VIDEO_READONLY_TOOL_NAMES)
    assert got == want, f"video_readonly = {got}, expected {want}"
    assert got.issubset(set(tool_groups.TOOL_GROUPS["video"]))
    mutators = {"rhino_render_video", "rhino_video_cancel"}
    assert not (got & mutators), (
        f"video_readonly leaked mutators: {got & mutators}"
    )


def test_tool_groups_video_NOT_in_MCP_ONLY_GROUPS():
    """V4 ships agent-direct dispatch via BRIDGE_ROUTES +
    TRANSFORM_FUNCTIONS. Both groups must be reachable by agents,
    so neither belongs in MCP_ONLY_GROUPS. Regression gate: if a
    future change adds them, agents would silently lose access to
    a feature they had on day one."""
    assert "video" not in tool_groups.MCP_ONLY_GROUPS, (
        "video is agent-direct via tool_dispatcher — must NOT be MCP-only."
    )
    assert "video_readonly" not in tool_groups.MCP_ONLY_GROUPS


def test_tool_groups_video_entries_match_list_tools():
    """Every tool in the video / video_readonly groups must be a
    real MCP tool. Guards against typos in tool_groups.py."""
    import asyncio
    tools = asyncio.run(server.list_tools())
    tool_names = {t.name for t in tools}
    for group in ("video", "video_readonly"):
        for name in tool_groups.TOOL_GROUPS[group]:
            assert name in tool_names, (
                f"tool_groups['{group}'] references {name!r} which is "
                f"not registered in list_tools()"
            )
