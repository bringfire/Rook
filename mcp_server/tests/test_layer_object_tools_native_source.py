"""Source-level guards for the layer and object tool fixes.

The native plug-in only runs inside Rhino, so these tests pin the
behaviour-carrying lines of the C++ handlers and check that the Python tool
schemas agree with them. They run without Rhino.

The behavioural counterparts, which need a Rhino running a plug-in built from
this source, are in ``test_layer_object_tools_live.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
NATIVE = REPO_ROOT / "src" / "RookNative"
LAYER_OPS = NATIVE / "Handlers" / "LayerOpsHandler.cpp"
SELECTION = NATIVE / "Handlers" / "SelectionHandler.cpp"
OBJECTS = NATIVE / "Handlers" / "ObjectsHandler.cpp"
LAYER_HELPERS = NATIVE / "Infrastructure" / "LayerHelpers.cpp"
DOCUMENT_HELPERS = NATIVE / "Models" / "DocumentHelpers.h"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_function(source: str, signature: str) -> str:
    start = source.index(signature)
    body_start = source.index("{", start)
    depth = 0
    for index in range(body_start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not extract function for {signature!r}")


async def _public_tools(monkeypatch) -> dict:
    from rook import server

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", "full")
    return {tool.name: tool for tool in await server.list_tools()}


# --- Case-only layer rename ---------------------------------------------------
#
# Rhino resolves layer paths case-insensitively, so looking up the target of a
# case-only rename ("mullions" -> "MULLIONS") finds the layer being renamed.
# The collision check must compare layer identity, not path text.


def test_layer_lookup_helper_returns_index_of_live_layer():
    source = _read(LAYER_HELPERS)
    lookup = _extract_function(source, "int FindLayerIndexByFullPath")

    assert "FindLayerFromFullPathName" in lookup
    assert "IsDeleted()" in lookup
    assert "return -1;" in lookup

    exists = _extract_function(source, "bool LayerExistsByFullPath")
    assert "FindLayerIndexByFullPath(pDoc, fullPath) >= 0" in exists


@pytest.mark.parametrize(
    "signature",
    [
        # rhino_layer_set_properties and rhino_layer_set_properties_batch
        "LayerMutationResult ApplyLayerPropertiesMutation",
        # rhino_layer_rename
        "void HandleLayerRename",
    ],
)
def test_rename_collision_compares_layer_identity_not_path_text(signature):
    body = _extract_function(_read(LAYER_OPS), signature)

    assert "const int existingIdx = FindLayerIndexByFullPath(pDoc, targetFullPath);" in body
    assert "existingIdx >= 0 && existingIdx != idx" in body
    # The defect: a case-sensitive comparison of the two path strings.
    assert "targetFullPath != " not in body


# --- What holds a layer: dependencies, delete, merge --------------------------
#
# Rhino refuses to delete a layer while any undeleted object is on it. Hidden
# objects, lights and objects on a turned-off layer count, and the default
# iterator (normal_or_locked_objects, no lights) returns none of them. Objects
# in the deleted state, kept for undo, do not hold a layer.


def test_layer_holder_scan_counts_hidden_objects_and_not_deleted_ones():
    source = _read(LAYER_OPS)
    scan = _extract_function(source, "LayerHolders CollectLayerHolders")

    assert "CRhinoObjectIterator::undeleted_objects" in scan
    assert "CRhinoObjectIterator::normal_or_locked_objects" not in scan
    assert "it.IncludeLights(true);" in scan
    assert "ON::light_object" in scan
    assert "ON::hidden_object" in scan
    # Deleted-but-undoable objects are counted separately, for information.
    assert "CRhinoObjectIterator::deleted_objects" in scan
    assert "++holders.deletedObjects;" in scan

    holders = _extract_function(source, "struct LayerHolders")
    can_delete = _extract_function(holders, "bool CanDelete() const")
    assert "objects == 0" in can_delete
    assert "deletedObjects" not in can_delete


@pytest.mark.parametrize(
    "signature",
    ["void HandleLayerDependencies", "void HandleDeleteLayer", "void HandleLayerMerge"],
)
def test_dependencies_delete_and_merge_share_one_holder_scan(signature):
    body = _extract_function(_read(LAYER_OPS), signature)

    assert "CollectLayerHolders(pDoc, " in body
    assert "CRhinoObjectIterator::normal_or_locked_objects" not in body


def test_dependencies_reports_every_holder_and_agrees_with_delete():
    body = _extract_function(_read(LAYER_OPS), "void HandleLayerDependencies")

    for key in (
        "directObjects",
        "hiddenObjects",
        "hiddenObjectTypes",
        "hiddenObjectIds",
        "lightObjects",
        "layerVisible",
        "deletedObjectsInUndo",
        "childLayers",
        "blockReferences",
        "isCurrentLayer",
        "blockers",
    ):
        assert f'wr.data["{key}"]' in body, key
    assert 'wr.data["canDelete"] = holders.CanDelete();' in body


def test_layer_delete_says_what_holds_the_layer_and_never_purges():
    body = _extract_function(_read(LAYER_OPS), "void HandleDeleteLayer")

    assert "holders.DescribeObjects()" in body
    assert "rhino_layer_dependencies" in body
    # Deleting a layer must never delete objects: no purge path, opt-in or not.
    assert "PurgeLayer" not in body
    assert '"purge"' not in body


def test_layer_merge_moves_hidden_objects_and_explains_a_failed_delete():
    body = _extract_function(_read(LAYER_OPS), "void HandleLayerMerge")
    move = body[body.index("int moved = 0;") :]

    assert "CRhinoObjectIterator::undeleted_objects" in move
    assert "it.IncludeLights(true);" in move
    assert 'wr.data["hiddenObjectsMoved"] = hiddenMoved;' in move
    failure = move[move.index("DeleteLayer(srcRef.index, true)") :]
    assert "DescribeBlockers()" in failure


@pytest.mark.asyncio
async def test_layer_tool_descriptions_state_the_holder_rules(monkeypatch):
    tools = await _public_tools(monkeypatch)

    dependencies = tools["rhino_layer_dependencies"].description
    for field in (
        "hiddenObjects",
        "hiddenObjectIds",
        "lightObjects",
        "layerVisible",
        "deletedObjectsInUndo",
        "blockers",
    ):
        assert field in dependencies, field
    assert "no purge option" in tools["rhino_layer_delete"].description
    assert "hiddenObjectsMoved" in tools["rhino_layer_merge"].description


# --- rhino_select: sub-layers are opt-in --------------------------------------
#
# `layer` selects objects directly on that layer (Rhino's SelLayer meaning).
# `includeSublayers: true` widens it to every layer nested below.


def test_select_layer_predicate_defaults_to_the_named_layer_only():
    body = _extract_function(_read(SELECTION), "void HandleSelect")

    assert 'const bool includeSublayers = body.value("includeSublayers", false);' in body
    assert "layerIndices.push_back(layerIdx);" in body
    assert "CollectLayerWithDescendants(pDoc, layerIdx)" in body
    assert "'includeSublayers' must be a boolean" in body
    assert "'includeSublayers' requires 'layer'" in body


def test_descendant_collection_walks_parent_ids_and_skips_deleted_layers():
    body = _extract_function(
        _read(LAYER_HELPERS), "std::vector<int> CollectLayerWithDescendants"
    )

    assert "result.push_back(layerIndex);" in body
    assert "ParentLayerId()" in body
    assert "IsDeleted()" in body


@pytest.mark.asyncio
async def test_rhino_select_schema_advertises_the_sublayer_opt_in(monkeypatch):
    tool = (await _public_tools(monkeypatch))["rhino_select"]
    prop = tool.inputSchema["properties"]["includeSublayers"]

    assert prop["type"] == "boolean"
    assert "default false" in prop["description"].lower()
    assert "includeSublayers" in tool.description
    assert "selects 0 objects" in tool.description


# --- rhino_objects: an unrecognized type is an error --------------------------
#
# ParseObjectTypeFilter returns 0 for a name it does not know, and 0 means
# "no filter" to the object iterator, so `type: "Unknown"` returned every
# object in the document.


def _native_type_filter_names() -> list[str]:
    table = _extract_function(
        _read(DOCUMENT_HELPERS),
        "inline const std::vector<ObjectTypeFilterEntry>& ObjectTypeFilterEntries",
    )
    return re.findall(r'\{"(\w+)",\s+ON::\w+\}', table)


def test_type_filter_parser_and_accepted_list_share_one_table():
    source = _read(DOCUMENT_HELPERS)

    assert "ObjectTypeFilterEntries()" in _extract_function(
        source, "inline unsigned int ParseObjectTypeFilter"
    )
    assert "ObjectTypeFilterEntries()" in _extract_function(
        source, "inline std::string ObjectTypeFilterNames"
    )

    names = _native_type_filter_names()
    assert len(names) == 13
    assert {"Point", "Curve", "Brep", "Mesh", "Extrusion", "ClipPlane"} <= set(names)
    # "Unknown" is what the serializer prints for types it has no name for;
    # it is not a type that can be filtered on.
    assert "Unknown" not in names
    # The objects query iterates without lights, so "Light" could never match.
    assert "Light" not in names


def test_objects_handler_rejects_an_unrecognized_type_before_querying():
    body = _extract_function(_read(OBJECTS), "void HandleObjects")
    reject = body.index("!typeFilter.empty() && ParseObjectTypeFilter(typeFilter) == 0")
    dispatch = body.index("CMainThreadDispatcher::Instance().Dispatch")

    assert reject < dispatch
    rejection = body[reject:dispatch]
    assert '{"errorCode", "invalid_input"}' in rejection
    assert "ObjectTypeFilterNames()" in rejection
    assert "acceptedTypes" in rejection
    assert "CRookServer::SendErrorData(res, err);" in rejection
    assert "return;" in rejection


@pytest.mark.asyncio
async def test_rhino_objects_schema_lists_exactly_the_native_type_names(monkeypatch):
    tool = (await _public_tools(monkeypatch))["rhino_objects"]
    description = tool.inputSchema["properties"]["type"]["description"]

    listed = description.split("Accepted values:")[1].split(".")[0]
    assert [name.strip() for name in listed.split(",")] == _native_type_filter_names()
    assert "rejected" in description
