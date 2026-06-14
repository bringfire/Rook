"""
FreeCAD headless BIM spike — run via FreeCADCmd.

Proves (or disproves) the load-bearing assumptions for the
FreeCAD -> Rook -> Rhino architecture:

  1. Arch/BIM object creation works under FreeCADCmd (no GUI).
  2. A persistent stable identity field exists on BIM objects.
  3. That identity SURVIVES: recompute, save/reopen, parameter-change+recompute.
  4. Headless reference-geometry export works (STEP / BREP; IFC best-effort).
  5. A minimal blueprint.json can be emitted from the live document.

Run:  FreeCADCmd spike_headless_bim.py
Outputs land next to this script: results.json, blueprint.json, reference.step, reference.brep
The whole thing is defensive: every step is independently try/excepted so a
partial run still yields signal. Nothing here imports FreeCADGui.
"""

import os
import sys
import json
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = HERE  # write artifacts beside the script

results = {
    "freecad_version": None,
    "freecad_cmd": sys.executable,
    "gui_up": None,
    "steps": [],          # ordered list of {name, ok, detail}
    "identity_field": None,
    "identity_survives": {},
    "exports": {},
    "blueprint_objects": 0,
    "fatal": None,
}


def step(name, fn):
    """Run fn(), record ok/detail, never raise."""
    rec = {"name": name, "ok": False, "detail": ""}
    try:
        out = fn()
        rec["ok"] = True
        rec["detail"] = "" if out is None else str(out)
    except Exception as e:
        rec["detail"] = "{}: {}".format(type(e).__name__, e)
        rec["trace"] = traceback.format_exc().splitlines()[-4:]
    results["steps"].append(rec)
    return rec


def identity_of(obj):
    """Probe whatever stable identity FreeCAD exposes on a BIM object.
    Returns (field_name, value) or (None, None)."""
    # Newer BIM exposes obj.GlobalId (App::PropertyString, IFC GUID).
    for field in ("GlobalId",):
        val = getattr(obj, field, None)
        if val:
            return field, val
    # Fallback: IfcData dict may carry IfcUID / GlobalId.
    ifc = getattr(obj, "IfcData", None)
    if isinstance(ifc, dict):
        for k in ("IfcUID", "GlobalId", "Id"):
            if ifc.get(k):
                return "IfcData[{}]".format(k), ifc[k]
    return None, None


# ---- 0. import core (no GUI) ----------------------------------------------
App = None


def _imp():
    global App
    import FreeCAD as _App
    App = _App
    results["freecad_version"] = ".".join(str(x) for x in App.Version()[:3]) + " (" + App.Version()[3] + ")"
    results["gui_up"] = bool(getattr(App, "GuiUp", None))
    return results["freecad_version"]


step("import FreeCAD (App, no GUI)", _imp)
if App is None:
    results["fatal"] = "FreeCAD App import failed — cannot continue"
    print(json.dumps(results, indent=2))
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(results, f, indent=2)
    sys.exit(1)


def _imp_arch():
    import Arch  # noqa: F401  compat module; pulls App-layer makeWall etc.
    return "Arch imported"


arch_ok = step("import Arch (BIM App layer)", _imp_arch)["ok"]

doc = App.newDocument("spike")
objects = {}  # role -> obj


# ---- 1. create BIM objects -------------------------------------------------
def _make_wall():
    import Arch
    baseline = None
    try:
        import Draft
        baseline = Draft.makeLine(App.Vector(0, 0, 0), App.Vector(5000, 0, 0))
        doc.recompute()
    except Exception:
        baseline = None  # fall back to baseline-less wall
    wall = Arch.makeWall(baseline, length=5000 if baseline is None else None,
                         width=200, height=3000)
    objects["wall"] = wall
    if baseline is not None:
        objects["baseline"] = baseline
    return "wall={} baseline={}".format(wall.Name, getattr(baseline, "Name", None))


def _make_slab():
    import Arch
    # A slab as a Structure with a large footprint.
    slab = Arch.makeStructure(length=6000, width=4000, height=200)
    objects["slab"] = slab
    return slab.Name


def _make_opening():
    # Window/opening is the hardest headless case — best-effort.
    import Arch
    wall = objects.get("wall")
    win = Arch.makeWindow(width=900, height=1200)
    objects["window"] = win
    if wall is not None:
        try:
            win.Hosts = [wall]  # establish hosted/voids relationship
        except Exception:
            pass
    return win.Name


if arch_ok:
    step("makeWall (headless)", _make_wall)
    step("makeStructure / slab (headless)", _make_slab)
    step("makeWindow / opening (headless, best-effort)", _make_opening)
    step("recompute after creation", lambda: doc.recompute())


# ---- 2. identity field exists ----------------------------------------------
def _probe_identity():
    wall = objects.get("wall")
    if wall is None:
        raise RuntimeError("no wall to probe")
    field, val = identity_of(wall)
    results["identity_field"] = field
    if not field:
        raise RuntimeError("no GlobalId / IfcUID found on wall")
    return "{} = {}".format(field, val)


step("identity field present on wall", _probe_identity)


# ---- 3. identity survival --------------------------------------------------
def _snapshot_ids():
    ids = {}
    for role, obj in objects.items():
        f, v = identity_of(obj)
        ids[role] = v
    return ids


baseline_ids = {}


def _capture_baseline():
    global baseline_ids
    baseline_ids = _snapshot_ids()
    return baseline_ids


def _survive_recompute():
    doc.recompute()
    now = _snapshot_ids()
    same = {r: (baseline_ids.get(r) == now.get(r)) for r in baseline_ids}
    results["identity_survives"]["recompute"] = same
    if not all(v for k, v in same.items() if baseline_ids.get(k)):
        raise RuntimeError("identity changed on recompute: {}".format(same))
    return same


SAVE_PATH = os.path.join(OUT, "spike.FCStd")


def _survive_saveopen():
    global doc
    doc.saveAs(SAVE_PATH)
    name = doc.Name
    App.closeDocument(name)
    doc = App.openDocument(SAVE_PATH)
    # rebind objects by Name
    for role in list(objects.keys()):
        nm = objects[role].Name if hasattr(objects[role], "Name") else None
        # after reopen the python proxy is stale; re-fetch
    reopened = {}
    for o in doc.Objects:
        reopened[o.Name] = o
    # remap by stored names captured before close
    return "reopened {} objects".format(len(doc.Objects))


def _survive_paramchange():
    # find the wall again in the (possibly reopened) doc
    wall = None
    for o in doc.Objects:
        if "Wall" in o.Name:
            wall = o
            break
    if wall is None:
        raise RuntimeError("wall not found after reopen")
    f_before, id_before = identity_of(wall)
    # capture geometry metric before
    vol_before = None
    try:
        vol_before = wall.Shape.Volume
    except Exception:
        pass
    # change a parameter
    changed_what = None
    for prop in ("Height", "Length", "Width"):
        if hasattr(wall, prop):
            try:
                cur = getattr(wall, prop)
                newval = (cur.Value if hasattr(cur, "Value") else cur) * 1.5
                setattr(wall, prop, newval)
                changed_what = prop
                break
            except Exception:
                continue
    doc.recompute()
    f_after, id_after = identity_of(wall)
    vol_after = None
    try:
        vol_after = wall.Shape.Volume
    except Exception:
        pass
    results["identity_survives"]["param_change"] = {
        "changed": changed_what,
        "id_before": id_before,
        "id_after": id_after,
        "id_stable": id_before == id_after,
        "vol_before": vol_before,
        "vol_after": vol_after,
        "geometry_changed": (vol_before != vol_after) if (vol_before and vol_after) else None,
    }
    if id_before != id_after:
        raise RuntimeError("identity changed on param edit")
    return results["identity_survives"]["param_change"]


if results.get("identity_field"):
    step("capture baseline identities", _capture_baseline)
    step("identity survives recompute", _survive_recompute)
    step("identity survives save/reopen", _survive_saveopen)
    step("identity survives param-change+recompute (THE SEAM)", _survive_paramchange)


# ---- 4. reference geometry export -----------------------------------------
def _export_step():
    import Part
    shapes = [o for o in doc.Objects if getattr(o, "Shape", None) and not o.Shape.isNull()]
    if not shapes:
        raise RuntimeError("no shapes to export")
    p = os.path.join(OUT, "reference.step")
    Part.export(shapes, p)
    results["exports"]["step"] = {"path": p, "bytes": os.path.getsize(p)}
    return results["exports"]["step"]


def _export_brep():
    shapes = [o for o in doc.Objects if getattr(o, "Shape", None) and not o.Shape.isNull()]
    if not shapes:
        raise RuntimeError("no shapes")
    import Part
    comp = Part.Compound([o.Shape for o in shapes])
    p = os.path.join(OUT, "reference.brep")
    comp.exportBrep(p)
    results["exports"]["brep"] = {"path": p, "bytes": os.path.getsize(p)}
    return results["exports"]["brep"]


def _export_ifc():
    # secondary; expected to hit the exportIFC.py GUI-import trap on the source
    # checkout — we want to know if the *packaged 1.1.1* has the same problem.
    import importers.exportIFC as eIFC  # this import is the trap
    p = os.path.join(OUT, "reference.ifc")
    eIFC.export([o for o in doc.Objects], p)
    results["exports"]["ifc"] = {"path": p, "bytes": os.path.getsize(p)}
    return results["exports"]["ifc"]


step("export STEP (reference geometry)", _export_step)
step("export BREP (reference geometry)", _export_brep)
step("export IFC (secondary, trap probe)", _export_ifc)


# ---- 5. emit minimal blueprint.json ---------------------------------------
def _emit_blueprint():
    objs = []
    for o in doc.Objects:
        f, ident = identity_of(o)
        bbox = None
        try:
            bb = o.Shape.BoundBox
            bbox = [round(bb.XMin, 1), round(bb.YMin, 1), round(bb.ZMin, 1),
                    round(bb.XMax, 1), round(bb.YMax, 1), round(bb.ZMax, 1)]
        except Exception:
            pass
        depends_on = []
        try:
            depends_on = [d.Name for d in o.OutList]
        except Exception:
            pass
        depended_by = []
        try:
            depended_by = [d.Name for d in o.InList]
        except Exception:
            pass
        params = {}
        for prop in ("Length", "Width", "Height"):
            if hasattr(o, prop):
                v = getattr(o, prop)
                params[prop] = v.Value if hasattr(v, "Value") else v
        objs.append({
            "id": ident,
            "identityField": f,
            "name": o.Name,
            "label": getattr(o, "Label", None),
            "kind": o.TypeId,
            "ifcType": getattr(o, "IfcType", None) or getattr(o, "Role", None),
            "params": params,
            "bbox": bbox,
            "dependsOn": depends_on,
            "dependedOnBy": depended_by,
        })
    bp = {"schemaVersion": "spike-0", "source": "FreeCAD", "objects": objs}
    p = os.path.join(OUT, "blueprint.json")
    with open(p, "w") as fh:
        json.dump(bp, fh, indent=2)
    results["blueprint_objects"] = len(objs)
    return "{} objects -> {}".format(len(objs), p)


step("emit blueprint.json", _emit_blueprint)


# ---- write results ---------------------------------------------------------
with open(os.path.join(OUT, "results.json"), "w") as f:
    json.dump(results, f, indent=2)

print("=" * 70)
print("FREECAD HEADLESS BIM SPIKE — RESULTS")
print("=" * 70)
print("FreeCAD:", results["freecad_version"], "| GuiUp:", results["gui_up"])
print("Identity field:", results["identity_field"])
print("-" * 70)
for s in results["steps"]:
    print(("  PASS  " if s["ok"] else "  FAIL  "), s["name"])
    if s["detail"]:
        print("          ", s["detail"][:200])
print("-" * 70)
print("identity_survives:", json.dumps(results["identity_survives"], indent=2))
print("exports:", json.dumps(results["exports"], indent=2))
print("blueprint objects:", results["blueprint_objects"])
print("=" * 70)
