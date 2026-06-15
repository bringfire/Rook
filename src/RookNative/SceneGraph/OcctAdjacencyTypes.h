// OcctAdjacencyTypes.h
// Production exact-adjacency contract for the OCCT engine. openNURBS-based
// (carries an owned ON_Brep); NO Rhino SDK types. Includable by the engine and
// the Rhino-facing service. See 2026-06-15-occt-adjacency-engine-design.md.
// PHASE 1: standalone. PHASE 2: add the ExactAdjacencyTypes.h include below for the
// shared broad-phase query types once that header is stripped of engine-contract types.
#pragma once
// #include "SceneGraph/ExactAdjacencyTypes.h"   // <-- uncomment in Phase 2 (query types)
#include <string>
#include <vector>
#include <memory>

class ON_Brep;   // fwd-decl; only the service/engine TUs include opennurbs

namespace Rook {

enum class Capability {
    ExactBrep,             // all relevant analytic Brep faces converted + evaluated
    PartialExactBrep,      // >=1 face evaluated, some skipped/failed (see diagnostics)
    UnsupportedGeometry,   // mesh / SubD / non-Brep — no analytic exact path
    FailedWithDiagnostics  // object-level failure (bad id / no geom / conversion / cap)
};
const char* CapabilityToString(Capability c);   // defined in OcctAdjacencyEngine.cpp

// Move-only, transient geometry payload. Built per-call on the MAIN thread,
// consumed on the WORKER thread, never copied, never cached.
struct ObjectBrepPayload {
    std::string objectId;
    std::unique_ptr<const ON_Brep> brep;   // owned IMMUTABLE deep-copy; null if unsupported/failed
    Capability capability = Capability::FailedWithDiagnostics;
    double modelUnitsToMillimeters = 1.0;  // doc unit scale (e.g. 25.4 for inches)
    std::vector<std::string> diagnostics;  // extraction reason codes
};

// One contributing coincident face pair (structured, first-class on the edge).
struct FacePair { int sourceFaceIndex; int candidateFaceIndex; double sharedArea; };

struct ExactEdge {
    std::string sourceId, targetId;
    std::string relationship = "adjacent_exact";
    double sharedArea = 0.0;               // model-units^2; sum of facePairs[].sharedArea
    std::vector<FacePair> facePairs;
};

struct ExactCandidate { std::string id; Capability capability; };

struct ExactAdjacencyCore {                // CACHED + serialized (plain data only)
    std::string objectId;
    int graphSequence = 0;
    Capability sourceCapability = Capability::FailedWithDiagnostics;
    std::string lengthUnit = "unknown";    // e.g. "inches"
    std::string areaUnit = "unknown";      // e.g. "inches^2"
    std::vector<ExactEdge> edges;
    std::vector<ExactCandidate> candidates;
    bool capped = false;
    int candidateCount = 0;
    int candidateLimit = 0;
    int totalCandidateCount = 0;
    std::vector<std::string> diagnostics;
};

// Engine constants (covered by kEngineVersion; bump when math/tol/contract changes).
constexpr double kAreaTol      = 1e-6;     // numerical noise floor, model-units^2 (NOT a graze policy)
constexpr double kDefaultFuzzMm = 1e-2;    // default fuzzy in mm; converted to model units per call
constexpr int    kEngineVersion = 2;       // was 1 (Clipper planar); bumped for OCCT contract

class IExactAdjacencyEngine {
public:
    virtual ~IExactAdjacencyEngine() = default;
    // toleranceModelUnits = fuzzMm / modelUnitsToMillimeters (computed by the service).
    virtual ExactAdjacencyCore Evaluate(
        const ObjectBrepPayload& source,
        const std::vector<ObjectBrepPayload>& candidates,
        double toleranceModelUnits) const = 0;
};

} // namespace Rook
