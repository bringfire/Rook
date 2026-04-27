# Agent Tooling Upgrade — Output Windowing, Context Compaction & Hook System

**Date:** 2026-04-13  
**Status:** Draft — awaiting Codex review  
**Authors:** Claude + aryan  
**Reference codebase:** `C:\Users\aryan\source\repos\claw-code` (Rust port / reverse-engineering of Claude Code harness)  
**Rook agent code:** `mcp_server/src/rook/agent/`  
**Rook intent runtime:** `mcp_server/src/rook/learning/`

---

## 1. Intent

Rook's agent system (RookAgent, Planner, Guardian, Conductor, spawn runners)
has the right *orchestration* DNA — task decomposition, trajectory monitoring,
progressive tool disclosure, knowledge seams. What it lacks is the *tool-level
intelligence* that lets agents operate on large scenes without choking.

The claw-code study reveals that Claude Code's tools are not semantically
smart — they don't summarize or analyze. The intelligence is in a simple,
mechanical contract: **bounded output windows + metadata about what was
excluded**. The LLM does all the semantic work; the tools just make sure it
gets manageable chunks.

This document proposes three upgrades derived from that study:

1. **Output windowing** — default caps, pagination, and truncation metadata on
   every variable-length Rook tool
2. **Context compaction** — graceful mid-session summarization when agent token
   budget gets tight, instead of hard `max_turns` death
3. **Agent-path hook system** — data-driven pre/post tool execution middleware
   on the autonomous agent path (currently only chat has `execution_policy.py`)

---

## 2. What claw-code Teaches Us

### 2.1 The 17 Tools and Their Output Contracts

claw-code defines 17 tools. The ones relevant to output management:

| Tool | Cap | Pagination | Metadata Returned |
|------|-----|------------|-------------------|
| `grep_search` | Default 250 lines | `offset` + `head_limit` | `appliedLimit`, `appliedOffset`, match count |
| `glob_search` | Hard cap 100 files | None | `truncated: bool`, file count |
| `read_file` | LLM controls via `offset`/`limit` | Full line-range | `totalLines`, `startLine`, `numLines` |
| `WebFetch` | 900 char text preview | None | Raw `bytes` count (LLM sees how much it missed) |
| `WebSearch` | 8 results hard cap | None | Just the results |
| `bash` | **Unbounded** | None | None |
| `NotebookEdit` | **Unbounded** | None | None |
| `Agent` (subagent) | 32 iteration cap | None | Status + output file path |

**Key insight:** The unbounded tools (bash, notebook) are where context blowups
happen. Every bounded tool returns metadata so the LLM can decide: paginate,
narrow the query, or pivot strategy.

### 2.2 The Output Contract Pattern

Every variable-length tool in claw-code follows this implicit contract:

```
Response {
    data: [bounded slice of results],
    total: int,          // how many exist
    returned: int,       // how many in this slice
    offset: int,         // where this slice starts
    truncated: bool,     // did we cap?
}
```

The LLM sees `"250 of 3,847 matches"` and can:
- Call again with `offset=250` to get the next page
- Add a `glob` filter to narrow results
- Switch to `files_with_matches` mode for overview first
- Decide it has enough and move on

**The tool never decides what's important.** It just caps and reports.

### 2.3 Session Compaction

When conversation context grows too large, claw-code's `compact.rs` implements:

1. **Trigger:** compactable messages exceed `max_estimated_tokens` (~10,000)
2. **Strategy:** preserve N most-recent messages + system prompt, summarize middle
3. **Summary content:** list of tool calls made + pending work description
4. **Truncation:** individual summaries capped at 160-200 chars with `...` ellipsis

This is the safety net. Even if a tool returns a huge blob, the session can
recover by compacting old turns.

### 2.4 Subagent Isolation Model

claw-code spawns subagents with triple isolation:

- **Separate OS thread** (named `claw-agent-{id}`)
- **Restricted tool set** via `SubagentToolExecutor` (e.g., Explore agents
  only get read_file, grep, glob, web tools — no write operations)
- **No permission prompter** — subagents cannot escalate; they either have
  access or they don't

Results are persisted to a file, not held in memory. The parent reads the
file when the agent completes.

### 2.5 Hook System

Hooks are data-driven middleware (shell commands from config, not hardcoded):

```
HookEvent::PreToolUse { tool_name, input }
HookEvent::PostToolUse { tool_name, output, is_error }

Exit codes: 0 = Allow, 2 = Deny, other = Warn (add message to context)
```

Hooks can inject messages into the conversation (e.g., warnings, validation
feedback). A plugin extends behavior without modifying runtime code.

### 2.6 Permission Policy

Hierarchical permission with explicit escalation rules:

```
PermissionMode: ReadOnly | WorkspaceWrite | DangerFullAccess | Prompt | Allow

authorize(tool_name, input, prompter):
    if active_mode >= tool_requirement: Allow
    if escalation possible AND prompter exists: Ask
    else: Deny with reason
```

Each tool has a required permission tier. Subagents get `Allow` for their
restricted set and no prompter — they can't escalate.

---

## 3. Comparison: claw-code vs. Rook Current State

### 3.1 Where Rook Is Ahead

| Capability | Rook | claw-code |
|---|---|---|
| **Knowledge seams** | 4 middleware points (inject, correct, record, adapt) wired into agent loop | Nothing — tools are stateless |
| **Trajectory monitoring** | Guardian (per-agent) + Conductor (fleet) detect stuck/loop/drift/budget | None — agents run blind |
| **Knowledge store depth tiers** | `quick`/`context`/`errors`/`raw` — progressive depth | Flat tool output, no semantic tiers |
| **Progressive tool disclosure** | Tier 0/1/2 with stale deactivation | Subagent tool restriction only — no progressive loading |
| **Task decomposition** | Planner produces execution groups with dependency ordering | Single-level agent spawn only |
| **Domain specificity** | 7 agent personas with tailored prompts + tool groups | Generic system prompt |
| **Asset exclusivity** | Parallel workers can't touch each other's workspace_assets | No concept of workspace ownership |

### 3.2 Where claw-code Is Ahead

| Capability | claw-code | Rook |
|---|---|---|
| **Output windowing** | Every search/read tool has caps + pagination + metadata | Tools return unbounded results |
| **Context compaction** | Summarize old turns, preserve recent | Hard `max_turns` (30) wall — no recovery |
| **Pre-dispatch permission gate** | `PermissionPolicy.authorize()` before every tool call | `execution_policy.py` only on chat path, post-dispatch only |
| **Hook system on agent path** | Pre/post hooks run for every tool execution | Chat has execution_policy; agents have nothing |
| **Pagination metadata** | `{ total, returned, offset, truncated }` on every bounded result | Some tools cap output but don't report it |
| **File reading with line ranges** | `offset`/`limit` → read lines 450-500 of a 3,000-line file | Agent path reads entire blobs |
| **Script output bounding** | bash has timeout + interrupted flag (output still unbounded though) | `rhino_execute` unbounded with no timeout signal |

### 3.3 Where Both Are Equal

| Capability | Status |
|---|---|
| **LLM provider abstraction** | Both use swappable transport (LiteLLM vs. ApiClient trait) |
| **Event/pub-sub system** | Both have event dispatchers (Rook's is richer with 20+ event types) |
| **Background task execution** | Both support async agent spawning with status polling |
| **Model routing** | Both support multiple model tiers (planner vs. worker) |

---

## 4. Upgrade Plan

### Phase 1: Output Windowing (C++ Native + Python ToolDispatcher)

**Goal:** Every Rook tool that returns variable-length data gets a default cap,
optional pagination, and truncation metadata.

#### 4.1 The Universal Response Envelope

All paginated responses adopt this shape:

```json
{
    "data": [ ... ],
    "pagination": {
        "total": 2340,
        "returned": 100,
        "offset": 0,
        "limit": 100,
        "truncated": true
    }
}
```

Tools that already return structured JSON add `pagination` as a sibling key.
Tools that return flat arrays wrap in `{ "data": [...], "pagination": {...} }`.

#### 4.2 Tools To Upgrade

**High priority — these are the context killers:**

| Tool | Current Output | Change | Default Limit |
|---|---|---|---|
| `rhino_objects` | All objects in scene | Add `limit`/`offset` params, return `pagination` | 100 objects |
| `gh_snapshot` | Full canvas JSON dump | Add `component_limit` param, section-based windowing (components, wires, groups separately) | 50 components |
| `scene_graph` / `scene_query` | Full subgraph | Add `node_limit` + `depth_limit`, return `pagination` | 200 nodes, depth 3 |
| `rhino_layers` | All layers flat | Add `limit`/`offset`, return `pagination` | 200 layers |
| `gh_errors` | All errors | Add `limit`, return `pagination` | 50 errors |
| `rhino_execute` / `rhino_command` | Unbounded script stdout | Cap output at N chars, return `{ output, truncated, totalChars }` | 8,000 chars |
| `rhino_objects` type/layer filters | Filter results but no cap | Same windowing applies post-filter | 100 objects |

**Medium priority — large in specific scenarios:**

| Tool | Change | Default Limit |
|---|---|---|
| `gh_library` | Add `limit`/`offset` to component listing | 100 components |
| `scene_stats` | Already summary-shaped — no change needed | N/A |
| `knowledge_query` (depth=raw) | Already tiered — no change needed | N/A |
| `rhino_blocks` | Add `limit`/`offset` | 100 blocks |
| `rhino_materials` / `rhino_linetypes` | Add `limit`/`offset` | 100 items |

#### 4.3 Implementation Path

**Layer 1 — C++ Native (RookNative)**

Each HTTP handler that returns arrays gets optional query params:

```
GET /objects?limit=100&offset=0&type=brep
→ { "objects": [...], "pagination": { "total": 2340, ... } }
```

The C++ side is mechanical: after collecting results into a vector, slice
`[offset..offset+limit]` and populate the pagination block. Total count is
the pre-slice vector size.

**Layer 2 — Python ToolDispatcher (agent path)**

`ToolDispatcher.dispatch()` injects default `limit` if the agent didn't
specify one. This is the safety net — even if an agent forgets to paginate,
it won't get 50,000 objects back.

```python
# In tool_dispatcher.py
DEFAULT_LIMITS = {
    "rhino_objects": 100,
    "gh_snapshot": 50,
    "scene_graph": 200,
    "rhino_layers": 200,
    "gh_errors": 50,
}

async def dispatch(self, tool_name: str, params: dict) -> dict:
    if tool_name in DEFAULT_LIMITS and "limit" not in params:
        params["limit"] = DEFAULT_LIMITS[tool_name]
    result = await self._call(tool_name, params)
    return result
```

**Layer 3 — MCP Tool Descriptions**

Update tool descriptions in `server.py` to advertise pagination:

```
"rhino_objects": "List objects in the scene. Returns paginated results.
  Use limit/offset for large scenes. Response includes pagination.total
  so you know if more results exist."
```

This is critical — the LLM needs to know pagination exists from the tool
description to use it.

#### 4.4 Script Output Bounding

`rhino_execute` and `rhino_command` need special handling because their
output is arbitrary script stdout, not structured JSON.

**Proposed approach:**

```json
{
    "success": true,
    "output": "... first 8000 chars ...",
    "outputTruncated": true,
    "totalOutputChars": 47823,
    "hint": "Output truncated. Consider printing less or writing results to a layer/user string for inspection."
}
```

The `hint` field is a soft nudge to the LLM to change strategy (write results
to Rhino doc instead of printing to stdout).

---

### Phase 2: Context Compaction (Python Agent Layer)

**Goal:** When an agent's token usage approaches its budget, summarize old
turns and continue instead of dying at `max_turns`.

#### 5.1 Compaction Trigger

```python
class CompactionConfig:
    budget_fraction: float = 0.75       # Trigger at 75% of token budget
    preserve_recent: int = 5            # Keep last 5 messages verbatim
    preserve_system: bool = True        # Always keep system prompt
    max_summary_tokens: int = 500       # Cap summary size
```

Checked after each turn in `RookAgent._run_loop()`. When estimated token
usage exceeds `budget_fraction * max_tokens`, compact.

#### 5.2 Compaction Strategy

1. Partition messages into: `[system] [compactable...] [recent_N]`
2. For each compactable message:
   - If tool_call: extract `tool_name` + first 100 chars of params
   - If tool_result: extract `tool_name` + success/fail + first 100 chars
   - If assistant text: extract first 150 chars
3. Assemble summary block:

```
<compacted_context>
Turns 2-18 summarized (17 turns, ~12,400 tokens recovered):
- rhino_objects(type=brep, layer=Structure) → 47 objects returned
- rhino_execute_intent(intent="move objects to layer Facade") → success, 12 moved
- gh_snapshot() → 23 components, 4 errors
- gh_edit(create=[Panel, Slider]) → created 2 components
- [... remaining tool calls ...]
Pending work: roof surface loft still needed, 3 GH errors unresolved.
</compacted_context>
```

4. Replace compactable messages with single summary message
5. Continue agent loop with recovered token budget

#### 5.3 Integration Point

In `base_agent.py`, after each turn:

```python
async def _run_loop(self):
    while ...:
        # Existing turn logic
        response = await self._call_llm()
        await self._execute_tools(response.tool_calls)

        # NEW: check compaction
        if self._should_compact():
            await self._compact_session()
            # Continue loop — agent now has headroom
```

The Guardian already monitors token budget (budget_threshold at 0.8). Compaction
should trigger *before* Guardian's warning (0.75 vs 0.8) so the agent recovers
without Guardian intervention.

---

### Phase 3: Agent-Path Hook System

**Goal:** Data-driven pre/post tool execution middleware on the autonomous
agent path, matching what `execution_policy.py` does for chat but extensible.

#### 6.1 Hook Definition

Hooks are Python callables (not shell commands — we're in-process, not CLI):

```python
@dataclass
class AgentHook:
    event: Literal["pre_tool", "post_tool"]
    tool_pattern: str           # glob pattern, e.g. "rhino_*" or "gh_edit"
    handler: Callable           # async (context) -> HookResult
    priority: int = 0           # lower runs first
    enabled: bool = True

class HookResult(Enum):
    ALLOW = "allow"
    DENY = "deny"              # block tool execution, inject reason
    WARN = "warn"              # inject warning message but proceed
    MODIFY = "modify"          # transform params (pre) or result (post)
```

#### 6.2 Built-In Hooks

**Pre-tool hooks:**

| Hook | Pattern | Purpose |
|---|---|---|
| `validate_geometry_exists` | `rhino_transform`, `rhino_boolean`, `rhino_delete` | Check that target GUIDs exist before mutating |
| `enforce_workspace_boundary` | `rhino_*`, `gh_*` | Deny if agent touches assets outside its `workspace_assets` (currently Guardian detects this *after* execution) |
| `inject_knowledge_hint` | `*` | This is Knowledge Seam 2 (parameter correction) — already exists, just formalized as a hook |

**Post-tool hooks:**

| Hook | Pattern | Purpose |
|---|---|---|
| `record_creation` | `rhino_create`, `rhino_boolean`, `rhino_loft`, `rhino_sweep`, `rhino_extrude` | Log what was created (layer, type, bounds) to agent's trajectory |
| `verify_creation` | Same as above | Check `objectsCreated == 0` → inject warning (same as chat's `execution_policy.py`) |
| `detect_modal_risk` | `rhino_execute`, `rhino_command` | Post-execution: poll `rhino_command_prompt` to detect stuck dialog |
| `cap_output` | `*` | Enforce output size limits if tool didn't self-cap (safety net) |

#### 6.3 Integration Point

In `base_agent.py`, the existing tool execution loop becomes:

```python
async def _execute_tool(self, tool_call):
    # Pre-hooks
    for hook in self._hooks.match("pre_tool", tool_call.name):
        result = await hook.handler(PreToolContext(tool_call, self))
        if result == HookResult.DENY:
            return ToolResult(error=hook.deny_reason)
        if result == HookResult.MODIFY:
            tool_call = hook.modified_call

    # Execute
    result = await self._dispatcher.dispatch(tool_call.name, tool_call.params)

    # Post-hooks
    for hook in self._hooks.match("post_tool", tool_call.name):
        result = await hook.handler(PostToolContext(tool_call, result, self))

    return result
```

This subsumes the existing Knowledge Seam 2 (parameter correction) and
Seam 3 (observation recording) into a unified hook system while keeping
them as individually toggleable hooks.

---

## 5. Phase Ordering & Dependencies

```
Phase 1: Output Windowing
  ├─ 1a: C++ pagination params on high-priority tools     [C++ native]
  ├─ 1b: Python ToolDispatcher default limits              [Python agent]
  ├─ 1c: MCP tool description updates                      [Python server]
  └─ 1d: Script output bounding for rhino_execute          [C++ native]

Phase 2: Context Compaction
  ├─ 2a: CompactionConfig + token estimation               [Python agent]
  ├─ 2b: Compaction logic in base_agent._run_loop          [Python agent]
  └─ 2c: Guardian integration (compact before warn)         [Python agent]

Phase 3: Agent-Path Hooks
  ├─ 3a: Hook registry + matching                          [Python agent]
  ├─ 3b: Built-in pre/post hooks                           [Python agent]
  ├─ 3c: Migrate Knowledge Seam 2+3 into hook system       [Python agent]
  └─ 3d: Pre-dispatch permission gate                       [Python agent]
```

**Phase 1 can start immediately** — it's mechanical C++ work (add params,
slice vectors, populate pagination JSON) plus Python defaults. No
architectural changes.

**Phase 2 depends on nothing** — pure Python addition to `base_agent.py`.
Can run in parallel with Phase 1.

**Phase 3 depends on Phase 2 being designed** — the hook system needs to know
about compaction (post-hooks shouldn't fire on compacted turns). But
implementation can overlap.

---

## 6. What We Deliberately Don't Copy

| claw-code Pattern | Why We Skip It |
|---|---|
| **Shell-command hooks** (subprocess per hook) | Too slow for Rhino's UI-thread constraint. In-process Python callables are faster. |
| **Permission prompter** (ask user mid-agent) | Rook agents are autonomous — no user in the loop. Use pre-dispatch deny instead. |
| **Session file persistence** (save/load from disk) | Rook agents are ephemeral. Chat has `conversation_store.py` already. |
| **Triple OS-thread isolation** | Rook agents share a Python process (GIL). Isolation is via tool restriction + workspace_assets, not threads. |
| **Config-file hook registration** | Rook skills/personas already configure agents. Hooks register in Python code, not YAML. |

---

## 7. Success Criteria

After all three phases:

1. **No agent should be able to blow its context with a single tool call.**
   `rhino_objects` on a 50,000-object scene returns 100 + metadata. The agent
   paginates or filters.

2. **Agents can handle 60+ effective turns** by compacting old context,
   instead of dying at 30.

3. **Write-path tools are validated before execution** on the agent path,
   not just post-annotated on the chat path.

4. **Guardian interventions for drift decrease** because pre-dispatch hooks
   catch boundary violations before they happen.

5. **Script output never exceeds 8KB** in agent context, with a clear signal
   to the LLM that truncation occurred.

---

## 8. Open Questions for Codex Review

1. **Pagination in C++ — query params or JSON body?** GET requests naturally
   use query params, but POST requests (like `/objects` with filters) already
   use JSON body. Should pagination always be in the body for consistency?

2. **Compaction token estimation accuracy.** We don't have a tokenizer in the
   Python layer. Options: (a) character-count heuristic (4 chars ≈ 1 token),
   (b) tiktoken for Claude-family estimation, (c) LiteLLM's token counting.
   Which is acceptable given the latency budget?

3. **Hook system vs. Knowledge Seams.** Phase 3 proposes migrating Seam 2+3
   into hooks. Should Seam 1 (knowledge injection) and Seam 4 (tool surface
   adaptation) also become hooks, or do they stay as first-class agent-loop
   features because they operate at a different granularity (per-turn, not
   per-tool)?

4. **Default limits tuning.** The proposed defaults (100 objects, 50 GH
   components, 200 scene nodes) are starting points. Should we instrument
   actual agent runs to find the 90th-percentile output sizes and set defaults
   just below them?

5. **Backward compatibility.** MCP consumers (Claude Code calling tools
   directly, not through agents) currently expect full results. Adding
   pagination changes the response shape. Options: (a) pagination only when
   `limit` param is present, (b) always paginate with high default (10,000),
   (c) separate `_paginated` variants. Recommendation: option (a) — existing
   callers unchanged, agents opt in via ToolDispatcher defaults.

---

## Appendix A: claw-code File Map

| Component | Path in claw-code |
|---|---|
| Tool definitions + dispatch | `rust/crates/tools/src/lib.rs` |
| File operations (read, glob, grep) | `rust/crates/runtime/src/file_ops.rs` |
| Bash execution | `rust/crates/runtime/src/bash.rs` |
| Session + conversation loop | `rust/crates/runtime/src/conversation.rs` |
| Session compaction | `rust/crates/runtime/src/compact.rs` |
| Permission policy | `rust/crates/runtime/src/permissions.rs` |
| Hook runner | `rust/crates/runtime/src/hooks.rs` |
| Subagent spawn | `rust/crates/tools/src/lib.rs` (lines 1505-1777) |
| Config (3-tier merge) | `rust/crates/runtime/src/config.rs` |

## Appendix B: Rook Agent File Map

| Component | Path in Rook |
|---|---|
| Agent loop + knowledge seams | `mcp_server/src/rook/agent/base_agent.py` |
| Planner (task decomposition) | `mcp_server/src/rook/agent/planner.py` |
| Guardian (trajectory monitor) | `mcp_server/src/rook/agent/guardian.py` |
| Conductor (fleet coordinator) | `mcp_server/src/rook/agent/conductor.py` |
| Spawn runners | `mcp_server/src/rook/agent/spawn.py` |
| Tool dispatcher (agent HTTP) | `mcp_server/src/rook/agent/tool_dispatcher.py` |
| Tool tiers + groups | `mcp_server/src/rook/agent/tool_groups.py` |
| Tool registry | `mcp_server/src/rook/agent/tool_registry.py` |
| Chat execution policy | `mcp_server/src/rook/agent/chat/execution_policy.py` |
| Chat runner | `mcp_server/src/rook/agent/chat/chat_runner.py` |
| Intent planner | `mcp_server/src/rook/learning/intent_planner.py` |
| Intent runtime | `mcp_server/src/rook/learning/intent_runtime.py` |
| Personas | `mcp_server/src/rook/agent/personas/` |
| MCP server (tool registration) | `mcp_server/src/rook/server.py` |
| C++ HTTP handlers | `src/RookNative/RookServer.cpp` |
