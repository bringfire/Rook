# OcctAdjacencyEngine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Gate-4 hand-rolled Clipper2 planar adjacency engine with a production OCCT-based engine that computes geometric shared-face-area adjacency over arbitrary Breps (planar + curved, open + closed), behind the existing `IExactAdjacencyEngine` seam.

**Architecture:** Main thread deep-copies a per-object `ON_Brep` into a move-only `ObjectBrepPayload` (no Rhino SDK type crosses the seam); a worker thread converts `ON_Brep`→OCCT `TopoDS` (preserving face indices + orientation) and runs serialized `BRepAlgoAPI_Common(faceA,faceB).Area`. The Gate-4 `ExactAdjacencyService` orchestration, cache, three-thread-hop, and HTTP route are kept; only the engine implementation and its data contract change. Temp-STEP survives only as an offline test oracle — never in the runtime path.

**Tech Stack:** C++17, OCCT 7.9.3 (modeling kernel, dynamic-link, LGPL), openNURBS/`ON_Brep` (already linked by RookNative), MSVC v143, MSBuild (`RookNative.vcxproj` + standalone test vcxprojs), Python `urllib` for live HTTP verification.

**Spec:** `docs/superpowers/specs/2026-06-15-occt-adjacency-engine-design.md` (read it first).

**Working location:** worktree `C:/Users/aryan/source/repos/rook-spatial`, branch `feature/spatial-intelligence`. **Verify `git branch --show-current` == `feature/spatial-intelligence` before every commit** (the primary `Rook` dir bounces between Codex worktrees; a prior commit mis-landed).

**Build/deploy/test rhythm (hard constraints):**
- Build: `cmd /c scripts\build-native.bat Release` (delegates to `build_native.ps1`).
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

## Execution order & the `.rhp` red window (read before starting)

The numeric task order is **not** the safe execution order. The `.rhp` must stay green
as long as possible, and an engine swap has exactly one unavoidable red→green window.
Execute in two phases:

**Phase 1 — offline, `.rhp` stays GREEN on the old Clipper engine** (no production-compiled
file is broken):
1. **Task 2** — add `OcctAdjacencyTypes.h` as a **standalone** header (it does NOT include
   `ExactAdjacencyTypes.h` and does NOT strip it yet; no `.rhp` TU includes it yet, so the
   old `Rook::Capability`/`ExactAdjacencyCore` and the new ones coexist in separate
   binaries with no ODR clash).
2. **Task 4** — converter surfaces + offline `OcctAdjacencyTests` exe.
3. **Task 5** — converter trims/orientation (oracle match).
4. **Task 6** — `OcctAdjacencyEngine` kernel + robustness matrix (offline exe).
5. **Task 7 Steps 1–2** — engine-internal diagnostic merge + offline diagnostics test.

Throughout Phase 1 the `.rhp` still compiles and runs the Gate-4 Clipper engine. Do NOT
yet remove `PlanarAdjacencyEngine.cpp` from `RookNative.vcxproj`, do NOT strip
`ExactAdjacencyTypes.h`, do NOT change `ExactAdjacencyService`/the handler.

**Phase 2 — the single `.rhp` migration block (one red→green transition):**
6. **Task 1** — freeze Clipper as `Rook::Legacy`, drop from `.rhp`. (`.rhp` now RED — the
   service still calls the now-removed engine.)
7. **Task 2 strip step** — remove the old engine-contract types from `ExactAdjacencyTypes.h`
   (keep only the broad-phase query types); add `#include "SceneGraph/ExactAdjacencyTypes.h"`
   to `OcctAdjacencyTypes.h` for those query types.
8. **Task 3** — service extraction → `ObjectBrepPayload`.
9. **Task 7 Step 3** — handler response migration.
10. **Task 8** — wire `OcctAdjacencyEngine` into the service, retire the tracer →
    **`.rhp` GREEN again** on the OCCT engine.
11. **Task 9** — build productionization. **Task 10** — live verification.

So: the `.rhp` is green at the end of Phase 1, RED only inside Phase-2 steps 6–9, and green
again after Task 8. There is **no** intermediate green `.rhp` build between Task 1 and Task
8 — do not assert one. Each Phase-1 offline task still produces a passing test exe (real,
testable progress).

---

## Task 1: Freeze the Clipper engine as a legacy unit

**Files:**
- Create: `src/RookNative/SceneGraph/legacy/LegacyPlanarAdjacency.h`
- Create: `src/RookNative/SceneGraph/legacy/LegacyPlanarAdjacency.cpp`
- Delete: `src/RookNative/SceneGraph/PlanarAdjacencyEngine.{h,cpp}`
- Modify: `src/RookNative/SceneGraph/tests/exact_adjacency_tests.cpp` (include path + namespace)
- Modify: `src/RookNative/ExactAdjacencyTests.vcxproj`
- Modify: `src/RookNative/RookNative.vcxproj` (remove `PlanarAdjacencyEngine.cpp`)

- [ ] **Step 1: Create the legacy header** — copy the current `PlanarAdjacencyEngine.h` content AND the planar-only types currently in `ExactAdjacencyTypes.h` (`FaceKind`, `PlanarFace`, `FaceSummary`, `ObjectFaceSummary`, the old 5-state `Capability`, `ExactEdge` without facePairs, `ExactCandidate`, `ExactAdjacencyCore`, `kNormalTol`, `kAreaTol`, `kClipperPrecision`, `kEngineVersion`) into `legacy/LegacyPlanarAdjacency.h`, wrapping everything in `namespace Rook { namespace Legacy { … } }`. The interface becomes `Rook::Legacy::IExactAdjacencyEngine` / `Rook::Legacy::PlanarAdjacencyEngine`. Include `SceneGraph/ExactAdjacencyTypes.h` for the shared `SceneNode`/query types only if referenced; otherwise self-contain.

- [ ] **Step 2: Create the legacy cpp** — move the body of `PlanarAdjacencyEngine.cpp` into `legacy/LegacyPlanarAdjacency.cpp`, change `namespace Rook` → `namespace Rook { namespace Legacy`, update the include to `SceneGraph/legacy/LegacyPlanarAdjacency.h`. No logic changes.

- [ ] **Step 3: Delete the old files** — `git rm src/RookNative/SceneGraph/PlanarAdjacencyEngine.h src/RookNative/SceneGraph/PlanarAdjacencyEngine.cpp`.

- [ ] **Step 4: Repoint the legacy test** — in `exact_adjacency_tests.cpp` change `#include "SceneGraph/PlanarAdjacencyEngine.h"` → `#include "SceneGraph/legacy/LegacyPlanarAdjacency.h"` and `using namespace Rook;` → `using namespace Rook::Legacy;`. In `ExactAdjacencyTests.vcxproj` change the two `ClCompile`/`ClInclude` entries from `SceneGraph\PlanarAdjacencyEngine.cpp`/`.h` and `SceneGraph\ExactAdjacencyTypes.h` to the legacy paths.

- [ ] **Step 5: Remove from the production build** — in `RookNative.vcxproj` delete the `<ClCompile Include="SceneGraph\PlanarAdjacencyEngine.cpp">…</ClCompile>` block (line ~151). Do NOT add the legacy cpp to RookNative.vcxproj — it is test-only.

- [ ] **Step 6: Build the legacy test, verify still green**

Run:
```
cd /c/Users/aryan/source/repos/rook-spatial/src/RookNative
MSBuild.exe ExactAdjacencyTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m
./bin/tests/Debug/x64/ExactAdjacencyTests.exe; echo "exit=$?"
```
Expected: builds; exe prints no `FAIL` lines and `exit=0` (the Gate-4 planar cases still pass against the frozen legacy engine).

- [ ] **Step 7: Commit**
```
git add -A src/RookNative/SceneGraph/legacy src/RookNative/ExactAdjacencyTests.vcxproj src/RookNative/RookNative.vcxproj src/RookNative/SceneGraph/tests/exact_adjacency_tests.cpp
git rm --cached src/RookNative/SceneGraph/PlanarAdjacencyEngine.h src/RookNative/SceneGraph/PlanarAdjacencyEngine.cpp 2>/dev/null; true
git commit -m "refactor(scene): freeze Clipper planar engine as Rook::Legacy unit, drop from .rhp"
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
# committed at the end of Task 3 (service migration), not standalone
```

---

## Task 3: Main-thread extraction → `ObjectBrepPayload`

**Files:**
- Modify: `src/RookNative/SceneGraph/ExactAdjacencyService.cpp` (replace `ExtractObjectFaceSummary` with `ExtractObjectBrepPayload`)
- Modify: `src/RookNative/SceneGraph/ExactAdjacencyService.h` (no signature change to `Compute`; internal only)

- [ ] **Step 1: Replace the extraction function.** Remove `ExtractObjectFaceSummary` + its planar helpers (`foldPlane`, the loop/plane extraction). Add `ExtractObjectBrepPayload(CRhinoDoc&, const std::string& objectId) -> ObjectBrepPayload`. It runs ONLY on the main thread (inside `Dispatch`). Logic:
  - Parse uuid; null/`object_not_found`/`no_geometry` → `FailedWithDiagnostics` + reason code.
  - `ON_Mesh` / `ON_SubD` → `UnsupportedGeometry` + `"mesh"`/`"subd"`, `brep=nullptr`.
  - Brep or Extrusion (`ext->BrepForm()`) → **deep-copy** into an owned `ON_Brep` (`new ON_Brep(*brep)`; for Extrusion, the `BrepForm()` result is already owned — wrap it). Set `capability = ExactBrep` provisionally (downgraded to `PartialExactBrep` by the engine if some faces fail conversion). Non-Brep geometry (curve/point) → `UnsupportedGeometry` + `"no_brep"`.
  - face-count cap (`brep->m_F.Count() > 4000`) → `FailedWithDiagnostics` + `"face_cap_exceeded:N"`, `brep=nullptr`.
  - `modelUnitsToMillimeters = doc.UnitsAndTolerances something` — use `ON::UnitScale(doc model unit system, ON::LengthUnitSystem::Millimeters)` from `doc.Properties().ModelUnitsAndTolerances().m_unit_system` (RhinoCommon: `doc.UnitSystem()` → `ON::UnitScale(thatUnit, ON::LengthUnitSystem::Millimeters)`).
  - **No Rhino SDK pointer escapes**: only the owned `ON_Brep` copy + plain fields are stored in the returned `ObjectBrepPayload`.

- [ ] **Step 2: Rewire `Compute`'s dispatch** to build `ObjectBrepPayload source` + `std::vector<ObjectBrepPayload> candidates` instead of `ObjectFaceSummary`. Because `ObjectBrepPayload` is move-only, the `Extracted` struct must hold them by value and be moved out of the future (`Dispatch` returns a `std::future<Extracted>`; move on `.get()`).

- [ ] **Step 3: Migrate `Compute` to the new engine.** Include `OcctAdjacencyEngine.h` (built in Phase 1, Task 6) and call it (the full wiring — units, tolerance conversion — is detailed in Task 8 Step 1; do it here since the service and the call site are the same edit). Because Tasks 4–6 already landed in Phase 1, the engine exists; there is no stub. This is the migration block — the `.rhp` does NOT build green until Task 8 completes (legacy removed, handler migrated, tracer retired).

- [ ] **Step 4: Do NOT build the `.rhp` here.** The migration block (Task 2 strip + Task 1 legacy removal + Task 3 + Task 7 Step 3 + Task 8) compiles green only at the end of Task 8. Defer the `cmd /c scripts\build-native.bat Release` build to Task 8 Step 4. Verify only that this TU's edits are internally consistent (types match `OcctAdjacencyTypes.h`).

- [ ] **Step 5: Commit** (the broken-but-coherent migration step, together with the Task 2 strip)
```
git add src/RookNative/SceneGraph/ExactAdjacencyService.cpp src/RookNative/SceneGraph/ExactAdjacencyService.h src/RookNative/SceneGraph/ExactAdjacencyTypes.h src/RookNative/SceneGraph/OcctAdjacencyTypes.h
git commit -m "feat(scene): migrate service to ObjectBrepPayload + OCCT engine (rhp green after Task 8)"
```

---

## Task 4: `ON_Brep`→`TopoDS` converter — surfaces + face-index map (offline harness)

**Files:**
- Create: `src/RookNative/SceneGraph/OnBrepToOcct.h`
- Create: `src/RookNative/SceneGraph/OnBrepToOcct.cpp`
- Create: `src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp`
- Create: `src/RookNative/OcctAdjacencyTests.vcxproj`

**Converter interface (`OnBrepToOcct.h`):**
```cpp
#pragma once
#include <vector>
class ON_Brep;
class TopoDS_Shape;       // returned by value via a small owning struct (see cpp)
namespace Rook {
struct OcctFaceMap {      // converted shape + index mapping
    // opaque handle to a TopoDS_Compound of faces + parallel vector mapping
    // OCCT face slot -> source ON_Brep face index. Defined in the .cpp; the
    // header exposes only the conversion entry point + a result the engine consumes.
};
// Convert every analytic face of `brep` to an OCCT face. Returns per-face OCCT
// faces with their SOURCE ON_Brep face index preserved. `failedFaceIndices`
// receives indices that could not be converted (engine downgrades to PartialExactBrep).
// Pure: no Rhino SDK, no STEP, no threads.
bool ConvertBrepFaces(const ON_Brep& brep,
                      /*out*/ std::vector<int>& sourceFaceIndexPerOcctFace,
                      /*out*/ void* occtFacesOut,           // TopTools/NCollection list (see cpp)
                      /*out*/ std::vector<int>& failedFaceIndices);
}
```
(The exact OCCT container types live in the `.cpp`; the header stays OCCT-header-free so Rhino-facing TUs can include it without the OpenNURBS↔OCCT header clash — mirror the `OcctProbe.h` discipline.)

- [ ] **Step 1: Write the offline harness test (RED) — surface fidelity.** In `occt_adjacency_tests.cpp`, dependency-free `CHECK`/`CHECK_NEAR` harness (copy the macro style from `exact_adjacency_tests.cpp`). First test: read a known planar object from `SpatialTest.3dm` via openNURBS `ONX_Model`, get its `ON_Brep`, call `ConvertBrepFaces`, sum converted face areas (`BRepGProp::SurfaceProperties`), and compare to the STEP oracle total surface area (read the committed per-object `.stp` via `STEPControl_Reader`), converting in²→mm² (× 645.16) or comparing in consistent units. Assert ratio ≈ 1.0 within 1e-4.

```cpp
// pseudostructure — real openNURBS/OCCT calls filled during impl:
//   ONX_Model m; m.Read(L"C:\\Users\\aryan\\Desktop\\SpatialTest.3dm");
//   const ON_Brep* b = /* component by known GUID 71065f57-... */;
//   std::vector<int> map, failed; NCollection_List<TopoDS_Shape> occtFaces;
//   ConvertBrepFaces(*b, map, &occtFaces, failed);
//   double conv = sumFaceAreas(occtFaces);
//   double oracle = stepTotalSurfaceArea("fixtures/71065f57.stp");
//   CHECK_NEAR(conv * 645.16, oracle, oracle * 1e-4);  // model in^2 vs STEP mm^2
```

- [ ] **Step 2: Create `OcctAdjacencyTests.vcxproj`** — copy `ExactAdjacencyTests.vcxproj`, change `ProjectGuid` (new GUID), `TargetName`/`RootNamespace` → `OcctAdjacencyTests`. Compile `SceneGraph\tests\occt_adjacency_tests.cpp` + `SceneGraph\OnBrepToOcct.cpp`. Add include dirs: `$(OcctRoot)\inc` and the openNURBS include dir (find it from RookNative.vcxproj's Rhino SDK include path). Link: OCCT modeling + DataExchange TK\* libs (the full Spike-G list is fine for the test target) from `$(OcctRoot)\win64\vc14\lib`, plus the openNURBS lib (`opennurbs_public.lib` or the Rhino SDK's `opennurbs.lib` — resolve from the Rhino SDK lib dir). Set `$(OcctRoot)` via an MSBuild property defaulting to `C:\Users\aryan\source\repos\OCCT\build-rook` (Task 9 makes this an env var across all projects).

- [ ] **Step 3: Generate the STEP oracle fixtures (one-time, offline, dev-only).** With Rhino open on `SpatialTest.3dm`, export the fixture objects (the Spike-A GUIDs: wall `71065f57…`, open floorplate `08d4dedf…`, and its 5 confirmed abutments) to per-object `.stp` files into `src/RookNative/SceneGraph/tests/fixtures/` (gitignored — user geometry). Document the exact GUIDs + export command in a `fixtures/README.md` (committed). This is a **dev/test artifact**; it is never invoked by the runtime.

- [ ] **Step 4: Build the test (verify RED)**
```
cd /c/Users/aryan/source/repos/rook-spatial/src/RookNative
MSBuild.exe OcctAdjacencyTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m
```
Expected: FAILS to link (unresolved `ConvertBrepFaces`) — the RED state.

- [ ] **Step 5: Implement `ConvertBrepFaces` surfaces only.** In `OnBrepToOcct.cpp`: for each `ON_BrepFace`, get `face.SurfaceOf()->NurbsSurface()`, build an OCCT `Geom_BSplineSurface` (poles ÷ W for homogeneous control points; weights; knots with end-knot padding per Spike D); make a face with `BRepBuilderAPI_MakeFace(geomSurf, tol)` (untrimmed full-surface face for now). Push to the out-list, record the source face index. On any per-face exception, push to `failedFaceIndices`. (Trims come in Task 5; surface areas won't match a trimmed oracle yet — so this step's test asserts only that conversion *runs* and produces N faces; the area-match assertion is enabled in Task 5.)

- [ ] **Step 6: Adjust the Task-4 test to its achievable bar** — assert face count == `brep->m_F.Count()` minus `failed`, and that areas are finite/positive. (The exact-area oracle match is Task 5's bar, once trimming lands.) Build + run; expect `exit=0`.

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
cd /c/Users/aryan/source/repos/rook-spatial/src/RookNative
MSBuild.exe OcctAdjacencyTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m
./bin/tests/Debug/x64/OcctAdjacencyTests.exe; echo "exit=$?"
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

- [ ] **Step 5: Port the robustness matrix** — add the 9 `spike_strengthener2_coverage.py` cases as engine assertions using OCCT primitive solids built in-test (`BRepPrimAPI_MakeBox`/`MakeCylinder` wrapped as `ObjectBrepPayload` via a tiny TopoDS→payload shim, OR convert via the same path): abutting→exact; gap>fuzzy→0; gap<fuzzy→bridged; coincident-duplicate→full overlap no crash; interpenetration→0 face-adjacency; far-from-origin→exact; sliver→no crash; degenerate→rejected; curved-on-planar→πr². Build + run; `exit=0`.

- [ ] **Step 6: Commit**
```
git add src/RookNative/SceneGraph/OcctAdjacencyEngine.* src/RookNative/SceneGraph/tests/occt_adjacency_tests.cpp src/RookNative/OcctAdjacencyTests.vcxproj
git commit -m "feat(scene): OcctAdjacencyEngine kernel — Common().Area, prefilter, facePairs, robustness matrix"
```

---

## Task 7: Diagnostic propagation + de-planarized wire serialization

**Files:**
- Modify: `src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp` (diagnostic merge)
- Modify: `src/RookNative/Handlers/SceneGraphHandler.cpp` (response fields)

- [ ] **Step 1: Engine diagnostic merge.** In `Evaluate`, merge into `core.diagnostics`: source extraction codes prefixed `source:`, each candidate's codes prefixed `cand:<id>:`, engine per-pair failures prefixed `engine:` (conversion failure, `Common` exception/HasErrors). Successful contributions are recorded in `facePairs`, not as strings.

- [ ] **Step 2: Add a diagnostics test** (offline) — feed a payload with `brep=nullptr`/`UnsupportedGeometry` ("mesh") as a candidate; assert the core's `diagnostics` contains `cand:<id>:mesh` and that candidate's `capability == UnsupportedGeometry`, while an `ExactBrep` source with no touching candidate yields zero edges and NO error diagnostic (the tightened no-edge invariant). Build + run; `exit=0`.

- [ ] **Step 3: Update the handler response** (`HandleSceneGraphExactAdjacency`, ~line 734): serialize `out["lengthUnit"] = core.lengthUnit; out["areaUnit"] = core.areaUnit;`. For each edge add `facePairs` array (`sourceFaceIndex`/`candidateFaceIndex`/`sharedArea`). `CapabilityToString` now emits `exact_brep`/`partial_exact_brep`/`unsupported_geometry`/`failed_with_diagnostics` — **no `exact_planar`**. Update `CapabilityToString` callers.

- [ ] **Step 4: Build the `.rhp`**
```
cd /c/Users/aryan/source/repos/rook-spatial && cmd /c scripts\\build-native.bat Release
```
Expected: compiles + links.

- [ ] **Step 5: Commit**
```
git add src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp src/RookNative/Handlers/SceneGraphHandler.cpp
git commit -m "feat(scene): honest diagnostic propagation + de-planarized wire contract (facePairs, area units)"
```

---

## Task 8: Wire the engine into the service; retire the tracer

**Files:**
- Modify: `src/RookNative/SceneGraph/ExactAdjacencyService.cpp` (use `OcctAdjacencyEngine`, set units, tolerance conversion)
- Modify: `src/RookNative/Handlers/SceneGraphHandler.cpp` (remove `HandleOcctProbe`)
- Modify: `src/RookNative/RookServer.cpp` (remove `/scene/occt_probe` route)
- Modify: `src/RookNative/RookNative.vcxproj` (add `OnBrepToOcct.cpp`, `OcctAdjacencyEngine.cpp` with per-file OCCT include; remove `OcctProbe.cpp`)
- Delete: `src/RookNative/SceneGraph/OcctProbe.{h,cpp}`

- [ ] **Step 1: Replace the trivial inline engine (Task 3 stub) with `OcctAdjacencyEngine`.** In `Compute`: after extraction, compute `double tolModelUnits = (opts.tolerance>0 ? opts.tolerance : kDefaultFuzzMm) / source.modelUnitsToMillimeters;` (decide whether `opts.tolerance` is mm or model units — treat the incoming `tolerance` as **mm** for caller stability, document it), call `OcctAdjacencyEngine().Evaluate(source, candidates, tolModelUnits)`. Set `evaluated.lengthUnit`/`areaUnit` from the doc unit system string (e.g. "inches"/"inches^2").

- [ ] **Step 2: Add the new cpps to `RookNative.vcxproj`** with the per-file OCCT include block (mirror the `OcctProbe.cpp` block: `NotUsing` PCH, `$(OcctRoot)\inc` include, `/bigobj`). Remove the `OcctProbe.cpp` block and `OcctProbe.h` `ClInclude`. **Note:** `ExactAdjacencyService.cpp` and `SceneGraphHandler.cpp` keep the PCH (Rhino-facing); they include the OCCT-header-free `OcctAdjacencyEngine.h`/`OnBrepToOcct.h`, so OCCT headers never leak into PCH TUs.

- [ ] **Step 3: Remove the tracer** — delete `OcctProbe.{h,cpp}`, the `HandleOcctProbe` function, its `#include`, and the `m_server->Post("/scene/occt_probe", …)` registration in `RookServer.cpp` (~1796).

- [ ] **Step 4: Build the `.rhp`**
```
cd /c/Users/aryan/source/repos/rook-spatial && cmd /c scripts\\build-native.bat Release
```
Expected: compiles + links; the production engine is now the OCCT engine.

- [ ] **Step 5: Commit**
```
git add -A src/RookNative/SceneGraph/ExactAdjacencyService.cpp src/RookNative/Handlers/SceneGraphHandler.cpp src/RookNative/RookServer.cpp src/RookNative/RookNative.vcxproj
git rm --cached src/RookNative/SceneGraph/OcctProbe.h src/RookNative/SceneGraph/OcctProbe.cpp 2>/dev/null; true
git commit -m "feat(scene): wire OcctAdjacencyEngine into the service; retire Spike-G tracer"
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
cd /c/Users/aryan/source/repos/rook-spatial && cmd /c scripts\\build-native.bat Release
dumpbin /DEPENDENTS "src/RookNative/bin/Release/x64/RookNative.rhp" | grep -i "TK"
```
Iterate the link list until it links with the minimal set; record the measured DLL list + total MB in the build doc (target ≈ 15 MB per the spec). If a link error names a missing `TK*`, add exactly that one back.

- [ ] **Step 4: LGPL attribution.** Grep for the existing about/version/licenses surface (e.g. `grep -rn "Uses\|License\|Copyright\|RhinoCommon" src/Rook src/RookNative --include=*.cpp --include=*.cs -l`), add a line: "This software uses Open CASCADE Technology (https://www.opencascade.com), licensed under LGPL 2.1." Confirm OCCT is dynamically linked (it is — DLLs).

- [ ] **Step 5: Commit**
```
git add src/RookNative/RookNative.vcxproj src/RookNative/OcctAdjacencyTests.vcxproj docs/rook_docs/occt-build-7.9.3.md <licenses-file>
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
- **Tolerance unit boundary:** the HTTP `tolerance` param is treated as **mm** at the service boundary and converted to model units via `modelUnitsToMillimeters` before OCCT. Keep this single conversion point in `Compute` (Task 8 Step 1); never let an unconverted mm value reach `Common`.
- **Move-only payloads:** `ObjectBrepPayload` never enters the cache or gets copied. Only `ExactAdjacencyCore` (plain data) is cached/serialized. If a build error mentions a deleted copy ctor on a payload vector, you are copying where you must move.
- **`kEngineVersion` is bumped to 2** → the adjacency cache auto-drops Gate-4 entries on first call. Do not also clear manually.
- **No STEP in the runtime path:** if any production TU (compiled into `.rhp`) includes a `STEPControl_*` header, that is a regression against spec §1's invariant. STEP lives only in `OcctAdjacencyTests`.
