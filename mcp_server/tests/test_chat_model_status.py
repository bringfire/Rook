import pytest
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rook.agent.model_profiles import ModelSet
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
