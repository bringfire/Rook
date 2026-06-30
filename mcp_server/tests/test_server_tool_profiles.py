import asyncio

import pytest

from rook import server
from rook.mcp_tool_profiles import (
    PUBLIC_LEAN_TOOL_NAMES,
    PUBLIC_READONLY_TOOL_NAMES,
    SENTINEL_TOOL_NAMES,
)

_GATED = {"rhino_command_experiment", "rhino_learn_next", "rhino_prepare_geometry"}


def _list_names(monkeypatch, profile_value):
    # Default flag-off state so the live surface is the canonical 427.
    monkeypatch.delenv("ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    if profile_value is None:
        monkeypatch.delenv("ROOK_MCP_TOOL_PROFILE", raising=False)
    else:
        monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile_value)
    tools = asyncio.run(server.list_tools())
    return {t.name for t in tools}


def test_full_surface_is_427_and_gates_deprecated(monkeypatch):
    full = _list_names(monkeypatch, None)  # absent => full
    assert len(full) == 427
    assert _GATED.isdisjoint(full)
    assert PUBLIC_LEAN_TOOL_NAMES <= full
    assert PUBLIC_READONLY_TOOL_NAMES <= full
    assert SENTINEL_TOOL_NAMES <= full


def test_explicit_full_equals_absent(monkeypatch):
    assert _list_names(monkeypatch, "full") == _list_names(monkeypatch, None)


def test_lean_surface_is_exactly_17(monkeypatch):
    lean = _list_names(monkeypatch, "lean")
    assert lean == set(PUBLIC_LEAN_TOOL_NAMES)
    assert len(lean) == 17


def test_readonly_surface_is_exactly_145(monkeypatch):
    ro = _list_names(monkeypatch, "readonly")
    assert ro == set(PUBLIC_READONLY_TOOL_NAMES)
    assert len(ro) == 145


def test_readonly_partition_over_live_surface(monkeypatch):
    full = _list_names(monkeypatch, None)
    ro = set(PUBLIC_READONLY_TOOL_NAMES)
    assert ro <= full
    assert ro.isdisjoint(SENTINEL_TOOL_NAMES)
    excluded = full - ro
    assert ro | excluded == full
    assert ro.isdisjoint(excluded)
    assert len(ro) + len(excluded) == len(full) == 427
