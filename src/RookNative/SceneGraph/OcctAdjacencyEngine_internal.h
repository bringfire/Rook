// OcctAdjacencyEngine_internal.h
//
// OCCT-AWARE internal header exposing the engine's testable primitive. Included
// ONLY by OCCT translation units: the engine TU (OcctAdjacencyEngine.cpp, which
// defines it) and the offline OCCT-only robustness test
// (occt_primitive_tests.cpp, which exercises it on raw OCCT primitives — no
// ON_Brep, no converter).
#pragma once
#include <TopoDS_Shape.hxx>

namespace Rook {

// Boolean-Common shared (overlap) area between two shapes, evaluated under a
// fuzzy tolerance. Returns the surface area (mass of the SurfaceProperties) of
// the Common result in the SAME units as the inputs. Sets `crashed=true` (and
// returns 0) if OCCT raises a Standard_Failure or any other exception, OR if
// the operation reports errors. This is the robustness boundary: an OCCT
// kernel failure on one pair must never take down the engine.
double SharedFaceArea(const TopoDS_Shape& a, const TopoDS_Shape& b,
                      double fuzz, bool& crashed);

} // namespace Rook
