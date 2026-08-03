# Compositional harness representation fit audit

- **Date:** 2026-08-02
- **Audit baseline:** `93fe02e58836934edf836c13a3a92439328616b8`
- **Branch:** `codex/compositional-harness-representation-fit-audit`
- **Decision:** use a **small replacement** for the prospective semantic design graph
- **Preserve:** the v2 recipe graph as a retrospective Grasshopper extraction/replay artifact
- **First implementation boundary:** deterministic, Grasshopper-only, no Worker

## Executive recommendation

Do **not** make the existing v2 recipe graph the Planner-authored semantic design graph, either unchanged or by extending its persisted meaning in place. Introduce a small prospective representation in Slice 1 and leave the learning recipe system compatible and independently useful.

This is not a recommendation for a universal IR. It is the opposite: keep one small admitted semantic program above the already-proven execution machinery, initially covering only a closed set of deterministic Grasshopper primitives. The representation must carry stable semantic node identity, admitted primitive identity, owned parameters, typed ports, deterministic edges, acceptance intent, and a correlation path into lowering. It need not support Rhino operations, reusable subgraphs, Worker leaves, replanning, or product exposure in Slice 1.

The conclusion follows from the production boundary, not from a preference for newness:

1. The native `/gh/snapshot` producer already reports stable component type GUIDs and detailed input/output port metadata, including index, name, type, access, and optionality.
2. `extract_recipe_v2()` deliberately removes those fields. The persisted v2 component keeps an `R*` ID, class/display names, position, and a few simple-control values. The active corpus contains no retained component GUID field.
3. `recipe_to_edit()` is a permissive replay adapter. It does not validate a closed graph, ignores `subgraphs`, does not preflight component availability or port compatibility, and can submit a batch that partially mutates the canvas before later errors are reported.
4. The v2 object called a `component` means a Grasshopper canvas object. Broadening it to mean a Rhino operation, inspection, comparison, mutation, or unresolved Worker leaf would replace its semantics while pretending to preserve them.
5. The separate execution side is much stronger. `PlanGraph`, `RookWorkflowContract`, the current-step runners, the Worker action boundary, and native receipt projections provide reusable execution mechanisms without needing the recipe graph to become an execution graph.

The clean connective tissue is therefore:

```text
Planner-authored small semantic design graph
-> strict semantic admission and canonical normalization
-> deterministic Grasshopper lowering
   -> complete /gh/edit request
   -> semantic-node-to-temp-ID correlation
-> fixed compiler-owned execution PlanGraph
-> existing typed ToolDispatcher/native bridge
-> /gh/edit result and instance GUID map
-> deterministic verification and native records
```

The semantic dataflow remains “what to build.” The execution PlanGraph remains “how this admitted batch progresses.” A variable semantic topology does not require a variable execution topology: Slice 1 can lower a complete semantic graph into one admitted `gh_edit` batch and execute it through a small fixed producer/verify/terminal PlanGraph.

## Baseline and audit method

The audit worktree was created directly from the required merge commit. At worktree creation, fetched `origin/main` was also exactly `93fe02e58836934edf836c13a3a92439328616b8`; there was no drift. The primary checkout was dirty with unrelated work and was not modified.

The audit used source inspection, read-only JSON corpus scans, and offline focused tests. It made no provider, Worker, Rhino, Grasshopper, readiness, or mutation contact. It changed no production or test file.

The graph roles in this report are deliberately separate:

- **Semantic design graph:** user/Planner-owned topology and admitted meaning.
- **Execution PlanGraph:** compiler-owned progress, evidence, and control state.

## Current artifact inventory

| Artifact | Current owner and purpose | Relevant fit finding |
|---|---|---|
| `DraftRecipe` / v2 `graph` | Learning layer; retrospective canvas extraction awaiting review | Plain dataclass/dict structure, not a closed Planner contract |
| `PatternNote.graph` | Persisted learning recipe | Stores the v2 dict without semantic validation or canonical equality |
| `/gh/snapshot` | Managed Grasshopper bridge | Rich source includes component GUID and typed ports that v2 extraction discards |
| `recipe_to_edit()` | Learning replay adapter | Directly maps v2 components/flows into `gh_edit` `create`/`connect` arrays |
| `gh_replay_recipe` | Python server operation | Loads a stored v2 recipe, obtains a fresh epoch, then calls `/gh/edit` |
| `/gh/edit` | Managed Grasshopper mutation batch | GH-only, index-wired, can report partial mutation; returns temp-ID/GUID maps |
| `PlanGraph` | Learning execution-state substrate | Strong reducer and role-aware evidence flow; not a semantic dataflow graph |
| `RookWorkflowContract` | Agent-layer compiler input | Closed, canonical, deterministic, but selects fixed hand-authored execution templates |
| `CompiledWorkflowScaffold` | Compiler-owned execution artifact | Reusable for fixed execution control; current templates are C# create/repair variants |
| Initial-body Worker handoff | Agent-layer one-leaf composition | Proven code-only Worker authority outside graph execution |
| Script receipts | Python tool boundary | Strong operation/mutation/verification facts and component GUID; no semantic node ID |
| Current-step records | Agent execution layer | Correlate execution node, tool, verifier source, and outcome; non-authoritative audit projection |

## The v2 recipe representation as implemented

### Authoring source and retained fields

`GrasshopperHandler.TakeSnapshot()` emits regular components with:

- short canvas ID;
- runtime class name and display identity;
- stable `ComponentGuid` as `componentGuid`;
- category/subcategory/description;
- position;
- inputs and outputs with `idx`, name, nickname, type, access, optionality, and connection counts;
- optional output previews and runtime diagnostics.

`extract_recipe_v2()` does not retain that semantic richness. `_transform_component_v2()` keeps:

- a sequential `R*` ID assigned from snapshot list order;
- a `type` string;
- optional nickname and display name;
- source-canvas position;
- slider min/max/value, panel content, or toggle value.

It drops `componentGuid`, the input/output declarations, port types, access/optionality, categories, diagnostics, plugin state, and ordinary persistent parameter values. `recipe_to_edit()` later looks for a field named `guid`, but the v2 extractor neither copies `componentGuid` nor creates `guid`. The stored active corpus confirms the mismatch: zero v2 component entries have a `guid` field.

The result is suitable as a compact visual replay hint for many native components. It is not sufficient as an admitted semantic operation declaration.

### Components, flows, and subgraphs

The v2 outer graph is:

```text
components: list of component dictionaries
flows:      list of "R1.O0>R2.I1" strings
subgraphs:  list, currently always initialized empty
```

The flow string carries endpoint node IDs and positional pin indices. That is enough to reproduce topology when the recreated components expose the same port ordering and arity. It does not declare pin type, access, optionality, or semantic name. There is no independent edge ID.

`subgraphs` is documented in `PatternNote` as an optional annotation, but `extract_recipe_v2()` always writes `[]`, and `recipe_to_edit()` never reads it. It currently provides neither nesting nor reusable lowering semantics.

Source snapshot groups are also not projected into v2 `subgraphs` or replay groups. Annotations are optional nearby-text associations only and are ignored by lowering.

### Parameters and variable components

Parameter support is narrow and representation-specific:

- slider: min, max, value, nickname;
- panel: content;
- toggle: value;
- ordinary component: no persistent component parameters;
- value list and colour swatch: extracted as types but not lowered as supported special controls.

The corpus contains 219 `colour` entries and five `valuelist` entries. `recipe_to_edit()` treats them as ordinary components, but their extracted entries lack a regular component name; replay therefore falls back to names such as `colour` or `valuelist` rather than restoring their value configuration.

Variable-parameter component topology is present only indirectly in flow indices. The corpus contains 447 `Component_MergeVariable` and 420 `Component_ListItemVariable` entries. Valid-looking flows target Merge inputs through `I6` and List Item inputs through `I2`, yet no retained field declares or reconstructs variable arity. `/gh/edit` resolves an actual target parameter by index at mutation time and reports an error if it does not exist.

### Layout

Layout is retrospective, not compiler-owned. v2 stores the source canvas position and `recipe_to_edit()` preserves it plus an operator offset. If position is absent, the managed creator defaults each component to the same `(100, 100)` location. There is no semantic layout policy or deterministic layout derivation from topology.

## Stored-recipe findings

A read-only scan of `knowledge/gh/patterns/*.json` found:

- 519 stored pattern files;
- 274 entries marked `pattern_type=recipe`;
- 268 v2 recipes with a graph;
- 18,821 v2 component entries;
- 20,652 v2 flow strings;
- 54 graphs with annotations;
- zero non-empty `subgraphs` arrays;
- zero v2 component `guid` fields;
- zero duplicate component-ID graphs;
- zero duplicate-flow graphs;
- nine non-v2 flow strings across six graphs.

The nine malformed retained flows contain a stale `C*` source joined to an `R*` target. They occur in:

- `625bd9e0.json` (two);
- `7bb677d9.json` (one);
- `8a71e405.json` (two);
- `ab7fb612.json` (two);
- `e1e6f130.json` (one);
- `fa2528c3.json` (one).

`recipe_to_edit()` only rewrites `R<number>` tokens, so those `C*` sources remain references to whatever current-canvas short ID happens to match, or fail after create operations have already been attempted. The stored corpus is therefore evidence of useful captured topology, not an admission-quality corpus.

The adjacent `knowledge/gh/notes/recipe_*.json` mirror contains 121 recipe notes and 10,513 legacy wiring rows. None contains the v2 graph at its top level. Those notes add retrieval prose and legacy semantic pin names but do not provide a second validated v2 representation.

The corpus also demonstrates breadth and loss at the same time:

- common deterministic components include Series, Range, Construct Point, vector operators, sliders, and many standard geometry components;
- it includes old Ladybug component specimens such as `LB SunPath`, `LB Analysis Period`, and `Ladybug_Shadow Study`;
- it contains many `ZuiPythonComponent` and legacy C#/VB script entries, but v2 retains neither script bodies nor declared script pin contracts;
- no Honeybee-named specimen was found.

## Actual lowering and validation boundary

### `recipe_to_edit()`

The lowerer performs only mechanical projection:

1. Iterate `graph.get("components", [])` in authored order.
2. Rewrite an `R<number>` component ID to the same numbered `T<number>` temp ID.
3. Lower slider, panel, and toggle specially.
4. Lower every other value by `guid` if present, otherwise by display `name` or `type`.
5. Preserve position plus optional offset.
6. Rewrite `R<number>` tokens in each authored flow and return `create` and `connect` arrays.

It does not:

- require exact graph keys or field types;
- require unique IDs or closed endpoints;
- validate flow grammar;
- verify that every flow endpoint belongs to the graph;
- validate pin indices or pin types;
- reject unknown component types;
- validate plugin availability;
- restore variable arity or ordinary persistent state;
- canonicalize ordering;
- lower `subgraphs` or annotations;
- produce a semantic-node correlation artifact.

### `/gh/edit`

The public tool contract requires only `epoch` at the request root and `temp_id` for each create entry. It accepts optional GUID/name/type, positions and simple values, plus positional flow strings. The JSON schema is descriptive and does not close all object fields.

The managed handler checks the current epoch, then applies phases in order: create, disconnect, delete, set values, connect, and groups. Component creation resolves a special control, stable GUID, or installed component name. Name resolution explicitly rejects ambiguity. Flow endpoints are resolved and parameters looked up by numeric index.

This is useful operational validation, but it is too late to be semantic admission. The handler accumulates per-operation errors while continuing the batch. `apply_gh_edit_contract()` truthfully reports a partial success when mutation evidence exists alongside errors. Unsupported primitives or bad ports can therefore be discovered after earlier components were created.

`gh_replay_recipe` adds the required epoch by taking a current snapshot immediately before dispatch. It does not add a recipe-validation phase.

### Canonicalization and equality

The recipe path has no canonical semantic form:

- `DraftRecipe` and `PatternNote` accept mutable Python dictionaries/lists;
- `PatternNote.from_dict()` uses permissive defaults and ignores unknown outer structure indirectly;
- persistence uses indented JSON without sorted-key canonicalization;
- there is no dedicated strict v2 graph loader;
- Python container equality is the only equality behavior;
- node and edge order remain authored/extracted order.

By contrast, `RookWorkflowContract` already demonstrates the right boundary discipline for execution contracts: closed payload fields, JSON-safe normalization, finite-number checks, duplicate node/rule rejection, immutable snapshots, sorted-key compact serialization for a fingerprint, exact expected refs, and compiler validation against a selected template. The semantic representation should reuse that normalization discipline, not import the workflow contract's fixed topology or create an identity/archive system.

## Execution PlanGraph findings

`PlanGraph` is a good execution substrate and a poor semantic-design substitute, exactly as the roadmap states.

Strengths:

- explicit node lifecycle states;
- typed control edges (`requires`, success, repair, failure, escalation);
- copy-on-write state reduction;
- captured `NodeEvidence`, graph facts, and bounded retry counters;
- unique-ready selection with explicit none-ready and ambiguous-ready halts;
- proposal revalidation before execution;
- separate producer, verifier, and parameter-bind step kinds;
- native current-step and supply records;
- injected typed tool execution with admissibility checks before dispatch.

Limits relevant to Slice 1:

- it carries control dependencies, not design dataflow ports;
- multiple independent ready roots cause an intentional ambiguous halt;
- node `execution_ref` and execution parameters are execution artifacts, not semantic primitive declarations;
- current `RookWorkflowContract` does not author arbitrary nodes or edges; it selects one of four fixed C# templates and stages parameters/rules into that template;
- the current verifier family is script-receipt oriented.

These limits do not require changing PlanGraph into the semantic graph. A compiler can serialize or batch an admitted semantic topology into a fixed execution path. For the first Grasshopper slice, a single `gh_edit` producer followed by deterministic batch verification and a terminal marker is sufficient in principle.

## Worker-leaf findings

The initial-body path proves the desired authority split for a future unresolved leaf:

```text
validated Planner draft
-> compiler-owned incomplete create scaffold
-> one Worker context with one allowed action
-> Worker supplies only code
-> pure applicator inserts only that code
-> create and deterministic receipt verification
```

The compiler owns pins, name, position, tool reference, topology, and verifier. `draft_create_body` accepts only `code`. `apply_worker_create_body_to_scaffold()` reconstitutes the exact compiled workflow snapshot before performing a copy-on-write insertion. The existing fixed path is intentionally limited to no inputs and one `A:double` output.

This is a reusable **pattern**, not a representation fit. The v2 recipe graph has no way to declare an unresolved field, its typed interface, its acceptance condition, or a sole Worker-authority boundary. A blank or generic script component in a stored recipe is not equivalent to an admitted unresolved Worker leaf.

Slice 1 should not add this feature. Slice 2 can place one bounded unresolved payload in the new semantic graph and reuse the existing context/action/applicator discipline without giving the Worker topology authority.

## Receipt correlation findings

There are two useful receipt paths:

1. `build_script_receipt()` records operation, language, mutation status/method, component GUID, verification status/method/counts, artifact status, pins, source-shape facts, and a repair anchor. PlanGraph evidence attaches that receipt to the producer execution node, and verifier records name their `verifier_source_node_id`.
2. `/gh/edit` returns `edit_summary.temp_id_map` and `edit_summary.instance_guids`, mapping submitted `T*` IDs to current short IDs and instance GUIDs, plus mutation counts and errors.

Neither receipt names a semantic design node. Current-step records name the execution PlanGraph node, not a prospective semantic node. `recipe_to_edit()` also returns no retained lowering map beyond the coincidental `R<number>` to `T<number>` rewrite.

Slice 1 therefore needs one ordinary ephemeral compiler correlation:

```text
semantic node ID -> lowered temp ID -> returned instance GUID / operation result
```

That map should be derived by the compiler and consumed by result projection. It does not require hashes, manifests, archives, proof carriers, or a new system of record.

## Requirement/evidence matrix

| Requirement | v2 fit | Repository evidence | Consequence |
|---|---|---|---|
| Typed operation/component identity | **No** | Snapshot has `componentGuid`; extractor drops it; corpus has zero `guid` fields; replay usually uses display name | Cannot pre-admit exact component identity or plugin capability |
| Typed input and output pins | **No** | Snapshot exposes typed ports; extractor strips them; flows keep indices only | Type/access/optionality errors surface only at runtime |
| Parameter ownership and validation | **No** | Only slider/panel/toggle values survive; no ownership role; ordinary persistent state is dropped | Planner/compiler/Worker authority cannot be separated unchanged |
| Variable nodes and topology | **Partial** | Flow indices express topology, including high indices; variable arity is not retained/recreated | Topology can describe ports the recreated component may not have |
| Deterministic flow/edge identity | **Partial** | Explicit strings preserve order and indices; no edge IDs/canonical sort/closed validation; nine stale flows exist | Not safe for canonical admission or equality unchanged |
| Nested or reusable subgraphs | **No** | All 268 graph specimens have empty `subgraphs`; lowerer ignores the field | Field is documentary scaffolding, not a feature |
| Compiler-owned layout/defaults | **No** | Source positions are retained and offset; absent positions collapse to handler defaults | Layout is captured UI state, not deterministic compilation |
| Deterministic lowering to typed tools | **Partial** | One deterministic GH-only projection to `gh_edit`; component/pin validity remains runtime-resolved | Useful implementation mechanism after a stricter compiler, not sufficient admission |
| Unsupported primitive refusal | **No** | Unknown/ambiguous names and bad pins reach `/gh/edit`; earlier mutations can already exist | Violates pre-mutation refusal required by Slice 1 |
| One unresolved bounded Worker leaf | **No** | Separate initial-body handoff proves code-only action; v2 has no unresolved-leaf semantics | Requires the future semantic representation, deferred to Slice 2 |
| Receipt correlation to semantic node | **Partial** | `/gh/edit` maps `T*` to GUID; current-step records map execution nodes; no semantic-to-lowered map | Add a compiler-owned ephemeral correlation in Slice 1 |
| Mixed Rhino and Grasshopper operations | **No** | v2 lowers only to `gh_edit`; repository has separate typed Rhino tools | Reusing `component` for non-GH operations would redefine the format |
| Canonical serialization and equality | **No** | Mutable permissive dicts, no strict loader/canonical bytes; workflow compiler has a stronger precedent | New prospective contract needs closed normalization |
| Current test coverage | **Partial** | Round-trip and execution seams are well tested separately | Cross-boundary semantic admission is not tested because it does not exist |
| Important corpus/runtime gaps | **No** | Empty subgraphs, stale flows, lost GUIDs/ports/state, legacy note mirror, runtime partial mutation | Stored success recipes cannot be treated as admitted Planner programs |

## Four-request conceptual stress test

These are capability probes, not selected Slice 1 witnesses and not proposed schemas.

### 1. Phyllotaxis points with vector forces and three sliders

**Existing composable evidence:** the corpus contains sliders, Series/Range, arithmetic operators, Construct Point, Unit Vector, Vector XYZ, vector amplitude, rotation, and display components. The v2 flow notation can draw the required Grasshopper dataflow topology.

**Representation result:** topology is expressible at the positional-port level. Admission is not. The graph cannot prove the exact component type or port types, distinguish compiler-owned defaults from user parameters, or represent a bounded C# body leaf if a deterministic primitive is unavailable. It would be plausible only as a known-recipe replay.

### 2. Ladybug/Honeybee sun-angle and solar-gain analysis

**Existing composable evidence:** `ab7fb612.json` contains old Ladybug `LB Analysis Period`, `LB SunPath`, `LB Import Location`, and `Ladybug_Shadow Study` components. Other stored components include incident-radiation and sky/EPW-related Ladybug names.

**Missing evidence:** no Honeybee-named specimen was found. The Ladybug entries are recorded as `ZuiPythonComponent` plus display names, without stable GUIDs, plugin/version requirements, typed ports, or retained executable state. `ab7fb612.json` itself has two stale `C*` flow sources.

**Representation result:** the graph can sketch an observed plugin topology, but it cannot admit or safely lower the requested analysis. Plugin availability and component/port identity are missing primitives, not merely missing examples.

### 3. Rhino box array with gradient height

**Existing composable evidence:** production exposes typed Rhino operations including `rhino_create`, `rhino_array_linear`, `rhino_array_rectangular`, `rhino_array_polar`, and `rhino_transform`.

**Representation result:** v2 cannot represent the request. Its nodes are Grasshopper canvas components and its only lowerer emits `/gh/edit`. It has no operation-result binding from created Rhino GUIDs into later array/transform calls and no meaning for a Rhino operation node. This would require redefining `components` and `flows`, not adding one optional field.

### 4. Rhino layer cleanup against a supplied JSON convention

**Existing composable evidence:** production has typed inspection and mutation surfaces including `rhino_layers`, layer dependencies, create, rename, property update, move objects, merge, and batch variants.

**Representation result:** v2 cannot carry the supplied convention as a typed input, represent inspection/comparison/mutation operations, express mutation dependencies, or attach acceptance to layer results. The topology itself is outside the Grasshopper component/port model.

### Stress-test conclusion

The v2 topology concept is genuinely useful for Grasshopper dataflow. The v2 representation is not the broader semantic program. Two requests reveal unsafe GH identity/state gaps; two require operation semantics the graph does not possess. That split is the decisive evidence for a small replacement and a Grasshopper-only first implementation.

## Comparison of the three outcomes

### Outcome 1: reuse the existing v2 recipe graph unchanged

**Supporting evidence**

- Large real corpus with explicit component nodes and flow topology.
- Direct `recipe_to_edit()` lowering already exists.
- Slider, panel, toggle, position, and many standard component replays are covered by focused tests.
- Maximum storage compatibility.

**Concrete limitations**

- No stable component identity in active specimens.
- No typed port declarations or persistent ordinary component state.
- No closed loader, canonical form, or pre-mutation unsupported refusal.
- Inert subgraphs and no Worker leaf.
- GH-only semantics and no semantic receipt correlation.
- Retained malformed flows prove corpus bytes are not admission-ready.

**Production modules affected**

- No existing module needs modification, but Slice 1 would have to trust `recipe_extraction.py`, `pattern_memory.py`, `pattern_store.py`, `recipe_to_edit()`, and `gh_replay_recipe` as the new planning boundary.

**Compatibility consequences**

- Stored replay behavior remains compatible.
- The meaning of “v2 valid” would remain permissive and operationally late.

**What it would authorize in Slice 1**

- Only replay-like tests over carefully selected known Grasshopper graphs.
- It would not truthfully authorize Planner-authored variable topology under typed primitive admission.

**Explicitly deferred**

- Stable identity, typed pins, unsupported refusal, Worker leaf, nested reuse, receipt correlation, Rhino/mixed operations.

**Verdict:** reject. It cannot meet Slice 1's hypothesis.

### Outcome 2: apply a narrow extension to v2

**Supporting evidence**

- The outer node/flow shape is directionally appropriate for Grasshopper.
- `/gh/snapshot` already provides stable GUID and port data that extraction could retain.
- Existing replay and stored graphs could remain readable through version-aware handling.

**Concrete limitations**

- Closing component identity, pins, params, ownership, canonicalization, unsupported refusal, Worker leaves, and receipt correlation is not one narrow addition.
- Mixed Rhino operations would change “component” from a GH object into a general operation and “flow” from a GH wire into multiple dependency/value meanings.
- Existing stored graphs would not satisfy the extended admission contract and would require migration or a compatibility adapter.
- `recipe_to_edit()` and the learning store would acquire product-compiler responsibilities unrelated to retrospective learning.

**Production modules affected**

- `recipe_extraction.py`, `pattern_memory.py`, `pattern_store.py`, server recipe save/replay tools, `recipe_to_edit()`, tool schemas, corpus migration/compatibility, and their tests.

**Compatibility consequences**

- A version bump or dual loader would be unavoidable.
- Old recipes would remain replay artifacts, which is effectively the same semantic split as a replacement but with more coupling.

**What it would authorize in Slice 1**

- A typed Grasshopper-only subset after substantial admission and lowering work.
- It still would not honestly authorize mixed-domain programs.

**Explicitly deferred**

- Mixed Rhino/GH operations, reusable subgraphs, Worker leaves, and replanning unless the “narrow” extension expands further.

**Verdict:** reject. The necessary changes constitute replacement-in-place with avoidable learning-system compatibility risk.

### Outcome 3: introduce a small replacement

**Supporting evidence**

- Prospective semantic programs and retrospective canvas recipes have different owners and invariants.
- The needed semantic contract is small even though v2 cannot supply it.
- Existing execution pieces already cover deterministic control, strict workflow normalization, typed tool dispatch, Worker action confinement, receipt interpretation, and native records.
- Leaving v2 unchanged preserves a large useful knowledge/replay corpus.

**Concrete limitations**

- Slice 1 must add one new strict semantic loader/normalizer and deterministic compiler.
- A fixed `gh_edit` execution template and batch-result verifier do not exist yet.
- Initially admitted primitive breadth will be deliberately small.

**Production modules affected**

- New narrowly scoped semantic representation/admission and lowering modules.
- One fixed execution template/provider rule set for an admitted `gh_edit` batch, plus a batch-result verifier if existing generic tool-result semantics are insufficient.
- A thin composition root using existing ToolDispatcher and current-step execution.
- No required change to recipe extraction, storage, replay, initial-body handoff, or LM9 systems.

**Compatibility consequences**

- No migration: v2 remains v2 and continues to replay under its present semantics.
- Stored recipes may later be imported only through an explicit validated adapter, not silently promoted.
- The new semantic graph has no accidental compatibility promise to malformed historical graphs.

**What it would authorize in Slice 1**

- One Planner-authored, strictly loaded, deterministic Grasshopper semantic graph using a small closed primitive set.
- Variable nodes, edges, and parameters that genuinely change with intent.
- Complete pre-dispatch unsupported refusal.
- Deterministic lowering to one `gh_edit` request, execution through a fixed PlanGraph, and receipt correlation through temp IDs.
- Two witnesses selected during Slice 1 planning, not in this audit.

**Explicitly deferred**

- Worker leaves (Slice 2), receipt-driven replanning (Slice 3), product UI (Slice 4), mixed Rhino/GH execution, reusable subgraphs, arbitrary plugins, and a general registry.

**Verdict:** recommend.

## Recommended Slice 1 boundary

Slice 1 should implement only the following freedom:

> A frontier Planner may vary a small deterministic Grasshopper design topology and parameters inside a closed primitive vocabulary; the compiler either lowers the complete graph before contact or refuses it without mutation.

Required boundary:

1. **Prospective graph, separate from learning recipes.** Add one small strict loader/normalizer. Do not migrate or reinterpret stored v2 recipes.
2. **Grasshopper-only.** Admit only deterministic components whose stable identities, typed port signatures, and supported parameters are code-owned and testable. Mixed Rhino operations remain unsupported.
3. **No Worker.** Every admitted node must lower deterministically. Missing script/code/plugin behavior is an unsupported primitive, not a blank node.
4. **Complete preflight.** Validate node IDs, primitive identities, parameters, port endpoints/types, edge closure, acyclicity where required, and the full lowerability of the batch before calling a tool.
5. **Compiler-owned layout and IDs.** Derive layout/defaults and `T*` temp IDs deterministically from normalized semantic nodes. The Planner owns design topology, not canvas coordinates or execution IDs.
6. **Fixed execution graph.** Lower the complete design graph to a typed `gh_edit` request, then use a compiler-owned producer/verify/terminal PlanGraph. Do not mirror semantic wires as execution control edges.
7. **Ordinary correlation.** Retain an ephemeral semantic-node-to-temp-ID map and combine it with `/gh/edit` instance GUIDs and errors. Do not add archives or identity machinery.
8. **Truthful batch result.** Treat partial `/gh/edit` mutation as an unsuccessful native result with exact known per-temp-ID facts; do not call it atomic success.
9. **Tests before live contact.** Prove structurally different normalized graphs, canonical equality, unsupported refusal before dispatch, lowering determinism, temp-ID correlation, and unchanged execution records with fake tool contact only.

The implementation plan may choose the two Slice 1 witnesses after this decision is independently reviewed. This report deliberately does not select them.

## Test coverage and important gaps

An offline focused selection covering recipe extraction, `gh_edit` result handling, script receipts, PlanGraph reduction/templates/runners, workflow compilation, Worker body application, and the initial-body handoff passed **291 tests**.

Adding `test_recipe_integration.py` produced **293 passed and 6 setup errors**. All six errors are the same baseline drift: the test fixture tries to patch removed module globals `rook.learning.pattern_store.KNOWLEDGE_DIR` and `PATTERNS_DIR`. No audit code caused the failure. This means the old extract/save/search integration file is not currently a reliable storage guard.

Adding `test_gh_edit_postmortem.py` to the clean selection produced **299 passed and 1 failure**. `test_gh_replay_recipe_strict_partial_failure_is_recorded_as_partial` expects `data.partial_success`, but the current tool response omits that field. This is a second baseline gap in the retrospective replay surface, not an audit change. The clean **291-test** selection excludes both files with known baseline failures.

Existing coverage proves:

- C-to-R-to-T topology/count preservation for a small sphere fixture;
- slider value preservation and positional offset;
- `gh_edit` partial-mutation result classification;
- receipt status derivation and role-aware PlanGraph projection;
- PlanGraph state reduction, unique-ready selection, revalidation, execution, and recording;
- strict workflow-contract normalization and fixed template compilation;
- exact code-only initial Worker action and one-pass create/verify behavior.

Important uncovered boundaries are:

- strict loading of a Planner-authored semantic graph;
- corpus-wide v2 validation (the stale flows were found only by this audit scan);
- stable component GUID preservation from snapshot through replay;
- typed-port preservation and preflight compatibility;
- variable-component arity reconstruction;
- value-list/colour and ordinary persistent-state replay;
- non-empty subgraph semantics;
- canonical graph serialization and type-exact equality;
- complete unsupported-primitive refusal before `/gh/edit`;
- semantic-node-to-native-receipt correlation;
- mixed Rhino/GH operation semantics.

## Explicit non-claims

This audit does not claim that:

- stored v2 recipes are useless or should be migrated, deleted, or repaired;
- every v2 recipe fails replay;
- a small replacement is a universal cross-domain IR;
- mixed Rhino and Grasshopper operations belong in Slice 1;
- the future semantic graph's concrete JSON schema has been designed;
- nested/reusable subgraphs are required in the first implementation;
- any particular two Slice 1 witnesses have been selected;
- the existing PlanGraph, workflow contract, Worker harness, or receipt system should be generalized now;
- live Grasshopper component availability, Ladybug/Honeybee compatibility, or any runtime result was verified;
- the six stale recipe-integration tests should be repaired within this slice.

## Code evidence index

### Candidate representation and storage

- `mcp_server/src/rook/learning/recipe_extraction.py`
  - `DraftRecipe`
  - `_transform_component_v2()`
  - `_transform_flow_v2()`
  - `extract_recipe_v2()`
  - `merge_v2_into_pattern()`
  - `recipe_to_edit()`
- `mcp_server/src/rook/learning/pattern_memory.py`
  - `PatternNote.graph`
  - `PatternNote.to_dict()`
  - `PatternNote.from_dict()`
- `mcp_server/src/rook/learning/pattern_store.py`
  - `PatternStore._load_all()`
  - `PatternStore._save_pattern()`
- `knowledge/gh/patterns/*.json`
- `knowledge/gh/notes/recipe_*.json`

### Snapshot, lowering, and native mutation

- `src/Rook/Handlers/GrasshopperHandler.cs`
  - `TakeSnapshot()`
  - `BuildComponentEntry()`
  - `ExtractParams()`
  - `ApplyEdit()`
  - `EditCreateComponent()`
  - `ParseFlowString()`
- `mcp_server/src/rook/server.py`
  - `gh_edit` tool schema
  - `gh_replay_recipe` dispatch branch
  - `_execute_gh_create_script()`
- `mcp_server/src/rook/gh_edit_contract.py`
  - `apply_gh_edit_contract()`
  - `has_mutation_evidence()`
- `mcp_server/src/rook/agent/tool_dispatcher.py`
  - `ToolDispatcher`
  - `_normalize_gh_create_script_kwargs()`
  - local Grasshopper create-script aliases

### Execution graph and compiler

- `mcp_server/src/rook/learning/plan_graph.py`
  - `PlanGraph`
  - `PlanGraphNode`
  - `PlanGraphEdge`
  - `apply_outcome()`
  - `runnable_nodes()`
- `mcp_server/src/rook/learning/plan_graph_templates.py`
  - `DEFAULT_REGISTRY`
  - `_build_gh_csharp_create_verify()`
  - `select_template()`
- `mcp_server/src/rook/learning/plan_graph_selector.py`
  - `propose_next_node()`
- `mcp_server/src/rook/learning/plan_graph_runner.py`
  - `apply_producer_result()`
  - `apply_verifier_step()`
- `mcp_server/src/rook/agent/plan_graph_workflow_contract.py`
  - `RookWorkflowContract`
  - `load_workflow_contract_payload()`
  - `compile_workflow_contract()`
  - `_normalize_workflow_contract()`
- `mcp_server/src/rook/agent/plan_graph_current_step_stream.py`
  - `run_current_step_stream()`
- `mcp_server/src/rook/agent/plan_graph_current_step_runner.py`
  - `CurrentStepRecord`
  - `project_current_step_record()`

### Worker leaf and receipts

- `mcp_server/src/rook/agent/minimal_csharp_initial_body_handoff.py`
  - `_build_initial_body_contract()`
  - `_build_worker_context()`
  - `run_minimal_csharp_initial_body_handoff()`
- `mcp_server/src/rook/agent/plan_graph_worker_create_body_apply.py`
  - `apply_worker_create_body_to_scaffold()`
  - `_matches_compiled_contract_snapshot()`
- `mcp_server/src/rook/agent/local_worker_turn_context.py`
  - `WorkerAllowedAction`
  - `build_local_worker_turn_context()`
- `mcp_server/src/rook/gh_script_receipts.py`
  - `build_script_receipt()`
  - `derive_verification()`
- `mcp_server/src/rook/learning/plan_graph_outcomes.py`
  - `node_evidence_from_tool_result()`
- `mcp_server/src/rook/learning/plan_graph_projection.py`
  - `project_receipt_outcome()`

### Focused tests inspected/executed

- `mcp_server/tests/test_recipe_extraction.py`
- `mcp_server/tests/test_recipe_integration.py`
- `mcp_server/tests/test_gh_edit_contract.py`
- `mcp_server/tests/test_gh_edit_postmortem.py`
- `mcp_server/tests/test_gh_script_receipts.py`
- `mcp_server/tests/test_plan_graph.py`
- `mcp_server/tests/test_plan_graph_templates.py`
- `mcp_server/tests/test_plan_graph_workflow_contract.py`
- `mcp_server/tests/test_plan_graph_worker_create_body_apply.py`
- `mcp_server/tests/test_minimal_csharp_initial_body_handoff.py`
- `mcp_server/tests/test_plan_graph_outcomes.py`
- `mcp_server/tests/test_plan_graph_runner.py`

## Stop condition

Slice 0 is complete when this decision is independently reviewed. No specification, implementation plan, schema, primitive registry, fixture, provider call, Worker call, or native contact is authorized by this report.
