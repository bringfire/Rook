"""Live P3 session-targeted-routing harness.

Run via `scripts/run_rhino_runtime_harness.py --smoke p3-session-mutation`, which
launches an OWNED throwaway Rhino and sets ROOK_RHINO_PROCESS_ID / ROOK_RHINO_PORT.
It drives the REAL server.call_tool routing wrapper against the owned session and
validates the routing-error paths.

Honesty boundaries (so the PR claim stays precise):
  - The bypass / conflict scenarios that need a "second instance" use a SYNTHETIC
    second discovery record (a fabricated native record with a throwaway pid/port),
    NOT a second real Rhino. They validate the routing decision, not a 2nd process.
  - Only the owned Rhino is ever mutated; it is shut down gracefully by the harness.
    No scenario executes against any other discovered Rhino (the bare mutate is
    REFUSED before it runs; every real call is session-pinned to the owned pid).

Scenarios:
  1. session_routes_mutation  — session-route a mutation, then read the object count
                                 back through the SAME session and assert it rose
                                 (success returns `data`; failures are "Error:"-
                                 prefixed, so there is no '"success": true' check).
  2. bogus_session_not_found   — session=rhino-<unused> -> rhino_session_not_found.
  3. session_disambiguates     — with a synthetic 2nd native record, FIRST prove a
                                 bare mutate refuses (multiple_rhino_instances), THEN
                                 prove session=<owned> routes the same call cleanly.
  4. selector_conflict         — session=<owned> + a synthetic different-pid port
                                 -> selector_conflict.
  5. non_routed_reject         — call_tool(knowledge_query, session=...) ->
                                 session_not_targetable.
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

from rook import bridge, server, targeting  # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str) -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _owned() -> tuple[int, int]:
    return int(os.environ["ROOK_RHINO_PROCESS_ID"]), int(os.environ["ROOK_RHINO_PORT"])


def _text(result) -> str:
    return result[0].text if result else ""


def _object_count(text: str) -> int:
    try:
        d = json.loads(text)
        if isinstance(d, dict):
            inner = d.get("data") if isinstance(d.get("data"), dict) else {}
            return int(d.get("objectCount") or inner.get("objectCount") or 0)
    except Exception:
        pass
    return -1


async def scenario_session_routes_mutation(pid: int) -> None:
    # Prove a mutation actually LANDS in the named session: read the object count
    # before and after, through the SAME session. call_tool success returns just
    # `data` and failures are prefixed "Error:", so the honest signal is
    # "not an Error" + a concrete count delta — never a '"success": true' substring.
    sess = f"rhino-{pid}"
    before = _text(await server.call_tool("rhino_document", {"session": sess}))
    create = _text(await server.call_tool(
        "rhino_execute",
        {"session": sess, "code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)"},
    ))
    after = _text(await server.call_tool("rhino_document", {"session": sess}))
    created_ok = not create.startswith("Error:")
    readback_ok = _object_count(after) > _object_count(before) >= 0
    _record(
        "session_routes_mutation", created_ok and readback_ok,
        f"created_ok={created_ok}, before={_object_count(before)}, after={_object_count(after)}",
    )


async def scenario_bogus_session(pid: int) -> None:
    txt = _text(await server.call_tool(
        "rhino_execute", {"session": "rhino-99999999", "code": "print(1)"}
    ))
    _record("bogus_session_not_found", "rhino_session_not_found" in txt, txt[:160])


def _patch_discover_with_synthetic(real: list[dict]) -> None:
    synthetic = {"host": "127.0.0.1", "port": 1, "processId": 424242, "pluginType": "native"}

    def fake_discover():
        return list(real) + [synthetic]

    server.discover_instances = fake_discover
    targeting.discover_instances = fake_discover


def _restore_discover() -> None:
    server.discover_instances = bridge.discover_instances
    targeting.discover_instances = bridge.discover_instances


async def scenario_disambiguates(pid: int) -> None:
    # Honesty (P2 standard): FIRST prove a bare mutate REFUSES with two native
    # instances, THEN prove the same call routes cleanly when a session names the
    # target. The second instance is a SYNTHETIC discovery record, not a 2nd Rhino.
    _patch_discover_with_synthetic(bridge.discover_instances())
    try:
        bare = _text(await server.call_tool("rhino_execute", {"code": "1+1"}))
        refused = "multiple_rhino_instances" in bare
        named = _text(await server.call_tool(
            "rhino_execute", {"session": f"rhino-{pid}", "code": "1+1"}
        ))
        routed = (
            "multiple_rhino_instances" not in named
            and "rhino_session_not_found" not in named
            and not named.startswith("Error:")
        )
        _record("session_disambiguates", refused and routed,
                f"bare_refused={refused}, named_routed={routed}")
    finally:
        _restore_discover()


async def scenario_conflict(pid: int) -> None:
    _patch_discover_with_synthetic(bridge.discover_instances())
    try:
        txt = _text(await server.call_tool(
            "rhino_execute", {"session": f"rhino-{pid}", "port": 1, "code": "print(1)"}
        ))
        _record("selector_conflict", "selector_conflict" in txt, txt[:160])
    finally:
        _restore_discover()


async def scenario_non_routed_reject(pid: int) -> None:
    txt = _text(await server.call_tool(
        "knowledge_query", {"session": f"rhino-{pid}", "intent": "x"}
    ))
    _record("non_routed_reject", "session_not_targetable" in txt, txt[:160])


async def main() -> int:
    pid, port = _owned()
    print(f"Owned Rhino: pid={pid} port={port}", flush=True)
    await scenario_session_routes_mutation(pid)
    await scenario_bogus_session(pid)
    await scenario_disambiguates(pid)
    await scenario_conflict(pid)
    await scenario_non_routed_reject(pid)

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"\n=== P3 live smoke: {passed}/{len(_RESULTS)} PASS ===", flush=True)
    return 0 if passed == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
