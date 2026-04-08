"""
Knowledge Explorer CLI

Usage:
    python -m rook.explorer sweep          # Test all tools once
    python -m rook.explorer deep           # Deep explore all tools
    python -m rook.explorer deep --tool X  # Deep explore specific tool
    python -m rook.explorer resume         # Resume previous session
    python -m rook.explorer coverage       # Show coverage report
    python -m rook.explorer reset          # Reset state
"""

import argparse
import asyncio
import json
import logging
import sys

from .agent import KnowledgeExplorer
from .registry import get_registry
from .state import ExplorerState


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_sweep(args: argparse.Namespace) -> int:
    """Run systematic sweep."""
    explorer = KnowledgeExplorer()

    categories = None
    if args.category:
        categories = [args.category]

    result = explorer.sweep_sync(categories=categories, stateful=args.stateful)

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print("\n" + "=" * 60)
    print(f"{'STATEFUL ' if args.stateful else ''}SWEEP COMPLETE")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    return 0


def cmd_deep(args: argparse.Namespace) -> int:
    """Run deep exploration."""
    explorer = KnowledgeExplorer()

    result = explorer.deep_sync(
        tool_name=args.tool,
        iterations=args.iterations,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print("\n" + "=" * 60)
    print("DEEP EXPLORATION COMPLETE")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume previous session."""
    explorer = KnowledgeExplorer()
    result = explorer.resume_sync()

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print("\n" + "=" * 60)
    print("RESUME COMPLETE")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    """Show coverage report."""
    # Load registry
    registry = get_registry()
    asyncio.run(registry.load())

    # Load state
    state = ExplorerState()
    state.load()

    # Get coverage
    explorer = KnowledgeExplorer()
    coverage = explorer.get_coverage()

    print("\n" + "=" * 60)
    print("KNOWLEDGE EXPLORER COVERAGE REPORT")
    print("=" * 60)

    print(f"\nTotal MCP Tools: {coverage['total_tools']}")
    print(f"Explorable Tools: {coverage['explorable_tools']}")
    print(f"Tools Tested: {coverage['tested']}")
    print(f"Tools Remaining: {coverage['remaining']}")
    print(f"Coverage: {coverage['coverage_pct']:.1f}%")

    print("\nBy Category:")
    for cat, stats in coverage.get("by_category", {}).items():
        pct = (stats["tested"] / stats["total"] * 100) if stats["total"] > 0 else 0
        print(f"  {cat}: {stats['tested']}/{stats['total']} ({pct:.0f}%)")

    # Show uncovered tools
    completed = set(state.state.get("tools_completed", []))
    uncovered = [t.name for t in registry.get_explorable_tools() if t.name not in completed]

    if uncovered and len(uncovered) <= 20:
        print(f"\nUncovered tools ({len(uncovered)}):")
        for name in uncovered:
            print(f"  - {name}")
    elif uncovered:
        print(f"\nUncovered tools: {len(uncovered)} (run 'sweep' to test them)")

    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Reset explorer state."""
    state = ExplorerState()
    state.reset()
    print("Explorer state reset.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all tools."""
    registry = get_registry()
    asyncio.run(registry.load())

    print("\n" + "=" * 60)
    print(f"MCP TOOLS ({len(registry)} total)")
    print("=" * 60)

    by_category = {}
    for tool in registry:
        cat = tool.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(tool)

    for cat, tools in sorted(by_category.items()):
        print(f"\n{cat.upper()} ({len(tools)} tools):")
        for tool in sorted(tools, key=lambda t: t.name):
            req = ", ".join(tool.required_params) if tool.required_params else "(none)"
            print(f"  {tool.name}")
            print(f"    Required: {req}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Knowledge Explorer - Autonomous MCP tool exploration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # sweep command
    sweep_parser = subparsers.add_parser("sweep", help="Run systematic sweep of all tools")
    sweep_parser.add_argument(
        "--category",
        choices=["stateless", "creation", "modification", "multi_object"],
        help="Only test tools in this category",
    )
    sweep_parser.add_argument(
        "--stateful",
        action="store_true",
        help="Create test geometry first and use real IDs (higher success rate)",
    )

    # deep command
    deep_parser = subparsers.add_parser("deep", help="Deep exploration with variations")
    deep_parser.add_argument("--tool", help="Specific tool to explore")
    deep_parser.add_argument(
        "--iterations", type=int, default=20, help="Iterations per tool (default: 20)"
    )

    # resume command
    subparsers.add_parser("resume", help="Resume previous exploration session")

    # coverage command
    subparsers.add_parser("coverage", help="Show coverage report")

    # reset command
    subparsers.add_parser("reset", help="Reset explorer state")

    # list command
    subparsers.add_parser("list", help="List all MCP tools")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "sweep": cmd_sweep,
        "deep": cmd_deep,
        "resume": cmd_resume,
        "coverage": cmd_coverage,
        "reset": cmd_reset,
        "list": cmd_list,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
