# Agent Setup Guide

> **This file is for AI agents** (Claude Code, Codex CLI, Cursor, Windsurf, or any
> MCP-compatible client). If you are an AI agent helping a user set up Rook, follow
> these instructions exactly. If you are a human, see [QUICK_START.md](QUICK_START.md).

---

## Critical: Supported AI Clients

**Rook requires [Claude Code](https://code.claude.com/docs/en/overview)** (CLI,
[Desktop app](https://code.claude.com/docs/en/desktop), or
[VS Code extension](https://code.claude.com/docs/en/vs-code)). All three variants
share the same engine and support the full Rook feature set:
[hooks](https://docs.anthropic.com/en/docs/claude-code/hooks-guide),
[plugins](https://code.claude.com/docs/en/plugins),
[skills](https://code.claude.com/docs/en/plugins-reference),
and [MCP servers](https://code.claude.com/docs/en/desktop-quickstart).

**The older "Claude Desktop" chat app (claude.ai/download) is NOT sufficient.**
It only supports MCP servers — no hooks, no plugins, no skills. Users on that app
will get the nearly 400 MCP tools but none of the orchestration skills (`/design-grasshopper`,
`/plan-grasshopper`, `/execute-grasshopper`, `/design-road`, etc.) or the session-start
hook that loads Rook context. If the user is on the older Claude Desktop app, help them
install [Claude Code Desktop](https://code.claude.com/docs/en/desktop-quickstart) instead.

Other MCP-compatible clients (Codex CLI, Cursor, Windsurf) get the MCP tools.
Codex CLI also gets the packaged Rook skill set, but Claude-specific features
(hooks, plugins, Claude agents) remain Claude-only.

## What Is Rook

Rook is an MCP server that gives AI agents direct control over Rhino 3D and
Grasshopper. It exposes nearly 400 tools for geometry creation, parametric modeling,
scene analysis, and more. The agent communicates with Rook via the Model Context
Protocol (stdio). Rook communicates with Rhino via HTTP on localhost.

## Prerequisites

Before starting, verify the user has:

| Requirement | How to Check | Required |
|-------------|-------------|----------|
| **Claude Code** | CLI: `claude --version`, Desktop: app installed, VS Code: extension installed | Yes |
| **Rhino 8** (Windows) | `where rhinoceros` or ask the user | Yes |
| **Python 3.10+** | `python --version` or `python3 --version` or `py -3 --version` | Yes (installer) |

## Installation

1. Download the latest `Rook-Setup-<version>.exe` from:
   `https://github.com/bringfire/rook-release/releases`

2. Run the installer. It handles everything automatically:
   - Deploys Rhino plugins to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\`
   - Creates a managed Python venv at `%LOCALAPPDATA%\Rook\venv`
   - Installs the MCP server (`pip install -e`) into that venv
   - Writes MCP configuration for Claude Code, Claude Desktop, and Codex CLI
   - Copies knowledge stores and Codex skills

3. After install, the user must **restart Rhino**.

## MCP Configuration

After installation, the MCP server must be registered with the AI client. The
installer does this automatically. For manual setup or verification:

### Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "rook": {
      "type": "stdio",
      "command": "<path-to-python>",
      "args": ["-m", "rook"],
      "cwd": "<path-to-mcp_server-directory>",
      "env": {
        "PYTHONPATH": "",
        "PYTHONHOME": "",
        "ROOK_INSTALL_ROOT": "<install-root>",
        "ROOK_DATA_DIR": "<data-directory>",
        "ROOK_MODE": "release"
      }
    }
  }
}
```

Fill in the placeholders for your install:
- `<path-to-python>`: `%LOCALAPPDATA%\Rook\venv\Scripts\python.exe`
- `<path-to-mcp_server-directory>`: `%LOCALAPPDATA%\Rook\app\mcp_server`
- `<install-root>`: `%LOCALAPPDATA%\Rook\app`
- `<data-directory>`: `%LOCALAPPDATA%\Rook\data`
- `ROOK_MODE`: `release`

**The `env` block is required.** Without `ROOK_INSTALL_ROOT` and `ROOK_DATA_DIR`,
the server falls back to repo-root detection which fails for release installs.
`doctor.py` validates these keys on startup.

### Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`)

Same structure as above, nested under `"mcpServers"`.

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.rook]
command = "<path-to-python>"
args = ["-m", "rook"]
cwd = "<path-to-mcp_server-directory>"

[mcp_servers.rook.env]
PYTHONPATH = ""
PYTHONHOME = ""
ROOK_INSTALL_ROOT = "<install-root>"
ROOK_DATA_DIR = "<data-directory>"
ROOK_MODE = "release"
```

## Verification

After setup, verify the full stack is working:

### Step 1: Check MCP Server

In the AI client, run:
```
/mcp
```
Look for `rook` in the list. It should show nearly 400 tools.

### Step 2: Ping Rhino

Ask: "Ping Rhino" or call `rhino_ping`. Expected response: `"pong"`.

If this fails:
- Rhino 8 must be running with the RookNative plugin loaded
- Run `ShowRookChat` in the Rhino command line to verify the plugin is loaded
- The plugin binds to an OS-assigned port and writes a discovery file to `%TEMP%\rook\`
- The MCP server reads this discovery file to find the port

### Step 3: Test Geometry

Ask: "Create a red sphere at the origin with radius 5"

This exercises: MCP → Python server → HTTP bridge → C++ plugin → Rhino.

## Architecture (for agents)

```
AI Client (you)
    |
    | stdio (MCP protocol)
    v
Python MCP Server (rook-mcp)     nearly 400 tools
    |
    | HTTP localhost (OS-assigned port, discovered via %TEMP%/rook/)
    v
C++ Plugin (RookNative.rhp)      sole HTTP server inside Rhino
    |
    | P/Invoke callbacks
    v
C# Companion (Rook.rhp)          Grasshopper bridge + chat panel
    |
    v
Rhino 3D / Grasshopper
```

Key points:
- The C++ plugin is the **only** HTTP server. Port is OS-assigned (not configurable).
- The Python MCP server discovers the port by reading JSON files in `%TEMP%/rook/`.
- All geometry operations serialize through Rhino's UI thread. One operation at a time.
- Grasshopper operations go through the C# companion via P/Invoke — there is no direct GH API in C++.

## Python Dependencies

The MCP server (`rook-mcp`) requires Python 3.10+ and these packages (installed
automatically via `pip install -e`):

| Package | Purpose |
|---------|---------|
| `mcp>=1.0.0` | Model Context Protocol SDK |
| `httpx>=0.25.0` | Async HTTP client (talks to C++ plugin) |
| `dspy>=2.6.0` | Intent resolution and knowledge consolidation |
| `litellm>=1.0.0` | Model-agnostic LLM routing for agents |
| `mabwiser>=2.7.0` | Multi-armed bandit for knowledge retrieval |
| `python-dotenv>=1.0.0` | Environment variable loading |
| `aiohttp>=3.9.0` | Async HTTP server (chat service) |
| `networkx>=3.2` | Graph algorithms (scene graph) |
| `opencv-python>=4.8.0` | Vision processing |
| `numpy>=1.24.0` | Numerical computation |
| `Pillow>=10.0.0` | Image processing |

## Environment Variables (Optional)

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | Powers DSPy intent resolution and agent system | None (falls back to simpler lookup) |
| `ROOK_LOG_LEVEL` | Logging verbosity | INFO |
| `DSPY_MODEL` | Model for DSPy operations | `anthropic/claude-haiku-4-5-20251001` |
| `ROOK_PLANNER_MODEL` | Model for agent planner | `claude-sonnet-4-20250514` |
| `ROOK_WORKER_MODEL` | Model for agent workers | `claude-haiku-4-5-20251001` |

Set these in `mcp_server/.env` or as system environment variables.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `rook` not in `/mcp` list | MCP config missing or wrong path | Re-run installer, or manually add to `~/.claude.json` |
| `rhino_ping` returns error | Rhino not running or plugin not loaded | Start Rhino 8, run `ShowRookChat` to confirm plugin is loaded |
| "Connection refused" | Plugin port not discovered | Check `%TEMP%\rook\` for discovery JSON files |
| pip install fails | Python <3.10 or missing dependencies | Verify `python --version` is 3.10+ |
| Tools timeout | Rhino showing a modal dialog | Dismiss any dialog in Rhino, then retry |
| GH component not found | Wrong component name/GUID | Use `gh_execute_intent` — it resolves GUIDs from the knowledge store |

## After Setup

Once verified, the agent has access to nearly 400 tools. Key tools to start with:

| Tool | Purpose |
|------|---------|
| `rhino_ping` | Verify connection |
| `rhino_execute_intent` | Create/modify Rhino geometry via natural language |
| `gh_execute_intent` | Create Grasshopper components via natural language |
| `gh_snapshot` | Read the current Grasshopper canvas state |
| `gh_edit` | Modify the Grasshopper canvas atomically |
| `rhino_objects` | List objects in the Rhino document |
| `knowledge_query` | Query the knowledge graph for commands/patterns |

For full tool documentation, call `/mcp` in the AI client to list all nearly 400 tools
with descriptions.
