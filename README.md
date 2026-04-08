<h1 align="center">ROOK</h1>

<p align="center">
  <img src="docs/Images/Rook_02.png" alt="Rook Logo" width="345">
</p>

<p align="center">
  <strong>AI-powered bridge for Rhino 3D and Grasshopper via the Model Context Protocol</strong>
</p>

<p align="center">
  264 MCP tools &bull; Intent-based execution &bull; Self-improving knowledge graph &bull; Model-agnostic
</p>

<p align="center">
  <a href="https://github.com/bringfire/Rook/releases"><strong>Download Latest Release</strong></a>
</p>

---

> **AI Agent?** If you are an AI agent helping a user set up Rook, read
> **[AGENT_SETUP.md](AGENT_SETUP.md)** — it has machine-readable instructions,
> dependency lists, config templates, and verification steps designed for you.
> **Rook requires [Claude Code](https://code.claude.com)** (CLI, Desktop app, or
> VS Code extension) — not the older Claude Desktop chat app which lacks hooks,
> plugins, and skills support.

Rook connects any MCP-compatible AI client to Rhino 3D and Grasshopper, enabling conversational CAD workflows. Create geometry, build parametric Grasshopper definitions, run analysis, capture viewports, and manage documents — all through natural language.

## Quick Start

```
1. Download the latest release installer, or clone the repo for a dev bootstrap
2. Release install: run the Windows installer
3. Source bootstrap: run install.ps1 from the repo root
3. Open Rhino 8
4. In your MCP client, say: "Ping Rhino" → should return "pong"
5. Try: "Create a red sphere at the origin with radius 5"
```

See [QUICK_START.md](QUICK_START.md) for detailed installation instructions.

## Architecture

```
MCP Client (Claude Code, Claude Desktop, Codex CLI, Cursor, etc.)
       │
       │  MCP Protocol (stdio)
       ▼
Rook MCP Server (Python)          ← 264 tools, knowledge graph, agent system
       │
       │  HTTP (127.0.0.1, OS-assigned port via discovery)
       ▼
RookNative (C++ plugin)           ← sole HTTP server, 198 routes, 34 handlers
       │
       │  P/Invoke callbacks
       ▼
Rook Companion (C# internal)     ← GH bridge + chat panel, no HTTP server
       │
       ▼
Rhino 3D / Grasshopper
```

| Layer | Role |
|-------|------|
| **RookNative (C++)** | The sole Rhino plugin and sole HTTP server. 198 routes across 34 handlers covering geometry, documents, scene graph, gumball, export, blocks, analysis, curves, meshes, SubD, and more. OS-assigned port discovered via `%TEMP%/rook/` JSON files. |
| **Managed Companion (C#)** | Loaded by RookNative. Grasshopper routes pass through a P/Invoke callback bridge — no separate HTTP server. Also hosts the embedded chat panel. |
| **MCP Server (Python)** | Translates 264 MCP tool calls into HTTP requests. Houses the knowledge graph, DSPy-based intent runtime (plan → route → execute → reflect), session recording, and the multi-agent system. Works with any MCP client. |
| **Knowledge Graph** | Self-improving store of 196 Rhino command patterns (543+ observations) and 924 Grasshopper components (1,400+ intents). Powers intent-based execution and correction detection. |
| **Scene Graph** | Real-time spatial intelligence — shadow graph of all Rhino objects with shape classification, bounding-box metrics, and 8 spatial relationship types. Background thread with lock-free immutable snapshots. |

## Key Features

### Rhino Geometry (90+ tools)

Full programmatic control over Rhino's geometry engine:

| Category | Capabilities |
|----------|-------------|
| **Creation** | Point, Line, Polyline, Curve, Circle, Arc, Ellipse, Rectangle, Box, Sphere, Cylinder, Cone, Torus, Surface, Extrusion, Loft, Sweep |
| **Transforms** | Move, Rotate, Scale, Mirror, Copy |
| **Booleans** | Union, Difference, Intersection |
| **Topology** | Fillet, Chamfer, Offset, Trim, Split, Project, Pull |
| **SubD** | Box, Sphere, Cylinder, from Mesh/Surface, Subdivide, Crease, convert to Brep/Mesh |
| **Mesh** | From Brep, primitives, Boolean, Reduce, QuadRemesh, Repair, Smooth, Weld/Unweld |
| **Blocks** | 19 tools — Create, Insert, Explode, Delete, Rename, Link/Unlink, Nested queries |
| **Analysis** | Area, Volume, Length, Curvature, Draft angle, Closest point, Normals, Topology queries |
| **Materials** | Create, assign, modify materials and textures |
| **Import/Export** | DWG, DXF, OBJ, STL, 3DM, STEP, IGES |

### Grasshopper Automation (70+ tools)

Build and manipulate parametric definitions entirely through AI:

- **Intent-based creation** — Describe what you want; Rook resolves component GUIDs from a catalog of 924 components and auto-wires inputs
- **Full canvas control** — Create, connect, disconnect, delete, move, group, cluster components
- **Value manipulation** — Set slider values, panel text, and Python 3 script source code
- **References** — Set and clear geometry references from Rhino to GH
- **Inspection** — Query canvas state, component I/O, connections, errors, solution status
- **Session recording** — Track every GH operation with success/failure for learning

### Grasshopper Design Cascade (Claude Code Plugin)

A 4-skill workflow for building complex Grasshopper definitions:

```
/design-grasshopper "parametric facade with attractor points"
```

| Phase | Skill | What happens |
|-------|-------|-------------|
| **Design** | `/design-grasshopper` | Explores knowledge store + scene, asks clarifying questions, produces a validated design doc |
| **Plan** | `/plan-grasshopper` | Converts design to exact MCP tool call batches with GUID lookups and canvas positions |
| **Execute** | `/execute-grasshopper` | Runs tool calls with `gh_solve` + `gh_errors` checkpoints every 3-5 components |
| **Learn** | `/consolidate` | Updates the knowledge graph with patterns discovered during construction |

Each phase auto-cascades into the next. The design doc is the boundary object — it survives context windows and makes commitment explicit before any tool touches the canvas.

### Multi-Agent System

Spawn background AI agents that operate Rhino and Grasshopper autonomously:

| Tool | What it does |
|------|-------------|
| `spawn_agent` | Launch a worker agent for a specific task (runs in background) |
| `plan_and_execute` | Planner decomposes complex requests into subtasks, workers execute in parallel |
| `agent_status` | Monitor running agents (turn count, cost, active tools) |
| `agent_abort` | Cancel a running agent |

**Architecture:** Planner (Sonnet) decomposes → Workers (Haiku) execute → Guardian monitors for stuck loops / drift / budget → Conductor coordinates the fleet.

**Model-agnostic:** Agents use [litellm](https://github.com/BerriAI/litellm) — supports Anthropic, OpenAI, Ollama, LM Studio, and 100+ other providers.

> **Security Notice (2026-03-24):** LiteLLM PyPI versions `1.82.7` and `1.82.8` were [compromised with a credential-stealing payload](https://github.com/BerriAI/litellm/issues/24512). Both versions have been yanked from PyPI. Rook's dependency pin explicitly excludes them (`!=1.82.7,!=1.82.8`). If you installed either version, rotate all credentials on the affected machine immediately. See the [LiteLLM team's response](https://github.com/BerriAI/litellm/issues/24518) for status updates.

### Knowledge Graph

A self-improving system that learns from every interaction:

- **196 Rhino commands** with 543+ observations — correct syntax, modes, gotchas, and antipatterns
- **924 Grasshopper components** cataloged with full I/O parameters and GUIDs
- **DSPy + MABWiser** — Intent resolution ranked by success rate; 97% token reduction vs raw patterns
- **Correction detection** — Automatically detects when you fix a mistake and records the learning
- **Tiered retrieval** — `quick` (20 tokens), `context` (50), `errors` (30), `raw` (500+)

### Scene Graph — Spatial Intelligence

Real-time spatial intelligence that gives AI agents a structured understanding of 3D scenes:

| Feature | Description |
|---------|-------------|
| **Object Classification** | Automatic shape classification (vertical-planar, horizontal-slab, thin-vertical, compact, etc.) |
| **Spatial Relationships** | 8 types: `supports`, `contains`, `adjacent`, `near`, `above`, `intersects`, `inside`, `surrounds` |
| **Domain Profiles** | Pluggable labeling — `general` and `architecture` profiles (wall, floor, column, beam, slab, etc.) |
| **Viewport Overlay** | Color-coded relationship lines and floating classification labels |

### Additional Capabilities

| Feature | Description |
|---------|-------------|
| **UV Mapping** | 4 tools (box, planar, cylinder, sphere) with auto-orientation and unit-aware scale |
| **Game Export** | Rhino-to-Unreal pipeline via Datasmith — semantic tagging, validation, manifest export |
| **AI Gumball** | Persistent transform tracker that hooks into Rhino's selection system |
| **Viewport Capture** | AI can "see" the model — any named view, any display mode, configurable resolution |
| **Session Recording** | Every command and GH operation recorded with full parameters — export as JSON or Markdown |
| **Embedded Chat** | Dockable chat panel inside Rhino with streaming responses and full tool access |

## Installation

### Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Rhino** | 8.x | Windows only (macOS planned) |
| **An MCP client** | Latest | Claude Code, Claude Desktop, Codex CLI, Cursor, Windsurf, etc. |

**Python 3.10+ required for the Windows installer.** The installer detects existing Python (`python`, `python3`, or `py -3`) and uses it to set up a managed MCP server environment. If you don't have Python, install it from [python.org](https://www.python.org/downloads/) first and make sure "Add to PATH" is checked. (If you prefer a zero-Python-prerequisite path, the source script installer `install.ps1` uses [uv](https://docs.astral.sh/uv/) to bootstrap Python automatically — see "Bootstrap from Source" below.)

### Install from Release

1. Download the latest release from [**GitHub Releases**](https://github.com/bringfire/Rook/releases)
2. Run the Windows installer (`Rook-Setup-<version>.exe`)

The installer automatically:
- Creates a managed Python venv under `%LOCALAPPDATA%\Rook\venv` using your system Python
- Copies the Rhino plugins to the correct location
- Writes user-scope MCP configuration for:
  - Claude Code: `~/.claude.json`
  - Claude Desktop: `%APPDATA%\Claude\claude_desktop_config.json`
  - Codex CLI: `~/.codex/config.toml`
- Copies skills to:
  - Claude Code: `~/.claude/skills/`
  - Codex: `~/.agents/skills/`

3. **Restart Rhino** and your MCP client
5. In your MCP client, type `/mcp` — you should see `rook` with 264 tools

### Bootstrap from Source

```powershell
git clone https://github.com/bringfire/Rook.git
cd Rook
powershell -ExecutionPolicy Bypass -File install.ps1
```

Source bootstrap automatically:
- Creates a repo-local venv at `mcp_server/.venv`
- Writes repo-scoped MCP config for Claude Code at `.mcp.json`
- Writes repo-scoped Codex config at `.codex/config.toml`
- Leaves user-scope Claude/Codex config untouched by default

Use `install.ps1 -UserConfig` only when you explicitly want the repo bootstrap to also write user-scope Claude Code and Codex config.

**For agents:** `install.ps1 -DryRun -Json` checks prerequisites with zero side
effects. `-RequireNative` fails hard if C++ toolchain is missing. See
[BUILDING.md](BUILDING.md) for the full flag reference and summary file contract.

### Install Design Cascade Skills

The Grasshopper design cascade uses documented skill locations:
- Release installs copy skills to `~/.claude/skills/` and `~/.agents/skills/`
- Source checkouts expose the repo skills from `.claude/skills`

The old plugin marketplace path is optional and is no longer required for core install correctness.

### Building from Source

<details>
<summary>Click to expand</summary>

```powershell
git clone https://github.com/bringfire/Rook.git
cd Rook

# Run the bootstrap script — it builds plugins and sets up repo-local MCP config
powershell -ExecutionPolicy Bypass -File install.ps1
```

The C++ native plugin (`src/RookNative/`) requires Visual Studio 2022 with the C++ Desktop workload and MFC. The C# companion (`src/Rook/`) requires .NET Framework 4.8. See **[BUILDING.md](BUILDING.md)** for the complete build chain with exact versions, flags, and troubleshooting.

</details>

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `rook` not found in MCP client | Re-run the installer or bootstrap script to regenerate the canonical config for your mode, then restart your MCP client |
| "Connection refused" errors | Ensure Rhino 8 is running with the plugin loaded; verify with `rhino_ping` |
| Plugin not loading in Rhino | Check `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\` |

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for more.

## Project Structure

```
Rook/
├── src/RookNative/              # C++ Rhino plugin (sole HTTP server)
│   ├── Handlers/                # 34 handler files (198 routes)
│   ├── RookServer.cpp           # HTTP server (cpp-httplib, OS-assigned port)
│   └── CMainThreadDispatcher.*  # Rhino UI thread serialization
│
├── src/Rook/                    # C# companion (GH bridge + chat panel)
│   ├── InternalBridge/          # P/Invoke callback bridge for GH routes
│   └── UI/Chat/                 # Embedded chat panel (Eto)
│
├── mcp_server/src/rook/         # Python MCP server
│   ├── server.py                # 264 MCP tool definitions
│   ├── agent/                   # Multi-agent system (Planner/Worker/Guardian)
│   └── learning/                # Knowledge stores + DSPy evolution
│
├── knowledge/                   # Persistent knowledge stores
│   ├── gh/                      # 924 GH components, 231 patterns
│   └── commands/                # 196 Rhino commands, 543+ observations
│
├── .claude/skills/              # Skills (copied to user skill dirs for both Claude Code and Codex on release install)
│   ├── design-grasshopper/      # Phase 1: Collaborative design
│   ├── plan-grasshopper/        # Phase 2: Tactical tool call plan
│   ├── execute-grasshopper/     # Phase 3: Batched execution
│   └── consolidate/             # Phase 4: Knowledge consolidation
│
├── installer/                   # Inno Setup installer source
├── install.ps1                  # PowerShell installer (Windows)
├── install.sh                   # Shell installer (macOS/Linux, MCP only)
└── docs/                        # Documentation
```

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor guide and [CLAUDE.md](CLAUDE.md) for architecture details.

## License

MIT License

## Acknowledgments

- Built with [RhinoCommon](https://developer.rhino3d.com/guides/rhinocommon/) and [cpp-httplib](https://github.com/yhirose/cpp-httplib)
- Uses [Model Context Protocol](https://modelcontextprotocol.io/)
- Knowledge system powered by [DSPy](https://github.com/stanfordnlp/dspy) and [MABWiser](https://github.com/fidelity/mabwiser)
- Agent system powered by [litellm](https://github.com/BerriAI/litellm)
