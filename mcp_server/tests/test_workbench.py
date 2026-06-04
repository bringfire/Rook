import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import workbench
from rook.runtime_harness import DiscoveryError, DiscoveryFailureReason, OwnedRhinoRecord


@pytest.fixture(autouse=True)
def clear_owned():
    workbench._OWNED.clear()
    yield
    workbench._OWNED.clear()


class _FakeProc:
    def __init__(self, pid):
        self.pid = pid
    def poll(self):
        return None


def _record(pid, port=9010):
    from pathlib import Path
    return OwnedRhinoRecord(pid=pid, host="127.0.0.1", port=port,
                            path=Path(f"instance-{pid}-native.json"), raw={})


async def _sync_to_thread(fn, *a, **k):
    # Deterministic stand-in for asyncio.to_thread in unit tests: run fn inline.
    # (Launch + close now route BOTH wait_for_ready and the cleanup primitives
    # through to_thread, so we control behaviour by monkeypatching those, not by
    # replacing to_thread wholesale.)
    return fn(*a, **k)


@pytest.mark.asyncio
async def test_launch_success_registers_owned(monkeypatch):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7777))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready",
                        lambda self, *a, **k: _record(7777, port=64000))

    out = await workbench.launch_owned_workbench(readiness_timeout_seconds=5)

    assert out["success"] is True
    d = out["data"]
    assert d["session"] == "rhino-7777"
    assert d["processId"] == 7777
    assert d["port"] == 64000
    assert d["owned"] is True
    assert d["mode"] == "workbench"
    assert 7777 in workbench._OWNED


@pytest.mark.asyncio
async def test_launch_exe_missing(monkeypatch):
    monkeypatch.setattr(workbench.Path, "exists", lambda self: False)
    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == "rhino_executable_not_found"
    assert out["data"]["retryable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,code", [
    (DiscoveryFailureReason.EXITED_BEFORE_BIND, "workbench_exited_before_bind"),
    (DiscoveryFailureReason.EXITED_BEFORE_READY, "workbench_exited_before_ready"),
    (DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY, "workbench_bind_timeout"),
    (DiscoveryFailureReason.INVALID_DISCOVERY_RECORD, "workbench_discovery_invalid"),
    (DiscoveryFailureReason.BIND_TIMEOUT_NO_PING, "workbench_listener_unreachable"),
])
async def test_launch_failure_maps_reason_to_code(monkeypatch, reason, code):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(8888))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid", lambda pid: [])
    reaped = []
    monkeypatch.setattr(workbench, "force_owned_process_cleanup",
                        lambda p, d: reaped.append(p.pid) or True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def raise_wfr(self, *a, **k):
        raise DiscoveryError("boom", reason=reason)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", raise_wfr)

    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == code
    assert out["data"]["retryable"] is True   # all launch DiscoveryError reasons are retryable
    assert 8888 not in workbench._OWNED        # failed launch never registered
    assert reaped == [8888]                    # EVERY failed launch is reaped (incl. bind timeout)


@pytest.mark.asyncio
async def test_bind_timeout_attaches_window_hint(monkeypatch):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(8889))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid",
                        lambda pid: [{"hwnd": "0x1", "visible": True, "title": ""}])
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def raise_wfr(self, *a, **k):
        raise DiscoveryError("timeout", reason=DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", raise_wfr)

    out = await workbench.launch_owned_workbench()
    d = out["data"]
    assert d["code"] == "workbench_bind_timeout"
    assert d["blockingWindows"] == [{"hwnd": "0x1", "visible": True, "title": ""}]
    assert d["diagnosticConfidence"] == "window_present_no_discovery"


@pytest.mark.asyncio
async def test_discovery_invalid_has_no_window_hint(monkeypatch):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(8890))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid",
                        lambda pid: [{"hwnd": "0x1", "visible": True, "title": ""}])
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def raise_wfr(self, *a, **k):
        raise DiscoveryError("bad", reason=DiscoveryFailureReason.INVALID_DISCOVERY_RECORD)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", raise_wfr)

    out = await workbench.launch_owned_workbench()
    assert out["data"]["code"] == "workbench_discovery_invalid"
    assert "blockingWindows" not in out["data"]


class _ClosableProc:
    def __init__(self, pid, poll_value=None):
        self.pid = pid
        self._poll = poll_value
    def poll(self):
        return self._poll


def _register(pid, proc):
    workbench._OWNED[pid] = workbench.OwnedWorkbench(
        record=_record(pid), process=proc, session=f"rhino-{pid}", launched_at=1.0)


@pytest.mark.asyncio
async def test_list_projects_owned_with_liveness(monkeypatch):
    _register(7001, _ClosableProc(7001))
    monkeypatch.setattr(workbench, "classify_session_liveness",
                        lambda inst: {"state": "live", "pidAlive": True, "portListening": True})
    out = await workbench.list_owned_workbenches()
    assert out["success"] is True
    wbs = out["data"]["workbenches"]
    assert len(wbs) == 1
    assert wbs[0]["session"] == "rhino-7001"
    assert wbs[0]["mode"] == "workbench"
    assert wbs[0]["liveness"]["state"] == "live"


@pytest.mark.asyncio
async def test_close_not_owned(monkeypatch):
    out = await workbench.close_owned_workbench("rhino-9999")
    assert out["success"] is False
    assert out["data"]["code"] == "not_owned"
    assert out["data"]["retryable"] is False


@pytest.mark.asyncio
async def test_close_invalid_session():
    out = await workbench.close_owned_workbench("bogus")
    assert out["success"] is False
    assert out["data"]["code"] == "invalid_session_id"
    assert out["data"]["retryable"] is False


@pytest.mark.asyncio
async def test_close_already_exited(monkeypatch):
    _register(7002, _ClosableProc(7002, poll_value=0))  # already exited
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    out = await workbench.close_owned_workbench("rhino-7002")
    assert out["success"] is True
    assert out["data"]["cleanupStatus"] == "already_exited"
    assert 7002 not in workbench._OWNED


@pytest.mark.asyncio
async def test_close_default_force(monkeypatch):
    _register(7003, _ClosableProc(7003))
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    out = await workbench.close_owned_workbench("rhino-7003")
    assert out["success"] is True
    assert out["data"]["cleanupStatus"] == "forced_kill"
    assert out["data"]["discardedUnsavedChanges"] is True
    assert 7003 not in workbench._OWNED


@pytest.mark.asyncio
async def test_close_force_failed_keeps_entry(monkeypatch):
    _register(7004, _ClosableProc(7004))
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: False)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    out = await workbench.close_owned_workbench("rhino-7004")
    assert out["success"] is False
    assert out["data"]["code"] == "force_kill_failed"
    assert out["data"]["retryable"] is True
    assert 7004 in workbench._OWNED  # retained on failure


@pytest.mark.asyncio
async def test_close_graceful_clean_exit(monkeypatch):
    _register(7005, _ClosableProc(7005, poll_value=None))
    # request_external_graceful_close returns False => WM_CLOSE exited cleanly.
    monkeypatch.setattr(workbench, "request_external_graceful_close",
                        lambda p, timeout_seconds, diagnostics=None: False)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    out = await workbench.close_owned_workbench("rhino-7005", graceful=True)
    assert out["data"]["cleanupStatus"] == "graceful_exit"
    assert out["data"]["discardedUnsavedChanges"] is False
    assert 7005 not in workbench._OWNED


def test_workbench_tools_are_meta():
    from rook import targeting
    for name in ("rhino_workbench_launch", "rhino_workbench_list", "rhino_workbench_close"):
        policy = targeting.policy_for_tool(name)
        assert policy.requires_rhino is False
        assert policy.risk == "meta"


def test_workbench_close_allows_non_routed_session():
    from rook import targeting
    assert targeting.allows_non_routed_session_argument("rhino_workbench_close") is True
    assert targeting.allows_non_routed_session_argument("rhino_workbench_launch") is False


@pytest.mark.asyncio
async def test_call_tool_dispatches_launch(monkeypatch):
    from rook import server, targeting
    targeting.reset_targeting_state_for_tests()
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {
            "session": "rhino-5", "processId": 5, "port": 64000,
            "owned": True, "mode": "workbench", "boundInSeconds": 1.0}}
        result = await server.call_tool("rhino_workbench_launch", {})
    assert "rhino-5" in result[0].text
    mock.assert_awaited()


@pytest.mark.asyncio
async def test_call_tool_close_not_rejected_by_p3_guard(monkeypatch):
    # rhino_workbench_close is non-routed + takes `session`; must NOT be
    # session_not_targetable.
    from rook import server, targeting
    targeting.reset_targeting_state_for_tests()
    with patch.object(server.workbench, "close_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {"success": False, "data": {"code": "not_owned", "message": "x"}}
        result = await server.call_tool("rhino_workbench_close", {"session": "rhino-5"})
    assert "session_not_targetable" not in result[0].text
    mock.assert_awaited()


@pytest.mark.asyncio
async def test_workbench_tools_fail_closed_under_panel_lock(monkeypatch):
    from rook import server, targeting
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked", "ROOK_MCP_TARGET_PROCESS_ID": "4242"})
    try:
        result = await server.call_tool("rhino_workbench_launch", {})
        assert "panel_target_locked" in result[0].text
    finally:
        targeting.reset_targeting_state_for_tests()


@pytest.mark.asyncio
async def test_workbench_tools_fail_closed_under_panel_config_error(monkeypatch):
    from rook import server, targeting
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({"ROOK_MCP_TARGET_MODE": "bogus_mode"})
    try:
        result = await server.call_tool("rhino_workbench_launch", {})
        assert "panel_target_config_error" in result[0].text
    finally:
        targeting.reset_targeting_state_for_tests()
