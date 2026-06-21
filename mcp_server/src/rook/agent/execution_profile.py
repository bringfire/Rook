"""LM2B read-only execution-profile view over the LM2A capability inventory.

Stdlib-only: imports only the LM2A stdlib-only record module. Resolves a
ProfileDefinition's intended tool set by inverting CapabilityInventory records
(no SurfaceSources, no dispatch-table rescan) and emits provenance-aware
findings. Diagnostic only; changes no runtime behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from rook.agent.capability_record import (
    CapabilityInventory,
    CapabilityRecord,
    Severity,
    SurfaceSources,
)


@dataclass(frozen=True)
class ProfileDefinition:
    name: str
    initial_tier: Literal["tier0", "agent_tier0", "readonly_tier0", "planner_tier0"] | None = None
    groups: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    description: str | None = None


@dataclass(frozen=True)
class ProfileFinding:
    profile: str
    code: str
    subject: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class ProfileResolution:
    profile: ProfileDefinition
    tools: tuple[CapabilityRecord, ...]
    tool_names: tuple[str, ...]
    findings: tuple[ProfileFinding, ...]


def _sorted_profile_findings(
    findings: list[ProfileFinding],
) -> list[ProfileFinding]:
    return sorted(findings, key=lambda f: (f.code, f.subject))


def resolve_profile(
    definition: ProfileDefinition, inventory: CapabilityInventory
) -> ProfileResolution:
    records = inventory.records
    by_name = {r.name: r for r in records}
    known_groups: set[str] = set()
    known_tiers: set[str] = set()
    for record in records:
        known_groups.update(record.groups)
        known_tiers.update(record.tiers)

    tier_names: set[str] = set()
    if definition.initial_tier is not None:
        tier_names = {
            r.name for r in records if definition.initial_tier in r.tiers
        }

    group_names: set[str] = set()
    for group in definition.groups:
        group_names.update(r.name for r in records if group in r.groups)

    pin_names = set(definition.tools)
    intended = sorted(tier_names | group_names | pin_names)
    tools = tuple(by_name[name] for name in intended if name in by_name)

    name = definition.name
    findings: list[ProfileFinding] = []

    if (
        definition.initial_tier is not None
        and definition.initial_tier not in known_tiers
    ):
        findings.append(
            ProfileFinding(
                profile=name,
                code="unknown_tier",
                subject=definition.initial_tier,
                severity="warning",
                message=(
                    f"Profile '{name}' references tier "
                    f"'{definition.initial_tier}' present in no inventory record."
                ),
            )
        )
    for group in definition.groups:
        if group not in known_groups:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="unknown_group",
                    subject=group,
                    severity="warning",
                    message=(
                        f"Profile '{name}' references group '{group}' present in "
                        f"no inventory record."
                    ),
                )
            )
    for pin in definition.tools:
        if pin not in by_name:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="unknown_tool",
                    subject=pin,
                    severity="warning",
                    message=f"Profile '{name}' pins tool '{pin}' with no record.",
                )
            )

    for record in tools:
        if record.mcp_only or record.visibility == "mcp_only_visible":
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="mcp_only_tool",
                    subject=record.name,
                    severity="warning",
                    message=(
                        f"Profile '{name}' includes MCP-only tool "
                        f"'{record.name}'."
                    ),
                )
            )
        elif record.visibility == "local_visible" and record.dispatch_path is None:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="not_dispatchable",
                    subject=record.name,
                    severity="error",
                    message=(
                        f"Profile '{name}' includes local-visible tool "
                        f"'{record.name}' with no dispatch path."
                    ),
                )
            )
        if record.visibility == "local_visible" and not record.has_schema:
            findings.append(
                ProfileFinding(
                    profile=name,
                    code="missing_schema",
                    subject=record.name,
                    severity="warning",
                    message=(
                        f"Profile '{name}' includes local-visible tool "
                        f"'{record.name}' with no catalog schema."
                    ),
                )
            )

    if not tools:
        findings.append(
            ProfileFinding(
                profile=name,
                code="empty_profile",
                subject=name,
                severity="warning",
                message=f"Profile '{name}' resolves to zero known tools.",
            )
        )

    return ProfileResolution(
        profile=definition,
        tools=tools,
        tool_names=tuple(intended),
        findings=tuple(_sorted_profile_findings(findings)),
    )


def resolve_profiles(
    definitions: Iterable[ProfileDefinition], inventory: CapabilityInventory
) -> tuple[ProfileResolution, ...]:
    return tuple(resolve_profile(d, inventory) for d in definitions)


def default_profile_definitions() -> tuple[ProfileDefinition, ...]:
    """Non-authoritative diagnostic seed profiles.

    All seeds are tier-only (groups=()): name-suffix heuristics are not
    faithful proxies for policy, so group membership is deferred until the
    source snapshot carries explicit evidence. No external_mcp seed.
    """
    return (
        ProfileDefinition(
            name="rookchat_local",
            initial_tier="agent_tier0",
            groups=(),
            description="Local in-file execution worker (diagnostic seed).",
        ),
        ProfileDefinition(
            name="readonly",
            initial_tier="readonly_tier0",
            groups=(),
            description="Observation-only worker (diagnostic seed).",
        ),
        ProfileDefinition(
            name="planner",
            initial_tier="planner_tier0",
            groups=(),
            description="Read-only planning/query worker (diagnostic tier-only seed; "
            "evidence-backed groups via planner_profile_from_sources).",
        ),
    )


def readonly_profile_from_sources(sources: SurfaceSources) -> ProfileDefinition:
    """Evidence-backed, locally-executable readonly seed.

    Groups = readonly-allowed groups that (a) have a definition in this same
    snapshot and (b) are not MCP-only. The result is resolvable against the
    inventory built from the same SurfaceSources and never knowingly emits an
    unknown_group finding from the default seed. Emits no findings itself.

    `(A & B) - C` is set-identical to Python's precedence-driven `A & (B - C)`;
    explicit parentheses are used for the reader.
    """
    local_groups = (
        sources.readonly_allowed_groups & frozenset(sources.groups.keys())
    ) - sources.mcp_only_groups
    return ProfileDefinition(
        name="readonly",
        initial_tier="readonly_tier0",
        groups=tuple(sorted(local_groups)),
        description="Locally-executable observation-only worker (evidence-backed seed).",
    )


def readonly_excluded_mcp_only_groups(sources: SurfaceSources) -> tuple[str, ...]:
    """Readonly-allowed groups deliberately excluded because they are MCP-only.

    Full policy intersection -- NOT filtered by groups.keys() -- so the excluded
    pin reflects policy regardless of whether a group definition exists.
    """
    return tuple(sorted(sources.readonly_allowed_groups & sources.mcp_only_groups))


def planner_profile_from_sources(sources: SurfaceSources) -> ProfileDefinition:
    """Evidence-backed, locally-executable planner seed (read-only plan/query).

    Groups = planner-allowed groups that have a definition in this snapshot and
    are not MCP-only. Mirrors readonly_profile_from_sources.
    """
    local_groups = (
        sources.planner_allowed_groups & frozenset(sources.groups.keys())
    ) - sources.mcp_only_groups
    return ProfileDefinition(
        name="planner",
        initial_tier="planner_tier0",
        groups=tuple(sorted(local_groups)),
        description="Read-only planning/query worker (evidence-backed seed).",
    )


def planner_excluded_mcp_only_groups(sources: SurfaceSources) -> tuple[str, ...]:
    """Planner-allowed groups excluded because they are MCP-only.

    Full policy intersection -- NOT filtered by groups.keys().
    """
    return tuple(sorted(sources.planner_allowed_groups & sources.mcp_only_groups))


def format_profile_report(
    resolutions: Iterable[ProfileResolution],
) -> str:
    lines: list[str] = []
    for resolution in resolutions:
        counts = {"error": 0, "warning": 0, "info": 0}
        for finding in resolution.findings:
            counts[finding.severity] += 1
        lines.append(
            f"Profile {resolution.profile.name}: "
            f"{len(resolution.tools)} tools, "
            f"{len(resolution.findings)} findings "
            f"(errors={counts['error']} warnings={counts['warning']} "
            f"info={counts['info']})"
        )
        for finding in resolution.findings:
            lines.append(
                f"  [{finding.severity}] {finding.code} {finding.subject}: "
                f"{finding.message}"
            )
    return "\n".join(lines)
