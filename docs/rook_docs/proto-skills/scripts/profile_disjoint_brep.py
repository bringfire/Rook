"""
Profile every Brep on a given layer and emit summary stats + histograms.

Run via: rhino_execute(code=open(this_file).read())

Assumes you already ran rhino_split_disjoint_breps on the source object so the
target_layer now holds the disjoint pieces.

Outputs to:
  - %TEMP%/rook/<task>_profile.json   (per-piece rows, for later layer-assignment)
  - stdout                              (summary JSON for human reading)
"""

import scriptcontext as sc
import Rhino
import json
import os
import tempfile

# -----------------------------------------------------------------------------
# Config — adjust per task
# -----------------------------------------------------------------------------
TARGET_LAYER = "A5_Roof Parts _dwg"     # parent layer holding the split pieces
TASK_NAME    = "roof_split"              # for the profile JSON filename


# -----------------------------------------------------------------------------
# Profile
# -----------------------------------------------------------------------------
doc = sc.doc
layer_idx = doc.Layers.FindByFullPath(TARGET_LAYER, -1)
if layer_idx < 0:
    raise RuntimeError(f"Layer not found: {TARGET_LAYER}")

pieces = []
for obj in doc.Objects:
    if obj.Attributes.LayerIndex != layer_idx:
        continue
    geo = obj.Geometry
    if not isinstance(geo, Rhino.Geometry.Brep):
        continue

    bb = geo.GetBoundingBox(True)
    dx = bb.Max.X - bb.Min.X
    dy = bb.Max.Y - bb.Min.Y
    dz = bb.Max.Z - bb.Min.Z

    area = 0.0
    for f in geo.Faces:
        amp = Rhino.Geometry.AreaMassProperties.Compute(f)
        if amp is not None:
            area += amp.Area

    dims = sorted([dx, dy, dz], reverse=True)
    aspect = (dims[0] / dims[2]) if dims[2] > 1e-6 else 9999

    pieces.append({
        "id": str(obj.Id),
        "fc": geo.Faces.Count,
        "ec": geo.Edges.Count,
        "area": round(area, 2),
        "bbox_min": [round(bb.Min.X, 3), round(bb.Min.Y, 3), round(bb.Min.Z, 3)],
        "bbox_max": [round(bb.Max.X, 3), round(bb.Max.Y, 3), round(bb.Max.Z, 3)],
        "dx": round(dx, 3),
        "dy": round(dy, 3),
        "dz": round(dz, 3),
        "aspect": round(aspect, 2) if aspect != 9999 else 9999,
        "closed": geo.IsSolid,
        "manifold": geo.IsManifold,
    })


# -----------------------------------------------------------------------------
# Persist per-piece rows for the next phase
# -----------------------------------------------------------------------------
tmp_dir = os.path.join(tempfile.gettempdir(), "rook")
os.makedirs(tmp_dir, exist_ok=True)
out_path = os.path.join(tmp_dir, f"{TASK_NAME}_profile.json")
with open(out_path, "w") as f:
    json.dump(pieces, f)


# -----------------------------------------------------------------------------
# Summary stats + histograms
# -----------------------------------------------------------------------------
def stats(vals):
    vals = sorted(vals)
    n = len(vals)
    return {
        "n": n,
        "min": round(min(vals), 3),
        "p25": round(vals[n // 4], 3),
        "median": round(vals[n // 2], 3),
        "p75": round(vals[(3 * n) // 4], 3),
        "max": round(max(vals), 3),
        "mean": round(sum(vals) / n, 3),
    }


def histogram(vals, bins):
    """Return [(label, count), ...] given strict ascending bin edges."""
    counts = [0] * (len(bins) + 1)
    labels = []
    for i, b in enumerate(bins):
        labels.append(f"< {b}" if i == 0 else f"{bins[i - 1]}-{b}")
    labels.append(f">= {bins[-1]}")
    for v in vals:
        placed = False
        for i, b in enumerate(bins):
            if v < b:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    return list(zip(labels, counts))


face_counts = [p["fc"] for p in pieces]
areas       = [p["area"] for p in pieces]
z_mins      = [p["bbox_min"][2] for p in pieces]
longest     = [max(p["dx"], p["dy"], p["dz"]) for p in pieces]
aspects     = [p["aspect"] for p in pieces if p["aspect"] < 9999]
closed_n    = sum(1 for p in pieces if p["closed"])

summary = {
    "total_pieces":      len(pieces),
    "closed_solids":     closed_n,
    "open_shells":       len(pieces) - closed_n,
    "face_count_stats":  stats(face_counts),
    "face_count_hist":   histogram(face_counts, [2, 4, 6, 10, 20, 50]),
    "area_stats":        stats(areas),
    "area_hist":         histogram(areas, [100, 1000, 10000, 100000, 500000]),
    "longest_dim_stats": stats(longest),
    "longest_dim_hist":  histogram(longest, [10, 50, 100, 500, 1000]),
    "z_min_stats":       stats(z_mins),
    "aspect_stats":      stats(aspects) if aspects else None,
    "aspect_hist":       histogram(aspects, [2, 5, 10, 50, 200]),
    "profile_saved_to":  out_path,
}

print(json.dumps(summary, indent=2))
