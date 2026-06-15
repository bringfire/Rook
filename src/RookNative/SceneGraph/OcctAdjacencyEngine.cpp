// OcctAdjacencyEngine.cpp
//
// Task 6 (Phase 1, ADDITIVE): the production OCCT exact-adjacency engine.
//
// OCCT-ONLY translation unit, same build shape as OnBrepToOcct.cpp / OcctProbe.cpp:
//   - NO stdafx.h (NotUsing PCH in the vcxproj).
//   - Per-file OCCT include path (C:\...\OCCT\build-rook\inc) + /bigobj.
//   - The public header (OcctAdjacencyEngine.h) stays OCCT-header-free; only this
//     TU pulls OCCT. The converter accessor (OnBrepToOcct_internal.h) and the
//     primitive declaration (OcctAdjacencyEngine_internal.h) are OCCT-aware and
//     included ONLY here (and by the OCCT-only test).
//
// CONCURRENCY (v1): the whole Evaluate body serializes under a static std::mutex,
// matching the OCCT mutex policy used by the dev routes. OCCT global state +
// single-UI-thread Rhino marshalling make this the conservative correct choice;
// finer-grained parallelism is a later optimization, not a Task-6 concern.
//
// CRASH/UNWIND CONTRACT: an OCCT fault inside this TU surfaces as a
// Standard_Failure synthesized by OCCT's OSD::SetSignal SEH translator. Under the
// default /EHsc model that SEH-translated throw does NOT reliably run C++
// destructors during unwind, so the lock_guard below could be skipped and leave
// s_engineMutex permanently locked — the next pooled httplib worker then deadlocks
// (EDEADLK: "resource deadlock would occur") trying to re-lock the held mutex.
// This TU is therefore compiled with /EHa (Async exceptions; set per-file in
// RookNative.vcxproj) so SEH-translated throws unwind the stack and run the
// lock_guard destructor — releasing the mutex on every fault path. Do NOT drop
// the /EHa flag.
//
// METHOD:
//   - Convert source + each candidate ON_Brep to OCCT faces ONCE (proven converter).
//   - Capability per object derives from the converter's failed-face set.
//   - v1: NO broad-phase prefilter. The earlier OCCT bbox prefilter
//     (BRepBndLib::Add) was the recurring fault origin (access violation; it can
//     also trigger OCCT triangulation/parallelism). At Spike-B scale the narrow
//     phase alone is fast enough, and it is the ONLY phase with its own crash
//     guard. Every (source-face, candidate-face) pair goes straight to the
//     narrow phase. Reinstate an openNURBS-side bbox prefilter later if
//     Spike-B-scale perf demands it.
//   - Narrow phase: SharedFaceArea = area of BRepAlgoAPI_Common(face_a, face_b)
//     under a fuzzy value. Coincident (mated) faces -> the shared planar/curved
//     region survives Common with nonzero surface area; non-touching faces -> 0.
//   - An edge is emitted only if the summed shared area exceeds the numeric noise
//     floor kAreaTol. Face-pair contributions above kAreaTol are recorded
//     individually (mapped slot -> ON_Brep face index).

#include "SceneGraph/OcctAdjacencyEngine.h"
#include "SceneGraph/OcctAdjacencyEngine_internal.h"
#include "SceneGraph/OnBrepToOcct.h"
#include "SceneGraph/OnBrepToOcct_internal.h"

// ── openNURBS (only ON_Brep is touched, through the converter). Declared import
//    for the same LNK2005 reason documented in OnBrepToOcct.cpp. ──
#ifndef NOMINMAX
#define NOMINMAX 1
#endif
#ifndef OPENNURBS_IMPORTS
#define OPENNURBS_IMPORTS
#endif
#include "opennurbs.h"

// ── OCCT ──
// CapabilityToString + SharedFaceArea live in the OCCT-PURE TU
// (OcctSharedFaceArea.cpp) so the offline test can link them without openNURBS.
// v1: no BRepBndLib/Bnd_Box — the broad-phase prefilter was removed (it was the
// fault origin). The narrow phase (SharedFaceArea) is self-guarding.
#include <TopoDS_Face.hxx>
#include <Standard_Failure.hxx>

#include <exception>
#include <mutex>
#include <string>
#include <vector>

namespace Rook {

namespace {

// "worse of" two capabilities (the combined candidate capability). Ordered from
// best to worst: ExactBrep < PartialExactBrep < UnsupportedGeometry <
// FailedWithDiagnostics. Returns the MAX (least capable) by that ordering.
int CapRank(Capability c) {
    switch (c) {
        case Capability::ExactBrep:             return 0;
        case Capability::PartialExactBrep:      return 1;
        case Capability::UnsupportedGeometry:   return 2;
        case Capability::FailedWithDiagnostics: return 3;
    }
    return 3;
}
Capability CombineCapability(Capability a, Capability b) {
    return CapRank(a) >= CapRank(b) ? a : b;
}

// Capability of a converted ON_Brep from the converter result.
Capability CapabilityFromConversion(const OcctFaceSet& fs) {
    if (fs.failedFaceIndices().empty()) return Capability::ExactBrep;
    return fs.faceCount() > 0 ? Capability::PartialExactBrep
                              : Capability::UnsupportedGeometry;
}

} // namespace

ExactAdjacencyCore OcctAdjacencyEngine::Evaluate(
    const ObjectBrepPayload& source,
    const std::vector<ObjectBrepPayload>& candidates,
    double toleranceModelUnits) const
{
    static std::mutex s_engineMutex;   // v1: serialize the whole body
    std::lock_guard<std::mutex> lk(s_engineMutex);

    ExactAdjacencyCore core;
    core.objectId = source.objectId;

    const double tol = toleranceModelUnits > 0.0 ? toleranceModelUnits : 0.0;

    // ── Source unsupported / failed at extraction: nothing to evaluate. ──
    if (!source.brep) {
        core.sourceCapability = source.capability;
        for (const std::string& d : source.diagnostics)
            core.diagnostics.push_back("source:" + d);
        return core;
    }

    // ── OUTER CRASH BOUNDARY ──────────────────────────────────────────────
    // Every OCCT call below is individually guarded (ConvertBrepFaces guards
    // per face, SharedFaceArea guards each pair). This outer guard is the
    // backstop: if any OCCT fault still escapes an inner guard (or an OCCT
    // global-state fault fires between calls), it must NOT propagate out of
    // Evaluate as an access violation. It degrades to a diagnostic on the
    // partially-built core. The whole point is honest degradation, never a crash.
    // NOTE: the outer try only HELPS if the SEH-translated throw actually unwinds
    // — which it does because this TU is compiled /EHa (see the header comment).
    try {

    // ── Convert source once; derive its capability from the conversion. ──
    OcctFaceSet srcFs = ConvertBrepFaces(*source.brep);
    core.sourceCapability = CapabilityFromConversion(srcFs);
    for (int fi : srcFs.failedFaceIndices())
        core.diagnostics.push_back("source:convert_failed_face:" + std::to_string(fi));

    const int srcCount = srcFs.faceCount();

    // ── Per-candidate evaluation. ──
    for (const ObjectBrepPayload& cand : candidates) {
        const Capability combined = CombineCapability(core.sourceCapability, cand.capability);
        core.candidates.push_back(ExactCandidate{cand.objectId, combined});

        // Candidate unsupported / failed at extraction: record reason, no edge.
        if (!cand.brep) {
            if (cand.diagnostics.empty()) {
                core.diagnostics.push_back(
                    "cand:" + cand.objectId + ":" + CapabilityToString(cand.capability));
            } else {
                for (const std::string& d : cand.diagnostics)
                    core.diagnostics.push_back("cand:" + cand.objectId + ":" + d);
            }
            continue;
        }

        OcctFaceSet candFs = ConvertBrepFaces(*cand.brep);
        for (int fi : candFs.failedFaceIndices())
            core.diagnostics.push_back(
                "cand:" + cand.objectId + ":convert_failed_face:" + std::to_string(fi));
        const int candCount = candFs.faceCount();

        double edgeArea = 0.0;
        std::vector<FacePair> facePairs;

        for (int si = 0; si < srcCount; ++si) {
            for (int ci = 0; ci < candCount; ++ci) {
                // v1: no broad-phase prefilter — every pair goes straight to the
                // guarded narrow phase. SharedFaceArea has its own
                // Standard_Failure/.../HasErrors() guard and returns crashed/0,
                // so the narrow phase is safe and self-degrading.
                bool crashed = false;
                double pairArea = SharedFaceArea(
                    OcctFaceAt(srcFs, si), OcctFaceAt(candFs, ci), tol, crashed);
                if (crashed) {
                    core.diagnostics.push_back(
                        "engine:common_failed:" + std::to_string(srcFs.sourceFaceIndex(si)) +
                        "x" + std::to_string(candFs.sourceFaceIndex(ci)));
                    continue;
                }
                if (pairArea > kAreaTol) {
                    facePairs.push_back(FacePair{
                        srcFs.sourceFaceIndex(si),
                        candFs.sourceFaceIndex(ci),
                        pairArea});
                    edgeArea += pairArea;
                }
            }
        }

        if (edgeArea > kAreaTol) {
            ExactEdge edge;
            edge.sourceId = source.objectId;
            edge.targetId = cand.objectId;
            edge.relationship = "adjacent_exact";
            edge.sharedArea = edgeArea;
            edge.facePairs = std::move(facePairs);
            core.edges.push_back(std::move(edge));
        }
        // No-edge on an ExactBrep source with a non-touching candidate is NOT an
        // error — emit no diagnostic.
    }

    } catch (const Standard_Failure& e) {
        const char* msg = e.what();
        core.diagnostics.push_back(
            std::string("engine:evaluate_caught:") + (msg ? msg : "Standard_Failure"));
    } catch (const std::exception& e) {
        core.diagnostics.push_back(
            std::string("engine:evaluate_caught:") + (e.what() ? e.what() : "std::exception"));
    } catch (...) {
        core.diagnostics.push_back("engine:evaluate_caught:unknown");
    }

    return core;
}

} // namespace Rook
