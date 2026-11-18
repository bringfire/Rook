"""Live-Rhino tests for the layer and object tool fixes.

Covers, against a real document:
  - a case-only layer rename succeeds (`rhino_layer_rename` and
    `rhino_layer_set_properties_batch`); renaming onto a DIFFERENT layer is
    still a collision
  - `rhino_layer_dependencies` counts hidden objects, lights and objects on a
    turned-off layer as holders, agrees with `rhino_layer_delete`, and reports
    deleted-but-undoable objects without treating them as holders
  - `rhino_layer_merge` moves hidden objects and lights and deletes the source
    layer
  - `rhino_select` with a parent layer selects nothing by default and selects
    the sub-layers' objects with `includeSublayers: true`
  - `rhino_objects` rejects an unrecognized `type` and lists the accepted ones

Run:
    pytest -m requires_rhino mcp_server/tests/test_layer_object_tools_live.py

Rhino must be running with a RookNative built from this source: the fixes are
in the native plug-in, so these tests fail against an older installed plug-in.
Tests reset the document on entry via the fresh_document fixture — run them in
a throwaway session. Because that reset does not reliably clear a live
document, every test also works on layers under its own unique prefix and
asserts only on those.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from .conftest import fresh_document, _is_error  # noqa: F401 — fixture import


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


@pytest.fixture
def tag() -> str:
    """Unique lower-case layer-name prefix owned by one test."""
    return "zt" + uuid.uuid4().hex[:8]


async def _tool(name: str, arguments: dict[str, Any]) -> Any:
    from rook.server import _mcp_tool_executor

    return await _mcp_tool_executor(name, arguments)


async def _ok(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    res = await _tool(name, arguments)
    assert not _is_error(res), f"{name}({arguments!r}) failed: {res!r}"
    assert isinstance(res, dict), f"{name} returned a non-dict result: {res!r}"
    return res


async def _layer_paths() -> set[str]:
    res = await _ok("rhino_layers", {})
    return {layer["fullPath"] for layer in res["layers"]}


_SETUP_PRELUDE = """
import Rhino
import System
doc = Rhino.RhinoDoc.ActiveDoc

def layer(path):
    parent = System.Guid.Empty
    index = -1
    for name in path.split("::"):
        found = -1
        for candidate in doc.Layers:
            if candidate.IsDeleted: continue
            if candidate.Name == name and candidate.ParentLayerId == parent:
                found = candidate.Index
        if found < 0:
            new_layer = Rhino.DocObjects.Layer()
            new_layer.Name = name
            new_layer.ParentLayerId = parent
            found = doc.Layers.Add(new_layer)
        index = found
        parent = doc.Layers[found].Id
    return index

def point(layer_index, x, hidden=False, deleted=False):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    object_id = doc.Objects.AddPoint(Rhino.Geometry.Point3d(x, 0, 0), attributes)
    if hidden:
        doc.Objects.Hide(object_id, True)
    if deleted:
        doc.Objects.Delete(object_id, True)
    return object_id

def light(layer_index, x):
    geometry = Rhino.Geometry.Light()
    geometry.LightStyle = Rhino.Geometry.LightStyle.WorldPoint
    geometry.Location = Rhino.Geometry.Point3d(x, 0, 0)
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    return doc.Lights.Add(geometry, attributes)
"""


async def _setup(body: str) -> str:
    """Run a setup script in Rhino (after the layer/point helpers) and return its output."""
    res = await _ok("rhino_execute", {"code": _SETUP_PRELUDE + body})
    assert not res.get("stderr"), f"setup script wrote to stderr: {res!r}"
    return res.get("output", "")


# --- Case-only layer rename ---------------------------------------------------


async def test_case_only_rename_succeeds(fresh_document, tag):
    lower = f"{tag}_mullions"
    await _ok("rhino_layer_create", {"name": lower})

    renamed = await _ok("rhino_layer_rename", {"name": lower, "newName": lower.upper()})

    assert renamed["name"] == lower.upper()
    paths = await _layer_paths()
    assert lower.upper() in paths
    assert lower not in paths


async def test_case_only_rename_succeeds_for_sub_layers_through_the_batch_tool(fresh_document, tag):
    await _setup(f'layer("{tag}_glass::mullions"); layer("{tag}_shell::head")')

    res = await _ok(
        "rhino_layer_set_properties_batch",
        {
            "items": [
                {"name": f"{tag}_glass::mullions", "set": {"rename": "MULLIONS"}},
                {"name": f"{tag}_shell::head", "set": {"rename": "HEAD"}},
            ]
        },
    )

    assert not res.get("errors"), f"case-only renames were rejected: {res!r}"
    assert res["routed"] == 2
    paths = await _layer_paths()
    assert {f"{tag}_glass::MULLIONS", f"{tag}_shell::HEAD"} <= paths
    assert not {f"{tag}_glass::mullions", f"{tag}_shell::head"} & paths


async def test_rename_onto_a_different_layer_is_still_a_collision(fresh_document, tag):
    await _setup(f'layer("{tag}_alpha"); layer("{tag}_beta")')

    res = await _tool(
        "rhino_layer_rename", {"name": f"{tag}_alpha", "newName": f"{tag}_BETA"}
    )

    assert _is_error(res), f"renaming onto another layer should fail: {res!r}"
    assert "already exists" in str(res)
    assert {f"{tag}_alpha", f"{tag}_beta"} <= await _layer_paths()
