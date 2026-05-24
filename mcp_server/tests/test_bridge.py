import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import bridge


@pytest.fixture(autouse=True)
def reset_targeting_state():
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    yield
    targeting.reset_targeting_state_for_tests()


def _write_instance(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def discovery_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    return tmp_path


def test_resolve_discovery_folder_prefers_localappdata(tmp_path: Path) -> None:
    env = {"LOCALAPPDATA": str(tmp_path / "LocalAppData")}

    folder, folders, diagnostics = bridge.resolve_discovery_folder(env=env, temp_root=tmp_path / "Temp")

    assert folder == tmp_path / "LocalAppData" / "Rook" / "discovery"
    assert folders == [folder, tmp_path / "Temp" / "rook"]
    assert diagnostics["selection"] == "localappdata"
    assert diagnostics["localAppData"] == str(tmp_path / "LocalAppData")
    assert diagnostics["tempRoot"] == str(tmp_path / "Temp")
    assert diagnostics["legacyTempDiscoveryFolder"] == str(tmp_path / "Temp" / "rook")
    assert diagnostics["discoveryFolders"] == [str(folder), str(tmp_path / "Temp" / "rook")]


def test_resolve_discovery_folder_falls_back_to_temp(tmp_path: Path) -> None:
    folder, folders, diagnostics = bridge.resolve_discovery_folder(env={}, temp_root=tmp_path / "Temp")

    assert folder == tmp_path / "Temp" / "rook"
    assert folders == [folder]
    assert diagnostics["selection"] == "temp"
    assert diagnostics["localAppData"] is None
    assert diagnostics["tempRoot"] == str(tmp_path / "Temp")
    assert diagnostics["discoveryFolders"] == [str(folder)]


def test_discovery_diagnostics_reports_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path / "selected")
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path / "selected", tmp_path / "legacy"])
    monkeypatch.setattr(
        bridge,
        "_DISCOVERY_FOLDER_DIAGNOSTICS",
        {
            "selection": "localappdata",
            "localAppData": str(tmp_path / "LocalAppData"),
            "tempRoot": str(tmp_path / "Temp"),
            "legacyTempDiscoveryFolder": str(tmp_path / "Temp" / "rook"),
            "discoveryFolders": [str(tmp_path / "selected"), str(tmp_path / "legacy")],
        },
    )

    diagnostics = bridge.discovery_diagnostics()

    assert diagnostics["discoveryFolder"] == str(tmp_path / "selected")
    assert diagnostics["discoveryFolders"] == [str(tmp_path / "selected"), str(tmp_path / "legacy")]
    assert diagnostics["selection"] == "localappdata"
    assert diagnostics["tempRoot"] == str(tmp_path / "Temp")


def test_discover_instances_reads_legacy_folder_when_primary_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = tmp_path / "primary"
    legacy = tmp_path / "legacy"
    primary.mkdir()
    legacy.mkdir()
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", primary)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [primary, legacy])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    _write_instance(
        legacy / "instance-rc-7101.json",
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "roadcreator",
        },
    )

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["pluginType"] == "roadcreator"
    assert instances[0]["port"] == 9960


def test_discover_instances_honors_discovery_folder_only_monkeypatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = tmp_path / "selected"
    configured = tmp_path / "configured"
    selected.mkdir()
    configured.mkdir()
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", selected)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [configured])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    _write_instance(
        selected / "instance-7101-native.json",
        {
            "host": "127.0.0.1",
            "port": 9950,
            "processId": 7101,
            "pluginType": "native",
        },
    )

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["pluginType"] == "native"
    assert instances[0]["port"] == 9950


def test_discover_instances_prefers_primary_duplicate_identity(
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
    _write_instance(
        primary / "instance-7101-native.json",
        {
            "host": "127.0.0.1",
            "port": 9950,
            "processId": 7101,
            "pluginType": "native",
        },
    )
    _write_instance(
        legacy / "instance-7101-native.json",
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "native",
        },
    )

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["port"] == 9950


def test_process_local_active_target_round_trip() -> None:
    from rook import targeting

    targeting.clear_active_target()
    try:
        targeting.set_active_target(targeting.InstanceRef(port=9950, process_id=7101))
        assert targeting.get_active_target() == targeting.InstanceRef(port=9950, process_id=7101)
    finally:
        targeting.clear_active_target()


def test_resolve_active_target_rejects_pid_mismatch(discovery_dir: Path) -> None:
    from rook import targeting

    _write_instance(
        discovery_dir / "instance-7102-native.json",
        {"port": 9951, "processId": 9999, "pluginType": "native"},
    )

    targeting.clear_active_target()
    try:
        targeting.set_active_target(targeting.InstanceRef(port=9951, process_id=7102))
        resolved = targeting.resolve_active_target()
        assert resolved.success is False
        assert resolved.error == "active_rhino_instance_unavailable"
        assert resolved.target is None
        assert resolved.stale_target == targeting.InstanceRef(port=9951, process_id=7102)
    finally:
        targeting.clear_active_target()


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _CapturingHttpClient:
    def __init__(self, captured: dict, payload: dict | None = None):
        self._captured = captured
        self._payload = payload or {"success": True, "data": {"ok": True}}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params=None):
        self._captured["method"] = "GET"
        self._captured["url"] = str(url)
        self._captured["params"] = params
        return _FakeHttpResponse(self._payload)

    async def post(self, url, json=None):
        self._captured["method"] = "POST"
        self._captured["url"] = str(url)
        self._captured["json"] = json
        return _FakeHttpResponse(self._payload)

    async def request(self, method, url, **kwargs):
        self._captured["method"] = method
        self._captured["url"] = str(url)
        self._captured.update(kwargs)
        return _FakeHttpResponse(self._payload)


@pytest.mark.asyncio
async def test_call_tool_installs_locked_document_context(monkeypatch):
    from rook import server, targeting
    from rook.bridge import get_rhino_request_context

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    captured = {}

    async def fake_dispatch(name, arguments):
        captured["context"] = get_rhino_request_context()
        captured["arguments"] = dict(arguments)
        return {"success": True, "data": {"ok": True}}

    monkeypatch.setattr(server, "_call_tool_dispatch", fake_dispatch)

    await server.call_tool("rhino_document", {})

    assert captured["context"]["process_id"] == 7101
    assert captured["context"]["document_serial_number"] == 42
    assert captured["arguments"]["documentSerialNumber"] == 42


@pytest.mark.asyncio
async def test_call_tool_rejects_conflicting_document_serial(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    result = await server.call_tool("rhino_document", {"documentSerialNumber": 99})
    text = result[0].text

    assert "panel_document_locked" in text
    assert "requestedDocumentSerialNumber" in text


@pytest.mark.asyncio
async def test_panel_lock_blocks_spawn_agent_before_background_task(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    result = await server.call_tool("spawn_agent", {"prompt": "create a box"})

    assert "panel_target_locked" in result[0].text


@pytest.mark.asyncio
async def test_panel_lock_launch_stale_owner_returns_stale(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7109",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    result = await server.call_tool("rhino_launch", {})

    assert "panel_target_stale" in result[0].text


@pytest.mark.asyncio
async def test_panel_lock_launch_live_owner_does_not_auto_bind(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])
    called = {"bind": False}
    monkeypatch.setattr(
        targeting,
        "bind_single_available_instance",
        lambda: called.__setitem__("bind", True),
    )

    async def fake_dispatch(name, arguments):
        return {"success": True, "data": {"status": "launched"}}

    monkeypatch.setattr(server, "_call_tool_dispatch", fake_dispatch)

    result = await server.call_tool("rhino_launch", {})

    assert '"status": "launched"' in result[0].text
    assert called["bind"] is False


@pytest.mark.asyncio
async def test_panel_lock_launch_ping_failure_does_not_spawn_rhino(monkeypatch):
    import os
    import subprocess

    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    async def failed_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        return {"success": False, "data": "ping failed"}

    popen_calls = []
    monkeypatch.setattr(server, "call_rhino", failed_ping)
    monkeypatch.setattr(os.path, "exists", lambda path: True)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: popen_calls.append((args, kwargs)))

    result = await server.call_tool("rhino_launch", {"timeout": 0})

    assert "panel_target_stale" in result[0].text
    assert popen_calls == []


@pytest.mark.asyncio
async def test_call_rhino_defaults_to_panel_locked_process(discovery_dir: Path, monkeypatch):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native",
    })
    captured = {}
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None: _CapturingHttpClient(captured),
    )

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is True
    assert ":9951" in captured["url"]
    assert captured["params"]["documentSerialNumber"] == "42"


@pytest.mark.asyncio
async def test_call_rhino_rejects_conflicting_panel_port(discovery_dir: Path):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native",
    })

    result = await bridge.call_rhino("/document", "GET", {}, port=9950)

    assert result["success"] is False
    assert result["data"]["error"] == "panel_target_locked"


@pytest.mark.asyncio
async def test_call_rhino_rejects_conflicting_panel_document(discovery_dir: Path):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native",
    })

    result = await bridge.call_rhino("/document", "GET", {"documentSerialNumber": 99})

    assert result["success"] is False
    assert result["data"]["error"] == "panel_document_locked"


@pytest.mark.asyncio
async def test_call_rhino_panel_lock_routes_rc_to_same_process_peer(discovery_dir: Path, monkeypatch):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7101-roadcreator.json", {
        "host": "127.0.0.1", "port": 9960, "processId": 7101, "pluginType": "roadcreator",
    })
    _write_instance(discovery_dir / "instance-7102-roadcreator.json", {
        "host": "127.0.0.1", "port": 9961, "processId": 7102, "pluginType": "roadcreator",
    })
    captured = {}
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None: _CapturingHttpClient(captured, {"success": True, "data": {"roads": []}}),
    )

    result = await bridge.call_rhino("/rc/roads")

    assert result["success"] is True
    assert ":9960" in captured["url"]


@pytest.mark.asyncio
async def test_call_rhino_panel_lock_canonicalizes_same_process_extension_port_for_native_endpoint(discovery_dir: Path, monkeypatch):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7101-roadcreator.json", {
        "host": "127.0.0.1", "port": 9960, "processId": 7101, "pluginType": "roadcreator",
    })
    captured = {}
    monkeypatch.setattr(
        bridge.httpx,
        "AsyncClient",
        lambda timeout=None: _CapturingHttpClient(captured, {"success": True, "data": {"name": "A.3dm"}}),
    )

    result = await bridge.call_rhino("/document", port=9960)

    assert result["success"] is True
    assert ":9950" in captured["url"]


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
