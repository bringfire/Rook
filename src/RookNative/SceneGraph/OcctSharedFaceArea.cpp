// OcctSharedFaceArea.cpp
//
// Task 6 (Phase 1, ADDITIVE): the OCCT-PURE engine primitives, split into their
// own translation unit so the offline OCCT-only robustness test can link them
// WITHOUT pulling the engine's openNURBS/converter dependencies (Evaluate +
// ConvertBrepFaces live in OcctAdjacencyEngine.cpp, which includes opennurbs.h).
//
// This TU touches OCCT only — no openNURBS, no Rhino SDK, no converter. It is
// compiled by BOTH RookNative (the .rhp) and OcctPrimitiveTests (the offline
// matrix). Same build shape as the other OCCT TUs: NotUsing PCH, per-file OCCT
// include path, /bigobj.
//
//   - CapabilityToString: the Capability enum string contract.
//   - SharedFaceArea: Boolean-Common shared-area primitive with a hard crash
//     boundary (Standard_Failure / any exception -> crashed=true, returns 0).

#include "SceneGraph/OcctAdjacencyTypes.h"
#include "SceneGraph/OcctAdjacencyEngine_internal.h"

#include <TopoDS_Shape.hxx>
#include <BRepAlgoAPI_Common.hxx>
#include <BRepGProp.hxx>
#include <GProp_GProps.hxx>
#include <NCollection_List.hxx>   // OCCT 8.0 moved TopTools_ListOfShape alias to Deprecated/
#include <Standard_Failure.hxx>

namespace Rook {

const char* CapabilityToString(Capability c) {
    switch (c) {
        case Capability::ExactBrep:             return "exact_brep";
        case Capability::PartialExactBrep:      return "partial_exact_brep";
        case Capability::UnsupportedGeometry:   return "unsupported_geometry";
        case Capability::FailedWithDiagnostics: return "failed_with_diagnostics";
    }
    return "failed_with_diagnostics";
}

double SharedFaceArea(const TopoDS_Shape& a, const TopoDS_Shape& b,
                      double fuzz, bool& crashed) {
    crashed = false;
    try {
        BRepAlgoAPI_Common op;
        NCollection_List<TopoDS_Shape> args;  args.Append(a);
        NCollection_List<TopoDS_Shape> tools; tools.Append(b);
        op.SetArguments(args);
        op.SetTools(tools);
        if (fuzz > 0.0) op.SetFuzzyValue(fuzz);
        op.Build();
        if (op.HasErrors()) return 0.0;
        GProp_GProps props;
        BRepGProp::SurfaceProperties(op.Shape(), props);
        return props.Mass();
    } catch (const Standard_Failure&) {
        crashed = true;
        return 0.0;
    } catch (...) {
        crashed = true;
        return 0.0;
    }
}

} // namespace Rook
