// PlanarAdjacencyEngine.cpp
//
// Pure (Rhino-free) implementation of the Gate 4 exact planar-adjacency engine.
// Implements spec §5. NO stdafx.h, NO Rhino SDK headers — this TU compiles in the
// dependency-free standalone test target AND in the Rhino-facing service.
//
// Clipper2: we deliberately include ONLY the lower-level core+engine headers, NOT
// clipper.h (which transitively pulls offset/rectclip/minkowski/triangulation).
// The one compiled Clipper2 TU (clipper.engine.cpp) includes clipper.h itself —
// that is the library's own TU and does not force linking the other units.

#include "SceneGraph/PlanarAdjacencyEngine.h"

#include "clipper2/clipper.core.h"     // PathD, PathsD, PointD, FillRule, ClipType, Area()
#include "clipper2/clipper.engine.h"   // ClipperD

#include <algorithm>
#include <array>
#include <cmath>
#include <string>
#include <vector>

namespace Rook {
namespace {

using Vec3 = std::array<double, 3>;

// ── Small vector helpers ─────────────────────────────────────────────────────

inline double dot3(const Vec3& a, const Vec3& b) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
inline Vec3 cross3(const Vec3& a, const Vec3& b) {
    return { a[1] * b[2] - a[2] * b[1],
             a[2] * b[0] - a[0] * b[2],
             a[0] * b[1] - a[1] * b[0] };
}
inline double norm3(const Vec3& a) { return std::sqrt(dot3(a, a)); }
inline Vec3 normalize3(const Vec3& a) {
    double n = norm3(a);
    if (n <= 0.0) return { 0.0, 0.0, 0.0 };
    return { a[0] / n, a[1] / n, a[2] / n };
}

// ── Capability combine (min-eligibility = worst = larger enum value) ─────────
// combine(a,b) = static_cast<Capability>(max((int)a,(int)b)).
inline Capability combine(Capability a, Capability b) {
    return static_cast<Capability>(std::max(static_cast<int>(a), static_cast<int>(b)));
}

// ── Coplanar gate ────────────────────────────────────────────────────────────
// Both faces' canonicalPlane are already sign-folded, so opposing faces on the
// same geometric plane share the SAME canonicalPlane. Compare normal components
// within kNormalTol and the offset d within the passed tolerance.
bool coplanar(const std::array<double, 4>& pa,
              const std::array<double, 4>& pb,
              double tolerance) {
    if (std::fabs(pa[0] - pb[0]) > kNormalTol) return false;
    if (std::fabs(pa[1] - pb[1]) > kNormalTol) return false;
    if (std::fabs(pa[2] - pb[2]) > kNormalTol) return false;
    if (std::fabs(pa[3] - pb[3]) > tolerance)  return false;
    return true;
}

// ── Opposing-normal gate ─────────────────────────────────────────────────────
// Uses the ORIGINAL oriented outwardNormal of each face (NOT the folded one).
bool opposing(const Vec3& na, const Vec3& nb) {
    return dot3(na, nb) < -(1.0 - kNormalTol);
}

// ── Deterministic in-plane orthonormal basis from a plane normal n ───────────
// Pick the reference world axis LEAST aligned with n (smallest |component|),
// remove the n-component, normalize -> u; v = n x u. Deterministic given n.
void buildBasis(const Vec3& nIn, Vec3& u, Vec3& v) {
    Vec3 n = normalize3(nIn);
    // Reference axis least aligned with n.
    double ax = std::fabs(n[0]), ay = std::fabs(n[1]), az = std::fabs(n[2]);
    Vec3 ref;
    if (ax <= ay && ax <= az)      ref = { 1.0, 0.0, 0.0 };
    else if (ay <= ax && ay <= az) ref = { 0.0, 1.0, 0.0 };
    else                           ref = { 0.0, 0.0, 1.0 };
    double d = dot3(ref, n);
    Vec3 uu = { ref[0] - d * n[0], ref[1] - d * n[1], ref[2] - d * n[2] };
    u = normalize3(uu);
    v = cross3(n, u);  // already unit (n,u orthonormal)
}

// Signed area (shoelace) of a 2D path.
double signedArea2D(const Clipper2Lib::PathD& path) {
    double a = 0.0;
    size_t m = path.size();
    for (size_t i = 0; i < m; ++i) {
        const auto& p = path[i];
        const auto& q = path[(i + 1) % m];
        a += p.x * q.y - q.x * p.y;
    }
    return 0.5 * a;
}

// Safe coordinate bound: |coord| * 10^kClipperPrecision must stay well within
// Clipper2's safe integer range. 1e9 model units is generous — after origin
// subtraction real geometry is tiny, so this only trips on pathological input.
constexpr double kSafeCoordBound = 1e9;

// Compute the exact net overlap area of two opposing coplanar planar faces.
// Returns net area (holes subtracted). Returns 0.0 (and pushes a diagnostic) if
// the range guard trips. Uses fa's canonicalPlane normal for the basis and fa's
// outer-loop centroid as the local origin (spec §5 precision).
double faceOverlapArea(const PlanarFace& fa,
                       const PlanarFace& fb,
                       const std::string& sourceId,
                       const std::string& targetId,
                       std::vector<std::string>& diagnostics) {
    using namespace Clipper2Lib;

    if (fa.loops.empty() || fb.loops.empty()) return 0.0;
    if (fa.loops[0].empty()) return 0.0;

    // Basis from the canonical (folded) plane normal of fa.
    Vec3 n = { fa.canonicalPlane[0], fa.canonicalPlane[1], fa.canonicalPlane[2] };
    Vec3 u, v;
    buildBasis(n, u, v);

    // Local origin = centroid of fa's OUTER loop (loops[0]).
    Vec3 O = { 0.0, 0.0, 0.0 };
    {
        const auto& outer = fa.loops[0];
        for (const auto& p : outer) { O[0] += p[0]; O[1] += p[1]; O[2] += p[2]; }
        double inv = 1.0 / static_cast<double>(outer.size());
        O[0] *= inv; O[1] *= inv; O[2] *= inv;
    }

    bool rangeTripped = false;

    // Project one face's loops into the common 2D frame, normalizing orientation:
    // outer (index 0) -> CCW (positive signed area); holes -> CW (negative).
    auto projectFace = [&](const PlanarFace& face) -> PathsD {
        PathsD paths;
        paths.reserve(face.loops.size());
        for (size_t li = 0; li < face.loops.size(); ++li) {
            const auto& loop = face.loops[li];
            PathD path;
            path.reserve(loop.size());
            for (const auto& p : loop) {
                Vec3 rel = { p[0] - O[0], p[1] - O[1], p[2] - O[2] };
                double cu = dot3(rel, u);
                double cv = dot3(rel, v);
                if (std::fabs(cu) > kSafeCoordBound || std::fabs(cv) > kSafeCoordBound) {
                    rangeTripped = true;
                }
                path.push_back(PointD(cu, cv));
            }
            // Normalize winding.
            double sa = signedArea2D(path);
            bool wantCCW = (li == 0);  // outer CCW (positive), holes CW (negative)
            if (wantCCW && sa < 0.0)       std::reverse(path.begin(), path.end());
            else if (!wantCCW && sa > 0.0) std::reverse(path.begin(), path.end());
            paths.push_back(std::move(path));
        }
        return paths;
    };

    PathsD subject = projectFace(fa);
    PathsD clip    = projectFace(fb);

    if (rangeTripped) {
        diagnostics.push_back("range_guard_skip:" + sourceId + "|" + targetId);
        return 0.0;
    }

    ClipperD clipper(kClipperPrecision);
    clipper.AddSubject(subject);
    clipper.AddClip(clip);
    PathsD solution;
    clipper.Execute(ClipType::Intersection, FillRule::NonZero, solution);

    return Area(solution);  // net (holes subtract) given correct orientation
}

} // anonymous namespace

ExactAdjacencyCore PlanarAdjacencyEngine::Evaluate(
        const ObjectFaceSummary& source,
        const std::vector<ObjectFaceSummary>& candidates,
        double tolerance) const {
    ExactAdjacencyCore core;
    core.objectId = source.objectId;
    core.sourceCapability = source.capability;
    // graphSequence, capped, totalCandidateCount, candidateLimit are populated by
    // the service later — leave at struct defaults.

    for (const ObjectFaceSummary& C : candidates) {
        Capability combined = combine(source.capability, C.capability);
        core.candidates.push_back(ExactCandidate{ C.objectId, combined });

        double pairArea = 0.0;
        for (const FaceSummary& fa : source.faces) {
            if (fa.kind != FaceKind::Planar) continue;   // eligibility contract
            for (const FaceSummary& fb : C.faces) {
                if (fb.kind != FaceKind::Planar) continue;
                if (!coplanar(fa.planar.canonicalPlane, fb.planar.canonicalPlane, tolerance))
                    continue;
                if (!opposing(fa.planar.outwardNormal, fb.planar.outwardNormal))
                    continue;
                pairArea += faceOverlapArea(fa.planar, fb.planar,
                                            source.objectId, C.objectId,
                                            core.diagnostics);
            }
        }

        if (pairArea > kAreaTol) {
            core.edges.push_back(ExactEdge{ source.objectId, C.objectId,
                                            "adjacent_exact", pairArea });
        }
    }

    core.candidateCount = static_cast<int>(core.candidates.size());
    return core;
}

} // namespace Rook
