# RookForge: Agent-Authored Capability Forge

**Date:** 2026-08-21

**Status:** Concept direction preserved for hackathon continuation; implementation is not yet specified or authorized

**Working name:** **RookForge**

**Tagline:** **Agents do not just use tools. They forge them.**

## Purpose

This document preserves the breadth of the RookForge idea so it can be resumed
on another development machine without reducing it to one demonstration, one
external service, or one media workflow.

RookForge is an agent-authoring layer for visible AEC capabilities. A user
describes a capability. An agent uses Rook to compose a Grasshopper
implementation from a small vocabulary of tested patterns. Chirp contributes
typed, human-correctable reasoning where semantic judgment is useful.
Grasshopper owns deterministic computation and visible dataflow. Swiftlet can
publish selected entry points as MCP tools. External services can participate
without becoming the center of the architecture.

The product thesis is:

> Turn natural-language intent into visible, editable, testable, and
> publishable AEC capabilities. The agent authors the tool; the human can see
> and correct it; other agents can use it.

RookForge is not merely a fal.ai image generator, a Swiftlet demo, a Chirp
cascade, or another Rhino MCP server. Those are possible facets within a
broader capability-authoring environment.

## Why The Opportunity Changed

Swiftlet was conceived when building an MCP tool inside Grasshopper was itself
novel. Its visual publication mechanism remains useful, but the likely author
has changed. A typical user is increasingly unlikely to wire a complete MCP
request/response graph by hand. The user will ask an agent to create the tool.
Rook or another Rhino-capable agent can author the Grasshopper definition, and
Swiftlet can serve the resulting capability.

At the same time, the existence of many Rhino and Grasshopper MCP servers means
that tool exposure alone is no longer a sufficient differentiator. Rook's
stronger opportunity is its combination of:

- authoritative Rhino and Grasshopper mutation;
- discovery, metadata, receipts, solve readiness, and fenced observation;
- empirical experience with local and frontier models;
- script and native Grasshopper authoring lanes;
- Chirp's typed, visible, corrigible reasoning dataflow; and
- the ability to author, inspect, repair, and qualify the artifact that becomes
  the new tool.

The relevant shift is therefore:

```text
old proposition
human wires a Grasshopper definition that exposes an MCP tool

new proposition
human expresses intent
-> agent forges a visible Grasshopper capability
-> selected entry points are published as tools
-> human and other agents inspect, invoke, and revise it
```

## Empirical Foundation

RookForge should build on the retained experiments rather than reset them.

### Model-led Grasshopper work is real but imperfect

The Qwen3.8 campaigns demonstrated meaningful native and Python Grasshopper
authoring, discovery, mutation, local repair, control testing, viewport
inspection, and evidence-grounded completion. They also exposed repeated
discovery, context replay, strategy churn, and weak stopping behavior. Better
skills and more truthful Rook observations improved performance, but no prompt
turned an imperfect model into a perfect designer.

The GPT-5.6 Sol Vessel work further showed that a stronger model can infer and
implement a substantially better geometric hypothesis, while still initially
validating the wrong spatial topology. Human visual criticism exposed the
error. The model converted that criticism into angular-locality and symmetry
tests, deterministic code measured the live graph, and the model replaced the
flawed premise. The retained postmortem is:

[`2026-08-20-gpt56-sol-codex-vessel-postmortem-record.md`](../reports/2026-08-20-gpt56-sol-codex-vessel-postmortem-record.md)

The architectural lesson is not that deterministic machinery should decide
open-ended design quality. It is:

> Intelligence proposes and interprets. Deterministic mechanisms establish
> closed facts. Human judgment supplies corrections that neither layer should
> pretend to own automatically.

### Harness affordances matter

Prime and Codex runs showed that models benefit from persistent context,
stateful computation, planning, verification, image access, web research, and
clear tool contracts. RookForge should be callable from different harnesses;
it should not assume one model or one agent runtime is uniquely authoritative.

### The artifact matters more than the chat

The durable result is the authored capability on the Grasshopper canvas, its
manifest, tests, evidence, and published interface. The authoring conversation
is useful provenance, but the product must not require preserving private model
reasoning or replaying one particular chat.

## Governing Principles

1. **Agents forge tools, not only geometry.** A successful authoring session may
   produce a reusable capability that other agents invoke later.
2. **The canvas remains the inspectable implementation.** Agent authorship must
   not turn Grasshopper into an invisible backend.
3. **Use intelligence for open choices and deterministic mechanisms for closed
   contracts.** Tool schemas, request custody, connection topology, receipts,
   solve state, units, and measurable requirements remain mechanical.
4. **Human correction is part of the architecture.** It is not an exceptional
   escape hatch. Chirp's per-node Correction input is an important precedent.
5. **Templates compress plumbing, not design diversity.** The template owns
   repetitive and failure-prone integration mechanics. The agent still chooses
   the capability, composition, domain semantics, and meaningful parameters.
6. **Publication and authorship are separate.** Rook can author and qualify a
   definition. Swiftlet can publish it. The published runtime need not retain
   Rook in its invocation path unless the capability actually needs Rook.
7. **Do not universalize from one use case.** Geometry, analysis, data,
   simulation, media, documentation, and reasoning are sibling capability
   families.
8. **Prefer explicit bounded iteration to autonomous recursive loops.** A human
   or exterior agent should decide when a critique justifies another expensive
   generation or solve.

## System Roles

```text
                         External agents
                               |
                    Swiftlet publication plane
                  tools, resources, and responses
                               |
       +-----------------------+-----------------------+
       |                       |                       |
 Chirp reasoning       GH computation          External services
 planning, critique,   geometry, simulation,   GIS, climate, energy,
 interpretation,       transformation, data    cost, BIM, fal.ai, APIs
 gates, correction
       +-----------------------+-----------------------+
                               |
                    Rook authoring/evidence plane
             create, connect, inspect, repair, verify
                               |
                       Human-visible canvas
```

### Rook

Rook owns authoritative interaction with Rhino and Grasshopper: discovery,
identity, admitted mutation, receipts, solve readiness, snapshots, diagnostics,
and viewport evidence. In RookForge it also acts as the authoring mechanism
that lowers a capability specification into a concrete canvas graph.

Rook should not acquire semantic authority merely because one design quality
can be measured in one example.

### Chirp

Chirp owns visible semantic components with typed pins, domain signatures,
reasoning propagation, and per-node human Correction. Its current categories
are planner, interpreter, critic, narrator, classifier, gate, and editor.

Chirp is appropriate where a capability must interpret a brief, reconcile
competing considerations, classify evidence, criticize an option, or explain a
result. It is not required in every RookForge tool.

### Grasshopper

Grasshopper is the visible deterministic substrate. It owns geometry,
transformation, simulation wiring, dataflow, metrics, and the authored
implementation that a designer can inspect or modify.

### Swiftlet

Swiftlet is a publication runtime. It turns selected Grasshopper entry points
into MCP tools and returns text, structured JSON, images, resources, and errors.
RookForge does not require Swiftlet for every capability, but Swiftlet is a
natural way to make a forged capability available to other agents.

### External services

External systems are adapters, not the architecture's center. Examples include
weather and GIS data, energy or structural analysis, cost databases, BIM
systems, search, model inference, fal.ai, and firm-specific APIs.

### Human designer

The designer sees the graph, changes parameters, supplies corrections, rejects
plausible-but-wrong results, and decides whether an open-ended design outcome is
adequate. RookForge should make this participation legible rather than treating
it as contamination of an autonomous process.

## Two Distinct Planes

Separating authoring from invocation prevents the product from becoming an
unbounded workflow engine.

### Authoring plane

```text
user intent
-> agent interprets requested capability
-> compact CapabilitySpec
-> pattern selection and composition
-> deterministic lowering through Rook
-> canvas inspection and repair
-> contract and behavior checks
-> optional publication through Swiftlet
```

The authoring plane may use a frontier model, Prime/Qwen, Codex, Claude, or
another capable harness. It is allowed to ask questions and iteratively repair
the artifact.

### Invocation plane

```text
client calls published tool
-> Swiftlet admits and emits the request
-> deterministic GH and optional Chirp/service facets execute
-> result is observed and assembled
-> Swiftlet responds once
```

The invocation plane should be understandable without replaying the authoring
conversation. It may be much smaller than the authoring environment.

## CapabilitySpec

An agent should author a compact declarative description of the capability,
not thousands of tokens of low-level component placement and HTTP plumbing.
The exact schema is not yet frozen, but the conceptual content is:

```yaml
capability: early_design_option
description: Generate and assess an early massing option

inputs:
  - brief
  - site_boundary
  - program_targets

facets:
  - pattern: chirp_planner
    role: interpret_program

  - pattern: external_service
    service: climate_data

  - pattern: grasshopper_computation
    function: generate_and_measure_massing

  - pattern: chirp_critic
    criteria:
      - program_fit
      - daylight
      - public_realm

  - pattern: artifact_presentation
    outputs:
      - viewport_image
      - metrics
      - narrative

publish:
  tools:
    - generate_option
    - evaluate_option
    - explain_option
```

The specification describes intent and composition. It does not duplicate the
entire Grasshopper document.

## Composable Pattern Vocabulary

The recommended middle path is a small library of reusable boundary patterns.
Avoid both a template per task and a universal visual-programming compiler.

### MCP tool shell

Owns tool definition, input schema, request deconstruction, exactly-one-response
behavior, structured success, structured error, and publication wiring.

### External-service job

Owns credential references, request construction, submission, waiting or
polling, timeout, error conversion, and result extraction. One pattern should
support multiple services through configuration; it should not become a
separate template for every endpoint.

### Grasshopper computation

Owns typed parameters, native components or scripts, deterministic outputs,
diagnostics, and measured postconditions.

### Data and resource adapter

Owns files, tables, images, resource links, embedded resources, and conversions
between service results and Grasshopper or MCP representations.

### Chirp reasoning chain

Owns a small semantic topology and typed reasoning roles. It can be a fan-out,
chain, or planner/interpreters/critic hybrid. It should not become a dynamic
multi-agent scheduler hidden inside Grasshopper.

### Artifact presentation

Owns viewport captures, canvas images, reports, tables, files, and links. Media
is one presentation family, not the definition of RookForge.

### Human correction and approval

Owns visible panels or controls that alter a specific semantic or computational
decision. Corrections should have explicit scope rather than silently changing
the whole capability.

### Observation and verification

Owns diagnostics, solve readiness, receipts, fenced observations, measurable
requirements, and the evidence returned to the caller. Open-ended design
quality remains attributed judgment.

## Template Granularity

The LLM should decide:

- what capability is needed;
- which patterns compose it;
- meaningful tool names and descriptions;
- domain inputs and outputs;
- which facts require computation or external evidence;
- which decisions require Chirp or human correction; and
- how the result should be presented.

The template should decide:

- request and response plumbing;
- authentication references;
- serialization and error handling;
- component identities and known wiring;
- timeout behavior;
- deterministic graph layout conventions;
- response cardinality; and
- mechanical postconditions.

This division applies the evidence-led rule already established in Rook:

> Do not spend model intelligence repeatedly rediscovering a closed contract.
> Do not give a closed contract authority over open-ended design judgment.

## Chirp's Actual Reasoning Contribution

A complete reasoning facet might be visible as:

```text
Brief
-> Planner: program and design parameters
-> parallel Interpreters: structure, environment, circulation
-> deterministic GH measurements and external evidence
-> Critic: contradictions and unresolved requirements
-> human Correction
-> Editor: reconciled decision
-> Gate: proceed, revise, or request human judgment
-> Narrator: attributable explanation of the result
```

The current `Reasoning` pin is a shared semantic context bus. Product-facing
contracts should prefer concise rationale, decisions, assumptions, evidence,
and uncertainty over any claim to preserve or expose a model's private chain of
thought. Typed outputs remain the downstream computational contract.

Chirp should be optional. A deterministic geometry transformer does not need a
planner merely to make the diagram look intelligent.

## Full Roundtrip

The complete RookForge roundtrip is:

```text
1. A user asks an authoring agent for a new AEC capability.
2. The agent proposes a CapabilitySpec and asks consequential questions.
3. Rook lowers selected patterns into a visible Grasshopper graph.
4. The agent inspects, tests, and repairs the graph using authentic evidence.
5. The human can inspect and correct semantic or computational decisions.
6. Swiftlet publishes selected entry points as MCP tools.
7. An exterior agent discovers and invokes the new tools.
8. Grasshopper, Chirp, and external-service facets produce a result.
9. The caller receives structured facts, artifacts, evidence, and uncertainty.
10. A human or exterior agent may request a bounded revision.
```

The important demonstration is not that one LLM called another. It is that an
agent created a new, inspectable domain capability that remained editable by a
designer and immediately usable by other agents.

## Capability Families

RookForge should be broad enough to support several families without pretending
to implement all of them in the first slice.

### Geometric

- parametric generators;
- existing-definition modifiers;
- circulation, facade, landscape, and fabrication tools;
- model cleanup and standards application; and
- reusable computational subgraphs.

### Analytical

- daylight and environmental assessment;
- structural or geometric checks;
- accessibility and circulation metrics;
- quantities, cost, and carbon;
- option comparison; and
- deterministic acceptance of explicitly measurable requirements.

### Data and interoperability

- GIS and weather acquisition;
- BIM exchange;
- project databases;
- firm standards and knowledge;
- structured model extraction; and
- transformation between AEC systems.

### Interpretive

- brief translation;
- multi-discipline reasoning;
- conflict identification;
- option critique;
- human-correctable design policy; and
- attributable explanation.

### Artifact and media

- reports, tables, and design narratives;
- viewport captures and diagrams;
- image generation or editing;
- video generation returned as a resource; and
- presentation packages.

Media illustrates the breadth but must not dominate the architecture.

## fal.ai As One Example, Not The Center

A user might ask:

> Publish a tool that sends the current Rhino viewport and a design prompt to
> fal.ai, displays the result on the Grasshopper canvas, and returns it to the
> caller.

RookForge could select an MCP shell, external-service job, image resource, and
artifact-presentation pattern. A Chirp interpreter could optionally translate
architectural intent into a controlled generation prompt, and a vision-capable
critic could evaluate the actual returned image before a bounded revision.

The same external-service pattern should also serve non-media APIs. fal.ai is a
good visible specimen, not a special architectural owner.

## Image And Video Findings

BitmapPlus was inspected at:

```text
Repository: https://github.com/interopxyz/BitmapPlus.git
Commit:     4f69916c937db2644a00b197f147f1f7fe68c045
```

Its `Preview Image` component provides a real static bitmap display directly on
the Grasshopper canvas through custom component attributes. Its loader accepts
common bitmap formats, including GIF, but the repository contains no video
decoder, frame lifecycle, playback clock, canvas refresh loop, scrub control,
or MP4/WebM support. It targets .NET Framework 4.5 and Rhino 6-era references;
Rhino 8 compatibility is not established by this inspection.

For an early RookForge media facet:

- use a static canvas preview for images;
- return video as an MCP resource link or file artifact;
- display a poster frame or contact sheet on the canvas; and
- treat native video playback as a separate optional feature.

Current Chirp was also inspected at commit
`1f954c27f796ecfe830d02a76497deffcf31cfc2`. Its type map has no bitmap,
image-reference, or multimodal input. A future image critic must receive the
actual image through a narrow reference contract such as path or URL, MIME
type, dimensions, and content hash. Passing only the generation prompt would
produce an imagined critique rather than observation of the result. This is a
potential Chirp extension, not a prerequisite for the entire RookForge idea.

## Current External Reference State

The following states were inspected while developing this concept:

```text
Rook continuity worktree
  branch: codex/coordinating-intelligence-evidence-ledger
  parent at concept creation: 943584b51ca60dd460d79f8234e369c501129c44

Chirp
  repository: git@github.com:bringfire/Chirp.git
  commit: 1f954c27f796ecfe830d02a76497deffcf31cfc2

Swiftlet
  repository: git@github.com:enmerk4r/Swiftlet.git
  commit: 3e4255ff43b55babd690c3bce5f209d98ced7ad3

BitmapPlus
  repository: https://github.com/interopxyz/BitmapPlus.git
  commit: 4f69916c937db2644a00b197f147f1f7fe68c045

Prime experimental baseline
  repository: git@github.com:PrimeIntellect-ai/prime-agent.git
  commit: 739400844f8f3f280414b0c7b9c65797208815d3
```

At the inspected Swiftlet commit, `Define Tool` describes name, description,
and input parameters. The current response component can return typed MCP
content blocks, structured JSON, and an error disposition. Swiftlet's fixed
request wait and its exact schema surface must be evaluated against each forged
capability rather than assumed adequate for long-running external jobs.

## Recommended Hackathon Shape

The hackathon should demonstrate breadth through one coherent scenario, not
attempt to implement every capability family.

### Central artifact

A small **RookForge authoring flow** that accepts a CapabilitySpec and composes
tested patterns onto the Grasshopper canvas through Rook.

### Proof of generality

Create or publish at least three contrasting entry points from the same pattern
system:

1. a geometric capability;
2. an analytical or external-data capability; and
3. an interpretive Chirp capability.

An image, diagram, or report may present their combined result. The three
capabilities do not need three separate application stories.

### Minimum convincing demonstration

```text
natural-language request
-> agent produces a compact capability description
-> Rook authors the visible graph
-> mechanical validation passes
-> Swiftlet advertises the tool
-> a different agent invokes it
-> Grasshopper returns an authentic result
-> a visible human Correction changes one decision
-> the caller receives the revised result and explanation
```

### Suggested time discipline

- Establish one end-to-end vertical early.
- Extract patterns from existing working Swiftlet examples rather than rewrite
  every component.
- Add a second and third capability type only after the first can be authored,
  published, and invoked.
- Preserve a manual fallback definition for the presentation.
- Spend the final hours on legibility and story, not a universal compiler.

## Approaches Considered

### Freeform agent wiring

An agent directly discovers and places every Swiftlet, API, Chirp, and response
component. This is useful as a feasibility baseline but repeatedly spends model
effort on closed plumbing and is fragile under component ambiguity.

### Template zoo

One frozen template is created for every service and use case. This is fast for
the first examples but scales poorly and obscures the reusable boundaries.

### Universal graph DSL or workflow engine

A new language describes arbitrary Grasshopper and agent workflows. This may
sound general, but it recreates Grasshopper, PlanGraph, and orchestration
machinery before the product question has been tested.

### Recommended: composable boundary patterns

A small pattern vocabulary handles repeated integration contracts. The agent
composes patterns into domain capabilities, and Rook lowers the composition
into the existing canvas and evidence machinery. This is the intended
RookForge direction.

## Explicit Non-Goals

RookForge does not initially require:

- a universal visual-programming compiler;
- an autonomous multi-agent swarm inside Grasshopper;
- a new supervisor or terminalization protocol;
- a deterministic vocabulary for all design quality;
- a template for every service or component family;
- automatic recursive generation and critique;
- native video playback on the Grasshopper canvas;
- a security sandbox for arbitrary Python or C#;
- replacement of Rook, Chirp, Grasshopper, or Swiftlet; or
- proof that any model can author every useful AEC capability.

## Open Decisions

These questions remain intentionally open for the hackathon design pass:

1. Is the first authoring interface a versioned skill, a small manifest
   compiler, or a narrowly extended Rook tool?
2. What is the smallest CapabilitySpec that can express three contrasting
   capability types without becoming a graph language?
3. Which existing Swiftlet definitions are suitable golden sources for the MCP
   shell and external-service patterns?
4. How should secret references be represented so credentials never enter the
   canvas, prompt, commit, or evidence archive?
5. Which postconditions prove that a forged tool is genuinely published and
   callable?
6. How are pattern versions and generated capability revisions represented?
7. Which Chirp outputs should be concise decision records rather than general
   reasoning prose?
8. Does the first composite scenario require multimodal Chirp input, or can
   that remain an optional follow-on?

## Success Criteria For The First Slice

The first slice is successful if:

- a user can request a new capability in ordinary language;
- an agent produces a compact, reviewable capability description;
- Rook creates a visible Grasshopper implementation from more than one reusable
  pattern;
- the resulting graph solves without hidden manual repair;
- at least one entry point is published and invoked by an exterior MCP client;
- the response contains truthful structured results or artifacts;
- a visible human correction can change a scoped decision;
- the revised behavior remains attributable to the edited graph; and
- the demonstration does not depend on claiming universal semantic correctness.

## Immediate Continuation On The Hackathon Machine

1. Pull the Rook branch containing this document.
2. Confirm the exact installed and source states of Rook, Chirp, Swiftlet, and
   Grasshopper before deployment or live authoring.
3. Run one short design session to select the composite AEC scenario and its
   three capability types.
4. Inspect the existing Swiftlet image-generation, image-editing, viewport, and
   MCP examples as pattern evidence, not as mandatory product scope.
5. Freeze the first three pattern contracts and their mechanical
   postconditions.
6. Build the smallest end-to-end author-publish-invoke vertical before adding
   breadth.
7. Preserve screenshots, the generated canvas, the capability description,
   and one exterior invocation as the core demonstration evidence.

## Closing Position

RookForge is a synthesis of the project's strongest surviving ideas:

- agent intelligence working empirically against the real design environment;
- deterministic custody of identity, mutation, solve, and observation;
- visible Grasshopper computation rather than opaque generated code alone;
- Chirp's typed and human-correctable semantic dataflow;
- Swiftlet's ability to publish Grasshopper behavior to other agents; and
- reusable templates that compress integration plumbing without constraining
  architectural breadth.

The concise product statement is:

> **RookForge enables agents to create the AEC tools they need, visibly in
> Grasshopper, from reusable computational and reasoning patterns—and makes
> those tools immediately available to people and other agents.**
