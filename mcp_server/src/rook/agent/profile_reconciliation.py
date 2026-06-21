"""LM2D profile reconciliation against disposable active-schema evidence.

Composition module (not import-light): activates a disposable ToolRegistry for a
profile's initial tier plus its groups, audits the active surface (LM1A), and
reports intended-vs-active drift and group-activation failures as
CapabilityFindings, carrying the profile's own ProfileFindings verbatim.

Read-only/diagnostic: no shared/runtime registry mutation, no surface compiler,
no runtime policy. It re-derives no profile facts from `sources` -- intended
names come only from `resolution.tool_names`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rook.agent.capability_inventory import (
    capability_findings_from_audit,
    dispatch_context_from_sources,
)
from rook.agent.capability_record import CapabilityFinding, SurfaceSources
from rook.agent.chat.tool_contracts import audit_visible_tool_dispatchability
from rook.agent.execution_profile import ProfileFinding, ProfileResolution
from rook.agent.tool_registry import ToolRegistry

_TIER_FIELDS = frozenset({"tier0", "agent_tier0", "readonly_tier0"})


@dataclass(frozen=True)
class ProfileReconciliation:
    profile_name: str
    intended_names: tuple[str, ...]
    active_names: tuple[str, ...]
    registry_findings: tuple[CapabilityFinding, ...]
    profile_findings: tuple[ProfileFinding, ...]


def _active_tool_names(registry: ToolRegistry) -> frozenset[str]:
    names: set[str] = set()
    for schema in registry.get_active_schemas():
        function = schema.get("function") if isinstance(schema, dict) else None
        if isinstance(function, dict) and isinstance(function.get("name"), str):
            names.add(function["name"])
    return frozenset(names)


def reconcile_profile(
    resolution: ProfileResolution,
    sources: SurfaceSources,
    catalog: Mapping[str, dict],
) -> ProfileReconciliation:
    definition = resolution.profile
    initial = definition.initial_tier
    tier_members = (
        frozenset(getattr(sources, initial))
        if initial in _TIER_FIELDS
        else frozenset()
    )
    registry = ToolRegistry(catalog=dict(catalog), tier0=set(tier_members))

    findings: list[CapabilityFinding] = []
    for group in definition.groups:
        result = registry.request_group(group)
        if not result.get("success"):
            findings.append(
                CapabilityFinding(
                    code="group_activation_failed",
                    tool=group,
                    severity="warning",
                    message=result.get(
                        "error", f"Group '{group}' could not be activated."
                    ),
                )
            )

    active_schemas = registry.get_active_schemas()
    active_names = _active_tool_names(registry)
    ctx = dispatch_context_from_sources(sources)
    findings.extend(
        capability_findings_from_audit(
            audit_visible_tool_dispatchability(active_schemas, ctx)
        )
    )

    intended = frozenset(resolution.tool_names)
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

    registry_findings = tuple(
        sorted(findings, key=lambda f: (f.tool, f.code, f.severity))
    )
    return ProfileReconciliation(
        profile_name=definition.name,
        intended_names=resolution.tool_names,
        active_names=tuple(sorted(active_names)),
        registry_findings=registry_findings,
        profile_findings=resolution.findings,
    )
