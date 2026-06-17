# OcctAdjacencyEngine — Production Exact-Adjacency Engine (design spec)

> **⚠ Extraction note (Slice A, `feature/occt-adjacency-engine`):** This spec describes the OCCT
> engine that ships on this branch, plus a *temporarily-retained* `LegacyPlanarAdjacency` unit +
> Clipper2 vendor code used during migration. Those legacy/Clipper2 artifacts were **pruned from
> this OCCT extraction branch** (archived on `feature/spatial-intelligence`); only the OCCT engine
> ships here. The downstream graph layer this engine feeds
> (`docs/rook_docs/2026-06-14-spatial-graph-projection-design.md`) is included as a docs-only
> companion and is implemented in Slice B (Exact Adjacency Projection v1).

> **Status (2026-06-15): APPROVED via brainstorming + reviewer gate — ready for writing-plans.**
> This spec defines the production `OcctAdjacencyEngine` that replaces the Gate-4
> hand-rolled Clipper2 planar engine behind the existing `IExactAdjacencyEngine`
> seam. It is **adjacency-only**. The uniform-OCCT *decision* and its empirical
> validation are upstream and settled — see prerequisites. This spec does not
> relitigate the engine choice; it specifies the build.
>
> **Branch:** `feature/spatial-intelligence` (worktree
> `C:/Users/aryan/source/repos/rook-spatial`). `main` untouched.
> **Verify branch before every commit.**

## Prerequisites (read first, do not relitigate)

1. `docs/rook_docs/2026-06-14-occt-uniform-engine-decision.md` — the decision +
   spike campaign A–E, G + strengtheners 1–2 + measured numbers. The engine choice,
   threading model, serialized-concurrency policy, and footprint are settled there.
2. `docs/rook_docs/2026-06-14-spatial-graph-projection-design.md` — the graph layer
   this engine's edges feed (next slice; out of scope here).
3. `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md` — the gated roadmap
   (this supersedes its Gate-4 narrow-phase choice).
4. Gate-4 spec/plan: `docs/superpowers/specs/2026-06-14-gate4-exact-adjacency-design.md`,
   `docs/superpowers/plans/2026-06-14-gate4-exact-adjacency.md`.

---

## 1. Goal & definition of done

**Goal:** ship the real `OcctAdjacencyEngine` behind the existing
`IExactAdjacencyEngine` seam — geometric shared-face-area adjacency over arbitrary
Breps (planar **and** curved, **open** and closed) — productionized and mergeable.

**Definition of done:**
- `POST /scene/graph/adjacency/exact` on `SpatialTest.3dm` returns the spike-validated
  solid-pair areas (wall×wall = **18651.672 in²**, cross-checking to 12,033,312.7 mm²
  = in² × 645.16 against the temp-STEP oracle), **and recovers the open-floorplate
  abutments** the Gate-4 engine was structurally blind to (open floorplate `08d4dedf`
  → the 5 user-confirmed abutments from Spike A).
- Every unsupported / partially-supported / failed object carries reason codes
  explaining its state (see §4 invariant). `rhino_ping` stays green; the UI never blocks.
- OCCT pinned to **7.9.3**; the vcxproj OCCT path is a property/env var (no hardcode);
  only the measured DLL closure is deployed; LGPL attribution present.
- `main` untouched. The Clipper engine remains shelved (see §2), not deleted.

**In scope:** new owning geometry payload + main-thread extraction; `ON_Brep`→`TopoDS`
direct converter (surfaces + trims/pcurves) with face-index preservation; the OCCT
compute kernel; diagnostic-propagation fix; de-planarized capability vocabulary; build
productionization.

**Out of scope (deferred):** exact containment/hosting; Spike-F construction tier
(`MakerVolume`/`CellsBuilder` → zones/circulation, where OCCT topological identity via
`IsSame` lives); the graph projection/intelligence layer; multi-core OCCT.

**Invariants (do not violate):**
- **No STEP exporter / no Rhino export command in the runtime adjacency path.**
  Temp-STEP exists *only* in the offline test/oracle harness. This protects the
  direct-converter decision.
- **No `CRhinoDoc`/`CRhinoObject` pointer crosses the engine seam.**
- **OCCT calls are serialized** (v1 concurrency policy). No hand-rolled threading of
  OCCT booleans.
- **OCCT never enters `CSceneGraph`** (it stays bbox-only, broad-phase).

---

## 2. The seam & data-contract change

The seam stays *swappable* but is **no longer the dependency-free plain-data seam**.
State it honestly: **the engine seam becomes openNURBS + OCCT capable**, with the hard
guarantee that no Rhino SDK type crosses it.

```cpp
struct ObjectBrepPayload {                 // openNURBS-based; NO Rhino SDK types
    std::string objectId;
    std::unique_ptr<const ON_Brep> brep;   // owned, IMMUTABLE deep-copy; null if unsupported/failed
    Capability capability;                 // see §4
    double modelUnitsToMillimeters;        // doc unit scale; tolerance + area metadata
    std::vector<std::string> diagnostics;  // source/candidate extraction reason codes
};
// Move-only (unique_ptr). Payloads are TRANSIENT: built per-call, passed by
// const-ref / moved, NEVER copied, NEVER cached. Only the plain-data
// ExactAdjacencyCore is cached.

class IExactAdjacencyEngine {
public:
    virtual ~IExactAdjacencyEngine() = default;
    virtual ExactAdjacencyCore Evaluate(
        const ObjectBrepPayload& source,
        const std::vector<ObjectBrepPayload>& candidates,
        double toleranceModelUnits) const = 0;
};
```

**Why this respects the settled rules:** `ON_Brep` is openNURBS, not the Rhino SDK.
Main thread does only: lookup → `ON_Brep` deep-copy → classify supported-ness → record
`modelUnitsToMillimeters`. Worker thread does: `ON_Brep`→`TopoDS` convert + serialized
`Common().Area`. The threading model from Gate 4 is unchanged.

**Standalone test target:** the payload change **reshapes/obsoletes** the existing
dependency-free `ExactAdjacencyTests` target. The new engine is exercised in-plugin +
via an OCCT-linked offline harness (see §6). The pure geometry-math helpers that remain
dependency-free can keep a unit target; the OCCT path cannot.

**Cache:** because the payload type and `kEngineVersion` both change, the adjacency
cache key changes; old entries drop on first call (already the cache's behavior on
engine-version bump). `ExactAdjacencyCore` (plain data) remains the only cached type.

**Clipper retention (concrete, no `#if`):** `PlanarAdjacencyEngine.{h,cpp}` and the old
`ObjectFaceSummary`/`PlanarFace` types are retained as a **self-contained shelved legacy
unit with its own interface** — it does *not* implement the new `IExactAdjacencyEngine`
signature. It is **excluded from the production `.rhp` target** and **compiled only by
its existing standalone test** (that legacy regression is the real use case that keeps
it from bitrotting). It is **not wired into `ExactAdjacencyService`**. If maintaining the
legacy test later proves not worth it, drop the files wholesale rather than leaving
half-compiled paths.

---

## 3. The `OcctAdjacencyEngine` + direct converter

### 3.1 Converter (`ON_Brep`→`TopoDS`, worker thread, pure openNURBS + OCCT)

- **Surfaces:** proven machine-exact in Spike D. Gotchas already solved: `rhino3dm`/
  openNURBS `Point4d` control points are **homogeneous** (divide by W for OCCT euclidean
  poles + weight); knot vectors need an **end-knot prepended/appended** for OCCT's
  flat-knot convention.
- **Trims/pcurves (the Strengthener-1 half, written here for the first time):** per face,
  copy each `ON_BrepLoop`'s pcurves → OCCT 2D curves →
  `BRepBuilderAPI_MakeEdge(pcurve, surface)` → `BRepBuilderAPI_MakeWire` (outer + holes)
  → `BRepBuilderAPI_MakeFace` → `ShapeFix_Face`. Use the `ON_Brep`'s own pcurves directly
  (exact; lower-risk than the 3D-edge reproject that failed in
  `spike_strengthener1_trimface.py`). Validated in-plugin against the live `ON_Brep` and
  cross-checked against the temp-STEP oracle (in² × 645.16).
- **Orientation & topology fidelity (explicit requirement — not optional):** the converter
  MUST preserve, not approximate:
  - **Face reversal** — `ON_BrepFace::m_bRev` maps to the OCCT face orientation
    (`TopoDS_Face` reversed flag); a converted face's natural normal must match the
    `ON_Brep`'s oriented normal.
  - **Trim traversal direction** — each `ON_BrepTrim::m_bRev3d` / 2d sense maps to the
    OCCT edge orientation within the wire, so the wire is consistently directed.
  - **Outer vs inner loop semantics** — `ON_BrepLoop::outer` builds the bounding wire;
    `ON_BrepLoop::inner` (holes) are added as reversed wires so `MakeFace` subtracts them.
    Holes must remain holes, not become separate faces.
  - **Seam trims** (`ON_BrepLoop`/trim seam type) — handled so periodic/closed surfaces
    (cylinders, full revolves) build a valid closed face rather than an open gap.
  - **Singular trims** (collapsed edges, e.g. sphere/cone poles) — represented as OCCT
    degenerated edges, not dropped (dropping them leaves an invalid wire).
  Rationale: without these, the first implementation can build *plausible but wrong* faces
  that still look "mostly working" on simple boxes and fail silently on real geometry.
  `ShapeFix_Face` is a safety net, **not** a substitute for correct orientation — a
  converted face whose area or normal disagrees with the `ON_Brep`/STEP oracle is a
  converter bug, not a fixup opportunity.
- **Face-index preservation (first-class requirement):** the converter returns a stable
  mapping **source `ON_Brep` face index → OCCT `TopoDS_Face`**, carried alongside the
  converted shape (not reconstructed by re-exploring). Every coincidence edge can then
  name the exact contributing `sourceFaceIndex`/`candidateFaceIndex`. Without this, the
  face-pair diagnostics are unreliable and debugging bad adjacencies is painful.

### 3.2 Compute kernel (the Spike-G/A primitive, productionized)

- For each (source face, candidate face) pair: `BRepAlgoAPI_Common(faceA, faceB)` with
  `SetFuzzyValue(toleranceModelUnits)`, sum `BRepGProp::SurfaceProperties().Mass()` of the
  result. This computes **geometric shared-face area** — it is *not* OCCT topological
  identity (`IsSame`), which is the Spike-F concept.
- Per-pair `try/catch` (OCCT can throw `Standard_Failure`; swallow per-pair → diagnostic,
  never crash — proven in Strengthener 2; note `BRepAlgoAPI_Common::HasErrors()` exists in
  the C++ API and should be checked in addition to the try/catch).
- **No opposing-normal predicate, no `IsSolid()` gate** — deleted. They were exactly what
  made the hand-rolled engine blind to open geometry; OCCT `Common()` needs neither.
- **Prefilter (must NOT reintroduce a planar assumption):** a cheap **face-bbox /
  proximity** prefilter (and optionally a same-surface-type / overlapping-parameter-domain
  check) trims `Common` calls and keeps lazy latency in the tens of ms (Spike B). A
  planar-style *coplanar* prefilter is **not** generally valid for curved/NURBS shared
  surfaces and must not be used — the prefilter only excludes pairs whose bounding boxes
  cannot touch within tolerance.
- **Edge emission:** `sharedArea > areaTol` → emit an `ExactEdge` carrying
  `{sourceId, targetId, "adjacent_exact", sharedArea}` **plus a structured
  `facePairs` array** — `[{sourceFaceIndex, candidateFaceIndex, sharedArea}, …]` — one
  entry per contributing coincident face pair (areas sum to the edge `sharedArea`). This
  is **first-class structured data on the edge**, not only a human-readable diagnostic
  string: it makes regression tests precise and is directly consumable by the future graph
  projection layer. (Per-pair diagnostic strings may still be emitted for `engine:…`
  failures, but the *successful* contributions live in `facePairs`.) `areaTol` is a
  **numerical noise floor** (model-units²), not a duplicate/graze semantic policy — a
  coincident-duplicate object honestly reporting full-surface overlap is correct geometry;
  semantic classification belongs to a later layer.
- **Serialized** via the service's worker discipline / mutex (v1 concurrency policy).

### 3.3 Unit contract

The converter **preserves Rhino document units** — OCCT operates in model units (inches
for `SpatialTest.3dm`). Therefore:
- `Common().Area` returns **model-units²**. The route's `sharedArea` stays model-units²
  and gains explicit unit metadata: `lengthUnit` (e.g. `"inches"`) and `areaUnit` (e.g.
  `"inches^2"`). Units are never implicit.
- **Tolerance is in model units.** The conceptual fuzzy (~1e-3–1e-2 mm) is converted:
  `toleranceModelUnits = toleranceMm / modelUnitsToMillimeters`. A nonzero fuzzy is
  mandatory (Spike C: `fuzz=0` finds nothing even for confirmed contacts).

---

## 4. Diagnostic propagation + de-planarized vocabulary

**The bug (precise):** `PlanarAdjacencyEngine::Evaluate` ignores `source.diagnostics`
entirely and drops every candidate's diagnostics; only engine-internal codes
(`degenerate_normal`, `clipper_exception`) reach `core.diagnostics`. So the HTTP
`diagnostics` array never explains *why* a face/object degraded — the honest-degradation
invariant is violated.

**The fix:** `OcctAdjacencyEngine::Evaluate` merges into `core.diagnostics`:
- **source** extraction diagnostics (namespaced `source:…`),
- **each candidate's** extraction diagnostics (namespaced `cand:<id>:…`),
- **engine-internal** per-pair codes (namespaced `engine:…`, e.g. conversion failure,
  `Common` exception, face-pair that contributed an edge).

**Capability vocabulary (de-planarized — a curved success must never be labeled
planar). Four states (keep `PartialExactBrep`; honest degradation needs it):**
- `ExactBrep` — all relevant analytic Brep faces converted and evaluated.
- `PartialExactBrep` — at least one face converted/evaluated, but some faces were skipped
  or failed conversion with diagnostics.
- `UnsupportedGeometry` — no Brep/analytic exact path (mesh / SubD / non-Brep).
- `FailedWithDiagnostics` — object-level failure (bad id / no geometry / extraction or
  conversion failure / face-cap exceeded).

Wire contract: relationship stays `adjacent_exact`; `sourceCapability` and per-candidate
`capability` serialize the new enum. **No `exact_planar` string anywhere.**

**No-edge invariant (tightened):** every `UnsupportedGeometry`, `PartialExactBrep`, or
`FailedWithDiagnostics` object carries reason codes. **Zero exact edges on an `ExactBrep`
object is valid and is NOT an error** — a fully supported object can simply not touch any
candidate.

---

## 5. Build productionization

- **Pin OCCT 7.9.3** (checkout `V7_9_3`): has official wheels, avoids the 8.0 API churn
  that already cost two fixes (`TopTools_ListOfShape` alias, `Standard_False`). This is
  the version A–E validated.
- **Runtime build links only the minimal non-DataExchange OCCT closure required by the
  direct converter and boolean kernel**, **measured with `dumpbin`** — do not freeze a
  module label. The converter/kernel pull `BRepBuilderAPI`, `ShapeFix_Face`, `Geom`,
  `TopoDS`, `BRepAlgoAPI`, `BRepGProp`, `GProp`, etc., which map to a specific set of
  `TK*` libraries; the deployed closure is whatever `dumpbin` reports for the linked
  `.rhp`, not an assumed "modeling module" list. (DataExchange / STEP toolkits —
  `TKDESTEP`/`TKXCAF`/… — are excluded from the runtime build and exist only in the
  offline test harness; dropping them is what reduces the closure below the 34.4 MB
  STEP-path measurement.)
- **Replace the hardcoded vcxproj OCCT path** (the Spike-G tracer shortcut) with an
  MSBuild property / env var (e.g. `$(OcctRoot)`), documented in the build doc.
- **Deploy only the measured DLL closure** next to the `.rhp` (Rhino finds them there —
  Spike G; no `AddDllDirectory` needed).
- **LGPL compliance:** dynamic-link OCCT + a "This software uses Open CASCADE Technology"
  attribution in the about/licenses surface.

---

## 6. Testing strategy

- **Pure helpers** (unit conversion, bbox/proximity prefilter math, diagnostic merging,
  edge keying) — keep dependency-free unit tests where the code stays Rhino/OCCT-free.
- **Converter fidelity (offline OCCT harness):** convert a real `ON_Brep` directly and
  compare its per-face / total surface area against the **temp-STEP oracle** for the same
  object (in² × 645.16). This is where temp-STEP legitimately lives. Covers the
  Strengthener-1 trimmed-face proof in C++ at last.
  - **Oracle generation (separate dev/test artifact):** oracle STEP files are produced
    **out-of-band, ahead of the test run** — exported once per fixture object from Rhino
    (interactive `-_Export` / `FileStp`, or the existing spike export) into a committed,
    gitignored fixtures dir (mirroring `docs/rook_docs/occt-spike/steps/`, which is
    gitignored — user geometry is never committed). The test harness **reads** these
    pre-existing `.stp` files via `STEPControl_Reader`; it never generates them.
  - **Hard separation from runtime:** STEP export and the STEP oracle are **dev/test-only
    artifacts**. They are **never** invoked by the `POST /scene/graph/adjacency/exact`
    route, by `ExactAdjacencyService`, or by any live-verification path, and the
    DataExchange/STEP toolkits are **not linked into the production `.rhp`** (§5). This is
    the enforcement of the no-STEP-runtime invariant (§1): the only code that can touch a
    STEP file is the offline harness target.
- **Engine correctness (in-plugin, live Rhino):** `POST /scene/graph/adjacency/exact` on
  `SpatialTest.3dm`; assert the validated solid-pair areas and the open-floorplate
  abutments; assert honest reason codes for a mesh and a SubD object; assert `ExactBrep`
  objects with no neighbors return zero edges and no error.
- **Robustness matrix:** port `spike_strengthener2_coverage.py`'s 9 cases (abutting / gap
  > fuzzy / gap < fuzzy / coincident duplicate / interpenetration / far-from-origin /
  sliver / degenerate / curved-on-planar) as engine-level assertions.
- **Concurrency:** the serialized path is exercised; no multi-core claim is tested
  (per policy).
- **Reach native HTTP from Python `urllib`, never `curl`** (security-software
  constraint). Deploy requires Rhino **closed** (file lock); live tests require Rhino
  **open**. Build → deploy (Rhino closed) → open Rhino → test.

---

## 7. File structure (keep / replace / new)

**KEEP (unchanged):**
- `CSceneGraph` + `QueryCandidatesAsync` (broad phase; OCCT never enters it).
- `ExactAdjacencyService` orchestration + cache + three-thread-hop (payload type and
  engine swap aside).
- HTTP route `POST /scene/graph/adjacency/exact` + handler shell (response fields extend:
  `lengthUnit`, `areaUnit`, new capability strings, and per-edge `facePairs`).
- `OcctProbe.{h,cpp}` may be retired or folded into the converter/kernel once the real
  engine subsumes it (the tracer's `Common`-over-face-pairs is the kernel seed).

**REPLACE / SHELVE:**
- `PlanarAdjacencyEngine.{h,cpp}` + old `ObjectFaceSummary`/`PlanarFace` → shelved legacy
  unit (own interface, excluded from `.rhp`, legacy test only). Not wired in.
- `IsSolid()` gate + opposing-normal predicate + per-face planar projection → deleted.
- Main-thread extraction → produces `ObjectBrepPayload` (deep-copy `ON_Brep` + classify +
  unit scale), not the planar `ObjectFaceSummary`.

**NEW:**
- `OcctAdjacencyEngine.{h,cpp}` — converter + kernel + diagnostics, behind the new seam.
- `OnBrepToOcct.{h,cpp}` (or equivalent) — the `ON_Brep`→`TopoDS` converter with
  face-index mapping (separable unit so it is independently testable in the offline
  harness).
- New `Capability` enum + `CapabilityToString` updates.
- Build wiring: `$(OcctRoot)` property; production `TK*` link subset (measured);
  offline test harness target (links DataExchange for the STEP oracle).

---

## 8. Sequencing note (for writing-plans)

Natural build order, TDD throughout: (1) new `Capability` enum + payload type + seam
signature; (2) main-thread extraction producing `ObjectBrepPayload`; (3) the converter
(surfaces → trims → face-index map), validated against the STEP oracle offline; (4) the
compute kernel + prefilter + tolerance/areaTol; (5) diagnostic merging + de-planarized
wire contract; (6) wire `OcctAdjacencyEngine` into `ExactAdjacencyService`, shelve
Clipper; (7) build productionization (7.9.3 pin, `$(OcctRoot)`, measured DLL closure,
LGPL); (8) in-plugin live verification on `SpatialTest.3dm`. Merge after live
verification — the user pulls the trigger (per doctrine).
