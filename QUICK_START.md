# Rook Quick Start

Get AI controlling Rhino 3D in 5 minutes.

## Prerequisites

- **Rhino 8** (Windows)
- **Python 3.10+** (the installer detects `python`, `python3`, or `py -3` automatically)
- **[Claude Code](https://code.claude.com)** (recommended) — CLI, [Desktop app](https://code.claude.com/docs/en/desktop), or [VS Code extension](https://code.claude.com/docs/en/vs-code). All three support Rook's full feature set including hooks, plugins, and skills.

> **Note:** The older "Claude Desktop" chat app (claude.ai/download) only supports
> MCP tools — it does not support hooks, plugins, or skills. For the full Rook
> experience, use [Claude Code Desktop](https://code.claude.com/docs/en/desktop-quickstart) instead.

Other MCP clients ([Codex CLI](https://developers.openai.com/codex/cli), Cursor, Windsurf) work for basic tool access but do not support Rook's Claude Code plugin features.

## Installation

1. Download the latest **Rook-Setup** installer from [GitHub Releases](https://github.com/bringfire/rook-release/releases).
2. Run the installer. Select components:
   - **Plugins** — Rhino 8 plugins (always installed)
   - **MCP Server** — Python MCP server + knowledge stores
   - **Chirp** — LLM-powered Grasshopper components (optional)
   - **Claude** — Auto-configure Claude Code & Claude Desktop
   - **Codex** — Auto-configure OpenAI Codex CLI (optional)
3. The installer requires Python 3.10+ on your system.
4. Restart Rhino.

## Verify Installation

### In Rhino
- RookNative starts automatically and binds to an OS-assigned port (check command line for "Rook HTTP server started")
- Run `ShowRookChat` to verify the plugin is loaded

### In Claude Code
```bash
claude
```

Rook is available globally — no need to be in the Rook directory.

Type `/mcp` — you should see `rook` with 250+ tools.

Test with:
- "Ping Rhino"
- "Create a red sphere at the origin"
- "What objects are in the document?"

## What Gets Installed

| Component | Location | Purpose |
|-----------|----------|---------|
| RookNative Plugin | `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` | C++ HTTP server inside Rhino |
| Rook Companion | Same directory | C# Grasshopper bridge + chat panel |
| MCP Server | `%LOCALAPPDATA%\Rook\app\mcp_server\` | Python MCP server — Claude ↔ Rhino bridge |
| Knowledge Stores | `%LOCALAPPDATA%\Rook\app\knowledge\` | 1,200+ GH component notes, 500+ patterns, command knowledge |
| Skills (Codex) | `%LOCALAPPDATA%\Rook\app\skills\` (copied to `~/.codex/skills/`) | Curated Rook skill set for Codex CLI |
| Chirp Adapter | `%LOCALAPPDATA%\Rook\app\chirp\` (installer) | LLM-powered Grasshopper components (optional) |
| Claude Code Config | `~/.claude.json` | Global MCP configuration (auto-generated) |
| Claude Desktop Config | `%APPDATA%\Claude\claude_desktop_config.json` | Desktop MCP configuration (auto-generated) |

## Optional Add-ons

| Add-on | Purpose | Install Separately |
|--------|---------|-------------------|
| **RookRoads** + **RoadCreator** | 3D road design via `/design-road` skill | Separate Rhino plugins — see their repos |
| **Chirp** | LLM-powered GH components | Included in installer if `../Chirp/` exists |

## Troubleshooting

### "rook" not found in Claude Code
- Re-run the installer to regenerate MCP config
- Or restart Claude Code

### "Connection refused" or timeout errors
- Make sure Rhino 8 is running
- Check that the plugin loaded: run `ShowRookChat` in Rhino
- Port is OS-assigned — the MCP server discovers native Rhino targets automatically via `%LOCALAPPDATA%\Rook\discovery\` files, and still reads legacy `%TEMP%\rook\` files

### Plugin not loading in Rhino
- Restart Rhino after installation
- Check `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` for files
- Run `_PlugInManager` and look for RookNative

### Installer says "Python not found"
- Install Python 3.10+ from [python.org](https://www.python.org/downloads/)
- Make sure "Add to PATH" is checked during Python installation

## Uninstall

Use Add/Remove Programs (Windows Settings → Apps).

## Next Steps

- Read [CLAUDE.md](CLAUDE.md) for usage rules and best practices
- Try `/design-grasshopper "a parametric tower"` for the full GH design cascade
- Try `/design-road` if you have RookRoads + RoadCreator installed
