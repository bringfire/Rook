# Gate 4 — Exact Planar Adjacency Service (design spec)

> **Status: DRAFT — revised 2026-06-14 addressing Codex review findings 1-6.**
> Awaiting re-confirmation before `writing-plans`. First gate that touches
> production C++ in `RookNative`.
> **Parent:** `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md` (Gate 4
> of the spatial-intelligence roadmap). Gates 0-3 proved: adjacency = pure-Python
> **B2** (coplanar + Sutherland-Hodgman polygon overlap) for planar; OCCT
> (`face.common().Area`) for curved; `CSceneGraph` is a background-thread, bbox-only,
> geometry-light pipeline. **Work happens in the `rook-spatial` worktree on branch
> `feature/spatial-intelligence`.**

## 1. Purpose & scope

Add **exact planar shared-face adjacency** as a **lazy, on-demand, query-time
refinement** of the scene graph — without disturbing the continuous bbox pipeline.
v1 = planar exact only (**including planar faces with holes**); curved is
designed-for (pluggable engine) but not implemented and must produce an **honest
flagged result, never a false exact**.

**In scope (v1):** planar exact engine (hole-aware); `ExactAdjacencyService`;
minimal `CSceneGraph` candidate-query read; one HTTP route; cache; explicit
capability + diagnostics reporting; unit + smoke tests.

**Out of scope (v1):** curved engine; kernel choice for curved (Rhino OpenNURBS vs
OCCT-in-plugin); folding exact edges into the Python networkx mirror; per-object
cache generation stamps; prewarming; MCP tool wrapper.

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
`EnqueueAction` (Finding 2 — deterministic, RTree-safe):

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
**Finding 2 fix:** the existing `FindNeighborIds` returns raw RTree order built from
`unordered_map` iteration (nondeterministic). `QueryCandidatesAsync` must, on the
processor thread: gather RTree neighbors → **score each by (bbox distance asc, then
bbox overlap desc, then objectId asc)** → **sort deterministically** → **then cap**
to `maxCandidates`. Capping raw RTree order is forbidden (would miss closer
neighbors nondeterministically).

Geometry extraction reuses the existing **`CMainThreadDispatcher`** (pattern from
`GeometryHandler.cpp:321`).

## 4. Data model (plain structs, owned by the service)

**Finding 1 fix — face vs object are distinct levels:**

```cpp
enum class FaceKind { Planar, Curved, MeshApprox, Unknown };

struct PlanarFace {
    std::array<double,4> plane;            // canonical normal (xyz) + offset
    // loops[0] = outer boundary; loops[1..] = inner loops (holes). (Finding 5)
    std::vector<std::vector<std::array<double,3>>> loops;
};
struct FaceSummary {                       // exactly ONE face
    FaceKind kind = FaceKind::Unknown;
    PlanarFace planar;                     // valid iff kind==Planar
    // curved: reserved future surface descriptor (NOT populated in v1)
};
struct ObjectFaceSummary {                 // ONE object's faces (Finding 1)
    std::string objectId;
    std::vector<FaceSummary> faces;
    Capability capability;                 // object-level rollup (see §5)
    std::vector<std::string> diagnostics;  // why curved/unsupported, extraction notes
};

enum class Capability {
    ExactPlanar,                           // all faces planar & valid; exact computed
    PartialExactPlanarCurvedUnsupported,   // some planar (evaluated), some curved (not)
    CoarseFallbackCurvedUnsupported,       // no planar faces
    UnsupportedGeometry,                   // mesh/subd/malformed loops
    FailedWithDiagnostics
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
    int candidateCount = 0;                // evaluated
    int candidateLimit = 0;                // the cap applied
    std::vector<std::string> diagnostics;
};
```

**Pluggable engine — evaluates OBJECT summaries (Finding 1):**
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

## 5. Planar engine math — hole-aware (Finding 5) + capability mapping

Two objects are **adjacent_exact** iff some coplanar face pair (one from each
object) has **hole-aware shared area > tolerance²**. Per face pair `(A,B)` on the
same canonical plane:

```
base = SHclip(A.outer, B.outer)                 # 2D overlap of outer loops
if area(base) <= tol²: contributes 0
area = area(base)
for hA in A.holes: area -= area(SHclip(base, hA))
for hB in B.holes: area -= area(SHclip(base, hB))
for hA in A.holes:                              # inclusion-exclusion: add back regions
  for hB in B.holes:                            # inside BOTH a hole of A and a hole of B
    area += area(SHclip(SHclip(base, hA), hB))
sharedArea(pair) = max(0, area)
```
Holes within one face are disjoint (Brep guarantee) → no intra-face add-back needed;
only cross-face hole overlap is added back. Object-pair `sharedArea` = sum over
qualifying face pairs. This correctly handles the **wall-with-window-opening** case
(the overlap region falling inside an opening is NOT counted as contact).

**Object-level capability rollup (from each `ObjectFaceSummary`):**
- all faces `Planar` & valid → `ExactPlanar` eligible
- mix of `Planar` + `Curved` → `PartialExactPlanarCurvedUnsupported` (exact computed
  on planar faces; diagnostics name the unevaluated curved faces)
- no planar faces → `CoarseFallbackCurvedUnsupported`
- any `MeshApprox`/`Unknown`/malformed loops → `UnsupportedGeometry`

A candidate's `CandidateOutcome.capability` is the **min** of source/candidate
eligibility for that pair. No silent fallback: a non-`ExactPlanar` outcome never
yields an `adjacent_exact` edge from the unsupported faces; `includeCoarse=true` may
attach the bbox relationship as context.

## 6. Data flow (three thread hops)

```
[worker]     handler receives { objectId, opts }
   │ EnqueueAction
   ▼
[processor]  QueryCandidatesAsync: RTree neighbors -> score -> sort nearest-first
             -> cap. Returns CandidateQueryResult {seq, sourceNode, scored caps, capped, total}
   │ CMainThreadDispatcher::Dispatch  (caps + face-count cap + extraction budget = the protection)
   ▼
[main]       for source + capped candidates: fetch CRhinoObjects, extract
             ObjectFaceSummary (planar faces: plane + outer/inner loops; classify
             curved/mesh/unknown). EXTRACTION ONLY — no SDK pointers escape.
   │ returns vector<ObjectFaceSummary> (plain data)
   ▼
[worker]     PlanarAdjacencyEngine.Evaluate(source, candidates, tol) -> ExactAdjacencyResult
   │ cache + return
```

## 7. Safety & limits (Finding 3 — over-cap resolved to ONE behavior)

- **Candidate cap** (default 64) — applied AFTER deterministic nearest-first sort.
- **Face-count cap** + **extraction budget** inside the main-thread lambda — the REAL
  stall protection (the dispatch future timeout does NOT preempt a running lambda;
  it only reports caller-side failure as `FailedWithDiagnostics`).
- **Over-cap behavior = SUCCESSFUL PARTIAL RESULT** (Finding 3, chosen): when the
  neighborhood exceeds the cap, return the exact result for the **nearest-first
  capped** candidates with `capped=true`, `candidateCount`, `candidateLimit`. Never a
  silent truncation, never a hard failure. The caller sees exactly what was and
  wasn't evaluated.
- **No watcher routing**; bbox pipeline untouched.

## 8. Cache & invalidation (Finding fuller key, retained)

```
CacheKey = (objectId, graphSequence, tolerance, maxCandidates, engineVersion)
```
v1 invalidation: drop entries on `graphSequence` change. `engineVersion` bumps when
the planar engine math changes. Per-object generation stamps = later optimization.

## 9. API contract (Finding 4 — full response shape; Finding 5 route family)

```
POST /scene/graph/adjacency/exact
  body: { objectId, maxCandidates?, tolerance?, includeCoarse? }
  200 -> {
    objectId, graphSequence, sourceCapability,
    edges:      [ { targetId, relationship:"adjacent_exact", sharedArea } ],
    candidates: [ { id, capability, coarseRelationship? } ],
    capped:          bool,
    candidateCount:  int,     // evaluated
    candidateLimit:  int,     // cap applied
    diagnostics:     [ string ]
  }
```
Overlay only — the `CSceneGraph` snapshot **never** holds `adjacent_exact` edges.
`capability`, `capped`, and `diagnostics` are first-class so implementers cannot
improvise incompatible shapes.

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
- **wall face with a window hole**: overlap inside the hole → NOT counted; overlap on
  solid → counted (hole-aware correctness);
- mixed planar+curved object → `PartialExactPlanarCurvedUnsupported`, planar faces
  still evaluated;
- deterministic candidate ordering (same input → same capped set).

**Live-Rhino integration smoke:**
- modify/delete object → cache invalidates (graphSequence bump);
- neighborhood over cap → `capped=true` partial result, nearest-first;
- curved object → `CoarseFallbackCurvedUnsupported` (never false exact);
- mesh/subd → `UnsupportedGeometry`.

## 12. Deferred to later gates/specs
- Curved engine + kernel choice (Rhino OpenNURBS vs OCCT-in-plugin) — Gate 3b/4b.
- Folding overlay edges into the Python networkx mirror.
- Per-object cache generation stamps; prewarming.
- Scale validation of cap/dispatch under large neighborhoods — Gate 5.
