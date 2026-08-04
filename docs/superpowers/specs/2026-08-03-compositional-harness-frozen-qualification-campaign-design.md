# Compositional Harness Frozen Qualification Campaign Design

**Date:** 2026-08-03

**Status:** Approved design; campaign support not implemented

**Baseline:** `8baf325a459ec9bb53cae24b1af0fab452b3001e`

**Branch:** `codex/compositional-harness-frozen-qualification-campaign-design`

## Purpose

This campaign qualifies the already-merged compositional agent harness across
controlled graph pressure, Planner models, Worker models, and repetition without
changing the harness between scored runs.

The two existing transaction shapes remain:

```text
deterministic transaction:
exact intent
-> one Planner response
-> strict semantic-graph loading
-> deterministic compilation
-> one snapshot
-> one gh_edit batch
-> native structural verification
-> terminal result

single-Worker-leaf transaction:
exact intent
-> one Planner response
-> strict semantic-graph loading
-> deterministic/Worker partition
-> one Worker initial-body turn
-> one C# create and clean compile receipt
-> one snapshot
-> one deterministic gh_edit batch
-> one receipt-derived gh_connect
-> completed result
```

The campaign measures whether different models can inhabit those existing
contracts under increasing structural pressure. It does not add another degree
of product freedom.

## Frozen-harness rule

Before the first scored model call, freeze:

- the exact merge SHA and locked Python environment;
- production code;
- Planner and Worker prompts;
- structured-response schemas and their provider materialization;
- strict loaders and compiler rules;
- primitive contracts, layout, temporary IDs, and physical pin indices;
- generation settings other than the model identity selected by a scored row;
- causal fake behavior;
- native receipt interpretation;
- case intents and structural tier definitions;
- the scored model roster and row order;
- local result projection.

Do not patch prompts, schemas, compiler behavior, generation settings, fake
responses, or receipt interpretation around individual model failures. A model
failure is recorded through the existing native boundary and the remaining safe,
truthful matrix continues unchanged.

If a harness defect makes subsequent evidence untrustworthy or unsafe, stop the
campaign. Repairing that defect requires a newly versioned frozen campaign; it
does not amend the current campaign in place.

Cost, token counts, and latency are observational telemetry. They are not
admission, execution, or semantic-success criteria.

## Current reusable system

The campaign reuses these production boundaries unchanged:

- `SemanticGraphPlannerAdapter` and its exact prompt snapshots;
- `build_semantic_graph_response_schema()`;
- `build_worker_leaf_semantic_graph_response_schema()`;
- `load_semantic_graph()` as the sole raw-JSON admission boundary;
- `compile_semantic_graph()`;
- `compile_semantic_graph_worker_leaf_partition()`;
- `run_semantic_graph_transaction()`;
- `run_semantic_graph_single_worker_leaf_transaction()`;
- the existing `draft_create_body` Worker context, adapter, action, and
  copy-on-write applicator;
- `run_minimal_csharp_initial_body_handoff()`;
- existing `gh_create_csharp_script`, `gh_snapshot`, `gh_edit`, and `gh_connect`
  dispatch;
- existing PlanGraph execution and native records;
- `SemanticGraphExecutionResult`;
- `SemanticGraphSingleWorkerLeafResult`;
- `MinimalCSharpInitialBodyHandoffResult`;
- `LiteLLMWorkerTransport.last_call_info` and `last_raw_output`.

The Planner transport and Worker transport remain structurally injectable. The
campaign must not change model profiles, application routing, or product model
selection to vary an experimental identity.

## Admitted language remains unchanged

The campaign does not expand the semantic language. It remains bounded to:

- `number_slider`;
- `series`;
- `construct_point`;
- `polyline`;
- `square_grid`;
- zero or one `csharp_script` Worker leaf;
- the fixed Worker interface `[] -> A:double`;
- no incoming Worker-leaf edge;
- exactly one outgoing Worker cross-edge to a compatible `Number` input;
- 1–16 total nodes;
- 0–24 total edges;
- exact case-sensitive primitive and pin names;
- current input multiplicity, required-input, type-compatibility, cycle, and
  self-edge rules.

Planner-authored node IDs, parameters, and topology remain genuine semantic
choices within those constraints. The qualification fixtures do not enter
production admission, lowering, or prompting.

## Model roster

### Scored Planners

| Role | Exact model identity | Campaign purpose |
|---|---|---|
| control | `anthropic/claude-opus-4-6` | Proven frontier semantic-graph control |
| strong local | `ollama_chat/qwen3.6:35b` | Strong local Planner candidate |
| cross-family local | `ollama_chat/gpt-oss:20b` | Local family comparison |
| small local floor | `ollama_chat/qwen3:14b` | Smaller local capability floor |

### Scored Workers

| Role | Exact model identity | Campaign purpose |
|---|---|---|
| control | `ollama_chat/qwen3-coder:30b-a3b-q4_K_M` | Proven-family Worker without the replaced Q8 footprint |
| cross-family local | `ollama_chat/north-mini-code-1.0:q4_K_M` | Alternate code-model family |
| small local | `ollama_chat/gemma4:12b-it-qat` | Smaller alternate family |

The Q4 Qwen-Coder identity replaces the obsolete Q8 campaign assumption. The
following identities are reserves and do not receive scored initial rows:

- `ollama_chat/qwen3:32b`;
- the custom Qwen-Coder `64k` tag;
- Anthropic Sonnet;
- GPT-OSS as Worker.

Operator confirmation establishes this roster before the freeze. Once the first
scored call begins, a missing or unavailable model is not silently substituted.
If an exact identity cannot be confirmed before contact, the campaign does not
start. Once its transport is invoked, any failure is retained through the
existing native transport record.

## Provider-specific structured output

Schema meaning remains fixed even though provider materialization differs.

### Anthropic Planner

Use the selected semantic-graph schema inside the proven LiteLLM
`response_format` JSON-schema wrapper:

```text
generation_params.response_format = code-owned semantic schema wrapper
structured_response_schema = None
```

### Ollama Planner

Use the same selected semantic-graph schema through the existing local structured
path:

```text
generation_params contains no response_format
structured_response_schema = code-owned semantic schema
```

`LiteLLMWorkerTransport` materializes that schema as `format`.

### Ollama Worker

Reuse the existing Worker response-union schema through
`structured_response_schema`, producing the existing `format` call shape.

The deterministic cases use `build_semantic_graph_response_schema()`. The
Worker-leaf cases use `build_worker_leaf_semantic_graph_response_schema()`.
Provider adaptation must not change either schema, prompt, or local strict
admission.

## Frozen generation settings

All Planner calls use:

```text
temperature = 0
max_tokens = 8192
max_retries = 0
timeout = 120 seconds
```

All Worker calls use:

```text
temperature = 0
max_tokens = 1024
max_retries = 0
timeout = 120 seconds
```

No stop sequence, seed, reasoning option, fallback, retry, repair, or output
patching is added per model.

### Planner budget qualification

The six exact legal case fixtures were serialized using compact, sorted,
`ensure_ascii=True` JSON, admitted by `load_semantic_graph()`, and compiled by the
appropriate existing compiler.

| Case | Nodes | Edges | Maximum depth | UTF-8 bytes | `cl100k_base` reference tokens |
|---|---:|---:|---:|---:|---:|
| minimum deterministic | 1 | 0 | 0 | 175 | 46 |
| minimum Worker leaf | 2 | 1 | 1 | 395 | 98 |
| medium deterministic | 7 | 6 | 3 | 1,075 | 272 |
| medium Worker leaf | 8 | 7 | 3 | 1,351 | 338 |
| maximum deterministic | 16 | 24 | 5 | 2,884 | 858 |
| maximum Worker leaf | 16 | 24 | 5 | 2,985 | 874 |

The uniform 8,192-token Planner budget supplies more than nine times the largest
reference token count and more than 2.7 times its complete ASCII byte size. It
therefore leaves deliberate headroom for tokenizer and harmless JSON-whitespace
variation instead of turning the maximum tier into a truncation test.

The Worker keeps its proven 1,024-token bound because this campaign does not
change the fixed one-body action and current evidence does not disprove that
bound.

## Exact legal tier fixtures

The fixtures qualify the campaign cases. They are not expected Planner output
templates and are never included in model prompts.

Maximum depth means the greatest directed edge distance from a source node in
the admitted DAG.

### Minimum deterministic

Primitive multiset:

```text
number_slider x1
```

Required shape:

```text
nodes = 1
edges = 0
maximum depth = 0
Worker leaves = 0
```

The legal reference is one standalone Number Slider.

### Minimum Worker leaf

Primitive multiset:

```text
csharp_script x1
construct_point x1
```

Required shape:

```text
nodes = 2
edges = 1
maximum depth = 1
Worker leaves = 1
cross edges = 1
```

The reference graph connects `code_leaf.A` to the Construct Point `x` input.
The Worker leaf has no incoming edge and retains the exact fixed interface.

### Medium deterministic

Primitive multiset:

```text
number_slider x3
series x1
construct_point x1
polyline x1
square_grid x1
```

Required shape:

```text
nodes = 7
edges = 6
maximum depth = 3
Worker leaves = 0
```

The legal reference uses three Slider-to-Series control edges, Series to one
Construct Point coordinate, Construct Point to required Polyline vertices, and
one Slider to Square Grid cell size.

### Medium Worker leaf

Primitive multiset:

```text
number_slider x3
series x1
construct_point x1
polyline x1
square_grid x1
csharp_script x1
```

Required shape:

```text
nodes = 8
edges = 7
maximum depth = 3
Worker leaves = 1
cross edges = 1
```

The legal reference extends the medium deterministic graph with one Worker leaf
connected to an otherwise unoccupied Construct Point Number input.

### Maximum deterministic

Primitive multiset:

```text
number_slider x6
series x3
construct_point x4
square_grid x2
polyline x1
```

Required shape:

```text
nodes = 16
edges = 24
maximum depth = 5
Worker leaves = 0
```

The compiled legal reference contains:

- nine edges forming and controlling a three-Series chain;
- twelve edges occupying all coordinates of four Construct Points;
- two Slider-to-Square-Grid input edges;
- one Construct-Point-to-Polyline required vertices edge.

One Square Grid may remain unconnected. The longest reference path is Slider to
Series to Series to Series to Construct Point to Polyline.

### Maximum Worker leaf

Primitive multiset:

```text
number_slider x5
csharp_script x1
series x3
construct_point x4
square_grid x2
polyline x1
```

Required shape:

```text
nodes = 16
edges = 24
maximum depth = 5
Worker leaves = 1
cross edges = 1
```

The compiled legal reference uses the same edge-group counts as the maximum
deterministic graph. One of the twelve point-coordinate edges is the single
Worker cross-edge, and the other eleven arise from deterministic sources.

## Frozen case intents

The following exact intent strings are campaign fixtures. They are supplied as
the unchanged user intent for their row and are not added to production prompts,
examples, compiler rules, or model-specific instructions.

### Minimum deterministic intent

```text
Create a Grasshopper semantic graph containing exactly one Number Slider and no edges.
```

### Minimum Worker-leaf intent

```text
Create a Grasshopper semantic graph containing exactly one C# script leaf and one Construct Point. The C# leaf goal is to produce one finite numeric value for a point coordinate. Use the exact [] -> A:double interface, connect A to one compatible Number input, and use exactly two nodes and one edge.
```

### Medium deterministic intent

```text
Create one connected Grasshopper semantic graph containing exactly three Number Sliders, one Series, one Construct Point, one Polyline, and one Square Grid. Use exactly seven nodes, six edges, and maximum topological depth three. Satisfy every compiler-required input and choose any wiring admitted by the listed pin contracts.
```

### Medium Worker-leaf intent

```text
Create one connected Grasshopper semantic graph containing exactly three Number Sliders, one Series, one Construct Point, one Polyline, one Square Grid, and one C# script leaf. The C# leaf goal is to produce one finite numeric value used by the deterministic graph. Use the exact [] -> A:double interface with no incoming edge and exactly one outgoing edge to a compatible Number input. Use exactly eight nodes, seven edges, and maximum topological depth three. Satisfy every compiler-required input and choose any other wiring admitted by the listed pin contracts.
```

### Maximum deterministic intent

```text
Create one Grasshopper semantic DAG containing exactly six Number Sliders, three Series components, four Construct Points, two Square Grids, and one Polyline. Use exactly sixteen nodes, twenty-four edges, and maximum topological depth five. Satisfy every compiler-required input and choose any wiring admitted by the listed pin contracts.
```

### Maximum Worker-leaf intent

```text
Create one Grasshopper semantic DAG containing exactly five Number Sliders, one C# script leaf, three Series components, four Construct Points, two Square Grids, and one Polyline. The C# leaf goal is to produce one finite numeric value used by the deterministic graph. Use the exact [] -> A:double interface with no incoming edge and exactly one outgoing edge to a compatible Number input. Use exactly sixteen nodes, twenty-four edges, and maximum topological depth five. Satisfy every compiler-required input and choose any other wiring admitted by the listed pin contracts.
```

Interior wiring remains Planner-authored. The exact legal reference topology is
never exposed to the Planner.

## Structural tier observation

Every admitted graph receives one campaign-only observation:

```text
structural_tier_attained: true | false
```

This observation is derived from the canonical graph after ordinary admission.
It checks exactly:

- node count;
- edge count;
- maximum topological depth;
- primitive multiplicities;
- Worker-leaf count;
- the required single cross-edge when the case is a Worker-leaf case.

It does not require the canonical edge set to equal the legal reference graph.
Alternative wiring is permitted when it satisfies the same structural facts and
the existing compiler admits it.

The complete canonical node and edge sets remain in the ordinary local result
for later human semantic-fidelity review. They do not become product authority.

`structural_tier_attained` is not a native runner outcome, receipt, semantic
score, or claim of intent fidelity. A result may truthfully be:

```text
mechanically successful
structural_tier_attained = true
semantic fidelity = not established
```

A smaller admitted graph may likewise execute successfully while reporting
`structural_tier_attained = false`.

## Scored matrix

The matrix varies one experimental dimension at a time.

### Stage A: graph complexity

Use the proven controls for all six exact tier cases:

```text
Planner = anthropic/claude-opus-4-6
Worker  = ollama_chat/qwen3-coder:30b-a3b-q4_K_M
tools   = causal fake
```

Rows:

- minimum deterministic;
- minimum Worker leaf;
- medium deterministic;
- medium Worker leaf;
- maximum deterministic;
- maximum Worker leaf.

New scored runs: **6**.

### Stage B: Planner identity

Use the medium deterministic and medium Worker-leaf cases. Stage A's two Opus
medium rows are the controls and are not rerun.

Run only:

- `ollama_chat/qwen3.6:35b` across both medium cases;
- `ollama_chat/gpt-oss:20b` across both medium cases;
- `ollama_chat/qwen3:14b` across both medium cases.

For Planner comparison, score the Planner response, strict loading, compilation,
canonical graph, and structural-tier observation. Downstream causal fake behavior
does not change Planner scoring.

New scored runs: **6**.

### Stage C: Worker identity

Freeze one admitted medium Worker-leaf raw graph behind a fake Planner transport.
Run each scored Worker once through the real existing Worker adapter and causal
fake tools:

- Qwen-Coder Q4 control;
- North Mini Code;
- Gemma 4 12B.

The fake Planner is invoked once at its adapter boundary but makes no model call.
Only the Worker identity changes.

New scored runs: **3**.

### Stage D: repeatability

Select one Planner/Worker pair after Stages A–C without changing any harness
setting. Run:

- the medium Worker-leaf case three total times;
- the maximum Worker-leaf case three total times.

A prior row counts as repetition one only when its exact intent, Planner model,
Worker model, schemas, generation settings, and fake/live tool mode are identical.
Do not rerun an identical scored row merely because it appears in this stage.

New scored runs: **up to 6**.

### Stage E: finalists-only physical qualification

Run exactly two separately authorized live Grasshopper rows:

1. one maximum legal deterministic case;
2. one maximum legal Worker-leaf case.

Each uses a prepared disposable canvas and the selected finalist identity or
identity pair. Earlier Slice 1 and Slice 2 milestones already establish the
minimum physical path; no minimum or medium live repetition is added here.

New scored runs: **2**.

### Campaign ceiling

```text
Stage A:       6
Stage B:       6 new
Stage C:       3
Stage D:       up to 6 new
Stage E:       2
maximum total: 23
```

The hard ceiling is 23 scored runs. Prior identical rows count once. There are
no unscheduled reruns, reserve attempts, or replacement rows.

## Call budgets

### Deterministic row

```text
Planner model: 1
Worker model:  0
C# create:     0
gh_snapshot:   1 after admission
gh_edit:       1 after snapshot admission
gh_connect:    0
retry:         0
```

### Worker-leaf row

```text
Planner model: 1
Worker model:  1 after partition admission
C# create:     1 after Worker action admission
gh_snapshot:   1 after clean C# receipt
gh_edit:       1 after snapshot admission
gh_connect:    1 after deterministic terminal
retry:         0
```

### Worker-isolation row

```text
Planner adapter transport: 1 fake response
Planner model:             0
Worker model:              1
```

Calls not reached because of an existing stop remain zero. The campaign never
fills missing calls with retry or fallback behavior.

## Native outcome vocabulary

The campaign preserves existing result ownership rather than constructing a
parallel outcome system.

| Boundary | Authoritative existing fields |
|---|---|
| Planner transport | `SemanticGraphPlannerRecord.status`, `failure_reason`, `transport_error_type`, and raw response |
| Graph loading | `SemanticGraphLoadResult.admitted`, `failure`, and `reason` |
| Deterministic compilation | `SemanticGraphCompileResult.admitted`, `failure`, and `reason` |
| Worker partition | `SemanticGraphWorkerLeafPartitionCompileResult.admitted`, `failure`, and `reason` |
| Worker turn/application | Existing adapter record, disposition, action result, handoff `terminal_stage`, and `terminal_reason` |
| C# creation | Existing create receipt and handoff native records |
| Deterministic execution | `SemanticGraphExecutionResult.terminal_stage` and exact `terminal_reason` |
| Cross-region connection | Retained connect request/response and `SemanticGraphSingleWorkerLeafResult.completed` |

An absent optional native record means that boundary was not reached. The
campaign does not invent placeholder stages or normalize distinct native reasons
into a second taxonomy.

Mechanical success means only the existing direct terminal equation was
satisfied. It does not establish semantic fidelity.

## Causal fake screening

Stages A–D use causal fake tools. The fake boundary must:

- accept only the exact expected call sequence;
- derive create receipts from the actual C# create request;
- derive snapshot state from previously admitted fake mutations;
- derive `gh_edit` mappings, instance identities, counts, and flows from the
  actual edit request;
- retain the existing physical C# output order `out/0`, then `A/1`;
- derive `gh_connect` evidence from the actual receipt-derived endpoint GUIDs
  and physical pin indices;
- refuse substitutions, repeats, updates, and calls after completion;
- return causal failure responses without retry or repair.

Fake screening can establish model-contract compliance, graph admission,
compilation, Worker action admission, request propagation, call budgets, and
causal result interpretation. It does not establish real Grasshopper component
availability, C# compilation, or physical wire materialization.

## Live physical qualification

Only Stage E contacts Rhino and Grasshopper, under separate explicit
authorization for each row.

The live boundary establishes only what current native receipts and structural
verification prove:

- the qualified primitive identities are accepted by real `gh_edit`;
- the maximum requested graph materializes structurally;
- returned mappings and wires satisfy existing verification;
- the Worker-authored C# leaf compiles cleanly for that row;
- physical output `A/1` connects to the intended deterministic input;
- the existing terminal equations hold.

It does not establish runtime value correctness, broad semantic fidelity,
repeatability beyond the declared rows, arbitrary C# interfaces, or generalized
intent coverage.

No cleanup, retry, replan, repair, update, resnapshot, fallback, or second Worker
call is permitted. Partial mutation remains an ordinary unsuccessful native
result.

## Minimal operator-only support

The campaign requires at most one private operator script and its focused tests.
It must not change any production module.

The script should:

- expose one closed campaign-row identifier at a time;
- resolve that row to one frozen intent, case, model identity or pair, schema
  materialization, generation settings, and tool mode;
- refuse unknown rows or overrides before contact;
- run exactly one existing transaction;
- use one private causal fake for fake-backed rows;
- use the existing `ToolDispatcher` unchanged for separately authorized live
  rows;
- retain exact role-local and tool call counts;
- write one bounded local JSON result outside the repository;
- exit after that single row.

It must not loop over the matrix, choose winners, retry failures, discover
models, mutate profiles, launch Rhino, prepare canvases, or publish results.

The local result reuses existing records and contains only an ordinary
projection sufficient for review:

- merge SHA and campaign-row identity;
- exact intent;
- exact Planner and Worker identities when invoked;
- frozen generation settings and provider materialization names;
- raw Planner and Worker responses and their existing records;
- canonical graph and canonical edge set when admitted;
- native compile, handoff, deterministic, and connect results when reached;
- exact call counts;
- `structural_tier_attained`;
- best-effort token, latency, and cost telemetry;
- fake or live tool mode;
- any ordinary raised exception type without credentials or traceback.

Raw model and tool content makes the file sensitive disposable diagnostic data.
It remains under the existing local trace directory convention. No manifest,
checksum, archive, dataset manager, upload, sealing, public verifier, or authority
claim is added.

## Anti-quagmire stop conditions

Stop before implementation or campaign execution if the proposed support
requires:

- any product-module change;
- a prompt, schema, loader, compiler, runner, or receipt change;
- model-specific semantic rules;
- dynamic model discovery or a registry;
- more than one operator script plus focused tests;
- a benchmark scheduler or automatic matrix loop;
- a new result hierarchy, trace framework, archive, or dataset manager;
- more than 23 scored rows;
- more than two live Grasshopper rows;
- a retry, fallback, repair, cleanup, or replacement-row mechanism;
- knowledge retrieval, DSPy optimization, product UI, or model routing.

If a model produces an invalid or smaller graph, record the existing refusal or
`structural_tier_attained=false`. Do not modify the harness to help that model.

## Explicit non-claims

This campaign does not claim:

- general user-intent coverage;
- semantic fidelity from compilation or structural success alone;
- runtime value correctness;
- arbitrary Grasshopper primitives or pin types;
- more than one Worker leaf;
- variable Worker interfaces;
- learned routing or automatic model selection;
- DSPy optimization;
- knowledge retrieval or corpus construction;
- statistically sufficient benchmarking;
- canonical scientific evidence;
- product readiness or a user-facing surface.

It is a bounded qualification of the frozen compositional harness and selected
model identities against six legal structural cases.
