"""LM4A live producer-node dispatch adapter (Stage 5A).

Non-pure agent-layer adapter: resolves ONE PlanGraph ``artifact_producer`` node to
a dispatch call, fires it through an injected dispatch callable, and delegates
application to the pure runner (``apply_producer_result``). It CONSUMES the pure
PlanGraph seams and never alters or grows them.

Boundary invariants:
- Imports only PUBLIC pure symbols (``runnable_nodes``, ``projection_role_for_node``,
  ``apply_producer_result``, types). No private ``_producer_*`` helpers.
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
    runnable_nodes,
)
from rook.learning.plan_graph_projection import (
    OUTCOME_PROJECTION_ROLE_KEY,
    projection_role_for_node,
)
from rook.learning.plan_graph_runner import apply_producer_result


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


# Stub so the test module imports cleanly; fully implemented in Task 3.
async def apply_live_producer_node(
    graph: PlanGraph,
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> LiveProducerResult:
    raise NotImplementedError  # implemented in Task 3
