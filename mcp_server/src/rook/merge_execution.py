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
        # (Task 5 continues here: classify; Task 6: apply + save.)
        raise NotImplementedError("classify + apply lands in Task 5-6")
