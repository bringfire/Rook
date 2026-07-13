# Agent Architecture

Updated: 2026-06-05

This document describes the agent system as it exists today.

---

## Overview

The agent system is ~12,000 lines of Python in `mcp_server/src/rook/agent/` and `mcp_server/src/rook/learning/intent_*.py`. It provides two execution paths:

1. **MCP path** — Claude Code/Desktop calls MCP tools → `server.py` → IntentOrchestrator → bridge → RookNative
2. **Chat path** — Rook chat panel → ChatRunner → ToolDispatcher → bridge → RookNative
3. **Autonomous path** — `spawn_agent` / `plan_and_execute` MCP tools → Planner → Workers → bridge → RookNative

All three paths converge at the HTTP bridge layer. **Agents never use MCP** — they call RookNative HTTP endpoints directly via `bridge.py`.

```
MCP Client (Claude Code)          Chat Panel (Rook C# UI)
         │                                │
    server.py                      chat/server.py
         │                                │
  IntentOrchestrator              ChatRunner + ExecutionPolicy
         │                                │
         ├─── spawn_agent ──→ Planner ──→ Workers
         │                      │           │
         │                   Guardian    Guardian
         │                      └──┬──┘
         │                     Conductor (fleet monitor)
         │                         │
         └─────────────────────────┘
                    │
            ToolDispatcher
                    │
              bridge.py → HTTP → RookNative C++ → Rhino
```

---

## Core Components

### RookAgent (`base_agent.py`, ~1,180 lines)

The LLM-powered agent loop. Each agent instance runs autonomously with its own LLM context, tool set, and event stream.

**Loop:** `prompt → Seam 1 (inject knowledge) → LLM call → tool calls → Seam 2 (correct params) + Seam 3 (record observations) → Seam 4 (adapt tool surface) → repeat`

**Terminates when:** Model returns a response with no tool calls, no steering messages queued, and no follow-up messages queued.

**Knowledge Seams** — four middleware points where the knowledge stores influence agent behavior:

| Seam | Name | What It Does |
|------|------|-------------|
| 1 | Knowledge Injection | Before each LLM call, injects relevant knowledge notes into context |
| 2 | Parameter Correction | After tool call, checks for known gotchas and injects correction hints |
| 3 | Observation Recording | After every tool execution, records outcome for future learning |
| 4 | Tool Surface Adaptation | After each turn, activates/deactivates tool groups based on usage patterns |

Each seam is independently toggleable via `AgentConfig`.

### Planner (`planner.py`, ~1,170 lines)

Decomposes a high-level user request into concrete tasks. Uses a stronger model (Opus) with **read-only tools only** — the Planner never modifies geometry or canvas.

**Output:** A `Plan` containing `TaskSpec` entries organized into execution groups:

```python
@dataclass
class TaskSpec:
    task_id: str
    description: str
    tool_groups: List[str]        # Which Tier 1 groups to load
    workspace_assets: List[str]   # Layers/objects this task owns
    depends_on: List[str]         # Task IDs that must complete first
    success_criteria: str
    estimated_turns: int
    agent_type: str               # "worker" persona
```

Execution groups define parallelism: tasks within a group run concurrently, groups execute sequentially.

### Guardian (`guardian.py`, ~580 lines)

Per-agent trajectory monitor. Subscribes to a single agent's event stream and intervenes when it detects problems.

**Detection rules (Phase 1):**

| Issue | Trigger | Action |
|-------|---------|--------|
| Stuck | 3 consecutive identical tool calls | `agent.steer()` with redirect |
| Looping | Same tool+params repeated 3 times | `agent.steer()` then `agent.abort()` |
| Drift | Agent calling tools outside its workspace_assets | `agent.steer()` with boundary reminder |
| Budget | 80% of token budget consumed | Warning, then abort at limit |

**Phase 2 (optional):** LLM-based trajectory analysis via cheap Haiku calls at configurable intervals. Disabled by default (`enable_llm_analysis: False`).

**Output:** `GuardianReport` with alignment_score (1.0 = no interventions, 0.0 = max reached), intervention counts by type, trajectory phases.

### Conductor (`conductor.py`, 351 lines)

Fleet-level coordinator for parallel agent swarms. Monitors 2+ agents simultaneously for **systemic** issues that no single Guardian can detect.

**Detection:**
- **Systemic bridge failure** — 2+ agents stuck on the HTTP bridge simultaneously → Rhino is likely frozen or in a modal dialog
- **Common tool failure** — 2+ agents failing the same tool → tool or endpoint is broken

**Deduplication:** 60-second suppression window prevents repeated reports for the same issue.

**Output:** `ConductorReport` with total_agents, completed, errored, total_cost_usd, systemic_issues, per_agent_summaries, common_failure_tools, avg_alignment_score, substrate_summary.

### Spawn (`spawn.py`, ~660 lines)

Task execution runners. Three entry points:

| Function | Purpose | Model |
|----------|---------|-------|
| `run_task(task)` | Single autonomous agent with Guardian | Sonnet (configurable) |
| `run_swarm(tasks)` | Parallel multi-task with Conductor + asset exclusivity | Sonnet workers |
| `run_plan(request)` | Planner decomposes, then dispatches via run_task/run_swarm | Opus planner → Sonnet workers |

**Asset exclusivity:** When running a swarm, tasks with overlapping `workspace_assets` are never scheduled concurrently. This prevents two workers from modifying the same layer simultaneously.

---

## Progressive Tool Disclosure

With 428 MCP tools advertised by `list_tools()` (431 static defs minus 3 deprecated-interactive tools gated by default), showing everything to an agent wastes context and confuses the LLM. The system uses three tiers:

The `lean` profile advertises 22 tools and the `readonly` profile advertises 148 tools.

- Director is retired from MCP discovery, profiles, meta-tools, targeting, and internal-agent dispatch. Native `/director/*` routes and implementation modules remain temporarily preserved for disposition review; they are not a public or agent-callable capability.

### Tier 0: Always Active (~12 tools, ~1,800 tokens)

```
rhino_execute_intent, gh_execute_intent, knowledge_query, gh_knowledge_query,
rhino_objects, rhino_ping, gh_snapshot, gh_errors, scene_graph, scene_context,
scene_stats, request_tools, search_tools
```

Agents get a variant (`AGENT_TIER_0`) that excludes `gh_execute_intent` (too large, DSPy-entangled) and adds `session_history`, `rhino_command_prompt`, `ui_block`.

### Tier 1: Named Groups (on-demand)

Groups like `gh_canvas`, `rhino_transform`, `curves`, `analysis`, `layers_readonly`. Loaded when:
- The Planner specifies `tool_groups` in a TaskSpec
- The agent calls `request_tools("gh_canvas")`
- A **transition trigger** fires (e.g., calling `rhino_create` auto-loads `rhino_transform`)

### Tier 2: Individual Tools (search)

Any of the 428 tools can be found via `search_tools("boolean")`. Returns matching tools with descriptions.

### Stale Tool Deactivation

Tools unused for N turns (default: 5 in agents, 8 in chat) are automatically deactivated to free context space.

---

## Chat Agent (`agent/chat/`, ~1,780 lines)

The interactive chat service powers the Rook chat panel in Rhino's sidebar.

### Architecture

```
User message (from C# chat panel via HTTP)
    │
    ▼
ChatRunner — LLM call (LiteLLM) + streaming
    │
    ▼
ToolRegistry — progressive disclosure (Tier 0/1/2)
    │
    ▼
ToolDispatcher — HTTP routing to RookNative
    │
    ▼
ExecutionPolicy — annotate_result() adds "verified" field
    │
    ▼
ChatEvent stream — text_delta, tool_start, tool_result, ui_block
```

### Execution Policy (Guarded Runtime)

Post-dispatch annotation for write-path tools. No pre-dispatch gate (would require intent classification).

| Tool Category | Tools | Verification |
|--------------|-------|-------------|
| CREATION_TOOLS | rhino_create, rhino_boolean, rhino_loft, rhino_sweep, rhino_extrude | `objectsCreated == 0` → `verified: false` |
| MODAL_RISK_TOOLS | rhino_execute, rhino_command (RunScript paths) | Polls `rhino_command_prompt` after dispatch; `prompt_poll_failed` → `verified: false` |

After every CREATION or MODAL_RISK dispatch, the runner automatically polls `rhino_command_prompt` to check if Rhino is stuck in a modal dialog.

### Components

| File | Lines | Purpose |
|------|-------|---------|
| `server.py` | 470 | aiohttp HTTP server, port discovery, route handlers |
| `chat_runner.py` | 692 | Conversation turn execution, streaming, tool dispatch |
| `execution_policy.py` | 199 | Post-dispatch result annotation (verified field) |
| `prompt_builder.py` | 94 | Dynamic system prompt with runtime health facts |
| `conversation_store.py` | 91 | Session conversation persistence to JSON |
| `runtime_health.py` | 136 | Bridge health and runtime facts injected into prompt |

---

## Intent Runtime (`learning/intent_*.py`, ~2,800 lines)

Replaces the old monolithic `rhino_execute_intent` with a layered pipeline:

```
Natural language intent
    │
    ▼
IntentPlanner (P1) — CapabilityRouter fast path or DSPy slow path
    │
    ▼
ExecutionPlan — operation, params, execution_route, command, mode
    │
    ▼
SmartExecutor (P2) — cascade: direct_api → known_command → interactive
    │
    ▼
ExecutionResult — success, objects_created, created_ids, failure
    │
    ▼
TypedReflection (P3) — classify failure layer, record correction
```

### CapabilityRouter (~95 operations)

Maps semantic operations directly to HTTP endpoints, skipping DSPy entirely. This is the fast path — checked first before any LLM call.

Example: `"create box"` → `POST /create` with `{type: "box", ...}` (direct API, no command resolution needed).

### Execution Cascade

The SmartExecutor uses non-interactive substrates only:

1. **Direct API** — Typed HTTP call to a specific endpoint (fastest, most reliable)
2. **Known Command** — Known-safe, fully scripted command string via `/command`

Interactive execution via `/command/start` + `/command/send` is deprecated for
normal agent execution. `/command/prompt` and `/command/cancel` remain recovery
and observability primitives only. If a known command stalls or prompt
verification is inconclusive, execution fails closed instead of auto-driving the
Rhino prompt.

### Failure Layers

When execution fails, `TypedReflection` classifies the failure into a precise layer for targeted learning:

| Layer | Meaning | Correction Strategy |
|-------|---------|-------------------|
| PLANNING | Wrong operation extracted from intent | Improve DSPy ExtractOperation |
| ROUTING | Right operation, wrong HTTP endpoint | Update CapabilityRouter |
| PARAMETER_SYNTHESIS | Right endpoint, wrong parameters | Record parameter gotcha |
| COMMAND_EXECUTION | Command ran but failed in Rhino | Record command syntax note |
| INTERACTIVE_PROMPT | Interactive polling failed | Record prompt sequence |
| WRONG_RESULT | Command succeeded but wrong output | Record expectation gap |
| TIMEOUT | Execution timed out | Record timeout pattern |

---

## Event System (`events.py`, ~130 lines)

Pub/sub event dispatcher that connects all agent components.

**Event types:**

| Category | Events |
|----------|--------|
| Lifecycle | `agent_start`, `agent_end`, `turn_start`, `turn_end` |
| Messages | `message_start`, `message_update`, `message_end` |
| Tool execution | `tool_exec_start`, `tool_exec_end` |
| Knowledge | `knowledge_inject`, `correction_applied`, `tool_group_loaded`, `tool_group_unloaded` |
| Guardian | `guardian_intervention` |
| Conductor | `conductor_systemic_issue` |
| Planner | `plan_created`, `plan_executing`, `plan_complete` |
| Errors | `error` |

Subscribers receive all events (filter by type). Subscriber exceptions are caught and logged — they never break the agent loop.

---

## Configuration

All configuration via dataclasses in `config.py` (~240 lines). Override via constructor, JSON file, or environment variables.

| Config | Key Settings | Env Override |
|--------|-------------|-------------|
| `AgentConfig` | model, api_base, max_turns (30), knowledge seams (all on), bridge_timeout (30s) | `ROOK_WORKER_MODEL`, `ROOK_BRIDGE_URL` |
| `PlannerConfig` | planner_model, worker_model, api_base, max_concurrent_workers (3) | `ROOK_PLANNER_MODEL`, `ROOK_WORKER_MODEL`, `ROOK_MODEL_PROFILE` |
| `GuardianConfig` | check_interval (3), max_consecutive_failures (3), budget_threshold (0.8) | — |
| `ConductorConfig` | bridge_failure_quorum (2), check_interval (5s), dedup_window (60s) | — |

### Model Profiles (`model_profiles.py`)

All agent subsystems resolve LLM models from `knowledge/model_profiles.json`. Five built-in profiles:

| Profile | Planner | Workers | DSPy | api_base |
|---------|---------|---------|------|----------|
| `cloud` (default) | Claude Opus | Claude Sonnet | Claude Sonnet | — |
| `hybrid` | Claude Opus (cloud) | Local (Ollama) | Local (Ollama) | — |
| `local` | Local (Ollama) | Local (Ollama) | Local (Ollama) | — |
| `lmstudio` | Claude Opus (cloud) | LM Studio | LM Studio | `http://127.0.0.1:1234/v1` |
| `finetuned` | Claude Opus (cloud) | Fine-tuned local | Fine-tuned local | — |

Switch profiles by editing `"active"` in `knowledge/model_profiles.json` or setting `ROOK_MODEL_PROFILE` env var.

**Profile resolution (highest wins):**
1. Explicit `profile_name` argument to `get_models()`
2. `ROOK_MODEL_PROFILE` environment variable
3. `"active"` field in `knowledge/model_profiles.json`

**Model resolution (highest wins, within a resolved profile):**
1. Explicit `ROOK_*_MODEL` env vars
2. Constructor kwargs / overrides
3. Profile's role-specific model string
4. Hardcoded defaults (Anthropic cloud)

**Per-role `api_base` filtering:** Mixed profiles (e.g., `lmstudio`) share a single `api_base` across all roles, but cloud models must not be routed to local endpoints. `api_base_for_model(model, profile_api_base)` is the single enforcement point — it returns the api_base only for models that need it:

- Known cloud providers (`anthropic/`, `groq/`, `huggingface/`, etc.) → `None`
- Ollama models → `None` (native LiteLLM routing)
- Known OpenAI cloud models (`openai/gpt-*`, `openai/o1*`, etc.) → `None`
- Local OpenAI-compatible models (`openai/lmstudio-model`) → api_base
- Bare model strings → api_base

**Propagation:** Model profiles + per-role api_base flow into all execution paths:
- `PlannerConfig.from_env()` → Planner agent + worker agents
- `run_task()` / `run_swarm()` → standalone agent spawning (resolves api_base from profile even for explicit model overrides)
- `PromptBuilder.resolve_model_and_base()` → chat conversations (re-filters on model_override)
- `configure_dspy()` / `configure_dspy_for_optimization()` → per-model api_base + is_local detection
- `Guardian` → LLM analysis model gets filtered api_base via `GuardianConfig`
- `server.py` spawn handler → always resolves api_base regardless of explicit model

**Local provider detection:** `detect_ollama_models()` and `detect_lmstudio_models()` probe localhost for running local model servers.

---

## MCP Entry Points (in `server.py`)

Five MCP tools expose the agent system to Claude:

| Tool | Purpose | Returns |
|------|---------|---------|
| `spawn_agent` | Launch single autonomous agent (background) | agent_id immediately |
| `plan_and_execute` | Planner decomposes + workers execute (background) | plan_id immediately |
| `agent_status` | Poll agent/plan completion and metrics | Status, turns, cost, active tools |
| `agent_abort` | Abort a running agent | Confirmation |
| `agent_answer` | Answer a pending question from a blocked agent | Unblocks the agent |

Active agents stored in `_active_agents` dict (max 50, oldest evicted).

---

## Known Limitations

Known constraints of the current flat orchestration model:

1. **No result passing** — Task N's output is not automatically available to Task N+1. Workers share a Rhino document but not execution context.
2. **No sibling awareness** — Parallel workers cannot see what their siblings have created on the canvas during execution.
3. **No escalation** — Workers have no `ask()` primitive to request human input mid-task.
4. **No mid-task validation** — Composition errors (wrong wiring, missing intermediaries) cascade until the task completes.

---

## Key Files

| Component | Path |
|-----------|------|
| Agent core | `mcp_server/src/rook/agent/base_agent.py` |
| Planner | `mcp_server/src/rook/agent/planner.py` |
| Guardian | `mcp_server/src/rook/agent/guardian.py` |
| Conductor | `mcp_server/src/rook/agent/conductor.py` |
| Spawn runners | `mcp_server/src/rook/agent/spawn.py` |
| Tool dispatcher | `mcp_server/src/rook/agent/tool_dispatcher.py` |
| Tool tiers | `mcp_server/src/rook/agent/tool_groups.py` |
| Tool registry | `mcp_server/src/rook/agent/tool_registry.py` |
| Events | `mcp_server/src/rook/agent/events.py` |
| Config | `mcp_server/src/rook/agent/config.py` |
| Chat server | `mcp_server/src/rook/agent/chat/server.py` |
| Chat runner | `mcp_server/src/rook/agent/chat/chat_runner.py` |
| Execution policy | `mcp_server/src/rook/agent/chat/execution_policy.py` |
| Intent orchestrator | `mcp_server/src/rook/learning/intent_orchestrator.py` |
| Intent planner | `mcp_server/src/rook/learning/intent_planner.py` |
| Smart executor | `mcp_server/src/rook/learning/smart_executor.py` |
| Typed reflection | `mcp_server/src/rook/learning/typed_reflection.py` |
| Intent runtime types | `mcp_server/src/rook/learning/intent_runtime.py` |
| Model profiles | `mcp_server/src/rook/agent/model_profiles.py` |
| Personas | `mcp_server/src/rook/agent/personas/` |
