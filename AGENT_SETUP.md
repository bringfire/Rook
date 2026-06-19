# Agent Setup Guide

> **This file is for AI agents** (Claude Code, Codex CLI, Cursor, Windsurf, or any
> MCP-compatible client). If you are an AI agent helping a user set up Rook, follow
> these instructions exactly. If you are a human, see [QUICK_START.md](QUICK_START.md).

---

## Supported AI Clients

Rook works with any **MCP-capable** assistant. Two clients get the full guided
experience:

- **[Claude Code](https://code.claude.com/docs/en/overview)** (CLI,
  [Desktop app](https://code.claude.com/docs/en/desktop), or
  [VS Code extension](https://code.claude.com/docs/en/vs-code)) — recommended for the
  complete experience: the MCP tools plus the Rook **skills + session hook**, installed
  from the marketplace plugin (`/plugin marketplace add bringfire/rook-release` →
  `/plugin install rook@rook`). All three variants share the same engine and support
  hooks, plugins, skills, and MCP servers.
- **Codex CLI** — first-class: the MCP tools **plus** a curated set of the same Rook
  skills, installed for you by the Rook installer (to `~/.codex/skills`), alongside
  `AGENTS.md` guidance.

Other MCP-compatible clients (Cursor, Windsurf, and the older "Claude Desktop" chat
app at claude.ai/download) get the **nearly 400 MCP tools**, but not the orchestration
skills (`/design-grasshopper`, `/plan-grasshopper`, `/execute-grasshopper`,
`/design-road`, etc.) or the session-start hook — those are Claude Code (marketplace
plugin) and Codex (installer) features. For the guided workflows, use Claude Code or
Codex.

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

> **Don't have a CLI agent installed yet?** Use its official native installer (Windows):
>
> - **Claude Code** — PowerShell: `irm https://claude.ai/install.ps1 | iex` (or `winget install Anthropic.ClaudeCode`) · [quickstart](https://code.claude.com/docs/en/quickstart)
> - **Codex CLI** — PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"` (or `npm install -g @openai/codex`) · [repo](https://github.com/openai/codex)

## Developer Machine Convention

For source-tree development, use `main` as the shared source of truth and use task
branches only for isolated work. Do not maintain separate laptop and desktop source
branches.

Before a local deploy from source:

1. Pull current `main`.

   ```powershell
   git switch main
   git pull --ff-only origin main
   ```
2. Run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-dev-doctor.ps1
   ```

3. Close Rhino and any `python -m rook` process. To inspect or stop only Rook
   MCP Python processes, run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-mcp-processes.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-mcp-processes.ps1 -Stop
   ```

4. Deploy with the repo Python runtime:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
   ```

5. Restart Rhino and open Grasshopper.
6. Optionally run the developer-open live smoke flow:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke
   ```

Prepared dev machines must set `OCCT_ROOT` to the active OCCT build root. Native
builds no longer use a hardcoded OCCT fallback path; pass `/p:OcctRoot=...` only
when intentionally overriding the shell environment for one build.

To prove a second dev machine is ready, run the same sequence from a fresh shell
on current `main` and record:

- `rook-dev-doctor.ps1` summary and the `OCCT root source` line.
- Whether `rook-mcp-processes.ps1 -Stop` stopped stale MCP processes.
- `deploy-local-testing.ps1 -UseRepoVenv` result.
- The developer-open live smoke result after Rhino and Grasshopper are open.

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
