# Agent Runtime And Local-Model North Star

- **Captured:** 2026-08-04T06:58:08-04:00
- **Baseline:** `8baf325a459ec9bb53cae24b1af0fab452b3001e`
- **Status:** Working architecture anchor; not an implementation authorization
- **Related roadmap:** [Compositional Agent Harness Roadmap](../roadmaps/2026-08-02-compositional-agent-harness-roadmap.md)
- **Evidence:** [Slice 1 milestone](2026-08-03-compositional-harness-slice1-live-qualification-milestone.md), [Slice 2 milestone](2026-08-03-compositional-harness-slice2-live-qualification-milestone.md)

## Purpose

Preserve the architectural thread exposed after Slices 1 and 2 so subsequent work
does not turn another bounded specimen into the universal product architecture.

The central question is:

> Can frontier-model intelligence be amortized into a reusable scaffold that lets
> local models author and execute increasingly broad programs through Rook's typed
> tools, Workers, and receipt loop?

## North Star

```text
user intent
-> capable top-level agent
-> selected or composed skills
-> direct tool use or a model-authored temporary program/DAG
-> bounded local Worker tasks where useful
-> deterministic tools and host adapters
-> receipts and observations
-> the top-level agent continues, replans, or completes
```

The stable harness is a runtime for model-authored programs. It must not become a
repository of developer-authored solutions for every possible user intent.

## What Has Been Proven

Slice 1 proved that a frontier Planner can author materially different Grasshopper
topologies over a small qualified primitive vocabulary. The strict loader,
deterministic compiler, one-snapshot/one-edit execution, native records, and physical
receipt verification all worked against real Grasshopper.

Slice 2 proved one hybrid composition:

```text
frontier Planner
-> admitted semantic graph
-> one local Worker-authored C# leaf
-> clean C# create receipt
-> deterministic Grasshopper region
-> receipt-derived physical connection
-> completed transaction
```

The final live witness used exactly one Planner call, one Worker call, one C# create,
one snapshot, one edit, and one connect. It used no retries, repairs, updates, or
fallbacks.

These proofs establish useful mechanisms. They do not establish a general agent
runtime or a general semantic language.

## Current Harness Limits

The current semantic harness deliberately admits only:

- five deterministic Grasshopper primitives;
- at most one Worker-backed C# leaf;
- the fixed Worker interface `inputs: [] -> outputs: A:double`;
- one outgoing cross-region connection;
- one-shot Planner authorship without a receipt-driven replan.

These are limits of the current semantic contract and compiler. They are not
fundamental limitations of C#, Grasshopper, `gh_create_csharp_script`, or the models.
The underlying C# tool can represent broader named and typed pin interfaces.

## Corrected Role Model

The word `Planner` currently names several different jobs and must not obscure their
ownership.

### Agent Runtime

Owns the user-facing reasoning and action loop: conversation context, skill loading,
tool access, delegation, budgets, observations, receipts, and continuation.

### Top-Level Agent

The model occupying the Agent Runtime. It receives the user's intent directly. It
may act directly, author a temporary program, delegate bounded leaves, inspect
receipts, ask for clarification, or replan.

### Structured Author

An optional role that emits a typed artifact such as a semantic graph, task DAG,
workflow request, or tool arguments. The current `SemanticGraphPlannerAdapter` is a
one-shot structured author, not a complete agent runtime.

In a mature runtime, the top-level agent may author the artifact itself under a
skill, or it may delegate authorship as a bounded subtask. A permanent
Planner-above-Planner stack is not the target.

### Compiler

Validates and lowers an authored artifact deterministically. It should enforce
structural representability, permissions, budgets, available tools, declared
interfaces, and execution invariants. It should not encode every legal design or
user intent.

### Worker

Performs one bounded unresolved task under a declared interface and local context.
A Worker does not own global topology, retries, or product authority.

### Runner

Executes admitted operations, invokes tools and Workers as directed, retains native
records, and returns observations and receipts. It does not supply missing semantic
intent.

### Chirp Planner

A domain reasoning node inside a Grasshopper dataflow cascade. It propagates design
reasoning to downstream Chirp components when Grasshopper solves. It is not the
RookAssistant top-level agent or product transaction owner.

## Skill-First Structure

A skill constrains method rather than prescribing the final program. For example, a
Grasshopper composition skill can teach the top-level agent to inspect the canvas,
retrieve relevant component knowledge, select native and Worker-backed operations,
author topology, execute through bounded tools, inspect receipts, and revise.

The skill must not contain the one correct graph for every request. It is reusable
procedural memory.

The closest existing pattern is Codex using the `chirp-cascade` skill:

```text
skill guides decomposition and signature design
-> top-level model authors component specifications and topology
-> chirp_create and gh_edit validate and execute
-> observations guide iteration
```

`chirp_create` is a typed execution tool. The model following the skill is the
structured author.

## Stable Kernel, Dynamic Program

The model should not rewrite Python harness code for each request. It should author
an ephemeral program for a small stable kernel.

The stable kernel owns:

- skill discovery and loading;
- typed tool discovery and invocation;
- Worker or subagent delegation;
- DAG dependencies and bounded scheduling when needed;
- authority, mutation, and budget checks;
- observations, receipts, cancellation, and continuation.

The model-authored program may own:

- task decomposition;
- topology and dependencies;
- declared bounded interfaces;
- Worker instructions;
- tool choices;
- acceptance criteria;
- whether a simple task needs a DAG at all.

This is the key correction:

> Rook needs a small, stable agent virtual machine. The top-level agent writes
> programs for it at runtime. The failed pattern is hardcoding those programs into
> the virtual machine itself.

## Where Strictness Belongs

Keep hard constraints around:

- tool schemas and host-supported values;
- mutation authority and approvals;
- current host and document identity;
- call, cost, and retry budgets;
- declared Worker interfaces;
- receipt and acceptance evidence;
- graph structural validity when a graph is used.

Preserve model freedom around:

- decomposition;
- topology;
- tool and strategy selection;
- bounded interface declaration;
- direct action versus delegation;
- Worker selection;
- replanning from authentic evidence.

## Frontier Intelligence And Local Execution

The product hypothesis is not merely that a frontier Planner can delegate one fixed
leaf to a local model. It is that frontier intelligence can help design transferable
support that lets local models own more of the loop.

Frontier models can help author and review:

- procedural skills;
- tool descriptions and examples;
- the small task-program grammar;
- delegation and recovery guidance;
- retrieval strategies;
- evaluation cases and failure analysis.

That support should be a scaffold, not a precomputed collection of answers.

The desired runtime can eventually be entirely local:

```text
user intent
-> strongest suitable local model as top-level agent
-> Rook skills and retrieved knowledge
-> direct tools or a temporary DAG
-> cheaper or specialized local Workers
-> receipts
-> local continuation or replanning
```

A frontier model may remain available as an optional escalation. It must not be
silently required for the local-first product claim.

## Knowledge And DSPy

The supporting roles are distinct:

- **Skills** provide reusable procedural memory.
- **Knowledge retrieval** provides relevant component facts, prior patterns,
  project context, and experiential evidence.
- **DSPy** may optimize prompt programs only after real traces and a meaningful
  outcome metric exist.
- **Receipts** provide the physical evidence needed to evaluate and improve all
  three.

Retrospective recipes and traces may be retrieval evidence. They are not automatic
training authority or mandatory templates.

## RookChat, RookAssistant, And RookStudio

RookChat is a view and lifecycle surface, not the agent harness.

RookAssistant should be a replaceable agent guest behind the same broker capability
edge as Codex, Hermes, Claude, DeepAgents, or another external harness. The agent
owns reasoning and conversation. RookStudio owns durable workflows, approvals,
artifacts, receipts, runtime/provider state, and cross-host product flow.

The next architectural choice is not yet `Hermes versus homemade`. First define the
smallest replaceable Agent Runtime contract. Then compare an embedded existing
harness, an external harness, and a thin Rook-native runtime against that same
boundary.

## Anti-Quagmire Constraints

Until this anchor is deliberately superseded:

1. Do not add another permanent Planner above the existing Planner.
2. Do not treat the semantic graph compiler as the universal agent language.
3. Do not generalize the C# interface in isolation before defining the Agent Runtime
   boundary and the experiment it enables.
4. Do not encode a new capability schema or product button for each user request.
5. Do not choose or bundle an agent framework before evaluating it against a small
   replaceable runtime contract.
6. Do not build another large fake simulator when real tools and bounded physical
   evaluation are available.
7. Add deterministic rules only for real safety, representability, ownership, and
   evidence requirements.
8. Treat every successful specimen as evidence, not as the product architecture.

## Next Decision And Experiment

The next design work should define the minimum Agent Runtime contract for:

- exact user intent and conversation context;
- skill selection and loading;
- typed capability discovery;
- direct tool calls and optional temporary DAG authorship;
- bounded Worker delegation;
- observations, receipts, and continuation;
- cancellation, budgets, and optional escalation.

The first meaningful experiment should place the strongest suitable local model in
the top-level agent seat with one general Rook skill and existing real tools. It
should test varied intents and preserve ordinary traces and receipts. A frontier
model may review failures and improve the reusable skill, but the experiment must
measure what the local model actually owns.

No implementation, framework selection, compiler expansion, product UI, or live
model/host run is authorized by this note.
