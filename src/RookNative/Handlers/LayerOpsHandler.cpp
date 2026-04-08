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

    snap.visible = layer.IsVisible();
    snap.locked = layer.IsLocked();

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

        if (body.contains("color"))
            layer.SetColor(ParseColor(body, "color"));

        if (!ON_UuidIsNil(parentId))
            layer.SetParentLayerId(parentId);

        if (body.contains("visible"))
            layer.SetVisible(body["visible"].get<bool>());

        if (body.contains("locked"))
            layer.SetLocked(body["locked"].get<bool>());

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

            if (item.spec.contains("color"))
                layer.SetColor(ParseColor(item.spec, "color"));
            if (item.spec.contains("visible"))
                layer.SetVisible(item.spec["visible"].get<bool>());
            if (item.spec.contains("locked"))
                layer.SetLocked(item.spec["locked"].get<bool>());

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

} // namespace Handlers
} // namespace Rook
