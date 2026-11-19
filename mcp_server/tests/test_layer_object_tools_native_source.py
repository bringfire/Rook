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
LAYERS = NATIVE / "Handlers" / "LayersHandler.cpp"
DOCUMENT = NATIVE / "Handlers" / "DocumentHandler.cpp"
SELECTION = NATIVE / "Handlers" / "SelectionHandler.cpp"
OBJECTS = NATIVE / "Handlers" / "ObjectsHandler.cpp"
GEOMETRY_OPS = NATIVE / "Handlers" / "GeometryOpsHandler.cpp"
LAYER_HELPERS = NATIVE / "Infrastructure" / "LayerHelpers.cpp"
DOCUMENT_HELPERS = NATIVE / "Models" / "DocumentHelpers.h"
SERIALIZER = NATIVE / "Serialization" / "RhinoSerializer.cpp"


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
    assert len(names) == 15
    assert {"Point", "Curve", "Brep", "Mesh", "Extrusion", "ClipPlane"} <= set(names)
    # "Unknown" is what the serializer prints for types it has no name for;
    # it is not a type that can be filtered on.
    assert "Unknown" not in names
    # Lights are listed with includeHidden, so "Light" can be filtered on.
    assert "Light" in names


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


# --- Object counts and listings: hidden objects, off layers, lights -----------
#
# Rhino's default object iterator (normal_or_locked_objects, no lights) leaves
# out hidden objects, lights and every object on a layer that is turned off.
# Counts report every undeleted object; the rhino_objects listing keeps the
# default set, says how many matches it left out, and lists them on request.


def _iterates_every_undeleted_object(block: str) -> bool:
    return (
        "CRhinoObjectIterator::undeleted_objects" in block
        and "it.IncludeLights(true);" in block
    )


@pytest.mark.parametrize(
    "signature",
    [
        "inline ObjectCounts CountObjects",
        "inline std::unordered_map<int, ObjectCounts> CountObjectsByLayer",
    ],
)
def test_object_count_helpers_count_all_and_listed_separately(signature):
    body = _extract_function(_read(DOCUMENT_HELPERS), signature)
    all_pass, listed_pass = body.split("CRhinoObjectIterator::normal_or_locked_objects")

    # `all`: undeleted objects plus lights. `listed`: the default iterator.
    assert _iterates_every_undeleted_object(all_pass)
    assert ".all" in all_pass
    assert ".listed" in listed_pass
    assert "IncludeLights" not in listed_pass

    counts = _extract_function(_read(DOCUMENT_HELPERS), "struct ObjectCounts")
    assert "int Unlisted() const { return all - listed; }" in counts


def test_layers_handler_counts_every_object_on_a_layer():
    body = _extract_function(_read(LAYERS), "void HandleLayers")

    assert "CountObjectsByLayer(pDoc)" in body
    # The defect: counting with the default iterator made a turned-off layer
    # report objectCount 0.
    assert "CRhinoObjectIterator" not in body
    assert "snap.objectCount = countIt->second.all;" in body
    assert "snap.unlistedObjectCount = countIt->second.Unlisted();" in body


def test_single_layer_responses_use_the_same_count():
    body = _extract_function(
        _read(LAYER_OPS),
        # The definition, not the forward declaration above it.
        "static nlohmann::json SerializeLayerAtIndex(CRhinoDoc* pDoc, int layerIndex)\n{",
    )

    assert "CountObjects(pDoc, layerIndex)" in body
    assert "CRhinoObjectIterator" not in body
    assert "snap.objectCount = counts.all;" in body
    assert "snap.unlistedObjectCount = counts.Unlisted();" in body


def test_document_handler_counts_every_object():
    body = _extract_function(_read(DOCUMENT), "void HandleDocument")

    assert "CountObjects(pDoc)" in body
    assert "CRhinoObjectIterator" not in body
    assert "snap.objectCount = counts.all;" in body
    assert "snap.unlistedObjectCount = counts.Unlisted();" in body


def test_layer_and_document_responses_carry_the_unlisted_count():
    source = _read(SERIALIZER)

    layer = _extract_function(source, "nlohmann::json SerializeLayer")
    assert 'j["objectCount"] = layer.objectCount;' in layer
    assert 'j["unlistedObjectCount"] = layer.unlistedObjectCount;' in layer

    document = _extract_function(source, "nlohmann::json SerializeDocument")
    assert '{"objectCount", doc.objectCount}' in document
    assert '{"unlistedObjectCount", doc.unlistedObjectCount}' in document


def test_objects_listing_keeps_its_default_and_counts_what_it_leaves_out():
    body = _extract_function(_read(OBJECTS), "void HandleObjects")

    # Opt-in, default false.
    assert "bool includeHidden = false;" in body
    # The wide pass always runs; it is the listing only with includeHidden.
    wide = body[body.index("std::vector<const CRhinoObject*> allMatches;") :]
    default = wide[wide.index("if (includeHidden)") :]
    wide = wide[: wide.index("if (includeHidden)")]
    assert _iterates_every_undeleted_object(wide)
    assert "matches = std::move(allMatches);" in default
    # Without it, the listing is still the default iterator...
    assert "CRhinoObjectIterator::normal_or_locked_objects" in default
    # ...and the difference is reported, not dropped.
    assert "result.unlistedCount = static_cast<int>(allMatches.size() - matches.size());" in default
    assert 'data["unlistedCount"] = result.unlistedCount;' in body
    assert 'data["unlistedHint"]' in body
    assert "includeHidden: true" in body
    # Both passes apply one filter test, so the two counts are comparable.
    assert body.count("matchesFilters(obj)") == 2
    assert "it.SetObjectFilter(" not in body


def test_objects_handler_rejects_a_malformed_include_hidden_before_querying():
    body = _extract_function(_read(OBJECTS), "void HandleObjects")
    reject = body.index("if (!includeHiddenValid)")
    dispatch = body.index("CMainThreadDispatcher::Instance().Dispatch")

    assert reject < dispatch
    rejection = body[reject:dispatch]
    assert '{"errorCode", "invalid_input"}' in rejection
    assert "'includeHidden' must be a boolean" in rejection
    # The bridge sends GET arguments as query text, so "True"/"False" must parse.
    assert 'IEquals(raw, "true")' in body
    assert 'IEquals(raw, "false")' in body


@pytest.mark.asyncio
async def test_object_tool_schemas_state_what_is_counted_and_listed(monkeypatch):
    tools = await _public_tools(monkeypatch)

    objects = tools["rhino_objects"]
    prop = objects.inputSchema["properties"]["includeHidden"]
    assert prop["type"] == "boolean"
    assert "default false" in prop["description"].lower()
    assert "unlistedCount" in objects.description
    assert "includeHidden" in objects.description

    for name in ("rhino_layers", "rhino_document"):
        description = tools[name].description
        assert "unlistedObjectCount" in description, name
        assert "turned-off" in description or "turned off" in description, name


# --- rhino_layer_move_objects: "all objects" means all ------------------------


def test_layer_move_objects_moves_hidden_objects_and_lights():
    body = _extract_function(_read(LAYER_OPS), "void HandleLayerMoveObjects")

    assert _iterates_every_undeleted_object(body)
    assert "CRhinoObjectIterator::normal_or_locked_objects" not in body
    assert "ON::hidden_object" in body
    assert 'wr.data["hiddenObjectsMoved"] = hiddenMoved;' in body
    # A refusal must not open a message box now that more objects are reached.
    assert "ModifyObjectAttributes(CRhinoObjRef(obj), attrs, true)" in body
    # Unlike merge, the source layer is kept.
    assert "DeleteLayer" not in body


@pytest.mark.asyncio
async def test_layer_move_objects_description_says_hidden_objects_move(monkeypatch):
    description = (await _public_tools(monkeypatch))["rhino_layer_move_objects"].description

    assert "hiddenObjectsMoved" in description
    assert "lights" in description


# --- rhino_select / rhino_select_by_type: an unrecognized type is an error ----
#
# MapSelectTypeFilter returns 0 for a name it does not know, and the type
# predicate read 0 as "match all", so `type: "NoSuchType"` selected every
# object in the document.


def _native_select_type_names() -> list[str]:
    table = _extract_function(
        _read(SELECTION), "static const std::vector<SelectTypeEntry>& SelectTypeEntries"
    )
    return re.findall(r'\{"(\w+)",\s+ON::\w+\}', table)


def test_select_type_parser_and_accepted_list_share_one_table():
    source = _read(SELECTION)
    mapper = _extract_function(source, "static unsigned int MapSelectTypeFilter")

    assert "SelectTypeEntries()" in mapper
    assert "return 0;" in mapper
    assert "match all" not in mapper.split("{", 1)[1]

    names = _native_select_type_names()
    assert len(names) == len(set(names)) == 20
    # The original aliases still work.
    assert {"line", "circle", "arc", "polyline", "text", "block"} <= set(names)
    # Selection iterates without lights, so "light" could only select nothing.
    assert "light" not in names


def test_select_accepts_every_type_name_rhino_objects_prints_except_light():
    printed = {name.lower() for name in _native_type_filter_names()}

    assert printed - set(_native_select_type_names()) == {"light"}


def test_select_rejects_an_unrecognized_type_before_touching_the_selection():
    body = _extract_function(_read(SELECTION), "void HandleSelect")
    reject = body.index("if (MapSelectTypeFilter(typeStr) == 0)")
    dispatch = body.index("CMainThreadDispatcher::Instance().Dispatch")

    # Before the dispatch: `clear` runs inside it, so a rejected request must
    # not have cleared the selection.
    assert reject < dispatch
    rejection = body[reject:dispatch]
    assert '{"errorCode", "invalid_input"}' in rejection
    assert "acceptedTypes" in rejection
    assert "SelectTypeEntries()" in rejection
    assert "CRookServer::SendErrorData(res, err);" in rejection
    assert "return;" in rejection

    predicate = body[body.index("// 5. type") : body.index("// 6. namePattern")]
    # The defect: 0 treated as "matches everything".
    assert "(typeFilter == 0) ||" not in predicate
    assert "if (typeFilter == 0)" in predicate
    assert "throw std::invalid_argument" in predicate


@pytest.mark.asyncio
async def test_select_by_type_schema_lists_exactly_the_native_type_names(monkeypatch):
    tool = (await _public_tools(monkeypatch))["rhino_select_by_type"]
    description = tool.inputSchema["properties"]["type"]["description"]

    listed = description.split("Accepted values:")[1].split(".")[0]
    assert [name.strip() for name in listed.split(",")] == _native_select_type_names()
    assert "rejected" in description
    assert "rejected" in tool.description


# --- Detail views have a type name --------------------------------------------
#
# ObjectTypeToString had no case for ON::detail_object, so detail views were
# listed as "Unknown" — a type that cannot be filtered on.


def test_every_filterable_type_has_a_printed_name_and_the_reverse():
    printer = _extract_function(
        _read(DOCUMENT_HELPERS), "inline std::string ObjectTypeToString"
    )
    printed = dict(re.findall(r'case (ON::\w+):\s+return "(\w+)";', printer))
    table = _extract_function(
        _read(DOCUMENT_HELPERS),
        "inline const std::vector<ObjectTypeFilterEntry>& ObjectTypeFilterEntries",
    )
    filterable = {name: constant for name, constant in re.findall(r'\{"(\w+)",\s+(ON::\w+)\}', table)}

    assert printed["ON::detail_object"] == "Detail"
    # A type name read from a listing can be passed back as a filter, with the
    # same meaning, and nothing filterable prints as "Unknown".
    assert {name: constant for constant, name in printed.items()} == filterable


# --- rhino_delete: hidden objects are opt-in, and failures say why ------------
#
# CRhinoDoc::DeleteObject(objref, bQuiet, bIgnoreModes=false) refuses hidden
# and locked objects. A hidden id came back in failedIds with no reason.
# "Hidden" is the object's own mode: an object on a turned-off layer is in
# normal mode and Rhino deletes it by id as it always did.


def test_delete_refuses_hidden_objects_unless_asked_and_never_overrides_a_lock():
    body = _extract_function(_read(GEOMETRY_OPS), "void HandleDelete")

    assert "bool includeHidden = false;" in body
    assert "'includeHidden' must be a boolean" in body
    assert body.index("'includeHidden' must be a boolean") < body.index(
        "CMainThreadDispatcher::Instance().Dispatch"
    )

    hidden = body[body.index("else if (obj->Attributes().Mode() == ON::hidden_object)") :]
    hidden = hidden[: hidden.index("else if (pDoc->DeleteObject(CRhinoObjRef(obj), true))")]
    # bIgnoreModes=true appears once, and only on the hidden path...
    assert body.count("DeleteObject(CRhinoObjRef(obj), true, true)") == 1
    assert "DeleteObject(CRhinoObjRef(obj), true, true)" in hidden
    # ...after the lock check, the reference-object check and the opt-in check.
    locked = hidden.index("if (onLockedLayer(obj))")
    reference = hidden.index("else if (obj->IsReference())")
    refused = hidden.index("else if (!includeHidden)")
    ignore_modes = hidden.index("DeleteObject(CRhinoObjRef(obj), true, true)")
    assert locked < reference < refused < ignore_modes
    assert "m_layer_table[layerIdx].IsLocked()" in body

    for reason in ("not_found", "hidden", "locked", "not_deletable"):
        assert f'"{reason}"' in body, reason
    assert 'wr.data["failureReasons"]' in body
    assert 'wr.data["hiddenDeletedCount"] = hiddenDeletedCount;' in body
    assert "includeHidden: true" in body


@pytest.mark.asyncio
async def test_rhino_delete_schema_advertises_the_hidden_opt_in(monkeypatch):
    tool = (await _public_tools(monkeypatch))["rhino_delete"]
    prop = tool.inputSchema["properties"]["includeHidden"]

    assert prop["type"] == "boolean"
    assert "default false" in prop["description"].lower()
    assert "lock" in prop["description"]
    assert "failureReasons" in tool.description
    assert tool.inputSchema["required"] == ["ids"]
