# LM4V - Catalog Provider Live Proof Design

**Date:** 2026-06-25
**Status:** Design approved
**Campaign:** LM north-star internal DAG agent coordination push - reusable provider live proof
**Predecessors:** LM4T (#360) live current-step stream proof; LM4U (#365) `CatalogCurrentStepProvider`

---

## 1. Goal

LM4V is a test-only live substitution proof: the production
`CatalogCurrentStepProvider` from LM4U must carry the same live repair stream that LM4T
proved with a bespoke test-local provider.

The question is narrow and load-bearing:

```text
Can the reusable provider scaffold feed LM4S under real Rhino/Grasshopper load?
```

LM4V does not add another provider abstraction. It does not add production code. It
keeps the LM4T ladder intact and swaps only the provider:

```text
LM4N propose
-> LM4P map (embedding LM4O revalidation)
-> LM4Q execute
-> LM4R record
-> LM4S stream
```

The expected live stream is:

```text
create_script           -> producer
verify_create           -> verifier
repair_same_component   -> bind
repair_same_component   -> producer
verify_repair           -> verifier
done                    -> provider HALT, non-executed
```

The same-node repair turn remains the pressure point. LM4V proves that the production
provider's explicit count-indexed rule can select `BindStep` for the first
`repair_same_component` proposal and `ProducerStep` for the second, using LM4S-provided
history through `CurrentStepRecord`s.

---

## 2. Scope

LM4V adds:

- one live `requires_rhino` test file:
  `mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py`;
- one spec and one implementation plan.

LM4V must not add or modify production modules:

- no `mcp_server/src/**` changes;
- no provider helper or factory;
- no LM4S changes;
- no LM4T helper extraction;
- no direct LM4O call;
- no scheduler loop;
- no terminal `done` authority inside LM4S;
- no model, server, dispatcher, or `RookAgent` production wiring changes.

Whole-branch diff guard:

- docs spec;
- docs plan;
- one live test file;
- no `mcp_server/src/**`;
- no committed `knowledge/gh/operations_knowledge.json` mutation.

---

## 3. Live Test Setup

The test is marked:

```python
pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]
```

It should follow the existing live repair conventions:

- use `fresh_document`;
- call `_ensure_gh_document()` via `_mcp_tool_executor("gh_document_new", {})`;
- skip with a concrete setup reason when Grasshopper setup is unavailable;
- create a real `RookAgent(tool_executor=_mcp_tool_executor)`;
- restore `knowledge/gh/operations_knowledge.json` after live runs.

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

No producer ref override is allowed. LM4V remains a declared-ref live proof.

Initialize through the reducer seam:

```python
graph = initialize_graph(selection.graph)
assert graph.nodes["create_script"].status == "ready"
```

Then assign create params:

```python
graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
    "code": "A = DefinitelyMissingSymbol;",
    "pins_in": [],
    "pins_out": ["A:double"],
    "name": "LM4VCatalogCurrentStepProviderLive",
    "x": 350,
    "y": 1040,
}
```

Omit `language` on create params, matching the declared `gh_create_csharp_script:v1`
alias behavior already proven in LM4J/LM4T.

---

## 4. Production Provider Configuration

LM4V imports and uses the production LM4U provider directly:

```python
from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
```

The provider configuration is caller-authored in the test:

```python
provider = CatalogCurrentStepProvider(
    (
        NodeStepRule("create_script", (ProducerStep("create_script"),)),
        NodeStepRule(
            "verify_create",
            (
                VerifierStep(
                    "verify_create",
                    "create_script",
                    expected_outcome="needs_repair",
                ),
            ),
        ),
        NodeStepRule(
            "repair_same_component",
            (
                BindStep(
                    "repair_same_component",
                    {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
                    {"guid": ("repair_anchor", "component_guid")},
                ),
                ProducerStep("repair_same_component"),
            ),
        ),
        NodeStepRule(
            "verify_repair",
            (
                VerifierStep(
                    "verify_repair",
                    "repair_same_component",
                    expected_outcome="succeeded",
                ),
            ),
        ),
    ),
    terminal_node_ids=frozenset({"done"}),
)
```

The production provider owns the same-node switch through its count-indexed
`NodeStepRule`:

- first accepted `repair_same_component` record -> `BindStep`;
- second accepted `repair_same_component` record -> `ProducerStep`.

LM4V should not define a test-local provider class and should not import LM4T's
provider. The test is a production-provider substitution proof, not a side-by-side
comparison with LM4T.

---

## 5. Stream Assertions

Run:

```python
result = await run_current_step_stream(
    graph,
    provider,
    max_steps=6,
    runner=agent,
)
```

Assert:

- `result.stop_reason == "provider_halt"`;
- `result.steps_attempted == 5`;
- `len(result.records) == 5`;
- `len(result.supply_records) == 6`;
- accepted ids exactly:

  ```python
  [
      "create_script",
      "verify_create",
      "repair_same_component",
      "repair_same_component",
      "verify_repair",
  ]
  ```

- execution kinds exactly:

  ```python
  ["producer", "verifier", "bind", "producer", "verifier"]
  ```

- all executed records have:
  - `ran is True`;
  - `execution_failure is None`;
  - `mapping_mapped is True`;
  - `record.revalidation.decision == "ACCEPT"`;
  - `record.mapping.revalidation is record.revalidation`;
  - `record.supplied_selected_node_id == record.accepted_node_id`;
  - `record.fresh_selected_node_id == record.accepted_node_id`.

Assert the repair pair explicitly:

```python
bind_record = result.records[2]
repair_record = result.records[3]
assert bind_record.accepted_node_id == "repair_same_component"
assert repair_record.accepted_node_id == "repair_same_component"
assert bind_record.execution_kind == "bind"
assert repair_record.execution_kind == "producer"
assert bind_record.bind_applied is True
```

Assert pure verifier observations:

```python
assert result.records[1].verifier_applied is True
assert result.records[1].verifier_outcome_status == "needs_repair"
assert result.records[4].verifier_applied is True
assert result.records[4].verifier_outcome_status == "succeeded"
```

---

## 6. Provider Metadata Assertions

LM4V must assert the provider's audit facts through `result.supply_records`, not through
`CurrentStepRecord.metadata`.

The provider's audit surface enters through `EnvelopeSupplyResult.metadata`, which LM4S
snapshots into `EnvelopeSupplyRecord.metadata`.

For executed supplies (`0..4`):

```python
for index in range(5):
    supply = result.supply_records[index]
    record = result.records[index]
    assert supply.decision == "SUPPLY"
    assert supply.envelope is not None
    assert supply.envelope.mapping is record.mapping
    assert supply.metadata["provider"] == "catalog_current_step_provider:v1"
    assert supply.metadata["selected_node_id"] == record.accepted_node_id
```

Provider-specific live facts:

```python
bind_supply = result.supply_records[2]
repair_supply = result.supply_records[3]

assert bind_supply.metadata["selected_node_id"] == "repair_same_component"
assert bind_supply.metadata["seen_count"] == 0
assert bind_supply.metadata["step_kind"] == "bind"

assert repair_supply.metadata["selected_node_id"] == "repair_same_component"
assert repair_supply.metadata["seen_count"] == 1
assert repair_supply.metadata["step_kind"] == "producer"
```

Final halt:

```python
final_supply = result.supply_records[5]
assert final_supply.decision == "HALT"
assert final_supply.envelope is None
assert final_supply.reason == "terminal_node_selected:done"
assert final_supply.metadata["proposal_decision"] == "SELECT_NODE"
assert final_supply.metadata["selected_node_id"] == "done"
```

These metadata checks are observational only. Canonical mapping truth remains
`record.mapping` / `record.revalidation`.

---

## 7. Live Producer Observations

LM4S and `CatalogCurrentStepProvider` remain non-evaluating. The test may build LM4G
`LiveProducerRecord`s locally from native producer results for measurement only:

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

Expected create observation:

- `tool_name == "gh_create_csharp_script"`;
- `artifact_status == "created_with_errors"`;
- `verified is False`;
- repair anchor present;
- expectation record passes.

Expected repair observation:

- `tool_name == "gh_update_script"`;
- `artifact_status == "usable"`;
- `verified is True`;
- `tool_status is None` for MCP-unwrapped success;
- expectation record passes.

The LM4G records must not influence stream continuation or provider decisions.

---

## 8. Terminal Boundary

Inside LM4S:

- provider halts because the production provider sees LM4N propose `done`;
- `result.final_graph.nodes["done"].status == "ready"`;
- `result.final_graph.nodes["done"].is_terminal is True`;
- `graph_status(result.final_graph) != "complete"`.

Outside LM4S, the test applies terminal completion:

```python
completed = apply_outcome(
    result.final_graph,
    "done",
    NodeOutcome(status="succeeded"),
)
assert graph_status(completed) == "complete"
```

This exact boundary matters: LM4V proves the production provider can carry the stream to
terminal readiness without granting LM4S or the provider terminal authority.

---

## 9. Verification

Run from repo root with `mcp_server/.venv/Scripts/python.exe`.

Collect-only:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest --collect-only mcp_server\tests\test_live_catalog_current_step_provider_vertical_live.py -q
```

Live acceptance when Rhino + Grasshopper are open:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server\tests\test_live_catalog_current_step_provider_vertical_live.py -q
```

After live execution:

```powershell
git restore knowledge/gh/operations_knowledge.json
```

Deterministic provider checks:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Focused LM4N-U gate:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_selector.py mcp_server\tests\test_plan_graph_revalidation.py mcp_server\tests\test_plan_graph_step_mapping.py mcp_server\tests\test_plan_graph_step_executor.py mcp_server\tests\test_plan_graph_current_step_runner.py mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Diff guard:

```powershell
git diff --check main..HEAD
git diff --name-status main..HEAD
```

Expected branch scope:

```text
docs/superpowers/specs/2026-06-25-lm4v-catalog-provider-live-proof-design.md
docs/superpowers/plans/2026-06-25-lm4v-catalog-provider-live-proof.md
mcp_server/tests/test_live_catalog_current_step_provider_vertical_live.py
```

No `mcp_server/src/**` changes are allowed in LM4V.

---

## 10. North-Star Fit

LM4V adds live load to the reusable provider scaffold without expanding its authority.
LM4T proved the vertical stream with bespoke caller logic; LM4U made that caller logic a
bounded production scaffold; LM4V proves the scaffold itself carries the same real live
repair stream.

If LM4V passes, the campaign can ask whether a template-to-provider factory, rule
declaration layer, or user-facing workflow should sit on top. LM4V itself deliberately
answers only:

```text
Can the production catalog provider replace the LM4T closure under live load?
```
