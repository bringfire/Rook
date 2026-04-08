"""Tests for Recipe Extraction (Phase: Recipe Learning)."""

import pytest
from rook.learning.recipe_extraction import (
    DraftRecipe,
    identify_inputs,
    identify_outputs,
    infer_output_type,
    build_connection_list,
    infer_input_semantics,
    extract_recipe,
    extract_recipe_v2,
    recipe_to_edit,
)


class TestDraftRecipe:
    """Tests for DraftRecipe data class."""

    def test_create_draft_recipe(self):
        """Can create a draft recipe with required fields."""
        draft = DraftRecipe(
            draft_id="draft_abc123",
            components=[
                {"guid": "a1", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "b1", "name": "Sphere", "type": "Component_Sphere"},
            ],
            wiring=[
                {"from": "a1", "from_param": "output", "to": "b1", "to_param": "R"}
            ],
            input_structure={
                "sliders": [{"guid": "a1", "role": "radius", "min": 0, "max": 100, "value": 5}]
            },
            output_type="surface",
        )
        assert draft.draft_id == "draft_abc123"
        assert len(draft.components) == 2
        assert len(draft.wiring) == 1
        assert draft.output_type == "surface"

    def test_draft_recipe_with_classification(self):
        """Draft recipe stores DSPy classification results."""
        draft = DraftRecipe(
            draft_id="draft_xyz",
            components=[],
            wiring=[],
            input_structure={},
            output_type="brep",
            suggested_name="parametric_sphere",
            detected_tags=["primitives", "parametric"],
            suggested_intents=["create sphere with radius slider"],
            description="Slider-controlled sphere radius",
        )
        assert draft.suggested_name == "parametric_sphere"
        assert "primitives" in draft.detected_tags
        assert len(draft.suggested_intents) == 1

    def test_draft_recipe_to_dict(self):
        """Draft recipe serializes to dict for MCP response."""
        draft = DraftRecipe(
            draft_id="draft_001",
            components=[{"guid": "x", "name": "Panel"}],
            wiring=[],
            input_structure={"panels": [{"guid": "x", "role": "text"}]},
            output_type="none",
            suggested_name="text_display",
            detected_tags=["display"],
            suggested_intents=["show text"],
            description="Display text on panel",
            source_definition="simple.ghx",
        )
        data = draft.to_dict()

        assert data["draft_id"] == "draft_001"
        assert data["component_count"] == 1
        assert data["connection_count"] == 0
        assert data["suggested_name"] == "text_display"
        assert data["detected_tags"] == ["display"]
        assert data["source_definition"] == "simple.ghx"


class TestCanvasAnalysis:
    """Tests for canvas analysis helper functions."""

    @pytest.fixture
    def simple_canvas(self):
        """A simple slider -> sphere canvas."""
        return {
            "objects": [
                {"guid": "slider1", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "sphere1", "name": "Sphere", "type": "Component_Sphere"},
            ]
        }

    @pytest.fixture
    def trigonometry_canvas(self):
        """A more complex canvas with multiple components."""
        return {
            "objects": [
                {"guid": "s1", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "s2", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "panel1", "name": "Panel", "type": "GH_Panel"},
                {"guid": "series1", "name": "Series", "type": "Component_Series"},
                {"guid": "sin1", "name": "Sine", "type": "FuncSin"},
                {"guid": "pt1", "name": "Construct Point", "type": "Component_ConstructPoint"},
                {"guid": "interp1", "name": "Interpolate", "type": "Component_InterpCurve"},
                {"guid": "pipe1", "name": "Pipe", "type": "Component_PipeSurface"},
                {"guid": "preview1", "name": "Custom Preview", "type": "GH_CustomPreviewComponent"},
            ]
        }

    def test_identify_inputs_sliders_and_panels(self, trigonometry_canvas):
        """Sliders and panels are identified as inputs."""
        inputs = identify_inputs(trigonometry_canvas["objects"])
        input_types = [i["type"] for i in inputs]

        assert len(inputs) == 3  # 2 sliders + 1 panel
        assert "GH_NumberSlider" in input_types
        assert "GH_Panel" in input_types

    def test_identify_outputs_preview_components(self, trigonometry_canvas):
        """Preview components and endpoints identified as outputs."""
        # Connections show pipe -> preview, so preview is terminal
        connections = [
            {"from": "pipe1", "to": "preview1"},
        ]
        outputs = identify_outputs(trigonometry_canvas["objects"], connections)

        assert any(o["guid"] == "preview1" for o in outputs)

    def test_infer_output_type_from_pipe(self):
        """Pipe component produces brep."""
        outputs = [{"name": "Pipe", "type": "Component_PipeSurface"}]
        assert infer_output_type(outputs) == "brep"

    def test_infer_output_type_from_curve(self):
        """Interpolate component produces curve."""
        outputs = [{"name": "Interpolate", "type": "Component_InterpCurve"}]
        assert infer_output_type(outputs) == "curve"

    def test_build_connection_list(self):
        """Build flat connection list from component data."""
        # Simulated gh_connections response for a component
        connections_data = {
            "sphere1": {
                "inputs": [
                    {"name": "R", "sources": [{"guid": "slider1", "param": "output"}]}
                ]
            }
        }
        connections = build_connection_list(connections_data)

        assert len(connections) == 1
        assert connections[0]["from"] == "slider1"
        assert connections[0]["to"] == "sphere1"
        assert connections[0]["to_param"] == "R"


class TestSemanticInference:
    """Tests for input semantic role inference."""

    def test_infer_radius_from_param_name(self):
        """Slider connected to 'R' or 'Radius' param inferred as radius."""
        inputs = [{"guid": "s1", "name": "Number Slider", "type": "GH_NumberSlider"}]
        connections = [{"from": "s1", "to": "sphere1", "to_param": "R"}]
        components = [
            {"guid": "s1", "name": "Number Slider"},
            {"guid": "sphere1", "name": "Sphere"},
        ]

        result = infer_input_semantics(inputs, connections, components)

        assert len(result["sliders"]) == 1
        assert result["sliders"][0]["role"] == "radius"

    def test_infer_count_from_series_count(self):
        """Slider connected to Series.Count inferred as count."""
        inputs = [{"guid": "s1", "type": "GH_NumberSlider"}]
        connections = [{"from": "s1", "to": "series1", "to_param": "Count"}]
        components = [{"guid": "s1"}, {"guid": "series1", "name": "Series"}]

        result = infer_input_semantics(inputs, connections, components)

        assert result["sliders"][0]["role"] == "count"

    def test_infer_step_from_series_step(self):
        """Slider connected to Series.Step inferred as step_size."""
        inputs = [{"guid": "s1", "type": "GH_NumberSlider"}]
        connections = [{"from": "s1", "to": "series1", "to_param": "Step"}]
        components = [{"guid": "s1"}, {"guid": "series1", "name": "Series"}]

        result = infer_input_semantics(inputs, connections, components)

        assert result["sliders"][0]["role"] == "step_size"

    def test_infer_amplitude_from_remap_target(self):
        """Slider connected to Remap.Target inferred as amplitude."""
        inputs = [{"guid": "s1", "type": "GH_NumberSlider"}]
        connections = [{"from": "s1", "to": "remap1", "to_param": "Target"}]
        components = [{"guid": "s1"}, {"guid": "remap1", "name": "Remap Numbers"}]

        result = infer_input_semantics(inputs, connections, components)

        assert result["sliders"][0]["role"] == "amplitude"

    def test_panel_inferred_as_text(self):
        """Panel inputs inferred as text role."""
        inputs = [{"guid": "p1", "type": "GH_Panel"}]
        connections = []
        components = [{"guid": "p1", "name": "Panel"}]

        result = infer_input_semantics(inputs, connections, components)

        assert len(result["panels"]) == 1
        assert result["panels"][0]["role"] == "text"

    def test_unknown_connection_role(self):
        """Unknown connections get 'parameter' as generic role."""
        inputs = [{"guid": "s1", "type": "GH_NumberSlider"}]
        connections = [{"from": "s1", "to": "custom1", "to_param": "Foo"}]
        components = [{"guid": "s1"}, {"guid": "custom1", "name": "Custom"}]

        result = infer_input_semantics(inputs, connections, components)

        assert result["sliders"][0]["role"] == "parameter"


class TestExtractRecipe:
    """Tests for the main extract_recipe function."""

    def test_extract_simple_recipe(self):
        """Extract recipe from simple slider -> sphere canvas."""
        canvas_state = {
            "objects": [
                {"guid": "s1", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "sphere1", "name": "Sphere", "type": "Component_Sphere"},
            ]
        }
        connections_data = {
            "sphere1": {
                "inputs": [
                    {"name": "R", "sources": [{"guid": "s1", "param": "output"}]}
                ]
            }
        }

        draft = extract_recipe(canvas_state, connections_data)

        assert draft.draft_id.startswith("draft_")
        assert len(draft.components) == 2
        assert len(draft.wiring) == 1
        assert draft.output_type == "surface"
        assert len(draft.input_structure["sliders"]) == 1
        assert draft.input_structure["sliders"][0]["role"] == "radius"

    def test_extract_with_classification(self):
        """Extracted recipe includes classification."""
        canvas_state = {
            "objects": [
                {"guid": "s1", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "s2", "name": "Number Slider", "type": "GH_NumberSlider"},
                {"guid": "series1", "name": "Series", "type": "Component_Series"},
                {"guid": "sin1", "name": "Sine", "type": "FuncSin"},
                {"guid": "pipe1", "name": "Pipe", "type": "Component_PipeSurface"},
            ]
        }
        connections_data = {}

        draft = extract_recipe(canvas_state, connections_data, use_dspy=False)

        assert "trigonometric" in draft.detected_tags
        assert "parametric" in draft.detected_tags
        assert draft.suggested_name  # Non-empty

    def test_extract_with_source_definition(self):
        """Source definition name is preserved."""
        canvas_state = {"objects": [{"guid": "a", "name": "Panel", "type": "GH_Panel"}]}

        draft = extract_recipe(
            canvas_state,
            connections_data={},
            source_definition="MyDefinition.ghx"
        )

        assert draft.source_definition == "MyDefinition.ghx"


class TestV2RoundTrip:
    """Tests for v2 snapshot → extract → replay round-trip fidelity."""

    @pytest.fixture
    def sphere_snapshot(self):
        """Simulated gh_snapshot output: slider → sphere → panel."""
        return {
            "version": "1.0.0",
            "document": {"name": "test.gh", "path": "", "solver_state": "ok"},
            "epoch": 3,
            "components": [
                {
                    "id": "C1", "type": "NumberSlider", "nick": "Radius",
                    "pos": [150, 100], "is_param": True,
                    "value": {"type": "slider", "val": 5.0, "min": 0, "max": 10},
                },
                {
                    "id": "C2", "type": "Component_Sphere", "nick": "Sph",
                    "name": "Sphere", "category": "Surface", "pos": [400, 100],
                    "inputs": [
                        {"idx": 0, "name": "Base", "nick": "B", "type": "Plane", "sources": 0},
                        {"idx": 1, "name": "Radius", "nick": "R", "type": "Number", "sources": 1},
                    ],
                    "outputs": [
                        {"idx": 0, "name": "Sphere", "nick": "S", "type": "Brep", "recipients": 1,
                         "data": {"structure": "single", "count": 1, "preview": ["Brep (1 face)"]}},
                    ],
                },
                {
                    "id": "C3", "type": "Panel", "nick": "Output",
                    "pos": [650, 100], "is_param": True,
                    "value": {"type": "panel", "val": "Brep (1 face)"},
                },
            ],
            "flows": [
                "C1.O0>C2.I1",
                "C2.O0>C3.I0",
            ],
            "groups": [],
            "diagnostics": {"total": 3, "errors": 0, "warnings": 0},
        }

    def test_extract_v2_produces_r_prefixed_ids(self, sphere_snapshot):
        """v2 extraction maps C-IDs to R-IDs."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)

        assert draft.schema_version == "2.0"
        assert draft.graph is not None

        comp_ids = [c["id"] for c in draft.graph["components"]]
        assert comp_ids == ["R1", "R2", "R3"]

    def test_extract_v2_preserves_flow_topology(self, sphere_snapshot):
        """v2 extraction preserves wiring topology with R-prefixed IDs."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)

        flows = draft.graph["flows"]
        assert "R1.O0>R2.I1" in flows
        assert "R2.O0>R3.I0" in flows
        assert len(flows) == 2

    def test_extract_v2_preserves_slider_values(self, sphere_snapshot):
        """v2 extraction preserves slider min/max/value."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)

        slider = draft.graph["components"][0]
        assert slider["type"] == "slider"
        assert slider["min"] == 0
        assert slider["max"] == 10
        assert slider["value"] == 5.0

    def test_extract_v2_strips_runtime_data(self, sphere_snapshot):
        """v2 extraction strips output data previews and sources/recipients."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)

        sphere = draft.graph["components"][1]
        # Should not have inputs/outputs with runtime data
        assert "inputs" not in sphere
        assert "outputs" not in sphere
        assert "data" not in sphere

    def test_recipe_to_edit_maps_r_to_t(self, sphere_snapshot):
        """recipe_to_edit converts R-IDs to T-IDs."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)
        edit_doc = recipe_to_edit(draft.graph)

        temp_ids = [c["temp_id"] for c in edit_doc["create"]]
        assert temp_ids == ["T1", "T2", "T3"]

    def test_recipe_to_edit_preserves_flow_topology(self, sphere_snapshot):
        """recipe_to_edit preserves topology with T-prefixed IDs."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)
        edit_doc = recipe_to_edit(draft.graph)

        assert "T1.O0>T2.I1" in edit_doc["connect"]
        assert "T2.O0>T3.I0" in edit_doc["connect"]
        assert len(edit_doc["connect"]) == 2

    def test_recipe_to_edit_preserves_slider_config(self, sphere_snapshot):
        """recipe_to_edit preserves slider type and values."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)
        edit_doc = recipe_to_edit(draft.graph)

        slider = edit_doc["create"][0]
        assert slider["type"] == "slider"
        assert slider["min"] == 0
        assert slider["max"] == 10
        assert slider["value"] == 5.0
        assert slider["nick"] == "Radius"

    def test_recipe_to_edit_uses_guid_for_components(self, sphere_snapshot):
        """recipe_to_edit uses component guid when available, falls back to display name."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)
        edit_doc = recipe_to_edit(draft.graph)

        sphere_entry = edit_doc["create"][1]
        # Sphere has no guid in recipe (snapshot doesn't include ComponentGuid),
        # so it uses the display name "Sphere", not the class name "Component_Sphere"
        assert sphere_entry.get("name") == "Sphere"

    def test_recipe_to_edit_applies_offset(self, sphere_snapshot):
        """recipe_to_edit applies position offset."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)
        edit_doc = recipe_to_edit(draft.graph, offset=(100, 50))

        slider = edit_doc["create"][0]
        assert slider["pos"] == [250, 150]  # 150+100, 100+50

    def test_full_roundtrip_topology(self, sphere_snapshot):
        """Full round-trip: snapshot → extract → replay preserves topology.

        The number of components and the connection pattern must be identical
        through the C→R→T transformation chain.
        """
        # Step 1: Extract (C→R)
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)
        assert draft.graph is not None

        # Step 2: Replay (R→T)
        edit_doc = recipe_to_edit(draft.graph)

        # Verify component count preserved
        original_count = len(sphere_snapshot["components"])
        create_count = len(edit_doc["create"])
        assert create_count == original_count, (
            f"Component count mismatch: {original_count} in snapshot, {create_count} in edit"
        )

        # Verify connection count preserved
        original_flows = len(sphere_snapshot["flows"])
        edit_flows = len(edit_doc["connect"])
        assert edit_flows == original_flows, (
            f"Flow count mismatch: {original_flows} in snapshot, {edit_flows} in edit"
        )

        # Verify topology shape: same param indices used
        # Original: C1.O0>C2.I1, C2.O0>C3.I0
        # After:    T1.O0>T2.I1, T2.O0>T3.I0
        # The index pattern (.O0>.I1, .O0>.I0) must be identical
        def strip_ids(flow: str) -> str:
            """Strip component IDs, keep only param references."""
            parts = flow.split(">")
            src_param = parts[0].split(".", 1)[1]  # "O0"
            tgt_param = parts[1].split(".", 1)[1]  # "I1"
            return f"{src_param}>{tgt_param}"

        original_shapes = sorted(strip_ids(f) for f in sphere_snapshot["flows"])
        edit_shapes = sorted(strip_ids(f) for f in edit_doc["connect"])
        assert original_shapes == edit_shapes, (
            f"Topology shape mismatch: {original_shapes} vs {edit_shapes}"
        )

    def test_v2_draft_to_dict_connection_count(self, sphere_snapshot):
        """v2 draft.to_dict() reports correct connection_count from graph flows."""
        draft = extract_recipe_v2(sphere_snapshot, use_dspy=False)
        data = draft.to_dict()

        assert data["connection_count"] == 2  # 2 flows, not 0


class TestMigrationStatus:
    """Tests for migration status logic (used by gh_migration_status dispatch)."""

    def test_partitions_v1_and_v2(self):
        """v1 and v2 patterns are correctly partitioned."""
        from rook.learning.pattern_memory import PatternNote

        patterns = [
            PatternNote(name="p1", pattern_type="recipe", schema_version="1.0"),
            PatternNote(name="p2", pattern_type="recipe", schema_version="1.0"),
            PatternNote(name="p3", pattern_type="recipe", schema_version="2.0",
                        graph={"components": [], "flows": []}),
            PatternNote(name="s1", pattern_type="struggle"),  # not a recipe
        ]

        recipes = [p for p in patterns if p.pattern_type == "recipe"]
        v1 = [p for p in recipes if p.schema_version != "2.0"]
        v2 = [p for p in recipes if p.schema_version == "2.0"]

        assert len(recipes) == 3
        assert len(v1) == 2
        assert len(v2) == 1

    def test_remaining_includes_source_definition(self):
        """Remaining list includes source_definition for identifying .gh files."""
        from rook.learning.pattern_memory import PatternNote

        p = PatternNote(name="sine_wave", pattern_type="recipe",
                        schema_version="1.0", source_definition="sine_wave.gh")

        entry = {
            "id": p.pattern_id,
            "name": p.name,
            "source": p.source_definition,
        }

        assert entry["name"] == "sine_wave"
        assert entry["source"] == "sine_wave.gh"


class TestUpgradeRecipe:
    """Tests for the v1→v2 upgrade merge logic."""

    def _make_v1_pattern(self):
        """Create a representative v1 pattern with A-MEM metadata."""
        from rook.learning.pattern_memory import PatternNote
        return PatternNote(
            pattern_id="test1234",
            name="test_sine_wave",
            pattern_type="recipe",
            schema_version="1.0",
            solution_brief="A sine wave pipe",
            trigger_intents=["create sine wave", "pipe along sine"],
            tags=["curves", "trigonometry"],
            links=["other_abc", "other_def"],
            times_used=5,
            times_succeeded=4,
            wiring=[{"from": "aaa", "from_param": "R", "to": "bbb", "to_param": "N"}],
            input_structure={"sliders": [{"guid": "aaa", "role": "radius"}]},
            output_type="curve",
            source_definition="sine_wave.gh",
            components_needed=["Sine", "Series", "Number Slider"],
        )

    def _make_v2_draft(self):
        """Create a mock v2 DraftRecipe as extract_recipe_v2 would return."""
        return DraftRecipe(
            draft_id="draft_test",
            components=[
                {"guid": "aaa", "name": "Sine", "type": "Component_Sine"},
                {"guid": "bbb", "name": "Series", "type": "Component_Series"},
            ],
            wiring=[],
            input_structure={"sliders": [{"id": "R1", "nick": "Count", "min": 0, "max": 100, "value": 50}]},
            output_type="curve",
            schema_version="2.0",
            graph={
                "components": [
                    {"id": "R1", "type": "slider", "nick": "Count", "pos": [100, 100]},
                    {"id": "R2", "type": "Component_Sine", "nick": "Sin", "name": "Sine", "pos": [300, 100]},
                    {"id": "R3", "type": "Component_Series", "nick": "Ser", "name": "Series", "pos": [300, 200]},
                ],
                "flows": ["R1.O0>R2.I0", "R1.O0>R3.I1"],
                "subgraphs": [],
            },
        )

    def test_merge_preserves_amem_metadata(self):
        """Upgrade must preserve links, tags, intents, confidence."""
        from rook.learning.recipe_extraction import merge_v2_into_pattern
        pattern = self._make_v1_pattern()
        draft = self._make_v2_draft()

        merge_v2_into_pattern(pattern, draft)

        # A-MEM fields untouched
        assert pattern.links == ["other_abc", "other_def"]
        assert pattern.tags == ["curves", "trigonometry"]
        assert pattern.trigger_intents == ["create sine wave", "pipe along sine"]
        assert pattern.solution_brief == "A sine wave pipe"
        assert pattern.times_used == 5
        assert pattern.times_succeeded == 4
        assert pattern.name == "test_sine_wave"
        assert pattern.source_definition == "sine_wave.gh"

    def test_merge_replaces_recipe_fields(self):
        """Upgrade must replace graph, wiring, input_structure, output_type, components_needed."""
        from rook.learning.recipe_extraction import merge_v2_into_pattern
        pattern = self._make_v1_pattern()
        draft = self._make_v2_draft()

        merge_v2_into_pattern(pattern, draft)

        # Recipe fields updated
        assert pattern.schema_version == "2.0"
        assert pattern.graph is not None
        assert len(pattern.graph["flows"]) == 2
        assert pattern.wiring == []
        assert "sliders" in pattern.input_structure
        assert pattern.input_structure["sliders"][0]["nick"] == "Count"
        assert pattern.components_needed == ["Sine", "Series"]

    def test_merge_adds_evolution_entry(self):
        """Upgrade should add a v2_migration evolution entry."""
        from datetime import datetime
        pattern = self._make_v1_pattern()
        assert len(pattern.evolution_history) == 0

        # Simulate adding evolution entry (dispatch does this after merge)
        pattern.evolution_history.append({
            "date": datetime.utcnow().isoformat() + "Z",
            "trigger": "v2_migration",
            "changes": "Upgraded from v1 wiring to v2 graph format",
        })

        assert len(pattern.evolution_history) == 1
        assert pattern.evolution_history[0]["trigger"] == "v2_migration"

    def test_pattern_id_preserved(self):
        """The pattern_id must not change during upgrade."""
        from rook.learning.recipe_extraction import merge_v2_into_pattern
        pattern = self._make_v1_pattern()
        original_id = pattern.pattern_id

        draft = self._make_v2_draft()
        merge_v2_into_pattern(pattern, draft)

        assert pattern.pattern_id == original_id
