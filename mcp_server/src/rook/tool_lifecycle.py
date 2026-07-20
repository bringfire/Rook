"""Exact lifecycle tombstones for legacy semantic-authority tools."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType


class ToolDisposition(str, Enum):
    RETIRED = "retired"
    SUSPENDED = "suspended"


@dataclass(frozen=True, slots=True)
class LifecycleEntry:
    name: str
    disposition: ToolDisposition
    recovery: str


_REDISCOVER = "Rediscover the current tool surface; "

CONTAINED_TOOLS = (
    LifecycleEntry(
        "gh_execute_intent",
        ToolDisposition.RETIRED,
        _REDISCOVER + "use explicit Grasshopper inspection, editing, solve, error, and output-verification tools.",
    ),
    LifecycleEntry(
        "rhino_execute_intent",
        ToolDisposition.RETIRED,
        _REDISCOVER + "use typed Rhino operations, rhino_execute, or sanctioned preflighted commands with verification.",
    ),
    LifecycleEntry(
        "plan_and_execute",
        ToolDisposition.SUSPENDED,
        _REDISCOVER + "plan explicitly and invoke admitted tools under caller-visible control.",
    ),
    LifecycleEntry(
        "spawn_agent",
        ToolDisposition.SUSPENDED,
        _REDISCOVER + "keep the primary model as actor and invoke admitted explicit tools directly.",
    ),
    LifecycleEntry(
        "gh_explore_workflow",
        ToolDisposition.SUSPENDED,
        _REDISCOVER + "use an explicit inspect, create, connect, solve, and inspect sequence.",
    ),
    LifecycleEntry(
        "gh_replay_recipe",
        ToolDisposition.SUSPENDED,
        _REDISCOVER + "inspect recipe data and use explicit mutation only after bounded validation.",
    ),
)

_BY_NAME = MappingProxyType({entry.name: entry for entry in CONTAINED_TOOLS})


def resolve_contained_tool(name: object) -> LifecycleEntry | None:
    """Resolve only exact, case-sensitive string identities."""
    if type(name) is not str:
        return None
    return _BY_NAME.get(name)


def denial_payload(entry: LifecycleEntry) -> dict[str, object]:
    """Return the stable caller-visible lifecycle denial."""
    if type(entry) is not LifecycleEntry:
        raise TypeError("entry must be a LifecycleEntry")
    return {
        "code": "legacy_semantic_tool_contained",
        "tool": entry.name,
        "verified": False,
        "retryable": False,
        "disposition": entry.disposition.value,
        "recovery": entry.recovery,
    }
