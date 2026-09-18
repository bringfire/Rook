import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import targeting


HOST_GENERATION_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def reset_targeting_state():
    targeting.reset_targeting_state_for_tests()
    yield
    targeting.reset_targeting_state_for_tests()


def _inst(port: int, pid: int, name: str = "Doc.3dm", plugin_type: str = "native") -> dict:
    return {
        "host": "127.0.0.1",
        "port": port,
        "processId": pid,
        "pluginType": plugin_type,
        "documentName": name,
        "hostGenerationId": HOST_GENERATION_ID,
    }


def test_toolroute_supports_session_selection_and_fields():
    route = targeting.ToolRoute(
        success=True,
        selection="session",
        invalid_session="x",
        requested_session="rhino-7",
        session_process_id=7,
        port_process_id=9,
    )
    assert route.selection == "session"
    assert route.invalid_session == "x"
    assert route.requested_session == "rhino-7"
    assert route.session_process_id == 7
    assert route.port_process_id == 9


def test_non_routed_session_argument_tools_membership():
    # rhino_session_capabilities (P1) + rhino_workbench_close (P4) + rhino_merge_contract_execute
    # (P7 Slice 4) own a non-routing `session` argument — the set grows only by intentional addition.
    assert targeting._NON_ROUTED_SESSION_ARGUMENT_TOOLS == {
        "rhino_session_capabilities", "rhino_workbench_close", "rhino_merge_contract_execute"}


def test_allows_non_routed_session_argument():
    assert targeting.allows_non_routed_session_argument("rhino_session_capabilities") is True
    assert targeting.allows_non_routed_session_argument("knowledge_query") is False
    assert targeting.allows_non_routed_session_argument("rhino_sessions") is False


def test_session_not_targetable_result_shape():
    out = targeting.session_not_targetable_result("knowledge_query")
    assert out["success"] is False
    assert out["data"]["error"] == "session_not_targetable"
    assert out["data"]["tool"] == "knowledge_query"
    assert "session" in out["data"]["message"].lower()


def test_present_but_null_session_is_invalid(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session=None, has_explicit_session=True
    )
    assert route.success is False
    assert route.error == "invalid_session_id"


@pytest.mark.parametrize("bad", ["bogus", "rhino-", "rhino-abc", "rhino-0", "rhino--5", 12345])
def test_malformed_session_is_invalid(monkeypatch, bad):
    # Includes non-positive PIDs: the bridge parser leniently returns int("0")==0
    # and int("-5")==-5, so the parse gate must reject pid_s <= 0 as invalid (NOT
    # let them fall through to rhino_session_not_found).
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session=bad, has_explicit_session=True
    )
    assert route.error == "invalid_session_id"


def test_absent_session_skips_session_rung(monkeypatch):
    # No session key -> has_explicit_session False -> falls through to existing auto.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route("rhino_execute", has_explicit_session=False)
    assert route.success is True
    assert route.error is None
    assert route.selection == "auto"


def test_invalid_session_id_envelope(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="bogus", has_explicit_session=True
    )
    result = targeting.route_error_result(route)
    assert result["success"] is False
    assert result["data"]["error"] == "invalid_session_id"
    assert result["data"]["invalidSession"] == repr("bogus")
    assert "instances" in result["data"]


def test_session_selects_named_target_among_multiple(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7102", has_explicit_session=True
    )
    assert route.success is True
    assert route.selection == "session"
    assert route.target == targeting.InstanceRef(9951, 7102)


def test_session_bypasses_multiple_instance_mutate_refusal(monkeypatch):
    # Bare mutate with 2 instances would be multiple_rhino_instances; naming a
    # session disambiguates.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", has_explicit_session=True
    )
    assert route.success is True
    assert route.target == targeting.InstanceRef(9950, 7101)


def test_session_not_found_when_no_native_record(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-9999", has_explicit_session=True
    )
    assert route.success is False
    assert route.error == "rhino_session_not_found"


def test_session_not_found_when_only_roadcreator_for_pid(monkeypatch):
    # A session is the NATIVE listener; a pid with only a roadcreator record is not
    # a session.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9960, 7101, "A.3dm", plugin_type="roadcreator"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", has_explicit_session=True
    )
    assert route.error == "rhino_session_not_found"


def test_rhino_session_not_found_envelope(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    monkeypatch.setattr(targeting, "discovery_diagnostics", lambda: {
        "discoveryFolder": r"C:\disc", "discoveryFolders": [r"C:\disc"],
        "selection": "localappdata", "tempRoot": r"C:\t", "legacyTempDiscoveryFolder": r"C:\t\rook",
    })
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-9999", has_explicit_session=True
    )
    result = targeting.route_error_result(route)
    assert result["data"]["error"] == "rhino_session_not_found"
    assert result["data"]["session"] == "rhino-9999"
    assert result["data"]["discoveryFolder"] == r"C:\disc"


def test_session_plus_same_pid_port_session_wins(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9950,
        has_explicit_session=True,
    )
    assert route.success is True
    assert route.selection == "session"
    assert route.target == targeting.InstanceRef(9950, 7101)


def test_session_plus_different_pid_port_is_conflict(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9951,
        has_explicit_session=True,
    )
    assert route.success is False
    assert route.error == "selector_conflict"


def test_session_plus_undiscovered_port_is_port_not_found(monkeypatch):
    # Conflict requires both selectors to resolve; an unknown port is a port error.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9999,
        has_explicit_session=True,
    )
    assert route.error == "requested_port_not_discovered"


def test_selector_conflict_envelope(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9951,
        has_explicit_session=True,
    )
    result = targeting.route_error_result(route)
    d = result["data"]
    assert d["error"] == "selector_conflict"
    assert d["session"] == "rhino-7101"
    assert d["requestedPort"] == 9951
    assert d["sessionProcessId"] == 7101
    assert d["portProcessId"] == 7102


def _lock_to(pid: int):
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": str(pid),
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "55",
    })


def test_panel_lock_allows_in_lock_session(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    _lock_to(7101)
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", has_explicit_session=True
    )
    assert route.success is True
    assert route.selection == "panel_locked"
    assert route.target == targeting.InstanceRef(9950, 7101)


def test_panel_lock_rejects_out_of_lock_session(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    _lock_to(7101)
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7102", has_explicit_session=True
    )
    assert route.success is False
    assert route.error == "panel_target_locked"


@pytest.mark.asyncio
async def test_call_tool_routes_by_session_sets_context(monkeypatch):
    # Mirrors the proven context-capture pattern (a read tool that reaches
    # call_rhino without per-tool preprocessing). Session=rhino-7102 must route to
    # 7102 even though it is NOT the auto-first instance.
    from rook import bridge, server
    insts = [_inst(9950, 7101, "A.3dm"), _inst(9951, 7102, "B.3dm")]
    monkeypatch.setattr(server, "discover_instances", lambda: insts)
    monkeypatch.setattr(targeting, "discover_instances", lambda: insts)
    targeting.clear_active_target()

    captured = {}

    async def fake_call_rhino(*a, **k):
        captured.update(bridge.get_rhino_request_context())
        return {"success": True, "data": []}

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.side_effect = fake_call_rhino
        await server.call_tool("rhino_layers", {"session": "rhino-7102"})
    assert captured["port"] == 9951
    assert captured["process_id"] == 7102


@pytest.mark.asyncio
async def test_call_tool_session_bypasses_mutate_ambiguity(monkeypatch):
    # Two instances: a bare mutate refuses (multiple_rhino_instances); naming a
    # session disambiguates and dispatches.
    from rook import server
    insts = [_inst(9950, 7101, "A.3dm"), _inst(9951, 7102, "B.3dm")]
    monkeypatch.setattr(server, "discover_instances", lambda: insts)
    monkeypatch.setattr(targeting, "discover_instances", lambda: insts)
    targeting.clear_active_target()

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"ok": True}}
        result = await server.call_tool(
            "rhino_execute", {"session": "rhino-7102", "code": "print(1)"}
        )
    assert "multiple_rhino_instances" not in result[0].text
    mock.assert_awaited()


@pytest.mark.asyncio
async def test_call_tool_strips_session_from_dispatch(monkeypatch):
    from rook import server
    insts = [_inst(9950, 7101, "A.3dm")]
    monkeypatch.setattr(server, "discover_instances", lambda: insts)
    monkeypatch.setattr(targeting, "discover_instances", lambda: insts)
    targeting.clear_active_target()

    captured = {}

    async def fake_dispatch(name, arguments):
        captured["arguments"] = arguments
        return {"success": True, "data": {}}

    with patch.object(server, "_call_tool_dispatch", new_callable=AsyncMock) as mock:
        mock.side_effect = fake_dispatch
        await server.call_tool(
            "rhino_execute", {"session": "rhino-7101", "code": "print(1)"}
        )
    assert "session" not in captured["arguments"]
    assert captured["arguments"]["code"] == "print(1)"


@pytest.mark.asyncio
async def test_call_tool_rejects_session_on_non_routed_tool(monkeypatch):
    from rook import server
    result = await server.call_tool(
        "knowledge_query", {"session": "rhino-7101", "intent": "x"}
    )
    assert "session_not_targetable" in result[0].text


@pytest.mark.asyncio
async def test_call_tool_allows_session_on_capabilities(monkeypatch):
    from rook import server
    monkeypatch.setattr(
        server, "get_session_capabilities",
        AsyncMock(return_value={"success": True, "data": {"session": "rhino-1"}}),
    )
    result = await server.call_tool("rhino_session_capabilities", {"session": "rhino-1"})
    assert "session_not_targetable" not in result[0].text
