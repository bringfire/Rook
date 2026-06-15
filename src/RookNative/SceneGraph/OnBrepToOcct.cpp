// OnBrepToOcct.cpp
//
// Task 4 (Phase 1, ADDITIVE): ON_Brep -> OCCT face converter, SURFACES ONLY.
// OCCT-ONLY translation unit in the same spirit as OcctProbe.cpp: NO stdafx.h
// (NotUsing PCH in the vcxproj), per-file OCCT include path. It is the ONE TU
// that includes BOTH openNURBS and OCCT headers; the public header
// (OnBrepToOcct.h) stays OCCT-header-free (pimpl) so Rhino-facing TUs can
// include it without pulling OCCT.
//
// Surface translation follows the Spike-D recipe (proven faithful to <1e-6 mm):
//   - openNURBS control points are HOMOGENEOUS (wx,wy,wz,w); divide X/Y/Z by W
//     to get OCCT euclidean poles, pass W as the OCCT weight.
//   - openNURBS knot vectors have length (ncv+deg-1); OCCT's flat-knot convention
//     wants (ncv+deg+1) — prepend AND append a clamp knot, then compress to
//     distinct-knots + multiplicities.
//
// TRIMS ARE NOT APPLIED IN THIS TASK (Task 5). Faces are built UNTRIMMED, so
// total area OVER-reports vs a trimmed oracle — that is expected for Task 4.

#include "SceneGraph/OnBrepToOcct.h"

// ── openNURBS (Rhino SDK; include path supplied per-file in the vcxproj) ──────
// This TU does NOT include RhinoSdk.h (which would define OPENNURBS_IMPORTS for us),
// so we declare it ourselves: openNURBS ships as a DLL and its classes/templates
// must be __declspec(dllimport) here, otherwise the template instantiations
// (e.g. ON_ClassArray<ON_BrepFace>) are emitted locally and collide at link time
// with the ones exported by opennurbs.lib (LNK2005).
#ifndef NOMINMAX
#define NOMINMAX 1
#endif
#ifndef OPENNURBS_IMPORTS
#define OPENNURBS_IMPORTS
#endif
#include "opennurbs.h"

// ── OCCT (per-file include path in the vcxproj; same as OcctProbe.cpp) ────────
#include <gp_Pnt.hxx>
#include <Standard_TypeDef.hxx>
#include <NCollection_Array1.hxx>
#include <NCollection_Array2.hxx>
#include <Geom_BSplineSurface.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepGProp.hxx>
#include <GProp_GProps.hxx>
#include <Precision.hxx>
#include <TopoDS_Face.hxx>
#include <Standard_Failure.hxx>

#include <vector>

namespace Rook {

// ── pimpl: holds the converted OCCT faces + the slot->source-face-index map ──
struct OcctFaceSet::Impl {
    std::vector<TopoDS_Face> faces;       // one per successfully converted face
    std::vector<int>         sourceIndex; // sourceIndex[slot] = ON_Brep face index
    std::vector<int>         failed;      // ON_Brep face indices that failed
};

OcctFaceSet::OcctFaceSet() : m_impl(new Impl()) {}
OcctFaceSet::~OcctFaceSet() = default;
OcctFaceSet::OcctFaceSet(OcctFaceSet&&) noexcept = default;
OcctFaceSet& OcctFaceSet::operator=(OcctFaceSet&&) noexcept = default;

int OcctFaceSet::faceCount() const {
    return m_impl ? static_cast<int>(m_impl->faces.size()) : 0;
}
int OcctFaceSet::sourceFaceIndex(int occtSlot) const {
    if (!m_impl || occtSlot < 0 || occtSlot >= static_cast<int>(m_impl->sourceIndex.size()))
        return -1;
    return m_impl->sourceIndex[occtSlot];
}
const std::vector<int>& OcctFaceSet::failedFaceIndices() const {
    static const std::vector<int> empty;
    return m_impl ? m_impl->failed : empty;
}
OcctFaceSet::Impl* OcctFaceSet::impl() { return m_impl.get(); }
const OcctFaceSet::Impl* OcctFaceSet::impl() const { return m_impl.get(); }

namespace {

// Build OCCT flat distinct-knots + multiplicities from an openNURBS knot vector
// in one direction (Spike-D occt_knots). openNURBS length = ncv+deg-1; we prepend
// the first knot and append the last knot to satisfy OCCT's clamped flat-knot
// convention, then compress to distinct values + multiplicities.
void OcctKnots(const ON_NurbsSurface& ns, int dir,
               std::vector<double>& knots, std::vector<int>& mults)
{
    const int n = ns.KnotCount(dir);
    std::vector<double> flat;
    flat.reserve(static_cast<size_t>(n) + 2);
    const double first = ns.Knot(dir, 0);
    const double last  = ns.Knot(dir, n - 1);
    flat.push_back(first);
    for (int i = 0; i < n; ++i) flat.push_back(ns.Knot(dir, i));
    flat.push_back(last);

    knots.clear();
    mults.clear();
    for (double k : flat) {
        if (!knots.empty() && std::fabs(k - knots.back()) < 1e-12) {
            ++mults.back();
        } else {
            knots.push_back(k);
            mults.push_back(1);
        }
    }
}

// Rebuild one openNURBS NURBS surface as an OCCT Geom_BSplineSurface. Throws
// Standard_Failure on bad geometry (caller catches per-face).
Handle(Geom_BSplineSurface) ToOcctSurface(const ON_NurbsSurface& ns)
{
    const int nu = ns.CVCount(0);
    const int nv = ns.CVCount(1);
    const int du = ns.Degree(0);
    const int dv = ns.Degree(1);

    NCollection_Array2<gp_Pnt>  poles(1, nu, 1, nv);
    NCollection_Array2<double>  weights(1, nu, 1, nv);

    for (int i = 0; i < nu; ++i) {
        for (int j = 0; j < nv; ++j) {
            // ControlPoint() returns HOMOGENEOUS (wx,wy,wz,w); de-homogenize.
            ON_4dPoint cp = ns.ControlPoint(i, j);
            double w = cp.w;
            if (w == 0.0) w = 1.0;
            poles.SetValue(i + 1, j + 1, gp_Pnt(cp.x / w, cp.y / w, cp.z / w));
            weights.SetValue(i + 1, j + 1, w);
        }
    }

    std::vector<double> uk, vk;
    std::vector<int>    um, vm;
    OcctKnots(ns, 0, uk, um);
    OcctKnots(ns, 1, vk, vm);

    NCollection_Array1<double> UK(1, static_cast<int>(uk.size()));
    NCollection_Array1<int>    UM(1, static_cast<int>(um.size()));
    NCollection_Array1<double> VK(1, static_cast<int>(vk.size()));
    NCollection_Array1<int>    VM(1, static_cast<int>(vm.size()));
    for (int i = 0; i < static_cast<int>(uk.size()); ++i) { UK.SetValue(i + 1, uk[i]); UM.SetValue(i + 1, um[i]); }
    for (int i = 0; i < static_cast<int>(vk.size()); ++i) { VK.SetValue(i + 1, vk[i]); VM.SetValue(i + 1, vm[i]); }

    return new Geom_BSplineSurface(poles, weights, UK, VK, UM, VM, du, dv,
                                   false, false);
}

double FaceArea(const TopoDS_Face& f)
{
    GProp_GProps props;
    BRepGProp::SurfaceProperties(f, props);
    return props.Mass();
}

} // namespace

OcctFaceSet ConvertBrepFaces(const ON_Brep& brep)
{
    OcctFaceSet set;
    OcctFaceSet::Impl* impl = set.impl();

    const int faceCount = brep.m_F.Count();
    for (int fi = 0; fi < faceCount; ++fi) {
        try {
            const ON_BrepFace& face = brep.m_F[fi];
            // Get the analytic surface as a NURBS form (handles planes, spheres,
            // NURBS, etc. via openNURBS' NurbsSurface conversion).
            ON_NurbsSurface ns;
            if (face.GetNurbForm(ns) == 0) {
                impl->failed.push_back(fi);
                continue;
            }
            Handle(Geom_BSplineSurface) surf = ToOcctSurface(ns);
            if (surf.IsNull()) {
                impl->failed.push_back(fi);
                continue;
            }
            // SURFACES ONLY (Task 4): untrimmed natural-bound face.
            BRepBuilderAPI_MakeFace mk(surf, Precision::Confusion());
            if (!mk.IsDone()) {
                impl->failed.push_back(fi);
                continue;
            }
            impl->faces.push_back(mk.Face());
            impl->sourceIndex.push_back(fi);
        } catch (const Standard_Failure&) {
            impl->failed.push_back(fi);
        } catch (...) {
            impl->failed.push_back(fi);
        }
    }
    return set;
}

double OcctFaceSetTotalArea(const OcctFaceSet& set)
{
    const OcctFaceSet::Impl* impl = set.impl();
    if (!impl) return 0.0;
    double total = 0.0;
    for (const TopoDS_Face& f : impl->faces) {
        try {
            total += FaceArea(f);
        } catch (...) {
            // ignore a single face's area-eval failure
        }
    }
    return total;
}

} // namespace Rook
