"""
Knowledge Explorer Agent - Main orchestration class.

Autonomous agent that systematically explores MCP tools and builds knowledge.
Enhanced with stateful exploration that creates test geometry and uses real IDs.
"""

import asyncio
import logging
from typing import Any

from .registry import ToolRegistry, ToolDefinition, get_registry
from .generator import ParamGenerator
from .executor import HttpExecutor, ExecutionResult
from .analyzer import ResultAnalyzer, AnalysisResult
from .recorder import KnowledgeRecorder
from .state import ExplorerState
from .context import ExplorationContext, GeometryType, parse_create_result

logger = logging.getLogger("explorer.agent")


class KnowledgeExplorer:
    """
    Autonomous agent that explores MCP tools and builds knowledge.

    Supports multiple modes:
    - sweep: One test per tool (stateless, fast)
    - sweep_stateful: Creates test geometry first, then tests with real IDs
    - deep: Exhaustive exploration of each tool with variations
    - curiosity: Background learning prioritizing unexplored areas
    """

    def __init__(
        self,
        executor: HttpExecutor | None = None,
        state_file: str | None = None,
    ):
        self.registry = get_registry()
        self.context = ExplorationContext()
        self.generator = ParamGenerator(self.context)
        self.executor = executor or HttpExecutor()
        self.analyzer = ResultAnalyzer()
        self.recorder = KnowledgeRecorder()
        self.state = ExplorerState(state_file)

        self._running = False
        self._results: list[ExecutionResult] = []

    async def initialize(self) -> bool:
        """Initialize the explorer (load registry, check connection)."""
        try:
            # Load tool definitions
            await self.registry.load()
            logger.info(f"Loaded {len(self.registry)} tools from registry")

            # Check Rhino connection
            if not await self.executor.ping():
                logger.error("Cannot connect to Rhino - is it running?")
                return False

            logger.info("Connected to Rhino")
            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    def initialize_sync(self) -> bool:
        """Synchronous initialization."""
        return asyncio.run(self.initialize())

    async def setup_test_geometry(self) -> dict[str, Any]:
        """
        Create test geometry for stateful exploration.

        Creates various geometry types (breps, curves, meshes, SubDs)
        that modification tools can operate on.
        """
        logger.info("Setting up test geometry...")

        setup_sequence = self.generator.generate_setup_sequence()
        created = 0
        failed = 0

        for tool_name, params in setup_sequence:
            result = await self.executor.execute(tool_name, params)

            if result.success:
                # Parse the result and track the created object
                # result.response is already {"success": True, "data": {...}} from Rhino
                obj_id, geom_type = parse_create_result(
                    result.response,
                    tool_name,
                    params
                )

                if obj_id and geom_type:
                    self.context.add_object(
                        obj_id=obj_id,
                        geometry_type=geom_type,
                        tool_used=tool_name,
                        params_used=params,
                        name=params.get("name"),
                        layer=params.get("layer"),
                    )
                    created += 1
                    logger.debug(f"Created {geom_type.value}: {obj_id}")

                # Track layers
                if tool_name == "rhino_layer_create" and result.response:
                    layer_name = params.get("name")
                    if layer_name:
                        self.context.add_layer(layer_name)
            else:
                failed += 1
                logger.warning(f"Failed to create: {tool_name} - {result.error}")

        stats = self.context.get_stats()
        logger.info(f"Setup complete: {created} objects created, {failed} failed")
        logger.info(f"Context: {stats}")

        return {
            "created": created,
            "failed": failed,
            "context": stats,
        }

    async def sweep(self, categories: list[str] | None = None, stateful: bool = False) -> dict[str, Any]:
        """
        Mode 1: Systematic sweep - one test per tool.

        Args:
            categories: Optional list of categories to test
            stateful: If True, create test geometry first and use real IDs

        Tests all tools with valid parameters, recording outcomes.
        """
        if not await self.initialize():
            return {"error": "Failed to initialize"}

        # Set up test geometry if stateful mode requested
        if stateful:
            setup_result = await self.setup_test_geometry()
            if setup_result["created"] == 0:
                logger.warning("No test geometry created - some tools may fail")

        # Get tools to test
        tools = self._get_tools_for_sweep(categories)
        logger.info(f"Starting {'stateful ' if stateful else ''}sweep of {len(tools)} tools")

        # Start session
        tool_names = [t.name for t in tools]
        self.state.start_session("sweep_stateful" if stateful else "sweep", tool_names)

        self._running = True
        self._results = []

        for tool in tools:
            if not self._running:
                break

            result = await self._test_tool(tool)
            self._results.append(result)

            # Track created objects from creation tools
            if result.success and tool.category == "creation":
                self._track_created_object(tool.name, result)

            # Analyze and record
            analysis = self.analyzer.analyze(result)
            await self.recorder.record(result, analysis)

            # Update state
            self.state.record_result(tool.name, result.success)

            # Progress logging
            progress = self.state.get_progress()
            logger.info(
                f"[{progress['tested']}/{progress['total_tools']}] "
                f"{tool.name}: {'✓' if result.success else '✗'}"
            )

        self._running = False

        # Return summary
        summary = self._get_summary()
        if stateful:
            summary["context"] = self.context.get_stats()
        return summary

    def sweep_sync(self, categories: list[str] | None = None, stateful: bool = False) -> dict[str, Any]:
        """Synchronous sweep."""
        return asyncio.run(self.sweep(categories, stateful))

    async def deep(
        self,
        tool_name: str | None = None,
        iterations: int = 20,
        stateful: bool = True,
    ) -> dict[str, Any]:
        """
        Mode 2: Deep exploration - exhaustive testing of tools.

        Tests each tool with multiple parameter variations,
        including edge cases and boundary values.

        Args:
            tool_name: Specific tool to explore (None = all tools)
            iterations: Number of variations per tool
            stateful: If True, create test geometry first (default: True)
        """
        if not await self.initialize():
            return {"error": "Failed to initialize"}

        # Set up test geometry for deep exploration
        if stateful:
            setup_result = await self.setup_test_geometry()
            logger.info(f"Setup: {setup_result['created']} test objects created")

        if tool_name:
            tools = [self.registry.get_tool(tool_name)]
            if tools[0] is None:
                return {"error": f"Unknown tool: {tool_name}"}
        else:
            tools = list(self.registry.get_explorable_tools())

        logger.info(f"Starting deep exploration of {len(tools)} tools, {iterations} iterations each")

        self._running = True
        self._results = []

        for tool in tools:
            if not self._running:
                break

            logger.info(f"Deep exploring: {tool.name}")

            # Generate variations
            variations = self.generator.generate_variations(tool, count=iterations)

            for i, params in enumerate(variations):
                if not self._running:
                    break

                result = await self._execute_with_params(tool, params)
                self._results.append(result)

                # Track created objects
                if result.success and tool.category == "creation":
                    self._track_created_object(tool.name, result)

                analysis = self.analyzer.analyze(result)
                await self.recorder.record(result, analysis)

                logger.debug(
                    f"  [{i+1}/{len(variations)}] {tool.name}: "
                    f"{'✓' if result.success else '✗'}"
                )

                # If failed, try to find correction
                if not result.success:
                    correction = await self._find_correction(tool, params)
                    if correction:
                        self._results.append(correction)
                        await self.recorder.record(
                            correction,
                            self.analyzer.analyze(correction),
                        )

        self._running = False

        summary = self._get_summary()
        summary["context"] = self.context.get_stats()
        return summary

    def deep_sync(
        self,
        tool_name: str | None = None,
        iterations: int = 20,
        stateful: bool = True,
    ) -> dict[str, Any]:
        """Synchronous deep exploration."""
        return asyncio.run(self.deep(tool_name, iterations, stateful))

    async def resume(self) -> dict[str, Any]:
        """Resume a previous exploration session."""
        if not await self.initialize():
            return {"error": "Failed to initialize"}

        self.state.load()
        progress = self.state.get_progress()

        if progress["remaining"] == 0:
            return {"message": "Previous session complete, nothing to resume"}

        remaining = self.state.resume_session()
        logger.info(f"Resuming with {len(remaining)} tools remaining")

        # Re-setup test geometry for resumed session
        await self.setup_test_geometry()

        self._running = True
        self._results = []

        for tool_name in remaining:
            if not self._running:
                break

            tool = self.registry.get_tool(tool_name)
            if tool is None:
                logger.warning(f"Unknown tool in state: {tool_name}")
                continue

            result = await self._test_tool(tool)
            self._results.append(result)

            analysis = self.analyzer.analyze(result)
            await self.recorder.record(result, analysis)
            self.state.record_result(tool.name, result.success)

        self._running = False
        return self._get_summary()

    def resume_sync(self) -> dict[str, Any]:
        """Synchronous resume."""
        return asyncio.run(self.resume())

    def _track_created_object(self, tool_name: str, result: ExecutionResult) -> None:
        """Track an object created during exploration."""
        # result.response is already {"success": True, "data": {...}} from Rhino
        obj_id, geom_type = parse_create_result(
            result.response,
            tool_name,
            result.params
        )

        if obj_id and geom_type:
            self.context.add_object(
                obj_id=obj_id,
                geometry_type=geom_type,
                tool_used=tool_name,
                params_used=result.params,
                name=result.params.get("name"),
                layer=result.params.get("layer"),
            )

    async def _test_tool(self, tool: ToolDefinition) -> ExecutionResult:
        """Test a single tool with generated parameters."""
        self.state.set_current_tool(tool.name)

        # Generate valid parameters (will use context for IDs)
        params = self.generator.generate_valid(tool)

        return await self._execute_with_params(tool, params)

    async def _execute_with_params(
        self, tool: ToolDefinition, params: dict[str, Any]
    ) -> ExecutionResult:
        """Execute a tool with specific parameters."""
        try:
            result = await self.executor.execute(tool.name, params)
            return result
        except Exception as e:
            return ExecutionResult(
                tool_name=tool.name,
                params=params,
                success=False,
                error=str(e),
            )

    async def _find_correction(
        self,
        tool: ToolDefinition,
        failed_params: dict[str, Any],
        max_attempts: int = 5,
    ) -> ExecutionResult | None:
        """Try to find working parameters after a failure."""
        logger.debug(f"Attempting to find correction for {tool.name}")

        # Generate alternative parameter sets
        alternatives = self.generator.generate_variations(
            tool, count=max_attempts, strategy="mutation"
        )

        for alt_params in alternatives:
            result = await self._execute_with_params(tool, alt_params)

            if result.success:
                logger.info(f"Found correction for {tool.name}")
                return result

        return None

    def _get_tools_for_sweep(
        self, categories: list[str] | None = None
    ) -> list[ToolDefinition]:
        """Get tools to include in sweep based on categories."""
        if categories:
            tools = []
            for cat in categories:
                tools.extend(self.registry.get_by_category(cat))
            return tools

        # Default: all explorable tools, organized by category
        # Start with stateless (safest), then creation, then modification
        tools = []
        tools.extend(self.registry.get_stateless_tools())
        tools.extend(self.registry.get_creation_tools())
        tools.extend(self.registry.get_modification_tools())
        tools.extend(self.registry.get_multi_object_tools())
        return tools

    def _get_summary(self) -> dict[str, Any]:
        """Get summary of exploration results."""
        batch_summary = self.analyzer.summarize_batch(self._results)
        recorder_summary = self.recorder.get_summary()
        progress = self.state.get_progress()

        return {
            "progress": progress,
            "execution": batch_summary,
            "recordings": recorder_summary,
        }

    def stop(self) -> None:
        """Stop the current exploration."""
        self._running = False
        logger.info("Exploration stopped")

    def get_coverage(self) -> dict[str, Any]:
        """Get coverage statistics."""
        self.state.load()
        progress = self.state.get_progress()

        # Get tool counts by category
        category_counts = self.registry.count_by_category()

        # Get tested tools per category
        completed = set(self.state.state.get("tools_completed", []))
        category_tested = {}
        for tool in self.registry.get_explorable_tools():
            cat = tool.category
            if cat not in category_tested:
                category_tested[cat] = {"total": 0, "tested": 0}
            category_tested[cat]["total"] += 1
            if tool.name in completed:
                category_tested[cat]["tested"] += 1

        return {
            "total_tools": len(self.registry),
            "explorable_tools": len(list(self.registry.get_explorable_tools())),
            "tested": progress["tested"],
            "remaining": progress["remaining"],
            "coverage_pct": progress["progress_pct"],
            "by_category": category_tested,
        }

    def clear_context(self) -> None:
        """Clear the exploration context (tracked objects)."""
        self.context.clear()
        logger.info("Exploration context cleared")
