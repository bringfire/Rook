import json
from types import SimpleNamespace

import pytest

from rook import server, targeting


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


def _decode_response(response):
    text = response[0].text
    if text.startswith("Error: "):
        raw = text[len("Error: "):]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
        return {"success": False, "data": data}
    return {"success": True, "data": json.loads(text)}


@pytest.fixture
def patched_server(monkeypatch):
    route = targeting.ToolRoute(
        success=True,
        target=targeting.InstanceRef(port=59123, process_id=4242),
        selection="session",
    )
    routed = []

    def resolve_route(name, **_kwargs):
        routed.append(name)
        return route

    monkeypatch.setattr(server.targeting, "resolve_tool_route", resolve_route)
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())
    yield
    assert len(routed) == 1
    assert routed[0] in {"gh_status", "gh_snapshot", "gh_edit"}


@pytest.mark.asyncio
async def test_gh_status_success_means_endpoint_executed_not_ready(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/status"
        assert method == "GET"
        return {
            "success": True,
            "data": {
                "available": True,
                "assemblyVersion": "8.0.0.0",
                "hasActiveCanvas": True,
                "canvasVisible": False,
                "visibilityUnknown": False,
                "hasActiveDocument": True,
                "documentId": "doc-1",
                "documentName": "example.gh",
                "documentPath": r"C:\tmp\example.gh",
                "readyForEdit": False,
                "objectCount": 4,
                "warnings": [],
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool("gh_status", {})
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["available"] is True
    assert payload["data"]["assembly_version"] == "8.0.0.0"
    assert payload["data"]["has_active_canvas"] is True
    assert payload["data"]["canvas_visible"] is False
    assert payload["data"]["visibility_unknown"] is False
    assert payload["data"]["has_active_document"] is True
    assert payload["data"]["document_id"] == "doc-1"
    assert payload["data"]["document_name"] == "example.gh"
    assert payload["data"]["document_path"] == r"C:\tmp\example.gh"
    assert payload["data"]["ready_for_edit"] is False
    assert payload["data"]["object_count"] == 4
    assert payload["data"]["warnings"] == []
    assert "readyForEdit" not in payload["data"]


@pytest.mark.asyncio
async def test_gh_snapshot_fails_closed_when_not_ready(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/snapshot"
        assert method == "POST"
        return {
            "success": False,
            "data": {
                "error": "grasshopper_not_ready",
                "ready_for_edit": False,
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    response = await server.call_tool("gh_snapshot", {})
    text = response[0].text

    assert text.startswith("Error:")
    assert "grasshopper_not_ready" in text


@pytest.mark.asyncio
async def test_gh_edit_fails_closed_when_not_ready(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        assert method == "POST"
        return {
            "success": False,
            "data": {
                "error": "grasshopper_not_ready",
                "ready_for_edit": False,
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 1})
    text = response[0].text

    assert text.startswith("Error:")
    assert "grasshopper_not_ready" in text
