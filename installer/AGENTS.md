# Rook — AI Agents for Rhino & Grasshopper

> An agent platform that lets AI operate directly inside Rhino 3D
> and Grasshopper. nearly 400 MCP tools. Works with any LLM provider.

> **Using this file:** If your working directory is the Rook install folder
> (`%LOCALAPPDATA%\Rook`), this file loads automatically. Otherwise, copy it
> to your project root so your AI agent can use it as context when working
> with Rook. You can customize the copy with project-specific conventions
> (units, layer naming, etc.) — the Rook guidance below will still apply.

---

## Start Here

```
1. Run /mcp - look for "rook"
2. Call rhino_ping - should return "pong"
3. You're connected.
```

**Key docs (load only when needed):**
- `docs/ONBOARDING_NEW_CLAUDE.md` - Quick decision tree for tool selection (~175 lines)
- `docs/CURRENT_ARCHITECTURE.md` - Runtime architecture description (~150 lines)
- `docs/AGENT_ARCHITECTURE.md` - Agent system, intent runtime, chat service (~400 lines)
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

There are nearly 400 MCP tools available. Two paths matter most.

### For Grasshopper: prefer the batch path — `gh_snapshot` → `gh_edit`

**This is the default, fastest, most reliable way to work on the canvas.**

1. `gh_snapshot` — read the entire canvas in ONE call (components, wires, groups,
   errors, data previews) and get back an `epoch`.
2. `gh_edit` — apply every change in ONE atomic call, passing that `epoch`:
   create → disconnect → delete → set_values → connect → groups.

```python
snap = gh_snapshot()                       # batch read; returns epoch + short IDs
gh_edit(epoch=snap["epoch"], create=[...], connect=["T1.O0>C2.I1"], set_values=[...])
```

One read, one atomic write — deterministic, minimal round trips, no GUID guessing.
Use this by default for creating, wiring, and editing definitions. `gh_undo`
reverses the last edit.

**Viable alternative — `gh_execute_intent`:** natural-language component creation
(`gh_execute_intent(intent="create a sphere with a radius slider")`). It works and
is handy for quick one-offs, but it is **slower** (DSPy resolution + per-operation
round trips + heuristic auto-wiring) and is **not the default**. Reach for it when
you want NL convenience, not for real definition work.

### For Rhino Geometry: prefer typed routes; `rhino_execute_intent` as NL convenience

Typed routes — `rhino_create`, `rhino_transform`, `rhino_boolean`, `rhino_extrude`,
`rhino_loft`, `rhino_sweep`, … — are the preferred, validated, deterministic path.

`rhino_execute_intent` is the natural-language convenience that resolves intent and
routes to those typed routes automatically:

```python
rhino_execute_intent(intent="create a box from 0,0,0 to 10,10,0 with height 5")
```

It's viable and convenient, but **not the default** when you can call the typed
route directly.

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
return structured results. `rhino_execute_intent` routes to these automatically.

`rhino_execute` and `rhino_command` have built-in error handling (script wrapper with
try/except, preflight validation, interactive detection with auto-cancel), so script
errors return structured JSON rather than freezing Rhino. However, typed routes are
still preferred — they validate inputs, track created objects, and avoid edge cases
where a Rhino command pops a native dialog (file chooser, confirmation prompt) that
blocks the UI thread with no programmatic recovery.

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
GUID with `gh_knowledge_query` and pass it to `gh_edit` (or use `gh_execute_intent`
for a quick natural-language create).

### Still stuck?
File an issue at https://github.com/bringfire/rook-release/issues
