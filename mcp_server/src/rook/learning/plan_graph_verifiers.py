"""LM3D verifier-outcome adapter.

Pure adapter that converts an already-captured ``NodeEvidence`` (its
``script_receipt``) into a *verifier node's* ``NodeOutcome``. Distinct from LM1F
(``plan_graph_outcomes.node_outcome_from_tool_result``), which consumes a *raw
tool result* and produces the *executing* node's outcome. Both share one truth
table -- ``ARTIFACT_STATUS_TO_OUTCOME`` -- so a receipt's artifact_status can
never mean different things to the two adapters.

It never calls tools, inspects live state, schedules, or emits
``needs_escalation`` (escalation needs retry/attempt policy, not receipt status).
Malformed evidence and deep-copy failures return a ``blocked`` outcome with an
explanatory error, never an exception.
"""

import copy

from rook.learning.plan_graph import NodeEvidence, NodeOutcome
from rook.learning.plan_graph_outcomes import ARTIFACT_STATUS_TO_OUTCOME


_KNOWN_ARTIFACT_STATUSES = frozenset(ARTIFACT_STATUS_TO_OUTCOME)


def _component_guid(receipt: dict, repair_anchor: dict | None) -> str | None:
    mutation = receipt.get("mutation")
    if isinstance(mutation, dict):
        guid = mutation.get("component_guid")
        if isinstance(guid, str) and guid:
            return guid
    if isinstance(repair_anchor, dict):
        guid = repair_anchor.get("component_guid")
        if isinstance(guid, str) and guid:
            return guid
    return None


def _blocked_outcome(message: str, verified: bool | None, tool_status) -> NodeOutcome:
    """Blocked outcome with REFERENCE-FREE evidence (no receipt/anchor objects)."""
    return NodeOutcome(
        status="blocked",
        evidence=NodeEvidence(
            tool_status=tool_status,
            verified=verified,
            receipt=None,
            repair_anchor=None,
            message=message,
            error=message,
        ),
        memory_updates={"node_summary": "verifier: blocked"},
        message=message,
        error=message,
    )


def script_receipt_verifier_outcome(evidence: NodeEvidence | None) -> NodeOutcome:
    """Convert an already-captured ``NodeEvidence`` into a verifier ``NodeOutcome``.

    Reads ``evidence.receipt``'s ``artifact_status`` and maps it through the shared
    ``ARTIFACT_STATUS_TO_OUTCOME`` table. Malformed evidence, an unrecognized
    status, or a deep-copy failure return ``blocked`` with an explanatory error
    and reference-free evidence. Never raises; never emits ``needs_escalation``.
    """
    tool_status = evidence.tool_status if evidence is not None else None
    carried_verified = evidence.verified if evidence is not None else None

    receipt = evidence.receipt if evidence is not None else None
    if not isinstance(receipt, dict) or "artifact_status" not in receipt:
        return _blocked_outcome(
            "verifier: missing receipt or artifact_status",
            carried_verified,
            tool_status,
        )

    artifact_status = receipt.get("artifact_status")
    if artifact_status not in _KNOWN_ARTIFACT_STATUSES:
        return _blocked_outcome(
            f"verifier: unrecognized artifact_status '{artifact_status}'",
            carried_verified,
            tool_status,
        )

    status = ARTIFACT_STATUS_TO_OUTCOME[artifact_status]

    try:
        receipt_copy = copy.deepcopy(receipt)
        repair_anchor_copy = (
            copy.deepcopy(evidence.repair_anchor)
            if evidence.repair_anchor is not None
            else None
        )
    except Exception:
        return _blocked_outcome(
            "verifier: evidence copy failed",
            carried_verified,
            tool_status,
        )

    if status == "succeeded":
        verified: bool | None = True
        message = "verifier: artifact usable"
    elif status == "needs_repair":
        verified = False
        message = "verifier: artifact needs repair"
    else:  # blocked: verification_pending / unknown
        verified = carried_verified
        message = f"verifier: artifact_status '{artifact_status}' is not usable"

    facts: dict = {}
    guid = _component_guid(receipt_copy, repair_anchor_copy)
    if guid is not None:
        facts["component_guid"] = guid
    if isinstance(repair_anchor_copy, dict):
        facts["repair_anchor"] = repair_anchor_copy

    memory_updates: dict = {"node_summary": f"verifier: {status}"}
    if facts:
        memory_updates["facts"] = facts

    return NodeOutcome(
        status=status,
        evidence=NodeEvidence(
            tool_status=tool_status,
            verified=verified,
            receipt=receipt_copy,
            repair_anchor=repair_anchor_copy,
            message=message,
            error=None,
        ),
        memory_updates=memory_updates,
        message=message,
        error=None,
    )
