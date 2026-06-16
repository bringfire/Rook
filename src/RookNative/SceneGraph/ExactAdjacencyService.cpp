// ExactAdjacencyService.cpp
//
// Rhino-facing exact-adjacency orchestrator. Runs from the HTTP worker thread.
// Keeps the precompiled header (Rhino-facing unit) — stdafx.h FIRST.
//
// Task 8: the engine is now the OCCT shared-face-area engine (Rook::occt). Extraction
// produces a move-only Rook::occt::ObjectBrepPayload (owned ON_Brep deep-copy + unit
// scale + capability); the pure engine computes exact adjacency over arbitrary Breps
// (planar + curved). No Rhino SDK pointer ever crosses the thread boundary.

#include "stdafx.h"   // FIRST — Rhino-facing unit keeps PCH (CRhinoDoc, RhinoApp)
#include "SceneGraph/ExactAdjacencyService.h"
#include "SceneGraph/SceneGraph.h"
#include "SceneGraph/OcctAdjacencyEngine.h"   // Rook::occt::OcctAdjacencyEngine (OCCT-header-free pimpl)
#include "Threading/MainThreadDispatcher.h"

#include <cstdio>
#include <memory>
#include <string>
#include <vector>
#include <exception>

namespace Rook {

namespace ro = ::Rook::occt;   // the OCCT exact-adjacency contract (ODR-isolated; see OcctAdjacencyTypes.h)

// File-local face-count cap (bound, not tuned) — matches the legacy extraction guard.
static constexpr int kMaxFacesPerObject = 4000;

// Copied (with cite) from AnalysisHandler.cpp::ExtractBrep — that copy is file-static and
// not linkable; replicate it. Returns an ON_Brep* for Brep OR Extrusion (via BrepForm),
// setting bMustDelete for the Extrusion case so the caller owns/guards the returned pointer.
static const ON_Brep* ExtractBrep(const ON_Geometry* geom, bool& bMustDelete) {
    bMustDelete = false;
    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return brep;
    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom)) {
        ON_Brep* brep = ext->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }
    return nullptr;
}

// Lowercase doc length-unit name for the wire `lengthUnit` field (e.g. "inches").
static std::string LengthUnitName(ON::LengthUnitSystem u) {
    switch (u) {
        case ON::LengthUnitSystem::Millimeters: return "millimeters";
        case ON::LengthUnitSystem::Centimeters: return "centimeters";
        case ON::LengthUnitSystem::Meters:      return "meters";
        case ON::LengthUnitSystem::Kilometers:  return "kilometers";
        case ON::LengthUnitSystem::Inches:      return "inches";
        case ON::LengthUnitSystem::Feet:        return "feet";
        case ON::LengthUnitSystem::Yards:       return "yards";
        case ON::LengthUnitSystem::Miles:       return "miles";
        case ON::LengthUnitSystem::Microinches: return "microinches";
        case ON::LengthUnitSystem::Mils:        return "mils";
        case ON::LengthUnitSystem::Microns:     return "microns";
        case ON::LengthUnitSystem::Nanometers:  return "nanometers";
        case ON::LengthUnitSystem::Angstroms:   return "angstroms";
        case ON::LengthUnitSystem::Decimeters:  return "decimeters";
        default:                                return "unknown";
    }
}

// ── Main-thread extraction of ONE object into a move-only ObjectBrepPayload. ──────────
// MUST run ONLY on the main thread (invoked inside CMainThreadDispatcher::Dispatch).
// Returns plain data + an owned, immutable ON_Brep deep-copy — no Rhino SDK pointer escapes.
static ro::ObjectBrepPayload ExtractObjectBrepPayload(CRhinoDoc& doc, const std::string& objectId) {
    ro::ObjectBrepPayload p;
    p.objectId = objectId;

    // Doc unit scale (model units -> mm). Pinned API (matches SceneGraph.cpp:175 /
    // the OcctAdjacencyValidateHandler extraction).
    const ON_3dmUnitsAndTolerances& ut = doc.Properties().ModelUnitsAndTolerances();
    p.modelUnitsToMillimeters =
        ON::UnitScale(ut.m_unit_system, ON::LengthUnitSystem::Millimeters);

    ON_UUID uuid = ON_UuidFromString(objectId.c_str());
    if (ON_UuidIsNil(uuid)) {
        p.capability = ro::Capability::FailedWithDiagnostics;
        p.diagnostics.push_back("bad_object_id");
        return p;
    }
    const CRhinoObject* obj = doc.LookupObject(uuid);
    if (!obj) {
        p.capability = ro::Capability::FailedWithDiagnostics;
        p.diagnostics.push_back("object_not_found");
        return p;
    }
    const ON_Geometry* geom = obj->Geometry();
    if (!geom) {
        p.capability = ro::Capability::FailedWithDiagnostics;
        p.diagnostics.push_back("no_geometry");
        return p;
    }
    if (ON_Mesh::Cast(geom) != nullptr) {
        p.capability = ro::Capability::UnsupportedGeometry;
        p.diagnostics.push_back("mesh");
        return p;
    }
    if (ON_SubD::Cast(geom) != nullptr) {
        p.capability = ro::Capability::UnsupportedGeometry;
        p.diagnostics.push_back("subd");
        return p;
    }

    bool bMustDelete = false;
    const ON_Brep* brep = ExtractBrep(geom, bMustDelete);
    if (!brep) {
        // Non-surface geometry (curve / point / etc.) — no analytic exact path.
        p.capability = ro::Capability::UnsupportedGeometry;
        p.diagnostics.push_back("no_brep");
        return p;
    }
    // Own an IMMUTABLE copy. Extrusion's BrepForm() already returns an owned ON_Brep* —
    // wrap it directly; a doc Brep must be deep-copied (don't alias the live document).
    std::unique_ptr<const ON_Brep> owned(bMustDelete ? brep : new ON_Brep(*brep));

    const int faceCount = owned->m_F.Count();
    if (faceCount > kMaxFacesPerObject) {
        p.capability = ro::Capability::FailedWithDiagnostics;
        p.diagnostics.push_back("face_cap_exceeded:" + std::to_string(faceCount));
        return p;   // owned freed here; brep stays null
    }

    p.brep = std::move(owned);
    p.capability = ro::Capability::ExactBrep;   // provisional; engine refines on conversion
    return p;
}

ExactAdjacencyService& ExactAdjacencyService::Instance() {
    static ExactAdjacencyService inst;
    return inst;
}

std::string ExactAdjacencyService::CacheKey(const std::string& objectId, int graphSequence,
                                            double tolerance, double fuzzMm,
                                            int maxCandidates, int engineVersion) {
    char buf[96];
    std::snprintf(buf, sizeof(buf), "|%d|%.9g|%.9g|%d|%d",
                  graphSequence, tolerance, fuzzMm, maxCandidates, engineVersion);
    return objectId + buf;
}

occt::ExactAdjacencyCore ExactAdjacencyService::Compute(const std::string& objectId,
                                                        const CandidateQueryOptions& opts,
                                                        double fuzzMm) {
    // 1) candidate query (runs on processor thread; we block here on the worker).
    CandidateQueryResult q = CSceneGraph::Instance().QueryCandidatesAsync(objectId, opts).get();

    occt::ExactAdjacencyCore core;
    core.objectId = objectId;
    core.graphSequence = q.graphSequence;
    core.candidateLimit = opts.maxCandidates;
    core.capped = q.capped;
    core.totalCandidateCount = q.totalCandidateCount;

    if (!q.sourceFound) {
        core.sourceCapability = ro::Capability::FailedWithDiagnostics;
        core.diagnostics.push_back("source_not_found:" + objectId);
        return core;
    }

    // 2) cache: drop ALL entries when graphSequence advances, then look up.
    //    Key includes fuzzMm (a different fuzzy => different edges) AND the broad-phase
    //    tolerance (opts.tolerance), both distinct knobs.
    const std::string key = CacheKey(objectId, q.graphSequence, opts.tolerance, fuzzMm,
                                     opts.maxCandidates, ro::kEngineVersion);
    {
        std::lock_guard<std::mutex> lk(m_cacheMutex);
        if (q.graphSequence != m_lastSeenSequence) {
            m_cache.clear();
            m_lastSeenSequence = q.graphSequence;
        }
        auto it = m_cache.find(key);
        if (it != m_cache.end()) return it->second;  // cached CORE (already merged)
    }

    // 3) main-thread extraction for source + candidates (move-only payloads + unit name).
    std::vector<std::string> candidateIds;
    candidateIds.reserve(q.candidates.size());
    for (const ScoredCandidate& c : q.candidates) candidateIds.push_back(c.id);

    struct Extracted {
        ro::ObjectBrepPayload source;
        std::vector<ro::ObjectBrepPayload> candidates;
        std::string lengthUnit;
        bool ok = false;
    };
    auto fut = CMainThreadDispatcher::Instance().Dispatch(
        [objectId, candidateIds]() -> Extracted {
            Extracted ex;
            unsigned int sn = CRhinoDoc::TargetDocSerialNumber();
            CRhinoDoc* doc = CRhinoDoc::FromRuntimeSerialNumber(sn);
            if (!doc) return ex;   // ok stays false
            ex.lengthUnit = LengthUnitName(
                doc->Properties().ModelUnitsAndTolerances().m_unit_system.UnitSystem());
            ex.source = ExtractObjectBrepPayload(*doc, objectId);
            ex.candidates.reserve(candidateIds.size());
            for (const std::string& id : candidateIds)
                ex.candidates.push_back(ExtractObjectBrepPayload(*doc, id));
            ex.ok = true;
            return ex;
        });

    Extracted ex;
    try {
        ex = fut.get();   // worker thread blocks (safe — not the main thread); move out.
    } catch (const std::exception& e) {
        core.sourceCapability = ro::Capability::FailedWithDiagnostics;
        // Distinguish the transient "Rhino mid-command / modal loop" case (the dispatcher
        // cancels Normal-policy tasks while a command is active) from a real failure, so
        // the agent/Python layer RETRIES instead of treating geometry as unsupported.
        const std::string what = e.what();
        const bool transient = (what.find("busy") != std::string::npos) ||
                               (what.find("not running") != std::string::npos);
        core.diagnostics.push_back(
            std::string(transient ? "dispatcher_busy_retry:" : "extraction_dispatch_failed:") + what);
        return core;
    }
    if (!ex.ok) {
        core.sourceCapability = ro::Capability::FailedWithDiagnostics;
        core.diagnostics.push_back("no_active_doc");
        return core;
    }

    // 4) tolerance: fuzzMm (mm) -> model units (plan issue-5). Distinct from opts.tolerance
    //    (broad-phase). Use the SOURCE object's unit scale.
    const double unitsToMm = ex.source.modelUnitsToMillimeters > 0.0
                                 ? ex.source.modelUnitsToMillimeters : 1.0;
    const double tolModelUnits = fuzzMm / unitsToMm;

    // 5) pure OCCT engine (worker thread; OCCT serialized on the dedicated OCCT thread
    //    inside Evaluate). Move the payloads in; they are never copied or cached.
    occt::ExactAdjacencyCore evaluated =
        ro::OcctAdjacencyEngine().Evaluate(ex.source, ex.candidates, tolModelUnits);

    // 6) merge service-owned fields + units, then cache + return.
    //    Engine owns: sourceCapability, edges, candidates, diagnostics.
    //    Service owns: objectId, graphSequence, candidateLimit, capped, totalCandidateCount,
    //    candidateCount, lengthUnit, areaUnit.
    evaluated.objectId = objectId;
    evaluated.graphSequence = q.graphSequence;
    evaluated.candidateLimit = opts.maxCandidates;
    evaluated.capped = q.capped;
    evaluated.totalCandidateCount = q.totalCandidateCount;
    evaluated.candidateCount = static_cast<int>(evaluated.candidates.size());
    evaluated.lengthUnit = ex.lengthUnit.empty() ? "unknown" : ex.lengthUnit;
    evaluated.areaUnit = evaluated.lengthUnit + "^2";

    {
        std::lock_guard<std::mutex> lk(m_cacheMutex);
        // re-check sequence (could have advanced while extracting); only cache if current.
        if (q.graphSequence == m_lastSeenSequence) {
            m_cache[key] = evaluated;
        }
    }
    return evaluated;
}

} // namespace Rook
