"""
FreeCAD headless spike v4 — VALID ONE-STOREY SOURCE PACKAGE.

Addresses review findings:
  - real hosted opening that actually CUTS the wall (no null-shape poisoning)
  - RookId minting with a PERSISTENCE RULE (read-existing-else-mint) + write-back
    to .FCStd, proven IDEMPOTENT across reopen (no ID churn on repeated export)
  - clean RookId-keyed blueprint.json with real voids/hosts relationships
  - probe the FREECAD SIDE of the export-mapping question: what identity actually
    lands inside reference.step / reference.ifc? (the Rhino-import side is a
    separate spike that needs a live Rhino)

No FreeCADGui. Run: freecadcmd spike_valid_storey.py
"""
import os, json, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
R = {"version": None, "steps": [], "opening_method": None, "minting": {}, "mapping_probe": {}, "blueprint_objects": 0}

def S(name, fn):
    rec={"name":name,"ok":False,"detail":""}
    try:
        o=fn(); rec["ok"]=True; rec["detail"]="" if o is None else str(o)
    except Exception as e:
        rec["detail"]="{}: {}".format(type(e).__name__,e); rec["trace"]=traceback.format_exc().splitlines()[-3:]
    R["steps"].append(rec); return rec

import FreeCAD as App
import Arch, Part
try: import Draft
except Exception: Draft=None
import ifcopenshell.guid as G
R["version"]=".".join(str(x) for x in App.Version()[:3])

doc=App.newDocument("storey")

# --- build wall + slab ------------------------------------------------------
base=Draft.makeLine(App.Vector(0,0,0),App.Vector(5000,0,0))
doc.recompute()
wall=Arch.makeWall(base,width=200,height=3000)
slab=Arch.makeStructure(length=6000,width=4000,height=300)
slab.Label="Slab"
slab.Placement=App.Placement(App.Vector(2500,0,-300),App.Rotation())
doc.recompute()
SOLID_WALL_VOL=wall.Shape.Volume   # expect 5000*200*3000 = 3.0e9

# --- real hosted opening: try Window, fall back to box subtraction -----------
opening=None
def _opening():
    global opening
    # Approach A: proper Arch Window with a base rectangle in the wall plane
    try:
        rect=Draft.makeRectangle(900,1200)
        # wall runs along X at Y~0; window plane = XZ -> rotate rect 90deg about X
        rect.Placement=App.Placement(App.Vector(2000,100,800),App.Rotation(App.Vector(1,0,0),90))
        doc.recompute()
        win=Arch.makeWindow(rect,width=220)   # 220 > wall width 200 -> full penetration
        win.Hosts=[wall]
        doc.recompute()
        v=wall.Shape.Volume
        if wall.Shape.isValid() and 0 < v < SOLID_WALL_VOL*0.999:
            opening=win; R["opening_method"]="Window"
            return {"method":"Window","wall_vol":v,"solid_vol":SOLID_WALL_VOL,"cut":SOLID_WALL_VOL-v}
        # didn't cut -> abandon window, remove it
        try:
            doc.removeObject(win.Name); doc.removeObject(rect.Name); doc.recompute()
        except Exception: pass
    except Exception as e:
        R["mapping_probe"]["window_error"]="{}: {}".format(type(e).__name__,e)
    # Approach B: box subtraction (robust IfcOpeningElement-style void)
    box=doc.addObject("Part::Box","Opening")
    box.Length=900; box.Width=400; box.Height=1200
    box.Placement=App.Placement(App.Vector(2000,-100,800),App.Rotation())
    doc.recompute()
    Arch.removeComponents(box,host=wall)
    doc.recompute()
    v=wall.Shape.Volume
    opening=box; R["opening_method"]="box-subtraction"
    return {"method":"box-subtraction","wall_vol":v,"solid_vol":SOLID_WALL_VOL,"cut":SOLID_WALL_VOL-v,
            "wall_valid":wall.Shape.isValid()}
S("real hosted opening that cuts the wall", _opening)

# --- RookId persistence rule (read-existing-else-mint) -----------------------
def ensure_rookid(obj):
    if "RookId" not in obj.PropertiesList:
        obj.addProperty("App::PropertyString","RookId","Rook","Rook stable identity")
    if not getattr(obj,"RookId",""):
        obj.RookId="rook-"+G.new(); return "minted"
    return "kept"

SEMANTIC_NAMES=[wall.Name, slab.Name, opening.Name]
def _mint_pass1():
    out={o.Name:ensure_rookid(o) for o in (wall,slab,opening)}
    R["minting"]["pass1"]=out
    return out
S("mint pass 1 (fresh objects -> all minted)", _mint_pass1)

SAVE=os.path.join(HERE,"storey.FCStd")
def _save_reopen_idempotent():
    global doc
    doc.saveAs(SAVE)
    App.closeDocument(doc.Name)
    doc=App.openDocument(SAVE)
    sem=[o for o in doc.Objects if o.Name in SEMANTIC_NAMES]
    out={o.Name:ensure_rookid(o) for o in sem}     # MUST all be "kept"
    R["minting"]["pass2_after_reopen"]=out
    R["minting"]["idempotent"]=all(v=="kept" for v in out.values())
    if not R["minting"]["idempotent"]:
        raise RuntimeError("RookId churned on reopen: {}".format(out))
    return out
S("mint pass 2 after save/reopen -> idempotent (no churn)", _save_reopen_idempotent)

# rebind live refs from reopened doc
wall=next(o for o in doc.Objects if o.Name==SEMANTIC_NAMES[0])
slab=next(o for o in doc.Objects if o.Name==SEMANTIC_NAMES[1])
opening=next(o for o in doc.Objects if o.Name==SEMANTIC_NAMES[2])
NAME2ROOK={o.Name:getattr(o,"RookId","") for o in doc.Objects if getattr(o,"RookId","")}

# --- clean RookId-keyed blueprint.json --------------------------------------
def _blueprint():
    SEM=set(NAME2ROOK.keys())
    def rid(o): return getattr(o,"RookId","") or None
    def bbox(o):
        try:
            bb=o.Shape.BoundBox
            if bb.XMin>1e300: return None  # uninitialized/invalid
            return [round(bb.XMin,1),round(bb.YMin,1),round(bb.ZMin,1),round(bb.XMax,1),round(bb.YMax,1),round(bb.ZMax,1)]
        except Exception: return None
    objs=[]
    for o in doc.Objects:
        subtr=[]
        try: subtr=[s.Name for s in getattr(o,"Subtractions",[]) or []]
        except Exception: pass
        hosts=[]
        try: hosts=[h.Name for h in getattr(o,"Hosts",[]) or []]
        except Exception: pass
        params={p:(getattr(o,p).Value if hasattr(getattr(o,p),"Value") else getattr(o,p)) for p in ("Length","Width","Height") if hasattr(o,p)}
        objs.append({
            "rookId": rid(o),
            "ifcGlobalId": getattr(o,"GlobalId","") or None,   # secondary, volatile on export
            "name": o.Name, "label": getattr(o,"Label",None),
            "semantic": o.Name in SEM,
            "kind": o.TypeId, "ifcType": getattr(o,"IfcType",None) or getattr(o,"Role",None),
            "params": params, "bbox": bbox(o),
            "dependsOn":[NAME2ROOK.get(d.Name,d.Name) for d in getattr(o,"OutList",[])],
            "dependedOnBy":[NAME2ROOK.get(d.Name,d.Name) for d in getattr(o,"InList",[])],
            "voids":[NAME2ROOK.get(n,n) for n in subtr],          # this element is voided by these
            "hostedBy":[NAME2ROOK.get(n,n) for n in hosts] or None,
        })
    bp={"schemaVersion":"storey-1","source":"FreeCAD "+R["version"],
        "identitySpine":"rookId (Rook-owned App::PropertyString; durable). ifcGlobalId is secondary & regenerated on IFC export.",
        "objects":objs}
    with open(os.path.join(HERE,"blueprint.json"),"w") as f:
        json.dump(bp,f,indent=2)
    R["blueprint_objects"]=len(objs)
    return "{} objects; semantic={}".format(len(objs),sorted(SEM))
S("emit clean RookId-keyed blueprint.json", _blueprint)

# --- export reference geometry ----------------------------------------------
STEP=os.path.join(HERE,"reference.step"); IFC=os.path.join(HERE,"reference.ifc")
def _export():
    shapes=[o for o in doc.Objects if getattr(o,"Shape",None) and not o.Shape.isNull() and o.Shape.isValid()]
    Part.export(shapes,STEP)
    from importers import exportIFC as E
    E.export([o for o in doc.Objects if o.Name in SEMANTIC_NAMES], IFC)
    return {"step_bytes":os.path.getsize(STEP),"ifc_bytes":os.path.getsize(IFC),"step_shapes":len(shapes)}
S("export reference.step + reference.ifc", _export)

# --- MAPPING PROBE: what identity survives INTO the exchange files? ----------
def _mapping_probe():
    out={}
    try:
        st=open(STEP,errors="ignore").read()
        out["step_contains_label_Wall"]= "Wall" in st
        out["step_contains_label_Slab"]= "Slab" in st
        out["step_contains_any_rookId"]= any((rid in st) for rid in NAME2ROOK.values())
        # STEP product names live in PRODUCT( '...' ) entities
        import re
        prods=re.findall(r"PRODUCT\(\s*'([^']*)'", st)
        out["step_product_names"]=prods[:20]
    except Exception as e:
        out["step_error"]="{}: {}".format(type(e).__name__,e)
    try:
        ic=open(IFC,errors="ignore").read()
        out["ifc_contains_label_Wall"]= "Wall" in ic
        out["ifc_contains_any_rookId"]= any((rid in ic) for rid in NAME2ROOK.values())
        import re
        gids=re.findall(r"IFCWALL\('([^']*)'", ic) + re.findall(r"IFCWALLSTANDARDCASE\('([^']*)'", ic)
        out["ifc_wall_globalids"]=gids[:10]
    except Exception as e:
        out["ifc_error"]="{}: {}".format(type(e).__name__,e)
    R["mapping_probe"].update(out)
    return out
S("MAPPING PROBE: identity inside STEP/IFC", _mapping_probe)

with open(os.path.join(HERE,"results_v4.json"),"w") as f:
    json.dump(R,f,indent=2,default=str)

print("="*72); print("VALID ONE-STOREY PACKAGE SPIKE — FreeCAD",R["version"]); print("="*72)
for s in R["steps"]:
    print(("  PASS " if s["ok"] else "  FAIL "), s["name"])
    if s["detail"]: print("        ", s["detail"][:260])
print("-"*72)
print("opening_method:", R["opening_method"])
print("minting:", json.dumps(R["minting"],indent=2))
print("mapping_probe:", json.dumps(R["mapping_probe"],indent=2,default=str)[:1500])
