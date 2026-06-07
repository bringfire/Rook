"""Live-Rhino end-to-end for the P7 linked-block executor. HELD: requires a running Rhino
with the #227 RookNative deployed. Skips cleanly when Rhino is unreachable (fresh_document).
Run (throwaway session):
    mcp_server\\.venv\\Scripts\\python.exe -m pytest -m requires_rhino ^
        mcp_server/tests/test_merge_contract_execute_live.py -s
IMPORTANT: replaces the active Rhino document; use a throwaway session.
"""
from __future__ import annotations
import os
import tempfile
import pytest

from rook import artifacts, work_units, linked_blocks as lb
from rook.server import _mcp_tool_executor
from .conftest import fresh_document  # noqa: F401

pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _tmp(tag):
    return os.path.join(tempfile.gettempdir(), f"rook_p7exec_{os.getpid()}_{tag}.3dm")


async def _save_box_source(path):
    await _mcp_tool_executor("rhino_create",
        {"type": "BOX", "corner1": [0, 0, 0], "corner2": [1, 1, 1], "name": "srcbox"})
    s = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": path})
    assert s.get("success") is not False, f"save source failed: {s!r}"


async def _session_for_doc(target_path):
    """Select the session whose active document IS our target — the explicit-session contract.
    rhino_sessions entries carry a 'session' id (e.g. 'rhino-<pid>'); pick by document identity,
    NOT ordering ('first live' would be wrong on a multi-Rhino machine). A dead session won't
    return a matching doc, so the match also filters liveness implicitly."""
    sess = await _mcp_tool_executor("rhino_sessions", {})
    items = (sess.get("data") or {}).get("sessions") or sess.get("sessions") or []
    target_norm = artifacts.normalize_path(target_path)
    for s in items:
        sid = s.get("session") or s.get("sessionId") or s.get("id")
        if not sid:
            continue
        doc = await _mcp_tool_executor("rhino_document", {"session": sid})
        path = (doc.get("documentPath") or doc.get("path")
                or (doc.get("data") or {}).get("documentPath"))
        if path and artifacts.normalize_path(path) == target_norm:
            return sid
    raise AssertionError(f"no session's active doc == {target_path!r}; sessions={items!r}")


async def test_execute_linked_block_contract_end_to_end(fresh_document):
    src = _tmp("src")
    tgt = _tmp("tgt")
    try:
        # source doc
        await _save_box_source(src)
        # target doc (separate content), saved so it has a path
        await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        await _mcp_tool_executor("rhino_create",
            {"type": "BOX", "corner1": [5, 5, 0], "corner2": [6, 6, 1], "name": "tgtbox"})
        st = await _mcp_tool_executor("rhino_document_ops", {"action": "save", "path": tgt})
        assert st.get("success") is not False

        rt = await artifacts.register_artifact(tgt)
        rs = await artifacts.register_artifact(src)
        tgt_id = rt["data"]["artifact"]["artifactId"]
        src_id = rs["data"]["artifact"]["artifactId"]
        rec = await work_units.record_merge_contract(
            target_artifact_id=tgt_id, source_artifact_ids=[src_id],
            merge_kind="linked_block", refresh_policy="refresh_on_demand")
        cid = rec["data"]["contractId"]
        session = await _session_for_doc(tgt)  # explicit-session contract: pick by document identity

        # dry-run: executable, would_create_link
        dry = await _mcp_tool_executor("rhino_merge_contract_execute",
            {"contractId": cid, "session": session, "expectedMergeKind": "linked_block", "dryRun": True})
        assert dry.get("dryRun") is True and dry.get("executable") is True, dry
        assert dry["perSource"][0]["plannedAction"] == lb.WOULD_CREATE_LINK

        # execute: creates + saves
        ex = await _mcp_tool_executor("rhino_merge_contract_execute",
            {"contractId": cid, "session": session, "expectedMergeKind": "linked_block"})
        assert ex.get("executed") is True and ex.get("saved") is True, ex
        assert ex["perSource"][0]["outcome"] == lb.CREATED_LINK

        # the linked def is present + correct
        name = lb.block_def_name(cid, src_id)
        info = await _mcp_tool_executor("rhino_block_info", {"name": name})
        assert info.get("isLinked") is True, info

        # idempotent re-run: refreshed_existing (refresh_on_demand), no duplicate
        ex2 = await _mcp_tool_executor("rhino_merge_contract_execute",
            {"contractId": cid, "session": session, "expectedMergeKind": "linked_block"})
        assert ex2.get("saved") is True, ex2
        assert ex2["perSource"][0]["outcome"] == lb.REFRESHED_EXISTING, ex2
    finally:
        for p in (src, tgt):
            try:
                os.remove(p)
            except OSError:
                pass
