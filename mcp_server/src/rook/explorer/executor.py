"""
HTTP Executor - Executes tool calls against Rhino via HTTP.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from ..bridge import native_client
from ..tool_lifecycle_runtime import DispatchOrigin, deny_if_contained

logger = logging.getLogger("explorer.executor")


@dataclass
class ExecutionResult:
    """Result of executing a tool."""
    tool_name: str
    params: dict[str, Any]
    success: bool
    response: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return f"ExecutionResult({status} {self.tool_name})"


class HttpExecutor:
    """
    Executes MCP tools against Rhino via the HTTP bridge.
    Uses discovery to find the native plugin's OS-assigned port.
    """

    TIMEOUT = 30.0

    def __init__(self, base_url: str | None = None):
        from ..bridge import get_rhino_host
        resolved = base_url or get_rhino_host()
        if resolved is None:
            raise RuntimeError(
                "No Rhino instance discovered. "
                "Ensure Rhino is running with RookNative loaded."
            )
        self.base_url = resolved.rstrip("/")

    async def ping(self) -> bool:
        """Check if Rhino is reachable."""
        try:
            async with native_client(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/ping")
                return response.status_code == 200
        except Exception:
            return False

    def ping_sync(self) -> bool:
        """Synchronous ping check."""
        return asyncio.run(self.ping())

    async def execute(self, tool_name: str, params: dict[str, Any]) -> ExecutionResult:
        """Execute a tool and return the result."""
        denial = deny_if_contained(tool_name, DispatchOrigin.INTERNAL_HANDLER)
        if denial is not None:
            return ExecutionResult(
                tool_name=tool_name,
                params={},
                success=False,
                response=denial,
                error="legacy_semantic_tool_contained",
            )
        import time
        start_time = time.time()

        try:
            # Route tool to appropriate endpoint
            endpoint, method = self._get_endpoint(tool_name)

            if endpoint is None:
                return ExecutionResult(
                    tool_name=tool_name,
                    params=params,
                    success=False,
                    error=f"Unknown tool: {tool_name}",
                )

            # Make the HTTP request
            async with native_client(timeout=self.TIMEOUT) as client:
                if method == "GET":
                    if params:
                        response = await client.request(
                            "GET",
                            f"{self.base_url}{endpoint}",
                            content=json.dumps(params),
                            headers={"Content-Type": "application/json"},
                        )
                    else:
                        response = await client.get(f"{self.base_url}{endpoint}")
                elif method == "DELETE":
                    response = await client.request(
                        "DELETE",
                        f"{self.base_url}{endpoint}",
                        content=json.dumps(params) if params else None,
                        headers={"Content-Type": "application/json"} if params else None,
                    )
                else:  # POST
                    response = await client.post(
                        f"{self.base_url}{endpoint}",
                        json=params,
                    )

            duration = (time.time() - start_time) * 1000

            # Parse response
            try:
                data = response.json()
            except json.JSONDecodeError:
                data = {"raw": response.text}

            # Determine success
            success = response.status_code == 200
            if isinstance(data, dict):
                success = success and data.get("success", True)

            return ExecutionResult(
                tool_name=tool_name,
                params=params,
                success=success,
                response=data,
                error=data.get("data") if not success and isinstance(data, dict) else None,
                duration_ms=duration,
            )

        except httpx.ConnectError:
            return ExecutionResult(
                tool_name=tool_name,
                params=params,
                success=False,
                error="Connection refused - is Rhino running with Rook plugin?",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except httpx.TimeoutException:
            return ExecutionResult(
                tool_name=tool_name,
                params=params,
                success=False,
                error="Request timed out",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return ExecutionResult(
                tool_name=tool_name,
                params=params,
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def execute_sync(self, tool_name: str, params: dict[str, Any]) -> ExecutionResult:
        """Synchronous execution wrapper."""
        return asyncio.run(self.execute(tool_name, params))

    def _get_endpoint(self, tool_name: str) -> tuple[str | None, str]:
        """Map tool name to HTTP endpoint and method."""
        # Remove 'rhino_' prefix if present
        name = tool_name.replace("rhino_", "")

        # Endpoint mappings
        MAPPINGS = {
            # Query tools (GET)
            "ping": ("/ping", "GET"),
            "document": ("/document", "GET"),
            "layers": ("/layers", "GET"),
            "objects": ("/objects", "GET"),
            "selection": ("/selection", "GET"),
            "geometry": ("/geometry", "GET"),
            "viewport": ("/viewport", "GET"),
            "blocks": ("/blocks", "GET"),

            # Create/modify tools (POST)
            "create": ("/create", "POST"),
            "transform": ("/transform", "POST"),
            "copy": ("/copy", "POST"),
            "select": ("/select", "POST"),
            "select_by_type": ("/select/type", "POST"),
            "select_by_name": ("/select/name", "POST"),
            "select_all": ("/select/all", "POST"),
            "select_none": ("/select/none", "POST"),
            "select_invert": ("/select/invert", "POST"),
            "deselect": ("/deselect", "POST"),
            "execute": ("/execute", "POST"),
            "command": ("/command", "POST"),
            "group": ("/group", "POST"),

            # Layer operations
            "layer_create": ("/layer/create", "POST"),
            "layer_delete": ("/layer/delete", "DELETE"),
            "layer_visibility": ("/layer/visibility", "POST"),
            "layer_lock": ("/layer/lock", "POST"),
            "layer_current": ("/layer/current", "POST"),

            # Boolean & geometry operations
            "boolean": ("/boolean", "POST"),
            "loft": ("/loft", "POST"),
            "sweep": ("/sweep", "POST"),
            "extrude": ("/extrude", "POST"),
            "import": ("/import", "POST"),
            "export": ("/export", "POST"),

            # Measurement
            "measure_distance": ("/measure/distance", "GET"),
            "measure_area": ("/measure/area", "GET"),
            "measure_volume": ("/measure/volume", "GET"),
            "measure_length": ("/measure/length", "GET"),
            "measure_bbox": ("/measure/bbox", "GET"),
            "measure_centroid": ("/measure/centroid", "GET"),

            # Curve operations
            "curve_ops": ("/curve/ops", "POST"),

            # Document operations
            "document_ops": ("/document/ops", "POST"),

            # Material operations
            "material_ops": ("/material/ops", "POST"),

            # Block operations
            "block_create": ("/block/create", "POST"),
            "block_insert": ("/block/insert", "POST"),
            "block_explode": ("/block/explode", "POST"),
            "block_delete": ("/block/delete", "DELETE"),
            "block_rename": ("/block/rename", "POST"),
            "block_description": ("/block/description", "POST"),
            "block_info": ("/block/info", "GET"),
            "block_add_objects": ("/block/add-objects", "POST"),
            "block_remove_objects": ("/block/remove-objects", "POST"),
            "block_replace_geometry": ("/block/replace-geometry", "POST"),
            "block_replace_object_geometry": ("/block/replace-object-geometry", "POST"),
            "block_replace_object_geometry_batch": ("/block/replace-object-geometry-batch", "POST"),
            "block_transform_object": ("/block/transform-object", "POST"),
            "block_transform_object_batch": ("/block/transform-object-batch", "POST"),
            "block_transform_instance_batch": ("/block/transform-instance-batch", "POST"),
            "block_instances": ("/block/instances", "GET"),
            "block_replace_instance": ("/block/replace-instance", "POST"),
            "block_replace_instance_batch": ("/block/replace-instance-batch", "POST"),
            "block_reset_scale": ("/block/reset-scale", "POST"),
            "block_link": ("/block/link", "POST"),
            "block_refresh": ("/block/refresh", "POST"),
            "block_unlink": ("/block/unlink", "POST"),
            "block_purge": ("/block/purge", "POST"),
            "block_duplicate": ("/block/duplicate", "POST"),
            "block_nested": ("/block/nested", "GET"),

            # Text and dimensions
            "text": ("/text", "POST"),
            "dimension": ("/dimension", "POST"),

            # Delete (DELETE method)
            "delete": ("/delete", "DELETE"),

            # Intersection operations
            "intersect_curves": ("/intersect/curves", "POST"),
            "intersect_curve_surface": ("/intersect/curve-surface", "POST"),
            "intersect_curve_brep": ("/intersect/curve-brep", "POST"),
            "intersect_breps": ("/intersect/breps", "POST"),
            "intersect_plane": ("/intersect/plane", "POST"),

            # Projection operations
            "project_curve": ("/project/curve", "POST"),
            "pull_curve": ("/pull/curve", "POST"),

            # Offset operations
            "offset_curve": ("/offset/curve", "POST"),
            "offset_curve_on_surface": ("/offset/curve-on-surface", "POST"),
            "offset_brep": ("/offset/brep", "POST"),

            # Split/trim operations
            "split_brep": ("/split/brep", "POST"),
            "trim_brep": ("/trim/brep", "POST"),
            "split_face": ("/split/face", "POST"),

            # SubD operations
            "subd_box": ("/subd/box", "POST"),
            "subd_sphere": ("/subd/sphere", "POST"),
            "subd_cylinder": ("/subd/cylinder", "POST"),
            "subd_from_mesh": ("/subd/from-mesh", "POST"),
            "subd_from_surface": ("/subd/from-surface", "POST"),
            "subd_subdivide": ("/subd/subdivide", "POST"),
            "subd_crease": ("/subd/crease", "POST"),
            "subd_to_brep": ("/subd/to-brep", "POST"),
            "subd_to_mesh": ("/subd/to-mesh", "POST"),

            # Mesh operations
            "mesh_from_brep": ("/mesh/from-brep", "POST"),
            "mesh_box": ("/mesh/box", "POST"),
            "mesh_sphere": ("/mesh/sphere", "POST"),
            "mesh_cylinder": ("/mesh/cylinder", "POST"),
            "mesh_cone": ("/mesh/cone", "POST"),
            "mesh_boolean": ("/mesh/boolean", "POST"),
            "mesh_reduce": ("/mesh/reduce", "POST"),
            "quad_remesh": ("/mesh/quad-remesh", "POST"),
            "mesh_repair": ("/mesh/repair", "POST"),
            "mesh_smooth": ("/mesh/smooth", "POST"),
            "mesh_weld": ("/mesh/weld", "POST"),
            "mesh_unweld": ("/mesh/unweld", "POST"),

            # Analysis operations
            "curvature_curve": ("/analysis/curvature/curve", "GET"),
            "curvature_surface": ("/analysis/curvature/surface", "GET"),
            "draft_angle": ("/analysis/draft-angle", "GET"),
            "closest_point": ("/analysis/closest-point", "GET"),
            "curve_point_at": ("/analysis/curve/point-at", "GET"),
            "curve_tangent": ("/analysis/curve/tangent", "GET"),
            "curve_frame": ("/analysis/curve/frame", "GET"),
            "surface_normal": ("/analysis/surface/normal", "GET"),
            "brep_edges": ("/analysis/brep/edges", "GET"),
            "brep_faces": ("/analysis/brep/faces", "GET"),
            "brep_vertices": ("/analysis/brep/vertices", "GET"),
            "is_closed": ("/analysis/is-closed", "GET"),
            "is_valid": ("/analysis/is-valid", "GET"),
        }

        return MAPPINGS.get(name, (None, "POST"))


class MockExecutor:
    """Mock executor for testing without Rhino."""

    async def ping(self) -> bool:
        return True

    def ping_sync(self) -> bool:
        return True

    async def execute(self, tool_name: str, params: dict[str, Any]) -> ExecutionResult:
        """Return a mock success result."""
        denial = deny_if_contained(tool_name, DispatchOrigin.INTERNAL_HANDLER)
        if denial is not None:
            return ExecutionResult(
                tool_name=tool_name,
                params={},
                success=False,
                response=denial,
                error="legacy_semantic_tool_contained",
            )
        return ExecutionResult(
            tool_name=tool_name,
            params=params,
            success=True,
            response={"success": True, "data": {"mock": True}},
            duration_ms=10.0,
        )

    def execute_sync(self, tool_name: str, params: dict[str, Any]) -> ExecutionResult:
        return asyncio.run(self.execute(tool_name, params))
