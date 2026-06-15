"""
Spike A — toolchain proof (corrected primitive): shared-face adjacency between two
solids = sum over FACE PAIRS of BRepAlgoAPI_Common(faceA, faceB).Area.
(Solid-solid Common returns empty for touching solids — measure-zero volume.)

Baseline (our planar engine): 71065f57 <-> f5164542 sharedArea = 18651.672
"""
from OCP.STEPControl import STEPControl_Reader
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_ListOfShape

STEPS = r"C:\Users\aryan\source\repos\rook-spatial\docs\rook_docs\occt-spike\steps"
BASELINE = 18651.672

def read_step(path):
    r = STEPControl_Reader(); r.ReadFile(path); r.TransferRoots(); return r.OneShape()

def faces(shape):
    out = []; e = TopExp_Explorer(shape, TopAbs_FACE)
    while e.More(): out.append(TopoDS.Face_s(e.Current())); e.Next()
    return out

def area(shape):
    p = GProp_GProps(); BRepGProp.SurfaceProperties_s(shape, p); return p.Mass()

def face_common_area(fa, fb, fuzz):
    try:
        op = BRepAlgoAPI_Common()
        la = TopTools_ListOfShape(); la.Append(fa)
        lb = TopTools_ListOfShape(); lb.Append(fb)
        op.SetArguments(la); op.SetTools(lb)
        if fuzz: op.SetFuzzyValue(fuzz)
        op.Build()
        return area(op.Shape())
    except Exception:
        return -1.0

a = read_step(STEPS + r"\71065f57.stp"); b = read_step(STEPS + r"\f5164542.stp")
fa, fb = faces(a), faces(b)
print(f"A faces={len(fa)}  B faces={len(fb)}  baseline shared={BASELINE}")
print()
for fuzz in (0.0, 1e-3, 1e-2, 1e-1):
    total = 0.0; hits = []
    for i, x in enumerate(fa):
        for j, y in enumerate(fb):
            ar = face_common_area(x, y, fuzz)
            if ar > 1e-6:
                total += ar; hits.append((i, j, ar))
    print(f"fuzz={fuzz:<6} total_shared_area={total:.3f}  (baseline {BASELINE})  pairs={len(hits)}")
    for i, j, ar in hits:
        print(f"    A[{i}] x B[{j}] = {ar:.3f}")
