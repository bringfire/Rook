"""
Tool Registry - Extracts and manages tool definitions from server.py.
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path


@dataclass
class ToolDefinition:
    """Represents a single MCP tool definition."""
    name: str
    description: str
    input_schema: dict[str, Any]
    category: str = "unknown"
    requires_objects: bool = False
    http_endpoint: str | None = None
    http_method: str = "POST"

    @property
    def required_params(self) -> list[str]:
        """Get list of required parameters."""
        return self.input_schema.get("required", [])

    @property
    def all_params(self) -> dict[str, dict]:
        """Get all parameter definitions."""
        return self.input_schema.get("properties", {})

    def __repr__(self) -> str:
        return f"ToolDefinition({self.name}, params={list(self.all_params.keys())})"


class ToolRegistry:
    """
    Registry of all MCP tool definitions.
    Loads tools from the server module and categorizes them.
    """

    # Category definitions based on tool behavior
    CATEGORY_STATELESS = "stateless"       # No Rhino state needed
    CATEGORY_CREATION = "creation"          # Creates new objects
    CATEGORY_MODIFICATION = "modification"  # Needs existing objects
    CATEGORY_MULTI_OBJECT = "multi_object"  # Needs multiple objects
    CATEGORY_KNOWLEDGE = "knowledge"        # Knowledge graph tools

    # Tool categorization map
    TOOL_CATEGORIES = {
        # Stateless queries
        "rhino_ping": CATEGORY_STATELESS,
        "rhino_document": CATEGORY_STATELESS,
        "rhino_layers": CATEGORY_STATELESS,
        "rhino_objects": CATEGORY_STATELESS,
        "rhino_selection": CATEGORY_STATELESS,
        "rhino_blocks": CATEGORY_STATELESS,
        "rhino_instances": CATEGORY_STATELESS,

        # Creation tools
        "rhino_create": CATEGORY_CREATION,
        "rhino_layer_create": CATEGORY_CREATION,
        "rhino_text": CATEGORY_CREATION,
        "rhino_dimension": CATEGORY_CREATION,
        "rhino_subd_box": CATEGORY_CREATION,
        "rhino_subd_sphere": CATEGORY_CREATION,
        "rhino_subd_cylinder": CATEGORY_CREATION,
        "rhino_mesh_box": CATEGORY_CREATION,
        "rhino_mesh_sphere": CATEGORY_CREATION,
        "rhino_mesh_cylinder": CATEGORY_CREATION,
        "rhino_mesh_cone": CATEGORY_CREATION,
        "rhino_block_create": CATEGORY_CREATION,
        # Phase 2 surface/curve extension (PR-1 worked example).
        "rhino_create_edge_srf": CATEGORY_CREATION,
        "rhino_blend_curves": CATEGORY_CREATION,
        # Phase 2 surface/curve extension (PR-2).
        "rhino_create_patch": CATEGORY_CREATION,
        # Phase 2 surface/curve extension (PR-3).
        "rhino_create_network_srf": CATEGORY_CREATION,
        # Phase 2 surface/curve extension (PR-4). Three intent keys →
        # /curve/boolean with operation discriminator (mirrors brep-boolean).
        "rhino_curve_boolean_union": CATEGORY_CREATION,
        "rhino_curve_boolean_difference": CATEGORY_CREATION,
        "rhino_curve_boolean_intersection": CATEGORY_CREATION,

        # Modification tools (need objects first)
        "rhino_transform": CATEGORY_MODIFICATION,
        "rhino_copy": CATEGORY_MODIFICATION,
        "rhino_delete": CATEGORY_MODIFICATION,
        "rhino_select": CATEGORY_MODIFICATION,
        "rhino_select_by_type": CATEGORY_MODIFICATION,
        "rhino_select_by_name": CATEGORY_MODIFICATION,
        "rhino_select_all": CATEGORY_MODIFICATION,
        "rhino_select_none": CATEGORY_MODIFICATION,
        "rhino_select_invert": CATEGORY_MODIFICATION,
        "rhino_deselect": CATEGORY_MODIFICATION,
        "rhino_geometry": CATEGORY_MODIFICATION,
        "rhino_measure_distance": CATEGORY_MODIFICATION,
        "rhino_measure_area": CATEGORY_MODIFICATION,
        "rhino_measure_volume": CATEGORY_MODIFICATION,
        "rhino_measure_length": CATEGORY_MODIFICATION,
        "rhino_measure_bbox": CATEGORY_MODIFICATION,
        "rhino_measure_centroid": CATEGORY_MODIFICATION,
        "rhino_extrude": CATEGORY_MODIFICATION,
        "rhino_layer_delete": CATEGORY_MODIFICATION,
        "rhino_layer_visibility": CATEGORY_MODIFICATION,
        "rhino_layer_lock": CATEGORY_MODIFICATION,
        "rhino_layer_current": CATEGORY_MODIFICATION,
        "rhino_layer_set_properties": CATEGORY_MODIFICATION,
        "rhino_layer_set_properties_batch": CATEGORY_MODIFICATION,
        "rhino_curve_ops": CATEGORY_MODIFICATION,
        "rhino_subd_from_mesh": CATEGORY_MODIFICATION,
        "rhino_subd_from_surface": CATEGORY_MODIFICATION,
        "rhino_subd_subdivide": CATEGORY_MODIFICATION,
        "rhino_subd_crease": CATEGORY_MODIFICATION,
        "rhino_subd_to_brep": CATEGORY_MODIFICATION,
        "rhino_subd_to_mesh": CATEGORY_MODIFICATION,
        "rhino_mesh_from_brep": CATEGORY_MODIFICATION,
        "rhino_mesh_reduce": CATEGORY_MODIFICATION,
        "rhino_quad_remesh": CATEGORY_MODIFICATION,
        "rhino_mesh_repair": CATEGORY_MODIFICATION,
        "rhino_mesh_smooth": CATEGORY_MODIFICATION,
        "rhino_mesh_weld": CATEGORY_MODIFICATION,
        "rhino_mesh_unweld": CATEGORY_MODIFICATION,
        "rhino_material_ops": CATEGORY_MODIFICATION,
        "rhino_group": CATEGORY_MODIFICATION,
        "rhino_block_insert": CATEGORY_MODIFICATION,
        "rhino_block_explode": CATEGORY_MODIFICATION,
        "rhino_block_delete": CATEGORY_MODIFICATION,
        "rhino_block_rename": CATEGORY_MODIFICATION,
        "rhino_block_description": CATEGORY_MODIFICATION,
        "rhino_block_info": CATEGORY_MODIFICATION,
        "rhino_block_add_objects": CATEGORY_MODIFICATION,
        "rhino_block_remove_objects": CATEGORY_MODIFICATION,
        "rhino_block_replace_geometry": CATEGORY_MODIFICATION,
        "rhino_block_replace_object_geometry": CATEGORY_MODIFICATION,
        "rhino_block_replace_object_geometry_batch": CATEGORY_MODIFICATION,
        "rhino_block_transform_object": CATEGORY_MODIFICATION,
        "rhino_block_transform_object_batch": CATEGORY_MODIFICATION,
        "rhino_block_transform_instance": CATEGORY_MODIFICATION,
        "rhino_block_transform_instance_batch": CATEGORY_MODIFICATION,
        "rhino_block_set_layers": CATEGORY_MODIFICATION,
        "rhino_block_set_layers_batch": CATEGORY_MODIFICATION,
        "rhino_block_set_materials": CATEGORY_MODIFICATION,
        "rhino_block_set_materials_batch": CATEGORY_MODIFICATION,
        "rhino_block_set_object_colors": CATEGORY_MODIFICATION,
        "rhino_block_set_object_colors_batch": CATEGORY_MODIFICATION,
        "rhino_block_set_object_user_strings": CATEGORY_MODIFICATION,
        "rhino_block_set_object_user_strings_batch": CATEGORY_MODIFICATION,
        "rhino_usertext_object_set": CATEGORY_MODIFICATION,
        "rhino_usertext_object_get": CATEGORY_MODIFICATION,
        "rhino_usertext_document_set": CATEGORY_MODIFICATION,
        "rhino_usertext_document_get": CATEGORY_STATELESS,
        "rhino_block_set_object_names": CATEGORY_MODIFICATION,
        "rhino_block_set_object_names_batch": CATEGORY_MODIFICATION,
        "rhino_block_instances": CATEGORY_MODIFICATION,
        "rhino_block_replace_instance": CATEGORY_MODIFICATION,
        "rhino_block_replace_instance_batch": CATEGORY_MODIFICATION,
        "rhino_block_reset_scale": CATEGORY_MODIFICATION,
        "rhino_block_link": CATEGORY_MODIFICATION,
        "rhino_block_refresh": CATEGORY_MODIFICATION,
        "rhino_block_unlink": CATEGORY_MODIFICATION,
        "rhino_block_purge": CATEGORY_MODIFICATION,
        "rhino_block_duplicate": CATEGORY_MODIFICATION,
        "rhino_block_nested": CATEGORY_MODIFICATION,
        "rhino_offset_curve": CATEGORY_MODIFICATION,
        "rhino_offset_curve_on_surface": CATEGORY_MODIFICATION,
        "rhino_offset_brep": CATEGORY_MODIFICATION,
        "rhino_split_brep": CATEGORY_MODIFICATION,
        "rhino_trim_brep": CATEGORY_MODIFICATION,
        "rhino_split_face": CATEGORY_MODIFICATION,
        "rhino_split_disjoint_breps": CATEGORY_MODIFICATION,
        "rhino_curvature_curve": CATEGORY_MODIFICATION,
        "rhino_curvature_surface": CATEGORY_MODIFICATION,
        "rhino_draft_angle": CATEGORY_MODIFICATION,
        "rhino_closest_point": CATEGORY_MODIFICATION,
        "rhino_curve_point_at": CATEGORY_MODIFICATION,
        "rhino_curve_tangent": CATEGORY_MODIFICATION,
        "rhino_curve_frame": CATEGORY_MODIFICATION,
        "rhino_surface_normal": CATEGORY_MODIFICATION,
        "rhino_brep_edges": CATEGORY_MODIFICATION,
        "rhino_brep_faces": CATEGORY_MODIFICATION,
        "rhino_brep_vertices": CATEGORY_MODIFICATION,
        "rhino_is_closed": CATEGORY_MODIFICATION,
        "rhino_is_valid": CATEGORY_MODIFICATION,

        # Multi-object tools
        "rhino_boolean": CATEGORY_MULTI_OBJECT,
        "rhino_loft": CATEGORY_MULTI_OBJECT,
        "rhino_sweep": CATEGORY_MULTI_OBJECT,
        "rhino_intersect_curves": CATEGORY_MULTI_OBJECT,
        "rhino_intersect_curve_surface": CATEGORY_MULTI_OBJECT,
        "rhino_intersect_curve_brep": CATEGORY_MULTI_OBJECT,
        "rhino_intersect_breps": CATEGORY_MULTI_OBJECT,
        "rhino_intersect_plane": CATEGORY_MULTI_OBJECT,
        "rhino_project_curve": CATEGORY_MULTI_OBJECT,
        "rhino_pull_curve": CATEGORY_MULTI_OBJECT,
        "rhino_mesh_boolean": CATEGORY_MULTI_OBJECT,

        # Knowledge tools (skip these in exploration)
        "knowledge_query": CATEGORY_KNOWLEDGE,
        "rhino_knowledge_query": CATEGORY_KNOWLEDGE,
        "knowledge_record": CATEGORY_KNOWLEDGE,
    }

    # HTTP endpoint mappings (tool name -> (endpoint, method))
    HTTP_MAPPINGS = {
        "rhino_ping": ("/ping", "GET"),
        "rhino_document": ("/document", "GET"),
        "rhino_layers": ("/layers", "GET"),
        "rhino_objects": ("/objects", "GET"),
        "rhino_selection": ("/selection", "GET"),
        "rhino_geometry": ("/geometry", "GET"),
        "rhino_viewport": ("/viewport", "GET"),
        "rhino_create": ("/create", "POST"),
        "rhino_delete": ("/delete", "DELETE"),
        "rhino_transform": ("/transform", "POST"),
        "rhino_copy": ("/copy", "POST"),
        "rhino_select": ("/select", "POST"),
        "rhino_execute": ("/execute", "POST"),
        "rhino_command": ("/command", "POST"),
        "rhino_layer_create": ("/layer/create", "POST"),
        "rhino_layer_delete": ("/layer/delete", "DELETE"),
        "rhino_layer_visibility": ("/layer/visibility", "POST"),
        "rhino_layer_lock": ("/layer/lock", "POST"),
        "rhino_layer_current": ("/layer/current", "POST"),
        "rhino_usertext_object_set": ("/usertext/object-set", "POST"),
        "rhino_usertext_object_get": ("/usertext/object-get", "POST"),
        "rhino_usertext_document_set": ("/usertext/document-set", "POST"),
        "rhino_usertext_document_get": ("/usertext/document-get", "POST"),
        # Phase 2 surface/curve extension (PR-1 worked example).
        "rhino_create_edge_srf": ("/surface/edge", "POST"),
        "rhino_blend_curves": ("/curve/blend", "POST"),
        # Phase 2 surface/curve extension (PR-2).
        "rhino_create_patch": ("/surface/patch", "POST"),
        # Phase 2 surface/curve extension (PR-3).
        "rhino_create_network_srf": ("/surface/network", "POST"),
        # Phase 2 surface/curve extension (PR-4). Three intent keys share
        # /curve/boolean with operation discriminator — HTTP_MAPPINGS
        # advertises the endpoint uniformly for all 3 tool names; the
        # executor + tool_dispatcher transforms inject the operation.
        "rhino_curve_boolean_union": ("/curve/boolean", "POST"),
        "rhino_curve_boolean_difference": ("/curve/boolean", "POST"),
        "rhino_curve_boolean_intersection": ("/curve/boolean", "POST"),
        # Add more as needed...
    }

    def __init__(self):
        self.tools: dict[str, ToolDefinition] = {}
        self._loaded = False

    async def load(self) -> None:
        """Load all tool definitions from the server module."""
        if self._loaded:
            return

        # Import the server module and get tool list
        from ..server import list_tools

        tools = await list_tools()

        for tool in tools:
            category = self.TOOL_CATEGORIES.get(tool.name, "unknown")
            http_info = self.HTTP_MAPPINGS.get(tool.name)

            defn = ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema,
                category=category,
                requires_objects=category in (self.CATEGORY_MODIFICATION, self.CATEGORY_MULTI_OBJECT),
                http_endpoint=http_info[0] if http_info else None,
                http_method=http_info[1] if http_info else "POST",
            )
            self.tools[tool.name] = defn

        self._loaded = True

    def load_sync(self) -> None:
        """Synchronous version of load."""
        asyncio.run(self.load())

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a specific tool by name."""
        return self.tools.get(name)

    def get_all_tools(self) -> list[ToolDefinition]:
        """Get all tool definitions."""
        return list(self.tools.values())

    def get_by_category(self, category: str) -> list[ToolDefinition]:
        """Get all tools in a specific category."""
        return [t for t in self.tools.values() if t.category == category]

    def get_explorable_tools(self) -> list[ToolDefinition]:
        """Get tools that should be explored (excludes knowledge tools)."""
        return [t for t in self.tools.values() if t.category != self.CATEGORY_KNOWLEDGE]

    def get_stateless_tools(self) -> list[ToolDefinition]:
        """Get stateless tools that can be tested without setup."""
        return self.get_by_category(self.CATEGORY_STATELESS)

    def get_creation_tools(self) -> list[ToolDefinition]:
        """Get tools that create new objects."""
        return self.get_by_category(self.CATEGORY_CREATION)

    def get_modification_tools(self) -> list[ToolDefinition]:
        """Get tools that modify existing objects."""
        return self.get_by_category(self.CATEGORY_MODIFICATION)

    def get_multi_object_tools(self) -> list[ToolDefinition]:
        """Get tools that require multiple objects."""
        return self.get_by_category(self.CATEGORY_MULTI_OBJECT)

    def count_by_category(self) -> dict[str, int]:
        """Count tools in each category."""
        counts: dict[str, int] = {}
        for tool in self.tools.values():
            counts[tool.category] = counts.get(tool.category, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self.tools)

    def __iter__(self):
        return iter(self.tools.values())


# Singleton instance
_registry: ToolRegistry | None = None

def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
