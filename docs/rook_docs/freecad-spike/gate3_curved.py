"""
GATE 3 — curved / complex geometry: where does pure-Python (B2) break, and does
OCCT genuinely handle it? Capability-first: curved walls + freeform are CORE, not
edge cases. This grounds whether OCCT is a required first-class engine.

Fixtures (the professional reality — round columns, tubes, curved walls):
  C1  round column standing on a slab      -> contact = planar CIRCLE (curved edge)
  C2  solid cylinder inside a tube         -> shared CYLINDRICAL face (curved surface)
  C3  cylindrical-shell curved wall on slab-> contact = annular-sector (curved edges)

Three approaches per fixture:
  A         OCCT generalFuse + isSame (fuse-map)  = ground truth
  B2_exact  coplanar + polygon overlap (Gate-2)   = expect BREAKAGE on curved
  B2_tess   tessellate faces, match coincident triangles (identity) = the general
            pure-Python attempt for any surface; expect FRAGILE on curved (independent
            meshes of coincident faces don't share identical triangles)

Reports exactly where each pure-Python path fails and whether OCCT succeeds.
Run: freecadcmd gate3_curved.py
"""
import os, json, time, itertools, math
import FreeCAD as App
import Part

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 1e-3
R = {"fixtures": {}, "answers": {}}
def rk(x): return round(x/TOL)*TOL

# ---- planar B2 helpers (from Gate 2) ---------------------------------------
def ordered_face_pts(face):
    try:
        vs = face.OuterWire.OrderedVertexes
        pts=[(v.Point.x,v.Point.y,v.Point.z) for v in vs]
        if len(pts)>=3: return pts
    except Exception: pass
    return [(v.Point.x,v.Point.y,v.Point.z) for v in face.Vertexes]

def face_plane(face):
    try: n=face.normalAt(0,0)
    except Exception:
        try: n=face.Surface.Axis
        except Exception: return None
    nx,ny,nz=n.x,n.y,n.z; L=math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
    nx,ny,nz=nx/L,ny/L,nz/L
    for c in (nx,ny,nz):
        if abs(c)>1e-9:
            if c<0: nx,ny,nz=-nx,-ny,-nz
            break
    com=face.CenterOfMass; d=nx*com.x+ny*com.y+nz*com.z
    return (rk(nx),rk(ny),rk(nz),rk(d))

def is_planar(face):
    try: return face.Surface.TypeId == "Part::GeomPlane" or "Plane" in str(type(face.Surface))
    except Exception: return False

def project2d(pts, plane):
    nx,ny,nz,_=plane; drop=max(range(3),key=lambda i:abs((nx,ny,nz)[i]))
    keep=[i for i in range(3) if i!=drop]
    return [(p[keep[0]],p[keep[1]]) for p in pts]

def poly_area(poly):
    a=0.0;n=len(poly)
    for i in range(n):
        x0,y0=poly[i];x1,y1=poly[(i+1)%n];a+=x0*y1-x1*y0
    return abs(a)/2.0
def _sa(poly):
    a=0.0;n=len(poly)
    for i in range(n):
        x0,y0=poly[i];x1,y1=poly[(i+1)%n];a+=x0*y1-x1*y0
    return a/2.0
def sh_clip(subject, clip):
    def inside(p,a,b): return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])>=-1e-9
    def inter(s,e,a,b):
        dc=(a[0]-b[0],a[1]-b[1]);dp=(s[0]-e[0],s[1]-e[1])
        n1=a[0]*b[1]-a[1]*b[0];n2=s[0]*e[1]-s[1]*e[0];den=dc[0]*dp[1]-dc[1]*dp[0]
        if abs(den)<1e-12: return e
        return ((n1*dp[0]-n2*dc[0])/den,(n1*dp[1]-n2*dc[1])/den)
    if _sa(clip)<0: clip=clip[::-1]
    out=subject[:]
    for i in range(len(clip)):
        a=clip[i];b=clip[(i+1)%len(clip)];inp=out;out=[]
        if not inp: break
        s=inp[-1]
        for e in inp:
            if inside(e,a,b):
                if not inside(s,a,b): out.append(inter(s,e,a,b))
                out.append(e)
            elif inside(s,a,b): out.append(inter(s,e,a,b))
            s=e
    return out
def poly_overlap(p,q):
    if len(p)<3 or len(q)<3: return False
    return poly_area(sh_clip(p,q))>TOL*TOL

def fmt(s): return sorted("|".join(sorted(p)) for p in s)

# ---- PATH A (OCCT) — CORRECTED: face.common().Area > 0 (surface-agnostic) ---
# (Gate-3 diagnostic proved generalFuse+isSame is the WRONG primitive: isSame tests
#  object-identity, false for independently-built coincident faces. common().Area
#  detects geometric coincidence on planar/cylindrical/NURBS uniformly.)
def path_a(cells):
    names=list(cells.keys())
    adj=set()
    for n1,n2 in itertools.combinations(names,2):
        s1,s2=cells[n1],cells[n2]
        try:
            if s1.distToShape(s2)[0] > 1e-6: continue  # broad-phase: not touching
        except Exception: pass
        shared=False
        for f1 in s1.Faces:
            for f2 in s2.Faces:
                try:
                    if f1.distToShape(f2)[0] < 1e-6:
                        c=f1.common(f2)
                        if c.Faces and sum(f.Area for f in c.Faces) > 1.0:
                            shared=True; break
                except Exception: pass
            if shared: break
        if shared: adj.add(frozenset((n1,n2)))
    return adj

# ---- PATH B2-exact (planar polygon; skips non-planar faces) ----------------
def path_b2_exact(cells):
    plane_faces={}; skipped_curved=0
    for n,s in cells.items():
        for f in s.Faces:
            if not is_planar(f): skipped_curved+=1; continue
            pl=face_plane(f)
            if pl is None: continue
            poly=project2d(ordered_face_pts(f),pl)
            plane_faces.setdefault(pl,[]).append((n,poly))
    adj=set()
    for pl,es in plane_faces.items():
        for (n1,p1),(n2,p2) in itertools.combinations(es,2):
            if n1!=n2 and poly_overlap(p1,p2): adj.add(frozenset((n1,n2)))
    return adj, skipped_curved

# ---- PATH B2-tess (tessellate faces; coincident-triangle identity) ---------
def path_b2_tess(cells, dev=1.0):
    tri_owners={}
    for n,s in cells.items():
        for f in s.Faces:
            try: vs,tris=f.tessellate(dev)
            except Exception: continue
            for (i,j,k) in tris:
                key=frozenset({(rk(vs[a].x),rk(vs[a].y),rk(vs[a].z)) for a in (i,j,k)})
                if len(key)==3: tri_owners.setdefault(key,set()).add(n)
    adj=set()
    for key,ow in tri_owners.items():
        if len(ow)>=2:
            for a,b in itertools.combinations(sorted(ow),2): adj.add(frozenset((a,b)))
    return adj

# ---- FIXTURES (curved) -----------------------------------------------------
def Cyl(r,h,x,y,z): return Part.makeCylinder(r,h,App.Vector(x,y,z),App.Vector(0,0,1))
def Box(L,W,H,x,y,z): return Part.makeBox(L,W,H,App.Vector(x,y,z))

fixtures={}
# C1 round column on slab (planar circular contact)
fixtures["C1_column_on_slab"]=(
    {"slab":Box(4000,4000,200, 0,0,0), "col":Cyl(500,3000, 2000,2000,200)},
    {frozenset(("slab","col"))}, "column circular bottom on slab top (curved EDGE, planar face)")
# C2 solid cylinder inside a tube (curved cylindrical shared face)
inner=Cyl(500,3000, 12000,2000,0)
tube=Cyl(800,3000, 12000,2000,0).cut(Cyl(500,3000, 12000,2000,0))
fixtures["C2_cyl_in_tube"]=(
    {"core":inner, "tube":tube},
    {frozenset(("core","tube"))}, "solid cylinder R500 inside tube R500..R800 — shared CYLINDRICAL face")
# C3 cylindrical-shell curved wall on slab
outer_sec=Part.makeCylinder(2000,3000,App.Vector(24000,0,200),App.Vector(0,0,1),90)
inner_sec=Part.makeCylinder(1800,3000,App.Vector(24000,0,200),App.Vector(0,0,1),90)
cwall=outer_sec.cut(inner_sec)
fixtures["C3_curved_wall_on_slab"]=(
    {"slab2":Box(3000,3000,200, 23500,-500,0), "cwall":cwall},
    {frozenset(("slab2","cwall"))}, "90deg cylindrical-shell wall standing on slab (annular-sector contact)")

for g,(cells,truth,note) in fixtures.items():
    t0=time.perf_counter(); A=path_a(cells); tA=time.perf_counter()-t0
    bex,skipped=path_b2_exact(cells)
    t0=time.perf_counter(); btess=path_b2_tess(cells); tT=time.perf_counter()-t0
    Afmt = A if isinstance(A,str) else fmt(A)
    rec={"note":note,"truth":fmt(truth),
         "A_OCCT":Afmt,"B2_exact":fmt(bex),"B2_exact_skipped_curved_faces":skipped,
         "B2_tess":fmt(btess),
         "A_eq_truth": (Afmt==fmt(truth)),
         "B2exact_eq_truth": fmt(bex)==fmt(truth),
         "B2tess_eq_truth": fmt(btess)==fmt(truth),
         "timing_ms":{"A":round(tA*1000,2),"B2_tess":round(tT*1000,2)}}
    R["fixtures"][g]=rec

R["answers"]={
    "A_OCCT_handles_all_curved": all(v["A_eq_truth"] for v in R["fixtures"].values()),
    "B2_exact_fails_curved": [g for g,v in R["fixtures"].items() if not v["B2exact_eq_truth"]],
    "B2_tess_results": {g: v["B2tess_eq_truth"] for g,v in R["fixtures"].items()},
    "verdict_curved_needs_OCCT": (all(v["A_eq_truth"] for v in R["fixtures"].values())
                                  and any(not v["B2exact_eq_truth"] for v in R["fixtures"].values())),
}

with open(os.path.join(HERE,"results_gate3.json"),"w") as f:
    json.dump(R,f,indent=2)

print("="*78); print("GATE 3 — CURVED/COMPLEX: A(OCCT) vs B2-exact vs B2-tess"); print("="*78)
for g,v in R["fixtures"].items():
    print(f"\n[{g}] {v['note']}")
    print(f"   truth   ={v['truth']}")
    print(f"   A(OCCT) ={v['A_OCCT']}   (==truth: {v['A_eq_truth']})")
    print(f"   B2_exact={v['B2_exact']}   (==truth: {v['B2exact_eq_truth']}; curved faces skipped: {v['B2_exact_skipped_curved_faces']})")
    print(f"   B2_tess ={v['B2_tess']}   (==truth: {v['B2tess_eq_truth']})")
    print(f"   timing ms: {v['timing_ms']}")
print("\n"+"-"*78); print("ANSWERS:", json.dumps(R["answers"],indent=2))
