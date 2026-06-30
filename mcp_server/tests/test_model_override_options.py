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


from rook.agent.chat.model_status import (
    ModelOverrideUnavailable,
    ModelOverrideIneligible,
)


def _resolver_env(monkeypatch, *favorites, key=True):
    """Patch the resolver's role/local/catalog sources for deterministic tests."""
    if key:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    else:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(model_status, "build_role_status",
                        lambda: _role_status("anthropic/claude-x"))

    async def _no_local(*a, **k):
        return {}
    monkeypatch.setattr(model_status, "get_cached_local_provider_status_async", _no_local)
    monkeypatch.setattr(model_status.openrouter_catalog, "load",
                        lambda: _catalog(*favorites))


@pytest.mark.asyncio
async def test_resolve_rejects_missing_tools_with_specific_code(monkeypatch):
    _resolver_env(monkeypatch, _meta("openrouter/x/no-tools", params=["temperature"]))
    with pytest.raises(ModelOverrideIneligible) as exc:
        await model_status.resolve_allowed_model_override("openrouter/x/no-tools")
    payload = exc.value.to_payload()
    assert payload["code"] == "model_not_tool_capable"
    assert payload["ineligible_reason"] == "missing_tools"


@pytest.mark.asyncio
async def test_resolve_rejects_unknown_capability_with_reason(monkeypatch):
    _resolver_env(monkeypatch, _meta("openrouter/x/unknown", params=[], state="unknown"))
    with pytest.raises(ModelOverrideIneligible) as exc:
        await model_status.resolve_allowed_model_override("openrouter/x/unknown")
    payload = exc.value.to_payload()
    assert payload["code"] == "model_override_ineligible"
    assert payload["ineligible_reason"] == "unknown_capability"


@pytest.mark.asyncio
async def test_resolve_rejects_missing_api_key_with_reason(monkeypatch):
    _resolver_env(
        monkeypatch,
        _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"]),
        key=False,
    )
    with pytest.raises(ModelOverrideIneligible) as exc:
        await model_status.resolve_allowed_model_override(
            "openrouter/anthropic/claude-sonnet-4.6"
        )
    payload = exc.value.to_payload()
    assert payload["code"] == "model_override_ineligible"
    assert payload["ineligible_reason"] == "missing_api_key"


@pytest.mark.asyncio
async def test_resolve_rejects_unknown_id_generic(monkeypatch):
    _resolver_env(monkeypatch)  # no favorites
    with pytest.raises(ModelOverrideUnavailable) as exc:
        await model_status.resolve_allowed_model_override("anthropic/nope")
    payload = exc.value.to_payload()
    assert payload["code"] == "model_override_unavailable"
    assert "ineligible_reason" not in payload


@pytest.mark.asyncio
async def test_resolve_binds_eligible_favorite_as_cloud(monkeypatch):
    _resolver_env(monkeypatch, _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"]))
    resolution = await model_status.resolve_allowed_model_override(
        "openrouter/anthropic/claude-sonnet-4.6"
    )
    assert resolution.routing == "cloud"
    assert resolution.api_base == ""
    assert resolution.provider == "openrouter"


@pytest.mark.asyncio
async def test_compute_allowed_async_includes_eligible_favorite(monkeypatch):
    # Regression: the async wrapper (used by some callers) must surface eligible
    # favorites via the refactored shared helper, not just the sync path.
    _resolver_env(monkeypatch, _meta("openrouter/anthropic/claude-sonnet-4.6", params=["tools"]))
    allowed = await model_status.compute_allowed_model_overrides_async()
    assert "openrouter/anthropic/claude-sonnet-4.6" in allowed
    assert "anthropic/claude-x" in allowed
