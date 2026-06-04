"""Owned Workbench session lifecycle (P4).

Launches a disposable OWNED Rhino, waits for PID-correlated RookNative discovery
to bind, tracks it in an in-process owned-set, and closes only what this runtime
owns. Owns PROCESS lifecycle, not document lifecycle — Save is P6, the durable
cross-process registry is P5. Drives the runtime-harness primitives off-thread.
"""

from __future__ import annotations

import asyncio
import os
import signal
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
from .bridge import (_process_id_from_session_id, classify_session_liveness,
                     _is_pid_alive, _is_port_listening, DEFAULT_HOST)
from . import registry as _reg
from .registry import get_runtime_owner, reconcile_owned_registry, resolve_registry_path
from . import targeting

DEFAULT_RHINO_EXE = Path(r"C:\Program Files\Rhino 8\System\Rhino.exe")


class PidProcessHandle:
    """A pid-backed stand-in for a subprocess.Popen lost across an MCP restart.
    Implements exactly the surface P4's close path touches: .pid/.poll/.wait/.kill
    (spec §13). Reclaimed Workbenches close as cleanly as freshly-launched ones."""

    def __init__(self, pid: int):
        self.pid = int(pid)
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if _is_pid_alive(self.pid):
            return None
        if self.returncode is None:
            self.returncode = 0
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while _is_pid_alive(self.pid):
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(cmd=f"pid {self.pid}", timeout=timeout)
            time.sleep(0.05)
        self.returncode = 0
        return 0

    def kill(self) -> None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(self.pid), "/F"],
                           capture_output=True, text=True, check=False)
        else:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
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
    "invalid_readiness_timeout": False,
    "invalid_graceful_flag": False,
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


def _validate_timeout(value: Any) -> float | None:
    """A positive number → float; bool / null / string / non-positive → None (invalid)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


async def launch_owned_workbench(readiness_timeout_seconds: int = 90) -> dict[str, Any]:
    # Validate the caller input BEFORE launching anything — a malformed timeout must
    # never spawn an orphan Rhino that the except-block cannot reach.
    timeout = _validate_timeout(readiness_timeout_seconds)
    if timeout is None:
        return _err("invalid_readiness_timeout",
                    f"readinessTimeoutSeconds must be a positive number, got "
                    f"{readiness_timeout_seconds!r}.")
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
            discovery.wait_for_ready, pid, process, ping_native, timeout, 0.25,
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
        # Run the blocking taskkill/wait OFF the event loop, and surface a reap failure
        # honestly (an orphan would otherwise be invisible to the coordinator).
        reaped = await asyncio.to_thread(force_owned_process_cleanup, process, [])
        data["cleanupStatus"] = "forced_kill" if reaped else "force_kill_failed"
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
    # Validate inside the module so it protects itself regardless of caller coercion
    # (bool("false") is True — a string must never silently flip into the WM_CLOSE path).
    if not isinstance(graceful, bool):
        return _err("invalid_graceful_flag", f"graceful must be a boolean, got {graceful!r}.")
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
