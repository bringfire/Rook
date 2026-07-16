from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rook import server


class _DummyPhaseTracker:
    def record_call(self, _name: str) -> None:
        pass


def _decode_success(contents):
    assert len(contents) == 1
    assert not contents[0].text.startswith("Error: ")
    return json.loads(contents[0].text)


def _telemetry_store(monkeypatch, tmp_path):
    from rook.learning import metrics_store

    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    return store


@pytest.fixture
def admitted_server(monkeypatch):
    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    monkeypatch.setattr(
        server.targeting,
        "policy_for_tool",
        lambda _name: SimpleNamespace(requires_rhino=False),
    )
    monkeypatch.setattr(server, "should_inject", lambda _name, _result: False)
    monkeypatch.setattr(server, "_record_observation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "get_phase_tracker", lambda: _DummyPhaseTracker())
    monkeypatch.setattr(server, "_record_gh_to_session", AsyncMock())
    monkeypatch.setattr(
        server,
        "get_unified_store",
        lambda: SimpleNamespace(
            check_deprecation_warnings=lambda _create: [],
        ),
    )


@pytest.mark.asyncio
async def test_typed_rhino_create_preserves_shared_safe_create_primitive(
    monkeypatch,
    tmp_path,
    admitted_server,
) -> None:
    """The explicit typed route still reaches the bounded /create primitive.

    The retired rhino_execute_intent orchestrator used the same low-level route
    for direct-api plans; containment follows the retired identity, not this
    explicit typed operation.
    """
    store = _telemetry_store(monkeypatch, tmp_path)
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {
            "success": True,
            "data": {"id": "sphere-1", "objectsCreated": 1},
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    before = store.get_containment_denials_snapshot()

    response = await server.call_tool(
        "rhino_create",
        {
            "type": "SPHERE",
            "center": [0, 0, 0],
            "radius": 5,
        },
    )

    assert _decode_success(response)["id"] == "sphere-1"
    assert calls == [
        (
            "/create",
            "POST",
            {
                "type": "SPHERE",
                "center": [0, 0, 0],
                "radius": 5,
            },
            None,
        )
    ]
    assert store.get_containment_denials_snapshot() == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_route", "expected_method"),
    [
        ("rhino_execute", {"code": "x = 1 + 2"}, "/execute", "POST"),
        ("gh_snapshot", {"include_data": False}, "/gh/snapshot", "POST"),
        ("gh_errors", {}, "/gh/errors", "GET"),
    ],
)
async def test_supported_explicit_execution_and_inspection_paths_remain_callable(
    monkeypatch,
    tmp_path,
    admitted_server,
    tool_name: str,
    arguments: dict,
    expected_route: str,
    expected_method: str,
) -> None:
    store = _telemetry_store(monkeypatch, tmp_path)
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {"success": True, "data": {"route": route}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    before = store.get_containment_denials_snapshot()

    response = await server.call_tool(tool_name, arguments)

    assert _decode_success(response)["route"] == expected_route
    assert len(calls) == 1
    assert calls[0][0] == expected_route
    assert calls[0][1] == expected_method
    assert store.get_containment_denials_snapshot() == before


def _safe_line_knowledge_store():
    return SimpleNamespace(
        parse_command_string=lambda _cmd: {
            "command": "-Line",
            "mode": "default",
            "syntax": "_Line <start> <end>",
            "parameters": {"start": "0,0,0", "end": "1,1,1"},
            "options_used": [],
        },
        get_command=lambda _cmd: SimpleNamespace(
            options={},
            modes={"default": SimpleNamespace(syntax="_Line <start> <end>")},
            preconditions={"safe_non_interactive": True},
        ),
    )


@pytest.mark.asyncio
async def test_sanctioned_preflighted_rhino_command_remains_callable(
    monkeypatch,
    tmp_path,
    admitted_server,
) -> None:
    store = _telemetry_store(monkeypatch, tmp_path)
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {"success": True, "data": {"output": "line created"}}

    monkeypatch.setattr(server.command_learner, "knowledge_store", _safe_line_knowledge_store())
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    before = store.get_containment_denials_snapshot()
    arguments = {"command": "_Line 0,0,0 1,1,1"}

    response = await server.call_tool("rhino_command", arguments)

    assert _decode_success(response)["output"] == "line created"
    assert calls == [("/command", "POST", arguments, None)]
    assert store.get_containment_denials_snapshot() == before


@pytest.mark.asyncio
async def test_gh_edit_remains_callable_without_containment_telemetry(
    monkeypatch,
    tmp_path,
    admitted_server,
) -> None:
    store = _telemetry_store(monkeypatch, tmp_path)
    calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        calls.append((route, method, payload, port))
        return {
            "success": True,
            "data": {
                "epoch": 12,
                "edit_summary": {
                    "created": 1,
                    "deleted": 0,
                    "values_set": 0,
                    "connected": 0,
                    "disconnected": 0,
                    "errors": [],
                },
            },
        }

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    before = store.get_containment_denials_snapshot()
    arguments = {
        "epoch": 12,
        "create": [{"temp_id": "T1", "name": "Panel", "x": 10, "y": 20}],
    }

    response = await server.call_tool("gh_edit", arguments)

    payload = _decode_success(response)
    assert payload["edit_summary"]["created"] == 1
    assert calls == [("/gh/edit", "POST", arguments, None)]
    assert store.get_containment_denials_snapshot() == before


@pytest.mark.asyncio
async def test_supported_gh_script_mutation_paths_remain_callable(
    monkeypatch,
    tmp_path,
    admitted_server,
) -> None:
    store = _telemetry_store(monkeypatch, tmp_path)
    create = AsyncMock(
        return_value={
            "success": True,
            "data": {"component_guid": "script-created"},
        }
    )
    update = AsyncMock(
        return_value={
            "success": True,
            "data": {"component_guid": "script-existing", "updated": True},
        }
    )
    host_calls = []

    async def fake_call_rhino(route, method="GET", payload=None, port=None):
        host_calls.append((route, method, payload, port))
        return {"success": True, "data": {"guid": payload["guid"]}}

    monkeypatch.setattr(server, "_execute_gh_create_script", create)
    monkeypatch.setattr(server, "_execute_gh_update_script", update)
    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    before = store.get_containment_denials_snapshot()

    created = await server.call_tool(
        "gh_create_script",
        {
            "language": "python",
            "code": "A = 1",
            "pins_in": [],
            "pins_out": [{"name": "A", "type": "int"}],
        },
    )
    updated = await server.call_tool(
        "gh_update_script",
        {
            "guid": "script-existing",
            "language": "python",
            "code": "A = 2",
        },
    )
    set_result = await server.call_tool(
        "gh_set_script",
        {"guid": "script-existing", "script": "A = 3"},
    )

    assert _decode_success(created)["component_guid"] == "script-created"
    assert _decode_success(updated)["updated"] is True
    assert _decode_success(set_result)["guid"] == "script-existing"
    create.assert_awaited_once()
    update.assert_awaited_once()
    assert host_calls == [
        (
            "/gh/script",
            "POST",
            {"guid": "script-existing", "script": "A = 3"},
            None,
        )
    ]
    assert store.get_containment_denials_snapshot() == before
