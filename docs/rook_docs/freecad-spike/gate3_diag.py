"""
GATE 3 DIAGNOSTIC — is the curved-case failure OCCT's incapability, or my naive
Path-A invocation (generalFuse+isSame)? Test the CORRECT OCCT coincidence primitives
on the two cases my Path A failed (C2 cyl-in-tube, C3 curved-wall-on-slab).

If OCCT 'sees' the coincident faces via distToShape / section, then OCCT is capable
and my generalFuse method was the wrong primitive (it drops internal interfaces when
solids merge). Run: freecadcmd gate3_diag.py
"""
import os, json, itertools
import FreeCAD as App
import Part
HERE=os.path.dirname(os.path.abspath(__file__)); R={}

def Cyl(r,h,x,y,z): return Part.makeCylinder(r,h,App.Vector(x,y,z),App.Vector(0,0,1))
def Box(L,W,H,x,y,z): return Part.makeBox(L,W,H,App.Vector(x,y,z))

cases={}
inner=Cyl(500,3000,0,0,0); tube=Cyl(800,3000,0,0,0).cut(Cyl(500,3000,0,0,0))
cases["C2_cyl_in_tube"]=(inner,tube)
outer_sec=Part.makeCylinder(2000,3000,App.Vector(0,0,200),App.Vector(0,0,1),90)
inner_sec=Part.makeCylinder(1800,3000,App.Vector(0,0,200),App.Vector(0,0,1),90)
cwall=outer_sec.cut(inner_sec); slab2=Box(3000,3000,200,-500,-500,0)
cases["C3_curved_wall_on_slab"]=(slab2,cwall)

for name,(s1,s2) in cases.items():
    rec={}
    # 1) solid-solid min distance (do they touch at all?)
    try:
        d=s1.distToShape(s2); rec["solid_solid_mindist"]=round(d[0],6)
    except Exception as e: rec["solid_solid_mindist"]="ERR %s"%e
    # 2) coincident FACE pairs: distToShape==0 AND each face overlaps a real area
    coincident=[]
    for i,f1 in enumerate(s1.Faces):
        for j,f2 in enumerate(s2.Faces):
            try:
                dd=f1.distToShape(f2)[0]
            except Exception:
                continue
            if dd<1e-6:
                # shared region area via common of the two faces
                try:
                    common=f1.common(f2)
                    area=sum(f.Area for f in common.Faces) if common.Faces else 0.0
                except Exception:
                    area=-1
                coincident.append({"f1":i,"f2":j,"dist":round(dd,6),
                                   "f1_type":str(f1.Surface)[:24],"shared_area":round(area,1)})
    rec["coincident_face_pairs"]=coincident
    rec["OCCT_sees_shared_face"]=any(c.get("shared_area",0)>1.0 for c in coincident)
    # 3) what did pairwise generalFuse produce? (did they merge -> interface lost?)
    try:
        fused,fmap=s1.generalFuse([s2])
        rec["generalFuse_result_solids"]=len(fused.Solids)
    except Exception as e:
        rec["generalFuse_result_solids"]="ERR %s"%e
    R[name]=rec

with open(os.path.join(HERE,"results_gate3_diag.json"),"w") as f:
    json.dump(R,f,indent=2)
print("GATE 3 DIAGNOSTIC — does OCCT SEE the coincident curved faces?")
print(json.dumps(R,indent=2))
