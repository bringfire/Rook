# RookChat OpenRouter-aware Model Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface curated OpenRouter favorites — with metadata and tool-capability gating — in the existing RookChat model dropdown, so a user can select and apply an `openrouter/` model for a conversation.

**Architecture:** A single Python eligibility computation (`compute_model_override_options`) feeds both the `/agent/chat/models` payload and the Apply resolver, so UI and server never drift. The payload gains a structured `allowed_model_override_options` sibling field while the legacy `allowed_model_overrides: list[str]` is preserved as the authoritative applyable set. The C# tab gains an enriched DTO, filters it to eligible options for the dropdown, and falls back to the legacy string list when the structured field is absent.

**Tech Stack:** Python 3 (pytest), C# / .NET Framework 4.8 (xUnit, Eto.Forms). Reuses Spec A's `providers/openrouter_catalog.py` (`load()`, pure-disk) and `agent/model_profiles.api_key_env_for_model`.

## Global Constraints

- **No new MCP tool.** Do NOT touch `targeting.py`, `mcp_tool_profiles.py`, `test_server_tool_profiles.py`, or `test_mcp_tool_profiles.py`. The FULL/LEAN/READONLY surface counts are unchanged.
- **No network on the chat path.** Use `openrouter_catalog.load()` (pure-disk) only; never call `refresh()` / httpx from the chat/payload/resolver paths.
- **Preserve `allowed_model_overrides`** as `list[str]`; its membership may only *grow* (eligible favorites). Role/local membership must not regress.
- **Capability + credential gating applies ONLY to `source == "openrouter_favorite"`.** Role and local options are ungated (always `eligibility == "eligible"`, `supports_tools == None`).
- **Eligibility precedence for favorites (first match wins):** `unknown_capability` → `missing_tools` → `missing_api_key`. `supports_tools` is always the metadata fact, never coerced by key state.
- **Invariant:** `set(o.id for o in options if o.eligibility == "eligible") == set(allowed_model_overrides)`.
- Do NOT claim native (C++) build verification — no native code changes here.
- Python tests run from repo root: `python -m pytest <path> -v`. C# tests: `dotnet test src/Rook.Tests/Rook.Tests.csproj` (note: a managed build/test deploys `Rook.rhp` into `%AppData%` as a side effect — expected).
- Spec: `docs/superpowers/specs/2026-06-30-openrouter-rookchat-picker-design.md`.

---

### Task 1: Eligibility engine — `ModelOverrideOption` + `compute_model_override_options`

The pure, testable core. Computes one deduped option per model ID across role / local / openrouter_favorite sources, applying favorite-only tools+credential gating with the precedence above.

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/model_status.py`
- Test: `mcp_server/tests/test_model_override_options.py` (create)

**Interfaces:**
- Consumes: `providers/openrouter_catalog.CatalogView` / `ModelMetadata` (`litellm_id`, `supported_parameters`, `pricing`, `context_length`, `display_name`, `metadata_state`); `model_profiles.api_key_env_for_model(model) -> Optional[str]`.
- Produces:
  - `ModelOverrideOption` (frozen dataclass): `id: str`, `display_name: str`, `source: str` (`"role"|"local"|"openrouter_favorite"`), `supports_tools: Optional[bool]`, `eligibility: str` (`"eligible"|"ineligible"`), `ineligible_reason: Optional[str]`, `metadata_state: str`, `pricing: Optional[dict]`, `context_length: Optional[int]`; method `to_payload() -> dict`.
  - `compute_model_override_options(role_status: dict, local_providers: dict, catalog_view, env: Optional[dict] = None) -> list[ModelOverrideOption]` (sorted by `id`).

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_model_override_options.py`:

```python
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.chat.model_status import (
    ModelOverrideOption,
    compute_model_override_options,
)
from rook.providers.openrouter_catalog import CatalogView, ModelMetadata


def _role_status(*effective_models):
    return {
        "roles": {
            f"r{i}": {"effective_model": m}
            for i, m in enumerate(effective_models)
        }
    }


def _catalog(*models):
    return CatalogView(
        models=list(models),
        fetched_at="2026-06-30T00:00:00+00:00",
        last_refresh_attempt_at=None,
        last_refresh_error=None,
        cache_present=True,
        stale=False,
    )


def _meta(litellm_id, *, params, state="known", name=None, ctx=None, pricing=None):
    return ModelMetadata(
        litellm_id=litellm_id,
        openrouter_id=litellm_id.replace("openrouter/", ""),
        canonical_slug=None,
        supported_parameters=list(params),
        pricing=pricing or {},
        context_length=ctx,
        display_name=name,
        metadata_state=state,
    )


def test_role_and_local_are_ungated_eligible():
    role = _role_status("anthropic/claude-x")
    local = {"ollama": {"models": [{"model_override": "ollama_chat/qwen3:30b"}]}}
    opts = compute_model_override_options(role, local, _catalog(), env={})
    by_id = {o.id: o for o in opts}
    assert by_id["anthropic/claude-x"].source == "role"
    assert by_id["anthropic/claude-x"].eligibility == "eligible"
    assert by_id["anthropic/claude-x"].supports_tools is None
    assert by_id["anthropic/claude-x"].metadata_state == "not_applicable"
    assert by_id["ollama_chat/qwen3:30b"].source == "local"
    assert by_id["ollama_chat/qwen3:30b"].eligibility == "eligible"


def test_favorite_eligible_with_tools_and_key():
    fav = _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"], name="Claude Sonnet 4.6", ctx=200000)
    opts = compute_model_override_options(_role_status(), {}, _catalog(fav),
                                          env={"OPENROUTER_API_KEY": "sk-x"})
    o = opts[0]
    assert o.source == "openrouter_favorite"
    assert o.supports_tools is True
    assert o.eligibility == "eligible"
    assert o.ineligible_reason is None
    assert o.display_name == "Claude Sonnet 4.6"
    assert o.context_length == 200000


def test_favorite_missing_tools_is_ineligible():
    fav = _meta("openrouter/x/no-tools", params=["temperature"])
    opts = compute_model_override_options(_role_status(), {}, _catalog(fav),
                                          env={"OPENROUTER_API_KEY": "sk-x"})
    assert opts[0].supports_tools is False
    assert opts[0].eligibility == "ineligible"
    assert opts[0].ineligible_reason == "missing_tools"


def test_favorite_unknown_capability_is_ineligible():
    fav = _meta("openrouter/x/unknown", params=[], state="unknown")
    opts = compute_model_override_options(_role_status(), {}, _catalog(fav),
                                          env={"OPENROUTER_API_KEY": "sk-x"})
    assert opts[0].supports_tools is None
    assert opts[0].eligibility == "ineligible"
    assert opts[0].ineligible_reason == "unknown_capability"


def test_favorite_tool_capable_but_missing_key():
    fav = _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"])
    opts = compute_model_override_options(_role_status(), {}, _catalog(fav), env={})
    assert opts[0].supports_tools is True          # capability fact, not coerced
    assert opts[0].eligibility == "ineligible"
    assert opts[0].ineligible_reason == "missing_api_key"


def test_favorite_stale_with_tools_stays_eligible_flagged():
    fav = _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"], state="stale")
    opts = compute_model_override_options(_role_status(), {}, _catalog(fav),
                                          env={"OPENROUTER_API_KEY": "sk-x"})
    assert opts[0].eligibility == "eligible"
    assert opts[0].metadata_state == "stale"


def test_favorite_stale_without_tools_is_missing_tools():
    fav = _meta("openrouter/x/stale-no-tools", params=["temperature"], state="stale")
    opts = compute_model_override_options(_role_status(), {}, _catalog(fav),
                                          env={"OPENROUTER_API_KEY": "sk-x"})
    assert opts[0].eligibility == "ineligible"
    assert opts[0].ineligible_reason == "missing_tools"


def test_dedup_role_precedence_over_favorite():
    # Same id from role and favorite (favorite has no key) -> role wins, eligible,
    # display_name enriched from catalog.
    rid = "openrouter/anthropic/claude-sonnet-4.6"
    fav = _meta(rid, params=["tools"], name="Claude Sonnet 4.6")
    opts = compute_model_override_options(_role_status(rid), {}, _catalog(fav), env={})
    matching = [o for o in opts if o.id == rid]
    assert len(matching) == 1
    assert matching[0].source == "role"
    assert matching[0].eligibility == "eligible"          # ungated despite missing key
    assert matching[0].display_name == "Claude Sonnet 4.6"


def test_to_payload_shape():
    fav = _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"], ctx=200000)
    opts = compute_model_override_options(_role_status(), {}, _catalog(fav),
                                          env={"OPENROUTER_API_KEY": "sk-x"})
    p = opts[0].to_payload()
    assert set(p) == {
        "id", "display_name", "source", "supports_tools", "eligibility",
        "ineligible_reason", "metadata_state", "pricing", "context_length",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest mcp_server/tests/test_model_override_options.py -v`
Expected: FAIL with `ImportError: cannot import name 'ModelOverrideOption'`.

- [ ] **Step 3: Write minimal implementation**

In `mcp_server/src/rook/agent/chat/model_status.py`, update the dataclasses import and the `model_profiles` import:

```python
from dataclasses import dataclass, replace
```

Add `api_key_env_for_model` to the existing `from ..model_profiles import (...)` block, and add a new import near the top-level imports:

```python
from ...providers import openrouter_catalog
```

Then add, after the existing `ModelOverrideResolution` dataclass:

```python
@dataclass(frozen=True)
class ModelOverrideOption:
    """One selectable/known chat model override with eligibility metadata."""

    id: str
    display_name: str
    source: str  # "role" | "local" | "openrouter_favorite"
    supports_tools: Optional[bool]  # capability fact: True | False | None(unknown)
    eligibility: str  # "eligible" | "ineligible"
    ineligible_reason: Optional[str]  # "missing_tools"|"unknown_capability"|"missing_api_key"|None
    metadata_state: str  # "known" | "stale" | "unknown" | "not_applicable"
    pricing: Optional[dict]
    context_length: Optional[int]

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "source": self.source,
            "supports_tools": self.supports_tools,
            "eligibility": self.eligibility,
            "ineligible_reason": self.ineligible_reason,
            "metadata_state": self.metadata_state,
            "pricing": self.pricing,
            "context_length": self.context_length,
        }


def _favorite_eligibility(meta, env: dict):
    """(supports_tools, eligibility, ineligible_reason, metadata_state) for a favorite.

    Precedence (first match wins): unknown_capability -> missing_tools -> missing_api_key.
    supports_tools is the metadata fact and is never coerced by key state.
    """
    if meta.metadata_state == "unknown":
        return (None, "ineligible", "unknown_capability", "unknown")
    supports_tools = "tools" in (meta.supported_parameters or [])
    if not supports_tools:
        return (False, "ineligible", "missing_tools", meta.metadata_state)
    key_env = api_key_env_for_model(meta.litellm_id)
    if key_env and not env.get(key_env):
        return (True, "ineligible", "missing_api_key", meta.metadata_state)
    return (True, "eligible", None, meta.metadata_state)


def _ungated_option(model: str, source: str) -> ModelOverrideOption:
    return ModelOverrideOption(
        id=model,
        display_name=model,
        source=source,
        supports_tools=None,
        eligibility="eligible",
        ineligible_reason=None,
        metadata_state="not_applicable",
        pricing=None,
        context_length=None,
    )


def compute_model_override_options(
    role_status: dict,
    local_providers: dict,
    catalog_view,
    env: Optional[dict] = None,
) -> list["ModelOverrideOption"]:
    """Deduped option list across role / local / openrouter_favorite sources.

    Role and local options are ungated. OpenRouter favorites are tools+credential
    gated. On id collision, the role/local entry wins (display_name may be enriched
    from catalog metadata).
    """
    env = os.environ if env is None else env
    by_id: dict[str, ModelOverrideOption] = {}

    for role in (role_status.get("roles") or {}).values():
        model = role.get("effective_model")
        if model:
            by_id.setdefault(model, _ungated_option(model, "role"))

    for provider in (local_providers or {}).values():
        for entry in provider.get("models") or []:
            override = entry.get("model_override")
            if override:
                by_id.setdefault(override, _ungated_option(override, "local"))

    for meta in catalog_view.models:
        if meta.litellm_id in by_id:
            existing = by_id[meta.litellm_id]
            if existing.display_name == existing.id and meta.display_name:
                by_id[meta.litellm_id] = replace(existing, display_name=meta.display_name)
            continue
        supports_tools, eligibility, reason, mstate = _favorite_eligibility(meta, env)
        by_id[meta.litellm_id] = ModelOverrideOption(
            id=meta.litellm_id,
            display_name=meta.display_name or meta.litellm_id,
            source="openrouter_favorite",
            supports_tools=supports_tools,
            eligibility=eligibility,
            ineligible_reason=reason,
            metadata_state=mstate,
            pricing=meta.pricing or None,
            context_length=meta.context_length,
        )

    return sorted(by_id.values(), key=lambda o: o.id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest mcp_server/tests/test_model_override_options.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/chat/model_status.py mcp_server/tests/test_model_override_options.py
git commit -m "feat(chat): model override eligibility engine (favorites tools+key gating)"
```

---

### Task 2: Wire the engine into the payload + `compute_allowed_model_overrides`

`build_models_payload` emits the new `allowed_model_override_options` + `openrouter_catalog` block and derives `allowed_model_overrides` from eligible options. `compute_allowed_model_overrides` is refactored to share the engine, preserving its `list[str]` return and growing membership with eligible favorites.

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/model_status.py` (`compute_allowed_model_overrides`, `build_models_payload`)
- Test: `mcp_server/tests/test_model_override_options.py` (add payload tests)

**Interfaces:**
- Consumes: `compute_model_override_options` (Task 1), `openrouter_catalog.load()`.
- Produces: `build_models_payload(...)` payload now contains `allowed_model_override_options: list[dict]` and `openrouter_catalog: dict`; `compute_allowed_model_overrides(local_providers, role_status=None, catalog_view=None) -> list[str]` (eligible ids).

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_model_override_options.py`:

```python
import pytest
from rook.agent.chat import model_status


def test_allowed_overrides_equals_eligible_ids_invariant(monkeypatch):
    # No key in the process env -> the tool-capable favorite is missing_api_key
    # (ineligible). Delete BEFORE calling compute_allowed_model_overrides, which
    # reads os.environ, so the result is deterministic.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    role = _role_status("anthropic/claude-x")
    tool_fav = _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"])
    bad_fav = _meta("openrouter/x/no-tools", params=["temperature"])
    view = _catalog(tool_fav, bad_fav)

    allowed = model_status.compute_allowed_model_overrides(
        local_providers={}, role_status=role, catalog_view=view,
    )
    options = compute_model_override_options(role, {}, view, env={})
    eligible_ids = {o.id for o in options if o.eligibility == "eligible"}

    assert set(allowed) == eligible_ids
    assert "anthropic/claude-x" in allowed          # role preserved
    assert "openrouter/x/no-tools" not in allowed    # ineligible favorite excluded
    # every favorite excluded from allowed carries a reason in the structured list
    for o in options:
        if o.source == "openrouter_favorite" and o.id not in allowed:
            assert o.ineligible_reason is not None


@pytest.mark.asyncio
async def test_build_models_payload_has_options_and_catalog_block(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    monkeypatch.setattr(model_status, "build_role_status",
                        lambda: _role_status("anthropic/claude-x"))

    async def _no_local(*a, **k):
        return {}
    monkeypatch.setattr(model_status, "get_cached_local_provider_status_async", _no_local)

    fav = _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"], name="Sonnet 4.6")
    monkeypatch.setattr(model_status.openrouter_catalog, "load", lambda: _catalog(fav))
    monkeypatch.setattr(model_status, "build_persona_status", lambda builder=None: [])

    payload = await model_status.build_models_payload()

    assert "allowed_model_override_options" in payload
    ids = {o["id"] for o in payload["allowed_model_override_options"]}
    assert "anthropic/claude-x" in ids
    assert "openrouter/anthropic/claude-sonnet-4.6" in ids
    assert "openrouter/anthropic/claude-sonnet-4.6" in payload["allowed_model_overrides"]
    assert payload["openrouter_catalog"]["cache_present"] is True
    assert payload["openrouter_catalog"]["stale"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest mcp_server/tests/test_model_override_options.py -k "invariant or payload" -v`
Expected: FAIL — `compute_allowed_model_overrides` has no `catalog_view` kwarg; payload lacks the new keys.

- [ ] **Step 3: Write minimal implementation**

In `model_status.py`, replace the body of `compute_allowed_model_overrides`:

```python
def compute_allowed_model_overrides(
    local_providers: dict,
    role_status: Optional[dict] = None,
    catalog_view=None,
) -> list[str]:
    """Return sorted eligible model override ids (role + local + eligible favorites)."""
    status = role_status or build_role_status()
    view = catalog_view if catalog_view is not None else openrouter_catalog.load()
    options = compute_model_override_options(status, local_providers, view)
    return sorted(o.id for o in options if o.eligibility == "eligible")
```

Replace the body of `build_models_payload`:

```python
async def build_models_payload(builder: Optional[PromptBuilder] = None) -> dict:
    """Build the full chat models payload for the model status endpoint."""
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async()
    catalog_view = openrouter_catalog.load()
    options = compute_model_override_options(role_status, local_providers, catalog_view)
    allowed_model_overrides = sorted(
        o.id for o in options if o.eligibility == "eligible"
    )

    return {
        **role_status,
        "personas": build_persona_status(builder),
        "local_providers": local_providers,
        "allowed_model_overrides": allowed_model_overrides,
        "allowed_model_override_options": [o.to_payload() for o in options],
        "openrouter_catalog": {
            "cache_present": catalog_view.cache_present,
            "fetched_at": catalog_view.fetched_at,
            "stale": catalog_view.stale,
            "last_refresh_error": catalog_view.last_refresh_error,
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest mcp_server/tests/test_model_override_options.py mcp_server/tests/test_chat_model_status.py mcp_server/tests/test_chat_server.py -v`
Expected: PASS. If `test_chat_server.py` asserts the exact `/agent/chat/models` key set (dict equality), update that assertion to include `allowed_model_override_options` and `openrouter_catalog`; if it uses subset/`in` checks, no change is needed.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/chat/model_status.py mcp_server/tests/test_model_override_options.py mcp_server/tests/test_chat_server.py
git commit -m "feat(chat): surface allowed_model_override_options + openrouter_catalog in models payload"
```

---

### Task 3: Specific Apply rejection for ineligible favorites (shared path)

`resolve_allowed_model_override` reuses the engine and raises a specific `model_not_tool_capable` error (subclass of `ModelOverrideUnavailable`, so the existing server `except` + 400 mapping handles it unchanged) when a forced override is a known `missing_tools` favorite.

**Files:**
- Modify: `mcp_server/src/rook/agent/chat/model_status.py` (`ModelOverrideUnavailable`, new `ModelOverrideNotToolCapable`, `resolve_allowed_model_override`)
- Test: `mcp_server/tests/test_model_override_options.py` (add resolver tests)

**Interfaces:**
- Consumes: `compute_model_override_options`, `openrouter_catalog.load()`, `_bound_routing` (existing).
- Produces: `ModelOverrideNotToolCapable(ModelOverrideUnavailable)` with `code == "model_not_tool_capable"`; `resolve_allowed_model_override` raises it for forced `missing_tools` favorites, generic `ModelOverrideUnavailable` otherwise; returns `ModelOverrideResolution` for eligible ids (unchanged shape).

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_model_override_options.py`:

```python
from rook.agent.chat.model_status import (
    ModelOverrideUnavailable,
    ModelOverrideNotToolCapable,
)


@pytest.mark.asyncio
async def test_resolve_rejects_missing_tools_favorite_with_specific_code(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    monkeypatch.setattr(model_status, "build_role_status", lambda: _role_status())

    async def _no_local(*a, **k):
        return {}
    monkeypatch.setattr(model_status, "get_cached_local_provider_status_async", _no_local)
    bad = _meta("openrouter/x/no-tools", params=["temperature"])
    monkeypatch.setattr(model_status.openrouter_catalog, "load", lambda: _catalog(bad))

    with pytest.raises(ModelOverrideNotToolCapable) as exc:
        await model_status.resolve_allowed_model_override("openrouter/x/no-tools")
    assert exc.value.to_payload()["code"] == "model_not_tool_capable"


@pytest.mark.asyncio
async def test_resolve_rejects_unknown_id_generic(monkeypatch):
    monkeypatch.setattr(model_status, "build_role_status", lambda: _role_status("anthropic/claude-x"))

    async def _no_local(*a, **k):
        return {}
    monkeypatch.setattr(model_status, "get_cached_local_provider_status_async", _no_local)
    monkeypatch.setattr(model_status.openrouter_catalog, "load", lambda: _catalog())

    with pytest.raises(ModelOverrideUnavailable) as exc:
        await model_status.resolve_allowed_model_override("anthropic/nope")
    assert exc.value.to_payload()["code"] == "model_override_unavailable"


@pytest.mark.asyncio
async def test_resolve_binds_eligible_favorite_as_cloud(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    monkeypatch.setattr(model_status, "build_role_status", lambda: _role_status())

    async def _no_local(*a, **k):
        return {}
    monkeypatch.setattr(model_status, "get_cached_local_provider_status_async", _no_local)
    fav = _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"])
    monkeypatch.setattr(model_status.openrouter_catalog, "load", lambda: _catalog(fav))

    resolution = await model_status.resolve_allowed_model_override(
        "openrouter/anthropic/claude-sonnet-4.6"
    )
    assert resolution.routing == "cloud"
    assert resolution.api_base == ""
    assert resolution.provider == "openrouter"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest mcp_server/tests/test_model_override_options.py -k resolve -v`
Expected: FAIL — `ModelOverrideNotToolCapable` undefined.

- [ ] **Step 3: Write minimal implementation**

In `model_status.py`, give `ModelOverrideUnavailable` a class-level `code` and use it in `to_payload`, then add the subclass. Replace the existing `ModelOverrideUnavailable` class with:

```python
class ModelOverrideUnavailable(ValueError):
    """Raised when a requested chat model override is not currently allowed."""

    code = "model_override_unavailable"

    def __init__(self, model_override: str, allowed_model_overrides: list[str]):
        super().__init__("Model override is not currently available.")
        self.model_override = model_override
        self.allowed_model_overrides = allowed_model_overrides

    def to_payload(self) -> dict:
        return {
            "error": "Model override is not currently available. Refresh the model list and try again.",
            "code": self.code,
            "model_override": self.model_override,
            "allowed_model_overrides": self.allowed_model_overrides,
        }


class ModelOverrideNotToolCapable(ModelOverrideUnavailable):
    """Raised when a forced override is a known model that lacks tool calling."""

    code = "model_not_tool_capable"

    def to_payload(self) -> dict:
        payload = super().to_payload()
        payload["error"] = (
            "That model does not support tool calling, which RookChat requires."
        )
        return payload
```

Replace the body of `resolve_allowed_model_override`:

```python
async def resolve_allowed_model_override(
    model_override: str,
    *,
    force_refresh: bool = False,
) -> ModelOverrideResolution:
    """Validate a chat override and bind routing metadata for the server."""
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async(
        force_refresh=force_refresh
    )
    catalog_view = openrouter_catalog.load()
    options = compute_model_override_options(role_status, local_providers, catalog_view)
    by_id = {o.id: o for o in options}
    allowed = sorted(o.id for o in options if o.eligibility == "eligible")

    option = by_id.get(model_override)
    if option is None or option.eligibility != "eligible":
        if option is not None and option.ineligible_reason == "missing_tools":
            raise ModelOverrideNotToolCapable(model_override, allowed)
        raise ModelOverrideUnavailable(model_override, allowed)

    return _bound_routing(
        model_override,
        detected_lmstudio_api_base=_detected_lmstudio_api_base(
            model_override,
            local_providers,
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest mcp_server/tests/test_model_override_options.py mcp_server/tests/test_chat_runner_model_tools.py -v`
Expected: PASS (resolver tests + the existing chat-runner model-tool tests, which mock `resolve_allowed_model_override`).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/chat/model_status.py mcp_server/tests/test_model_override_options.py
git commit -m "feat(chat): specific model_not_tool_capable rejection via shared eligibility path"
```

---

### Task 4: Python regression sweep

Confirm the broader chat/model suite is green before crossing to C#.

**Files:** none (verification only).

- [ ] **Step 1: Run the chat/model suite**

Run: `python -m pytest mcp_server/tests/test_chat_model_status.py mcp_server/tests/test_chat_server.py mcp_server/tests/test_chat_runner_model_tools.py mcp_server/tests/test_model_override_options.py -v`
Expected: PASS. If any pre-existing test asserts an exact `/agent/chat/models` payload shape, update it to include the two new keys (additive only); do not weaken behavioral assertions.

- [ ] **Step 2: Commit (only if a test file was updated)**

```bash
git add mcp_server/tests/
git commit -m "test(chat): update payload-shape assertions for enriched models endpoint"
```

---

### Task 5: C# DTO — `ModelOverrideOption` + `ChatModelsInfo.AllowedModelOverrideOptions`

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatClient.cs`
- Test: `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs` (add a case)

**Interfaces:**
- Produces: `Rook.UI.Chat.ModelOverrideOption` (Id, DisplayName, Source, SupportsTools `bool?`, Eligibility, IneligibleReason, MetadataState, Pricing `JsonElement?`, ContextLength `int?`); `ChatModelsInfo.AllowedModelOverrideOptions: List<ModelOverrideOption>`.

- [ ] **Step 1: Write the failing test**

Add to `src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs`:

```csharp
[Fact]
public void Model_not_tool_capable_400_code_parses()
{
    var body = "{\"code\":\"model_not_tool_capable\",\"error\":\"no tools\",\"allowed_model_overrides\":[\"a\"]}";
    var r = AgentChatClient.ParseSetModelResult(400, false, body);
    Assert.False(r.Success);
    Assert.Equal("model_not_tool_capable", r.ErrorCode);
    Assert.NotNull(r.AllowedModelOverrides);
}
```

- [ ] **Step 2: Run test to verify it passes (parse is already generic) — then add the DTO**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Model_not_tool_capable"`
Expected: PASS — `ParseSetModelResult` already extracts `code`. (This locks the contract; no parse change needed.)

- [ ] **Step 3: Add the DTO**

In `src/Rook/UI/Chat/AgentChatClient.cs`, add a class above `ChatModelsInfo`:

```csharp
public class ModelOverrideOption
{
    public string Id { get; set; } = "";

    [JsonPropertyName("display_name")]
    public string DisplayName { get; set; } = "";

    public string Source { get; set; } = "";

    [JsonPropertyName("supports_tools")]
    public bool? SupportsTools { get; set; }

    public string Eligibility { get; set; } = "";

    [JsonPropertyName("ineligible_reason")]
    public string? IneligibleReason { get; set; }

    [JsonPropertyName("metadata_state")]
    public string? MetadataState { get; set; }

    public JsonElement? Pricing { get; set; }

    [JsonPropertyName("context_length")]
    public int? ContextLength { get; set; }
}
```

And add to `ChatModelsInfo` (keep the existing `AllowedModelOverrides`):

```csharp
        [JsonPropertyName("allowed_model_override_options")]
        public List<ModelOverrideOption> AllowedModelOverrideOptions { get; set; } = new();
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AgentChatClientParseTests"`
Expected: PASS (all parse tests, including the new one).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/UI/Chat/AgentChatClient.cs src/Rook.Tests/UI/Chat/AgentChatClientParseTests.cs
git commit -m "feat(chat-ui): ModelOverrideOption DTO + allowed_model_override_options binding"
```

---

### Task 6: C# pure helpers — `EligibleOptions` + label / selection-detail builders

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs` (add internal static helpers)
- Test: `src/Rook.Tests/UI/Chat/ModelOverrideOptionHelpersTests.cs` (create)

**Interfaces:**
- Produces: `AgentChatTab.EligibleOptions(IEnumerable<ModelOverrideOption>) -> List<ModelOverrideOption>`; `AgentChatTab.BuildOptionLabel(ModelOverrideOption) -> string`; `AgentChatTab.BuildSelectionDetail(ModelOverrideOption) -> string`.

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/UI/Chat/ModelOverrideOptionHelpersTests.cs`:

```csharp
using System.Collections.Generic;
using System.Linq;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class ModelOverrideOptionHelpersTests
    {
        private static ModelOverrideOption Opt(string id, string elig, string? name = null,
            string? state = null, int? ctx = null)
            => new ModelOverrideOption
            {
                Id = id, DisplayName = name ?? "", Eligibility = elig,
                MetadataState = state, ContextLength = ctx,
            };

        [Fact]
        public void EligibleOptions_keeps_only_eligible()
        {
            var opts = new List<ModelOverrideOption>
            {
                Opt("a", "eligible"),
                Opt("b", "ineligible"),
                Opt("c", "eligible"),
            };
            var eligible = AgentChatTab.EligibleOptions(opts);
            Assert.Equal(new[] { "a", "c" }, eligible.Select(o => o.Id).ToArray());
        }

        [Fact]
        public void BuildOptionLabel_uses_display_name_then_falls_back_to_id()
        {
            Assert.Equal("Claude Sonnet 4.6",
                AgentChatTab.BuildOptionLabel(Opt("openrouter/anthropic/claude-sonnet-4.6", "eligible", "Claude Sonnet 4.6")));
            Assert.Equal("anthropic/x",
                AgentChatTab.BuildOptionLabel(Opt("anthropic/x", "eligible")));
        }

        [Fact]
        public void BuildSelectionDetail_includes_ctx_and_stale_note()
        {
            var detail = AgentChatTab.BuildSelectionDetail(
                Opt("x", "eligible", "X", state: "stale", ctx: 200000));
            Assert.Contains("200000", detail);
            Assert.Contains("stale", detail);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ModelOverrideOptionHelpersTests"`
Expected: FAIL — helpers don't exist.

- [ ] **Step 3: Write minimal implementation**

In `src/Rook/UI/Chat/AgentChatTab.cs`, add (near the existing `ShouldEnableApply` static; ensure `using System.Linq;` and `using System.Collections.Generic;` are present — they are):

```csharp
        internal static List<ModelOverrideOption> EligibleOptions(
            IEnumerable<ModelOverrideOption> options)
        {
            return options
                .Where(o => string.Equals(o.Eligibility, "eligible", StringComparison.Ordinal))
                .ToList();
        }

        internal static string BuildOptionLabel(ModelOverrideOption option)
        {
            return string.IsNullOrEmpty(option.DisplayName) ? option.Id : option.DisplayName;
        }

        internal static string BuildSelectionDetail(ModelOverrideOption option)
        {
            var parts = new List<string>();
            if (option.ContextLength.HasValue)
                parts.Add($"{option.ContextLength.Value} ctx");
            if (string.Equals(option.MetadataState, "stale", StringComparison.Ordinal))
                parts.Add("metadata stale — refresh");
            return string.Join(" · ", parts);
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ModelOverrideOptionHelpersTests"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/UI/Chat/AgentChatTab.cs src/Rook.Tests/UI/Chat/ModelOverrideOptionHelpersTests.cs
git commit -m "feat(chat-ui): pure EligibleOptions + label/selection-detail helpers"
```

---

### Task 7: Wire the dropdown to the structured options (applyable-only + fallback)

Consume `AllowedModelOverrideOptions` when present (friendly labels, eligible-only, active-model never injected when ineligible); fall back to the legacy string list otherwise. UI integration — covered behaviorally by Task 6's pure helpers; verified by build + full C# test run.

**Files:**
- Modify: `src/Rook/UI/Chat/AgentChatTab.cs` (`RefreshModelStatusAsync`, new `PopulateModelSelector` overload)

**Interfaces:**
- Consumes: `EligibleOptions`, `BuildOptionLabel`, `BuildSelectionDetail` (Task 6); `ChatModelsInfo.AllowedModelOverrideOptions` (Task 5).

- [ ] **Step 1: Add the options-aware overload**

In `src/Rook/UI/Chat/AgentChatTab.cs`, add a new overload beside the existing `PopulateModelSelector(List<string>, string)`:

```csharp
        private void PopulateModelSelector(List<ModelOverrideOption> options, string activeModel)
        {
            if (_modelDropDown == null)
                return;

            var previousSelectedKey = _modelDropDown.SelectedKey;
            var eligible = EligibleOptions(options);
            var activeIsEligible = eligible.Any(
                o => string.Equals(o.Id, activeModel, StringComparison.Ordinal));

            _modelListAvailable = eligible.Count > 0;

            var preservePending =
                _modelSelectionDirty
                && !string.IsNullOrEmpty(previousSelectedKey)
                && eligible.Any(o => string.Equals(o.Id, previousSelectedKey, StringComparison.Ordinal))
                && !string.Equals(previousSelectedKey, activeModel, StringComparison.Ordinal);

            // Dropdown stays applyable-only: the active model is added/selected only when
            // it is itself eligible. An ineligible/unknown active model lives in the status
            // label (set by the caller), never as a selectable row.
            string? selectedKey = preservePending
                ? previousSelectedKey
                : (activeIsEligible ? activeModel : null);
            if (!preservePending)
                _modelSelectionDirty = false;

            _suppressModelSelectionEvents = true;
            try
            {
                _modelDropDown.Items.Clear();
                foreach (var o in eligible)
                    _modelDropDown.Items.Add(new ListItem { Text = BuildOptionLabel(o), Key = o.Id });
                _modelDropDown.SelectedKey = selectedKey;
            }
            finally
            {
                _suppressModelSelectionEvents = false;
            }

            UpdateApplyEnabled();
        }
```

- [ ] **Step 2: Call the overload from `RefreshModelStatusAsync`**

In `RefreshModelStatusAsync`, after `var allowed = models.AllowedModelOverrides ?? new List<string>();` add:

```csharp
                var options = models.AllowedModelOverrideOptions ?? new List<ModelOverrideOption>();
```

Then replace the success-path `PopulateModelSelector(allowed, activeModel!);` call (inside the `Application.Instance.Invoke(...)` block) with:

```csharp
                    if (options.Count > 0)
                        PopulateModelSelector(options, activeModel!);
                    else
                        PopulateModelSelector(allowed, activeModel!);
```

Leave the catch-block fallback `PopulateModelSelector(new List<string>(), active!);` unchanged (legacy path on endpoint failure).

- [ ] **Step 3: Build and run the full C# test suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS (all existing + new tests; `ShouldEnableApply` and parse suites unaffected).

- [ ] **Step 4: Commit**

```bash
git add src/Rook/UI/Chat/AgentChatTab.cs
git commit -m "feat(chat-ui): populate model dropdown from structured options (applyable-only + fallback)"
```

---

### Task 8: Live Tier-2 validation (manual; closes deferred Spec A item #3)

Not TDD — a live deploy + RookChat turn on an `openrouter/` model. Run before opening the PR. Follows `docs/openrouter-live-smoke.md`.

**Files:** none.

- [ ] **Step 1: Deploy the Python payload to the runtime**

Run: `pwsh scripts/deploy-local-testing.ps1 -PayloadOnly -AllowRunning`
(Python-only; the runtime runs from `LocalAppData/Rook`, not the repo. Kills nothing.)

- [ ] **Step 2: Ensure the key is present in the deployed runtime env**

Confirm `OPENROUTER_API_KEY` is set in `LocalAppData/Rook/app/mcp_server/.env` (deploy seeds `.env` only when missing — add the key manually if absent; read it from the main repo's gitignored `mcp_server/.env`, never paste it into chat).

- [ ] **Step 3: Populate the catalog cache and reconnect**

In Claude Code, run `/mcp` to reconnect, then call the `openrouter_refresh_catalog` MCP tool. Expected: `success`, favorites matched ≥ 1 for `openrouter/anthropic/claude-sonnet-4.6`.

- [ ] **Step 4: Verify the picker + turn in the RookChat panel**

In the RookChat panel: confirm `openrouter/anthropic/claude-sonnet-4.6` appears in the Model dropdown with a friendly label (e.g. "Claude Sonnet 4.6"); select it → Apply → send a short message → confirm the turn completes and routes via `openrouter/` (chat-server log / DSPy or LiteLLM trace shows the `openrouter/...` model). Record the evidence in the PR description.

- [ ] **Step 5: No commit** — validation only; capture results for the PR.

---

## Notes for the implementer

- The eligibility logic lives in exactly one place (`compute_model_override_options`); the payload builder and the Apply resolver both derive from it. Do not re-implement gating in the resolver or in C#.
- C# filtering is convenience; the server is authoritative — an ineligible favorite forced via `POST /agent/chat/model` is rejected server-side (Task 3).
- Eto `DropDown` cannot disable individual rows — there are intentionally no per-row tooltips. Selection-detail text is surfaced via the status label / `BuildSelectionDetail`, not item tooltips.
- Do not modify `targeting.py`, `mcp_tool_profiles.py`, or the surface-count tests — no MCP tool is added.
