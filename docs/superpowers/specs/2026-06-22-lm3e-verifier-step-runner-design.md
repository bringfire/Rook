# LM3E — Verifier-Step Runner (first composition layer)

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), fifth slice
**Branch:** `codex/lm3e-verifier-step-runner`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM1E reducer/types (`plan_graph.py`), LM3D verifier adapter (`plan_graph_verifiers.py`).

---

## Summary

LM3E is the **first composition layer** above the pure PlanGraph primitives: a
single cross-node verifier primitive that drives one verifier node by reading a
**source node's** already-captured evidence, projecting it through the LM3D
verifier adapter, and applying the result through the LM1E reducer.

It deliberately does the irreducible minimum. The `walk_plan_graph` walker stays
byte-stable and pure (flat `(node_id, raw_result)` tool-result replay); verifier
driving — which needs cross-node evidence the flat step list can't carry — lives
in this new runner beside it, not inside it. No sequencing, no scheduling, no
producer-role semantics, no LM1F change.

This slice does **not** revive the 5-node verifier-mediated template. Reviving it
requires *producer* semantics (a node that reports `succeeded` on artifact
existence even when the receipt is `created_with_errors`), which is a distinct
execution semantic deferred to **LM3F** (see Roadmap).

## Boundary (hard constraints)

- **One primitive only:** `apply_verifier_step(graph, verifier_node_id,
  source_node_id) -> VerifierStepResult`. No sequence/interleaving runner.
- **`runnable_nodes(graph)` is the sole readiness authority.** The runner does
  **not** separately require `source.status == "succeeded"` or inspect edges to
  decide whether the verifier may run. The source node need only **exist and carry
  evidence**; if the verifier node is runnable, the reducer's state is trusted.
  This keeps edge/scheduling policy out of the runner.
- **Receipt interpretation stays in LM3D.** The runner calls
  `script_receipt_verifier_outcome`; it does not read `script_receipt` fields
  itself.
- **No `initialize_graph` inside the primitive.** Like `apply_tool_result` /
  `apply_outcome`, it operates on the graph as given.
- **Never mutates the input graph.** Not-applied returns the input unchanged;
  applied returns `apply_outcome`'s fresh deep copy.
- **No model calls, no live tools, no `planner.py`, no walker change, no LM1F
  change.**
- **Import-light:** imports only `rook.learning.plan_graph` +
  `rook.learning.plan_graph_verifiers` among rook modules (+ stdlib
  `dataclasses`). Enforced by an AST allowlist test and a subprocess probe.

## Module & files

- **New:** `mcp_server/src/rook/learning/plan_graph_runner.py`
- **New tests:** `mcp_server/tests/test_plan_graph_runner.py`

## Public surface

```python
VerifierStepReason = Literal[
    "unknown_verifier_node",
    "unknown_source_node",
    "source_evidence_missing",
    "verifier_not_runnable",
]


@dataclass(frozen=True)
class VerifierStepResult:
    graph: PlanGraph                      # new graph if applied; the unmodified input if not
    applied: bool
    verifier_node_id: str
    source_node_id: str
    outcome_status: OutcomeStatus | None  # the verifier outcome's status if applied, else None
    reason: VerifierStepReason | None     # failure code if not applied, else None


def apply_verifier_step(
    graph: PlanGraph, verifier_node_id: str, source_node_id: str
) -> VerifierStepResult
```

`OutcomeStatus` is the existing `Literal` alias re-exported from
`rook.learning.plan_graph`. `reason` is a closed `Literal` union so the diagnostic
surface is drift-pinned (matching the campaign's code/severity-table discipline).

## Algorithm

1. `verifier_node_id not in graph.nodes` → return not-applied,
   `reason="unknown_verifier_node"`.
2. `source_node_id not in graph.nodes` → return not-applied,
   `reason="unknown_source_node"`.
3. `graph.nodes[source_node_id].evidence is None` → return not-applied,
   `reason="source_evidence_missing"`.
4. `verifier_node_id not in {n.id for n in runnable_nodes(graph)}` → return
   not-applied, `reason="verifier_not_runnable"`. (Sole readiness authority — no
   `source.status` check.)
5. `outcome = script_receipt_verifier_outcome(graph.nodes[source_node_id]
   .evidence)` — the real LM3D adapter.
6. `new_graph = apply_outcome(graph, verifier_node_id, outcome)`; return
   `VerifierStepResult(graph=new_graph, applied=True,
   verifier_node_id=..., source_node_id=..., outcome_status=outcome.status,
   reason=None)`.

Not-applied results carry `graph=<input graph, unchanged>`, `applied=False`,
`outcome_status=None`, and the `reason`. `runnable_nodes` returns deep copies and
does not mutate the graph, so the input is untouched on every path.

## Approved decisions

- **A** — `VerifierStepResult` carries the new graph plus a small diagnostic
  record (consistent with `WalkReport` / `BindingResult`).
- **B** — not-applied returns the input graph unchanged (no deepcopy, since no
  mutation occurred); applied returns `apply_outcome`'s new graph.
- **C** — new module `plan_graph_runner.py` (the runner/composition home), not
  folded into `plan_graph_verifiers`.

## Test graph (no producer semantics)

A fixture with:
- a **fixture source node** (`id="source"`) pre-seeded `status="succeeded"`,
  carrying a `NodeEvidence` whose `receipt` is a `created_with_errors` (or
  `usable`) `script_receipt`;
- a **verifier node** (`id="verify"`) pre-seeded `status="ready"`;
- a `requires` edge `source → verify` and an `on_repair` edge `verify → repair`
  (with a `repair` node).

**Fixture nuance (state plainly):** because the verifier node is pre-seeded
`ready`, the `requires` source→verify edge is **documentary** — it records the
intended graph shape but is **not** what unlocks the verifier during the test. In
a real run a producer step would apply a `succeeded` outcome to `source` and the
reducer would unlock `verify`; here the verifier is pre-seeded `ready` because
producer unlocking / role-aware projection is deferred to LM3F. The test therefore
proves cross-node verifier *application*, **not** producer unlocking.

## Testing (TDD)

1. **Happy path (`needs_repair`):** source carries a `created_with_errors`
   receipt → `apply_verifier_step(graph, "verify", "source")` returns
   `applied=True`, `outcome_status="needs_repair"` **through the real LM3D
   adapter**; the result graph's `verify` node is `needs_repair`; the `on_repair`
   edge unlocks `repair` to `ready`; the `verify` node's evidence carries the
   receipt.
2. **Usable source (`succeeded`):** source carries a `usable` receipt →
   `applied=True`, `outcome_status="succeeded"`.
3. **Unknown verifier node** → `applied=False`,
   `reason="unknown_verifier_node"`, `outcome_status is None`, returned graph is
   the unmodified input.
4. **Unknown source node** → `applied=False`, `reason="unknown_source_node"`.
5. **Source evidence missing** (source exists, `evidence=None`) → `applied=False`,
   `reason="source_evidence_missing"`.
6. **Verifier not runnable** (`verify` pre-seeded `status="pending"`) →
   `applied=False`, `reason="verifier_not_runnable"`.
7. **Input graph not mutated** (happy path): the original graph's `verify` node is
   still `ready` and `source` is unchanged after the call.
8. **Purity:** AST allowlist (`rook` imports ⊆ {`rook.learning.plan_graph`,
   `rook.learning.plan_graph_verifiers`}); subprocess probe (importing
   `plan_graph_runner` loads no `tool_dispatcher` / `dspy` / `litellm`).

## Out of scope (LM3E)

- Any sequence/interleaving runner; any scheduling or node selection.
- Producer-role semantics; reviving the 5-node verifier-mediated template.
- Reading `script_receipt` fields in the runner (LM3D's job).
- `GraphMemory` input, raw tool results, escalation policy.

## Roadmap (recorded, not built)

**LM3F candidate — "role-aware outcome projection from receipt evidence."** The
same receipt should project to different graph outcomes by node **role**:
`artifact_producer: created_with_errors → succeeded`, `artifact_verifier →
needs_repair`, `direct_task → needs_repair`. This formalizes the *artifact-
existence success* (mutation: created/written) vs *artifact-functional/task
success* (verification/usability) seam that LM1D's receipt already separates and
LM1F deliberately compresses into one conservative `NodeOutcome.status` for direct
tool-result consumption. Role-awareness is the layer above LM1F — not a correction
to it. Reviving the 5-node verifier-mediated template depends on this slice.

## File touch list

- Add: `mcp_server/src/rook/learning/plan_graph_runner.py` —
  `VerifierStepReason`, `VerifierStepResult`, `apply_verifier_step`.
- Add: `mcp_server/tests/test_plan_graph_runner.py` — LM3E tests.
