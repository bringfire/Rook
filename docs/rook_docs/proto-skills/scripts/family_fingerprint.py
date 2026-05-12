"""
Family fingerprinting: given an exemplar Brep ID, find all instances of the
same Revit family in the document by thickness-invariant matching.

Run via: rhino_execute(code=open(this_file).read())

Writes hits to %TEMP%/rook/<task>_family_scan.json grouped by classification:
  - intact_closed_exemplar_size  (closed solid, envelope matches exemplar)
  - intact_closed_different_size (closed solid, thickness matches, larger envelope)
  - mode_b_intact_with_hole      (open shell, envelope matches -- missing one face)
  - mode_a_thickness_only        (open shell, thickness matches, larger envelope)
  - not_family                   (filtered out, written only as count)

See revit-family-fingerprinting.md for the technique writeup and the
two insights that make it work.
"""

import scriptcontext as sc
import Rhino
import json
import os
import tempfile


# -----------------------------------------------------------------------------
# Config -- adjust per task
# -----------------------------------------------------------------------------
#
# UPGRADED: pass 2+ EXEMPLAR_IDS and the script derives the invariant axis.
# The original single-exemplar form hard-coded "smallest dim = invariant",
# which is wrong for span-fixed families like long beams. See proto-skill doc.
#
EXEMPLAR_IDS = [
    "c4bdade3-0c95-4bf9-8da8-db36476248d1",
    # add 1-3 more examples of the same family here
]
TASK_NAME    = "family"

# Search universe: list of fully-qualified layer paths to scan
SEARCH_LAYERS = [
    "A5_Roof Parts _dwg::01_Panels_Flat",
    "A5_Roof Parts _dwg::02_Trim_Linear",
    "A5_Roof Parts _dwg::03_Profiled_Open",
    "A5_Roof Parts _dwg::04_Solids_Closed",
]

# Wide-scan tolerance is matched to a small multiple of OBSERVED example
# spread on the invariant axis. If your examples have <1% spread, ~5%
# wide-scan tolerance is plenty. If they have 3-5% spread, use ~15%.
INVARIANT_TOL_REL = 0.10
ENVELOPE_TOL_REL  = 0.25    # for "envelope match" -- distinguishes Mode B from Mode A
MIN_LONG_DIM      = 50.0    # mm; skip tiny scraps


# -----------------------------------------------------------------------------
# Setup -- derive the invariant axis from the example set
# -----------------------------------------------------------------------------
import statistics
doc = sc.doc
from System import Guid

example_dims = []  # one (long, mid, min) tuple per example
for eid in EXEMPLAR_IDS:
    obj = doc.Objects.Find(Guid(eid))
    if obj is None:
        raise RuntimeError(f"Exemplar not found: {eid}")
    geo = obj.Geometry
    if not isinstance(geo, Rhino.Geometry.Brep):
        raise RuntimeError(f"Exemplar must be a Brep: {eid}")
    bb = geo.GetBoundingBox(True)
    dims = sorted([bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y, bb.Max.Z - bb.Min.Z], reverse=True)
    example_dims.append(tuple(dims))

if len(example_dims) < 2:
    raise RuntimeError("Need at least 2 examples to derive the invariant axis. "
                       "See proto-skill doc, Insight 1.")

def cv(vals):
    m = sum(vals)/len(vals)
    if m < 1e-6: return 0.0
    return statistics.pstdev(vals) / m

per_axis_vals = {
    "long_dim": [d[0] for d in example_dims],
    "mid_dim":  [d[1] for d in example_dims],
    "min_dim":  [d[2] for d in example_dims],
}
per_axis_cv = {k: cv(v) for k, v in per_axis_vals.items()}
invariant_axis  = min(per_axis_cv.keys(), key=lambda k: per_axis_cv[k])
invariant_value = sum(per_axis_vals[invariant_axis]) / len(per_axis_vals[invariant_axis])

# Use mid+max dim spread to choose envelope tolerance per-axis
EXEMPLAR_MEANS = {k: sum(v)/len(v) for k, v in per_axis_vals.items()}

search_layer_idx = set(doc.Layers.FindByFullPath(p, -1) for p in SEARCH_LAYERS)


# -----------------------------------------------------------------------------
# Classification
# -----------------------------------------------------------------------------
def within_rel(a, b, tol):
    if max(a, b) < 1e-6:
        return True
    return abs(a - b) / max(a, b) <= tol


_AXIS_INDEX = {"long_dim": 0, "mid_dim": 1, "min_dim": 2}

def classify(piece_dims_sorted, is_solid):
    long_d, mid_d, min_d = piece_dims_sorted

    # Required: piece must match the family invariant
    inv_d = piece_dims_sorted[_AXIS_INDEX[invariant_axis]]
    if not within_rel(inv_d, invariant_value, INVARIANT_TOL_REL):
        return "not_family"
    if long_d < MIN_LONG_DIM:
        return "not_family"

    # Envelope match: all 3 dims close to exemplar means (Mode B candidate)
    envelope_match = all(
        within_rel(piece_dims_sorted[i], EXEMPLAR_MEANS[axis], ENVELOPE_TOL_REL)
        for axis, i in _AXIS_INDEX.items()
    )

    if is_solid and envelope_match:
        return "intact_closed_exemplar_size"
    if is_solid:
        return "intact_closed_different_size"
    if envelope_match:
        return "mode_b_intact_with_hole"
    return "mode_a_invariant_only"


# -----------------------------------------------------------------------------
# Scan
# -----------------------------------------------------------------------------
buckets = {
    "intact_closed_exemplar_size":  [],
    "intact_closed_different_size": [],
    "mode_b_intact_with_hole":      [],
    "mode_a_invariant_only":        [],
}
not_family_count = 0

for obj in doc.Objects:
    if obj.Attributes.LayerIndex not in search_layer_idx:
        continue
    geo = obj.Geometry
    if not isinstance(geo, Rhino.Geometry.Brep):
        continue

    bb = geo.GetBoundingBox(True)
    dims = sorted([bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y, bb.Max.Z - bb.Min.Z], reverse=True)
    bucket = classify(dims, geo.IsSolid)

    if bucket == "not_family":
        not_family_count += 1
        continue

    buckets[bucket].append({
        "id": str(obj.Id),
        "fc": geo.Faces.Count,
        "dims": [round(d, 1) for d in dims],
        "centroid": [
            round((bb.Min.X + bb.Max.X) / 2, 1),
            round((bb.Min.Y + bb.Max.Y) / 2, 1),
            round((bb.Min.Z + bb.Max.Z) / 2, 1),
        ],
        "layer": doc.Layers[obj.Attributes.LayerIndex].Name,
    })

for k in buckets:
    buckets[k].sort(key=lambda r: (r["centroid"][1], r["centroid"][0]))


# -----------------------------------------------------------------------------
# Sanity-check histogram: size distribution by middle-dim, 25mm bins
# -----------------------------------------------------------------------------
all_hits = []
for v in buckets.values():
    all_hits.extend(v)

from collections import Counter
size_dist = Counter()
for r in all_hits:
    size_dist[int(round(r["dims"][1] / 25.0) * 25)] += 1
size_dist_sorted = sorted(size_dist.items())


# -----------------------------------------------------------------------------
# Persist + report
# -----------------------------------------------------------------------------
out_path = os.path.join(tempfile.gettempdir(), "rook", f"{TASK_NAME}_family_scan.json")
with open(out_path, "w") as f:
    json.dump(buckets, f)

print(json.dumps({
    "examples_used":      len(EXEMPLAR_IDS),
    "per_axis_cv":        {k: round(v, 4) for k, v in per_axis_cv.items()},
    "invariant_axis":     invariant_axis,
    "invariant_value":    round(invariant_value, 1),
    "invariant_tol_rel":  INVARIANT_TOL_REL,
    "counts":             {k: len(v) for k, v in buckets.items()},
    "not_family_filtered": not_family_count,
    "total_family_hits":  len(all_hits),
    "size_distribution_mid_dim_25mm_bins": size_dist_sorted,
    "saved_to": out_path,
}, indent=2))
