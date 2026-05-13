# Proto-Skills

A staging ground for **emergent techniques** discovered during real Rook work
that aren't yet formal `/skills` but are worth capturing for reuse.

## What lives here

Each file is a single technique:

- **Trigger** — when to reach for this
- **Workflow** — the steps, in order, with the actual scripts
- **Design notes** — why each rule, what the tradeoffs are
- **First-use evidence** — concrete output from the session that birthed it

## Promotion path

A proto-skill graduates to `.claude/skills/<name>/SKILL.md` once:

1. It has been used **at least twice** on different geometry / contexts
2. The trigger phrases are stable
3. The script blocks have been parameterized (no hard-coded layer paths, etc.)
4. There's a small validation example

Until then, treat these docs as **recipes you read and adapt**, not as
automation. They live in `docs/rook_docs/` so they're searchable, but they're
explicitly *not* under `.claude/skills/` to keep the skill loader free of
half-baked entries.

## The single most important lesson — Phase 0 ⭐

**Always check sibling Revit category layers BEFORE reaching for any
of the workflows below.** Revit exports use category-nested layer
names (`APERTURE$APERTURE_PANEL_glass`, `G-IMPT`, `A-GENM`, etc.) and
design-intent geometry — clean panel outlines, family-instance blocks,
structural members — is often already present on a sibling layer
while the broken polysurface debris sits on a `_dwg` import layer.

The 2026-05-12 session spent ~3 hours on manual cusp reconstruction
before discovering that `APERTURE$APERTURE_PANEL_glass` contained the
entire glazing design as 141 clean curves. Building Breps from them
gave us **160 exact panels in 15 minutes** — orders of magnitude faster
and more accurate than the manual approach.

**First action on any Revit-cleanup task: run `rhino_layers` and look
for sibling category layers.** See
[`revit-polysurface-classification`](./revit-polysurface-classification.md)
Phase 0 for the recon recipe.

## The unifying framework (read this second)

All four proto-skills below are specific applications of the same
underlying workflow:

**The classification ladder** — a tiered reasoning stack where each
tier asks a question the tier above can't answer (Topology → Scene-graph
shape class → Edge-curve geometry → Spatial pattern → Family identity →
Architectural identity).

**The supervised-learning loop** — user labels concrete examples → agent
probes across ladder tiers → agent finds the feature(s) that cleanly
separate the labeled groups → agent applies the discriminator at
population scale → user confirms or relabels → repeat.

The framework is documented in detail at the top of
[`revit-polysurface-classification.md`](./revit-polysurface-classification.md).
Read it before approaching any of the techniques below — they're the
framework's recipes for specific phases (sibling-layer recon, initial
classification, family identity, geometric repair), not standalone
procedures.

## Index

| File | Technique | First used |
|---|---|---|
| [`revit-polysurface-classification.md`](./revit-polysurface-classification.md) | **Framework spine.** Sibling-layer reconnaissance (Phase 0) → split disjoint Revit-exported Brep → profile → classify via the ladder (topology + scene graph + edge-curve) → refine via supervised loop. | 2026-05-12, Crystal Bridges roof (241 pieces) + curtain wall (184 pieces, then APERTURE pivot) |
| [`revit-aperture-curve-to-brep.md`](./revit-aperture-curve-to-brep.md) | **Phase 0 happy path.** When sibling-layer recon finds design-intent curves: build Breps via `Brep.CreatePlanarBreps` for individual panels, and via vertex-pairing of 24-segment polylines for section boundaries. Exact, one-pass, replaces manual cusp work. | 2026-05-12, Crystal Bridges curtain wall (160 panels from 141 curves) |
| [`revit-family-fingerprinting.md`](./revit-family-fingerprinting.md) | **Ladder Tier 2.** Given a known-good exemplar, find all instances of the same Revit family in the document by thickness-invariant fingerprint matching across topological layers. Handles intact, almost-correct, and exploded fragments. | 2026-05-12, Crystal Bridges roof arched ribs (62 family instances found) |
| [`revit-glazing-cusp-reconstruction.md`](./revit-glazing-cusp-reconstruction.md) | ⚠️ **Fallback only.** Reconstruct rectangular glazing panels from "petal"-shaped Breps produced by Revit's failed planar trim. Pairs petals by panel Y-center, then walks a cascading chain inheriting corners from neighbors. **Only use when no sibling design-curve layer exists** — otherwise `revit-aperture-curve-to-brep` is strictly better. | 2026-05-12, Crystal Bridges curtain wall (16 panels via cusp cascade — superseded by APERTURE approach later in same session) |

## Composition: how the four techniques chain

```
[Revit-exported document]
        |
        v
[Phase 0: sibling-layer reconnaissance]   (in revit-polysurface-classification.md)
        |
        +-- design curves FOUND --+
        |                         |
        |                         v
        |             [revit-aperture-curve-to-brep]
        |             — Brep.CreatePlanarBreps for individual outlines
        |             — Vertex-pairing subdivision for section boundaries
        |             — DONE: exact, one-pass, design-intent panels
        |
        +-- design curves MISSING --+
                                    |
                                    v
                    [revit-polysurface-classification Phase 1+]
                    Topological buckets:
                      - 01_Panels_Flat / 02_Trim_Linear / ...
                                    |
                                    v
                    [revit-family-fingerprinting]
                    Semantic family identity across topological layers
                                    |
                          (glazing-specific repair if no curves)
                                    v
                    [revit-glazing-cusp-reconstruction]
                    Cusp-chain cascade — approximate but tractable
```

The three earlier techniques classify on **orthogonal axes**:

- **Topological** asks: "What kind of shape is this piece?" (closed solid vs. linear vs. panel vs. profiled vs. artifact)
- **Family fingerprint** asks: "What Revit family type is this an instance of?" (Plate-Spec-A vs. Plate-Spec-B vs. ...)
- **APERTURE curve-to-Brep** asks: "Has the design already been preserved as polylines on a sibling layer?" If yes, that's the answer to *all* the above questions in one pass.

One Revit family can have instances scattered across multiple topological layers
(some intact = closed-solid, some broken = open-trim). Run the topological pass
first to clean up the geometry, then run family fingerprinting to recover
semantic identity.

The fourth technique, **glazing cusp reconstruction**, is a *geometric repair*
pass that *recreates* missing rectangular panels from petal-shaped failed-op
debris. It's narrower in scope and is now **fallback-only** — prefer
`revit-aperture-curve-to-brep` whenever design curves exist.
