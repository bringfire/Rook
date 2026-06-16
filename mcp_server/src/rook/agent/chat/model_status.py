"""Model visibility helpers for the chat model status endpoint."""

from __future__ import annotations

import asyncio
import copy
import os
import time
from typing import Optional

from ..config import AgentConfig
from ..model_profiles import (
    FALLBACK_MODELS,
    ModelSet,
    api_base_for_model,
    detect_lmstudio_models,
    detect_ollama_models,
    get_active_profile_name,
    get_models,
    get_profile_names,
)
from ..personas import available_personas, get_model_role, load_display_config
from .prompt_builder import PromptBuilder


LOCAL_DETECTION_TTL_SECONDS = 45.0
LOCAL_DETECTION_TIMEOUT_SECONDS = 1.5

_GUARDIAN_NOTE = (
    "Profile guardian role is defined, but spawned Guardian LLM analysis "
    "currently uses AgentConfig.guardian_llm_model."
)

_local_cache_payload: Optional[dict] = None
_local_cache_time: Optional[float] = None


def reset_local_provider_status_cache() -> None:
    """Clear cached local provider detection results."""
    global _local_cache_payload, _local_cache_time
    _local_cache_payload = None
    _local_cache_time = None


def _is_fallback_model_set(model_set: ModelSet) -> bool:
    return model_set == ModelSet(**FALLBACK_MODELS)


def _profile_exists(profile_name: str) -> bool:
    try:
        return profile_name in get_profile_names()
    except Exception:
        return False


def _get_profile_model_set() -> tuple[str, str, ModelSet]:
    """Return active profile name, source, and resolved model set."""
    env_profile = os.environ.get("ROOK_MODEL_PROFILE")
    if env_profile:
        active_profile = env_profile
        profile_source = "env"
    else:
        active_profile = get_active_profile_name()
        profile_source = "file" if active_profile else "fallback"

    model_set = get_models(active_profile)
    if (
        active_profile
        and not _profile_exists(active_profile)
        and _is_fallback_model_set(model_set)
    ):
        return "fallback", "fallback", model_set

    return active_profile or "fallback", profile_source, model_set


def _routing_info(model: str, profile_api_base: Optional[str]) -> dict:
    """Return provider, routing class, and api_base for a model."""
    api_base = api_base_for_model(model, profile_api_base)
    is_ollama = model.startswith("ollama_chat/") or model.startswith("ollama/")
    routing = "local" if api_base or is_ollama else "cloud"
    provider = model.split("/", 1)[0] if "/" in model else "local"
    return {
        "provider": provider,
        "routing": routing,
        "api_base": api_base,
    }


def _role_entry(
    *,
    profile_model: str,
    effective_model: str,
    source: str,
    profile_api_base: Optional[str],
    consumer: str,
    **extra: object,
) -> dict:
    entry = {
        "profile_model": profile_model,
        "effective_model": effective_model,
        "source": source,
        **_routing_info(effective_model, profile_api_base),
        "consumer": consumer,
    }
    entry.update(extra)
    return entry


def build_role_status() -> dict:
    """Build env-aware model status for all model roles."""
    active_profile, profile_source, model_set = _get_profile_model_set()
    profile_api_base = model_set.api_base
    guardian_config = AgentConfig()

    planner_override = os.environ.get("ROOK_PLANNER_MODEL")
    worker_override = os.environ.get("ROOK_WORKER_MODEL")

    roles = {
        "planner": _role_entry(
            profile_model=model_set.planner,
            effective_model=planner_override or model_set.planner,
            source="env" if planner_override else "profile",
            profile_api_base=profile_api_base,
            consumer="PlannerConfig.planner_model",
        ),
        "worker": _role_entry(
            profile_model=model_set.worker,
            effective_model=worker_override or model_set.worker,
            source="env" if worker_override else "profile",
            profile_api_base=profile_api_base,
            consumer="PlannerConfig.worker_model",
        ),
        "specialist": _role_entry(
            profile_model=model_set.specialist,
            effective_model=model_set.specialist,
            source="profile",
            profile_api_base=profile_api_base,
            consumer="persona model_role",
        ),
        "guardian": _role_entry(
            profile_model=model_set.guardian,
            effective_model=guardian_config.guardian_llm_model,
            source="agent_config_default",
            profile_api_base=profile_api_base,
            consumer="GuardianConfig.llm_analysis_model",
            enabled_by_default=guardian_config.guardian_llm_analysis,
            note=_GUARDIAN_NOTE,
        ),
        "dspy": _role_entry(
            profile_model=model_set.dspy,
            effective_model=model_set.dspy,
            source="configured_at_startup",
            profile_api_base=profile_api_base,
            consumer="DSPy global LM",
            live_switchable=False,
        ),
    }

    return {
        "active_profile": active_profile,
        "profile_source": profile_source,
        "roles": roles,
    }


def _normalize_ollama(raw: dict) -> dict:
    """Normalize detect_ollama_models() output for chat status payloads."""
    models = []
    for model in raw.get("models") or []:
        if not isinstance(model, dict):
            continue
        name = model.get("name")
        if not name:
            continue
        models.append(
            {
                "id": name,
                "model_override": f"ollama_chat/{name}",
                "size": model.get("size"),
            }
        )

    recommended = raw.get("largest_above_4gb")
    return {
        "available": bool(raw.get("ollama_available")),
        "models": models,
        "recommended_model_override": (
            f"ollama_chat/{recommended}" if recommended else None
        ),
        "error": raw.get("error"),
    }


def _normalize_lmstudio(raw: dict) -> dict:
    """Normalize detect_lmstudio_models() output for chat status payloads."""
    models = []
    for model in raw.get("models") or []:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if not model_id:
            continue
        models.append(
            {
                "id": model_id,
                "model_override": f"openai/{model_id}",
                "size": None,
            }
        )

    return {
        "available": bool(raw.get("lmstudio_available")),
        "models": models,
        "recommended_model_override": raw.get("recommended"),
        "api_base": raw.get("api_base", "http://127.0.0.1:1234/v1"),
        "error": raw.get("error"),
    }


def _unavailable_ollama(error: object) -> dict:
    return _normalize_ollama(
        {
            "ollama_available": False,
            "models": [],
            "largest_above_4gb": None,
            "error": str(error),
        }
    )


def _unavailable_lmstudio(error: object) -> dict:
    return _normalize_lmstudio(
        {
            "lmstudio_available": False,
            "models": [],
            "recommended": None,
            "api_base": "http://127.0.0.1:1234/v1",
            "error": str(error),
        }
    )


async def _probe_provider(detector, normalizer, unavailable) -> dict:
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(
                detector,
                timeout=LOCAL_DETECTION_TIMEOUT_SECONDS,
            ),
            timeout=LOCAL_DETECTION_TIMEOUT_SECONDS + 0.25,
        )
        return normalizer(raw)
    except Exception as exc:
        return unavailable(exc)


async def refresh_local_provider_status() -> dict:
    """Probe local providers concurrently and update the module cache."""
    global _local_cache_payload, _local_cache_time

    ollama, lmstudio = await asyncio.gather(
        _probe_provider(detect_ollama_models, _normalize_ollama, _unavailable_ollama),
        _probe_provider(
            detect_lmstudio_models,
            _normalize_lmstudio,
            _unavailable_lmstudio,
        ),
    )
    payload = {
        "ollama": ollama,
        "lmstudio": lmstudio,
    }
    _local_cache_payload = copy.deepcopy(payload)
    _local_cache_time = time.monotonic()
    return copy.deepcopy(payload)


def _cache_is_fresh() -> bool:
    if _local_cache_payload is None or _local_cache_time is None:
        return False
    return (time.monotonic() - _local_cache_time) < LOCAL_DETECTION_TTL_SECONDS


async def get_cached_local_provider_status_async(
    force_refresh: bool = False,
) -> dict:
    """Return cached local provider status, refreshing asynchronously if needed."""
    if not force_refresh and _cache_is_fresh():
        return copy.deepcopy(_local_cache_payload)
    return await refresh_local_provider_status()


def get_cached_local_provider_status_snapshot() -> Optional[dict]:
    """Return the current cache snapshot without probing providers."""
    if _local_cache_payload is None:
        return None
    return copy.deepcopy(_local_cache_payload)


def compute_allowed_model_overrides(
    local_providers: dict,
    role_status: Optional[dict] = None,
) -> list[str]:
    """Return sorted allowed model overrides for chat conversations."""
    status = role_status or build_role_status()

    allowed = {
        role.get("effective_model")
        for role in (status.get("roles") or {}).values()
        if role.get("effective_model")
    }

    for provider in (local_providers or {}).values():
        for model in provider.get("models") or []:
            override = model.get("model_override")
            if override:
                allowed.add(override)

    return sorted(allowed)


async def compute_allowed_model_overrides_async(
    force_refresh: bool = False,
) -> list[str]:
    """Return allowed overrides using async local-provider cache refresh."""
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async(
        force_refresh=force_refresh
    )
    return compute_allowed_model_overrides(
        local_providers=local_providers,
        role_status=role_status,
    )


def build_persona_status(builder: Optional[PromptBuilder] = None) -> list[dict]:
    """Build persona model resolution rows using PromptBuilder."""
    prompt_builder = builder or PromptBuilder()
    personas = []

    for persona in available_personas():
        display = load_display_config(persona)
        resolved_model, api_base = prompt_builder.resolve_model_and_base(persona)
        personas.append(
            {
                "persona": persona,
                "label": display.get("label", persona),
                "model_role": get_model_role(persona),
                "resolved_model": resolved_model,
                "routing": _routing_info(resolved_model, api_base)["routing"],
            }
        )

    return personas


async def build_models_payload(builder: Optional[PromptBuilder] = None) -> dict:
    """Build the full chat models payload for the future endpoint."""
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async()
    allowed_model_overrides = compute_allowed_model_overrides(
        local_providers=local_providers,
        role_status=role_status,
    )

    return {
        **role_status,
        "personas": build_persona_status(builder),
        "local_providers": local_providers,
        "allowed_model_overrides": allowed_model_overrides,
    }
