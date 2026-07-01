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
