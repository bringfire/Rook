"""LM3F role-aware outcome projection.

Pure function that converts an already-captured ``NodeEvidence`` (its
``script_receipt``) into a ``NodeOutcome`` whose meaning depends on the node's
ROLE. The same receipt projects to different graph outcomes by role:

- ``artifact_producer`` treats artifact EXISTENCE as success
  (``created_with_errors`` -> ``succeeded`` when mutation evidence is present),
  decoupling ``status`` (existence / task progress) from ``verified`` (functional
  success). This is the projection that makes a producer node unlock a downstream
  verifier via the reducer's ``requires`` edge.
- ``artifact_verifier`` and ``direct_task`` treat the same receipt conservatively
  (``created_with_errors`` -> ``needs_repair``), riding the shared
  ``ARTIFACT_STATUS_TO_OUTCOME`` table.

Role-awareness is the layer ABOVE LM1F, not a correction to it. LM1F is unchanged.
``plan_graph_verifiers.script_receipt_verifier_outcome`` is a compatibility
wrapper delegating here with ``role="artifact_verifier"``; that role reproduces
LM3D verbatim (hard regression contract).

Never calls tools, inspects live state, schedules, or emits ``needs_escalation``.
Malformed evidence and deep-copy failures return a ``blocked`` outcome with an
explanatory error -- never an exception. An invalid ROLE, however, raises
``ValueError``: that is API misuse, not bad data.
"""

import copy
from typing import Literal

from rook.learning.plan_graph import NodeEvidence, NodeOutcome, PlanGraphNode
from rook.learning.plan_graph_outcomes import ARTIFACT_STATUS_TO_OUTCOME


OutcomeProjectionRole = Literal["direct_task", "artifact_producer", "artifact_verifier"]

_VALID_ROLES = frozenset(("direct_task", "artifact_producer", "artifact_verifier"))
_KNOWN_ARTIFACT_STATUSES = frozenset(ARTIFACT_STATUS_TO_OUTCOME)
_ROLE_PREFIX = {
    "direct_task": "task",
    "artifact_producer": "producer",
    "artifact_verifier": "verifier",
}
_MUTATION_DONE = frozenset(("created", "written", "updated"))

OUTCOME_PROJECTION_ROLE_KEY = "outcome_projection_role"


def projection_role_for_node(node: PlanGraphNode) -> OutcomeProjectionRole | None:
    """Return the node's declared projection role if present AND valid, else None.

    Reads ``node.metadata[OUTCOME_PROJECTION_ROLE_KEY]`` and validates it against
    the LM3F role set. Never raises -- node metadata is graph data, not API misuse
    (the raise stays in ``project_receipt_outcome`` for direct misuse).
    """
    value = node.metadata.get(OUTCOME_PROJECTION_ROLE_KEY)
    return value if value in _VALID_ROLES else None


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


def _has_mutation_evidence(receipt: dict, repair_anchor: dict | None) -> bool:
    """Producer GATE predicate. NOTE: requires a NON-EMPTY repair anchor."""
    mutation = receipt.get("mutation")
    if isinstance(mutation, dict) and mutation.get("status") in _MUTATION_DONE:
        return True
    if _component_guid(receipt, repair_anchor) is not None:
        return True
    if isinstance(repair_anchor, dict) and repair_anchor:
        return True
    return False


def _facts(receipt: dict, repair_anchor: dict | None) -> dict:
    """Facts helper (LM3D-equivalent): emit repair_anchor whenever it is a dict."""
    facts: dict = {}
    guid = _component_guid(receipt, repair_anchor)
    if guid is not None:
        facts["component_guid"] = guid
    if isinstance(repair_anchor, dict):
        facts["repair_anchor"] = repair_anchor
    return facts


def _reference_free_blocked(message, verified, tool_status, prefix) -> NodeOutcome:
    """Blocked with NO receipt/anchor references (missing/unrecognized/copy-fail)."""
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
        memory_updates={"node_summary": f"{prefix}: blocked"},
        message=message,
        error=message,
    )


def _conservative_outcome(
    artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status, prefix
) -> NodeOutcome:
    status = ARTIFACT_STATUS_TO_OUTCOME[artifact_status]
    if status == "succeeded":
        verified: bool | None = True
        message = f"{prefix}: artifact usable"
    elif status == "needs_repair":
        verified = False
        message = f"{prefix}: artifact needs repair"
    else:  # blocked: verification_pending / unknown
        verified = carried_verified
        message = f"{prefix}: artifact_status '{artifact_status}' is not usable"

    facts = _facts(receipt_copy, repair_anchor_copy)
    memory_updates: dict = {"node_summary": f"{prefix}: {status}"}
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


def _producer_success(receipt_copy, repair_anchor_copy, verified, message, tool_status) -> NodeOutcome:
    facts = _facts(receipt_copy, repair_anchor_copy)
    memory_updates: dict = {"node_summary": "producer: succeeded"}
    if facts:
        memory_updates["facts"] = facts
    return NodeOutcome(
        status="succeeded",
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


def _producer_blocked(message, receipt_copy, repair_anchor_copy, verified, tool_status, error) -> NodeOutcome:
    """Producer blocked with the cleanly-copied receipt PRESERVED, no facts."""
    return NodeOutcome(
        status="blocked",
        evidence=NodeEvidence(
            tool_status=tool_status,
            verified=verified,
            receipt=receipt_copy,
            repair_anchor=repair_anchor_copy,
            message=message,
            error=error,
        ),
        memory_updates={"node_summary": "producer: blocked"},
        message=message,
        error=error,
    )


def _producer_outcome(
    artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status
) -> NodeOutcome:
    if artifact_status == "usable":
        return _producer_success(
            receipt_copy, repair_anchor_copy, True, "producer: artifact usable", tool_status
        )
    if artifact_status == "unknown":
        return _producer_blocked(
            "producer: artifact_status 'unknown' is not usable",
            receipt_copy, repair_anchor_copy, carried_verified, tool_status, error=None,
        )
    # promoted rows: created_with_errors / written_with_errors / verification_pending
    if _has_mutation_evidence(receipt_copy, repair_anchor_copy):
        if artifact_status == "created_with_errors":
            return _producer_success(
                receipt_copy, repair_anchor_copy, False,
                "producer: artifact created with repairable errors", tool_status,
            )
        if artifact_status == "written_with_errors":
            return _producer_success(
                receipt_copy, repair_anchor_copy, False,
                "producer: artifact written with repairable errors", tool_status,
            )
        # verification_pending
        return _producer_success(
            receipt_copy, repair_anchor_copy, None,
            "producer: artifact produced, verification pending", tool_status,
        )
    return _producer_blocked(
        "producer: artifact existence unconfirmed",
        receipt_copy, repair_anchor_copy, carried_verified, tool_status,
        error="producer: artifact existence unconfirmed",
    )


def project_receipt_outcome(
    evidence: NodeEvidence | None, role: OutcomeProjectionRole
) -> NodeOutcome:
    """Project already-captured ``NodeEvidence`` into a role-aware ``NodeOutcome``.

    Raises ``ValueError`` for an unknown ``role`` (API misuse), before any evidence
    inspection. Malformed evidence / deep-copy failures return ``blocked``.
    """
    if role not in _VALID_ROLES:
        raise ValueError(f"Unknown outcome projection role: {role!r}")
    prefix = _ROLE_PREFIX[role]

    tool_status = evidence.tool_status if evidence is not None else None
    carried_verified = evidence.verified if evidence is not None else None

    receipt = evidence.receipt if evidence is not None else None
    if not isinstance(receipt, dict) or "artifact_status" not in receipt:
        return _reference_free_blocked(
            f"{prefix}: missing receipt or artifact_status", carried_verified, tool_status, prefix
        )

    artifact_status = receipt.get("artifact_status")
    if artifact_status not in _KNOWN_ARTIFACT_STATUSES:
        return _reference_free_blocked(
            f"{prefix}: unrecognized artifact_status '{artifact_status}'",
            carried_verified, tool_status, prefix,
        )

    try:
        receipt_copy = copy.deepcopy(receipt)
        repair_anchor_copy = (
            copy.deepcopy(evidence.repair_anchor)
            if evidence is not None and evidence.repair_anchor is not None
            else None
        )
    except Exception:
        return _reference_free_blocked(
            f"{prefix}: evidence copy failed", carried_verified, tool_status, prefix
        )

    if role == "artifact_producer":
        return _producer_outcome(
            artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status
        )
    return _conservative_outcome(
        artifact_status, receipt_copy, repair_anchor_copy, carried_verified, tool_status, prefix
    )
