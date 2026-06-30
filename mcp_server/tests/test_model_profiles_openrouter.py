from rook.agent.model_profiles import api_base_for_model


def test_openrouter_never_gets_profile_api_base():
    # openrouter is a native-cloud provider; even inside a mixed profile that
    # carries a local api_base (e.g. lmstudio), it must route to OpenRouter.
    assert api_base_for_model(
        "openrouter/anthropic/claude-3.7-sonnet", "http://127.0.0.1:1234/v1"
    ) is None


def test_openrouter_no_profile_api_base():
    assert api_base_for_model("openrouter/openai/gpt-4o", None) is None


def test_lmstudio_local_still_gets_api_base():
    # Regression guard: the openai/ local case is unchanged by the openrouter fix.
    assert api_base_for_model(
        "openai/lmstudio-model", "http://127.0.0.1:1234/v1"
    ) == "http://127.0.0.1:1234/v1"
