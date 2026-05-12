# Revit Polysurface Classification

**Status:** proto-skill (first use 2026-05-12)
**Maturity:** 1 successful application on Crystal Bridges roof export.
Promote to `/skills` after a second independent use confirms the rule set
generalizes.

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
- A small polysurface (< ~10 faces) — the bimodal pattern that makes this
  technique work won't be present.

---

## The insight that makes it work

> Revit exports each **family-element type** with a consistent geometric
> signature. When a single Brep contains many disconnected shells, the
> shells almost always sort into **2–5 sharply distinct families** by
> face count, closed/open state, and aspect ratio — because each family
> in Revit (panel, mullion, rib, gutter, bracket) has its own modeling
> convention.

The distribution is **bimodal**, not continuous. That's what lets a small
set of simple rules produce a clean classification — there are no edge
cases sitting on the boundary, because the boundary is empty.

**Always profile before classifying.** The rules below are a starting
point that worked once; the actual thresholds should be picked from the
histogram of *your* file.

---

## Workflow

### Phase 0 — Inspect the input

```python
# Via rhino_selection / rhino_geometry
# Look for:
#   - faceCount   (high = many welded pieces; if < 50, this skill is overkill)
#   - isManifold  (yes = clean topology; no = needs repair first)
#   - layer       (target for new child layers)
```

If the object isn't selected yet, ask the user to select it. Don't guess.

### Phase 1 — Split disjoint Breps

```python
rhino_split_disjoint_breps(ids=[selected_id])
# Returns: {split, created, skipped, candidates}
# `created` is your piece count. If it's 1, the Brep wasn't actually
# disjoint and this skill doesn't apply — abort and tell the user.
```

This is **non-destructive** in a single sense: one undo restores the
original. But the original ID is gone after the call, so save it first
if you need it for anything else.

### Phase 2 — Profile every piece

Run a script that walks the new Breps and emits one row per piece with:

- `fc` — face count
- `ec` — edge count
- `area` — total surface area (sum of face areas)
- `dx, dy, dz` — bbox dimensions
- `aspect` — `max(dims) / min(dims)` (use `9999` for `min < 1e-6`)
- `closed` — `Brep.IsSolid`
- `manifold` — `Brep.IsManifold`
- `bbox_min, bbox_max` — for downstream Z-band rules

Save the table to `%TEMP%/rook/<task>_profile.json` so later phases can
re-read without re-querying Rhino.

Then compute **summary stats** (min/p25/median/p75/max/mean) plus a
**histogram** for: `fc`, `area`, `longest_dim`, `z_min`, `aspect`.

The histograms are the load-bearing artifact. Show them to the user.

See [`scripts/profile_disjoint_brep.py`](./scripts/profile_disjoint_brep.py)
for a runnable version.

### Phase 3 — Pick the rule set (with the user)

Look at the histograms. If face count is bimodal (e.g. many `fc=1` + many
`fc≥6` + almost nothing between), you have classic Revit family export
geometry. The default rule set below will likely work.

If face count looks **continuous** instead of bimodal, the geometry is
probably hand-modeled or from a different export pipeline — fall back to
size-bucket or Z-band classification.

### Default rule set (ordered — order matters)

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
  single-face. Catching it as an artifact prevents misclassification into
  trim or panels.
- Closed check **before** aspect because a long thin closed solid
  (e.g. a mullion) is correctly a "Solid," not "Trim."
- Aspect **before** face count because a single-face long strip is
  visually trim, not a panel.
- Single-face **before** the catch-all because flat panels have their own
  semantic.

### Phase 4 — Create child layers + assign

Create child layers under the original layer with **distinguishing colors**
(not just sequential index-default colors — bright, saturated, mutually
distinguishable):

| Layer | RGB | Why this color |
|---|---|---|
| `01_Panels_Flat` | `(60, 140, 220)` blue | cool, recedes — surfaces |
| `02_Trim_Linear` | `(240, 140, 40)` orange | warm, distinct from blue |
| `03_Profiled_Open` | `(160, 80, 200)` purple | mid-saturation, separates from blue and orange |
| `04_Solids_Closed` | `(80, 180, 80)` green | structural / "load-bearing" feel |
| `05_Artifacts_Tiny` | `(220, 40, 40)` red | alarming — draws attention to junk |

After moving objects, **flip `ColorSource` to `ColorFromLayer`**. Without
this, pieces inherit their pre-split color (often a flat per-object RGB
from the Revit export) and the layer colors won't show in the viewport.

See [`scripts/classify_and_layer.py`](./scripts/classify_and_layer.py)
for a runnable version.

### Phase 5 — Verify visually

```python
rhino_viewport(view="Perspective", displayMode="Shaded", zoomExtents=True, ...)
```

The classification has worked if you can **read the architecture** from
the colors alone — green ribs supporting purple panels with orange purlins
between them, etc. If the colors look randomly distributed, the rule set
didn't match the geometry's families and needs tuning.

### Phase 6 — Semantic rename (optional, with user)

Once the families are visible, rename layers from geometric (`Solids_Closed`)
to architectural (`Arched_Ribs`, `Curved_Panels`, `Purlins`, `Base_Panels`).
This is **always** a user-driven step — the agent doesn't know what the
building's vocabulary is.

### Phase 7 — Family identity recovery (optional, sibling technique)

Note that this classification works on **shape character** (closed vs open,
panel vs linear). It does *not* recover **Revit family identity**. One
Revit family can have instances in multiple topological layers — e.g. some
of its instances exported as closed solids, others as broken open shells —
because Revit's export breaks elements unevenly.

To recover family identity *after* topological cleanup, use the
[`revit-family-fingerprinting`](./revit-family-fingerprinting.md)
proto-skill. It uses an exemplar + thickness-invariant matching to find
all instances of one family across the topological layers.

---

## First-use evidence (Crystal Bridges, 2026-05-12)

**Input:** One Brep on layer `A5_Roof Parts _dwg`, 1363 faces, 3606 edges,
2265 vertices, manifold but not solid.

**Split output:** 241 disjoint pieces (62 closed solids, 179 open shells).

**Histograms confirmed bimodality:**

```
Face count:    107 with fc=1, 4 with fc=2-5, 130 with fc=6-20  ← bimodal ✓
Aspect ratio:  67 with <5, 65 with 5-50, 109 with >50          ← bimodal ✓
Longest dim:   24 < 10mm (artifacts), then a cluster 500-1000  ← bimodal ✓
Z-elevation:   166/241 inside a 100mm band                     ← NOT useful
```

**Classification output:**

| Layer | Count | What it picked out (verified visually) |
|---|---|---|
| `01_Panels_Flat` | 73 | flat base panels at the lower edge |
| `02_Trim_Linear` | 45 | horizontal purlins between ribs |
| `03_Profiled_Open` | 37 | curved roof panel surfaces (top caps) |
| `04_Solids_Closed` | 62 | arched structural ribs |
| `05_Artifacts_Tiny` | 24 | sliver fragments to delete |

Zero errors during moves. Each color in the perspective view mapped to a
genuine architectural family — the rules picked out **what was actually
there**, not an arbitrary partition.

---

## Known limitations / open questions

0. **Aspect-ratio threshold can split families in half.** Discovered in
   second-use evidence on the same Crystal Bridges roof: the
   `02_Trim_Linear` vs `03_Profiled_Open` boundary at aspect=50 happens
   to bisect families whose section depth varies parametrically. Family
   members with thin sections land in Trim, members with thick sections
   land in Profiled — same family, two layers. This is recoverable via
   the [`revit-family-fingerprinting`](./revit-family-fingerprinting.md)
   pass downstream, but it's a reminder: **topological buckets are about
   shape character, not family identity.** If you only run the
   topological pass, family identity stays hidden in the layer mix.

1. **Threshold tuning is manual.** The `< 10` artifact threshold assumes
   mm units. A cm or m document will need different numbers. A future
   version should read `doc.ModelUnitSystem` and scale.

2. **Aspect ratio uses bbox, not actual geometry.** A curved-but-overall-
   blocky piece (e.g. a barrel-vault segment) gets a low aspect from its
   bbox even though it's a "panel." For Crystal Bridges this didn't matter
   because the panels were also single-face, but a more profiled panel
   geometry might need a different signal.

3. **No re-merging.** If the user wants a specific subset re-joined (e.g.
   the 62 ribs back into a single solid for downstream booleans), that's a
   manual `Join` step today.

4. **Colors are hard-coded.** They should pull from a project
   `conventions.yaml` if one exists.

5. **Re-running is destructive.** Running this twice on the same parent
   layer will create duplicate child layers if names collide. The script
   already guards against duplicate creation, but doesn't guard against
   double-classification of objects already moved.

---

## Promotion checklist

Before this graduates to `.claude/skills/revit-polysurface-classification/`:

- [ ] Second independent use on different geometry (not a Crystal Bridges
      roof) confirms the rule set
- [ ] Thresholds read from `doc.ModelUnitSystem`
- [ ] Colors read from `.rook/conventions.yaml` if present
- [ ] Trigger phrases tested with `skill-creator` evaluator
- [ ] Idempotency guard added (detect "already split" parent layers)
- [ ] Histograms rendered as text bars in the chat output (not just JSON)
