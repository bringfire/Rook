# Rook Spatial Intelligence — Foundational Document

> **Current north star (2026-06-28):** This document is retained as historical grounding for
> the OCCT/Topologic evidence gates. For the current canonical architecture framing, use
> `docs/rook_docs/SPATIAL_INTELLIGENCE_NORTH_STAR.md`, especially the
> `RelationshipClaim -> RelationshipEvidence -> RelationshipVerdict` spine.

> **⚠ Extraction note (Slice A, `feature/occt-adjacency-engine`):** This roadmap is retained as the
> parent context for the OCCT engine docs. The FreeCAD grounding-spike harnesses it cites as Gate
> 0–3 evidence (`freecad-spike/*.py` and the `.FCStd`/`.step`/`.ifc` fixtures) and the companion
> `2026-06-13-freecad-rook-bim-architecture.md` are **archived on `feature/spatial-intelligence` and
> omitted from this clean OCCT extraction** — those paths are historical evidence pointers, not
> files present on this branch.

> **Status: FOUNDATIONAL. Thesis UNPROVEN. Discipline-mandated.**
> This document defines the spatial-intelligence core of Rook — a native
> topology/relationship layer that augments the scene graph. It is deliberately
> written to *resist* over-confidence: every claim is tiered VERIFIED / HYPOTHESIS
> / UNKNOWN, and the roadmap is a sequence of falsifiable gates each with a **kill
> criterion**. If a gate fails, we stop and re-ground. This is the core of Rook's
> spatial intelligence; getting it right matters more than getting it fast.
>
> **Provenance:** synthesized 2026-06-13 from live spikes and source reads in this
> session. Companion: `2026-06-13-freecad-rook-bim-architecture.md` (the BIM/source
> side; §11/§12 define the element-vs-relationship boundary this layer realizes).

---

## 1. Thesis & stakes

**Thesis:** Rook can own a spatial-intelligence layer — adjacency, containment,
hosting, circulation, change-impact — that is **equivalent-or-better than
Topologic *for Rook's needs***, built clean-room on permissive/owned foundations,
and **woven into the existing scene graph** rather than bolted on.

**Why it's the core:** every higher capability (perception "why is this here?",
the interiors layout gate, BIM coordination, change-impact reasoning, circulation)
reduces to *relationships between spatial elements*. Today those relationships are
bbox-approximate. Spatial intelligence is the difference between "these two boxes
touch" and "this wall is bounded by that slab and hosts this opening which connects
to that room." This layer is that difference.

**Stakes:** this becomes load-bearing for many features. A wrong abstraction here
propagates everywhere. Hence the discipline mandate below.

---

## 2. Scope — and explicit non-goals

**In scope (the claim we will actually try to prove):** match-or-beat Topologic
for **architectural / scene spatial reasoning** — predominantly planar-polygonal
geometry (walls, slabs, zones, openings, furniture footprints): exact shared-face
adjacency, containment, hosting/apertures, dual-graph extraction, circulation,
change-impact — integrated with the scene graph, keyed by `rookId`, MIT-clean.

**Explicit NON-goals (where "better than Topologic" would be hallucination):**
- ❌ Reimplementing Topologic wholesale.
- ❌ General non-manifold boolean on arbitrary curved B-reps. (That is OCCT's job;
  if we need it we *borrow* OCCT via FreeCAD, §7 — we do not rebuild it.)
- ❌ Graph-ML / energy / shape-grammar breadth Topologic ships.
- ❌ Being a geometry kernel.

"Better" here means **better-integrated and right-sized for Rook** (native to the
scene graph, joined on `rookId`, agent-consumable, permissively licensed) — not
more capable in general. State this every time the claim is repeated.

---

## 3. Evidence ledger (the anti-hallucination spine)

### VERIFIED (this session — evidence in repo)
- **GATE 0 PASSED — Topologic's hard geometry is OCCT all the way down** (read
  `Topologic` C++ core, repo `<repos>/Topologic`, AGPL v3).
  `TopologicCore` (12.7k LOC, 73/105 files reference OCCT). Traced:
  shared-topology = `DownwardNavigation` (`TopExp_Explorer`) + **`IsSame()`**
  (`Topology.cpp:831-868, 3284`); coboundary = `TopExp::MapShapesAndUniqueAncestors`
  (`Cell.cpp:48`, `Face.cpp:65`); non-manifold construction = `BOPAlgo_CellsBuilder`
  / `BOPAlgo_MakerVolume` (`CellComplex.cpp:164,244`). **No novel algorithm** — the
  kernel work is OCCT (LGPL). Topologic's own value = object model + `GlobalCluster`
  (one shared OCCT compound) + `Graph::ByTopology` taxonomy + `Dictionary`/`Aperture`.
- **The adjacency mechanism is OCCT SHARED-IDENTITY (`IsSame`), not geometric
  coincidence.** Cells are adjacent iff they reference the *same OCCT face object* —
  which requires non-manifold construction (`BOPAlgo`) or a shared `GlobalCluster`
  compound. **Disjoint solids (FreeCAD BIM / STEP / layout boxes) do NOT share
  identity** → coincident faces are separate objects → `IsSame` is false. This is
  exactly why FreeCAD `Space` reported no containment (v5). Consequence: imprinting
  coincident-but-separate faces into shared topology (partial overlaps, T-junctions,
  tolerance) is the genuinely hard work — OCCT `BOPAlgo` does it; naive hashing must
  reinvent it. → drives the Path A / Path B decision (§8).
- **Topologic's Python is thin orchestration over a C++ core.** `SharedTopologies`,
  `SuperTopologies`, `Faces(host,…)` all delegate via "Hook to Core"
  (`topologicpy/src/topologicpy/Topology.py:9520, 11979`). The dual-graph builder
  `Graph.ByTopology` (`Graph.py:5911`) is orchestration: cells→nodes@centroid, edge
  policies (direct / viaSharedTopology / viaSharedAperture / toExterior / toContents),
  typed categories, a `Dictionary` per entity.
- **topologicpy is AGPL-3.0** (`topologicpy/LICENSE`) → cannot be embedded in
  network-served Rook. Concepts/algorithms are reusable; code is not. (See the BIM
  doc's licensing matrix.)
- **Rook's scene graph is a networkx `MultiDiGraph` mirror** of the C++ live graph
  (`mcp_server/src/rook/scene/scene_graph.py`). Nodes = whole objects (bbox +
  metrics + shape_class/domain_label + provenance). Edges = relationships
  (contains/supports/above/intersects/adjacent/near) **computed C++-side from
  bounding boxes**. Ships `find_path`, Louvain communities, degree centrality,
  `containment_tree`. **No** sub-object topology, **no** apertures/hosting, **no**
  `rookId` field today.
- **FreeCAD BIM elements are disjoint solids** → no shared topology → no native
  adjacency without an explicit glue step (the v5 interiors spike: `Space.Group`
  empty, placement created no dep edge). So adjacency is *our* computation
  regardless of source.
- **`rookId` is a durable cross-system key** that survives recompute/save/export
  and projects onto Rhino user-strings (BIM doc spikes v2-v4 + live mapping).

### HYPOTHESIS (plausible, NOT yet tested — must be gated)
- Canonical **face-hashing** recovers exact shared-face adjacency for architectural
  (planar-polygonal) scenes, robustly, at real STEP/mesh tolerances. *(Gate 1-2.)*
- The pure-Python path covers the **common** architectural case; OCCT-via-FreeCAD
  is needed only for **exotic** curved/non-manifold geometry. *(Gate 3.)*
- **networkx** is a sufficient substrate at building scale (hundreds–thousands of
  elements). *(Gate 5.)*
- The layer can **augment** the existing scene graph (enrich edges + add cell/face/
  aperture model + `rookId`) without a disproportionate C++ rewrite. *(Gate 4.)*
- "Equivalent-or-better for our scope" holds head-to-head vs Topologic. *(Gate 6.)*

### UNKNOWN (must be explored before relying on it)
- ~~Does face-hashing match OCCT on partial overlaps/tolerance?~~ **RESOLVED
  (Gate 1):** B1 vertex-hash NO (fails partial); **B2 coplanar+2D-overlap YES**
  (matches OCCT). Remaining: B2 general-polygon overlap (currently axis-aligned-rect
  only) needs shapely/clip. *(Gate 2.)*
- ~~C++ vs Python placement~~ **RESOLVED (§6):** geometry/broad/narrow-phase → C++
  (co-located with objects + `ON_RTree`); graph analytics → Python mirror. Decided
  by data-locality + complexity-in-N, grounded in `SceneGraph.cpp`. Prototype in
  Python, port validated narrow-phase to C++.
- Robustness of coincident-face detection under non-matching tessellations,
  T-junctions, partial-face overlaps, tolerance drift.

---

## 4. What we are building

A **topology/relationship layer** that turns geometry + identity into an exact
spatial-relationship graph. Source-agnostic input: `(geometry, rookId,
optional ifcType/params)` per element — origin (FreeCAD BIM, Rook-native layout,
import) is irrelevant. Output: relationship edges + (optionally) a sub-object
topology model, merged into the scene graph and persisted in blueprint.json.

Core capabilities, in dependency order:
1. **Shared-face adjacency** (exact) — replaces/upgrades today's bbox-approximate
   `adjacent`/`intersects`.
2. **Containment** — point/volume-in-cell (exact), upgrades bbox `contains`.
3. **Hosting / apertures** — openings hosted in faces; the host/void relationship
   (the thing FreeCAD models parametrically but doesn't expose as a graph edge).
4. **Dual-graph extraction** — the `by_topology` taxonomy (concept adopted from
   Topologic, code clean-room): cells→nodes, edges by policy (adjacency /
   via-aperture-traversal / to-exterior-egress / contains-furniture), typed,
   metadata per element.
5. **Queries** — circulation (shortest path on the *traversal* subgraph), egress,
   change-impact (what depends on / is bounded by this), adjacency neighborhoods.

---

## 5. Relationship to the scene graph (grounded in the code read)

| | Today (scene_graph.py) | With the topology layer |
|---|---|---|
| Node | whole object (bbox+metrics+class+provenance) | + sub-object entities (face/cell) *optional*; + `rookId` |
| Adjacency | **bbox-approximate** ("boxes touch") | **exact shared-face** |
| Containment | bbox heuristic | exact point/volume-in-cell |
| Hosting/apertures | — none — | `hosts`/`hostedBy`, traversal edges |
| Substrate | networkx MultiDiGraph | **same** — reuse it |
| Algorithms | path, Louvain, centrality, containment_tree | **same, unchanged** — they consume better edges |

**Design intent: augment, not replace.** The networkx substrate and the existing
algorithms stay. The topology layer (a) makes the *edge layer exact* and (b) adds
*new edge types and an optional sub-object model* and (c) adds the *`rookId` join*.
The C++ bbox relationships can remain as a fast broad-phase; exact topology
refines them. **Whether topology edges replace or coexist-with bbox edges is an
open decision (Gate 4), not pre-decided here.**

---

## 6. Architecture placement — C++ vs Python (decided by data-locality, not taste)

**The decision rule (not "pick one for the layer"):** computation goes to the
data; minimize what crosses the HTTP/UI-thread boundary (Rook's core concurrency
constraint). Per stage, ask: *does it touch geometry, and what is its complexity
in N?* Geometry-touching / O(N)–O(N²) stages → **C++**, co-located with the objects
+ RTree. Stages over the *reduced* graph → **Python**. You ship the reduced graph
(N nodes, ~kN edges) across the boundary, **never the geometry**.

**Grounded in the code (read 2026-06-14, `SceneGraph.cpp`):** the existing engine
is already scale-built — `ON_RTree` (OpenNURBS, **free, no OCCT**) broad-phase
(`m_rtree->Search`, :1155), incremental recompute (new+modified nodes only, :619),
narrow-phase = pure bbox predicates (`BBoxDistance`/`OverlapVolume`/`Contains`/
`HorizontalOverlapFraction`, :1173-1203) on RTree candidates. The topology layer's
**exact shared-face narrow-phase slots in right beside those bbox predicates**, on
the same candidates.

| Stage | Geometry? | Complexity | Home |
|---|---|---|---|
| Geometry access (faces/verts) | yes (in Rhino) | O(N) | **C++** |
| Broad-phase (candidates) | bbox | ~O(N log N) RTree | **C++ (exists)** |
| Narrow-phase (exact shared-face) | yes | O(kN) | **C++** |
| Graph build + analytics | no (reduced graph) | O(N+E) | **Python (exists)** |

**Scale consequences (the non-toy requirement):**
- Never move geometry across the boundary → narrow-phase MUST be C++. Path B
  hashing *in Python* would require shipping all face geometry to Python — fatal at
  100k objects.
- **Path B (hashing) in C++ needs no kernel** — OpenNURBS breps + existing RTree,
  O(N). The production target if Gate 1 validates it.
- **Path A (OCCT) does not scale as production narrow-phase** (`BOPAlgo`
  superlinear/fragile; not linked in plugin) → OCCT is the *accuracy oracle on
  subsets*, not the per-pair engine.
- Graph analytics in Python strain only at millions of edges — a later gate; the
  geometry stages bottleneck first.

**Prototype vs production (do not conflate):** Gate 1 prototype in **Python**
(correctness on 3 objects — FreeCAD reads geometry, numpy hashes, diff vs OCCT
oracle); then **port the validated ~dozens-of-lines algorithm into C++** beside the
bbox narrow-phase. Prototype where iteration is fast; ship where the data lives.
(This supersedes the earlier under-considered "leans Python" placement.)

---

## 7. Relationship to FreeCAD (from the BIM-architecture thread)

The topology layer is **source-agnostic**; FreeCAD relates to it in exactly two
narrow, optional ways, never as engine or dependency:
1. **Geometry+identity source** (BIM track) — FreeCAD authors parametric geometry +
   `rookId`; the layer ingests it and computes the relationships FreeCAD
   structurally does not produce (disjoint solids → no native adjacency).
2. **OCCT kernel of last resort** — for curved/non-manifold geometry the
   pure-Python path can't handle, borrow OCCT via `FreeCADCmd` subprocess (LGPL,
   out-of-process). Dark for the common architectural case.

**Decoupling guarantee / correctness test:** the interiors (`rook-layout`) case
must run the *identical* layer with **zero FreeCAD** in-process. If it can't, the
boundary is wrong.

---

## 8. The algorithm core (clean-room, from concepts)

> Concepts and standard algorithms only. No Topologic code is transcribed. The
> non-manifold-topology model, shared-face-as-adjacency, aperture-as-hosting, and
> the by_topology edge taxonomy are *ideas* (and OCCT/published-CS primitives),
> not protected expression.

**Two paths (corrected by Gate 0). Path A is the robust reference; Path B is an
optimization to be validated against it — NOT the assumed primary.**
- **Path A — OCCT (reference & curved engine). CORRECTED PRIMITIVE (Gate 3):**
  adjacency = **`face1.common(face2).Area > 0`** (with a `distToShape` broad-phase),
  which is **surface-agnostic — planar, cylindrical, NURBS, freeform** — and exact.
  ⚠️ Do NOT use `generalFuse`+`isSame` (the Gate-0/1/2 method): `isSame` tests
  object-identity and is FALSE for independently-built coincident faces (failed
  curved C2/C3 in Gate 3). `common().Area` is the right primitive (Gate-3 diagnostic:
  9.42M mm² cylinder, 596K mm² annulus). This is also the corrected Gate-6 oracle.
- **Path B — pure-Python, kernel-free (Gate-1 VALIDATED as B2).** Two sub-methods
  tested: **B1 naive vertex-set hash** (rounded vertex loop) — catches only
  *exact-coincident* faces, **FAILS partial overlaps** (Gate 1 F2). **B2 = coplanar
  grouping + 2D overlap** (group faces by rounded plane; within a plane test 2D
  polygon overlap) — **catches partial overlaps, matches OCCT** (Gate 1). *Use B2.*
  O(n) with plane-bucketing, controllable tolerance (an asset for imperfect
  geometry). General polygons handled by Sutherland-Hodgman clip (Gate 2 — caveat
  closed). **Hard limit (Gate 3): B2 is PLANAR-ONLY** — circular/cylindrical/NURBS
  faces are not polygons; B2 cannot do them.

**TWO-ENGINE ARCHITECTURE (grounded by Gates 1-3) — both first-class, routed per
face/element:**
- **Planar fast path → B2** (pure-Python coplanar + polygon overlap): the orthogonal
  bulk. Fast (~1-3ms), scales, kernel-free.
- **Curved/complex path → OCCT** `face.common().Area > 0`: cylindrical, NURBS,
  freeform. Exact, REQUIRED, slower (~9-47ms). **Committed first-class dependency** —
  curved/complex is core to the work, never sacrificed for zero-dep.
- **Router:** `is_planar(face)` → B2; else OCCT. (Open option, Gate 5: use OCCT
  `common()` *uniformly* for everything and keep B2 only if scale demands the planar
  accelerator — OCCT's primitive handles planar too.)

- **Containment:** point-in-polyhedron (ray/winding) or OCCT `common().Volume`.
- **Hosting/aperture:** opening associated with a host face → `hostedBy` + a
  *traversal* edge distinct from wall-adjacency (Gate 2 validated).
- **Dual graph (`by_topology`):** cell→node@centroid; typed edges per policy;
  `rookId`+metadata on every node/edge → straight into networkx (Gate 2 validated).

---

## 9. Roadmap as grounding gates (each has a KILL criterion)

Sequential. A gate must pass before the next is funded. A failed kill criterion
stops the program and forces re-grounding — that is the point.

- **Gate 0 — Verify the premise. ✅ PASSED (2026-06-14).** Read the `Topologic` C++
  core: hard math is OCCT (`BOPAlgo` construct, `TopExp` navigate, `IsSame` detect);
  no novel algorithm; adjacency = OCCT shared-identity (requires non-manifold build
  or shared compound). Thesis holds; no proprietary algorithm blocks us. Refinement:
  flipped the Path-A/Path-B leaning (§8) — OCCT does real robustness work hashing
  must match. (Evidence in §3 VERIFIED.)
- **Gate 1 — ✅ PASSED for Path B2 (2026-06-14).** Harness `freecad-spike/
  gate1_adjacency.py` on 5 ground-truth fixtures + the storey package. Findings:
  (1) **Naive vertex-hash (B1) FAILS partial overlaps** (column-on-slab) — the
  central risk, confirmed. (2) **Coplanar-grouping + 2D-overlap (B2) catches partial
  overlaps and matches OCCT** on clean/partial/gap/containment. (3) Disjoint solids
  share nothing by raw `isSame` (Gate-0 mechanism re-confirmed). (4) Containment
  caught + separated from adjacency. (5) **Tolerance is a POLICY knob** — OCCT strict
  (~1e-7), B grid-controllable; for imperfect real geometry B's tolerance is
  *preferable*, so "B must match A exactly" was too strict and the divergence favors
  B. (6) B ~2-3× faster, linear; A superlinear. **Algorithm decision: production
  narrow-phase = coplanar + 2D-overlap, NO kernel.** Two bounded follow-ups: B2's
  2D-AABB is exact only for axis-aligned rectangles → **general polygons need true
  2D polygon-overlap** (shapely / Sutherland-Hodgman); Path A (oracle) needs the
  `generalFuse` element-map, not centroid mapping.
- **Gate 2 — ✅ PASSED (2026-06-14).** Harness `freecad-spike/gate2_cellcomplex.py`,
  3-room CellComplex. All checks true: multi-wall adjacency A==truth & B2==A (A|B,
  A|C; corner-only B|C correctly excluded); **Path-A oracle FIXED** via `generalFuse`
  element-map (not centroid); **B2 upgraded to general-polygon** (Sutherland-Hodgman
  clip) — proven to fix the AABB false-positive (two coplanar disjoint triangles:
  AABB says overlap, polygon-clip correctly says none); **apertures→graph**: door in
  shared wall = interior traversal edge, door in exterior wall = edge to EXTERIOR;
  **circulation/egress** via BFS distinguishes adjacency from traversability — room C
  is *adjacent* to A (shared wall) but **sealed (no door) → correctly NO egress**,
  room B reaches exterior via A. B2 ~2.3× faster than A. Adjacency≠traversability is
  now a working distinction.
- **Gate 3 — ✅ PASSED (2026-06-14), with a method-bug caught.** Harness
  `freecad-spike/gate3_curved.py` + `gate3_diag.py` on curved fixtures (column on
  slab / cylinder in tube / cylindrical-shell wall on slab). Findings:
  (1) **Pure-Python B2-exact FAILS curved** — circular & cylindrical faces aren't
  planar polygons (verdict_curved_needs_OCCT = true). B2-tess (tessellation-identity)
  is unreliable (works only by coincidental mesh alignment). **So zero-dep planar
  alone WOULD sacrifice curved capability — confirmed.**
  (2) **My Path-A oracle was wrong** (`generalFuse`+`isSame`) — `isSame` tests
  object-identity, false for independently-built coincident faces; it failed C2/C3.
  The diagnostic (`gate3_diag.py`) proved OCCT *does* see the coincidence:
  `face.common().Area` = 9,424,778 mm² (full cylinder C2) / 596,902 mm² (annular C3).
  (3) **Corrected primitive: `face1.common(face2).Area > 0`** — surface-agnostic
  (planar/cylindrical/NURBS), exact. With it, **OCCT handles all 3 curved cases**.
  This also fixes the Gate-6 equivalence oracle (the old isSame method was unsound).
  Timing: OCCT ~9-47ms vs B2 ~1-3ms (planar) — cost justifies keeping B2 as a planar
  accelerator. **OCCT is a COMMITTED first-class engine for curved/complex, not an
  exotic fallback.**
- **Gate 4 — Scene-graph integration (placement already decided, §6).** Port the
  Gate-1-validated narrow-phase into `CSceneGraph` beside the bbox predicates, on the
  same `ON_RTree` candidates; emit exact shared-face/hosting edges into the Python
  networkx mirror keyed by `rookId`, consumed unchanged by `find_path`/
  `containment_tree`; decide replace-vs-coexist with bbox edges. *Kill:* the C++
  narrow-phase port proves disproportionate to value, or the bbox edges can't be
  cleanly superseded.
- **Gate 5 — Scale.** Realistic building (hundreds–thousands of elements);
  acceptable build + query time. *Kill:* hashing/networkx don't scale → need
  C++/RTree path; re-architect.
- **Gate 6 — Equivalence audit.** Head-to-head vs Topologic on a benchmark set
  (run Topologic locally for ground truth — AGPL is fine for *our own evaluation
  use*); does ours match adjacency/graph output for our scope? *Kill:* systematic
  divergence we can't close → "equivalent" claim retracted, scope honestly reduced.

Only after Gate 6 is the "equivalent-or-better for our scope" claim *earned* and
promotable from HYPOTHESIS to VERIFIED.

---

## 10. Discipline & review protocol

- **Evidence-tiering rule:** no claim enters this doc (or downstream design) as fact
  without an evidence pointer. New claims default to HYPOTHESIS until a gate proves
  them. Repeating "equivalent-or-better" without the "*for our scope*" qualifier is
  a review-blocking error.
- **Clean-room hygiene:** design from concepts/papers/observed behavior + OCCT
  primitives; never transcribe Topologic source. Topologic is run only for
  *evaluation ground truth* (Gate 6), never imported into Rook.
- **Codex rounds** on each gate's spike before it's accepted (per established
  practice for high-stakes, irreversible work — each round catches a different
  class of error; stop when remaining risk is runtime behavior, not static).
- **Observe before theorizing:** every gate is an *executed* spike on real
  geometry, not a paper argument. (The whole BIM thread earned its corrections this
  way — GlobalId, the STEP-flattens-identity finding, the v5 interiors fitness.)

---

## 11. Open questions / risks (live)

- Tessellation/tolerance robustness of face-hashing (the central technical risk).
- C++ vs Python placement + the geometry-exposure prerequisite (§6).
- Replace vs coexist with bbox relationships (§5).
- Where the persisted graph lives long-term (blueprint.json + networkx now; graph
  DB later only if scale demands — do not start there).
- Does the sub-object (face/cell) model get materialized in the scene graph, or
  computed transiently and only relationships persisted? (Memory/scale tradeoff.)

---

## 12. Immediate next step

Gates 0, 1, 2 are ✅ PASSED (see §9). Adjacency = pure-Python **B2** (coplanar +
general-polygon overlap), validated against the OCCT oracle on clean/partial/gap/
containment + a 3-room CellComplex with apertures/egress. **Gate 3 is next:** the
honest curved/non-planar case — does B2 degrade gracefully, and is the OCCT handoff
actually needed, or does coplanar+polygon cover more than expected? Then Gate 4
(port the validated B2 narrow-phase into C++ `CSceneGraph`).

---

## 13. Kernel & dependency strategy (grounded 2026-06-14)

Resolves "how much FreeCAD/OCCT do we need; take only what we need; go to the OCCT
root?" — with sourced facts (research agent) + the Gate 1-2 empirical finding that
**every kernel op we used is pure OCCT-standard** (`generalFuse`/`isSame`/`Faces`/
STEP read) — nothing FreeCAD-specific.

**Three-tier need:**

| Need | Kernel | Delivery |
|---|---|---|
| Production topology runtime (common case) | **none** | B2 in C++/OpenNURBS (`ON_RTree` already present) |
| Dev oracle / Python kernel work (Gate-6 audit, experiments) | OCCT | **OCP (`cadquery-ocp`)** |
| Production curved/complex engine (**COMMITTED — Gate 3 confirmed curved needs OCCT**) | OCCT | raw **OCCT `TK*` DLLs** linked into `RookNative` (C++) |
| BIM source-of-truth (parametric authoring, IFC) | — | **FreeCAD**, out-of-process, optional (external plane) |

**OCP facts (sourced):** Apache-2.0 wrapper over OCCT 7.9.3 (LGPL-2.1 **+ Open
CASCADE exception**). **~46 MB** wheel (vs FreeCAD ~1 GB+), official Windows pip
wheels Py 3.10–3.14, active (rel. May 2026). Full API parity for our ops
(`BOPAlgo_CellsBuilder`, `BRepAlgoAPI`, `TopExp::MapShapesAndUniqueAncestors`,
`TopExp_Explorer`, `STEPControl_Reader`). **Commercial/closed-source safe** — the
OCCT exception lets us ship our code "under terms of our choice"; *not*
copyleft-viral.

**License compliance (if we ship OCCT via OCP or raw DLLs):** (1) keep OCCT as
separate **dynamically-linked** DLLs (wheel already does); (2) add a "Uses Open
CASCADE Technology" notice in docs/about; (3) never statically fold OCCT into a
closed binary; (4) any patches to OCCT *itself* stay LGPL — our own code stays
MIT/closed.

**FreeCAD vs OCCT (confirmed):** raw OCCT = geometry + data-exchange only (incl. an
*optional IFC geometry reader* in OCCT 8.0 — a reader, not authoring). **No**
parametric recompute, **no** Arch/IfcSpace, **no** IFC authoring. FreeCAD adds
exactly those — its value is the **BIM-source track only**, irrelevant to the
topology layer. FreeCAD therefore stays: (a) our *current* dev oracle (already
installed, zero ship cost) and (b) the optional out-of-process BIM authoring engine
— **never a topology dependency, never in core.**

Sources: OCCT LGPL-exception (`Open-Cascade-SAS/OCCT/OCCT_LGPL_EXCEPTION.txt`,
SPDX `OCCT-exception-1.0`); `cadquery-ocp` (PyPI, Apache-2.0 wrapper, win_amd64
wheels); `pythonocc-core` (conda-forge, LGPL-3.0 wrapper — rejected: conda-only +
stricter wrapper); FreeCAD IfcOpenShell docs; OCCT 8.0 FOSDEM 2026 talk.
