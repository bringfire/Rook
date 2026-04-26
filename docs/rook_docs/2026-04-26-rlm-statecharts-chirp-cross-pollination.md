# RLM × Statecharts × Chirp — Cross-Pollination Expedition

**Date:** 2026-04-26
**Status:** Open-horizon exploration. Not a plan. Not scoped. Intentionally not reduced.
**Authors:** aryan + Claude (visionary voice) + Codex (analytical voice), via conversation
**Mode:** Seed document. Capture the surface area. Stay generative. Defer pruning.

**Related sources:**
- [RLM blog (Alex Zhang, 2025)](https://alexzhang13.github.io/blog/2025/rlm/)
- [RLM repo](https://github.com/alexzhang13/rlm)
- [statecharts.dev](https://statecharts.dev/) — esp. *what is a statechart*, *how to use statecharts*
- Harel 1987 — original statecharts paper
- Existing Rook docs: `2026-04-08-sa-banana-integration.md` (RookVision module pattern), `2026-04-15-typed-route-gap-analysis.md` (theory-of-capability shift), `2026-04-22-contextual-capability-understanding-design.md`

---

## 0. Why This Doc Exists

We hit a three-way resonance in conversation:

1. **Statecharts** (Harel) — making behavior explicit through nested states, orthogonal regions, guards, events, history.
2. **RLMs** (Recursive Language Models) — treating context as a programmable variable that the model peeks/greps/partitions/recursively-calls itself over.
3. **Chirp + Rook + Grasshopper** — LLM-embedded GH components, knowledge-graph substrate, typed-route catalog, persistent dataflow canvas.

None of these alone is the point. The combinations might be. This doc captures the surface area of those combinations — both the conservative reductions and the open-horizon claims — so we can come back to it without re-deriving from scratch.

**Posture:** Codex has already given a sharp, scope-reducing pass. Claude has given a dreamier, substrate-claiming pass. Both voices are preserved here on purpose. The doc's job is to *not collapse them prematurely*.

---

## 1. The Three Traditions, Stated Plainly

### 1.1 Statecharts — what they add over flat FSMs

| Concept | What it gives you |
|---|---|
| Hierarchy (nested states) | Factor concerns into layers; one transition can exit many substates cleanly |
| Orthogonal regions | Multiple state machines running in parallel inside one chart, communicating via events |
| Guards | Conditional transitions based on data |
| Entry/exit/transition actions | Side effects pinned to boundary crossings, not buried in code |
| History states | Re-enter a region where you left off |
| Events | Named triggers that propagate through the chart |

Big claim of statecharts: **behavior is best described by *what's true right now* (the active state configuration), not by tracing through code.** The chart is the spec.

### 1.2 RLMs — what they add over flat LM calls

| Concept | What it gives you |
|---|---|
| Context-as-variable | Prompt is a Python object the model operates on, not a token stream |
| REPL environment | Executable substrate where context lives between operations |
| Recursive self-call | Model spawns itself with a transformed slice of context |
| Strategy palette (emergent) | peek / grep / partition+map / summarize / long-output |
| `FINAL(answer)` / `FINAL_VAR(name)` | Explicit termination protocol |
| Trajectory logging | Every iteration and sub-call captured for replay/debug |
| Isolated environments | Docker / Modal / E2B for parallel sub-calls without shared-state concerns |

Big claim of RLMs: **don't stuff long context into a model — give the model an environment where it can *operate on* the context programmatically.**

### 1.3 Chirp + Rook + Grasshopper — what we already have

| Asset | What it gives |
|---|---|
| GH canvas | Persistent, typed, visual dataflow — wires are named variables, components are functions |
| Chirp components | LLM-embedded GH nodes with categories `{planner, interpreter, critic, narrator, classifier, gate, editor}` |
| ConductorEngine | Phase-driven Blueprint construction (FSM today, flat) |
| UnifiedStore + PatternStore | Semantic graph of components, recipes, patterns, with `links` |
| Typed-route catalog | ~300 MCP tools; `rhino_execute_intent` / `gh_execute_intent` route to them |
| Knowledge graph panel | v1.1 visual surface over UnifiedStore |
| Correction signal | `correction_detected` → `knowledge_record` learning loop |
| Trajectory log | Chirp JSONL traces (today, partial) |
| Concurrency constraint | All HTTP requests serialize through Rhino's UI thread |

---

## 2. Core Resonance

> **Statecharts say:** don't bury behavior in ad hoc conditionals; make modes, events, guards, actions, hierarchy, and parallelism explicit.
>
> **RLM says:** don't stuff all context into the model; give the model an environment where context is an inspectable object, and let it peek, grep, partition, map, summarize, and recursively ask submodels.
>
> **Chirp / Rook already has the missing substrate:** Grasshopper as persistent typed dataflow, Rook as canvas/scene/knowledge observer, Chirp nodes as typed LLM-backed components.

The asymmetry that makes this interesting: **Rook has substrate that RLM doesn't have, and a behavioral need statecharts solve.** We can pollinate inward.

---

## 3. The High-Energy Combinations

Both voices contributed. Where attribution sharpens the idea, it's noted. Where the synthesis is joint, it isn't.

### 3.1 The Grasshopper canvas IS the REPL

> **Claude's framing:** RLM ships with a Python REPL because it needs an executable substrate where context lives as named, inspectable, mutable values. Rook already has one and it's *visual*. Wires are named variables. Components are functions. `gh_snapshot` is `peek`. `gh_edit` is mutation. Clusters / sub-definitions are recursive scopes. Nobody else has this — RLM has a text REPL; we have a 2D one.
>
> **Codex's framing (more conservative):** Treat the GH canvas, Rook knowledge stores, scene graph, and traces as the RLM "context variable." A Chirp component would receive *query access* to context: `peek_canvas()`, `get_upstream(guid)`, `grep_components("surface")`, `summarize_subgraph(guid)`, `ask_subchirp(query, context_slice)`.

Both are real. The Codex version is the responsible read-only first move. The Claude version is the eventual claim that the canvas is also the *trajectory visualizer* — agent reasoning, GH editing, and trace inspection collapse into the same surface.

**Boundary it pushes:** RLM's trajectory viewer is a Node.js UI bolted on. For Rook, the workspace itself is the visualizer. That's a category difference, not a feature difference.

### 3.2 Recursive Chirp cascades

Today a Chirp cascade is fan-out: planner → critic → narrator. Long contexts get stuffed into each prompt. That's exactly the context-rot RLMs target.

Combination: a cascade *is* an RLM if the planner can `partition + map` over downstream Chirps with sliced context, and any branch can spawn a sub-cascade. Today's flat cascade → tomorrow's recursive tree where each subtree only sees its slice.

| Today | With RLM thinking |
|---|---|
| Planner sees full input, fans out to N children | Planner peeks, partitions, calls N sub-cascades each on their slice |
| Critic re-reads everything | Critic sees only the FINAL_VARs from sub-cascades |
| Narrator concatenates outputs | Narrator gets a tree, not a soup |

The `gate` category is *already* the termination predicate; we just don't name it that.

### 3.3 Statechart-orchestrated reasoning cascades (Codex)

Existing Chirp cascades already look like statecharts with parallel regions. A design-language fanout maps cleanly:

- parallel region: structure interpreter
- parallel region: envelope interpreter
- parallel region: environment interpreter
- join / synchronization: critic
- final state: narrator or resolved design parameters

This turns cascade topology from "a graph we draw" into "an executable behavioral spec for design reasoning."

### 3.4 RLM strategy palette as first-class Chirp execution modes (Codex, sharpened)

The RLM blog highlights emergent strategies: peeking, grepping, partition+map, summarization, long-output generation. These could become explicit Chirp execution modes:

- `peek` — inspect representative canvas / context samples
- `grep` — search graph / trace / knowledge text
- `partition_map` — fan out subcalls over branches, layers, panels, rooms, zones
- `reduce` — merge sub-results into typed outputs
- `finalize` — produce public rationale and pins

**Probably the most immediately actionable insight:** Chirp components need not be single LLM calls. They can be tiny RLMs with typed GH pins as their outer API.

### 3.5 Knowledge store as the recursive context object (Claude)

RLM's claim: context is a programmable variable. Rook's UnifiedStore is *already this shape* — a graph the agent traverses, not a doc dump.

Today `knowledge_query(intent, depth)` is a one-shot lookup with a fixed resolution knob. RLM-flavored:

```python
loft_neighborhood = store.query("loft").follow_links(depth=2)
by_pattern_kind = loft_neighborhood.partition_by("pattern_kind")
candidates = by_pattern_kind.map(lambda p: sub_rlm(f"is {p} relevant?", p))
FINAL(candidates.filter(relevant=True))
```

The `quick / context / errors / raw` depth tiers stop being a global setting and become *what the root LM picks adaptively per partition*. We already have the philosophy ("the knowledge store is not a lookup table" — CLAUDE.md). RLM gives us the *execution model* that matches.

**Boundary pushed:** the linked-neighborhood doctrine becomes machine-executable, not just authorial advice to Claude.

### 3.6 The UI-thread bottleneck × isolated REPLs (Claude)

We have one hard constraint: all HTTP requests serialize through Rhino's UI thread. RLM offers isolated execution environments precisely so sub-calls don't fight over a shared resource.

Cross-application: **sub-RLMs run in isolated REPLs and can't touch Rhino — but they can do all the *planning, knowledge retrieval, decomposition, and Chirp reasoning* in parallel, then return typed instructions for the UI thread to serialize.** Cascade parallelism without violating the concurrency constraint.

### 3.7 Statechart × RLM (the natural marriage)

If states own RLM scopes:

- Each state has its own REPL variables (its context window)
- Transitions are *recursive calls* with transformed context
- History states = persistent REPL state across re-entry
- Orthogonal regions = parallel REPLs with shared event bus

The chart says *what's true now*. The RLM says *what variables you have in scope right now.* Same thing, different vocabularies. A Chirp statechart would be both — visual structure AND executable recursion.

### 3.8 Patterns as compiled sub-RLMs (Claude)

A Rook pattern today is a wiring template. In RLM language, a pattern is **a compiled subroutine the root LM can call without re-reasoning.** PatternStore becomes a library of pre-trained sub-RLMs. DSPy compilation lands here naturally — compile a recurring decomposition strategy into a typed sub-RLM, store it, retrieve it on intent match.

`gh_save_pattern` is reframed from "save a wiring template" to "save a learned sub-program." The pattern *runs* recursively when invoked.

### 3.9 New Chirp category: `orchestrator` (Codex)

Not a planner, not a critic. An `orchestrator` component owns a small executable statechart and coordinates other Chirp calls or downstream solve behavior.

```
Inputs:  Brief, CanvasContext, Budget, Correction
Outputs: NextAction, TargetComponents, ReasoningSummary, Done
```

It drives multi-step design workflows without turning the whole system into an opaque agent loop.

### 3.10 Correction pin as a statechart event (Codex — the sharpest single observation)

Current Chirp treats `Correction` as extra input context. Statecharts suggest a sharper model: correction is an *event* that interrupts or transitions the component.

```
validated → correction_received → reconciling → validating
```

This makes human steering durable, replayable, and visible — instead of just another prompt string. Combined with trajectory logging, corrections become first-class transitions, not pluggable strings.

### 3.11 Component flight recorder (Codex naming, both contributing)

Chirp already logs JSONL traces. RLM emphasizes trajectory interpretability. Statecharts give event/state vocabulary. Combine into a "component flight recorder":

```
event:        solve_started
state:        inspecting_context
action:       grep upstream reasoning
state:        partitioning
subcall_count: 6
state:        validating
guard failed: output coercion
state:        corrected
```

AI nodes become debuggable in a Grasshopper-native way.

### 3.12 Canvas as persistent RLM memory (joint)

Aligns with Chirp's founding idea: Grasshopper is the LLM's working memory. RLM adds: the memory can be too large to paste. Statecharts add: memory interaction should have modes and transitions. The canvas becomes not just storage, but **an executable cognitive environment.**

---

## 4. The Synthesis — Three Orthogonal Regions

This is the frame neither voice reached alone, but both voices imply.

> **A Chirp component's identity has three axes that are currently conflated into "category":**
>
> 1. **Role** — what it contributes to a cascade (planner, critic, narrator, ...)
> 2. **Strategy** — how it processes context (peek, grep, partition_map, reduce, finalize)
> 3. **Lifecycle** — where it is in the solve (dirty, inspecting, calling, validating, cached, corrected)

Today the seven Chirp categories squash these together. The categories are mostly *role*, sometimes *strategy* (a `gate` is really a strategy), never *lifecycle*.

**Statecharts pull (3) out as an orthogonal region. RLMs pull (2) out as an orthogonal region.** What we want is a single statechart with three orthogonal regions running in parallel, and the existing seven categories become *configurations* over those regions, not the dimension itself.

```
role:       planner
strategies: [peek, partition_map, reduce]
lifecycle:  default                          (dirty → ... → cached, with correction event)
```

A `gate` becomes `role: predicate, strategies: [peek], lifecycle: default`.
An `interpreter` becomes `role: extractor, strategies: [peek, grep, summarize], lifecycle: default`.
An `orchestrator` becomes `role: orchestrator, strategies: [partition_map, reduce], lifecycle: extended`.

Cascades are not separate constructs. **A cascade is a parent statechart whose orthogonal regions are component statecharts.** Composition for free.

### 4.1 Two-level FSM observation

Codex's lifecycle diagram (`idle → dirty → inspecting → calling_llm → validating → cached`) is the **executor** state machine. Inside `calling_llm`, the *reasoning* state machine lives — that's where RLM's `peek/grep/partition/map/reduce/finalize` actually executes.

Statechart hierarchy handles this for free: `calling_llm` is a superstate containing the RLM substates. This is a place statecharts and RLM compose mechanically, not just thematically.

---

## 5. Open-Horizon Claims (Don't Reduce These Yet)

These are the visionary moves we'd lose if we collapsed the doc to "what ships next." Keeping them here on purpose.

### 5.1 The canvas as a 2D REPL is a category difference

Every other RLM implementation has a 1D textual REPL. Rook has a 2D persistent typed visual one. This isn't a feature; it's a *substrate* claim. The implication: a Chirp-RLM can have its trajectory be *literally drawn* — every recursive sub-call is a sub-cluster, every peek is a hover, every partition is a fan-out of wires. The user sees the agent thinking in their native medium.

If true, "trajectory visualizer" stops being an artifact and becomes a *property of the substrate*. RLM-the-paper has nothing analogous.

### 5.2 The roles axis might dissolve

Once `strategy` is first-class, "planner" might just mean "uses partition_map + reduce, prompted to plan." The seven Chirp roles could be **a UX/affordance choice for human authors** — they tell you what *intent* to put in the component — but architecturally the system is 2D (strategy × lifecycle), not 3D (role × strategy × lifecycle). Roles become docs, not architecture.

This is a load-bearing question. If true, it changes the schema. If false, roles stay first-class. Worth empirical pressure.

### 5.3 The knowledge store wants to be queried recursively, not retrieved

Our existing CLAUDE.md doctrine — "the knowledge store is not a lookup table; it's a semantic graph of composable primitives, your job is to compose them" — is *currently advice to Claude*. With an RLM execution model, that doctrine becomes the *runtime behavior of `knowledge_query`*. The agent doesn't query and read; it queries and *operates on the result graph recursively*. The philosophy and the execution model converge.

### 5.4 Earned autonomy is a guard

The Assist / Explore / Build interaction modes (memory: `project_earned_autonomy.md`) live in their own orthogonal region. Earned autonomy = guards on transitions between them. Today this is implicit in agent code; statecharts would make it *first-class* and inspectable. The user could *see* why the system thinks they're ready (or not) for a mode shift.

### 5.5 Patterns are subroutines, not templates

Today PatternStore feels like a library of stencils. With RLM thinking, patterns are *compiled sub-programs*. `gh_save_pattern` saves a recursive strategy, not just a wiring. A skilled user creates a pattern by *demonstrating a decomposition*, and the system records the strategy along with the wiring. This is a much bigger claim than the current doctrine and probably needs DSPy compilation to land for real.

### 5.6 The `Correction` event might not just be human steering

If correction is a statechart event with a transition, *anything* can fire it — a critic Chirp, a downstream validator, a knowledge-store contradiction, a scene-graph anomaly detector. The correction-event protocol generalizes from "human typed something" to "any source of authoritative dissent can interrupt the active state." That's a substrate.

### 5.7 The canvas as cognitive environment is a thesis, not a feature

The deepest version: **Grasshopper isn't where the agent ends up; it's where the agent thinks.** The canvas is to the Chirp-RLM what the Python REPL is to a programmer — not output, not visualization, but the medium of cognition. Every other AI-CAD product has the model output drawings *to* a canvas. Rook would have the model think *in* a canvas. That's the thesis worth defending.

---

## 6. Empirical Anchors (Before We Commit to Anything)

Per the `feedback_observe_before_theorizing` posture: nothing here is buildable until we test the load-bearing assumptions. Three pressure tests:

1. **Is the canvas-as-REPL claim real, or just suggestive?** What would `peek/grep/partition` literally mean as `gh_*` calls? If we can write the mapping table on a napkin, the idea has legs. If we can't, the claim is poetic, not architectural.

2. **Where does context-rot actually hurt today?** If our longest Chirp cascade today fits in 50k tokens, RLM's framing is theoretical. If we're already feeling it (Wasp grammar, knowledge-store dumps, full-canvas snapshots, large scenes), it's load-bearing now.

3. **Recursion vs. statechart hierarchy — same thing or distinct tools?** They overlap a lot. Honest version: recursion is dynamic (the LM decides), statecharts are static (the chart decides). Both can coexist; they're not competitors. But we should be precise about which problems each one owns.

---

## 7. Conservative-First Sequencing (If We Pull the Trigger)

Codex's sharpest move: *start inside the component, not at the cascade layer.* If each Chirp is a statechart with the three regions (§4), the cascade layer is *literally* statechart composition. Cascades fall out for free.

If we ever decide to ship this, the sequence would be:

1. **Spec the three orthogonal regions** as a doc — role / strategy / lifecycle, with the seven categories re-expressed as configurations.
2. **Pick one category and instrument it** — probably `gate`, since it's the simplest and the "correction-as-event" claim is most testable there.
3. **Confirm the flight-recorder artifact has the shape we want** before committing the rest of the categories.
4. **Then** move to cascade-as-composed-statechart and orchestrator-as-special-case.
5. **Then** introduce RLM-style recursion inside `calling_llm` substate.
6. **Then** attempt the canvas-as-REPL substrate work — only after we have a flight-recorder showing real context-rot pain.

This is sequencing, not commitment. Don't read it as a plan.

---

## 8. Open Questions Worth Carrying Forward

- Does the `role` axis survive long-term, or dissolve into prompt-authoring (§5.2)?
- Is recursion-as-state-transition cleaner than recursion-as-substate? (probably the latter, but worth thinking through)
- How does this interact with Conductor (today's flat phase FSM)? Does Conductor become a statechart at the agent layer that mirrors the per-component statecharts at the Chirp layer? (suspected: yes, fractally)
- Where do trajectories *live*? Per-component? Per-cascade? Per-session? Per-canvas? Probably all four, with hierarchy.
- Is the flight recorder a Rook artifact, a Chirp artifact, or a substrate artifact (i.e., shared between Chirp, Conductor, and agent loops)?
- If patterns are sub-RLMs (§3.8, §5.5), what's the relationship to skills (the `/chirp`, `/design-grasshopper` markdown files)? Are skills just human-authored sub-RLMs?
- Does any of this change how we think about earned autonomy (§5.4)?
- The interaction-model vision (Assist/Explore/Build) is in memory but not in the codebase yet — does this work *replace* that thread, *unblock* it, or *coexist* with it?

---

## 9. Voices Preserved

This doc is on purpose a duet. Where it matters:

- **Codex tends to:** reduce scope, sharpen lifecycles, name the next concrete step, propose new categories with clear pin contracts, treat the canvas as a queryable context object.
- **Claude tends to:** claim substrate, surface category-level reframings, push the canvas-as-REPL framing, hold the open-horizon dimension, reach for "this is the thesis worth defending."
- **Both agree on:** statechart × RLM is the natural marriage; correction-as-event is the cleanest single sharpening; cascades are statecharts; Chirp components want to be tiny RLMs; the three-orthogonal-regions synthesis (§4) is the load-bearing factoring.

When this doc is revisited, *don't collapse the duet*. The reduction is easy. The vision is the part that gets lost first.

---

## 10. What This Doc Is Not

- Not a plan.
- Not a scope.
- Not a PR proposal.
- Not load-bearing on any current work.
- Not a commitment to any of the §5 claims.

It is a record of an exploratory conversation, structured enough to be picked up later without re-derivation. If we never build any of this, the doc still earned its keep by being the place we put the surface area down.

---

## 11. Resume Hooks

If a future session needs to pick this up:

- Start in §4 (synthesis) — it's the densest and least likely to drift.
- The §5 claims are the open-horizon dimension; protect them when refining.
- §6 is what to test before committing.
- §7 is the conservative sequencing if we ever pull the trigger.
- §8 is the live question list.

Re-read §0 first to remember the posture: *don't reduce prematurely.*
