<h1 align="center">ROOK</h1>

<p align="center">
  <img src="docs/Images/Rook_02.png" alt="Rook Logo" width="345">
</p>

<p align="center">
  <strong>AI-powered bridge for Rhino 3D and Grasshopper via the Model Context Protocol</strong>
</p>

<p align="center">
  Lifecycle-admitted MCP tools &bull; Explicit typed execution &bull; Self-improving knowledge graph &bull; Model-agnostic
</p>

<p align="center">
  <a href="https://github.com/bringfire/rook-release/releases"><strong>Download Latest Release</strong></a>
</p>

---

> **AI Agent?** If you are an AI agent helping a user set up Rook, read
> **[AGENT_SETUP.md](AGENT_SETUP.md)** — it has machine-readable instructions,
> dependency lists, config templates, and verification steps designed for you.
> Rook works with compatible MCP clients. The installer supplies curated Codex
> skills; Claude Code skills and hooks are distributed through the public Rook
> marketplace plugin.

Rook connects any MCP-compatible AI client to Rhino 3D and Grasshopper, enabling conversational CAD workflows. Create geometry, build parametric Grasshopper definitions, design road networks, inspect BIM models, generate images and video, run analysis, capture viewports, and manage documents — all through natural language.

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
Rook MCP Server (Python)          ← lifecycle-admitted tools, knowledge graph, chat runtime
       │
       │  HTTP (127.0.0.1, OS-assigned port via discovery)
       ▼
RookNative (C++ plugin)           ← sole HTTP server, 263 routes, 42 handlers
       │
       │  P/Invoke callbacks
       ▼
Rook Companion (C# internal)     ← GH bridge + chat panel, no HTTP server
       │
       ▼
Rhino 3D / Grasshopper

Embedded RookChat panel
       │ HTTP/NDJSON
       ▼
Python chat service ── ACP stdio ──► Bundled Prime runtime
       ▲                                  │
       └──── service-owned `rook` MCP ────┘
```

| Layer | Role |
|-------|------|
| **RookNative (C++)** | The sole Rhino plugin and sole HTTP server. 263 routes across 42 handlers covering geometry, documents, scene graph, gumball, export, blocks, analysis, curves, meshes, SubD, annotations, materials, vision/media, BIM, and more. OS-assigned port discovered via `%LOCALAPPDATA%/Rook/discovery` JSON files, with legacy `%TEMP%/rook` compatibility reads. |
| **Managed Companion (C#)** | Loaded by RookNative. Grasshopper routes pass through a P/Invoke callback bridge — no separate HTTP server. Also hosts the embedded chat panel. |
| **MCP Server (Python)** | Defines the MCP schema source, applies lifecycle and profile admission, and translates admitted calls into HTTP requests. Houses the knowledge graph, DSPy consolidation, session recording, and chat runtime. Works with any MCP client. |
| **Knowledge Graph** | Self-improving store of 197 Rhino commands (543 observations) and 945 Grasshopper component notes (942 GUIDs, 1,533 intents) within ~1,230 total GH notes. Powers intent-based execution and correction detection. |
| **Scene Graph** | Real-time spatial intelligence — shadow graph of all Rhino objects with shape classification, bounding-box metrics, and 8 spatial relationship types. Background thread with lock-free immutable snapshots. |

## Key Features

### Rhino Geometry (~250 tools)

Full programmatic control over Rhino's geometry engine:

| Category | Capabilities |
|----------|-------------|
| **Creation** | Point, Line, Polyline, Curve, Circle, Arc, Ellipse, Rectangle, Box, Sphere, Cylinder, Cone, Torus, Surface, Extrusion, Loft, Sweep, Revolve, Pipe, Patch, Edge surface |
| **Transforms** | Move, Rotate, Scale, Mirror, Copy, Arrays (linear, polar, rectangular) |
| **Booleans** | Union, Difference, Intersection (Brep, mesh, and curve booleans) |
| **Topology** | Fillet, Chamfer, Offset, Trim, Split, Project, Pull, Blend |
| **SubD** | Box, Sphere, Cylinder, from Mesh/Surface, Subdivide, Crease, convert to Brep/Mesh |
| **Mesh** | From Brep, primitives, Boolean, Reduce, QuadRemesh, Repair, Smooth, Weld/Unweld |
| **Blocks** | 49 tools — Create, Insert, Explode, Delete, Rename, Link/Unlink, Nested queries, batch transform/replace/restyle, layer census, instance distribution |
| **Annotation** | Dimensions (linear, aligned, angular, radius, diameter), text, leaders, dots |
| **Layers & Materials** | Full layer CRUD + properties/visibility/locking; create, assign, modify materials and textures |
| **Analysis** | Area, Volume, Length, Curvature, Draft angle, Closest point, Normals, Topology queries |
| **Import/Export** | DWG, DXF, OBJ, STL, 3DM, STEP, IGES; Datasmith game export to Unreal |

### Grasshopper Automation (69 tools)

Build and manipulate parametric definitions entirely through AI:

- **Explicit component authoring** — Inspect the canvas, resolve exact component names/GUIDs from the catalog, apply bounded `gh_edit` batches, and verify the solved graph
- **Full canvas control** — Create, connect, disconnect, delete, move, align, distribute, group, cluster components
- **Scripting** — Create and edit Python 3 and C# script components, set pins, manage source
- **Value manipulation** — Set slider values, panel text, and parameter properties (flatten/graft/reverse)
- **References** — Set and clear geometry references from Rhino to GH
- **Canvas capture** — Focus, zoom-to-fit, and render the canvas to an image the AI can see
- **Inspection** — Query canvas state, component I/O, connections, errors, solution status
- **Recipes & patterns** — Save, replay, and learn reusable definitions from real `.gh` files
- **Session recording** — Track every GH operation with success/failure for learning

### Routed Grasshopper Workflow Skills

Choose the smallest stage that matches the work. A clear, bounded build goes directly to execution. An ambiguous or open-ended brief starts with read-only design. A durable plan is optional for large, destructive, cross-session, or review-sensitive work.

| Route | Skill | Boundary |
|-------|-------|----------|
| **Clarify** | `/design-grasshopper` | Read-only alternatives, constraints, preservation boundaries, and acceptance criteria |
| **Plan when useful** | `/plan-grasshopper` | Optional read-only structural baseline and bounded technical batches for review |
| **Build or modify** | `/execute-grasshopper` | Fresh live-state admission, execution-owned mutation, and result verification |

Skills return control to the user at each boundary; they do not automatically invoke the next stage.

### Chirp — LLM-Powered Grasshopper Components

Chirp components are native Grasshopper nodes with a language model embedded inside. They take data in, run LLM reasoning, and emit structured results — wiring into a definition like any other component.

- **7 categories** — `planner`, `interpreter`, `critic`, `narrator`, `classifier`, `gate`, `editor`
- **Single component** — `chirp_create` or the `/chirp` skill drops one reasoning node on the canvas
- **Reasoning cascades** — `/chirp-cascade` builds multi-component chains that fan out shared reasoning context across disciplines, including Wasp aggregation grammars

### RookBIM — Revit / BIM Inspection

Agentic inspection of live BIM models via RhinoInside. 8 `rookbim_*` tools let an agent query the active Revit document, list categories, inspect element parameters, and select/highlight elements — element-identity-aware, read-first.

### Image & Video Generation

Rook can both *see* and *generate* visual content:

- **Viewport capture** — Render any named view or display mode to an image the AI can reason over
- **RookVision artifacts** — Generated and captured images stored in an artifact store with roles, approval workflow, and a gallery
- **Video** — Render viewport/turntable video, manage generation jobs, and inspect status/estimate/cancel results
- **Model-agnostic generation** — A provider framework routes image/video generation across backends rather than hard-coding a single model

### Agent and Chat Runtime

The repository retains planner, worker, guardian, and conductor implementation
modules, but autonomous multi-worker coordination is suspended from the public
tool surface. Current clients rediscover the admitted catalog and have the
connected model call explicit tools directly.

Embedded RookChat is powered by the bundled Prime agent over standard ACP. There is
one implementation and no ChatRunner backend or fallback. Prime owns reasoning,
conversation history, goals, compaction, and model context. RookChat owns the
directly launched ACP connection, durable association, immutable Rhino target,
dynamic Grasshopper document checks, and bounded panel presentation. The full Rook
authoring surface remains available through a service-owned MCP server named
`rook`. The Prime runtime is a pinned, published artifact rather than repository
source; source builds fetch it with `scripts/prime/fetch-prime-runtime.ps1`
(see [BUILDING.md](BUILDING.md#prime-runtime-rookchat)).

**Model-agnostic internal workflows:** Retained non-chat agent and knowledge
workflows use [litellm](https://github.com/BerriAI/litellm), which supports
Anthropic, OpenAI, Ollama, LM Studio, and many other providers. RookChat model and
authentication handling belongs to Prime.

> **Security Notice (2026-03-24):** LiteLLM PyPI versions `1.82.7` and `1.82.8` were [compromised with a credential-stealing payload](https://github.com/BerriAI/litellm/issues/24512). Both versions have been yanked from PyPI. Rook's dependency pin explicitly excludes them (`!=1.82.7,!=1.82.8`). If you installed either version, rotate all credentials on the affected machine immediately. See the [LiteLLM team's response](https://github.com/BerriAI/litellm/issues/24518) for status updates.

### Knowledge Graph

A self-improving system that learns from every interaction:

- **197 Rhino commands** with 543 observations — correct syntax, modes, gotchas, and antipatterns
- **945 Grasshopper components** cataloged with full I/O parameters and GUIDs (1,533 indexed intents)
- **~1,230 GH knowledge notes** — components, recipes, teaching units, and recorded struggles, ~520 raw extracted patterns
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
| **Session Recording** | Every command and GH operation recorded with full parameters — export as JSON or Markdown |
| **Embedded Chat** | Dockable chat panel inside Rhino with streaming responses and full tool access |

## Installation

### Requirements

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Rhino** | 8.x | Windows only (macOS planned) |
| **An MCP client** | Latest | Claude Code, Claude Desktop, Codex CLI, Cursor, Windsurf, etc. |

The Windows installer includes a sealed, bundled CPython 3.11.9 runtime for the MCP server
and an exact manifest-verified Prime runtime with its pinned `uv` executable. A
system Python, Prime, Node, Bun, or separate `uv` installation is not required for
a release install.

### Install from Release

1. Download the latest release from [**GitHub Releases**](https://github.com/bringfire/rook-release/releases)
2. Run the Windows installer (`Rook-Setup-<version>.exe`)

The installer automatically:
- Creates the managed MCP environment under `%LOCALAPPDATA%\Rook\venv` using the bundled runtime
- Copies the Rhino plugins to the correct location
- Writes user-scope MCP configuration for:
  - Claude Code: `~/.claude.json`
  - Claude Desktop: `%APPDATA%\Claude\claude_desktop_config.json`
  - Codex CLI: `~/.codex/config.toml`
- Copies curated Codex skills to `~/.codex/skills/`
- Leaves Claude Code skills and hooks to the public marketplace plugin
- Installs and promotes the bundled Prime runtime used by RookChat

3. **Restart Rhino** and your MCP client
4. In your MCP client, inspect its MCP server list — `rook` should be connected. The admitted catalog depends on the configured client profile.

### Use RookChat

Run `ShowRookChat` in Rhino. Prime owns RookChat authentication: if authentication
is missing, open Prime interactively and run `/login` there. `/login` is not an ACP
command inside RookChat, and RookChat does not store or forward credentials.

For a new conversation, the panel can request a fully qualified Prime model and a
supported reasoning level. Those controls become read-only after creation. Reopen
passes no override, allowing Prime to restore the persisted conversation settings.
The first tool-bearing turn may take longer and require internet access while Prime
bootstraps its mutable kernel environment.

Conversation state and bounded presentation history live outside replaceable
application payloads. Release rollback does not switch backends; reinstalling the
ACP-capable release restores access to preserved ACP conversations.

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

The Grasshopper workflow uses client-specific distribution:
- Release installs copy curated Codex skills to `~/.codex/skills/`.
- Claude Code installs the Rook skills and session hook from the public marketplace plugin.
- Source checkouts retain `.agents/skills` and `.claude/skills` as development mirrors.

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
| RookChat reports missing authentication | Open Prime interactively and run `/login`; do not enter credentials in RookChat |
| RookChat reports `session_recovery_required` | A previous owner did not observe its Prime child exit. The conversation remains fail-closed pending an explicit recovery workflow; do not delete its claim manually. |
| RookChat reports `target_unavailable` | The bound Rhino host/document is unavailable or no longer matches the conversation. Start a new conversation for a different Rhino document. |
| Reopened image has no preview | Original image bytes are live-only; reopened history intentionally retains metadata rather than the image payload. |

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for more.

## Project Structure

```
Rook/
├── src/RookNative/              # C++ Rhino plugin (sole HTTP server)
│   ├── Handlers/                # 42 handler files (263 routes)
│   ├── RookServer.cpp           # HTTP server (cpp-httplib, OS-assigned port)
│   └── CMainThreadDispatcher.*  # Rhino UI thread serialization
│
├── src/Rook/                    # C# companion (GH bridge + chat panel)
│   ├── InternalBridge/          # P/Invoke callback bridge for GH routes
│   └── UI/Chat/                 # Embedded chat panel (Eto)
│
├── mcp_server/src/rook/         # Python MCP server
│   ├── server.py                # Raw schemas plus lifecycle/profile admission
│   ├── agent/                   # Chat runtime + retained agent implementation modules
│   └── learning/                # Knowledge stores + DSPy evolution
│
├── knowledge/                   # Persistent knowledge stores
│   ├── gh/                      # 945 GH components, ~1,230 notes, ~520 patterns
│   └── commands/                # 197 Rhino commands, 543 observations
│
├── .claude/skills/              # Claude marketplace skill payload mirrored from the authoritative agent skills
│   ├── design-grasshopper/      # Optional read-only clarification and design
│   ├── plan-grasshopper/        # Optional read-only technical plan
│   ├── execute-grasshopper/     # Owned mutation and verification
│   ├── chirp/ chirp-cascade/    # LLM-embedded GH components
│   └── ...                      # capture-convention, clean-layers, twisted-column, etc.
│
├── installer/                   # Inno Setup installer source
├── install.ps1                  # PowerShell installer (Windows)
├── install.sh                   # Shell installer (macOS/Linux, MCP only)
└── docs/                        # Documentation
```

## Support & Feedback

Rook is open source under the MIT License. Bug reports, questions and feature
ideas are welcome; pull requests are accepted by invitation, for issues marked
`accepted` or `help wanted`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
policy and [BUILDING.md](BUILDING.md) for building every component from source.

- **Bugs & feature requests** — [GitHub Issues](https://github.com/bringfire/Rook/issues)
- **Security** — [SECURITY.md](SECURITY.md) (please don't file public issues for vulnerabilities)
- **Email** — bringfiregames@gmail.com

## License

Rook is released under the **[MIT License](LICENSE)**.

Bundled third-party components keep their own licenses: the minimal LGPL-only
FFmpeg build in `third_party/ffmpeg`, the MIT-licensed Prime agent runtime
(`third_party/prime-agent`), the MIT-licensed `httplib` and `nlohmann/json`
sources under `src/RookNative/vendor`, and the OFL-licensed fonts under
`src/Rook/UI/Vision/Resources/fonts`. See the accompanying notices in each
directory.

## Acknowledgments

- Built with [RhinoCommon](https://developer.rhino3d.com/guides/rhinocommon/) and [cpp-httplib](https://github.com/yhirose/cpp-httplib)
- Uses [Model Context Protocol](https://modelcontextprotocol.io/)
- Knowledge system powered by [DSPy](https://github.com/stanfordnlp/dspy) and [MABWiser](https://github.com/fidelity/mabwiser)
- Agent system powered by [litellm](https://github.com/BerriAI/litellm)
