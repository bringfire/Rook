// OnBrepToOcct.cpp
//
// Task 4 (Phase 1, ADDITIVE): ON_Brep -> OCCT face converter.
// Task 5 (this revision): TRIMMED + orientation-faithful faces.
//
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
// Task 5 — trims/orientation (Strengthener-1, written here for the first time):
//   - Per ON_BrepFace, walk its ON_BrepLoops. For each loop, build an OCCT wire
//     from the loop's ON_BrepTrim pcurves (the 2D parameter-space curves on the
//     surface — exact, lower-risk than 3D-edge reprojection).
//   - Each pcurve -> Geom2d_BSplineCurve (same homogeneous ÷W + clamped-knot
//     recipe as the 3D surface, but in 2D: gp_Pnt2d poles).
//   - BRepBuilderAPI_MakeEdge(Handle(Geom2d_Curve), Handle(Geom_Surface)) builds
//     the edge FROM the pcurve on the surface. trim.m_bRev3d is the 2d-pcurve-vs-
//     3d-edge orientation relationship, NOT the loop-traversal direction; the
//     pcurves are already loop-oriented, so m_bRev3d must NOT be applied (applying
//     it would double-account and mis-direct the wire).
//   - Singular trims (sphere/cone poles) -> OCCT degenerated edges (NOT dropped:
//     dropping leaves an open wire). Seam trims appear on both sides so periodic
//     surfaces (cylinders) close.
//   - Outer loop -> bounding wire; inner loops -> holes added to the face.
//   - Face reversal: ON_BrepFace::m_bRev -> reverse the OCCT face so its natural
//     normal matches the ON_Brep oriented normal.
//   - BRepLib::BuildCurves3d generates 3D curves from pcurves where needed.
//   - ShapeFix_Face is a tolerance/ordering safety net, NOT a corrector.

#include "SceneGraph/OnBrepToOcct.h"
#include "SceneGraph/OnBrepToOcct_internal.h"  // OCCT-aware accessor (defined below)

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
#include <gp_Pnt2d.hxx>
#include <Standard_TypeDef.hxx>
#include <NCollection_Array1.hxx>
#include <NCollection_Array2.hxx>
#include <TopLoc_Location.hxx>
#include <Geom_BSplineSurface.hxx>
#include <Geom_Surface.hxx>
#include <Geom2d_BSplineCurve.hxx>
#include <Geom2d_Curve.hxx>
#include <BRep_Builder.hxx>
#include <BRepBuilderAPI_MakeEdge.hxx>
#include <BRepBuilderAPI_MakeWire.hxx>
#include <BRepBuilderAPI_MakeFace.hxx>
#include <BRepLib.hxx>
#include <ShapeFix_Face.hxx>
#include <BRepGProp.hxx>
#include <GProp_GProps.hxx>
#include <Precision.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Edge.hxx>
#include <TopoDS_Wire.hxx>
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

// OCCT-aware internal accessor (declared in OnBrepToOcct_internal.h). Defined
// here where OcctFaceSet::Impl is a complete type. Additive; no behavior change.
const TopoDS_Face& OcctFaceAt(const OcctFaceSet& set, int slot) {
    return set.impl()->faces[static_cast<size_t>(slot)];
}

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

// Same clamped flat-knot expansion, but for an ON_NurbsCurve knot vector
// (length ncv+deg-1 -> OCCT wants ncv+deg+1: prepend first, append last).
void OcctCurveKnots(const ON_NurbsCurve& nc,
                    std::vector<double>& knots, std::vector<int>& mults)
{
    const int n = nc.KnotCount();
    std::vector<double> flat;
    flat.reserve(static_cast<size_t>(n) + 2);
    const double first = nc.Knot(0);
    const double last  = nc.Knot(n - 1);
    flat.push_back(first);
    for (int i = 0; i < n; ++i) flat.push_back(nc.Knot(i));
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

// Rebuild an openNURBS 2D parameter-space curve (a trim pcurve) as an OCCT
// Geom2d_BSplineCurve. The pcurve lives in the surface's (u,v) domain; openNURBS
// 2D control points are homogeneous (wx,wy,w) -> divide X/Y by W. Throws
// Standard_Failure / returns null on bad geometry (caller handles).
Handle(Geom2d_BSplineCurve) ToOcct2dCurve(const ON_NurbsCurve& nc)
{
    const int n = nc.CVCount();
    const int deg = nc.Degree();
    if (n < 2 || deg < 1) return Handle(Geom2d_BSplineCurve)();

    NCollection_Array1<gp_Pnt2d> poles(1, n);
    NCollection_Array1<double>   weights(1, n);

    for (int i = 0; i < n; ++i) {
        // GetCV in homogeneous form: (wx, wy, w) for a 2D rational curve.
        ON_4dPoint cp;
        nc.GetCV(i, cp);   // homogeneous CV; for dim=2, z is unused, w is weight
        double w = cp.w;
        if (w == 0.0) w = 1.0;
        poles.SetValue(i + 1, gp_Pnt2d(cp.x / w, cp.y / w));
        weights.SetValue(i + 1, w);
    }

    std::vector<double> ck;
    std::vector<int>    cm;
    OcctCurveKnots(nc, ck, cm);

    NCollection_Array1<double> CK(1, static_cast<int>(ck.size()));
    NCollection_Array1<int>    CM(1, static_cast<int>(cm.size()));
    for (int i = 0; i < static_cast<int>(ck.size()); ++i) { CK.SetValue(i + 1, ck[i]); CM.SetValue(i + 1, cm[i]); }

    return new Geom2d_BSplineCurve(poles, weights, CK, CM, deg, false);
}

double FaceArea(const TopoDS_Face& f)
{
    GProp_GProps props;
    BRepGProp::SurfaceProperties(f, props);
    return props.Mass();
}

// Build a single OCCT wire from one ON_BrepLoop, using the loop's trim pcurves on
// `surf`. Returns true with `outWire` set on success. Singular trims become OCCT
// degenerated edges; ordinary trims become pcurve-on-surface edges honoring
// m_bRev3d. Throws / returns false on unrecoverable trouble.
bool BuildLoopWire(const ON_Brep& brep, const ON_BrepLoop& loop,
                   const Handle(Geom_Surface)& surf, TopoDS_Wire& outWire)
{
    BRepBuilderAPI_MakeWire mkWire;
    int edgesAdded = 0;

    const int trimCount = loop.m_ti.Count();
    for (int k = 0; k < trimCount; ++k) {
        const int ti = loop.m_ti[k];
        if (ti < 0 || ti >= brep.m_T.Count()) continue;
        const ON_BrepTrim& trim = brep.m_T[ti];

        // Pull the 2D pcurve in surface (u,v) space.
        const ON_Curve* pc = trim.TrimCurveOf();
        if (!pc && trim.m_c2i >= 0 && trim.m_c2i < brep.m_C2.Count())
            pc = brep.m_C2[trim.m_c2i];

        if (trim.m_type == ON_BrepTrim::singular) {
            // Singular (collapsed) trim: the surface degenerates to a point along
            // this parameter-edge (e.g. a sphere/cone pole). Build a DEGENERATE
            // OCCT edge carrying the 2D pcurve on the surface but no 3D curve.
            // Dropping it would leave an open wire.
            if (!pc) continue;  // nothing to build from; skip (rare)
            ON_NurbsCurve nc;
            if (pc->GetNurbForm(nc) == 0) continue;
            Handle(Geom2d_BSplineCurve) c2d = ToOcct2dCurve(nc);
            if (c2d.IsNull()) continue;

            BRep_Builder bb;
            TopoDS_Edge de;
            bb.MakeEdge(de);
            // UpdateEdge(edge, pcurve2d, surface, location, tol): attaches the
            // 2D pcurve on the surface (no 3D curve — degenerate).
            bb.UpdateEdge(de, c2d, surf, TopLoc_Location(), Precision::Confusion());
            // The endpoints collapse to a single 3D vertex; set a small range and
            // mark degenerate so OCCT treats it as a pole edge.
            double t0 = c2d->FirstParameter();
            double t1 = c2d->LastParameter();
            bb.Range(de, t0, t1);
            bb.Degenerated(de, true);

            // NOTE: do NOT apply m_bRev3d here. m_bRev3d describes the 2D-trim vs
            // 3D-edge orientation relationship; the wire direction is governed by
            // the 2D pcurve, which openNURBS already orients for loop traversal
            // (outer CCW / inner CW in parameter space). The edge is built FROM
            // that pcurve, so it is already loop-directed — reversing by m_bRev3d
            // would double-account and break the wire (the "plausible-but-wrong"
            // trap). 3D-edge sense is irrelevant: we never build from 3D edges.
            mkWire.Add(de);
            if (mkWire.IsDone()) ++edgesAdded;
            continue;
        }

        // Ordinary / mated / seam / boundary trim: build a pcurve-on-surface edge.
        if (!pc) continue;
        ON_NurbsCurve nc;
        if (pc->GetNurbForm(nc) == 0) continue;
        Handle(Geom2d_BSplineCurve) c2d = ToOcct2dCurve(nc);
        if (c2d.IsNull()) continue;

        // Edge built FROM the 2D pcurve ON the surface (the 2D-on-surface ctor).
        BRepBuilderAPI_MakeEdge mkEdge(c2d, surf);
        if (!mkEdge.IsDone()) continue;
        TopoDS_Edge e = mkEdge.Edge();

        // NOTE: do NOT apply m_bRev3d. It is the 2D-trim-vs-3D-edge orientation
        // flag, NOT the loop direction. The loop direction is carried by the 2D
        // pcurve itself (openNURBS orients loop pcurves: outer CCW / inner CW in
        // parameter space). Since this edge is built FROM the pcurve, it already
        // runs in loop order; reversing by m_bRev3d would mis-direct the wire.
        // We never reproject from the 3D edge, so its sense never enters here.
        mkWire.Add(e);
        if (mkWire.IsDone()) ++edgesAdded;
    }

    if (edgesAdded == 0 || !mkWire.IsDone()) return false;
    outWire = mkWire.Wire();
    return true;
}

// Convert one ON_BrepFace to a trimmed, correctly-oriented OCCT face. Throws
// Standard_Failure on bad geometry (caller catches per-face). Returns a null face
// on a soft failure the caller should record.
TopoDS_Face ConvertOneFace(const ON_Brep& brep, const ON_BrepFace& face)
{
    // Analytic surface as a NURBS form (planes, spheres, NURBS, etc.).
    ON_NurbsSurface ns;
    if (face.GetNurbForm(ns) == 0) return TopoDS_Face();
    Handle(Geom_BSplineSurface) surf = ToOcctSurface(ns);
    if (surf.IsNull()) return TopoDS_Face();
    Handle(Geom_Surface) gsurf = surf;

    // Find the outer loop + collect inner (hole) loops. Skip non-area loop types
    // (slit / ptonsrf / crvonsrf are not area boundaries).
    TopoDS_Wire outerWire;
    bool haveOuter = false;
    std::vector<TopoDS_Wire> innerWires;

    const int loopCount = face.LoopCount();
    for (int li = 0; li < loopCount; ++li) {
        const ON_BrepLoop* loop = face.Loop(li);
        if (!loop) continue;

        if (loop->m_type == ON_BrepLoop::outer) {
            TopoDS_Wire w;
            if (BuildLoopWire(brep, *loop, gsurf, w)) {
                outerWire = w;
                haveOuter = true;
            }
        } else if (loop->m_type == ON_BrepLoop::inner) {
            TopoDS_Wire w;
            if (BuildLoopWire(brep, *loop, gsurf, w))
                innerWires.push_back(w);
        }
        // slit / ptonsrf / crvonsrf: not area boundaries -> ignore for area.
    }

    TopoDS_Face occtFace;
    if (haveOuter) {
        // Trimmed face: surface bounded by the outer wire.
        BRepBuilderAPI_MakeFace mk(gsurf, outerWire);
        if (!mk.IsDone()) {
            // Fall back to untrimmed rather than emit nothing — but this is a bug
            // signal; ShapeFix below cannot rescue a missing bound.
            return TopoDS_Face();
        }
        occtFace = mk.Face();

        // Subtract holes. MakeFace::Add expects inner wires whose orientation
        // (relative to the face) marks them as holes; ShapeFix_Face reconciles
        // wire orientation as a net.
        for (const TopoDS_Wire& hw : innerWires) {
            BRepBuilderAPI_MakeFace addMk(occtFace);
            addMk.Add(hw);
            if (addMk.IsDone()) occtFace = addMk.Face();
        }
    } else {
        // No usable outer loop -> fall back to the natural-bound full surface.
        BRepBuilderAPI_MakeFace mk(gsurf, Precision::Confusion());
        if (!mk.IsDone()) return TopoDS_Face();
        occtFace = mk.Face();
    }

    // Generate 3D curves from the pcurves where OCCT needs them.
    BRepLib::BuildCurves3d(occtFace);

    // Safety net for tolerance/ordering ONLY (NOT a corrector). Reconciles wire
    // ordering, missing pcurves, and hole orientation within tolerance.
    {
        ShapeFix_Face sff(occtFace);
        sff.Perform();
        occtFace = sff.Face();
    }

    // Face reversal: ON_BrepFace::m_bRev means the face normal is reversed vs the
    // surface normal. Reverse the OCCT face so its natural normal matches the
    // ON_Brep's oriented normal. (Required for Common() correctness downstream;
    // does not change area.)
    if (face.m_bRev)
        occtFace = TopoDS::Face(occtFace.Reversed());

    return occtFace;
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
            TopoDS_Face occtFace = ConvertOneFace(brep, face);
            if (occtFace.IsNull()) {
                impl->failed.push_back(fi);
                continue;
            }
            impl->faces.push_back(occtFace);
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
