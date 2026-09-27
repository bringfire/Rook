"""The MCP server instructions are the one guidance channel every client receives.

They replaced the Claude plugin's bash SessionStart hook, which needed Git Bash on
Windows, marked the plugin "Can run code without asking", and never reached Chat or
Codex. These tests keep the carried-over rules present and the text client-neutral.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "mcp_server" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook import server  # noqa: E402
from rook.tool_lifecycle import CONTAINED_TOOLS  # noqa: E402

INSTRUCTIONS = server.SERVER_INSTRUCTIONS

# Some clients truncate long server instructions (observed cut-offs near 2,000
# characters), so the whole text must stay below that.
MAX_INSTRUCTION_CHARS = 1900


def test_server_uses_the_shared_instructions() -> None:
    assert server.mcp.instructions == INSTRUCTIONS


def test_instructions_fit_under_client_truncation() -> None:
    assert len(INSTRUCTIONS) <= MAX_INSTRUCTION_CHARS


def test_instructions_keep_the_rules_the_retired_hook_carried() -> None:
    for category in ("planner", "interpreter", "critic", "narrator", "classifier", "gate", "editor"):
        assert category in INSTRUCTIONS
    assert "chirp_create requires a category" in INSTRUCTIONS
    assert "Correction input pin" in INSTRUCTIONS and "Reasoning output pin" in INSTRUCTIONS
    assert "do not include them in pins_in or pins_out" in INSTRUCTIONS
    for skill in ("execute-grasshopper", "design-grasshopper", "plan-grasshopper", "chirp-cascade", "twisted-column"):
        assert skill in INSTRUCTIONS
    assert "Skills do not invoke the next stage automatically" in INSTRUCTIONS
    assert "rhino_ping" in INSTRUCTIONS


@pytest.mark.asyncio
async def test_instructions_name_only_live_tools() -> None:
    live = {tool.name for tool in await server._all_live_tools()}
    named = {"rhino_ping", "rook_tools_search", "rook_tools_read", "rook_tools_call", "chirp_create"}
    assert named <= live
    for name in named:
        assert name in INSTRUCTIONS


def test_instructions_name_no_contained_or_retired_identity() -> None:
    contained = [entry.name for entry in CONTAINED_TOOLS if entry.name in INSTRUCTIONS]
    assert contained == []
    for retired in ("design-road", "masterplan-roads", "RoadCreator", "RookRoads", "consolidate"):
        assert retired not in INSTRUCTIONS


def test_instructions_are_client_neutral() -> None:
    # Slash-command syntax differs per client (Claude Code /skill, Codex $skill,
    # chat has none), and skills may not be installed at all.
    assert re.search(r"(?<![\w/])/[a-z][a-z0-9-]+", INSTRUCTIONS) is None
    assert "when Rook's skills are installed" in INSTRUCTIONS
