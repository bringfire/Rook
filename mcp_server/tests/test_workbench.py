import os
import sys

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
