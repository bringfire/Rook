"""
Tests for Phase 4: API Updates for Contextual MAB Integration

Test categories:
- T4.1.x: Query with context (4 tests)
- T4.2.x: Record with context (3 tests)
- T4.3.x: Introspection (2 tests)
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the API functions
from rook.knowledge import (
    query_knowledge,
    record_knowledge,
    get_pattern_statistics,
    explain_recommendation,
    get_learning_summary,
    load_graph,
    save_graph,
    CANONICAL_PATH,
    LOCAL_PATH,
)

# Import context modules for mocking
from rook.context import encode_context
from rook.context_storage import ContextHistory


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_knowledge_dir(tmp_path):
    """Create temporary knowledge directory with test graphs."""
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()

    # Create minimal canonical graph
    canonical = {
        "directed": True,
        "multigraph": False,
        "graph": {"name": "test", "version": "1.0.0"},
        "nodes": [
            {
                "id": "intent:create_layer",
                "type": "intent",
                "labels": ["create layer", "add layer", "new layer"]
            },
            {
                "id": "action:rhino_layer_create",
                "type": "action",
                "tool": "rhino_layer_create"
            },
            {
                "id": "pattern:nested_layers",
                "type": "pattern",
                "params": {"name": "child", "parent": "parent"},
                "note": "Create nested layers with a child name plus parent field",
                "weight": 0.8
            },
            {
                "id": "antipattern:literal_colons",
                "type": "antipattern",
                "params": {"name": "parent::child"},
                "reason": "Creates literal name, not hierarchy",
                "weight": 0.7
            }
        ],
        "links": [
            {
                "source": "intent:create_layer",
                "target": "action:rhino_layer_create",
                "relation": "solved_by"
            },
            {
                "source": "action:rhino_layer_create",
                "target": "pattern:nested_layers",
                "relation": "requires"
            },
            {
                "source": "action:rhino_layer_create",
                "target": "antipattern:literal_colons",
                "relation": "avoid"
            }
        ]
    }

    canonical_path = knowledge_dir / "canonical.json"
    canonical_path.write_text(json.dumps(canonical, indent=2))

    # Create empty local graph
    local = {
        "directed": True,
        "multigraph": False,
        "graph": {"name": "local", "version": "0.1.0"},
        "nodes": [],
        "links": []
    }
    local_path = knowledge_dir / "local.json"
    local_path.write_text(json.dumps(local, indent=2))

    return knowledge_dir


@pytest.fixture
def mock_context_available():
    """Mock contextual MAB as available."""
    import rook.knowledge as knowledge

    # The contextual stack is bound lazily; initialize it explicitly so the
    # patched names below refer to the same module attributes in isolation.
    knowledge._contextual_ready()
    with patch('rook.knowledge._contextual_mab_available', True):
        yield


@pytest.fixture
def mock_context_unavailable():
    """Mock contextual MAB as unavailable."""
    with patch('rook.knowledge._contextual_mab_available', False):
        yield


# =============================================================================
# T4.1.x: Query with Context Tests
# =============================================================================

class TestQueryWithContext:
    """Tests for query_knowledge with context parameters."""

    def test_query_accepts_params_parameter(self, temp_knowledge_dir):
        """T4.1.1: query_knowledge accepts params parameter."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            # Should not raise error
            result = query_knowledge(
                intent="create layer",
                tool="rhino_layer_create",
                params={"name": "test_layer"}
            )

            assert "patterns" in result
            assert "avoid" in result
            assert "confidence" in result

    def test_query_accepts_include_context_score(self, temp_knowledge_dir):
        """T4.1.2: query_knowledge accepts include_context_score parameter."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            result = query_knowledge(
                intent="create layer",
                tool="rhino_layer_create",
                include_context_score=True
            )

            assert "patterns" in result

    def test_query_backward_compatible(self, temp_knowledge_dir):
        """T4.1.3: query_knowledge remains backward compatible."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            # Old-style call without new params should work
            result = query_knowledge(intent="create layer")

            assert "patterns" in result
            assert len(result["patterns"]) > 0

            # Also test tool-only query
            result2 = query_knowledge(tool="rhino_layer_create")
            assert "patterns" in result2

    def test_query_with_context_encodes_vector(self, temp_knowledge_dir, mock_context_available):
        """T4.1.4: query_knowledge encodes context vector when contextual MAB available."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"), \
             patch('rook.knowledge.encode_context') as mock_encode:

            mock_encode.return_value = [0.0] * 21

            query_knowledge(
                intent="create nested layer",
                tool="rhino_layer_create",
                params={"name": "child", "parent": "parent"}
            )

            # encode_context should have been called
            mock_encode.assert_called_once_with(
                "create nested layer",
                "rhino_layer_create",
                {"name": "child", "parent": "parent"}
            )


# =============================================================================
# T4.2.x: Record with Context Tests
# =============================================================================

class TestRecordWithContext:
    """Tests for record_knowledge with context tracking."""

    def test_record_accepts_context_override(self, temp_knowledge_dir):
        """T4.2.1: record_knowledge accepts context_override parameter."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            custom_context = [1.0] * 21

            result = record_knowledge(
                intent="test intent",
                action={"tool": "rhino_create", "params": {"type": "BOX"}},
                outcome="success",
                context_override=custom_context
            )

            assert result["success"] is True
            assert "context_recorded" in result

    def test_record_returns_context_status(self, temp_knowledge_dir):
        """T4.2.2: record_knowledge returns context recording status."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            result = record_knowledge(
                intent="test intent",
                action={"tool": "rhino_create", "params": {"type": "SPHERE"}},
                outcome="success"
            )

            # Should have new context-related fields
            assert "context_recorded" in result
            assert "contextual_mab_updated" in result

    def test_record_backward_compatible(self, temp_knowledge_dir):
        """T4.2.3: record_knowledge remains backward compatible."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            # Old-style call without context_override should work
            result = record_knowledge(
                intent="create a box",
                action={"tool": "rhino_create", "params": {"type": "BOX"}},
                outcome="success"
            )

            assert result["success"] is True
            assert "message" in result
            assert "mab_updated" in result


# =============================================================================
# T4.3.x: Introspection Tests
# =============================================================================

class TestIntrospection:
    """Tests for introspection methods."""

    def test_get_pattern_statistics_returns_structure(self):
        """T4.3.1: get_pattern_statistics returns proper structure."""
        with patch('rook.knowledge._contextual_mab_available', False):
            result = get_pattern_statistics()

            assert "patterns" in result
            assert "total_observations" in result
            assert "contextual_mab_available" in result
            assert result["contextual_mab_available"] is False

    def test_explain_recommendation_returns_structure(self):
        """T4.3.2: explain_recommendation returns proper structure."""
        with patch('rook.knowledge._contextual_mab_available', False):
            result = explain_recommendation(
                intent="create nested layer",
                tool="rhino_layer_create"
            )

            assert "intent" in result
            assert "tool" in result
            assert "context_vector" in result
            assert "pattern_scores" in result
            assert "reasoning" in result
            assert result["intent"] == "create nested layer"
            assert result["tool"] == "rhino_layer_create"

    def test_get_learning_summary_returns_structure(self, temp_knowledge_dir):
        """T4.3.3: get_learning_summary returns comprehensive structure."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"), \
             patch('rook.knowledge._contextual_mab_available', False):

            result = get_learning_summary()

            assert "knowledge_graph" in result
            assert "mab" in result
            assert "contextual_mab" in result
            assert "context_history" in result

            # Check knowledge_graph structure
            kg = result["knowledge_graph"]
            assert "total_nodes" in kg
            assert "total_links" in kg
            assert "node_types" in kg

            # Check mab structure
            mab = result["mab"]
            assert "available" in mab

            # Check contextual_mab structure
            cmab = result["contextual_mab"]
            assert "available" in cmab
            assert "is_fitted" in cmab


# =============================================================================
# Additional Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Edge case and integration tests."""

    def test_query_with_none_params(self, temp_knowledge_dir):
        """Query handles None params gracefully."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            result = query_knowledge(
                intent="create layer",
                tool="rhino_layer_create",
                params=None
            )

            assert "patterns" in result

    def test_record_with_empty_params(self, temp_knowledge_dir):
        """Record handles empty params gracefully."""
        with patch('rook.knowledge.CANONICAL_PATH', temp_knowledge_dir / "canonical.json"), \
             patch('rook.knowledge.LOCAL_PATH', temp_knowledge_dir / "local.json"):

            result = record_knowledge(
                intent="test",
                action={"tool": "rhino_ping", "params": {}},
                outcome="success"
            )

            assert result["success"] is True

    def test_explain_with_params(self):
        """explain_recommendation handles params parameter."""
        with patch('rook.knowledge._contextual_mab_available', False):
            result = explain_recommendation(
                intent="create box",
                tool="rhino_create",
                params={"type": "BOX", "width": 10}
            )

            assert result["tool"] == "rhino_create"

    def test_pattern_statistics_with_specific_id(self):
        """get_pattern_statistics can filter by pattern_id."""
        with patch('rook.knowledge._contextual_mab_available', False):
            result = get_pattern_statistics(pattern_id="pattern:test")

            assert "patterns" in result
            # Should return empty since no observations exist
            assert result["patterns"] == {}
