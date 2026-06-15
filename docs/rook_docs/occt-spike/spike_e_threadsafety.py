"""
Spike E — OCCT thread-safety (partial, OCP-level). Runs the same set of face-pair
Common ops (a) single-threaded to get a baseline, then (b) across N worker threads,
and checks: no crash, and concurrent results == baseline (deterministic/correct).
OCP releases the GIL during native OCCT calls, so threads exercise real concurrency.
NOTE: this is OCP/Python; the C++ plugin must still call OSD::SetSignal and verify
in-process; serialized fallback (single OCCT worker queue) is the known safe answer.
"""
import json, urllib.request, threading, time
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
MM_PER_IN=25.4
def post(p,b):
    r=urllib.request.Request("http://localhost:63762"+p,data=json.dumps(b).encode(),method="POST",headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(r,timeout=60) as x: return json.loads(x.read().decode())
nodes=post("/scene/graph/query",{"depth":"full"})["data"]["nodes"]
if isinstance(nodes,dict): nodes=list(nodes.values())
for n in nodes:
    mn,mx=n["bboxMin"],n["bboxMax"]
    n["_min"]=[mn[i]*MM_PER_IN for i in range(3)]; n["_max"]=[mx[i]*MM_PER_IN for i in range(3)]; n["_vol"]=max(1e-9,(mx[0]-mn[0])*(mx[1]-mn[1])*(mx[2]-mn[2]))
def faces_of(s):
    o=[]; e=TopExp_Explorer(s,TopAbs_FACE)
    while e.More(): o.append(TopoDS.Face_s(e.Current())); e.Next()
    return o
def sarea(s):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(s,p); return p.Mass()
def vcom(s):
    p=GProp_GProps(); BRepGProp.VolumeProperties_s(s,p); c=p.CentreOfMass(); return (c.X(),c.Y(),c.Z())
def scom(s):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(s,p); c=p.CentreOfMass(); return (c.X(),c.Y(),c.Z())
def assign(c):
    best=None;bv=1e30;m=0.5*MM_PER_IN
    for n in nodes:
        mn,mx=n["_min"],n["_max"]
        if all(mn[i]-m<=c[i]<=mx[i]+m for i in range(3)) and n["_vol"]<bv: bv=n["_vol"];best=n["id"]
    return best
r=STEPControl_Reader(); r.ReadFile(STEP); r.TransferRoots(); root=r.OneShape()
obj={}
def add(shape,com):
    g=assign(com)
    if not g: return
    obj.setdefault(g,[]).extend(faces_of(shape))
e=TopExp_Explorer(root,TopAbs_SOLID)
while e.More(): s=TopoDS.Solid_s(e.Current()); add(s,vcom(s)); e.Next()
e=TopExp_Explorer(root,TopAbs_SHELL)
while e.More(): s=TopoDS.Shell_s(e.Current()); add(s,scom(s)); e.Next()

def shared(gA,gB):
    A=obj.get(gA); B=obj.get(gB)
    if not A or not B: return 0.0
    tot=0.0
    for fa in A:
        for fb in B:
            try:
                op=BRepAlgoAPI_Common(); la=TopTools_ListOfShape(); la.Append(fa); lb=TopTools_ListOfShape(); lb.Append(fb)
                op.SetArguments(la); op.SetTools(lb); op.SetFuzzyValue(1e-3); op.Build(); tot+=sarea(op.Shape())
            except Exception: pass
    return tot

# work list: a fixed set of object pairs (the slab + wall queries)
SLAB="08d4dedf-1387-453a-9938-7f3ab516b8ac"; WALL="71065f57-ee93-4af5-8a67-9aa1c4e88302"
work=[(SLAB,n["id"]) for n in nodes[:30]] + [(WALL,n["id"]) for n in nodes[:30]]

# baseline single-threaded
t=time.time(); base={p:shared(*p) for p in work}; tb=time.time()-t
print(f"baseline single-thread: {len(work)} pairs in {tb:.2f}s")

# concurrent
results={}; lock=threading.Lock(); errors=[]
def worker(chunk):
    for p in chunk:
        try:
            v=shared(*p)
            with lock: results[p]=v
        except Exception as ex:
            with lock: errors.append((p,repr(ex)))
NTH=8
chunks=[work[i::NTH] for i in range(NTH)]
t=time.time(); ths=[threading.Thread(target=worker,args=(c,)) for c in chunks]
[x.start() for x in ths]; [x.join() for x in ths]; tc=time.time()-t
print(f"concurrent {NTH} threads: {len(results)} results in {tc:.2f}s  errors={len(errors)}")

mismatch=0
for p in work:
    if p not in results: mismatch+=1; continue
    if abs(results[p]-base[p])>1e-6*max(1,abs(base[p])): mismatch+=1
print(f"crashes/exceptions: {len(errors)}")
print(f"result mismatches vs baseline: {mismatch} / {len(work)}")
if errors[:3]: print("sample errors:", errors[:3])
print("VERDICT:", "THREAD-SAFE at OCP level (no crash, results identical)" if (not errors and mismatch==0) else "NOT clean -> serialize")
