#!/bin/bash
# ──────────────────────────────────────────────────────────────────────
# RookNative Plugin Smoke Test
# ──────────────────────────────────────────────────────────────────────
#
# Prerequisites:
#   1. Open Rhino 8
#   2. Drag RookNative.rhp into the viewport (or load via Options > Plug-ins)
#   3. Confirm "RookNative ...: HTTP server on port XXXX" in the command line
#   4. Run this script: bash test_native_plugin.sh
#
# The script tests every route category without requiring scene objects.
# Tests that need objects will create them first via /create.

# Discover port from discovery file (OS-assigned, no hardcoded default).
# Override: PORT=12345 bash test_native_plugin.sh
TEMP_DIR="${TEMP:-/tmp}"
if [ -z "$PORT" ]; then
    PY=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
    DISC_FILE=$(ls "$TEMP_DIR/rook/instance-"*"-native.json" 2>/dev/null | head -1)
    if [ -n "$DISC_FILE" ] && [ -n "$PY" ]; then
        PORT=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['port'])" "$DISC_FILE" 2>/dev/null)
    fi
fi

if [ -z "$PORT" ]; then
    echo "  FATAL: No RookNative discovery file found in $TEMP_DIR/rook/"
    echo "  Is Rhino running with the plugin loaded?"
    echo "  (Or set PORT explicitly: PORT=12345 bash test_native_plugin.sh)"
    exit 1
fi

BASE="http://127.0.0.1:$PORT"
PASS=0
FAIL=0
SKIP=0
ERRORS=""

# ── Helpers ──────────────────────────────────────────────────────────

pass() { PASS=$((PASS+1)); echo "  PASS  $1"; }
fail() { FAIL=$((FAIL+1)); ERRORS="$ERRORS\n  FAIL: $1 — $2"; echo "  FAIL  $1 — $2"; }
skip() { SKIP=$((SKIP+1)); echo "  SKIP  $1 — $2"; }

# Test a GET endpoint returns 200
test_get() {
    local name="$1" path="$2"
    local resp
    resp=$(curl -s -w "\n%{http_code}" "$BASE$path" 2>/dev/null)
    local code=$(echo "$resp" | tail -1)
    local body=$(echo "$resp" | sed '$d')
    if [ "$code" = "200" ]; then
        pass "$name"
    else
        fail "$name" "HTTP $code — $(echo "$body" | head -c 120)"
    fi
}

# Test a POST endpoint returns 200
test_post() {
    local name="$1" path="$2" data="$3"
    local resp
    resp=$(curl -s -w "\n%{http_code}" -X POST -H "Content-Type: application/json" -d "$data" "$BASE$path" 2>/dev/null)
    local code=$(echo "$resp" | tail -1)
    local body=$(echo "$resp" | sed '$d')
    if [ "$code" = "200" ]; then
        pass "$name"
    else
        fail "$name" "HTTP $code — $(echo "$body" | head -c 120)"
    fi
}

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " RookNative Smoke Test — port $PORT"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── 0. Connectivity ─────────────────────────────────────────────────
echo "── Connectivity ──"
resp=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/ping" 2>/dev/null)
if [ "$resp" = "200" ]; then
    pass "GET /ping"
else
    echo ""
    echo "  FATAL: Cannot reach RookNative on port $PORT."
    echo "  Is Rhino running with the plugin loaded?"
    echo ""
    exit 1
fi

# ── 0.5. Discovery File ────────────────────────────────────────────
echo ""
echo "── Discovery File ──"
DISC_CHECK=$(ls "$TEMP_DIR/rook/instance-"*"-native.json" 2>/dev/null | head -1)
if [ -n "$DISC_CHECK" ]; then
    pass "Discovery file exists: $(basename "$DISC_CHECK")"
    if [ -n "$PY" ]; then
        PORT_IN_FILE=$("$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('port',''))" "$DISC_CHECK" 2>/dev/null)
        TYPE_IN_FILE=$("$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('pluginType',''))" "$DISC_CHECK" 2>/dev/null)
        PID_IN_FILE=$("$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('processId',''))" "$DISC_CHECK" 2>/dev/null)
        [ "$PORT_IN_FILE" = "$PORT" ]  && pass "Discovery port=$PORT" || fail "Discovery port" "expected $PORT, got $PORT_IN_FILE"
        [ "$TYPE_IN_FILE" = "native" ] && pass "Discovery pluginType=native" || fail "Discovery pluginType" "expected native, got $TYPE_IN_FILE"
        [ -n "$PID_IN_FILE" ]          && pass "Discovery processId=$PID_IN_FILE" || fail "Discovery processId" "missing"
    else
        skip "Discovery JSON validation" "no python available"
    fi
else
    fail "Discovery file" "No instance-*-native.json found in $TEMP_DIR/rook/"
fi

# ── 1. Read-Only ────────────────────────────────────────────────────
echo ""
echo "── Read-Only ──"
test_get  "GET /document"   "/document"
test_get  "GET /layers"     "/layers"
test_get  "GET /objects"    "/objects"
test_get  "GET /selection"  "/selection"
test_get  "GET /views"      "/views"
test_get  "GET /groups"     "/groups"
test_get  "GET /materials"  "/materials"
test_get  "GET /blocks"     "/blocks"

# ── 2. Create + Geometry Query ──────────────────────────────────────
echo ""
echo "── Create + Geometry Query ──"
# Create a box (params are top-level, not nested under "parameters")
create_resp=$(curl -s -X POST -H "Content-Type: application/json" \
    -d '{"type":"box","origin":[0,0,0],"width":10,"height":10,"depth":10}' \
    "$BASE/create" 2>/dev/null)
BOX_ID=$(echo "$create_resp" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -n "$BOX_ID" ]; then
    pass "POST /create (box → $BOX_ID)"

    # GET /geometry uses ?id= (singular)
    test_get  "GET /geometry?id=$BOX_ID" "/geometry?id=$BOX_ID"

    # Measure endpoints use "id" (singular)
    test_post "POST /measure/bbox"       "/measure/bbox"       "{\"id\":\"$BOX_ID\"}"
    test_post "POST /measure/volume"     "/measure/volume"     "{\"id\":\"$BOX_ID\"}"
    test_post "POST /measure/area"       "/measure/area"       "{\"id\":\"$BOX_ID\"}"
    test_post "POST /measure/centroid"   "/measure/centroid"   "{\"id\":\"$BOX_ID\"}"

    # Analysis uses "id" for single-object, "brepId" for brep-specific
    test_post "POST /analysis/is-valid"  "/analysis/is-valid"  "{\"id\":\"$BOX_ID\"}"
    test_post "POST /analysis/is-closed" "/analysis/is-closed" "{\"id\":\"$BOX_ID\"}"
    test_post "POST /analysis/brep-faces"    "/analysis/brep-faces"    "{\"brepId\":\"$BOX_ID\"}"
    test_post "POST /analysis/brep-edges"    "/analysis/brep-edges"    "{\"brepId\":\"$BOX_ID\"}"
    test_post "POST /analysis/brep-vertices" "/analysis/brep-vertices" "{\"brepId\":\"$BOX_ID\"}"
else
    fail "POST /create (box)" "No ID — $(echo "$create_resp" | head -c 200)"
    skip "Geometry queries" "no box created"
fi

# ── 3. Curves ────────────────────────────────────────────────────────
echo ""
echo "── Curves ──"
line_resp=$(curl -s -X POST -H "Content-Type: application/json" \
    -d '{"type":"line","start":[0,0,0],"end":[10,0,0]}' \
    "$BASE/create" 2>/dev/null)
LINE_ID=$(echo "$line_resp" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -n "$LINE_ID" ]; then
    pass "POST /create (line → $LINE_ID)"
    # Curve analysis uses "curveId"
    test_post "POST /analysis/curve-point-at"  "/analysis/curve-point-at"  "{\"curveId\":\"$LINE_ID\",\"parameter\":0.5}"
    test_post "POST /analysis/curve-tangent"   "/analysis/curve-tangent"   "{\"curveId\":\"$LINE_ID\",\"parameter\":0.5}"
    # Measure/length uses "id"
    test_post "POST /measure/length"           "/measure/length"           "{\"id\":\"$LINE_ID\"}"
    test_post "POST /curve/divide"             "/curve/divide"             "{\"id\":\"$LINE_ID\",\"count\":3}"
else
    fail "POST /create (line)" "No ID — $(echo "$line_resp" | head -c 200)"
fi

# ── 4. Transform / Copy ─────────────────────────────────────────────
echo ""
echo "── Write Operations ──"
if [ -n "$BOX_ID" ]; then
    # Copy
    test_post "POST /copy" "/copy" "{\"ids\":[\"$BOX_ID\"],\"translation\":[20,0,0]}"

    # Transform requires "operation" + "vector"
    test_post "POST /transform (move)" "/transform" "{\"ids\":[\"$BOX_ID\"],\"operation\":\"move\",\"vector\":[0,0,5]}"

    # Select
    test_post "POST /select"    "/select"    "{\"ids\":[\"$BOX_ID\"],\"action\":\"select\"}"
    test_get  "GET /selection"  "/selection"
fi

# ── 5. Undo / Redo ──────────────────────────────────────────────────
echo ""
echo "── Undo/Redo ──"
if [ -n "$BOX_ID" ]; then
    test_post "POST /undo" "/undo" "{}"
    test_post "POST /redo" "/redo" "{}"
else
    skip "POST /undo" "nothing to undo"
    skip "POST /redo" "nothing to redo"
fi

# ── 6. Layers ────────────────────────────────────────────────────────
echo ""
echo "── Layer Operations ──"
# Use unique layer name to avoid "already exists" error
LAYER_NAME="TestLayer_$(date +%s)"
test_post "POST /layers (create)"        "/layers"            "{\"name\":\"$LAYER_NAME\"}"
test_post "POST /layers/visibility"      "/layers/visibility" "{\"name\":\"$LAYER_NAME\",\"visible\":false}"
test_post "POST /layers/visibility (on)" "/layers/visibility" "{\"name\":\"$LAYER_NAME\",\"visible\":true}"

# ── 7. Scene Graph ──────────────────────────────────────────────────
echo ""
echo "── Scene Graph ──"
test_get  "GET /scene/graph"       "/scene/graph"
test_get  "GET /scene/graph/stats" "/scene/graph/stats"

# ── 8. Command Interactive ──────────────────────────────────────────
echo ""
echo "── Command Interactive ──"
test_get  "GET /command/prompt"     "/command/prompt"
test_post "POST /command/cancel"    "/command/cancel" "{}"

# ── 9. Session Recording ───────────────────────────────────────────
echo ""
echo "── Session Recording ──"
test_get  "GET /session"            "/session"
test_get  "GET /session/history"    "/session/history?limit=5"
test_get  "GET /session/list"       "/session/list?limit=5"

# ── 10. Gumball ─────────────────────────────────────────────────────
echo ""
echo "── Gumball ──"
test_get  "GET /gumball/status"     "/gumball/status"
test_get  "GET /gumball/history"    "/gumball/history?limit=5"
test_get  "GET /gumball/context"    "/gumball/context"
test_post "POST /gumball/align"     "/gumball/align"      "{\"mode\":\"world\"}"
test_post "POST /gumball/appearance" "/gumball/appearance" "{\"auto\":true}"

# ── 11. Mesh ─────────────────────────────────────────────────────────
echo ""
echo "── Mesh Operations ──"
if [ -n "$BOX_ID" ]; then
    test_post "POST /mesh/from-brep"  "/mesh/from-brep" "{\"brepId\":\"$BOX_ID\"}"
fi
test_post "POST /mesh/box"       "/mesh/box"       "{\"center\":[50,0,0],\"width\":5,\"depth\":5,\"height\":5}"
test_post "POST /mesh/sphere"    "/mesh/sphere"    "{\"center\":[60,0,0],\"radius\":5}"

# ── 12. SubD ─────────────────────────────────────────────────────────
echo ""
echo "── SubD Operations ──"
test_post "POST /subd/box"       "/subd/box"       "{\"center\":[70,0,0],\"width\":5,\"depth\":5,\"height\":5}"
test_post "POST /subd/sphere"    "/subd/sphere"    "{\"center\":[80,0,0],\"radius\":5}"

# ── 13. Execute (fire-and-forget command) ────────────────────────────
echo ""
echo "── Execute ──"
# /execute runs Python scripts; /command runs Rhino commands
test_post "POST /command"  "/command" "{\"command\":\"_SelNone\"}"
test_post "POST /execute (python)"  "/execute" "{\"code\":\"import rhinoscriptsyntax as rs\\nrs.AddPoint(0,0,0)\"}"

# ── 14. Viewport ────────────────────────────────────────────────────
echo ""
echo "── Viewport ──"
test_get  "GET /viewport"   "/viewport"

# ── 15. Cleanup ─────────────────────────────────────────────────────
echo ""
echo "── Cleanup ──"
for i in $(seq 1 12); do
    resp=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
        -d '{}' "$BASE/undo" 2>/dev/null)
    if [ "$resp" = "200" ]; then
        echo "  (undo $i: ok)"
    else
        break
    fi
done

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo " Results: $PASS passed, $FAIL failed, $SKIP skipped"
echo "═══════════════════════════════════════════════════════════════"

if [ $FAIL -gt 0 ]; then
    echo ""
    echo "Failures:"
    echo -e "$ERRORS"
    echo ""
fi

exit $FAIL
