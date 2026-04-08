"""Tests for Recipe Classification (DSPy-based)."""

import pytest
from rook.learning.recipe_classification import (
    RecipeClassifier,
    classify_recipe_heuristic,
)


class TestHeuristicClassification:
    """Tests for heuristic (non-DSPy) classification fallback."""

    def test_detect_trigonometric_pattern(self):
        """Components with Sin/Cos detected as trigonometric."""
        components = ["Number Slider", "Series", "Radians", "Sine", "Cosine", "Remap Numbers"]

        result = classify_recipe_heuristic(components)

        assert "trigonometric" in result["tags"]

    def test_detect_parametric_pattern(self):
        """Multiple sliders indicate parametric pattern."""
        components = ["Number Slider", "Number Slider", "Number Slider", "Sphere"]

        result = classify_recipe_heuristic(components)

        assert "parametric" in result["tags"]

    def test_detect_pipe_output(self):
        """Pipe component indicates pipe-output pattern."""
        components = ["Circle", "Pipe"]

        result = classify_recipe_heuristic(components)

        assert "pipe-output" in result["tags"]

    def test_detect_surface_pattern(self):
        """Loft/Sweep components indicate surface creation."""
        components = ["Circle", "Circle", "Loft"]

        result = classify_recipe_heuristic(components)

        assert "surface-creation" in result["tags"]

    def test_detect_point_sequence(self):
        """Series + Construct Point indicates point sequence."""
        components = ["Series", "Construct Point", "Interpolate"]

        result = classify_recipe_heuristic(components)

        assert "point-sequence" in result["tags"]

    def test_suggest_name_from_components(self):
        """Suggested name combines detected patterns."""
        components = ["Series", "Radians", "Sine", "Construct Point", "Pipe"]

        result = classify_recipe_heuristic(components)

        # Should combine patterns into a name
        assert result["suggested_name"]  # Non-empty
        assert isinstance(result["suggested_name"], str)

    def test_suggest_intents(self):
        """Generates suggested intent phrases."""
        components = ["Number Slider", "Sphere"]

        result = classify_recipe_heuristic(components)

        assert len(result["intents"]) > 0
        assert any("sphere" in i.lower() for i in result["intents"])
