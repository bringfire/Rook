import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import workbench
from rook import registry
from rook.runtime_harness import DiscoveryError, DiscoveryFailureReason, OwnedRhinoRecord


@pytest.fixture(autouse=True)
def clear_owned():
    workbench._OWNED.clear()
    yield
    workbench._OWNED.clear()


def _reset_registry_singleton():
    if workbench._REGISTRY is not None:
        try:
            workbench._REGISTRY.close()
        except Exception:
            pass
    workbench._REGISTRY = None


@pytest.fixture(autouse=True)
def fresh_registry(tmp_path, monkeypatch):
    # Isolate every workbench test's registry to a throwaway db + a fixed runtime
    # identity + external scope. Autouse so the P5 refactor of launch/list/close
    # (now registry-backed) never touches the real %LOCALAPPDATA% registry.
    db = tmp_path / "owned.db"
    # workbench did `from .registry import resolve_registry_path`, so it holds a LOCAL
    # name — patch the name workbench actually calls, not registry's module attribute.
    monkeypatch.setattr(workbench, "resolve_registry_path", lambda: db)
    monkeypatch.setattr(registry, "_RUNTIME_OWNER",
                        registry.RuntimeOwner(pid=4242, token="me-tok", started_at=1))
    monkeypatch.setattr(workbench, "current_owner_scope", lambda: "external")
    # Manage _REGISTRY MANUALLY (not via monkeypatch): monkeypatch would restore a
    # stale closed connection at teardown, so _registry() would reopen the prior
    # (real) db on the next test -> UNIQUE-constraint contamination across tests.
    _reset_registry_singleton()
    yield
    _reset_registry_singleton()


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
    # P5: list is registry-backed (reconcile-at-entry + read rows), not _OWNED.
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    monkeypatch.setattr(workbench, "classify_session_liveness",
                        lambda inst: {"state": "live", "pidAlive": True, "portListening": True})
    reg = workbench._registry()
    reg.insert_launching("rhino-7001", 7001, registry.get_runtime_owner(), "external", 1000)
    reg.bind("rhino-7001", 64001)
    out = await workbench.list_owned_workbenches()
    assert out["success"] is True
    wbs = out["data"]["workbenches"]
    assert len(wbs) == 1
    assert wbs[0]["session"] == "rhino-7001"
    assert wbs[0]["mode"] == "workbench"
    assert wbs[0]["lifecycleStatus"] == "bound"
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


def _seed_registry_owned(pid, port=64700):
    # P5 close is registry-backed: seed a bound row owned by the fixed runtime owner.
    reg = workbench._registry()
    reg.insert_launching(f"rhino-{pid}", pid, registry.get_runtime_owner(), "external", 1000)
    reg.bind(f"rhino-{pid}", port)


@pytest.mark.asyncio
async def test_close_already_exited(monkeypatch):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    _seed_registry_owned(7002)
    _register(7002, _ClosableProc(7002, poll_value=0))  # already exited
    out = await workbench.close_owned_workbench("rhino-7002")
    assert out["success"] is True
    assert out["data"]["cleanupStatus"] == "already_exited"
    assert 7002 not in workbench._OWNED
    assert workbench._registry().get("rhino-7002") is None   # row deleted on success


@pytest.mark.asyncio
async def test_close_default_force(monkeypatch):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: True)
    _seed_registry_owned(7003)
    _register(7003, _ClosableProc(7003))
    out = await workbench.close_owned_workbench("rhino-7003")
    assert out["success"] is True
    assert out["data"]["cleanupStatus"] == "forced_kill"
    assert out["data"]["discardedUnsavedChanges"] is True
    assert 7003 not in workbench._OWNED


@pytest.mark.asyncio
async def test_close_force_failed_keeps_entry(monkeypatch):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: False)
    _seed_registry_owned(7004)
    _register(7004, _ClosableProc(7004))
    out = await workbench.close_owned_workbench("rhino-7004")
    assert out["success"] is False
    assert out["data"]["code"] == "force_kill_failed"
    assert out["data"]["retryable"] is True
    assert 7004 in workbench._OWNED  # retained on failure
    assert workbench._registry().get("rhino-7004").status == registry.BOUND  # reverted to resting


@pytest.mark.asyncio
async def test_close_graceful_clean_exit(monkeypatch):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    # request_external_graceful_close returns False => WM_CLOSE exited cleanly.
    monkeypatch.setattr(workbench, "request_external_graceful_close",
                        lambda p, timeout_seconds, diagnostics=None: False)
    _seed_registry_owned(7005)
    _register(7005, _ClosableProc(7005, poll_value=None))
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


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, "abc", 0, -5, True, False])
async def test_launch_invalid_timeout_rejected_before_popen(monkeypatch, bad):
    called = []
    monkeypatch.setattr(workbench.subprocess, "Popen",
                        lambda *a, **k: called.append(1) or _FakeProc(1))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    out = await workbench.launch_owned_workbench(readiness_timeout_seconds=bad)
    assert out["success"] is False
    assert out["data"]["code"] == "invalid_readiness_timeout"
    assert out["data"]["retryable"] is False
    assert called == []  # Rhino must NOT be launched for a malformed timeout


@pytest.mark.asyncio
async def test_launch_failure_surfaces_cleanup_failure(monkeypatch):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(9001))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid", lambda pid: [])
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: False)  # reap FAILS
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def raise_wfr(self, *a, **k):
        raise DiscoveryError("boom", reason=DiscoveryFailureReason.EXITED_BEFORE_BIND)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", raise_wfr)

    out = await workbench.launch_owned_workbench()
    d = out["data"]
    assert d["code"] == "workbench_exited_before_bind"
    assert d["cleanupStatus"] == "force_kill_failed"   # orphan honestly surfaced
    assert d["processId"] == 9001
    assert d["retryable"] is True


@pytest.mark.asyncio
async def test_launch_failure_reports_forced_kill_when_reaped(monkeypatch):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(9002))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid", lambda pid: [])
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def raise_wfr(self, *a, **k):
        raise DiscoveryError("boom", reason=DiscoveryFailureReason.EXITED_BEFORE_BIND)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", raise_wfr)

    out = await workbench.launch_owned_workbench()
    assert out["data"]["cleanupStatus"] == "forced_kill"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["false", "true", 1, 0, None])
async def test_close_invalid_graceful_flag(bad):
    out = await workbench.close_owned_workbench("rhino-7001", graceful=bad)
    assert out["success"] is False
    assert out["data"]["code"] == "invalid_graceful_flag"
    assert out["data"]["retryable"] is False


# ==== P5 Task 7: PidProcessHandle surrogate ====
def test_pid_process_handle(monkeypatch):
    alive = {555}
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: pid in alive)
    h = workbench.PidProcessHandle(555)
    assert h.pid == 555
    assert h.poll() is None            # alive
    alive.discard(555)
    assert h.poll() == 0               # dead -> exit sentinel
    assert h.returncode == 0


def test_pid_process_handle_wait_timeout(monkeypatch):
    import subprocess
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    h = workbench.PidProcessHandle(556)
    with pytest.raises(subprocess.TimeoutExpired):
        h.wait(timeout=0.05)


# ==== P5 Task 8: registry-backed launch ====
@pytest.mark.asyncio
async def test_launch_writes_bound_row_and_session(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7000))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready",
                        lambda self, *a, **k: _record(7000, port=64500))

    out = await workbench.launch_owned_workbench(readiness_timeout_seconds=5)
    assert out["success"] is True and out["data"]["session"] == "rhino-7000"
    row = workbench._registry().get("rhino-7000")
    assert row.status == registry.BOUND and row.port == 64500
    assert 7000 in workbench._OWNED


@pytest.mark.asyncio
async def test_launch_force_kill_failed_retains_launching_with_session(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7001))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench, "describe_windows_for_pid", lambda pid: [])
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: False)  # reap fails
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready",
                        lambda self, *a, **k: (_ for _ in ()).throw(
                            DiscoveryError("boom", reason=DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY)))

    out = await workbench.launch_owned_workbench()
    d = out["data"]
    assert out["success"] is False
    assert d["session"] == "rhino-7001"
    assert d["lifecycleStatus"] == "launching"
    assert d["port"] is None
    assert d["cleanupStatus"] == "force_kill_failed"
    assert workbench._registry().get("rhino-7001").status == registry.LAUNCHING


@pytest.mark.asyncio
async def test_launch_superseded_when_bind_loses_to_close(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7002))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)

    def wfr_then_close(self, *a, **k):
        # a concurrent close moved the row to 'closing' before bind commits
        workbench._registry()._conn.execute(
            "UPDATE owned_sessions SET status='closing' WHERE session_id='rhino-7002';")
        return _record(7002, port=64502)
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready", wfr_then_close)

    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == "workbench_launch_superseded"
    assert out["data"]["retryable"] is False
    assert workbench._registry().get("rhino-7002").status == registry.CLOSING  # not resurrected


@pytest.mark.asyncio
async def test_launch_registry_claim_failure_reaps(monkeypatch, fresh_registry):
    # insert_launching raises after Popen -> the live Rhino must be REAPED, not orphaned (finding 1).
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7003))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    reaped = []
    monkeypatch.setattr(workbench, "force_owned_process_cleanup",
                        lambda p, d: reaped.append(p.pid) or True)

    class _BoomReg:
        def insert_launching(self, *a, **k):
            raise RuntimeError("db locked")
    monkeypatch.setattr(workbench, "_registry", lambda: _BoomReg())

    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == "workbench_registry_claim_failed"
    assert out["data"]["cleanupStatus"] == "forced_kill"
    assert reaped == [7003]   # the live Rhino was reaped, not orphaned


@pytest.mark.asyncio
async def test_launch_claim_failure_reap_fails_retains(monkeypatch, fresh_registry):
    # bind throws AND cleanup fails -> the live Rhino's launching row must be RETAINED
    # (not deleted), with a session handle returned (finding 1 — delete only when dead).
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7004))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: False)  # reap fails
    monkeypatch.setattr(workbench.OwnedRhinoDiscovery, "wait_for_ready",
                        lambda self, *a, **k: _record(7004, port=64504))

    def boom_bind(self, *a, **k):
        raise RuntimeError("db locked during bind")
    monkeypatch.setattr(workbench._reg.OwnedSessionRegistry, "bind", boom_bind)

    out = await workbench.launch_owned_workbench()
    d = out["data"]
    assert out["success"] is False
    assert d["code"] == "workbench_launch_retained_after_registry_error"   # recovered, not "failed" (finding 1)
    assert d["cleanupStatus"] == "force_kill_failed" and d["retryable"] is True
    assert d["session"] == "rhino-7004" and d["lifecycleStatus"] == "launching"
    assert workbench._registry().get("rhino-7004").status == registry.LAUNCHING  # RETAINED, not deleted
    assert 7004 in workbench._OWNED   # real handle kept for a retry-close


@pytest.mark.asyncio
async def test_launch_insert_failure_rescue_insert(monkeypatch, fresh_registry):
    # initial insert raises, cleanup FAILS (alive), rescue insert succeeds -> a durable
    # launching row is created so the live process is listable/closable (finding 2).
    monkeypatch.setattr(workbench.subprocess, "Popen", lambda *a, **k: _FakeProc(7005))
    monkeypatch.setattr(workbench.Path, "exists", lambda self: True)
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "force_owned_process_cleanup", lambda p, d: False)  # reap fails

    real_insert = workbench._reg.OwnedSessionRegistry.insert_launching
    calls = {"n": 0}
    def flaky_insert(self, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db locked")     # initial claim fails
        return real_insert(self, *a, **k)       # rescue succeeds
    monkeypatch.setattr(workbench._reg.OwnedSessionRegistry, "insert_launching", flaky_insert)

    out = await workbench.launch_owned_workbench()
    d = out["data"]
    assert out["success"] is False
    assert d["code"] == "workbench_launch_retained_after_registry_error"
    assert d["session"] == "rhino-7005" and d["lifecycleStatus"] == "launching"
    assert workbench._registry().get("rhino-7005").status == registry.LAUNCHING  # rescue row exists
    assert 7005 in workbench._OWNED   # listable + closable


@pytest.mark.asyncio
async def test_launch_panel_locked_does_not_popen(monkeypatch, fresh_registry):
    # Panel-scope defense-in-depth (finding 2): refuse BEFORE Popen; never launch a Rhino.
    monkeypatch.setattr(workbench, "current_owner_scope", lambda: "panel_locked")
    popened = []
    monkeypatch.setattr(workbench.subprocess, "Popen",
                        lambda *a, **k: popened.append(1) or _FakeProc(1))

    out = await workbench.launch_owned_workbench()
    assert out["success"] is False
    assert out["data"]["code"] == "workbench_requires_external_scope"
    assert popened == []   # Popen NEVER called under panel lock


# ==== P5 Task 9: list includes launching/closing + lifecycleStatus ====
@pytest.mark.asyncio
async def test_list_includes_launching_and_bound(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    owner = registry.get_runtime_owner()
    reg = workbench._registry()
    reg.insert_launching("rhino-7100", 7100, owner, "external", 1000)
    reg.insert_launching("rhino-7101", 7101, owner, "external", 1000)
    reg.bind("rhino-7101", 64511)

    out = await workbench.list_owned_workbenches()
    by = {w["session"]: w for w in out["data"]["workbenches"]}
    assert by["rhino-7100"]["lifecycleStatus"] == "launching" and by["rhino-7100"]["port"] is None
    assert by["rhino-7101"]["lifecycleStatus"] == "bound" and by["rhino-7101"]["port"] == 64511


# ==== P5 Task 10: registry-backed close ====
def _OWNED_set(pid, session):
    workbench._OWNED[pid] = workbench.OwnedWorkbench(
        record=None, process=workbench.PidProcessHandle(pid), session=session, launched_at=1.0)


@pytest.mark.asyncio
async def test_close_success_deletes_row(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    owner = registry.get_runtime_owner()
    reg = workbench._registry()
    reg.insert_launching("rhino-7200", 7200, owner, "external", 1000)
    reg.bind("rhino-7200", 64600)
    _OWNED_set(7200, "rhino-7200")
    monkeypatch.setattr(workbench, "_terminate", lambda proc, graceful: ("forced_kill", True))

    out = await workbench.close_owned_workbench("rhino-7200")
    assert out["success"] is True and out["data"]["closed"] is True
    assert reg.get("rhino-7200") is None


@pytest.mark.asyncio
async def test_close_force_kill_failed_reverts_to_resting_and_retries(monkeypatch, fresh_registry):
    monkeypatch.setattr(workbench.asyncio, "to_thread", _sync_to_thread)
    monkeypatch.setattr(workbench, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(workbench, "_is_port_listening", lambda host, port: True)
    owner = registry.get_runtime_owner()
    reg = workbench._registry()
    reg.insert_launching("rhino-7201", 7201, owner, "external", 1000)
    reg.bind("rhino-7201", 64601)
    _OWNED_set(7201, "rhino-7201")

    monkeypatch.setattr(workbench, "_terminate", lambda proc, graceful: ("force_kill_failed", True))
    out = await workbench.close_owned_workbench("rhino-7201")
    assert out["success"] is False and out["data"]["code"] == "force_kill_failed"
    assert out["data"]["retryable"] is True
    assert reg.get("rhino-7201").status == registry.BOUND   # back to RESTING, not stuck closing

    # a SECOND close re-enters Tx1 and starts another terminate (now succeeds)
    monkeypatch.setattr(workbench, "_terminate", lambda proc, graceful: ("forced_kill", True))
    out2 = await workbench.close_owned_workbench("rhino-7201")
    assert out2["success"] is True and reg.get("rhino-7201") is None
