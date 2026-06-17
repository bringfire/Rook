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
- Route (modify, all three — Finding 2 of plan-rev-2): `Handlers/SceneGraphHandler.h`
  (declare), `Handlers/SceneGraphHandler.cpp` (implement), `RookServer.cpp` (register
  `POST /scene/graph/adjacency/exact`)
- `src/RookNative/RookNative.vcxproj` + `.filters` — units added per-task (AUTHORIZED)
- **Separate** test project `ExactAdjacencyTests.vcxproj` (its own build target — NOT
  added to the plugin project) compiling the pure engine + Clipper2 + types, no Rhino

> **BUILD POLICY — PCH (Finding 1, verified):** the plugin uses `/Yu stdafx.h`
> globally with NO `NotUsing` precedent. Every new `.cpp` must opt in or out:
> - Clipper2 `.cpp`s and `PlanarAdjacencyEngine.cpp` (pure, Rhino-free) →
>   `<PrecompiledHeader>NotUsing</PrecompiledHeader>` per-file in the vcxproj.
> - `ExactAdjacencyService.cpp` (Rhino-facing: `CRhinoDoc`, dispatcher) → keep PCH
>   (`Use`); it includes `stdafx.h` first like every other plugin unit.
> - The pure engine must NOT pull Rhino SDK via `stdafx.h` (keeps it standalone-testable).

---

## Task 0: Locate test harness + Clipper2 source (investigation, no commit)

**Files:** none. **Use Windows-native commands (`rg`, PowerShell).**

- [ ] **Step 1 (Finding 6):** find any native test target:
  `rg -l -i "gtest|catch2|doctest|CppUnitTest" src/RookNative` and
  `Get-ChildItem -Recurse src/RookNative -Filter *.vcxproj | Select-String -Pattern "test"`.
  Record whether a native unit-test project/framework exists.
- [ ] **Step 2 — define the engine test target (Finding 4):** the engine is pure (no
  Rhino). If a harness exists, follow it. If NONE exists, the plan creates a standalone
  target: test file `src/RookNative/SceneGraph/tests/exact_adjacency_tests.cpp` +
  `ExactAdjacencyTests.vcxproj` — a SEPARATE console-exe target (its own project,
  optionally referenced from the `.sln`; **never nested in / added to
  `RookNative.vcxproj`**). It links ONLY the pure engine + Clipper2 + types — **no
  Rhino SDK, no `stdafx.h`/PCH**. Built via `cmd /c msbuild ExactAdjacencyTests.vcxproj`
  (or the repo's chosen runner). Record exact files + build command — **Task 3 creates
  this target** (the new standalone test `.vcxproj` is AUTHORIZED).
- [ ] **Step 3 — Clipper2 source:** fetch the FULL `CPP/Clipper2Lib/include/clipper2/`
  header tree + `CPP/Clipper2Lib/src/` from `AngusJohnson/Clipper2`; record version.
  Note: `clipper.h` transitively includes offset/rectclip/minkowski/triangulation —
  Task 1 includes engine/core headers DIRECTLY and compiles only the minimal `.cpp` set.
- [ ] No commit (investigation only).

## Task 1: Vendor Clipper2 (AUTHORIZED dependency step)

**Files:** Create `src/RookNative/vendor/clipper2/*`; Modify `vendor/versions.txt`

- [ ] **Step 1 (Finding 3):** copy the FULL `CPP/Clipper2Lib/include/clipper2/` header
  tree into `src/RookNative/vendor/clipper2/include/` (headers cross-reference; do not
  prune them) and `CPP/Clipper2Lib/src/` into `.../src/`. Our code includes
  `clipper2/clipper.engine.h` + `clipper.core.h` **directly** (avoid `clipper.h`, which
  pulls offset/rectclip/minkowski/triangulation).
- [ ] **Step 2 (AUTHORIZED .vcxproj):** add to `RookNative.vcxproj` (+ `.filters`) ONLY
  the `.cpp` units actually required to link `Intersect`+`Area` — begin with
  `clipper.engine.cpp` (+ `clipper.rectclip.cpp` if the linker requires it); do NOT add
  offset/triangulation/minkowski units. **Set `<PrecompiledHeader>NotUsing</PrecompiledHeader>`
  on every Clipper2 `.cpp`** (they don't include `stdafx.h`; without this the `/Yu`
  build fails). Prove the minimal set by compiling a scratch `Intersect`+`Area` smoke;
  if a unit is undefined-at-link, add it and re-record.
- [ ] **Step 3:** Append to `vendor/versions.txt`:
  `clipper2 <version> — Boost Software License 1.0 — 2D polygon boolean (Intersect/Area)`.
  Commit. `git commit -m "deps: vendor Clipper2 (BSL-1.0) + minimal compiled units"`

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
- [ ] **Step 3 (Finding 3 — create the test target HERE so the failure is real):**
  create `ExactAdjacencyTests.vcxproj` per Task 0 — a standalone console exe including
  `exact_adjacency_tests.cpp` + `ExactAdjacencyTypes.h` + `PlanarAdjacencyEngine.h` +
  the Clipper2 units, all `NotUsing` PCH, **no Rhino**. Build it.
- [ ] **Step 4:** Run the test exe → FAIL (link error: `PlanarAdjacencyEngine::Evaluate`
  undefined — not yet implemented). Commit the failing tests + test target:
  `git commit -m "test(scene): planar adjacency engine cases + standalone test target (failing)"`

## Task 4: PlanarAdjacencyEngine — implement (Clipper2)

**Files:** Create `PlanarAdjacencyEngine.cpp`

- [ ] **Step 1:** Implement helpers (pure): `canonicalPlaneKey` compare within tol;
  `opposingNormals(nA,nB) = dot < -(1-kNormalTol)`; `projectToPlaneLocal(loop, plane,
  origin)` → 2D minus a **local origin** (source-face centroid; spec §5 precision).
- [ ] **Step 2:** Implement `faceOverlapArea(A,B)`: normalize loops (outer CCW, holes
  CW), build Clipper2 `PathsD` (precision `kClipperPrecision`), **range-guard** scaled
  coords (on overflow → diagnostic + skip pair), `Intersect(a,b,FillRule::NonZero)`,
  return `Area(result)` (net; holes subtract). See spec §5.
- [ ] **Step 3 (Finding 5 — engine does NOT classify geometry):** implement `Evaluate`
  consuming the per-object `capability` ALREADY assigned by extraction (Task 7). The
  engine only: (a) evaluates eligible planar face pairs (coplanar + opposing-normal),
  summing `faceOverlapArea > kAreaTol` into `ExactEdge`s; (b) sets each candidate's
  `capability = min(source.capability, candidate.capability)`; (c) populates
  `ExactAdjacencyCore` (`candidateCount`, engine diagnostics). It must NOT re-derive
  Mesh/SubD/curved/malformed — that ownership is extraction's.
- [ ] **Step 4:** Run tests → PASS. Iterate on precision/orientation until (e) hole
  and (f) concave cases match expected areas.
- [ ] **Step 5 — add unit to the plugin project WITH this task (AUTHORIZED):** add
  `PlanarAdjacencyEngine.{cpp,h}` + `ExactAdjacencyTypes.h` to `RookNative.vcxproj`/
  `.filters`, with `<PrecompiledHeader>NotUsing</PrecompiledHeader>` on
  `PlanarAdjacencyEngine.cpp` (pure, no `stdafx.h`). **Do NOT add the test project to
  `RookNative.vcxproj`** — `ExactAdjacencyTests.vcxproj` is a separate target (Task 3).
  Build the plugin green, then commit.
  `git commit -m "feat(scene): planar adjacency engine via Clipper2"`

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
- [ ] **Step 3 (Finding 4 — stale wording fixed):** this task modifies ONLY existing
  units (`SceneGraph.h`/`.cpp`), so `cmd /c scripts\build-native.bat` compiles cleanly
  now (no new project entries needed here). Commit.
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
- [ ] **Step 3 (Finding 1):** add `ExactAdjacencyService.{cpp,h}` to
  `RookNative.vcxproj`/`.filters` (AUTHORIZED) so the unit links. Build green, then
  commit. `git commit -m "feat(scene): ExactAdjacencyService orchestration + core cache"`

## Task 7: Main-thread face extraction (Rhino → plain structs)

**Files:** `ExactAdjacencyService.cpp` (extraction helper, called inside the Dispatch lambda)

- [ ] **Step 1:** `ExtractObjectFaceSummary(CRhinoDoc&, objectId) -> ObjectFaceSummary`
  (MAIN THREAD ONLY): get `CRhinoObject`; if Mesh/SubD type → `UnsupportedGeometry`.
  For Brep/Extrusion: iterate faces; for each planar face capture the **oriented**
  normal (`outwardNormal`), `canonicalPlane` (sign-folded), outer+inner loops as
  `array<double,3>` lists; mark non-eligible faces with reason codes
  (`curved`/`unoriented`/`malformed`). **No Rhino SDK pointers escape** — only the
  plain `ObjectFaceSummary` is returned. Roll up object `Capability` (spec §5
  precedence). **Extraction is the SOLE owner of object-capability classification +
  reason-code diagnostics; the engine never re-derives them (Finding 5).**
- [ ] **Step 2:** Enforce face-count cap + extraction budget; on exceed → diagnostic
  + `FailedWithDiagnostics` for that object.
- [ ] **Step 3:** Build + commit. `git commit -m "feat(scene): main-thread Brep face-summary extraction"`

## Task 8: HTTP route + coarse decoration

**Files (Finding 2 — all three):** Modify `src/RookNative/Handlers/SceneGraphHandler.h`
(declare the handler method, near `:13`), `src/RookNative/Handlers/SceneGraphHandler.cpp`
(implement), and `src/RookNative/RookServer.cpp` (register the route near the other
scene-graph route registrations, `~:1766`).

- [ ] **Step 1:** Register `POST /scene/graph/adjacency/exact`. Parse
  `{objectId, maxCandidates?, tolerance?, includeCoarse?}` (defaults from spec).
- [ ] **Step 2:** Call `ExactAdjacencyService::Compute(...)` → `ExactAdjacencyCore`.
  Build the response DTO (spec §9): copy core scalars; map `ExactCandidate` →
  `CandidateOutcome`; if `includeCoarse`, decorate each with the live bbox
  relationship from the snapshot (`coarseRelationship`) — **after** cache, never cached.
- [ ] **Step 3:** Serialize with `nlohmann/json` exactly per spec §9 (incl. `capped`,
  `candidateCount`, `candidateLimit`, `totalCandidateCount`, `diagnostics`). Commit.
  `git commit -m "feat(api): POST /scene/graph/adjacency/exact overlay route"`

## Task 9: Final project-file verification (units added per-task in Tasks 1/4/6)

> Project-file edits now happen WITH each unit-creating task (Finding 1), so by here
> everything links. This task is the consolidation/verification pass.

- [ ] **Step 1:** Confirm `.filters` groups the new units sensibly (SceneGraph/,
  vendor/clipper2/) and that NO offset/triangulation/minkowski Clipper2 `.cpp` snuck
  into the project (only the minimal linked set from Task 1).
- [ ] **Step 2:** Clean full build: `cmd /c scripts\build-native.bat`. Expected: clean
  compile + link, no warnings about the new units.
- [ ] **Step 3:** Commit any `.filters`/project tidy.
  `git commit -m "build: tidy exact-adjacency + Clipper2 project layout"`

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
