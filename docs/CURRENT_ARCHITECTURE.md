# Current Architecture

Updated: 2026-09-05

This file is the short canonical description of the live runtime architecture.

Active program sequencing is indexed in [Active Roadmaps](roadmaps/README.md).

## System Diagram

```
MCP Client (Claude Code, Claude Desktop, Codex CLI, Cursor, etc.)
       │
       │  MCP Protocol (stdio)
       ▼
Rook MCP Server (Python)          ← lifecycle-admitted MCP tools, knowledge graph, agent system
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

Embedded RookChat panel (C#)
       │ HTTP/NDJSON
       ▼
Python chat service              ← ACP process/connection, bounded presentation, durable association
       │ ACP stdio
       ▼
Bundled Prime runtime            ← reasoning, transcript, goals, compaction, model context
       │ service-owned MCP server declaration named "rook"
       └────────────────────────► Rook MCP Server (Python)
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
| Role | GH callback bridge, ACP-backed chat panel UI, managed capability evidence, and 4 Rhino commands |
| Commands | AIGumball, ShowRookChat, RestartRookChatService, UVBoxMapping |
| GH bridge | P/Invoke callbacks registered via `NativeGhBridgeRegistrar.cs` |
| Load mode | WhenNeeded (loaded by RookNative on demand) |

### Companion-backed routes

**By design** (Grasshopper has no C++ API):
- All `/gh/*` routes, Canvas Graph Protocol, GH canvas navigation

**By explicit exception** (native port crashed Rhino for block-definition internals):
- `/block/set-layers`, `/block/set-materials`, `/block/set-object-colors`, `/block/set-object-names`, `/block/set-object-user-strings`, `/block/replace-object-geometry`, `/block/transform-object`

Everything else is native-owned.

### Grasshopper component discovery and identity

Grasshopper-native `FindObjects()` proposes ordinary component candidates. Proxy GUID
and `sourceKind` own component-type identity, while the managed Grasshopper endpoint
resolves one names-or-GUID batch against one live component-server view. Compiled and
user-object provenance remain distinct. Python forwards the batch once, verifies ordered
correlation, and adds compatibility summaries; knowledge does not alter authoritative
discovery or metadata. After type selection, the existing `T*` and `C*` identities own
graph execution.

### Grasshopper authoring capability routing

Model-facing ordinary component creation (`gh_edit` and the active exploration
routes) applies one shared Python guard in canonical `call_tool()` after
containment/profile/meta enforcement and before target resolution or panel
document-context enrichment. Direct `ToolDispatcher` applies the same guard,
and the lower dispatcher repeats it as defense in depth. Requests for
the supported modern Python or C# script identities return a structured handoff
to `gh_create_script` (or its language alias); name and GUID selectors use the
same classifier. `chirp_create` also delegates its generated C# source to that
canonical script helper. The internal `/gh/create-component` bridge primitive
remains capability-neutral and is neither advertised nor directly dispatched to
models. A closed AST-backed literal-call inventory fails when a new direct raw
creation call is introduced without review; it does not claim to detect
indirect or dynamically constructed calls.

### Grasshopper solve-fenced behavioral acceptance

Covered terminal authoring routes retain the managed
`solve_readiness_receipt` for each confirmed solve-relevant commit. Behavioral
acceptance combines the latest eligible receipt in a complete caller-owned
authoring trace with a managed atomic solve/read fence, then evaluates the
resulting typed snapshot through a closed deterministic acceptance artifact:

```text
covered terminal authoring receipt
+ complete caller-owned trace custody
+ managed atomic solve/read fence
-> behaviorally admissible snapshot
-> deterministic artifact evaluation
```

Freshness is bounded to mutations present in the closed trace and the managed
receipt fence; it does not claim protection from unobserved out-of-band
changes. A later retained preparatory or legacy mutation invalidates an older
receipt until a newer covered terminal commit supplies one. Script helpers keep
the existing Python `script_receipt` for script-pipeline evidence and the
managed `solve_readiness_receipt` for solve/read authority as distinct values.

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
| Key subsystems | Intent runtime, Knowledge stores, Agent system, ACP chat service, DSPy consolidation, Chirp manager |

- Director is retired from MCP discovery, profiles, meta-tools, targeting, and internal-agent dispatch. Native `/director/*` routes and implementation modules remain temporarily preserved for disposition review; they are not a public or agent-callable capability.

`rook_tools_call` validates the untrusted target argument object against the target's
live top-level schema before re-entering dispatch. Unknown fields return
`invalid_arguments` and do not contact the target.

Future scene preview, timeline, rendering, and finalized-video export belongs in RookStudio. `rook2` remains a narrow Rhino connector/broker and is unchanged by this retirement.

### Agent System (`agent/`)

The agent package retains Planner, Worker, Guardian, and Conductor internals, but autonomous MCP creation entry points are lifecycle-contained. RookChat uses Prime over standard ACP and delivers the normal Rook MCP surface through a service-owned server declaration. See `AGENT_ARCHITECTURE.md` for retained internal-agent details.

| Component | Purpose |
|-----------|---------|
| RookAgent | Core LLM-powered agent loop with 4 knowledge seams |
| Planner | Opus-based task decomposition (read-only) → TaskSpec plan |
| Guardian | Per-agent trajectory monitor (stuck/loop/drift/budget detection) |
| Conductor | Fleet coordinator for parallel swarms (systemic issue detection) |
| IntentOrchestrator | Layered intent pipeline: plan → route → execute → reflect |

**Key principle:** Retained internal-agent modules call RookNative HTTP endpoints
directly via `bridge.py`; they do not re-enter MCP. RookChat is separate and gives
Prime the public Rook MCP contract. Native ports are resolved through discovery
files in the shared discovery root.

### RookChat (`agent/chat/` and `src/Rook/UI/Chat/`)

RookChat is a single ACP-backed implementation. ChatRunner is removed rather than
retained as a backend or fallback. The C# panel owns UI attachment and projects the
Python service's bounded NDJSON stream. The Python service owns the durable
conversation association, directly owned Prime process and ACP connection, prompt
correlation, cancellation request, bounded presentation cache, runtime identity,
and immutable Rook/Rhino binding. Prime owns reasoning, its authoritative
transcript, goals, compaction, model context, and semantic completion.

Each conversation uses one exact, manifest-verified Prime runtime. New
conversations read and validate `prime/current.json` once, then record that runtime
ID; reopen uses the recorded runtime. RookChat supplies a service-owned ACP MCP
declaration named exactly `rook`, injects the strictly decoded verified contents of
`rook-full/SKILL.md`, and excludes ambient Prime project resources. Prime owns
credentials. RookChat neither reads nor forwards Rook's legacy `.env` credentials;
users authenticate by opening Prime interactively and running `/login` there.

The conversation's Rook host-generation ID and Rhino document serial are immutable.
Grasshopper document identity is dynamic: document-scoped observations return a
canonical `ghDocumentId`, mutations require it as `expectedGhDocumentId`, and
explicit open/new transitions return the resulting active ID. This is optimistic
target concurrency, not a sandbox for authored code.

Durable ACP data resides under
`%LOCALAPPDATA%\Rook\data\rookchat\acp\v1`. Prime runtimes reside under
`%LOCALAPPDATA%\Rook\app\prime\runtimes\<runtime-id>`. Install, upgrade, repair,
and release rollback preserve conversation data and historical runtimes. A
retained-data uninstall preserves ACP data, but a normal uninstall may remove the
application payload and its Prime runtimes. After reinstall, a conversation whose
recorded runtime is absent returns `runtime_unavailable`; RookChat does not scan for
or substitute another runtime. An `open.claim` is created before Prime launch and
removed only after the directly owned child is observed exited. A crash therefore
fails closed with `session_recovery_required`; there is no automatic stale-claim
recovery.

The presentation cache is disposable and bounded: at most 4 MiB per projected turn,
64 MiB per conversation, and 256 retained complete turns. Eviction removes only a
contiguous oldest-turn prefix and displays an omitted-history marker. Thought
content and original image bytes are live-only. Reopened image entries retain
bounded metadata and explicitly report that the preview is unavailable.

### Intent Runtime (`learning/intent_*.py`)

The retained intent internals use a typed pipeline:

```
IntentPlanner (P1) → ExecutionPlan → SmartExecutor (P2) → ExecutionResult → TypedReflection (P3)
```

- **CapabilityRouter:** Maps ~95 operations directly to HTTP endpoints (fast path, no LLM)
- **Execution cascade:** direct_api → known_command → interactive (auto-escalation)
- **Failure layers:** 7 typed failure categories for targeted knowledge recording

### Tool Result Surface

The internal envelope and legacy text projection **are not interchangeable**. The legacy text seam lives in exactly one function — `_format_tool_result()` in `server.py`:

| Layer | Shape |
|-------|-------|
| **Internal** — `_call_tool_dispatch()` and every `*_result()` helper | envelope dict `{ "success": bool, "data": {...} }` |
| **Legacy text** — internal `server.call_tool()` and public MCP `CallToolResult.content` | success: `json.dumps(data)` — the **`data` only**; failure: `"Error: " + json.dumps(data)` for a dict payload, else `"Error: " + str(data)` |

A test or live harness reading `call_tool()` output therefore parses the success text as the **data itself** (e.g. `json.loads(text)["artifacts"]`), **not** `["data"]["artifacts"]`; for failures, strip the leading `Error: `, then parse the remainder as JSON when the payload is a dict, otherwise treat it as raw error text. Mistaking the internal envelope for the wire shape is a recurring footgun (it cost a ~13-run debugging detour in P6 Slice 1). The public success shape is load-bearing — agents may depend on success-text-being-`data` — so the contract is documented and centralized rather than changed. Shared parse helpers + a contract test that pins the formatter are tracked in issue #218.

For every public request-handler branch that completes with an ordinary Rook `{success, data}` envelope, MCP also returns:

- `structuredContent = {"success": success, "data": data}`;
- `isError = !success`.

The existing `TextContent` bytes remain unchanged. Structured content is additive, but truthful `isError` is a deliberate semantic behavior change for compliant MCP clients. SDK-generated schema-validation and pre-envelope exception results retain the SDK's existing result behavior. Internal Python callers of `server.call_tool()` continue receiving `list[TextContent]`.

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
