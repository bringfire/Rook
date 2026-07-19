from __future__ import annotations

import sys
from pathlib import Path


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
    ROOT / "docs" / "rook_docs" / "POSITIONING.md",
    ROOT / "scripts" / "session-start.sh",
    ROOT / "mcp_server" / "src" / "rook" / "agent" / "chat" / "prompt_builder.py",
)


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
