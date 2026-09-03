import json
import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import bridge


def _write_instance(folder: Path, data: dict) -> Path:
    path = folder / f"instance-{data['processId']}-native.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_is_port_listening_true_for_open_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert bridge._is_port_listening("127.0.0.1", port) is True
    finally:
        sock.close()
    # After close, nothing is listening on that port.
    assert bridge._is_port_listening("127.0.0.1", port) is False


def test_is_port_listening_false_for_zero_port():
    assert bridge._is_port_listening("127.0.0.1", 0) is False


def test_session_id_round_trip():
    instance = {"processId": 12345, "port": 10500, "pluginType": "native"}
    sid = bridge.session_id_for_instance(instance)
    assert sid == "rhino-12345"
    assert bridge._process_id_from_session_id(sid) == 12345


def test_process_id_from_session_id_rejects_bad_input():
    assert bridge._process_id_from_session_id("bogus") is None
    assert bridge._process_id_from_session_id("rhino-") is None
    assert bridge._process_id_from_session_id("rhino-abc") is None
    assert bridge._process_id_from_session_id(None) is None


def test_classify_live(monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)
    out = bridge.classify_session_liveness({"processId": 1, "host": "127.0.0.1", "port": 10500})
    assert out["state"] == "live"
    assert out["pidAlive"] is True
    assert out["portListening"] is True
    assert out["code"] is None


def test_classify_unreachable_keeps_session(monkeypatch):
    # PID alive but port down => unreachable, NOT dead. Must never imply reaping.
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)
    out = bridge.classify_session_liveness({"processId": 2, "host": "127.0.0.1", "port": 10500})
    assert out["state"] == "unreachable"
    assert out["code"] == "rook_native_listener_unreachable"


def test_classify_dead(monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)
    out = bridge.classify_session_liveness({"processId": 3, "host": "127.0.0.1", "port": 10500})
    assert out["state"] == "dead"
    assert out["code"] == "rhino_session_dead"


@pytest.fixture
def sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path])
    return tmp_path


def test_list_sessions_projects_named_sessions_with_liveness(sessions_dir, monkeypatch):
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native",
        "processId": 4321, "pluginVersion": "1.5.8", "rhinoInside": False,
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    sessions = bridge.list_sessions()

    assert len(sessions) == 1
    s = sessions[0]
    assert s["session"] == "rhino-4321"
    assert s["processId"] == 4321
    assert s["port"] == 10500
    assert s["pluginType"] == "native"
    assert s["pluginVersion"] == "1.5.8"
    assert s["liveness"]["state"] == "live"


def test_list_sessions_dedupes_roadcreator_sharing_rhino_pid(sessions_dir, monkeypatch):
    # The roadcreator adapter shares the Rhino PID. Only the native listener is
    # a session — otherwise we'd emit two sessions with the same rhino-<pid> id.
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 909,
    })
    rc_path = sessions_dir / "instance-rc-909.json"
    rc_path.write_text(json.dumps({
        "host": "127.0.0.1", "port": 10600, "pluginType": "roadcreator", "processId": 909,
    }), encoding="utf-8")
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    sessions = bridge.list_sessions()

    assert [s["session"] for s in sessions] == ["rhino-909"]
    assert sessions[0]["pluginType"] == "native"


def test_list_sessions_dedupes_pid_without_hiding_discovery_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = tmp_path / "primary"
    legacy = tmp_path / "legacy"
    primary.mkdir()
    legacy.mkdir()
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", primary)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [primary, legacy])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)
    _write_instance(primary, {
        "host": "127.0.0.1", "port": 9950, "pluginType": "native", "processId": 7101,
    })
    _write_instance(legacy, {
        "host": "127.0.0.1", "port": 9960, "pluginType": "native", "processId": 7101,
    })

    instances = bridge.discover_instances()
    sessions = bridge.list_sessions()

    assert sorted(instance["port"] for instance in instances) == [9950, 9960]
    assert [(session["session"], session["port"]) for session in sessions] == [
        ("rhino-7101", 9950)
    ]


def test_list_sessions_result_envelope(sessions_dir, monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 7,
    })

    envelope = bridge.list_sessions_result()

    assert envelope["success"] is True
    assert [s["session"] for s in envelope["data"]["sessions"]] == ["rhino-7"]


def test_assert_session_readonly_endpoint_allows_vetted():
    # Must not raise.
    bridge.assert_session_readonly_endpoint("/ping")
    bridge.assert_session_readonly_endpoint("/capabilities")


def test_assert_session_readonly_endpoint_rejects_others():
    with pytest.raises(bridge.SessionEndpointNotAllowed):
        bridge.assert_session_readonly_endpoint("/objects")
    with pytest.raises(bridge.SessionEndpointNotAllowed):
        bridge.assert_session_readonly_endpoint("/gh/add")


@pytest.mark.asyncio
async def test_get_session_capabilities_invalid_id(sessions_dir):
    out = await bridge.get_session_capabilities("not-a-session")
    assert out["success"] is False
    assert out["data"]["code"] == "invalid_session_id"


@pytest.mark.asyncio
async def test_get_session_capabilities_dead_when_absent(sessions_dir, monkeypatch):
    # No discovery file AND the pid is gone => dead. (P2: absence alone no longer
    # implies dead — the pid is probed; an alive pid with no record is unreachable.)
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(bridge, "find_recent_rhino_crash_artifact",
                        lambda process_id=None, since_utc=None: None)
    out = await bridge.get_session_capabilities("rhino-999")
    assert out["success"] is False
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["session"] == "rhino-999"
    assert "next_action" in out["data"]


@pytest.mark.asyncio
async def test_get_session_capabilities_unreachable_does_not_reap(sessions_dir, monkeypatch):
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 555,
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)

    out = await bridge.get_session_capabilities("rhino-555")

    assert out["success"] is False
    assert out["data"]["code"] == "rook_native_listener_unreachable"
    # The discovery file must still be present (we never reap an alive process).
    assert (sessions_dir / "instance-555-native.json").exists()


@pytest.mark.asyncio
async def test_get_session_capabilities_pins_endpoint_to_allowlist(sessions_dir, monkeypatch):
    # A forged/malformed discovery record must NOT be able to redirect resolution
    # off the read-only allowlist. liveEndpoint="/objects" must be forced back to
    # "/capabilities" on the instance actually handed to resolve_capabilities.
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 77,
        "capabilities": {"liveEndpoint": "/objects"},
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    seen = {}

    async def capture_resolve(instance, timeout=None):
        seen["endpoint"] = (instance.get("capabilities") or {}).get("liveEndpoint")
        return {"source": "live", "capabilities": {"domains": []}}

    monkeypatch.setattr(bridge, "resolve_capabilities", capture_resolve)

    out = await bridge.get_session_capabilities("rhino-77")

    assert out["success"] is True
    assert seen["endpoint"] == "/capabilities"  # never "/objects"


@pytest.mark.asyncio
async def test_get_session_capabilities_live(sessions_dir, monkeypatch):
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 42,
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    async def fake_resolve(instance, timeout=None):
        return {"source": "live", "stale": False, "authoritative": True,
                "capabilities": {"domains": []}}

    monkeypatch.setattr(bridge, "resolve_capabilities", fake_resolve)

    out = await bridge.get_session_capabilities("rhino-42")

    assert out["success"] is True
    assert out["data"]["session"] == "rhino-42"
    assert out["data"]["processId"] == 42
    assert out["data"]["liveness"]["state"] == "live"
    assert out["data"]["capabilities"]["source"] == "live"


@pytest.mark.asyncio
async def test_get_session_capabilities_dead_after_discovery_race(sessions_dir, monkeypatch):
    # The record survives discovery cleanup (pid alive then) but the process dies
    # before classification. Truth contract: report dead, and never resolve stale
    # capabilities for a gone process. _is_pid_alive is called once during cleanup
    # (alive) and once during classification (dead).
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 333,
    })

    calls = {"n": 0}

    def flaky_pid_alive(pid):
        calls["n"] += 1
        return calls["n"] == 1  # alive during cleanup, dead during classification

    monkeypatch.setattr(bridge, "_is_pid_alive", flaky_pid_alive)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)

    resolved_called = {"hit": False}

    async def must_not_resolve(inst, timeout=None):
        resolved_called["hit"] = True
        return {"source": "bootstrap", "capabilities": {"domains": []}}

    monkeypatch.setattr(bridge, "resolve_capabilities", must_not_resolve)

    out = await bridge.get_session_capabilities("rhino-333")

    assert out["success"] is False
    assert out["data"]["code"] == "rhino_session_dead"
    assert resolved_called["hit"] is False  # never resolved a dead session
