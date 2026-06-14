// PlanarAdjacencyEngine.h
//
// Pure (Rhino-free) exact planar-adjacency engine interface + concrete class.
// Gate 4 exact-adjacency spec. NO Rhino SDK includes, NO stdafx — this header
// (and its eventual .cpp) compile in the dependency-free standalone test target
// as well as in the Rhino-facing service.
//
// The engine CONSUMES the per-object `capability` already present on each
// ObjectFaceSummary (it does NOT classify geometry — see spec Finding 5). For an
// evaluated source/candidate pair it (a) evaluates eligible planar face pairs via
// Clipper2 boolean intersection, and (b) sets each candidate's combined
// capability = min-eligibility(source.capability, candidate.capability).
//
// IMPLEMENTATION NOTE (TDD RED): Evaluate is declared here but DEFINED in
// PlanarAdjacencyEngine.cpp (Task 4). It is intentionally NOT inline so the
// standalone test links with an unresolved external until Task 4 lands.

#pragma once

#include "SceneGraph/ExactAdjacencyTypes.h"

#include <vector>

namespace Rook {

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
        double tolerance) const override;   // DEFINED in PlanarAdjacencyEngine.cpp (Task 4)
};

} // namespace Rook
