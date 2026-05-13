# Starting prompt for next Claude — Link Bridge section cleanup

Copy the block below verbatim into a new Claude Code session.

---

I'm continuing a multi-session Revit-export cleanup project. The previous
Claude (2026-05-12) cleaned up the lower curtain wall section on
`A5_PARTS_dwg` AND discovered a transformative pattern mid-session that
changes the recommended workflow. Please read the proto-skill docs **and**
the critical new guidance below before doing anything.

## Proto-skill docs to read (in order)

1. `docs/rook_docs/proto-skills/README.md` — index + the unifying
   framework (classification ladder + supervised-learning loop)
2. `docs/rook_docs/proto-skills/revit-polysurface-classification.md` —
   **the framework spine: 6-tier classification ladder + supervised loop.**
   Rewritten 2026-05-12. This is the load-bearing content for ANY
   Revit-export cleanup. Read carefully.
3. `docs/rook_docs/proto-skills/revit-family-fingerprinting.md` — Tier 2
   pass for recovering Revit family identity across topological layers
4. `docs/rook_docs/proto-skills/revit-glazing-cusp-reconstruction.md` —
   geometric repair for failed-op glazing petals. **Mostly superseded**
   by the APERTURE-first lesson below — still useful as fallback when
   no design curves exist.

## The most important lesson from 2026-05-12 (NOT YET IN THE PROTO-SKILL DOCS — please add it)

> **ALWAYS look for sibling Revit category layers before reconstructing
> anything.** Revit exports use category-nested layer names (`APERTURE$...`,
> `G-IMPT`, `A-GENM`, `S-COLS`, etc.). Design-intent geometry — clean
> panel outlines, family-instance blocks, structural members — is often
> already present on sibling layers while the broken polysurface debris
> sits on a `_dwg` import layer. The 2026-05-12 session spent hours on
> supervised-learning + cusp-cascade petal reconstruction before
> discovering that `APERTURE$APERTURE_PANEL_glass` contained **141 clean
> design curves** that produced exact panel surfaces in one
> `Brep.CreatePlanarBreps` pass.
>
> **FIRST ACTION on any cleanup task: query ALL layers
> (`rhino_layers` or `rhino_execute` walking `doc.Layers`) and look for
> sibling category names to the dirty-import layer.** Report what you
> find before doing anything. If clean design data exists, use it —
> orders of magnitude faster and more accurate than manual
> reconstruction.

The new Phase 0 (before split-disjoint-Breps) should be: **"Sibling-layer
reconnaissance"**. Please add it to the proto-skill doc during your
session.

## Current state of the document

From the 2026-05-12 session, these layers exist and should not be
touched unless your task overlaps:

```
A5_PARTS_dwg::
  01_Panels_Glazing_Intact            1 InstanceReference (Link Bridge_0415 block)
  01_Panels_Glazing_FromAperture     160 Breps (design-intent glazing — vertical + angled)
  02_Glazing_Petals                    0
  03_Columns_Vertical                  0
  04_Beams_Horizontal                  0
  05_Slabs_Trim                        0
  06_Triage_Mode_B                     0
  01b_Panels_Glazing_Intact_Angled     0
  02b_Glazing_Petals_Angled            0
  _TEST_AutoRecon_Vertical             0

APERTURE$APERTURE_PANEL_glass        141 source design curves (untouched)
```

The empty layers + empty test layer can be deleted at some point. The
`01_Panels_Glazing_FromAperture` is the successful result of the prior
session.

## What I have selected now

A new building section — likely a sibling section of what 2026-05-12
cleaned (the Link Bridge connector or another wing) — with **59
objects** spanning three layers. Likely the building's "Link Bridge" arm
based on the block names.

### Layer `A-GENM` (1 Brep — the polysurface candidate)

- 1 polysurface Brep
- Bbox X 4097..5131, Y -3986..-1431, Z 13998..14468
- Dimensions ~1034 × 2555 × 470 mm — similar shape/scale to the
  2026-05-12 curtain wall section (~1198 × 2821 × 512), suggesting
  another curtain-wall stretch
- **This is the "scrapheap" candidate** — analogous to the original
  `A5_PARTS_dwg` polysurface. Probably the broken-Revit-export part
  that may need `rhino_split_disjoint_breps` + classification.
- DO NOT split it until you've checked the sibling layers (see below).

### Layer `G-IMPT` (13 curves — possible design-intent data)

- These are likely **design-intent curves** analogous to APERTURE.
  **Check them first** before any cusp reconstruction.
- One curve has Z=14202 only (flat floor trace — analogous to the WEST
  floor trace we excluded from APERTURE)
- Most others have Z 14154–14400 ranges (panel-scale Z extents)
- 13 is much smaller than the 141 we found in APERTURE — they may be a
  *subset* covering just one part of the section, or *section
  boundaries* covering many panels each, or *isolated reference
  curves*. Probe and classify by Y-extent first (see the
  `revit-polysurface-classification` proto-skill for the
  individual-panel-vs-section-boundary discriminator).

### Layer `0` (45 InstanceReferences — already-clean Revit family blocks)

Three block types, already organized:

- **`Link Bridge_0415 ... FIN COLUMN 1`** — 7 instances (columns)
- **`Link Bridge_0415 ... FIN WALL`** — 8 instances (wall sections)
- **`Link Bridge_0415 ... BRIDGE BEAM-3466750`** — 28 instances (beam type A)
- **`Link Bridge_0415 ... BRIDGE BEAM-3466751`** — 2 instances (beam type B)

The 45 block instances are **already organized into Revit families** —
they don't need cusp-style reconstruction. Likely tasks:

1. Verify they're properly placed (sanity check vs spatial pattern)
2. Move them to architecturally-named child layers (e.g.,
   `LinkBridge::Columns`, `LinkBridge::Walls`, `LinkBridge::Beams_Type_A`,
   `LinkBridge::Beams_Type_B`)
3. Reason about how they relate to the scrapheap on `A-GENM` and
   curves on `G-IMPT`

## How to proceed

1. **Verify connection**: `rhino_ping` returns `pong`. Then read the
   proto-skill docs (start with README, then the
   polysurface-classification rewrite).

2. **Confirm understanding** — tell me back in your own words:
   - The 6-tier classification ladder
   - The supervised-learning loop
   - **The APERTURE-first lesson above** (this is the #1 thing)
   - The other critical lessons in the "Critical guidance" section below

   Don't proceed until I'm satisfied you've internalized the lessons.

3. **Sibling-layer reconnaissance** (Phase 0, NEW): query
   `rhino_layers` and walk the layer tree. Report:
   - All top-level Revit category layers in the doc (anything with `$`
     in the name, or all-caps prefixes like `A-...`, `S-...`, `G-...`)
   - For each, the count of objects on it (Breps / Curves / Blocks)
   - **Are there any sibling layers that might contain design-intent
     data for the Link Bridge section?** Look for layer names containing
     `APERTURE`, `WALL`, `GLAZ`, `LINK`, etc.

4. **Probe the selection** — get the A-GENM Brep's faceCount,
   isManifold, isSolid; classify the 13 G-IMPT curves by Y-extent
   (individual / multi-panel-span / section-boundary / flat-trace);
   describe the spatial pattern of the 45 block instances.

5. **Show your interpretation in words BEFORE acting.** Specifically:
   - What does each layer represent architecturally?
   - What's the cleanup goal? (build Breps from curves? reorganize
     blocks? split + classify the polysurface?)
   - What's the proposed end state?

6. **Stop and ask** before any irreversible operations. The
   2026-05-12 session had many corrections from the user. Build *one*
   test case; capture visually; mass-apply only after explicit go-ahead.

## Critical guidance (cumulative lessons from prior sessions)

These supplement what's in the proto-skill docs. Reference the docs for
detail.

### The classification ladder (in the doc)

- **Tier 1** topology (fc, ec, vc, bbox, aspect, closed/manifold)
- **Tier 1.5** scene graph (`shapeClass`, `domainLabel`, `label` —
  `scene_query`)
- **Tier 1.7** edge-curve geometry (`nurbs_edges` vs `linear_edges`,
  `max_chord_deviation`, `area_ratio`)
- **Tier 1.9** spatial pattern (centroid grid, interleaving, mirroring)
- **Tier 2** family identity (cross-layer fingerprint)
- **Tier 3** architectural identity (user-only)

### The supervised-learning loop (in the doc)

User labels examples → agent probes ladder tiers → finds clean
separator → applies at population scale → user confirms or relabels →
repeat. **The user is the architectural oracle.**

### From the 2026-05-12 session (NOT YET IN THE DOC — please add)

1. **APERTURE-first lesson** (see above — most important).

2. **`Brep.CreatePlanarBreps`** on closed planar curves gives exact
   design-intent panels. Use this in preference to manual cusp
   reconstruction whenever curves are available. In the 2026-05-12
   session: 138 panels built in one pass, zero failures.

3. **Section-boundary subdivision via vertex pairing**: a closed
   planar polyline that spans multiple panels (e.g., a 24-segment
   polyline covering 11 panels) has its corners arranged as 12 LZ + 12
   HZ vertices on the bottom and top edges. Sort each set by Y, then
   pair adjacently: `panel[i] corners = (LZ[i], LZ[i+1], HZ[i+1], HZ[i])`.
   One `Brep.CreateFromCornerPoints` call per panel. **Works perfectly
   for curved curtain walls** (panels are trapezoids, not rectangles).
   This is much cleaner than `Brep.Split` with cutting planes (which
   didn't work in our case).

4. **MidZ-key pairing for petals**: pair top + bottom petals by their
   *shared midZ vertices* (frozenset comparison of `(x_round, y_round)`
   for vertices near the cut-line Z). NOT by Y-centroid binning. The
   midZ vertices are precise across both petals of a pair; Y-centroids
   can be offset at chain endpoints.

5. **Edge-curve linearity is the perfect petal-vs-intact
   discriminator**: intact panels have all-linear edges (max chord
   deviation = 0); petals have all-NURBS curved edges (max chord
   deviation ~10mm). The scene-graph `panel` shape class does NOT
   distinguish them — both get classified as `panel`. **Always descend
   to Tier 1.7 when the user shows you two pieces from the same Tier-1.5
   class that they say are different.**

6. **Atomic snapshot-to-disk for hide/capture/restore**: if you need
   to hide layers for a clean capture, save the visibility snapshot to
   disk *inside the same script that hides* (BEFORE the hide), then
   restore from disk after the capture. Cross-MCP-call state leaks
   otherwise — you'll lose the user's pre-hide visibility state.

7. **Single undo record per bulk operation**: wrap any multi-piece
   move/build in `doc.BeginUndoRecord("description")` /
   `doc.EndUndoRecord(rec)`. One Ctrl+Z reverts the whole batch.

8. **Layer state drifts**: don't trust in-memory assignment JSONs as
   substitutes for `rhino_objects(layer=...)` queries when the user
   has been active. Re-query before acting on stored state.

9. **Use undo, not delete, for your own mistakes** (preserves
   attributes/history; delete loses them).

10. **Don't pre-collapse families** until cross-layer fingerprinting
    has run. Layer subdivision based on within-layer bbox clusters is
    *preview, not evidence.*

11. **Triage layers should be named honestly** (`Triage_Mode_B`, not
    `Debris`) — the name should reflect uncertainty, not your guess.

12. **Don't conflate `A5_PARTS_dwg`-style sections.** Each named
    section is its own cleanup territory. The 2026-05-12 session
    worked on the lower curtain wall; you're working on the Link
    Bridge section. They have different geometry, different design
    intent, possibly different sibling-layer naming.

13. **Don't extrapolate when you can inherit.** Cascading-chain corner
    inheritance from neighbors gives exact results; parallelogram
    extrapolation is ~5mm off on curved walls. Use APERTURE curves
    when available (most accurate), then inheritance (still exact),
    then extrapolation as last resort.

14. **Show your interpretation before building.** Verbal model first,
    code second. Build *one* test case and capture visually before
    mass-applying.

## What success looks like

Depends on what your reconnaissance reveals. Most-likely paths:

- **(a)** `G-IMPT` curves cover the Link Bridge elements → mass-build
  Breps from them on a new non-destructive layer
  (`LinkBridge::Glazing_FromGIMPT` or similar), following the same
  pattern as `01_Panels_Glazing_FromAperture` from 2026-05-12.

- **(b)** There are MORE sibling layers (e.g., `APERTURE$APERTURE_PANEL_glass`
  contains Link Bridge curves too, or there's a separate layer for
  wall outlines) → use those.

- **(c)** Only the polysurface on `A-GENM` has the data → fall back to
  the full polysurface-classification pipeline (split → profile → scene
  graph → classify → supervised refine).

- **(d)** The 45 layer-0 block instances are sufficient on their own
  and the polysurface is just redundant noise → reorganize the blocks
  into architecturally-named layers, archive/ignore the polysurface.

End state: a clean, well-layered Link Bridge section where the
architecture is readable from the layer organization, no broken petal
debris (if any), and design-intent surfaces in place.

## After you finish

Update the proto-skill docs with what you learn:

1. **Add the APERTURE-first lesson** as a new **Phase 0** in
   `revit-polysurface-classification.md`. Position it BEFORE Phase 1
   (split disjoint Breps) — it's the single biggest time-saver
   discovered in 2026-05-12.

2. **Document the `Brep.CreatePlanarBreps` + section-boundary
   subdivision** technique. Could be a new sibling proto-skill
   (`revit-aperture-curve-to-brep.md`) or a section in
   `revit-polysurface-classification.md`. Include the
   24-segment-polyline vertex-pairing approach.

3. **Mark `revit-glazing-cusp-reconstruction`** as "fallback only —
   prefer APERTURE-curve approach when design data is available."

4. **Add any new lessons** you discover this session. The point of
   staging these as proto-skills (vs promoting to `.claude/skills/`) is
   continuous refinement. If you make a new mistake, document it.

Good luck. Be careful, think clearly, **check sibling layers first**,
and ask before you act.
