"""
Tests for Phase 6: Rollout & Monitoring Module

Test categories:
- T6.1.x: Feature flags (1 test)
- T6.2.x: Metrics recording (1 test)
- T6.3.x: Rollback (1 test - implicit in feature flag disable)
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from rook.rollout import (
    FeatureFlags,
    MetricsCollector,
    get_feature_flags,
    get_metrics_collector,
    reset_feature_flags,
    reset_metrics_collector,
    rollback_to_context_free,
    gradual_rollout,
    get_rollout_status,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir(tmp_path):
    """Create temporary directory for test files."""
    return tmp_path


@pytest.fixture
def clean_flags():
    """Reset feature flags before and after test."""
    reset_feature_flags()
    yield
    reset_feature_flags()


@pytest.fixture
def clean_metrics():
    """Reset metrics collector before and after test."""
    reset_metrics_collector()
    yield
    reset_metrics_collector()


# =============================================================================
# T6.1.x: Feature Flag Tests
# =============================================================================

class TestFeatureFlags:
    """Tests for feature flag system."""

    def test_feature_flag_disables_contextual(self, temp_dir, clean_flags):
        """T6.1.1: Feature flag disables contextual MAB."""
        flags = FeatureFlags(_config_path=temp_dir / "flags.json")

        # Default should be disabled
        assert flags.USE_CONTEXTUAL_MAB is False
        assert flags.should_use_contextual() is False

        # Enable at 100%
        flags.enable_contextual(100.0)
        assert flags.USE_CONTEXTUAL_MAB is True
        assert flags.CONTEXTUAL_MAB_PERCENTAGE == 100.0
        assert flags.should_use_contextual() is True

        # Disable
        flags.disable_contextual()
        assert flags.USE_CONTEXTUAL_MAB is False
        assert flags.CONTEXTUAL_MAB_PERCENTAGE == 0.0
        assert flags.should_use_contextual() is False

    def test_feature_flag_persistence(self, temp_dir):
        """Feature flags persist to disk."""
        config_path = temp_dir / "flags.json"

        # Create and save flags
        flags1 = FeatureFlags(_config_path=config_path)
        flags1.enable_contextual(75.0)
        flags1.LOG_CONTEXT_FEATURES = False
        assert flags1.save() is True

        # Load in new instance
        flags2 = FeatureFlags(_config_path=config_path)
        assert flags2.load() is True
        assert flags2.USE_CONTEXTUAL_MAB is True
        assert flags2.CONTEXTUAL_MAB_PERCENTAGE == 75.0
        assert flags2.LOG_CONTEXT_FEATURES is False

    def test_feature_flag_percentage_rollout(self, temp_dir):
        """Percentage-based rollout works correctly."""
        flags = FeatureFlags(_config_path=temp_dir / "flags.json")

        # 0% should always return False
        flags.enable_contextual(0.0)
        results = [flags.should_use_contextual() for _ in range(100)]
        assert all(r is False for r in results)

        # 100% should always return True
        flags.enable_contextual(100.0)
        results = [flags.should_use_contextual() for _ in range(100)]
        assert all(r is True for r in results)

        # 50% should return mix (statistically)
        flags.enable_contextual(50.0)
        results = [flags.should_use_contextual() for _ in range(1000)]
        true_count = sum(results)
        # Should be roughly 50% with some variance
        assert 300 < true_count < 700

    def test_feature_flag_bounds(self, temp_dir):
        """Percentage is bounded to 0-100."""
        flags = FeatureFlags(_config_path=temp_dir / "flags.json")

        flags.enable_contextual(150.0)
        assert flags.CONTEXTUAL_MAB_PERCENTAGE == 100.0

        flags.enable_contextual(-50.0)
        assert flags.CONTEXTUAL_MAB_PERCENTAGE == 0.0


# =============================================================================
# T6.2.x: Metrics Recording Tests
# =============================================================================

class TestMetricsRecording:
    """Tests for metrics collection."""

    def test_metrics_recorded(self, temp_dir, clean_metrics):
        """T6.2.1: Metrics recorded for queries."""
        metrics = MetricsCollector(path=temp_dir / "metrics.json")

        # Record some queries
        metrics.record_query(
            latency_ms=5.5,
            used_context=True,
            patterns_returned=3,
            confidence=0.85
        )
        metrics.record_query(
            latency_ms=3.2,
            used_context=False,
            patterns_returned=2,
            confidence=0.70
        )

        # Record outcomes
        metrics.record_outcome(
            pattern_id="pattern:test1",
            outcome="success",
            was_top_recommendation=True
        )
        metrics.record_outcome(
            pattern_id="pattern:test2",
            outcome="failure",
            was_top_recommendation=False
        )

        # Get summary
        summary = metrics.get_summary(time_window_hours=1)

        assert summary["queries"]["total"] == 2
        assert summary["queries"]["contextual"] == 1
        assert summary["queries"]["contextual_pct"] == 50.0
        assert summary["outcomes"]["total"] == 2
        assert summary["outcomes"]["successes"] == 1
        assert summary["outcomes"]["success_rate"] == 0.5

    def test_metrics_persistence(self, temp_dir):
        """Metrics persist to disk."""
        metrics_path = temp_dir / "metrics.json"

        # Create and record
        metrics1 = MetricsCollector(path=metrics_path)
        metrics1.record_query(latency_ms=10.0, used_context=True, patterns_returned=1)

        # Load in new instance
        metrics2 = MetricsCollector(path=metrics_path)
        assert len(metrics2.query_metrics) == 1
        assert metrics2.query_metrics[0]["latency_ms"] == 10.0

    def test_metrics_clear(self, temp_dir):
        """Can clear metrics."""
        metrics = MetricsCollector(path=temp_dir / "metrics.json")

        metrics.record_query(latency_ms=5.0, used_context=True, patterns_returned=1)
        assert len(metrics.query_metrics) == 1

        metrics.clear()
        assert len(metrics.query_metrics) == 0
        assert len(metrics.outcome_metrics) == 0

    def test_metrics_summary_empty(self, temp_dir):
        """Summary works with no data."""
        metrics = MetricsCollector(path=temp_dir / "metrics.json")
        summary = metrics.get_summary()

        assert summary["queries"]["total"] == 0
        assert summary["queries"]["avg_latency_ms"] == 0
        assert summary["outcomes"]["total"] == 0
        assert summary["outcomes"]["success_rate"] == 0


# =============================================================================
# T6.3.x: Rollback Tests
# =============================================================================

class TestRollback:
    """Tests for rollback mechanism."""

    def test_rollback_disables_contextual(self, temp_dir, clean_flags):
        """Rollback disables contextual MAB."""
        # Patch the global flags to use temp path
        flags = FeatureFlags(_config_path=temp_dir / "flags.json")
        flags.enable_contextual(100.0)
        flags.save()

        with patch('rook.rollout._feature_flags', flags):
            result = rollback_to_context_free()

        assert result["success"] is True
        assert "Rolled back" in result["message"]
        assert flags.USE_CONTEXTUAL_MAB is False
        assert flags.CONTEXTUAL_MAB_PERCENTAGE == 0.0

    def test_gradual_rollout(self, temp_dir, clean_flags):
        """Gradual rollout increases percentage."""
        flags = FeatureFlags(_config_path=temp_dir / "flags.json")

        with patch('rook.rollout._feature_flags', flags):
            # Start at 0, rollout to 30 in steps of 10
            result = gradual_rollout(target_percentage=30.0, step_size=10.0)

        assert result["success"] is True
        assert result["previous_percentage"] == 0.0
        assert result["new_percentage"] == 10.0
        assert result["complete"] is False

    def test_get_rollout_status(self, temp_dir, clean_flags, clean_metrics):
        """Can get current rollout status."""
        flags = FeatureFlags(_config_path=temp_dir / "flags.json")
        flags.enable_contextual(50.0)

        metrics = MetricsCollector(path=temp_dir / "metrics.json")

        with patch('rook.rollout._feature_flags', flags), \
             patch('rook.rollout._metrics_collector', metrics):
            status = get_rollout_status()

        assert status["contextual_enabled"] is True
        assert status["rollout_percentage"] == 50.0
        assert "timestamp" in status


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for rollout system."""

    def test_full_rollout_cycle(self, temp_dir, clean_flags, clean_metrics):
        """Full rollout cycle works end-to-end."""
        flags = FeatureFlags(_config_path=temp_dir / "flags.json")
        metrics = MetricsCollector(path=temp_dir / "metrics.json")

        with patch('rook.rollout._feature_flags', flags), \
             patch('rook.rollout._metrics_collector', metrics):

            # Start disabled
            assert flags.should_use_contextual() is False

            # Gradual rollout to 100%
            while flags.CONTEXTUAL_MAB_PERCENTAGE < 100.0:
                gradual_rollout(100.0, step_size=25.0)

            assert flags.CONTEXTUAL_MAB_PERCENTAGE == 100.0

            # Record some activity
            metrics.record_query(latency_ms=5.0, used_context=True, patterns_returned=2)
            metrics.record_outcome("pattern:test", "success", True)

            # Get status
            status = get_rollout_status()
            assert status["rollout_percentage"] == 100.0
            assert status["recent_queries"] == 1

            # Rollback
            rollback_to_context_free()
            assert flags.should_use_contextual() is False
