# LM1E: PlanGraph State Reducer Skeleton Design

## Status

Design draft for senior review. This document defines the LM1E slice only. It
must not be treated as approval for LM2 capability registry work, PlanGraph
execution, ChatRunner orchestration, workflow tools, live Rhino/GH execution, or
model-driven planning.

## Context

LM1A made local RookChat-visible tools structurally dispatchable. LM1B added
`ToolResultView` so ChatRunner can classify existing tool results without
changing dispatcher semantics. LM1C added C# script preflight before GH
mutation. LM1D added producer-side GH script receipts and repair anchors after
structured create/update mutations.

The next scaffold gap is not tool truth; it is where local/internal models keep
multi-step task state. Today, Rook has:

- `rook.learning.intent_runtime.ExecutionPlan`: a single typed operation between
  intent planning and execution.
- `rook.learning.plan_validator.ExecutionPlan`: a separate validation shape.
- `rook.agent.planner.Plan` / `TaskSpec`: cloud-style task decomposition with
  dependencies and postconditions.

LM1E must not replace those. It adds a tiny, generic graph-state adapter above
single-operation execution concepts. The purpose is to hold node intent,
contract refs, verifier refs, result evidence, repair anchors, retry state,
escalation state, and graph-local memory so a sparse model does not have to
remember them.

## Goals

- Add a pure, non-live `rook.learning.plan_graph` module.
- Define a small DAG-shaped state model:
  - `PlanGraph`
  - `PlanGraphNode`
  - `PlanGraphEdge`
  - `NodeOutcome`
  - `NodeEvidence`
  - `RetryState`
  - `GraphMemory`
- Add deterministic reducer helpers:
  - `initialize_graph(graph) -> PlanGraph`
  - `apply_outcome(graph, node_id, outcome) -> PlanGraph`
  - `runnable_nodes(graph) -> list[PlanGraphNode]`
  - `graph_status(graph) -> GraphStatus`
- Prove graph mechanics with non-live tests using explicit `NodeOutcome`
  objects.
- Prove an LM1D-style receipt and repair anchor can be carried as opaque
  evidence through a hardcoded test fixture graph.
- Keep the graph reducer stateful but unintelligent: it stores and transitions
  explicit state; it does not choose tools, call tools, inspect receipts, or
  plan repairs.

## Non-Goals

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
- No prompt injection or scheduled knowledge push yet.
- No live Rhino/GH dependency.
- No dynamic edge predicates or expression evaluation.

## Module Boundary

Create:

`mcp_server/src/rook/learning/plan_graph.py`

Tests:

`mcp_server/tests/test_plan_graph.py`

Allowed imports in `plan_graph.py`:

- `copy`
- `dataclasses`
- `typing`

The module must not import:

- `server.py`
- ChatRunner
- ToolDispatcher
- capability or registry modules
- Rhino/GH live tools
- KG write paths
- `rook.agent.planner`
- either existing `ExecutionPlan` class

The production module must not contain GH-specific node names or a
`build_gh_script_repair_graph(...)` helper. The GH repair graph appears only as
a test fixture.

## Core Data Model

### NodeStatus

`NodeStatus` is a constrained string literal:

```python
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
```

Only `initialize_graph(...)` and `apply_outcome(...)` may change node status.
Read-only helpers must not infer or mutate node statuses.

### GraphStatus

`GraphStatus` is derived, never stored:

```python
GraphStatus = Literal[
    "pending",
    "running",
    "complete",
    "blocked",
    "failed",
    "needs_escalation",
]
```

There must be no `PlanGraph.status` field. Graph-level status is derived from
nodes and `runnable_nodes(graph)`.

### PlanGraphNode

```python
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
```

Field meanings:

- `intent`: human/model-readable node purpose.
- `execution_ref`: opaque string naming the expected executable contract.
- `verifier_ref`: opaque string naming the expected evidence/verifier contract.
- `repair_policy_ref`: opaque string naming the surrounding repair policy.
- `metadata`: JSON-ish hints only.
- `is_terminal`: marks nodes that can complete the graph.

The reducer treats `execution_ref`, `verifier_ref`, `repair_policy_ref`, and
`metadata` as opaque. It does not resolve them.

### PlanGraphEdge

```python
EdgeKind = Literal[
    "requires",
    "on_success",
    "on_repair",
    "on_failure",
    "on_escalation",
]

@dataclass
class PlanGraphEdge:
    source: str
    target: str
    kind: EdgeKind = "requires"
```

V0 edge kinds are static transition labels:

- `requires`: target can run after source is `succeeded`.
- `on_success`: target can run after source is `succeeded`.
- `on_repair`: target can run after source is `needs_repair`.
- `on_failure`: target can run after source is `failed` or `blocked`.
- `on_escalation`: target can run after source is `needs_escalation`.

The reducer must not support dynamic predicates or receipt-dependent edge
conditions.

### NodeEvidence

```python
@dataclass
class NodeEvidence:
    tool_status: Literal["success", "failed"] | None = None
    verified: bool | None = None
    receipt: dict[str, Any] | None = None
    repair_anchor: dict[str, Any] | None = None
    message: str | None = None
    error: str | None = None
```

Evidence is schema-light. LM1E may carry LM1D `script_receipt` and
`repair_anchor` dictionaries, but it must not inspect their fields.

### NodeOutcome

```python
@dataclass
class NodeOutcome:
    status: NodeStatus
    evidence: NodeEvidence | None = None
    memory_updates: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    error: str | None = None
```

`NodeOutcome.status` uses the same constrained `NodeStatus` values. It is the
prepared adapter output from a tool/verifier/scaffold layer. The PlanGraph
reducer accepts it; it does not derive it from receipts.

Only outcome application may move a node into terminal, repair, failure, or
escalation states.

### RetryState

```python
@dataclass
class RetryState:
    attempts: int = 0
    max_attempts: int = 1
    last_error: str | None = None
    retry_exhausted: bool = False
```

Reducer rules:

- Applying a `NodeOutcome` increments `attempts`.
- Administrative transitions and read-only queries do not increment attempts.
- `last_error` comes from `NodeOutcome.error` or `NodeEvidence.error`.
- `retry_exhausted = attempts >= max_attempts`.
- Retry exhaustion does not auto-escalate.
- `needs_escalation` only happens when `NodeOutcome.status` explicitly says
  `needs_escalation`.

### GraphMemory

```python
@dataclass
class GraphMemory:
    facts: dict[str, Any] = field(default_factory=dict)
    node_summaries: dict[str, str] = field(default_factory=dict)
```

GraphMemory is graph-local and ephemeral. It is not KG memory and not
conversation history.

`NodeOutcome.memory_updates` may contain:

```python
{
    "facts": {
        "component_guid": "...",
        "repair_anchor": {...},
    },
    "node_summary": "created component with compile errors",
}
```

Reducer rules:

- Merge only explicit `NodeOutcome.memory_updates`.
- Last writer wins for `facts`.
- `node_summaries[node_id]` is replaced by latest explicit summary.
- Do not summarize transcripts.
- Do not inspect receipts to infer facts.
- Do not write to KG.
- Do not integrate with prompt or chat context in V0.

### PlanGraph

```python
@dataclass
class PlanGraph:
    nodes: dict[str, PlanGraphNode] = field(default_factory=dict)
    edges: list[PlanGraphEdge] = field(default_factory=list)
    memory: GraphMemory = field(default_factory=GraphMemory)
```

`PlanGraph` stores node and edge state only. It does not store a graph-level
status.

## Reducer Operations

### initialize_graph

```python
initialize_graph(graph: PlanGraph) -> PlanGraph
```

Rules:

- Returns a deep-copied graph.
- Does not mutate the input graph.
- A root node is any node with no incoming edges.
- Root nodes with status `pending` become `ready`.
- Non-root nodes remain unchanged.
- If the graph has cycles and no roots, initialization does not try to resolve
  the cycle. With no ready nodes, `graph_status(...)` derives to `blocked`.

### runnable_nodes

```python
runnable_nodes(graph: PlanGraph) -> list[PlanGraphNode]
```

Rules:

- Read-only.
- Does not mutate the graph.
- Returns nodes whose current status is `ready`.
- Does not recalculate hidden readiness.
- Calling it repeatedly must leave the graph unchanged.

### apply_outcome

```python
apply_outcome(graph: PlanGraph, node_id: str, outcome: NodeOutcome) -> PlanGraph
```

Rules:

- Returns a deep-copied graph.
- Does not mutate the input graph.
- Copies `NodeOutcome`, `NodeEvidence`, `receipt`, `repair_anchor`, metadata, and
  memory updates so caller-owned dictionaries cannot rewrite graph history.
- Updates the target node:
  - `status = outcome.status`
  - `evidence = outcome.evidence`
  - increment `retry.attempts`
  - update `retry.last_error`
  - update `retry.retry_exhausted`
- Merges explicit `GraphMemory` updates from `outcome.memory_updates`.
- Marks newly unlocked target nodes `ready` only when:
  - the source outcome/status matches the edge kind;
  - all `requires` dependencies for the target are satisfied;
  - the target is currently `pending`.
- Does not call tools, verifiers, models, planners, or registries.
- Does not inspect `receipt`, `repair_anchor`, or metadata.

### graph_status

```python
graph_status(graph: PlanGraph) -> GraphStatus
```

Rules, in precedence order:

1. `needs_escalation` if any node status is `needs_escalation`.
2. `complete` if at least one terminal node exists and all terminal nodes are
   `succeeded` or `skipped`.
3. `running` if `runnable_nodes(graph)` is non-empty or any node is `running`.
4. `pending` if no node has attempts/evidence and at least one node is
   `pending` or `ready`.
5. `failed` if no runnable nodes remain and any node is `failed`.
6. `blocked` if no runnable nodes remain and any node is `blocked` or still
   `pending`.

`needs_repair` means progress only when an `on_repair` edge has unlocked a
ready node. `graph_status(...)` must use `runnable_nodes(...)` rather than
guessing from `needs_repair` alone.

## Edge Unlock Examples

### Linear Success

```text
create --requires--> verify
verify --requires--> done
```

After `create` receives `NodeOutcome(status="succeeded")`, `verify` becomes
`ready` if all its `requires` dependencies are satisfied.

### Repair Branch

```text
create_script --requires--> verify_receipt
verify_receipt --on_repair--> repair_same_component
repair_same_component --requires--> verify_clean
verify_clean --requires--> done
verify_receipt --on_success--> done
```

If `verify_receipt` receives `NodeOutcome(status="needs_repair")`,
`repair_same_component` becomes `ready`. The reducer does not know that the node
repairs a script; it only applies the `on_repair` transition.

### Retry Exhaustion Without Escalation

For a node with `max_attempts=1`, applying `NodeOutcome(status="failed")`
produces:

```python
node.retry.attempts == 1
node.retry.retry_exhausted is True
node.status == "failed"
```

The node does not become `needs_escalation` unless the outcome explicitly says
`needs_escalation`.

## Test Strategy

Add `mcp_server/tests/test_plan_graph.py`.

Required non-live tests:

- `initialize_graph` marks root nodes `ready`.
- `initialize_graph` does not mutate the original graph.
- `runnable_nodes` returns ready nodes and is read-only.
- Calling `runnable_nodes` twice leaves graph state unchanged.
- `apply_outcome` does not mutate the original graph.
- Mutating outcome evidence after `apply_outcome` does not alter stored graph
  evidence.
- Deep-copy protection covers:
  - `NodeEvidence.receipt`
  - `NodeEvidence.repair_anchor`
  - node `metadata`
  - `GraphMemory.facts`
  - `NodeOutcome.memory_updates`
- `requires` unlocks a pending target after source success.
- `on_repair` unlocks a repair target after `needs_repair`.
- `on_failure` and `on_escalation` unlock only for matching statuses.
- Edge unlock does not mark a target `ready` if its other `requires`
  dependencies are not satisfied.
- Edge unlock does not change a target that is not `pending`.
- Retry exhaustion sets `retry_exhausted` but does not auto-escalate.
- `GraphMemory` merges explicit facts and node summaries; last writer wins.
- `graph_status` derives:
  - `pending`
  - `running`
  - `complete`
  - `blocked`
  - `failed`
  - `needs_escalation`
- A graph with a cycle and no roots initializes without ready nodes and derives
  to `blocked`.
- A test-only GH script repair fixture carries an LM1D-style `script_receipt`
  and `repair_anchor` through:

```text
create_script -> verify_receipt
verify_receipt --on_repair--> repair_same_component
repair_same_component -> verify_clean
verify_clean -> done
```

The fixture must construct generic nodes manually. Production code must not
contain GH-specific builders or names.

## Acceptance Criteria

- `rook.learning.plan_graph` exists and is pure/non-live.
- The module exposes only generic graph primitives and reducer helpers.
- It imports no ChatRunner, dispatcher, server, planner, executor, registry,
  KG writer, Rhino, or GH modules.
- Reducers return copied graphs and do not mutate inputs.
- Read-only helpers do not mutate state.
- Node outcomes carry evidence, receipts, repair anchors, retry state, and
  graph-local memory without receipt interpretation.
- Graph status is derived, not stored.
- Root and edge-unlock behavior is deterministic and covered by tests.
- Retry exhaustion is recorded but does not auto-escalate.
- Cycle behavior is deterministic for V0: no roots means no initialization
  readiness; graph status derives to `blocked`.
- No public GH script repair graph builder is added.

## Future Work

Future slices may add:

- adapters from `ToolResultView` / `script_receipt` into `NodeOutcome`;
- adapters from existing `ExecutionPlan` concepts into node execution payloads;
- scheduled knowledge push;
- workflow tool promotion;
- local eval harness transcript capture;
- capability registry integration.

Those are intentionally out of scope for LM1E.
