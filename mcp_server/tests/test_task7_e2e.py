"""
Task 7: Testing & Polish - End-to-End Pattern Memory Test

Tests the complete pattern memory flow:
1. Create seed pattern manually
2. Add related pattern, verify evolution
3. Query patterns by intent/symptom
4. Record usage, verify confidence updates
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestTask7EndToEnd:
    """End-to-end tests for Phase 2 Pattern Memory."""

    @pytest.fixture
    def temp_storage(self):
        """Create isolated temporary storage."""
        tmpdir = Path(tempfile.mkdtemp())
        patterns_dir = tmpdir / "patterns"
        index_path = tmpdir / "pattern_index.json"
        patterns_dir.mkdir(parents=True, exist_ok=True)

        # Patch the module-level paths
        import rook.learning.pattern_store as ps

        original_knowledge_dir = ps.KNOWLEDGE_DIR
        original_patterns_dir = ps.PATTERNS_DIR
        original_index_path = ps.INDEX_PATH

        ps.KNOWLEDGE_DIR = tmpdir
        ps.PATTERNS_DIR = patterns_dir
        ps.INDEX_PATH = index_path

        yield {
            "tmpdir": tmpdir,
            "patterns_dir": patterns_dir,
            "index_path": index_path,
        }

        # Restore and cleanup
        ps.KNOWLEDGE_DIR = original_knowledge_dir
        ps.PATTERNS_DIR = original_patterns_dir
        ps.INDEX_PATH = original_index_path
        shutil.rmtree(tmpdir)

    def test_step1_create_seed_pattern(self, temp_storage):
        """Step 1: Create seed pattern manually."""
        from rook.learning.pattern_memory import PatternNote
        from rook.learning.pattern_store import PatternStore

        store = PatternStore(auto_save=True, enable_evolution=False)

        seed_pattern = PatternNote(
            name="Concentric Circle Arc Extraction",
            solution_brief="Scale domain by radius: domain_end = angle * radius",
            solution_principle="GH circles use arc-length parameterization (0 to 2*pi*R), not angular.",
            trigger_intents=["wedge shape from circles", "pie slice", "arc extraction"],
            trigger_symptoms=["same domain different angles", "microscopic slider changes"],
            tags=["domain-math", "curves", "parameterization", "concentric"],
            components_needed=["Circle", "Construct Domain", "SubCurve", "Multiplication"],
            anti_patterns=[
                {
                    "mistake": "Using same domain for both circles",
                    "symptom": "Inner and outer arcs span different angles",
                    "why_wrong": "Arc-length parameterization means same domain != same angle",
                }
            ],
            preconditions=["Circles must be concentric", "Circles must be in same plane"],
        )

        result = store.add(seed_pattern, skip_evolution=True)

        # Verify
        assert result.pattern_id == seed_pattern.pattern_id
        assert store.exists(seed_pattern.pattern_id)
        assert (temp_storage["patterns_dir"] / f"{seed_pattern.pattern_id}.json").exists()

        stats = store.stats()
        assert stats["total_patterns"] == 1

    def test_step2_add_related_pattern_with_evolution(self, temp_storage):
        """Step 2: Add related pattern, verify evolution links."""
        from rook.learning.pattern_memory import PatternNote
        from rook.learning.pattern_store import PatternStore

        # Create store with evolution disabled initially
        store = PatternStore(auto_save=True, enable_evolution=False)

        # Add seed pattern
        seed = PatternNote(
            name="Domain Scaling Pattern",
            solution_brief="Scale domains proportionally to geometry size",
            trigger_intents=["domain scaling", "proportional domains"],
            trigger_symptoms=["domain mismatch"],
            tags=["domain-math", "parameterization"],
            components_needed=["Construct Domain", "Multiplication"],
        )
        store.add(seed, skip_evolution=True)

        # Now enable evolution and add related pattern
        store.enable_evolution = True

        # Mock DSPy modules to avoid API calls
        mock_linker = MagicMock()
        mock_linker.return_value = MagicMock(
            links_to_create=[seed.pattern_id],
            link_rationales=["Both deal with domain math"],
            updated_tags=["domain-math", "parameterization", "curves"],
        )

        mock_evolver = MagicMock()
        mock_evolver.return_value = MagicMock(
            should_evolve=True,
            neighbor_updates=[
                {
                    "id": seed.pattern_id,
                    "new_tags": ["related-to-curves"],
                    "context_addition": "Also applies to curve operations",
                    "rationale": "Extended context from new pattern",
                }
            ],
            evolution_summary="Updated neighbor with curve context",
        )

        # Patch the evolution module
        with patch.object(store.evolution, "_linker", mock_linker):
            with patch.object(store.evolution, "_evolver", mock_evolver):
                related = PatternNote(
                    name="Arc Length Parameterization",
                    solution_brief="Understand arc-length vs angular parameterization",
                    trigger_intents=["arc parameterization", "curve domains"],
                    trigger_symptoms=["unexpected arc lengths"],
                    tags=["domain-math", "curves"],
                    components_needed=["SubCurve", "Evaluate Curve"],
                )
                result = store.add(related, skip_evolution=False)

        # Verify linking occurred
        assert seed.pattern_id in result.links, "New pattern should link to seed"

        # Verify neighbor evolution
        evolved_seed = store.get(seed.pattern_id)
        assert "related-to-curves" in evolved_seed.tags, "Seed should have new tag from evolution"
        assert result.pattern_id in evolved_seed.evolved_by, "Seed should track what evolved it"

        stats = store.stats()
        assert stats["total_patterns"] == 2
        assert stats["total_links"] >= 1

    def test_step3_query_by_intent_and_symptom(self, temp_storage):
        """Step 3: Query patterns by intent/symptom."""
        from rook.learning.pattern_memory import PatternNote
        from rook.learning.pattern_store import PatternStore

        store = PatternStore(auto_save=True, enable_evolution=False)

        # Add multiple patterns
        p1 = PatternNote(
            name="Circle Domain Pattern",
            solution_brief="Handle circle domains correctly",
            trigger_intents=["circle domain", "arc from circle"],
            trigger_symptoms=["wrong arc angle", "domain mismatch"],
            tags=["circles", "domain-math"],
        )
        p2 = PatternNote(
            name="Loft Direction Pattern",
            solution_brief="Ensure consistent curve direction for lofts",
            trigger_intents=["loft surface", "surface from curves"],
            trigger_symptoms=["twisted loft", "surface flip"],
            tags=["surfaces", "loft"],
        )
        p3 = PatternNote(
            name="Curve Parameterization Pattern",
            solution_brief="Understand curve parameterization",
            trigger_intents=["curve domain", "evaluate curve"],
            trigger_symptoms=["wrong point on curve", "domain mismatch"],
            tags=["curves", "domain-math"],
        )

        store.add(p1, skip_evolution=True)
        store.add(p2, skip_evolution=True)
        store.add(p3, skip_evolution=True)

        # Query by intent
        results = store.search(intent="circle domain")
        assert len(results) >= 1
        assert any(p.name == "Circle Domain Pattern" for p in results)

        # Query by symptom
        results = store.search(symptoms=["domain mismatch"])
        assert len(results) >= 2  # p1 and p3 both have this symptom

        # Query by tag
        results = store.search(tags=["domain-math"])
        assert len(results) >= 2  # p1 and p3

        # Query by component
        results = store.search(components=["SubCurve"])
        # May not match since we didn't add components_needed

    def test_step4_record_usage_and_confidence(self, temp_storage):
        """Step 4: Record usage, verify confidence updates."""
        from rook.learning.pattern_memory import PatternNote
        from rook.learning.pattern_store import PatternStore

        store = PatternStore(auto_save=True, enable_evolution=False)

        pattern = PatternNote(
            name="Test Confidence Pattern",
            solution_brief="Test confidence tracking",
            trigger_intents=["test"],
            tags=["test"],
        )
        store.add(pattern, skip_evolution=True)

        # Initial state
        assert pattern.times_used == 0
        assert pattern.times_succeeded == 0
        assert pattern.success_rate() == 0.5  # Neutral prior

        # Record successful use
        updated = store.record_use(pattern.pattern_id, success=True, session_id="test_session_1")
        assert updated.times_used == 1
        assert updated.times_succeeded == 1
        assert updated.success_rate() == 1.0
        assert updated.last_used is not None
        assert updated.last_verified is not None
        assert len(updated.citations) == 1
        assert updated.citations[0]["session_id"] == "test_session_1"

        # Record failed use
        updated = store.record_use(pattern.pattern_id, success=False, session_id="test_session_2")
        assert updated.times_used == 2
        assert updated.times_succeeded == 1
        assert updated.success_rate() == 0.5

        # Record another success
        updated = store.record_use(pattern.pattern_id, success=True)
        assert updated.times_used == 3
        assert updated.times_succeeded == 2
        assert abs(updated.success_rate() - 0.667) < 0.01

    def test_step5_persistence_and_reload(self, temp_storage):
        """Step 5: Verify patterns persist and reload correctly."""
        from rook.learning.pattern_memory import PatternNote
        from rook.learning.pattern_store import PatternStore

        # Create and populate store
        store1 = PatternStore(auto_save=True, enable_evolution=False)

        p1 = PatternNote(
            name="Persistence Test Pattern",
            solution_brief="Test persistence",
            trigger_intents=["persistence test"],
            trigger_symptoms=["data lost"],
            tags=["test", "persistence"],
            components_needed=["TestComponent"],
        )
        store1.add(p1, skip_evolution=True)
        store1.record_use(p1.pattern_id, success=True, session_id="persist_test")

        pattern_id = p1.pattern_id

        # Create new store instance (simulates restart)
        store2 = PatternStore(auto_save=True, enable_evolution=False)

        # Verify pattern loaded
        assert store2.exists(pattern_id)
        loaded = store2.get(pattern_id)

        assert loaded.name == "Persistence Test Pattern"
        assert loaded.times_used == 1
        assert loaded.times_succeeded == 1
        assert len(loaded.citations) == 1
        assert "test" in loaded.tags
        assert "persistence" in loaded.tags

        # Verify index rebuilt correctly
        results = store2.search(symptoms=["data lost"])
        assert len(results) == 1
        assert results[0].pattern_id == pattern_id

    def test_full_workflow(self, temp_storage):
        """Complete workflow test combining all steps."""
        from rook.learning.pattern_memory import PatternNote
        from rook.learning.pattern_store import PatternStore

        # Step 1: Create store and seed pattern
        store = PatternStore(auto_save=True, enable_evolution=False)

        seed = PatternNote(
            name="Wedge Shape Pattern",
            solution_brief="Create wedges by scaling domains to radii",
            trigger_intents=["wedge shape", "pie chart segment"],
            trigger_symptoms=["unequal angles", "distorted wedge"],
            tags=["geometry", "domain-math", "circles"],
            components_needed=["Circle", "SubCurve", "Loft"],
            anti_patterns=[{"mistake": "Fixed domain", "symptom": "Wrong angles", "why_wrong": "Arc-length param"}],
            preconditions=["Concentric circles required"],
        )
        store.add(seed, skip_evolution=True)

        # Step 2: Query to find the pattern
        results = store.search(intent="wedge shape")
        assert len(results) == 1
        found = results[0]
        assert found.pattern_id == seed.pattern_id

        # Step 3: Record usage (success)
        store.record_use(seed.pattern_id, success=True, session_id="workflow_test")

        # Step 4: Verify confidence updated
        updated = store.get(seed.pattern_id)
        assert updated.times_used == 1
        assert updated.success_rate() == 1.0

        # Step 5: Create new store, verify persistence
        store2 = PatternStore(auto_save=True, enable_evolution=False)
        reloaded = store2.get(seed.pattern_id)
        assert reloaded.times_used == 1
        assert reloaded.name == "Wedge Shape Pattern"

        print("\n✓ Full workflow test passed!")
