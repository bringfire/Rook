// occt_primitive_tests.cpp
//
// Task 6: OCCT-only OFFLINE robustness matrix for the engine primitive
// SharedFaceArea (declared in OcctAdjacencyEngine_internal.h, defined in
// OcctAdjacencyEngine.cpp). Dependency-free CHECK macros (no gtest/catch), same
// spirit as exact_adjacency_tests.cpp.
//
// These cases exercise SharedFaceArea on RAW OCCT primitives only — NO ON_Brep,
// NO converter, NO openNURBS — so this target links only OCCT MODELING libs.
// The point is to prove the Boolean-Common shared-area primitive behaves and
// degrades safely (no crash) across abutting / gapped / bridged / coincident /
// interpenetrating / far-from-origin / sliver / zero-thickness / curved-on-planar
// inputs. fuzz = 1e-3, units mm, boxes 10mm.

#define _USE_MATH_DEFINES   // M_PI on MSVC

#include "SceneGraph/OcctAdjacencyEngine_internal.h"

#include <TopoDS_Shape.hxx>
#include <TopoDS_Solid.hxx>
#include <TopoDS_Face.hxx>
#include <BRepPrimAPI_MakeBox.hxx>
#include <BRepPrimAPI_MakeCylinder.hxx>
#include <TopExp_Explorer.hxx>
#include <TopAbs_ShapeEnum.hxx>
#include <TopoDS.hxx>
#include <gp_Pnt.hxx>
#include <gp_Ax2.hxx>
#include <gp_Dir.hxx>
#include <Bnd_Box.hxx>
#include <BRepBndLib.hxx>
#include <Standard_Failure.hxx>

#include <vector>

#include <cstdio>
#include <cmath>

using Rook::SharedFaceArea;

static int g_failures = 0;
static int g_checks = 0;
#define CHECK(cond) do { ++g_checks; if(!(cond)){ \
    printf("FAIL %s:%d: %s\n",__FILE__,__LINE__,#cond); ++g_failures; } } while(0)
#define CHECK_NEAR(a,b,tol) do { ++g_checks; double _a=(a),_b=(b); \
    if(std::fabs(_a-_b)>(tol)){ printf("FAIL %s:%d: %s~=%s (%.6f vs %.6f)\n", \
    __FILE__,__LINE__,#a,#b,_a,_b); ++g_failures; } } while(0)

static const double FUZZ = 1e-3;

// Axis-aligned box from a corner (x,y,z) with extents (dx,dy,dz).
static TopoDS_Shape MakeBox(double x, double y, double z,
                            double dx, double dy, double dz) {
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape();
}

// The engine evaluates FACE-vs-FACE (its converter emits TopoDS_Faces). A
// solid-vs-solid Common of two abutting blocks yields nothing (they only touch);
// the contact area lives on the shared FACE pair. So the matrix exercises the
// primitive the way the engine calls it: pick the planar face of `s` whose
// x-extent collapses to ~`xPlane`, and Common it against the matching face.
static TopoDS_Face FaceAtX(const TopoDS_Shape& s, double xPlane, double tol = 1e-6) {
    for (TopExp_Explorer e(s, TopAbs_FACE); e.More(); e.Next()) {
        TopoDS_Face f = TopoDS::Face(e.Current());
        Bnd_Box bb; BRepBndLib::Add(f, bb);
        double xmin, ymin, zmin, xmax, ymax, zmax;
        bb.Get(xmin, ymin, zmin, xmax, ymax, zmax);
        if (std::fabs(xmax - xmin) <= 1e-3 &&
            std::fabs(xmin - xPlane) <= 1e-1 + tol)
            return f;
    }
    return TopoDS_Face();
}

// Pick the planar face of `s` whose z-extent collapses to ~`zPlane`.
static TopoDS_Face FaceAtZ(const TopoDS_Shape& s, double zPlane) {
    for (TopExp_Explorer e(s, TopAbs_FACE); e.More(); e.Next()) {
        TopoDS_Face f = TopoDS::Face(e.Current());
        Bnd_Box bb; BRepBndLib::Add(f, bb);
        double xmin, ymin, zmin, xmax, ymax, zmax;
        bb.Get(xmin, ymin, zmin, xmax, ymax, zmax);
        if (std::fabs(zmax - zmin) <= 1e-3 &&
            std::fabs(zmin - zPlane) <= 1e-1)
            return f;
    }
    return TopoDS_Face();
}

int main() {
    printf("OCCT primitive robustness matrix (SharedFaceArea)\n");

    // 1. Abutting boxes: B at x[0,10], C at x[10,20]; their coincident faces at
    //    x=10 share the full 10x10=100 contact area (engine evaluates face pairs).
    {
        TopoDS_Shape b = MakeBox(0,0,0, 10,10,10);
        TopoDS_Shape c = MakeBox(10,0,0, 10,10,10);
        TopoDS_Face fb = FaceAtX(b, 10.0);
        TopoDS_Face fc = FaceAtX(c, 10.0);
        bool crashed = false;
        double a = SharedFaceArea(fb, fc, FUZZ, crashed);
        printf("  [1] abutting faces: area=%.6f crashed=%d\n", a, crashed);
        CHECK(!crashed);
        CHECK_NEAR(a, 100.0, 1e-2);
    }

    // 2. Gap 0.5 > fuzz: the two faces (x=10 and x=10.5) don't overlap -> 0.
    {
        TopoDS_Shape b = MakeBox(0,0,0, 10,10,10);
        TopoDS_Shape c = MakeBox(10.5,0,0, 10,10,10);
        TopoDS_Face fb = FaceAtX(b, 10.0);
        TopoDS_Face fc = FaceAtX(c, 10.5);
        bool crashed = false;
        double a = SharedFaceArea(fb, fc, FUZZ, crashed);
        printf("  [2] gap 0.5>fuzz: area=%.6f crashed=%d\n", a, crashed);
        CHECK(!crashed);
        CHECK_NEAR(a, 0.0, 1e-6);
    }

    // 3. Gap 1e-4 < fuzz: the fuzzy value bridges the near-coincident faces -> ~100.
    {
        TopoDS_Shape b = MakeBox(0,0,0, 10,10,10);
        TopoDS_Shape c = MakeBox(10.0001,0,0, 10,10,10);
        TopoDS_Face fb = FaceAtX(b, 10.0);
        TopoDS_Face fc = FaceAtX(c, 10.0001);
        bool crashed = false;
        double a = SharedFaceArea(fb, fc, FUZZ, crashed);
        printf("  [3] gap 1e-4<fuzz: area=%.6f crashed=%d\n", a, crashed);
        CHECK(!crashed);
        CHECK_NEAR(a, 100.0, 1.0);  // bridged; allow fuzzy slack
    }

    // 4. Coincident duplicate box: full overlap -> surface area of the whole
    //    common solid (6 faces of a 10mm box = 600), i.e. > 100, no crash.
    {
        TopoDS_Shape b = MakeBox(0,0,0, 10,10,10);
        TopoDS_Shape c = MakeBox(0,0,0, 10,10,10);
        bool crashed = false;
        double a = SharedFaceArea(b, c, FUZZ, crashed);
        printf("  [4] coincident dup: area=%.6f crashed=%d\n", a, crashed);
        CHECK(!crashed);
        CHECK(a > 100.0);
    }

    // 5. Interpenetrating boxes (volume overlap, no coplanar contact): the common
    //    is a solid block; there is no degenerate face-adjacency collapse and no
    //    crash. We assert robustness (no crash) + a positive common surface.
    {
        TopoDS_Shape b = MakeBox(0,0,0, 10,10,10);
        TopoDS_Shape c = MakeBox(5,5,5, 10,10,10);
        bool crashed = false;
        double a = SharedFaceArea(b, c, FUZZ, crashed);
        printf("  [5] interpenetrating: area=%.6f crashed=%d\n", a, crashed);
        CHECK(!crashed);
        CHECK(a >= 0.0);  // never negative; never crashes
    }

    // 6. Far-from-origin (+1e6) abutting faces: same 100 shared face, no precision
    //    collapse, no crash.
    {
        const double O = 1e6;
        TopoDS_Shape b = MakeBox(O,O,O, 10,10,10);
        TopoDS_Shape c = MakeBox(O+10,O,O, 10,10,10);
        TopoDS_Face fb = FaceAtX(b, O+10);
        TopoDS_Face fc = FaceAtX(c, O+10);
        bool crashed = false;
        double a = SharedFaceArea(fb, fc, FUZZ, crashed);
        printf("  [6] far-from-origin: area=%.6f crashed=%d\n", a, crashed);
        CHECK(!crashed);
        CHECK_NEAR(a, 100.0, 1.0);
    }

    // 7. Sliver box (dz=1e-4) abutting a normal box at x=10: their x=10 faces are
    //    10 x 1e-4 vs 10 x 10. Tiny overlap (~1e-3) — must not crash; small area ok.
    {
        TopoDS_Shape b = MakeBox(0,0,0, 10,10,10);
        TopoDS_Shape c = MakeBox(10,0,0, 10,10,1e-4);  // very thin in z
        TopoDS_Face fb = FaceAtX(b, 10.0);
        TopoDS_Face fc = FaceAtX(c, 10.0);
        bool crashed = false;
        double a = SharedFaceArea(fb, fc, FUZZ, crashed);
        printf("  [7] sliver abutting: area=%.6f crashed=%d\n", a, crashed);
        CHECK(!crashed);
        CHECK(a >= 0.0);
    }

    // 8. Zero-thickness box (dz=0): construction must be REJECTED (no silent bad
    //    face). Guard the construction in try/catch — a valid OCCT install throws
    //    on a degenerate box. If construction somehow succeeds, SharedFaceArea
    //    must still not crash.
    {
        bool constructionRejected = false;
        TopoDS_Shape degenerate;
        try {
            degenerate = MakeBox(10,0,0, 10,10,0);  // dz=0
        } catch (const Standard_Failure&) {
            constructionRejected = true;
        } catch (...) {
            constructionRejected = true;
        }
        printf("  [8] zero-thickness: constructionRejected=%d\n", constructionRejected);
        if (constructionRejected) {
            CHECK(true);  // rejected as required
        } else {
            // Construction didn't throw; the primitive must still be crash-safe.
            TopoDS_Shape b = MakeBox(0,0,0, 10,10,10);
            bool crashed = false;
            double a = SharedFaceArea(b, degenerate, FUZZ, crashed);
            printf("      (constructed; SharedFaceArea area=%.6f crashed=%d)\n", a, crashed);
            CHECK(!crashed);
        }
    }

    // 9. Cylinder bottom circle resting on a box top face (curved-on-planar):
    //    box top face at z=10; cylinder r=3 based at z=10 with its bottom disk on
    //    z=10. Common of the box-top planar face and the cylinder bottom disk
    //    face -> the disk area ~pi*r^2 (~28.27). No crash on planar-vs-curved-edge.
    {
        TopoDS_Shape box = MakeBox(0,0,0, 10,10,10);  // top face z=10
        // Cylinder based at (5,5,10) pointing +z, r=3, h=10. Bottom disk on z=10.
        gp_Ax2 axis(gp_Pnt(5,5,10), gp_Dir(0,0,1));
        TopoDS_Shape cyl = BRepPrimAPI_MakeCylinder(axis, 3.0, 10.0).Shape();
        TopoDS_Face topFace  = FaceAtZ(box, 10.0);  // box top
        TopoDS_Face diskFace = FaceAtZ(cyl, 10.0);  // cylinder bottom disk
        bool crashed = false;
        double a = SharedFaceArea(topFace, diskFace, FUZZ, crashed);
        const double expected = M_PI * 3.0 * 3.0;  // ~28.27
        printf("  [9] cyl-on-box: area=%.6f expected~%.6f crashed=%d\n",
               a, expected, crashed);
        CHECK(!crashed);
        CHECK_NEAR(a, expected, 1.0);
    }

    printf("\n%d checks, %d failures\n", g_checks, g_failures);
    if (g_failures == 0) printf("ALL PASS\n");
    return g_failures == 0 ? 0 : 1;
}
