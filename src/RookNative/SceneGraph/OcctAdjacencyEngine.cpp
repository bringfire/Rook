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
// METHOD:
//   - Convert source + each candidate ON_Brep to OCCT faces ONCE (proven converter).
//   - Capability per object derives from the converter's failed-face set.
//   - Broad phase: per (source-face, candidate-face) pair, reject if their OCCT
//     bounding boxes don't overlap within tolerance (Bnd_Box::IsOut after enlarging
//     by the tolerance gap). Cheap, conservative — never a false NEGATIVE.
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
#include <TopoDS_Face.hxx>
#include <BRepBndLib.hxx>
#include <Bnd_Box.hxx>
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

// Bounding box of an OCCT face. Returned by value (Bnd_Box is copyable).
//
// CRASH BOUNDARY: BRepBndLib::Add is the ONE OCCT call in the broad phase that is
// NOT inside SharedFaceArea's guard. On a face that converted to a non-null
// TopoDS_Face but carries degenerate / missing internal geometry (no triangulation,
// a null Geom handle along the bbox path), BRepBndLib::Add can fault with a
// null-pointer WRITE; OCCT's OSD::SetSignal translator turns that access violation
// into a Standard_Failure. If it escaped here it would propagate straight out of
// Evaluate (this was the observed `evaluate_failed: ACCESS VIOLATION ... WRITE`).
// Guard it: on ANY failure return a VOID (empty) Bnd_Box. A void box is treated by
// Bnd_Box::IsOut as "always overlapping" (IsOut returns false), so the prefilter
// CANNOT false-skip the pair — it conservatively falls through to the narrow phase,
// which runs under SharedFaceArea's own crash guard. `failed` is set so the caller
// can record an honest `engine:` diagnostic. Never crashes.
Bnd_Box FaceBox(const TopoDS_Face& f, bool& failed) {
    failed = false;
    try {
        Bnd_Box box;
        BRepBndLib::Add(f, box);
        return box;
    } catch (const Standard_Failure&) {
        failed = true;
        return Bnd_Box();   // void box -> IsOut == false -> never skipped
    } catch (...) {
        failed = true;
        return Bnd_Box();
    }
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
    // per face, FaceBox guards each bbox, SharedFaceArea guards each pair). This
    // outer guard is the backstop: if any OCCT fault still escapes an inner guard
    // (or an OCCT global-state fault fires between calls), it must NOT propagate
    // out of Evaluate as an access violation. It degrades to a diagnostic on the
    // partially-built core. The whole point is honest degradation, never a crash.
    try {

    // ── Convert source once; derive its capability from the conversion. ──
    OcctFaceSet srcFs = ConvertBrepFaces(*source.brep);
    core.sourceCapability = CapabilityFromConversion(srcFs);
    for (int fi : srcFs.failedFaceIndices())
        core.diagnostics.push_back("source:convert_failed_face:" + std::to_string(fi));

    const int srcCount = srcFs.faceCount();

    // Precompute source face bounding boxes (guarded; a failed box stays void
    // so the prefilter never false-skips that face's pairs).
    std::vector<Bnd_Box> srcBoxes;
    srcBoxes.reserve(static_cast<size_t>(srcCount));
    for (int s = 0; s < srcCount; ++s) {
        bool boxFailed = false;
        srcBoxes.push_back(FaceBox(OcctFaceAt(srcFs, s), boxFailed));
        if (boxFailed)
            core.diagnostics.push_back(
                "engine:bbox_failed:source_face:" + std::to_string(srcFs.sourceFaceIndex(s)));
    }

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

        // Precompute candidate face bounding boxes (guarded; same conservative
        // void-box-on-failure policy as the source side).
        std::vector<Bnd_Box> candBoxes;
        candBoxes.reserve(static_cast<size_t>(candCount));
        for (int c = 0; c < candCount; ++c) {
            bool boxFailed = false;
            candBoxes.push_back(FaceBox(OcctFaceAt(candFs, c), boxFailed));
            if (boxFailed)
                core.diagnostics.push_back(
                    "engine:bbox_failed:cand:" + cand.objectId + ":face:" +
                    std::to_string(candFs.sourceFaceIndex(c)));
        }

        double edgeArea = 0.0;
        std::vector<FacePair> facePairs;

        for (int si = 0; si < srcCount; ++si) {
            for (int ci = 0; ci < candCount; ++ci) {
                // Broad phase: skip non-overlapping boxes (gap > tol). IsOut with
                // a tolerance gap; conservative (enlarge the candidate box by tol).
                Bnd_Box cb = candBoxes[ci];
                if (tol > 0.0) cb.Enlarge(tol);
                if (srcBoxes[si].IsOut(cb)) continue;

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
