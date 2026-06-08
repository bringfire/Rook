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
import subprocess
import tempfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DISCOVERY_FOLDER = Path(tempfile.gettempdir()) / "rook"
DISCOVERY_PREFIX = "chirp-service-"
HEALTH_TIMEOUT = httpx.Timeout(2.0)
STARTUP_POLL_INTERVAL = 0.4
STARTUP_MAX_WAIT = float(os.environ.get("ROOK_CHIRP_STARTUP_MAX_WAIT", "45.0"))

# Module-level state
_chirp_process: subprocess.Popen | None = None
_startup_lock: asyncio.Lock | None = None


def _get_startup_lock() -> asyncio.Lock:
    """Lazy-init the lock (must be created inside a running event loop)."""
    global _startup_lock
    if _startup_lock is None:
        _startup_lock = asyncio.Lock()
    return _startup_lock


async def _health_check(host: str, port: int) -> bool:
    """Return True if Chirp is responding on the given host:port."""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT) as client:
            resp = await client.get(f"http://{host}:{port}/health")
            return resp.status_code == 200
    except Exception:
        return False


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


def _find_chirp_home() -> Path | None:
    """Locate the Chirp repository root.

    Search order:
    1. CHIRP_HOME environment variable
    2. Discovery file (Chirp writes its home path when it starts)
    3. Sibling directory to Rook repo (../Chirp relative to Rook project root)
    """
    # 1. Explicit env var
    env_home = os.environ.get("CHIRP_HOME")
    if env_home:
        p = Path(env_home)
        if (p / "src" / "chirp").is_dir():
            return p

    # 2. Discovery file
    disc = _find_live_discovery()
    if disc and disc.get("home"):
        p = Path(disc["home"])
        if (p / "src" / "chirp").is_dir():
            return p

    # 3. Sibling to Rook
    rook_root = os.environ.get("ROOK_PROJECT_ROOT")
    if rook_root:
        p = Path(rook_root).parent / "Chirp"
        if (p / "src" / "chirp").is_dir():
            return p

    # Try relative to this file: rook/ → src/ → mcp_server/ → Rook/ → repos/ → Chirp/
    this_dir = Path(__file__).resolve().parent       # .../Rook/mcp_server/src/rook/
    rook_dir = this_dir.parent.parent.parent         # .../Rook/
    candidate = rook_dir.parent / "Chirp"            # .../repos/Chirp/
    if (candidate / "src" / "chirp").is_dir():
        return candidate

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


def _start_chirp(chirp_home: Path) -> subprocess.Popen | None:
    """Start the Chirp adapter as a detached background process.

    Does not pass CHIRP_PORT — Chirp defaults to port 0 (OS-assigned).
    """
    python_exe = _find_chirp_python(chirp_home)
    if not python_exe:
        logger.error("Chirp venv not found at %s/.venv", chirp_home)
        return None

    logger.info("Starting Chirp adapter: %s -m chirp (port 0 — OS-assigned)", python_exe)

    env = os.environ.copy()
    # Don't pass CHIRP_PORT — let Chirp use port 0 (OS-assigned)
    env.pop("CHIRP_PORT", None)
    # Prevent Python path conflicts
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["CHIRP_HOME"] = str(chirp_home)
    env["CHIRP_DSPY_RESTRICT_PICKLE"] = "1"
    env["DSPY_CACHEDIR"] = str(chirp_home / "data" / "dspy-cache")

    # Fully detach child stdio — passing a file handle and closing it in the
    # parent causes the child to block on its first stderr write on Windows.
    proc = subprocess.Popen(
        [str(python_exe), "-m", "chirp"],
        cwd=str(chirp_home),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc


async def _wait_for_health(host: str, port: int) -> dict:
    """Poll the health endpoint until it responds or we time out."""
    elapsed = 0.0
    while elapsed < STARTUP_MAX_WAIT:
        await asyncio.sleep(STARTUP_POLL_INTERVAL)
        elapsed += STARTUP_POLL_INTERVAL
        if await _health_check(host, port):
            return {"running": True, "host": host, "port": port, "error": None}
    return {
        "running": False,
        "host": host,
        "port": port,
        "error": f"Chirp process exists but did not respond within {STARTUP_MAX_WAIT}s",
    }


async def ensure_chirp_running() -> dict:
    """Ensure the Chirp adapter is running, starting it if necessary.

    Returns:
        dict with keys: running (bool), host (str), port (int), error (str | None)
    """
    global _chirp_process

    # Fast path: discovery file with live PID → health check
    disc = _find_live_discovery()
    if disc:
        host = disc.get("host", "127.0.0.1")
        port = disc["port"]
        if await _health_check(host, port):
            return {"running": True, "host": host, "port": port, "error": None}

    # Serialize startup attempts so concurrent calls don't spawn multiple processes
    async with _get_startup_lock():
        # Re-check after acquiring lock (another caller may have started it)
        disc = _find_live_discovery()
        if disc:
            host = disc.get("host", "127.0.0.1")
            port = disc["port"]
            if await _health_check(host, port):
                return {"running": True, "host": host, "port": port, "error": None}
            # PID alive but not healthy — wait for reload
            logger.info("Chirp PID %s alive but not responding — waiting for reload", disc.get("pid"))
            return await _wait_for_health(host, port)

        # Find Chirp repo
        chirp_home = _find_chirp_home()
        if not chirp_home:
            return {
                "running": False,
                "host": "127.0.0.1",
                "port": 0,
                "error": (
                    "Cannot find Chirp repo. Set CHIRP_HOME environment variable "
                    "to the Chirp repository root (e.g., C:\\Users\\aryan\\source\\repos\\Chirp)"
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

        _chirp_process = _start_chirp(chirp_home)
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
            if disc:
                host = disc.get("host", "127.0.0.1")
                port = disc["port"]
                # Discovery file appeared — now wait for health
                if await _health_check(host, port):
                    logger.info("Chirp adapter is ready on %s:%d (%.1fs startup)", host, port, elapsed)
                    return {"running": True, "host": host, "port": port, "error": None}

        return {
            "running": False,
            "host": "127.0.0.1",
            "port": 0,
            "error": f"Chirp started but discovery file did not appear within {STARTUP_MAX_WAIT}s",
        }
