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


class _RaisingClient:
    """Async context manager whose request methods raise a chosen exception."""
    def __init__(self, exc):
        self._exc = exc
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, *a, **k):
        raise self._exc
    async def post(self, *a, **k):
        raise self._exc
    async def request(self, *a, **k):
        raise self._exc


@pytest.mark.asyncio
async def test_call_rhino_connect_error_returns_structured_dead(monkeypatch):
    inst = {"host": "127.0.0.1", "port": 59306, "processId": 4242, "pluginType": "native"}
    monkeypatch.setattr(bridge, "select_rhino_instance", lambda **k: inst)
    monkeypatch.setattr(bridge, "discover_instances", lambda: [inst])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)
    monkeypatch.setattr(bridge, "find_recent_rhino_crash_artifact",
                        lambda process_id=None, since_utc=None: None)
    monkeypatch.setattr(bridge.httpx, "AsyncClient",
                        lambda *a, **k: _RaisingClient(httpx.ConnectError("refused")))

    out = await bridge.call_rhino("/objects", method="GET", port=59306, process_id=4242)

    assert out["success"] is False
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["session"] == "rhino-4242"
    assert out["data"]["endpoint"] == "/objects"


@pytest.mark.asyncio
async def test_call_rhino_post_response_decode_error_is_not_transport(monkeypatch):
    # A response WAS received but .json() fails -> must NOT become a bridge transport
    # error; existing behavior (success:False, data=str(error)) is preserved.
    class _BadJsonClient(_RaisingClient):
        async def get(self, *a, **k):
            class _R:
                def json(self_inner):
                    raise ValueError("not json")
            return _R()
    inst = {"host": "127.0.0.1", "port": 59306, "processId": 7, "pluginType": "native"}
    monkeypatch.setattr(bridge, "select_rhino_instance", lambda **k: inst)
    monkeypatch.setattr(bridge, "discover_instances", lambda: [inst])
    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda *a, **k: _BadJsonClient(None))

    out = await bridge.call_rhino("/objects", method="GET", port=59306, process_id=7)

    assert out["success"] is False
    assert "code" not in out["data"]  # not a structured bridge error
    assert "not json" in out["data"]


@pytest.fixture
def diag_sessions_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path])
    return tmp_path


@pytest.mark.asyncio
async def test_gsc_no_record_alive_pid_is_unreachable_not_dead(diag_sessions_dir, monkeypatch):
    # No native record for the pid, but the pid is alive -> unreachable, NOT dead.
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    out = await bridge.get_session_capabilities("rhino-888")
    assert out["success"] is False
    assert out["data"]["code"] == "rook_native_listener_unreachable"
    assert out["data"]["retryable"] is True


@pytest.mark.asyncio
async def test_gsc_no_record_dead_pid_is_dead(diag_sessions_dir, monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(bridge, "find_recent_rhino_crash_artifact",
                        lambda process_id=None, since_utc=None: None)
    out = await bridge.get_session_capabilities("rhino-889")
    assert out["success"] is False
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["retryable"] is False
