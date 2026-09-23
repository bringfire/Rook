"""Manage the Chirp adapter service lifecycle.

Handles auto-discovery, startup, health checks, and cleanup for the Chirp
sidecar process. Uses discovery files (chirp-service-{port}.json) as the
sole source of truth for port resolution — no hardcoded ports.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import os
import socket
import subprocess
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

import httpx
from dotenv import dotenv_values

from .providers.vertex_auth import (
    VERTEX_SCHEMA_VERSION,
    VertexAuthError,
    VertexStore,
    vertex_gemini_model_name,
)

logger = logging.getLogger(__name__)

DISCOVERY_FOLDER = Path(tempfile.gettempdir()) / "rook"
DISCOVERY_PREFIX = "chirp-service-"
HEALTH_TIMEOUT = httpx.Timeout(2.0)
STARTUP_POLL_INTERVAL = 0.4
STARTUP_MAX_WAIT = float(os.environ.get("ROOK_CHIRP_STARTUP_MAX_WAIT", "45.0"))
INVALID_TIMEOUT_CODE = "chirp_invalid_inference_timeout"
INVALID_TIMEOUT_MESSAGE = (
    "Chirp is disabled because CHIRP_INFERENCE_TIMEOUT_SECONDS must contain "
    "only ASCII digits and resolve to 1–1800 seconds."
)
MAX_VERTEX_BOOTSTRAP_BYTES = 65_536
RETIREMENT_EVENT_NAME = r"Local\BringFire.Rook.Chirp.VertexGenerationChanged.v1"
RETIREMENT_MAX_WAIT = 10.0
RETIREMENT_FORCE_WAIT = 2.0
VERTEX_RESTART_MESSAGE = (
    "Vertex authorization changed, but a managed process could not be retired."
)
DEFAULT_CHIRP_MODEL = "anthropic/claude-opus-5"
VERTEX_LOCAL_ERROR_CODES = frozenset(
    {
        "vertex_signed_out",
        "vertex_restart_required",
        "vertex_model_family_unsupported",
    }
)

# Module-level state
_chirp_process: subprocess.Popen | None = None
_startup_lock: asyncio.Lock | None = None
# Shared by async admission and synchronous post-commit replacement entrypoints.
_replacement_lock = threading.Lock()


def _get_startup_lock() -> asyncio.Lock:
    """Lazy-init the lock (must be created inside a running event loop)."""
    global _startup_lock
    if _startup_lock is None:
        _startup_lock = asyncio.Lock()
    return _startup_lock


async def _read_health(host: str, port: int) -> dict | None:
    """Return a valid HTTP 200 Chirp health object, otherwise None."""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(f"http://{host}:{port}/health")
            if resp.status_code != 200:
                return None
            payload = resp.json()
            return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_health_sync(host: str, port: int) -> dict | None:
    try:
        with httpx.Client(timeout=HEALTH_TIMEOUT) as client:
            response = client.get(f"http://{host}:{port}/health")
        if response.status_code != 200:
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _classify_health(host: str, port: int, payload: dict | None) -> dict | None:
    """Map only healthy or terminal timeout-policy health to lifecycle results."""
    if not isinstance(payload, dict):
        return None
    if payload.get("status") == "ok":
        return {"running": True, "host": host, "port": port, "error": None}
    error = payload.get("error")
    if (
        payload.get("status") == "disabled"
        and isinstance(error, dict)
        and error.get("code") == INVALID_TIMEOUT_CODE
        and error.get("message") == INVALID_TIMEOUT_MESSAGE
    ):
        return {
            "running": False,
            "host": host,
            "port": port,
            "error": INVALID_TIMEOUT_MESSAGE,
            "error_code": INVALID_TIMEOUT_CODE,
        }
    return None


def _classify_model_health(
    host: str,
    port: int,
    payload: dict | None,
    *,
    vertex_required: bool,
) -> dict | None:
    ordinary = _classify_health(host, port, payload)
    if not isinstance(payload, dict):
        return ordinary
    if vertex_required:
        if (
            payload.get("status") == "ok"
            and payload.get("rook_managed") is True
            and isinstance(payload.get("vertex"), dict)
            and payload["vertex"].get("status") == "ready"
        ):
            return {"running": True, "host": host, "port": port, "error": None}
        if ordinary is not None and not ordinary.get("running"):
            return ordinary
        return None
    if ordinary is not None:
        return ordinary
    error = payload.get("error")
    if (
        payload.get("status") == "disabled"
        and payload.get("rook_managed") is True
        and isinstance(error, dict)
        and error.get("code") in VERTEX_LOCAL_ERROR_CODES
    ):
        return {"running": True, "host": host, "port": port, "error": None}
    return None


def _error_result(error: VertexAuthError, host: str, port: int) -> dict:
    return {
        "running": False,
        "host": host,
        "port": port,
        "error": error.public_message,
        "error_code": error.code,
    }


def _resolve_effective_model(
    required_model: str | None,
    chirp_home: Path | None,
) -> str:
    if isinstance(required_model, str) and required_model:
        return required_model
    process_model = os.environ.get("CHIRP_MODEL")
    if process_model:
        return process_model
    if chirp_home is not None:
        env_path = chirp_home / ".env"
        if env_path.is_file():
            file_model = dotenv_values(env_path).get("CHIRP_MODEL")
            if isinstance(file_model, str) and file_model:
                return file_model
    return DEFAULT_CHIRP_MODEL


def _resolve_vertex_bootstrap(
    expected_generation: str | None = None,
) -> dict[str, object]:
    store = VertexStore.production()
    runtime = store.resolve_runtime()
    record = store.read()
    if (
        record is None
        or record.generation != runtime.generation
        or (
            expected_generation is not None
            and runtime.generation != expected_generation
        )
    ):
        raise _restart_required()
    return {
        "schema_version": VERTEX_SCHEMA_VERSION,
        "generation": runtime.generation,
        "mode": record.mode.value,
        "project_id": runtime.project_id,
        "region": runtime.region,
        "vertex_credentials": runtime.vertex_credentials,
    }


def _find_live_discovery() -> dict | None:
    """Scan all chirp-service-*.json files and return the first with a live PID.

    Cleans up stale files from dead processes.
    """
    if not DISCOVERY_FOLDER.is_dir():
        return None
    for path in sorted(DISCOVERY_FOLDER.glob(f"{DISCOVERY_PREFIX}*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = data.get("pid")
            port = data.get("port")
            if pid and port and _is_pid_alive(pid):
                # Ensure host is present (backward compat with old discovery files)
                data.setdefault("host", "127.0.0.1")
                return data
            # Stale file — clean up
            path.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _is_pid_alive(pid: int) -> bool:
    """Check if a Windows process is still running."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        return exit_code.value == 259  # STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _parent_pid_map() -> dict[int, int]:
    """Snapshot ``pid -> parent pid`` for every live process (Toolhelp32)."""
    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE or not snapshot:
        return {}
    parents: dict[int, int] = {}
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return {}
        while True:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return parents


_MAX_LAUNCHER_DEPTH = 4


def _process_owns_pid(process, pid) -> bool:
    """True when ``pid`` is the managed child itself or a live descendant of it.

    A venv ``python.exe`` on Windows is a launcher: it starts the real interpreter
    as a child and waits for it, so the pid Chirp records in its discovery file is
    the launcher's child, never the ``Popen`` pid. Ownership therefore means "the
    discovered process descends from the process we started", bounded to a few
    launcher hops. The launcher must still be alive (it outlives its child), which
    also guards against a recycled parent pid.
    """
    own_pid = getattr(process, "pid", None)
    if type(own_pid) is not int or type(pid) is not int or pid <= 0:
        return False
    if pid == own_pid:
        return True
    if process.poll() is not None:
        return False
    parents = _parent_pid_map()
    current = pid
    for _ in range(_MAX_LAUNCHER_DEPTH):
        parent = parents.get(current)
        if parent is None or parent == current:
            return False
        if parent == own_pid:
            return True
        current = parent
    return False


def _terminate_pid(pid: int) -> None:
    """Terminate a descendant process the launcher would otherwise leave running."""
    PROCESS_TERMINATE = 0x0001
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        raise OSError(ctypes.get_last_error(), f"OpenProcess({pid}) failed")
    try:
        if not ctypes.windll.kernel32.TerminateProcess(handle, 1):
            raise OSError(ctypes.get_last_error(), f"TerminateProcess({pid}) failed")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _restart_required() -> VertexAuthError:
    return VertexAuthError("vertex_restart_required", VERTEX_RESTART_MESSAGE)


def _read_discovery_for_port(port: int) -> dict | None:
    path = DISCOVERY_FOLDER / f"{DISCOVERY_PREFIX}{port}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("port") != port:
        return None
    return payload


def _set_retirement_event(*, reset: bool) -> None:
    if os.name != "nt":
        raise OSError("managed retirement events require Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateEventW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.restype = wintypes.BOOL
    kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
    kernel32.ResetEvent.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateEventW(None, True, False, RETIREMENT_EVENT_NAME)
    if not handle:
        raise OSError("managed retirement event unavailable")
    try:
        operation = kernel32.ResetEvent if reset else kernel32.SetEvent
        if not operation(handle):
            raise OSError("managed retirement event operation failed")
    finally:
        kernel32.CloseHandle(handle)


def _signal_retirement_event() -> None:
    _set_retirement_event(reset=False)


def _reset_retirement_event() -> None:
    _set_retirement_event(reset=True)


def _wait_for_retirement(discovery: dict, timeout: float) -> bool:
    pid = discovery.get("pid")
    port = discovery.get("port")
    if type(pid) is not int or type(port) is not int:
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


def _port_is_available(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
        return True
    except OSError:
        return False


def _retire_discovered_process(
    discovery: dict,
    health_payload: dict,
) -> tuple[str, int]:
    """Retire one managed child without inferring termination ownership."""

    global _chirp_process
    host = discovery.get("host", "127.0.0.1")
    port = discovery.get("port")
    pid = discovery.get("pid")
    if (
        health_payload.get("rook_managed") is not True
        or host != "127.0.0.1"
        or type(port) is not int
        or type(pid) is not int
    ):
        raise _restart_required()

    try:
        _signal_retirement_event()
    except Exception as exc:
        raise _restart_required() from exc

    if not _wait_for_retirement(discovery, RETIREMENT_MAX_WAIT):
        process = _chirp_process
        current = _read_discovery_for_port(port)
        owns_exact_process = (
            process is not None
            and process.poll() is None
            and _process_owns_pid(process, pid)
            and isinstance(current, dict)
            and current.get("pid") == pid
            and current.get("port") == port
            and current.get("host", "127.0.0.1") == host
        )
        if not owns_exact_process:
            raise _restart_required()
        try:
            if pid == getattr(process, "pid", None):
                process.terminate()
            else:
                # The discovered server is the launcher's child; terminating the
                # launcher alone would leave it running.
                _terminate_pid(pid)
        except Exception as exc:
            raise _restart_required() from exc
        if not _wait_for_retirement(discovery, RETIREMENT_FORCE_WAIT):
            raise _restart_required()

    if not _port_is_available(host, port):
        raise _restart_required()
    try:
        _reset_retirement_event()
    except Exception as exc:
        raise _restart_required() from exc
    if _chirp_process is not None and (
        getattr(_chirp_process, "pid", None) == pid
        or getattr(_chirp_process, "poll", lambda: None)() is not None
    ):
        _chirp_process = None
    return host, port


def _find_managed_chirp_home() -> Path | None:
    """Locate Chirp only from manager-owned configuration and source layout."""

    env_home = os.environ.get("CHIRP_HOME")
    if env_home:
        candidate = Path(env_home)
        if (candidate / "src" / "chirp").is_dir():
            return candidate

    rook_root = os.environ.get("ROOK_PROJECT_ROOT")
    if rook_root:
        candidate = Path(rook_root).parent / "Chirp"
        if (candidate / "src" / "chirp").is_dir():
            return candidate

    this_dir = Path(__file__).resolve().parent
    rook_dir = this_dir.parent.parent.parent
    candidate = rook_dir.parent / "Chirp"
    if (candidate / "src" / "chirp").is_dir():
        return candidate

    return None


def _find_chirp_home() -> Path | None:
    """Locate Chirp for configuration reads without trusting it for launches.

    Search order:
    1. Manager-owned environment or approved source layout
    2. Live discovery path, for compatibility reads only
    """
    managed_home = _find_managed_chirp_home()
    if managed_home is not None:
        return managed_home

    disc = _find_live_discovery()
    if disc and disc.get("home"):
        p = Path(disc["home"])
        if (p / "src" / "chirp").is_dir():
            return p

    return None


def _find_chirp_python(chirp_home: Path) -> Path | None:
    """Find the Python executable in Chirp's venv."""
    # Windows venv
    venv_python = chirp_home / ".venv" / "Scripts" / "python.exe"
    if venv_python.is_file():
        return venv_python

    # Unix-style venv
    venv_python = chirp_home / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return venv_python

    return None


def _start_chirp(
    chirp_home: Path,
    *,
    vertex_bootstrap: dict[str, object] | None = None,
    requested_port: int | None = None,
) -> subprocess.Popen | None:
    """Start the Chirp adapter as a detached background process.

    Ordinary cold starts use port 0. A verified recycle may request the exact
    prior port. Vertex authorization is written once to child stdin and closed.
    """
    python_exe = _find_chirp_python(chirp_home)
    if not python_exe:
        logger.error("Chirp venv not found at %s/.venv", chirp_home)
        return None

    logger.info("Starting Chirp adapter: %s -m chirp (port 0 — OS-assigned)", python_exe)

    env = os.environ.copy()
    if requested_port is None:
        env["CHIRP_PORT"] = "0"
    else:
        env["CHIRP_PORT"] = str(requested_port)
    # Prevent Python path conflicts
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["CHIRP_HOME"] = str(chirp_home)
    env["CHIRP_DSPY_RESTRICT_PICKLE"] = "1"
    env["DSPY_CACHEDIR"] = str(chirp_home / "data" / "dspy-cache")

    # Fully detach child stdio — passing a file handle and closing it in the
    # parent causes the child to block on its first stderr write on Windows.
    arguments = [str(python_exe), "-m", "chirp", "--rook-managed"]
    bootstrap_line: bytes | None = None
    if vertex_bootstrap is not None:
        arguments.append("--rook-vertex-bootstrap-stdin")
        bootstrap_line = (
            json.dumps(
                vertex_bootstrap,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        if len(bootstrap_line) > MAX_VERTEX_BOOTSTRAP_BYTES + 1:
            raise ValueError("Vertex bootstrap exceeds the bounded stdin payload")

    proc = subprocess.Popen(
        arguments,
        cwd=str(chirp_home),
        env=env,
        stdin=(subprocess.PIPE if bootstrap_line is not None else subprocess.DEVNULL),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if bootstrap_line is not None:
        if proc.stdin is None:
            try:
                proc.terminate()
            except Exception:
                pass
            raise RuntimeError("Managed Vertex stdin pipe was not created")
        try:
            proc.stdin.write(bootstrap_line)
            proc.stdin.flush()
        except BaseException:
            try:
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
            raise
        else:
            proc.stdin.close()
    return proc


def _wait_for_started_process_sync(
    process: subprocess.Popen,
    host: str,
    port: int,
    *,
    vertex_required: bool,
) -> dict:
    deadline = time.monotonic() + STARTUP_MAX_WAIT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise _restart_required()
        discovery = _read_discovery_for_port(port)
        if isinstance(discovery, dict) and _process_owns_pid(process, discovery.get("pid")):
            classified = _classify_model_health(
                host,
                port,
                _read_health_sync(host, port),
                vertex_required=vertex_required,
            )
            if classified is not None:
                if classified.get("running"):
                    return classified
                raise VertexAuthError(
                    classified.get("error_code", "vertex_restart_required"),
                    classified.get("error") or VERTEX_RESTART_MESSAGE,
                )
        time.sleep(STARTUP_POLL_INTERVAL)
    raise _restart_required()


def _restart_discovered_process(
    discovery: dict,
    health_payload: dict,
    vertex_bootstrap: dict[str, object] | None,
) -> dict:
    global _chirp_process
    with _replacement_lock:
        current = _find_live_discovery()
        same_process = (
            isinstance(current, dict)
            and current.get("host", "127.0.0.1")
            == discovery.get("host", "127.0.0.1")
            and current.get("port") == discovery.get("port")
            and current.get("pid") == discovery.get("pid")
        )
        if not same_process:
            if not isinstance(current, dict):
                raise _restart_required()
            host = current.get("host", "127.0.0.1")
            port = current.get("port")
            if host != "127.0.0.1" or type(port) is not int:
                raise _restart_required()
            classified = _classify_model_health(
                host,
                port,
                _read_health_sync(host, port),
                vertex_required=vertex_bootstrap is not None,
            )
            if classified is not None:
                return classified
            raise _restart_required()

        chirp_home = _find_managed_chirp_home()
        if chirp_home is None or _find_chirp_python(chirp_home) is None:
            raise _restart_required()
        host, port = _retire_discovered_process(discovery, health_payload)
        process = _start_chirp(
            chirp_home,
            vertex_bootstrap=vertex_bootstrap,
            requested_port=port,
        )
        if process is None:
            raise _restart_required()
        _chirp_process = process
        return _wait_for_started_process_sync(
            process,
            host,
            port,
            vertex_required=vertex_bootstrap is not None,
        )


def recycle_after_vertex_commit(generation: str | None) -> None:
    """Replace a previously live managed sidecar after an auth commit."""

    discovery = _find_live_discovery()
    if discovery is None:
        process = _chirp_process
        if process is not None:
            try:
                if process.poll() is None:
                    raise _restart_required()
            except VertexAuthError:
                raise
            except Exception as exc:
                raise _restart_required() from exc
        return
    host = discovery.get("host", "127.0.0.1")
    port = discovery.get("port")
    if host != "127.0.0.1" or type(port) is not int:
        raise _restart_required()
    health_payload = _read_health_sync(host, port)
    if not isinstance(health_payload, dict):
        raise _restart_required()

    vertex_bootstrap = None
    if generation is not None:
        vertex = health_payload.get("vertex")
        was_vertex_ready = (
            isinstance(vertex, dict) and vertex.get("status") == "ready"
        )
        chirp_home = _find_chirp_home()
        default_model = _resolve_effective_model(None, chirp_home)
        default_is_vertex = vertex_gemini_model_name(default_model) is not None
        if was_vertex_ready or default_is_vertex:
            vertex_bootstrap = _resolve_vertex_bootstrap(generation)

    _restart_discovered_process(discovery, health_payload, vertex_bootstrap)


async def _handle_live_discovery(
    discovery: dict,
    effective_model: str,
) -> dict | None:
    host = discovery.get("host", "127.0.0.1")
    port = discovery.get("port")
    if host != "127.0.0.1" or type(port) is not int:
        return _error_result(_restart_required(), "127.0.0.1", 0)
    try:
        vertex_required = vertex_gemini_model_name(effective_model) is not None
    except VertexAuthError as error:
        return _error_result(error, host, port)
    payload = await _read_health(host, port)
    classified = _classify_model_health(
        host,
        port,
        payload,
        vertex_required=vertex_required,
    )
    if classified is not None:
        return classified
    if not isinstance(payload, dict):
        return None
    if not vertex_required:
        return None
    if payload.get("rook_managed") is not True:
        return _error_result(_restart_required(), host, port)
    try:
        bootstrap = _resolve_vertex_bootstrap()
        return await asyncio.to_thread(
            _restart_discovered_process,
            discovery,
            payload,
            bootstrap,
        )
    except VertexAuthError as error:
        return _error_result(error, host, port)
    except Exception:
        return _error_result(_restart_required(), host, port)


async def _wait_for_existing_model(
    discovery: dict,
    effective_model: str,
) -> dict:
    elapsed = 0.0
    while elapsed < STARTUP_MAX_WAIT:
        result = await _handle_live_discovery(discovery, effective_model)
        if result is not None:
            return result
        await asyncio.sleep(STARTUP_POLL_INTERVAL)
        elapsed += STARTUP_POLL_INTERVAL
    return {
        "running": False,
        "host": discovery.get("host", "127.0.0.1"),
        "port": discovery.get("port", 0),
        "error": f"Chirp process exists but did not respond within {STARTUP_MAX_WAIT}s",
    }


async def ensure_chirp_running(required_model: str | None = None) -> dict:
    """Ensure the Chirp adapter is running, starting it if necessary.

    Returns:
        dict with keys: running (bool), host (str), port (int), error (str | None)
    """
    global _chirp_process

    chirp_home = _find_chirp_home()
    effective_model = _resolve_effective_model(required_model, chirp_home)
    try:
        vertex_required = vertex_gemini_model_name(effective_model) is not None
    except VertexAuthError as error:
        return _error_result(error, "127.0.0.1", 0)

    # Fast path: discovery file with live PID → model-aware health check
    disc = _find_live_discovery()
    if disc:
        existing = await _handle_live_discovery(disc, effective_model)
        if existing is not None:
            return existing

    # Serialize startup attempts so concurrent calls don't spawn multiple processes
    async with _get_startup_lock():
        # Re-check after acquiring lock (another caller may have started it)
        disc = _find_live_discovery()
        if disc:
            existing = await _handle_live_discovery(disc, effective_model)
            if existing is not None:
                return existing
            logger.info(
                "Chirp PID %s alive but not responding — waiting for reload",
                disc.get("pid"),
            )
            return await _wait_for_existing_model(disc, effective_model)

        # Find Chirp repo
        if not chirp_home:
            return {
                "running": False,
                "host": "127.0.0.1",
                "port": 0,
                "error": (
                    "Cannot find Chirp repo. Set CHIRP_HOME environment variable "
                    "to the Chirp repository root (the sibling checkout next to Rook, e.g. ..\\Chirp)"
                ),
            }

        python_exe = _find_chirp_python(chirp_home)
        if not python_exe:
            return {
                "running": False,
                "host": "127.0.0.1",
                "port": 0,
                "error": (
                    f"Chirp repo found at {chirp_home} but no .venv detected. "
                    f"Run: cd {chirp_home} && python -m venv .venv && .venv/Scripts/pip install -e \".[dev]\""
                ),
            }

        try:
            bootstrap = _resolve_vertex_bootstrap() if vertex_required else None
        except VertexAuthError as error:
            return _error_result(error, "127.0.0.1", 0)

        _chirp_process = _start_chirp(
            chirp_home,
            vertex_bootstrap=bootstrap,
        )
        if _chirp_process is None:
            return {"running": False, "host": "127.0.0.1", "port": 0, "error": "Failed to start Chirp process"}

        # Wait for discovery file to appear (Chirp writes it after binding port 0)
        elapsed = 0.0
        while elapsed < STARTUP_MAX_WAIT:
            await asyncio.sleep(STARTUP_POLL_INTERVAL)
            elapsed += STARTUP_POLL_INTERVAL

            # Check if process died
            if _chirp_process.poll() is not None:
                return {
                    "running": False,
                    "host": "127.0.0.1",
                    "port": 0,
                    "error": f"Chirp process exited with code {_chirp_process.returncode} during startup",
                }

            # Check for discovery file
            disc = _find_live_discovery()
            if disc and _process_owns_pid(_chirp_process, disc.get("pid")):
                host = disc.get("host", "127.0.0.1")
                port = disc["port"]
                # Discovery file appeared — now wait for health
                health_result = _classify_model_health(
                    host,
                    port,
                    await _read_health(host, port),
                    vertex_required=vertex_required,
                )
                if health_result is not None:
                    if health_result["running"]:
                        logger.info(
                            "Chirp adapter is ready on %s:%d (%.1fs startup)",
                            host,
                            port,
                            elapsed,
                        )
                    return health_result

        return {
            "running": False,
            "host": "127.0.0.1",
            "port": 0,
            "error": f"Chirp started but discovery file did not appear within {STARTUP_MAX_WAIT}s",
        }
