// LinetypesHandler.cpp
//
// GET  /linetypes       — List all linetypes with usage reporting
// POST /linetypes/purge — Purge unused linetypes

#include "stdafx.h"
#include "Handlers/LinetypesHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <unordered_map>

namespace Rook {
namespace Handlers {

// ─── GET /linetypes — List all linetypes with usage ─────────────────

void HandleGetLinetypes(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        int ltCount = pDoc->m_linetype_table.LinetypeCount();

        // Pre-compute usage: objects per linetype (single pass)
        std::unordered_map<int, int> objectsPerLinetype;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                int ltIdx = obj->Attributes().m_linetype_index;
                if (ltIdx >= 0)
                    objectsPerLinetype[ltIdx]++;
            }
        }

        // Pre-compute usage: layers per linetype (single pass)
        std::unordered_map<int, int> layersPerLinetype;
        for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
        {
            const CRhinoLayer& layer = pDoc->m_layer_table[i];
            if (layer.IsDeleted()) continue;
            int ltIdx = layer.LinetypeIndex();
            if (ltIdx >= 0)
                layersPerLinetype[ltIdx]++;
        }

        // Pre-compute usage: block definition objects per linetype
        std::unordered_map<int, int> blockObjsPerLinetype;
        const CRhinoInstanceDefinitionTable& idefTable = pDoc->m_instance_definition_table;
        for (int d = 0; d < idefTable.InstanceDefinitionCount(); ++d)
        {
            const CRhinoInstanceDefinition* idef = idefTable[d];
            if (!idef || idef->IsDeleted()) continue;

            ON_SimpleArray<const CRhinoObject*> objArray;
            idef->GetObjects(objArray);
            for (int j = 0; j < objArray.Count(); ++j)
            {
                if (!objArray[j]) continue;
                int ltIdx = objArray[j]->Attributes().m_linetype_index;
                if (ltIdx >= 0)
                    blockObjsPerLinetype[ltIdx]++;
            }
        }

        nlohmann::json linetypes = nlohmann::json::array();
        int activeCount = 0;

        for (int i = 0; i < ltCount; ++i)
        {
            const ON_Linetype& lt = pDoc->m_linetype_table[i];
            if (lt.IsDeleted()) continue;

            auto objIt = objectsPerLinetype.find(i);
            auto layIt = layersPerLinetype.find(i);
            auto blkIt = blockObjsPerLinetype.find(i);

            int objCount = (objIt != objectsPerLinetype.end()) ? objIt->second : 0;
            int layCount = (layIt != layersPerLinetype.end()) ? layIt->second : 0;
            int blkCount = (blkIt != blockObjsPerLinetype.end()) ? blkIt->second : 0;

            nlohmann::json j;
            j["index"] = i;
            j["name"] = WideToUtf8(lt.Name());
            j["usage"] = {
                {"objectCount", objCount},
                {"layerCount", layCount},
                {"blockDefinitionObjectCount", blkCount},
                {"totalReferences", objCount + layCount + blkCount},
                {"canPurge", (objCount + layCount + blkCount) == 0}
            };

            linetypes.push_back(std::move(j));
            ++activeCount;
        }

        nlohmann::json result;
        result["count"] = activeCount;
        result["linetypes"] = std::move(linetypes);
        return result;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /linetypes/purge — Purge unused linetypes ────────────────

void HandlePurgeLinetypes(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Purge Unused Linetypes");

        int ltCount = pDoc->m_linetype_table.LinetypeCount();

        // Compute usage for each linetype
        std::unordered_map<int, int> objectsPerLinetype;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                int ltIdx = obj->Attributes().m_linetype_index;
                if (ltIdx >= 0)
                    objectsPerLinetype[ltIdx]++;
            }
        }

        std::unordered_map<int, int> layersPerLinetype;
        for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
        {
            const CRhinoLayer& layer = pDoc->m_layer_table[i];
            if (layer.IsDeleted()) continue;
            int ltIdx = layer.LinetypeIndex();
            if (ltIdx >= 0)
                layersPerLinetype[ltIdx]++;
        }

        std::unordered_map<int, int> blockObjsPerLinetype;
        const CRhinoInstanceDefinitionTable& idefTable = pDoc->m_instance_definition_table;
        for (int d = 0; d < idefTable.InstanceDefinitionCount(); ++d)
        {
            const CRhinoInstanceDefinition* idef = idefTable[d];
            if (!idef || idef->IsDeleted()) continue;

            ON_SimpleArray<const CRhinoObject*> objArray;
            idef->GetObjects(objArray);
            for (int j = 0; j < objArray.Count(); ++j)
            {
                if (!objArray[j]) continue;
                int ltIdx = objArray[j]->Attributes().m_linetype_index;
                if (ltIdx >= 0)
                    blockObjsPerLinetype[ltIdx]++;
            }
        }

        // Collect purgeable linetypes (reverse order for safe deletion)
        nlohmann::json purged = nlohmann::json::array();
        nlohmann::json skipped = nlohmann::json::array();
        int purgedCount = 0;

        std::vector<int> toPurge;
        for (int i = 0; i < ltCount; ++i)
        {
            const ON_Linetype& lt = pDoc->m_linetype_table[i];
            if (lt.IsDeleted()) continue;

            auto objIt = objectsPerLinetype.find(i);
            auto layIt = layersPerLinetype.find(i);
            auto blkIt = blockObjsPerLinetype.find(i);

            int total = 0;
            if (objIt != objectsPerLinetype.end()) total += objIt->second;
            if (layIt != layersPerLinetype.end()) total += layIt->second;
            if (blkIt != blockObjsPerLinetype.end()) total += blkIt->second;

            std::string ltName = WideToUtf8(lt.Name());

            if (total == 0)
            {
                toPurge.push_back(i);
                purged.push_back(ltName);
            }
            else
            {
                nlohmann::json skip;
                skip["name"] = ltName;
                skip["reason"] = "In use (" + std::to_string(total) + " references)";
                skipped.push_back(std::move(skip));
            }
        }

        // Delete in reverse index order
        for (int j = static_cast<int>(toPurge.size()) - 1; j >= 0; --j)
        {
            if (pDoc->m_linetype_table.DeleteLinetype(toPurge[j], true))
                ++purgedCount;
        }

        WriteResult wr;
        wr.success = true;
        wr.data["purgedCount"] = purgedCount;
        wr.data["purged"] = std::move(purged);
        wr.data["skippedCount"] = static_cast<int>(skipped.size());
        wr.data["skipped"] = std::move(skipped);
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
