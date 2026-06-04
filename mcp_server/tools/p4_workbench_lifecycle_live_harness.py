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

        # 2. list shows it
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
        if closed.get("closed"):
            launched_session = None
        _record("workbench_close",
                closed.get("closed") is True
                and closed.get("cleanupStatus") in ("forced_kill", "graceful_exit"),
                f"cleanupStatus={closed.get('cleanupStatus')}")

        # 6. list no longer shows it
        lst2 = _json(_text(await server.call_tool("rhino_workbench_list", {})))
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
