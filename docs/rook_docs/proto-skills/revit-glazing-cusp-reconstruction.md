# Revit Glazing Cusp Reconstruction

**Status:** proto-skill (first use 2026-05-12) — ⚠️ **fallback only**
**Maturity:** 1 successful application on Crystal Bridges curtain wall —
recovered 16 glazing panels across 2 columns from 34 failed-op petals.
A second attempt in the same session reconstructed 39 vertical panels
manually before discovering the APERTURE-curve approach replaced the
need for manual reconstruction entirely.

---

## ⚠️ Read this before reaching for cusp reconstruction

**This is a fallback skill.** As of 2026-05-12 we discovered that
Revit exports usually include **clean design-intent curves on a
sibling category layer** (e.g., `APERTURE$APERTURE_PANEL_glass`). When
those curves exist, building Breps from them via
[`revit-aperture-curve-to-brep`](./revit-aperture-curve-to-brep.md)
produces **exact** panels in one pass, orders of magnitude faster than
the manual cusp-cascade reconstruction below.

**Before invoking this skill:**

1. Run Phase 0 of
   [`revit-polysurface-classification`](./revit-polysurface-classification.md)
   — sibling-layer reconnaissance. Look for `APERTURE$...`, `G-IMPT`,
   or similar category layers.
2. If design curves are found, use
   [`revit-aperture-curve-to-brep`](./revit-aperture-curve-to-brep.md)
   instead. Skip this skill entirely.
3. **Only fall back to cusp reconstruction below if no design curves
   exist** — i.e., Revit truly exported only the broken polysurface
   without the design-intent boundary curves.

The 2026-05-12 session spent ~3 hours running this skill on a building
section before discovering the APERTURE curves existed. Don't repeat
that mistake.

---

## Prerequisites (when this skill DOES apply)

- The dirty polysurface has been split via
  [`revit-polysurface-classification`](./revit-polysurface-classification.md)
  (so petals are isolated as separate Breps)
- No sibling layer contains design-intent curves for these panels
  (otherwise, use the APERTURE approach above)
- At least 2-4 *intact* glazing panels are available in the same column
  to seed the cascade chain (typically already on `Family_Glazing` from a
  prior reconstruction or imported clean)

---

## When to reach for this

Trigger phrases / situations:

- "These petals should be rectangular glazing panels"
- "The curtain wall got destroyed by Revit's failed planar trim"
- "Reconstruct the panels from the cusps"
- A 2-column-style curtain wall where Revit's planar boolean (or similar)
  failed and left **curved-edge "petals"** instead of clean rectangular
  glazing panels, in a regular vertical chain.

Do **not** use this on:

- A single isolated petal — the reconstruction needs at least the
  neighbor chain or an intact reference panel to source the missing
  corners.
- Geometry where the petals don't tile cleanly into a column (random
  orientations, mixed families, etc.).
- Roof tiles or other panels where the chain isn't a single straight
  column (the cascading-chain logic depends on a linear chain along one
  axis).

---

## The 4 insights that make it work

### Insight 1 — Cusps are signals, not corners

The failed planar operation produces "petals" — Brep faces with **4
vertices, 4 NURBS edges, and ~2 sharp corners**. The sharp corners
("cusps") are where the failed operation *accidentally hit a correct
boundary point* of the design.

**A cusp is a clue to where the rectangular boundary should be — not a
corner of the rectangle by itself.** The actual rectangle requires
combining cusps from *multiple petals*, plus inherited corners from
neighboring panels.

This is the lesson that took me 3 wrong attempts to internalize. Don't
extract cusps and trim each petal's underlying surface to fit its own
cusps — that produces disjoint, mis-aligned rectangles. Each panel's
boundary is a **shared signal across petals + neighbors**.

### Insight 2 — Petal pairs are by panel Y-center, not by cusp coincidence

Each glazing panel is split by the failed op into **2 petals**:
- **TOP petal**: outer cusp at HY_HZ (the panel's top corner on the
  high-Y side), central cusp at LY_midZ (mid-Z on the low-Y edge)
- **BOTTOM petal**: outer cusp at LY_LZ (bottom corner, low-Y side),
  central cusp at HY_midZ (mid-Z on the high-Y edge)

The 2 petals of one panel have **overlapping bbox Y-ranges** (same panel
position) but split Z (one in the top half, one in the bottom).

**To pair them: compute each petal's `panel_y_center` = midpoint of its
2 cusps' Y values, then group leaves whose midpoints are within ~5 mm of
each other.** Two leaves with the same Y midpoint form one panel.

Cusp-coincidence clustering is *wrong* for this — cusps shared between
petals are usually the **boundary points between adjacent panels**, not
within one panel. (When I tried union-finding on shared cusps, my "pair"
at Y=−3423 turned out to be 1 petal from a Y=−3388 panel and 1 from a
Y=−3458 panel, joined by their common grid corner at Y=−3423.)

### Insight 3 — Cascading-chain corner inheritance (not extrapolation)

Each panel's 4 corners are sourced as:

```
BL (LY_LZ) ← own BOTTOM petal's outer cusp
TR (HY_HZ) ← own TOP petal's outer cusp
TL (LY_HZ) ← TR of the panel directly BELOW (cascade from below)
BR (HY_LZ) ← BL of the panel directly ABOVE (cascade from above)
```

For an intact neighbor panel (already a clean rectangle): query its
geometry corners directly.

For a chain-built neighbor panel: use the values you already computed
when you built that panel.

**This is exact, not approximate.** No extrapolation needed mid-chain.
Each panel inherits 2 corners from real cusp data in adjacent leaves
(or real corner data in adjacent intact panels). The "TL = TR of below"
identity is structural: those 2 names refer to the same point at the
shared boundary's HZ corner.

### Insight 4 — Panels are trapezoids, not parallelograms

On a curved curtain wall, each panel's LY edge and HY edge have
**different lengths** because the wall's local curvature differs along Y.
For Crystal Bridges, consecutive panels differed by ~5-7mm in LY-edge
length (chain delta).

This is why "TL = BL + (top_petal_central_cusp - BL) * (panel_height / cut_height)"
(parallelogram extrapolation, which I tried) is **wrong by ~5mm** —
parallelogram assumes LY_height = HY_height, which is true only for
flat-wall panels.

**Don't extrapolate when you can inherit.** Use the chain.

---

## Workflow

### Phase 0 — Confirm preconditions

1. Topological classification done (petals on `01_Panels_Flat`)
2. At least 1 intact glazing panel exists at one end of the column
   (typically purple `03_Profiled_Open` panels or `Family_Glazing` from a
   prior reconstruction)
3. The user has selected at least 1 example pair of petals so you can
   verify the algorithm before mass-applying

### Phase 1 — Detect failed-op leaves

Scan all Breps for the signature:
- 1 planar face
- 4 NURBS edges, 4 vertices
- `face_is_surface_subset = false` (trim curves ≠ underlying surface boundary)
- Exactly 2 sharp corners (vertex tangent deviation > 30°)

Some end-of-chain variants don't match exactly (e.g. **3-vertex triangle
petals** at the building edge, or 4-vertex petals with only 1 detectable
cusp due to softer corners). Handle these as a separate "end-pair"
class (see Phase 5).

### Phase 2 — Pair by panel Y-center

For each detected petal:
- `panel_y_center` = midpoint of its 2 cusps' Y values
- `petal_kind` = TOP if max cusp Z > 14320 (above cut line); BOTTOM if
  min cusp Z < 14280 (below cut line)

Group petals where `panel_y_center` values are within ~5 mm of each
other. Each group should have **1 TOP + 1 BOTTOM** = one panel.

### Phase 3 — Identify columns

Group panels by Y-range buckets — each column is a continuous run of
panels at similar X positions. For Crystal Bridges: right column at
Y ∈ (−3700, −3300), left column at Y ∈ (−2400, −1700).

### Phase 4 — Cascade chain reconstruction

For each column (top to bottom):
1. Start with the intact panel at the top (or first complete pair)
2. For each successive complete pair, build using the cascade rule:
   - own BL = bottom petal outer
   - own TR = top petal outer
   - inherited BR = (panel above's BL corner)
   - inherited TL = (panel below's TR corner)
3. Build `Brep.CreateFromCornerPoints(BL, BR, TR, TL)`

### Phase 5 — Endpoint extrapolation (only at true chain ends)

If a complete pair has *no* neighbor on one side (chain endpoint at the
extreme top or bottom of a column), extrapolate the missing corner using
**linear continuation of the chain delta**:

```python
# For missing TL (no panel below):
last_panel = chain[-1]   # most extreme, has TL inherited from neighbor
prev_panel = chain[-2]
delta = last_panel.TL - prev_panel.TL
endpoint.TL = last_panel.TL + delta
```

Compute the chain delta **per column** (the two columns mirror each
other, so a global average cancels to zero — I made this mistake on my
first attempt).

### Phase 6 — End-pair shapes at the building edge

At the absolute building-edge end-pairs, the topology changes:

- **The BOTTOM petal contains BOTH BL and BR** (two LZ vertices). The
  building wall terminates, so the petal spans the entire bottom edge
  including the side-edge corner.
- **The TOP petal may be a 3-vertex triangle** if the building edge
  cuts the panel diagonally.
- **The HY_HZ / LY_HZ corner may be missing from both petals' vertices**
  — you have to extrapolate it from the shared midZ vertex along the
  shared LY/HY edge, targeting an HZ value from the chain delta
  projection.

For end-pairs:
- BL, BR = both directly from BOTTOM petal's two LZ vertices
- TR (HY_HZ) = highest-Z vertex of TOP petal (if available) — for
  building-edge panels this might be displaced way outward along Y
- TL (LY_HZ) = extrapolate from shared LY-edge midZ cusp, targeting
  the chain-projected HZ value

---

## First-use evidence (Crystal Bridges, 2026-05-12)

**Inputs:**
- Topological pass had produced ~73 panels on `01_Panels_Flat`
- 28 of those were detected as failed-op petals by the standard
  signature; 6 more were end-pair variants the user pointed out
- 4 intact glazing panels on `Family_Glazing` (2 original purple + 2
  earlier-reconstructed)

**Output (after 4 failed attempts and ~5 rounds of user correction):**
- **16 reconstructed panels** total, in 2 columns
- 10 chain-cascade panels (BL/TR from own petals, BR/TL from neighbors)
- 3 endpoint panels (one corner extrapolated via chain delta)
- 3 building-edge end-pairs (non-standard topology, shared-edge extrapolation)
- Trapezoid edge lengths progressed smoothly across both columns
  (right column LY edges: 161.72 → 167.14 → 173.13 → 179.65 → 186.33 → 192.69)

**Math verification on user's selected pair (Y=−3315):**
- Own TR = `(736.43, −3280.50, 14356.55)` (top petal outer cusp)
- Inherited BR = `(763.80, −3277.85, 14202.05)` (Family_Glazing panel
  above's BL — distance to actual point: **0.0014 mm**, basically zero)
- Inherited TL = `(743.02, −3352.74, 14361.27)` (panel below's top
  petal outer cusp — user-verified as the *exact* correct point)
- Own BL = `(771.20, −3349.67, 14202.05)` (bottom petal outer cusp)

The chain inheritance produced the exact correct corners with no
extrapolation error in the middle of the chain.

---

## The 4 mistakes I made (and what they taught me)

### Mistake 1 — Per-petal trim of the underlying surface

I treated each petal as containing its own clean rectangle, extracted
the cusps' UV coordinates on the underlying NURBS surface, and trimmed
to that sub-rectangle.

**Result:** 4 isolated rectangles of different sizes, none aligned with
the curtain grid or each other. The user described it as "a weird
disjointed patchwork."

**Lesson:** Cusps are signals on a shared boundary network across
panels, not anchors of independent rectangles.

### Mistake 2 — Cusp-coincidence clustering

I built a union-find graph where 2 leaves were "connected" if they
shared a cusp location, and called each connected component a "panel
pair."

**Result:** Clusters that actually contained 1 petal from one panel + 1
petal from an *adjacent* panel, joined by their shared corner cusp at
the grid intersection.

**Lesson:** Pair leaves by `panel_y_center` (midpoint of cusp Y values),
not by cusp sharing. Cusps between panels are at boundaries, not within
panels.

### Mistake 3 — Parallelogram extrapolation

I assumed `TL.Z = TR.Z` (top corners at the same height) and computed
TL via `BL + (LY_midZ_cusp − BL) × (panel_height / cut_height)`.

**Result:** TL position was ~5 mm off from the actual cusp that should
sit there (the panel below's TR). The user pointed this out by drawing
two points and noting they should be coincident but were 4.7 mm apart.

**Lesson:** On a curved wall, panels are trapezoids — the LY and HY
edges have different lengths. Inherit corners from the chain instead of
extrapolating.

### Mistake 4 — Average chain delta across both mirrored columns

For endpoint extrapolation, I computed the chain's LY-edge length delta
as an average over all built panels.

**Result:** Average came out to *zero* because the two columns mirror
each other (one grows, the other shrinks). My extrapolation used zero
delta, so TL ended up too far from the chain pattern.

**Lesson:** Compute chain delta *per column*, never across mirrored
columns. The chain pattern is a local property.

---

## Known limitations / open questions

1. **End-pair detection isn't automated.** The 6 building-edge petals
   in this case had relaxed signatures (triangle, single-cusp, etc.) and
   my standard scanner missed them. The user had to manually identify
   them. A future version should detect end-pairs by their bbox sitting
   *outside* the regular chain spacing.

2. **End-pair reconstruction is approximate.** When the HY_HZ corner is
   missing from both shared petals, extrapolation through the shared
   midZ vertex requires a target HZ value, which I get from the chain
   delta projection — accurate to ~5-10 mm but not exact.

3. **Tolerance tuning.** `panel_y_center` tolerance of 5 mm worked for
   Crystal Bridges. Tighter (2 mm) split obvious pairs; looser (8 mm)
   would risk merging unrelated panels. Project-specific.

4. **No automated columns split.** I hardcoded Y-range buckets for the
   2 columns. A future version should auto-cluster by X spread.

5. **The cut-line Z value (~14298) is hardcoded.** Real Revit failed-op
   cuts could be at any Z. Should detect from the petal central cusps'
   Z mode.

6. **No support for >2 columns** (only L+R curtain walls). A multi-bay
   building would need column grouping by both X and Y bounds.

---

## Promotion checklist

Before this graduates to `.claude/skills/revit-glazing-cusp-reconstruction/`:

- [ ] Second independent use on a different curtain wall
- [ ] End-pair auto-detection (relaxed signature scan)
- [ ] Column auto-clustering (no hardcoded Y bounds)
- [ ] Cut-line Z auto-detection
- [ ] Better endpoint extrapolation (per-column chain delta, automated)
- [ ] Visual verification step built into the workflow
- [ ] Trigger phrases tested with `skill-creator` evaluator
