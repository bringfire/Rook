# LM4W - Workflow Contract Compile Design

**Date:** 2026-06-26
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push - declarative workflow contract
**Predecessors:** LM4N (#345) `propose_next_node` -> LM4O (#352) `revalidate_proposal` -> LM4P (#353) `map_accepted_proposal_to_step` -> LM4Q (#354) `execute_mapped_step` -> LM4R (#356) `run_current_mapped_step` -> LM4S (#357) `run_current_step_stream` -> LM4U (#365) `CatalogCurrentStepProvider` -> LM4V (#367) catalog provider live proof

---

## 1. Goal

LM4W adds the first declarative contract layer above the live-proven runtime scaffold.

The runtime spine now exists and has carried live load:

```text
LM4N propose
-> LM4O distrust/revalidate
-> LM4P translate
-> LM4Q execute
-> LM4R record
-> LM4S stream
-> LM4U provide current-step artifacts
-> LM4V prove the production provider live
```

LM4W does not make that runtime smarter. It gives the caller a Rook-native contract
artifact that compiles into the scaffold objects the runtime already trusts:

```text
RookWorkflowContract
-> compile_workflow_contract(...)
-> CompiledWorkflowScaffold
-> caller invokes run_current_step_stream(...)
```

The first contract payload is intentionally narrow: the known live repair workflow that
has been hand-authored through LM4T/LM4V. The new load-bearing question is whether that
workflow can be described as structured, JSON-shaped data and compiled into:

- a selected and initialized `PlanGraph`;
- initial execution params staged on named nodes;
- caller-authored `Step` objects;
- `NodeStepRule`s and a `CatalogCurrentStepProvider`;
- explicit terminal node ids;
- an explicit positive `max_steps` budget;
- copied observational metadata.

LM4W is a compile/validate slice. It does not execute.

---

## 2. Production Module

Add one agent-layer module:

```text
mcp_server/src/rook/agent/plan_graph_workflow_contract.py
```

The module belongs in the agent layer because it compiles workflow data into agent
runtime artifacts:

- LM4M `ProducerStep` / `VerifierStep` / `BindStep`;
- LM4U `NodeStepRule` / `CatalogCurrentStepProvider`;
- graph node `metadata[EXECUTION_PARAMS_KEY]`.

It may import learning-layer template seams:

- `select_template`;
- `initialize_graph`;
- `PlanGraph` types needed for validation.

It must not import or call:

- LM4N `propose_next_node`;
- LM4O `revalidate_proposal`;
- LM4P `map_accepted_proposal_to_step`;
- LM4Q `execute_mapped_step`;
- LM4R `run_current_mapped_step`;
- LM4S `run_current_step_stream`;
- LM4G producer record builders or `LiveProducerExpectation`;
- `RookAgent`, server, dispatcher, model, or MCP tool execution surfaces;
- terminal application seams such as `apply_outcome`.

The compiler prepares artifacts. A caller still invokes LM4S explicitly.

---

## 3. Public Contract Types

LM4W uses frozen dataclasses. They are Python-first, but JSON-safe by design. No file
loader or parser is introduced in this slice.

```python
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | Mapping[str, "JsonValue"] | Sequence["JsonValue"]

@dataclass(frozen=True)
class WorkflowTemplateRef:
    descriptor: Mapping[str, str]
    expected_template_id: str

@dataclass(frozen=True)
class InitialNodeParams:
    node_id: str
    execution_params: Mapping[str, Any]

@dataclass(frozen=True)
class ProducerStepSpec:
    node_id: str

@dataclass(frozen=True)
class VerifierStepSpec:
    verifier_node_id: str
    source_node_id: str
    expected_outcome: OutcomeStatus | None = None

@dataclass(frozen=True)
class BindStepSpec:
    node_id: str
    base_params: Mapping[str, Any]
    bindings: Mapping[str, tuple[str, ...]]

WorkflowStepSpec = ProducerStepSpec | VerifierStepSpec | BindStepSpec

@dataclass(frozen=True)
class WorkflowNodeRule:
    node_id: str
    steps_by_seen_count: tuple[WorkflowStepSpec, ...]

@dataclass(frozen=True)
class ExpectedNodeRef:
    node_id: str
    execution_ref: str

@dataclass(frozen=True)
class RookWorkflowContract:
    workflow_id: str
    template: WorkflowTemplateRef
    initial_params: tuple[InitialNodeParams, ...]
    rules: tuple[WorkflowNodeRule, ...]
    terminal_node_ids: tuple[str, ...]
    expected_refs: tuple[ExpectedNodeRef, ...]
    max_steps: int
    metadata: Mapping[str, Any] | None = None

@dataclass(frozen=True)
class CompiledWorkflowScaffold:
    workflow_id: str
    graph: PlanGraph
    provider: CatalogCurrentStepProvider
    max_steps: int
    metadata: Mapping[str, Any]
    rules: tuple[NodeStepRule, ...]
    steps: tuple[Step, ...]
```

`CompiledWorkflowScaffold` is a named bundle, not an executor. It is the return value of:

```python
def compile_workflow_contract(contract: RookWorkflowContract) -> CompiledWorkflowScaffold:
    ...
```

The `steps` tuple is audit/convenience only; the executable copy is already embedded in
the compiled `NodeStepRule`s and provider.

---

## 4. Compile Flow

`compile_workflow_contract(...)` performs the following steps in order:

1. Validate and snapshot JSON-shaped contract fields.
2. Call `select_template(contract.template.descriptor)`.
3. Require `selection.selected_template_id == contract.template.expected_template_id`.
   The actual selector field is `TemplateSelection.selected_template_id`; LM4W must not
   use a guessed alias such as `template_id` or `template_name`.
4. Require `selection.graph is not None`.
5. Call `initialize_graph(selection.graph)`.
6. Validate and assert `ExpectedNodeRef`s against the initialized graph. Expected refs
   are assertions only; the compiler never sets or overrides `execution_ref`.
7. Validate and stage `InitialNodeParams` into
   `graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY]`.
8. Compile `WorkflowNodeRule`s into `NodeStepRule`s:
   - `ProducerStepSpec` -> `ProducerStep`;
   - `VerifierStepSpec` -> `VerifierStep`;
   - `BindStepSpec` -> `BindStep`.
9. Validate terminal node ids and create the `CatalogCurrentStepProvider`.
10. Return `CompiledWorkflowScaffold`.

The compiler does not call the selector/runtime ladder. In particular, it does not call
LM4N/LM4O/LM4P/LM4Q/LM4R/LM4S, and it does not inspect live Grasshopper/Rhino state.

---

## 5. Snapshot Contract

LM4W must make caller mutation harmless. All JSON-shaped contract payloads are validated
and snapshotted before they are used to build runtime artifacts.

The snapshot policy is explicit:

- mappings require string keys;
- mappings are copied into immutable mapping views for compiled audit fields where the
  runtime does not require a plain dict;
- lists and tuples are normalized to tuples;
- JSON scalar values (`str`, `int`, `float`, `bool`, `None`) are preserved;
- sets, frozensets, callables, arbitrary objects, non-string mapping keys, and
  non-copyable values are rejected;
- `bool` remains a boolean, not an integer special case.

This policy applies to:

- `WorkflowTemplateRef.descriptor` (string-keyed and string-valued for the current
  `select_template` API);
- `RookWorkflowContract.metadata`;
- `InitialNodeParams.execution_params`;
- `BindStepSpec.base_params`;
- `BindStepSpec.bindings`.

When the compiler writes node `execution_params` into the graph, it writes a fresh plain
dict/list-free JSON-shaped tree derived from the validated snapshot. This preserves the
existing execution-param convention while still preventing later caller mutation from
affecting the compiled graph. For compiled metadata and bind payloads, LM4W should follow
the LM4U precedent: immutable mapping views and tuple-normalized sequences.

---

## 6. Validation Rules

LM4W validates only the contract entries it declares. It does not attempt total graph
coverage or reachability proof.

### Workflow identity and budget

- `workflow_id` must be a non-empty string.
- `max_steps` must be an `int`; non-int raises `TypeError`.
- `bool` is explicitly rejected for `max_steps` even though Python treats `bool` as an
  `int`; `max_steps=True` and `max_steps=False` raise `TypeError`.
- `max_steps <= 0` raises `ValueError`.
- There is no default and no unbounded mode.
- The compiler does not derive `max_steps` from rule count, graph size, or terminal ids.

### Template reference

- `descriptor` must be a JSON-safe mapping with string keys and string values. The
  current `select_template` API is `Mapping[str, str]`, and LM4W does not add a richer
  descriptor interpreter.
- `expected_template_id` must be a non-empty string.
- `select_template` must select exactly that id via
  `TemplateSelection.selected_template_id`.
- A different selected id, no match, ambiguous match, or `graph is None` raises
  `ValueError`.

### Initial execution params

- duplicate `InitialNodeParams.node_id` raises `ValueError`;
- empty `node_id` raises `ValueError`;
- unknown `node_id` raises `ValueError`;
- non-mapping `execution_params` raises `TypeError`;
- non-JSON-safe params raise `TypeError`;
- params are copied into the initialized graph;
- the compiler never fabricates missing params or infers defaults.

### Step specs and rules

- duplicate `WorkflowNodeRule.node_id` raises `ValueError`;
- empty `node_id` raises `ValueError`;
- unknown `node_id` raises `ValueError`;
- empty `steps_by_seen_count` raises `ValueError`;
- non-step-spec entries raise `TypeError`;
- every step spec must target its rule node:
  - `ProducerStepSpec.node_id == rule.node_id`;
  - `VerifierStepSpec.verifier_node_id == rule.node_id`;
  - `BindStepSpec.node_id == rule.node_id`;
- `VerifierStepSpec.source_node_id` must be non-empty and present in the initialized
  graph;
- `VerifierStepSpec.expected_outcome` may be `None` or a valid `OutcomeStatus`;
- `BindStepSpec.base_params` and `bindings` must be JSON-safe mappings;
- compiled `BindStep.bindings` paths are tuples of non-empty strings.

### Terminal node ids

- at least one terminal node id is required for LM4W;
- empty terminal ids raise `ValueError`;
- duplicate terminal ids raise `ValueError`;
- unknown terminal ids raise `ValueError`;
- each declared terminal node must be terminal in the initialized graph;
- a terminal node id may not also have a `WorkflowNodeRule`;
- terminal ids compile into `CatalogCurrentStepProvider.terminal_node_ids`;
- the compiler never constructs a `NodeOutcome` or applies terminal completion.

### Expected execution refs

- duplicate `ExpectedNodeRef.node_id` raises `ValueError`;
- empty node id or ref raises `ValueError`;
- unknown node id raises `ValueError`;
- mismatch between `graph.nodes[node_id].execution_ref` and the expected ref raises
  `ValueError`;
- refs are asserted only, never set.

### Metadata

- metadata is optional and observational only;
- metadata must be JSON-safe;
- metadata is snapshotted into `CompiledWorkflowScaffold.metadata`;
- metadata must not affect template selection, params, rule compilation, terminal policy,
  max-step behavior, or execution.

---

## 7. Deliberate Non-Goals

LM4W does not add:

- YAML/JSON parsing;
- file loading;
- schema migrations;
- OpenProse/Forme/Reactor integration;
- natural-language compilation;
- role/metadata inference;
- graph traversal or total coverage validation;
- producer expectation/evaluation records;
- LM4G record building;
- LM4S execution;
- live Rhino/GH checks;
- terminal `done` application;
- scheduler behavior.

If a compiled workflow later encounters a ready non-terminal node with no provider rule,
that remains an LM4U/LM4S runtime audit event (`provider_invalid`). LM4W is not a static
proof that every possible graph path is covered.

---

## 8. Tests

LM4W should add unit tests for the compiler and one offline chain guard.

### Unit tests

Cover successful compilation of the repair contract plus validation failures:

- template selection mismatch / no graph;
- duplicate, empty, unknown initial-param node ids;
- non-mapping or non-JSON-safe initial params;
- duplicate, empty, unknown workflow-rule node ids;
- empty step tuple;
- non-step-spec entry;
- producer/verifier/bind target mismatch;
- empty or unknown verifier source node id;
- invalid verifier expected outcome;
- non-JSON-safe bind payload or invalid binding path;
- missing, duplicate, unknown, or rule-overlapping terminal ids;
- non-terminal declared as terminal;
- duplicate, empty, unknown, and mismatched expected refs;
- expected-ref override is not performed;
- non-int, bool, and non-positive `max_steps`;
- non-JSON-safe metadata;
- snapshot independence for descriptor, metadata, initial params, and bind payloads;
- imported-boundary / AST guard: no LM4N/O/P/Q/R/S runtime calls, no LM4G record builders,
  no dispatcher/server/model imports, no `apply_outcome`.

### Offline chain guard

Build the known repair workflow as a `RookWorkflowContract`, compile it, and run the
compiled scaffold through LM4S with an offline fake producer runner.

The fake producer runner must advance the graph through `apply_producer_result`, not
return the same graph, so LM4S does not stop on `graph_not_advanced`.

Expected trace:

```text
create_script           -> producer
verify_create           -> verifier
repair_same_component   -> bind
repair_same_component   -> producer
verify_repair           -> verifier
done                    -> provider HALT, non-executed
```

The repair contract fixture should include:

- descriptor selecting the repair template;
- `expected_template_id` equal to the selected template id;
- initial create params using the declared `gh_create_csharp_script:v1` path;
- expected refs:
  - `create_script == "gh_create_csharp_script:v1"`;
  - `repair_same_component == "gh_update_script:v1"`;
- `WorkflowNodeRule("repair_same_component", (BindStepSpec(...), ProducerStepSpec(...)))`;
- `terminal_node_ids=("done",)`;
- `max_steps=6`.

The guard asserts:

- exact executed trace and final provider halt;
- compiled provider is a `CatalogCurrentStepProvider`;
- compiled `max_steps` is used;
- stream reaches `done` ready but LM4W/LM4S do not apply terminal completion.

No live test is added in LM4W. LM4V already proved the production provider under live
Rhino/Grasshopper load. LM4W's novelty is contract compilation.

---

## 9. Process And Gates

Whole-branch scope:

- one spec;
- one plan;
- one production module: `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`;
- compiler unit tests;
- one offline chain guard.

Verification:

- focused PlanGraph gate including LM4N-W tests;
- targeted compiler tests;
- no live Rhino requirement;
- `git diff --check`;
- production diff contains exactly the one new workflow-contract module;
- `base_agent.py` byte-stable;
- no `knowledge/gh/operations_knowledge.json` mutation.

Merge remains gated by explicit approval after review.
