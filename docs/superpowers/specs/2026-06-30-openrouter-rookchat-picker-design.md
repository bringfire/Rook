# Spec B — RookChat OpenRouter-aware Model Picker

## Status

Design for review. This is **Spec B** of the "add Codex CLI + OpenRouter support to
Rook" effort. **Spec A** (OpenRouter as a first-class LiteLLM provider + catalog +
`openrouter_refresh_catalog` MCP tool) is merged to `main` (PR #385, commit `1e07010d`).
Spec B turns Spec A's curated-favorites catalog into a usable model picker in RookChat.

The Chirp per-component `model` param is **tracked separately** — it requires a coordinated
change in the separate Chirp adapter repo (the adapter bakes the model into the generated
C# script) and gets its own spec/contract/tests. It is **out of scope here.**

## Goal

Surface curated OpenRouter favorites — with metadata and tool-capability gating — in the
existing RookChat model dropdown, so a user can select and apply an `openrouter/` model for
a conversation. This closes the deferred Spec A Tier-2 check: a RookChat turn on an
`openrouter/` model.

## Non-Goals

- **No new MCP tool.** This is endpoint + UI enrichment, not a new tool. The
  FULL/LEAN/READONLY surface counts and the `targeting.py` / `mcp_tool_profiles.py`
  dual-layer classification are therefore untouched.
- **No network on the chat path.** Options are built only from disk/config state:
  curated favorites + cached catalog metadata (`OpenRouterCatalog.load()`, pure-disk).
  Catalog refresh remains the `openrouter_refresh_catalog` MCP tool. No live discovery.
- **No Chirp changes** (separate spec, separate repo).
- No process-wide profile writes, no DSPy reconfiguration, no Guardian/planner/worker
  routing changes, no client-supplied `api_base`.
- `ClaudeCodeTab` is untouched (it has no per-conversation model concept).
- No change to the agent-mediated `set_chat_model` path being the primary UX; the panel
  dropdown remains the secondary control.

## Existing Ground Truth (verified on `main`, HEAD `1e07010d`)

- `model_status.build_models_payload()` (`model_status.py:476`) returns a payload whose
  top-level `allowed_model_overrides` is a flat `list[str]` built by
  `compute_allowed_model_overrides()` from **role effective-models + local-provider model
  overrides**. OpenRouter favorites are **not** surfaced today.
- `compute_allowed_model_overrides()` (`model_status.py:392`) and
  `resolve_allowed_model_override()` (`model_status.py:428`, → `_bound_routing`) are the
  authoritative applyable-set + Apply-validation path. `resolve_allowed_model_override`
  raises `ModelOverrideUnavailable` for anything not in the allowed set.
- `OpenRouterCatalog.load()` (`providers/openrouter_catalog.py:122`) returns a `CatalogView`
  of `ModelMetadata` (`litellm_id`, `supported_parameters` incl. `"tools"`, `pricing`,
  `context_length`, `display_name`, `metadata_state` ∈ `known`/`stale`/`unknown`) plus
  `cache_present`, `fetched_at`, `stale`, `last_refresh_error`. Pure-disk.
- `api_base_for_model()` returns `None` for `openrouter/` (it is in `_NATIVE_CLOUD_PREFIXES`)
  → an `openrouter/` model binds as `routing="cloud"`, empty `api_base` through the existing
  `_bound_routing`. `api_key_env_for_model()` returns `"OPENROUTER_API_KEY"` for
  `openrouter/` and is the provider-agnostic credential-presence probe.
- C# `ChatModelsInfo.AllowedModelOverrides` is `List<string>` (`AgentChatClient.cs:78`). The
  Slice 2.1 dropdown shipped in `AgentChatTab.cs` (`_modelDropDown`, populated from
  `allowed_model_overrides`, `ShouldEnableApply`, Apply button, `RefreshModelStatusAsync`).
  Eto `DropDown` cannot disable individual rows.
- chat_runner's agent loop is tool-calling (`set_chat_model` / `list_chat_models`
  pseudo-tools, `tool_choice="auto"`) — a model lacking `"tools"` genuinely cannot drive it.
- Curated favorites today: a single tool-capable entry
  `openrouter/anthropic/claude-sonnet-4.6` (`knowledge/openrouter_favorites.json`).

## Architecture

A single Python eligibility computation feeds both the model-status payload and the Apply
resolver, so the UI and the server can never drift. The C# side gains an enriched DTO and
filters it for display; the legacy string field is preserved for backward-compat.

### The two contract fields and their invariant

- `allowed_model_overrides: list[str]` — **unchanged shape**, remains the *authoritative
  applyable ID list*. Its membership grows to include eligible favorites. Current clients
  keep working.
- `allowed_model_override_options: list[object]` — new, descriptive/enriched. One entry per
  model ID across all sources.

**Invariant (asserted in tests):** the set of IDs in `allowed_model_overrides` equals the
set of option IDs with `eligibility == "eligible"`. Every OpenRouter favorite that is
**absent** from `allowed_model_overrides` appears in `allowed_model_override_options` with
`eligibility == "ineligible"` and a non-null `ineligible_reason`.

### Option schema

```jsonc
{
  "id": "openrouter/anthropic/claude-sonnet-4.6",  // litellm id
  "display_name": "Anthropic: Claude Sonnet 4.6",  // metadata name, else id
  "source": "openrouter_favorite",                 // "role" | "local" | "openrouter_favorite"
  "supports_tools": true,                           // capability FACT: true | false | null
  "eligibility": "eligible",                        // picker/apply STATUS: "eligible" | "ineligible"
  "ineligible_reason": null,                        // "missing_api_key" | "missing_tools" | "unknown_capability" | null
  "metadata_state": "known",                        // "known" | "stale" | "unknown" | "not_applicable"
  "pricing": { "prompt": "...", "completion": "..." }, // when known, else null
  "context_length": 200000                          // when known, else null
}
```

`supports_tools` (capability) and `eligibility` (apply status) are **distinct axes**:
"not eligible" must never be read as "not tool-capable." A tool-capable model with no key is
`supports_tools: true, eligibility: "ineligible", ineligible_reason: "missing_api_key"`.

### Catalog status block

The payload also carries an `openrouter_catalog` block passed through from the `CatalogView`:
`{ cache_present, fetched_at, stale, last_refresh_error }`. This lets the UI/agent hint
"run `openrouter_refresh_catalog`" when the cache is empty or stale, without itself fetching.

## Eligibility model (Python — single source of truth)

Capability gating applies **only to OpenRouter favorites**, because only they carry catalog
metadata. Role effective-models and local-provider models are **not** tools-gated: this
preserves existing trust boundaries (the system has no reliable capability metadata for those
sources today) and is **not** a claim that they are always tool-capable.

For each OpenRouter favorite (litellm id from `OpenRouterCatalog.load()`). `supports_tools` is
always the capability fact from metadata, computed independently of credentials.
`ineligible_reason` is assigned by **precedence, capability before credentials:**
`unknown_capability` → `missing_tools` → `missing_api_key` (rows below are in that order and
are mutually exclusive):

| Condition (first match wins) | `supports_tools` | `eligibility` | `ineligible_reason` | `metadata_state` |
|---|---|---|---|---|
| Not in cache (`metadata_state=="unknown"`) | `null` | ineligible | `unknown_capability` | `unknown` |
| Known/stale metadata, `"tools"` **absent** from `supported_parameters` | `false` | ineligible | `missing_tools` | `known`/`stale` |
| `"tools"` present, but key env named by `api_key_env_for_model(id)` is absent | `true` | ineligible | `missing_api_key` | `known`/`stale` |
| `"tools"` present and key present, metadata `known` | `true` | eligible | `null` | `known` |
| `"tools"` present and key present, metadata **stale** | `true` | eligible | `null` | `stale` |

Notes:
- **Capability and credentials are distinct axes.** `supports_tools` reflects the metadata
  fact (`true`/`false`/`null`) and is never coerced by key state; a tool-capable model with
  no key is `supports_tools:true, eligibility:"ineligible", ineligible_reason:"missing_api_key"`.
- **`unknown` capability is never treated as tool-capable.**
- **Stale-with-tools stays eligible** as a pragmatic compatibility tradeoff, **not** a
  confidence claim. It is marked `metadata_state="stale"` so the UI keeps refresh guidance
  visible. If the provider has since removed tool support, the live Apply/chat turn may fail
  — that is acceptable residual risk.

Role/local options are emitted with `source` `"role"`/`"local"`, `eligibility="eligible"`,
`supports_tools=null`, `metadata_state="not_applicable"`.

### Deduplication / merge

Options are deduped to **one entry per model ID**. If the same litellm id arrives from both a
role/local source and an OpenRouter favorite (e.g. a profile role is set to an `openrouter/`
model that is also favorited), the **role/local entry wins** (ungated, eligible). No duplicate
dropdown rows. `display_name` may still be enriched from catalog metadata when available.

### Shared helper

A single function — `compute_model_override_options(role_status, local_providers,
catalog_view) -> list[ModelOverrideOption]` — produces the deduped option list. Both
consumers derive from it:

- `build_models_payload` emits `allowed_model_override_options` (the options) and
  `allowed_model_overrides` (`sorted({o.id for o in options if o.eligibility == "eligible"})`).
- `resolve_allowed_model_override` computes the same options, then:
  - id eligible → bind routing via existing `_bound_routing` (openrouter/ → cloud, no
    api_base);
  - id is a known-but-ineligible option → raise a **specific** error carrying the
    `ineligible_reason` (new variant / field on `ModelOverrideUnavailable`, e.g.
    `code: "model_not_tool_capable"` for `missing_tools`, surfaced with the reason);
  - id unknown → existing generic `model_override_unavailable`.

`compute_allowed_model_overrides()` is refactored to derive from the shared helper (or kept as
a thin wrapper returning the eligible ids) so there is exactly one eligibility code path.

## C# changes

### `AgentChatClient.cs`

- New `ModelOverrideOption` DTO: `Id`, `DisplayName`, `Source`, `SupportsTools` (`bool?`),
  `Eligibility`, `IneligibleReason`, `MetadataState`, `Pricing` (raw `JsonElement?`),
  `ContextLength` (`int?`), with `[JsonPropertyName]` snake_case bindings.
- `ChatModelsInfo.AllowedModelOverrideOptions: List<ModelOverrideOption>` (new).
  **Keep** `AllowedModelOverrides: List<string>` (backward-compat).
- `SetModelResult` / `ParseSetModelResult` already parse `code`/`error`; the new
  `model_not_tool_capable` code flows through unchanged and is mapped to a clear status
  message in the tab.

### `AgentChatTab.cs`

- `RefreshModelStatusAsync` populates `_modelDropDown` from `AllowedModelOverrideOptions`
  filtered to `eligibility == "eligible"`: `Key = Id`, `Text = DisplayName` (fall back to
  `Id`), with a tooltip carrying provider / context_length / pricing / a "metadata stale —
  refresh" note when `metadata_state == "stale"`.
- **Graceful degrade:** if `AllowedModelOverrideOptions` is empty/absent (older backend),
  fall back to the legacy `AllowedModelOverrides` strings exactly as today.
- Active model still guaranteed present (prepend if the eligible set omits it), preserving
  the current contract that the control reflects the true active model.
- Pure, Eto-free helpers for unit testing: `EligibleOptions(options)` (filter) and a
  label/tooltip builder. `ShouldEnableApply` is unchanged.

## Testing

### Python (`tests/test_chat_model_status.py`, `tests/test_chat_server.py`)

- Eligibility computation, each row of the table above, using temp favorites + cache files
  (`load()` accepts paths): eligible, `missing_tools`, `unknown_capability`,
  `missing_api_key` (with `supports_tools` still reflecting capability), stale-with-tools
  (eligible + `metadata_state="stale"`), stale-without-tools (`missing_tools`).
- **Invariant test:** `{o.id for o in options if eligible} == set(allowed_model_overrides)`;
  every favorite absent from `allowed_model_overrides` has a non-null `ineligible_reason`.
- **No-regression:** role + local overrides still present in both fields, never tools-gated.
- Dedup: role + favorite collision on one id yields a single option, role precedence.
- Catalog-status passthrough (`cache_present`/`fetched_at`/`stale`/`last_refresh_error`),
  including the empty-cache case.
- Apply resolver: forcing a `missing_tools` favorite raises the specific
  `model_not_tool_capable` error; forcing an unknown id raises generic
  `model_override_unavailable`; an eligible favorite binds `routing="cloud"`, empty api_base.
- No network: tests assert `load()`/disk only on the chat path (no `refresh()` / httpx).

### C# (`src/Rook.Tests/UI/Chat/`)

- `EligibleOptions` filter (mixed eligible/ineligible), label/tooltip builder (display_name
  fallback to id, stale note), structured-absent → legacy fallback path.
- `ParseSetModelResult` maps the `model_not_tool_capable` body to `ErrorCode`.

Surface-count tests are **not** touched (no MCP tool added). Verify with
`pytest mcp_server/tests/test_chat_model_status.py mcp_server/tests/test_chat_server.py` and
`dotnet test src/Rook.Tests/Rook.Tests.csproj`. Do not claim native (C++) build verification.

## Live Tier-2 validation (closes deferred Spec A item #3)

Per `docs/openrouter-live-smoke.md`. Deploy
`scripts/deploy-local-testing.ps1 -PayloadOnly -AllowRunning` (Python-only; runtime runs from
`LocalAppData/Rook`), ensure `OPENROUTER_API_KEY` is in
`LocalAppData/Rook/app/mcp_server/.env`, run `openrouter_refresh_catalog` (MCP) to populate
the cache, `/mcp` reconnect. Then in the RookChat panel: `openrouter/anthropic/claude-sonnet-4.6`
appears in the dropdown with a friendly label → Apply → send a turn → confirm it routes through
`openrouter/` (chat-server / trace evidence). Run before opening the PR.

## Files Touched

- `mcp_server/src/rook/agent/chat/model_status.py` — `ModelOverrideOption` dataclass,
  `compute_model_override_options` shared helper, enriched `build_models_payload`
  (+`allowed_model_override_options`, `openrouter_catalog` block), refactored
  `compute_allowed_model_overrides`, enriched `resolve_allowed_model_override` +
  `ModelOverrideUnavailable` specific reason. Consumes `providers/openrouter_catalog.load()`
  and `model_profiles.api_key_env_for_model`.
- `src/Rook/UI/Chat/AgentChatClient.cs` — `ModelOverrideOption` DTO,
  `ChatModelsInfo.AllowedModelOverrideOptions`.
- `src/Rook/UI/Chat/AgentChatTab.cs` — dropdown population from options + tooltip + fallback,
  pure `EligibleOptions` / label helpers.
- `mcp_server/tests/test_chat_model_status.py`, `mcp_server/tests/test_chat_server.py`,
  `src/Rook.Tests/UI/Chat/` — tests above.

Avoid changes to: native (C++) routes, `targeting.py` / `mcp_tool_profiles.py`, MCP tool
defs, model-profile persistence, DSPy startup/reconfigure, `ClaudeCodeTab` behavior, the
catalog `refresh()`/network path. Do not edit historical `docs/superpowers/` specs/plans.

## Acceptance Criteria

- Eligible OpenRouter favorites appear in the existing RookChat dropdown with usable labels.
- Ineligible favorites never produce broken chat sessions (excluded from the dropdown;
  rejected server-side with a clear reason if forced).
- The Python/C# contract stays compatible for existing consumers (`allowed_model_overrides`
  shape and the role/local membership preserved).

## Follow-Ups

- Chirp per-component `model` param (separate spec; coordinates with the Chirp adapter repo).
- A future chooser/knowledge-store slice may own online model discovery; this picker stays a
  pure consumer of disk/config state.
