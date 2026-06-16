// ExactAdjacencyService.h
//
// Rhino-facing orchestrator for exact adjacency. Ties together:
//   candidate query (CSceneGraph, processor thread)
//   -> result cache
//   -> main-thread ON_Brep deep-copy extraction (-> Rook::occt::ObjectBrepPayload)
//   -> pure Rook::occt::OcctAdjacencyEngine (OCCT shared-face area, Rhino-free)
//   -> cache store
//
// Lean header: NO Rhino SDK includes, NO OCCT headers. Only the OCCT-header-free
// plain-data DTOs are referenced here (query types from ExactAdjacencyTypes.h in
// bare `Rook`; engine/result contract from OcctAdjacencyTypes.h in `Rook::occt`) so
// callers and the engine share this surface without pulling Rhino or OCCT.

#pragma once
#include "SceneGraph/ExactAdjacencyTypes.h"   // broad-phase query types (bare Rook)
#include "SceneGraph/OcctAdjacencyTypes.h"    // OCCT engine/result contract (Rook::occt)
#include <string>
#include <unordered_map>
#include <mutex>

namespace Rook {

// Lazy, on-demand exact planar-adjacency orchestration with a result cache.
// Singleton (holds the cache across calls), mirroring CSceneGraph::Instance().
//
// TEARDOWN CONTRACT (do not break): this Meyers singleton is constructed on the
// first Compute() call — i.e. AFTER CMainThreadDispatcher::Instance() and
// CSceneGraph::Instance() — so it is destroyed FIRST during static teardown. Its
// destructor MUST stay trivial: it must never call Dispatch()/EnqueueAction() or
// otherwise touch the dispatcher or scene graph (which may already be torn down).
// In-flight Compute() calls during plugin unload are safe ONLY because Dispatch()
// and EnqueueAction() are self-guarding (they resolve their futures with an
// exception / drained action once Stop() has run); Compute() catches that and
// returns a "dispatcher_busy_retry"/"failed_with_diagnostics" core. There is
// intentionally NO Stop() hook here — keep it that way unless you add explicit
// shutdown ordering in OnUnloadPlugIn.
class ExactAdjacencyService {
public:
    static ExactAdjacencyService& Instance();

    // Worker-thread entry point. Orchestrates: candidate query (processor thread)
    // -> cache lookup -> main-thread ON_Brep extraction -> pure OCCT engine -> cache store.
    // Returns the exact CORE only (no coarse decoration — that is the handler's job).
    // `fuzzMm` is the OCCT coincidence fuzzy in MILLIMETERS (converted to model units per
    // call). It is DISTINCT from opts.tolerance (broad-phase, model units) — see plan issue-5.
    occt::ExactAdjacencyCore Compute(const std::string& objectId,
                                     const CandidateQueryOptions& opts,
                                     double fuzzMm = occt::kDefaultFuzzMm);

private:
    ExactAdjacencyService() = default;

    std::mutex m_cacheMutex;
    std::unordered_map<std::string, occt::ExactAdjacencyCore> m_cache;  // key = CacheKey()
    int m_lastSeenSequence = -1;

    static std::string CacheKey(const std::string& objectId, int graphSequence,
                                double tolerance, double fuzzMm, int maxCandidates, int engineVersion);
};

} // namespace Rook
