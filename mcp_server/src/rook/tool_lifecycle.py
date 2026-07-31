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

ROADCREATOR_TOOL_NAMES = frozenset({
    "rc_apply_intersection_ownership",
    "rc_apply_sidewalk_ownership",
    "rc_assemble_route",
    "rc_build_profile",
    "rc_clothoid",
    "rc_concrete_barrier_profile",
    "rc_contour_levels",
    "rc_cross_section",
    "rc_crossing",
    "rc_crossing_params",
    "rc_cubic_parabola",
    "rc_deltablok_profile",
    "rc_extract_offsets",
    "rc_get_road_profile",
    "rc_guardrail",
    "rc_guardrail_profile",
    "rc_list_road_profiles",
    "rc_longitudinal_profile",
    "rc_ping",
    "rc_pole_spacing",
    "rc_project_offset_profile",
    "rc_resolve_edges",
    "rc_road_3d",
    "rc_road_footprint",
    "rc_roads",
    "rc_roundabout_params",
    "rc_sidewalk",
    "rc_sidewalk_corners",
    "rc_sidewalk_profile",
    "rc_slope_profile",
    "rc_slopes",
    "rc_standards",
    "rc_store_road_profile",
    "rc_terrain_profile",
    "rc_validate_profile",
    "rc_validate_road_profile",
    "rc_validate_style_set",
    "rc_verge_profile",
    "rc_vertical_curve",
    "rc_widening",
})

_ROADCREATOR_RECOVERY = (
    _REDISCOVER
    + "RoadCreator/RookRoads is not in the supported Rook surface; use admitted native "
    "Rook tools or another supported workflow."
)
_UNCLASSIFIED_RC_RECOVERY = (
    _REDISCOVER
    + "the rc_* namespace is reserved; add an explicit lifecycle entry before admitting "
    "this tool."
)

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
    *(
        LifecycleEntry(name, ToolDisposition.SUSPENDED, _ROADCREATOR_RECOVERY)
        for name in sorted(ROADCREATOR_TOOL_NAMES)
    ),
)

_BY_NAME = MappingProxyType({entry.name: entry for entry in CONTAINED_TOOLS})


def resolve_contained_tool(name: object) -> LifecycleEntry | None:
    """Resolve exact tombstones and fail closed for the reserved rc_* namespace."""
    if type(name) is not str:
        return None
    entry = _BY_NAME.get(name)
    if entry is not None:
        return entry
    if name.startswith("rc_"):
        return LifecycleEntry(
            name,
            ToolDisposition.SUSPENDED,
            _UNCLASSIFIED_RC_RECOVERY,
        )
    return None


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
