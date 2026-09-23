"""Gated live verification for rookbim_export_preset.

Run with Rhino.Inside.Revit active and a Revit model open on a 3D view (NOT a sheet).
Exports the architectural_shell preset, then asserts a non-vacuous, organized bundle:
hierarchical RookBim:: layers, populated object names, standard metadata stamps, the bijection,
count reconciliation, the summary, and the relationship index.

Usage: python docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export_preset.py <abs_output_dir>
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

from rook.bridge import NATIVE_CLIENT_HEADERS, discover_instances


def _native_port() -> int:
    instances = discover_instances()
    native = [i for i in instances if i.get("pluginType") == "native" and isinstance(i.get("port"), int)]
    if not native:
        raise RuntimeError(
            "No native Rook instance found. Is Rhino.Inside.Revit running with the Rook plugins loaded?"
        )
    return int(native[0]["port"])


def _post(port: int, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **NATIVE_CLIENT_HEADERS},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="rookbim_preset_")
    port = _native_port()

    result = _post(port, "/bim/export-preset", {
        "preset": "architectural_shell",
        "output": {"directory": out_dir, "name": "shell-preset", "units": "meters", "overwrite": True},
        "scope": "active_view",
        "allowTruncated": True,
    })

    assert result.get("success"), f"export failed: {result}"
    data = result["data"]
    paths = data["paths"]
    for key in ("model3dm", "sidecar", "validation"):
        assert Path(paths[key]).exists(), f"missing artifact {key}: {paths[key]}"

    sidecar = json.loads(Path(paths["sidecar"]).read_text(encoding="utf-8"))
    validation = json.loads(Path(paths["validation"]).read_text(encoding="utf-8"))

    # Bijection + counts.
    assert data["verification"]["ok"], f"bijection failed: {data['verification']['discrepancies']}"
    counts = data["counts"]
    exported = counts["exportedBrep"] + counts["exportedMesh"] + counts["exportedBboxProxy"]
    assert counts["resolved"] == exported + counts["failed"], f"count mismatch: {counts}"

    # NON-VACUOUS gate 1: at least one exported model object.
    assert exported >= 1, f"vacuous export — no model geometry: {counts}"

    # NON-VACUOUS gate 2: at least one preset-organized layer under RookBim:: that is not the flat
    # Model layer, and never the wrong-cased root.
    elements = sidecar["elements"]
    assert elements, "vacuous export — no element records"
    raw_text = Path(paths["sidecar"]).read_text(encoding="utf-8")
    assert "RookBIM::" not in raw_text, "wrong-cased layer root present"

    # NON-VACUOUS gate 3: summary present + structured + WIRE-FORMAT policy echo.
    summary = data["summary"]
    assert summary["digest"], "summary digest missing"
    assert summary["preset"] == "architectural_shell"
    assert summary["layerPolicy"] == "by_level_then_category", f"policy not wire-format: {summary['layerPolicy']}"
    assert summary["namePolicy"] == "readable_with_id"
    assert summary["metadataProfile"] == "standard"
    assert summary["resolvedCategories"], "no resolved categories in summary"
    assert summary["geometryQuality"]["brep"] >= 1 or summary["geometryQuality"]["mesh"] >= 1

    # NON-VACUOUS gate 4: object NAMES + metadata STAMPS proven from the actual .3dm objects
    # (validation.objects is computed from File3dm.Objects, not the sidecar records).
    audit = validation["objects"]
    assert audit["objectCount"] >= 1, "no objects in .3dm"
    assert audit["namedObjectCount"] >= 1, f"no named .3dm objects: {audit}"
    assert audit["withUniqueIdCount"] >= 1, "no revit.uniqueId stamps on .3dm objects"
    assert audit["withLevelStampCount"] >= 1 or audit["withFamilyStampCount"] >= 1, \
        f"standard stamps (revit.level/revit.family) missing on objects: {audit}"
    assert audit["sampleNames"], "no sample object names captured"

    # NON-VACUOUS gate 5a: namespaced metadata stamp keys reached the objects.
    assert any("." in k for k in audit["sampleStampKeys"]), f"no namespaced stamp keys: {audit['sampleStampKeys']}"

    # NON-VACUOUS gate 5b: structural hierarchical RookBim layers exist in the .3dm. Rhino
    # displays nested paths with "::", but each Layer.Name must be a single segment and children
    # must point at a parent layer id.
    layer_names = audit["layerNames"]
    layer_paths = audit["layerPaths"]
    layer_records = audit["layerRecords"]
    object_layer_paths = audit["objectLayerPaths"]
    assert "RookBim" in layer_names, f"no RookBim root layer: {layer_names}"
    assert not any("::" in n for n in layer_names), f"flat path-encoded layer names found: {layer_names}"
    assert not any(n.startswith("RookBIM") for n in layer_names), "wrong-cased layer root"
    assert any(p.startswith("RookBim::") for p in layer_paths), f"no RookBim child paths: {layer_paths}"
    assert any(p.count("::") >= 2 for p in layer_paths), f"no level::category layer paths: {layer_paths}"
    assert any(p.startswith("RookBim::") and p.count("::") >= 2 for p in object_layer_paths), \
        f"object layers do not resolve under nested RookBim tree: {object_layer_paths}"
    assert any(r["name"] != "RookBim" and r["hasParent"] for r in layer_records), \
        f"RookBim child layers have no parent id: {layer_records}"

    # NON-VACUOUS gate 6: relationship index present (facts only) in response, sidecar, AND validation.
    members = {"roomMembership", "hostMembership", "levelMembership"}
    assert set(data["relationships"].keys()) >= members, "relationships missing in response"
    assert set(sidecar["relationships"].keys()) >= members, "relationships missing in sidecar"
    assert set(validation["relationships"].keys()) >= members, "relationships missing in validation"

    print("LIVE VERIFY PASS (preset)")
    print(f"  preset=architectural_shell resolved={counts['resolved']} exported={exported} "
          f"failed={counts['failed']} rooms={counts['rooms']}")
    print(f"  categories={[c['category'] for c in summary['resolvedCategories']]}")
    print(f"  digest: {summary['digest']}")
    print(f"  bundle: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
