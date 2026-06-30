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
