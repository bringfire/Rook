"""
Contextual Multi-Armed Bandit Integration (Phase 3)

This module provides a wrapper around MABWiser for contextual pattern
recommendation in the Rook knowledge system.

Classes:
- MABConfig: Configuration dataclass for MAB setup
- ContextualMAB: Wrapper class managing MAB lifecycle

Functions:
- warm_start_mab: Initialize MAB from historical observations
- get_pattern_ranking: Get pattern ranking with fallback logic
"""

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .context_storage import ContextHistory, ScalerManager
from .runtime_paths import resolve_writable_knowledge_path

logger = logging.getLogger("rook.contextual_mab")

# Storage paths
CONTEXTUAL_MAB_PATH = resolve_writable_knowledge_path("contextual_mab.pkl")

# MABWiser integration - graceful fallback if not installed
_mabwiser_available = False
try:
    from mabwiser.mab import MAB, LearningPolicy, NeighborhoodPolicy
    _mabwiser_available = True
except ImportError:
    logger.warning(
        "MABWiser not installed. Contextual MAB disabled. "
        "Install with: pip install mabwiser"
    )
    MAB = None
    LearningPolicy = None
    NeighborhoodPolicy = None


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class MABConfig:
    """Configuration for contextual MAB."""

    # Learning policy
    learning_policy: str = "thompson_sampling"  # "ucb1", "epsilon_greedy"

    # Neighborhood policy for contextual learning
    neighborhood_policy: str = "knearest"  # "radius", "clusters"
    neighborhood_k: int = 5  # for knearest
    neighborhood_radius: float = 1.0  # for radius
    n_clusters: int = 4  # for clusters

    # Policy-specific parameters
    exploration_alpha: float = 1.0  # UCB1 alpha
    epsilon: float = 0.1  # epsilon-greedy

    # General settings
    seed: int = 42
    n_jobs: int = 1

    # Minimum observations for warm start
    min_observations: int = 10

    def validate(self) -> bool:
        """Validate configuration values."""
        valid_learning = {"thompson_sampling", "ucb1", "epsilon_greedy"}
        valid_neighborhood = {"knearest", "radius", "clusters"}

        if self.learning_policy not in valid_learning:
            logger.error(f"Invalid learning_policy: {self.learning_policy}")
            return False

        if self.neighborhood_policy not in valid_neighborhood:
            logger.error(f"Invalid neighborhood_policy: {self.neighborhood_policy}")
            return False

        if self.neighborhood_k < 1:
            logger.error(f"neighborhood_k must be >= 1, got {self.neighborhood_k}")
            return False

        if self.neighborhood_radius <= 0:
            logger.error(f"neighborhood_radius must be > 0, got {self.neighborhood_radius}")
            return False

        if self.n_clusters < 1:
            logger.error(f"n_clusters must be >= 1, got {self.n_clusters}")
            return False

        if self.epsilon < 0 or self.epsilon > 1:
            logger.error(f"epsilon must be in [0, 1], got {self.epsilon}")
            return False

        return True


# =============================================================================
# Contextual MAB Wrapper
# =============================================================================

class ContextualMAB:
    """
    Wrapper for MABWiser with context support.

    Provides a clean interface for:
    - Initializing MAB with pattern arms
    - Training on batch or streaming data
    - Making contextual predictions
    - Managing arms (add/remove patterns)
    """

    def __init__(self, config: Optional[MABConfig] = None):
        """
        Initialize contextual MAB.

        Args:
            config: MAB configuration (uses defaults if None)
        """
        self.config = config or MABConfig()
        self.mab: Optional["MAB"] = None
        self._is_fitted = False
        self._arms: list[str] = []

    @property
    def is_fitted(self) -> bool:
        """Check if MAB has been fitted with data."""
        return self._is_fitted

    @property
    def arms(self) -> list[str]:
        """Get list of current arm IDs."""
        return self._arms.copy()

    def initialize(self, pattern_ids: list[str]) -> bool:
        """
        Initialize MAB with available arms (patterns).

        Args:
            pattern_ids: List of pattern IDs to use as arms

        Returns:
            True if initialization succeeded
        """
        if not _mabwiser_available:
            logger.error("MABWiser not available")
            return False

        if not pattern_ids:
            logger.error("Cannot initialize MAB with empty pattern list")
            return False

        if not self.config.validate():
            return False

        try:
            # Build learning policy
            learning_policy = self._build_learning_policy()

            # Build neighborhood policy
            neighborhood_policy = self._build_neighborhood_policy()

            # Create MAB instance
            self.mab = MAB(
                arms=pattern_ids,
                learning_policy=learning_policy,
                neighborhood_policy=neighborhood_policy,
                seed=self.config.seed,
                n_jobs=self.config.n_jobs
            )

            self._arms = list(pattern_ids)
            self._is_fitted = False

            logger.info(f"Initialized ContextualMAB with {len(pattern_ids)} arms")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize MAB: {e}")
            return False

    def _build_learning_policy(self) -> "LearningPolicy":
        """Build the learning policy from config."""
        if self.config.learning_policy == "thompson_sampling":
            return LearningPolicy.ThompsonSampling()
        elif self.config.learning_policy == "ucb1":
            return LearningPolicy.UCB1(alpha=self.config.exploration_alpha)
        elif self.config.learning_policy == "epsilon_greedy":
            return LearningPolicy.EpsilonGreedy(epsilon=self.config.epsilon)
        else:
            # Default to Thompson Sampling
            return LearningPolicy.ThompsonSampling()

    def _build_neighborhood_policy(self) -> "NeighborhoodPolicy":
        """Build the neighborhood policy from config."""
        if self.config.neighborhood_policy == "knearest":
            return NeighborhoodPolicy.KNearest(k=self.config.neighborhood_k)
        elif self.config.neighborhood_policy == "radius":
            return NeighborhoodPolicy.Radius(radius=self.config.neighborhood_radius)
        elif self.config.neighborhood_policy == "clusters":
            return NeighborhoodPolicy.Clusters(n_clusters=self.config.n_clusters)
        else:
            # Default to KNearest
            return NeighborhoodPolicy.KNearest(k=self.config.neighborhood_k)

    def fit(
        self,
        contexts: list[list[float]],
        decisions: list[str],
        rewards: list[int]
    ) -> bool:
        """
        Batch fit MAB on historical data.

        Args:
            contexts: List of context vectors
            decisions: List of arm IDs that were chosen
            rewards: List of rewards (0 or 1)

        Returns:
            True if fitting succeeded
        """
        if self.mab is None:
            logger.error("MAB not initialized. Call initialize() first.")
            return False

        if not contexts or not decisions or not rewards:
            logger.error("Cannot fit with empty data")
            return False

        if len(contexts) != len(decisions) or len(decisions) != len(rewards):
            logger.error(
                f"Data length mismatch: contexts={len(contexts)}, "
                f"decisions={len(decisions)}, rewards={len(rewards)}"
            )
            return False

        try:
            self.mab.fit(decisions, rewards, contexts)
            self._is_fitted = True
            logger.info(f"Fitted MAB on {len(contexts)} observations")
            return True

        except Exception as e:
            logger.error(f"Failed to fit MAB: {e}")
            return False

    def partial_fit(
        self,
        context: list[float],
        decision: str,
        reward: int
    ) -> bool:
        """
        Online update with single observation.

        Args:
            context: Context vector
            decision: Arm ID that was chosen
            reward: Reward (0 or 1)

        Returns:
            True if update succeeded
        """
        if self.mab is None:
            logger.error("MAB not initialized. Call initialize() first.")
            return False

        if not self._is_fitted:
            logger.error("MAB not fitted. Call fit() first.")
            return False

        try:
            self.mab.partial_fit([decision], [reward], [context])
            return True

        except Exception as e:
            logger.error(f"Failed to partial_fit MAB: {e}")
            return False

    def predict(self, context: list[float]) -> Optional[str]:
        """
        Get best pattern for context.

        Args:
            context: Context vector

        Returns:
            Best arm ID, or None if prediction failed
        """
        if self.mab is None or not self._is_fitted:
            return None

        try:
            prediction = self.mab.predict([context])
            # MABWiser returns a single string when given one context
            if isinstance(prediction, str):
                return prediction
            # In case it returns a list/array
            return prediction[0] if prediction else None

        except Exception as e:
            logger.error(f"Failed to predict: {e}")
            return None

    def predict_expectations(
        self,
        context: list[float]
    ) -> dict[str, float]:
        """
        Get expected rewards for all patterns given context.

        Args:
            context: Context vector

        Returns:
            Dictionary mapping arm IDs to expected rewards
        """
        if self.mab is None or not self._is_fitted:
            return {}

        try:
            expectations = self.mab.predict_expectations([context])
            # expectations is a dict with arm -> list of expectations
            # We have one context, so take first element of each list
            return {
                arm: exp[0] if isinstance(exp, list) else exp
                for arm, exp in expectations.items()
            }

        except Exception as e:
            logger.error(f"Failed to predict_expectations: {e}")
            return {}

    def add_arm(self, pattern_id: str) -> bool:
        """
        Add new pattern to MAB.

        Args:
            pattern_id: Pattern ID to add as arm

        Returns:
            True if arm was added
        """
        if self.mab is None:
            logger.error("MAB not initialized")
            return False

        if pattern_id in self._arms:
            logger.warning(f"Arm '{pattern_id}' already exists")
            return True

        try:
            self.mab.add_arm(pattern_id)
            self._arms.append(pattern_id)
            logger.info(f"Added arm: {pattern_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add arm: {e}")
            return False

    def remove_arm(self, pattern_id: str) -> bool:
        """
        Remove pattern from MAB.

        Args:
            pattern_id: Pattern ID to remove

        Returns:
            True if arm was removed
        """
        if self.mab is None:
            logger.error("MAB not initialized")
            return False

        if pattern_id not in self._arms:
            logger.warning(f"Arm '{pattern_id}' not found")
            return False

        try:
            self.mab.remove_arm(pattern_id)
            self._arms.remove(pattern_id)
            logger.info(f"Removed arm: {pattern_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove arm: {e}")
            return False

    def save(self, path: Optional[Path] = None) -> bool:
        """
        Save MAB state to disk.

        Args:
            path: Custom path (defaults to CONTEXTUAL_MAB_PATH)

        Returns:
            True if save succeeded
        """
        save_path = path or CONTEXTUAL_MAB_PATH

        if self.mab is None:
            logger.warning("Cannot save uninitialized MAB")
            return False

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "mab": self.mab,
                "config": self.config,
                "is_fitted": self._is_fitted,
                "arms": self._arms
            }
            with open(save_path, 'wb') as f:
                pickle.dump(state, f)
            logger.info(f"Saved ContextualMAB to {save_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save MAB: {e}")
            return False

    def load(self, path: Optional[Path] = None) -> bool:
        """
        Load MAB state from disk.

        Args:
            path: Custom path (defaults to CONTEXTUAL_MAB_PATH)

        Returns:
            True if load succeeded
        """
        load_path = path or CONTEXTUAL_MAB_PATH

        if not load_path.exists():
            logger.warning(f"MAB file not found: {load_path}")
            return False

        try:
            with open(load_path, 'rb') as f:
                state = pickle.load(f)

            self.mab = state["mab"]
            self.config = state["config"]
            self._is_fitted = state["is_fitted"]
            self._arms = state["arms"]

            logger.info(f"Loaded ContextualMAB from {load_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load MAB: {e}")
            return False


# =============================================================================
# Warm Start and Fallback Functions
# =============================================================================

def warm_start_mab(
    mab: ContextualMAB,
    history: ContextHistory,
    scaler: Optional[ScalerManager] = None
) -> bool:
    """
    Initialize MAB from historical observations.

    Args:
        mab: ContextualMAB instance (must be initialized with arms)
        history: ContextHistory with observations
        scaler: Optional ScalerManager for context normalization

    Returns:
        True if warm start succeeded (enough observations)
    """
    observations = history.get_observations()

    if len(observations) < mab.config.min_observations:
        logger.warning(
            f"Insufficient observations for warm start: "
            f"{len(observations)} < {mab.config.min_observations}"
        )
        return False

    # Extract data from observations
    contexts = [obs['features'] for obs in observations]
    decisions = [obs['pattern_id'] for obs in observations]
    rewards = [1 if obs['outcome'] == 'success' else 0 for obs in observations]

    # Filter to only include decisions for known arms
    known_arms = set(mab.arms)
    filtered_data = [
        (ctx, dec, rew)
        for ctx, dec, rew in zip(contexts, decisions, rewards)
        if dec in known_arms
    ]

    if len(filtered_data) < mab.config.min_observations:
        logger.warning(
            f"Insufficient observations for known arms: "
            f"{len(filtered_data)} < {mab.config.min_observations}"
        )
        return False

    contexts = [d[0] for d in filtered_data]
    decisions = [d[1] for d in filtered_data]
    rewards = [d[2] for d in filtered_data]

    # Scale contexts if scaler provided
    if scaler is not None:
        scaler.fit(contexts)
        contexts = [scaler.transform(c) for c in contexts]

    # Fit MAB
    success = mab.fit(contexts, decisions, rewards)

    if success:
        logger.info(f"Warm started MAB with {len(contexts)} observations")

    return success


def get_pattern_ranking(
    mab: ContextualMAB,
    context: list[float],
    patterns: list[dict[str, Any]],
    fallback: str = "static_weight"
) -> list[dict[str, Any]]:
    """
    Get pattern ranking with fallback for edge cases.

    Args:
        mab: ContextualMAB instance
        context: Context vector for prediction
        patterns: List of pattern dictionaries (must have 'id' key)
        fallback: Fallback strategy ("static_weight", "uniform", "random")

    Returns:
        Sorted list of patterns (highest expected reward first)
    """
    if not patterns:
        return []

    # Check if MAB can make predictions
    if not mab.is_fitted:
        logger.debug("MAB not fitted, using fallback ranking")
        return _fallback_ranking(patterns, fallback)

    try:
        expectations = mab.predict_expectations(context)

        if not expectations:
            logger.debug("Empty expectations, using fallback ranking")
            return _fallback_ranking(patterns, fallback)

        # Sort patterns by expected reward
        def get_score(pattern: dict) -> float:
            pattern_id = pattern.get('id', '')
            return expectations.get(pattern_id, 0.0)

        return sorted(patterns, key=get_score, reverse=True)

    except Exception as e:
        logger.warning(f"Prediction failed, using fallback: {e}")
        return _fallback_ranking(patterns, fallback)


def _fallback_ranking(
    patterns: list[dict[str, Any]],
    strategy: str
) -> list[dict[str, Any]]:
    """
    Apply fallback ranking strategy.

    Args:
        patterns: List of pattern dictionaries
        strategy: "static_weight", "uniform", or "random"

    Returns:
        Ranked list of patterns
    """
    if strategy == "static_weight":
        # Sort by static weight if available
        return sorted(
            patterns,
            key=lambda p: p.get('weight', p.get('_weight', 0.5)),
            reverse=True
        )
    elif strategy == "random":
        import random
        shuffled = patterns.copy()
        random.shuffle(shuffled)
        return shuffled
    else:  # uniform
        return patterns.copy()


# =============================================================================
# Utility Functions
# =============================================================================

def is_mabwiser_available() -> bool:
    """Check if MABWiser library is available."""
    return _mabwiser_available
