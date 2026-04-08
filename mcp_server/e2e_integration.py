#!/usr/bin/env python
"""
End-to-end integration test for the Hybrid Learning System.

This script tests the full integration:
1. DSPy reasoning generates hypotheses
2. MAB selects which to test
3. Execute against real Rhino
4. Visual verification via viewport capture
5. Knowledge graph recording

Requirements:
- Rhino 3D running with the RookNative or Rook plugin loaded
- ANTHROPIC_API_KEY environment variable set

Usage:
    python test_e2e_integration.py
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from rook.bridge import call_rhino

# Load API key from autonomous_dev/.env if not already set
if not os.environ.get("ANTHROPIC_API_KEY"):
    env_path = os.path.join(os.path.dirname(__file__), "..", "autonomous_dev", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
        print(f"Loaded API key from {env_path}")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("e2e_test")


async def create_tool_executor():
    """Create async tool executor that calls Rhino HTTP bridge."""
    async def execute_tool(tool_name: str, params: dict) -> dict:
        """Execute an MCP tool via HTTP."""
        # Simple mapping - most tools POST to /toolname
        endpoint_map = {
            "rhino_ping": ("GET", "/ping"),
            "rhino_document": ("GET", "/document"),
            "rhino_viewport": ("GET", "/viewport"),
            "rhino_objects": ("GET", "/objects"),
            "rhino_create": ("POST", "/create"),
            "rhino_transform": ("POST", "/transform"),
            "rhino_delete": ("POST", "/delete"),
            "rhino_boolean": ("POST", "/boolean"),
        }

        method, endpoint = endpoint_map.get(tool_name, ("POST", f"/{tool_name.replace('rhino_', '')}"))
        result = await call_rhino(endpoint, method, params or None)
        if result.get("success", False):
            return result
        return {"success": False, "error": str(result.get("data", "Unknown error"))}

    return execute_tool


async def test_rhino_connection():
    """Test that Rhino is running and accessible."""
    print("\n" + "=" * 60)
    print("TEST 1: Rhino Connection")
    print("=" * 60)

    executor = await create_tool_executor()
    result = await executor("rhino_ping", {})

    if result.get("success"):
        print(f"[OK] Rhino is running: {result.get('data', 'pong')}")
        return True
    else:
        print(f"[FAILED] Cannot connect to Rhino: {result.get('error')}")
        print("Make sure Rhino is running with the RookNative or Rook plugin loaded")
        return False


async def test_hybrid_investigator():
    """Test HybridInvestigator with real Rhino."""
    print("\n" + "=" * 60)
    print("TEST 2: HybridInvestigator with Real Rhino")
    print("=" * 60)

    from rook.learning import (
        HybridInvestigator,
        KnowledgeGraphV2,
        configure_dspy,
    )

    # Configure DSPy
    configure_dspy(model="claude-3-5-haiku-latest")
    print("[OK] DSPy configured")

    # Create components
    executor = await create_tool_executor()
    kg = KnowledgeGraphV2(session_id="e2e_test_session")

    # Create hybrid investigator with visual verification
    investigator = HybridInvestigator(
        kg=kg,
        executor=executor,
        use_dspy=True,
        visual_verification=True,
    )
    print("[OK] HybridInvestigator created")

    # Investigate rhino_create (should work without prerequisites)
    print("\nInvestigating: rhino_create")
    print("-" * 40)

    result = await investigator.investigate_tool("rhino_create")

    print(f"\nResult:")
    print(f"  Tool: {result.tool}")
    print(f"  Success: {result.success}")
    print(f"  Attempts: {result.attempts}")
    print(f"  Time: {result.time_ms:.0f}ms")

    if result.hypotheses_generated:
        print(f"\n  Hypotheses generated ({len(result.hypotheses_generated)}):")
        for h in result.hypotheses_generated[:3]:
            print(f"    - {h[:60]}...")

    if result.hypothesis_selected:
        print(f"\n  Selected hypothesis: {result.hypothesis_selected[:60]}...")

    if result.patterns_discovered:
        print(f"\n  Patterns discovered ({len(result.patterns_discovered)}):")
        for p in result.patterns_discovered:
            print(f"    - {p.get('note', str(p))[:60]}...")

    if result.reasoning_trace:
        print(f"\n  Reasoning trace (last 5):")
        for trace in result.reasoning_trace[-5:]:
            print(f"    > {trace[:70]}...")

    # Visual verification
    print(f"\n  Visual verification:")
    print(f"    Verified: {result.visually_verified}")
    print(f"    Before hash: {result.viewport_hash_before}")
    print(f"    After hash: {result.viewport_hash_after}")
    if result.visual_description:
        print(f"    Description: {result.visual_description}")

    # Stats
    stats = investigator.get_stats()
    print(f"\n  Investigator stats:")
    print(f"    Success rate: {stats['success_rate']:.1%}")
    print(f"    Verification rate: {stats['verification_rate']:.1%}")
    print(f"    DSPy enabled: {stats['dspy_enabled']}")

    return result.success


async def test_learning_session():
    """Test LearningSession with hybrid mode."""
    print("\n" + "=" * 60)
    print("TEST 3: LearningSession with Hybrid Mode")
    print("=" * 60)

    from rook.learning import LearningSession, configure_dspy

    # Configure DSPy
    configure_dspy(model="claude-3-5-haiku-latest")

    # Create session
    executor = await create_tool_executor()
    session = LearningSession(
        executor=executor,
        all_tools=["rhino_ping", "rhino_create", "rhino_transform"],
        use_hybrid=True,
        use_dspy=True,
        visual_verification=True,
    )
    print(f"[OK] LearningSession created (ID: {session.session_id[:8]}...)")

    # Orient
    plan = await session.orient()
    print(f"\n  Session plan:")
    print(f"    Primary targets: {len(plan.primary_targets)}")
    print(f"    Secondary targets: {len(plan.secondary_targets)}")
    print(f"    Coverage: {plan.current_coverage:.1f}%")

    # Run one investigation cycle
    if plan.secondary_targets:
        target = plan.secondary_targets[0]
    elif plan.primary_targets:
        target = plan.primary_targets[0]
    else:
        target = "tool:rhino_create"

    print(f"\n  Running investigation: {target}")
    result = await session.run_investigation_cycle(target)

    if result:
        print(f"  Result: {'SUCCESS' if result.success else 'FAILED'}")
        print(f"  Patterns: {len(result.patterns_discovered)}")
        if hasattr(result, 'visually_verified'):
            print(f"  Verified: {result.visually_verified}")

    # Get status
    status = session.get_status()
    print(f"\n  Session status:")
    print(f"    Investigations: {status['progress']['investigations_completed']}")
    print(f"    Patterns: {status['progress']['patterns_discovered']}")
    print(f"    Verifications: {status['progress']['verifications_performed']}")

    return True


async def test_full_cycle():
    """Test a complete learning cycle."""
    print("\n" + "=" * 60)
    print("TEST 4: Full Learning Cycle (3 investigations)")
    print("=" * 60)

    from rook.learning import LearningSession, configure_dspy

    configure_dspy(model="claude-3-5-haiku-latest")

    executor = await create_tool_executor()
    session = LearningSession(
        executor=executor,
        all_tools=["rhino_ping", "rhino_create", "rhino_transform", "rhino_delete"],
        use_hybrid=True,
        use_dspy=True,
        visual_verification=True,
    )

    # Run session with limited investigations
    print("\nRunning session with max 3 investigations...")

    try:
        handoff = await session.run(max_cycles=3)

        print(f"\n  Session complete!")
        print(f"  Accomplishments:")
        for acc in handoff.accomplishments[:5]:
            print(f"    - {acc}")

        print(f"\n  Next priorities:")
        for pri in handoff.next_priorities[:3]:
            print(f"    - {pri}")

        return True
    except Exception as e:
        print(f"  Session failed: {e}")
        return False


async def main():
    print("=" * 60)
    print("End-to-End Integration Test")
    print("HybridInvestigator + DSPy + MAB + Visual Verification")
    print("=" * 60)

    # Test 1: Rhino connection
    if not await test_rhino_connection():
        print("\n[ABORT] Cannot proceed without Rhino connection")
        return False

    # Test 2: HybridInvestigator
    test2_pass = await test_hybrid_investigator()

    # Test 3: LearningSession
    test3_pass = await test_learning_session()

    # Test 4: Full cycle
    test4_pass = await test_full_cycle()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  [{'OK' if True else 'FAILED'}] Rhino Connection")
    print(f"  [{'OK' if test2_pass else 'FAILED'}] HybridInvestigator")
    print(f"  [{'OK' if test3_pass else 'FAILED'}] LearningSession")
    print(f"  [{'OK' if test4_pass else 'FAILED'}] Full Cycle")

    passed = sum([True, test2_pass, test3_pass, test4_pass])
    print(f"\nPassed: {passed}/4")

    return passed == 4


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
