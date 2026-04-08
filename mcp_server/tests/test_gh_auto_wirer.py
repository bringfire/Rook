"""Tests for GH auto-wiring logic.

Tests for knowledge-based auto-wiring heuristics:
- Output type detection from component info
- Type-based parameter matching
- Wiring plan generation
"""

import pytest
from rook.learning.gh_auto_wirer import GHAutoWirer


class TestDetermineOutputType:
    """Tests for determine_output_type method."""

    def test_determine_output_type_slider(self):
        """Number Slider provides Number type."""
        wirer = GHAutoWirer()
        comp = {"name": "Number Slider", "component_guid": "57da07bd-ecab-415d-9d86-af36d7073abc"}
        assert wirer.determine_output_type(comp) == "number"

    def test_determine_output_type_panel(self):
        """Panel provides Text type."""
        wirer = GHAutoWirer()
        comp = {"name": "Panel", "component_guid": "59e0b89a-e487-49f8-bab8-b5bab16be14c"}
        assert wirer.determine_output_type(comp) == "text"

    def test_determine_output_type_point(self):
        """Construct Point provides Point type."""
        wirer = GHAutoWirer()
        comp = {"name": "Construct Point", "component_guid": "3581f42a-9592-4549-bd6b-1c0fc39d067b"}
        assert wirer.determine_output_type(comp) == "point"

    def test_determine_output_type_vector(self):
        """Unit Vector provides Vector type."""
        wirer = GHAutoWirer()
        comp = {"name": "Unit X", "component_guid": "some-guid"}
        assert wirer.determine_output_type(comp) == "vector"

    def test_determine_output_type_circle(self):
        """Circle provides Curve type."""
        wirer = GHAutoWirer()
        comp = {"name": "Circle", "component_guid": "some-guid"}
        assert wirer.determine_output_type(comp) == "curve"

    def test_determine_output_type_sphere(self):
        """Sphere provides Surface type."""
        wirer = GHAutoWirer()
        comp = {"name": "Sphere", "component_guid": "dabc854d-..."}
        assert wirer.determine_output_type(comp) == "surface"

    def test_determine_output_type_box(self):
        """Box provides Brep type."""
        wirer = GHAutoWirer()
        comp = {"name": "Box", "component_guid": "some-guid"}
        assert wirer.determine_output_type(comp) == "brep"

    def test_determine_output_type_unknown(self):
        """Unknown component returns None."""
        wirer = GHAutoWirer()
        comp = {"name": "SomeUnknownComponent", "component_guid": "xyz"}
        assert wirer.determine_output_type(comp) is None


class TestFindParamMatch:
    """Tests for find_param_match method."""

    def test_match_input_to_param_by_type(self):
        """Match slider to Number parameter."""
        wirer = GHAutoWirer()

        input_comp = {"name": "Number Slider", "instance_guid": "input-123"}
        main_params = [
            {"name": "Base", "nickName": "B", "type": "Plane"},
            {"name": "Radius", "nickName": "R", "type": "Number"},
        ]

        match = wirer.find_param_match(input_comp, main_params, connected_params=set())
        assert match is not None
        assert match["nickName"] == "R"

    def test_no_match_when_types_incompatible(self):
        """No match when types don't align."""
        wirer = GHAutoWirer()

        input_comp = {"name": "Number Slider", "instance_guid": "input-123"}
        main_params = [
            {"name": "Base", "nickName": "B", "type": "Plane"},
            {"name": "Vector", "nickName": "V", "type": "Vector"},
        ]

        match = wirer.find_param_match(input_comp, main_params, connected_params=set())
        assert match is None

    def test_skip_already_connected_params(self):
        """Don't rewire already connected params."""
        wirer = GHAutoWirer()

        input_comp = {"name": "Number Slider", "instance_guid": "input-123"}
        main_params = [
            {"name": "Radius", "nickName": "R", "type": "Number"},
        ]

        # R is already connected
        match = wirer.find_param_match(input_comp, main_params, connected_params={"R"})
        assert match is None

    def test_match_point_to_point_param(self):
        """Match Construct Point to Point parameter."""
        wirer = GHAutoWirer()

        input_comp = {"name": "Construct Point", "instance_guid": "pt-123"}
        main_params = [
            {"name": "Center", "nickName": "C", "type": "Point"},
        ]

        match = wirer.find_param_match(input_comp, main_params, connected_params=set())
        assert match is not None
        assert match["nickName"] == "C"

    def test_match_panel_to_text_param(self):
        """Match Panel to Text parameter."""
        wirer = GHAutoWirer()

        input_comp = {"name": "Panel", "instance_guid": "panel-123"}
        main_params = [
            {"name": "Text", "nickName": "T", "type": "Text"},
        ]

        match = wirer.find_param_match(input_comp, main_params, connected_params=set())
        assert match is not None
        assert match["nickName"] == "T"

    def test_match_number_to_generic_param(self):
        """Match Number to Generic parameter (fallback)."""
        wirer = GHAutoWirer()

        input_comp = {"name": "Number Slider", "instance_guid": "num-123"}
        main_params = [
            {"name": "Input", "nickName": "I", "type": "Generic"},
        ]

        match = wirer.find_param_match(input_comp, main_params, connected_params=set())
        assert match is not None
        assert match["nickName"] == "I"

    def test_first_compatible_param_wins(self):
        """First compatible parameter in list wins."""
        wirer = GHAutoWirer()

        input_comp = {"name": "Number Slider", "instance_guid": "num-123"}
        main_params = [
            {"name": "First", "nickName": "F", "type": "Number"},
            {"name": "Second", "nickName": "S", "type": "Number"},
        ]

        match = wirer.find_param_match(input_comp, main_params, connected_params=set())
        assert match is not None
        assert match["nickName"] == "F"


class TestGenerateWiringPlan:
    """Tests for generate_wiring_plan method."""

    def test_generate_wiring_plan(self):
        """Generate wiring plan for sphere with radius slider."""
        wirer = GHAutoWirer()

        created = [
            {"name": "Number Slider", "instance_guid": "slider-1", "component_guid": "57da07bd-..."},
            {"name": "Sphere", "instance_guid": "sphere-1", "component_guid": "dabc854d-..."},
        ]

        # Mock component info
        component_params = {
            "sphere-1": {
                "inputs": [
                    {"name": "Base", "nickName": "B", "type": "Plane"},
                    {"name": "Radius", "nickName": "R", "type": "Number"},
                ]
            }
        }

        plan = wirer.generate_wiring_plan(created, component_params)

        assert len(plan) == 1
        assert plan[0]["source_guid"] == "slider-1"
        assert plan[0]["target_guid"] == "sphere-1"
        assert plan[0]["target_param"] == "R"

    def test_wiring_plan_multiple_inputs(self):
        """Multiple inputs wire to different params."""
        wirer = GHAutoWirer()

        created = [
            {"name": "Number Slider", "instance_guid": "slider-1", "component_guid": "57da07bd-..."},
            {"name": "Construct Point", "instance_guid": "point-1", "component_guid": "3581f42a-..."},
            {"name": "Cylinder", "instance_guid": "cyl-1", "component_guid": "xxx-..."},
        ]

        component_params = {
            "cyl-1": {
                "inputs": [
                    {"name": "Base", "nickName": "B", "type": "Point"},
                    {"name": "Radius", "nickName": "R", "type": "Number"},
                    {"name": "Length", "nickName": "L", "type": "Number"},
                ]
            }
        }

        plan = wirer.generate_wiring_plan(created, component_params)

        # Should wire slider to R (first available number param) and point to B
        assert len(plan) == 2

        source_map = {p["source_guid"]: p for p in plan}
        assert "slider-1" in source_map
        assert "point-1" in source_map
        assert source_map["slider-1"]["target_param"] == "R"
        assert source_map["point-1"]["target_param"] == "B"

    def test_wiring_plan_empty_when_no_inputs(self):
        """Empty plan when no input components."""
        wirer = GHAutoWirer()

        created = [
            {"name": "Sphere", "instance_guid": "sphere-1", "component_guid": "dabc854d-..."},
        ]

        component_params = {
            "sphere-1": {
                "inputs": [
                    {"name": "Radius", "nickName": "R", "type": "Number"},
                ]
            }
        }

        plan = wirer.generate_wiring_plan(created, component_params)
        assert len(plan) == 0

    def test_wiring_plan_no_match_for_incompatible(self):
        """No wiring when types are incompatible."""
        wirer = GHAutoWirer()

        created = [
            {"name": "Panel", "instance_guid": "panel-1", "component_guid": "59e0b89a-..."},
            {"name": "Sphere", "instance_guid": "sphere-1", "component_guid": "dabc854d-..."},
        ]

        component_params = {
            "sphere-1": {
                "inputs": [
                    {"name": "Radius", "nickName": "R", "type": "Number"},
                ]
            }
        }

        plan = wirer.generate_wiring_plan(created, component_params)

        # Panel (text) can't wire to Number param
        assert len(plan) == 0


class TestClassifyComponent:
    """Tests for classify_component method."""

    def test_classify_slider_as_input(self):
        """Number Slider classified as input component."""
        wirer = GHAutoWirer()
        comp = {"name": "Number Slider", "instance_guid": "slider-1"}
        assert wirer.classify_component(comp) == "input"

    def test_classify_panel_as_input(self):
        """Panel classified as input component."""
        wirer = GHAutoWirer()
        comp = {"name": "Panel", "instance_guid": "panel-1"}
        assert wirer.classify_component(comp) == "input"

    def test_classify_point_as_input(self):
        """Construct Point classified as input component."""
        wirer = GHAutoWirer()
        comp = {"name": "Construct Point", "instance_guid": "point-1"}
        assert wirer.classify_component(comp) == "input"

    def test_classify_sphere_as_main(self):
        """Sphere classified as main component."""
        wirer = GHAutoWirer()
        comp = {"name": "Sphere", "instance_guid": "sphere-1"}
        assert wirer.classify_component(comp) == "main"

    def test_classify_unknown_as_main(self):
        """Unknown component defaults to main."""
        wirer = GHAutoWirer()
        comp = {"name": "SomeComponent", "instance_guid": "some-1"}
        assert wirer.classify_component(comp) == "main"


class TestValuesToSet:
    """Test values_to_set processing."""

    def test_build_value_calls_slider(self):
        """Build set-value call for slider."""
        wirer = GHAutoWirer()

        created = [
            {"name": "Number Slider", "instance_guid": "slider-1"},
            {"name": "Sphere", "instance_guid": "sphere-1"},
        ]
        values_to_set = [
            {"component_index": 0, "value": 5.0}
        ]

        calls = wirer.build_value_calls(created, values_to_set)

        assert len(calls) == 1
        assert calls[0]["guid"] == "slider-1"
        assert calls[0]["value"] == 5.0

    def test_build_value_calls_panel(self):
        """Build set-value call for panel."""
        wirer = GHAutoWirer()

        created = [
            {"name": "Panel", "instance_guid": "panel-1"},
        ]
        values_to_set = [
            {"component_index": 0, "value": "hello"}
        ]

        calls = wirer.build_value_calls(created, values_to_set)

        assert len(calls) == 1
        assert calls[0]["guid"] == "panel-1"
        assert calls[0]["value"] == "hello"

    def test_skip_invalid_indices(self):
        """Skip values_to_set with out-of-bounds indices."""
        wirer = GHAutoWirer()

        created = [{"name": "Slider", "instance_guid": "s1"}]
        values_to_set = [
            {"component_index": 5, "value": 10}  # Out of bounds
        ]

        calls = wirer.build_value_calls(created, values_to_set)
        assert len(calls) == 0

    def test_skip_none_values(self):
        """Skip values_to_set with None value."""
        wirer = GHAutoWirer()

        created = [{"name": "Slider", "instance_guid": "s1"}]
        values_to_set = [
            {"component_index": 0, "value": None}
        ]

        calls = wirer.build_value_calls(created, values_to_set)
        assert len(calls) == 0

    def test_handle_empty_values_to_set(self):
        """Handle empty or None values_to_set gracefully."""
        wirer = GHAutoWirer()
        created = [{"name": "Slider", "instance_guid": "s1"}]

        assert wirer.build_value_calls(created, []) == []
        assert wirer.build_value_calls(created, None) == []