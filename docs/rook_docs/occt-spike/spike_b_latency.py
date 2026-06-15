"""
Spike B — latency / scale. Reuses the Spike-A mapping. Times:
  (1) per-object lazy adjacency query (object vs its broad-phase bbox-candidates)
  (2) full-model batch (every object)
with a realistic face-bbox + coplanar prefilter before each Common (what a sane
engine does). NOTE: OCP/Python is a PESSIMISTIC UPPER BOUND; production C++ OCCT
is faster. Decision: is lazy-per-object fine, and is batch tolerable, or do we
need the planar accelerator?
"""
import json, urllib.request, time
from OCP.STEPControl import STEPControl_Reader
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID, TopAbs_SHELL
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_ListOfShape
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane

STEP=r"C:\Users\aryan\source\repos\rook-spatial\docs\rook_docs\occt-spike\steps\spatialtest_all.stp"
MM_PER_IN=25.4

def post(p,b):
    r=urllib.request.Request("http://localhost:63762"+p,data=json.dumps(b).encode(),method="POST",headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=60) as x: return json.loads(x.read().decode())

nodes=post("/scene/graph/query",{"depth":"full"})["data"]["nodes"]
if isinstance(nodes,dict): nodes=list(nodes.values())
for n in nodes:
    mn,mx=n["bboxMin"],n["bboxMax"]
    n["_min"]=[mn[i]*MM_PER_IN for i in range(3)]; n["_max"]=[mx[i]*MM_PER_IN for i in range(3)]
    n["_vol"]=max(1e-9,(mx[0]-mn[0])*(mx[1]-mn[1])*(mx[2]-mn[2]))

def faces_of(s):
    o=[]; e=TopExp_Explorer(s,TopAbs_FACE)
    while e.More(): o.append(TopoDS.Face_s(e.Current())); e.Next()
    return o
def area(s):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(s,p); return p.Mass()
def vcom(s):
    p=GProp_GProps(); BRepGProp.VolumeProperties_s(s,p); c=p.CentreOfMass(); return (c.X(),c.Y(),c.Z())
def scom(s):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(s,p); c=p.CentreOfMass(); return (c.X(),c.Y(),c.Z())
def fbb(f):
    bb=Bnd_Box(); BRepBndLib.Add_s(f,bb); a=bb.CornerMin(); b=bb.CornerMax(); return (a.X(),a.Y(),a.Z(),b.X(),b.Y(),b.Z())
def fplane(f):
    s=BRepAdaptor_Surface(f)
    if s.GetType()==GeomAbs_Plane:
        pl=s.Plane(); ax=pl.Axis(); d=ax.Direction(); loc=pl.Location()
        nx,ny,nz=d.X(),d.Y(),d.Z(); off=nx*loc.X()+ny*loc.Y()+nz*loc.Z()
        # sign-fold
        lead = nx if abs(nx)>1e-9 else (ny if abs(ny)>1e-9 else nz)
        sgn = -1.0 if lead<0 else 1.0
        return (round(nx*sgn,5),round(ny*sgn,5),round(nz*sgn,5),round(off*sgn,2))
    return None  # curved

def assign(c):
    best=None; bv=1e30; m=0.5*MM_PER_IN
    for n in nodes:
        mn,mx=n["_min"],n["_max"]
        if all(mn[i]-m<=c[i]<=mx[i]+m for i in range(3)) and n["_vol"]<bv: bv=n["_vol"]; best=n["id"]
    return best

t0=time.time()
r=STEPControl_Reader(); r.ReadFile(STEP); r.TransferRoots(); root=r.OneShape()
obj={}  # guid -> list[(face, fbbox, plane)]
seen={}
def add(shape,com):
    g=assign(com)
    if not g: return
    obj.setdefault(g,[]); seen.setdefault(g,set())
    for f in faces_of(shape):
        p=GProp_GProps(); BRepGProp.SurfaceProperties_s(f,p); cc=p.CentreOfMass()
        sig=(round(p.Mass(),3),round(cc.X(),2),round(cc.Y(),2),round(cc.Z(),2))
        if sig in seen[g]: continue
        seen[g].add(sig); obj[g].append((f,fbb(f),fplane(f)))
e=TopExp_Explorer(root,TopAbs_SOLID)
while e.More(): s=TopoDS.Solid_s(e.Current()); add(s,vcom(s)); e.Next()
e=TopExp_Explorer(root,TopAbs_SHELL)
while e.More(): s=TopoDS.Shell_s(e.Current()); add(s,scom(s)); e.Next()
print(f"map+load: {time.time()-t0:.2f}s; mapped {sum(1 for g in obj if obj[g])}/{len(nodes)}")

PLANE_TOL=0.05  # mm offset tol for coplanar prefilter (loose)
def coplanar(pa,pb):
    if pa is None or pb is None: return True  # curved -> can't prefilter, must test
    return abs(pa[0]-pb[0])<1e-3 and abs(pa[1]-pb[1])<1e-3 and abs(pa[2]-pb[2])<1e-3 and abs(pa[3]-pb[3])<=PLANE_TOL*MM_PER_IN
def fcommon(fa,fb,fuzz=1e-3):
    try:
        op=BRepAlgoAPI_Common(); la=TopTools_ListOfShape(); la.Append(fa); lb=TopTools_ListOfShape(); lb.Append(fb)
        op.SetArguments(la); op.SetTools(lb); op.SetFuzzyValue(fuzz); op.Build(); return area(op.Shape())
    except Exception: return 0.0
def bbov(b1,b2,m=5.0):
    return (b1[0]<=b2[3]+m and b2[0]<=b1[3]+m and b1[1]<=b2[4]+m and b2[1]<=b1[4]+m and b1[2]<=b2[5]+m and b2[2]<=b1[5]+m)

stats={"common_calls":0}
def shared(gA,gB):
    A=obj.get(gA); B=obj.get(gB)
    if not A or not B: return 0.0
    tot=0.0
    for fa,ba,pa in A:
        for fb,bb,pb in B:
            if not bbov(ba,bb): continue
            if not coplanar(pa,pb): continue
            stats["common_calls"]+=1
            tot+=fcommon(fa,fb)
    return tot

def candidates(n):
    out=[]; m=1.0
    for o in nodes:
        if o["id"]==n["id"]: continue
        a,b=n,o
        if (a["bboxMin"][0]<=b["bboxMax"][0]+m and b["bboxMin"][0]<=a["bboxMax"][0]+m and
            a["bboxMin"][1]<=b["bboxMax"][1]+m and b["bboxMin"][1]<=a["bboxMax"][1]+m and
            a["bboxMin"][2]<=b["bboxMax"][2]+m and b["bboxMin"][2]<=a["bboxMax"][2]+m):
            out.append(o["id"])
    return out

# (1) per-object lazy queries
print("\n=== per-object lazy adjacency latency (object vs bbox-candidates) ===")
for gid in ["71065f57-ee93-4af5-8a67-9aa1c4e88302",   # big wall
            "08d4dedf-1387-453a-9938-7f3ab516b8ac",   # open slab
            "a290fca5-50ff-4a64-b6f6-b2c294733935"]:  # floor
    n=next(x for x in nodes if x["id"]==gid)
    cs=candidates(n); stats["common_calls"]=0
    t=time.time(); nedges=0
    for cid in cs:
        if shared(gid,cid)>1.0*645.16: nedges+=1
    dt=time.time()-t
    print(f"  {gid[:8]} ({n['layer']:20}) cands={len(cs):2} edges={nedges} commonCalls={stats['common_calls']:4}  time={dt*1000:7.1f} ms")

# (2) full-model batch
print("\n=== full-model batch (every object vs its candidates) ===")
stats["common_calls"]=0; t=time.time(); pairs=set()
for n in nodes:
    for cid in candidates(n):
        key=tuple(sorted((n["id"],cid)))
        if key in pairs: continue
        pairs.add(key); shared(n["id"],cid)
dt=time.time()-t
print(f"  objects={len(nodes)} unique_pairs={len(pairs)} commonCalls={stats['common_calls']} totalTime={dt:.2f}s  avg/object={dt/len(nodes)*1000:.1f} ms")
print("  (OCP/Python upper bound; C++ OCCT faster; lazy means we rarely batch all)")
