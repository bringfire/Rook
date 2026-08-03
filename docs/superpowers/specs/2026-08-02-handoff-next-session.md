# Handoff — NYC context modelling / reasoning-as-dataflow

**Read this, then read the spec. Do not re-derive what is already measured below.**

## Where things are

- **Branch:** `docs/reasoning-as-dataflow-design` (20 commits, off `main`, **nothing pushed**)
- **Spec:** `docs/superpowers/specs/2026-08-01-reasoning-as-dataflow-design.md` (~1,200 lines)
- **Plan:** `docs/superpowers/plans/2026-08-01-findings-to-parameters-spine.md` (slice 1, **not built**)
- **Rhino:** the user **closed the file**. Models were saved to the session scratchpad
  (`502-10th-ave-context.3dm`, `doitt-2014-recon-by-bin.3dm`) — a *new* session has a new
  scratchpad, so treat those as gone unless the user moved them.
- **Test site:** 502 10th Avenue, Manhattan. BBL `1007360001`, CD 104, lat/lon
  40.7570872 / −73.9966792, EPSG:2263 E 985,170 N 215,104.

## Do this first

**Evaluate [3dfier](https://github.com/tudelft3d/3dfier) before writing any terrain solver.**
It already implements the whole "coherent ground surface" slice: 2D polygons + LAS/LAZ →
semantic lifting → constrained Delaunay per polygon → *stitched* watertight DSM → CityJSON,
with polygon IDs preserved. A Docker image is published. The last session hand-rolled most
of the way toward it before finding it.

## Established facts — do not re-derive

**The reconciliation (2014 DOITT model vs current NYC footprints)**
- **Median height delta 0.00 ft**, stable across two AOIs, three pipeline versions and every
  threshold tested. The two datasets are vertically consistent *by construction*.
- The DGN transport **drops BIN**. Join by spatial containment/overlap, not by key.
- The DGN is **closed planar face loops**, not wireframe. It cannot be joined into solids
  because aerial stereo never captured party walls. Build solids by **extruding roof
  polygons down to base and boolean-unioning**.
- Tile index: `DeliveryArea.shp` → DA12 covers this site (39.6 MB of 762 MB).
- **200 SF roof-area filter** for the height comparison, validated on two AOIs. 400 SF scores
  better but strands 2.9% of low-rise buildings into false MISSING.

**Terrain / streetscape**
- **USGS 3DEP** `getSamples` — keyless, 1 m, **must POST** (GET blows the URL limit), returns
  **metres NAVD88** (×3.280839895). Calibrated against NYC building `ground_elevation`:
  **median difference 0.11 ft**.
- Elevation Points `9uxf-ng6q`: **feat 3020/sub 302000 = building** roofs;
  **3000/300000 = ground**. Fetching without `sub_code` puts 1,290 ft rooflines into the
  street surface.
- Planimetric layers share a **uniform schema**, so one reader handles all of them.
- **The coverage is topologically clean**: 12,246 of 23,803 vertices (51.4%) are shared at
  full precision, no tolerance. **10,601 roadbed↔sidewalk shared vertices *are the curb
  line*.** Connectivity is in the data; independent per-polygon processing destroys it.
- Pavement must be **fitted per surface, not sampled** from a height field — sampling
  aliases at the grid pitch because nodes straddle different surfaces.

## Practices learned the hard way

1. **Verify at the same coordinate and the same viewpoint.** Two "fixes" were declared on
   summary statistics plus a *different* camera angle. The user caught both.
2. **Never delete source data.** Park it on a hidden layer. Deleting the DGN curves
   mid-investigation destroyed evidence and forced a re-import.
3. Rhino's default enumerator **skips hidden layers** — pass explicit
   `ObjectEnumeratorSettings`. Hiding a layer before a script ends also keeps the tool from
   dumping thousands of GUIDs into context.
4. **Check the instrument before blaming the data.** A "positional offset in the source" was
   really a vertex-count overlap metric failing where area sampling saw 86% overlap.
5. **Conditioning tests must be relative** at coordinates near 10⁶. An absolute `1e-9`
   determinant threshold produced a polygon 550,168 ft tall.
6. Order of operations dominates: **flat → planar Brep (holes trimmed) → dense mesh → drape.**
   `SimplePlanes=False` or planar faces mesh to two triangles and draping does nothing.

## Open questions

1. **Showcase shape** — one project across several returns, or one return moment in depth.
   Still unanswered; it shapes everything downstream.
2. **Slice 1 (findings → Chirp planner → parameters) is unbuilt.** That is the actual thesis;
   the NYC context work is slice C, which ran in parallel.
3. ~~Multi-level ground~~ — **largely answered 2026-08-03.** CSCL carries
   `from_level_code`/`to_level_code` per segment (13 = grade, 9 below, 17/21 above; mixed
   pairs are the transition ramps). Solve per level set. Transportation Structures
   `h9sf-7bej` is now a cross-check rather than the primary source.
4. Street Centerline `inkn-q76z` — **source verified 2026-08-03, still unbuilt.** Fields,
   level-code distribution and the exact-coincidence node graph (389 nodes from 1,206
   endpoint refs, no tolerance) are in the spec under slice G. It is 2D: Z comes from 3DEP
   sampled along the line. See ASAM OpenDRIVE in the spec for the conceptual schema.

## Tone note

The user is an architect and Rook's author, works empirically, and will call out
over-claiming, chasing the last thing they mentioned, and unverified success claims. Push
back with evidence, admit errors plainly and move on, and prefer measuring to asserting.
