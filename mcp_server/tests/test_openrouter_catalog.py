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


FIXTURE = [
    {"id": "anthropic/claude-3.7-sonnet", "canonical_slug": "anthropic/claude-3.7-sonnet",
     "name": "Anthropic: Claude 3.7 Sonnet", "context_length": 200000,
     "pricing": {"prompt": "0.000003", "completion": "0.000015"},
     "supported_parameters": ["tools", "tool_choice"]},
    {"id": "meta-llama/llama-3-8b", "canonical_slug": "meta-llama/llama-3-8b",
     "name": "Meta Llama 3 8B", "context_length": 8192,
     "pricing": {"prompt": "0", "completion": "0"}, "supported_parameters": []},
]


def _favorites(tmp_path, ids):
    p = tmp_path / "openrouter_favorites.json"
    p.write_text(json.dumps([{"id": i} for i in ids]), encoding="utf-8")
    return p


def test_refresh_normalizes_ids_and_matches_favorite(tmp_path, monkeypatch):
    monkeypatch.setattr(cat, "_fetch_models", lambda key, client=None: FIXTURE)
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])
    cache = tmp_path / "cache.json"
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    assert res.success is True
    assert res.models_fetched == 2
    assert res.favorites_matched == 1
    assert res.unknown_favorites == []          # bare catalog id matched LiteLLM favorite
    stored = json.loads(cache.read_text())["models"]
    assert "openrouter/anthropic/claude-3.7-sonnet" in stored
    assert stored["openrouter/anthropic/claude-3.7-sonnet"]["openrouter_id"] == "anthropic/claude-3.7-sonnet"


def test_refresh_flags_unknown_favorite(tmp_path, monkeypatch):
    monkeypatch.setattr(cat, "_fetch_models", lambda key, client=None: FIXTURE)
    fav = _favorites(tmp_path, ["openrouter/does/not-exist"])
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=tmp_path / "c.json")
    assert res.unknown_favorites == ["openrouter/does/not-exist"]


def test_refresh_missing_key_writes_status_only(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])
    cache = tmp_path / "c.json"
    res = cat.refresh(api_key=None, favorites_path=fav, cache_path=cache)
    assert res.success is False
    assert res.last_refresh_error["code"] == "missing_api_key"
    data = json.loads(cache.read_text())
    assert data["models"] == {}
    assert data["fetched_at"] is None


def test_failed_refresh_preserves_prior_models(tmp_path, monkeypatch):
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])
    cache = tmp_path / "c.json"
    monkeypatch.setattr(cat, "_fetch_models", lambda key, client=None: FIXTURE)
    cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    good = json.loads(cache.read_text())["models"]

    def _boom(key, client=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(cat, "_fetch_models", _boom)
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    assert res.success is False
    after = json.loads(cache.read_text())
    assert after["models"] == good                      # data preserved
    assert after["last_refresh_error"]["code"] == "fetch_failed"
    assert after["fetched_at"] is not None              # last success retained


def test_corrupt_prior_cache_failed_refresh_status_only(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text("{ not json", encoding="utf-8")
    fav = _favorites(tmp_path, ["openrouter/anthropic/claude-3.7-sonnet"])

    def _boom(key, client=None):
        raise RuntimeError("down")

    monkeypatch.setattr(cat, "_fetch_models", _boom)
    res = cat.refresh(api_key="k", favorites_path=fav, cache_path=cache)
    assert res.success is False
    data = json.loads(cache.read_text())
    assert data["models"] == {}                         # no trusted prior data -> status-only
