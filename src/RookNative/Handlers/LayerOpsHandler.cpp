// LayerOpsHandler.cpp
//
// POST   /layers            — Create a layer
// POST   /layers/batch      — Create multiple layers atomically
// DELETE /layers            — Delete a layer
// POST   /layers/visibility — Show/hide a layer
// POST   /layers/lock       — Lock/unlock a layer
// POST   /layers/current    — Set current layer

#include "stdafx.h"
#include "Handlers/LayerOpsHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include "Infrastructure/LayerHelpers.h"

#include <cctype>
#include <functional>
#include <map>
#include <unordered_map>
#include <unordered_set>
#include <vector>

using Rook::Infrastructure::ResolvedLayerRef;
using Rook::Infrastructure::GetLayerFullPath;
using Rook::Infrastructure::JoinLayerPath;
using Rook::Infrastructure::ContainsPathSeparator;
using Rook::Infrastructure::LayerExistsByFullPath;
using Rook::Infrastructure::FindLayerIndexByFullPath;
using Rook::Infrastructure::ValidateNewLayerName;
using Rook::Infrastructure::ResolveLayerRef;

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// Forward declaration: definition at file scope below this namespace.
static nlohmann::json SerializeLayerAtIndex(CRhinoDoc* pDoc, int layerIndex);

namespace {

// Find a non-deleted material by name (matches pattern used in MaterialsHandler/BlocksHandler).
int FindMaterialIndexSafe(CRhinoDoc* pDoc, const std::string& name)
{
    ON_wString wName = Utf8ToWide(name);
    int count = pDoc->m_material_table.MaterialCount();
    for (int i = 0; i < count; ++i)
    {
        const CRhinoMaterial& mat = pDoc->m_material_table[i];
        if (mat.IsDeleted()) continue;
        if (mat.Name().CompareNoCase(wName) == 0)
            return i;
    }
    return -1;
}

// Everything that can keep a layer from being deleted.
//
// CRhinoLayerTable::DeleteLayer(quiet) refuses while ANY undeleted object is
// on the layer. Checked against Rhino 8, that includes three kinds the
// default iterator (normal_or_locked_objects, lights excluded) never returns:
//   - objects in hidden mode,
//   - objects on a layer that is turned off,
//   - lights.
// Counting with the default iterator therefore reports a layer as empty when
// Rhino will still refuse to delete it. Holders are counted with
// undeleted_objects plus IncludeLights.
//
// Objects in the deleted state do NOT hold a layer (a layer whose only object
// is deleted-but-undoable deletes fine). They are counted for information only.
struct LayerHolders
{
    int objects = 0;            // every undeleted object on the layer, lights included
    int hiddenObjects = 0;      // subset in hidden mode
    int lightObjects = 0;       // subset that are lights
    int deletedObjects = 0;     // objects in the deleted state — never a blocker
    std::map<std::string, int> hiddenTypes;
    std::vector<std::string> hiddenIds;     // capped at kMaxHiddenIds
    std::vector<std::string> childLayers;
    nlohmann::json blockRefs = nlohmann::json::array();
    bool isCurrent = false;
    bool layerVisible = true;

    static constexpr size_t kMaxHiddenIds = 50;

    bool CanDelete() const
    {
        return objects == 0 && childLayers.empty() && blockRefs.empty() && !isCurrent;
    }

    // True when the layer holds objects GET /objects (rhino_objects) will not
    // show: hidden objects, lights, or anything on a turned-off layer.
    bool HasUnlistedObjects() const
    {
        return hiddenObjects > 0 || lightObjects > 0 || (objects > 0 && !layerVisible);
    }

    // "6 objects (5 hidden: 5 ClipPlane; 1 light; layer is turned off)"
    std::string DescribeObjects() const
    {
        std::string text = std::to_string(objects) + (objects == 1 ? " object" : " objects");
        std::vector<std::string> notes;
        if (hiddenObjects > 0)
        {
            std::string note = std::to_string(hiddenObjects) + " hidden: ";
            bool first = true;
            for (const auto& entry : hiddenTypes)
            {
                if (!first) note += ", ";
                note += std::to_string(entry.second) + " " + entry.first;
                first = false;
            }
            notes.push_back(note);
        }
        if (lightObjects > 0)
            notes.push_back(std::to_string(lightObjects) + (lightObjects == 1 ? " light" : " lights"));
        if (objects > 0 && !layerVisible)
            notes.push_back("layer is turned off");

        if (!notes.empty())
        {
            text += " (";
            for (size_t i = 0; i < notes.size(); ++i)
            {
                if (i > 0) text += "; ";
                text += notes[i];
            }
            text += ")";
        }
        return text;
    }

    // One human-readable line per blocker; empty when the layer can be deleted.
    std::vector<std::string> Blockers() const
    {
        std::vector<std::string> blockers;
        if (isCurrent)
            blockers.push_back("it is the current layer");
        if (objects > 0)
            blockers.push_back("layer contains " + DescribeObjects());
        if (!childLayers.empty())
            blockers.push_back("layer has " + std::to_string(childLayers.size()) + " child layer(s)");
        for (const auto& ref : blockRefs)
        {
            blockers.push_back("block definition '" + ref.value("blockName", std::string()) +
                "' has " + std::to_string(ref.value("objectsOnLayer", 0)) +
                " object(s) on this layer");
        }
        return blockers;
    }

    std::string DescribeBlockers() const
    {
        std::string text;
        for (const auto& blocker : Blockers())
        {
            if (!text.empty()) text += "; ";
            text += blocker;
        }
        return text;
    }
};

LayerHolders CollectLayerHolders(CRhinoDoc* pDoc, int layerIdx)
{
    LayerHolders holders;
    const ON_UUID layerId = pDoc->m_layer_table[layerIdx].Id();
    holders.layerVisible = pDoc->m_layer_table[layerIdx].IsVisible();

    // Undeleted objects: normal, locked and hidden, on visible or hidden
    // layers, and lights (which the iterator leaves out unless asked).
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::undeleted_objects,
            CRhinoObjectIterator::active_objects);
        it.IncludeLights(true);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (obj->Attributes().m_layer_index != layerIdx)
                continue;
            ++holders.objects;
            if (obj->ObjectType() == ON::light_object)
                ++holders.lightObjects;
            if (obj->Attributes().Mode() == ON::hidden_object)
            {
                ++holders.hiddenObjects;
                ++holders.hiddenTypes[ObjectTypeToString(obj->ObjectType())];
                if (holders.hiddenIds.size() < LayerHolders::kMaxHiddenIds)
                    holders.hiddenIds.push_back(UuidToString(obj->Attributes().m_uuid));
            }
        }
    }

    // Objects in the deleted state (informational only). Rhino keeps these
    // for undo: objects the user deleted, and the earlier versions of objects
    // that were edited or replaced.
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::deleted_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (obj->Attributes().m_layer_index == layerIdx)
                ++holders.deletedObjects;
        }
    }

    // Child layers
    for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
    {
        const CRhinoLayer& other = pDoc->m_layer_table[i];
        if (other.IsDeleted()) continue;
        if (ON_UuidCompare(other.ParentLayerId(), layerId) == 0)
        {
            ON_wString childPath;
            pDoc->m_layer_table.GetLayerPathName(i, childPath);
            holders.childLayers.push_back(WideToUtf8(childPath));
        }
    }

    // Block definitions with geometry on this layer
    const CRhinoInstanceDefinitionTable& idefTable = pDoc->m_instance_definition_table;
    for (int d = 0; d < idefTable.InstanceDefinitionCount(); ++d)
    {
        const CRhinoInstanceDefinition* idef = idefTable[d];
        if (!idef || idef->IsDeleted()) continue;

        ON_SimpleArray<const CRhinoObject*> objArray;
        idef->GetObjects(objArray);

        int objsOnLayer = 0;
        for (int j = 0; j < objArray.Count(); ++j)
        {
            if (objArray[j] && objArray[j]->Attributes().m_layer_index == layerIdx)
                ++objsOnLayer;
        }

        if (objsOnLayer > 0)
        {
            ON_SimpleArray<const CRhinoInstanceObject*> refs;
            idef->GetReferences(refs);

            nlohmann::json ref;
            ref["blockName"] = WideToUtf8(idef->Name());
            ref["objectsOnLayer"] = objsOnLayer;
            ref["instanceCount"] = refs.Count();
            holders.blockRefs.push_back(std::move(ref));
        }
    }

    holders.isCurrent = (pDoc->m_layer_table.CurrentLayerIndex() == layerIdx);
    return holders;
}

// Validate that a JSON value is exactly a 3-element [r,g,b] integer array
// with each component in [0, 255]. Strict: 4-element arrays, negative values,
// out-of-range values, and non-integer types all fail. Prevents invalid
// payloads from flowing into ParseColor(), which would otherwise wrap or
// truncate them via implicit unsigned int conversion.
bool IsValidRgbArray(const nlohmann::json& val)
{
    if (!val.is_array() || val.size() != 3) return false;
    for (size_t i = 0; i < 3; ++i)
    {
        if (!val[i].is_number_integer()) return false;
        const int component = val[i].get<int>();
        if (component < 0 || component > 255) return false;
    }
    return true;
}

// Validate a rename string. Returns empty string on success, error message on failure.
std::string ValidateRenameShape(const nlohmann::json& val)
{
    if (!val.is_string()) return "rename must be a string";
    const std::string s = val.get<std::string>();
    if (s.empty()) return "rename must be non-empty";
    if (s.find("::") != std::string::npos) return "rename must not contain '::'";
    return "";
}

// Shared result carrier for the per-layer mutation. `success` is the canonical
// field. `errorCode` + `errorMessage` are populated only on failure. `layerData`
// is populated only on success (consumed by the single-target route's response).
struct LayerMutationResult
{
    bool success = false;
    std::string errorCode;
    std::string errorMessage;
    nlohmann::json layerData;
};

LayerMutationResult MakeLayerFailure(const std::string& code, const std::string& message)
{
    LayerMutationResult r;
    r.success = false;
    r.errorCode = code;
    r.errorMessage = message;
    return r;
}

// Apply one layer's property mutation against the current document state.
// Must be called on the Rhino main thread, inside an active UndoScope owned
// by the caller (single-target wraps with one UndoScope per request; batch
// wraps with one UndoScope around the per-item loop).
//
// This helper is the shared source of truth for per-layer mutation rules:
//   - shape validation of every property in `setProps`
//   - resolution of target layer, parent (if reparenting), linetype, material
//   - cycle detection and name-collision detection
//   - final ModifyLayer call
//
// Error classification is structured: shape/type errors (invalid_*) come first,
// then resolution errors (not_found, parent_not_found, linetype_not_found, etc.),
// then commit errors (modify_failed). An `exception` fallback catches anything
// unexpected from the underlying Rhino calls.
LayerMutationResult ApplyLayerPropertiesMutation(
    CRhinoDoc* pDoc,
    const std::string& name,
    const nlohmann::json& setProps)
{
    // ---- Shape: `name` — caller is expected to have checked, but guard anyway.
    if (name.empty())
        return MakeLayerFailure("invalid_name", "'name' must be a non-empty string");

    // ---- Shape: `set` empty → no_changes
    if (!setProps.is_object())
        return MakeLayerFailure("invalid_set", "'set' must be an object");
    if (setProps.empty())
        return MakeLayerFailure("no_changes", "'set' has no properties to apply");

    // ---- Shape validation (types/formats). Run before any doc mutation.
    if (setProps.contains("rename"))
    {
        const std::string renameErr = ValidateRenameShape(setProps["rename"]);
        if (!renameErr.empty()) return MakeLayerFailure("invalid_rename", renameErr);
    }
    if (setProps.contains("parent"))
    {
        const auto& pv = setProps["parent"];
        if (!pv.is_null() && !pv.is_string())
            return MakeLayerFailure("invalid_parent", "parent must be a string or null");
    }
    if (setProps.contains("color") && !IsValidRgbArray(setProps["color"]))
        return MakeLayerFailure("invalid_color", "color must be a 3-element integer array [r,g,b]");
    if (setProps.contains("plotColor") && !IsValidRgbArray(setProps["plotColor"]))
        return MakeLayerFailure("invalid_plot_color", "plotColor must be a 3-element integer array [r,g,b]");
    if (setProps.contains("plotWeight"))
    {
        if (!setProps["plotWeight"].is_number())
            return MakeLayerFailure("invalid_plot_weight", "plotWeight must be a number");
        if (setProps["plotWeight"].get<double>() < 0.0)
            return MakeLayerFailure("invalid_plot_weight", "plotWeight must be >= 0");
    }
    if (setProps.contains("linetype") && !setProps["linetype"].is_string())
        return MakeLayerFailure("invalid_linetype", "linetype must be a string");
    if (setProps.contains("linetypeIndex") && !setProps["linetypeIndex"].is_number_integer())
        return MakeLayerFailure("invalid_linetype_index", "linetypeIndex must be an integer");
    if (setProps.contains("material") && !setProps["material"].is_string())
        return MakeLayerFailure("invalid_material", "material must be a string");
    if (setProps.contains("materialIndex") && !setProps["materialIndex"].is_number_integer())
        return MakeLayerFailure("invalid_material_index", "materialIndex must be an integer");
    if (setProps.contains("visible") && !setProps["visible"].is_boolean())
        return MakeLayerFailure("invalid_visible", "visible must be a boolean");
    if (setProps.contains("locked") && !setProps["locked"].is_boolean())
        return MakeLayerFailure("invalid_locked", "locked must be a boolean");

    // ---- Resolution: target layer
    int idx = -1;
    try
    {
        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        idx = layerRef.index;
    }
    catch (const std::exception&)
    {
        return MakeLayerFailure("not_found", "Layer '" + name + "' not found");
    }

    ON_Layer layerCopy = pDoc->m_layer_table[idx];
    const ON_UUID layerId = layerCopy.Id();

    // ---- Resolution: parent (if reparenting) + cycle detection
    const bool hasParentOp = setProps.contains("parent");
    ON_UUID newParentId = layerCopy.ParentLayerId();
    std::string parentNameForError;
    if (hasParentOp)
    {
        if (setProps["parent"].is_null())
        {
            newParentId = ON_nil_uuid;
        }
        else
        {
            parentNameForError = setProps["parent"].get<std::string>();
            try
            {
                const ResolvedLayerRef parentRef =
                    ResolveLayerRef(pDoc, parentNameForError, "parent");
                newParentId = pDoc->m_layer_table[parentRef.index].Id();
            }
            catch (const std::exception&)
            {
                return MakeLayerFailure("parent_not_found",
                    "Parent '" + parentNameForError + "' not found");
            }

            if (ON_UuidCompare(newParentId, layerId) == 0)
                return MakeLayerFailure("cycle_detected",
                    "Cannot reparent layer under itself");

            ON_UUID walkId = newParentId;
            while (!ON_UuidIsNil(walkId))
            {
                bool found = false;
                const int layerCount = pDoc->m_layer_table.LayerCount();
                for (int i = 0; i < layerCount; ++i)
                {
                    const CRhinoLayer& walkLayer = pDoc->m_layer_table[i];
                    if (walkLayer.IsDeleted()) continue;
                    if (ON_UuidCompare(walkLayer.Id(), walkId) == 0)
                    {
                        walkId = walkLayer.ParentLayerId();
                        if (ON_UuidCompare(walkId, layerId) == 0)
                            return MakeLayerFailure("cycle_detected",
                                "Parent '" + parentNameForError +
                                "' is a descendant of '" + name + "'");
                        found = true;
                        break;
                    }
                }
                if (!found) break;
            }
        }
    }

    // ---- Rename shape validation (defensive; pre-validation already covered it)
    if (setProps.contains("rename"))
    {
        const std::string newName = setProps["rename"].get<std::string>();
        try { ValidateNewLayerName(newName); }
        catch (const std::exception& ex) { return MakeLayerFailure("invalid_rename", ex.what()); }
    }

    // ---- Collision check: runs whenever the target full path could change,
    //      i.e. when EITHER `rename` OR `parent` is present. Pure reparent
    //      that lands the layer next to an existing same-named sibling must
    //      surface as `name_collision`, not fall through to `modify_failed`.
    const bool hasRenameOp = setProps.contains("rename");
    if (hasRenameOp || hasParentOp)
    {
        // Target leaf name: rename if specified, else current name.
        const std::string targetLeafName = hasRenameOp
            ? setProps["rename"].get<std::string>()
            : WideToUtf8(layerCopy.Name());

        // Target parent path: new parent if reparenting, else current parent.
        const ON_UUID targetParentId = hasParentOp ? newParentId : layerCopy.ParentLayerId();
        std::string parentPath;
        if (!ON_UuidIsNil(targetParentId))
        {
            const int layerCount = pDoc->m_layer_table.LayerCount();
            for (int i = 0; i < layerCount; ++i)
            {
                if (!pDoc->m_layer_table[i].IsDeleted() &&
                    ON_UuidCompare(pDoc->m_layer_table[i].Id(), targetParentId) == 0)
                {
                    ON_wString pp;
                    pDoc->m_layer_table.GetLayerPathName(i, pp);
                    parentPath = WideToUtf8(pp);
                    break;
                }
            }
        }
        const std::string targetFullPath = JoinLayerPath(parentPath, targetLeafName);
        // Rhino resolves layer paths case-insensitively, so a case-only rename
        // ("mullions" -> "MULLIONS") finds the layer being renamed. Only a
        // DIFFERENT layer at the target path is a collision.
        const int existingIdx = FindLayerIndexByFullPath(pDoc, targetFullPath);
        if (existingIdx >= 0 && existingIdx != idx)
        {
            return MakeLayerFailure("name_collision",
                "Layer '" + targetFullPath + "' already exists");
        }
    }

    // ---- Apply rename + parent (after collision check has cleared the path)
    if (setProps.contains("rename"))
        layerCopy.SetName(Utf8ToWide(setProps["rename"].get<std::string>()));
    if (hasParentOp)
        layerCopy.SetParentLayerId(newParentId);

    // ---- Apply display/render props. Shape was pre-validated; remaining
    //      failure modes are value-lookup (linetype/material name → index).
    if (setProps.contains("color"))
        layerCopy.SetColor(ParseColor(setProps, "color"));
    if (setProps.contains("plotColor"))
        layerCopy.SetPlotColor(ParseColor(setProps, "plotColor"));
    if (setProps.contains("plotWeight"))
        layerCopy.SetPlotWeight(setProps["plotWeight"].get<double>());
    if (setProps.contains("visible"))
        layerCopy.SetVisible(setProps["visible"].get<bool>());
    if (setProps.contains("locked"))
        layerCopy.SetLocked(setProps["locked"].get<bool>());

    if (setProps.contains("linetype"))
    {
        const std::string ltName = setProps["linetype"].get<std::string>();
        const int ltIdx = pDoc->m_linetype_table.FindLinetype(Utf8ToWide(ltName));
        if (ltIdx < 0)
            return MakeLayerFailure("linetype_not_found",
                "Linetype '" + ltName + "' not found");
        layerCopy.SetLinetypeIndex(ltIdx);
    }
    else if (setProps.contains("linetypeIndex"))
    {
        const int ltIdx = setProps["linetypeIndex"].get<int>();
        if (ltIdx < -1)
            return MakeLayerFailure("invalid_linetype_index",
                "linetypeIndex must be -1 (default) or a valid index");
        if (ltIdx >= 0 && ltIdx >= pDoc->m_linetype_table.LinetypeCount())
            return MakeLayerFailure("invalid_linetype_index",
                "linetypeIndex out of range");
        layerCopy.SetLinetypeIndex(ltIdx);
    }

    if (setProps.contains("material"))
    {
        const std::string matName = setProps["material"].get<std::string>();
        const int matIdx = FindMaterialIndexSafe(pDoc, matName);
        if (matIdx < 0)
            return MakeLayerFailure("material_not_found",
                "Material '" + matName + "' not found");
        layerCopy.SetRenderMaterialIndex(matIdx);
    }
    else if (setProps.contains("materialIndex"))
    {
        const int matIdx = setProps["materialIndex"].get<int>();
        if (matIdx < -1)
            return MakeLayerFailure("invalid_material_index",
                "materialIndex must be -1 (no material) or a valid index");
        if (matIdx >= 0)
        {
            if (matIdx >= pDoc->m_material_table.MaterialCount())
                return MakeLayerFailure("invalid_material_index",
                    "materialIndex out of range");
            if (pDoc->m_material_table[matIdx].IsDeleted())
                return MakeLayerFailure("invalid_material_index",
                    "materialIndex " + std::to_string(matIdx) +
                    " references a deleted material");
        }
        layerCopy.SetRenderMaterialIndex(matIdx);
    }

    // ---- Commit
    if (!pDoc->m_layer_table.ModifyLayer(layerCopy, idx))
        return MakeLayerFailure("modify_failed",
            "ModifyLayer returned false for '" + name + "'");

    // ---- Success
    LayerMutationResult ok;
    ok.success = true;
    ok.layerData = SerializeLayerAtIndex(pDoc, idx);
    return ok;
}

// Apply optional layer properties from a JSON object to an ON_Layer.
// Used by create, batch create, and set_properties handlers.
void ApplyLayerProperties(ON_Layer& layer, const nlohmann::json& spec, CRhinoDoc* pDoc)
{
    if (spec.contains("color"))
        layer.SetColor(ParseColor(spec, "color"));

    if (spec.contains("plotColor"))
        layer.SetPlotColor(ParseColor(spec, "plotColor"));

    if (spec.contains("plotWeight"))
    {
        double pw = spec["plotWeight"].get<double>();
        if (pw < 0.0)
            throw std::invalid_argument("plotWeight must be >= 0");
        layer.SetPlotWeight(pw);
    }

    if (spec.contains("visible"))
        layer.SetVisible(spec["visible"].get<bool>());

    if (spec.contains("locked"))
        layer.SetLocked(spec["locked"].get<bool>());

    // Note: expanded (UI tree state) is not exposed in the C++ SDK

    if (spec.contains("linetype"))
    {
        const std::string ltName = spec["linetype"].get<std::string>();
        int ltIdx = pDoc->m_linetype_table.FindLinetype(Utf8ToWide(ltName));
        if (ltIdx < 0)
            throw std::invalid_argument("Linetype '" + ltName + "' not found");
        layer.SetLinetypeIndex(ltIdx);
    }
    else if (spec.contains("linetypeIndex"))
    {
        int ltIdx = spec["linetypeIndex"].get<int>();
        if (ltIdx < -1)
            throw std::invalid_argument("linetypeIndex must be -1 (default) or a valid index");
        if (ltIdx >= 0 && ltIdx >= pDoc->m_linetype_table.LinetypeCount())
            throw std::invalid_argument("linetypeIndex out of range");
        layer.SetLinetypeIndex(ltIdx);
    }

    if (spec.contains("material"))
    {
        const std::string matName = spec["material"].get<std::string>();
        int matIdx = FindMaterialIndexSafe(pDoc, matName);
        if (matIdx < 0)
            throw std::invalid_argument("Material '" + matName + "' not found");
        layer.SetRenderMaterialIndex(matIdx);
    }
    else if (spec.contains("materialIndex"))
    {
        int matIdx = spec["materialIndex"].get<int>();
        if (matIdx < -1)
            throw std::invalid_argument("materialIndex must be -1 (no material) or a valid index");
        if (matIdx >= 0)
        {
            if (matIdx >= pDoc->m_material_table.MaterialCount())
                throw std::invalid_argument("materialIndex out of range");
            if (pDoc->m_material_table[matIdx].IsDeleted())
                throw std::invalid_argument("materialIndex " + std::to_string(matIdx) + " references a deleted material");
        }
        layer.SetRenderMaterialIndex(matIdx);
    }
}

struct BatchLayerItem
{
    std::string key;
    std::string name;
    std::string parentKey;
    nlohmann::json spec;
};

std::string ToLowerAscii(std::string value)
{
    for (char& ch : value)
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    return value;
}

std::vector<BatchLayerItem> ParseBatchLayerItems(const nlohmann::json& body)
{
    if (!body.contains("layers") || !body["layers"].is_array())
        throw std::invalid_argument("Missing 'layers' array");

    const auto& layers = body["layers"];
    if (layers.empty())
        throw std::invalid_argument("'layers' array cannot be empty");

    std::vector<BatchLayerItem> items;
    items.reserve(layers.size());

    std::unordered_set<std::string> keysSeen;
    for (size_t i = 0; i < layers.size(); ++i)
    {
        const auto& item = layers[i];
        const std::string itemPrefix = "layers[" + std::to_string(i) + "]";
        if (!item.is_object())
            throw std::invalid_argument(itemPrefix + " must be an object");
        if (!item.contains("key") || !item["key"].is_string())
            throw std::invalid_argument(itemPrefix + " is missing string field 'key'");
        if (!item.contains("name") || !item["name"].is_string())
            throw std::invalid_argument(itemPrefix + " is missing string field 'name'");

        BatchLayerItem parsed;
        parsed.key = item["key"].get<std::string>();
        parsed.name = item["name"].get<std::string>();
        if (item.contains("parentKey"))
        {
            if (!item["parentKey"].is_string())
                throw std::invalid_argument(itemPrefix + ".parentKey must be a string");
            parsed.parentKey = item["parentKey"].get<std::string>();
        }
        parsed.spec = item;

        if (parsed.key.empty())
            throw std::invalid_argument(itemPrefix + ".key cannot be empty");
        ValidateNewLayerName(parsed.name);

        const std::string normalizedKey = ToLowerAscii(parsed.key);
        if (!keysSeen.insert(normalizedKey).second)
            throw std::invalid_argument("Duplicate batch layer key '" + parsed.key + "'");

        items.push_back(std::move(parsed));
    }

    return items;
}

} // namespace

// Capture a LayerSnapshot for a given layer index, then serialize to JSON.
// Called on the main thread.
static nlohmann::json SerializeLayerAtIndex(CRhinoDoc* pDoc, int layerIndex)
{
    const CRhinoLayer& layer = pDoc->m_layer_table[layerIndex];

    LayerSnapshot snap;
    snap.id = UuidToString(layer.Id());
    snap.index = layerIndex;
    snap.name = WideToUtf8(layer.Name());

    ON_wString fullPath;
    pDoc->m_layer_table.GetLayerPathName(layerIndex, fullPath);
    snap.fullPath = WideToUtf8(fullPath);

    ON_Color c = layer.Color();
    snap.color = { static_cast<int>(c.Red()),
                   static_cast<int>(c.Green()),
                   static_cast<int>(c.Blue()) };

    ON_Color pc = layer.PlotColor();
    snap.plotColor = { static_cast<int>(pc.Red()),
                       static_cast<int>(pc.Green()),
                       static_cast<int>(pc.Blue()) };

    snap.plotWeight = layer.PlotWeight();

    snap.linetypeIndex = layer.LinetypeIndex();
    if (snap.linetypeIndex >= 0 &&
        snap.linetypeIndex < pDoc->m_linetype_table.LinetypeCount())
    {
        const ON_Linetype& lt = pDoc->m_linetype_table[snap.linetypeIndex];
        snap.linetypeName = WideToUtf8(lt.Name());
    }
    else
    {
        snap.linetypeName = "Continuous";
    }

    snap.materialIndex = layer.RenderMaterialIndex();
    if (snap.materialIndex >= 0 &&
        snap.materialIndex < pDoc->m_material_table.MaterialCount())
    {
        const CRhinoMaterial& mat = pDoc->m_material_table[snap.materialIndex];
        snap.materialName = WideToUtf8(mat.Name());
    }

    snap.visible = layer.IsVisible();
    snap.locked = layer.IsLocked();
    // Note: IsExpanded is UI state not exposed in the C++ SDK

    ON_UUID parentId = layer.ParentLayerId();
    if (ON_UuidIsNil(parentId))
        snap.parentId.clear();
    else
        snap.parentId = UuidToString(parentId);

    // Object count: quick scan (acceptable for single-layer response).
    // Same meaning as GET /layers: every undeleted object on the layer.
    const ObjectCounts counts = CountObjects(pDoc, layerIndex);
    snap.objectCount = counts.all;
    snap.unlistedObjectCount = counts.Unlisted();

    return Serializer::SerializeLayer(snap);
}

// ─── POST /layers — Create Layer ────────────────────────────────────

void HandleCreateLayer(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field in request");
        return;
    }

    std::string name = body["name"].get<std::string>();
    try
    {
        ValidateNewLayerName(name);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create Layer");

        std::string parentPath;
        ON_UUID parentId = ON_nil_uuid;
        if (body.contains("parent"))
        {
            if (!body["parent"].is_string())
                throw std::invalid_argument("'parent' must be a string");

            const std::string parentName = body["parent"].get<std::string>();
            const ResolvedLayerRef parentRef = ResolveLayerRef(pDoc, parentName, "parent");
            parentPath = parentRef.fullPath;
            parentId = pDoc->m_layer_table[parentRef.index].Id();
        }

        const std::string targetFullPath = JoinLayerPath(parentPath, name);
        if (LayerExistsByFullPath(pDoc, targetFullPath))
            throw std::invalid_argument("Layer '" + targetFullPath + "' already exists");

        // Build the new layer
        ON_Layer layer;
        layer.SetName(Utf8ToWide(name));

        if (!ON_UuidIsNil(parentId))
            layer.SetParentLayerId(parentId);

        ApplyLayerProperties(layer, body, pDoc);

        int newIdx = pDoc->m_layer_table.AddLayer(layer);
        if (newIdx < 0)
            throw std::runtime_error("Failed to create layer");

        WriteResult wr;
        wr.success = true;
        wr.data = SerializeLayerAtIndex(pDoc, newIdx);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

void HandleCreateLayersBatch(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    try
    {
        ParseBatchLayerItems(body);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create Layers Batch");

        const std::vector<BatchLayerItem> items = ParseBatchLayerItems(body);

        std::string rootParentPath;
        ON_UUID rootParentId = ON_nil_uuid;
        if (body.contains("rootParent"))
        {
            if (!body["rootParent"].is_string())
                throw std::invalid_argument("'rootParent' must be a string");
            const ResolvedLayerRef rootParent =
                ResolveLayerRef(pDoc, body["rootParent"].get<std::string>(), "rootParent");
            rootParentPath = rootParent.fullPath;
            rootParentId = pDoc->m_layer_table[rootParent.index].Id();
        }

        std::unordered_map<std::string, BatchLayerItem> itemsByKey;
        itemsByKey.reserve(items.size());
        for (const BatchLayerItem& item : items)
            itemsByKey.emplace(ToLowerAscii(item.key), item);

        std::unordered_map<std::string, std::string> fullPathByKey;
        std::unordered_map<std::string, int> visitState;

        std::function<std::string(const std::string&)> computeFullPath =
            [&](const std::string& normalizedKey) -> std::string
        {
            auto cached = fullPathByKey.find(normalizedKey);
            if (cached != fullPathByKey.end())
                return cached->second;

            auto itemIt = itemsByKey.find(normalizedKey);
            if (itemIt == itemsByKey.end())
                throw std::invalid_argument("Unknown batch layer key '" + normalizedKey + "'");

            int& state = visitState[normalizedKey];
            if (state == 1)
                throw std::invalid_argument("Cycle detected in batch layer parentKey references");
            if (state == 2)
                return fullPathByKey.at(normalizedKey);

            state = 1;

            std::string parentPath = rootParentPath;
            if (!itemIt->second.parentKey.empty())
            {
                const std::string parentNormalized = ToLowerAscii(itemIt->second.parentKey);
                if (itemsByKey.find(parentNormalized) == itemsByKey.end())
                {
                    throw std::invalid_argument(
                        "Layer '" + itemIt->second.key + "' references unknown parentKey '" +
                        itemIt->second.parentKey + "'");
                }
                parentPath = computeFullPath(parentNormalized);
            }

            const std::string fullPath = JoinLayerPath(parentPath, itemIt->second.name);
            fullPathByKey[normalizedKey] = fullPath;
            state = 2;
            return fullPath;
        };

        std::unordered_set<std::string> batchFullPaths;
        batchFullPaths.reserve(items.size());
        for (const BatchLayerItem& item : items)
        {
            const std::string normalizedKey = ToLowerAscii(item.key);
            const std::string targetFullPath = computeFullPath(normalizedKey);
            const std::string normalizedPath = ToLowerAscii(targetFullPath);
            if (!batchFullPaths.insert(normalizedPath).second)
                throw std::invalid_argument("Duplicate target layer path '" + targetFullPath + "' in batch");
            if (LayerExistsByFullPath(pDoc, targetFullPath))
                throw std::invalid_argument("Layer '" + targetFullPath + "' already exists");
        }

        std::unordered_map<std::string, int> createdIndexByKey;
        createdIndexByKey.reserve(items.size());

        std::function<int(const std::string&)> ensureCreated =
            [&](const std::string& normalizedKey) -> int
        {
            auto existing = createdIndexByKey.find(normalizedKey);
            if (existing != createdIndexByKey.end())
                return existing->second;

            const BatchLayerItem& item = itemsByKey.at(normalizedKey);

            ON_Layer layer;
            layer.SetName(Utf8ToWide(item.name));

            ApplyLayerProperties(layer, item.spec, pDoc);

            if (!item.parentKey.empty())
            {
                const std::string parentNormalized = ToLowerAscii(item.parentKey);
                const int parentIdx = ensureCreated(parentNormalized);
                layer.SetParentLayerId(pDoc->m_layer_table[parentIdx].Id());
            }
            else if (!ON_UuidIsNil(rootParentId))
            {
                layer.SetParentLayerId(rootParentId);
            }

            const int newIdx = pDoc->m_layer_table.AddLayer(layer);
            if (newIdx < 0)
            {
                throw std::runtime_error(
                    "Failed to create layer '" + fullPathByKey.at(normalizedKey) + "'");
            }

            createdIndexByKey[normalizedKey] = newIdx;
            return newIdx;
        };

        nlohmann::json created = nlohmann::json::array();
        for (const BatchLayerItem& item : items)
        {
            const std::string normalizedKey = ToLowerAscii(item.key);
            const int newIdx = ensureCreated(normalizedKey);

            nlohmann::json entry = SerializeLayerAtIndex(pDoc, newIdx);
            entry["key"] = item.key;
            if (!item.parentKey.empty())
                entry["parentKey"] = item.parentKey;
            created.push_back(std::move(entry));
        }

        WriteResult wr;
        wr.success = true;
        wr.data["count"] = static_cast<int>(created.size());
        wr.data["layers"] = std::move(created);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── DELETE /layers — Delete Layer ──────────────────────────────────

void HandleDeleteLayer(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field in request");
        return;
    }

    std::string name = body["name"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Delete Layer");

        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        const int layerIdx = layerRef.index;

        const CRhinoLayer& layer = pDoc->m_layer_table[layerIdx];
        if (layer.IsDeleted())
            throw std::invalid_argument("Layer '" + name + "' already deleted");

        // Preflight with the same holder scan rhino_layer_dependencies reports,
        // so the two agree and the refusal says what is holding the layer.
        const LayerHolders holders = CollectLayerHolders(pDoc, layerIdx);

        if (holders.objects > 0)
        {
            std::string message = "Cannot delete layer '" + name +
                "': layer contains " + holders.DescribeObjects();
            if (holders.HasUnlistedObjects())
                message += ". rhino_objects does not list hidden objects, lights, "
                    "or objects on a turned-off layer, and rhino_delete cannot "
                    "delete hidden objects; rhino_layer_dependencies reports them. "
                    "rhino_layer_merge moves everything to another layer (hidden "
                    "objects stay hidden) and then deletes this one";
            throw std::invalid_argument(message);
        }

        if (holders.isCurrent)
            throw std::invalid_argument("Cannot delete layer '" + name +
                "': it is the current layer");

        if (!holders.childLayers.empty())
            throw std::invalid_argument("Cannot delete layer '" + name +
                "': layer has " + std::to_string(holders.childLayers.size()) + " child layer(s)");

        if (!holders.blockRefs.empty())
            throw std::invalid_argument("Cannot delete layer '" + name + "': " +
                holders.DescribeBlockers() +
                ". Use rhino_block_set_layers to remap block geometry first");

        if (!pDoc->m_layer_table.DeleteLayer(layerIdx, true))
            throw std::runtime_error("Failed to delete layer '" + name +
                "': Rhino refused the delete although no object, child layer or "
                "block definition was found on it. Check rhino_layer_dependencies");

        WriteResult wr;
        wr.success = true;
        wr.data["deleted"] = name;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/visibility ────────────────────────────────────────

void HandleLayerVisibility(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field");
        return;
    }
    if (!body.contains("visible") || !body["visible"].is_boolean())
    {
        CRookServer::SendError(res, "Missing 'visible' field (boolean)");
        return;
    }

    std::string name = body["name"].get<std::string>();
    bool visible = body["visible"].get<bool>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, visible]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Set Layer Visibility");

        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        const int idx = layerRef.index;

        // C++ SDK layer modification: copy → modify → ModifyLayer
        ON_Layer layerCopy = pDoc->m_layer_table[idx];
        layerCopy.SetVisible(visible);
        if (!pDoc->m_layer_table.ModifyLayer(layerCopy, idx))
            throw std::runtime_error("Failed to modify visibility for layer '" + name + "'");

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["name"] = name;
        wr.data["visible"] = visible;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/lock ──────────────────────────────────────────────

void HandleLayerLock(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field");
        return;
    }
    if (!body.contains("locked") || !body["locked"].is_boolean())
    {
        CRookServer::SendError(res, "Missing 'locked' field (boolean)");
        return;
    }

    std::string name = body["name"].get<std::string>();
    bool locked = body["locked"].get<bool>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, locked]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Set Layer Lock");

        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        const int idx = layerRef.index;

        ON_Layer layerCopy = pDoc->m_layer_table[idx];
        layerCopy.SetLocked(locked);
        if (!pDoc->m_layer_table.ModifyLayer(layerCopy, idx))
            throw std::runtime_error("Failed to modify lock state for layer '" + name + "'");

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["name"] = name;
        wr.data["locked"] = locked;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/current ───────────────────────────────────────────

void HandleLayerCurrent(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field");
        return;
    }

    std::string name = body["name"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Set Current Layer");

        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        const int idx = layerRef.index;

        if (!pDoc->m_layer_table.SetCurrentLayerIndex(idx, true))
            throw std::runtime_error("Failed to set current layer to '" + name + "'");

        WriteResult wr;
        wr.success = true;
        wr.data["currentLayer"] = name;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/properties — Set any combination of layer properties ──

void HandleLayerSetProperties(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field (target layer)");
        return;
    }
    if (!body.contains("set") || !body["set"].is_object())
    {
        CRookServer::SendError(res, "Missing 'set' object with properties to modify");
        return;
    }

    std::string name = body["name"].get<std::string>();
    nlohmann::json props = body["set"];

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, props]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Set Layer Properties");

        // Route through the shared helper. The helper owns all validation,
        // resolution, and the ModifyLayer call.
        LayerMutationResult r = ApplyLayerPropertiesMutation(pDoc, name, props);

        // Preserve legacy single-target behavior: empty `set` is a successful
        // no-op that returns the current (unchanged) layer snapshot. The batch
        // route reports no_changes as a per-item skip; single-target doesn't.
        if (!r.success && r.errorCode == "no_changes")
        {
            const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
            pDoc->Redraw();
            WriteResult wr;
            wr.success = true;
            wr.data = SerializeLayerAtIndex(pDoc, layerRef.index);
            return wr;
        }

        if (!r.success)
        {
            // Any other failure raises; outer try/catch converts to SendError.
            if (r.errorCode == "modify_failed")
                throw std::runtime_error(r.errorMessage);
            throw std::invalid_argument(r.errorMessage);
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data = std::move(r.layerData);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/properties-batch — Best-effort batch set-properties ──
//
// Body: { "items": [{ "name": "...", "set": {...} }, ...], "redraw": false? }
//
// Shape/top-level contract (request-level failures, HTTP error):
//   - body must parse
//   - `items` must be an array
//   - `redraw` if present must be boolean
//
// Per-item semantics (best-effort, structured skip on failure):
//   - Each item resolves `name`, `parent`, linetype, material, and sibling
//     collisions against the current doc state at that item's turn.
//   - Order is observable; cross-item dependency choreography is NOT
//     guaranteed. Callers sequence if they need strict ordering.
//   - Empty `set: {}` records an item-level `no_changes` error (unlike the
//     single-target route, which treats empty set as a silent no-op success).
//
// Response: { routed, skipped, total, errors? } — compact summary convention.
void HandleLayerSetPropertiesBatch(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (body.is_null())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }
    if (!body.contains("items") || !body["items"].is_array())
    {
        CRookServer::SendError(res, "'items' array required");
        return;
    }
    if (body.contains("redraw") && !body["redraw"].is_boolean())
    {
        CRookServer::SendError(res, "'redraw' must be a boolean");
        return;
    }

    const bool redraw = !body.contains("redraw") || body["redraw"].get<bool>();
    nlohmann::json items = body["items"];

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, items, redraw]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Batch Set Layer Properties");

        int routed = 0;
        int skipped = 0;
        nlohmann::json errors = nlohmann::json::array();

        for (const auto& item : items)
        {
            // Echo the request's `name` verbatim as a raw JSON value. If the
            // caller sent `{"name": 123}` we echo 123; if `{"name": null}`,
            // null; if the item is not an object at all, null. This preserves
            // the "errors[].name always echoes the request name verbatim"
            // contract regardless of the value's type or shape.
            nlohmann::json echoName = nullptr;
            if (item.is_object() && item.contains("name"))
                echoName = item["name"];

            try
            {
                if (!item.is_object())
                {
                    errors.push_back({{"name", echoName}, {"error", "invalid_name"},
                                      {"message", "item must be an object"}});
                    ++skipped;
                    continue;
                }
                if (!item.contains("name") || !item["name"].is_string() ||
                    item["name"].get<std::string>().empty())
                {
                    errors.push_back({{"name", echoName}, {"error", "invalid_name"},
                                      {"message", "'name' must be a non-empty string"}});
                    ++skipped;
                    continue;
                }
                if (!item.contains("set") || item["set"].is_null() || !item["set"].is_object())
                {
                    errors.push_back({{"name", echoName}, {"error", "invalid_set"},
                                      {"message", "'set' must be a non-null object"}});
                    ++skipped;
                    continue;
                }

                const std::string itemName = item["name"].get<std::string>();
                const nlohmann::json& setProps = item["set"];

                LayerMutationResult r = ApplyLayerPropertiesMutation(pDoc, itemName, setProps);

                if (r.success)
                {
                    ++routed;
                }
                else
                {
                    nlohmann::json entry = {
                        {"name", echoName},
                        {"error", r.errorCode},
                    };
                    if (!r.errorMessage.empty())
                        entry["message"] = r.errorMessage;
                    // Useful extras for retry diagnostics on structural failures.
                    if (setProps.contains("rename") && setProps["rename"].is_string())
                        entry["rename"] = setProps["rename"].get<std::string>();
                    if (setProps.contains("parent"))
                    {
                        const auto& pv = setProps["parent"];
                        if (pv.is_null())
                            entry["parent"] = nullptr;
                        else if (pv.is_string())
                            entry["parent"] = pv.get<std::string>();
                    }
                    errors.push_back(entry);
                    ++skipped;
                }
            }
            catch (const std::exception& ex)
            {
                errors.push_back({{"name", echoName}, {"error", "exception"},
                                  {"message", ex.what()}});
                ++skipped;
            }
        }

        if (redraw)
            pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["routed"] = routed;
        wr.data["skipped"] = skipped;
        wr.data["total"] = static_cast<int>(items.size());
        if (!errors.empty())
            wr.data["errors"] = std::move(errors);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/rename — Convenience rename endpoint ─────────────

void HandleLayerRename(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field (current layer name)");
        return;
    }
    if (!body.contains("newName") || !body["newName"].is_string())
    {
        CRookServer::SendError(res, "Missing 'newName' field");
        return;
    }

    std::string name = body["name"].get<std::string>();
    std::string newName = body["newName"].get<std::string>();

    try
    {
        ValidateNewLayerName(newName);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, newName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Rename Layer");

        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        const int idx = layerRef.index;
        const CRhinoLayer& layer = pDoc->m_layer_table[idx];

        // Check for duplicate sibling
        std::string parentPath;
        ON_UUID parentId = layer.ParentLayerId();
        if (!ON_UuidIsNil(parentId))
        {
            for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
            {
                if (!pDoc->m_layer_table[i].IsDeleted() &&
                    ON_UuidCompare(pDoc->m_layer_table[i].Id(), parentId) == 0)
                {
                    ON_wString pp;
                    pDoc->m_layer_table.GetLayerPathName(i, pp);
                    parentPath = WideToUtf8(pp);
                    break;
                }
            }
        }
        const std::string targetFullPath = JoinLayerPath(parentPath, newName);
        // Compare by layer index, not by path string: Rhino's lookup is
        // case-insensitive, so a case-only rename resolves to this same layer.
        const int existingIdx = FindLayerIndexByFullPath(pDoc, targetFullPath);
        if (existingIdx >= 0 && existingIdx != idx)
            throw std::invalid_argument("Cannot rename: layer '" + targetFullPath + "' already exists");

        ON_Layer layerCopy = pDoc->m_layer_table[idx];
        layerCopy.SetName(Utf8ToWide(newName));

        if (!pDoc->m_layer_table.ModifyLayer(layerCopy, idx))
            throw std::runtime_error("Failed to rename layer '" + name + "'");

        WriteResult wr;
        wr.success = true;
        wr.data = SerializeLayerAtIndex(pDoc, idx);
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/move-objects — Move all objects from source to target ──

void HandleLayerMoveObjects(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("source") || !body["source"].is_string())
    {
        CRookServer::SendError(res, "Missing 'source' layer name");
        return;
    }
    if (!body.contains("target") || !body["target"].is_string())
    {
        CRookServer::SendError(res, "Missing 'target' layer name");
        return;
    }

    std::string source = body["source"].get<std::string>();
    std::string target = body["target"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, source, target]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Move Objects Between Layers");

        const ResolvedLayerRef srcRef = ResolveLayerRef(pDoc, source, "source");
        const ResolvedLayerRef tgtRef = ResolveLayerRef(pDoc, target, "target");

        if (srcRef.index == tgtRef.index)
            throw std::invalid_argument("Source and target are the same layer");

        // "All objects" means every undeleted object on the source layer, as
        // in HandleLayerMerge: iterate undeleted_objects plus lights, not the
        // default normal_or_locked_objects. The default iterator skips hidden
        // objects, lights and — when the source layer is turned off — every
        // object on it, so the move used to report success and leave them
        // behind. Hidden objects stay hidden; only their layer changes.
        int moved = 0;
        int hiddenMoved = 0;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::undeleted_objects,
                CRhinoObjectIterator::active_objects);
            it.IncludeLights(true);
            for (CRhinoObject* obj = const_cast<CRhinoObject*>(it.First());
                 obj; obj = const_cast<CRhinoObject*>(it.Next()))
            {
                if (obj->Attributes().m_layer_index == srcRef.index)
                {
                    const bool wasHidden = (obj->Attributes().Mode() == ON::hidden_object);
                    CRhinoObjectAttributes attrs = obj->Attributes();
                    attrs.m_layer_index = tgtRef.index;
                    // bQuiet = true: a refusal must come back as an error,
                    // never as a message box that blocks Rhino's UI thread.
                    if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs, true))
                        throw std::runtime_error(
                            "Failed to move object '" + UuidToString(obj->Attributes().m_uuid) +
                            "' from '" + source + "' to '" + target +
                            "' (" + std::to_string(moved) + " moved before failure). "
                            "Use Ctrl+Z to undo partial changes.");
                    ++moved;
                    if (wasHidden)
                        ++hiddenMoved;
                }
            }
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["source"] = source;
        wr.data["target"] = target;
        wr.data["objectsMoved"] = moved;
        wr.data["hiddenObjectsMoved"] = hiddenMoved;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /layers/merge — Move objects from source to target, delete source ──

void HandleLayerMerge(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("source") || !body["source"].is_string())
    {
        CRookServer::SendError(res, "Missing 'source' layer name");
        return;
    }
    if (!body.contains("target") || !body["target"].is_string())
    {
        CRookServer::SendError(res, "Missing 'target' layer name");
        return;
    }

    std::string source = body["source"].get<std::string>();
    std::string target = body["target"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, source, target]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Merge Layers");

        const ResolvedLayerRef srcRef = ResolveLayerRef(pDoc, source, "source");
        const ResolvedLayerRef tgtRef = ResolveLayerRef(pDoc, target, "target");

        if (srcRef.index == tgtRef.index)
            throw std::invalid_argument("Source and target are the same layer");

        // Check: source is not the current layer
        if (pDoc->m_layer_table.CurrentLayerIndex() == srcRef.index)
            throw std::invalid_argument("Cannot merge the current layer — set a different current layer first");

        // Preflight: source has no child layers
        {
            ON_UUID srcId = pDoc->m_layer_table[srcRef.index].Id();
            for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
            {
                const CRhinoLayer& other = pDoc->m_layer_table[i];
                if (!other.IsDeleted() && ON_UuidCompare(other.ParentLayerId(), srcId) == 0)
                    throw std::invalid_argument("Cannot merge layer '" + source +
                        "': it has child layers. Move or merge children first.");
            }
        }

        // Preflight: no block definitions have geometry on the source layer
        // (block-owned geometry would prevent DeleteLayer and leave a partial mutation)
        {
            const CRhinoInstanceDefinitionTable& idefTable = pDoc->m_instance_definition_table;
            for (int d = 0; d < idefTable.InstanceDefinitionCount(); ++d)
            {
                const CRhinoInstanceDefinition* idef = idefTable[d];
                if (!idef || idef->IsDeleted()) continue;

                ON_SimpleArray<const CRhinoObject*> objArray;
                idef->GetObjects(objArray);
                for (int j = 0; j < objArray.Count(); ++j)
                {
                    if (objArray[j] && objArray[j]->Attributes().m_layer_index == srcRef.index)
                        throw std::invalid_argument(
                            "Cannot merge layer '" + source + "': block definition '" +
                            WideToUtf8(idef->Name()) + "' has geometry on this layer. "
                            "Use rhino_block_set_layers to remap block geometry first, or "
                            "use rhino_layer_dependencies to see all references.");
                }
            }
        }

        // Move all objects (preflight passed — delete will succeed).
        // Fail fast on first error to minimize partial state. The entire
        // operation is wrapped in UndoScope so Ctrl+Z reverts all changes
        // made before the throw.
        //
        // Iterate undeleted_objects plus lights, not the default
        // normal_or_locked_objects: hidden objects, lights and objects on a
        // source layer that is turned off also hold the layer, so leaving
        // them behind makes DeleteLayer refuse after the visible objects have
        // already moved. Hidden objects stay hidden; only their layer changes.
        int moved = 0;
        int hiddenMoved = 0;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::undeleted_objects,
                CRhinoObjectIterator::active_objects);
            it.IncludeLights(true);
            for (CRhinoObject* obj = const_cast<CRhinoObject*>(it.First());
                 obj; obj = const_cast<CRhinoObject*>(it.Next()))
            {
                if (obj->Attributes().m_layer_index == srcRef.index)
                {
                    const bool wasHidden = (obj->Attributes().Mode() == ON::hidden_object);
                    CRhinoObjectAttributes attrs = obj->Attributes();
                    attrs.m_layer_index = tgtRef.index;
                    if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
                        throw std::runtime_error(
                            "Failed to move object '" + UuidToString(obj->Attributes().m_uuid) +
                            "' from '" + source + "' to '" + target +
                            "' (" + std::to_string(moved) + " moved before failure). "
                            "Use Ctrl+Z to undo partial changes.");
                    ++moved;
                    if (wasHidden)
                        ++hiddenMoved;
                }
            }
        }

        // Delete the now-empty source layer
        if (!pDoc->m_layer_table.DeleteLayer(srcRef.index, true))
        {
            const std::string blockers = CollectLayerHolders(pDoc, srcRef.index).DescribeBlockers();
            throw std::runtime_error(
                "Objects moved but failed to delete source layer '" + source + "': " +
                (blockers.empty()
                    ? std::string("Rhino refused the delete although nothing was found holding the layer")
                    : blockers) +
                ". Use Ctrl+Z to undo the move.");
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["source"] = source;
        wr.data["target"] = target;
        wr.data["objectsMoved"] = moved;
        wr.data["hiddenObjectsMoved"] = hiddenMoved;
        wr.data["sourceDeleted"] = true;
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── GET /layers/dependencies — What holds a layer alive ────────────

void HandleLayerDependencies(const httplib::Request& req, httplib::Response& res)
{
    // Accept layer name from query param or body
    std::string name;
    if (req.has_param("name"))
    {
        name = req.get_param_value("name");
    }
    else if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.contains("name"))
            name = body["name"].get<std::string>();
    }

    if (name.empty())
    {
        CRookServer::SendError(res, "Missing 'name' parameter");
        return;
    }

    unsigned int docSn = 0;
    if (req.has_param("documentSerialNumber"))
    {
        try { docSn = static_cast<unsigned int>(std::stoul(req.get_param_value("documentSerialNumber"))); }
        catch (...) {}
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = nullptr;
        if (docSn > 0) pDoc = CRhinoDoc::FromRuntimeSerialNumber(docSn);
        if (!pDoc) pDoc = GetDocument();
        if (!pDoc) throw std::runtime_error("No active document");

        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        const int layerIdx = layerRef.index;

        // Same scan HandleDeleteLayer preflights with, so canDelete agrees
        // with what delete will actually do.
        const LayerHolders holders = CollectLayerHolders(pDoc, layerIdx);

        WriteResult wr;
        wr.success = true;
        wr.data["layer"] = name;
        // Every undeleted object on the layer: hidden objects, lights and
        // objects on a turned-off layer included.
        wr.data["directObjects"] = holders.objects;
        // Subset of directObjects in hidden mode. rhino_objects does not list
        // these, so their ids are returned here (first kMaxHiddenIds).
        wr.data["hiddenObjects"] = holders.hiddenObjects;
        wr.data["hiddenObjectTypes"] = nlohmann::json(holders.hiddenTypes);
        wr.data["hiddenObjectIds"] = holders.hiddenIds;
        // Subset of directObjects that are lights (also not listed by rhino_objects).
        wr.data["lightObjects"] = holders.lightObjects;
        wr.data["layerVisible"] = holders.layerVisible;
        // Objects in the deleted state that Rhino keeps for undo (deleted
        // objects and earlier versions of edited ones). Informational: they
        // do not block a delete and are not part of canDelete.
        wr.data["deletedObjectsInUndo"] = holders.deletedObjects;
        wr.data["childLayers"] = holders.childLayers;
        wr.data["blockReferences"] = holders.blockRefs;
        wr.data["isCurrentLayer"] = holders.isCurrent;
        wr.data["canDelete"] = holders.CanDelete();
        wr.data["blockers"] = holders.Blockers();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.error);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
