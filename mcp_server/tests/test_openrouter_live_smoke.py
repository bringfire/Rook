import os
import pytest

import rook.providers.openrouter_catalog as cat

pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_LIVE_SMOKE"),
    reason="gated: set OPENROUTER_LIVE_SMOKE=1 and OPENROUTER_API_KEY to run a real refresh",
)


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
