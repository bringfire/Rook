"""Golden Gate Bridge Generator

Parametric suspension bridge for Grasshopper.
Scale: 1 unit = 10 feet

Inputs (from GH sliders):
    x           : MainSpan       (default 420 = 4,200 ft)
    y           : TowerHeight    (default 75  = 746 ft)
    CableSag    : Cable sag      (default 47  = 470 ft)
    DeckClearance: Deck height   (default 22  = 220 ft)
    SideSpan    : Side span      (default 112 = 1,125 ft)
    NumSuspenders: Suspender count (default 20 per side)
    DeckWidth   : Deck width     (default 9   = 90 ft)

Output:
    a : list of Brep (towers, cables, suspenders, deck)
"""
import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

# Read all inputs from sliders
MainSpan = float(x)
TowerHeight = float(y)
_CableSag = float(CableSag) if CableSag is not None else MainSpan * 0.112
_DeckClearance = float(DeckClearance) if DeckClearance is not None else MainSpan * 0.052
_SideSpan = float(SideSpan) if SideSpan is not None else MainSpan * 0.267
_NumSuspenders = int(NumSuspenders) if NumSuspenders is not None else 20
_DeckWidth = float(DeckWidth) if DeckWidth is not None else MainSpan * 0.021

# Derived dimensions
TowerWidth = max(1.0, MainSpan * 0.007)
CableRadius = max(0.3, MainSpan * 0.002)
SuspenderRadius = max(0.1, MainSpan * 0.0005)

HalfSpan = MainSpan / 2.0
HalfWidth = _DeckWidth / 2.0
CableMinZ = TowerHeight - _CableSag

geometry = []

# ====== TOWERS ======
for tx in [-HalfSpan, HalfSpan]:
    box = rg.Box(
        rg.Plane.WorldXY,
        rg.Interval(tx - TowerWidth / 2, tx + TowerWidth / 2),
        rg.Interval(-HalfWidth, HalfWidth),
        rg.Interval(0, TowerHeight),
    )
    geometry.append(box.ToBrep())

# ====== MAIN CABLES ======
for cy in [-HalfWidth, HalfWidth]:
    pts = []
    pts.append(rg.Point3d(-HalfSpan - _SideSpan, cy, _DeckClearance))
    for i in range(21):
        t = i / 20.0
        px = -HalfSpan + t * MainSpan
        pz = CableMinZ + _CableSag * (2 * t - 1) ** 2
        pts.append(rg.Point3d(px, cy, pz))
    pts.append(rg.Point3d(HalfSpan + _SideSpan, cy, _DeckClearance))
    cable = rg.Curve.CreateInterpolatedCurve(pts, 3)
    if cable:
        pipes = rg.Brep.CreatePipe(
            cable, CableRadius, False, rg.PipeCapMode.Round, True, 0.01, 0.01
        )
        if pipes:
            geometry.extend(pipes)

# ====== SUSPENDER CABLES ======
for cy in [-HalfWidth, HalfWidth]:
    for i in range(_NumSuspenders):
        t = (i + 0.5) / _NumSuspenders
        px = -HalfSpan + t * MainSpan
        pz = CableMinZ + _CableSag * (2 * t - 1) ** 2
        lc = rg.LineCurve(
            rg.Point3d(px, cy, pz), rg.Point3d(px, cy, _DeckClearance)
        )
        pipes = rg.Brep.CreatePipe(
            lc, SuspenderRadius, False, rg.PipeCapMode.Round, True, 0.01, 0.01
        )
        if pipes:
            geometry.extend(pipes)

# ====== DECK ======
deck = rg.Box(
    rg.Plane.WorldXY,
    rg.Interval(-HalfSpan - _SideSpan, HalfSpan + _SideSpan),
    rg.Interval(-HalfWidth, HalfWidth),
    rg.Interval(_DeckClearance - 1.0, _DeckClearance),
)
geometry.append(deck.ToBrep())

# Output as DataTree so GH previews each item
tree = DataTree[object]()
path = GH_Path(0)
for g in geometry:
    tree.Add(g, path)
a = tree
