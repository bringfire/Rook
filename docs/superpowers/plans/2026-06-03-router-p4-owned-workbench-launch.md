# Router P4 — Owned Workbench Session Launch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the owned-Rhino runtime-harness primitives into three coordinator-facing **meta** tools (`rhino_workbench_launch` / `list` / `close`) backed by an in-process owned-set — launching a disposable owned Rhino, waiting for PID-correlated discovery to bind, and closing only what this runtime owns.

**Architecture:** A new `workbench.py` holds the in-process owned-set + `asyncio.Lock`, drives the existing `runtime_harness` primitives (`OwnedRhinoDiscovery.wait_for_ready`, `force_owned_process_cleanup`, `request_external_graceful_close`, `describe_windows_for_pid`) via `asyncio.to_thread`, and maps a new **typed** `DiscoveryFailureReason` to public codes. `runtime_harness` gains the typed reason (no substring matching). `targeting` classifies the three tools as meta + adds `rhino_workbench_close` to the non-routed-`session` exception. `server.call_tool` adds a panel fail-closed guard (lock OR config error) and three dispatch cases.

**Tech Stack:** Python 3.13, `asyncio`, `subprocess`, `httpx` (existing), `pytest` + `pytest-asyncio`. No new dependencies. No RookNative/C++ change.

**Authoritative spec:** `docs/superpowers/specs/2026-06-03-p4-owned-workbench-launch-design.md`. Read it first.

**Commit convention:** every commit ends with the trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` (omitted from the per-step examples for brevity — add it to each).

---

## Source-of-truth facts (verified against current code, post-P3 `main`)

- `runtime_harness.py`: `DiscoveryError(RuntimeError)` (`:66`); `OwnedRhinoDiscovery.read_owned_record(pid)` raises `DiscoveryError("...not found")` when the file is absent (`:946-947`) and other `DiscoveryError`s on validation failure (wrong pid / pluginType / non-loopback / bad port / malformed JSON, `:951-976`). `wait_for_ready` (`:986-1035`) loop: `process.poll()` exit check (raises before/after `saw_discovery`); reads the record (caught into `last_discovery_error`); pings; on deadline raises one of three terminal `DiscoveryError`s. **The "no file" and "invalid file" cases both populate `last_discovery_error`, so today they are indistinguishable** — `read_owned_record` must tag them.
- Cleanup primitives: `force_owned_process_cleanup(process, diagnostics: list[str]) -> bool` (`:346`; `taskkill /PID <pid> /F` then `process.kill()` fallback; returns `True` if the process is gone — including if `process.poll() is not None` already). `request_external_graceful_close(process, timeout_seconds, ..., diagnostics=None) -> bool` (`:316`; posts WM_CLOSE, waits, force-kills on timeout; returns `True` if it had to force, `False` if WM_CLOSE exited cleanly). `describe_windows_for_pid(pid) -> list[dict]` (`:287`; `[{hwnd,visible,title}]`, `[]` on non-Windows). `ping_native(host, port) -> bool` is async (`:920`).
- `targeting.py`: `_META_TOOLS` set begins `:539`; `_ALL_KNOWN_TOOLS` `:139`; `_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {"rhino_session_capabilities"}` + `allows_non_routed_session_argument(name)` (from P3). `policy_for_tool` returns `RhinoToolPolicy(False, "meta")` for `_META_TOOLS` members.
- `server.py` `call_tool` (`:19291`): config-error guard fires only for `requires_rhino or name == "rhino_launch"` (`:19296`); `spawn_agent`/`plan_and_execute` lock guard (`:19303`); non-routed branch (`:19315`). Meta dispatch cases live in `_call_tool_dispatch`'s `match name:` (`rhino_instances` `:12724`, `rhino_sessions` `:12727`, … `rhino_launch` `:12746`).
- Tests: `test_runtime_harness.py` has `FakeProcess(pid, poll_results: list[int|None])` (`:42`), `PingRecorder([bool])` (`:54`), `FakeClock` (`:66`), `_write_record(dir, pid, record)` (`:100`), `_native_record(pid, **overrides)` (`:106`); `wait_for_ready` tests at `:430`/`:469`/`:508`. `test_multi_instance_targeting.py` drives `server.call_tool` with `patch.object(server, "call_rhino", new_callable=AsyncMock)`.

**Run command (P4 unit tasks), from repo root:**
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py mcp_server/tests/test_runtime_harness.py -v
```
Regression (Task 5 + final): add `mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_session_routing.py`.

---

## File Structure

- **Modify** `mcp_server/src/rook/runtime_harness.py` — add `DiscoveryFailureReason` enum; give `DiscoveryError` a `reason`; tag `read_owned_record`'s two failure paths; set the five terminal reasons in `wait_for_ready`.
- **Create** `mcp_server/src/rook/workbench.py` — `OwnedWorkbench` dataclass, module-level `_OWNED` dict + `_LOCK`, `launch_owned_workbench` / `list_owned_workbenches` / `close_owned_workbench`, the reason→code map, the window-hint logic, the cleanup→`cleanupStatus` mapping.
- **Modify** `mcp_server/src/rook/targeting.py` — add the three tool names to `_META_TOOLS` + `_ALL_KNOWN_TOOLS`; add `rhino_workbench_close` to `_NON_ROUTED_SESSION_ARGUMENT_TOOLS`.
- **Modify** `mcp_server/src/rook/server.py` — `import workbench`; three `Tool(...)` decls; three dispatch cases; the panel fail-closed guard.
- **Create** `mcp_server/tests/test_workbench.py`; **Create** `mcp_server/tools/p4_workbench_lifecycle_live_harness.py`; **Modify** `scripts/run_rhino_runtime_harness.py` (smoke choice).

**Not touched:** `src/RookNative/**`, `bridge.call_rhino`, `rhino_launch`, any P5 registry / P6 save path.

---

## Task 1: Typed `DiscoveryFailureReason` on `DiscoveryError`

**Files:**
- Modify: `mcp_server/src/rook/runtime_harness.py` (`DiscoveryError` `:66`; `read_owned_record` `:944-978`; `wait_for_ready` terminal raises `:1003-1032`)
- Test: `mcp_server/tests/test_runtime_harness.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_runtime_harness.py` (the fakes `FakeProcess`/`PingRecorder`/`_write_record`/`_native_record` already exist):

```python
from rook.runtime_harness import DiscoveryFailureReason


def test_wait_for_ready_reason_exited_before_bind(tmp_path: Path):
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, 17]), PingRecorder([True]),
            timeout_seconds=1.0, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.EXITED_BEFORE_BIND


def test_wait_for_ready_reason_exited_before_ready(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, port=9821))
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, 9]), PingRecorder([False]),
            timeout_seconds=1.0, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.EXITED_BEFORE_READY


def test_wait_for_ready_reason_bind_timeout_no_discovery(tmp_path: Path):
    # No file ever written; process stays alive; deadline passes.
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, None, None]), PingRecorder([]),
            timeout_seconds=0.01, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY


def test_wait_for_ready_reason_invalid_discovery_record(tmp_path: Path):
    # A file is present but fails validation (wrong pid); process stays alive.
    _write_record(tmp_path, 1234, _native_record(1234, processId=999))
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, None, None]), PingRecorder([]),
            timeout_seconds=0.01, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.INVALID_DISCOVERY_RECORD


def test_wait_for_ready_reason_bind_timeout_no_ping(tmp_path: Path):
    _write_record(tmp_path, 1234, _native_record(1234, port=9821))
    with pytest.raises(DiscoveryError) as exc:
        OwnedRhinoDiscovery(tmp_path).wait_for_ready(
            1234, FakeProcess(1234, [None, None, None]), PingRecorder([False, False, False]),
            timeout_seconds=0.01, poll_seconds=0,
        )
    assert exc.value.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_PING
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_runtime_harness.py -k reason -v`
Expected: FAIL — `ImportError: cannot import name 'DiscoveryFailureReason'`.

- [ ] **Step 3: Write minimal implementation**

In `runtime_harness.py`, replace `class DiscoveryError(RuntimeError): pass` (`:66-67`) with the enum + a reason-carrying error:

```python
class DiscoveryFailureReason(Enum):
    FILE_NOT_FOUND = "file_not_found"
    INVALID_RECORD = "invalid_record"
    EXITED_BEFORE_BIND = "exited_before_bind"
    EXITED_BEFORE_READY = "exited_before_ready"
    BIND_TIMEOUT_NO_DISCOVERY = "bind_timeout_no_discovery"
    BIND_TIMEOUT_NO_PING = "bind_timeout_no_ping"
    INVALID_DISCOVERY_RECORD = "invalid_discovery_record"


class DiscoveryError(RuntimeError):
    def __init__(self, message: str, *, reason: "DiscoveryFailureReason | None" = None):
        super().__init__(message)
        self.reason = reason
```

In `read_owned_record`, tag the absent-file raise (`:946-947`) with `reason=DiscoveryFailureReason.FILE_NOT_FOUND`, and **every other** `DiscoveryError(...)` raise in that method (malformed JSON, non-object, wrong processId, bad pluginType, non-loopback host, invalid port — `:951`–`:976`) with `reason=DiscoveryFailureReason.INVALID_RECORD`. Example:

```python
        if not path.exists():
            raise DiscoveryError(
                f"owned Rhino discovery file not found: {path}",
                reason=DiscoveryFailureReason.FILE_NOT_FOUND,
            )
        ...
        if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id != pid:
            raise DiscoveryError(
                f"wrong processId in owned Rhino discovery file: {process_id}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )
        # ...and likewise for the pluginType / host / port / JSON raises.
```

In `wait_for_ready`, set the terminal reasons. Replace the exit block (`:1003-1010`):

```python
            if exit_code is not None:
                if saw_discovery:
                    raise DiscoveryError(
                        f"Rhino exited with code {exit_code} before RookNative became pingable",
                        reason=DiscoveryFailureReason.EXITED_BEFORE_READY,
                    )
                raise DiscoveryError(
                    f"Rhino exited with code {exit_code} before RookNative discovery appeared",
                    reason=DiscoveryFailureReason.EXITED_BEFORE_BIND,
                )
```

Replace the deadline block (`:1025-1032`):

```python
            if now >= deadline:
                if saw_discovery:
                    raise DiscoveryError(
                        f"owned RookNative discovery for Rhino pid {pid} did not become pingable",
                        reason=DiscoveryFailureReason.BIND_TIMEOUT_NO_PING,
                    )
                if (
                    last_discovery_error is not None
                    and last_discovery_error.reason is DiscoveryFailureReason.INVALID_RECORD
                ):
                    raise DiscoveryError(
                        str(last_discovery_error),
                        reason=DiscoveryFailureReason.INVALID_DISCOVERY_RECORD,
                    ) from last_discovery_error
                raise DiscoveryError(
                    str(last_discovery_error)
                    if last_discovery_error is not None
                    else f"owned Rhino discovery file not found for pid {pid}",
                    reason=DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY,
                )
```

- [ ] **Step 4: Run to verify it passes (+ no harness regression)**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_runtime_harness.py -v`
Expected: PASS (the 5 new reason tests + all existing — the string messages are unchanged, so `match=`-based tests stay green).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/runtime_harness.py mcp_server/tests/test_runtime_harness.py
git commit -m "feat(harness): typed DiscoveryFailureReason on DiscoveryError (no substring matching)"
```

---

## Task 2: `workbench.py` — owned-set + `launch_owned_workbench` (async) + taxonomy

**Files:**
- Create: `mcp_server/src/rook/workbench.py`
- Test: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_workbench.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -k launch -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rook.workbench'`.

- [ ] **Step 3: Write minimal implementation**

Create `mcp_server/src/rook/workbench.py`:

```python
"""Owned Workbench session lifecycle (P4).

Launches a disposable OWNED Rhino, waits for PID-correlated RookNative discovery
to bind, tracks it in an in-process owned-set, and closes only what this runtime
owns. Owns PROCESS lifecycle, not document lifecycle — Save is P6, the durable
cross-process registry is P5. Drives the runtime-harness primitives off-thread.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_harness import (
    DiscoveryError,
    DiscoveryFailureReason,
    OwnedRhinoDiscovery,
    OwnedRhinoRecord,
    describe_windows_for_pid,
    force_owned_process_cleanup,
    ping_native,
    request_external_graceful_close,
)

DEFAULT_RHINO_EXE = Path(r"C:\Program Files\Rhino 8\System\Rhino.exe")
_GRACEFUL_TIMEOUT_SECONDS = 10.0

_REASON_TO_CODE: dict[DiscoveryFailureReason, str] = {
    DiscoveryFailureReason.EXITED_BEFORE_BIND: "workbench_exited_before_bind",
    DiscoveryFailureReason.EXITED_BEFORE_READY: "workbench_exited_before_ready",
    DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY: "workbench_bind_timeout",
    DiscoveryFailureReason.BIND_TIMEOUT_NO_PING: "workbench_listener_unreachable",
    DiscoveryFailureReason.INVALID_DISCOVERY_RECORD: "workbench_discovery_invalid",
}

# Per-code retryability — the single field an agent reads to decide retry vs abandon.
_RETRYABLE: dict[str, bool] = {
    "rhino_executable_not_found": False,
    "workbench_launch_failed": False,
    "workbench_exited_before_bind": True,
    "workbench_exited_before_ready": True,
    "workbench_bind_timeout": True,
    "workbench_discovery_invalid": True,
    "workbench_listener_unreachable": True,
    "invalid_session_id": False,
    "not_owned": False,
    "force_kill_failed": True,
}


@dataclass
class OwnedWorkbench:
    record: OwnedRhinoRecord
    process: Any  # subprocess.Popen — retained so cleanup can reap it
    session: str
    launched_at: float


_OWNED: dict[int, OwnedWorkbench] = {}
_LOCK = asyncio.Lock()


def _err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "data": {
        "code": code, "message": message, "retryable": _RETRYABLE.get(code, True), **extra}}


def _resolve_rhino_exe() -> Path:
    """Server-side resolution: ROOK_RHINO_EXE env override, else the default.
    NEVER sourced from tool arguments (an agent must not launch an arbitrary path)."""
    override = os.environ.get("ROOK_RHINO_EXE")
    return Path(override) if override else DEFAULT_RHINO_EXE


async def launch_owned_workbench(readiness_timeout_seconds: int = 90) -> dict[str, Any]:
    exe = _resolve_rhino_exe()
    if not exe.exists():
        return _err("rhino_executable_not_found", f"Rhino executable not found: {exe}")
    try:
        process = subprocess.Popen([str(exe)])
    except OSError as exc:
        return _err("workbench_launch_failed", f"Rhino launch failed: {exc}")

    pid = int(process.pid)
    discovery = OwnedRhinoDiscovery()
    started = time.monotonic()
    try:
        record = await asyncio.to_thread(
            discovery.wait_for_ready, pid, process, ping_native,
            float(readiness_timeout_seconds), 0.25,
        )
    except DiscoveryError as exc:
        code = _REASON_TO_CODE.get(exc.reason, "workbench_launch_failed")
        data: dict[str, Any] = {"code": code, "message": str(exc), "processId": pid,
                                "retryable": _RETRYABLE.get(code, True)}
        if exc.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY:
            windows = describe_windows_for_pid(pid)  # collect BEFORE reaping
            if windows:
                data["blockingWindows"] = windows
                data["diagnosticConfidence"] = "window_present_no_discovery"
                data["next_action"] = (
                    "RookNative never published discovery before the timeout and a startup "
                    "window was open — likely a modal (license/activation, 'another instance', "
                    "or template chooser). The launch was cleaned up; resolve the underlying "
                    "condition (e.g., activate Rhino) and retry."
                )
        # Ownership invariant: a failed launch is NEVER tracked and ALWAYS reaped
        # (own-it-if-bound, clean-it-up-if-failed) — no launched-but-orphaned middle ground.
        # Run the blocking taskkill/wait OFF the event loop.
        await asyncio.to_thread(force_owned_process_cleanup, process, [])
        return {"success": False, "data": data}

    session = f"rhino-{pid}"
    async with _LOCK:
        _OWNED[pid] = OwnedWorkbench(
            record=record, process=process, session=session, launched_at=time.time(),
        )
    return {
        "success": True,
        "data": {
            "session": session,
            "processId": pid,
            "port": record.port,
            "owned": True,
            "mode": "workbench",
            "boundInSeconds": round(time.monotonic() - started, 2),
        },
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -k launch -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/workbench.py mcp_server/tests/test_workbench.py
git commit -m "feat(workbench): owned-set + async launch_owned_workbench with typed failure codes"
```

---

## Task 3: `workbench.py` — `list_owned_workbenches` + `close_owned_workbench`

**Files:**
- Modify: `mcp_server/src/rook/workbench.py`
- Test: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_workbench.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -k "list or close" -v`
Expected: FAIL — `AttributeError: module 'rook.workbench' has no attribute 'list_owned_workbenches'`.

- [ ] **Step 3: Write minimal implementation**

Add to `workbench.py` the imports `from .bridge import _process_id_from_session_id, classify_session_liveness, session_id_for_instance` (extend the existing import region), then:

```python
async def list_owned_workbenches() -> dict[str, Any]:
    async with _LOCK:
        snapshot = list(_OWNED.values())
    workbenches = []
    for wb in snapshot:
        inst = {"processId": wb.record.pid, "host": wb.record.host, "port": wb.record.port}
        workbenches.append({
            "session": wb.session,
            "processId": wb.record.pid,
            "port": wb.record.port,
            "mode": "workbench",
            "launchedAt": wb.launched_at,
            "liveness": classify_session_liveness(inst),
        })
    return {"success": True, "data": {"workbenches": workbenches}}


def _terminate(process, graceful: bool) -> tuple[str, bool]:
    """Return (cleanupStatus, discardedUnsavedChanges). Caller handles set pruning.

    Runs blocking primitives (WM_CLOSE wait, taskkill) — invoke via asyncio.to_thread.
    """
    if process.poll() is not None:
        return ("already_exited", False)
    if graceful:
        # request_external_graceful_close GUARANTEES termination (WM_CLOSE, then kill on
        # timeout); trust its return rather than re-polling the process.
        had_to_force = request_external_graceful_close(
            process, _GRACEFUL_TIMEOUT_SECONDS, diagnostics=[])
        return ("forced_kill" if had_to_force else "graceful_exit", bool(had_to_force))
    if force_owned_process_cleanup(process, []):
        return ("forced_kill", True)
    return ("force_kill_failed", True)


async def close_owned_workbench(session: str, graceful: bool = False) -> dict[str, Any]:
    pid = _process_id_from_session_id(session)
    if pid is None or pid <= 0:
        return _err("invalid_session_id", f"Not a valid session id: {session!r}")
    async with _LOCK:
        wb = _OWNED.pop(pid, None)
    if wb is None:
        return _err("not_owned",
                    f"Session {session} is not an owned Workbench of this runtime; "
                    "only sessions launched here can be closed.")

    # _terminate runs blocking primitives off the event loop.
    status, discarded = await asyncio.to_thread(_terminate, wb.process, graceful)
    if status == "force_kill_failed":
        async with _LOCK:
            _OWNED[pid] = wb  # retain — still owned, retry-able
        return _err("force_kill_failed", f"Failed to terminate owned Workbench {session}.",
                    session=session)
    return {
        "success": True,
        "data": {
            "session": session,
            "owned": True,
            "mode": "workbench",
            "closed": True,
            "cleanupStatus": status,
            "discardedUnsavedChanges": discarded,
        },
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -v`
Expected: PASS (all launch + list + close tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/workbench.py mcp_server/tests/test_workbench.py
git commit -m "feat(workbench): list + close (owned-only guard, cleanupStatus mapping, retain on force-fail)"
```

---

## Task 4: `targeting` wiring (meta + non-routed-`session` exception)

**Files:**
- Modify: `mcp_server/src/rook/targeting.py` (`_META_TOOLS` `:539`, `_ALL_KNOWN_TOOLS` `:139`, `_NON_ROUTED_SESSION_ARGUMENT_TOOLS`)
- Test: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_workbench.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -k "meta or non_routed" -v`
Expected: FAIL — the workbench tools resolve to `UNKNOWN_TOOL_POLICY` (`requires_rhino=True`, `mutate`).

- [ ] **Step 3: Write minimal implementation**

In `targeting.py`, add the three names to `_ALL_KNOWN_TOOLS` (the set at `:139`) and to `_META_TOOLS` (the set at `:539`), and add `rhino_workbench_close` to `_NON_ROUTED_SESSION_ARGUMENT_TOOLS`:

```python
_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {"rhino_session_capabilities", "rhino_workbench_close"}
```

(Insert `"rhino_workbench_close"`, `"rhino_workbench_launch"`, `"rhino_workbench_list"` as members of both `_ALL_KNOWN_TOOLS` and `_META_TOOLS`, alphabetically near the other `rhino_*` meta entries.)

- [ ] **Step 4: Run to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py mcp_server/tests/test_multi_instance_targeting.py -k "meta or non_routed or policy_entry" -v`
Expected: PASS (incl. `test_every_exposed_tool_has_policy_entry` once the tools are exposed in Task 5 — if that test runs before Task 5 it is unaffected, since the tools are not yet in `list_tools`).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_workbench.py
git commit -m "feat(targeting): classify rhino_workbench_* as meta; close joins non-routed-session exception"
```

---

## Task 5: `server.py` — tool decls + dispatch + panel fail-closed guard

**Files:**
- Modify: `mcp_server/src/rook/server.py` (import; three `Tool(...)` near `rhino_launch`'s decl; three dispatch cases near `:12746`; panel guard at `:19315`)
- Test: `mcp_server/tests/test_workbench.py`

- [ ] **Step 1: Write the failing tests**

Append to `mcp_server/tests/test_workbench.py`:

```python
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_call_tool_dispatches_launch(monkeypatch):
    from rook import server, targeting
    targeting.reset_targeting_state_for_tests()
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "session": "rhino-5", "processId": 5,
                             "port": 64000, "owned": True, "mode": "workbench",
                             "boundInSeconds": 1.0}
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py -k "dispatch or not_rejected or fail_closed" -v`
Expected: FAIL — `server.workbench` doesn't exist / the tools aren't dispatched / no panel guard.

- [ ] **Step 3: Write minimal implementation**

In `server.py`, add the import near the other intra-package imports: `from rook import workbench` (or `from . import workbench` — match the file's existing style).

Add three `Tool(...)` declarations in `list_tools` (near the `rhino_launch` declaration):

```python
        Tool(
            name="rhino_workbench_launch",
            description="Launch an OWNED, disposable Workbench Rhino and wait for it to bind. "
                        "Returns a session id you can route work to. Owned by this runtime only.",
            inputSchema={"type": "object", "properties": {
                "readinessTimeoutSeconds": {"type": "integer", "description": "Bind wait (default 90)."}}},
        ),
        Tool(
            name="rhino_workbench_list",
            description="List the Workbench sessions this MCP runtime owns (with liveness). "
                        "Use rhino_sessions for the full discovered fleet.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="rhino_workbench_close",
            description="Close/dispose an OWNED Workbench session (discards unsaved document "
                        "state by design). Only sessions launched by this runtime can be closed.",
            inputSchema={"type": "object", "properties": {
                "session": {"type": "string", "description": "Session id from rhino_workbench_list."},
                "graceful": {"type": "boolean", "description": "Attempt WM_CLOSE first (may stall on a dirty doc)."}},
                "required": ["session"]},
        ),
```

Add the panel guard in `call_tool`, immediately before the `if not policy.requires_rhino:` branch (`:19315`):

```python
    if name in {"rhino_workbench_launch", "rhino_workbench_list", "rhino_workbench_close"}:
        if targeting.get_panel_target_config_error() is not None:
            return _format_tool_result(
                {"success": False, "data": targeting.get_panel_target_config_error()})
        if targeting.get_panel_target_lock() is not None:
            return _format_tool_result(targeting.panel_target_locked_result(
                message="Workbench lifecycle tools are disabled in the panel-locked Claude Code tab."))
```

Add the three dispatch cases in `_call_tool_dispatch`'s `match name:` (after the `case "rhino_launch":` block, before `case "rhino_ping":`):

```python
        case "rhino_workbench_launch":
            result = await workbench.launch_owned_workbench(
                readiness_timeout_seconds=arguments.get("readinessTimeoutSeconds", 90),
            )

        case "rhino_workbench_list":
            result = await workbench.list_owned_workbenches()

        case "rhino_workbench_close":
            result = await workbench.close_owned_workbench(
                session=arguments.get("session"),
                graceful=bool(arguments.get("graceful", False)),
            )
```

- [ ] **Step 4: Run to verify it passes (+ regression)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_session_routing.py -v
```
Expected: PASS. `test_every_exposed_tool_has_policy_entry` stays green (the three tools are now exposed AND classified meta).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_workbench.py
git commit -m "feat(server): rhino_workbench_* tool decls + dispatch + panel fail-closed (lock OR config error)"
```

---

## Task 6: Live smoke verification (against a real owned Rhino)

**Files:**
- Create: `mcp_server/tools/p4_workbench_lifecycle_live_harness.py`
- Modify: `scripts/run_rhino_runtime_harness.py` (add the `p4-workbench-lifecycle` smoke choice)

This smoke is the cleanest of the four — it launches and closes a *real* owned Rhino end-to-end through `server.call_tool`, with **no synthetic records**.

- [ ] **Step 1: Add the smoke choice**

In `scripts/run_rhino_runtime_harness.py`, add a `_smoke_command` branch (after the `p3-session-mutation` branch) and `"p4-workbench-lifecycle"` to the `--smoke` `choices` list:

```python
    if name == "p4-workbench-lifecycle":
        return (
            [sys.executable, "mcp_server/tools/p4_workbench_lifecycle_live_harness.py"],
            repo_root,
        )
```

- [ ] **Step 2: Write the live harness**

Create `mcp_server/tools/p4_workbench_lifecycle_live_harness.py`:

```python
"""Live P4 owned-Workbench lifecycle smoke.

Run via `scripts/run_rhino_runtime_harness.py --smoke p4-workbench-lifecycle`. The
runner launches its OWN owned Rhino (sets ROOK_RHINO_PROCESS_ID) and runs this
smoke. This smoke then launches a SECOND, P4-owned Workbench through the real
server.call_tool path, exercises it, and closes it. The runner's Rhino is NOT in
this process's owned-set, so closing it must fail closed (not_owned) — and the
smoke must NOT terminate it (the runner cleans it up gracefully).

Real end-to-end: no synthetic discovery records.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


_ensure_import_path()

from rook import server  # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str) -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _text(result) -> str:
    return result[0].text if result else ""


def _json(text: str) -> dict:
    # call_tool renders success as json.dumps(data) and failures as "Error: {data}".
    # Strip the prefix so both yield the data payload directly.
    t = text.strip()
    if t.startswith("Error:"):
        t = t[len("Error:"):].strip()
    try:
        return json.loads(t)
    except Exception:
        return {}


async def main() -> int:
    runner_pid = int(os.environ["ROOK_RHINO_PROCESS_ID"])
    print(f"Runner-owned Rhino pid={runner_pid}", flush=True)

    launched_session = None
    try:
        # 1. launch a real owned Workbench
        out = _json(_text(await server.call_tool("rhino_workbench_launch",
                                                 {"readinessTimeoutSeconds": 120})))
        launched_session = out.get("session")
        ok = out.get("owned") is True and out.get("mode") == "workbench" and bool(launched_session)
        _record("workbench_launch", ok, f"session={launched_session} port={out.get('port')}")

        # 2. list shows it, live
        lst = _json(_text(await server.call_tool("rhino_workbench_list", {})))
        sessions = [w.get("session") for w in lst.get("workbenches", [])]
        _record("workbench_list", launched_session in sessions, f"owned={sessions}")

        # 3. a P3-routed mutation lands in it (P3<->P4 compose)
        mut = _text(await server.call_tool(
            "rhino_execute",
            {"session": launched_session, "code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)"}))
        _record("p3_route_into_workbench", not mut.startswith("Error:"), mut[:120])

        # 4. closing the RUNNER's Rhino (not owned here) fails closed; does NOT kill it
        not_owned = _json(_text(await server.call_tool(
            "rhino_workbench_close", {"session": f"rhino-{runner_pid}"})))
        _record("close_adopted_is_not_owned",
                not_owned.get("code") == "not_owned", json.dumps(not_owned)[:120])

        # 5. close the owned Workbench
        closed = _json(_text(await server.call_tool(
            "rhino_workbench_close", {"session": launched_session})))
        launched_session = None if closed.get("closed") else launched_session
        _record("workbench_close", closed.get("closed") is True
                and closed.get("cleanupStatus") in ("forced_kill", "graceful_exit"),
                f"cleanupStatus={closed.get('cleanupStatus')}")

        # 6. list no longer shows it
        lst2 = _json(_text(await server.call_tool("rhino_workbench_list", {})))
        gone = all(w.get("cleanupStatus") != "live" for w in lst2.get("workbenches", []))
        remaining = [w.get("session") for w in lst2.get("workbenches", [])]
        _record("workbench_pruned", closed.get("session") not in remaining, f"remaining={remaining}")
    finally:
        # safety: if we launched a Workbench and did not close it, force-close it now
        if launched_session:
            await server.call_tool("rhino_workbench_close", {"session": launched_session})

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"\n=== P4 live smoke: {passed}/{len(_RESULTS)} PASS ===", flush=True)
    return 0 if passed == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 3: Run the live smoke**

Run: `mcp_server/.venv/Scripts/python.exe scripts/run_rhino_runtime_harness.py --smoke p4-workbench-lifecycle --readiness-timeout 120`
Expected: launches the runner Rhino, then `=== P4 live smoke: 6/6 PASS ===`, runner Rhino `graceful_exit`. Read the artifact manifest's `smoke.stdout` for the per-scenario lines (as in P3). If readiness flakes on cold start, re-run with a larger `--readiness-timeout`.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tools/p4_workbench_lifecycle_live_harness.py scripts/run_rhino_runtime_harness.py
git commit -m "test(p4): live owned-Workbench lifecycle smoke (launch/list/route/close, real owned Rhino)"
```

---

## Task 7: Full regression + finish the branch

- [ ] **Step 1: Targeted regression + baseline parity**

Run the P4 + adjacent suites:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_workbench.py mcp_server/tests/test_runtime_harness.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_session_routing.py mcp_server/tests/test_sessions.py -m "not requires_rhino" -q
```
Expected: all green. (Repo-wide `pytest mcp_server/tests/` is **not** a clean gate — pre-existing script-style/live files; confirm P4 adds no new failures via a baseline diff against `main` if desired, as in P3.)

- [ ] **Step 2: Finish**

Announce and use **superpowers:finishing-a-development-branch** — verify tests, present the 4 options, execute the user's choice (default: push + PR for Codex review, then squash-merge).

---

## Self-Review

**1. Spec coverage** (against `2026-06-03-p4-owned-workbench-launch-design.md`):
- §4 three meta tools + contracts → Tasks 2/3 (functions) + 5 (decls/dispatch). ✅
- §5 owned-set in-process, owned-vs-adopted, close guard, restart/orphan → Task 2 (`_OWNED`) + Task 3 (`not_owned`) + §10 lock. ✅
- §6 PID-correlated wait-for-bind off-thread → Task 2 (`asyncio.to_thread(wait_for_ready)`). ✅
- §7 typed taxonomy (incl. `INVALID_DISCOVERY_RECORD`, window hint only on `bind_timeout`) → Task 1 (typed reason) + Task 2 (mapping + hint). ✅
- §8 direct-force default / graceful ladder / `cleanupStatus` mapping / retain-on-fail → Task 3 (`_terminate`). ✅
- §9 meta-classification + non-routed-`session` exception + panel fail-closed (lock OR config error) → Tasks 4 + 5. ✅
- §10 `asyncio.Lock` at set granularity → Task 2/3. ✅
- §12 unit + live smoke → Tasks 1–5 + Task 6. ✅

**2. Placeholder scan:** No TBD/TODO. Every code step is complete; every run step has a command + expected result. The launch-failure disposition (every failed launch reaped + untracked) is stated explicitly in Task 2's code comment. ✅

**3. Type consistency:** `DiscoveryFailureReason` members match between Task 1 (definition), the Task 1 tests, and Task 2's `_REASON_TO_CODE`. `OwnedWorkbench(record, process, session, launched_at)` is identical in Task 2 (def) and Task 3 (`_register`). Public codes (`workbench_*`, `not_owned`, `force_kill_failed`, `invalid_session_id`) and `cleanupStatus` values (`already_exited`/`forced_kill`/`graceful_exit`) match across Tasks 2/3/6 and the spec. `launch_owned_workbench(readiness_timeout_seconds)` / `close_owned_workbench(session, graceful)` signatures match between `workbench.py` and the server dispatch (Task 5). ✅

---

## Notes / risks for the executor

- **Launch-failure disposition (ownership invariant):** a failed launch is **never** registered in the owned-set and is **always** force-cleaned (`force_owned_process_cleanup`) — including `BIND_TIMEOUT_NO_DISCOVERY`, where the `blockingWindows` snapshot is collected *first*, then the process is reaped. Own-it-if-bound, clean-it-up-if-failed; no launched-but-orphaned middle ground.
- **`asyncio.to_thread` + async ping:** `wait_for_ready` runs in a worker thread; it invokes the async `ping_native` via the harness's existing `_run_awaitable_sync` bridge (proven in the harness's sync orchestrator). Do not "simplify" `ping_native` to a bare coroutine call inside the thread.
- **Lock granularity is load-bearing:** never hold `_LOCK` across `wait_for_ready` (a 90s wait) or across `_terminate` (cleanup I/O). Only the dict mutations are inside the lock. `close` pops under the lock, terminates outside it, and re-inserts under the lock on `force_kill_failed`.
- **The P3 `session`-strip does not apply here** — workbench tools are meta/non-routed; `rhino_workbench_close` reads `arguments.get("session")` on the non-routed path, so it must be in `_NON_ROUTED_SESSION_ARGUMENT_TOOLS` (Task 4).
- **`server.py` imports `workbench` as a module** so tests patch `server.workbench.launch_owned_workbench` etc. Keep the `from rook import workbench` (module) import, not `from .workbench import ...` (names), so the patch points resolve.
