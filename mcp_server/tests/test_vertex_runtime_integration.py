from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


VERTEX_MODEL = "vertex_ai/gemini-2.5-pro"
VERTEX_STUDENT_MODEL = "vertex_ai/gemini-2.5-flash"
PROJECT_ID = "company-ai-project"
REGION = "us-central1"
GENERATION = "0123456789abcdef0123456789abcdef"
AUTHORIZED_USER = {
    "type": "authorized_user",
    "client_id": "client",
    "client_secret": "application-material",
    "refresh_token": "refresh-token-sentinel",
}


def test_vertex_text_routing_does_not_enter_ai_studio_rookvision():
    repo_root = Path(__file__).resolve().parents[2]
    endpoint_files = (
        "src/Rook/Services/Vision/Image/Gemini/GeminiImageProvider.cs",
        "src/Rook/Services/Vision/Video/VeoClient.cs",
        "src/Rook/Services/Vision/PromptEnhancer.cs",
    )

    for relative_path in endpoint_files:
        source = (repo_root / relative_path).read_text(encoding="utf-8")
        assert "generativelanguage.googleapis.com" in source
        assert "vertex_ai" not in source

    secret_contract = (
        repo_root
        / "src/Rook/Services/Vision/Generation/IGenerationSecretStore.cs"
    ).read_text(encoding="utf-8")
    registration = (
        repo_root / "src/Rook/Services/Vision/VisionProviderRegistrations.cs"
    ).read_text(encoding="utf-8")

    assert 'GeminiApiKey = "gemini.api_key"' in secret_contract
    assert "GenerationSecretKeys.GeminiApiKey" in registration
    assert "vertex_ai" not in secret_contract
    assert "vertex_ai" not in registration


class _RuntimeStore:
    def __init__(self):
        from rook.providers.vertex_auth import VertexRuntimeArguments

        self.calls = 0
        self.error = None
        self.runtime = VertexRuntimeArguments(
            generation=GENERATION,
            project_id=PROJECT_ID,
            region=REGION,
            vertex_credentials=dict(AUTHORIZED_USER),
        )

    def resolve_runtime(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.runtime


class _UntouchableStore:
    def resolve_runtime(self):
        raise AssertionError("non-Vertex model accessed the Vertex store")


class _LocalHealthStore:
    def __init__(self, record):
        self.record = record
        self.read_calls = 0
        self.resolve_calls = 0

    def read(self):
        self.read_calls += 1
        return self.record

    def resolve_runtime(self):
        self.resolve_calls += 1
        raise AssertionError("passive health decrypted or refreshed credentials")


def _install_runtime_store(monkeypatch):
    from rook.providers import vertex_auth

    store = _RuntimeStore()
    monkeypatch.setattr(
        vertex_auth.VertexStore,
        "production",
        classmethod(lambda _cls: store),
    )
    return store


def _assert_vertex_arguments(kwargs, credentials=AUTHORIZED_USER):
    assert kwargs["model"].startswith("vertex_ai/gemini-")
    assert kwargs["vertex_project"] == PROJECT_ID
    assert kwargs["vertex_location"] == REGION
    assert kwargs["vertex_credentials"] == credentials


def test_vertex_arguments_are_additive_and_other_providers_are_unchanged():
    from rook.providers.vertex_auth import apply_vertex_litellm_arguments

    store = _RuntimeStore()
    base = {"model": VERTEX_MODEL, "temperature": 0.25}

    result = apply_vertex_litellm_arguments(VERTEX_MODEL, base, store=store)

    assert result == {
        "model": VERTEX_MODEL,
        "temperature": 0.25,
        "vertex_project": PROJECT_ID,
        "vertex_location": REGION,
        "vertex_credentials": AUTHORIZED_USER,
    }
    assert base == {"model": VERTEX_MODEL, "temperature": 0.25}
    assert store.calls == 1

    for model in (
        "gemini/gemini-2.5-pro",
        "anthropic/claude-sonnet-5",
        "openai/gpt-5",
        "openrouter/google/gemini-2.5-pro",
        "ollama_chat/qwen3:30b",
        "openai/lmstudio-model",
        "bare-local-model",
    ):
        original = {"model": model, "temperature": 0.25}
        assert apply_vertex_litellm_arguments(
            model,
            original,
            store=_UntouchableStore(),
        ) == original


def test_unsupported_vertex_family_fails_before_store_access():
    from rook.providers.vertex_auth import (
        VertexAuthError,
        apply_vertex_litellm_arguments,
    )

    with pytest.raises(VertexAuthError) as exc_info:
        apply_vertex_litellm_arguments(
            "vertex_ai/claude-sonnet",
            {"model": "vertex_ai/claude-sonnet"},
            store=_UntouchableStore(),
        )

    assert exc_info.value.code == "vertex_model_family_unsupported"


@pytest.mark.asyncio
async def test_base_agent_routes_fresh_vertex_arguments(monkeypatch):
    from rook.agent import base_agent
    from rook.agent.config import AgentConfig

    store = _install_runtime_store(monkeypatch)
    captured = []

    async def completion(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace()

    async def execute_tool(_name, _params):
        return {"success": True}

    monkeypatch.setattr(base_agent.litellm, "acompletion", completion)
    agent = base_agent.RookAgent(
        config=AgentConfig(model=VERTEX_MODEL),
        tool_executor=execute_tool,
        tool_schemas=[],
    )

    assert await agent._call_model([{"role": "user", "content": "hello"}]) is not None
    assert len(captured) == 1
    _assert_vertex_arguments(captured[0])
    assert store.calls == 1


@pytest.mark.asyncio
async def test_guardian_routes_fresh_vertex_arguments(monkeypatch):
    import litellm

    from rook.agent import guardian
    from rook.agent.config import GuardianConfig

    store = _install_runtime_store(monkeypatch)
    captured = []

    async def completion(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
        )

    monkeypatch.setattr(litellm, "acompletion", completion)
    monitor = guardian.Guardian(
        SimpleNamespace(),
        config=GuardianConfig(llm_analysis_model=VERTEX_MODEL),
    )

    await monitor._run_llm_analysis()

    assert len(captured) == 1
    _assert_vertex_arguments(captured[0])
    assert store.calls == 1


def test_local_worker_routes_fresh_vertex_arguments(monkeypatch):
    from rook.agent import local_worker_model_transport as transport_module

    store = _install_runtime_store(monkeypatch)
    captured = []

    def completion(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=None,
        )

    monkeypatch.setattr(transport_module.litellm, "completion", completion)
    transport = transport_module.LiteLLMWorkerTransport(model=VERTEX_MODEL)

    assert transport.send({"messages": [{"role": "user", "content": "hello"}]}) == "ok"
    assert len(captured) == 1
    _assert_vertex_arguments(captured[0])
    assert store.calls == 1


@pytest.mark.asyncio
async def test_chat_routes_fresh_vertex_arguments(monkeypatch):
    from rook.agent.chat import chat_runner
    from rook.agent.chat.conversation_store import Conversation
    from rook.agent.tool_registry import ToolRegistry

    store = _install_runtime_store(monkeypatch)
    captured = []

    async def completion(**kwargs):
        captured.append(kwargs)

        async def stream():
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="ok", tool_calls=None)
                    )
                ],
                usage=None,
            )

        return stream()

    async def runtime_facts(**_kwargs):
        return {}

    async def execute_tool(_name, _params):
        return {"success": True}

    monkeypatch.setattr(chat_runner.litellm, "acompletion", completion)
    monkeypatch.setattr(chat_runner, "collect_runtime_facts", runtime_facts)
    runner = chat_runner.ChatRunner(
        tool_executor=execute_tool,
        registry=ToolRegistry(catalog={}, agent_mode=True),
    )
    conversation = Conversation(
        id="vertex-test",
        persona="worker",
        model=VERTEX_MODEL,
    )

    events = [
        event
        async for event in runner.run_turn(
            conversation,
            "hello",
            system_prompt="system",
        )
    ]

    assert any(event.type == "text_delta" for event in events)
    assert len(captured) == 1
    _assert_vertex_arguments(captured[0])
    assert store.calls == 1


def _install_dspy_transports(monkeypatch):
    from dspy.clients import lm as dspy_lm

    sync_requests = []
    async_requests = []

    def completion(*, request, num_retries, cache):
        del num_retries, cache
        sync_requests.append(dict(request))
        return {"choices": [SimpleNamespace(finish_reason="stop")]}

    async def acompletion(*, request, num_retries, cache):
        del num_retries, cache
        async_requests.append(dict(request))
        return {"choices": [SimpleNamespace(finish_reason="stop")]}

    monkeypatch.setattr(dspy_lm, "litellm_completion", completion)
    monkeypatch.setattr(dspy_lm, "alitellm_completion", acompletion)
    return sync_requests, async_requests


def _rotate_runtime(store, credentials):
    from rook.providers.vertex_auth import VertexRuntimeArguments

    store.runtime = VertexRuntimeArguments(
        generation="fedcba9876543210fedcba9876543210",
        project_id=PROJECT_ID,
        region=REGION,
        vertex_credentials=dict(credentials),
    )


def test_default_dspy_sync_rechecks_rotation_and_disconnect(monkeypatch):
    from rook.learning import dspy_config
    from rook.providers.vertex_auth import VertexAuthError

    store = _install_runtime_store(monkeypatch)
    sync_requests, _ = _install_dspy_transports(monkeypatch)
    monkeypatch.setattr(dspy_config.dspy, "configure", lambda **_kwargs: None)
    lm = dspy_config.configure_dspy(model=VERTEX_MODEL, cache=False)

    assert store.calls == 1
    assert "vertex_credentials" not in lm.kwargs
    assert "vertex_project" not in lm.kwargs
    assert "vertex_location" not in lm.kwargs
    lm.forward(prompt="before rotation")
    _assert_vertex_arguments(sync_requests[0])

    rotated = {**AUTHORIZED_USER, "refresh_token": "rotated-refresh-token"}
    _rotate_runtime(store, rotated)
    lm.forward(prompt="after rotation")
    _assert_vertex_arguments(sync_requests[1], rotated)

    store.error = VertexAuthError(
        "vertex_signed_out",
        "Vertex AI is not configured for this Windows user.",
    )
    with pytest.raises(VertexAuthError, match="not configured") as exc_info:
        lm.forward(prompt="after disconnect")

    assert exc_info.value.code == "vertex_signed_out"
    assert len(sync_requests) == 2
    assert store.calls == 4


@pytest.mark.asyncio
async def test_default_dspy_async_rechecks_invalid_authorization(monkeypatch):
    from rook.learning import dspy_config
    from rook.providers.vertex_auth import VertexAuthError

    store = _install_runtime_store(monkeypatch)
    _, async_requests = _install_dspy_transports(monkeypatch)
    monkeypatch.setattr(dspy_config.dspy, "configure", lambda **_kwargs: None)
    lm = dspy_config.configure_dspy(model=VERTEX_MODEL, cache=False)

    await lm.aforward(prompt="authorized")
    _assert_vertex_arguments(async_requests[0])

    store.error = VertexAuthError(
        "vertex_record_invalid",
        "Stored Vertex authorization is invalid.",
    )
    with pytest.raises(VertexAuthError, match="invalid") as exc_info:
        await lm.aforward(prompt="invalid authorization")

    assert exc_info.value.code == "vertex_record_invalid"
    assert len(async_requests) == 1
    assert store.calls == 3


@pytest.mark.asyncio
async def test_optimization_dspy_rechecks_teacher_and_student(monkeypatch):
    from rook.learning import dspy_config

    store = _install_runtime_store(monkeypatch)
    sync_requests, async_requests = _install_dspy_transports(monkeypatch)
    monkeypatch.setattr(dspy_config.dspy, "configure", lambda **_kwargs: None)
    teacher_lm, student_lm = dspy_config.configure_dspy_for_optimization(
        teacher_model=VERTEX_MODEL,
        student_model=VERTEX_STUDENT_MODEL,
    )
    teacher_lm.cache = False
    student_lm.cache = False
    assert "vertex_credentials" not in teacher_lm.kwargs
    assert "vertex_credentials" not in student_lm.kwargs

    teacher_lm.forward(prompt="teacher authorization")
    _assert_vertex_arguments(sync_requests[0])

    rotated = {**AUTHORIZED_USER, "refresh_token": "student-refresh-token"}
    _rotate_runtime(store, rotated)
    await student_lm.aforward(prompt="student authorization")
    _assert_vertex_arguments(async_requests[0], rotated)

    assert store.calls == 4


@pytest.mark.asyncio
async def test_non_vertex_dspy_preserves_sync_and_async_requests(monkeypatch):
    from rook.learning import dspy_config

    monkeypatch.setattr(
        "rook.providers.vertex_auth.VertexStore.production",
        classmethod(lambda _cls: _UntouchableStore()),
    )
    sync_requests, async_requests = _install_dspy_transports(monkeypatch)
    monkeypatch.setattr(dspy_config.dspy, "configure", lambda **_kwargs: None)
    lm = dspy_config.configure_dspy(
        model="gemini/gemini-2.5-pro",
        api_key="gemini-key-sentinel",
        cache=False,
    )

    lm.forward(prompt="sync")
    await lm.aforward(prompt="async")

    for request in (*sync_requests, *async_requests):
        assert request["model"] == "gemini/gemini-2.5-pro"
        assert request["api_key"] == "gemini-key-sentinel"
        assert "vertex_project" not in request
        assert "vertex_location" not in request
        assert "vertex_credentials" not in request


def test_vertex_health_reads_only_local_record_without_decryption_or_network():
    from rook.agent.chat import runtime_health
    from rook.providers.vertex_auth import VertexMode, VertexRecord

    record = VertexRecord(
        schema_version=1,
        generation=GENERATION,
        mode=VertexMode.OAUTH,
        project_id=PROJECT_ID,
        region=REGION,
        oauth_ciphertext="opaque-dpapi-ciphertext",
        service_account_path=None,
    )
    store = _LocalHealthStore(record)

    state = runtime_health._llm_state(VERTEX_MODEL, vertex_store=store)

    assert state["configured"] is True
    assert state["provider"] == "vertex_ai"
    assert state["active_model"] == VERTEX_MODEL
    assert state.get("code") is None
    assert PROJECT_ID not in state["message"]
    assert REGION not in state["message"]
    assert GENERATION not in state["message"]
    assert store.read_calls == 1
    assert store.resolve_calls == 0


def test_vertex_health_reports_signed_out_without_provider_work():
    from rook.agent.chat import runtime_health

    store = _LocalHealthStore(None)

    state = runtime_health._llm_state(VERTEX_MODEL, vertex_store=store)

    assert state["configured"] is False
    assert state["code"] == "vertex_signed_out"
    assert store.read_calls == 1
    assert store.resolve_calls == 0


def test_vertex_health_rejects_unsupported_family_before_store_access():
    from rook.agent.chat import runtime_health

    state = runtime_health._llm_state(
        "vertex_ai/claude-sonnet",
        vertex_store=_UntouchableStore(),
    )

    assert state["configured"] is False
    assert state["code"] == "vertex_model_family_unsupported"


def test_vertex_verified_fact_does_not_claim_an_api_key():
    from rook.agent.chat import runtime_health

    lines = runtime_health._build_verified_fact_lines(
        rhino_connected=False,
        prompt_available=False,
        prompt_state={},
        gh_state=None,
        llm_state={"configured": True, "provider": "vertex_ai"},
    )

    assert "The active LLM provider is configured for chat turns." in lines
    assert all("API key" not in line for line in lines)


def test_model_options_include_admitted_vertex_and_omit_unsupported_family():
    from rook.agent.chat import model_status
    from rook.providers.openrouter_catalog import CatalogView

    role_status = {
        "roles": {
            "worker": {"effective_model": VERTEX_MODEL},
            "guardian": {"effective_model": "vertex_ai/claude-sonnet"},
        }
    }
    catalog = CatalogView(
        models=(),
        fetched_at=None,
        stale=False,
        cache_present=False,
        last_refresh_error=None,
        last_refresh_attempt_at=None,
    )

    options = model_status.compute_model_override_options(
        role_status,
        {},
        catalog,
        env={},
    )

    assert [option.id for option in options] == [VERTEX_MODEL]


@pytest.mark.asyncio
async def test_model_override_rejects_unsupported_vertex_before_provider_probes(
    monkeypatch,
):
    from rook.agent.chat import model_status
    from rook.providers.vertex_auth import VertexAuthError

    async def forbidden_probe(**_kwargs):
        raise AssertionError("unsupported Vertex model reached provider detection")

    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        forbidden_probe,
    )

    with pytest.raises(VertexAuthError) as exc_info:
        await model_status.resolve_allowed_model_override(
            "vertex_ai/claude-sonnet"
        )

    assert exc_info.value.code == "vertex_model_family_unsupported"


@pytest.mark.asyncio
async def test_chat_model_tool_reports_unsupported_vertex_family(monkeypatch):
    from rook.agent.chat import chat_runner, model_status
    from rook.agent.chat.conversation_store import Conversation
    from rook.agent.tool_registry import ToolRegistry

    async def forbidden_probe(**_kwargs):
        raise AssertionError("unsupported Vertex model reached provider detection")

    async def execute_tool(_name, _params):
        return {"success": True}

    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        forbidden_probe,
    )
    runner = chat_runner.ChatRunner(
        tool_executor=execute_tool,
        registry=ToolRegistry(catalog={}, agent_mode=True),
    )
    conversation = Conversation(
        id="vertex-model-tool",
        persona="worker",
        model="anthropic/claude-sonnet-5",
    )

    result = await runner._handle_set_chat_model(
        conversation,
        {"model_override": "vertex_ai/claude-sonnet"},
    )

    assert result == {
        "success": False,
        "data": {
            "error": (
                "This release supports only Gemini publisher models on Vertex AI "
                "(vertex_ai/gemini-*)."
            ),
            "code": "vertex_model_family_unsupported",
        },
    }
