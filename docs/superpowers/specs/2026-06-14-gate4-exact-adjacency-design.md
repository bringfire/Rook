# Gate 4 — Exact Planar Adjacency Service (design spec)

> **Status:** Design approved (with revisions) via brainstorming + Codex review
> round, 2026-06-14. Ready for implementation-plan (writing-plans). First gate that
> touches production C++ in `RookNative`.
> **Parent:** `docs/rook_docs/2026-06-13-spatial-intelligence-foundation.md` (the
> spatial-intelligence foundation; this is Gate 4 of its roadmap). Gates 0-3 proved:
> adjacency = pure-Python **B2** (coplanar + Sutherland-Hodgman polygon overlap) for
> planar; OCCT (`face.common().Area`) for curved; the C++ `CSceneGraph` is a
> background-thread, bbox-only, geometry-light pipeline.

## 1. Purpose & scope

Add **exact planar shared-face adjacency** to Rook as a **lazy, on-demand,
query-time refinement** of the existing scene graph — without disturbing the
continuous bbox pipeline. v1 = planar exact only; curved is designed-for (pluggable
engine) but not implemented, and must produce an **honest flagged result, never a
false exact**.

**In scope (v1):** planar exact adjacency engine; the `ExactAdjacencyService`;
minimal `CSceneGraph` read APIs; one HTTP route; cache; capability reporting; unit
+ smoke tests.

**Out of scope (v1):** curved adjacency engine; kernel choice for curved (Rhino
OpenNURBS vs OCCT-in-plugin); folding exact edges into the Python networkx mirror;
per-object cache generation stamps; prewarming; MCP tool wrapper (route is the
contract; the tool is a thin later add).

## 2. Binding constraints (from review rounds — do not violate)

1. **No Rhino SDK pointers cross threads.** Geometry extraction happens on the main
   thread and yields only plain structs.
2. **The continuous bbox pipeline is untouched.** No face data, cache, or geometry
   extraction in `CSceneGraph`; not on the watcher hot path.
3. **No silent fallback.** Every candidate carries an explicit capability status;
   curved/unsupported geometry is reported as such, never returned as exact.
4. **`m_rtree` / `m_rtreeIdOrder` are processor-thread-owned writer state** — never
   read them from an HTTP worker thread (Revision 1).
5. **Don't widen `ObjectEvent` / `SceneNode`** — face summaries live in the service,
   not the node, until measured evidence says otherwise.

## 3. Architecture & boundary

New sibling module, **not** methods piled onto `CSceneGraph`:
```
src/RookNative/SceneGraph/ExactAdjacencyService.h
src/RookNative/SceneGraph/ExactAdjacencyService.cpp
```

`CSceneGraph` remains the bbox substrate and gains **only** a candidate-query read,
exposed as an **action-queued read that runs on the processor thread** (Revision 1):

```cpp
// Runs on the graph processor thread via EnqueueAction(); safe access to m_rtree.
struct CandidateQueryResult {
    int graphSequence;
    SceneNode sourceNode;              // copy (plain data)
    std::vector<std::string> candidateIds;
    bool sourceFound;
};
std::future<CandidateQueryResult>
CSceneGraph::QueryCandidatesAsync(const std::string& objectId,
                                  const CandidateQueryOptions& opts);
```
Implemented by wrapping the existing private RTree `FindNeighborIds` logic inside an
`EnqueueAction` lambda. The service **never** touches `m_rtree` directly.

The service reuses the existing **`CMainThreadDispatcher`** (the pattern used by
`GeometryHandler.cpp:321`) for geometry extraction on the Rhino main thread.

## 4. Data model (plain structs, owned by the service)

```cpp
enum class FaceKind { Planar, Curved, MeshApprox, Unknown };

struct PlanarFace {
    std::array<double,4> plane;                 // canonical normal (xyz) + offset
    std::vector<std::vector<std::array<double,3>>> loops;  // ordered; [0]=outer
};
struct FaceSummary {
    FaceKind kind = FaceKind::Unknown;
    PlanarFace planar;                           // valid iff kind==Planar
    // curved: reserved for the future surface descriptor (NOT populated in v1)
};

enum class Capability {
    ExactPlanar,                                 // exact result computed
    PartialExactPlanarCurvedUnsupported,         // some faces planar, some curved (Rev 4)
    CoarseFallbackCurvedUnsupported,             // object is curved/non-planar
    UnsupportedGeometry,                         // mesh/subd/malformed loops
    FailedWithDiagnostics
};

struct ExactEdge {
    std::string sourceId, targetId;
    std::string relationship = "adjacent_exact"; // provenance explicit
    double sharedArea = 0.0;
};
struct CandidateOutcome { std::string id; Capability capability; };

struct ExactAdjacencyResult {
    std::string objectId;
    int graphSequence = 0;
    std::vector<ExactEdge> edges;
    std::vector<CandidateOutcome> candidates;    // per-candidate status (no silent gaps)
    Capability sourceCapability = Capability::FailedWithDiagnostics;
};
```

**Pluggable engine** (Revision 4 — curved-ready, not curved-pretend):
```cpp
class IExactAdjacencyEngine {
public:
    virtual ~IExactAdjacencyEngine() = default;
    // Pure function of plain data — no Rhino, no threads. Unit-testable in isolation.
    virtual ExactAdjacencyResult Evaluate(
        const std::string& sourceId, const FaceSummary& source,
        const std::vector<std::pair<std::string,FaceSummary>>& candidates,
        double tolerance) const = 0;
};
class PlanarAdjacencyEngine : public IExactAdjacencyEngine { /* B2: coplanar + SH clip */ };
// CurvedAdjacencyEngine — later, behind this same interface.
```

## 5. Extraction scope & capability mapping (Revision 4)

Extraction (main thread) classifies each face and fills `FaceSummary.kind`:
- **Planar** — `Brep`/`Extrusion` faces whose surface is planar AND whose loops
  project & validate to non-degenerate ordered polygons → `PlanarFace`.
- **Curved** — planar-surface test fails (cylinder/NURBS/etc.) → `kind=Curved`.
- **MeshApprox / Unknown** — `Mesh`, `SubD`, or malformed/degenerate loops →
  `kind=MeshApprox`/`Unknown`.

Object-level capability:
- all faces planar & valid → `ExactPlanar` eligible
- mixed planar + curved → `PartialExactPlanarCurvedUnsupported` (exact computed on
  the planar faces; agent is told curved faces were NOT evaluated)
- no planar faces / curved object → `CoarseFallbackCurvedUnsupported`
- mesh/subd/malformed → `UnsupportedGeometry`

In every non-exact case the response MAY include the existing bbox/coarse
relationship as *context* (when `includeCoarse=true`), clearly distinct from
`adjacent_exact`.

## 6. Data flow (three thread hops, each minimal)

```
[worker thread]  handler receives { objectId, opts }
      │  EnqueueAction (Revision 1)
      ▼
[processor thread]  QueryCandidates: RTree neighborhood (capped), copy sourceNode,
                    read graphSequence  ->  CandidateQueryResult (plain data)
      │  CMainThreadDispatcher::Dispatch  (Revision 2: caps are the protection)
      ▼
[main thread]  for source + candidates: fetch CRhinoObjects, extract FaceSummary
               (planar plane+loops). EXTRACTION ONLY — no SDK pointers escape.
               Bounded by candidate cap + face-count cap + extraction budget.
      │  returns vector<(id,FaceSummary)> (plain data)
      ▼
[worker thread]  PlanarAdjacencyEngine.Evaluate(...) on plain structs (B2:
                 coplanar grouping + Sutherland-Hodgman overlap) -> ExactAdjacencyResult
      │
      ▼  cache + return
```

**Threading safety:** the only Rhino-geometry access is inside the
`CMainThreadDispatcher` lambda; RTree access is inside the `EnqueueAction` lambda;
the predicate runs on plain data on the worker thread.

## 7. Safety & limits (Revision 2 — precise)

- **Candidate cap** (default ~64, configurable) — bounds the neighborhood.
- **Face-count cap** + **extraction budget** *inside* the main-thread lambda — the
  REAL protection against stalling Rhino, because once the dispatched lambda starts,
  the caller-side future timeout does **not** preempt it.
- **Dispatch timeout** — for caller-side failure *reporting* only
  (`FailedWithDiagnostics`), NOT preemption.
- Over-cap neighborhoods: return `FailedWithDiagnostics` (or a truncated result with
  an explicit "capped" flag) — never silently partial.

## 8. Cache & invalidation (Revision 3 — fuller key)

```
CacheKey = (objectId, graphSequence, tolerance, maxCandidates /*query profile*/, engineVersion)
```
Without `tolerance` / `maxCandidates` / `engineVersion` a 64-candidate response
could wrongly satisfy a later 256-candidate request. **v1 invalidation:** drop cache
entries when `graphSequence` changes (coarse). Per-object generation stamps are a
later optimization.

## 9. API contract (Revision 5 — under the scene-graph family)

```
POST /scene/graph/adjacency/exact
  body: { objectId, maxCandidates?, tolerance?, includeCoarse? }
  ->   { objectId, graphSequence, sourceCapability,
         edges:[{ targetId, relationship:"adjacent_exact", sharedArea }],
         candidates:[{ id, capability }] }
```
Overlay only — the `CSceneGraph` snapshot **never** holds `adjacent_exact` edges.
Python/MCP wrapper and any networkx-mirror merge are later/out-of-scope.

## 10. Build / project-file impact (Revision 6)

`ExactAdjacencyService.cpp` is a **new compiled translation unit** → it must be added
to **`src/RookNative/RookNative.vcxproj`** (and `.filters`). Our standing rule is to
**not edit `.vcxproj` unless the task explicitly authorizes it** — so the
implementation plan must call this out and obtain explicit authorization for the
`.vcxproj` edit as a discrete step. Build via `scripts/build-native.bat` (per
project convention).

## 11. Testing

**Engine unit tests (no Rhino — plain `FaceSummary` structs; reuse Gate-1/2 fixtures):**
- adjacent boxes → exact edge; partial overlap (column-on-slab) → exact edge;
  bbox-near-but-not-touching (150mm gap) → no edge; corner-only → no edge;
  tolerance boundary behavior; mixed planar+curved input → `PartialExact...`.

**Live-Rhino integration smoke:**
- modify an object → cache invalidates (graphSequence bump); delete → invalidates;
  neighborhood over cap → bounded/flagged; curved object →
  `CoarseFallbackCurvedUnsupported` (never a false exact); mesh/subd →
  `UnsupportedGeometry`.

## 12. Open items deferred to their own gates/specs
- Curved engine + kernel choice (Rhino OpenNURBS vs OCCT-in-plugin) — Gate 3b/4b.
- Folding overlay edges into the Python networkx mirror for graph algorithms.
- Per-object cache generation stamps; prewarming small scenes.
- Scale validation of the dispatch/cap behavior under large neighborhoods — Gate 5.
