"""P7 Slice 4 — linked-block merge executor (the first Rhino-mutating P7 tool).

I/O shell: resolves a strict linked_block merge_contract + its P6 sources, pins the
selected session via bridge.rhino_request_context, classifies each source via the PURE
linked_blocks.plan_source_action, and (unless dry_run) ensures each linked block + saves
the target. Writes nothing durable; the saved .3dm is the execution artifact.
See docs/superpowers/specs/2026-06-07-p7-linked-block-executor-design.md.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Callable

from . import artifacts as _artifacts
from . import bridge as _bridge
from . import linked_blocks as _lb
from . import targeting as _targeting
from . import work_units as _work_units

CallTool = Callable[[str, dict], Awaitable[dict]]

_SUPPORTED_MERGE_KINDS = ("linked_block",)

_RETRYABLE = {
    "invalid_argument": False, "session_required": False,
    "invalid_session_id": False, "rhino_session_not_found": False,
    "panel_target_locked": False, "panel_target_stale": True,
    "panel_target_config_error": False, "rhino_target_unavailable": True,
    "contract_not_found": False, "merge_kind_mismatch": False, "unsupported_merge_kind": False,
    "target_not_open": True, "target_document_mismatch": True,
    "block_table_read_failed": True,
    "merge_contract_not_executable": False,
    "document_save_failed": True, "merge_contract_execution_incomplete": True,
}

_HARD_BLOCKERS = frozenset({
    _lb.CONFLICT_NONLINKED, _lb.CONFLICT_DIFFERENT_SOURCE,
    _lb.SOURCE_ARTIFACT_NOT_PRESENT, _lb.SOURCE_PATH_UNRESOLVABLE,
})


def _err(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "data": {
        "code": code, "message": message, "retryable": _RETRYABLE.get(code, True), **extra}}


def _resolve_session(session: str):
    """Resolve the explicit selector to a concrete route. has_explicit_session=True is
    load-bearing — without it resolve_tool_route ignores the selector and falls through to
    ambient routing (the very thing this slice forbids)."""
    route = _targeting.resolve_tool_route(
        "rhino_document", explicit_session=session, has_explicit_session=True)
    if not route.success:
        return None, _err(route.error or "rhino_target_unavailable",
                          f"Could not resolve session {session!r}: {route.error}.")
    if route.target is None:
        return None, _err("rhino_target_unavailable",
                          f"Session {session!r} resolved to no live instance.")
    return route, None


async def _read_active_doc_path(call_tool: CallTool):
    """(path, err). path is the active document's OS path; target_not_open when absent/unsaved."""
    resp = await call_tool("rhino_document", {})
    if resp.get("success") is False:
        return None, _err("target_not_open", "Could not read the active document on the session.")
    data = resp.get("data") or {}
    path = data.get("documentPath") or data.get("path")
    if not path:
        return None, _err("target_not_open",
                          "The selected session has no saved active document (no path).")
    return path, None


def _verify_target_identity(active_path: str, target_artifact_id: str):
    norm = _artifacts.normalize_path(active_path)
    if _artifacts.artifact_id_for(norm) != target_artifact_id:
        return _err("target_document_mismatch",
                    "The selected session's active document is not the contract target.",
                    activeDocumentPath=active_path, targetArtifactId=target_artifact_id)
    return None


async def _resolve_source(source_artifact_id: str):
    """(path, present). path is the normalized P6 path or None; present iff a P6 row exists
    and file_state == 'present'."""
    row = await asyncio.to_thread(
        lambda: _artifacts.artifact_registry().get(artifact_id=source_artifact_id))
    if row is None:
        return None, False
    return row.path, (row.file_state == "present")


def _observed_source_artifact_id(block_facts: dict, target_dir: str):
    """artifact id of an existing linked block's sourcePath; relative paths resolve against the
    target document's directory first. None when empty/unparseable."""
    raw = (block_facts or {}).get("sourcePath") or ""
    if not raw:
        return None
    try:
        p = raw if os.path.isabs(raw) else os.path.join(target_dir, raw)
        return _artifacts.artifact_id_for(_artifacts.normalize_path(p))
    except Exception:
        return None


async def _read_blocks(call_tool: CallTool):
    """Read the target document's block table ONCE. (by_name, None) on success — a SUCCESSFUL read
    of an empty table is {}; a FAILED read is fail-closed to (None, err) so a read failure is NEVER
    mistaken for 'no existing defs' (which would let mutation proceed past a failed pre-flight read)."""
    resp = await call_tool("rhino_blocks", {})
    if resp.get("success") is False:
        return None, _err("block_table_read_failed",
                          "Could not read the target document's block table; not mutating.")
    blocks = (resp.get("data") or {}).get("blocks") or []
    return {b.get("name"): b for b in blocks if isinstance(b, dict)}, None


async def _classify(by_name: dict, contract_id: str, sources, refresh_policy: str, target_dir: str):
    """Classify every source via the PURE planner over an already-read block snapshot. Returns the
    perSource list."""
    per_source = []
    for sid in sources:
        name = _lb.block_def_name(contract_id, sid)
        facts = by_name.get(name)
        src_path, present = await _resolve_source(sid)
        observed = _observed_source_artifact_id(facts, target_dir) if facts else None
        action = _lb.plan_source_action(
            block_facts=facts, expected_source_artifact_id=sid,
            observed_source_artifact_id=observed, source_present=present,
            refresh_policy=refresh_policy)
        per_source.append({
            "sourceArtifactId": sid, "blockName": name, "plannedAction": action,
            "sourcePath": src_path, "observedSourcePath": (facts or {}).get("sourcePath"),
            "observedSourceArtifactId": observed, "isLinked": (facts or {}).get("isLinked"),
            "blockType": (facts or {}).get("blockType")})
    return per_source


def _blockers_of(per_source):
    return [{"sourceArtifactId": e["sourceArtifactId"], "blockName": e["blockName"],
             "code": e["plannedAction"],
             "retryable": e["plannedAction"] == _lb.SOURCE_ARTIFACT_NOT_PRESENT}
            for e in per_source if e["plannedAction"] in _HARD_BLOCKERS]


async def execute_merge_contract(*, contract_id: str, session: str, expected_merge_kind: str,
                                 dry_run: bool, call_tool: CallTool) -> dict[str, Any]:
    # 1-2. lower-plane guards (reuse work_units' shared guards → identical codes)
    if (u := await _work_units._registry_unusable()) is not None:
        return u
    if (p6u := await _work_units._p6_unusable()) is not None:
        return p6u
    # 3. arguments
    if not isinstance(contract_id, str) or not contract_id.strip():
        return _err("invalid_argument", "'contractId' must be a non-empty string.")
    if expected_merge_kind not in _work_units.MERGE_KINDS:
        return _err("invalid_argument",
                    f"'expectedMergeKind' must be one of {_work_units.MERGE_KINDS}.")
    if not isinstance(session, str) or not session.strip():
        return _err("session_required",
                    "'session' is required (e.g. 'rhino-<pid>'); no ambient routing fallback.")
    # 4-6. contract + kind gates
    reg = _work_units.work_units_registry()
    contract = await asyncio.to_thread(lambda: reg.get_contract(contract_id))
    if contract is None:
        return _err("contract_not_found", f"No merge contract {contract_id!r}.")
    if contract.merge_kind != expected_merge_kind:
        return _err("merge_kind_mismatch",
                    f"Contract kind {contract.merge_kind!r} != expectedMergeKind {expected_merge_kind!r}.",
                    contractMergeKind=contract.merge_kind, expectedMergeKind=expected_merge_kind)
    if contract.merge_kind not in _SUPPORTED_MERGE_KINDS:
        return _err("unsupported_merge_kind",
                    f"Slice 4 executes only {list(_SUPPORTED_MERGE_KINDS)}.",
                    supportedMergeKinds=list(_SUPPORTED_MERGE_KINDS))
    sources = await asyncio.to_thread(lambda: reg.sources_for(contract_id))
    # 7. resolve + pin the session
    route, serr = _resolve_session(session)
    if serr is not None:
        return serr
    # 8+. all Rhino-facing work inside the pinned routing context (Finding 1)
    with _bridge.rhino_request_context(
            port=route.target.port, process_id=route.target.process_id,
            document_serial_number=route.document_serial_number):
        active_path, terr = await _read_active_doc_path(call_tool)
        if terr is not None:
            return terr
        if (merr := _verify_target_identity(active_path, contract.target_artifact_id)) is not None:
            return merr
        target_dir = os.path.dirname(active_path)
        by_name, berr = await _read_blocks(call_tool)   # fail closed on a failed pre-flight read
        if berr is not None:
            return berr
        per_source = await _classify(by_name, contract_id, sources, contract.refresh_policy, target_dir)
        blockers = _blockers_of(per_source)
        if dry_run:
            return {"success": True, "data": {
                "dryRun": True, "executable": (len(blockers) == 0),
                "blockers": blockers, "perSource": per_source}}
        # (Task 6 continues here: pre-flight gate, apply, re-verify, save.)
        raise NotImplementedError("apply + save lands in Task 6")
