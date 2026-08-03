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

## How Architecture Studio factors in

AS does three distinct kinds of work here, and they are **not** equally load-bearing.
Naming which is which prevents treating the whole suite as one undifferentiated
dependency.

### 1. Research — essential

Site, environmental, mobility, demographics, history, zoning, occupancy, programming,
and later materials and EPD data. This produces the **findings** that the Chirp `planner`
converts into parameters.

This leg is not substitutable. Without it, "parameters reasoned from researched data"
degrades to "parameters invented by a language model." The entire trustworthiness claim
rests on findings that carry a real source.

### 2. Project record — the underrated spine

`PROJECT.md`, `decisions/`, `/as:project record-decision`, meeting minutes, site visit
reports. Every AS skill reads `PROJECT.md` on entry and offers updates on exit.

This matters more than it first appears, because the workflow is **asynchronous and spans
returns**. Something must hold state between sessions. The division is clean:

| Layer | Holds | Mechanism |
|---|---|---|
| Parameter-level *why* | Why this value | Chirp Reasoning pin |
| Project-level *why* | Why this decision, and what it superseded | AS `decisions/` + `PROJECT.md` |

Neither covers the whole surface alone. Together they do.

### 3. Delivery — valuable, substitutable

`/as:slide-deck-generator`, `as:brand-manager`, `/as:color-palette-generator`,
`/as:resize-images`. Real polish on a genuine design system, and the deck leg is
well-specified — but a deck could be produced by other means. Treat as high-value
convenience, not as foundation.

### Constraint

AS's zoning and due-diligence skills are **NYC-only**. The research legs that are not
geographically bound — environmental, mobility, demographics, programming, occupancy,
materials, sustainability — work anywhere. The first build should not assume the
regulatory leg is available.

---

## What AS provides that becomes geometry

Inventoried from the skills and their bundled data. The distribution is lopsided and
that shapes the architecture.

### Tier 1 — true coordinate geometry

| Source | Payload | Becomes |
|---|---|---|
| `/as:zoning-analysis-nyc` → `## Envelope Data` | `lot_poly`, real polygon from MapPLUTO ArcGIS | Site boundary → surface |
| same | `volumes[]` with `inset`, `h_bottom`, `h_top` | Offset + extrude per volume |
| same | `setbacks` {front, rear, lateral1, lateral2} | Per-edge offsets (needs edge classification) |
| same | `height_cap` | Horizontal plane at Z |
| environmental / mobility / PLUTO | site lat/lon | Rhino EarthAnchorPoint → native sun |

**That is the entire list, and it is NYC-only.**

### Tier 2 — dimensional parameters that drive geometry

| Source | Payload | Becomes |
|---|---|---|
| `/as:environmental-analysis` | Solar altitude at solstices/equinoxes, azimuth at sunrise/sunset | Sun vectors → shadow studies, solar envelopes, shading angles |
| same | Elevation, slope | Ground datum and slope plane — **a number, not a DEM** |
| `workplace-programmer/data/space-types.json` | `default_sf` + `capacity` per room type | Room footprints → test-fit packing |
| `program.json` | RSF, five-zone splits, seat counts, room schedule | Floor-plate allocation, stacking |
| `occupancy-calculator/data/occupancy-load-factors.json` | `load_factor_sf`, `area_type`, IBC 1004.5 refs | Occupant load from measured area; egress widths |
| FF&E product CSV cols L–Q | `W`, `D`, `H`, `Seat H`, `Unit` (in/cm/mm) | Bounding boxes → Rhino block definitions |
| zoning | Max FAR, Max Floor Area | Target volume to test achieved massing against |

### Tier 3 — guidance that shapes geometry without being geometry

Zoning district and use groups, landmark status, transit and walkability, demographics,
neighbourhood character, EPD/GWP. These attach to geometry as attributes and decisions,
never as shape.

### Gaps

- **No terrain mesh.** Environmental yields a number and prose, not a DEM.
- **No context building footprints.** See the Context model section — that comes from
  NYC Open Data directly, not from AS.
- **No street or right-of-way geometry.** Mobility analysis is entirely textual.
- **Outside NYC there is no lot boundary at all.**

### The two-channel principle

AS is rich in dimensional parameters and nearly barren in coordinate geometry. That
*validates* the planner-centric architecture rather than undermining it — findings become
parameters precisely because findings are almost never geometry.

But it means there are **two channels into the definition, not one**:

1. **Findings channel** — numbers and facts, through the Chirp planner, reasoned over.
2. **Geometry channel** — coordinates, bypassing the planner entirely, landing as data.

> **Never route coordinates through a language model.** Numbers *about* geometry go
> through reasoning; geometry itself goes around it. An LLM re-emitting forty coordinate
> pairs is wasteful, unverifiable, and a corruption risk.

`Finding.value` is a `str` and must stay one. `lot_poly` does not belong in the findings
contract and must not be forced into it.

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

## Site setup: units, datum, georeferencing

Three of these are expensive to reverse once a model and a definition exist.

### Units: Feet

Not a preference — a traceability requirement. NYC zoning is entirely in feet, AS's
`Envelope Data` declares `"unit": "ft"`, and NYC building-footprint `height_roof` and
`ground_elevation` are **also already in feet**. Every source agrees, so no conversion
appears anywhere in the chain.

The practical consequence: with document units in feet, `rhino_measure_area` returns
**square feet natively**, so a FAR check is a direct comparison against the zoning
`Max Floor Area` with no conversion step to get wrong.

Plain **Feet**, not US Survey Feet — the site is translated to the origin (below), so the
2 ppm distinction is immaterial at building scale.

**Absolute tolerance: 0.001 ft** (~1/64"). Tight enough for massing booleans, loose
enough that offset and extrude do not fail on near-coincident vertices.

### Georeferencing: EarthAnchorPoint

Source data arrives in two projections — MapPLUTO lot polygons in **WGS84**, the DOITT 3D
model in **EPSG:2263** (NAD83 NY State Plane Long Island, US foot). State Plane places NYC
at roughly 980,000 ft easting; modelling a building a million units from the origin
destroys floating-point precision and produces shading artifacts, unreliable meshing, and
booleans that fail for no visible reason.

Set Rhino's **EarthAnchorPoint** to the site lat/lon. This yields three things at once:

- correct georeferencing, stored durably in the `.3dm`;
- model coordinates that stay **near the origin** — solving the State Plane problem
  natively rather than by manual translation;
- **Rhino's sun uses the same anchor**, so the solar altitude and azimuth findings from
  `/as:environmental-analysis` become working shadow studies with no extra plumbing.

Over a site-scale AOI the local-tangent-plane approximation is negligible.

> **Not currently available.** Grep of the C# companion and the native plugin found **no
> EarthAnchorPoint handling anywhere in Rook**. This is the right approach but it is a
> route that must be built. See the Context model slice.

### Z datum: the zoning base plane

Zoning heights are measured from the base plane or curb level, not from sea level. Set
**Z=0 to the zoning base plane** so a 120 ft cap sits at Z=120 and the model reads
directly against the regulation. Determining the base plane is a zoning question and
belongs in the findings, not in a modelling assumption.

Context buildings carry their own `ground_elevation` and are seated at true grade relative
to that datum, not flattened to Z=0.

### Where units break

- **FF&E is in inches or millimetres**, and the product schema says *"Keep manufacturer's
  original — do not convert."* Block creation needs an explicit conversion at that
  boundary.
- **Grasshopper has no units of its own** and silently inherits the document's. Opening
  the definition in a metric document produces wrong geometry with no warning. Record the
  expected unit system in the definition.

---

## Context model

### The two sources

| | NYC Building Footprints (`5zhs-2jue`) | DOITT 3-D Building Model |
|---|---|---|
| Attributes | `bin`, `doitt_id`, `base_bbl`, `mappluto_bbl`, `name`, `height_roof`, `ground_elevation`, `construction_year`, `feature_code`, `geom_source`, `last_edited_date`, `shape_area` | **`BIN`, `DOITT_ID`, `SOURCE_ID`** — the entire schema |
| Geometry | MultiPolygon, WGS84 | Solids, EPSG:2263 |
| Detail | flat extrusion from attributes | CityGML LOD 1/1.5 hybrid, ~100 iconic at LOD 2; roof/facade/ground components differentiated |
| Vintage | **updated daily** | 2014 survey, published 2016-04-18, **one-time capture, never updated** |
| Accuracy | — | XY ±1.25 ft, Z ±1.6 ft at 95% |
| Obtainable | Socrata, keyless, verified | direct zips, verified live: Multipatch 251 MB, CityGML 894 MB, DGN 744 MB |

The DCP `.3dm` conversion (by Community District, enriched with lots/streets/parks/rail)
is a *derivative* of the DOITT model. Its download page is now a redirect stub to a
JavaScript search app and could not be scripted; the **upstream DOITT source is fully
open** and is the dependable path.

### They are the same feature class — join on BIN

From the DOITT capture notes:

> "3-D models are based on the **planimetrics building footprint feature class**… the
> elevation attributes (ground elevation and roof height) from the building footprint
> feature class were used for building base and top data collection **to ensure vertical
> consistency**."

The 3D solids were compiled *from* the footprints using the *same* `ground_elevation` and
`height_roof` values. Both carry `BIN` and `DOITT_ID`.

**This is a key join, not a spatial match.** No centroid-in-polygon, no fuzzy
correspondence, no tolerance on identity.

### Reconciliation

```
for each BIN in current footprints ∩ AOI:
    in model?      compare (ground_elevation + height_roof) vs solid bbox max Z
                   → MATCH within tolerance | STALE beyond
    not in model?  → MISSING, extrude from footprint
for each BIN in model but not in current footprints:
                   → GHOST, demolished
```

**Tolerance must be tight, not generous.** Because the two were built for vertical
consistency from the same numbers, divergence is *signal*, not noise — on the order of the
stated ±1.6 ft Z accuracy plus documented LOD effects. Over-generous thresholds would
silently trade surveyed geometry for flat extrusions, which is strictly worse.

Documented legitimate divergences: LOD 2 iconic buildings have "some differences in
elevation for the 3D roof infrastructure"; LOD 1.5 merges roofs less than 8 ft apart to
the highest point; parapets, chimneys, spindles and antennae are excluded throughout; and
`height_roof` is the *highest* point of roof.

**Self-check:** `construction_year > 2014` should predict MISSING exactly. If the key join
and the construction-year signal disagree, the method is broken rather than the data — a
validation a geometry-only approach could not provide.

### Provenance on context

Every context object carries user text recording its verdict, source and vintage — 2014
survey geometry versus current extrusion. The context model becomes auditable in the same
way the spec argues parameters should be: one can look at a render and know which parts of
the skyline are surveyed and which are approximated. Same principle, one layer out.

### Degradation

Without the DOITT model, pure footprint extrusion — verified working. With it, surveyed
detail where still valid. Nothing blocks on the download.

### Verified in Rhino (2026-08-02)

Built live against the selected site. Results, not projections:

| Check | Result |
|---|---|
| EarthAnchorPoint round-trip | 1000 ft east → Δlon 0.00362° (276,250 ft/deg at this latitude); 1000 ft north → Δlat 0.00274° (364,700 ft/deg). Correct. |
| Model coordinate range | ±1,900 ft of origin. State Plane precision problem never arises. |
| **Lot polygon area** | **24,912.4 SF measured vs 24,959 SF PLUTO-declared — 0.19% delta** |
| Footprints → curves | 614 features → 617 curves (3 inner rings), 0 skipped |
| Curves → solids | 608 solids, 0 failed, 6 skipped for height ≤ 0.5 ft |
| Ground elevations | −6 to +54 ft, seated at true grade |
| Heights | 9 / 57 / 1,039 ft (min / median / max) |
| Post-2014 detection | **40 of 608, of which 11 exceed 400 ft**, including the tallest |

**The area check is the one to keep permanently.** Two independent sources — a transformed
WGS84 polygon and a PLUTO attribute — agreeing to 0.19% means the projection chain is
right, not merely plausible. It costs one call and it fails loudly.

**Post-2014 detection needs no download.** The `construction_year` signal alone identifies
what a 2014 model cannot contain, which is the MISSING class of the reconciliation. At this
site that is essentially the entire west-side tower cluster.

### Gotcha: ring winding inverts extrusion

`Extrusion.Create` follows the curve plane's normal. NYC footprint ring winding produces a
**−Z normal**, so a naive extrude builds the city downward — first attempt returned a
massing bbox of Z [−1011, 51].

This is a property of the source data, not an implementation slip. **Any footprint →
extrusion path needs an explicit orientation guard**: test the resulting bbox against the
base elevation and mirror about the base plane if it hangs below. This sits alongside the
winding self-correction AS already documents for `insetPolygon`, and for the same reason —
winding varies by data source and cannot be assumed.

### Known minor gap

Inner rings currently extrude as solid plugs rather than voids. Two buildings affected in
the test AOI; cosmetic at context scale, wrong in principle. Proper handling needs a planar
Brep with holes before extrusion.

---

## Reconciliation: tested against the real DOITT model (2026-08-02)

The 762 MB DGN was downloaded, the covering tile isolated, imported into Rhino, and
correlated against the current footprints. Results below **correct two claims made earlier
in this spec.**

### Tile indexing — do not import the city

The zip contains 20 DGN tiles (`DA1`–`DA20`) plus a `DeliveryArea` shapefile index. The
`.prj` confirms **EPSG:2263** verbatim: Lambert Conformal Conic, GRS80, `False_Easting`
984250, `Central_Meridian` −74.0, standard parallels 40.6667/41.0333, `Foot_US`.

Implementing the LCC forward projection from those parameters (no dependency needed) puts
the site at **E 985,170 / N 215,104**, which selects **`DA12_3D_Buildings.dgn` — 39.6 MB of
762 MB.** Always resolve the tile before importing.

### CORRECTION 1 — BIN does not survive the DGN transport

**The key join described above is impossible via DGN.** The import produced **610,987
objects** across exactly three layers — `Building_FootPrint`, `Building_RoofTop`,
`Building_Facade` — with **no object names and no user strings whatsoever**.

The underlying datasets do share `BIN`/`DOITT_ID`; this particular *transport* discards
them. Multipatch (ESRI FGDB) and CityGML carry attributes and would preserve the key, but
neither imports into Rhino natively. So the trade is explicit:

| Format | Rhino-native | Carries BIN |
|---|---|---|
| DGN | **yes** (`import_DGN` plugin) | **no** |
| Multipatch / CityGML | no (needs GDAL/FME) | yes |

### CORRECTION 2 — it is wireframe, not solids

All 610,987 objects are **Curves**. The model is roof/facade/footprint *outlines*, not
closed volumes. Solids must be constructed. Usefully, `Building_RoofTop` curves sit at true
roof elevation, which is what the height comparison needs.

### The correct match: containment + max Z

There are **3,887 rooftop curves for 614 buildings** — LOD 1.5 carries roughly six roof
polygons each. Nearest-centroid matching therefore latches onto small appendages and
produced **~31% false divergence**.

The correct algorithm respects the metadata's own definition — `height_roof` is the
*highest point of roof*:

> for each footprint polygon, take **max Z over all rooftop curves whose centroid lies
> inside it**, and compare against `ground_elevation + height_roof`.

### Results — vertical consistency confirmed

| Measure | Result |
|---|---|
| Footprints in AOI | 614 |
| Matched by containment | 585 |
| **Median height difference** | **0.00 ft** |
| Within ±1.6 ft (stated Z accuracy) | 398 / 585 — 68% |
| Within 8 ft (documented LOD 1.5 roof merge) | 446 / 585 — 76% |
| Diverging > 20 ft → **STALE** | 46 — 7.9% |
| Unmatched → **MISSING** | 29 |
| **of which post-2014** | **21 of 29** |

**A median difference of exactly 0.00 ft proves the "built for vertical consistency" claim
directly.** Where a building is unchanged, the 2014 survey roof elevation and the current
attribute height agree exactly — because they came from the same numbers. This validates
the tight-tolerance decision: divergence really is signal.

**The self-check holds.** 21 of 29 unmatched buildings are confirmed post-2014, exactly as
predicted. The remaining 8 warrant investigation — demolish-and-rebuild, footprint
revision, or containment failure on awkward geometry.

---

## Solids from the DGN, and correlation during import

CORRECTION 2 above ("wireframe, not solids") was itself imprecise. Diagnosed properly:

### The curves are face boundaries, not wireframe

Every curve is **closed and planar** — sampled near the site, 21/21 footprints, 87/87
roofs, 547/547 facades, and every facade is a **5-vertex quad**. MicroStation Shape
elements are semantically planar faces; Rhino's importer renders them as their boundary
loops. This is a complete B-rep delivered as face boundaries.

### Why they cannot be joined into solids

Joining one building's 11 faces leaves **18 naked edges, identical at tolerance 0.001,
0.01, 0.1, 0.5 and 1.0**. Tolerance-invariance proves faces are *absent*, not gapped: a
13-vertex footprint (12 edges) carried only 8 facades.

The cause is in the capture method. **Aerial stereo compilation records only what is
visible from above, so party walls between attached buildings were never compiled.** In
Manhattan row fabric this is pervasive. The model is inherently open where buildings abut
and no tolerance will ever close it.

### The reconstruction that works

Do not join their faces. Use what the DGN uniquely holds — **roof outlines at true
elevation** — and generate the rest:

> for each building, extrude every roof polygon down to the base elevation, then
> boolean-union the resulting prisms.

Measured: **21 footprints → 21 closed solids, 0 failures, 0.7 s**, including 11
multi-roof buildings (max 20 roof polygons) resolving into correct stepped massing with
setbacks and rooftop bulkheads — articulation the attribute-extrusion path cannot produce.

### Correlation: containment, not polygon pairing

A tempting assumption — that the two footprint sets are identical geometry because they
share a feature class — is **false at polygon level**. Measured in the AOI: **1,021 DGN
footprint polygons for 614 NYC buildings**, centroid p50 3.04 ft apart, **zero pairs within
0.5 ft**.

The DGN decomposes buildings into *components* (wings, stair bulkheads, towers — the
metadata captures structures over 10 ft on a side separately). There is no 1:1 pairing to
find.

**Use the NYC footprint polygon as a spatial key envelope.** It carries BIN and is the
authoritative whole-building outline; every DGN component whose centroid falls inside it
belongs to that BIN. This absorbs the 1,021→614 decomposition naturally and is measured at
**585/614**, with 21 of the 29 misses confirmed post-2014.

### The pipeline

1. Fetch NYC footprints for the AOI — BIN, `height_roof`, `ground_elevation`,
   `construction_year`.
2. Project WGS84 → EPSG:2263 by LCC forward from the `.prj` parameters. **No dependency.**
3. Resolve the tile via `DeliveryArea.shp`; import 39.6 MB, not 762 MB.
4. **Assign BIN by containment** — the correlate-during-import step.
5. **Reconstruct per BIN**, not per DGN footprint: group that BIN's roof polygons, extrude
   down, union → one solid per building. Grouping by DGN footprint over-segments to ~1,021.
6. Tag each solid with BIN, attributes, and provenance (2014 survey vs current extrusion).
7. Reconcile: reconstructed max Z vs `ground_elevation + height_roof` → MATCH / STALE;
   BINs with no DGN geometry → MISSING, validated against `construction_year`.

### Enumerator gotcha — and the working pattern

Rhino's default `doc.Objects` enumerator **skips objects on hidden layers**. Hiding a layer
silently removes its objects from iteration and from `objectCount`, which reads as data
loss.

Turned into the working pattern: **never delete source data, park it on a hidden layer.**
Import, hide the source layers in the same operation, and read them back with explicit
settings:

```python
s = Rhino.DocObjects.ObjectEnumeratorSettings()
s.NormalObjects = True; s.HiddenObjects = True; s.LockedObjects = True
for o in doc.Objects.GetObjectList(s): ...
```

Deleting the DGN curves mid-investigation destroyed the evidence needed to diagnose a bad
classification and forced a re-import. Superseded reconstructions go to a hidden
`*_v1_buggy` layer, not to the bin.

---

## Pipeline v2 — three defects found and fixed

The first full run produced plausible-looking numbers that were substantially wrong. All
three defects were in the harness, not the data.

### Defect 1 — one-sided orientation guard (the serious one)

The guard fired only when a prism hung *below* its base:

```python
if br.GetBoundingBox(True).Min.Z < base_z - 0.01:   # catches downward only
```

When `Extrusion.Create` went *upward* from a roof curve, the prism floated from `roof_z` to
`roof_z + (roof_z − base_z)` — and `Min.Z` was then *greater* than `base_z`, so the guard
never fired. The prism hung in mid-air above the building at double its true height.

Diagnosed on BIN 1088523: reported roof 731.50 ft against an attribute value of 417.00, a
+314.50 ft delta on a building constructed in 2010. Its assigned roof polygons in fact top
out at 431.4 ft, and `384.8 × 2 − 38 = 731.6`. Arithmetic, not change.

**Fix — direction-agnostic normalisation.** The prism's *height* is correct either way;
only its position is wrong. After extruding, translate so the top sits at `roof_z`:

```python
dz = roof_z - br.GetBoundingBox(True).Max.Z
if abs(dz) > 1e-6: br.Translate(Vector3d(0, 0, dz))
```

Verified by asserting every solid's base against its own `ground_elevation`:
**`base_misplaced: 0`.**

### Defect 2 — first match instead of best overlap

The assignment loop `break`s on the first footprint containing a roof centroid. Wrong
spatial-join semantics wherever footprints overlap or nest. **Fix:** score every candidate
by the fraction of the roof polygon's vertices it contains, take the maximum.

### Defect 3 — mismatched AOI shapes

The DGN was filtered with a **square** (±1,968 ft) while NYC footprints came from a **600 m
circle**. The square is 27% larger by area with corners reaching 2,783 ft, so a large share
of roof polygons had no footprint to land in. **Fix:** circular filter for both.

### v2 results

| | v1 | v2 |
|---|---|---|
| Orphan roof curves | 1,477 — 38% | **343 — 12.5%** |
| MATCH | 401 | **446 — 76%** |
| STALE | 183 | **138 — 24%** |
| MISSING | 30 (21 post-2014) | 30 (21 post-2014) |
| p50 delta | 0.00 ft | 0.00 ft |
| **p90 delta** | **94.99 ft** | **16.31 ft** |
| Base misplaced | unmeasured | **0** |
| Model top | 1,245 ft | 665 ft |

**MISSING held at exactly 30, with 21 post-2014, across both runs** — unmoved while
everything around it was broken. The primary change detector is bug-independent, which is
the property it needs.

The p90 collapse from 95 ft to 16 ft measures how much of the original "31% STALE" was
arithmetic rather than change.

---

## Roof-area filter for the height comparison

`height_roof` is documented as the highest point of roof, but the DGN carries small
bulkheads and stair heads as separate roof polygons that the attribute does not
consistently count. Sweeping a minimum-area threshold for the polygons eligible to set the
comparison height:

| Threshold | MATCH % | p75 delta | within 1.6 ft | Buildings lost |
|---|---|---|---|---|
| 0 | 76.2% | 7.06 ft | 398 | 0 |
| 100 SF | 76.9% | 5.73 ft | 405 | 0 |
| **200 SF** | **81.9%** | **1.50 ft** | 442 | **0** |
| 400 SF | 85.9% | 0.83 ft | 465 | 3 |
| 800 SF | 79.4% ↓ | 1.97 ft | 398 | 42 |

**Adopt 200 SF.** It takes most of the gain and strands no buildings. 400 SF scores better
but leaves 3 buildings with no eligible roof — converting them to false MISSING — and on a
single 585-building AOI that optimum is plausibly overfit.

### Validated on a second AOI (2026-08-02)

Second AOI chosen **adversarially**: West Village, 600 m radius, 2,489 buildings — low-rise
historic rowhouse fabric where a minimum-area filter is most likely to fail. Median height
47 ft (vs 57), p90 69 ft (vs 249), max 228 ft (vs 1,039), only 0.6% post-2014 (vs 7.5%).
Median footprint 1,279 SF; median roof polygon 741 SF with p10 at 154 SF.

| Threshold | Hell's Kitchen (585) | West Village (2,468) |
|---|---|---|
| | match / stranded | match / stranded |
| 0 | 76.2% / 0 | 88.7% / 0 |
| 100 SF | 76.9% / 0 | 88.9% / 0 |
| **200 SF** | **81.9% / 0** | **93.1% / 6 (0.24%)** |
| 400 SF | 85.9% / 3 (0.5%) | 94.8% / **71 (2.9%)** |
| 800 SF | 79.4% / 42 | 94.1% / **652 (26%)** |

**200 SF confirmed.** Same inflection, same magnitude of gain, stranding negligible in both.

**The case against 400 SF is far stronger than the first AOI suggested.** It strands 0.5%
of high-rise buildings but **2.9% of low-rise** — a six-fold worse rate, because rowhouse
roofs are small enough that an aggressive minimum consumes real roof planes rather than
bulkheads. Tuning on the first AOI alone would have shipped a filter silently converting
~3% of low-rise buildings into false MISSING.

Two differences between AOIs, both explainable: baseline match is much higher in the West
Village (88.7% vs 76.2%) because it is stable historic fabric with far less real change;
and orphans fall to 6.3% from 12.5% because continuous dense fabric has fewer AOI-edge
effects.

**`p50` delta = 0.00 ft in this AOI too, at every threshold** — a third independent
confirmation of vertical consistency, now across two urban typologies and 3,053 buildings.

---

## The unexplained MISSING buildings — resolved

Of 29 MISSING in AOI 1, 21 were confirmed post-2014 and 8 were unexplained residue. All 8
now have a specific cause; **none is genuinely unexplained.**

| BIN | Year | Cause | Evidence |
|---|---|---|---|
| 1026915 | 1960 | Assignment failure | Nearest roof 18.8 ft away, area **4,632 SF — identical to footprint** — at Z 49.0, exactly `ground+height_roof`; 5 roofs overlap |
| 1024961 | 1939 | Assignment failure | Nearest roof **578 SF — identical** to footprint, 27.2 ft away |
| 1089690 | blank | Assignment failure | 4 roof polygons overlap, none with centroid inside |
| 1026441 | 1937 | `height_roof` = 0 | Nothing to model |
| 1080374 | 2000 | Below capture threshold | 175 SF, 9 ft, `feature_code` 1000 |
| 1090933 | blank | Below capture threshold | 298 SF, 10 ft, `feature_code` 1000 |
| 1089382 | blank | Probably post-2014 | 207 ft tall, zero overlapping DGN roofs |
| 1089379 | blank | Probably post-2014 | 120 ft, 20,501 SF, zero overlapping DGN roofs |

### Fix 1 — two-pass assignment

Centroid containment has a **systematic blind spot**: roofs that exist and match perfectly
(identical polygon area, identical elevation) but whose centroid falls just outside the
footprint, on concave outlines or where the roof is offset from its footprint.

**Add a second pass.** For any footprint left with no assigned roofs, search for roof
polygons that *overlap* it and take the best by overlap fraction. Overlap counts confirm
this recovers all three cases.

### Fix 2 — blank `construction_year` pollutes the self-check

Four of the eight carry no year at all, two of them large and tall with no 2014 geometry —
almost certainly new construction. The "21 of 29 explained by post-2014" figure therefore
**understates**; the true count is likely 23. The self-check is sound, its denominator is
not. Treat blank year as *unknown*, never as *not-post-2014*.

### Fix 3 — filter on `feature_code`

Buildings are `2100`. Both sub-300 SF strays are `1000`. Non-2100 features should be
excluded from the reconciliation population rather than counted as failures. Likewise
exclude `height_roof = 0` upfront — there is nothing to compare.

### Revised accounting

Of 29 MISSING: roughly **23 genuine post-2014 absence, 3 recoverable assignment failures,
3 that should never have been in the population.** The method's true residue is far smaller
than the raw count implied.

---

## Pipeline v3 — filters and two-pass assignment implemented

| | v2 | v3 |
|---|---|---|
| Population | 614 | **598** |
| MATCH | 76.2% (81.9% with area filter) | **82.3%** |
| STALE | 139 | **102** |
| MISSING | 29 | **22** |
| — post-2014 | 21 | 16 |
| — blank year | — | 3 |
| — dated pre-2014 | 8 | **3** |
| p75 / p90 delta | 7.06 / 16.69 ft | **1.47 / 14.23 ft** |
| p50 delta | 0.00 ft | 0.00 ft |

Aggregate predictions held: MISSING 22 against a predicted ~23, match 82.3% against ~82%.

### Population filters — one unanticipated win

`feature_code` distribution in AOI 1: `2100` 602, `5110` 5, `5100` 3, `1000` 2, `1003` 1,
`1004` 1. Twelve non-2100 features and four `height_roof = 0` excluded.

**Three of the exclusions are `feature_code` 5100 — "Building Under Construction".** These
could never appear in a 2014 survey and were silently inflating the failure count. Worth
filtering explicitly rather than as a side effect of the 2100 rule.

### Two-pass assignment — under-delivered, and why

Pass 2 recovered 2 buildings but **not one of the three it was designed for.** All three
targets remain MISSING.

The flaw is in the design: pass 2 was restricted to **orphan** roofs. Those buildings'
matching roofs had already been claimed by neighbours during pass 1, so pass 2 was
structurally unable to contest them.

**Correct fix: global best-overlap matching, not greedy-assign-then-fallback.** A roof
should go to the footprint it overlaps most, evaluated across all candidates
simultaneously, rather than to whichever footprint happens to contain its centroid first.

### BIN 1026915 — diagnosis corrected, then corrected again

**v3 reading (WRONG, retained as a cautionary record):** measured with vertex-counting
overlap, its identical-area roof showed *zero* overlap with the footprint at 18.8 ft
distance, and this was written up as a positional offset — "a genuine data discrepancy that
no assignment algorithm can recover."

**v4 reading (verified):** the roof overlaps the footprint by **86%**. Area sampling
assigns it correctly — area 4,632.10 SF against a 4,632 SF footprint, Z 48.99 against an
attribute of 49.00, **delta 0.0 ft, MATCH**.

There was never a data discrepancy. **The vertex-count overlap proxy was the defect**: the
roof's vertices fell outside the footprint while its interior overlapped substantially. A
measurement artifact was attributed to the source data.

The real lesson is the inverse of the one first recorded: before concluding that data
disagrees with itself, verify the instrument.

### Residual

Five non-post-2014 MISSING remain, cleanly split:

- **2 with zero overlapping roofs** — 1089379 (120 ft) and 1089382 (207 ft), both
  blank-year, near-certainly post-2014 construction with missing attribution.
- **3 with overlapping roofs at wrong elevations** — contested or offset geometry, of which
  1026915 is confirmed offset rather than contested.

---

## Pipeline v4 — global best-overlap matching

Replaces greedy centroid-containment-then-fallback with a single global pass:

- Candidates are all footprints whose **bounding box intersects** the roof's, not only those
  containing its centroid.
- Overlap is measured by **area sampling** — a 5×5 grid over the roof's bbox filtered to
  points inside the roof polygon, falling back to vertices plus centroid for degenerate
  slivers — rather than by counting vertices.
- Each roof goes to the footprint with maximum sampled overlap, evaluated across all
  candidates simultaneously.

### Re-validated on both AOIs

| | HK v3 | **HK v4** | WV v2+filter | **WV v4** |
|---|---|---|---|---|
| MATCH | 82.3% | **82.0%** | 93.1% | **93.0%** |
| MISSING | 22 | **20** | 21 | **13** |
| — dated pre-2014 | 3 | **1** | — | 5 |
| Orphan roofs | 13.5% | **12.0%** | 6.3% | **5.2%** |
| p75 / p90 delta | 1.47 / 14.23 | 1.54 / 14.60 | 0.87 / 3.81 | 0.87 / 3.85 |
| p50 delta | 0.00 | **0.00** | 0.00 | **0.00** |

**It did what it was designed for.** Dated-pre-2014 MISSING in AOI 1 fell from 3 to **1** —
the two assignment failures the orphan-only pass could not contest are recovered. West
Village MISSING fell 21 → 13.

**Match rate is deliberately flat.** The rewrite fixes *assignment*, not the match
statistic; a jump here would have been a red flag rather than a win.

### The statistic that justifies it

**Contested roofs** — polygons overlapping more than one footprint: **493 in AOI 1 (18%),
1,547 in the West Village (30%)**. In dense rowhouse fabric nearly a third of roof polygons
touch multiple footprints, so greedy first-match was guessing on a third of the data and
happening to be right most of the time. Global matching removes the guess.

### Residue — verified, and it is not the BIN predicted

One dated-pre-2014 MISSING remains in AOI 1. It was **predicted to be 1026915 and is not** —
it is **BIN 1024961**.

1026915 was recovered correctly by area-sampled overlap (86% overlap, delta 0.0 ft, MATCH).
The prediction was an inference from a diagnosis that itself turned out to be a measurement
artifact; verifying it cost one call and overturned two claims.

**BIN 1024961** — a 1939 playground restroom, 578 SF footprint, with a roof of *identical*
area 27.2 ft away at Z 63.9 against an attribute roof of 49.0. **Position and elevation
both disagree**, which is materially different from 1026915 where the elevation matched
exactly. This is the genuine single-building residue of the method in AOI 1.

### West Village re-run with `feature_code` — caveat refuted

The earlier caveat ("uneven in the West Village's disfavour; filtering will tighten it")
was speculation, and re-fetching with `feature_code` **refuted it**.

| | unfiltered | filtered |
|---|---|---|
| Population | 2,489 | 2,460 (29 excluded, all `5110`) |
| MATCH | 93.0% | **92.9%** |
| MISSING | 13 | **13 — unchanged** |
| — dated pre-2014 | 5 | **5 — unchanged** |
| p75 / p90 | 0.87 / 3.85 | 0.89 / 3.88 |

The 29 `feature_code` 5110 features (16–30 ft structures — canopies, garages, sheds) were
matching perfectly well. Not one was in the MISSING set. Every metric moved by less than a
tenth of a point.

The `feature_code` filter is still correct in principle — it removes things that are not
buildings from a building reconciliation — but it is **not load-bearing**. In AOI 1 it
mattered because three exclusions were `5100` *Building Under Construction*; here there
were none.

### Positional offset — now properly evidenced

The five dated-pre-2014 MISSING in the West Village:

| BIN | Year | Attr roof | Nearest roof Z | Distance | Area |
|---|---|---|---|---|---|
| 1010544 | 1910 | 53.85 | **53.9** | 14.8 ft | 1,040 SF |
| 1084642 | 1900 | 36.58 | **36.6** | 12.7 ft | 546 SF |
| 1076786 | 1900 | 77.62 | **77.6** | 30.9 ft | 1,992 SF |
| 1083544 | 1911 | 50.84 | 49.7 | 9.2 ft | 919 SF |
| 1076830 | 1899 | 48.00 | 56.6 | 44.5 ft | 311 SF |

**Three have a roof at exactly the right elevation — matching within 0.05 ft — 12 to 31 ft
away with zero sampled overlap.** An elevation agreeing to a twentieth of a foot is not
coincidence; those are the right buildings' roofs, displaced in plan. On rowhouses 20–25 ft
wide, that displacement puts the roof over the neighbour.

**The distinguishing test, learned the hard way:**

| | 1026915 (false alarm) | These three (genuine) |
|---|---|---|
| Elevation match | exact | exact |
| Interior overlap, area-sampled | **86%** | **0%** |
| Verdict | vertex-metric artifact | true positional offset |

Genuine positional offset is real but **rare: ~3 in 2,460, or 0.12%** — an order of
magnitude smaller than the failure mode first assumed, and only diagnosable once the
overlap metric itself is trustworthy.

---

## Streetscape and ground plane — the NYC Planimetric Database

This closes the "**No terrain mesh**" gap recorded earlier in this spec. The DGN carries
buildings only, but DOITT's planimetric database — the *other* source the DCP model was
built from — carries the whole ground surface, and it is on Socrata, keyless, spatially
queryable with `within_circle`.

### Verified in the site AOI (600 m of 502 10th Ave)

| Layer | Resource | Features |
|---|---|---|
| Roadbed | `i36f-5ih7` | **287** polygons |
| Sidewalk | `52n9-sdep` | **93** polygons |
| Curbs | `5xvt-8cbk` | **894** lines |
| Elevation Points | `9uxf-ng6q` | **1,918** in 700 m |

Also available in the same database and same schema: **Median** (8 subtypes — traffic
island, painted, curb, grass, barrier, rail, fence, other), **Curb Cut**, **Pavement Edge**,
**Open Space (Parks)** and **(Other)**, **Public Plazas**, **Parking Lot**, **Boardwalk**,
**Railroad Line** / **Structure**, **Transportation Structures**, **Hydrography**,
**Shoreline**, **Swimming Pools**, **Misc Structure Poly** (billboards, sign gantries, toll
areas).

Uniform schema across all of them — `the_geom`, `feat_code`, `sub_code`, `status`,
`shape_leng`, `shape_area` — so **one reader handles every layer.**

### The 2D/3D split

**The streetscape polygons carry no Z.** Terrain comes from Elevation Points, so a ground
plane is *drape 2D planimetrics onto a surface interpolated from spot elevations*.

### Elevation subtypes must be separated — this bites

| feat / sub | n | min | p50 | max | Meaning |
|---|---|---|---|---|---|
| 3020 / 302000 | 953 | 19.0 | 94.1 | **1290.6** | **Building** elevation — roofs |
| 3000 / 300000 | 871 | −5.0 | 25.7 | 91.1 | **Ground** spot elevation |
| 3000 / 300020 | 94 | 10.6 | 40.0 | 103.8 | Third subtype, excluded |

A first attempt fetched elevation without `sub_code` and interpolated over **all** points,
pulling streets near towers up toward 1,290 ft rooflines. Filtering to `3000/300000`
produced a plausible ground surface: draped Z **−4.8 / 30.5 / 88.3 ft** (min/p50/max).

**Always fetch `feat_code` and `sub_code` with elevation.** The dataset name says
"Elevation Points"; it does not say most of them are on roofs.

### Demonstrated

410 curves built and draped — 289 roadbed, 121 sidewalk — by inverse-distance weighting
over the 4 nearest ground points, in EPSG:2263 alongside the reconstructed buildings.

**Limitations of the demonstration:** IDW-4 is crude, and at 871 points over a 700 m radius
the sampling is roughly one per 1,770 m². The **1-foot DEM raster** (`dpc8-z3jc`, or the
integer variant `7kuu-zah7`) is the better terrain source where accuracy matters — it is an
`href` download rather than a Socrata query.

### Surfacing the streetscape — order of operations is the whole problem

Draping vertices individually destroys planarity. Measured on the curve version:
**1 of 289 roadbed curves and 2 of 121 sidewalk curves were planar** at 0.001. So
`Brep.CreatePlanarBreps` applied to draped curves fails on ~99% of them. Surfacing must
happen *before* deformation, not after.

Three SDK facts drive the design:

- `Brep.CreatePlanarBreps` accepts an **`IEnumerable<Curve>` of loops** — pass a polygon's
  outer and inner rings *together* and holes are trimmed correctly.
- `Mesh.CreateFromBrep(brep, MeshingParameters)` with **`MaximumEdgeLength`** controls
  subdivision, and **`SimplePlanes` must be `False`** — otherwise a planar face meshes to
  two triangles and draping moves only its corners, leaving the interior flat.
- Meshes deform by moving vertices; Breps do not. The draped result must be mesh.

**Correct sequence:**

```
group rings per polygon  ->  build flat at Z=0  ->  Brep.CreatePlanarBreps (holes trimmed)
  ->  Mesh.CreateFromBrep at 20 ft max edge  ->  drape vertices to terrain
```

Topology is established while everything is planar; deformation happens last.

**Ring grouping must come from source.** It is lost the moment each ring becomes an
independent curve, so the surfacing pass re-reads the GeoJSON rather than consuming the
curve layer.

### Result

| Layer | Surfaces | Failed | Inner rings | Mesh vertices |
|---|---|---|---|---|
| Roadbed | 230 | **0** | 2 | 93,994 |
| Sidewalk | 59 | **0** | **28** | 53,197 |

6.6 s total, IDW accelerated by a 250 ft grid index (243 cells).

**The 30 inner rings are the proof.** Surfacing ring-by-ring — which is what a naive pass
over the curve layer does — would have produced 30 spurious patches lying on top of holes.
Grouping per polygon before surfacing is what prevents it, and sidewalks are where it
matters: 28 of the 30 holes are theirs.

### Terrain contamination — the streets came out lumpy

The first surfaced result had a 50 ft **hill in the middle of 10th Avenue**. IDW is a
faithful interpolator and cannot overshoot its samples, so a peak that size means a real
data point is up there.

**74 of 871 ground-classified spot elevations deviate more than 15 ft from their local
neighbourhood median**, the worst by **+50.4 ft**.

They are not noise. This AOI — 10th Avenue in the West 30s and 40s — is wrapped in the
**Lincoln Tunnel approach viaducts and the Port Authority bus ramps**. Those points are
genuine surface measurements *of an elevated deck*. The data is correct; the assumption
that **"spot elevation = street level"** was wrong. In a dense city the ground is not a
single-valued function of (x, y).

**Two fixes:**

1. **Outlier rejection** against the local median (>15 ft) — 74 of 871 removed.
2. **Add building `ground_elevation` as a second sample source** — 611 points that are
   *semantically* guaranteed at-grade, because they are the elevation at a building's base.
   Buildings do not sit on viaducts.

| | before | after |
|---|---|---|
| Samples | 871 | **1,408** |
| Sample z p50 | 25.7 | 32.0 |
| Sample z p99 | 64.5 | **48.3** |
| Sample z max | **91.1** | **62.7** |

The second fix is the more robust of the two: it does not merely reject bad data, it adds a
sample set whose semantics guarantee the property being interpolated. Coverage improves 62%
and distribution improves with it, since buildings are spread across every block while spot
elevations cluster along roadways.

**Honest limitation:** this *deletes* the elevated ramps rather than modelling them. The
correct treatment is to bring in **Transportation Structures** (`h9sf-7bej`) and build those
decks as their own surfaces at their own elevations, leaving the at-grade street network
beneath them. A multi-level city needs a multi-level ground model.

The **reversal at 800 SF** is what makes the result credible: match rate *falls*, so the
curve is tracking a real property of the data rather than rewarding more aggressive
filtering.

The filter applies to the **comparison height only**. Bulkheads are real and stay in the
geometry.

**`p50` remains 0.00 ft at every threshold** — the vertical-consistency finding is
independent of all of this.

### Generalisation beyond NYC

Rook's **GIS BYOK research** (2026-04-24, "research complete, synthesis drafted", unbuilt)
already specs this pipeline: *lat/lon → AOI buffer → LIDAR DSM+DTM → nDSM → footprints →
zonal stats → extrude to `.3dm`*, with an abstract `HeightProvider` having
`DSMMinusDTMProvider` and `AttributeHeightProvider` implementations converging at
extrusion.

**NYC's `height_roof` is an `AttributeHeightProvider`.** The verified NYC path is an
instance of the already-designed no-LIDAR branch, not a workaround. This is also the route
by which the whole workflow escapes NYC — AS supplies a lot boundary only in New York;
GIS BYOK supplies footprints, terrain and heights anywhere.

---

## Site selection

### Method

Pick the site **archetype** first, then find an instance. Deriving an address from a
single metric optimises a proxy for "interesting."

The criterion is **constraint conflict**. If all constraints agree, the planner's reasoning
is trivial, the `critic` has nothing to catch, and no decision is worth a Correction pin.

### Chosen archetype: the split-zone lot

- `splitzone` is a literal PLUTO boolean, alongside `zonedist1`–`zonedist4`.
- It is exactly where AS goes soft: *"Pro-rate FAR by estimated area in each zone if lot
  dimensions are available, otherwise present both sets of controls."* AS either estimates
  or punts — and synthesising two conflicting bulk regimes into one envelope is precisely
  the planner's job.
- **The geometry channel is unaffected**: the lot polygon comes from a separate BBL-keyed
  MapPLUTO ArcGIS endpoint, independent of zoning complexity.

### The screen

PLUTO is Socrata resource `64uk-42ks`, keyless.

```
$where=splitzone=true AND lotarea>6000 AND lotarea<60000 AND builtfar<1.0
       AND zonedist1 NOT LIKE '%PARK%' AND zonedist2 NOT LIKE '%PARK%' AND residfar>0
```

`builtfar<1.0` keeps the site under-built so "what can be built here" is live. Excluding
PARK removes public parkland, which dominates the raw Manhattan results.

Distribution of split-zone under-built lots: Queens 1,495 · Staten Island 958 ·
Brooklyn 643 · Bronx 482 · **Manhattan 168**. Manhattan is scarcest — it is built out —
but is correct for the showcase because the highest densities produce the sharpest
conflicts.

### Selected site

**502 10th Avenue, BBL 1007360001** — Manhattan CD 104 (Clinton/Hell's Kitchen),
lat/lon 40.7570872, −73.9966792.

| Property | Value |
|---|---|
| Districts | **C2-8 / R8A**, C2-5 overlay |
| Conflict | C2-8 permits 10 FAR with no contextual cap; R8A is contextual with mandatory streetwall and height cap. Plus an overlay stacking commercial use rules — one lateral conflict, one vertical |
| Lot area | 24,959 SF |
| `builtfar` | 0.00 — under-built, question is live |
| `irrlotcode` | **false** — geometrically tractable |
| Lot polygon | verified: 1 ring, 6 vertices, WGS84 |
| Context | 614 buildings within 600 m; `height_roof` median 57 ft, p90 249 ft, max 1,039 ft; `ground_elevation` on 611/614; **45 post-2014** |

Six vertices is slightly non-rectangular — it exercises real polygon handling without the
offset self-intersection risk that would confound slice 1.

**Deliberate exclusion:** keep slice 1 geometrically simple. Irregular polygons stress GH
offset in ways unrelated to the thesis; if it broke we could not tell whether the spine or
the offset failed. Irregular lots (225 E 23rd — C2-8A/R8B; 1711 3rd Ave — R10/R7-2) are
reserved for a deliberate offset stress test.

**Vintage trap at this site:** the tallest context building is 1,039 ft and Hudson Yards
was built after 2014, so the DOITT model alone would delete the most visually dominant
context. This site *requires* the reconciliation rather than merely benefiting from it.

**Unverified:** PLUTO `lottype` code meanings. Several candidates are `lottype=3`, believed
to be corner, not confirmed. It matters — a corner lot adds a second streetwall regime.

---

## Open problems, with proposed resolutions

These are the three things a plan must actually solve rather than gesture at.

### 1. Chirp determinism semantics — DEFERRED (2026-08-01)

**Status: acknowledged, deliberately out of scope for now.** A full node state machine is
an entire subsystem and does not need to be carried yet. Recorded here so it is not
rediscovered later as a surprise.

**Problem.** A GH definition is supposed to be a pure function of its inputs. Chirp nodes
are not. Typed pins constrain the *shape* of an output, not its *value*. If a planner
returns 0.4 on Tuesday and 0.45 on Thursday from identical inputs, the model changed
silently. For a proposition built on *trustworthy* early-stage rigour, a model that
quietly drifts is worse than no model.

This is a live concern in the ecosystem already: the CanvasDirector design explicitly
fences off "global nondeterminism analysis of arbitrary upstream GH components."

**Why deferral is safe — verified in the implementation.** `ChirpAdapter.call()` keys its
cache on `(signature, inputs, schema, model)` and returns a `cached` flag on every call;
caching is on by default (`CHIRP_CACHE`, default `true`). So repeated solves with
unchanged inputs do **not** re-call the LLM — the practical behaviour is already
freeze-by-default. `chirp_create` additionally exposes `deterministic_only`, which runs
post-processing C# with no LLM call at all.

What is missing is only the *surfacing* — a visible signal when an upstream input has
changed such that a cached reasoning result no longer applies. That is the Stale problem,
and it is the piece being deferred.

**Eventual resolution sketch (not now).** Three node states: **Live** (re-evaluates),
**Frozen** (pinned to a recorded evaluation + trace id), **Stale** (was frozen, upstream
changed — flagged visibly, never silently re-run). The failure mode is not nondeterminism
as such, it is **undetected change**.

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
- An **EarthAnchorPoint route** — set anchor from lat/lon, expose the model↔earth
  transform. Absent from both the C# companion and native today. Small, and it unlocks
  both georeferencing and Rhino's native sun.
- A **footprint → extrusion path** (`AttributeHeightProvider` against `5zhs-2jue`, seated
  at `ground_elevation`), behind a provider seam so NYC is one implementation rather than
  the assumption.
- The BIN-join **reconciliation** against the DOITT model.
- Node state machine (Live / Frozen / Stale) and its surfacing — deferred, see open
  problem 1.
- The return brief.
- Narrator → deck wiring.

### Credentials

**Architecture Studio requires none.** Its data-governance doc is explicit: it "does not
bundle connector credentials, select providers, configure OAuth, or create connector
manifests," and `/as:studio init` writes an empty `mcpServers` object as a reserved
boundary. All seven NYC skills state "No API key required"; NYC Open Data (Socrata) and
the MapPLUTO ArcGIS endpoint are open, as verified by direct query.

| Need | For | Required? |
|---|---|---|
| EC3 / Building Transparency | `/as:epd-research` | **Optional** — degrades to UL, NSF, Environdec, IBU, SCS, ASTM, manufacturer pages |
| Pillow | `/as:resize-images`, product images | On demand |
| rembg + onnxruntime | Background removal (+~170 MB u2net on first run) | On demand |
| PyMuPDF | EPD and product PDF parsing | On demand |
| curl, python3 | Image download, disclaimer hook | Baseline |
| `ANTHROPIC_API_KEY` or LiteLLM provider | **Chirp reasoning nodes** | Required for the spine |
| Gemini key | `rhino_render_view`, `rhino_enhance_prompt` | Required for generation |
| — | `rhino_capture_depth` | **None** — entirely local |
| fal.ai key | 2D→3D reconstruction | That path only |

The credential burden sits on the Rook side, not the AS side. **Slice 1 needs no AS
credentials at all.** Note also that `WebSearch` is US-only, which matters for non-US
practice.

Caveat: the Gemini rows reflect current tool descriptions; a generation-provider framework
and multi-provider plan exist in `docs/rook_docs/`, so the provider set may already be
broader. Confirm before writing it into anything user-facing.

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
   audience can actually watch? **Still open.**
2. ~~First vertical~~ — **answered.** NYC zoning, split-zone archetype, 502 10th Avenue.
   See Site selection.
3. ~~Chirp cache semantics~~ — **answered.** Cache keys on
   `(signature, inputs, schema, model)`, on by default, returns a `cached` flag.
   See open problem 1.
4. **PLUTO `lottype` codes** — unverified. Determines whether the selected site carries a
   second streetwall regime.
5. **DOITT model vertical datum** — must be established before any height comparison is
   meaningful.

---

## Implementation sequence

This spec is larger than one plan. It decomposes into slices, each producing something
demonstrable on its own:

| Slice | Deliverable | Depends on |
|---|---|---|
| **1 — the spine link** | Findings contract + AS reader + a `planner` node driving a real definition to geometry. Proves the thesis in miniature. | nothing |
| **C — site + context** | EarthAnchorPoint route; footprint→extrusion behind a provider seam; BIN-join reconciliation against the DOITT model; provenance user text. | nothing — **runs in parallel with 1** |
| 2 — the human loop | Correction pin → `editor` round trip; correction persists across solves. | 1 |
| 3 — the return brief | What the architect sees on returning. | 2 |
| 4 — analysis + imagery | Spatial analysis geometry; RookVision diagram/render of current state. | 1, C |
| 5 — narrative + deck | `narrator` → AS deck. | 4 |

Slice C is deliberately independent: it is geometry-channel work and touches none of the
reasoning spine, so it neither blocks slice 1 nor is blocked by it.

Slice 1 is planned in
`docs/superpowers/plans/2026-08-01-findings-to-parameters-spine.md`. Later slices are
planned separately, after slice 1 returns evidence.

---

## Next step

Implementation plan via `superpowers:writing-plans`, once the open questions above are
settled.

---

## Terrain done properly — USGS 3DEP 1 m bare-earth DEM

The scattered-point approach was wrong in both data and method. Replaced.

### The data

**USGS 3DEP ElevationServer**, keyless, 1 m resolution:
`https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/getSamples`

- **Must POST, not GET.** 400+ points in a GET exceeds the URL limit and every batch fails
  silently-ish; the same payload by POST returns 400 samples in 4 s.
- Returns **metres, NAVD88**. Convert ×3.280839895 for feet.
- Backed by the 2017 NYC topobathymetric LiDAR (Quantum Spatial / AppGeo), bare-earth DEM
  built by TIN over classified ground returns.

### Calibrated before use, not assumed

Sampled 3DEP at 150 building centroids and differenced against NYC's own
`ground_elevation`:

**median 0.11 ft, mean 0.25 ft, σ 4.57 ft**

Two wholly independent sources agreeing to a tenth of a foot at the median confirms unit,
datum and service in one check.

### Result

13,273 nodes on a 10 m grid over a 650 m radius, 0 failed batches, 272 s.

| | scattered spot elevations | 3DEP bare-earth |
|---|---|---|
| Samples | 871 | **13,273** |
| Spacing | ~1 per 1,770 m² | 1 per 100 m² |
| z max | **91.1 ft** | **52.6 ft** |

**Verified at the exact failure coordinate** — the worst outlier from the lumpy-road
diagnosis:

| | |
|---|---|
| Old spot elevation | **72.4 ft** |
| Old local neighbourhood median | 22.0 ft |
| Old spike | **+50.4 ft** |
| **3DEP bare-earth** | **24.3 ft** |

The viaduct is **absent from the DEM by definition** rather than filtered out of a sample
set. 289 surfaces rebuilt, 0 failures, **0 vertices falling outside DEM coverage**.

### Method lesson

A previous fix was declared successful on summary statistics and a *different* camera
angle. That is not verification. Re-photograph the same failure, and quote the number at
the same coordinate.

### Still short of a surveyor

The surfaces are draped on a smooth height field. A civil model builds pavement from
**breaklines** — curb lines as hard triangulation constraints, roads as ruled surfaces
between their edges with a crown, sidewalk as a constant curb-reveal offset. The 894 curb
lines are already fetched and still unused as constraints. And a TIN remains single-valued,
so elevated decks still need modelling as separate surfaces from Transportation Structures
(`h9sf-7bej`).

### Sampling a height field is wrong for pavement — fit per surface

Even on the 1 m DEM, sidewalks came out as rollercoasters. **The undulation wavelength
matched the 10 m sampling grid**, which is the diagnosis: nodes straddle *different
surfaces*. One lands 3 ft into the roadbed and pulls the sidewalk down, the next lands on a
stoop and pulls it up, and interpolation between them oscillates at the grid pitch.

This is the breakline problem again. A sidewalk is a **distinct surface bounded by curbs**;
interpolating across that boundary mixes in elevations belonging to something else.

**Fit each polygon instead of sampling it.** Gather DEM nodes strictly interior (4 ft inset
so edges do not bleed), then fit robustly with median-based outlier rejection.

**Conditioning is not optional.** A naive least-squares plane on a long thin ribbon is
**ill-conditioned** — interior samples are nearly collinear, the cross-ribbon slope is
undetermined, and coefficients explode. First attempt produced a polygon with a Z range of
**550,168 ft**. A determinant threshold of `1e-9` is meaningless at coordinates near
985,000; the test must be *relative*: `det > 1e-4 * Sxx * Syy`.

When ill-conditioned, fall back to the **more correct model anyway**: grade along the
principal axis, flat across — which is what a sidewalk is. Then clamp every vertex to the
observed sample range as a safety net.

| per-polygon Z range | sampled | naive plane | conditioned fit |
|---|---|---|---|
| p50 | 4.76 ft | 0.87 ft | **0.87 ft** |
| p90 | 25.15 ft | 13.81 ft | **12.91 ft** |
| max | 62.9 ft | **550,168 ft** | **38.96 ft** |

209 polygons fitted, 171 fell back to constant, 3,962 vertices clamped.

**Still not a surveyor.** The 894 curb lines remain unused as triangulation constraints;
there is no road crown; and sidewalk is fitted independently rather than derived as
roadbed + curb reveal. Those are the remaining gap between this and a civil model.

---

## Slice G — the coherent ground surface

**Status:** scoped, not built. This supersedes per-polygon fitting rather than extending it.

### The failure it fixes

Every polygon is currently fitted in isolation, so nothing forces adjacent patches to agree
along their shared edge. Road patches float relative to one another. **No refinement of the
per-polygon fit can fix this** — independent fits guarantee seams by construction. The
architecture is wrong, not the parameters.

### The finding that makes it cheap

The planimetric database is a **proper coverage**. Measured at full floating-point
precision, no snapping tolerance:

| | |
|---|---|
| Distinct vertices (roadbed + sidewalk, AOI) | 23,803 |
| **Shared by 2+ polygons** | **12,246 — 51.4%** |
| roadbed ↔ roadbed | 1,636 |
| **roadbed ↔ sidewalk** | **10,601** |
| Vertex degree | 1:11,557 · 2:11,683 · 3:394 · 4:167 · 5:2 |

Polygons already share exact boundary vertices, and degree-3/4/5 nodes are street corners
and intersections. **The connectivity was always in the data; independent processing
discarded it.**

**The 10,601 roadbed↔sidewalk vertices are the curb line** — the model's one legitimate
discontinuity, already explicitly identified by the topology. Curbs do not need to be
inferred.

### The algorithm

**1. Weld.** Build one vertex graph keyed on exact coordinates. No tolerance needed.

**2. Solve globally.** One elevation per welded vertex, as a single least-squares system:

```
minimise   Σ (z_v - dem_v)²           data term, pulls toward the 3DEP DEM
       + λ Σ (z_u - z_v)²             Laplacian smoothness along graph edges
```

Shared vertices are shared *unknowns*, so C0 continuity is structural rather than fitted.
This replaces N independent solves with one.

**3. Split at curbs.** Duplicate each roadbed↔sidewalk vertex into a road-side and a
sidewalk-side unknown, coupled by a curb-reveal constraint (~0.5 ft) instead of an equality.
Continuity everywhere except where a known step belongs.

**4. Longitudinal control from centerlines.** Welding removes seams but leaves streets
locally smooth and globally aimless — a Laplacian has no notion that forty patches in a row
are 10th Avenue. **NYC Street Centerline (CSCL)** supplies segment→node topology, street
identity for grouping patches into one run, and an axis for enforcing continuous grade
between intersections. Intersection nodes become shared constraints where several streets
must agree — which is how a survey is actually controlled. Source verified below.

### Street centerlines — source verified (2026-08-03)

**`inkn-q76z`**, NYC Open Data, dataset name "Centerline", 122,245 segments citywide.
Socrata SODA, GeoJSON `MultiLineString` in WGS84 — project with the same EPSG:2263 forward
implementation already written for the tile index. Query by
`$where=within_circle(the_geom,lat,lon,metres)`.

Fields that matter, confirmed against a live row:

| Field | Example | Use |
|---|---|---|
| `the_geom` | MultiLineString, WGS84 | the reference line |
| `from_level_code` / `to_level_code` | `13`, `9`, `17`, `21` | **vertical level** — see below |
| `streetwidth` | `34` (ft) | cross-section half-width |
| `number_travel_lanes`, `number_park_lanes`, `number_total_lanes` | `2`, `2`, `4` | lane geometry |
| `trafdir` | `FT` | direction of travel |
| `segmentlength` | `260.14` (ft) | station length |
| `physicalid` | `46810` | stable segment key |
| `rw_type` | `1` | roadway class — **codes not yet verified** |

**The graph is free.** In the 900 m AOI around the site: 539 segments, 1,206 endpoint
references collapsing to **389 distinct coordinates at full floating-point precision** — no
snapping tolerance, exactly as with the planimetric polygon coverage. Node degree
1:14 · 2:126 · 3:81 · 4:149 · 5:14 · 6:4 · 7:1. The degree-1 nodes are the AOI clip edge;
degree 3 and 4 are T- and four-way intersections. Segments at different levels correctly do
*not* share a node where they cross.

**Level codes resolve the multi-level ground problem**, and better than Transportation
Structures (`h9sf-7bej`) does, because the level is carried per segment and is already
attached to the topology rather than needing a spatial join. Distribution in the AOI:

| `(from, to)` | count | reading |
|---|---|---|
| `(13, 13)` | 399 | at grade |
| `(9, 9)` | 56 | below grade |
| `(17, 17)` | 44 | above grade |
| `(21, 21)` | 4 | higher still |
| mixed pairs — `(17,13)`, `(13,9)`, `(13,17)`, `(9,13)`, `(21,17)` | 35 | **the ramps that transition between levels** |

This AOI contains the Lincoln Tunnel helix and the Dyer Avenue approaches, which is exactly
the roads-over-roads case that breaks a single-valued TIN. Segments should be solved per
level, with the mixed-pair ramps as the stitching elements between level sets.

**What CSCL does not give.** No elevation — it is strictly 2D. Z comes from 3DEP sampled
along each centerline and smoothed longitudinally, which is the OpenDRIVE structure exactly:
reference line from CSCL, elevation profile attached to it, cross-section from `streetwidth`
and lane counts, with the planimetric roadbed polygon as the lateral constraint. No curb
geometry either — that is already identified as the 10,601 roadbed↔sidewalk shared vertices.

**Two caveats.** The Socrata publication **drops `NODEIDFROM`/`NODEIDTO`**; DCP's LION
shapefile carries them, but coordinate identity works exactly, so LION is not needed. And
`rw_type` (1 ×320, 9 ×97, 6 ×38, 2 ×28, 3 ×27, 4 ×24, 13 ×5 in the AOI) must be read against
the CSCL data dictionary before filtering on it — 97 segments of one non-street class in a
900 m radius is consistent with tunnel ramps, but the code meanings are unverified.

### Verification — decided in advance

A **seam metric**: for every shared vertex, the maximum |Δz| between incident polygons.

| | now | target |
|---|---|---|
| Non-curb shared vertices | unbounded | **0.0 ft exactly** |
| Curb shared vertices | unbounded | **≈ curb reveal, ~0.5 ft** |

Report p50/p90/max, and re-photograph the same viewpoint as the floating-patch screenshot.
Summary statistics from a different camera angle are not verification — that mistake was
made twice in this document already.

### Risks

- **Solver size.** ~24k unknowns per AOI. Sparse and well conditioned, but needs a sparse
  solver or Gauss–Seidel iteration; dense normal equations will not fit.
- **λ choice.** Too low leaves DEM noise, too high flattens genuine grade. Sweep it and
  validate on both AOIs, as with the 200 SF threshold.
- **Degree-1 vertices** (11,557 of them) have no neighbour constraint and will be driven
  entirely by the data term. The AOI boundary needs explicit handling.
- **The coverage is only clean within a layer set.** Medians, plazas and parking lots have
  not been tested for shared topology with roadbed; verify before assuming.

### Principle

**Coherence is a property of the solve, not of the data.** Every earlier refinement made
each patch individually more correct while the architecture guaranteed they would not agree.
A surveyor never fits patches — they build one surface with breaklines describing where it
is permitted to break.

---

## Prior art and unused data — research sweep (2026-08-02)

Done before building slice G. **The main finding is that slice G is a solved problem** and
should not be written from scratch.

### 3dfier (tudelft3d) — this *is* slice G

`github.com/tudelft3d/3dfier` — TU Delft, open source, Docker image published.

Takes **2D GIS polygons + a LAS/LAZ point cloud** and produces a **watertight 3D city
model**. Its architecture is, line for line, what slice G describes:

- **Semantics drive the lifting** — water polygons extrude to horizontal, buildings to LOD1
  blocks, **roads to smooth surfaces**. Exactly the "fit per surface class" conclusion.
- **Constrained Delaunay triangulation per polygon.**
- Lifted polygons are **"stitched" together into one DSM** — no intersecting triangles, no
  holes. That is the coherence problem, solved structurally.
- **Polygon ID preserved 1-to-1** input to output, so attributes survive.
- Output: OBJ, **CityJSON**, CityGML, PostGIS, STL.

Sibling project **City4CFD** (`tudelft3d/city4cfd`) reconstructs LoD2 models for urban flow
simulation.

**Implication:** the novel part of our work was never the algorithm. It is having this
inside Rhino, driven by Rook, with NYC semantics. Three options, in order of sanity:
1. Run 3dfier as an external process on the planimetric polygons + NYC LiDAR, import the
   CityJSON. Fastest path to a correct ground plane.
2. Port its architecture (semantic lift → CDT → stitch) into the Rook pipeline.
3. Use it as a correctness oracle to check whatever we do build.

Note it consumes **LAS/LAZ directly** — so it wants the raw NYC LiDAR, not my sampled grid.

### ASAM OpenDRIVE — the road connectivity model I was missing

`asam.net/standards/detail/opendrive/` — XML (`.xodr`), industry standard for HD road maps.

- The primitive is the **road reference line**; everything attaches along it.
- **Elevation profile is attached to the reference line** — precisely the longitudinal
  control I identified as missing from a Laplacian solve.
- **Superelevation** is first-class — that is the road crown/cross-slope.
- **Junctions** formalise intersections with predecessor/successor links between roads *and
  between lanes*.

This is the data model for "a street that goes somewhere" rather than "a patch that doesn't
disagree with its neighbour." Worth adopting as the conceptual schema even if we never emit
`.xodr`.

### Constrained Delaunay with breaklines — canonical, confirmed

The surveying method, stated plainly: break lines are drawn along rivers, **edges of roads**,
ridges, and used as **constraints when constructing the triangulation**. Implementations:
**CGAL** `Constrained_Delaunay_triangulation_2` (usable from Python), and **Triangle**.
"Conforming" CDT refines constrained edges until they are Delaunay.

### Data types fetched but still unused

| Layer | Resource | Why it matters |
|---|---|---|
| ~~Street Centerline~~ | `inkn-q76z` | **Source verified 2026-08-03** — see slice G. Still unused, but no longer unknown. |
| Transportation Structures | `h9sf-7bej` | Elevated decks — **largely superseded** by CSCL level codes, which carry level per segment |
| Median, Curb Cut, Pavement Edge | planimetric DB | More breaklines |
| Public Plazas, Parking Lot | planimetric DB | More ground classes |
| **1 ft DEM raster** | `dpc8-z3jc` / `7kuu-zah7` | Denser than the 10 m grid actually sampled |
| **NYC LiDAR point cloud (LAS)** | 3DEP AWS S3, OpenTopography `NY_NewYorkCity` | 3dfier's native input; classified ground returns |

### Strategic read

Every refinement this session was a hand-rolled step toward an architecture that already
exists, is published, and reconstructed the Netherlands. The lesson is not that the work was
wasted — the failure modes found (viaduct contamination, sampling-grid aliasing,
ill-conditioned ribbon fits, seam incoherence) are all real and would have bitten any
implementation. But **the next move is to evaluate 3dfier before writing a solver.**

Sources: [3dfier](https://github.com/tudelft3d/3dfier) ·
[City4CFD](https://github.com/tudelft3d/city4cfd) ·
[TU Delft 3D geoinformation code](https://3d.bk.tudelft.nl/code/) ·
[ASAM OpenDRIVE](https://www.asam.net/standards/detail/opendrive/) ·
[CGAL 2D Triangulations](https://doc.cgal.org/latest/Triangulation_2/index.html)
