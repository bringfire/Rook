# Revit Polysurface Classification

**Status:** proto-skill (first use 2026-05-12, refined same day with
second independent application + Phase 0 sibling-layer reconnaissance
added after APERTURE-curve discovery).
**Maturity:** 2 successful uses on Crystal Bridges Revit export — roof
layer (241 pieces → 5 topological buckets) and lower curtain-wall layer
(184 pieces → 6 scene-graph-informed buckets with edge-curve refinement
→ then pivoted to APERTURE-curve approach for 160 design-intent
panels). Promote to `/skills` after a third independent use on a
different building **with Phase 0 sibling-layer reconnaissance applied
from the start** (the 2026-05-12 sessions discovered the lesson
mid-flight; we need at least one use that opens with it).

---

## What this proto-skill is actually about

Earlier framings called this a "rule set for classifying Revit export
debris." That framing is too narrow — it makes the work look like running
a fixed classifier. **The actual work is a reasoning workflow that uses
the rule set as a starting point and refines it from user-labeled
examples.** The recipe falls out of the workflow, not the other way
around.

Two structural elements drive everything below:

1. **The classification ladder** — a tiered reasoning stack where each
   tier asks a question the tier above can't answer.
2. **The supervised-learning loop** — the discipline that turns the
   user's labels on concrete examples into population-scale rules.

What makes the agent-Rook pairing more than a script:

- A script applies a *fixed* rule (e.g. `fc=1 → panel`).
- The reasoning agent finds the *right* rule for *this* dataset, validates
  it against user-labeled examples, then scales.

The rest of this doc walks through the framework, then the recipe, then
the worked examples, then the distilled lessons.

---

## Quick-start for a new Claude instance reading this cold

1. **Run Phase 0 (sibling-layer reconnaissance) FIRST.** This is the
   most expensive lesson from 2026-05-12 — design-intent curves are
   often already in the document on a sibling Revit category layer.
   See lesson #12 in the Critical lessons section.
2. Read the framework section (the ladder + the loop). That's the
   load-bearing content.
3. Skim the workflow phases — they're the typical trace of the framework
   running on a Revit-scrapheap polysurface.
4. Read the second worked example (Crystal Bridges curtain wall)
   carefully — its 6 iterations show the supervised loop in action,
   including the APERTURE pivot (iteration 6) that replaced 3 hours of
   manual reconstruction with a 15-minute curve-to-Brep pass.
5. Read the "Critical lessons" section before you act. Most of them are
   mistakes one of us has already made.
6. Default to Tier 1 + Tier 1.5 for first-pass classification. Descend
   to Tier 1.7 (edge-curve) only when the user shows you two pieces
   from the same Tier-1.5 class that they say are different — that's
   the signal you need a finer feature.

---

## When to reach for this

Trigger phrases / situations:

- "Clean up this Revit export"
- "This polysurface has a bunch of disjoint pieces stuck together"
- "Layer up the similar components"
- "Sort these pieces into families"
- A single Brep object with **many faces** (50+) that was exported from
  Revit, Archicad, or similar BIM, where multiple architectural elements
  have been welded into one container shell.

Do **not** use this on:

- A Brep that is supposed to be a single solid (e.g. a hand-modeled
  building mass). Splitting it will dissolve intentional unioning.
- A mesh — this workflow is Brep-only. Mesh equivalents need different
  tooling (`rhino_mesh_repair`, etc.).
- A small polysurface (< ~10 faces) — the bimodal pattern that makes
  this technique work won't be present.

---

## The reasoning framework

### The classification ladder

Classification of post-export Revit geometry is a problem with multiple
nested information levels. Each tier asks a question the preceding tier
can't answer. Sometimes a question gets answered cheaply at a low tier;
sometimes you have to descend.

| Tier | Question | Signals available | Cost | Limits |
|---|---|---|---|---|
| **1 — Topology** | What kind of shape is this? | `fc`, `ec`, `vc`, bbox dims, aspect, `isClosed`, `isManifold`, area | very cheap (one probe per Brep) | conflates families with different identities but similar topology |
| **1.5 — Scene-graph shape class** | What semantic category does this shape belong to in the scene? | `label` (panel / post / bar / slab / block / irregular), `shapeClass` (vertical-planar / thin-vertical / compact / horizontal-slab / thin-horizontal / irregular), `domainLabel` | cheap (one `scene_query` call) | can't distinguish failed-op debris from clean output within a category |
| **1.7 — Edge-curve geometry** | What does the trim / edge structure tell me about how this shape was *produced*? | `nurbs_edges` vs `linear_edges` per outer loop, max chord deviation per edge, `outer_trim_count`, `face_is_surface`, `area_ratio` (face vs underlying surface) | moderate (per-Brep edge walk) | requires probing trim curves explicitly; not in any built-in classifier |
| **1.9 — Spatial pattern** | How does this piece relate to its neighbors? | centroid grid spacing (X/Y/Z), interleaving with other classes, mirrored / paired alignment, arithmetic series detection | moderate (cross-Brep analysis on the population) | inferential; needs 3+ instances to detect a pattern |
| **2 — Family identity** | Which Revit family is this an instance of? | invariant-axis fingerprint, CV across user-confirmed exemplars, Mode A / Mode B / intact mode | expensive (cross-layer scan + user labels) | requires a separate pass — covered in [`revit-family-fingerprinting`](./revit-family-fingerprinting.md) |
| **3 — Architectural identity** | What does this piece DO in the building? | none — user knowledge only | one-shot question | not derivable from geometry; only the user can name it |

**Working principle: descend only when necessary.** Tier 1 + Tier 1.5
together suffice for first-pass classification in most cases. Tier 1.7
comes into play when Tier 1.5 reports overlap between classes you know
should be different (the trigger: user labels two pieces from the same
Tier-1.5 class as different categories). Tier 1.9 is for understanding
architectural *systems* (assemblies, modular grids, mirrored ends), not
individual pieces. Tier 2 is a separate workflow. Tier 3 is the user's.

### The supervised-learning loop

The ladder gives you a feature space. The loop is the discipline for
finding the right discriminator inside that space:

```
user labels concrete examples ("these are X, these are Y")
           │
           ▼
agent probes the labeled groups across ladder tiers
           │
           ▼
agent finds feature(s) that cleanly separate the groups
   (boolean / categorical separators preferred; numeric gaps second)
           │
           ▼
agent applies the discriminator at population scale
           │
           ▼
user confirms — or relabels misses
           │
           ▼
[ separation perfect → scale and commit ]
[ misses found      → repeat with refined examples ]
```

Both Crystal Bridges sessions hit this loop:

- **Roof session** (first use): the rule set itself was the discriminator,
  derived from looking at histograms (Tier 1) + bimodality. No
  user-label round needed because Tier 1 alone separated families.
- **Curtain wall session** (second use): Tier 1.5 gave a first cut, but
  the user labeled 22 intact + 5 mishapen panels that **shared the same
  Tier-1.5 class** (`panel`). The discriminator had to be found at
  Tier 1.7 — edge linearity. Once found, it scaled to all 160 glazing
  pieces and surfaced 7 *additional* misclassifications the user hadn't
  yet labeled.

### How the ladder and the loop compose

The ladder is the **feature space**. The loop is the **discipline** for
choosing the right feature inside it. The recipe (split → profile →
classify → layer → verify → refine) is the typical trace of both
running on a Revit scrapheap. Don't treat the recipe as canonical;
re-derive it each time from the framework.

---

## Workflow (a worked path through the framework)

### Phase 0 — Sibling-layer reconnaissance ⭐ ADDED 2026-05-12

**This is the single most valuable phase, discovered the hard way.**
Revit exports use **category-nested layer names** (`APERTURE$...`,
`G-IMPT`, `A-GENM`, `S-...`, etc.). Design-intent geometry — clean
panel outlines, family-instance blocks, structural members — is often
already present on a sibling category layer while the broken
polysurface debris sits on a `_dwg` import layer.

**The 2026-05-12 session spent ~3 hours doing manual cusp reconstruction
on the broken-petal debris BEFORE discovering that
`APERTURE$APERTURE_PANEL_glass` contained 141 clean design curves
for the same glazing.** Building Breps from those curves produced
**160 exact panels in 15 minutes** vs the 38 approximate panels we'd
spent hours on.

```python
# Run BEFORE anything else
layers = doc.Layers  # walk every layer
for layer in layers:
    if layer.IsDeleted: continue
    fullpath = layer.FullPath
    # Look for Revit category prefixes
    is_category = (
        '$' in fullpath or                       # APERTURE$APERTURE_PANEL_glass
        fullpath.split(':')[-1].startswith(('A-', 'S-', 'G-', 'M-', 'P-', 'E-'))
        # A-* architecture, S-* structure, G-* general, etc.
    )
    if is_category:
        # Count Breps + Curves + InstanceReferences on this layer
        report_layer_contents(layer)
```

**Three flavors of design-intent geometry you might find:**

| Type | Indicator | How to use |
|---|---|---|
| **Closed planar curves** | layer has many polylines, all closed + planar | Pipe to [`revit-aperture-curve-to-brep`](./revit-aperture-curve-to-brep.md) — `Brep.CreatePlanarBreps` builds exact panels |
| **InstanceReference blocks** | layer "0" or similar, with `Link Bridge_...`-style block names | Already organized into Revit families; reorganize into architecturally-named layers, no reconstruction needed |
| **Mixed (curves + Breps)** | both types present | Survey both; curves = design intent, Breps = reference geometry |

**Report sibling-layer findings to the user before proceeding.** Then
choose:

- **Design curves found** → skip Phase 1–6 entirely; use
  [`revit-aperture-curve-to-brep`](./revit-aperture-curve-to-brep.md)
  to build panels from the curves. Fast, exact, zero approximation.
- **Family blocks found, no broken polysurface** → reorganize blocks
  into architecturally-named layers; you're done.
- **No clean sibling data, only the dirty polysurface** → proceed to
  Phase 1+ below. This is the case the rest of this workflow was
  designed for.

**Why this lesson took a session to discover:** the polysurface on the
dirty `_dwg` layer is visually dominant — it's what the user selects.
The clean design curves are usually invisible / hidden behind the
polysurface, on a different layer the user doesn't immediately know
about. **Make checking siblings reflexive — it's cheap (one
`rhino_layers` call) and saves hours.**

### Phase 1 — Inspect the input

```python
# Via rhino_selection / rhino_geometry. Look for:
#   - faceCount   (high = many welded pieces; if < 50, the bimodal pattern
#                  isn't likely; consider whether this skill applies)
#   - isManifold  (yes = clean topology; no = needs repair first)
#   - layer       (target for new child layers)
```

If the object isn't selected yet, ask the user. Don't guess.

### Phase 2 — Split disjoint Breps

```python
rhino_split_disjoint_breps(ids=[selected_id])
# Returns: {split, created, skipped, candidates}
# `created` is your piece count. If it's 1, the Brep wasn't actually
# disjoint and this skill doesn't apply — abort and tell the user.
```

This is **non-destructive in a single-undo sense**: one Ctrl+Z restores
the original. But the original ID is gone after the call, so save it
beforehand if you need it for anything else.

### Phase 3 — Tier 1: topological profile

Walk the new Breps and emit one row per piece with:

- `fc, ec, vc` — face / edge / vertex count
- `area` — total surface area
- `dx, dy, dz` — bbox dims
- `longest, shortest, aspect` (`= longest / shortest`)
- `closed, manifold`
- `bbox_min, bbox_max` — for downstream Z-band and centroid analyses

Save the table to `%TEMP%/rook/<task>_profile.json` so later phases can
re-read without re-querying Rhino.

Compute **summary stats** (min / p25 / median / p75 / max / mean) and
**histograms** for: `fc`, `area`, `longest`, `z_min`, `aspect`.

**The histograms are the load-bearing artifact at this tier.** Show them
to the user. Bimodality signals "Revit family scrapheap with 2–5
distinct families." Continuous distribution signals "hand-modeled or
different export pipeline" — fall back to size-bucket or Z-band rules.

See [`scripts/profile_disjoint_brep.py`](./scripts/profile_disjoint_brep.py)
for a runnable version.

### Phase 3.5 — Tier 1.5: scene-graph consultation

```python
scene_query(layers=["A5_PARTS_dwg"], depth="summary")
```

Returns counts per `shapeClass`. This single call often gives a richer
first-pass classification than topological rules alone, because the scene
graph has already analyzed bbox isotropy, orientation, and dimension
scale.

**Key insight from second-use:** the curtain-wall case had 138 `fc=1`
pieces — a single bucket by Tier 1. The scene graph split those 138 into:

- 45 `panel` (vertical-planar)
- 57 `block` (compact-aspect, fc=1)
- 38 `irregular` (irregular-aspect, fc=1)

That's a **3-way split that Tier 1 cannot see** because Tier 1 only has
face count, which is identical (=1) across all three populations. Tier 1.5
is the right entry tier; Tier 1 is the prerequisite.

**Don't ask for compact-depth scene_query when there are many objects.**
The cross-piece relationship edges balloon the response. Stay at
`depth="summary"` for counts; use `rhino_execute` to walk the document
yourself if you need per-piece scene-graph labels. (Second-use blew the
context window with a compact-depth call before learning this.)

### Phase 4 — Pick the projection (with the user)

**Old framing**: "pick the rule set." **New framing**: the rule set is a
*projection of multidim classification onto a layer tree.* Different
projections suit different cases. Check the histograms + scene-graph
counts first and ask: does my default projection match the bimodality
I see? If the scene graph gives a 6-way split and the default rule
forces a 5-way collapse, that's information loss.

If face count is **bimodal** (e.g. many `fc=1` + many `fc≥6` + nothing
between), classic Revit family export geometry — the default rule set
below will likely work as a first pass.

If face count is **continuous**, fall back to size-bucket or Z-band
classification (probably hand-modeled or a different export pipeline).

#### Default rule set (ordered — order matters)

```python
def classify(p):
    longest = max(p["dx"], p["dy"], p["dz"])

    # 1. Tiny artifacts win first — sliver triangles, degenerate fragments
    if longest < 10:           # mm; raise to ~25 for cm-scale models
        return "05_Artifacts_Tiny"

    # 2. Closed solids next — proper Revit structural members
    if p["closed"]:
        return "04_Solids_Closed"

    # 3. Highly elongated open shells — gutters, ridges, trim strips
    if p["aspect"] >= 50:
        return "02_Trim_Linear"

    # 4. Single-face shells — flat panels, planar trim
    if p["fc"] == 1:
        return "01_Panels_Flat"

    # 5. Everything else — multi-face open shells
    return "03_Profiled_Open"
```

**Why this order?**

- Tiny check **first** because a 3mm sliver might also be high-aspect or
  single-face. Catching it as an artifact prevents misclassification.
- Closed check **before** aspect because a long thin closed solid (e.g.
  a mullion) is correctly a "Solid," not "Trim."
- Aspect **before** face count because a single-face long strip is
  visually trim, not a panel.
- Single-face **before** the catch-all because flat panels have their
  own semantic.

#### The default rule set is a starting point, not a canon

In second-use the default was wrong — the right projection used
scene-graph classes directly:

```
A5_PARTS_dwg::
  01_Panels_Glazing_Intact    (~45)  ← scene 'panel'         — proper glazing
  02_Glazing_Petals           (~95)  ← block+irregular fc=1  — failed-op debris pool
  03_Mullions_Vertical        (~18)  ← scene 'post'          — vertical frames    [later renamed Columns_Vertical]
  04_Beams_Horizontal         ( 2)   ← scene 'bar'           — long horizontal rails
  05_Slabs_Trim               ( 7)   ← scene 'slab'          — horizontal plates
  06_Debris_Multi_Face       (~17)   ← block+irregular fc>1  — multi-face debris  [later renamed Triage_Mode_B]
```

That projection used Tier 1.5 (scene-graph) as the primary classifier
and Tier 1 (`fc`) as a secondary refinement (splitting block+irregular
into petals-vs-multi-face based on face count). The result was richer
than the default would have been.

**Don't pre-collapse just for parity.** If the data shows 6 distinct
categories and a prior session used 5, use 6. The point is to maintain
distinctions until cross-layer fingerprinting validates that some can
collapse.

### Phase 5 — Create child layers + assign

Create child layers under the original layer with **distinguishing
colors** — bright, saturated, mutually distinguishable; not sequential
index-default colors:

| Layer (default scheme) | RGB | Why this color |
|---|---|---|
| `01_Panels_Flat` | `(60, 140, 220)` blue | cool, recedes — surfaces |
| `02_Trim_Linear` | `(240, 140, 40)` orange | warm, distinct from blue |
| `03_Profiled_Open` | `(160, 80, 200)` purple | mid-saturation, separates from blue and orange |
| `04_Solids_Closed` | `(80, 180, 80)` green | structural / "load-bearing" feel |
| `05_Artifacts_Tiny` | `(220, 40, 40)` red | alarming — draws attention to junk |

For the scene-graph-informed projection (second-use), the colors were:

| Layer | RGB | Role |
|---|---|---|
| `01_Panels_Glazing_Intact` | `(60, 140, 220)` blue | clean glazing |
| `02_Glazing_Petals` | `(220, 40, 40)` red | failed-op debris — alarm color (this is what needs repair) |
| `03_Columns_Vertical` | `(80, 180, 80)` green | structural members |
| `04_Beams_Horizontal` | `(40, 170, 200)` cyan | horizontal structure, distinct from green |
| `05_Slabs_Trim` | `(240, 140, 40)` orange | slab / trim |
| `06_Triage_Mode_B` | `(140, 140, 140)` gray | uncertain — needs inspection |

After moving objects, **flip `ColorSource` to `ColorFromLayer`**. Without
this, pieces inherit their pre-split per-object RGB (often a flat Revit
export color) and the layer colors won't show.

**Use a single undo record for the entire bulk move:**

```python
rec = doc.BeginUndoRecord("Classify A5_PARTS_dwg into 6 layers")
try:
    for guid_str, target_layer in assign.items():
        # ... move + set ColorSource ...
finally:
    doc.EndUndoRecord(rec)
```

All 184 attribute modifications become **one Ctrl+Z**. Without this, the
user has to undo each move separately — a usability disaster.

See [`scripts/classify_and_layer.py`](./scripts/classify_and_layer.py)
for a runnable version.

### Phase 6 — Visual verification

```python
rhino_viewport(view="Perspective", displayMode="Shaded", zoomExtents=True, ...)
```

The classification has worked if you can **read the architecture** from
the colors alone — green members supporting blue panels with orange trim
between them, etc. If the colors look randomly distributed, the
projection didn't match the geometry's families and needs tuning.

#### Atomic hide / capture / restore pattern

If you want a clean capture showing only the new child layers (other
doc layers hidden), use the **snapshot-to-disk** sequence — NOT three
separate scripts:

```
1. (Atomic Rhino script)
   - Snapshot current visibility state to disk as JSON
   - THEN hide all non-target layers.
2. (Separate MCP call) rhino_viewport — capture.
3. (Atomic Rhino script)
   - Read snapshot from disk
   - Restore visibility per snapshot.
```

The snapshot must be saved to disk **inside the same script that
performs the hide**, BEFORE the hide. If you snapshot *after*, you've
captured the post-hide state, not the pre-hide state, and recovery
becomes lossy. (Second-use made exactly this mistake and had to
over-restore to all-visible, losing the user's prior hide choices.)

### Phase 7 — Supervised refinement loop

After the first-pass classification, the user may label specific
examples that the classifier got wrong. **Embrace this. Don't avoid
it.** Each labeled example is high-information; the user sees things
no classifier can.

The loop:

1. **User labels examples** — "these N are X, these M are Y." Read via
   `rhino_selection`.
2. **Probe across the ladder** — for each labeled group, compute every
   feature you can at every tier. Save per-piece JSON.
3. **Find the separator** — compare distributions across the groups,
   find features where the groups don't overlap. Cleanest separators
   are **categorical / discrete** with zero overlap. Numeric features
   with a gap between group ranges are second-best.
4. **Verify at population scale** — apply the discriminator to all
   unlabeled pieces. Move any that the discriminator reclassifies.
   Report all moves.
5. **User confirms or escalates** — if the discriminator caught all
   misclassifications, done. If not, get new labels and repeat.

**Worked example (Crystal Bridges curtain wall):** the user labeled
22 intact panels and 5 mishapen pieces, **all on the same Tier-1.5
class (`panel`)**. Probing across the ladder:

| Feature | Tier | Intact (n=22) | Mishapen (n=5) | Separable? |
|---|---|---|---|---|
| `fc` | 1 | 1 | 1 | overlap (useless) |
| `aspect` | 1 | 4–6 | 4–5 | overlap |
| `shapeClass` | 1.5 | panel | panel | **overlap — the killer** |
| **`nurbs_edges`** | **1.7** | **0** | **4** | **PERFECT** |
| **`max_chord_dev`** | **1.7** | **0.00 mm** | **9.07–11.15 mm** | **PERFECT** |
| `linear_edges` | 1.7 | 5–6 | 0 | PERFECT |
| `area_ratio` | 1.7 | 0.857–1.000 | 0.644–0.709 | clean (big gap) |
| `vc` | 1 | 5–6 | 4 | clean |

The separator emerged at Tier 1.7. Scaling the rule
(`nurbs_edges >= 1 → petal`) to all 160 pieces on the two glazing
layers reclassified:

- 5 pieces from intact → petals (matching the user's labels exactly)
- 7 pieces from petals → intact (new findings — the discriminator
  found pieces the user hadn't yet labeled, all of which the user
  could confirm by inspection)

**Generalized lesson**: Tier 1.5 (`shapeClass`) does NOT distinguish
intact-rectangular from mishapen-petal panels. They share shape class.
Tier 1.7 (edge-curve linearity) does. **The user's labels were the
oracle that triggered the descent.**

### Phase 8 — Family identity recovery (pointer, optional)

This classification works on **shape character** (closed vs open, panel
vs linear) and **scene-graph category** (panel vs post vs block vs ...).
It does *not* recover **Revit family identity**. One Revit family can
have instances in multiple topological layers — e.g. some closed-solid,
others as broken open shells — because Revit's export breaks elements
unevenly.

To recover family identity after topological cleanup, use the
[`revit-family-fingerprinting`](./revit-family-fingerprinting.md)
proto-skill. It uses an exemplar + thickness-invariant matching to find
all instances of one family across the topological layers.

---

## Worked examples

### First-use: Crystal Bridges roof (2026-05-12)

**Input:** One Brep on layer `A5_Roof Parts _dwg`, 1363 faces, 3606
edges, 2265 vertices, manifold but not solid.

**Tier-1 split output:** 241 disjoint pieces (62 closed solids, 179 open
shells).

**Tier-1 histograms confirmed bimodality:**

```
Face count:    107 with fc=1, 4 with fc=2-5, 130 with fc=6-20  ← bimodal ✓
Aspect ratio:  67 with <5, 65 with 5-50, 109 with >50          ← bimodal ✓
Longest dim:   24 < 10mm (artifacts), then a cluster 500-1000  ← bimodal ✓
Z-elevation:   166/241 inside a 100mm band                     ← NOT useful
```

**Projection used (default rule set, no Tier 1.5 consultation):**

| Layer | Count | What it picked out (verified visually) |
|---|---|---|
| `01_Panels_Flat` | 73 | flat base panels at the lower edge |
| `02_Trim_Linear` | 45 | horizontal purlins between ribs |
| `03_Profiled_Open` | 37 | curved roof panel surfaces (top caps) |
| `04_Solids_Closed` | 62 | arched structural ribs |
| `05_Artifacts_Tiny` | 24 | sliver fragments to delete |

Zero errors during moves. Each color in the perspective view mapped to
a genuine architectural family — the rules picked out **what was
actually there**, not an arbitrary partition. No supervised refinement
needed; Tier 1 alone was sufficient because the bimodality was sharp
and the families were topologically distinct.

### Second-use: Crystal Bridges curtain wall (2026-05-12)

**Input:** One Brep on layer `A5_PARTS_dwg`, 545 faces, 1548 edges, 891
vertices, manifold but not solid. Bbox ~1198 × 2821 × 512 mm (Y is the
long axis; Z is the short axis — a "long thin enclosure" suggesting a
curtain-wall strip).

**Tier-1 split output:** 184 disjoint pieces (22 closed solids, 162
open shells).

**Tier-1 histograms:**

```
Face count:    138 fc=1, 0 with fc=2-5, 31 with fc>=6  ← bimodal but panel-heavy
Aspect ratio:  126 in 2-5, 31 >= 50                    ← bimodal but mostly low-aspect
Longest dim:   0 < 50mm                                ← no tiny artifacts
Closed:        22 of 184                               ← fewer structural members than roof
```

**Tier-1.5 scene-graph consultation:**

```
panel:        45  (vertical-planar)
block:        65  (compact)        ← Tier 1 saw these all as fc=1
irregular:    47  (irregular)      ← these too
post:         18  (thin-vertical, closed solid)
slab:          7  (horizontal-slab)
bar:           2  (thin-horizontal, closed solid)
```

The scene graph split populations that Tier 1 had merged. The 138 `fc=1`
pieces split into 45 panels + 57 blocks + 38 irregulars. The 22 closed
solids split into 18 posts + 2 bars + 2 slabs (plus a few that landed
elsewhere).

**Projection chosen (informed by scene graph):**

| Layer | Count | Source signal |
|---|---|---|
| `01_Panels_Glazing_Intact` | 45 | `shapeClass = panel` |
| `02_Glazing_Petals` | 95 | `shapeClass ∈ {block, irregular}` AND `fc = 1` |
| `03_Mullions_Vertical` | 18 | `shapeClass = post` |
| `04_Beams_Horizontal` | 2 | `shapeClass = bar` |
| `05_Slabs_Trim` | 7 | `shapeClass = slab` |
| `06_Debris_Multi_Face` | 17 | `shapeClass ∈ {block, irregular}` AND `fc > 1` |

**Refinement iterations:**

- **Iteration 1 — user-corrected naming**: user pointed out that the 18
  "mullions" were architecturally **columns** (2 exterior + 16 interior).
  Renamed `03_Mullions_Vertical` → `03_Columns_Vertical`. The two
  sub-families have 0% CV in bbox dimensions: 24×24×132mm exterior and
  6×6×198mm interior. Subdivision deferred to cross-layer fingerprinting.
- **Iteration 2 — diagnosis of layer 06**: bbox-cluster analysis on the
  17 pieces showed at least 6 distinct families with identical or
  near-identical bbox fingerprints (e.g. 5 instances of 278 × 264 × 177
  in a perfect arithmetic Y-series with 282mm spacing, plus 2-instance
  pairs at 569×216×189, 602×216×197, 840×588×210). The architectural
  reading: these are **structural modules** + **bracket plates**
  arranged in a coupled interleaved-Y pattern, not random debris.
  Renamed `06_Debris_Multi_Face` → `06_Triage_Mode_B` to reflect
  pending inspection, not discard. Subdivision deferred.
- **Iteration 3 — edge-curve discriminator** (described in Phase 7
  above): user labeled 22 intact + 5 mishapen panels, both on the
  same Tier-1.5 class (`panel`). Probed; found edge linearity as the
  perfect separator. Scaled to all 160 glazing pieces. Discriminator
  caught 5 user-labeled petals + 7 unlabeled petals that the user
  confirmed on inspection. Also surfaced an architectural pattern:
  the 7 newly-promoted-to-intact pieces are **mirrored corner-frame
  pairs** (4 pieces) plus 3 corner-cap pieces (3 not 4 — one missing,
  candidate for reconstruction).

- **Iteration 4 — angled-vs-vertical glazing distinction** (described
  via Tier 1.7 in Phase 7): user labeled 62 angled glazing panels.
  Probed across the ladder; **bbox `dz` (Z-extent)** was a perfect
  separator — angled panels had dz 26–49mm, vertical panels had dz
  65–147mm, with a 16mm clean gap. Surprisingly, **face normal Z
  component was NOT separable** (overlapping ranges). The right
  signal was bbox-aspect, not surface normal. Moved 62 pieces to
  sibling sub-layers `01b_Panels_Glazing_Intact_Angled` (3) and
  `02b_Glazing_Petals_Angled` (59), preserving hierarchy for
  reconstruction order (vertical first, angled second using vertical
  as cascade guide).

- **Iteration 5 — manual reconstruction of vertical petals**
  (described via Phase 7 supervised loop): ran the cusp-cascade
  pattern from
  [`revit-glazing-cusp-reconstruction`](./revit-glazing-cusp-reconstruction.md)
  on the vertical petal pairs. Built 32 mass-applied panels + 1 test
  + 6 endpoint panels = 39 manual reconstructions. Endpoint panels
  used extrapolation when top petals had only 1 cusp instead of 2;
  results had ~5mm approximation error at chain ends due to
  triangle-top-petal asymmetry.

- **Iteration 6 — APERTURE discovery (the pivot)** ⭐: user revealed
  that the document contained a sibling category layer
  `APERTURE$APERTURE_PANEL_glass` with **141 closed planar polylines
  representing the entire glazing design**. This had been there the
  whole time; we just never checked sibling layers. Reframing:
  - 130 of the 141 were individual panel outlines (dy ≈ 30–100mm) →
    `Brep.CreatePlanarBreps` produced 138 exact panels in one pass,
    zero failures.
  - 8 were multi-panel-span (dy 100–126mm, chain endpoints) → also
    handled by direct `CreatePlanarBreps`.
  - 3 were section boundaries: 1 floor trace (skipped) + 2 ×
    24-segment polylines each spanning 11 panels (vertex-pairing
    subdivided each into 11 trapezoidal Breps).
  - **Total: 160 design-intent panels.** Built in ~15 minutes vs the
    ~3 hours spent on iteration 5's 39 manual panels.
  - **The lesson:** check sibling Revit category layers FIRST. See
    [`revit-aperture-curve-to-brep`](./revit-aperture-curve-to-brep.md)
    for the worked technique.

**Final state on `A5_PARTS_dwg`:**

| Layer | Count |
|---|---|
| `01_Panels_Glazing_Intact` | 29 |
| `02_Glazing_Petals` | 131 |
| `03_Columns_Vertical` | 18 |
| `04_Beams_Horizontal` | 2 |
| `05_Slabs_Trim` | 7 |
| `06_Triage_Mode_B` | 17 |
| **Total** | **204** |

The total exceeds the 184 from my split because 20 previously-reconstructed
pieces from a prior session were on the parent layer when classification
ran (see Lesson #8 below).

---

## Critical lessons (for future Claude instances)

1. **Show your interpretation before building.**
   Before any irreversible classification move, state in words what you
   think each layer represents and what counts will land in each.
   Cheapest possible guard against acting on a wrong model.

2. **The scene graph is a classification *dimension*, not a step.**
   Querying `scene_query` is a signal source parallel to bbox-profile
   probing — part of the feature space available at every refinement
   iteration. Not a one-shot phase.

3. **Don't pre-collapse families across layers.**
   Layer subdivision based on within-layer bbox clusters is preview,
   not evidence. Cross-layer fingerprinting (the separate proto-skill)
   is what validates whether two same-bbox clusters in different
   topological layers are one family or two. Defer subdivision until
   then.

4. **Scene-graph `panel` ≠ rectangular-intact.**
   This was the load-bearing miss in second-use. Petals that *look*
   panel-like (single planar face, similar bbox) get `shapeClass=panel`
   from the scene graph but have **curved NURBS trim edges** that
   distinguish them from clean rectangles. Always descend to Tier 1.7
   (edge-curve linearity) when the user shows you two pieces from the
   same Tier-1.5 class that they say are different.

5. **Triage layers should be named honestly.**
   "Debris" implies discard; "Triage_Mode_B" implies pending
   inspection. If you don't know what something is yet, the name
   should reflect the uncertainty, not your guess. (Second-use renamed
   `Debris_Multi_Face` → `Triage_Mode_B` after diagnosis showed it
   held 6+ families of real architectural elements.)

6. **The user is the architectural oracle.**
   You cannot know that "mullion" is wrong and "column" is right from
   geometry alone — that's a Tier-3 question only the user can
   answer. When the user labels examples, treat those labels as ground
   truth and work backwards to find the discriminating feature.

7. **Atomic hide / capture / restore requires snapshot-to-disk.**
   The capture is a separate MCP call, so the three-step sequence
   (hide, capture, restore) can't be one Rhino script. Bridge the gap
   by saving the visibility snapshot to disk **inside the same script
   that hides**, BEFORE the hide. Without that snapshot, recovery is
   lossy — only over-restore-to-all-visible works, which loses any
   layers the user had hidden.

8. **Layer state drifts from your in-memory model.**
   When the user works in Rhino between your operations, objects can
   be added to or moved between layers. Don't trust your assignment
   JSON as a substitute for `rhino_objects(layer=...)` queries when
   the user has been active. (Second-use found 22 unknown IDs on
   `01_Panels_Glazing_Intact` that weren't from my split — they were
   prior-session reconstructions the user had placed there.)

9. **Run a single undo record per bulk operation.**
   Wrap any multi-piece move / modify in `doc.BeginUndoRecord(...)` /
   `doc.EndUndoRecord(rec)`. The user gets one Ctrl+Z to revert the
   whole classification. Without it, undo becomes a per-piece slog.

10. **The classification record is data, not the layer tree.**
    The layer tree is a *projection* of multidim classification onto a
    tree structure. Each piece's full record (topology + scene-graph +
    edge-curve + family) lives in a JSON sidecar; the layer is the
    visible name of the projection. When refining, update the sidecar
    first, then re-project.

11. **The supervised-learning loop is the engine; the recipe is the
    trace.** Future Claude instances reading this doc should internalize
    the framework (ladder + loop) before the recipe (split → profile →
    classify → layer → verify → refine). The recipe is what the
    framework looks like when applied to a Revit scrapheap on a typical
    Tuesday; a different geometry source might trace a different path
    through the same framework.

12. **Check sibling Revit category layers FIRST** (Phase 0).
    This is the most expensive lesson from 2026-05-12. Revit exports
    use `$`-nested category names (`APERTURE$APERTURE_PANEL_glass`,
    `G-IMPT`, etc.) and design-intent geometry is *often* already
    present on a sibling layer while the broken polysurface debris
    sits on a `_dwg` import layer. The 2026-05-12 session ran the
    full Phase 1–7 workflow (split → profile → classify → supervised
    refinement → manual cusp cascade) for ~3 hours before discovering
    `APERTURE$APERTURE_PANEL_glass` contained the entire design as
    141 clean polylines. Building Breps from them produced 160 exact
    panels in 15 minutes. **One `rhino_layers` call at the start
    would have skipped most of the work.** See
    [`revit-aperture-curve-to-brep`](./revit-aperture-curve-to-brep.md)
    for what to do when you find the curves.

---

## Known limitations / open questions

0. **Aspect-ratio threshold can split families in half.** Discovered in
   roof first-use: the `02_Trim_Linear` vs `03_Profiled_Open` boundary
   at aspect=50 happens to bisect families whose section depth varies
   parametrically. Family members with thin sections land in Trim,
   members with thick sections land in Profiled — same family, two
   layers. Recoverable via the
   [`revit-family-fingerprinting`](./revit-family-fingerprinting.md)
   pass, but a reminder: **topological buckets are about shape
   character, not family identity.** Tier 1.5 (scene-graph) sometimes
   helps because shape-class is more semantic than aspect-ratio
   thresholds.

1. **Threshold tuning is manual.** The `< 10` artifact threshold
   assumes mm units. A cm or m document will need different numbers.
   A future version should read `doc.ModelUnitSystem` and scale.

2. **Aspect ratio uses bbox, not actual geometry.** A
   curved-but-overall-blocky piece (e.g. a barrel-vault segment) gets
   a low aspect from its bbox even though it's a "panel." For roof
   case this didn't matter because the panels were also single-face,
   but a more profiled panel geometry might need a different signal.

3. **No re-merging.** If the user wants a specific subset re-joined
   (e.g. 62 ribs back into a single solid for downstream booleans),
   that's a manual `Join` step today.

4. **Colors are hard-coded.** They should pull from a project
   `conventions.yaml` if one exists.

5. **Re-running is destructive.** Running this twice on the same
   parent layer creates duplicate child layers if names collide. The
   script guards against duplicate creation but not double-classification
   of objects already moved.

6. **Edge-curve discriminator thresholds are calibrated to one wall.**
   The `max_chord_deviation > 1.0 mm` cutoff was derived from one
   curtain wall where petals had 9–11 mm chord deviation. Other
   failed-op patterns might have different scales. The **qualitative
   rule** (`nurbs_edges > 0 → petal-like; linear_edges == fc_loop →
   intact-like`) should generalize, but numeric thresholds need
   recalibration per project.

7. **No automation for the supervised loop.** Each refinement round
   (label → probe → derive → scale) currently requires the agent to
   handcraft the probe script. A future version could template the
   probe across all Tier-1.7 features automatically when descending
   from 1.5.

8. **Tier 1.9 (spatial pattern) is undertheorized.** The interleaved-Y
   pattern that revealed the spandrel-bracket coupling on
   `06_Triage_Mode_B` was detected ad-hoc. A proper spatial-pattern
   tier would scan centroid grids, detect arithmetic spacing, and
   surface paired / triplet alignment as first-class signals.

9. **The classification record sidecar is not yet a persistent thing.**
   Currently per-piece classification lives in `<task>_profile.json`
   and `<task>_assignment.json`, refined inline. A future version
   should maintain a persistent per-piece record across all sessions
   on a model.

10. **Cross-MCP-call atomicity is a recurring footgun.** Visibility
    state, selection state, and current-layer state all leak across
    MCP boundaries. Snapshot-to-disk is the workaround today; a
    proper fix would be MCP-level transactions or session-scoped
    state recovery.

---

## Promotion checklist

Before this graduates to `.claude/skills/revit-polysurface-classification/`:

- [x] Second independent use on different geometry (Crystal Bridges
      curtain wall, not the roof) confirmed the framework — but the
      *default rule set* needed scene-graph augmentation in that case.
- [x] Phase 0 sibling-layer reconnaissance added after the APERTURE
      discovery (2026-05-12).
- [ ] Third independent use on a different building **opening with
      Phase 0 from the start** (so we validate the recon step in cold
      use, not as a mid-flight discovery).
- [ ] Phase 0 recon templated as a callable check (`find_sibling_design_layers()`)
      that returns layer paths + content counts for sibling categories.
- [ ] Edge-curve discriminator templated as a Tier 1.7 routine that
      runs automatically when the user labels examples within one
      Tier-1.5 class.
- [ ] Thresholds (artifact size, aspect cut, chord deviation) read
      from `doc.ModelUnitSystem` and rescale by unit.
- [ ] Colors read from `.rook/conventions.yaml` if present.
- [ ] Trigger phrases tested with `skill-creator` evaluator.
- [ ] Idempotency guard added (detect "already split" parent layers
      with existing child sublayers).
- [ ] Histograms rendered as text bars in chat output (not just JSON).
- [ ] Atomic snapshot-to-disk pattern templated for hide / capture /
      restore.
- [ ] Single-undo-record wrapper standardized.
- [ ] Layer-state-drift check (`rhino_objects` vs assignment JSON)
      built into refinement-loop entry.
- [ ] Tier 1.9 (spatial pattern) feature library: centroid grid
      detection, arithmetic series detection, mirror/pair alignment.
- [ ] Per-piece classification record persists across sessions as a
      JSON sidecar keyed by Brep ID.
