"""
Tests for context feature extraction (Phase 1 of Contextual MAB Migration)

Test IDs correspond to mab_migration_tests.json:
- T1.1.x: Tool category mapping tests
- T1.2.x: Intent parsing tests
- T1.3.x: Context encoding tests
- T1.4.x: Edge case tests
"""

import pytest
from rook.context import (
    TOOL_CATEGORIES,
    CATEGORY_ORDER,
    GEOMETRY_ORDER,
    get_tool_category,
    parse_intent,
    analyze_tool,
    encode_context,
    get_all_tool_names,
)


# =============================================================================
# T1.1.x: Tool Category Mapping Tests
# =============================================================================

class TestToolCategoryMapping:
    """Tests for tool category mapping (T1.1.x)"""

    def test_tool_category_mapping(self):
        """T1.1.1: All 47 MCP tools map to valid categories."""
        expected_tools = [
            # Core tools
            "rhino_ping", "rhino_document", "rhino_layers", "rhino_objects",
            "rhino_selection", "rhino_select", "rhino_geometry", "rhino_execute",
            "rhino_command", "rhino_viewport", "rhino_create",
            # Geometry operations
            "rhino_delete", "rhino_transform", "rhino_copy",
            # Layer management
            "rhino_layer_create", "rhino_layer_delete", "rhino_layer_visibility",
            "rhino_layer_lock", "rhino_layer_current",
            # Selection tools
            "rhino_select_by_type", "rhino_select_by_name", "rhino_select_all",
            "rhino_select_none", "rhino_select_invert",
            # Measurement
            "rhino_measure_distance", "rhino_measure_area", "rhino_measure_volume",
            "rhino_measure_length", "rhino_measure_bbox", "rhino_measure_centroid",
            # Boolean and surface
            "rhino_boolean", "rhino_loft", "rhino_sweep", "rhino_extrude",
            # Import/export
            "rhino_import", "rhino_export",
            # Groups and blocks
            "rhino_group", "rhino_block_create",
            # Annotations
            "rhino_text", "rhino_dimension",
            # Consolidated ops
            "rhino_document_ops", "rhino_curve_ops", "rhino_material_ops",
            # Multi-instance
            "rhino_instances",
            # Knowledge
            "knowledge_query", "knowledge_record",
        ]

        # Verify all expected tools are mapped
        for tool in expected_tools:
            category = get_tool_category(tool)
            assert category is not None, f"Tool '{tool}' not mapped to any category"
            assert category in CATEGORY_ORDER, f"Tool '{tool}' mapped to invalid category '{category}'"

        # Verify count matches
        assert len(TOOL_CATEGORIES) >= len(expected_tools), \
            f"Expected at least {len(expected_tools)} tools, found {len(TOOL_CATEGORIES)}"

    def test_tool_category_correctness(self):
        """T1.1.2: Spot check category assignments are correct."""
        # Create operations
        assert get_tool_category("rhino_create") == "create"
        assert get_tool_category("rhino_loft") == "create"
        assert get_tool_category("rhino_sweep") == "create"
        assert get_tool_category("rhino_extrude") == "create"

        # Layer operations
        assert get_tool_category("rhino_layer_create") == "layer"
        assert get_tool_category("rhino_layer_delete") == "layer"
        assert get_tool_category("rhino_layer_visibility") == "layer"

        # Boolean operations
        assert get_tool_category("rhino_boolean") == "boolean"

        # Transform operations
        assert get_tool_category("rhino_transform") == "transform"
        assert get_tool_category("rhino_copy") == "transform"
        assert get_tool_category("rhino_delete") == "transform"

        # Viewport
        assert get_tool_category("rhino_viewport") == "viewport"

        # Measure
        assert get_tool_category("rhino_measure_distance") == "measure"
        assert get_tool_category("rhino_measure_area") == "measure"

        # Material
        assert get_tool_category("rhino_material_ops") == "material"

        # Select
        assert get_tool_category("rhino_select") == "select"
        assert get_tool_category("rhino_select_all") == "select"

        # Document
        assert get_tool_category("rhino_document") == "document"
        assert get_tool_category("rhino_ping") == "document"


# =============================================================================
# T1.2.x: Intent Parsing Tests
# =============================================================================

class TestIntentParsing:
    """Tests for intent parsing (T1.2.x)"""

    def test_intent_geometry_extraction(self):
        """T1.2.1: Geometry types extracted from intent strings."""
        result = parse_intent("create a box at origin")
        assert "brep" in result["geometry_keywords"]  # box -> brep

        result = parse_intent("draw a line from point A to B")
        assert "line" in result["geometry_keywords"]
        assert "point" in result["geometry_keywords"]

        result = parse_intent("create a sphere with radius 5")
        assert "brep" in result["geometry_keywords"]  # sphere -> brep

        result = parse_intent("add a circle at center")
        assert "circle" in result["geometry_keywords"]

        result = parse_intent("create mesh from surface")
        assert "mesh" in result["geometry_keywords"]
        assert "surface" in result["geometry_keywords"]

    def test_intent_action_extraction(self):
        """T1.2.2: Action keywords extracted from intent strings."""
        result = parse_intent("delete the selected objects")
        assert "delete" in result["action_keywords"]

        result = parse_intent("create nested layer structure")
        assert "create" in result["action_keywords"]
        assert "nested" in result["modifiers"]

        result = parse_intent("move the box 10 units")
        assert "move" in result["action_keywords"]

        result = parse_intent("rotate and scale the sphere")
        assert "rotate" in result["action_keywords"]
        assert "scale" in result["action_keywords"]

        result = parse_intent("export selected to STL")
        assert "export" in result["action_keywords"]

    def test_intent_empty(self):
        """T1.2.3: Empty/None intent handled gracefully."""
        result = parse_intent("")
        assert result["geometry_keywords"] == []
        assert result["action_keywords"] == []
        assert result["modifiers"] == []

        result = parse_intent(None)
        assert result is not None
        assert result["geometry_keywords"] == []
        assert result["action_keywords"] == []
        assert result["modifiers"] == []


# =============================================================================
# T1.3.x: Context Encoding Tests
# =============================================================================

class TestContextEncoding:
    """Tests for context encoding (T1.3.x)"""

    def test_context_vector_length(self):
        """T1.3.1: Context vector has 21 dimensions."""
        context = encode_context("create box", "rhino_create", {"type": "BOX"})
        assert len(context) == 21

        # Also test with minimal input
        context = encode_context()
        assert len(context) == 21

        context = encode_context("test intent")
        assert len(context) == 21

        context = encode_context(tool="rhino_ping")
        assert len(context) == 21

    def test_context_vector_normalized(self):
        """T1.3.2: Context vector values are 0-1 normalized."""
        context = encode_context(
            "create a box and sphere",
            "rhino_create",
            {"type": "BOX", "origin": [0, 0, 0], "width": 10, "depth": 10, "height": 5}
        )

        for i, val in enumerate(context):
            assert 0.0 <= val <= 1.0, f"Value at index {i} is {val}, not in [0, 1]"

    def test_context_deterministic(self):
        """T1.3.3: Same inputs produce same context."""
        c1 = encode_context("create box", "rhino_create", {"type": "BOX"})
        c2 = encode_context("create box", "rhino_create", {"type": "BOX"})
        assert c1 == c2

        c3 = encode_context("create layer", "rhino_layer_create", {"name": "test"})
        c4 = encode_context("create layer", "rhino_layer_create", {"name": "test"})
        assert c3 == c4

    def test_context_tool_category_onehot(self):
        """T1.3.4: Tool category is one-hot encoded."""
        context = encode_context("create", "rhino_create", {})
        tool_cat_slice = context[0:10]

        # Exactly one category should be active
        assert sum(tool_cat_slice) == 1, f"Expected one-hot, got sum={sum(tool_cat_slice)}"

        # Verify it's the correct category (create is index 0)
        assert tool_cat_slice[0] == 1.0, "Create category should be at index 0"

        # Test another category
        context = encode_context("layer", "rhino_layer_create", {})
        tool_cat_slice = context[0:10]
        assert sum(tool_cat_slice) == 1
        assert tool_cat_slice[1] == 1.0, "Layer category should be at index 1"

    def test_context_geometry_multihot(self):
        """T1.3.5: Geometry types can be multi-hot encoded."""
        # Single geometry type
        context = encode_context("create a box", "rhino_create", {"type": "BOX"})
        geom_slice = context[10:18]
        assert sum(geom_slice) >= 1, "At least one geometry type should be active"

        # Multiple geometry types in intent
        context = encode_context("create box and sphere near the line", "rhino_create", {})
        geom_slice = context[10:18]
        assert sum(geom_slice) >= 2, "Multiple geometry types should be active"


# =============================================================================
# T1.4.x: Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases (T1.4.x)"""

    def test_unknown_tool(self):
        """T1.4.1: Unknown tool handled gracefully."""
        context = encode_context("do something", "rhino_unknown_tool", {})
        assert len(context) == 21

        # Tool category should be all zeros for unknown tool
        tool_cat_slice = context[0:10]
        assert sum(tool_cat_slice) == 0, "Unknown tool should have no category"

        # Category lookup should return None
        assert get_tool_category("rhino_unknown_tool") is None
        assert get_tool_category("not_a_tool") is None
        assert get_tool_category("") is None
        assert get_tool_category(None) is None

    def test_special_characters_in_intent(self):
        """T1.4.2: Special characters in intent don't break parsing."""
        # Quotes
        context = encode_context("create 'box' with size=10", "rhino_create", {})
        assert len(context) == 21

        # Brackets and parentheses
        context = encode_context("create [box] at (0,0,0)", "rhino_create", {})
        assert len(context) == 21

        # Newlines and tabs
        context = encode_context("create\nbox\tat origin", "rhino_create", {})
        assert len(context) == 21

        # Numbers and symbols
        context = encode_context("create box #1 with 50% scale", "rhino_create", {})
        assert len(context) == 21

    def test_unicode_intent(self):
        """T1.4.3: Unicode in intent handled."""
        # French
        context = encode_context("créer une boîte", "rhino_create", {})
        assert len(context) == 21

        # German
        context = encode_context("Erstellen Sie eine Kugel", "rhino_create", {})
        assert len(context) == 21

        # Chinese
        context = encode_context("创建一个盒子", "rhino_create", {})
        assert len(context) == 21

        # Emoji (should not crash)
        context = encode_context("create a box 📦", "rhino_create", {})
        assert len(context) == 21


# =============================================================================
# Additional Helper Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for utility functions"""

    def test_get_all_tool_names(self):
        """All tool names are returned."""
        tools = get_all_tool_names()
        assert len(tools) >= 46  # 46 MCP tools currently defined
        assert "rhino_create" in tools
        assert "rhino_ping" in tools
        assert "knowledge_query" in tools

    def test_analyze_tool(self):
        """Tool analysis returns correct info."""
        # Destructive tool
        result = analyze_tool("rhino_delete", {"ids": ["guid1", "guid2"]})
        assert result["category"] == "transform"
        assert result["is_destructive"] is True
        assert result["param_count"] == 1

        # Selection-dependent tool
        result = analyze_tool("rhino_transform", {"ids": ["guid"], "operation": "move"})
        assert result["has_selection_dependency"] is True

        # Normal tool
        result = analyze_tool("rhino_ping", {})
        assert result["is_destructive"] is False
        assert result["has_selection_dependency"] is False

    def test_category_order(self):
        """Category order is correct."""
        assert len(CATEGORY_ORDER) == 10
        assert "create" in CATEGORY_ORDER
        assert "layer" in CATEGORY_ORDER
        assert "boolean" in CATEGORY_ORDER

    def test_geometry_order(self):
        """Geometry order is correct."""
        assert len(GEOMETRY_ORDER) == 8
        assert "point" in GEOMETRY_ORDER
        assert "line" in GEOMETRY_ORDER
        assert "brep" in GEOMETRY_ORDER
        assert "mesh" in GEOMETRY_ORDER
