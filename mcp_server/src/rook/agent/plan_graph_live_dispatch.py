"""LM4B live-dispatch composition root for one PlanGraph producer node."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_live import apply_live_producer_node

if TYPE_CHECKING:
    from rook.agent.plan_graph_live import LiveProducerResult
    from rook.learning.plan_graph import PlanGraph


async def run_live_producer_node(
    graph: "PlanGraph",
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> "LiveProducerResult":
    """Drive one live producer node through an injected dispatch callable."""
    return await apply_live_producer_node(graph, node_id, dispatch)
