import pytest

from rook import server
from rook.agent import tool_dispatcher as dispatcher_module
from rook.agent.tool_dispatcher import ToolDispatcher


@pytest.mark.asyncio
async def test_readiness_tools_advertise_exact_inputs():
    tools = {tool.name: tool for tool in await server.list_tools()}

    readiness = tools["gh_solve_readiness"]
    wait = tools["gh_wait_for_solve_readiness"]
    snapshot = tools["gh_snapshot"]

    assert readiness.inputSchema["required"] == ["readiness_receipt_id"]
    assert readiness.inputSchema["properties"]["readiness_receipt_id"] == {
        "type": "string",
        "minLength": 1,
        "description": "Opaque solve readiness receipt ID returned by gh_set_value.",
    }
    assert wait.inputSchema["required"] == ["readiness_receipt_id"]
    assert wait.inputSchema["properties"]["timeout_ms"] == {
        "type": "integer",
        "default": 10_000,
        "minimum": 1,
        "maximum": 300_000,
        "description": "Maximum managed wait in milliseconds.",
    }
    assert snapshot.inputSchema["properties"]["readiness_receipt_id"] == {
        "type": "string",
        "minLength": 1,
        "description": "Optional solve-readiness receipt that fences this snapshot to the admitted solved state.",
    }


@pytest.mark.asyncio
async def test_snapshot_preserves_exact_fenced_request_through_canonical_and_direct_dispatch(
    monkeypatch,
):
    request = {
        "readiness_receipt_id": "opaque",
        "include_data": True,
        "max_preview_items": 17,
    }
    calls = []

    async def fake_server_call(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(("canonical", route, method, payload, port))
        return {"success": True, "data": {"source": "canonical"}}

    async def fake_direct_call(route, method="GET", payload=None, port=None, **kwargs):
        calls.append(("direct", route, method, payload, port))
        return {"success": True, "data": {"source": "direct"}}

    monkeypatch.setattr(server, "call_rhino", fake_server_call)
    canonical = await server._call_tool_dispatch("gh_snapshot", {**request, "port": 6011})
    monkeypatch.setattr(dispatcher_module, "call_rhino", fake_direct_call)
    direct = await ToolDispatcher(port=6011).dispatch("gh_snapshot", dict(request))

    assert canonical["success"] is True
    assert direct["success"] is True
    assert calls == [
        ("canonical", "/gh/snapshot", "POST", request, 6011),
        ("direct", "/gh/snapshot", "POST", request, 6011),
    ]


@pytest.mark.asyncio
async def test_wait_dispatches_with_a_transport_deadline_that_covers_the_managed_wait(monkeypatch):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None, timeout=None):
        calls.append((route, method, payload, timeout))
        return {"success": True, "data": {"wait_status": "ready"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    result = await server._call_tool_dispatch(
        "gh_wait_for_solve_readiness",
        {"readiness_receipt_id": "opaque", "timeout_ms": 10_000},
    )

    assert result["success"] is True
    route, method, payload, timeout = calls[-1]
    assert (route, method, payload) == (
        "/gh/wait-for-solve-readiness",
        "POST",
        {"readiness_receipt_id": "opaque", "timeout_ms": 10_000},
    )
    assert timeout.connect == 5.0
    assert timeout.read == 15.0
    assert timeout.write == 60.0
    assert timeout.pool == 5.0

    await server._call_tool_dispatch(
        "gh_wait_for_solve_readiness",
        {"readiness_receipt_id": "opaque", "timeout_ms": 300_000},
    )
    max_timeout = calls[-1][-1]
    assert max_timeout.connect == 5.0
    assert max_timeout.read == 305.0
    assert max_timeout.write == 60.0
    assert max_timeout.pool == 5.0


@pytest.mark.asyncio
async def test_inspect_output_forwards_readiness_receipt_only_when_supplied(monkeypatch):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {"success": True, "data": {"value": 7.5}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    await server._call_tool_dispatch(
        "gh_inspect_output",
        {"guid": "COMPONENT", "param": "A"},
    )
    await server._call_tool_dispatch(
        "gh_inspect_output",
        {
            "guid": "COMPONENT",
            "param": "A",
            "readiness_receipt_id": "opaque",
        },
    )

    assert calls == [
        ("/gh/inspect-output", "GET", {"guid": "COMPONENT", "param": "A"}, None),
        (
            "/gh/inspect-output",
            "GET",
            {
                "guid": "COMPONENT",
                "param": "A",
                "readiness_receipt_id": "opaque",
            },
            None,
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("receipt_id", ["", "   "])
async def test_inspect_output_forwards_explicit_blank_receipt_for_managed_rejection(
    monkeypatch, receipt_id
):
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {"success": False, "data": {"error": "readiness_receipt_id_invalid"}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    result = await server._call_tool_dispatch(
        "gh_inspect_output",
        {
            "guid": "COMPONENT",
            "param": "A",
            "readiness_receipt_id": receipt_id,
        },
    )

    assert result == {
        "success": False,
        "data": {"error": "readiness_receipt_id_invalid"},
    }
    assert calls == [
        (
            "/gh/inspect-output",
            "GET",
            {
                "guid": "COMPONENT",
                "param": "A",
                "readiness_receipt_id": receipt_id,
            },
            None,
        )
    ]
