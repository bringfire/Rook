"""
Autonomous Learning Agent for Rook.

This is the main entry point for running autonomous learning sessions.
The agent uses the Claude Agent SDK to orchestrate multi-turn conversations
with tool use for knowledge cultivation.

The agent's purpose is to CULTIVATE THE KNOWLEDGE GRAPH:
1. Read from knowledge graph (what do we know?)
2. Find gaps (what don't we know?)
3. Investigate with problem-solving
4. Verify results visually
5. Write back to knowledge graph
6. Hand off to next instance

Usage:
    # Single session
    python -m rook.learning.agent --max-sessions 1

    # Continuous learning
    python -m rook.learning.agent --continuous

    # Focus on specific area
    python -m rook.learning.agent --focus "boolean_operations"
"""

import argparse
import asyncio
import logging
import sys
import warnings
from pathlib import Path
from typing import Any

# Try to import Claude Agent SDK
try:
    from claude_code_sdk import ClaudeCodeOptions, Message, query
    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False

from .session import LearningSession
from .graph import KnowledgeGraphV2
from .monitor import setup_logging, ProgressReporter
from ..bridge import call_rhino

logger = logging.getLogger("rook.learning.agent")

# Get all available MCP tools from server
def get_all_tools() -> list[str]:
    """Get list of all available MCP tool names."""
    # Import here to avoid circular imports
    try:
        from ..server import mcp
        return [tool.name for tool in mcp.list_tools()]
    except Exception:
        # Fallback: return known tools
        return [
            "rhino_ping", "rhino_document", "rhino_layers", "rhino_objects",
            "rhino_selection", "rhino_select", "rhino_geometry", "rhino_execute",
            "rhino_command", "rhino_viewport", "rhino_create", "rhino_delete",
            "rhino_transform", "rhino_copy", "rhino_layer_create", "rhino_layer_create_batch", "rhino_layer_delete",
            "rhino_layer_visibility", "rhino_layer_lock", "rhino_layer_current",
            "rhino_layer_set_properties", "rhino_layer_set_properties_batch", "rhino_layer_rename",
            "rhino_layer_move_objects", "rhino_layer_merge", "rhino_layer_dependencies",
            "rhino_materials", "rhino_material_purge", "rhino_linetypes", "rhino_linetype_purge",
            "rhino_block_layer_census",
            "rhino_select_by_type", "rhino_select_by_name", "rhino_select_all",
            "rhino_select_none", "rhino_select_invert", "rhino_deselect",
            "rhino_measure_distance", "rhino_measure_area", "rhino_measure_volume",
            "rhino_measure_length", "rhino_measure_bbox", "rhino_measure_centroid",
            "rhino_boolean", "rhino_extrude",
            "rhino_import", "rhino_export", "rhino_group",
            "rhino_blocks", "rhino_block_create", "rhino_block_insert",
            "rhino_block_explode", "rhino_block_delete", "rhino_block_rename",
            "rhino_block_description", "rhino_block_info", "rhino_block_add_objects",
            "rhino_block_remove_objects", "rhino_block_replace_geometry",
            "rhino_block_replace_object_geometry", "rhino_block_replace_object_geometry_batch",
            "rhino_block_transform_object", "rhino_block_transform_object_batch",
            "rhino_block_transform_instance_batch",
            "rhino_block_instances", "rhino_block_replace_instance", "rhino_block_replace_instance_batch",
            "rhino_block_reset_scale", "rhino_block_reset_scale_batch",
            "rhino_block_link", "rhino_block_refresh", "rhino_block_unlink",
            "rhino_block_purge", "rhino_block_duplicate", "rhino_block_nested",
            "knowledge_query", "rhino_knowledge_query", "knowledge_record",
        ]


# Agent system prompt for knowledge cultivation
AGENT_SYSTEM_PROMPT = '''
# Autonomous Knowledge Graph Cultivator for Rook

You are an autonomous agent whose purpose is to cultivate the Rook
knowledge graph. Every action you take should enrich collective understanding
of how Rhino's tools work.

## Your Purpose

The knowledge graph is the persistent memory for all Claude instances that
interact with Rhino. You are one of many instances that will contribute to it.
Future Claudes will be born knowing nothing - they inherit intelligence from
the knowledge graph you help build.

## Available Tools

You have access to all Rook MCP tools. The most important ones for
your work are:

- `knowledge_query` - Query BEFORE every action to get patterns and avoid mistakes
- `knowledge_record` - Record AFTER every action to capture what you learned
- `rhino_viewport` - Capture viewport to visually verify results
- `rhino_create` - Create test geometry
- Various Rhino tools to test and investigate

## Session Workflow

### 1. ORIENT (Always First)

Read the knowledge graph state:
- What patterns are known?
- What gaps exist?
- What was the last session working on?
- What should you focus on?

Use: knowledge_query to read current state

### 2. PRIORITIZE

Choose what to investigate based on:
- Highest priority gaps
- Tools with low confidence scores
- Unverified patterns that need confirmation
- Relationships between tools that aren't understood

### 3. INVESTIGATE (Problem-Solve, Don't Just Test)

For each investigation target:

a) Form hypothesis: "I think rhino_loft needs curves arranged in sequence"

b) Set up context: Create necessary geometry using known patterns
   - Use rhino_create to make test objects
   - Track IDs for later use

c) Run experiment: Try the operation with your hypothesis
   - Capture viewport BEFORE
   - Execute the tool
   - Capture viewport AFTER

d) Analyze result:
   - If SUCCESS: Verify visually, record pattern with high confidence
   - If FAILURE: Diagnose WHY, form new hypothesis, try alternatives

e) Record EVERYTHING:
   - What you tried
   - What happened
   - What you learned
   - What questions arose

### 4. VERIFY VISUALLY

Never trust API responses alone. Always:
- Capture viewport to see actual geometry
- Check that created objects are visible
- Verify transforms actually moved things
- Confirm boolean operations produced expected results

Use: rhino_viewport to capture images

### 5. RECORD TO KNOWLEDGE GRAPH

After each investigation:
- Record patterns discovered (with confidence scores)
- Record antipatterns (with diagnosis and attempted fixes)
- Record new gaps discovered
- Record insights about tool relationships

Use: knowledge_record with rich structured data

### 6. HANDOFF

When you sense context filling up or after completing targets:
- Summarize what you accomplished
- Identify next priorities
- Write notes for next instance

## Quality Standards

- NEVER mark something as working without visual verification
- ALWAYS record the diagnosis for failures, not just "it failed"
- ALWAYS try alternatives when something fails
- ALWAYS write session handoff notes
'''


async def create_tool_executor():
    """
    Create an async tool executor that calls MCP tools.

    Returns:
        Async function that executes MCP tools
    """
    async def execute_tool(tool_name: str, params: dict) -> dict:
        """Execute an MCP tool via HTTP."""
        # Map tool name to HTTP endpoint
        endpoint_map = {
            "rhino_ping": ("GET", "/ping"),
            "rhino_document": ("GET", "/document"),
            "rhino_layers": ("GET", "/layers"),
            "rhino_objects": ("GET", "/objects"),
            "rhino_selection": ("GET", "/selection"),
            "rhino_viewport": ("GET", "/viewport"),
            "rhino_geometry": ("GET", "/geometry"),
            "rhino_create": ("POST", "/create"),
            "rhino_delete": ("POST", "/delete"),
            "rhino_transform": ("POST", "/transform"),
            "rhino_copy": ("POST", "/copy"),
            "rhino_select": ("POST", "/select"),
            "rhino_execute": ("POST", "/execute"),
            "rhino_command": ("POST", "/command"),
            "rhino_layer_create": ("POST", "/layers"),
            "rhino_layer_create_batch": ("POST", "/layers/batch"),
            "rhino_layer_delete": ("DELETE", "/layers"),
            "rhino_layer_set_properties": ("POST", "/layers/properties"),
            "rhino_layer_set_properties_batch": ("POST", "/layers/properties-batch"),
            "rhino_layer_rename": ("POST", "/layers/rename"),
            "rhino_layer_move_objects": ("POST", "/layers/move-objects"),
            "rhino_layer_merge": ("POST", "/layers/merge"),
            "rhino_layer_dependencies": ("GET", "/layers/dependencies"),
            "rhino_materials": ("GET", "/materials"),
            "rhino_material_purge": ("POST", "/materials/purge"),
            "rhino_linetypes": ("GET", "/linetypes"),
            "rhino_linetype_purge": ("POST", "/linetypes/purge"),
            "rhino_block_layer_census": ("GET", "/block/layer-census"),
            "rhino_boolean": ("POST", "/boolean"),
            # extrude uses /create with type - handled in special cases below
            "rhino_extrude": ("POST", "/create"),
            # Selection tools - all use /select with different params
            "rhino_select_by_type": ("POST", "/select"),
            "rhino_select_by_name": ("POST", "/select"),
            "rhino_select_all": ("POST", "/select"),
            "rhino_select_none": ("POST", "/select"),
            "rhino_select_invert": ("POST", "/select"),
            "rhino_deselect": ("POST", "/select"),
            # Measurement tools - use /measure/xxx endpoints
            "rhino_measure_distance": ("POST", "/measure/distance"),
            "rhino_measure_area": ("POST", "/measure/area"),
            "rhino_measure_volume": ("POST", "/measure/volume"),
            "rhino_measure_length": ("POST", "/measure/length"),
            "rhino_measure_bbox": ("POST", "/measure/bbox"),
            "rhino_measure_centroid": ("POST", "/measure/centroid"),
            # Layer visibility/lock tools (endpoints are /layers/xxx)
            "rhino_layer_visibility": ("POST", "/layers/visibility"),
            "rhino_layer_lock": ("POST", "/layers/lock"),
            "rhino_layer_current": ("POST", "/layers/current"),
            # Import/Export
            "rhino_import": ("POST", "/import"),
            "rhino_export": ("POST", "/export"),
            # Groups
            "rhino_group": ("POST", "/group"),
            # Block tools
            "rhino_blocks": ("GET", "/blocks"),
            "rhino_block_create": ("POST", "/block/create"),
            "rhino_block_insert": ("POST", "/block/insert"),
            "rhino_block_explode": ("POST", "/block/explode"),
            "rhino_block_delete": ("DELETE", "/block"),
            "rhino_block_rename": ("POST", "/block/rename"),
            "rhino_block_description": ("POST", "/block/description"),
            "rhino_block_info": ("POST", "/block/info"),
            "rhino_block_add_objects": ("POST", "/block/add-objects"),
            "rhino_block_remove_objects": ("POST", "/block/remove-objects"),
            "rhino_block_replace_geometry": ("POST", "/block/replace-geometry"),
            "rhino_block_replace_object_geometry": ("POST", "/block/replace-object-geometry"),
            "rhino_block_replace_object_geometry_batch": ("POST", "/block/replace-object-geometry-batch"),
            "rhino_block_transform_object": ("POST", "/block/transform-object"),
            "rhino_block_transform_object_batch": ("POST", "/block/transform-object-batch"),
            "rhino_block_transform_instance_batch": ("POST", "/block/transform-instance-batch"),
            "rhino_block_instances": ("POST", "/block/instances"),
            "rhino_block_replace_instance": ("POST", "/block/replace-instance"),
            "rhino_block_replace_instance_batch": ("POST", "/block/replace-instance-batch"),
            "rhino_block_reset_scale": ("POST", "/block/reset-scale"),
            "rhino_block_reset_scale_batch": ("POST", "/block/reset-scale-batch"),
            "rhino_block_link": ("POST", "/block/link"),
            "rhino_block_refresh": ("POST", "/block/refresh"),
            "rhino_block_unlink": ("POST", "/block/unlink"),
            "rhino_block_purge": ("POST", "/block/purge"),
            "rhino_block_duplicate": ("POST", "/block/duplicate"),
            "rhino_block_nested": ("POST", "/block/nested"),
        }

        # Transform params for selection tools that need special handling
        if tool_name == "rhino_select_all":
            params = {"all": True}
        elif tool_name == "rhino_select_none":
            params = {"none": True}
        elif tool_name == "rhino_select_invert":
            params = {"invert": True}
        elif tool_name == "rhino_deselect":
            params = {"deselectIds": params.get("ids", []), "clear": False}

        # Add type param for extrude (uses /create endpoint)
        if tool_name == "rhino_extrude":
            params = dict(params)
            params["type"] = "EXTRUDE"

        # Get method and endpoint
        if tool_name in endpoint_map:
            method, endpoint = endpoint_map[tool_name]
        else:
            # Default: POST to /tool_name (without rhino_ prefix)
            method = "POST"
            endpoint = "/" + tool_name.replace("rhino_", "")

        result = await call_rhino(endpoint, method, params or None)
        if result.get("success", False):
            return result

        error = result.get("data", result.get("error", "Unknown error"))
        return {"success": False, "error": str(error)}

    return execute_tool


class AutonomousLearningAgent:
    """
    Long-running agent that cultivates the knowledge graph.

    .. deprecated::
        This class is not currently used by the MCP server. Consider using
        HybridInvestigator for active learning workflows instead. This class
        may be removed in a future version.

    Can run as:
    - Single session (quick exploration)
    - Continuous mode (keeps running until stopped)
    - Focused mode (investigates specific area)
    """

    def __init__(
        self,
        focus: str | None = None,
        max_investigations_per_session: int = 20,
    ):
        """
        Initialize the agent.

        Args:
            focus: Optional area to focus on (e.g., "boolean_operations")
            max_investigations_per_session: Max investigations before handoff
        """
        warnings.warn(
            "AutonomousLearningAgent is deprecated and not used by the MCP server. "
            "Consider using HybridInvestigator instead. This class may be removed "
            "in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.focus = focus
        self.max_investigations = max_investigations_per_session
        self.all_tools = get_all_tools()
        self._stop_requested = False

    async def run_session(self) -> dict[str, Any]:
        """
        Run one learning session.

        Returns:
            Session result summary
        """
        # Create tool executor
        executor = await create_tool_executor()

        # Create session
        session = LearningSession(
            executor=executor,
            all_tools=self.all_tools,
        )

        # Run session
        handoff = await session.run(max_cycles=self.max_investigations)

        return {
            "session_id": session.session_id,
            "status": session.get_status(),
            "handoff": handoff.to_dict(),
        }

    async def run_continuous(self, max_sessions: int | None = None) -> None:
        """
        Run continuous learning sessions.

        Args:
            max_sessions: Optional limit on total sessions
        """
        session_count = 0

        logger.info("Starting continuous learning mode")

        while not self._stop_requested:
            session_count += 1
            logger.info(f"Starting session {session_count}")

            try:
                result = await self.run_session()
                logger.info(f"Session {session_count} complete: {result['status']['progress']}")
            except Exception as e:
                logger.error(f"Session {session_count} failed: {e}")

            if max_sessions and session_count >= max_sessions:
                logger.info(f"Reached max sessions ({max_sessions})")
                break

            # Brief pause between sessions
            await asyncio.sleep(2)

        logger.info(f"Completed {session_count} sessions")

    def stop(self):
        """Request stop (will complete current session first)."""
        self._stop_requested = True
        logger.info("Stop requested")

    async def run_with_claude_sdk(self, prompt: str | None = None) -> None:
        """
        Run using Claude Agent SDK for extended sessions.

        This uses the Claude SDK to orchestrate multi-turn conversations
        with tool use, allowing for more sophisticated exploration.

        Args:
            prompt: Optional initial prompt (uses default if not provided)
        """
        if not CLAUDE_SDK_AVAILABLE:
            logger.error("Claude Agent SDK not available. Install with: pip install claude-code-sdk")
            raise ImportError("Claude Agent SDK not installed")

        initial_prompt = prompt or """
        You are starting a knowledge cultivation session. Your goal is to enrich
        the Rook knowledge graph by investigating tools, finding patterns,
        and recording everything you learn.

        Start by:
        1. Query the knowledge graph to understand current state
        2. Identify gaps or low-confidence areas
        3. Pick an investigation target
        4. Begin systematic exploration

        Focus on: {focus}
        """.format(focus=self.focus or "general tool coverage")

        logger.info("Starting Claude SDK session")

        # Create Claude client with MCP configuration
        options = ClaudeCodeOptions(
            system_prompt=AGENT_SYSTEM_PROMPT,
            max_turns=50,  # Allow many turns for exploration
            allowed_tools=self.all_tools + ["knowledge_query", "knowledge_record"],
        )

        # Run the conversation
        async for message in query(initial_prompt, options=options):
            if isinstance(message, Message):
                logger.info(f"Agent: {message.content[:200]}...")

        logger.info("Claude SDK session complete")


async def main():
    """Main entry point for the learning agent."""
    parser = argparse.ArgumentParser(
        description="Autonomous Learning Agent for Rook"
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=1,
        help="Maximum number of sessions to run (default: 1)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run continuously until stopped"
    )
    parser.add_argument(
        "--focus",
        type=str,
        default=None,
        help="Focus on specific area (e.g., 'boolean_operations')"
    )
    parser.add_argument(
        "--max-investigations",
        type=int,
        default=20,
        help="Max investigations per session (default: 20)"
    )
    parser.add_argument(
        "--use-sdk",
        action="store_true",
        help="Use Claude Agent SDK for orchestration"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--no-file-log",
        action="store_true",
        help="Disable logging to file"
    )

    args = parser.parse_args()

    # Setup structured logging (to file and console)
    setup_logging(verbose=args.verbose, log_to_file=not args.no_file_log)

    logger.info("=" * 60)
    logger.info("AUTONOMOUS LEARNING AGENT STARTING")
    logger.info("=" * 60)
    logger.info(f"Mode: {'continuous' if args.continuous else f'{args.max_sessions} session(s)'}")
    if args.focus:
        logger.info(f"Focus: {args.focus}")
    logger.info(f"Max investigations per session: {args.max_investigations}")
    logger.info("=" * 60)

    # Create agent
    agent = AutonomousLearningAgent(
        focus=args.focus,
        max_investigations_per_session=args.max_investigations,
    )

    # Run
    try:
        if args.use_sdk:
            await agent.run_with_claude_sdk()
        elif args.continuous:
            await agent.run_continuous(max_sessions=None)
        else:
            await agent.run_continuous(max_sessions=args.max_sessions)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        agent.stop()
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        raise
    finally:
        logger.info("Agent shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
