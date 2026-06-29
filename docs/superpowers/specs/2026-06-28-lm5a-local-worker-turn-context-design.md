# LM5A - Local Worker Turn Context Design

**Date:** 2026-06-28
**Status:** Approved design for implementation planning
**Campaign:** Rook local/internal models north-star, LM5 entry slice
**Predecessor checkpoint:** `docs/superpowers/checkpoints/2026-06-28-lm4-phase-closeout.md`

---

## 1. Goal

LM5A introduces a deterministic worker-consumption boundary.

It packages the information a future local/internal worker is allowed to see for
one caller-declared workflow turn:

- workflow provenance and compile identity;
- current graph and current node facts;
- bounded current-step and supply history summaries;
- caller-pushed knowledge packets;
- caller-declared allowed action descriptors.

LM5A does **not** call a model. It does not route through RookChat, execute
tools, mutate a graph, select/remap/revalidate nodes, evaluate outcomes, parse a
worker response, or continue a stream. It defines the worker input contract only.

North-star fit:

```text
Rook-owned scaffold + graph snapshot + history + pushed knowledge + action vocabulary
-> LocalWorkerTurnContext
-> future bounded local/internal worker
```

The future worker receives facts, not authority handles.

---

## 2. Production Scope

Add one production module:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
```

Add one focused test file:

```text
mcp_server/tests/test_local_worker_turn_context.py
```

No package-level exports are added.

The module is an agent-layer adapter from LM4 artifacts into future-worker facts.
It is not a workflow compiler, stream runner, executor, RookChat component, model
harness, or dispatcher.

---

## 3. Public Surface

The module exports exactly:

```python
__all__ = (
    "LocalWorkerTurnContext",
    "WorkerWorkflowSummary",
    "WorkerGraphSummary",
    "WorkerNodeSummary",
    "WorkerHistorySummary",
    "WorkerStepTraceSummary",
    "WorkerSupplyTraceSummary",
    "WorkerKnowledgePacket",
    "WorkerAllowedAction",
    "build_local_worker_turn_context",
)
```

All public dataclasses are frozen:

```python
@dataclass(frozen=True)
class WorkerWorkflowSummary:
    workflow_id: str
    contract_schema: str
    contract_fingerprint: str
    compiler_id: str
    provider_id: str
    selected_template_id: str
    max_steps: int


@dataclass(frozen=True)
class WorkerGraphSummary:
    node_count: int
    node_ids: tuple[str, ...]
    ready_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]
    status_counts: Mapping[str, int]


@dataclass(frozen=True)
class WorkerNodeSummary:
    node_id: str
    intent: str
    role: str | None
    status: str
    execution_ref: str | None
    is_terminal: bool
    has_execution_params: bool
    memory_keys: tuple[str, ...]


@dataclass(frozen=True)
class WorkerStepTraceSummary:
    accepted_node_id: str | None
    execution_kind: str | None
    ran: bool
    failure: str | None


@dataclass(frozen=True)
class WorkerSupplyTraceSummary:
    decision: str | None
    reason: str | None
    selected_node_id: str | None
    has_envelope: bool


@dataclass(frozen=True)
class WorkerHistorySummary:
    current_step_count: int
    supply_count: int
    last_accepted_node_id: str | None
    last_execution_kind: str | None
    last_stop_reason: str | None
    recent_steps: tuple[WorkerStepTraceSummary, ...]
    recent_supplies: tuple[WorkerSupplyTraceSummary, ...]


@dataclass(frozen=True)
class WorkerKnowledgePacket:
    packet_id: str
    kind: str
    title: str | None
    content: Mapping[str, Any]


@dataclass(frozen=True)
class WorkerAllowedAction:
    action_id: str
    kind: str
    description: str
    input_schema: Mapping[str, Any]


@dataclass(frozen=True)
class LocalWorkerTurnContext:
    workflow: WorkerWorkflowSummary
    current_graph: WorkerGraphSummary
    current_node: WorkerNodeSummary | None
    history: WorkerHistorySummary
    knowledge: tuple[WorkerKnowledgePacket, ...]
    allowed_actions: tuple[WorkerAllowedAction, ...]
```

Builder:

```python
def build_local_worker_turn_context(
    scaffold: CompiledWorkflowScaffold,
    graph: PlanGraph,
    records: tuple[CurrentStepRecord, ...] | list[CurrentStepRecord],
    supply_records: tuple[EnvelopeSupplyRecord, ...] | list[EnvelopeSupplyRecord],
    *,
    current_node_id: str | None,
    knowledge: tuple[WorkerKnowledgePacket, ...] | list[WorkerKnowledgePacket],
    allowed_actions: tuple[WorkerAllowedAction, ...] | list[WorkerAllowedAction],
    history_limit: int = 5,
) -> LocalWorkerTurnContext:
    ...
```

The builder accepts canonical LM4 objects as inputs, but the returned context
contains no raw LM4 objects.

---

## 4. Input Ownership And Authority

### Scaffold

`scaffold` must be a `CompiledWorkflowScaffold`.

It supplies workflow identity, compile receipt fields, provider id, max-step
budget, and template anchor.

LM5A validates only visible scaffold identity consistency needed for the workflow
summary:

```text
scaffold.compile_record.workflow_id == scaffold.workflow_id
scaffold.compile_record.contract_fingerprint == scaffold.contract_snapshot.contract_fingerprint
scaffold.compile_record.contract_schema == scaffold.contract_snapshot.normalized_contract["schema"]
```

If any check fails, raise `ValueError`.

LM5A does not check `provider_id` against `CATALOG_CURRENT_STEP_PROVIDER_ID`.
Provider identity is reported as a fact, not policed as an implementation choice.

### Graph

`graph` must be a `PlanGraph`.

It may differ from `scaffold.graph`. After LM4S advances a stream, the current
graph is normally an advanced snapshot. LM5A must not require identity with the
original scaffold graph and must not try to prove they belong together.

LM5A does not check graph coverage against scaffold rules or terminal ids. It
summarizes the caller-provided current graph snapshot.

### Current Node

`current_node_id` is explicit caller-owned turn intent.

Semantics:

- `current_node_id is None` -> `context.current_node is None`;
- non-`str | None` `current_node_id` -> `TypeError`;
- `current_node_id == ""` -> `ValueError`;
- unknown `current_node_id` -> `ValueError`;
- existing node, any status -> summarize that node.

The builder must not require the node to be ready. Readiness is policy; LM5A
only summarizes facts.

The returned context has no separate `current_node_id` field. When present,
`context.current_node.node_id` is the node id.

### History

`records` and `supply_records` are caller-supplied history, not authority.

Validation is structural only:

- `records`: `list | tuple` of `CurrentStepRecord`, snapshotted to tuple;
- `supply_records`: `list | tuple` of `EnvelopeSupplyRecord`, snapshotted to tuple;
- `history_limit`: positive `int`, with `bool` rejected.

LM5A must not require:

- `len(supply_records) == len(records)` or `len(records) + 1`;
- supply/record mapping identity alignment;
- workflow provenance on every record;
- records corresponding to the provided graph;
- current node matching the last selected or accepted node.

Inconsistent but structurally valid histories are summarized, not adjudicated.

---

## 5. Summary Semantics

### Workflow Summary

`WorkerWorkflowSummary` is derived from `scaffold.compile_record` and
`scaffold.max_steps`:

```text
workflow_id = compile_record.workflow_id
contract_schema = compile_record.contract_schema
contract_fingerprint = compile_record.contract_fingerprint
compiler_id = compile_record.compiler_id
provider_id = compile_record.provider_id
selected_template_id = compile_record.selected_template_id
max_steps = scaffold.max_steps
```

Do not include the full normalized contract, full compile record, scaffold
metadata, graph node list, expected refs, rule specs, or compiled steps.

### Graph Summary

`WorkerGraphSummary` is an observational snapshot of the provided current graph:

```text
node_count = len(graph.nodes)
node_ids = sorted graph node ids
ready_node_ids = sorted ids whose node.status == "ready"
terminal_node_ids = sorted ids whose node.is_terminal is true
status_counts = immutable mapping of status string -> count
```

`ready_node_ids` is context only. It does not authorize the builder or future
worker to select a node.

No edges, full node metadata, graph memory payloads, graph mutation helpers, or
raw graph object are exposed.

### Node Summary

`WorkerNodeSummary` summarizes a caller-declared existing node:

```text
node_id = node.id
intent = node.intent
role = projection_role_for_node(node), normalized to str | None
status = node.status
execution_ref = node.execution_ref
is_terminal = bool(node.is_terminal)
has_execution_params = derived from node.metadata[EXECUTION_PARAMS_KEY]
memory_keys = sorted graph memory fact keys visible while preparing this node
```

Role derivation:

- import `projection_role_for_node` from `rook.learning.plan_graph_projection`;
- do not import `OUTCOME_PROJECTION_ROLE_KEY` unless implementation truly needs it;
- do not read `node.metadata["role"]`;
- do not infer role from node id;
- normalize the returned value to `str | None`.

Execution params derivation:

- import `EXECUTION_PARAMS_KEY` from `rook.agent.plan_graph_live`;
- `has_execution_params` is true iff `node.metadata` is a mapping,
  `EXECUTION_PARAMS_KEY` exists, and the value is a non-empty mapping;
- do not copy or expose the params payload.

Memory key derivation:

- use `graph.memory.facts`;
- if `graph.memory.facts` is not a mapping, raise `TypeError`;
- if any memory fact key is not a string, raise `TypeError`;
- expose sorted string keys;
- `memory_keys` means graph memory fact keys visible while preparing this node,
  not node-owned memory.

Do not expose:

- node metadata blob;
- metadata key list;
- execution params payload;
- memory values;
- `Step`, mapping, execution, record, evidence, or provider objects.

If `current_node_id is None`, no `WorkerNodeSummary` is produced and memory keys
are not surfaced elsewhere in LM5A.

### History Summary

`WorkerHistorySummary` includes full counts and bounded recent summaries:

```text
current_step_count = len(records)
supply_count = len(supply_records)
last_accepted_node_id = records[-1].accepted_node_id if records else None
last_execution_kind = records[-1].execution_kind if records else None
last_stop_reason = derived from the last supply record if present
recent_steps = last history_limit step summaries
recent_supplies = last history_limit supply summaries
```

`last_stop_reason` is not `CurrentStepStreamResult.stop_reason`, because the
builder does not receive a `CurrentStepStreamResult`. It is a last-supply clue:

```text
last.invalid_reason if present
else last.reason if present
else last.error_class if present
else None
```

`WorkerStepTraceSummary` is derived from flattened `CurrentStepRecord` fields:

```text
accepted_node_id = record.accepted_node_id
execution_kind = record.execution_kind
ran = record.ran
failure = record.execution_failure or record.mapping_failure
```

`WorkerSupplyTraceSummary` is derived from `EnvelopeSupplyRecord` fields:

```text
decision = record.decision
reason = record.invalid_reason or record.reason or record.error_class
selected_node_id = record.metadata["selected_node_id"] if metadata is a mapping and value is a string else None
has_envelope = record.envelope is not None
```

No native seam results, mappings, execution result payloads, envelopes, or
provider metadata blobs are copied into the worker context.

---

## 6. Knowledge Packets

Knowledge is caller-pushed. LM5A does not fetch, infer, rank, or schedule
knowledge.

`WorkerKnowledgePacket` validation:

- `packet_id`: non-empty string;
- `kind`: non-empty string;
- `title`: string or `None`;
- `content`: mapping with string keys and JSON-safe values;
- duplicate `packet_id`: `ValueError`.

`WorkerKnowledgePacket.__post_init__` validates these fields and replaces
`content` with a recursively frozen immutable snapshot. The builder snapshots
the `knowledge` sequence and checks duplicate `packet_id` values; it does not
need to re-freeze packet content that the public dataclass constructor already
validated.

Out of scope:

- knowledge-store fetching;
- KG query;
- memory lookup;
- relevance selection;
- automatic scheduled knowledge push.

LM5A proves the receiving shape, not retrieval.

---

## 7. Allowed Actions

Allowed actions are declarative descriptors only. They describe what a future
worker may talk about, not what it can run.

`WorkerAllowedAction` validation:

- `action_id`: non-empty string;
- `kind`: non-empty string;
- `description`: non-empty string;
- `input_schema`: mapping with string keys and JSON-safe values;
- duplicate `action_id`: `ValueError`.

`WorkerAllowedAction.__post_init__` validates these fields and replaces
`input_schema` with a recursively frozen immutable snapshot. The builder
snapshots the `allowed_actions` sequence and checks duplicate `action_id`
values; it does not need to re-freeze action schemas that the public dataclass
constructor already validated.

Out of scope:

- callables;
- MCP tool handles;
- execution refs;
- graph mutation permission;
- auto-execute or auto-continue flags;
- dispatcher integration.

---

## 8. JSON-Freezing And Immutability

LM5A uses a local private `_freeze_json_value(...)` helper. It must not import
LM4 private snapshot helpers.

Rules:

- mappings require string keys and return `types.MappingProxyType` around copied
  dictionaries;
- `list | tuple` values become tuples recursively;
- `str`, `bool`, `int`, finite `float`, and `None` are allowed;
- non-finite floats are rejected;
- arbitrary objects and callables are rejected.

Public mapping fields are typed as `Mapping[str, Any]`; the concrete immutable
mapping type is an implementation detail.

All public dataclasses are frozen. All sequence fields are tuples. Mapping fields
are immutable mapping proxies, and nested mappings/sequences are recursively
frozen. The returned `LocalWorkerTurnContext` must be detached from caller-owned
containers.

No serialization helper is added:

- no `to_payload`;
- no `to_json`;
- no prompt formatter;
- no token budgeter;
- no model-message rendering;
- no context fingerprint or context schema/id.

LM5A defines the Python worker-consumption contract only.

---

## 9. Error Taxonomy

Use built-in exceptions only.

Raise `TypeError` for wrong shapes or types:

- `scaffold` not `CompiledWorkflowScaffold`;
- `graph` not `PlanGraph`;
- `current_node_id` not `str | None`;
- `records` / `supply_records` not `list | tuple`;
- history item with wrong type;
- `knowledge` / `allowed_actions` not `list | tuple`;
- knowledge/action item with wrong type;
- JSON payload value unsupported;
- mapping keys not strings;
- `history_limit` not `int` or is `bool`;
- `title` not `str | None`;
- scalar dataclass fields with wrong type;
- `graph.memory.facts` malformed or with non-string keys.

Raise `ValueError` for invalid values:

- empty `current_node_id`;
- unknown `current_node_id`;
- `history_limit <= 0`;
- duplicate knowledge `packet_id`;
- empty knowledge `packet_id` / `kind`;
- duplicate action `action_id`;
- empty action `action_id` / `kind` / `description`;
- visible scaffold identity contradiction.

No custom exception class.

---

## 10. Import And Authority Boundary

Allowed production imports:

- `collections.abc.Mapping`;
- `dataclasses`;
- `math`;
- `types.MappingProxyType`;
- typing helpers;
- `CompiledWorkflowScaffold`;
- `CurrentStepRecord`;
- `EnvelopeSupplyRecord`;
- `EXECUTION_PARAMS_KEY`;
- `PlanGraph`;
- `projection_role_for_node`.

The production module must not import or call:

- `propose_next_node`;
- `map_accepted_proposal_to_step`;
- `revalidate_proposal`;
- `execute_mapped_step`;
- `run_current_mapped_step`;
- `run_current_step_stream`;
- `EnvelopeSupplyResult`;
- `CatalogCurrentStepProvider`;
- `WorkflowProvenanceEnvelopeSource`;
- `compile_workflow_contract`;
- `load_workflow_contract_payload`;
- `snapshot_workflow_contract`;
- `RookAgent`;
- `base_agent`;
- chat server, chat runner, prompt builder, model status, model profiles, or
  other RookChat surfaces;
- dispatcher or tool execution surfaces;
- live Rhino/GH runner surfaces;
- file IO, `Path`, or `open`;
- `json`, `json.loads`, `json.dumps`, YAML, OpenAI, litellm, or model provider
  imports.

Integration tests may import LM4 compiler/scaffold helpers. Production may not.

---

## 11. Tests

Create:

```text
mcp_server/tests/test_local_worker_turn_context.py
```

### Unit Coverage

Tests should cover:

- public `__all__` surface;
- all public dataclasses are frozen;
- workflow summary is derived from scaffold compile record and max steps;
- scaffold identity mismatches raise `ValueError`;
- graph may differ from `scaffold.graph`;
- wrong scaffold/graph types raise `TypeError`;
- `current_node_id is None` produces `current_node is None`;
- empty/unknown current node ids raise `ValueError`;
- existing non-ready node is summarized without refusal;
- node summary uses `intent`, `projection_role_for_node`, `EXECUTION_PARAMS_KEY`,
  `is_terminal`, and sorted graph memory keys;
- malformed memory facts or non-string memory keys raise `TypeError`;
- graph summary sorts node/ready/terminal ids and freezes `status_counts`;
- history validation is structural only;
- `history_limit` validation rejects bool, non-int, and `<= 0`;
- history counts reflect full histories while recent summaries are truncated;
- last supply reason derivation uses `invalid_reason`, then `reason`, then
  `error_class`;
- supply selected node id is read only from mapping metadata with string value;
- malformed supply metadata yields `selected_node_id is None`;
- knowledge packet validation and duplicate detection;
- allowed action validation and duplicate detection;
- knowledge/action JSON payloads are deeply frozen and detached from caller
  mutation;
- no raw canonical LM4 objects appear in context fields;
- AST/import boundary forbids runtime/model/file/JSON surfaces.

### Offline Integration Test

Include one small deterministic integration proof:

```text
RookWorkflowContract
-> compile_workflow_contract
-> build_local_worker_turn_context
```

The test may use the existing repair workflow contract fixture style and minimal
fake records if building full LM4S history is noisy. It should prove LM5A accepts
real `CompiledWorkflowScaffold` and `PlanGraph` shapes.

Assert:

- workflow summary fingerprint equals `scaffold.compile_record.contract_fingerprint`;
- current graph/current node/history summaries are worker-facing only;
- knowledge and allowed action payloads are frozen;
- no raw `PlanGraph`, scaffold, records, mappings, executions, envelopes, or
  providers appear in the returned context fields.

Do not add a live Rhino/GH test. Do not call a model. Do not touch RookChat.

---

## 12. Verification And Gates

Targeted:

```text
pytest mcp_server/tests/test_local_worker_turn_context.py -q
```

Nearby regression:

```text
pytest \
  mcp_server/tests/test_plan_graph_workflow_contract.py \
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py \
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py \
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py \
  mcp_server/tests/test_plan_graph_workflow_provenance.py \
  mcp_server/tests/test_local_worker_turn_context.py \
  -q
```

Focused gate:

```text
Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py'
```

plus the new local-worker context test file. The exact command can be pinned in
the implementation plan once file names are final.

Static:

- `git diff --check`;
- production diff is exactly `mcp_server/src/rook/agent/local_worker_turn_context.py`;
- no `base_agent.py`, chat panel, server, dispatcher, model, live Rhino/GH, or
  stream-runner changes;
- AST/import guard over `local_worker_turn_context.py` for banned runtime/model,
  file, JSON/YAML, compile/load/snapshot, selector/mapper/revalidator/executor,
  and stream-runner surfaces.

---

## 13. Deliberate Non-Goals

LM5A does not add:

- model calls;
- RookChat integration;
- worker persona/profile/model routing;
- prompt or message rendering;
- token budgeting;
- serialization helpers;
- context fingerprinting or turn receipts;
- response/action schema;
- action proposal parser;
- response validation;
- accept/reject policy;
- dispatch/tool execution;
- graph mutation;
- selector/revalidator/mapper/executor calls;
- stream running or continuation;
- knowledge retrieval or relevance selection;
- JSON/YAML/text/file loading;
- live Rhino/GH coverage.

LM5A defines only the deterministic, frozen, worker-facing input context.
