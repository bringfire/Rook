// OcctAdjacencyEngine.h
//
// Task 6 (Phase 1, ADDITIVE): the production OCCT exact-adjacency engine.
// Implements IExactAdjacencyEngine over the proven ON_Brep->OCCT converter
// (OnBrepToOcct). OCCT-HEADER-FREE: this public header includes only the
// contract (OcctAdjacencyTypes.h). The OCCT-aware machinery lives entirely in
// OcctAdjacencyEngine.cpp (a NotUsing-PCH, per-file-OCCT-include-path TU, same
// build shape as OnBrepToOcct.cpp).
//
// WIRED into the production /scene/graph/adjacency/exact route (Task 8): the
// ExactAdjacencyService extracts move-only Rook::occt::ObjectBrepPayloads on the main
// thread and calls Evaluate here (OCCT serialized on the OcctExecutor worker thread).
#pragma once
#include "SceneGraph/OcctAdjacencyTypes.h"

namespace Rook {
namespace occt {

class OcctAdjacencyEngine : public IExactAdjacencyEngine {
public:
    ExactAdjacencyCore Evaluate(
        const ObjectBrepPayload& source,
        const std::vector<ObjectBrepPayload>& candidates,
        double toleranceModelUnits) const override;
};

} // namespace occt
} // namespace Rook
