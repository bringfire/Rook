"""LM2A capability inventory and reconciliation (read-only).

Builds capability records from an injected SurfaceSources snapshot plus a
catalog (static layer), and reconciles intended membership against a disposable
canned-catalog ToolRegistry (reconciliation layer). Changes no runtime behavior.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Iterable, Literal

from rook.agent.capability_record import (
    CapabilityFinding,
    CapabilityInventory,
    CapabilityRecord,
    SurfaceSources,
    TIER_FIELDS,
    Visibility,
)
from rook.agent.chat.tool_contracts import (
    DispatchContext,
    DispatchabilityFinding,
    audit_visible_tool_dispatchability,
    classify_visible_tool,
)
from rook.agent.tool_registry import ToolRegistry
from rook.mcp_capability_gateway_contract import MCP_CAPABILITY_GATEWAY_NAMES
from rook.tool_lifecycle import resolve_contained_tool

INTERNAL_AGENT_META_TOOLS: frozenset[str] = frozenset({
    "request_tools",
    "search_tools",
}) | MCP_CAPABILITY_GATEWAY_NAMES

_DISPATCH_UNKNOWN_SEVERITY = {
    "local_visible": "error",
    "mcp_only_visible": "info",
    "support_only": "warning",
}


def dispatch_context_from_sources(sources: SurfaceSources) -> DispatchContext:
    return DispatchContext(
        intercepted_names=frozenset(sources.intercepted_names),
        local_tool_names=frozenset(sources.local_tool_names),
        transform_names=frozenset(sources.transform_names),
        bridge_names=frozenset(sources.bridge_names),
        excluded_names=frozenset(sources.excluded_names),
        strict_no_argument_names=frozenset(sources.strict_no_argument_names),
    )


def _sorted_findings(findings: list[CapabilityFinding]) -> list[CapabilityFinding]:
    return sorted(findings, key=lambda f: (f.tool, f.code, f.severity))


def _tiers_for(name: str, sources: SurfaceSources) -> tuple[str, ...]:
    return tuple(sorted(tf for tf in TIER_FIELDS if name in getattr(sources, tf)))


def _groups_for(name: str, sources: SurfaceSources) -> tuple[str, ...]:
    return tuple(
        sorted(g for g, tools in sources.groups.items() if name in tools)
    )


def _risk_for(name: str, sources: SurfaceSources) -> tuple[str, ...]:
    out: list[str] = []
    if name in sources.creation_tools:
        out.append("creation")
    if name in sources.modal_risk_tools:
        out.append("modal_risk")
    if name in sources.needs_verification:
        out.append("needs_verification")
    return tuple(sorted(out))


def _visibility(
    name: str, sources: SurfaceSources, groups: tuple[str, ...]
) -> tuple[Visibility, bool, bool]:
    in_tier = bool(_tiers_for(name, sources))
    mcp_groups = [g for g in groups if g in sources.mcp_only_groups]
    non_mcp_groups = [g for g in groups if g not in sources.mcp_only_groups]
    mcp_only = bool(groups) and not non_mcp_groups
    contradictory = bool(mcp_groups) and bool(non_mcp_groups)
    if in_tier or non_mcp_groups:
        visibility: Visibility = "local_visible"
    elif groups:
        visibility = "mcp_only_visible"
    else:
        visibility = "support_only"
    return visibility, mcp_only, contradictory


def _universe(sources: SurfaceSources, catalog: Mapping[str, dict]) -> list[str]:
    names: set[str] = set()
    for tier_field in TIER_FIELDS:
        names |= set(getattr(sources, tier_field))
    for tools in sources.groups.values():
        names |= set(tools)
    names |= set(sources.bridge_names) | set(sources.transform_names)
    names |= set(sources.intercepted_names) | set(sources.excluded_names)
    names |= set(sources.local_tool_names)
    names |= set(sources.creation_tools) | set(sources.modal_risk_tools)
    names |= set(sources.needs_verification)
    names |= set(catalog.keys())
    return sorted(name for name in names if resolve_contained_tool(name) is None)


def build_inventory(
    sources: SurfaceSources, catalog: Mapping[str, dict]
) -> CapabilityInventory:
    ctx = dispatch_context_from_sources(sources)
    records: list[CapabilityRecord] = []
    findings: list[CapabilityFinding] = []

    for name in _universe(sources, catalog):
        groups = _groups_for(name, sources)
        tiers = _tiers_for(name, sources)
        risk = _risk_for(name, sources)
        visibility, mcp_only, contradictory = _visibility(name, sources, groups)
        classification = classify_visible_tool(name, ctx)
        dispatch_path = None if classification == "failure" else classification
        has_schema = name in catalog
        no_argument = (
            name in sources.zero_argument_names
            or name in sources.strict_no_argument_names
        )

        records.append(
            CapabilityRecord(
                name=name,
                visibility=visibility,
                tiers=tiers,
                groups=groups,
                dispatch_path=dispatch_path,
                has_schema=has_schema,
                risk=risk,
                no_argument=no_argument,
                mcp_only=mcp_only,
            )
        )

        if dispatch_path is None:
            findings.append(
                CapabilityFinding(
                    code="dispatch_unknown",
                    tool=name,
                    severity=_DISPATCH_UNKNOWN_SEVERITY[visibility],
                    message=(
                        f"No dispatch/intercept/transform/bridge/exclusion path "
                        f"for '{name}'."
                    ),
                )
            )
        if visibility == "local_visible" and not has_schema:
            findings.append(
                CapabilityFinding(
                    code="missing_schema",
                    tool=name,
                    severity="warning",
                    message=f"Locally-visible tool '{name}' has no catalog schema.",
                )
            )
        if contradictory:
            findings.append(
                CapabilityFinding(
                    code="contradictory_membership",
                    tool=name,
                    severity="error",
                    message=(
                        f"Tool '{name}' is in both an MCP-only group and a "
                        f"non-MCP group."
                    ),
                )
            )

    return CapabilityInventory(
        records=tuple(records),
        findings=tuple(_sorted_findings(findings)),
    )


def format_report(inventory: CapabilityInventory) -> str:
    counts = {"error": 0, "warning": 0, "info": 0}
    for finding in inventory.findings:
        counts[finding.severity] += 1
    lines = [
        f"Capability inventory: {len(inventory.records)} records, "
        f"{len(inventory.findings)} findings",
        f"  errors={counts['error']} warnings={counts['warning']} "
        f"info={counts['info']}",
    ]
    for finding in inventory.findings:
        lines.append(
            f"  [{finding.severity}] {finding.code} {finding.tool}: "
            f"{finding.message}"
        )
    return "\n".join(lines)


_DISPATCHABILITY_SEVERITY = {
    "not_dispatchable": "error",
    "missing_function_name": "error",
    "strict_no_arg_schema_drift": "error",
    "duplicate_visible_name": "warning",
}


def capability_findings_from_audit(
    audit_findings: Iterable[DispatchabilityFinding],
) -> list[CapabilityFinding]:
    """Map LM1A dispatchability findings onto CapabilityFindings with severity.

    Shared by reconcile_active_schemas and profile_reconciliation so the severity
    table has a single home. Returns a list; callers combine/sort with their own
    findings.
    """
    return [
        CapabilityFinding(
            code=finding.code,
            tool=finding.tool,
            severity=_DISPATCHABILITY_SEVERITY.get(finding.code, "warning"),
            message=finding.message,
        )
        for finding in audit_findings
    ]


def _active_tool_names(registry: ToolRegistry) -> frozenset[str]:
    names: set[str] = set()
    for schema in registry.get_active_schemas():
        function = schema.get("function") if isinstance(schema, dict) else None
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.add(function["name"])
    return frozenset(names)


def reconcile_active_schemas(
    sources: SurfaceSources,
    catalog: Mapping[str, dict],
    *,
    group: str | None = None,
    initial: Literal["tier0", "agent_tier0", "readonly_tier0", "planner_tier0"] = "agent_tier0",
) -> tuple[CapabilityFinding, ...]:
    selected_tier = frozenset(getattr(sources, initial))
    registry = ToolRegistry(catalog=dict(catalog), tier0=set(selected_tier))
    if group is not None:
        registry.request_group(group)

    active_schemas = registry.get_active_schemas()
    active_names = _active_tool_names(registry)
    ctx = dispatch_context_from_sources(sources)

    findings: list[CapabilityFinding] = capability_findings_from_audit(
        audit_visible_tool_dispatchability(active_schemas, ctx)
    )

    if group is None:
        intended = selected_tier
    else:
        intended = selected_tier | frozenset(sources.groups.get(group, ()))

    for name in sorted(intended - active_names):
        findings.append(
            CapabilityFinding(
                code="intended_not_active",
                tool=name,
                severity="warning",
                message=f"Intended tool '{name}' is not in the active schema set.",
            )
        )
    for name in sorted(active_names - intended):
        findings.append(
            CapabilityFinding(
                code="active_not_intended",
                tool=name,
                severity="warning",
                message=f"Active tool '{name}' is not in the intended set.",
            )
        )

    return tuple(_sorted_findings(findings))


def collect_live_sources() -> SurfaceSources:
    """Read module constants only. No catalog cache, no MCP, no live ToolRegistry,
    no ToolDispatcher instantiation. local_tool_names is left empty."""
    from rook.agent import planner as _planner
    from rook.agent import tool_groups as tg
    from rook.agent import tool_dispatcher as td
    from rook.agent.chat import execution_policy as ep
    from rook.agent.chat.tool_contracts import ZERO_ARGUMENT_TOOLS

    return SurfaceSources(
        tier0=frozenset(tg.TIER_0),
        agent_tier0=frozenset(tg.AGENT_TIER_0),
        readonly_tier0=frozenset(tg.READONLY_TIER_0),
        planner_tier0=frozenset(_planner.PLANNER_TIER_0),
        groups={g: tuple(tools) for g, tools in tg.TOOL_GROUPS.items()},
        mcp_only_groups=frozenset(tg.MCP_ONLY_GROUPS),
        readonly_allowed_groups=frozenset(tg.READONLY_ALLOWED_GROUPS),
        planner_allowed_groups=frozenset(_planner.PLANNER_ALLOWED_GROUPS),
        bridge_names=frozenset(td.BRIDGE_ROUTES.keys()),
        transform_names=frozenset(td.TRANSFORM_FUNCTIONS.keys()),
        intercepted_names=INTERNAL_AGENT_META_TOOLS,
        excluded_names=frozenset(tg.LOCAL_TIER_0_DISPATCH_EXCLUSIONS),
        local_tool_names=frozenset(),
        zero_argument_names=frozenset(ZERO_ARGUMENT_TOOLS),
        strict_no_argument_names=frozenset(td.STRICT_NO_ARGUMENT_BRIDGE_TOOLS),
        creation_tools=frozenset(ep.CREATION_TOOLS),
        modal_risk_tools=frozenset(ep.MODAL_RISK_TOOLS),
        needs_verification=frozenset(ep.NEEDS_VERIFICATION),
    )


def collect_runtime_sources() -> SurfaceSources:
    """Runtime-enriched surface snapshot.

    collect_live_sources() plus the ACTUAL local tools dispatchable in THIS
    runtime (build_local_tools().keys()). Diagnostic runtime evidence -- NOT a
    static registry or policy source, and intentionally environment-dependent
    (a local tool whose optional import fails is faithfully absent, so it is
    genuinely not dispatchable here).

    An unexpected build_local_tools() failure propagates; this never silently
    returns empty local_tool_names. Per-tool optional-import failures are
    handled inside build_local_tools() itself.
    """
    from rook.agent import tool_dispatcher as td  # lazy, like collect_live_sources

    base = collect_live_sources()
    local_names = frozenset(td.build_local_tools().keys())
    return dataclasses.replace(base, local_tool_names=local_names)
