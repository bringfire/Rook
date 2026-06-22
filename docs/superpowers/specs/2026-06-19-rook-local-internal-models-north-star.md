# Rook Local/Internal Models North-Star - Scaffolded Execution & Reliability

- **Date:** 2026-06-19
- **Status:** Foundational architecture draft. Corollary to the multi-file topology north-star.
- **Author:** Codex senior-review synthesis from Rook local-model testing, tool-surface audits, the Rhizome scaffold-held planning discussion, and LogicRAG review.
- **Area:** RookChat, local/internal execution profiles, tool registry/schema exposure, `IntentPlanner` / `ExecutionPlan` / `SmartExecutor`, knowledge injection, Grasshopper script tooling, local eval harnesses.
- **Relationship to other docs:**
  - Complements `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`. That document defines the macro topology: cloud-grade coordinator plus many cheap/local file workers. This document defines how those cheap/local workers become reliable enough to exist.
  - Builds on the Rhizome concept `pages/concepts/scaffold-held-planning-for-sparse-models.md` and source note `pages/sources/chen-2025-logicrag.md`.
  - Incorporates lessons from `docs/superpowers/specs/2026-06-17-rookchat-tool-schema-contract-hardening-design.md`, `docs/superpowers/specs/2026-06-18-rookchat-gh-script-tier0-affordance-design.md`, and `docs/superpowers/specs/2026-06-18-gh-script-compile-status-truthfulness-design.md`.
  - Does not supersede `docs/CURRENT_ARCHITECTURE.md`; RookNative remains the sole in-Rhino HTTP/control surface, and the managed companion remains internal.

---

## 1. Why this document exists

The local-model failures are not random bad luck and they are not solved by one more prompt sentence. The recent Grasshopper C# script failures exposed a general architectural problem:

- local models overfit literal examples;
- they attach arguments to the wrong visible tool;
- they cannot infer hidden runtime contracts such as "output pins become variables";
- they treat transport success as task success;
- they often cannot hold a multi-step plan across create, check, repair, and report;
- they do not reliably pull knowledge or ask for missing tools unless the scaffold pushes that work.

The wrong conclusion is "local models are useless." The more useful conclusion is:

> Local/internal models are not small frontier agents. They are bounded executors that can be useful when Rook holds the plan, the contracts, the memory, and the verification outside the model.

This document gives that path a durable name and roadmap. The goal is not to make a weak model clever by asking harder. The goal is to reduce what the model has to hold in its own reasoning until the remaining task is small, explicit, validated, and repairable.

---

## 2. North-Star

### 2.1 The one sentence

> Rook's local/internal model tier should execute one well-scaffolded node at a time inside a Rook-owned plan graph, with model-visible tools compiled from verified capability contracts, preflighted before mutation, checked after execution, and summarized into rolling task memory.

### 2.2 The inversion

For frontier models, the model can be the planner and Rook's knowledge graph is a subsidy.

For local/internal models, the scaffold is the planner and the model is a node resolver.

That inversion changes the design center:

| Frontier path | Local/internal path |
|---|---|
| Broad tool surface is tolerable. | Narrow execution-profiled surface is required. |
| Examples may be interpreted correctly. | Examples are sticky and must be quarantined. |
| The model can infer missing plan edges. | Rook must provide or validate plan edges. |
| Repair can live in conversation. | Repair must preserve typed state and target IDs. |
| Result nuance may be understood. | Result state must be mechanically classified. |
| Retrieval can be suggested. | Retrieval must be scheduled and pushed. |

This is not a second product. It is the bottom tier promised by the topology north-star: many cheap workers, each made competent by external structure.

### 2.3 The operating contract

Every local/internal model turn should be shaped like this:

```
user/task intent
    -> execution profile selection
    -> plan graph / workflow contract
    -> one active node
    -> scheduled knowledge push
    -> narrow model-visible tool set
    -> preflight validation
    -> tool execution
    -> deterministic verifier
    -> rolling memory update
    -> next node, repair, or escalation
```

The local model should rarely see "the whole world." It should see the current node, the relevant contract, the exact available tools, and the memory needed to move one step.

---

## 3. Current diagnosis

This is not a huge mess. It is a mature system with sedimentary layers and a few missing invariants that matter much more for sparse models than for frontier ones.

### 3.1 What is already strong

- Rook already has a real knowledge substrate and typed route/operation knowledge.
- RookChat already has a small initial active tool set rather than exposing every MCP tool by default.
- The recent schema-contract work is moving model-visible schemas toward closed, testable contracts.
- Grasshopper script create/update tools already have enough runtime behavior to support repair when IDs and errors are preserved.
- The topology north-star already names the economic reason local workers matter.

### 3.2 The load-bearing gaps

1. **Visible does not always imply dispatchable.** Audits found paths where a tool can be model-visible from a full catalog or group but unavailable to `ToolDispatcher`. This is survivable for humans and frontier agents; it is toxic for local models.
2. **The model-visible schema is not yet the single truth.** Rook has MCP schemas, fallback schemas, local overrides, cached catalogs, dispatcher transforms, and server case arms. They are converging, but the invariant is not yet fully architectural.
3. **`ExecutionPlan` is single-operation.** The current small-model typed path plans one operation plus fallbacks for that operation. It has no subproblems, dependency edges, per-node memory, or DAG walk.
4. **Tool success has been overloaded.** Transport completion, write/placement milestone, compile/application success, and verification success need distinct names and UI/result handling.
5. **Script component creation exposes hidden environment grammar.** C# code is not enough. The effective API is code body plus declared pins plus pin variable names plus access modes plus compile/solve repair.
6. **Examples are too easy to literalize.** A "box" example in generic live guidance teaches weaker models to make a box, not to apply a grammar.

### 3.3 The critical review conclusion

The architecture should not chase every model failure with a patch. The structural order is:

1. make the visible tool surface truthful and dispatchable;
2. make tool contracts preflighted and mechanically validated;
3. make result truth unambiguous;
4. put multi-step planning outside the model;
5. only then optimize prompts, descriptions, model choice, or harness variants.

---

## 4. Design principles

### 4.1 Scaffold over discipline

If a local model repeatedly fails a contract, the durable fix is not "tell it harder." The durable fix is to externalize the contract into schema, validation, scheduling, verifier gates, and repair state.

### 4.2 Grammar, not recipes

Live tool guidance should teach the environment grammar, not task content.

Good generic guidance:

```text
For RhinoCode C#, provide body code and assign declared output variables by pin name.
Example shape: OutputName = <RhinoCommon geometry or value>;
```

Bad generic guidance:

```text
Make a box by assigning B = Brep.CreateFromBox(...);
```

There is a narrow exception: abstract shape examples are allowed when they explain grammar without supplying task content. `OutputName = <RhinoCommon geometry or value>;` is a shape example. `B = <box construction>;` is task content when the user's request did not ask for a box.

Concrete task examples belong in clearly labelled docs, fixtures, eval prompts, and tests. They should not be injected as generic repair hints unless the current user task actually asks for that content.

Current live schema text still contains box/Brep examples in places. LM1 should not simply delete every example; it should classify live examples into:

- **allowed shape examples:** generic placeholders, pin-name grammar, access-mode grammar;
- **allowed task examples:** only in labelled examples, fixtures, tests, or task-specific prompts;
- **forbidden generic guidance:** content recipes shown for unrelated user tasks.

### 4.3 Visible implies dispatchable

No model-visible tool should be absent from the active dispatch path for that same runtime/execution profile. If a tool is MCP-only, it must not appear in an internal RookChat execution profile unless the internal dispatcher can call it or explicitly proxy it.

### 4.4 Schema equals dispatcher

If the schema allows a call, the dispatcher should accept its shape. If the dispatcher rejects a shape, the schema should not advertise it. Compatibility aliases are allowed only when named and tested.

### 4.5 Preflight before mutation

A tool family with hidden runtime grammar needs a preflight gate before it mutates Rhino or Grasshopper. The gate should catch impossible contracts early and return corrective, structured failures.

### 4.6 Verification is a state, not a vibe

The result model must separate:

- `transport_status`: did the tool call return?
- `contract_status`: did arguments pass schema/preflight?
- `operation_status`: did the requested operation succeed?
- `verification_status`: was the result checked against the target substrate?
- `artifact_status`: was the intended object/component/file produced and addressable?

Top-level success should not go green merely because bytes moved across a boundary.

### 4.7 Push, do not hope for pull

Local models should not be expected to remember to query the KG. The scheduler should push the right knowledge packet at each plan node.

### 4.8 Hard edges are contracts; soft edges are hints

This is the main correction to make carefully.

Rook has several possible edge sources:

- typed tool contracts and preconditions;
- verifier-defined dependencies;
- known workflow ordering;
- KG `prerequisite` or correction edges;
- observed successor/Markov statistics.

Only explicit contracts, preconditions, effects, and verifiers should become hard dependency edges by default. Observed successor statistics mean "B often follows A"; they do not automatically mean "A is required before B." Sparse models cannot reliably detect a wrong hard edge, so promotion from soft to hard must be gated by evidence and tests.

### 4.9 Escalation is part of autonomy

The local path should know when to stop. A bounded local worker that escalates cleanly is more valuable than one that keeps mutating blindly.

---

## 5. Core architecture

### 5.1 Layers

```
Execution Profile Layer
  chooses local/internal/frontier behavior, tool budget, context budget, escalation policy

Capability Contract Layer
  compiles model-visible tools from canonical capability records
  enforces schema/dispatcher parity and visibility rules

PlanGraph Layer
  holds per-task nodes, edges, node contracts, verifier gates, and scheduled knowledge pushes

Node Execution Layer
  emits one single-operation ExecutionPlan or workflow call at a time
  calls preflight, tool dispatcher, and verifier

Working Memory Layer
  maintains rolling per-task memory and target IDs
  compresses prior node results for the next node

Learning/Eval Layer
  records transcripts, failures, successful patterns, and candidate workflow promotions
```

### 5.2 Execution profiles, not provider profiles

Rook should separate the model/provider profile from the execution policy. The repo already has model/provider/role profile machinery; this document's concept is an `execution_profile`: the policy bundle that controls tool budget, context budget, mutation allowance, verifier strictness, and escalation behavior for a worker.

| Execution profile | Role | Surface | Planning |
|---|---|---|---|
| `frontier_coordinator` | Macro planning, cross-file reasoning, ambiguous design judgment | Broad but still contracted | Model can plan, scaffold optional |
| `local_internal_worker` | In-file execution node resolver | Narrow, execution-profile-compiled | Scaffold owns plan |
| `local_repair_worker` | Repair an existing failed node/component/object | Very narrow, target-bound | Receives fixed IDs and errors |
| `local_classifier` | Cheap classification/ranking/extraction | Read-only or no tools | No mutation |
| `deterministic_verifier` | Mechanical checks, not an LLM | No generative tools | Verifier gate |

"Internal" does not mean trusted. It means Rook controls more of the environment. Internal/local models still run behind the same contracts and verifier gates.

### 5.3 Capability records

The long-term tool source of truth should be a capability registry record, not scattered schema prose. A record should contain at least:

```json
{
  "name": "gh_create_csharp_script",
  "family": "grasshopper_script",
  "execution_profiles": ["rookchat_local", "rookchat_cloud", "external_mcp"],
  "dispatch_path": "tool_dispatcher",
  "schema": {},
  "preflight": "gh_csharp_script_contract",
  "result_contract": "script_component_create",
  "verifier": "gh_component_errors_for_target",
  "risk": "mutation",
  "requires": ["grasshopper_available"],
  "examples_policy": "example_only_not_live_hint"
}
```

This does not require a giant rewrite in the first slice. It defines the direction: model-visible schemas should be compiled from capability records or audited against them.

### 5.4 PlanGraph

The PlanGraph is an ephemeral per-task artifact. It is not the persistent KG and it is not a Grasshopper canvas.

Minimum node shape:

```json
{
  "id": "node_03",
  "intent": "create verified RhinoCode C# script component",
  "tool_family": "grasshopper_script",
  "inputs": {"requested_geometry": "<task-specific geometry/value>"},
  "outputs": {"component_guid": "pending", "output_pin": "B"},
  "contract": "gh_csharp_body_script_v1",
  "knowledge_push": ["rhinocode_csharp_body_contract", "rhino_common_brep_creation"],
  "preflight": "gh_csharp_script_contract",
  "verifier": "gh_component_errors_for_target",
  "repair_policy": "repair_existing_component_once_then_escalate"
}
```

Edges should be typed:

- `requires`: hard dependency from contracts/preconditions;
- `produces_for`: data dependency;
- `verifies`: check must run after operation;
- `repairs`: repair node targets a prior failed artifact;
- `suggests_next`: soft empirical successor hint;
- `blocks`: failure state prevents dependent node execution.

The PlanGraph should sit above the current `ExecutionPlan`. Each node can still emit a single-operation `ExecutionPlan`; the key change is that ordering, memory, and repair state live outside the model.

### 5.5 Rolling memory

A local task needs a compact working-memory tier:

- persistent KG = long-term memory;
- PlanGraph = current task structure;
- rolling memory = compressed resolved state;
- model context = current node registers.

Rolling memory should preserve:

- target IDs, GUIDs, object IDs, session/document IDs;
- declared pins and variable names;
- operation status and verifier status;
- concise error summaries;
- user-level intent that must not be lost;
- constraints that affect later nodes.

It should not preserve every raw transcript token. The purpose is to carry the few facts a weak model cannot be trusted to remember.

---

## 6. Tool surface doctrine for local/internal models

### 6.1 Initial surface

The initial local execution profile should expose a small set of high-value tools:

- session/model/meta tools needed to orient;
- read-only inspection tools;
- verification/error tools;
- a few common workflow or script tools that would otherwise be hidden behind a bad first move;
- `request_tools` only when the next group is genuinely needed.

Adding `gh_create_script`, `gh_create_python_script`, `gh_create_csharp_script`, and `gh_update_script` to the initial RookChat surface is consistent with this doctrine. It makes the correct first move visible. It does not justify exposing the entire GH/Rhino surface.

### 6.2 Tool groups

Tool groups should be execution-profile-aware:

- `external_mcp`: full public MCP surface, with public docs.
- `rookchat_cloud`: broader internal surface for stronger models.
- `rookchat_local`: constrained surface with workflow affordances and strict contracts.
- `readonly`: inspection-only.
- `planner`: no mutation, plan and query only.

This prevents local-model support from harming larger models. Stronger models can use broader execution profiles; local models get the narrowed, validated execution profile.

### 6.3 Schema description policy

Descriptions should be short, contractual, and non-literal:

- Name the substrate grammar.
- Name required variables, pin names, IDs, or modes.
- Name prohibited shapes such as `GH_Component` subclasses when relevant.
- Avoid task-content examples in generic live schemas.
- Put longer examples in fixtures and labelled docs.

### 6.4 Dispatchability gate

Every active schema set should pass:

```text
for each model-visible tool in execution profile:
  tool exists in dispatch path
  schema is closed unless allowlisted
  required fields match dispatcher
  no-arg tools reject and do not advertise args
  result contract is known or explicitly legacy
```

This gate should run in tests and optionally as startup diagnostics.

The first implementation should audit exact Rook exposure/dispatch surfaces, not just the critical GH happy path:

- meta-tool intercepts such as `request_tools`, `search_tools`, model/session helpers, and history helpers;
- local ChatRunner tools and local override catalog entries;
- `ToolDispatcher` local tools;
- dispatcher transform functions;
- bridge route mappings;
- cached MCP catalog entries after contract normalization;
- pseudo-tools or MCP/server-only tools, which must be explicitly excluded, proxied, or given a real internal dispatch path before becoming visible.

The invariant is about active/requested schema sets per execution profile. A test that proves `gh_create_csharp_script` dispatches is necessary, but it is not enough to prove the execution profile is coherent.

---

## 7. Contract/preflight layer

### 7.1 Why preflight matters

Some Rook tools are simple: arguments map directly to one route. Others are little programming environments. GH script components are the canonical example.

For these, the model is not merely choosing a tool. It is constructing a contract:

1. component runtime/language;
2. code mode;
3. input pins;
4. output pins;
5. pin variable names;
6. access modes/types;
7. assignment behavior;
8. repair path after compile/solve.

If the contract is incoherent, Rhino cannot fix it. Preflight should reject before mutation where possible.

### 7.2 First tool-family preflight: RhinoCode C#

The first preflight slice should be C# only because that is where the sharpest failures are:

- body code vs full source confusion;
- `GH_Component` subclass code sent to a script component;
- undeclared or unassigned output pins;
- invalid C# identifiers as pin names;
- duplicate pins;
- invalid access values;
- compile errors reported as nested details under green top-level success.

Required preflight behavior:

- validate declared input/output names as C# identifiers;
- validate duplicate pin names;
- validate access values: `item`, `list`, `tree`;
- reject obvious `GH_Component` / `SolveInstance` plugin source in body mode;
- distinguish body source from full `Script_Instance : GH_ScriptInstance` source;
- warn or fail when declared outputs are not assigned, with a conservative parser;
- return targeted corrective messages:
  - "Declared output `B`; assign `B = ...` in body code."
  - "C# script components use body code by default; do not send a `GH_Component` subclass."
  - "Output pin names become variables and must be valid identifiers."

This should apply to both `gh_create_csharp_script` and `gh_create_script(language="csharp")`, and later to `gh_update_script` where pin context is known.

The ordering matters: this preflight must run before any `/gh/create-component` placement/write mutation. Pin normalization and C# wrapping can still be preparation steps, but invalid identifiers, duplicate pins, obvious plugin-component source, and incoherent output contracts should be caught before a component is created whenever they are detectable.

### 7.3 Preserve repair anchors

Failed mutation can still be useful if it preserves the target:

- component GUID;
- pins in/out;
- code mode;
- compile errors;
- verifier status;
- suggested next tool.

A local model should repair the existing component, not create duplicates because the failure erased the handle.

### 7.4 Expand by family, not by anecdote

After C# script preflight, add preflights by recurring family:

- Python script geometry outputs;
- GH component creation/update;
- Rhino typed route argument contracts;
- block mutation contracts;
- document/save/refresh contracts in the topology fan-in track.

Each family should get a contract and verifier. Avoid one-off patches that only recognize the last bad prompt.

---

## 8. Result truth ontology

### 8.1 Required status fields

For local/internal execution profiles, every mutating or verification-relevant tool should eventually report a structured status envelope:

```json
{
  "success": false,
  "transport_status": "returned",
  "contract_status": "passed",
  "operation_status": "partial",
  "verification_status": "failed",
  "artifact_status": "created_with_errors",
  "message": "Component was created but has compile errors.",
  "repair": {
    "tool": "gh_update_script",
    "target": "component_guid"
  }
}
```

This richer status model should migrate through an adapter first. Keep the public MCP wire shape stable; normalize legacy boolean-centric results into these fields at the ChatRunner, dispatcher, or tool-result boundary while individual tools migrate.

### 8.2 Top-level success rule

For tools whose stated goal includes a checkable application result, top-level `success: true` should mean the operation reached that checked goal, or that verification was explicitly deferred/unavailable.

Examples:

- "Created component and it has no target compile errors" can be success.
- "Placed component but it has target compile errors" should be failure with repair data.
- "Source was written but solver verification is locked/deferred" can be write success only if the payload clearly says verification is deferred.

### 8.3 UI/card classification

RookChat cards should render:

- failed contract/preflight as failed;
- partial mutation with verifier failure as failed or warning, not green done;
- verification deferred as unverified, not success;
- unrelated canvas errors separately from target component errors.

Sparse models read UI feedback through the next tool-result message. The UI truth layer is also the model truth layer.

---

## 9. Scaffold-held planning

### 9.1 What changes

Today, the small-model typed path can produce one operation. The north-star path produces a PlanGraph, then executes one node at a time.

The first implementation should be a tiny adapter over existing planning/execution concepts, not a competing planner. Rook already has Planner/TaskSpec concepts, postconditions, and the single-operation `ExecutionPlan`; LM4 should initially wrap those with just enough graph structure to preserve node order, rolling memory, target IDs, verifier gates, and repair policy.

**Implementation note (2026-06-22): roadmap labels evolved during delivery.**
The original LM4 described here was "PlanGraph skeleton for local tasks." That
work was intentionally decomposed and largely landed earlier, across LM1E-G and
LM3A-H, before any live execution bridge was added. In the implemented campaign:

- LM1E-G established the pure reducer, tool-result outcome adapter, and bridge.
- LM3A-H established template selection, binding, walking, verifier/projection
  primitives, role adoption, and the non-live
  `create -> verify -> repair -> reverify -> done` proof.
- LM3I is now the next bridge slice: role-aware live evidence capture.
- What remains of "LM4" should be read as live PlanGraph execution: a production
  runner/evidence bridge/evaluation layer that consumes the proven graph
  semantics instead of inventing them.

The first version does not need to solve every design workflow. It needs to make a simple multi-step local task mechanically reliable:

```text
create script component
  -> verify target component
  -> if errors, repair same component
  -> verify again
  -> report exact final state
```

That graph is small, but it exercises every required concept:

- dependency edges;
- target preservation;
- scheduled verification;
- repair policy;
- rolling memory;
- escalation after bounded attempts.

### 9.2 How KG participates

The KG should supply:

- stable preconditions and tool-family gotchas;
- valid contract fragments;
- repair hints for known error classes;
- examples only when labelled and task-appropriate;
- soft ordering priors for likely next steps.

The KG should not silently become the plan. The PlanGraph is per-task. KG facts are inputs to plan compilation and node execution.

### 9.3 Scheduler behavior

The scheduler should:

- topologically walk hard dependencies;
- push relevant knowledge before each node;
- restrict active tools to the node execution profile;
- run preflight before mutation;
- run verifier after mutation;
- update rolling memory;
- choose repair, proceed, or escalate based on typed status.

Same-rank batching is allowed only when operations are independent and the substrate supports parallelism. Grasshopper canvas mutation and Rhino document mutation should default to conservative serialization unless proven safe.

### 9.4 Adaptation

Local models may propose adjustments, but the scheduler owns graph mutation.

Allowed:

- model suggests a missing node;
- scheduler validates it against known contracts;
- scheduler inserts it if safe.

Not allowed:

- model invents arbitrary tools or dependencies;
- model silently skips verifier gates;
- model changes target IDs after a failed mutation without an explicit reason;
- unvalidated soft successor hints become hard execution order.

### 9.5 Escalation

Escalation triggers should be explicit:

- contract cannot be compiled;
- preflight fails twice for the same reason;
- verifier fails after bounded repair;
- needed tool is not dispatchable;
- local model proposes unsafe graph mutation;
- rolling memory exceeds execution-profile budget;
- user intent is ambiguous in a way that affects mutation.

Escalation can go to a stronger model, a frontier coordinator, or a user question depending on risk.

---

## 10. Workflow tools

### 10.1 Why workflow tools matter

For local models, a good workflow tool is not a convenience wrapper. It is a way to move hidden multi-step discipline out of the model.

Example future workflow:

```text
gh_create_verified_csharp_script
  inputs: code, pins_in, pins_out, name
  internal sequence:
    preflight contract
    create/update component
    check target errors
    return verified success or repairable failure
```

This should not replace primitive tools. It should sit above them for execution profiles that need fewer moves.

### 10.2 Workflow promotion rule

Promote a workflow when all are true:

- the same multi-step sequence recurs in local-model transcripts;
- at least one step is easy for the model to omit;
- Rook can verify the outcome mechanically;
- preserving target IDs matters for repair;
- the workflow can remain generic, not task-content-specific.

Do not promote "make one box" as a workflow. Promote "create a verified script component with declared pins."

### 10.3 Relationship to frontier models

Workflow tools do not harm larger models if they are additive and execution-profile-aware:

- frontier execution profiles can still access primitives;
- local execution profiles prefer workflow tools;
- both share the same underlying result truth and preflight validators.

---

## 11. Evaluation doctrine

### 11.1 Failure taxonomy

Every local-model run should be classifiable:

- tool discovery failure;
- tool selection failure;
- schema/argument failure;
- preflight failure;
- code/content generation failure;
- transport failure;
- application operation failure;
- verification failure;
- repair failure;
- reporting/truthfulness failure.

This taxonomy prevents "model failed" from hiding platform bugs.

### 11.2 Deterministic first

Merge gates should begin with non-live deterministic tests:

- active schema/execution-profile fixtures;
- schema/dispatcher parity tests;
- visible-implies-dispatchable tests;
- transcript simulations;
- result classifier tests;
- preflight unit tests;
- PlanGraph scheduler unit tests.

Live Rhino smokes are essential but should validate an already-specified contract, not discover it from scratch.

### 11.3 Model probes

Local provider probes are evidence, not ordinary CI gates.

For each candidate model plus execution profile, record:

- prompt;
- active tool set;
- tool calls;
- tool results;
- failure taxonomy;
- verifier results;
- whether escalation should have triggered.

Compare models only after the contract surface is stable. Otherwise the benchmark measures Rook's ambiguity, not the model.

### 11.4 Golden tasks

Start with small tasks that exercise contracts:

1. create a verified C# script component with one output;
2. repair a provided compile-error component without duplicating it;
3. create Python list-access geometry output without wrapping arbitrary objects;
4. inspect canvas and report target vs unrelated errors;
5. execute a two-node Rhino typed route workflow with verification;
6. save a workbench artifact and report durable path/status once the topology track reaches fan-in.

The original 10x10 box-grid prompt is a useful stretch regression. It should not be the first merge gate.

---

## 12. Roadmap

Use `LM` phase numbers to avoid colliding with the topology document's P1-P7 phases.

### LM0 - Baseline and doctrine

**Goal:** Name the local/internal model architecture and capture current failure modes.

Status: this document starts LM0.

Deliverables:

- this north-star doc;
- current tool-surface audit summary;
- failure taxonomy;
- initial local-model golden transcript set;
- explicit examples policy.

Exit criteria:

- the team can classify new failures without inventing a new category every time;
- local-model work is evaluated against this architecture rather than ad hoc prompt patches.

### LM1 - Contract and truth hardening

**Goal:** Make the model-visible surface closed, truthful, and dispatchable for the active local execution profiles.

Deliverables:

- closed model-visible schemas by default;
- zero-argument tool discipline;
- `gh_errors` and similar no-arg tools consistently advertised as no-arg;
- active schema fixtures for initial and requested groups;
- tool result classification that distinguishes transport, operation, and verification;
- compile-error truthfulness for script create/update.

Exit criteria:

- every active initial tool in `rookchat_local` is dispatchable;
- bad `gh_errors(code=...)` is prevented by schema or returns a corrective contract failure;
- created-with-compile-errors cannot be reported as clean success;
- local-model probes can be interpreted without wondering whether the tool surface lied.

### LM2 - Capability registry / surface compiler

**Goal:** Move from scattered tool exposure toward a canonical capability contract layer.

Deliverables:

- capability record shape;
- execution-profile membership for `external_mcp`, `rookchat_cloud`, `rookchat_local`, `readonly`, and `planner`;
- visible-implies-dispatchable audit over all execution-profile groups;
- schema source and override policy;
- allowlist for intentional open/dynamic schemas;
- startup diagnostics for stale or inconsistent catalogs.

Exit criteria:

- a new tool cannot become local-model-visible without a dispatch path and contract classification;
- cached catalogs cannot silently expose stale/open schemas without diagnostics;
- group activation is execution-profile-aware and testable.

### LM3 - Tool-family preflight and repair anchors

**Goal:** Add preflight validators and repair-preserving result contracts for the highest-risk tool families.

First family: RhinoCode C# script components.

Deliverables:

- C# pin/code coherence preflight;
- body/full-source mode validation;
- `GH_Component` subclass rejection with targeted message;
- declared-output assignment warning/failure policy;
- target GUID preservation on create/update failures;
- repair hints tied to the existing target.

Exit criteria:

- impossible C# script contracts fail before Rhino mutation when detectable;
- compile failures preserve enough state for `gh_update_script`;
- local model repair attempts target the existing component in transcript tests.

Later families:

- Python script geometry outputs;
- GH component update contracts;
- Rhino typed route argument contracts;
- document save/refresh contracts.

### LM4 - PlanGraph skeleton for local tasks

**Goal:** Give multi-step local-model execution a home above single-operation `ExecutionPlan`.

**Status / translation (2026-06-22):** this original LM4 scope has been split.
The skeleton and non-live semantics are now complete through LM3H; the remaining
work is live execution. Future work should not restart "LM4" by rebuilding the
graph model. It should treat the existing PlanGraph semantics as the substrate
and focus on the live boundary:

- role-aware live evidence capture (LM3I);
- a production runner that executes ready nodes one at a time without asking the
  model to remember the workflow;
- knowledge push / rolling-memory persistence at node boundaries;
- bounded repair/escalation policy;
- eval harnesses that measure whether the graph improves local-model reliability.

Deliverables:

- minimal `PlanGraph` adapter data model; **landed by LM1E/LM3**
- node contract and typed edge model for the first fixed workflow; **landed by LM1E/LM3**
- scheduler that executes one node at a time; **remaining live-execution work**
- scheduled knowledge push per node; **remaining live-execution work**
- rolling memory object; **landed as pure graph memory; live persistence remains**
- verifier gate support; **landed in pure semantics; live evidence capture remains**
- escalation policy hooks; **partly scaffolded; bounded live policy remains**
- non-live graph test for a hardcoded create -> verify -> repair -> verify -> report workflow; **landed as LM3H's `create -> verify -> repair -> reverify -> done` proof**

Exit criteria:

- a two-to-four-node task can run without relying on the model to remember the plan;
- node outputs and verifier status are available to later nodes through rolling memory;
- failed nodes branch to repair or escalation by policy.

### LM5 - Workflow tools and contract macros

**Goal:** Promote repeated local-model sequences into generic verified workflow tools.

Deliverables:

- workflow promotion criteria;
- first verified GH script workflow or equivalent contract macro;
- primitive tool preservation for frontier/cloud execution profiles;
- local execution-profile preference for workflow tools;
- transcript tests proving fewer model moves and better recovery.

Exit criteria:

- local models can complete common tasks through one or two workflow calls where primitives required several brittle calls;
- workflows remain content-generic and do not bake in design examples.

### LM6 - Execution profile governance and eval harness

**Goal:** Make local/internal model support measurable and maintainable.

Deliverables:

- execution profile definitions with context/tool/repair budgets;
- provider probe script and artifact format;
- golden transcript suite;
- failure taxonomy dashboard or report;
- escalation-rate tracking;
- model comparison protocol after contract stabilization.

Exit criteria:

- model regressions are distinguishable from Rook contract regressions;
- a candidate local model can be accepted, rejected, or scoped to a role based on evidence;
- merge gates remain deterministic while live probes provide supporting artifacts.

### LM7 - Integration with the multi-file topology

**Goal:** Make the local worker scaffold the executable bottom tier of the topology north-star.

Deliverables:

- Work Unit nodes can select a local/internal execution profile;
- each file/session worker runs a PlanGraph, not an unstructured chat loop;
- artifact/save/verification state flows back to the coordinator;
- merge/fan-in dependencies consume verified artifact states;
- escalation from local worker returns structured failure to the macro coordinator.

Exit criteria:

- the cloud/frontier coordinator can assign a bounded work unit to a local worker and receive a truthful artifact or structured failure;
- local worker failure does not corrupt the master/anchor document;
- fan-in waits on verified artifact states, not chat summaries.

---

## 13. First recommended implementation sequence

After this document, the first durable engineering sequence should be:

1. **Visible-implies-dispatchable audit/gate.** Make active local execution-profile schemas prove their tools are callable through the internal dispatcher.
2. **Result truth cleanup.** Complete compile-status truthfulness and tool-card/application-status classification.
3. **C# script preflight.** Validate the pin/code/body contract before mutation and preserve repair anchors after failure.
4. **PlanGraph skeleton.** Build a non-live scheduler around the create -> verify -> repair -> verify pattern.
5. **Local eval harness.** Record deterministic transcript tasks and optional provider probes against the now-stable surface.

This order is intentional. A PlanGraph on top of a lying tool surface just makes failures more elaborate. Tool truth comes first.

---

## 14. Anti-goals

- Do not expose hundreds of raw tools to a local model and call it autonomy.
- Do not fix local failures by loosening schemas or accepting arbitrary arguments.
- Do not silently auto-route malformed calls to the tool the model "probably meant."
- Do not make task examples part of generic tool guidance.
- Do not make Grasshopper the executor for a dynamic reasoning DAG.
- Do not rely on model self-reporting as verification.
- Do not let observed successor statistics become hard dependencies without promotion criteria.
- Do not remove expert escape hatches for larger models while improving local execution profiles.
- Do not build a broad prompt rewrite before contract and result truth are pinned.

---

## 15. Open questions

### 15.1 Where should PlanGraph live?

Recommendation: above `ExecutionPlan`, not inside it at first, and as a tiny adapter rather than a new planner. Keep the current single-operation contract stable and let each PlanGraph node emit an `ExecutionPlan`.

### 15.2 How hard should output-assignment preflight be?

Recommendation: start with hard failures for obvious missing assignments in simple C# body code, warnings for cases the parser cannot confidently judge, and verifier failure after execution as the final authority.

### 15.3 Should workflow tools be public MCP tools?

Recommendation: not automatically. Some workflow tools should be internal/execution-profile-only until their contracts are stable. Public exposure should come after result shape and failure behavior are settled.

### 15.4 How much should frontier models use the scaffold?

Recommendation: make the scaffold available but optional by execution profile. Frontier models benefit from inspectability and replay, but should not lose primitive access or be forced through local-worker constraints.

### 15.5 Should local models create or modify the PlanGraph?

Recommendation: they may propose nodes or repairs, but Rook validates and applies graph changes. The scheduler owns the graph.

---

## 16. Decision log

- Local/internal models are treated as bounded node resolvers, not miniature frontier agents.
- The scaffold owns plan, contracts, memory, verification, and escalation.
- Tool-surface reliability is the first structural prerequisite: visible implies dispatchable, schema equals dispatcher, closed by default.
- Generic live guidance teaches environment grammar, not task-content recipes.
- Result truth separates transport, contract, operation, verification, and artifact status.
- C# RhinoCode script preflight is the first high-value tool-family contract gate.
- PlanGraph is an ephemeral per-task execution artifact above the current single-operation `ExecutionPlan`.
- KG participates by supplying contract facts, gotchas, repair hints, and soft priors; it is not itself the task plan.
- Hard dependency edges come from contracts/preconditions/effects/verifiers. Observed successor statistics are soft until promoted.
- Workflow tools are execution-profile-aware generic contract macros, not baked task recipes.
- Deterministic contract/transcript tests precede live model optimization.
- The local worker scaffold is the executable bottom tier of the topology north-star.
