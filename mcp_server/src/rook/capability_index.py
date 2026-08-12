"""Public-MCP capability facet (read-only link to the LM2A agent facet)."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from rook.agent.capability_record import CapabilityRecord  # type only; stdlib-only module
from rook.tool_lifecycle import resolve_contained_tool


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

    def _visible(self, *, scope_readonly: bool):
        for r in self.records:
            if not r.mcp_dispatchable:            # visible => mcp-dispatchable
                continue
            if scope_readonly and not r.readonly_safe:
                continue
            yield r

    def ls(self, path="/", depth=1, *, scope_readonly=False) -> dict:
        p = path if path.endswith("/") else path + "/"
        entries, children = [], set()
        for r in self._visible(scope_readonly=scope_readonly):
            if not (r.path + "").startswith(p if p != "/" else "/"):
                continue
            rest = r.path[len(p):] if p != "/" else r.path.lstrip("/")
            if rest.count("/") < depth:
                entries.append({"name": r.name, "path": r.path, "domain": r.domain,
                                "groups": list(r.groups), "readonly_safe": r.readonly_safe,
                                "summary": r.summary})
            else:
                children.add(p + "/".join(rest.split("/")[:depth]))
        return {"path": path, "entries": entries, "children": sorted(children)}

    def search(self, query, *, domain=None, scope_readonly=False, limit=10) -> list[dict]:
        terms = [t for t in query.lower().split() if t]
        scored = []
        for r in self._visible(scope_readonly=scope_readonly):
            if domain and r.domain != domain:
                continue
            hay = f"{r.name} {r.summary} {r.domain} {' '.join(r.groups)}".lower()
            score = sum(hay.count(t) for t in terms) + (2 if any(t in r.name.lower() for t in terms) else 0)
            if score:
                scored.append((score, r))
        scored.sort(key=lambda sr: (-sr[0], sr[1].name))
        return [{"name": r.name, "path": r.path, "domain": r.domain,
                 "readonly_safe": r.readonly_safe, "summary": r.summary} for _, r in scored[:limit]]

    def read(self, name, *, scope_readonly=False) -> dict | None:
        r = self.by_name.get(name)
        if r is None or not r.mcp_dispatchable:
            return None
        if scope_readonly and not r.readonly_safe:
            return None   # readonly clients must not read blocked-mutator schemas
        ar = r.agent_record
        return {"name": r.name, "path": r.path, "domain": r.domain, "groups": list(r.groups),
                "description": r.description, "readonly_safe": r.readonly_safe,
                "mcp_dispatchable": r.mcp_dispatchable, "input_schema": dict(r.input_schema),
                "agent_dispatchable": (ar is not None and ar.dispatch_path is not None),
                "agent_visibility": (ar.visibility if ar else None),
                "agent_mcp_only": (ar.mcp_only if ar else None)}


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
        if resolve_contained_tool(name) is not None:
            continue
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


_JSON_TYPES = {"string": str, "integer": int, "number": (int, float),
               "boolean": bool, "array": list, "object": dict}


def validate_arguments(schema, arguments) -> list[str]:
    errors: list[str] = []
    props = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
    unknown = sorted(key for key in arguments if key not in props)
    if unknown:
        accepted = sorted(props)
        errors.append(
            f"unknown fields: {', '.join(unknown)}; accepted fields: "
            f"{', '.join(accepted) if accepted else '<none>'}"
        )
    for req in schema.get("required", []) or []:
        if req not in arguments:
            errors.append(f"{req}: required field missing")
    for key, spec in props.items():
        if key not in arguments or not isinstance(spec, Mapping):
            continue
        val = arguments[key]
        t = spec.get("type")
        py = _JSON_TYPES.get(t)
        if py and not isinstance(val, py) or (t in ("integer", "number") and isinstance(val, bool)):
            errors.append(f"{key}: expected {t}")
            continue
        if "enum" in spec and val not in spec["enum"]:
            errors.append(f"{key}: must be one of {spec['enum']}")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if "minimum" in spec and val < spec["minimum"]:
                errors.append(f"{key}: below minimum {spec['minimum']}")
            if "maximum" in spec and val > spec["maximum"]:
                errors.append(f"{key}: above maximum {spec['maximum']}")
        if t == "array" and isinstance(val, list):
            item_t = (spec.get("items") or {}).get("type")
            ipy = _JSON_TYPES.get(item_t)
            if ipy and any(not isinstance(v, ipy) for v in val):
                errors.append(f"{key}: array items must be {item_t}")
    return errors
