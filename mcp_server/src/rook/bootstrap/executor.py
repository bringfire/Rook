"""
MCP Tool Executor

Provides execution of MCP tools for bootstrap testing.
Can use either direct HTTP calls or the MCP protocol.
"""

import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Callable

from ..bridge import NATIVE_CLIENT_HEADERS, get_rhino_host
from ..tool_lifecycle_runtime import DispatchOrigin, deny_if_contained

logger = logging.getLogger("rook.bootstrap")

# Default Rhino HTTP server is discovered at runtime.
DEFAULT_RHINO_URL: str | None = None


class HttpExecutor:
    """
    Execute MCP tools via direct HTTP calls to Rhino.

    This bypasses the MCP protocol and calls the Rhino HTTP server directly.
    Useful for bootstrap testing when running outside of Claude Code.
    """

    def __init__(self, base_url: str | None = DEFAULT_RHINO_URL):
        resolved = base_url or get_rhino_host()
        if resolved is None:
            raise RuntimeError(
                "No Rhino instance discovered. "
                "Ensure Rhino is running with RookNative loaded."
            )
        self.base_url = resolved.rstrip("/")

    def ping(self) -> bool:
        """Check if Rhino is reachable."""
        try:
            req = urllib.request.Request(f"{self.base_url}/ping", headers=dict(NATIVE_CLIENT_HEADERS))
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Ping failed: {e}")
            return False

    def _get_curve_endpoint(self, params: dict[str, Any]) -> tuple[str, str, dict]:
        """Get the correct endpoint for curve operations based on action."""
        action = params.get("action", "")
        action_map = {
            "join": "/curve/join",
            "explode": "/curve/explode",
            "divide": "/curve/divide",
            "extend": "/curve/extend",
            "trim": "/curve/trim",
            "split": "/curve/split",
            "rebuild": "/curve/rebuild",
            "fillet": "/curve/fillet",
        }
        endpoint = action_map.get(action, f"/curve/{action}")
        return ("POST", endpoint, params)

    def _get_document_ops_endpoint(self, params: dict[str, Any]) -> tuple[str, str, dict]:
        """Get the correct endpoint for document operations based on action."""
        action = params.get("action", "")
        action_map = {
            "undo": "/undo",
            "redo": "/redo",
            "save": "/document/save",
            "new": "/document/new",
            "set_units": "/document/units",
        }
        endpoint = action_map.get(action, f"/document/{action}")
        return ("POST", endpoint, params)

    def _get_material_endpoint(self, params: dict[str, Any]) -> tuple[str, str, dict]:
        """Get the correct endpoint for material operations based on action."""
        action = params.get("action", "")
        if action == "list":
            return ("GET", "/materials", None)
        elif action == "create":
            return ("POST", "/materials", params)
        elif action == "delete":
            return ("DELETE", "/materials", params)
        elif action == "assign":
            return ("POST", "/materials/assign", params)
        return ("POST", "/materials", params)

    def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Execute an MCP tool via HTTP.

        Maps tool names to HTTP endpoints and methods.
        """
        denial = deny_if_contained(tool_name, DispatchOrigin.INTERNAL_HANDLER)
        if denial is not None:
            return denial

        # Tool to endpoint mapping
        endpoint_map = {
            # Query tools (GET)
            "rhino_ping": ("GET", "/ping", None),
            "rhino_document": ("GET", "/document", None),
            "rhino_layers": ("GET", "/layers", None),
            "rhino_objects": ("GET", "/objects", params),
            "rhino_selection": ("GET", "/selection", None),
            "rhino_geometry": ("GET", "/geometry", params),
            "rhino_viewport": ("GET", "/viewport", params),
            "rhino_instances": ("GET", "/instances", None),

            # Measurement tools (GET)
            "rhino_measure_distance": ("GET", "/measure/distance", params),
            "rhino_measure_area": ("GET", "/measure/area", params),
            "rhino_measure_volume": ("GET", "/measure/volume", params),
            "rhino_measure_length": ("GET", "/measure/length", params),
            "rhino_measure_bbox": ("GET", "/measure/bbox", params),
            "rhino_measure_centroid": ("GET", "/measure/centroid", params),

            # Creation tools (POST)
            "rhino_create": ("POST", "/create", params),
            "rhino_text": ("POST", "/create", {**params, "type": "TEXT"}),
            "rhino_dimension": ("POST", "/dimension", params),

            # Layer tools - Note: create uses POST /layers, delete uses DELETE /layers
            "rhino_layer_create": ("POST", "/layers", params),
            "rhino_layer_create_batch": ("POST", "/layers/batch", params),
            "rhino_layer_delete": ("DELETE", "/layers", params),
            "rhino_layer_visibility": ("POST", "/layers/visibility", params),
            "rhino_layer_lock": ("POST", "/layers/lock", params),
            "rhino_layer_current": ("POST", "/layers/current", params),
            "rhino_layer_set_properties": ("POST", "/layers/properties", params),
            "rhino_layer_set_properties_batch": ("POST", "/layers/properties-batch", params),
            "rhino_layer_rename": ("POST", "/layers/rename", params),
            "rhino_layer_move_objects": ("POST", "/layers/move-objects", params),
            "rhino_layer_merge": ("POST", "/layers/merge", params),
            "rhino_layer_dependencies": ("GET", "/layers/dependencies", params),

            # Material / linetype / block audit
            "rhino_materials": ("GET", "/materials", params),
            "rhino_material_purge": ("POST", "/materials/purge", params),
            "rhino_linetypes": ("GET", "/linetypes", params),
            "rhino_linetype_purge": ("POST", "/linetypes/purge", params),
            "rhino_block_layer_census": ("GET", "/block/layer-census", params),

            # Selection tools (POST)
            # Selection tools - all use POST /select with different body params
            "rhino_select": ("POST", "/select", params),
            "rhino_select_by_type": ("POST", "/select", params),  # passes {type: ...}
            "rhino_select_by_name": ("POST", "/select", params),  # passes {namePattern: ...}
            "rhino_select_all": ("POST", "/select", {"all": True}),
            "rhino_select_none": ("POST", "/select", {"none": True}),
            "rhino_select_invert": ("POST", "/select", {"invert": True}),
            "rhino_deselect": ("POST", "/select", {"deselectIds": params.get("ids", []), "clear": False}),

            # Transform tools (POST)
            "rhino_transform": ("POST", "/transform", params),
            "rhino_copy": ("POST", "/copy", params),
            "rhino_delete": ("POST", "/delete", params),

            # Advanced geometry (POST)
            "rhino_boolean": ("POST", "/boolean", params),
            "rhino_extrude": ("POST", "/extrude", params),

            # Curve operations - routes based on action parameter
            "rhino_curve_ops": self._get_curve_endpoint(params),

            # Document operations - routes based on action parameter
            "rhino_document_ops": self._get_document_ops_endpoint(params),

            # Material operations - routes based on action parameter
            "rhino_material_ops": self._get_material_endpoint(params),

            # Script execution (POST)
            "rhino_execute": ("POST", "/execute", params),
            "rhino_command": ("POST", "/command", params),

            # Import/Export (POST)
            "rhino_import": ("POST", "/import", params),
            "rhino_export": ("POST", "/export", params),

            # Groups/Blocks (POST)
            "rhino_group": ("POST", "/group", params),
            "rhino_block_create": ("POST", "/block/create", params),
        }

        if tool_name not in endpoint_map:
            return {"success": False, "data": f"Unknown tool: {tool_name}"}

        method, endpoint, body = endpoint_map[tool_name]
        url = f"{self.base_url}{endpoint}"

        try:
            if method == "GET":
                # Add query params for GET (URL-encoded for safe layer paths)
                if body:
                    params = {k: str(v) for k, v in body.items() if v is not None}
                    if params:
                        url = f"{url}?{urllib.parse.urlencode(params)}"
                req = urllib.request.Request(url, headers=dict(NATIVE_CLIENT_HEADERS))
            else:
                # POST/DELETE/PUT with JSON body
                data = json.dumps(body or {}).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json", **NATIVE_CLIENT_HEADERS},
                    method=method
                )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result

        except urllib.error.HTTPError as e:
            try:
                error_body = json.loads(e.read().decode("utf-8"))
                return {"success": False, "data": error_body}
            except:
                return {"success": False, "data": f"HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {"success": False, "data": f"Connection error: {e.reason}"}
        except Exception as e:
            return {"success": False, "data": f"Error: {str(e)}"}


def create_http_executor(base_url: str | None = DEFAULT_RHINO_URL) -> Callable:
    """
    Create an HTTP-based tool executor.

    Returns a callable that can be passed to BootstrapRunner.
    """
    executor = HttpExecutor(base_url)

    # Verify connection
    if not executor.ping():
        logger.warning(f"Cannot connect to Rhino at {executor.base_url}")
        return None

    logger.info(f"Connected to Rhino at {executor.base_url}")
    return executor.execute


def create_mock_executor() -> Callable:
    """
    Create a mock executor for testing without Rhino.

    Returns predictable results based on expected outcomes.
    """
    def mock_execute(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        denial = deny_if_contained(tool_name, DispatchOrigin.INTERNAL_HANDLER)
        if denial is not None:
            return denial
        # Simulate different outcomes based on tool/params

        # Query tools always succeed
        if tool_name.startswith("rhino_") and any(
            tool_name.endswith(x) for x in ["ping", "document", "layers", "objects", "selection", "viewport", "instances"]
        ):
            return {"success": True, "data": {"mock": True, "tool": tool_name}}

        # Create tools - check for invalid params
        if tool_name == "rhino_create":
            type_ = params.get("type", "")

            # Missing required params
            if type_ == "POINT" and "point" not in params:
                return {"success": False, "data": "Missing required parameter: point"}
            if type_ == "LINE" and ("start" not in params or "end" not in params):
                return {"success": False, "data": "Missing required parameters: start, end"}
            if type_ == "CIRCLE" and params.get("radius", 1) <= 0:
                return {"success": False, "data": "Radius must be positive"}
            if type_ == "SPHERE" and params.get("radius", 1) <= 0:
                return {"success": False, "data": "Radius must be positive"}
            if type_ == "POLYLINE" and len(params.get("points", [])) < 2:
                return {"success": False, "data": "Polyline requires at least 2 points"}

            # Color validation
            color = params.get("color")
            if color is not None:
                if isinstance(color, str):
                    return {"success": False, "data": "Color must be [r,g,b] array, not string"}
                if isinstance(color, dict):
                    # Object format might work or not - simulate success
                    pass

            # Success with ID
            return {
                "success": True,
                "data": {
                    "id": f"mock-{type_.lower()}-001",
                    "type": type_,
                }
            }

        # Layer operations
        if tool_name == "rhino_layer_create":
            return {"success": True, "data": {"name": params.get("name", "Layer")}}

        if tool_name == "rhino_layer_create_batch":
            layers = []
            for item in params.get("layers", []):
                if not isinstance(item, dict):
                    continue
                layer = {
                    "key": item.get("key"),
                    "name": item.get("name"),
                }
                if "parentKey" in item:
                    layer["parentKey"] = item.get("parentKey")
                layers.append(layer)
            return {"success": True, "data": {"count": len(layers), "layers": layers}}

        if tool_name == "rhino_layer_delete":
            return {"success": True, "data": "Layer deleted"}

        # Default success for other tools
        return {"success": True, "data": {"mock": True, "tool": tool_name}}

    return mock_execute
