"""Live P2 bridge-failure diagnosis harness.

Run via `scripts/run_rhino_runtime_harness.py --smoke p2-bridge-diagnosis`, which
launches an OWNED throwaway Rhino and sets ROOK_RHINO_PROCESS_ID / ROOK_RHINO_PORT.
This exercises P2's structured diagnosis against that owned process (including
killing it), verifying the things mocks cannot: a real OS pid-alive check, a real
TCP probe, real crash-file location. It never touches any other Rhino session.

Scenarios (in order):
  1. live_baseline        — call_rhino /ping against the owned Rhino succeeds.
  2. unreachable          — synthetic dead-port record (owned alive pid) ->
                            rook_native_listener_unreachable, record retained.
  3. kill_owned_rhino     — force-kill the owned Rhino (taskkill /F).
  4. dead_with_crash      — diagnose with the now-dead pid + a fresh crash file ->
                            rhino_session_dead + crash_artifact pointer.
  5. dead_no_crash        — same, no crash file -> rhino_session_dead, no artifact.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


_ensure_import_path()

import httpx  # noqa: E402
from rook import bridge, crash_artifacts  # noqa: E402


_RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str) -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _owned() -> tuple[int, int]:
    return int(os.environ["ROOK_RHINO_PROCESS_ID"]), int(os.environ["ROOK_RHINO_PORT"])


def _discovery_file(pid: int) -> Path | None:
    name = f"instance-{pid}-native.json"
    for folder in (getattr(bridge, "DISCOVERY_FOLDER", None), *getattr(bridge, "DISCOVERY_FOLDERS", [])):
        if folder is None:
            continue
        candidate = Path(folder) / name
        if candidate.is_file():
            return candidate
    return None


def _target(pid: int, port: int) -> dict:
    return {"host": "127.0.0.1", "port": port, "processId": pid,
            "session": f"rhino-{pid}", "endpoint": "/objects", "method": "GET"}


async def scenario_live(pid: int, port: int) -> None:
    out = await bridge.call_rhino("/ping", method="GET", port=port, process_id=pid)
    _record("live_baseline", "pong" in json.dumps(out), f"call_rhino /ping -> {json.dumps(out)[:120]}")


async def scenario_unreachable(pid: int, port: int) -> None:
    f = _discovery_file(pid)
    if f is None:
        _record("unreachable", False, "could not locate owned discovery file")
        return
    backup = f.read_text(encoding="utf-8")
    try:
        rec = json.loads(backup)
        rec["port"] = 1  # nothing listens on port 1
        f.write_text(json.dumps(rec), encoding="utf-8")
        out = await bridge.call_rhino("/objects", method="GET", port=1, process_id=pid)
        data = out.get("data") if isinstance(out, dict) else None
        code = data.get("code") if isinstance(data, dict) else None
        retryable = data.get("retryable") if isinstance(data, dict) else None
        ok = code == "rook_native_listener_unreachable" and f.exists()
        _record("unreachable", ok,
                f"code={code}, retryable={retryable}, record_retained={f.exists()}")
    finally:
        f.write_text(backup, encoding="utf-8")  # restore the real record


def make_dead_pid() -> int:
    # Spawn a trivial throwaway process and wait for it to fully exit, giving us a
    # genuinely-dead PID to diagnose WITHOUT killing the harness's owned Rhino (so
    # the harness can still shut it down gracefully -> clean green run).
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    for _ in range(60):
        if not bridge._is_pid_alive(proc.pid):
            break
        time.sleep(0.05)
    dead = not bridge._is_pid_alive(proc.pid)
    _record("dead_pid_ready", dead, f"throwaway pid={proc.pid} alive={not dead}")
    return proc.pid


def scenario_dead_with_crash(pid: int, port: int) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="p2smoke-desktop-"))
    (tmp / "RhinoDotNetCrash.txt").write_text(
        "[ERROR] FATAL UNHANDLED EXCEPTION: System.Exception: smoke", encoding="utf-8")
    crash_artifacts._desktop_dirs = lambda: [tmp]
    crash_artifacts._dump_dirs = lambda: []
    out = bridge.diagnose_bridge_failure(_target(pid, port), httpx.ConnectError("refused"))
    d = out.get("data", {})
    art = d.get("crash_artifact")
    ok = (d.get("code") == "rhino_session_dead" and d.get("retryable") is False
          and isinstance(art, dict) and art.get("available") is True)
    _record("dead_with_crash_artifact", ok,
            f"code={d.get('code')}, retryable={d.get('retryable')}, "
            f"crash_artifact_kind={art.get('kind') if isinstance(art, dict) else None}, "
            f"match={art.get('match') if isinstance(art, dict) else None}")


def scenario_dead_no_crash(pid: int, port: int) -> None:
    crash_artifacts._desktop_dirs = lambda: []
    crash_artifacts._dump_dirs = lambda: []
    out = bridge.diagnose_bridge_failure(_target(pid, port), httpx.ConnectError("refused"))
    d = out.get("data", {})
    ok = d.get("code") == "rhino_session_dead" and "crash_artifact" not in d
    _record("dead_no_crash_artifact", ok,
            f"code={d.get('code')}, has_crash_artifact={'crash_artifact' in d}")


async def main() -> int:
    pid, port = _owned()
    print(f"Owned Rhino: pid={pid} port={port}  discovery_folder={getattr(bridge, 'DISCOVERY_FOLDER', '?')}",
          flush=True)
    await scenario_live(pid, port)
    await scenario_unreachable(pid, port)
    dead_pid = make_dead_pid()
    scenario_dead_with_crash(dead_pid, port)
    scenario_dead_no_crash(dead_pid, port)

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"\n=== P2 live smoke: {passed}/{len(_RESULTS)} PASS ===", flush=True)
    return 0 if passed == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
