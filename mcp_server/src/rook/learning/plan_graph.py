from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Literal


NodeStatus = Literal[
    "pending",
    "ready",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "needs_repair",
    "needs_escalation",
    "skipped",
]
OutcomeStatus = Literal[
    "succeeded",
    "failed",
    "blocked",
    "needs_repair",
    "needs_escalation",
    "skipped",
]
GraphStatus = Literal[
    "pending",
    "running",
    "complete",
    "blocked",
    "failed",
    "needs_escalation",
]
EdgeKind = Literal[
    "requires",
    "on_success",
    "on_repair",
    "on_failure",
    "on_escalation",
]


@dataclass
class NodeEvidence:
    tool_status: Literal["success", "failed"] | None = None
    verified: bool | None = None
    receipt: dict[str, Any] | None = None
    repair_anchor: dict[str, Any] | None = None
    message: str | None = None
    error: str | None = None


@dataclass
class RetryState:
    attempts: int = 0
    max_attempts: int = 1
    last_error: str | None = None
    retry_exhausted: bool = False


@dataclass
class PlanGraphNode:
    id: str
    intent: str
    execution_ref: str | None = None
    verifier_ref: str | None = None
    repair_policy_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    status: NodeStatus = "pending"
    evidence: NodeEvidence | None = None
    retry: RetryState = field(default_factory=RetryState)
    is_terminal: bool = False


@dataclass
class PlanGraphEdge:
    source: str
    target: str
    kind: EdgeKind = "requires"


@dataclass
class NodeOutcome:
    status: OutcomeStatus
    evidence: NodeEvidence | None = None
    memory_updates: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status in ("pending", "ready", "running"):
            raise ValueError(f"NodeOutcome status '{self.status}' is not an outcome state.")


@dataclass
class GraphMemory:
    facts: dict[str, Any] = field(default_factory=dict)
    node_summaries: dict[str, str] = field(default_factory=dict)


@dataclass
class PlanGraph:
    nodes: dict[str, PlanGraphNode] = field(default_factory=dict)
    edges: list[PlanGraphEdge] = field(default_factory=list)
    memory: GraphMemory = field(default_factory=GraphMemory)


def _root_ids(graph: PlanGraph) -> set[str]:
    targeted = {edge.target for edge in graph.edges}
    return set(graph.nodes) - targeted


def initialize_graph(graph: PlanGraph) -> PlanGraph:
    next_graph = copy.deepcopy(graph)
    for node_id in _root_ids(next_graph):
        node = next_graph.nodes[node_id]
        if node.status == "pending":
            node.status = "ready"
    return next_graph


def runnable_nodes(graph: PlanGraph) -> list[PlanGraphNode]:
    return [node for node in graph.nodes.values() if node.status == "ready"]


def graph_status(graph: PlanGraph) -> GraphStatus:
    if any(node.status == "needs_escalation" for node in graph.nodes.values()):
        return "needs_escalation"
    if runnable_nodes(graph) or any(node.status == "running" for node in graph.nodes.values()):
        return "running"
    terminal_nodes = [node for node in graph.nodes.values() if node.is_terminal]
    if terminal_nodes and all(
        node.status in ("succeeded", "skipped") for node in terminal_nodes
    ):
        return "complete"
    has_activity = any(
        node.retry.attempts > 0 or node.evidence is not None
        for node in graph.nodes.values()
    )
    has_roots = bool(_root_ids(graph))
    if not has_activity and has_roots and any(
        node.status in ("pending", "ready") for node in graph.nodes.values()
    ):
        return "pending"
    if any(node.status == "failed" for node in graph.nodes.values()):
        return "failed"
    return "blocked"


def apply_outcome(graph: PlanGraph, node_id: str, outcome: NodeOutcome) -> PlanGraph:
    raise NotImplementedError("apply_outcome is implemented in the reducer task")
