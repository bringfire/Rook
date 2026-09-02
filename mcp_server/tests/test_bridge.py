import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import bridge

HOST_GENERATION_ID = "11111111-1111-1111-1111-111111111111"


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


def test_discover_instances_preserves_distinct_routes_for_same_process(
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

    assert sorted(instance["port"] for instance in instances) == [9950, 9960]


def test_discover_instances_collapses_identical_route_records(
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
    record = {
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 7101,
        "pluginType": "native",
        "hostGenerationId": "11111111-1111-1111-1111-111111111111",
    }
    _write_instance(primary / "instance-7101-native.json", record)
    _write_instance(legacy / "instance-7101-native.json", record)

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["port"] == 9950


def test_discover_instances_accepts_rhino_inside_native_record(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-528-native.json",
        {
            "host": "127.0.0.1",
            "port": 57011,
            "processId": 528,
            "pluginType": "native",
            "pluginVersion": "1.5.8",
            "rhinoInside": True,
            "capabilities": {"ghProvider": "callback", "ghRoutes": []},
        },
    )

    instances = bridge.discover_instances()

    assert len(instances) == 1
    assert instances[0]["port"] == 57011
    assert instances[0]["processId"] == 528
    assert instances[0]["pluginType"] == "native"
    assert instances[0]["rhinoInside"] is True
    assert instances[0]["capabilities"] == {"ghProvider": "callback", "ghRoutes": []}


def test_normalize_instance_preserves_capability_domains() -> None:
    raw = {
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 7101,
        "pluginType": "native",
        "capabilities": {
            "schemaVersion": 1,
            "ghProvider": "callback",
            "ghRoutes": [],
            "domainSummary": [
                {
                    "domainId": "bim.rhino_inside_revit",
                    "state": "blocked_by_host",
                    "ready": False,
                    "reasonCode": "not_rhino_inside",
                }
            ],
        },
    }

    normalized = bridge._normalize_instance(raw)

    assert normalized["capabilities"]["schemaVersion"] == 1
    assert normalized["capabilities"]["domainSummary"] == [
        {
            "domainId": "bim.rhino_inside_revit",
            "state": "blocked_by_host",
            "ready": False,
            "reasonCode": "not_rhino_inside",
        }
    ]


def test_get_bootstrap_capability_domain_summary_returns_matching_domain() -> None:
    instance = {
        "capabilities": {
            "domainSummary": [
                {"domainId": "native.core", "state": "ready", "ready": True},
                {"domainId": "bim.rhino_inside_revit", "state": "blocked_by_host", "ready": False},
            ]
        }
    }

    domain = bridge.get_bootstrap_capability_domain_summary(instance, "bim.rhino_inside_revit")

    assert domain == {
        "domainId": "bim.rhino_inside_revit",
        "state": "blocked_by_host",
        "ready": False,
    }


def test_get_bootstrap_capability_domain_summary_handles_older_discovery() -> None:
    instance = {"capabilities": {"ghProvider": "callback", "ghRoutes": []}}

    assert bridge.get_bootstrap_capability_domain_summary(instance, "native.core") is None


@pytest.mark.asyncio
async def test_resolve_capabilities_prefers_live_endpoint_over_bootstrap_summary(monkeypatch):
    instance = {
        "host": "127.0.0.1",
        "port": 9950,
        "processId": 7101,
        "pluginType": "native",
        "capabilities": {
            "liveEndpoint": "/capabilities",
            "summaryKind": "bootstrap_snapshot",
            "authoritative": False,
            "domainSummary": [
                {
                    "domainId": "chat.ui",
                    "state": "not_loaded",
                    "ready": False,
                    "reasonCode": "companion_startup_not_complete",
                }
            ],
        },
    }

    async def fake_fetch_live_capabilities(target, timeout=None):
        assert target is instance
        return {
            "schemaVersion": 1,
            "domains": [
                {
                    "domainId": "chat.ui",
                    "state": "unknown",
                    "ready": False,
                    "reasonCode": "chat_service_state_not_probed_phase1",
                    "companionEvidence": [
                        {
                            "kind": "managed_companion_runtime",
                            "name": "panelsRegistered",
                            "value": True,
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(bridge, "_fetch_live_capabilities", fake_fetch_live_capabilities)

    resolved = await bridge.resolve_capabilities(instance)
    chat = bridge.get_resolved_capability_domain(resolved, "chat.ui")

    assert resolved["source"] == "live"
    assert resolved["stale"] is False
    assert chat["state"] == "unknown"
    assert chat["reasonCode"] == "chat_service_state_not_probed_phase1"
    assert len(chat["companionEvidence"]) == 1


@pytest.mark.asyncio
async def test_resolve_capabilities_marks_bootstrap_fallback_when_live_endpoint_unavailable(monkeypatch):
    instance = {
        "capabilities": {
            "schemaVersion": 1,
            "liveEndpoint": "/capabilities",
            "summaryKind": "bootstrap_snapshot",
            "authoritative": False,
            "generatedUtc": "2026-06-01T13:35:27Z",
            "domainSummary": [
                {
                    "domainId": "chat.ui",
                    "state": "not_loaded",
                    "ready": False,
                    "reasonCode": "companion_startup_not_complete",
                }
            ],
        }
    }

    async def fake_fetch_live_capabilities(target, timeout=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(bridge, "_fetch_live_capabilities", fake_fetch_live_capabilities)

    resolved = await bridge.resolve_capabilities(instance)
    chat = bridge.get_resolved_capability_domain(resolved, "chat.ui")

    assert resolved["source"] == "discovery_bootstrap_fallback"
    assert resolved["stale"] is True
    assert resolved["fallbackReason"] == "connection refused"
    assert resolved["summaryKind"] == "bootstrap_snapshot"
    assert resolved["authoritative"] is False
    assert chat == {
        "domainId": "chat.ui",
        "state": "not_loaded",
        "ready": False,
        "reasonCode": "companion_startup_not_complete",
    }


@pytest.mark.asyncio
async def test_resolve_capabilities_never_trusts_bootstrap_authoritative_flag(monkeypatch):
    instance = {
        "capabilities": {
            "schemaVersion": 1,
            "liveEndpoint": "/capabilities",
            "summaryKind": "bootstrap_snapshot",
            "authoritative": True,
            "domainSummary": [
                {
                    "domainId": "chat.ui",
                    "state": "ready",
                    "ready": True,
                    "reasonCode": "stale_or_malformed_bootstrap_claim",
                }
            ],
        }
    }

    async def fake_fetch_live_capabilities(target, timeout=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(bridge, "_fetch_live_capabilities", fake_fetch_live_capabilities)

    resolved = await bridge.resolve_capabilities(instance)

    assert resolved["source"] == "discovery_bootstrap_fallback"
    assert resolved["stale"] is True
    assert resolved["authoritative"] is False


def test_cleanup_keeps_live_rhino_inside_native_record(
    discovery_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery_dir / "instance-528-native.json"
    _write_instance(
        path,
        {
            "host": "127.0.0.1",
            "port": 57011,
            "processId": 528,
            "pluginType": "native",
            "rhinoInside": True,
        },
    )
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: pid == 528)

    survivors = bridge._cleanup_stale_discovery_files()

    assert path.exists()
    assert len(survivors) == 1
    assert survivors[0]["processId"] == 528


def test_cleanup_removes_dead_rhino_inside_native_record(
    discovery_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = discovery_dir / "instance-528-native.json"
    _write_instance(
        path,
        {
            "host": "127.0.0.1",
            "port": 57011,
            "processId": 528,
            "pluginType": "native",
            "rhinoInside": True,
        },
    )
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)

    survivors = bridge._cleanup_stale_discovery_files()

    assert not path.exists()
    assert survivors == []


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

    def raise_for_status(self) -> None:
        return None


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
        if str(url).endswith("/capabilities"):
            return _FakeHttpResponse({
                "hostGenerationId": HOST_GENERATION_ID,
                "domains": [],
            })
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
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID},
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
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID},
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
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID},
    ])

    result = await server.call_tool("spawn_agent", {"prompt": "create a box"})

    assert "legacy_semantic_tool_contained" in result[0].text


@pytest.mark.asyncio
async def test_panel_lock_launch_unreachable_requires_external_scope(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7109",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": "22222222-2222-2222-2222-222222222222"},
    ])

    async def failed_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        raise RuntimeError("panel target unreachable")

    monkeypatch.setattr(server, "call_rhino", failed_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_launch", {})

    assert "workbench_requires_external_scope" in result[0].text
    assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_panel_lock_launch_live_owner_returns_already_running_without_auto_bind(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID},
    ])
    called = {"bind": False}
    monkeypatch.setattr(
        targeting,
        "bind_single_available_instance",
        lambda: called.__setitem__("bind", True),
    )

    async def reachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        return {"success": True, "data": {"status": "ok"}}

    monkeypatch.setattr(server, "call_rhino", reachable_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_launch", {})

    assert '"status": "already_running"' in result[0].text
    assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
    assert '"auto_bound": true' not in result[0].text
    assert called["bind"] is False
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_panel_lock_launch_ping_failure_does_not_launch_workbench(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID},
    ])

    async def failed_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        return {"success": False, "data": "ping failed"}

    monkeypatch.setattr(server, "call_rhino", failed_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_launch", {"timeout": 0})

    assert "workbench_requires_external_scope" in result[0].text
    assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_rhino_defaults_to_panel_locked_process(discovery_dir: Path, monkeypatch):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": "22222222-2222-2222-2222-222222222222",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID,
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
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": "22222222-2222-2222-2222-222222222222",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID,
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
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID,
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
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID,
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
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native", "hostGenerationId": HOST_GENERATION_ID,
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


def test_select_rhino_instance_rejects_missing_explicit_port(
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

    assert selected is None


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


def test_get_rhino_host_resolves_discovered_explicit_port(discovery_dir: Path) -> None:
    _write_instance(
        discovery_dir / "instance-7101-native.json",
        {
            "port": 9950,
            "processId": 7101,
            "pluginType": "native",
        },
    )

    result = bridge.get_rhino_host(port=9950)

    assert result == "http://127.0.0.1:9950"


def test_get_rhino_host_rejects_missing_explicit_port_without_http_probe(
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

    class UnexpectedAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("get_rhino_host must not create an HTTP client")

    monkeypatch.setattr(bridge.httpx, "AsyncClient", UnexpectedAsyncClient)

    result = bridge.get_rhino_host(port=9999)

    assert result is None


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


@pytest.mark.asyncio
async def test_call_rhino_rejects_missing_explicit_port_without_http_probe(
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
    called = False

    class UnexpectedAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def get(self, url: str, params: dict[str, str] | None = None):
            nonlocal called
            called = True
            raise RuntimeError(f"HTTP client invoked for {url}")

    monkeypatch.setattr(bridge.httpx, "AsyncClient", UnexpectedAsyncClient)

    result = await bridge.call_rhino("/ping", port=9999)

    assert result["success"] is False
    assert "No Rhino instance discovered" in result["data"]
    assert called is False


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
