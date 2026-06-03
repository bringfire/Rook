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
