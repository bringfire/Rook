"""
Tool Schema Registry for Intelligent Parameter Generation.

This module provides:
1. Complete tool schemas with required and optional parameters
2. Type information for each parameter
3. Smart default value generation based on param type and context
4. Error message parsing to extract missing parameter names
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("rook.learning.tool_schemas")


@dataclass
class ParamSchema:
    """Schema for a single parameter."""
    name: str
    param_type: str  # "string", "number", "integer", "boolean", "array", "object"
    description: str = ""
    required: bool = False
    default: Any = None
    enum: list[str] | None = None  # For parameters with fixed values
    items_type: str | None = None  # For array parameters

    # For generating smart defaults
    geometry_type: str | None = None  # "id", "ids", "curveId", "brepId", "meshId", etc.


@dataclass
class ToolSchema:
    """Complete schema for an MCP tool."""
    name: str
    description: str
    params: list[ParamSchema] = field(default_factory=list)

    # Setup requirements
    needs_geometry: list[str] = field(default_factory=list)  # ["brep", "curve", "mesh", "subd", "any"]
    geometry_count: int = 1  # How many objects needed (e.g., 2 for boolean ops)

    def get_required_params(self) -> list[ParamSchema]:
        """Get list of required parameters."""
        return [p for p in self.params if p.required]

    def get_optional_params(self) -> list[ParamSchema]:
        """Get list of optional parameters."""
        return [p for p in self.params if not p.required]

    def get_param(self, name: str) -> ParamSchema | None:
        """Get a parameter by name."""
        return next((p for p in self.params if p.name == name), None)


# Registry of all MCP tool schemas
TOOL_SCHEMAS: dict[str, ToolSchema] = {
    # =========================================================================
    # Connection & Document
    # =========================================================================
    "rhino_instances": ToolSchema(
        name="rhino_instances",
        description="List all active Rhino instances",
        params=[],
    ),
    "rhino_ping": ToolSchema(
        name="rhino_ping",
        description="Check if Rhino bridge is running",
        params=[
            ParamSchema("port", "integer", "Specific port to ping"),
        ],
    ),
    "rhino_document": ToolSchema(
        name="rhino_document",
        description="Get document info",
        params=[],
    ),
    "rhino_layers": ToolSchema(
        name="rhino_layers",
        description="Get all layers",
        params=[],
    ),
    "rhino_objects": ToolSchema(
        name="rhino_objects",
        description="Query objects with filters",
        params=[
            ParamSchema("layer", "string", "Filter by layer path"),
            ParamSchema("type", "string", "Filter by object type"),
            ParamSchema("name", "string", "Filter by name"),
            ParamSchema("limit", "integer", "Maximum objects to return", default=100),
            ParamSchema("offset", "integer", "Skip this many objects"),
        ],
    ),

    # =========================================================================
    # Selection
    # =========================================================================
    "rhino_selection": ToolSchema(
        name="rhino_selection",
        description="Get selected objects",
        params=[],
    ),
    "rhino_select": ToolSchema(
        name="rhino_select",
        description="Select objects by ID or layer",
        params=[
            ParamSchema("ids", "array", "Object GUIDs to select", items_type="string", geometry_type="ids"),
            ParamSchema("layer", "string", "Select all objects on this layer"),
            ParamSchema("clear", "boolean", "Clear existing selection first", default=True),
        ],
    ),
    "rhino_select_by_type": ToolSchema(
        name="rhino_select_by_type",
        description="Select objects by geometry type",
        params=[
            ParamSchema("type", "string", "Object type: Point, Curve, Brep, Mesh, etc.", required=True,
                       enum=["Point", "Curve", "Brep", "Mesh", "SubD", "Surface"]),
            ParamSchema("clear", "boolean", "Clear existing selection first", default=True),
        ],
    ),
    "rhino_select_by_name": ToolSchema(
        name="rhino_select_by_name",
        description="Select objects by name pattern",
        params=[
            ParamSchema("namePattern", "string", "Name pattern with wildcards", required=True),
            ParamSchema("clear", "boolean", "Clear existing selection first", default=True),
        ],
    ),
    "rhino_select_all": ToolSchema(
        name="rhino_select_all",
        description="Select all objects",
        params=[],
    ),
    "rhino_select_none": ToolSchema(
        name="rhino_select_none",
        description="Deselect all objects",
        params=[],
    ),
    "rhino_select_invert": ToolSchema(
        name="rhino_select_invert",
        description="Invert the current selection",
        params=[],
    ),
    "rhino_deselect": ToolSchema(
        name="rhino_deselect",
        description="Deselect specific objects",
        params=[
            ParamSchema("ids", "array", "Object GUIDs to deselect", required=True, items_type="string", geometry_type="ids"),
        ],
        needs_geometry=["any"],
    ),

    # =========================================================================
    # Geometry Info
    # =========================================================================
    "rhino_geometry": ToolSchema(
        name="rhino_geometry",
        description="Get detailed geometry info",
        params=[
            ParamSchema("id", "string", "Object GUID", required=True, geometry_type="id"),
        ],
        needs_geometry=["any"],
    ),

    # =========================================================================
    # Script Execution
    # =========================================================================
    "rhino_execute": ToolSchema(
        name="rhino_execute",
        description="Execute Python script in Rhino",
        params=[
            ParamSchema("code", "string", "Python code to execute", required=True),
        ],
    ),
    "rhino_command": ToolSchema(
        name="rhino_command",
        description="Run a Rhino command string (must start with '_' for locale-independent execution)",
        params=[
            ParamSchema("command", "string", "Command string to execute", required=True),
            ParamSchema("echo", "boolean", "Echo command to command line", default=False),
        ],
    ),

    # =========================================================================
    # Viewport
    # =========================================================================
    "rhino_viewport": ToolSchema(
        name="rhino_viewport",
        description="Capture viewport as PNG",
        params=[
            ParamSchema("width", "integer", "Image width in pixels", default=800),
            ParamSchema("height", "integer", "Image height in pixels", default=600),
            ParamSchema("view", "string", "View name", enum=["Perspective", "Top", "Front", "Right"]),
        ],
    ),

    # =========================================================================
    # Geometry Creation
    # =========================================================================
    "rhino_create": ToolSchema(
        name="rhino_create",
        description="Create geometry",
        params=[
            ParamSchema("type", "string", "Geometry type", required=True,
                       enum=["POINT", "LINE", "POLYLINE", "CIRCLE", "ARC", "RECTANGLE", "BOX", "SPHERE", "CYLINDER", "CONE"]),
            ParamSchema("name", "string", "Object name"),
            ParamSchema("layer", "string", "Layer path"),
            ParamSchema("color", "array", "Color as [r,g,b]"),
            ParamSchema("point", "array", "For POINT: [x, y, z]"),
            ParamSchema("start", "array", "For LINE: start point"),
            ParamSchema("end", "array", "For LINE: end point"),
            ParamSchema("points", "array", "For POLYLINE: array of points"),
            ParamSchema("center", "array", "For CIRCLE/ARC/SPHERE/CYLINDER/CONE: center"),
            ParamSchema("radius", "number", "For CIRCLE/ARC/SPHERE/CYLINDER/CONE: radius"),
            ParamSchema("origin", "array", "For RECTANGLE/BOX: origin"),
            ParamSchema("corner", "array", "Alias for RECTANGLE/BOX origin"),
            ParamSchema("corner1", "array", "For BOX: first diagonal corner"),
            ParamSchema("corner2", "array", "For BOX: second diagonal corner"),
            ParamSchema("width", "number", "For RECTANGLE/BOX: width"),
            ParamSchema("height", "number", "For RECTANGLE/BOX/CYLINDER/CONE: height"),
            ParamSchema("depth", "number", "For BOX: depth"),
            ParamSchema("x", "number", "Alias for BOX width"),
            ParamSchema("y", "number", "Alias for BOX depth"),
            ParamSchema("z", "number", "Alias for BOX height"),
            ParamSchema("startAngle", "number", "For ARC: start angle in degrees"),
            ParamSchema("endAngle", "number", "For ARC: end angle in degrees"),
        ],
    ),

    # =========================================================================
    # Geometry Operations
    # =========================================================================
    "rhino_delete": ToolSchema(
        name="rhino_delete",
        description="Delete objects by ID",
        params=[
            ParamSchema("ids", "array", "Object GUIDs to delete", required=True, items_type="string", geometry_type="ids"),
        ],
        needs_geometry=["any"],
    ),
    "rhino_transform": ToolSchema(
        name="rhino_transform",
        description="Transform objects (move, rotate, scale, mirror)",
        params=[
            ParamSchema("ids", "array", "Object GUIDs to transform", required=True, items_type="string", geometry_type="ids"),
            ParamSchema("operation", "string", "Transform type", required=True, enum=["move", "rotate", "scale", "mirror"]),
            ParamSchema("vector", "array", "For move: translation vector [x, y, z]"),
            ParamSchema("angle", "number", "For rotate: angle in degrees"),
            ParamSchema("axis", "array", "For rotate: rotation axis [x, y, z]"),
            ParamSchema("center", "array", "For rotate/scale: center point"),
            ParamSchema("factor", "number", "For scale: scale factor"),
            ParamSchema("planeOrigin", "array", "For mirror: plane origin"),
            ParamSchema("planeNormal", "array", "For mirror: plane normal"),
        ],
        needs_geometry=["any"],
    ),
    "rhino_copy": ToolSchema(
        name="rhino_copy",
        description="Copy objects with optional offset",
        params=[
            ParamSchema("ids", "array", "Object GUIDs to copy", required=True, items_type="string", geometry_type="ids"),
            ParamSchema("offset", "array", "Offset vector [x, y, z]"),
        ],
        needs_geometry=["any"],
    ),

    # =========================================================================
    # Layer Management
    # =========================================================================
    "rhino_layer_create": ToolSchema(
        name="rhino_layer_create",
        description="Create a new layer with optional properties",
        params=[
            ParamSchema("name", "string", "Layer name. Must be a single segment; do not include '::'", required=True),
            ParamSchema("color", "array", "Layer color as [r, g, b]"),
            ParamSchema("plotColor", "array", "Print color as [r, g, b]"),
            ParamSchema("plotWeight", "number", "Print width in mm (0 = default)"),
            ParamSchema("parent", "string", "Existing parent layer name or full path"),
            ParamSchema("visible", "boolean", "Layer visibility", default=True),
            ParamSchema("locked", "boolean", "Layer locked state", default=False),
            ParamSchema("linetype", "string", "Linetype name"),
            ParamSchema("linetypeIndex", "integer", "Linetype table index (-1 = default/Continuous)"),
            ParamSchema("material", "string", "Render material name"),
            ParamSchema("materialIndex", "integer", "Material table index (-1 = no material)"),
        ],
    ),
    "rhino_layer_create_batch": ToolSchema(
        name="rhino_layer_create_batch",
        description="Create multiple layers in one call using explicit key/parentKey relationships. All layers are created under a single undo record (Ctrl+Z reverts all).",
        params=[
            ParamSchema("layers", "array", "Layer specs [{key, name, parentKey?, color?, plotColor?, plotWeight?, linetype?, linetypeIndex?, material?, materialIndex?, visible?, locked?}]", required=True, items_type="object"),
            ParamSchema("rootParent", "string", "Optional existing parent layer name or full path for top-level batch items"),
        ],
    ),
    "rhino_layer_delete": ToolSchema(
        name="rhino_layer_delete",
        description="Delete an empty layer",
        params=[
            ParamSchema("name", "string", "Layer name to delete", required=True),
        ],
    ),
    "rhino_layer_visibility": ToolSchema(
        name="rhino_layer_visibility",
        description="Set layer visibility",
        params=[
            ParamSchema("name", "string", "Layer name", required=True),
            ParamSchema("visible", "boolean", "Visibility state", required=True),
        ],
    ),
    "rhino_layer_lock": ToolSchema(
        name="rhino_layer_lock",
        description="Set layer lock state",
        params=[
            ParamSchema("name", "string", "Layer name", required=True),
            ParamSchema("locked", "boolean", "Lock state", required=True),
        ],
    ),
    "rhino_layer_current": ToolSchema(
        name="rhino_layer_current",
        description="Set the current layer",
        params=[
            ParamSchema("name", "string", "Layer name", required=True),
        ],
    ),
    "rhino_layer_set_properties": ToolSchema(
        name="rhino_layer_set_properties",
        description="Set any combination of layer properties in a single call",
        params=[
            ParamSchema("name", "string", "Target layer name or full path", required=True),
            ParamSchema("set", "object", "Properties to modify: rename, parent, color, plotColor, plotWeight, linetype, linetypeIndex, material, materialIndex, visible, locked", required=True),
        ],
    ),
    "rhino_layer_set_properties_batch": ToolSchema(
        name="rhino_layer_set_properties_batch",
        description="Batch apply layer property changes to multiple layers in one call. Best-effort per-item semantics; single UndoScope wraps the batch. Each item has {name, set} matching the single-target shape.",
        params=[
            ParamSchema("items", "array", "Array of {name, set} items. Same set shape as rhino_layer_set_properties.", required=True),
            ParamSchema("redraw", "boolean", "Redraw viewport after batch (default true)", required=False),
        ],
    ),
    "rhino_layer_rename": ToolSchema(
        name="rhino_layer_rename",
        description="Rename a layer. All objects remain on the layer.",
        params=[
            ParamSchema("name", "string", "Current layer name or full path", required=True),
            ParamSchema("newName", "string", "New single-segment name", required=True),
        ],
    ),
    "rhino_layer_move_objects": ToolSchema(
        name="rhino_layer_move_objects",
        description="Move all objects from source layer to target layer",
        params=[
            ParamSchema("source", "string", "Source layer name or full path", required=True),
            ParamSchema("target", "string", "Target layer name or full path", required=True),
        ],
    ),
    "rhino_layer_merge": ToolSchema(
        name="rhino_layer_merge",
        description="Move all objects from source to target, then delete source layer",
        params=[
            ParamSchema("source", "string", "Source layer to merge away", required=True),
            ParamSchema("target", "string", "Target layer to receive objects", required=True),
        ],
    ),
    "rhino_layer_dependencies": ToolSchema(
        name="rhino_layer_dependencies",
        description="Analyze what holds a layer alive: objects, block refs, child layers, canDelete flag",
        params=[
            ParamSchema("name", "string", "Layer name or full path to analyze", required=True),
        ],
    ),

    # =========================================================================
    # Material / Linetype Audit
    # =========================================================================
    "rhino_materials": ToolSchema(
        name="rhino_materials",
        description="List all materials with usage reporting (objectCount, layerCount, blockDefinitionObjectCount, canPurge)",
        params=[],
    ),
    "rhino_material_purge": ToolSchema(
        name="rhino_material_purge",
        description="Purge unused materials. Returns purged names and skipped names with reasons.",
        params=[],
    ),
    "rhino_linetypes": ToolSchema(
        name="rhino_linetypes",
        description="List all linetypes with usage reporting (objectCount, layerCount, blockDefinitionObjectCount, canPurge)",
        params=[],
    ),
    "rhino_linetype_purge": ToolSchema(
        name="rhino_linetype_purge",
        description="Purge unused linetypes. Returns purged names and skipped names with reasons.",
        params=[],
    ),
    "rhino_block_layer_census": ToolSchema(
        name="rhino_block_layer_census",
        description="Report which layers each block definition's geometry lives on with per-layer object counts",
        params=[],
    ),

    # =========================================================================
    # Measurement
    # =========================================================================
    "rhino_measure_distance": ToolSchema(
        name="rhino_measure_distance",
        description="Measure distance between two points or objects",
        params=[
            ParamSchema("from", "array", "Start point [x, y, z]"),
            ParamSchema("to", "array", "End point [x, y, z]"),
            ParamSchema("fromId", "string", "First object GUID", geometry_type="id"),
            ParamSchema("toId", "string", "Second object GUID", geometry_type="id"),
        ],
    ),
    "rhino_measure_area": ToolSchema(
        name="rhino_measure_area",
        description="Calculate surface area",
        params=[
            ParamSchema("id", "string", "Object GUID", required=True, geometry_type="id"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_measure_volume": ToolSchema(
        name="rhino_measure_volume",
        description="Calculate volume of closed solid",
        params=[
            ParamSchema("id", "string", "Object GUID (must be closed solid)", required=True, geometry_type="id"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_measure_length": ToolSchema(
        name="rhino_measure_length",
        description="Calculate length of a curve",
        params=[
            ParamSchema("id", "string", "Curve object GUID", required=True, geometry_type="curveId"),
        ],
        needs_geometry=["curve"],
    ),
    "rhino_measure_bbox": ToolSchema(
        name="rhino_measure_bbox",
        description="Get bounding box of an object",
        params=[
            ParamSchema("id", "string", "Object GUID", required=True, geometry_type="id"),
        ],
        needs_geometry=["any"],
    ),
    "rhino_measure_centroid": ToolSchema(
        name="rhino_measure_centroid",
        description="Get centroid/center point",
        params=[
            ParamSchema("id", "string", "Object GUID", required=True, geometry_type="id"),
        ],
        needs_geometry=["any"],
    ),

    # =========================================================================
    # Boolean Operations
    # =========================================================================
    "rhino_boolean": ToolSchema(
        name="rhino_boolean",
        description="Boolean operations on solids",
        params=[
            ParamSchema("operation", "string", "Boolean operation", required=True, enum=["union", "difference", "intersection"]),
            ParamSchema("ids", "array", "Object GUIDs for union/intersection", items_type="string", geometry_type="ids"),
            ParamSchema("targetId", "string", "Target object GUID for difference", geometry_type="brepId"),
            ParamSchema("toolIds", "array", "Tool object GUIDs for difference", items_type="string", geometry_type="ids"),
            ParamSchema("deleteInputs", "boolean", "Delete input objects after operation", default=True),
        ],
        needs_geometry=["brep"],
        geometry_count=2,
    ),

    # =========================================================================
    # Surface Creation
    # =========================================================================
    "rhino_loft": ToolSchema(
        name="rhino_loft",
        description="Create lofted surface through curves",
        params=[
            ParamSchema("curveIds", "array", "Curve GUIDs to loft through", required=True, items_type="string", geometry_type="curveIds"),
            ParamSchema("closed", "boolean", "Create closed loft", default=False),
            ParamSchema("name", "string", "Object name"),
            ParamSchema("layer", "string", "Layer path"),
        ],
        needs_geometry=["curve"],
        geometry_count=2,
    ),
    "rhino_sweep": ToolSchema(
        name="rhino_sweep",
        description="Create swept surface along rail",
        params=[
            ParamSchema("railId", "string", "Rail curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("profileIds", "array", "Profile curve GUIDs", required=True, items_type="string", geometry_type="curveIds"),
            ParamSchema("name", "string", "Object name"),
            ParamSchema("layer", "string", "Layer path"),
        ],
        needs_geometry=["curve"],
        geometry_count=2,
    ),
    "rhino_extrude": ToolSchema(
        name="rhino_extrude",
        description="Extrude curve or surface",
        params=[
            ParamSchema("curveId", "string", "Curve GUID to extrude", required=True, geometry_type="curveId"),
            ParamSchema("direction", "array", "Extrusion direction [x, y, z]"),
            ParamSchema("distance", "number", "Extrusion distance"),
            ParamSchema("cap", "boolean", "Cap ends if curve is closed", default=True),
            ParamSchema("name", "string", "Object name"),
            ParamSchema("layer", "string", "Layer path"),
        ],
        needs_geometry=["curve"],
    ),

    # =========================================================================
    # Import/Export
    # =========================================================================
    "rhino_import": ToolSchema(
        name="rhino_import",
        description="Import a file into Rhino",
        params=[
            ParamSchema("path", "string", "File path to import", required=True),
            ParamSchema("targetLayer", "string", "Layer to place imported objects"),
        ],
    ),
    "rhino_export": ToolSchema(
        name="rhino_export",
        description="Export objects to file",
        params=[
            ParamSchema("path", "string", "File path to export to", required=True),
            ParamSchema("ids", "array", "Object GUIDs to export", items_type="string", geometry_type="ids"),
            ParamSchema("selection", "boolean", "Export selected objects", default=False),
        ],
    ),

    # =========================================================================
    # Groups
    # =========================================================================
    "rhino_group": ToolSchema(
        name="rhino_group",
        description="Create a group from objects",
        params=[
            ParamSchema("ids", "array", "Object GUIDs to group", required=True, items_type="string", geometry_type="ids"),
            ParamSchema("name", "string", "Group name"),
        ],
        needs_geometry=["any"],
        geometry_count=2,
    ),

    # =========================================================================
    # Blocks
    # =========================================================================
    "rhino_blocks": ToolSchema(
        name="rhino_blocks",
        description="List all block definitions",
        params=[],
    ),
    "rhino_block_create": ToolSchema(
        name="rhino_block_create",
        description="Create a block definition (aliases: objectIds, point/insertionPoint, deleteObjects)",
        params=[
            ParamSchema("ids", "array", "Object GUIDs to include", required=True, items_type="string", geometry_type="ids"),
            ParamSchema("objectIds", "array", "Alias for ids", items_type="string", geometry_type="ids"),
            ParamSchema("name", "string", "Block name", required=True),
            ParamSchema("basePoint", "array", "Block base point [x, y, z]"),
            ParamSchema("point", "array", "Alias for basePoint"),
            ParamSchema("insertionPoint", "array", "Alias for basePoint"),
            ParamSchema("replaceWithInstance", "boolean", "Replace objects with block instance", default=True),
            ParamSchema("deleteObjects", "boolean", "Legacy alias for replaceWithInstance"),
        ],
        needs_geometry=["any"],
    ),
    "rhino_block_insert": ToolSchema(
        name="rhino_block_insert",
        description="Insert a block instance (aliases: insertionPoint, basePoint)",
        params=[
            ParamSchema("name", "string", "Block definition name", required=True),
            ParamSchema("point", "array", "Insertion point [x, y, z]"),
            ParamSchema("insertionPoint", "array", "Alias for point"),
            ParamSchema("basePoint", "array", "Alias for point"),
            ParamSchema("scale", "number", "Uniform scale factor", default=1.0),
            ParamSchema("rotation", "number", "Rotation angle in degrees", default=0),
        ],
    ),
    "rhino_block_explode": ToolSchema(
        name="rhino_block_explode",
        description="Explode a block instance",
        params=[
            ParamSchema("id", "string", "Block instance GUID", required=True, geometry_type="id"),
        ],
        needs_geometry=["any"],
    ),
    "rhino_block_delete": ToolSchema(
        name="rhino_block_delete",
        description="Delete a block definition",
        params=[
            ParamSchema("name", "string", "Block definition name", required=True),
            ParamSchema("deleteInstances", "boolean", "Also delete all instances", default=True),
        ],
    ),
    "rhino_block_info": ToolSchema(
        name="rhino_block_info",
        description="Get detailed block information",
        params=[
            ParamSchema("name", "string", "Block name", required=True),
        ],
    ),
    "rhino_block_rename": ToolSchema(
        name="rhino_block_rename",
        description="Rename a block definition",
        params=[
            ParamSchema("name", "string", "Current block name", required=True),
            ParamSchema("newName", "string", "New block name", required=True),
        ],
    ),
    "rhino_block_rebase": ToolSchema(
        name="rhino_block_rebase",
        description="Rebase block definition geometry while compensating instances so world-space geometry does not move; rejects nested-use definitions for now",
        params=[
            ParamSchema("name", "string", "Block definition name", required=True),
            ParamSchema("anchor", "string", "Reference point from definition bbox", enum=["bbox_min", "bbox_center", "bbox_max"], default="bbox_min"),
            ParamSchema("targetPoint", "array", "Target point [x, y, z] for the chosen anchor"),
            ParamSchema("axes", "array", "Axes to rebase", items_type="string"),
            ParamSchema("dryRun", "boolean", "When true, report translation only", default=True),
            ParamSchema("verbose", "boolean", "Include old/new instance ID mappings on execute", default=False),
        ],
    ),

    "rhino_block_rebase_recursive": ToolSchema(
        name="rhino_block_rebase_recursive",
        description="Rebase a leaf block definition and compensate direct parent definitions that reference it as a nested block, plus direct document instances of the leaf",
        params=[
            ParamSchema("name", "string", "Leaf block definition name (must have at least one parent)", required=True),
            ParamSchema("anchor", "string", "Reference point from definition bbox", enum=["bbox_min", "bbox_center", "bbox_max"], default="bbox_min"),
            ParamSchema("targetPoint", "array", "Target point [x, y, z] for the chosen anchor"),
            ParamSchema("axes", "array", "Axes to rebase", items_type="string"),
            ParamSchema("dryRun", "boolean", "When true, return the mutation plan without executing", default=True),
            ParamSchema("expectedPlanHash", "string", "Required on execute; must match planHash from dry-run"),
            ParamSchema("verbose", "boolean", "Include leafRefObjectIndices per parent", default=False),
        ],
    ),

    # =========================================================================
    # Text & Dimensions
    # =========================================================================
    "rhino_text": ToolSchema(
        name="rhino_text",
        description="Create text annotation",
        params=[
            ParamSchema("text", "string", "Text content", required=True),
            ParamSchema("point", "array", "Location [x, y, z]", required=True),
            ParamSchema("height", "number", "Text height", required=True),
            ParamSchema("font", "string", "Font name"),
            ParamSchema("bold", "boolean", "Bold text"),
            ParamSchema("italic", "boolean", "Italic text"),
            ParamSchema("name", "string", "Object name"),
            ParamSchema("layer", "string", "Layer path"),
        ],
    ),
    "rhino_dimension": ToolSchema(
        name="rhino_dimension",
        description="Create dimension annotation",
        params=[
            ParamSchema("type", "string", "Dimension type", required=True,
                       enum=["DIMENSION_LINEAR", "DIMENSION_ALIGNED", "DIMENSION_RADIUS", "DIMENSION_DIAMETER", "DIMENSION_ANGLE"]),
            ParamSchema("start", "array", "Start point for linear"),
            ParamSchema("end", "array", "End point for linear"),
            ParamSchema("offset", "number", "Dimension line offset"),
            ParamSchema("curveId", "string", "Curve GUID for radius/diameter", geometry_type="curveId"),
            ParamSchema("anglePoint", "array", "Point on curve for radius/diameter"),
            ParamSchema("center", "array", "Center point for angle dimensions"),
            ParamSchema("dimLocation", "array", "Dimension arc location for angle"),
            ParamSchema("name", "string", "Object name"),
            ParamSchema("layer", "string", "Layer path"),
        ],
    ),

    # =========================================================================
    # Document Operations
    # =========================================================================
    "rhino_document_ops": ToolSchema(
        name="rhino_document_ops",
        description="Document operations (undo, redo, save, new, set_units). Alias: operation -> action",
        params=[
            ParamSchema("action", "string", "The operation", enum=["undo", "redo", "save", "new", "set_units"]),
            ParamSchema("operation", "string", "Alias for action", enum=["undo", "redo", "save", "new", "set_units"]),
            ParamSchema("path", "string", "File path for save action"),
            ParamSchema("units", "string", "Unit system for set_units", enum=["Millimeters", "Centimeters", "Meters", "Inches", "Feet"]),
        ],
    ),

    # =========================================================================
    # Curve Operations
    # =========================================================================
    "rhino_curve_ops": ToolSchema(
        name="rhino_curve_ops",
        description="Curve operations (join, explode, divide, extend, trim, split, rebuild, fillet)",
        params=[
            ParamSchema("action", "string", "The operation", required=True,
                       enum=["join", "explode", "divide", "extend", "trim", "split", "rebuild", "fillet"]),
            ParamSchema("id", "string", "Curve GUID (for single-curve operations)", geometry_type="curveId"),
            ParamSchema("ids", "array", "Curve GUIDs (for join)", items_type="string", geometry_type="curveIds"),
            ParamSchema("count", "integer", "Number of division points (for divide)"),
            ParamSchema("end", "integer", "Which end to extend: 0=start, 1=end"),
            ParamSchema("length", "number", "Extension length"),
            ParamSchema("parameter", "number", "Curve parameter (for trim/split)"),
            ParamSchema("point", "array", "Point [x, y, z] for trim"),
            ParamSchema("degree", "integer", "Curve degree (for rebuild)"),
            ParamSchema("pointCount", "integer", "Number of control points (for rebuild)"),
            ParamSchema("id1", "string", "First curve GUID (for fillet)", geometry_type="curveId"),
            ParamSchema("id2", "string", "Second curve GUID (for fillet)", geometry_type="curveId"),
            ParamSchema("radius", "number", "Fillet radius"),
        ],
        needs_geometry=["curve"],
    ),

    # =========================================================================
    # Material Operations
    # =========================================================================
    "rhino_material_ops": ToolSchema(
        name="rhino_material_ops",
        description="Material operations (list, create, delete, assign)",
        params=[
            ParamSchema("action", "string", "The operation", required=True, enum=["list", "create", "delete", "assign"]),
            ParamSchema("name", "string", "Material name"),
            ParamSchema("color", "array", "RGB color [r, g, b]"),
            ParamSchema("transparency", "number", "Transparency 0-1"),
            ParamSchema("reflectivity", "number", "Reflectivity 0-1"),
            ParamSchema("shininess", "number", "Shininess 0-1"),
            ParamSchema("id", "string", "Object GUID to assign material to", geometry_type="id"),
            ParamSchema("ids", "array", "Object GUIDs to assign material to", items_type="string", geometry_type="ids"),
        ],
    ),

    # =========================================================================
    # Intersection Operations
    # =========================================================================
    "rhino_intersect_curves": ToolSchema(
        name="rhino_intersect_curves",
        description="Find intersections between two curves",
        params=[
            ParamSchema("curveId1", "string", "First curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("curveId2", "string", "Second curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("tolerance", "number", "Intersection tolerance"),
        ],
        needs_geometry=["curve"],
        geometry_count=2,
    ),
    "rhino_intersect_curve_surface": ToolSchema(
        name="rhino_intersect_curve_surface",
        description="Find intersections between curve and surface",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("surfaceId", "string", "Surface/Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("tolerance", "number", "Intersection tolerance"),
        ],
        needs_geometry=["curve", "brep"],
    ),
    "rhino_intersect_curve_brep": ToolSchema(
        name="rhino_intersect_curve_brep",
        description="Find intersections between curve and brep",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("tolerance", "number", "Intersection tolerance"),
        ],
        needs_geometry=["curve", "brep"],
    ),
    "rhino_intersect_breps": ToolSchema(
        name="rhino_intersect_breps",
        description="Find intersections between two breps",
        params=[
            ParamSchema("brepId1", "string", "First Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("brepId2", "string", "Second Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("tolerance", "number", "Intersection tolerance"),
        ],
        needs_geometry=["brep"],
        geometry_count=2,
    ),
    "rhino_intersect_plane": ToolSchema(
        name="rhino_intersect_plane",
        description="Intersect brep with a plane",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("planeOrigin", "array", "Plane origin [x, y, z]", required=True),
            ParamSchema("planeNormal", "array", "Plane normal [x, y, z]", required=True),
            ParamSchema("tolerance", "number", "Intersection tolerance"),
        ],
        needs_geometry=["brep"],
    ),

    # =========================================================================
    # Projection Operations
    # =========================================================================
    "rhino_project_curve": ToolSchema(
        name="rhino_project_curve",
        description="Project curves onto brep along direction",
        params=[
            ParamSchema("curveIds", "array", "Curve GUIDs to project", required=True, items_type="string", geometry_type="curveIds"),
            ParamSchema("brepIds", "array", "Brep GUIDs to project onto", required=True, items_type="string", geometry_type="ids"),
            ParamSchema("direction", "array", "Projection direction [x, y, z]", required=True),
            ParamSchema("tolerance", "number", "Projection tolerance"),
        ],
        needs_geometry=["curve", "brep"],
    ),
    "rhino_pull_curve": ToolSchema(
        name="rhino_pull_curve",
        description="Pull curve to closest point on brep",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("faceIndex", "integer", "Face index on brep", default=0),
            ParamSchema("tolerance", "number", "Pull tolerance"),
        ],
        needs_geometry=["curve", "brep"],
    ),
    "rhino_offset_curve": ToolSchema(
        name="rhino_offset_curve",
        description="Offset a curve in a plane",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("distance", "number", "Offset distance", required=True),
            ParamSchema("plane", "string", "Offset plane"),
            ParamSchema("cornerStyle", "string", "How to handle corners", enum=["None", "Sharp", "Round", "Smooth", "Chamfer"]),
            ParamSchema("tolerance", "number", "Offset tolerance"),
        ],
        needs_geometry=["curve"],
    ),
    "rhino_offset_curve_on_surface": ToolSchema(
        name="rhino_offset_curve_on_surface",
        description="Offset curve on a surface",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("surfaceId", "string", "Surface GUID", required=True, geometry_type="brepId"),
            ParamSchema("distance", "number", "Offset distance", required=True),
            ParamSchema("tolerance", "number", "Offset tolerance"),
        ],
        needs_geometry=["curve", "brep"],
    ),
    "rhino_offset_brep": ToolSchema(
        name="rhino_offset_brep",
        description="Create offset/shell of a brep",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("distance", "number", "Offset distance", required=True),
            ParamSchema("solid", "boolean", "Create solid", default=True),
            ParamSchema("extend", "boolean", "Extend edges", default=True),
            ParamSchema("shrink", "boolean", "Shrink faces", default=False),
            ParamSchema("tolerance", "number", "Offset tolerance"),
        ],
        needs_geometry=["brep"],
    ),

    # =========================================================================
    # Split/Trim Operations
    # =========================================================================
    "rhino_split_brep": ToolSchema(
        name="rhino_split_brep",
        description="Split brep with cutters or plane",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("cutterIds", "array", "Cutter object GUIDs", items_type="string", geometry_type="ids"),
            ParamSchema("planeOrigin", "array", "Cutting plane origin"),
            ParamSchema("planeNormal", "array", "Cutting plane normal"),
            ParamSchema("tolerance", "number", "Split tolerance"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_trim_brep": ToolSchema(
        name="rhino_trim_brep",
        description="Trim brep with plane, keeping one side",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("planeOrigin", "array", "Cutting plane origin", required=True),
            ParamSchema("planeNormal", "array", "Cutting plane normal", required=True),
            ParamSchema("keepSide", "string", "Which side to keep", required=True, enum=["positive", "negative"]),
            ParamSchema("tolerance", "number", "Trim tolerance"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_split_face": ToolSchema(
        name="rhino_split_face",
        description="Split brep face with curves",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("faceIndex", "integer", "Face index to split", required=True),
            ParamSchema("curveIds", "array", "Curve GUIDs to split with", required=True, items_type="string", geometry_type="curveIds"),
            ParamSchema("tolerance", "number", "Split tolerance"),
        ],
        needs_geometry=["brep", "curve"],
    ),
    "rhino_split_disjoint_breps": ToolSchema(
        name="rhino_split_disjoint_breps",
        description="Separate disjoint Breps into individual connected components. Filter by ids array, layer name, or process all Breps.",
        params=[
            ParamSchema("ids", "array", "Optional: specific Brep GUIDs to check", items_type="string"),
            ParamSchema("layer", "string", "Optional: only process Breps on this layer"),
            ParamSchema("redraw", "boolean", "Redraw after split (default true)"),
        ],
    ),

    # =========================================================================
    # SubD Operations
    # =========================================================================
    "rhino_subd_box": ToolSchema(
        name="rhino_subd_box",
        description="Create a SubD box",
        params=[
            ParamSchema("width", "number", "Width in X direction", required=True),
            ParamSchema("depth", "number", "Depth in Y direction", required=True),
            ParamSchema("height", "number", "Height in Z direction", required=True),
            ParamSchema("origin", "array", "Origin point [x, y, z]"),
            ParamSchema("xFaces", "integer", "Face divisions in X", default=2),
            ParamSchema("yFaces", "integer", "Face divisions in Y", default=2),
            ParamSchema("zFaces", "integer", "Face divisions in Z", default=2),
        ],
    ),
    "rhino_subd_sphere": ToolSchema(
        name="rhino_subd_sphere",
        description="Create a SubD sphere",
        params=[
            ParamSchema("radius", "number", "Sphere radius", required=True),
            ParamSchema("center", "array", "Center point [x, y, z]"),
            ParamSchema("divisions", "integer", "Subdivision level", default=3),
        ],
    ),
    "rhino_subd_cylinder": ToolSchema(
        name="rhino_subd_cylinder",
        description="Create a SubD cylinder",
        params=[
            ParamSchema("radius", "number", "Cylinder radius", required=True),
            ParamSchema("height", "number", "Cylinder height", required=True),
            ParamSchema("center", "array", "Base center point [x, y, z]"),
            ParamSchema("circumferenceFaces", "integer", "Faces around circumference", default=8),
            ParamSchema("heightFaces", "integer", "Face divisions in height", default=1),
        ],
    ),
    "rhino_subd_from_mesh": ToolSchema(
        name="rhino_subd_from_mesh",
        description="Create SubD from mesh",
        params=[
            ParamSchema("meshId", "string", "Mesh GUID", required=True, geometry_type="meshId"),
            ParamSchema("interpolateVertices", "boolean", "Interpolate mesh vertices", default=False),
        ],
        needs_geometry=["mesh"],
    ),
    "rhino_subd_from_surface": ToolSchema(
        name="rhino_subd_from_surface",
        description="Create SubD from surface/brep",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("method", "string", "Conversion method", enum=["Pack", "Interpolate"]),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_subd_subdivide": ToolSchema(
        name="rhino_subd_subdivide",
        description="Subdivide a SubD",
        params=[
            ParamSchema("subdId", "string", "SubD GUID", required=True, geometry_type="subdId"),
            ParamSchema("level", "integer", "Number of subdivision levels", default=1),
        ],
        needs_geometry=["subd"],
    ),
    "rhino_subd_crease": ToolSchema(
        name="rhino_subd_crease",
        description="Set edge creases on a SubD",
        params=[
            ParamSchema("subdId", "string", "SubD GUID", required=True, geometry_type="subdId"),
            ParamSchema("edgeIndices", "array", "Edge indices to modify", required=True, items_type="integer"),
            ParamSchema("crease", "boolean", "True to add crease, false to remove", default=True),
        ],
        needs_geometry=["subd"],
    ),
    "rhino_subd_to_brep": ToolSchema(
        name="rhino_subd_to_brep",
        description="Convert SubD to NURBS Brep",
        params=[
            ParamSchema("subdId", "string", "SubD GUID", required=True, geometry_type="subdId"),
            ParamSchema("packFaces", "boolean", "Pack faces for efficiency", default=False),
        ],
        needs_geometry=["subd"],
    ),
    "rhino_subd_to_mesh": ToolSchema(
        name="rhino_subd_to_mesh",
        description="Convert SubD to mesh",
        params=[
            ParamSchema("subdId", "string", "SubD GUID", required=True, geometry_type="subdId"),
            ParamSchema("density", "integer", "Mesh density 0-5", default=1),
        ],
        needs_geometry=["subd"],
    ),

    # =========================================================================
    # Mesh Operations
    # =========================================================================
    "rhino_mesh_from_brep": ToolSchema(
        name="rhino_mesh_from_brep",
        description="Create mesh from Brep/Surface",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("density", "number", "Mesh density", default=0.5),
            ParamSchema("minEdgeLength", "number", "Minimum edge length"),
            ParamSchema("maxEdgeLength", "number", "Maximum edge length"),
            ParamSchema("jagged", "boolean", "Allow jagged seams"),
            ParamSchema("simple", "boolean", "Use simple/minimal meshing"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_mesh_box": ToolSchema(
        name="rhino_mesh_box",
        description="Create a mesh box",
        params=[
            ParamSchema("width", "number", "Width in X direction", required=True),
            ParamSchema("depth", "number", "Depth in Y direction", required=True),
            ParamSchema("height", "number", "Height in Z direction", required=True),
            ParamSchema("origin", "array", "Origin point [x, y, z]"),
            ParamSchema("xCount", "integer", "Subdivisions in X", default=1),
            ParamSchema("yCount", "integer", "Subdivisions in Y", default=1),
            ParamSchema("zCount", "integer", "Subdivisions in Z", default=1),
        ],
    ),
    "rhino_mesh_sphere": ToolSchema(
        name="rhino_mesh_sphere",
        description="Create a mesh sphere",
        params=[
            ParamSchema("radius", "number", "Sphere radius", required=True),
            ParamSchema("center", "array", "Center point [x, y, z]"),
            ParamSchema("rings", "integer", "Number of rings", default=10),
            ParamSchema("segments", "integer", "Number of segments", default=10),
        ],
    ),
    "rhino_mesh_cylinder": ToolSchema(
        name="rhino_mesh_cylinder",
        description="Create a mesh cylinder",
        params=[
            ParamSchema("radius", "number", "Cylinder radius", required=True),
            ParamSchema("height", "number", "Cylinder height", required=True),
            ParamSchema("center", "array", "Base center point [x, y, z]"),
            ParamSchema("vertical", "integer", "Vertical divisions", default=10),
            ParamSchema("around", "integer", "Divisions around circumference", default=20),
        ],
    ),
    "rhino_mesh_cone": ToolSchema(
        name="rhino_mesh_cone",
        description="Create a mesh cone",
        params=[
            ParamSchema("radius", "number", "Cone base radius", required=True),
            ParamSchema("height", "number", "Cone height", required=True),
            ParamSchema("center", "array", "Base center point [x, y, z]"),
            ParamSchema("vertical", "integer", "Vertical divisions", default=10),
            ParamSchema("around", "integer", "Divisions around circumference", default=20),
        ],
    ),
    "rhino_mesh_boolean": ToolSchema(
        name="rhino_mesh_boolean",
        description="Boolean operations on meshes",
        params=[
            ParamSchema("operation", "string", "Boolean operation", required=True, enum=["union", "difference", "intersection"]),
            ParamSchema("meshIds", "array", "Mesh GUIDs (at least 2)", required=True, items_type="string", geometry_type="meshIds"),
            ParamSchema("deleteInputs", "boolean", "Delete input meshes", default=True),
        ],
        needs_geometry=["mesh"],
        geometry_count=2,
    ),
    "rhino_mesh_reduce": ToolSchema(
        name="rhino_mesh_reduce",
        description="Reduce mesh face count",
        params=[
            ParamSchema("meshId", "string", "Mesh GUID", required=True, geometry_type="meshId"),
            ParamSchema("targetCount", "integer", "Target face count", required=True),
            ParamSchema("accuracy", "integer", "Accuracy 1-10", default=5),
        ],
        needs_geometry=["mesh"],
    ),
    "rhino_quad_remesh": ToolSchema(
        name="rhino_quad_remesh",
        description="QuadRemesh for better topology",
        params=[
            ParamSchema("meshId", "string", "Mesh GUID", required=True, geometry_type="meshId"),
            ParamSchema("targetQuadCount", "integer", "Target quad count", default=1000),
            ParamSchema("adaptive", "boolean", "Use adaptive sizing", default=True),
        ],
        needs_geometry=["mesh"],
    ),
    "rhino_mesh_repair": ToolSchema(
        name="rhino_mesh_repair",
        description="Repair a mesh",
        params=[
            ParamSchema("meshId", "string", "Mesh GUID", required=True, geometry_type="meshId"),
            ParamSchema("fillHoles", "boolean", "Fill holes", default=True),
            ParamSchema("rebuildNormals", "boolean", "Rebuild normals", default=True),
        ],
        needs_geometry=["mesh"],
    ),
    "rhino_mesh_smooth": ToolSchema(
        name="rhino_mesh_smooth",
        description="Smooth a mesh",
        params=[
            ParamSchema("meshId", "string", "Mesh GUID", required=True, geometry_type="meshId"),
            ParamSchema("factor", "number", "Smoothing factor 0-1", default=0.5),
            ParamSchema("iterations", "integer", "Number of iterations", default=1),
        ],
        needs_geometry=["mesh"],
    ),
    "rhino_mesh_weld": ToolSchema(
        name="rhino_mesh_weld",
        description="Weld mesh vertices",
        params=[
            ParamSchema("meshId", "string", "Mesh GUID", required=True, geometry_type="meshId"),
            ParamSchema("angle", "number", "Weld angle in degrees", default=22.5),
        ],
        needs_geometry=["mesh"],
    ),
    "rhino_mesh_unweld": ToolSchema(
        name="rhino_mesh_unweld",
        description="Unweld mesh vertices",
        params=[
            ParamSchema("meshId", "string", "Mesh GUID", required=True, geometry_type="meshId"),
            ParamSchema("angle", "number", "Unweld angle in degrees", default=22.5),
        ],
        needs_geometry=["mesh"],
    ),

    # =========================================================================
    # Analysis Operations
    # =========================================================================
    "rhino_curvature_curve": ToolSchema(
        name="rhino_curvature_curve",
        description="Get curvature at a parameter on a curve",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("parameter", "number", "Normalized parameter 0-1", required=True),
        ],
        needs_geometry=["curve"],
    ),
    "rhino_curvature_surface": ToolSchema(
        name="rhino_curvature_surface",
        description="Get curvature at UV on a surface",
        params=[
            ParamSchema("surfaceId", "string", "Surface/Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("u", "number", "Normalized U parameter 0-1", required=True),
            ParamSchema("v", "number", "Normalized V parameter 0-1", required=True),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_draft_angle": ToolSchema(
        name="rhino_draft_angle",
        description="Analyze draft angles on a brep",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("direction", "array", "Pull direction [x, y, z]"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_closest_point": ToolSchema(
        name="rhino_closest_point",
        description="Find closest point on geometry",
        params=[
            ParamSchema("id", "string", "Object GUID", required=True, geometry_type="id"),
            ParamSchema("point", "array", "Test point [x, y, z]", required=True),
        ],
        needs_geometry=["any"],
    ),
    "rhino_curve_point_at": ToolSchema(
        name="rhino_curve_point_at",
        description="Get point at parameter on a curve",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("parameter", "number", "Normalized parameter 0-1", required=True),
        ],
        needs_geometry=["curve"],
    ),
    "rhino_curve_tangent": ToolSchema(
        name="rhino_curve_tangent",
        description="Get tangent at parameter on a curve",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("parameter", "number", "Normalized parameter 0-1", required=True),
        ],
        needs_geometry=["curve"],
    ),
    "rhino_curve_frame": ToolSchema(
        name="rhino_curve_frame",
        description="Get frame at parameter on a curve",
        params=[
            ParamSchema("curveId", "string", "Curve GUID", required=True, geometry_type="curveId"),
            ParamSchema("parameter", "number", "Normalized parameter 0-1", required=True),
        ],
        needs_geometry=["curve"],
    ),
    "rhino_surface_normal": ToolSchema(
        name="rhino_surface_normal",
        description="Get normal at UV on a surface",
        params=[
            ParamSchema("surfaceId", "string", "Surface/Brep GUID", required=True, geometry_type="brepId"),
            ParamSchema("u", "number", "Normalized U parameter 0-1", required=True),
            ParamSchema("v", "number", "Normalized V parameter 0-1", required=True),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_brep_edges": ToolSchema(
        name="rhino_brep_edges",
        description="Get edge information for a brep",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_brep_faces": ToolSchema(
        name="rhino_brep_faces",
        description="Get face information for a brep",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_brep_vertices": ToolSchema(
        name="rhino_brep_vertices",
        description="Get vertex information for a brep",
        params=[
            ParamSchema("brepId", "string", "Brep GUID", required=True, geometry_type="brepId"),
        ],
        needs_geometry=["brep"],
    ),
    "rhino_is_closed": ToolSchema(
        name="rhino_is_closed",
        description="Check if geometry is closed/solid",
        params=[
            ParamSchema("id", "string", "Object GUID", required=True, geometry_type="id"),
        ],
        needs_geometry=["any"],
    ),
    "rhino_is_valid": ToolSchema(
        name="rhino_is_valid",
        description="Check if geometry is valid",
        params=[
            ParamSchema("id", "string", "Object GUID", required=True, geometry_type="id"),
        ],
        needs_geometry=["any"],
    ),

    # =========================================================================
    # Knowledge Tools
    # =========================================================================
    "knowledge_query": ToolSchema(
        name="knowledge_query",
        description="Query the knowledge graph for patterns",
        params=[
            ParamSchema("intent", "string", "What you're trying to do"),
            ParamSchema("tool", "string", "Specific MCP tool name"),
        ],
    ),
    "rhino_knowledge_query": ToolSchema(
        name="rhino_knowledge_query",
        description="Alias for rhino_command_knowledge",
        params=[
            ParamSchema("command", "string", "Specific Rhino command to query"),
        ],
    ),
    "knowledge_record": ToolSchema(
        name="knowledge_record",
        description="Record a learning outcome",
        params=[
            ParamSchema("intent", "string", "What you wanted to accomplish", required=True),
            ParamSchema("action", "object", "The action taken: {tool, params}", required=True),
            ParamSchema("outcome", "string", "success or failure", required=True, enum=["success", "failure"]),
            ParamSchema("correction_of", "object", "If correcting a failure: {params, error}"),
        ],
    ),
}


def get_tool_schema(tool_name: str) -> ToolSchema | None:
    """Get schema for a tool by name."""
    return TOOL_SCHEMAS.get(tool_name)


def get_all_tool_names() -> list[str]:
    """Get list of all known tool names."""
    return list(TOOL_SCHEMAS.keys())


def parse_missing_param_from_error(error: str) -> str | None:
    """
    Parse error message to extract the missing parameter name.

    Examples:
    - "Missing 'code' field" -> "code"
    - "Required parameter 'id' not provided" -> "id"
    - "'curveId' is required" -> "curveId"
    """
    import re

    # Pattern 1: "Missing 'X' field" or "Missing required parameter 'X'"
    match = re.search(r"[Mm]issing\s+(?:required\s+)?(?:parameter\s+)?['\"](\w+)['\"]", error)
    if match:
        return match.group(1)

    # Pattern 2: "'X' is required" or "'X' field is required"
    match = re.search(r"['\"](\w+)['\"](?:\s+field)?\s+is\s+required", error)
    if match:
        return match.group(1)

    # Pattern 3: "Required parameter 'X' not provided"
    match = re.search(r"[Rr]equired\s+parameter\s+['\"](\w+)['\"]", error)
    if match:
        return match.group(1)

    # Pattern 4: "parameter 'X' is missing"
    match = re.search(r"parameter\s+['\"](\w+)['\"]\s+is\s+missing", error)
    if match:
        return match.group(1)

    # Pattern 5: "Missing field: X" or "Missing: X"
    match = re.search(r"[Mm]issing(?:\s+field)?:\s*['\"]?(\w+)['\"]?", error)
    if match:
        return match.group(1)

    # Pattern 6: "X is required"
    match = re.search(r"\b(\w+)\s+is\s+required\b", error)
    if match:
        param = match.group(1)
        # Filter out common non-param words
        if param.lower() not in ["this", "that", "it", "parameter", "field", "value", "input"]:
            return param

    return None


def parse_invalid_param_from_error(error: str) -> tuple[str | None, str | None]:
    """
    Parse error message to extract invalid parameter name and expected type.

    Returns:
        Tuple of (param_name, expected_type) or (None, None) if not found
    """
    import re

    # Pattern 1: "'X' must be a Y" or "'X' should be a Y"
    match = re.search(r"['\"](\w+)['\"](?:\s+must|\s+should)\s+be\s+(?:a\s+)?(\w+)", error)
    if match:
        return match.group(1), match.group(2)

    # Pattern 2: "Invalid type for 'X': expected Y"
    match = re.search(r"[Ii]nvalid\s+type\s+for\s+['\"](\w+)['\"].*expected\s+(\w+)", error)
    if match:
        return match.group(1), match.group(2)

    # Pattern 3: "X: expected Y, got Z"
    match = re.search(r"(\w+):\s+expected\s+(\w+)", error)
    if match:
        return match.group(1), match.group(2)

    return None, None


def generate_default_value(param: ParamSchema, context=None) -> Any:
    """
    Generate a default value for a parameter based on its type and context.

    Args:
        param: The parameter schema
        context: Optional ExplorationContext for getting object IDs
    """
    # If param has a geometry type, try to get from context
    if param.geometry_type and context:
        if param.geometry_type == "id":
            obj_id = context.get_any_id()
            if obj_id:
                return obj_id
            else:
                logger.warning(f"No objects in context for param '{param.name}' (needs any ID). Will use placeholder.")
        elif param.geometry_type == "ids":
            obj_ids = context.get_any_ids(limit=2)
            if obj_ids:
                return obj_ids
            else:
                logger.warning(f"No objects in context for param '{param.name}' (needs IDs). Will use placeholder.")
        elif param.geometry_type == "curveId":
            curve_id = context.get_curve_id()
            if curve_id:
                return curve_id
            else:
                logger.warning(f"No curves in context for param '{param.name}'. Will use placeholder.")
        elif param.geometry_type == "curveIds":
            curve_ids = context.get_curve_ids(limit=2)
            if curve_ids:
                return curve_ids
            else:
                logger.warning(f"No curves in context for param '{param.name}' (needs multiple). Will use placeholder.")
        elif param.geometry_type == "brepId":
            brep_id = context.get_brep_id()
            if brep_id:
                return brep_id
            else:
                logger.warning(f"No breps in context for param '{param.name}'. Will use placeholder.")
        elif param.geometry_type == "meshId":
            mesh_id = context.get_mesh_id()
            if mesh_id:
                return mesh_id
            else:
                logger.warning(f"No meshes in context for param '{param.name}'. Will use placeholder.")
        elif param.geometry_type == "meshIds":
            mesh_ids = context.get_mesh_ids(limit=2)
            if mesh_ids:
                return mesh_ids
            else:
                logger.warning(f"No meshes in context for param '{param.name}' (needs multiple). Will use placeholder.")
        elif param.geometry_type == "subdId":
            subd_id = context.get_subd_id()
            if subd_id:
                return subd_id
            else:
                logger.warning(f"No SubDs in context for param '{param.name}'. Will use placeholder.")
    elif param.geometry_type and not context:
        logger.warning(f"Param '{param.name}' needs geometry type '{param.geometry_type}' but no context provided!")

    # If there's a default value, use it
    if param.default is not None:
        return param.default

    # If there are enum values, use the first one
    if param.enum:
        return param.enum[0]

    # Generate based on type
    if param.param_type == "string":
        # Special cases based on param name
        if param.name == "code":
            return "import rhinoscriptsyntax as rs\nprint('Hello from Rook')"
        elif param.name == "command":
            return "_Line 0,0,0 10,0,0"
        elif param.name == "name":
            return "TestObject"
        elif param.name == "text":
            return "Test Text"
        elif "pattern" in param.name.lower():
            return "*"
        return "test_value"

    elif param.param_type == "number":
        # Special cases based on param name
        if "radius" in param.name.lower():
            return 5.0
        elif "distance" in param.name.lower():
            return 10.0
        elif "height" in param.name.lower():
            return 10.0
        elif "width" in param.name.lower():
            return 10.0
        elif "depth" in param.name.lower():
            return 10.0
        elif "factor" in param.name.lower():
            return 2.0
        elif "angle" in param.name.lower():
            return 45.0
        elif "parameter" in param.name.lower():
            return 0.5
        elif param.name in ("u", "v"):
            return 0.5
        return 1.0

    elif param.param_type == "integer":
        if "count" in param.name.lower():
            return 10
        elif "level" in param.name.lower():
            return 1
        elif "index" in param.name.lower():
            return 0
        return 1

    elif param.param_type == "boolean":
        return True

    elif param.param_type == "array":
        # Special cases based on param name
        if "origin" in param.name.lower() or "center" in param.name.lower():
            return [0, 0, 0]
        elif "point" in param.name.lower():
            return [5, 5, 5]
        elif "start" in param.name.lower():
            return [0, 0, 0]
        elif "end" in param.name.lower():
            return [10, 0, 0]
        elif "vector" in param.name.lower():
            return [10, 0, 0]
        elif "direction" in param.name.lower():
            return [0, 0, 1]
        elif "normal" in param.name.lower():
            return [0, 0, 1]
        elif "axis" in param.name.lower():
            return [0, 0, 1]
        elif "color" in param.name.lower():
            return [255, 0, 0]
        elif param.items_type == "integer":
            return [0, 1, 2]
        elif param.items_type == "string":
            return []
        return [0, 0, 0]

    elif param.param_type == "object":
        return {}

    return None


def generate_params_for_tool(tool_name: str, context=None, include_optional: bool = False) -> dict:
    """
    Generate valid parameters for a tool based on its schema.

    Args:
        tool_name: The tool to generate parameters for
        context: Optional ExplorationContext for getting object IDs
        include_optional: Whether to include optional parameters with defaults

    Returns:
        Dictionary of parameters
    """
    schema = get_tool_schema(tool_name)
    if not schema:
        return {}

    params = {}

    # Add required parameters
    for param in schema.get_required_params():
        value = generate_default_value(param, context)
        if value is not None:
            params[param.name] = value

    # Optionally add optional parameters with good defaults
    if include_optional:
        for param in schema.get_optional_params():
            # Only add if there's a sensible default
            if param.default is not None or param.geometry_type:
                value = generate_default_value(param, context)
                if value is not None:
                    params[param.name] = value

    # Special handling for rhino_create - need type-specific params
    if tool_name == "rhino_create" and "type" in params:
        geom_type = params["type"]
        if geom_type == "POINT":
            params["point"] = [0, 0, 0]
        elif geom_type == "LINE":
            params["start"] = [0, 0, 0]
            params["end"] = [10, 0, 0]
        elif geom_type == "POLYLINE":
            params["points"] = [[0, 0, 0], [5, 5, 0], [10, 0, 0]]
        elif geom_type == "CIRCLE":
            params["center"] = [0, 0, 0]
            params["radius"] = 5
        elif geom_type == "ARC":
            params["center"] = [0, 0, 0]
            params["radius"] = 5
            params["startAngle"] = 0
            params["endAngle"] = 90
        elif geom_type == "RECTANGLE":
            params["origin"] = [0, 0, 0]
            params["width"] = 10
            params["height"] = 5
        elif geom_type == "BOX":
            params["origin"] = [0, 0, 0]
            params["width"] = 10
            params["depth"] = 10
            params["height"] = 10
        elif geom_type == "SPHERE":
            params["center"] = [0, 0, 0]
            params["radius"] = 5
        elif geom_type == "CYLINDER":
            params["center"] = [0, 0, 0]
            params["radius"] = 5
            params["height"] = 10
        elif geom_type == "CONE":
            params["center"] = [0, 0, 0]
            params["radius"] = 5
            params["height"] = 10

    return params


def get_geometry_requirements(tool_name: str) -> list[str]:
    """
    Get the geometry types needed for a tool.

    Returns:
        List of geometry types needed: ["brep", "curve", "mesh", "subd", "any"]
    """
    schema = get_tool_schema(tool_name)
    if not schema:
        return []
    return schema.needs_geometry


def get_geometry_count(tool_name: str) -> int:
    """
    Get how many objects are needed for a tool.

    Returns:
        Number of objects needed (default 1)
    """
    schema = get_tool_schema(tool_name)
    if not schema:
        return 1
    return schema.geometry_count
