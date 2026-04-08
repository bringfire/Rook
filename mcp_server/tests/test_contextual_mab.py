"""
Tests for Contextual MAB Integration (Phase 3 of Contextual MAB Migration)

Test IDs correspond to mab_migration_tests.json:
- T3.1.x: MAB initialization tests
- T3.2.x: Training tests
- T3.3.x: Prediction tests
- T3.4.x: Arm management tests
- T3.5.x: Warm start tests
- T3.6.x: Fallback tests
"""

import pytest
import tempfile
from pathlib import Path

from rook.contextual_mab import (
    MABConfig,
    ContextualMAB,
    warm_start_mab,
    get_pattern_ranking,
    is_mabwiser_available,
)
from rook.context_storage import ContextHistory, ScalerManager


# Skip all tests if MABWiser is not installed
pytestmark = pytest.mark.skipif(
    not is_mabwiser_available(),
    reason="MABWiser not installed"
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_context():
    """Create a sample 21-dimensional context vector."""
    return [
        1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # create category
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0,  # brep geometry
        0.3, 0.0, 0.0  # param_count, selection_dep, destructive
    ]


@pytest.fixture
def sample_contexts():
    """Create multiple sample context vectors."""
    return [
        # Create brep
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.3, 0.0, 0.0],
        # Layer operation
        [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0],
        # Transform brep
        [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.5, 1.0, 1.0],
        # Boolean
        [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.4, 1.0, 1.0],
    ]


@pytest.fixture
def sample_patterns():
    """Create sample pattern list."""
    return ["pattern:box", "pattern:sphere", "pattern:layer_nested"]


@pytest.fixture
def temp_mab_path(tmp_path):
    """Create a temporary path for MAB storage."""
    return tmp_path / "test_mab.pkl"


@pytest.fixture
def temp_history(tmp_path, sample_contexts):
    """Create a populated context history for warm start testing."""
    history = ContextHistory(path=tmp_path / "test_history.json")

    patterns = ["pattern:box", "pattern:sphere", "pattern:layer_nested"]

    # Add 15 observations (enough for warm start)
    for i in range(15):
        ctx_idx = i % len(sample_contexts)
        pattern_idx = i % len(patterns)
        history.add_observation(
            context=sample_contexts[ctx_idx],
            pattern_id=patterns[pattern_idx],
            outcome="success" if i % 3 != 0 else "failure"
        )

    return history


# =============================================================================
# T3.1.x: MAB Initialization Tests
# =============================================================================

class TestMABInitialization:
    """Tests for MAB initialization (T3.1.x)"""

    def test_mab_initialize(self, sample_patterns):
        """T3.1.1: MAB initializes with patterns."""
        mab = ContextualMAB()
        result = mab.initialize(sample_patterns)

        assert result is True
        assert mab.mab is not None
        assert len(mab.arms) == len(sample_patterns)
        assert set(mab.arms) == set(sample_patterns)
        assert mab.is_fitted is False

    def test_mab_config_defaults(self):
        """T3.1.2: Default MAB config is valid."""
        config = MABConfig()

        assert config.learning_policy == "thompson_sampling"
        assert config.neighborhood_policy == "knearest"
        assert config.neighborhood_k == 5
        assert config.seed == 42
        assert config.validate() is True

    def test_mab_custom_config(self, sample_patterns):
        """T3.1.3: Custom MAB config applied."""
        config = MABConfig(
            learning_policy="ucb1",
            neighborhood_policy="radius",
            neighborhood_radius=2.0,
            exploration_alpha=1.5,
            seed=123
        )

        assert config.validate() is True

        mab = ContextualMAB(config=config)
        result = mab.initialize(sample_patterns)

        assert result is True
        assert mab.config.learning_policy == "ucb1"
        assert mab.config.neighborhood_policy == "radius"
        assert mab.config.seed == 123

    def test_mab_initialize_empty_patterns(self):
        """Initialize with empty patterns fails."""
        mab = ContextualMAB()
        result = mab.initialize([])

        assert result is False
        assert mab.mab is None

    def test_mab_config_invalid(self):
        """Invalid config fails validation."""
        config = MABConfig(learning_policy="invalid_policy")
        assert config.validate() is False

        config = MABConfig(neighborhood_k=0)
        assert config.validate() is False

        config = MABConfig(epsilon=1.5)
        assert config.validate() is False


# =============================================================================
# T3.2.x: Training Tests
# =============================================================================

class TestMABTraining:
    """Tests for MAB training (T3.2.x)"""

    def test_mab_fit(self, sample_patterns, sample_contexts):
        """T3.2.1: MAB fits on batch data."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # Create training data
        contexts = sample_contexts * 5  # 20 observations
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(20)]
        rewards = [1 if i % 3 != 0 else 0 for i in range(20)]

        result = mab.fit(contexts, decisions, rewards)

        assert result is True
        assert mab.is_fitted is True

    def test_mab_partial_fit(self, sample_patterns, sample_contexts):
        """T3.2.2: MAB updates incrementally."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # First batch fit
        contexts = sample_contexts * 3
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(12)]
        rewards = [1] * 12
        mab.fit(contexts, decisions, rewards)

        # Partial fit
        result = mab.partial_fit(
            context=sample_contexts[0],
            decision=sample_patterns[0],
            reward=1
        )

        assert result is True

    def test_mab_fit_without_initialize(self, sample_contexts):
        """Fit without initialize fails."""
        mab = ContextualMAB()

        result = mab.fit(
            contexts=sample_contexts,
            decisions=["pattern:a"] * 4,
            rewards=[1] * 4
        )

        assert result is False

    def test_mab_partial_fit_without_fit(self, sample_patterns, sample_contexts):
        """Partial fit without initial fit fails."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        result = mab.partial_fit(
            context=sample_contexts[0],
            decision=sample_patterns[0],
            reward=1
        )

        assert result is False


# =============================================================================
# T3.3.x: Prediction Tests
# =============================================================================

class TestMABPrediction:
    """Tests for MAB prediction (T3.3.x)"""

    def test_mab_predict(self, sample_patterns, sample_contexts):
        """T3.3.1: MAB makes predictions."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # Fit with data favoring first pattern for first context type
        contexts = [sample_contexts[0]] * 10
        decisions = [sample_patterns[0]] * 10
        rewards = [1] * 10
        mab.fit(contexts, decisions, rewards)

        prediction = mab.predict(sample_contexts[0])

        assert prediction is not None
        assert prediction in sample_patterns

    def test_mab_predict_expectations(self, sample_patterns, sample_contexts):
        """T3.3.2: MAB returns expectations for all arms."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # Fit with varied data
        contexts = sample_contexts * 5
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(20)]
        rewards = [1 if i % 2 == 0 else 0 for i in range(20)]
        mab.fit(contexts, decisions, rewards)

        expectations = mab.predict_expectations(sample_contexts[0])

        assert isinstance(expectations, dict)
        assert len(expectations) == len(sample_patterns)
        for pattern in sample_patterns:
            assert pattern in expectations
            assert isinstance(expectations[pattern], (int, float))
            assert 0.0 <= expectations[pattern] <= 1.0

    def test_mab_context_affects_prediction(self, sample_patterns, sample_contexts):
        """T3.3.3: Different contexts yield different predictions."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # Train with context-specific patterns
        # Context 0 -> pattern 0 (always success)
        # Context 1 -> pattern 1 (always success)
        training_contexts = []
        training_decisions = []
        training_rewards = []

        for i in range(20):
            if i < 10:
                training_contexts.append(sample_contexts[0])
                training_decisions.append(sample_patterns[0])
                training_rewards.append(1)
            else:
                training_contexts.append(sample_contexts[1])
                training_decisions.append(sample_patterns[1])
                training_rewards.append(1)

        mab.fit(training_contexts, training_decisions, training_rewards)

        # Get expectations for different contexts
        exp_ctx0 = mab.predict_expectations(sample_contexts[0])
        exp_ctx1 = mab.predict_expectations(sample_contexts[1])

        # The expectations should differ between contexts
        # (KNearest should find different neighbors)
        assert exp_ctx0 != exp_ctx1 or len(sample_patterns) == 1

    def test_mab_predict_unfitted(self, sample_patterns, sample_contexts):
        """Predict on unfitted MAB returns None."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        prediction = mab.predict(sample_contexts[0])
        assert prediction is None

        expectations = mab.predict_expectations(sample_contexts[0])
        assert expectations == {}


# =============================================================================
# T3.4.x: Arm Management Tests
# =============================================================================

class TestArmManagement:
    """Tests for arm management (T3.4.x)"""

    def test_mab_add_arm(self, sample_patterns, sample_contexts):
        """T3.4.1: New patterns can be added."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # Fit first
        contexts = sample_contexts * 3
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(12)]
        rewards = [1] * 12
        mab.fit(contexts, decisions, rewards)

        # Add new arm
        new_pattern = "pattern:new_cylinder"
        result = mab.add_arm(new_pattern)

        assert result is True
        assert new_pattern in mab.arms
        assert len(mab.arms) == len(sample_patterns) + 1

    def test_mab_remove_arm(self, sample_patterns, sample_contexts):
        """T3.4.2: Patterns can be removed."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # Fit first
        contexts = sample_contexts * 3
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(12)]
        rewards = [1] * 12
        mab.fit(contexts, decisions, rewards)

        # Remove arm
        pattern_to_remove = sample_patterns[0]
        result = mab.remove_arm(pattern_to_remove)

        assert result is True
        assert pattern_to_remove not in mab.arms
        assert len(mab.arms) == len(sample_patterns) - 1

    def test_mab_add_duplicate_arm(self, sample_patterns):
        """Adding duplicate arm returns True but doesn't duplicate."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        result = mab.add_arm(sample_patterns[0])
        assert result is True
        assert mab.arms.count(sample_patterns[0]) == 1

    def test_mab_remove_nonexistent_arm(self, sample_patterns):
        """Removing nonexistent arm returns False."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        result = mab.remove_arm("pattern:does_not_exist")
        assert result is False


# =============================================================================
# T3.5.x: Warm Start Tests
# =============================================================================

class TestWarmStart:
    """Tests for warm start functionality (T3.5.x)"""

    def test_warm_start_success(self, sample_patterns, temp_history):
        """T3.5.1: MAB warm starts from history."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        result = warm_start_mab(mab, temp_history)

        assert result is True
        assert mab.is_fitted is True

    def test_warm_start_insufficient_data(self, sample_patterns, tmp_path, sample_contexts):
        """T3.5.2: Warm start fails gracefully with insufficient data."""
        # Create history with fewer than min_observations
        history = ContextHistory(path=tmp_path / "sparse_history.json")
        for i in range(5):  # Only 5 observations (default min is 10)
            history.add_observation(
                context=sample_contexts[0],
                pattern_id=sample_patterns[0],
                outcome="success"
            )

        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        result = warm_start_mab(mab, history)

        assert result is False
        assert mab.is_fitted is False

    def test_warm_start_with_scaler(self, sample_patterns, temp_history, tmp_path):
        """Warm start with scaler normalizes contexts."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        scaler = ScalerManager(path=tmp_path / "scaler.pkl")

        result = warm_start_mab(mab, temp_history, scaler)

        assert result is True
        assert scaler.is_fitted is True

    def test_warm_start_filters_unknown_patterns(self, tmp_path, sample_contexts):
        """Warm start filters out observations for unknown patterns."""
        # Create history with observations for unknown patterns
        history = ContextHistory(path=tmp_path / "mixed_history.json")

        # Add observations for known pattern
        for i in range(8):
            history.add_observation(
                context=sample_contexts[0],
                pattern_id="pattern:known",
                outcome="success"
            )

        # Add observations for unknown pattern
        for i in range(10):
            history.add_observation(
                context=sample_contexts[1],
                pattern_id="pattern:unknown",
                outcome="success"
            )

        mab = ContextualMAB()
        mab.initialize(["pattern:known"])  # Only knows one pattern

        # Should fail because only 8 observations for known pattern
        result = warm_start_mab(mab, history)
        assert result is False


# =============================================================================
# T3.6.x: Fallback Tests
# =============================================================================

class TestFallback:
    """Tests for fallback logic (T3.6.x)"""

    def test_fallback_unfitted(self, sample_patterns):
        """T3.6.1: Fallback when MAB not fitted."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)
        # Not fitted

        patterns = [
            {"id": "pattern:a", "weight": 0.8},
            {"id": "pattern:b", "weight": 0.5},
            {"id": "pattern:c", "weight": 0.9},
        ]

        context = [0.0] * 21

        result = get_pattern_ranking(mab, context, patterns)

        # Should fall back to static weight ordering
        assert len(result) == 3
        assert result[0]["id"] == "pattern:c"  # highest weight
        assert result[1]["id"] == "pattern:a"
        assert result[2]["id"] == "pattern:b"

    def test_fallback_error(self, sample_patterns, sample_contexts):
        """T3.6.2: Fallback on prediction error."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        # Fit MAB
        contexts = sample_contexts * 3
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(12)]
        rewards = [1] * 12
        mab.fit(contexts, decisions, rewards)

        patterns = [
            {"id": "pattern:x", "weight": 0.3},  # Not in MAB arms
            {"id": "pattern:y", "weight": 0.7},
        ]

        # Context vector (should work, but patterns aren't in MAB)
        result = get_pattern_ranking(mab, sample_contexts[0], patterns)

        # Should return patterns (may use fallback if expectations empty)
        assert len(result) == 2

    def test_fallback_uniform(self, sample_patterns):
        """Fallback with uniform strategy."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        patterns = [
            {"id": "pattern:a"},
            {"id": "pattern:b"},
        ]

        result = get_pattern_ranking(mab, [0.0] * 21, patterns, fallback="uniform")

        assert len(result) == 2

    def test_fallback_empty_patterns(self, sample_patterns):
        """Fallback with empty patterns list."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        result = get_pattern_ranking(mab, [0.0] * 21, [])

        assert result == []


# =============================================================================
# Additional Tests
# =============================================================================

class TestPersistence:
    """Tests for MAB persistence"""

    def test_save_and_load(self, sample_patterns, sample_contexts, temp_mab_path):
        """MAB state can be saved and loaded."""
        # Create and fit MAB
        mab1 = ContextualMAB()
        mab1.initialize(sample_patterns)
        contexts = sample_contexts * 3
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(12)]
        rewards = [1] * 12
        mab1.fit(contexts, decisions, rewards)

        # Get prediction before save
        pred_before = mab1.predict(sample_contexts[0])

        # Save
        assert mab1.save(temp_mab_path) is True

        # Load into new instance
        mab2 = ContextualMAB()
        assert mab2.load(temp_mab_path) is True

        # Verify state restored
        assert mab2.is_fitted is True
        assert set(mab2.arms) == set(sample_patterns)

        # Prediction should be same
        pred_after = mab2.predict(sample_contexts[0])
        assert pred_before == pred_after

    def test_load_nonexistent(self, temp_mab_path):
        """Loading nonexistent file returns False."""
        mab = ContextualMAB()
        assert mab.load(temp_mab_path) is False


class TestEdgeCases:
    """Edge case tests"""

    def test_config_epsilon_greedy(self, sample_patterns, sample_contexts):
        """Epsilon greedy policy works."""
        config = MABConfig(
            learning_policy="epsilon_greedy",
            epsilon=0.2
        )
        mab = ContextualMAB(config=config)
        mab.initialize(sample_patterns)

        contexts = sample_contexts * 3
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(12)]
        rewards = [1] * 12

        assert mab.fit(contexts, decisions, rewards) is True
        assert mab.predict(sample_contexts[0]) is not None

    def test_config_clusters_policy(self, sample_patterns, sample_contexts):
        """Clusters neighborhood policy works."""
        config = MABConfig(
            neighborhood_policy="clusters",
            n_clusters=2
        )
        mab = ContextualMAB(config=config)
        mab.initialize(sample_patterns)

        contexts = sample_contexts * 5
        decisions = [sample_patterns[i % len(sample_patterns)] for i in range(20)]
        rewards = [1] * 20

        assert mab.fit(contexts, decisions, rewards) is True
        assert mab.predict(sample_contexts[0]) is not None

    def test_arms_property_returns_copy(self, sample_patterns):
        """Arms property returns a copy, not the internal list."""
        mab = ContextualMAB()
        mab.initialize(sample_patterns)

        arms = mab.arms
        arms.append("should_not_affect_internal")

        assert "should_not_affect_internal" not in mab.arms
