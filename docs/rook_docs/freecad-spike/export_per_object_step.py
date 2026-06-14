"""
Generate per-object STEP files keyed by RookId, from storey.FCStd.

This is the input for the step-3 export/import MAPPING spike (§6b lead strategy):
one `<rookId>.step` per semantic object, so the join is by filename — zero
reliance on in-file identity (which STEP flattens, v4 finding).

Outputs into ./per_object/  +  a manifest.json mapping rookId -> file + metrics
(volume/bbox) so the Rhino side can both map AND validate geometry.

Run: freecadcmd export_per_object_step.py
"""
import os, json
import FreeCAD as App
import Part

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "storey.FCStd")
OUTDIR = os.path.join(HERE, "per_object")
os.makedirs(OUTDIR, exist_ok=True)

doc = App.openDocument(SRC)
manifest = {"source": "storey.FCStd", "objects": []}

for o in doc.Objects:
    rid = getattr(o, "RookId", "")
    if not rid:
        continue  # semantic objects only (they carry RookId)
    shp = getattr(o, "Shape", None)
    if not shp or shp.isNull() or not shp.isValid():
        manifest["objects"].append({"rookId": rid, "name": o.Name, "exported": False, "reason": "no valid shape"})
        continue
    path = os.path.join(OUTDIR, rid + ".step")
    Part.export([o], path)
    bb = shp.BoundBox
    manifest["objects"].append({
        "rookId": rid,
        "name": o.Name,
        "label": getattr(o, "Label", None),
        "ifcType": getattr(o, "IfcType", None) or getattr(o, "Role", None),
        "file": os.path.relpath(path, HERE).replace("\\", "/"),
        "bytes": os.path.getsize(path),
        "volume": round(shp.Volume, 1),
        "bbox": [round(bb.XMin,1),round(bb.YMin,1),round(bb.ZMin,1),round(bb.XMax,1),round(bb.YMax,1),round(bb.ZMax,1)],
        "exported": True,
    })

with open(os.path.join(HERE, "per_object_manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)

print("Per-object STEP export complete:")
for m in manifest["objects"]:
    if m.get("exported"):
        print("  {:24s} {:10s} vol={:>14} -> {}".format(m["rookId"], m.get("label",""), m["volume"], m["file"]))
    else:
        print("  {:24s} SKIPPED ({})".format(m["rookId"], m.get("reason")))
