"""Direct MCP-path safety tests for rhino_execute."""

import json

import pytest

from rook import server
from rook import targeting


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


@pytest.fixture
def patched_server(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setattr(targeting, "discover_instances", lambda: [{
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 7101,
        "pluginType": "native",
        "documentName": "SafetyFixture.3dm",
    }])
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())
    yield
    targeting.reset_targeting_state_for_tests()


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


@pytest.mark.asyncio
async def test_rhino_command_refusal_advisory_survives_existing_error_text_transport(monkeypatch, patched_server):
    from rook import server

    async def fail_call_rhino(*args, **kwargs):
        raise AssertionError("rhino_command refusal must happen before call_rhino")

    monkeypatch.setattr(server, "call_rhino", fail_call_rhino)
    monkeypatch.setattr(server.command_learner, "knowledge_store", None)

    response = await server.call_tool("rhino_command", {"command": "_Line"})

    assert response[0].text.startswith("Error: ")
    data = json.loads(response[0].text.removeprefix("Error: "))
    assert data["error_code"] == "run_script_safety_refusal"
    assert data["retry_allowed"] is False
    assert data["candidate_tools"][0]["tool"] == "rhino_create"
