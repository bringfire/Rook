"""Live-Rhino end-to-end for P7 Slice 5 — chained linked-block recomposition.
HELD: requires a running Rhino with RookNative deployed; skips cleanly when no Rhino is live.
Hermetic P6/P7 registries (temp dbs) keep the in-process contract graph to exactly {A, B} and
leave the real stores untouched.

Run (throwaway session — replaces the active document repeatedly):
    mcp_server\\.venv\\Scripts\\python.exe -m pytest -m requires_rhino ^
        mcp_server/tests/test_merge_contract_chain_live.py -s
"""
from __future__ import annotations
import os
import tempfile
import pytest

from rook import artifacts, work_units, linked_blocks as lb
from rook.server import _mcp_tool_executor

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_PREFIX = lb._SCHEME + "_"   # "rook_p7lb_" — Rook's deterministic linked-block name prefix


@pytest.fixture
def hermetic_registries(tmp_path, monkeypatch):
    """In-process P6/P7 registries pointed at temp dbs so the contract graph is exactly what
    this test records and the real stores are untouched."""
    monkeypatch.setattr(work_units, "resolve_work_units_db_path", lambda: tmp_path / "work_units.db")
    monkeypatch.setattr(artifacts, "resolve_artifact_db_path", lambda: tmp_path / "artifacts.db")
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()
    yield tmp_path
    work_units._reset_work_units_registry_singleton()
    artifacts._reset_artifact_registry_singleton()


def _tmp(tag):
    return os.path.join(tempfile.gettempdir(), f"rook_p7chain_{os.getpid()}_{tag}.3dm")


async def _single_live_session():
    """The single-Rhino harness contract, enforced as the FIRST operation (read-only) so no
    mutation can hit an ambiguous instance: skip on zero live; fail on more than one."""
    sess = await _mcp_tool_executor("rhino_sessions", {})
    items = (sess.get("data") or sess).get("sessions") or []
    live = [s for s in items if (s.get("liveness") or {}).get("state") == "live"]
    if not live:
        pytest.skip("no live Rhino; held live test")
    assert len(live) == 1, (
        f"multiple live Rhino sessions ({len(live)}): close the extras, or run under an owned "
        "Workbench in a later slice. Harness safety guard, not a product failure.")
    return live[0]["session"]


async def _new_doc_with_box(name, c1, c2, path):
    n = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
    assert n.get("success") is not False, f"new for {name} failed: {n!r}"
    c = await _mcp_tool_executor("rhino_create",
        {"type": "BOX", "corner1": c1, "corner2": c2, "name": name})
    assert c.get("success") is not False, f"create {name} failed: {c!r}"
    s = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": path})
    assert s.get("success") is not False, f"save {name} failed: {s!r}"


async def _open(path):
    r = await _mcp_tool_executor("rhino_document_ops", {"action": "open", "path": path})
    assert r.get("success") is not False, f"open {path} failed: {r!r}"


async def _execute(cid, session):
    return await _mcp_tool_executor("rhino_merge_contract_execute",
        {"contractId": cid, "session": session, "expectedMergeKind": "linked_block"})


async def _assert_linked(session, names):
    """Each deterministic name resolves and isLinked on the active doc of `session`."""
    for nm in names:
        info = await _mcp_tool_executor("rhino_block_info", {"name": nm, "session": session})
        assert info.get("isLinked") is True, f"{nm}: {info!r}"


async def _rook_block_names(session):
    """Set of Rook deterministic linked-block names (rook_p7lb_*) in the active doc. Successful
    _mcp_tool_executor payloads are data-only, so rhino_blocks is {'blocks': [...]} (not wrapped)."""
    blocks = await _mcp_tool_executor("rhino_blocks", {"session": session})
    assert blocks.get("success") is not False, f"rhino_blocks failed: {blocks!r}"
    rows = (blocks.get("data") or blocks).get("blocks") or []
    return {b.get("name") for b in rows if str(b.get("name") or "").startswith(_PREFIX)}


async def test_chain_recomposition_end_to_end(hermetic_registries):
    # 0. SESSION GUARD FIRST (read-only) — before any document mutation.
    session = await _single_live_session()
    s1 = _tmp("s1"); s2 = _tmp("s2"); inter = _tmp("inter"); master = _tmp("master")
    paths = [s1, s2, inter, master]
    try:
        # 1. four saved docs (asserted), each registered in P6 (temp registry)
        await _new_doc_with_box("s1box", [0, 0, 0], [1, 1, 1], s1)
        await _new_doc_with_box("s2box", [2, 0, 0], [3, 1, 1], s2)
        await _new_doc_with_box("interbox", [0, 2, 0], [1, 3, 1], inter)
        await _new_doc_with_box("masterbox", [2, 2, 0], [3, 3, 1], master)
        ids = {}
        for p in paths:
            r = await artifacts.register_artifact(p)
            ids[p] = r["data"]["artifact"]["artifactId"]
        s1_id, s2_id, inter_id, master_id = ids[s1], ids[s2], ids[inter], ids[master]

        # 2. record A: [s1,s2] -> inter ; B: [inter] -> master
        recA = await work_units.record_merge_contract(
            target_artifact_id=inter_id, source_artifact_ids=[s1_id, s2_id],
            merge_kind="linked_block", refresh_policy="refresh_on_demand")
        recB = await work_units.record_merge_contract(
            target_artifact_id=master_id, source_artifact_ids=[inter_id],
            merge_kind="linked_block", refresh_policy="refresh_on_demand")
        cid_A = recA["data"]["contractId"]; cid_B = recB["data"]["contractId"]

        # 3. scoped plan == [A, B]
        reg = work_units.work_units_registry()
        plan = work_units.plan_linked_block_execution(reg, [cid_A, cid_B])
        assert plan["ok"] is True, plan
        assert plan["plan"] == [{"contractId": cid_A, "targetArtifactId": inter_id},
                                {"contractId": cid_B, "targetArtifactId": master_id}], plan

        name_A1 = lb.block_def_name(cid_A, s1_id)
        name_A2 = lb.block_def_name(cid_A, s2_id)
        name_B = lb.block_def_name(cid_B, inter_id)

        # 4. step A: open inter, execute, assert WHILE inter is active
        await _open(inter)
        exA = await _execute(cid_A, session)
        assert exA.get("executed") is True and exA.get("saved") is True, exA
        assert {e["sourceArtifactId"]: e["outcome"] for e in exA["perSource"]} == {
            s1_id: lb.CREATED_LINK, s2_id: lb.CREATED_LINK}, exA
        await _assert_linked(session, [name_A1, name_A2])
        inter_names_1 = await _rook_block_names(session)

        # step B: open master, execute, assert WHILE master is active
        await _open(master)
        exB = await _execute(cid_B, session)
        assert exB.get("executed") is True and exB.get("saved") is True, exB
        assert exB["perSource"][0]["outcome"] == lb.CREATED_LINK, exB
        await _assert_linked(session, [name_B])   # master consumes the intermediate id, not s1/s2
        master_names_1 = await _rook_block_names(session)
        infoB = await _mcp_tool_executor("rhino_block_info", {"name": name_B, "session": session})
        print("OBSERVE master name_B sourcePath:", infoB.get("sourcePath"))

        # 5. idempotent re-run: refreshed_existing, saved, deterministic names still resolve
        await _open(inter)
        exA2 = await _execute(cid_A, session)
        assert exA2.get("saved") is True, exA2
        assert {e["outcome"] for e in exA2["perSource"]} == {lb.REFRESHED_EXISTING}, exA2
        await _assert_linked(session, [name_A1, name_A2])
        assert await _rook_block_names(session) == inter_names_1, "intermediate rook-def set changed"

        await _open(master)
        exB2 = await _execute(cid_B, session)
        assert exB2.get("saved") is True, exB2
        assert exB2["perSource"][0]["outcome"] == lb.REFRESHED_EXISTING, exB2
        await _assert_linked(session, [name_B])
        assert await _rook_block_names(session) == master_names_1, "master rook-def set changed"

        # 6. OBSERVATIONS (non-failing): evict master from the single active slot, reopen, and
        # record sourcePath + whether /blocks surfaces nested source defs. Nested-refresh
        # propagation is observed, not asserted (spec §6).
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})  # evict master
        await _open(master)
        reopened = await _mcp_tool_executor("rhino_block_info", {"name": name_B, "session": session})
        print("OBSERVE master name_B after evict+reopen:", reopened)
        print("OBSERVE master rook_p7lb_* names (nested presentation?):",
              sorted(await _rook_block_names(session)))
    finally:
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass
