"""Live-Rhino coverage for the unified `gh_create_script` MCP tool (PR-2).

Parallel to the existing alias live coverage — exercises the unified tool
end-to-end through the MCP dispatcher against a running Rhino + Grasshopper.
The aliases (`gh_create_python_script` / `gh_create_csharp_script`) delegate
to the same `_execute_gh_create_script` helper, so these tests also serve as
a regression floor for the shared implementation.

See rook_docs/2026-04-21-gh-script-component-routing-design-pass.md §PR-2.

Run (from repo root, with Rhino open and Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_gh_create_script_live.py
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _get_guid(result: Any) -> str | None:
    """Extract a component GUID from a gh_create_script response shape."""
    if not isinstance(result, dict):
        return None
    for key in ("component_guid", "guid", "Guid"):
        val = result.get(key)
        if isinstance(val, str) and val:
            return val
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("component_guid", "guid", "Guid"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return None


async def test_gh_create_script_python_end_to_end():
    """Unified tool with language='python' creates a real Python 3 Script
    component on the canvas via the same pipeline as the alias.
    Verifies the happy path: fixed GUID → pin config → script injection →
    compilation-error check, all in one transaction.
    """
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_create_script",
        {
            "language": "python",
            "code": "Result = X * 2",
            "pins_in": [{"name": "X", "type": "float"}],
            "pins_out": [{"name": "Result", "type": "float"}],
            "name": "UnifiedPyLive",
            "x": 300,
            "y": 300,
        },
    )
    assert not _is_error(result), f"gh_create_script(language=python) failed: {result!r}"

    guid = _get_guid(result)
    assert isinstance(guid, str) and guid, f"no component_guid in response: {result!r}"

    data = result.get("data") if isinstance(result, dict) else None
    assert isinstance(data, dict)
    assert data.get("name") == "UnifiedPyLive"
    assert data.get("pins_in") and data["pins_in"][0]["name"] == "X"
    assert data.get("pins_out") and data["pins_out"][0]["name"] == "Result"
    # Preamble is prepended — code_length must exceed the bare user code.
    assert data.get("code_length", 0) > len("Result = X * 2")


async def test_gh_create_script_csharp_end_to_end():
    """Unified tool with language='csharp' creates a real RhinoCode C# Script
    component on the canvas. Verifies the Script_Instance wrapper landed
    (code_length grows well beyond the user body) and the component reports
    clean compilation for a trivial valid RunScript body.
    """
    from rook.server import _mcp_tool_executor

    user_code = "A = Convert.ToDouble(R) * 2.0;"
    result = await _mcp_tool_executor(
        "gh_create_script",
        {
            "language": "csharp",
            "code": user_code,
            "pins_in": [{"name": "R", "type": "double"}],
            "pins_out": [{"name": "A", "type": "double"}],
            "name": "UnifiedCSLive",
            "x": 400,
            "y": 300,
        },
    )
    assert not _is_error(result), f"gh_create_script(language=csharp) failed: {result!r}"

    guid = _get_guid(result)
    assert isinstance(guid, str) and guid, f"no component_guid in response: {result!r}"

    data = result.get("data") if isinstance(result, dict) else None
    assert isinstance(data, dict)
    assert data.get("name") == "UnifiedCSLive"
    # Wrapper adds ~20 lines of boilerplate — code_length must be substantially
    # larger than the user's body.
    assert data.get("code_length", 0) > len(user_code) + 100


async def test_gh_create_script_python_point_list_bakes_as_geometry():
    """A declared Point3d list output must be usable by downstream GH/Rhino
    geometry consumers. Baking is the anchor because it fails for dicts,
    strings, wrapper/debug objects, or other non-geometry blobs.
    """
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_create_script",
        {
            "language": "python",
            "code": (
                "import Rhino.Geometry as rg\n"
                "Points = [rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), "
                "rg.Point3d(2, 0, 0)]"
            ),
            "pins_in": [],
            "pins_out": [{"name": "Points", "type": "Point3d", "access": "list"}],
            "name": "UsablePointListPyLive",
            "x": 300,
            "y": 420,
        },
    )
    assert not _is_error(result), f"gh_create_script Point3d list failed: {result!r}"

    guid = _get_guid(result)
    assert isinstance(guid, str) and guid, f"no component_guid in response: {result!r}"

    bake = await _mcp_tool_executor(
        "gh_bake_output",
        {
            "targets": [
                {
                    "instanceGuid": guid,
                    "outputIndex": 1,
                    "outputName": "Points",
                }
            ],
            "layerName": "RookTest_GhPythonPointList",
            "createSublayers": True,
            "clearExisting": True,
        },
    )
    assert not _is_error(bake), f"gh_bake_output failed for Point3d list: {bake!r}"

    data = bake.get("data") if isinstance(bake, dict) and isinstance(bake.get("data"), dict) else bake
    assert isinstance(data, dict), f"unexpected bake response: {bake!r}"
    assert data.get("totalBaked") == 3

    per_target = data.get("perTarget")
    assert isinstance(per_target, list) and len(per_target) == 1
    target = per_target[0]
    assert target.get("bakedCount") == 3
    assert len(target.get("bakedIds", [])) == 3

    geometry_types = target.get("geometryTypes")
    assert isinstance(geometry_types, list)
    assert "Point3d" in geometry_types


async def test_gh_create_script_omitted_language_fails_live():
    """End-to-end MCP dispatch for a caller that omits `language`. The
    handler-level redundant check returns a structured error naming both
    valid choices — confirms the user-visible rejection shape matches the
    mock-level contract tests when invoked through the full dispatcher
    with a running Rhino. No HTTP calls to Rhino are made on rejection.
    """
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_create_script",
        {
            "code": "Result = X",
            "pins_in": [{"name": "X", "type": "float"}],
            "pins_out": [{"name": "Result", "type": "float"}],
        },
    )
    assert _is_error(result), (
        f"gh_create_script should reject when language omitted; got {result!r}"
    )
    data = result.get("data") if isinstance(result, dict) else None
    # The rejection message must name both valid choices so the caller
    # can self-recover without needing to read the schema.
    assert isinstance(data, str)
    assert "python" in data and "csharp" in data, (
        f"rejection message should name both valid languages; got {data!r}"
    )
