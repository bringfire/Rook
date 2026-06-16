// ExactAdjacencyTypes.h
//
// Broad-phase candidate-QUERY DTOs for the exact-adjacency pipeline.
// Header-only — NO Rhino SDK includes. Includable by the Rhino-facing service and
// the scene graph. Mirrors the Gate 4 exact-adjacency spec §3.
//
// SCOPE (post-Task-8): this header carries ONLY the broad-phase query types. The
// ENGINE / RESULT contract (Capability, ObjectBrepPayload, FacePair, ExactEdge,
// ExactCandidate, ExactAdjacencyCore, IExactAdjacencyEngine) now lives in
// `Rook::occt` in OcctAdjacencyTypes.h. The legacy planar engine-contract types that
// used to live here were removed (they had the SAME bare-`Rook` names as the new OCCT
// contract — a latent ODR hazard; see the §0 RESOLVED banner in
// docs/rook_docs/2026-06-14-occt-uniform-engine-decision.md). Consumers that need both
// (e.g. ExactAdjacencyService) include this header AND OcctAdjacencyTypes.h directly.

#pragma once

#include <string>
#include <vector>

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

} // namespace Rook
