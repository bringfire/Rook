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
    role_status = {
        "active_profile": "cloud",
        "profile_source": "file",
        "roles": {"worker": {"effective_model": "anthropic/worker"}},
    }
    local_providers = {"ollama": {"models": []}, "lmstudio": {"models": []}}
    calls = {
        "build_role_status": 0,
        "allowed_role_status": None,
        "allowed_local_providers": None,
    }

    def fake_build_role_status():
        calls["build_role_status"] += 1
        return role_status

    def fake_compute_allowed_model_overrides(
        local_providers=None,
        role_status=None,
    ):
        calls["allowed_local_providers"] = local_providers
        calls["allowed_role_status"] = role_status
        return ["anthropic/worker"]

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
        "compute_allowed_model_overrides",
        fake_compute_allowed_model_overrides,
    )

    payload = await model_status.build_models_payload()

    assert calls["build_role_status"] == 1
    assert calls["allowed_role_status"] is role_status
    assert calls["allowed_local_providers"] is local_providers
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
