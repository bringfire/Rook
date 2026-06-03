import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import targeting


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


def test_non_routed_session_argument_tools_is_capabilities_only():
    assert targeting._NON_ROUTED_SESSION_ARGUMENT_TOOLS == {"rhino_session_capabilities"}


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
