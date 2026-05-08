import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import bridge


def _write_instance(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def discovery_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    return tmp_path


def test_discover_instances_ignores_legacy_public_csharp_records(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-1234.json",
        {
            "port": 9876,
            "processId": 1234,
            "pluginType": "csharp",
            "startTime": "2026-03-06T10:00:00",
        },
    )
    _write_instance(
        discovery_dir / "instance-1234-native.json",
        {
            "port": 9950,
            "processId": 1234,
            "pluginType": "native",
            "capabilities": {
                "ghProvider": "callback",
                "ghRoutes": ["/gh/query"],
            },
        },
    )

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["pluginType"] == "native"
    assert instances[0]["port"] == 9950


def test_select_rhino_instance_prefers_native_callback_gh_when_ready(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-2001-native.json",
        {
            "port": 9950,
            "processId": 2001,
            "pluginType": "native",
            "capabilities": {
                "ghProvider": "callback",
                "ghRoutes": ["/gh/query", "/gh/document"],
            },
        },
    )

    selected = bridge.select_rhino_instance(endpoint="/gh/query")

    assert selected is not None
    assert selected["port"] == 9950
    assert selected["pluginType"] == "native"


def test_select_rhino_instance_prefers_native_for_expanded_gh_routes(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-2002-native.json",
        {
            "port": 9951,
            "processId": 2002,
            "pluginType": "native",
            "capabilities": {
                "ghProvider": "callback",
                "ghRoutes": ["/gh/library", "/gh/categories", "/gh/errors"],
            },
        },
    )

    selected = bridge.select_rhino_instance(endpoint="/gh/library")

    assert selected is not None
    assert selected["port"] == 9951
    assert selected["pluginType"] == "native"


def test_select_rhino_instance_returns_none_when_native_lacks_requested_gh_route(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-3001-native.json",
        {
            "port": 9950,
            "processId": 3001,
            "pluginType": "native",
            "capabilities": {
                "ghProvider": "callback",
                "ghRoutes": ["/gh/query", "/gh/document"],
            },
        },
    )

    selected = bridge.select_rhino_instance(endpoint="/gh/value", port=9950)

    assert selected is None


def test_select_rhino_instance_returns_none_before_callback_bridge_is_ready(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-4001-native.json",
        {
            "port": 9950,
            "processId": 4001,
            "pluginType": "native",
            "capabilities": {
                "ghProvider": "callback",
                "ghRoutes": [],
            },
        },
    )

    selected = bridge.select_rhino_instance(endpoint="/gh/query")

    assert selected is None


def test_select_rhino_instance_respects_explicit_port_for_non_gh(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-5001-native.json",
        {
            "port": 9950,
            "processId": 5001,
            "pluginType": "native",
        },
    )
    _write_instance(
        discovery_dir / "instance-5002-native.json",
        {
            "port": 9951,
            "processId": 5002,
            "pluginType": "native",
        },
    )

    selected = bridge.select_rhino_instance(endpoint="/document", port=9951)

    assert selected is not None
    assert selected["port"] == 9951
    assert selected["pluginType"] == "native"


def test_select_rhino_instance_preserves_ambient_missing_explicit_port(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-5001-native.json",
        {
            "port": 9950,
            "processId": 5001,
            "pluginType": "native",
        },
    )

    selected = bridge.select_rhino_instance(port=9951)

    assert selected == {"port": 9951}


def test_select_rhino_instance_respects_process_id_for_non_gh(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-7001-native.json",
        {
            "port": 9950,
            "processId": 7001,
            "pluginType": "native",
        },
    )
    _write_instance(
        discovery_dir / "instance-7002-native.json",
        {
            "port": 9951,
            "processId": 7002,
            "pluginType": "native",
        },
    )

    selected = bridge.select_rhino_instance(endpoint="/document", process_id=7002)

    assert selected is not None
    assert selected["port"] == 9951
    assert selected["pluginType"] == "native"


def test_select_rhino_instance_rejects_port_anchor_with_wrong_process_id(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-7102-native.json",
        {
            "port": 9951,
            "processId": 9999,
            "pluginType": "native",
        },
    )

    selected = bridge.select_rhino_instance(port=9951, process_id=7102)

    assert selected is None


def test_select_rhino_instance_rejects_missing_port_anchor_with_process_id(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-7101-native.json",
        {
            "port": 9950,
            "processId": 7101,
            "pluginType": "native",
        },
    )

    selected = bridge.select_rhino_instance(port=9951, process_id=7102)

    assert selected is None


@pytest.mark.asyncio
async def test_call_rhino_uses_scoped_process_and_document_context(
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

    captured: dict[str, object] = {}

    class FakeResponse:
        def json(self) -> dict[str, object]:
            return {"success": True, "data": "ok"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, params: dict[str, str] | None = None):
            captured["url"] = url
            captured["params"] = params
            return FakeResponse()

    monkeypatch.setattr(bridge.httpx, "AsyncClient", FakeAsyncClient)

    with bridge.rhino_request_context(process_id=7102, document_serial_number=77):
        result = await bridge.call_rhino("/document")

    assert result["success"] is True
    assert captured["url"] == "http://127.0.0.1:9951/document"
    assert captured["params"] == {"documentSerialNumber": "77"}


def test_legacy_native_discovery_does_not_claim_gh_support(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-6001-native.json",
        {
            "port": 9950,
            "processId": 6001,
            "pluginType": "native",
        },
    )

    selected = bridge.select_rhino_instance(endpoint="/gh/query")

    assert selected is None


@pytest.mark.asyncio
async def test_call_rhino_fails_fast_on_duplicate_native_host_port(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-8001-native.json",
        {
            "host": "127.0.0.1",
            "port": 9950,
            "processId": 8001,
            "pluginType": "native",
        },
    )
    _write_instance(
        discovery_dir / "instance-8002-native.json",
        {
            "host": "127.0.0.1",
            "port": 9950,
            "processId": 8002,
            "pluginType": "native",
        },
    )

    result = await bridge.call_rhino("/document", process_id=8002)

    assert result["success"] is False
    assert "Ambiguous native bridge discovery" in result["data"]


def test_get_rhino_host_returns_none_when_no_instance(discovery_dir: Path) -> None:
    """With an empty discovery folder, get_rhino_host() returns None."""
    result = bridge.get_rhino_host()
    assert result is None


def test_get_rhino_host_uses_scoped_process_context(discovery_dir: Path) -> None:
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

    with bridge.rhino_request_context(port=9951, process_id=7102):
        result = bridge.get_rhino_host()

    assert result == "http://127.0.0.1:9951"


def test_get_rhino_host_rejects_scoped_port_with_wrong_process_id(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-7102-native.json",
        {
            "port": 9951,
            "processId": 9999,
            "pluginType": "native",
        },
    )

    with bridge.rhino_request_context(port=9951, process_id=7102):
        result = bridge.get_rhino_host()

    assert result is None


def test_get_rhino_host_rejects_missing_scoped_port_anchor_with_process_id(
    discovery_dir: Path,
) -> None:
    _write_instance(
        discovery_dir / "instance-7101-native.json",
        {
            "port": 9950,
            "processId": 7101,
            "pluginType": "native",
        },
    )

    with bridge.rhino_request_context(port=9951, process_id=7102):
        result = bridge.get_rhino_host()

    assert result is None


@pytest.mark.asyncio
async def test_call_rhino_returns_error_when_no_instance(discovery_dir: Path) -> None:
    """call_rhino() returns structured error when no instance is discovered."""
    result = await bridge.call_rhino("/ping")

    assert result["success"] is False
    assert "No Rhino instance discovered" in result["data"]


# ─── Host loopback validation (security Phase 1B) ────────────────────


def test_normalize_instance_overrides_non_loopback_host() -> None:
    """A forged discovery file with a non-loopback host is overridden."""
    data = bridge._normalize_instance(
        {"port": 9999, "processId": 1, "pluginType": "native", "host": "evil.com"}
    )
    assert data["host"] == "127.0.0.1"


def test_normalize_instance_accepts_loopback_hosts() -> None:
    """Legitimate loopback hosts are preserved (and normalized)."""
    for host in ("127.0.0.1", "localhost"):
        data = bridge._normalize_instance(
            {"port": 9999, "processId": 1, "pluginType": "native", "host": host}
        )
        assert data["host"] == host


def test_normalize_instance_rejects_ipv6_loopback() -> None:
    """::1 is overridden — bridge URL construction doesn't bracket IPv6."""
    data = bridge._normalize_instance(
        {"port": 9999, "processId": 1, "pluginType": "native", "host": "::1"}
    )
    assert data["host"] == "127.0.0.1"


def test_normalize_instance_normalizes_localhost_case() -> None:
    """LOCALHOST, Localhost, etc. are accepted and lowercased."""
    data = bridge._normalize_instance(
        {"port": 9999, "processId": 1, "pluginType": "native", "host": " LOCALHOST "}
    )
    assert data["host"] == "localhost"


def test_normalize_instance_defaults_non_string_host() -> None:
    """Non-string host values (int, dict, None) get default host."""
    for bad_host in (123, {"x": 1}, None, ""):
        data = bridge._normalize_instance(
            {"port": 9999, "processId": 1, "pluginType": "native", "host": bad_host}
        )
        assert data["host"] == "127.0.0.1"
