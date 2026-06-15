// OcctProbe.cpp
//
// Spike G tracer implementation. OCCT-ONLY translation unit: includes no Rhino SDK,
// no stdafx.h (NotUsing PCH in the vcxproj). Proves OCCT links + initializes +
// runs BRepAlgoAPI_Common inside the RookNative process. The Common-over-face-pairs
// logic is the exact Spike-A primitive, now in-plugin.
#include "SceneGraph/OcctProbe.h"

#include <STEPControl_Reader.hxx>
#include <IFSelect_ReturnStatus.hxx>
#include <BRepAlgoAPI_Common.hxx>
#include <GProp_GProps.hxx>
#include <BRepGProp.hxx>
#include <TopExp_Explorer.hxx>
#include <TopAbs_ShapeEnum.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Shape.hxx>
#include <TopoDS_Face.hxx>
#include <NCollection_List.hxx>   // OCCT 8.0 moved TopTools_ListOfShape alias to Deprecated/; use the underlying type
#include <OSD.hxx>

#include <vector>
#include <string>

namespace Rook {

void OcctProbeInit()
{
    // Signal/exception handling setup for OCCT in this process. Idempotent in
    // practice; safe to call once at first probe.
    OSD::SetSignal(Standard_False);
}

static double SurfaceArea(const TopoDS_Shape& s)
{
    GProp_GProps props;
    BRepGProp::SurfaceProperties(s, props);
    return props.Mass();
}

static TopoDS_Shape ReadStep(const std::string& path, bool& ok)
{
    STEPControl_Reader reader;
    ok = (reader.ReadFile(path.c_str()) == IFSelect_RetDone);
    if (!ok) return TopoDS_Shape();
    reader.TransferRoots();
    return reader.OneShape();
}

double OcctProbeSharedArea(const std::string& stepA, const std::string& stepB, std::string& diag)
{
    bool okA = false, okB = false;
    TopoDS_Shape a = ReadStep(stepA, okA);
    if (!okA) { diag = "read A failed: " + stepA; return -1.0; }
    TopoDS_Shape b = ReadStep(stepB, okB);
    if (!okB) { diag = "read B failed: " + stepB; return -1.0; }

    std::vector<TopoDS_Face> fa, fb;
    for (TopExp_Explorer e(a, TopAbs_FACE); e.More(); e.Next())
        fa.push_back(TopoDS::Face(e.Current()));
    for (TopExp_Explorer e(b, TopAbs_FACE); e.More(); e.Next())
        fb.push_back(TopoDS::Face(e.Current()));

    double total = 0.0;
    int pairs = 0;
    for (const TopoDS_Face& x : fa) {
        for (const TopoDS_Face& y : fb) {
            try {
                BRepAlgoAPI_Common op;
                NCollection_List<TopoDS_Shape> la, lb;
                la.Append(x); lb.Append(y);
                op.SetArguments(la); op.SetTools(lb);
                op.SetFuzzyValue(1e-3);
                op.Build();
                if (!op.HasErrors()) {
                    double ar = SurfaceArea(op.Shape());
                    if (ar > 1e-9) { total += ar; ++pairs; }
                }
            } catch (...) {
                // OCCT can throw Standard_Failure; swallow per-pair (engine policy).
            }
        }
    }
    diag = "facesA=" + std::to_string(fa.size()) +
           " facesB=" + std::to_string(fb.size()) +
           " overlapPairs=" + std::to_string(pairs);
    return total;
}

} // namespace Rook
