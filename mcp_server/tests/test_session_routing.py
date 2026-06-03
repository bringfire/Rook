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
