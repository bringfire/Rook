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

        nlohmann::json materials = nlohmann::json::array();
        int count = pDoc->m_material_table.MaterialCount();
        int activeCount = 0;

        for (int i = 0; i < count; ++i)
        {
            const CRhinoMaterial& mat = pDoc->m_material_table[i];
            if (mat.IsDeleted()) continue;

            materials.push_back(SerializeMaterial(pDoc, i));
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

} // namespace Handlers
} // namespace Rook
