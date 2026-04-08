#!/usr/bin/env python
"""
Test DSPy integration with real LLM calls.

This script tests that:
1. DSPy configures correctly with Anthropic
2. The signatures and modules work
3. We get real reasoning from Claude
"""

import os
import sys

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

def test_dspy_config():
    """Test basic DSPy configuration."""
    print("\n" + "="*60)
    print("TEST 1: DSPy Configuration")
    print("="*60)

    from rook.learning import configure_dspy, is_configured, get_lm

    assert not is_configured(), "Should not be configured yet"

    lm = configure_dspy(model="claude-3-5-haiku-latest", temperature=0.5)

    assert is_configured(), "Should be configured now"
    assert get_lm() is not None, "LM should exist"

    print(f"[OK] DSPy configured with: {lm.model}")
    return True


def test_investigation_planner():
    """Test the InvestigationPlanner module with a real LLM call."""
    print("\n" + "="*60)
    print("TEST 2: InvestigationPlanner (Real LLM Call)")
    print("="*60)

    from rook.learning import InvestigationPlanner

    planner = InvestigationPlanner()

    # Call the planner with a real tool investigation request
    result = planner(
        tool_name="rhino_loft",
        tool_description="Create a lofted surface through multiple curves",
        known_patterns=["Curves should be in order from bottom to top"],
        known_antipatterns=["Single curve fails - need at least 2"],
        available_geometry=["curve", "circle"],
    )

    print(f"\nHypotheses generated ({len(result.hypotheses)}):")
    for i, h in enumerate(result.hypotheses[:5], 1):
        print(f"  {i}. {h}")

    print(f"\nRequired geometry: {result.required_geometry}")
    print(f"Test sequence: {len(result.test_sequence)} experiments")

    assert len(result.hypotheses) > 0, "Should generate hypotheses"
    print("\n[OK] InvestigationPlanner works!")
    return True


def test_failure_diagnoser():
    """Test the FailureDiagnoser module."""
    print("\n" + "="*60)
    print("TEST 3: FailureDiagnoser (Real LLM Call)")
    print("="*60)

    from rook.learning import FailureDiagnoser

    diagnoser = FailureDiagnoser()

    result = diagnoser(
        tool_name="rhino_boolean",
        params_used={"operation": "difference", "ids": ["abc123"]},
        error_message="Boolean difference requires targetId and toolIds parameters",
        available_geometry=["brep"],
        tool_schema={
            "required": ["operation"],
            "properties": {
                "operation": {"type": "string", "enum": ["union", "difference", "intersection"]},
                "targetId": {"type": "string", "description": "Target object GUID for difference"},
                "toolIds": {"type": "array", "description": "Tool object GUIDs for difference"},
            }
        },
    )

    print(f"\nError category: {result.error_category}")
    print(f"Root cause: {result.root_cause}")
    print(f"\nFix suggestions ({len(result.fix_suggestions)}):")
    for i, fix in enumerate(result.fix_suggestions[:3], 1):
        print(f"  {i}. {fix}")

    assert result.error_category is not None, "Should categorize error"
    assert result.root_cause, "Should identify root cause"
    print("\n[OK] FailureDiagnoser works!")
    return True


def test_mab_selectors():
    """Test MAB selectors (no LLM needed)."""
    print("\n" + "="*60)
    print("TEST 4: MAB Selectors")
    print("="*60)

    from rook.learning import HypothesisSelector, SelectionContext

    selector = HypothesisSelector()

    hypotheses = [
        "Curves must be parallel for loft to work",
        "Curves can be at any angle",
        "Curves should have same number of control points",
    ]

    context = SelectionContext(
        tool_name="rhino_loft",
        existing_pattern_count=2,
        existing_antipattern_count=1,
        session_progress=0.3,
        recent_success_rate=0.7,
        geometry_available=["curve"],
    )

    selected, idx = selector.select(hypotheses, context)
    print(f"Selected hypothesis: '{selected}' (index {idx})")

    # Simulate outcome and update
    selector.update(selected, success=True, context=context)
    print("Updated MAB with success")

    # Select again - should favor the successful one
    selected2, idx2 = selector.select(hypotheses, context)
    print(f"After update, selected: '{selected2}' (index {idx2})")

    print("\n[OK] MAB Selectors work!")
    return True


def main():
    print("="*60)
    print("DSPy + MABWiser Integration Test")
    print("="*60)

    tests = [
        ("DSPy Configuration", test_dspy_config),
        ("Investigation Planner", test_investigation_planner),
        ("Failure Diagnoser", test_failure_diagnoser),
        ("MAB Selectors", test_mab_selectors),
    ]

    results = []
    for name, test_fn in tests:
        try:
            success = test_fn()
            results.append((name, success, None))
        except Exception as e:
            print(f"\n[FAILED] {name}: {e}")
            results.append((name, False, str(e)))

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for name, success, error in results:
        status = "[OK]" if success else "[FAILED]"
        print(f"  {status} {name}")
        if error:
            print(f"         Error: {error}")

    passed = sum(1 for _, s, _ in results if s)
    print(f"\nPassed: {passed}/{len(results)}")

    return all(s for _, s, _ in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
