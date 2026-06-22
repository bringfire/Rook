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
    return [
        copy.deepcopy(node) for node in graph.nodes.values() if node.status == "ready"
    ]


def graph_status(graph: PlanGraph) -> GraphStatus:
    nodes = list(graph.nodes.values())
    if any(node.status == "needs_escalation" for node in nodes):
        return "needs_escalation"
    terminal_nodes = [node for node in nodes if node.is_terminal]
    if terminal_nodes and all(
        node.status in ("succeeded", "skipped") for node in terminal_nodes
    ):
        return "complete"
    if runnable_nodes(graph) or any(node.status == "running" for node in nodes):
        return "running"
    has_activity = any(
        node.retry.attempts > 0 or node.evidence is not None
        for node in nodes
    )
    has_roots = bool(_root_ids(graph))
    if not has_activity and has_roots and any(
        node.status in ("pending", "ready") for node in nodes
    ):
        return "pending"
    if any(node.status == "failed" for node in nodes):
        return "failed"
    if any(node.status in ("blocked", "pending", "needs_repair") for node in nodes):
        return "blocked"
    # Catch-all fallback (load-bearing, not redundant with the check above):
    # reached by residual states none of the named branches cover -- an empty
    # graph, or a graph whose nodes are all succeeded/skipped but none is declared
    # terminal (so "complete" cannot fire and nothing is blocked/pending/
    # needs_repair). Without this line graph_status would fall through and return
    # None, which is not a valid GraphStatus.
    return "blocked"


def _validate_edge_endpoints(graph: PlanGraph) -> None:
    for edge in graph.edges:
        if edge.source not in graph.nodes:
            raise ValueError(f"PlanGraph edge has unknown source node: {edge.source}")
        if edge.target not in graph.nodes:
            raise ValueError(f"PlanGraph edge has unknown target node: {edge.target}")


def _edge_matches(edge: PlanGraphEdge, source_status: NodeStatus) -> bool:
    if edge.kind == "requires":
        return source_status == "succeeded"
    if edge.kind == "on_success":
        return source_status == "succeeded"
    if edge.kind == "on_repair":
        return source_status == "needs_repair"
    if edge.kind == "on_failure":
        return source_status in ("failed", "blocked")
    if edge.kind == "on_escalation":
        return source_status == "needs_escalation"
    return False


def _requires_satisfied(graph: PlanGraph, target_id: str) -> bool:
    for edge in graph.edges:
        if edge.target == target_id and edge.kind == "requires":
            if graph.nodes[edge.source].status != "succeeded":
                return False
    return True


def _merge_memory(graph: PlanGraph, node_id: str, memory_updates: dict[str, Any]) -> None:
    facts = memory_updates.get("facts")
    if isinstance(facts, dict):
        graph.memory.facts.update(copy.deepcopy(facts))
    node_summary = memory_updates.get("node_summary")
    if isinstance(node_summary, str):
        graph.memory.node_summaries[node_id] = node_summary


def apply_outcome(graph: PlanGraph, node_id: str, outcome: NodeOutcome) -> PlanGraph:
    next_graph = copy.deepcopy(graph)
    if node_id not in next_graph.nodes:
        raise ValueError(f"Unknown PlanGraph node: {node_id}")
    _validate_edge_endpoints(next_graph)

    outcome_copy = copy.deepcopy(outcome)
    node = next_graph.nodes[node_id]
    node.status = outcome_copy.status
    node.evidence = outcome_copy.evidence
    node.retry.attempts += 1
    node.retry.last_error = outcome_copy.error
    if node.retry.last_error is None and outcome_copy.evidence is not None:
        node.retry.last_error = outcome_copy.evidence.error
    node.retry.retry_exhausted = node.retry.attempts >= node.retry.max_attempts

    _merge_memory(next_graph, node_id, outcome_copy.memory_updates)

    for edge in next_graph.edges:
        if edge.source != node_id:
            continue
        target = next_graph.nodes[edge.target]
        if (
            target.status == "pending"
            and _edge_matches(edge, node.status)
            and _requires_satisfied(next_graph, edge.target)
        ):
            target.status = "ready"

    return next_graph
