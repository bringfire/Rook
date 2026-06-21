"""LM2A capability record types (stdlib-only).

Plain frozen dataclasses describing the read-only capability inventory. This
module must stay stdlib-only: it must not import tool_contracts or
tool_dispatcher. The DispatchContext mapping for the LM1A audit lives in
capability_inventory.py instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

Visibility = Literal["local_visible", "mcp_only_visible", "support_only"]
Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class SurfaceSources:
    tier0: frozenset[str] = frozenset()
    agent_tier0: frozenset[str] = frozenset()
    readonly_tier0: frozenset[str] = frozenset()
    groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    mcp_only_groups: frozenset[str] = frozenset()
    readonly_allowed_groups: frozenset[str] = frozenset()
    bridge_names: frozenset[str] = frozenset()
    transform_names: frozenset[str] = frozenset()
    intercepted_names: frozenset[str] = frozenset()
    excluded_names: frozenset[str] = frozenset()
    local_tool_names: frozenset[str] = frozenset()
    zero_argument_names: frozenset[str] = frozenset()
    strict_no_argument_names: frozenset[str] = frozenset()
    creation_tools: frozenset[str] = frozenset()
    modal_risk_tools: frozenset[str] = frozenset()
    needs_verification: frozenset[str] = frozenset()


@dataclass(frozen=True)
class CapabilityRecord:
    name: str
    visibility: Visibility
    tiers: tuple[str, ...]
    groups: tuple[str, ...]
    dispatch_path: str | None
    has_schema: bool
    risk: tuple[str, ...]
    no_argument: bool
    mcp_only: bool


@dataclass(frozen=True)
class CapabilityFinding:
    code: str
    tool: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class CapabilityInventory:
    records: tuple[CapabilityRecord, ...]
    findings: tuple[CapabilityFinding, ...]
