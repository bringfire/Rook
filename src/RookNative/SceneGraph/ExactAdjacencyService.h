// ExactAdjacencyService.h
//
// Rhino-facing orchestrator for exact (planar) adjacency. Ties together:
//   candidate query (CSceneGraph, processor thread)
//   -> result cache
//   -> main-thread Brep face-summary extraction (Task 7)
//   -> pure PlanarAdjacencyEngine (Task 4, Rhino-free)
//   -> cache store
//
// Lean header: NO Rhino SDK includes, NO engine include. Only the plain-data
// DTOs are referenced here so callers and the engine can share this surface
// without pulling Rhino.

#pragma once
#include "SceneGraph/ExactAdjacencyTypes.h"
#include <string>
#include <unordered_map>
#include <mutex>

namespace Rook {

// Lazy, on-demand exact planar-adjacency orchestration with a result cache.
// Singleton (holds the cache across calls), mirroring CSceneGraph::Instance().
class ExactAdjacencyService {
public:
    static ExactAdjacencyService& Instance();

    // Worker-thread entry point. Orchestrates: candidate query (processor thread)
    // -> cache lookup -> main-thread face extraction -> pure engine -> cache store.
    // Returns the exact CORE only (no coarse decoration — that is the handler's job).
    ExactAdjacencyCore Compute(const std::string& objectId, const CandidateQueryOptions& opts);

private:
    ExactAdjacencyService() = default;

    std::mutex m_cacheMutex;
    std::unordered_map<std::string, ExactAdjacencyCore> m_cache;  // key = CacheKey()
    int m_lastSeenSequence = -1;

    static std::string CacheKey(const std::string& objectId, int graphSequence,
                                double tolerance, int maxCandidates, int engineVersion);
};

} // namespace Rook
