"""LM3D verifier-outcome adapter (compatibility wrapper over LM3F).

``script_receipt_verifier_outcome`` converts an already-captured ``NodeEvidence``
(its ``script_receipt``) into a *verifier node's* ``NodeOutcome``. As of LM3F the
projection logic lives in ``plan_graph_projection.project_receipt_outcome``; this
module keeps the original public function as the ``artifact_verifier`` role, so
existing callers (e.g. ``plan_graph_runner``) and the LM3D regression tests are
unchanged.

Distinct from LM1F (``plan_graph_outcomes.node_outcome_from_tool_result``), which
consumes a *raw tool result* and produces the *executing* node's outcome.
"""

from rook.learning.plan_graph import NodeEvidence, NodeOutcome
from rook.learning.plan_graph_projection import project_receipt_outcome


def script_receipt_verifier_outcome(evidence: NodeEvidence | None) -> NodeOutcome:
    """Re-judge an already-captured ``NodeEvidence`` as a verifier node would.

    Thin compatibility wrapper for the ``artifact_verifier`` projection role. Reads
    ``evidence.receipt``'s ``artifact_status`` and maps it through the shared
    ``ARTIFACT_STATUS_TO_OUTCOME`` table. Malformed evidence, an unrecognized
    status, or a deep-copy failure return ``blocked`` with an explanatory error.
    Never raises; never emits ``needs_escalation``.
    """
    return project_receipt_outcome(evidence, "artifact_verifier")
