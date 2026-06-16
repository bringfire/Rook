"""Live smoke for the ExactAdjacencyProjector (Python projection layer).

Requires Rhino OPEN on C:/Users/aryan/Desktop/SpatialTest.3dm with RookNative loaded.
Imports the actual projector and drives project([SOURCE]) against the live native
route, then asserts the mirror was enriched and the cache works. Does NOT revalidate
the OCCT engine (that is live_verify_occt_adjacency.py's job).

Port discovery uses urllib only (never curl). Pass the port as argv[1] or auto-discover.

  python live_verify_exact_projection.py [port]
"""
import asyncio
import json
import pathlib
import subprocess
import sys
import urllib.request

# Make the rook package importable from this docs-tree script.
REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server" / "src"))

from rook.scene.scene_graph import get_scene_graph          # noqa: E402
from rook.scene.exact_projection import (                   # noqa: E402
    get_exact_projector, EXACT_EDGE_KEY,
)

SOURCE = "08d4dedf-1387-453a-9938-7f3ab516b8ac"  # the floorplate (5 abutments)


def _get(port, path, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def discover_port():
    try:
        pids = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process Rhino -ErrorAction SilentlyContinue).Id"], text=True).split()
    except Exception:
        pids = []
    pidset = {p.strip() for p in pids if p.strip()}
    out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
            local, pid = parts[1], parts[4]
            if "127.0.0.1:" in local and pid in pidset:
                port = int(local.rsplit(":", 1)[1])
                try:
                    _get(port, "/scene/graph/stats", 3)
                    return port
                except Exception:
                    continue
    return None


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else discover_port()
    if not port:
        print("FAIL: could not discover the native port (is Rhino open with RookNative?)")
        return 1
    print("port =", port)

    sg = get_scene_graph()
    projector = get_exact_projector(sg)
    fails = []

    # First projection — drives sync + the exact route + edge upsert into the mirror.
    out = asyncio.run(projector.project([SOURCE], port=port))
    block = out["projected"][0]
    if block["routeStatus"] != "ok":
        fails.append(f"routeStatus={block['routeStatus']!r} error={block.get('error')!r}")
    if len(block["neighbors"]) != 5:
        fails.append(f"expected 5 neighbors, got {len(block['neighbors'])}")
    if any(n["fromCache"] for n in block["neighbors"]):
        fails.append("first call should not be fromCache")
    if block["neighbors"] and block["neighbors"][0].get("areaUnit") != "inches^2":
        fails.append(f"areaUnit={block['neighbors'][0].get('areaUnit')!r}")

    # The mirror now holds 5 canonical occt edges incident to SOURCE.
    occt_incident = [
        (u, v) for u, v, k in sg.graph.edges(keys=True)
        if k == EXACT_EDGE_KEY and SOURCE in (u, v)
    ]
    if len(occt_incident) != 5:
        fails.append(f"expected 5 occt edges incident to source, got {len(occt_incident)}")

    # NL surface renders the exact edges.
    ctx = sg.get_context([SOURCE])
    if "exact" not in ctx.lower() or "inches^2" not in ctx:
        fails.append("get_context did not render exact adjacency with areaUnit")

    # Second projection — cache hit, no new route call, neighbors flagged fromCache.
    out2 = asyncio.run(projector.project([SOURCE], port=port))
    if out2["cache"]["hits"] != 1:
        fails.append(f"expected cache hit, got {out2['cache']}")
    if not all(n["fromCache"] for n in out2["projected"][0]["neighbors"]):
        fails.append("second call neighbors should be fromCache")

    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("RESULT: ALL PASS — projector enriched the mirror with 5 exact edges, "
          "NL rendered, cache hit on re-call.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
