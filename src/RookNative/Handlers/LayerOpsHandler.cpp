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
#include <unordered_map>
#include <unordered_set>
#include <vector>

using Rook::Infrastructure::ResolvedLayerRef;
using Rook::Infrastructure::GetLayerFullPath;
using Rook::Infrastructure::JoinLayerPath;
using Rook::Infrastructure::ContainsPathSeparator;
using Rook::Infrastructure::LayerExistsByFullPath;
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

// Validate that a JSON value is a 3-element [r,g,b] integer array with values 0-255.
// Permissive about numeric clamping at parse time (ParseColor does its own coercion);
// this check is strictly for pre-classification of shape errors in the batch path.
bool IsValidRgbArray(const nlohmann::json& val)
{
    if (!val.is_array() || val.size() < 3) return false;
    for (size_t i = 0; i < 3; ++i)
    {
        if (!val[i].is_number_integer()) return false;
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
    std::string targetFullPathBefore;
    try
    {
        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        idx = layerRef.index;
        targetFullPathBefore = layerRef.fullPath;
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

    // ---- Rename + collision check (must run after parent resolution so
    //      the collision check uses the target's final parent path)
    if (setProps.contains("rename"))
    {
        const std::string newName = setProps["rename"].get<std::string>();
        // ValidateNewLayerName throws on bad names; we've already pre-validated
        // the shape, so any throw here is an unexpected case → exception.
        try { ValidateNewLayerName(newName); }
        catch (const std::exception& ex) { return MakeLayerFailure("invalid_rename", ex.what()); }

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
        const std::string targetFullPath = JoinLayerPath(parentPath, newName);
        if (LayerExistsByFullPath(pDoc, targetFullPath) &&
            targetFullPath != targetFullPathBefore)
        {
            return MakeLayerFailure("name_collision",
                "Layer '" + targetFullPath + "' already exists");
        }

        layerCopy.SetName(Utf8ToWide(newName));
    }

    // ---- Apply parent
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

    // Object count: quick scan (acceptable for single-layer response)
    snap.objectCount = 0;
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (obj->Attributes().m_layer_index == layerIndex)
                ++snap.objectCount;
        }
    }

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

        // Check for objects on layer
        {
            int objCount = 0;
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->Attributes().m_layer_index == layerIdx)
                    ++objCount;
            }
            if (objCount > 0)
                throw std::invalid_argument("Cannot delete layer '" + name +
                    "': layer contains " + std::to_string(objCount) + " objects");
        }

        // Check if current layer
        if (pDoc->m_layer_table.CurrentLayerIndex() == layerIdx)
            throw std::invalid_argument("Cannot delete layer '" + name +
                "': it is the current layer");

        // Check for child layers
        {
            ON_UUID layerId = layer.Id();
            int childCount = 0;
            for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
            {
                const CRhinoLayer& other = pDoc->m_layer_table[i];
                if (other.IsDeleted())
                    continue;
                if (ON_UuidCompare(other.ParentLayerId(), layerId) == 0)
                    ++childCount;
            }
            if (childCount > 0)
                throw std::invalid_argument("Cannot delete layer '" + name +
                    "': layer has " + std::to_string(childCount) + " child layer(s)");
        }

        if (!pDoc->m_layer_table.DeleteLayer(layerIdx, true))
            throw std::runtime_error("Failed to delete layer '" + name + "'");

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

        const ResolvedLayerRef layerRef = ResolveLayerRef(pDoc, name, "name");
        const int idx = layerRef.index;

        ON_Layer layerCopy = pDoc->m_layer_table[idx];
        const ON_UUID layerId = layerCopy.Id();

        // Rename (special — not in ApplyLayerProperties since it's name, not a display property)
        if (props.contains("rename"))
        {
            std::string newName = props["rename"].get<std::string>();
            ValidateNewLayerName(newName);

            // Check for duplicate sibling: compute target full path and verify it doesn't exist
            ON_UUID parentId = layerCopy.ParentLayerId();
            // If reparent is also happening, use the new parent for collision check
            if (props.contains("parent") && !props["parent"].is_null())
            {
                const ResolvedLayerRef newParentRef = ResolveLayerRef(pDoc, props["parent"].get<std::string>(), "parent");
                parentId = pDoc->m_layer_table[newParentRef.index].Id();
            }
            else if (props.contains("parent") && props["parent"].is_null())
            {
                parentId = ON_nil_uuid;
            }

            std::string parentPath;
            if (!ON_UuidIsNil(parentId))
            {
                // Find parent index to get its full path
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
            if (LayerExistsByFullPath(pDoc, targetFullPath))
            {
                // Allow if it's the same layer (no-op rename to same name)
                if (targetFullPath != layerRef.fullPath)
                    throw std::invalid_argument("Cannot rename: layer '" + targetFullPath + "' already exists");
            }

            layerCopy.SetName(Utf8ToWide(newName));
        }

        // Reparent
        if (props.contains("parent"))
        {
            if (props["parent"].is_null())
            {
                layerCopy.SetParentLayerId(ON_nil_uuid);
            }
            else
            {
                std::string parentName = props["parent"].get<std::string>();
                const ResolvedLayerRef parentRef = ResolveLayerRef(pDoc, parentName, "parent");
                ON_UUID newParentId = pDoc->m_layer_table[parentRef.index].Id();

                // Cycle detection: walk up from proposed parent to root,
                // verify the target layer is not an ancestor
                if (ON_UuidCompare(newParentId, layerId) == 0)
                    throw std::invalid_argument("Cannot reparent layer under itself");

                ON_UUID walkId = newParentId;
                while (!ON_UuidIsNil(walkId))
                {
                    // Find the layer with this ID
                    bool found = false;
                    for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
                    {
                        const CRhinoLayer& walkLayer = pDoc->m_layer_table[i];
                        if (walkLayer.IsDeleted()) continue;
                        if (ON_UuidCompare(walkLayer.Id(), walkId) == 0)
                        {
                            walkId = walkLayer.ParentLayerId();
                            if (ON_UuidCompare(walkId, layerId) == 0)
                                throw std::invalid_argument(
                                    "Cannot reparent: '" + parentName +
                                    "' is a descendant of '" + name + "' (would create a cycle)");
                            found = true;
                            break;
                        }
                    }
                    if (!found) break;
                }

                layerCopy.SetParentLayerId(newParentId);
            }
        }

        // Apply all standard display/render properties
        ApplyLayerProperties(layerCopy, props, pDoc);

        if (!pDoc->m_layer_table.ModifyLayer(layerCopy, idx))
            throw std::runtime_error("Failed to modify layer '" + name + "'");

        pDoc->Redraw();

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
        if (LayerExistsByFullPath(pDoc, targetFullPath) && targetFullPath != layerRef.fullPath)
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

        int moved = 0;
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (CRhinoObject* obj = const_cast<CRhinoObject*>(it.First());
             obj; obj = const_cast<CRhinoObject*>(it.Next()))
        {
            if (obj->Attributes().m_layer_index == srcRef.index)
            {
                CRhinoObjectAttributes attrs = obj->Attributes();
                attrs.m_layer_index = tgtRef.index;
                if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
                    throw std::runtime_error(
                        "Failed to move object '" + UuidToString(obj->Attributes().m_uuid) +
                        "' from '" + source + "' to '" + target +
                        "' (" + std::to_string(moved) + " moved before failure). "
                        "Use Ctrl+Z to undo partial changes.");
                ++moved;
            }
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["source"] = source;
        wr.data["target"] = target;
        wr.data["objectsMoved"] = moved;
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
        int moved = 0;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (CRhinoObject* obj = const_cast<CRhinoObject*>(it.First());
                 obj; obj = const_cast<CRhinoObject*>(it.Next()))
            {
                if (obj->Attributes().m_layer_index == srcRef.index)
                {
                    CRhinoObjectAttributes attrs = obj->Attributes();
                    attrs.m_layer_index = tgtRef.index;
                    if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
                        throw std::runtime_error(
                            "Failed to move object '" + UuidToString(obj->Attributes().m_uuid) +
                            "' from '" + source + "' to '" + target +
                            "' (" + std::to_string(moved) + " moved before failure). "
                            "Use Ctrl+Z to undo partial changes.");
                    ++moved;
                }
            }
        }

        // Delete the now-empty source layer
        if (!pDoc->m_layer_table.DeleteLayer(srcRef.index, true))
            throw std::runtime_error("Objects moved but failed to delete source layer '" + source + "'");

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["source"] = source;
        wr.data["target"] = target;
        wr.data["objectsMoved"] = moved;
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
        const ON_UUID layerId = pDoc->m_layer_table[layerIdx].Id();

        // Count direct objects
        int directObjects = 0;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->Attributes().m_layer_index == layerIdx)
                    ++directObjects;
            }
        }

        // Count child layers
        nlohmann::json childLayers = nlohmann::json::array();
        for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
        {
            const CRhinoLayer& other = pDoc->m_layer_table[i];
            if (other.IsDeleted()) continue;
            if (ON_UuidCompare(other.ParentLayerId(), layerId) == 0)
            {
                ON_wString childPath;
                pDoc->m_layer_table.GetLayerPathName(i, childPath);
                childLayers.push_back(WideToUtf8(childPath));
            }
        }

        // Scan block definitions for geometry on this layer
        nlohmann::json blockRefs = nlohmann::json::array();
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
                blockRefs.push_back(std::move(ref));
            }
        }

        bool isCurrentLayer = (pDoc->m_layer_table.CurrentLayerIndex() == layerIdx);
        bool canDelete = (directObjects == 0) && childLayers.empty() &&
                         blockRefs.empty() && !isCurrentLayer;

        WriteResult wr;
        wr.success = true;
        wr.data["layer"] = name;
        wr.data["directObjects"] = directObjects;
        wr.data["childLayers"] = std::move(childLayers);
        wr.data["blockReferences"] = std::move(blockRefs);
        wr.data["isCurrentLayer"] = isCurrentLayer;
        wr.data["canDelete"] = canDelete;
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
