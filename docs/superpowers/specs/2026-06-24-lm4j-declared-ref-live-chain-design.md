# LM4J — Declared-Ref Live Chain (No Producer Overrides) + Memory-Substrate Guard

Status: design approved (brainstorming), pre-plan.
Campaign: Rook local/internal-model reliability (LM). North-star:
`docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`.
Predecessor: LM4I (PR #339, merge `5d21f27b`) — first full live repair chain, with the
create producer ref overridden to the proven `gh_create_script`.

## Goal

Prove the **declared `gh_create_csharp_script:v1` PlanGraph live path**: rerun LM4I's
full 5-node live chain (`create → verify → repair → reverify → done` to
`graph_status == "complete"`) with **no producer execution refs overridden**, so
`create_script`'s registered ref `gh_create_csharp_script:v1` resolves and dispatches
live inside the PlanGraph chain — exactly as the repair node already does with
`gh_update_script:v1`. This is not about the alias *existing* (the
`gh_create_csharp_script` ↔ `gh_create_script` alias already has parity tests); it is
about the **template's declared producer ref resolving and dispatching live within the
chain**.

Plus a deterministic CI guard pinning the new substrate fact LM4J relies on: producer
projection writes the repair target (`component_guid` / `repair_anchor`) into
`graph.memory.facts` through the real `apply_producer_result` path.

This closes LM4I's biggest honest non-goal ("does not prove `gh_create_csharp_script`
live") and exercises `:vN` resolution on **both** producer nodes.

## Non-Goals (explicit, load-bearing)

- **No producer execution refs are overridden.** Both producers dispatch their real
  declared refs (`gh_create_csharp_script:v1`, `gh_update_script:v1`), each resolved by
  `_resolve_tool_name` (`:vN` stripped). This is the whole point of the slice.
- **No new production module and no production code change.** Two new test files only
  (+ this spec + the plan). `gh_create_csharp_script` already dispatches via the shared
  `_execute_gh_create_script("csharp", …)` helper — the same implementation and
  response shape as the proven `gh_create_script`.
- **No scheduler / runner / node-selection policy.** Hand-driven inline test
  composition over existing seams, every node id named explicitly.
- **No automatic rolling-memory propagation.** The repair target guid is still
  **hand-wired from create's `evidence.repair_anchor["component_guid"]`**, NOT sourced
  from `graph.memory.facts`. The memory-facts assertion is an **observational** pin
  that the substrate carries the right target; sourcing repair params from memory is a
  separate future slice.

## Why This Slice

- **Feasibility is strong.** `gh_create_csharp_script`'s dispatch case calls
  `_execute_gh_create_script("csharp", arguments, …)` — the same implementation as the
  proven `gh_create_script` (its doc: "convenience alias … both paths share the same
  implementation and response shape"). So the receipt shape (`created_with_errors`,
  `repair_anchor.component_guid`) is identical; the role-agnostic `run_live_producer_node`
  (LM4D) drives it with zero new machinery.
- **The memory-substrate claim is traced end-to-end.** On producer success:
  `apply_producer_result` → `project_receipt_outcome(evidence, "artifact_producer")` →
  `_producer_success` sets `memory_updates["facts"] = {"component_guid", "repair_anchor"}`
  (`_facts`, plan_graph_projection.py) → `apply_outcome` → `_merge_memory` does
  `graph.memory.facts.update(facts)` (plan_graph.py). So after a live/dict producer
  success, `graph.memory.facts["component_guid"]` and `["repair_anchor"]` are populated.
- **It removes LM4I's last artificial training wheel** and prepares the ground for a
  future ordered runner, which must not need special-case ref overrides.

## The Registered Template (under guard)

`gh_csharp_create_verify_repair_verify`, descriptor `{"domain": "grasshopper",
"operation": "create_verify_repair_verify", "language": "csharp"}` (verified against
`DEFAULT_REGISTRY`). 5 nodes; both producers carry their declared `:v1` refs:

| node | role | declared execution_ref | terminal |
|------|------|------------------------|----------|
| `create_script` | artifact_producer | `gh_create_csharp_script:v1` | no |
| `verify_create` | artifact_verifier | — | no |
| `repair_same_component` | artifact_producer | `gh_update_script:v1` | no |
| `verify_repair` | artifact_verifier | — | no |
| `done` | — | — | **yes** |

## Architecture — Existing Seams Only

Same seam set as LM4I (`run_live_producer_node`, `apply_live_producer_node`,
`apply_verifier_step`, `build_live_producer_record` / `LiveProducerExpectation`,
`apply_outcome` / `graph_status` / `NodeOutcome`, `select_template`,
`_mcp_tool_executor`, `fresh_document` / `_is_error`), plus — for the pure guard — `initialize_graph`
(promotes root `pending → ready`) and the LM3I dict→projection entry
`apply_producer_result(graph, node_id, raw_result)`, both from
`rook.learning.plan_graph_runner` / `rook.learning.plan_graph`, which route a raw
tool-result dict through the producer projection and populate `graph.memory.facts`.

## Deliverables — Two Tests, No Production Code

### (a) Memory-substrate pure guard — `mcp_server/tests/test_plan_graph_live_repair_memory.py`

In the focused `test_plan_graph*` gate (runtime-free, raw-dict driven through the REAL
projection path). Proves both the memory-facts substrate and that the dict-projection
path composes to `complete`:

1. `select_template` → assert template id + both declared producer refs.
2. **`graph = initialize_graph(graph)`** (root `create_script` is `pending` after
   selection; `apply_producer_result` requires a `ready` node via `runnable_nodes` and
   would otherwise return `node_not_runnable`). Assert `create_script.status == "ready"`.
3. `apply_producer_result(graph, "create_script", <WRAPPED-FAILURE raw>)` → assert
   `outcome_status == "succeeded"`, `create_script.status == "succeeded"`,
   `evidence.tool_status == "failed"`, and
   **`graph.memory.facts["component_guid"] == GUID`** +
   **`graph.memory.facts["repair_anchor"]["component_guid"] == GUID`**.
4. `apply_verifier_step(graph, "verify_create", "create_script")` → `needs_repair`,
   unlock `repair_same_component`.
5. `apply_producer_result(graph, "repair_same_component", <UNWRAPPED-SUCCESS raw>)` →
   `succeeded`; assert `graph.memory.facts["component_guid"] == GUID` still holds, and
   **`repair_same_component.evidence.tool_status is None`** (fidelity to the LM4I live
   finding); unlock `verify_repair`.
6. `apply_verifier_step(graph, "verify_repair", "repair_same_component")` → `succeeded`,
   unlock `done`.
7. `apply_outcome(graph, "done", NodeOutcome(status="succeeded"))` → assert
   `graph_status(graph) == "complete"`.

**Raw-dict shapes (load-bearing — they must mirror the live envelopes, not the older
`success: True` `_update_result` style):**
- **Create = WRAPPED FAILURE** (live create returns `success: False`):
  `{"success": False, "data": {"script_receipt": {"version": 1, "operation": "create",
  "language": "csharp", "artifact_status": "created_with_errors", "mutation":
  {"status": "created", "component_guid": GUID}, "verification": {"status": "failed",
  "target_error_count": 1}, "repair_anchor": {"component_guid": GUID, "language":
  "csharp"}}}}` → `_extract_script_receipt` reads `data.script_receipt`;
  `normalize_tool_result` sees `success: False` → `tool_status="failed"`.
- **Repair = MCP-UNWRAPPED SUCCESS** (live success is unwrapped, no envelope marker):
  `{"script_receipt": {"version": 1, "operation": "update", "language": "csharp",
  "artifact_status": "usable", "mutation": {"status": "written", "component_guid":
  GUID}, "verification": {"status": "passed", "target_error_count": 0},
  "repair_anchor": {"component_guid": GUID, "language": "csharp"}}}` (NO
  `data`/`success`/`ok`/`error` keys) → `_extract_script_receipt` reads the top-level
  `script_receipt`; `normalize_tool_result` finds no marker → `tool_status=None`.

### (b) Declared-ref live proof — `mcp_server/tests/test_live_repair_chain_declared_refs_live.py`

`requires_rhino` + `asyncio`. LM4I's live chain with **no producer override**:

1. `await _ensure_gh_document()` (skip-safe; LM4H/LM4I guard).
2. `select_template` → assert template id + both declared producer refs.
3. Set **only** `create_script.execution_params` (NO ref override): `{"code": "A =
   DefinitelyMissingSymbol;", "pins_in": [], "pins_out": ["A:double"], "name":
   "LM4JDeclaredRefLive", "x": 350, "y": 880}` — **`language` omitted** (the
   `gh_create_csharp_script` alias forces csharp). Set `status = "ready"`.
4. `create_result = await agent.run_live_producer_node(graph, "create_script")`.
5. **Direct declared-ref claim:** `assert create_result.tool_name ==
   "gh_create_csharp_script"` (the registered `:v1` ref resolved and dispatched live).
6. `build_live_producer_record(create_result, <two-successes seam: outcome/node
   succeeded, tool_status="failed", verified=False,
   artifact_status="created_with_errors">)` → assert passed.
7. **Memory-substrate live assertion:** `repair_guid =
   create_result.graph.nodes["create_script"].evidence.repair_anchor["component_guid"]`
   (assert non-empty str); assert
   `create_result.graph.memory.facts["component_guid"] == repair_guid` and
   `create_result.graph.memory.facts["repair_anchor"]["component_guid"] == repair_guid`.
8. `apply_verifier_step(verify_create, create_script)` → `needs_repair`,
   `repair_same_component` → `ready`.
9. **Hand-wire** the repair params from `repair_guid` (NOT from memory.facts): leave the
   repair ref unchanged (`gh_update_script:v1` → `gh_update_script`); set
   `repair_same_component.execution_params = {"guid": repair_guid, "code": "A = 42.0;",
   "mode": "body", "language": "csharp"}`.
10. `repair_result = await agent.run_live_producer_node(graph, "repair_same_component")`;
    `assert repair_result.tool_name == "gh_update_script"`.
11. `build_live_producer_record(repair_result, <clean seam: outcome/node succeeded,
    verified=True, artifact_status="usable">)` → assert passed; **`assert
    repair_record.tool_status is None`** (LM4I live finding — a successful, MCP-unwrapped
    producer result carries no top-level success marker; see the LM4I spec's "Live
    Findings" section, `2026-06-23-lm4i-live-repair-node-design.md`).
12. `apply_verifier_step(verify_repair, repair_same_component)` → `succeeded`,
    `done` → `ready`.
13. `apply_outcome(done, NodeOutcome(status="succeeded"))` → assert
    `graph_status == "complete"`.

## Data Flow

```
create dispatch (gh_create_csharp_script:v1 -> gh_create_csharp_script, broken body)
   -> LiveProducerResult.graph   (evidence.repair_anchor.component_guid = GUID;
                                   memory.facts{component_guid, repair_anchor} = GUID)
   verify_create (pure) -> needs_repair
   repair_guid = evidence.repair_anchor.component_guid   (hand-wired, NOT from memory)
repair dispatch (gh_update_script:v1 -> gh_update_script, corrected body, guid=^)
   -> verify_repair (pure) -> succeeded -> done (apply_outcome) -> "complete"
```

## Error Handling / Risks

- **`gh_create_csharp_script` live receipt differs from `gh_create_script`** → unlikely
  (shared `_execute_gh_create_script`), but if it surfaces, the create record's
  `mismatches` report it; capture and report, do not weaken the test.
- **`language` key in create params** → omitted by design; the alias hardcodes csharp.
- **No active GH doc** → `_ensure_gh_document` skips (LM4H/LM4I lesson).
- **Memory facts absent** → would fail the explicit memory assertion (a real finding
  about the substrate), not pass silently.
- **`operations_knowledge.json` dirtied by live run** → `git restore` post-run.

## Testing Strategy

- Pure guard runs in the focused `test_plan_graph*` gate (deterministic, CI) — the
  durable tripwire for `memory_updates -> graph.memory.facts`.
- Live proof is `requires_rhino` (deselected from CI; skip-safe). Acceptance: Rhino +
  Grasshopper open, run `pytest -m requires_rhino
  mcp_server/tests/test_live_repair_chain_declared_refs_live.py`.
- Post-merge focused-gate count rises by the pure guard's test(s); live count by one.

## Diff Guard

- New files only: the two tests above, plus this spec + the plan.
- **Zero** edits to `agent/`, `learning/`, `server.py`. `git diff --numstat
  main...HEAD -- mcp_server/src src knowledge` must be empty.
