"""Gated live verification for rookbim_export_elements.

Run with Rhino.Inside.Revit active and a Revit model open. Resolves the live native
port from the discovery files, exports a small category, and asserts the three-file
bundle, the join bijection, and count reconciliation.

Usage: python docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py <abs_output_dir>
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

from rook.bridge import NATIVE_CLIENT_HEADERS, discover_instances


def _native_port() -> int:
    """Resolve the live native (C++) listener port from the discovery files."""
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
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="rookbim_export_")
    port = _native_port()

    result = _post(port, "/bim/export-elements", {
        "selector": {"scope": "active_view", "category": "Walls", "limit": 50},
        "output": {"directory": out_dir, "name": "walls-fixture", "units": "meters", "overwrite": True},
        "rooms": "both",
        "allowTruncated": True,
        "allowBboxProxy": False,
    })

    assert result.get("success"), f"export failed: {result}"
    data = result["data"]
    paths = data["paths"]
    for key in ("model3dm", "sidecar", "validation"):
        assert Path(paths[key]).exists(), f"missing artifact {key}: {paths[key]}"

    sidecar = json.loads(Path(paths["sidecar"]).read_text(encoding="utf-8"))
    validation = json.loads(Path(paths["validation"]).read_text(encoding="utf-8"))

    assert data["verification"]["ok"], f"bijection failed: {data['verification']['discrepancies']}"

    counts = data["counts"]
    exported = counts["exportedBrep"] + counts["exportedMesh"] + counts["exportedBboxProxy"]
    assert counts["resolved"] == exported + counts["failed"], f"count mismatch: {counts}"
    assert validation["units"]["source"] == "feet"

    print("LIVE VERIFY PASS")
    print(f"  resolved={counts['resolved']} brep={counts['exportedBrep']} "
          f"mesh={counts['exportedMesh']} bbox={counts['exportedBboxProxy']} failed={counts['failed']} "
          f"rooms={counts['rooms']}")
    print(f"  bundle: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
