import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rook import server, targeting
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
    route = targeting.ToolRoute(
        success=True,
        target=targeting.InstanceRef(port=59123, process_id=4242),
        selection="session",
    )
    monkeypatch.setattr(server.targeting, "resolve_tool_route", lambda *args, **kwargs: route)
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

    assert payload["success"] is False
    assert payload["data"]["partial_success"] is True
    assert payload["data"]["errors"] == ["set_values exception: value must be numeric"]
    assert payload["data"]["warnings"] == ["set_values exception: value must be numeric"]
    assert payload["data"]["verified"] is False
    assert "partially applied" in payload["data"]["verification_note"]
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

    assert payload["success"] is False
    assert payload["data"]["partial_success"] is True
    assert payload["data"]["errors"] == ["connect: unknown target 'T2'"]
    assert payload["data"]["warnings"] == ["connect: unknown target 'T2'"]
    assert payload["data"]["verified"] is False
    assert "partially applied" in payload["data"]["verification_note"]


@pytest.mark.asyncio
async def test_gh_edit_strict_partial_failure_still_records_session(monkeypatch, patched_server):
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

    record_mock = AsyncMock()

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", record_mock)
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(check_deprecation_warnings=lambda _create: []),
    )

    response = await server.call_tool("gh_edit", {"epoch": 3, "create": []})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["partial_success"] is True
    record_mock.assert_awaited_once()
    recorded_result = record_mock.await_args.kwargs["result"]
    assert recorded_result["success"] is False
    assert recorded_result["partial_success"] is True


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


@pytest.mark.asyncio
async def test_gh_replay_recipe_strict_partial_failure_is_recorded_as_partial(monkeypatch, patched_server):
    class _Pattern:
        pattern_id = "pat-1"
        name = "partial recipe"
        schema_version = "2.0"
        graph = {
            "components": [{"id": "R1", "type": "Panel", "pos": [0, 0]}],
            "flows": [],
        }

    class _Store:
        def get(self, pattern_id):
            assert pattern_id == "pat-1"
            return _Pattern()

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        if route == "/gh/snapshot":
            return {"success": True, "data": {"epoch": 4}}
        if route == "/gh/edit":
            return {
                "success": True,
                "data": {
                    "edit_summary": {
                        "created": 1,
                        "errors": ["connect: failed during replay"],
                        "instance_guids": {"T1": "guid-1"},
                    }
                },
            }
        raise AssertionError(f"Unexpected route: {route}")

    record_mock = AsyncMock()

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "_record_gh_to_session", record_mock)
    monkeypatch.setattr("rook.learning.pattern_store.get_pattern_store", lambda: _Store())

    response = await server.call_tool("gh_replay_recipe", {"pattern_id": "pat-1"})
    payload = _decode_response(response)

    assert payload["success"] is False
    assert payload["data"]["partial_success"] is True
    assert payload["data"]["errors"] == ["connect: failed during replay"]
    record_mock.assert_awaited_once()


def test_batch_gh_edit_partial_result_does_not_request_sequential_fallback():
    edit_result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 1,
                "connected": 0,
                "errors": ["connect: failed"],
                "instance_guids": {"T1": "guid-1"},
            }
        },
    }
    temp_id_map = [({"guid": "component-guid"}, "Panel", 10, 20)]

    contracted, should_fallback, created, errors = server._prepare_batch_gh_edit_result(
        edit_result,
        temp_id_map,
    )

    assert contracted["success"] is False
    assert contracted["partial_success"] is True
    assert should_fallback is False
    assert created == [{
        "name": "Panel",
        "component_guid": "component-guid",
        "instance_guid": "guid-1",
        "x": 10,
        "y": 20,
    }]
    assert errors == ["connect: failed"]


def test_batch_gh_edit_no_mutation_failure_requests_sequential_fallback():
    edit_result = {
        "success": True,
        "data": {
            "edit_summary": {
                "created": 0,
                "connected": 0,
                "errors": ["epoch mismatch"],
            }
        },
    }

    contracted, should_fallback, created, errors = server._prepare_batch_gh_edit_result(
        edit_result,
        [({"guid": "component-guid"}, "Panel", 10, 20)],
    )

    assert contracted["success"] is False
    assert should_fallback is True
    assert created == []
    assert errors == []


@pytest.mark.asyncio
async def test_universal_injection_skips_partial_or_unverified_success(monkeypatch, patched_server):
    monkeypatch.setattr(server, "_record_observation", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        assert route == "/gh/snapshot"
        return {
            "success": True,
            "partial_success": True,
            "verified": False,
            "_injection_meta": {"store": "gh", "items": []},
            "data": {"objects": []},
        }

    def fail_should_inject(_name, _result):
        raise AssertionError("partial or unverified result must not request injection")

    record_mock = AsyncMock()

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server, "should_inject", fail_should_inject)
    monkeypatch.setattr(server, "record_injection_success", record_mock)

    response = await server.call_tool("gh_snapshot", {})
    payload = _decode_response(response)

    assert payload["success"] is True
    record_mock.assert_not_called()
