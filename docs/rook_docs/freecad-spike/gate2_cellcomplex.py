"""
GATE 2 — multi-room CellComplex: adjacency at multi-wall scale + apertures
(traversal/egress graph) + general-polygon overlap (beyond axis-aligned AABB).

Builds on Gate 1 (Path B2 = coplanar + 2D-overlap validated). Gate 2 adds:
  G2.1  Multiple rooms sharing walls — A (OCCT, FIXED with generalFuse element-map,
        not centroid guessing) vs B2, must match. Includes a corner-only pair
        (share an edge, NOT a face) as a negative.
  G2.2  Apertures (doors): door in a shared wall -> traversal edge between rooms;
        door in an exterior wall -> edge to EXTERIOR. Then circulation/egress via
        BFS. A sealed room (adjacent but no door) must have NO egress.
  G2.3  General-polygon overlap: two coplanar quads whose AABBs overlap but whose
        polygons are DISJOINT -> AABB method FALSE-POSITIVES, Sutherland-Hodgman
        polygon clip is correct. Proves the B2 upgrade beyond rectangles.

Pure-Python graph/clip (no networkx/shapely needed inside FreeCAD). Touches no
existing code. Run: freecadcmd gate2_cellcomplex.py
"""
import os, json, time, itertools, math
import FreeCAD as App
import Part

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 1e-3
R = {"adjacency": {}, "apertures": {}, "circulation": {}, "general_polygon": {}, "timing": {}, "answers": {}}

def rk(x): return round(x / TOL) * TOL

# ---- geometry helpers (pure coordinate extraction) -------------------------
def ordered_face_pts(face):
    try:
        vs = face.OuterWire.OrderedVertexes
        pts = [(v.Point.x, v.Point.y, v.Point.z) for v in vs]
        if len(pts) >= 3:
            return pts
    except Exception:
        pass
    pts = [(v.Point.x, v.Point.y, v.Point.z) for v in face.Vertexes]
    return pts  # fallback (unordered)

def face_plane(face):
    try:
        n = face.normalAt(0, 0)
    except Exception:
        n = face.Surface.Axis
    nx, ny, nz = n.x, n.y, n.z
    L = math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
    nx, ny, nz = nx/L, ny/L, nz/L
    for c in (nx, ny, nz):
        if abs(c) > 1e-9:
            if c < 0: nx, ny, nz = -nx, -ny, -nz
            break
    com = face.CenterOfMass
    d = nx*com.x+ny*com.y+nz*com.z
    return (rk(nx), rk(ny), rk(nz), rk(d))

def plane_of_pts(pts):
    # normal via Newell's method (robust for planar polygon)
    nx=ny=nz=0.0
    n=len(pts)
    for i in range(n):
        x0,y0,z0=pts[i]; x1,y1,z1=pts[(i+1)%n]
        nx+=(y0-y1)*(z0+z1); ny+=(z0-z1)*(x0+x1); nz+=(x0-x1)*(y0+y1)
    L=math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
    nx,ny,nz=nx/L,ny/L,nz/L
    for c in (nx,ny,nz):
        if abs(c)>1e-9:
            if c<0: nx,ny,nz=-nx,-ny,-nz
            break
    cx=sum(p[0] for p in pts)/n; cy=sum(p[1] for p in pts)/n; cz=sum(p[2] for p in pts)/n
    d=nx*cx+ny*cy+nz*cz
    return (rk(nx),rk(ny),rk(nz),rk(d))

def project2d(pts, plane):
    nx,ny,nz,_=plane
    drop=max(range(3), key=lambda i: abs((nx,ny,nz)[i]))
    keep=[i for i in range(3) if i!=drop]
    return [(p[keep[0]], p[keep[1]]) for p in pts]

# ---- 2D polygon ops (Sutherland-Hodgman convex clip) -----------------------
def poly_area(poly):
    a=0.0; n=len(poly)
    for i in range(n):
        x0,y0=poly[i]; x1,y1=poly[(i+1)%n]
        a+=x0*y1-x1*y0
    return abs(a)/2.0

def sh_clip(subject, clip):
    """Clip convex/simple subject by convex clip polygon (Sutherland-Hodgman)."""
    def inside(p, a, b):
        return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]) >= -1e-9
    def inter(s, e, a, b):
        dc=(a[0]-b[0], a[1]-b[1]); dp=(s[0]-e[0], s[1]-e[1])
        n1=a[0]*b[1]-a[1]*b[0]; n2=s[0]*e[1]-s[1]*e[0]
        den=dc[0]*dp[1]-dc[1]*dp[0]
        if abs(den)<1e-12: return e
        return ((n1*dp[0]-n2*dc[0])/den, (n1*dp[1]-n2*dc[1])/den)
    # ensure clip CCW
    if _signed_area(clip) < 0: clip = clip[::-1]
    output=subject[:]
    for i in range(len(clip)):
        a=clip[i]; b=clip[(i+1)%len(clip)]
        inp=output; output=[]
        if not inp: break
        s=inp[-1]
        for e in inp:
            if inside(e,a,b):
                if not inside(s,a,b): output.append(inter(s,e,a,b))
                output.append(e)
            elif inside(s,a,b):
                output.append(inter(s,e,a,b))
            s=e
    return output

def _signed_area(poly):
    a=0.0; n=len(poly)
    for i in range(n):
        x0,y0=poly[i]; x1,y1=poly[(i+1)%n]
        a+=x0*y1-x1*y0
    return a/2.0

def aabb(poly):
    xs=[p[0] for p in poly]; ys=[p[1] for p in poly]
    return (min(xs),min(ys),max(xs),max(ys))

def aabb_overlap(p,q):
    a=aabb(p); b=aabb(q)
    return min(a[2],b[2])-max(a[0],b[0])>TOL and min(a[3],b[3])-max(a[1],b[1])>TOL

def poly_overlap(p,q):
    return poly_area(sh_clip(p,q))>TOL*TOL

def point_in_poly(pt, poly):
    x,y=pt; inside=False; n=len(poly); j=n-1
    for i in range(n):
        xi,yi=poly[i]; xj,yj=poly[j]
        if ((yi>y)!=(yj>y)) and (x < (xj-xi)*(y-yi)/((yj-yi) or 1e-12)+xi):
            inside=not inside
        j=i
    return inside

# ---- ROOMS as air cells (shared face = partition wall) ---------------------
def Box(L,W,H,x,y,z): return Part.makeBox(L,W,H,App.Vector(x,y,z))
rooms = {
    "A": Box(4000,3000,3000, 0,0,0),
    "B": Box(4000,3000,3000, 4000,0,0),     # shares x=4000 face with A
    "C": Box(4000,3000,3000, 0,3000,0),     # shares y=3000 face with A
    # B and C touch only at the corner edge (4000,3000) -> NOT face-adjacent
}
truth_adj = {frozenset(("A","B")), frozenset(("A","C"))}

# ---- PATH A (OCCT) with element-map attribution (the Gate-1 fix) -----------
def path_a(cells):
    names=list(cells.keys()); shapes=[cells[n] for n in names]
    result, fmap = shapes[0].generalFuse(shapes[1:])
    # fmap[i] = list of result subshapes from argument i; order [shapes[0]]+rest
    input_faces=[]
    for i,frags in enumerate(fmap):
        faces=[]
        for fr in frags: faces.extend(fr.Faces)
        input_faces.append((names[i], faces))
    adj=set()
    for (n1,f1s),(n2,f2s) in itertools.combinations(input_faces,2):
        if any(a.isSame(b) for a in f1s for b in f2s):
            adj.add(frozenset((n1,n2)))
    return adj

# ---- PATH B2 (coplanar + general polygon overlap) --------------------------
def path_b2(cells, use_polygon=True):
    plane_faces={}
    for n,s in cells.items():
        for f in s.Faces:
            pl=face_plane(f)
            poly2d=project2d(ordered_face_pts(f), pl)
            plane_faces.setdefault(pl,[]).append((n,poly2d))
    adj=set()
    for pl,entries in plane_faces.items():
        for (n1,p1),(n2,p2) in itertools.combinations(entries,2):
            if n1==n2: continue
            hit = poly_overlap(p1,p2) if use_polygon else aabb_overlap(p1,p2)
            if hit: adj.add(frozenset((n1,n2)))
    return adj

t0=time.perf_counter(); A=path_a(rooms); tA=time.perf_counter()-t0
t0=time.perf_counter(); B=path_b2(rooms); tB=time.perf_counter()-t0
def fmt(s): return sorted("|".join(sorted(p)) for p in s)
R["adjacency"]={"truth":fmt(truth_adj),"pathA":fmt(A),"pathB2":fmt(B),
                "A_eq_truth":fmt(A)==fmt(truth_adj),"B2_eq_A":fmt(B)==fmt(A)}
R["timing"]={"A_ms":round(tA*1000,2),"B2_ms":round(tB*1000,2)}

# ---- APERTURES (doors) -> traversal graph ----------------------------------
# door = ordered 4 pts (a rectangle in a wall plane)
doors = {
    "door_AB": [(4000,1000,0),(4000,2000,0),(4000,2000,2100),(4000,1000,2100)],  # in A|B wall (x=4000)
    "door_Aext": [(1000,0,0),(2000,0,0),(2000,0,2100),(1000,0,2100)],            # in A exterior wall (y=0)
    # C has a shared wall with A but NO door -> sealed
}
def assign_door(door_pts):
    pl=plane_of_pts(door_pts)
    c2=project2d(door_pts,pl)
    cx=sum(p[0] for p in c2)/len(c2); cy=sum(p[1] for p in c2)/len(c2)
    hosts=[]
    for n,s in rooms.items():
        for f in s.Faces:
            if face_plane(f)==pl:
                fp=project2d(ordered_face_pts(f),pl)
                if point_in_poly((cx,cy),fp):
                    hosts.append(n); break
    return sorted(set(hosts))
aperture_edges=[]   # (u, v) traversal edges; v may be "EXTERIOR"
for dn,dp in doors.items():
    hosts=assign_door(dp)
    if len(hosts)>=2:
        aperture_edges.append((hosts[0],hosts[1],dn))
    elif len(hosts)==1:
        aperture_edges.append((hosts[0],"EXTERIOR",dn))
    R["apertures"][dn]={"hosts":hosts,"kind":"interior" if len(hosts)>=2 else "exterior"}

# ---- CIRCULATION / EGRESS (BFS on traversal edges) -------------------------
trav={}
for u,v,_ in aperture_edges:
    trav.setdefault(u,set()).add(v); trav.setdefault(v,set()).add(u)
def reaches_exterior(start):
    seen={start}; stack=[start]
    while stack:
        cur=stack.pop()
        if cur=="EXTERIOR": return True
        for nb in trav.get(cur,()):
            if nb not in seen: seen.add(nb); stack.append(nb)
    return "EXTERIOR" in seen
for rm in rooms:
    R["circulation"][rm]={"has_egress":reaches_exterior(rm),
                          "doors":sorted(n for u,v,n in aperture_edges if rm in (u,v))}

# ---- GENERAL-POLYGON test: AABB false-positive vs SH clip ------------------
# Two coplanar (z=0) triangles whose AABBs overlap but polygons are disjoint.
tri1=[(0,0),(100,0),(0,100)]          # lower-left triangle
tri2=[(100,100),(20,100),(100,20)]    # upper-right triangle; AABBs overlap in the middle box
R["general_polygon"]={
    "aabb_says_overlap": aabb_overlap(tri1,tri2),     # expect True (false positive)
    "polygon_says_overlap": poly_overlap(tri1,tri2),  # expect False (correct)
    "clip_area": round(poly_area(sh_clip(tri1,tri2)),4),
}

# ---- ANSWERS ---------------------------------------------------------------
R["answers"]={
    "G2_1_multiwall_A_eq_truth": R["adjacency"]["A_eq_truth"],
    "G2_1_B2_eq_A": R["adjacency"]["B2_eq_A"],
    "G2_1_corner_only_excluded": ("B|C" not in R["adjacency"]["pathB2"] and "B|C" not in R["adjacency"]["pathA"]),
    "G2_2_door_AB_interior": R["apertures"].get("door_AB",{}).get("kind")=="interior",
    "G2_2_door_Aext_exterior": R["apertures"].get("door_Aext",{}).get("kind")=="exterior",
    "G2_2_sealed_C_no_egress": (R["circulation"]["C"]["has_egress"]==False),
    "G2_2_B_egress_via_A": R["circulation"]["B"]["has_egress"]==True,
    "G2_3_polygon_fixes_aabb_falsepositive": (R["general_polygon"]["aabb_says_overlap"]==True and R["general_polygon"]["polygon_says_overlap"]==False),
}

with open(os.path.join(HERE,"results_gate2.json"),"w") as f:
    json.dump(R,f,indent=2)

print("="*78); print("GATE 2 — CellComplex: multi-wall adjacency + apertures + general polygon"); print("="*78)
print("ADJACENCY:", json.dumps(R["adjacency"],indent=2))
print("APERTURES:", json.dumps(R["apertures"],indent=2))
print("CIRCULATION/EGRESS:", json.dumps(R["circulation"],indent=2))
print("GENERAL-POLYGON:", json.dumps(R["general_polygon"],indent=2))
print("TIMING:", R["timing"])
print("-"*78); print("ANSWERS:", json.dumps(R["answers"],indent=2))
