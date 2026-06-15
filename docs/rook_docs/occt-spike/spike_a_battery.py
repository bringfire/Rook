"""
Spike A battery (v2) — OCCT face-pair Common adjacency vs our engine on real model.
Maps the single all-model STEP to Rhino GUIDs by SOLID/SHELL centroid containment
(interior centroids are unambiguous; interface faces on bbox boundaries are not).
Then tests: (1) agreement on solids, (2) open slab gap, (3) curved wall gap.
Units: ours = inches; STEP = mm; in^2 -> mm^2 factor = 645.16.
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

STEP = r"C:\Users\aryan\source\repos\rook-spatial\docs\rook_docs\occt-spike\steps\spatialtest_all.stp"
MM2_PER_IN2 = 645.16
MM_PER_IN = 25.4

def post(path, body):
    req=urllib.request.Request("http://localhost:63762"+path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

# nodes with bbox (inches)
nodes = post("/scene/graph/query", {"depth":"full"})["data"]["nodes"]
if isinstance(nodes, dict): nodes=list(nodes.values())
for n in nodes:
    mn=n["bboxMin"]; mx=n["bboxMax"]
    n["_min_mm"]=[mn[i]*MM_PER_IN for i in range(3)]
    n["_max_mm"]=[mx[i]*MM_PER_IN for i in range(3)]
    n["_vol"]=max(1e-9,(mx[0]-mn[0])*(mx[1]-mn[1])*(mx[2]-mn[2]))
by_id={n["id"]:n for n in nodes}

def faces_of(shape):
    out=[]; e=TopExp_Explorer(shape, TopAbs_FACE)
    while e.More(): out.append(TopoDS.Face_s(e.Current())); e.Next()
    return out
def surf_area(shape):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(shape,p); return p.Mass()
def vol_com(shape):
    p=GProp_GProps(); BRepGProp.VolumeProperties_s(shape,p); c=p.CentreOfMass(); return (c.X(),c.Y(),c.Z())
def surf_com(shape):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(shape,p); c=p.CentreOfMass(); return (c.X(),c.Y(),c.Z())
def fbbox(f):
    bb=Bnd_Box(); BRepBndLib.Add_s(f,bb); a=bb.CornerMin(); b=bb.CornerMax(); return (a.X(),a.Y(),a.Z(),b.X(),b.Y(),b.Z())

def assign(c_mm):
    # smallest-volume Rhino bbox (in mm) containing centroid c_mm
    best=None; bestv=1e30; m=0.5*MM_PER_IN
    for n in nodes:
        mn=n["_min_mm"]; mx=n["_max_mm"]
        if all(mn[i]-m<=c_mm[i]<=mx[i]+m for i in range(3)):
            if n["_vol"]<bestv: bestv=n["_vol"]; best=n["id"]
    return best

r=STEPControl_Reader(); r.ReadFile(STEP); r.TransferRoots(); root=r.OneShape()

# group faces by GUID via SOLID then SHELL primitives (interior centroids)
obj_faces={}   # guid -> list[(face, sig)]
seen={}        # guid -> set of sigs (dedupe)
def add_primitive(shape, com):
    g=assign(com)
    if g is None: return
    obj_faces.setdefault(g,[]); seen.setdefault(g,set())
    for f in faces_of(shape):
        p=GProp_GProps(); BRepGProp.SurfaceProperties_s(f,p); cc=p.CentreOfMass()
        sig=(round(p.Mass(),3), round(cc.X(),2), round(cc.Y(),2), round(cc.Z(),2))
        if sig in seen[g]: continue
        seen[g].add(sig); obj_faces[g].append((f, fbbox(f)))

e=TopExp_Explorer(root, TopAbs_SOLID)
nsol=0
while e.More():
    s=TopoDS.Solid_s(e.Current()); add_primitive(s, vol_com(s)); nsol+=1; e.Next()
e=TopExp_Explorer(root, TopAbs_SHELL)
nsh=0
while e.More():
    s=TopoDS.Shell_s(e.Current()); add_primitive(s, surf_com(s)); nsh+=1; e.Next()

mapped=sum(1 for g in obj_faces if obj_faces[g])
print(f"primitives: solids={nsol} shells={nsh}; GUIDs with faces: {mapped}/{len(nodes)}")
unmapped=[n['id'][:8]+':'+n['layer'] for n in nodes if not obj_faces.get(n['id'])]
if unmapped: print("  UNMAPPED:", unmapped)

def bbov(b1,b2,m):
    return (b1[0]<=b2[3]+m and b2[0]<=b1[3]+m and b1[1]<=b2[4]+m and b2[1]<=b1[4]+m and b1[2]<=b2[5]+m and b2[2]<=b1[5]+m)
def fc_area(fa,fb,fuzz):
    try:
        op=BRepAlgoAPI_Common(); la=TopTools_ListOfShape(); la.Append(fa); lb=TopTools_ListOfShape(); lb.Append(fb)
        op.SetArguments(la); op.SetTools(lb)
        if fuzz: op.SetFuzzyValue(fuzz)
        op.Build(); return surf_area(op.Shape())
    except Exception: return 0.0
def shared_in2(gA,gB,fuzz=1e-3):
    A=obj_faces.get(gA); B=obj_faces.get(gB)
    if not A or not B: return None
    tot=0.0
    for fa,ba in A:
        for fb,bb in B:
            if not bbov(ba,bb,max(fuzz,5.0)): continue
            tot+=fc_area(fa,fb,fuzz)
    return tot/MM2_PER_IN2

print("\n=== TEST 1: agreement on closed-solid pairs (OCCT in^2 vs ours) ===")
for ga,gb,ours in [("71065f57-ee93-4af5-8a67-9aa1c4e88302","f5164542-1ace-4976-a534-3ff68cdfd794",18651.672),
                   ("71065f57-ee93-4af5-8a67-9aa1c4e88302","2e19c012-6a6a-4250-a25d-9714c0bae202",12175.853),
                   ("71065f57-ee93-4af5-8a67-9aa1c4e88302","a290fca5-50ff-4a64-b6f6-b2c294733935",13487.953)]:
    occt=shared_in2(ga,gb)
    print(f"  {ga[:8]} x {gb[:8]}: OCCT={'UNMAPPED' if occt is None else f'{occt:11.3f}'}  ours={ours:11.3f}" + ("" if occt is None else f"  ratio={occt/ours:.4f}"))

def scan(guid, label):
    src=post("/scene/graph/adjacency/exact",{"objectId":guid,"maxCandidates":16})["data"]
    cands=[c["id"] for c in src["candidates"]]
    print(f"\n=== {label} {guid[:8]} (ours: {src['sourceCapability']}, edges={len(src['edges'])}) ===")
    print(f"    OCCT vs its {len(cands)} broad-phase candidates:")
    any_found=False
    for cid in cands:
        a=shared_in2(guid,cid)
        if a is None:
            print(f"      {cid[:8]} UNMAPPED"); continue
        if a>1.0:
            any_found=True
            print(f"      {cid[:8]} {by_id[cid]['layer']:26} OCCT={a:11.3f} in^2  >>> our engine: 0")
    if not any_found: print("      (OCCT found no shared area either)")

scan("08d4dedf-1387-453a-9938-7f3ab516b8ac", "TEST 2 OPEN SLAB")
scan("7d55840d-2516-4a78-9c7d-3a10152756b1", "TEST 3 CURVED WALL")
