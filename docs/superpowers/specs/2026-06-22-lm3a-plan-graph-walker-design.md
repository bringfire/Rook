# LM3A — PlanGraph Replay/Walker (non-live drive scaffold)

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), first slice
**Branch:** `codex/lm3a-plan-graph-walker`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`

---

## Summary

LM3A is the **drive seam** of the PlanGraph execution scaffold: a single pure
function that *replays* an explicit, caller-supplied ordered list of tool-result
evidence against an existing `PlanGraph`, advancing it through the already-merged
LM1G bridge (`apply_tool_result`) and LM1E reducer, and returns an explicit
diagnostic report.

It is deliberately **not a scheduler**. It never chooses what to run, never calls
a tool or a model, never resolves profiles/capabilities, never inspects
`script_receipt` internals, and never invents retry/escalation policy. The caller
dictates the exact `(node_id, raw_result)` sequence; the walker applies each in
turn, validates that the named node was actually runnable at that point, surfaces
the resulting state, and stops at the first terminal graph status or invalid step.

The five LM3 proof-goals split across two independent seams — **birth**
(intent → graph) and **drive** (advance a graph on evidence). LM3A builds the
**drive** seam only. It proves goals 2 (advance via existing evidence), 3 (graph
memory carries repair anchors / component ids forward), 4 (verifier/escalation
state explicit), and 5 (no live tools). Goal 1 (planner-like intent → PlanGraph)
is proved *minimally* here via hand-authored fixture graphs; the real birth seam
(template selector or `Plan`→`PlanGraph` adapter) is deferred to LM3B.

## Boundary (hard constraints)

The walker:

- **May call:** `initialize_graph`, `runnable_nodes`, `graph_status` (LM1E
  reducer) and `apply_tool_result` (LM1G bridge).
- **Must not:** choose the next node; call tools; call models; resolve
  profiles/capabilities; inspect `script_receipt` internals; duplicate edge
  semantics; invent retry/escalation policy.
- **State authority stays in LM1E.** "Runnable" is computed *only* via
  `runnable_nodes(graph)` — the walker never re-derives readiness from edges.
  All transitions go *only* through `apply_tool_result`.
- **Import-light.** Imports are restricted to stdlib (`copy`, `dataclasses`,
  `typing`) plus `rook.learning.plan_graph` and `rook.learning.plan_graph_bridge`.
  It must **not** import `plan_graph_outcomes` directly (the bridge composes it),
  `tool_result_view`, `tool_contracts`, `tool_dispatcher`, `chat_runner`,
  `rook.server`, `dspy`, or `litellm`. Enforced by an AST import-allowlist test
  and a subprocess probe (mirroring the LM1F/LM1G sibling tests).
- **No mutation of the caller's graph.** The walker relies on the reducer's
  existing deep-copy semantics (`initialize_graph` and `apply_tool_result` both
  return new graphs); per-step memory snapshots are independently deep-copied so
  later mutation of the report cannot alias graph state.

## Module & files

- **New:** `mcp_server/src/rook/learning/plan_graph_walker.py`
- **New tests:** `mcp_server/tests/test_plan_graph_walker.py`

## Public surface

```python
def walk_plan_graph(graph: PlanGraph, steps: list[tuple[str, Any]]) -> WalkReport
```

The walker calls `initialize_graph(graph)` exactly **once** at the start and
relies on the reducer's copy semantics; the caller's graph is never mutated. (We
do not assert `initialize_graph` is idempotent in prose — a focused test proves
that re-initializing an already-initialized graph does not change it
unexpectedly, and only then is the word used.)

## Report types (frozen dataclasses)

```python
@dataclass(frozen=True)
class EvidenceSummary:
    """Projection of NodeEvidence TOP-LEVEL fields only.

    Never reads evidence.receipt internals — that would be receipt inspection,
    which is forbidden. repair_anchor is a top-level NodeEvidence field, so a
    presence check on it is allowed and is surfaced as has_repair_anchor.
    """
    tool_status: str | None
    verified: bool | None
    has_repair_anchor: bool
    message: str | None
    error: str | None


@dataclass(frozen=True)
class WalkStep:
    node_id: str
    applied: bool                  # False ⇒ invalid step (not applied)
    runnable_before: bool
    status_before: NodeStatus | None
    status_after: NodeStatus | None
    graph_status_after: GraphStatus
    memory_facts: dict[str, Any]   # deep-copied snapshot AFTER this step
    evidence: EvidenceSummary | None
    reason: str | None             # "unknown_node" | "node_not_runnable" | None


@dataclass(frozen=True)
class WalkReport:
    steps: tuple[WalkStep, ...]
    final_graph: PlanGraph
    final_graph_status: GraphStatus
    final_runnable_node_ids: tuple[str, ...]
    final_memory_facts: dict[str, Any]
    nodes_needing_repair: tuple[str, ...]       # pure status reflection
    nodes_needing_escalation: tuple[str, ...]   # pure status reflection
    halted: bool
    halt_reason: str | None        # "terminal_status" | "invalid_step" | None
    remaining_steps: tuple[tuple[str, Any], ...]
```

`NodeStatus` and `GraphStatus` are the existing `Literal` aliases re-exported
from `rook.learning.plan_graph`.

`nodes_needing_repair` / `nodes_needing_escalation` are **pure status
reflections** — `tuple(id for id, node in graph.nodes.items() if node.status ==
"needs_repair"|"needs_escalation")`, sorted for determinism. They introduce no
new policy; they restate reducer state so verifier/escalation status is explicit
in the report (goal 4).

## Algorithm

1. `graph = initialize_graph(graph)` (once).
2. For each `(node_id, raw_result)` in `steps`, in order:
   a. Compute `runnable_ids = {n.id for n in runnable_nodes(graph)}` and
      `known_ids = set(graph.nodes)`.
   b. **Invalid step** — if `node_id not in runnable_ids`:
      - `reason = "unknown_node"` if `node_id not in known_ids`, else
        `"node_not_runnable"`.
      - Append `WalkStep(applied=False, runnable_before=False,
        status_before=<current status or None>, status_after=<same>,
        graph_status_after=graph_status(graph), memory_facts=<snapshot>,
        evidence=None, reason=reason)`.
      - Set `halted=True`, `halt_reason="invalid_step"`, stash the steps *after*
        this one (the unprocessed tail) in `remaining_steps`, **stop**. The
        invalid step itself is recorded as the final `WalkStep` (with
        `applied=False`) and is **not** included in `remaining_steps`.
   c. **Valid step** — apply `graph = apply_tool_result(graph, node_id,
      raw_result)`; record `runnable_before=True`, before/after node status,
      `graph_status_after`, deep-copied `memory_facts` snapshot, and
      `EvidenceSummary` built from the node's post-apply `evidence` (or `None` if
      the node has no evidence).
   d. **Terminal stop** — halt when `graph_status_after` is terminal, with one
      exception for clean completion: `failed` / `blocked` / `needs_escalation`
      **always** halt (`halt_reason="terminal_status"`); `complete` halts **only
      if unprocessed steps remain** (an early stop that surfaces the leftover
      tail). `complete` reached on the *last* step with no steps left is a
      successful natural exit, **not** a halt (`halted=False`,
      `halt_reason=None`). When halting, stash remaining steps, **stop**.
3. Fill `final_*`, `nodes_needing_*`, and (if the loop ran to completion without
   halting) `halted=False`, `halt_reason=None`, `remaining_steps=()`.

### Approved design decisions

- **A — invalid step halts (does not skip).** An out-of-order step means the
  caller's script disagrees with reducer state; skipping would require scheduling
  judgment. Record it and stop.
- **B — terminal status halts, except clean completion on the last step.**
  `failed` / `blocked` / `needs_escalation` always halt: the walker has no policy
  for unblocking, and later steps could not be runnable anyway, so this yields a
  clean `halt_reason="terminal_status"` rather than a misleading `invalid_step` on
  the next step. `complete` is the one terminal that represents success: reaching
  it with no steps left is a natural exit (`halted=False`), while reaching it with
  steps still queued is an early halt (`halt_reason="terminal_status"`) that
  surfaces the unprocessed tail. (Implemented as the `_is_halt_status` helper.)
- **C — report carries `final_graph`.** Keeps the walker composable (LM3B feeds a
  birth-seam graph in; a consumer reads the result out) while staying pure data.

## Error / edge behavior

- **Non-dict `raw_result`** (e.g. a bare string): the LM1G bridge does not raise —
  `node_outcome_from_tool_result` maps it to a `blocked` outcome. This is
  **bridge/adapter behavior surfaced by the walker**, not walker behavior: the
  walker applies it like any other valid step, records the resulting `blocked`
  status, and then halts via Decision B (terminal status). The walker adds no
  special-casing for non-dict results.
- **Unknown `node_id` in a step:** never reaches `apply_tool_result`; it is caught
  by the runnable check (step 2b) and reported as `reason="unknown_node"`. (The
  bridge *would* raise `ValueError` for an unknown node, but the walker's
  runnable pre-check means that path is not exercised — the walker turns it into a
  structured invalid-step report instead of a raise.)
- **Empty `steps`:** returns a report with `steps=()`, the initialized graph as
  `final_graph`, `halted=False`, and the initialized `final_*` snapshot.

## Testing (TDD)

1. **Full create→repair→complete replay** (reuse the LM1G create→needs_repair→
   repair→usable receipt shapes as fixtures): assert per-step `status_before`/
   `status_after`, that `memory_facts` carries `component_guid` and
   `repair_anchor` forward across steps (goal 3), `EvidenceSummary` fields, and a
   final `complete` status with `halted=False`.
2. **Invalid step — not runnable:** a step naming a node that exists but is not
   yet `ready` ⇒ `applied=False`, `reason="node_not_runnable"`, `halted=True`,
   `halt_reason="invalid_step"`, `remaining_steps` populated, **input graph
   unmutated**.
3. **Invalid step — unknown node:** a step naming a node not in the graph ⇒
   `reason="unknown_node"`, same halt behavior, no raise.
4. **Escalation fixture:** a graph whose applied outcome drives a node to
   `needs_escalation` ⇒ `final_graph_status == "needs_escalation"`,
   `nodes_needing_escalation` populated, `halt_reason="terminal_status"` (goal 4).
5. **`needs_repair` reflection:** a graph left with a `needs_repair` node and no
   unlocked repair edge ⇒ `nodes_needing_repair` populated and (per LM1E)
   `final_graph_status == "blocked"`, halting via Decision B.
6. **Non-dict raw result:** node ends `blocked`, no raise; halts via Decision B.
7. **Empty steps:** report reflects the initialized graph; `halted=False`.
8. **Initialize-once / copy semantics:** the input graph is not mutated by a full
   walk; a focused test re-initializes an already-initialized graph and asserts no
   unexpected change (this is the only place the word "idempotent" is earned).
9. **Snapshot isolation:** mutating `WalkReport.final_memory_facts` or a
   `WalkStep.memory_facts` after the call does not alter `final_graph` (deep-copy
   proof).
10. **Purity — imports:** AST import-allowlist test asserting the walker imports
    only the permitted modules; subprocess probe asserting that importing
    `rook.learning.plan_graph_walker` loads no `rook.agent.tool_dispatcher`,
    `dspy`, or `litellm`.

## Out of scope (LM3A)

- Birth seam (intent → graph): template selector or `Plan`→`PlanGraph` adapter →
  **LM3B**.
- Any node selection / scheduling among multiple runnable nodes.
- Any live tool/model call, ToolRegistry mutation, or capability/profile change.
- Any full scheduler/executor.

## File touch list

- Add: `mcp_server/src/rook/learning/plan_graph_walker.py`
- Add: `mcp_server/tests/test_plan_graph_walker.py`
