"""
Tests for Testing & Validation Module

Test categories:
- T5.1.x: Scenario generation
- T5.2.x: A/B comparison
- T5.3.x: Latency benchmarks
- T7.1.x: Regression detection (Phase 7)
- T7.2.x: Confidence filtering (Phase 7)
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from rook.validation import (
    generate_test_scenarios,
    get_category_coverage,
    ABComparison,
    ABComparisonMetrics,
    benchmark_query_latency,
    benchmark_record_latency,
    check_latency_targets,
    LatencyStats,
    CATEGORY_ORDER,
)


# =============================================================================
# T5.1.x: Scenario Generation Tests
# =============================================================================

class TestScenarioGeneration:
    """Tests for synthetic test data generation."""

    def test_generate_scenarios_coverage(self):
        """T5.1.1: Generated scenarios cover all categories."""
        scenarios = generate_test_scenarios(n_scenarios=100, seed=42)

        # Check we got the right number
        assert len(scenarios) == 100

        # Check all required fields present
        for s in scenarios:
            assert "id" in s
            assert "intent" in s
            assert "tool" in s
            assert "params" in s
            assert "expected_category" in s
            assert "expected_outcome" in s

        # Check category coverage
        coverage = get_category_coverage(scenarios)

        # All categories should have at least one scenario
        for category in CATEGORY_ORDER:
            assert coverage[category] >= 1, f"Category {category} has no scenarios"

    def test_generate_scenarios_reproducible(self):
        """Scenarios are reproducible with same seed."""
        scenarios1 = generate_test_scenarios(n_scenarios=50, seed=123)
        scenarios2 = generate_test_scenarios(n_scenarios=50, seed=123)

        # Same seed should produce identical scenarios
        for s1, s2 in zip(scenarios1, scenarios2):
            assert s1["id"] == s2["id"]
            assert s1["intent"] == s2["intent"]
            assert s1["tool"] == s2["tool"]

    def test_generate_scenarios_different_seeds(self):
        """Different seeds produce different scenarios."""
        scenarios1 = generate_test_scenarios(n_scenarios=50, seed=1)
        scenarios2 = generate_test_scenarios(n_scenarios=50, seed=2)

        # Different seeds should produce different scenarios
        intents1 = [s["intent"] for s in scenarios1]
        intents2 = [s["intent"] for s in scenarios2]

        # At least some should be different (not all identical)
        assert intents1 != intents2

    def test_generate_scenarios_category_filter(self):
        """Can filter to specific categories."""
        scenarios = generate_test_scenarios(
            n_scenarios=20,
            categories=["create", "layer"]
        )

        # All scenarios should be in specified categories
        for s in scenarios:
            assert s["expected_category"] in ["create", "layer"]


# =============================================================================
# T5.2.x: A/B Comparison Tests
# =============================================================================

class TestABComparison:
    """Tests for A/B comparison framework."""

    def test_ab_comparison_runs(self):
        """T5.2.1: A/B comparison framework works."""
        # Mock baseline and challenger functions
        def mock_baseline(intent, tool, params):
            return {"patterns": [{"note": "baseline"}], "confidence": 0.7}

        def mock_challenger(intent, tool, params):
            return {"patterns": [{"note": "challenger"}, {"note": "extra"}], "confidence": 0.85}

        comparison = ABComparison(mock_baseline, mock_challenger)

        # Generate some scenarios
        scenarios = generate_test_scenarios(n_scenarios=10, seed=42)

        # Run comparison
        results = comparison.run_scenarios(scenarios)

        # Should have results for all scenarios
        assert len(results) == 10

        # Compute metrics
        metrics = comparison.compute_metrics()

        # Check metrics structure
        assert isinstance(metrics, ABComparisonMetrics)
        assert metrics.n_scenarios == 10
        assert metrics.baseline_avg_confidence == 0.7
        assert metrics.challenger_avg_confidence == 0.85
        assert metrics.baseline_avg_patterns == 1.0
        assert metrics.challenger_avg_patterns == 2.0

        # Challenger should show improvement in confidence
        assert metrics.confidence_improvement_pct > 0

    def test_ab_comparison_empty(self):
        """A/B comparison handles no scenarios."""
        def mock_fn(intent, tool, params):
            return {"patterns": [], "confidence": 0.0}

        comparison = ABComparison(mock_fn, mock_fn)
        metrics = comparison.compute_metrics()

        assert metrics.n_scenarios == 0
        assert metrics.baseline_avg_latency_ms == 0.0

    def test_ab_comparison_clear(self):
        """Can clear and reuse comparison."""
        def mock_fn(intent, tool, params):
            return {"patterns": [], "confidence": 0.5}

        comparison = ABComparison(mock_fn, mock_fn)
        scenarios = generate_test_scenarios(n_scenarios=5)

        comparison.run_scenarios(scenarios)
        assert len(comparison.results) == 5

        comparison.clear_results()
        assert len(comparison.results) == 0


# =============================================================================
# T5.3.x: Latency Benchmark Tests
# =============================================================================

class TestLatencyBenchmarks:
    """Tests for performance benchmarks."""

    def test_query_latency_acceptable(self):
        """T5.3.1: Query latency p50 < 10ms, p99 < 50ms."""
        # Mock a fast query function
        call_count = [0]

        def fast_query(intent, tool, params):
            call_count[0] += 1
            return {"patterns": [], "confidence": 0.5}

        scenarios = generate_test_scenarios(n_scenarios=20, seed=42)
        stats = benchmark_query_latency(fast_query, scenarios, n_iterations=1)

        # Check stats structure
        assert isinstance(stats, LatencyStats)
        assert stats.n_samples == 20

        # Check latency targets (should easily pass for mock)
        passes, message = check_latency_targets(stats, p50_target_ms=10.0, p99_target_ms=50.0)
        assert passes, message

        # Verify function was called
        assert call_count[0] == 20

    def test_record_latency_acceptable(self):
        """T5.3.2: Record latency p50 < 20ms, p99 < 100ms."""
        # Mock a fast record function
        def fast_record(intent, action, outcome):
            return {"success": True}

        scenarios = generate_test_scenarios(n_scenarios=20, seed=42)
        stats = benchmark_record_latency(fast_record, scenarios, n_iterations=1)

        # Check stats structure
        assert isinstance(stats, LatencyStats)
        assert stats.n_samples == 20

        # Check latency targets
        passes, message = check_latency_targets(stats, p50_target_ms=20.0, p99_target_ms=100.0)
        assert passes, message

    def test_latency_stats_structure(self):
        """Latency stats have all expected fields."""
        def mock_fn(intent, tool, params):
            return {}

        scenarios = generate_test_scenarios(n_scenarios=10)
        stats = benchmark_query_latency(mock_fn, scenarios)

        assert hasattr(stats, "n_samples")
        assert hasattr(stats, "p50_ms")
        assert hasattr(stats, "p90_ms")
        assert hasattr(stats, "p99_ms")
        assert hasattr(stats, "mean_ms")
        assert hasattr(stats, "min_ms")
        assert hasattr(stats, "max_ms")

        # All values should be non-negative
        assert stats.p50_ms >= 0
        assert stats.p90_ms >= 0
        assert stats.p99_ms >= 0
        assert stats.mean_ms >= 0

    def test_check_latency_targets_failure(self):
        """check_latency_targets correctly reports failures."""
        # Create stats that fail targets
        stats = LatencyStats(
            n_samples=100,
            p50_ms=15.0,  # > 10ms target
            p90_ms=40.0,
            p99_ms=60.0,  # > 50ms target
            mean_ms=20.0,
            min_ms=5.0,
            max_ms=100.0
        )

        passes, message = check_latency_targets(stats, p50_target_ms=10.0, p99_target_ms=50.0)

        assert passes is False
        assert "p50=15.0ms > 10.0ms" in message
        assert "p99=60.0ms > 50.0ms" in message

    def test_benchmark_empty_scenarios(self):
        """Benchmarks handle empty scenarios."""
        def mock_fn(intent, tool, params):
            return {}

        stats = benchmark_query_latency(mock_fn, [], n_iterations=1)

        assert stats.n_samples == 0
        assert stats.p50_ms == 0
        assert stats.mean_ms == 0


# =============================================================================
# T7.1.x: Regression Detection Tests (Phase 7)
# =============================================================================

class TestRegressionDetection:
    """Tests for pattern regression detection."""

    @pytest.fixture
    def store_with_patterns(self, tmp_path):
        """Create a store with patterns that have usage history."""
        from rook.learning.pattern_store import PatternStore, PATTERNS_DIR, INDEX_PATH
        from rook.learning.pattern_memory import PatternNote

        # Use temp directory
        import shutil
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        # Patch the paths
        original_patterns_dir = PATTERNS_DIR
        original_index_path = INDEX_PATH

        import rook.learning.pattern_store as ps_module
        ps_module.PATTERNS_DIR = patterns_dir
        ps_module.INDEX_PATH = tmp_path / "pattern_index.json"

        store = PatternStore(auto_save=True, enable_evolution=False, verify_on_search=False)

        # Create a pattern that was good but is now failing
        regressed_pattern = PatternNote(
            pattern_id="regressed1",
            name="Regressed Pattern",
            solution_brief="A pattern that used to work",
            times_used=10,
            times_succeeded=8,  # 80% overall
            citations=[
                # Old successes
                {"session_id": "old1", "outcome": "success", "timestamp": "2026-01-01T00:00:00Z"},
                {"session_id": "old2", "outcome": "success", "timestamp": "2026-01-02T00:00:00Z"},
                {"session_id": "old3", "outcome": "success", "timestamp": "2026-01-03T00:00:00Z"},
                {"session_id": "old4", "outcome": "success", "timestamp": "2026-01-04T00:00:00Z"},
                {"session_id": "old5", "outcome": "success", "timestamp": "2026-01-05T00:00:00Z"},
                # Recent failures
                {"session_id": "new1", "outcome": "failure", "timestamp": "2026-01-28T00:00:00Z"},
                {"session_id": "new2", "outcome": "failure", "timestamp": "2026-01-29T00:00:00Z"},
                {"session_id": "new3", "outcome": "failure", "timestamp": "2026-01-30T00:00:00Z"},
                {"session_id": "new4", "outcome": "failure", "timestamp": "2026-01-31T00:00:00Z"},
                {"session_id": "new5", "outcome": "success", "timestamp": "2026-01-31T01:00:00Z"},
            ]
        )
        store.add(regressed_pattern, skip_evolution=True)

        # Create a pattern that's still working well
        good_pattern = PatternNote(
            pattern_id="good1",
            name="Good Pattern",
            solution_brief="A pattern that still works",
            times_used=10,
            times_succeeded=9,  # 90% overall
            citations=[
                {"session_id": "s1", "outcome": "success", "timestamp": "2026-01-25T00:00:00Z"},
                {"session_id": "s2", "outcome": "success", "timestamp": "2026-01-26T00:00:00Z"},
                {"session_id": "s3", "outcome": "success", "timestamp": "2026-01-27T00:00:00Z"},
                {"session_id": "s4", "outcome": "success", "timestamp": "2026-01-28T00:00:00Z"},
                {"session_id": "s5", "outcome": "success", "timestamp": "2026-01-29T00:00:00Z"},
            ]
        )
        store.add(good_pattern, skip_evolution=True)

        yield store

        # Restore paths
        ps_module.PATTERNS_DIR = original_patterns_dir
        ps_module.INDEX_PATH = original_index_path

    def test_detect_regressions_finds_degraded(self, store_with_patterns):
        """T7.1.1: Regression detection identifies degraded patterns."""
        regressions = store_with_patterns.detect_regressions()

        # Should find the regressed pattern
        assert len(regressions) == 1
        assert regressions[0]["pattern_id"] == "regressed1"
        # Historical rate is from the 5 old citations (all success) = 100%
        assert regressions[0]["historical_success_rate"] == 1.0
        # Recent rate is 1/5 = 20%
        assert regressions[0]["recent_success_rate"] == 0.2

    def test_detect_regressions_ignores_good(self, store_with_patterns):
        """T7.1.2: Regression detection ignores still-working patterns."""
        regressions = store_with_patterns.detect_regressions()

        # Should NOT include the good pattern
        pattern_ids = [r["pattern_id"] for r in regressions]
        assert "good1" not in pattern_ids

    def test_detect_regressions_recommendation(self, store_with_patterns):
        """T7.1.3: Regression includes actionable recommendation."""
        regressions = store_with_patterns.detect_regressions()

        assert len(regressions) == 1
        assert "recommendation" in regressions[0]
        assert len(regressions[0]["recommendation"]) > 0

    def test_detect_regressions_long_running(self, tmp_path):
        """T7.1.5: Detects regression even when overall rate has degraded.

        This is the bug fix: Previously, if a pattern's overall rate dropped
        below the threshold due to accumulated failures, it would NOT be
        detected. The sliding window approach fixes this by comparing
        historical (older) vs recent windows.
        """
        from rook.learning.pattern_store import PatternStore, PATTERNS_DIR, INDEX_PATH
        from rook.learning.pattern_memory import PatternNote
        import rook.learning.pattern_store as ps_module

        # Setup temp directory
        patterns_dir = tmp_path / "patterns_long"
        patterns_dir.mkdir()
        original_patterns_dir = PATTERNS_DIR
        original_index_path = INDEX_PATH
        ps_module.PATTERNS_DIR = patterns_dir
        ps_module.INDEX_PATH = tmp_path / "pattern_index_long.json"

        store = PatternStore(auto_save=True, enable_evolution=False, verify_on_search=False)

        # Create pattern that was 100% but has degraded to 67% overall
        # Old behavior: 67% < 70% threshold → NOT detected (BUG)
        # New behavior: historical 100% >= 70%, recent 0% < 50% → DETECTED (FIX)
        long_running_regression = PatternNote(
            pattern_id="longregress1",
            name="Long Running Regression",
            solution_brief="Pattern that regressed a while ago",
            times_used=15,
            times_succeeded=10,  # 67% overall (below old threshold!)
            citations=[
                # Historical successes (10 total)
                {"session_id": "h1", "outcome": "success", "timestamp": "2026-01-01T00:00:00Z"},
                {"session_id": "h2", "outcome": "success", "timestamp": "2026-01-02T00:00:00Z"},
                {"session_id": "h3", "outcome": "success", "timestamp": "2026-01-03T00:00:00Z"},
                {"session_id": "h4", "outcome": "success", "timestamp": "2026-01-04T00:00:00Z"},
                {"session_id": "h5", "outcome": "success", "timestamp": "2026-01-05T00:00:00Z"},
                {"session_id": "h6", "outcome": "success", "timestamp": "2026-01-06T00:00:00Z"},
                {"session_id": "h7", "outcome": "success", "timestamp": "2026-01-07T00:00:00Z"},
                {"session_id": "h8", "outcome": "success", "timestamp": "2026-01-08T00:00:00Z"},
                {"session_id": "h9", "outcome": "success", "timestamp": "2026-01-09T00:00:00Z"},
                {"session_id": "h10", "outcome": "success", "timestamp": "2026-01-10T00:00:00Z"},
                # Recent failures (5 total) - all failures!
                {"session_id": "r1", "outcome": "failure", "timestamp": "2026-01-27T00:00:00Z"},
                {"session_id": "r2", "outcome": "failure", "timestamp": "2026-01-28T00:00:00Z"},
                {"session_id": "r3", "outcome": "failure", "timestamp": "2026-01-29T00:00:00Z"},
                {"session_id": "r4", "outcome": "failure", "timestamp": "2026-01-30T00:00:00Z"},
                {"session_id": "r5", "outcome": "failure", "timestamp": "2026-01-31T00:00:00Z"},
            ]
        )
        store.add(long_running_regression, skip_evolution=True)

        try:
            regressions = store.detect_regressions()

            # The fix: Should now detect this regression
            assert len(regressions) == 1
            assert regressions[0]["pattern_id"] == "longregress1"
            # Historical window (citations 6-15, the 10 old ones): 100% success
            assert regressions[0]["historical_success_rate"] == 1.0
            # Recent window (citations 1-5, the 5 new ones): 0% success
            assert regressions[0]["recent_success_rate"] == 0.0
            # Includes the historical window size
            assert regressions[0]["historical_uses"] == 10
        finally:
            ps_module.PATTERNS_DIR = original_patterns_dir
            ps_module.INDEX_PATH = original_index_path

    def test_get_confidence_stats(self, store_with_patterns):
        """T7.1.4: Confidence stats breakdown works."""
        stats = store_with_patterns.get_confidence_stats()

        assert "total" in stats
        assert stats["total"] == 2
        assert "high_confidence" in stats
        assert "medium_confidence" in stats
        assert "low_confidence" in stats
        assert "untested" in stats


# =============================================================================
# T7.2.x: Confidence Filtering Tests (Phase 7)
# =============================================================================

class TestConfidenceFiltering:
    """Tests for confidence-based pattern filtering."""

    @pytest.fixture
    def store_with_varied_confidence(self, tmp_path):
        """Create store with patterns at different confidence levels."""
        from rook.learning.pattern_store import PatternStore, PATTERNS_DIR, INDEX_PATH
        from rook.learning.pattern_memory import PatternNote

        # Use temp directory
        patterns_dir = tmp_path / "patterns"
        patterns_dir.mkdir()

        import rook.learning.pattern_store as ps_module
        ps_module.PATTERNS_DIR = patterns_dir
        ps_module.INDEX_PATH = tmp_path / "pattern_index.json"

        store = PatternStore(auto_save=True, enable_evolution=False, verify_on_search=False)

        # High confidence pattern (90%)
        high = PatternNote(
            pattern_id="high1",
            name="High Confidence",
            solution_brief="Very reliable",
            trigger_intents=["test intent"],
            times_used=10,
            times_succeeded=9,
        )
        store.add(high, skip_evolution=True)

        # Medium confidence pattern (60%)
        medium = PatternNote(
            pattern_id="medium1",
            name="Medium Confidence",
            solution_brief="Somewhat reliable",
            trigger_intents=["test intent"],
            times_used=10,
            times_succeeded=6,
        )
        store.add(medium, skip_evolution=True)

        # Low confidence pattern (30%)
        low = PatternNote(
            pattern_id="low1",
            name="Low Confidence",
            solution_brief="Not very reliable",
            trigger_intents=["test intent"],
            times_used=10,
            times_succeeded=3,
        )
        store.add(low, skip_evolution=True)

        # Untested pattern
        untested = PatternNote(
            pattern_id="untested1",
            name="Untested",
            solution_brief="Never used",
            trigger_intents=["test intent"],
            times_used=0,
            times_succeeded=0,
        )
        store.add(untested, skip_evolution=True)

        yield store

        # Restore paths
        from rook.learning.pattern_store import PATTERNS_DIR as orig_pd, INDEX_PATH as orig_ip
        ps_module.PATTERNS_DIR = orig_pd
        ps_module.INDEX_PATH = orig_ip

    def test_search_no_filter_returns_all(self, store_with_varied_confidence):
        """T7.2.1: Search without confidence filter returns all matches."""
        results = store_with_varied_confidence.search(
            intent="test",
            confidence_min=0.0,
            limit=10,
            verify=False
        )

        # Should return all 4 patterns
        assert len(results) == 4

    def test_search_high_confidence_filter(self, store_with_varied_confidence):
        """T7.2.2: High confidence filter only returns trusted patterns."""
        results = store_with_varied_confidence.search(
            intent="test",
            confidence_min=0.8,
            limit=10,
            verify=False
        )

        # Should only return the high confidence pattern
        assert len(results) == 1
        assert results[0].pattern_id == "high1"

    def test_search_medium_confidence_filter(self, store_with_varied_confidence):
        """T7.2.3: Medium confidence filter excludes low confidence."""
        results = store_with_varied_confidence.search(
            intent="test",
            confidence_min=0.5,
            limit=10,
            verify=False
        )

        # Should return high and medium
        pattern_ids = [p.pattern_id for p in results]
        assert "high1" in pattern_ids
        assert "medium1" in pattern_ids
        assert "low1" not in pattern_ids

    def test_search_includes_untested_at_low_threshold(self, store_with_varied_confidence):
        """T7.2.4: Untested patterns included when threshold < 0.5."""
        results = store_with_varied_confidence.search(
            intent="test",
            confidence_min=0.3,
            limit=10,
            verify=False
        )

        # Should include untested (has 0.5 neutral prior)
        pattern_ids = [p.pattern_id for p in results]
        assert "untested1" in pattern_ids

    def test_search_excludes_untested_at_high_threshold(self, store_with_varied_confidence):
        """T7.2.5: Untested patterns excluded when threshold >= 0.5."""
        results = store_with_varied_confidence.search(
            intent="test",
            confidence_min=0.6,
            limit=10,
            verify=False
        )

        # Should NOT include untested
        pattern_ids = [p.pattern_id for p in results]
        assert "untested1" not in pattern_ids
