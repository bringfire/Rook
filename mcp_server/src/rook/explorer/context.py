"""
Exploration Context - Maintains state during exploration sessions.

Tracks created objects, their types, and IDs so that modification tools
can use real object references instead of empty placeholders.
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from enum import Enum

logger = logging.getLogger("explorer.context")


class GeometryType(Enum):
    """Types of geometry that can be created and tracked."""
    POINT = "Point"
    CURVE = "Curve"
    SURFACE = "Surface"
    BREP = "Brep"
    MESH = "Mesh"
    SUBD = "SubD"
    BLOCK = "BlockInstance"
    TEXT = "TextDot"
    DIMENSION = "Dimension"
    LAYER = "Layer"
    MATERIAL = "Material"
    GROUP = "Group"


@dataclass
class TrackedObject:
    """An object created during exploration."""
    id: str
    geometry_type: GeometryType
    tool_used: str
    params_used: dict
    name: str | None = None
    layer: str | None = None


@dataclass
class ExplorationContext:
    """
    Maintains state during an exploration session.

    Tracks all objects created so they can be referenced by
    subsequent operations (transform, measure, delete, etc.)
    """

    # All objects created during this session
    objects: list[TrackedObject] = field(default_factory=list)

    # Objects organized by type for quick lookup
    by_type: dict[GeometryType, list[TrackedObject]] = field(default_factory=dict)

    # Layers created
    layers: list[str] = field(default_factory=list)

    # Materials created
    materials: list[str] = field(default_factory=list)

    # Blocks created
    blocks: list[str] = field(default_factory=list)

    # Groups created
    groups: list[str] = field(default_factory=list)

    def add_object(
        self,
        obj_id: str,
        geometry_type: GeometryType,
        tool_used: str,
        params_used: dict,
        name: str | None = None,
        layer: str | None = None,
    ) -> TrackedObject:
        """Track a newly created object."""
        obj = TrackedObject(
            id=obj_id,
            geometry_type=geometry_type,
            tool_used=tool_used,
            params_used=params_used,
            name=name,
            layer=layer,
        )
        self.objects.append(obj)

        # Index by type
        if geometry_type not in self.by_type:
            self.by_type[geometry_type] = []
        self.by_type[geometry_type].append(obj)

        logger.debug(f"Tracked {geometry_type.value}: {obj_id}")
        return obj

    def add_layer(self, name: str) -> None:
        """Track a created layer."""
        if name not in self.layers:
            self.layers.append(name)
            logger.debug(f"Tracked layer: {name}")

    def add_material(self, name: str) -> None:
        """Track a created material."""
        if name not in self.materials:
            self.materials.append(name)
            logger.debug(f"Tracked material: {name}")

    def add_block(self, name: str) -> None:
        """Track a created block definition."""
        if name not in self.blocks:
            self.blocks.append(name)
            logger.debug(f"Tracked block: {name}")

    def add_group(self, name: str) -> None:
        """Track a created group."""
        if name not in self.groups:
            self.groups.append(name)
            logger.debug(f"Tracked group: {name}")

    def remove_object(self, obj_id: str) -> bool:
        """Remove an object (e.g., after deletion)."""
        for i, obj in enumerate(self.objects):
            if obj.id == obj_id:
                removed = self.objects.pop(i)
                # Also remove from type index
                if removed.geometry_type in self.by_type:
                    self.by_type[removed.geometry_type] = [
                        o for o in self.by_type[removed.geometry_type]
                        if o.id != obj_id
                    ]
                logger.debug(f"Removed object: {obj_id}")
                return True
        return False

    # ========== Getters for parameter generation ==========

    def get_any_id(self) -> str | None:
        """Get any available object ID."""
        if self.objects:
            return self.objects[0].id
        return None

    def get_any_ids(self, limit: int = 2, count: int = None) -> list[str]:
        """Get multiple object IDs.

        Args:
            limit: Maximum number of IDs to return
            count: Alias for limit (deprecated, use limit)
        """
        n = count if count is not None else limit
        return [obj.id for obj in self.objects[:n]]

    def get_brep_id(self) -> str | None:
        """Get a Brep (solid) object ID."""
        breps = self.by_type.get(GeometryType.BREP, [])
        return breps[0].id if breps else None

    def get_brep_ids(self, limit: int = 2, count: int = None) -> list[str]:
        """Get multiple Brep IDs for boolean operations."""
        n = count if count is not None else limit
        breps = self.by_type.get(GeometryType.BREP, [])
        return [b.id for b in breps[:n]]

    def get_curve_id(self) -> str | None:
        """Get a curve object ID."""
        curves = self.by_type.get(GeometryType.CURVE, [])
        return curves[0].id if curves else None

    def get_curve_ids(self, limit: int = 2, count: int = None) -> list[str]:
        """Get multiple curve IDs."""
        n = count if count is not None else limit
        curves = self.by_type.get(GeometryType.CURVE, [])
        return [c.id for c in curves[:n]]

    def get_mesh_id(self) -> str | None:
        """Get a mesh object ID."""
        meshes = self.by_type.get(GeometryType.MESH, [])
        return meshes[0].id if meshes else None

    def get_mesh_ids(self, limit: int = 2, count: int = None) -> list[str]:
        """Get multiple mesh IDs."""
        n = count if count is not None else limit
        meshes = self.by_type.get(GeometryType.MESH, [])
        return [m.id for m in meshes[:n]]

    def get_subd_id(self) -> str | None:
        """Get a SubD object ID."""
        subds = self.by_type.get(GeometryType.SUBD, [])
        return subds[0].id if subds else None

    def get_subd_ids(self, limit: int = 2) -> list[str]:
        """Get multiple SubD IDs."""
        subds = self.by_type.get(GeometryType.SUBD, [])
        return [s.id for s in subds[:limit]]

    def get_surface_id(self) -> str | None:
        """Get a surface object ID."""
        surfaces = self.by_type.get(GeometryType.SURFACE, [])
        return surfaces[0].id if surfaces else None

    def get_point_id(self) -> str | None:
        """Get a point object ID."""
        points = self.by_type.get(GeometryType.POINT, [])
        return points[0].id if points else None

    def get_layer(self) -> str | None:
        """Get a created layer name."""
        return self.layers[0] if self.layers else None

    def get_material(self) -> str | None:
        """Get a created material name."""
        return self.materials[0] if self.materials else None

    def get_block(self) -> str | None:
        """Get a created block definition name."""
        return self.blocks[0] if self.blocks else None

    def get_block_instance_id(self) -> str | None:
        """Get a block instance ID."""
        instances = self.by_type.get(GeometryType.BLOCK, [])
        return instances[0].id if instances else None

    # ========== Statistics ==========

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about tracked objects."""
        type_counts = {
            t.value: len(objs)
            for t, objs in self.by_type.items()
        }
        return {
            "total_objects": len(self.objects),
            "by_type": type_counts,
            "layers": len(self.layers),
            "materials": len(self.materials),
            "blocks": len(self.blocks),
            "groups": len(self.groups),
        }

    def clear(self) -> None:
        """Clear all tracked objects."""
        self.objects.clear()
        self.by_type.clear()
        self.layers.clear()
        self.materials.clear()
        self.blocks.clear()
        self.groups.clear()
        logger.info("Context cleared")

    def has_objects(self) -> bool:
        """Check if any objects are tracked."""
        return len(self.objects) > 0

    def has_breps(self) -> bool:
        """Check if any Breps are tracked."""
        return len(self.by_type.get(GeometryType.BREP, [])) > 0

    def has_curves(self) -> bool:
        """Check if any curves are tracked."""
        return len(self.by_type.get(GeometryType.CURVE, [])) > 0

    def has_meshes(self) -> bool:
        """Check if any meshes are tracked."""
        return len(self.by_type.get(GeometryType.MESH, [])) > 0

    def has_subds(self) -> bool:
        """Check if any SubDs are tracked."""
        return len(self.by_type.get(GeometryType.SUBD, [])) > 0


# Result parsing helpers

def parse_create_result(result: dict, tool_name: str, params: dict) -> tuple[str | None, GeometryType | None]:
    """Parse a creation result to extract ID and geometry type."""
    if not result.get("success"):
        return None, None

    data = result.get("data", {})

    # Handle different response formats
    # The response might be the data directly, or nested under "data"
    if isinstance(data, dict):
        obj_id = data.get("id") or data.get("guid") or data.get("ID")
    else:
        obj_id = None

    # If not found in data, try the result itself (some endpoints return id at top level)
    if not obj_id and isinstance(result, dict):
        obj_id = result.get("id") or result.get("guid") or result.get("ID")

    # Some tools return the ID directly as a string
    if not obj_id and isinstance(data, str) and len(data) == 36:  # GUID format
        obj_id = data

    # Determine geometry type from tool and params
    geom_type = _infer_geometry_type(tool_name, params, data if isinstance(data, dict) else {})

    return obj_id, geom_type


def _infer_geometry_type(tool_name: str, params: dict, data: dict) -> GeometryType:
    """Infer the geometry type from tool name and parameters."""

    # rhino_create uses 'type' parameter
    if tool_name == "rhino_create":
        create_type = params.get("type", "").upper()
        if create_type in ("POINT",):
            return GeometryType.POINT
        elif create_type in ("LINE", "POLYLINE", "CIRCLE", "ARC", "RECTANGLE"):
            return GeometryType.CURVE
        elif create_type in ("BOX", "SPHERE", "CYLINDER", "CONE"):
            return GeometryType.BREP

    # SubD tools
    if "subd" in tool_name:
        return GeometryType.SUBD

    # Mesh tools
    if "mesh" in tool_name:
        return GeometryType.MESH

    # Block tools
    if "block" in tool_name:
        return GeometryType.BLOCK

    # Surface tools (loft, sweep, extrude)
    if tool_name in ("rhino_loft", "rhino_sweep", "rhino_extrude"):
        return GeometryType.BREP

    # Default to Brep for unknown geometry
    return GeometryType.BREP
