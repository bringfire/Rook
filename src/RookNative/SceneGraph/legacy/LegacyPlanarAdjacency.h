// LegacyPlanarAdjacency.h
//
// FROZEN LEGACY COPY of the Gate 4 Clipper2-based exact planar-adjacency engine.
//
// This is a self-contained snapshot of the planar engine contract types (formerly
// in SceneGraph/ExactAdjacencyTypes.h) PLUS the engine interface + concrete class
// (formerly in SceneGraph/PlanarAdjacencyEngine.h), all re-homed under
// `namespace Rook::Legacy`. It exists so the Clipper engine can be retired from
// the production default while remaining buildable and regression-tested in
// isolation.
//
// SELF-CONTAINED: this header deliberately does NOT depend on
// SceneGraph/ExactAdjacencyTypes.h — the engine-contract types are copied here.
// The shared broad-phase query types (CandidateQueryOptions / ScoredCandidate /
// CandidateQueryResult) are NOT copied: the Clipper Evaluate path only needs
// ObjectFaceSummary / ExactAdjacencyCore. Those query types are the only reason
// the original types header pulled in SceneGraphModels.h (for SceneNode), so no
// SceneGraph header include is required here.
//
// NO Rhino SDK includes, NO stdafx — compiles in the dependency-free standalone
// test target.

#pragma once

#include <string>
#include <vector>
#include <array>
#include <optional>

namespace Rook {
namespace Legacy {

// ─── Data model (spec §4) ──────────────────────────────────────

enum class FaceKind { Planar, Curved, MeshApprox, Unknown };

// Declared BEFORE ObjectFaceSummary.
enum class Capability {
    ExactPlanar,                     // all faces planar, orientation-reliable, valid
    PartialExactUnsupported,         // some faces exact-eligible, some not
    CoarseFallbackExactUnsupported,  // no exact-eligible faces
    UnsupportedGeometry,             // mesh/subd/malformed loops
    FailedWithDiagnostics
};
// Per-face/object reason codes carried in ObjectFaceSummary.diagnostics:
//   "curved" | "mesh" | "subd" | "unoriented" | "malformed_loop"
//   (concave is NOT a reason — Clipper2 handles it.)

struct PlanarFace {
    std::array<double,3> outwardNormal;    // ORIGINAL oriented normal — opposing-normal
                                           //   predicate. From the Brep face's oriented
                                           //   normal; valid only when orientation is
                                           //   reliable (closed/orientable solid).
    std::array<double,4> canonicalPlane;   // sign-folded normal+offset — COPLANAR grouping only
    // loops[0]=outer, loops[1..]=holes. Concave allowed. Plane-local 2D
    // projection + boolean done by the engine, not stored here.
    std::vector<std::vector<std::array<double,3>>> loops;
};
struct FaceSummary {                       // exactly ONE face
    FaceKind kind = FaceKind::Unknown;
    PlanarFace planar;                     // valid iff kind==Planar
    // curved: reserved future surface descriptor (NOT populated in v1)
};
struct ObjectFaceSummary {                 // ONE object's faces
    std::string objectId;
    std::vector<FaceSummary> faces;
    Capability capability;                 // rollup (see §5)
    std::vector<std::string> diagnostics;  // reason codes + notes
};

struct ExactEdge {
    std::string sourceId, targetId;
    std::string relationship = "adjacent_exact";
    double sharedArea = 0.0;               // Clipper2 hole/concave-aware
};
// Type-enforced separation: the cached core carries NO coarse state.
struct ExactCandidate { std::string id; Capability capability; };  // cached
struct ExactAdjacencyCore {                // CACHED — exact-only, never coarse
    std::string objectId;
    int graphSequence = 0;
    Capability sourceCapability = Capability::FailedWithDiagnostics;
    std::vector<ExactEdge> edges;
    std::vector<ExactCandidate> candidates;
    bool capped = false;
    int candidateCount = 0;                // evaluated (post-cap)
    int candidateLimit = 0;
    int totalCandidateCount = 0;           // pre-cap
    std::vector<std::string> diagnostics;
};
// RESPONSE DTO — built from a cached ExactAdjacencyCore + live coarse decoration
// (post-lookup, never cached).
struct CandidateOutcome {                  // response only
    std::string id;
    Capability capability;
    std::optional<std::string> coarseRelationship;
};

// ─── Engine constants (spec §5) ────────────────────────────────
// Fixed engine constants, covered by kEngineVersion.

constexpr double kNormalTol = 1e-6;        // opposing-normal predicate slack: dot < -(1 - kNormalTol)
constexpr double kAreaTol   = 1e-6;        // minimum shared area to count as adjacency (model units^2)
constexpr int    kClipperPrecision = 6;    // ClipperD decimal precision
constexpr int    kEngineVersion    = 1;    // bump when engine math/tols/precision change

// ─── Engine interface + concrete class ─────────────────────────
//
// The engine CONSUMES the per-object `capability` already present on each
// ObjectFaceSummary (it does NOT classify geometry — see spec Finding 5). For an
// evaluated source/candidate pair it (a) evaluates eligible planar face pairs via
// Clipper2 boolean intersection, and (b) sets each candidate's combined
// capability = min-eligibility(source.capability, candidate.capability).

class IExactAdjacencyEngine {
public:
    virtual ~IExactAdjacencyEngine() = default;
    virtual ExactAdjacencyCore Evaluate(
        const ObjectFaceSummary& source,
        const std::vector<ObjectFaceSummary>& candidates,
        double tolerance) const = 0;       // pure data; no Rhino, no threads
};

class PlanarAdjacencyEngine : public IExactAdjacencyEngine {
public:
    ExactAdjacencyCore Evaluate(
        const ObjectFaceSummary& source,
        const std::vector<ObjectFaceSummary>& candidates,
        double tolerance) const override;   // DEFINED in LegacyPlanarAdjacency.cpp
};

} // namespace Legacy
} // namespace Rook
