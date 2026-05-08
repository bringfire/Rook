import json
from pathlib import Path

import pytest

from rook import bridge
from tests import conftest


class _FakeNode:
    def __init__(self, has_requires_rhino: bool) -> None:
        self._has_requires_rhino = has_requires_rhino

    def get_closest_marker(self, name: str) -> object | None:
        if name == "requires_rhino" and self._has_requires_rhino:
            return object()
        return None


class _FakeRequest:
    def __init__(self, has_requires_rhino: bool) -> None:
        self.node = _FakeNode(has_requires_rhino)


def _write_instance(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_harness_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROOK_RHINO_PORT", raising=False)
    monkeypatch.delenv("ROOK_RHINO_PROCESS_ID", raising=False)


@pytest.fixture
def discovery_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    return tmp_path


def test_get_harness_scope_from_env_returns_none_when_env_absent() -> None:
    assert conftest._get_harness_scope_from_env() is None


def test_get_harness_scope_from_env_rejects_partial_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")

    with pytest.raises(RuntimeError, match="must both be set"):
        conftest._get_harness_scope_from_env()


@pytest.mark.parametrize(
    ("port", "pid"),
    [
        ("abc", "7102"),
        ("9951", "not-a-pid"),
        ("0", "7102"),
        ("9951", "-1"),
    ],
)
def test_get_harness_scope_from_env_rejects_malformed_or_nonpositive_env(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
    pid: str,
) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", port)
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", pid)

    with pytest.raises(RuntimeError, match="positive integers"):
        conftest._get_harness_scope_from_env()


def test_get_harness_scope_from_env_returns_valid_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")

    assert conftest._get_harness_scope_from_env() == (9951, 7102)


def test_harness_context_scopes_direct_bridge_calls(
    discovery_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_instance(
        discovery_dir / "instance-7101-native.json",
        {
            "port": 9950,
            "processId": 7101,
            "pluginType": "native",
        },
    )
    _write_instance(
        discovery_dir / "instance-7102-native.json",
        {
            "port": 9951,
            "processId": 7102,
            "pluginType": "native",
        },
    )
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")

    with conftest._harness_rhino_request_context_for_test():
        assert bridge.get_rhino_request_context() == {
            "port": 9951,
            "process_id": 7102,
            "document_serial_number": None,
        }
        assert bridge.get_rhino_host() == "http://127.0.0.1:9951"

    assert bridge.get_rhino_request_context() == {
        "port": None,
        "process_id": None,
        "document_serial_number": None,
    }


def test_marker_aware_wrapper_scopes_requires_rhino_test_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROOK_RHINO_PORT", "9951")
    monkeypatch.setenv("ROOK_RHINO_PROCESS_ID", "7102")

    with conftest._harness_rhino_request_context_for_marked_test(
        _FakeRequest(has_requires_rhino=True)
    ):
        assert bridge.get_rhino_request_context()["port"] == 9951
        assert bridge.get_rhino_request_context()["process_id"] == 7102

    with conftest._harness_rhino_request_context_for_marked_test(
        _FakeRequest(has_requires_rhino=False)
    ):
        assert bridge.get_rhino_request_context()["port"] is None
        assert bridge.get_rhino_request_context()["process_id"] is None
