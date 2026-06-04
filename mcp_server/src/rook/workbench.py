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
