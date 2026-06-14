"""
GATE 1 — adjacency engine: Path A (OCCT) vs Path B (pure-Python hashing), on
deliberate fixtures with KNOWN ground truth, plus the real storey package.

Answers (as many unresolved questions as possible, no existing code touched):
  Q1  Clean full-face sharing: does B match A?
  Q2  PARTIAL overlap (small face on big face) — the central risk: B1 (vertex hash)
      vs B2 (coplanar 2D overlap) vs A (OCCT generalFuse imprint).
  Q3  No-touch gap: do any paths false-positive?
  Q4  Disjoint solids: does raw IsSame find adjacency WITHOUT generalFuse?
      (Gate-0 mechanism check — expect NO.)
  Q5  Tolerance: coincident-but-1e-5-off faces — what does each path detect?
  Q6  Containment vs adjacency: embedded box — face-sharing conflates it?
  Q7  Real storey (wall/slab/window from STEP): hosting + wall/slab gap.
  Q8  Timing smell of A vs B.

Run: freecadcmd gate1_adjacency.py   (uses FreeCAD's OCCT for A; pure-Python for B)
"""
import os, json, time, itertools, math
import FreeCAD as App
import Part

HERE = os.path.dirname(os.path.abspath(__file__))
TOL_GRID = 1e-3          # 1 micron rounding grid for vertex/plane hashing (mm units)
R = {"fixtures": {}, "storey": {}, "answers": {}, "timing": {}}

# ----------------------------------------------------------------------------
# geometry readers (pure coordinate extraction — no kernel topology ops)
# ----------------------------------------------------------------------------
def face_vertices(face):
    pts = []
    for v in face.Vertexes:
        p = v.Point
        pts.append((p.x, p.y, p.z))
    return pts

def rkey(x):  # round to grid
    return round(x / TOL_GRID) * TOL_GRID

def face_vertex_key(face):
    """B1 key: orientation/winding/start-independent set of rounded vertices."""
    return tuple(sorted({(rkey(x), rkey(y), rkey(z)) for (x, y, z) in face_vertices(face)}))

def face_plane(face):
    """(canonical unit normal, signed offset) rounded — for coplanar grouping."""
    try:
        n = face.normalAt(0, 0)
    except Exception:
        n = face.Surface.Axis
    nx, ny, nz = n.x, n.y, n.z
    L = math.sqrt(nx*nx + ny*ny + nz*nz) or 1.0
    nx, ny, nz = nx/L, ny/L, nz/L
    # canonical sign: make the first nonzero component positive (coplanar faces
    # of opposite orientation must group together)
    for c in (nx, ny, nz):
        if abs(c) > 1e-9:
            if c < 0:
                nx, ny, nz = -nx, -ny, -nz
            break
    com = face.CenterOfMass
    d = nx*com.x + ny*com.y + nz*com.z
    return (rkey(nx), rkey(ny), rkey(nz), rkey(d))

def face_2d_bounds(face, plane):
    """Project face verts to the 2 in-plane axes (drop dominant normal axis).
    Assumes axis-aligned-ish rectangles (true for boxes / most architecture)."""
    nx, ny, nz, _ = plane
    drop = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
    keep = [i for i in range(3) if i != drop]
    us, vs = [], []
    for p in face_vertices(face):
        us.append(p[keep[0]]); vs.append(p[keep[1]])
    return (min(us), min(vs), max(us), max(vs))

def aabb2d_overlap(b1, b2):
    ox = min(b1[2], b2[2]) - max(b1[0], b2[0])
    oy = min(b1[3], b2[3]) - max(b1[1], b2[1])
    if ox > TOL_GRID and oy > TOL_GRID:
        return ox * oy
    return 0.0

# ----------------------------------------------------------------------------
# PATH A — OCCT: generalFuse imprints coincident faces -> shared (IsSame)
# ----------------------------------------------------------------------------
def path_a_adjacency(named_solids):
    """Returns set of frozenset(pairs) that share a face after generalFuse."""
    names = list(named_solids.keys())
    shapes = [named_solids[n] for n in names]
    base, rest = shapes[0], shapes[1:]
    fused, _ = base.generalFuse(rest)
    result_solids = fused.Solids
    # map each fused solid back to an original by nearest centroid
    def owner(sol):
        c = sol.CenterOfMass
        best, bd = None, 1e18
        for n in names:
            oc = named_solids[n].CenterOfMass
            d = (c.x-oc.x)**2 + (c.y-oc.y)**2 + (c.z-oc.z)**2
            if d < bd:
                bd, best = d, n
        return best
    sol_owner = [(owner(s), s) for s in result_solids]
    adj = set()
    # face shared (IsSame) between two result solids of different owners
    for (n1, s1), (n2, s2) in itertools.combinations(sol_owner, 2):
        if n1 == n2:
            continue
        shared = False
        for f1 in s1.Faces:
            for f2 in s2.Faces:
                if f1.isSame(f2):
                    shared = True; break
            if shared: break
        if shared:
            adj.add(frozenset((n1, n2)))
    return adj

def raw_issame_adjacency(named_solids):
    """Q4: do disjoint solids share faces by IsSame WITHOUT generalFuse?"""
    names = list(named_solids.keys())
    adj = set()
    for n1, n2 in itertools.combinations(names, 2):
        s1, s2 = named_solids[n1], named_solids[n2]
        if any(f1.isSame(f2) for f1 in s1.Faces for f2 in s2.Faces):
            adj.add(frozenset((n1, n2)))
    return adj

# ----------------------------------------------------------------------------
# PATH B1 — naive vertex-set hash (catches EXACT-coincident faces only)
# ----------------------------------------------------------------------------
def path_b1_adjacency(named_solids):
    key_to_solids = {}
    for n, s in named_solids.items():
        for f in s.Faces:
            key_to_solids.setdefault(face_vertex_key(f), set()).add(n)
    adj = set()
    for key, owners in key_to_solids.items():
        if len(owners) >= 2:
            for a, b in itertools.combinations(sorted(owners), 2):
                adj.add(frozenset((a, b)))
    return adj

# ----------------------------------------------------------------------------
# PATH B2 — coplanar grouping + 2D overlap (catches PARTIAL overlaps)
# ----------------------------------------------------------------------------
def path_b2_adjacency(named_solids):
    plane_faces = {}  # plane_key -> list of (solid_name, 2d_bounds)
    for n, s in named_solids.items():
        for f in s.Faces:
            pl = face_plane(f)
            plane_faces.setdefault(pl, []).append((n, face_2d_bounds(f, pl)))
    adj = set()
    for pl, entries in plane_faces.items():
        for (n1, b1), (n2, b2) in itertools.combinations(entries, 2):
            if n1 == n2:
                continue
            if aabb2d_overlap(b1, b2) > 0:
                adj.add(frozenset((n1, n2)))
    return adj

def containment(named_solids):
    """Q6: embedded detection via common-volume ~ inner-volume."""
    names = list(named_solids.keys())
    out = set()
    for n1, n2 in itertools.permutations(names, 2):
        s1, s2 = named_solids[n1], named_solids[n2]  # is n2 inside n1?
        try:
            cv = s1.common(s2).Volume
        except Exception:
            continue
        if s2.Volume > 0 and cv > 0.99 * s2.Volume and s1.Volume > s2.Volume * 1.01:
            out.add((n1, n2))  # n1 contains n2
    return out

def fmt(adjset):
    return sorted("|".join(sorted(p)) for p in adjset)

# ----------------------------------------------------------------------------
# FIXTURES — boxes with KNOWN ground truth, spaced apart in X so groups don't mix
# ----------------------------------------------------------------------------
def B(L, W, H, x, y, z):
    return Part.makeBox(L, W, H, App.Vector(x, y, z))

fixtures = {}   # group -> (named_solids, ground_truth_adjacency, note)

# F1: clean full shared face (stacked, identical face)
fixtures["F1_clean_fullface"] = (
    {"lower": B(1000,1000,1000, 0,0,0), "upper": B(1000,1000,1000, 0,0,1000)},
    {frozenset(("lower","upper"))},
    "upper sits exactly on lower; shared face is identical 1000x1000 @ z=1000")

# F2: PARTIAL overlap (small column bottom on big slab top) — THE central risk
fixtures["F2_partial_overlap"] = (
    {"slab": B(4000,3000,200, 20000,0,0), "col": B(500,500,1000, 21000,1000,200)},
    {frozenset(("slab","col"))},
    "col bottom (500x500 @ z=200) sits on slab top (4000x3000 @ z=200) — PARTIAL")

# F3: no-touch gap (false-positive guard)
fixtures["F3_gap"] = (
    {"ground": B(2000,2000,200, 40000,0,0), "floater": B(500,500,500, 40500,500,350)},
    set(),
    "floater bottom z=350, ground top z=200 -> 150mm gap. NOT adjacent")

# F4: containment (embedded box) — adjacency must NOT claim it; containment must catch
fixtures["F4_containment"] = (
    {"outer": B(2000,2000,2000, 60000,0,0), "inner": B(600,600,600, 60700,700,700)},
    set(),  # ground-truth ADJACENCY is empty; it's containment, tested separately
    "inner fully inside outer volume; no shared boundary face -> not adjacency")

# F5: tolerance — coincident faces 1e-5 mm apart
fixtures["F5_tolerance"] = (
    {"ta": B(1000,1000,1000, 80000,0,0), "tb": B(1000,1000,1000, 80000,0,1000.00001)},
    {frozenset(("ta","tb"))},  # physically touching within a micron -> 'should' be adjacent
    "tb is 1e-5 mm above ta. Probes tolerance policy of each path")

# ----------------------------------------------------------------------------
# RUN fixtures
# ----------------------------------------------------------------------------
for group, (solids, truth, note) in fixtures.items():
    rec = {"note": note, "ground_truth": fmt(truth)}
    t0 = time.perf_counter(); a = path_a_adjacency(solids); ta = time.perf_counter()-t0
    t0 = time.perf_counter(); b1 = path_b1_adjacency(solids); tb1 = time.perf_counter()-t0
    t0 = time.perf_counter(); b2 = path_b2_adjacency(solids); tb2 = time.perf_counter()-t0
    raw = raw_issame_adjacency(solids)
    cont = containment(solids)
    rec.update({
        "pathA_OCCT": fmt(a), "pathB1_vertexhash": fmt(b1), "pathB2_2Doverlap": fmt(b2),
        "raw_isSame_noFuse": fmt(raw), "containment": sorted("%s>%s" % c for c in cont),
        "A_eq_truth": fmt(a) == rec["ground_truth"],
        "B1_eq_A": fmt(b1) == fmt(a), "B2_eq_A": fmt(b2) == fmt(a),
        "timing_ms": {"A": round(ta*1000,2), "B1": round(tb1*1000,2), "B2": round(tb2*1000,2)},
    })
    R["fixtures"][group] = rec

# ----------------------------------------------------------------------------
# REAL STOREY — load the 3 per-object STEPs (wall/slab/window)
# ----------------------------------------------------------------------------
pod = os.path.join(HERE, "per_object")
storey = {}
if os.path.isdir(pod):
    for fn in os.listdir(pod):
        if fn.endswith(".step"):
            shp = Part.Shape(); shp.read(os.path.join(pod, fn))
            label = {"0NJu":"wall","0neT":"slab","3b$R":"window"}
            name = next((v for k,v in label.items() if k in fn), fn[:8])
            solids = shp.Solids
            if solids:
                storey[name] = solids[0]
if len(storey) >= 2:
    R["storey"] = {
        "loaded": sorted(storey.keys()),
        "pathA_OCCT": fmt(path_a_adjacency(storey)),
        "pathB1_vertexhash": fmt(path_b1_adjacency(storey)),
        "pathB2_2Doverlap": fmt(path_b2_adjacency(storey)),
        "containment": sorted("%s>%s" % c for c in containment(storey)),
        "volumes": {n: round(s.Volume,1) for n,s in storey.items()},
    }
else:
    R["storey"] = {"error": "per_object STEPs not found/loaded", "found": sorted(storey.keys())}

# ----------------------------------------------------------------------------
# ANSWERS — distilled verdicts
# ----------------------------------------------------------------------------
fx = R["fixtures"]
R["answers"] = {
    "Q1_clean_B_matches_A": fx["F1_clean_fullface"]["B1_eq_A"] and fx["F1_clean_fullface"]["B2_eq_A"],
    "Q2_partial_B1_misses": (not fx["F2_partial_overlap"]["B1_eq_A"]),
    "Q2_partial_B2_catches": fx["F2_partial_overlap"]["B2_eq_A"],
    "Q3_gap_no_false_positive": (fx["F3_gap"]["pathA_OCCT"]==[] and fx["F3_gap"]["pathB2_2Doverlap"]==[]),
    "Q4_disjoint_raw_isSame_finds_nothing": all(v["raw_isSame_noFuse"]==[] for v in fx.values()),
    "Q5_tolerance": {"A": fx["F5_tolerance"]["pathA_OCCT"], "B2": fx["F5_tolerance"]["pathB2_2Doverlap"]},
    "Q6_containment_caught": fx["F4_containment"]["containment"],
    "timing_smell_ms": {g: v["timing_ms"] for g,v in fx.items()},
}

with open(os.path.join(HERE, "results_gate1.json"), "w") as f:
    json.dump(R, f, indent=2)

# ----------------------------------------------------------------------------
print("="*78); print("GATE 1 — ADJACENCY: Path A (OCCT) vs Path B1/B2 (pure-Python)"); print("="*78)
for g, v in fx.items():
    print(f"\n[{g}]  {v['note']}")
    print(f"   truth={v['ground_truth']}")
    print(f"   A(OCCT)   ={v['pathA_OCCT']}   (==truth: {v['A_eq_truth']})")
    print(f"   B1(vhash) ={v['pathB1_vertexhash']}   (==A: {v['B1_eq_A']})")
    print(f"   B2(2Dovl) ={v['pathB2_2Doverlap']}   (==A: {v['B2_eq_A']})")
    print(f"   raw isSame (no fuse) ={v['raw_isSame_noFuse']}   containment={v['containment']}")
    print(f"   timing ms: {v['timing_ms']}")
print("\n" + "-"*78); print("STOREY:", json.dumps(R["storey"], indent=2))
print("-"*78); print("ANSWERS:", json.dumps(R["answers"], indent=2))
