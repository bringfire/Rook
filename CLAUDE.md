# Rook — AI Agents for Rhino & Grasshopper

> An agent platform that lets AI operate directly inside Rhino 3D
> and Grasshopper. The Python MCP surface is lifecycle-admitted and profile-filtered; `test_server_tool_profiles.py` is the authoritative count contract. Works with any LLM provider.

---

## Start Here

```
1. Run /mcp - look for "rook"
2. Call rhino_ping - should return "pong"
3. You're connected.
```

**Key docs (load only when needed):**
- `docs/CURRENT_ARCHITECTURE.md` - Canonical architecture description (~150 lines)
- `docs/AGENT_ARCHITECTURE.md` - Agent system, intent runtime, chat service (~400 lines)
- `docs/ONBOARDING_NEW_CLAUDE.md` - Quick decision tree (~175 lines)
- `docs/TROUBLESHOOTING.md` - Common issues and recovery (~525 lines)

---

## Philosophy

### The Knowledge Store is Not a Lookup Table

The knowledge store contains **components, recipes, and patterns** extracted from real Grasshopper definitions. It's a **semantic graph of composable primitives**, not a database of finished solutions.

When you query for "spiral staircase," you won't find a spiral staircase. You'll find helix patterns, point-sequence patterns, trig patterns, pipe/sweep patterns — and their links to each other. **Your job is to compose them.**

When a user asks for something not directly in the store:
1. **Query for related concepts** — linked neighborhoods surface relevant primitives
2. **Understand each primitive** — components, wiring patterns, gotchas
3. **Compose** — combine primitives to achieve the intent
4. **Bridge the gap** — domain knowledge about how things work together

### Record Corrections, Not Successes

When `correction_detected: true` appears in tool output, call `knowledge_record`. The store learns from failure, not routine success.

---

## Primary Tools

The Python MCP surface is lifecycle-admitted and profile-filtered; `test_server_tool_profiles.py` is the authoritative count contract. Two paths matter most.

### For Grasshopper: prefer the batch path — `gh_snapshot` → `gh_edit`

**This is the default, fastest, most reliable way to work on the canvas.**

1. `gh_snapshot` — read the entire canvas in ONE call (components, wires, groups,
   errors, data previews) and get back an `epoch`.
2. `gh_edit` — apply one bounded, logically related batch, passing that `epoch`:
   create → disconnect → delete → set_values → connect → groups.

```python
snap = gh_snapshot()                       # batch read; returns epoch + short IDs
gh_edit(epoch=snap["epoch"], create=[...], connect=["T1.O0>C2.I1"], set_values=[...])
```

One request, ordered non-transactional mutations, at most one post-mutation solve request—not an all-or-nothing transaction.
Inspect `success`, `partial_success`, every operation outcome, `edit_summary`, and
the solve-scheduling fields. `gh_edit` does not return solved output previews inline;
after the solve has settled, verify the live canvas with a fresh `gh_snapshot` and
`gh_errors`. If a batch partially succeeds, reconcile the observed canvas and retry
only missing or failed operations—never blindly replay the entire batch.
Use this by default for creating, wiring, and editing definitions. `gh_undo`
reverses the last edit.

For an unfamiliar component, query `gh_library` or `gh_knowledge_query` first,
then pass the exact name or GUID to `gh_edit`. Follow every mutation with
`gh_snapshot` and `gh_errors`; use `gh_undo` or explicit cleanup when a partial
edit committed.

### For Rhino Geometry: rediscover, inspect, then use explicit routes

Typed routes — `rhino_create`, `rhino_transform`, `rhino_boolean`, `rhino_extrude`,
`rhino_loft`, `rhino_sweep`, … — are the preferred, validated, deterministic path.

When the operation is unfamiliar, rediscover the admitted tool surface and inspect
the document before choosing a route. If no typed route fits, use only a sanctioned,
fully scripted `rhino_command` after knowledge lookup and preflight, or a short
non-interactive `rhino_execute` script as the last resort. Verify the result with
the structured response plus `rhino_objects`, `rhino_geometry`, or the relevant
query tool.

### Everything Else

| Need | Tool |
|------|------|
| Query objects | `rhino_objects`, `rhino_geometry` |
| Direct knowledge lookup | `knowledge_query`, `gh_knowledge_query` |
| See what's failing | `gh_errors` |

For other tools, use `/mcp` to see the full list with descriptions.

### For LLM-Powered GH Components: Chirp

Chirp components are native Grasshopper nodes powered by language models. Use the
`chirp_create` tool or the `/chirp` skill to create them.

Available categories: `planner`, `interpreter`, `critic`, `narrator`, `classifier`,
`gate`, `editor`. Chain multiple Chirp components into reasoning cascades using
`/chirp-cascade`.

Chirp components wire into definitions like any other GH node — they take data in,
run LLM reasoning, and output structured results.

### Any LLM Provider

Rook uses LiteLLM for model routing. Works with Claude (Anthropic), GPT (OpenAI),
or local models via Ollama / LM Studio. Configure in `.env` files. The user chooses
their provider — never assume a specific model is available.

---

## Using the Knowledge Store

### Query Before You're Stuck

```python
# When you're uncertain about a command
knowledge_query(intent="create cone", depth="context")

# When something failed
knowledge_query(intent="create cone", depth="errors")
```

**Depth tiers:**
- `quick` (~20 tokens) - essential facts
- `context` (~50 tokens) - specific rules for your use case
- `errors` (~30 tokens) - what fails and why
- `raw` (~500+ tokens) - full patterns

Each knowledge note has a `links` field to related notes — follow them to find related primitives.

---

## Critical Rules

### Never Say "I Can't"

Rhino and Grasshopper are professional tools refined over decades. Basic operations always have solutions. If you can't accomplish something:
1. The solution exists — you haven't found it yet
2. Re-read tool descriptions completely
3. Query the knowledge store with different intents
4. Follow the linked neighborhoods

**Never tell the user to do it manually.** That's giving up.

### Use MCP Tools, Not HTTP

Never use curl or direct HTTP calls. The MCP tools handle request formatting and error handling.

### No Keyboard Automation

Never use PowerShell SendKeys or wscript.shell. This triggers security alerts.

### Prefer Typed Routes Over Scripts

Most geometry operations have dedicated typed endpoints (`rhino_create`, `rhino_transform`,
`rhino_boolean`, `rhino_extrude`, `rhino_loft`, `rhino_sweep`, etc.) that are safe and
return structured results. Rediscover the admitted surface and call the exact route directly.

`rhino_execute` and `rhino_command` have built-in error handling (script wrapper with
try/except, preflight validation, interactive detection with auto-cancel), so script
errors return structured JSON rather than freezing Rhino. However, typed routes are
still preferred — they validate inputs, track created objects, and avoid edge cases
where a Rhino command pops a native dialog (file chooser, confirmation prompt) that
blocks the UI thread with no programmatic recovery.

---

## Architecture

> **For contributors.** Users operating Rook through MCP tools can skip this section.

```
Claude Code (CLI)
       │
       │ MCP Protocol (stdio)
       ▼
MCP Server (Python)     ← mcp_server/src/rook/server.py  [stdio only, no HTTP]
       │
       │ HTTP (127.0.0.1, OS-assigned port via bridge.py instance discovery)
       ▼
C++ Native Plugin       ← src/RookNative/   [PRIMARY — all routes, OS-assigned port]
       │
       │ P/Invoke callbacks
       ▼
C# Companion Plugin     ← src/Rook/         [GH operations + chat panel, no HTTP server]
       │
       │ Spawns separate Python process
       ▼
Chat Server (aiohttp)   ← mcp_server/src/rook/agent/chat/service_main.py [own OS-assigned port]
       │
       ▼
Rhino 3D / Grasshopper
```

**Startup order:**
1. Claude Code launches `python -m rook` (via `.mcp.json`) → MCP server on stdio (no HTTP)
2. Rhino loads `RookNative.rhp` → HTTP on OS-assigned port, writes discovery file to `%TEMP%/rook/`
3. Rhino loads `Rook.rhp` (companion) → registers GH callbacks via P/Invoke, spawns chat server as separate Python process (own port, own discovery file in `%TEMP%/rook/`)
4. `bridge.py` discovers native instances lazily — filters for `pluginType: "native"` only

### Agents Do NOT Use MCP

Rook agents (Planner, Workers) call HTTP endpoints on `127.0.0.1:{discovered_port}` directly — they never go through MCP. Port is resolved via discovery files in `%TEMP%/rook/`. When designing new features, expose HTTP endpoints first (C++ handlers in `src/RookNative/`), then optionally wrap as MCP tools. Agents consume the HTTP layer, not MCP.

GH operations are an exception: C++ native proxies GH routes through P/Invoke callbacks into the C# companion → `GrasshopperHandler` methods.

### Knowledge Stores

| Store | Contents | Location |
|-------|----------|----------|
| UnifiedStore | ~1,230 notes (components, recipes, teaching, struggles) | `knowledge/gh/notes/` |
| PatternStore | ~520 raw extracted patterns | `knowledge/gh/patterns/` |
| SparseIndex | ~942 GUIDs, ~1,533 intents | `knowledge/gh/sparse_index.json` |
| CommandKnowledgeStore | 197 Rhino commands, 543 observations | `knowledge/commands/` |

### Key Files

| Component | Path |
|-----------|------|
| MCP Server | `mcp_server/src/rook/server.py` |
| HTTP Bridge | `mcp_server/src/rook/bridge.py` |
| Chat Server | `mcp_server/src/rook/agent/chat/server.py` |
| C++ Native Plugin | `src/RookNative/RookServer.cpp` |
| C# Companion Plugin | `src/Rook/RookPlugin.cs` |
| GH Callback Bridge | `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` |
| Knowledge Evolution | `mcp_server/src/rook/learning/knowledge_evolution.py` |
| GH Knowledge | `knowledge/gh/notes/` |
| Command Knowledge | `knowledge/commands/command_knowledge.json` |

---

## Troubleshooting

### MCP tools not available
Run `/mcp` in Claude Code, look for "rook". If missing, restart Claude Code from project directory.

### Rhino not responding
A modal dialog may be blocking Rhino. Check the Rhino window for any dialog box
and dismiss it, then try `rhino_ping`. If this happened after a scripted command,
report it — the typed route for that operation may be missing.

### Command creates 0 objects
Invalid inputs. Check coordinates, units, required options.

### GH component not found
Don't guess component names — GUIDs differ across installs. Look up the correct
GUID with `gh_knowledge_query` or `gh_library`, pass it to `gh_edit`, and verify
the solved graph with a follow-up `gh_snapshot`.

### Still stuck?
File an issue at https://github.com/bringfire/rook-release/issues

---

## Documentation Tiers

This document (CLAUDE.md) is **Tier 0** — loaded automatically, provides routing.

| Tier | Purpose | Docs |
|------|---------|------|
| **0** | Entry point, routing | `CLAUDE.md` (this file) |
| **1** | Quick references | `docs/ONBOARDING_NEW_CLAUDE.md`, `docs/CURRENT_ARCHITECTURE.md` |
| **2** | Architecture deep dive | `docs/AGENT_ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md` |

**Rule:** Don't load Tier 2 docs unless you need specific details.
