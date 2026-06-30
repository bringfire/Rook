"""
Model Profiles
==============

Central model configuration for all Rook subsystems.

A single JSON file (knowledge/model_profiles.json) controls which LLM
is used for each role.  Change ``"active": "hybrid"`` to switch the
entire system between cloud / local / hybrid / finetuned setups.

Override hierarchy (highest wins):
    1. Explicit ROOK_*_MODEL env vars
    2. ``"active"`` field in model_profiles.json
    3. Hardcoded FALLBACK_MODELS (backward-compatible)

Ported from Engram's ``core/model_profiles.py``, adapted for
Rook's 5-role ModelSet (planner, worker, specialist, guardian, dspy).
"""

import copy
import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..runtime_paths import resolve_readable_knowledge_path, resolve_writable_knowledge_path

logger = logging.getLogger(__name__)

# ── Module-level cache (mtime-based) ─────────────────────────────────────
_cached_profiles: Optional[Dict] = None
_cached_mtime: float = 0.0

# ── Hardcoded fallbacks (match current PlannerConfig defaults exactly) ────
FALLBACK_MODELS: Dict[str, str] = {
    "planner": "anthropic/claude-opus-4-6",
    "worker": "anthropic/claude-sonnet-4-6",
    "specialist": "anthropic/claude-sonnet-4-6",
    "guardian": "anthropic/claude-sonnet-4-6",
    "dspy": "anthropic/claude-sonnet-4-6",
}


@dataclass(frozen=True)
class ModelSet:
    """Immutable set of model identifiers for all Rook roles."""
    planner: str
    worker: str
    specialist: str
    guardian: str
    dspy: str
    api_base: Optional[str] = None  # For local providers (LM Studio, vLLM)


# Provider prefixes with native LiteLLM cloud routing (never need api_base).
# The "openai/" prefix is intentionally absent — it's ambiguous (real OpenAI
# vs local OpenAI-compatible servers like LM Studio) and handled separately.
_NATIVE_CLOUD_PREFIXES = frozenset({
    "anthropic/",
    "azure/",
    "azure_ai/",
    "bedrock/",
    "cerebras/",
    "cloudflare/",
    "cohere/",
    "cohere_chat/",
    "databricks/",
    "deepseek/",
    "fireworks_ai/",
    "friendliai/",
    "gemini/",
    "groq/",
    "huggingface/",
    "mistral/",
    "openrouter/",
    "perplexity/",
    "replicate/",
    "sagemaker/",
    "together_ai/",
    "vertex_ai/",
    "voyage/",
    "xai/",
    "ai21/",
})

# Known OpenAI cloud model family prefixes.  Models starting with these
# (after the "openai/" provider prefix) are hosted on api.openai.com and
# don't need api_base.  Anything else under openai/ (e.g.,
# "openai/lmstudio-model") is assumed to be a local OpenAI-compatible server.
_OPENAI_CLOUD_MODEL_PREFIXES = (
    "gpt-", "o1", "o3", "o4", "chatgpt-", "dall-e",
    "whisper-", "tts-", "text-", "babbage-", "davinci-", "ft:gpt-",
)


def api_base_for_model(model: str, profile_api_base: Optional[str]) -> Optional[str]:
    """Return api_base only when the model actually needs it.

    Cloud providers have their own endpoints — sending them to a local
    api_base would misroute them.  Ollama has native LiteLLM routing.
    Only OpenAI-compatible local servers (LM Studio, vLLM) need the
    api_base redirect.

    This function is the single enforcement point for mixed profiles like
    'lmstudio' where cloud planner + local workers share one profile-level
    api_base.

    Args:
        model: LiteLLM model identifier (e.g., "anthropic/claude-opus-4-6",
               "ollama_chat/qwen3:30b", "openai/lmstudio-model").
        profile_api_base: The api_base from the active model profile.

    Returns:
        profile_api_base if the model needs it, None otherwise.
    """
    if not profile_api_base:
        return None

    # Ollama — LiteLLM handles routing natively (localhost:11434)
    if model.startswith("ollama_chat/") or model.startswith("ollama/"):
        return None

    # Check provider prefix against known cloud providers
    slash_idx = model.find("/")
    if slash_idx > 0:
        prefix = model[:slash_idx + 1]

        # Known cloud providers — LiteLLM routes to their native APIs
        if prefix in _NATIVE_CLOUD_PREFIXES:
            return None

        # openai/ is ambiguous: real OpenAI cloud models vs local
        # OpenAI-compatible servers (LM Studio, vLLM).  Disambiguate
        # by checking the model name against known OpenAI families.
        if prefix == "openai/":
            model_name = model[slash_idx + 1:]
            if any(model_name.startswith(p) for p in _OPENAI_CLOUD_MODEL_PREFIXES):
                return None

    # Everything else (local openai/* models, bare strings) — needs api_base
    return profile_api_base


# ── Default profiles data ────────────────────────────────────────────────
_OLLAMA_PLACEHOLDER = "ollama_chat/qwen3-coder:30b-a3b-q8_0"
_LMSTUDIO_PLACEHOLDER = "openai/lmstudio-model"
_FINETUNED_PLACEHOLDER = "ollama_chat/rook-worker"

DEFAULT_PROFILES_DATA: Dict[str, Any] = {
    "_comment": "Rook model profiles. Change 'active' to switch all models.",
    "active": "cloud",
    "profiles": {
        "cloud": {
            "description": "Full Anthropic API (highest quality, costs money)",
            "planner": FALLBACK_MODELS["planner"],
            "worker": FALLBACK_MODELS["worker"],
            "specialist": FALLBACK_MODELS["specialist"],
            "guardian": FALLBACK_MODELS["guardian"],
            "dspy": FALLBACK_MODELS["dspy"],
        },
        "hybrid": {
            "description": "Cloud planner + local workers (best balance)",
            "planner": FALLBACK_MODELS["planner"],
            "worker": _OLLAMA_PLACEHOLDER,
            "specialist": FALLBACK_MODELS["specialist"],
            "guardian": _OLLAMA_PLACEHOLDER,
            "dspy": _OLLAMA_PLACEHOLDER,
        },
        "local": {
            "description": "All local models (zero API cost)",
            "planner": _OLLAMA_PLACEHOLDER,
            "worker": _OLLAMA_PLACEHOLDER,
            "specialist": _OLLAMA_PLACEHOLDER,
            "guardian": _OLLAMA_PLACEHOLDER,
            "dspy": _OLLAMA_PLACEHOLDER,
        },
        "lmstudio": {
            "description": "Cloud planner + LM Studio local workers",
            "planner": FALLBACK_MODELS["planner"],
            "worker": _LMSTUDIO_PLACEHOLDER,
            "specialist": FALLBACK_MODELS["specialist"],
            "guardian": _LMSTUDIO_PLACEHOLDER,
            "dspy": _LMSTUDIO_PLACEHOLDER,
            "api_base": "http://127.0.0.1:1234/v1",
        },
        "finetuned": {
            "description": "Cloud planner + fine-tuned local workers",
            "planner": FALLBACK_MODELS["planner"],
            "worker": _FINETUNED_PLACEHOLDER,
            "specialist": FALLBACK_MODELS["specialist"],
            "guardian": _FINETUNED_PLACEHOLDER,
            "dspy": _FINETUNED_PLACEHOLDER,
        },
    },
}


# ═════════════════════════════════════════════════════════════════════════
# Ollama detection
# ═════════════════════════════════════════════════════════════════════════

def detect_ollama_models(
    host: str = "127.0.0.1",
    port: int = 11434,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    """Query Ollama REST API for available local models.

    Returns dict with keys:
        ollama_available: bool
        models: list of {"name": str, "size": int, ...}
        largest_above_4gb: str or None
        error: str or None
    """
    url = f"http://{host}:{port}/api/tags"
    result: Dict[str, Any] = {
        "ollama_available": False,
        "models": [],
        "largest_above_4gb": None,
        "error": None,
    }
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("models", [])
        result["ollama_available"] = True
        result["models"] = models

        # Find largest model above 4 GB
        threshold = 4 * 1024 * 1024 * 1024  # 4 GB
        candidates = [
            m for m in models
            if m.get("size", 0) > threshold
        ]
        if candidates:
            largest = max(candidates, key=lambda m: m.get("size", 0))
            result["largest_above_4gb"] = largest.get("name")

        logger.debug(f"Ollama: {len(models)} models available")
    except Exception as e:
        result["error"] = str(e)
        logger.debug(f"Ollama not reachable: {e}")
    return result


# ═════════════════════════════════════════════════════════════════════════
# LM Studio detection
# ═════════════════════════════════════════════════════════════════════════

def detect_lmstudio_models(
    host: str = "127.0.0.1",
    port: int = 1234,
    timeout: float = 3.0,
) -> Dict[str, Any]:
    """Query LM Studio's OpenAI-compatible API for loaded models.

    LM Studio serves on localhost:1234 with /v1/models endpoint.
    Models are returned as litellm-compatible "openai/<model-id>" strings
    with api_base override.

    Returns dict with keys:
        lmstudio_available: bool
        models: list of {"id": str, ...}
        recommended: str or None (litellm model string)
        api_base: str
        error: str or None
    """
    api_base = f"http://{host}:{port}/v1"
    url = f"{api_base}/models"
    result: Dict[str, Any] = {
        "lmstudio_available": False,
        "models": [],
        "recommended": None,
        "api_base": api_base,
        "error": None,
    }
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("data", [])
        result["lmstudio_available"] = True
        result["models"] = models

        if models:
            # Pick the first loaded model (LM Studio typically loads one at a time)
            model_id = models[0].get("id", "")
            result["recommended"] = f"openai/{model_id}"

        logger.debug(f"LM Studio: {len(models)} models loaded")
    except Exception as e:
        result["error"] = str(e)
        logger.debug(f"LM Studio not reachable: {e}")
    return result


def detect_local_providers() -> Dict[str, Any]:
    """Detect all available local model providers (Ollama + LM Studio).

    Returns a summary dict for use by the profiles system or diagnostics.
    """
    ollama = detect_ollama_models()
    lmstudio = detect_lmstudio_models()

    return {
        "ollama": ollama,
        "lmstudio": lmstudio,
        "any_available": ollama["ollama_available"] or lmstudio["lmstudio_available"],
    }


def build_profiles_data(
    active_profile: str = "cloud",
    local_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Build profiles data dict, optionally replacing local model refs.

    If local_model is provided, replaces all local placeholders (ollama_chat/
    and openai/ prefixed) in hybrid, local, and lmstudio profiles.
    """
    data = copy.deepcopy(DEFAULT_PROFILES_DATA)
    data["active"] = active_profile

    if local_model:
        _local_prefixes = ("ollama_chat/", "openai/")
        for profile_name in ("hybrid", "local", "lmstudio"):
            profile = data["profiles"].get(profile_name, {})
            for role in ("planner", "worker", "specialist", "guardian", "dspy"):
                if profile.get(role, "").startswith(_local_prefixes):
                    profile[role] = local_model
    return data


# ═════════════════════════════════════════════════════════════════════════
# File I/O with mtime caching
# ═════════════════════════════════════════════════════════════════════════

def _profiles_path() -> Optional[Path]:
    """Resolve path to knowledge/model_profiles.json."""
    try:
        return resolve_readable_knowledge_path("model_profiles.json")
    except Exception:
        return None


def _profiles_write_path() -> Optional[Path]:
    """Resolve the writable path to knowledge/model_profiles.json."""
    try:
        return resolve_writable_knowledge_path("model_profiles.json")
    except Exception:
        return None


def _load_raw() -> Optional[Dict]:
    """Load profiles JSON with mtime-based caching."""
    global _cached_profiles, _cached_mtime

    path = _profiles_path()
    if path is None or not path.exists():
        return None

    try:
        mtime = path.stat().st_mtime
        if _cached_profiles is not None and mtime == _cached_mtime:
            return _cached_profiles

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        _cached_profiles = data
        _cached_mtime = mtime
        logger.debug(f"Loaded model profiles from {path}")
        return data
    except Exception as e:
        logger.warning(f"Failed to load model profiles: {e}")
        return None


def invalidate_cache() -> None:
    """Force next get_models() to re-read from disk. Useful for tests."""
    global _cached_profiles, _cached_mtime
    _cached_profiles = None
    _cached_mtime = 0.0


# ═════════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════════

def get_models(profile_name: Optional[str] = None) -> ModelSet:
    """Return ModelSet for the requested (or active) profile.

    Fallback chain:
        1. Explicit profile_name argument
        2. ROOK_MODEL_PROFILE environment variable
        3. ``"active"`` field in model_profiles.json
        4. Auto-write defaults + retry
        5. FALLBACK_MODELS (hardcoded)
    """
    data = _load_raw()

    # Auto-create on first use
    if data is None:
        wrote = write_default_profiles()
        if wrote:
            data = _load_raw()

    if data is None:
        return ModelSet(**FALLBACK_MODELS)

    profiles = data.get("profiles", {})
    name = (
        profile_name
        or os.environ.get("ROOK_MODEL_PROFILE")
        or data.get("active", "cloud")
    )
    profile = profiles.get(name, {})

    if not profile:
        logger.warning(f"Profile '{name}' not found, using fallbacks")
        return ModelSet(**FALLBACK_MODELS)

    return ModelSet(
        planner=profile.get("planner", FALLBACK_MODELS["planner"]),
        worker=profile.get("worker", FALLBACK_MODELS["worker"]),
        specialist=profile.get("specialist", FALLBACK_MODELS["specialist"]),
        guardian=profile.get("guardian", FALLBACK_MODELS["guardian"]),
        dspy=profile.get("dspy", FALLBACK_MODELS["dspy"]),
        api_base=profile.get("api_base"),
    )


def get_profile_names() -> List[str]:
    """Return list of available profile names."""
    data = _load_raw()
    if data is None:
        return list(DEFAULT_PROFILES_DATA["profiles"].keys())
    return list(data.get("profiles", {}).keys())


def get_active_profile_name() -> Optional[str]:
    """Return the currently active profile name.

    Checks ROOK_MODEL_PROFILE env var first, then the JSON ``"active"`` field.
    """
    env = os.environ.get("ROOK_MODEL_PROFILE")
    if env:
        return env
    data = _load_raw()
    if data is None:
        return None
    return data.get("active")


def write_default_profiles(
    active_profile: Optional[str] = None,
    local_model: Optional[str] = None,
) -> bool:
    """Write default model_profiles.json if it doesn't exist.

    Returns True if file was written, False if it already existed.
    """
    read_path = _profiles_path()
    write_path = _profiles_write_path()
    if read_path is None or write_path is None:
        logger.warning("Cannot determine model profiles path")
        return False

    if read_path.exists() or write_path.exists():
        return False

    data = build_profiles_data(
        active_profile=active_profile or "cloud",
        local_model=local_model,
    )

    try:
        write_path.parent.mkdir(parents=True, exist_ok=True)
        with open(write_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Wrote default model profiles to {write_path}")
        invalidate_cache()
        return True
    except Exception as e:
        logger.warning(f"Failed to write model profiles: {e}")
        return False
