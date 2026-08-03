# Compositional Agent Harness Roadmap

- **Status:** Active product architecture roadmap
- **Created:** 2026-08-02
- **Baseline:** `1e0a79934770e0ed56370bb9811f21e10fd2a0b7`
- **Scope:** Semantic planning, deterministic compilation, bounded Worker jobs,
  native execution, receipt handling, and eventual product exposure
- **Non-scope:** Release packaging, a universal intermediate representation,
  per-intent capability schemas, or another scientific archive system

## Why This Roadmap Exists

Rook has proved a real end-to-end transaction:

```text
exact user intent
-> one frontier Planner call
-> one local Worker call
-> one real Grasshopper C# create
-> authentic compile receipt
-> deterministic verification
-> clean terminal result
```

That result established transport, role separation, Worker handoff, native tool
routing, receipt consumption, and product event projection. It did not establish a
general planning language. The successful specimen compiled every accepted intent to
the same fixed interface: no inputs and one `A:double` output. Its product button was
therefore removed; the internal path remains useful evidence and regression coverage.

The next program must broaden semantic freedom without rebuilding the evidentiary
machinery that made the earlier work difficult to change.

## Product Principle

Rook should be broad because a strong model can compose a finite set of typed
primitives, not because the repository contains one schema for every user request.

```text
Frontier Planner authors a semantic program and design topology
-> deterministic compiler validates and lowers what it understands
-> unresolved leaf tasks become bounded Worker jobs
-> native tools execute the compiled operations
-> receipts complete the transaction or return to the Planner only when replanning is needed
```

Strictness belongs at the boundaries of primitives, authority, and execution. The
Planner must retain freedom over semantic structure inside those boundaries.

## Two Different Graphs

The program must keep two graph meanings separate.

### Semantic Design Graph

Describes **what should be built**:

- typed components or operations;
- parameters and user-authored facts;
- dataflow and dependency topology;
- acceptance conditions;
- explicitly unresolved leaves that require model-authored content.

The frontier Planner owns this graph within the admitted primitive vocabulary. The
topology can also provide local context and useful shorthand to weaker Workers.

### Execution PlanGraph

Describes **how admitted work progresses**:

- runnable, blocked, succeeded, failed, and terminal states;
- producer and verifier ordering;
- native execution records;
- receipts and bounded escalation.

The deterministic compiler produces this graph. The Planner and Workers do not edit
its runtime state or invent its control rules.

Rook's existing `PlanGraph` is an execution-state substrate. The v2 Grasshopper
recipe graph (`components`, `flows`, `subgraphs`) and `recipe_to_edit()` are the
closest existing design-graph candidate, but they are not adopted by this roadmap
without the fit audit below.

## Reuse And Containment

### Reuse

- model profiles and one-call Planner/Worker transports;
- strict structured-response loading;
- local Worker context, adapter, harness, and disposition boundaries;
- typed tool dispatch and the native Rhino/Grasshopper bridge;
- `PlanGraph` execution, verification, and receipt records;
- the v2 recipe graph and `recipe_to_edit()` where the fit audit proves them adequate;
- the private JSONL flight recorder for authorized live diagnosis.

### Keep As Historical Evidence

- the fixed Worker-first C# specimen;
- the repair-path specimen;
- LM9 scientific checkpoints, archive policies, and governed-resolution results;
- completed implementation plans and milestone notes.

These may supply tested mechanisms. Their fixed semantic envelopes, scientific
authorization systems, and experiment-specific outcome taxonomies do not become the
new product architecture.

## Program Slices

Each slice introduces one new behavioral freedom and stops for review before the
next begins.

### Slice 0: Representation Fit Audit

Perform a read-only comparison between the desired semantic design graph and the
existing v2 recipe graph/lowerer.

The audit must answer:

- Can components and typed pins be represented without fixture-specific fields?
- Are flow identities and ordering deterministic enough for lowering?
- Can nested or reusable topology be represented honestly?
- Can the same semantic program include Rhino and Grasshopper operations, or should
  the first implementation remain Grasshopper-only?
- Where can an unresolved Worker leaf appear without granting it topology authority?
- Can native receipts be associated with the originating semantic node?

**Deliverable:** a short decision note selecting reuse, a narrow extension, or a
small replacement. No production code, universal IR, registry, provider call, or
live mutation belongs in this slice.

### Slice 1: Variable Topology Without A Worker

Let one frontier Planner produce a semantic design graph using a small set of
already deterministic primitives. Compile and execute it without a Worker.

Use two genuinely useful, structurally different witnesses chosen after the fit
audit. They must prove that changing the intent changes nodes, connections, or
parameters rather than merely changing prose. Avoid arbitrary toy requests selected
only to make the test pass.

**Success:** both graphs validate, lower, execute through existing typed tools, and
produce independently checked receipts. Unsupported primitives refuse clearly.

### Slice 2: One Unresolved Worker Leaf

Admit one semantic node whose topology and interface are Planner-owned but whose
bounded payload cannot be produced deterministically, such as a C# body.

The Worker receives only the local semantic neighborhood, typed interface,
acceptance conditions, representation convention, and one allowed action. It returns
only the missing payload. It cannot add nodes, edges, tools, retries, or execution
policy.

**Success:** the same compiled transaction works with one deterministic region and
one Worker-authored leaf. No second Worker call or repair path is added.

### Slice 3: One Receipt-Driven Replan

Only after an authentic execution receipt demonstrates a semantic or environmental
contradiction, return bounded evidence to the frontier Planner.

Permit one revised semantic graph. Revalidate and recompile it from the beginning;
do not patch the execution graph or let the Worker decide the new topology.

**Success:** one observed failure produces either one admitted revision or one honest
stop. There is no generic retry loop, fallback model, or hidden repair.

### Slice 4: Product Graduation

Expose the harness through a generic product action only after the earlier slices
prove materially different intents. RookChat remains a view and lifecycle owner, not
the planning runtime.

Graduation requires:

- at least two distinct topology families;
- at least one deterministic-only transaction;
- at least one bounded Worker-leaf transaction;
- truthful unsupported-capability behavior;
- ordinary bounded diagnostics through the existing flight recorder;
- no capability-specific button or mode presented as general intelligence.

The product surface should express a generic user action and render native progress
and receipts. It should not expose template IDs, Worker actions, or harness internals.

## Breadth Model

The same harness should eventually address requests such as:

- a phyllotaxis point field with sliders and a Worker-authored C# leaf;
- a Ladybug/Honeybee solar analysis graph when those plugin primitives are available;
- a Rhino box array with a height gradient using native creation and transform
  primitives;
- layer cleanup against a supplied JSON convention using inspection, comparison, and
  bounded mutation primitives.

These are not four capability schemas. They are semantic programs composed from
different admitted primitives. A request that needs an unavailable primitive should
stop as unsupported, identify the missing primitive, and leave the document
unchanged.

## Anti-Quagmire Rules

1. Add one new behavioral degree of freedom per slice.
2. Do not create a per-intent template, capability schema, or UI affordance.
3. Do not create a universal IR before the fit audit proves the existing graph
   inadequate.
4. Do not add a registry until at least two real consumers require it.
5. Do not invoke a Worker where deterministic lowering is sufficient.
6. Do not add retry or replanning before an authentic receipt requires it.
7. Use ordinary ephemeral records and the existing JSONL trace; do not add archives,
   sealing, proof carriers, or parallel systems of record.
8. Test semantic invariants and representative refusal classes. Do not pursue
   exhaustive provenance closure for an ordinary product transaction.
9. Prefer a few focused production modules and one real vertical. If a slice starts
   changing several ownership layers or inventing future consumers, stop for scope
   review.
10. Three repeated high-severity findings at the same boundary trigger design
    reconsideration, not another layer of local patches.
11. No product UI work occurs before Slice 4.
12. A successful test specimen is evidence, not a product claim.

## Decision Gates

At the end of each slice, answer only:

1. What new freedom did this slice prove?
2. What authentic evidence supports that claim?
3. What remains fixed or unsupported?
4. Can the next slice reuse the result without generalizing it first?

If the fourth answer is no, stop and simplify before proceeding.

## Immediate Next Action

Run Slice 0 as a read-only fit audit. Do not choose the first implementation witness,
change the semantic schema, re-expose a product button, or contact a model/native
runtime until that audit is reviewed.
