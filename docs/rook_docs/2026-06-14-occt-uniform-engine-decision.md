# Spatial Adjacency — Uniform-OCCT Engine Decision & Spike Campaign

> **Status (2026-06-14): DECISION MADE and EMPIRICALLY VALIDATED end-to-end (lab + in-plugin).**
> Adopt a **uniform OCCT adjacency engine** behind the existing pluggable seam.
> Spikes A–E (Python/OCP on real geometry) + Spike G (OCCT linked & running inside
> RookNative) all PASS. Remaining = bounded engineering, not open questions.
> Nothing merged to `main`. All work on branch `feature/spatial-intelligence`
> (worktree `C:/Users/aryan/source/repos/rook-spatial`).

---

## 0. START HERE (fresh-instance resume guide)

**What this is:** the decision record + evidence + reproduction guide for replacing
Rook's hand-rolled planar adjacency engine (Gate 4) with a single OCCT-based engine
that handles planar + curved + open + closed geometry uniformly.

**Read these first, in order:**
1. This doc (decision + spikes + numbers + remaining work).
2. `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md` (the gated roadmap; this supersedes its Gate-4 narrow-phase choice).
3. Memory: `project_spatial_intelligence_topology` (lineage), `project_gh_edit_deferred_solve` (unrelated), `project_freecad_bim_architecture` (kernel licensing matrix).
4. Gate 4 spec/plan: `docs/superpowers/specs/2026-06-14-gate4-exact-adjacency-design.md`, `docs/superpowers/plans/2026-06-14-gate4-exact-adjacency.md`.

**Verify branch before EVERY commit:** `git -C C:/Users/aryan/source/repos/rook-spatial branch --show-current` must print `feature/spatial-intelligence` (the primary `Rook` dir bounces between Codex worktrees; a prior commit once mis-landed).

**Immediate next work (the two strengtheners the user wants, then productionize):**
- **Strengthener 1 — direct converter** (`ON_Brep`→OCCT, off-disk, off-main-thread, ~15 MB footprint). Surface translation already proven; remaining = trims (pcurves→wire→`MakeFace`+`ShapeFix`) + face assembly.
- **Strengthener 2 — messier/varied-geometry coverage** (meshes/open polysurfaces/SubD/dirty → honest degradation; the "any user" guarantee).
- Then the **real `OcctAdjacencyEngine`** behind `IExactAdjacencyEngine`, the **build-system productionization** (pin 7.9.3, env-var paths, deploy subset), and **Spike F** (construction tier → zones).

---

## 1. The decision and why

**Decision:** one **uniform OCCT engine** computes adjacency for all geometry classes
(planar/curved × closed/open) via identity-keyed coincidence
(`BRepAlgoAPI_Common(faceA,faceB).Area` over cross-object face pairs), behind the
**existing `IExactAdjacencyEngine` seam** built in Gate 4. The hand-rolled Clipper2
planar engine (`PlanarAdjacencyEngine`) is **shelved behind that seam** as a possible
*measured-later* planar accelerator — not deleted, not the default.

**Why uniform, not a planar/curved split (the "chimera" question):** OCCT enters the
plugin the moment curved geometry is supported (it must, for arbitrary users). So
uniform pays the OCCT cost *once* and covers all quadrants; a split *adds* a second
engine + a planar↔curved seam + two tolerance models for speed we don't need (the
path is lazy + cached). Going uniform also **deletes** the opposing-normal predicate
and the `IsSolid()` gate — the exact things that made the hand-rolled engine blind to
open geometry. The split's only benefit (planar speed) is unnecessary: Spike B shows
lazy queries are tens of ms and full batch is ~3.7 s.

**Why this is not seesawing:** the through-line is stable — the pluggable engine seam
(designed in Gate 4) is correct; only the *default implementation behind it* changed,
from Clipper2-planar to OCCT-uniform, decided by **measurement on real geometry**, not
argument. Gate 4 was the necessary Phase 1 that built the chassis and taught us the
problem shape (the `IsSolid` gate failing on open geometry, the four quadrants).

---

## 2. Architecture: keep / replace ledger

The Gate 4 service architecture is engine-agnostic chassis — almost all of it stays.

**KEEP (unchanged):**
- `CSceneGraph` — bbox-only, background-thread, `ON_RTree`, broad-phase only. **OCCT never enters the scene graph.**
- `CSceneGraph::QueryCandidatesAsync` (SceneGraph.cpp) — processor-thread, deterministic scored+capped candidate query. Any engine needs this broad phase.
- `ExactAdjacencyService` (SceneGraph/ExactAdjacencyService.{h,cpp}) — orchestration + cache (key incl. graphSequence+engineVersion, drop-on-sequence-advance) + the three-thread-hop discipline.
- `IExactAdjacencyEngine` seam (SceneGraph/PlanarAdjacencyEngine.h) — the swap point.
- HTTP route `POST /scene/graph/adjacency/exact` + response DTO (SceneGraphHandler.cpp).
- Test fixtures/expected areas (re-point at the OCCT engine as its correctness spec).
- Clipper2 vendored (`vendor/clipper2/`) — harmless; available if a planar accelerator is ever measured-necessary.

**REPLACE / SHELVE:**
- `PlanarAdjacencyEngine` (Clipper2 + opposing-normal + projection) → shelved behind the seam; a new `OcctAdjacencyEngine` becomes default.
- `IsSolid()` gate + opposing-normal predicate → **deleted** (OCCT `Common()` needs neither; identity-keying disambiguates).
- Main-thread extraction's per-face projection → becomes "deep-copy `ON_Brep` on main thread; convert + `Common()` on worker."

**NEW WORK:**
- `OcctAdjacencyEngine` (OCCT `Common().Area`, identity-keyed) behind the seam.
- `ON_Brep`→OCCT `TopoDS` conversion (direct converter, or temp-STEP v1).
- OCCT integration into the RookNative build (productionized).
- Fix the Gate-4 **diagnostic-propagation bug** (per-face reason codes — "curved"/"unoriented"/"mesh" — currently don't reach the HTTP response; the honest-degradation invariant requires they do).

**Threading (preserved from Gate 4, validated):**
- HTTP worker → `QueryCandidatesAsync` (processor thread, RTree) → **main thread**: deep-copy `ON_Brep` only (no Rhino SDK pointer crosses the boundary) → **worker thread**: `ON_Brep`→`TopoDS` convert + OCCT `Common()` (pure, off the UI thread) → cache → route. UI never blocks.

**Concurrency policy (Spike E + research):**
- **v1 = serialized OCCT** (single worker queue / mutex). Safe, correct (Spike E proved it), and lazy+cached makes it cheap. The tracer's `HandleOcctProbe` already serializes via a static mutex.
- **Later, if batch throughput demands multi-core:** prefer OCCT internal parallelism (`SetRunParallel`) on the big construction-tier ops, or a **process-pool** of single-threaded OCCT workers. **Hand-rolled shared-memory threading of OCCT booleans is explicitly OUT OF SCOPE** — OCCT booleans are documented not-thread-safe (static-init races, boolean non-thread-safety, allocator-mutex serialization).

---

## 3. Spike campaign — evidence

All spikes ran on the real model **`C:\Users\aryan\Desktop\SpatialTest.3dm`** (61 active
objects: A-WALL/I-WALL/A-FLOR/A-DOOR/stairs/handrails/columns/slabs; the .3dm has 4506
objects incl. block instances). **Units = inches; STEP export = mm; in²→mm² = 645.16.**
Scripts: `docs/rook_docs/occt-spike/spike_*.py` (committed). STEP geometry under
`occt-spike/steps/` is **gitignored** (don't commit user geometry).

### Spike A — correctness — PASS (user-confirmed)
- Method: face-pair `BRepAlgoAPI_Common().Area` (NOTE: **solid-solid `Common` returns empty** for touching solids — measure-zero volume; must do **face-pair**).
- Exact agreement with the Gate-4 Clipper engine on 3 solid pairs (ratio 1.0000): e.g. wall×wall = 18651.672 in² = 12,033,312.7 mm².
- **Open floorplate `08d4dedf`** (Gate-4 engine: 0 edges, structurally blind) → OCCT recovered **5 real abutments the user confirmed by eye**: A-WALL `71065f57` (3312 in²), Triage `5c12cc83`/`be0ca730` (~5440/5423), I-WALL `7e80db98`/`26b2c012` (~1040/1055). Plus a 1.69 in² sliver `502898fc` (real, see C).
- Curved wall `7d55840d`: both engines found 0 shared face area (honest agreement; no positive curved-shared-face case in this model — curved `Common` itself was proven in Gate 3 synthetically).

### Spike B — latency/scale — PASS (accelerator unneeded)
OCP/Python = pessimistic upper bound (C++ faster). With a cheap coplanar prefilter
(→ ~22–34 `Common` calls/object): lazy per-object **46–111 ms**; **full-model batch
(61 obj/229 pairs) = 3.69 s**. Caveat: heavily-curved models prefilter less (more
`Common` calls), still seconds; lazy is the default.

### Spike C — tolerance — PASS
- **`fuzz=0` finds nothing** even for confirmed contacts (real coincident faces aren't exact to machine precision) → **a nonzero fuzzy is mandatory.**
- Real adjacencies **rock-stable across `[1e-4 mm, 0.1 in]`** (identical areas over 4+ orders) → tolerance tuning is trivial; default ~`1e-3`–`1e-2` mm.
- The 1.69 in² sliver is **stable across tolerances = a real small graze**, not noise. Surfacing trivial grazes is an **`areaTol` min-area policy** (a knob), not a correctness issue.

### Spike D — conversion — PASS / de-risked
- No off-the-shelf `ON_Brep`→`TopoDS` converter; Rhino **can't** export STEP to memory (`FileStp` file-based); OCCT side **can** `ReadStream`.
- STEP round-trip is **faithful** (Spike A exact areas). STEP read ~7–16 ms/object.
- **Direct converter surface translation proven machine-exact** (`spike_d_converter.py`): rebuilt real curved+planar NURBS surfaces from `rhino3dm` into OCCT `Geom_BSplineSurface`, max deviation **~8e-12 mm** — *after* fixing the gotcha that `rhino3dm` `Point4d` control points are **homogeneous** (divide by W for OCCT euclidean poles + weight) and that `rhino3dm` knot vectors need an end-knot prepended/appended for OCCT's flat-knot convention.
- Remaining (unspiked) = trims/pcurves→wire→`MakeFace`+`ShapeFix` + face assembly (same NURBS-curve mechanics; medium effort). Temp-STEP is the proven fallback.

### Spike E — thread-safety — PARTIAL PASS
8 threads × face-pair `Common`: 0 crashes, results identical to single-threaded — but
no speedup (OCP holds the GIL), so this **proves serialized-OCCT is safe/correct** (the
v1 policy) and does **not** prove true multi-core. Research confirms OCCT booleans are
not-thread-safe by default → serialize for v1 (see §2 concurrency policy).

### Spike G — OCCT in the C++ plugin — PASS (the gate)
- OCCT 8.0 (modeling+STEP, **source-built**) **compiles + links + initializes + runs inside RookNative**. `POST /scene/occt_probe` returned **12,033,312.694 mm²** — bit-identical to the Python baseline. (First call 2.2 s = cold OCCT static-init.)
- **DLL closure, measured:** 23 DLLs / **34.4 MB** (STEP path drags `TKDESTEP→TKXCAF→TKV3d/TKService/…`). **Direct converter (no STEP) ≈ 15 MB.** Full runtime = 65 MB.
- Rhino **finds OCCT DLLs next to the `.rhp`** (plugin loaded + `rhino_ping` green) → no `AddDllDirectory` needed.
- OCCT-only unit + plain interface compiles cleanly alongside the Rhino SDK (no header clash).
- **OCCT 8.0 API churn observed** (`TopTools_ListOfShape` alias deprecated → use `NCollection_List<TopoDS_Shape>`; `Standard_False` deprecated → `false`) → **pin 7.9.3 in production** (what A–E validated; has official wheels).

---

## 4. Key grounded numbers (decision inputs)

| Question | Answer (measured) |
|---|---|
| Correctness | OCCT == Gate-4 engine on solids (ratio 1.0000); recovers open geometry (user-confirmed) |
| Lazy latency | 46–111 ms/object (Python upper bound; C++ faster) |
| Batch latency | 3.69 s / 61 objects (Python upper bound) |
| Tolerance | nonzero fuzzy mandatory; stable over `[1e-4 mm, 0.1 in]`; default ~1e-3–1e-2 mm |
| Conversion fidelity | machine-exact (~1e-11 mm) incl. rational curved surfaces |
| Footprint (STEP path) | **34.4 MB** (23 DLLs) |
| Footprint (direct converter) | **~15 MB** |
| Footprint (full runtime) | 65 MB (not shipped) |
| Version to pin | **OCCT 7.9.3** (8.0 has API churn) |
| Concurrency | serialized v1; multi-core via internal-parallel/process-pool later |

---

## 5. Reproduction & current state

**Toolchain installed (system Python 3.13):** `cadquery-ocp` 7.9.3 (`import OCP`),
`rhino3dm`. (`pip install cadquery-ocp rhino3dm`.)

**OCCT source build (Spike G):**
- Source: `C:/Users/aryan/source/repos/OCCT` (shallow @ **V8_0_0** — for production, fetch/checkout **V7_9_3**).
- Configure (VS2022 cmake): modeling + DataExchange modules, viz/OCAF/Draw off, `BUILD_LIBRARY_TYPE=Shared`, all `USE_*` 3rd-party OFF. (DataExchange still pulled XCAF/viz toolkits transitively.)
- Build: `cmake --build build-rook --config Release --target install --parallel` (note: `INSTALL_DIR` var failed to expand → use the **build tree** directly).
- Outputs: headers `build-rook/inc`, libs `build-rook/win64/vc14/lib`, dlls `build-rook/win64/vc14/bin` (48 TK*.dll / 49 MB built).

**In-plugin probe (Spike G) — files (committed `e49d56bb`):**
- `src/RookNative/SceneGraph/OcctProbe.{h,cpp}` — OCCT-only unit (no Rhino/stdafx, NotUsing PCH, `/bigobj`, per-file OCCT include path). Plain interface; `OcctProbeInit()` (OSD::SetSignal) + `OcctProbeSharedArea(stepA, stepB, diag)`.
- `Handlers/SceneGraphHandler.cpp` — `HandleOcctProbe` (serialized via static mutex).
- `RookServer.cpp` (~:1796) — route `POST /scene/occt_probe`.
- `RookNative.vcxproj` — OcctProbe.cpp entry + Release Link `AdditionalLibraryDirectories`/`AdditionalDependencies` (TK* subset). **Hardcoded absolute OCCT path = tracer shortcut; productionize to a property/env var.**

**Build/deploy/run the probe:**
- Build: `cmd /c scripts\build-native.bat Release` (or `build_native.ps1 -Configuration Release`).
- Deploy: copy `.rhp` + the 23-DLL closure to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` (closure list in `spike` commit message / §3 G).
- Run: find native port (probe Rhino pid's listening ports for `GET /scene/graph/stats` → 200), then `POST /scene/occt_probe {stepA, stepB}` (paths to per-object STEP files). NOTE: native port changes per Rhino session.
- Native route HTTP is reached from Python `urllib` (NOT curl — user's security-software constraint allows direct HTTP, just not curl).

**Currently deployed:** the **tracer build** (adds `/scene/occt_probe`; everything else
unchanged & working; `rhino_ping` green). `main` untouched. Branch
`feature/spatial-intelligence`; latest commit `e49d56bb`. Gate-4 commits `3fceb52b..37fb9542`.

---

## 6. Remaining work (ordered)

1. **Strengthener 1 — direct converter** (`ON_Brep`→`TopoDS`): trims (pcurve→wire→`BRepBuilderAPI_MakeFace`+`ShapeFix`) + face assembly. Surface translation proven (`spike_d_converter.py`). Payoff: off-disk, off-main-thread, ~15 MB footprint, drops the STEP/XCAF/viz DLL chain.
2. **Strengthener 2 — messier/varied-geometry coverage**: meshes (honest `unsupported`), open polysurfaces, SubD, gappy/duplicate/far-from-origin → confirm honest degradation across the input space (the "any user" guarantee). Get a second, dirtier model.
3. **Real `OcctAdjacencyEngine`** behind `IExactAdjacencyEngine`: identity-keyed cross-object `Common().Area`; deep-copy `ON_Brep` on main thread; convert + `Common` on worker (serialized); cache; **fix diagnostic propagation** (reason codes → response); `areaTol` min-area policy + nonzero-fuzzy tolerance policy (surfaced, not hidden).
4. **Build-system productionization**: pin **OCCT 7.9.3**; source-build with module selection; replace hardcoded vcxproj path with a property/env var; deploy only the measured DLL closure; LGPL compliance (dynamic-link + "Uses Open CASCADE Technology" attribution).
5. **Spike F (deferred)** — construction tier: `BOPAlgo_MakerVolume`/`CellsBuilder` → enclosed cells (zones/IfcSpace), shared-face adjacency by topological identity (`TopExp::MapShapesAndUniqueAncestors`+`IsSame`), apertures→circulation. This is the **next capability** (zones/circulation), not part of the adjacency engine. OCCT internal `SetRunParallel` is the parallelism lever here. **The graph/intelligence layer that consumes all this — projection model, IFC-aligned edge ontology, space-syntax analytics, open design forks — is captured in `2026-06-14-spatial-graph-projection-design.md` (the engine makes the edges; that doc is the graph those edges feed).**
6. **Merge**: after strengtheners + real engine + correctness spot-checks, the user pulls the merge trigger (per doctrine). Gate-4 planar engine stays shelved as a possible accelerator.

---

## 7. Open decisions / risks

- **Direct-converter trim half unproven** (medium effort/risk; temp-STEP fallback exists). Strengthener 1 closes it.
- **OCCT version pin** 7.9.3 vs 8.0.0 — recommend 7.9.3; confirm before productionizing (8.0 API churn already cost two fixes).
- **`areaTol` threshold** — product decision: do tiny grazes (e.g. 1.69 in²) count as adjacency?
- **Edge/angled contact** — face-area adjacency reports 0 for elements meeting at an edge (both Clipper and OCCT). If "edge contact = adjacency" is wanted, that's a *separate relation* (shared-edge / `DistShapeShape`), above either engine.
- **Far-from-origin** — model is −630..+505 (in); OCCT handled it in-plugin fine; extreme coordinates remain a watch item (local-origin handling).
- **Construction tier robustness/scale** (Spike F) — `MakerVolume` can silently drop faces (warnings, not errors); needs validation on real conditioned geometry.
