# Rook Chat Model Visibility Design

## Goal

Ship Slice 1 of the public model-control work: a trustworthy, read-only model visibility contract for the RookChat panel. The endpoint must explain which models are effectively assigned to each role, which models power each persona, and which local models are currently selectable by later per-conversation override UI.

## Scope

Slice 1 adds a nonce-gated `GET /agent/chat/models` endpoint and the supporting Python helpers and tests. It does not add persistent profile writes, process-wide profile switching, or chat-panel selection UI.

Slice 2 will reuse the same helper for per-conversation `model_override` validation and UI selection. Slice 3, if built later, must solve persistent profile writes, DSPy reconfiguration, and cache invalidation.

## Existing Infrastructure

Rook already has the core model-routing infrastructure:

- `mcp_server/src/rook/agent/model_profiles.py` defines active profiles, local provider detection, and `api_base_for_model()`.
- `mcp_server/src/rook/agent/chat/server.py` already accepts `model_override` on `/agent/chat/start`.
- `PromptBuilder.resolve_model_and_base(persona)` is the source of truth for chat persona model resolution.
- `PlannerConfig.from_env()` applies `ROOK_PLANNER_MODEL` and `ROOK_WORKER_MODEL` over profile values.

The new endpoint must expose this infrastructure without inventing a second model-resolution path.

## Endpoint Contract

`GET /agent/chat/models`

Security:

- Requires `X-Rook-Session` when the chat server has a session nonce.
- Keeps `/agent/chat/health` as the only nonce-exempt path.
- Returns `Cache-Control: no-store`.

Response shape:

```json
{
  "active_profile": "cloud",
  "profile_source": "env",
  "roles": {
    "planner": {
      "profile_model": "anthropic/claude-opus-4-6",
      "effective_model": "anthropic/claude-opus-4-6",
      "source": "profile",
      "provider": "anthropic",
      "routing": "cloud",
      "api_base": null,
      "consumer": "PlannerConfig.planner_model"
    },
    "worker": {
      "profile_model": "anthropic/claude-sonnet-4-6",
      "effective_model": "anthropic/claude-sonnet-4-6",
      "source": "profile",
      "provider": "anthropic",
      "routing": "cloud",
      "api_base": null,
      "consumer": "PlannerConfig.worker_model"
    },
    "specialist": {
      "profile_model": "anthropic/claude-sonnet-4-6",
      "effective_model": "anthropic/claude-sonnet-4-6",
      "source": "profile",
      "provider": "anthropic",
      "routing": "cloud",
      "api_base": null,
      "consumer": "persona model_role"
    },
    "guardian": {
      "profile_model": "anthropic/claude-sonnet-4-6",
      "effective_model": "anthropic/claude-haiku-4-5-20251001",
      "source": "agent_config_default",
      "provider": "anthropic",
      "routing": "cloud",
      "api_base": null,
      "consumer": "GuardianConfig.llm_analysis_model",
      "enabled_by_default": false,
      "note": "Profile guardian role is defined, but spawned Guardian LLM analysis currently uses AgentConfig.guardian_llm_model."
    },
    "dspy": {
      "profile_model": "anthropic/claude-sonnet-4-6",
      "effective_model": "anthropic/claude-sonnet-4-6",
      "source": "configured_at_startup",
      "provider": "anthropic",
      "routing": "cloud",
      "api_base": null,
      "consumer": "DSPy global LM",
      "live_switchable": false
    }
  },
  "personas": [
    {
      "persona": "architect",
      "label": "Architect",
      "model_role": "worker",
      "resolved_model": "anthropic/claude-sonnet-4-6",
      "routing": "cloud"
    }
  ],
  "local_providers": {
    "ollama": {
      "available": true,
      "models": [
        {
          "id": "qwen3-coder:30b-a3b-q8_0",
          "model_override": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
          "size": 30000000000
        }
      ],
      "recommended_model_override": "ollama_chat/qwen3-coder:30b-a3b-q8_0",
      "error": null
    },
    "lmstudio": {
      "available": false,
      "models": [],
      "recommended_model_override": null,
      "api_base": "http://127.0.0.1:1234/v1",
      "error": "connection refused"
    }
  },
  "allowed_model_overrides": [
    "anthropic/claude-opus-4-6",
    "anthropic/claude-sonnet-4-6",
    "ollama_chat/qwen3-coder:30b-a3b-q8_0"
  ]
}
```

## Resolution Rules

The role builder must mirror real runtime consumers:

- `planner` uses the active profile planner model, overridden by `ROOK_PLANNER_MODEL`.
- `worker` uses the active profile worker model, overridden by `ROOK_WORKER_MODEL`.
- `specialist` uses the active profile specialist model.
- `guardian` reports the profile guardian model separately from the current spawned Guardian analysis model. Today the profile value is dead config for spawned Guardian analysis; track a follow-up to either wire it into `GuardianConfig` or remove the profile field before Slice 3.
- `dspy` reports the profile DSPy model as the configured-at-startup model, with `live_switchable: false`.
- `personas[].resolved_model` must be produced by `PromptBuilder.resolve_model_and_base(persona)`, the same method used by `/agent/chat/start`.

`profile_source` values:

- `env`: `ROOK_MODEL_PROFILE` selected the profile.
- `file`: `knowledge/model_profiles.json` selected the profile.
- `fallback`: no profile file or unknown profile caused hardcoded fallback behavior.

`provider`, `routing`, and `api_base` must be derived from `api_base_for_model()` instead of hand-labeled. `routing` is `local` when `api_base_for_model()` returns a base or the model uses the `ollama_chat/` or `ollama/` prefixes; otherwise it is `cloud`.

## Local Detection And Allowed Overrides

The endpoint should fold local provider detection into the same response. Detection must be bounded and cached:

- Probe Ollama and LM Studio concurrently.
- Use short per-probe timeouts.
- Always return a `local_providers` object, even on timeout or connection failure.
- Cache local detection for a short TTL, about 30-60 seconds.

`allowed_model_overrides` is defined as:

> the active profile's effective, env-aware role models union detected local `model_override` strings.

The helper that computes this set must be shared with `/agent/chat/start` in Slice 2. `/start` should validate `model_override` against the cached allowed set and should not probe local providers synchronously.

Slice 2 stale-cache rejection response:

```json
{
  "error": "Model override is not currently available. Refresh the model list and try again.",
  "code": "model_override_unavailable",
  "model_override": "ollama_chat/qwen3-coder:30b-a3b-q8_0"
}
```

## Testing

Slice 1 tests should cover:

- `/agent/chat/models` returns the expected top-level fields.
- `ROOK_PLANNER_MODEL` and `ROOK_WORKER_MODEL` are reflected in `roles.*.effective_model`.
- `allowed_model_overrides` includes effective env-aware role models.
- Persona rows are resolved through `PromptBuilder.resolve_model_and_base()`.
- Local provider probe failures do not fail the endpoint.
- Session nonce enforcement applies to `/agent/chat/models`.
- `Cache-Control: no-store` is present.

## Follow-Ups

- Decide whether the profile `guardian` role should wire into spawned Guardian analysis or be removed from the profile schema.
- In Slice 2, add per-conversation selector UI using `allowed_model_overrides` and existing `/start` `model_override`.
- In Slice 3, if persistent profile writes are added, invalidate the local detection cache after profile writes and reconfigure DSPy or make DSPy liveness limitations explicit in UI.
