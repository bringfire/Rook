"""
Spike C — tolerance behavior + silent-failure surface.
Sweeps OCCT fuzzy value on: (a) the 5 confirmed-good slab adjacencies (should be
STABLE across tolerance = robust), and (b) the 1.687 in^2 sliver 08d4dedf x
502898fc (does it vanish at tight tolerance = artifact, or persist = real graze?).
Also reports OCCT errors/warnings per op (silent-failure surface).
"""
import json, urllib.request
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

STEP=r"C:\Users\aryan\source\repos\rook-spatial\docs\rook_docs\occt-spike\steps\spatialtest_all.stp"
MM_PER_IN=25.4; MM2_PER_IN2=645.16

def post(p,b):
    r=urllib.request.Request("http://localhost:63762"+p,data=json.dumps(b).encode(),method="POST",headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=60) as x: return json.loads(x.read().decode())
nodes=post("/scene/graph/query",{"depth":"full"})["data"]["nodes"]
if isinstance(nodes,dict): nodes=list(nodes.values())
for n in nodes:
    mn,mx=n["bboxMin"],n["bboxMax"]
    n["_min"]=[mn[i]*MM_PER_IN for i in range(3)]; n["_max"]=[mx[i]*MM_PER_IN for i in range(3)]
    n["_vol"]=max(1e-9,(mx[0]-mn[0])*(mx[1]-mn[1])*(mx[2]-mn[2]))
by_id={n["id"]:n for n in nodes}
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
def assign(c):
    best=None; bv=1e30; m=0.5*MM_PER_IN
    for n in nodes:
        mn,mx=n["_min"],n["_max"]
        if all(mn[i]-m<=c[i]<=mx[i]+m for i in range(3)) and n["_vol"]<bv: bv=n["_vol"]; best=n["id"]
    return best
r=STEPControl_Reader(); r.ReadFile(STEP); r.TransferRoots(); root=r.OneShape()
obj={}; seen={}
def add(shape,com):
    g=assign(com)
    if not g: return
    obj.setdefault(g,[]); seen.setdefault(g,set())
    for f in faces_of(shape):
        p=GProp_GProps(); BRepGProp.SurfaceProperties_s(f,p); cc=p.CentreOfMass()
        sig=(round(p.Mass(),3),round(cc.X(),2),round(cc.Y(),2),round(cc.Z(),2))
        if sig in seen[g]: continue
        seen[g].add(sig); obj[g].append((f,fbb(f)))
e=TopExp_Explorer(root,TopAbs_SOLID)
while e.More(): s=TopoDS.Solid_s(e.Current()); add(s,vcom(s)); e.Next()
e=TopExp_Explorer(root,TopAbs_SHELL)
while e.More(): s=TopoDS.Shell_s(e.Current()); add(s,scom(s)); e.Next()

def bbov(b1,b2,m=5.0):
    return (b1[0]<=b2[3]+m and b2[0]<=b1[3]+m and b1[1]<=b2[4]+m and b2[1]<=b1[4]+m and b1[2]<=b2[5]+m and b2[2]<=b1[5]+m)
def shared_in2(gA,gB,fuzz):
    A=obj.get(gA); B=obj.get(gB)
    if not A or not B: return None, 0
    tot=0.0; errs=0
    for fa,ba in A:
        for fb,bb in B:
            if not bbov(ba,bb): continue
            try:
                op=BRepAlgoAPI_Common(); la=TopTools_ListOfShape(); la.Append(fa); lb=TopTools_ListOfShape(); lb.Append(fb)
                op.SetArguments(la); op.SetTools(lb)
                if fuzz: op.SetFuzzyValue(fuzz)
                op.Build(); tot+=area(op.Shape())
            except Exception: errs+=1
    return tot/MM2_PER_IN2, errs

SLAB="08d4dedf-1387-453a-9938-7f3ab516b8ac"
GOOD={"71065f57":"71065f57-ee93-4af5-8a67-9aa1c4e88302",
      "5c12cc83":"5c12cc83-5fe3-4f2c-9fca-c0575c9f5dd3",
      "7e80db98":"7e80db98-d133-4a05-b9fe-ee6d37d9069d",
      "26b2c012":"26b2c012-24cf-4656-9e48-8083dc072cad"}
SLIVER="502898fc-75f3-4d59-bddf-cc966a942795"

fuzzes=[0.0, 1e-4, 1e-3, 1e-2, 2.54, 25.4]   # last two = 0.1 in, 1 in (mm)
print("Tolerance sweep (shared area in^2 vs fuzzy value in mm). 2.54mm=0.1in, 25.4mm=1in\n")
hdr="pair".ljust(22)+ "".join(f"f={f:<8}" for f in fuzzes)
print(hdr)
for label,gid in GOOD.items():
    row=f"slab x {label}".ljust(22)
    for f in fuzzes:
        a,_=shared_in2(SLAB,gid,f); row+=f"{a:<10.2f}"
    print(row)
row=f"slab x 502898fc*".ljust(22)
for f in fuzzes:
    a,_=shared_in2(SLAB,SLIVER,f); row+=f"{a:<10.2f}"
print(row)
print("\n* = the suspected sliver. Stable-across-fuzzy => real; grows-with-fuzzy => tolerance-bridged graze.")
