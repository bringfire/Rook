"""P7 linked-block coordinator helpers.

Pure module: no server imports, no Rhino calls, no P7-registry dependency.
Currently hosts the deterministic block-definition naming helper; future
home for the linked-block merge executor + comparator.
"""
from __future__ import annotations

import hashlib

# Versioned/purpose prefix so the scheme can evolve unambiguously.
_SCHEME = "rook_p7lb"
_HEX_DIGITS = frozenset("0123456789abcdef")


def block_def_name(contract_id: str, source_artifact_id: str) -> str:
    """Deterministic Rhino block-definition NAME for a P7 linked-block merge.

    A stable idempotency ADDRESS, not a human explanation — Rhino's Block
    Manager already shows each linked block's source path in its own column.

    contract_id is HASHED (generated ids may not be restricted-alphabet).
    source_artifact_id is the canonical SHA-256 hex from
    artifacts.artifact_id_for and is validated fail-closed (exactly 64
    lowercase-hex chars — a full SHA-256) so a truncated/malformed id raises
    rather than silently minting a wrong-but-valid durable address (a 16-hex
    prefix must not alias the full id to the same name).

    Output: lowercase [a-z0-9_-], ~35 chars, far under Rhino name limits.
    """
    sid = source_artifact_id.lower()
    if len(sid) != 64 or any(c not in _HEX_DIGITS for c in sid):
        raise ValueError(
            "source_artifact_id must be a full SHA-256 hex (64 hex chars); "
            f"got {source_artifact_id!r}"
        )
    contract_hash = hashlib.sha256(contract_id.encode("utf-8")).hexdigest()[:8]
    return f"{_SCHEME}_{contract_hash}_{sid[:16]}"


# ----- P7 Slice 4: per-source planned actions (dry-run) + outcomes (execute) -----
# Planned actions (also the dry-run plannedAction values):
WOULD_CREATE_LINK = "would_create_link"
WOULD_REFRESH_EXISTING = "would_refresh_existing"
ALREADY_LINKED = "already_linked"
CONFLICT_NONLINKED = "conflict_nonlinked"
CONFLICT_DIFFERENT_SOURCE = "conflict_different_source"
SOURCE_ARTIFACT_NOT_PRESENT = "source_artifact_not_present"
SOURCE_PATH_UNRESOLVABLE = "source_path_unresolvable"
# Execute-mode outcomes for the actionable plans:
CREATED_LINK = "created_link"
REFRESHED_EXISTING = "refreshed_existing"
BLOCK_LINK_FAILED = "block_link_failed"
BLOCK_REFRESH_FAILED = "block_refresh_failed"


def plan_source_action(*, block_facts, expected_source_artifact_id,
                       observed_source_artifact_id, source_present, refresh_policy):
    """PURE classification of one source against the target document's block table.

    block_facts: the /blocks entry for the deterministic block name, or None if absent.
        When present: {"isLinked": bool, "sourcePath": str, "blockType": str}.
    observed_source_artifact_id: artifact_id_for(resolved observed sourcePath), or None
        if the observed linked path can't be resolved.
    source_present: True iff the contract source resolves to a P6 row file_state=='present'.

    Hard conflicts dominate (the name is taken by the wrong thing — a blocker regardless).
    The strict present-bar (Finding 2) gates EVERY success-eligible action, including
    already_linked: refresh_policy chooses refresh-vs-no-op only AFTER presence is proven.
    """
    if block_facts is None:
        return WOULD_CREATE_LINK if source_present else SOURCE_ARTIFACT_NOT_PRESENT
    if not block_facts.get("isLinked"):
        return CONFLICT_NONLINKED
    if observed_source_artifact_id is None:
        return SOURCE_PATH_UNRESOLVABLE
    if observed_source_artifact_id != expected_source_artifact_id:
        return CONFLICT_DIFFERENT_SOURCE
    if not source_present:                       # present-bar before refresh-vs-no-op
        return SOURCE_ARTIFACT_NOT_PRESENT
    if refresh_policy == "refresh_on_demand":
        return WOULD_REFRESH_EXISTING
    return ALREADY_LINKED
