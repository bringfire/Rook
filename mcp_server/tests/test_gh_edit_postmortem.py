import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rook import server
import rook.learning.gh_session_history as gh_session_history


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
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())


@pytest.mark.asyncio
async def test_gh_edit_surfaces_edit_summary_errors_as_warnings(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        assert method == "POST"
        return {
            "success": True,
            "data": {
                "epoch": 3,
                "edit_summary": {
                    "created": 1,
                    "errors": ["set_values exception: value must be numeric"],
                },
            },
        }

    record_mock = AsyncMock()

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", record_mock)
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 3, "set_values": []})
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["partial_success"] is True
    assert payload["data"]["errors"] == ["set_values exception: value must be numeric"]
    assert payload["data"]["warnings"] == ["set_values exception: value must be numeric"]
    assert payload["data"]["verified"] is False
    record_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_gh_edit_no_mutation_errors_return_failure(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        return {
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 0,
                    "deleted": 0,
                    "values_set": 0,
                    "connected": 0,
                    "disconnected": 0,
                    "errors": ["Create failed: Centre Box not found"],
                }
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", AsyncMock())
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 3, "create": []})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["verified"] is False
    assert payload["data"]["errors"] == ["Create failed: Centre Box not found"]
    assert "failed before applying any mutations" in payload["data"]["verification_note"]


@pytest.mark.asyncio
async def test_gh_edit_partial_mutation_response_contains_visible_contract(monkeypatch, patched_server):
    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/edit"
        return {
            "success": True,
            "data": {
                "edit_summary": {
                    "created": 1,
                    "errors": ["connect: unknown target 'T2'"],
                    "temp_id_map": {"T1": "R1"},
                }
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", AsyncMock())
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 3, "create": []})
    payload = _decode_response(response)

    assert payload["success"] is True
    assert payload["data"]["partial_success"] is True
    assert payload["data"]["errors"] == ["connect: unknown target 'T2'"]
    assert payload["data"]["warnings"] == ["connect: unknown target 'T2'"]
    assert payload["data"]["verified"] is False
    assert "partially applied" in payload["data"]["verification_note"]


@pytest.mark.asyncio
async def test_record_gh_to_session_marks_edit_summary_errors_as_partial(monkeypatch):
    recorded = {}

    class _DummyRecorder:
        async def record(self, **kwargs):
            recorded.update(kwargs)
            return 11

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/document"
        return {
            "success": True,
            "data": {
                "name": "postmortem.gh",
                "path": r"C:\temp\postmortem.gh",
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(gh_session_history, "get_session_recorder", lambda: _DummyRecorder())

    result = {
        "success": True,
        "data": {
            "edit_summary": {
                "errors": ["connect: unknown target 'C9'"],
            },
        },
    }

    entry_id = await server._record_gh_to_session(
        action="gh_edit",
        params={"epoch": 7},
        result=result,
        port=9999,
    )

    assert entry_id == 11
    tool_result = recorded["result"]
    assert tool_result.success is True
    assert tool_result.outcome == "partial"
    assert tool_result.errors == ["connect: unknown target 'C9'"]
    assert tool_result.warnings == []
