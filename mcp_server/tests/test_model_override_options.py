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
