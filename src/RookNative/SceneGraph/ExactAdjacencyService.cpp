// ExactAdjacencyService.cpp
//
// Rhino-facing exact planar-adjacency orchestrator. Runs from the HTTP worker
// thread. Keeps the precompiled header (Rhino-facing unit) — stdafx.h FIRST.

#include "stdafx.h"   // FIRST — Rhino-facing unit keeps PCH (CRhinoDoc, RhinoApp)
#include "SceneGraph/ExactAdjacencyService.h"
#include "SceneGraph/SceneGraph.h"
#include "SceneGraph/PlanarAdjacencyEngine.h"
#include "Threading/MainThreadDispatcher.h"

#include <cstdio>
#include <vector>
#include <exception>

namespace Rook {

// ── STUB for Task 7 ───────────────────────────────────────────────────────────
// Main-thread Brep face-summary extraction. Task 7 replaces this body with the
// real RhinoCommon extraction (oriented normals, canonicalPlane, loops, capability
// rollup, face-count cap + extraction budget). For now it returns a clearly-marked
// unimplemented result so the service compiles, links, and is structurally complete.
// MUST be called ONLY on the main thread (inside the Dispatch lambda).
static ObjectFaceSummary ExtractObjectFaceSummary(CRhinoDoc& doc, const std::string& objectId) {
    (void)doc;
    ObjectFaceSummary s;
    s.objectId = objectId;
    s.capability = Capability::FailedWithDiagnostics;
    s.diagnostics.push_back("extraction_pending_task7");
    return s;
}

ExactAdjacencyService& ExactAdjacencyService::Instance() {
    static ExactAdjacencyService inst;
    return inst;
}

std::string ExactAdjacencyService::CacheKey(const std::string& objectId, int graphSequence,
                                            double tolerance, int maxCandidates, int engineVersion) {
    char buf[64];
    std::snprintf(buf, sizeof(buf), "|%d|%.9g|%d|%d", graphSequence, tolerance, maxCandidates, engineVersion);
    return objectId + buf;
}

ExactAdjacencyCore ExactAdjacencyService::Compute(const std::string& objectId,
                                                  const CandidateQueryOptions& opts) {
    // 1) candidate query (runs on processor thread; we block here on the worker).
    CandidateQueryResult q = CSceneGraph::Instance().QueryCandidatesAsync(objectId, opts).get();

    ExactAdjacencyCore core;
    core.objectId = objectId;
    core.graphSequence = q.graphSequence;
    core.candidateLimit = opts.maxCandidates;
    core.capped = q.capped;
    core.totalCandidateCount = q.totalCandidateCount;

    if (!q.sourceFound) {
        core.sourceCapability = Capability::FailedWithDiagnostics;
        core.diagnostics.push_back("source_not_found:" + objectId);
        return core;
    }

    // 2) cache: drop ALL entries when graphSequence advances, then look up.
    const std::string key = CacheKey(objectId, q.graphSequence, opts.tolerance,
                                     opts.maxCandidates, kEngineVersion);
    {
        std::lock_guard<std::mutex> lk(m_cacheMutex);
        if (q.graphSequence != m_lastSeenSequence) {
            m_cache.clear();
            m_lastSeenSequence = q.graphSequence;
        }
        auto it = m_cache.find(key);
        if (it != m_cache.end()) return it->second;  // cached CORE (already merged)
    }

    // 3) main-thread face extraction for source + candidates (plain structs only).
    std::vector<std::string> candidateIds;
    candidateIds.reserve(q.candidates.size());
    for (const ScoredCandidate& c : q.candidates) candidateIds.push_back(c.id);

    struct Extracted { ObjectFaceSummary source; std::vector<ObjectFaceSummary> candidates; bool ok; };
    auto fut = CMainThreadDispatcher::Instance().Dispatch(
        [objectId, candidateIds]() -> Extracted {
            Extracted ex; ex.ok = false;
            // Resolve the doc on the main thread, matching CSceneGraph's pattern
            // (TargetDocSerialNumber + FromRuntimeSerialNumber) rather than the
            // raw ActiveDoc accessor.
            unsigned int sn = CRhinoDoc::TargetDocSerialNumber();
            CRhinoDoc* doc = CRhinoDoc::FromRuntimeSerialNumber(sn);
            if (!doc) return ex;
            ex.source = ExtractObjectFaceSummary(*doc, objectId);
            ex.candidates.reserve(candidateIds.size());
            for (const std::string& id : candidateIds)
                ex.candidates.push_back(ExtractObjectFaceSummary(*doc, id));
            ex.ok = true;
            return ex;
        });

    Extracted ex;
    try {
        ex = fut.get();   // worker thread blocks; safe (not main thread)
    } catch (const std::exception& e) {
        core.sourceCapability = Capability::FailedWithDiagnostics;
        core.diagnostics.push_back(std::string("extraction_dispatch_failed:") + e.what());
        return core;
    }
    if (!ex.ok) {
        core.sourceCapability = Capability::FailedWithDiagnostics;
        core.diagnostics.push_back("no_active_doc");
        return core;
    }

    // 4) pure engine evaluation (worker thread; no Rhino, no locks).
    PlanarAdjacencyEngine engine;
    ExactAdjacencyCore evaluated = engine.Evaluate(ex.source, ex.candidates, opts.tolerance);

    // 5) merge service-owned fields the engine left at defaults, then cache + return.
    //    Engine owns: sourceCapability, edges, candidates, candidateCount, diagnostics.
    //    Service owns: objectId, graphSequence, candidateLimit, capped, totalCandidateCount.
    evaluated.objectId = objectId;
    evaluated.graphSequence = q.graphSequence;
    evaluated.candidateLimit = opts.maxCandidates;
    evaluated.capped = q.capped;
    evaluated.totalCandidateCount = q.totalCandidateCount;

    {
        std::lock_guard<std::mutex> lk(m_cacheMutex);
        // re-check sequence (could have advanced while extracting); only cache if current
        if (q.graphSequence == m_lastSeenSequence) {
            m_cache[key] = evaluated;
        }
    }
    return evaluated;
}

} // namespace Rook
