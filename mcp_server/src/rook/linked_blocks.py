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
