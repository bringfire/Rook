"""
Strengthener 1 — direct-converter TRIMMED-FACE proof.

Spike D proved the SURFACE translation (ON NURBS surface -> OCCT Geom_BSplineSurface)
is machine-exact. This proves the TRIMMED FACE: build an OCCT trimmed face from a
real Rhino face's surface + its 3D edge curves (OCCT re-projects pcurves), and check
the trimmed-face AREA matches the STEP->OCCT ground truth (Spike A proved STEP faithful).

NOTE: rhino3dm does NOT expose pcurves/loops/trims (thin openNURBS subset), so this
spikes the 3D-edge-reproject strategy. The production C++ converter would use ON_Brep
pcurves directly (exact, no reprojection) — lower risk than what we test here, so a
PASS here bounds the harder path. Holes: this model has NO multi-loop faces (scan=0),
so hole separation is by-design (per-loop wires) not exercised here.
"""
import sys
import rhino3dm as r3
from OCP.STEPControl import STEPControl_Reader
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt
from OCP.TColgp import TColgp_Array2OfPnt, TColgp_Array1OfPnt
from OCP.TColStd import (TColStd_Array2OfReal, TColStd_Array1OfReal, TColStd_Array1OfInteger)
from OCP.Geom import Geom_BSplineSurface, Geom_BSplineCurve
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace)
from OCP.TopTools import TopTools_ListOfShape
from OCP.ShapeFix import ShapeFix_Face
from OCP.GeomProjLib import GeomProjLib
from OCP.BRepLib import BRepLib
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

STEPS = r"C:\Users\aryan\source\repos\rook-spatial\docs\rook_docs\occt-spike\steps"
F3DM  = r"C:\Users\aryan\Desktop\SpatialTest.3dm"

# ---------- openNURBS -> OCCT converters ----------
def _occt_knots(on_knots, ncv, deg):
    vals = [on_knots[i] for i in range(len(on_knots))]
    flat = [vals[0]] + vals + [vals[-1]]
    ks=[]; ms=[]
    for k in flat:
        if ks and abs(k-ks[-1])<1e-9: ms[-1]+=1
        else: ks.append(k); ms.append(1)
    return ks, ms

def surf_to_occt(ns):
    nu,nv = ns.Points.CountU, ns.Points.CountV
    du,dv = ns.Degree(0), ns.Degree(1)
    poles=TColgp_Array2OfPnt(1,nu,1,nv); wts=TColStd_Array2OfReal(1,nu,1,nv)
    for i in range(nu):
        for j in range(nv):
            cp=ns.Points.GetControlPoint(i,j); w=cp.W or 1.0
            poles.SetValue(i+1,j+1,gp_Pnt(cp.X/w,cp.Y/w,cp.Z/w)); wts.SetValue(i+1,j+1,w)
    uk,um=_occt_knots(ns.KnotsU,nu,du); vk,vm=_occt_knots(ns.KnotsV,nv,dv)
    UK=TColStd_Array1OfReal(1,len(uk)); UM=TColStd_Array1OfInteger(1,len(um))
    VK=TColStd_Array1OfReal(1,len(vk)); VM=TColStd_Array1OfInteger(1,len(vm))
    for i,(k,mm) in enumerate(zip(uk,um)): UK.SetValue(i+1,k); UM.SetValue(i+1,mm)
    for i,(k,mm) in enumerate(zip(vk,vm)): VK.SetValue(i+1,k); VM.SetValue(i+1,mm)
    return Geom_BSplineSurface(poles,wts,UK,VK,UM,VM,du,dv,False,False)

def curve_to_occt(nc):
    pts=nc.Points; n=len(pts); deg=nc.Degree
    poles=TColgp_Array1OfPnt(1,n); wts=TColStd_Array1OfReal(1,n)
    for i in range(n):
        cp=pts[i]; w=cp.W or 1.0
        poles.SetValue(i+1,gp_Pnt(cp.X/w,cp.Y/w,cp.Z/w)); wts.SetValue(i+1,w)
    ks,ms=_occt_knots(nc.Knots,n,deg)
    K=TColStd_Array1OfReal(1,len(ks)); M=TColStd_Array1OfInteger(1,len(ms))
    for i,(k,mm) in enumerate(zip(ks,ms)): K.SetValue(i+1,k); M.SetValue(i+1,mm)
    return Geom_BSplineCurve(poles,wts,K,M,deg,False)

def area(shape):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(shape,p); return p.Mass()

# ---------- direct-converter trimmed face from a rhino3dm BrepFace ----------
def convert_face_area(face):
    single = face.DuplicateFace(False)          # single-face brep: edges = this face's boundary
    occt_surf = surf_to_occt(single.Faces[0].ToNurbsSurface())
    edges = TopTools_ListOfShape()
    for e in single.Edges:
        gc = curve_to_occt(e.ToNurbsCurve())            # 3D edge curve
        pc = GeomProjLib.Curve2d_s(gc, occt_surf)       # project -> 2D pcurve on the surface
        me = BRepBuilderAPI_MakeEdge(pc, occt_surf)     # edge built FROM the pcurve (has 2D)
        if not me.IsDone(): continue
        ed = me.Edge()
        BRepLib.BuildCurves3d_s(ed)                     # add the 3D curve back
        edges.Append(ed)
    mw = BRepBuilderAPI_MakeWire()
    mw.Add(edges)                                # connect edges by shared endpoints (any order)
    if not mw.IsDone(): return None, "wire failed"
    mf = BRepBuilderAPI_MakeFace(occt_surf, mw.Wire(), True)
    if not mf.IsDone(): return None, "face failed"
    sf = ShapeFix_Face(mf.Face())
    sf.Perform()
    return area(sf.Face()), "ok"

# ---------- STEP ground truth (sum of an object's face surface areas) ----------
def step_total_surface_area(path):
    r=STEPControl_Reader(); r.ReadFile(path); r.TransferRoots(); s=r.OneShape()
    tot=0.0; e=TopExp_Explorer(s,TopAbs_FACE)
    while e.More(): tot+=area(TopoDS.Face_s(e.Current())); e.Next()
    return tot

def obj_by_id(model, gid):
    for o in model.Objects:
        if str(o.Attributes.Id)==gid: return o

m = r3.File3dm.Read(F3DM)
tests = [
    ("71065f57 planar wall", "71065f57-ee93-4af5-8a67-9aa1c4e88302", STEPS+r"\71065f57.stp"),
]
# curved wall ground truth from the all-model STEP (centroid-mapped); export per-object if needed.
print("=== Strengthener 1: trimmed-face direct converter vs STEP ground truth ===\n")
for label, gid, steppath in tests:
    obj = obj_by_id(m, gid); b = obj.Geometry
    conv_total=0.0; nfaces=0; fails=[]
    for fi in range(len(b.Faces)):
        a,stat = convert_face_area(b.Faces[fi])
        if a is None: fails.append((fi,stat)); continue
        conv_total += a; nfaces+=1
    gt = step_total_surface_area(steppath)
    print(f"{label}: faces={len(b.Faces)} converted={nfaces} fails={fails}")
    print(f"  direct-converter total trimmed-face area = {conv_total:.1f} mm^2")
    print(f"  STEP ground-truth total surface area      = {gt:.1f} mm^2")
    print(f"  ratio = {conv_total/gt:.5f}  (1.0 => trimmed faces faithful)\n")
