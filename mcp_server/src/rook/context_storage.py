"""
Context Storage & Persistence for Contextual MAB (Phase 2)

This module provides storage and retrieval of context observations
for training the contextual multi-armed bandit.

Classes:
- ContextHistory: Stores and retrieves context observations
- ScalerManager: Manages feature scaling for consistent encoding
- Migration utilities for schema versioning
"""

import json
import pickle
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
import hashlib
from .runtime_paths import resolve_writable_knowledge_path

logger = logging.getLogger("rook.context_storage")

# Storage paths
CONTEXT_HISTORY_PATH = resolve_writable_knowledge_path("context_history.json")
SCALER_PATH = resolve_writable_knowledge_path("context_scaler.pkl")

# Schema version for migration tracking
SCHEMA_VERSION = "2.0.0"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class ContextObservation:
    """A single context observation for MAB learning."""
    id: str
    features: list[float]  # 23-dimensional context vector
    pattern_id: str
    outcome: str  # "success" or "failure"
    timestamp: str  # ISO format
    intent: str = ""
    tool: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextObservation":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            features=data["features"],
            pattern_id=data["pattern_id"],
            outcome=data["outcome"],
            timestamp=data["timestamp"],
            intent=data.get("intent", ""),
            tool=data.get("tool", ""),
            metadata=data.get("metadata", {})
        )


# =============================================================================
# Context History Manager
# =============================================================================

class ContextHistory:
    """
    Manages historical context observations for MAB training.

    Stores observations in a JSON file with newest-first ordering.
    Supports filtering by pattern ID and pruning old observations.
    """

    def __init__(self, path: Optional[Path] = None):
        """
        Initialize context history.

        Args:
            path: Custom path for history file (defaults to CONTEXT_HISTORY_PATH)
        """
        self.path = path or CONTEXT_HISTORY_PATH
        self._observations: list[ContextObservation] = []
        self._loaded = False

    def _ensure_loaded(self):
        """Lazy load observations from disk."""
        if not self._loaded:
            self.load()
            self._loaded = True

    def load(self) -> bool:
        """Load observations from disk."""
        self._observations = []
        if not self.path.exists():
            return True  # Empty is valid

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))

            # Handle schema migration
            if isinstance(data, dict):
                version = data.get("schema_version", "1.0.0")
                observations_data = data.get("observations", [])
            elif isinstance(data, list):
                # Old format: just a list of observations
                observations_data = data
            else:
                logger.error(f"Invalid context history format in {self.path}")
                return False

            for obs_data in observations_data:
                try:
                    self._observations.append(ContextObservation.from_dict(obs_data))
                except (KeyError, TypeError) as e:
                    logger.warning(f"Skipping invalid observation: {e}")
                    continue

            return True
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse context history: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to load context history: {e}")
            return False

    def save(self) -> bool:
        """Save observations to disk."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "schema_version": SCHEMA_VERSION,
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "observation_count": len(self._observations),
                "observations": [obs.to_dict() for obs in self._observations]
            }
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to save context history: {e}")
            return False

    def add_observation(
        self,
        context: list[float],
        pattern_id: str,
        outcome: str,
        intent: str = "",
        tool: str = "",
        metadata: Optional[dict] = None
    ) -> str:
        """
        Add a new context observation.

        Args:
            context: 23-dimensional feature vector
            pattern_id: ID of the pattern used
            outcome: "success" or "failure"
            intent: Natural language intent (optional)
            tool: MCP tool name (optional)
            metadata: Additional metadata (optional)

        Returns:
            ID of the new observation

        Raises:
            ValueError: If context vector is invalid
        """
        self._ensure_loaded()

        # Validate context vector
        if not isinstance(context, list):
            raise ValueError("Context must be a list")
        if len(context) not in (21, 23):
            raise ValueError(f"Context must have 23 dimensions (or 21 for legacy), got {len(context)}")
        for i, val in enumerate(context):
            if not isinstance(val, (int, float)):
                raise ValueError(f"Context value at index {i} must be numeric, got {type(val)}")

        # Validate outcome
        if outcome not in ("success", "failure"):
            raise ValueError(f"Outcome must be 'success' or 'failure', got '{outcome}'")

        # Generate unique ID
        timestamp = datetime.now(timezone.utc).isoformat()
        hash_input = f"{timestamp}:{pattern_id}:{context}"
        obs_id = f"ctx_{hashlib.md5(hash_input.encode()).hexdigest()[:12]}"

        observation = ContextObservation(
            id=obs_id,
            features=context,
            pattern_id=pattern_id,
            outcome=outcome,
            timestamp=timestamp,
            intent=intent,
            tool=tool,
            metadata=metadata or {}
        )

        # Insert at beginning (newest first)
        self._observations.insert(0, observation)

        # Auto-save
        self.save()

        return obs_id

    def get_observations(self, limit: int = 1000) -> list[dict]:
        """
        Get recent observations for MAB training.

        Args:
            limit: Maximum number of observations to return

        Returns:
            List of observation dictionaries, newest first
        """
        self._ensure_loaded()
        return [obs.to_dict() for obs in self._observations[:limit]]

    def get_observations_for_pattern(self, pattern_id: str) -> list[dict]:
        """
        Get all observations for a specific pattern.

        Args:
            pattern_id: Pattern ID to filter by

        Returns:
            List of observation dictionaries for the pattern
        """
        self._ensure_loaded()
        return [
            obs.to_dict()
            for obs in self._observations
            if obs.pattern_id == pattern_id
        ]

    def get_observation_count(self) -> int:
        """Get total number of observations."""
        self._ensure_loaded()
        return len(self._observations)

    def prune_old_observations(self, max_age_days: int = 90) -> int:
        """
        Remove observations older than threshold.

        Args:
            max_age_days: Maximum age in days

        Returns:
            Number of observations pruned
        """
        self._ensure_loaded()

        cutoff = datetime.now(timezone.utc)
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=max_age_days)
        cutoff_iso = cutoff.isoformat()

        original_count = len(self._observations)
        self._observations = [
            obs for obs in self._observations
            if obs.timestamp >= cutoff_iso
        ]

        pruned = original_count - len(self._observations)
        if pruned > 0:
            self.save()

        return pruned

    def clear(self):
        """Clear all observations (for testing)."""
        self._observations = []
        self._loaded = True
        self.save()


# =============================================================================
# Feature Scaler Manager
# =============================================================================

class ScalerManager:
    """
    Manages feature scaling for consistent context encoding.

    Uses simple min-max scaling to normalize features to [0, 1] range.
    This is simpler than StandardScaler and works well for our one-hot
    and multi-hot encoded features.
    """

    def __init__(self, path: Optional[Path] = None):
        """
        Initialize scaler manager.

        Args:
            path: Custom path for scaler file (defaults to SCALER_PATH)
        """
        self.path = path or SCALER_PATH
        self._min: Optional[list[float]] = None
        self._max: Optional[list[float]] = None
        self._is_fitted = False

    @property
    def is_fitted(self) -> bool:
        """Check if scaler has been fitted."""
        return self._is_fitted

    def fit(self, contexts: list[list[float]]) -> bool:
        """
        Fit scaler to context data.

        Args:
            contexts: List of 23-dimensional context vectors

        Returns:
            True if fitting succeeded
        """
        if not contexts:
            # Handle empty data gracefully
            self._min = [0.0] * 21
            self._max = [1.0] * 21
            self._is_fitted = True
            return True

        n_features = len(contexts[0])
        self._min = [float('inf')] * n_features
        self._max = [float('-inf')] * n_features

        for context in contexts:
            if len(context) != n_features:
                logger.warning(f"Inconsistent context length: expected {n_features}, got {len(context)}")
                continue
            for i, val in enumerate(context):
                self._min[i] = min(self._min[i], val)
                self._max[i] = max(self._max[i], val)

        # Handle constant features (min == max)
        for i in range(n_features):
            if self._min[i] == self._max[i]:
                self._max[i] = self._min[i] + 1.0  # Avoid division by zero

        self._is_fitted = True
        return True

    def transform(self, context: list[float]) -> list[float]:
        """
        Transform a single context vector.

        Args:
            context: 23-dimensional feature vector

        Returns:
            Normalized feature vector

        Raises:
            ValueError: If scaler not fitted or context invalid
        """
        if not self._is_fitted:
            raise ValueError("Scaler must be fitted before transform")

        if len(context) != len(self._min):
            raise ValueError(f"Expected {len(self._min)} features, got {len(context)}")

        result = []
        for i, val in enumerate(context):
            range_val = self._max[i] - self._min[i]
            if range_val == 0:
                result.append(0.0)
            else:
                normalized = (val - self._min[i]) / range_val
                result.append(max(0.0, min(1.0, normalized)))  # Clip to [0, 1]

        return result

    def fit_transform(self, contexts: list[list[float]]) -> list[list[float]]:
        """
        Fit scaler and transform all contexts.

        Args:
            contexts: List of context vectors

        Returns:
            List of normalized context vectors
        """
        self.fit(contexts)
        return [self.transform(c) for c in contexts]

    def save(self) -> bool:
        """Persist scaler state to disk."""
        if not self._is_fitted:
            logger.warning("Cannot save unfitted scaler")
            return False

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "min": self._min,
                "max": self._max,
                "schema_version": SCHEMA_VERSION
            }
            with open(self.path, 'wb') as f:
                pickle.dump(state, f)
            return True
        except Exception as e:
            logger.error(f"Failed to save scaler: {e}")
            return False

    def load(self) -> bool:
        """Load scaler state from disk."""
        if not self.path.exists():
            return False

        try:
            with open(self.path, 'rb') as f:
                state = pickle.load(f)
            self._min = state["min"]
            self._max = state["max"]
            self._is_fitted = True
            return True
        except Exception as e:
            logger.error(f"Failed to load scaler: {e}")
            return False


# =============================================================================
# Schema Migration Utilities
# =============================================================================

def get_schema_version(graph: dict[str, Any]) -> str:
    """Get schema version from a knowledge graph."""
    return graph.get("graph", {}).get("schema_version", "1.0.0")


def migrate_knowledge_graph_v1_to_v2(graph: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate knowledge graph from v1 to v2 schema.

    V2 adds:
    - schema_version field in graph metadata
    - context_observations support (stored separately)

    Args:
        graph: V1 knowledge graph

    Returns:
        V2 knowledge graph (preserves all existing data)
    """
    # Check if already migrated
    current_version = get_schema_version(graph)
    if current_version >= "2.0.0":
        return graph  # Already migrated

    # Create migrated graph
    migrated = {
        "directed": graph.get("directed", True),
        "multigraph": graph.get("multigraph", False),
        "graph": {
            **graph.get("graph", {}),
            "schema_version": "2.0.0",
            "migrated_from": current_version,
            "migrated_at": datetime.now(timezone.utc).isoformat()
        },
        "nodes": graph.get("nodes", []).copy(),
        "links": graph.get("links", []).copy()
    }

    return migrated


def is_migration_needed(graph: dict[str, Any]) -> bool:
    """Check if a knowledge graph needs migration."""
    return get_schema_version(graph) < "2.0.0"
