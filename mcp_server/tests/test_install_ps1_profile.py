"""Text-guard over install.ps1: lean profile is Codex-only.

install.ps1 generates configs in PowerShell (Pester-free here), so we assert on
the script source: the Codex TOML here-string must add the lean profile env
line, and the Claude .mcp.json / .claude.json generation must not.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_PS1 = _REPO_ROOT / "install.ps1"


def _text():
    return _INSTALL_PS1.read_text(encoding="utf-8")


def test_install_ps1_exists():
    assert _INSTALL_PS1.is_file()


def test_codex_here_string_sets_lean_profile():
    text = _text()
    # The Codex TOML here-string is the only block emitting `[mcp_servers.rook.env]`.
    assert "[mcp_servers.rook.env]" in text
    assert "'ROOK_MCP_TOOL_PROFILE = \"lean\"'," in text


def test_claude_mcp_json_block_has_no_lean_profile():
    text = _text()
    # The Claude project/user config is generated via the `cfg = {...}` /
    # `config['mcpServers']['rook']` Python blocks; none may set the profile.
    assert "'ROOK_MCP_TOOL_PROFILE': 'lean'" not in text
    assert '"ROOK_MCP_TOOL_PROFILE": "lean"' not in text
