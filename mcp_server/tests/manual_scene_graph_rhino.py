"""
Scene Graph C# Engine — Manual Rhino Test Script
=================================================

Run this via Rhino's Python editor or via the MCP execute tool.
It creates a simple architectural scene, then queries the scene graph
endpoints to verify classification, relationships, and the overlay.

NOTE: Legacy/manual script, NOT a pytest module. It performs live Rhino
calls at import time. Renamed `manual_*` (not `test_*`) so pytest does not
collect it. Run it directly, not via the test suite.

Prerequisites:
  - Rhino 8 running with Rook plugin loaded
  - Empty document (or clear first)

Usage from MCP:
  rhino_command("_-RunPythonScript manual_scene_graph_rhino.py")

Usage from Rhino Python editor:
  Paste and run.
"""

import json
import time
import urllib.request

from rook.bridge import NATIVE_CLIENT_HEADERS, get_rhino_host


def api(path, method="GET", body=None):
    """Call a Rook HTTP endpoint."""
    host = get_rhino_host()
    if host is None:
        raise RuntimeError("No Rhino instance discovered for integration test")
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{host}{path}", data=data, method=method, headers=dict(NATIVE_CLIENT_HEADERS))
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def run_command(cmd):
    """Run a Rhino command via the API."""
    return api("/command", "POST", {"command": cmd})


def check(condition, msg):
    """Assert-like check that prints pass/fail."""
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {msg}")
    return condition


# ================================================================
# Test Setup: Create architectural objects
# ================================================================

print("=" * 60)
print("Scene Graph C# Engine Test")
print("=" * 60)

print("\n1. Creating test geometry...")

# Floor slab: 10x10x0.2 at Z=0
run_command("_-Box _Corner 0,0,0 10,10,0 0.2")
time.sleep(0.3)

# Wall N: 10x0.2x3 at Z=0.2
run_command("_-Box _Corner 0,9.8,0.2 10,10,0.2 3")
time.sleep(0.3)

# Wall S: 10x0.2x3 at Z=0.2
run_command("_-Box _Corner 0,0,0.2 10,0.2,0.2 3")
time.sleep(0.3)

# Wall E: 0.2x10x3 at Z=0.2
run_command("_-Box _Corner 9.8,0,0.2 10,10,0.2 3")
time.sleep(0.3)

# Column: 0.3x0.3x3 at Z=0.2
run_command("_-Box _Corner 5,5,0.2 5.3,5.3,0.2 3")
time.sleep(0.3)

# Small cube (compact): 1x1x1 at Z=0.2
run_command("_-Box _Corner 2,2,0.2 3,3,0.2 1")
time.sleep(0.5)

# Reconcile to make sure the graph picked everything up
print("\n2. Reconciling scene graph...")
result = api("/scene/graph/reconcile", "POST")
print(f"   Reconcile result: {result.get('data', {})}")

# ================================================================
# Test: Graph summary
# ================================================================

print("\n3. Testing graph endpoints...")

stats = api("/scene/graph/stats")
data = stats.get("data", {})
node_count = data.get("nodeCount", 0)
edge_count = data.get("edgeCount", 0)
print(f"   Nodes: {node_count}, Edges: {edge_count}")
check(node_count >= 6, f"Expected >= 6 nodes, got {node_count}")
check(edge_count > 0, f"Expected edges > 0, got {edge_count}")

classifications = data.get("classifications", {})
print(f"   Classifications: {classifications}")

relationships = data.get("relationships", {})
print(f"   Relationships: {relationships}")

# ================================================================
# Test: Classification
# ================================================================

print("\n4. Testing classification...")

# Switch to architecture profile
classify_result = api("/scene/graph/classify", "POST", {"profile": "architecture"})
print(f"   Profile: {classify_result.get('data', {}).get('profile', '?')}")
print(f"   Classifications: {classify_result.get('data', {}).get('classifications', {})}")

# Get full graph to inspect individual nodes
full = api("/scene/graph", "GET", {"depth": "full"})
full_data = full.get("data", {})
nodes = full_data.get("nodes", [])

print(f"\n   Individual nodes:")
for n in nodes:
    label = n.get("domainLabel") or n.get("shapeClass") or "?"
    name = n.get("name") or n.get("id", "?")[:8]
    sc = n.get("shapeClass", "?")
    conf = n.get("classConfidence", 0)
    metrics = n.get("metrics", {})
    dims = f"{metrics.get('maxDim', 0):.1f}x{metrics.get('midDim', 0):.1f}x{metrics.get('minDim', 0):.1f}"
    thin = metrics.get("thinAxis", "?")
    print(f"     {label:20s} | {sc:20s} | {dims:12s} | thin={thin} | conf={conf:.2f} | {name}")

# Check that we got wall, floor, column classifications
labels = {n.get("domainLabel", "") for n in nodes}
check("wall" in labels or "panel" in labels, "Found wall/panel classification")
check("floor" in labels or "slab" in labels, "Found floor/slab classification")

# ================================================================
# Test: Relationships
# ================================================================

print("\n5. Testing relationships...")

edges = full_data.get("edges", [])
rel_types = {e.get("relationship", "") for e in edges}
print(f"   Relationship types found: {rel_types}")
check("supports" in rel_types or "above" in rel_types, "Found supports/above relationships")
check(len(edges) >= 4, f"Expected >= 4 edges, got {len(edges)}")

# ================================================================
# Test: Query endpoint
# ================================================================

print("\n6. Testing query endpoint...")

# Query only walls
query_result = api("/scene/graph/query", "POST", {
    "shape_classes": ["wall", "vertical-planar"],
    "depth": "summary"
})
qdata = query_result.get("data", {})
print(f"   Wall query: {qdata.get('nodeCount', 0)} nodes, {qdata.get('edgeCount', 0)} edges")

# ================================================================
# Test: Diff endpoint
# ================================================================

print("\n7. Testing diff endpoint...")
seq = data.get("sequence", 0)
diff_result = api("/scene/graph/diff", "POST", {"since_sequence": max(0, seq - 5)})
diff_data = diff_result.get("data", {})
print(f"   Current seq: {diff_data.get('currentSequence', '?')}")

# ================================================================
# Test: Overlay toggle
# ================================================================

print("\n8. Testing overlay toggle...")
overlay_on = api("/scene/graph/overlay", "POST", {"enabled": True})
print(f"   Overlay ON: {overlay_on.get('data', {})}")
time.sleep(1)

overlay_off = api("/scene/graph/overlay", "POST", {"enabled": False})
print(f"   Overlay OFF: {overlay_off.get('data', {})}")

# ================================================================
# Summary
# ================================================================

print("\n" + "=" * 60)
print("Test complete. Check Rhino viewport for overlay visualization.")
print(f"Scene: {node_count} nodes, {edge_count} edges, seq={seq}")
print("Run 'ShowSceneGraph' in Rhino to see the overlay again.")
print("Open http://localhost:8855 and click 'Scene Graph' tab for dashboard.")
print("=" * 60)
