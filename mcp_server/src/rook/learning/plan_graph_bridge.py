"""LM1G PlanGraph tool-result bridge.

A single pure seam that composes the LM1F tool-result adapter with the LM1E
PlanGraph reducer. Given a raw tool-result dictionary, it produces a
``NodeOutcome`` and applies it to a named node.

The bridge holds no policy: it does not select runnable nodes, walk the graph,
check readiness, retry, escalate, or inspect ``script_receipt`` fields. Receipt
interpretation lives in ``plan_graph_outcomes``; graph transitions live in
``plan_graph``.
"""

from typing import Any

from rook.learning.plan_graph import PlanGraph, apply_outcome
from rook.learning.plan_graph_outcomes import node_outcome_from_tool_result


def apply_tool_result(
    graph: PlanGraph, node_id: str, raw_result: Any
) -> PlanGraph:
    """Adapt ``raw_result`` to a ``NodeOutcome`` and apply it to ``node_id``.

    Returns a new graph. Raises ``ValueError`` for an unknown ``node_id``
    (passed through from ``apply_outcome``). Does not mutate ``graph``.
    """
    outcome = node_outcome_from_tool_result(raw_result)
    return apply_outcome(graph, node_id, outcome)
