# Reasoning as Dataflow — An Agentic Design Workflow

**Date:** 2026-08-01
**Status:** design, pending review
**Scope:** Rook + Chirp + Architecture Studio, composed into a single working model
**Type:** Design doc (precedes implementation plan)

---

## Purpose

This document records a design *and the reasoning that produced it*. Several
earlier framings were proposed and discarded during the design conversation;
the discards are recorded in "Rejected framings" below, because knowing why an
approach was dropped is worth more than the approach.

The subject is not a demo. It is the shape of how an architect and an agent work
together on a project, and which existing pieces already implement it.

---

## Thesis

**Architecture Studio produces reasoning as prose. Chirp turns reasoning into typed
dataflow. That is the difference that makes everything else compose.**

Prose can inform a model but cannot drive one, which is why research and geometry
always drift apart in practice. Once reasoning is a wire rather than a document, it
can set parameters, be read by another node through a different lens, be criticised,
be corrected by a human, be narrated into a presentation, and be traced.

---

## Premise: what changed

The agent is the expert coder. **An architect never needs to learn Grasshopper again
unless they want to.**

Grasshopper literacy was never a competence — it was a tax. Nobody learns GH because
they want to write programs; they learn it because it was the only route to parametric
behaviour. The skill was always instrumental. With an agent that can author, edit,
diagnose and explain a definition, the tax is refundable.

The consequence is larger than convenience. Today parametric capability correlates with
**programming aptitude**, not design talent. That is a bad filter and the profession has
simply lived with it. Removing it means design ability, not graph-thinking ability,
determines who gets the good tools.

### Why this matters commercially

| Fact | Source |
|---|---|
| 76% of US architecture firms have fewer than 10 employees | AIA 2024 Firm Survey |
| 28% are sole practitioners; 32% have 2–4 staff | AIA 2024 Firm Survey |
| Small firms are 76% of firms but 14% of billings | AIA 2024 Firm Survey |

The overwhelming majority of practices structurally cannot employ a computational
designer — no headcount, no slack to learn, thinnest margins, and they do early-phase
work at risk. Parametric capability is currently rationed to roughly the 6% of firms
that can staff it.

"Democratic" therefore does not mean a simplified interface. It means **a capability
that currently requires a specialist headcount becomes available to a practice that
cannot have one.** The agent is the computational designer a three-person office could
never hire.

### The critical qualifier

Rook does not replace Grasshopper. It replaces the **requirement to author**
Grasshopper. The artifact remains a real `.gh` file — native, open, inspectable,
portable, editable by anyone who cares to. This is the difference between this and a
black-box service that returns a picture and keeps the model. The architect owns a
genuine parametric definition whether or not they ever open it.

---

## Architecture

```
Architecture Studio            structured research → findings (prose, tables, JSON)
        │
        ▼
Chirp  planner                 findings + brief → typed parameters
        │                      Reasoning pin carries the derivation
        ▼
Grasshopper (Rook-authored)    deterministic parametric geometry
        │                      typed pins are the structural boundary
        ▼
Geometric + spatial analysis   analytical geometry: the finding, as geometry
        │
        ├─► Chirp interpreter / critic / gate     multi-lens evaluation
        │
        ├─► RookVision                            diagrams, images, film
        │
        └─► Chirp narrator                        design narrative
                    │
                    ▼
        Architecture Studio deck                  presentation from the same source of truth
```

### Why the deck is honest

The narrator synthesises the *same reasoning streams that drove the geometry*. Nobody
summarises the model after the fact. The presentation and the model share a source of
truth, which is precisely what fails in conventional practice.

---

## The working model

Practices are time-poor and interrupted. The unit of work is not a command; it is a
**session with a return**.

1. The architect briefs the work.
2. The agent runs research, authors the definition, wires the reasoning nodes, produces
   geometry and imagery — while the architect is elsewhere.
3. The architect returns and engages the **result**, not the process.
4. Disagreement enters as a **Correction pin**, not a chat message.
5. The `editor` node reconciles; downstream re-solves; narrative and imagery update.

### Why the Correction pin is the whole human-in-the-loop story

Every Chirp component automatically carries a **Correction input pin** and a **Reasoning
output pin**, and the `editor` category exists specifically to reconcile upstream
reasoning with human corrections.

So judgment does not enter as a message that scrolls away. It enters as a pin. It lives
in the definition, re-participates in every solve, and survives the architect going to a
meeting, the project changing hands, and the brief changing in March.

This is the answer to the problem that GH definitions are **amnesiac** — they encode
*what* but never *why*. Why is that slider 0.4? Because of a rear-yard rule, a daylight
study, a client preference. None of that is in the file today, so six months later the
definition gets rebuilt from scratch. A definition whose parameters carry live derivations
is **re-reasonable**: when inputs change, it can be updated rather than discarded.

---

## Open problems, with proposed resolutions

These are the three things a plan must actually solve rather than gesture at.

### 1. Chirp determinism semantics

**Problem.** A GH definition is supposed to be a pure function of its inputs. Chirp nodes
are not. Typed pins constrain the *shape* of an output, not its *value*. If a planner
returns 0.4 on Tuesday and 0.45 on Thursday from identical inputs, the model changed
silently. For a proposition built on *trustworthy* early-stage rigour, a model that
quietly drifts is worse than no model.

This is a live concern in the ecosystem already: the CanvasDirector design explicitly
fences off "global nondeterminism analysis of arbitrary upstream GH components."

**Proposed resolution — propose, then freeze.** Three node states:

| State | Behaviour | When |
|---|---|---|
| **Live** | Re-evaluates on input change | Exploration |
| **Frozen** | Output pinned to a recorded evaluation + trace id; reasoning still displayed; no LLM call | Development, presentation |
| **Stale** | Was frozen; an upstream input has since changed | Flagged visibly — never silently re-run |

The failure mode is not nondeterminism as such, it is **undetected change**. The Stale
state makes drift visible and leaves re-evaluation to the human.

Chirp already provides the substrate: caching in the call pipeline and JSONL tracing that
records cache hits. What is missing is the semantics and its surfacing.

**Unverified:** whether Chirp's cache keys on an input hash, and how invalidation is
currently exposed. Must be confirmed before planning.

### 2. What the return-to-engage moment renders

**Problem.** If the architect returns and has to audit a stranger's model, the asynchrony
is worse than useless.

**Proposed resolution — a brief, not a model.** Five parts:

1. **What was built** — one line, plus a diagram or render of the current state.
2. **What was assumed** — every default the agent chose rather than asking about, each
   traceable to a source.
3. **What changed since last return** — the diff, including any Stale nodes.
4. **What needs you** — the small set of decisions that earn a human.
5. **What it costs to change your mind** — which parameters are cheap to revise and which
   invalidate downstream work.

Item 5 is the one nobody does, and it is what makes the brief actionable rather than
merely informative.

### 3. Which decisions earn a Correction pin

**Problem.** An agent that asks thirty questions has handed the job back to the human.
Knowing which decisions deserve a person is most of the skill.

**Proposed resolution.** A decision earns a pin only when it is all three of:

- **Contested** — reasonable practitioners would differ;
- **Consequential** — it propagates into geometry, cost, or compliance;
- **Underivable** — no amount of research settles it, because it is preference, judgment,
  or client politics.

Everything else is defaulted with the assumption stated in the brief. A default the
architect disagrees with can be promoted to a pin retroactively.

---

## Component status

Honest accounting of what exists versus what needs building.

### Verified present

| Capability | Evidence |
|---|---|
| GH batch authoring | `gh_snapshot` → `gh_edit`, atomic; `gh_errors`, solve-readiness |
| Composition knowledge | `gh_knowledge_query`, `gh_query_patterns` over real extracted definitions |
| Chirp reasoning nodes | 7 categories; DSPy modules; typed pin contracts; auto Correction + Reasoning pins; JSONL tracing; LiteLLM model-agnostic |
| Vision artifact store | kinds (`generated_image`, `depth_map`, `enhanced_prompt`), `parent_ids` lineage, approval gate (`rhino_vision_approve` → `rhino_vision_consume_approved`) |
| Depth capture | `rhino_capture_depth` — Arctic display mode, local, no API key, ControlNet-style conditioning input |
| Deterministic film | 14 `rhino_director_*` tools; camera planning in `camera_planner.py`; H.264 MP4 via Media Foundation; CanvasDirector merged (PR #416) |
| Image → geometry | `rhino_2d_to_3d_*`, `FalReconstructionProvider.cs` |
| AS research legs | site, environmental, mobility, demographics, programming, specs, sustainability, materials |
| AS zoning handoff | `## Envelope Data` JSON block (`lot_poly`, `setbacks`, `volumes[]`, `height_cap`) — a typed contract that already exists |
| AS deck | `/as:slide-deck-generator` — self-contained HTML, base64-embedded images, image-grid types 19–22, full-bleed 17–18, pairs with `/as:resize-images`; `as:brand-manager` agent for palettes and visual QA |
| Shared project state | `PROJECT.md`; every AS skill reads on entry and offers updates on exit; `/as:project record-decision` |

### Needs building

- The AS-findings → Chirp `planner` handoff (a reader plus a parameter contract).
- Node state machine (Live / Frozen / Stale) and its surfacing.
- The return brief.
- Narrator → deck wiring.

### Known gap

`rhino_director_*` is **not advertised on the currently deployed MCP surface** — the tools
exist in `server.py` but are absent from the running install. This is the standing
merge ≠ deploy gap. Either redeploy, or drive Director over HTTP, which is arguably more
correct anyway since agents use the HTTP layer directly and never MCP.

### Geographic constraint

AS's zoning and due-diligence skills are **NYC-only**. The site, programming, materials,
sustainability and presentation legs are not geographically bound. For "architects in
general," the research and delivery legs generalise today; the regulatory leg does not.

---

## Rejected framings

Recorded so they are not re-proposed.

| Framing | Why rejected |
|---|---|
| Bake geometry in order to measure it | Grasshopper measures area and volume natively. A chore invented to justify a step. |
| Depth-conditioned imagery with provenance as the centrepiece | Intellectually tidy, commercially thin. Still just Rook producing a render, dressed in epistemology. Valuable as *a* leg, not as the thesis. |
| The 2D→3D reconstruction loop as centrepiece | Image-to-3D returns meshes, not construction geometry. The "image becomes accountable geometry" claim is false if what returns cannot be built from. One capability among several, not the spine. |
| A FAR-versus-envelope "verdict" tool | A checking tool nobody asked for. Checking is what permits speed; it is not the product. |
| Sophisticated vs. democratic product fork | False fork. Same `.gh` artifact; engagement depth varies by user. The Correction pin lets a non-author steer without wiring anything. **One thing gets built.** |

---

## Risks

1. **Determinism** (see open problem 1) — the one that decides whether the model is
   trustworthy.
2. **Cost and latency** — Grasshopper re-solves constantly. A definition with several
   Live Chirp nodes is unusable without effective caching. Freezing is the mitigation as
   well as the semantics.
3. **Diagnosis is load-bearing.** When the architect cannot read the definition, they lose
   their own fallback. `gh_errors`, `gh_snapshot` and solve-readiness stop being
   conveniences and become the only diagnostic path. Acceptable — one does not debug one's
   compiler — provided the toolchain is honest about failure.
4. **Definition quality.** The claim fails if the agent authors bad definitions. Mitigated
   by querying the knowledge store before building rather than guessing components; this is
   a standing rule, not an optimisation.

---

## Out of scope

- Construction documentation, BIM authoring, or anything downstream of design development.
- Replacing design judgment. The architect's expertise — spatial judgment, program,
  materiality, code, client, context — is retained in full. Only the instrumental skill is
  delegated.
- Hiding or deprecating the Grasshopper canvas.

---

## Open questions

1. **Showcase shape.** One project carried across several returns — truer to how practice
   works, harder to stage — or a single return moment rendered in depth, which is what an
   audience can actually watch?
2. **First vertical.** The regulatory leg is NYC-only today. Does the first build lean on
   it, or on a geographically neutral leg (program, environment, materials)?
3. **Chirp cache semantics** — must be read from the implementation before planning.

---

## Next step

Implementation plan via `superpowers:writing-plans`, once the open questions above are
settled.
