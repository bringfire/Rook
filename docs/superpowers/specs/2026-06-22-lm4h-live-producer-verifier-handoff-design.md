# LM4H — Live Producer → Verifier Handoff (Composition Proof)

**Date:** 2026-06-22
**Campaign:** LM (Local/Internal-Models reliability) — Stage 5 (live PlanGraph execution)
**Predecessors:** LM4A–LM4G (live producer path proven end-to-end through observability)
**Status:** Design — approved in brainstorming, pending spec review

---

## Goal

Prove the **first explicit live graph handoff**: one live producer run's captured
evidence drives one pure verifier step, advancing the graph through the registered
3-node template's `requires`/`on_repair` edges to unlock repair — and **stopping**
the moment `repair_same_component` reaches `ready`.

LM4H is a **test-only composition proof** over already-merged seams. It introduces
**no new production code**, no scheduler, no chain runner, and no repair dispatch.

## Non-Goals (explicit)

- **No repair dispatch.** `repair_same_component → ready` is the terminal assertion.
  Driving the repair producer live is a separate future slice (LM4I-ish).
- **No scheduler / multi-node advancement / chain runner.** The only advancement
  proven is the single `requires` unlock (producer → verifier) and the single
  `on_repair` unlock (verifier → repair). Each step is invoked explicitly in the
  test; no production function selects or advances nodes.
- **LM4H does NOT prove `gh_create_csharp_script` live dispatch compatibility.**
  The registered template declares `create_script.execution_ref ==
  "gh_create_csharp_script:v1"`. The live test deliberately overrides the producer
  dispatch ref to the already-proven generic `gh_create_script` (see Design
  Decision D4). Proving the template's *declared* producer tool live is a separate
  future slice — provisional name **"template producer-ref live compatibility."**
- **No new production module, dataclass, or function.**

## Why This Slice

LM4A–LM4G proved the live producer path end-to-end and gave it a durable,
self-explaining record (LM4G). The producer → verifier handoff *logic* is already
pure-tested over synthetic evidence in LM3G/LM3H. What remains unproven is that
**live-captured** producer evidence — a real `gh_create_script` receipt traveling
the production executor seam — drives that same handoff. LM4H closes that gap with
the smallest honest composition: one live producer run + one pure verifier step.

## Architecture — Existing Seams Only

| Seam | Module | Role in LM4H |
|------|--------|--------------|
| `select_template` | `learning/plan_graph_templates.py` | registry path → fresh `gh_csharp_create_verify_repair` 3-node graph |
| `apply_outcome` | `learning/plan_graph.py` | pure guard only: apply producer `succeeded`+evidence, unlock `verify_create` via the `requires` edge |
| `RookAgent.run_live_producer_node` | `agent/base_agent.py` (LM4D) | live test only: live producer dispatch → graph-bearing `LiveProducerResult` |
| `build_live_producer_record` | `agent/plan_graph_live_runner.py` (LM4G, pure) | durable producer record + declarative eval vs `LiveProducerExpectation` |
| `apply_verifier_step` | `learning/plan_graph_runner.py` (LM3E, pure) | verifier reads producer evidence → `needs_repair` → reducer unlocks `repair_same_component` |

The composition is **explicit in each test**. No production function advances the
chain. LM4G's `run_and_record_live_producer_node` convenience wrapper is
deliberately **not** used, because it returns a flat `LiveProducerRecord` that does
not carry the graph; the handoff needs the graph-bearing `LiveProducerResult`. LM4H
uses the correct half of LM4G — the pure `build_live_producer_record` builder — over
the `LiveProducerResult` returned by `run_live_producer_node`.

## The Registered Template (under guard)

`gh_csharp_create_verify_repair` (`_build_gh_csharp_create_verify_repair`):

```
create_script  (artifact_producer, execution_ref="gh_create_csharp_script:v1")
      │ requires
      ▼
verify_create  (artifact_verifier)
      │ on_repair
      ▼
repair_same_component  (is_terminal, execution_ref="gh_update_script:v1")
```

A `created_with_errors` producer receipt projects to `succeeded` (the producer
"two-successes" seam), unlocking `verify_create` via `requires`. `verify_create`
maps the same evidence to `needs_repair`, routing to `repair_same_component` via
`on_repair`. LM4H stops at `repair_same_component.status == "ready"`.

## Design Decisions

- **D1 — boundary: producer → verifier only.** One live side effect (producer
  dispatch) + one pure step (verifier). The verifier landing and the reducer's
  consequent edge-unlock is the full assertion surface. No second dispatch.
- **D2 — seam: Option A (pure builder + graph-bearing result).** Use
  `agent.run_live_producer_node` for the `LiveProducerResult` (has `.graph`), then
  `build_live_producer_record` for the durable record, then `apply_verifier_step`
  over `producer_result.graph`. No change to `LiveProducerRecord`, no new wrapper.
- **D3 — test surface: live + pure guard (Option B).** The live test is the new
  truth; the pure guard is a Rhino-independent CI **composition contract** over the
  registered topology + LM4G record builder + LM3E verifier step. The guard does
  not claim to prove live capture and does not retest all of LM3G/LM4G.
- **D4 — live producer ref override.** The live test keeps the registered 3-node
  topology but overrides `create_script.execution_ref` to the proven
  `gh_create_script` for dispatch, so the slice's only live variable is the
  handoff — not whether `gh_create_csharp_script` shares the receipt contract. The
  override mutates a cloned/built graph instance only; the registry/template
  definition is never touched. Both tests assert the original
  `gh_create_csharp_script:v1` ref before any mutation so the override is visibly
  deliberate and template drift is caught in CI and live alike.
- **D5 — broken body.** `A = DefinitelyMissingSymbol;` empirically yields
  `artifact_status == "created_with_errors"` on RhinoCode 8.33 (LM4E-established);
  `B = new Box();` does not error on this build. A clean `usable` producer would
  route the verifier to `succeeded` and not exercise `on_repair`, so the broken
  body is required to prove the verifier-mediated repair unlock.
- **D6 — pure guard unlock via `apply_outcome`, not direct status setting.** The
  guard applies `NodeOutcome(status="succeeded", evidence=...)` to `create_script`
  via `apply_outcome` and asserts `verify_create.status == "ready"`, proving the
  real `requires`-edge unlock (mirroring what the live producer path does through
  the reducer) rather than hand-setting both statuses. It still avoids
  `apply_producer_step` and still uses synthetic evidence.

## Deliverables — Two Tests, No Production Code

### (a) Pure composition guard

**File:** `mcp_server/tests/test_plan_graph_live_handoff.py`
(INSIDE the `test_plan_graph*` focused gate; Rhino-independent.)

Claim: *the registered 3-node template topology + LM4G record builder + LM3E
verifier step still compose as LM4H expects.* It is **not** a live-capture proof.

Flow:

1. Select via the registry path and guard the template contract:
   ```python
   selection = select_template(
       {"domain": "grasshopper", "operation": "create_verify_repair", "language": "csharp"}
   )
   assert selection.selected_template_id == "gh_csharp_create_verify_repair"
   assert selection.graph is not None
   graph = selection.graph
   assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
   ```
2. Build synthetic broken producer evidence mirroring the live-capture shape:
   ```python
   evidence = NodeEvidence(
       tool_status="failed",
       verified=False,
       receipt={"artifact_status": "created_with_errors"},
       repair_anchor={"component_guid": "pure-guard-guid"},
   )
   ```
3. Apply the producer outcome through the reducer (proves the `requires` unlock):
   ```python
   applied = apply_outcome(graph, "create_script", NodeOutcome(status="succeeded", evidence=evidence))
   assert applied.nodes["create_script"].status == "succeeded"
   assert applied.nodes["verify_create"].status == "ready"   # requires-edge unlock
   ```
4. Build the producer record over the graph-bearing synthetic result and evaluate:
   ```python
   result = LiveProducerResult(
       graph=applied, applied=True, node_id="create_script",
       tool_name="gh_create_script", outcome_status="succeeded", reason=None,
   )
   expectation = LiveProducerExpectation(
       outcome_status="succeeded", node_status="succeeded",
       tool_status="failed", verified=False, artifact_status="created_with_errors",
   )
   record = build_live_producer_record(result, expectation)
   assert record.evaluated is True
   assert record.passed is True
   assert record.tool_status == "failed"
   assert record.artifact_status == "created_with_errors"
   ```
5. Apply the verifier step and assert the repair unlock:
   ```python
   verifier_step = apply_verifier_step(applied, "verify_create", "create_script")
   assert verifier_step.applied is True
   assert verifier_step.outcome_status == "needs_repair"
   assert verifier_step.graph.nodes["verify_create"].status == "needs_repair"
   assert verifier_step.graph.nodes["repair_same_component"].status == "ready"
   ```

### (b) Live proof

**File:** `mcp_server/tests/test_live_producer_verifier_handoff_live.py`
(OUTSIDE the gate glob; `requires_rhino`; `fresh_document` fixture.)

`pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]`.

Flow:

1. Select via the registry path (fresh deepcopy — a cloned instance; the registry
   is never mutated), then guard the declared ref **before** overriding:
   ```python
   selection = select_template(
       {"domain": "grasshopper", "operation": "create_verify_repair", "language": "csharp"}
   )
   assert selection.selected_template_id == "gh_csharp_create_verify_repair"
   assert selection.graph is not None
   graph = selection.graph
   # Template contract pinned before the deliberate dispatch-ref override:
   assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
   ```
2. Deliberate override + producer setup on the cloned graph only:
   ```python
   # LM4H overrides ONLY the producer dispatch ref to reuse the LM4E/LM4G-proven
   # gh_create_script contract. LM4H does not prove gh_create_csharp_script live.
   graph.nodes["create_script"].execution_ref = "gh_create_script"
   graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
       "language": "csharp",
       "code": "A = DefinitelyMissingSymbol;",
       "pins_in": [],
       "pins_out": ["A:double"],
       "name": "LM4HHandoffLive",
       "x": 350,
       "y": 880,
   }
   graph.nodes["create_script"].status = "ready"
   ```
3. Live producer run + durable record:
   ```python
   agent = RookAgent(tool_executor=_mcp_tool_executor)
   producer_result = await agent.run_live_producer_node(graph, "create_script")
   expectation = LiveProducerExpectation(
       outcome_status="succeeded", node_status="succeeded",
       tool_status="failed", verified=False, artifact_status="created_with_errors",
   )
   producer_record = build_live_producer_record(producer_result, expectation)
   assert producer_record.evaluated is True
   assert producer_record.passed is True
   assert producer_record.tool_status == "failed"
   assert producer_record.outcome_status == "succeeded"
   assert producer_record.node_status == "succeeded"
   assert producer_record.verified is False
   assert producer_record.artifact_status == "created_with_errors"
   ```
4. Handoff on `producer_result.graph` **before** the verifier:
   ```python
   assert producer_result.graph.nodes["create_script"].status == "succeeded"
   assert producer_result.graph.nodes["verify_create"].status == "ready"
   ```
5. Verifier step + repair unlock:
   ```python
   verifier_step = apply_verifier_step(producer_result.graph, "verify_create", "create_script")
   assert verifier_step.applied is True
   assert verifier_step.outcome_status == "needs_repair"
   assert verifier_step.graph.nodes["verify_create"].status == "needs_repair"
   assert verifier_step.graph.nodes["repair_same_component"].status == "ready"
   ```

## Data Flow

```
select_template ─► clone ─►┬─ live: override ref + inject params + ready ─► run_live_producer_node ─► LiveProducerResult(.graph)
                           └─ pure: apply_outcome(succeeded, synthetic evidence) ─► graph
                                                                                        │
                              build_live_producer_record(result)  (OBSERVE) ◄──────────┤
                              apply_verifier_step(graph)           (ADVANCE) ◄──────────┘
                                                                                        ▼
                                                       assert verify_create=needs_repair, repair=ready
```

## Error Handling / Risks

- **Live tool contract:** reuses the LM4E/LM4G-proven `gh_create_script`; the
  slice's only live variable is the handoff, not a tool contract.
- **`runnable_nodes` on the unlocked verifier:** after `apply_outcome` (pure) or
  the live producer reducer apply, `verify_create.status == "ready"`, so
  `runnable_nodes` includes it and `apply_verifier_step`'s readiness gate passes.
  First plan step verifies this against the reducer.
- **`operations_knowledge.json`** mutates on live runs → `git restore`, never
  commit (hard gate; diff guard below).
- **GH-open** is a manual live precondition; `fresh_document` skips cleanly when
  Rhino is unreachable, so the live test never hard-fails CI.

## Testing Strategy

- Pure guard runs in the focused PlanGraph gate (`test_plan_graph*.py`, from repo
  root — VERIFY-CWD: purity probes are repo-root-relative). PowerShell does not
  expand `test_plan_graph*.py`; use `Get-ChildItem` or git-bash to enumerate.
- Live proof runs only under `pytest -m requires_rhino
  mcp_server/tests/test_live_producer_verifier_handoff_live.py` with Rhino +
  Grasshopper open; deselected from normal CI.

## Diff Guard

Exactly four paths, nothing else:

- `mcp_server/tests/test_plan_graph_live_handoff.py` (new)
- `mcp_server/tests/test_live_producer_verifier_handoff_live.py` (new)
- `docs/superpowers/specs/2026-06-22-lm4h-live-producer-verifier-handoff-design.md` (this spec)
- `docs/superpowers/plans/2026-06-22-lm4h-live-producer-verifier-handoff.md` (plan)

Specifically **not** `knowledge/gh/operations_knowledge.json` (runtime mutation) or
any production module.
