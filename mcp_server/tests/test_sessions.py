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
