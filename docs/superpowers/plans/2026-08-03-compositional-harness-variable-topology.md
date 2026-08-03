# Compositional Harness Slice 1: Variable Grasshopper Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for Inline Execution. Keep one coder context, execute task-by-task, and stop at every mandatory independent review gate. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admit one bounded Planner-authored Grasshopper semantic graph, deterministically lower its complete topology into one existing `gh_edit` batch, execute exactly one snapshot and at most one edit, and prove exact structural materialization through existing Grasshopper identities and PlanGraph state.

**Architecture:** Add three private agent-layer modules: a strict raw-JSON semantic graph contract with one five-entry compiler tuple, a deterministic epoch-free compiler, and a fixed `create_edit -> verify_edit -> done` runner. The runner reuses the existing `T*`, `C*`, instance-GUID, `gh_snapshot`, `gh_edit`, PlanGraph reducer, selector/mapping, and native record boundaries. A separately authorized static snapshot qualification is a hard prerequisite; no production implementation begins until that fixture independently agrees with every regular-component identity/port contract and the slider identity/range/value shape. The slider output port remains an explicit code-owned special-lowering convention because the existing simple-parameter snapshot shape does not expose ports.

**Tech Stack:** Python 3.12, frozen dataclasses, standard-library strict JSON decoding and canonical serialization, existing Rook `PlanGraph` reducers/selectors/records, existing `ToolDispatcher` callable shape, existing `gh_snapshot` and `gh_edit` contracts, pytest, PowerShell, Git.

## Global Constraints

- Execute against [the approved specification](../specs/2026-08-02-compositional-harness-variable-topology-design.md).
- Preserve the current stacked branch. Before execution, require the Slice 0 audit head `65108bcbd00f572dc65203d39ecb8890dbd5c98f` to be reachable from `origin/main`; do not rebase merely because `main` gained that merge.
- The truthful audit baseline remains `93fe02e58836934edf836c13a3a92439328616b8`; do not rewrite it.
- Task 0 requires fresh, separate authorization for one read-only Grasshopper snapshot. No production task may begin before Task 0 is independently approved.
- Outside that single authorized qualification call, implementation and review make no provider, Worker, Rhino, Grasshopper, readiness, discovery, or mutation contact.
- Slice 1 is Grasshopper-only and deterministic: one Planner call, zero Worker calls, at most one `gh_snapshot`, at most one `gh_edit`, no retry, no resnapshot, no fallback, no repair, no cleanup, and no second verification call.
- The semantic graph describes what to build. The execution `PlanGraph` describes only `create_edit -> verify_edit -> done`.
- The Planner authors semantic primitive names, node-local symbols, slider parameters, and semantic edges. It never authors Grasshopper GUIDs, pin indices, access metadata, layout, epochs, `T*` IDs, `C*` IDs, instance GUIDs, PlanGraph structure, or execution rules.
- The compiler tuple contains only `number_slider`, `series`, `construct_point`, `polyline`, and `square_grid`; it is private immutable data, not a registry or plugin API.
- Production contains no witness names, witness intent strings, expected witness node counts, or witness-shape branches.
- Reuse existing `gh_edit` identity machinery. The only new correlation is ephemeral `semantic node ID -> existing T ID -> returned C ID / instance GUID`.
- Do not modify `recipe_to_edit()`, v2 recipes, the knowledge store, DSPy, Worker modules, Chat/UI, native or managed Grasshopper handlers, `gh_snapshot`/`gh_edit` schemas, tool registration, or product surfaces.
- Do not add a universal IR, catalog loader, visitor framework, type-inference system, subgraphs, mixed Rhino/GH operations, output-value verification, dataset manager, recorder, archive, checksum, fingerprint, attempt identity, or publication workflow.
- Strict JSON text is the untrusted boundary. Use compact table-driven tests over real JSON strings and causal fake tool responses; do not add carrier-authenticity, Python-subclass, source-provenance, or exhaustive mutation machinery.
- Expected Planner, graph-admission, snapshot, edit, and verification stops return one bounded ephemeral result. Impossible tuple/lowerer contradictions raise.
- Use `apply_patch` for file edits. Add no dependency.

---

## Planned File Surface

### Qualification fixture

- Create `mcp_server/tests/fixtures/gh_semantic_graph_slice1_primitives_snapshot.json`
  - Exact contracted request and response from the one authorized `gh_snapshot` call.

### Production

- Create `mcp_server/src/rook/agent/semantic_graph.py`
  - Frozen graph and primitive-contract types.
  - One private five-entry primitive tuple.
  - Strict raw JSON loader and semantic prompt/schema projection.
- Create `mcp_server/src/rook/agent/semantic_graph_compiler.py`
  - Relational graph admission, canonicalization, cycle/depth analysis, deterministic layout, existing `T*` assignment, epoch-free lowering, and ephemeral correlations.
- Create `mcp_server/src/rook/agent/semantic_graph_runner.py`
  - One-call Planner adapter.
  - Fixed three-node execution PlanGraph.
  - One snapshot plus one edit composition.
  - Structural materialization verification and bounded result aggregation.

### Tests

- Create `mcp_server/tests/test_semantic_graph.py`
  - Qualification-to-tuple equality, raw JSON admission, field bounds, prompt/schema projection.
- Create `mcp_server/tests/test_semantic_graph_compiler.py`
  - Relational refusals, canonical lowering, layout, correlations, and non-witness compositions.
- Create `mcp_server/tests/test_semantic_graph_runner.py`
  - Planner boundary, exact call budgets, fixed PlanGraph records, causal edit evidence, correlation, and the two witnesses.

### Durable plan ledger

- Modify only this plan during execution to mark completed steps and record reviewed commits, commands, counts, and final HEAD.

No other file is in scope unless a focused failing test reveals a direct contradiction with an existing contracted seam. Stop for review before widening the file surface.

---

## Task 0: Independently Qualify the Five Primitive Contracts

**Files:**

- Create: `mcp_server/tests/fixtures/gh_semantic_graph_slice1_primitives_snapshot.json`
- Modify: this plan ledger only after capture/review

**Authorization:** This task is the only live step in the implementation plan. It requires a new explicit authorization after an operator has prepared the disposable canvas. It performs one read-only `gh_snapshot` call and zero mutation/model/Worker calls.

**Hard gate:** Do not create any production module or production test until the captured fixture passes the exact review below and an independent reviewer approves Task 0.

- [ ] **Step 1: Verify stack and lane before contact**

Run from the Slice 1 worktree:

```powershell
git fetch origin main
git status --short
git rev-parse HEAD
git rev-parse origin/main
git merge-base --is-ancestor 65108bcbd00f572dc65203d39ecb8890dbd5c98f origin/main
git diff --name-only 65108bcbd00f572dc65203d39ecb8890dbd5c98f...HEAD
```

Expected before execution:

- status is empty;
- the audit head is an ancestor of `origin/main`;
- the branch contains only the approved Slice 1 specification and this plan above the audit stack;
- no production/test fixture already exists.

If the audit is not merged, `origin/main` has unexpected conflicting drift, or the worktree is dirty, stop without contact.

- [ ] **Step 2: Obtain separate authorization and inspect the operator-prepared canvas**

Require the operator to state that a disposable Grasshopper document is active and contains exactly these five unwired objects:

```text
one Number Slider
one Series
one Construct Point
one Polyline
one Square Grid
```

Do not create, wire, move, rename, or inspect components through any mutation or discovery tool. The operator owns preparation. Obtain explicit authorization for exactly one `gh_snapshot` call.

- [ ] **Step 3: Capture exactly one existing contracted snapshot**

Invoke the existing `gh_snapshot` tool once with the exact request:

```json
{
  "include_data": false,
  "max_preview_items": 0
}
```

Make no other Rhino or Grasshopper call. Preserve the returned contracted value exactly in:

```json
{
  "request": {
    "include_data": false,
    "max_preview_items": 0
  },
  "response": <exact returned contracted response>
}
```

Write the fixture using `apply_patch`; do not generate it from candidate constants, a knowledge record, or a helper script.

- [ ] **Step 4: Review the physical snapshot before accepting the fixture**

Using read-only JSON inspection, require all of the following:

- response success is exact `true`;
- response data has an exact positive integer epoch;
- exactly five components are present and `flows` is exactly empty;
- the four regular components expose the exact candidate `componentGuid` values;
- every regular input/output exposes exact direction/index, `type`, `access`, and
  `optional` evidence;
- each regular component has exactly the fixed input/output count from the
  specification and no unexpected variable pin;
- snapshot `name`/`nick` strings are retained but are not equated with semantic pin
  aliases;
- the slider exposes the existing snapshot special identity `NumberSlider` and a
  value payload with exact `type: "slider"` plus finite numeric `val`, `min`, and
  `max` fields satisfying `min <= val <= max`;
- no placeholder or `BROKEN` entry appears; and
- ordinary component runtime warnings/errors are retained but ignored for metadata
  qualification, including a legitimate missing-input diagnostic on an unwired
  Polyline.

Compare the four regular components against this exact direction/index projection:

```text
series:         I0 start Number item optional
                I1 step Number item optional
                I2 count Integer item optional
                O0 values Number list
construct_point:I0 x Number item optional
                I1 y Number item optional
                I2 z Number item optional
                O0 point Point item
polyline:       I0 vertices Point list required
                I1 closed Boolean item optional
                O0 curve Curve item
square_grid:    I0 plane Plane item optional
                I1 cell_size Number item optional
                I2 extent_x Integer item optional
                I3 extent_y Integer item optional
                O0 cells Rectangle list
                O1 points Point list
```

The semantic names shown above are exact code-owned aliases; qualification locates
each snapshot pin through component GUID plus direction/index and does not require a
snapshot name match. Separately record:

```text
number_slider snapshot qualification: NumberSlider identity + slider range/value shape
number_slider compiler convention:     value -> O0 / Number / item
```

The second row is not snapshot-derived. If a regular-component field is missing or
disagrees, or the slider identity/range/value shape is absent, stop here. Do not
weaken the comparison, query knowledge, call another tool, modify snapshot
production, or begin implementation. Report the exact missing/disagreeing field for
design review.

- [ ] **Step 5: Run fixture-only checks**

```powershell
uv run --project mcp_server python -c `
  "import json, pathlib; json.loads(pathlib.Path(r'mcp_server/tests/fixtures/gh_semantic_graph_slice1_primitives_snapshot.json').read_text(encoding='utf-8'))"
git diff --check
git status --short
```

Confirm the only uncommitted file is the fixture.

- [ ] **Step 6: Commit the qualification fixture only**

```powershell
git add mcp_server/tests/fixtures/gh_semantic_graph_slice1_primitives_snapshot.json
git commit -m "test(agent): qualify slice1 grasshopper primitives"
git status --short
```

- [ ] **Step 7: Mandatory independent qualification review stop**

The reviewer must independently inspect the exact fixture fields against specification section 6 and confirm:

- one snapshot, no mutation evidence;
- exact five-component/no-wire scope;
- all four regular GUIDs and every regular pin direction/index/type/access/optionality
  row;
- slider `NumberSlider` identity and finite range/value shape;
- code-owned slider `value -> O0 / Number / item` convention clearly separated from
  snapshot evidence;
- no missing or unexpected regular-component pins;
- runtime diagnostics ignored while placeholder/`BROKEN` entries refuse;
- fixture independence from the prospective tuple.

Record the approved fixture commit in this plan. **Do not start Task 1 before approval.**

---

## Task 1: Strict Semantic Graph Contract and Qualified Primitive Tuple

**Files:**

- Create: `mcp_server/src/rook/agent/semantic_graph.py`
- Create: `mcp_server/tests/test_semantic_graph.py`
- Read: `mcp_server/tests/fixtures/gh_semantic_graph_slice1_primitives_snapshot.json`

**Interfaces:**

```python
load_semantic_graph(raw_response: str) -> SemanticGraphLoadResult
build_semantic_graph_response_schema() -> dict[str, object]
semantic_primitive_prompt_projection() -> tuple[dict[str, object], ...]
```

The loader owns raw JSON decoding. The fixture is read only by tests; production never reads it.

- [ ] **Step 1: Create an importable behavioral skeleton**

Create `semantic_graph.py` with the module constants, frozen dataclass declarations, an empty private tuple, and the three exact functions above raising `NotImplementedError`. Use these graph records:

```python
@dataclass(frozen=True, slots=True)
class SemanticGraphNode:
    id: str
    primitive: str
    parameters: tuple[tuple[str, object], ...]

@dataclass(frozen=True, slots=True)
class SemanticGraphEdge:
    from_node: str
    from_pin: str
    to_node: str
    to_pin: str

@dataclass(frozen=True, slots=True)
class SemanticGraph:
    schema: str
    nodes: tuple[SemanticGraphNode, ...]
    edges: tuple[SemanticGraphEdge, ...]

@dataclass(frozen=True, slots=True)
class SemanticGraphLoadResult:
    admitted: bool
    graph: SemanticGraph | None
    failure: str | None
    reason: str
```

Primitive/pin entries remain frozen inert data. Do not add callbacks, inheritance, registry lookup, or per-primitive classes.

- [ ] **Step 2: Write the fixture-to-tuple RED**

In `test_semantic_graph.py`, load the static fixture directly with standard JSON, project only its existing component/pin fields, and compare those fixture-owned facts with the production `_PRIMITIVES` tuple. The test must prove:

- regular `componentGuid` values match after one code-owned lowercase normalization;
- regular pins match by component GUID plus direction/index, then exact type/access/optionality;
- semantic aliases are not compared with snapshot `name` or `nick` strings;
- slider identity is `NumberSlider`, its range/value payload has the contracted
  finite numeric shape, and lowering kind is `slider`;
- the separate code-owned slider `value -> O0 / Number / item` convention is exact;
- every input has `max_connections == 1`;
- no production fixture read occurs (AST/import assertion: `semantic_graph.py` does not reference `tests`, `fixtures`, `Path`, or file I/O).

Run:

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph.py -k qualified_fixture
```

Expected RED: the private primitive tuple is empty or unimplemented, not a collection failure.

- [ ] **Step 3: Add table-driven raw JSON loader REDs**

Add a smallest valid graph and compact parameterized cases for:

- response not an exact built-in string;
- more than 65,536 UTF-8 bytes or invalid UTF-8 encoding through an unencodable surrogate;
- malformed JSON, duplicate keys, nonfinite numbers, exponent overflow, oversized integer token, trailing content, markdown fences, and non-object root;
- unknown/missing root, node, edge, or parameter keys;
- schema other than exact `rook.gh_semantic_graph:v1`;
- 0 or 17 nodes, 25 edges;
- node ID outside `[a-z][a-z0-9_]{0,47}`;
- duplicate node IDs and duplicate exact edges;
- unknown primitive and unknown parameter;
- non-exact JSON scalar types, including booleans in numeric fields;
- slider label blank, over 64 characters, or over 256 UTF-8 bytes;
- nonfinite/out-of-range slider values and `minimum > initial` or `initial > maximum`.

Assert every expected refusal is a typed `SemanticGraphLoadResult(admitted=False, graph=None, ...)`; no parser error escapes.

- [ ] **Step 4: Add schema and semantic prompt projection REDs**

Require a fresh JSON schema mapping on every call with:

- closed root/node/edge/slider-parameter shapes;
- exact schema constant;
- node/edge count bounds;
- no `guid`, pin index, access metadata, layout, epoch, `T*`, `C*`, PlanGraph, witness name, witness topology, knowledge, Worker, or expected graph.

Require `semantic_primitive_prompt_projection()` to contain only Planner-facing primitive names, semantic pins, required/unconnected meaning, closed slider fields, and element compatibility guidance. It must not expose GUIDs, indices, layout, or lowering kinds.

- [ ] **Step 5: Run the complete Task 1 RED**

```powershell
uv run --project mcp_server pytest -q mcp_server/tests/test_semantic_graph.py
```

Expected RED: the skeleton functions are unimplemented.

- [ ] **Step 6: Implement the private tuple and strict loader**

Implement exactly five qualified entries. Parse with `json.JSONDecoder` using:

- `object_pairs_hook` that rejects duplicate keys;
- `parse_constant` that rejects `NaN`, `Infinity`, and `-Infinity`;
- a finite `parse_float` hook;
- residual parser `ValueError` mapped to invalid JSON;
- `raw_decode` plus an exact trailing-whitespace check.

Perform closed-key/type/bound validation before constructing frozen nodes and edges. Store parameters as name-sorted tuples so downstream code never depends on source mapping order. Do not trim, coerce, repair, extract markdown, or accept aliases.

- [ ] **Step 7: Implement fresh Planner-facing projections**

Build the response schema and semantic prompt tuple afresh from the code-owned primitive data, while explicitly omitting execution-owned fields. Do not cache a mutable mapping.

- [ ] **Step 8: Run Task 1 GREEN and adjacent parser regression**

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph.py `
  mcp_server/tests/test_minimal_intent_worker_integration.py
uv run --project mcp_server python -m compileall -q `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/tests/test_semantic_graph.py
git diff --check
```

- [ ] **Step 9: Commit Task 1**

```powershell
git add `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/tests/test_semantic_graph.py
git commit -m "feat(agent): admit bounded semantic gh graphs"
git status --short
```

- [ ] **Step 10: Review gate**

Require review of the raw-string ownership, fixture equality, closed vocabulary, and absence of execution identities in the Planner projection before Task 2.

---

## Task 2: Deterministic Canonical Compiler and Epoch-Free Edit Plan

**Files:**

- Create: `mcp_server/src/rook/agent/semantic_graph_compiler.py`
- Create: `mcp_server/tests/test_semantic_graph_compiler.py`
- Read: `mcp_server/src/rook/agent/semantic_graph.py`

**Interfaces:**

```python
compile_semantic_graph(graph: SemanticGraph) -> SemanticGraphCompileResult
materialize_gh_edit_request(plan: EpochFreeEditPlan, epoch: int) -> dict[str, object]
```

`SemanticGraphCompileResult` is either an admitted canonical plan or one expected `graph_admission` refusal. Once admitted, lowering is total; an impossible code-owned lowering kind raises.

- [ ] **Step 1: Create an importable behavioral skeleton**

Declare frozen records for:

- `CanonicalSemanticGraph`;
- one narrow immutable create instruction;
- `EpochFreeEditPlan` containing create instructions, flow strings, semantic-node-to-T pairs, semantic-edge-to-flow pairs, and canonical graph JSON;
- `SemanticGraphCompileResult` with `admitted`, optional plan, failure, and reason.

Leave `compile_semantic_graph()` and `materialize_gh_edit_request()` as behavioral `NotImplementedError` skeletons.

- [ ] **Step 2: Write relational admission REDs**

Load real JSON strings through `load_semantic_graph()`, then compile them. Parameterize:

- edge references unknown source/target node;
- source pin or target pin unknown or wrong case;
- edge direction reversed by selecting input as source or output as target;
- incompatible element types;
- second connection into any input;
- an unconnected required input, including `polyline.vertices`;
- every self-edge;
- two-node and longer cycles;
- slider connected to `series.count` or square-grid extents with nonintegral, below-1, or above-100 initial value.
- a non-slider Number source such as `series.values` connected to another
  `series.count`; the narrow Number-to-Integer exception belongs only to
  `number_slider`.

Do not require source/target access equality. Add positive tests for `series.values (Number/list) -> construct_point.x (Number/item)` and `square_grid.points (Point/list) -> polyline.vertices (Point/list)` to prove Grasshopper-native data matching remains runtime-owned.

- [ ] **Step 3: Write canonicalization and lowering REDs**

Create two JSON graphs that differ only in node, edge, and parameter source order. Require exact equality of:

- canonical graph JSON bytes;
- nodes sorted by ID;
- edges sorted by `(from_node, from_pin, to_node, to_pin)`;
- name-sorted parameter objects;
- semantic node-to-T mapping;
- create instructions;
- connect strings.

Pin:

```text
canonical node order -> T1, T2, ...
topological depth    -> x coordinate
node ID tie-break    -> y coordinate within a depth
```

Use one fixed code-owned origin and spacing constants. Renaming a node while consistently updating its edges may alter canonical identity/tie-breaking but never primitive meaning.

Require exact existing flow syntax such as `T1.O0>T2.I1` and exact existing creator shapes:

- regular component: `temp_id`, `guid`, `pos`;
- slider: `temp_id`, `type: slider`, `nick`, `min`, `max`, `value`, `pos`.

The epoch-free plan must contain no `epoch`, `C*` ID, instance GUID, delete, disconnect, update, set-values, group, or witness metadata.

- [ ] **Step 4: Add compositional non-witness REDs**

Require both legal graphs to compile without production special cases:

```text
number_slider.value -> construct_point.x
number_slider.value -> square_grid.cell_size
```

Add an AST/string guard proving production contains no witness intent, `point_row`, expected witness node count, or hard-coded witness topology.

- [ ] **Step 5: Add internal-contradiction RED**

In one focused test, substitute an internal primitive entry with an unknown code-owned lowering kind and assert `compile_semantic_graph()` raises `RuntimeError`. Do not express `lowering_kind` in Planner JSON or the public schema, and do not map the contradiction to graph admission.

- [ ] **Step 6: Run Task 2 RED**

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph.py `
  mcp_server/tests/test_semantic_graph_compiler.py
```

- [ ] **Step 7: Implement relational validation and canonical lowering**

Implement with direct dictionaries/sets and one deterministic topological sort. Do not add a generic graph framework or general list/tree inference. Compute depth during cycle analysis and use node ID only as the within-depth tie-break.

Return ordinary graph-admission refusals for Planner-controlled invalidity. Raise only when qualified internal tuple data cannot lower through `slider` or `component_guid`.

- [ ] **Step 8: Materialize a fresh final edit request only after epoch admission**

`materialize_gh_edit_request()` must require an exact positive built-in integer epoch and return a fresh mutable mapping:

```python
{
    "epoch": epoch,
    "create": [...],
    "connect": [...],
}
```

The function must not mutate the epoch-free plan or retain caller-owned mutable containers.

- [ ] **Step 9: Run Task 2 GREEN**

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph.py `
  mcp_server/tests/test_semantic_graph_compiler.py `
  mcp_server/tests/test_gh_edit_contract.py `
  mcp_server/tests/test_recipe_extraction.py
uv run --project mcp_server python -m compileall -q `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/tests/test_semantic_graph_compiler.py
git diff --check
```

- [ ] **Step 10: Commit Task 2**

```powershell
git add `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/tests/test_semantic_graph_compiler.py
git commit -m "feat(agent): lower semantic gh graphs deterministically"
git status --short
```

- [ ] **Step 11: Review gate**

Review must confirm arbitrary valid composition over the five primitives, no witness templates, no new ID family, exact `T*` reuse, total post-admission lowering, and no epoch before materialization.

---

## Task 3: One-Call Planner Boundary and Fixed Execution Graph

**Files:**

- Create: `mcp_server/src/rook/agent/semantic_graph_runner.py`
- Create: `mcp_server/tests/test_semantic_graph_runner.py`
- Read: `mcp_server/src/rook/agent/minimal_intent_worker_integration.py`
- Read: `mcp_server/src/rook/learning/plan_graph.py`
- Read: `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`

**Interfaces:**

```python
class SemanticGraphPlannerTransport(Protocol):
    def send(self, prompt_artifact: dict[str, object]) -> str: ...

class SemanticGraphPlannerAdapter:
    def produce(self, intent: str) -> SemanticGraphPlannerRecord: ...

async def run_semantic_graph_transaction(
    intent: str,
    planner_adapter: SemanticGraphPlannerAdapter,
    tool_executor: Callable[[str, dict[str, object]], object],
) -> SemanticGraphExecutionResult: ...
```

Task 3 implements the adapter, result/stage types, and fixed graph builder. Snapshot/edit behavior remains a behavioral skeleton until Task 4.

- [ ] **Step 1: Create the runner skeleton**

Declare:

- exact intent bounds `16,384` UTF-8 bytes;
- immutable `SemanticGraphPromptSnapshot`;
- closed `SemanticGraphPlannerRecord` states `response_received` and `transport_failed`;
- `SemanticGraphExecutionResult` with optional fields by reached stage;
- terminal stages `planner`, `graph_admission`, `snapshot`, `edit`, `verification`, `terminal`;
- private `_build_execution_graph(edit_request)`;
- private unimplemented `_execute_compiled_plan(...)` used only after compilation.

Aggregate validation is immediate shape/stage presence only. It does not replay Planner, loader, compiler, tool, graph, or mapping lineage.

- [ ] **Step 2: Write Planner request and one-call REDs**

Using a fake transport through the exact adapter, prove:

- intent must be exact built-in, nonblank, and within 16,384 UTF-8 bytes before prompt rendering/call;
- the prompt contains the exact intent and fresh output schema;
- the prompt contains the semantic tuple projection;
- the prompt excludes all four regular GUIDs, pin indices, access metadata, layout constants, epoch, `T1`, `C1`, PlanGraph, both witness intents/topologies, knowledge, Worker, and expected graph;
- one immutable snapshot is retained while a fresh mutable request is sent;
- exactly one transport call occurs;
- ordinary transport exceptions produce `planner` with zero tool calls;
- the exact raw returned string is retained without decode, repair, coercion, or markdown extraction.

- [ ] **Step 3: Write raw-response ownership and graph-admission REDs**

Call `run_semantic_graph_transaction()` with raw duplicate-key, trailing-content, non-object, unknown-primitive, cyclic, and invalid-edge responses. Require:

- exactly one Planner call;
- `load_semantic_graph()` receives the raw string unchanged;
- stage is `graph_admission`;
- zero snapshot/edit calls;
- no result contains a graph or plan when its owning admission stage failed.

Add one valid raw graph and expect the `_execute_compiled_plan()` behavioral skeleton to raise `NotImplementedError`; this proves Planner/load/compiler code was actually crossed before Task 4.

- [ ] **Step 4: Write exact fixed PlanGraph RED**

Require `_build_execution_graph()` to produce only:

```text
create_edit --requires--> verify_edit --requires--> done
```

Pin:

- `create_edit` starts ready and owns `gh_edit:v1` plus the final request;
- `verify_edit` starts pending and has no execution reference or tool parameters;
- `done` is terminal, pending, and has no execution reference;
- no semantic node becomes a PlanGraph node;
- both edges are exact `requires` edges;
- the original request is copied rather than mutated.

- [ ] **Step 5: Run Task 3 RED**

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph_runner.py -k "planner or graph_admission or execution_graph"
```

- [ ] **Step 6: Implement the Planner adapter and pre-execution root**

Mirror only the proven one-call shape from `MinimalPlannerDraftAdapter`: validate intent, render immutable canonical prompt content, materialize a fresh request, call once, capture exact raw response, and catch ordinary transport exceptions. Do not reuse its four-field prompt, decoded-object contract, Worker semantics, or result types.

Pass `record.raw_response` directly to `load_semantic_graph()`, then compile the admitted graph. Never decode in the adapter.

- [ ] **Step 7: Implement the fixed graph builder**

Use existing `PlanGraphNode`, `PlanGraphEdge`, `PlanGraph`, and `initialize_graph()`. Do not add a `RookWorkflowContract` template or one execution node per semantic component.

- [ ] **Step 8: Run Task 3 GREEN excluding the intentional execution skeleton**

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph.py `
  mcp_server/tests/test_semantic_graph_compiler.py `
  mcp_server/tests/test_semantic_graph_runner.py -k "planner or graph_admission or execution_graph"
uv run --project mcp_server python -m compileall -q `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/tests/test_semantic_graph_runner.py
git diff --check
```

- [ ] **Step 9: Commit Task 3**

```powershell
git add `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/tests/test_semantic_graph_runner.py
git commit -m "feat(agent): add semantic graph planner boundary"
git status --short
```

- [ ] **Step 10: Review gate**

Confirm one raw Planner response reaches one strict loader, no execution identity appears in the prompt, and all invalid graphs stop before any GH tool call.

---

## Task 4: One Snapshot, One Edit, and Exact Structural Verification

**Files:**

- Modify: `mcp_server/src/rook/agent/semantic_graph_runner.py`
- Modify: `mcp_server/tests/test_semantic_graph_runner.py`
- Read: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Read: `mcp_server/src/rook/gh_edit_contract.py`
- Read: `mcp_server/src/rook/agent/plan_graph_current_step_runner.py`
- Read: `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`
- Read: `mcp_server/src/rook/learning/plan_graph.py`

**Execution discipline:** Reuse the existing contracted tool results directly. Do not route `gh_edit` through the script-receipt verifier and do not create a new receipt taxonomy. Apply one local structural `NodeOutcome` to `verify_edit`, then retain existing PlanGraph/step/supply record types.

- [ ] **Step 1: Add a causal fake snapshot/edit executor**

In the runner test only, build a fake that:

- accepts only `gh_snapshot` then optionally `gh_edit`;
- derives its returned components, `temp_id_map`, `instance_guids`, edit summary counts, and flows from the actual edit request;
- assigns unique existing `C*` and instance GUID values;
- uses the qualified primitive identities from request GUID/special type, not canned witness output;
- records the current `get_rhino_request_context()` value at each call;
- refuses unexpected tools, order, repeated calls, or request mutation.

- [ ] **Step 2: Write snapshot-budget REDs**

Require the exact structural snapshot request:

```python
{"include_data": False, "max_preview_items": 0}
```

Cover:

- snapshot executor exception;
- non-mapping result;
- `success` not exact `True`;
- missing data or epoch;
- boolean, zero, negative, float, and string epoch.

Every case must return stage `snapshot`, retain the exact request/observed response when available, make one snapshot call, and make zero edit calls.

- [ ] **Step 3: Write context and edit materialization REDs**

Within one `rhino_request_context(port=..., process_id=..., document_serial_number=...)`, require:

- runner captures one frozen context snapshot before snapshot;
- the same injected executor object receives both calls;
- the same context values are visible at snapshot and edit entry;
- final edit request equals the epoch-free plan plus only the admitted epoch;
- no snapshot field other than epoch changes lowering;
- exactly one snapshot and one edit are entered.

If the bound context changes between calls, raise as an internal transaction contradiction before edit rather than silently retargeting.

- [ ] **Step 4: Write edit-stage REDs**

Using already contracted fake results, cover:

- executor exception;
- top-level failure;
- stale-epoch failure;
- `partial_success` at either top level or nested data;
- nonempty `edit_summary.errors`;
- created/connected count shortfall accompanied by edit errors.

Require stage `edit`, one snapshot, one edit, no verification success, no retry/resnapshot/cleanup, and truthful retention of returned mutation evidence.

- [ ] **Step 5: Write mapping and identity verification REDs**

Starting from a contracted edit success with empty errors, mutate one field at a time:

- expected T-key set differs from `temp_id_map` keys;
- expected T-key set differs from `instance_guids` keys;
- empty C ID or instance GUID;
- duplicate returned C IDs;
- duplicate returned instance GUIDs;
- mapped C component absent from returned snapshot;
- regular component `componentGuid` differs;
- slider returned type differs from `NumberSlider`;
- created or connected count differs without an edit error.

The existing edit contract pairs `temp_id_map[T]` and `instance_guids[T]` by the
same `T` key. The returned structural snapshot does not expose instance GUIDs on
component rows, so do not invent a second GUID-to-component lookup. Require exact
key equality, uniqueness of both value sets, and use `temp_id_map[T]` to locate the
snapshot component whose qualified primitive identity is checked.

Each must reach stage `verification`, not `edit`, because the existing edit contract succeeded but the reconstructed requested structure disagrees.

- [ ] **Step 6: Write exact incident-wiring REDs**

Translate every requested T-flow using `temp_id_map`. Define actual wires as every returned flow whose source **or** target is in the newly mapped C set. Cover:

- missing requested new/new wire;
- extra new/new wire;
- unexpected pre-existing/new wire;
- unexpected new/pre-existing wire;
- malformed incident wire;
- an unrelated pre-existing/pre-existing wire, which must be ignored.

Require exact set equality, not subset containment.

- [ ] **Step 7: Write PlanGraph/native-record REDs**

Require the returned native execution chain:

```text
initial:      create_edit ready, verify_edit pending, done pending
after edit:   create_edit succeeded, verify_edit ready, done pending
after verify: create_edit succeeded, verify_edit succeeded, done ready
terminal:     selector_halt terminal_node_selected:done
```

Use existing public artifacts:

- `CatalogCurrentStepProvider` for selector/revalidation/mapping supply;
- `StepExecutionResult` and `LiveProducerResult` for the edit step;
- `VerifierStepResult` for the deterministic structural step;
- `project_current_step_record()` for both flattened step records;
- `EnvelopeSupplyRecord` for supplied steps and terminal halt;
- `apply_outcome()` for the two node transitions.

Do not invoke `apply_verifier_step()`: it is intentionally the script-receipt verifier and does not own `gh_edit` structural evidence. Do not change that shared verifier.

Require complete ordered records for `create_edit`, `verify_edit`, then terminal halt. Verification makes no tool call.

- [ ] **Step 8: Write result-stage presence REDs**

Directly construct each allowed stage and enforce only immediate ownership:

```text
planner          -> Planner record only
graph_admission  -> Planner record, no admitted plan
snapshot         -> canonical graph/plan + snapshot request/observed response
edit             -> final request + edit response when returned + execution prefix
verification     -> edit response + failed structural projection + execution prefix
terminal         -> exact correlation + final graph + full records
```

Do not add replay, self-authentication, cross-transaction substitution matrices, hashes, or source binding.

- [ ] **Step 9: Run the complete Task 4 RED**

```powershell
uv run --project mcp_server pytest -q mcp_server/tests/test_semantic_graph_runner.py
```

- [ ] **Step 10: Implement the fixed transaction**

Implementation order inside `_execute_compiled_plan()`:

```text
capture frozen Rhino context
record exact snapshot request
call gh_snapshot once
admit exact epoch
materialize final gh_edit request
build fixed PlanGraph
supply/map create_edit through existing provider
call gh_edit once
retain contracted response and apply edit outcome
if edit contract failed -> edit stop
compute exact structural projection from returned snapshot/mappings
apply deterministic verify_edit outcome with no call
if mismatch -> verification stop
observe done through existing selector/provider halt
return terminal result
```

Normalize sync-or-async tool executors only with `inspect.isawaitable`; delegate each admitted call exactly once and return/retain the original mapping unchanged.

- [ ] **Step 11: Run Task 4 GREEN and adjacent native seams**

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph.py `
  mcp_server/tests/test_semantic_graph_compiler.py `
  mcp_server/tests/test_semantic_graph_runner.py `
  mcp_server/tests/test_gh_edit_contract.py `
  mcp_server/tests/test_dispatcher_safety.py `
  mcp_server/tests/test_plan_graph.py `
  mcp_server/tests/test_plan_graph_selector.py `
  mcp_server/tests/test_plan_graph_revalidation.py `
  mcp_server/tests/test_plan_graph_step_mapping.py `
  mcp_server/tests/test_plan_graph_current_step_runner.py `
  mcp_server/tests/test_plan_graph_current_step_provider.py
uv run --project mcp_server python -m compileall -q `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/tests/test_semantic_graph_runner.py
git diff --check
```

- [ ] **Step 12: Commit Task 4**

```powershell
git add `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/tests/test_semantic_graph_runner.py
git commit -m "feat(agent): execute semantic gh edit graphs"
git status --short
```

- [ ] **Step 13: Mandatory execution-boundary review stop**

Review exact call counts, context continuity, existing edit-contract consumption, native record construction, mapping bijection, incident-wire equality, and stage truth before witness tests/final reconciliation.

---

## Task 5: Two Witnesses, Compositionality Guards, and Final Reconciliation

**Files:**

- Modify: `mcp_server/tests/test_semantic_graph_runner.py`
- Modify: this plan ledger
- Production changes: none unless an existing focused test demonstrates a concrete behavioral defect

- [ ] **Step 1: Add witness 1 as raw Planner JSON**

Test only:

```text
three number sliders
-> Series start / step / count
-> Construct Point x
-> Polyline vertices
```

Use arbitrary valid local node IDs and an intent stored only in the test. Assert Planner-authored node selection/count/parameters/wiring survive canonicalization, while the compiler alone supplies GUIDs, indices, temp IDs, and layout.

Drive it through the causal fake executor and require one Planner, one snapshot, one edit, exact structural correlation, and terminal `done`.

- [ ] **Step 2: Add witness 2 as raw Planner JSON**

Test only:

```text
cell-size slider
x-extent slider
y-extent slider
-> Square Grid
```

Require materially different topology, the same production compiler path, integral initial admission for the two extent connections, one Planner/snapshot/edit, and exact terminal materialization.

- [ ] **Step 3: Re-run the two non-witness recombinations through the full runner**

Require full transaction success for:

```text
slider -> construct_point.x
slider -> square_grid.cell_size
```

This is the explicit guard that production is a bounded graph language rather than two hidden templates.

- [ ] **Step 4: Add unsuccessful witness-shaped variants**

Keep failures causal and minimal:

- Planner returns witness 1 with an invalid cycle -> `graph_admission`, zero GH calls;
- snapshot failure after valid witness 2 -> one snapshot, zero edits;
- edit partial success -> `edit`, no retry;
- clean edit response with an extra new/pre-existing wire -> `verification`;
- no failed path performs cleanup or a second call of either tool.

- [ ] **Step 5: Run the final focused seam**

```powershell
uv run --project mcp_server pytest -q `
  mcp_server/tests/test_semantic_graph.py `
  mcp_server/tests/test_semantic_graph_compiler.py `
  mcp_server/tests/test_semantic_graph_runner.py `
  mcp_server/tests/test_gh_edit_contract.py `
  mcp_server/tests/test_dispatcher_safety.py `
  mcp_server/tests/test_recipe_extraction.py `
  mcp_server/tests/test_plan_graph.py `
  mcp_server/tests/test_plan_graph_selector.py `
  mcp_server/tests/test_plan_graph_revalidation.py `
  mcp_server/tests/test_plan_graph_step_mapping.py `
  mcp_server/tests/test_plan_graph_step_executor.py `
  mcp_server/tests/test_plan_graph_current_step_runner.py `
  mcp_server/tests/test_plan_graph_current_step_provider.py
```

Record the exact passing count. No test in this command may contact a provider, Worker, Rhino, or Grasshopper.

- [ ] **Step 6: Run compilation and source-surface audit**

```powershell
uv run --project mcp_server python -m compileall -q `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/tests/test_semantic_graph.py `
  mcp_server/tests/test_semantic_graph_compiler.py `
  mcp_server/tests/test_semantic_graph_runner.py
rg -n "Worker|DSPy|knowledge|recipe_to_edit|subgraph|retry|fallback|archive|fingerprint|checksum" `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/src/rook/agent/semantic_graph_runner.py
rg -n "phyllotaxis|point_row|square_grid_witness|expected_witness|TEMPLATE" `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/src/rook/agent/semantic_graph_runner.py
git diff --check
git status --short
git diff --name-only 65108bcbd00f572dc65203d39ecb8890dbd5c98f...HEAD
```

The first scan may find only explanatory non-claims; inspect every match. The witness/template scan must have zero production matches. The merge diff must contain only the one fixture, three production modules, three tests, approved specification, and this plan.

- [ ] **Step 7: Reconcile this durable plan**

Mark every completed checkbox, and record:

- fixture capture commit and independent approval;
- each implementation commit;
- exact focused commands and counts;
- Python compilation result;
- `git diff --check` result;
- final HEAD;
- exact file scope;
- explicit statement that the result is bounded ephemeral telemetry, not a metric/evaluation/archive system;
- explicit statement that no live witness was run after Task 0.

- [ ] **Step 8: Commit test/ledger reconciliation only**

```powershell
git add `
  mcp_server/tests/test_semantic_graph_runner.py `
  docs/superpowers/plans/2026-08-03-compositional-harness-variable-topology.md
git commit -m "test(agent): close semantic graph slice1 witness seam"
git status --short
git show --check --stat --oneline HEAD
```

- [ ] **Step 9: Final independent implementation review stop**

Do not push, open a PR, merge, construct a real Planner transport, or run either live witness until an independent reviewer approves the complete implementation and confirms the Slice 0 audit dependency is already merged.

---

## Post-Merge Work Explicitly Deferred

After a separately reviewed merge, a new authorization may permit two live witness transactions using existing operator tracing only if it fits unchanged. That later work must not be folded into this plan.

Still deferred:

- Worker leaves;
- knowledge retrieval/runtime authority;
- v2 recipe import or migration;
- DSPy optimization or corpus management;
- product UI/Chat/MCP/CLI registration;
- reusable subgraphs;
- Rhino or mixed-domain primitives;
- output-value, geometry, visual, or semantic-fidelity evaluation;
- repeatability claims;
- runtime primitive discovery or automatic tuple updates;
- additive `gh_snapshot` port parity across the supported simple-parameter families;
- recorder, archive, verifier, registry, or evidence-system work.
