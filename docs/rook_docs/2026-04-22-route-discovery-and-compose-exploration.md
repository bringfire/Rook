# Route Discovery & Compose — Exploration

**Date:** 2026-04-22
**Status:** Draft — exploration, not approved. Intended for iteration with Codex.
**Authors:** aryan + Claude (conversation seed)
**Related prior docs:**
- `2026-04-10-knowledge-graph-visualizer-spec.md` — shipped v1 panel
- `2026-04-11-knowledge-graph-v1.1-design.md` — tooltips, category spotlight, `similar_to` edges
- `2026-04-10-public-skills-brainstorm.md` — hand-authored skill inventory & convention system
- `2026-04-10-webui-substrate-contract.md` — substrate boundaries

---

## 1. Problem

Rook exposes ~300 MCP tools across Rhino, Grasshopper, Chirp, road/sidewalk,
blocks, scene, knowledge, etc. The CLAUDE.md onboarding teaches two entry
points (`rhino_execute_intent`, `gh_execute_intent`) and tells the user "use
`/mcp` to see the rest." That is enough for an LLM agent but not for a human.

A human sitting in front of Rook has no visual way to answer:

1. **What can I do here?** (capability discovery)
2. **What lives near the thing I'm already doing?** (adjacency / "if I'm in curves, what else is one step away")
3. **Can I save this as a reusable move?** (composition into a skill)

Memory is unreliable. Without a surface, users forget routes exist and
fall back to `rhino_execute_intent` for everything, which defeats the purpose
of the typed-route phases we've been shipping.

---

## 2. One-Sentence Proposal

Extend the existing Knowledge Graph panel with a **Routes layer** so
capabilities appear as nodes linked to the patterns/components they operate
on, entered via **search-led reveal** (not full-graph browse), with a
**compose tray** that turns a selection + prompt into a generated skill file.

---

## 3. What Already Exists (Grounding)

Before proposing, anchor on what's real today:

| Thing | State | Source |
|---|---|---|
| Knowledge Graph panel | Shipped v1.1 | `Rook/UI/...`, `mcp_server/.../chat/server.py`, Cytoscape + fcose |
| UnifiedStore (notes) | Canonical data source | `mcp_server/src/rook/learning/unified_store.py` |
| Note types | `component`, `recipe`, `pattern`, others | `knowledge_note.py` |
| Hover tooltips | Shipped | v1.1 |
| Category spotlight | Shipped | v1.1 |
| `similar_to` edges | Shipped | v1.1 |
| Skills | Hand-authored markdown files | `/chirp`, `/twisted-column`, pipeline skills |
| MCP tool catalog | Registered in MCP server; not (yet) indexed as notes | **open question — see §6** |
| WebUI substrate | Hardened; graph panel proves the boundary works | contract doc |

**Key constraint:** v1 of the graph was deliberately inspect-only. Anything
that *writes* (new note types, skill files) is a new stage, not a v1.2 tweak.

---

## 4. Proposed Direction

### 4.1 Three ideas, stacked

This is one composite idea with three layers. Each is independently
implementable and adds value on its own.

**Layer A — Routes as graph nodes.**
Add a `route` (or `tool`) note type. Each MCP tool becomes a node with
category (e.g. `rhino.geometry`, `gh.canvas`, `scene.query`), a short
description (first line of the tool's docstring), and edges to the
components / patterns it operates on.

**Layer B — Search-led reveal.**
Change the default view from "show the whole graph" to "show a prompt
box." User types intent or picks a domain chip. Relevant neighborhood
(patterns + routes) lights up, everything else stays hidden or collapsed
into category bubbles. Semantic zoom: zoomed-out = category clusters
("curves," "booleans," "pattern"); zoomed-in = specific routes/notes.

**Layer C — Compose tray.**
Side panel. Clicking a node adds it to the tray. User arranges an order,
writes a prompt description, and hits "Generate skill." Output is a
markdown file following the existing skill convention (see
`public-skills-brainstorm`), saved to the user's skill directory.

### 4.2 Why each layer pulls its weight

- **Layer A alone** makes routes discoverable even without search changes.
  Users can filter by `type=route` and browse by category.
- **Layer B alone** makes the *existing* graph more usable for its current
  purpose (patterns and components), separate from the routes work.
- **Layer C alone** is the novel piece — it inverts skill authoring from
  "write markdown" to "select a path and describe it."

Shipping A → B → C in that order means each stage stands on its own.

### 4.3 Density strategy — why search-led

The graph already has 880+ components and ~533 `similar_to` pairs. Adding
~300 route nodes plus their edges would make full-graph browse unreadable.
The answer is to stop using the full graph as the default view:

- **Empty-state:** prompt box + category chips + "popular routes" seed.
- **Query-state:** subgraph of ~10–30 nodes lit up, rest dimmed or hidden.
- **Zoomed-out state:** category cluster bubbles only, expand on click.

This reuses the existing Cytoscape + fcose stack — it's a default view
and class-toggle change, not a re-render.

---

## 5. Reality Check — What This Costs

**Data side:**
- Route exporter: pull tool registry → emit route notes with category,
  description, inferred edges. Open question on where edges come from
  (see §6).
- UnifiedStore may or may not want to host route notes natively. Could
  live as a parallel source the exporter unions in.

**Frontend side:**
- New node-type color / shape in Cytoscape.
- Empty-state / query-state / zoomed-out-state view modes.
- Compose tray component (new, but small).
- Skill generator: simple markdown template filled from selection + prompt.

**Skill generator side:**
- Need a canonical skill template that works for a compose-generated skill
  vs. the hand-authored ones.
- Need a save location convention and a way to invoke the generated skill
  afterward. The `public-skills-brainstorm` doc's convention system may
  be the right home for this.

**Not cheap, not huge.** Estimate: Layer A is a week of exporter + style
work; Layer B is ~a week of UI modes; Layer C is a week of tray +
generator + template. Rough.

---

## 6. Open Questions

Flag these for Codex to push back on:

1. **Where do route descriptions live?** Is there a structured tool
   registry in the MCP server with docstrings/categories, or does the
   exporter need to parse them from source? How stable are they across
   `rhino_*`, `gh_*`, `rc_*`, `chirp_*`, `rhino_command_*`?
2. **What are the edges between a route and a pattern/component?** Are
   they derivable (e.g. from intent-routing data), or do they need to be
   authored? Could the intent runtime's routing history *be* the edge
   source over time?
3. **Does the graph want route nodes at all,** or is a "capability panel"
   that cross-links to the graph better? The earlier conversation leaned
   toward unified; this is worth challenging.
4. **What does a "generated skill" actually contain?** Is it a prompt +
   an ordered tool list, a plan document, or a full markdown skill with
   frontmatter? The existing skills vary — `/twisted-column` vs.
   `/design-grasshopper` are very different shapes.
5. **Where do generated skills save?** Per-user? Per-project (`.rook/`
   following the convention system proposal)? Is there a "library" view
   in the WebUI?
6. **Does this need a v2 UnifiedStore write path,** or can generated
   skills be pure file writes outside the store?
7. **Interaction with Chirp cascades.** Is a generated skill different
   from a Chirp cascade definition? Where do they overlap?
8. **Failure mode:** what happens when a user composes a selection that
   doesn't make sense (incompatible routes)? Silent, warning, or
   validation gate?

---

## 7. Suggested Next Steps

1. **Codex review pass** — push back on §4 and §6, especially the data
   model for routes and whether edges are authored or derived.
2. **Sketch exercise** — paper/Figma mock of the three view states
   (empty, query, zoomed-out) and the compose tray. Before any code.
3. **Pick a concrete slice to prototype** — probably Layer A + a basic
   type filter, to prove the data model before committing UI work.
4. **Write a Layer A spec** in the style of the v1.1 design doc,
   answering §6.1, §6.2, §6.3.
5. **Revisit convention system doc** to decide whether generated skills
   live inside that proposal or are independent.

---

## 8. Non-Goals

- This is **not** a redesign of the Knowledge Graph panel. It extends it.
- This is **not** a replacement for CLAUDE.md or `/mcp` — those remain
  the canonical references for LLM agents.
- This is **not** a visual programming environment. The compose tray
  produces a skill (a named, reusable, describable move), not a live
  dataflow graph.
- This is **not** a promise that every route is worth surfacing. Some
  routes are agent-internal and should be hidden by default (flag in
  the exporter).

---

## 9. Honest Caveats

- The estimates in §5 are rough and based on doc signals, not a code
  audit. Codex should sanity-check.
- The claim that the UnifiedStore can absorb route notes is unverified —
  it may need a parallel source or a schema extension.
- "Search-led reveal" sounds clean but the empty-state is a real design
  problem (what seeds the first view?). This is where the idea lives
  or dies.
- The compose tray assumes a user knows what they want to save before
  they start clicking. In practice people compose by exploring. The
  tray needs an "undo / reorder / remove" ergonomics pass.
