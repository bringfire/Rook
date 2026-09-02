import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import targeting

HOST_GENERATION_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def reset_targeting_state():
    targeting.reset_targeting_state_for_tests()
    yield
    targeting.reset_targeting_state_for_tests()


def _inst(port: int, pid: int, name: str) -> dict:
    return {
        "host": "127.0.0.1",
        "port": port,
        "processId": pid,
        "pluginType": "native",
        "hostGenerationId": HOST_GENERATION_ID,
        "documentName": name,
    }


@pytest.mark.asyncio
async def test_every_exposed_tool_has_policy_entry():
    from rook.server import list_tools

    tools = await list_tools()
    exposed = {tool.name for tool in tools}
    classified = set(targeting.TOOL_POLICIES)

    assert exposed - classified == set()


def test_unknown_policy_fails_closed():
    policy = targeting.policy_for_tool("not_a_real_tool")
    assert policy.requires_rhino is True
    assert policy.risk == "mutate"


def test_meta_tools_are_resolver_exempt():
    for name in {
        "rhino_instances",
        "rhino_set_active_instance",
        "rhino_get_active_instance",
        "rhino_clear_active_instance",
        "rhino_launch",
        "agent_status",
        "agent_abort",
        "agent_answer",
    }:
        policy = targeting.policy_for_tool(name)
        assert policy.requires_rhino is False
        assert policy.risk == "meta"


def test_background_worker_launch_tools_are_rhino_dependent_mutating():
    for name in {"spawn_agent", "plan_and_execute"}:
        policy = targeting.policy_for_tool(name)
        assert policy.requires_rhino is True
        assert policy.risk == "mutate"


def test_director_tools_have_no_callable_targeting_metadata():
    assert not any(
        name.startswith("rhino_director_") for name in targeting._ALL_KNOWN_TOOLS
    )
    assert not any(
        name.startswith("rhino_director_") for name in targeting.TOOL_POLICIES
    )


def test_gh_update_script_policy_is_explicit_rhino_mutate():
    policy = targeting.policy_for_tool("gh_update_script")
    assert policy == targeting.RhinoToolPolicy(True, "mutate")


def test_solve_readiness_tools_are_explicit_rhino_reads():
    for name in {"gh_solve_readiness", "gh_wait_for_solve_readiness"}:
        assert name in targeting._ALL_KNOWN_TOOLS
        assert targeting.policy_for_tool(name) == targeting.RhinoToolPolicy(
            True, "read"
        )


def test_panel_lock_initializes_from_valid_env(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_locked")
    monkeypatch.setenv("ROOK_MCP_TARGET_HOST_GENERATION_ID", HOST_GENERATION_ID)
    monkeypatch.setenv("ROOK_MCP_TARGET_PROCESS_ID", "7101")
    monkeypatch.setenv("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER", "42")

    targeting.initialize_from_environment()

    lock = targeting.get_panel_target_lock()
    assert lock is not None
    assert lock.mode == "panel_locked"
    assert lock.host_generation_id == HOST_GENERATION_ID
    assert lock.process_id == 7101
    assert lock.document_serial_number == 42
    assert lock.reason == "rook_chat_panel"
    assert targeting.get_panel_target_config_error() is None


def test_panel_lock_missing_process_id_fails_closed(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_locked")
    monkeypatch.setenv("ROOK_MCP_TARGET_HOST_GENERATION_ID", HOST_GENERATION_ID)
    monkeypatch.delenv("ROOK_MCP_TARGET_PROCESS_ID", raising=False)

    targeting.initialize_from_environment()

    assert targeting.get_panel_target_lock() is None
    error = targeting.get_panel_target_config_error()
    assert error is not None
    assert error["error"] == "target_unavailable"


def test_unknown_target_mode_fails_closed(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_lokced")
    monkeypatch.setenv("ROOK_MCP_TARGET_PROCESS_ID", "7101")

    targeting.initialize_from_environment()

    assert targeting.get_panel_target_lock() is None
    error = targeting.get_panel_target_config_error()
    assert error is not None
    assert error["error"] == "target_unavailable"


def test_no_target_mode_preserves_external_behavior(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_HOST_GENERATION_ID", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_PROCESS_ID", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER", raising=False)

    targeting.initialize_from_environment()

    assert targeting.get_panel_target_lock() is None
    assert targeting.get_panel_target_config_error() is None


def test_read_tool_auto_selects_with_warning(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    targeting.clear_active_target()

    route = targeting.resolve_tool_route("rhino_document", explicit_port=None)

    assert route.success is True
    assert route.target == targeting.InstanceRef(9950, 7101)
    assert route.selection == "auto"
    assert route.warning == "multiple_instances"
    assert len(route.alternatives or []) == 1


def test_mutating_tool_refuses_multiple_unbound_instances(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    targeting.clear_active_target()

    route = targeting.resolve_tool_route("rhino_execute", explicit_port=None)

    assert route.success is False
    assert route.error == "multiple_rhino_instances"
    assert route.target is None
    assert len(route.instances or []) == 2


def test_gh_document_open_refuses_multiple_unbound_instances(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    targeting.clear_active_target()

    route = targeting.resolve_tool_route("gh_document_open", explicit_port=None)

    assert route.success is False
    assert route.error == "multiple_rhino_instances"
    assert route.target is None
    assert len(route.instances or []) == 2


def test_panel_lock_routes_read_tool_to_locked_process_without_auto_pick(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_document")

    assert route.success is True
    assert route.selection == "panel_locked"
    assert route.target == targeting.InstanceRef(9951, 7102)
    assert route.document_serial_number == 42
    assert route.warning is None


def test_panel_lock_rejects_explicit_different_process_port(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_execute", explicit_port=9950)

    assert route.success is False
    assert route.error == "panel_target_locked"
    assert route.target is None


def test_panel_lock_stale_owner_wins_over_conflicting_explicit_port(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7109",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_execute", explicit_port=9950)

    assert route.success is False
    assert route.error == "target_unavailable"
    assert route.instances == [_inst(9950, 7101, "A.3dm")]


def test_panel_lock_allows_same_process_roadcreator_peer(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "roadcreator",
            "documentName": "A.3dm",
        },
    ])

    route = targeting.resolve_tool_route("rhino_document", explicit_port=9960)

    assert route.success is True
    assert route.target == targeting.InstanceRef(9950, 7101)
    assert route.selection == "panel_locked"


def test_explicit_port_wins_over_active_binding(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    targeting.clear_active_target()
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))
    try:
        route = targeting.resolve_tool_route("rhino_document", explicit_port=9951)
        assert route.success is True
        assert route.target == targeting.InstanceRef(9951, 7102)
        assert route.selection == "explicit"
    finally:
        targeting.clear_active_target()


def test_explicit_port_still_selects_discovered_target(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_document", explicit_port=9951)

    assert route.success is True
    assert route.target == targeting.InstanceRef(9951, 7102)
    assert route.selection == "explicit"


def test_explicit_missing_port_returns_requested_port_not_discovered(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    monkeypatch.setattr(
        targeting,
        "discovery_diagnostics",
        lambda: {
            "discoveryFolder": r"C:\Users\bring\AppData\Local\Rook\discovery",
            "discoveryFolders": [
                r"C:\Users\bring\AppData\Local\Rook\discovery",
                r"C:\Users\bring\AppData\Local\Temp\rook",
            ],
            "selection": "localappdata",
            "tempRoot": r"C:\Users\bring\AppData\Local\Temp",
            "legacyTempDiscoveryFolder": r"C:\Users\bring\AppData\Local\Temp\rook",
        },
    )
    targeting.clear_active_target()

    route = targeting.resolve_tool_route("rhino_document", explicit_port=9999)
    result = targeting.route_error_result(route)

    assert route.success is False
    assert route.error == "requested_port_not_discovered"
    assert route.target is None
    assert result["success"] is False
    assert result["data"]["error"] == "requested_port_not_discovered"
    assert result["data"]["requestedPort"] == 9999
    assert result["data"]["discoveryFolder"] == r"C:\Users\bring\AppData\Local\Rook\discovery"
    assert result["data"]["discoveryFolders"][1] == r"C:\Users\bring\AppData\Local\Temp\rook"
    assert result["data"]["selection"] == "localappdata"
    assert result["data"]["instances"][0]["port"] == 9950


@pytest.mark.parametrize("raw_port", ["9951", 0, -1, True, False])
def test_invalid_explicit_port_returns_invalid_requested_port(monkeypatch, raw_port):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_document", explicit_port=raw_port)
    result = targeting.route_error_result(route)

    assert route.success is False
    assert route.error == "invalid_requested_port"
    assert result["success"] is False
    assert result["data"]["error"] == "invalid_requested_port"
    assert "requestedPort" not in result["data"]
    assert result["data"]["invalidPort"] == repr(raw_port)


def test_single_rhino_process_with_native_and_roadcreator_is_not_ambiguous(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "roadcreator",
            "documentName": "A.3dm",
        },
    ])
    targeting.clear_active_target()

    route = targeting.resolve_tool_route("rhino_execute", explicit_port=None)

    assert route.success is True
    assert route.target == targeting.InstanceRef(9950, 7101)
    assert route.selection == "auto"


@pytest.mark.asyncio
async def test_bind_match_refuses_ambiguous_matches(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "SK-101-A.3dm"),
        _inst(9951, 7102, "SK-101-B.3dm"),
    ])
    targeting.clear_active_target()

    result = await targeting.bind_active_instance(match="SK-101")

    assert result["success"] is False
    assert result["data"]["error"] == "multiple_rhino_instances"
    assert len(result["data"]["instances"]) == 2
    assert targeting.get_active_target() is None


@pytest.mark.asyncio
async def test_panel_lock_bind_match_prefers_same_process_match(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "SK-101-other.3dm"),
        _inst(9951, 7102, "SK-101-panel.3dm"),
    ])

    result = await targeting.bind_active_instance(match="SK-101")

    assert result["success"] is True
    assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)
    assert result["data"]["locked"] is True


@pytest.mark.asyncio
async def test_panel_lock_bind_match_other_process_only_fails_locked(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "SK-101-other.3dm"),
        _inst(9951, 7102, "Panel.3dm"),
    ])

    result = await targeting.bind_active_instance(match="SK-101")

    assert result["success"] is False
    assert result["data"]["error"] == "panel_target_locked"
    assert targeting.get_active_target() is None


def test_panel_lock_clear_active_instance_fails():
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    targeting.set_active_target(targeting.InstanceRef(9951, 7102))

    result = targeting.clear_active_instance_result()

    assert result["success"] is False
    assert result["data"]["error"] == "panel_target_locked"
    assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)


@pytest.mark.asyncio
async def test_panel_lock_instances_result_reports_lock(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "B.3dm"),
    ])

    result = await targeting.instances_result()

    assert result["success"] is True
    assert result["data"]["lock"]["locked"] is True
    assert result["data"]["lock"]["target"]["processId"] == 7102
    assert result["data"]["lock"]["target"]["documentSerialNumber"] == 42


def test_panel_document_allows_missing_or_matching_serial():
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })

    assert targeting.apply_locked_document_context({}) == {"documentSerialNumber": 42}
    assert targeting.apply_locked_document_context({"documentSerialNumber": 42}) == {"documentSerialNumber": 42}
    assert targeting.apply_locked_document_context({"documentSerialNumber": 0}) == {"documentSerialNumber": 42}


def test_panel_document_rejects_conflicting_positive_serial():
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })

    result = targeting.apply_locked_document_context({"documentSerialNumber": 99})

    assert result["success"] is False
    assert result["data"]["error"] == "panel_document_locked"
    assert result["data"]["requestedDocumentSerialNumber"] == 99


@pytest.mark.asyncio
async def test_bind_by_port_sets_process_identity(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    targeting.clear_active_target()

    result = await targeting.bind_active_instance(port=9950)

    assert result["success"] is True
    assert targeting.get_active_target() == targeting.InstanceRef(9950, 7101)
    assert result["data"]["active"]["port"] == 9950
    assert result["data"]["active"]["processId"] == 7101


@pytest.mark.asyncio
async def test_bind_match_uses_enriched_document_metadata(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    async def fake_document(instance):
        return {
            "documentName": "SK-101.3dm",
            "documentPath": "C:/projects/SK-101.3dm",
            "objectCount": 2290,
        }

    monkeypatch.setattr(targeting, "fetch_document_metadata", fake_document)
    targeting.clear_active_target()

    result = await targeting.bind_active_instance(match="SK-101")

    assert result["success"] is True
    assert targeting.get_active_target() == targeting.InstanceRef(9950, 7101)


@pytest.mark.asyncio
async def test_document_metadata_normalizes_native_document_fields(monkeypatch):
    async def fake_call_document(instance):
        return {
            "success": True,
            "data": {
                "name": "SK-101.3dm",
                "path": "C:/projects/SK-101.3dm",
                "objectCount": 2290,
            },
        }

    monkeypatch.setattr(targeting, "_call_document_for_instance", fake_call_document)

    metadata = await targeting.fetch_document_metadata(
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"}
    )

    assert metadata["documentName"] == "SK-101.3dm"
    assert metadata["documentPath"] == "C:/projects/SK-101.3dm"
    assert metadata["objectCount"] == 2290


@pytest.mark.asyncio
async def test_bind_missing_port_returns_requested_port_not_discovered(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    monkeypatch.setattr(
        targeting,
        "discovery_diagnostics",
        lambda: {
            "discoveryFolder": r"C:\Users\bring\AppData\Local\Rook\discovery",
            "discoveryFolders": [
                r"C:\Users\bring\AppData\Local\Rook\discovery",
                r"C:\Users\bring\AppData\Local\Temp\rook",
            ],
            "selection": "localappdata",
            "tempRoot": r"C:\Users\bring\AppData\Local\Temp",
            "legacyTempDiscoveryFolder": r"C:\Users\bring\AppData\Local\Temp\rook",
        },
    )
    targeting.clear_active_target()

    result = await targeting.bind_active_instance(port=9999)

    assert result["success"] is False
    assert result["data"]["error"] == "requested_port_not_discovered"
    assert result["data"]["requestedPort"] == 9999
    assert result["data"]["discoveryFolder"] == r"C:\Users\bring\AppData\Local\Rook\discovery"
    assert result["data"]["discoveryFolders"][1] == r"C:\Users\bring\AppData\Local\Temp\rook"
    assert len(result["data"]["instances"]) == 1
    assert targeting.get_active_target() is None


@pytest.mark.asyncio
async def test_bind_by_roadcreator_port_canonicalizes_to_native(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "roadcreator",
            "documentName": "A.3dm",
        },
    ])
    targeting.clear_active_target()

    result = await targeting.bind_active_instance(port=9960)

    assert result["success"] is True
    assert targeting.get_active_target() == targeting.InstanceRef(9950, 7101)
    assert result["data"]["active"]["port"] == 9950


@pytest.mark.asyncio
async def test_active_binding_applies_to_handler_that_does_not_pass_port(monkeypatch):
    from rook import bridge
    from rook import server

    monkeypatch.setattr(server, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    targeting.clear_active_target()
    targeting.set_active_target(targeting.InstanceRef(9951, 7102))
    try:
        captured_context = {}

        async def fake_call_rhino(*args, **kwargs):
            captured_context.update(bridge.get_rhino_request_context())
            return {"success": True, "data": []}

        with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
            mock.side_effect = fake_call_rhino
            await server.call_tool("rhino_layers", {})
            assert captured_context["port"] == 9951
            assert captured_context["process_id"] == 7102
            assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)
    finally:
        targeting.clear_active_target()


@pytest.mark.asyncio
async def test_mutating_dispatch_refuses_ambiguous_unbound_instances(monkeypatch):
    from rook import server

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    targeting.clear_active_target()

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_execute", {"code": "print(1)"})
        text = result[0].text
        assert "multiple_rhino_instances" in text
        mock.assert_not_called()


@pytest.mark.asyncio
async def test_single_instance_mutating_dispatch_routes_without_ambiguity(monkeypatch):
    from rook import server

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    targeting.clear_active_target()

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"ok": True}}
        result = await server.call_tool("rhino_execute", {"code": "print(1)"})
        assert "multiple_rhino_instances" not in result[0].text
        mock.assert_awaited()


@pytest.mark.asyncio
async def test_explicit_extension_port_dispatches_canonical_native_port(monkeypatch):
    from rook import server

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "roadcreator",
            "documentName": "A.3dm",
        },
    ])
    targeting.clear_active_target()

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"name": "A.3dm"}}
        await server.call_tool("rhino_document", {"port": 9960})

    _, kwargs = mock.call_args
    assert kwargs.get("port") == 9950


@pytest.mark.asyncio
async def test_set_active_instance_works_when_multiple_instances_exist(monkeypatch):
    from rook import server

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    targeting.clear_active_target()

    result = await server.call_tool("rhino_set_active_instance", {"port": 9951})
    payload = result[0].text
    assert '"active"' in payload
    assert '"port": 9951' in payload
    assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)
    targeting.clear_active_target()


@pytest.mark.asyncio
async def test_set_active_instance_recovers_from_stale_binding(monkeypatch):
    from rook import server

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "Replacement.3dm"),
    ])
    targeting.clear_active_target()
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))

    result = await server.call_tool("rhino_set_active_instance", {"port": 9951})

    assert '"active"' in result[0].text
    assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)
    targeting.clear_active_target()


@pytest.mark.asyncio
async def test_clear_active_instance_clears_binding(monkeypatch):
    from rook import server

    targeting.set_active_target(targeting.InstanceRef(9951, 7102))
    result = await server.call_tool("rhino_clear_active_instance", {})
    assert '"cleared"' in result[0].text
    assert targeting.get_active_target() is None


@pytest.mark.asyncio
async def test_clear_active_instance_without_binding_returns_null(monkeypatch):
    from rook import server

    targeting.clear_active_target()
    result = await server.call_tool("rhino_clear_active_instance", {})
    assert '"cleared": null' in result[0].text
    assert targeting.get_active_target() is None


@pytest.mark.asyncio
async def test_meta_tools_work_with_stale_active_binding(monkeypatch):
    from rook import server

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 9999, "Replacement.3dm"),
    ])
    targeting.clear_active_target()
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))
    try:
        instances = await server.call_tool("rhino_instances", {})
        assert "Replacement.3dm" in instances[0].text

        active = await server.call_tool("rhino_get_active_instance", {})
        assert "active_rhino_instance_unavailable" in active[0].text
    finally:
        targeting.clear_active_target()


@pytest.mark.asyncio
async def test_stale_active_route_error_reports_canonical_native_instances(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "Replacement.3dm"),
        {
            "host": "127.0.0.1",
            "port": 9961,
            "processId": 7102,
            "pluginType": "roadcreator",
            "documentName": "Replacement.3dm",
        },
    ])
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))
    try:
        route = targeting.resolve_tool_route("rhino_document")
        result = targeting.route_error_result(route)

        assert result["data"]["error"] == "active_rhino_instance_unavailable"
        assert result["data"]["stale_target"] == {"port": 9950, "processId": 7101}
        assert result["data"]["instances"] == [_inst(9951, 7102, "Replacement.3dm")]
    finally:
        targeting.clear_active_target()


@pytest.mark.asyncio
async def test_get_active_instance_stale_error_reports_canonical_native_instances(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "Replacement.3dm"),
        {
            "host": "127.0.0.1",
            "port": 9961,
            "processId": 7102,
            "pluginType": "roadcreator",
            "documentName": "Replacement.3dm",
        },
    ])
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))
    try:
        result = await targeting.get_active_instance_result()

        assert result["data"]["error"] == "active_rhino_instance_unavailable"
        assert result["data"]["stale_target"] == {"port": 9950, "processId": 7101}
        assert result["data"]["instances"] == [_inst(9951, 7102, "Replacement.3dm")]
    finally:
        targeting.clear_active_target()


@pytest.mark.asyncio
async def test_panel_lock_get_active_instance_reports_lock_when_active_binding_stale(monkeypatch):
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_HOST_GENERATION_ID": HOST_GENERATION_ID,
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "Panel.3dm"),
    ])
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))

    result = await targeting.get_active_instance_result()

    assert result["success"] is False
    assert result["data"]["error"] == "active_rhino_instance_unavailable"
    assert result["data"]["lock"]["locked"] is True
    assert result["data"]["lock"]["target"]["processId"] == 7102
    assert result["data"]["lock"]["target"]["documentSerialNumber"] == 42


def test_launch_auto_binds_only_without_valid_active_target(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])

    targeting.clear_active_target()
    assert targeting.should_auto_bind_launched_instance() is True
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))
    try:
        assert targeting.should_auto_bind_launched_instance() is False
    finally:
        targeting.clear_active_target()


@pytest.mark.asyncio
async def test_launch_already_running_leaves_stale_active_binding_unchanged(monkeypatch):
    from rook import server

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "Replacement.3dm"),
    ])
    targeting.clear_active_target()
    targeting.set_active_target(targeting.InstanceRef(9950, 7101))
    try:
        with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
            mock.return_value = {"success": True, "data": {"status": "ok"}}
            result = await server.call_tool("rhino_launch", {})

        assert '"already_running"' in result[0].text
        assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
        assert '"auto_bound": true' not in result[0].text
        assert targeting.get_active_target() == targeting.InstanceRef(9950, 7101)
    finally:
        targeting.clear_active_target()


def test_bind_single_available_instance_refuses_multiple_live_targets(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "B.3dm"),
        _inst(9952, 7103, "C.3dm"),
    ])
    targeting.clear_active_target()

    result = targeting.bind_single_available_instance()

    assert result is None
    assert targeting.get_active_target() is None

    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "B.3dm"),
    ])

    result = targeting.bind_single_available_instance()

    assert result == targeting.InstanceRef(9951, 7102)
    assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)
    targeting.clear_active_target()
