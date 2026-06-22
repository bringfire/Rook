"""LM3A PlanGraph replay/walker (non-live drive scaffold).

A single pure function that replays an explicit, caller-supplied ordered list of
``(node_id, raw_result)`` steps against a ``PlanGraph``, advancing it through the
LM1G bridge (``apply_tool_result``) and LM1E reducer, and returning a diagnostic
``WalkReport``.

It is not a scheduler: it never selects a node, calls a tool or model, resolves
profiles/capabilities, inspects ``script_receipt`` internals, or invents
retry/escalation policy. The caller dictates the exact step sequence. Readiness is
read only via ``runnable_nodes``; transitions go only through ``apply_tool_result``.
"""

import copy
from dataclasses import dataclass
from typing import Any

from rook.learning.plan_graph import (
    GraphStatus,
    NodeStatus,
    PlanGraph,
    PlanGraphNode,
    graph_status,
    initialize_graph,
    runnable_nodes,
)
from rook.learning.plan_graph_bridge import apply_tool_result


_NON_TERMINAL_STATUSES = ("pending", "running")


@dataclass(frozen=True)
class EvidenceSummary:
    """Projection of NodeEvidence TOP-LEVEL fields only (no receipt inspection)."""

    tool_status: str | None
    verified: bool | None
    has_repair_anchor: bool
    message: str | None
    error: str | None


@dataclass(frozen=True)
class WalkStep:
    node_id: str
    applied: bool
    runnable_before: bool
    status_before: NodeStatus | None
    status_after: NodeStatus | None
    graph_status_after: GraphStatus
    memory_facts: dict[str, Any]
    evidence: EvidenceSummary | None
    reason: str | None


@dataclass(frozen=True)
class WalkReport:
    steps: tuple[WalkStep, ...]
    final_graph: PlanGraph
    final_graph_status: GraphStatus
    final_runnable_node_ids: tuple[str, ...]
    final_memory_facts: dict[str, Any]
    nodes_needing_repair: tuple[str, ...]
    nodes_needing_escalation: tuple[str, ...]
    halted: bool
    halt_reason: str | None
    remaining_steps: tuple[tuple[str, Any], ...]


def _evidence_summary(node: PlanGraphNode) -> EvidenceSummary | None:
    evidence = node.evidence
    if evidence is None:
        return None
    return EvidenceSummary(
        tool_status=evidence.tool_status,
        verified=evidence.verified,
        has_repair_anchor=evidence.repair_anchor is not None,
        message=evidence.message,
        error=evidence.error,
    )


def _ids_by_status(graph: PlanGraph, status: NodeStatus) -> tuple[str, ...]:
    return tuple(
        sorted(
            node_id
            for node_id, node in graph.nodes.items()
            if node.status == status
        )
    )


def _report(
    graph: PlanGraph,
    steps: list[WalkStep],
    *,
    halted: bool,
    halt_reason: str | None,
    remaining: tuple[tuple[str, Any], ...],
) -> WalkReport:
    return WalkReport(
        steps=tuple(steps),
        final_graph=graph,
        final_graph_status=graph_status(graph),
        final_runnable_node_ids=tuple(
            sorted(node.id for node in runnable_nodes(graph))
        ),
        final_memory_facts=copy.deepcopy(graph.memory.facts),
        nodes_needing_repair=_ids_by_status(graph, "needs_repair"),
        nodes_needing_escalation=_ids_by_status(graph, "needs_escalation"),
        halted=halted,
        halt_reason=halt_reason,
        remaining_steps=remaining,
    )


def _is_halt_status(gstatus: GraphStatus, has_remaining_steps: bool) -> bool:
    """Whether the walk should halt after reaching ``gstatus``.

    Any terminal status halts EXCEPT ``complete`` reached with no steps left:
    a fully-consumed walk ending in ``complete`` is a successful exit, not a
    halt. ``complete`` with steps still queued halts early (and surfaces the
    unprocessed tail). ``failed`` / ``blocked`` / ``needs_escalation`` always
    halt.
    """
    if gstatus == "complete":
        return has_remaining_steps
    return gstatus not in _NON_TERMINAL_STATUSES


def walk_plan_graph(graph: PlanGraph, steps: list[tuple[str, Any]]) -> WalkReport:
    """Replay ``steps`` against ``graph`` and return a diagnostic ``WalkReport``.

    Initializes ``graph`` once (relying on the reducer's copy semantics; the
    caller's graph is never mutated). For each ``(node_id, raw_result)``: if the
    node is not currently runnable, records an invalid step and halts
    (``halt_reason="invalid_step"``); otherwise applies it through the bridge and
    halts if the resulting graph status is terminal
    (``halt_reason="terminal_status"``). ``remaining_steps`` holds the unprocessed
    tail as-is (no copy).
    """
    graph = initialize_graph(graph)
    recorded: list[WalkStep] = []

    for index, (node_id, raw_result) in enumerate(steps):
        runnable_ids = {node.id for node in runnable_nodes(graph)}
        if node_id not in runnable_ids:
            known = node_id in graph.nodes
            status_before = graph.nodes[node_id].status if known else None
            recorded.append(
                WalkStep(
                    node_id=node_id,
                    applied=False,
                    runnable_before=False,
                    status_before=status_before,
                    status_after=status_before,
                    graph_status_after=graph_status(graph),
                    memory_facts=copy.deepcopy(graph.memory.facts),
                    evidence=None,
                    reason="unknown_node" if not known else "node_not_runnable",
                )
            )
            return _report(
                graph,
                recorded,
                halted=True,
                halt_reason="invalid_step",
                remaining=tuple(steps[index + 1 :]),
            )

        status_before = graph.nodes[node_id].status
        graph = apply_tool_result(graph, node_id, raw_result)
        node_after = graph.nodes[node_id]
        gstatus = graph_status(graph)
        recorded.append(
            WalkStep(
                node_id=node_id,
                applied=True,
                runnable_before=True,
                status_before=status_before,
                status_after=node_after.status,
                graph_status_after=gstatus,
                memory_facts=copy.deepcopy(graph.memory.facts),
                evidence=_evidence_summary(node_after),
                reason=None,
            )
        )
        if _is_halt_status(gstatus, index + 1 < len(steps)):
            return _report(
                graph,
                recorded,
                halted=True,
                halt_reason="terminal_status",
                remaining=tuple(steps[index + 1 :]),
            )

    return _report(
        graph, recorded, halted=False, halt_reason=None, remaining=()
    )
