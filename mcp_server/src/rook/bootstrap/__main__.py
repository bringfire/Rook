"""
Bootstrap CLI

Command-line interface for running bootstrap tests.

Usage:
    python -m rook.bootstrap run --phase 1
    python -m rook.bootstrap status
    python -m rook.bootstrap summary
    python -m rook.bootstrap review
    python -m rook.bootstrap transfer
    python -m rook.bootstrap cleanup
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .test_matrix import TestPhase, TOOL_TESTS, get_test_count_by_phase
from .runner import BootstrapRunner, get_knowledge_summary
from .transfer import KnowledgeTransfer, interactive_review
from .executor import create_http_executor, create_mock_executor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("rook.bootstrap")


def create_executor(use_mock: bool = False, rhino_url: str | None = None):
    """
    Create an executor for running bootstrap tests.

    Args:
        use_mock: If True, use mock executor (no Rhino needed)
        rhino_url: URL of Rhino HTTP server

    Returns:
        Executor function or None if connection fails
    """
    if use_mock:
        logger.info("Using mock executor")
        return create_mock_executor()

    # Try to connect to Rhino
    executor = create_http_executor(rhino_url)
    if executor is None:
        logger.warning(f"Cannot connect to Rhino at {rhino_url}")
        return None

    return executor


def cmd_run(args):
    """Run bootstrap tests for a phase."""
    try:
        phase = TestPhase(args.phase)
    except ValueError:
        print(f"Invalid phase: {args.phase}")
        print(f"Valid phases: {[p.value for p in TestPhase]}")
        return 1

    print(f"\n{'='*60}")
    print(f"Running Bootstrap Phase {args.phase}: {phase.name}")
    print(f"{'='*60}\n")

    # Create executor
    executor = create_executor(use_mock=args.mock, rhino_url=args.url)

    # Check if we got an executor
    if executor is None:
        print("WARNING: Cannot connect to Rhino.")
        print("Options:")
        print("  1. Start Rhino with the RookNative or Rook plugin loaded")
        print("  2. Use --mock flag to run with mock executor\n")

        if not args.force:
            response = input("Continue with mock tests? [y/N]: ")
            if response.lower() != 'y':
                return 0
            executor = create_mock_executor()

    runner = BootstrapRunner(executor)

    # Show executor type
    if args.mock or executor.__name__ == "mock_execute":
        print("Using MOCK executor (simulated results)\n")
    else:
        print(f"Using HTTP executor (connected to Rhino)\n")

    # Run the phase
    session = runner.run_phase(phase)

    # Show summary
    summary = session.get_summary()
    print(f"\n{'='*60}")
    print("Session Summary")
    print(f"{'='*60}")
    print(f"  Total tests: {summary['total_tests']}")
    print(f"  Passed:      {summary['passed']} ({summary['pass_rate']}%)")
    print(f"  Successes:   {summary['successes']}")
    print(f"  Failures:    {summary['failures']}")
    print(f"  Errors:      {summary['errors']}")
    print(f"  Skipped:     {summary['skipped']}")

    # Save results
    runner.record_to_knowledge(session)
    runner.save_session(session)

    print(f"\nResults saved to local knowledge graph.")

    # Cleanup if requested
    if args.cleanup:
        print("\nCleaning up created objects...")
        runner.cleanup_created_objects(session)

    return 0


def cmd_status(args):
    """Show status of all phases."""
    runner = BootstrapRunner(None)
    status = runner.get_phase_status()

    print(f"\n{'='*60}")
    print("Bootstrap Phase Status")
    print(f"{'='*60}\n")

    for phase_name, info in status.items():
        check = "x" if info["complete"] else " "
        pct = info["completed"] / info["total"] * 100 if info["total"] > 0 else 0
        bar = "#" * int(pct / 10) + "-" * (10 - int(pct / 10))
        print(f"  [{check}] {phase_name:20} [{bar}] {info['completed']}/{info['total']}")

    return 0


def cmd_summary(args):
    """Show summary of knowledge system (production MAB)."""
    print(f"\n{'='*60}")
    print("Knowledge System Summary (Production MAB)")
    print(f"{'='*60}\n")

    # Get production knowledge summary
    summary = get_knowledge_summary()

    if not summary.get("exists"):
        print("  Knowledge system not initialized")
        if summary.get("error"):
            print(f"  Error: {summary['error']}")
        return 1

    # Knowledge Graph
    kg = summary.get("knowledge_graph", {})
    print("KNOWLEDGE GRAPH:")
    print(f"  Total nodes:   {kg.get('total_nodes', 0)}")
    print(f"  Total links:   {kg.get('total_links', 0)}")
    node_types = kg.get("node_types", {})
    if node_types:
        print(f"  Node types:    {node_types}")

    # Context-free MAB
    mab = summary.get("mab", {})
    print("\nCONTEXT-FREE MAB:")
    print(f"  Available:     {mab.get('available', False)}")
    print(f"  Model exists:  {mab.get('model_exists', False)}")

    # Contextual MAB
    cmab = summary.get("contextual_mab", {})
    print("\nCONTEXTUAL MAB:")
    print(f"  Available:     {cmab.get('available', False)}")
    print(f"  Is fitted:     {cmab.get('is_fitted', False)}")
    print(f"  Num arms:      {cmab.get('num_arms', 0)}")

    # Context History
    ch = summary.get("context_history", {})
    print("\nCONTEXT HISTORY:")
    print(f"  Observations:  {ch.get('total_observations', 0)}")

    return 0


def cmd_review(args):
    """Interactive review of pending knowledge."""
    pending = interactive_review()

    if pending["total_pending"] == 0:
        print("\nNo items pending review.")
        return 0

    if args.validate_all:
        transfer = KnowledgeTransfer()
        transfer.mark_all_validated(validated_by=args.validated_by or "cli")
        print(f"\nMarked all {pending['total_pending']} items as validated.")

    return 0


def cmd_transfer(args):
    """Transfer validated knowledge to canonical."""
    transfer = KnowledgeTransfer()

    # Check for pending items
    pending = transfer.get_pending_review()
    if pending["total_pending"] > 0 and not args.force:
        print(f"\nWARNING: {pending['total_pending']} items not yet validated.")
        print("Run with --force to transfer anyway, or review first.")
        return 1

    # Perform transfer
    result = transfer.transfer_validated()

    print(f"\n{'='*60}")
    print("Transfer Complete")
    print(f"{'='*60}")
    print(f"  Patterns transferred:     {result.patterns_transferred}")
    print(f"  Patterns skipped:         {result.patterns_skipped}")
    print(f"  Antipatterns transferred: {result.antipatterns_transferred}")
    print(f"  Antipatterns skipped:     {result.antipatterns_skipped}")

    if result.errors:
        print(f"\nErrors:")
        for e in result.errors:
            print(f"  - {e}")

    return 0


def cmd_tests(args):
    """List all defined tests."""
    print(f"\n{'='*60}")
    print("Defined Test Cases")
    print(f"{'='*60}\n")

    counts = get_test_count_by_phase()
    total = 0

    for phase in TestPhase:
        tests = TOOL_TESTS.get_phase(phase)
        if tests:
            print(f"\n{phase.name} ({len(tests)} tests):")
            for t in tests:
                exp = t.expected.value[0].upper()  # S/F/E
                print(f"  [{exp}] {t.id}: {t.description}")
            total += len(tests)

    print(f"\n{'='*60}")
    print(f"Total: {total} tests defined")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap Knowledge System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m rook.bootstrap run --phase 1
  python -m rook.bootstrap status
  python -m rook.bootstrap summary
  python -m rook.bootstrap review --validate-all
  python -m rook.bootstrap transfer
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # run command
    run_parser = subparsers.add_parser("run", help="Run bootstrap tests")
    run_parser.add_argument("--phase", "-p", type=int, required=True,
                           help="Phase number (1-11)")
    run_parser.add_argument("--cleanup", "-c", action="store_true",
                           help="Clean up created objects after tests")
    run_parser.add_argument("--force", "-f", action="store_true",
                           help="Run even without Rhino connection")
    run_parser.add_argument("--mock", "-m", action="store_true",
                           help="Use mock executor (no Rhino needed)")
    run_parser.add_argument("--url", type=str, default=None,
                           help="Rhino HTTP server URL (defaults to discovered active instance)")

    # status command
    subparsers.add_parser("status", help="Show phase status")

    # summary command
    subparsers.add_parser("summary", help="Show knowledge graph summary")

    # review command
    review_parser = subparsers.add_parser("review", help="Review pending knowledge")
    review_parser.add_argument("--validate-all", action="store_true",
                              help="Mark all pending as validated")
    review_parser.add_argument("--validated-by", type=str,
                              help="Name of validator")

    # transfer command
    transfer_parser = subparsers.add_parser("transfer", help="Transfer to canonical")
    transfer_parser.add_argument("--force", "-f", action="store_true",
                                help="Transfer even with unvalidated items")

    # tests command
    subparsers.add_parser("tests", help="List all defined tests")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "run": cmd_run,
        "status": cmd_status,
        "summary": cmd_summary,
        "review": cmd_review,
        "transfer": cmd_transfer,
        "tests": cmd_tests,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
