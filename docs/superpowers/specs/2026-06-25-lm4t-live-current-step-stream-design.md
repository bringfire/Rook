# LM4T - Live Current-Step Stream Vertical Proof

**Date:** 2026-06-25
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push - vertical proof
**Predecessors:** LM4N (#345) `propose_next_node` · LM4O (#352) `revalidate_proposal` · LM4P (#353) `map_accepted_proposal_to_step` · LM4Q (#354) `execute_mapped_step` · LM4R (#356) `run_current_mapped_step` · LM4S (#357) `run_current_step_stream`

---

## 1. Goal

LM4T is a test-only live vertical proof that the completed current-step ladder carries
load under real producer seams:

```text
LM4N propose
-> LM4P map (embedding LM4O revalidation)
-> LM4Q execute
-> LM4R record
-> LM4S stream
```

The unique pressure is the same-node repair turn. After `verify_create`, LM4N proposes
`repair_same_component`. The provider must first supply a `BindStep` for that node, which
stages memory-sourced params but leaves the node ready. On the next graph snapshot, LM4N
proposes `repair_same_component` again, and the provider must supply a `ProducerStep` for
the same node. LM4T proves that caller-owned provider logic can make that current-artifact
decision from LM4S stream history without giving LM4S any scheduler authority.

This is not a new scheduler and not a production provider. It is one `requires_rhino`
test that asks whether the fenced primitives actually compose into the live repair stream
they are meant to support.

---

## 2. Scope

LM4T should add:

- one live test file, likely
  `mcp_server/tests/test_live_current_step_stream_vertical_live.py`;
- one spec and one implementation plan.

LM4T must not add or modify production modules. In particular:

- no LM4S change;
- no production provider/helper;
- no new mapper/selector/revalidator helper;
- no scheduler loop;
- no model involvement;
- no terminal `done` authority inside LM4S.

Whole-branch diff guard: docs plus one live test only. No `mcp_server/src/**` production
diff and no committed `knowledge/gh/operations_knowledge.json` mutation.

---

## 3. Live Test Envelope

The test is marked:

```python
pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]
```

It should follow existing live repair setup conventions:

- use `fresh_document`;
- call a local `_ensure_gh_document()` that invokes `gh_document_new` through
  `_mcp_tool_executor`;
- skip, never silently pass, when Grasshopper document setup is unavailable;
- create a real `RookAgent(tool_executor=_mcp_tool_executor)`;
- restore `knowledge/gh/operations_knowledge.json` after live runs:

```powershell
git restore knowledge/gh/operations_knowledge.json
```

The live test uses the registered template:

```python
_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}
```

Before execution, assert declared refs are intact:

```python
assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"
```

No producer ref override is allowed. LM4T must remain a declared-ref live proof, not an
override proof.

---

## 4. Fixed Caller-Authored Step Catalog

The test prebuilds all `Step` objects before calling `run_current_step_stream`:

```python
create_step = ProducerStep("create_script")
verify_create_step = VerifierStep(
    "verify_create",
    "create_script",
    expected_outcome="needs_repair",
)
repair_bind_step = BindStep(
    "repair_same_component",
    {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
    {"guid": ("repair_anchor", "component_guid")},
)
repair_producer_step = ProducerStep("repair_same_component")
verify_repair_step = VerifierStep(
    "verify_repair",
    "repair_same_component",
    expected_outcome="succeeded",
)
```

The provider must not construct `Step` objects inside its call method. A strict AST guard
is optional, but the spec and plan should keep Step construction visibly outside the
provider class. The provider may build a fresh per-call `node_id -> Step` map view from
this fixed catalog; it must not mutate the catalog.

The same node cannot map to both `BindStep` and `ProducerStep` at once because LM4P takes
a `node_id -> Step` map. Therefore, the provider uses a per-call map view:

- before repair binding: `{"repair_same_component": repair_bind_step}`;
- after repair binding: `{"repair_same_component": repair_producer_step}`.

---

## 5. Test-Local Provider

Use a small test-local provider class. It is not production scaffold and should stay in
the live test file.

Provider call flow:

```python
proposal = propose_next_node(current_graph)  # LM4N
step_map = self.step_map_for(records)
mapping = map_accepted_proposal_to_step(proposal, current_graph, step_map)  # LM4P
return EnvelopeSupplyResult(
    "SUPPLY",
    CurrentStepEnvelope(mapping, {"call": len(self.proposals) + 1}),
    f"caller supplied {proposal.selected_node_id}",
)
```

Do not call LM4O separately. LM4P embeds the canonical `RevalidationResult`, LM4R
preserves it, and LM4S records it. Assertions should inspect the single-source artifact
chain through:

- `record.mapping.revalidation`;
- `record.revalidation`;
- `record.supplied_selected_node_id`;
- `record.fresh_selected_node_id`;
- `record.accepted_node_id`.

The provider may hold observational/debug fields only:

- `proposals`;
- `mapped_steps` or mapped targets;
- per-call `step_map_views`;
- `records_lengths`.

It must not use mutable provider-local state to decide first-vs-second repair. The repair
switch is derived from the `records` tuple passed by LM4S:

```python
repair_seen = sum(
    1 for record in records
    if record.accepted_node_id == "repair_same_component"
)
```

Then:

- `repair_seen == 0` -> expose the prebuilt `BindStep`;
- `repair_seen == 1` -> expose the prebuilt `ProducerStep`;
- `repair_seen > 1` -> fail the test or return a provider-invalid shape; a third repair
  turn is unexpected.

When LM4N proposes `done`, the provider returns:

```python
EnvelopeSupplyResult("HALT", None, "done_ready")
```

The halt must be driven by `proposal.selected_node_id == "done"`, not by direct
`graph_status` inspection.

---

## 6. Live Payloads

Reuse the established LM4J/LM4L live repair payloads so LM4T stays focused on stream
composition.

Initialize through the graph reducer seam, then assign create params before the stream
starts:

```python
graph = initialize_graph(selection.graph)
assert graph.nodes["create_script"].status == "ready"
graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
    "code": "A = DefinitelyMissingSymbol;",
    "pins_in": [],
    "pins_out": ["A:double"],
    "name": "LM4TCurrentStepStreamLive",
    "x": 350,
    "y": 880,
}
```

Omit `language` on create params, matching declared `gh_create_csharp_script:v1`
behavior from LM4J/LM4L.

Repair params are sourced by the prebuilt `BindStep`:

```python
base_params = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}
bindings = {"guid": ("repair_anchor", "component_guid")}
```

The bind step stages the repair guid from `graph.memory.facts`, not from a test-side
assignment.

---

## 7. Expected Stream

The live stream should execute exactly five current-step records, then halt on a sixth
provider decision:

```text
0. create_script           -> producer
1. verify_create           -> verifier
2. repair_same_component   -> bind
3. repair_same_component   -> producer
4. verify_repair           -> verifier
5. done                    -> provider HALT, non-executed
```

Assertions:

- `result.stop_reason == "provider_halt"`;
- `len(result.records) == 5`;
- `len(result.supply_records) == 6`;
- supply records `0..4` have `decision == "SUPPLY"`;
- for `i in range(5)`,
  `result.supply_records[i].envelope.mapping is result.records[i].mapping`;
- final supply record has `decision == "HALT"`, `envelope is None`, and reason naming
  `done`;
- accepted ids exactly:
  `["create_script", "verify_create", "repair_same_component",
  "repair_same_component", "verify_repair"]`;
- execution kinds exactly:
  `["producer", "verifier", "bind", "producer", "verifier"]`;
- the two repair records share
  `accepted_node_id == "repair_same_component"` and differ as `bind`, then `producer`;
- provider observed `records_lengths == [0, 1, 2, 3, 4, 5]`;
- all executed records have `ran is True`;
- all executed records have `execution_failure is None`;
- all executed records have `mapping_mapped is True`;
- all executed records have `record.revalidation.decision == "ACCEPT"`.

Do not assert every consecutive graph identity. The exact trace and final stop reason
prove the stream did not stop early on `execution_refused` or `graph_not_advanced`
without relying on reducer/live graph object identity.

---

## 8. Live Producer Observations

LM4S remains non-evaluating. The test may build LM4G `LiveProducerRecord`s locally from
native producer results for observation only:

```python
create_record = build_live_producer_record(
    result.records[0].execution.producer_result,
    LiveProducerExpectation(...),
)
repair_record = build_live_producer_record(
    result.records[3].execution.producer_result,
    LiveProducerExpectation(...),
)
```

These records must not influence provider decisions or stream continuation.

Expected producer observations:

- create producer:
  - `tool_name == "gh_create_csharp_script"`;
  - `artifact_status == "created_with_errors"`;
  - `verified is False`;
  - repair anchor present;
  - expectation record passes;
- repair producer:
  - `tool_name == "gh_update_script"`;
  - `artifact_status == "usable"`;
  - `verified is True`;
  - `tool_status is None` if the MCP-unwrapped success behavior remains;
  - expectation record passes.

The stream would still have advanced/halted independently of these LM4G expectations.
They are measurement, not policy.

---

## 9. Terminal Boundary

LM4T keeps terminal authority outside LM4S.

Inside LM4S:

- provider halts because LM4N proposes `done`;
- `result.final_graph.nodes["done"].status == "ready"`;
- `result.final_graph.nodes["done"].is_terminal is True`;
- `graph_status(result.final_graph) != "complete"`.

After LM4S returns, the test may explicitly apply terminal completion outside the stream:

```python
completed = apply_outcome(
    result.final_graph,
    "done",
    NodeOutcome(status="succeeded"),
)
assert graph_status(completed) == "complete"
```

This proves the live stream reaches the terminal boundary cleanly without granting LM4S
terminal authority.

---

## 10. Process / Gates

- Branch: `codex/lm4t-live-current-step-stream`.
- Use `mcp_server/.venv/Scripts/python.exe` from the repo root.
- Live run command:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server\tests\test_live_current_step_stream_vertical_live.py -q
```

- After live run, restore runtime mutation:

```powershell
git restore knowledge/gh/operations_knowledge.json
```

- Focused non-live gate should include the merged LM4N-S PlanGraph tests to prove the new
  live test did not disturb deterministic coverage, but LM4T does not need a focused CI
  gate count bump because the new test is `requires_rhino`.
- Diff guard:
  - docs spec;
  - docs plan;
  - one live test file;
  - no `mcp_server/src/**`;
  - no `knowledge/gh/operations_knowledge.json`;
  - unrelated local installer edits remain untouched.
- Stop at PR; no merge without explicit approval.

---

## 11. North-Star Fit

LM4T is a vertical proof without authority creep. It lets the caller-owned provider
prepare fresh current-step artifacts across graph snapshots, including the real
same-node bind-then-producer repair turn. LM4S remains a stream threader: it records,
delegates, threads, and stops; it does not select, revalidate separately, map, dispatch
directly, evaluate, apply terminal completion, or remember the plan.

If LM4T passes, LM4U can ask whether any provider pattern deserves production scaffold.
LM4T itself deliberately answers only: do the fenced pieces compose under live pressure?
