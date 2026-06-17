"""
Spike D — ground the DIRECT ON_Brep -> OCCT converter (the recommended production
path) by rebuilding a real curved NURBS surface from rhino3dm (openNURBS) into an
OCCT Geom_BSplineSurface and checking the two evaluate to identical 3D points.
This proves the core NURBS translation a C++ ON_Surface->Geom converter would do.
"""
import rhino3dm as r3
from OCP.TColgp import TColgp_Array2OfPnt
from OCP.TColStd import TColStd_Array2OfReal, TColStd_Array1OfReal, TColStd_Array1OfInteger
from OCP.Geom import Geom_BSplineSurface
from OCP.gp import gp_Pnt

m = r3.File3dm.Read(r"C:\Users\aryan\Desktop\SpatialTest.3dm")
def getobj(gid):
    for o in m.Objects:
        if str(o.Attributes.Id)==gid: return o
brep = getobj("7d55840d-2516-4a78-9c7d-3a10152756b1").Geometry

def occt_knots(on_knots, degree, ncv):
    # openNURBS knot vec len = ncv+deg-1; OCCT flat len = ncv+deg+1.
    vals = [on_knots[i] for i in range(len(on_knots))]   # rhino3dm list has no neg-index
    flat = [vals[0]] + vals + [vals[-1]]
    # compress to distinct knots + multiplicities
    ks=[]; ms=[]
    for k in flat:
        if ks and abs(k-ks[-1])<1e-12: ms[-1]+=1
        else: ks.append(k); ms.append(1)
    return ks, ms

def to_occt_surface(ns):
    nu, nv = ns.Points.CountU, ns.Points.CountV
    du, dv = ns.Degree(0), ns.Degree(1)
    poles = TColgp_Array2OfPnt(1,nu,1,nv)
    weights = TColStd_Array2OfReal(1,nu,1,nv)
    rational=False
    for i in range(nu):
        for j in range(nv):
            cp = ns.Points.GetControlPoint(i,j)   # rhino3dm Point4d = HOMOGENEOUS (wx,wy,wz,w)
            w = cp.W if cp.W not in (0,None) else 1.0
            poles.SetValue(i+1,j+1, gp_Pnt(cp.X/w, cp.Y/w, cp.Z/w))  # -> euclidean for OCCT
            weights.SetValue(i+1,j+1, w)
            if abs(w-1.0)>1e-9: rational=True
    uk,um = occt_knots(ns.KnotsU, du, nu)
    vk,vm = occt_knots(ns.KnotsV, dv, nv)
    UK=TColStd_Array1OfReal(1,len(uk)); UM=TColStd_Array1OfInteger(1,len(um))
    VK=TColStd_Array1OfReal(1,len(vk)); VM=TColStd_Array1OfInteger(1,len(vm))
    for i,(k,mm) in enumerate(zip(uk,um)): UK.SetValue(i+1,k); UM.SetValue(i+1,mm)
    for i,(k,mm) in enumerate(zip(vk,vm)): VK.SetValue(i+1,k); VM.SetValue(i+1,mm)
    return Geom_BSplineSurface(poles, weights, UK, VK, UM, VM, du, dv, False, False), rational

maxdev=0.0; tested=0; rationals=0
for fi in range(len(brep.Faces)):
    ns = brep.Faces[fi].ToNurbsSurface()
    try:
        surf, rational = to_occt_surface(ns)
    except Exception as e:
        print(f"  face {fi}: CONVERT FAILED {type(e).__name__}: {e}"); continue
    if rational: rationals+=1
    du0=ns.Domain(0); dv0=ns.Domain(1)
    u0,u1=du0.T0,du0.T1; v0,v1=dv0.T0,dv0.T1
    fdev=0.0
    for a in range(6):
        for b in range(4):
            u = u0 + (u1-u0)*a/5.0
            v = v0 + (v1-v0)*b/3.0
            p_rh = ns.PointAt(u,v)
            p_oc = surf.Value(u,v)
            d = ((p_rh.X-p_oc.X())**2+(p_rh.Y-p_oc.Y())**2+(p_rh.Z-p_oc.Z())**2)**0.5
            fdev=max(fdev,d); maxdev=max(maxdev,d); tested+=1
    print(f"  face {fi}: deg {ns.Degree(0)}x{ns.Degree(1)} cv {ns.Points.CountU}x{ns.Points.CountV} rational={rational}  max point dev={fdev:.2e} mm")

print(f"\nfaces tested: {len(brep.Faces)}  rational faces: {rationals}  samples: {tested}")
print(f"MAX 3D point deviation rhino3dm vs OCCT-rebuilt surface: {maxdev:.3e} mm")
print("(<1e-6 mm => direct ON_Surface->Geom_BSplineSurface conversion is faithful)")
