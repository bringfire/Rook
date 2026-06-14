"""
FreeCAD headless spike v5 — INTERIORS LAYOUT FITNESS.

Question (before committing FreeCAD to the interiors/Shimmer brief): does FreeCAD's
*runtime* actually do the interiors "layout/relationship compiler" work, or would
Rook write the same logic regardless — making FreeCAD just a box + property bag here?

Codex's claim is FreeCAD = "layout/relationship compiler" (zones, containment,
adjacency, clearance, repeatable regeneration). Test each load-bearing capability:

  P1  Arch Space (IfcSpace) headless: does makeSpace auto-compute area/volume/boundary?
  P2  Spatial CONTAINMENT: does FreeCAD auto-know "this furniture is in this zone",
      or must I compute point-in-volume myself?
  P3  Dependency GRAPH from placement: does placing furniture in a zone create any
      OutList/InList relationship? (the thing blueprint.json would need)
  P4  CONSTRAINT maintenance for 3D layout: is there any core solver that keeps
      "chair 0.9m from table" / "aisle >= 1.2m" true across recompute?
  P5  REFLOW: resize the envelope/zone, recompute — does anything move automatically?

Verdict per probe: FREECAD-NATIVE (it does it for me) vs ROOK-WOULD-DO-ANYWAY.
No FreeCADGui. Run: freecadcmd spike_interiors_layout.py
"""
import os, json, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
R = {"version": None, "probes": [], "verdicts": {}}

def P(name, fn):
    rec = {"name": name, "ok": False, "detail": ""}
    try:
        o = fn(); rec["ok"] = True; rec["detail"] = "" if o is None else str(o)
    except Exception as e:
        rec["detail"] = "{}: {}".format(type(e).__name__, e); rec["trace"] = traceback.format_exc().splitlines()[-3:]
    R["probes"].append(rec); return rec

import FreeCAD as App
import Arch, Part
try: import Draft
except Exception: Draft = None
R["version"] = ".".join(str(x) for x in App.Version()[:3])

doc = App.newDocument("interiors")

# --- envelope 10x10x7 (a room shell as a hollow box would be heavy; use a floor slab + a Space) ---
floor = doc.addObject("Part::Box", "Floor")
floor.Length = 10000; floor.Width = 10000; floor.Height = 200
floor.Placement = App.Placement(App.Vector(0, 0, -200), App.Rotation())
doc.recompute()

# --- P1: Arch Space for a 'dining' zone --------------------------------------
space = None
def _p1():
    global space
    # Build a solid representing the dining zone volume, then makeSpace from it
    zonebox = doc.addObject("Part::Box", "DiningZoneSolid")
    zonebox.Length = 6000; zonebox.Width = 5000; zonebox.Height = 7000
    zonebox.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation())
    doc.recompute()
    space = Arch.makeSpace(zonebox)
    doc.recompute()
    out = {
        "made": space.Name,
        "has_Area": hasattr(space, "Area"),
        "Area": getattr(getattr(space, "Area", None), "Value", None),
        "props_sample": [p for p in space.PropertiesList if any(k in p.lower() for k in ("area","volume","boundar","zone","group","contain","finish"))],
        "ifcType": getattr(space, "IfcType", None),
    }
    # try volume
    try: out["shape_volume"] = space.Shape.Volume
    except Exception as e: out["shape_volume_err"] = str(e)
    R["verdicts"]["P1_space"] = "FREECAD-NATIVE: IfcSpace object with auto area/volume" if out.get("Area") or out.get("shape_volume") else "WEAK"
    return out
P("P1: Arch Space auto-computes area/volume/boundary", _p1)

# --- furniture proxies inside the dining zone --------------------------------
table = doc.addObject("Part::Box", "Table_proxy")
table.Length = 1200; table.Width = 800; table.Height = 750
table.Placement = App.Placement(App.Vector(2000, 2000, 0), App.Rotation())
chair = doc.addObject("Part::Box", "Chair_proxy")
chair.Length = 500; chair.Width = 500; chair.Height = 900
chair.Placement = App.Placement(App.Vector(2000, 1300, 0), App.Rotation())
doc.recompute()

# --- P2: spatial containment — does FreeCAD auto-know furniture is in the zone? ---
def _p2():
    out = {}
    # candidate 1: Arch.getContainer / getHost
    for helper in ("getContainer", "getHost", "getSpaceBoundaries"):
        fn = getattr(Arch, helper, None)
        if fn is None:
            out[helper] = "<no such helper>"
            continue
        try:
            out[helper] = str(fn(table))
        except Exception as e:
            out[helper] = "ERR {}: {}".format(type(e).__name__, e)
    # candidate 2: does the Space list contained objects automatically?
    out["space_Group"] = [o.Name for o in getattr(space, "Group", []) or []]
    out["space_Boundaries"] = str(getattr(space, "Boundaries", "<none>"))
    # candidate 3: must we compute it ourselves? (point-in-bbox) — show it's trivial
    tb = table.Shape.BoundBox; zb = space.Shape.BoundBox
    inside = (zb.XMin <= tb.Center.x <= zb.XMax and zb.YMin <= tb.Center.y <= zb.YMax)
    out["manual_point_in_bbox"] = inside
    auto = bool(out["space_Group"]) or (isinstance(out.get("getContainer"), str) and "Space" in str(out.get("getContainer")))
    R["verdicts"]["P2_containment"] = ("FREECAD-NATIVE: zone auto-lists contents" if auto
                                       else "ROOK-WOULD-DO-ANYWAY: containment is manual point-in-volume (trivial in Rook)")
    return out
P("P2: spatial containment auto-detected vs manual", _p2)

# --- P3: dependency graph from placement -------------------------------------
def _p3():
    out = {
        "table_OutList": [o.Name for o in getattr(table, "OutList", [])],
        "table_InList": [o.Name for o in getattr(table, "InList", [])],
        "space_OutList": [o.Name for o in getattr(space, "OutList", [])],
        "space_InList": [o.Name for o in getattr(space, "InList", [])],
    }
    linked = (space.Name in out["table_InList"] or space.Name in out["table_OutList"]
              or table.Name in out["space_OutList"] or table.Name in out["space_InList"])
    out["placement_created_dep_edge"] = linked
    R["verdicts"]["P3_depgraph"] = ("FREECAD-NATIVE: placement creates a graph edge" if linked
                                    else "ROOK-WOULD-DO-ANYWAY: placement creates NO dep edge; zone↔slot relationship must live in an external graph (= blueprint.json)")
    return out
P("P3: does placement create a dependency-graph edge?", _p3)

# --- P4: constraint maintenance for 3D layout --------------------------------
def _p4():
    out = {}
    # Is there any core 3D assembly/constraint solver?
    for mod in ("Assembly", "AssemblyA2plus", "a2plus", "Assembly4"):
        try:
            __import__(mod); out[mod] = "importable"
        except Exception as e:
            out[mod] = "absent ({})".format(type(e).__name__)
    # Sketcher exists but is 2D-profile only
    try:
        import Sketcher; out["Sketcher"] = "present (2D profile constraints only — not a 3D furniture layout solver)"
    except Exception as e:
        out["Sketcher"] = "absent"
    # ExpressionEngine CAN bind one property to another (e.g. chair.x = table.x) — test it
    try:
        chair.setExpression("Placement.Base.x", "Table_proxy.Placement.Base.x + 700")
        doc.recompute()
        out["expression_binding"] = "WORKS: chair.x bound to table.x+700 -> {}".format(chair.Placement.Base.x)
        out["expression_note"] = "1-D property binding only; NOT clearance/collision/aisle constraint solving"
    except Exception as e:
        out["expression_binding"] = "ERR {}: {}".format(type(e).__name__, e)
    has_solver = any(v == "importable" for k, v in out.items() if k != "Sketcher")
    R["verdicts"]["P4_constraints"] = ("FREECAD-NATIVE: has a 3D layout/assembly solver" if has_solver
                                       else "ROOK-WOULD-DO-ANYWAY: no 3D layout solver in core; only 1-D expression bindings + 2D sketcher. Clearance/adjacency/packing = custom code either way")
    return out
P("P4: 3D layout constraint/assembly solver in core?", _p4)

# --- P5: reflow — resize envelope, does anything move? -----------------------
def _p5():
    before = (table.Placement.Base.x, table.Placement.Base.y, chair.Placement.Base.x)
    # grow the dining zone solid; recompute
    try:
        sld = doc.getObject("DiningZoneSolid")
        if sld is not None:
            sld.Length = 8000
        doc.recompute()
    except Exception:
        pass
    after = (table.Placement.Base.x, table.Placement.Base.y, chair.Placement.Base.x)
    # chair.x was expression-bound to table.x in P4, so it tracks table — but NOTHING tracks the zone
    moved_with_zone = (before[0] != after[0])  # did table follow the zone resize?
    R["verdicts"]["P5_reflow"] = ("FREECAD-NATIVE: furniture reflows with zone" if moved_with_zone
                                  else "ROOK-WOULD-DO-ANYWAY: resizing the zone moves NO furniture; reflow logic is custom either way (only explicit expression bindings propagate)")
    return {"before": before, "after": after, "table_followed_zone_resize": moved_with_zone}
P("P5: does furniture reflow when the zone resizes?", _p5)

with open(os.path.join(HERE, "results_v5.json"), "w") as f:
    json.dump(R, f, indent=2, default=str)

print("=" * 74); print("INTERIORS LAYOUT FITNESS SPIKE — FreeCAD", R["version"]); print("=" * 74)
for p in R["probes"]:
    print(("  PASS " if p["ok"] else "  FAIL "), p["name"])
    if p["detail"]: print("         ", p["detail"][:300])
print("-" * 74)
print("VERDICTS:")
for k, v in R["verdicts"].items():
    print("  {:18s} {}".format(k, v))
