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


import httpx


def _diag(exc, monkeypatch, pid_alive=True, port_listening=True, target=None):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: pid_alive)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: port_listening)
    monkeypatch.setattr(
        bridge, "find_recent_rhino_crash_artifact",
        lambda process_id=None, since_utc=None: None,
    )
    return bridge.diagnose_bridge_failure(target or _target(), exc)


def test_read_timeout_is_request_timeout(monkeypatch):
    out = _diag(httpx.ReadTimeout("slow"), monkeypatch, pid_alive=True)
    assert out["data"]["code"] == "rook_native_request_timeout"
    assert out["data"]["retryable"] is True


def test_timeout_masking_death_is_dead(monkeypatch):
    # A death can surface as a ReadTimeout. PID known-dead => rhino_session_dead.
    out = _diag(httpx.ReadTimeout("slow"), monkeypatch, pid_alive=False)
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["retryable"] is False


def test_connect_error_dead(monkeypatch):
    out = _diag(httpx.ConnectError("refused"), monkeypatch, pid_alive=False, port_listening=False)
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["retryable"] is False


def test_connect_error_unreachable(monkeypatch):
    out = _diag(httpx.ConnectError("refused"), monkeypatch, pid_alive=True, port_listening=False)
    assert out["data"]["code"] == "rook_native_listener_unreachable"
    assert out["data"]["retryable"] is True


def test_connect_error_live_race_is_transport(monkeypatch):
    out = _diag(httpx.ConnectError("refused"), monkeypatch, pid_alive=True, port_listening=True)
    assert out["data"]["code"] == "rook_native_transport_error"


def test_close_error_probes_liveness(monkeypatch):
    # CloseError (connection dropped) is connectivity — probe liveness, don't fall
    # through to a generic transport error.
    out = _diag(httpx.CloseError("closed"), monkeypatch, pid_alive=True, port_listening=False)
    assert out["data"]["code"] == "rook_native_listener_unreachable"


def test_connect_timeout_uses_connectivity_not_timeout(monkeypatch):
    # ConnectTimeout subclasses TimeoutException but must be treated as connectivity.
    out = _diag(httpx.ConnectTimeout("slow"), monkeypatch, pid_alive=False, port_listening=False)
    assert out["data"]["code"] == "rhino_session_dead"


def test_protocol_error_is_transport(monkeypatch):
    out = _diag(httpx.ProtocolError("bad"), monkeypatch)
    assert out["data"]["code"] == "rook_native_transport_error"


def test_port_only_target_unresolvable_is_transport(monkeypatch):
    # No processId and no record owning the port => cannot confirm dead.
    monkeypatch.setattr(bridge, "discover_instances", lambda: [])
    out = _diag(httpx.ConnectError("refused"), monkeypatch,
                target=_target(processId=None, session=None))
    assert out["data"]["code"] == "rook_native_transport_error"
