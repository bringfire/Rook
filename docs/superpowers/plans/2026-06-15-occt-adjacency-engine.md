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

**Test surfaces (amended — in-plugin first):**
- **Dev validation route** `POST /scene/occt_validate_converter` (handler in `SceneGraphHandler.cpp`, registered in `RookServer.cpp`) — feature-branch dev route (gated like the Spike-G `/scene/occt_probe`), REMOVED/gated in Task 8/9 before productionization. Runs `ConvertBrepFaces` on the live `ON_Brep` (main-thread copy → worker convert) and reports converted face count, failed face indices, converted total area (model units + ×645.16 mm²), the precomputed expected mm² oracle, relative error, face-index-map sanity, and diagnostics. Uses a built-in oracle table for the known SpatialTest GUIDs (Task 4); accepts an optional `expectedMm2` override in the body. **Never reads STEP.**
- `src/RookNative/OcctPrimitiveTests.vcxproj` + `src/RookNative/SceneGraph/tests/occt_primitive_tests.cpp` — NEW, **OCCT-only** offline console (links OCCT modeling only; NO openNURBS, NO STEP, NO `ON_Brep`). Tests the kernel coincidence primitive `SharedFaceArea(TopoDS, TopoDS, fuzz)` on `BRepPrimAPI` boxes/cylinders — the Task-6 robustness matrix.
- `docs/rook_docs/occt-spike/live_verify_occt_adjacency.py` — NEW. Python `urllib` in-plugin verification (Task 10; also exercises the dev validation route).
- The STEP `.stp` fixtures (committed-as-README, gitignored geometry) were the one-time source of the oracle constants; they are NOT linked or read by any shipped or test binary.

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

**TEST VENUE (amended 2026-06-15, user decision): IN-PLUGIN FIRST.** The converter is
validated *inside RookNative* against the live `ON_Brep` and **precomputed STEP-oracle
constants** (hardcoded mm², computed offline — see the oracle table in Task 4), via a
**dev-gated diagnostic route** `POST /scene/occt_validate_converter`. RookNative already
links openNURBS + OCCT, so this is **zero new linking** and **no STEP in the `.rhp`** (the
route uses constants, never reads STEP). No standalone-openNURBS console is built (the
plan's prior `OcctAdjacencyTests` offline console is REPLACED by this route). The only
remaining *offline* test is Task 6's OCCT-primitive robustness matrix, which needs no
`ON_Brep` and so links OCCT only (like the Spike-G `OcctProbe` unit).

**Phase 1 — additive; `.rhp` stays GREEN on the old Clipper engine while gaining the new
converter + a dev route alongside it. Each task is its own buildable commit:**
1. **Task 1 (additive)** — `Rook::Legacy` unit + repoint the legacy *test*; old engine and
   `RookNative.vcxproj` untouched. `.rhp` green; legacy test green. ✅ DONE (`32a594be`).
2. **Task 2 (additive)** — `OcctAdjacencyTypes.h` standalone header. ✅ DONE (`c2104bd2`).
3. **Task 4** — converter surfaces + the dev validation route + oracle table; `.rhp` builds
   (additive: new files + new dev route; old engine still wired).
4. **Task 5** — converter trims/orientation; the dev route reports oracle match within 1e-4
   for the planar wall + the curved wall.
5. **Task 6** — `OcctAdjacencyEngine` kernel; OCCT-only offline primitive robustness matrix.
6. **Task 7 Steps 1–2** — engine-internal diagnostic merge (offline-testable on payloads
   built from live `ON_Brep` via the dev route, or a small OCCT-only harness).

Throughout Phase 1 the `.rhp` stays green on the old Clipper engine; the new converter and
dev route are ADDITIVE (the production adjacency route is unchanged until Task 8). Each task
ends with a verifiable result (dev-route oracle match, or the offline primitive matrix).

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

## Task 4: `ON_Brep`→`TopoDS` converter — surfaces + face-index map (in-plugin venue)

**Files:**
- Create: `src/RookNative/SceneGraph/OnBrepToOcct.h`
- Create: `src/RookNative/SceneGraph/OnBrepToOcct.cpp`
- Modify: `src/RookNative/Handlers/SceneGraphHandler.{h,cpp}` (dev route handler `HandleOcctValidateConverter`)
- Modify: `src/RookNative/RookServer.cpp` (register `POST /scene/occt_validate_converter`)
- Modify: `src/RookNative/RookNative.vcxproj` (add `OnBrepToOcct.cpp`, per-file OCCT block — additive)

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

> **Implementer note:** OCCT call shapes below are **illustrative scaffolding, not a literal
> required API**. Converter internals are compiler-and-oracle-driven (see Self-Review notes);
> the binding contract is the oracle area match within 1e-4 and the `OcctFaceSet`/
> `ConvertBrepFaces` signatures in `OnBrepToOcct.h`.

**Oracle constants (precomputed offline 2026-06-15 via OCP 7.9.3 reading the committed
`.stp` fixtures; total surface area in mm² — these are the converter-fidelity targets, no
STEP read at runtime). Embed as a built-in table in the dev route:**

| objectId (full GUID) | expected total surface mm² | (÷645.16 = in²) | role |
|---|---|---|---|
| `71065f57-ee93-4af5-8a67-9aa1c4e88302` | 431441833.631 | 668736.180 | planar wall |
| `08d4dedf-1387-453a-9938-7f3ab516b8ac` | 236698710.791 | 366883.735 | open floorplate |
| `5c12cc83-5fe3-4f2c-9fca-c0575c9f5dd3` |  57752777.327 |  89516.984 | Triage abutment |
| `be0ca730-f3e9-4b41-a5bf-6b3848607b14` |  57730120.364 |  89481.866 | Triage abutment |
| `7e80db98-d133-4a05-b9fe-ee6d37d9069d` |  31753629.008 |  49218.223 | I-WALL abutment |
| `26b2c012-24cf-4656-9e48-8083dc072cad` |  31461872.558 |  48766.000 | I-WALL abutment |
| `7d55840d-2516-4a78-9c7d-3a10152756b1` |  40404289.332 |  62626.774 | **curved wall** |
| `502898fc-75f3-4d59-bddf-cc966a942795` |  37898150.015 |  58742.250 | sliver |

- [ ] **Step 1: Implement `OcctFaceSet` + `ConvertBrepFaces` surfaces only** in `OnBrepToOcct.cpp`: define `OcctFaceSet::Impl` (a `TopoDS_Compound`/`NCollection_List<TopoDS_Face>` + `std::vector<int>` source-index map + `std::vector<int>` failed). For each `ON_BrepFace`, get `face.SurfaceOf()->NurbsSurface()`, build an OCCT `Geom_BSplineSurface` (poles ÷ W for homogeneous control points; weights; knots with end-knot padding per Spike D); make a face with `BRepBuilderAPI_MakeFace(geomSurf, tol)` (untrimmed full-surface for now); append + record the source face index. Per-face exception → record in `failed`. Pure: no Rhino SDK, no STEP, no threads. (Trims come in Task 5; untrimmed areas WON'T match the oracle yet.)

- [ ] **Step 2: Add the dev validation route handler** `HandleOcctValidateConverter` in `SceneGraphHandler.cpp` + register `POST /scene/occt_validate_converter` in `RookServer.cpp` (next to the existing `/scene/occt_probe`; same dev-gating). Body: `{ "objectId": "<guid>", "expectedMm2": <optional override> }`. It: dispatches to the MAIN thread to deep-copy the object's `ON_Brep` (reuse the `ExtractBrep` pattern already in `ExactAdjacencyService.cpp`; mesh/SubD/non-brep → error JSON), then on the worker calls `ConvertBrepFaces`, sums converted area (model units), and returns JSON: `convertedFaceCount`, `failedFaceIndices`, `totalAreaModel`, `totalAreaMm2` (= model × `modelUnitsToMillimeters²`… NB area scale is the SQUARE of the length scale — for inches 645.16 = 25.4²), `expectedMm2` (from the built-in table or the override), `relErr`, `faceIndexMapOk` (every OCCT slot maps to a valid source index), and `diagnostics`. OCCT work serialized via a static mutex (mirror `HandleOcctProbe`).

- [ ] **Step 3: Add the new converter file to `RookNative.vcxproj`** — add `SceneGraph\OnBrepToOcct.cpp` with the per-file OCCT block (mirror the `OcctProbe.cpp` block: `NotUsing` PCH, `<AdditionalIncludeDirectories>$(OcctRoot)\inc;…` — for now keep the existing hardcoded `C:\Users\aryan\source\repos\OCCT\build-rook\inc` path that `OcctProbe.cpp` uses; Task 9 swaps all of them to `$(OcctRoot)`, `/bigobj`). This is ADDITIVE — do not remove or alter the old engine. `SceneGraphHandler.cpp` keeps its PCH and includes the OCCT-header-free `OnBrepToOcct.h` only.

- [ ] **Step 4: Build the `.rhp` (additive, stays green on the old engine)**
```
cmd //c scripts/build-native.bat Release
```
Expected: compiles + links (old Clipper adjacency route unchanged; new converter + dev route added).

- [ ] **Step 5: Validate in-plugin (controller-coordinated deploy/live loop).** This needs the Rhino deploy cycle (deploy requires Rhino CLOSED; test requires Rhino OPEN on `SpatialTest.3dm`). The implementer subagent STOPS after Step 4 with `STATUS: DONE` and reports that in-plugin validation is pending the deploy cycle; the CONTROLLER coordinates deploy + hits `POST /scene/occt_validate_converter` (via Python `urllib`) for the wall `71065f57`. At THIS task's bar (surfaces only, untrimmed): assert the route returns `convertedFaceCount == brep face count`, `failedFaceIndices` empty, finite positive area, `faceIndexMapOk == true`. (The exact-area oracle match is Task 5's bar.)

- [ ] **Step 6: Commit (additive — `.rhp` green on old engine + new converter/route)**
```
git add src/RookNative/SceneGraph/OnBrepToOcct.* src/RookNative/Handlers/SceneGraphHandler.* src/RookNative/RookServer.cpp src/RookNative/RookNative.vcxproj
git commit -m "feat(scene): ON_Brep->OCCT surface converter + dev validation route (in-plugin venue)"
```

---

## Task 5: Converter trims/pcurves + orientation fidelity

**Files:**
- Modify: `src/RookNative/SceneGraph/OnBrepToOcct.cpp`

Validated in-plugin via the `POST /scene/occt_validate_converter` route from Task 4 (no
console exe). Bar: each fixture's converted total area matches its `expectedMm2` oracle
(table in Task 4) within 1e-4 relative — including the curved wall.

- [ ] **Step 1: Implement trims + orientation** in `ConvertBrepFaces`, per spec §3.1:
  - For each face, build a wire per `ON_BrepLoop`: for each `ON_BrepTrim`, copy its pcurve (`trim.TrimCurveOf()->NurbsCurve()`) → OCCT 2D `Geom2d_BSplineCurve` → `BRepBuilderAPI_MakeEdge(pcurve2d, geomSurf)`; honor `trim.m_bRev3d` for edge orientation; `BRepLib::BuildCurves3d` on the edge.
  - **Outer loop** (`ON_BrepLoop::outer`) → bounding wire; **inner loops** (`ON_BrepLoop::inner`) → reversed wires (holes subtract).
  - **Face reversal**: apply `ON_BrepFace::m_bRev` to the OCCT face orientation (`face.Reversed()` / `TopoDS_Face` orientation flag) so the natural normal matches the `ON_Brep` oriented normal.
  - **Seam trims**: handle `ON_BrepTrim::seam` so closed/periodic surfaces (cylinders, full revolves) close properly.
  - **Singular trims**: represent collapsed trims (`ON_BrepTrim::singular`) as OCCT degenerated edges (`BRepBuilderAPI_MakeEdge` degenerate form) — do NOT drop them (dropping leaves an invalid wire).
  - `BRepBuilderAPI_MakeFace(geomSurf, outerWire)` then `.Add(holeWire)`; `ShapeFix_Face` as a *net*, not a corrector — if fixed area disagrees with the oracle it is a converter bug.

- [ ] **Step 2: Build the `.rhp`**
```
cmd //c scripts/build-native.bat Release
```
Expected: compiles + links.

- [ ] **Step 3: Validate in-plugin (controller-coordinated deploy/live loop).** Implementer reports `STATUS: DONE`, validation pending deploy. Controller deploys (Rhino closed → open on `SpatialTest.3dm`) and hits `POST /scene/occt_validate_converter` for the **planar wall `71065f57`** AND the **curved wall `7d55840d`**: assert `relErr < 1e-4` against each `expectedMm2`, `failedFaceIndices` empty, `faceIndexMapOk == true`. The curved wall proves rational/curved trims. (Spot-check 1–2 more fixtures opportunistically.)

- [ ] **Step 4: Commit**
```
git add src/RookNative/SceneGraph/OnBrepToOcct.cpp
git commit -m "feat(scene): converter trims/pcurves + orientation fidelity (Strengthener-1 proof, in-plugin)"
```

---

## Task 6: `OcctAdjacencyEngine` compute kernel

**Files:**
- Create: `src/RookNative/SceneGraph/OcctAdjacencyEngine.h`
- Create: `src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp`
- Create: `src/RookNative/SceneGraph/OcctAdjacencyEngine_internal.h` (OCCT-aware internal decls)
- Create: `src/RookNative/SceneGraph/tests/occt_primitive_tests.cpp` + `src/RookNative/OcctPrimitiveTests.vcxproj` (OCCT-only offline matrix)
- Modify: `src/RookNative/Handlers/SceneGraphHandler.cpp` + `RookServer.cpp` (extend the dev route to run `Evaluate`)
- Modify: `src/RookNative/RookNative.vcxproj` (add `OcctAdjacencyEngine.cpp`)

- [ ] **Step 1: Engine header** — `class OcctAdjacencyEngine : public IExactAdjacencyEngine` overriding `Evaluate`. OCCT-header-free header (like `OnBrepToOcct.h`); include only `OcctAdjacencyTypes.h`. Also create `OcctAdjacencyEngine_internal.h` declaring the testable primitive `double SharedFaceArea(const TopoDS_Shape& a, const TopoDS_Shape& b, double fuzz, bool& crashed);` (OCCT-aware; included only by OCCT TUs + the primitive test).

- [ ] **Step 2: Implement `Evaluate`** per spec §3.2 (in `OcctAdjacencyEngine.cpp`, OCCT-aware TU):
  - For source + each candidate: `ConvertBrepFaces` (downgrade `capability` to `PartialExactBrep` if `failedFaceIndices` non-empty; if zero faces convert, `UnsupportedGeometry`/`FailedWithDiagnostics`).
  - **Prefilter**: skip face pairs whose OCCT face bounding boxes (`BRepBndLib::Add` → `Bnd_Box`) do not overlap within `toleranceModelUnits`. **No coplanar/planar assumption.**
  - The per-pair coincidence is the `SharedFaceArea` primitive: `BRepAlgoAPI_Common op; op.SetArguments({faceA}); op.SetTools({faceB}); op.SetFuzzyValue(fuzz); op.Build();` guard with `try/catch(Standard_Failure)` AND `if (op.HasErrors())`. Area = `SurfaceProperties(op.Shape()).Mass()`.
  - Accumulate per (sourceFaceIndex, candFaceIndex); pair area > `kAreaTol` → append a `FacePair`. After all pairs, sum > `kAreaTol` → emit one `ExactEdge{sourceId,targetId,"adjacent_exact",sum,facePairs}`.
  - Populate `core.candidates` (id + combined capability), `core.sourceCapability`; merge diagnostics (Task 7 finalizes namespacing). Serialize OCCT behind a `static std::mutex`. Define `CapabilityToString` here.
  - Add `OcctAdjacencyEngine.cpp` to `RookNative.vcxproj` (per-file OCCT block, additive).

- [ ] **Step 3: OCCT-only offline robustness matrix (RED→GREEN).** Create `OcctPrimitiveTests.vcxproj` (copy `ExactAdjacencyTests.vcxproj`; new GUID; `TargetName`=`OcctPrimitiveTests`; links **OCCT modeling only** from `$(OcctRoot)\win64\vc14\lib` — NO openNURBS, NO STEP, NO DataExchange; include `$(OcctRoot)\inc`). Compile `occt_primitive_tests.cpp` + `OcctAdjacencyEngine.cpp` (the `SharedFaceArea` primitive). Build the 9 `spike_strengthener2_coverage.py` cases from `BRepPrimAPI_MakeBox`/`MakeCylinder` directly (no `ObjectBrepPayload`, no converter): abutting→exact(≈100·25.4²); gap>fuzzy→0; gap<fuzzy→bridged; coincident-duplicate→full overlap, no crash; interpenetration→0 face-adjacency; far-from-origin(+1e6)→exact; sliver→no crash; degenerate→rejected at construction; curved-on-planar→πr². Build + run; `exit=0`.
```
cd src/RookNative
MSBuild.exe OcctPrimitiveTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m
./bin/tests/Debug/x64/OcctPrimitiveTests.exe; echo "exit=$?"
cd ..
```

- [ ] **Step 4: Extend the dev route to validate the full `Evaluate(payload)` path in-plugin.** Add an optional mode to `POST /scene/occt_validate_converter` (or a sibling `…/occt_validate_adjacency`): body `{ "sourceId", "candidateIds": [...] }` → main-thread deep-copy each `ON_Brep` into `ObjectBrepPayload`s → worker `OcctAdjacencyEngine().Evaluate(...)` → return the edges (`sharedArea`, `facePairs`) + capabilities + diagnostics. Build the `.rhp` (`cmd //c scripts/build-native.bat Release`). Implementer reports `STATUS: DONE`, in-plugin validation pending deploy.

- [ ] **Step 5: Validate in-plugin (controller-coordinated).** Controller deploys + hits the route for source `08d4dedf` (open floorplate) with the 5 candidate abutment GUIDs: assert an edge to wall `71065f57` with `sharedArea` ≈ 3312 in² (×25.4² mm²) within 1e-3 relative, `facePairs` non-empty summing to `sharedArea`, `sourceCapability == exact_brep`.

- [ ] **Step 6: Commit (additive)**
```
git add src/RookNative/SceneGraph/OcctAdjacencyEngine.* src/RookNative/SceneGraph/OcctAdjacencyEngine_internal.h src/RookNative/SceneGraph/tests/occt_primitive_tests.cpp src/RookNative/OcctPrimitiveTests.vcxproj src/RookNative/Handlers/SceneGraphHandler.* src/RookNative/RookServer.cpp src/RookNative/RookNative.vcxproj
git commit -m "feat(scene): OcctAdjacencyEngine kernel + OCCT-only robustness matrix + in-plugin Evaluate validation"
```

---

## Task 7: Engine-internal diagnostic propagation (Phase 1, additive)

> Phase 1. The engine diagnostic MERGE lives in `OcctAdjacencyEngine.cpp` (additive — the
> engine isn't wired into the production route until Task 8, so this stays green on the old
> engine). The matching **production handler/wire-serialization** (the `/scene/graph/
> adjacency/exact` response) is a step of the Task 8 integration block, NOT here. Diagnostic
> behavior is validated in-plugin via the Task-6 dev `Evaluate` route, not a console.

**Files:**
- Modify: `src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp` (diagnostic merge)

- [ ] **Step 1: Engine diagnostic merge.** In `Evaluate`, merge into `core.diagnostics`: source extraction codes prefixed `source:`, each candidate's codes prefixed `cand:<id>:`, engine per-pair failures prefixed `engine:` (conversion failure, `Common` exception/HasErrors). Successful contributions are recorded in `facePairs`, not as strings.

- [ ] **Step 2: Build the `.rhp`** (`cmd //c scripts/build-native.bat Release`) — additive, still green on the old production engine. Implementer reports `STATUS: DONE`, diagnostic validation pending the deploy/live check.

- [ ] **Step 3: Validate in-plugin (controller-coordinated).** Via the Task-6 dev `Evaluate` route, feed source = an `ExactBrep` wall with candidates including a **mesh** object and a **SubD** object: assert each non-brep candidate's `capability == unsupported_geometry` with a `cand:<id>:mesh`/`:subd` reason in `diagnostics`; assert an `ExactBrep` source with a non-touching candidate yields zero edges and NO error diagnostic (tightened no-edge invariant).

- [ ] **Step 4: Commit (additive — `.rhp` green on old production engine)**
```
git add src/RookNative/SceneGraph/OcctAdjacencyEngine.cpp
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
- Modify: `src/RookNative/Handlers/SceneGraphHandler.cpp` (response fields; parse `fuzzMm`; remove dev routes `HandleOcctValidateConverter`/`HandleOcctProbe`)
- Modify: `src/RookNative/RookServer.cpp` (remove `/scene/occt_validate_converter` + `/scene/occt_probe` routes)
- Modify: `src/RookNative/RookNative.vcxproj` (remove `PlanarAdjacencyEngine.cpp` + `OcctProbe.cpp`; `OnBrepToOcct.cpp`/`OcctAdjacencyEngine.cpp` were ALREADY added additively in Tasks 4/6 — leave them)

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

- [ ] **Step 4: `RookNative.vcxproj` — remove old engine + tracer (the new cpps are ALREADY present).** `OnBrepToOcct.cpp` (Task 4) and `OcctAdjacencyEngine.cpp` (Task 6) were already added additively, so do NOT re-add them. Remove the `PlanarAdjacencyEngine.cpp` and `OcctProbe.cpp` `ClCompile` blocks and the `OcctProbe.h` `ClInclude`. `ExactAdjacencyService.cpp`/`SceneGraphHandler.cpp` keep the PCH and include only the OCCT-header-free `OcctAdjacencyEngine.h`/`OnBrepToOcct.h` — OCCT headers never leak into PCH TUs.

- [ ] **Step 5: Production handler migration + `fuzzMm` + remove dev routes/tracer.** In `SceneGraphHandler.cpp::HandleSceneGraphExactAdjacency`: parse optional `fuzzMm` (default `kDefaultFuzzMm`) and pass to `Compute`; serialize `out["lengthUnit"]`/`out["areaUnit"]`; per edge add `facePairs`; `CapabilityToString` emits `exact_brep`/`partial_exact_brep`/`unsupported_geometry`/`failed_with_diagnostics` (no `exact_planar`). **Remove the dev validation route(s)** added in Tasks 4/6 — delete `HandleOcctValidateConverter` (+ the Evaluate-mode sibling) and `HandleOcctProbe`, their `#include "SceneGraph/OcctProbe.h"`, and the `m_server->Post("/scene/occt_validate_converter", …)` + `/scene/occt_probe` registrations in `RookServer.cpp`. `git rm src/RookNative/SceneGraph/OcctProbe.h src/RookNative/SceneGraph/OcctProbe.cpp`. (The dev routes have served Tasks 4–7; the real `/scene/graph/adjacency/exact` route + Task 10's live verify replace them. `OnBrepToOcct`/`OcctAdjacencyEngine` STAY — they are the production engine now.)

- [ ] **Step 6: Build the `.rhp` (the green restore) + the OCCT-only primitive matrix**
```
cmd //c scripts/build-native.bat Release
cd src/RookNative && MSBuild.exe OcctPrimitiveTests.vcxproj -p:Configuration=Debug -p:Platform=x64 -v:m && ./bin/tests/Debug/x64/OcctPrimitiveTests.exe; echo "exit=$?"; cd ..
```
Expected: `.rhp` compiles + links (production engine is now OCCT; no dev routes); primitive matrix still `exit=0`.

- [ ] **Step 7: Single integration commit**
```
git add -A src/RookNative
git commit -m "feat(scene): integrate OcctAdjacencyEngine — payload extraction, engine wiring, de-planarized wire contract, retire Clipper+tracer"
```

---

## Task 9: Build productionization (OCCT 7.9.3 pin, `$(OcctRoot)`, measured DLL closure, LGPL)

**Files:**
- Modify: `src/RookNative/RookNative.vcxproj`, `src/RookNative/OcctPrimitiveTests.vcxproj` (`$(OcctRoot)` property; trim production link list)
- Create: `docs/rook_docs/occt-build-7.9.3.md` (build + deploy doc)
- Modify: the about/licenses surface (locate via grep) for LGPL attribution

- [ ] **Step 1: Build OCCT 7.9.3.** In `C:/Users/aryan/source/repos/OCCT`, fetch + checkout `V7_9_3`; configure **modeling modules only** (no DataExchange/STEP is needed by the runtime OR by any C++ test now — the converter-fidelity oracle was precomputed offline via Python OCP; the primitive matrix is OCCT-modeling-only) into `build-rook-793`; build Release. Document exact cmake flags in `docs/rook_docs/occt-build-7.9.3.md`.

- [ ] **Step 2: Introduce `$(OcctRoot)`.** Add `<OcctRoot Condition="'$(OcctRoot)'==''">$(OCCT_ROOT)</OcctRoot>` then a fallback default to the 7.9.3 build tree, in a `PropertyGroup` in both vcxprojs (`RookNative` + `OcctPrimitiveTests`). Replace every hardcoded `C:\Users\aryan\source\repos\OCCT\build-rook\…` (including the per-file include paths added in Tasks 4/6 and the `OcctProbe` legacy path if still present) with `$(OcctRoot)\…`. Document the `OCCT_ROOT` env var in the build doc.

- [ ] **Step 3: Trim the production TK\* link list.** In `RookNative.vcxproj`, reduce `AdditionalDependencies` to the **non-DataExchange** modeling closure required by the converter + kernel (drop `TKDESTEP`, `TKXSBase`, `TKDE`, `TKDECascade`, `TKCAF`, `TKLCAF`, `TKXCAF`, `TKCDF`, `TKExpress`). Build the `.rhp`, then **measure the real closure with `dumpbin`**:
```
cmd //c scripts/build-native.bat Release
dumpbin //DEPENDENTS "src/RookNative/bin/Release/x64/RookNative.rhp" | grep -i "TK"
```
Iterate the link list until it links with the minimal set; record the measured DLL list + total MB in the build doc (target ≈ 15 MB per the spec). If a link error names a missing `TK*`, add exactly that one back.

- [ ] **Step 4: LGPL attribution.** Grep for the existing about/version/licenses surface (e.g. `grep -rn "Uses\|License\|Copyright\|RhinoCommon" src/Rook src/RookNative --include=*.cpp --include=*.cs -l`), add a line: "This software uses Open CASCADE Technology (https://www.opencascade.com), licensed under LGPL 2.1." Confirm OCCT is dynamically linked (it is — DLLs).

- [ ] **Step 5: Commit** (replace `<licenses-file>` with the actual path located in Step 4 — e.g. an about/version `.cpp` in `src/RookNative` or a `.cs` in `src/Rook`; do NOT commit a literal placeholder)
```
git add src/RookNative/RookNative.vcxproj src/RookNative/OcctPrimitiveTests.vcxproj docs/rook_docs/occt-build-7.9.3.md <licenses-file-from-step-4>
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

- **TEST VENUE = IN-PLUGIN (amended).** The converter/engine are validated inside RookNative via the dev route `POST /scene/occt_validate_converter` against precomputed oracle constants (Task 4 table) — NOT a standalone openNURBS console. The only offline C++ test is the OCCT-modeling-only primitive matrix (`OcctPrimitiveTests`). Validation loop is controller-coordinated: implementer builds the `.rhp`; controller deploys (Rhino CLOSED) + hits the route (Rhino OPEN). Dev routes are removed in Task 8 Step 5.
- **OCCT converter internals (Tasks 4–5) are compiler-and-oracle-driven.** The exact `Geom2d_BSplineCurve`/`BRepBuilderAPI` call sequences will be refined against the MSVC compiler and the oracle area match — the bar (oracle within 1e-4) is the contract, not a fixed code listing. This is deliberate: bit-exact OCCT code cannot be authored blind, and orientation bugs hide behind plausible-looking faces (spec §3.1 rationale).
- **Tolerance unit boundary (issue-5 resolution):** there are TWO distinct tolerances. `CandidateQueryOptions.tolerance` stays **model-units** and feeds ONLY the broad-phase candidate query — do not touch its meaning. The OCCT fuzzy is a SEPARATE HTTP param **`fuzzMm`** (mm), converted ONCE in `Compute` (Task 8 Step 3) via `tolModelUnits = fuzzMm / modelUnitsToMillimeters` before reaching `Common`. Never reinterpret `opts.tolerance` as mm; never let an unconverted mm value reach `Common`.
- **Move-only payloads:** `ObjectBrepPayload` never enters the cache or gets copied. Only `ExactAdjacencyCore` (plain data) is cached/serialized. If a build error mentions a deleted copy ctor on a payload vector, you are copying where you must move.
- **`kEngineVersion` is bumped to 2** → the adjacency cache auto-drops Gate-4 entries on first call. Do not also clear manually.
- **No STEP anywhere in the C++ build:** no production TU AND no C++ test TU includes a `STEPControl_*`/DataExchange header. The STEP oracle was consumed once, offline, via Python OCP to produce the constants in the Task-4 table; the `.stp` fixtures are never read by a shipped or test binary. Any `STEPControl_*` include is a regression against spec §1's invariant.
