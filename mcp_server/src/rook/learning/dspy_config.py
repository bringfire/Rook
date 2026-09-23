"""DSPy configuration for Rook learning system.

This module handles the setup of DSPy with Claude as the language model backend.
It provides centralized configuration to ensure consistent behavior across all
DSPy modules in the learning system.
"""

import os
import logging
from typing import Any, Optional
from pathlib import Path

import dspy

from rook.agent.generation_params import sanitize_generation_params_for_model
from rook.providers.vertex_auth import apply_vertex_litellm_arguments

logger = logging.getLogger(__name__)

# Global DSPy language model instance
_lm: Optional[dspy.LM] = None
_cache_configured = False


DEFAULT_MODEL = "claude-sonnet-5"

_ensure_attempted = False
_ensure_result = False


def ensure_configured() -> bool:
    """Configure DSPy from the model profiles once per process; never raises.

    The learning boundary. Until 2026-09 the MCP server configured DSPy at
    import time; that import now happens lazily (the learning stack costs tens
    of seconds cold), so every module that runs a DSPy program calls this at
    its own import, which is exactly "first learning use". Idempotent: a failed
    attempt (no key, no local profile) is remembered and logged once.
    """
    global _ensure_attempted, _ensure_result
    if _ensure_attempted:
        return _ensure_result
    _ensure_attempted = True
    # Never override an explicit configuration: one made through configure_dspy()
    # (tracked in _lm) or directly through dspy.configure(lm=...) by the host or a
    # test. Profile defaults apply only when nothing is configured yet.
    if is_configured() or getattr(dspy.settings, "lm", None) is not None:
        logger.debug("DSPy already configured; leaving the existing LM in place")
        _ensure_result = True
        return _ensure_result
    try:
        configure_dspy()
        logger.info("DSPy configured successfully")
        _ensure_result = True
    except Exception as e:  # pragma: no cover - environment dependent
        logger.warning(f"Failed to configure DSPy: {e}")
        _ensure_result = False
    return _ensure_result


_VERTEX_RUNTIME_FIELDS = frozenset(
    {"vertex_project", "vertex_location", "vertex_credentials"}
)


def _without_vertex_runtime_fields(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in kwargs.items()
        if key not in _VERTEX_RUNTIME_FIELDS
    }


class _VertexAwareLM(dspy.LM):
    """DSPy LM that resolves Rook-owned Vertex authorization per inference."""

    def __init__(self, model: str, **kwargs: Any):
        constructor_kwargs = _without_vertex_runtime_fields(kwargs)
        # Validate current authorization at configuration time without retaining it.
        apply_vertex_litellm_arguments(model, constructor_kwargs)
        super().__init__(model=model, **constructor_kwargs)

    def _fresh_call_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return apply_vertex_litellm_arguments(
            self.model,
            _without_vertex_runtime_fields(kwargs),
        )

    def forward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        return super().forward(
            prompt=prompt,
            messages=messages,
            **self._fresh_call_kwargs(kwargs),
        )

    async def aforward(
        self,
        prompt: Optional[str] = None,
        messages: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ):
        return await super().aforward(
            prompt=prompt,
            messages=messages,
            **self._fresh_call_kwargs(kwargs),
        )


def _create_dspy_lm(lm_kwargs: dict[str, Any]) -> dspy.LM:
    model = lm_kwargs.get("model")
    if isinstance(model, str) and model.startswith("vertex_ai/"):
        return _VertexAwareLM(**lm_kwargs)
    return dspy.LM(**lm_kwargs)


def _get_rook_dspy_cache_dir() -> Optional[str]:
    """Resolve Rook's DSPy cache directory for release/runtime processes."""
    configured = os.environ.get("DSPY_CACHEDIR")
    if configured:
        return configured

    data_dir = os.environ.get("ROOK_DATA_DIR")
    if data_dir:
        cache_dir = str(Path(data_dir) / "dspy-cache")
        os.environ["DSPY_CACHEDIR"] = cache_dir
        return cache_dir

    return None


def configure_secure_dspy_cache() -> dict:
    """Force DSPy disk cache reads through restricted pickle deserialization."""
    global _cache_configured
    cache_dir = _get_rook_dspy_cache_dir()
    require_restricted_pickle = (
        os.environ.get("ROOK_DSPY_RESTRICT_PICKLE") == "1"
        or os.environ.get("ROOK_MODE") == "release"
    )
    kwargs = {
        "enable_disk_cache": True,
        "enable_memory_cache": True,
        "restrict_pickle": True,
    }
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        kwargs["disk_cache_dir"] = cache_dir

    if not hasattr(dspy, "configure_cache"):
        raise RuntimeError("Installed DSPy does not support secure cache configuration")

    try:
        dspy.configure_cache(**kwargs)
    except TypeError as exc:
        if require_restricted_pickle:
            raise RuntimeError(
                "Installed DSPy does not support restrict_pickle cache configuration"
            ) from exc
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("restrict_pickle", None)
        dspy.configure_cache(**fallback_kwargs)
        kwargs["restrict_pickle"] = False

    if kwargs["restrict_pickle"]:
        os.environ["ROOK_DSPY_RESTRICT_PICKLE"] = "1"
    else:
        os.environ.pop("ROOK_DSPY_RESTRICT_PICKLE", None)
    _cache_configured = True
    logger.info(
        "DSPy cache configured with restricted pickle; disk_cache_dir=%s",
        cache_dir or "(dspy default)",
    )
    return kwargs


configure_secure_dspy_cache()


def _get_default_model() -> str:
    """Get default model from DSPY_MODEL env var, falling back to DEFAULT_MODEL."""
    return os.environ.get("DSPY_MODEL", DEFAULT_MODEL)


def _is_provider_prefixed(model: str) -> bool:
    """Check if model string already has a LiteLLM provider prefix."""
    return "/" in model


def configure_dspy(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    cache: bool = True,
) -> dspy.LM:
    """
    Configure DSPy with an LLM backend.

    Supports Anthropic cloud models, Ollama local models, LM Studio,
    and any OpenAI-compatible local provider via api_base.

    When no model is specified, resolves from model profiles
    (knowledge/model_profiles.json → "dspy" role) or falls back
    to the DSPY_MODEL env var.

    Args:
        model: LiteLLM model identifier. Provider-prefixed strings
            (e.g., "anthropic/claude-sonnet-5", "ollama_chat/qwen3-coder:30b")
            are passed through as-is. Bare model names are prefixed with "anthropic/".
        api_key: API key (uses ANTHROPIC_API_KEY env var for Anthropic models).
            Not required for local models (Ollama, LM Studio).
        api_base: Base URL for local providers (e.g., "http://127.0.0.1:1234/v1").
        temperature: Sampling temperature (0.0-1.0).
        max_tokens: Maximum tokens per response.
        cache: Whether to cache responses for identical requests.

    Returns:
        Configured dspy.LM instance

    Raises:
        ValueError: If an Anthropic model is requested but no API key is available.
    """
    global _lm

    configure_secure_dspy_cache()

    # Resolve model from profiles if not explicitly provided
    if not model:
        try:
            from ..agent.model_profiles import get_models
            model_set = get_models()
            model = model_set.dspy
            if not api_base and model_set.api_base:
                api_base = model_set.api_base
        except Exception:
            pass
    if not model:
        model = _get_default_model()

    # Apply provider prefix if needed (before is_local check so prefix is consistent)
    if not _is_provider_prefixed(model):
        model = f"anthropic/{model}"

    # Determine if this is a local or cloud model.
    # api_base_for_model() filters: cloud providers (anthropic/) and native-routed
    # providers (ollama*/) don't need api_base, only OpenAI-compatible local servers do.
    from ..agent.model_profiles import api_base_for_model
    filtered_api_base = api_base_for_model(model, api_base)
    is_local = (
        filtered_api_base is not None or
        model.startswith("ollama_chat/") or
        model.startswith("ollama/")
    )
    # Use filtered api_base from here on (None for cloud models in mixed profiles)
    api_base = filtered_api_base

    # Resolve API key — required for Anthropic, optional for local
    if not is_local:
        from ..agent.model_profiles import api_key_env_for_model
        key_env = api_key_env_for_model(model, api_base)
        if not api_key and key_env:
            api_key = os.environ.get(key_env)
            if not api_key:
                raise ValueError(
                    f"{key_env} environment variable required for model '{model}'. "
                    f"Set it (e.g. export {key_env}='your-key-here'), pass api_key=, "
                    "or select a local profile in knowledge/model_profiles.json."
                )
        # key_env is None for multi-auth/unknown providers (Azure, Bedrock, ...);
        # leave api_key unset and let LiteLLM/DSPy surface provider-specific errors.

    # Build LM kwargs
    lm_kwargs = dict(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        cache=cache,
    )
    lm_kwargs = sanitize_generation_params_for_model(model, lm_kwargs)
    if api_key:
        lm_kwargs["api_key"] = api_key
    if api_base:
        lm_kwargs["api_base"] = api_base

    _lm = _create_dspy_lm(lm_kwargs)

    # Set as the global default LM for all DSPy modules
    dspy.configure(lm=_lm)

    logger.info(
        "DSPy configured: model=%s api_base=%s local=%s",
        model, api_base or "(cloud)", is_local,
    )
    return _lm


def configure_dspy_for_optimization(
    teacher_model: Optional[str] = None,
    student_model: str = "claude-haiku-4-5-20251001",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
) -> tuple[dspy.LM, dspy.LM]:
    """
    Configure DSPy with separate teacher and student models for optimization.

    During DSPy optimization (e.g., BootstrapFewShot), a more capable "teacher"
    model generates demonstrations that a faster "student" model learns from.

    Args:
        teacher_model: Model for generating demonstrations (more capable).
            Provider-prefixed strings passed through; bare names get "anthropic/".
        student_model: Model for inference after optimization (faster/cheaper).
        api_key: API key. Not required for local models.
        api_base: Base URL for local providers.

    Returns:
        Tuple of (teacher_lm, student_lm)
    """
    configure_secure_dspy_cache()

    teacher_model = teacher_model or _get_default_model()

    # Apply provider prefix if needed
    if not _is_provider_prefixed(teacher_model):
        teacher_model = f"anthropic/{teacher_model}"
    if not _is_provider_prefixed(student_model):
        student_model = f"anthropic/{student_model}"

    # Resolve api_base from profile when caller didn't provide one
    from ..agent.model_profiles import api_base_for_model
    if not api_base:
        try:
            from ..agent.model_profiles import get_models
            _ms = get_models()
            if _ms.api_base:
                api_base = _ms.api_base
        except Exception:
            pass

    # Filter api_base per-model — cloud models don't get local api_base,
    # local models do.  This handles mixed teacher/student setups correctly.
    teacher_base = api_base_for_model(teacher_model, api_base)
    student_base = api_base_for_model(student_model, api_base)

    # Determine locality per-model for API key requirements
    def _is_local_model(model: str, filtered_base: Optional[str]) -> bool:
        return (
            filtered_base is not None or
            model.startswith("ollama_chat/") or
            model.startswith("ollama/")
        )

    teacher_is_local = _is_local_model(teacher_model, teacher_base)
    student_is_local = _is_local_model(student_model, student_base)

    # Resolve a provider-correct key per cloud model.  An explicit api_key=
    # overrides env lookup for all cloud models; multi-auth/unknown providers
    # resolve to None and let LiteLLM surface their own auth errors.
    from ..agent.model_profiles import api_key_env_for_model

    def _resolve_key(mdl: str, mdl_is_local: bool, mdl_base: Optional[str]) -> Optional[str]:
        if mdl_is_local:
            return None
        if api_key:
            return api_key
        key_env = api_key_env_for_model(mdl, mdl_base)
        if key_env:
            val = os.environ.get(key_env)
            if not val:
                raise ValueError(
                    f"{key_env} environment variable required for model '{mdl}'. "
                    "Set it or pass api_key=."
                )
            return val
        return None

    teacher_key = _resolve_key(teacher_model, teacher_is_local, teacher_base)
    student_key = _resolve_key(student_model, student_is_local, student_base)

    teacher_kwargs = sanitize_generation_params_for_model(
        teacher_model,
        dict(model=teacher_model, temperature=0.7, max_tokens=4096, cache=True),
    )
    student_kwargs = sanitize_generation_params_for_model(
        student_model,
        dict(model=student_model, temperature=0.3, max_tokens=2048, cache=True),
    )
    if teacher_key:
        teacher_kwargs["api_key"] = teacher_key
    if student_key:
        student_kwargs["api_key"] = student_key
    if teacher_base:
        teacher_kwargs["api_base"] = teacher_base
    if student_base:
        student_kwargs["api_base"] = student_base

    teacher_lm = _create_dspy_lm(teacher_kwargs)
    student_lm = _create_dspy_lm(student_kwargs)

    # Set student as default (teacher used explicitly during optimization)
    dspy.configure(lm=student_lm)

    logger.info(f"DSPy configured for optimization: teacher={teacher_model}, student={student_model}")
    return teacher_lm, student_lm


def get_lm() -> Optional[dspy.LM]:
    """Get the currently configured language model."""
    return _lm


def is_configured() -> bool:
    """Check if DSPy has been configured."""
    return _lm is not None


def _model_from_lm(lm: dspy.LM) -> Optional[str]:
    model = getattr(lm, "model", None)
    if isinstance(model, str) and model:
        return model
    kwargs = getattr(lm, "kwargs", None)
    if isinstance(kwargs, dict):
        value = kwargs.get("model")
        if isinstance(value, str) and value:
            return value
    return None


def reconfigure_temperature(temperature: float) -> None:
    """
    Update the temperature setting for the current LM.

    Useful for switching between exploration (higher temp) and
    exploitation (lower temp) modes.

    Args:
        temperature: New temperature value (0.0-1.0)
    """
    global _lm
    if _lm is None:
        raise RuntimeError("DSPy not configured. Call configure_dspy() first.")

    # Create a new LM with updated temperature when the model accepts it.
    model = _model_from_lm(_lm)
    params = {"temperature": temperature}
    if model:
        params = sanitize_generation_params_for_model(model, params)
    _lm = _lm.copy(**params)
    dspy.configure(lm=_lm)
    logger.debug(f"Temperature updated to {temperature}")


# Context manager for temporary LM settings
class TemporaryLMSettings:
    """Context manager for temporarily changing LM settings.

    Example:
        with TemporaryLMSettings(temperature=1.0):
            # High-temperature exploration
            result = planner(...)
        # Back to original settings
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.original_lm = None

    def __enter__(self):
        global _lm
        if _lm is None:
            raise RuntimeError("DSPy not configured. Call configure_dspy() first.")

        self.original_lm = _lm
        model = _model_from_lm(_lm)
        kwargs = dict(self.kwargs)
        if model:
            kwargs = sanitize_generation_params_for_model(model, kwargs)
        _lm = _lm.copy(**kwargs)
        dspy.configure(lm=_lm)
        return _lm

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _lm
        _lm = self.original_lm
        dspy.configure(lm=_lm)
        return False
