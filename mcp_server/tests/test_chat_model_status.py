import pytest
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.model_profiles import FALLBACK_MODELS, ModelSet
from rook.agent.chat import model_status


@pytest.fixture(autouse=True)
def reset_model_status_cache():
    model_status.reset_local_provider_status_cache()
    yield
    model_status.reset_local_provider_status_cache()


def test_roles_apply_planner_and_worker_env_overrides(monkeypatch):
    monkeypatch.delenv("ROOK_MODEL_PROFILE", raising=False)
    monkeypatch.setenv("ROOK_PLANNER_MODEL", "anthropic/env-planner")
    monkeypatch.setenv("ROOK_WORKER_MODEL", "ollama_chat/env-worker")
    monkeypatch.setattr(
        model_status,
        "get_active_profile_name",
        lambda: "cloud",
    )
    monkeypatch.setattr(
        model_status,
        "get_models",
        lambda profile_name=None: ModelSet(
            planner="anthropic/profile-planner",
            worker="anthropic/profile-worker",
            specialist="anthropic/profile-specialist",
            guardian="anthropic/profile-guardian",
            dspy="anthropic/profile-dspy",
            api_base=None,
        ),
    )

    roles = model_status.build_role_status()["roles"]

    assert roles["planner"]["profile_model"] == "anthropic/profile-planner"
    assert roles["planner"]["effective_model"] == "anthropic/env-planner"
    assert roles["planner"]["source"] == "env"
    assert roles["worker"]["profile_model"] == "anthropic/profile-worker"
    assert roles["worker"]["effective_model"] == "ollama_chat/env-worker"
    assert roles["worker"]["source"] == "env"
    assert roles["worker"]["routing"] == "local"


def test_unknown_env_profile_reports_fallback(monkeypatch):
    monkeypatch.setenv("ROOK_MODEL_PROFILE", "missing-profile")
    monkeypatch.setattr(model_status, "get_profile_names", lambda: ["cloud"])
    monkeypatch.setattr(
        model_status,
        "get_models",
        lambda profile_name=None: ModelSet(**FALLBACK_MODELS),
    )

    status = model_status.build_role_status()

    assert status["active_profile"] == "fallback"
    assert status["profile_source"] == "fallback"


def test_unknown_file_active_profile_reports_fallback(monkeypatch):
    monkeypatch.delenv("ROOK_MODEL_PROFILE", raising=False)
    monkeypatch.setattr(
        model_status,
        "get_active_profile_name",
        lambda: "missing-profile",
    )
    monkeypatch.setattr(model_status, "get_profile_names", lambda: ["cloud"])
    monkeypatch.setattr(
        model_status,
        "get_models",
        lambda profile_name=None: ModelSet(**FALLBACK_MODELS),
    )

    status = model_status.build_role_status()

    assert status["active_profile"] == "fallback"
    assert status["profile_source"] == "fallback"


def test_allowed_overrides_use_effective_models_and_detected_local(monkeypatch):
    monkeypatch.delenv("ROOK_MODEL_PROFILE", raising=False)
    monkeypatch.setenv("ROOK_WORKER_MODEL", "anthropic/env-worker")
    monkeypatch.setattr(
        model_status,
        "get_active_profile_name",
        lambda: "cloud",
    )
    monkeypatch.setattr(
        model_status,
        "get_models",
        lambda profile_name=None: ModelSet(
            planner="anthropic/profile-planner",
            worker="anthropic/profile-worker",
            specialist="anthropic/profile-specialist",
            guardian="anthropic/profile-guardian",
            dspy="anthropic/profile-dspy",
            api_base=None,
        ),
    )
    local_providers = {
        "ollama": {
            "available": True,
            "models": [
                {
                    "id": "qwen3:30b",
                    "model_override": "ollama_chat/qwen3:30b",
                    "size": None,
                }
            ],
            "recommended_model_override": "ollama_chat/qwen3:30b",
            "error": None,
        },
        "lmstudio": {
            "available": False,
            "models": [],
            "recommended_model_override": None,
            "api_base": "http://127.0.0.1:1234/v1",
            "error": "connection refused",
        },
    }

    allowed = model_status.compute_allowed_model_overrides(
        local_providers=local_providers
    )

    assert "anthropic/env-worker" in allowed
    assert "anthropic/profile-worker" not in allowed
    assert "ollama_chat/qwen3:30b" in allowed


@pytest.mark.asyncio
async def test_resolve_allowed_model_override_rejects_unavailable(monkeypatch):
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {"ollama": {"models": []}, "lmstudio": {"models": []}}

    monkeypatch.setattr(model_status, "build_role_status", lambda: role_status)

    async def fake_get_cached_local_provider_status_async(force_refresh=False):
        return local_providers

    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        fake_get_cached_local_provider_status_async,
    )

    with pytest.raises(model_status.ModelOverrideUnavailable) as exc_info:
        await model_status.resolve_allowed_model_override("openai/not-allowed")

    assert exc_info.value.to_payload() == {
        "error": "Model override is not currently available. Refresh the model list and try again.",
        "code": "model_override_unavailable",
        "model_override": "openai/not-allowed",
        "allowed_model_overrides": ["anthropic/worker"],
    }


@pytest.mark.asyncio
async def test_resolve_allowed_model_override_uses_detected_lmstudio_api_base(
    monkeypatch,
):
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {
        "ollama": {"models": []},
        "lmstudio": {
            "available": True,
            "api_base": "http://127.0.0.1:1234/v1",
            "models": [
                {
                    "id": "lmstudio-community/qwen",
                    "model_override": "openai/lmstudio-community/qwen",
                    "size": None,
                }
            ],
        },
    }

    monkeypatch.setattr(model_status, "build_role_status", lambda: role_status)

    async def fake_get_cached_local_provider_status_async(force_refresh=False):
        return local_providers

    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        fake_get_cached_local_provider_status_async,
    )

    resolution = await model_status.resolve_allowed_model_override(
        "openai/lmstudio-community/qwen"
    )

    assert resolution.to_payload() == {
        "model_override": "openai/lmstudio-community/qwen",
        "api_base": "http://127.0.0.1:1234/v1",
        "routing": "local",
        "provider": "openai",
        "api_base_source": "detected_lmstudio",
    }


@pytest.mark.asyncio
async def test_resolve_allowed_model_override_defaults_detected_lmstudio_api_base(
    monkeypatch,
):
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {
        "ollama": {"models": []},
        "lmstudio": {
            "available": True,
            "models": [
                {
                    "id": "lmstudio-community/qwen",
                    "model_override": "openai/lmstudio-community/qwen",
                    "size": None,
                }
            ],
        },
    }

    monkeypatch.setattr(model_status, "build_role_status", lambda: role_status)

    async def fake_get_cached_local_provider_status_async(force_refresh=False):
        return local_providers

    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        fake_get_cached_local_provider_status_async,
    )

    resolution = await model_status.resolve_allowed_model_override(
        "openai/lmstudio-community/qwen"
    )

    assert resolution.to_payload() == {
        "model_override": "openai/lmstudio-community/qwen",
        "api_base": "http://127.0.0.1:1234/v1",
        "routing": "local",
        "provider": "openai",
        "api_base_source": "detected_lmstudio",
    }


@pytest.mark.asyncio
async def test_resolve_allowed_model_override_uses_profile_for_profile_models(
    monkeypatch,
):
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {"ollama": {"models": []}, "lmstudio": {"models": []}}

    monkeypatch.setattr(model_status, "build_role_status", lambda: role_status)
    monkeypatch.setattr(
        model_status,
        "get_models",
        lambda profile_name=None: ModelSet(
            planner="anthropic/planner",
            worker="anthropic/worker",
            specialist="anthropic/specialist",
            guardian="anthropic/guardian",
            dspy="anthropic/dspy",
            api_base=None,
        ),
    )

    async def fake_get_cached_local_provider_status_async(force_refresh=False):
        return local_providers

    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        fake_get_cached_local_provider_status_async,
    )

    resolution = await model_status.resolve_allowed_model_override("anthropic/worker")

    assert resolution.to_payload() == {
        "model_override": "anthropic/worker",
        "api_base": "",
        "routing": "cloud",
        "provider": "anthropic",
        "api_base_source": "none",
    }


def test_normalize_ollama_maps_detection_shape():
    normalized = model_status._normalize_ollama(
        {
            "ollama_available": True,
            "models": [
                {"name": "qwen3:30b", "size": 30_000_000_000},
                {"name": "nomic-embed-text", "size": None},
                {"size": 123},
            ],
            "largest_above_4gb": "qwen3:30b",
            "error": None,
        }
    )

    assert normalized == {
        "available": True,
        "models": [
            {
                "id": "qwen3:30b",
                "model_override": "ollama_chat/qwen3:30b",
                "size": 30_000_000_000,
            },
            {
                "id": "nomic-embed-text",
                "model_override": "ollama_chat/nomic-embed-text",
                "size": None,
            },
        ],
        "recommended_model_override": "ollama_chat/qwen3:30b",
        "error": None,
    }


def test_normalize_lmstudio_maps_detection_shape():
    normalized = model_status._normalize_lmstudio(
        {
            "lmstudio_available": True,
            "models": [
                {"id": "lmstudio-community/model-a"},
                {"id": "model-b", "owned_by": "user"},
                {"object": "model"},
            ],
            "recommended": "openai/lmstudio-community/model-a",
            "api_base": "http://127.0.0.1:1234/v1",
            "error": None,
        }
    )

    assert normalized == {
        "available": True,
        "models": [
            {
                "id": "lmstudio-community/model-a",
                "model_override": "openai/lmstudio-community/model-a",
                "size": None,
            },
            {
                "id": "model-b",
                "model_override": "openai/model-b",
                "size": None,
            },
        ],
        "recommended_model_override": "openai/lmstudio-community/model-a",
        "api_base": "http://127.0.0.1:1234/v1",
        "error": None,
    }


@pytest.mark.asyncio
async def test_refresh_local_provider_status_degrades_detector_failures(monkeypatch):
    def raise_ollama(timeout=None):
        raise RuntimeError("ollama unavailable")

    def raise_lmstudio(timeout=None):
        raise RuntimeError("lmstudio unavailable")

    monkeypatch.setattr(model_status, "detect_ollama_models", raise_ollama)
    monkeypatch.setattr(model_status, "detect_lmstudio_models", raise_lmstudio)

    local_providers = await model_status.refresh_local_provider_status()

    assert local_providers["ollama"]["available"] is False
    assert local_providers["ollama"]["models"] == []
    assert "ollama unavailable" in local_providers["ollama"]["error"]
    assert local_providers["lmstudio"]["available"] is False
    assert local_providers["lmstudio"]["models"] == []
    assert "lmstudio unavailable" in local_providers["lmstudio"]["error"]


@pytest.mark.asyncio
async def test_local_provider_cache_returns_copies_and_force_refreshes(monkeypatch):
    calls = {"count": 0}

    def fake_ollama(timeout=None):
        calls["count"] += 1
        name = f"qwen3:{calls['count']}"
        return {
            "ollama_available": True,
            "models": [{"name": name, "size": calls["count"]}],
            "largest_above_4gb": name,
            "error": None,
        }

    def fake_lmstudio(timeout=None):
        return {
            "lmstudio_available": True,
            "models": [{"id": f"studio-{calls['count']}"}],
            "recommended": f"openai/studio-{calls['count']}",
            "api_base": "http://127.0.0.1:1234/v1",
            "error": None,
        }

    monkeypatch.setattr(model_status, "detect_ollama_models", fake_ollama)
    monkeypatch.setattr(model_status, "detect_lmstudio_models", fake_lmstudio)

    first = await model_status.get_cached_local_provider_status_async()
    first["ollama"]["models"][0]["id"] = "mutated"

    second = await model_status.get_cached_local_provider_status_async()
    refreshed = await model_status.get_cached_local_provider_status_async(
        force_refresh=True
    )

    assert second["ollama"]["models"][0]["id"] == "qwen3:1"
    assert refreshed["ollama"]["models"][0]["id"] == "qwen3:2"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_build_models_payload_reuses_role_status_for_allowed_overrides(
    monkeypatch,
):
    from rook.agent.chat.model_status import ModelOverrideOption
    from rook.providers.openrouter_catalog import CatalogView

    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {"ollama": {"models": []}, "lmstudio": {"models": []}}
    calls = {
        "build_role_status": 0,
        "options_role_status": None,
        "options_local_providers": None,
    }

    def fake_build_role_status():
        calls["build_role_status"] += 1
        return role_status

    stub_option = ModelOverrideOption(
        id="anthropic/worker",
        display_name="anthropic/worker",
        source="role",
        supports_tools=None,
        eligibility="eligible",
        ineligible_reason=None,
        metadata_state="not_applicable",
        pricing=None,
        context_length=None,
    )

    def fake_compute_model_override_options(role_status_arg, local_providers_arg, catalog_view_arg):
        calls["options_role_status"] = role_status_arg
        calls["options_local_providers"] = local_providers_arg
        return [stub_option]

    fake_catalog_view = CatalogView(
        models=[],
        fetched_at=None,
        last_refresh_attempt_at=None,
        last_refresh_error=None,
        cache_present=False,
        stale=False,
    )

    async def fake_get_cached_local_provider_status_async(force_refresh=False):
        return local_providers

    monkeypatch.setattr(model_status, "build_role_status", fake_build_role_status)
    monkeypatch.setattr(
        model_status,
        "get_cached_local_provider_status_async",
        fake_get_cached_local_provider_status_async,
    )
    monkeypatch.setattr(model_status, "build_persona_status", lambda builder=None: [])
    monkeypatch.setattr(
        model_status,
        "compute_model_override_options",
        fake_compute_model_override_options,
    )
    monkeypatch.setattr(model_status.openrouter_catalog, "load", lambda: fake_catalog_view)

    payload = await model_status.build_models_payload()

    assert calls["build_role_status"] == 1
    assert calls["options_role_status"] is role_status
    assert calls["options_local_providers"] is local_providers
    assert payload["allowed_model_overrides"] == ["anthropic/worker"]


def test_build_persona_status_uses_prompt_builder_resolution(monkeypatch):
    class FakeBuilder:
        def __init__(self):
            self.resolved = []

        def resolve_model_and_base(self, persona):
            self.resolved.append(persona)
            return "openai/local-model", "http://127.0.0.1:1234/v1"

    builder = FakeBuilder()
    monkeypatch.setattr(model_status, "available_personas", lambda: ["architect"])
    monkeypatch.setattr(
        model_status,
        "load_display_config",
        lambda persona: {"label": "Architect"},
    )
    monkeypatch.setattr(
        model_status,
        "get_model_role",
        lambda persona: "specialist",
    )

    personas = model_status.build_persona_status(builder)

    assert builder.resolved == ["architect"]
    assert personas == [
        {
            "persona": "architect",
            "label": "Architect",
            "model_role": "specialist",
            "resolved_model": "openai/local-model",
            "routing": "local",
        }
    ]


def test_conversation_applies_model_override_atomically():
    from rook.agent.chat.conversation_store import Conversation

    conv = Conversation(id="conv_test", persona="worker")
    conv.pending_model = "ollama_chat/old"
    conv.pending_api_base = ""
    conv.pending_model_source = "agent_tool"
    conv.pending_api_base_source = "none"
    conv.pending_model_reason = "old pending switch"
    resolution = model_status.ModelOverrideResolution(
        model_override="openai/lmstudio-community/qwen",
        api_base="http://127.0.0.1:1234/v1",
        routing="local",
        provider="openai",
        api_base_source="detected_lmstudio",
    )

    payload = conv.apply_model_override(
        resolution,
        source="start_override",
        reason="user requested local model",
    )

    assert conv.model == "openai/lmstudio-community/qwen"
    assert conv.api_base == "http://127.0.0.1:1234/v1"
    assert conv.model_source == "start_override"
    assert conv.api_base_source == "detected_lmstudio"
    assert conv.pending_model == ""
    assert conv.pending_api_base == ""
    assert conv.pending_model_source == ""
    assert conv.pending_api_base_source == ""
    assert conv.pending_model_reason == ""
    assert payload == {
        "active_model": "openai/lmstudio-community/qwen",
        "active_routing": "local",
        "model_source": "start_override",
        "api_base_source": "detected_lmstudio",
    }
    assert "api_base" not in payload


def test_conversation_stages_and_applies_pending_model():
    from rook.agent.chat.conversation_store import Conversation

    conv = Conversation(id="conv_test", persona="worker")
    conv.model = "anthropic/worker"
    conv.api_base = ""
    conv.model_source = "persona"
    conv.api_base_source = "none"
    resolution = model_status.ModelOverrideResolution(
        model_override="ollama_chat/qwen3:30b",
        api_base="",
        routing="local",
        provider="ollama_chat",
        api_base_source="none",
    )

    staged = conv.stage_model_override(
        resolution,
        source="agent_tool",
        reason="use local qwen",
    )

    assert staged == {
        "pending_model": "ollama_chat/qwen3:30b",
        "pending_routing": "local",
        "model_source": "agent_tool",
        "api_base_source": "none",
        "applies_to": "next_turn",
    }
    assert "api_base" not in staged
    assert conv.model == "anthropic/worker"
    assert conv.api_base == ""
    assert conv.model_source == "persona"
    assert conv.api_base_source == "none"
    assert conv.pending_model == "ollama_chat/qwen3:30b"
    assert conv.pending_api_base == ""
    assert conv.pending_model_source == "agent_tool"
    assert conv.pending_api_base_source == "none"
    assert conv.pending_model_reason == "use local qwen"

    applied = conv.apply_pending_model_override()

    assert applied == {
        "active_model": "ollama_chat/qwen3:30b",
        "active_routing": "local",
        "model_source": "agent_tool",
        "api_base_source": "none",
    }
    assert conv.model == "ollama_chat/qwen3:30b"
    assert conv.api_base == ""
    assert conv.model_source == "agent_tool"
    assert conv.api_base_source == "none"
    assert conv.pending_model == ""
    assert conv.pending_api_base == ""
    assert conv.pending_model_source == ""
    assert conv.pending_api_base_source == ""
    assert conv.pending_model_reason == ""
    assert conv.apply_pending_model_override() is None
