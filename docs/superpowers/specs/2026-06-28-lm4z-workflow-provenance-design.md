# LM4Z - Workflow Provenance Envelope Source Design

**Date:** 2026-06-28
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM4 closeout joint
**Predecessors:** LM4N (#345) `propose_next_node` -> LM4O (#352) `revalidate_proposal` -> LM4P (#353) `map_accepted_proposal_to_step` -> LM4Q (#354) `execute_mapped_step` -> LM4R (#356) `run_current_mapped_step` -> LM4S (#357) `run_current_step_stream` -> LM4U (#365) `CatalogCurrentStepProvider` -> LM4V (#367) catalog provider live proof -> LM4W (#371) `RookWorkflowContract` -> LM4X (#372) workflow contract fingerprint and compile record -> LM4Y (#373) workflow contract payload loader

---

## 1. Purpose

LM4X gave compiled workflow scaffolds a receipt:

```text
RookWorkflowContract
-> normalized contract snapshot
-> contract_fingerprint
-> WorkflowCompileRecord
-> CompiledWorkflowScaffold
```

LM4S gives current-step streams an audit trace:

```text
EnvelopeSupplyRecord[]
CurrentStepRecord[]
stop_reason
final_graph
```

LM4Y lets an already-parsed schema payload round-trip into a typed contract and compile into the scaffold again.

The missing joint is that an LM4S stream trace does not naturally point back to the workflow contract fingerprint or compile receipt that prepared it. Callers can keep that association externally, but the trace itself does not carry it.

LM4Z adds one narrow bridge:

```text
CompiledWorkflowScaffold receipt
-> provenance-aware EnvelopeSource wrapper
-> LM4S supply records and LM4R current-step records carry compact workflow provenance
```

LM4Z does not run a stream. It does not compile contracts. It does not select, map, revalidate, execute, mutate graphs, apply terminal nodes, parse files, or talk to models. It only overlays compact compile identity onto returned `EnvelopeSupplyResult` metadata and, for valid supplied envelopes, onto `CurrentStepEnvelope.metadata`.

---

## 2. Public Surface

Add one new production module:

```text
mcp_server/src/rook/agent/plan_graph_workflow_provenance.py
```

Public constants:

```python
WORKFLOW_PROVENANCE_METADATA_KEY = "workflow_provenance"
WORKFLOW_PROVENANCE_METADATA_INVALID_REASON = "workflow_provenance_metadata_invalid"
WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON = (
    "workflow_provenance_metadata_collision:workflow_provenance"
)
```

Public callable dataclass:

```python
@dataclass(frozen=True)
class WorkflowProvenanceEnvelopeSource:
    scaffold: CompiledWorkflowScaffold
    source: EnvelopeSource | None = None

    def __call__(
        self,
        graph: PlanGraph,
        records: tuple[CurrentStepRecord, ...],
        supply_records: tuple[EnvelopeSupplyRecord, ...],
    ) -> EnvelopeSupplyResult:
        ...
```

There is no factory function. The class is the artifact and the callable envelope source.

The implementation may use private constants for diagnostic metadata keys, but only the metadata key and invalid/collision reason strings above are public.

---

## 3. Provenance Payload

The wrapper snapshots one compact provenance payload at construction from `scaffold.compile_record`:

```python
{
    "workflow_id": compile_record.workflow_id,
    "contract_schema": compile_record.contract_schema,
    "contract_fingerprint": compile_record.contract_fingerprint,
    "compiler_id": compile_record.compiler_id,
    "provider_id": compile_record.provider_id,
    "selected_template_id": compile_record.selected_template_id,
}
```

This payload is a lightweight pointer to the compile receipt. It is not a copy of the full receipt.

Do not include:

- `graph_node_ids`;
- `initial_param_node_ids`;
- `rule_node_ids`;
- `terminal_node_ids`;
- `expected_refs`;
- `step_kinds_by_rule`;
- `max_steps`;
- scaffold or contract metadata payloads;
- normalized contract payload;
- timestamps;
- machine/user/path/environment fields.

`WorkflowProvenanceEnvelopeSource` keeps the internal provenance snapshot private. There is no public `.provenance` property. Tests and callers can derive the expected payload from `scaffold.compile_record`, which remains the canonical source.

When inserting provenance into returned metadata, use a copied payload value:

```python
merged["workflow_provenance"] = dict(self._provenance)
```

The contract is value equality, not object identity. Tests should assert:

```python
supply_provenance == envelope_provenance == expected_provenance
```

They should not assert `is`.

---

## 4. Constructor Semantics

`WorkflowProvenanceEnvelopeSource` is frozen. It uses `object.__setattr__` in `__post_init__` to default `source` and to set the private provenance snapshot.

### 4.1 Type Validation

Raise `TypeError` when:

- `scaffold` is not a `CompiledWorkflowScaffold`;
- `source` is neither callable nor `None`.

When `source is None`, default it to `scaffold.provider`.

### 4.2 Receipt Invariants

Raise `ValueError` when the scaffold receipt contradicts itself:

```python
scaffold.compile_record.contract_fingerprint != (
    scaffold.contract_snapshot.contract_fingerprint
)
scaffold.compile_record.contract_schema != (
    scaffold.contract_snapshot.normalized_contract["schema"]
)
scaffold.compile_record.workflow_id != scaffold.workflow_id
scaffold.compile_record.workflow_id != scaffold.contract_snapshot.workflow_id
scaffold.compile_record.provider_id != CATALOG_CURRENT_STEP_PROVIDER_ID
```

These checks happen at construction time because a malformed scaffold receipt is not a runtime provider decision.

---

## 5. Call Semantics

`WorkflowProvenanceEnvelopeSource.__call__` delegates exactly once:

```python
supplied = self.source(graph, records, supply_records)
```

It passes through the exact `graph`, `records`, and `supply_records` objects it receives. It does not inspect graph state and does not mutate graph state.

Delegated source exceptions are not caught. If the source raises, the exception propagates to LM4S, and `run_current_step_stream` records `provider_error` exactly as before. LM4Z provenance is attached only to returned `EnvelopeSupplyResult` objects.

If the delegated source returns a non-`EnvelopeSupplyResult` value such as `None`, `object()`, or another malformed object, LM4Z passes that value through unchanged with no provenance. LM4S must preserve its existing taxonomy and record `provider_invalid` with `invalid_reason="supply_result_invalid"`. LM4Z must not access `.metadata` or any other fields before checking the returned value is an `EnvelopeSupplyResult`.

The wrapper always returns a new `EnvelopeSupplyResult` object for returned `EnvelopeSupplyResult` results.

It preserves by value or reference:

- `decision`: original value;
- `reason`: original value;
- `envelope`: original reference except for valid supplied envelopes that need enriched envelope metadata.

It replaces:

- `metadata`: a new top-level mapping with `workflow_provenance` inserted.

LM4Z does not decide whether a result is semantically valid. It preserves delegated invalid shapes for LM4S to classify, unless metadata attachment itself must fail closed.

---

## 6. Metadata Merge Rules

Normal metadata merge:

```python
merged = dict(original_metadata or {})
merged["workflow_provenance"] = dict(self._provenance)
```

This is a shallow top-level copy only.

LM4Z does not:

- mutate delegated metadata;
- deep-copy nested metadata values;
- JSON-normalize metadata;
- evaluate provider metadata semantics.

LM4S and LM4R remain responsible for copying metadata into records and reporting metadata copy status.

### 6.1 Supply Metadata

Every returned `EnvelopeSupplyResult` gets supply metadata enrichment unless supply metadata is invalid or colliding.

Rules:

- `metadata is None` becomes `{"workflow_provenance": ...}`;
- mapping metadata is shallow-copied and enriched;
- non-mapping metadata returns an invalid LM4S-native supply shape;
- mapping metadata containing `"workflow_provenance"` returns an invalid LM4S-native supply shape.

Supply metadata is checked first.

### 6.2 Envelope Metadata

Only enrich `CurrentStepEnvelope.metadata` when:

```python
decision == "SUPPLY" and envelope is not None
```

For that case, return a new `CurrentStepEnvelope`:

```python
CurrentStepEnvelope(
    mapping=original.envelope.mapping,
    metadata=merged_envelope_metadata,
)
```

The original mapping object is preserved. The original envelope is not mutated.

For invalid `HALT` with an envelope, unknown decisions with an envelope, or any other non-`SUPPLY` decision, preserve the original envelope reference and only enrich supply metadata.

Envelope metadata is checked after supply metadata.

### 6.3 Invalid Metadata Results

When supply or envelope metadata is non-mapping:

```python
EnvelopeSupplyResult(
    decision="SUPPLY",
    envelope=None,
    reason="workflow_provenance_metadata_invalid",
    metadata={
        "workflow_provenance": <payload>,
        "workflow_provenance_error": "metadata_invalid",
        "workflow_provenance_error_location": "supply" | "envelope",
    },
)
```

When supply or envelope metadata already contains `"workflow_provenance"`:

```python
EnvelopeSupplyResult(
    decision="SUPPLY",
    envelope=None,
    reason="workflow_provenance_metadata_collision:workflow_provenance",
    metadata={
        "workflow_provenance": <payload>,
        "workflow_provenance_error": "metadata_collision",
        "workflow_provenance_error_location": "supply" | "envelope",
        "workflow_provenance_collision_key": "workflow_provenance",
    },
)
```

Diagnostic keys are intentionally not public constants in LM4Z:

- `workflow_provenance_error`;
- `workflow_provenance_error_location`;
- `workflow_provenance_collision_key`.

The invalid result does not copy the delegated non-mapping or colliding metadata. It creates a new invalid supply result that explains why provenance attachment was refused.

LM4S then records `provider_invalid` through its existing invalid-supply taxonomy, normally `supply_missing_envelope`.

---

## 7. Enrichment Matrix

| Delegated result shape | Supply metadata | Envelope metadata | Decision/reason |
|---|---|---|---|
| `SUPPLY` with envelope | enriched | enriched in a new envelope | preserved |
| `SUPPLY` with `envelope=None` | enriched | none | preserved |
| `HALT` with `envelope=None` | enriched | none | preserved |
| `HALT` with envelope | enriched | original envelope preserved, not enriched | preserved |
| unknown decision | enriched | original envelope preserved, not enriched | preserved |
| supply metadata invalid/collision | invalid LM4Z result | none | LM4Z invalid reason |
| envelope metadata invalid/collision | invalid LM4Z result | none | LM4Z invalid reason |
| non-`EnvelopeSupplyResult` return | no provenance, passed through unchanged | no provenance | LM4S classifies `supply_result_invalid` |
| source raises | no result from LM4Z | no result from LM4Z | exception propagates |

---

## 8. Data Flow

Primary intended flow:

```text
normalized payload
-> load_workflow_contract_payload(...)
-> snapshot_workflow_contract(...)
-> compile_workflow_contract(...)
-> CompiledWorkflowScaffold
-> WorkflowProvenanceEnvelopeSource(scaffold)
-> run_current_step_stream(scaffold.graph, provenance_source, max_steps=scaffold.max_steps)
-> EnvelopeSupplyRecord.metadata["workflow_provenance"]
-> CurrentStepRecord.metadata["workflow_provenance"]
```

`run_current_step_stream` remains caller-invoked. LM4Z does not provide a run helper.

---

## 9. Boundaries

Allowed imports in the new production module:

- `dataclass`, `field`;
- `Mapping`, `Any`;
- `CompiledWorkflowScaffold`;
- `CATALOG_CURRENT_STEP_PROVIDER_ID`;
- `CurrentStepEnvelope`;
- `CurrentStepRecord`;
- `EnvelopeSource`;
- `EnvelopeSupplyRecord`;
- `EnvelopeSupplyResult`;
- `PlanGraph` under `TYPE_CHECKING` if needed for annotations.

Disallowed imports or referenced runtime functions:

- `run_current_step_stream`;
- `run_current_mapped_step`;
- `execute_mapped_step`;
- `map_accepted_proposal_to_step`;
- `revalidate_proposal`;
- `propose_next_node`;
- `compile_workflow_contract`;
- `snapshot_workflow_contract`;
- `load_workflow_contract_payload`;
- `run_explicit_sequence`;
- live runner seams;
- base agent;
- dispatcher;
- server;
- model surfaces;
- LM4G producer record/evaluation builders;
- `apply_outcome` or terminal completion helpers;
- JSON/YAML/file/path loading.

LM4Z is metadata provenance only.

---

## 10. Tests

Add a dedicated test file:

```text
mcp_server/tests/test_plan_graph_workflow_provenance.py
```

### 10.1 Unit Tests

Cover:

1. Constructor defaults `source` to `scaffold.provider`.
2. Constructor rejects non-`CompiledWorkflowScaffold` with `TypeError`.
3. Constructor rejects non-callable source with `TypeError`.
4. Constructor rejects inconsistent scaffold receipt values with `ValueError`:
   - fingerprint mismatch;
   - schema mismatch;
   - compile record workflow id differs from scaffold workflow id;
   - compile record workflow id differs from snapshot workflow id;
   - provider id mismatch.
5. Delegation passes exact `graph`, `records`, and `supply_records` to the source.
6. Valid `SUPPLY` with envelope returns:
   - new `EnvelopeSupplyResult`;
   - new `CurrentStepEnvelope`;
   - same mapping object;
   - supply metadata has provenance;
   - envelope metadata has equal provenance;
   - delegated metadata objects are not mutated.
7. Valid `HALT` returns:
   - enriched supply metadata;
   - no envelope.
8. Delegated invalid `SUPPLY, envelope=None` preserves decision/reason and enriches supply metadata.
9. Invalid `HALT` with envelope enriches supply metadata and preserves original envelope reference without enriching envelope metadata.
10. Unknown decision preserves decision/reason and enriches supply metadata only.
11. Supply metadata non-mapping returns `workflow_provenance_metadata_invalid`.
12. Supply metadata collision returns `workflow_provenance_metadata_collision:workflow_provenance`.
13. Envelope metadata non-mapping returns `workflow_provenance_metadata_invalid`.
14. Envelope metadata collision returns `workflow_provenance_metadata_collision:workflow_provenance`.
15. Invalid result metadata shape includes:
    - `workflow_provenance`;
    - `workflow_provenance_error`;
    - `workflow_provenance_error_location`;
    - `workflow_provenance_collision_key` for collisions only.
16. Delegated non-`EnvelopeSupplyResult` returns pass through unchanged so LM4S records `supply_result_invalid`.
17. Delegated source exceptions propagate.
18. No public provenance property is required or tested.

### 10.2 Offline Receipt-Chain Integration Test

Use the existing repair workflow contract fixture style and fake runner style from `test_plan_graph_workflow_contract_chain.py`.

Test flow:

```text
source_snapshot = snapshot_workflow_contract(repair_contract)
payload = source_snapshot.normalized_contract
loaded = load_workflow_contract_payload(payload)
loaded_snapshot = snapshot_workflow_contract(loaded)
scaffold = compile_workflow_contract(loaded)
source = WorkflowProvenanceEnvelopeSource(scaffold)
result = await run_current_step_stream(
    scaffold.graph,
    source,
    max_steps=scaffold.max_steps,
    runner=fake_runner,
)
```

Assertions:

- `loaded_snapshot.contract_fingerprint == source_snapshot.contract_fingerprint`;
- `scaffold.contract_snapshot.contract_fingerprint == source_snapshot.contract_fingerprint`;
- exact stream trace reaches terminal halt:
  - `create_script` -> producer;
  - `verify_create` -> verifier;
  - `repair_same_component` -> bind;
  - `repair_same_component` -> producer;
  - `verify_repair` -> verifier;
  - final supply `HALT` for `done`;
- every supply record has `metadata["workflow_provenance"]`;
- every executed current-step record has `metadata["workflow_provenance"]`;
- every provenance payload has `contract_fingerprint == scaffold.compile_record.contract_fingerprint`;
- every provenance payload has the compact field set only;
- final `HALT` supply record also has provenance;
- terminal `done` is ready but not applied by LM4S;
- stream `stop_reason == "provider_halt"`;
- no live/Rhino dependency.

### 10.3 Boundary Guard

Add an AST/import boundary test for `plan_graph_workflow_provenance.py`.

It should assert:

- allowed imports are limited to the small bridge set;
- banned runtime authority names are absent;
- there are no calls or imports for compile/load/snapshot functions;
- there are no JSON/YAML/file/path parsing surfaces;
- no model/server/dispatcher/base-agent names appear.

### 10.4 Verification Gates

Targeted:

```powershell
pytest `
  mcp_server/tests/test_plan_graph_workflow_provenance.py `
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  -q
```

Focused:

```powershell
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
pytest $files -q
```

Diff guards:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
git diff --name-only main..HEAD -- base_agent.py knowledge/gh/operations_knowledge.json
git diff --name-only main..HEAD -- mcp_server/src/rook/agent | Sort-Object
```

Expected production diff:

```text
mcp_server/src/rook/agent/plan_graph_workflow_provenance.py
```

No live test is required.

---

## 11. Out Of Scope

LM4Z does not add:

- stream runner helper;
- compile-and-run helper;
- file, JSON text, or YAML loader;
- graph fingerprinting;
- full compile record duplication in stream metadata;
- failed compile receipt;
- stream-level provenance for provider exceptions;
- RookChat integration;
- local model worker;
- scheduler;
- terminal completion;
- evaluation verdicts;
- LM4 closeout checkpoint doc.

After LM4Z lands, a separate closeout checkpoint can summarize the LM4 ladder and the LM5 starting line.

---

## 12. North-Star Fit

LM4Z completes the LM4 receipt path without adding authority:

```text
payload artifact
-> typed contract
-> normalized snapshot
-> contract fingerprint
-> compile record
-> compiled scaffold
-> provenance-aware envelope source
-> stream trace records
```

This matches the north-star rule that the model does not own the plan, graph mutation, memory, verification, mapping, or execution authority. The scaffold owns the contract and receipt. The stream records become inspectable enough for later local/internal model work to say which exact workflow artifact produced a given trace.

LM4Z is the final small joint before shifting to LM5-style questions about how a local/internal model consumes one narrow workflow surface under the scaffold.
