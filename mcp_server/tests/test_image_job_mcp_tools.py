"""Configured image/video admission through real MCP gateway and dispatch paths."""
import json
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import pytest

# The managed join executes this test-only capture entry point in a subprocess.
# Isolate writable runtime data before importing production modules.
if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[2]
    data = Path(sys.argv[3]).resolve().parent / "gateway-data"
    os.environ.update(ROOK_INSTALL_ROOT=str(repository), ROOK_DATA_DIR=str(data),
                      DSPY_CACHEDIR=str(data / "dspy-cache"), ROOK_MODE="dev")
    sys.path.insert(0, str(repository / "mcp_server" / "src"))

from rook import server, targeting
from rook.agent import tool_dispatcher, tool_groups


IMAGE_ROUTES = {
    "rhino_image_models": ("/vision/image/models", "GET", None),
    "rhino_image_estimate": ("/vision/image/estimate", "POST", {"model": "configured-image"}),
    "rhino_generate_image": ("/vision/image/jobs", "POST", {"model": "configured-image"}),
    "rhino_image_status": ("/vision/image/jobs/12345678-1234-1234-1234-123456789abc", "GET", None),
    "rhino_image_result": ("/vision/image/jobs/12345678-1234-1234-1234-123456789abc/result", "GET", None),
    "rhino_image_cancel": ("/vision/image/jobs/12345678-1234-1234-1234-123456789abc/cancel", "POST", {}),
    "rhino_image_jobs": ("/vision/image/jobs", "GET", None),
}
READONLY = {"rhino_image_models", "rhino_image_estimate", "rhino_image_status", "rhino_image_result", "rhino_image_jobs"}


@pytest.fixture(autouse=True)
def isolated_surface(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])
    server._reset_capability_index_cache()
    yield
    server._reset_capability_index_cache()


def decoded(response):
    return json.loads(response[0].text.removeprefix("Error: "))


@pytest.mark.asyncio
async def test_image_inventory_profiles_groups_and_lifecycle(monkeypatch):
    full = {t.name for t in await server.list_tools()}
    assert set(IMAGE_ROUTES) <= full
    assert set(IMAGE_ROUTES) <= set(tool_groups.TOOL_GROUPS["vision"])
    assert READONLY <= set(tool_groups.TOOL_GROUPS["vision_readonly"])
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "readonly")
    readonly = {t.name for t in await server.list_tools()}
    assert set(IMAGE_ROUTES) & readonly == READONLY
    for name in IMAGE_ROUTES:
        policy = targeting.policy_for_tool(name)
        assert policy.requires_rhino
        assert policy.risk == ("read" if name in READONLY else "mutate")
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
        for name in ("rhino_generate_image", "rhino_image_cancel"):
            assert decoded(await server.call_tool(name, {}))["code"] == "tool_profile_blocked"
        call.assert_not_awaited()
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    lean = {t.name for t in await server.list_tools()}
    assert set(IMAGE_ROUTES).isdisjoint(lean)
    assert "rook_tools_call" in lean


@pytest.mark.asyncio
@pytest.mark.parametrize("name", IMAGE_ROUTES)
async def test_image_route_methods_and_internal_dispatch_parity(name, monkeypatch):
    endpoint, method, body = IMAGE_ROUTES[name]
    args = body if name in {"rhino_image_estimate", "rhino_generate_image"} else (
        {"job_id": "12345678-1234-1234-1234-123456789abc"} if name in {"rhino_image_status", "rhino_image_result", "rhino_image_cancel"} else {})
    for module in (server, tool_dispatcher):
        with patch.object(module, "call_rhino", new_callable=AsyncMock) as call:
            call.return_value = {"success": True, "data": {"state": "queued"}}
            if module is server:
                await server.call_tool(name, args)
            else:
                await tool_dispatcher.ToolDispatcher().dispatch(name, args)
            assert call.call_args.args[:3] == (endpoint, method, body)
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
        call.return_value = {"success": True, "data": {"forwarded": True}}
        response = await server.call_tool("rook_tools_call", {"name": name, "arguments": args})
        assert decoded(response) == {"forwarded": True}
        assert call.call_args.args[:3] == (endpoint, method, body)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["rhino_image_estimate", "rhino_generate_image", "rhino_video_estimate", "rhino_render_video"])
@pytest.mark.parametrize("extras", [
    {},
    {"operation": "text_to_image", "quote_fingerprint": "fal1:" + "a" * 64, "max_estimated_cost_usd": 0.000001},
    {"duration_seconds": 1.5, "seed": 9007199254740991, "options": {"enabled": False, "strength": 0, "guidance": 7.5}},
    {"duration_seconds": -1000000000, "seed": -9007199254740991, "options": {"small": 0.000001}},
    {"media": [
        {"semantic_role": "reference_image", "artifact_id": "00000000-0000-0000-0000-000000000001", "artifact_role": "input_image"},
        {"semantic_role": "reference_image", "artifact_id": "00000000-0000-0000-0000-000000000002", "artifact_role": "generated_image"},
    ]},
])
async def test_gateway_preserves_configured_omissions_types_and_confirmation(name, extras, monkeypatch):
    # The real gateway validates the schema before re-entering dispatch.
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "lean")
    args = {"model": "configured-model", **extras}
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
        call.return_value = {"success": True, "data": {"forwarded": True}}
        response = await server.call_tool("rook_tools_call", {"name": name, "arguments": args})
        assert decoded(response) == {"forwarded": True}
        assert call.call_args.args[2] == args


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("duration_seconds", None), ("duration_seconds", "1.5"), ("duration_seconds", True), ("duration_seconds", 1000000001), ("seed", 1.5), ("seed", 9007199254740992), ("options", None), ("media", None), ("operation", None)])
async def test_gateway_rejects_wrong_common_types_and_out_of_range(field, value):
    for name in ("rhino_image_estimate", "rhino_generate_image", "rhino_video_estimate", "rhino_render_video"):
        with patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
            response = await server.call_tool("rook_tools_call", {"name": name, "arguments": {"model": "configured", field: value}})
            assert decoded(response)["error"] == "invalid_arguments"
            call.assert_not_awaited()


@pytest.mark.asyncio
async def test_gateway_forwards_legacy_omission_and_preserves_managed_error():
    managed_error = {"code": "invalid_request", "field": "mode", "message": "mode is required"}
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
        call.return_value = {"success": False, "data": managed_error}
        response = await server.call_tool("rook_tools_call", {"name": "rhino_render_video", "arguments": {"model": "veo-3.0-fast-generate-001"}})
        assert decoded(response) == managed_error
        call.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["rhino_image_estimate", "rhino_generate_image", "rhino_video_estimate", "rhino_render_video"])
async def test_direct_paths_preserve_explicit_null_for_managed_validation(name):
    args = {"model": "configured", "prompt": None, "options": None, "seed": None, "max_estimated_cost_usd": None}
    for module in (server, tool_dispatcher):
        with patch.object(module, "call_rhino", new_callable=AsyncMock) as call:
            call.return_value = {"success": False, "data": {"code": "invalid_request", "field": "prompt"}}
            if module is server:
                await server.call_tool(name, args)
            else:
                await tool_dispatcher.ToolDispatcher().dispatch(name, args)
            assert call.call_args.args[2] == args


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["rhino_image_cancel", "rhino_video_cancel"])
@pytest.mark.parametrize("success", [True, False])
async def test_cancel_preserves_local_and_remote_metadata_on_error(name, success):
    data = {"job_id": "12345678-1234-1234-1234-123456789abc", "state": "canceled", "cancellation": {"local_stopped": True, "remote_disposition": "already_completed", "remote_terminal_state": "Completed", "automatic": False, "remote_cancellation_confirmed": False}}
    if not success:
        data.update(code="provider_error", error={"message": "cancel failed"}, detail_code="fal_cancel_failed")
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
        call.return_value = {"success": success, "data": data}
        response = await server.call_tool(name, {"job_id": data["job_id"]})
        assert decoded(response) == data


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["rhino_image_status", "rhino_image_result", "rhino_image_cancel"])
@pytest.mark.parametrize("job_id", [None, "", "a/b", "a\\b"])
async def test_image_path_ids_rejected_before_http(name, job_id):
    for module in (server, tool_dispatcher):
        with patch.object(module, "call_rhino", new_callable=AsyncMock) as call:
            response = await server.call_tool(name, {"job_id": job_id}) if module is server else await tool_dispatcher.ToolDispatcher().dispatch(name, {"job_id": job_id})
            assert "job_id" in str(response)
            call.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("limit,query", [(None, ""), ("", ""), ("bad", "bad"), (3, "3")])
async def test_image_history_forwards_explicit_limit(limit, query):
    for module in (server, tool_dispatcher):
        with patch.object(module, "call_rhino", new_callable=AsyncMock) as call:
            call.return_value = {"success": True, "data": {"jobs": []}}
            if module is server:
                await server.call_tool("rhino_image_jobs", {"limit": limit})
            else:
                await tool_dispatcher.ToolDispatcher().dispatch("rhino_image_jobs", {"limit": limit})
            assert call.call_args.args[:3] == ("/vision/image/jobs?limit=" + query, "GET", None)


@pytest.mark.asyncio
async def test_catalog_contents_do_not_change_inventory():
    before = {t.name: t.inputSchema for t in await server.list_tools()}
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
        for catalog in ([], [{"model_id": "new-model", "operations": [{"operation_id": "text_to_image"}]}]):
            call.return_value = {"success": True, "data": {"models": catalog, "catalog_diagnostics": []}}
            assert decoded(await server.call_tool("rhino_image_models", {}))["models"] == catalog
            assert {t.name: t.inputSchema for t in await server.list_tools()} == before


async def capture_gateway_request(input_path, output_path):
    """Export the real gateway's forwarded JSON for the managed fake-fal join.

    This intercepts only the HTTP boundary, after actual schema admission and
    target dispatch. It never contacts Rhino or a paid provider.
    """
    request = json.loads(Path(input_path).read_text(encoding="utf-8"))
    os.environ["ROOK_MCP_TOOL_PROFILE"] = "lean"
    os.environ.pop("ROOK_MCP_TARGET_MODE", None)
    server._reset_capability_index_cache()
    with patch.object(targeting, "discover_instances", return_value=[
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ]), patch.object(server, "call_rhino", new_callable=AsyncMock) as call:
        call.return_value = {"success": True, "data": {"forwarded": True}}
        response = await server.call_tool("rook_tools_call", request)
        assert decoded(response) == {"forwarded": True}, response
        call.assert_awaited_once()
        endpoint, method, payload = call.await_args.args[:3]
        index = await server._get_capability_index()
        result = {"name": request["name"], "endpoint": endpoint, "method": method,
                  "arguments": payload, "input_schema": index.read(request["name"])["input_schema"]}
        Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import asyncio

    assert len(sys.argv) == 4 and sys.argv[1] == "--capture-gateway"
    asyncio.run(capture_gateway_request(sys.argv[2], sys.argv[3]))
