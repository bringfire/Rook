# LM3H — Full 5-node Re-verification Chain (the non-live PlanGraph capstone)

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), eighth slice
**Branch:** `codex/lm3h-five-node-reverification-chain`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM1E reducer/types (`plan_graph.py`), LM1G bridge (`plan_graph_bridge.py`), LM3B/LM3C/LM3G templates (`plan_graph_templates.py`), LM3E verifier-step runner + LM3G producer step (`plan_graph_runner.py`), LM3F role-aware projection (`plan_graph_projection.py`).

---

## Summary

LM3H registers the full **linear re-verification chain** — `create → verify → repair → reverify → done` — and proves a registered graph can be driven to `complete` by deterministic primitives, **without the model remembering the workflow**. This is the **capstone of the non-live PlanGraph semantics**: pure graph state + pure primitives represent and execute a create/verify/repair/reverify/finalize workflow end to end.

**"Linear re-verification chain," not a loop.** This shape has long been called the "5-node loop" (historical shorthand only). It is **not** a retry/re-entry cycle: the reducer unlocks only **pending** targets (`apply_outcome` gates on `target.status == "pending"`), so a node that already succeeded cannot be re-unlocked. The chain runs forward exactly once. The happy path — reverify finds the repaired artifact **clean** — is the proof. "Reverify still broken → re-repair" would require re-entrancy / retry / escalation policy and is explicitly **out of scope**.

LM3H adds **no new production primitives**. Every drive primitive already exists:
- `apply_producer_step` (LM3G) drives **both** producer nodes (create and repair).
- `apply_verifier_step` (LM3E) drives **both** verifier nodes.
- `apply_outcome` (LM1E) finalizes the terminal `done` marker.

The only production change is `plan_graph_templates.py` (a new builder + registry entry, additive). This makes LM3H a small, template-plus-proof slice.

## Boundary (hard constraints)

- **Third registered template, additive.** `gh_csharp_create_verify_repair_verify`
  (`operation="create_verify_repair_verify"`) is added beside the **byte-stable**
  2-node (`gh_csharp_create_repair`) and 3-node (`gh_csharp_create_verify_repair`)
  entries. All three stay independently selectable; exact-match criteria stay
  disjoint.
- **Linear chain, no re-entry.** No cyclic / on_repair-back / retry edge. The chain
  is driven forward exactly once. No reverify-still-broken handling, no retry, no
  escalation.
- **No new production primitives.** Reuses `apply_producer_step`,
  `apply_verifier_step`, `apply_outcome`. The only production edit is the new
  template builder + registry entry in `plan_graph_templates.py`.
- **`done` is a terminal marker only.** It has `is_terminal=True`, **no**
  `execution_ref`, **no** `verifier_ref`, and **no** `outcome_projection_role`
  metadata (it neither produces an artifact nor verifies one). Tests pin all four.
- **`done` is driven by an explicit test-only outcome.** After `verify_repair`
  succeeds and unlocks `done`, the proof constructs
  `NodeOutcome(status="succeeded", message="done: reverified clean")` and applies
  it via `apply_outcome`. **No fake `script_receipt`, no `apply_tool_result`, no
  reducer auto-complete, no production `done` helper.** The proof asserts `done` is
  `ready` **before** applying the outcome.
- **`plan_graph_templates` does NOT import `plan_graph_projection`.** Role metadata
  is literal strings (`"artifact_producer"` / `"artifact_verifier"`), pinned to the
  projection constant by a test (birth independent of drive).
- **No reducer / walker / runner / projection / verifier *logic* change.**
  Templates-only production change. No `needs_escalation`, no production
  sequencer, no model calls, no live tools, no `planner.py`.

## Module & files

- **Modify (additive):** `mcp_server/src/rook/learning/plan_graph_templates.py` —
  add `_build_gh_csharp_create_verify_repair_verify()` + a third
  `DEFAULT_REGISTRY` entry. Existing builders/entries unchanged.
- **Modify:** `mcp_server/tests/test_plan_graph_templates.py` — selection /
  three-way disjointness / topology / metadata-pin (incl. `done`
  terminal-marker-only) tests.
- **Modify:** `mcp_server/tests/test_plan_graph_runner.py` — the end-to-end
  composition proof for the 5-node chain.

## Template & topology

`gh_csharp_create_verify_repair_verify`, criteria
`{domain: "grasshopper", operation: "create_verify_repair_verify", language: "csharp"}`:

```
create_script         metadata[outcome_projection_role]="artifact_producer"
  --requires-->    verify_create         metadata[outcome_projection_role]="artifact_verifier"
  --on_repair-->   repair_same_component  metadata[outcome_projection_role]="artifact_producer"  (NOT terminal)
  --requires-->    verify_repair         metadata[outcome_projection_role]="artifact_verifier"
  --requires-->    done                  [is_terminal=True; no execution_ref / verifier_ref / role]
```

- `create_script`: `execution_ref="gh_create_csharp_script:v1"`,
  `verifier_ref="script_receipt_has_artifact_or_errors:v1"`,
  `repair_policy_ref="repair_same_component_once:v1"`, role `artifact_producer`.
- `verify_create`: `verifier_ref="script_receipt_has_artifact_or_errors:v1"`, role
  `artifact_verifier`. (Self-describing; `apply_verifier_step` is hardcoded to the
  verifier projection and does not read the role.)
- `repair_same_component`: `execution_ref="gh_update_script:v1"`,
  `repair_policy_ref="repair_same_component_once:v1"`, role `artifact_producer`.
  **Not terminal** (vs the 3-node, where the repair node was terminal).
- `verify_repair`: `verifier_ref="script_receipt_has_artifact_or_errors:v1"`, role
  `artifact_verifier`.
- `done`: `intent="Finalize: artifact reverified clean"`, `is_terminal=True`. No
  `execution_ref`, no `verifier_ref`, no role metadata.

All success-gated edges are `requires` (consistent with `create→verify_create`);
the one needs-repair-gated edge is `on_repair`. Role metadata uses literal strings,
test-pinned to `OUTCOME_PROJECTION_ROLE_KEY`. Bindings reuse the existing optional
pattern (`goal → memory_fact`, `component_name → create_script.metadata`).

## End-to-end proof (test-only explicit composition)

No production sequencer. One test composes the existing primitives + one explicit
terminal outcome, with `initialize_graph` called exactly once before any step:

1. `select_and_bind({...operation: "create_verify_repair_verify"...})` → bound
   graph; `initialize_graph` once → `create_script` is `ready`.
2. Inject `create_script.evidence` = `created_with_errors` receipt **with mutation
   evidence**; `apply_producer_step(graph, "create_script")` → `succeeded`,
   `evidence.verified is False`; assert `verify_create` is `ready`.
3. `apply_verifier_step(graph, "verify_create", "create_script")` → `needs_repair`;
   assert `repair_same_component` is `ready` (via `on_repair`).
4. Inject `repair_same_component.evidence` = `usable` receipt **with mutation
   evidence**; `apply_producer_step(graph, "repair_same_component")` → `succeeded`,
   `evidence.verified is True`; assert `verify_repair` is `ready` (via `requires`).
   **← repair-as-producer**
5. `apply_verifier_step(graph, "verify_repair", "repair_same_component")` →
   `succeeded`; assert `done` is `ready` (via `requires`). **← second verifier
   confirms clean**
6. Assert `done` is `ready` (watchpoint), then
   `apply_outcome(graph, "done", NodeOutcome(status="succeeded", message="done:
   reverified clean"))` → `done` is `succeeded`.
7. Assert `graph_status(graph) == "complete"`.

This proves the **same two primitives yield different outcomes by evidence**:
`verify_create → needs_repair` on `created_with_errors`, `verify_repair →
succeeded` on `usable`. The graph — not the model — carries the workflow.

## Approved decisions

- **A — Third additive template** (`operation="create_verify_repair_verify"`);
  2-node + 3-node byte-stable.
- **B — Linear re-verification chain**, not a retry loop; reverify-still-broken /
  re-entry out of scope.
- **C — Repair node is a second `artifact_producer`** (not terminal), driven by
  `apply_producer_step` from injected `usable` evidence; `requires` into the second
  verifier.
- **D — `done` is a terminal marker only** (no `execution_ref` / `verifier_ref` /
  role), driven by an explicit test-only `succeeded` outcome via `apply_outcome`;
  asserted `ready` before finalization.
- **E — No new production primitives**; the only production change is the template
  builder + registry entry.

## Testing (TDD)

1. **Selection:** `operation="create_verify_repair_verify"` selects
   `gh_csharp_create_verify_repair_verify`; the 2-node and 3-node descriptors still
   select their own templates.
2. **Three-way disjointness (evaluation trail):** for each canonical descriptor
   (`create_repair`, `create_verify_repair`, `create_verify_repair_verify`), the
   selected id is its own template AND the **other two** templates' evaluation
   trails show the `operation` criterion `value_mismatch`. No impossible
   both/neither descriptor.
3. **Topology:** the 5 node ids; edges `create_script --requires--> verify_create`,
   `verify_create --on_repair--> repair_same_component`,
   `repair_same_component --requires--> verify_repair`,
   `verify_repair --requires--> done`; `done.is_terminal is True`;
   `repair_same_component.is_terminal is False`.
4. **Role metadata-pin:** `create_script` and `repair_same_component` pinned to
   `artifact_producer`; `verify_create` and `verify_repair` to `artifact_verifier`
   (keys equal `OUTCOME_PROJECTION_ROLE_KEY`, imported from projection in the test).
5. **`done` terminal-marker-only (watchpoint):** `done` has
   `is_terminal is True`, `execution_ref is None`, `verifier_ref is None`, and
   **no** `OUTCOME_PROJECTION_ROLE_KEY` in its metadata.
6. **End-to-end chain:** the seven-step sequence above, asserting every transition
   — including `verify_create → needs_repair` vs `verify_repair → succeeded`,
   `repair` driven as a producer (`verified is True`), `done` `ready` before the
   terminal outcome, and final `graph_status == "complete"`. `initialize_graph`
   called exactly once, before any step.

## Out of scope (LM3H)

- Re-entrancy / cyclic retry / reverify-still-broken / retry / `needs_escalation`
  policy.
- Production sequencer / scheduler; any new runner primitive.
- Live evidence capture (injected in the proof) — that is LM3I.
- Any change to the reducer, walker, runner, projection, or verifier *logic*, or to
  the 2-node / 3-node templates.

## Roadmap (recorded, not built)

**Next — LM3I: role-aware live evidence-capture bridge.** Land producer/verifier
evidence on a node from **real** tool results (without LM1F's conservative outcome
overriding the producer projection), closing the gap between injected and live
evidence. It consumes this now-proven graph shape rather than co-designing it. The
campaign's decomposition: (1) truthful surface — done; (2) result/receipt truth —
done; (3) pure graph semantics — **LM3H capstone**; (4) live execution bridge —
next; (5) runner/scheduler/eval harness — later.

## File touch list

- Modify: `plan_graph_templates.py` —
  `_build_gh_csharp_create_verify_repair_verify` + third `DEFAULT_REGISTRY` entry.
- Modify: `test_plan_graph_templates.py` — selection / three-way disjointness /
  topology / role-pin / `done` terminal-marker-only tests.
- Modify: `test_plan_graph_runner.py` — the 5-node end-to-end chain proof.
