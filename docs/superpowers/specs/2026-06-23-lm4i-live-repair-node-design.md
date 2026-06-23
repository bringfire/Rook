# LM4I — Live Repair Node (Full 5-Node Create→Verify→Repair→Reverify→Done, Live)

Status: design approved (brainstorming), pre-plan.
Campaign: Rook local/internal-model reliability (LM). North-star:
`docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`.
Predecessor: LM4H (PR #335, merge `12cd537`) — first live producer→verifier
handoff, test-only, stopped at `repair_same_component.status == "ready"`.

## Goal

Make LM3H's **non-live** capstone (`create → verify → repair → reverify → done`)
**live, end-to-end, to a terminal clean state** — by driving a **second** live
producer dispatch (the repair) through the already-proven role-agnostic
`run_live_producer_node`, with no new production code.

LM4H drove **one** live dispatch (create) and stopped where the verifier unlocked
repair. LM4I drives **two** live dispatches (create with a broken body, then repair
with a corrected body), runs the two pure verifier steps between/after, and applies
the explicit terminal `done` marker — proving failed live producer evidence
**branches to repair and re-verification confirms the repaired artifact clean**.

This closes the open LM4 exit criterion: *"failed nodes branch to repair or
escalation by policy"* and *"a two-to-four-node task can run without relying on the
model to remember the plan."*

## Non-Goals (explicit, load-bearing)

- **No production scheduler / runner / node-selection policy.** "Full 5-node" means
  a **hand-driven inline test composition** over existing seams. The test names every
  node id explicitly and drives them in a hardcoded order. No automatic node
  selection, no retry loop, no model loop. (Reviewer guardrail.)
- **No new production module and no production code change.** Two new test files only
  — the exact shape LM4H landed.
- **Does NOT prove the `:v1` versioned execution refs live.** Both producer nodes
  declare versioned refs (`gh_create_csharp_script:v1`, `gh_update_script:v1`); the
  live test deliberately **overrides** them to the LM4E/smoke-proven unversioned
  tools (`gh_create_script`, `gh_update_script`) and asserts the declared ref
  **before** each override so template drift is caught. Proving the versioned-ref
  dispatch compatibility is a separate future slice.
- **Does NOT prove automatic rolling-memory propagation of the repair target.** The
  repair's target guid is **hand-wired** in the test from the create node's evidence
  (`repair_anchor.component_guid`). Automatic carry-forward through rolling memory is
  scheduler work, deliberately deferred.
- **Does NOT prove `gh_create_csharp_script` live** (inherited LM4H non-goal).

## Why This Slice

- The repair node is **itself an `artifact_producer`**: in
  `gh_csharp_create_verify_repair_verify`, `repair_same_component` has
  `outcome_projection_role: artifact_producer` and `execution_ref:
  gh_update_script:v1`, and is **not** terminal. So `run_live_producer_node` (LM4D,
  role-agnostic — it gates on `role == "artifact_producer"` + `status == "ready"` +
  resolvable ref/params) can drive it with **zero** new dispatch machinery.
- The guid handoff is already proven feasible:
  `test_base_agent_live_producer_live.py:91-93` reads
  `node.evidence.repair_anchor["component_guid"]` live after a create, and
  `gh_update_script` takes a `guid` argument (`server.py:15206`).
- Reaching terminal `complete` is a stronger LM4 checkpoint than "repair node ran" —
  it proves the chain reaches a **reverified clean terminal state**.

## The Registered Template (under guard)

`gh_csharp_create_verify_repair_verify` — selected via the exact descriptor
`{domain: "grasshopper", operation: "create_verify_repair_verify", language:
"csharp"}` (verified against `DEFAULT_REGISTRY`, plan_graph_templates.py:360-366).
5 nodes:

| node | role | execution_ref (declared) | terminal |
|------|------|--------------------------|----------|
| `create_script` | artifact_producer | `gh_create_csharp_script:v1` | no |
| `verify_create` | artifact_verifier | — | no |
| `repair_same_component` | artifact_producer | `gh_update_script:v1` | no |
| `verify_repair` | artifact_verifier | — | no |
| `done` | — | — | **yes** |

Edges: `create_script →requires→ verify_create`,
`verify_create →on_repair→ repair_same_component`,
`repair_same_component →requires→ verify_repair`,
`verify_repair →requires→ done`.

The live test asserts `selected_template_id` and both declared producer refs
**before** any mutation/override.

## Architecture — Existing Seams Only

| Seam | Module | Role in LM4I |
|------|--------|--------------|
| `run_live_producer_node` | `agent/base_agent.py` (LM4D) | drives BOTH producer dispatches (create, repair) |
| `apply_live_producer_node` | `agent/plan_graph_live.py` (LM4A) | resolve→dispatch→delegate, under the agent method |
| `LiveProducerResult` | `agent/plan_graph_live.py` | graph-bearing producer result (carries `.graph`) |
| `apply_verifier_step` | `learning/plan_graph_runner.py` (LM3E) | both pure verifier steps (verify_create, verify_repair) |
| `build_live_producer_record` / `LiveProducerExpectation` | `agent/plan_graph_live_runner.py` (LM4G) | durable evidence records for both producer dispatches |
| `apply_outcome` / `graph_status` / `NodeOutcome` | `learning/plan_graph.py` | terminal `done` marker + final `complete` assertion |
| `select_template` | `learning/plan_graph_templates.py` | registry path + drift guard |
| `_mcp_tool_executor` | `rook/server.py` | live tool executor injected into RookAgent |

## Design Decisions

1. **5-node template, not 3-node.** The 3-node `gh_csharp_create_verify_repair`
   makes repair terminal and has no reverify; only the 5-node template proves
   re-verification-clean to a terminal state.
2. **Assert declared refs before overriding.** `create_script ==
   gh_create_csharp_script:v1`, `repair_same_component == gh_update_script:v1`,
   asserted before the override to the proven unversioned tools. Drift in the
   registered template fails the test loudly.
3. **Hand-wire the repair guid from create evidence.**
   `repair_guid = create_node.evidence.repair_anchor["component_guid"]` (assert
   non-empty str), then set `guid: repair_guid` in the repair node's
   `execution_params` alongside the **corrected** C# body.
4. **Broken create body, corrected repair body.** Create dispatches the LM4E/LM4H
   canonical seam body `A = DefinitelyMissingSymbol;` / `pins_out: ["A:double"]`
   (compiles to `created_with_errors`). Repair dispatches a clean body
   (e.g. `A = 42.0;`) → `usable` receipt → producer projects `succeeded`.
5. **`done` is a terminal marker only.** Do NOT dispatch or verify it. After
   `verify_repair` unlocks `done` to `ready`, apply `NodeOutcome(status="succeeded")`
   to `done`, then assert `graph_status(final_graph) == "complete"`. `complete` is a
   `GraphStatus`, not a `NodeStatus` (plan_graph.py:25-28, 132-135); `NodeOutcome`
   rejects pending/ready/running (plan_graph.py:89-91).
6. **Keep the GH-document setup guard.** Reuse LM4H's `_ensure_gh_document()`
   (`gh_document_new` + `_is_error`/skip). The live path needs an **active GH
   document**, not just the `_Grasshopper` window — a receipt-less first-run
   `blocked` means a missing doc, not a settle race.
7. **Restore `knowledge/gh/operations_knowledge.json` after live acceptance.** Live
   runs dirty it; `git restore` it post-run (it must never enter a commit/slice).

## Deliverables — Two Tests, No Production Code

### (a) Pure composition guard — `mcp_server/tests/test_plan_graph_live_repair_chain.py`

In the focused `test_plan_graph*` gate (runtime-free, synthetic evidence). Proves the
full 5-node chain composes to `complete` without any live capture:

1. `select_template` → assert `gh_csharp_create_verify_repair_verify` + both declared
   producer refs.
2. `apply_outcome(create_script, succeeded, broken-producer evidence)` (synthetic
   `created_with_errors` + `repair_anchor`) → assert `verify_create` unlocks (`ready`).
3. `apply_verifier_step(verify_create, create_script)` → `needs_repair`, unlock
   `repair_same_component` (`ready`).
4. `apply_outcome(repair_same_component, succeeded, usable-producer evidence)` →
   assert `verify_repair` unlocks (`ready`).
5. `apply_verifier_step(verify_repair, repair_same_component)` → `succeeded`/passed,
   unlock `done` (`ready`).
6. `apply_outcome(done, succeeded)` → assert `graph_status() == "complete"`.
7. Compose both `build_live_producer_record` expectations (the two-successes seam
   for create — `outcome_status`/`node_status` succeeded despite `tool_status:
   failed`, `artifact_status: created_with_errors`; the clean seam for repair) over
   the synthetic `LiveProducerResult`s — assert
   `evaluated` / `passed`.

### (b) Live proof — `mcp_server/tests/test_live_repair_chain_live.py`

`requires_rhino` + `asyncio`. Drives the two live dispatches:

1. `await _ensure_gh_document()` (skip-safe).
2. `select_template` → assert template id + both declared producer refs.
3. Override `create_script` ref → `gh_create_script`; set broken
   `execution_params`; `status = "ready"`.
4. `agent = RookAgent(tool_executor=_mcp_tool_executor)`;
   `create_result = await agent.run_live_producer_node(graph, "create_script")`.
5. `build_live_producer_record(create_result, <two-successes-seam expectation:
   outcome/node succeeded, tool_status failed, verified False, artifact_status
   created_with_errors>)` →
   assert passed; assert `verify_create` unlocked on `create_result.graph`.
6. `apply_verifier_step(create_result.graph, "verify_create", "create_script")` →
   `needs_repair`, `repair_same_component` → `ready`.
7. **Guid handoff:** `repair_guid =
   create_result.graph.nodes["create_script"].evidence.repair_anchor["component_guid"]`
   (assert non-empty str).
8. Assert `repair_same_component` declared ref `== gh_update_script:v1`; override →
   `gh_update_script`; set repair `execution_params` (`guid: repair_guid`, corrected
   body, matching pins).
9. `repair_result = await agent.run_live_producer_node(<verifier-step graph>,
   "repair_same_component")`.
10. `build_live_producer_record(repair_result, <clean seam expectation>)` → assert
    passed (`tool_status: success`, `verified: True`/`artifact_status: usable`,
    `outcome_status: succeeded`); assert `verify_repair` unlocked.
11. `apply_verifier_step(repair_result.graph, "verify_repair",
    "repair_same_component")` → `succeeded`/passed, `done` → `ready`.
12. `apply_outcome(<graph>, "done", NodeOutcome(status="succeeded"))`; assert
    `graph_status(final) == "complete"`.

## Data Flow

```
create dispatch (broken body)  --LiveProducerResult.graph-->  verify_create (pure)
   evidence.repair_anchor.component_guid ----------------+        |needs_repair
                                                         |        v
repair dispatch (corrected body, guid=^)  <--hand-wire--+   repair_same_component ready
   --LiveProducerResult.graph-->  verify_repair (pure)  --succeeded-->  done (ready)
   apply_outcome(done, succeeded)  -->  graph_status == "complete"
```

## Error Handling / Risks

- **No active GH doc** → `_ensure_gh_document` skips (LM4H lesson; not a settle race).
- **Repair targets wrong/absent component** → guarded by assert-non-empty
  `repair_guid` + assert-before-override on the repair ref; a bad guid surfaces as a
  failed/blocked repair producer record, not a silent pass.
- **Template drift** (refs/roles/edges change) → assert-before-override + the pure
  guard's topology assertions fail loudly.
- **`gh_update_script` GH1-legacy refusal** (`server.py:1643`) → the created component
  is a RhinoCode (GH2) C# script via `gh_create_script`, the supported update path;
  pinned by the corrected-body dispatch returning `usable`.
- **`operations_knowledge.json` dirtied by live run** → `git restore` post-run.

## Testing Strategy

- Pure guard runs in the focused `test_plan_graph*` gate (deterministic, CI).
- Live proof is `requires_rhino` (deselected from normal CI; skip-safe when Rhino/GH
  unreachable). Acceptance: Rhino + Grasshopper open, run
  `pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_live.py`.
- Post-merge focused-gate count expected to rise by the pure-guard test(s); live
  count by one.

## Diff Guard

- New files only: `mcp_server/tests/test_plan_graph_live_repair_chain.py`,
  `mcp_server/tests/test_live_repair_chain_live.py`, plus this spec + the plan.
- **Zero** edits to `agent/`, `learning/`, `server.py`. `git numstat` over
  production paths must show 0 changes (verified in the plan's gate step).
