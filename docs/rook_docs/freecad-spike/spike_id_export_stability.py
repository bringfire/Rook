"""
FreeCAD headless spike v3 — IDENTITY EXPORT-STABILITY (settles the spine choice).

v2 surprise: IFC export OVERWROTE a GlobalId we had set. That threatens using
GlobalId as the single cross-system identity spine. This decides between:
  (1) GlobalId-as-spine  -> only viable if exporter preserves a pre-set value
  (2) Rook-owned property -> a custom App::PropertyString we control, that
                             FreeCAD's exporters never rewrite

Tests, on a clean wall+slab:
  T1  Set GlobalId explicitly. Add a custom 'RookId' property, set it.
  T2  Export IFC. Does GlobalId survive? Does RookId survive?
  T3  save/reopen. Does the custom RookId persist in the .FCStd?
  T4  param-change+recompute after reopen. Does RookId stay stable?
Run: freecadcmd spike_id_export_stability.py
"""
import os, json, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
R = {"tests": [], "answers": {}}

def T(name, fn):
    rec={"name":name,"ok":False,"detail":""}
    try:
        o=fn(); rec["ok"]=True; rec["detail"]="" if o is None else str(o)
    except Exception as e:
        rec["detail"]="{}: {}".format(type(e).__name__,e)
        rec["trace"]=traceback.format_exc().splitlines()[-3:]
    R["tests"].append(rec); return rec

import FreeCAD as App
import Arch
try: import Draft
except Exception: Draft=None
import ifcopenshell.guid as G

doc=App.newDocument("idstab")
base=Draft.makeLine(App.Vector(0,0,0),App.Vector(5000,0,0)) if Draft else None
doc.recompute()
wall=Arch.makeWall(base,width=200,height=3000)
slab=Arch.makeStructure(length=6000,width=4000,height=200)
doc.recompute()

def gid(o): return getattr(o,"GlobalId","<none>")
def rid(o): return getattr(o,"RookId","<none>")

SET_GID="11111111111111111111aa"
def _t1():
    for o in (wall,slab):
        o.GlobalId = G.new()
    wall.GlobalId = SET_GID  # a known sentinel so we can spot overwrites
    # custom Rook-owned property
    for o in (wall,slab):
        if "RookId" not in o.PropertiesList:
            o.addProperty("App::PropertyString","RookId","Rook","Rook stable identity")
        o.RookId = "rook-"+G.new()
    return {"wall_gid": gid(wall), "wall_rid": rid(wall)}
T("T1: assign sentinel GlobalId + custom RookId", _t1)

wall_gid_set = gid(wall); wall_rid_set = rid(wall)

def _t2():
    from importers import exportIFC as E
    p=os.path.join(HERE,"idstab.ifc")
    E.export([wall,slab],p)
    out={"gid_before":wall_gid_set,"gid_after":gid(wall),
         "gid_survived_export": gid(wall)==wall_gid_set,
         "rid_before":wall_rid_set,"rid_after":rid(wall),
         "rid_survived_export": rid(wall)==wall_rid_set,
         "ifc_bytes":os.path.getsize(p)}
    R["answers"]["export_stability"]=out
    return out
T("T2: IFC export — what survives?", _t2)

SAVE=os.path.join(HERE,"idstab.FCStd")
def _t3():
    global doc
    doc.saveAs(SAVE); nm=doc.Name; App.closeDocument(nm); doc=App.openDocument(SAVE)
    w=next(o for o in doc.Objects if o.Name=="Wall")
    out={"rid_persisted": rid(w)==wall_rid_set, "rid_value": rid(w),
         "gid_value": gid(w),
         "RookId_in_props": "RookId" in w.PropertiesList}
    R["answers"]["saveopen_custom_prop"]=out
    return out
T("T3: custom RookId persists in .FCStd", _t3)

def _t4():
    w=next(o for o in doc.Objects if o.Name=="Wall")
    rb=rid(w); cur=w.Height; w.Height=(cur.Value if hasattr(cur,"Value") else cur)*1.25
    doc.recompute()
    out={"rid_before":rb,"rid_after":rid(w),"rid_stable":rb==rid(w)}
    R["answers"]["param_change_custom_prop"]=out
    return out
T("T4: RookId stable across param-change+recompute", _t4)

with open(os.path.join(HERE,"results_v3.json"),"w") as f:
    json.dump(R,f,indent=2,default=str)

print("="*70); print("IDENTITY EXPORT-STABILITY SPIKE"); print("="*70)
for t in R["tests"]:
    print(("  PASS " if t["ok"] else "  FAIL "), t["name"])
    if t["detail"]: print("        ", t["detail"][:240])
print("-"*70); print(json.dumps(R["answers"],indent=2,default=str))
