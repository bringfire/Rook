# RookLLM Chooser Slice 2 Design

## Status

Design for review. This is Slice 2 of the Model Control phase: agent-mediated, per-conversation model setting for RookChat. It follows Slice 1 model visibility, merged in PR #257.

Context consulted:

- `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`
- `docs/superpowers/specs/2026-06-16-rook-chat-model-visibility-design.md`
- `docs/rook_docs/2026-06-16-rookllm-chooser-vision.md` from local commit `ebc134fd` (`docs/rookllm-chooser-vision` branch; not yet present on `origin/main`)
- `docs/superpowers/specs/2026-06-16-local-model-tool-calling-spike.md` from the same local commit

## Goal

Give the RookLLM Chooser its first hands: a user can tell the chat agent, in natural language, to switch this conversation to a different allowed model, and the agent can perform that switch. The switch is limited to the current chat conversation. It does not change the active model profile, planner, worker, Guardian, DSPy, or any persistent config file.

The primary user experience is:

1. User says: "Use my local Qwen for this chat."
2. The chat persona inspects available models if needed.
3. The persona calls an agent tool to set the current conversation's model.
4. The tool validates the model and stages the change for the next turn.
5. The panel refreshes the Slice 1 visibility surface and shows text feedback that the next user message will use the new model.

This is deliberately not a primary dropdown feature. A selector can come later as a secondary fallback, but the Slice 2 contract is agent-mediated setting with Slice 1 visibility as the feedback channel.

## Non-Goals

- No process-wide profile switching.
- No writes to `knowledge/model_profiles.json`.
- No DSPy reconfiguration.
- No Guardian model wiring changes.
- No client-supplied `api_base`.
- No free-form model strings reaching LiteLLM.
- No broad visual UI work. Text/status feedback is sufficient.
- No claim that a local model is autonomous-grade. Slice 2 is human-in-the-loop conversation override; the tool-calling spike gates autonomous local agents.

## Existing Ground Truth

The current conversation already stores `model` and `api_base` on `Conversation`. `ChatRunner.run_turn()` reads `conversation.model` and `conversation.api_base` fresh when building `litellm.acompletion(...)` kwargs for each turn. Therefore a per-conversation change can be picked up by the next turn without touching process-wide state.

Slice 1 provides:

- `GET /agent/chat/models`
- `model_status.get_cached_local_provider_status_async()`
- `model_status.get_cached_local_provider_status_snapshot()`
- `model_status.compute_allowed_model_overrides(local_providers, role_status=...)`

Routing remains rooted in `api_base_for_model()` and server-side provider detection in `model_profiles.py`.

## Approaches Considered

### A. Agent Tool Primary, Conversation Mutation

Add agent-callable tools for model visibility and model setting. The setter validates against the Slice 1 allowed override set, stages a per-conversation model change during the current turn, and applies it before the next turn.

Pros:

- Matches the phase framing: the user speaks naturally; the agent acts.
- Does not require a new visual selector.
- Uses the existing per-conversation `Conversation.model` and `api_base` fields.
- Keeps profile switching out of scope.

Cons:

- Requires the tool to be conversation-aware; a generic dispatcher local tool cannot safely mutate the right conversation without extra context.
- Needs precise timing semantics so a tool call inside an active turn does not accidentally swap the model for later LLM rounds in that same turn.

Recommendation: use this as the primary path.

### B. Standalone Conversation Setter Endpoint

Add a nonce-gated endpoint such as `POST /agent/chat/model` for out-of-band setting by conversation id.

Pros:

- Simple for future fallback UI.
- Easy to test as an HTTP mutation route.
- Can reject active conversations with `409` because it is truly concurrent with any streaming turn.

Cons:

- If used as the primary path, it turns model choice into panel command plumbing instead of agent-mediated control.
- It does not by itself help the agent map "local Qwen" to an allowed override.

Recommendation: include as a secondary fallback and shared validation surface, but do not make it the primary UX.

### C. Restart/Re-Start Conversation With `model_override`

Keep `model_override` as start-time only and have the panel create a new conversation when a model changes.

Pros:

- Minimal mutation semantics.
- Avoids mid-conversation state changes.

Cons:

- It is a restart workflow, not "the agent has hands."
- Loses the continuity users expect when they ask to switch "this chat."
- Does not exercise the per-conversation model control infrastructure users asked for.

Rejected.

## Design Decision

Slice 2 uses Approach A as the primary path and Approach B as a secondary fallback.

Timing is:

- A model change applies to the current conversation's next turn.
- It does not change an in-flight completion.
- It does not change later LLM rounds inside the same active turn that requested the switch.
- The existing conversation history is preserved. The new model inherits prior messages. The switch point must be visible in panel text/status so the user knows which model answers from then onward.

## Server-Side Model Resolution

Add a shared resolver, likely in `mcp_server/src/rook/agent/chat/model_status.py` or a small adjacent module:

```python
@dataclass(frozen=True)
class ModelOverrideResolution:
    model_override: str
    api_base: str
    routing: str
    provider: str
    api_base_source: str


async def resolve_allowed_model_override(
    model_override: str,
    *,
    force_refresh: bool = False,
) -> ModelOverrideResolution:
    ...
```

The resolver is the only path that validates and binds routing for a requested override.

Validation rule:

- Build or reuse the current local-provider status through the Slice 1 async cache helper.
- Build `allowed_model_overrides` with `compute_allowed_model_overrides(local_providers, role_status=...)`.
- Reject the override if it is not in that set.
- Rejection shape:

```json
{
  "error": "Model override is not currently available. Refresh the model list and try again.",
  "code": "model_override_unavailable",
  "model_override": "ollama_chat/qwen3-coder:30b-a3b-q8_0"
}
```

Routing rule:

1. If `model_override` matches a detected LM Studio model in `local_providers["lmstudio"]["models"]`, use `local_providers["lmstudio"]["api_base"]` and mark `api_base_source: "detected_lmstudio"`.
2. Otherwise use `api_base_for_model(model_override, active_model_set.api_base)` and mark `api_base_source: "active_profile"`.
3. If no `api_base` is needed, store an empty string on the conversation and mark `api_base_source: "none"`.

This is the load-bearing fix for the LM Studio trap. A cloud active profile has no LM Studio `api_base`; detected `openai/<id>` LM Studio overrides must not route to real OpenAI by default. The client never supplies `api_base`.

## Conversation State

Extend `Conversation` with pending model state:

```python
pending_model: str = ""
pending_api_base: str = ""
pending_model_source: str = ""
pending_model_reason: str = ""
```

The active fields remain:

```python
model: str
api_base: str
```

Atomicity invariant:

- `model` and `api_base` are updated together through one helper, for example `Conversation.apply_model_override(resolution, source, reason)`.
- There is never a window where a local model is active with a stale cloud/profile `api_base`, or vice versa.

Turn-safety invariant:

- Agent-tool model setting during a turn writes only pending fields.
- Active `model/api_base` are applied after the active LLM/tool loop has finished and before `active_run_id` is cleared.
- Out-of-band setting mutates active fields only when `active_run_id is None`.
- Future code must not rely on today's implementation detail that `ChatRunner` copies `model/api_base` into `llm_kwargs` at call start. The model switch contract is "next turn," not "whenever the runner happens to read the fields."

## Agent Tools

Add two chat-local tools to the RookChat agent tool surface. These should be implemented as ChatRunner-intercepted pseudo-tools, like `ui_block`, or another conversation-aware path. They should not be generic Rhino bridge tools.

### `list_chat_models`

Purpose: let the agent map natural language requests like "my local Qwen" to allowed override strings.

Returns a compact version of the Slice 1 payload:

```json
{
  "active_profile": "cloud",
  "roles": {...},
  "local_providers": {...},
  "allowed_model_overrides": [...]
}
```

It may call `build_models_payload(builder=...)` and should use the same injected `PromptBuilder` as `/agent/chat/models`.

### `set_chat_model`

Parameters:

```json
{
  "model_override": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
  "reason": "User asked to use local Qwen for this chat"
}
```

Behavior when called by the agent during a turn:

- Validate through `resolve_allowed_model_override(...)`.
- On success, stage the pending model and return:

```json
{
  "success": true,
  "model_override": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
  "routing": "local",
  "api_base_source": "none",
  "applies_to": "next_turn",
  "message": "Model switch staged. The next user message in this conversation will use ollama_chat/qwen3-coder:30b-a3b-q8_0."
}
```

- Do not return `409` just because the turn is active. This path is inside the active turn by design.
- On validation failure, return the structured `model_override_unavailable` error in the tool result and include a short list of currently allowed overrides.

The agent's normal text reply should confirm the switch in plain language.

## HTTP Endpoints

### Existing `/agent/chat/start`

`POST /agent/chat/start` keeps accepting `model_override`, but now it must validate with the shared resolver before creating or finalizing the conversation model.

Rules:

- If `model_override` is absent, keep current persona resolution.
- If present, validate against `allowed_model_overrides`.
- Bind `api_base` with the shared resolver, including detected LM Studio `api_base`.
- Never accept `api_base` in the request body.
- On rejection, return `400` with the `model_override_unavailable` shape.

Implementation note: create the `Conversation` only after model validation succeeds, or stop/remove it on validation failure. Do not leave a rejected conversation in the store.

### New `/agent/chat/model`

Secondary fallback endpoint:

`POST /agent/chat/model`

Request:

```json
{
  "conversation_id": "conv_abc123",
  "model_override": "openai/lmstudio-community/Qwen3-Coder-30B",
  "reason": "panel fallback"
}
```

Behavior:

- Requires the same nonce gate as all mutating routes. `/agent/chat/health` remains the only nonce-exempt path.
- Rejects unknown conversations with `404`.
- Rejects missing `conversation_id` or `model_override` with `400`.
- Rejects if `conv.active_run_id is not None`:

```json
{
  "error": "Conversation already processing. Try again after the current turn finishes.",
  "code": "conversation_processing"
}
```

- If inactive, validates with the shared resolver and atomically applies active `model/api_base`.
- Returns the new conversation model status.

This endpoint is not the primary Slice 2 UX. It exists as a safe fallback for future panel controls and as an explicit mutation route for tests.

## Visibility And Panel Feedback

Slice 2 extends the Slice 1 feedback channel instead of creating a full selector UI.

### `/agent/chat/models` Conversation Section

`GET /agent/chat/models` should accept an optional `conversation_id` query parameter. When present and found, include:

```json
{
  "conversation": {
    "conversation_id": "conv_abc123",
    "persona": "architect",
    "active_model": "anthropic/claude-sonnet-4-6",
    "active_routing": "cloud",
    "pending_model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
    "pending_routing": "local",
    "pending_applies_to": "next_turn",
    "api_base_source": "none"
  }
}
```

If no pending switch exists, `pending_model` is `null`.

Do not expose raw `api_base` in the panel payload unless there is a diagnostic need. The source label is enough for normal users and avoids training UI code to reason about routing secrets/URLs.

### Streaming Refresh Cue

Add a lightweight `ChatEvent` type, for example `model_update`, emitted when the agent setter stages a model switch and again when the pending switch is applied at turn end.

Example staged event:

```json
{
  "type": "model_update",
  "content": "Model switch staged for next turn",
  "model": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
  "applies_to": "next_turn"
}
```

C# handling:

- `AgentChatClient` adds `GetModelsAsync(conversationId)` for `/agent/chat/models?conversation_id=...`.
- `AgentChatTab` stores the current conversation model label.
- On conversation start, after model-update events, and after turn completion, refresh model status.
- Display text-only feedback in the status label or a system message, such as `Model: ollama_chat/qwen3-coder:30b-a3b-q8_0 (next turn)` or `Model: ollama_chat/qwen3-coder:30b-a3b-q8_0`.

No dropdown or visual selector is required in Slice 2.

## Security Properties

- All model selection paths validate server-side against `allowed_model_overrides`.
- The client never supplies `api_base`.
- LM Studio `api_base` comes only from server-side detection.
- `/agent/chat/model` and `/agent/chat/start` are nonce-gated mutation routes.
- Agent tool setting still validates through the same server-side resolver; it is not trusted because "the agent called it."
- No sync local-provider detection path is reintroduced.

## Error Handling

Validation failure:

- Code: `model_override_unavailable`
- Message: "Model override is not currently available. Refresh the model list and try again."
- Tool result should include current allowed overrides so the agent can offer a valid alternative.

Stale cache:

- Same as validation failure. A model that was just started locally may not appear until the Slice 1 model list refreshes.
- Panel should refresh `/agent/chat/models` after a failure if the user is likely to have just started a provider/model.

Concurrent out-of-band set:

- Code: `conversation_processing`
- HTTP status: `409`
- Applies only to `/agent/chat/model`, not to the agent tool path.

Provider unavailable:

- Local providers remain represented in `local_providers` with `available: false` and `error`, as in Slice 1.

## Testing

Python tests:

- `/agent/chat/start` rejects unavailable `model_override`.
- `/agent/chat/start` accepts allowed profile/effective model overrides.
- `/agent/chat/start` accepts detected Ollama overrides.
- `/agent/chat/start` accepts detected LM Studio overrides and sets `conv.api_base` from `local_providers["lmstudio"]["api_base"]`.
- `/agent/chat/start` never accepts request body `api_base`.
- Agent-tool setter stages pending model during an active turn and does not return `409`.
- Staged agent-tool switch is applied before the next turn and not used by later LLM rounds in the current turn.
- `/agent/chat/model` rejects while active with `409`.
- `/agent/chat/model` applies immediately while inactive.
- `/agent/chat/model` is nonce-gated.
- `/agent/chat/models?conversation_id=...` reports active and pending conversation model status.

C# tests or focused manual verification:

- `AgentChatClient.GetModelsAsync(conversationId)` includes the nonce header.
- `AgentChatTab` refreshes text status after conversation start and model-update events.
- No visual selector is added.

Regression tests:

- No sync `get_cached_local_provider_status(...)` wrapper returns.
- `compute_allowed_model_overrides` remains explicit about `local_providers`.
- Existing Slice 1 helper tests continue to pass.

## Implementation Boundaries

Python files likely touched:

- `mcp_server/src/rook/agent/chat/model_status.py`
- `mcp_server/src/rook/agent/chat/conversation_store.py`
- `mcp_server/src/rook/agent/chat/chat_runner.py`
- `mcp_server/src/rook/agent/chat/server.py`
- `mcp_server/tests/test_chat_model_status.py`
- `mcp_server/tests/test_chat_server.py`

C# files likely touched:

- `src/Rook/UI/Chat/AgentChatClient.cs`
- `src/Rook/UI/Chat/AgentChatTab.cs`

Avoid changes to:

- Native routes.
- Model profile file writing.
- DSPy startup/reconfigure.
- Persistent knowledge/profile storage.

## Follow-Ups

- A future selector UI may call `/agent/chat/model`, but it must remain secondary to agent-mediated setting.
- Slice 3 must handle process-wide profile writes, config security, local detection cache invalidation after profile writes, and DSPy reconfiguration/liveness.
- The local-model tool-calling spike decides which local model/runtime/hardware cells are autonomous-grade. Slice 2 should not imply that a human-in-the-loop local chat override is autonomous-grade.
