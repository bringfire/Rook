"""
Parameter Generator - Generates test parameters from tool schemas.

Enhanced with context-awareness: uses real object IDs from the exploration context
instead of empty placeholders.
"""

import random
from typing import Any
from .registry import ToolDefinition
from .context import ExplorationContext


class ParamGenerator:
    """
    Generates parameters for testing tools based on their schemas.

    When a context is provided, uses real object IDs from previously
    created geometry instead of empty placeholders.
    """

    # Default values for different JSON schema types
    TYPE_DEFAULTS = {
        "string": "test_string",
        "number": 5.0,
        "integer": 5,
        "boolean": True,
        "array": [],
        "object": {},
    }

    # Common parameter patterns and their generators
    PARAM_PATTERNS = {
        # Point/vector arrays
        "point": [0.0, 0.0, 0.0],
        "center": [0.0, 0.0, 0.0],
        "start": [0.0, 0.0, 0.0],
        "end": [10.0, 10.0, 0.0],
        "origin": [0.0, 0.0, 0.0],
        "vector": [1.0, 0.0, 0.0],
        "axis": [0.0, 0.0, 1.0],
        "direction": [0.0, 0.0, 1.0],
        "planeOrigin": [0.0, 0.0, 0.0],
        "planeNormal": [0.0, 0.0, 1.0],
        "from": [0.0, 0.0, 0.0],
        "to": [10.0, 10.0, 0.0],

        # Dimensions
        "radius": 5.0,
        "width": 10.0,
        "height": 10.0,
        "depth": 10.0,
        "distance": 5.0,
        "length": 10.0,
        "factor": 2.0,
        "angle": 45.0,
        "startAngle": 0.0,
        "endAngle": 90.0,
        "tolerance": 0.001,
        "u": 0.5,
        "v": 0.5,
        "parameter": 0.5,

        # Counts
        "count": 10,
        "limit": 100,
        "offset": 0,
        "targetCount": 1000,
        "targetQuadCount": 1000,
        "iterations": 1,
        "level": 1,
        "divisions": 3,
        "degree": 3,
        "pointCount": 10,
        "faceIndex": 0,
        "density": 0.5,
        "circumferenceFaces": 8,
        "heightFaces": 1,
        "xFaces": 2,
        "yFaces": 2,
        "zFaces": 2,
        "xCount": 2,
        "yCount": 2,
        "zCount": 2,
        "rings": 10,
        "segments": 10,
        "around": 20,
        "vertical": 10,
        "accuracy": 5,

        # Strings
        "name": "ExplorerTest",
        "newName": "ExplorerTestRenamed",
        "layer": "Default",
        "type": "SPHERE",
        "operation": "move",
        "action": "list",
        "command": "_Line 0,0,0 10,10,0",
        "code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)",
        "view": "Perspective",
        "font": "Arial",
        "text": "Explorer Test",
        "namePattern": "*",
        "method": "Pack",
        "cornerStyle": "Sharp",
        "updateType": "linked",
        "mode": "uniform",
        "keepSide": "positive",
        "units": "Millimeters",
        "path": "C:/temp/explorer_test.3dm",
        "description": "Created by Knowledge Explorer",
        "url": "",
        "urlDescription": "",

        # Booleans
        "clear": True,
        "echo": False,
        "closed": False,
        "cap": True,
        "solid": True,
        "deleteInputs": False,  # Don't delete during exploration!
        "replaceWithInstance": False,
        "deleteOriginals": False,  # Don't delete during exploration!
        "visible": True,
        "locked": False,
        "bold": False,
        "italic": False,
        "adaptive": True,
        "fillHoles": True,
        "rebuildNormals": True,
        "interpolateVertices": False,
        "packFaces": False,
        "extend": True,
        "shrink": False,
        "unused": True,
        "deleted": True,
        "multiline": False,
        "selection": False,
        "crease": True,
        "jagged": False,
        "simple": False,

        # Special
        "color": [255, 128, 0],  # Orange
        "points": [[0, 0, 0], [10, 0, 0], [10, 10, 0]],
        "basePoint": [0.0, 0.0, 0.0],
        "insertionPoint": [0.0, 0.0, 0.0],
        "dimLocation": [5.0, 5.0, 0.0],
        "anglePoint": [5.0, 0.0, 0.0],
        "edgeIndices": [0],
        "indices": [0],
        "scale": 1.0,
        "rotation": 0.0,
    }

    # Geometry type specific parameters for rhino_create
    GEOMETRY_PARAMS = {
        "POINT": {"point": [5.0, 5.0, 0.0]},
        "LINE": {"start": [0.0, 0.0, 0.0], "end": [10.0, 0.0, 0.0]},
        "POLYLINE": {"points": [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]]},
        "CIRCLE": {"center": [0.0, 0.0, 0.0], "radius": 5.0},
        "ARC": {"center": [0.0, 0.0, 0.0], "radius": 5.0, "startAngle": 0.0, "endAngle": 90.0},
        "RECTANGLE": {"origin": [0.0, 0.0, 0.0], "width": 10.0, "height": 10.0},
        "BOX": {"origin": [0.0, 0.0, 0.0], "width": 10.0, "depth": 10.0, "height": 10.0},
        "SPHERE": {"center": [0.0, 0.0, 0.0], "radius": 5.0},
        "CYLINDER": {"center": [0.0, 0.0, 0.0], "radius": 5.0, "height": 10.0},
        "CONE": {"center": [0.0, 0.0, 0.0], "radius": 5.0, "height": 10.0},
    }

    def __init__(self, context: ExplorationContext | None = None):
        """Initialize with optional exploration context."""
        self.context = context

    def set_context(self, context: ExplorationContext) -> None:
        """Set or update the exploration context."""
        self.context = context

    def generate_valid(self, tool: ToolDefinition) -> dict[str, Any]:
        """Generate valid parameters for a tool based on its schema."""
        params = {}
        schema = tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Handle special cases first
        if tool.name == "rhino_create":
            return self._generate_create_params()
        if tool.name == "rhino_transform":
            return self._generate_transform_params()
        if tool.name == "rhino_boolean":
            return self._generate_boolean_params()
        if tool.name == "rhino_curve_ops":
            return self._generate_curve_ops_params()
        if tool.name == "rhino_document_ops":
            return self._generate_document_ops_params()
        if tool.name == "rhino_material_ops":
            return self._generate_material_ops_params()
        if tool.name == "rhino_dimension":
            return self._generate_dimension_params()

        # Generate required parameters
        for param_name in required:
            if param_name in properties:
                params[param_name] = self._generate_param_value(
                    param_name, properties[param_name], tool.name
                )

        return params

    def generate_variations(
        self, tool: ToolDefinition, count: int = 5, strategy: str = "mixed"
    ) -> list[dict[str, Any]]:
        """Generate multiple parameter variations for deeper exploration."""
        variations = []

        if strategy == "boundary":
            variations.extend(self._generate_boundary_variations(tool))
        elif strategy == "mutation":
            base = self.generate_valid(tool)
            variations.extend(self._generate_mutations(tool, base, count))
        else:  # mixed
            variations.append(self.generate_valid(tool))
            variations.extend(self._generate_boundary_variations(tool)[:count - 1])

        return variations[:count]

    def _generate_param_value(self, param_name: str, schema: dict, tool_name: str = "") -> Any:
        """Generate a value for a single parameter, using context when available."""

        # First, check if this parameter needs a real ID from context
        value = self._get_contextual_value(param_name, tool_name)
        if value is not None:
            return value

        # Check if we have a known pattern for this parameter name
        if param_name in self.PARAM_PATTERNS:
            return self.PARAM_PATTERNS[param_name]

        # Fall back to type-based generation
        param_type = schema.get("type", "string")

        if param_type == "array":
            items = schema.get("items", {})
            if items.get("type") == "string":
                return ["test_item_1", "test_item_2"]
            elif items.get("type") == "integer":
                return [0, 1, 2]
            else:
                return [0.0, 0.0, 0.0]  # Default to point-like array

        return self.TYPE_DEFAULTS.get(param_type, None)

    def _get_contextual_value(self, param_name: str, tool_name: str) -> Any | None:
        """Get a value from context if available."""
        if not self.context:
            return None

        # Single object ID parameters
        if param_name == "id":
            # Try to get appropriate type based on tool
            if "curve" in tool_name or "curvature_curve" in tool_name:
                return self.context.get_curve_id()
            elif "mesh" in tool_name:
                return self.context.get_mesh_id()
            elif "subd" in tool_name:
                return self.context.get_subd_id()
            elif "brep" in tool_name or "surface" in tool_name:
                return self.context.get_brep_id()
            elif "block" in tool_name:
                return self.context.get_block_instance_id()
            else:
                return self.context.get_any_id()

        # Specific ID types
        if param_name == "curveId":
            return self.context.get_curve_id()
        if param_name == "surfaceId":
            return self.context.get_surface_id() or self.context.get_brep_id()
        if param_name == "brepId":
            return self.context.get_brep_id()
        if param_name == "meshId":
            return self.context.get_mesh_id()
        if param_name == "subdId":
            return self.context.get_subd_id()
        if param_name == "instanceId":
            return self.context.get_block_instance_id()
        if param_name == "targetId":
            breps = self.context.get_brep_ids(2)
            return breps[0] if breps else None
        if param_name == "fromId":
            return self.context.get_any_id()
        if param_name == "toId":
            ids = self.context.get_any_ids(2)
            return ids[1] if len(ids) > 1 else None

        # Array of IDs
        if param_name == "ids":
            return self.context.get_any_ids(2) or []
        if param_name == "curveIds":
            return self.context.get_curve_ids(2) or []
        if param_name == "meshIds":
            return self.context.get_mesh_ids(2) or []
        if param_name == "brepIds":
            return self.context.get_brep_ids(2) or []
        if param_name == "toolIds":
            breps = self.context.get_brep_ids(3)
            return breps[1:] if len(breps) > 1 else []
        if param_name == "profileIds":
            return self.context.get_curve_ids(2) or []

        # Rail for sweep
        if param_name == "railId":
            return self.context.get_curve_id()

        # Named resources
        if param_name == "layer" and self.context.get_layer():
            return self.context.get_layer()

        # Block names - only provide if we have blocks
        if param_name == "name" and "block" in tool_name:
            block = self.context.get_block()
            if block:
                return block

        return None

    def _generate_create_params(self, geom_type: str | None = None) -> dict[str, Any]:
        """Generate parameters for rhino_create tool."""
        if geom_type is None:
            # Randomly select a geometry type
            geom_type = random.choice(list(self.GEOMETRY_PARAMS.keys()))

        if geom_type not in self.GEOMETRY_PARAMS:
            geom_type = "SPHERE"

        # Add some randomness to position to avoid overlapping geometry
        offset_x = random.uniform(-20, 20)
        offset_y = random.uniform(-20, 20)

        params = {"type": geom_type}
        base_params = self.GEOMETRY_PARAMS[geom_type].copy()

        # Apply offset to center/origin/start positions
        for key in ["center", "origin", "start", "point"]:
            if key in base_params:
                pos = base_params[key].copy()
                pos[0] += offset_x
                pos[1] += offset_y
                base_params[key] = pos

        # Offset end point for lines
        if "end" in base_params:
            pos = base_params["end"].copy()
            pos[0] += offset_x
            pos[1] += offset_y
            base_params["end"] = pos

        # Offset polyline points
        if "points" in base_params:
            base_params["points"] = [
                [p[0] + offset_x, p[1] + offset_y, p[2]]
                for p in base_params["points"]
            ]

        params.update(base_params)
        params["name"] = f"Explorer_{geom_type}_{random.randint(1000, 9999)}"
        return params

    def _generate_transform_params(self, operation: str = "move") -> dict[str, Any]:
        """Generate parameters for rhino_transform tool."""
        # Get real IDs from context
        ids = []
        if self.context:
            ids = self.context.get_any_ids(2)

        base = {"ids": ids, "operation": operation}

        if operation == "move":
            base["vector"] = [random.uniform(5, 15), 0.0, 0.0]
        elif operation == "rotate":
            base["angle"] = random.uniform(15, 90)
            base["axis"] = [0.0, 0.0, 1.0]
            base["center"] = [0.0, 0.0, 0.0]
        elif operation == "scale":
            base["factor"] = random.uniform(1.5, 2.5)
            base["center"] = [0.0, 0.0, 0.0]
        elif operation == "mirror":
            base["planeOrigin"] = [0.0, 0.0, 0.0]
            base["planeNormal"] = [1.0, 0.0, 0.0]

        return base

    def _generate_boolean_params(self, operation: str = "union") -> dict[str, Any]:
        """Generate parameters for rhino_boolean tool."""
        base = {"operation": operation, "deleteInputs": False}

        if self.context:
            breps = self.context.get_brep_ids(3)
            if operation == "difference" and len(breps) >= 2:
                base["targetId"] = breps[0]
                base["toolIds"] = breps[1:]
            elif len(breps) >= 2:
                base["ids"] = breps
        else:
            if operation == "difference":
                base["targetId"] = ""
                base["toolIds"] = []
            else:
                base["ids"] = []

        return base

    def _generate_curve_ops_params(self, action: str = "divide") -> dict[str, Any]:
        """Generate parameters for rhino_curve_ops tool."""
        base = {"action": action}

        curve_id = self.context.get_curve_id() if self.context else None
        curve_ids = self.context.get_curve_ids(2) if self.context else []

        if action == "join":
            base["ids"] = curve_ids
        elif action == "divide":
            base["id"] = curve_id or ""
            base["count"] = 10
        elif action == "extend":
            base["id"] = curve_id or ""
            base["end"] = 0
            base["length"] = 5.0
        elif action == "fillet":
            base["id1"] = curve_ids[0] if len(curve_ids) > 0 else ""
            base["id2"] = curve_ids[1] if len(curve_ids) > 1 else ""
            base["radius"] = 2.0
        elif action == "rebuild":
            base["id"] = curve_id or ""
            base["degree"] = 3
            base["pointCount"] = 20
        else:
            base["id"] = curve_id or ""

        return base

    def _generate_document_ops_params(self, action: str = "undo") -> dict[str, Any]:
        """Generate parameters for rhino_document_ops tool."""
        base = {"action": action}

        if action == "save":
            base["path"] = f"C:/temp/explorer_test_{random.randint(1000, 9999)}.3dm"
        elif action == "set_units":
            base["units"] = "Millimeters"

        return base

    def _generate_material_ops_params(self, action: str = "list") -> dict[str, Any]:
        """Generate parameters for rhino_material_ops tool."""
        base = {"action": action}

        if action == "create":
            base["name"] = f"ExplorerMaterial_{random.randint(1000, 9999)}"
            base["color"] = [random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)]
        elif action == "delete":
            material = self.context.get_material() if self.context else None
            base["name"] = material or "ExplorerMaterial"
        elif action == "assign":
            material = self.context.get_material() if self.context else None
            base["name"] = material or "ExplorerMaterial"
            base["ids"] = self.context.get_any_ids(2) if self.context else []

        return base

    def _generate_dimension_params(self, dim_type: str = "DIMENSION_LINEAR") -> dict[str, Any]:
        """Generate parameters for rhino_dimension tool."""
        base = {"type": dim_type}

        if dim_type == "DIMENSION_LINEAR":
            base["start"] = [0.0, 0.0, 0.0]
            base["end"] = [10.0, 0.0, 0.0]
            base["offset"] = 2.0
        elif dim_type == "DIMENSION_RADIUS":
            curve_id = self.context.get_curve_id() if self.context else None
            base["curveId"] = curve_id or ""
            base["anglePoint"] = [5.0, 0.0, 0.0]
        elif dim_type == "DIMENSION_ANGLE":
            base["center"] = [0.0, 0.0, 0.0]
            base["start"] = [10.0, 0.0, 0.0]
            base["end"] = [0.0, 10.0, 0.0]
            base["dimLocation"] = [7.0, 7.0, 0.0]

        return base

    def _generate_boundary_variations(self, tool: ToolDefinition) -> list[dict[str, Any]]:
        """Generate edge case parameter variations."""
        variations = []
        base = self.generate_valid(tool)
        properties = tool.input_schema.get("properties", {})

        for param_name, schema in properties.items():
            param_type = schema.get("type", "string")

            # Skip ID parameters - we don't want to test with invalid IDs
            if param_name in ("id", "ids", "curveId", "surfaceId", "brepId", "meshId"):
                continue

            # Generate boundary values based on type
            if param_type == "number":
                # Zero
                v = base.copy()
                v[param_name] = 0.0
                variations.append(v)

                # Negative
                v = base.copy()
                v[param_name] = -5.0
                variations.append(v)

                # Very large
                v = base.copy()
                v[param_name] = 10000.0
                variations.append(v)

            elif param_type == "integer":
                # Zero
                v = base.copy()
                v[param_name] = 0
                variations.append(v)

                # Negative
                v = base.copy()
                v[param_name] = -1
                variations.append(v)

            elif param_type == "string":
                # Empty string (but not for IDs)
                if not param_name.endswith("Id") and param_name != "ids":
                    v = base.copy()
                    v[param_name] = ""
                    variations.append(v)

            elif param_type == "array":
                # Empty array (but not for IDs)
                if param_name not in ("ids", "curveIds", "meshIds", "brepIds"):
                    v = base.copy()
                    v[param_name] = []
                    variations.append(v)

        return variations

    def _generate_mutations(
        self, tool: ToolDefinition, base: dict[str, Any], count: int
    ) -> list[dict[str, Any]]:
        """Generate mutations of a base parameter set."""
        mutations = []
        properties = tool.input_schema.get("properties", {})

        # Filter out ID parameters
        param_names = [
            p for p in properties.keys()
            if not p.endswith("Id") and p not in ("ids", "curveIds", "meshIds", "brepIds")
        ]

        for _ in range(count):
            if not param_names:
                break

            mutated = base.copy()
            param_to_mutate = random.choice(param_names)
            schema = properties[param_to_mutate]
            param_type = schema.get("type", "string")

            # Apply random mutation
            if param_type == "number":
                mutated[param_to_mutate] = random.uniform(-10, 100)
            elif param_type == "integer":
                mutated[param_to_mutate] = random.randint(-5, 100)
            elif param_type == "boolean":
                mutated[param_to_mutate] = not base.get(param_to_mutate, False)

            mutations.append(mutated)

        return mutations

    def generate_all_geometry_types(self) -> list[dict[str, Any]]:
        """Generate test params for all geometry types in rhino_create."""
        return [
            self._generate_create_params(geom_type)
            for geom_type in self.GEOMETRY_PARAMS.keys()
        ]

    def generate_setup_sequence(self) -> list[tuple[str, dict[str, Any]]]:
        """
        Generate a sequence of creation operations to set up test geometry.

        Returns list of (tool_name, params) tuples.
        """
        sequence = []

        # Create various geometry types for testing
        # Breps (for boolean, transform, measure operations)
        sequence.append(("rhino_create", self._generate_create_params("BOX")))
        sequence.append(("rhino_create", self._generate_create_params("SPHERE")))
        sequence.append(("rhino_create", self._generate_create_params("CYLINDER")))

        # Curves (for curve operations, extrude, sweep)
        sequence.append(("rhino_create", self._generate_create_params("LINE")))
        sequence.append(("rhino_create", self._generate_create_params("CIRCLE")))
        sequence.append(("rhino_create", self._generate_create_params("POLYLINE")))

        # Meshes (for mesh operations)
        sequence.append(("rhino_mesh_box", {
            "width": 10, "depth": 10, "height": 10,
            "origin": [30, 0, 0]
        }))
        sequence.append(("rhino_mesh_sphere", {
            "radius": 5, "center": [30, 15, 0]
        }))

        # SubDs (for SubD operations)
        sequence.append(("rhino_subd_box", {
            "width": 10, "depth": 10, "height": 10,
            "origin": [45, 0, 0]
        }))
        sequence.append(("rhino_subd_sphere", {
            "radius": 5, "center": [45, 15, 0]
        }))

        # Layer (for layer operations)
        sequence.append(("rhino_layer_create", {
            "name": f"ExplorerTestLayer_{random.randint(1000, 9999)}"
        }))

        return sequence
