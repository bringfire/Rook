"""
Tests for Context Storage & Persistence (Phase 2 of Contextual MAB Migration)

Test IDs correspond to mab_migration_tests.json:
- T2.1.x: Context history tests
- T2.2.x: Scaler tests
- T2.3.x: Migration tests
"""

import pytest
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from rook.context_storage import (
    ContextHistory,
    ContextObservation,
    ScalerManager,
    migrate_knowledge_graph_v1_to_v2,
    is_migration_needed,
    get_schema_version,
    SCHEMA_VERSION,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_history_path(tmp_path):
    """Create a temporary path for context history."""
    return tmp_path / "test_context_history.json"


@pytest.fixture
def temp_scaler_path(tmp_path):
    """Create a temporary path for scaler."""
    return tmp_path / "test_scaler.pkl"


@pytest.fixture
def sample_context():
    """Create a sample 21-dimensional context vector."""
    # Tool category one-hot (10 dims) + geometry multi-hot (8 dims) + characteristics (3 dims)
    return [
        1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # create category
        0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0,  # brep geometry
        0.3, 0.0, 0.0  # param_count, selection_dep, destructive
    ]


@pytest.fixture
def sample_contexts():
    """Create multiple sample context vectors for scaler testing."""
    return [
        [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.3, 0.0, 0.0],  # create brep
        [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.0, 0.0],  # layer
        [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.5, 1.0, 1.0],  # transform brep
    ]


# =============================================================================
# T2.1.x: Context History Tests
# =============================================================================

class TestContextHistory:
    """Tests for ContextHistory class (T2.1.x)"""

    def test_add_observation(self, temp_history_path, sample_context):
        """T2.1.1: Observations can be added to history."""
        history = ContextHistory(path=temp_history_path)

        obs_id = history.add_observation(
            context=sample_context,
            pattern_id="pattern:test_001",
            outcome="success",
            intent="create a box",
            tool="rhino_create"
        )

        assert obs_id is not None
        assert obs_id.startswith("ctx_")
        assert len(obs_id) == 16  # "ctx_" + 12 hex chars

        # Verify observation was stored
        observations = history.get_observations()
        assert len(observations) == 1
        assert observations[0]["pattern_id"] == "pattern:test_001"
        assert observations[0]["outcome"] == "success"

    def test_get_observations(self, temp_history_path, sample_context):
        """T2.1.2: Observations can be retrieved."""
        history = ContextHistory(path=temp_history_path)

        # Add multiple observations
        for i in range(5):
            history.add_observation(
                context=sample_context,
                pattern_id=f"pattern:test_{i:03d}",
                outcome="success" if i % 2 == 0 else "failure",
                intent=f"test intent {i}"
            )

        observations = history.get_observations()
        assert len(observations) == 5

        # Test limit
        limited = history.get_observations(limit=3)
        assert len(limited) == 3

    def test_observations_ordered(self, temp_history_path, sample_context):
        """T2.1.3: Observations returned newest first."""
        history = ContextHistory(path=temp_history_path)

        # Add observations with small delays to ensure different timestamps
        history.add_observation(
            context=sample_context,
            pattern_id="pattern:first",
            outcome="success"
        )
        time.sleep(0.01)  # Small delay for different timestamp
        history.add_observation(
            context=sample_context,
            pattern_id="pattern:second",
            outcome="success"
        )
        time.sleep(0.01)
        history.add_observation(
            context=sample_context,
            pattern_id="pattern:third",
            outcome="success"
        )

        observations = history.get_observations()
        assert observations[0]["pattern_id"] == "pattern:third"
        assert observations[1]["pattern_id"] == "pattern:second"
        assert observations[2]["pattern_id"] == "pattern:first"

    def test_observations_by_pattern(self, temp_history_path, sample_context):
        """T2.1.4: Filter observations by pattern ID."""
        history = ContextHistory(path=temp_history_path)

        # Add observations for different patterns
        for i in range(3):
            history.add_observation(
                context=sample_context,
                pattern_id="pattern:target",
                outcome="success"
            )
        for i in range(5):
            history.add_observation(
                context=sample_context,
                pattern_id="pattern:other",
                outcome="failure"
            )

        target_obs = history.get_observations_for_pattern("pattern:target")
        assert len(target_obs) == 3
        assert all(obs["pattern_id"] == "pattern:target" for obs in target_obs)

        other_obs = history.get_observations_for_pattern("pattern:other")
        assert len(other_obs) == 5

    def test_persistence(self, temp_history_path, sample_context):
        """Observations persist across instances."""
        # Create and populate first instance
        history1 = ContextHistory(path=temp_history_path)
        history1.add_observation(
            context=sample_context,
            pattern_id="pattern:persistent",
            outcome="success"
        )

        # Create new instance pointing to same file
        history2 = ContextHistory(path=temp_history_path)
        observations = history2.get_observations()

        assert len(observations) == 1
        assert observations[0]["pattern_id"] == "pattern:persistent"

    def test_prune_old_observations(self, temp_history_path, sample_context):
        """Old observations can be pruned."""
        history = ContextHistory(path=temp_history_path)

        # Add current observation
        history.add_observation(
            context=sample_context,
            pattern_id="pattern:recent",
            outcome="success"
        )

        # Manually add an old observation
        old_obs = ContextObservation(
            id="ctx_old_000000001",
            features=sample_context,
            pattern_id="pattern:old",
            outcome="failure",
            timestamp=(datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        )
        history._observations.append(old_obs)
        history.save()

        # Verify both exist
        assert len(history.get_observations()) == 2

        # Prune old observations
        pruned = history.prune_old_observations(max_age_days=90)
        assert pruned == 1

        # Verify only recent remains
        observations = history.get_observations()
        assert len(observations) == 1
        assert observations[0]["pattern_id"] == "pattern:recent"

    def test_validation_invalid_context_length(self, temp_history_path):
        """Invalid context length raises error."""
        history = ContextHistory(path=temp_history_path)

        with pytest.raises(ValueError, match="21 dimensions"):
            history.add_observation(
                context=[1.0, 0.0, 0.0],  # Too short
                pattern_id="pattern:test",
                outcome="success"
            )

    def test_validation_invalid_context_type(self, temp_history_path):
        """Invalid context type raises error."""
        history = ContextHistory(path=temp_history_path)

        with pytest.raises(ValueError, match="must be a list"):
            history.add_observation(
                context="not a list",
                pattern_id="pattern:test",
                outcome="success"
            )

    def test_validation_invalid_outcome(self, temp_history_path, sample_context):
        """Invalid outcome raises error."""
        history = ContextHistory(path=temp_history_path)

        with pytest.raises(ValueError, match="success.*failure"):
            history.add_observation(
                context=sample_context,
                pattern_id="pattern:test",
                outcome="invalid"
            )

    def test_clear(self, temp_history_path, sample_context):
        """History can be cleared."""
        history = ContextHistory(path=temp_history_path)

        history.add_observation(
            context=sample_context,
            pattern_id="pattern:test",
            outcome="success"
        )
        assert history.get_observation_count() == 1

        history.clear()
        assert history.get_observation_count() == 0


# =============================================================================
# T2.2.x: Scaler Tests
# =============================================================================

class TestScalerManager:
    """Tests for ScalerManager class (T2.2.x)"""

    def test_scaler_fit_transform(self, temp_scaler_path, sample_contexts):
        """T2.2.1: Scaler fits and transforms correctly."""
        scaler = ScalerManager(path=temp_scaler_path)

        # Fit on sample contexts
        result = scaler.fit(sample_contexts)
        assert result is True
        assert scaler.is_fitted is True

        # Transform a context
        transformed = scaler.transform(sample_contexts[0])
        assert len(transformed) == 21

        # All values should be in [0, 1]
        for val in transformed:
            assert 0.0 <= val <= 1.0

    def test_scaler_persistence(self, temp_scaler_path, sample_contexts):
        """T2.2.2: Scaler state persists to disk."""
        # Create and fit first scaler
        scaler1 = ScalerManager(path=temp_scaler_path)
        scaler1.fit(sample_contexts)
        original_transform = scaler1.transform(sample_contexts[0])

        # Save to disk
        assert scaler1.save() is True

        # Load in new instance
        scaler2 = ScalerManager(path=temp_scaler_path)
        assert scaler2.load() is True
        assert scaler2.is_fitted is True

        # Transform should produce same result
        loaded_transform = scaler2.transform(sample_contexts[0])
        assert original_transform == loaded_transform

    def test_scaler_empty_handling(self, temp_scaler_path):
        """T2.2.3: Scaler handles empty data gracefully."""
        scaler = ScalerManager(path=temp_scaler_path)

        # Fit on empty data
        result = scaler.fit([])
        assert result is True
        assert scaler.is_fitted is True

        # Should still be able to transform
        context = [0.5] * 21
        transformed = scaler.transform(context)
        assert len(transformed) == 21

    def test_scaler_fit_transform_combined(self, temp_scaler_path, sample_contexts):
        """fit_transform combines fit and transform."""
        scaler = ScalerManager(path=temp_scaler_path)

        transformed = scaler.fit_transform(sample_contexts)

        assert len(transformed) == len(sample_contexts)
        for t in transformed:
            assert len(t) == 21
            for val in t:
                assert 0.0 <= val <= 1.0

    def test_scaler_transform_without_fit(self, temp_scaler_path, sample_contexts):
        """Transform without fit raises error."""
        scaler = ScalerManager(path=temp_scaler_path)

        with pytest.raises(ValueError, match="must be fitted"):
            scaler.transform(sample_contexts[0])

    def test_scaler_load_nonexistent(self, temp_scaler_path):
        """Loading nonexistent file returns False."""
        scaler = ScalerManager(path=temp_scaler_path)
        assert scaler.load() is False


# =============================================================================
# T2.3.x: Migration Tests
# =============================================================================

class TestSchemaMigration:
    """Tests for schema migration utilities (T2.3.x)"""

    def test_schema_migration(self):
        """T2.3.1: Migration from v1 to v2 preserves data."""
        v1_graph = {
            "directed": True,
            "multigraph": False,
            "graph": {
                "name": "local",
                "version": "0.1.0"
            },
            "nodes": [
                {"id": "intent:test", "type": "intent", "labels": ["test"]},
                {"id": "pattern:test", "type": "pattern", "params": {}}
            ],
            "links": [
                {"source": "intent:test", "target": "pattern:test", "relation": "solved_by"}
            ]
        }

        migrated = migrate_knowledge_graph_v1_to_v2(v1_graph)

        # Schema version should be updated
        assert get_schema_version(migrated) == "2.0.0"

        # All original data should be preserved
        assert len(migrated["nodes"]) == 2
        assert len(migrated["links"]) == 1
        assert migrated["directed"] is True
        assert migrated["multigraph"] is False

        # Migration metadata should be present
        assert migrated["graph"]["migrated_from"] == "1.0.0"
        assert "migrated_at" in migrated["graph"]

    def test_migration_idempotent(self):
        """T2.3.2: Migration is idempotent."""
        v1_graph = {
            "directed": True,
            "multigraph": False,
            "graph": {"name": "test"},
            "nodes": [{"id": "node1", "type": "intent"}],
            "links": []
        }

        # Migrate twice
        migrated1 = migrate_knowledge_graph_v1_to_v2(v1_graph)
        migrated2 = migrate_knowledge_graph_v1_to_v2(migrated1)

        # Second migration should not change anything
        assert migrated1 == migrated2

    def test_is_migration_needed(self):
        """is_migration_needed correctly identifies v1 graphs."""
        v1_graph = {
            "graph": {"name": "test"},
            "nodes": [],
            "links": []
        }
        assert is_migration_needed(v1_graph) is True

        v2_graph = {
            "graph": {"schema_version": "2.0.0"},
            "nodes": [],
            "links": []
        }
        assert is_migration_needed(v2_graph) is False

    def test_get_schema_version_default(self):
        """get_schema_version returns 1.0.0 for graphs without version."""
        graph = {"graph": {}, "nodes": [], "links": []}
        assert get_schema_version(graph) == "1.0.0"


# =============================================================================
# Additional Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Additional edge case tests"""

    def test_context_observation_dataclass(self, sample_context):
        """ContextObservation dataclass works correctly."""
        obs = ContextObservation(
            id="ctx_test123456",
            features=sample_context,
            pattern_id="pattern:test",
            outcome="success",
            timestamp=datetime.now(timezone.utc).isoformat(),
            intent="test intent",
            tool="rhino_create",
            metadata={"key": "value"}
        )

        # Convert to dict and back
        obs_dict = obs.to_dict()
        obs_restored = ContextObservation.from_dict(obs_dict)

        assert obs_restored.id == obs.id
        assert obs_restored.features == obs.features
        assert obs_restored.pattern_id == obs.pattern_id
        assert obs_restored.metadata == obs.metadata

    def test_history_with_metadata(self, temp_history_path, sample_context):
        """Observations can include custom metadata."""
        history = ContextHistory(path=temp_history_path)

        history.add_observation(
            context=sample_context,
            pattern_id="pattern:test",
            outcome="success",
            metadata={"error_message": None, "duration_ms": 150}
        )

        observations = history.get_observations()
        assert observations[0]["metadata"]["duration_ms"] == 150

    def test_scaler_constant_feature(self, temp_scaler_path):
        """Scaler handles constant features (all same value)."""
        contexts = [
            [1.0, 0.5, 0.0] * 7,  # 21 dimensions, with constant 0.5 in middle
            [1.0, 0.5, 0.0] * 7,
            [1.0, 0.5, 0.0] * 7,
        ]

        scaler = ScalerManager(path=temp_scaler_path)
        scaler.fit(contexts)

        # Should not raise division by zero
        transformed = scaler.transform(contexts[0])
        assert len(transformed) == 21

    def test_large_history(self, temp_history_path, sample_context):
        """History handles many observations efficiently."""
        history = ContextHistory(path=temp_history_path)

        # Add 100 observations
        for i in range(100):
            history.add_observation(
                context=sample_context,
                pattern_id=f"pattern:test_{i % 10:03d}",
                outcome="success" if i % 3 != 0 else "failure"
            )

        assert history.get_observation_count() == 100

        # Get limited subset
        limited = history.get_observations(limit=20)
        assert len(limited) == 20

        # Filter by pattern
        pattern_obs = history.get_observations_for_pattern("pattern:test_000")
        assert len(pattern_obs) == 10  # Should have 10 observations for this pattern
