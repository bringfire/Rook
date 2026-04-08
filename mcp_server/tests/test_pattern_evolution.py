"""
Tests for Pattern Evolution (Phase 2, Task 4)

Tests the A-MEM style evolution logic:
- Candidate finding via structured filters
- Link decision (with mocked DSPy)
- Neighbor evolution (with mocked DSPy)
- Full integration flow
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from rook.learning.pattern_memory import PatternNote, PatternIndex
from rook.learning.pattern_evolution import PatternEvolution, get_pattern_evolution
from rook.learning.pattern_store import PatternStore


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_knowledge_dir(tmp_path):
    """Create a temporary knowledge directory for testing."""
    knowledge_dir = tmp_path / "knowledge" / "gh"
    patterns_dir = knowledge_dir / "patterns"
    patterns_dir.mkdir(parents=True)
    return knowledge_dir


@pytest.fixture
def evolution():
    """Create a PatternEvolution instance."""
    return PatternEvolution()


@pytest.fixture
def base_pattern():
    """Base pattern for evolution testing."""
    return PatternNote(
        pattern_id="base001",
        name="Base Pattern",
        solution_brief="Base solution for testing",
        solution_principle="The base principle for testing evolution",
        trigger_intents=["create shape", "make geometry"],
        trigger_symptoms=["geometry needed", "shape required"],
        tags=["geometry", "shapes", "basics"],
        components_needed=["Circle", "Rectangle"],
    )


@pytest.fixture
def related_pattern():
    """Pattern related to base_pattern (overlapping tags)."""
    return PatternNote(
        pattern_id="related001",
        name="Related Pattern",
        solution_brief="Related solution with similar concepts",
        solution_principle="Shares concepts with base pattern",
        trigger_intents=["modify shape", "adjust geometry"],
        trigger_symptoms=["geometry issue", "shape problem"],
        tags=["geometry", "modification"],
        components_needed=["Circle", "Move"],
    )


@pytest.fixture
def unrelated_pattern():
    """Pattern unrelated to base_pattern (no overlap)."""
    return PatternNote(
        pattern_id="unrelated001",
        name="Unrelated Pattern",
        solution_brief="Completely different domain",
        solution_principle="No relation to geometry",
        trigger_intents=["process data", "compute values"],
        trigger_symptoms=["data error", "computation needed"],
        tags=["data", "computation"],
        components_needed=["Panel", "Expression"],
    )


@pytest.fixture
def store_with_evolution(temp_knowledge_dir, monkeypatch):
    """Create a PatternStore with evolution enabled."""
    monkeypatch.setattr("rook.learning.pattern_store.KNOWLEDGE_DIR", temp_knowledge_dir)
    monkeypatch.setattr("rook.learning.pattern_store.PATTERNS_DIR", temp_knowledge_dir / "patterns")
    monkeypatch.setattr("rook.learning.pattern_store.INDEX_PATH", temp_knowledge_dir / "pattern_index.json")

    return PatternStore(auto_save=True, enable_evolution=True)


@pytest.fixture
def store_no_evolution(temp_knowledge_dir, monkeypatch):
    """Create a PatternStore with evolution disabled."""
    monkeypatch.setattr("rook.learning.pattern_store.KNOWLEDGE_DIR", temp_knowledge_dir)
    monkeypatch.setattr("rook.learning.pattern_store.PATTERNS_DIR", temp_knowledge_dir / "patterns")
    monkeypatch.setattr("rook.learning.pattern_store.INDEX_PATH", temp_knowledge_dir / "pattern_index.json")

    return PatternStore(auto_save=True, enable_evolution=False)


# =============================================================================
# PatternEvolution Unit Tests
# =============================================================================

class TestFindEvolutionCandidates:
    """Tests for find_evolution_candidates."""

    def test_finds_by_tag_overlap(self, evolution, base_pattern, related_pattern, unrelated_pattern):
        """Patterns with overlapping tags are found."""
        index = PatternIndex()
        all_patterns = {}

        for p in [base_pattern, related_pattern, unrelated_pattern]:
            all_patterns[p.pattern_id] = p
            index.add_pattern(p)

        # New pattern with overlapping tags
        new_pattern = PatternNote(
            pattern_id="new001",
            name="New Pattern",
            tags=["geometry", "new"],  # "geometry" overlaps
        )

        candidates = evolution.find_evolution_candidates(
            pattern=new_pattern,
            index=index,
            all_patterns=all_patterns,
            limit=10,
        )

        # Should find base_pattern and related_pattern (both have "geometry" tag)
        assert "base001" in candidates
        assert "related001" in candidates
        # Should not find unrelated
        assert "unrelated001" not in candidates

    def test_finds_by_component_overlap(self, evolution):
        """Patterns with overlapping components are found."""
        p1 = PatternNote(pattern_id="p1", components_needed=["Circle", "Line"])
        p2 = PatternNote(pattern_id="p2", components_needed=["Circle", "Rectangle"])
        p3 = PatternNote(pattern_id="p3", components_needed=["Panel", "Slider"])

        index = PatternIndex()
        all_patterns = {}
        for p in [p1, p2, p3]:
            all_patterns[p.pattern_id] = p
            index.add_pattern(p)

        new_pattern = PatternNote(pattern_id="new", components_needed=["Circle"])

        candidates = evolution.find_evolution_candidates(
            pattern=new_pattern,
            index=index,
            all_patterns=all_patterns,
        )

        assert "p1" in candidates
        assert "p2" in candidates
        assert "p3" not in candidates

    def test_excludes_self(self, evolution, base_pattern):
        """Pattern should not be in its own candidate list."""
        index = PatternIndex()
        all_patterns = {base_pattern.pattern_id: base_pattern}
        index.add_pattern(base_pattern)

        candidates = evolution.find_evolution_candidates(
            pattern=base_pattern,
            index=index,
            all_patterns=all_patterns,
        )

        assert base_pattern.pattern_id not in candidates

    def test_respects_limit(self, evolution):
        """Limit is respected."""
        index = PatternIndex()
        all_patterns = {}

        # Create many patterns with same tag
        for i in range(10):
            p = PatternNote(pattern_id=f"p{i}", tags=["shared"])
            all_patterns[p.pattern_id] = p
            index.add_pattern(p)

        new_pattern = PatternNote(pattern_id="new", tags=["shared"])

        candidates = evolution.find_evolution_candidates(
            pattern=new_pattern,
            index=index,
            all_patterns=all_patterns,
            limit=3,
        )

        assert len(candidates) == 3


class TestDecideLinks:
    """Tests for decide_links with mocked DSPy."""

    def test_decide_links_success(self, evolution, base_pattern, related_pattern):
        """Successfully decide links with mocked DSPy."""
        # Mock the linker
        mock_result = Mock()
        mock_result.links_to_create = ["related001"]
        mock_result.link_rationales = ["Both deal with geometry"]
        mock_result.updated_tags = ["geometry", "shapes", "basics", "linking"]

        with patch.object(evolution, "_linker", None):
            mock_linker = Mock()
            mock_linker.return_value = mock_result
            evolution._linker = mock_linker

            links, rationales, tags = evolution.decide_links(
                new_pattern=base_pattern,
                candidate_patterns=[related_pattern],
            )

            assert links == ["related001"]
            assert len(rationales) == 1
            assert "linking" in tags

    def test_decide_links_empty_candidates(self, evolution, base_pattern):
        """Empty candidates returns empty results."""
        links, rationales, tags = evolution.decide_links(
            new_pattern=base_pattern,
            candidate_patterns=[],
        )

        assert links == []
        assert rationales == []
        assert tags == base_pattern.tags

    def test_decide_links_filters_invalid_ids(self, evolution, base_pattern, related_pattern):
        """Invalid link IDs from DSPy are filtered out."""
        mock_result = Mock()
        mock_result.links_to_create = ["related001", "nonexistent", "also_fake"]
        mock_result.link_rationales = ["reason1", "reason2", "reason3"]
        mock_result.updated_tags = base_pattern.tags

        with patch.object(evolution, "_linker", None):
            mock_linker = Mock()
            mock_linker.return_value = mock_result
            evolution._linker = mock_linker

            links, _, _ = evolution.decide_links(
                new_pattern=base_pattern,
                candidate_patterns=[related_pattern],
            )

            # Only related001 exists in candidates
            assert links == ["related001"]

    def test_decide_links_handles_dspy_error(self, evolution, base_pattern, related_pattern):
        """DSPy errors are handled gracefully."""
        with patch.object(evolution, "_linker", None):
            mock_linker = Mock()
            mock_linker.side_effect = Exception("DSPy failed")
            evolution._linker = mock_linker

            links, rationales, tags = evolution.decide_links(
                new_pattern=base_pattern,
                candidate_patterns=[related_pattern],
            )

            # Graceful fallback
            assert links == []
            assert rationales == []
            assert tags == base_pattern.tags


class TestEvolveNeighbors:
    """Tests for evolve_neighbors with mocked DSPy."""

    def test_evolve_neighbors_success(self, evolution, base_pattern, related_pattern):
        """Successfully evolve neighbors with mocked DSPy."""
        mock_result = Mock()
        mock_result.should_evolve = True
        mock_result.neighbor_updates = [
            {
                "id": "related001",
                "new_tags": ["evolved-tag"],
                "context_addition": "New insight from base pattern",
                "rationale": "Shared geometry concepts",
            }
        ]

        with patch.object(evolution, "_evolver", None):
            mock_evolver = Mock()
            mock_evolver.return_value = mock_result
            evolution._evolver = mock_evolver

            updates = evolution.evolve_neighbors(
                new_pattern=base_pattern,
                neighbor_patterns=[related_pattern],
            )

            assert len(updates) == 1
            assert updates[0]["id"] == "related001"
            assert "evolved-tag" in updates[0]["new_tags"]

    def test_evolve_neighbors_no_evolution_needed(self, evolution, base_pattern, related_pattern):
        """DSPy decides no evolution needed."""
        mock_result = Mock()
        mock_result.should_evolve = False
        mock_result.neighbor_updates = []

        with patch.object(evolution, "_evolver", None):
            mock_evolver = Mock()
            mock_evolver.return_value = mock_result
            evolution._evolver = mock_evolver

            updates = evolution.evolve_neighbors(
                new_pattern=base_pattern,
                neighbor_patterns=[related_pattern],
            )

            assert updates == []

    def test_evolve_neighbors_empty_list(self, evolution, base_pattern):
        """Empty neighbor list returns empty updates."""
        updates = evolution.evolve_neighbors(
            new_pattern=base_pattern,
            neighbor_patterns=[],
        )

        assert updates == []


class TestApplyNeighborUpdates:
    """Tests for apply_neighbor_updates."""

    def test_applies_new_tags(self, evolution, related_pattern):
        """New tags are merged into neighbor."""
        all_patterns = {related_pattern.pattern_id: related_pattern}
        original_tags = related_pattern.tags.copy()

        updates = [
            {"id": "related001", "new_tags": ["new-tag-1", "new-tag-2"], "rationale": "testing"}
        ]

        modified = evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_patterns=all_patterns,
            triggering_pattern_id="trigger001",
        )

        assert "related001" in modified
        assert "new-tag-1" in related_pattern.tags
        assert "new-tag-2" in related_pattern.tags
        # Original tags preserved
        for tag in original_tags:
            assert tag in related_pattern.tags

    def test_applies_context_addition(self, evolution, related_pattern):
        """Context addition is appended to principle."""
        all_patterns = {related_pattern.pattern_id: related_pattern}
        original_principle = related_pattern.solution_principle

        updates = [
            {"id": "related001", "context_addition": "New related insight", "rationale": "testing"}
        ]

        modified = evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_patterns=all_patterns,
            triggering_pattern_id="trigger001",
        )

        assert "related001" in modified
        assert "New related insight" in related_pattern.solution_principle
        assert original_principle in related_pattern.solution_principle

    def test_tracks_evolution_metadata(self, evolution, related_pattern):
        """Evolution metadata is tracked correctly."""
        all_patterns = {related_pattern.pattern_id: related_pattern}

        updates = [
            {"id": "related001", "new_tags": ["evolved"], "rationale": "test evolution"}
        ]

        evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_patterns=all_patterns,
            triggering_pattern_id="trigger001",
        )

        assert related_pattern.last_evolved is not None
        assert "trigger001" in related_pattern.evolved_by
        assert len(related_pattern.evolution_history) == 1
        assert "test evolution" in related_pattern.evolution_history[0]["changes"]

    def test_skips_nonexistent_patterns(self, evolution):
        """Updates for non-existent patterns are skipped."""
        all_patterns = {}

        updates = [
            {"id": "nonexistent", "new_tags": ["wont-apply"], "rationale": "testing"}
        ]

        modified = evolution.apply_neighbor_updates(
            neighbor_updates=updates,
            all_patterns=all_patterns,
            triggering_pattern_id="trigger001",
        )

        assert modified == []


# =============================================================================
# PatternStore Evolution Integration Tests
# =============================================================================

class TestPatternStoreEvolution:
    """Integration tests for PatternStore with evolution."""

    def test_evolution_disabled_no_links(self, store_no_evolution, base_pattern, related_pattern):
        """With evolution disabled, no links are created."""
        store_no_evolution.add(related_pattern)
        store_no_evolution.add(base_pattern)

        # No links should be created
        assert base_pattern.links == []
        assert related_pattern.links == []

    def test_first_pattern_no_evolution(self, store_with_evolution, base_pattern):
        """First pattern doesn't trigger evolution (no candidates)."""
        with patch.object(store_with_evolution.evolution, "decide_links") as mock_decide:
            store_with_evolution.add(base_pattern)

            # decide_links should not be called for first pattern
            mock_decide.assert_not_called()

    def test_skip_evolution_flag(self, store_with_evolution, base_pattern, related_pattern):
        """skip_evolution=True prevents evolution."""
        store_with_evolution.add(related_pattern)

        with patch.object(store_with_evolution.evolution, "decide_links") as mock_decide:
            store_with_evolution.add(base_pattern, skip_evolution=True)

            mock_decide.assert_not_called()

    def test_full_evolution_flow(self, store_with_evolution, base_pattern, related_pattern):
        """Full evolution flow with mocked DSPy."""
        # Add first pattern (no evolution)
        store_with_evolution.add(related_pattern)

        # Mock DSPy for second pattern
        mock_link_result = Mock()
        mock_link_result.links_to_create = ["related001"]
        mock_link_result.link_rationales = ["Same domain"]
        mock_link_result.updated_tags = base_pattern.tags + ["linked"]

        mock_evolve_result = Mock()
        mock_evolve_result.should_evolve = True
        mock_evolve_result.neighbor_updates = [
            {"id": "related001", "new_tags": ["evolved"], "context_addition": "", "rationale": "updated"}
        ]

        with patch.object(store_with_evolution.evolution, "_linker", Mock(return_value=mock_link_result)):
            with patch.object(store_with_evolution.evolution, "_evolver", Mock(return_value=mock_evolve_result)):
                result = store_with_evolution.add(base_pattern)

                # Base pattern should have link
                assert "related001" in result.links
                assert "linked" in result.tags

                # Related pattern should have reverse link and be evolved
                related = store_with_evolution.get("related001")
                assert "base001" in related.links
                assert "evolved" in related.tags

    def test_stats_includes_evolution(self, store_with_evolution, base_pattern, related_pattern):
        """Stats include evolution metrics."""
        store_with_evolution.add(related_pattern)

        # Manually simulate evolution
        base_pattern.links = ["related001"]
        related_pattern.links = ["base001"]
        related_pattern.evolved_by = ["base001"]
        store_with_evolution.patterns["base001"] = base_pattern
        store_with_evolution.patterns["related001"] = related_pattern

        stats = store_with_evolution.stats()

        assert stats["evolution_enabled"] is True
        assert stats["linked_patterns"] == 2
        assert stats["evolved_patterns"] == 1
        assert stats["total_links"] == 1  # Bidirectional counted once

    def test_manual_evolve_pattern(self, store_with_evolution, base_pattern, related_pattern):
        """evolve_pattern() manually triggers evolution."""
        store_with_evolution.add(related_pattern, skip_evolution=True)
        store_with_evolution.add(base_pattern, skip_evolution=True)

        # Mock DSPy for manual evolution
        mock_link_result = Mock()
        mock_link_result.links_to_create = ["related001"]
        mock_link_result.link_rationales = ["Same domain"]
        mock_link_result.updated_tags = base_pattern.tags

        mock_evolve_result = Mock()
        mock_evolve_result.should_evolve = False
        mock_evolve_result.neighbor_updates = []

        with patch.object(store_with_evolution.evolution, "_linker", Mock(return_value=mock_link_result)):
            with patch.object(store_with_evolution.evolution, "_evolver", Mock(return_value=mock_evolve_result)):
                updated, evolved = store_with_evolution.evolve_pattern("base001")

                assert "related001" in updated.links

    def test_repr_shows_evolution_status(self, store_with_evolution, store_no_evolution):
        """__repr__ shows evolution status."""
        assert "evolution=on" in repr(store_with_evolution)
        assert "evolution=off" in repr(store_no_evolution)


# =============================================================================
# Singleton Tests
# =============================================================================

class TestGetPatternEvolution:
    """Tests for the singleton accessor."""

    def test_returns_same_instance(self):
        """get_pattern_evolution returns the same instance."""
        # Reset singleton
        import rook.learning.pattern_evolution as pe_module
        pe_module._evolution_instance = None

        e1 = get_pattern_evolution()
        e2 = get_pattern_evolution()

        assert e1 is e2

    def test_lazy_loads_dspy_modules(self, evolution):
        """DSPy modules are lazy-loaded."""
        # Before access, _linker should be None
        assert evolution._linker is None
        assert evolution._evolver is None

        # Access triggers load (will fail without DSPy config, but that's ok)
        # We just check the property exists
        with patch("rook.learning.pattern_evolution.PatternLinker") as mock_linker:
            mock_linker.return_value = Mock()
            _ = evolution.linker
            mock_linker.assert_called_once()
