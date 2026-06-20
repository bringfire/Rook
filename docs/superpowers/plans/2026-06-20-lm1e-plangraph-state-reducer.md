# LM1E PlanGraph State Reducer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure, non-live PlanGraph state reducer skeleton that carries node intent, opaque contract refs, evidence, repair anchors, retry state, escalation state, and graph-local memory without executing tools or planning.

**Architecture:** Create `rook.learning.plan_graph` as an import-light dataclass module with copied-graph reducer helpers. Tests construct graphs manually and feed explicit `NodeOutcome` objects, including a GH script repair fixture that carries LM1D-style receipts as opaque evidence.

**Tech Stack:** Python 3, dataclasses, `typing.Literal`, `copy.deepcopy`, pytest.

---

## Scope Guardrails

This plan implements only the approved LM1E spec:

- No tool execution.
- No model calls.
- No planner calls.
- No `ExecutionPlan` coupling.
- No `agent.planner.Plan` / `TaskSpec` imports.
- No ChatRunner changes.
- No ToolDispatcher changes.
- No server/MCP wire changes.
- No capability registry, provider profile, model profile, or LM2 work.
- No workflow tools or GH-specific production builders.
- No KG writes.
- No conversation history integration.
- No prompt injection or scheduled knowledge push.
- No live Rhino/GH dependency.
- No dynamic edge predicates or expression evaluation.

If implementation pressure points toward any of those, stop and ask for review.

---

## File Structure

- Create `mcp_server/src/rook/learning/plan_graph.py`
  - Owns `PlanGraph`, `PlanGraphNode`, `PlanGraphEdge`, `NodeOutcome`,
    `NodeEvidence`, `RetryState`, `GraphMemory`.
  - Owns constrained string literal aliases for node, outcome, edge, and graph
    statuses.
  - Owns pure reducer helpers:
    `initialize_graph`, `apply_outcome`, `runnable_nodes`, `graph_status`.
  - Imports only `copy`, `dataclasses`, and `typing`.
  - Has no imports from server, ChatRunner, dispatcher, planner, executor,
    registry, Rhino/GH, or KG modules.

- Create `mcp_server/tests/test_plan_graph.py`
  - Pure non-live unit tests.
  - Builds all graphs manually.
  - Contains the GH repair acceptance fixture only in test code.

---

## Task 1: Add Failing Data Model And Initialization Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Write initial failing tests**

Create `mcp_server/tests/test_plan_graph.py` with this content:

```python
from __future__ import annotations

import copy

import pytest

from rook.learning.plan_graph import (
    GraphMemory,
    NodeEvidence,
    NodeOutcome,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    RetryState,
    apply_outcome,
    graph_status,
    initialize_graph,
    runnable_nodes,
)


def test_initialize_graph_marks_root_nodes_ready_without_mutating_original():
    graph = PlanGraph(
        nodes={
            "root": PlanGraphNode(id="root", intent="Root node"),
            "child": PlanGraphNode(id="child", intent="Child node"),
        },
        edges=[PlanGraphEdge(source="root", target="child", kind="requires")],
    )

    initialized = initialize_graph(graph)

    assert graph.nodes["root"].status == "pending"
    assert graph.nodes["child"].status == "pending"
    assert initialized.nodes["root"].status == "ready"
    assert initialized.nodes["child"].status == "pending"


def test_initialize_graph_marks_all_roots_ready():
    graph = PlanGraph(
        nodes={
            "a": PlanGraphNode(id="a", intent="Root A"),
            "b": PlanGraphNode(id="b", intent="Root B"),
            "c": PlanGraphNode(id="c", intent="Child C"),
        },
        edges=[PlanGraphEdge(source="a", target="c", kind="requires")],
    )

    initialized = initialize_graph(graph)

    assert {node.id for node in runnable_nodes(initialized)} == {"a", "b"}
    assert initialized.nodes["c"].status == "pending"


def test_runnable_nodes_is_read_only():
    graph = initialize_graph(PlanGraph(
        nodes={"root": PlanGraphNode(id="root", intent="Root node")},
    ))
    before = copy.deepcopy(graph)

    first = runnable_nodes(graph)
    second = runnable_nodes(graph)

    assert [node.id for node in first] == ["root"]
    assert [node.id for node in second] == ["root"]
    assert graph == before


def test_graph_with_cycle_and_no_roots_initializes_blocked_not_pending():
    graph = PlanGraph(
        nodes={
            "a": PlanGraphNode(id="a", intent="A"),
            "b": PlanGraphNode(id="b", intent="B"),
        },
        edges=[
            PlanGraphEdge(source="a", target="b", kind="requires"),
            PlanGraphEdge(source="b", target="a", kind="requires"),
        ],
    )

    initialized = initialize_graph(graph)

    assert runnable_nodes(initialized) == []
    assert graph_status(initialized) == "blocked"


def test_default_factories_do_not_share_mutable_state():
    first = PlanGraphNode(id="first", intent="First")
    second = PlanGraphNode(id="second", intent="Second")
    first.metadata["x"] = {"nested": 1}
    first.retry.attempts = 1

    assert second.metadata == {}
    assert second.retry.attempts == 0

    graph_a = PlanGraph()
    graph_b = PlanGraph()
    graph_a.memory.facts["component_guid"] = "abc"

    assert graph_b.memory.facts == {}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rook.learning.plan_graph'`.

Do not commit yet. These tests are intentionally red until Task 2.

---

## Task 2: Implement Data Model And Initialization

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph.py`
- Test: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Add the `plan_graph.py` module**

Create `mcp_server/src/rook/learning/plan_graph.py` with this content:

```python
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
```

- [ ] **Step 2: Add a temporary partial `graph_status`**

Append this to `plan_graph.py` so Task 1 cycle tests can pass. Later tasks will
complete the status derivation:

```python
def graph_status(graph: PlanGraph) -> GraphStatus:
    if any(node.status == "needs_escalation" for node in graph.nodes.values()):
        return "needs_escalation"
    if runnable_nodes(graph) or any(node.status == "running" for node in graph.nodes.values()):
        return "running"
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
```

- [ ] **Step 3: Add temporary `apply_outcome` guard**

Append this to `plan_graph.py`; later tasks will replace it:

```python
def apply_outcome(graph: PlanGraph, node_id: str, outcome: NodeOutcome) -> PlanGraph:
    raise NotImplementedError("apply_outcome is implemented in the reducer task")
```

- [ ] **Step 4: Run Task 1 tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: PASS for the initial tests.

- [ ] **Step 5: Run import-boundary check**

Run:

```powershell
rg -n "server|chat_runner|tool_dispatcher|agent\.planner|ExecutionPlan|call_rhino|knowledge" mcp_server/src/rook/learning/plan_graph.py
```

Expected: no matches.

- [ ] **Step 6: Commit data model and initialization**

Run:

```powershell
git add mcp_server/src/rook/learning/plan_graph.py mcp_server/tests/test_plan_graph.py
git commit -m "feat: add PlanGraph state model"
```

---

## Task 3: Add Reducer And Edge Unlock Tests

**Files:**
- Modify: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Add reducer tests**

Append these tests to `mcp_server/tests/test_plan_graph.py`:

```python
def test_apply_outcome_updates_node_evidence_retry_and_unlocked_requires_target():
    graph = initialize_graph(PlanGraph(
        nodes={
            "create": PlanGraphNode(id="create", intent="Create"),
            "verify": PlanGraphNode(id="verify", intent="Verify"),
        },
        edges=[PlanGraphEdge(source="create", target="verify", kind="requires")],
    ))
    evidence = NodeEvidence(
        tool_status="success",
        verified=True,
        receipt={"version": 1, "artifact_status": "usable"},
        repair_anchor={"component_guid": "abc"},
    )

    updated = apply_outcome(
        graph,
        "create",
        NodeOutcome(
            status="succeeded",
            evidence=evidence,
            memory_updates={
                "facts": {"component_guid": "abc"},
                "node_summary": "created component abc",
            },
        ),
    )

    assert graph.nodes["create"].status == "ready"
    assert graph.nodes["verify"].status == "pending"
    assert updated.nodes["create"].status == "succeeded"
    assert updated.nodes["create"].evidence == evidence
    assert updated.nodes["create"].retry.attempts == 1
    assert updated.nodes["create"].retry.retry_exhausted is True
    assert updated.nodes["verify"].status == "ready"
    assert updated.memory.facts["component_guid"] == "abc"
    assert updated.memory.node_summaries["create"] == "created component abc"


def test_apply_outcome_deep_copies_evidence_and_memory_updates():
    graph = initialize_graph(PlanGraph(
        nodes={
            "create": PlanGraphNode(
                id="create",
                intent="Create",
                metadata={"pins_out": [{"name": "B"}]},
            ),
        },
    ))
    outcome = NodeOutcome(
        status="needs_repair",
        evidence=NodeEvidence(
            receipt={"script_receipt": {"artifact_status": "created_with_errors"}},
            repair_anchor={"pins_out": [{"name": "B"}]},
        ),
        memory_updates={
            "facts": {"repair_anchor": {"component_guid": "abc"}},
            "node_summary": "needs repair",
        },
    )

    updated = apply_outcome(graph, "create", outcome)
    outcome.evidence.receipt["script_receipt"]["artifact_status"] = "mutated"
    outcome.evidence.repair_anchor["pins_out"][0]["name"] = "Mutated"
    outcome.memory_updates["facts"]["repair_anchor"]["component_guid"] = "mutated"
    graph.nodes["create"].metadata["pins_out"][0]["name"] = "MutatedGraph"

    assert updated.nodes["create"].evidence.receipt["script_receipt"]["artifact_status"] == "created_with_errors"
    assert updated.nodes["create"].evidence.repair_anchor["pins_out"][0]["name"] == "B"
    assert updated.memory.facts["repair_anchor"]["component_guid"] == "abc"
    assert updated.nodes["create"].metadata["pins_out"][0]["name"] == "B"


def test_apply_outcome_raises_for_unknown_node_id():
    graph = PlanGraph(nodes={"known": PlanGraphNode(id="known", intent="Known")})

    with pytest.raises(ValueError, match="Unknown PlanGraph node"):
        apply_outcome(graph, "missing", NodeOutcome(status="succeeded"))


def test_apply_outcome_raises_for_unknown_edge_endpoint():
    graph = initialize_graph(PlanGraph(
        nodes={"source": PlanGraphNode(id="source", intent="Source")},
        edges=[PlanGraphEdge(source="source", target="missing", kind="requires")],
    ))

    with pytest.raises(ValueError, match="unknown target"):
        apply_outcome(graph, "source", NodeOutcome(status="succeeded"))


@pytest.mark.parametrize(
    "edge_kind,outcome_status,unlocks",
    [
        ("on_success", "succeeded", True),
        ("on_repair", "needs_repair", True),
        ("on_failure", "failed", True),
        ("on_failure", "blocked", True),
        ("on_escalation", "needs_escalation", True),
        ("on_repair", "failed", False),
        ("on_success", "needs_repair", False),
        ("on_escalation", "failed", False),
    ],
)
def test_transition_edges_unlock_only_for_matching_outcomes(edge_kind, outcome_status, unlocks):
    graph = initialize_graph(PlanGraph(
        nodes={
            "source": PlanGraphNode(id="source", intent="Source"),
            "target": PlanGraphNode(id="target", intent="Target"),
        },
        edges=[PlanGraphEdge(source="source", target="target", kind=edge_kind)],
    ))

    updated = apply_outcome(graph, "source", NodeOutcome(status=outcome_status))

    assert updated.nodes["target"].status == ("ready" if unlocks else "pending")


def test_unlock_waits_for_all_requires_dependencies():
    graph = initialize_graph(PlanGraph(
        nodes={
            "a": PlanGraphNode(id="a", intent="A"),
            "b": PlanGraphNode(id="b", intent="B"),
            "target": PlanGraphNode(id="target", intent="Target"),
        },
        edges=[
            PlanGraphEdge(source="a", target="target", kind="requires"),
            PlanGraphEdge(source="b", target="target", kind="requires"),
        ],
    ))

    after_a = apply_outcome(graph, "a", NodeOutcome(status="succeeded"))
    after_b = apply_outcome(after_a, "b", NodeOutcome(status="succeeded"))

    assert after_a.nodes["target"].status == "pending"
    assert after_b.nodes["target"].status == "ready"


def test_unlock_does_not_change_non_pending_target():
    graph = initialize_graph(PlanGraph(
        nodes={
            "source": PlanGraphNode(id="source", intent="Source"),
            "target": PlanGraphNode(id="target", intent="Target", status="blocked"),
        },
        edges=[PlanGraphEdge(source="source", target="target", kind="requires")],
    ))

    updated = apply_outcome(graph, "source", NodeOutcome(status="succeeded"))

    assert updated.nodes["target"].status == "blocked"
```

- [ ] **Step 2: Run reducer tests and verify they fail**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: FAIL because `apply_outcome` still raises `NotImplementedError`.

Do not commit yet.

---

## Task 4: Implement Reducer And Edge Unlocking

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph.py`
- Test: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Replace `apply_outcome` and add helper functions**

Replace the temporary `apply_outcome` in
`mcp_server/src/rook/learning/plan_graph.py` with this code:

```python
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
```

- [ ] **Step 2: Run reducer tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: PASS for Task 1-4 tests.

- [ ] **Step 3: Run py_compile and import-boundary check**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/learning/plan_graph.py
rg -n "server|chat_runner|tool_dispatcher|agent\.planner|ExecutionPlan|call_rhino|knowledge" mcp_server/src/rook/learning/plan_graph.py
```

Expected:

- `py_compile`: no output, exit code 0.
- `rg`: no matches.

- [ ] **Step 4: Commit reducer implementation**

Run:

```powershell
git add mcp_server/src/rook/learning/plan_graph.py mcp_server/tests/test_plan_graph.py
git commit -m "feat: add PlanGraph reducer"
```

---

## Task 5: Add Graph Status And Memory Behavior Tests

**Files:**
- Modify: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Add status and memory tests**

Append these tests to `mcp_server/tests/test_plan_graph.py`:

```python
def test_retry_exhaustion_does_not_auto_escalate():
    graph = initialize_graph(PlanGraph(
        nodes={
            "node": PlanGraphNode(
                id="node",
                intent="Try once",
                retry=RetryState(max_attempts=1),
            ),
        },
    ))

    updated = apply_outcome(graph, "node", NodeOutcome(status="failed", error="bad input"))

    assert updated.nodes["node"].retry.attempts == 1
    assert updated.nodes["node"].retry.retry_exhausted is True
    assert updated.nodes["node"].retry.last_error == "bad input"
    assert updated.nodes["node"].status == "failed"
    assert graph_status(updated) == "failed"


def test_retry_last_error_falls_back_to_evidence_error():
    graph = initialize_graph(PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node")},
    ))

    updated = apply_outcome(
        graph,
        "node",
        NodeOutcome(status="failed", evidence=NodeEvidence(error="evidence error")),
    )

    assert updated.nodes["node"].retry.last_error == "evidence error"


def test_graph_memory_last_writer_wins_for_facts_and_summary():
    graph = initialize_graph(PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node")},
    ))
    first = apply_outcome(
        graph,
        "node",
        NodeOutcome(
            status="failed",
            memory_updates={
                "facts": {"component_guid": "first"},
                "node_summary": "first summary",
            },
        ),
    )
    second = apply_outcome(
        first,
        "node",
        NodeOutcome(
            status="needs_repair",
            memory_updates={
                "facts": {"component_guid": "second"},
                "node_summary": "second summary",
            },
        ),
    )

    assert second.memory.facts["component_guid"] == "second"
    assert second.memory.node_summaries["node"] == "second summary"


def test_graph_status_pending_running_complete_failed_blocked_and_escalation():
    pending_graph = PlanGraph(nodes={"root": PlanGraphNode(id="root", intent="Root")})
    assert graph_status(pending_graph) == "pending"
    assert graph_status(initialize_graph(pending_graph)) == "running"

    complete_graph = PlanGraph(
        nodes={
            "done": PlanGraphNode(
                id="done",
                intent="Done",
                status="succeeded",
                is_terminal=True,
            ),
        },
    )
    assert graph_status(complete_graph) == "complete"

    skipped_terminal = PlanGraph(
        nodes={
            "done": PlanGraphNode(
                id="done",
                intent="Done",
                status="skipped",
                is_terminal=True,
            ),
        },
    )
    assert graph_status(skipped_terminal) == "complete"

    failed_graph = PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node", status="failed")},
    )
    assert graph_status(failed_graph) == "failed"

    blocked_graph = PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node", status="blocked")},
    )
    assert graph_status(blocked_graph) == "blocked"

    escalation_graph = PlanGraph(
        nodes={
            "node": PlanGraphNode(
                id="node",
                intent="Node",
                status="needs_escalation",
            )
        },
    )
    assert graph_status(escalation_graph) == "needs_escalation"


def test_needs_repair_without_unlocked_repair_edge_is_not_running():
    graph = PlanGraph(
        nodes={"node": PlanGraphNode(id="node", intent="Node", status="needs_repair")},
    )

    assert runnable_nodes(graph) == []
    assert graph_status(graph) == "blocked"


@pytest.mark.parametrize("bad_status", ["pending", "ready", "running"])
def test_node_outcome_rejects_administrative_statuses(bad_status):
    with pytest.raises(ValueError, match="not an outcome state"):
        NodeOutcome(status=bad_status)
```

- [ ] **Step 2: Run tests and verify failures if graph_status is incomplete**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: Some failures are acceptable if Task 2's temporary `graph_status`
does not yet satisfy all status rules.

Do not commit yet if failures occur.

---

## Task 6: Complete Graph Status Behavior

**Files:**
- Modify: `mcp_server/src/rook/learning/plan_graph.py`
- Test: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Replace `graph_status` with full derivation**

Replace `graph_status(...)` in `mcp_server/src/rook/learning/plan_graph.py`
with:

```python
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
    return "blocked"
```

- [ ] **Step 2: Run status tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: PASS for all current `test_plan_graph.py` tests.

- [ ] **Step 3: Commit graph status behavior**

Run:

```powershell
git add mcp_server/src/rook/learning/plan_graph.py mcp_server/tests/test_plan_graph.py
git commit -m "feat: add PlanGraph status derivation"
```

---

## Task 7: Add GH Repair Fixture Acceptance Test

**Files:**
- Modify: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Add the test-only GH repair fixture**

Append this fixture and test to `mcp_server/tests/test_plan_graph.py`:

```python
def _gh_script_repair_fixture() -> PlanGraph:
    return PlanGraph(
        nodes={
            "create_script": PlanGraphNode(
                id="create_script",
                intent="Create a script component",
                execution_ref="gh_create_csharp_script:v1",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
                repair_policy_ref="repair_same_component_once:v1",
                metadata={"contract": "gh_csharp_body_script_v1"},
            ),
            "verify_receipt": PlanGraphNode(
                id="verify_receipt",
                intent="Verify script receipt",
                verifier_ref="script_receipt_has_artifact_or_errors:v1",
            ),
            "repair_same_component": PlanGraphNode(
                id="repair_same_component",
                intent="Repair same component",
                execution_ref="gh_update_script:v1",
                repair_policy_ref="repair_same_component_once:v1",
            ),
            "verify_clean": PlanGraphNode(
                id="verify_clean",
                intent="Verify repaired component",
                verifier_ref="script_receipt_has_clean_artifact:v1",
            ),
            "done": PlanGraphNode(
                id="done",
                intent="Report verified script component",
                is_terminal=True,
            ),
        },
        edges=[
            PlanGraphEdge(source="create_script", target="verify_receipt", kind="requires"),
            PlanGraphEdge(source="verify_receipt", target="repair_same_component", kind="on_repair"),
            PlanGraphEdge(source="repair_same_component", target="verify_clean", kind="requires"),
            PlanGraphEdge(source="verify_clean", target="done", kind="requires"),
            PlanGraphEdge(source="verify_receipt", target="done", kind="on_success"),
        ],
    )


def test_gh_script_repair_fixture_carries_receipt_and_repair_anchor_through_graph():
    graph = initialize_graph(_gh_script_repair_fixture())
    assert [node.id for node in runnable_nodes(graph)] == ["create_script"]

    receipt = {
        "version": 1,
        "operation": "create",
        "artifact_status": "created_with_errors",
        "repair_anchor": {"component_guid": "component-guid"},
    }
    repair_anchor = {
        "component_guid": "component-guid",
        "pins_out": [{"name": "B", "type": "Brep"}],
        "target_errors": ["Cannot convert Box to Brep"],
    }
    graph = apply_outcome(
        graph,
        "create_script",
        NodeOutcome(
            status="succeeded",
            evidence=NodeEvidence(
                tool_status="failed",
                verified=False,
                receipt=receipt,
                repair_anchor=repair_anchor,
                message="created with compile errors",
            ),
            memory_updates={
                "facts": {
                    "component_guid": "component-guid",
                    "repair_anchor": repair_anchor,
                },
                "node_summary": "component created with compile errors",
            },
        ),
    )

    assert [node.id for node in runnable_nodes(graph)] == ["verify_receipt"]
    assert graph.memory.facts["component_guid"] == "component-guid"
    assert graph.memory.facts["repair_anchor"]["pins_out"][0]["name"] == "B"

    graph = apply_outcome(
        graph,
        "verify_receipt",
        NodeOutcome(
            status="needs_repair",
            evidence=NodeEvidence(
                receipt=receipt,
                repair_anchor=repair_anchor,
                error="target compile errors remain",
            ),
            memory_updates={"node_summary": "repair required"},
        ),
    )

    assert [node.id for node in runnable_nodes(graph)] == ["repair_same_component"]
    assert graph.nodes["verify_receipt"].evidence.repair_anchor["component_guid"] == "component-guid"

    graph = apply_outcome(
        graph,
        "repair_same_component",
        NodeOutcome(
            status="succeeded",
            evidence=NodeEvidence(tool_status="success", message="updated source"),
            memory_updates={"node_summary": "repair written"},
        ),
    )
    assert [node.id for node in runnable_nodes(graph)] == ["verify_clean"]

    graph = apply_outcome(
        graph,
        "verify_clean",
        NodeOutcome(
            status="succeeded",
            evidence=NodeEvidence(verified=True, message="clean receipt"),
            memory_updates={"node_summary": "verified clean"},
        ),
    )
    assert [node.id for node in runnable_nodes(graph)] == ["done"]

    graph = apply_outcome(
        graph,
        "done",
        NodeOutcome(status="succeeded", memory_updates={"node_summary": "done"}),
    )

    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Run PlanGraph tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: PASS.

- [ ] **Step 3: Verify no GH-specific production helper exists**

Run:

```powershell
rg -n "gh_|grasshopper|script|repair_same_component|create_script|verify_receipt|build_gh" mcp_server/src/rook/learning/plan_graph.py
```

Expected: no matches.

- [ ] **Step 4: Commit acceptance fixture**

Run:

```powershell
git add mcp_server/tests/test_plan_graph.py
git commit -m "test: cover PlanGraph repair fixture"
```

---

## Task 8: Final Verification And Hygiene

**Files:**
- Verify: `mcp_server/src/rook/learning/plan_graph.py`
- Verify: `mcp_server/tests/test_plan_graph.py`

- [ ] **Step 1: Run focused tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph.py -q
```

Expected: PASS.

- [ ] **Step 2: Run compile check**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/learning/plan_graph.py
```

Expected: no output and exit code `0`.

- [ ] **Step 3: Run import-boundary checks**

Run:

```powershell
rg -n "server|chat_runner|tool_dispatcher|agent\.planner|ExecutionPlan|call_rhino|knowledge" mcp_server/src/rook/learning/plan_graph.py
rg -n "gh_|grasshopper|script|repair_same_component|create_script|verify_receipt|build_gh" mcp_server/src/rook/learning/plan_graph.py
```

Expected: no matches from either command.

- [ ] **Step 4: Run diff hygiene**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected:

- `git diff --check` exits `0`.
- `git status --short --branch` shows only the LM1E branch and no unstaged
  runtime artifacts.

- [ ] **Step 5: Commit final fixes if any were needed**

If Task 8 required code/test fixes, commit only those fixes:

```powershell
git add mcp_server/src/rook/learning/plan_graph.py mcp_server/tests/test_plan_graph.py
git commit -m "test: verify LM1E PlanGraph reducer"
```

If no fixes were needed and the working tree is clean, do not create an empty
commit.

---

## Review Checkpoints

Use review checkpoints after:

- Task 2: data model and initialization are green.
- Task 4: reducer and edge unlocking are green.
- Task 7: GH repair fixture acceptance test is green.
- Task 8: final focused verification and hygiene are complete.

At each checkpoint, confirm:

- `plan_graph.py` imports only allowed modules.
- No ChatRunner, dispatcher, server, planner, executor, registry, KG, Rhino, or
  GH imports.
- No public GH repair graph builder exists.
- Reducer functions return copied graphs and do not mutate inputs.
- Graph status is derived, not stored.
- Reducer stores evidence and memory but does not inspect receipt semantics.
- Retry exhaustion does not auto-escalate.

---

## Self-Review Notes

Spec coverage:

- Data model: Tasks 1-2.
- Initialization/root behavior and cycle/no-root blocked status: Tasks 1-2.
- Reducer and edge unlock behavior: Tasks 3-4.
- Retry and GraphMemory: Tasks 5-6.
- Derived graph status: Tasks 5-6.
- Test-only GH repair fixture with LM1D receipt/anchor: Task 7.
- Import/scope boundaries: Tasks 2, 7, 8.
- No implementation integration with planners/executors/ChatRunner/dispatcher:
  scope guardrails and import checks.

Unresolved-wording scan:

- No task uses unresolved wording.

Type consistency:

- `OutcomeStatus` excludes administrative statuses.
- `NodeStatus` includes all persisted node states.
- `GraphStatus` is only derived by `graph_status`.
- Edge kinds match the spec exactly.
