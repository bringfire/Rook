from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server, targeting
from rook.agent import tool_dispatcher, tool_groups


RECONSTRUCTION_TOOL_NAMES = [
    "rhino_2d_to_3d_models",
    "rhino_2d_to_3d_submit",
    "rhino_2d_to_3d_jobs",
    "rhino_2d_to_3d_status",
    "rhino_2d_to_3d_cancel",
    "rhino_2d_to_3d_result",
    "rhino_2d_to_3d_import",
]

RECONSTRUCTION_READONLY_TOOL_NAMES = [
    "rhino_2d_to_3d_models",
    "rhino_2d_to_3d_jobs",
    "rhino_2d_to_3d_status",
    "rhino_2d_to_3d_result",
]


@pytest.fixture(autouse=True)
def fake_rhino_discovery(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])


@pytest.mark.asyncio
async def test_all_reconstruction_tools_registered():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    for name in RECONSTRUCTION_TOOL_NAMES:
        assert name in names


@pytest.mark.asyncio
async def test_reconstruction_submit_requires_source_artifact_id_only_for_identity():
    tools = await server.list_tools()
    submit = {t.name: t for t in tools}["rhino_2d_to_3d_submit"]

    assert set(submit.inputSchema.get("required", [])) == {"source_artifact_id"}
    assert "source_artifact_id" in submit.inputSchema["properties"]
    assert "path" not in submit.inputSchema["properties"]
    assert "image_path" not in submit.inputSchema["properties"]
    assert "local_path" not in submit.inputSchema["properties"]


@pytest.mark.asyncio
async def test_reconstruction_models_dispatches_get(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"models": []}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    await server.call_tool("rhino_2d_to_3d_models", {})

    assert calls == [("/reconstruction/2d-to-3d/models", "GET", None)]


@pytest.mark.asyncio
async def test_reconstruction_models_query_flags(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"models": []}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    await server.call_tool("rhino_2d_to_3d_models", {"include_experimental": True})

    assert calls == [("/reconstruction/2d-to-3d/models?include_experimental=true", "GET", None)]


@pytest.mark.asyncio
async def test_reconstruction_submit_dispatches_post_with_artifact_body():
    args_in = {
        "source_artifact_id": "12345678-1234-1234-1234-123456789abc",
        "source_role": "image",
        "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
        "preprocessing_chain": [],
        "options": {"enable_pbr": True, "enable_geometry": False},
    }
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"job_id": "X", "state": "queued"}}
        await server.call_tool("rhino_2d_to_3d_submit", args_in)
    args, _ = mock.call_args
    assert args == ("/reconstruction/2d-to-3d/jobs", "POST", args_in)


@pytest.mark.asyncio
async def test_reconstruction_status_encodes_job_id(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"job": {}}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    await server.call_tool("rhino_2d_to_3d_status", {"job_id": "bad?x=1"})

    assert calls[0][0] == "/reconstruction/2d-to-3d/jobs/bad%3Fx%3D1"
    assert calls[0][1:] == ("GET", None)


@pytest.mark.asyncio
async def test_reconstruction_cancel_dispatches_post_with_empty_body():
    guid = "12345678-1234-1234-1234-123456789abc"
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"state": "cancelled"}}
        await server.call_tool("rhino_2d_to_3d_cancel", {"job_id": guid})
    args, _ = mock.call_args
    assert args == (f"/reconstruction/2d-to-3d/jobs/{guid}/cancel", "POST", {})


@pytest.mark.asyncio
async def test_reconstruction_result_dispatches_get():
    guid = "12345678-1234-1234-1234-123456789abc"
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"result_artifact_id": "pkg"}}
        await server.call_tool("rhino_2d_to_3d_result", {"job_id": guid})
    args, _ = mock.call_args
    assert args == (f"/reconstruction/2d-to-3d/jobs/{guid}/result", "GET", None)


@pytest.mark.asyncio
async def test_reconstruction_jobs_limit_forwarded_as_query():
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"jobs": []}}
        await server.call_tool("rhino_2d_to_3d_jobs", {"limit": None})
    args, _ = mock.call_args
    assert args == ("/reconstruction/2d-to-3d/jobs", "GET", None)


def test_reconstruction_dispatcher_jobs_omits_null_limit():
    endpoint, method, data = tool_dispatcher._reconstruction_jobs({"limit": None})

    assert endpoint == "/reconstruction/2d-to-3d/jobs"
    assert method == "GET"
    assert data is None


@pytest.mark.asyncio
async def test_reconstruction_import_dispatches_owned_route():
    args_in = {
        "package_id": "12345678-1234-1234-1234-123456789abc",
        "targetLayer": "Rook::Reconstruction",
    }
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"imported_ids": []}}
        await server.call_tool("rhino_2d_to_3d_import", args_in)
    args, _ = mock.call_args
    assert args == ("/reconstruction/2d-to-3d/import", "POST", args_in)


@pytest.mark.parametrize("tool_name", [
    "rhino_2d_to_3d_status",
    "rhino_2d_to_3d_cancel",
    "rhino_2d_to_3d_result",
])
@pytest.mark.asyncio
async def test_reconstruction_path_param_tools_reject_slash_before_http(tool_name):
    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool(tool_name, {"job_id": "bad/segment"})
    mock.assert_not_called()
    assert "Error:" in result[0].text
    assert "job_id" in result[0].text


def test_reconstruction_dispatcher_routes_partitioned():
    bridge = set(tool_dispatcher.BRIDGE_ROUTES)
    transform = set(tool_dispatcher.TRANSFORM_FUNCTIONS)
    for name in RECONSTRUCTION_TOOL_NAMES:
        assert (name in bridge) ^ (name in transform)


def test_reconstruction_dispatcher_status_transform_encodes_job_id():
    endpoint, method, data = tool_dispatcher._reconstruction_status({"job_id": "bad?x=1"})
    assert endpoint == "/reconstruction/2d-to-3d/jobs/bad%3Fx%3D1"
    assert method == "GET"
    assert data is None


def test_reconstruction_tool_groups():
    assert set(tool_groups.TOOL_GROUPS["reconstruction"]) == set(RECONSTRUCTION_TOOL_NAMES)
    assert set(tool_groups.TOOL_GROUPS["reconstruction_readonly"]) == set(RECONSTRUCTION_READONLY_TOOL_NAMES)
    assert "reconstruction_readonly" in tool_groups.READONLY_ALLOWED_GROUPS
    assert "reconstruction" not in tool_groups.MCP_ONLY_GROUPS
    assert "reconstruction_readonly" not in tool_groups.MCP_ONLY_GROUPS
