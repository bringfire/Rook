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
// CONCURRENCY (v1, Task 6b): the whole Evaluate body runs on the single dedicated
// OCCT worker thread via OcctExecutor::Instance().Run([&]{ ... }). One worker
// thread == serial execution, so this IS the v1 serialization — the old per-call
// `static std::mutex s_engineMutex` (and its stale-lock/EDEADLK failure class) is
// gone. More importantly, the worker thread installs OCCT's per-thread
// SEH->Standard_Failure translation (OSD::SetSignal) ONCE at startup, so OCCT
// faults here are catchable Standard_Failure (the inner try/catch below degrades
// them to diagnostics) rather than a raw access violation that kills Rhino.
// Run() blocks the caller and rethrows any escaping exception on the caller
// thread; `source`/`candidates` are const refs captured by reference that outlive
// the blocking call, so the capture is safe.
//
// CRASH/UNWIND CONTRACT: an OCCT fault inside this TU surfaces as a
// Standard_Failure synthesized by OCCT's OSD::SetSignal SEH translator (installed
// on the OCCT worker thread). Under the default /EHsc model that SEH-translated
// throw does NOT reliably run C++ destructors during unwind. This TU is therefore
// compiled with /EHa (Async exceptions; set per-file in RookNative.vcxproj) so
// SEH-translated throws unwind the stack and run RAII destructors on every fault
// path. Do NOT drop the /EHa flag.
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
#include "SceneGraph/OcctExecutor.h"   // Task 6b: dedicated serialized OCCT thread

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
#include <string>
#include <vector>
#include <cstdio>
#include <cstdarg>
#include <cstdlib>
#include <malloc.h>   // _heapchk — TEMPORARY diagnostic (heap-corruption probe)

namespace Rook {

namespace {

// ── DIAGNOSTIC TRACE (TEMPORARY — pinpoints the OCCT call that hard-crashes the
//    process via terminate during exception unwind; see 2026-06-14 doc §0). Opens/
//    flushes/closes per line so the LAST line before a hard crash names the failing
//    step. REMOVE once root-caused. Logs candidate INDEX (not objectId) to stay
//    crash-safe regardless of string state. ──
void OcctTrace(const char* fmt, ...) {
    const char* tmp = std::getenv("TEMP");
    std::string path = (tmp ? std::string(tmp) : std::string("C:")) + "/rook_occt_trace.log";
    FILE* f = std::fopen(path.c_str(), "a");
    if (!f) return;
    va_list ap; va_start(ap, fmt); std::vfprintf(f, fmt, ap); va_end(ap);
    std::fputc('\n', f);
    std::fflush(f);
    std::fclose(f);
}

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
    // Task 6b: run the entire evaluate body on the dedicated OCCT worker thread.
    // One worker == serial (the v1 serialization) AND it is the only thread with
    // OCCT SE translation installed, so OCCT faults are catchable here instead of
    // killing the process. Run() blocks until the lambda returns and rethrows any
    // escaping exception on this caller thread. `source`/`candidates` are const
    // refs that outlive the blocking call — safe to capture by reference.
    return OcctExecutor::Instance().Run([&]() -> ExactAdjacencyCore {

    ExactAdjacencyCore core;
    core.objectId = source.objectId;
    OcctTrace("ENTER Evaluate ncand=%zu srcHasBrep=%d core.cands.cap=%zu data=%p", candidates.size(), source.brep ? 1 : 0, core.candidates.capacity(), (void*)core.candidates.data());

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
    OcctTrace("convert SOURCE begin");
    OcctFaceSet srcFs = ConvertBrepFaces(*source.brep);
    { int hc = _heapchk(); OcctTrace("convert SOURCE done faces=%d failed=%zu HEAPCHK=%d(%s) core.cands.cap=%zu data=%p",
        srcFs.faceCount(), srcFs.failedFaceIndices().size(), hc, hc==_HEAPOK?"OK":"BAD", core.candidates.capacity(), (void*)core.candidates.data()); }
    core.sourceCapability = CapabilityFromConversion(srcFs);
    for (int fi : srcFs.failedFaceIndices())
        core.diagnostics.push_back("source:convert_failed_face:" + std::to_string(fi));

    const int srcCount = srcFs.faceCount();

    // ── Per-candidate evaluation. ──
    int candIdx = -1;
    for (const ObjectBrepPayload& cand : candidates) {
        ++candIdx;
        OcctTrace("cand[%d] begin hasBrep=%d", candIdx, cand.brep ? 1 : 0);
        { int hc = _heapchk(); OcctTrace("cand[%d] preflight HEAPCHK=%d(%s) objId.size=%zu candidates.cap=%zu",
            candIdx, hc, hc==_HEAPOK?"OK":"BAD", cand.objectId.size(), core.candidates.capacity()); }
        const Capability combined = CombineCapability(core.sourceCapability, cand.capability);
        OcctTrace("cand[%d] before push_back", candIdx);
        core.candidates.push_back(ExactCandidate{cand.objectId, combined});
        OcctTrace("cand[%d] after push_back", candIdx);

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

        OcctTrace("cand[%d] convert begin", candIdx);
        OcctFaceSet candFs = ConvertBrepFaces(*cand.brep);
        OcctTrace("cand[%d] convert done faces=%d failed=%zu", candIdx, candFs.faceCount(), candFs.failedFaceIndices().size());
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
                OcctTrace("cand[%d] pair si=%d ci=%d begin", candIdx, si, ci);
                bool crashed = false;
                double pairArea = SharedFaceArea(
                    OcctFaceAt(srcFs, si), OcctFaceAt(candFs, ci), tol, crashed);
                OcctTrace("cand[%d] pair si=%d ci=%d done area=%.3f crashed=%d", candIdx, si, ci, pairArea, crashed ? 1 : 0);
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

    OcctTrace("LOOP DONE edges=%zu di. reached clean end", core.edges.size());

    } catch (const Standard_Failure& e) {
        OcctTrace("CAUGHT Standard_Failure");
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

    });  // OcctExecutor::Instance().Run
}

} // namespace Rook
