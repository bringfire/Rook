# Exotic Capability Promotion Design: From Script Prototype to First-Class Typed Route

**Date:** 2026-04-22
**Author:** bringfire + Codex + Claude
**Status:** Design draft, intended to guide implementation planning
**Related:** `2026-04-15-typed-route-gap-analysis.md`, `2026-04-10-public-skills-brainstorm.md`, `Rook/CLAUDE.md`, `Rook/docs/CURRENT_ARCHITECTURE.md`

---

## Executive Summary

This document defines how Rook should handle the next class of high-value,
"exotic" capabilities: operations that often begin life as a Rhino Python
script, embody real domain knowledge, and are newly feasible as productized
features because agents can supply precise parameters and semantic adaptation at
runtime.

The key conclusion is the same one reached in the typed-route gap analysis, but
applied to a new source of ideas:

- **scripts are valid prototypes**
- **scripts are not the shipped execution substrate**
- **reusable operation primitives graduate into typed routes**
- **skills orchestrate typed routes for workflow-shaped tasks**

This is not a proposal to ship a script library as a parallel runtime next to
typed routes. That would recreate the same command-era problem in a new form:
opaque execution, weak discovery, poor validation, drift across consumers, and
runtime fragility.

Instead, Rook should treat user-authored or agent-authored scripts as:

1. **reference artifacts** that expose useful algorithms and option surfaces
2. **design inputs** for new typed contracts
3. **test material** for validating typed promotions

The shipped product remains the typed route, surfaced through HTTP first, then
MCP, then intent routing, then skills.

---

## Why This Document Exists

The typed-route gap analysis focused on common Rhino operations still trapped in
command-oriented execution. That document corrected the original "simulate a
human at the command line" theory of capability.

This document addresses the next question:

> What should Rook do with useful, nontrivial scripts that encode operations
> Rhino does not expose as a clean first-class machine contract today?

Examples include:

- distribute blocks along a curve with spacing, randomization, and orientation
- populate objects along terrain or site features with controlled variation
- parameterized layout and placement tools that are too specific to be native
  Rhino commands but too useful to remain one-off scripts

These capabilities matter because the current agent moment changes the backlog.
Agents can now:

- extract the latent operation from a script
- infer a bounded option model from messy user intent
- gather context from the open document
- choose parameters or presets intelligently
- chain the capability into a larger workflow

But none of that changes the need for a stable machine contract.

The runtime lesson remains the same: **semantic reasoning may happen in the
agent, but execution still needs typed contracts**.

---

## The Theory Shift for "Exotic" Capabilities

### Old temptation: "Agents can read scripts, so ship scripts"

This is the wrong conclusion.

A script file can be:

- rich in algorithmic knowledge
- easy for a human to iterate on
- expressive in ways that outpace a static UI

But as a product substrate it is weak:

- discovery is prompt-fragile
- schemas are implicit
- validation is late
- outputs are inconsistent
- testability is poor
- drift is easy
- multiple consumer classes see it differently

### Correct framing: "Agents make more typed capabilities worth building"

The right conclusion is stronger and more specific:

- agents increase the number of operations that are worth promoting
- agents help compile fuzzy user intent into exact typed arguments
- agents help choose presets, thresholds, and mode flags at runtime
- typed routes still carry the load-bearing execution contract

In other words: **agents are semantic compilers and workflow orchestrators, not
an excuse to ship production logic as free-form scripts**.

---

## Hard Constraints from the Live Rook Architecture

These are not preferences. They are architectural constraints already present in
the repo.

### 1. Interactive `rhinoscriptsyntax.Get*` prompts are not an agent runtime

`rhino_execute` explicitly rejects blocking `rhinoscriptsyntax.Get*` calls in
`mcp_server/src/rook/server.py` (`_find_blocking_rhinoscriptsyntax_call`,
around line 10883). A script that depends on `GetObject`, `GetObjects`,
`GetString`, `GetInteger`, or `GetReal` is therefore not merely "suboptimal" for
agents; it is refused before dispatch.

This means an interactive Rhino script cannot be the runtime shape of a Rook
capability.

### 2. Typed routes are already the preferred substrate

`CLAUDE.md` states the policy directly: prefer typed routes over scripts.
Scripts and commands remain fallback tools, not the primary product surface.

This document extends that policy to script-originated features. The origin of
the idea does not change the target substrate.

### 3. Rook has three real consumer classes

The capability must be robust for all three:

1. **Rook-internal agents** — call native HTTP routes directly; they do not use
   MCP
2. **MCP clients** — discover tool schemas through MCP
3. **In-repo LLMs** — read prose, skill files, AGENTS/CLAUDE instructions, and
   nearby source code directly

Any design that only works for one of these three is incomplete.

### 4. Duplicate logic is maintenance debt, not product

Once a typed route exists, the original standalone script should not remain a
shipped parallel implementation of the same algorithm. That creates drift.

If a keyboard-driven Rhino UX remains valuable after promotion, it should be a
thin command wrapper that gathers prompts and calls the same typed handler or
shared implementation path. The algorithm must have one load-bearing home.

---

## Decision Framework

This is the primary rule set for deciding what a script-like capability should
become.

### Rule 1: Reusable operation primitive -> typed route

If the capability is:

- reusable across projects
- parameterizable with a bounded schema
- meaningful as a standalone machine operation
- testable as input -> document mutation/query -> structured output

then it should be a typed route.

Examples:

- distribute blocks along a curve
- populate along path with deterministic options
- orient instances to frames along a curve
- terrain-aware instance placement with explicit constraints

### Rule 2: Multi-step guided workflow -> skill over typed routes

If the value comes from sequencing, auditing, interviewing, approval, or
combining several operations, it should be a skill.

Examples:

- "clean this imported file using my conventions"
- "capture site furniture from these references and distribute it along the road"
- "lay out trees, lights, and benches based on path hierarchy"

The skill may use one or more exotic typed primitives, but it is not itself the
primitive.

### Rule 3: Niche, exploratory, or weakly parameterized logic -> reference script only

If the operation is still too exploratory, too user-specific, or too hard to
bound cleanly, it can remain a script prototype or research artifact.

But agents should not depend on it as a production runtime path.

### Rule 4: Parameterization beats adaptation

If the capability can be expressed as:

- stable executable body
- structured parameter block
- explicit modes / enums / thresholds / seeds

then that is the correct shape.

Free-form script rewriting is a sign that the contract is underspecified.

### Rule 5: Runtime prompts are not contract surface

All user choices gathered interactively in the original script must become typed
inputs, defaults, or skill-level interview questions before promotion.

### Rule 6: Postconditions matter as much as inputs

Each promoted capability must return structured outputs rich enough for agent
chaining:

- created IDs
- counts
- route mode actually used
- defaulted parameters actually used
- warnings
- any sampled points / frames / transforms worth reusing downstream

### Rule 7: Batch semantics must be explicit

Each high-fanout or multi-create route declares whether it is:

- atomic with explicit rollback on failure
- best-effort with per-item errors
- partial-success with structured failure reporting

Do not leave this implicit.

### Rule 8: Discovery is a product surface

The route, MCP tool, intent entries, skill references, and repo-facing docs
must agree. If discovery only works because a specific prompt remembered a file
path, the capability is not really shipped.

### Rule 9: One algorithm, one load-bearing implementation

After promotion, the typed route or shared helper becomes the single source of
truth. Historical scripts may remain in `rook_docs/` as frozen reference
artifacts, but not as duplicated shipped logic.

---

## Promotion Pipeline

Every script-originated capability should pass through the same lifecycle.

### Stage 0: Intake

Capture:

- source script path
- author / provenance
- what real problem it solves
- why users keep reaching for it
- whether it is query, creation, mutation, or workflow

### Stage 1: Algorithm extraction

Separate the script into:

- **interactive shell** — object picking, option prompts, ad hoc print output
- **load-bearing algorithm** — geometry math, distribution logic, orientation
  logic, transform composition, selection rules

Only the second part is a candidate for promotion.

### Stage 2: Classification

Choose one:

- typed primitive
- skill
- keep as reference script

The default for reusable geometry operations is typed primitive.

### Stage 3: Contract design

Before code, write the contract:

- route namespace and name
- input schema
- defaulting rules
- error taxonomy
- undo / rollback behavior
- response payload
- intent vocabulary

### Stage 4: Substrate decision

Default order:

1. native direct-sdk route, if coverage exists and is stable
2. managed companion route, if RhinoCommon-only APIs or existing ownership make
   that the right boundary
3. script/command fallback only as a temporary spike or migration bridge, never
   the target design

### Stage 5: Implementation

Promotion is not complete until all of these exist:

1. HTTP route
2. handler implementation
3. MCP tool schema
4. intent-runtime / router registration where appropriate
5. test coverage
6. documentation / skill references

### Stage 6: Historical cleanup

After the typed route ships:

- archive the original script in `rook_docs/` if useful as a historical spec
- or delete it if it no longer adds value
- do not keep a second shipped implementation in `RhinoScripts/` that can drift

---

## Contract Standards for Exotic Typed Capabilities

These capabilities are often more complex than basic primitives, so the
contract standards matter more, not less.

### Inputs

- MCP wire format uses **camelCase**
- IDs are explicit (`curveId`, `ids`, `instanceIds`, `blockNames`)
- mode flags use closed enums where possible
- optional randomness is seedable (`seed`)
- defaults are documented and echoed back in the response
- document-derived defaults (tolerance, CPlane, world Z, current layer) are
  explicit in both handler comments and success payloads

### Outputs

Minimum for mutation routes:

- `createdCount`
- `createdIds` or `instanceIds`
- `mode`
- `parametersUsed`
- `warnings`

For placement/distribution routes, strongly prefer also returning:

- sampled positions
- frame/orientation summary
- random seed actually used

### Error taxonomy

Use a small closed set plus route-specific detail, for example:

- `invalid_input`
- `not_found`
- `invalid_geometry`
- `operation_failed`
- `rollback_failed`

Do not leak vague string-only failure as the primary contract.

### Preview and dry-run

High-fanout placement tools should support preview or dry-run semantics when the
operation could create many instances or where the user may want to inspect the
distribution before commit.

This can be deferred for first PRs, but the route contract should be designed so
preview can be added cleanly later.

### Randomness

If the capability exposes randomness, it must support deterministic replay:

- user-supplied `seed` optional
- generated seed echoed back when omitted

Without this, debugging, testing, and user trust all degrade.

---

## Discovery Surfaces

Because Rook has three consumer classes, discovery must be deliberate.

### Source of truth

For promoted capabilities, the typed route contract is the source of truth.

If Rook later wants a "prototype catalog," it should catalog **promotion
candidates** and their status, not become a second execution substrate.

Suggested future metadata for candidate tracking:

- `candidateId`
- `status`: prototype | designing | promoted | rejected
- `sourceScript`
- `proposedRoute`
- `classification`: primitive | skill | reference
- `owner`
- `openQuestions`

### Derived discovery surfaces

From the promoted route, propagate to:

1. native route registration
2. MCP tool schema
3. intent runtime / capability router / sparse-index entries where useful
4. AGENTS / CLAUDE / skill references for in-repo agents

The important rule is: **metadata derives from the typed route design, not from
an informal script path**.

---

## Worked Example: `DistributeBlocksAlongCurve.py`

Source artifact:
`%USERPROFILE%\Documents\RhinoScripts\DistributeBlocksAlongCurve.py`

### What the script gets right

The script exposes a real operation family, not just a one-off hack:

- choose one or more source block definitions
- sample positions along a curve using multiple distribution methods
- orient instances to the curve while keeping them upright
- apply controlled random scale and rotation
- create new instances at the sampled transforms

This is exactly the kind of thing users repeatedly need, and exactly the kind
of capability that agents can invoke well once the contract exists.

### Why it cannot remain a runtime script

As written, it uses interactive `Get*` prompts for:

- selecting source instances
- selecting the curve
- choosing distribution mode
- entering counts, spacing, scale, and rotation options

That shape is blocked by `rhino_execute` preflight and is therefore not a viable
agent runtime substrate.

### Correct classification

This is a **reusable operation primitive**, so it should become a typed route.

It is not primarily a skill because the value is not sequencing or interview
logic; the value is the placement algorithm itself.

### Recommended first route

**First PR recommendation:** keep it block-scoped and explicit.

Proposed route family:

- `POST /block/distribute-along-curve`
- MCP tool: `rhino_block_distribute_along_curve`
- handler home: `BlocksHandler` or a new `BlockPlacementHandler` if the family
  grows

Block-scoped is the right first cut because:

- the prototype is block-specific
- the created output is block instances, not arbitrary transformed copies
- the schema is clearer
- random prototype selection is naturally a block concern
- it avoids prematurely over-generalizing into a generic array contract

If later demand justifies a generic object-placement primitive, that can be a
separate route rather than forcing this first contract to carry both concerns.

### Suggested input contract

```json
{
  "curveId": "guid",
  "blockNames": ["Tree_A", "Tree_B"],
  "distributionMethod": "fillCurve",
  "count": 24,
  "distributionType": "even",
  "spacing": 3.0,
  "spacingVariation": 0.4,
  "placement": "center",
  "orientation": "followCurve",
  "keepUpright": true,
  "rotationMode": "random",
  "scaleMode": "randomRange",
  "minScale": 0.8,
  "maxScale": 1.2,
  "seed": 42
}
```

Not every field is required for every mode. The route should validate by mode.

### Suggested output contract

```json
{
  "createdCount": 24,
  "instanceIds": ["..."],
  "mode": "fillCurve",
  "parametersUsed": {
    "distributionType": "even",
    "orientation": "followCurve",
    "keepUpright": true,
    "seed": 42
  },
  "sampledPositions": [[0,0,0], [3.1,0,0], "..."],
  "warnings": []
}
```

### Behavior standards for the route

- one UndoScope per request
- explicit rollback behavior on failure
- deterministic randomness through `seed`
- explicit handling of tangent/frame failures
- orientation semantics documented clearly
- source block selection explicit (`blockNames` or later `sourceInstanceIds`)

### Generalization path

Do not force genericity into the first PR.

Possible later siblings:

- `/array/along-curve` for deterministic copy-array of arbitrary object IDs
- `/block/distribute-on-surface`
- `/block/distribute-in-region`

The first route should prove the pattern, not solve the whole design space.

---

## What Survives from the "Script Library" Idea

Some of the original script-library framing remains valuable, but in a narrower
role.

### Keep

- scripts as reference artifacts for algorithm discovery
- metadata for promotion candidates
- harvested option models from real scripts
- test material drawn from scripts that users already rely on

### Reject

- shipped script folder as a parallel runtime substrate
- "agents know about the scripts somehow" as a discovery strategy
- free-form adaptation of mutating scripts at runtime as a primary mechanism
- duplicate manual utilities that drift from promoted typed routes

### Refined interpretation

The right durable artifact is not a "script library." It is a **promotion
pipeline** plus, optionally, a **prototype catalog** that tracks which scripts
have been promoted, rejected, or are under design.

---

## Implementation Pattern for Promoted Exotic Capabilities

Each promoted capability should ship with the same artifact set.

### 1. Design record

One short design section or mini-doc covering:

- classification
- namespace
- schema
- substrate
- batch / atomicity semantics
- routing vocabulary

### 2. Native or managed handler

The implementation lives where the architecture says it should live, not where
the original script happened to be written.

### 3. MCP tool

Needed for external MCP clients and for schema discoverability.

### 4. Intent integration

Register the capability with:

- intent runtime / capability router if it belongs on the fast path
- sparse index or adjacent intent metadata where semantic routing benefits

### 5. Tests

At minimum:

- contract parse/validation tests
- execution-path tests
- live integration test when Rhino-side verification is required

### 6. Documentation

Update the relevant skill docs, AGENTS/CLAUDE guidance if the capability is
important enough to affect agent behavior, and any backlog / design inventory
docs.

---

## Initial Roadmap

### Phase A: Establish the pattern

1. Ratify this promotion model
2. Create a small candidate inventory for script-originated capabilities
3. Choose one exemplar capability

### Phase B: First exemplar

Use `DistributeBlocksAlongCurve.py` as the first full worked promotion:

1. extract algorithm + options
2. decide exact route home and contract
3. implement typed route
4. add MCP tool
5. add intent vocabulary
6. add tests
7. archive original script as reference artifact or remove it

### Phase C: Build a small family, not a zoo

After the first exemplar, promote only a few neighboring operations that share
patterns:

- along-curve distribution
- deterministic placement with seedable variation
- typed placement/orientation around frames

Do not accept a flood of unrelated script promotions before the pattern is
proven.

---

## Open Questions

These are real design questions, but they do not weaken the core conclusion.

1. Should the first along-curve distribution route live in `BlocksHandler` or a
   dedicated placement/distribution handler?
2. What preview standard should high-fanout placement routes share?
3. How much sampled-position detail should success payloads return by default?
4. Should promotion candidates get a lightweight catalog file in `rook_docs/`,
   and if so what is the minimum useful schema?
5. Which exotic capabilities are truly primitive enough for direct promotion,
   versus better expressed as skills over existing typed routes?

---

## Net Decision

Rook should not ship a general script library as a second execution substrate.

Rook should:

- accept scripts as valuable prototype/spec inputs
- promote reusable script-shaped operations into first-class typed routes
- use skills for workflow orchestration around those routes
- preserve one load-bearing implementation per promoted capability

The agent moment does not reduce the need for typed contracts. It increases the
set of capabilities worth turning into typed contracts in the first place.
