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
