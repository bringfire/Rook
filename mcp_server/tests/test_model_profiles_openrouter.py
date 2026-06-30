from rook.agent.model_profiles import api_base_for_model, api_key_env_for_model


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


def test_key_env_openrouter():
    assert api_key_env_for_model("openrouter/anthropic/claude-3.7-sonnet") == "OPENROUTER_API_KEY"


def test_key_env_anthropic():
    assert api_key_env_for_model("anthropic/claude-opus-4-6") == "ANTHROPIC_API_KEY"


def test_key_env_openai_cloud():
    assert api_key_env_for_model("openai/gpt-4o") == "OPENAI_API_KEY"


def test_key_env_openai_local_lmstudio_is_none():
    assert api_key_env_for_model("openai/lmstudio-model", "http://127.0.0.1:1234/v1") is None


def test_key_env_ollama_is_none():
    assert api_key_env_for_model("ollama_chat/qwen3:30b") is None


def test_key_env_multiauth_providers_are_none():
    assert api_key_env_for_model("azure/gpt-4") is None
    assert api_key_env_for_model("bedrock/anthropic.claude") is None
    assert api_key_env_for_model("gemini/gemini-1.5-pro") is None
