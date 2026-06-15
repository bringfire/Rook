# OcctAdjacencyEngine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Gate-4 hand-rolled Clipper2 planar adjacency engine with a production OCCT-based engine that computes geometric shared-face-area adjacency over arbitrary Breps (planar + curved, open + closed), behind the existing `IExactAdjacencyEngine` seam.

**Architecture:** Main thread deep-copies a per-object `ON_Brep` into a move-only `ObjectBrepPayload` (no Rhino SDK type crosses the seam); a worker thread converts `ON_Brep`→OCCT `TopoDS` (preserving face indices + orientation) and runs serialized `BRepAlgoAPI_Common(faceA,faceB).Area`. The Gate-4 `ExactAdjacencyService` orchestration, cache, three-thread-hop, and HTTP route are kept; only the engine implementation and its data contract change. Temp-STEP survives only as an offline test oracle — never in the runtime path.

**Tech Stack:** C++17, OCCT 7.9.3 (modeling kernel, dynamic-link, LGPL), openNURBS/`ON_Brep` (already linked by RookNative), MSVC v143, MSBuild (`RookNative.vcxproj` + standalone test vcxprojs), Python `urllib` for live HTTP verification.

**Spec:** `docs/superpowers/specs/2026-06-15-occt-adjacency-engine-design.md` (read it first).

**Working location:** worktree `C:/Users/aryan/source/repos/rook-spatial`, branch `feature/spatial-intelligence`. **Verify `git branch --show-current` == `feature/spatial-intelligence` before every commit** (the primary `Rook` dir bounces between Codex worktrees; a prior commit mis-landed).

**Build/deploy/test rhythm (hard constraints):**
- Build (Git Bash): `cmd //c scripts/build-native.bat Release` (delegates to `build_native.ps1`; double-slash escapes MSYS path-mangling).
- Standalone test exes build via their own vcxproj with `msbuild` (see tasks).
- **Deploy requires Rhino CLOSED** (the `.rhp`/DLLs are file-locked while Rhino runs).
- **Live tests require Rhino OPEN** with `C:\Users\aryan\Desktop\SpatialTest.3dm`.
- Reach native HTTP from **Python `urllib`, never `curl`** (security-software constraint).
- The native port changes per Rhino session; discover it by probing the Rhino pid's listening ports for `GET /scene/graph/stats` → 200 (pattern already used in the spikes).

---

## File Structure

**Legacy (frozen, excluded from `.rhp`):**
- `src/RookNative/SceneGraph/legacy/LegacyPlanarAdjacency.h` — NEW. Frozen planar types + interface + `PlanarAdjacencyEngine` decl, all under `namespace Rook::Legacy`.
- `src/RookNative/SceneGraph/legacy/LegacyPlanarAdjacency.cpp` — NEW. Moved body of `PlanarAdjacencyEngine.cpp`, namespaced `Rook::Legacy`.
- Old `SceneGraph/PlanarAdjacencyEngine.{h,cpp}` — DELETED (content moved to legacy/).

**New production contract & engine:**
- `src/RookNative/SceneGraph/OcctAdjacencyTypes.h` — NEW. 4-state `Capability`, `ObjectBrepPayload`, `FacePair`, `ExactEdge` (+`facePairs`), `ExactCandidate`, `ExactAdjacencyCore`, `IExactAdjacencyEngine` (new signature), constants (`kAreaTol`, `kEngineVersion=2`). The shared broad-phase query types (`CandidateQueryOptions`, `ScoredCandidate`, `CandidateQueryResult`) stay in `ExactAdjacencyTypes.h` and are included by both.
- `src/RookNative/SceneGraph/OnBrepToOcct.{h,cpp}` — NEW. `ON_Brep`→`TopoDS` converter + face-index map. Pure openNURBS+OCCT, no Rhino SDK, no STEP.
- `src/RookNative/SceneGraph/OcctAdjacencyEngine.{h,cpp}` — NEW. Implements `IExactAdjacencyEngine` using the converter + `Common().Area` kernel.

**Modified:**
- `src/RookNative/SceneGraph/ExactAdjacencyTypes.h` — drop planar-only members (FaceKind/PlanarFace/FaceSummary/ObjectFaceSummary/old Capability/kNormalTol/kClipperPrecision); keep the broad-phase query types only.
- `src/RookNative/SceneGraph/ExactAdjacencyService.{h,cpp}` — extraction produces `ObjectBrepPayload`; wires `OcctAdjacencyEngine`; merges diagnostics.
- `src/RookNative/Handlers/SceneGraphHandler.cpp` — response gains `lengthUnit`, `areaUnit`, per-edge `facePairs`, new capability strings; retire `HandleOcctProbe` (optional).
- `src/RookNative/RookServer.cpp` — drop the `/scene/occt_probe` route when the tracer is retired.
- `src/RookNative/RookNative.vcxproj` — remove `PlanarAdjacencyEngine.cpp`; add the new cpps with per-file OCCT include; replace hardcoded OCCT path with `$(OcctRoot)`; trim the production TK\* link list to the measured non-DataExchange closure.
- `src/RookNative/ExactAdjacencyTests.vcxproj` — repoint at the legacy header/unit.

**New test targets:**
- `src/RookNative/OcctAdjacencyTests.vcxproj` — NEW. Offline OCCT harness: links openNURBS (read `.3dm`→`ON_Brep`) + OCCT modeling + OCCT DataExchange (read STEP oracle). Builds `SceneGraph/tests/occt_adjacency_tests.cpp`.
- `src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp` — NEW. Converter-fidelity + engine-kernel offline tests.
- `docs/rook_docs/occt-spike/live_verify_occt_adjacency.py` — NEW. Python `urllib` in-plugin verification.

---

## Execution order & buildable-commit discipline (read before starting)

The numeric task order is **not** the execution order, and **every commit on the branch
must build** (no broken-`.rhp` commits — they are rejected). The swap is structured so all
`.rhp`-breaking edits happen inside **one integration task with a single build + single
commit**; everything before it is either additive (the `.rhp` keeps building the old
engine) or offline (independent test exes).

**Shell convention:** all shell snippets run in **Git Bash** (the Bash tool's shell) at the
worktree root `C:/Users/aryan/source/repos/rook-spatial`. Windows paths use forward
slashes; the native build is invoked via `cmd //c scripts/build-native.bat Release`
(double-slash escapes the MSYS path-mangling); `MSBuild.exe` must be on `PATH` (run from a
"Developer Command Prompt"-initialized Git Bash, or call the full VS MSBuild path).

**Phase 1 — additive + offline; `.rhp` stays GREEN on the old Clipper engine. Each task is
its own buildable commit:**
1. **Task 1 (additive)** — create the `Rook::Legacy` unit (new files) + repoint the legacy
   *test* at it; **do NOT delete the old `PlanarAdjacencyEngine.{h,cpp}` and do NOT touch
   `RookNative.vcxproj`** yet. `.rhp` still green (old engine intact); legacy test green.
2. **Task 2 (additive)** — add `OcctAdjacencyTypes.h` as a **standalone** header (does NOT
   include/strip `ExactAdjacencyTypes.h`; no `.rhp` TU includes it, so old and new contract
   types coexist in separate binaries with no ODR clash).
3. **Task 4** — converter surfaces + offline `OcctAdjacencyTests` exe.
4. **Task 5** — converter trims/orientation (oracle match).
5. **Task 6** — `OcctAdjacencyEngine` kernel + offline kernel-primitive robustness matrix.
6. **Task 7 Steps 1–2** — engine-internal diagnostic merge + offline diagnostics test.

Throughout Phase 1 the `.rhp` compiles and runs the Gate-4 Clipper engine; each offline
task ends with a passing `OcctAdjacencyTests.exe` (real, testable progress).

**Phase 2 — ONE integration task (Task 8), ONE build, ONE commit. The only `.rhp`
red→green window lives entirely inside this task and never reaches a commit boundary.**
Task 8 performs, in order, then builds green and commits once:
- delete old `PlanarAdjacencyEngine.{h,cpp}`; remove it from `RookNative.vcxproj`;
- strip `ExactAdjacencyTypes.h` to broad-phase query types; uncomment the
  `ExactAdjacencyTypes.h` include in `OcctAdjacencyTypes.h`;
- migrate `ExactAdjacencyService` extraction → `ObjectBrepPayload` (Task 3 content);
- migrate the handler response (Task 7 Step 3 content);
- wire `OcctAdjacencyEngine`, retire the tracer;
- `cmd //c scripts/build-native.bat Release` → green → single commit.

**Phase 3 — Task 9** build productionization, **Task 10** live verification.

> Tasks 3 and 7-Step-3 below are written as standalone sections for detail, but they are
> **executed as steps inside Task 8** — they are NOT separately committed. This is the
> reviewer-mandated single-integration-block rule.

---

## Task 1: Freeze the Clipper engine as a legacy unit

**Files (additive only — the old files and `RookNative.vcxproj` are NOT touched here; their
removal is Task 8):**
- Create: `src/RookNative/SceneGraph/legacy/LegacyPlanarAdjacency.h`
- Create: `src/RookNative/SceneGraph/legacy/LegacyPlanarAdjacency.cpp`
- Modify: `src/RookNative/SceneGraph/tests/exact_adjacency_tests.cpp` (include path + namespace)
- Modify: `src/RookNative/ExactAdjacencyTests.vcxproj` (point the legacy test at the legacy unit)

- [ ] **Step 1: Create the legacy header** — copy the current `PlanarAdjacencyEngine.h` content AND the planar-only types currently in `ExactAdjacencyTypes.h` (`FaceKind`, `PlanarFace`, `FaceSummary`, `ObjectFaceSummary`, the old 5-state `Capability`, `ExactEdge` without facePairs, `ExactCandidate`, `ExactAdjacencyCore`, `kNormalTol`, `kAreaTol`, `kClipperPrecision`, `kEngineVersion`) into `legacy/LegacyPlanarAdjacency.h`, wrapping everything in `namespace Rook { namespace Legacy { … } }`. The interface becomes `Rook::Legacy::IExactAdjacencyEngine` / `Rook::Legacy::PlanarAdjacencyEngine`. Self-contain the types (don't depend on `ExactAdjacencyTypes.h` for anything Task 8 will strip; if `SceneNode` is referenced, include `SceneGraph/SceneGraphModels.h` directly). The old `Rook::PlanarAdjacencyEngine` and these `Rook::Legacy::` copies coexist — different namespaces, no clash.

- [ ] **Step 2: Create the legacy cpp** — copy the body of `PlanarAdjacencyEngine.cpp` into `legacy/LegacyPlanarAdjacency.cpp`, wrap in `namespace Rook { namespace Legacy { … } }`, update the include to `SceneGraph/legacy/LegacyPlanarAdjacency.h`. No logic changes. (This is a COPY — the original `PlanarAdjacencyEngine.cpp` stays in the `.rhp` until Task 8.)

- [ ] **Step 3: Repoint the legacy test** — in `exact_adjacency_tests.cpp` change `#include "SceneGraph/PlanarAdjacencyEngine.h"` → `#include "SceneGraph/legacy/LegacyPlanarAdjacency.h"` and `using namespace Rook;` → `using namespace Rook::Legacy;`. In `ExactAdjacencyTests.vcxproj` change the `ClCompile` for `SceneGraph\PlanarAdjacencyEngine.cpp` → `SceneGraph\legacy\LegacyPlanarAdjacency.cpp` and the `ClInclude`s to the legacy header (drop the `ExactAdjacencyTypes.h` ClInclude — the legacy header is self-contained).

- [ ] **Step 4: Build the legacy test, verify green**
```
cd src/RookNative
MSBuild.exe ExactAdjacencyTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m
./bin/tests/Debug/x64/ExactAdjacencyTests.exe; echo "exit=$?"
cd ..
```
Expected: builds; exe prints no `FAIL` lines and `exit=0` (the Gate-4 planar cases still pass against the frozen `Rook::Legacy` engine). The `.rhp` is untouched and still green on the old engine.

- [ ] **Step 5: Commit (buildable — old engine intact, legacy test green)**
```
git add src/RookNative/SceneGraph/legacy src/RookNative/ExactAdjacencyTests.vcxproj src/RookNative/SceneGraph/tests/exact_adjacency_tests.cpp
git commit -m "refactor(scene): add Rook::Legacy planar engine unit (additive; old engine still wired)"
```

---

## Task 2: New OCCT contract types + seam

**Files:**
- Create: `src/RookNative/SceneGraph/OcctAdjacencyTypes.h` (Phase 1 — standalone)
- Modify: `src/RookNative/SceneGraph/ExactAdjacencyTypes.h` (Phase 2 — strip planar-only members; keep query types)

- [ ] **Step 1 (Phase 1): Create `OcctAdjacencyTypes.h`** with the exact production contract, **standalone** (it does NOT include `ExactAdjacencyTypes.h` yet — that include is added in the Phase-2 strip step so the new and old contract types coexist without an ODR clash while the `.rhp` is still on the old engine):

```cpp
// OcctAdjacencyTypes.h
// Production exact-adjacency contract for the OCCT engine. openNURBS-based
// (carries an owned ON_Brep); NO Rhino SDK types. Includable by the engine and
// the Rhino-facing service. See 2026-06-15-occt-adjacency-engine-design.md.
// PHASE 1: standalone. PHASE 2: add the ExactAdjacencyTypes.h include below for the
// shared broad-phase query types once that header is stripped of engine-contract types.
#pragma once
// #include "SceneGraph/ExactAdjacencyTypes.h"   // <-- uncomment in Phase 2 (query types)
#include <string>
#include <vector>
#include <memory>

class ON_Brep;   // fwd-decl; only the service/engine TUs include opennurbs

namespace Rook {

enum class Capability {
    ExactBrep,             // all relevant analytic Brep faces converted + evaluated
    PartialExactBrep,      // >=1 face evaluated, some skipped/failed (see diagnostics)
    UnsupportedGeometry,   // mesh / SubD / non-Brep — no analytic exact path
    FailedWithDiagnostics  // object-level failure (bad id / no geom / conversion / cap)
};
const char* CapabilityToString(Capability c);   // defined in OcctAdjacencyEngine.cpp

// Move-only, transient geometry payload. Built per-call on the MAIN thread,
// consumed on the WORKER thread, never copied, never cached.
struct ObjectBrepPayload {
    std::string objectId;
    std::unique_ptr<const ON_Brep> brep;   // owned IMMUTABLE deep-copy; null if unsupported/failed
    Capability capability = Capability::FailedWithDiagnostics;
    double modelUnitsToMillimeters = 1.0;  // doc unit scale (e.g. 25.4 for inches)
    std::vector<std::string> diagnostics;  // extraction reason codes
};

// One contributing coincident face pair (structured, first-class on the edge).
struct FacePair { int sourceFaceIndex; int candidateFaceIndex; double sharedArea; };

struct ExactEdge {
    std::string sourceId, targetId;
    std::string relationship = "adjacent_exact";
    double sharedArea = 0.0;               // model-units^2; sum of facePairs[].sharedArea
    std::vector<FacePair> facePairs;
};

struct ExactCandidate { std::string id; Capability capability; };

struct ExactAdjacencyCore {                // CACHED + serialized (plain data only)
    std::string objectId;
    int graphSequence = 0;
    Capability sourceCapability = Capability::FailedWithDiagnostics;
    std::string lengthUnit = "unknown";    // e.g. "inches"
    std::string areaUnit = "unknown";      // e.g. "inches^2"
    std::vector<ExactEdge> edges;
    std::vector<ExactCandidate> candidates;
    bool capped = false;
    int candidateCount = 0;
    int candidateLimit = 0;
    int totalCandidateCount = 0;
    std::vector<std::string> diagnostics;
};

// Engine constants (covered by kEngineVersion; bump when math/tol/contract changes).
constexpr double kAreaTol      = 1e-6;     // numerical noise floor, model-units^2 (NOT a graze policy)
constexpr double kDefaultFuzzMm = 1e-2;    // default fuzzy in mm; converted to model units per call
constexpr int    kEngineVersion = 2;       // was 1 (Clipper planar); bumped for OCCT contract

class IExactAdjacencyEngine {
public:
    virtual ~IExactAdjacencyEngine() = default;
    // toleranceModelUnits = fuzzMm / modelUnitsToMillimeters (computed by the service).
    virtual ExactAdjacencyCore Evaluate(
        const ObjectBrepPayload& source,
        const std::vector<ObjectBrepPayload>& candidates,
        double toleranceModelUnits) const = 0;
};

} // namespace Rook
```

- [ ] **Step 2 (Phase 1): Commit the standalone header** — it is verified by the offline test build in Task 4 (which includes it). No `.rhp` build here.
```
git add src/RookNative/SceneGraph/OcctAdjacencyTypes.h
git commit -m "feat(scene): OCCT adjacency contract types (4-state Capability, ObjectBrepPayload, facePairs)"
```

- [ ] **Step 3 (Phase 2 — during the migration block): Strip `ExactAdjacencyTypes.h`** to the broad-phase query types only. Keep `CandidateQueryOptions`, `ScoredCandidate`, `CandidateQueryResult` (and the `SceneGraphModels.h` include). Remove `FaceKind`, `PlanarFace`, `FaceSummary`, `ObjectFaceSummary`, the old 5-state `Capability`, the old `ExactEdge`/`ExactCandidate`/`ExactAdjacencyCore`/`CandidateOutcome`, `kNormalTol`, `kAreaTol`, `kClipperPrecision`, `kEngineVersion`. Then **uncomment** the `#include "SceneGraph/ExactAdjacencyTypes.h"` line in `OcctAdjacencyTypes.h`. This step intentionally breaks the `.rhp` (the old service/handler still reference the removed types) — it is recovered by Tasks 3/7/8 within the same migration block. Commit it together with Task 3 (don't leave a lone broken commit):
```
# applied + committed inside the Task 8 integration block, not standalone
```

---

## Task 3: Main-thread extraction → `ObjectBrepPayload` (executed inside Task 8)

> **This task has no standalone commit.** Its content — replacing
> `ExtractObjectFaceSummary` with `ExtractObjectBrepPayload` (owned `ON_Brep` deep-copy,
> capability classification, pinned `ON::UnitScale(... m_unit_system, Millimeters)` unit
> scale), rewiring `Compute`'s move-only dispatch, and the `fuzzMm`→model-units tolerance
> conversion — is **Task 8 Steps 2–3**. It is documented there with the exact pinned API
> and the issue-5 `fuzzMm` separation. Kept here as a cross-reference so the dependency is
> explicit: extraction touches `.rhp`-compiled code, so it lives in the single Phase-2
> integration block, not a separate (broken) commit.

---

## Task 4: `ON_Brep`→`TopoDS` converter — surfaces + face-index map (offline harness)

**Files:**
- Create: `src/RookNative/SceneGraph/OnBrepToOcct.h`
- Create: `src/RookNative/SceneGraph/OnBrepToOcct.cpp`
- Create: `src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp`
- Create: `src/RookNative/OcctAdjacencyTests.vcxproj`

**Converter interface (`OnBrepToOcct.h`) — RAII pimpl result, NO `void*`:**
```cpp
#pragma once
#include <vector>
#include <memory>
class ON_Brep;
namespace Rook {

// RAII owning result of a Brep->OCCT conversion. Holds (pimpl) a TopoDS_Compound of
// the converted faces + a parallel face-index map; OCCT headers live ONLY in the .cpp,
// so this header is OCCT-header-free and safe to include from Rhino-facing TUs
// (mirrors the OcctProbe.h discipline). Move-only; frees the OCCT shape on destruction.
class OcctFaceSet {
public:
    OcctFaceSet();
    ~OcctFaceSet();
    OcctFaceSet(OcctFaceSet&&) noexcept;
    OcctFaceSet& operator=(OcctFaceSet&&) noexcept;
    OcctFaceSet(const OcctFaceSet&) = delete;
    OcctFaceSet& operator=(const OcctFaceSet&) = delete;

    int faceCount() const;                       // number of converted OCCT faces
    int sourceFaceIndex(int occtSlot) const;     // OCCT face slot -> source ON_Brep face index
    const std::vector<int>& failedFaceIndices() const;  // ON_Brep faces that failed conversion

    struct Impl;                                 // defined in OnBrepToOcct.cpp (OCCT types)
    Impl* impl();                                // engine-internal access (kernel reads faces)
    const Impl* impl() const;
private:
    std::unique_ptr<Impl> m_impl;
};

// Convert every analytic face of `brep` to an OCCT face, preserving the SOURCE
// ON_Brep face index for each. Faces that fail conversion are recorded in
// failedFaceIndices() (the engine downgrades the object to PartialExactBrep).
// Pure: no Rhino SDK, no STEP, no threads. Returns an empty set (faceCount()==0)
// if nothing converts.
OcctFaceSet ConvertBrepFaces(const ON_Brep& brep);

}
```
The kernel (Task 6) reaches the OCCT faces via `OcctFaceSet::impl()` inside the OCCT-aware
`.cpp` only. Ownership/lifetime are explicit (RAII, move-only) — no raw `void*`.

- [ ] **Step 1: Write the offline harness test (RED) — surface fidelity.** In `occt_adjacency_tests.cpp`, dependency-free `CHECK`/`CHECK_NEAR` harness (copy the macro style from `exact_adjacency_tests.cpp`). First test: read a known planar object from `SpatialTest.3dm` via openNURBS `ONX_Model`, get its `ON_Brep`, call `ConvertBrepFaces`, sum converted face areas (`BRepGProp::SurfaceProperties`), and compare to the STEP oracle total surface area (read the committed per-object `.stp` via `STEPControl_Reader`), converting in²→mm² (× 645.16) or comparing in consistent units. Assert ratio ≈ 1.0 within 1e-4.

```cpp
// pseudostructure — real openNURBS/OCCT calls filled during impl:
//   ONX_Model m; m.Read(L"C:\\Users\\aryan\\Desktop\\SpatialTest.3dm");
//   const ON_Brep* b = /* component by known GUID 71065f57-... */;
//   Rook::OcctFaceSet fs = Rook::ConvertBrepFaces(*b);   // RAII; owns the OCCT faces
//   double conv = occtFaceSetTotalArea(fs);              // sums via fs.impl() in the .cpp
//   double oracle = stepTotalSurfaceArea("fixtures/71065f57.stp");  // STEPControl_Reader
//   CHECK_NEAR(conv * 645.16, oracle, oracle * 1e-4);    // model in^2 vs STEP mm^2
// (occtFaceSetTotalArea + stepTotalSurfaceArea are test helpers in the OCCT-aware test TU.)
```
> **Implementer note:** the helper names above (`occtFaceSetTotalArea`,
> `stepTotalSurfaceArea`, `sumFaceAreas`) and OCCT call shapes are **illustrative
> scaffolding, not a literal required API**. Converter internals are compiler-and-oracle-
> driven (see Self-Review notes); the binding contract is the oracle area match within
> 1e-4 and the `OcctFaceSet`/`ConvertBrepFaces` signatures in `OnBrepToOcct.h`.

- [ ] **Step 2: Create `OcctAdjacencyTests.vcxproj`** — copy `ExactAdjacencyTests.vcxproj`, change `ProjectGuid` (new GUID), `TargetName`/`RootNamespace` → `OcctAdjacencyTests`. Compile `SceneGraph\tests\occt_adjacency_tests.cpp` + `SceneGraph\OnBrepToOcct.cpp`. Add include dirs: `$(OcctRoot)\inc` and the openNURBS include dir (find it from RookNative.vcxproj's Rhino SDK include path). Link: OCCT modeling + DataExchange TK\* libs (the full Spike-G list is fine for the test target) from `$(OcctRoot)\win64\vc14\lib`, plus the openNURBS lib (`opennurbs_public.lib` or the Rhino SDK's `opennurbs.lib` — resolve from the Rhino SDK lib dir). Set `$(OcctRoot)` via an MSBuild property defaulting to `C:\Users\aryan\source\repos\OCCT\build-rook` (Task 9 makes this an env var across all projects).

- [ ] **Step 3: Generate the STEP oracle fixtures (one-time, offline, dev-only).** With Rhino open on `SpatialTest.3dm`, export the fixture objects (the Spike-A GUIDs: wall `71065f57…`, open floorplate `08d4dedf…`, and its 5 confirmed abutments) to per-object `.stp` files into `src/RookNative/SceneGraph/tests/fixtures/` (gitignored — user geometry). Document the exact GUIDs + export command in a `fixtures/README.md` (committed). This is a **dev/test artifact**; it is never invoked by the runtime.

- [ ] **Step 4: Build the test (verify RED)**
```
cd src/RookNative
MSBuild.exe OcctAdjacencyTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m
cd ..
```
Expected: FAILS to link (unresolved `ConvertBrepFaces`/`OcctFaceSet`) — the RED state.

- [ ] **Step 5: Implement `OcctFaceSet` + `ConvertBrepFaces` surfaces only.** In `OnBrepToOcct.cpp`: define `OcctFaceSet::Impl` (holding a `TopoDS_Compound`/`NCollection_List<TopoDS_Face>` + `std::vector<int>` source-index map + `std::vector<int>` failed). For each `ON_BrepFace`, get `face.SurfaceOf()->NurbsSurface()`, build an OCCT `Geom_BSplineSurface` (poles ÷ W for homogeneous control points; weights; knots with end-knot padding per Spike D); make a face with `BRepBuilderAPI_MakeFace(geomSurf, tol)` (untrimmed full-surface face for now); append to the Impl's list and record the source face index. On any per-face exception, record the index in `failed`. (Trims come in Task 5; untrimmed areas won't match the oracle yet — so this step's test asserts only that conversion *runs* and `faceCount()` is as expected; the area-match assertion is enabled in Task 5.)

- [ ] **Step 6: Adjust the Task-4 test to its achievable bar** — assert `fs.faceCount() == brep->m_F.Count() - fs.failedFaceIndices().size()`, and that the summed areas are finite/positive. (The exact-area oracle match is Task 5's bar, once trimming lands.) Build + run; expect `exit=0`.

- [ ] **Step 7: Commit**
```
git add src/RookNative/SceneGraph/OnBrepToOcct.* src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp src/RookNative/OcctAdjacencyTests.vcxproj src/RookNative/SceneGraph/tests/fixtures/README.md
git commit -m "feat(scene): ON_Brep->OCCT surface converter + face-index map + offline harness"
```

---

## Task 5: Converter trims/pcurves + orientation fidelity

**Files:**
- Modify: `src/RookNative/SceneGraph/OnBrepToOcct.cpp`
- Modify: `src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp`

- [ ] **Step 1: Enable the exact-area oracle assertion (RED).** Turn the Task-4 test's area check into `CHECK_NEAR(conv_in2 * 645.16, oracle_mm2, oracle_mm2 * 1e-4)` for the wall fixture (expected wall total ≈ the Spike-A value). Build + run; expect FAIL (untrimmed full-surface faces over-report area).

- [ ] **Step 2: Implement trims + orientation** in `ConvertBrepFaces`, per spec §3.1:
  - For each face, build a wire per `ON_BrepLoop`: for each `ON_BrepTrim`, copy its pcurve (`trim.TrimCurveOf()->NurbsCurve()`) → OCCT 2D `Geom2d_BSplineCurve` → `BRepBuilderAPI_MakeEdge(pcurve2d, geomSurf)`; honor `trim.m_bRev3d` for edge orientation; `BRepLib::BuildCurves3d` on the edge.
  - **Outer loop** (`ON_BrepLoop::outer`) → bounding wire; **inner loops** (`ON_BrepLoop::inner`) → reversed wires (holes subtract).
  - **Face reversal**: apply `ON_BrepFace::m_bRev` to the OCCT face orientation (`face.Reversed()` / `TopoDS_Face` orientation flag) so the natural normal matches the `ON_Brep` oriented normal.
  - **Seam trims**: handle `ON_BrepTrim::seam` so closed/periodic surfaces (cylinders, full revolves) close properly.
  - **Singular trims**: represent collapsed trims (`ON_BrepTrim::singular`) as OCCT degenerated edges (`BRepBuilderAPI_MakeEdge` degenerate form) — do NOT drop them (dropping leaves an invalid wire).
  - `BRepBuilderAPI_MakeFace(geomSurf, outerWire)` then `.Add(holeWire)`; `ShapeFix_Face` as a *net*, not a corrector — if fixed area disagrees with the oracle it is a converter bug.

- [ ] **Step 3: Build + run (GREEN)** — wall fixture converted area matches the STEP oracle within 1e-4.
```
cd src/RookNative
MSBuild.exe OcctAdjacencyTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m
./bin/tests/Debug/x64/OcctAdjacencyTests.exe; echo "exit=$?"
cd ..
```
Expected: no `FAIL` lines, `exit=0`.

- [ ] **Step 4: Add a curved-face fixture assertion** — convert the curved wall (`7d55840d…`) and assert converted total area matches its STEP oracle within 1e-4 (proves rational/curved trims). Build + run; expect `exit=0`.

- [ ] **Step 5: Commit**
```
git add src/RookNative/SceneGraph/OnBrepToOcct.cpp src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp
git commit -m "feat(scene): converter trims/pcurves + orientation fidelity (Strengthener-1 proof in C++)"
```

---

## Task 6: `OcctAdjacencyEngine` compute kernel

**Files:**
- Create: `src/RookNative/SceneGraph/OcctAdjacencyEngine.h`
- Create: `src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp`
- Modify: `src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp`
- Modify: `src/RookNative/OcctAdjacencyTests.vcxproj` (add `OcctAdjacencyEngine.cpp`)

- [ ] **Step 1: Engine header** — `class OcctAdjacencyEngine : public IExactAdjacencyEngine` overriding `Evaluate`. OCCT-header-free header (like `OnBrepToOcct.h`); include only `OcctAdjacencyTypes.h`.

- [ ] **Step 2: Write the engine kernel test (RED)** — in the offline harness, build two `ObjectBrepPayload`s from two abutting fixtures (wall `71065f57` + the floorplate `08d4dedf`), call `OcctAdjacencyEngine().Evaluate(source, {cand}, tolModelUnits)`, assert: one `ExactEdge` with `sharedArea` ≈ the Spike-A confirmed abutment area (3312 in²) within 1e-3 relative, `facePairs` non-empty and `sum(facePairs.sharedArea) == edge.sharedArea`, `sourceCapability == ExactBrep`. Build → expect link FAIL (RED).

- [ ] **Step 3: Implement `Evaluate`** per spec §3.2:
  - For source + each candidate: `ConvertBrepFaces` (downgrade `capability` to `PartialExactBrep` if `failedFaceIndices` non-empty; if zero faces convert, `UnsupportedGeometry`/`FailedWithDiagnostics`).
  - **Prefilter**: skip face pairs whose OCCT face bounding boxes (`BRepBndLib::Add` → `Bnd_Box`) do not overlap within `toleranceModelUnits`. **No coplanar/planar assumption.**
  - For surviving pairs: `BRepAlgoAPI_Common op; op.SetArguments({faceA}); op.SetTools({faceB}); op.SetFuzzyValue(toleranceModelUnits); op.Build();` guard with `try/catch(Standard_Failure)` AND `if (op.HasErrors()) continue;`. Area = `SurfaceProperties(op.Shape()).Mass()`.
  - Accumulate per (sourceFaceIndex, candFaceIndex); if pair area > `kAreaTol`, append a `FacePair`. After all pairs, if `sum > kAreaTol`, emit one `ExactEdge{sourceId,targetId,"adjacent_exact",sum,facePairs}`.
  - Populate `core.candidates` (id + combined capability), `core.sourceCapability`, and merge diagnostics (Task 7 finalizes the merge namespacing).
  - Serialize OCCT work behind a `static std::mutex` (engine-level; the service also serializes — belt and suspenders for v1).
  - Define `CapabilityToString` here.

- [ ] **Step 4: Build + run (GREEN)** — kernel test passes (abutment area + facePairs + capability). `exit=0`.

- [ ] **Step 5: Port the robustness matrix as a LOWER-LEVEL kernel test (resolved fork).** The 9 `spike_strengthener2_coverage.py` cases test the *coincidence primitive*, not the Brep→payload path. Expose the kernel primitive as a separately-testable free function in `OcctAdjacencyEngine.cpp`'s OCCT-aware TU — e.g. `double SharedFaceArea(const TopoDS_Shape& a, const TopoDS_Shape& b, double fuzz, bool& crashed);` (declared in an internal `OcctAdjacencyEngine_internal.h` included only by OCCT-aware TUs). Build the 9 cases from `BRepPrimAPI_MakeBox`/`MakeCylinder` directly (no `ObjectBrepPayload`, no converter) and assert: abutting→exact(100); gap>fuzzy→0; gap<fuzzy→bridged(100); coincident-duplicate→full overlap, no crash; interpenetration→0 face-adjacency; far-from-origin(+1e6)→exact; sliver→no crash; degenerate→rejected at construction; curved-on-planar→πr². This deliberately tests the primitive at the level Strengthener 2 validated it; the full `Evaluate(ObjectBrepPayload…)` path is covered by Step 2's fixture test + Task 10's live test. Build + run; `exit=0`.

- [ ] **Step 6: Commit**
```
git add src/RookNative/SceneGraph/OcctAdjacencyEngine.* src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp src/RookNative/OcctAdjacencyTests.vcxproj
git commit -m "feat(scene): OcctAdjacencyEngine kernel — Common().Area, prefilter, facePairs, robustness matrix"
```

---

## Task 7: Engine-internal diagnostic propagation (offline; Phase 1)

> Phase 1, offline. The matching **handler/wire-serialization** change is a step of the
> Task 8 integration block (it touches the `.rhp`), NOT here — see issue: never build the
> `.rhp` before Task 8 wires the engine.

**Files:**
- Modify: `src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp` (diagnostic merge)
- Modify: `src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp` (diagnostics test)

- [ ] **Step 1: Engine diagnostic merge.** In `Evaluate`, merge into `core.diagnostics`: source extraction codes prefixed `source:`, each candidate's codes prefixed `cand:<id>:`, engine per-pair failures prefixed `engine:` (conversion failure, `Common` exception/HasErrors). Successful contributions are recorded in `facePairs`, not as strings.

- [ ] **Step 2: Add a diagnostics test** (offline) — feed a payload with `brep=nullptr`/`UnsupportedGeometry` ("mesh") as a candidate; assert the core's `diagnostics` contains `cand:<id>:mesh` and that candidate's `capability == UnsupportedGeometry`, while an `ExactBrep` source with no touching candidate yields zero edges and NO error diagnostic (the tightened no-edge invariant). Build + run the offline exe; `exit=0`.

- [ ] **Step 3: Commit (offline engine only — `.rhp` untouched)**
```
git add src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp
git commit -m "feat(scene): engine-internal diagnostic propagation (source/cand/engine namespaces)"
```

> **The handler wire-serialization** (`lengthUnit`/`areaUnit`/per-edge `facePairs`/new
> capability strings, `CapabilityToString` emitting `exact_brep`/`partial_exact_brep`/
> `unsupported_geometry`/`failed_with_diagnostics`, no `exact_planar`) is **Task 8 Step 5**.

---

## Task 8: Phase-2 integration — single red→green block, ONE build, ONE commit

> This is the ONLY task that breaks then restores the `.rhp`. All `.rhp`-breaking edits
> (old-engine deletion, type strip, service + handler migration, engine wiring, tracer
> removal) happen here and are committed **once, after a green build**. The branch never
> has a broken commit. Do NOT run an intermediate `.rhp` build between the steps.

**Files:**
- Delete: `src/RookNative/SceneGraph/PlanarAdjacencyEngine.{h,cpp}` (old `Rook::` copy; the `Rook::Legacy` copy from Task 1 remains, test-only)
- Delete: `src/RookNative/SceneGraph/OcctProbe.{h,cpp}`
- Modify: `src/RookNative/SceneGraph/ExactAdjacencyTypes.h` (strip to query types — Task 2 Step 3)
- Modify: `src/RookNative/SceneGraph/OcctAdjacencyTypes.h` (uncomment the `ExactAdjacencyTypes.h` include)
- Modify: `src/RookNative/SceneGraph/ExactAdjacencyService.{h,cpp}` (extraction → `ObjectBrepPayload`; engine wiring; units; `fuzzMm` conversion)
- Modify: `src/RookNative/Handlers/SceneGraphHandler.cpp` (response fields; parse `fuzzMm`; remove `HandleOcctProbe`)
- Modify: `src/RookNative/RookServer.cpp` (remove `/scene/occt_probe` route)
- Modify: `src/RookNative/RookNative.vcxproj` (remove `PlanarAdjacencyEngine.cpp` + `OcctProbe.cpp`; add `OnBrepToOcct.cpp` + `OcctAdjacencyEngine.cpp` with per-file OCCT include)

- [ ] **Step 1: Remove the old engine + strip types.** `git rm src/RookNative/SceneGraph/PlanarAdjacencyEngine.h src/RookNative/SceneGraph/PlanarAdjacencyEngine.cpp`. Apply **Task 2 Step 3** (strip `ExactAdjacencyTypes.h` to the broad-phase query types only; uncomment the `#include "SceneGraph/ExactAdjacencyTypes.h"` in `OcctAdjacencyTypes.h`).

- [ ] **Step 2: Migrate `ExactAdjacencyService` extraction (Task 3 content).** Replace `ExtractObjectFaceSummary` with `ExtractObjectBrepPayload(CRhinoDoc&, const std::string&) -> ObjectBrepPayload` (main thread only):
  - bad uuid / `object_not_found` / `no_geometry` → `FailedWithDiagnostics` + reason code, `brep=nullptr`.
  - `ON_Mesh::Cast` / `ON_SubD::Cast` → `UnsupportedGeometry` + `"mesh"`/`"subd"`.
  - Brep, or Extrusion via `ext->BrepForm()` → owned deep-copy `std::unique_ptr<const ON_Brep>(new ON_Brep(*brep))` (Extrusion's `BrepForm()` returns an owned `ON_Brep*` — wrap it directly, don't double-copy). Provisional `capability = ExactBrep`. Non-Brep (curve/point) → `UnsupportedGeometry` + `"no_brep"`.
  - `brep->m_F.Count() > 4000` → `FailedWithDiagnostics` + `"face_cap_exceeded:N"`, `brep=nullptr`.
  - **Unit scale (exact pinned API — matches `SceneGraph.cpp:175`):**
    ```cpp
    payload.modelUnitsToMillimeters = ON::UnitScale(
        doc.Properties().ModelUnitsAndTolerances().m_unit_system,
        ON::LengthUnitSystem::Millimeters);
    ```
  - No Rhino SDK pointer escapes (only the owned `ON_Brep` copy + plain fields).
  - Rewire `Compute`'s `Dispatch` lambda to return move-only `ObjectBrepPayload source` + `std::vector<ObjectBrepPayload> candidates` in the `Extracted` struct; **move** out of the future (`.get()` into a local, then move).

- [ ] **Step 3: Wire the engine + tolerance (Task 3 + the issue-5 fix).** In `Compute`, after extraction:
  - Tolerance: **do NOT reuse `opts.tolerance`** (that field stays model-units, broad-phase). The handler passes a separate `fuzzMm` (Step 5); thread it into `Compute` (add a `double fuzzMm` param defaulting to `kDefaultFuzzMm`). Convert once: `double tolModelUnits = fuzzMm / std::max(1e-12, source.modelUnitsToMillimeters);`.
  - `ExactAdjacencyCore evaluated = OcctAdjacencyEngine().Evaluate(source, candidates, tolModelUnits);`
  - Set `evaluated.lengthUnit` from the doc unit system (reuse/extend the unit-name mapper in `DocumentOpsHandler.cpp`, e.g. "inches"); `evaluated.areaUnit = lengthUnit + "^2"`.
  - Merge the service-owned fields (objectId/graphSequence/candidateLimit/capped/totalCandidateCount) and cache exactly as today (`kEngineVersion==2` auto-drops Gate-4 entries).

- [ ] **Step 4: Add the new cpps to `RookNative.vcxproj`; remove old/tracer.** Add `SceneGraph\OnBrepToOcct.cpp` and `SceneGraph\OcctAdjacencyEngine.cpp` each with the per-file OCCT block (mirror the existing `OcctProbe.cpp` block: `NotUsing` PCH, `<AdditionalIncludeDirectories>$(OcctRoot)\inc;…`, `/bigobj`). Remove the `PlanarAdjacencyEngine.cpp` and `OcctProbe.cpp` `ClCompile` blocks and the `OcctProbe.h` `ClInclude`. `ExactAdjacencyService.cpp`/`SceneGraphHandler.cpp` keep the PCH and include only the OCCT-header-free `OcctAdjacencyEngine.h`/`OnBrepToOcct.h` — OCCT headers never leak into PCH TUs.

- [ ] **Step 5: Handler migration (was Task 7 Step 3) + `fuzzMm` param + tracer removal.** In `SceneGraphHandler.cpp::HandleSceneGraphExactAdjacency`: parse optional `fuzzMm` (default `kDefaultFuzzMm`) from the body and pass it to `Compute`; serialize `out["lengthUnit"]`/`out["areaUnit"]`; per edge add a `facePairs` array (`sourceFaceIndex`/`candidateFaceIndex`/`sharedArea`); `CapabilityToString` emits `exact_brep`/`partial_exact_brep`/`unsupported_geometry`/`failed_with_diagnostics` (no `exact_planar`). Delete `HandleOcctProbe` + its `#include "SceneGraph/OcctProbe.h"`. In `RookServer.cpp` remove the `m_server->Post("/scene/occt_probe", …)` registration (~1796). `git rm src/RookNative/SceneGraph/OcctProbe.h src/RookNative/SceneGraph/OcctProbe.cpp`.

- [ ] **Step 6: Build the `.rhp` (the green restore) + build the offline tests**
```
cmd //c scripts/build-native.bat Release
cd src/RookNative && MSBuild.exe OcctAdjacencyTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m && ./bin/tests/Debug/x64/OcctAdjacencyTests.exe; echo "exit=$?"; cd ..
```
Expected: `.rhp` compiles + links (production engine is now OCCT); offline tests still `exit=0`.

- [ ] **Step 7: Single integration commit**
```
git add -A src/RookNative
git commit -m "feat(scene): integrate OcctAdjacencyEngine — payload extraction, engine wiring, de-planarized wire contract, retire Clipper+tracer"
```

---

## Task 9: Build productionization (OCCT 7.9.3 pin, `$(OcctRoot)`, measured DLL closure, LGPL)

**Files:**
- Modify: `src/RookNative/RookNative.vcxproj`, `src/RookNative/OcctAdjacencyTests.vcxproj` (`$(OcctRoot)` property; trim production link list)
- Create: `docs/rook_docs/occt-build-7.9.3.md` (build + deploy doc)
- Modify: the about/licenses surface (locate via grep) for LGPL attribution

- [ ] **Step 1: Build OCCT 7.9.3.** In `C:/Users/aryan/source/repos/OCCT`, fetch + checkout `V7_9_3`; configure modeling + DataExchange (DataExchange only needed for the test target) into `build-rook-793`; build Release. Document exact cmake flags in `docs/rook_docs/occt-build-7.9.3.md`. (DataExchange in the shared build is fine; the *runtime link list* excludes it — Step 3.)

- [ ] **Step 2: Introduce `$(OcctRoot)`.** Add `<OcctRoot Condition="'$(OcctRoot)'==''">$(OCCT_ROOT)</OcctRoot>` then a fallback default to the 7.9.3 build tree, in a `PropertyGroup` in both vcxprojs. Replace every hardcoded `C:\Users\aryan\source\repos\OCCT\build-rook\…` with `$(OcctRoot)\…`. Document the `OCCT_ROOT` env var in the build doc.

- [ ] **Step 3: Trim the production TK\* link list.** In `RookNative.vcxproj`, reduce `AdditionalDependencies` to the **non-DataExchange** modeling closure required by the converter + kernel (drop `TKDESTEP`, `TKXSBase`, `TKDE`, `TKDECascade`, `TKCAF`, `TKLCAF`, `TKXCAF`, `TKCDF`, `TKExpress`). Build the `.rhp`, then **measure the real closure with `dumpbin`**:
```
cmd //c scripts/build-native.bat Release
dumpbin //DEPENDENTS "src/RookNative/bin/Release/x64/RookNative.rhp" | grep -i "TK"
```
Iterate the link list until it links with the minimal set; record the measured DLL list + total MB in the build doc (target ≈ 15 MB per the spec). If a link error names a missing `TK*`, add exactly that one back.

- [ ] **Step 4: LGPL attribution.** Grep for the existing about/version/licenses surface (e.g. `grep -rn "Uses\|License\|Copyright\|RhinoCommon" src/Rook src/RookNative --include=*.cpp --include=*.cs -l`), add a line: "This software uses Open CASCADE Technology (https://www.opencascade.com), licensed under LGPL 2.1." Confirm OCCT is dynamically linked (it is — DLLs).

- [ ] **Step 5: Commit** (replace `<licenses-file>` with the actual path located in Step 4 — e.g. an about/version `.cpp` in `src/RookNative` or a `.cs` in `src/Rook`; do NOT commit a literal placeholder)
```
git add src/RookNative/RookNative.vcxproj src/RookNative/OcctAdjacencyTests.vcxproj docs/rook_docs/occt-build-7.9.3.md <licenses-file-from-step-4>
git commit -m "build(occt): pin 7.9.3, \$(OcctRoot) property, measured non-DataExchange DLL closure, LGPL attribution"
```

---

## Task 10: In-plugin live verification on `SpatialTest.3dm`

**Files:**
- Create: `docs/rook_docs/occt-spike/live_verify_occt_adjacency.py`

- [ ] **Step 1: Deploy (Rhino CLOSED).** Confirm Rhino is closed, then copy the freshly built `.rhp` + the measured OCCT DLL closure to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\`. (Use the existing deploy script if present; otherwise copy per the Spike-G closure list updated to the 7.9.3 measured set.)

- [ ] **Step 2: Write `live_verify_occt_adjacency.py`** — Python `urllib` (NOT curl). Discover the native port (probe the Rhino pid's listening ports for `GET /scene/graph/stats` → 200). Then `POST /scene/graph/adjacency/exact` with `{objectId, includeCoarse:false}` for: the wall pair, the open floorplate `08d4dedf`, a mesh object, a SubD object. Assert:
  - wall×wall edge `sharedArea` ≈ 18651.672 in² (within 1e-3 relative); `areaUnit=="inches^2"`.
  - floorplate `08d4dedf` recovers the 5 user-confirmed abutments (ids present as edges; the Gate-4 engine returned 0 here).
  - mesh/SubD objects → `sourceCapability` `unsupported_geometry` with a reason code in `diagnostics`.
  - an `ExactBrep` object with no neighbor → zero edges, no error diagnostic.
  - every edge carries non-empty `facePairs` summing to `sharedArea`.

- [ ] **Step 3: Run live (Rhino OPEN)** with `SpatialTest.3dm` loaded:
```
python docs/rook_docs/occt-spike/live_verify_occt_adjacency.py
```
Expected: all assertions PASS; `rhino_ping` (or `/scene/graph/stats`) stays green throughout (UI never blocks).

- [ ] **Step 4: Commit**
```
git add docs/rook_docs/occt-spike/live_verify_occt_adjacency.py
git commit -m "test(scene): in-plugin live verification of OCCT adjacency on SpatialTest.3dm"
```

- [ ] **Step 5: Update the resume docs** — flip `2026-06-14-occt-uniform-engine-decision.md` §6 item 3 to DONE with the live numbers; add a one-line memory pointer update. (Do not merge to `main` — the user pulls the merge trigger per doctrine.)

---

## Self-Review notes (for the executor)

- **OCCT converter internals (Tasks 4–5) are compiler-and-oracle-driven.** The exact `Geom2d_BSplineCurve`/`BRepBuilderAPI` call sequences will be refined against the MSVC compiler and the STEP-oracle area match — the test (oracle within 1e-4) is the contract, not a fixed code listing. This is deliberate: bit-exact OCCT code cannot be authored blind, and orientation bugs hide behind plausible-looking faces (spec §3.1 rationale).
- **Tolerance unit boundary (issue-5 resolution):** there are TWO distinct tolerances. `CandidateQueryOptions.tolerance` stays **model-units** and feeds ONLY the broad-phase candidate query — do not touch its meaning. The OCCT fuzzy is a SEPARATE HTTP param **`fuzzMm`** (mm), converted ONCE in `Compute` (Task 8 Step 3) via `tolModelUnits = fuzzMm / modelUnitsToMillimeters` before reaching `Common`. Never reinterpret `opts.tolerance` as mm; never let an unconverted mm value reach `Common`.
- **Move-only payloads:** `ObjectBrepPayload` never enters the cache or gets copied. Only `ExactAdjacencyCore` (plain data) is cached/serialized. If a build error mentions a deleted copy ctor on a payload vector, you are copying where you must move.
- **`kEngineVersion` is bumped to 2** → the adjacency cache auto-drops Gate-4 entries on first call. Do not also clear manually.
- **No STEP in the runtime path:** if any production TU (compiled into `.rhp`) includes a `STEPControl_*` header, that is a regression against spec §1's invariant. STEP lives only in `OcctAdjacencyTests`.
