import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mcp_server" / "src"))

from rook.bridge import get_rhino_host  # noqa: E402
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
EXAMPLE_GH = REPO_ROOT / "knowledge" / "gh" / "examples" / "spiral_staircase.ghx"
POINT_PARAM_GUID = "fbac3e32-f100-4292-8692-77240a42fd1a"


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
    return result.get("guid") or result.get("Guid")


class Suite:
    def __init__(self) -> None:
        self.checks: list[tuple[str, bool, Any]] = []

    def record(self, label: str, ok: bool, detail: Any) -> None:
        self.checks.append((label, ok, detail))

    def expect(self, label: str, result: Any, predicate) -> Any:
        ok = not is_tool_error(result) and predicate(result)
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


async def tool(name: str, args: dict[str, Any] | None = None) -> Any:
    payload = dict(args or {})
    return await _mcp_tool_executor(name, payload)


async def main() -> int:
    suite = Suite()

    # Baseline
    status = await tool("gh_status")
    suite.expect("gh_status", status, lambda r: r.get("available") is True)

    categories = await tool("gh_categories")
    suite.expect("gh_categories", categories, lambda r: r.get("totalCategories", 0) > 0)

    library = await tool("gh_library", {"search": "addition", "limit": 20})
    suite.expect("gh_library", library, lambda r: r.get("count", 0) > 0)
    addition = next(
        (
            component
            for component in library.get("components", [])
            if component.get("name") == "Addition"
            and component.get("nickName") == "A+B"
            and component.get("category") == "Maths"
        ),
        None,
    )
    suite.expect_raw("addition component located", addition is not None, library)
    if addition is None:
        return suite.summarize()

    python_lib = await tool("gh_library", {"search": "python 3 script", "limit": 10})
    suite.expect("gh_library python", python_lib, lambda r: r.get("count", 0) > 0)
    python_component = next(
        (component for component in python_lib.get("components", []) if component.get("name") == "Python 3 Script"),
        None,
    )
    suite.expect_raw("python component located", python_component is not None, python_lib)
    if python_component is None:
        return suite.summarize()

    # Working document
    document_new = await tool("gh_document_new")
    suite.expect("gh_document_new", document_new, lambda r: r.get("created") is True)

    query_empty = await tool("gh_query")
    suite.expect("gh_query after new", query_empty, lambda r: r.get("objectCount", -1) == 0)

    selection = await tool("gh_selection")
    suite.expect("gh_selection", selection, lambda r: r.get("count", -1) == 0)

    # Create operational test canvas
    slider_a = await tool("gh_create_slider", {
        "nickname": f"SuiteA_{uuid.uuid4().hex[:6]}",
        "min": 0,
        "max": 10,
        "value": 2,
        "x": 20,
        "y": 80,
    })
    suite.expect("gh_create_slider A", slider_a, lambda r: r.get("created") is True)

    slider_b = await tool("gh_create_slider", {
        "nickname": f"SuiteB_{uuid.uuid4().hex[:6]}",
        "min": 0,
        "max": 10,
        "value": 3,
        "x": 20,
        "y": 180,
    })
    suite.expect("gh_create_slider B", slider_b, lambda r: r.get("created") is True)

    panel = await tool("gh_create_panel", {
        "content": "Suite Panel",
        "x": 520,
        "y": 120,
    })
    suite.expect("gh_create_panel", panel, lambda r: r.get("created") is True)

    addition_comp = await tool("gh_create_component", {
        "guid": addition["guid"],
        "x": 240,
        "y": 120,
    })
    suite.expect("gh_create_component addition", addition_comp, lambda r: r.get("created") is True)

    script_comp = await tool("gh_create_component", {
        "guid": python_component["guid"],
        "x": 240,
        "y": 260,
    })
    suite.expect("gh_create_component python", script_comp, lambda r: r.get("created") is True)

    point_param = await tool("gh_create_component", {
        "guid": POINT_PARAM_GUID,
        "x": 240,
        "y": 360,
    })
    suite.expect("gh_create_component point param", point_param, lambda r: r.get("created") is True)

    slider_a_guid = get_guid(slider_a)
    slider_b_guid = get_guid(slider_b)
    panel_guid = get_guid(panel)
    addition_guid = get_guid(addition_comp)
    script_guid = get_guid(script_comp)
    point_param_guid = get_guid(point_param)

    suite.expect_raw(
        "created guid extraction",
        all([slider_a_guid, slider_b_guid, panel_guid, addition_guid, script_guid, point_param_guid]),
        {
            "slider_a": slider_a,
            "slider_b": slider_b,
            "panel": panel,
            "addition": addition_comp,
            "script": script_comp,
            "point_param": point_param,
        },
    )
    if not all([slider_a_guid, slider_b_guid, panel_guid, addition_guid, script_guid, point_param_guid]):
        return suite.summarize()

    query_created = await tool("gh_query")
    suite.expect("gh_query after creates", query_created, lambda r: r.get("objectCount", 0) >= 6)

    component_info = await tool("gh_component", {"guid": addition_guid})
    suite.expect("gh_component", component_info, lambda r: r.get("guid") == addition_guid)

    errors = await tool("gh_errors")
    suite.expect("gh_errors", errors, lambda r: "totalComponents" in r)

    get_slider_a = await tool("gh_get_value", {"guid": slider_a_guid})
    suite.expect("gh_get_value", get_slider_a, lambda r: str(r.get("guid")) == slider_a_guid)

    set_slider_a = await tool("gh_set_value", {"guid": slider_a_guid, "value": 7})
    suite.expect("gh_set_value", set_slider_a, lambda r: r.get("success") is True or r.get("guid") == slider_a_guid)

    get_slider_a_after = await tool("gh_get_value", {"guid": slider_a_guid})
    suite.expect("gh_get_value after set", get_slider_a_after, lambda r: str(r.get("value")) in {"7", "7.0"})

    set_script = await tool("gh_set_script", {"guid": script_guid, "script": "a = 42\nout = a"})
    suite.expect("gh_set_script set", set_script, lambda r: r.get("action") == "set")

    get_script = await tool("gh_set_script", {"guid": script_guid})
    suite.expect("gh_set_script get", get_script, lambda r: r.get("script") == "a = 42\nout = a")

    connect_a = await tool("gh_connect", {"sourceGuid": slider_a_guid, "targetGuid": addition_guid, "targetParam": "A"})
    suite.expect("gh_connect A", connect_a, lambda r: r.get("connected") is True)

    connect_b = await tool("gh_connect", {"sourceGuid": slider_b_guid, "targetGuid": addition_guid, "targetParam": "B"})
    suite.expect("gh_connect B", connect_b, lambda r: r.get("connected") is True)

    connections = await tool("gh_connections", {"guid": addition_guid})
    suite.expect("gh_connections", connections, lambda r: "inputs" in r or "outputs" in r)

    solve = await tool("gh_solve", {"delay": 25})
    suite.expect("gh_solve", solve, lambda r: r.get("scheduled") is True)

    inspect_output = await tool("gh_inspect_output", {"guid": addition_guid, "param": "R"})
    suite.expect("gh_inspect_output", inspect_output, lambda r: r.get("data_count", 0) >= 1)

    disconnect_b = await tool("gh_disconnect", {"sourceGuid": slider_b_guid, "targetGuid": addition_guid, "targetParam": "B"})
    suite.expect("gh_disconnect", disconnect_b, lambda r: r.get("disconnected") is True or r.get("removed") is True)

    reconnect_b = await tool("gh_connect", {"sourceGuid": slider_b_guid, "targetGuid": addition_guid, "targetParam": "B"})
    suite.expect("gh_reconnect B", reconnect_b, lambda r: r.get("connected") is True)

    move = await tool("gh_move", {
        "positions": [
            {"guid": slider_a_guid, "x": 40, "y": 80},
            {"guid": slider_b_guid, "x": 40, "y": 180},
            {"guid": addition_guid, "x": 280, "y": 120},
        ]
    })
    suite.expect("gh_move", move, lambda r: r.get("moved", 0) >= 3)

    align = await tool("gh_align", {"guids": [slider_a_guid, slider_b_guid, panel_guid], "direction": "left"})
    suite.expect("gh_align", align, lambda r: r.get("aligned", 0) >= 2)

    distribute = await tool("gh_distribute", {"guids": [slider_a_guid, addition_guid, panel_guid], "axis": "horizontal"})
    suite.expect("gh_distribute", distribute, lambda r: r.get("distributed", 0) >= 2)

    straighten = await tool("gh_straighten_wires", {})
    suite.expect("gh_straighten_wires", straighten, lambda r: r.get("straightened", 0) >= 0)

    preview_hide = await tool("gh_preview", {"guids": [addition_guid], "hidden": True})
    suite.expect("gh_preview hide", preview_hide, lambda r: r.get("modified", 0) >= 1)

    preview_show = await tool("gh_preview", {"guids": [addition_guid], "hidden": False})
    suite.expect("gh_preview show", preview_show, lambda r: r.get("modified", 0) >= 1)

    rhino_point = await _mcp_tool_executor("rhino_create", {"type": "POINT", "point": [1, 2, 3]})
    suite.expect("rhino_create point", rhino_point, lambda r: r.get("id") is not None)
    rhino_point_id = rhino_point.get("id") if isinstance(rhino_point, dict) else None

    set_reference = await tool("gh_set_reference", {"paramGuid": point_param_guid, "rhinoObjectId": rhino_point_id})
    suite.expect("gh_set_reference", set_reference, lambda r: str(r.get("guid")) == point_param_guid)

    get_reference = await tool("gh_get_reference", {"guid": point_param_guid})
    suite.expect("gh_get_reference", get_reference, lambda r: r.get("referenceCount", 0) == 1)

    clear_reference = await tool("gh_clear_reference", {"guid": point_param_guid})
    suite.expect("gh_clear_reference", clear_reference, lambda r: str(r.get("guid")) == point_param_guid)

    get_reference_after = await tool("gh_get_reference", {"guid": point_param_guid})
    suite.expect("gh_get_reference after clear", get_reference_after, lambda r: r.get("referenceCount", -1) == 0)

    group = await tool("gh_group", {"guids": [slider_a_guid, slider_b_guid, addition_guid], "nickname": "SuiteGroup"})
    suite.expect("gh_group", group, lambda r: r.get("created") is True)

    canvas_cleanup = await tool("gh_canvas_cleanup", {"dry_run": True})
    suite.expect("gh_canvas_cleanup dry run", canvas_cleanup, lambda r: r.get("success") is True)

    delete_panel = await tool("gh_delete", {"guids": [panel_guid]})
    suite.expect("gh_delete", delete_panel, lambda r: r.get("deleted", 0) >= 1 or r.get("removed", 0) >= 1)

    session_current = await tool("gh_session_current", {})
    suite.expect("gh_session_current", session_current, lambda r: r.get("status") == "active")

    session_history = await tool("gh_session_history", {"limit": 20})
    suite.expect("gh_session_history", session_history, lambda r: len(r.get("entries", [])) > 0)

    session_note = await tool("gh_session_note", {"note": "Operational suite note"})
    suite.expect("gh_session_note", session_note, lambda r: r.get("success") is True)

    clear_doc = await tool("gh_clear", {})
    suite.expect("gh_clear", clear_doc, lambda r: r.get("cleared") is True)

    # Cluster scenario
    cluster_doc = await tool("gh_document_new", {})
    suite.expect("gh_document_new cluster scenario", cluster_doc, lambda r: r.get("created") is True)
    cluster_slider_a = await tool("gh_create_slider", {"nickname": "ClusterA", "x": 20, "y": 80, "value": 1})
    cluster_slider_b = await tool("gh_create_slider", {"nickname": "ClusterB", "x": 20, "y": 180, "value": 2})
    cluster_add = await tool("gh_create_component", {"guid": addition["guid"], "x": 240, "y": 120})
    cluster_result = await tool("gh_cluster", {
        "guids": [get_guid(cluster_slider_a), get_guid(cluster_slider_b), get_guid(cluster_add)],
        "nickname": "SuiteCluster",
        "x": 420,
        "y": 160,
    })
    suite.expect("gh_cluster", cluster_result, lambda r: r.get("created") is True or r.get("guid") is not None)

    # Document open / learn-directory scenario
    document_open = await tool("gh_document_open", {"path": str(EXAMPLE_GH)})
    suite.expect("gh_document_open", document_open, lambda r: r.get("opened") is True or r.get("path") == str(EXAMPLE_GH))

    query_open = await tool("gh_query")
    suite.expect("gh_query after open", query_open, lambda r: r.get("objectCount", 0) > 0)

    learn_directory = await tool("gh_learn_directory", {
        "directory": str(EXAMPLE_GH.parent),
        "recursive": False,
        "limit": 1,
    })
    suite.expect("gh_learn_directory", learn_directory, lambda r: r.get("processed", 0) >= 1)

    session_end = await tool("gh_session_end", {})
    suite.expect("gh_session_end", session_end, lambda r: ("ended" in r) or (r.get("status") == "no_active_session"))

    return suite.summarize()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
