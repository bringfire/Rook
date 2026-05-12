# Revit Family Fingerprinting

**Status:** proto-skill (first use 2026-05-12)
**Maturity:** 1 successful application on Crystal Bridges roof — found 62
family instances (29 intact + 33 broken) from a single exemplar.
Promote to `/skills` after a second independent use.

**Prerequisite:** ideally runs after the
[`revit-polysurface-classification`](./revit-polysurface-classification.md)
proto-skill — that one cleans up geometry by *shape character*; this one
recovers *family identity* on top of it. They classify on orthogonal axes
and compose cleanly.

---

## When to reach for this

Trigger phrases / situations:

- "Find all the elements that are the same as this one"
- "These four pieces are supposed to be the same family — find the rest"
- "I have one good copy of an element and a bunch of broken versions
  elsewhere in the model — group them"
- "Recover the Revit family identity from this dirty export"
- The user has a **known-good exemplar** selected (one closed solid or one
  near-complete shell that represents the family they want to find), and
  asks for "all the others like this."

Do **not** use this on:

- Hand-modeled geometry that doesn't come from a parametric family — the
  thickness-invariant assumption fails.
- A document where the user hasn't yet identified an exemplar. The whole
  technique pivots on knowing what one good instance looks like.
- Looking for "similarity" in a fuzzy / aesthetic sense (e.g. "find
  everything that *looks* roof-like"). This is a strict geometric match,
  not a visual one.

---

## The two insights that make it work

### Insight 1 — One bbox dimension is the family invariant. *Which* one is data-driven.

Revit families are parametric. Some dimensions are locked by the family
definition; others vary per instance. After export, the locked dimensions
show up as **bbox dimensions with near-zero variance** across all instances
of the family — the family's fingerprint axis.

**Which axis is the invariant depends on the family type:**

| Family type | Locked dim | Varying dims | Invariant axis |
|---|---|---|---|
| Profile-extrusion (plate, mullion, rebar) | section profile | length, height | **smallest** bbox dim (thickness) |
| Span-fixed (beam spanning a fixed bay) | span length | section width, depth | **largest** bbox dim (length) |
| Tile / panel family | section thickness AND footprint | rotation, position | **smallest + median** bbox dims |
| Component (mixer, bracket, fixture) | full envelope locked | nothing meaningful | all three dims (the entire envelope) |

**Don't assume which dim is the invariant.** Always *derive* it from the
user's example set: compute the coefficient of variation per dim across
the examples and pick the smallest.

```python
def find_invariant_axis(example_dims_sorted):
    # example_dims_sorted: list of (long, mid, min) tuples, one per example
    by_axis = {
        "long_dim": [d[0] for d in example_dims_sorted],
        "mid_dim":  [d[1] for d in example_dims_sorted],
        "min_dim":  [d[2] for d in example_dims_sorted],
    }
    def cv(vals):
        m = sum(vals)/len(vals)
        if m < 1e-6: return 0
        sd = statistics.pstdev(vals)
        return sd / m
    return min(by_axis.keys(), key=lambda k: cv(by_axis[k]))
```

With 2-4 user-confirmed examples this is usually decisive: the invariant
axis has CV < 1%, the varying axes have CV > 5%.

### Insight 2 — Brokenness manifests as a *larger* bbox, not a different one

When Revit exports a family instance correctly, you get one closed solid
whose bbox matches the design intent.

When Revit exports it **almost correctly** (one missing cap face), you
still get one Brep — open this time — but the bbox is essentially
identical to the closed version. We call this **Mode B**.

When Revit exports it **catastrophically**, the side surfaces fly outward
past where they should sit. You get multiple loose shells, and their
combined bbox is *bigger* than the design intent. We call this **Mode A**.

So the brokenness modes sort cleanly:

| Mode | Symptoms | Detection signal |
|---|---|---|
| Intact closed | One closed Brep, correct bbox | `is_solid=True` AND envelope matches exemplar |
| **Mode B** — Intact with hole | One open Brep, correct bbox | `is_solid=False` AND envelope matches exemplar |
| **Mode A** — Exploded fragments | Multiple shells, inflated bbox | thickness matches AND envelope larger than exemplar |
| Orphan surfaces | Single planar face, no shell | `fc=1` AND smallest_dim does NOT match family thickness |

---

## Workflow

### Phase 0 — User picks examples (plural)

Ask the user to select **2-4 examples** of the family they want to find.
Two minimum, because we need to derive the invariant axis from variance.
Single-example fingerprinting forces an assumption about which dim is
invariant — and that assumption is wrong about half the time
(see Insight 1).

Mix the examples deliberately:

- At least one **clean** instance (closed solid if available)
- One or two **broken / variant** instances (different topological layer
  is fine — that's actually informative, see below)

The broken ones don't degrade the fingerprint as long as their *invariant
dim* still matches. They DO contaminate the envelope tolerance — so we
also use them to estimate the *spread* of the varying dims, which sets
the tolerance for the wide scan.

**Why mixed examples matter:** if the topological classifier (the prior
proto-skill) split the family across different layers (e.g. some on
`02_Trim_Linear`, some on `03_Profiled_Open`), the user's selection mix
reveals that immediately. A "single layer" exemplar would hide it.

### Phase 1 — Compute the exemplar fingerprint

```python
bb = exemplar.GetBoundingBox(True)
dims = sorted([dx, dy, dz], reverse=True)   # (long, mid, thickness)
fingerprint = {
    "long_dim":   dims[0],
    "mid_dim":    dims[1],
    "thickness":  dims[2],     # this is the family invariant
    "face_count": exemplar.Faces.Count,
    "is_solid":   exemplar.IsSolid,
}
```

### Phase 2 — Wide scan (find ALL instances regardless of size)

Iterate every Brep in the search universe. For each piece, classify into
one of four buckets:

```python
def classify_vs_exemplar(piece, fp):
    bb = piece.GetBoundingBox(True)
    dims = sorted([dx, dy, dz], reverse=True)
    long_d, mid_d, thick = dims

    # Filter 1: must match family thickness (the invariant)
    if not within_rel(thick, fp["thickness"], 0.20):
        return "not_family"

    # Filter 2: must be meaningfully large (skip tiny scraps)
    if long_d < 50:
        return "not_family"

    # Now sort into intact / Mode B / Mode A
    envelope_match = (
        within_rel(long_d, fp["long_dim"], 0.25)
        and within_rel(mid_d, fp["mid_dim"], 0.25)
    )

    if piece.IsSolid and envelope_match:
        return "intact_closed_exemplar_size"
    if piece.IsSolid and not envelope_match:
        return "intact_closed_different_size"   # parametric variant
    if not piece.IsSolid and envelope_match:
        return "mode_b_intact_with_hole"
    return "mode_a_thickness_only"
```

### Phase 3 — Sanity-check via size distribution

For all hits combined, bucket their middle-dim values into uniform width
bins (25mm worked for Crystal Bridges) and print the histogram.

A **monotonic distribution** (each successive bucket has roughly more or
fewer instances than the last, in a smooth trend) means: yes, this is a
parametric family series. A **chaotic distribution** means: your fingerprint
is too loose and matched unrelated families.

If the distribution is monotonic, proceed.
If chaotic, tighten the thickness tolerance and re-run.

### Phase 4 — Visualize before acting

**Always** isolate the hits and capture a perspective view before doing
anything irreversible. Hide every other object, zoom-extents, capture.

If the hits form a coherent spatial pattern (e.g. a row of arches, a grid
of mullions, a stack of plates), the family ID is correct. If they're
scattered randomly across the model, your fingerprint is matching noise.

### Phase 5 — Decide treatment per mode

```python
# Intact closed -- leave alone, just tag with family ID
# Intact closed different size -- same, parametric variant
# Mode B intact-with-hole -- try CapPlanarHoles to recover the closed form
# Mode A thickness-only -- inspect manually; might be more parametric
#                          variants, or might be exploded fragments
```

For Mode A specifically, the user must visually confirm whether the
matches are legitimate parametric variants (smooth size distribution +
spatial coherence) or exploded fragments (chaotic distribution + spatial
randomness). The technique can't disambiguate these two automatically.

### Phase 6 — Move to family-named layers (optional, with user)

Once family identity is confirmed, the natural action is a layer reshuffle:

```
A5_Roof Parts _dwg::
  Family_ArchRib_Small/        # exemplar's size variant
  Family_ArchRib_All_Sizes/    # all 62 hits
  ...
```

**Important:** this *replaces* the topological classification from
`revit-polysurface-classification`, or sits alongside it (sub-layers).
Discuss with the user which they want before moving anything.

---

## Why this composes with topological classification — and why it must

The prior proto-skill ([`revit-polysurface-classification`](./revit-polysurface-classification.md))
uses an **aspect-ratio threshold** (default 50) to separate "linear trim"
from "profiled open shell." That threshold is a topological heuristic.
It does *not* respect family identity.

Concrete example from the Crystal Bridges second sweep:

```
Long-beam family — 9 instances, all sharing long_dim ≈ 2241mm:
  4 of them had thin sections (12–16mm) -> aspect ratio 141–187 -> 02_Trim_Linear
  5 of them had thick sections (57–69mm) -> aspect ratio  32–39  -> 03_Profiled_Open
```

The topological pass tore one family in half because the family has
**varying section depth** but constant span length. The aspect-ratio
threshold sat right in the middle of the family's section-depth range.

**This is structural, not bad luck.** Topology cares about shape character.
Family identity is independent of shape character — the same family can
be intact (closed solid), almost-intact (open shell), or fragmented
(multiple shells). Topological cleanup organizes *shapes*; family
fingerprinting organizes *identities*. You need both.

The composition order matters too: do **topology first** to get the
geometry into well-defined buckets, then **family fingerprinting** to
heal cross-bucket family fragmentation. Going in the other order means
your fingerprint scan has to wade through all 241 raw pieces including
artifacts and orphan surfaces, which dilutes the signal.

---

## First-use evidence (Crystal Bridges, 2026-05-12)

**Inputs:**

- User selection: 3 open polysurfaces + 1 closed solid (all on layer
  `A5_Roof Parts _dwg::02_Trim_Linear` and `::04_Solids_Closed`)
- The 1 closed solid was the exemplar
- The 3 open ones included: 1 Mode B (almost-correct) + 2 rogue side
  surfaces that flew far beyond the intended element bounds

**Exemplar fingerprint:**

```
long_dim:  685.3 mm    (parametric)
mid_dim:   96.2  mm    (parametric)
thickness: 7.4   mm    <-- family invariant
```

**Strict envelope match (exemplar size only):**

- 5 intact closed solids matched within ±20%
- 4 more closed solids matched within ±35% (smaller variants)
- 2 Mode B open shells found (one of them was selected by the user)
- 31 Mode A "thickness matches, envelope larger" pieces — initially
  suspected to be exploded fragments

**Wide scan (thickness-only, all sizes):**

- **62 total family members** across the document
- 29 intact closed solids
- 33 open shells (Mode B + Mode A combined)

**Sanity check — size distribution by middle-dim (25mm buckets):**

```
 50: 2     100: 3     150: 5     200: 6     250: 12
 75: 3     125: 4     175: 5     225: 9     275: 13
```

Beautifully monotonic. Confirms parametric family series.

**Visual confirmation:** isolating the 38 strict matches in a perspective
view revealed **two coherent arches at opposite ends of the lens-shaped
barrel-vault roof** — symmetric end-arches of the structural system.
Their colors (assigned by the prior topological pass) showed green for
closed solids, orange for Mode A — and the spatial pattern was exactly
what one would predict for a symmetric tapered roof.

**What about the user's 3 broken pieces from the selection?**

- 1 of them (`b5898818`) was correctly identified as **Mode B**
  (intact-with-hole) — its dims (704, 114, 7.2) fell within the envelope
  tolerance. This was the "missing a tiny cap" case.
- The other 2 (`e9e96add`, `4e0aef20`) had `min_dim = 4.6mm`, which
  doesn't match the family thickness of 7.4mm. They were classified as
  **not_family** — confirming they are the "side surfaces that flew way
  past the open shell" the user described, sitting in the orphan-surface
  graveyard waiting for manual cleanup.

The technique correctly distinguished "missing-cap" from "exploded-side"
without being told the difference.

---

## Second-use evidence (Crystal Bridges, same session, 2026-05-12)

After the arched-rib family was complete, the user selected 4 more pieces:
2 from `02_Trim_Linear` and 2 from `03_Profiled_Open`, and said
*"these are all the same family — why are they classified differently?"*

This case is what motivated the "derive the invariant" upgrade. The user's
4 examples showed:

```
Per-axis spread (CV) across the 4 examples:
  long_dim:  0.13%   <- invariant! (all four span ~2241mm in Y)
  mid_dim:   9.44%
  min_dim:  65.21%   <- huge variation (thin sections to thick sections)
```

**Original assumption (smallest dim invariant) would have failed completely.**
The smallest-dim spread is 65%, which is dominated by varying section
depth. The actual invariant is the *largest* dim: span length.

Applying the derived fingerprint (`long_dim ≈ 2241 ± 5%`) found **9 family
instances** total (the user's 4 plus 5 more). Centroid X positions revealed
the geometry: a parallel array of long beams running along Y, with **gaps
of `68.7, 78.2, 84.7, 86.1, 85.4, 84.4, 77.7, 68.1` mm** along X —
symmetric and slightly compressed at the ends, consistent with beams
arranged along a curved arch projecting onto a flat axis. Visual
verification confirmed.

**Why the topological pass split this family in half:** the aspect-ratio
threshold (50) for `02_Trim_Linear` vs `03_Profiled_Open` happened to sit
inside the family's section-depth range. Thin-section instances (aspect
141-187) went to Trim; thick-section instances (aspect 32-39) went to
Profiled. The family is one thing; the topology pass split it because
shape character ≠ family identity.

This is the case that drove the **"Why this composes with topological
classification"** section above.

---

## Known limitations / open questions

1. **Invariant tolerance is the load-bearing knob.** If user examples show
   <1% spread on the invariant axis (as in both Crystal Bridges cases —
   thickness CV was 0.4%, span-length CV was 0.13%), a ±5% wide-scan
   tolerance is plenty tight. If user examples show 2-5% spread,
   ±10–15% is appropriate. Match wide-scan tolerance to a small multiple
   of observed example spread, not a fixed default.

2. **Mode A vs. parametric variant is ambiguous from the score alone.**
   A piece with thickness matching but envelope 2x larger could be either
   a much-larger family instance or a fragment from a different family.
   Disambiguation requires either: (a) visual inspection by the user, or
   (b) checking spatial coherence — a parametric series clusters
   spatially, exploded fragments don't necessarily.

3. **Multi-axis parametric families break the fingerprint.** If a family
   parameterizes its section profile as well as its length/height (e.g. a
   variable-thickness mullion), there's no single invariant dimension.
   Need to extend to multi-signature fingerprinting (volume, surface area,
   topology).

4. **Curved-section families confuse the bbox approach.** A C-channel or
   tube has a non-axis-aligned cross-section; its smallest bbox dim isn't
   the section thickness, it's the bounding-box width of the curved
   section as projected. Could fix by using oriented bbox or principal
   component analysis instead of axis-aligned bbox.

5. **Mode B auto-repair is non-trivial.** `Brep.CapPlanarHoles(tol)` only
   closes *planar* holes. It fails on curved family sections — e.g. an
   arched rib whose missing end-cap is itself a curved profile. First
   use of this skill hit exactly this case: both Mode B pieces returned
   `None` from CapPlanarHoles because the missing surface was curved.
   The pragmatic answer is to *tag* Mode B pieces with a user-string
   marker (`rook_family_repair_needed = "mode_b_curved_cap"`) and route
   them to manual cleanup. A future repair pipeline would: (a) extract
   the naked edge loop, (b) try `Brep.Patch` with neighboring face
   tangency, (c) fall back to `NetworkSrf` from the edge loop, (d)
   surface to user as last resort.

6. **Doesn't use rotation.** If two instances of the same family are
   rotated differently, their bbox dimensions might not align — sorted
   dims help, but only for orthogonal rotations. Curved or tilted
   members might evade detection.

---

## Promotion checklist

Before this graduates to `.claude/skills/revit-family-fingerprinting/`:

- [ ] Second independent use on a different family (not arched ribs)
      confirms the thickness-invariant signature generalizes
- [ ] Mode B auto-repair (`CapPlanarHoles`) wired up and tested
- [ ] Distinction between "Mode A exploded" and "parametric variant"
      automated via spatial-coherence test
- [ ] Oriented-bbox fallback for non-axis-aligned families
- [ ] Trigger phrases tested with `skill-creator` evaluator
- [ ] Volume + surface-area fingerprints added as secondary signals
      for families where thickness is ambiguous
