"""
Planner Agent
=============

Accepts a high-level user request, inspects the project via read-only tools,
decomposes into concrete tasks, and dispatches workers for execution.

Architecture:
    Planner (Sonnet, read-only) -> Plan JSON -> Workers (Haiku, full tools)

The Planner never modifies geometry or canvas. It calls ``submit_plan`` to
output a structured plan, which is then executed via run_task/run_swarm.

Ported from Engram's Planner, adapted for Rhino/GH domain.

Usage:
    from rook.agent.planner import Planner
    from rook.agent.config import PlannerConfig

    planner = Planner(PlannerConfig())
    result = await planner.run("Build a parametric staircase")
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import AgentConfig, PlannerConfig
from .events import (
    AgentEvent, EventDispatcher,
    PLAN_CREATED, PLAN_EXECUTING, PLAN_COMPLETE,
    CHECKPOINT_PASS, CHECKPOINT_FAIL,
)
from .model_profiles import api_base_for_model

logger = logging.getLogger(__name__)


# =============================================================================
# Plan Schema
# =============================================================================

@dataclass
class TaskSpec:
    """A single task in a plan."""
    task_id: str
    description: str
    tool_groups: List[str] = field(default_factory=list)
    workspace_assets: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    success_criteria: str = ""
    estimated_turns: int = 15
    retry_on_failure: bool = True
    agent_type: str = "worker"
    postconditions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Plan:
    """A decomposed execution plan."""
    goal: str
    tasks: List[TaskSpec] = field(default_factory=list)
    execution_groups: List[List[str]] = field(default_factory=list)
    total_estimated_cost: float = 0.0
    rollback_notes: str = ""

    def get_task(self, task_id: str) -> Optional[TaskSpec]:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def validate(self) -> List[str]:
        """Validate plan structure. Returns error messages (empty = valid)."""
        errors: List[str] = []
        task_ids = {t.task_id for t in self.tasks}

        if not self.tasks:
            errors.append("Plan has no tasks")
            return errors
        if not self.execution_groups:
            errors.append("Plan has no execution groups")
            return errors

        # Dependency references
        for t in self.tasks:
            for dep in t.depends_on:
                if dep not in task_ids:
                    errors.append(
                        f"Task '{t.task_id}' depends on unknown task '{dep}'"
                    )

        # Execution group references
        for gi, group in enumerate(self.execution_groups):
            for tid in group:
                if tid not in task_ids:
                    errors.append(
                        f"Execution group {gi} references unknown task '{tid}'"
                    )

        # Asset exclusivity within parallel groups
        for gi, group in enumerate(self.execution_groups):
            if len(group) > 1:
                seen: Dict[str, str] = {}
                for tid in group:
                    task = self.get_task(tid)
                    if task:
                        for asset in task.workspace_assets:
                            norm = asset.strip().rstrip("/")
                            if norm in seen:
                                errors.append(
                                    f"Asset conflict in group {gi}: '{norm}' "
                                    f"claimed by '{seen[norm]}' and '{tid}'"
                                )
                            seen[norm] = tid

        # All tasks in at least one group
        grouped = set()
        for group in self.execution_groups:
            grouped.update(group)
        orphans = task_ids - grouped
        if orphans:
            errors.append(f"Tasks not in any execution group: {orphans}")

        # Dependency ordering
        task_group_index: Dict[str, int] = {}
        for gi, group in enumerate(self.execution_groups):
            for tid in group:
                task_group_index[tid] = gi

        for t in self.tasks:
            t_gi = task_group_index.get(t.task_id, -1)
            for dep in t.depends_on:
                dep_gi = task_group_index.get(dep, -1)
                if dep_gi >= 0 and t_gi >= 0 and dep_gi >= t_gi:
                    errors.append(
                        f"Task '{t.task_id}' (group {t_gi}) depends on "
                        f"'{dep}' (group {dep_gi}), but dependencies must "
                        f"be in an earlier group"
                    )

        return errors


@dataclass
class PlanResult:
    """Result from a complete plan execution."""
    goal: str
    plan: Plan
    task_results: List[Any] = field(default_factory=list)  # List[SpawnResult]
    status: str = ""
    total_cost_usd: float = 0.0
    total_wall_time_s: float = 0.0
    planning_cost_usd: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "result_type": "plan",
            "goal": self.goal,
            "plan": asdict(self.plan),
            "task_results": [
                r.to_dict() if hasattr(r, "to_dict") else r
                for r in self.task_results
            ],
            "status": self.status,
            "total_cost_usd": self.total_cost_usd,
            "total_wall_time_s": self.total_wall_time_s,
            "planning_cost_usd": self.planning_cost_usd,
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class CheckpointResult:
    """Result from postcondition verification between execution groups."""
    group_index: int
    passed: bool
    checks: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# submit_plan tool schema (registered as local tool on the planning agent)
# =============================================================================

SUBMIT_PLAN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": (
            "Submit the final execution plan. Call this ONCE when planning is "
            "complete. Each task becomes a worker agent prompt. Tasks in the "
            "same execution group run in parallel; groups run sequentially."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The original user request being planned",
                },
                "tasks": {
                    "type": "array",
                    "description": "List of task specifications",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "Unique short identifier (e.g. 't1')",
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed instruction for the worker agent",
                            },
                            "tool_groups": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Tool groups the worker needs preloaded "
                                    "(e.g. 'rhino_geometry', 'gh_canvas')"
                                ),
                            },
                            "workspace_assets": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Rhino layers/object names this task will modify. "
                                    "CRITICAL: No two parallel tasks may share assets."
                                ),
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "task_ids that must complete before this",
                            },
                            "success_criteria": {
                                "type": "string",
                                "description": "How to verify the task succeeded",
                            },
                            "estimated_turns": {
                                "type": "integer",
                                "description": "Expected agent turns (default 15)",
                            },
                            "retry_on_failure": {
                                "type": "boolean",
                                "description": "Auto-retry once on failure (default true)",
                            },
                            "agent_type": {
                                "type": "string",
                                "enum": ["worker", "specialist", "scripter", "explorer"],
                                "description": (
                                    "Agent persona: 'worker' (Haiku, routine tasks), "
                                    "'specialist' (Sonnet, complex GH composition, boolean ops), "
                                    "'scripter' (Sonnet, Python 3 script generation), "
                                    "'explorer' (Haiku, read-only research). Default: 'worker'."
                                ),
                            },
                            "postconditions": {
                                "type": "array",
                                "description": (
                                    "Machine-verifiable checks to run after this task completes. "
                                    "Types: objects_on_layer (layer, min_count), objects_exist, no_gh_errors."
                                ),
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["objects_on_layer", "objects_exist", "no_gh_errors"],
                                        },
                                        "layer": {"type": "string"},
                                        "min_count": {"type": "integer"},
                                    },
                                    "required": ["type"],
                                },
                            },
                        },
                        "required": ["task_id", "description"],
                    },
                },
                "execution_groups": {
                    "type": "array",
                    "description": (
                        "Ordered list of task groups. Groups run sequentially. "
                        "Tasks within a group run in parallel. "
                        "Example: [['t1'], ['t2', 't3'], ['t4']]"
                    ),
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "rollback_notes": {
                    "type": "string",
                    "description": "What to do if tasks fail",
                },
            },
            "required": ["goal", "tasks", "execution_groups"],
        },
    },
}

PLANNER_LOCAL_CATALOG = {
    "submit_plan": SUBMIT_PLAN_SCHEMA,
}


# =============================================================================
# Planner read-only tool constraints
# =============================================================================

PLANNER_TIER_0 = {
    "rhino_ping",
    "rhino_objects",
    "rhino_geometry",
    "gh_snapshot",
    "gh_errors",
    "knowledge_query",
    "gh_knowledge_query",
    "request_tools",
    "search_tools",
}

PLANNER_ALLOWED_GROUPS = {
    "rhino_measurement",
    "rhino_selection",
    "layers",
    "viewport",
    "gh_exploration",
    "gh_knowledge",
}


# =============================================================================
# Planner class
# =============================================================================

class Planner:
    """Orchestrator that plans and dispatches worker agents.

    Lifecycle:
        plan(request) -> Plan
        execute(plan) -> PlanResult
        run(request) -> PlanResult  (plan + execute combined)
    """

    def __init__(
        self,
        config: Optional[PlannerConfig] = None,
        catalog: Optional[Dict[str, dict]] = None,
        tool_executor: Optional[Any] = None,
    ):
        self.config = config or PlannerConfig()
        self._plan: Optional[Plan] = None
        self._planning_cost: float = 0.0
        self._events = EventDispatcher()
        self._catalog = catalog or {}
        self._tool_executor = tool_executor

    def subscribe(self, callback: Callable[[AgentEvent], None]) -> Callable[[], None]:
        """Subscribe to planner events."""
        return self._events.subscribe(callback)

    # =========================================================================
    # Planning phase
    # =========================================================================

    async def plan(self, request: str) -> Plan:
        """Inspect the project and decompose request into an execution plan.

        The planning agent (Sonnet) uses read-only tools to understand
        the scene, then calls submit_plan with a structured plan.

        Args:
            request: User's natural-language request.

        Returns:
            Validated Plan ready for execution.

        Raises:
            RuntimeError: If the planner fails to produce a valid plan.
        """
        self._plan = None

        agent = self._build_planning_agent()

        # Register the submit_plan local tool
        agent.register_local_tools({
            "submit_plan": self._make_submit_handler(),
        })

        t0 = time.time()
        await agent.prompt(request)
        await agent.wait_for_idle()
        planning_time = time.time() - t0

        if self._plan is None:
            self._plan = self._try_extract_plan_from_messages(agent.messages)

        if self._plan is None:
            msg_summary = []
            for msg in agent.messages:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, str):
                    msg_summary.append(f"  [{role}] {content[:200]}")
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            msg_summary.append(
                                f"  [{role}] {block.get('type', '?')}: "
                                f"{str(block.get('text', block.get('name', '')))[:200]}"
                            )
            detail = "\n".join(msg_summary[-20:])
            raise RuntimeError(
                f"Planner did not submit a plan after {planning_time:.1f}s "
                f"({len(agent.messages)} messages). Activity:\n{detail}"
            )

        errors = self._plan.validate()
        if errors:
            raise RuntimeError(
                "Plan validation failed:\n" +
                "\n".join(f"  - {e}" for e in errors)
            )

        self._plan.total_estimated_cost = self._estimate_cost(self._plan)
        self._planning_cost = agent.cost

        self._events.emit(AgentEvent(
            type=PLAN_CREATED,
            data={
                "goal": self._plan.goal,
                "task_count": len(self._plan.tasks),
                "group_count": len(self._plan.execution_groups),
                "estimated_cost": self._plan.total_estimated_cost,
                "planning_time_s": round(planning_time, 2),
                "planning_cost_usd": round(self._planning_cost, 6),
            },
        ))

        logger.info(
            f"Plan created: {len(self._plan.tasks)} tasks, "
            f"{len(self._plan.execution_groups)} groups, "
            f"est. ${self._plan.total_estimated_cost:.4f}"
        )
        return self._plan

    # =========================================================================
    # Execution phase
    # =========================================================================

    async def execute(self, plan: Plan, on_agent_created=None) -> PlanResult:
        """Dispatch plan tasks to worker agents.

        Groups execute sequentially; tasks within a group run in parallel.

        Args:
            plan: Validated plan from plan().
            on_agent_created: Callback(tid, agent) for registering live worker agents.

        Returns:
            PlanResult with per-task results and aggregated metrics.
        """
        # Lazy import to avoid circular dependency
        from .spawn import run_task, run_swarm

        self._events.emit(AgentEvent(
            type=PLAN_EXECUTING,
            data={
                "goal": plan.goal,
                "task_count": len(plan.tasks),
                "group_count": len(plan.execution_groups),
            },
        ))

        all_results = []
        prior_group_results: List = []  # Result carriage between groups
        t0 = time.time()

        for gi, group in enumerate(plan.execution_groups):
            logger.info(
                f"Executing group {gi + 1}/{len(plan.execution_groups)}: {group}"
            )

            group_tasks = [plan.get_task(tid) for tid in group]
            group_tasks = [t for t in group_tasks if t is not None]

            if not group_tasks:
                logger.warning(f"Group {gi} has no valid tasks, skipping")
                continue

            results = await self._execute_group(
                group_tasks,
                prior_results=prior_group_results,
                on_agent_created=on_agent_created,
            )
            all_results.extend(results)

            # Retry failed tasks (once)
            if self.config.auto_retry:
                retries = []
                for result in results:
                    if result.status != "success":
                        task = plan.get_task(result.task_id)
                        if task and task.retry_on_failure:
                            logger.info(f"Retrying failed task {result.task_id}")
                            retries.append(task)

                if retries:
                    retry_results = await self._execute_group(
                        retries,
                        prior_results=prior_group_results,
                        on_agent_created=on_agent_created,
                    )
                    retry_map = {r.task_id: r for r in retry_results}
                    all_results = [
                        retry_map.get(r.task_id, r) if r.status != "success" else r
                        for r in all_results
                    ]
                    # Update results for checkpoint/carriage with final post-retry outcomes
                    results = [
                        retry_map.get(r.task_id, r) if r.status != "success" else r
                        for r in results
                    ]

            # Checkpoint: verify postconditions (Phase 2 — wired here, impl below)
            checkpoint = await self._run_checkpoint(gi, results, group_tasks)
            if not checkpoint.passed:
                logger.warning(f"Checkpoint failed for group {gi}: {checkpoint.warnings}")
                for r in results:
                    r.phase_context["checkpoint_warnings"] = checkpoint.warnings

            # Accumulate prior results AFTER retry + checkpoint (final outcomes only)
            prior_group_results.extend(results)

        wall_time = time.time() - t0
        total_cost = sum(
            r.metrics.get("cost_usd", 0)
            for r in all_results
            if hasattr(r, "metrics") and isinstance(r.metrics, dict)
        )

        statuses = [getattr(r, "status", "error") for r in all_results]
        if not statuses:
            status = "failed"
        elif all(s == "success" for s in statuses):
            status = "success"
        elif any(s == "success" for s in statuses):
            status = "partial"
        else:
            status = "failed"

        succeeded = sum(1 for s in statuses if s == "success")
        summary = (
            f"{succeeded}/{len(all_results)} tasks succeeded. "
            f"Total cost: ${total_cost:.4f}. "
            f"Wall time: {wall_time:.1f}s."
        )

        plan_result = PlanResult(
            goal=plan.goal,
            plan=plan,
            task_results=all_results,
            status=status,
            total_cost_usd=round(total_cost, 6),
            total_wall_time_s=round(wall_time, 2),
            summary=summary,
        )

        self._events.emit(AgentEvent(
            type=PLAN_COMPLETE,
            data={
                "goal": plan.goal,
                "status": status,
                "succeeded": succeeded,
                "total": len(all_results),
                "cost_usd": round(total_cost, 6),
                "wall_time_s": round(wall_time, 2),
            },
        ))

        logger.info(f"Plan complete: {summary}")
        return plan_result

    # =========================================================================
    # Combined lifecycle
    # =========================================================================

    async def run(
        self,
        request: str,
        auto_approve: bool = True,
        on_agent_created=None,
    ) -> PlanResult:
        """Full lifecycle: plan -> execute -> report.

        Args:
            request: Natural-language user request.
            auto_approve: Always True for now. Plan approval workflow is
                not yet implemented — plans execute immediately after creation.
            on_agent_created: Callback(tid, agent) for registering live worker agents.
        """
        plan = await self.plan(request)

        result = await self.execute(plan, on_agent_created=on_agent_created)
        result.planning_cost_usd = round(self._planning_cost, 6)
        result.total_cost_usd = round(
            result.total_cost_usd + self._planning_cost, 6
        )
        return result

    # =========================================================================
    # Internal: build the planning agent
    # =========================================================================

    def _build_planning_agent(self):
        """Create a RookAgent configured for read-only planning."""
        from .base_agent import RookAgent
        from .tool_registry import ToolRegistry

        registry = ToolRegistry(
            catalog=self._catalog,
            max_active=40,
            tier0=PLANNER_TIER_0,
            allowed_groups=PLANNER_ALLOWED_GROUPS,
        )
        registry.register_local_catalog(PLANNER_LOCAL_CATALOG)

        config = AgentConfig(
            model=self.config.planner_model,
            api_base=api_base_for_model(self.config.planner_model, self.config.api_base),
            max_turns=self.config.max_planning_turns,
            max_input_tokens_per_task=self.config.max_planning_tokens,
            temperature=self.config.planner_temperature,
            knowledge_injection=self.config.knowledge_injection,
            observation_recording=False,
            tool_surface_adaptation=False,
            guardian_enabled=False,
            system_prompt=self._build_planner_prompt(registry),
        )

        return RookAgent(
            config=config,
            tool_registry=registry,
            tool_executor=self._tool_executor,
        )

    def _build_planner_prompt(self, registry) -> str:
        """Generate the planner system prompt with dynamic tool summary."""
        prompt_path = (
            Path(__file__).parent / "prompts" / "PLANNER.md"
        )
        if prompt_path.exists():
            base_prompt = prompt_path.read_text(encoding="utf-8")
        else:
            base_prompt = self._default_planner_prompt()

        tool_summary = self._build_tool_summary(registry)
        return f"{base_prompt}\n\n## Available Tools\n\n{tool_summary}"

    @staticmethod
    def _build_tool_summary(registry) -> str:
        """Generate a tool list from the registry's active schemas."""
        schemas = registry.get_active_schemas()
        lines = []
        for schema in schemas:
            func = schema.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            first_sentence = desc.split(". ")[0].split(".\n")[0]
            if first_sentence and not first_sentence.endswith("."):
                first_sentence += "."
            if name:
                lines.append(f"- `{name}` -- {first_sentence}")
        lines.sort()
        header = (
            "Read-only tools for inspecting the scene. "
            "Load additional groups via `request_tools` and `search_tools`. "
            "Write-tool groups are blocked — those are for workers only.\n"
        )
        return header + "\n".join(lines) if lines else header

    @staticmethod
    def _default_planner_prompt() -> str:
        """Fallback planner prompt when PLANNER.md doesn't exist."""
        return """\
You are a planning agent for Rook, a Rhino 3D and Grasshopper assistant.

Your job is to decompose a user's design request into concrete, executable tasks
that worker agents will carry out. You have read-only access to inspect the
Rhino scene and Grasshopper canvas.

## Rules

1. NEVER modify geometry, layers, or GH components yourself
2. Use inspection tools to understand the current scene state
3. Decompose into the minimum number of tasks needed
4. Each task should be achievable in ~15 agent turns
5. Assign workspace_assets (layer names) to prevent parallel conflicts
6. Call submit_plan exactly once when your plan is ready

## Tool Groups for Workers

Workers can preload these tool groups:
- rhino_geometry: create, boolean, extrude, loft, sweep
- rhino_transform: transform, copy, delete
- rhino_curves: curve ops, offset, project, pull
- rhino_surfaces: brep ops, intersect, split, trim
- rhino_mesh: mesh creation and editing
- gh_canvas: component, connect, set_value, errors
- materials: material ops, UV mapping
- layers: layer management
- game_export: tagging, validation, export

## Workspace Assets

Use Rhino layers for workspace isolation:
- "Layer::Walls" — only one task modifies walls
- "Layer::Roof" — separate task for roof geometry
Tasks in the same execution group MUST NOT share assets.

## Output

Call submit_plan with your structured plan. Do NOT output the plan as text."""

    # =========================================================================
    # Internal: submit_plan handler
    # =========================================================================

    def _make_submit_handler(self) -> Callable:
        """Create the submit_plan local tool handler."""
        def submit_plan(**kwargs) -> dict:
            try:
                plan = self._parse_plan(kwargs)
                errors = plan.validate()
                if errors:
                    return {
                        "success": False,
                        "error": (
                            "Plan validation failed:\n" +
                            "\n".join(f"  - {e}" for e in errors)
                        ),
                        "hint": "Fix the issues and call submit_plan again.",
                    }
                self._plan = plan
                return {
                    "success": True,
                    "message": (
                        f"Plan accepted: {len(plan.tasks)} tasks in "
                        f"{len(plan.execution_groups)} execution groups."
                    ),
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to parse plan: {e}",
                    "hint": "Check the plan format and try again.",
                }
        return submit_plan

    def _parse_plan(self, data: dict) -> Plan:
        """Parse a Plan from submit_plan tool call parameters."""
        raw_tasks = data.get("tasks", [])
        if isinstance(raw_tasks, str):
            raw_tasks = json.loads(raw_tasks)
        raw_groups = data.get("execution_groups", [])
        if isinstance(raw_groups, str):
            raw_groups = json.loads(raw_groups)

        tasks = []
        for td in raw_tasks:
            if isinstance(td, str):
                td = json.loads(td)

            raw_turns = td.get("estimated_turns", 15)
            try:
                turns = int(raw_turns)
            except (ValueError, TypeError):
                turns = 15

            raw_retry = td.get("retry_on_failure", True)
            if isinstance(raw_retry, str):
                retry = raw_retry.lower() in ("true", "1", "yes")
            elif isinstance(raw_retry, bool):
                retry = raw_retry
            else:
                retry = bool(raw_retry)

            agent_type = td.get("agent_type", "worker")
            try:
                from .personas import available_personas, _INFRASTRUCTURE_PERSONAS
                valid_types = set(available_personas()) - _INFRASTRUCTURE_PERSONAS
            except Exception:
                valid_types = {"worker", "specialist"}
            if agent_type not in valid_types:
                agent_type = "worker"

            # Parse postconditions (gracefully handle non-list values)
            raw_postconditions = td.get("postconditions", [])
            if not isinstance(raw_postconditions, list):
                raw_postconditions = []
            postconditions = [
                pc for pc in raw_postconditions
                if isinstance(pc, dict) and "type" in pc
            ]

            tasks.append(TaskSpec(
                task_id=str(td["task_id"]),
                description=str(td["description"]),
                tool_groups=td.get("tool_groups", []),
                workspace_assets=td.get("workspace_assets", []),
                depends_on=td.get("depends_on", []),
                success_criteria=td.get("success_criteria", ""),
                estimated_turns=turns,
                retry_on_failure=retry,
                agent_type=agent_type,
                postconditions=postconditions,
            ))

        return Plan(
            goal=data.get("goal", ""),
            tasks=tasks,
            execution_groups=raw_groups,
            rollback_notes=data.get("rollback_notes", ""),
        )

    def _try_extract_plan_from_messages(self, messages: List[dict]) -> Optional[Plan]:
        """Fallback: extract plan from agent's text if submit_plan wasn't called."""
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            search_from = 0
            while search_from < len(content):
                json_idx = content.find("```json", search_from)
                plain_idx = content.find("```", search_from)
                if json_idx >= 0 and json_idx == plain_idx:
                    block_start = json_idx + len("```json")
                elif plain_idx >= 0:
                    block_start = plain_idx + len("```")
                else:
                    break

                block_end = content.find("```", block_start)
                if block_end <= block_start:
                    break

                try:
                    data = json.loads(content[block_start:block_end].strip())
                    if isinstance(data, dict) and "tasks" in data:
                        return self._parse_plan(data)
                except (json.JSONDecodeError, KeyError):
                    pass

                search_from = block_end + 3

            try:
                data = json.loads(content.strip())
                if isinstance(data, dict) and "tasks" in data:
                    return self._parse_plan(data)
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    # =========================================================================
    # Internal: task execution
    # =========================================================================

    async def _execute_group(
        self,
        tasks: List[TaskSpec],
        prior_results: Optional[List] = None,
        on_agent_created=None,
    ) -> List[Any]:
        """Execute a group of tasks (parallel if multiple).

        Args:
            tasks: Tasks to execute in this group.
            prior_results: SpawnResults from earlier groups, injected as context.
            on_agent_created: Callback(tid, agent) for registering live agents.
        """
        from .spawn import run_task, run_swarm

        # Build context prefix from prior group results
        context_prefix = self._format_prior_results(prior_results) if prior_results else ""

        if len(tasks) == 1:
            task = tasks[0]
            _resolved_model = self._resolve_model(task.agent_type)
            _desc = (context_prefix + "\n\n" + task.description) if context_prefix else task.description
            result = await run_task(
                _desc,
                model=_resolved_model,
                api_base=api_base_for_model(_resolved_model, self.config.api_base),
                agent_type=task.agent_type,
                max_turns=self.config.max_worker_turns,
                max_input_tokens=self.config.max_worker_tokens,
                preload_groups=task.tool_groups or None,
                workspace_assets=task.workspace_assets or None,
                task_id=task.task_id,
                guardian_enabled=self.config.guardian_enabled,
                catalog=self._catalog,
                tool_executor=self._tool_executor,
                on_agent_created=on_agent_created,
            )
            return [result]
        else:
            task_dicts = []
            for task in tasks:
                _desc = (context_prefix + "\n\n" + task.description) if context_prefix else task.description
                task_dicts.append({
                    "task": _desc,
                    "task_id": task.task_id,
                    "preload_groups": task.tool_groups or None,
                    "workspace_assets": task.workspace_assets or None,
                    "model": self._resolve_model(task.agent_type),
                    "agent_type": task.agent_type,
                })

            swarm_result = await run_swarm(
                task_dicts,
                max_concurrent=self.config.max_concurrent_workers,
                model=self.config.worker_model,
                api_base=api_base_for_model(self.config.worker_model, self.config.api_base),
                max_turns=self.config.max_worker_turns,
                max_input_tokens=self.config.max_worker_tokens,
                guardian_enabled=self.config.guardian_enabled,
                catalog=self._catalog,
                tool_executor=self._tool_executor,
                on_agent_created=on_agent_created,
            )
            return swarm_result.results

    def _resolve_model(self, agent_type: str) -> str:
        """Resolve model string from agent type via persona → profile lookup.

        Fast path: 'worker' returns worker_model directly.
        Otherwise: persona display.json → model_role → active ModelSet → model string.
        Falls back to worker_model on any error.
        """
        if agent_type == "worker":
            return self.config.worker_model
        try:
            from .personas import get_model_role
            from .model_profiles import get_models
            role = get_model_role(agent_type)
            profile = getattr(self.config, "model_profile", None)
            models = get_models(profile)
            return getattr(models, role, self.config.worker_model)
        except Exception:
            return self.config.worker_model

    async def _run_checkpoint(
        self,
        group_index: int,
        results: List,
        tasks: List[TaskSpec],
    ) -> CheckpointResult:
        """Verify postconditions after an execution group completes.

        Uses HTTP calls only (no LLM cost). Checks:
        1. created_ids exist (Rhino GUIDs via GET /geometry)
        2. Task-level postconditions (objects_on_layer, objects_exist, no_gh_errors)
        3. Auto-added no_gh_errors if any GH tools were used
        """
        checks: List[Dict[str, Any]] = []
        warnings: List[str] = []

        for result, task in zip(results, tasks):
            task_id = getattr(result, "task_id", "?")
            created_ids = getattr(result, "created_ids", [])
            tools_called = getattr(result, "tools_called", [])

            # 1. Verify created Rhino objects still exist (up to 10)
            if created_ids:
                for oid in created_ids[:10]:
                    check = await self._evaluate_postcondition(
                        {"type": "objects_exist"}, [oid],
                    )
                    checks.append(check)
                    if not check.get("passed", True):
                        warnings.append(f"{task_id}: created object {oid} not found")

            # 2. Evaluate explicit postconditions
            for pc in task.postconditions:
                check = await self._evaluate_postcondition(pc, created_ids)
                checks.append(check)
                if not check.get("passed", True):
                    warnings.append(f"{task_id}: postcondition {pc.get('type')} failed")

            # 3. Auto-add GH error check if any GH tools were used
            gh_used = any(
                (t.get("tool", "") or "").startswith("gh_")
                for t in tools_called
            )
            if gh_used:
                # Only add if not already in postconditions
                has_gh_check = any(pc.get("type") == "no_gh_errors" for pc in task.postconditions)
                if not has_gh_check:
                    check = await self._evaluate_postcondition(
                        {"type": "no_gh_errors"}, [],
                    )
                    checks.append(check)
                    if not check.get("passed", True):
                        warnings.append(f"{task_id}: GH errors detected after execution")

        passed = len(warnings) == 0
        event_type = CHECKPOINT_PASS if passed else CHECKPOINT_FAIL
        self._events.emit(AgentEvent(event_type, {
            "group_index": group_index,
            "passed": passed,
            "check_count": len(checks),
            "warnings": warnings,
        }))

        return CheckpointResult(
            group_index=group_index,
            passed=passed,
            checks=checks,
            warnings=warnings,
        )

    async def _evaluate_postcondition(
        self,
        pc: Dict[str, Any],
        created_ids: List[str],
    ) -> Dict[str, Any]:
        """Evaluate a single postcondition via HTTP bridge calls.

        Supported types:
        - objects_on_layer: GET /objects?layer=X → check totalCount >= min_count
        - objects_exist: GET /geometry?id=X for each created_id → check all found
        - no_gh_errors: GET /gh/errors → check ErrorCount = 0

        Returns dict with {type, passed, detail}.

        Real endpoint contracts:
        - /objects → data: {totalCount, count, offset, limit, objects: [...]}
        - /gh/errors → data: {TotalComponents, ErrorCount, WarningCount, Errors: [...], Warnings: [...]}

        Bridge or endpoint failures FAIL the check (not pass). Verification
        exists to catch problems — silently passing on errors defeats the purpose.
        """
        from ..bridge import call_rhino

        pc_type = pc.get("type", "")
        try:
            if pc_type == "objects_on_layer":
                layer = pc.get("layer", "")
                min_count = pc.get("min_count", 1)
                resp = await call_rhino("/objects", "GET", {"layer": layer})
                if isinstance(resp, dict) and resp.get("success"):
                    # /objects returns data.totalCount (int) + data.objects (list)
                    data = resp.get("data", {})
                    if isinstance(data, dict):
                        count = data.get("totalCount", 0)
                    else:
                        count = 0
                    return {
                        "type": pc_type,
                        "passed": count >= min_count,
                        "detail": f"Found {count} objects on '{layer}', need {min_count}",
                    }
                return {"type": pc_type, "passed": False, "detail": f"Bridge call failed: {resp}"}

            elif pc_type == "objects_exist":
                if not created_ids:
                    return {"type": pc_type, "passed": True, "detail": "No IDs to verify"}
                missing = []
                for oid in created_ids[:10]:
                    resp = await call_rhino("/geometry", "GET", {"id": oid})
                    if isinstance(resp, dict):
                        if not resp.get("success"):
                            missing.append(oid)
                    else:
                        missing.append(oid)
                return {
                    "type": pc_type,
                    "passed": len(missing) == 0,
                    "detail": f"Missing: {missing}" if missing else "All objects verified",
                }

            elif pc_type == "no_gh_errors":
                resp = await call_rhino("/gh/errors", "GET", {})
                if isinstance(resp, dict) and resp.get("success"):
                    # /gh/errors returns data: {ErrorCount, WarningCount, Errors, Warnings, ...}
                    data = resp.get("data", {})
                    if isinstance(data, dict):
                        error_count = data.get("ErrorCount", 0)
                    else:
                        error_count = 0
                    return {
                        "type": pc_type,
                        "passed": error_count == 0,
                        "detail": f"{error_count} GH errors",
                    }
                return {"type": pc_type, "passed": False, "detail": "GH errors endpoint unavailable or failed"}

            else:
                # Unknown postcondition type — pass gracefully
                return {"type": pc_type, "passed": True, "detail": f"Unknown type '{pc_type}', skipped"}

        except Exception as e:
            logger.warning(f"Postcondition check '{pc_type}' failed due to error: {e}")
            return {"type": pc_type, "passed": False, "detail": f"Error during check: {e}"}

    @staticmethod
    def _format_prior_results(prior_results: List) -> str:
        """Format prior group results as context for next-group workers.

        Returns a markdown block summarizing what earlier tasks accomplished,
        including created object GUIDs and any checkpoint warnings.
        Cost: ~200-400 tokens per 5 prior results — negligible.
        """
        if not prior_results:
            return ""
        lines = ["## Prior Task Results\n"]
        for r in prior_results:
            status = getattr(r, "status", "?")
            summary = (getattr(r, "summary", "") or "")[:300]
            task_id = getattr(r, "task_id", "?")
            created = getattr(r, "created_ids", [])[:20]
            ctx = getattr(r, "phase_context", {}) or {}
            warnings = ctx.get("checkpoint_warnings", [])

            lines.append(f"- **{task_id}** [{status}]: {summary}")
            if created:
                lines.append(f"  - Created IDs: {', '.join(created)}")
            if warnings:
                lines.append(f"  - Checkpoint warnings: {'; '.join(warnings)}")
        return "\n".join(lines)

    # Role-based pricing: (input_$/M, output_$/M)
    _MODEL_PRICING = {
        "worker": (0.80, 4.00),
        "specialist": (3.00, 15.00),
        "planner": (3.00, 15.00),
        "guardian": (0.80, 4.00),
        "dspy": (3.00, 15.00),
    }

    def _estimate_cost(self, plan: Plan) -> float:
        """Rough cost estimate based on task count and estimated turns.

        Uses role-based pricing via persona model_role lookup.
        ~1K input tokens/turn, ~200 output tokens/turn.
        """
        total = 0.0
        for task in plan.tasks:
            turns = task.estimated_turns or 15
            try:
                from .personas import get_model_role
                role = get_model_role(task.agent_type)
            except Exception:
                role = "worker"
            input_rate, output_rate = self._MODEL_PRICING.get(role, (0.80, 4.00))
            input_cost = turns * 1000 * (input_rate / 1_000_000)
            output_cost = turns * 200 * (output_rate / 1_000_000)
            total += input_cost + output_cost
        return round(total, 6)
