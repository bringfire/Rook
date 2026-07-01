"""Public-MCP capability facet (read-only link to the LM2A agent facet)."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from rook.agent.capability_record import CapabilityRecord  # type only; stdlib-only module


@dataclass(frozen=True)
class McpCapabilityRecord:
    name: str
    path: str
    domain: str
    groups: tuple[str, ...]
    summary: str
    description: str
    readonly_safe: bool
    mcp_dispatchable: bool
    input_schema: Mapping[str, Any]
    agent_record: CapabilityRecord | None


@dataclass(frozen=True)
class CapabilityIndex:
    records: tuple[McpCapabilityRecord, ...]
    by_name: Mapping[str, McpCapabilityRecord]


from rook.mcp_tool_profiles import PUBLIC_READONLY_TOOL_NAMES
from rook.agent.tool_groups import TOOL_GROUPS

_DOMAIN_PREFIXES = (  # longest-prefix wins
    ("rhino_director_", "director"), ("rhino_vision_", "vision"),
    ("rhino_video_", "video"), ("rhino_2d_to_3d_", "vision"),
    ("rookbim_", "bim"), ("scene_", "scene"), ("rc_", "rc"), ("road_", "rc"),
    ("gh_", "gh"), ("rhino_", "rhino"), ("knowledge_", "knowledge"),
    ("session_", "session"), ("rook_tools_", "meta"),
)


def _domain_for(name: str) -> str:
    for prefix, domain in _DOMAIN_PREFIXES:
        if name.startswith(prefix):
            return domain
    return "other"


def _summary_of(description: str) -> str:
    text = (description or "").strip()
    dot = text.find(". ")
    return (text[: dot + 1] if dot != -1 else text.split("\n", 1)[0]).strip()


def _groups_for(name: str) -> tuple[str, ...]:
    return tuple(sorted(g for g, tools in TOOL_GROUPS.items() if name in tools))


def build_index(tools, agent_records, dispatchable_names) -> CapabilityIndex:
    records = []
    for tool in tools:
        name = tool.name
        domain = _domain_for(name)
        groups = _groups_for(name)
        head = f"/{domain}" + (f"/{groups[0]}" if groups else "")
        records.append(McpCapabilityRecord(
            name=name, path=f"{head}/{name}", domain=domain, groups=groups,
            summary=_summary_of(tool.description), description=tool.description or "",
            readonly_safe=name in PUBLIC_READONLY_TOOL_NAMES,
            mcp_dispatchable=name in dispatchable_names,
            input_schema=tool.inputSchema, agent_record=agent_records.get(name),
        ))
    records = tuple(records)
    return CapabilityIndex(records=records, by_name={r.name: r for r in records})
