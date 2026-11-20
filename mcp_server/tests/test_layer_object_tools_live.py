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
  - `rhino_objects` leaves hidden objects, lights and objects on a turned-off
    layer out by default, reports them in `unlistedCount` with the reason for
    each in `unlistedByReason`, and lists them with `includeUnlisted: true`;
    `includeHidden` on this tool is rejected with the right name; `objectCount`
    in `rhino_layers` and `rhino_document` counts them
  - every listed object carries `mode`, `layerVisible` and `layerLocked`, and
    those fields predict what `rhino_delete` will refuse; `rhino_geometry` and
    `rhino_block_objects_detailed` report the same three fields
  - `rhino_layer_move_objects` moves hidden objects and lights, and everything
    on a turned-off layer
  - `rhino_select` and `rhino_select_by_type` reject an unrecognized `type`
    without touching the selection, and accept the type names `rhino_objects`
    prints
  - detail views are listed as type `Detail`
  - `rhino_delete` refuses a hidden object with a reason, deletes it with
    `includeHidden: true`, and never deletes a locked one (locked itself, on
    a locked layer, or on a layer locked through its parent); the delete is
    one undo step that brings the object back still hidden; an object on a
    turned-off layer is not "hidden" and is deleted by id as before
  - the default `rhino_objects` listing keeps Rhino's order through
    pagination, and `unlistedCount` respects the name and type filters

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

def point(layer_index, x, hidden=False, deleted=False, name=None, locked=False):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    if name:
        attributes.Name = name
    object_id = doc.Objects.AddPoint(Rhino.Geometry.Point3d(x, 0, 0), attributes)
    if hidden:
        doc.Objects.Hide(object_id, True)
    if locked:
        doc.Objects.Lock(object_id, True)
    if deleted:
        doc.Objects.Delete(object_id, True)
    return object_id

def light(layer_index, x):
    geometry = Rhino.Geometry.Light()
    geometry.LightStyle = Rhino.Geometry.LightStyle.WorldPoint
    geometry.Location = Rhino.Geometry.Point3d(x, 0, 0)
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    return doc.Lights[doc.Lights.Add(geometry, attributes)].Id

def dot(layer_index, x, name=None, hidden=False):
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    if name:
        attributes.Name = name
    object_id = doc.Objects.AddTextDot("dot", Rhino.Geometry.Point3d(x, 0, 0), attributes)
    if hidden:
        doc.Objects.Hide(object_id, True)
    return object_id

def default_order(layer_index):
    # The ids Rhino's default object iterator returns for one layer, in order.
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.NormalObjects = True
    settings.LockedObjects = True
    settings.HiddenObjects = False
    settings.DeletedObjects = False
    settings.IncludeLights = False
    settings.LayerIndexFilter = layer_index
    return [str(o.Id) for o in doc.Objects.GetObjectList(settings)]

def mode(object_id):
    found = doc.Objects.FindId(System.Guid(object_id))
    return str(found.Attributes.Mode) if found is not None else "missing"

def block(name, layer_index):
    # A block definition with one point on the given layer. No instance is
    # inserted: the definition's member is all the tests look at.
    attributes = Rhino.DocObjects.ObjectAttributes()
    attributes.LayerIndex = layer_index
    return doc.InstanceDefinitions.Add(
        name,
        "",
        Rhino.Geometry.Point3d.Origin,
        [Rhino.Geometry.Point(Rhino.Geometry.Point3d(0, 0, 0))],
        [attributes],
    )

def detail(page_name):
    page = doc.Views.AddPageView(page_name, 200.0, 100.0)
    view = page.AddDetailView(
        page_name,
        Rhino.Geometry.Point2d(10, 10),
        Rhino.Geometry.Point2d(90, 90),
        Rhino.Display.DefinedViewportProjection.Top,
    )
    return view.Id
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


# --- What holds a layer: dependencies, delete, merge --------------------------


async def test_hidden_object_holds_a_layer_and_dependencies_says_so(fresh_document, tag):
    held = f"{tag}_held"
    hidden_id = (await _setup(f'print(point(layer("{held}"), 0, hidden=True))')).strip()

    deps = await _ok("rhino_layer_dependencies", {"name": held})

    assert deps["directObjects"] == 1
    assert deps["hiddenObjects"] == 1
    assert deps["hiddenObjectTypes"] == {"Point": 1}
    assert deps["hiddenObjectIds"] == [hidden_id]
    assert deps["canDelete"] is False
    assert deps["blockers"], "a held layer must list what holds it"

    res = await _tool("rhino_layer_delete", {"name": held})
    assert _is_error(res), f"delete must agree with canDelete=false: {res!r}"
    assert "hidden" in str(res)
    assert held in await _layer_paths()


async def test_objects_on_a_turned_off_layer_hold_it(fresh_document, tag):
    switched_off = f"{tag}_switched_off"
    await _setup(f'point(layer("{switched_off}"), 0)')
    await _ok("rhino_layer_visibility", {"name": switched_off, "visible": False})

    deps = await _ok("rhino_layer_dependencies", {"name": switched_off})

    assert deps["directObjects"] == 1
    assert deps["hiddenObjects"] == 0
    assert deps["layerVisible"] is False
    assert deps["canDelete"] is False


async def test_light_holds_a_layer_and_merge_moves_it(fresh_document, tag):
    source, target = f"{tag}_lit", f"{tag}_lights"
    await _setup(f'light(layer("{source}"), 0); layer("{target}")')

    deps = await _ok("rhino_layer_dependencies", {"name": source})
    assert deps["directObjects"] == 1
    assert deps["lightObjects"] == 1
    assert deps["canDelete"] is False

    res = await _tool("rhino_layer_delete", {"name": source})
    assert _is_error(res), f"delete must agree with canDelete=false: {res!r}"
    assert "1 light" in str(res)

    merged = await _ok("rhino_layer_merge", {"source": source, "target": target})
    assert merged["objectsMoved"] == 1
    assert merged["sourceDeleted"] is True
    assert source not in await _layer_paths()


async def test_deleted_objects_in_undo_are_reported_but_do_not_hold_a_layer(fresh_document, tag):
    emptied = f"{tag}_emptied"
    await _setup(f'point(layer("{emptied}"), 0, deleted=True)')

    deps = await _ok("rhino_layer_dependencies", {"name": emptied})

    assert deps["directObjects"] == 0
    assert deps["deletedObjectsInUndo"] == 1
    assert deps["canDelete"] is True
    assert deps["blockers"] == []

    await _ok("rhino_layer_delete", {"name": emptied})
    assert emptied not in await _layer_paths()


async def test_merge_moves_hidden_objects_and_deletes_the_source_layer(fresh_document, tag):
    source, target = f"{tag}_layer 01", f"{tag}_detail tag"
    hidden_id = (
        await _setup(
            f'source = layer("{source}"); layer("{target}")\n'
            "point(source, 0)\n"
            "print(point(source, 1, hidden=True))"
        )
    ).strip()

    merged = await _ok("rhino_layer_merge", {"source": source, "target": target})

    assert merged["objectsMoved"] == 2
    assert merged["hiddenObjectsMoved"] == 1
    assert merged["sourceDeleted"] is True
    assert source not in await _layer_paths()

    after = await _ok("rhino_layer_dependencies", {"name": target})
    assert after["directObjects"] == 2
    # The hidden object moved with the rest and is still hidden.
    assert after["hiddenObjectIds"] == [hidden_id]


# --- rhino_select: sub-layers are opt-in --------------------------------------


async def test_select_parent_layer_includes_sub_layers_only_when_asked(fresh_document, tag):
    parent = f"{tag}_shakes"
    await _setup(
        f'layer("{parent}")\n'
        f'point(layer("{parent}::0"), 0); point(layer("{parent}::0"), 1)\n'
        f'point(layer("{parent}::head::trim"), 2)\n'
        f'point(layer("{tag}_other"), 3)'
    )

    default = await _ok("rhino_select", {"layer": parent})
    assert default["selectedCount"] == 0

    widened = await _ok("rhino_select", {"layer": parent, "includeSublayers": True})
    assert widened["selectedCount"] == 3
    # the parent, ::0, ::head, ::head::trim
    assert widened["layersMatched"] == 4

    explicit_off = await _ok(
        "rhino_select", {"layer": f"{parent}::0", "includeSublayers": False}
    )
    assert explicit_off["selectedCount"] == 2

    await _ok("rhino_select", {"none": True})


async def test_select_include_sublayers_without_a_layer_is_rejected(fresh_document):
    res = await _tool("rhino_select", {"includeSublayers": True, "clear": False})

    assert _is_error(res), f"includeSublayers without layer should fail: {res!r}"
    assert "requires 'layer'" in str(res)


# --- rhino_objects: an unrecognized type is an error --------------------------


async def test_objects_rejects_an_unrecognized_type_and_lists_the_accepted_ones(fresh_document, tag):
    await _setup(f'point(layer("{tag}_pts"), 0); point(layer("{tag}_pts"), 1)')

    res = await _tool("rhino_objects", {"type": "Unknown", "limit": 1})

    assert _is_error(res), f"an unknown type must not match every object: {res!r}"
    for accepted in ("Point", "Curve", "Brep", "ClipPlane"):
        assert accepted in str(res)


async def test_objects_type_filter_is_still_case_insensitive(fresh_document, tag):
    await _setup(f'point(layer("{tag}_pts"), 0); point(layer("{tag}_pts"), 1)')

    res = await _ok("rhino_objects", {"type": "point", "layer": f"{tag}_pts"})

    assert res["totalCount"] == 2


# --- Counts and listings: hidden objects, off layers, lights ------------------


def _ids(objects: list[dict[str, Any]]) -> list[str]:
    return [obj["id"].lower() for obj in objects]


async def _layer_row(path: str) -> dict[str, Any]:
    res = await _ok("rhino_layers", {})
    return next(layer for layer in res["layers"] if layer["fullPath"] == path)


async def test_objects_lists_hidden_objects_and_lights_only_when_asked(fresh_document, tag):
    mixed = f"{tag}_mixed"
    out = await _setup(
        f'index = layer("{mixed}")\n'
        "print(point(index, 0))\n"
        "print(point(index, 1, hidden=True))\n"
        "print(light(index, 2))"
    )
    normal_id, hidden_id, light_id = (line.strip().lower() for line in out.split())

    default = await _ok("rhino_objects", {"layer": mixed})
    assert default["totalCount"] == 1
    assert default["unlistedCount"] == 2
    assert default["unlistedByReason"] == {"hidden": 1, "layerOff": 0, "light": 1}
    assert "includeUnlisted" in default["unlistedHint"]
    assert "1 hidden" in default["unlistedHint"]
    assert "1 light" in default["unlistedHint"]
    assert hidden_id not in _ids(default["objects"])

    everything = await _ok("rhino_objects", {"layer": mixed, "includeUnlisted": True})
    assert everything["totalCount"] == 3
    assert everything["unlistedCount"] == 0
    assert everything["unlistedByReason"] == {"hidden": 0, "layerOff": 0, "light": 0}
    by_id = {obj["id"].lower(): obj for obj in everything["objects"]}
    assert by_id[hidden_id]["visible"] is False
    assert by_id[light_id]["type"] == "Light"
    # Each object says why it is, or is not, in the default listing.
    assert by_id[normal_id]["mode"] == "normal"
    assert by_id[hidden_id]["mode"] == "hidden"
    assert by_id[light_id]["mode"] == "normal"
    assert all(obj["layerVisible"] is True for obj in everything["objects"])
    assert all(obj["layerLocked"] is False for obj in everything["objects"])

    lights = await _ok(
        "rhino_objects", {"layer": mixed, "type": "Light", "includeUnlisted": True}
    )
    assert _ids(lights["objects"]) == [light_id]

    # The layer's count agrees with the wide listing, not the default one.
    row = await _layer_row(mixed)
    assert row["objectCount"] == 3
    assert row["unlistedObjectCount"] == 2


async def test_turned_off_layer_keeps_its_object_count(fresh_document, tag):
    switched_off = f"{tag}_weathervane"
    await _setup(f'index = layer("{switched_off}")\npoint(index, 0); point(index, 1)')
    assert (await _layer_row(switched_off))["objectCount"] == 2

    await _ok("rhino_layer_visibility", {"name": switched_off, "visible": False})

    row = await _layer_row(switched_off)
    assert row["objectCount"] == 2, "turning a layer off must not empty its count"
    assert row["unlistedObjectCount"] == 2

    default = await _ok("rhino_objects", {"layer": switched_off})
    assert default["totalCount"] == 0
    assert default["unlistedCount"] == 2
    assert default["unlistedByReason"] == {"hidden": 0, "layerOff": 2, "light": 0}
    assert "on a turned-off layer" in default["unlistedHint"]

    everything = await _ok("rhino_objects", {"layer": switched_off, "includeUnlisted": True})
    assert everything["totalCount"] == 2
    assert all(obj["visible"] is False for obj in everything["objects"])
    # Not visible because of the layer, not because the objects are hidden.
    assert all(obj["mode"] == "normal" for obj in everything["objects"])
    assert all(obj["layerVisible"] is False for obj in everything["objects"])


async def test_document_object_count_includes_hidden_objects_and_lights(fresh_document, tag):
    before = await _ok("rhino_document", {})

    await _setup(
        f'index = layer("{tag}_doc")\n'
        "point(index, 0)\n"
        "point(index, 1, hidden=True)\n"
        "light(index, 2)"
    )

    after = await _ok("rhino_document", {})
    assert after["objectCount"] - before["objectCount"] == 3
    assert after["unlistedObjectCount"] - before["unlistedObjectCount"] == 2


async def test_default_listing_keeps_rhino_order_through_pagination(fresh_document, tag):
    ordered = f"{tag}_ordered"
    out = await _setup(
        f'index = layer("{ordered}")\n'
        "for x in range(5): point(index, x)\n"
        "point(index, 9, hidden=True)\n"
        'print(" ".join(default_order(index)))'
    )
    expected = [object_id.lower() for object_id in out.split()]
    assert len(expected) == 5

    listed = await _ok("rhino_objects", {"layer": ordered})
    assert _ids(listed["objects"]) == expected

    page = await _ok("rhino_objects", {"layer": ordered, "limit": 2, "offset": 1})
    assert _ids(page["objects"]) == expected[1:3]
    assert page["totalCount"] == 5
    assert page["unlistedCount"] == 1


async def test_unlisted_count_respects_the_name_and_type_filters(fresh_document, tag):
    mixed = f"{tag}_filtered"
    await _setup(
        f'index = layer("{mixed}")\n'
        'point(index, 0, name="keep"); point(index, 1, name="keep")\n'
        'point(index, 2, name="keep", hidden=True)\n'
        # Hidden, but filtered out by name or by type: must not be counted.
        'point(index, 3, name="other", hidden=True)\n'
        "point(index, 4, hidden=True)\n"
        "light(index, 5)\n"
        "dot(index, 6)\n"
        # Named like the points but not points: a type filter that was dropped
        # whenever a name filter is present would count these.
        'dot(index, 7, name="keep")\n'
        'dot(index, 8, name="keep", hidden=True)'
    )

    # The page size must not change either count.
    for limit in (1, 100):
        res = await _ok(
            "rhino_objects",
            {"layer": mixed, "name": "keep", "type": "Point", "limit": limit},
        )
        assert res["totalCount"] == 2
        assert res["unlistedCount"] == 1
        assert res["count"] == min(limit, 2)

    by_name = await _ok("rhino_objects", {"layer": mixed, "name": "keep"})
    assert by_name["totalCount"] == 3  # two points and one text dot
    assert by_name["unlistedCount"] == 2  # the hidden point and the hidden text dot

    by_type = await _ok("rhino_objects", {"layer": mixed, "type": "Point"})
    assert by_type["totalCount"] == 2
    assert by_type["unlistedCount"] == 3

    unfiltered = await _ok("rhino_objects", {"layer": mixed})
    assert unfiltered["totalCount"] == 4  # two points and two text dots
    assert unfiltered["unlistedCount"] == 5  # three hidden points, a hidden dot, the light
    assert unfiltered["unlistedByReason"] == {"hidden": 4, "layerOff": 0, "light": 1}


async def test_unlisted_reasons_when_more_than_one_applies(fresh_document, tag):
    # On a turned-off layer: a normal object, a locked one and a hidden one.
    # Each is counted once. Hidden mode wins over the layer being off, because
    # turning the layer on would not bring that object back; a locked object
    # is unlisted only because of the layer.
    overlap = f"{tag}_overlap"
    out = await _setup(
        f'index = layer("{overlap}")\n'
        "print(point(index, 0))\n"
        "print(point(index, 1, locked=True))\n"
        "print(point(index, 2, hidden=True))"
    )
    normal_id, locked_id, hidden_id = (line.strip().lower() for line in out.split())
    await _ok("rhino_layer_visibility", {"name": overlap, "visible": False})

    default = await _ok("rhino_objects", {"layer": overlap})
    assert default["totalCount"] == 0
    assert default["unlistedCount"] == 3
    assert default["unlistedByReason"] == {"hidden": 1, "layerOff": 2, "light": 0}

    everything = await _ok("rhino_objects", {"layer": overlap, "includeUnlisted": True})
    by_id = {obj["id"].lower(): obj for obj in everything["objects"]}
    assert {key: by_id[key]["mode"] for key in by_id} == {
        normal_id: "normal",
        locked_id: "locked",
        hidden_id: "hidden",
    }
    assert all(obj["layerVisible"] is False for obj in everything["objects"])
    assert all(obj["visible"] is False for obj in everything["objects"])


async def test_a_created_object_carries_the_state_fields(fresh_document, tag):
    target = f"{tag}_created"
    await _ok("rhino_layer_create", {"name": target})

    created = await _ok(
        "rhino_create", {"type": "POINT", "point": [0, 0, 0], "layer": target}
    )

    # The create response has the same state fields a listing gives.
    assert created["mode"] == "normal"
    assert created["layerVisible"] is True
    assert created["layerLocked"] is False
    listed = await _ok("rhino_objects", {"layer": target})
    assert [(obj["id"], obj["mode"]) for obj in listed["objects"]] == [(created["id"], "normal")]


async def test_geometry_detail_carries_the_state_fields(fresh_document, tag):
    held = f"{tag}_geometry"
    hidden_id = (
        await _setup(f'print(point(layer("{held}"), 0, hidden=True))')
    ).strip().lower()

    detail_before = await _ok("rhino_geometry", {"id": hidden_id})
    assert detail_before["mode"] == "hidden"
    assert detail_before["layerVisible"] is True
    assert detail_before["layerLocked"] is False
    assert detail_before["visible"] is False

    await _ok("rhino_layer_lock", {"name": held, "locked": True})
    await _ok("rhino_layer_visibility", {"name": held, "visible": False})

    detail_after = await _ok("rhino_geometry", {"id": hidden_id})
    assert detail_after["mode"] == "hidden"
    assert detail_after["layerVisible"] is False
    assert detail_after["layerLocked"] is True


async def test_block_member_records_carry_the_state_fields(fresh_document, tag):
    held, name = f"{tag}_block_layer", f"{tag}_block"
    index = (await _setup(f'print(block("{name}", layer("{held}")))')).strip()
    assert int(index) >= 0, "the setup script did not create the block definition"

    before = await _ok("rhino_block_objects_detailed", {"name": name})
    assert before["objectCount"] == 1
    member = before["objects"][0]
    # A definition's member is not a model object.
    assert member["mode"] == "instanceDefinition"
    assert member["layerVisible"] is True
    assert member["layerLocked"] is False

    await _ok("rhino_layer_visibility", {"name": held, "visible": False})

    after = await _ok("rhino_block_objects_detailed", {"name": name})
    assert after["objects"][0]["mode"] == "instanceDefinition"
    assert after["objects"][0]["layerVisible"] is False


async def test_objects_rejects_a_malformed_include_unlisted(fresh_document):
    res = await _tool("rhino_objects", {"includeUnlisted": "yes", "limit": 1})

    assert _is_error(res), f"a malformed includeUnlisted must not read as false: {res!r}"
    assert "includeUnlisted" in str(res)


async def test_objects_rejects_include_hidden_and_names_the_right_flag(fresh_document):
    # rhino_delete has includeHidden, so it is the name a caller will guess.
    res = await _tool("rhino_objects", {"includeHidden": True, "limit": 1})

    assert _is_error(res), f"a guessed flag must not be answered with the default listing: {res!r}"
    assert "includeUnlisted" in str(res)


# --- rhino_layer_move_objects: "all objects" means all ------------------------


async def test_move_objects_moves_hidden_objects_and_lights(fresh_document, tag):
    source, target = f"{tag}_from", f"{tag}_to"
    hidden_id = (
        await _setup(
            f'source = layer("{source}"); layer("{target}")\n'
            "point(source, 0)\n"
            "light(source, 2)\n"
            "print(point(source, 1, hidden=True))"
        )
    ).strip().lower()

    moved = await _ok("rhino_layer_move_objects", {"source": source, "target": target})

    assert moved["objectsMoved"] == 3
    assert moved["hiddenObjectsMoved"] == 1
    # Unlike merge, the source layer stays, now with nothing on it.
    assert source in await _layer_paths()
    emptied = await _ok("rhino_layer_dependencies", {"name": source})
    assert emptied["directObjects"] == 0
    after = await _ok("rhino_layer_dependencies", {"name": target})
    assert after["directObjects"] == 3
    # The hidden object moved with the rest and is still hidden.
    assert [hidden.lower() for hidden in after["hiddenObjectIds"]] == [hidden_id]


async def test_move_objects_moves_everything_off_a_turned_off_layer(fresh_document, tag):
    source, target = f"{tag}_off", f"{tag}_on"
    await _setup(f'source = layer("{source}"); layer("{target}")\npoint(source, 0); point(source, 1)')
    await _ok("rhino_layer_visibility", {"name": source, "visible": False})

    moved = await _ok("rhino_layer_move_objects", {"source": source, "target": target})

    assert moved["objectsMoved"] == 2
    assert (await _layer_row(target))["objectCount"] == 2
    assert (await _layer_row(source))["objectCount"] == 0


# --- rhino_select / rhino_select_by_type: an unrecognized type is an error ----


@pytest.mark.parametrize("tool", ["rhino_select_by_type", "rhino_select"])
async def test_select_rejects_an_unrecognized_type_and_keeps_the_selection(fresh_document, tag, tool):
    kept_id = (
        await _setup(f'index = layer("{tag}_sel")\nprint(point(index, 0)); point(index, 1)')
    ).strip().lower()
    await _ok("rhino_select", {"ids": [kept_id]})

    res = await _tool(tool, {"type": "NoSuchType"})

    assert _is_error(res), f"an unknown type must not select every object: {res!r}"
    for accepted in ("brep", "curve", "instancereference"):
        assert accepted in str(res)
    # Rejected before anything ran: the earlier selection was not cleared.
    selection = await _ok("rhino_selection", {})
    assert _ids(selection["objects"]) == [kept_id]

    await _ok("rhino_select", {"none": True})


@pytest.mark.parametrize("bad_type", [123, None, ["Point"]])
async def test_select_rejects_a_type_that_is_not_a_string(fresh_document, tag, bad_type):
    kept_id = (
        await _setup(f'index = layer("{tag}_sel_num")\nprint(point(index, 0)); point(index, 1)')
    ).strip().lower()
    await _ok("rhino_select", {"ids": [kept_id]})

    res = await _tool("rhino_select", {"type": bad_type})

    assert _is_error(res), f"a non-string type must not be ignored: {res!r}"
    assert "'type' must be a string" in str(res)
    selection = await _ok("rhino_selection", {})
    assert _ids(selection["objects"]) == [kept_id]

    await _ok("rhino_select", {"none": True})


async def test_select_by_type_accepts_a_type_name_read_from_rhino_objects(fresh_document, tag):
    dots = f"{tag}_dots"
    dot_id = (
        await _setup(f'index = layer("{dots}")\nprint(dot(index, 0)); point(index, 1)')
    ).strip().lower()
    listed = await _ok("rhino_objects", {"layer": dots, "type": "TextDot"})
    assert _ids(listed["objects"]) == [dot_id]

    await _ok("rhino_select_by_type", {"type": listed["objects"][0]["type"]})

    selection = await _ok("rhino_selection", {})
    assert dot_id in _ids(selection["objects"])
    assert {obj["type"] for obj in selection["objects"]} == {"TextDot"}

    await _ok("rhino_select", {"none": True})


# --- Detail views have a type name --------------------------------------------


async def test_detail_views_are_listed_as_detail_and_can_be_filtered(fresh_document, tag):
    detail_id = (await _setup(f'print(detail("{tag}_page"))')).strip().lower()

    details = await _ok("rhino_objects", {"type": "Detail", "limit": 500})

    assert detail_id in _ids(details["objects"])
    assert {obj["type"] for obj in details["objects"]} == {"Detail"}


# --- rhino_delete: hidden objects are opt-in, and failures say why ------------


async def test_delete_refuses_a_hidden_object_until_asked(fresh_document, tag):
    held = f"{tag}_hidden"
    hidden_id = (
        await _setup(f'print(point(layer("{held}"), 0, hidden=True))')
    ).strip().lower()

    res = await _tool("rhino_delete", {"ids": [hidden_id]})

    assert _is_error(res), f"a hidden object must not be deleted by default: {res!r}"
    assert "hidden" in str(res)
    assert "includeHidden" in str(res)
    assert (await _ok("rhino_layer_dependencies", {"name": held}))["directObjects"] == 1

    deleted = await _ok("rhino_delete", {"ids": [hidden_id], "includeHidden": True})

    assert deleted["deletedCount"] == 1
    assert deleted["hiddenDeletedCount"] == 1
    assert (await _ok("rhino_layer_dependencies", {"name": held}))["directObjects"] == 0


async def test_delete_reports_a_reason_for_each_id_it_leaves(fresh_document, tag):
    out = await _setup(
        f'index = layer("{tag}_partial")\n'
        "print(point(index, 0))\n"
        "print(point(index, 1, hidden=True))"
    )
    normal_id, hidden_id = (line.strip().lower() for line in out.split())
    missing_id = str(uuid.uuid4())

    res = await _ok("rhino_delete", {"ids": [normal_id, hidden_id, missing_id]})

    assert res["deletedCount"] == 1
    assert res["requestedCount"] == 3
    reasons = {key.lower(): value for key, value in res["failureReasons"].items()}
    assert reasons == {hidden_id: "hidden", missing_id: "not_found"}
    assert "includeHidden" in res["hint"]


async def test_delete_takes_an_object_on_a_turned_off_layer_without_the_opt_in(fresh_document, tag):
    # Regression guard: "hidden" is the object's own mode. An object in normal
    # mode on a layer that is turned off was always deletable by id.
    switched_off = f"{tag}_off_delete"
    object_id = (await _setup(f'print(point(layer("{switched_off}"), 0))')).strip().lower()
    await _ok("rhino_layer_visibility", {"name": switched_off, "visible": False})

    deleted = await _ok("rhino_delete", {"ids": [object_id]})

    assert deleted["deletedCount"] == 1
    assert "failedIds" not in deleted


async def test_include_hidden_does_not_delete_a_hidden_object_on_a_locked_layer(fresh_document, tag):
    held = f"{tag}_locked"
    hidden_id = (
        await _setup(f'print(point(layer("{held}"), 0, hidden=True))')
    ).strip().lower()
    await _ok("rhino_layer_lock", {"name": held, "locked": True})

    # Without the opt-in the reason is already the lock, and there is no hint
    # to pass includeHidden: it would not delete this object either.
    res = await _tool("rhino_delete", {"ids": [hidden_id]})
    assert _is_error(res)
    assert "locked" in str(res)
    assert "includeHidden" not in str(res)

    res = await _tool("rhino_delete", {"ids": [hidden_id], "includeHidden": True})

    assert _is_error(res), f"includeHidden must not override a lock: {res!r}"
    assert "locked" in str(res)
    assert (await _ok("rhino_layer_dependencies", {"name": held}))["directObjects"] == 1


async def test_delete_reports_locked_for_a_locked_object_and_for_a_locked_layer(fresh_document, tag):
    free, locked_layer = f"{tag}_free", f"{tag}_locked_layer"
    out = await _setup(
        f'print(point(layer("{free}"), 0, locked=True))\n'
        f'print(point(layer("{locked_layer}"), 1))'
    )
    locked_id, on_locked_layer_id = (line.strip().lower() for line in out.split())
    await _ok("rhino_layer_lock", {"name": locked_layer, "locked": True})

    # The listing already says both will be refused, and for which reason.
    listed_free = await _ok("rhino_objects", {"layer": free})
    assert [(obj["mode"], obj["layerLocked"]) for obj in listed_free["objects"]] == [("locked", False)]
    listed_locked = await _ok("rhino_objects", {"layer": locked_layer})
    assert [(obj["mode"], obj["layerLocked"]) for obj in listed_locked["objects"]] == [("normal", True)]

    # includeHidden is about hidden objects only: it changes nothing here.
    for arguments in ({}, {"includeHidden": True}):
        res = await _tool(
            "rhino_delete", {"ids": [locked_id, on_locked_layer_id], **arguments}
        )
        assert _is_error(res), f"locked objects must not be deleted ({arguments}): {res!r}"
        reasons = {key.lower(): value for key, value in res["data"]["failureReasons"].items()}
        assert reasons == {locked_id: "locked", on_locked_layer_id: "locked"}
        assert "hint" not in res["data"]

    assert (await _ok("rhino_layer_dependencies", {"name": free}))["directObjects"] == 1
    assert (await _ok("rhino_layer_dependencies", {"name": locked_layer}))["directObjects"] == 1


async def test_include_hidden_does_not_delete_through_a_lock_inherited_from_the_parent_layer(fresh_document, tag):
    parent = f"{tag}_parent"
    child = f"{parent}::child"
    hidden_id = (
        await _setup(f'print(point(layer("{child}"), 0, hidden=True))')
    ).strip().lower()
    # Lock the parent only; Rhino locks the child through it.
    await _ok("rhino_layer_lock", {"name": parent, "locked": True})

    res = await _tool("rhino_delete", {"ids": [hidden_id], "includeHidden": True})

    assert _is_error(res), f"includeHidden must not override an inherited lock: {res!r}"
    assert "locked" in str(res)
    assert (await _ok("rhino_layer_dependencies", {"name": child}))["directObjects"] == 1


async def test_include_hidden_delete_is_one_undo_step_and_restores_the_hidden_object(fresh_document, tag):
    held = f"{tag}_undo"
    hidden_id = (
        await _setup(f'print(point(layer("{held}"), 0, hidden=True))')
    ).strip().lower()

    deleted = await _ok("rhino_delete", {"ids": [hidden_id], "includeHidden": True})
    assert deleted["hiddenDeletedCount"] == 1
    assert (await _ok("rhino_layer_dependencies", {"name": held}))["directObjects"] == 0

    # The undo action answers with a plain string, so _ok (dict only) does not fit.
    undone = await _tool("rhino_document_ops", {"action": "undo"})
    assert not _is_error(undone), f"undo failed: {undone!r}"

    # Back on its layer, and still hidden: undo restores the mode as well.
    after = await _ok("rhino_layer_dependencies", {"name": held})
    assert after["directObjects"] == 1
    assert [hidden.lower() for hidden in after["hiddenObjectIds"]] == [hidden_id]
    assert (await _setup(f'print(mode("{hidden_id}"))')).strip() == "Hidden"
