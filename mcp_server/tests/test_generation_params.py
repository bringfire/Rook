from rook.agent.generation_params import sanitize_generation_params_for_model


def test_sonnet_5_direct_anthropic_omits_sampling_params():
    params = {
        "max_tokens": 2048,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "stream": True,
    }

    sanitized = sanitize_generation_params_for_model(
        "anthropic/claude-sonnet-5",
        params,
    )

    assert sanitized == {"max_tokens": 2048, "stream": True}
    assert params["temperature"] == 0.7


def test_sonnet_5_openrouter_omits_sampling_params():
    sanitized = sanitize_generation_params_for_model(
        "openrouter/anthropic/claude-sonnet-5",
        {"temperature": 0.3, "max_tokens": 128},
    )

    assert sanitized == {"max_tokens": 128}


def test_sonnet_4_6_keeps_sampling_params():
    params = {"temperature": 0.7, "top_p": 0.9, "max_tokens": 2048}

    assert sanitize_generation_params_for_model(
        "anthropic/claude-sonnet-4-6",
        params,
    ) == params
