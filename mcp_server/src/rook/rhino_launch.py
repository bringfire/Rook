"""Leaf module owning the Rhino launch + readiness primitives.

This is the canonical home for the discovery/readiness/window-read primitives that
`runtime_harness.py` and `workbench.py` both use. They live here (not in
`runtime_harness.py`) so the future launch helpers in this module can reuse them
without `runtime_harness` ↔ `rhino_launch` becoming a circular import.

`runtime_harness.py` re-exports the names below for back-compat; `close_windows_for_pid`
and `WM_CLOSE` (cleanup, not evidence) stay in `runtime_harness.py`.

Imports only stdlib, `httpx`, and the leaf `.bridge` (`resolve_discovery_folder`) — never
`runtime_harness` or `workbench`.
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import dataclasses
import inspect
import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Any, Awaitable, Callable, Protocol

import httpx

from .bridge import resolve_discovery_folder


LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}
MIN_POLL_SECONDS = 0.001


class DiscoveryFailureReason(Enum):
    FILE_NOT_FOUND = "file_not_found"
    INVALID_RECORD = "invalid_record"
    EXITED_BEFORE_BIND = "exited_before_bind"
    EXITED_BEFORE_READY = "exited_before_ready"
    BIND_TIMEOUT_NO_DISCOVERY = "bind_timeout_no_discovery"
    BIND_TIMEOUT_NO_PING = "bind_timeout_no_ping"
    INVALID_DISCOVERY_RECORD = "invalid_discovery_record"
    # Launch-layer extensions (reconcile with — do not fork — the P4 taxonomy above):
    LAUNCH_EXEC_FAILED = "launch_exec_failed"
    SCHEME_AUTOLOAD_NOT_VALIDATED = "scheme_autoload_not_validated"


class DiscoveryError(RuntimeError):
    def __init__(self, message: str, *, reason: "DiscoveryFailureReason | None" = None):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class OwnedRhinoRecord:
    pid: int
    host: str
    port: int
    path: Path
    raw: dict[str, Any]


class ProcessLike(Protocol):
    pid: int
    returncode: int | None

    def poll(self) -> int | None: ...


PingFunction = Callable[[str, int], bool | Awaitable[bool]]


def default_discovery_dir() -> Path:
    folder, _, _ = resolve_discovery_folder(temp_root=Path(tempfile.gettempdir()))
    return folder


def _windows_user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    return user32


def _window_title(user32: ctypes.WinDLL, hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    copied = user32.GetWindowTextW(hwnd, buffer, length + 1)
    if copied <= 0:
        return ""
    return buffer.value


def describe_windows_for_pid(pid: int) -> list[dict[str, Any]]:
    if os.name != "nt":
        return []

    user32 = _windows_user32()
    windows: list[dict[str, Any]] = []

    def enum_window(hwnd, lparam):
        visible = bool(user32.IsWindowVisible(hwnd))
        if not visible:
            return True

        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value == pid:
            windows.append(
                {
                    "hwnd": f"0x{int(hwnd):x}",
                    "visible": visible,
                    "title": _window_title(user32, hwnd),
                }
            )
        return True

    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(enum_windows_proc(enum_window), 0)
    return windows


def _run_awaitable_sync(awaitable: Awaitable[bool]) -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return bool(asyncio.run(awaitable))
    if inspect.iscoroutine(awaitable):
        awaitable.close()
    raise DiscoveryError("async ping function cannot be used from a running event loop")


async def ping_native(host: str, port: int) -> bool:
    from .bridge import native_client  # local import: bridge imports this module

    async with native_client(timeout=3.0) as client:
        try:
            response = await client.get(f"http://{host}:{port}/ping")
        except httpx.HTTPError:
            return False
    if response.text.strip() == "pong":
        return True
    try:
        data = response.json()
    except ValueError:
        return False
    if data == "pong":
        return True
    return isinstance(data, dict) and (data.get("data") == "pong" or data.get("success") is True)


class OwnedRhinoDiscovery:
    def __init__(self, discovery_dir: Path | None = None):
        self.discovery_dir = discovery_dir or default_discovery_dir()

    def owned_path(self, pid: int) -> Path:
        return self.discovery_dir / f"instance-{pid}-native.json"

    def read_owned_record(self, pid: int) -> OwnedRhinoRecord:
        path = self.owned_path(pid)
        if not path.exists():
            raise DiscoveryError(
                f"owned Rhino discovery file not found: {path}",
                reason=DiscoveryFailureReason.FILE_NOT_FOUND,
            )

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DiscoveryError(
                f"malformed JSON in owned Rhino discovery file: {path}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            ) from exc
        if not isinstance(raw, dict):
            raise DiscoveryError(
                f"owned Rhino discovery JSON must be an object: {path}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        process_id = raw.get("processId")
        if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id != pid:
            raise DiscoveryError(
                f"wrong processId in owned Rhino discovery file: {process_id}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        plugin_type = raw.get("pluginType")
        if plugin_type != "native":
            raise DiscoveryError(
                f"unexpected pluginType in owned Rhino discovery file: {plugin_type}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        raw_host = raw.get("host")
        if raw_host is None or raw_host == "":
            host = "127.0.0.1"
        elif not isinstance(raw_host, str):
            raise DiscoveryError(
                f"owned Rhino discovery host must be loopback: {raw_host}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )
        else:
            host = raw_host.strip().lower()
        if host not in LOOPBACK_HOSTS:
            raise DiscoveryError(
                f"owned Rhino discovery host must be loopback: {host}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        port = raw.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or port <= 0:
            raise DiscoveryError(
                f"invalid port in owned Rhino discovery file: {port}",
                reason=DiscoveryFailureReason.INVALID_RECORD,
            )

        return OwnedRhinoRecord(pid=pid, host=host, port=port, path=path, raw=raw)

    def snapshot_owned_record(self, record: OwnedRhinoRecord, artifact_dir: Path) -> Path:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = artifact_dir / f"owned-discovery-{record.path.name}"
        snapshot_path.write_text(json.dumps(record.raw, indent=2), encoding="utf-8")
        return snapshot_path

    def wait_for_ready(
        self,
        pid: int,
        process: ProcessLike,
        ping: PingFunction = ping_native,
        timeout_seconds: float = 30.0,
        poll_seconds: float = 0.25,
        *,
        _monotonic: Callable[[], float] = time.monotonic,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> OwnedRhinoRecord:
        deadline = _monotonic() + timeout_seconds
        last_discovery_error: DiscoveryError | None = None
        saw_discovery = False

        while True:
            exit_code = process.poll()
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

            try:
                record = self.read_owned_record(pid)
            except DiscoveryError as exc:
                last_discovery_error = exc
            else:
                saw_discovery = True
                ping_result = ping(record.host, record.port)
                if inspect.isawaitable(ping_result):
                    ping_result = _run_awaitable_sync(ping_result)
                if ping_result:
                    return record

            now = _monotonic()
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

            wait_seconds = poll_seconds if poll_seconds > 0 else MIN_POLL_SECONDS
            _sleep(min(wait_seconds, deadline - now))


# --------------------------------------------------------------------------------------
# Launch hardening (#222): capability flags, structured outcome/evidence, scheme + argv,
# and the split start/readiness primitives the callers compose.
# --------------------------------------------------------------------------------------

SCHEME_ISOLATION_AVAILABLE = False          # Phase 2 flips this only once autoload is validated
CAN_RESET_SCHEME_RECOVERY_STATE = False     # Phase 2 flips this only once a scheme-local marker is proven


WINDOWS_ENV_INVARIANTS = ("SystemDrive", "SystemRoot", "windir")
CUSTOMIZABLE_LAUNCH_ENV_KEYS = (
    "APPDATA",
    "LOCALAPPDATA",
    "PATH",
    "ProgramData",
    "TEMP",
    "TMP",
    "USERPROFILE",
)
FALLBACK_WINDOWS_DIR = r"C:\Windows"


@dataclass(frozen=True)
class LaunchOsInfo:
    windows_dir: str | None
    windows_dir_exists: bool = True
    fallback_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class LaunchEnvResult:
    env: dict[str, str]
    report: dict[str, Any]


def _discover_windows_launch_os_info() -> LaunchOsInfo:
    if os.name != "nt":
        return LaunchOsInfo(
            windows_dir=FALLBACK_WINDOWS_DIR,
            windows_dir_exists=True,
            fallback_used=("non_windows_fallback",),
        )
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        if length <= 0 or length >= len(buffer):
            return LaunchOsInfo(
                windows_dir=FALLBACK_WINDOWS_DIR,
                windows_dir_exists=True,
                fallback_used=("windows_dir",),
            )
        candidate = buffer.value
        return LaunchOsInfo(
            windows_dir=candidate,
            windows_dir_exists=Path(candidate).exists(),
            fallback_used=(),
        )
    except Exception:
        return LaunchOsInfo(
            windows_dir=FALLBACK_WINDOWS_DIR,
            windows_dir_exists=True,
            fallback_used=("os_info_exception",),
        )


def _non_empty(value: object) -> bool:
    return str(value).strip() != ""


def _sorted_mapping(values: dict[str, str]) -> dict[str, str]:
    return {key: values[key] for key in sorted(values)}


def _resolve_launch_os_info(os_info) -> LaunchOsInfo:
    if os_info is None:
        return _discover_windows_launch_os_info()
    if callable(os_info):
        return os_info()
    return os_info


def _fallback_launch_os_info(extra_fallbacks: list[str] | None = None) -> LaunchOsInfo:
    fallbacks = ["windows_dir"]
    if extra_fallbacks:
        fallbacks = [*extra_fallbacks, *fallbacks]
    return LaunchOsInfo(
        windows_dir=FALLBACK_WINDOWS_DIR,
        windows_dir_exists=True,
        fallback_used=tuple(dict.fromkeys(fallbacks)),
    )


def build_launch_env(base_env=None, os_info=None) -> LaunchEnvResult:
    source = os.environ if base_env is None else base_env
    env = {str(key): str(value) for key, value in source.items()}

    try:
        info = _resolve_launch_os_info(os_info)
    except Exception:
        info = _fallback_launch_os_info(["os_info_exception"])

    if not isinstance(info, LaunchOsInfo):
        info = _fallback_launch_os_info(["os_info_invalid"])
    elif not _non_empty(info.windows_dir) or not info.windows_dir_exists:
        info = _fallback_launch_os_info(list(info.fallback_used))

    windows_dir = str(info.windows_dir or FALLBACK_WINDOWS_DIR).rstrip("\\/")
    system_drive = PureWindowsPath(windows_dir).drive or "C:"

    authoritative = {
        "SystemDrive": system_drive,
        "SystemRoot": windows_dir,
        "windir": windows_dir,
    }
    env.update(authoritative)

    backfilled: dict[str, str] = {}
    inherited: dict[str, str] = {}
    missing_unresolved: list[str] = []

    def has_value(name: str) -> bool:
        return name in env and _non_empty(env[name])

    def inherit_or_backfill(name: str, value: str | None) -> None:
        if has_value(name):
            inherited[name] = env[name]
            return
        if value is not None and _non_empty(value):
            env[name] = value
            backfilled[name] = value
            return
        missing_unresolved.append(name)

    userprofile = env.get("USERPROFILE") if has_value("USERPROFILE") else None
    inherit_or_backfill("USERPROFILE", None)
    inherit_or_backfill("ProgramData", rf"{system_drive}\ProgramData")
    inherit_or_backfill(
        "APPDATA",
        rf"{userprofile}\AppData\Roaming" if userprofile else None,
    )
    inherit_or_backfill(
        "LOCALAPPDATA",
        rf"{userprofile}\AppData\Local" if userprofile else None,
    )

    local_app_data = env.get("LOCALAPPDATA") if has_value("LOCALAPPDATA") else None
    temp_value = rf"{local_app_data}\Temp" if local_app_data else None
    inherit_or_backfill("TEMP", temp_value)
    inherit_or_backfill("TMP", temp_value)
    inherit_or_backfill("PATH", rf"{windows_dir}\System32;{windows_dir}")

    report = {
        "authoritative": _sorted_mapping(authoritative),
        "backfilled": _sorted_mapping(backfilled),
        "inherited": _sorted_mapping(inherited),
        "missing_unresolved": sorted(dict.fromkeys(missing_unresolved)),
        "fallback_used": sorted(dict.fromkeys(info.fallback_used)),
    }
    return LaunchEnvResult(env=env, report=report)


@dataclass(frozen=True)
class LaunchEvidence:
    requestedScheme: str | None        # what the caller asked for
    activeScheme: str | None           # what argv actually used (None when isolation unavailable)
    isolationMode: str                 # "isolated" | "default" — derives from activeScheme, never the request
    discoveryRecordPath: str | None
    discoveryLogSeen: bool
    windows: list[dict[str, Any]]
    visibleWindowCount: int
    emptyTitleWindowPresent: bool
    exitCode: int | None
    argv: list[str]
    elapsedSeconds: float
    diagnosticHint: str | None         # NON-CAUSAL, e.g. "startup_window_present_no_discovery"
    launchEnv: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class LaunchOutcome:
    ok: bool
    schemeIsolationAvailable: bool
    canResetSchemeRecoveryState: bool
    evidence: LaunchEvidence
    pid: int | None = None
    port: int | None = None
    discoveryRecordPath: str | None = None
    reason: DiscoveryFailureReason | None = None   # None on success; passed through on failure
    message: str | None = None                     # human-readable failure detail (str(exc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schemeIsolationAvailable": self.schemeIsolationAvailable,
            "canResetSchemeRecoveryState": self.canResetSchemeRecoveryState,
            "pid": self.pid,
            "port": self.port,
            "discoveryRecordPath": self.discoveryRecordPath,
            "reason": self.reason.value if self.reason else None,
            "message": self.message,
            "evidence": self.evidence.to_dict(),
        }


def resolve_requested_scheme(default_scheme: str, env, *, env_var: str = "ROOK_WORKBENCH_SCHEME") -> str | None:
    """The scheme the caller REQUESTS. Explicit `<env_var>=default` opts out -> None (default profile)."""
    if env.get(env_var) == "default":
        return None
    return default_scheme


def resolve_active_scheme(requested_scheme: str | None, *, scheme_isolation_available: bool):
    """Return (activeScheme, isolationMode). Active ONLY if requested AND isolation is available."""
    if requested_scheme and scheme_isolation_available:
        return (requested_scheme, "isolated")
    return (None, "default")


def build_rhino_argv(rhino_exe, *, active_scheme: str | None) -> list[str]:
    """`/nosplash` ALWAYS; `/scheme=` only for an ACTIVE (validated+available) scheme."""
    argv = [str(rhino_exe), "/nosplash"]
    if active_scheme:
        argv.append(f"/scheme={active_scheme}")
    return argv


def _build_evidence(*, requested_scheme, active_scheme, isolation_mode, discovery_record_path,
                    discovery_log_seen, windows, exit_code, argv, elapsed,
                    launch_env=None) -> LaunchEvidence:
    visible = [w for w in windows if w.get("visible")]
    empty_title_present = any((w.get("title") or "") == "" for w in visible)
    hint = "startup_window_present_no_discovery" if visible and discovery_record_path is None else None
    return LaunchEvidence(
        requestedScheme=requested_scheme, activeScheme=active_scheme, isolationMode=isolation_mode,
        discoveryRecordPath=discovery_record_path, discoveryLogSeen=discovery_log_seen,
        windows=list(windows), visibleWindowCount=len(visible),
        emptyTitleWindowPresent=empty_title_present, exitCode=exit_code, argv=list(argv),
        elapsedSeconds=elapsed, diagnosticHint=hint, launchEnv=launch_env)


@dataclass(frozen=True)
class StartedRhino:
    process: Any                  # the live subprocess.Popen — CALLER owns cleanup / registry / _OWNED
    pid: int
    argv: list[str]
    requestedScheme: str | None
    activeScheme: str | None
    isolationMode: str
    started_at: float             # time.monotonic() at Popen — elapsed timing
    started_wall: float           # time.time() at Popen — native-discovery log freshness (PID-reuse guard)
    launchEnv: dict[str, Any] | None = None


class LaunchExecError(RuntimeError):
    """Popen itself failed (exe missing / OSError) — carries the evidence base."""
    def __init__(self, message, *, argv, requested_scheme, active_scheme, isolation_mode,
                 launch_env=None):
        super().__init__(message)
        self.argv = list(argv)
        self.requested_scheme = requested_scheme
        self.active_scheme = active_scheme
        self.isolation_mode = isolation_mode
        self.launch_env = launch_env


def start_rhino_process(rhino_exe, *, requested_scheme: str | None, env,
                        launch_env_report: dict[str, Any] | None = None,
                        scheme_isolation_available: bool = SCHEME_ISOLATION_AVAILABLE,
                        popen=None) -> StartedRhino:
    active_scheme, isolation_mode = resolve_active_scheme(
        requested_scheme, scheme_isolation_available=scheme_isolation_available)
    argv = build_rhino_argv(rhino_exe, active_scheme=active_scheme)
    popen = popen or (lambda a: subprocess.Popen(a, env=dict(env) if env is not None else None))
    started_at = time.monotonic()
    started_wall = time.time()
    try:
        proc = popen(argv)
    except OSError as exc:
        raise LaunchExecError(str(exc), argv=argv, requested_scheme=requested_scheme,
                              active_scheme=active_scheme, isolation_mode=isolation_mode,
                              launch_env=launch_env_report) from exc
    return StartedRhino(process=proc, pid=int(proc.pid), argv=argv,
                        requestedScheme=requested_scheme, activeScheme=active_scheme,
                        isolationMode=isolation_mode, started_at=started_at,
                        started_wall=started_wall, launchEnv=launch_env_report)


def exec_failure_outcome(exc: LaunchExecError) -> LaunchOutcome:
    ev = _build_evidence(requested_scheme=exc.requested_scheme, active_scheme=exc.active_scheme,
                         isolation_mode=exc.isolation_mode, discovery_record_path=None,
                         discovery_log_seen=False, windows=[], exit_code=None, argv=exc.argv,
                         elapsed=0.0, launch_env=exc.launch_env)
    return LaunchOutcome(ok=False, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                         canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE, evidence=ev,
                         reason=DiscoveryFailureReason.LAUNCH_EXEC_FAILED, message=str(exc))


@dataclass(frozen=True)
class ReadinessResult:
    outcome: LaunchOutcome              # serializable structured result (manifest / envelope)
    record: OwnedRhinoRecord | None     # the live OwnedRhinoRecord on success; None on failure


def _discovery_log_seen(discovery_dir, pid: int, since_wall: float) -> bool:
    """Best-effort: did RookNative write its `native-discovery-<pid>.log` for THIS launch?

    `RookServer.cpp::WriteDiscoveryDiagnostic` appends to
    `<sharedDiscoveryFolder>/native-discovery-<pid>.log` (the SAME folder the instance JSON lands in)
    as it resolves the discovery folder — so a fresh log is evidence the plugin BEGAN its discovery
    sequence, distinct from publishing a valid instance record. The load-bearing failure discriminator:
    `discoveryLogSeen=False` + no record ⇒ RookNative likely never loaded (disabled / wrong scheme /
    crashed pre-init); `discoveryLogSeen=True` + no record ⇒ it started but didn't bind.

    `mtime >= since_wall - 2.0s` guards PID reuse (a recycled PID's stale log; 2s tolerates FS timestamp
    coarseness). Pure signal, NOT a gate — any error returns False, never throws."""
    try:
        if discovery_dir is None:
            return False
        log_path = Path(discovery_dir) / f"native-discovery-{pid}.log"
        return log_path.is_file() and os.stat(log_path).st_mtime >= since_wall - 2.0
    except OSError:
        return False


def wait_for_rook_readiness(started: StartedRhino, *, discovery, ping=None,
                            timeout_seconds: float = 30.0, poll_seconds: float = 0.25,
                            describe_windows=None, log_seen=None, now=time.monotonic) -> ReadinessResult:
    """SYNC (mirrors OwnedRhinoDiscovery.wait_for_ready). Workbench wraps this in asyncio.to_thread;
    the harness calls it directly. The failure reason is PASSED THROUGH from DiscoveryError.reason —
    never re-derived from window state. `discoveryLogSeen` is computed for REAL (the native-discovery
    log predicate), not inferred from ok/not-ok. Returns ReadinessResult so the caller gets BOTH the
    serializable outcome AND the live record (no re-read, no lossy reconstruction)."""
    ping = ping or ping_native
    describe_windows = describe_windows or describe_windows_for_pid
    log_seen = log_seen or (lambda: _discovery_log_seen(
        getattr(discovery, "discovery_dir", None), started.pid, started.started_wall))
    try:
        record = discovery.wait_for_ready(
            pid=started.pid, process=started.process, ping=ping,
            timeout_seconds=timeout_seconds, poll_seconds=poll_seconds)
    except DiscoveryError as exc:
        windows = list(describe_windows(started.pid) or [])
        ev = _build_evidence(requested_scheme=started.requestedScheme, active_scheme=started.activeScheme,
                             isolation_mode=started.isolationMode, discovery_record_path=None,
                             discovery_log_seen=log_seen(), windows=windows, exit_code=started.process.poll(),
                             argv=started.argv, elapsed=now() - started.started_at,
                             launch_env=started.launchEnv)
        outcome = LaunchOutcome(ok=False, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                                canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE, evidence=ev,
                                reason=exc.reason or DiscoveryFailureReason.BIND_TIMEOUT_NO_DISCOVERY,
                                message=str(exc))
        return ReadinessResult(outcome=outcome, record=None)
    ev = _build_evidence(requested_scheme=started.requestedScheme, active_scheme=started.activeScheme,
                         isolation_mode=started.isolationMode, discovery_record_path=str(record.path),
                         discovery_log_seen=log_seen(), windows=[], exit_code=None, argv=started.argv,
                         elapsed=now() - started.started_at, launch_env=started.launchEnv)
    outcome = LaunchOutcome(ok=True, schemeIsolationAvailable=SCHEME_ISOLATION_AVAILABLE,
                            canResetSchemeRecoveryState=CAN_RESET_SCHEME_RECOVERY_STATE, evidence=ev,
                            pid=record.pid, port=record.port, discoveryRecordPath=str(record.path))
    return ReadinessResult(outcome=outcome, record=record)
