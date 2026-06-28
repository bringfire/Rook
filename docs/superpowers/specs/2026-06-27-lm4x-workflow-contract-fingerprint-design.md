# LM4X - Workflow Contract Fingerprint And Compile Record Design

**Date:** 2026-06-27
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push - workflow contract identity
**Predecessors:** LM4N (#345) `propose_next_node` -> LM4O (#352) `revalidate_proposal` -> LM4P (#353) `map_accepted_proposal_to_step` -> LM4Q (#354) `execute_mapped_step` -> LM4R (#356) `run_current_mapped_step` -> LM4S (#357) `run_current_step_stream` -> LM4U (#365) `CatalogCurrentStepProvider` -> LM4V (#367) catalog provider live proof -> LM4W (#371) `RookWorkflowContract`

---

## 1. Goal

LM4W introduced a Rook-native workflow contract compiler:

```text
RookWorkflowContract
-> compile_workflow_contract(...)
-> CompiledWorkflowScaffold
-> caller invokes run_current_step_stream(...)
```

LM4X adds the next receipt layer: content-addressed identity for the authored workflow
contract and a deterministic compile record for the scaffold produced from it.

This follows the OpenProse/Reactor guidepost of content-addressed semantic artifacts and
receipts, but LM4X implements only the Rook workflow-contract identity layer. Public APIs,
field names, and validation rules remain Rook-native.

LM4X does not make the runtime smarter. It does not execute, stream, schedule, select,
revalidate, map, evaluate, or apply terminal completion. It gives callers and reviewers a
stable way to answer two narrow questions:

- Which exact normalized workflow contract artifact is this?
- What deterministic scaffold facts resulted from a successful compile?

---

## 2. Production Scope

LM4X extends the existing workflow contract compiler module:

```text
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
```

It also makes one existing LM4U identity string public:

```text
mcp_server/src/rook/agent/plan_graph_current_step_provider.py
```

The provider change is a constant exposure only:

```python
CATALOG_CURRENT_STEP_PROVIDER_ID = "catalog_current_step_provider:v1"
_PROVIDER_ID = CATALOG_CURRENT_STEP_PROVIDER_ID
```

No behavior changes are added to LM4U.

No new production module is introduced. Snapshotting, normalization, fingerprinting, and
compile-record creation stay in `plan_graph_workflow_contract.py` so they share one
normalization path with compilation.

---

## 3. Public Surface

Add public constants to `plan_graph_workflow_contract.py`:

```python
WORKFLOW_CONTRACT_SCHEMA = "rook.workflow_contract:v1"
WORKFLOW_CONTRACT_COMPILER_ID = "rook_workflow_contract_compiler:v1"
CONTRACT_FINGERPRINT_ALGORITHM = "sha256"
```

Add two frozen dataclasses:

```python
@dataclass(frozen=True)
class WorkflowContractSnapshot:
    workflow_id: str
    normalized_contract: Mapping[str, Any]
    contract_fingerprint: str


@dataclass(frozen=True)
class WorkflowCompileRecord:
    workflow_id: str
    compiler_id: str
    contract_schema: str
    contract_fingerprint_algorithm: str
    contract_fingerprint: str
    provider_id: str
    expected_template_id: str
    selected_template_id: str
    graph_node_ids: tuple[str, ...]
    initial_param_node_ids: tuple[str, ...]
    rule_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[tuple[str, str], ...]
    step_kinds_by_rule: tuple[tuple[str, tuple[str, ...]], ...]
    max_steps: int
```

Add a public pure snapshot helper:

```python
def snapshot_workflow_contract(
    contract: RookWorkflowContract,
) -> WorkflowContractSnapshot:
    ...
```

Extend `CompiledWorkflowScaffold` by appending fields at the end:

```python
@dataclass(frozen=True)
class CompiledWorkflowScaffold:
    workflow_id: str
    graph: PlanGraph
    provider: CatalogCurrentStepProvider
    max_steps: int
    metadata: Mapping[str, Any]
    rules: tuple[NodeStepRule, ...]
    steps: tuple[Step, ...]
    contract_snapshot: WorkflowContractSnapshot
    compile_record: WorkflowCompileRecord
```

Appending keeps the change additive for existing field-name callers and minimizes churn for
any positional test construction.

No package-level exports or `rook.agent.__init__` edits are added. Callers import directly
from the module.

---

## 4. Snapshot Contract

`snapshot_workflow_contract` computes identity before template selection or graph access.
It must not call:

- `select_template`;
- `initialize_graph`;
- step compilation;
- provider construction;
- any runtime ladder seam.

It returns only `WorkflowContractSnapshot`. The internal typed normalized object used by
the compiler remains private.

The snapshot contains:

- `workflow_id`, copied from the normalized contract;
- `normalized_contract`, an immutable schema-tagged mapping;
- `contract_fingerprint`, a lowercase SHA-256 hex string.

Invariant:

```python
snapshot.workflow_id == snapshot.normalized_contract["workflow_id"]
```

The snapshot may succeed for graph-free-valid contracts that later fail graph-context
compile. For example:

- `WorkflowNodeRule.node_id="missing_in_graph"` may snapshot but compile fails if the
  selected graph lacks that node;
- `VerifierStepSpec.source_node_id="missing_in_graph"` may snapshot but compile fails if
  the selected graph lacks that source;
- a terminal id may snapshot but compile fails if the selected graph lacks it or it is not
  terminal;
- an expected-ref node id may snapshot but compile fails if the selected graph lacks it.

Identity exists before world fit.

---

## 5. Normalized Contract Shape

`WorkflowContractSnapshot.normalized_contract` is a versioned schema envelope:

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

The exposed field order mirrors `RookWorkflowContract`, with `schema` prepended:

```text
schema
workflow_id
template
initial_params
rules
terminal_node_ids
expected_refs
max_steps
metadata
```

Mapping key order is not semantic for fingerprinting. Public normalized mappings preserve
caller insertion order for debugging, while canonical JSON hashing sorts object keys.

Declared sequences are semantic and order-sensitive:

- `initial_params`;
- `rules`;
- `steps_by_seen_count`;
- `terminal_node_ids`;
- `expected_refs`.

Reordering any declared sequence changes the normalized artifact and fingerprint.

Inside JSON-shaped values, list and tuple inputs normalize to tuples everywhere in the
public snapshot. A caller using `["A:double"]` and a caller using `("A:double",)` for the
same value produce the same normalized snapshot and fingerprint.

The public snapshot uses LM4W's immutable snapshot style:

- immutable mapping containers;
- tuples for sequences;
- JSON-shaped scalar values only.

Canonical JSON is an internal hashing mechanism only. LM4X does not expose a canonical
JSON string or helper.

---

## 6. Normalized Steps

Step specs are normalized into explicit tagged records, not Python class names.

Producer:

```python
{
    "kind": "producer",
    "node_id": "create_script",
}
```

Verifier:

```python
{
    "kind": "verifier",
    "verifier_node_id": "verify_create",
    "source_node_id": "create_script",
    "expected_outcome": "needs_repair",
}
```

Bind:

```python
{
    "kind": "bind",
    "node_id": "repair_same_component",
    "base_params": {
        "code": "A = 42.0;",
        "mode": "body",
        "language": "csharp",
    },
    "bindings": {
        "guid": ("repair_anchor", "component_guid"),
    },
}
```

Rules include both the rule-level `node_id` and step-level ids:

```python
{
    "node_id": "repair_same_component",
    "steps_by_seen_count": (
        {"kind": "bind", "node_id": "repair_same_component", ...},
        {"kind": "producer", "node_id": "repair_same_component"},
    ),
}
```

This duplication is intentional. The validator ensures step ids agree with the enclosing
rule where required, then freezes the self-contained records into the normalized artifact.

Bind paths stay tuple-valued in the public snapshot. LM4X does not convert paths to dotted
strings.

---

## 7. Fingerprint

The contract fingerprint covers the entire normalized authored artifact:

- `schema`;
- `workflow_id`;
- template ref;
- initial params;
- rules;
- terminal ids;
- expected refs;
- `max_steps`;
- metadata.

Metadata participates in the fingerprint. This fingerprint answers "which exact normalized
authored contract artifact is this?", not "which executable semantics modulo labels is
this?".

`metadata=None` normalizes to an empty immutable mapping. These are fingerprint-equivalent:

```python
RookWorkflowContract(..., metadata=None)
RookWorkflowContract(..., metadata={})
```

Hash format:

```python
CONTRACT_FINGERPRINT_ALGORITHM = "sha256"
contract_fingerprint = "<64 lowercase hex chars>"
```

No `sha256:` prefix is added. The algorithm is recorded separately in
`WorkflowCompileRecord.contract_fingerprint_algorithm`.

Fingerprint computation:

```text
immutable normalized contract
-> plain canonical JSON tree
-> json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True)
-> SHA-256 lowercase hex
```

Serialization failures caused by invalid type or canonicalization shape are `TypeError`.

---

## 8. Single Normalization Path

LM4X introduces one graph-free normalization path:

```python
def _normalize_workflow_contract(contract: RookWorkflowContract) -> _NormalizedWorkflowContract:
    ...
```

This internal object is private. It captures:

- normalized typed values for compile use;
- the immutable `normalized_contract` mapping for snapshot use.

`snapshot_workflow_contract(contract)` calls the same normalizer and returns the public
snapshot.

`compile_workflow_contract(contract)` also calls the same normalizer once, builds the
snapshot from it, and compiles from that normalized intermediate. It must not snapshot and
then reread mutable caller-owned payloads from the original contract.

This prevents drift between:

- the data that was fingerprinted;
- the data that was compiled into the scaffold.

---

## 9. Compile Flow

`compile_workflow_contract` remains the only compile entry point. It now returns scaffold
identity by default:

```text
RookWorkflowContract
-> normalize
-> WorkflowContractSnapshot
-> graph-context compile
-> WorkflowCompileRecord
-> CompiledWorkflowScaffold
```

Successful compile flow:

1. Normalize the graph-free contract.
2. Build `WorkflowContractSnapshot`.
3. Select the template via `select_template(normalized.template.descriptor)`.
4. Require `selection.selected_template_id == normalized.template.expected_template_id`.
5. Require `selection.graph is not None`.
6. Initialize the graph.
7. Validate expected refs, initial params, rules, and terminal ids against the graph.
8. Compile normalized step specs into runtime `ProducerStep`, `VerifierStep`, and `BindStep`.
9. Compile normalized rules into `NodeStepRule`s.
10. Construct `CatalogCurrentStepProvider`.
11. Build `WorkflowCompileRecord`.
12. Return `CompiledWorkflowScaffold`.

`WorkflowCompileRecord` is built only after provider construction succeeds. If compilation
fails, the compiler raises as LM4W does and returns no record. Failed compile receipts are
out of scope.

---

## 10. Compile Record

`WorkflowCompileRecord` is a compact deterministic receipt for a successful compile. It is
not a run ledger.

Core fields:

```python
WorkflowCompileRecord(
    workflow_id=normalized.workflow_id,
    compiler_id=WORKFLOW_CONTRACT_COMPILER_ID,
    contract_schema=WORKFLOW_CONTRACT_SCHEMA,
    contract_fingerprint_algorithm=CONTRACT_FINGERPRINT_ALGORITHM,
    contract_fingerprint=snapshot.contract_fingerprint,
    provider_id=CATALOG_CURRENT_STEP_PROVIDER_ID,
    expected_template_id=normalized.template.expected_template_id,
    selected_template_id=selection.selected_template_id,
    graph_node_ids=tuple(sorted(graph.nodes)),
    initial_param_node_ids=tuple(entry.node_id for entry in normalized.initial_params),
    rule_node_ids=tuple(rule.node_id for rule in normalized.rules),
    terminal_node_ids=normalized.terminal_node_ids,
    expected_refs=tuple(
        (ref.node_id, ref.execution_ref)
        for ref in normalized.expected_refs
    ),
    step_kinds_by_rule=tuple(
        (
            rule.node_id,
            tuple(step.kind for step in rule.steps_by_seen_count),
        )
        for rule in normalized.rules
    ),
    max_steps=normalized.max_steps,
)
```

`graph_node_ids` includes all initialized graph nodes, sorted. It is a compact graph
observation, not a graph fingerprint.

Authored-order fields are derived from normalized contract sequences:

- `initial_param_node_ids`;
- `rule_node_ids`;
- `terminal_node_ids`;
- `expected_refs`;
- `step_kinds_by_rule`.

`step_kinds_by_rule` uses lowercase schema/provider vocabulary:

- `producer`;
- `verifier`;
- `bind`.

It is derived from normalized step specs, not Python class names or compiled `Step`
instances.

The compile record does not include:

- descriptor payloads;
- metadata or metadata keys;
- initial parameter values;
- provider rule counts or terminal counts;
- graph status or ready/root node observations;
- template graph fingerprint;
- timestamps, environment, machine, user, path, git SHA, run id, or attempt id.

---

## 11. Scaffold Invariants

`CompiledWorkflowScaffold` keeps compatibility fields but ties them to the new snapshot and
record:

```python
scaffold.workflow_id == scaffold.contract_snapshot.workflow_id
scaffold.workflow_id == scaffold.compile_record.workflow_id
scaffold.workflow_id == scaffold.contract_snapshot.normalized_contract["workflow_id"]

scaffold.compile_record.contract_fingerprint == (
    scaffold.contract_snapshot.contract_fingerprint
)
scaffold.compile_record.contract_schema == (
    scaffold.contract_snapshot.normalized_contract["schema"]
)
```

Metadata remains a compatibility/convenience field, but it must be the same immutable
object as the normalized snapshot metadata:

```python
scaffold.metadata is scaffold.contract_snapshot.normalized_contract["metadata"]
```

This is a hard anti-drift invariant.

`WorkflowContractSnapshot` and `WorkflowCompileRecord` are frozen dataclasses. Their nested
payloads must also be immutable:

- `normalized_contract` is immutable mapping plus tuples;
- compile-record sequence fields are tuples;
- no mutable dict/list payloads are exposed from the compile record.

---

## 12. Validation Split

Snapshot validation is the single graph-free validation path. Compile performs
graph-context validation only after snapshotting.

### Snapshot-time failures

Snapshot rejects malformed graph-free artifacts before fingerprinting.

Type failures use `TypeError`:

- contract fields with wrong container types;
- non-mapping descriptor, metadata, params, bind payloads, or bindings;
- non-string mapping keys;
- non-string binding param keys;
- non-string descriptor values;
- non-JSON-safe values;
- non-finite floats;
- `max_steps` as `bool`;
- unknown/non-step spec objects.

Value failures use `ValueError`:

- empty `workflow_id`;
- empty `WorkflowTemplateRef.expected_template_id`;
- `max_steps <= 0`;
- duplicate or empty `InitialNodeParams.node_id`;
- duplicate or empty `WorkflowNodeRule.node_id`;
- empty `rules`;
- empty `WorkflowNodeRule.steps_by_seen_count`;
- `ProducerStepSpec.node_id` empty or not equal to the enclosing rule node id;
- `VerifierStepSpec.verifier_node_id` empty or not equal to the enclosing rule node id;
- `VerifierStepSpec.source_node_id` empty;
- invalid `VerifierStepSpec.expected_outcome`;
- `BindStepSpec.node_id` empty or not equal to the enclosing rule node id;
- empty binding param keys;
- malformed or empty binding paths;
- empty `terminal_node_ids`;
- duplicate or empty terminal node ids;
- terminal/rule overlap;
- duplicate or empty `ExpectedNodeRef.node_id`;
- empty `ExpectedNodeRef.execution_ref`.

Graph-free unknown ids may still snapshot successfully when they are non-empty and
structurally coherent. Compile determines whether they fit the selected graph.

### Compile-time failures

Compile catches graph-world mismatches:

- template selector mismatch;
- selected template has no graph;
- unknown initial-param node ids;
- unknown workflow-rule node ids;
- unknown verifier source node ids;
- unknown terminal node ids;
- declared terminal node is not terminal;
- unknown expected-ref node ids;
- expected execution ref mismatch.

Compile may keep defensive checks already present in LM4W/LM4U, but the canonical
graph-free validation path is snapshot normalization.

---

## 13. Tests

Add one focused test file:

```text
mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py
```

The existing LM4W compiler tests and chain guard remain in place. LM4X does not add a new
offline stream proof.

### Golden repair contract

Use a distinct workflow id:

```python
workflow_id="lm4x_repair_contract"
```

Use familiar live-style repair payloads as offline data:

```python
{
    "code": "A = DefinitelyMissingSymbol;",
    "pins_in": [],
    "pins_out": ["A:double"],
    "name": "LM4XWorkflowContractFingerprint",
    "x": 350,
    "y": 1080,
}
```

Repair bind base params:

```python
{"code": "A = 42.0;", "mode": "body", "language": "csharp"}
```

Repair binding:

```python
{"guid": ("repair_anchor", "component_guid")}
```

Include small metadata so metadata participates in the golden fingerprint:

```python
metadata={
    "workflow_label": "LM4X repair contract",
    "trace": {"slice": "LM4X"},
}
```

Assert one golden 64-character SHA-256 fingerprint for the canonical repair contract.

### Snapshot behavior

Tests should assert:

- `snapshot_workflow_contract` does not call `select_template` by monkeypatching
  `select_template` to raise and proving snapshot still succeeds;
- snapshot schema equals `WORKFLOW_CONTRACT_SCHEMA`;
- snapshot workflow id mirrors normalized contract workflow id;
- selected normalized fields, not the full giant structure:
  - template descriptor and expected id;
  - `pins_out` normalized to tuple;
  - bind path normalized to tuple;
  - step tags and order, especially `bind` -> `producer`;
  - metadata normalized into the snapshot;
- nested immutable mapping mutation fails;
- repeated snapshots of equivalent-but-not-identical contracts are deterministic;
- mapping key reorder does not change fingerprint;
- list vs tuple value payloads do not change fingerprint;
- metadata value change changes fingerprint;
- rule order change changes fingerprint;
- `steps_by_seen_count` order change changes fingerprint;
- `metadata=None` and `metadata={}` are fingerprint-equivalent.

Do not assert canonical JSON text. Canonical JSON is internal-only.

### Compile record behavior

Tests should assert:

- scaffold includes `contract_snapshot` and `compile_record`;
- scaffold workflow id, snapshot workflow id, and record workflow id match;
- record schema and fingerprint match the snapshot;
- record provider id equals `CATALOG_CURRENT_STEP_PROVIDER_ID`;
- record compiler id and fingerprint algorithm match constants;
- record selected template id equals expected template id on success;
- `graph_node_ids == tuple(sorted(scaffold.graph.nodes))`;
- authored-order fields match normalized contract order:
  - initial param node ids;
  - rule node ids;
  - terminal node ids;
  - expected refs;
  - step kinds by rule;
- repeated compiles of the same contract produce equal compile records;
- `scaffold.metadata is scaffold.contract_snapshot.normalized_contract["metadata"]`;
- compile record does not include metadata, descriptor, param payloads, timestamps, or run
  fields.

### Validation behavior

Tests should prove structural failures fail through both `snapshot_workflow_contract` and
`compile_workflow_contract` because compile uses the same snapshot path:

- empty workflow id;
- bad descriptor keys/values;
- bad metadata;
- invalid `max_steps`, including `bool`;
- duplicate initial params, rules, terminals, and expected refs;
- empty `rules`;
- empty `steps_by_seen_count`;
- terminal/rule overlap;
- non-step spec;
- target mismatch for producer/verifier/bind;
- empty `VerifierStepSpec.source_node_id`;
- empty `ExpectedNodeRef.execution_ref`;
- invalid verifier expected outcome;
- invalid bind path.

Tests should also prove graph-context failures remain compile-only:

- unknown-but-non-empty node id snapshots successfully;
- compile fails when the selected graph lacks that node.

### Boundary guard

Add or update a scoped boundary guard for `plan_graph_workflow_contract.py`.

Allowed LM4X additions:

- `hashlib`;
- `json`;
- `CATALOG_CURRENT_STEP_PROVIDER_ID`.

Existing LM4W compile-time imports remain allowed:

- `CatalogCurrentStepProvider`;
- `NodeStepRule`;
- `ProducerStep`;
- `VerifierStep`;
- `BindStep`;
- `EXECUTION_PARAMS_KEY`;
- `initialize_graph`;
- `select_template`.

Still disallowed:

- LM4N/O/P/Q/R/S runtime ladder modules/functions;
- `run_current_step_stream`;
- `run_current_mapped_step`;
- `execute_mapped_step`;
- `map_accepted_proposal_to_step`;
- `revalidate_proposal`;
- `propose_next_node`;
- live Rhino/GH dispatch surfaces;
- model, server, dispatcher, or base agent surfaces;
- `apply_outcome` or terminal completion helpers;
- LM4G evaluation record builders.

---

## 14. Deliberate Non-Goals

LM4X does not add:

- JSON/YAML parsing, loading, dumping, or file acceptance;
- a public canonical JSON helper or canonical JSON string field;
- natural-language or user-intent compilation;
- OpenProse code or public OpenProse API terms;
- graph fingerprinting;
- template graph canonicalization;
- failed compile receipts;
- compile/run ledgers;
- timestamps or environment provenance;
- stream/provider/current-step metadata integration;
- producer expectations or evaluation records;
- live Rhino/GH tests;
- terminal completion;
- runtime authority changes.

The snapshot is an identity artifact. The compile record is a successful-compile receipt.
Neither one authorizes a next step, continuation, terminal application, or graph mutation.

---

## 15. Verification And Gates

Targeted deterministic tests:

```text
mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py
mcp_server/tests/test_plan_graph_workflow_contract.py
mcp_server/tests/test_plan_graph_workflow_contract_chain.py
```

Focused gate:

```text
LM4N-X PlanGraph-focused gate
```

Additional checks:

- `git diff --check`;
- production scope guard:
  - `plan_graph_workflow_contract.py`;
  - tiny provider id constant exposure in `plan_graph_current_step_provider.py`;
  - no runtime authority imports;
- no live Rhino/GH acceptance required;
- no `knowledge/gh/operations_knowledge.json` mutation;
- no `base_agent.py` drift.

Merge remains gated by explicit approval after review.
