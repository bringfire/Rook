import rook.agent.chat.runtime_health as rh


def test_active_anthropic_model_with_key_is_green(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = rh._llm_state(active_model="anthropic/claude-opus-4-6")
    assert state["configured"] is True
    assert state["provider_keys"]["OPENROUTER_API_KEY"] is False


def test_openrouter_active_model_missing_key_is_unconfigured(monkeypatch):
    # Anthropic key present but irrelevant: the ACTIVE model is openrouter.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = rh._llm_state(active_model="openrouter/anthropic/claude-3.7-sonnet")
    assert state["configured"] is False
    assert "OPENROUTER_API_KEY" in state["message"]


def test_active_local_model_is_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    state = rh._llm_state(active_model="ollama_chat/qwen3:30b")
    assert state["configured"] is True


def test_default_path_gates_on_effective_model(monkeypatch):
    # No active model -> resolve the effective default and gate on IT, not any key.
    monkeypatch.setattr(rh, "_effective_default_model", lambda: "openrouter/x/y")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")  # present but irrelevant
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    state = rh._llm_state()
    assert state["configured"] is False
    assert "OPENROUTER_API_KEY" in state["message"]


def test_provider_key_map_is_informational(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    state = rh._llm_state(active_model="anthropic/claude-opus-4-6")
    assert state["provider_keys"]["OPENROUTER_API_KEY"] is True
