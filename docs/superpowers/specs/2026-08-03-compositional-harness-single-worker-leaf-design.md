# Compositional Harness Single Worker Leaf Design

**Date:** 2026-08-03

**Status:** Approved design; implementation not started

**Baseline:** `48dc2f200348c4f34454ad9c6d0bdb819c097ddc`

**Branch:** `codex/compositional-harness-single-worker-leaf-design`

## Purpose

Slice 2 proves one new freedom:

> A compiled Grasshopper semantic transaction may contain exactly one unresolved
> C# body leaf. One existing Worker turn supplies that body, after which the
> existing deterministic transaction continues and native receipts determine the
> result.

The intended successful path is:

```text
one Planner response
-> strict semantic-graph loading
-> compiler-owned deterministic/Worker partition
-> one existing Worker-first C# handoff
-> one clean C# create receipt
-> one snapshot
-> one gh_edit deterministic batch
-> one verified gh_connect
-> completed ephemeral result
```

This slice composes two already-proven capabilities. It does not independently
re-prove general Worker code authoring or variable deterministic topology.

## Architectural warning and containment

The read-only splice audit found one real anti-quagmire constraint: the existing
Worker-first contract supports only this interface:

```yaml
inputs: []
outputs:
  - name: A
    type: double
```

Slice 2 does not generalize that contract. The Planner must explicitly author the
interface, and the compiler admits only that exact shape. Variable Worker inputs,
multiple outputs, other pin types, and multiple Worker leaves remain unsupported.

No PlanGraph core change, runtime component discovery, or new Worker action is
required.

## Reused production seams

The design reuses these existing boundaries unchanged:

- `SemanticGraphLoadResult` and strict raw-JSON loading;
- the Slice 1 primitive tuple, deterministic compiler, epoch-free edit plan, and
  deterministic execution result;
- `draft_create_body` and its code-only Worker response;
- the existing Worker adapter, context, one-shot harness, disposition, and
  copy-on-write applicator;
- `run_minimal_csharp_initial_body_handoff()` and its clean compile receipt;
- `gh_snapshot`, `gh_edit`, and their current normalized results;
- `gh_connect` and its current normalized response;
- existing PlanGraph runners, typed-tool execution, and native receipt ownership.

The only missing product behavior is a fixed compositor over one compiler-owned
partition.

## Considered approaches

### Approach 1: connected source-only Worker leaf — selected

Compile one Worker-backed source node plus a deterministic region. Execute the
existing Worker-first handoff, execute the existing deterministic transaction,
then connect their receipt-derived identities with one `gh_connect` call.

This proves actual structural composition without a new identity or scheduling
system.

### Approach 2: isolated Worker leaf

Run the Worker-backed component beside a deterministic graph without connecting
them. This is smaller, but it proves only aggregation of two independent results,
not composition of their topology.

### Approach 3: extend `gh_edit` to create script bodies

This could place everything in one edit batch, but it would change the managed
tool contract and require new qualification. It exceeds Slice 2 and is rejected.

## Semantic graph representation

The existing semantic-node envelope remains unchanged. One new exact primitive
variant is admitted:

```json
{
  "id": "generated_value",
  "primitive": "csharp_script",
  "parameters": {
    "goal": "Produce the requested numeric value.",
    "interface": {
      "inputs": [],
      "outputs": [
        {"name": "A", "type": "double"}
      ]
    }
  }
}
```

`csharp_script` is the only unresolved primitive in this slice.

### Goal admission

`goal` must be:

- an exact built-in `str` after strict JSON loading;
- nonblank without trimming or normalization;
- between 1 and 4,096 characters;
- at most 16,384 bytes under strict UTF-8 encoding.

UTF-8 encoding failures, including escaped lone surrogates, refuse at graph
admission. Admitted text is copied byte-for-byte into the compiler-owned leaf and
then into the existing Worker-visible goal context.

### Interface admission

`interface` has closed keys and this exact value:

```json
{
  "inputs": [],
  "outputs": [
    {"name": "A", "type": "double"}
  ]
}
```

There are no aliases, defaults, coercions, alternative names, alternative types,
or case folding. The semantic output pin is exactly `A`.

The Planner authors `goal` and `interface`. The compiler does not inject or
rewrite either field. Capability selection, clean-compile acceptance, body mode,
tool selection, and all non-code execution parameters remain code-owned.

## Graph admission

The shared semantic language remains compatible with Slice 1:

- zero Worker leaves remain valid for the existing deterministic Slice 1 path;
- the Slice 2 compositor requires exactly one admitted Worker leaf;
- more than one Worker leaf always refuses;
- the Worker leaf has no incoming edges;
- it has exactly one outgoing edge;
- the outgoing source pin is exactly `A`;
- the target is an admitted deterministic primitive input whose element type is
  exactly `Number`;
- the full graph remains acyclic and obeys existing node/edge bounds.

All edges are validated in the complete semantic graph before partitioning. The
cross-edge counts against the target pin's code-owned `max_connections`. No
deterministic edge may occupy the same target input.

After successful full-graph validation, the cross-edge is excluded from the
deterministic `gh_edit` plan and retained only in the compiler-owned partition.

The production prompt and production logic contain no witness name, expected
witness topology, `construct_point.x`, or other example-specific branch.

## Compiler-owned partition

The compiler returns one immutable partition compilation result. Its admitted
payload contains:

```text
deterministic_plan:
  existing EpochFreeEditPlan

unresolved_leaf:
  semantic node ID
  exact admitted goal
  exact admitted interface

cross_edge:
  source semantic node ID
  source pin A
  source output index 0
  target semantic node ID
  target semantic pin
  compiler-resolved target input index
```

The partition compiler accepts zero or one Worker leaf so shared compilation
remains Slice 1 compatible. The Slice 2 compositor refuses an otherwise admitted
zero-leaf partition because this entry point exists specifically to exercise one
Worker leaf.

The compiler alone identifies and removes the unresolved leaf and cross-edge from
the deterministic edit plan. The compositor never rereads the raw Planner graph,
reconstructs topology, or independently resolves semantic pins.

`csharp_script` cannot enter the deterministic `gh_edit` create instructions or
receive a `T*` identifier.

## Identity ownership

Slice 2 reuses existing identities:

```text
Worker leaf semantic ID
-> existing C# create receipt component GUID

deterministic semantic ID
-> existing gh_edit T ID
-> existing gh_edit instance GUID
```

The cross-edge is materialized using those two returned GUIDs and the
compiler-owned pin indices. There is no new short-ID family, semantic-ID registry,
persistent correlation store, GUID inference, or snapshot reconstruction.

## Fixed execution sequence

The successful sequence is code-owned and fixed:

1. Invoke the Planner adapter exactly once.
2. Pass the raw response unchanged to `load_semantic_graph()`.
3. Compile the complete graph into the immutable partition.
4. Project only the compiler-owned unresolved leaf into the existing fixed
   `ValidatedPlannerDraft` shape.
5. Run `run_minimal_csharp_initial_body_handoff()` exactly once.
6. Require its existing clean terminal result.
7. Run the existing deterministic Slice 1 execution over the retained
   `EpochFreeEditPlan`.
8. Require `terminal_stage == "terminal"` and
   `terminal_reason == "terminal_node_selected:done"`.
9. Construct and dispatch exactly one `gh_connect` request from the partition and
   the two native identity owners.
10. Verify its direct normalized result and stop.

The fixed draft projection is exactly:

```text
goal = unresolved_leaf.goal
capability = grasshopper_csharp_component       # code-owned
interface = unresolved_leaf.interface
acceptance = clean_compile_receipt              # code-owned
```

It passes through the existing strict draft loader. A refusal after successful
partition compilation is an internal compiler/compositor contradiction, not an
operational Planner stop.

One frozen Rhino request context and the same injected tool executor cover C#
create, snapshot, edit, and connect.

Snapshot begins only after the existing C# receipt proves a clean compile.
`gh_connect` begins only after `gh_edit` proves structural materialization and
both endpoint identities are available.

Contradictions among code-owned/compiler-owned objects or Rhino request-context
drift raise as internal contract failures. Ordinary model or tool failures return
the completed result prefix.

The sequence is not a scheduler. It has no suspension, resumption, queue, job,
loop, or generalized execution phase.

## Call budget and partial mutation

| Stop | Planner | Worker | C# create | Snapshot | Edit | Connect |
|---|---:|---:|---:|---:|---:|---:|
| Planner or graph refusal | 1 | 0 | 0 | 0 | 0 | 0 |
| Worker refusal or invalid response | 1 | 1 | 0 | 0 | 0 | 0 |
| C# create or compile stop | 1 | 1 | 1 | 0 | 0 | 0 |
| Snapshot stop | 1 | 1 | 1 | 1 | 0 | 0 |
| Edit stop | 1 | 1 | 1 | 1 | 1 | 0 |
| Connect stop or completion | 1 | 1 | 1 | 1 | 1 | 1 |

There are always zero updates, retries, repairs, fallbacks, replans, cleanup
calls, resnapshots, and second Worker calls.

Operational stops retain truthful partial mutation:

- the C# leaf may remain after snapshot failure;
- the leaf and partially or fully edited deterministic region may remain after
  edit failure;
- both created regions remain after connect failure.

No cleanup is attempted.

## Connection request and response

The request uses only code-owned indices and returned GUIDs:

```text
sourceGuid = Worker create receipt component GUID
sourceIndex = 0
targetGuid = gh_edit correlation GUID for cross_edge.target_node
targetIndex = cross_edge.target_input_index
```

Completion reads the existing normalized response keys exactly:

```text
success
data.connected
data.source.guid
data.source.index
data.target.guid
data.target.index
```

The connection portion passes only when:

```text
success is true
data.connected is true
data.source.guid == requested sourceGuid
data.source.index == requested sourceIndex
data.target.guid == requested targetGuid
data.target.index == requested targetIndex
```

A failed, malformed, or identity-mismatched returned `gh_connect` response is
operational evidence. It is retained and produces `completed=False`; it does not
raise. Only contradictions among already code-owned/compiler-owned objects raise.

## Thin ephemeral result

The compositor returns one bounded prefix aggregate:

```text
planner_record
graph_load_result?
partition_compile_result?
worker_handoff_result?
deterministic_execution_result?
connect_request?
connect_response?
completed
```

It retains the existing `SemanticGraphLoadResult`, the compiler-owned partition
compilation result, the existing Worker-handoff result, the existing deterministic
execution result, and the exact connect request/response directly.

Optional fields appear only after their owning boundary is reached. Failed raw
responses remain available for ordinary diagnostics.

`completed` is the only new outcome projection. It is true exactly when:

```text
the existing Worker handoff reports its clean terminal
AND
the deterministic result reports terminal_node_selected:done
AND
the direct gh_connect response equation passes
```

Aggregate validation checks immediate prefix shape and these direct terminal
properties. It does not replay native histories, recompile retained objects,
reconstruct graphs, prove transitive lineage, or introduce another stage/reason
taxonomy.

The result is ephemeral operational state, not durable or self-authenticating
evidence.

## Planner boundary

The Slice 2 Planner prompt contains only:

- the exact user intent;
- the existing deterministic semantic primitive projection;
- the exact `csharp_script` semantic shape and ownership rules;
- closed semantic graph output instructions.

It contains no GUIDs, GH pin indices, layout values, `T*` IDs, Worker action,
body-mode field, generated code, expected code, receipt, tool request, or witness
topology.

The adapter makes one transport call. Its raw response reaches the existing strict
loader unchanged. There is no parsing repair, retry, fallback, or deterministic
graph patching.

## Deterministic test strategy

The primary fake-backed witness exists only in tests:

```text
csharp_script.A -> construct_point.x
```

The causal test path is:

```text
raw Planner JSON
-> real strict loader
-> real partition compiler
-> fake Worker transport through the real Worker adapter/harness/action
-> real code-only applicator
-> causal fake typed tool executor
-> existing C# receipt interpretation
-> existing deterministic Slice 1 transaction
-> one verified connect response
-> completed result
```

The fake executor must derive each response from the received request:

- the C# receipt comes from the exact Worker-authored `code` parameter;
- the leaf GUID originates only in that receipt;
- deterministic mappings and GUIDs derive from the actual `gh_edit` request;
- `gh_connect` accepts only the receipt-derived source, edit-derived target, and
  compiler-owned indices.

Focused tests prove:

- exactly one Planner response and one admitted graph;
- prompt inclusion of semantic leaf vocabulary and exclusion of execution
  internals and witness topology;
- zero-leaf Slice 1 compatibility;
- Slice 2 zero-leaf refusal and multi-leaf refusal;
- strict goal bounds, UTF-8 refusal, interface closure, and exact case-sensitive
  `A`;
- no incoming leaf edge, exactly one outgoing edge, Number-only target, cycle
  refusal, and full-graph connection multiplicity;
- no deterministic edge may occupy the cross-edge target;
- `csharp_script` never enters `gh_edit` creation;
- Worker code is the exact body sent to C# creation;
- Worker refusal, malformed response, or rejected action causes zero GH calls;
- compile failure causes zero deterministic-region mutation;
- exact call prefixes for snapshot, edit, and connect failures;
- malformed or mismatched connect evidence returns `completed=False`;
- no update, retry, repair, fallback, replan, cleanup, or second Worker call is
  reachable;
- neither production prompt nor production behavior depends on the witness.

All development tests use fake Planner, Worker, and tool transports at approved
external boundaries. No provider, Worker box, Rhino, or Grasshopper contact is
authorized during specification, planning, implementation, or review.

## Expected implementation surface

Implementation should remain within a few focused semantic-harness modules:

- `semantic_graph.py`: the exact unresolved node variant and Planner schema
  projection;
- `semantic_graph_compiler.py`: full-graph validation and immutable partition;
- one thin semantic-graph Worker-leaf compositor reusing the current Slice 1
  executor and Worker-first handoff;
- focused tests for those boundaries.

Existing Worker-first modules, PlanGraph core, tool endpoints, managed code,
knowledge systems, and product UI remain unchanged. If implementation requires a
general scheduler, descriptor discovery, PlanGraph change, or broader interface
system, work stops for scope review.

## Explicit non-claims

Slice 2 does not prove or introduce:

- variable Worker interfaces;
- Worker inputs, multiple outputs, or alternative pin types;
- more than one Worker leaf;
- Worker sinks or bidirectional Worker topology;
- multiple cross-edges;
- runtime value or broader semantic correctness;
- atomic mutation or rollback;
- repair, retry, replanning, or fallback;
- generalized suspension or scheduling;
- knowledge retrieval or DSPy optimization;
- product UI or Chat integration;
- a new trace, archive, proof, or evaluation system.

A post-merge live witness requires separate authorization. It may reuse existing
ordinary diagnostic tracing; Slice 2 adds no recorder.
