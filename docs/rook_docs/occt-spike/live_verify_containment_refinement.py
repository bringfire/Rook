"""Live wiring smoke for the ContainmentRefiner (Python read-model).

Requires Rhino OPEN on C:/Users/aryan/Desktop/SpatialTest.3dm with RookNative loaded.
Imports the refiner and runs refine() over a sample of scene objects against the live
mirror, asserting a well-formed contract. CONTRACT/WIRING ONLY — SpatialTest may yield
zero semantic containment positives; that is acceptable. Verdict logic is owned by unit
tests. Port discovery uses urllib only (never curl). Pass port as argv[1] or auto-discover.

  python live_verify_containment_refinement.py [port]
"""
import asyncio
import json
import pathlib
import subprocess
import sys
import urllib.request

REPO = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "mcp_server" / "src"))

from rook.scene.scene_graph import get_scene_graph          # noqa: E402
from rook.scene.containment_refinement import get_containment_refiner  # noqa: E402


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
    refiner = get_containment_refiner(sg)
    fails = []

    # Sync once to learn the node ids, then refine over a bounded sample.
    asyncio.run(sg.sync(port=port))
    sample = list(sg.graph.nodes)[:25]
    out = asyncio.run(refiner.refine(sample, port=port))

    if out.get("success") is not True:
        fails.append(f"success={out.get('success')!r} error={out.get('error')!r}")
    if "graphSequence" not in out or "refined" not in out or "bySource" not in out:
        fails.append("missing top-level contract fields")
    for cand in out.get("refined", []):
        if cand["verdict"] not in {"contains_semantic", "insufficient_evidence", "disqualified", "failed"}:
            fails.append(f"bad verdict {cand['verdict']!r}")
        if cand["candidateId"] != f"{cand['containerId']}|contains|{cand['containedId']}":
            fails.append(f"bad candidateId {cand['candidateId']!r}")
    for sid, blk in out.get("bySource", {}).items():
        if blk["status"] not in {"ok", "skipped", "failed"}:
            fails.append(f"bad status {blk['status']!r} for {sid}")

    # Rhino still responsive?
    try:
        _get(port, "/scene/graph/stats", 5)
    except Exception as ex:
        fails.append(f"Rhino unresponsive after refine: {ex}")

    n_pos = sum(1 for c in out.get("refined", []) if c["verdict"] == "contains_semantic")
    print(f"refined={len(out.get('refined', []))} positives={n_pos} "
          f"(zero positives is acceptable for SpatialTest)")
    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("RESULT: ALL PASS — well-formed contract, Rhino stable (contract/wiring only).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
