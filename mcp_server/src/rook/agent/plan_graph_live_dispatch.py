"""LM4B live-dispatch composition root for one PlanGraph producer node.

Also hosts the LM4C ``ToolExecutor`` contract bridge: the production agent seam
exposes the looser ``Callable[[str, dict], Any]`` (sync-or-async) shape, which
``run_live_producer_node_with_executor`` normalizes before delegating to the
strict-async kernel. Result shape and error taxonomy stay owned by LM4A.
"""

from __future__ import annotations

import inspect
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


async def run_live_producer_node_with_executor(
    graph: "PlanGraph",
    node_id: str,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> "LiveProducerResult":
    """Drive one live producer node from a production ``ToolExecutor`` callable.

    ``tool_executor`` follows the agent seam's looser contract
    (``Callable[[str, dict], Any]`` -- sync OR async return). The inner ``dispatch``
    normalizes awaitability only, then delegates to the LM4B/LM4A kernel. It does
    not validate the result: a malformed/non-dict result flows into LM4A's
    raw-result handling, and a raising executor maps to LM4A ``dispatch_failed``.
    """
    async def dispatch(name: str, params: dict[str, Any]) -> dict[str, Any]:
        result = tool_executor(name, params)
        if inspect.isawaitable(result):
            result = await result
        return result

    return await run_live_producer_node(graph, node_id, dispatch)
