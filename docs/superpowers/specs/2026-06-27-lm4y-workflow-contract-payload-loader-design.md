# LM4Y - Workflow Contract Payload Loader Design

**Date:** 2026-06-27
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push - workflow contract artifact loading
**Predecessors:** LM4N (#345) `propose_next_node` -> LM4O (#352) `revalidate_proposal` -> LM4P (#353) `map_accepted_proposal_to_step` -> LM4Q (#354) `execute_mapped_step` -> LM4R (#356) `run_current_mapped_step` -> LM4S (#357) `run_current_step_stream` -> LM4U (#365) `CatalogCurrentStepProvider` -> LM4V (#367) catalog provider live proof -> LM4W (#371) `RookWorkflowContract` -> LM4X (#372) workflow contract fingerprint and compile record

---

## 1. Goal

LM4X gave workflow contracts a schema-tagged normalized artifact and stable fingerprint:

```text
RookWorkflowContract
-> snapshot_workflow_contract(...)
-> WorkflowContractSnapshot.normalized_contract
-> contract_fingerprint
```

LM4Y adds the inverse bridge for already-parsed payloads:

```text
Mapping[str, Any] payload
-> load_workflow_contract_payload(...)
-> RookWorkflowContract
```

This is the first loader boundary. It is intentionally boring. It accepts the exact LM4X
normalized schema envelope, represented as already-parsed Python mappings/lists/tuples, and
returns typed `RookWorkflowContract` dataclasses.

LM4Y does not parse text or files. It does not compile or run. It does not authorize a
fingerprint. It only turns a canonical schema-shaped payload into the typed contract object
that LM4W/LM4X already understand.

---

## 2. Production Scope

Add one public function to the existing module:

```text
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
```

Public surface:

```python
def load_workflow_contract_payload(
    payload: Mapping[str, Any],
) -> RookWorkflowContract:
    ...
```

The loader belongs in this module because it directly targets the existing
`WORKFLOW_CONTRACT_SCHEMA`, `RookWorkflowContract` dataclasses, and
`snapshot_workflow_contract` validation gate.

No new production module is added:

- no `plan_graph_workflow_contract_loader.py`;
- no package-level exports;
- no registry.

Private helpers may be introduced, but all helper names should remain private, for example:

- `_load_template_ref_payload`;
- `_load_initial_param_payload`;
- `_load_rule_payload`;
- `_load_step_spec_payload`;
- `_load_expected_ref_payload`;
- `_require_fields`;
- `_copy_json_payload`.

No public partial loaders are added.

---

## 3. Accepted Input

LM4Y accepts only the LM4X normalized schema envelope:

```python
{
    "schema": "rook.workflow_contract:v1",
    "workflow_id": "...",
    "template": {
        "descriptor": {...},
        "expected_template_id": "...",
    },
    "initial_params": (...),
    "rules": (...),
    "terminal_node_ids": (...),
    "expected_refs": (...),
    "max_steps": 6,
    "metadata": {...},
}
```

`payload["schema"]` must equal `WORKFLOW_CONTRACT_SCHEMA`.

LM4Y does not accept:

- schema-less authoring shapes;
- friendly aliases;
- inferred defaults;
- compact rule syntax;
- Python class-name step kinds;
- JSON text;
- file paths;
- YAML;
- old or future schema values.

The only representation flexibility is container-level:

- schema sequence fields may be `list` or `tuple`;
- nested JSON array values may be `list` or `tuple`;
- mappings must be `Mapping` instances with string keys.

This lets LM4Y load payloads produced by:

```python
snapshot.normalized_contract
```

and by already-parsed JSON-style containers:

```python
json.loads(json.dumps(snapshot.normalized_contract))
```

Production loader code must not call `json.loads` or `json.dumps`.

---

## 4. Loader Flow

`load_workflow_contract_payload` flow:

1. Require `payload` is a `Mapping`, otherwise `TypeError`.
2. Require the exact top-level field set, otherwise `ValueError`.
3. Require `payload["schema"] == WORKFLOW_CONTRACT_SCHEMA`, otherwise `ValueError`.
4. Parse nested records with exact field sets.
5. Convert declared sequence fields to tuples while preserving order.
6. Copy JSON-shaped payload containers so the returned contract does not alias caller data.
7. Construct `RookWorkflowContract`.
8. Call `snapshot_workflow_contract(contract)` as the canonical graph-free validation gate.
9. Return only the `RookWorkflowContract`.

The internal validation snapshot is not returned. Callers explicitly compose:

```python
contract = load_workflow_contract_payload(payload)
snapshot = snapshot_workflow_contract(contract)
scaffold = compile_workflow_contract(contract)
```

Returning only the contract keeps LM4Y from becoming a second receipt API. LM4X owns
snapshots, fingerprints, and compile records.

---

## 5. Exact Field Sets

LM4Y must validate exact field sets before constructing dataclasses. It should not use
`SomeDataclass(**payload)`.

A private helper should enforce exact fields consistently:

```python
def _require_fields(
    payload: Mapping[str, Any],
    *,
    required: frozenset[str],
    context: str,
) -> None:
    keys = set(payload)
    missing = required - keys
    extra = keys - required
    if missing:
        raise ValueError(f"{context} missing required fields: {sorted(missing)!r}")
    if extra:
        raise ValueError(f"{context} has unknown fields: {sorted(extra)!r}")
```

Required field sets:

```python
TOP_LEVEL = frozenset({
    "schema",
    "workflow_id",
    "template",
    "initial_params",
    "rules",
    "terminal_node_ids",
    "expected_refs",
    "max_steps",
    "metadata",
})

TEMPLATE = frozenset({"descriptor", "expected_template_id"})
INITIAL_PARAM = frozenset({"node_id", "execution_params"})
RULE = frozenset({"node_id", "steps_by_seen_count"})
EXPECTED_REF = frozenset({"node_id", "execution_ref"})

PRODUCER_STEP = frozenset({"kind", "node_id"})
VERIFIER_STEP = frozenset({
    "kind",
    "verifier_node_id",
    "source_node_id",
    "expected_outcome",
})
BIND_STEP = frozenset({"kind", "node_id", "base_params", "bindings"})
```

Unknown or missing fields are `ValueError` at every level:

- top-level envelope;
- template record;
- initial-param record;
- rule record;
- producer step record;
- verifier step record;
- bind step record;
- expected-ref record.

Top-level `metadata` is required. It may be an empty mapping, but it may not be missing and
may not be `None`.

`VerifierStepSpec.expected_outcome` is required and may be `None`.

---

## 6. Step Dispatch

Step dispatch is literal by `"kind"` only:

```text
"producer" -> ProducerStepSpec
"verifier" -> VerifierStepSpec
"bind"     -> BindStepSpec
```

Rules:

- missing `"kind"` -> `ValueError`;
- non-string `"kind"` -> `ValueError`;
- unknown `"kind"` -> `ValueError`;
- no inference from fields;
- no aliases such as `"produce"` or `"verify"`;
- no Python class-name variants such as `"ProducerStepSpec"`.

Variant field sets are checked after reading `"kind"` and before dataclass construction.

A verifier-shaped record without `"kind"` must be rejected.

LM4Y preserves `expected_outcome` as-is. It only requires the field to be present. LM4X
`snapshot_workflow_contract` validates whether the value is `None` or a known outcome.

---

## 7. Sequence And Mapping Rules

Schema-defined sequence fields accept only `list` or `tuple`:

- `initial_params`;
- `rules`;
- `steps_by_seen_count`;
- `terminal_node_ids`;
- `expected_refs`;
- bind path values.

Generic `Sequence` is not accepted. Strings must not be treated as sequences.

Nested JSON array values inside `execution_params`, `metadata`, and bind `base_params`
also accept only `list` or `tuple`, then copy to tuples.

Mapping keys must be strings everywhere:

- top-level payload;
- template descriptor;
- execution params;
- metadata;
- bind base params;
- bind `bindings`;
- nested mappings inside JSON-shaped payloads.

Non-string mapping keys raise `TypeError`. LM4Y does not stringify keys.

---

## 8. Copy And Aliasing

The returned `RookWorkflowContract` must not alias caller-owned payload containers.

Load-time copies:

- descriptor mapping;
- initial execution params mapping and nested JSON-shaped containers;
- metadata mapping and nested JSON-shaped containers;
- bind base params mapping and nested JSON-shaped containers;
- bindings mapping;
- binding path values converted to tuples;
- declared sequences converted to tuples.

Use a small JSON-shaped copy helper rather than `copy.deepcopy`:

```python
def _copy_json_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        # require string keys
        return {key: _copy_json_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_copy_json_payload(item) for item in value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("JSON float values must be finite")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(...)
```

This helper is not a second graph-free contract validator. It only enforces that external
payload containers can be safely copied into a contract object without preserving arbitrary
Python objects or caller aliases. LM4X remains the canonical snapshot validator.

---

## 9. Validation Split

LM4Y owns schema-envelope loading:

- top-level payload is a mapping;
- exact field sets;
- required fields;
- unknown-field rejection;
- literal step-kind dispatch;
- basic container expectations needed to construct dataclasses;
- no caller-payload aliasing.

LM4X `snapshot_workflow_contract` remains canonical for graph-free contract validation:

- duplicate ids;
- empty ids;
- invalid `expected_outcome`;
- invalid `max_steps`;
- malformed bind paths after tuple conversion;
- non-JSON-safe nested payloads;
- non-finite floats;
- fingerprint normalization.

The loader must call `snapshot_workflow_contract(contract)` before returning. If snapshot
validation fails, `load_workflow_contract_payload` raises and returns no contract.

For example, a duplicate-rule payload should fail through the loader:

```python
with pytest.raises(ValueError):
    load_workflow_contract_payload(payload_with_duplicate_rule_ids)
```

The test does not need to prove whether LM4Y or LM4X detected the duplicate. The required
property is that invalid structural contracts cannot be returned.

---

## 10. Error Taxonomy

Use built-in exceptions only. LM4Y does not introduce `WorkflowContractLoadError`.

`ValueError`:

- missing required field;
- unknown extra field;
- unsupported schema value;
- missing, non-string, or unknown step kind;
- invalid known literal/value;
- malformed binding path contents when detected before snapshot validation.

`TypeError`:

- top-level payload is not a `Mapping`;
- nested record is not a `Mapping`;
- wrong container type;
- non-string mapping keys;
- non-JSON-safe value types detected during JSON-shaped copy;
- non-finite float detected during JSON-shaped copy.

Tests should assert exception type and only lightweight message fragments where helpful.
Avoid pinning complete error strings.

---

## 11. Round Trip Requirement

LM4Y must preserve exact LM4X fingerprints for valid normalized payloads.

Direct snapshot payload:

```python
source = snapshot_workflow_contract(_repair_contract())
loaded = load_workflow_contract_payload(source.normalized_contract)
roundtrip = snapshot_workflow_contract(loaded)

assert roundtrip.contract_fingerprint == source.contract_fingerprint
assert roundtrip.normalized_contract == source.normalized_contract
```

Already-parsed JSON-style payload:

```python
payload = json.loads(json.dumps(source.normalized_contract))
loaded = load_workflow_contract_payload(payload)
roundtrip = snapshot_workflow_contract(loaded)

assert roundtrip.contract_fingerprint == source.contract_fingerprint
assert roundtrip.normalized_contract == source.normalized_contract
```

LM4Y must preserve:

- declared sequence order;
- mapping values after LM4X normalization;
- `expected_outcome=None` when present;
- bind path segments as explicit sequences;
- metadata payloads exactly after LM4X normalization.

LM4Y must not:

- sort declared sequences;
- inject defaults;
- drop `None` fields;
- rewrite tuple paths to dotted strings;
- normalize into a friendlier or alternate schema.

---

## 12. Compile Assertion

LM4Y should include one practical consumer proof:

```python
source = snapshot_workflow_contract(_repair_contract())
loaded = load_workflow_contract_payload(source.normalized_contract)

scaffold = compile_workflow_contract(loaded)

assert scaffold.contract_snapshot.contract_fingerprint == source.contract_fingerprint
assert scaffold.contract_snapshot.normalized_contract == source.normalized_contract
```

This proves the loaded contract lands on the existing LM4W/LM4X compiler.

No stream proof is added:

- no `run_current_step_stream`;
- no fake producer runner;
- no live Rhino/GH test;
- no terminal outcome application.

Existing LM4W chain tests remain the execution regression gate.

---

## 13. Boundary Guard

Extend the existing module boundary guard for compile/runtime authority.

Add a loader-specific AST assertion scoped only to:

- `load_workflow_contract_payload`;
- private helpers whose names start with `_load_`.

Those function bodies must not call or reference:

- `compile_workflow_contract`;
- `select_template`;
- `initialize_graph`;
- `json.loads`;
- `json.dumps`;
- `open`;
- `Path`;
- `yaml`.

The module may still use `json.dumps` in LM4X `_fingerprint_normalized_contract`.
The guard must be function-scoped so LM4X fingerprinting remains valid.

---

## 14. Tests

Add one focused test file:

```text
mcp_server/tests/test_plan_graph_workflow_contract_loader.py
```

Test groups:

1. Direct `WorkflowContractSnapshot.normalized_contract` load:
   - returns `RookWorkflowContract`;
   - exact fingerprint and normalized-contract round trip.
2. JSON-style parsed payload:
   - `json.loads(json.dumps(snapshot.normalized_contract))`;
   - list containers load;
   - exact fingerprint and normalized-contract round trip.
3. Compile assertion:
   - loaded contract compiles;
   - scaffold snapshot matches source snapshot.
4. Exact field-set rejection:
   - missing and extra top-level fields;
   - unknown template field;
   - unknown initial-param field;
   - unknown rule field;
   - unknown producer/verifier/bind step field;
   - unknown expected-ref field.
5. Step dispatch:
   - missing `kind`;
   - non-string `kind`;
   - unknown `kind`;
   - verifier-shaped record without `kind` is rejected.
6. Metadata:
   - missing metadata -> `ValueError`;
   - `metadata=None` -> `TypeError`;
   - `metadata={}` accepted.
7. Container and key strictness:
   - top-level non-mapping -> `TypeError`;
   - sequence field as string -> `TypeError`;
   - bind path as dotted string -> `TypeError`;
   - non-string nested mapping key -> `TypeError`.
8. Caller aliasing:
   - mutate original payload after load in descriptor, metadata, params, bind base params,
     and binding path list;
   - loaded contract round-trip fingerprint remains unchanged.
9. Delegated LM4X validation:
   - duplicate rule ids raise through loader;
   - invalid `expected_outcome` raises through loader;
   - invalid `max_steps=True` raises through loader.
10. Loader-specific AST boundary:
   - loader and `_load_*` helpers do not call compile, template selection, graph init,
     JSON parse/dump, file IO, path APIs, or YAML.

No new live test is added.

---

## 15. Deliberate Non-Goals

LM4Y does not add:

- JSON text parsing;
- JSON file loading;
- YAML support;
- path or encoding policy;
- schema migrations;
- schema-less authoring shape;
- friendly aliases or inferred defaults;
- public partial loader helpers;
- public canonical JSON helper;
- fingerprint authorization;
- compile helper returning scaffold;
- stream/run helper;
- provider metadata integration;
- run ledger;
- live Rhino/GH checks;
- terminal completion.

LM4Y is strictly:

```text
already-parsed LM4X schema envelope -> RookWorkflowContract
```

---

## 16. Verification And Gates

Targeted tests:

```text
mcp_server/tests/test_plan_graph_workflow_contract_loader.py
mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py
mcp_server/tests/test_plan_graph_workflow_contract.py
mcp_server/tests/test_plan_graph_workflow_contract_chain.py
```

Focused gate:

```text
LM4N-Y PlanGraph-focused gate
```

Additional checks:

- `git diff --check`;
- production scope guard:
  - only `plan_graph_workflow_contract.py` production changes expected;
  - no new production module;
  - no runtime authority imports;
- no live Rhino/GH acceptance required;
- no `knowledge/gh/operations_knowledge.json` mutation;
- no `base_agent.py` drift.

Execution mode:

- write and review this spec;
- write and review the plan;
- inline execution is acceptable after plan approval;
- do not skip spec/plan review gates.

Merge remains gated by explicit approval after review.
