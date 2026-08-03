# Compositional Harness Slice 1: Variable Grasshopper Topology Design

**Date:** 2026-08-02

**Status:** Proposed for independent specification review

**Branch:** `codex/compositional-harness-variable-topology-design`

**Dependent base:** `65108bcbd00f572dc65203d39ecb8890dbd5c98f`

**Audit baseline:** `93fe02e58836934edf836c13a3a92439328616b8`

**Scope:** One Planner-authored Grasshopper semantic graph, one deterministic
compiler, one snapshot, one `gh_edit` batch, and one bounded ephemeral execution
result

**Authorization:** Specification work only. No provider, Worker, Rhino,
Grasshopper, product UI, or live mutation contact is authorized.

## 1. Purpose

The Slice 0 fit audit selected a small prospective semantic graph rather than the
existing v2 recipe graph. The audit found that v2 recipes preserve useful topology
precedents but lose or weaken the component identity, typed-port, state, validation,
and receipt-correlation facts required for prospective execution authority.

Slice 1 introduces one new freedom:

> A frontier Planner may vary a Grasshopper definition's nodes, parameters, and
> wiring inside one small code-owned primitive vocabulary, while a deterministic
> compiler validates and lowers the complete design before canvas mutation.

The transaction is:

```text
exact user intent
-> one Planner call
-> strict prospective semantic graph loader
-> complete graph admission and canonicalization
-> total deterministic lowering to an epoch-free edit plan
-> one gh_snapshot call
-> one gh_edit batch
-> fixed create_edit / verify_edit / done PlanGraph
-> bounded ephemeral execution result
```

This is a Grasshopper-only deterministic slice. There is no Worker, retry,
replanning, reusable subgraph, Rhino operation, product UI, knowledge lookup, DSPy
optimizer, or stored-recipe migration.

## 2. Falsifiable hypothesis

> Given one of two materially different intents, a frontier Planner can compose a
> valid graph from five deterministic Grasshopper primitives; the compiler can
> reject unsupported or contradictory graphs before contact, lower admitted graphs
> without discretion, and correlate one returned `gh_edit` result to every requested
> semantic node and edge.

Success for a transaction proves only:

```text
requested nodes and wires materialized
+ correlation maps are complete and consistent
+ no edit errors were returned
```

It does not prove runtime values, geometric correctness, semantic fidelity,
repeatability, broad intent coverage, or general Grasshopper support.

The slice is unsuccessful if either witness requires:

- a witness-specific production branch or hidden graph template;
- a Worker, retry, fallback, graph repair, or second edit;
- runtime knowledge or component discovery to change admission;
- a general list/tree type system or integer-slider feature;
- a new identity registry, receipt taxonomy, trace subsystem, or archive; or
- changes to historical v2 recipes.

## 3. Considered approaches

### 3.1 Small prospective graph plus thin runner — selected

Add one strict semantic graph contract, one deterministic compiler, and one thin
runner. The semantic graph describes what to build. The existing `PlanGraph`
describes how the already-admitted batch progresses through execution.

This creates the missing prospective language without changing the meaning of v2
recipes or execution-control graphs.

### 3.2 Strict profile over the v2 recipe graph — rejected

This would require parallel strict rules around a representation that permits names
instead of stable identities, retains authored positions, omits typed pin contracts,
and contains malformed historical examples. Identical-looking v2 records would carry
different authority depending on their entry path.

### 3.3 Grasshopper components as workflow nodes — rejected

Encoding each semantic component as a `RookWorkflowContract` or `PlanGraph` node
would conflate Grasshopper dataflow with execution control. The batch still needs
separate snapshot, edit, verification, and terminal progression, so this approach
would create two intertwined graphs rather than remove one.

## 4. Graph roles and ownership

The graph roles remain separate:

| Role | Owner | Meaning |
|---|---|---|
| Prospective semantic graph | Planner within a closed vocabulary | What nodes, parameters, and wires to build |
| Primitive meaning | Private code-owned tuple | GUIDs, pin contracts, parameter bounds, and lowering kinds |
| Epoch-free edit plan | Deterministic compiler | Complete create/connect batch without canvas epoch |
| Execution `PlanGraph` | Runner | `create_edit -> verify_edit -> done` transaction progress |
| Canvas identities and edit evidence | Existing `gh_snapshot` and `gh_edit` contracts | Current epoch, created mappings, native identities, returned topology, and errors |

The Planner owns only:

- local node symbols;
- primitive selection;
- closed primitive parameters; and
- semantic pin-to-pin edges.

The compiler owns:

- primitive interpretation;
- Grasshopper component GUIDs;
- exact pin indices and compatibility rules;
- connection limits;
- canonical ordering;
- cycle analysis;
- layout;
- `T*` assignment; and
- lowering to existing `gh_edit` request syntax.

The runner owns snapshot/edit sequencing and the fixed execution graph. Existing
tool results and native PlanGraph records remain authoritative for execution facts.

## 5. Strict semantic graph contract

The Planner returns one JSON object:

```json
{
  "schema": "rook.gh_semantic_graph:v1",
  "nodes": [
    {
      "id": "local_symbol",
      "primitive": "number_slider",
      "parameters": {
        "label": "Value",
        "minimum": 0.0,
        "maximum": 10.0,
        "initial": 5.0
      }
    }
  ],
  "edges": [
    {
      "from_node": "source",
      "from_pin": "value",
      "to_node": "target",
      "to_pin": "input"
    }
  ]
}
```

The top-level object has exactly `schema`, `nodes`, and `edges`. Node and edge
objects have exactly the shown structural fields. All primitives require a
`parameters` object; primitives without authored parameters require it to be empty.

The lexical and size bounds are:

```text
complete Planner response: <= 65,536 UTF-8 bytes
nodes:                    1–16
edges:                    0–24
node ID:                  [a-z][a-z0-9_]{0,47}
slider label:             exact str, 1–64 characters, 1–256 UTF-8 bytes,
                          at least one non-whitespace character
```

Node IDs are opaque local symbols. Their spelling never selects behavior. Renaming
a node and consistently updating its edges changes identity but not semantics.

Pin and primitive names are exact and case-sensitive. There are no aliases, fuzzy
matches, coercions, defaults for missing authored fields, markdown extraction, or
deterministic repairs.

Strict JSON decoding rejects:

- duplicate keys at every depth;
- non-finite numbers;
- trailing content;
- non-object roots;
- unknown or missing fields;
- values of the wrong JSON type; and
- malformed UTF-8 or values that cannot satisfy a stated UTF-8 bound.

This strict JSON boundary is the untrusted-value boundary. Implementation tests use
actual JSON text and compact table-driven rejection cases. Slice 1 does not add
carrier-authenticity, Python-subclass, source-provenance, or exhaustive mutation
machinery around already-admitted internal values.

## 6. Private primitive authority

`semantic_graph.py` owns one private immutable tuple. It is a small compiler table,
not a registry. Entries are inert data, not per-primitive classes, callbacks, or
plugins.

The tuple contains exactly:

```text
number_slider
series
construct_point
polyline
square_grid
```

Each entry records only:

- semantic primitive name;
- lowering kind (`slider` or `component_guid`);
- fixed Grasshopper component GUID where applicable;
- exact semantic input/output pin names;
- fixed Grasshopper pin index, element type, access, and observed `gh_optional`
  metadata;
- input `max_connections` and the separate code-owned `connection_required` policy;
  and
- closed parameter fields and necessary bounds.

The candidate regular-component identities to qualify are:

| Semantic primitive | Grasshopper identity |
|---|---|
| `series` | `e64c5fb1-845c-4ab1-8911-5f338516ba67` |
| `construct_point` | `3581f42a-9592-4549-bd6b-1c0fc39d067b` |
| `polyline` | `71b5b089-500a-4ea6-81c5-2f960441a0e8` |
| `square_grid` | `717a1e25-a075-4530-bc80-d43ecc2500d9` |

`number_slider` lowers through the existing `gh_edit` special `type: "slider"`
creator. Returned verification uses the existing snapshot special identity for a
slider; Slice 1 does not invent a parallel identity.

The slider's `value -> output 0 / Number / item` row is an explicit code-owned
special-lowering convention. The current `gh_snapshot` simple-parameter shape
exposes `NumberSlider` identity and slider range/value data, but deliberately does
not expose input/output port records. Slice 1 therefore does not claim that the
slider port row was snapshot-qualified and does not change `gh_snapshot` to make it
so.

The semantic pins are:

| Primitive | Inputs | Outputs |
|---|---|---|
| `number_slider` | none | `value` |
| `series` | `start`, `step`, `count` | `values` |
| `construct_point` | `x`, `y`, `z` | `point` |
| `polyline` | `vertices`, `closed` | `curve` |
| `square_grid` | `plane`, `cell_size`, `extent_x`, `extent_y` | `cells`, `points` |

The candidate compiler pin projection is:

| Primitive | Semantic pin | GH direction/index | Element type | Access | Observed `gh_optional` | `connection_required` |
|---|---|---|---|---|---|---|
| `number_slider` | `value` | output 0 | Number | item | not exposed | n/a |
| `series` | `start` | input 0 | Number | item | `false` | `false` |
| `series` | `step` | input 1 | Number | item | `false` | `false` |
| `series` | `count` | input 2 | Integer | item | `false` | `false` |
| `series` | `values` | output 0 | Number | list | `false` | n/a |
| `construct_point` | `x` | input 0 | Number | item | `false` | `false` |
| `construct_point` | `y` | input 1 | Number | item | `false` | `false` |
| `construct_point` | `z` | input 2 | Number | item | `false` | `false` |
| `construct_point` | `point` | output 0 | Point | item | `false` | n/a |
| `polyline` | `vertices` | input 0 | Point | list | `false` | `true` |
| `polyline` | `closed` | input 1 | Boolean | item | `false` | `false` |
| `polyline` | `curve` | output 0 | Curve | item | `false` | n/a |
| `square_grid` | `plane` | input 0 | Plane | item | `false` | `false` |
| `square_grid` | `cell_size` | input 1 | Number | item | `false` | `false` |
| `square_grid` | `extent_x` | input 2 | Integer | item | `false` | `false` |
| `square_grid` | `extent_y` | input 3 | Integer | item | `false` | `false` |
| `square_grid` | `cells` | output 0 | Rectangle | item | `false` | n/a |
| `square_grid` | `points` | output 1 | Point | tree | `false` | n/a |

The semantic names in this table are the prospective graph's exact, case-sensitive
compiler aliases. They are not required to equal Grasshopper's snapshot `name` or
`nick` strings. Qualification matches each regular-component pin by its qualified
component GUID plus direction and index, then checks the returned element type,
access, and physical `optional` metadata. Grasshopper's `Optional` property does not
define whether the prospective language requires a connection: the separate
code-owned `connection_required` policy requires only `polyline.vertices`, while all
other current inputs may remain unconnected and use Grasshopper-owned defaults or
persistent data. This avoids a second alias map and keeps semantic names out of
runtime discovery.

The four regular-component GUID and pin rows become reviewed code-owned constants
only after the one-time qualification in section 6.1 succeeds. The slider's special
identity and range/value shape are independently qualified there; its output row
remains the explicit compiler convention above. Knowledge data is supporting
evidence, not a qualification source or runtime authority. The Planner never sees or
authors the indices.

Every admitted input in Slice 1 has `max_connections = 1`. Pin access metadata is
retained exactly, but access is not edge cardinality. The compiler does not require
source and target access equality and does not infer list/tree propagation.
Grasshopper owns runtime data matching.

Edge admission checks compatible element types plus the few explicit code-owned
compatibility rules required by these primitives. A number-slider connection to an
integer input requires its admitted initial value to be finite and integral. This is
only an admission constraint for the initial transaction. The component remains an
ordinary number slider; Grasshopper owns subsequent conversion and runtime behavior.

Only `number_slider` has authored parameters:

```text
label:   bounded exact string
minimum: exact finite JSON number
maximum: exact finite JSON number
initial: exact finite JSON number
```

It must satisfy `minimum <= initial <= maximum`. Boolean values are not numbers.
All three numbers must lie in the closed range `[-1,000,000, 1,000,000]`. A slider
connected directly to `series.count`, `square_grid.extent_x`, or
`square_grid.extent_y` must have an integral initial value in `[1, 100]`. This is a
bounded initial-execution admission rule, not a persistent integer guarantee. Slice
1 adds no integer-slider mode or slider feature.

Knowledge records and historical recipes may support review and tests, but neither
is read at runtime and neither can modify the tuple. A later separately authorized
live witness run may expose component drift. Drift must fail visibly; it must never
update the tuple automatically or trigger another qualification path.

There is no registry API, catalog loader, fingerprint, migration system, generic
component introspection, or plugin extension point.

### 6.1 One-time primitive qualification prerequisite

Production implementation must not begin until one separately authorized,
read-only qualification has produced this ordinary static test fixture:

```text
mcp_server/tests/fixtures/gh_semantic_graph_slice1_primitives_snapshot.json
```

An operator manually prepares a disposable Grasshopper canvas containing exactly one
instance of each of the five primitives and no wires. The qualification makes one
`gh_snapshot` call and no mutation call. The fixture is the exact returned snapshot
body. The fixed qualification request remains in the Task 0 procedure; it is not
duplicated inside the fixture. Tool-call success belongs to the outer invocation
envelope and is checked before accepting the body, not invented as an inner snapshot
field. The future runner continues to consume its existing `ToolDispatcher` envelope
separately and unchanged.

The fixture must independently expose enough existing snapshot evidence to review:

- each regular component GUID;
- every regular-component input and output direction/index, element type, access,
  and exact observed `optional: false` metadata;
- the absence of unexpected variable pins on those four regular components;
- the slider's existing `NumberSlider` special identity; and
- the slider value payload's `type: "slider"` plus finite numeric `val`, `min`, and
  `max` shape satisfying `min <= val <= max`.

Snapshot `name` and `nick` values are retained as captured diagnostics but are not
compared with the semantic aliases. Component runtime warnings and errors are also
retained but ignored for metadata qualification: an unwired component such as
Polyline may legitimately report a missing required input. Qualification rejects a
placeholder or `BROKEN` component entry, not ordinary runtime diagnostics.

The fixture is captured from Grasshopper, never generated from the candidate table.
A focused test projects the fixture through its existing contracted fields and
requires exact agreement with the private tuple for the fixture-owned facts above,
including physical `optional: false` metadata. The test independently checks the
code-owned `connection_required` policy and slider output convention without
mislabeling either as snapshot evidence. Production code never reads the fixture.
Runtime admission never performs component discovery.

If the snapshot omits a required regular-component fact, disagrees with a candidate
regular GUID/index/type/access/physical-optional value, or fails to expose the slider
identity/range/value shape, qualification stops. The specification and witness choice
must be reviewed rather than guessing, weakening the comparison, or updating the
tuple automatically.

General simple-parameter port parity in `gh_snapshot` is a legitimate product
observability improvement, but it is deferred. It should be handled as one additive,
general-purpose slice across supported simple-parameter families rather than as a
Number Slider exception shaped around this witness.

This is one static regression fixture, not a registry, manifest, archive, runtime
probe, recurring qualification system, or authority framework. Capturing it requires
separate explicit authorization and is prohibited during specification, planning,
or review.

## 7. Planner boundary

The Planner boundary uses one exact code-owned adapter and one injected structural
transport. Provider, model, credentials, and generation construction remain outside
the semantic graph modules.

The adapter:

1. validates an exact built-in nonblank intent string of at most 16,384 UTF-8 bytes;
2. renders one immutable prompt snapshot;
3. materializes a fresh mutable transport request;
4. calls the transport exactly once;
5. captures the raw returned value or ordinary transport failure; and
6. passes that returned value unchanged to the single strict graph loader.

The graph loader first requires an exact built-in string, measures the complete raw
UTF-8 response bound, and then owns all decoding, duplicate-key detection, JSON
parsing, structural validation, and semantic admission. No decoded mapping crosses
from the adapter into the loader. A transport exception stops at `planner`; any
returned value rejected by the loader stops at `graph_admission`.

There is no retry, fallback, prompt repair, prose classifier, graph patch, or second
Planner call.

The prompt contains:

- the exact intent;
- the closed graph output shape;
- the semantic projection of the five-entry tuple;
- exact semantic pin and parameter meanings; and
- the requirement to return one JSON object.

The prompt excludes:

- component GUIDs;
- GH pin indices;
- layout constants or coordinates;
- `T*`, `C*`, and instance identities;
- execution PlanGraph details;
- either witness name, intent, or expected topology;
- knowledge-store content; and
- expected output graphs.

The prompt projection and compiler tuple have one code-owned source so their
vocabulary cannot drift independently. Tests inspect the exact rendered prompt and
prove one Planner call.

## 8. Admission and canonicalization

After strict loading, graph admission performs:

1. schema and global-bound checks;
2. unique node-ID checks;
3. primitive and parameter checks through the private tuple;
4. exact source/output and target/input resolution;
5. duplicate-edge refusal;
6. self-edge refusal;
7. per-input connection-count checks;
8. required-input connection checks;
9. closed element-type compatibility checks, with the Number-to-Integer initial-value
   exception available only to `number_slider` sources;
10. cycle detection across all nodes and edges; and
11. complete graph-input lowerability checks for every node and edge.

Every self-edge and every cycle refuses. Unknown primitives, pins, parameters,
or incompatible connections refuse before any GH call. A code-owned tuple entry with
an unknown lowering kind cannot be authored by the Planner; encountering one is an
internal compiler contradiction and raises.

Canonical form is:

```text
nodes:      sorted by node ID
edges:      sorted by (from_node, from_pin, to_node, to_pin)
parameters: existing canonical JSON key ordering
```

Declaration order is not semantic. Two JSON inputs that differ only in node, edge,
or parameter declaration order produce the same admitted graph and epoch-free edit
plan.

Expected graph or compiler refusals end at `graph_admission`. Once admission
succeeds, lowering is total. An impossible contradiction between an admitted tuple
entry and its lowerer is an internal contract violation and raises; it is not
reported as an ordinary compilation stage.

## 9. Deterministic epoch-free lowering

Canonical node order assigns existing `gh_edit` temp IDs:

```text
first canonical node  -> T1
second canonical node -> T2
...
```

The compiler does not define a new short-ID family. Semantic edges lower directly
to existing flow syntax such as `T1.O0>T2.I1`.

Layout reuses cycle analysis:

```text
x position = fixed origin + topological depth * fixed horizontal spacing
y position = fixed origin + node index within that depth * fixed vertical spacing
```

Node ID is only the tie-break within a depth. It does not select primitives,
parameters, behavior, or special layout.

The compiler returns one immutable epoch-free edit plan containing:

- the complete canonical `create` array;
- the complete canonical `connect` array;
- semantic node ID to existing `T*` correlation; and
- semantic edge endpoint tuple to lowered flow correlation.

It contains no snapshot epoch. It contains no delete, disconnect, update, group, or
existing-canvas `C*` reference.

No production condition recognizes the point-row witness, square-grid witness, or
their expected node combinations. Primitive-specific lowering facts may appear only
as tuple data or the two closed lowering kinds.

## 10. Snapshot and edit execution

Only after the complete epoch-free plan exists may execution contact Grasshopper.

The runner uses the same injected tool executor and the same frozen Rhino request
context for both calls:

```text
gh_snapshot
gh_edit
```

The call budget is exact:

```text
invalid graph:                    0 GH calls
valid graph, snapshot failure:    1 snapshot, 0 edits
valid graph, edit attempted:      1 snapshot, 1 edit
```

The snapshot request and existing contracted response are retained in the ephemeral
result. Only the exact admitted epoch becomes authority for the edit request. The
snapshot does not change semantic admission, primitive meaning, topology, layout, or
lowering.

Malformed snapshot evidence or a missing/invalid epoch stops at `snapshot` with zero
edit calls. There is no polling, resnapshot, retry, fallback epoch, or repair.

After snapshot admission the runner materializes exactly:

```text
epoch-free create/connect plan + admitted epoch -> final gh_edit request
```

The fixed execution `PlanGraph` has only:

```text
create_edit -> verify_edit -> done
```

Both edges are `requires`. `create_edit` owns the single `gh_edit` call.
`verify_edit` is deterministic evaluation of evidence already returned by that call;
it makes no tool call. `done` is the terminal node. Semantic GH nodes never become
execution PlanGraph nodes.

Stale-epoch rejection is an ordinary `edit` stop. There is no resnapshot, retry,
cleanup, or restoration. Edit exceptions, partial mutation, and edit errors remain
truthful unsuccessful results even when mutation may have occurred.

There is no second snapshot.

## 11. Structural materialization verification

The runner consumes existing contracted `gh_snapshot` and `gh_edit` results
directly. It does not duplicate their normalization, partial-success interpretation,
or error taxonomy.

The four identity layers are:

| Identity | Existing owner | Slice 1 use |
|---|---|---|
| semantic node ID, such as `series_a` | Prospective graph | Pre-lowering reference |
| `T1` | Existing `gh_edit` batch protocol | Within-batch request reference |
| `C1` | Existing returned snapshot registry | Returned-canvas reference |
| instance GUID | Grasshopper | Physical component identity |

The only new correlation is ephemeral:

```text
semantic node ID
-> compiler-assigned existing T ID
-> gh_edit-owned temp_id_map / instance_guids
```

The runner never reconstructs or allocates a `C*` ID. It uses each returned
`temp_id_map[T]` value to locate the mapped component and translate the requested
flows into the returned snapshot's existing shorthand.

Successful structural verification requires:

```text
expected T keys == temp_id_map keys == instance_guids keys
all returned C IDs are unique
all returned instance GUIDs are unique
each T identifies the same returned component through both mappings
```

Each mapped component must have the existing snapshot primitive identity expected by
the code-owned tuple: fixed component GUID for regular components and the existing
slider special type for `number_slider`.

Let `new_C` be the exact set of returned `C*` values in `temp_id_map`. The wiring
sets are:

```text
requested_mapped_wires = every requested T-flow translated through temp_id_map

actual_new_incident_wires = every returned wire where
                            source C is in new_C
                            or target C is in new_C

actual_new_incident_wires == requested_mapped_wires
```

Only returned wires whose two endpoints are both pre-existing are ignored. Missing
requested wires, extra wires between new components, and unexpected wires between a
new and pre-existing component all fail verification.

Verification also requires:

- the existing edit contract reports success rather than failure or partial success;
- the returned edit-error collection is empty;
- created and connected summary counts equal the requested node and edge counts;
- every expected mapped component appears in the returned snapshot; and
- every expected mapping is exact, nonempty, and internally consistent.

The result boundary is deterministic:

```text
gh_edit failure, partial success, or edit errors
-> edit

contracted edit success but reconstructed requested structure disagrees
-> verification

exact structural materialization
-> terminal
```

Verification does not inspect component output data, solve values, geometry, visual
appearance, or intent fidelity.

## 12. Bounded ephemeral execution result

The runner returns one ordinary ephemeral transaction aggregate. It may retain only
fields whose owning stage was reached:

- exact intent;
- Planner adapter record;
- admitted canonical graph;
- epoch-free edit plan and correlations;
- snapshot request and contracted response;
- fixed execution scaffold;
- existing native PlanGraph step and supply records;
- existing `gh_edit` response and returned snapshot when available;
- verified semantic-to-native materialization correlation when proven;
- final execution graph when reached;
- terminal stage; and
- native or bounded local reason.

The only ordinary terminal stages are:

```text
planner
graph_admission
snapshot
edit
verification
terminal
```

The aggregate validates immediate field presence and stage relationships only. It is
not self-authenticating evidence and does not replay provider, compiler, graph,
snapshot, or execution lineage in `__post_init__`. Existing native records retain
their existing ownership.

Expected operational and admission stops return the aggregate. Impossible internal
contracts raise. There is no metric, score, scientific classification, ready proof,
archive, checksum, fingerprint, attempt identity, or durable evidence object.

## 13. Witnesses and compositionality guards

The witnesses exist only in tests and later separately authorized qualification
inputs. Their names, intent text, node counts, and expected graph shapes do not enter
production code or the Planner prompt.

### 13.1 Witness 1: parametric point row

The expected semantic family is:

```text
three number sliders
-> series
-> construct_point
-> polyline
```

The sliders control start, step, and count. The witness exercises a known
Grasshopper-native data-matching chain. It does not prove compiler-level scalar/list
inference.

### 13.2 Witness 2: rectangular square grid

The expected semantic family is:

```text
cell-size slider ----\
x-extent slider ------> square_grid
y-extent slider -----/
```

Extent initial values are finite and integral. The sliders remain ordinary number
sliders.

### 13.3 Non-witness recombinations

At least these two legal graphs must compile:

```text
number_slider -> construct_point.x
number_slider -> square_grid.cell_size
```

They prove that production composes arbitrary admitted nodes and edges over the
vocabulary rather than recognizing two templates.

Any production branch containing witness intent text or recognizing a witness graph
shape is prohibited. A primitive name outside the private tuple data is a review
warning unless it participates only in closed schema projection or diagnostics.

## 14. Deterministic test strategy

Tests use fake Planner and tool transports only. Fake GH responses are causally
derived from the actual snapshot and edit requests; they are not canned success
objects.

The focused test surface must prove:

### Planner boundary

- exactly one Planner transport call;
- transport failure and malformed response stop with zero GH calls;
- the prompt contains the semantic tuple projection;
- the prompt excludes GUIDs, pin indices, layout, `T*` IDs, witness intents, and
  witness topology;
- prompt vocabulary and loader vocabulary derive from the same tuple; and
- no retry, fallback, repair, or second call occurs.

### Loading and admission

- the one-time static snapshot fixture independently projects every regular-component
  GUID and direction/index/type/access/physical-optional fact, plus the slider
  identity and range/value shape;
- the separate code-owned `connection_required` policy requires only
  `polyline.vertices` and is not represented as snapshot-derived evidence;
- the slider `value -> O0 / Number / item` convention is tested as code-owned rather
  than represented as snapshot-derived evidence;
- actual JSON duplicate-key and non-finite refusal;
- exact node, edge, identifier, response, label, and numeric bounds;
- unknown field, primitive, parameter, or pin refusal;
- type-exact slider parameters and `minimum <= initial <= maximum`;
- direct integer-input admission requires a finite integral `number_slider` initial
  value, while every non-slider Number source refuses at an Integer input;
- every required input, including `polyline.vertices`, must be connected;
- duplicate edge, multiplicity, incompatible element type, self-edge, and cycle
  refusal; and
- every invalid graph causes zero GH calls.

### Canonical compiler

- reordered node, edge, and parameter declarations canonicalize identically;
- topological depths, depth-based layout, node-ID tie-breaking, and `T*` assignment
  are deterministic;
- lowered `create` entries use fixed GUIDs or the existing slider creator;
- semantic pin names lower to fixed GH indices;
- lowered flows use existing `T*.O*>T*.I*` syntax;
- the compiler emits no epoch or `C*` references;
- an impossible code-owned lowering-kind contradiction raises rather than becoming
  graph admission;
- both witnesses produce materially different plans; and
- both non-witness recombinations compile.

### Execution and correlation

- snapshot and edit use the same executor and frozen Rhino context;
- snapshot failure produces one snapshot call and zero edits;
- valid execution produces one snapshot and one edit;
- malformed epoch, stale epoch, edit failure, partial success, and edit errors stop at
  their specified stages without retry;
- missing, duplicate, inconsistent, non-bijective, or extra mapping identities fail;
- component identity mismatch fails;
- missing requested wires, unexpected new-to-new wires, and unexpected
  new-to-existing wires fail;
- wires whose two endpoints are both pre-existing are ignored;
- exact materialization reaches `done` through existing PlanGraph records; and
- no second snapshot, edit, cleanup, Worker, or other tool call occurs.

Tests should be compact and table-driven over raw JSON or causal response mutations.
They must not recreate the historical source-provenance, carrier-authenticity,
archive, or exhaustive splice machinery.

## 15. Live witness runs and trace handling

Implementation, planning, and review make no provider, Rhino, Grasshopper, or Worker
contact.

After merge, each witness may receive one separately authorized run on a
manually prepared disposable Grasshopper canvas. Provider/model construction remains
outside the semantic graph modules. Each run permits:

```text
one Planner call
one gh_snapshot call
one gh_edit call
zero Worker calls
zero retries
```

The live command retains the bounded ephemeral result. If an already
reusable ordinary recorder fits without modification, it may record the transaction.
Slice 1 does not build a recorder, trace API, dataset manager, archive, publication
lifecycle, or training-record system.

## 16. Physical implementation boundary

Production stays physically lean:

```text
mcp_server/src/rook/agent/semantic_graph.py
  frozen graph types
  strict loader and Planner schema projection
  private five-entry primitive tuple

mcp_server/src/rook/agent/semantic_graph_compiler.py
  graph admission
  canonicalization and cycle/depth analysis
  epoch-free lowering and correlation

mcp_server/src/rook/agent/semantic_graph_runner.py
  one-call Planner adapter
  fixed create_edit / verify_edit / done PlanGraph
  one snapshot and one edit composition
  structural verification
  bounded ephemeral result
```

The conceptual responsibilities do not justify further modules, registries, class
families, visitors, or frameworks. Existing canonical JSON, `PlanGraph`, tool
dispatch, `gh_snapshot`, `gh_edit`, normalization, partial-success handling, and
native records are reused.

No production or migration changes are made to:

- v2 recipes or `recipe_to_edit()`;
- the knowledge graph;
- DSPy, Chirp, ChatRunner, or RookChat;
- Worker contexts or actions;
- Rhino operations;
- native or managed Grasshopper handlers;
- `gh_snapshot` or `gh_edit` schemas;
- product UI, MCP registration, or CLI surfaces; or
- LM9 evidence and provenance systems.

If implementation requires a registry, generalized type system, schema family,
component introspection system, new receipt taxonomy, new trace subsystem, or
witness-specific production path, work stops and the representation is reconsidered.

## 17. Explicit non-claims

Slice 1 does not claim:

- semantic fidelity to either intent;
- geometric or output-value correctness;
- general list/tree inference;
- persistent integral slider behavior;
- arbitrary Grasshopper primitives or plugins;
- reusable or nested subgraphs;
- mixed Rhino and Grasshopper programs;
- Worker-authored leaves;
- retry, repair, or replanning;
- knowledge-grounded planning;
- DSPy eligibility or optimization;
- historical recipe import compatibility;
- repeatability across live environments;
- product-surface readiness; or
- durable scientific evidence.

It proves one deliberately smaller fact: a Planner may author variable topology over
five reviewed deterministic primitives, and existing Grasshopper batch identity and
receipt machinery can truthfully establish exact structural materialization.
