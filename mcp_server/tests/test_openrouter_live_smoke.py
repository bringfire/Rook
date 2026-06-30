import os
import pytest

import rook.providers.openrouter_catalog as cat

# Gate for the free catalog smoke (only hits /api/v1/models — no spend).
_CATALOG_GATE = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_LIVE_SMOKE"),
    reason="free catalog smoke: set OPENROUTER_LIVE_SMOKE=1 + OPENROUTER_API_KEY",
)

# Gate for PAID routing smoke (makes real LLM calls — small spend).
_LLM_GATE = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_LIVE_LLM_SMOKE"),
    reason="PAID routing smoke: set OPENROUTER_LIVE_LLM_SMOKE=1 + OPENROUTER_API_KEY (+ optional OPENROUTER_SMOKE_MODEL)",
)

# Override the model via env var; default is cheap but real.
_SMOKE_MODEL = os.environ.get("OPENROUTER_SMOKE_MODEL", "openrouter/openai/gpt-4o-mini")


@_CATALOG_GATE
def test_live_refresh_populates_cache(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text('[{"id": "openrouter/anthropic/claude-3.7-sonnet"}]', encoding="utf-8")
    cache = tmp_path / "cache.json"
    result = cat.refresh(favorites_path=fav, cache_path=cache)
    assert result.success is True, result.last_refresh_error
    assert result.models_fetched > 0
    view = cat.load(favorites_path=fav, cache_path=cache)
    # The curated model should resolve to known metadata after a real refresh.
    assert view.models[0].metadata_state == "known"
    assert "tools" in view.models[0].supported_parameters


@_LLM_GATE
def test_live_openrouter_routes_via_litellm():
    # Proves openrouter/ routes + authenticates through LiteLLM with OPENROUTER_API_KEY
    # (the prefix fix attaches no bogus api_base). Tiny call.
    import litellm
    resp = litellm.completion(
        model=_SMOKE_MODEL,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=5,
    )
    content = resp.choices[0].message.content
    assert content and content.strip(), "empty completion routed via OpenRouter"


@_LLM_GATE
def test_live_openrouter_routes_via_dspy():
    # Proves configure_dspy resolves OPENROUTER_API_KEY (no false ANTHROPIC demand)
    # and a real call routes via OpenRouter. Direct configured-LM call (avoids DSPy
    # structured-output parsing so max_tokens=5 is safe).
    import rook.learning.dspy_config as dc
    lm = dc.configure_dspy(model=_SMOKE_MODEL, max_tokens=5)
    out = lm("Reply with the single word: ok")
    assert out and str(out[0]).strip(), "empty DSPy response routed via OpenRouter"
