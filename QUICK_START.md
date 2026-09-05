# Rook Quick Start

Get AI controlling Rhino 3D in 5 minutes.

## Prerequisites

- **Rhino 8** (Windows)
- A compatible MCP client, such as **[Claude Code](https://code.claude.com)** or **[Codex](https://developers.openai.com/codex/cli)**

The Windows installer includes the MCP server's CPython 3.11.9 runtime and the
manifest-verified Prime runtime used by embedded RookChat. No separate Prime,
Node, Bun, `uv`, or system Python installation is required. Claude Code can add
Rook's skills and session hook from the public marketplace plugin; the installer
supplies curated Codex skills. Other compatible clients can use the MCP tools their
configured profile admits.

## Installation

1. Download the latest **Rook-Setup** installer from [GitHub Releases](https://github.com/bringfire/rook-release/releases).
2. Run the installer. Select components:
   - **Plugins** — Rhino 8 plugins (always installed)
   - **MCP Server** — Python MCP server + knowledge stores
   - **Chirp** — LLM-powered Grasshopper components (optional)
   - **Claude** — Auto-configure Claude Code & Claude Desktop
   - **Codex** — Auto-configure OpenAI Codex CLI (optional)
3. No system Python installation is required.
4. Restart Rhino.

## Verify Installation

### In Rhino
- RookNative starts automatically and binds to an OS-assigned port (check command line for "Rook HTTP server started")
- Run `ShowRookChat` to verify the plugin is loaded

### In your MCP client

Inspect the client's MCP server list and confirm that `rook` is connected. The tool
catalog varies by client profile; Codex uses progressive discovery for tools outside
its lean catalog.

Test with:
- "Ping Rhino"
- "Create a red sphere at the origin"
- "What objects are in the document?"

## What Gets Installed

| Component | Location | Purpose |
|-----------|----------|---------|
| RookNative Plugin | `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` | C++ HTTP server inside Rhino |
| Rook Companion | Same directory | C# Grasshopper bridge + chat panel |
| MCP Server | `%LOCALAPPDATA%\Rook\app\mcp_server\` | Python MCP server — assistant ↔ Rhino bridge |
| Prime runtimes | `%LOCALAPPDATA%\Rook\app\prime\runtimes\<runtime-id>\` | Immutable, manifest-verified RookChat agent runtime |
| RookChat data | `%LOCALAPPDATA%\Rook\data\rookchat\acp\v1\` | Prime sessions, durable associations, bounded presentation, and open claims |
| Knowledge Stores | `%LOCALAPPDATA%\Rook\app\knowledge\` | 1,200+ GH component notes, 500+ patterns, command knowledge |
| Skills (Codex) | `%LOCALAPPDATA%\Rook\app\.agents\skills\` (copied to `~/.codex/skills/`) | Curated Rook skill set for Codex CLI |
| Chirp Adapter | `%LOCALAPPDATA%\Rook\app\chirp\` (installer) | LLM-powered Grasshopper components (optional) |
| Claude Code Config | `~/.claude.json` | Global MCP configuration (auto-generated) |
| Claude Desktop Config | `%APPDATA%\Claude\claude_desktop_config.json` | Desktop MCP configuration (auto-generated) |

## Optional Add-ons

| Add-on | Purpose | Install Separately |
|--------|---------|-------------------|
| **Chirp** | LLM-powered GH components | Included in installer if `../Chirp/` exists |

## Use Embedded RookChat

Run `ShowRookChat` in Rhino. Prime owns authentication. If RookChat reports that
authentication is missing, open Prime interactively and run `/login` there; `/login`
is not available inside the ACP panel. RookChat does not accept or persist
credentials.

New conversations may request a fully qualified model and supported reasoning
level. The selection becomes read-only after creation, and reopen restores Prime's
persisted settings without another override. The first IPython/Rook tool call may
take longer and require internet access while Prime prepares its kernel.

The panel accepts up to 8 images, 16 MiB decoded per image, and 32 MiB decoded per
turn. Original image bytes are live-only. Reopened history retains filename, MIME
type, dimensions, byte count, and SHA-256, and says the preview is unavailable.

Presentation history is bounded to 4 MiB per turn, 64 MiB per conversation, and
256 complete turns. When old turns are evicted, the panel states that earlier
presentation history was omitted; Prime still retains the authoritative
conversation state. Thought content is never persisted in the presentation cache.

## Troubleshooting

### "rook" not found in the MCP client
- Re-run the installer to regenerate MCP config
- Restart the MCP client

### "Connection refused" or timeout errors
- Make sure Rhino 8 is running
- Check that the plugin loaded: run `ShowRookChat` in Rhino
- Port is OS-assigned — the MCP server discovers native Rhino targets automatically via `%LOCALAPPDATA%\Rook\discovery\` files, and still reads legacy `%TEMP%\rook\` files

### Plugin not loading in Rhino
- Restart Rhino after installation
- Check `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` for files
- Run `_PlugInManager` and look for RookNative

### RookChat says `session_recovery_required`
The service did not observe the directly owned Prime child exit, so the durable
claim remains and reopen/delete fail closed. Do not remove the claim manually;
automatic crash recovery is intentionally deferred.

### RookChat says `target_unavailable`
The immutable Rook/Rhino target is unavailable. A new conversation is required to
target a different Rhino document. Changing Grasshopper definitions is supported
within a conversation through explicit open/new operations and document-ID checks.

## Uninstall

Use Add/Remove Programs (Windows Settings → Apps).

## Next Steps

- Read [AGENT_SETUP.md](AGENT_SETUP.md) for usage rules and verification guidance.
- For Claude Code skills and the session hook, run `/plugin marketplace add bringfire/rook-release`, then `/plugin install rook@rook`.
- For a clear, bounded build, use `/execute-grasshopper` directly; it performs a fresh live-state preflight before mutation.
- For an ambiguous or open-ended brief, use `/design-grasshopper` to resolve intent and success criteria without mutation.
- For large, destructive, cross-session, or high-risk work, use the optional `/plan-grasshopper` stage to create a durable review artifact before execution.
