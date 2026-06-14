"""
FreeCAD headless spike v2 — IDENTITY LIFECYCLE (the crux).

v1 proved: headless modeling works; STEP/BREP export works; but GlobalId is
NOT present at creation (it appeared only later, after the IFC-export attempt
touched the objects). v2 answers the questions the architecture actually hinges on:

  Q-A  At creation, what is wall.GlobalId? ("" empty, or a value?)
  Q-B  What MINTS the GlobalId, and can I mint it deterministically WITHOUT a
       full IFC export? (so the bundle step controls identity)
  Q-C  THE SEAM: once assigned, does GlobalId survive
           recompute -> save/reopen -> param-change+recompute ?
  Q-D  Fallbacks: are obj.Name / obj.ID stable across the same lifecycle?
  Q-E  Does a CLEAN IFC export (no malformed window) actually work headless,
       or hit the exportIFC GUI-import trap?

No FreeCADGui import anywhere. Defensive: every probe independent.
Run: freecadcmd spike_identity_lifecycle.py
"""
import os, sys, json, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
R = {"version": None, "answers": {}, "probes": [], "fatal": None}

def probe(name, fn):
    rec = {"name": name, "ok": False, "detail": ""}
    try:
        out = fn(); rec["ok"] = True; rec["detail"] = "" if out is None else str(out)
    except Exception as e:
        rec["detail"] = "{}: {}".format(type(e).__name__, e)
        rec["trace"] = traceback.format_exc().splitlines()[-3:]
    R["probes"].append(rec); return rec

import FreeCAD as App
R["version"] = ".".join(str(x) for x in App.Version()[:3])
import Arch
try:
    import Draft
except Exception:
    Draft = None

doc = App.newDocument("idspike")

# --- build a CLEAN wall + slab (no malformed window) ------------------------
baseline = Draft.makeLine(App.Vector(0,0,0), App.Vector(5000,0,0)) if Draft else None
doc.recompute()
wall = Arch.makeWall(baseline, width=200, height=3000)
slab = Arch.makeStructure(length=6000, width=4000, height=200)
doc.recompute()

def gid(o):
    """raw GlobalId value (may be '' )"""
    return getattr(o, "GlobalId", "<<no-attr>>")

# Q-A : state at creation -----------------------------------------------------
def _qa():
    info = {
        "wall_has_GlobalId_attr": hasattr(wall, "GlobalId"),
        "wall_GlobalId_repr": repr(gid(wall)),
        "wall_GlobalId_empty": (gid(wall) == ""),
        "wall_Name": wall.Name,
        "wall_ID": getattr(wall, "ID", None),
        "slab_GlobalId_repr": repr(gid(slab)),
    }
    # list every property whose name smells like identity
    idprops = [p for p in wall.PropertiesList if any(k in p.lower() for k in ("id","guid","uid","uuid"))]
    info["wall_identity_like_props"] = idprops
    R["answers"]["A_at_creation"] = info
    return info
probe("Q-A: identity state at creation", _qa)

# Q-B : deterministic minting WITHOUT full export -----------------------------
def _qb():
    res = {}
    # candidate 1: ifcopenshell guid generator (FreeCAD bundles ifcopenshell)
    try:
        import ifcopenshell.guid as G
        res["ifcopenshell_guid_new"] = G.new()
        res["ifcopenshell_available"] = True
    except Exception as e:
        res["ifcopenshell_available"] = "{}: {}".format(type(e).__name__, e)
    # candidate 2: a minting helper inside the IFC exporter module
    try:
        from importers import exportIFC as E
        helpers = [f for f in dir(E) if any(k in f.lower() for k in ("uid","guid","global"))]
        res["exportIFC_id_helpers"] = helpers
        res["exportIFC_import_ok"] = True   # <- also answers the GUI-trap question
    except Exception as e:
        res["exportIFC_import_ok"] = "{}: {}".format(type(e).__name__, e)
    # try assigning a minted guid to the wall and confirm it sticks in-memory
    try:
        import ifcopenshell.guid as G
        newid = G.new()
        wall.GlobalId = newid
        res["assigned"] = newid
        res["readback_matches"] = (gid(wall) == newid)
    except Exception as e:
        res["assign_error"] = "{}: {}".format(type(e).__name__, e)
    R["answers"]["B_minting"] = res
    return res
probe("Q-B: deterministic GlobalId minting (no full export)", _qb)

# ensure BOTH objects carry a stable id we control, then snapshot -------------
def _ensure_ids():
    try:
        import ifcopenshell.guid as G
        for o in (wall, slab):
            if gid(o) in ("", "<<no-attr>>") and hasattr(o, "GlobalId"):
                o.GlobalId = G.new()
    except Exception:
        pass
    return {o.Name: gid(o) for o in (wall, slab)}
snap0 = probe("ensure ids assigned", _ensure_ids)["detail"]

# Q-C : survival across recompute / save-reopen / param change ----------------
def _snapshot():
    return {o.Name: {"gid": gid(o), "ID": getattr(o,"ID",None)} for o in doc.Objects if o.Name in ("Wall","Structure")}

before = {}
def _cap():
    global before
    before = _snapshot(); return before
probe("capture identities", _cap)

def _survive_recompute():
    doc.recompute()
    after = _snapshot()
    same = {n: before.get(n,{}).get("gid")==after.get(n,{}).get("gid") for n in before}
    R["answers"]["C_recompute"] = {"stable": same, "before": before, "after": after}
    return same
probe("C1: survives recompute", _survive_recompute)

SAVE = os.path.join(HERE, "idspike.FCStd")
def _survive_saveopen():
    global doc
    doc.saveAs(SAVE)
    nm = doc.Name
    App.closeDocument(nm)
    doc = App.openDocument(SAVE)
    after = {}
    for o in doc.Objects:
        if o.Name in ("Wall","Structure"):
            after[o.Name] = {"gid": gid(o), "ID": getattr(o,"ID",None)}
    same = {n: before.get(n,{}).get("gid")==after.get(n,{}).get("gid") for n in before}
    R["answers"]["C_saveopen"] = {"stable": same, "after": after}
    return same
probe("C2: survives save/close/reopen", _survive_saveopen)

def _survive_param():
    w = next((o for o in doc.Objects if o.Name=="Wall"), None)
    if not w: raise RuntimeError("wall missing after reopen")
    gid_before = gid(w)
    try: vol_before = w.Shape.Volume
    except Exception: vol_before = None
    cur = w.Height; w.Height = (cur.Value if hasattr(cur,"Value") else cur)*1.5
    doc.recompute()
    gid_after = gid(w)
    try: vol_after = w.Shape.Volume
    except Exception: vol_after = None
    out = {"gid_before": gid_before, "gid_after": gid_after,
           "id_stable": gid_before==gid_after,
           "vol_before": vol_before, "vol_after": vol_after,
           "geometry_changed": (vol_before!=vol_after) if (vol_before and vol_after) else None}
    R["answers"]["C_param_change_THE_SEAM"] = out
    return out
probe("C3: survives param-change+recompute (THE SEAM)", _survive_param)

# Q-D : Name / ID as fallback identities -------------------------------------
def _qd():
    w = next((o for o in doc.Objects if o.Name=="Wall"), None)
    R["answers"]["D_fallbacks"] = {
        "wall_Name_stable": (w.Name=="Wall"),
        "wall_ID": getattr(w,"ID",None),
        "note": "Name is unique-per-doc & immutable; ID is int unique-per-doc. Neither is globally unique across docs/bundles."
    }
    return R["answers"]["D_fallbacks"]
probe("Q-D: Name/ID fallback identity", _qd)

# Q-E : clean IFC export (trap probe, no malformed window) --------------------
def _qe():
    from importers import exportIFC as E
    p = os.path.join(HERE, "reference_clean.ifc")
    objs = [o for o in doc.Objects if o.Name in ("Wall","Structure")]
    E.export(objs, p)
    R["answers"]["E_ifc_export"] = {"ok": True, "path": p, "bytes": os.path.getsize(p)}
    # did export (re)write GlobalIds we can read back?
    R["answers"]["E_ifc_export"]["wall_gid_after_export"] = gid(next(o for o in objs if o.Name=="Wall"))
    return R["answers"]["E_ifc_export"]
probe("Q-E: clean headless IFC export (trap probe)", _qe)

with open(os.path.join(HERE,"results_v2.json"),"w") as f:
    json.dump(R, f, indent=2, default=str)

print("="*70); print("IDENTITY LIFECYCLE SPIKE — FreeCAD", R["version"]); print("="*70)
for p in R["probes"]:
    print(("  PASS " if p["ok"] else "  FAIL "), p["name"])
    if p["detail"]: print("        ", p["detail"][:240])
print("-"*70)
print(json.dumps(R["answers"], indent=2, default=str))
