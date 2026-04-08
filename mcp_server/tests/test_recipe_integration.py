"""Integration tests for Recipe Learning System.

Tests the full workflow: extract -> save -> search.

This tests the complete integration path without needing a live Rhino/GH connection:
- extract_recipe analyzes canvas state
- PatternNote stores the extracted recipe
- PatternStore indexes and searches recipes
- pattern_type filtering separates recipes from struggles
"""

import pytest
from rook.learning.recipe_extraction import extract_recipe, DraftRecipe
from rook.learning.pattern_memory import PatternNote
from rook.learning.pattern_store import PatternStore


class TestRecipeWorkflow:
    """End-to-end recipe extraction and storage workflow."""

    @pytest.fixture
    def temp_store(self, tmp_path, monkeypatch):
        """Create a temporary pattern store with isolated storage."""
        knowledge_dir = tmp_path / "knowledge" / "gh"
        patterns_dir = knowledge_dir / "patterns"
        patterns_dir.mkdir(parents=True)

        # Patch storage paths
        monkeypatch.setattr("rook.learning.pattern_store.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("rook.learning.pattern_store.PATTERNS_DIR", patterns_dir)
        monkeypatch.setattr("rook.learning.pattern_store.INDEX_PATH", knowledge_dir / "pattern_index.json")

        store = PatternStore(auto_save=False, enable_evolution=False, verify_on_search=False)
        return store

    def test_extract_and_save_recipe(self, temp_store):
        """Full workflow: extract -> review -> save -> search."""
        # 1. Simulate canvas state (like from gh_query)
        canvas_state = {
            "objects": [
                {"guid": "s1", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "s2", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "series1", "name": "Series", "type": "Component_Series"},
                {"guid": "sin1", "name": "Sine", "type": "FuncSin"},
                {"guid": "pt1", "name": "Construct Point", "type": "Component_ConstructPoint"},
                {"guid": "interp1", "name": "Interpolate", "type": "Component_InterpCurve"},
                {"guid": "pipe1", "name": "Pipe", "type": "Component_PipeSurface"},
            ]
        }
        connections_data = {
            "series1": {"inputs": [{"name": "Step", "sources": [{"guid": "s1"}]}]},
            "sin1": {"inputs": [{"name": "Value", "sources": [{"guid": "series1"}]}]},
            "pt1": {"inputs": [{"name": "Y", "sources": [{"guid": "sin1"}]}]},
            "interp1": {"inputs": [{"name": "Vertices", "sources": [{"guid": "pt1"}]}]},
            "pipe1": {"inputs": [{"name": "Curve", "sources": [{"guid": "interp1"}]}]},
        }

        # 2. Extract recipe
        draft = extract_recipe(canvas_state, connections_data, use_dspy=False)

        assert isinstance(draft, DraftRecipe)
        assert "trigonometric" in draft.detected_tags
        assert draft.output_type == "brep"

        # 3. Create PatternNote from draft (simulating gh_save_recipe)
        pattern = PatternNote(
            name=draft.suggested_name,
            pattern_type="recipe",
            solution_brief=draft.description,
            components_needed=[c["name"] for c in draft.components],
            trigger_intents=draft.suggested_intents + ["helix pipe", "sine wave tube"],
            tags=draft.detected_tags,
            wiring=draft.wiring,
            input_structure=draft.input_structure,
            output_type=draft.output_type,
            created_from="recipe_extraction",
        )

        # 4. Save to store
        temp_store.add(pattern, skip_evolution=True)

        # 5. Search should find it
        results = temp_store.search(intent="helix pipe", pattern_type="recipe")

        assert len(results) >= 1
        found = results[0]
        assert found.pattern_type == "recipe"
        assert found.output_type == "brep"
        assert "trigonometric" in found.tags

    def test_recipes_separate_from_struggles(self, temp_store):
        """Recipe and struggle patterns can be filtered separately."""
        # Add a struggle pattern
        struggle = PatternNote(
            name="radians_gotcha",
            pattern_type="struggle",
            solution_brief="Use Radians component to convert degrees",
            trigger_symptoms=["angles wrong", "trig functions unexpected"],
            tags=["trigonometric", "conversion"],
        )
        temp_store.add(struggle, skip_evolution=True)

        # Add a recipe pattern
        recipe = PatternNote(
            name="sine_wave",
            pattern_type="recipe",
            solution_brief="Create sine wave curve",
            trigger_intents=["sine wave", "oscillating curve"],
            tags=["trigonometric", "curve"],
        )
        temp_store.add(recipe, skip_evolution=True)

        # Search for trigonometric - finds both
        all_results = temp_store.search(tags=["trigonometric"], pattern_type="all")
        assert len(all_results) == 2

        # Filter to recipes only
        recipe_results = temp_store.search(tags=["trigonometric"], pattern_type="recipe")
        assert len(recipe_results) == 1
        assert recipe_results[0].name == "sine_wave"

        # Filter to struggles only
        struggle_results = temp_store.search(tags=["trigonometric"], pattern_type="struggle")
        assert len(struggle_results) == 1
        assert struggle_results[0].name == "radians_gotcha"

    def test_recipe_wiring_preserved(self, temp_store):
        """Wiring connections are preserved through save/load cycle."""
        # Create recipe with specific wiring
        wiring = [
            {"from": "s1", "from_param": "output", "to": "sphere1", "to_param": "R"},
            {"from": "sphere1", "from_param": "S", "to": "preview1", "to_param": "G"},
        ]
        recipe = PatternNote(
            name="wired_sphere",
            pattern_type="recipe",
            solution_brief="Sphere with radius slider",
            trigger_intents=["parametric sphere"],
            wiring=wiring,
            output_type="surface",
        )

        temp_store.add(recipe, skip_evolution=True)

        # Retrieve and check wiring
        found = temp_store.get(recipe.pattern_id)
        assert found is not None
        assert len(found.wiring) == 2
        assert found.wiring[0]["from"] == "s1"
        assert found.wiring[1]["to_param"] == "G"

    def test_recipe_input_structure_preserved(self, temp_store):
        """Input structure with semantic roles is preserved."""
        input_structure = {
            "sliders": [
                {"guid": "s1", "role": "radius", "connected_to": "Sphere", "param": "R"},
                {"guid": "s2", "role": "count", "connected_to": "Series", "param": "N"},
            ],
            "panels": [
                {"guid": "p1", "role": "text", "connected_to": "Panel", "param": None},
            ],
        }
        recipe = PatternNote(
            name="multi_input_recipe",
            pattern_type="recipe",
            solution_brief="Recipe with multiple inputs",
            trigger_intents=["parametric array"],
            input_structure=input_structure,
            output_type="brep",
        )

        temp_store.add(recipe, skip_evolution=True)

        found = temp_store.get(recipe.pattern_id)
        assert len(found.input_structure["sliders"]) == 2
        assert found.input_structure["sliders"][0]["role"] == "radius"
        assert found.input_structure["sliders"][1]["role"] == "count"
        assert len(found.input_structure["panels"]) == 1

    def test_search_by_components(self, temp_store):
        """Can search for recipes by component names."""
        recipe1 = PatternNote(
            name="sphere_recipe",
            pattern_type="recipe",
            solution_brief="Create a sphere",
            trigger_intents=["sphere"],
            components_needed=["Sphere", "Number Slider"],
        )
        recipe2 = PatternNote(
            name="box_recipe",
            pattern_type="recipe",
            solution_brief="Create a box",
            trigger_intents=["box"],
            components_needed=["Box", "Number Slider"],
        )

        temp_store.add(recipe1, skip_evolution=True)
        temp_store.add(recipe2, skip_evolution=True)

        # Search by component
        sphere_results = temp_store.search(components=["Sphere"], pattern_type="recipe")
        assert len(sphere_results) == 1
        assert sphere_results[0].name == "sphere_recipe"

        # Slider appears in both
        slider_results = temp_store.search(components=["Number Slider"], pattern_type="recipe")
        assert len(slider_results) == 2

    def test_recipe_serialization_roundtrip(self, temp_store, tmp_path):
        """Recipe pattern survives save/load cycle through JSON."""
        recipe = PatternNote(
            name="full_recipe",
            pattern_type="recipe",
            solution_brief="Complete recipe test",
            solution_principle="Tests all recipe fields survive serialization",
            trigger_intents=["full test", "serialization test"],
            components_needed=["Sphere", "Pipe", "Loft"],
            tags=["test", "serialization"],
            wiring=[{"from": "a", "to": "b", "to_param": "R"}],
            input_structure={"sliders": [{"guid": "s1", "role": "radius"}]},
            output_type="brep",
            source_definition="test.ghx",
        )

        # Add and save
        temp_store.add(recipe, skip_evolution=True)
        temp_store.save()

        # Create new store from same location (simulates restart)
        new_store = PatternStore(auto_save=False, enable_evolution=False, verify_on_search=False)

        # Find the recipe
        found = new_store.get(recipe.pattern_id)
        assert found is not None
        assert found.pattern_type == "recipe"
        assert found.name == "full_recipe"
        assert found.solution_brief == "Complete recipe test"
        assert found.output_type == "brep"
        assert found.source_definition == "test.ghx"
        assert len(found.wiring) == 1
        assert len(found.input_structure["sliders"]) == 1
        assert "Sphere" in found.components_needed


class TestDraftToPatternConversion:
    """Tests for converting DraftRecipe to PatternNote."""

    def test_draft_fields_map_to_pattern(self):
        """DraftRecipe fields correctly map to PatternNote."""
        draft = DraftRecipe(
            draft_id="draft_test123",
            components=[
                {"guid": "a", "name": "Sphere", "type": "Component_Sphere"},
            ],
            wiring=[{"from": "s1", "to": "a", "to_param": "R"}],
            input_structure={"sliders": [{"guid": "s1", "role": "radius"}]},
            output_type="surface",
            suggested_name="simple_sphere",
            detected_tags=["primitives"],
            suggested_intents=["create sphere"],
            description="A simple sphere recipe",
            source_definition="sphere.ghx",
        )

        # Convert to PatternNote (as gh_save_recipe would)
        pattern = PatternNote(
            name=draft.suggested_name,
            pattern_type="recipe",
            solution_brief=draft.description,
            components_needed=[c["name"] for c in draft.components],
            trigger_intents=draft.suggested_intents,
            tags=draft.detected_tags,
            wiring=draft.wiring,
            input_structure=draft.input_structure,
            output_type=draft.output_type,
            source_definition=draft.source_definition,
            created_from="recipe_extraction",
        )

        assert pattern.name == "simple_sphere"
        assert pattern.pattern_type == "recipe"
        assert pattern.solution_brief == "A simple sphere recipe"
        assert "Sphere" in pattern.components_needed
        assert pattern.output_type == "surface"
        assert pattern.source_definition == "sphere.ghx"
        assert pattern.created_from == "recipe_extraction"

    def test_empty_draft_produces_valid_pattern(self):
        """Empty draft can still produce a valid PatternNote."""
        draft = DraftRecipe(
            draft_id="draft_empty",
            components=[],
            wiring=[],
            input_structure={},
            output_type="unknown",
        )

        pattern = PatternNote(
            name=draft.suggested_name or "unnamed_recipe",
            pattern_type="recipe",
            solution_brief=draft.description or "No description",
            components_needed=[],
            trigger_intents=draft.suggested_intents,
            tags=draft.detected_tags,
            wiring=draft.wiring,
            input_structure=draft.input_structure,
            output_type=draft.output_type,
        )

        assert pattern.name == "unnamed_recipe"
        assert pattern.pattern_type == "recipe"
        assert pattern.output_type == "unknown"
