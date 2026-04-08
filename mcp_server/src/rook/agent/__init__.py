"""Rook Agent System — Multi-agent architecture for autonomous Rhino/GH workflows.

Ported from Engram (UE5 sister project). Provides:
- RookAgent: Core agent loop with 4 knowledge seams
- Planner: Decomposes complex tasks into parallel worker tasks
- Guardian: Trajectory monitor per-worker (stuck/loop/drift/budget detection)
- Conductor: Fleet coordinator across parallel workers
"""

from .config import AgentConfig, PlannerConfig, GuardianConfig, ConductorConfig
from .events import AgentEvent, EventDispatcher
from .base_agent import RookAgent
from .tool_registry import ToolRegistry, build_catalog_from_mcp_tools
from .guardian import Guardian, GuardianReport
from .conductor import Conductor, ConductorReport
from .planner import Planner, Plan, TaskSpec, PlanResult
from .spawn import run_task, run_swarm, run_plan, SpawnResult, SwarmResult

__all__ = [
    "AgentConfig",
    "PlannerConfig",
    "GuardianConfig",
    "ConductorConfig",
    "RookAgent",
    "AgentEvent",
    "EventDispatcher",
    "ToolRegistry",
    "build_catalog_from_mcp_tools",
    "Guardian",
    "GuardianReport",
    "Conductor",
    "ConductorReport",
    "Planner",
    "Plan",
    "TaskSpec",
    "PlanResult",
    "run_task",
    "run_swarm",
    "run_plan",
    "SpawnResult",
    "SwarmResult",
]
