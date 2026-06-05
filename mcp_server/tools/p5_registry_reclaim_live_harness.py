"""Live P5 registry-reclaim smoke.

Run via `scripts/run_rhino_runtime_harness.py --smoke p5-registry-reclaim`. The
runner launches its OWN owned Rhino. This smoke launches a SECOND owned Workbench
through the real registry-backed path, then exercises adopt-on-restart reclaim
HONESTLY: it rewrites the row's owner to a REAL DEAD pid (a throwaway process that
exited) + a stale token, then reconciles with this runtime's live identity and
asserts reclaim + close-via-surrogate. No fabricated pids.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


_ensure_import_path()

from rook import server, workbench  # noqa: E402
from rook import registry as reg    # noqa: E402
from rook.tool_result import parse_call_tool_data  # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str) -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _real_dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
    p.wait(timeout=10)
    # give the OS a moment to release the pid object; the pid is now a dead pid
    for _ in range(20):
        if not workbench._is_pid_alive(p.pid):
            return p.pid
        time.sleep(0.05)
    return p.pid


async def main() -> int:
    runner_pid = int(os.environ["ROOK_RHINO_PROCESS_ID"])
    print(f"Runner-owned Rhino pid={runner_pid}", flush=True)

    session = None
    try:
        # 1. launch a real owned Workbench through the registry-backed path
        out = parse_call_tool_data(await server.call_tool("rhino_workbench_launch",
                                                 {"readinessTimeoutSeconds": 120}))
        session = out.get("session")
        _record("launch", out.get("owned") is True and bool(session), f"session={session}")

        registry = workbench._registry()
        row = registry.get(session)
        _record("bound_row", row is not None and row.status == "bound",
                f"status={row.status if row else None}")

        # 2. rewrite owner to a REAL dead pid + stale token (a dead predecessor MCP)
        dead_pid = _real_dead_pid()
        registry._conn.execute(
            "UPDATE owned_sessions SET owner_pid=?, owner_token='stale-token' WHERE session_id=?;",
            (dead_pid, session))
        _record("seed_dead_owner", workbench._is_pid_alive(dead_pid) is False,
                f"dead_owner_pid={dead_pid}")

        # 3. reconcile with THIS runtime's live identity -> reclaim
        await asyncio.to_thread(workbench._reconcile_sync, reg.get_runtime_owner(), "external")
        reclaimed = reg.get_runtime_owner()
        row = registry.get(session)
        # _reconcile_sync settles the registry; _OWNED is rebuilt by the close driver
        # at its own entry (step 4), which is what actually proves closability.
        _record("reclaimed",
                row is not None and row.owner_pid == reclaimed.pid,
                f"owner_pid={row.owner_pid if row else None}")

        # 4. close still works via the surrogate
        closed = parse_call_tool_data(await server.call_tool("rhino_workbench_close", {"session": session}))
        if closed.get("closed"):
            session = None
        _record("close_after_reclaim", closed.get("closed") is True,
                f"cleanupStatus={closed.get('cleanupStatus')}")

        # 5. a dead-Rhino row is reaped by reconcile
        registry.insert_launching("rhino-999999", 999999, reg.get_runtime_owner(), "external", 1000)
        registry.bind("rhino-999999", 65000)
        await asyncio.to_thread(workbench._reconcile_sync, reg.get_runtime_owner(), "external")
        _record("dead_rhino_reaped", registry.get("rhino-999999") is None, "reaped")
    finally:
        if session:
            await server.call_tool("rhino_workbench_close", {"session": session})

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"\n=== P5 live smoke: {passed}/{len(_RESULTS)} PASS ===", flush=True)
    return 0 if passed == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
