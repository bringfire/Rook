"""DSPy configuration for Rook learning system.

This module handles the setup of DSPy with Claude as the language model backend.
It provides centralized configuration to ensure consistent behavior across all
DSPy modules in the learning system.
"""

import os
import logging
from typing import Optional

import dspy

logger = logging.getLogger(__name__)

# Global DSPy language model instance
_lm: Optional[dspy.LM] = None


DEFAULT_MODEL = "claude-sonnet-4-6"


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
            (e.g., "anthropic/claude-sonnet-4-6", "ollama_chat/qwen3-coder:30b")
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
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable required for cloud models. "
                "Set it with: export ANTHROPIC_API_KEY='your-key-here'\n"
                "For local models, set the 'active' profile to 'local' or 'lmstudio' "
                "in knowledge/model_profiles.json"
            )

    # Build LM kwargs
    lm_kwargs = dict(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        cache=cache,
    )
    if api_key:
        lm_kwargs["api_key"] = api_key
    if api_base:
        lm_kwargs["api_base"] = api_base

    _lm = dspy.LM(**lm_kwargs)

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

    # Require API key if either model is cloud
    if not teacher_is_local or not student_is_local:
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable required for cloud models")

    teacher_kwargs = dict(model=teacher_model, temperature=0.7, max_tokens=4096, cache=True)
    student_kwargs = dict(model=student_model, temperature=0.3, max_tokens=2048, cache=True)
    # API key goes to cloud models; local models ignore it
    if api_key:
        if not teacher_is_local:
            teacher_kwargs["api_key"] = api_key
        if not student_is_local:
            student_kwargs["api_key"] = api_key
    if teacher_base:
        teacher_kwargs["api_base"] = teacher_base
    if student_base:
        student_kwargs["api_base"] = student_base

    teacher_lm = dspy.LM(**teacher_kwargs)
    student_lm = dspy.LM(**student_kwargs)

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

    # Create a new LM with updated temperature
    _lm = _lm.copy(temperature=temperature)
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
        _lm = _lm.copy(**self.kwargs)
        dspy.configure(lm=_lm)
        return _lm

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _lm
        _lm = self.original_lm
        dspy.configure(lm=_lm)
        return False
