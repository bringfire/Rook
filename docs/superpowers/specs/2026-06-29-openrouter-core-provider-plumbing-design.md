# OpenRouter Core Provider Plumbing — Design Spec (Spec A)

- **Date:** 2026-06-29
- **Branch / worktree:** `feature/codex-openrouter` @ `.worktrees/codex-openrouter` (off `origin/main` `a62854fb`)
- **Status:** Draft, pending review (brainstorming gate)
- **Authors:** bringfire (lead), Claude (senior engineer), Codex (senior reviewer) — three-way design session
- **Related specs (not this one):**
  - **Spec B — RookChat model-metadata picker** (richer `/agent/chat/models` contract, C# DTO/UI, tool-capability filtering, pricing/context display, backward-compat for `List<string>`).
  - **Spec C — Codex CLI tab** (mirror of the Claude CLI tab; protocol decision `app-server` vs `exec --json` behind a wrapper seam — headline risk item, not pre-decided).

---

## 1. Context & goal

Rook routes all LLM calls through LiteLLM. Three direct `litellm.acompletion()` call sites
([base_agent.py](../../../mcp_server/src/rook/agent/base_agent.py),
[chat_runner.py](../../../mcp_server/src/rook/agent/chat/chat_runner.py),
[guardian.py](../../../mcp_server/src/rook/agent/guardian.py)) plus DSPy
([dspy_config.py](../../../mcp_server/src/rook/learning/dspy_config.py)) bottom out at LiteLLM.
Model routing is centralized in [model_profiles.py](../../../mcp_server/src/rook/agent/model_profiles.py)
(`ModelSet` roles `planner`/`worker`/`specialist`/`guardian`/`dspy`, profiles in
`knowledge/model_profiles.json`, `api_base_for_model()` as the cloud-vs-local enforcement point).

OpenRouter is a native LiteLLM provider (`openrouter/...`, reads `OPENROUTER_API_KEY`, base
`https://openrouter.ai/api/v1`). This spec makes OpenRouter a first-class, robust provider for
Rook's existing model-selection paths — **without any new UI** — and produces the curated
model-catalog data contract that Spec B's picker will consume.

### Goal / success criterion

A user sets `OPENROUTER_API_KEY`, and a curated `openrouter/...` model routes correctly through the
**existing** selection paths — a `model_profiles.json` role (including the `dspy` role),
`ROOK_*_MODEL` env override, and `chirp_create(model=...)` — proven by deterministic tests, with no
new UI. The curated favorites + a refreshable metadata cache form the data contract Spec B inherits.

---

## 2. Scope & non-goals

### In scope
- `openrouter/` routing fix + regression test.
- Provider-aware cloud key resolution (removes the hardcoded `ANTHROPIC_API_KEY` assumption that
  blocks any non-Anthropic cloud provider on the `dspy` role).
- `OPENROUTER_API_KEY` env documentation + **optional** runtime-health reporting.
- `OpenRouterCatalog` reusable service (`refresh()` networked, `load()` pure-disk).
- Curated favorites file (human-authored) + generated metadata cache (refreshable).
- `openrouter_refresh_catalog` MCP tool (thin wrapper over the service).
- Chirp **confirmation** (test + doc) that `openrouter/...` routes via `OPENROUTER_API_KEY`.
- Deterministic, fixture-backed tests; one gated (non-CI) live smoke.

### Explicit non-goals (deferred to Spec B / Spec C)
- No `/agent/chat/models` enrichment, no C# DTO/UI, no badges/filtering — **Spec B**.
- No `chirp_create` favorites wiring (Chirp keeps accepting arbitrary model strings) — Spec B-adjacent.
- No background/automatic refresh; no network during chat startup or runtime routing.
- No chat-server HTTP endpoint (the picker layer is Spec B).
- No Codex CLI tab work — **Spec C**.

---

## 3. Architecture

### 3.1 New module — `mcp_server/src/rook/providers/openrouter_catalog.py`

A reusable, network-bounded service. Pure Python, testable without Rhino.

- `refresh(api_key=None) -> RefreshResult` — the **only** networked path. Resolves `OPENROUTER_API_KEY`
  (arg or env), `GET https://openrouter.ai/api/v1/models`, atomically writes the cache, returns a
  structured result. Never raises on network/auth/JSON failure — returns `success=false`.
- `load() -> CatalogView` — **pure-disk, never networks.** Reads favorites + cache; returns each
  curated model tagged with metadata, or `unknown` when the cache is missing/corrupt/schema-mismatched or
  a favorite is absent. A **stale** cache returns metadata **with stale provenance** (not `unknown`) — see
  §8. This is the contract Spec B consumes.
- ID normalization helpers (provider-specific, live here — not in the routing module):
  - `to_litellm_id(catalog_id) -> str` → prepends the single leading `openrouter/` segment.
  - `to_openrouter_id(litellm_id) -> str` → strips the single leading `openrouter/` segment.
  - Rationale: OpenRouter's `/api/v1/models` returns bare IDs (`anthropic/claude-x`, `canonical_slug`),
    while LiteLLM/favorites use `openrouter/anthropic/claude-x`. Named helpers so Spec B's picker never
    reimplements prefix stripping.
  - Edge (documented, not special-cased in v1): variant suffixes (`:nitro`, `:floor`) and
    `openrouter/auto` are part of the id and matched verbatim.

`RefreshResult` fields (returned by the service and surfaced by the MCP tool):
`success`, `models_fetched`, `favorites_matched`, `cache_path`, `source_endpoint`, `fetched_at`,
`last_refresh_error`, `unknown_favorites`.

### 3.2 Data files — split by volatility

- **`knowledge/openrouter_favorites.json`** — **checked in**, human curation only:
  ```json
  [ { "id": "openrouter/anthropic/claude-3.7-sonnet", "notes": "default planner", "tags": ["planner"] } ]
  ```
  IDs are in LiteLLM form. No volatile metadata.

- **Generated cache — `knowledge/generated/openrouter_catalog_cache.json`** — gitignored, written to the
  runtime-writable knowledge path (via the existing `resolve_*_knowledge_path` helper). Carries
  `schema_version`; **safe to delete/ignore** at any time. Keyed by LiteLLM id; preserves
  `openrouter_id` + `canonical_slug`. (Full schema in §5.)

`knowledge/generated/` is added to `.gitignore`.

### 3.3 New MCP tool — `openrouter_refresh_catalog`

Thin wrapper over `OpenRouterCatalog.refresh()`, registered in `server.py`. Returns the `RefreshResult`
fields. The user (via Claude) or an agent triggers it explicitly ("refresh the OpenRouter catalog").
A CLI convenience over the same service may be added only if near-free; the MCP tool is the primary
Spec A surface.

### 3.4 Shared helper — `api_key_env_for_model(model, profile_api_base=None) -> str | None`

Lives in [model_profiles.py](../../../mcp_server/src/rook/agent/model_profiles.py) alongside
`_NATIVE_CLOUD_PREFIXES` / `api_base_for_model` (the routing-knowledge home). **Conservative and
routing-aware** — maps only single-env-var providers; never invents a `FOO_API_KEY`:

| Model | Result |
|---|---|
| `openrouter/...` | `OPENROUTER_API_KEY` |
| `anthropic/...` | `ANTHROPIC_API_KEY` |
| real-cloud `openai/...` (e.g. `openai/gpt-4`, `o1`, `o3`) | `OPENAI_API_KEY` |
| local `openai/...` **with** profile `api_base` (LM Studio) | `None` |
| `ollama*` | `None` |
| `azure/`, `bedrock/`, `gemini/`/Vertex, unknown/multi-auth | `None` (let LiteLLM/DSPy surface provider-specific auth errors) |

It shares the exact `openai/` cloud-vs-local disambiguation `api_base_for_model` already uses, so the
two cannot drift.

### 3.5 Existing-code touch-points (four)

1. **Routing** — add `"openrouter/"` to `_NATIVE_CLOUD_PREFIXES` in
   [model_profiles.py](../../../mcp_server/src/rook/agent/model_profiles.py) + the profile-`api_base`-present
   regression test. (Without the fix, `openrouter/` is misclassified as local **only** when a profile-level
   `api_base` is present — exactly the mixed-profile case `_NATIVE_CLOUD_PREFIXES` exists to handle.)
2. **DSPy provider-aware key resolution** *(load-bearing)* — **both** `configure_dspy()` **and**
   `configure_dspy_for_optimization()` (teacher + student) replace their hardcoded `ANTHROPIC_API_KEY`
   demand with `api_key_env_for_model(model, profile_api_base)`: validate/fail-fast on *that* provider's
   key with a provider-correct message; `dspy.LM(model)` then lets LiteLLM read the resolved key. An
   explicit `api_key=` argument remains a valid override — validation fails **only** when no explicit
   `api_key` is passed **and** the provider's env var is absent.
   (`base_agent.py`/`chat_runner.py`/`guardian.py` need no change — they never hardcoded the key.)
3. **Config / health — optional, never degrading** — `OPENROUTER_API_KEY` added to
   [.env.example](../../../mcp_server/.env.example). [runtime_health.py](../../../mcp_server/src/rook/agent/chat/runtime_health.py)
   reports known provider keys as an **informational/optional** map, and the existing `llm.configured`
   boolean is gated on **the active/effective model's** provider key (via the helper), not on all keys.
4. **Chirp** — confirmation test + doc only (no `chirp_create` favorites wiring), proving `openrouter/...`
   routes via `OPENROUTER_API_KEY` through DSPy→LiteLLM in
   [adapter.py](../../../../Chirp/src/chirp/adapter.py).

---

## 4. Data flows

1. **Curate** (human, no network): hand-edit `openrouter_favorites.json` — add `openrouter/...` IDs +
   optional notes/tags.
2. **Refresh** (explicit, the only networked path): `openrouter_refresh_catalog` →
   `OpenRouterCatalog.refresh()` → resolve `OPENROUTER_API_KEY` → `GET /api/v1/models` → normalize IDs →
   atomic write (temp + `os.replace`) of the full catalog metadata keyed by LiteLLM id (so Spec B's future
   browse needs no re-fetch) → return counts + provenance + `unknown_favorites`.
3. **Select & route** (runtime, network-free): an `openrouter/...` model set via profile role /
   `ROOK_*_MODEL` / `chirp_create(model=)` resolves through `api_base_for_model → None`, and — for the
   `dspy` role — `api_key_env_for_model → OPENROUTER_API_KEY` validation, then LiteLLM routes.
   **`load()` metadata is never consulted for routing.**

---

## 5. Cache schema

Single generated file. `schema_version` guards forward-compat; mismatch is treated as **missing**.

### Success
```json
{
  "schema_version": 1,
  "source_endpoint": "https://openrouter.ai/api/v1/models",
  "fetched_at": "2026-06-29T17:04:00Z",
  "last_refresh_attempt_at": "2026-06-29T17:04:00Z",
  "last_refresh_error": null,
  "models": {
    "openrouter/anthropic/claude-3.7-sonnet": {
      "openrouter_id": "anthropic/claude-3.7-sonnet",
      "canonical_slug": "anthropic/claude-3.7-sonnet",
      "supported_parameters": ["tools", "tool_choice", "..."],
      "pricing": { "prompt": "...", "completion": "..." },
      "context_length": 200000,
      "display_name": "Anthropic: Claude 3.7 Sonnet"
    }
  }
}
```

### Failure header semantics (resolves the observability-vs-intact contradiction)
- `fetched_at` = timestamp of the last **successful** fetch (unchanged on failure; `null` if never).
- `last_refresh_attempt_at` = timestamp of the last attempt (success or failure).
- `last_refresh_error` = `{ "code": "...", "message": "..." }` on failure, `null` on success.
- A failed refresh **preserves the prior `models` payload** and atomically updates only the provenance
  header.
- **No trusted prior data** — first-ever failure, OR existing cache corrupt / `schema_version`-mismatched
  — writes a **status-only** cache: `fetched_at: null`, `models: {}`, `last_refresh_attempt_at: <ts>`,
  `last_refresh_error: {code, message}`. Every write is atomic.

---

## 6. Invariants

- **I1 — Routing is network-independent.** Missing/stale/corrupt cache never blocks routing a configured
  `openrouter/` model.
- **I2 — Single networked path.** `refresh()` is the only code that networks; `load()` and routing never do.
- **I3 — Optional-provider health.** A missing `OPENROUTER_API_KEY` never degrades `llm.configured` for a
  non-OpenRouter active model (Anthropic-only users stay green).
- **I4 — Failure observability with data preservation.** A failed refresh preserves prior catalog data and
  updates only the provenance header (§5). No-trusted-prior-data failures write a status-only cache. All
  writes atomic.
- **I5 — Helper conservatism.** `api_key_env_for_model` never invents an env var; unknown/multi-auth → `None`.
- **I6 — `openai/` disambiguation preserved.** Cloud → `OPENAI_API_KEY`; local + `api_base` → `None`
  (LM Studio unbroken).
- **I7 — Cache is disposable.** Deleting the generated cache is always safe; `schema_version` mismatch is
  treated as missing.

---

## 7. Error handling

`refresh()` returns structured `success=false` with `last_refresh_error: {code, message}` (never crashes)
for: network timeout / connection error, OpenRouter `401` (auth), malformed catalog JSON, missing
`OPENROUTER_API_KEY`. In all cases the prior `models` payload is preserved (or status-only written per I4).
`unknown_favorites` (curated IDs absent from the catalog — typos / delisted models) is a surfaced warning,
not fatal.

---

## 8. Test matrix

Deterministic, fixture-backed, **zero live network** (HTTP mocked; a trimmed real `/models` response is
checked in as a fixture).

### Routing
- `api_base_for_model("openrouter/x")` → `None`.
- `api_base_for_model("openrouter/x", profile_api_base="http://...")` → `None` *(the flagged mixed-profile case)*.
- Unchanged: `openai/gpt-4` → `None`; `openai/lmstudio-model` + `api_base` → `api_base`.

### Helper `api_key_env_for_model`
- `openrouter/` → `OPENROUTER_API_KEY`; `anthropic/` → `ANTHROPIC_API_KEY`; `openai/gpt-4` → `OPENAI_API_KEY`.
- **`openai/lmstudio-model` + profile_api_base → `None`** (LM Studio guard).
- `ollama_chat/` → `None`; `azure/`, `bedrock/`, `gemini/` → `None`.

### DSPy
- `configure_dspy("openrouter/…")` w/ `OPENROUTER_API_KEY` → configures, no Anthropic demand.
- `configure_dspy("openrouter/…")` missing key → raises, message names `OPENROUTER_API_KEY`.
- **`configure_dspy_for_optimization` teacher + student `openrouter/…`** → same (both paths).
- `configure_dspy("anthropic/…")` missing `ANTHROPIC_API_KEY` → still raises (back-compat).
- **Explicit `api_key` override:** `configure_dspy("openrouter/…", api_key=...)` with the env var absent →
  succeeds; same for `configure_dspy_for_optimization`.
- `configure_dspy(local/ollama)` → no key demanded (back-compat).

### Health
- Anthropic-only env (no `OPENROUTER_API_KEY`), active `anthropic/` → `llm.configured = True` (**I3**).
- Active `openrouter/` + key → `True`; active `openrouter/` no key → `False`, message names the key.
- Provider keys always reported as an informational map.

### Catalog service
- `refresh()` vs fixture → cache + provenance + counts correct.
- **ID normalization:** fixture `id: "anthropic/claude-x"` matches favorite `openrouter/anthropic/claude-x`
  and is **not** in `unknown_favorites`.
- Missing `OPENROUTER_API_KEY` → `success=false`; prior `models` preserved with error provenance, or
  status-only cache written when no trusted prior data exists (per I4).
- HTTP / JSON error → `success=false`, **prior cache `models` intact**, header updated.
- **Failed refresh after a good cache preserves the exact `models` payload**, updating only provenance.
- **First-ever failed refresh writes status-only cache** (`fetched_at: null`, `models: {}`) without crashing `load()`.
- **Corrupt / schema-mismatched existing cache + failed refresh → status-only write** (same as first-ever).
- `load()` present → metadata; missing → `unknown` (routing unaffected); stale → flagged stale but returned;
  bad `schema_version` → treated as missing, no crash.

### Chirp
- Adapter resolves `openrouter/` model w/ `OPENROUTER_API_KEY` (dspy.LM mocked) → no Anthropic demand,
  correct model string passed.

### Live smoke *(gated, documented, not CI)*
- One real `refresh()` + one cheap `openrouter/` chat call — per the repo's live-smoke-before-PR practice.

---

## 9. References

- OpenRouter models API (bare `id` / `canonical_slug`, no `openrouter/` prefix; `pricing`,
  `supported_parameters`, `context_length`): <https://openrouter.ai/docs/api/api-reference/models/get-models>
- Routing enforcement point: [model_profiles.py](../../../mcp_server/src/rook/agent/model_profiles.py)
  (`_NATIVE_CLOUD_PREFIXES`, `api_base_for_model`).
- DSPy key assumption to fix: [dspy_config.py](../../../mcp_server/src/rook/learning/dspy_config.py).
- RookChat tool-calling loop (motivates tool-capability filtering in Spec B):
  [chat_runner.py](../../../mcp_server/src/rook/agent/chat/chat_runner.py).
- Chirp adapter (arbitrary model string passthrough):
  [adapter.py](../../../../Chirp/src/chirp/adapter.py).
