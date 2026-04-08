"""
Sub-Agent Spawning
==================

Spawn lightweight RookAgent instances for task execution.
Provides single-task (run_task) and parallel multi-task (run_swarm) runners,
plus a planner entry point (run_plan).

Ported from Engram's spawn.py, adapted for Rook's HTTP bridge.

Usage:
    from rook.agent.spawn import run_task, run_swarm, run_plan

    # Single task
    result = await run_task("Create a box at the origin")

    # Parallel tasks
    swarm = await run_swarm([
        {"task": "Create walls on Layer::Walls"},
        {"task": "Create roof on Layer::Roof"},
    ])

    # Planner-driven
    plan_result = await run_plan("Build a parametric staircase")
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .planner import PlanResult

from .conductor import Conductor, ConductorConfig
from .config import AgentConfig, PlannerConfig
from .events import AgentEvent, TOOL_EXEC_END, ERROR
from .guardian import Guardian, GuardianConfig
from .model_profiles import api_base_for_model
from .substrate_analytics import summarize_substrate_observations
from .tool_groups import READONLY_TIER_0, READONLY_ALLOWED_GROUPS

logger = logging.getLogger(__name__)


# =============================================================================
# Result dataclasses
# =============================================================================

@dataclass
class SpawnResult:
    """Structured output from a spawned agent task."""
    task_id: str
    status: str                    # "success" | "error" | "budget_exceeded"
    task: str
    summary: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    tools_called: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    guardian_report: Dict[str, Any] = field(default_factory=dict)
    substrate_summary: Dict[str, Any] = field(default_factory=dict)
    failure_reason: Optional[str] = None
    broken_tools: List[str] = field(default_factory=list)
    created_ids: List[str] = field(default_factory=list)       # Rhino object GUIDs created
    phase_context: Dict[str, Any] = field(default_factory=dict) # Opaque caller context

    def to_dict(self) -> dict:
        d = asdict(self)
        d["result_type"] = "spawn"
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class SwarmResult:
    """Structured output from a parallel swarm run."""
    results: List[SpawnResult] = field(default_factory=list)
    conductor_report: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "results": [r.to_dict() for r in self.results],
            "conductor_report": self.conductor_report,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# =============================================================================
# Failure classification
# =============================================================================

_TOOL_BROKEN_PATTERNS = [
    "Connection refused",
    "Bridge call timed out",
    "connection error",
    "Incomplete or empty response",
    "Traceback (most recent call last)",
    "unknown type",
    "Internal error",
    "ConnectError",
    "TimeoutException",
]


def classify_tool_failure(error_msg: str) -> str:
    """Classify a tool failure as 'tool_broken' or 'model_error'."""
    lower = error_msg.lower()
    for pattern in _TOOL_BROKEN_PATTERNS:
        if pattern.lower() in lower:
            return "tool_broken"
    return "model_error"


# =============================================================================
# Dynamic system prompt
# =============================================================================

def _build_worker_prompt(
    registry,
    preloaded_groups: List[str],
    agent_type: str = "worker",
) -> str:
    """Build a worker system prompt with dynamic tool awareness.

    Loads persona personality.md + role.md as the base (falls back to WORKER.md),
    then appends a dynamic section listing the currently active tools.
    """
    from pathlib import Path

    # Try persona-based prompt first
    personality = role = ""
    try:
        from .personas import load_persona
        p = load_persona(agent_type)
        personality = p.get("personality", "")
        role = p.get("role", "")
    except Exception:
        pass

    if role:
        base = "\n\n".join(filter(None, [personality, role]))
    else:
        # Fallback to WORKER.md
        prompt_path = Path(__file__).parent / "prompts" / "WORKER.md"
        if prompt_path.exists():
            try:
                base = prompt_path.read_text(encoding="utf-8")
            except Exception:
                base = ""
        else:
            base = ""

    # Build dynamic tool summary from registry's active schemas
    schemas = registry.get_active_schemas()
    tool_lines = []
    for schema in schemas:
        func = schema.get("function", {})
        name = func.get("name", "")
        desc = func.get("description", "")
        if not name:
            continue
        first_sentence = desc.split(". ")[0].split(".\n")[0]
        if first_sentence and not first_sentence.endswith("."):
            first_sentence += "."
        tool_lines.append(f"- `{name}` -- {first_sentence}")
    tool_lines.sort()

    groups_str = ", ".join(f"`{g}`" for g in sorted(preloaded_groups))
    dynamic = (
        f"\n\n## Active Tools (preloaded: {groups_str})\n\n"
        f"These tools are already loaded — use them directly without calling `request_tools`.\n"
        f"Use `request_tools` or `search_tools` only if you need tools NOT listed here.\n\n"
    )
    dynamic += "\n".join(tool_lines) if tool_lines else "(no tools loaded)"

    return base + dynamic


# =============================================================================
# Core single-task runner
# =============================================================================

async def run_task(
    task: str,
    *,
    model: str = "",
    api_base: Optional[str] = None,
    agent_type: str = "worker",
    max_turns: int = 30,
    max_input_tokens: int = 500_000,
    preload_groups: Optional[List[str]] = None,
    workspace_assets: Optional[List[str]] = None,
    task_id: Optional[str] = None,
    on_agent_created: Optional[Any] = None,
    guardian_enabled: bool = True,
    catalog: Optional[Dict[str, dict]] = None,
    tool_executor: Optional[Any] = None,
) -> SpawnResult:
    """Run a single agent task to completion.

    Args:
        task: Natural-language instruction for the agent.
        model: LiteLLM model identifier (defaults to Haiku).
        max_turns: Max agent turns before stopping.
        max_input_tokens: Token budget for the task.
        preload_groups: Tool groups to activate before prompting.
        workspace_assets: Rhino layers/objects this agent may modify.
        task_id: Optional ID; auto-generated if not provided.
        on_agent_created: Optional callback(task_id, agent) for Conductor.
        guardian_enabled: Attach Guardian trajectory monitor.
        catalog: Pre-built tool catalog. If None, creates empty registry.
        tool_executor: Async callable(name, params) -> dict. If None, uses
            the agent's default HTTP bridge. Used by MCP server to route
            tools through call_tool() instead of the bridge.

    Returns:
        SpawnResult with status, metrics, and tool call log.
    """
    from .base_agent import RookAgent
    from .tool_registry import ToolRegistry

    # Resolve model and/or api_base from active profile.
    # Both paths matter: model defaults to profile worker when empty;
    # api_base must always be resolved so explicit model overrides
    # (e.g., model="openai/lmstudio-model") can reach local servers.
    if not model or not api_base:
        try:
            from .model_profiles import get_models
            _ms = get_models()
            if not model:
                model = _ms.worker
            if not api_base and _ms.api_base:
                api_base = _ms.api_base
        except Exception:
            if not model:
                model = "anthropic/claude-haiku-4-5-20251001"

    # Auto-build ToolDispatcher when no tool_executor provided.
    # This gives agents direct bridge access, bypassing MCP overhead.
    if tool_executor is None:
        from .tool_dispatcher import ToolDispatcher, build_local_tools
        dispatcher = ToolDispatcher()
        dispatcher.register_locals(build_local_tools())
        tool_executor = dispatcher.dispatch
        logger.info("run_task: auto-built ToolDispatcher (direct bridge)")

    tid = task_id or uuid.uuid4().hex[:8]
    tools_log: List[dict] = []
    error_log: List[str] = []
    all_created_ids: List[str] = []

    # Event collector
    def _collect(event: AgentEvent) -> None:
        if event.type == TOOL_EXEC_END:
            tools_log.append({
                "tool": event.data.get("tool", ""),
                "success": event.data.get("success", False),
                "error": event.data.get("error", ""),
                "route_taken": event.data.get("route_taken", ""),
                "operation": event.data.get("operation", ""),
                "verified": event.data.get("verified"),
            })
            # Accumulate Rhino object GUIDs created during this task
            all_created_ids.extend(event.data.get("created_ids", []))
        elif event.type == ERROR:
            error_log.append(event.data.get("message", "unknown error"))

    # Load cached catalog when none provided (autonomous spawn path)
    if catalog is None:
        from .tool_registry import load_catalog_from_cache
        catalog = load_catalog_from_cache()
        if catalog:
            logger.info(f"Loaded {len(catalog)} tools from catalog cache")

    # Check tool_access from persona display config
    _tool_access = "full"
    try:
        from .personas import load_display_config
        _display = load_display_config(agent_type)
        _tool_access = _display.get("tool_access", "full")
    except Exception as e:
        logger.warning("Failed to load display config for %r, defaulting to full access: %s", agent_type, e)

    if _tool_access == "readonly":
        # Readonly agents get restricted tier0 + allowed_groups
        registry = ToolRegistry(
            catalog=catalog or {},
            tier0=READONLY_TIER_0,
            allowed_groups=READONLY_ALLOWED_GROUPS,
        )
    else:
        # Full-access agents — agent_mode excludes gh_execute_intent from Tier 0
        registry = ToolRegistry(catalog=catalog or {}, agent_mode=True)

    config = AgentConfig(
        model=model,
        api_base=api_base_for_model(model, api_base),
        agent_type=agent_type,
        max_turns=max_turns,
        max_input_tokens_per_task=max_input_tokens,
        observation_recording=True,
        guardian_enabled=guardian_enabled,
    )
    agent = RookAgent(
        config=config,
        tool_registry=registry,
        tool_executor=tool_executor,
    )
    agent.subscribe(_collect)

    # Register ask_human escalation tool
    async def _ask_human_tool(question: str, context: str = "") -> dict:
        """Ask the human operator a question when stuck."""
        answer = await agent.ask_human(question, context)
        return {"success": True, "data": {"answer": answer}}

    agent.register_local_tools({"ask_human": _ask_human_tool})
    registry.register_local_catalog({
        "ask_human": {
            "type": "function",
            "function": {
                "name": "ask_human",
                "description": (
                    "Ask the human operator a question when you genuinely cannot proceed. "
                    "Use sparingly — only when you've exhausted other approaches and need "
                    "clarification, a decision, or information you can't find."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "The specific question you need answered",
                        },
                        "context": {
                            "type": "string",
                            "description": "What you tried and why you're stuck",
                        },
                    },
                    "required": ["question"],
                },
            },
        },
    })

    # Conductor callback
    if on_agent_created:
        try:
            on_agent_created(tid, agent)
        except Exception as e:
            logger.debug(f"on_agent_created callback error: {e}")

    # Guardian
    guardian = None
    if guardian_enabled:
        guardian = Guardian(
            agent,
            config=GuardianConfig(
                check_interval=config.guardian_check_interval,
                max_consecutive_failures=config.guardian_max_failures,
                max_identical_calls=config.guardian_max_loops,
                budget_warning_threshold=config.guardian_budget_threshold,
                max_interventions=config.guardian_max_interventions,
                enable_steering=True,
                enable_llm_analysis=config.guardian_llm_analysis,
                llm_analysis_model=config.guardian_llm_model,
                api_base=api_base_for_model(config.guardian_llm_model, api_base),
            ),
            workspace_assets=workspace_assets,
            task_description=task,
        )
        guardian.start()

    # Preload tool groups
    preload_groups = list(preload_groups or [])
    if _tool_access == "readonly":
        # Swap gh_canvas for read-only subset
        if "gh_canvas" in preload_groups:
            preload_groups.remove("gh_canvas")
        if "gh_canvas_readonly" not in preload_groups:
            preload_groups.append("gh_canvas_readonly")
    else:
        # Full-access agents always get gh_canvas
        if "gh_canvas" not in preload_groups:
            preload_groups.append("gh_canvas")
    for group in preload_groups:
        registry.request_group(group, turn=0)

    # Dynamic system prompt with preloaded-group awareness
    agent.set_system_prompt(_build_worker_prompt(registry, preload_groups, agent_type))

    # Workspace constraint prefix
    effective_task = task
    if workspace_assets:
        asset_list = ", ".join(workspace_assets)
        effective_task = (
            f"WORKSPACE CONSTRAINT: You may ONLY modify these assets: "
            f"[{asset_list}]. Do NOT create or modify other assets.\n\n"
            f"{task}"
        )

    # Run
    t0 = time.time()
    try:
        await agent.prompt(effective_task)
        await agent.wait_for_idle()
    except Exception as e:
        error_log.append(f"Agent loop exception: {e}")
    wall_time = time.time() - t0

    # Determine status
    if agent._total_input_tokens >= max_input_tokens:
        status = "budget_exceeded"
    elif error_log:
        status = "error"
    else:
        status = "success"

    # Extract summary from last assistant message
    summary = ""
    for msg in reversed(agent.messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            content = msg["content"]
            if isinstance(content, str):
                summary = content
            break

    metrics = {
        "turns": agent._turn_count,
        "input_tokens": agent._total_input_tokens,
        "output_tokens": agent._total_output_tokens,
        "total_tokens": agent._total_input_tokens + agent._total_output_tokens,
        "cost_usd": round(agent._total_cost, 6),
        "wall_time_s": round(wall_time, 2),
        "model": agent.config.model,
    }

    # Guardian report
    guardian_data = {}
    if guardian:
        try:
            guardian_data = guardian.report().to_dict()
        finally:
            guardian.stop()

    # Classify failure reasons from tool log
    broken = set()
    for entry in tools_log:
        if not entry["success"] and entry.get("error"):
            if classify_tool_failure(entry["error"]) == "tool_broken":
                broken.add(entry["tool"])

    failure_reason = None
    if status != "success":
        failure_reason = "tool_broken" if broken else "model_error"

    substrate_summary = summarize_substrate_observations(tools_log)

    return SpawnResult(
        task_id=tid,
        status=status,
        task=task,
        summary=summary,
        metrics=metrics,
        tools_called=tools_log,
        errors=error_log,
        guardian_report=guardian_data,
        substrate_summary=substrate_summary,
        failure_reason=failure_reason,
        broken_tools=sorted(broken),
        created_ids=all_created_ids,
    )


# =============================================================================
# Asset exclusivity validation
# =============================================================================

def _validate_asset_exclusivity(tasks: List[dict]) -> None:
    """Raise ValueError if two tasks share a workspace asset."""
    seen: Dict[str, int] = {}
    for i, t in enumerate(tasks):
        for asset in t.get("workspace_assets") or []:
            normalized = asset.strip().rstrip("/")
            if normalized in seen:
                raise ValueError(
                    f"Asset conflict: '{normalized}' claimed by both "
                    f"task {seen[normalized]} and task {i}. "
                    f"Parallel agents on the same layer cause conflicts."
                )
            seen[normalized] = i


# =============================================================================
# Parallel multi-task runner
# =============================================================================

async def run_swarm(
    tasks: List[dict],
    *,
    max_concurrent: int = 3,
    model: str = "",
    api_base: Optional[str] = None,
    max_turns: int = 30,
    max_input_tokens: int = 500_000,
    conductor_config: Optional[ConductorConfig] = None,
    guardian_enabled: bool = True,
    catalog: Optional[Dict[str, dict]] = None,
    tool_executor: Optional[Any] = None,
    on_agent_created: Optional[Any] = None,
) -> SwarmResult:
    """Run multiple agent tasks in parallel with safety checks.

    Args:
        tasks: List of task dicts, each with "task" (str).
               Optional: "preload_groups", "workspace_assets", "task_id".
        max_concurrent: Max simultaneous agents.
        model: LiteLLM model for all agents.
        api_base: Optional API base URL for local providers (LM Studio, vLLM).
        max_turns: Max turns per task.
        max_input_tokens: Token budget per task.
        conductor_config: Optional Conductor configuration.
        guardian_enabled: Attach Guardian to each agent.
        catalog: Pre-built tool catalog for all agents.
        tool_executor: Async callable(name, params) -> dict for MCP routing.

    Returns:
        SwarmResult with per-task results and conductor report.

    Raises:
        ValueError: If two tasks share a workspace asset.
    """
    # Resolve model and/or api_base from active profile (same logic as run_task).
    if not model or not api_base:
        try:
            from .model_profiles import get_models
            _ms = get_models()
            if not model:
                model = _ms.worker
            if not api_base and _ms.api_base:
                api_base = _ms.api_base
        except Exception:
            if not model:
                model = "anthropic/claude-haiku-4-5-20251001"

    _validate_asset_exclusivity(tasks)

    # Conductor
    conductor = Conductor(config=conductor_config)

    def _on_agent_created_internal(tid: str, agent: Any) -> None:
        conductor.register_agent(tid, agent)
        # Fan out to external callback (e.g. for plan_and_execute agent tracking)
        if on_agent_created:
            try:
                on_agent_created(tid, agent)
            except Exception as e:
                logger.debug(f"External on_agent_created error: {e}")

    await conductor.start()

    # Pre-assign task IDs
    for i, t in enumerate(tasks):
        if "task_id" not in t:
            t["task_id"] = uuid.uuid4().hex[:8]

    sem = asyncio.Semaphore(max_concurrent)

    async def _gated(task_spec: dict) -> SpawnResult:
        async with sem:
            return await run_task(
                task_spec["task"],
                model=task_spec.get("model") or model,
                api_base=api_base,
                agent_type=task_spec.get("agent_type", "worker"),
                max_turns=max_turns,
                max_input_tokens=max_input_tokens,
                preload_groups=task_spec.get("preload_groups"),
                workspace_assets=task_spec.get("workspace_assets"),
                task_id=task_spec["task_id"],
                on_agent_created=_on_agent_created_internal,
                guardian_enabled=guardian_enabled,
                catalog=catalog,
                tool_executor=tool_executor,
            )

    coros = [_gated(t) for t in tasks]
    raw_results = await asyncio.gather(*coros, return_exceptions=True)

    results: List[SpawnResult] = []
    for i, r in enumerate(raw_results):
        if isinstance(r, BaseException):
            result = SpawnResult(
                task_id=tasks[i]["task_id"],
                status="error",
                task=tasks[i].get("task", ""),
                errors=[f"{type(r).__name__}: {r}"],
            )
        else:
            result = r
        results.append(result)
        conductor.add_result(result.task_id, result)

    conductor_report = conductor.report()
    await conductor.stop()

    return SwarmResult(
        results=results,
        conductor_report=conductor_report.to_dict(),
    )


# =============================================================================
# Planner entry point
# =============================================================================

async def run_plan(
    request: str,
    *,
    config: Optional[PlannerConfig] = None,
    auto_approve: bool = False,
    catalog: Optional[Dict[str, dict]] = None,
    tool_executor: Optional[Any] = None,
) -> "PlanResult":
    """Plan and execute a user request via the Planner orchestrator.

    Args:
        request: Natural-language user request.
        config: Optional PlannerConfig.
        auto_approve: Skip approval and execute immediately.
        catalog: Pre-built tool catalog for planner and workers.
        tool_executor: Async callable(name, params) -> dict for MCP routing.

    Returns:
        PlanResult with per-task results and aggregated metrics.
    """
    from .planner import Planner

    # Load cached catalog when none provided (same fallback as run_task)
    if catalog is None:
        from .tool_registry import load_catalog_from_cache
        catalog = load_catalog_from_cache()
        if catalog:
            logger.info(f"run_plan: loaded {len(catalog)} tools from catalog cache")

    planner = Planner(
        config or PlannerConfig(),
        catalog=catalog,
        tool_executor=tool_executor,
    )
    return await planner.run(request, auto_approve=auto_approve)
