"""
Classify pieces (from a prior `profile_disjoint_brep.py` run) and move each one
to a child layer with a distinguishing color.

Run via: rhino_execute(code=open(this_file).read())

Reads:  %TEMP%/rook/<task>_profile.json   (from the profile phase)
Writes: layer hierarchy + object moves into the live Rhino doc
"""

import scriptcontext as sc
import Rhino
import System.Drawing as SD
from System import Guid
import json
import os
import tempfile


# -----------------------------------------------------------------------------
# Config — match the profile phase
# -----------------------------------------------------------------------------
PARENT_LAYER = "A5_Roof Parts _dwg"
TASK_NAME    = "roof_split"

# Tune for your model. Default values assume mm units.
TINY_DIM_THRESHOLD = 10        # pieces with longest_dim < this are artifacts
LINEAR_ASPECT_MIN  = 50        # aspect ratio >= this => "linear" (trim/gutter)

# Child layer specs: (short_name, color_rgb)
CHILDREN_SPEC = [
    ("01_Panels_Flat",     (60, 140, 220)),   # blue   — flat surfaces
    ("02_Trim_Linear",     (240, 140,  40)),  # orange — linear strips
    ("03_Profiled_Open",   (160,  80, 200)),  # purple — multi-face open shells
    ("04_Solids_Closed",   ( 80, 180,  80)),  # green  — closed solids
    ("05_Artifacts_Tiny",  (220,  40,  40)),  # red    — junk
]


# -----------------------------------------------------------------------------
# Classification rules — ORDER MATTERS. See proto-skill doc for rationale.
# -----------------------------------------------------------------------------
def classify(p):
    longest = max(p["dx"], p["dy"], p["dz"])
    if longest < TINY_DIM_THRESHOLD:
        return "05_Artifacts_Tiny"
    if p["closed"]:
        return "04_Solids_Closed"
    if p["aspect"] >= LINEAR_ASPECT_MIN:
        return "02_Trim_Linear"
    if p["fc"] == 1:
        return "01_Panels_Flat"
    return "03_Profiled_Open"


# -----------------------------------------------------------------------------
# Setup: find parent, create or fetch child layers
# -----------------------------------------------------------------------------
doc = sc.doc
parent_idx = doc.Layers.FindByFullPath(PARENT_LAYER, -1)
if parent_idx < 0:
    raise RuntimeError(f"Parent layer not found: {PARENT_LAYER}")
parent_layer = doc.Layers[parent_idx]

child_indices = {}
for short_name, (r, g, b) in CHILDREN_SPEC:
    full = f"{PARENT_LAYER}::{short_name}"
    idx = doc.Layers.FindByFullPath(full, -1)
    if idx < 0:
        layer = Rhino.DocObjects.Layer()
        layer.ParentLayerId = parent_layer.Id
        layer.Name = short_name
        layer.Color = SD.Color.FromArgb(r, g, b)
        idx = doc.Layers.Add(layer)
    child_indices[short_name] = idx


# -----------------------------------------------------------------------------
# Load profile and move each piece
# -----------------------------------------------------------------------------
profile_path = os.path.join(tempfile.gettempdir(), "rook", f"{TASK_NAME}_profile.json")
with open(profile_path, "r") as f:
    pieces = json.load(f)

counts = {name: 0 for name, _ in CHILDREN_SPEC}
errors = []
for p in pieces:
    bucket = classify(p)
    obj = doc.Objects.Find(Guid(p["id"]))
    if obj is None:
        errors.append({"id": p["id"], "reason": "not_found"})
        continue
    attrs = obj.Attributes.Duplicate()
    attrs.LayerIndex = child_indices[bucket]
    # Flip to ColorFromLayer so the layer color is actually visible — without
    # this, pieces keep the per-object color from the Revit export.
    attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromLayer
    if doc.Objects.ModifyAttributes(obj, attrs, True):
        counts[bucket] += 1
    else:
        errors.append({"id": p["id"], "reason": "modify_failed"})

doc.Views.Redraw()

print(json.dumps({
    "child_layers": list(child_indices.keys()),
    "moved": counts,
    "total_moved": sum(counts.values()),
    "errors": errors[:10],
    "error_count": len(errors),
}, indent=2))
