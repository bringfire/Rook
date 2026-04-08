"""
Entry point for running the Autonomous Learning Agent.

Usage:
    # Single session (default)
    python -m rook.learning

    # Continuous mode
    python -m rook.learning --continuous

    # Focused investigation
    python -m rook.learning --focus "mesh_operations"

    # With Claude SDK orchestration
    python -m rook.learning --use-sdk

    # Verbose logging
    python -m rook.learning --verbose

    # Check agent status (from another terminal)
    python -m rook.learning --status

    # Tail the log file
    python -m rook.learning --tail [lines]
"""

import sys
import asyncio
from .agent import main
from .monitor import print_agent_status, tail_log


def cli_main():
    """CLI entry point with status and tail commands."""
    # Check for status/tail commands first
    if len(sys.argv) > 1:
        if sys.argv[1] == "--status":
            print_agent_status()
            return

        if sys.argv[1] == "--tail":
            lines = 20
            if len(sys.argv) > 2:
                try:
                    lines = int(sys.argv[2])
                except ValueError:
                    pass
            tail_log(lines)
            return

    # Otherwise run the agent
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
