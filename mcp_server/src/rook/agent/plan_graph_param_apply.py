"""LM4L memory-backed execution-param applier (agent layer).

First real consumer of LM4K's pure bind_params_from_memory: it sources a node's
producer params from the runtime graph.memory.facts substrate (via the learning helper)
and STAGES them onto one explicitly-named node's metadata["execution_params"].

Copy-on-write: on success it returns a NEW graph (the input is untouched); on every
failure it returns the input graph unchanged (result.graph is graph). It does NOT
dispatch, does NOT select a node, does NOT advance the chain -- readiness, projection
role, execution-ref resolution, and param dispatchability remain run_live_producer_node's
concern.

Boundary: agent -> learning, one way. Imports bind_params_from_memory / ParamBindingResult
from learning and EXECUTION_PARAMS_KEY from plan_graph_live (single source, NOT redefined).
NO dispatcher/server/base_agent import; the applier needs no RookAgent instance state, so
there is no RookAgent method. learning/* never imports this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph_param_binding import (
    ParamBindingResult,
    bind_params_from_memory,
)

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


ApplyReason = Literal["unknown_node", "binding_failed", "graph_copy_failed"]


@dataclass(frozen=True)
class MemoryParamApplyResult:
    graph: "PlanGraph"
    applied: bool
    node_id: str
    binding: ParamBindingResult | None
    reason: ApplyReason | None


def apply_memory_bound_params(
    graph: "PlanGraph",
    node_id: str,
    base_params: "Mapping",
    bindings: "Mapping[str, tuple[str, ...]]",
) -> MemoryParamApplyResult:
    """Stage memory-sourced params onto ONE named node's execution_params.

    Copy-on-write: returns a NEW graph with ``node.metadata[EXECUTION_PARAMS_KEY]`` set on
    success; returns the INPUT graph unchanged on every failure (``result.graph is graph``).
    Binds against the ORIGINAL ``graph.memory.facts`` (pure), THEN copies, THEN stages --
    never the reverse. Checks ONLY node existence, binding success, and copy success;
    leaves status / role / ref / dispatchability to ``run_live_producer_node``.
    """
    if node_id not in graph.nodes:
        return MemoryParamApplyResult(
            graph=graph,
            applied=False,
            node_id=node_id,
            binding=None,
            reason="unknown_node",
        )

    binding = bind_params_from_memory(base_params, graph, bindings)
    if binding.findings:
        return MemoryParamApplyResult(
            graph=graph,
            applied=False,
            node_id=node_id,
            binding=binding,
            reason="binding_failed",
        )

    try:
        new_graph = deepcopy(graph)
    except Exception:
        return MemoryParamApplyResult(
            graph=graph,
            applied=False,
            node_id=node_id,
            binding=binding,
            reason="graph_copy_failed",
        )

    # binding.params is a fresh deep-copied dict (LM4K), so assigning it directly creates
    # no aliasing into the caller's graph or into new_graph.memory.
    new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = binding.params
    return MemoryParamApplyResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        binding=binding,
        reason=None,
    )
