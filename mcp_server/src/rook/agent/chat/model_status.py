"""Model visibility helpers for the chat model status endpoint."""

from __future__ import annotations

import asyncio
import copy
import os
import time
from dataclasses import dataclass, replace
from typing import Optional

from ..config import AgentConfig
from ..model_profiles import (
    FALLBACK_MODELS,
    ModelSet,
    api_base_for_model,
    api_key_env_for_model,
    detect_lmstudio_models,
    detect_ollama_models,
    get_active_profile_name,
    get_models,
    get_profile_names,
)
from ...providers import openrouter_catalog
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


@dataclass(frozen=True)
class ModelOverrideResolution:
    """Validated chat model override with server-side routing metadata."""

    model_override: str
    api_base: str
    routing: str
    provider: str
    api_base_source: str

    def to_payload(self) -> dict:
        return {
            "model_override": self.model_override,
            "api_base": self.api_base,
            "routing": self.routing,
            "provider": self.provider,
            "api_base_source": self.api_base_source,
        }


@dataclass(frozen=True)
class ModelOverrideOption:
    """One selectable/known chat model override with eligibility metadata."""

    id: str
    display_name: str
    source: str  # "role" | "local" | "openrouter_favorite"
    supports_tools: Optional[bool]  # capability fact: True | False | None(unknown)
    eligibility: str  # "eligible" | "ineligible"
    ineligible_reason: Optional[str]  # "missing_tools"|"unknown_capability"|"missing_api_key"|None
    metadata_state: str  # "known" | "stale" | "unknown" | "not_applicable"
    pricing: Optional[dict]
    context_length: Optional[int]

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "source": self.source,
            "supports_tools": self.supports_tools,
            "eligibility": self.eligibility,
            "ineligible_reason": self.ineligible_reason,
            "metadata_state": self.metadata_state,
            "pricing": self.pricing,
            "context_length": self.context_length,
        }


def _favorite_eligibility(meta, env: dict):
    """(supports_tools, eligibility, ineligible_reason, metadata_state) for a favorite.

    Precedence (first match wins): unknown_capability -> missing_tools -> missing_api_key.
    supports_tools is the metadata fact and is never coerced by key state.
    """
    if meta.metadata_state == "unknown":
        return (None, "ineligible", "unknown_capability", "unknown")
    supports_tools = "tools" in (meta.supported_parameters or [])
    if not supports_tools:
        return (False, "ineligible", "missing_tools", meta.metadata_state)
    key_env = api_key_env_for_model(meta.litellm_id)
    if key_env and not env.get(key_env):
        return (True, "ineligible", "missing_api_key", meta.metadata_state)
    return (True, "eligible", None, meta.metadata_state)


def _ungated_option(model: str, source: str) -> ModelOverrideOption:
    return ModelOverrideOption(
        id=model,
        display_name=model,
        source=source,
        supports_tools=None,
        eligibility="eligible",
        ineligible_reason=None,
        metadata_state="not_applicable",
        pricing=None,
        context_length=None,
    )


def compute_model_override_options(
    role_status: dict,
    local_providers: dict,
    catalog_view,
    env: Optional[dict] = None,
) -> list["ModelOverrideOption"]:
    """Deduped option list across role / local / openrouter_favorite sources.

    Role and local options are ungated. OpenRouter favorites are tools+credential
    gated. On id collision, the role/local entry wins (display_name may be enriched
    from catalog metadata).
    """
    env = os.environ if env is None else env
    by_id: dict[str, ModelOverrideOption] = {}

    for role in (role_status.get("roles") or {}).values():
        model = role.get("effective_model")
        if model:
            by_id.setdefault(model, _ungated_option(model, "role"))

    for provider in (local_providers or {}).values():
        for entry in provider.get("models") or []:
            override = entry.get("model_override")
            if override:
                by_id.setdefault(override, _ungated_option(override, "local"))

    for meta in catalog_view.models:
        if meta.litellm_id in by_id:
            existing = by_id[meta.litellm_id]
            if existing.display_name == existing.id and meta.display_name:
                by_id[meta.litellm_id] = replace(existing, display_name=meta.display_name)
            continue
        supports_tools, eligibility, reason, mstate = _favorite_eligibility(meta, env)
        by_id[meta.litellm_id] = ModelOverrideOption(
            id=meta.litellm_id,
            display_name=meta.display_name or meta.litellm_id,
            source="openrouter_favorite",
            supports_tools=supports_tools,
            eligibility=eligibility,
            ineligible_reason=reason,
            metadata_state=mstate,
            pricing=meta.pricing or None,
            context_length=meta.context_length,
        )

    return sorted(by_id.values(), key=lambda o: o.id)


class ModelOverrideUnavailable(ValueError):
    """Raised when a requested chat model override is not currently allowed."""

    code = "model_override_unavailable"
    ineligible_reason: Optional[str] = None

    def __init__(self, model_override: str, allowed_model_overrides: list[str]):
        super().__init__("Model override is not currently available.")
        self.model_override = model_override
        self.allowed_model_overrides = allowed_model_overrides

    def to_payload(self) -> dict:
        payload = {
            "error": "Model override is not currently available. Refresh the model list and try again.",
            "code": self.code,
            "model_override": self.model_override,
            "allowed_model_overrides": self.allowed_model_overrides,
        }
        if self.ineligible_reason:
            payload["ineligible_reason"] = self.ineligible_reason
        return payload


class ModelOverrideIneligible(ModelOverrideUnavailable):
    """Raised when a forced override is a known model that is not eligible.

    Carries the specific ``ineligible_reason``. ``missing_tools`` keeps the
    spec-named ``model_not_tool_capable`` code; other reasons use the generic
    ``model_override_ineligible`` code.
    """

    _MESSAGES = {
        "missing_tools": "That model does not support tool calling, which RookChat requires.",
        "missing_api_key": "That model needs an API key that is not configured.",
        "unknown_capability": "That model's capabilities are unknown — refresh the OpenRouter catalog.",
    }
    _CODES = {"missing_tools": "model_not_tool_capable"}

    def __init__(
        self,
        model_override: str,
        allowed_model_overrides: list[str],
        ineligible_reason: str,
    ):
        super().__init__(model_override, allowed_model_overrides)
        self.ineligible_reason = ineligible_reason
        self.code = self._CODES.get(ineligible_reason, "model_override_ineligible")

    def to_payload(self) -> dict:
        payload = super().to_payload()
        payload["error"] = self._MESSAGES.get(self.ineligible_reason, payload["error"])
        return payload


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


def _provider_for_model(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "local"


def _conversation_routing(model: str, api_base: str) -> str:
    if api_base:
        return "local"
    if model.startswith("ollama_chat/") or model.startswith("ollama/"):
        return "local"
    return "cloud"


def _detected_lmstudio_api_base(
    model_override: str,
    local_providers: dict,
) -> Optional[str]:
    lmstudio = (local_providers or {}).get("lmstudio") or {}
    for model in lmstudio.get("models") or []:
        if model.get("model_override") == model_override:
            return lmstudio.get("api_base") or "http://127.0.0.1:1234/v1"
    return None


def _bound_routing(
    model_override: str,
    *,
    detected_lmstudio_api_base: Optional[str],
) -> ModelOverrideResolution:
    provider = _provider_for_model(model_override)
    if detected_lmstudio_api_base is not None:
        return ModelOverrideResolution(
            model_override=model_override,
            api_base=detected_lmstudio_api_base,
            routing="local",
            provider=provider,
            api_base_source="detected_lmstudio",
        )

    model_set = get_models()
    api_base = api_base_for_model(model_override, model_set.api_base) or ""
    is_ollama = model_override.startswith("ollama_chat/") or model_override.startswith(
        "ollama/"
    )
    routing = "local" if api_base or is_ollama else "cloud"
    return ModelOverrideResolution(
        model_override=model_override,
        api_base=api_base,
        routing=routing,
        provider=provider,
        api_base_source="active_profile" if api_base else "none",
    )


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
    catalog_view=None,
) -> list[str]:
    """Return sorted eligible model override ids (role + local + eligible favorites)."""
    status = role_status or build_role_status()
    view = catalog_view if catalog_view is not None else openrouter_catalog.load()
    options = compute_model_override_options(status, local_providers, view)
    return sorted(o.id for o in options if o.eligibility == "eligible")


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


async def resolve_allowed_model_override(
    model_override: str,
    *,
    force_refresh: bool = False,
) -> ModelOverrideResolution:
    """Validate a chat override and bind routing metadata for the server."""
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async(
        force_refresh=force_refresh
    )
    catalog_view = openrouter_catalog.load()
    options = compute_model_override_options(role_status, local_providers, catalog_view)
    by_id = {o.id: o for o in options}
    allowed = sorted(o.id for o in options if o.eligibility == "eligible")

    option = by_id.get(model_override)
    if option is None:
        raise ModelOverrideUnavailable(model_override, allowed)
    if option.eligibility != "eligible":
        reason = option.ineligible_reason
        if reason:
            raise ModelOverrideIneligible(model_override, allowed, reason)
        # Defensive: an ineligible option with no reason should never occur
        # (the engine always sets one), but never raise an Ineligible error
        # carrying a blank reason — fall back to the generic unavailable error.
        raise ModelOverrideUnavailable(model_override, allowed)

    return _bound_routing(
        model_override,
        detected_lmstudio_api_base=_detected_lmstudio_api_base(
            model_override,
            local_providers,
        ),
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
    """Build the full chat models payload for the model status endpoint."""
    role_status = build_role_status()
    local_providers = await get_cached_local_provider_status_async()
    catalog_view = openrouter_catalog.load()
    options = compute_model_override_options(role_status, local_providers, catalog_view)
    allowed_model_overrides = sorted(
        o.id for o in options if o.eligibility == "eligible"
    )

    return {
        **role_status,
        "personas": build_persona_status(builder),
        "local_providers": local_providers,
        "allowed_model_overrides": allowed_model_overrides,
        "allowed_model_override_options": [o.to_payload() for o in options],
        "openrouter_catalog": {
            "cache_present": catalog_view.cache_present,
            "fetched_at": catalog_view.fetched_at,
            "stale": catalog_view.stale,
            "last_refresh_error": catalog_view.last_refresh_error,
        },
    }


def build_conversation_model_status(conversation) -> dict:
    """Return model visibility for one conversation without exposing api_base."""
    pending_model = conversation.pending_model or None
    pending_routing = (
        _conversation_routing(conversation.pending_model, conversation.pending_api_base)
        if pending_model
        else None
    )
    return {
        "conversation_id": conversation.id,
        "persona": conversation.persona,
        "active_model": conversation.model,
        "active_routing": _conversation_routing(
            conversation.model,
            conversation.api_base,
        ),
        "model_source": conversation.model_source,
        "api_base_source": conversation.api_base_source,
        "pending_model": pending_model,
        "pending_routing": pending_routing,
        "pending_model_source": conversation.pending_model_source or None,
        "pending_api_base_source": conversation.pending_api_base_source or None,
        "pending_applies_to": "next_turn" if pending_model else None,
    }
