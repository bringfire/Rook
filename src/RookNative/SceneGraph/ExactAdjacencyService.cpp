// ExactAdjacencyService.cpp
//
// Rhino-facing exact planar-adjacency orchestrator. Runs from the HTTP worker
// thread. Keeps the precompiled header (Rhino-facing unit) — stdafx.h FIRST.

#include "stdafx.h"   // FIRST — Rhino-facing unit keeps PCH (CRhinoDoc, RhinoApp)
#include "SceneGraph/ExactAdjacencyService.h"
#include "SceneGraph/SceneGraph.h"
#include "SceneGraph/PlanarAdjacencyEngine.h"
#include "Threading/MainThreadDispatcher.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <memory>
#include <string>
#include <vector>
#include <exception>

namespace Rook {

// ── Task 7: main-thread Brep face-summary extraction ──────────────────────────
// Real RhinoCommon/openNURBS extraction. MUST run ONLY on the main thread (it is
// invoked inside CMainThreadDispatcher::Dispatch). Returns ONLY plain DTOs — no
// Rhino SDK pointer ever escapes this function.

// File-local constants (caps / stall guard). See task spec — bounds, not tuned.
static constexpr int    kMaxFacesPerObject     = 4000;     // face-count cap
static constexpr int    kExtractionPointBudget = 2000000;  // total loop-points per object
static constexpr int    kCurvedEdgeSamples     = 8;        // interior samples on a curved edge
static constexpr double kPlaneTol              = ON_ZERO_TOLERANCE;  // IsPlanar tolerance
static constexpr double kLinearTol             = ON_ZERO_TOLERANCE;  // IsLinear tolerance

// Copied (with cite) from AnalysisHandler.cpp::ExtractBrep — that copy is file-static
// and therefore not linkable; replicate it here. Returns an ON_Brep* for Brep OR
// Extrusion (via BrepForm), setting bMustDelete for the Extrusion case so the caller
// can guard the lifetime with a unique_ptr.
static const ON_Brep* ExtractBrep(const ON_Geometry* geom, bool& bMustDelete) {
    bMustDelete = false;
    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return brep;
    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom)) {
        ON_Brep* brep = ext->BrepForm();
        if (brep) {
            bMustDelete = true;
            return brep;
        }
    }
    return nullptr;
}

// Sign-fold a plane {nx,ny,nz,d} so the FIRST nonzero normal component (scan order
// nx, ny, nz) is positive. MUST byte-for-byte match the engine/test fold so that
// two opposing coplanar faces collapse to the SAME canonicalPlane.
static std::array<double, 4> foldPlane(double nx, double ny, double nz, double d) {
    double lead = 0.0;
    if (std::fabs(nx) > 1e-12)      lead = nx;
    else if (std::fabs(ny) > 1e-12) lead = ny;
    else if (std::fabs(nz) > 1e-12) lead = nz;
    double s = (lead < 0.0) ? -1.0 : 1.0;
    return { nx * s, ny * s, nz * s, d * s };
}

static ObjectFaceSummary ExtractObjectFaceSummary(CRhinoDoc& doc, const std::string& objectId) {
    ObjectFaceSummary s;
    s.objectId = objectId;

    // 1) parse uuid (inverse of Rook::UuidToString -> ON_UuidToString); lookup object.
    //    ON_UuidFromString returns ON_nil_uuid on parse failure.
    ON_UUID uuid = ON_UuidFromString(objectId.c_str());
    if (ON_UuidIsNil(uuid)) {
        s.capability = Capability::FailedWithDiagnostics;
        s.diagnostics.push_back("bad_object_id");
        return s;
    }
    const CRhinoObject* obj = doc.LookupObject(uuid);
    if (!obj) {
        s.capability = Capability::FailedWithDiagnostics;
        s.diagnostics.push_back("object_not_found");
        return s;
    }
    const ON_Geometry* geom = obj->Geometry();
    if (!geom) {
        s.capability = Capability::FailedWithDiagnostics;
        s.diagnostics.push_back("no_geometry");
        return s;
    }

    // 2) Mesh / SubD -> UnsupportedGeometry (the exact engine does not handle them).
    if (ON_Mesh::Cast(geom) != nullptr) {
        s.capability = Capability::UnsupportedGeometry;
        s.diagnostics.push_back("mesh");
        return s;
    }
    if (ON_SubD::Cast(geom) != nullptr) {
        s.capability = Capability::UnsupportedGeometry;
        s.diagnostics.push_back("subd");
        return s;
    }

    // 3) Brep (or Extrusion via BrepForm). Non-surface geometry (curve/point/etc.)
    //    lands here as no_brep -> CoarseFallbackExactUnsupported.
    bool bMustDelete = false;
    const ON_Brep* brep = ExtractBrep(geom, bMustDelete);
    std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
    if (!brep) {
        s.capability = Capability::CoarseFallbackExactUnsupported;
        s.diagnostics.push_back("no_brep");
        return s;
    }

    // 4) Orientation is only trustworthy on closed solids (outward normal meaningful).
    const bool orientationReliable = brep->IsSolid();

    // 5) face-count cap.
    const int faceCount = brep->m_F.Count();
    if (faceCount > kMaxFacesPerObject) {
        s.capability = Capability::FailedWithDiagnostics;
        s.diagnostics.push_back("face_cap_exceeded:" + std::to_string(faceCount));
        return s;
    }

    // Per-object extraction point budget (stall guard).
    long long pointBudget = 0;

    // Helper: extract one loop's ordered 3D world polygon. Returns false if the loop
    // is not a real area boundary (degenerate / non-outer-inner type / <3 pts).
    auto extractLoop = [&](const ON_BrepLoop* loop,
                           std::vector<std::array<double, 3>>& outPts,
                           bool& budgetTripped) -> bool {
        outPts.clear();
        if (!loop) return false;
        for (int lti = 0; lti < loop->m_ti.Count(); ++lti) {
            const ON_BrepTrim& trim = brep->m_T[loop->m_ti[lti]];
            const ON_BrepEdge* edge = trim.Edge();   // null for singular/seam-point trims
            if (!edge) continue;
            const ON_Curve* ec = edge->EdgeCurveOf();
            if (!ec) continue;

            // Start vertex of this trim, honoring traversal direction relative to loop.
            ON_3dPoint pStart = trim.m_bRev3d ? ec->PointAtEnd() : ec->PointAtStart();
            outPts.push_back({ pStart.x, pStart.y, pStart.z });
            if (++pointBudget > kExtractionPointBudget) { budgetTripped = true; return false; }

            // Curved edge on a planar face: sample interior points so the polygon
            // approximates the arc (documented v1 approximation; pure-line faces exact).
            if (!ec->IsLinear(kLinearTol)) {
                ON_Interval dom = ec->Domain();
                for (int k = 1; k <= kCurvedEdgeSamples; ++k) {
                    double f = static_cast<double>(k) / static_cast<double>(kCurvedEdgeSamples + 1);
                    // Walk the param in loop-traversal direction.
                    double t = trim.m_bRev3d ? dom.ParameterAt(1.0 - f)
                                             : dom.ParameterAt(f);
                    ON_3dPoint ps = ec->PointAt(t);
                    outPts.push_back({ ps.x, ps.y, ps.z });
                    if (++pointBudget > kExtractionPointBudget) { budgetTripped = true; return false; }
                }
            }
        }
        return outPts.size() >= 3;
    };

    int countEligible = 0;     // faces with kind == Planar
    int countIneligible = 0;   // faces marked Curved / Unknown
    bool budgetTripped = false;

    for (int fi = 0; fi < faceCount && !budgetTripped; ++fi) {
        const ON_BrepFace& face = brep->m_F[fi];
        FaceSummary fs;

        const ON_Surface* srf = face.SurfaceOf();
        ON_Plane plane;
        const bool isPlanar = (srf != nullptr) && srf->IsPlanar(&plane, kPlaneTol);

        if (!isPlanar) {
            fs.kind = FaceKind::Curved;
            s.faces.push_back(fs);
            s.diagnostics.push_back("curved:face" + std::to_string(fi));
            ++countIneligible;
            continue;
        }
        if (!orientationReliable) {
            fs.kind = FaceKind::Unknown;
            s.faces.push_back(fs);
            s.diagnostics.push_back("unoriented:face" + std::to_string(fi));
            ++countIneligible;
            continue;
        }

        // Oriented outward normal: surface normal at the domain midpoint, flipped by
        // the face's m_bRev, then unitized.
        ON_Interval du = srf->Domain(0);
        ON_Interval dv = srf->Domain(1);
        ON_3dVector n0 = srf->NormalAt(du.Mid(), dv.Mid());
        if (face.m_bRev) n0 = -n0;
        if (!n0.Unitize()) {
            fs.kind = FaceKind::Unknown;
            s.faces.push_back(fs);
            s.diagnostics.push_back("unoriented:face" + std::to_string(fi));
            ++countIneligible;
            continue;
        }

        // Loops: outer at loops[0], holes after. Stray non-boundary loops are ignored;
        // a missing/degenerate outer loop makes the whole face malformed.
        std::vector<std::array<double, 3>> outerPts;
        std::vector<std::vector<std::array<double, 3>>> holeLoops;
        bool haveOuter = false;
        bool malformed = false;

        const int loopCount = face.LoopCount();
        for (int li = 0; li < loopCount && !budgetTripped; ++li) {
            const ON_BrepLoop* loop = face.Loop(li);
            if (!loop) continue;
            if (loop->m_type == ON_BrepLoop::outer) {
                std::vector<std::array<double, 3>> pts;
                if (!extractLoop(loop, pts, budgetTripped)) {
                    if (!budgetTripped) malformed = true;  // outer loop must be valid
                } else if (!haveOuter) {
                    outerPts = std::move(pts);
                    haveOuter = true;
                }
                // (extra outer loops are pathological; first wins)
            } else if (loop->m_type == ON_BrepLoop::inner) {
                std::vector<std::array<double, 3>> pts;
                if (extractLoop(loop, pts, budgetTripped))
                    holeLoops.push_back(std::move(pts));
                // a degenerate hole loop is simply dropped (not fatal)
            }
            // slit / crvonsrf / ptonsrf -> not a real area boundary; ignore.
        }

        if (budgetTripped) break;
        if (malformed || !haveOuter) {
            fs.kind = FaceKind::Unknown;
            s.faces.push_back(fs);
            s.diagnostics.push_back("malformed_loop:face" + std::to_string(fi));
            ++countIneligible;
            continue;
        }

        // Build the eligible planar face. canonicalPlane uses an ACTUAL outer-loop
        // point as P0 (numerically consistent with the loop coords the engine sees),
        // d = n0 . P0, then sign-fold.
        const std::array<double, 3>& p0 = outerPts.front();
        double d = n0.x * p0[0] + n0.y * p0[1] + n0.z * p0[2];

        fs.kind = FaceKind::Planar;
        fs.planar.outwardNormal = { n0.x, n0.y, n0.z };
        fs.planar.canonicalPlane = foldPlane(n0.x, n0.y, n0.z, d);
        fs.planar.loops.clear();
        fs.planar.loops.push_back(std::move(outerPts));
        for (auto& h : holeLoops) fs.planar.loops.push_back(std::move(h));

        s.faces.push_back(std::move(fs));
        ++countEligible;
    }

    if (budgetTripped) {
        s.capability = Capability::FailedWithDiagnostics;
        s.diagnostics.push_back("extraction_budget_exceeded");
        return s;
    }

    // 7) capability rollup (precedence, spec §5).
    if (countEligible == 0) {
        s.capability = Capability::CoarseFallbackExactUnsupported;
    } else if (countIneligible > 0) {
        s.capability = Capability::PartialExactUnsupported;
    } else {
        s.capability = Capability::ExactPlanar;
    }
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
