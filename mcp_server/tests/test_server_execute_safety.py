"""Direct MCP-path safety tests for rhino_execute."""

import pytest

from rook import server


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


@pytest.fixture
def patched_server(monkeypatch):
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())


@pytest.mark.asyncio
async def test_rhino_execute_blocks_interactive_rs_call_on_direct_mcp_path(monkeypatch, patched_server):
    call_count = 0

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        nonlocal call_count
        call_count += 1
        return {"success": True, "data": {"unexpected": True}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "rhino_execute",
        {"code": "import rhinoscriptsyntax as rs\nrs.GetPoint('Pick a point')"},
    )

    assert call_count == 0
    assert "interactive rhino input call" in response[0].text.lower()
    assert "not sent to rhino" in response[0].text.lower()


@pytest.mark.asyncio
async def test_rhino_execute_allows_non_blocking_code_on_direct_mcp_path(monkeypatch, patched_server):
    call_args: list[tuple[str, str, dict | None, int | None]] = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        call_args.append((route, method, payload, port))
        return {"success": True, "data": {"ok": True}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool(
        "rhino_execute",
        {"code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)"},
    )

    assert call_args == [
        ("/execute", "POST", {"code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)"}, None)
    ]
    assert '"ok": true' in response[0].text.lower()
