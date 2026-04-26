# Rook Positioning Thesis — Rhino Side

> **One sentence:** Rook is the layer that makes LLMs reliable in Rhino.

> **One paragraph:** Rhino is an object editor. Rook is the layer that lets an LLM operate on the *building* — query columns by facade, find walls by orientation, rebase Revit-imported blocks atomically, and recover from modal-dialog deadlocks before they crash the session. Open source. Bring your own model.

---

**Status:** Canonical positioning reference. Read this before drafting any launch post, pitch deck, conference talk, sales conversation, or marketing copy.

**Last verified:** 2026-04-08 — by skeptical audit of the actual code via parallel explorer agents reading `src/RookNative/Handlers/SceneGraphHandler.cpp`, `src/RookNative/Handlers/BlocksHandler.cpp`, `src/RookNative/Handlers/CommandHandler.cpp`, and `knowledge/commands/command_knowledge.json`.

**Re-verify if:** any cited file path or line range no longer matches the code, any "do not claim" item graduates to real, or a new differentiator emerges that belongs in the top three.

---

## How to use this doc

- **If you're drafting copy:** Read the *Three Differentiators* section and the *Do Not Claim* section. Build claims only from the first; explicitly avoid claims from the second. The honest one-sentence pitch and the honest one-paragraph version are both at the top — start there, edit from there.
- **If you're filming a demo:** Skip to the *Demo Recipe* section. It's a 60–90 second continuous-take recipe with timing, voiceover, and exact MCP tool calls. Every step is grounded in code that exists today.
- **If you're reviewing this doc for accuracy:** Walk the file:line citations. If they don't match the code anymore, the doc is stale and either needs updating or needs an item demoted to *Do Not Claim*.
- **If you're a collaborator (Codex / Manus / contributor):** This doc is the source of truth for "what is Rook, really." Other strategy docs in `drafts/` (competitive teardowns, technical dives) build on this thesis but should not contradict it. If you find a contradiction, this doc wins unless you have evidence the underlying code has changed.

---

## Why this thesis, and why now

The trap this doc exists to prevent: *"Claude makes a box in Rhino"* demos undersell Rook by demoing the wrong unit of value. Single-command execution is not what makes Rook special — single-command execution is what makes Rook *table stakes*. The layer above it is what's load-bearing.

Equally important: the temptation to claim more than has shipped. Rook has aspirational architecture (multi-agent autopilot, self-improving learning loop, continuous DSPy consolidation) that is real *as design* but not yet wired end-to-end in production. Promising those in launch copy creates a credibility debt that costs more than the marketing lift is worth. The *Do Not Claim* section is the standing answer to "should we say X?"

---

## Three load-bearing differentiators

These are real, shipped, and defensible today. Each is anchored to a specific file in the codebase so this doc rots loudly if the code moves.

### 1. Scene Graph + semantic spatial classification

**Where:** [`src/RookNative/Handlers/SceneGraphHandler.cpp`](../Rook/src/RookNative/Handlers/SceneGraphHandler.cpp)

**What it is:** A real-time, queryable spatial relationship graph computed from document state. Each object carries shape-class metadata (`vertical-planar`, `horizontal-slab`, `elongated-vertical`, etc.), spatial metrics (`isVertical`, `elongation`, `flatness`, `volume`, `floorArea`), and relationship edges to other objects (`contains`, `supports`, `adjacent`, `above/below`, `intersects`) with distance metadata. The graph is queryable by bounding box, layer, shape class, and relationship type.

**Why it matters:** A naked LLM with Rhino access cannot answer *"find all the structural columns on the south facade."* It can match object names if you happen to have named them, but it has no concept of what a column *is* spatially. An LLM with Rook can. The classification is heuristic, not ML — that doesn't matter. What matters is that the question becomes answerable in natural language.

**How unique:** Rhino does not ship spatial reasoning. Revit has BIM semantics, but the Rhino ecosystem does not. The closest analogues are commercial BIM-overlay plugins, none of which expose their graph to an LLM via MCP. As far as we know, no open-source tool in the Rhino ecosystem does this.

**Why it's the moat:** It's the precondition that makes everything else feel like reasoning instead of automation. A demo that opens with a scene-graph query frames Rook as understanding the model. A demo without it frames Rook as scripting the model. The difference is the entire pitch.

### 2. Block Rebase Recursive

**Where:** [`src/RookNative/Handlers/BlocksHandler.cpp`](../Rook/src/RookNative/Handlers/BlocksHandler.cpp) — rebase logic around line 3209+, recursive variant around line 3635

**What it is:** Atomic rebase of block definitions whose origins have drifted (typically the result of Revit-exported `.3dm` files where each floor's block definitions have absolute Z-offsets baked in). The implementation:

- Detects null object slots that would corrupt the rebase before starting
- Rejects linked blocks (which can't safely rebase)
- Validates all geometry is materializable
- Computes the anchor point and delta translation
- **Compensates every instance post-multiplication** so the model does not move in world space
- Updates parent block definitions that reference the leaf as a nested block (the recursive variant)
- Uses a dry-run/execute dance with `expectedPlanHash` to prevent stale executions
- Wraps the entire compound operation in a single undo record

**Why it matters:** Architects spend days fighting this manually after a Revit-to-Rhino handoff. The blocks aren't reusable, the bounding boxes are wrong, instancing is broken, and there's no clean way to fix it without moving every floor in world space. Rook does it atomically.

**How unique:** No other open-source Rhino tool does this. It's the kind of operation that makes a senior practitioner stop and ask *"wait, you have what?"* — which is the reaction worth designing the demo around.

### 3. Knowledge store with hard-won gotchas

**Where:** [`knowledge/commands/command_knowledge.json`](../Rook/knowledge/commands/command_knowledge.json) — 196 commands, 543 observations as of 2026-04-08

**What it is:** A structured knowledge base of Rhino commands, organized by command, then by mode within each command, then by gotcha within each mode. Observation density per command serves as a confidence signal. Real failure-mode wisdom that does not appear in Rhino's official docs:

- `-Box` default mode: the third input is *height*, not a Z-coordinate — the base rectangle is in the construction plane. Catches the user-says-Z, gets-2D-in-CPlane bug.
- `-Sphere` 3Point: points must not be coplanar or collinear, or you get silent degenerate failure.
- `-Cone`: the height parameter takes a numeric value OR an apex point coordinate, never both. Mixing produces a cryptic Rhino error with no recovery path.
- `-Cylinder`: height must be non-zero or you get an invalid solid object left on the canvas.

**Why it matters:** This is not a docs-RAG. It's docs *organized for failure recovery*, with mode-level granularity that lets the routing layer disambiguate variants (`-Box _Diagonal` vs `-Box _Center` are fundamentally different operations, not just option flags). Useful as-is even before any learning loop fires.

**How unique:** A static RAG over Rhino's official documentation could not produce these gotchas — they exist because someone hit the failure and wrote it down. Rook chose to architect for that flow rather than for keyword retrieval. The schema is the differentiator, not the current contents.

---

## Missing framing that should stay front-of-mind

The easiest way to undersell Rook is to demo it as "Claude makes a simple object in Rhino." That is the wrong benchmark. It collapses Rook down to command execution, which is table stakes and visually interchangeable with every other AI-for-CAD toy demo.

The more honest framing is:

> Rook is most special when Rhino stops being a dumb command terminal and becomes a live, inspectable working context for an AI.

That means the interesting unit of value is not blank-canvas generation. The interesting unit of value is **continuation inside an existing design session**:

- the AI can read scene context, not just object IDs
- the AI can see interactive state, not just final geometry
- the AI can continue a human move, not just start from zero
- the AI can expose what it saw and why it acted

On the Rhino side, this matters because the host application is fundamentally interactive. Architects and designers do not work by serializing complete intent into pristine prompts. They select things, drag gumballs, inspect local conditions, change their mind, and work against messy imported geometry. If the AI only performs command execution, it is a scripting layer. If it can operate inside that interaction loop, it becomes a collaborator.

This is why launch copy should avoid over-indexing on "natural language modeling in Rhino" and instead emphasize **contextual, interactive, inspectable collaboration**.

---

## Secondary differentiator worth naming explicitly

This is not in the top three because it is harder to explain in one sentence, but it is one of the most important reasons Rook feels different in practice.

### 4. Interactive state capture: gumball context + session history

**Where:** [`src/RookNative/Interactive/GumballContext.h`](../Rook/src/RookNative/Interactive/GumballContext.h), [`src/RookNative/Handlers/GumballHandler.cpp`](../Rook/src/RookNative/Handlers/GumballHandler.cpp), [`src/RookNative/Handlers/SessionHandler.cpp`](../Rook/src/RookNative/Handlers/SessionHandler.cpp)

**What it is:** Rook exposes Rhino's live interactive state to the AI, not just the resulting geometry. The gumball context returns the full frame, selected-object summaries, available operations, and spatial neighbors in one round-trip. Gumball drags have their own history. Sessions can be queried and exported as structured history.

**Why it matters:** This is the bridge between "AI can call geometry tools" and "AI can work with me while I design." It lets the model understand what is selected, what operation is meaningful right now, what changed, and what the user just did. That is much closer to how human designers actually work in Rhino than prompt-in, geometry-out demos.

The strongest detail here is `AvailableOperations`. This is not just the host exposing every handle generically; it is the system telling the AI which operations are actually meaningful for the current selection. `canExtrude` only turns on when the selected geometry supports it, and `enabledHandles` tells the model which manipulations are worth attempting. That is contextual tool availability, not just contextual tool access.

**How unique:** Most AI CAD demos treat the host as a stateless executor. Rook treats Rhino as an interactive environment with ongoing state. That difference is subtle in copy but obvious in use.

**Positioning value:** If the scene graph is what makes Rook look like it understands the model, interactive state capture is what makes it look like it understands the *session*.

---

## Do not claim (the load-bearing honesty section)

**These are real architecture but NOT yet shippable as positioning claims.** Do not quietly upgrade them to differentiators in launch copy without re-verifying first. The temptation will creep back every time someone is drafting marketing material under pressure.

### "Self-improving — learns from your corrections"

`correction_detected` is wired in 6 places across `mcp_server/src/rook/server.py` and `mcp_server/src/rook/agent/tool_dispatcher.py`. The flag flows into `mcp_server/src/rook/learning/metrics_store.py`. The infrastructure is sound and the architecture is correct.

**But:** the flag has fired *zero* times in production traffic as of 2026-04-08. The store grew via batch consolidation (most recent: February 2026), not via production feedback loops.

**Honest framing:** *"Open knowledge store with documented gotchas, designed to grow from corrections."* Not *"learns from your corrections."* Promote this only after the first non-zero `correction_detected` count appears in production metrics and produces a visible new gotcha.

### "Multi-agent autopilot — Planner + Workers via direct HTTP"

`Plan` and `PlanResult` dataclasses, validation logic, and dispatch infrastructure all exist in `mcp_server/src/rook/agent/`. The CLAUDE.md architecture description (agents calling HTTP directly, not through MCP) is accurate as a design.

**But:** the end-to-end multi-step agent loop is **not yet wired in production**. `spawn_agent` and conductor logic exist but no live multi-worker coordination is happening in user-facing flows. The chat server is primarily backing the embedded chat panel, not orchestrating workers.

**Honest framing:** Save for a future v0.2 announcement when the loop ships end-to-end. Don't include in v1 launch.

### "DSPy-driven continuous consolidation"

DSPy code exists. Consolidation runs as a batch process. Last batch: February 2026.

**But:** it is not a continuous loop fed by production traffic. It's a periodic offline process.

**Honest framing:** *"DSPy-based knowledge consolidation pipeline."* Not *"continuously learning."*

### Standing rule

If any of these graduate to "real," update this section *first*, then update the *Three Differentiators* section. The order matters — it forces the honesty check to happen before the marketing claim.

---

## Demo recipe — 60–90 second clip

A single continuous screen capture, four steps, voiceover narration. Every step is grounded in MCP tool calls that work today.

**Setup:** A real, messy Revit-exported building model. Five floors. Blocks per floor with baked Z-offsets. Mixed structural and MEP layers. No object names you can rely on for queries. No setup theater on camera — open the file cold.

| Time | Action | What Rook does | Voiceover |
|------|--------|----------------|-----------|
| 0–10s | Open the file | Loads, scene graph populates | *"This is a Revit export. Five floors, hundreds of blocks, layer names from Autodesk."* |
| 10–35s | Type: *"Show me all the structural columns above floor 3"* | `scene_query` with shape-class + bbox + layer filters; columns highlight in viewport | *"It found them by understanding what a column is — vertical, elongated, in the structure layer. Not by reading their names."* |
| 35–60s | Type: *"These blocks have baked Z-offsets from the Revit export — clean them up"* | `rhino_block_rebase_recursive`; definitions normalize, instances stay in place in world space; one undo record | *"One undo. The whole thing rolls back if I want."* |
| 60–90s | Type: *"Now tag the columns and the cleaned blocks for game-asset export with collision categories"* | Auto-tags via layer rules, validates, exports with manifest | *"And it hands off to the next tool with semantics intact."* |

**Narrative arc:** understanding → cleaning → handing off. The architect's actual workflow.

**Why this order matters:** The scene query *first* establishes "Rook understands the model." That's the precondition that makes everything else feel like reasoning instead of automation. If you lead with block rebase, it looks like a clever script. If you lead with the scene graph, the block rebase looks like reasoning *applied to a model the system already understands*. The order is the story — do not reorder for pacing.

**What this demo deliberately does not show:**

- No multi-agent orchestration (not yet wired end-to-end in production)
- No "learning from correction" arc (correction loop has not fired in production)
- No renderer (separate plugin, separate story, save for its own clip)
- No Grasshopper (this is the Rhino-side post; GH gets its own thesis and its own demo)

Leading with what is solid is how you build trust for the things that aren't yet.

---

## Alternate demo recipe — live collaboration, not blank-canvas generation

If the launch wants to emphasize "why Rook is different from simple prompt-to-geometry," this is the clip to film.

**Setup:** An existing Rhino model with repetition and local constraints: facade bays, roof ribs, panel openings, framing members, or any condition where one manual move should logically propagate to neighboring conditions.

| Time | Action | What Rook does | Voiceover |
|------|--------|----------------|-----------|
| 0–15s | Start with the existing model, not an empty file | Selection + scene context are already meaningful | *"This is where Rhino work actually happens: not from zero, but in the middle of an existing model."* |
| 15–30s | Manually select one object/face and make one gumball edit | Rook can read selection, gumball state, object summaries, and neighbors | *"Rook isn't just reading object IDs. It can see what I selected, how it's oriented, and what's around it."* |
| 30–55s | Type: *"Continue that move across the adjacent bays, but stop at the skylights"* | Uses interactive context + scene context to continue the intent in the local region | *"This is the point: not 'make me a shape,' but 'understand what I just did and continue it where it makes sense.'"* |
| 55–75s | Briefly show the result plus history/context | Gumball history or session history proves the action stayed inspectable | *"Every step is visible. This is collaboration inside Rhino, not a black box outside it."* |

**Narrative arc:** human action → AI understanding → AI continuation → inspectable result.

**Why this demo matters:** It reveals a more important truth than any toy generation clip: Rook's real strength is turning live Rhino interaction into something an AI can perceive and continue responsibly.

**Production caveat:** The 30–55s prompt depends on the test model supporting the needed semantics cleanly, either through the scene classifier, layer-name fallback, or both. Do not film this cold on an arbitrary model. Stage-test the exact file and prompt before capture.

**When to use this demo instead of the primary one:** Use it when the audience is skeptical of flashy AI demos and you need to show that Rook is about workflow depth, not novelty. Keep the block rebase demo for audiences that respond to painful production problems. Keep this one for audiences that need to understand the product thesis.

---

## The honest pitches (drop-in copy)

Use these verbatim or as starting points. All three are derived from the thesis and verified against the differentiators above. Pick the one that fits the channel.

### A. The "operates on the building" pitch (recommended for launch)

> Rhino is an object editor. Rook is the layer that lets an LLM operate on the building — query columns by facade, find walls by orientation, rebase Revit-imported blocks atomically, and recover from modal-dialog deadlocks before they crash the session. Open source. Bring your own model.

### B. The "infrastructure not vibes" pitch (for technical audiences)

> Most "AI in CAD" demos are an LLM piping commands at the host application and hoping. Rook is 242 typed routes, a queryable spatial scene graph, atomic block-rebase operations, and a 196-command knowledge store of real failure modes — the boring infrastructure that makes "Claude, fix this Revit import" actually work instead of crash.

### C. The "open-source counterweight" pitch (for the AEC + open-source crowd)

> The AI-for-CAD category is going closed. Rook is open source, runs in your Rhino, with your model provider, on your knowledge store. We built it because architects shouldn't have to send their site models to someone else's GPU cluster.

**Recommended default:** A. It is the most defensible against "but can it actually do that?" because every clause in it maps to a specific differentiator above.

---

## Verification protocol

This doc rots if the code moves. Re-verify on any of the following triggers:

1. **Major refactor of the C++ native plugin** (the cited handlers) — walk the file:line citations and update or demote.
2. **`correction_detected` fires non-zero in production metrics** — promote the learning-loop claim from *Do Not Claim* to *Differentiators*, write a new file:line citation pointing at the production evidence.
3. **Multi-agent loop ships end-to-end** — same promotion process.
4. **A new load-bearing capability emerges** that belongs in the top three — add it, and demote one of the existing three to a secondary claim with a written rationale for the demotion.
5. **Six months elapsed** with no other trigger — re-verify anyway. Six months is the staleness ceiling for a positioning doc anchored to a fast-moving codebase.

**Method:** Read the cited handlers directly. Sample the knowledge store. Check production metrics for the `correction_detected` field. Use parallel explorer agents to avoid confirmation bias. Skeptical audit, not face-value trust. Update this doc *before* updating any external copy that depends on it.

---

*This document is the canonical positioning reference for Rook on the Rhino side. The Grasshopper-side thesis is a separate document and should be drafted with the same skeptical-audit method.*
