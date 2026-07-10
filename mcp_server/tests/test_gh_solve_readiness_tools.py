import pytest

from rook import server


@pytest.mark.asyncio
async def test_readiness_tools_advertise_exact_inputs():
    tools = {tool.name: tool for tool in await server.list_tools()}

    readiness = tools["gh_solve_readiness"]
    wait = tools["gh_wait_for_solve_readiness"]

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
