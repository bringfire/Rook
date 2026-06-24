# LM4N — Bounded Node-Selection Proposal Primitive

**Date:** 2026-06-24
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push — Stage 5 → policy pivot
**Predecessors:** LM4K (#341) `bind_params_from_memory` · LM4L (#343) `apply_memory_bound_params` · LM4M (#344) `run_explicit_sequence`

---

## 1. Goal

Open the **policy/selection** surface with the smallest possible authority. LM4N adds a
**pure node-selection proposal primitive**: given a frozen `PlanGraph` snapshot, it
observes the admissible (ready) set and *proposes* a next node only when the choice is
trivially unambiguous — exactly one ready node. Zero ready and multiple ready are both
halts. It never mutates, never dispatches, never constructs a typed step, and nothing
consumes it in this slice.

This is the first policy-shaped artifact in the campaign. It **names** policy (a stable
`selector_id`) without letting policy **drive** anything. The glass box: policy gets a
shape, not authority.

---

## 2. Containment Contract (load-bearing — pin these)

- **Policy governs scaffold transition proposals, not model reasoning** (north-star §44:
  "the scaffold is the planner and the model is a node resolver"). LM4N is scaffold-side
  and has no LLM involvement.
- **Admissible nodes are observed, not bypassed.** The selector calls the canonical
  `runnable_nodes(graph)` — it never reinvents or forks the readiness definition.
- **The proposal is data, not execution.** No graph mutation, no dispatch, no
  verifier/repair/outcome calls, no typed-`Step` construction.
- **Snapshot-validity:** a `NodeSelectionProposal` is *data about the specific graph
  snapshot observed by `propose_next_node`*. It is **not authority**. Any future consumer
  MUST revalidate readiness against the current graph state before acting on it — the
  proposal can go stale the instant the graph advances. This is the contract that keeps
  LM4N from quietly becoming authority later.
- **Execution stays a later slice.** Nothing consumes the proposal in LM4N.
- **Every decision records its candidates + reason + the policy that produced it.**

---

## 3. Architecture

One new **learning-layer** module:

```
mcp_server/src/rook/learning/plan_graph_selector.py
```

A pure graph-fact query, mirroring LM3A's `plan_graph_walker.py` (also learning-layer,
also reads `runnable_nodes`, also explicitly "not a scheduler"). Learning-layer is the
honest home: it is a pure read over a `PlanGraph`, and a future agent-layer runner can
consume it one-way (`agent → learning`). It introduces **no** dependency on the agent
layer, the dispatcher, or any model.

---

## 4. Public Surface

```python
from typing import Literal

SelectionDecision = Literal["SELECT_NODE", "HALT_NONE_READY", "HALT_AMBIGUOUS_READY"]

_SELECTOR_ID = "unique_ready_node:v1"

@dataclass(frozen=True)
class NodeSelectionProposal:
    decision: SelectionDecision
    selected_node_id: str | None          # set iff decision == "SELECT_NODE"
    candidate_node_ids: tuple[str, ...]    # the admissible (ready) set, SORTED -- audit trail
    ready_count: int                       # == len(candidate_node_ids)
    reason: str                            # human/audit string
    selector_id: str                       # stable policy identity, == _SELECTOR_ID

def propose_next_node(graph: PlanGraph) -> NodeSelectionProposal: ...
```

- `selector_id = "unique_ready_node:v1"` stamps every proposal with the rule that produced
  it, so policy audit records stay traceable as future selectors are added — without
  granting any authority.
- `candidate_node_ids` is always populated (even on halts) and sorted, so the proposal is
  a self-contained audit record of what was observed.

---

## 5. Logic (the only "policy" is a uniqueness gate)

```
candidates = sorted(node.id for node in runnable_nodes(graph))
```

- `len(candidates) == 1` → `SELECT_NODE`, `selected_node_id = candidates[0]`,
  reason `"exactly one admissible ready node"`.
- `len(candidates) == 0` → `HALT_NONE_READY`, `selected_node_id = None`,
  reason `"no admissible ready node"`.
- `len(candidates) >= 2` → `HALT_AMBIGUOUS_READY`, `selected_node_id = None`,
  reason `"<N> admissible ready nodes; refusing to choose"`.

`ready_count = len(candidates)`; `selector_id = _SELECTOR_ID` on every path.

It does **not** inspect roles, edges, evidence, `graph_status`, or memory — pure
uniqueness over the ready set. In the linear repair chain there is exactly one ready node
at each transition (create → only verify_create → only repair → only verify_repair →
only done), so the selector proposes the whole sequence one node at a time; the instant a
graph forks (≥2 ready) it refuses with `HALT_AMBIGUOUS_READY`.

---

## 6. Boundaries / Invariants

- **Pure / frozen-snapshot:** reads only the graph via `runnable_nodes` (which already
  deep-copies); never mutates the input graph (asserted — node statuses + graph identity
  unchanged after a call).
- **Imports only** `runnable_nodes` + `PlanGraph` from `rook.learning.plan_graph`
  (`PlanGraph` may be `TYPE_CHECKING`-quoted) + stdlib (`dataclass`, `typing`).
- **AST import-boundary guard bans:** any `rook.agent.*` import, any dispatcher/server
  import, `apply_outcome` / `apply_verifier_step` / `apply_producer_result` references
  (it never transitions the graph), and any LiteLLM/model import.
- Production change = **exactly** one new module
  (`git diff --numstat main...HEAD -- mcp_server/src` lists only
  `learning/plan_graph_selector.py`); `base_agent.py` byte-stable; LM4K/L/M modules and
  the walker untouched.

---

## 7. Testing

Whole-branch diff = this spec + the plan + **1 module + 2 test files = 5 paths**.

### Task 1 — real TDD (the prod module)
`mcp_server/tests/test_plan_graph_selector.py` (focused `test_plan_graph*.py` gate).
Failing tests first, then the module:

- **exactly-one-ready → SELECT_NODE:** a graph with a single ready node →
  `decision == "SELECT_NODE"`, `selected_node_id` is that node, `ready_count == 1`,
  `candidate_node_ids == (that_id,)`, `selector_id == "unique_ready_node:v1"`.
- **zero-ready → HALT_NONE_READY:** a graph with no ready node (all pending, or all
  succeeded) → `decision == "HALT_NONE_READY"`, `selected_node_id is None`,
  `candidate_node_ids == ()`, `ready_count == 0`.
- **multiple-ready → HALT_AMBIGUOUS_READY:** a graph with two ready nodes →
  `decision == "HALT_AMBIGUOUS_READY"`, `selected_node_id is None`, candidates SORTED,
  `ready_count == 2`.
- **candidate sorting determinism:** ready nodes inserted out of lexical order still yield
  a sorted `candidate_node_ids`.
- **observe-not-bypass:** a graph mixing a `ready` node with `needs_repair` / `pending` /
  `running` nodes → only the `ready` node is a candidate (the selector defers to
  `runnable_nodes`, never to its own status check).
- **frozen-snapshot:** after a call, the input graph object is unchanged (node statuses
  equal; same object identity; calling twice yields equal proposals).
- **selector_id stamped on every decision** (SELECT and both HALTs).
- **AST import-boundary guard:** module imports no `rook.agent.*`, no dispatcher/server,
  references no `apply_outcome` / `apply_verifier_step` / `apply_producer_result`, no
  LiteLLM/model import.

### Task 2 — chain observation guard
`mcp_server/tests/test_plan_graph_selector_chain.py` (focused gate). Drive the real 5-node
`gh_csharp_create_verify_repair_verify` template through the reducer
(`initialize_graph` → `apply_producer_result` → `apply_verifier_step` → `apply_outcome`)
and at each transition assert `propose_next_node` proposes the unique expected next node:
`SELECT_NODE(create_script)` → after create: `SELECT_NODE(verify_create)` → after
verify_create→needs_repair: `SELECT_NODE(repair_same_component)` → after repair:
`SELECT_NODE(verify_repair)` → after verify_repair: `SELECT_NODE(done)` → after the
terminal: `HALT_NONE_READY`. Then build a hand-made **fork** graph (two ready nodes) and
assert `HALT_AMBIGUOUS_READY`.

**Honest scope:** the selector only *proposes*; nothing in this guard consumes the
proposal to dispatch or mutate. The reducer drives the graph; the selector merely observes
each resulting snapshot. This proves the selector tracks the linear chain's
unique-ready property and refuses on a fork — purely, with no execution.

### Deliberate non-goal: no live test
The selector is a pure read over `PlanGraph` state; the graph it observes is identical in
shape whether produced by a live run or offline projection. A `requires_rhino` test would
re-prove the already-proven (LM4I–M) live chain and add **zero** selector-contract
coverage. LM4N is therefore a 2-task, 5-path slice with **no live proof** — the honest,
minimal call for a pure primitive.

---

## 8. Process / Gates

- `codex/` branch off `main`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- PowerShell glob gotcha: enumerate the focused gate via `Get-ChildItem`.
- Focused PlanGraph gate green (rises from 290).
- No live acceptance step (pure primitive — see §7 non-goal).
- Merge to `main` **always** needs explicit user approval.

---

## 9. North-Star Fit

The north-star's eventual **scheduler** (§9.3) chooses the next ready node and owns graph
mutation, validating proposals against contracts before acting (§569, §574–575). That
scheduler is the surface where the system could get harder to control. LM4N is the first,
most-contained sliver of it: it computes only the trivial, unambiguous selection and
emits an auditable proposal — *separated from execution, with no authority*. It deliberately
refuses every non-trivial choice (`HALT_AMBIGUOUS_READY`), so the policy surface is named
and observable before any consumer is designed. The next rung — a runner that *consumes* a
proposal under strict revalidation (the snapshot-validity contract), or a richer selector
that resolves a fork — is explicitly out of LM4N scope and gets its own deliberate design.
