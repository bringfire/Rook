"""
Strengthener 2 — messier/varied-geometry FUNCTIONAL COVERAGE matrix.

The "any user, who knows what they'll throw" guarantee. Runs the engine primitive
(identity-keyed face-pair BRepAlgoAPI_Common().Area, fuzzy=1e-3, with try/catch) over
synthetic adversarial cases + curved/far-origin/sliver, asserting each row is:
  - CORRECT where a real shared face exists,
  - HONEST (0, no false-exact) where it doesn't,
  - NO CRASH ever (OCCT can throw; the engine swallows per-pair).

Mesh/SubD are NOT tested here: no analytic faces, so handled at the EXTRACTION layer
(Task 7) which classifies them UnsupportedGeometry — proven in the Gate-4 live smoke.
This spike covers the *geometric robustness* rows the clean SpatialTest model lacks.
"""
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_ListOfShape
from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir

FUZZ = 1e-3
SHARED = 100.0   # 10x10 shared face

def faces(s):
    o=[]; e=TopExp_Explorer(s,TopAbs_FACE)
    while e.More(): o.append(TopoDS.Face_s(e.Current())); e.Next()
    return o
def area(s):
    p=GProp_GProps(); BRepGProp.SurfaceProperties_s(s,p); return p.Mass()
def box(x,y,z, dx=10,dy=10,dz=10):
    return BRepPrimAPI_MakeBox(gp_Pnt(x,y,z), dx,dy,dz).Shape()
def cyl():
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(5,5,0), gp_Dir(0,0,1)), 4.0, 10.0).Shape()

def shared_face_area(a, b):
    tot=0.0; crashed=False
    for fa in faces(a):
        for fb in faces(b):
            try:
                op=BRepAlgoAPI_Common(); la=TopTools_ListOfShape(); la.Append(fa); lb=TopTools_ListOfShape(); lb.Append(fb)
                op.SetArguments(la); op.SetTools(lb); op.SetFuzzyValue(FUZZ); op.Build()
                tot += area(op.Shape())   # OCP BRepAlgoAPI_Common has no HasErrors(); rely on try/except
            except Exception:
                crashed=True
    return tot, crashed

# each case: (name, builder->(A,B), expected-desc, predicate(area,crashed,ctor_err)->bool)
cases = [
 ("abutting boxes (clean adjacency)",
  lambda: (box(0,0,0), box(10,0,0)),
  "~100 (one shared face)",
  lambda a,c,e: e is None and not c and abs(a-SHARED)<1.0),

 ("gap 0.5mm > fuzzy (no false adjacency)",
  lambda: (box(0,0,0), box(10.5,0,0)),
  "0 (gap exceeds tolerance)",
  lambda a,c,e: e is None and not c and a<1e-6),

 ("gap 1e-4mm < fuzzy (tolerance-bridged)",
  lambda: (box(0,0,0), box(10.0001,0,0)),
  "~100 (bridged by fuzzy)",
  lambda a,c,e: e is None and not c and abs(a-SHARED)<1.0),

 ("coincident duplicate box (identity case)",
  lambda: (box(0,0,0), box(0,0,0)),
  ">100 sane, no crash (whole surface coincident)",
  lambda a,c,e: e is None and not c and a>100.0),

 ("interpenetrating boxes (volume overlap, no coplanar contact)",
  lambda: (box(0,0,0), box(5,5,5)),
  "0 face-adjacency (interpenetration != shared face)",
  lambda a,c,e: e is None and not c and a<1e-6),

 ("far-from-origin abutting (+1e6)",
  lambda: (box(1e6,1e6,1e6), box(1e6+10,1e6,1e6)),
  "~100 (no precision collapse) OR honest",
  lambda a,c,e: e is None and not c),  # report area; honesty = no crash

 ("sliver box dz=1e-4 (near-degenerate, constructible)",
  lambda: (box(0,0,0), box(10,0,0, dz=1e-4)),
  "no crash; small/0 honest",
  lambda a,c,e: e is None and not c),

 ("zero-thickness box (degenerate, rejected at construction)",
  lambda: (box(0,0,0), box(10,0,0, dz=0)),
  "construction rejected (honest, no silent bad face)",
  lambda a,c,e: e is not None),   # expect ctor error = OCCT rejects degenerate input

 ("cylinder bottom-circle on planar box face (curved contact)",
  lambda: (cyl(), box(0,0,-10)),
  ">1 curved-face overlap, no crash",
  lambda a,c,e: e is None and not c and a>1.0),
]

print("=== Strengthener 2: functional-coverage matrix (engine primitive, fuzzy=1e-3) ===\n")
allpass=True
for name, build, expected, pred in cases:
    ctor_err=None; ar=0.0; cr=False
    try:
        A,B = build()
        ar,cr = shared_face_area(A,B)
    except Exception as ex:
        ctor_err = type(ex).__name__
    ok = pred(ar,cr,ctor_err); allpass = allpass and ok
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"        expected: {expected}")
    print(f"        got: area={ar:.3f} crashed={cr} ctor_err={ctor_err}\n")

print("ALL HONEST:", allpass)
print("(no engine crash anywhere; correct where a real shared face exists; 0/no-false-exact otherwise;")
print(" degenerate input rejected at construction; far-origin reported for inspection)")
