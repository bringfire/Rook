# Revit APERTURE Curve to Brep

**Status:** proto-skill (first use 2026-05-12)
**Maturity:** 1 successful application on Crystal Bridges curtain wall —
**160 design-intent panels** built from 141 source curves in two passes
(138 from individual curves + 22 from subdividing 2 section boundaries).
Replaced the entire manual cusp-cascade reconstruction approach with
exact, design-correct geometry.

**Prerequisite:** the document contains a sibling Revit category layer
holding clean design-intent **curves** for the elements you want to
reconstruct. The 2026-05-12 example was `APERTURE$APERTURE_PANEL_glass`
containing 141 closed planar polylines for the building's glazing.

---

## Why this proto-skill exists

The earlier sibling proto-skill,
[`revit-glazing-cusp-reconstruction`](./revit-glazing-cusp-reconstruction.md),
manually reconstructs glazing panels from petal-shaped failed-op debris
on the dirty import layer. It works, but it's labor-intensive,
sensitive to chain-endpoint variations, and produces approximate
geometry where extrapolation is required.

In 2026-05-12 we discovered that **the same Revit export already
provided clean design-intent geometry on a sibling category layer**
(`APERTURE$APERTURE_PANEL_glass`). Building Breps from those curves
gave us **exact** panel surfaces in one pass — orders of magnitude
faster and more accurate than manual reconstruction.

The headline rule: **check for sibling design-intent layers before
reaching for cusp reconstruction.** This proto-skill documents how to
build Breps from those curves once you find them.

This skill is **the preferred Phase 0 outcome** of the parent workflow
in [`revit-polysurface-classification`](./revit-polysurface-classification.md)
— if Phase 0's sibling-layer reconnaissance finds design curves, you
end up here. If not, fall back to the cusp-reconstruction approach.

---

## When to reach for this

Trigger phrases / situations:

- "I found the design-intent curves for X on layer Y — build the panels"
- "There's an APERTURE-style sibling layer with clean polylines"
- "Replace these broken petals with the design intent"
- A sibling Revit-category layer (anything with `$` or all-caps prefix
  like `APERTURE-...`, `G-IMPT`, `S-...`) contains closed planar
  polyline curves that match the bbox extents of broken polysurface
  debris on the dirty import layer.

Do **not** use this on:

- Curves that aren't closed and planar — `Brep.CreatePlanarBreps`
  needs both. Open polylines suggest the layer is something other
  than panel outlines (maybe edge dimensions or reference lines).
- Curves spanning multiple panels without sub-curves (use the
  subdivision technique below).
- Curves at floor-level Z only (dy and dx vary, dz=0) — those are
  footprint traces or column outlines, not panel surfaces.

---

## The two insights that make it work

### Insight 1 — `Brep.CreatePlanarBreps` is one call per curve

For any closed planar curve, RhinoCommon's `Brep.CreatePlanarBreps(curve, tol)`
returns a list of planar Brep surfaces filling the curve. For
individual panel outlines this is **one Brep per curve, exact
geometry, zero failures**.

```python
breps = Rhino.Geometry.Brep.CreatePlanarBreps(curve, tol)
for b in breps:
    doc.Objects.AddBrep(b, attrs)
```

In 2026-05-12: 138 panels built from 138 curves in one pass, zero
failures, zero `Brep.CreatePlanarBreps` returns of `None`.

### Insight 2 — Section boundaries need vertex pairing, not Brep splitting

Not every curve on the design layer is an individual panel outline.
Some are **section boundaries** spanning multiple panels — a single
polyline outlining a stretch of N panels without internal mullion
separators. The 2026-05-12 example had 2 × 24-segment polylines, each
covering 11 intact panels in the curtain wall's center section.

The intuitive approach (`Brep.Split` of the section's planar Brep with
cutting planes at each panel boundary) **does not work reliably** — in
2026-05-12 it returned 0 sub-pieces on every cut. The reliable approach:

> A closed planar polyline that wraps N panels has its corners arranged
> as **(N+1) LZ vertices + (N+1) HZ vertices** along the bottom and top
> edges respectively (plus 2 short side-edge segments). Sort each set
> by Y, then pair adjacently: `panel[i] corners = (LZ[i], LZ[i+1], HZ[i+1], HZ[i])`.
> One `Brep.CreateFromCornerPoints` call per panel.

```python
# For a 24-segment closed polyline covering 11 panels:
verts = unique_polyline_vertices(curve)        # → 24 vertices
lz = sorted([v for v in verts if v.Z < midZ], key=lambda v: v.Y)  # 12 vertices
hz = sorted([v for v in verts if v.Z >= midZ], key=lambda v: v.Y) # 12 vertices
for i in range(len(lz) - 1):  # 11 panels
    BL, BR = lz[i], lz[i+1]
    TL, TR = hz[i], hz[i+1]
    brep = Brep.CreateFromCornerPoints(BL, BR, TR, TL, tol)
    add_to_layer(brep)
```

This handles **curved curtain walls correctly** — each adjacent vertex
pair produces a trapezoid panel whose shape matches the wall's local
curvature. No extrapolation. No approximation.

In 2026-05-12: 22 panels built from 2 section boundaries in one pass,
zero failures.

---

## Workflow

### Phase 0 — Confirm sibling-layer reconnaissance found design curves

You should arrive here from Phase 0 of
[`revit-polysurface-classification`](./revit-polysurface-classification.md)
after finding a sibling Revit category layer with closed planar
polylines. If not, run that recon first.

### Phase 1 — Census the curves by Y-extent

Walk every curve on the design layer and classify it:

```python
def classify_curve(c):
    bb = c.GetBoundingBox(True)
    dy = bb.Max.Y - bb.Min.Y
    dz = bb.Max.Z - bb.Min.Z
    if dy < 1 and dz < 1:        return "flat-trace"          # floor outline
    if dy > 500:                  return "section-boundary"    # multi-panel
    if 100 < dy <= 500:           return "multi-panel-span"    # 2–6 panels
    if 30 <= dy <= 100:           return "individual-panel"    # 1 panel
    return "other"
```

**Y-extent thresholds are project-specific.** Calibrate from the
observed panel spacing (typically the dy of the smallest closed
curves). For 2026-05-12 the panel spacing was ~72mm, so individual
panels had dy ≈ 30–100mm.

Report counts to the user. The distribution tells you:
- **Mostly individual panels** → straight `CreatePlanarBreps` pass
- **Many section boundaries** → subdivision needed
- **Many flat-traces / open curves** → the layer isn't pure panel-outline data; treat carefully

### Phase 2 — Build Breps from individual + multi-panel-span curves

```python
SECTION_BOUNDARY_IDS = {...}  # the multi-panel boundaries; skip these
for curve_obj in curves_on_design_layer:
    if curve_obj.Id in SECTION_BOUNDARY_IDS: continue
    geo = curve_obj.Geometry
    if not geo.IsClosed:    continue
    if not geo.IsPlanar(tol): continue
    breps = Brep.CreatePlanarBreps(geo, tol)
    for b in breps:
        add_to_target_layer(b)
```

Wrap in one `BeginUndoRecord` for atomic undo. Place on a
**non-destructive new layer** (e.g. `01_Panels_Glazing_FromAperture`)
for visual verification before merging into the main intact-panel
layer.

### Phase 3 — Subdivide section boundaries via vertex pairing

For each section-boundary curve (dy > 500mm):

```python
def subdivide_section(curve, mid_z):
    # Extract unique vertices from closed polyline
    rc, pl = curve.TryGetPolyline()
    verts = [pl[i] for i in range(pl.Count - 1)]  # closed → skip repeated last
    # Split by Z
    lz = sorted([v for v in verts if v.Z < mid_z], key=lambda v: v.Y)
    hz = sorted([v for v in verts if v.Z >= mid_z], key=lambda v: v.Y)
    if len(lz) != len(hz):
        raise ValueError(f"asymmetric vertex count: {len(lz)} LZ + {len(hz)} HZ")
    # Build N-1 quadrilateral panels
    panels = []
    for i in range(len(lz) - 1):
        BL = Point3d(*lz[i])
        BR = Point3d(*lz[i+1])
        TR = Point3d(*hz[i+1])
        TL = Point3d(*hz[i])
        brep = Brep.CreateFromCornerPoints(BL, BR, TR, TL, tol)
        if brep: panels.append(brep)
    return panels
```

`mid_z` is the cut-line Z value — pick it as the midpoint between the
curve's `bbox.Min.Z` and `bbox.Max.Z`. For 2026-05-12 the section
boundaries had Z=14202..14349, midZ ≈ 14275.

### Phase 4 — Visual verification

Capture a perspective view showing the new panels. The architecture
should be **immediately legible** — clean panel grid with mullion
separators visible. If you see gaps in the grid, you have unsubdivided
section boundaries. If you see overlapping panels, you have duplicate
sources.

Use the **atomic snapshot-to-disk** pattern from
[`revit-polysurface-classification`](./revit-polysurface-classification.md)
Phase 6 if you need to hide non-glazing layers for a clean capture.

### Phase 5 — Commit / consolidate (with user)

After visual sign-off, options for end state:

- **(a) Merge** the new panels into the main intact-panel layer; delete
  the source design curves. Clean single-layer result.
- **(b) Keep separate** — design curves on the source layer, panels on
  the new "FromAperture" layer, original intact-panel layer holds any
  reference geometry (e.g., a Revit block). Maximum auditability.
- **(c) Archive** the petal/broken-export layers to a
  `_ARCHIVE_BrokenExport` parent. The design-intent panels become the
  primary geometry.

User chooses based on auditability vs cleanliness trade-off. The
2026-05-12 session kept everything separate per user preference.

---

## First-use evidence (Crystal Bridges curtain wall, 2026-05-12)

**Discovery moment.** After ~3 hours of manual cusp-cascade
reconstruction work that produced 38 panels (32 mass-applied + 6
endpoint) with extrapolation issues at the chain ends, the user
selected 141 objects on layer `APERTURE$APERTURE_PANEL_glass` and
asked "what are these?" They turned out to be **the entire glazing
design as polyline outlines** — clean, exact, untouched by the failed
planar trim that produced the petal debris on `02_Glazing_Petals`.

**Curve census (141 total):**

| Bucket | Count | Treatment |
|---|---|---|
| `flat-trace` (dy<1, dz<1) | 0 in this case | (would skip) |
| `individual-panel` (30 ≤ dy ≤ 100) | 130 | `CreatePlanarBreps` direct |
| `multi-panel-span` (100 < dy ≤ 500) | 8 | `CreatePlanarBreps` direct (endpoint-wraparound, 1–2 panels each) |
| `section-boundary` (dy > 500) | 3 | 1 floor trace (skip) + 2 × 11-panel boundaries (subdivide) |

**Phase 2 result:** 138 Breps built from 138 closed planar curves. Zero
failures. One pass.

**Phase 3 result:** Each of the 2 × 11-panel section boundaries was a
24-segment closed polyline with 24 unique vertices: 12 LZ (Z=14202)
+ 12 HZ (Z=14349). Vertex pairing produced 11 trapezoidal panels per
section = **22 additional panels**.

**Total: 160 panels** filling the entire curtain wall (vertical + angled
glazing). The architecture became **immediately legible** in the
visual capture — both curved curtain walls with clean panel grids and
the angled-glazing strip sitting above the vertical-glazing strip
exactly as designed.

**Time comparison:**

| Approach | Time spent | Output | Quality |
|---|---|---|---|
| Manual cusp-cascade reconstruction | ~3 hours of supervised work | 38 panels | Approximate at chain ends, manual fixup needed |
| `Brep.CreatePlanarBreps` from APERTURE curves | ~5 minutes | 138 panels | Exact, zero failures |
| Section-boundary vertex pairing | ~10 minutes | 22 more panels | Exact, zero failures |

---

## Known limitations / open questions

1. **Only works when design-intent curves exist.** The sibling-layer
   reconnaissance step is the prerequisite. If Revit exported only the
   broken polysurface and no clean curves, this skill doesn't apply —
   fall back to
   [`revit-glazing-cusp-reconstruction`](./revit-glazing-cusp-reconstruction.md).

2. **Threshold values for curve classification are project-specific.**
   The Y-extent buckets (30–100mm for individual panel, etc.) need
   recalibration per project. Read from `doc.ModelUnitSystem` and scale.

3. **Mid-Z detection for section-boundary subdivision.** Currently uses
   bbox midpoint, which works for symmetric panels. For asymmetric
   panels (e.g., where the cut line isn't at the geometric center)
   this might need refinement.

4. **Vertex pairing assumes (N+1, N+1) LZ/HZ split.** If a section
   boundary has irregular vertex distribution (e.g., extra mid-segment
   vertices), the pairing fails. Detect via `len(lz) != len(hz)` and
   fall back to a manual split-by-Y-cut approach.

5. **Doesn't handle non-planar curves.** Curves on slightly twisted
   walls might fail `IsPlanar(tol)` even though they're "planar enough."
   Increase tolerance or project to best-fit plane before building.

6. **No automatic handling of "open" design curves.** 5 of the 141
   curves in 2026-05-12 were initially flagged as open polylines in
   one probe — turned out to be a probe-state bug; all 141 were
   actually closed. A future version should distinguish "open by
   design" (e.g., guide lines) from "open by tolerance" (closeable).

7. **Doesn't validate against the broken polysurface.** A check that
   each new Brep matches an existing petal cluster's bbox would
   catch design/export mismatches.

---

## Promotion checklist

Before this graduates to `.claude/skills/revit-aperture-curve-to-brep/`:

- [ ] Second independent use on a different Revit-category sibling layer
      (not `APERTURE$APERTURE_PANEL_glass`) — e.g., `G-IMPT` for
      glazing, structural-category layers for beams/columns, etc.
- [ ] Y-extent thresholds read from `doc.ModelUnitSystem` and scale by unit.
- [ ] Mid-Z auto-detection for asymmetric panels.
- [ ] Open-vs-closed curve disambiguation (tolerance-aware).
- [ ] Cross-check against broken-polysurface bboxes for validation.
- [ ] Trigger phrases tested with `skill-creator` evaluator.
- [ ] Atomic snapshot-to-disk pattern templated for visual verification.

---

## Relationship to other proto-skills

```
revit-polysurface-classification (framework spine)
    │
    └─ Phase 0: Sibling-layer reconnaissance
        │
        ├─ design curves FOUND  →  revit-aperture-curve-to-brep (THIS DOC)
        │                          (preferred path — exact, fast)
        │
        └─ design curves MISSING  →  Phase 1+ of polysurface-classification
                                     (split, profile, classify, ...)
                                     │
                                     └─ for glazing: revit-glazing-cusp-reconstruction
                                                     (fallback only)
```
