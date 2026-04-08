"""MABWiser-based Knowledge Retrieval Module.

This module learns which knowledge context to return for a given query.
It uses Multi-Armed Bandits to balance exploration vs exploitation:
- Explore new contexts when uncertain
- Exploit known-good contexts when confident

Arms: Each {tool}:{context} pair is an arm
Features: Query intent, tool name, recent history
Reward: 1 if subsequent tool call succeeded, 0 if failed

The retrieval MAB improves over time as it learns which contexts
lead to successful tool usage.
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from ..runtime_paths import resolve_writable_knowledge_path

logger = logging.getLogger(__name__)

# Try to import MABWiser, but allow module to load without it
try:
    from mabwiser.mab import MAB, LearningPolicy, NeighborhoodPolicy
    MABWISER_AVAILABLE = True
except ImportError:
    MABWISER_AVAILABLE = False
    logger.warning("MABWiser not available. KnowledgeRetrievalMAB will not work.")


# =============================================================================
# Feature Encoding
# =============================================================================


@dataclass
class QueryFeatures:
    """Features extracted from a knowledge query."""

    tool: str
    intent: str
    recent_failures: list[str] = field(default_factory=list)
    session_length: int = 0
    time_of_day_hour: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "intent": self.intent,
            "recent_failures": self.recent_failures,
            "session_length": self.session_length,
            "time_of_day_hour": self.time_of_day_hour,
        }


class QueryFeatureEncoder:
    """Encode query information into MAB context features.

    Converts a query (tool, intent, context) into a fixed-size feature vector
    that the contextual MAB can use to make context-aware selections.

    Feature Vector (15 dimensions):
        [0-5]: Intent keyword indicators
        [6]: Has recent failures indicator
        [7]: Number of recent failures (normalized)
        [8-11]: Tool category indicators (create, modify, query, advanced)
        [12]: Session length (normalized)
        [13]: Time of day (normalized 0-1)
        [14]: Intent length (normalized)
    """

    # Keywords that indicate specific intents
    INTENT_KEYWORDS = [
        "nested",   # Creating nested/hierarchical structures
        "color",    # Color-related operations
        "delete",   # Deletion operations
        "create",   # Creation operations
        "error",    # Troubleshooting errors
        "failed",   # Recovering from failures
    ]

    # Tool categories for feature extraction
    TOOL_CATEGORIES = {
        "create": [
            "rhino_create", "rhino_layer_create", "rhino_block_create",
            "rhino_subd_box", "rhino_subd_sphere", "rhino_mesh_box",
        ],
        "modify": [
            "rhino_transform", "rhino_boolean", "rhino_loft", "rhino_sweep",
            "rhino_extrude", "rhino_offset_curve", "rhino_split_brep",
        ],
        "query": [
            "rhino_objects", "rhino_selection", "rhino_geometry", "rhino_layers",
            "rhino_measure_distance", "rhino_measure_area", "rhino_is_valid",
        ],
        "advanced": [
            "rhino_execute", "rhino_command", "rhino_boolean",
            "rhino_intersect_breps", "rhino_project_curve",
        ],
    }

    def __init__(self) -> None:
        self.feature_dim = 15

    def encode(
        self,
        tool: str,
        intent: str,
        recent_failures: list[str] | None = None,
        session_length: int = 0,
    ) -> np.ndarray:
        """Encode query into feature vector.

        Args:
            tool: The MCP tool name
            intent: Natural language intent/description
            recent_failures: List of recent failure messages
            session_length: How many operations in current session

        Returns:
            15-dimensional numpy array
        """
        features = []

        # [0-5]: Intent keyword indicators
        intent_lower = intent.lower() if intent else ""
        for keyword in self.INTENT_KEYWORDS:
            features.append(1.0 if keyword in intent_lower else 0.0)

        # [6]: Has recent failures indicator
        recent_failures = recent_failures or []
        features.append(1.0 if recent_failures else 0.0)

        # [7]: Number of recent failures (normalized, cap at 5)
        features.append(min(len(recent_failures) / 5.0, 1.0))

        # [8-11]: Tool category indicators
        for category in ["create", "modify", "query", "advanced"]:
            is_in_category = any(
                tool.startswith(prefix) or tool == prefix
                for prefix in self.TOOL_CATEGORIES.get(category, [])
            )
            features.append(1.0 if is_in_category else 0.0)

        # [12]: Session length (normalized, cap at 100)
        features.append(min(session_length / 100.0, 1.0))

        # [13]: Time of day (normalized 0-1)
        hour = datetime.now().hour
        features.append(hour / 24.0)

        # [14]: Intent length (normalized, cap at 100 chars)
        features.append(min(len(intent) / 100.0, 1.0) if intent else 0.0)

        return np.array(features, dtype=np.float32)

    def encode_batch(
        self,
        queries: list[QueryFeatures],
    ) -> np.ndarray:
        """Encode multiple queries into feature matrix.

        Args:
            queries: List of QueryFeatures to encode

        Returns:
            (N, 15) numpy array where N is number of queries
        """
        return np.array([
            self.encode(
                q.tool,
                q.intent,
                q.recent_failures,
                q.session_length,
            )
            for q in queries
        ])


# =============================================================================
# Knowledge Retrieval MAB
# =============================================================================


@dataclass
class RetrievalOutcome:
    """Record of a retrieval attempt and its outcome."""

    arm: str  # {tool}:{context}
    features: np.ndarray
    succeeded: bool
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"


class KnowledgeRetrievalMAB:
    """Contextual MAB for selecting which knowledge context to return.

    This MAB learns which context is most helpful for each query type.
    It uses K-Nearest Neighbors + Thompson Sampling:
    - K-NN finds similar past queries
    - Thompson Sampling balances exploration vs exploitation

    Arms:
        Each arm is a "{tool}:{context}" string.
        Example: "rhino_layer_create:nested"

    Features:
        15-dimensional vector from QueryFeatureEncoder

    Reward:
        1.0 if the subsequent tool call succeeded
        0.0 if it failed

    Usage:
        mab = KnowledgeRetrievalMAB()

        # Select context for a query
        context = mab.select_context(
            tool="rhino_layer_create",
            intent="create nested layer",
        )

        # After tool execution, record outcome
        mab.record_outcome(
            arm=f"rhino_layer_create:{context}",
            tool_succeeded=True
        )

        # Save learned weights
        mab.save("knowledge/retrieval_mab.pkl")
    """

    def __init__(
        self,
        k_neighbors: int = 5,
        min_observations_for_contextual: int = 10,
    ) -> None:
        """Initialize the retrieval MAB.

        Args:
            k_neighbors: Number of neighbors for K-NN contextual policy
            min_observations_for_contextual: Minimum data points before
                using contextual features (falls back to Thompson Sampling)
        """
        self.k_neighbors = k_neighbors
        self.min_observations = min_observations_for_contextual
        self.feature_encoder = QueryFeatureEncoder()

        # Arms are populated dynamically from consolidated knowledge
        self.arms: list[str] = []

        # Training data for MAB
        self.decisions: list[str] = []  # Arm selected
        self.rewards: list[float] = []  # Reward received
        self.contexts: list[np.ndarray] = []  # Feature vectors

        # MAB instance (lazy initialization)
        self._mab: MAB | None = None
        self._fitted = False

    @property
    def is_fitted(self) -> bool:
        """Check if MAB has been fitted with data."""
        return self._fitted and len(self.decisions) >= self.min_observations

    def add_arms_from_consolidated(
        self,
        consolidated_tools: dict[str, Any],
    ) -> None:
        """Populate arms from consolidated knowledge structure.

        Args:
            consolidated_tools: The "tools" dict from condensed_knowledge.json
        """
        new_arms = []
        for tool_name, tool_data in consolidated_tools.items():
            contexts = tool_data.get("contexts", {})
            for context_name in contexts:
                arm = f"{tool_name}:{context_name}"
                if arm not in self.arms:
                    new_arms.append(arm)

        self.arms.extend(new_arms)
        logger.info(f"Added {len(new_arms)} arms, total: {len(self.arms)}")

        # Reset MAB if arms changed
        if new_arms:
            self._mab = None
            self._fitted = False

    def select_context(
        self,
        tool: str,
        intent: str,
        recent_failures: list[str] | None = None,
    ) -> str | None:
        """Select best context for this query.

        Args:
            tool: The MCP tool name
            intent: Natural language intent
            recent_failures: List of recent failure messages

        Returns:
            Context name (not the full arm), or None if no contexts available
        """
        # Find available arms for this tool
        available = [a for a in self.arms if a.startswith(f"{tool}:")]

        if not available:
            logger.debug(f"No consolidated knowledge for {tool}")
            return None

        if not MABWISER_AVAILABLE:
            # Fallback: random selection
            import random
            arm = random.choice(available)
            return arm.split(":")[1]

        # Encode features
        features = self.feature_encoder.encode(tool, intent, recent_failures)

        # Use MAB to select
        if self.is_fitted:
            try:
                arm = self._mab.predict(contexts=[features])[0]
                if arm in available:
                    return arm.split(":")[1]
            except Exception as e:
                logger.warning(f"MAB prediction failed: {e}")

        # Fallback: Thompson Sampling without context
        return self._thompson_sampling_select(available)

    def _thompson_sampling_select(self, arms: list[str]) -> str:
        """Simple Thompson Sampling selection without contextual features."""
        # Count successes and failures per arm
        arm_successes: dict[str, int] = {a: 1 for a in arms}  # Prior
        arm_failures: dict[str, int] = {a: 1 for a in arms}  # Prior

        for arm, reward in zip(self.decisions, self.rewards):
            if arm in arms:
                if reward > 0.5:
                    arm_successes[arm] = arm_successes.get(arm, 1) + 1
                else:
                    arm_failures[arm] = arm_failures.get(arm, 1) + 1

        # Sample from Beta distribution
        samples = {}
        for arm in arms:
            alpha = arm_successes.get(arm, 1)
            beta = arm_failures.get(arm, 1)
            samples[arm] = np.random.beta(alpha, beta)

        best_arm = max(samples, key=samples.get)
        return best_arm.split(":")[1]

    def record_outcome(
        self,
        arm: str,
        tool_succeeded: bool,
        features: np.ndarray | None = None,
    ) -> None:
        """Update MAB with feedback.

        Args:
            arm: The arm that was selected (e.g., "rhino_layer_create:nested")
            tool_succeeded: Whether the subsequent tool call succeeded
            features: Optional pre-computed features (if not provided, uses last query)
        """
        if arm not in self.arms:
            logger.warning(f"Unknown arm: {arm}")
            self.arms.append(arm)

        reward = 1.0 if tool_succeeded else 0.0

        self.decisions.append(arm)
        self.rewards.append(reward)

        if features is not None:
            self.contexts.append(features)
        elif self.contexts:
            # Use last context if features not provided
            self.contexts.append(self.contexts[-1])
        else:
            # Generate placeholder features
            parts = arm.split(":")
            tool = parts[0] if parts else ""
            self.contexts.append(
                self.feature_encoder.encode(tool, "", [])
            )

        # Re-fit MAB periodically
        if len(self.decisions) >= self.min_observations and len(self.decisions) % 10 == 0:
            self._fit_mab()

        logger.debug(f"Recorded outcome: {arm} -> {reward}")

    def _fit_mab(self) -> None:
        """Fit or update the MAB with accumulated data."""
        if not MABWISER_AVAILABLE:
            return

        if len(self.decisions) < self.min_observations:
            return

        try:
            # Create K-NN contextual MAB
            self._mab = MAB(
                arms=self.arms,
                learning_policy=LearningPolicy.ThompsonSampling(),
                neighborhood_policy=NeighborhoodPolicy.KNearest(k=self.k_neighbors),
            )

            # Fit with accumulated data
            contexts_array = np.array(self.contexts)
            self._mab.fit(
                decisions=self.decisions,
                rewards=self.rewards,
                contexts=contexts_array,
            )

            self._fitted = True
            logger.info(f"Fitted MAB with {len(self.decisions)} observations")

        except Exception as e:
            logger.error(f"Failed to fit MAB: {e}")
            self._fitted = False

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the MAB state."""
        # Compute per-arm success rates
        arm_stats = {}
        for arm in self.arms:
            successes = sum(
                1 for a, r in zip(self.decisions, self.rewards)
                if a == arm and r > 0.5
            )
            total = sum(1 for a in self.decisions if a == arm)
            arm_stats[arm] = {
                "successes": successes,
                "total": total,
                "success_rate": successes / total if total > 0 else 0.0,
            }

        return {
            "total_arms": len(self.arms),
            "total_observations": len(self.decisions),
            "is_fitted": self.is_fitted,
            "arm_stats": arm_stats,
        }

    def save(self, path: Path | str) -> None:
        """Save MAB state to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "arms": self.arms,
            "decisions": self.decisions,
            "rewards": self.rewards,
            "contexts": [c.tolist() for c in self.contexts],
            "k_neighbors": self.k_neighbors,
            "min_observations": self.min_observations,
            "fitted": self._fitted,
        }

        with open(path, "wb") as f:
            pickle.dump(state, f)

        logger.info(f"Saved retrieval MAB to {path}")

    @classmethod
    def load(cls, path: Path | str) -> "KnowledgeRetrievalMAB":
        """Load MAB state from file."""
        path = Path(path)

        if not path.exists():
            logger.info(f"No existing MAB at {path}, creating new")
            return cls()

        with open(path, "rb") as f:
            state = pickle.load(f)

        mab = cls(
            k_neighbors=state.get("k_neighbors", 5),
            min_observations_for_contextual=state.get("min_observations", 10),
        )

        mab.arms = state.get("arms", [])
        mab.decisions = state.get("decisions", [])
        mab.rewards = state.get("rewards", [])
        mab.contexts = [np.array(c) for c in state.get("contexts", [])]
        mab._fitted = state.get("fitted", False)

        # Re-fit if we have enough data
        if len(mab.decisions) >= mab.min_observations:
            mab._fit_mab()

        logger.info(f"Loaded retrieval MAB from {path} with {len(mab.decisions)} observations")
        return mab


# =============================================================================
# Convenience Functions
# =============================================================================


def load_retrieval_mab(
    path: Path | str | None = None,
) -> KnowledgeRetrievalMAB:
    """Load or create the retrieval MAB.

    Args:
        path: Path to MAB pickle file. If None, uses default location.

    Returns:
        KnowledgeRetrievalMAB instance
    """
    if path is None:
        path = DEFAULT_RETRIEVAL_MAB_PATH

    return KnowledgeRetrievalMAB.load(path)


def initialize_retrieval_mab_from_condensed(
    condensed_path: Path | str,
    mab_path: Path | str | None = None,
) -> KnowledgeRetrievalMAB:
    """Initialize retrieval MAB from condensed knowledge.

    Creates a new MAB with arms from the consolidated knowledge structure.

    Args:
        condensed_path: Path to condensed_knowledge.json
        mab_path: Path to save MAB. If None, uses default location.

    Returns:
        Initialized KnowledgeRetrievalMAB
    """
    condensed_path = Path(condensed_path)
    mab_path = Path(mab_path) if mab_path else DEFAULT_RETRIEVAL_MAB_PATH

    # Load existing MAB or create new
    mab = KnowledgeRetrievalMAB.load(mab_path)

    # Load condensed knowledge
    if condensed_path.exists():
        with open(condensed_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        tools = data.get("tools", {})
        mab.add_arms_from_consolidated(tools)

    # Save updated MAB
    mab.save(mab_path)

    return mab


# Default paths
DEFAULT_RETRIEVAL_MAB_PATH = resolve_writable_knowledge_path("retrieval_mab.pkl")
