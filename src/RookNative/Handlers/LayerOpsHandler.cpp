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

namespace {

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
        if (ltIdx >= 0 && ltIdx >= pDoc->m_linetype_table.LinetypeCount())
            throw std::invalid_argument("linetypeIndex out of range");
        layer.SetLinetypeIndex(ltIdx);
    }

    if (spec.contains("material"))
    {
        const std::string matName = spec["material"].get<std::string>();
        int matIdx = pDoc->m_material_table.FindMaterial(Utf8ToWide(matName));
        if (matIdx < 0)
            throw std::invalid_argument("Material '" + matName + "' not found");
        layer.SetRenderMaterialIndex(matIdx);
    }
    else if (spec.contains("materialIndex"))
    {
        int matIdx = spec["materialIndex"].get<int>();
        if (matIdx >= 0 && matIdx >= pDoc->m_material_table.MaterialCount())
            throw std::invalid_argument("materialIndex out of range");
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
        pDoc->m_layer_table.ModifyLayer(layerCopy, idx);

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
        pDoc->m_layer_table.ModifyLayer(layerCopy, idx);

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

        // Rename (special — not in ApplyLayerProperties since it's name, not a display property)
        if (props.contains("rename"))
        {
            std::string newName = props["rename"].get<std::string>();
            ValidateNewLayerName(newName);
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
                layerCopy.SetParentLayerId(pDoc->m_layer_table[parentRef.index].Id());
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
                pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
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

        // Check: source has no child layers
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

        // Move all objects
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
                    pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
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
