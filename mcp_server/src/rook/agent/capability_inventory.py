"""LM2A capability inventory and reconciliation (read-only).

Builds capability records from an injected SurfaceSources snapshot plus a
catalog (static layer), and reconciles intended membership against a disposable
canned-catalog ToolRegistry (reconciliation layer). Changes no runtime behavior.
"""

from __future__ import annotations

from collections.abc import Mapping

from rook.agent.capability_record import (
    CapabilityFinding,
    CapabilityInventory,
    CapabilityRecord,
    SurfaceSources,
    Visibility,
)
from rook.agent.chat.tool_contracts import (
    DispatchContext,
    classify_visible_tool,
)

INTERCEPTED_META_TOOLS: frozenset[str] = frozenset(
    {"request_tools", "search_tools", "ui_block", "list_chat_models", "set_chat_model"}
)

_DISPATCH_UNKNOWN_SEVERITY = {
    "local_visible": "error",
    "mcp_only_visible": "info",
    "support_only": "warning",
}


def _dispatch_context_from_sources(sources: SurfaceSources) -> DispatchContext:
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
    out: list[str] = []
    if name in sources.tier0:
        out.append("tier0")
    if name in sources.agent_tier0:
        out.append("agent_tier0")
    if name in sources.readonly_tier0:
        out.append("readonly_tier0")
    return tuple(sorted(out))


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
    names |= set(sources.tier0) | set(sources.agent_tier0) | set(sources.readonly_tier0)
    for tools in sources.groups.values():
        names |= set(tools)
    names |= set(sources.bridge_names) | set(sources.transform_names)
    names |= set(sources.intercepted_names) | set(sources.excluded_names)
    names |= set(sources.local_tool_names)
    names |= set(sources.creation_tools) | set(sources.modal_risk_tools)
    names |= set(sources.needs_verification)
    names |= set(catalog.keys())
    return sorted(names)


def build_inventory(
    sources: SurfaceSources, catalog: Mapping[str, dict]
) -> CapabilityInventory:
    ctx = _dispatch_context_from_sources(sources)
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
