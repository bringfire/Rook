"""
Benchmark: RookNative (C++) vs Rook (C#)
========================================
Both plugins running on the same Rhino instance, same document.
Measures latency, consistency, and throughput for identical operations.

Usage:
    python benchmark_native_vs_csharp.py
"""

import json
import statistics
import time

import httpx

# -- Configuration --------------------------------------------------------
# Ports are OS-assigned. Discover from %TEMP%/rook/ discovery files,
# or override via environment: CPP_PORT=12345 python benchmark_native_vs_csharp.py
import glob
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp_server" / "src"))
from rook.bridge import NATIVE_CLIENT_HEADERS  # the native server requires X-Rook-Client

def _discover_native_port() -> int | None:
    disc_dir = os.path.join(tempfile.gettempdir(), "rook")
    for f in sorted(glob.glob(os.path.join(disc_dir, "instance-*-native.json"))):
        try:
            with open(f) as fh:
                data = json.load(fh)
            if data.get("pluginType") == "native" and data.get("port"):
                return int(data["port"])
        except Exception:
            continue
    return None

CPP_PORT = int(os.environ.get("CPP_PORT", 0)) or _discover_native_port()
CS_PORT = int(os.environ.get("CS_PORT", 0)) or None  # C# HTTP server is disabled

WARMUP = 5         # discard first N for JIT/cache warmup
ITERATIONS = 100   # per test (read), 50 (write)

PLUGINS = []
if CPP_PORT:
    PLUGINS.append(("C++ Native", CPP_PORT))
if CS_PORT:
    PLUGINS.append(("C# Managed", CS_PORT))

if not PLUGINS:
    print("No Rhino plugin ports discovered. Is Rhino running with RookNative loaded?")
    print("Override: CPP_PORT=12345 python benchmark_native_vs_csharp.py")
    raise SystemExit(1)

# Shared client per port — reuses connections (keep-alive), just like
# the real MCP bridge does with httpx.AsyncClient.
_clients: dict[int, httpx.Client] = {}


def _client(port: int) -> httpx.Client:
    if port not in _clients:
        _clients[port] = httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            headers=NATIVE_CLIENT_HEADERS,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        )
    return _clients[port]


# -- HTTP Helpers ---------------------------------------------------------

def http_get(port: int, path: str) -> tuple[int, str]:
    try:
        r = _client(port).get(path)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def http_post(port: int, path: str, data: dict) -> tuple[int, str]:
    try:
        r = _client(port).post(path, json=data)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


# -- Timing Infrastructure -----------------------------------------------

def measure(fn, iterations: int, warmup: int = WARMUP) -> dict:
    """Run fn() iterations times, return timing stats in ms."""
    times = []
    errors = 0
    for i in range(warmup + iterations):
        t0 = time.perf_counter()
        code, _ = fn()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        if i >= warmup:
            if 200 <= code < 300:
                times.append(elapsed_ms)
            else:
                errors += 1

    if not times:
        return {"avg": 0, "min": 0, "p50": 0, "p95": 0, "p99": 0, "max": 0,
                "stdev": 0, "errors": errors, "n": 0}

    times.sort()
    n = len(times)
    return {
        "avg": statistics.mean(times),
        "min": min(times),
        "p50": times[n // 2],
        "p95": times[int(n * 0.95)],
        "p99": times[int(n * 0.99)],
        "max": max(times),
        "stdev": statistics.stdev(times) if n > 1 else 0.0,
        "errors": errors,
        "n": n,
    }


# -- Test Definitions -----------------------------------------------------

def make_tests(port: int) -> list[tuple[str, callable, int]]:
    """Return list of (name, fn, iterations) for a given port."""
    return [
        # 1. Pure overhead -- minimal processing
        ("GET /ping",
         lambda p=port: http_get(p, "/ping"),
         ITERATIONS),

        # 2. Read + JSON serialize (document metadata)
        ("GET /document",
         lambda p=port: http_get(p, "/document"),
         ITERATIONS),

        # 3. Read + JSON serialize (object list)
        ("GET /objects",
         lambda p=port: http_get(p, "/objects"),
         ITERATIONS),

        # 4. Read + JSON serialize (layer tree)
        ("GET /layers",
         lambda p=port: http_get(p, "/layers"),
         ITERATIONS),

        # 5. Read with query params (filtered objects)
        ("GET /objects?type=Brep",
         lambda p=port: http_get(p, "/objects?type=Brep"),
         ITERATIONS),

        # 6. Selection query
        ("GET /selection",
         lambda p=port: http_get(p, "/selection"),
         ITERATIONS),

        # 7. Scene graph (complex tree build)
        ("GET /scene/graph",
         lambda p=port: http_get(p, "/scene/graph"),
         50),

        # 8. Write path: create box (UI thread dispatch)
        ("POST /create (box)",
         lambda p=port: http_post(p, "/create",
                                  {"type": "box", "origin": [0, 0, 0],
                                   "width": 5, "height": 5, "depth": 5}),
         50),

        # 9. Write path: undo (UI thread dispatch)
        ("POST /undo",
         lambda p=port: http_post(p, "/undo", {}),
         50),

        # 10. Command execution
        ("POST /command (_SelNone)",
         lambda p=port: http_post(p, "/command", {"command": "_SelNone"}),
         50),
    ]


# -- Reporting ------------------------------------------------------------

def print_header():
    print()
    print("=" * 90)
    print(" RookNative (C++) vs Rook (C#) -- Latency Benchmark")
    print("=" * 90)
    print(f" Iterations: {ITERATIONS} (read), 50 (write) -- Warmup: {WARMUP}")
    print("=" * 90)


def print_test_results(test_name: str, results: list[tuple[str, dict]]):
    """Print side-by-side results for one test across all plugins."""
    print(f"\n  {test_name}")
    print(f"  {'-' * 78}")
    print(f"  {'Plugin':<14} {'Avg':>7} {'P50':>7} {'P95':>7} {'P99':>7} "
          f"{'Max':>7} {'StDev':>7} {'Min':>7}  {'N':>4} {'Err':>3}")

    rows = []
    for plugin_name, stats in results:
        print(f"  {plugin_name:<14} "
              f"{stats['avg']:>6.1f}ms "
              f"{stats['p50']:>6.1f}ms "
              f"{stats['p95']:>6.1f}ms "
              f"{stats['p99']:>6.1f}ms "
              f"{stats['max']:>6.1f}ms "
              f"{stats['stdev']:>6.1f}ms "
              f"{stats['min']:>6.1f}ms "
              f" {stats['n']:>4} {stats['errors']:>3}")
        rows.append(stats)

    # Speedup comparison
    if len(rows) == 2 and rows[0]["avg"] > 0 and rows[1]["avg"] > 0:
        cpp_avg, cs_avg = rows[0]["avg"], rows[1]["avg"]
        if cpp_avg < cs_avg:
            pct = ((cs_avg - cpp_avg) / cs_avg) * 100
            print(f"  -> C++ is {pct:.0f}% faster (avg), {cs_avg/cpp_avg:.2f}x speedup")
        elif cs_avg < cpp_avg:
            pct = ((cpp_avg - cs_avg) / cpp_avg) * 100
            print(f"  -> C# is {pct:.0f}% faster (avg), {cpp_avg/cs_avg:.2f}x speedup")
        else:
            print(f"  -> Identical")

        # Consistency comparison (stdev)
        cpp_stdev, cs_stdev = rows[0]["stdev"], rows[1]["stdev"]
        if cpp_stdev > 0 and cs_stdev > 0:
            if cpp_stdev < cs_stdev:
                print(f"  -> C++ is {cs_stdev/cpp_stdev:.1f}x more consistent (lower stdev)")
            elif cs_stdev < cpp_stdev:
                print(f"  -> C# is {cpp_stdev/cs_stdev:.1f}x more consistent (lower stdev)")


def print_summary(all_results: dict):
    """Print overall summary table."""
    print()
    print("=" * 90)
    print(" SUMMARY -- Average Latency (ms)")
    print("=" * 90)
    print(f"  {'Test':<28} {'C++ (ms)':>10} {'C# (ms)':>10} {'Winner':>8} {'Speedup':>10}")
    print(f"  {'-' * 76}")

    cpp_wins = 0
    cs_wins = 0

    for test_name, results in all_results.items():
        cpp_stats = results[0][1]
        cs_stats = results[1][1]
        cpp_avg = cpp_stats["avg"]
        cs_avg = cs_stats["avg"]

        if cpp_avg < cs_avg and cs_avg > 0:
            winner = "C++"
            speedup = f"{cs_avg/cpp_avg:.2f}x"
            cpp_wins += 1
        elif cs_avg < cpp_avg and cpp_avg > 0:
            winner = "C#"
            speedup = f"{cpp_avg/cs_avg:.2f}x"
            cs_wins += 1
        else:
            winner = "Tie"
            speedup = "1.00x"

        print(f"  {test_name:<28} {cpp_avg:>9.1f} {cs_avg:>9.1f} {winner:>8} {speedup:>10}")

    print(f"  {'-' * 76}")
    print(f"  C++ wins: {cpp_wins}, C# wins: {cs_wins}, "
          f"of {len(all_results)} tests")
    print()


# -- Burst Test -----------------------------------------------------------

def burst_test(port: int, n: int = 50) -> float:
    """Fire N sequential requests as fast as possible, return total time."""
    t0 = time.perf_counter()
    for _ in range(n):
        http_get(port, "/ping")
    return (time.perf_counter() - t0) * 1000.0


def print_burst_results():
    """Run burst test on both plugins."""
    n = 50
    print(f"\n{'=' * 90}")
    print(f" BURST TEST -- {n} sequential /ping requests, total time")
    print(f"{'=' * 90}")

    for plugin_name, port in PLUGINS:
        # Warmup
        for _ in range(5):
            http_get(port, "/ping")

        times = []
        for _ in range(5):  # 5 rounds
            t = burst_test(port, n)
            times.append(t)

        avg = statistics.mean(times)
        rps = (n / (avg / 1000.0))
        print(f"  {plugin_name:<14}  avg {avg:.0f}ms total  "
              f"=> {rps:.0f} req/s  (best: {min(times):.0f}ms)")

    print()


# -- Main -----------------------------------------------------------------

def main():
    # Verify both plugins are alive
    for name, port in PLUGINS:
        code, body = http_get(port, "/ping")
        if code != 200:
            print(f"ERROR: {name} on port {port} not responding (HTTP {code})")
            return
        print(f"  OK  {name} on port {port} - alive")

    print_header()

    all_results = {}

    # Build test lists for both plugins
    cpp_tests = make_tests(CPP_PORT)
    cs_tests = make_tests(CS_PORT)

    # Run tests interleaved (A then B for each test) to reduce bias
    for i in range(len(cpp_tests)):
        test_name = cpp_tests[i][0]
        print(f"\n  Running: {test_name} ...", end="", flush=True)

        results = []
        for plugin_name, port in PLUGINS:
            if port == CPP_PORT:
                _, fn, iters = cpp_tests[i]
            else:
                _, fn, iters = cs_tests[i]

            stats = measure(fn, iters)
            results.append((plugin_name, stats))

        print(" done")
        print_test_results(test_name, results)
        all_results[test_name] = results

    # Burst throughput test
    print_burst_results()

    # Summary
    print_summary(all_results)

    # Cleanup clients
    for c in _clients.values():
        c.close()


if __name__ == "__main__":
    main()
