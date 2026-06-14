# Gate 4 — Exact Planar Adjacency Service (design spec)

> **Status: DRAFT — revised 2026-06-14 (round 2), addressing Codex findings 1-6
> then 7-10.** Awaiting re-confirmation before `writing-plans`. First gate that
> touches production C++ in `RookNative`.
> **Parent:** `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md` (Gate 4
> of the spatial-intelligence roadmap). Gates 0-3 proved: adjacency = pure-Python
> **B2** (coplanar + Sutherland-Hodgman polygon overlap) for planar; OCCT
> (`face.common().Area`) for curved; `CSceneGraph` is a background-thread, bbox-only,
> geometry-light pipeline. **Work happens in the `rook-spatial` worktree on branch
> `feature/spatial-intelligence`.**

## 1. Purpose & scope

Add **exact planar shared-face adjacency** as a **lazy, on-demand, query-time
refinement** of the scene graph — without disturbing the continuous bbox pipeline.
v1 = planar exact only, **convex outer/inner loops, with holes**, requiring
**opposing face normals**; curved is designed-for (pluggable engine) but not
implemented and must produce an **honest flagged result, never a false exact**.

**In scope (v1):** planar exact engine (opposing-normal, hole-aware, convex-loop);
`ExactAdjacencyService`; minimal `CSceneGraph` candidate-query read; one HTTP route;
cache; explicit capability + diagnostics reporting; unit + smoke tests.

**Out of scope (v1):** curved engine; **concave-loop polygon clipping** (robust
boolean — flagged unsupported in v1); kernel choice for curved; folding exact edges
into the Python networkx mirror; per-object cache generation stamps; prewarming;
MCP tool wrapper.

## 2. Binding constraints (do not violate)

1. **No Rhino SDK pointers cross threads.** Extraction on the main thread yields only
   plain structs.
2. **Continuous bbox pipeline untouched.** No face data, cache, or extraction in
   `CSceneGraph`; not on the watcher hot path.
3. **No silent fallback.** Every candidate carries an explicit capability status.
4. **`m_rtree` / `m_rtreeIdOrder` are processor-thread-owned.** Never read from an
   HTTP worker thread.
5. **Don't widen `ObjectEvent` / `SceneNode`.** Summaries live in the service.

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
    bool capped;                           // true if neighborhood exceeded maxCandidates
    int totalCandidateCount;               // pre-cap count
};
std::future<CandidateQueryResult>
CSceneGraph::QueryCandidatesAsync(const std::string& objectId,
                                  const CandidateQueryOptions& opts);
```
The existing `FindNeighborIds` returns raw RTree order built from `unordered_map`
iteration (nondeterministic). `QueryCandidatesAsync` must, on the processor thread:
gather RTree neighbors → **score each by (bbox distance asc, then bbox overlap desc,
then objectId asc)** → **sort deterministically** → **then cap** to `maxCandidates`.
Capping raw RTree order is forbidden.

Geometry extraction reuses the existing **`CMainThreadDispatcher`** (pattern from
`GeometryHandler.cpp:321`).

## 4. Data model (plain structs, owned by the service)

```cpp
enum class FaceKind { Planar, Curved, MeshApprox, Unknown };

// Declared before ObjectFaceSummary (Finding 10 — valid declaration order).
enum class Capability {
    ExactPlanar,                           // all faces planar, convex, valid; exact computed
    PartialExactPlanarCurvedUnsupported,   // some exact-eligible, some not (curved/concave)
    CoarseFallbackCurvedUnsupported,       // no exact-eligible planar faces
    UnsupportedGeometry,                   // mesh/subd/malformed loops
    FailedWithDiagnostics
};

struct PlanarFace {
    std::array<double,3> outwardNormal;    // ORIGINAL oriented normal — for the
                                           //   opposing-normal predicate (Finding 7)
    std::array<double,4> canonicalPlane;   // sign-folded normal+offset — for COPLANAR
                                           //   grouping only (NOT the predicate)
    // loops[0] = outer boundary; loops[1..] = inner loops (holes). All loops MUST be
    // convex in v1 (Finding 8); concave -> face is not exact-eligible.
    std::vector<std::vector<std::array<double,3>>> loops;
    bool allLoopsConvex = false;           // false -> excluded from exact (flagged)
};
struct FaceSummary {                       // exactly ONE face
    FaceKind kind = FaceKind::Unknown;
    PlanarFace planar;                     // valid iff kind==Planar
    // curved: reserved future surface descriptor (NOT populated in v1)
};
struct ObjectFaceSummary {                 // ONE object's faces
    std::string objectId;
    std::vector<FaceSummary> faces;
    Capability capability;                 // object-level rollup (see §5)
    std::vector<std::string> diagnostics;  // why curved/concave/unsupported
};

struct ExactEdge {
    std::string sourceId, targetId;
    std::string relationship = "adjacent_exact";
    double sharedArea = 0.0;               // hole-aware (see §5)
};
struct CandidateOutcome {
    std::string id;
    Capability capability;
    std::optional<std::string> coarseRelationship;  // bbox context if includeCoarse
};
struct ExactAdjacencyResult {
    std::string objectId;
    int graphSequence = 0;
    Capability sourceCapability = Capability::FailedWithDiagnostics;
    std::vector<ExactEdge> edges;
    std::vector<CandidateOutcome> candidates;
    bool capped = false;
    int candidateCount = 0;                // evaluated (post-cap)
    int candidateLimit = 0;                // the cap applied
    int totalCandidateCount = 0;           // pre-cap neighborhood size (Finding 9)
    std::vector<std::string> diagnostics;
};
```

**Pluggable engine — evaluates OBJECT summaries:**
```cpp
class IExactAdjacencyEngine {
public:
    virtual ~IExactAdjacencyEngine() = default;
    // Pure function of plain data — no Rhino, no threads. Unit-testable in isolation.
    virtual ExactAdjacencyResult Evaluate(
        const ObjectFaceSummary& source,
        const std::vector<ObjectFaceSummary>& candidates,
        double tolerance) const = 0;
};
class PlanarAdjacencyEngine : public IExactAdjacencyEngine { /* §5 */ };
// CurvedAdjacencyEngine — later, behind this same interface.
```

## 5. Planar engine predicate (Findings 7 + 8) + capability

Two objects are **adjacent_exact** iff some face pair `(A,B)` — one face from each
object — satisfies ALL THREE:

1. **Coplanar:** `A.canonicalPlane == B.canonicalPlane` (within tolerance) — grouping
   only.
2. **Opposing normals (Finding 7):** `dot(A.outwardNormal, B.outwardNormal) < -(1 - normalTol)`.
   Genuine solid shared-face adjacency has antiparallel outward normals (each solid's
   boundary points outward, toward the other). This rejects same-normal coplanar
   overlaps: stacked duplicate surfaces, two co-facing panels, duplicate geometry.
3. **Convex loops (Finding 8):** both faces have `allLoopsConvex == true`. (Required
   because Sutherland-Hodgman is only correct when the clip polygon is convex.)

For a qualifying pair, **hole-aware shared area** (all loops convex):
```
base = SHclip(A.outer, B.outer)
if area(base) <= tol²: contributes 0
area = area(base)
for hA in A.holes: area -= area(SHclip(base, hA))
for hB in B.holes: area -= area(SHclip(base, hB))
for hA in A.holes:                              # inclusion-exclusion add-back for
  for hB in B.holes:                            # regions inside a hole of BOTH faces
    area += area(SHclip(SHclip(base, hA), hB))
sharedArea(pair) = max(0, area)
```
Holes within one face are disjoint (Brep guarantee). Object-pair `sharedArea` = sum
over qualifying pairs with `sharedArea > tol²`. Correctly handles the
**wall-with-window-opening** case (overlap inside an opening is not contact).

**Object-level capability rollup (per `ObjectFaceSummary`):**
- every face `Planar` & `allLoopsConvex` & valid → `ExactPlanar` eligible
- mix of exact-eligible + non-eligible (curved OR concave) →
  `PartialExactPlanarCurvedUnsupported`; eligible faces still evaluated; diagnostics
  name the skipped faces (curved vs concave)
- no exact-eligible planar faces → `CoarseFallbackCurvedUnsupported`
- mesh/subd/malformed loops → `UnsupportedGeometry`

A candidate's `CandidateOutcome.capability` = min eligibility of the source/candidate
pair. Non-eligible faces never yield an `adjacent_exact` edge; `includeCoarse=true`
may attach the bbox relationship as context.

## 6. Data flow (three thread hops)

```
[worker]     handler receives { objectId, opts }
   │ EnqueueAction
   ▼
[processor]  QueryCandidatesAsync: RTree neighbors -> score -> sort nearest-first
             -> cap. Returns {seq, sourceNode, scored caps, capped, totalCandidateCount}
   │ CMainThreadDispatcher::Dispatch  (caps + face-count cap + extraction budget = protection)
   ▼
[main]       for source + capped candidates: fetch CRhinoObjects, extract
             ObjectFaceSummary (per planar face: outwardNormal, canonicalPlane,
             outer/inner loops, convexity check; classify curved/mesh/unknown).
             EXTRACTION ONLY — no SDK pointers escape.
   │ returns vector<ObjectFaceSummary> (plain data)
   ▼
[worker]     PlanarAdjacencyEngine.Evaluate(source, candidates, tol) -> ExactAdjacencyResult
   │ cache + return
```

## 7. Safety & limits (over-cap = successful partial result)

- **Candidate cap** (default 64) — applied AFTER deterministic nearest-first sort.
- **Face-count cap** + **extraction budget** inside the main-thread lambda — the REAL
  stall protection (the dispatch future timeout does NOT preempt a running lambda; it
  only reports caller-side failure as `FailedWithDiagnostics`).
- **Over-cap = SUCCESSFUL PARTIAL RESULT**: exact result for the nearest-first capped
  candidates with `capped=true`, `candidateCount`, `candidateLimit`,
  `totalCandidateCount`. Never silent truncation, never hard failure.
- **No watcher routing**; bbox pipeline untouched.

## 8. Cache & invalidation

```
CacheKey = (objectId, graphSequence, tolerance, maxCandidates, engineVersion)
```
v1 invalidation: drop entries on `graphSequence` change. `engineVersion` bumps when
the planar engine math changes. Per-object generation stamps = later optimization.

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
    candidateLimit:      int,   // cap applied
    totalCandidateCount: int,   // pre-cap neighborhood size (Finding 9)
    diagnostics:         [ string ]
  }
```
Overlay only — the `CSceneGraph` snapshot **never** holds `adjacent_exact` edges.
`capability`, `capped`, `totalCandidateCount`, and `diagnostics` are first-class so
implementers cannot improvise incompatible shapes.

## 10. Build / project-file impact

`ExactAdjacencyService.cpp` is a **new compiled translation unit** → must be added to
`src/RookNative/RookNative.vcxproj` (+ `.filters`). Standing rule: **do not edit
`.vcxproj` unless the task explicitly authorizes it** — the implementation plan must
make this a discrete, explicitly-authorized step. Build via
`scripts/build-native.bat`.

## 11. Testing

**Engine unit tests (no Rhino — plain `ObjectFaceSummary` structs; reuse Gate-1/2/3
fixtures):**
- multi-face objects (box/wall/slab) adjacent → exact edge on the shared face only;
- partial overlap (column-on-slab) → exact edge;
- bbox-near-but-not-touching (150mm gap) → no edge; corner-only → no edge;
- **opposing-normal discrimination (Finding 7):** two coplanar faces with the SAME
  outward normal (stacked duplicate surfaces / co-facing panels) → **no** edge;
  genuine opposing-normal coincident faces → edge;
- **wall face with a window hole:** overlap inside the hole → NOT counted; overlap on
  solid → counted (hole-aware correctness);
- **concave loop (Finding 8):** face with a concave outer or inner loop → flagged
  not-exact-eligible (capability reflects it, diagnostic names concavity), never a
  silently-wrong area;
- mixed planar+curved object → `PartialExactPlanarCurvedUnsupported`;
- deterministic candidate ordering (same input → same capped set).

**Live-Rhino integration smoke:**
- modify/delete object → cache invalidates (graphSequence bump);
- neighborhood over cap → `capped=true` partial result, nearest-first,
  `totalCandidateCount` reported;
- curved object → `CoarseFallbackCurvedUnsupported` (never false exact);
- mesh/subd → `UnsupportedGeometry`.

## 12. Deferred to later gates/specs
- Curved engine + kernel choice (Rhino OpenNURBS vs OCCT-in-plugin) — Gate 3b/4b.
- **Concave-loop polygon clipping** (robust boolean: Weiler-Atherton / a polygon
  library) — v1.1; flagged unsupported in v1.
- Folding overlay edges into the Python networkx mirror.
- Per-object cache generation stamps; prewarming.
- Scale validation of cap/dispatch under large neighborhoods — Gate 5.
