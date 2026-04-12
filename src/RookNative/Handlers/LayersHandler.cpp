// LayersHandler.cpp
//
// GET /layers — returns all non-deleted layers with metadata.

#include "stdafx.h"
#include "Handlers/LayersHandler.h"
#include "Models/Snapshots.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <unordered_map>

namespace Rook {
namespace Handlers {

struct LayersResult {
    std::vector<LayerSnapshot> layers;
    std::string currentLayer;
};

void HandleLayers(const httplib::Request& req, httplib::Response& res)
{
    // Parse documentSerialNumber from query params or body
    unsigned int docSn = 0;
    if (req.has_param("documentSerialNumber"))
    {
        try { docSn = static_cast<unsigned int>(std::stoul(req.get_param_value("documentSerialNumber"))); }
        catch (...) {}
    }
    if (docSn == 0 && !req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.contains("documentSerialNumber"))
            docSn = body.value("documentSerialNumber", 0u);
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch([docSn]() -> LayersResult
    {
        // Resolve document (cannot use thread-local g_request_doc_serial across threads)
        CRhinoDoc* pDoc = nullptr;
        if (docSn > 0)
            pDoc = CRhinoDoc::FromRuntimeSerialNumber(docSn);
        if (!pDoc)
            pDoc = GetDocument();
        if (!pDoc)
            throw std::runtime_error("No active document");

        LayersResult result;

        const int layerCount = pDoc->m_layer_table.LayerCount();
        result.layers.reserve(layerCount);

        // Pre-count objects per layer in a single pass (O(N) objects).
        std::unordered_map<int, int> objectsPerLayer;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
                objectsPerLayer[obj->Attributes().m_layer_index]++;
        }

        for (int i = 0; i < layerCount; ++i)
        {
            const CRhinoLayer& layer = pDoc->m_layer_table[i];
            if (layer.IsDeleted())
                continue;

            LayerSnapshot snap;
            snap.id = UuidToString(layer.Id());
            snap.index = i;
            snap.name = WideToUtf8(layer.Name());

            ON_wString fullPath;
            pDoc->m_layer_table.GetLayerPathName(i, fullPath);
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

            // Linetype: resolve index to name
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

            // Render material: resolve index to name
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
                snap.parentId.clear();  // serialized as null
            else
                snap.parentId = UuidToString(parentId);

            auto countIt = objectsPerLayer.find(i);
            snap.objectCount = (countIt != objectsPerLayer.end()) ? countIt->second : 0;

            result.layers.push_back(std::move(snap));
        }

        // Current layer
        int curIdx = pDoc->m_layer_table.CurrentLayerIndex();
        if (curIdx >= 0 && curIdx < layerCount)
        {
            ON_wString curPath;
            pDoc->m_layer_table.GetLayerPathName(curIdx, curPath);
            result.currentLayer = WideToUtf8(curPath);
        }
        else
        {
            result.currentLayer = "Default";
        }

        return result;
    });

    try
    {
        auto result = future.get();

        // Serialize on worker thread
        nlohmann::json layerArray = nlohmann::json::array();
        for (const auto& ls : result.layers)
            layerArray.push_back(Serializer::SerializeLayer(ls));

        nlohmann::json data;
        data["count"] = static_cast<int>(result.layers.size());
        data["currentLayer"] = result.currentLayer;
        data["layers"] = std::move(layerArray);

        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
