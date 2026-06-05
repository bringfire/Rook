"""Live P6 artifact-perception smoke.

Run via `scripts/run_rhino_runtime_harness.py --smoke p6-artifact-perception`. The
runner launches its OWN owned Rhino (the NON-owned ambient target here). This smoke
launches a SECOND, disposable OWNED Workbench, creates a box in it, SaveAs to a
throwaway .3dm, then proves durable artifact perception across the REAL Rook/Rhino
path:

  owned save -> observe -> close -> artifact PERSISTS,
  NON-owned (runner) saved doc is NEVER auto-persisted (I8),
  deregister forgets the row but NEVER deletes the .3dm (I5).

A freshly-launched second Workbench can intermittently exit after save/load (a
P4/P5/Rhino stability concern orthogonal to P6); reconcile then correctly reaps it,
so the observe (which rides list_owned_workbenches) has nothing to perceive. To
measure P6 and not Workbench survival, the disposable-Workbench flow is retried a few
times with a survival guard before observing. If EVERY attempt dies before observe,
the smoke fails with a clear stability message rather than a false P6 failure. The
artifact DB is isolated to a throwaway dir so assertions can't see stale rows; P5's
owned_sessions.db stays real. Nothing touches the user's session.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


_ensure_import_path()

from rook import server, artifacts  # noqa: E402
from rook import workbench as _wb    # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []
_MAX_ATTEMPTS = 3


def _record(name: str, ok: bool, detail: str) -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _text(result) -> str:
    return result[0].text if result else ""


def _json(text: str) -> dict:
    t = text.strip()
    if t.startswith("Error:"):
        t = t[len("Error:"):].strip()
    try:
        return json.loads(t)
    except Exception:
        return {}


def _rows_by_path(listing: dict) -> dict:
    # _format_tool_result renders a SUCCESS envelope as json.dumps(data), so the tool
    # text is the DATA itself ({"artifacts": [...]}), NOT {"data": {"artifacts": [...]}}.
    return {a["path"]: a for a in listing.get("artifacts", [])}


def _owned_alive(session: str) -> bool:
    """Is the owned Workbench still a live owned row (registry row present + pid alive)?
    A freshly-launched second Workbench can exit after save; reconcile then reaps it,
    so the observe (which rides list_owned_workbenches) would have nothing to perceive."""
    row = _wb._registry().get(session)
    return row is not None and _wb._is_pid_alive(row.rhino_pid)


async def _artifacts() -> dict:
    return _rows_by_path(_json(_text(await server.call_tool("rhino_artifacts", {}))))


async def _attempt(smoke_doc: Path) -> "tuple[str, str | None, dict | None]":
    """One disposable-Workbench attempt. Returns (status, session, owned_row):
      observed       -> the owned save was perceived as a durable artifact
      launch_failed  -> the Workbench did not launch/bind
      died           -> the Workbench exited before/while observing (retry)
      observe_failed -> the Workbench stayed alive but the artifact never appeared
    """
    out = _json(_text(await server.call_tool(
        "rhino_workbench_launch", {"readinessTimeoutSeconds": 120})))
    session = out.get("session")
    if not (out.get("owned") and session):
        return ("launch_failed", session, None)

    await server.call_tool("rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [10, 10, 5], "session": session})
    await server.call_tool("rhino_document_ops",
        {"action": "save", "path": str(smoke_doc), "session": session})
    if not _owned_alive(session):
        return ("died", session, None)

    want = artifacts.normalize_path(str(smoke_doc))
    for _ in range(10):
        await server.call_tool("rhino_workbench_list", {})  # fires the owned observe hook
        rows = await _artifacts()
        if want in rows:
            return ("observed", session, rows[want])
        if not _owned_alive(session):
            return ("died", session, None)
        await asyncio.sleep(0.75)
    return ("observe_failed", session, None)


def _finish() -> int:
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"\n=== P6 live smoke: {passed}/{len(_RESULTS)} PASS ===", flush=True)
    return 0 if passed == len(_RESULTS) else 1


async def main() -> int:
    print(f"Runner-owned (ambient/non-owned) Rhino pid={os.environ.get('ROOK_RHINO_PROCESS_ID')}", flush=True)

    # Isolate the artifact DB to a fresh throwaway dir (delete+recreate before assigning
    # the path; reset the singleton before AND after). P5's owned_sessions.db stays real.
    smoke_dir = Path(tempfile.gettempdir()) / "rook-p6-smoke"
    if smoke_dir.exists():
        shutil.rmtree(smoke_dir, ignore_errors=True)
    smoke_dir.mkdir(parents=True, exist_ok=True)
    smoke_doc = smoke_dir / "owned-workbench.3dm"
    runner_doc = smoke_dir / "runner-nonowned.3dm"
    artifacts.resolve_artifact_db_path = lambda: smoke_dir / "artifacts.db"
    artifacts._reset_artifact_registry_singleton()

    session = None
    try:
        status, owned_row, used = "no_attempt", None, 0
        for attempt in range(_MAX_ATTEMPTS):
            status, session, owned_row = await _attempt(smoke_doc)
            used = attempt + 1
            if status in ("observed", "observe_failed"):
                break
            if session:  # launch_failed / died -> dispose this attempt's Workbench, retry
                await server.call_tool("rhino_workbench_close", {"session": session})
                session = None
            print(f"[retry] attempt {used} -> {status}; relaunching disposable Workbench", flush=True)

        if status == "observed":
            _record("observe_present",
                    owned_row.get("source") == "owned_workbench"
                    and owned_row.get("fileState") == "present",
                    f"attempt {used}/{_MAX_ATTEMPTS} source={owned_row.get('source')} "
                    f"state={owned_row.get('fileState')}")
        elif status == "observe_failed":
            _record("observe_present", False,
                    "owned Workbench stayed alive but the saved artifact never appeared")
            return _finish()
        else:
            _record("observe_present", False,
                    f"owned Workbench died/unavailable before observe across {_MAX_ATTEMPTS} "
                    f"attempts ({status}) -- P4/P5/Rhino Workbench stability blocked the P6 "
                    "smoke, NOT a P6 artifact-perception failure")
            return _finish()

        # The Workbench survived and the owned save was perceived.
        want = artifacts.normalize_path(str(smoke_doc))

        # I8: a NON-owned (runner) saved doc is never auto-persisted.
        await server.call_tool("rhino_document_ops", {"action": "save", "path": str(runner_doc)})
        runner_norm = artifacts.normalize_path(str(runner_doc))
        await server.call_tool("rhino_workbench_list", {})  # fire observe again
        rows = await _artifacts()
        _record("non_owned_not_persisted", runner_norm not in rows,
                f"runner_in_list={runner_norm in rows}")

        # Close the owned Workbench -> the artifact row must PERSIST.
        closed = _json(_text(await server.call_tool("rhino_workbench_close", {"session": session})))
        if closed.get("closed"):
            session = None
        still = (await _artifacts()).get(want)
        _record("persists_after_close",
                still is not None and still.get("fileState") == "present",
                f"state={still.get('fileState') if still else None}")

        # Deregister forgets the ROW but NEVER the .3dm (I5).
        await server.call_tool("rhino_artifact_deregister", {"path": str(smoke_doc)})
        rows3 = await _artifacts()
        _record("deregister_keeps_file",
                want not in rows3 and os.path.exists(smoke_doc),
                f"row_gone={want not in rows3} file_exists={os.path.exists(smoke_doc)}")
        return _finish()
    finally:
        if session:
            await server.call_tool("rhino_workbench_close", {"session": session})
        artifacts._reset_artifact_registry_singleton()
        shutil.rmtree(smoke_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
