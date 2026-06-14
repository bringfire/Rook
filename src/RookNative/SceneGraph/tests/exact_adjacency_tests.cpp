// exact_adjacency_tests.cpp
//
// Dependency-free (no gtest/catch) standalone test harness for the Gate 4 exact
// planar-adjacency engine. TDD RED: these cases describe the behaviour Task 4's
// PlanarAdjacencyEngine::Evaluate must satisfy. The standalone test target links
// only this TU + clipper.engine.cpp; until Task 4 defines Evaluate, the build
// FAILS at LINK with an unresolved external for Rook::PlanarAdjacencyEngine::Evaluate.
// That link failure is the passing RED state for Task 3.
//
// ── Conventions asserted here (Task 4 MUST match) ───────────────────────────
//
// SIGN-FOLDING (canonicalPlane): A plane {nx,ny,nz,d} (n·p = d for points p on
//   the plane) is folded so the FIRST nonzero component of the normal, scanned in
//   the order (nx, ny, nz), is POSITIVE. If that leading component is negative,
//   negate the whole 4-tuple (n and d together). The normal is unit-length. This
//   makes two OPPOSING faces that lie on the same geometric plane produce the
//   SAME canonicalPlane (used for coplanar grouping only — the opposing-normal
//   test uses the ORIGINAL outwardNormal, not the canonical one).
//   Example: a face at x=1 has geometric plane n=(1,0,0), d=1 -> canonical
//   {1,0,0,1}; the opposing face (outward normal (-1,0,0)) on the same x=1 plane
//   has raw {-1,0,0,-1} -> folded to {1,0,0,1}. Identical => coplanar.
//
// CAPABILITY MIN-ELIGIBILITY: "min eligibility" means LEAST capable = the LARGER
//   enum value (ExactPlanar(0) < PartialExactUnsupported(1) <
//   CoarseFallbackExactUnsupported(2) < UnsupportedGeometry(3) <
//   FailedWithDiagnostics(4)). The combined candidate capability and the
//   reported sourceCapability are therefore the MAX of the two enum values.
//   combine(a,b) = static_cast<Capability>(max((int)a,(int)b)).

#include "SceneGraph/PlanarAdjacencyEngine.h"
#include <cstdio>
#include <cmath>
#include <vector>
#include <array>
#include <string>
using namespace Rook;

static int g_failures = 0;
#define CHECK(cond) do { if(!(cond)){ printf("FAIL %s:%d: %s\n",__FILE__,__LINE__,#cond); ++g_failures; } } while(0)
static bool approx(double a, double b, double tol=1e-6){ return std::fabs(a-b) <= tol; }
#define CHECK_NEAR(a,b,tol) do { double _a=(a),_b=(b); if(std::fabs(_a-_b)>(tol)){ printf("FAIL %s:%d: %s~=%s (%.9f vs %.9f)\n",__FILE__,__LINE__,#a,#b,_a,_b); ++g_failures; } } while(0)

// ── Geometry helpers ────────────────────────────────────────────────────────

using P3 = std::array<double,3>;
using Loop = std::vector<P3>;

// Sign-fold a plane {nx,ny,nz,d} so the first nonzero normal component is
// positive (scan order nx,ny,nz). See header comment. Normal assumed unit.
static std::array<double,4> foldPlane(double nx, double ny, double nz, double d) {
    double lead = 0.0;
    if (std::fabs(nx) > 1e-12)      lead = nx;
    else if (std::fabs(ny) > 1e-12) lead = ny;
    else if (std::fabs(nz) > 1e-12) lead = nz;
    double s = (lead < 0.0) ? -1.0 : 1.0;
    return { nx*s, ny*s, nz*s, d*s };
}

// Build a single arbitrary planar face object. The canonicalPlane is derived
// from (normal, first loop point): d = n . p0, then sign-folded.
static ObjectFaceSummary makeFaceObject(
        const std::string& id,
        const P3& normal,
        const std::vector<Loop>& loops,           // loops[0]=outer, [1..]=holes
        Capability capability = Capability::ExactPlanar,
        FaceKind kind = FaceKind::Planar) {
    ObjectFaceSummary o;
    o.objectId = id;
    o.capability = capability;
    FaceSummary fs;
    fs.kind = kind;
    fs.planar.outwardNormal = normal;
    // canonical plane offset from the first outer-loop point
    const P3& p0 = loops.at(0).at(0);
    double d = normal[0]*p0[0] + normal[1]*p0[1] + normal[2]*p0[2];
    fs.planar.canonicalPlane = foldPlane(normal[0], normal[1], normal[2], d);
    fs.planar.loops = loops;
    o.faces.push_back(fs);
    return o;
}

// Build a 6-face axis-aligned box ObjectFaceSummary (capability ExactPlanar,
// every face Planar). Each face's loops[0] is the 4 corners CCW w.r.t. the
// OUTWARD normal (right-hand rule), no holes.
static ObjectFaceSummary makeBox(const std::string& id, const double mn[3], const double mx[3]) {
    ObjectFaceSummary o;
    o.objectId = id;
    o.capability = Capability::ExactPlanar;

    auto addFace = [&](const P3& n, const Loop& loop) {
        FaceSummary fs;
        fs.kind = FaceKind::Planar;
        fs.planar.outwardNormal = n;
        double d = n[0]*loop[0][0] + n[1]*loop[0][1] + n[2]*loop[0][2];
        fs.planar.canonicalPlane = foldPlane(n[0], n[1], n[2], d);
        fs.planar.loops = { loop };
        o.faces.push_back(fs);
    };

    const double x0=mn[0], y0=mn[1], z0=mn[2];
    const double x1=mx[0], y1=mx[1], z1=mx[2];

    // For each face, the corner order is CCW when viewed from OUTSIDE (looking
    // back along the outward normal toward the solid), i.e. right-handed about n.

    // -X face (normal (-1,0,0)): in-plane axes for CCW about (-1,0,0) are (Z then Y)
    //   sequence z0,z1 with y... we build explicitly and trust CCW-about-n.
    addFace({-1,0,0}, { {x0,y0,z0},{x0,y0,z1},{x0,y1,z1},{x0,y1,z0} });
    // +X face (normal (+1,0,0)): CCW about +X is Y->Z
    addFace({ 1,0,0}, { {x1,y0,z0},{x1,y1,z0},{x1,y1,z1},{x1,y0,z1} });
    // -Y face (normal (0,-1,0)): CCW about -Y is X->Z
    addFace({0,-1,0}, { {x0,y0,z0},{x1,y0,z0},{x1,y0,z1},{x0,y0,z1} });
    // +Y face (normal (0,+1,0)): CCW about +Y is Z->X
    addFace({0, 1,0}, { {x0,y1,z0},{x0,y1,z1},{x1,y1,z1},{x1,y1,z0} });
    // -Z face (normal (0,0,-1)): CCW about -Z is Y->X
    addFace({0,0,-1}, { {x0,y0,z0},{x0,y1,z0},{x1,y1,z0},{x1,y0,z0} });
    // +Z face (normal (0,0,+1)): CCW about +Z is X->Y
    addFace({0,0, 1}, { {x0,y0,z1},{x1,y0,z1},{x1,y1,z1},{x0,y1,z1} });

    return o;
}

// Build a single planar face object on plane x=k with a given normal, where the
// face lies in the y-z plane; (y,z) pairs are mapped to world (k, y, z).
// outer + optional holes given as lists of (y,z) pairs.
static ObjectFaceSummary makeYZFaceAtX(
        const std::string& id, double k, const P3& normal,
        const std::vector<std::vector<std::array<double,2>>>& yzLoops,
        Capability capability = Capability::ExactPlanar) {
    std::vector<Loop> loops;
    for (const auto& yz : yzLoops) {
        Loop loop;
        for (const auto& p : yz) loop.push_back({ k, p[0], p[1] });
        loops.push_back(loop);
    }
    return makeFaceObject(id, normal, loops, capability, FaceKind::Planar);
}

// Find a candidate entry by id in an ExactAdjacencyCore.
static const ExactCandidate* findCandidate(const ExactAdjacencyCore& r, const std::string& id) {
    for (const auto& c : r.candidates) if (c.id == id) return &c;
    return nullptr;
}

// ── Test cases (spec §11) ────────────────────────────────────────────────────

// test_a — full shared face. A=[0,0,0]..[1,1,1], B=[1,0,0]..[2,1,1].
// Shared plane x=1: A +X normal (+1,0,0), B -X normal (-1,0,0) -> opposing.
// Overlap = 1x1 square = 1.0.
static void test_a() {
    double amn[3]={0,0,0}, amx[3]={1,1,1};
    double bmn[3]={1,0,0}, bmx[3]={2,1,1};
    ObjectFaceSummary A = makeBox("A", amn, amx);
    ObjectFaceSummary B = makeBox("B", bmn, bmx);
    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 1);
    if (r.edges.size() == 1) {
        CHECK(r.edges[0].targetId == "B");
        CHECK_NEAR(r.edges[0].sharedArea, 1.0, 1e-6);
    }
    CHECK(r.sourceCapability == Capability::ExactPlanar);
    const ExactCandidate* cb = findCandidate(r, "B");
    CHECK(cb != nullptr);
    if (cb) CHECK(cb->capability == Capability::ExactPlanar);
}

// test_b — same-normal coplanar (no edge). Two 1x1 squares on z=0, BOTH with
// outward normal (0,0,+1) (co-facing duplicates), overlapping fully. The
// opposing-normal gate fails (dot=+1, not < -(1-tol)) -> 0 edges.
static void test_b() {
    std::vector<Loop> sq = { { {0,0,0},{1,0,0},{1,1,0},{0,1,0} } };
    ObjectFaceSummary A = makeFaceObject("A", {0,0,1}, sq);
    ObjectFaceSummary B = makeFaceObject("B", {0,0,1}, sq);
    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 0);
}

// test_c — partial overlap (small on large). A 4x4 on x=1 normal (+1,0,0),
// y,z in [0,4]. B 1x1 on x=1 normal (-1,0,0), y,z in [1,2] (inside A).
// Opposing + coplanar -> 1 edge, area 1.0.
static void test_c() {
    ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0},
        { { {0,0},{4,0},{4,4},{0,4} } });
    ObjectFaceSummary B = makeYZFaceAtX("B", 1.0, {-1,0,0},
        { { {1,1},{2,1},{2,2},{1,2} } });
    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 1);
    if (r.edges.size() == 1) CHECK_NEAR(r.edges[0].sharedArea, 1.0, 1e-6);
}

// test_d — 150mm gap (no edge). A on plane x=1 normal (+1,0,0); B on plane
// x=1.15 normal (-1,0,0). 0.15 model-unit gap -> different canonicalPlane.
// Expect 0 edges.
static void test_d() {
    ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0},
        { { {0,0},{4,0},{4,4},{0,4} } });
    ObjectFaceSummary B = makeYZFaceAtX("B", 1.15, {-1,0,0},
        { { {0,0},{4,0},{4,4},{0,4} } });
    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 0);
}

// test_e — hole-aware net area. A on x=1 normal (+1,0,0): OUTER 4x4 (y,z in
// [0,4]) with ONE hole 2x2 (y,z in [1,3]). B solid 4x4 on x=1 normal (-1,0,0).
// Net overlap = 16 - 4 = 12.0 (proves Clipper2 hole subtraction).
static void test_e() {
    ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0}, {
        { {0,0},{4,0},{4,4},{0,4} },   // outer 4x4
        { {1,1},{3,1},{3,3},{1,3} }    // hole 2x2
    });
    ObjectFaceSummary B = makeYZFaceAtX("B", 1.0, {-1,0,0},
        { { {0,0},{4,0},{4,4},{0,4} } });
    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 1);
    if (r.edges.size() == 1) CHECK_NEAR(r.edges[0].sharedArea, 12.0, 1e-6);
}

// test_f — concave L-shape. A L-shape on x=1 normal (+1,0,0): outer loop =
// 4x4 square with a 2x2 corner removed (area 12), points (y,z):
// (0,0)->(4,0)->(4,4)->(2,4)->(2,2)->(0,2). B identical L-shape on x=1 normal
// (-1,0,0). Full overlap = 12.0.
static void test_f() {
    std::vector<std::array<double,2>> L =
        { {0,0},{4,0},{4,4},{2,4},{2,2},{0,2} };
    ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0}, { L });
    ObjectFaceSummary B = makeYZFaceAtX("B", 1.0, {-1,0,0}, { L });
    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 1);
    if (r.edges.size() == 1) CHECK_NEAR(r.edges[0].sharedArea, 12.0, 1e-6);
}

// test_g — mixed planar+curved object (capability respected, planar still
// evaluated). A = ObjectFaceSummary PRE-SET capability PartialExactUnsupported,
// faces = [ Planar face on x=1 normal (+1,0,0) 1x1, one Curved face (planar
// ignored) ], diagnostics ["curved"]. B = planar face opposing on x=1,
// capability ExactPlanar. Expect: planar pair STILL yields 1 edge area 1.0;
// candidate B combined capability = combine(Partial, Exact) = Partial (worst);
// sourceCapability == PartialExactUnsupported.
static void test_g() {
    // A: build the planar face, then append a curved face and downgrade cap.
    ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0},
        { { {0,0},{1,0},{1,1},{0,1} } }, Capability::PartialExactUnsupported);
    FaceSummary curved;
    curved.kind = FaceKind::Curved;          // planar member left default/ignored
    A.faces.push_back(curved);
    A.diagnostics.push_back("curved");

    ObjectFaceSummary B = makeYZFaceAtX("B", 1.0, {-1,0,0},
        { { {0,0},{1,0},{1,1},{0,1} } }, Capability::ExactPlanar);

    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 1);
    if (r.edges.size() == 1) CHECK_NEAR(r.edges[0].sharedArea, 1.0, 1e-6);
    CHECK(r.sourceCapability == Capability::PartialExactUnsupported);
    const ExactCandidate* cb = findCandidate(r, "B");
    CHECK(cb != nullptr);
    if (cb) CHECK(cb->capability == Capability::PartialExactUnsupported);
}

// test_h — corner-only touch -> no edge (spec §11). Two opposing coplanar faces
// on plane x=1. A occupies (y,z) in [0,1]x[0,1]; B occupies (y,z) in [1,2]x[1,2].
// They meet ONLY at the single corner point (1,1). Boolean intersection area = 0
// -> no edge. Coordinates kept small/near origin.
static void test_h() {
    ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0},
        { { {0,0},{1,0},{1,1},{0,1} } });          // [0,1] x [0,1]
    ObjectFaceSummary B = makeYZFaceAtX("B", 1.0, {-1,0,0},
        { { {1,1},{2,1},{2,2},{1,2} } });          // [1,2] x [1,2], touches at (1,1)
    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 0);
}

// test_i — near-contact precision boundary (spec §11). Two parts:
//  (1) NO spurious area: A on x=1 (y in [0,1]); B opposing on x=1 (y in [1.001,2]).
//      The projected outlines are separated by a 0.001 gap (above the 6-decimal
//      precision floor). They do NOT overlap -> 0 edges.
//  (2) GENUINE tiny overlap: B' on x=1 (y in [0.999,2]) overlaps A in a strip
//      0.001 wide (y in [0.999,1]) x 1 tall = 0.001 area > kAreaTol(1e-6) ->
//      1 edge with sharedArea ~= 0.001. Coordinates kept small/near origin.
static void test_i() {
    // (1) tiny gap -> no overlap.
    {
        ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0},
            { { {0,0},{1,0},{1,1},{0,1} } });               // y in [0,1], z in [0,1]
        ObjectFaceSummary B = makeYZFaceAtX("B", 1.0, {-1,0,0},
            { { {1.001,0},{2,0},{2,1},{1.001,1} } });       // y in [1.001,2]
        PlanarAdjacencyEngine eng;
        ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
        CHECK(r.edges.size() == 0);
    }
    // (2) genuine 0.001-wide overlap strip -> edge with area ~0.001.
    {
        ObjectFaceSummary A = makeYZFaceAtX("A", 1.0, {1,0,0},
            { { {0,0},{1,0},{1,1},{0,1} } });               // y in [0,1], z in [0,1]
        ObjectFaceSummary B = makeYZFaceAtX("B", 1.0, {-1,0,0},
            { { {0.999,0},{2,0},{2,1},{0.999,1} } });       // y in [0.999,2]
        PlanarAdjacencyEngine eng;
        ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
        CHECK(r.edges.size() == 1);
        if (r.edges.size() == 1) CHECK_NEAR(r.edges[0].sharedArea, 0.001, 1e-6);
    }
}

// test_j — TILTED (non-axis-aligned) plane end-to-end. All other cases use
// axis-aligned planes ({±1,0,0} etc.); this exercises the projection/basis/area
// math on a real-world angled plane (angled walls / sloped slabs).
//
// Plane normal n = (s, s, 0) with s = 1/sqrt(2) — a 45° plane through the world
// origin. In-plane orthonormal axes: e1 = (-s, s, 0) (perpendicular to n, in XY),
// e2 = (0,0,1). A unit square (side 1, area 1) centered at the origin has corners
// O + a*e1 + b*e2 for (a,b) in {(-.5,-.5),(.5,-.5),(.5,.5),(-.5,.5)}.
//
// Faces A and B use these SAME 4 coplanar corner points but opposite outward
// normals (A: +n, B: -n). Sign-folding maps +n and -n to the identical
// canonicalPlane (n leads with +s -> stays; -n leads with -s -> negated to +n),
// so they are coplanar; the opposing-normal gate uses the raw normals -> opposing.
// Full overlap => exactly 1 edge with sharedArea ≈ 1.0 (the square's true area).
static void test_j() {
    const double s = 1.0 / std::sqrt(2.0);
    const P3 e1 = { -s, s, 0.0 };   // in-plane, perpendicular to n, in XY plane
    const P3 e2 = { 0.0, 0.0, 1.0 };
    auto corner = [&](double a, double b) -> P3 {
        return { a * e1[0] + b * e2[0],
                 a * e1[1] + b * e2[1],
                 a * e1[2] + b * e2[2] };
    };
    Loop sq = { corner(-0.5, -0.5), corner(0.5, -0.5),
                corner(0.5, 0.5),  corner(-0.5, 0.5) };

    ObjectFaceSummary A = makeFaceObject("A", { s, s, 0.0 }, { sq });
    ObjectFaceSummary B = makeFaceObject("B", { -s, -s, 0.0 }, { sq });

    PlanarAdjacencyEngine eng;
    ExactAdjacencyCore r = eng.Evaluate(A, { B }, 1e-3);
    CHECK(r.edges.size() == 1);
    if (r.edges.size() == 1) CHECK_NEAR(r.edges[0].sharedArea, 1.0, 1e-6);
}

int main(){
    test_a(); test_b(); test_c(); test_d(); test_e(); test_f(); test_g();
    test_h(); test_i(); test_j();
    printf("%d failure(s)\n", g_failures);
    return g_failures ? 1 : 0;
}
