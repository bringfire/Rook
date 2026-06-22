# LM4A-FU1 — Runnable Snapshot Boundary Audit

**Date:** 2026-06-22
**Type:** Findings / boundary audit (not a feature slice)
**Trigger:** The LM4A "Option A" design correction.

---

## What triggered the audit

During LM4A (the first live producer-node dispatch adapter) we discovered a
mistaken assumption:

> We treated `runnable_nodes(graph)` as a cheap **predicate** ("is this node
> runnable?"). It is actually a **snapshot API** that **deep-copies** every ready
> node: `[copy.deepcopy(node) for node in graph.nodes.values() if node.status == "ready"]`
> (`mcp_server/src/rook/learning/plan_graph.py`).

In a **live side-effect preflight**, that deep copy can **raise** on a transient
non-deepcopyable `execution_params` value *before* the adapter reaches
`_resolve_params` — making the graceful `params_copy_failed` path unreachable in
production as well as in tests. LM4A was corrected to read `node.status == "ready"`
directly. This audit checks whether the same mistaken assumption lives anywhere
else before we build more live execution (Stage 5) on top.

## All production call sites, classified

| Site | Use | Verdict |
|------|-----|---------|
| `plan_graph.py:121` — `runnable_nodes` definition | snapshot api (deep-copies ready nodes) | valid as-is |
| `plan_graph.py:136` — `graph_status` | `if runnable_nodes(graph) or …` — truthiness **predicate** | **safe (pure).** Deepcopy-for-a-bool is wasteful but there is no live side effect |
| `plan_graph_runner.py:102` — `apply_verifier_step` | membership **predicate** ("verifier runnable?") | **safe (pure).** No live side effect |
| `plan_graph_runner.py:154` — `_producer_runnable_check` | membership **predicate** ("producer runnable?") | **safe.** Pure; in LM4A's live flow it runs only *after* `_resolve_params` proved the params copyable |
| `plan_graph_walker.py:107` — `_make_report` | report of final runnable node ids — **snapshot** | **OK snapshot** — exactly its purpose |
| `plan_graph_walker.py:147` — `walk_plan_graph` | membership **predicate** before a bridge step | **safe (pure).** Pure replay, no live tool |

(Test-file references in `tests/test_plan_graph*.py` are assertions about the
snapshot's contents and are not call-site classifications.)

## Conclusion

**No new misuse found.** Four sites *are* predicate uses of a snapshot API — the
same idiom LM4A tripped on — but **all four live in the pure learning layer**,
which already treats graph deep-copyability as a universal invariant:
`apply_outcome`, `initialize_graph`, `runnable_nodes`, and the walker all deep-copy
on every transition. A non-deepcopyable metadata value is out-of-contract for the
*entire* pure layer, not a `runnable_nodes`-specific hazard, and none of these
sites precedes a live side effect.

**The hazard is structurally confined to the agent/live boundary** — the one place
a node legitimately carries transient dispatch payload (`execution_params`) that
is meant to be handed to a tool and discarded, *not* persisted through graph
deep-copies. That boundary is `agent/plan_graph_live.py`, and it is already
corrected.

## Boundary rule (for future Stage-5 slices)

> In a **live side-effect preflight**, read `node.status == "ready"` **directly**.
> Do **not** use `runnable_nodes` — it is a snapshot API that deep-copies and can
> raise on transient non-copyable payload before graceful handling runs. In
> **pure** scheduling/replay code, `runnable_nodes` is correct and idiomatic.

## Actions taken

- **Regression guard (one test):** `test_adapter_does_not_use_runnable_nodes` in
  `mcp_server/tests/test_plan_graph_live.py` AST-asserts that
  `agent/plan_graph_live.py` never imports, references, or calls `runnable_nodes`
  (import / `ast.Name` / `ast.Attribute`). The existing import-boundary test
  allows `rook.learning.plan_graph` (the adapter needs `PlanGraph` /
  `PlanGraphNode`), so without this guard a future edit could silently re-import
  `runnable_nodes` and reintroduce the hazard.
- **No production refactor.** The four pure predicate uses are safe and
  behavior-equivalent; changing them would be churn.
- **No change to `runnable_nodes`.** Its deep-copy behavior is correct for
  snapshot consumers.
- **No `is_node_runnable(graph, node_id)` helper.** Only one live-adapter site has
  needed the direct check; repeated need is not yet proven. If a second live
  consumer needs a readiness predicate, design a pure `is_node_runnable` then —
  deliberately, not preemptively.
