"""
E2E Agent Tests — Requires Rhino + Grasshopper Running
========================================================

Tests real agent execution against a live Rhino instance.
Exercises both Rhino geometry and Grasshopper canvas operations.

Run:
    python mcp_server/tests/test_e2e_agents.py

Prerequisites:
    - Rhino 8 open with the Rook plugin loaded (rhino_ping responds)
    - Grasshopper open (for GH tests)
    - ANTHROPIC_API_KEY set (via .env or environment)
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# --- Path setup ---
REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Load .env
from dotenv import load_dotenv
load_dotenv(REPO / ".env")

from rook.bridge import call_rhino
from rook.agent.spawn import run_task, run_swarm, SpawnResult
from rook.agent.tool_dispatcher import ToolDispatcher, build_local_tools, BRIDGE_ROUTES, TRANSFORM_FUNCTIONS

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
logger = logging.getLogger("e2e")


# =============================================================================
# Helpers
# =============================================================================

def safe_summary(result: SpawnResult) -> str:
    """Get ASCII-safe summary from SpawnResult."""
    return result.summary.encode("ascii", errors="replace").decode("ascii")


def print_result(label: str, result: SpawnResult):
    """Print a concise result summary."""
    tools = [t["tool"] for t in result.tools_called if t.get("success")]
    errors = [t for t in result.tools_called if not t.get("success")]
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Status:  {result.status}")
    print(f"  Turns:   {result.metrics.get('turns', '?')}")
    print(f"  Cost:    ${result.metrics.get('cost_usd', 0):.4f}")
    print(f"  Tools:   {', '.join(tools) if tools else '(none)'}")
    if errors:
        print(f"  Errors:  {len(errors)} tool failures")
        for e in errors[:3]:
            print(f"    - {e['tool']}: {e.get('error', '')[:80]}")
    print(f"  Summary: {safe_summary(result)[:200]}")
    return result


async def count_objects() -> int:
    """Count Rhino objects (uses totalCount, not paginated count)."""
    r = await call_rhino("/objects", "GET")
    if r.get("success"):
        data = r.get("data", {})
        if isinstance(data, dict):
            # totalCount = actual total; count = page size (default 100)
            return data.get("totalCount", data.get("count", len(data.get("objects", []))))
        return 0
    return -1


async def check_rhino() -> bool:
    """Verify Rhino is responding."""
    r = await call_rhino("/ping", "GET")
    return r.get("data") == "pong" or r.get("success", False)


async def check_grasshopper() -> bool:
    """Verify Grasshopper is responding."""
    r = await call_rhino("/gh/query", "GET")
    return r.get("success", False)


def build_catalog() -> dict:
    """Build tool catalog from dispatcher routing tables."""
    from rook.agent.tool_groups import TIER_0, AGENT_TIER_0, TOOL_GROUPS
    all_names = set()
    all_names |= AGENT_TIER_0
    for group_tools in TOOL_GROUPS.values():
        all_names.update(group_tools)
    # Add dispatcher-only tools
    all_names |= set(BRIDGE_ROUTES.keys())
    all_names |= set(TRANSFORM_FUNCTIONS.keys())

    catalog = {}
    for name in sorted(all_names):
        catalog[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name.replace('_', ' ')} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    return catalog


# =============================================================================
# Test 1: Dispatcher direct (no LLM, just bridge)
# =============================================================================

async def test_dispatcher_direct():
    """Test ToolDispatcher can reach Rhino and GH without LLM."""
    print("\n" + "="*60)
    print("  TEST 1: ToolDispatcher Direct Bridge")
    print("="*60)

    dispatcher = ToolDispatcher()
    dispatcher.register_locals(build_local_tools())

    results = {}

    # Rhino ping
    r = await dispatcher.dispatch("rhino_ping", {})
    results["rhino_ping"] = r.get("data") == "pong" or r.get("success", False)
    print(f"  rhino_ping:    {'PASS' if results['rhino_ping'] else 'FAIL'}")

    # Rhino objects
    r = await dispatcher.dispatch("rhino_objects", {})
    results["rhino_objects"] = r.get("success", False)
    count = 0
    if isinstance(r.get("data"), dict):
        count = r["data"].get("count", len(r["data"].get("objects", [])))
    print(f"  rhino_objects: {'PASS' if results['rhino_objects'] else 'FAIL'} ({count} objects)")

    # Rhino layers
    r = await dispatcher.dispatch("rhino_layers", {})
    results["rhino_layers"] = r.get("success", False)
    print(f"  rhino_layers:  {'PASS' if results['rhino_layers'] else 'FAIL'}")

    # GH snapshot
    r = await dispatcher.dispatch("gh_snapshot", {})
    results["gh_snapshot"] = r.get("success", False)
    gh_count = 0
    if isinstance(r.get("data"), dict):
        gh_count = len(r["data"].get("components", r["data"].get("objects", [])))
    print(f"  gh_snapshot:   {'PASS' if results['gh_snapshot'] else 'FAIL'} ({gh_count} components)")

    # GH errors
    r = await dispatcher.dispatch("gh_errors", {})
    results["gh_errors"] = r.get("success", False)
    print(f"  gh_errors:     {'PASS' if results['gh_errors'] else 'FAIL'}")

    # Knowledge query (local tool)
    r = await dispatcher.dispatch("knowledge_query", {"intent": "create box", "depth": "quick"})
    results["knowledge_query"] = r.get("success", False)
    print(f"  knowledge_q:   {'PASS' if results['knowledge_query'] else 'FAIL'}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  Result: {passed}/{total} passed")
    return results


# =============================================================================
# Test 2: Worker creates Rhino geometry
# =============================================================================

async def test_worker_rhino_geometry():
    """Worker agent creates geometry in Rhino via an explicit typed route."""
    print("\n" + "="*60)
    print("  TEST 2: Worker — Rhino Geometry Creation")
    print("="*60)

    before = await count_objects()
    catalog = build_catalog()

    result = await run_task(
        "Create a sphere at position 50,0,0 with radius 5. "
        "Then verify it exists by listing objects.",
        agent_type="worker",
        max_turns=10,
        catalog=catalog,
        guardian_enabled=False,
    )

    after = await count_objects()
    print_result("Worker: Rhino geometry", result)
    print(f"  Objects: {before} -> {after} (delta: {after - before})")

    success = result.status == "success" and after > before
    print(f"  VERDICT: {'PASS' if success else 'FAIL'}")
    return success


# =============================================================================
# Test 3: Worker builds GH definition
# =============================================================================

async def test_worker_gh_canvas():
    """Worker agent creates GH components and wires them together."""
    print("\n" + "="*60)
    print("  TEST 3: Worker — Grasshopper Canvas Operations")
    print("="*60)

    catalog = build_catalog()

    result = await run_task(
        "In Grasshopper, create a Number Slider component and a Panel component. "
        "Wire the slider output to the panel input. "
        "Then verify the connection exists using gh_snapshot. "
        "Use gh_snapshot to inspect state, gh_edit to create and connect the "
        "components, and a follow-up gh_snapshot to verify the solved graph.",
        agent_type="worker",
        max_turns=15,
        catalog=catalog,
        guardian_enabled=False,
    )

    print_result("Worker: GH canvas", result)

    # Check that GH canvas tools were used
    gh_tools_used = [
        t["tool"] for t in result.tools_called
        if t.get("success") and t["tool"].startswith("gh_")
    ]
    print(f"  GH tools used: {', '.join(gh_tools_used) if gh_tools_used else '(none)'}")

    success = result.status == "success" and len(gh_tools_used) > 0
    print(f"  VERDICT: {'PASS' if success else 'FAIL'}")
    return success


# =============================================================================
# Test 4: Explorer readonly enforcement
# =============================================================================

async def test_explorer_readonly():
    """Explorer agent can inspect but cannot create geometry."""
    print("\n" + "="*60)
    print("  TEST 4: Explorer — Readonly Enforcement")
    print("="*60)

    before = await count_objects()
    catalog = build_catalog()

    result = await run_task(
        "List all objects in Rhino and describe what you see. "
        "Report the object count and types. "
        "Also check the Grasshopper canvas and report what components exist.",
        agent_type="explorer",
        max_turns=8,
        catalog=catalog,
        guardian_enabled=False,
    )

    after = await count_objects()
    print_result("Explorer: readonly", result)
    print(f"  Objects: {before} -> {after} (delta: {after - before})")

    # Check NO write tools were used
    write_tools = {
        "rhino_create", "rhino_transform",
        "rhino_delete", "rhino_boolean", "rhino_extrude",
        "gh_component", "gh_connect", "gh_set_value", "gh_delete",
    }
    tools_used = {t["tool"] for t in result.tools_called}
    write_used = tools_used & write_tools
    print(f"  Write tools used: {write_used if write_used else '(none — correct)'}")

    success = result.status == "success" and not write_used and after == before
    print(f"  VERDICT: {'PASS' if success else 'FAIL'}")
    return success


# =============================================================================
# Test 5: Worker transforms existing geometry
# =============================================================================

async def test_worker_transform():
    """Worker agent transforms existing geometry."""
    print("\n" + "="*60)
    print("  TEST 5: Worker — Transform Geometry")
    print("="*60)

    catalog = build_catalog()

    result = await run_task(
        "List all objects in Rhino. Pick the first object and copy it "
        "with a translation of 20,0,0. Verify the copy exists.",
        agent_type="worker",
        max_turns=10,
        catalog=catalog,
        guardian_enabled=False,
    )

    print_result("Worker: transform", result)

    transform_tools = {"rhino_transform", "rhino_copy"}
    tools_used = {t["tool"] for t in result.tools_called if t.get("success")}
    used_transform = tools_used & transform_tools
    print(f"  Transform tools: {used_transform if used_transform else '(none)'}")

    success = result.status == "success"
    print(f"  VERDICT: {'PASS' if success else 'FAIL'}")
    return success


# =============================================================================
# Test 6: Swarm — parallel workers
# =============================================================================

async def test_swarm_parallel():
    """Two workers operate in parallel on different layers."""
    print("\n" + "="*60)
    print("  TEST 6: Swarm — Parallel Workers")
    print("="*60)

    catalog = build_catalog()

    swarm_result = await run_swarm(
        [
            {
                "task": "Create a box at 0,0,0 with size 10 using rhino_create. Verify it exists with rhino_objects.",
                "task_id": "swarm_a",
                "workspace_assets": ["Layer::SwarmA"],
            },
            {
                "task": "List all objects in Rhino and report how many there are.",
                "task_id": "swarm_b",
                "agent_type": "explorer",
            },
        ],
        max_turns=10,
        catalog=catalog,
        guardian_enabled=False,
    )

    for r in swarm_result.results:
        print_result(f"Swarm [{r.task_id}]", r)

    success_count = sum(1 for r in swarm_result.results if r.status == "success")
    print(f"\n  Swarm: {success_count}/{len(swarm_result.results)} tasks succeeded")
    print(f"  VERDICT: {'PASS' if success_count == len(swarm_result.results) else 'FAIL'}")
    return success_count == len(swarm_result.results)


# =============================================================================
# Main
# =============================================================================

async def main():
    print("\n" + "#"*60)
    print("#  Rook Multi-Agent E2E Tests")
    print("#"*60)

    # Preflight
    if not await check_rhino():
        print("\n  FATAL: Rhino not responding. Start Rhino with the Rook plugin loaded first.")
        return

    gh_ok = await check_grasshopper()
    if not gh_ok:
        print("\n  WARNING: Grasshopper not responding. GH tests will be skipped.")

    results = {}

    # Test 1: Dispatcher direct (no LLM)
    try:
        dispatcher_results = await test_dispatcher_direct()
        results["1_dispatcher"] = all(dispatcher_results.values())
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        results["1_dispatcher"] = False

    # Test 2: Worker creates Rhino geometry
    try:
        results["2_worker_rhino"] = await test_worker_rhino_geometry()
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        results["2_worker_rhino"] = False

    # Test 3: Worker builds GH definition (skip if GH not available)
    if gh_ok:
        try:
            results["3_worker_gh"] = await test_worker_gh_canvas()
        except Exception as e:
            print(f"  EXCEPTION: {e}")
            results["3_worker_gh"] = False
    else:
        print("\n  SKIP: Test 3 (Grasshopper not available)")
        results["3_worker_gh"] = None

    # Test 4: Explorer readonly enforcement
    try:
        results["4_explorer_readonly"] = await test_explorer_readonly()
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        results["4_explorer_readonly"] = False

    # Test 5: Worker transforms geometry
    try:
        results["5_worker_transform"] = await test_worker_transform()
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        results["5_worker_transform"] = False

    # Test 6: Swarm parallel
    try:
        results["6_swarm"] = await test_swarm_parallel()
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        results["6_swarm"] = False

    # Summary
    print("\n" + "#"*60)
    print("#  SUMMARY")
    print("#"*60)
    total_cost = 0.0
    for name, passed in results.items():
        status = "PASS" if passed else ("SKIP" if passed is None else "FAIL")
        print(f"  {name}: {status}")
    print()

    passed = sum(1 for v in results.values() if v is True)
    skipped = sum(1 for v in results.values() if v is None)
    failed = sum(1 for v in results.values() if v is False)
    print(f"  {passed} passed, {failed} failed, {skipped} skipped")
    print(f"  (out of {len(results)} tests)")


if __name__ == "__main__":
    asyncio.run(main())
