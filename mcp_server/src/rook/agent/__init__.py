"""Rook Agent System — Multi-agent architecture for autonomous Rhino/GH workflows.

Ported from Engram (UE5 sister project). Provides:
- RookAgent: Core agent loop with 4 knowledge seams
- Planner: Decomposes complex tasks into parallel worker tasks
- Guardian: Trajectory monitor per-worker (stuck/loop/drift/budget detection)
- Conductor: Fleet coordinator across parallel workers
"""

from importlib import import_module
from typing import Any

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

_EXPORT_MODULES = {
    "AgentConfig": ".config",
    "PlannerConfig": ".config",
    "GuardianConfig": ".config",
    "ConductorConfig": ".config",
    "AgentEvent": ".events",
    "EventDispatcher": ".events",
    "RookAgent": ".base_agent",
    "ToolRegistry": ".tool_registry",
    "build_catalog_from_mcp_tools": ".tool_registry",
    "Guardian": ".guardian",
    "GuardianReport": ".guardian",
    "Conductor": ".conductor",
    "ConductorReport": ".conductor",
    "Planner": ".planner",
    "Plan": ".planner",
    "TaskSpec": ".planner",
    "PlanResult": ".planner",
    "run_task": ".spawn",
    "run_swarm": ".spawn",
    "run_plan": ".spawn",
    "SpawnResult": ".spawn",
    "SwarmResult": ".spawn",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
