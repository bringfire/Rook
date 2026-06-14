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
from .rhino_launch import (
    LaunchExecError,
    LaunchOutcome,
    build_launch_env,
    exec_failure_outcome,
    resolve_requested_scheme,
    start_rhino_process,
    wait_for_rook_readiness,
)
from .bridge import (_process_id_from_session_id, classify_session_liveness,
                     _is_pid_alive, _is_port_listening, DEFAULT_HOST)
from . import registry as _reg
from .registry import get_runtime_owner, reconcile_owned_registry, resolve_registry_path
from . import targeting
from . import artifacts

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
    "workbench_requires_external_scope": False,
    "workbench_registry_claim_failed": True,
    "workbench_launch_retained_after_registry_error": True,
    "workbench_launch_superseded": False,
    "workbench_close_in_progress": True,
    "registry_schema_unsupported": False,
}


@dataclass
class OwnedWorkbench:
    record: "OwnedRhinoRecord | None"   # None for a reclaimed session (no live Popen/record)
    process: Any  # subprocess.Popen OR PidProcessHandle — retained so cleanup can reap it
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


def current_owner_scope() -> str:
    """Live panel scope — recomputed every call, NEVER cached (spec §7). The only
    place workbench imports targeting; the gate that forbids a panel agent from
    reclaiming/closing across its lock."""
    if (targeting.get_panel_target_lock() is not None
            or targeting.get_panel_target_config_error() is not None):
        return "panel_locked"
    return "external"


_REGISTRY: "_reg.OwnedSessionRegistry | None" = None


def _registry() -> "_reg.OwnedSessionRegistry":
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _reg.OwnedSessionRegistry(resolve_registry_path())
    return _REGISTRY


async def _registry_unusable() -> dict[str, Any] | None:
    """Open the registry off-thread and fail CLOSED if its db was written by an
    incompatible version: return a structured error so we never operate on (or
    orphan) ownership rows we can't safely read. Returns None when usable."""
    reg = await asyncio.to_thread(_registry)
    bad = getattr(reg, "schema_unsupported", None)
    if bad is not None:
        return _err("registry_schema_unsupported",
                    f"Owned-session registry was written by an incompatible version {bad!r}; "
                    "ownership rows are left intact. Resolve the version skew before launching "
                    "or closing Workbenches.")
    return None


def _rebind_probe(pid: int) -> int | None:
    """Single discovery re-probe for a launching dead-owner row: did it bind after
    its owner died? Returns the discovered port (PID-correlated) so reconcile can
    promote launching->bound WITH the port (§8.2 L3), else None."""
    try:
        return OwnedRhinoDiscovery().read_owned_record(pid).port
    except DiscoveryError:
        return None


def _reconcile_sync(owner, scope) -> list:
    return reconcile_owned_registry(
        _registry(), owner, scope,
        is_pid_alive=_is_pid_alive,
        is_port_listening=_is_port_listening,
        rebind_probe=_rebind_probe,
        now=lambda: int(time.time()),
    )


def _rebuild_owned(owned_rows) -> None:
    """Derived-cache rebuild: ensure _OWNED has a handle for each owned live row,
    PRESERVING an existing real Popen over a surrogate (spec §9)."""
    keep = set()
    for row in owned_rows:
        keep.add(row.rhino_pid)
        if row.rhino_pid not in _OWNED:
            _OWNED[row.rhino_pid] = OwnedWorkbench(
                record=None, process=PidProcessHandle(row.rhino_pid),
                session=row.session_id, launched_at=row.launched_at)
    for pid in list(_OWNED):
        if pid not in keep:
            _OWNED.pop(pid, None)


_OBSERVE_TIMEOUT_SECONDS = 2.0


async def _best_effort_observe_owned_artifact(inst: dict[str, Any], session_id: str) -> None:
    """Stat-gated durable observe for ONE owned, live Workbench. EVERY failure
    (metadata fetch / stat / SQLite / TIMEOUT) is swallowed — perception must never
    fail OR STALL listing (spec I4). The metadata fetch is BOUNDED so a busy/modal
    Workbench cannot hang rhino_workbench_list. source is hard-coded 'owned_workbench'
    because this is the ONLY caller, reached only from the owned path (I8 is structural)."""
    try:
        md = await asyncio.wait_for(
            targeting.fetch_document_metadata(inst), timeout=_OBSERVE_TIMEOUT_SECONDS)
        path = md.get("documentPath")
        if not isinstance(path, str) or not path.strip():
            return  # unsaved / no durable path
        norm = artifacts.normalize_path(path)
        state, size, mtime = await asyncio.to_thread(artifacts.stat_file_state, norm)
        await asyncio.to_thread(lambda: artifacts.artifact_registry().upsert(
            norm, source="owned_workbench", file_state=state, size=size, mtime=mtime,
            document_name=md.get("documentName"), origin_session_id=session_id,
            label=None, now=int(time.time())))
    except Exception:
        return


async def _observe_owned_artifacts(owned_rows) -> None:
    """Concurrently observe all owned, LIVE workbenches (best-effort). Caps delay at
    ~one observe timeout regardless of fleet size (Codex finding): each per-row attempt
    is already timeout-bounded; gather runs them in parallel, return_exceptions guards
    the gather (each task also swallows internally)."""
    tasks = [
        _best_effort_observe_owned_artifact(
            {"processId": row.rhino_pid, "host": DEFAULT_HOST, "port": row.port}, row.session_id)
        for row in owned_rows if row.port
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def launch_owned_workbench(readiness_timeout_seconds: int = 90) -> dict[str, Any]:
    timeout = _validate_timeout(readiness_timeout_seconds)
    if timeout is None:
        return _err("invalid_readiness_timeout",
                    f"readinessTimeoutSeconds must be a positive number, got "
                    f"{readiness_timeout_seconds!r}.")
    # Panel-scope defense-in-depth (finding 2): a panel-scoped runtime acquires
    # NOTHING. Check BEFORE Popen so we never even launch a Rhino we may not own.
    scope = current_owner_scope()
    if scope != "external":
        return _err("workbench_requires_external_scope",
                    "Only an external coordinator runtime may launch Workbenches.")
    # Fail closed BEFORE Popen if the registry db is an incompatible version — never
    # launch a Rhino we then cannot durably claim (Codex finding 1).
    if (unusable := await _registry_unusable()) is not None:
        return unusable
    exe = _resolve_rhino_exe()
    if not exe.exists():
        return _err("rhino_executable_not_found", f"Rhino executable not found: {exe}")
    launch_env = build_launch_env(os.environ)
    requested = resolve_requested_scheme("RookWorkbench", launch_env.env, env_var="ROOK_WORKBENCH_SCHEME")
    try:
        started = start_rhino_process(
            exe, requested_scheme=requested, env=launch_env.env,
            launch_env_report=launch_env.report,
            # Launch via THIS module's subprocess.Popen so tests patching
            # workbench.subprocess.Popen still intercept; start_rhino_process owns argv (/nosplash).
            # The explicit env is intentionally duplicated here and in start_rhino_process(env=...):
            # removing this lambda later must still preserve the controlled launch environment.
            popen=lambda argv: subprocess.Popen(argv, env=launch_env.env))
    except LaunchExecError as exc:
        # _err derives retryable from _RETRYABLE (workbench_launch_failed -> False); add the
        # structured reason/evidence. NOT retryable by existing policy.
        out = exec_failure_outcome(exc)
        return _err("workbench_launch_failed", out.message,
                    reason=out.reason.value, evidence=out.evidence.to_dict())

    process = started.process
    pid = int(started.pid)
    session = f"rhino-{pid}"
    owner = get_runtime_owner()
    # Durably claim the launch FIRST (first statement after Popen). insert_launching
    # can THROW (DB lock / schema build / disk error) — a CATCHABLE failure that would
    # otherwise leave a live Rhino with no row. Reap-and-report rather than orphan it
    # (finding 1). The lambda defers _registry() into the worker thread (finding 5).
    try:
        await asyncio.to_thread(
            lambda: _registry().insert_launching(session, pid, owner, scope, int(time.time())))
    except Exception as exc:
        return await _reap_unclaimable(process, pid, exc, owner=owner, scope=scope)

    discovery = OwnedRhinoDiscovery()
    started_at = time.monotonic()
    rr = await asyncio.to_thread(
        wait_for_rook_readiness, started, discovery=discovery, ping=ping_native,
        timeout_seconds=timeout, poll_seconds=0.25, describe_windows=describe_windows_for_pid)
    if not rr.outcome.ok:
        return await _handle_launch_failure(rr.outcome, process, pid, session)
    record = rr.record   # the live OwnedRhinoRecord — no re-read, no new failure path

    # bind CAS — a concurrent close may have superseded us. bind() can also THROW
    # (DB error) while the Rhino is already live + bound: reap it and drop the
    # stranded launching claim rather than orphan it (finding 1).
    try:
        outcome = await asyncio.to_thread(lambda: _registry().bind(session, record.port))
    except Exception as exc:
        return await _reap_unclaimable(process, pid, exc, session=session)
    if outcome == "superseded":
        return {"success": False, "data": {
            "code": "workbench_launch_superseded", "processId": pid, "retryable": False,
            "message": "Launch was superseded by a concurrent close; launch again if a "
                       "new Workbench is still wanted."}}

    async with _LOCK:
        _OWNED[pid] = OwnedWorkbench(record=record, process=process, session=session,
                                     launched_at=time.time())
    return {"success": True, "data": {
        "session": session, "processId": pid, "port": record.port, "owned": True,
        "mode": "workbench", "boundInSeconds": round(time.monotonic() - started_at, 2),
        "evidence": rr.outcome.evidence.to_dict()}}


async def _reap_unclaimable(process, pid: int, exc: Exception, *,
                            session: str | None = None,
                            owner=None, scope: str | None = None) -> dict[str, Any]:
    """A live Rhino we could not durably claim (a registry failure). Reap it; delete
    its row ONLY if death is confirmed (§8 L1). If reap FAILS the process is alive, so
    keep a durable claim — retain the existing launching row, or best-effort rescue-
    insert one — so the live process stays listable/closable. Never silently orphan.
    The CODE distinguishes a true failure from a recovered/actionable one (finding 1)."""
    data: dict[str, Any] = {"processId": pid}
    reaped = await asyncio.to_thread(force_owned_process_cleanup, process, [])
    if reaped:
        # confirmed dead -> drop any row that exists; the claim genuinely FAILED.
        if session is not None:
            try:
                await asyncio.to_thread(lambda: _registry().reap(session))
            except Exception:
                pass
        data["code"] = "workbench_registry_claim_failed"
        data["message"] = f"Failed to record the launch in the registry: {exc}"
        data["cleanupStatus"] = "forced_kill"
        data["retryable"] = True
        return {"success": False, "data": data}

    # reap FAILED: the process is ALIVE -> we MUST keep a durable claim, never delete.
    data["cleanupStatus"] = "force_kill_failed"
    if session is None and owner is not None and scope is not None:   # finding 3: scope required to rescue
        candidate = f"rhino-{pid}"
        try:
            await asyncio.to_thread(lambda: _registry().insert_launching(
                candidate, pid, owner, scope, int(time.time())))
            session = candidate
        except Exception:
            session = None
    if session is not None:
        # A durable launching row exists -> RECOVERED, not "claim failed" (finding 1).
        async with _LOCK:
            _OWNED[pid] = OwnedWorkbench(record=None, process=process, session=session,
                                         launched_at=time.time())
        data["code"] = "workbench_launch_retained_after_registry_error"
        data["message"] = (f"Registry error during launch, but the live Workbench was retained "
                           f"and is listable/closable via its session: {exc}")
        data["session"] = session
        data["lifecycleStatus"] = "launching"
        data["port"] = None
        data["retryable"] = True
    else:
        data["code"] = "workbench_registry_claim_failed"
        data["message"] = f"Failed to record the launch in the registry: {exc}"
        data["unclaimableResidual"] = True
        data["retryable"] = False
    return {"success": False, "data": data}


async def _handle_launch_failure(outcome: LaunchOutcome, process, pid: int, session: str) -> dict[str, Any]:
    code = _REASON_TO_CODE.get(outcome.reason, "workbench_launch_failed")
    data: dict[str, Any] = {"code": code, "message": outcome.message, "processId": pid,
                            "retryable": _RETRYABLE.get(code, True),
                            "reason": outcome.reason.value if outcome.reason else None,
                            "evidence": outcome.evidence.to_dict()}
    if outcome.reason is DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY:
        windows = outcome.evidence.windows  # captured at readiness-failure time (no re-enum)
        if windows:
            data["blockingWindows"] = windows
            data["diagnosticConfidence"] = "window_present_no_discovery"
            data["next_action"] = (
                "RookNative never published discovery before the timeout and a startup "
                "window was open — likely a modal (license/activation, 'another instance', "
                "or template chooser). The launch was cleaned up; resolve the underlying "
                "condition (e.g., activate Rhino) and retry.")
    reaped = await asyncio.to_thread(force_owned_process_cleanup, process, [])
    if reaped:
        # confirmed dead -> drop the durable row (§8 L1). The process is ALREADY dead,
        # so a registry hiccup here must NOT escape as an unstructured exception
        # (finding 2): return the structured launch-failure envelope; the stale dead
        # row is reaped later by reconcile (rhino pid dead -> DELETE).
        try:
            await asyncio.to_thread(lambda: _registry().reap(session))
        except Exception as reap_exc:
            data["registryCleanupError"] = str(reap_exc)
        data["cleanupStatus"] = "forced_kill"
    else:
        # process alive but unkillable -> RETAIN the launching row + return a handle (§8.4)
        async with _LOCK:
            _OWNED[pid] = OwnedWorkbench(record=None, process=process, session=session,
                                        launched_at=time.time())
        data["cleanupStatus"] = "force_kill_failed"
        data["session"] = session
        data["lifecycleStatus"] = "launching"
        data["port"] = None
        data["retryable"] = True
    return {"success": False, "data": data}


async def list_owned_workbenches() -> dict[str, Any]:
    if (unusable := await _registry_unusable()) is not None:
        return unusable
    owner = get_runtime_owner()
    scope = current_owner_scope()
    owned_rows = await asyncio.to_thread(_reconcile_sync, owner, scope)
    async with _LOCK:
        _rebuild_owned(owned_rows)
    workbenches = []
    for row in owned_rows:
        inst = {"processId": row.rhino_pid, "host": DEFAULT_HOST, "port": row.port}
        workbenches.append({
            "session": row.session_id,
            "processId": row.rhino_pid,
            "port": row.port,
            "lifecycleStatus": row.status,
            "mode": "workbench",
            "launchedAt": row.launched_at,
            "lastPortUp": (None if row.last_port_up is None else bool(row.last_port_up)),
            # lifecycleStatus carries the lifecycle truth; for a port-less row (launching,
            # or a launching-derived closing) there is no listener to probe, so liveness
            # uses a NEUTRAL state, not a lifecycle word (finding 5).
            "liveness": classify_session_liveness(inst) if row.port else {
                "state": "not_bound", "pidAlive": _is_pid_alive(row.rhino_pid),
                "portListening": False, "code": None},
        })
    # Post-list side effect: durable artifact perception for owned, LIVE workbenches
    # only (I8 structural — this is the owned path). Run CONCURRENTLY so a busy fleet
    # caps the delay at ~one observe timeout, not N. The returned list is unaffected.
    await _observe_owned_artifacts(owned_rows)
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
    # Panel-scope defense-in-depth (same gate as launch): a panel-scoped runtime
    # closes nothing. Distinct code from not_owned (which is "no owned row for you").
    scope = current_owner_scope()
    if scope != "external":
        return _err("workbench_requires_external_scope",
                    "Only an external coordinator runtime may close Workbenches.")
    if (unusable := await _registry_unusable()) is not None:
        return unusable
    owner = get_runtime_owner()
    owned_rows = await asyncio.to_thread(_reconcile_sync, owner, scope)
    async with _LOCK:
        _rebuild_owned(owned_rows)

    pid = _process_id_from_session_id(session)
    if pid is None or pid <= 0:
        return _err("invalid_session_id", f"Not a valid session id: {session!r}")

    # Tx1: verify owner + claim-by-update to 'closing' (or in_progress / not_owned).
    result, row = await asyncio.to_thread(lambda: _registry().claim_for_close(session, owner))
    if result == "not_owned":
        return _err("not_owned",
                    f"Session {session} is not an owned Workbench of this runtime.")
    if result == "close_in_progress":
        return _err("workbench_close_in_progress",
                    f"A close of {session} is already in progress.", session=session)

    async with _LOCK:
        wb = _OWNED.get(pid)
    handle = wb.process if wb is not None else PidProcessHandle(pid)

    # terminate off the event loop
    status, discarded = await asyncio.to_thread(_terminate, handle, graceful)
    success = status in ("forced_kill", "graceful_exit", "already_exited")

    # Tx2: delete on confirmed death, else revert to RESTING (§8.3) — never rest in 'closing'.
    await asyncio.to_thread(lambda: _registry().finish_close(session, owner, success=success))

    if not success:   # force_kill_failed
        async with _LOCK:
            _OWNED[pid] = wb or OwnedWorkbench(record=None, process=handle, session=session,
                                               launched_at=time.time())
        return _err("force_kill_failed", f"Failed to terminate owned Workbench {session}.",
                    session=session)

    async with _LOCK:
        _OWNED.pop(pid, None)
    return {"success": True, "data": {
        "session": session, "owned": True, "mode": "workbench", "closed": True,
        "cleanupStatus": status, "discardedUnsavedChanges": discarded}}
