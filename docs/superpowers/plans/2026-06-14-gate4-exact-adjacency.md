# Gate 4 — Exact Planar Adjacency Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax. **All work happens in the `rook-spatial`
> worktree on branch `feature/spatial-intelligence`. Verify the branch before every
> commit** (a prior commit mis-landed on a codex branch).

**Goal:** Add lazy, on-demand exact planar shared-face adjacency to Rook as a
separate `ExactAdjacencyService`, leaving the continuous bbox scene graph untouched.

**Architecture:** HTTP worker → action-queued RTree candidate read on the processor
thread → main-thread face extraction (plain structs only) → pure Clipper2-based
planar engine off-thread → cached exact core → coarse-decorated response. Curved is
designed-for (pluggable engine) but flagged-unsupported in v1.

**Tech Stack:** C++17, RookNative plugin, OpenNURBS (`ON_RTree`, Brep faces),
**Clipper2** (Boost Software License) for 2D polygon boolean, `CMainThreadDispatcher`,
`nlohmann/json`, `httplib`.

**Spec (authoritative contract):** `docs/superpowers/specs/2026-06-14-gate4-exact-adjacency-design.md`
— refer to it for every struct field, capability rule, and the precision policy.

---

## File structure

- `src/RookNative/vendor/clipper2/` — vendored Clipper2 (new; authorized dependency)
- `src/RookNative/vendor/versions.txt` — pin Clipper2 version + BSL-1.0 (modify)
- `src/RookNative/SceneGraph/ExactAdjacencyTypes.h` — plain DTOs (new; spec §4)
- `src/RookNative/SceneGraph/PlanarAdjacencyEngine.{h,cpp}` — `IExactAdjacencyEngine`
  + `PlanarAdjacencyEngine` (new; pure, no Rhino/threads — the testable core)
- `src/RookNative/SceneGraph/ExactAdjacencyService.{h,cpp}` — orchestration (new)
- `src/RookNative/SceneGraph/SceneGraph.{h,cpp}` — add `QueryCandidatesAsync` (modify)
- `src/RookNative/Handlers/SceneGraphHandler.cpp` (or owning handler) — route
  `POST /scene/graph/adjacency/exact` + coarse decoration (modify)
- `src/RookNative/RookNative.vcxproj` + `.filters` — include new units (modify; AUTHORIZED)
- Native test target — engine unit tests (location confirmed in Task 0)

---

## Task 0: Confirm test harness + Clipper2 fetch source (no code)

**Files:** none (investigation)

- [ ] **Step 1:** Search for the existing native test pattern.
  Run: `grep -ril "test" src/RookNative --include=*.vcxproj; ls src/RookNative` and
  check `scripts/` for a test runner. Record: is there a native unit-test project, or
  do we add a small standalone test exe for the pure engine?
- [ ] **Step 2:** Confirm Clipper2 acquisition: target the latest Clipper2 C++
  release (`AngusJohnson/Clipper2`, `CPP/` tree: `clipper.core.h`, `clipper.engine.*`,
  `clipper.h`, `clipper.offset.*` — we need core + engine only). Record exact version.
- [ ] **Step 3:** No commit (investigation only). Decide engine-test placement based
  on Step 1; the engine is pure so a standalone test exe is acceptable if no harness.

## Task 1: Vendor Clipper2 (AUTHORIZED dependency step)

**Files:** Create `src/RookNative/vendor/clipper2/*`; Modify `vendor/versions.txt`

- [ ] **Step 1:** Copy Clipper2 `CPP/Clipper2Lib/{include,src}` into
  `src/RookNative/vendor/clipper2/`. Include only `clipper.core.*`, `clipper.engine.*`,
  `clipper.h` (NOT triangulation/offset units we don't use).
- [ ] **Step 2:** Append to `src/RookNative/vendor/versions.txt`:
  `clipper2 <version> — Boost Software License 1.0 — 2D polygon boolean (Intersect/Area)`.
- [ ] **Step 3:** Commit. `git commit -m "deps: vendor Clipper2 (BSL-1.0) for 2D polygon boolean"`

## Task 2: Plain DTOs

**Files:** Create `src/RookNative/SceneGraph/ExactAdjacencyTypes.h`

- [ ] **Step 1:** Transcribe the spec §4 structs verbatim into the header inside
  `namespace Rook`: `FaceKind`, `Capability`, `PlanarFace`, `FaceSummary`,
  `ObjectFaceSummary`, `ExactEdge`, `ExactCandidate`, `ExactAdjacencyCore`,
  `CandidateOutcome`, plus `CandidateQueryOptions`, `ScoredCandidate`,
  `CandidateQueryResult` from §3. Header-only, no Rhino includes. (See spec for exact
  fields — do not improvise names; `ExactAdjacencyCore` carries NO coarse state.)
- [ ] **Step 2:** Add engine constants (spec §5): `constexpr double kNormalTol`,
  `kAreaTol`, `constexpr int kClipperPrecision = 6`, `constexpr int kEngineVersion = 1`.
- [ ] **Step 3:** Commit. `git commit -m "feat(scene): exact-adjacency plain DTOs"`

## Task 3: PlanarAdjacencyEngine — failing test first (the core, pure)

**Files:** Create `PlanarAdjacencyEngine.h`; Test (per Task 0 placement)

- [ ] **Step 1: Write failing tests** on plain `ObjectFaceSummary` inputs (no Rhino).
  Reuse Gate-1/2/3 fixture geometry as 2D/3D loops. Cases (spec §11):
  (a) two coplanar faces, opposing normals, full overlap → one `adjacent_exact`,
      `sharedArea≈faceArea`;
  (b) **same** outward normal, coplanar, overlapping → **no** edge (opposing-normal gate);
  (c) partial overlap (small-on-large) → edge with the small shared area;
  (d) 150mm-gap (different `canonicalPlane`) → no edge;
  (e) outer face with a **hole**, overlap inside the hole → net area excludes hole;
  (f) **concave** L-shaped face overlap → correct net area (Clipper2);
  (g) mixed planar+curved object → `PartialExactUnsupported`, planar still evaluated.

```cpp
// test sketch (framework per Task 0):
ObjectFaceSummary a = makeBox("A", /*...*/), b = makeBox("B", /*adjacent*/);
PlanarAdjacencyEngine eng;
auto r = eng.Evaluate(a, {b}, /*tolerance*/1e-3);
assert(r.edges.size()==1 && r.edges[0].targetId=="B");
assert(approx(r.edges[0].sharedArea, expectedArea));
```

- [ ] **Step 2:** Declare `IExactAdjacencyEngine` (spec §4) and `class
  PlanarAdjacencyEngine : public IExactAdjacencyEngine` with `Evaluate(...) const
  override` in the header.
- [ ] **Step 3:** Run tests → FAIL (link/undefined). Commit the failing tests:
  `git commit -m "test(scene): planar adjacency engine cases (failing)"`

## Task 4: PlanarAdjacencyEngine — implement (Clipper2)

**Files:** Create `PlanarAdjacencyEngine.cpp`

- [ ] **Step 1:** Implement helpers (pure): `canonicalPlaneKey` compare within tol;
  `opposingNormals(nA,nB) = dot < -(1-kNormalTol)`; `projectToPlaneLocal(loop, plane,
  origin)` → 2D minus a **local origin** (source-face centroid; spec §5 precision).
- [ ] **Step 2:** Implement `faceOverlapArea(A,B)`: normalize loops (outer CCW, holes
  CW), build Clipper2 `PathsD` (precision `kClipperPrecision`), **range-guard** scaled
  coords (on overflow → diagnostic + skip pair), `Intersect(a,b,FillRule::NonZero)`,
  return `Area(result)` (net; holes subtract). See spec §5.
- [ ] **Step 3:** Implement `Evaluate`: for each candidate, for each coplanar +
  opposing-normal eligible face pair, sum `faceOverlapArea > kAreaTol`; build
  `ExactEdge`s; roll up `Capability` per spec §5 precedence (Mesh/SubD →
  `UnsupportedGeometry`; none-eligible → `CoarseFallbackExactUnsupported`; some →
  `PartialExactUnsupported`; all → `ExactPlanar`); populate `ExactAdjacencyCore`
  (`candidateCount`, diagnostics with reason codes).
- [ ] **Step 4:** Run tests → PASS. Iterate on precision/orientation until (e) hole
  and (f) concave cases match expected areas.
- [ ] **Step 5:** Commit. `git commit -m "feat(scene): planar adjacency engine via Clipper2"`

## Task 5: CSceneGraph::QueryCandidatesAsync (processor-thread read)

**Files:** Modify `SceneGraph.h`, `SceneGraph.cpp`

- [ ] **Step 1:** Add public `std::future<CandidateQueryResult>
  QueryCandidatesAsync(objectId, CandidateQueryOptions)` declared in `SceneGraph.h`.
- [ ] **Step 2:** Implement via `EnqueueAction([...]{ ... })` so it runs on the
  processor thread (safe `m_rtree` access). Inside: locate source node; gather RTree
  neighbors (reuse `FindNeighborIds` logic); **score each** `(bboxDistance asc,
  bboxOverlap desc, id asc)`; **sort deterministically**; capture `totalCandidateCount`;
  **then cap** to `maxCandidates`; set `capped`; copy `sourceNode` + `graphSequence`.
  (Spec §3 — capping raw RTree order is forbidden.)
- [ ] **Step 3:** Build (`scripts/build-native.bat`) — will fail until Task 9 adds new
  units; this task only touches existing files, so it compiles. Commit.
  `git commit -m "feat(scene): deterministic action-queued candidate query"`

## Task 6: ExactAdjacencyService (orchestration + cache)

**Files:** Create `ExactAdjacencyService.{h,cpp}`

- [ ] **Step 1:** `Compute(objectId, opts)`:
  (1) `CSceneGraph::Instance().QueryCandidatesAsync(...).get()`;
  (2) cache lookup by `CacheKey(objectId, graphSequence, tolerance, maxCandidates,
      kEngineVersion)` (spec §8) → return cached `ExactAdjacencyCore` if hit;
  (3) else `CMainThreadDispatcher::Dispatch([...]{ extract ObjectFaceSummary for
      source+candidates })` (Task 7) with face-count cap + extraction budget;
  (4) `PlanarAdjacencyEngine().Evaluate(...)` → `ExactAdjacencyCore`;
  (5) store in cache; return core.
- [ ] **Step 2:** Cache: `std::unordered_map<CacheKey, ExactAdjacencyCore>` guarded by
  a mutex; drop ALL entries when `graphSequence` advances (compare to last-seen).
  Stores the CORE only — never coarse (type-enforced via `ExactAdjacencyCore`).
- [ ] **Step 3:** Build + commit. `git commit -m "feat(scene): ExactAdjacencyService orchestration + core cache"`

## Task 7: Main-thread face extraction (Rhino → plain structs)

**Files:** `ExactAdjacencyService.cpp` (extraction helper, called inside the Dispatch lambda)

- [ ] **Step 1:** `ExtractObjectFaceSummary(CRhinoDoc&, objectId) -> ObjectFaceSummary`
  (MAIN THREAD ONLY): get `CRhinoObject`; if Mesh/SubD type → `UnsupportedGeometry`.
  For Brep/Extrusion: iterate faces; for each planar face capture the **oriented**
  normal (`outwardNormal`), `canonicalPlane` (sign-folded), outer+inner loops as
  `array<double,3>` lists; mark non-eligible faces with reason codes
  (`curved`/`unoriented`/`malformed`). **No Rhino SDK pointers escape** — only the
  plain `ObjectFaceSummary` is returned. Roll up object `Capability` (spec §5 precedence).
- [ ] **Step 2:** Enforce face-count cap + extraction budget; on exceed → diagnostic
  + `FailedWithDiagnostics` for that object.
- [ ] **Step 3:** Build + commit. `git commit -m "feat(scene): main-thread Brep face-summary extraction"`

## Task 8: HTTP route + coarse decoration

**Files:** Modify the scene-graph HTTP handler (`SceneGraphHandler.cpp` or owner)

- [ ] **Step 1:** Register `POST /scene/graph/adjacency/exact`. Parse
  `{objectId, maxCandidates?, tolerance?, includeCoarse?}` (defaults from spec).
- [ ] **Step 2:** Call `ExactAdjacencyService::Compute(...)` → `ExactAdjacencyCore`.
  Build the response DTO (spec §9): copy core scalars; map `ExactCandidate` →
  `CandidateOutcome`; if `includeCoarse`, decorate each with the live bbox
  relationship from the snapshot (`coarseRelationship`) — **after** cache, never cached.
- [ ] **Step 3:** Serialize with `nlohmann/json` exactly per spec §9 (incl. `capped`,
  `candidateCount`, `candidateLimit`, `totalCandidateCount`, `diagnostics`). Commit.
  `git commit -m "feat(api): POST /scene/graph/adjacency/exact overlay route"`

## Task 9: Project-file inclusion (AUTHORIZED .vcxproj edit)

**Files:** Modify `src/RookNative/RookNative.vcxproj` + `.filters`

- [ ] **Step 1:** Add `<ClCompile>`/`<ClInclude>` entries for: Clipper2 `src/*.cpp` +
  headers, `PlanarAdjacencyEngine.cpp/.h`, `ExactAdjacencyService.cpp/.h`,
  `ExactAdjacencyTypes.h`. Mirror in `.filters`.
- [ ] **Step 2:** Build: `cmd /c scripts\build-native.bat`. Expected: clean compile/link.
- [ ] **Step 3:** Commit. `git commit -m "build: include exact-adjacency + Clipper2 units in RookNative.vcxproj"`

## Task 10: Live-Rhino integration smoke (deploy + exercise)

**Files:** none (manual/scripted smoke per spec §11)

- [ ] **Step 1:** Deploy (`scripts/deploy-native.bat` via `cmd /c`), open Rhino, build
  the storey fixture (or import the Gate-spike STEPs). Hit the route for a wall:
  expect `adjacent_exact` to the slab/window with sane `sharedArea`.
- [ ] **Step 2:** Verify: modify/delete an object → cache invalidates (graphSequence);
  over-cap neighborhood → `capped=true` + `totalCandidateCount`; `includeCoarse`
  true/false both served; a curved object → `CoarseFallbackExactUnsupported` (no false
  exact); mesh → `UnsupportedGeometry`.
- [ ] **Step 3:** Record results in the spike notes; commit any fixes.
  Then request a `native-reviewer` pass (thread-safety / callback-boundary).

---

## Notes for the executor
- **Threading is the risk surface:** `QueryCandidatesAsync` MUST run via `EnqueueAction`
  (processor thread); geometry extraction MUST run inside `CMainThreadDispatcher::Dispatch`
  (main thread) and return only plain structs. The engine is pure (worker thread).
- **Do NOT** add face data/cache to `CSceneGraph` or touch the watcher hot path.
- **Clipper2:** intersection + area only; no triangulation. Local-origin subtraction +
  integer range-guard per spec §5.
- Confirm the exact native test framework in Task 0 before Task 3; the engine is pure
  and standalone-testable if no harness exists.
