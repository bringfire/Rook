import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import bridge


def _target(**over):
    t = {"host": "127.0.0.1", "port": 59306, "processId": 12345,
         "session": "rhino-12345", "endpoint": "/objects", "method": "GET"}
    t.update(over)
    return t


def test_build_unreachable_envelope():
    liveness = {"state": "unreachable", "pidAlive": True, "portListening": False}
    out = bridge.build_session_liveness_error(_target(), liveness, reason="tool_call")
    assert out["success"] is False
    d = out["data"]
    assert d["code"] == "rook_native_listener_unreachable"
    assert d["retryable"] is True
    assert d["session"] == "rhino-12345"
    assert d["processId"] == 12345
    assert d["port"] == 59306
    assert d["endpoint"] == "/objects"
    assert d["liveness"]["state"] == "unreachable"
    assert "crash_artifact" not in d
    assert "next_action" in d


def test_build_dead_envelope_attaches_crash_artifact(monkeypatch):
    monkeypatch.setattr(
        bridge, "find_recent_rhino_crash_artifact",
        lambda process_id=None, since_utc=None: {"available": True, "kind": "minidump",
                                                 "path": "X", "pidMatched": True},
    )
    liveness = {"state": "dead", "pidAlive": False, "portListening": False}
    out = bridge.build_session_liveness_error(_target(), liveness, reason="tool_call")
    d = out["data"]
    assert d["code"] == "rhino_session_dead"
    assert d["retryable"] is False
    assert d["crash_artifact"]["pidMatched"] is True


def test_build_dead_envelope_no_artifact_when_none(monkeypatch):
    monkeypatch.setattr(
        bridge, "find_recent_rhino_crash_artifact",
        lambda process_id=None, since_utc=None: None,
    )
    liveness = {"state": "dead", "pidAlive": False, "portListening": False}
    out = bridge.build_session_liveness_error(_target(), liveness, reason="tool_call")
    assert out["data"]["code"] == "rhino_session_dead"
    assert "crash_artifact" not in out["data"]
