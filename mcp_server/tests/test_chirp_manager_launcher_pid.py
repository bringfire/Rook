"""The Chirp manager must recognise the adapter behind a venv launcher.

On Windows a venv ``python.exe`` is a launcher: it starts the real interpreter as
a child and waits for it. Chirp records that child's pid in its discovery file,
so the pid never equals the ``Popen`` pid the manager holds. On the installed
runtime this made every first ``chirp_create`` fail with "discovery file did not
appear within 45.0s" while the adapter was alive and healthy; the retry only
worked because the live-discovery fast path never compared pids.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from rook import chirp_manager

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows process tree semantics")

_CHILD_TREE = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "print(child.pid, flush=True)\n"
    "child.wait()\n"
)


@pytest.fixture
def launcher_tree():
    parent = subprocess.Popen(
        [sys.executable, "-c", _CHILD_TREE],
        stdout=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    child_pid = int(parent.stdout.readline().strip())
    try:
        yield parent, child_pid
    finally:
        subprocess.run(["taskkill", "/PID", str(parent.pid), "/T", "/F"], capture_output=True)
        parent.wait(timeout=10)


def test_process_owns_pid_accepts_the_launcher_child(launcher_tree):
    parent, child_pid = launcher_tree
    assert chirp_manager._process_owns_pid(parent, parent.pid) is True
    assert chirp_manager._process_owns_pid(parent, child_pid) is True


def test_process_owns_pid_rejects_unrelated_and_dead_launchers(launcher_tree):
    parent, child_pid = launcher_tree
    assert chirp_manager._process_owns_pid(parent, os.getpid()) is False
    assert chirp_manager._process_owns_pid(parent, None) is False
    assert chirp_manager._process_owns_pid(SimpleNamespace(pid=None, poll=lambda: None), child_pid) is False
    # Once the launcher is gone its pid could be recycled; descendants are no longer owned.
    subprocess.run(["taskkill", "/PID", str(parent.pid), "/T", "/F"], capture_output=True)
    parent.wait(timeout=10)
    assert chirp_manager._process_owns_pid(parent, child_pid) is False


def _fake_startup(monkeypatch, tmp_path, *, discovery, parents):
    chirp_home = tmp_path / "Chirp"
    (chirp_home / "src" / "chirp").mkdir(parents=True)
    python_exe = chirp_home / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")
    monkeypatch.setenv("CHIRP_HOME", str(chirp_home))

    calls = {"discovery": 0}

    def fake_find_live_discovery():
        calls["discovery"] += 1
        # Fast path and the post-lock re-check see nothing; the wait loop sees the file.
        return discovery if calls["discovery"] > 2 else None

    async def fake_sleep(_seconds):
        pass

    async def fake_health(_host, _port):
        return {"status": "ok", "version": "0.1.0", "rook_managed": True}

    started = []

    def fake_start(chirp_home, **_kwargs):
        started.append(chirp_home)
        return SimpleNamespace(pid=4101, poll=lambda: None)

    monkeypatch.setattr(chirp_manager, "_chirp_process", None)
    monkeypatch.setattr(chirp_manager, "_find_live_discovery", fake_find_live_discovery)
    monkeypatch.setattr(chirp_manager, "_parent_pid_map", lambda: parents)
    monkeypatch.setattr(chirp_manager, "_start_chirp", fake_start)
    monkeypatch.setattr(chirp_manager, "_read_health", fake_health)
    monkeypatch.setattr(
        chirp_manager,
        "_classify_model_health",
        lambda host, port, _payload, **_kwargs: {"running": True, "host": host, "port": port, "error": None},
    )
    monkeypatch.setattr(chirp_manager.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(chirp_manager, "STARTUP_MAX_WAIT", 2.0)
    return started


@pytest.mark.asyncio
async def test_startup_accepts_discovery_written_by_the_launcher_child(monkeypatch, tmp_path):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 5001}
    started = _fake_startup(monkeypatch, tmp_path, discovery=discovery, parents={5001: 4101})

    result = await chirp_manager.ensure_chirp_running()

    assert started, "the manager must have started the adapter"
    assert result["running"] is True
    assert result["port"] == 9123


@pytest.mark.asyncio
async def test_startup_still_rejects_discovery_from_an_unrelated_process(monkeypatch, tmp_path):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 5001}
    _fake_startup(monkeypatch, tmp_path, discovery=discovery, parents={5001: 999})

    result = await chirp_manager.ensure_chirp_running()

    assert result["running"] is False
    assert "did not appear" in result["error"]


def test_retirement_terminates_the_launcher_child_not_the_launcher(monkeypatch):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 5001}
    health = {"status": "ok", "rook_managed": True}
    terminated = []
    waits = iter([False, True])
    process = SimpleNamespace(
        pid=4101,
        poll=lambda: None,
        terminate=lambda: pytest.fail("terminating the launcher leaves the adapter running"),
    )

    monkeypatch.setattr(chirp_manager, "_chirp_process", process)
    monkeypatch.setattr(chirp_manager, "_signal_retirement_event", lambda: None)
    monkeypatch.setattr(chirp_manager, "_reset_retirement_event", lambda: None)
    monkeypatch.setattr(chirp_manager, "_wait_for_retirement", lambda _d, _t: next(waits))
    monkeypatch.setattr(chirp_manager, "_read_discovery_for_port", lambda _port: dict(discovery))
    monkeypatch.setattr(chirp_manager, "_parent_pid_map", lambda: {5001: 4101})
    monkeypatch.setattr(chirp_manager, "_terminate_pid", lambda pid: terminated.append(pid))
    monkeypatch.setattr(chirp_manager, "_port_is_available", lambda _h, _p: True)

    assert chirp_manager._retire_discovered_process(discovery, health) == ("127.0.0.1", 9123)
    assert terminated == [5001]


def test_sync_wait_accepts_discovery_written_by_the_launcher_child(monkeypatch):
    discovery = {"host": "127.0.0.1", "port": 9123, "pid": 5001}
    process = SimpleNamespace(pid=4101, poll=lambda: None)
    monkeypatch.setattr(chirp_manager, "_read_discovery_for_port", lambda _port: dict(discovery))
    monkeypatch.setattr(chirp_manager, "_parent_pid_map", lambda: {5001: 4101})
    monkeypatch.setattr(chirp_manager, "_read_health_sync", lambda _h, _p: {"status": "ok", "rook_managed": True})
    monkeypatch.setattr(
        chirp_manager,
        "_classify_model_health",
        lambda host, port, _payload, **_kwargs: {"running": True, "host": host, "port": port, "error": None},
    )

    result = chirp_manager._wait_for_started_process_sync(process, "127.0.0.1", 9123, vertex_required=False)

    assert result["running"] is True
