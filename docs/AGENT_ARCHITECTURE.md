# Agent Architecture

Updated: 2026-09-05

This document describes the agent system as it exists today.

Current sequencing is governed by the
[Compositional Agent Harness Roadmap](roadmaps/2026-08-02-compositional-agent-harness-roadmap.md).

---

## Overview

The agent system is implemented primarily in `mcp_server/src/rook/agent/` and `mcp_server/src/rook/learning/intent_*.py`. It provides two production entry paths:

1. **MCP path** — Claude Code/Desktop selects explicit MCP tools → `server.py` → bridge → RookNative
2. **RookChat path** — RookChat C# panel → authenticated local HTTP → Python ACP conversation service → official ACP SDK → directly owned Prime process → service-declared Rook MCP server → Rook gateway / RookNative

Both paths converge at Rook's MCP/gateway authority boundary. Internal agent modules call RookNative HTTP endpoints directly via `bridge.py`; autonomous MCP creation entry points are lifecycle-contained and are not a production execution path.

```
MCP Client                         RookChat C# panel
    │                                      │
 server.py                    authenticated local HTTP
    │                                      │
    │                         Python ACP conversation service
    │                                      │
    │                              official ACP SDK
    │                                      │
    │                         directly owned Prime process
    │                                      │
    │                         service-declared Rook MCP server
    │                                      │
    └──────────────────┬───────────────────┘
                       │
              Rook gateway / bridge.py
                       │
             RookNative C++ → Rhino
```

### Semantic-Harness Direction

The retained Planner and Worker internals distinguish two graph roles:

| Graph | Ownership | Meaning |
|---|---|---|
| Semantic design graph | Frontier Planner within admitted primitive contracts | What to build: operations, parameters, connections, acceptance, and unresolved leaves |
| Execution `PlanGraph` | Deterministic compiler and runner | How admitted work advances: readiness, execution, verification, receipts, failure, and terminal state |

The v2 Grasshopper recipe graph and `recipe_to_edit()` are candidates for the design
representation. The existing `PlanGraph` remains the execution-state substrate. No
active decision yet promotes either into a universal cross-domain IR.

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

The MCP surface is large enough that showing every admitted tool to every agent wastes context. The system uses three disclosure tiers. Full, lean, and readonly counts are pinned by `test_server_tool_profiles.py`.

- Director is retired from MCP discovery, profiles, meta-tools, targeting, and internal-agent dispatch. Native `/director/*` routes and implementation modules remain temporarily preserved for disposition review; they are not a public or agent-callable capability.

### Tier 0: Always Active (~12 tools, ~1,800 tokens)

Tier 0 contains explicit knowledge queries, Rhino and Grasshopper inspection, scene context, and progressive-disclosure meta-tools. `AGENT_TIER_0` adds supported script mutation, Grasshopper snapshot, session history, and Rhino prompt-state inspection.

### Tier 1: Named Groups (on-demand)

Groups like `gh_canvas`, `rhino_transform`, `curves`, `analysis`, `layers_readonly`. Loaded when:
- The Planner specifies `tool_groups` in a TaskSpec
- The agent calls `request_tools("gh_canvas")`
- A **transition trigger** fires (e.g., calling `rhino_create` auto-loads `rhino_transform`)

### Tier 2: Individual Tools (search)

Any active tool can be found via `search_tools("boolean")`. Returns matching tools with descriptions.

### Stale Tool Deactivation

Tools unused for N turns (default: 5 in internal agents) are automatically deactivated to free context space.

---

## RookChat (Prime ACP)

[CURRENT_ARCHITECTURE.md](CURRENT_ARCHITECTURE.md) is the canonical concise description of RookChat's product boundary. The active path is:

```text
RookChat C# panel
→ authenticated local HTTP
→ Python ACP conversation service
→ official ACP SDK
→ directly owned Prime process
→ service-declared Rook MCP server
→ Rook gateway / RookNative
```

RookChat owns the durable conversation association, directly owned ACP process and connection, transport correlation, bounded presentation, runtime identity, and immutable Rook target binding. Prime owns reasoning, transcript, goals, compaction, model context, and semantic completion. Normal Rook tools are delivered through the service-declared MCP server and remain subject to Rook's capability, target, command, and gateway enforcement.

The modules under `agent/chat/` implement ACP transport, conversation storage, bounded presentation, runtime verification, and the authenticated HTTP surface. RookChat does not retain the internal `RookAgent`/`ToolRegistry` loop as a second chat backend. Shared helpers that remain under this package serve classified non-chat or internal-agent consumers; they do not form another RookChat implementation.

---

## Intent Runtime (`learning/intent_*.py`, ~2,800 lines)

The retained intent internals use a layered pipeline:

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

Three MCP tools expose status and control for existing agent records:

| Tool | Purpose | Returns |
|------|---------|---------|
| `agent_status` | Poll agent/plan completion and metrics | Status, turns, cost, active tools |
| `agent_abort` | Abort a running agent | Confirmation |
| `agent_answer` | Answer a pending question from a blocked agent | Unblocks the agent |

The autonomous creation entry points are lifecycle-contained. Existing active-agent state uses the `_active_agents` dict (max 50, oldest evicted).

---

## Known Limitations

Known constraints of the current flat orchestration model:

1. **No result passing** — Task N's output is not automatically available to Task N+1. Workers share a Rhino document but not execution context.
2. **No sibling awareness** — Parallel workers cannot see what their siblings have created on the canvas during execution.
3. **No escalation** — Workers have no `ask()` primitive to request human input mid-task.
4. **No mid-task validation** — Composition errors (wrong wiring, missing intermediaries) cascade until the task completes.
5. **No universal semantic design graph** — Retained Planner and Worker internals use bounded task and execution structures; no active decision promotes them into a universal cross-domain IR.
6. **No receipt-driven semantic replan** — Existing receipts can stop and verify execution, but they do not yet drive one bounded Planner-authored topology revision.

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
| Chat service entrypoint | `mcp_server/src/rook/agent/chat/service_main.py` |
| ACP conversation owner | `mcp_server/src/rook/agent/chat/acp_conversation.py` |
| Authenticated chat HTTP surface | `mcp_server/src/rook/agent/chat/server.py` |
| Internal-agent execution policy | `mcp_server/src/rook/agent/chat/execution_policy.py` |
| Intent orchestrator | `mcp_server/src/rook/learning/intent_orchestrator.py` |
| Intent planner | `mcp_server/src/rook/learning/intent_planner.py` |
| Smart executor | `mcp_server/src/rook/learning/smart_executor.py` |
| Typed reflection | `mcp_server/src/rook/learning/typed_reflection.py` |
| Intent runtime types | `mcp_server/src/rook/learning/intent_runtime.py` |
| Model profiles | `mcp_server/src/rook/agent/model_profiles.py` |
| Personas | `mcp_server/src/rook/agent/personas/` |
