# Compositional Harness Slice 2: Single Worker Leaf Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` for Inline Execution of this tightly coupled transaction. Steps use checkbox (`- [ ]`) syntax for tracking. Stop at the mandatory independent review gate after Task 2.

**Goal:** Admit one Planner-authored `csharp_script` semantic leaf, resolve its exact `[] -> A:double` body through one existing Worker turn, execute the existing deterministic semantic region, connect the two native identities once, and stop.

**Architecture:** Extend the strict semantic graph boundary with one recursively immutable Worker-leaf variant, then add one immutable compiler partition containing the existing deterministic `EpochFreeEditPlan`, one unresolved leaf, and one cross-edge. A thin sibling compositor invokes the existing Worker-first handoff leaf-first, calls the existing Slice 1 deterministic executor, dispatches one existing `gh_connect`, and returns a bounded prefix aggregate containing the existing owner records directly.

**Tech Stack:** Python 3.12.12, frozen slots dataclasses, standard-library strict JSON decoding, Anthropic-compatible JSON Schema using `anyOf`, existing `SemanticGraphPlannerAdapter`, existing Worker adapter/harness/action/applicator, existing PlanGraph and typed-tool runners, `gh_create_csharp_script`, `gh_snapshot`, `gh_edit`, `gh_connect`, pytest, PowerShell, and Git.

## Global Constraints

- Implement only [the approved Slice 2 specification](../specs/2026-08-03-compositional-harness-single-worker-leaf-design.md).
- Baseline commit is `48dc2f200348c4f34454ad9c6d0bdb819c097ddc`; the approved specification commits are `09e09ed4` and `8a2216d9`.
- The pre-plan focused baseline is **399 passed**.
- Preserve the primary checkout and unrelated worktrees unchanged.
- No provider, Worker box, Rhino, Grasshopper, readiness, discovery, or mutation contact occurs during implementation or review.
- The Planner makes at most one call. The Worker makes at most one call. A full successful transaction makes exactly one `gh_create_csharp_script`, one `gh_snapshot`, one `gh_edit`, and one `gh_connect` call.
- There are zero `gh_update_script` calls, repairs, retries, fallbacks, replans, resnapshots, cleanup calls, second Worker calls, or second connect calls.
- Preserve Slice 1 compatibility: deterministic graphs with zero Worker leaves remain accepted by the existing loader/compiler/runner.
- The Slice 2 compositor requires exactly one Worker leaf. More than one Worker leaf always refuses.
- The Planner explicitly authors the exact interface `inputs: []`, `outputs: [{"name":"A","type":"double"}]`; the compiler admits but never injects or rewrites it.
- `csharp_script` has no incoming edge and exactly one outgoing `A` edge to a deterministic input whose element type is exactly `Number`.
- Validate the cross-edge in the full graph, including the target pin's existing `max_connections`, before excluding it from the deterministic `gh_edit` plan.
- The compiler alone partitions the admitted graph. The compositor consumes the partition and never rereads or reinterprets raw Planner topology.
- Reuse `draft_create_body`, `run_minimal_csharp_initial_body_handoff()`, `_execute_compiled_plan()`, native receipts, Slice 1 structural correlation, and the normalized `gh_connect` response. Do not redesign them.
- One frozen Rhino request context and the same tool executor cover C# create, snapshot, edit, and connect.
- A failed, malformed, or identity-mismatched returned connect response is operational evidence and yields `completed=False`. Only contradictions among code-owned/compiler-owned objects or Rhino context drift raise.
- The result is a thin ephemeral prefix. It does not replay histories, recompile retained values, prove transitive lineage, or create a stage/reason taxonomy.
- Production code and Planner prompts contain no witness intent, `construct_point.x`, expected graph shape, generated body, GUID, pin index, layout, `T*` identifier, Worker action, or expected code.
- Provider-facing schema alternatives use `anyOf`, never `oneOf`. Unsupported semantic limits remain enforced by the strict loader/compiler.
- Add no scheduler, suspension/resumption system, registry, job language, generalized interface system, new Worker response, PlanGraph concept, tool endpoint, UI, knowledge/DSPy path, archive, recorder, proof carrier, or evidence framework.
- Use `apply_patch` for edits. Add no dependency.
- If production work exceeds the four planned files, total production additions across those files exceed roughly 650 lines, the new compositor exceeds roughly 350 production lines, or a PlanGraph/tool-contract change appears necessary, stop for scope review. Count additions directly; deletions do not offset the growth gate.

---

## Planned File Surface

### Production

- Modify `mcp_server/src/rook/agent/semantic_graph.py`
  - Add the exact frozen C# interface/output types.
  - Admit one `csharp_script` node variant from strict JSON.
  - Add a Slice 2 provider schema and prompt projection while preserving Slice 1 builders unchanged.
- Modify `mcp_server/src/rook/agent/semantic_graph_compiler.py`
  - Add the immutable zero-or-one-leaf partition and compiler result.
  - Reuse the existing deterministic compiler for the remaining graph.
- Modify `mcp_server/src/rook/agent/semantic_graph_runner.py`
  - Add one code-owned `produce_worker_leaf()` Planner path using the Slice 2 schema/projection.
  - Preserve existing `produce()` and `run_semantic_graph_transaction()` behavior.
- Create `mcp_server/src/rook/agent/semantic_graph_worker_leaf_runner.py`
  - Define the thin prefix result and fixed leaf-first compositor.
  - Reuse the existing Worker handoff and Slice 1 executor directly.

### Tests

- Modify `mcp_server/tests/test_semantic_graph.py`
  - Strict nested interface admission, immutability, schema compatibility, and prompt projection.
- Modify `mcp_server/tests/test_semantic_graph_compiler.py`
  - Partition, cross-edge, compatibility, multiplicity, and Slice 1 compatibility.
- Modify `mcp_server/tests/test_semantic_graph_runner.py`
  - Slice 2 Planner prompt/call behavior while retaining existing Slice 1 assertions.
- Create `mcp_server/tests/test_semantic_graph_worker_leaf_runner.py`
  - Walking connected vertical, causal tool responses, prefix stops, call budgets, and thin result shape.

### Durable plan ledger

- Modify only this plan during implementation to mark completed steps and record reviewed commits, exact commands, counts, and final HEAD.

No existing Worker-first, PlanGraph, tool-dispatcher, native, managed, Chat, knowledge, DSPy, or operator-script file is in scope. Stop before widening this surface.

---

## Task 1: Admit the Exact Recursively Immutable Worker Leaf

**Files:**

- Modify: `mcp_server/src/rook/agent/semantic_graph.py`
- Modify: `mcp_server/tests/test_semantic_graph.py`

**Interfaces:**

- Consumes: existing `SemanticGraphNode`, `SemanticGraphLoadResult`, `load_semantic_graph()`, `build_semantic_graph_response_schema()`, and `semantic_primitive_prompt_projection()`.
- Produces:
  - `SemanticCSharpOutput(name: str, type: str)`
  - `SemanticCSharpInterface(inputs: tuple[object, ...], outputs: tuple[SemanticCSharpOutput, ...])`
  - `build_worker_leaf_semantic_graph_response_schema() -> dict[str, object]`
  - `semantic_worker_leaf_prompt_projection() -> tuple[dict[str, object], ...]`
  - admitted `SemanticGraphNode(parameters=(("goal", str), ("interface", SemanticCSharpInterface)))` for `primitive == "csharp_script"`

- [x] **Step 1: Add behavioral RED tests through the existing module import**

Add helpers to `test_semantic_graph.py` without importing not-yet-existing names directly:

```python
def _csharp_node(
    node_id: str = "generated_value",
    *,
    goal: object = "Produce one numeric value.",
    interface: object | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "primitive": "csharp_script",
        "parameters": {
            "goal": goal,
            "interface": (
                {
                    "inputs": [],
                    "outputs": [{"name": "A", "type": "double"}],
                }
                if interface is None
                else interface
            ),
        },
    }
```

Add one admitted-shape test:

```python
def test_loader_materializes_owned_immutable_csharp_interface() -> None:
    payload = _payload(nodes=[_csharp_node()], edges=[])
    source_interface = payload["nodes"][0]["parameters"]["interface"]

    graph = semantic_graph._load_graph_object(payload)
    node = graph.nodes[0]
    parameters = dict(node.parameters)
    interface = parameters["interface"]

    assert type(interface) is semantic_graph.SemanticCSharpInterface
    assert interface.inputs == ()
    assert type(interface.outputs) is tuple
    assert interface.outputs == (
        semantic_graph.SemanticCSharpOutput(name="A", type="double"),
    )
    source_interface["outputs"][0]["name"] = "B"
    source_interface["outputs"].append({"name": "B", "type": "integer"})
    assert interface.outputs[0].name == "A"
    assert len(interface.outputs) == 1
```

Add `import dataclasses` to the test module, then add mutation/substitution tests:

```python
def test_csharp_interface_rejects_mutable_or_wrong_nested_carriers() -> None:
    output = semantic_graph.SemanticCSharpOutput(name="A", type="double")
    with pytest.raises(TypeError):
        semantic_graph.SemanticCSharpInterface(inputs=[], outputs=(output,))
    with pytest.raises(TypeError):
        semantic_graph.SemanticCSharpInterface(
            inputs=(),
            outputs=({"name": "A", "type": "double"},),
        )

    interface = semantic_graph.SemanticCSharpInterface(
        inputs=(),
        outputs=(output,),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        interface.outputs = ()
```

Add a compact table over raw JSON for:

```text
missing/extra goal or interface fields
non-string, blank, >4096-character, >16384-byte, and lone-surrogate goal
non-list inputs, nonempty inputs
non-list outputs, zero/two outputs
wrong/extra output fields
name other than exact A
type other than exact double
more than one csharp_script node
```

Require exact refusal reasons owned by the loader. Do not introduce Python-subclass or equality-spoof matrices; strict JSON text is the untrusted boundary.

Add provider-schema tests:

```python
def _walk_schema(value: object):
    yield value
    if type(value) is dict:
        for child in value.values():
            yield from _walk_schema(child)
    elif type(value) is list:
        for child in value:
            yield from _walk_schema(child)


def test_worker_leaf_schema_uses_provider_qualified_anyof_only() -> None:
    schema = semantic_graph.build_worker_leaf_semantic_graph_response_schema()
    Draft202012Validator.check_schema(schema)
    walked = tuple(_walk_schema(schema))
    assert not any(type(value) is dict and "oneOf" in value for value in walked)
    alternatives = schema["properties"]["nodes"]["items"]["anyOf"]
    assert any(
        item["properties"]["primitive"] == {"const": "csharp_script"}
        for item in alternatives
    )
    serialized = json.dumps(schema, sort_keys=True)
    assert "maxItems" not in serialized
    assert "minItems" not in serialized
    assert "maxLength" not in serialized
```

Also prove the existing Slice 1 schema and primitive projection remain byte-for-byte equal before and after mutating fresh Slice 2 return values.

- [x] **Step 2: Run Task 1 RED tests**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q tests/test_semantic_graph.py
```

Expected: behavioral failures because `csharp_script`, `SemanticCSharpInterface`, `SemanticCSharpOutput`, and the Slice 2 schema/projection builders do not yet exist. Existing Slice 1 tests still pass up to those assertions.

- [x] **Step 3: Implement the exact frozen interface and strict loader branch**

Add constants and types in `semantic_graph.py`:

```python
_CSHARP_SCRIPT_PRIMITIVE = "csharp_script"
_MAX_CSHARP_GOAL_CHARACTERS = 4_096
_MAX_CSHARP_GOAL_UTF8_BYTES = 16_384


@dataclass(frozen=True, slots=True)
class SemanticCSharpOutput:
    name: str
    type: str

    def __post_init__(self) -> None:
        if type(self.name) is not str or self.name != "A":
            raise TypeError("C# output name must be exact A")
        if type(self.type) is not str or self.type != "double":
            raise TypeError("C# output type must be exact double")


@dataclass(frozen=True, slots=True)
class SemanticCSharpInterface:
    inputs: tuple[object, ...]
    outputs: tuple[SemanticCSharpOutput, ...]

    def __post_init__(self) -> None:
        if type(self.inputs) is not tuple:
            raise TypeError("C# inputs must be an exact tuple")
        if self.inputs:
            raise ValueError("C# inputs must be empty")
        if type(self.outputs) is not tuple:
            raise TypeError("C# outputs must be an exact tuple")
        if len(self.outputs) != 1 or type(self.outputs[0]) is not SemanticCSharpOutput:
            raise TypeError("C# outputs must contain exact A:double")
```

Branch in `_load_node()` only on the exact primitive name, leaving `_PRIMITIVES` unchanged:

```python
primitive_name = value["primitive"]
if primitive_name == _CSHARP_SCRIPT_PRIMITIVE:
    return SemanticGraphNode(
        id=node_id,
        primitive=_CSHARP_SCRIPT_PRIMITIVE,
        parameters=_load_csharp_parameters(value["parameters"]),
    )
primitive = _find_primitive(primitive_name)
```

Implement `_load_csharp_parameters()` with closed dictionaries/lists, strict goal bounds, and immediate typed conversion:

```python
def _load_csharp_parameters(value: object) -> tuple[tuple[str, object], ...]:
    if type(value) is not dict or set(value) != {"goal", "interface"}:
        raise _AdmissionError("parameters", "invalid_csharp_parameters")
    goal = value["goal"]
    if type(goal) is not str or not goal.strip():
        raise _AdmissionError("parameters", "invalid_csharp_goal")
    if len(goal) > _MAX_CSHARP_GOAL_CHARACTERS:
        raise _AdmissionError("parameters", "invalid_csharp_goal")
    try:
        goal_bytes = goal.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _AdmissionError("parameters", "invalid_csharp_goal") from exc
    if len(goal_bytes) > _MAX_CSHARP_GOAL_UTF8_BYTES:
        raise _AdmissionError("parameters", "invalid_csharp_goal")

    raw_interface = value["interface"]
    if type(raw_interface) is not dict or set(raw_interface) != {"inputs", "outputs"}:
        raise _AdmissionError("parameters", "invalid_csharp_interface")
    raw_inputs = raw_interface["inputs"]
    raw_outputs = raw_interface["outputs"]
    if type(raw_inputs) is not list or raw_inputs:
        raise _AdmissionError("parameters", "invalid_csharp_interface")
    if type(raw_outputs) is not list or len(raw_outputs) != 1:
        raise _AdmissionError("parameters", "invalid_csharp_interface")
    raw_output = raw_outputs[0]
    if type(raw_output) is not dict or set(raw_output) != {"name", "type"}:
        raise _AdmissionError("parameters", "invalid_csharp_interface")
    try:
        output = SemanticCSharpOutput(
            name=raw_output["name"],
            type=raw_output["type"],
        )
        interface = SemanticCSharpInterface(inputs=(), outputs=(output,))
    except (TypeError, ValueError) as exc:
        raise _AdmissionError("parameters", "invalid_csharp_interface") from exc
    return (("goal", goal), ("interface", interface))
```

Count `csharp_script` nodes after node loading and refuse more than one with `multiple_worker_leaves`.

- [x] **Step 4: Add the Slice 2-only schema and prompt projection**

Keep `build_semantic_graph_response_schema()` and `semantic_primitive_prompt_projection()` behavior unchanged. Add fresh Slice 2 builders:

```python
def build_worker_leaf_semantic_graph_response_schema() -> dict[str, object]:
    schema = build_semantic_graph_response_schema()
    alternatives = schema["properties"]["nodes"]["items"]["anyOf"]
    alternatives.append(_csharp_node_schema())
    return schema


def _csharp_node_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "primitive", "parameters"],
        "properties": {
            "id": {"type": "string"},
            "primitive": {"const": "csharp_script"},
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["goal", "interface"],
                "properties": {
                    "goal": {"type": "string"},
                    "interface": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["inputs", "outputs"],
                        "properties": {
                            "inputs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {},
                                },
                            },
                            "outputs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["name", "type"],
                                    "properties": {
                                        "name": {"const": "A"},
                                        "type": {"const": "double"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }
```

Add the fresh Planner projection:

```python
def semantic_worker_leaf_prompt_projection() -> tuple[dict[str, object], ...]:
    return (
        *semantic_primitive_prompt_projection(),
        {
            "primitive": "csharp_script",
            "inputs": (),
            "outputs": ({"name": "A", "element_type": "Number"},),
            "parameters": (
                {"name": "goal", "value_kind": "string", "required": True},
                {
                    "name": "interface",
                    "required": True,
                    "exact": {
                        "inputs": [],
                        "outputs": [{"name": "A", "type": "double"}],
                    },
                },
            ),
            "connection_rules": {
                "incoming": 0,
                "outgoing": 1,
                "source_pin": "A",
                "target_element_type": "Number",
            },
        },
    )
```

The schema contains no `minItems`, `maxItems`, `maxLength`, GUID, index, layout, `T*`, body, action, or witness topology. The strict loader owns those semantic limits.

- [x] **Step 5: Run Task 1 tests and the Slice 1 compatibility tests**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_semantic_graph.py `
  tests/test_semantic_graph_compiler.py `
  tests/test_semantic_graph_runner.py
```

Expected: all pass. Existing Slice 1 schema and Planner prompt assertions remain unchanged.

- [x] **Step 6: Commit Task 1**

```powershell
git add -- `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/tests/test_semantic_graph.py
git diff --cached --check
git commit -m "feat: admit one semantic csharp worker leaf"
```

Record the exact commit and test count in this plan ledger. Do not begin Task 2 with a dirty worktree.

Observed Task 1 evidence:

```text
RED: 23 failed, 85 passed (missing Worker-leaf admission surface)
loader/schema GREEN: 108 passed
Slice 1 compatibility seam: 216 passed
commit: 57e7c253975e144f4d0e66acafdd9bbe08b1e242
```

---

## Task 2: Compile One Immutable Deterministic/Worker Partition

**Files:**

- Modify: `mcp_server/src/rook/agent/semantic_graph_compiler.py`
- Modify: `mcp_server/tests/test_semantic_graph_compiler.py`

**Interfaces:**

- Consumes: admitted `SemanticGraph`, exact `SemanticCSharpInterface`, existing private primitive tuple/pins, and `compile_semantic_graph()`.
- Produces:
  - `UnresolvedCSharpLeaf`
  - `WorkerLeafCrossEdge`
  - `SemanticGraphWorkerLeafPartition`
  - `SemanticGraphWorkerLeafPartitionCompileResult`
  - `compile_semantic_graph_worker_leaf_partition(graph)` accepting zero or one Worker leaf

- [x] **Step 1: Add behavioral RED tests through the existing compiler module**

Import the module, not absent names:

```python
import rook.agent.semantic_graph_compiler as compiler
```

Add a helper that loads real raw JSON before compilation. Add the successful partition assertion:

```python
def test_partition_compiler_separates_one_worker_leaf_and_cross_edge() -> None:
    graph = _load_graph(
        nodes=[_csharp_node(), _node("point", "construct_point")],
        edges=[_edge("generated_value", "A", "point", "x")],
    )

    result = compiler.compile_semantic_graph_worker_leaf_partition(graph)

    assert result.admitted is True
    partition = result.partition
    assert partition is not None
    assert partition.unresolved_leaf.node_id == "generated_value"
    assert partition.unresolved_leaf.goal == "Produce one numeric value."
    assert partition.unresolved_leaf.interface.outputs[0].name == "A"
    assert partition.cross_edge == compiler.WorkerLeafCrossEdge(
        source_node_id="generated_value",
        source_pin="A",
        source_output_index=0,
        target_node_id="point",
        target_pin="x",
        target_input_index=0,
    )
    assert partition.deterministic_plan.semantic_node_to_temp_id == (("point", "T1"),)
    assert partition.deterministic_plan.connect == ()
    assert all(
        dict(instruction.fields).get("guid")
        != "csharp_script"
        for instruction in partition.deterministic_plan.create_instructions
    )
```

Add zero-leaf compatibility:

```python
def test_partition_compiler_preserves_zero_leaf_slice1_plan() -> None:
    graph = _load_graph(nodes=[_node("point", "construct_point")], edges=[])
    existing = compiler.compile_semantic_graph(graph)
    partitioned = compiler.compile_semantic_graph_worker_leaf_partition(graph)

    assert existing.admitted is True
    assert partitioned.admitted is True
    assert partitioned.partition is not None
    assert partitioned.partition.deterministic_plan == existing.plan
    assert partitioned.partition.unresolved_leaf is None
    assert partitioned.partition.cross_edge is None
```

Add table-driven refusals for:

```text
two Worker leaves
incoming edge to the Worker leaf
zero outgoing Worker edges
two outgoing Worker edges
source pin other than exact A
unknown deterministic target
target pin other than a real input
target element type other than exact Number
self-edge or cycle in the complete graph
deterministic edge plus cross-edge occupying the same max_connections=1 input
```

The strict loader already refuses two Worker leaves. For the compiler's defensive
multi-leaf regression, construct one exact `SemanticGraph` from two individually
admitted typed leaf nodes and one deterministic target; do not bypass the typed
node/interface classes with dictionaries or mutable carriers.

For the occupied-target case, use a slider-to-`construct_point.x` deterministic edge plus `csharp_script.A -> construct_point.x`. Assert `too_many_input_connections` before any lowering.

Add a source scan asserting `construct_point.x`, witness intent, `gh_connect`, and generated code do not appear in `semantic_graph_compiler.py`.

- [x] **Step 2: Run Task 2 RED tests**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_semantic_graph_compiler.py `
  -k "partition or worker_leaf or zero_leaf"
```

Expected: behavioral failures because the partition result and compiler function are absent. Existing deterministic compiler tests still pass.

- [x] **Step 3: Add the exact immutable partition types**

Add:

```python
@dataclass(frozen=True, slots=True)
class UnresolvedCSharpLeaf:
    node_id: str
    goal: str
    interface: _semantic_graph.SemanticCSharpInterface


@dataclass(frozen=True, slots=True)
class WorkerLeafCrossEdge:
    source_node_id: str
    source_pin: str
    source_output_index: int
    target_node_id: str
    target_pin: str
    target_input_index: int


@dataclass(frozen=True, slots=True)
class SemanticGraphWorkerLeafPartition:
    deterministic_plan: EpochFreeEditPlan
    unresolved_leaf: UnresolvedCSharpLeaf | None
    cross_edge: WorkerLeafCrossEdge | None


@dataclass(frozen=True, slots=True)
class SemanticGraphWorkerLeafPartitionCompileResult:
    admitted: bool
    partition: SemanticGraphWorkerLeafPartition | None
    failure: str | None
    reason: str
```

Validate immediate field types and paired leaf/cross-edge presence in these dataclasses only. Do not compare or replay the deterministic plan.

- [x] **Step 4: Implement the compiler-owned partition**

Implement `compile_semantic_graph_worker_leaf_partition()` as a sibling of the existing compiler:

```python
def compile_semantic_graph_worker_leaf_partition(
    graph: SemanticGraph,
) -> SemanticGraphWorkerLeafPartitionCompileResult:
    worker_nodes = tuple(
        node for node in graph.nodes if node.primitive == "csharp_script"
    )
    if len(worker_nodes) > 1:
        return _partition_refused("multiple_worker_leaves")
    if not worker_nodes:
        deterministic = compile_semantic_graph(graph)
        if not deterministic.admitted:
            return _partition_refused(deterministic.reason)
        if deterministic.plan is None:
            raise RuntimeError("admitted deterministic compilation lacks a plan")
        return _admitted_partition(deterministic.plan, None, None)

    worker_node = worker_nodes[0]
    incoming = tuple(edge for edge in graph.edges if edge.to_node == worker_node.id)
    outgoing = tuple(edge for edge in graph.edges if edge.from_node == worker_node.id)
    if incoming:
        return _partition_refused("worker_leaf_has_incoming_edge")
    if len(outgoing) != 1:
        return _partition_refused("worker_leaf_requires_one_outgoing_edge")
    cross = outgoing[0]
    if cross.from_pin != "A":
        return _partition_refused("worker_leaf_source_pin_invalid")

    deterministic_nodes = tuple(
        node for node in graph.nodes if node.id != worker_node.id
    )
    target_node = next(
        (node for node in deterministic_nodes if node.id == cross.to_node),
        None,
    )
    if target_node is None:
        return _partition_refused("worker_leaf_target_invalid")
    primitives = {
        primitive.name: primitive for primitive in _semantic_graph._PRIMITIVES
    }
    target_primitive = primitives.get(target_node.primitive)
    if target_primitive is None:
        return _partition_refused("worker_leaf_target_invalid")
    target_pin = _pin_by_name(target_primitive.inputs, cross.to_pin)
    if target_pin is None:
        return _partition_refused("worker_leaf_target_pin_invalid")
    if target_pin.element_type != "Number":
        return _partition_refused("worker_leaf_target_type_invalid")

    occupancy = sum(
        1
        for edge in graph.edges
        if edge.to_node == cross.to_node and edge.to_pin == cross.to_pin
    )
    if target_pin.max_connections is not None and occupancy > target_pin.max_connections:
        return _partition_refused("too_many_input_connections")

    deterministic_edges = tuple(edge for edge in graph.edges if edge is not cross)
    deterministic_graph = SemanticGraph(
        schema=graph.schema,
        nodes=deterministic_nodes,
        edges=deterministic_edges,
    )
    deterministic = compile_semantic_graph(deterministic_graph)
    if not deterministic.admitted:
        return _partition_refused(deterministic.reason)
    if deterministic.plan is None:
        raise RuntimeError("admitted deterministic compilation lacks a plan")

    parameters = dict(worker_node.parameters)
    interface = parameters["interface"]
    if type(interface) is not _semantic_graph.SemanticCSharpInterface:
        raise RuntimeError("admitted Worker interface changed type")
    return _admitted_partition(
        deterministic.plan,
        UnresolvedCSharpLeaf(
            node_id=worker_node.id,
            goal=parameters["goal"],
            interface=interface,
        ),
        WorkerLeafCrossEdge(
            source_node_id=worker_node.id,
            source_pin="A",
            source_output_index=0,
            target_node_id=cross.to_node,
            target_pin=cross.to_pin,
            target_input_index=target_pin.index,
        ),
    )
```

Use identity from the selected `cross` object only inside this function; do not accept a separately supplied graph, leaf, or edge. Keep refusal helpers local and reason-bearing. Unknown code-owned primitive/lowering contradictions continue to raise through the existing compiler.

- [x] **Step 5: Run the complete loader/compiler seam**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_semantic_graph.py `
  tests/test_semantic_graph_compiler.py `
  tests/test_semantic_graph_runner.py
```

Expected: all pass. Confirm canonical deterministic plans are still invariant to declaration order and that existing Slice 1 witnesses remain green.

- [x] **Step 6: Compile and inspect the exact Task 1–2 surface**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m compileall -q `
  src/rook/agent/semantic_graph.py `
  src/rook/agent/semantic_graph_compiler.py
cd ..
git diff --check
git diff --stat 8a2216d9...HEAD
git diff --name-only 8a2216d9...HEAD
```

Expected production scope at this gate:

```text
mcp_server/src/rook/agent/semantic_graph.py
mcp_server/src/rook/agent/semantic_graph_compiler.py
```

Expected test scope:

```text
mcp_server/tests/test_semantic_graph.py
mcp_server/tests/test_semantic_graph_compiler.py
```

No compositor or new runner module may exist yet.

- [x] **Step 7: Commit Task 2**

```powershell
git add -- `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/tests/test_semantic_graph_compiler.py
git diff --cached --check
git commit -m "feat: partition one semantic worker leaf"
```

Record the exact commit and test count in this plan ledger.

Observed Task 2 evidence:

```text
RED: 14 failed, 40 deselected (missing partition compiler surface)
partition GREEN: 14 passed, 40 deselected
complete loader/compiler/runner seam: 230 passed
commit: ae3cb1fb003d52d94bcc1272a76fca45d4014ef8
production additions through Task 2:
  semantic_graph.py: 165
  semantic_graph_compiler.py: 207
  total: 372
compileall: passed
git diff --check: passed
new compositor/runner module: absent
```

### Mandatory independent review gate after Task 2

- [x] **Stop before creating or modifying compositor code**

Report for independent review:

- Task 1 and Task 2 commit SHAs;
- exact changed files;
- exact focused test command and count;
- compilation and `git diff --check` results;
- proof that existing Slice 1 zero-leaf paths remain green;
- proof that the nested interface is recursively immutable;
- proof that provider schema uses `anyOf` and contains no `oneOf`;
- proof that cross-edge occupancy is validated before partitioning;
- proof that `csharp_script` never enters deterministic create instructions;
- cumulative production additions in `semantic_graph.py` and
  `semantic_graph_compiler.py`, counted without subtracting deletions;
- confirmation that no new runner/compositor, Worker protocol, PlanGraph concept,
  tool contract, registry, or framework exists.

Do not proceed to Task 3 until an independent reviewer explicitly approves this gate. If review finds the loader or compiler becoming a general script/interface system, stop and simplify rather than adding abstractions.

---

## Task 3: Compose the One-Shot Happy Path

**Prerequisite:** The mandatory Task 2 review gate is approved.

**Files:**

- Modify: `mcp_server/src/rook/agent/semantic_graph_runner.py`
- Create: `mcp_server/src/rook/agent/semantic_graph_worker_leaf_runner.py`
- Modify: `mcp_server/tests/test_semantic_graph_runner.py`
- Create: `mcp_server/tests/test_semantic_graph_worker_leaf_runner.py`

**Interfaces:**

- Consumes:
  - `SemanticGraphPlannerAdapter`
  - `SemanticGraphPlannerRecord`
  - `load_semantic_graph()`
  - `compile_semantic_graph_worker_leaf_partition()`
  - `load_minimal_csharp_repair_draft()`
  - `run_minimal_csharp_initial_body_handoff()`
  - existing private `_execute_compiled_plan()` and `_invoke_tool()`
  - existing `_require_exact_intent()` and `get_rhino_request_context()`
- Produces:
  - `SemanticGraphPlannerAdapter.produce_worker_leaf(intent)`
  - `SemanticGraphSingleWorkerLeafResult`
  - `run_semantic_graph_single_worker_leaf_transaction()`

- [x] **Step 1: Create an importable compositor skeleton before the RED test**

Create `semantic_graph_worker_leaf_runner.py` with the exact public surface and no behavior:

```python
from __future__ import annotations

from dataclasses import dataclass

from .minimal_csharp_initial_body_handoff import MinimalCSharpInitialBodyHandoffResult
from .semantic_graph import SemanticGraphLoadResult
from .semantic_graph_compiler import SemanticGraphWorkerLeafPartitionCompileResult
from .semantic_graph_runner import (
    SemanticGraphExecutionResult,
    SemanticGraphPlannerAdapter,
    SemanticGraphPlannerRecord,
)


@dataclass(frozen=True, slots=True)
class SemanticGraphSingleWorkerLeafResult:
    intent: str
    planner_record: SemanticGraphPlannerRecord
    graph_load_result: SemanticGraphLoadResult | None = None
    partition_compile_result: SemanticGraphWorkerLeafPartitionCompileResult | None = None
    worker_handoff_result: MinimalCSharpInitialBodyHandoffResult | None = None
    deterministic_execution_result: SemanticGraphExecutionResult | None = None
    connect_request: dict[str, object] | None = None
    connect_response: object | None = None
    completed: bool = False


async def run_semantic_graph_single_worker_leaf_transaction(*args, **kwargs):
    raise NotImplementedError("single Worker leaf compositor is not implemented")
```

Do not commit the skeleton separately.

- [x] **Step 2: Add the behavioral walking RED through all existing seams**

In `test_semantic_graph_worker_leaf_runner.py`, use:

```text
Planner raw JSON:
  csharp_script generated_value
  construct_point point
  generated_value.A -> point.x

Worker response:
  rook.local_worker_turn_response:v1
  action_request
  draft_create_body
  input.code = "A = 7.0;"
```

Implement test-only transports that deep-copy requests and count calls. Implement one causal executor with exact call order:

```python
_EXPECTED_TOOLS = (
    "gh_create_csharp_script",
    "gh_snapshot",
    "gh_edit",
    "gh_connect",
)


class _CausalExecutor:
    def __call__(self, name: str, params: dict[str, object]) -> object:
        self.calls.append((name, copy.deepcopy(params)))
        assert name == _EXPECTED_TOOLS[len(self.calls) - 1]
        if name == "gh_create_csharp_script":
            assert params["code"] == "A = 7.0;"
            assert params["pins_in"] == ()
            assert params["pins_out"] == ("A:double",)
            return _clean_create_response(_LEAF_GUID)
        if name == "gh_snapshot":
            assert params == {"include_data": False, "max_preview_items": 0}
            return _snapshot_response(epoch=11, preexisting_guid=_LEAF_GUID)
        if name == "gh_edit":
            self.edit_response = _derive_edit_response(params, target_guid=_TARGET_GUID)
            return self.edit_response
        assert params == {
            "sourceGuid": _LEAF_GUID,
            "sourceIndex": 0,
            "targetGuid": _TARGET_GUID,
            "targetIndex": 0,
        }
        return {
            "success": True,
            "data": {
                "connected": True,
                "source": {"guid": _LEAF_GUID, "param": "A", "index": 0},
                "target": {"guid": _TARGET_GUID, "param": "X", "index": 0},
            },
        }
```

The response helpers must derive `temp_id_map`, `instance_guids`, component counts, and flows from the received `gh_edit` request, following the existing `_CausalSnapshotEditExecutor` test pattern. They may use fixed physical GUID values only as fake external identities.

Add the walking assertion:

```python
@pytest.mark.asyncio
async def test_one_worker_leaf_composes_with_one_deterministic_region() -> None:
    planner = _PlannerTransport(_connected_raw_graph())
    worker = _WorkerTransport("A = 7.0;")
    executor = _CausalExecutor()

    result = await worker_leaf_runner.run_semantic_graph_single_worker_leaf_transaction(
        _INTENT,
        planner_adapter=SemanticGraphPlannerAdapter(planner),
        worker_transport=worker,
        tool_executor=executor,
    )

    assert result.completed is True
    assert len(planner.calls) == 1
    assert len(worker.calls) == 1
    assert [name for name, _ in executor.calls] == list(_EXPECTED_TOOLS)
    assert result.worker_handoff_result.terminal_stage == "terminal"
    assert result.worker_handoff_result.terminal_reason == "terminal_node_selected:done"
    assert result.deterministic_execution_result.terminal_stage == "terminal"
    assert result.deterministic_execution_result.terminal_reason == "terminal_node_selected:done"
    assert result.connect_request == executor.calls[-1][1]
    assert result.connect_response["data"]["connected"] is True
```

Add one compact parameterized capability-order regression covering:

```text
non-exact, blank, or invalid UTF-8 intent
SemanticGraphPlannerAdapter subclass or substitute
Worker transport without callable send
non-callable tool executor
```

Each case must raise before `produce_worker_leaf()` and prove zero Planner,
Worker, and tool calls. Caller validation must not be deferred to the existing
handoff or deterministic runner.

- [x] **Step 3: Run the walking test and verify behavioral RED**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_semantic_graph_worker_leaf_runner.py
```

Expected: the walking and capability-order tests fail against the skeleton's
missing behavior after fixtures and imports complete successfully. The
capability-order cases must not pass merely because the skeleton raises an
unrelated exception type.

- [x] **Step 4: Add the code-owned Slice 2 Planner call**

In `semantic_graph_runner.py`, preserve `produce()` and factor only the common send/record operation:

```python
class SemanticGraphPlannerAdapter:
    def produce(self, intent: str) -> SemanticGraphPlannerRecord:
        _require_exact_intent(intent)
        return self._produce_snapshot(_render_prompt_snapshot(intent))

    def produce_worker_leaf(self, intent: str) -> SemanticGraphPlannerRecord:
        _require_exact_intent(intent)
        return self._produce_snapshot(_render_worker_leaf_prompt_snapshot(intent))

    def _produce_snapshot(
        self,
        prompt_snapshot: SemanticGraphPromptSnapshot,
    ) -> SemanticGraphPlannerRecord:
        try:
            raw_response = self._transport.send(prompt_snapshot.materialize())
        except Exception as exc:
            return SemanticGraphPlannerRecord(
                prompt_snapshot=prompt_snapshot,
                status="transport_failed",
                raw_response=None,
                failure_reason="transport_failed",
                transport_error_type=type(exc).__name__,
            )
        return SemanticGraphPlannerRecord(
            prompt_snapshot=prompt_snapshot,
            status="response_received",
            raw_response=raw_response,
            failure_reason=None,
            transport_error_type=None,
        )
```

Add `_render_worker_leaf_prompt_snapshot()` using only `build_worker_leaf_semantic_graph_response_schema()` and `semantic_worker_leaf_prompt_projection()`. Keep the existing user-content encoding and one-object instruction. Tests in `test_semantic_graph_runner.py` must prove:

- exactly one transport call;
- raw response retained unchanged;
- prompt contains the exact `csharp_script` shape and current deterministic primitives;
- prompt excludes GUIDs, indices, layout, `T1`, Worker action IDs, code, receipts, and `construct_point.x`;
- mutating the materialized transport request does not alter the retained prompt snapshot;
- existing `produce()` prompt remains unchanged.

- [x] **Step 5: Implement the thin prefix result and fixed compositor**

Replace the skeleton with an exact signature:

```python
async def run_semantic_graph_single_worker_leaf_transaction(
    intent: str,
    *,
    planner_adapter: SemanticGraphPlannerAdapter,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, object]], object],
) -> SemanticGraphSingleWorkerLeafResult:
```

Validate all caller-owned capabilities before the first Planner call:

```python
_require_exact_intent(intent)
if type(planner_adapter) is not SemanticGraphPlannerAdapter:
    raise TypeError("planner_adapter must be the exact SemanticGraphPlannerAdapter")
if not callable(getattr(worker_transport, "send", None)):
    raise TypeError("worker_transport must provide callable send")
if not callable(tool_executor):
    raise TypeError("tool_executor must be callable")
```

Then use the fixed sequence:

```python
planner_record = planner_adapter.produce_worker_leaf(intent)
if planner_record.status == "transport_failed":
    return _result(intent, planner_record)

loaded = load_semantic_graph(planner_record.raw_response)
if not loaded.admitted:
    return _result(intent, planner_record, graph_load_result=loaded)
if loaded.graph is None:
    raise RuntimeError("admitted semantic graph is missing")

compiled = compile_semantic_graph_worker_leaf_partition(loaded.graph)
if not compiled.admitted:
    return _result(
        intent,
        planner_record,
        graph_load_result=loaded,
        partition_compile_result=compiled,
    )
partition = compiled.partition
if partition is None:
    raise RuntimeError("admitted partition is missing")
if partition.unresolved_leaf is None or partition.cross_edge is None:
    return _result(
        intent,
        planner_record,
        graph_load_result=loaded,
        partition_compile_result=compiled,
    )
```

Freeze the Rhino context once before any tool-capable handoff. Project only the unresolved leaf through the existing draft loader:

```python
draft = load_minimal_csharp_repair_draft(
    {
        "goal": partition.unresolved_leaf.goal,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [
                {
                    "name": partition.unresolved_leaf.interface.outputs[0].name,
                    "type": partition.unresolved_leaf.interface.outputs[0].type,
                }
            ],
        },
        "acceptance": "clean_compile_receipt",
    }
)
```

If this code-owned projection refuses, raise an internal contradiction. Run `run_minimal_csharp_initial_body_handoff()` once. Immediately after every return, compare the current Rhino context with the frozen context **before** inspecting terminal fields or returning an incomplete prefix. This includes Worker refusal, invalid response, create failure, and compile failure. If the handoff raises an ordinary exception, compare in the exception path before re-raising; context drift takes precedence. Only after the comparison may a non-clean handoff return the prefix without snapshot/edit/connect.

Extract the source GUID directly from the existing `create_script` receipt owned by the handoff's final graph:

```text
final_graph.nodes["create_script"].evidence.receipt
-> mutation.component_guid
```

Require one exact nonblank string. Missing or malformed GUID after a clean terminal is an internal contradiction. Do not parse or replay Worker records.

Call existing `_execute_compiled_plan()` with `partition.deterministic_plan`, then compare context again before inspecting or returning its result. If deterministic execution raises, compare in the exception path before re-raising; context drift takes precedence. If the deterministic result is not its direct terminal equation, return the prefix without connect only after that comparison.

Resolve the target GUID from the existing `structural_correlation` tuple by exact semantic target node ID. Require exactly one match. Build:

```python
connect_request = {
    "sourceGuid": source_guid,
    "sourceIndex": partition.cross_edge.source_output_index,
    "targetGuid": target_guid,
    "targetIndex": partition.cross_edge.target_input_index,
}
```

Compare context again, then invoke `gh_connect` once through existing `_invoke_tool()`. After a returned response, compare context before interpreting the response. Catch ordinary `Exception` only; in the exception path compare context before producing the incomplete result. Context drift takes precedence over either a returned failure or a dispatch exception. When context is unchanged, a dispatch exception retains the request, leaves response absent, and returns `completed=False` without error text.

Implement direct completion:

```python
def _connect_matches(response: object, request: dict[str, object]) -> bool:
    if type(response) is not dict or response.get("success") is not True:
        return False
    data = response.get("data")
    if type(data) is not dict or data.get("connected") is not True:
        return False
    source = data.get("source")
    target = data.get("target")
    return (
        type(source) is dict
        and type(target) is dict
        and type(source.get("guid")) is str
        and type(source.get("index")) is int
        and type(target.get("guid")) is str
        and type(target.get("index")) is int
        and source.get("guid") == request["sourceGuid"]
        and source.get("index") == request["sourceIndex"]
        and target.get("guid") == request["targetGuid"]
        and target.get("index") == request["targetIndex"]
    )
```

`SemanticGraphSingleWorkerLeafResult.__post_init__()` checks only exact immediate types, ordered optional-field presence, and the direct completed equation. It must not re-run loaders/compilers, walk nested histories, or reconstruct receipt lineage.

- [x] **Step 6: Run the walking vertical and adjacent Planner tests**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_semantic_graph_worker_leaf_runner.py::test_one_worker_leaf_composes_with_one_deterministic_region `
  tests/test_semantic_graph_runner.py `
  tests/test_minimal_csharp_initial_body_handoff.py
```

Expected: all pass. The walking test reports exactly one Planner, one Worker, one create, one snapshot, one edit, and one connect.

- [x] **Step 7: Commit Task 3**

```powershell
git add -- `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/src/rook/agent/semantic_graph_worker_leaf_runner.py `
  mcp_server/tests/test_semantic_graph_runner.py `
  mcp_server/tests/test_semantic_graph_worker_leaf_runner.py
git diff --cached --check
git commit -m "feat: compose one semantic worker leaf"
```

Stop for independent Task 3 review before expanding the unsuccessful matrix.
Report both the new compositor's production additions and cumulative production
additions across all four planned modules, counted without subtracting
deletions. Stop if the compositor exceeds roughly 350 additions or the
cumulative total exceeds roughly 650 additions.

Observed Task 3 evidence:

```text
walking/capability RED: 10 failed (NotImplementedError skeleton)
Planner-path RED: 1 failed (produce_worker_leaf absent)
prescribed walking/adjacent seam: 81 passed
complete Task 3 files plus adjacent seam: 90 passed
successful call budget:
  Planner 1, Worker 1, gh_create_csharp_script 1,
  gh_snapshot 1, gh_edit 1, gh_connect 1
commit: 75eaaf30abc5a37280b3d6b47b1c1635e10c387f
production additions since 8a2216d9:
  semantic_graph.py: 165
  semantic_graph_compiler.py: 207
  semantic_graph_runner.py: 34
  semantic_graph_worker_leaf_runner.py: 243
  total: 649
compileall: passed
git diff --check: passed
```

Task 3 review repair evidence:

```text
RED: 2 failed
  Worker context drift entered gh_create_csharp_script before refusal
  impossible connect-only prefix was accepted
focused repair GREEN: 2 passed
complete adjacent seam: 449 passed
repair commit: a3d2fb3893a571f21870dbd418166591302e6989
production additions since 8a2216d9:
  semantic_graph.py: 165
  semantic_graph_compiler.py: 207
  semantic_graph_runner.py: 34
  semantic_graph_worker_leaf_runner.py: 275
  total: 681
growth note: the 32-line delta above the approximate gate is the reviewed
  context guard and immediate predecessor equations; no scope expansion
compileall: passed
git diff --check: passed
renewed independent Task 3 approval: approved (449 passed)
```

---

## Task 4: Close the Bounded Prefix and Failure Matrix

**Files:**

- Modify: `mcp_server/tests/test_semantic_graph_worker_leaf_runner.py`
- Modify production only if one of these exact tests exposes a concrete local defect.

**Interfaces:**

- Consumes: completed Task 3 compositor and its thin prefix result.
- Produces: deterministic evidence that every expected stop preserves exact call counts and no forbidden continuation.

- [x] **Step 1: Add Planner/load/compiler stop tests**

Add tests proving:

```text
Planner transport failure:
  Planner entered once
  graph_load_result is None
  all later fields None
  zero Worker/tool calls

malformed raw JSON or invalid interface:
  graph_load_result retained with owned reason
  partition_compile_result None
  zero Worker/tool calls

zero Worker leaf:
  admitted graph and admitted zero-leaf partition retained
  Worker and tools remain zero
  completed False

compiler refusal, including occupied cross-edge target:
  partition_compile_result retained with owned reason
  zero Worker/tool calls
```

Do not add an aggregate stop reason.

- [x] **Step 2: Add Worker and C# compile stop tests**

Parameterize the existing response semantics:

```text
refusal
wrong action ID
extra mode field
blank code
malformed JSON response
```

For each, assert exactly one Planner call, one Worker call, and zero tool calls. Assert the existing handoff result owns its exact terminal stage/reason.

Add a causal compile-error receipt. Assert exactly:

```text
Planner 1
Worker 1
gh_create_csharp_script 1
gh_snapshot 0
gh_edit 0
gh_connect 0
```

Retain the failed handoff result and `completed=False`.

- [x] **Step 3: Add snapshot, edit, and connect prefix tests**

Use the causal executor with one controlled fault at a time:

```text
snapshot exception or malformed response:
  create 1, snapshot 1, edit 0, connect 0
  leaf handoff retained
  deterministic result retained at snapshot stop

edit failure, partial success, or structural verification stop:
  create 1, snapshot 1, edit 1, connect 0
  both owner results retained

connect returned failure/malformed/mismatched source/mismatched target:
  all four GH tools entered once
  exact request and raw response retained
  completed False

connect exception:
  exact request retained
  response None
  completed False
  exception type/message absent from result representation
```

Add direct context-precedence regressions for every post-contact exit:

```text
failed Worker handoff return after C# contact
raised Worker handoff exception after C# contact
failed deterministic execution return
raised deterministic execution exception
returned gh_connect failure
raised gh_connect exception
```

Each case changes the current Rhino context during that phase and asserts
`RuntimeError("Rhino context changed...")`, no later call, and no cleanup. The
failed handoff case specifically proves the comparison occurs before returning
its ordinary C# create/compile stop. The two connect cases prove drift takes
precedence over both a retained failed response and an exception-based
incomplete result.

- [x] **Step 4: Add direct result-shape tests without replay**

Use `dataclasses.replace()` only for immediate prefix inversions:

```text
completed=True with absent owner result
connect_response present without connect_request
deterministic result present without successful Worker handoff
later field present after an earlier absent field
```

Do not build a cross-transaction splice matrix. Do not replace nested graphs, records, receipts, prompts, or mappings. Existing owner results validate themselves.

- [x] **Step 5: Prove prompt, code, and call isolation**

Assert:

- Planner prompt contains the exact semantic interface and excludes generated code, `draft_create_body`, GUIDs, pin indices, `T1`, layout, and the witness edge text.
- Worker request contains the exact compiler-projected goal/interface and only `draft_create_body`.
- Worker-authored body appears in the Worker response and C# create request, not in Planner content, compiler partition, connect request, or aggregate parallel fields.
- Source GUID originates only in the create receipt.
- Target GUID originates only in Slice 1 structural correlation.
- `gh_update_script`, `draft_repair_params`, and a second Worker dispatch are unreachable.

- [x] **Step 6: Run the complete Task 4 seam**

Run:

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_semantic_graph.py `
  tests/test_semantic_graph_compiler.py `
  tests/test_semantic_graph_runner.py `
  tests/test_semantic_graph_worker_leaf_runner.py `
  tests/test_minimal_csharp_initial_body_handoff.py `
  tests/test_plan_graph_worker_create_body_apply.py `
  tests/test_local_worker_turn_context.py `
  tests/test_local_worker_turn_harness.py `
  tests/test_local_worker_adapter.py `
  tests/test_plan_graph_current_step_runner.py
```

Expected: all pass with no external contact.

- [x] **Step 7: Commit Task 4**

If Task 4 changes tests only:

```powershell
git add -- mcp_server/tests/test_semantic_graph_worker_leaf_runner.py
git diff --cached --check
git commit -m "test: close single worker leaf stop paths"
```

If a test exposes a concrete local defect, stop with the valid-red evidence and proposed smallest correction before editing production. Do not patch autonomously or expand the architecture.

Observed Task 4 evidence:

```text
pre-contact Planner/load/compiler matrix: 5 passed
Worker/compile receipt stops: 6 passed
snapshot/edit/connect prefixes: 10 passed
post-contact context precedence: 6 passed
immediate result shape: 1 passed
prompt/code/identity isolation: 1 passed
complete worker-leaf test file: 41 passed
complete prescribed Task 4 seam: 478 passed
commit: b04b572ec34266021547a69dd3ed93011c6b117e
production changes: none
external contact: none
git diff --check: passed
```

---

## Task 5: Final Verification and Plan Reconciliation

**Files:**

- Modify: `docs/superpowers/plans/2026-08-03-compositional-harness-single-worker-leaf.md`
- No production change is expected.

**Interfaces:**

- Consumes: reviewed Tasks 1–4.
- Produces: reproducible verification ledger and clean implementation-review HEAD.

- [ ] **Step 1: Run the focused Slice 2 seam**

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_semantic_graph.py `
  tests/test_semantic_graph_compiler.py `
  tests/test_semantic_graph_runner.py `
  tests/test_semantic_graph_worker_leaf_runner.py `
  tests/test_minimal_csharp_initial_body_handoff.py `
  tests/test_plan_graph_worker_create_body_apply.py
```

Record the exact passed count and warnings.

- [ ] **Step 2: Run the broader shared execution seam**

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_local_worker_turn_context.py `
  tests/test_local_worker_turn_request.py `
  tests/test_local_worker_turn_response.py `
  tests/test_local_worker_turn_harness.py `
  tests/test_local_worker_adapter.py `
  tests/test_plan_graph_worker_create_body_apply.py `
  tests/test_plan_graph_current_step_runner.py `
  tests/test_plan_graph_current_step_stream.py `
  tests/test_plan_graph_live_dispatch.py `
  tests/test_plan_graph_workflow_contract.py `
  tests/test_minimal_csharp_initial_body_handoff.py `
  tests/test_semantic_graph.py `
  tests/test_semantic_graph_compiler.py `
  tests/test_semantic_graph_runner.py `
  tests/test_semantic_graph_worker_leaf_runner.py
```

Record the exact passed count and warnings. Any new failure blocks completion.

- [ ] **Step 3: Compile and run source-surface checks**

```powershell
cd mcp_server
.\.venv\Scripts\python.exe -m compileall -q `
  src/rook/agent/semantic_graph.py `
  src/rook/agent/semantic_graph_compiler.py `
  src/rook/agent/semantic_graph_runner.py `
  src/rook/agent/semantic_graph_worker_leaf_runner.py
cd ..

rg -n 'gh_update_script|draft_repair_params|run_minimal_csharp_repair_handoff' `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/src/rook/agent/semantic_graph_worker_leaf_runner.py

rg -n 'construct_point\.x|Produce one numeric value|A = 7\.0' `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/src/rook/agent/semantic_graph_worker_leaf_runner.py

git diff --check
git status --short
```

Expected:

- compilation succeeds;
- both source scans return zero production matches;
- diff check passes;
- status contains only the plan-ledger reconciliation before its commit.

- [ ] **Step 4: Audit exact scope and production growth**

```powershell
git diff --name-only 8a2216d9...HEAD
git diff --stat 8a2216d9...HEAD
git diff --numstat 8a2216d9...HEAD -- `
  mcp_server/src/rook/agent/semantic_graph.py `
  mcp_server/src/rook/agent/semantic_graph_compiler.py `
  mcp_server/src/rook/agent/semantic_graph_runner.py `
  mcp_server/src/rook/agent/semantic_graph_worker_leaf_runner.py

$productionFiles = @(
  'mcp_server/src/rook/agent/semantic_graph.py',
  'mcp_server/src/rook/agent/semantic_graph_compiler.py',
  'mcp_server/src/rook/agent/semantic_graph_runner.py',
  'mcp_server/src/rook/agent/semantic_graph_worker_leaf_runner.py'
)
$totalProductionAdditions = 0
git diff --numstat 8a2216d9...HEAD -- $productionFiles | ForEach-Object {
  $totalProductionAdditions += [int](($_ -split "`t")[0])
}
"TOTAL_PRODUCTION_ADDITIONS=$totalProductionAdditions"
if ($totalProductionAdditions -gt 650) {
  throw 'Single Worker leaf production growth exceeded the scope gate'
}
```

Require exactly the planned production/test files plus this specification and plan. Report both the total production additions and the new compositor's production line count. Stop for scope review if total additions exceed roughly 650 lines, the compositor exceeds roughly 350 lines, or any unplanned product surface appears. Deletions do not offset either additions gate.

- [ ] **Step 5: Reconcile this ledger with observed evidence**

Mark only actually completed checkboxes. Record:

```text
Task 1 commit and focused count
Task 2 commit, focused count, and independent review approval
Task 3 commit, walking count, and independent review approval
Task 4 commit and full stop-matrix count
focused final count and warnings
broader final count and warnings
final implementation HEAD
exact changed-file list
total production additions across all four planned modules
new compositor production line count
```

Do not claim provider, Worker-box, Rhino, Grasshopper, or live semantic execution.

- [ ] **Step 6: Commit documentation-only reconciliation**

```powershell
git add -- docs/superpowers/plans/2026-08-03-compositional-harness-single-worker-leaf.md
git diff --cached --check
git commit -m "docs: reconcile single worker leaf plan"
git show --check --stat --oneline HEAD
git status --short --branch
```

Expected: clean worktree. Stop for final independent implementation review. Do not push, open a PR, merge, or perform live qualification without separate authorization.

---

## Execution Checkpoints

1. **Task 1:** strict loader, immutable interface, provider schema, and prompt projection.
2. **Task 2:** compiler-owned partition and cross-edge validation.
3. **Mandatory independent review:** Tasks 1–2 approved before compositor creation.
4. **Task 3:** one complete walking composition with exact successful call budget.
5. **Independent Task 3 review:** verify the compositor remains thin before adding stop tests.
6. **Task 4:** bounded unsuccessful matrix and immediate result-shape checks.
7. **Task 5:** final verification, scope audit, plan reconciliation, and implementation review stop.

The post-merge live witness remains separately authorized. It may use existing ordinary diagnostic tracing; this plan creates no live launcher, recorder, UI, or product route.
