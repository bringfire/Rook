"""
Agent Configuration
===================

Configuration dataclasses for the Rook multi-agent system.
Adapted from Engram's config.py for Rhino/GH domain.

All values can be overridden via constructor or JSON config file.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the RookAgent loop.

    Controls LLM model, turn limits, knowledge seam toggles, cost tracking,
    and bridge connection settings.
    """

    # --- LLM ---
    model: str = "anthropic/claude-haiku-4-5-20251001"
    fallback_model: Optional[str] = None
    api_base: Optional[str] = None            # For local models (LM Studio, vLLM, etc.)
    max_tokens: int = 8192
    temperature: float = 0.0

    # --- Agent behavior ---
    max_turns: int = 30                    # Safety limit per prompt() call
    max_tool_calls_per_turn: int = 25      # Max tool calls per single LLM response

    # --- Knowledge seams ---
    knowledge_injection: bool = True       # Seam 1: inject before LLM call
    parameter_correction: bool = True      # Seam 2: check blocking gotchas
    observation_recording: bool = True     # Seam 3: record every execution
    tool_surface_adaptation: bool = True   # Seam 4: adapt tool visibility

    # --- Progressive disclosure ---
    stale_tool_turns: int = 5              # Deactivate tools unused for N turns
    max_active_tools: int = 64             # Hard cap on visible tools

    # --- Cost / safety ---
    max_input_tokens_per_task: int = 500_000  # Token budget per prompt()

    # --- Bridge (HTTP to Rhino plugin; auto-discovered when unset) ---
    bridge_base_url: Optional[str] = None
    bridge_timeout: float = 30.0           # HTTP timeout in seconds

    # --- Streaming ---
    enable_streaming: bool = False         # TODO: Implement streaming in _call_model via litellm.acompletion(stream=True)

    # --- Guardian (inline config for convenience) ---
    guardian_enabled: bool = True
    guardian_check_interval: int = 3
    guardian_max_failures: int = 3
    guardian_max_loops: int = 3
    guardian_budget_threshold: float = 0.8
    guardian_max_interventions: int = 5
    guardian_llm_analysis: bool = False
    guardian_llm_model: str = "anthropic/claude-haiku-4-5-20251001"

    # --- Persona ---
    agent_type: str = "worker"             # Persona directory name

    # --- System prompt ---
    system_prompt: str = ""                # Set by planner/spawner

    @classmethod
    def from_env(cls, **overrides) -> "AgentConfig":
        """Create config with model overrides from environment variables.

        Reads:
            ROOK_WORKER_MODEL: Override worker/default model
            ROOK_BRIDGE_URL: Override bridge base URL
        """
        env_overrides = {}
        worker_model = os.environ.get("ROOK_WORKER_MODEL")
        if worker_model:
            env_overrides["model"] = worker_model
        bridge_url = os.environ.get("ROOK_BRIDGE_URL")
        if bridge_url:
            env_overrides["bridge_base_url"] = bridge_url
        env_overrides.update(overrides)
        return cls(**env_overrides)

    @classmethod
    def from_file(cls, path: Path) -> "AgentConfig":
        """Load from JSON file, merging with defaults."""
        if not path.exists():
            logger.info(f"No config file at {path}, using defaults")
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            config = cls(**known)
            logger.info(f"Loaded agent config from {path}: model={config.model}")
            return config
        except Exception as e:
            logger.warning(f"Failed to load agent config from {path}: {e}")
            return cls()

    def to_file(self, path: Path) -> None:
        """Save config to JSON file."""
        data = {k: getattr(self, k) for k in self.__dataclass_fields__}
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved agent config to {path}")


@dataclass
class PlannerConfig:
    """Configuration for the Planner orchestrator.

    The planner uses a stronger model (Sonnet) for task decomposition
    and spawns workers with a cheaper model (Haiku) for execution.

    Model resolution priority (highest wins):
        1. Explicit ROOK_*_MODEL env vars
        2. Constructor kwargs / overrides
        3. Active model profile (knowledge/model_profiles.json)
        4. Hardcoded defaults below
    """

    # --- Models (defaults match FALLBACK_MODELS in model_profiles.py) ---
    planner_model: str = "anthropic/claude-opus-4-6"
    worker_model: str = "anthropic/claude-sonnet-4-6"
    api_base: Optional[str] = None         # For local providers (LM Studio, vLLM, Ollama)

    # --- Planning phase ---
    max_planning_turns: int = 15           # Turns for the planning agent
    max_planning_tokens: int = 200_000     # Token budget for planning
    planner_temperature: float = 0.0

    # --- Execution phase ---
    max_worker_turns: int = 30             # Max turns per worker task
    max_worker_tokens: int = 200_000       # Token budget per worker
    max_concurrent_workers: int = 3        # Parallel workers limit

    # --- Behavior ---
    auto_approve: bool = False             # Require user approval of plan
    auto_retry: bool = True                # Retry failed tasks once
    guardian_enabled: bool = True           # Attach Guardian to workers
    knowledge_injection: bool = True       # Enable knowledge seams for planner

    # --- Model profile ---
    model_profile: Optional[str] = None    # Active profile name (cloud/hybrid/local/finetuned)

    # --- Worker config override ---
    worker_config: Optional[AgentConfig] = None  # Custom worker settings

    @classmethod
    def from_env(cls, **overrides) -> "PlannerConfig":
        """Create config from model profiles + environment variable overrides.

        Resolution order:
            1. Load active model profile → set planner_model, worker_model, api_base
            2. Apply ROOK_*_MODEL env vars (override profile values)
            3. Apply explicit **overrides (override everything)

        Reads:
            ROOK_PLANNER_MODEL: Override planner model
            ROOK_WORKER_MODEL: Override worker model
            ROOK_MODEL_PROFILE: Active model profile name
        """
        # Step 1: Resolve from model profiles
        profile_overrides: dict = {}
        try:
            from .model_profiles import get_models
            profile_name = os.environ.get("ROOK_MODEL_PROFILE") or overrides.get("model_profile")
            models = get_models(profile_name)
            profile_overrides["planner_model"] = models.planner
            profile_overrides["worker_model"] = models.worker
            if models.api_base:
                profile_overrides["api_base"] = models.api_base
            if profile_name:
                profile_overrides["model_profile"] = profile_name
            logger.info(
                "PlannerConfig: profile=%s planner=%s worker=%s api_base=%s",
                profile_name or "(active)", models.planner, models.worker, models.api_base,
            )
        except Exception as e:
            logger.debug("Model profiles unavailable, using defaults: %s", e)

        # Step 2: Env vars override profiles
        env_overrides: dict = {}
        planner_model = os.environ.get("ROOK_PLANNER_MODEL")
        if planner_model:
            env_overrides["planner_model"] = planner_model
        worker_model = os.environ.get("ROOK_WORKER_MODEL")
        if worker_model:
            env_overrides["worker_model"] = worker_model
        model_profile = os.environ.get("ROOK_MODEL_PROFILE")
        if model_profile:
            env_overrides["model_profile"] = model_profile

        # Step 3: Merge (profile < env < explicit overrides)
        merged = {**profile_overrides, **env_overrides, **overrides}
        return cls(**merged)


@dataclass
class GuardianConfig:
    """Configuration for the Guardian trajectory monitor.

    Controls detection thresholds, steering behavior, and optional
    LLM-based trajectory analysis.
    """

    check_interval: int = 3                # Analyze every N tool calls
    max_consecutive_failures: int = 3      # Same tool failing N times -> stuck
    max_identical_calls: int = 3           # Same tool+params N times -> looping
    budget_warning_threshold: float = 0.8  # Warn at 80% budget
    enable_steering: bool = True           # Actually inject corrections
    max_interventions: int = 5             # Abort after this many interventions
    # LLM trajectory analysis (Phase 2)
    enable_llm_analysis: bool = False
    llm_analysis_model: str = "anthropic/claude-haiku-4-5-20251001"
    llm_analysis_interval_multiplier: int = 3  # LLM every check_interval * this
    api_base: Optional[str] = None         # For local providers (LM Studio, vLLM)


@dataclass
class ConductorConfig:
    """Configuration for the Conductor fleet coordinator.

    Detects systemic issues across parallel workers (e.g., Rhino bridge
    down, common tool failures affecting multiple agents).
    """

    bridge_failure_quorum: int = 2         # N agents stuck on bridge -> systemic
    systemic_tool_quorum: int = 2          # N agents failing same tool -> systemic
    check_interval_seconds: float = 5.0    # How often to check cross-agent patterns
    dedup_window_seconds: float = 60.0     # Don't re-report same issue within window
