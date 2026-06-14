# Gate 4 — Exact Planar Adjacency Service (design spec)

> **Status: DRAFT — revised 2026-06-14 (round 3).** Adopts Clipper2 for the 2D
> polygon boolean (replacing hand-rolled Sutherland-Hodgman) and addresses Codex
> findings 1-10. Awaiting re-confirmation before `writing-plans`. First gate that
> touches production C++ in `RookNative`.
> **Parent:** `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md` (Gate 4
> of the spatial-intelligence roadmap). Gates 0-3 proved: adjacency = planar polygon
> overlap (now via Clipper2) for planar; OCCT (`face.common().Area`) for curved;
> `CSceneGraph` is a background-thread, bbox-only, geometry-light pipeline.
> **Work happens in the `rook-spatial` worktree on branch `feature/spatial-intelligence`.**

## 1. Purpose & scope

Add **exact planar shared-face adjacency** as a **lazy, on-demand, query-time
refinement** of the scene graph — without disturbing the continuous bbox pipeline.
v1 = planar exact (**concave + holes supported via Clipper2**), requiring **opposing
face normals**; curved is designed-for (pluggable engine) but not implemented and
must produce an **honest flagged result, never a false exact**.

**In scope (v1):** planar exact engine (opposing-normal, Clipper2 polygon boolean,
concave + holes); `ExactAdjacencyService`; minimal `CSceneGraph` candidate-query
read; one HTTP route; cache; explicit capability + diagnostics; vendor Clipper2;
unit + smoke tests.

**Out of scope (v1):** curved engine; kernel choice for curved; folding exact edges
into the Python networkx mirror; per-object cache generation stamps; prewarming;
MCP tool wrapper. (Concave clipping is now IN scope, handled by Clipper2.)

## 2. Binding constraints (do not violate)

1. **No Rhino SDK pointers cross threads.** Extraction on the main thread yields only
   plain structs.
2. **Continuous bbox pipeline untouched.** No face data, cache, or extraction in
   `CSceneGraph`; not on the watcher hot path.
3. **No silent fallback.** Every candidate carries an explicit capability + reasons.
4. **`m_rtree` / `m_rtreeIdOrder` are processor-thread-owned.** Never read from an
   HTTP worker thread.
5. **Don't widen `ObjectEvent` / `SceneNode`.** Summaries live in the service.
6. **Reuse libraries for hard geometry.** Clipper2 for 2D polygon boolean; OpenNURBS
   `ON_RTree` for spatial index; OCCT (later) for curved. Hand-write only trivial
   CAD glue (coplanar grouping, normal dot, projection, tolerance policy).

## 3. Architecture & boundary

New sibling module: `src/RookNative/SceneGraph/ExactAdjacencyService.{h,cpp}`.

`CSceneGraph` gains ONE candidate-query read, run on the **processor thread** via
`EnqueueAction` (deterministic, RTree-safe):

```cpp
struct CandidateQueryOptions { int maxCandidates = 64; double tolerance = 1e-3; };
struct ScoredCandidate { std::string id; double bboxDistance; double bboxOverlap; };
struct CandidateQueryResult {
    int graphSequence;
    bool sourceFound;
    SceneNode sourceNode;                  // plain copy
    std::vector<ScoredCandidate> candidates;  // DETERMINISTIC nearest-first, then capped
    bool capped;
    int totalCandidateCount;               // pre-cap count
};
std::future<CandidateQueryResult>
CSceneGraph::QueryCandidatesAsync(const std::string& objectId,
                                  const CandidateQueryOptions& opts);
```
`QueryCandidatesAsync` (processor thread): gather RTree neighbors → **score by (bbox
distance asc, bbox overlap desc, objectId asc)** → **sort deterministically** →
**then cap**. Capping raw RTree order is forbidden (`m_rtreeIdOrder` is
`unordered_map`-iteration order, nondeterministic).

Geometry extraction reuses the existing **`CMainThreadDispatcher`**
(`GeometryHandler.cpp:321` pattern).

## 4. Data model (plain structs, owned by the service)

```cpp
enum class FaceKind { Planar, Curved, MeshApprox, Unknown };

// Declared before ObjectFaceSummary (Finding 10).
enum class Capability {
    ExactPlanar,                     // all faces planar, orientation-reliable, valid
    PartialExactUnsupported,         // some faces exact-eligible, some not (Finding 1)
    CoarseFallbackExactUnsupported,  // no exact-eligible faces (Finding 1)
    UnsupportedGeometry,             // mesh/subd/malformed loops
    FailedWithDiagnostics
};
// Per-face/object reason codes carried in ObjectFaceSummary.diagnostics:
//   "curved" | "mesh" | "subd" | "unoriented" | "malformed_loop"
//   (concave is NO LONGER a reason — Clipper2 handles it.)

struct PlanarFace {
    std::array<double,3> outwardNormal;    // ORIGINAL oriented normal — opposing-normal
                                           //   predicate. From the Brep face's oriented
                                           //   normal; valid only when orientation is
                                           //   reliable (closed/orientable solid). (Finding 4)
    std::array<double,4> canonicalPlane;   // sign-folded normal+offset — COPLANAR grouping only
    // loops[0]=outer, loops[1..]=holes. Concave allowed (Clipper2). Plane-local 2D
    // projection + boolean done by the engine, not stored here.
    std::vector<std::vector<std::array<double,3>>> loops;
};
struct FaceSummary {                       // exactly ONE face
    FaceKind kind = FaceKind::Unknown;
    PlanarFace planar;                     // valid iff kind==Planar
    // curved: reserved future surface descriptor (NOT populated in v1)
};
struct ObjectFaceSummary {                 // ONE object's faces
    std::string objectId;
    std::vector<FaceSummary> faces;
    Capability capability;                 // rollup (see §5)
    std::vector<std::string> diagnostics;  // reason codes + notes
};

struct ExactEdge {
    std::string sourceId, targetId;
    std::string relationship = "adjacent_exact";
    double sharedArea = 0.0;               // Clipper2 hole/concave-aware (see §5)
};
struct CandidateOutcome {
    std::string id;
    Capability capability;
    std::optional<std::string> coarseRelationship;  // decorated AFTER cache (Finding 2)
};
struct ExactAdjacencyResult {              // CACHED CORE (no coarse decoration — Finding 2)
    std::string objectId;
    int graphSequence = 0;
    Capability sourceCapability = Capability::FailedWithDiagnostics;
    std::vector<ExactEdge> edges;
    std::vector<CandidateOutcome> candidates;
    bool capped = false;
    int candidateCount = 0;                // evaluated (post-cap)
    int candidateLimit = 0;
    int totalCandidateCount = 0;           // pre-cap (Finding 9)
    std::vector<std::string> diagnostics;
};
```

**Pluggable engine — evaluates OBJECT summaries:**
```cpp
class IExactAdjacencyEngine {
public:
    virtual ~IExactAdjacencyEngine() = default;
    virtual ExactAdjacencyResult Evaluate(
        const ObjectFaceSummary& source,
        const std::vector<ObjectFaceSummary>& candidates,
        double tolerance) const = 0;       // pure data; no Rhino, no threads
};
class PlanarAdjacencyEngine : public IExactAdjacencyEngine { /* §5, uses Clipper2 */ };
// CurvedAdjacencyEngine — later, behind this same interface.
```

## 5. Planar engine predicate (Clipper2-based)

Two objects are **adjacent_exact** iff some face pair `(A,B)` satisfies BOTH gates,
then a positive overlap:

1. **Coplanar:** `A.canonicalPlane == B.canonicalPlane` within tolerance (grouping).
2. **Opposing normals (Finding 7):** `dot(A.outwardNormal, B.outwardNormal) < -(1 - normalTol)`.
   Genuine solid shared faces are antiparallel; this rejects same-normal coplanar
   overlaps (stacked duplicates, co-facing panels, duplicate geometry).

For a qualifying pair, compute **shared area via Clipper2**:
- Project both faces' loops into **plane-local 2D** coordinates (shared in-plane
  basis derived from the canonical plane).
- Build each face as a Clipper2 path set (outer + holes) and run
  `Intersect(A, B, FillRule::NonZero)`; `sharedArea = Area(result)`.
- Clipper2 handles concave loops, holes, and self-touching robustly. **We do NOT use
  Clipper2 triangulation** (documented as buggy) — only intersection + area.
- Adjacency iff `sharedArea > areaTol`. Object-pair `sharedArea` = sum over
  qualifying face pairs.

This correctly handles the **wall-with-window-opening** case (overlap inside the
opening contributes no area) and concave faces (L-shaped slabs/walls).

**Precision policy (Clipper2 is integer-backed):** project in **model units**; feed
`ClipperD` with a fixed precision of **6 decimal places**; `areaTol` and `normalTol`
are **fixed engine constants covered by `engineVersion`** (Finding 3 — not options,
not in the cache key). Tests must exercise small architectural tolerances around
openings and near-contact gaps (§11).

**Capability rollup (per `ObjectFaceSummary`):**
- every face `Planar`, orientation-reliable, valid → `ExactPlanar`
- mix of eligible + ineligible (curved / unoriented / malformed) →
  `PartialExactUnsupported`; eligible faces still evaluated; diagnostics carry reason
  codes
- no eligible faces → `CoarseFallbackExactUnsupported`
- mesh/subd/malformed → `UnsupportedGeometry`

A candidate's `capability` = min eligibility of the pair. Ineligible faces never
yield an `adjacent_exact` edge.

## 6. Data flow (three thread hops)

```
[worker]     handler receives { objectId, opts }
   │ EnqueueAction
   ▼
[processor]  QueryCandidatesAsync: RTree -> score -> sort nearest-first -> cap
             -> {seq, sourceNode, scored, capped, totalCandidateCount}
   │ CMainThreadDispatcher::Dispatch  (caps + face-count cap + extraction budget)
   ▼
[main]       extract ObjectFaceSummary: per planar face, the Brep face's ORIENTED
             normal (mark exact-eligible only if orientation reliable — closed/
             orientable solid; open/unoriented surface -> diagnostic "unoriented",
             not eligible), canonicalPlane, outer/inner loops. Classify curved/mesh/
             unknown. EXTRACTION ONLY — no SDK pointers escape.
   │ returns vector<ObjectFaceSummary>
   ▼
[worker]     PlanarAdjacencyEngine.Evaluate(...) (Clipper2) -> ExactAdjacencyResult (core)
   │ cache CORE result; THEN decorate coarseRelationship if includeCoarse (Finding 2)
   ▼  return
```

## 7. Safety & limits (over-cap = successful partial result)

- **Candidate cap** (default 64) applied AFTER nearest-first sort.
- **Face-count cap** + **extraction budget** inside the main-thread lambda — the REAL
  stall protection (dispatch future timeout does NOT preempt a running lambda; it
  only reports caller-side failure as `FailedWithDiagnostics`).
- **Over-cap = SUCCESSFUL PARTIAL RESULT** with `capped`, `candidateCount`,
  `candidateLimit`, `totalCandidateCount`. Never silent truncation, never hard fail.
- **No watcher routing**; bbox pipeline untouched.

## 8. Cache & invalidation (Finding 2)

```
CacheKey = (objectId, graphSequence, tolerance, maxCandidates, engineVersion)
```
**Cache stores the exact CORE result only** (`includeCoarse` is NOT in the key).
`coarseRelationship` decoration happens **after** cache lookup, from the live bbox
graph — so a cached core serves both `includeCoarse` true and false. v1 invalidation:
drop entries on `graphSequence` change. `engineVersion` bumps when the engine math,
`areaTol`, `normalTol`, or Clipper2 precision changes. Per-object generation stamps =
later optimization.

## 9. API contract

```
POST /scene/graph/adjacency/exact
  body: { objectId, maxCandidates?, tolerance?, includeCoarse? }
  200 -> {
    objectId, graphSequence, sourceCapability,
    edges:      [ { targetId, relationship:"adjacent_exact", sharedArea } ],
    candidates: [ { id, capability, coarseRelationship? } ],
    capped:              bool,
    candidateCount:      int,   // evaluated (post-cap)
    candidateLimit:      int,
    totalCandidateCount: int,   // pre-cap neighborhood size (Finding 9)
    diagnostics:         [ string ]
  }
```
Overlay only — the `CSceneGraph` snapshot **never** holds `adjacent_exact` edges.

## 10. Build / dependency impact (authorized steps)

- **Vendor Clipper2** under `src/RookNative/vendor/clipper2/`; pin version + BSL-1.0
  license in `src/RookNative/vendor/versions.txt`. Clipper2 is a small C++17 library
  (a few source files, not single-header) — its `.cpp` units + `ExactAdjacencyService.cpp`
  must be added to **`src/RookNative/RookNative.vcxproj`** (+ `.filters`).
- Standing rule: **do not edit `.vcxproj` / add a vendored dependency unless the task
  explicitly authorizes it** — the implementation plan must make Clipper2 vendoring
  and the `.vcxproj` inclusion **discrete, explicitly-authorized steps**.
- Build via `scripts/build-native.bat`. Do NOT use Clipper2 triangulation.

## 11. Testing

**Engine unit tests (no Rhino — plain `ObjectFaceSummary`; reuse Gate-1/2/3 fixtures):**
- multi-face objects (box/wall/slab) adjacent → exact edge on the shared face only;
- partial overlap (column-on-slab) → exact edge;
- bbox-near-but-not-touching (150mm gap) → no edge; corner-only → no edge;
- **opposing-normal discrimination:** same-outward-normal coplanar overlap (stacked
  duplicates / co-facing panels) → **no** edge; opposing-normal coincident → edge;
- **wall face with a window hole:** overlap inside hole → not counted; on solid → counted;
- **concave face (now SUPPORTED via Clipper2):** L-shaped slab/wall adjacency →
  correct shared area;
- **precision/tolerance:** small openings and near-contact gaps around the Clipper2
  6-decimal precision boundary behave correctly (no spurious/zero area);
- mixed planar+curved object → `PartialExactUnsupported`;
- unoriented/open surface face → flagged `unoriented`, not eligible;
- deterministic candidate ordering (same input → same capped set).

**Live-Rhino integration smoke:**
- modify/delete object → cache invalidates (graphSequence bump);
- neighborhood over cap → `capped=true` partial, nearest-first, `totalCandidateCount`;
- `includeCoarse` true/false both served from one cached core (Finding 2);
- curved object → `CoarseFallbackExactUnsupported` (never false exact);
- mesh/subd → `UnsupportedGeometry`.

## 12. Deferred to later gates/specs
- Curved engine + kernel choice (Rhino OpenNURBS vs OCCT-in-plugin) — Gate 3b/4b.
- Folding overlay edges into the Python networkx mirror.
- Per-object cache generation stamps; prewarming.
- Scale validation of cap/dispatch under large neighborhoods — Gate 5.
