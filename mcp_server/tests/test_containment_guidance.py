from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "mcp_server" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.tool_lifecycle import CONTAINED_TOOLS  # noqa: E402


GUIDANCE_ROOTS = (
    ROOT / ".agents" / "skills",
    ROOT / ".claude" / "skills",
    ROOT / "installer" / "agent-assets" / "codex-skills",
    ROOT / "mcp_server" / "src" / "rook" / "agent" / "prompts",
    ROOT / "mcp_server" / "src" / "rook" / "agent" / "personas",
)
GUIDANCE_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "AGENT_SETUP.md",
    ROOT / "README.md",
    ROOT / "installer" / "AGENTS.md",
    ROOT / "installer" / "CLAUDE.md",
    ROOT / "docs" / "ONBOARDING_NEW_CLAUDE.md",
    ROOT / "docs" / "TROUBLESHOOTING.md",
    ROOT / "docs" / "AGENT_ARCHITECTURE.md",
    ROOT / "docs" / "CURRENT_ARCHITECTURE.md",
    ROOT / "docs" / "rook_docs" / "POSITIONING.md",
    ROOT / "scripts" / "session-start.sh",
    ROOT / "mcp_server" / "src" / "rook" / "learning" / "dspy_signatures.py",
)
INSTALLER_GUIDANCE_FILES = (
    ROOT / "installer" / "AGENTS.md",
    ROOT / "installer" / "CLAUDE.md",
)
BACKTICK_TOKEN_RE = re.compile(r"`([^`\r\n]+)`")
MCP_TOOL_NAME_RE = re.compile(r"[a-z][a-z0-9_]*_[a-z0-9_]+")
SLASH_COMMAND_RE = re.compile(r"/[a-z][a-z0-9-]*")
ALLOWED_SLASH_COMMANDS = frozenset({"/mcp", "/chirp", "/chirp-cascade"})
RETIRED_SKILL_ROOTS = (
    ROOT / ".agents" / "skills" / "design-road",
    ROOT / ".agents" / "skills" / "masterplan-roads",
    ROOT / ".claude" / "skills" / "design-road",
    ROOT / ".claude" / "skills" / "masterplan-roads",
    ROOT / "installer" / "agent-assets" / "codex-skills" / "design-road",
    ROOT / "installer" / "agent-assets" / "codex-skills" / "masterplan-roads",
)
RETIRED_GUIDANCE_IDENTITIES = (
    "design-road",
    "masterplan-roads",
    "RoadCreator",
    "RookRoads",
)
ACTIVE_RETIREMENT_GUIDANCE_FILES = (
    ROOT / "README.md",
    ROOT / "QUICK_START.md",
    ROOT / "AGENT_SETUP.md",
    ROOT / "installer" / "agent-assets" / "ROOK_CLAUDE_POST_INSTALL.md",
    ROOT / "installer" / "agent-assets" / "ROOK_CODEX_POST_INSTALL.md",
    ROOT / "scripts" / "session-start.sh",
)
RETAINED_WASP_SKILL_ROOTS = tuple(
    ROOT / prefix / skill
    for prefix in (
        Path(".agents/skills"),
        Path(".claude/skills"),
        Path("installer/agent-assets/codex-skills"),
    )
    for skill in ("chirp-cascade", "design-grasshopper", "plan-grasshopper")
)


def test_retired_road_skill_roots_are_absent() -> None:
    assert [str(path.relative_to(ROOT)) for path in RETIRED_SKILL_ROOTS if path.exists()] == []


def test_scoped_active_guidance_has_no_retired_road_identity() -> None:
    findings = []
    for path in ACTIVE_RETIREMENT_GUIDANCE_FILES:
        text = path.read_text(encoding="utf-8", errors="replace")
        for identity in RETIRED_GUIDANCE_IDENTITIES:
            if identity in text:
                findings.append(f"{path.relative_to(ROOT)}: {identity}")
    assert findings == []


@pytest.mark.asyncio
async def test_live_model_visible_catalog_has_no_retired_road_identity() -> None:
    from rook import server

    tools = await server._all_live_tools()
    rendered = json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in tools
        ],
        sort_keys=True,
    )
    assert [identity for identity in RETIRED_GUIDANCE_IDENTITIES if identity in rendered] == []


def test_retained_wasp_skill_roots_remain_outside_retired_roots() -> None:
    for path in RETAINED_WASP_SKILL_ROOTS:
        assert path.is_dir(), path
        skill_file = path / "SKILL.md"
        assert skill_file.is_file(), skill_file
        assert "Wasp" in skill_file.read_text(encoding="utf-8", errors="replace")
        assert all(retired not in path.parents and path != retired for retired in RETIRED_SKILL_ROOTS)


def test_active_and_installer_shipped_guidance_has_no_contained_identity() -> None:
    names = tuple(entry.name for entry in CONTAINED_TOOLS)
    files = list(GUIDANCE_FILES)
    for root in GUIDANCE_ROOTS:
        files.extend(path for path in root.rglob("*") if path.is_file())

    findings = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [name for name in names if name in text]
        if hits:
            findings.append(f"{path.relative_to(ROOT)}: {', '.join(hits)}")
    assert findings == []


@pytest.mark.asyncio
async def test_installer_guidance_names_only_live_mcp_tools() -> None:
    from rook import server

    live_names = {tool.name for tool in await server._all_live_tools()}
    unknown_by_file: dict[str, list[str]] = {}
    slash_commands: set[str] = set()

    for path in INSTALLER_GUIDANCE_FILES:
        tokens = BACKTICK_TOKEN_RE.findall(path.read_text(encoding="utf-8"))
        named_tools = {token for token in tokens if MCP_TOOL_NAME_RE.fullmatch(token)}
        unknown = sorted(named_tools - live_names)
        if unknown:
            unknown_by_file[str(path.relative_to(ROOT))] = unknown
        slash_commands.update(
            token for token in tokens if SLASH_COMMAND_RE.fullmatch(token)
        )

    assert unknown_by_file == {}
    assert slash_commands <= ALLOWED_SLASH_COMMANDS


def test_installer_guidance_separates_tool_and_component_discovery() -> None:
    for path in INSTALLER_GUIDANCE_FILES:
        text = path.read_text(encoding="utf-8")
        assert "Progressive discovery searches Rook tools, not Grasshopper components" in text
        assert "`gh_library` for exact component identity" in text
        assert "`gh_batch_component_info` for SDK-backed input/output metadata" in text


@pytest.mark.asyncio
async def test_knowledge_query_is_optional_advisory_context() -> None:
    from rook import server

    tools = await server._all_live_tools()
    description = next(tool.description for tool in tools if tool.name == "knowledge_query")

    assert "optional advisory context" in description.lower()
    assert "before every" not in description.lower()
