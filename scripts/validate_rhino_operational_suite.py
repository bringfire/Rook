import asyncio
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mcp_server" / "src"))

from rook.bridge import get_rhino_host, native_client  # noqa: E402
from rook.server import _mcp_tool_executor  # noqa: E402


def _discover_native_base_url() -> str:
    """Resolve native plugin base URL from discovery files or NATIVE_PORT env var."""
    env_port = os.environ.get("NATIVE_PORT")
    if env_port:
        return f"http://127.0.0.1:{env_port}"
    url = get_rhino_host()
    if url is None:
        print("ERROR: No Rhino native plugin discovered.")
        print("Ensure Rhino is running with RookNative loaded, or set NATIVE_PORT=12345.")
        raise SystemExit(1)
    return url


NATIVE_BASE_URL = _discover_native_base_url()
TOOL_TIMEOUT_SECONDS = 20.0


def is_tool_error(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, dict):
        if result.get("success") is False:
            return True
        if result.get("error"):
            return True
        data = result.get("data")
        if isinstance(data, str) and data.startswith("Error:"):
            return True
    return False


def get_guid(result: dict[str, Any]) -> str | None:
    if not isinstance(result, dict):
        return None
    return (
        result.get("id")
        or result.get("guid")
        or result.get("Guid")
        or result.get("instanceId")
        or result.get("sessionId")
    )


class Suite:
    def __init__(self) -> None:
        self.checks: list[tuple[str, bool, Any]] = []

    def record(self, label: str, ok: bool, detail: Any) -> None:
        self.checks.append((label, ok, detail))

    def expect(self, label: str, result: Any, predicate) -> Any:
        ok = False
        if not is_tool_error(result):
            try:
                ok = predicate(result)
            except Exception as exc:
                ok = False
                result = {"result": result, "predicateError": str(exc)}
        self.record(label, ok, result)
        return result

    def expect_raw(self, label: str, ok: bool, detail: Any) -> None:
        self.record(label, ok, detail)

    def summarize(self) -> int:
        failed = False
        for label, ok, detail in self.checks:
            print(f"{'PASS' if ok else 'FAIL'}: {label}")
            if not ok:
                failed = True
                print(json.dumps(detail, indent=2, default=str))
        return 1 if failed else 0


async def call_native(endpoint: str, method: str = "GET", data: dict[str, Any] | None = None) -> tuple[int, dict[str, Any], httpx.Headers]:
    async with native_client(timeout=30.0) as client:
        url = f"{NATIVE_BASE_URL}{endpoint}"
        if method == "GET":
            response = await client.get(url, params=data)
        else:
            response = await client.post(url, json=data or {})
        return response.status_code, response.json(), response.headers


async def get_prompt_state() -> dict[str, Any]:
    status, body, _ = await call_native("/command/prompt", "GET")
    if status == 200 and isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return {}


def prompt_is_interactive(prompt_state: dict[str, Any]) -> bool:
    prompt = str(prompt_state.get("prompt") or "").strip()
    options = prompt_state.get("options") or []
    default_value = prompt_state.get("default_value")
    if prompt in ("", "Command") and not options and default_value in (None, ""):
        return False
    return bool(prompt_state.get("is_active")) or prompt not in ("", "Command")


async def cancel_active_command() -> dict[str, Any]:
    status, body, _ = await call_native("/command/cancel", "POST", {})
    if status == 200 and isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            return data
    return {"cancelled": False, "status": status, "body": body}


async def guarded_call_native(endpoint: str, method: str = "GET", data: dict[str, Any] | None = None) -> tuple[int, dict[str, Any], httpx.Headers]:
    prompt_before = await get_prompt_state()
    if prompt_is_interactive(prompt_before):
        cancel_result = await cancel_active_command()
        return 409, {
            "success": False,
            "data": f"Active Rhino command before {endpoint}: {prompt_before.get('prompt', 'Command')}",
            "interactivePrompt": prompt_before,
            "cancelResult": cancel_result,
        }, httpx.Headers()

    try:
        status, body, headers = await asyncio.wait_for(
            call_native(endpoint, method, data),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        prompt_state = await get_prompt_state()
        cancel_result = await cancel_active_command() if prompt_is_interactive(prompt_state) else {}
        return 408, {
            "success": False,
            "data": f"Native call {endpoint} timed out",
            "interactivePrompt": prompt_state,
            "cancelResult": cancel_result,
        }, httpx.Headers()

    prompt_after = await get_prompt_state()
    if prompt_is_interactive(prompt_after):
        cancel_result = await cancel_active_command()
        return 409, {
            "success": False,
            "data": f"Native call {endpoint} left Rhino in an interactive command: {prompt_after.get('prompt', 'Command')}",
            "interactivePrompt": prompt_after,
            "cancelResult": cancel_result,
            "nativeStatus": status,
            "nativeBody": body,
        }, headers

    return status, body, headers


async def tool(name: str, args: dict[str, Any] | None = None) -> Any:
    print(f"RUN: {name}", flush=True)
    prompt_before = await get_prompt_state()
    if prompt_is_interactive(prompt_before):
        await cancel_active_command()
        return {
            "success": False,
            "data": f"Active Rhino command before {name}: {prompt_before.get('prompt', 'Command')}",
            "interactivePrompt": prompt_before,
        }

    payload = dict(args or {})
    try:
        result = await asyncio.wait_for(
            _mcp_tool_executor(name, payload),
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        prompt_state = await get_prompt_state()
        cancel_result = await cancel_active_command() if prompt_is_interactive(prompt_state) else {}
        return {
            "success": False,
            "data": f"Tool {name} timed out",
            "interactivePrompt": prompt_state,
            "cancelResult": cancel_result,
        }

    prompt_after = await get_prompt_state()
    if prompt_is_interactive(prompt_after):
        cancel_result = await cancel_active_command()
        return {
            "success": False,
            "data": f"Tool {name} left Rhino in an interactive command: {prompt_after.get('prompt', 'Command')}",
            "interactivePrompt": prompt_after,
            "cancelResult": cancel_result,
            "toolResult": result,
        }

    return result


async def main() -> int:
    suite = Suite()
    tmpdir = Path(tempfile.gettempdir()) / f"rook_runtime_{uuid.uuid4().hex[:8]}"
    tmpdir.mkdir(parents=True, exist_ok=True)
    export_3dm = tmpdir / "runtime_export.3dm"
    save_3dm = tmpdir / "runtime_doc.3dm"
    game_3dm = tmpdir / "runtime_game_export.3dm"

    # Baseline and clean document
    ping = await tool("rhino_ping")
    suite.expect(
        "rhino_ping",
        ping,
        lambda r: r == "pong" or (isinstance(r, dict) and (r.get("data") == "pong" or r.get("success") is True)),
    )

    doc_new = await tool("rhino_document_ops", {"action": "new"})
    suite.expect("rhino_document_ops new", doc_new, lambda r: isinstance(r, dict) and ("name" in r or r.get("success") is True or r.get("created") is True))

    doc_units = await tool("rhino_document_ops", {"action": "set_units", "units": "Millimeters"})
    suite.expect("rhino_document_ops set_units", doc_units, lambda r: isinstance(r, dict) and ("newUnits" in r or r.get("success") is True or "units" in r))

    # Layer family
    layer_name = f"Runtime::{uuid.uuid4().hex[:6]}"
    layer_create = await tool("rhino_layer_create", {"name": layer_name, "color": [20, 120, 220]})
    suite.expect("rhino_layer_create", layer_create, lambda r: isinstance(r, dict) and (r.get("fullPath") == layer_name or r.get("created") is True or r.get("success") is True))

    layer_current = await tool("rhino_layer_current", {"name": layer_name})
    suite.expect("rhino_layer_current", layer_current, lambda r: r.get("success") is True or r.get("currentLayer") == layer_name)

    default_layer_current = await tool("rhino_layer_current", {"name": "Default"})
    suite.expect("rhino_layer_current default", default_layer_current, lambda r: r.get("success") is True or r.get("currentLayer") == "Default")

    layer_hide = await tool("rhino_layer_visibility", {"name": layer_name, "visible": False})
    suite.expect("rhino_layer_visibility hide", layer_hide, lambda r: isinstance(r, dict) and (r.get("visible") is False or r.get("success") is True))

    layer_show = await tool("rhino_layer_visibility", {"name": layer_name, "visible": True})
    suite.expect("rhino_layer_visibility show", layer_show, lambda r: isinstance(r, dict) and (r.get("visible") is True or r.get("success") is True))

    layer_lock = await tool("rhino_layer_lock", {"name": layer_name, "locked": True})
    suite.expect("rhino_layer_lock", layer_lock, lambda r: isinstance(r, dict) and (r.get("locked") is True or r.get("success") is True))

    layer_unlock = await tool("rhino_layer_lock", {"name": layer_name, "locked": False})
    suite.expect("rhino_layer_unlock", layer_unlock, lambda r: isinstance(r, dict) and (r.get("locked") is False or r.get("success") is True))

    layer_current = await tool("rhino_layer_current", {"name": layer_name})
    suite.expect("rhino_layer_current restore", layer_current, lambda r: r.get("success") is True or r.get("currentLayer") == layer_name)

    # Geometry creation family
    line = await tool("rhino_create", {
        "type": "LINE",
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "name": "runtime_line",
        "layer": layer_name,
    })
    suite.expect("rhino_create line", line, lambda r: get_guid(r) is not None)

    circle = await tool("rhino_create", {
        "type": "CIRCLE",
        "center": [0, 0, 0],
        "radius": 5,
        "name": "runtime_circle",
        "layer": layer_name,
    })
    suite.expect("rhino_create circle", circle, lambda r: get_guid(r) is not None)

    box = await tool("rhino_create", {
        "type": "BOX",
        "origin": [0, 0, 0],
        "width": 10,
        "depth": 8,
        "height": 6,
        "name": "runtime_box",
        "layer": layer_name,
    })
    suite.expect("rhino_create box", box, lambda r: get_guid(r) is not None)

    sphere = await tool("rhino_create", {
        "type": "SPHERE",
        "center": [20, 0, 0],
        "radius": 4,
        "name": "runtime_sphere",
        "layer": layer_name,
    })
    suite.expect("rhino_create sphere", sphere, lambda r: get_guid(r) is not None)

    text = await tool("rhino_text", {
        "text": "Runtime",
        "point": [0, 12, 0],
        "height": 2.5,
        "layer": layer_name,
    })
    suite.expect("rhino_text", text, lambda r: get_guid(r) is not None)

    line_id = get_guid(line)
    circle_id = get_guid(circle)
    box_id = get_guid(box)
    sphere_id = get_guid(sphere)
    text_id = get_guid(text)
    suite.expect_raw(
        "created ids captured",
        all([line_id, circle_id, box_id, sphere_id]),
        {"line": line, "circle": circle, "box": box, "sphere": sphere, "text": text},
    )
    if not all([line_id, circle_id, box_id, sphere_id]):
        return suite.summarize()

    dim = await tool("rhino_dimension", {
        "type": "DIMENSION_LINEAR",
        "start": [0, 0, 0],
        "end": [10, 0, 0],
        "offset": 2,
        "layer": layer_name,
    })
    suite.expect("rhino_dimension", dim, lambda r: get_guid(r) is not None)

    # Core document/object queries
    doc = await tool("rhino_document")
    suite.expect("rhino_document", doc, lambda r: "name" in r or "documentName" in r)

    layers = await tool("rhino_layers")
    suite.expect("rhino_layers", layers, lambda r: len(r.get("layers", [])) > 0 or r.get("count", 0) > 0)

    objects = await tool("rhino_objects")
    suite.expect("rhino_objects", objects, lambda r: len(r.get("objects", [])) >= 4 or r.get("count", 0) >= 4)

    # Selection family
    select = await tool("rhino_select", {"ids": [box_id, sphere_id]})
    suite.expect("rhino_select", select, lambda r: r.get("selected", 0) >= 2 or r.get("selectedCount", 0) >= 2 or r.get("count", 0) >= 2)

    selection = await tool("rhino_selection")
    suite.expect("rhino_selection", selection, lambda r: r.get("count", 0) >= 2)

    select_by_name = await tool("rhino_select_by_name", {"namePattern": "runtime_*"})
    suite.expect("rhino_select_by_name", select_by_name, lambda r: r.get("selected", 0) >= 1 or r.get("selectedCount", 0) >= 1 or r.get("count", 0) >= 1)

    select_by_type = await tool("rhino_select_by_type", {"type": "Brep"})
    suite.expect("rhino_select_by_type", select_by_type, lambda r: r.get("selected", 0) >= 1 or r.get("selectedCount", 0) >= 1 or r.get("count", 0) >= 1)

    select_none = await tool("rhino_select_none")
    suite.expect("rhino_select_none", select_none, lambda r: r.get("success") is True or r.get("count", 0) == 0)

    # Transform/copy/delete family
    copy_result = await tool("rhino_copy", {"ids": [box_id], "offset": [30, 0, 0]})
    suite.expect("rhino_copy", copy_result, lambda r: len(r.get("copiedIds", [])) >= 1 or r.get("copied", 0) >= 1 or r.get("copiedCount", 0) >= 1 or len(r.get("copies", [])) >= 1)
    copied_box_id = None
    if isinstance(copy_result, dict):
        copied_ids = copy_result.get("copiedIds") or []
        copies = copy_result.get("copies") or []
        copied_box_id = copied_ids[0] if copied_ids else (copies[0].get("newId") if copies else None)

    transform = await tool("rhino_transform", {"ids": [sphere_id], "operation": "move", "vector": [0, 10, 0]})
    suite.expect("rhino_transform move", transform, lambda r: r.get("transformed", 0) >= 1 or r.get("transformedCount", 0) >= 1 or r.get("success") is True)

    delete_copy = await tool("rhino_delete", {"ids": [copied_box_id]}) if copied_box_id else {"success": False}
    suite.expect("rhino_delete", delete_copy, lambda r: r.get("deleted", 0) >= 1 or r.get("deletedCount", 0) >= 1 or r.get("success") is True)

    # Measurement family
    measure_distance = await tool("rhino_measure_distance", {"from": [0, 0, 0], "to": [10, 0, 0]})
    suite.expect("rhino_measure_distance", measure_distance, lambda r: abs(float(r.get("distance", 0)) - 10.0) < 1e-6)

    measure_length = await tool("rhino_measure_length", {"id": line_id})
    suite.expect("rhino_measure_length", measure_length, lambda r: float(r.get("length", 0)) > 0)

    measure_bbox = await tool("rhino_measure_bbox", {"id": box_id})
    suite.expect("rhino_measure_bbox", measure_bbox, lambda r: "min" in r and "max" in r)

    measure_centroid = await tool("rhino_measure_centroid", {"id": box_id})
    suite.expect("rhino_measure_centroid", measure_centroid, lambda r: "centroid" in r or "point" in r)

    # Group family
    group = await tool("rhino_group", {"ids": [box_id, sphere_id], "name": f"runtime_group_{uuid.uuid4().hex[:6]}"})
    suite.expect("rhino_group", group, lambda r: r.get("success") is True or r.get("groupIndex") is not None)

    # Block family
    block_name = f"RuntimeBlock_{uuid.uuid4().hex[:6]}"
    block_create = await tool("rhino_block_create", {
        "ids": [line_id, circle_id],
        "name": block_name,
        "basePoint": [0, 0, 0],
        "replaceWithInstance": False,
    })
    suite.expect("rhino_block_create", block_create, lambda r: r.get("success") is True or r.get("name") == block_name)

    blocks = await tool("rhino_blocks")
    suite.expect("rhino_blocks", blocks, lambda r: len(r.get("blocks", [])) >= 1 or r.get("count", 0) >= 1)

    block_insert = await tool("rhino_block_insert", {"name": block_name, "point": [50, 0, 0]})
    suite.expect("rhino_block_insert", block_insert, lambda r: get_guid(r) is not None or r.get("inserted") is True)
    block_instance_id = get_guid(block_insert)

    block_explode = await tool("rhino_block_explode", {"id": block_instance_id}) if block_instance_id else {"success": False}
    suite.expect("rhino_block_explode", block_explode, lambda r: r.get("success") is True or len(r.get("createdIds", [])) >= 1)

    # Curve family - use fresh objects so earlier block operations do not affect IDs
    curve_line = await tool("rhino_create", {
        "type": "LINE",
        "start": [0, 20, 0],
        "end": [10, 20, 0],
        "name": "runtime_curve_line",
        "layer": layer_name,
    })
    suite.expect("rhino_create curve line", curve_line, lambda r: get_guid(r) is not None)
    curve_line_id = get_guid(curve_line)

    curve_circle = await tool("rhino_create", {
        "type": "CIRCLE",
        "center": [5, 20, 0],
        "radius": 4,
        "name": "runtime_curve_circle",
        "layer": layer_name,
    })
    suite.expect("rhino_create curve circle", curve_circle, lambda r: get_guid(r) is not None)
    curve_circle_id = get_guid(curve_circle)

    divide = await tool("rhino_curve_ops", {"action": "divide", "id": curve_line_id, "count": 5})
    suite.expect("rhino_curve_ops divide", divide, lambda r: len(r.get("points", [])) >= 5 or r.get("count", 0) >= 5)

    offset_curve = await tool("rhino_offset_curve", {"curveId": curve_line_id, "distance": 2.0, "cornerStyle": 1})
    suite.expect("rhino_offset_curve", offset_curve, lambda r: len(r.get("createdIds", [])) >= 1 or len(r.get("offsetIds", [])) >= 1 or r.get("success") is True)

    intersect_curves = await tool("rhino_intersect_curves", {"curveId1": curve_line_id, "curveId2": curve_circle_id})
    suite.expect("rhino_intersect_curves", intersect_curves, lambda r: "points" in r or "intersections" in r)

    # Material + mapping family
    material_name = f"RuntimeMaterial_{uuid.uuid4().hex[:6]}"
    mat_create = await tool("rhino_material_ops", {"action": "create", "name": material_name, "color": [180, 30, 30]})
    suite.expect("rhino_material_ops create", mat_create, lambda r: r.get("success") is True or r.get("name") == material_name)

    mat_assign = await tool("rhino_material_ops", {"action": "assign", "name": material_name, "id": box_id})
    suite.expect("rhino_material_ops assign", mat_assign, lambda r: r.get("success") is True or r.get("assignedCount", 0) >= 1)

    uv_planar = await tool("rhino_apply_uv_planar_mapping", {"ids": [box_id]})
    suite.expect("rhino_apply_uv_planar_mapping", uv_planar, lambda r: r.get("success") is True or r.get("mapped", 0) >= 1 or r.get("mapped_count", 0) >= 1)

    # Mesh/SubD family
    mesh_box = await tool("rhino_mesh_box", {"origin": [70, 0, 0], "width": 4, "depth": 4, "height": 4})
    suite.expect("rhino_mesh_box", mesh_box, lambda r: get_guid(r) is not None)
    mesh_box_id = get_guid(mesh_box)

    subd_box = await tool("rhino_subd_box", {"origin": [80, 0, 0], "width": 4, "depth": 4, "height": 4})
    suite.expect("rhino_subd_box", subd_box, lambda r: get_guid(r) is not None)
    subd_box_id = get_guid(subd_box)

    subd_to_brep = await tool("rhino_subd_to_brep", {"id": subd_box_id}) if subd_box_id else {"success": False}
    suite.expect("rhino_subd_to_brep", subd_to_brep, lambda r: get_guid(r) is not None or len(r.get("createdIds", [])) >= 1)

    # Analysis family
    is_closed = await tool("rhino_is_closed", {"id": box_id})
    suite.expect("rhino_is_closed", is_closed, lambda r: "isClosed" in r or "closed" in r)

    is_valid = await tool("rhino_is_valid", {"id": box_id})
    suite.expect("rhino_is_valid", is_valid, lambda r: r.get("isValid") is True or r.get("valid") is True)

    # Viewport
    viewport = await tool("rhino_viewport", {"width": 320, "height": 240, "saveToFile": True})
    suite.expect("rhino_viewport", viewport, lambda r: bool(r.get("path")) or bool(r.get("filePath")))

    # Scene graph family
    scene_graph = await tool("scene_graph", {"depth": "summary"})
    suite.expect("scene_graph", scene_graph, lambda r: "nodeCount" in r or "counts" in r or "summary" in r)

    scene_stats = await tool("scene_stats")
    suite.expect("scene_stats", scene_stats, lambda r: "nodeCount" in r or "edgeCount" in r or "relationshipTypes" in r or "nodes" in r or "edges" in r)

    scene_query = await tool("scene_query", {"layers": [layer_name], "depth": "compact"})
    suite.expect("scene_query", scene_query, lambda r: "nodes" in r or "nodeCount" in r or "results" in r)

    overlay_on = await tool("scene_overlay", {"enabled": True})
    suite.expect("scene_overlay on", overlay_on, lambda r: r.get("success") is True or r.get("enabled") is True)

    overlay_off = await tool("scene_overlay", {"enabled": False})
    suite.expect("scene_overlay off", overlay_off, lambda r: r.get("success") is True or r.get("enabled") is False)

    # Gumball family
    gumball_activate = await tool("rhino_gumball_activate", {"ids": [box_id]})
    suite.expect("rhino_gumball_activate", gumball_activate, lambda r: r.get("success") is True or r.get("active") is True or r.get("enabled") is True)

    gumball_status = await tool("rhino_gumball_status")
    suite.expect("rhino_gumball_status", gumball_status, lambda r: "active" in r or "enabled" in r)

    gumball_deactivate = await tool("rhino_gumball_deactivate")
    suite.expect("rhino_gumball_deactivate", gumball_deactivate, lambda r: r.get("success") is True or r.get("active") is False or r.get("enabled") is False)

    # Export/import family
    export_result = await tool("rhino_export", {"path": str(export_3dm), "ids": [box_id, sphere_id]})
    suite.expect("rhino_export", export_result, lambda r: export_3dm.exists() and export_3dm.stat().st_size > 0)

    save_result = await tool("rhino_document_ops", {"action": "save", "path": str(save_3dm)})
    suite.expect("rhino_document_ops save", save_result, lambda r: save_3dm.exists() and save_3dm.stat().st_size > 0)

    import_doc_new = await tool("rhino_document_ops", {"action": "new"})
    suite.expect("rhino_document_ops new before import", import_doc_new, lambda r: r.get("success") is True or r.get("created") is True or "name" in r)

    import_result = await tool("rhino_import", {"path": str(export_3dm)})
    suite.expect("rhino_import", import_result, lambda r: r.get("success") is True or r.get("imported", 0) >= 1 or r.get("importedCount", 0) >= 1)

    # Game export family
    validate_export = await tool("rhino_validate_export")
    suite.expect("rhino_validate_export", validate_export, lambda r: r.get("success") is True or "issues" in r or "summary" in r)

    prepare_export = await tool("rhino_prepare_for_game_export", {"path": str(game_3dm), "skip_tagging": False, "skip_validation": False})
    suite.expect("rhino_prepare_for_game_export", prepare_export, lambda r: game_3dm.exists() and game_3dm.stat().st_size > 0)

    # Companion-backed make2d parity check
    make2d_status, make2d_body, _ = await guarded_call_native(
        "/make2d",
        "POST",
        {
            "view": "Front",
            "ids": [box_id, sphere_id],
            "showHiddenLines": False,
            "targetLayer": "RuntimeMake2D",
        },
    )
    suite.expect_raw(
        "native /make2d",
        make2d_status == 200 and make2d_body.get("success") is True,
        {"status": make2d_status, "body": make2d_body},
    )

    # Session family
    session_current = await tool("session_current")
    suite.expect("session_current", session_current, lambda r: r.get("status") == "active" or r.get("sessionId") is not None or r.get("id") is not None)

    session_history = await tool("session_history", {"limit": 20})
    suite.expect("session_history", session_history, lambda r: len(r.get("commands", [])) > 0 or len(r.get("entries", [])) > 0 or isinstance(r.get("count"), int))

    # Cleanup families
    mat_delete = await tool("rhino_material_ops", {"action": "delete", "name": material_name})
    suite.expect("rhino_material_ops delete", mat_delete, lambda r: r.get("success") is True or "deleted" in r)

    layer_delete = await tool("rhino_layer_delete", {"name": layer_name})
    if is_tool_error(layer_delete):
        data = layer_delete.get("data") if isinstance(layer_delete, dict) else ""
        ok = isinstance(data, str) and ("not found" in data.lower() or "contains" in data.lower())
        suite.expect_raw("rhino_layer_delete", ok, layer_delete)
    else:
        suite.expect("rhino_layer_delete", layer_delete, lambda r: r.get("success") is True or "deleted" in r)

    return suite.summarize()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
