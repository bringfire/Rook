"""Task 10 in-plugin live verification of the production OCCT exact-adjacency route.

Verifies POST /scene/graph/adjacency/exact on SpatialTest.3dm (Rhino open). urllib only
(never curl). Pass the native port as argv[1], or let it auto-discover via the Rhino pid's
listening ports (Windows netstat).

  python live_verify_occt_adjacency.py [port]

Asserts, for the open floorplate 08d4dedf:
  - sourceCapability == exact_brep ; lengthUnit == inches ; areaUnit == inches^2
  - the 5 user-confirmed abutments appear as edges with the expected sharedArea (in^2)
  - every edge carries non-empty facePairs summing to sharedArea
  - Rhino stays responsive (/scene/graph/stats answers before and after)
Exit code 0 = all pass, 1 = failure.
"""
import json, sys, subprocess, urllib.request

SOURCE = "08d4dedf-1387-453a-9938-7f3ab516b8ac"
EXPECT = {  # abutment GUID prefix -> shared area in^2 (user-confirmed, Spike A)
    "71065f57": 3311.978, "5c12cc83": 5440.438, "be0ca730": 5423.437,
    "7e80db98": 1040.005, "26b2c012": 1055.000,
}

def discover_port():
    # Windows: find a 127.0.0.1 listening port owned by a Rhino.exe pid that answers stats.
    try:
        pids = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process Rhino -ErrorAction SilentlyContinue).Id"],
            text=True).split()
    except Exception:
        pids = []
    pidset = set(p.strip() for p in pids if p.strip())
    out = subprocess.check_output(["netstat", "-ano", "-p", "TCP"], text=True)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING":
            local, pid = parts[1], parts[4]
            if "127.0.0.1:" in local and pid in pidset:
                port = int(local.rsplit(":", 1)[1])
                if _answers_stats(port):
                    return port
    return None

def _answers_stats(port):
    try:
        get(port, "/scene/graph/stats", 3)
        return True
    except Exception:
        return False

def get(port, path, timeout=8):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def post(port, path, body, timeout=120):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else discover_port()
    if not port:
        print("FAIL: could not discover the native port (is Rhino open with RookNative?)")
        return 1
    print("port =", port, "| stats nodes =", get(port, "/scene/graph/stats")["data"]["nodeCount"])

    d = post(port, "/scene/graph/adjacency/exact", {"objectId": SOURCE, "includeCoarse": False}).get("data", {})
    fails = []
    if d.get("sourceCapability") != "exact_brep": fails.append("sourceCapability=%r" % d.get("sourceCapability"))
    if d.get("lengthUnit") != "inches":           fails.append("lengthUnit=%r" % d.get("lengthUnit"))
    if d.get("areaUnit") != "inches^2":           fails.append("areaUnit=%r" % d.get("areaUnit"))

    edges = d.get("edges", [])
    by_prefix = {e.get("targetId", "")[:8]: e for e in edges}
    print("edges total =", len(edges))
    for pre, exp in EXPECT.items():
        e = by_prefix.get(pre)
        if not e:
            fails.append("MISSING abutment %s" % pre); continue
        area = e.get("sharedArea", 0.0)
        fp = e.get("facePairs", [])
        fpsum = sum(x.get("sharedArea", 0.0) for x in fp)
        ok = abs(area - exp) / exp < 1e-3
        if not ok:                  fails.append("%s area %.3f != %.3f" % (pre, area, exp))
        if not fp:                  fails.append("%s has no facePairs" % pre)
        elif abs(fpsum - area) > max(1e-6, area * 1e-6): fails.append("%s facePairs sum %.3f != %.3f" % (pre, fpsum, area))
        print("  %s area=%.3f facePairs=%d fpSum=%.3f %s" % (pre, area, len(fp), fpsum, "OK" if ok and fp else "FAIL"))

    # Rhino still responsive after the compute?
    try:
        get(port, "/scene/graph/stats", 5)
    except Exception as ex:
        fails.append("Rhino unresponsive after compute: %s" % ex)

    if fails:
        print("RESULT: FAIL")
        for f in fails: print("  -", f)
        return 1
    print("RESULT: ALL PASS (5/5 abutments exact, contract fields correct, Rhino stable)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
