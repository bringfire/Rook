import json
import rook.providers.openrouter_catalog as cat


def test_to_helpers_roundtrip():
    assert cat.to_openrouter_id("openrouter/anthropic/claude-x") == "anthropic/claude-x"
    assert cat.to_litellm_id("anthropic/claude-x") == "openrouter/anthropic/claude-x"
    # idempotent: already-prefixed ids are unchanged
    assert cat.to_litellm_id("openrouter/anthropic/claude-x") == "openrouter/anthropic/claude-x"
    assert cat.to_openrouter_id("anthropic/claude-x") == "anthropic/claude-x"


def test_load_favorites_dict_and_string(tmp_path):
    p = tmp_path / "openrouter_favorites.json"
    p.write_text(json.dumps([
        {"id": "openrouter/anthropic/claude-3.7-sonnet", "notes": "n", "tags": ["planner"]},
        "openrouter/openai/gpt-4o",
    ]), encoding="utf-8")
    favs = cat.load_favorites(p)
    assert [f.id for f in favs] == [
        "openrouter/anthropic/claude-3.7-sonnet", "openrouter/openai/gpt-4o"]
    assert favs[0].tags == ("planner",)


def test_load_favorites_missing_file_is_empty(tmp_path):
    assert cat.load_favorites(tmp_path / "nope.json") == []


from datetime import datetime, timezone, timedelta


def _write_cache(path, models, fetched_at="2026-06-29T00:00:00+00:00"):
    path.write_text(json.dumps({
        "schema_version": cat.CACHE_SCHEMA_VERSION,
        "source_endpoint": cat.OPENROUTER_MODELS_ENDPOINT,
        "fetched_at": fetched_at,
        "last_refresh_attempt_at": fetched_at,
        "last_refresh_error": None,
        "models": models,
    }), encoding="utf-8")


def test_load_present_returns_known_metadata(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    cache = tmp_path / "cache.json"
    _write_cache(cache, {"openrouter/anthropic/claude-3.7-sonnet": {
        "openrouter_id": "anthropic/claude-3.7-sonnet",
        "canonical_slug": "anthropic/claude-3.7-sonnet",
        "supported_parameters": ["tools"], "pricing": {"prompt": "1"},
        "context_length": 200000, "display_name": "Claude 3.7 Sonnet"}})
    view = cat.load(favorites_path=fav, cache_path=cache)
    assert view.cache_present is True
    m = view.models[0]
    assert m.metadata_state == "known"
    assert "tools" in m.supported_parameters
    assert m.context_length == 200000


def test_load_missing_cache_marks_unknown(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    view = cat.load(favorites_path=fav, cache_path=tmp_path / "absent.json")
    assert view.cache_present is False
    assert view.models[0].metadata_state == "unknown"


def test_load_corrupt_cache_marks_unknown(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    cache = tmp_path / "cache.json"
    cache.write_text("{ not json", encoding="utf-8")
    view = cat.load(favorites_path=fav, cache_path=cache)
    assert view.cache_present is False
    assert view.models[0].metadata_state == "unknown"


def test_load_stale_returns_metadata_with_stale_state(tmp_path):
    fav = tmp_path / "openrouter_favorites.json"
    fav.write_text(json.dumps([{"id": "openrouter/anthropic/claude-3.7-sonnet"}]), encoding="utf-8")
    cache = tmp_path / "cache.json"
    old = "2020-01-01T00:00:00+00:00"
    _write_cache(cache, {"openrouter/anthropic/claude-3.7-sonnet": {
        "openrouter_id": "anthropic/claude-3.7-sonnet", "canonical_slug": None,
        "supported_parameters": ["tools"], "pricing": {}, "context_length": 1,
        "display_name": "x"}}, fetched_at=old)
    view = cat.load(favorites_path=fav, cache_path=cache,
                    now=datetime(2021, 1, 1, tzinfo=timezone.utc))
    assert view.stale is True
    assert view.models[0].metadata_state == "stale"
    assert "tools" in view.models[0].supported_parameters  # metadata still returned
