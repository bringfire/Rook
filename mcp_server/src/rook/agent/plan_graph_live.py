"""LM4A live producer-node dispatch adapter (Stage 5A).

Non-pure agent-layer adapter: resolves ONE PlanGraph ``artifact_producer`` node to
a dispatch call, fires it through an injected dispatch callable, and delegates
application to the pure runner (``apply_producer_result``). It CONSUMES the pure
PlanGraph seams and never alters or grows them.

Boundary invariants:
- Imports only PUBLIC pure symbols (``projection_role_for_node``,
  ``apply_producer_result``, types) and reads ``node.status`` directly for the live
  side-effect readiness preflight (a cheap gate that must not deep-copy node
  payloads). No private ``_producer_*`` helpers.
- Does NOT import the dispatcher / server / ChatRunner -- the dispatcher arrives
  only as the injected ``dispatch`` callable.
- Admissibility + tool-name resolution + param copy are ALL side-effect-free and
  precede dispatch: a non-admissible or unresolvable node never fires a tool.
- ``learning/plan_graph_*`` modules never import this adapter (agent -> learning,
  one direction).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from rook.learning.plan_graph import (
    OutcomeStatus,
    PlanGraph,
    PlanGraphNode,
)
from rook.learning.plan_graph_projection import (
    OUTCOME_PROJECTION_ROLE_KEY,
    projection_role_for_node,
)
from rook.learning.plan_graph_runner import apply_producer_result
from rook.tool_lifecycle import DispatchOrigin
from rook.tool_lifecycle_runtime import deny_if_contained


EXECUTION_PARAMS_KEY = "execution_params"

# A valid execution_ref is a non-whitespace, colon-free tool name with an
# optional trailing ``:vN`` version suffix (N = one or more digits). The tool
# name never contains a colon, so the only colon is the version separator.
_EXECUTION_REF_RE = re.compile(r"(?P<name>[^\s:]+)(?::v\d+)?")


LiveProducerReason = Literal[
    "unknown_node",
    "node_not_runnable",
    "role_missing",
    "role_invalid",
    "role_not_producer",
    "execution_ref_missing",
    "execution_ref_invalid",
    "tool_lifecycle_denied",
    "execution_params_missing",
    "execution_params_invalid",
    "params_copy_failed",
    "dispatch_failed",
]


@dataclass(frozen=True)
class LiveProducerResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    tool_name: str | None
    outcome_status: OutcomeStatus | None
    reason: LiveProducerReason | None


def _not_applied(
    graph: PlanGraph,
    node_id: str,
    tool_name: str | None,
    reason: LiveProducerReason,
) -> LiveProducerResult:
    return LiveProducerResult(
        graph=graph,
        applied=False,
        node_id=node_id,
        tool_name=tool_name,
        outcome_status=None,
        reason=reason,
    )


def _resolve_tool_name(
    execution_ref: Any,
) -> tuple[str | None, LiveProducerReason | None]:
    if execution_ref is None or execution_ref == "":
        return None, "execution_ref_missing"
    if not isinstance(execution_ref, str):
        # execution_ref is typed str | None; a non-string is malformed graph
        # data (not absence) -> invalid, not missing.
        return None, "execution_ref_invalid"
    match = _EXECUTION_REF_RE.fullmatch(execution_ref)
    if match is None:
        return None, "execution_ref_invalid"
    return match.group("name"), None


def _check_admissibility(graph: PlanGraph, node_id: str) -> LiveProducerReason | None:
    if node_id not in graph.nodes:
        return "unknown_node"
    node = graph.nodes[node_id]
    if node.status != "ready":
        return "node_not_runnable"
    if OUTCOME_PROJECTION_ROLE_KEY not in node.metadata:
        return "role_missing"
    role = projection_role_for_node(node)
    if role is None:
        return "role_invalid"
    if role != "artifact_producer":
        return "role_not_producer"
    return None


def _resolve_params(
    node: PlanGraphNode,
) -> tuple[dict[str, Any] | None, LiveProducerReason | None]:
    if EXECUTION_PARAMS_KEY not in node.metadata:
        return None, "execution_params_missing"
    params_source = node.metadata[EXECUTION_PARAMS_KEY]
    if not isinstance(params_source, Mapping):
        return None, "execution_params_invalid"
    try:
        params = deepcopy(dict(params_source))
    except Exception:
        return None, "params_copy_failed"
    return params, None


async def apply_live_producer_node(
    graph: PlanGraph,
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> LiveProducerResult:
    """Drive one live producer step: resolve -> dispatch -> delegate-apply.

    Side-effect-free admissibility + tool-name resolution + param copy precede the
    only live side effect (``dispatch``). A returned ``{"success": False}`` is a real
    raw result (flows into ``apply_producer_result``); only the callable *raising*
    is ``dispatch_failed``. Post-dispatch application is delegated to the pure
    runner, which stays authoritative. Every not-applied path returns the input
    graph unchanged.
    """
    reason = _check_admissibility(graph, node_id)
    if reason is not None:
        return _not_applied(graph, node_id, None, reason)

    node = graph.nodes[node_id]

    tool_name, reason = _resolve_tool_name(node.execution_ref)
    if reason is not None:
        return _not_applied(graph, node_id, None, reason)

    denial = deny_if_contained(tool_name, DispatchOrigin.PLAN_GRAPH)
    if denial is not None:
        return _not_applied(
            graph,
            node_id,
            tool_name,
            "tool_lifecycle_denied",
        )

    params, reason = _resolve_params(node)
    if reason is not None:
        return _not_applied(graph, node_id, tool_name, reason)

    try:
        raw = await dispatch(tool_name, params)
    except Exception:
        return _not_applied(graph, node_id, tool_name, "dispatch_failed")

    inner = apply_producer_result(graph, node_id, raw)
    return LiveProducerResult(
        graph=inner.graph,
        applied=inner.applied,
        node_id=node_id,
        tool_name=tool_name,
        outcome_status=inner.outcome_status,
        reason=inner.reason,
    )
