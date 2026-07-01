import pytest
import rook.learning.dspy_config as dc


class _StubLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def copy(self, **kwargs):
        next_kwargs = dict(self.kwargs)
        next_kwargs.update(kwargs)
        return _StubLM(**next_kwargs)


@pytest.fixture(autouse=True)
def stub_dspy(monkeypatch):
    monkeypatch.setattr(dc.dspy, "LM", _StubLM)
    monkeypatch.setattr(dc.dspy, "configure", lambda **kw: None)


def test_openrouter_role_uses_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lm = dc.configure_dspy(model="openrouter/anthropic/claude-3.7-sonnet")
    assert lm.kwargs["api_key"] == "sk-or-test"
    assert "api_base" not in lm.kwargs  # openrouter routes natively (Task 1)


def test_openrouter_role_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        dc.configure_dspy(model="openrouter/anthropic/claude-3.7-sonnet")


def test_anthropic_still_requires_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        dc.configure_dspy(model="anthropic/claude-opus-4-6")


def test_explicit_api_key_overrides_missing_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    lm = dc.configure_dspy(model="openrouter/x/y", api_key="explicit-key")
    assert lm.kwargs["api_key"] == "explicit-key"


def test_optimization_openrouter_keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    teacher, student = dc.configure_dspy_for_optimization(
        teacher_model="openrouter/anthropic/claude-3.7-sonnet",
        student_model="openrouter/anthropic/claude-haiku",
    )
    assert teacher.kwargs["api_key"] == "sk-or-test"
    assert student.kwargs["api_key"] == "sk-or-test"


def test_optimization_explicit_key_override(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    teacher, student = dc.configure_dspy_for_optimization(
        teacher_model="openrouter/x/y", student_model="openrouter/a/b", api_key="explicit",
    )
    assert teacher.kwargs["api_key"] == "explicit"
    assert student.kwargs["api_key"] == "explicit"


def test_multi_auth_provider_does_not_raise(monkeypatch):
    # Azure-style multi-auth provider: helper returns None -> no key demand.
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    lm = dc.configure_dspy(model="azure/gpt-4")
    assert "api_key" not in lm.kwargs


def test_optimization_anthropic_back_compat(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        dc.configure_dspy_for_optimization(
            teacher_model="anthropic/x", student_model="anthropic/y",
        )


def test_local_model_needs_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    lm = dc.configure_dspy(model="ollama_chat/qwen3:30b")
    assert "api_key" not in lm.kwargs


def test_configure_dspy_sonnet_5_omits_temperature(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    lm = dc.configure_dspy(model="anthropic/claude-sonnet-5", temperature=0.7)

    assert "temperature" not in lm.kwargs
    assert lm.kwargs["max_tokens"] == 4096


def test_optimization_sonnet_5_omits_teacher_and_student_temperature(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    teacher, student = dc.configure_dspy_for_optimization(
        teacher_model="anthropic/claude-sonnet-5",
        student_model="anthropic/claude-sonnet-5",
    )

    assert "temperature" not in teacher.kwargs
    assert "temperature" not in student.kwargs


def test_reconfigure_temperature_sonnet_5_still_omits_temperature(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    dc.configure_dspy(model="anthropic/claude-sonnet-5")

    dc.reconfigure_temperature(0.2)

    assert "temperature" not in dc.get_lm().kwargs


def test_temporary_lm_settings_sonnet_5_still_omits_temperature(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    original = dc.configure_dspy(model="anthropic/claude-sonnet-5")

    with dc.TemporaryLMSettings(temperature=1.0) as lm:
        assert "temperature" not in lm.kwargs

    assert dc.get_lm() is original
