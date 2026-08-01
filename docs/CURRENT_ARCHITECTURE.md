# Current Architecture

Updated: 2026-06-05

This file is the short canonical description of the live runtime architecture.

## System Diagram

```
MCP Client (Claude Code, Claude Desktop, Codex CLI, Cursor, etc.)
       │
       │  MCP Protocol (stdio)
       ▼
Rook MCP Server (Python)          ← lifecycle-admitted MCP tools, knowledge graph, agent system
  │         │
  │         │ HTTP (127.0.0.1, OS-assigned port via discovery file)
  │         ▼
  │    Chat Server (aiohttp) — auto-started inside MCP server
  │
  │ HTTP (127.0.0.1, OS-assigned port via bridge.py instance discovery)
  ▼
RookNative (C++ plugin)           ← sole HTTP server, 263 routes, 42 handlers
       │
       │ P/Invoke callbacks
       ▼
Rook Companion (C# plugin)       ← GH bridge + chat/panel UI + internal status evidence, no HTTP server
       │
       ▼
Rhino 3D / Grasshopper
```

## Public Surface

- `RookNative` is the **only** public Rhino plugin and the **only** HTTP surface
- All ports are OS-assigned (port 0) — discovered via JSON files in the shared discovery root
- MCP clients and internal Python tooling target the discovered native instance

## C++ Native Plugin (`src/RookNative/`)

| Fact | Value |
|------|-------|
| HTTP routes | 292 registrations (263 unique paths) across 42 handler files |
| HTTP library | cpp-httplib, port 0 (OS-assigned) |
| Thread pool | 8 threads (capped) |
| Thread dispatch | CMainThreadDispatcher — all Rhino API calls serialize through UI thread |
| Discovery file | `%LOCALAPPDATA%\Rook\discovery\instance-{PID}-native.json` by default; MCP also reads legacy `%TEMP%\rook` records |
| Key subsystems | Scene graph (CRhinoEventWatcher + ON_RTree), AI Gumball (WH_MOUSE hook), Session recording, Command interactive (WndProc subclass), GH proxy (P/Invoke to C# companion) |

## C# Managed Companion (`src/Rook/`)

The companion is **internal** — not a separate public plugin surface.

| Fact | Value |
|------|-------|
| HTTP server | **None** |
| Role | GH callback bridge, chat/panel UI, managed capability evidence, and 4 Rhino commands |
| Commands | AIGumball, ShowRookChat, RestartRookChatService, UVBoxMapping |
| GH bridge | P/Invoke callbacks registered via `NativeGhBridgeRegistrar.cs` |
| Load mode | WhenNeeded (loaded by RookNative on demand) |

### Companion-backed routes

**By design** (Grasshopper has no C++ API):
- All `/gh/*` routes, Canvas Graph Protocol, GH canvas navigation

**By explicit exception** (native port crashed Rhino for block-definition internals):
- `/block/set-layers`, `/block/set-materials`, `/block/set-object-colors`, `/block/set-object-names`, `/block/set-object-user-strings`, `/block/replace-object-geometry`, `/block/transform-object`

Everything else is native-owned.

## Runtime Capability Discovery

`RookNative` exposes `GET /capabilities` as the public runtime capability discovery surface. The endpoint reports declared capability domains, current runtime state, reason codes, routes, operations, diagnostics, and evidence. It is descriptive in Phase 1: it does not move route ownership, change companion loading, change installer layout, or make the managed companion public.

Native discovery JSON keeps the legacy `capabilities.ghProvider` and `capabilities.ghRoutes` fields for compatibility. It also includes `capabilities.liveEndpoint`, `capabilities.summaryKind: "bootstrap_snapshot"`, `capabilities.authoritative: false`, `capabilities.generatedUtc`, and `capabilities.domainSummary`. This summary is bootstrap/fallback metadata only. Clients use discovery to find `RookNative`, then call `GET /capabilities` for authoritative live readiness.

Managed companion domain evidence is internal. The companion writes it to its existing per-process runtime status file under the shared discovery root; `RookNative` remains the only public HTTP/discovery surface.

## Python MCP Server (`mcp_server/src/rook/`)

| Fact | Value |
|------|-------|
| MCP tools | Lifecycle-admitted through the `full`, `lean`, and `readonly` profiles |
| Other MCP profiles | Deprecated-interactive definitions are gated by default |
| Entry point | `python -m rook` (stdio transport) |
| HTTP bridge | `bridge.py` — discovers native plugin via `%LOCALAPPDATA%\Rook\discovery` by default and legacy `%TEMP%\rook` compatibility files |
| Key subsystems | Intent runtime, Knowledge stores, Agent system, Chat service, DSPy consolidation, Chirp manager |

- Director is retired from MCP discovery, profiles, meta-tools, targeting, and internal-agent dispatch. Native `/director/*` routes and implementation modules remain temporarily preserved for disposition review; they are not a public or agent-callable capability.

Future scene preview, timeline, rendering, and finalized-video export belongs in RookStudio. `rook2` remains a narrow Rhino connector/broker and is unchanged by this retirement.

### Agent System (`agent/`)

The agent package retains Planner, Worker, Guardian, and Conductor internals, but autonomous MCP creation entry points are lifecycle-contained. RookChat remains the active model-driven path and selects supported explicit tools. See `AGENT_ARCHITECTURE.md` for details.

| Component | Purpose |
|-----------|---------|
| RookAgent | Core LLM-powered agent loop with 4 knowledge seams |
| Planner | Opus-based task decomposition (read-only) → TaskSpec plan |
| Guardian | Per-agent trajectory monitor (stuck/loop/drift/budget detection) |
| Conductor | Fleet coordinator for parallel swarms (systemic issue detection) |
| ChatRunner | Interactive chat service for Rook panel (aiohttp, execution policy) |
| IntentOrchestrator | Layered intent pipeline: plan → route → execute → reflect |

**Key principle:** Agents call RookNative HTTP endpoints directly via `bridge.py` — they never go through MCP. Port is resolved via discovery files in the shared discovery root.

### Intent Runtime (`learning/intent_*.py`)

The retained intent internals use a typed pipeline:

```
IntentPlanner (P1) → ExecutionPlan → SmartExecutor (P2) → ExecutionResult → TypedReflection (P3)
```

- **CapabilityRouter:** Maps ~95 operations directly to HTTP endpoints (fast path, no LLM)
- **Execution cascade:** direct_api → known_command → interactive (auto-escalation)
- **Failure layers:** 7 typed failure categories for targeted knowledge recording

### Tool Result Surface

Two result shapes exist and **are not interchangeable**. The seam lives in exactly one function — `_format_tool_result()` in `server.py`:

| Layer | Shape |
|-------|-------|
| **Internal** — `_call_tool_dispatch()` and every `*_result()` helper | envelope dict `{ "success": bool, "data": {...} }` |
| **Public wire** — `call_tool()` → `list[TextContent]` | success: `json.dumps(data)` — the **`data` only**; failure: `"Error: " + json.dumps(data)` for a dict payload, else `"Error: " + str(data)` |

A test or live harness reading `call_tool()` output therefore parses the success text as the **data itself** (e.g. `json.loads(text)["artifacts"]`), **not** `["data"]["artifacts"]`; for failures, strip the leading `Error: `, then parse the remainder as JSON when the payload is a dict, otherwise treat it as raw error text. Mistaking the internal envelope for the wire shape is a recurring footgun (it cost a ~13-run debugging detour in P6 Slice 1). The public success shape is load-bearing — agents may depend on success-text-being-`data` — so the contract is documented and centralized rather than changed. Shared parse helpers + a contract test that pins the formatter are tracked in issue #218.

## Knowledge Stores

| Store | Location | Size |
|-------|----------|------|
| UnifiedStore (GH) | `knowledge/gh/notes/` | ~1,230 notes (component, recipe, teaching, struggle) |
| PatternStore (GH) | `knowledge/gh/patterns/` | ~520 raw patterns |
| CommandKnowledgeStore | `knowledge/commands/` | 197 Rhino commands, 543 observations |
| Sparse Index | `knowledge/gh/sparse_index.json` | 942 GUIDs, 1,533 intents |

## Port Discovery

All Rook services use OS-assigned ports. Native Rhino target discovery uses atomic JSON files in `%LOCALAPPDATA%\Rook\discovery` by default. MCP also reads legacy `%TEMP%\rook` records for compatibility with older producers.

| Service | Discovery file | Writer |
|---------|---------------|--------|
| Native plugin | `%LOCALAPPDATA%\Rook\discovery\instance-{PID}-native.json` | C++ plugin on startup |
| Chat service | `%TEMP%/rook/chat-service-{PID}.json` | Python chat server |

Stale files are cleaned up on startup by checking process liveness.

## MCP Client Configuration

| Client | Config file | Format |
|--------|------------|--------|
| Claude Code | Dev: `.mcp.json` in repo root; Release: `~/.claude.json` | JSON |
| Claude Desktop | `%APPDATA%/Claude/claude_desktop_config.json` | JSON |
| Codex CLI | Dev: `.codex/config.toml` in repo root; Release: `~/.codex/config.toml` | TOML |

Install modes are intentionally split:
- Dev bootstrap writes repo-scoped config by default and may write user config only when explicitly requested.
- Release install writes user-scoped config only.

Release MCP registrations also carry explicit runtime env:
- `ROOK_MODE=release`
- `ROOK_INSTALL_ROOT=<install payload root>`
- `ROOK_DATA_DIR=%LOCALAPPDATA%\Rook\data`

Dev bootstrap registrations carry:
- `ROOK_MODE=dev`
- `ROOK_INSTALL_ROOT=<repo root>`
- `ROOK_DATA_DIR=<repo root>\knowledge`

## Documentation Rule

If a document still describes the old public C# `Rook` plugin or `localhost:9876` as the main runtime architecture, it has been moved to `docs/archive/`. All active docs reflect this architecture.
