// ExactAdjacencyTypes.h
//
// Plain-data DTOs for the exact (planar) adjacency engine.
// Header-only — NO Rhino SDK includes. Includable by the pure (Rhino-free)
// engine AND by the Rhino-facing service.
// Mirrors the Gate 4 exact-adjacency spec §3–§5.

#pragma once

#include <string>
#include <vector>
#include <array>
#include <optional>

// SceneNode is an existing plain-data struct (Rhino-free) — include its header
// rather than redefining it.
#include "SceneGraph/SceneGraphModels.h"

namespace Rook {

// ─── Candidate query (spec §3) ─────────────────────────────────

struct CandidateQueryOptions { int maxCandidates = 64; double tolerance = 1e-3; };

struct ScoredCandidate { std::string id; double bboxDistance; double bboxOverlap; };

struct CandidateQueryResult {
    int graphSequence;
    bool sourceFound;
    SceneNode sourceNode;                  // plain copy (existing type — include its header)
    std::vector<ScoredCandidate> candidates;  // DETERMINISTIC nearest-first, then capped
    bool capped;
    int totalCandidateCount;               // pre-cap count
};

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

} // namespace Rook
