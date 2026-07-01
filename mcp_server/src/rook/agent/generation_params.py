"""Model-aware generation parameter compatibility helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_SAMPLING_PARAMS = frozenset({"temperature", "top_p", "top_k"})


def _base_model_id(model: str) -> str:
    if model.startswith("openrouter/"):
        return model[len("openrouter/") :]
    return model


def _rejects_non_default_sampling_params(model: str) -> bool:
    return _base_model_id(model) in {
        "anthropic/claude-sonnet-5",
        "claude-sonnet-5",
    }


def sanitize_generation_params_for_model(
    model: str,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    """Return generation params that are safe to send for ``model``.

    This is a narrow compatibility shim, not the long-term execution-profile
    policy layer. It only strips params known to fail on current models.
    """
    sanitized = dict(params)
    if _rejects_non_default_sampling_params(model):
        for name in _SAMPLING_PARAMS:
            sanitized.pop(name, None)
    return sanitized
