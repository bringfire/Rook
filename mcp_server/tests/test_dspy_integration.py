"""
Real DSPy Integration Tests for Phase 2 Pattern Memory.

These tests make actual LLM API calls - requires ANTHROPIC_API_KEY in .env.
Run with: pytest tests/test_dspy_integration.py -v -s
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Load environment from various possible locations
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent.parent / "autonomous_dev" / ".env")

# Check if API key is available
API_KEY_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not API_KEY_AVAILABLE, reason="ANTHROPIC_API_KEY not set")
class TestRealDSPyIntegration:
    """Tests that make real DSPy/LLM calls."""

    @pytest.fixture
    def temp_storage(self):
        """Create isolated temporary storage."""
        tmpdir = Path(tempfile.mkdtemp())
        patterns_dir = tmpdir / "patterns"
        index_path = tmpdir / "pattern_index.json"
        patterns_dir.mkdir(parents=True, exist_ok=True)

        import rook.learning.pattern_store as ps

        original_knowledge_dir = ps.KNOWLEDGE_DIR
        original_patterns_dir = ps.PATTERNS_DIR
        original_index_path = ps.INDEX_PATH

        ps.KNOWLEDGE_DIR = tmpdir
        ps.PATTERNS_DIR = patterns_dir
        ps.INDEX_PATH = index_path

        yield {"tmpdir": tmpdir, "patterns_dir": patterns_dir}

        ps.KNOWLEDGE_DIR = original_knowledge_dir
        ps.PATTERNS_DIR = original_patterns_dir
        ps.INDEX_PATH = original_index_path
        shutil.rmtree(tmpdir)

    def test_pattern_metadata_extraction(self, temp_storage):
        """Test real DSPy metadata extraction."""
        from rook.learning.dspy_modules import PatternMetadataExtractor

        # Configure DSPy
        from rook.learning.dspy_config import configure_dspy, is_configured
        if not is_configured():
            configure_dspy()

        extractor = PatternMetadataExtractor()

        result = extractor(
            solution_description="""
            When extracting arcs from concentric circles in Grasshopper, you must scale
            the domain by the radius. GH circles use arc-length parameterization (0 to 2πR),
            not angular parameterization (0 to 2π). So the same domain value on circles
            with different radii produces different angles. To get equal angles, multiply
            the domain end by the radius.
            """,
            session_context="Working on a spiral staircase tread design",
            components_involved=["Circle", "Construct Domain", "SubCurve", "Multiplication"],
        )

        print(f"\n--- Metadata Extraction Result ---")
        print(f"Solution brief: {result.solution_brief}")
        print(f"Solution principle: {result.solution_principle}")
        print(f"Trigger intents: {result.trigger_intents}")
        print(f"Trigger symptoms: {result.trigger_symptoms}")
        print(f"Tags: {result.tags}")
        print(f"Preconditions: {result.preconditions}")

        # Verify we got meaningful results
        assert result.solution_brief, "Should extract a solution brief"
        assert result.trigger_intents, "Should extract trigger intents"
        assert result.tags, "Should extract tags"

    def test_pattern_linker(self, temp_storage):
        """Test real DSPy link decision."""
        from rook.learning.dspy_modules import PatternLinker
        from rook.learning.dspy_config import configure_dspy, is_configured

        if not is_configured():
            configure_dspy()

        linker = PatternLinker()

        result = linker(
            new_pattern_summary="Arc extraction from circles requires scaling domain by radius due to arc-length parameterization",
            new_pattern_tags=["domain-math", "circles", "parameterization"],
            candidate_patterns=[
                {
                    "id": "p1",
                    "name": "Curve Domain Basics",
                    "brief": "Understanding curve domains in Grasshopper",
                    "tags": ["domain-math", "curves", "basics"],
                },
                {
                    "id": "p2",
                    "name": "Loft Surface Creation",
                    "brief": "Creating surfaces by lofting through curves",
                    "tags": ["surfaces", "loft"],
                },
                {
                    "id": "p3",
                    "name": "Circle Parameterization",
                    "brief": "How circles are parameterized in Grasshopper",
                    "tags": ["circles", "parameterization"],
                },
            ],
        )

        print(f"\n--- Link Decision Result ---")
        print(f"Links to create: {result.links_to_create}")
        print(f"Link rationales: {result.link_rationales}")
        print(f"Updated tags: {result.updated_tags}")

        # Should link to related patterns (p1 and p3 are most relevant)
        assert isinstance(result.links_to_create, list), "Should return list of links"

    def test_neighbor_evolver(self, temp_storage):
        """Test real DSPy neighbor evolution."""
        from rook.learning.dspy_modules import NeighborEvolver
        from rook.learning.dspy_config import configure_dspy, is_configured

        if not is_configured():
            configure_dspy()

        evolver = NeighborEvolver()

        result = evolver(
            new_pattern={
                "id": "new1",
                "name": "Arc Length Domain Scaling",
                "brief": "Scale domain by radius for arc extraction",
                "principle": "Arc-length parameterization means domain = angle * radius",
                "tags": ["domain-math", "circles", "arc-length"],
            },
            neighbor_patterns=[
                {
                    "id": "n1",
                    "name": "Curve Domain Basics",
                    "brief": "Understanding curve domains",
                    "tags": ["domain-math", "curves"],
                    "context": "Domains map 0-1 to curve length",
                },
            ],
        )

        print(f"\n--- Neighbor Evolution Result ---")
        print(f"Should evolve: {result.should_evolve}")
        print(f"Neighbor updates: {result.neighbor_updates}")
        print(f"Evolution summary: {result.evolution_summary}")

        assert isinstance(result.should_evolve, bool), "Should return boolean"
        assert isinstance(result.neighbor_updates, list), "Should return list of updates"

    def test_full_evolution_with_real_dspy(self, temp_storage):
        """Test complete evolution flow with real DSPy calls."""
        from rook.learning.pattern_memory import PatternNote
        from rook.learning.pattern_store import PatternStore
        from rook.learning.dspy_config import configure_dspy, is_configured

        if not is_configured():
            configure_dspy()

        # Create store with evolution ENABLED
        store = PatternStore(auto_save=True, enable_evolution=True)

        # Add seed pattern (no evolution for first)
        seed = PatternNote(
            name="Curve Domain Fundamentals",
            solution_brief="Curve domains map parameter space to curve geometry",
            solution_principle="In GH, curves are parameterized from 0 to their length or a normalized 0-1 range.",
            trigger_intents=["curve domain", "parameter space", "evaluate curve"],
            trigger_symptoms=["wrong point on curve", "unexpected evaluation"],
            tags=["domain-math", "curves", "fundamentals"],
            components_needed=["Evaluate Curve", "Curve Domain"],
        )
        store.add(seed, skip_evolution=True)
        print(f"\n--- Added seed pattern: {seed.pattern_id} ---")

        # Add related pattern WITH evolution
        related = PatternNote(
            name="Circle Arc-Length Parameterization",
            solution_brief="Circles use arc-length (0 to 2πR) not angular (0 to 2π) parameterization",
            solution_principle="Same domain on different radius circles = different angles. Scale domain by radius.",
            trigger_intents=["circle arc", "arc extraction", "wedge shape"],
            trigger_symptoms=["unequal angles", "microscopic changes", "wrong arc span"],
            tags=["domain-math", "circles", "arc-length"],
            components_needed=["Circle", "SubCurve", "Construct Domain"],
        )

        print(f"\n--- Adding related pattern with evolution ---")
        result = store.add(related, skip_evolution=False)

        print(f"\n--- Evolution Results ---")
        print(f"New pattern links: {result.links}")
        print(f"New pattern tags: {result.tags}")

        # Check if seed was evolved
        evolved_seed = store.get(seed.pattern_id)
        print(f"Seed evolved_by: {evolved_seed.evolved_by}")
        print(f"Seed tags after evolution: {evolved_seed.tags}")
        print(f"Seed evolution_history: {evolved_seed.evolution_history}")

        # Verify something happened
        stats = store.stats()
        print(f"\n--- Store Stats ---")
        print(f"Total patterns: {stats['total_patterns']}")
        print(f"Total links: {stats['total_links']}")
        print(f"Evolved patterns: {stats['evolved_patterns']}")


if __name__ == "__main__":
    # Run with verbose output
    pytest.main([__file__, "-v", "-s"])
