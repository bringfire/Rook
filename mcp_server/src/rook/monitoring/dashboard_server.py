"""Web dashboard for Rook metrics.

Serves a single-page HTML dashboard with Chart.js at localhost:8855.
Reads from knowledge/metrics.json via MetricsStore.

Adapted from Engram's dashboard_server.py, simplified for Rook.

Usage:
    # Auto-started when metrics_dashboard MCP tool is called
    # Or manually: python -m rook.monitoring.dashboard_server
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DASHBOARD_PORT = 8855
_server_task: Optional[asyncio.Task] = None
_dashboard_url: Optional[str] = None
_server_ready: Optional[asyncio.Event] = None

# TTL cache for metrics to avoid re-reading on every poll
_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL = 5.0  # seconds


def _get_cached_metrics() -> dict:
    """Get metrics with TTL cache."""
    global _cache, _cache_ts
    now = time.time()
    if now - _cache_ts < _CACHE_TTL and _cache:
        return _cache

    try:
        from rook.learning.metrics_store import get_metrics_store
        store = get_metrics_store()
        _cache = {
            "summary": store.get_summary(),
            "tools": store.get_tool_metrics(),
            "recent": store.get_recent(20),
        }
        _cache_ts = now
    except Exception as e:
        logger.warning(f"Failed to read metrics: {e}")
        _cache = {"summary": None, "tools": {}, "recent": []}
        _cache_ts = now

    return _cache


# ---------------------------------------------------------------------------
# HTTP handlers (using aiohttp)
# ---------------------------------------------------------------------------

async def handle_index(request):
    """Serve the dashboard HTML page."""
    from aiohttp import web
    return web.Response(text=DASHBOARD_HTML, content_type="text/html")


async def handle_api_summary(request):
    """Return summary metrics."""
    from aiohttp import web
    data = _get_cached_metrics()
    return web.json_response(data.get("summary") or {})


async def handle_api_tools(request):
    """Return per-tool metrics."""
    from aiohttp import web
    data = _get_cached_metrics()
    return web.json_response(data.get("tools", {}))


async def handle_api_recent(request):
    """Return recent observations for live feed."""
    from aiohttp import web
    data = _get_cached_metrics()
    return web.json_response(data.get("recent", []))


async def handle_api_ab(request):
    """Return A/B comparison data."""
    from aiohttp import web
    data = _get_cached_metrics()
    summary = data.get("summary") or {}
    return web.json_response(summary.get("ab_comparison", {}))


async def handle_api_history(request):
    """Return daily period history."""
    from aiohttp import web
    try:
        from rook.learning.metrics_store import get_metrics_store
        store = get_metrics_store()
        return web.json_response(store.get_period_history(30))
    except Exception as e:
        return web.json_response({"error": str(e)})


# Scene graph cache (separate from metrics cache)
_sg_cache: dict = {}
_sg_cache_ts: float = 0.0
_SG_CACHE_TTL = 2.0


async def handle_api_scene_graph(request):
    """Return scene graph data (proxied from Rhino C# bridge)."""
    from aiohttp import web
    global _sg_cache, _sg_cache_ts

    now = time.time()
    if now - _sg_cache_ts < _SG_CACHE_TTL and _sg_cache:
        return web.json_response(_sg_cache)

    try:
        from rook.bridge import call_rhino
        result = await call_rhino("/scene/graph", "GET", {"depth": "compact"})
        if result.get("success"):
            _sg_cache = result["data"]
        else:
            _sg_cache = {"Nodes": [], "Edges": [], "error": result.get("data", "Failed")}
        _sg_cache_ts = now
    except Exception as e:
        _sg_cache = {"Nodes": [], "Edges": [], "error": str(e)}
        _sg_cache_ts = now

    return web.json_response(_sg_cache)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

async def _run_server():
    """Start the aiohttp web server."""
    global _dashboard_url, _server_ready
    try:
        from aiohttp import web

        app = web.Application()
        app.router.add_get("/", handle_index)
        app.router.add_get("/api/summary", handle_api_summary)
        app.router.add_get("/api/tools", handle_api_tools)
        app.router.add_get("/api/recent", handle_api_recent)
        app.router.add_get("/api/ab", handle_api_ab)
        app.router.add_get("/api/history", handle_api_history)
        app.router.add_get("/api/scene-graph", handle_api_scene_graph)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", DASHBOARD_PORT)
        await site.start()

        _dashboard_url = f"http://localhost:{DASHBOARD_PORT}"
        logger.info(f"Dashboard running at {_dashboard_url}")
        if _server_ready:
            _server_ready.set()

        # Keep running
        while True:
            await asyncio.sleep(3600)
    except ImportError:
        logger.error("aiohttp not installed. Install with: pip install aiohttp")
        if _server_ready:
            _server_ready.set()
        raise
    except OSError as e:
        if "address already in use" in str(e).lower() or "10048" in str(e):
            _dashboard_url = f"http://localhost:{DASHBOARD_PORT}"
            logger.info(f"Dashboard already running at {_dashboard_url}")
            if _server_ready:
                _server_ready.set()
        else:
            if _server_ready:
                _server_ready.set()
            raise


async def ensure_dashboard_running() -> str:
    """Ensure the dashboard server is running. Returns the URL."""
    global _server_task, _dashboard_url, _server_ready

    if _dashboard_url:
        return _dashboard_url

    if _server_task is None or _server_task.done():
        _server_ready = asyncio.Event()
        _server_task = asyncio.create_task(_run_server())
        # Wait for actual startup (with timeout)
        try:
            await asyncio.wait_for(_server_ready.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Dashboard startup timed out, returning fallback URL")

    return _dashboard_url or f"http://localhost:{DASHBOARD_PORT}"


# ---------------------------------------------------------------------------
# Dashboard HTML (self-contained with Chart.js CDN)
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rook Metrics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
<style>
:root {
    --bg: #0d1117;
    --card: #161b22;
    --border: #30363d;
    --text: #c9d1d9;
    --text-muted: #8b949e;
    --accent: #58a6ff;
    --green: #3fb950;
    --red: #f85149;
    --yellow: #d29922;
    --purple: #bc8cff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }
.header { padding: 16px 24px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 18px; font-weight: 600; }
.header .status { font-size: 12px; color: var(--text-muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; padding: 16px 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.card h2 { font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
.big-number { font-size: 48px; font-weight: 700; line-height: 1; }
.big-number.green { color: var(--green); }
.big-number.red { color: var(--red); }
.big-number.accent { color: var(--accent); }
.stat-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border); }
.stat-row:last-child { border-bottom: none; }
.stat-label { color: var(--text-muted); }
.stat-value { font-weight: 600; }
.ab-bar { display: flex; gap: 16px; margin-top: 8px; }
.ab-item { flex: 1; text-align: center; padding: 12px; border-radius: 6px; }
.ab-item.with { background: rgba(59, 185, 80, 0.1); border: 1px solid rgba(59, 185, 80, 0.3); }
.ab-item.without { background: rgba(139, 148, 158, 0.1); border: 1px solid rgba(139, 148, 158, 0.3); }
.ab-rate { font-size: 28px; font-weight: 700; }
.ab-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 8px 6px; color: var(--text-muted); border-bottom: 1px solid var(--border); font-weight: 500; cursor: pointer; }
td { padding: 6px; border-bottom: 1px solid var(--border); }
tr:hover { background: rgba(88, 166, 255, 0.05); }
.feed { max-height: 400px; overflow-y: auto; }
.feed-item { padding: 8px; border-bottom: 1px solid var(--border); font-size: 12px; display: flex; gap: 8px; align-items: flex-start; }
.feed-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
.feed-dot.success { background: var(--green); }
.feed-dot.failure { background: var(--red); }
.feed-tool { font-weight: 600; color: var(--accent); min-width: 140px; }
.feed-time { color: var(--text-muted); min-width: 60px; }
.feed-hint { color: var(--text-muted); font-style: italic; }
.wide { grid-column: 1 / -1; }
canvas { max-height: 200px; }
.tabs { display: flex; gap: 4px; padding: 8px 24px; border-bottom: 1px solid var(--border); }
.tab { padding: 8px 16px; border-radius: 6px 6px 0 0; cursor: pointer; font-size: 13px; color: var(--text-muted); background: transparent; border: 1px solid transparent; border-bottom: none; }
.tab:hover { color: var(--text); background: rgba(88,166,255,0.05); }
.tab.active { color: var(--accent); background: var(--card); border-color: var(--border); }
.view { display: none; }
.view.active { display: block; }
#sgContainer { width: 100%; height: 500px; background: var(--card); border: 1px solid var(--border); border-radius: 8px; }
.sg-stats { display: flex; gap: 16px; margin-bottom: 12px; flex-wrap: wrap; }
.sg-stat { padding: 8px 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; font-size: 12px; }
.sg-stat .value { font-size: 20px; font-weight: 700; color: var(--accent); }
.sg-legend { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; font-size: 11px; color: var(--text-muted); }
.sg-legend-item { display: flex; align-items: center; gap: 4px; }
.sg-legend-dot { width: 10px; height: 10px; border-radius: 50%; }
</style>
</head>
<body>

<div class="header">
    <h1>Rook Dashboard</h1>
    <div class="status" id="status">Connecting...</div>
</div>

<div class="tabs">
    <div class="tab active" onclick="switchView('metrics', this)">Metrics</div>
    <div class="tab" onclick="switchView('scenegraph', this)">Scene Graph</div>
</div>

<div id="metricsView" class="view active">
<div class="grid">
    <!-- Success Rate -->
    <div class="card">
        <h2>Success Rate (Today)</h2>
        <div class="big-number green" id="successRate">--</div>
        <div style="margin-top: 8px;">
            <div class="stat-row"><span class="stat-label">Total calls</span><span class="stat-value" id="totalCalls">0</span></div>
            <div class="stat-row"><span class="stat-label">Successes</span><span class="stat-value" id="successes">0</span></div>
            <div class="stat-row"><span class="stat-label">Failures</span><span class="stat-value" id="failures">0</span></div>
        </div>
    </div>

    <!-- First Attempt -->
    <div class="card">
        <h2>First-Attempt Success</h2>
        <div class="big-number accent" id="firstAttempt">--</div>
        <div style="margin-top: 8px;">
            <div class="stat-row"><span class="stat-label">First attempts</span><span class="stat-value" id="firstTotal">0</span></div>
            <div class="stat-row"><span class="stat-label">Corrections today</span><span class="stat-value" id="corrections">0</span></div>
            <div class="stat-row"><span class="stat-label">Avg duration</span><span class="stat-value" id="avgDuration">--</span></div>
        </div>
    </div>

    <!-- A/B Comparison -->
    <div class="card">
        <h2>Knowledge Injection A/B</h2>
        <div class="ab-bar">
            <div class="ab-item with">
                <div class="ab-rate" id="abWithRate" style="color: var(--green);">--</div>
                <div class="ab-label">With Knowledge (<span id="abWithCalls">0</span> calls)</div>
            </div>
            <div class="ab-item without">
                <div class="ab-rate" id="abWithoutRate">--</div>
                <div class="ab-label">Without Knowledge (<span id="abWithoutCalls">0</span> calls)</div>
            </div>
        </div>
    </div>

    <!-- DSPy -->
    <div class="card">
        <h2>DSPy Intent Resolution</h2>
        <div class="big-number purple" id="dspyConfidence" style="color: var(--purple);">--</div>
        <div style="margin-top: 8px;">
            <div class="stat-row"><span class="stat-label">DSPy calls</span><span class="stat-value" id="dspyCalls">0</span></div>
            <div class="stat-row"><span class="stat-label">Avg confidence</span><span class="stat-value" id="dspyAvg">--</span></div>
        </div>
    </div>

    <!-- Timing Chart -->
    <div class="card wide">
        <h2>Average Duration (ms) by Day</h2>
        <canvas id="timingChart"></canvas>
    </div>

    <!-- Tool Performance Table -->
    <div class="card wide">
        <h2>Tool Performance</h2>
        <div style="max-height: 400px; overflow-y: auto;">
            <table id="toolTable">
                <thead>
                    <tr>
                        <th onclick="sortTable(0)">Tool</th>
                        <th onclick="sortTable(1)">Calls</th>
                        <th onclick="sortTable(2)">Success %</th>
                        <th onclick="sortTable(3)">Avg ms</th>
                        <th onclick="sortTable(4)">With Knowledge</th>
                        <th onclick="sortTable(5)">Corrections</th>
                    </tr>
                </thead>
                <tbody id="toolBody"></tbody>
            </table>
        </div>
    </div>

    <!-- Live Feed -->
    <div class="card wide">
        <h2>Live Feed</h2>
        <div class="feed" id="liveFeed"></div>
    </div>
</div>
</div><!-- /metricsView -->

<div id="scenegraphView" class="view" style="padding: 16px 24px;">
    <div class="sg-stats">
        <div class="sg-stat"><div class="value" id="sgNodes">0</div>Nodes</div>
        <div class="sg-stat"><div class="value" id="sgEdges">0</div>Edges</div>
        <div class="sg-stat"><div class="value" id="sgSeq">0</div>Sequence</div>
    </div>
    <div id="sgContainer"></div>
    <div class="sg-legend">
        <div class="sg-legend-item"><div class="sg-legend-dot" style="background:#dc3c3c"></div>supports</div>
        <div class="sg-legend-item"><div class="sg-legend-dot" style="background:#3c64dc"></div>contains</div>
        <div class="sg-legend-item"><div class="sg-legend-dot" style="background:#3cc850"></div>adjacent</div>
        <div class="sg-legend-item"><div class="sg-legend-dot" style="background:#dcc828"></div>near</div>
        <div class="sg-legend-item"><div class="sg-legend-dot" style="background:#a0a0a0"></div>intersects</div>
        <div class="sg-legend-item"><div class="sg-legend-dot" style="background:#c87828"></div>above</div>
    </div>
</div>

<script>
let timingChart = null;
let sortCol = 1;
let sortAsc = false;

function pct(n) { return n != null ? (n * 100).toFixed(1) + '%' : '--'; }
function ms(n) { return n != null ? n.toFixed(0) + ' ms' : '--'; }

async function fetchJSON(url) {
    try {
        const r = await fetch(url);
        return r.ok ? await r.json() : null;
    } catch { return null; }
}

async function updateDashboard() {
    const [summary, tools, recent, history] = await Promise.all([
        fetchJSON('/api/summary'),
        fetchJSON('/api/tools'),
        fetchJSON('/api/recent'),
        fetchJSON('/api/history'),
    ]);

    document.getElementById('status').textContent =
        'Updated ' + new Date().toLocaleTimeString();

    // Today's summary
    const today = summary?.today;
    if (today) {
        document.getElementById('successRate').textContent = pct(today.success_rate);
        document.getElementById('successRate').className =
            'big-number ' + (today.success_rate >= 0.8 ? 'green' : today.success_rate >= 0.5 ? 'accent' : 'red');
        document.getElementById('totalCalls').textContent = today.total_calls;
        document.getElementById('successes').textContent = today.successes;
        document.getElementById('failures').textContent = today.failures;
        document.getElementById('firstAttempt').textContent = pct(today.first_attempt_success_rate);
        document.getElementById('firstTotal').textContent = today.first_attempt_total;
        document.getElementById('corrections').textContent = today.corrections_detected;
        document.getElementById('avgDuration').textContent = ms(today.avg_duration_ms);
        document.getElementById('dspyCalls').textContent = today.dspy_calls;
        document.getElementById('dspyAvg').textContent = today.dspy_avg_confidence?.toFixed(2) || '--';
        document.getElementById('dspyConfidence').textContent =
            today.dspy_calls > 0 ? (today.dspy_avg_confidence * 100).toFixed(0) + '%' : '--';
    }

    // A/B
    const ab = summary?.ab_comparison;
    if (ab) {
        document.getElementById('abWithRate').textContent = pct(ab.with_knowledge?.success_rate);
        document.getElementById('abWithCalls').textContent = ab.with_knowledge?.calls || 0;
        document.getElementById('abWithoutRate').textContent = pct(ab.without_knowledge?.success_rate);
        document.getElementById('abWithoutCalls').textContent = ab.without_knowledge?.calls || 0;
    }

    // Tool table
    if (tools) {
        const tbody = document.getElementById('toolBody');
        const rows = Object.values(tools).sort((a, b) => {
            const av = [a.tool_name, a.calls, a.success_rate, a.avg_duration_ms, a.with_knowledge, a.corrections][sortCol];
            const bv = [b.tool_name, b.calls, b.success_rate, b.avg_duration_ms, b.with_knowledge, b.corrections][sortCol];
            return sortAsc ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
        });
        tbody.innerHTML = rows.map(t => `<tr>
            <td style="color:var(--accent)">${t.tool_name}</td>
            <td>${t.calls}</td>
            <td style="color:${t.success_rate >= 0.8 ? 'var(--green)' : t.success_rate >= 0.5 ? 'var(--yellow)' : 'var(--red)'}">${pct(t.success_rate)}</td>
            <td>${ms(t.avg_duration_ms)}</td>
            <td>${t.with_knowledge}</td>
            <td>${t.corrections}</td>
        </tr>`).join('');
    }

    // Timing chart
    if (history && Object.keys(history).length > 0) {
        const dates = Object.keys(history).sort();
        const durations = dates.map(d => history[d].avg_duration_ms);
        const succRates = dates.map(d => (history[d].success_rate || 0) * 100);

        if (!timingChart) {
            const ctx = document.getElementById('timingChart').getContext('2d');
            timingChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dates,
                    datasets: [
                        { label: 'Avg Duration (ms)', data: durations, borderColor: '#58a6ff', tension: 0.3, yAxisID: 'y' },
                        { label: 'Success Rate (%)', data: succRates, borderColor: '#3fb950', tension: 0.3, yAxisID: 'y1' },
                    ]
                },
                options: {
                    responsive: true,
                    interaction: { mode: 'index', intersect: false },
                    scales: {
                        y: { display: true, position: 'left', title: { display: true, text: 'ms', color: '#8b949e' }, ticks: { color: '#8b949e' }, grid: { color: '#30363d' } },
                        y1: { display: true, position: 'right', min: 0, max: 100, title: { display: true, text: '%', color: '#8b949e' }, ticks: { color: '#8b949e' }, grid: { drawOnChartArea: false } },
                        x: { ticks: { color: '#8b949e' }, grid: { color: '#30363d' } }
                    },
                    plugins: { legend: { labels: { color: '#c9d1d9' } } }
                }
            });
        } else {
            timingChart.data.labels = dates;
            timingChart.data.datasets[0].data = durations;
            timingChart.data.datasets[1].data = succRates;
            timingChart.update('none');
        }
    }

    // Live feed
    if (recent && recent.length > 0) {
        const feed = document.getElementById('liveFeed');
        feed.innerHTML = recent.slice().reverse().map(o => `<div class="feed-item">
            <div class="feed-dot ${o.success ? 'success' : 'failure'}"></div>
            <span class="feed-tool">${o.tool}</span>
            <span class="feed-time">${o.duration_ms}ms</span>
            <span>${o.phase || ''}</span>
            ${o.knowledge ? '<span style="color:var(--purple)">K</span>' : ''}
            ${o.hint ? '<span class="feed-hint">' + o.hint + '</span>' : ''}
            ${o.error ? '<span style="color:var(--red)">' + o.error.slice(0, 60) + '</span>' : ''}
        </div>`).join('');
    }
}

function sortTable(col) {
    if (sortCol === col) sortAsc = !sortAsc;
    else { sortCol = col; sortAsc = false; }
    updateDashboard();
}

// Poll every 2 seconds
updateDashboard();
setInterval(updateDashboard, 2000);

// ================================================================
// View switching
// ================================================================
let currentView = 'metrics';

function switchView(view, tabEl) {
    currentView = view;
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById(view + 'View').classList.add('active');
    tabEl.classList.add('active');

    if (view === 'scenegraph') {
        updateSceneGraph();
        if (!sgInterval) sgInterval = setInterval(updateSceneGraph, 3000);
    } else {
        if (sgInterval) { clearInterval(sgInterval); sgInterval = null; }
    }
}

// ================================================================
// Scene Graph visualization
// ================================================================
const SG_EDGE_COLORS = {
    supports: '#dc3c3c', contains: '#3c64dc', adjacent: '#3cc850',
    near: '#dcc828', intersects: '#a0a0a0', above: '#c87828'
};
const SG_NODE_COLORS = {
    'vertical-planar': '#b45050', 'horizontal-slab': '#5050b4',
    'thin-vertical': '#50a050', 'thin-horizontal': '#a07828',
    compact: '#8c8c8c'
};

let sgNetwork = null;
let sgInterval = null;
let sgLastSeq = -1;

async function updateSceneGraph() {
    const data = await fetchJSON('/api/scene-graph');
    if (!data) return;

    const nodes = data.Nodes || [];
    const edges = data.Edges || [];
    const seq = data.Sequence || 0;

    document.getElementById('sgNodes').textContent = nodes.length;
    document.getElementById('sgEdges').textContent = edges.length;
    document.getElementById('sgSeq').textContent = seq;

    // Skip re-render if sequence unchanged
    if (seq === sgLastSeq && sgNetwork) return;
    sgLastSeq = seq;

    const visNodes = nodes.map(n => ({
        id: n.Id,
        label: (n.Label || n.ShapeClass || '?') + '\\n' + (n.Name || n.Id.slice(0,8)),
        color: {
            background: SG_NODE_COLORS[n.ShapeClass] || '#6e7681',
            border: '#444c56',
            highlight: { background: '#58a6ff', border: '#58a6ff' }
        },
        font: { color: '#c9d1d9', size: 11 },
        shape: 'dot',
        size: 14,
    }));

    const visEdges = edges.map((e, i) => ({
        id: 'e' + i,
        from: e.Source,
        to: e.Target,
        label: e.Rel,
        color: { color: SG_EDGE_COLORS[e.Rel] || '#6e7681', highlight: '#58a6ff' },
        font: { color: '#8b949e', size: 9, strokeWidth: 0 },
        arrows: { to: { enabled: true, scaleFactor: 0.5 } },
        smooth: { type: 'curvedCW', roundness: 0.15 },
    }));

    if (!sgNetwork) {
        const container = document.getElementById('sgContainer');
        sgNetwork = new vis.Network(container, {
            nodes: new vis.DataSet(visNodes),
            edges: new vis.DataSet(visEdges)
        }, {
            physics: {
                solver: 'forceAtlas2Based',
                forceAtlas2Based: { gravitationalConstant: -40, centralGravity: 0.005, springLength: 120 },
                stabilization: { iterations: 80 }
            },
            layout: { improvedLayout: true },
            interaction: { hover: true, tooltipDelay: 200 },
        });
    } else {
        sgNetwork.setData({
            nodes: new vis.DataSet(visNodes),
            edges: new vis.DataSet(visEdges)
        });
    }
}

</script>
</body>
</html>"""


if __name__ == "__main__":
    async def _main():
        await _run_server()

    asyncio.run(_main())
