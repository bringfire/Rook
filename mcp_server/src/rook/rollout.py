"""
Phase 6: Rollout & Monitoring Module

Provides tools for controlled rollout of contextual MAB:
- Feature flags for gradual enablement
- Metrics collection for monitoring
- Rollback mechanism for quick reversion
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from .runtime_paths import resolve_writable_knowledge_path

logger = logging.getLogger("rook.rollout")

# Metrics storage path
KNOWLEDGE_DIR = resolve_writable_knowledge_path()
METRICS_PATH = resolve_writable_knowledge_path("metrics.json")


# =============================================================================
# F6.1: Feature Flags
# =============================================================================

@dataclass
class FeatureFlags:
    """
    Feature flag management for contextual MAB rollout.

    Flags can be modified at runtime to control behavior:
    - USE_CONTEXTUAL_MAB: Master switch for contextual features
    - CONTEXTUAL_MAB_PERCENTAGE: Gradual rollout (0-100)
    - LOG_CONTEXT_FEATURES: Enable detailed logging
    - FALLBACK_ON_ERROR: Use static weights on errors
    """

    USE_CONTEXTUAL_MAB: bool = False
    CONTEXTUAL_MAB_PERCENTAGE: float = 0.0  # 0-100 for gradual rollout
    LOG_CONTEXT_FEATURES: bool = True
    FALLBACK_ON_ERROR: bool = True

    # Persistence path
    _config_path: Path = field(default=KNOWLEDGE_DIR / "feature_flags.json", repr=False)

    def should_use_contextual(self) -> bool:
        """
        Determine if contextual MAB should be used for this request.

        Uses percentage-based rollout for gradual enablement.
        """
        if not self.USE_CONTEXTUAL_MAB:
            return False

        if self.CONTEXTUAL_MAB_PERCENTAGE >= 100.0:
            return True

        if self.CONTEXTUAL_MAB_PERCENTAGE <= 0.0:
            return False

        # Random percentage check for gradual rollout
        return random.random() * 100 < self.CONTEXTUAL_MAB_PERCENTAGE

    def enable_contextual(self, percentage: float = 100.0):
        """Enable contextual MAB at specified percentage."""
        self.USE_CONTEXTUAL_MAB = True
        self.CONTEXTUAL_MAB_PERCENTAGE = max(0.0, min(100.0, percentage))
        logger.info(f"Enabled contextual MAB at {self.CONTEXTUAL_MAB_PERCENTAGE}%")

    def disable_contextual(self):
        """Disable contextual MAB completely."""
        self.USE_CONTEXTUAL_MAB = False
        self.CONTEXTUAL_MAB_PERCENTAGE = 0.0
        logger.info("Disabled contextual MAB")

    def save(self) -> bool:
        """Persist flags to disk."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            config = {
                "USE_CONTEXTUAL_MAB": self.USE_CONTEXTUAL_MAB,
                "CONTEXTUAL_MAB_PERCENTAGE": self.CONTEXTUAL_MAB_PERCENTAGE,
                "LOG_CONTEXT_FEATURES": self.LOG_CONTEXT_FEATURES,
                "FALLBACK_ON_ERROR": self.FALLBACK_ON_ERROR,
                "updated_at": datetime.now().isoformat()
            }
            self._config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to save feature flags: {e}")
            return False

    def load(self) -> bool:
        """Load flags from disk."""
        try:
            if not self._config_path.exists():
                return False

            config = json.loads(self._config_path.read_text(encoding="utf-8"))
            self.USE_CONTEXTUAL_MAB = config.get("USE_CONTEXTUAL_MAB", False)
            self.CONTEXTUAL_MAB_PERCENTAGE = config.get("CONTEXTUAL_MAB_PERCENTAGE", 0.0)
            self.LOG_CONTEXT_FEATURES = config.get("LOG_CONTEXT_FEATURES", True)
            self.FALLBACK_ON_ERROR = config.get("FALLBACK_ON_ERROR", True)
            return True
        except Exception as e:
            logger.error(f"Failed to load feature flags: {e}")
            return False


# Global feature flags instance
_feature_flags: Optional[FeatureFlags] = None


def get_feature_flags() -> FeatureFlags:
    """Get or initialize global feature flags."""
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags()
        _feature_flags.load()  # Load from disk if exists
    return _feature_flags


def reset_feature_flags():
    """Reset feature flags to defaults (for testing)."""
    global _feature_flags
    _feature_flags = None


# =============================================================================
# F6.2: Metrics Collection
# =============================================================================

@dataclass
class QueryMetric:
    """Single query metric record."""
    timestamp: str
    latency_ms: float
    used_context: bool
    patterns_returned: int
    confidence: float


@dataclass
class OutcomeMetric:
    """Single outcome metric record."""
    timestamp: str
    pattern_id: str
    outcome: str  # "success" or "failure"
    was_top_recommendation: bool


class MetricsCollector:
    """
    Collect and report metrics for monitoring.

    Tracks:
    - Query latency and success rates
    - Contextual vs context-free usage
    - Recommendation accuracy
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = path or METRICS_PATH
        self.query_metrics: list[dict] = []
        self.outcome_metrics: list[dict] = []
        self._load()

    def _load(self):
        """Load existing metrics from disk."""
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.query_metrics = data.get("query_metrics", [])
                self.outcome_metrics = data.get("outcome_metrics", [])
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")

    def _save(self):
        """Persist metrics to disk."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "query_metrics": self.query_metrics[-1000:],  # Keep last 1000
                "outcome_metrics": self.outcome_metrics[-1000:],
                "updated_at": datetime.now().isoformat()
            }
            self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save metrics: {e}")

    def record_query(
        self,
        latency_ms: float,
        used_context: bool,
        patterns_returned: int,
        confidence: float = 0.0
    ):
        """Record query metrics."""
        metric = {
            "timestamp": datetime.now().isoformat(),
            "latency_ms": round(latency_ms, 3),
            "used_context": used_context,
            "patterns_returned": patterns_returned,
            "confidence": round(confidence, 3)
        }
        self.query_metrics.append(metric)
        self._save()

    def record_outcome(
        self,
        pattern_id: str,
        outcome: str,
        was_top_recommendation: bool
    ):
        """Record recommendation outcome."""
        metric = {
            "timestamp": datetime.now().isoformat(),
            "pattern_id": pattern_id,
            "outcome": outcome,
            "was_top_recommendation": was_top_recommendation
        }
        self.outcome_metrics.append(metric)
        self._save()

    def get_summary(self, time_window_hours: int = 24) -> dict[str, Any]:
        """
        Get metrics summary for time window.

        Returns:
            Summary with query stats, outcome stats, and recommendations
        """
        cutoff = datetime.now() - timedelta(hours=time_window_hours)
        cutoff_str = cutoff.isoformat()

        # Filter to time window
        recent_queries = [
            m for m in self.query_metrics
            if m.get("timestamp", "") >= cutoff_str
        ]
        recent_outcomes = [
            m for m in self.outcome_metrics
            if m.get("timestamp", "") >= cutoff_str
        ]

        # Query stats
        total_queries = len(recent_queries)
        contextual_queries = sum(1 for m in recent_queries if m.get("used_context"))
        avg_latency = (
            sum(m.get("latency_ms", 0) for m in recent_queries) / total_queries
            if total_queries > 0 else 0.0
        )
        avg_confidence = (
            sum(m.get("confidence", 0) for m in recent_queries) / total_queries
            if total_queries > 0 else 0.0
        )

        # Outcome stats
        total_outcomes = len(recent_outcomes)
        successes = sum(1 for m in recent_outcomes if m.get("outcome") == "success")
        top_rec_successes = sum(
            1 for m in recent_outcomes
            if m.get("outcome") == "success" and m.get("was_top_recommendation")
        )
        success_rate = successes / total_outcomes if total_outcomes > 0 else 0.0
        top_rec_accuracy = top_rec_successes / successes if successes > 0 else 0.0

        return {
            "time_window_hours": time_window_hours,
            "queries": {
                "total": total_queries,
                "contextual": contextual_queries,
                "contextual_pct": round(contextual_queries / total_queries * 100, 1) if total_queries > 0 else 0.0,
                "avg_latency_ms": round(avg_latency, 2),
                "avg_confidence": round(avg_confidence, 3)
            },
            "outcomes": {
                "total": total_outcomes,
                "successes": successes,
                "success_rate": round(success_rate, 3),
                "top_rec_accuracy": round(top_rec_accuracy, 3)
            },
            "generated_at": datetime.now().isoformat()
        }

    def clear(self):
        """Clear all metrics (for testing)."""
        self.query_metrics = []
        self.outcome_metrics = []
        if self.path.exists():
            self.path.unlink()


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get or initialize global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics_collector():
    """Reset metrics collector (for testing)."""
    global _metrics_collector
    _metrics_collector = None


# =============================================================================
# F6.3: Rollback Mechanism
# =============================================================================

def rollback_to_context_free():
    """
    Disable contextual MAB and revert to baseline.

    This is the emergency rollback function to use if issues are detected
    with the contextual MAB system.
    """
    flags = get_feature_flags()
    flags.disable_contextual()
    flags.save()

    logger.warning("ROLLBACK: Reverted to context-free MAB")

    return {
        "success": True,
        "message": "Rolled back to context-free MAB",
        "timestamp": datetime.now().isoformat()
    }


def gradual_rollout(target_percentage: float, step_size: float = 10.0) -> dict:
    """
    Perform gradual rollout to target percentage.

    Args:
        target_percentage: Target rollout percentage (0-100)
        step_size: Increment size for gradual rollout

    Returns:
        Status of the rollout
    """
    flags = get_feature_flags()
    current = flags.CONTEXTUAL_MAB_PERCENTAGE

    if target_percentage > current:
        # Increasing rollout
        new_pct = min(target_percentage, current + step_size)
    else:
        # Decreasing rollout
        new_pct = max(target_percentage, current - step_size)

    flags.enable_contextual(new_pct)
    flags.save()

    return {
        "success": True,
        "previous_percentage": current,
        "new_percentage": new_pct,
        "target_percentage": target_percentage,
        "complete": new_pct == target_percentage,
        "timestamp": datetime.now().isoformat()
    }


def get_rollout_status() -> dict:
    """Get current rollout status."""
    flags = get_feature_flags()
    metrics = get_metrics_collector()
    summary = metrics.get_summary(time_window_hours=1)

    return {
        "contextual_enabled": flags.USE_CONTEXTUAL_MAB,
        "rollout_percentage": flags.CONTEXTUAL_MAB_PERCENTAGE,
        "fallback_on_error": flags.FALLBACK_ON_ERROR,
        "recent_queries": summary["queries"]["total"],
        "recent_contextual_pct": summary["queries"]["contextual_pct"],
        "recent_success_rate": summary["outcomes"]["success_rate"],
        "timestamp": datetime.now().isoformat()
    }
