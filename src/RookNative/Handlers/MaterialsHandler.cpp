// MaterialsHandler.cpp
//
// GET    /materials        — List all materials
// POST   /materials        — Create a material
// DELETE /materials        — Delete a material
// POST   /materials/assign — Assign material to object(s) or layer

#include "stdafx.h"
#include "Handlers/MaterialsHandler.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// Find material by name (case-insensitive). Returns index or -1.
static int FindMaterialIndex(CRhinoDoc* pDoc, const std::string& name)
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

// Serialize a material at a given index to JSON.
static nlohmann::json SerializeMaterial(CRhinoDoc* pDoc, int matIndex)
{
    const CRhinoMaterial& mat = pDoc->m_material_table[matIndex];

    ON_Color dc = mat.Diffuse();
    ON_Color sc = mat.Specular();
    ON_Color ec = mat.Emission();

    nlohmann::json j;
    j["index"] = matIndex;
    j["id"] = UuidToString(mat.Id());
    j["name"] = WideToUtf8(mat.Name());
    j["diffuseColor"] = { static_cast<int>(dc.Red()), static_cast<int>(dc.Green()), static_cast<int>(dc.Blue()) };
    j["specularColor"] = { static_cast<int>(sc.Red()), static_cast<int>(sc.Green()), static_cast<int>(sc.Blue()) };
    j["emissionColor"] = { static_cast<int>(ec.Red()), static_cast<int>(ec.Green()), static_cast<int>(ec.Blue()) };
    j["reflectivity"] = mat.Reflectivity();
    j["transparency"] = mat.Transparency();
    j["shine"] = mat.Shine();
    j["hasTexture"] = (mat.TextureBitmap() != nullptr);
    return j;
}

// ─── GET /materials ─────────────────────────────────────────────────

void HandleGetMaterials(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        int matCount = pDoc->m_material_table.MaterialCount();

        // Pre-compute usage: objects per material (single pass over objects)
        std::unordered_map<int, int> objectsPerMaterial;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                const auto& attrs = obj->Attributes();
                if (attrs.MaterialSource() == ON::material_from_object && attrs.m_material_index >= 0)
                    objectsPerMaterial[attrs.m_material_index]++;
            }
        }

        // Pre-compute usage: layers per material (single pass over layers)
        std::unordered_map<int, int> layersPerMaterial;
        for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
        {
            const CRhinoLayer& layer = pDoc->m_layer_table[i];
            if (layer.IsDeleted()) continue;
            int matIdx = layer.RenderMaterialIndex();
            if (matIdx >= 0)
                layersPerMaterial[matIdx]++;
        }

        // Pre-compute usage: block definition objects per material
        std::unordered_map<int, int> blockObjsPerMaterial;
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
                const auto& attrs = objArray[j]->Attributes();
                if (attrs.MaterialSource() == ON::material_from_object && attrs.m_material_index >= 0)
                    blockObjsPerMaterial[attrs.m_material_index]++;
            }
        }

        nlohmann::json materials = nlohmann::json::array();
        int activeCount = 0;

        for (int i = 0; i < matCount; ++i)
        {
            const CRhinoMaterial& mat = pDoc->m_material_table[i];
            if (mat.IsDeleted()) continue;

            nlohmann::json j = SerializeMaterial(pDoc, i);

            // Usage reporting
            auto objIt = objectsPerMaterial.find(i);
            auto layIt = layersPerMaterial.find(i);
            auto blkIt = blockObjsPerMaterial.find(i);

            int objCount = (objIt != objectsPerMaterial.end()) ? objIt->second : 0;
            int layCount = (layIt != layersPerMaterial.end()) ? layIt->second : 0;
            int blkCount = (blkIt != blockObjsPerMaterial.end()) ? blkIt->second : 0;

            j["usage"] = {
                {"objectCount", objCount},
                {"layerCount", layCount},
                {"blockDefinitionObjectCount", blkCount},
                {"totalReferences", objCount + layCount + blkCount},
                {"canPurge", (objCount + layCount + blkCount) == 0}
            };

            materials.push_back(std::move(j));
            ++activeCount;
        }

        nlohmann::json result;
        result["count"] = activeCount;
        result["materials"] = std::move(materials);
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

// ─── POST /materials ────────────────────────────────────────────────

void HandleCreateMaterial(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field (string)");
        return;
    }

    std::string name = body["name"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create Material");

        // Check if material already exists
        int existing = FindMaterialIndex(pDoc, name);
        if (existing >= 0)
            throw std::invalid_argument("Material '" + name + "' already exists");

        // Build material
        ON_Material mat;
        mat.SetName(Utf8ToWide(name));

        if (body.contains("color"))
            mat.SetDiffuse(ParseColor(body, "color"));

        if (body.contains("specularColor"))
            mat.SetSpecular(ParseColor(body, "specularColor"));

        if (body.contains("emissionColor"))
            mat.SetEmission(ParseColor(body, "emissionColor"));

        if (body.contains("reflectivity"))
            mat.SetReflectivity(body["reflectivity"].get<double>());

        if (body.contains("transparency"))
            mat.SetTransparency(body["transparency"].get<double>());

        if (body.contains("shine"))
            mat.SetShine(body["shine"].get<double>());

        int newIdx = pDoc->m_material_table.AddMaterial(mat);
        if (newIdx < 0)
            throw std::runtime_error("Failed to create material");

        WriteResult wr;
        wr.success = true;
        wr.data = SerializeMaterial(pDoc, newIdx);
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

// ─── DELETE /materials ──────────────────────────────────────────────

void HandleDeleteMaterial(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("name") || !body["name"].is_string())
    {
        CRookServer::SendError(res, "Missing 'name' field (string)");
        return;
    }

    std::string name = body["name"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Delete Material");

        int matIdx = FindMaterialIndex(pDoc, name);
        if (matIdx < 0)
            throw std::invalid_argument("Material '" + name + "' not found");

        if (!pDoc->m_material_table.DeleteMaterial(matIdx))
            throw std::runtime_error("Failed to delete material '" + name + "'");

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

// ─── POST /materials/assign ─────────────────────────────────────────

void HandleAssignMaterial(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("material") || !body["material"].is_string())
    {
        CRookServer::SendError(res, "Missing 'material' field (string)");
        return;
    }

    std::string materialName = body["material"].get<std::string>();

    // Collect object IDs (from "id" or "ids")
    std::vector<ON_UUID> ids;
    try
    {
        if (body.contains("ids"))
            ids = ParseUuids(body, "ids");
        else if (body.contains("id"))
            ids.push_back(ParseUuid(body, "id"));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string layerName;
    if (body.contains("layer") && body["layer"].is_string())
        layerName = body["layer"].get<std::string>();

    if (ids.empty() && layerName.empty())
    {
        CRookServer::SendError(res, "Must provide 'id', 'ids', or 'layer'");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, materialName, ids = std::move(ids), layerName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Assign Material");

        int matIdx = FindMaterialIndex(pDoc, materialName);
        if (matIdx < 0)
            throw std::invalid_argument("Material '" + materialName + "' not found");

        int assignedCount = 0;

        // Assign to specific objects
        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) continue;

            ON_3dmObjectAttributes attrs = obj->Attributes();
            attrs.SetMaterialSource(ON::material_from_object);
            attrs.m_material_index = matIdx;
            pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
            ++assignedCount;
        }

        // Assign to layer
        if (!layerName.empty())
        {
            const int layerIdx = Rook::Infrastructure::ResolveLayerRef(
                pDoc, layerName, "layer").index;

            ON_Layer layerCopy = pDoc->m_layer_table[layerIdx];
            layerCopy.SetRenderMaterialIndex(matIdx);
            pDoc->m_layer_table.ModifyLayer(layerCopy, layerIdx);
            ++assignedCount;
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["material"] = materialName;
        wr.data["assignedCount"] = assignedCount;
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

// ─── POST /materials/purge — Purge unused materials ─────────────────

void HandlePurgeMaterials(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Purge Unused Materials");

        int matCount = pDoc->m_material_table.MaterialCount();

        // Compute usage (same logic as GET /materials)
        std::unordered_map<int, int> objectsPerMaterial;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                const auto& attrs = obj->Attributes();
                if (attrs.MaterialSource() == ON::material_from_object && attrs.m_material_index >= 0)
                    objectsPerMaterial[attrs.m_material_index]++;
            }
        }

        std::unordered_map<int, int> layersPerMaterial;
        for (int i = 0; i < pDoc->m_layer_table.LayerCount(); ++i)
        {
            const CRhinoLayer& layer = pDoc->m_layer_table[i];
            if (layer.IsDeleted()) continue;
            int matIdx = layer.RenderMaterialIndex();
            if (matIdx >= 0)
                layersPerMaterial[matIdx]++;
        }

        std::unordered_map<int, int> blockObjsPerMaterial;
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
                const auto& attrs = objArray[j]->Attributes();
                if (attrs.MaterialSource() == ON::material_from_object && attrs.m_material_index >= 0)
                    blockObjsPerMaterial[attrs.m_material_index]++;
            }
        }

        // Collect purgeable materials
        nlohmann::json purged = nlohmann::json::array();
        nlohmann::json skipped = nlohmann::json::array();
        int purgedCount = 0;

        std::vector<int> toPurge;
        for (int i = 0; i < matCount; ++i)
        {
            const CRhinoMaterial& mat = pDoc->m_material_table[i];
            if (mat.IsDeleted()) continue;

            auto objIt = objectsPerMaterial.find(i);
            auto layIt = layersPerMaterial.find(i);
            auto blkIt = blockObjsPerMaterial.find(i);

            int objCount = (objIt != objectsPerMaterial.end()) ? objIt->second : 0;
            int layCount = (layIt != layersPerMaterial.end()) ? layIt->second : 0;
            int blkCount = (blkIt != blockObjsPerMaterial.end()) ? blkIt->second : 0;
            int total = objCount + layCount + blkCount;

            std::string matName = WideToUtf8(mat.Name());

            if (total == 0)
            {
                toPurge.push_back(i);
            }
            else
            {
                nlohmann::json skip;
                skip["name"] = matName;
                nlohmann::json reasons = nlohmann::json::array();
                if (objCount > 0)
                    reasons.push_back(std::to_string(objCount) + " object(s)");
                if (layCount > 0)
                    reasons.push_back(std::to_string(layCount) + " layer(s)");
                if (blkCount > 0)
                    reasons.push_back(std::to_string(blkCount) + " block definition object(s)");
                skip["reasons"] = std::move(reasons);
                skipped.push_back(std::move(skip));
            }
        }

        // Delete in reverse index order; only report as purged after success
        for (int j = static_cast<int>(toPurge.size()) - 1; j >= 0; --j)
        {
            std::string name = WideToUtf8(pDoc->m_material_table[toPurge[j]].Name());
            if (pDoc->m_material_table.DeleteMaterial(toPurge[j]))
            {
                purged.push_back(name);
                ++purgedCount;
            }
            else
            {
                nlohmann::json skip;
                skip["name"] = name;
                skip["reasons"] = nlohmann::json::array({"Delete failed"});
                skipped.push_back(std::move(skip));
            }
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
