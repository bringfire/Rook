// GameExportHandler.cpp
//
// Game export pipeline: semantic tagging, validation, .3dm + manifest export.
// Uses user strings for metadata, ONX_Model for .3dm writing.

#include "stdafx.h"
#include "Handlers/GameExportHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/PathValidation.h"
#include "Models/DocumentHelpers.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <filesystem>
#include <fstream>
#include <ctime>

namespace fs = std::filesystem;

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

struct LayerMapping {
    const wchar_t* keyword;
    const char* semanticType;
    const char* collision;
    bool nanite;
};

static const LayerMapping DefaultLayerMappings[] = {
    { L"Walls",      "wall",       "complex_as_simple",     true  },
    { L"Floors",     "floor",      "complex_as_simple",     true  },
    { L"Glazing",    "glass",      "box",                   true  },
    { L"Glass",      "glass",      "box",                   true  },
    { L"Columns",    "column",     "complex_as_simple",     true  },
    { L"Furniture",  "furniture",  "convex_decomposition",  true  },
    { L"Seating",    "furniture",  "convex_decomposition",  true  },
    { L"Landscape",  "landscape",  "complex_as_simple",     true  },
    { L"Terrain",    "landscape",  "complex_as_simple",     true  },
    { L"Doors",      "door",       "box",                   true  },
    { L"Stairs",     "stair",      "complex_as_simple",     true  },
    { L"Railing",    "railing",    "box",                   false },
};

// Get layer full path for an object
static ON_wString GetLayerPath(CRhinoDoc* pDoc, const CRhinoObject* obj)
{
    int layerIdx = obj->Attributes().m_layer_index;
    ON_wString fullPath;
    pDoc->m_layer_table.GetLayerPathName(layerIdx, fullPath);
    return fullPath;
}

// Resolve objects: by ids array, or all non-definition objects
static std::vector<const CRhinoObject*> ResolveObjects(CRhinoDoc* pDoc, const nlohmann::json& body)
{
    std::vector<const CRhinoObject*> result;

    if (body.contains("ids") && body["ids"].is_array())
    {
        for (const auto& el : body["ids"])
        {
            if (!el.is_string()) continue;
            ON_UUID uuid = ON_UuidFromString(el.get<std::string>().c_str());
            if (ON_UuidIsNil(uuid)) continue;
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (obj) result.push_back(obj);
        }
    }
    else
    {
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (!obj->Attributes().IsInstanceDefinitionObject())
                result.push_back(obj);
        }
    }
    return result;
}

// Build manifest JSON for export
static nlohmann::json BuildManifest(CRhinoDoc* pDoc, const std::string& filePath,
                                     const std::vector<const CRhinoObject*>& objects,
                                     const nlohmann::json& body)
{
    nlohmann::json manifest;
    manifest["version"] = "1.0";

    // Source info
    nlohmann::json source;
    source["rhinoVersion"] = "8";
    auto pathObj = fs::path(filePath);
    source["file"] = pathObj.filename().string();
    // UTC timestamp
    std::time_t now = std::time(nullptr);
    char timeBuf[64];
    struct tm tm_buf = {};
    gmtime_s(&tm_buf, &now);
    std::strftime(timeBuf, sizeof(timeBuf), "%Y-%m-%dT%H:%M:%SZ", &tm_buf);
    source["exportedAt"] = timeBuf;
    manifest["source"] = source;

    // Pass through optional settings/material_map/level_placement
    if (body.contains("settings")) manifest["settings"] = body["settings"];
    if (body.contains("material_map")) manifest["materialMap"] = body["material_map"];
    if (body.contains("level_placement")) manifest["levelPlacement"] = body["level_placement"];

    // Build object entries
    nlohmann::json objArray = nlohmann::json::array();
    for (const auto* obj : objects)
    {
        nlohmann::json entry;
        entry["rhinoUuid"] = UuidToString(obj->Attributes().m_uuid);

        ON_wString nameW = obj->Attributes().m_name;
        if (nameW.IsEmpty())
        {
            std::string uuidStr = UuidToString(obj->Attributes().m_uuid);
            entry["name"] = uuidStr.substr(0, 8);
        }
        else
        {
            entry["name"] = WideToUtf8(nameW);
        }

        entry["layer"] = WideToUtf8(GetLayerPath(pDoc, obj));

        // Read user strings
        ON_wString val;
        if (obj->Attributes().GetUserString(L"semantic_type", val) && !val.IsEmpty())
            entry["semanticType"] = WideToUtf8(val);
        if (obj->Attributes().GetUserString(L"collision", val) && !val.IsEmpty())
            entry["collision"] = WideToUtf8(val);
        if (obj->Attributes().GetUserString(L"nanite", val) && !val.IsEmpty())
            entry["nanite"] = (val.CompareNoCase(L"true") == 0);
        if (obj->Attributes().GetUserString(L"material_intent", val) && !val.IsEmpty())
        {
            auto parsed = nlohmann::json::parse(WideToUtf8(val), nullptr, false);
            if (!parsed.is_discarded())
                entry["materialIntent"] = parsed;
        }
        if (obj->Attributes().GetUserString(L"tags", val) && !val.IsEmpty())
        {
            nlohmann::json tags = nlohmann::json::array();
            std::string tagsStr = WideToUtf8(val);
            size_t pos = 0;
            while (pos < tagsStr.size())
            {
                size_t comma = tagsStr.find(',', pos);
                if (comma == std::string::npos) comma = tagsStr.size();
                std::string tag = tagsStr.substr(pos, comma - pos);
                // trim
                size_t start = tag.find_first_not_of(" \t");
                if (start != std::string::npos)
                {
                    size_t end = tag.find_last_not_of(" \t");
                    tags.push_back(tag.substr(start, end - start + 1));
                }
                pos = comma + 1;
            }
            entry["tags"] = tags;
        }

        objArray.push_back(entry);
    }
    manifest["objects"] = objArray;
    return manifest;
}

// Internal tag-from-layers logic (returns JSON result for composition)
static nlohmann::json DoTagFromLayers(CRhinoDoc* pDoc, const nlohmann::json& body)
{
    int taggedCount = 0;
    nlohmann::json matchedLayers = nlohmann::json::array();
    std::set<std::string> matchedSet;
    std::set<std::string> allLayerPaths;

    CRhinoObjectIterator it(*pDoc,
        CRhinoObjectIterator::normal_objects,
        CRhinoObjectIterator::active_objects);

    for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
    {
        if (obj->Attributes().IsInstanceDefinitionObject()) continue;

        ON_wString layerPath = GetLayerPath(pDoc, obj);
        std::string pathUtf8 = WideToUtf8(layerPath);
        allLayerPaths.insert(pathUtf8);

        // Tag-once: skip if already has semantic_type
        ON_wString existing;
        if (obj->Attributes().GetUserString(L"semantic_type", existing) && !existing.IsEmpty())
            continue;

        // Check against mappings (case-insensitive)
        ON_wString layerPathLower = layerPath;
        layerPathLower.MakeLower();
        for (const auto& m : DefaultLayerMappings)
        {
            ON_wString keyLower(m.keyword);
            keyLower.MakeLower();
            if (layerPathLower.Find(keyLower) >= 0)
            {
                ON_3dmObjectAttributes attrs = obj->Attributes();
                attrs.SetUserString(L"semantic_type", Utf8ToWide(m.semanticType));
                attrs.SetUserString(L"collision", Utf8ToWide(m.collision));
                attrs.SetUserString(L"nanite", m.nanite ? L"true" : L"false");
                pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
                taggedCount++;
                matchedSet.insert(pathUtf8);
                break;
            }
        }
    }

    nlohmann::json unmatchedLayers = nlohmann::json::array();
    for (const auto& p : allLayerPaths)
    {
        if (matchedSet.find(p) == matchedSet.end())
            unmatchedLayers.push_back(p);
    }
    for (const auto& p : matchedSet)
        matchedLayers.push_back(p);

    if (taggedCount > 0)
        pDoc->Redraw();

    nlohmann::json result;
    result["tagged_count"] = taggedCount;
    result["layers_matched"] = matchedLayers;
    result["unmatched_layers"] = unmatchedLayers;
    return result;
}

// Internal validate logic
static nlohmann::json DoValidate(CRhinoDoc* pDoc, const std::vector<const CRhinoObject*>& objects)
{
    nlohmann::json issues = nlohmann::json::array();
    bool hasWarnings = false;

    for (const auto* obj : objects)
    {
        const ON_Geometry* geom = obj->Geometry();
        if (!geom) continue;

        std::string objId = UuidToString(obj->Attributes().m_uuid);
        ON_wString nameW = obj->Attributes().m_name;
        std::string objName = nameW.IsEmpty() ? objId.substr(0, 8) : WideToUtf8(nameW);

        // Check Brep health
        if (const ON_Brep* brep = ON_Brep::Cast(geom))
        {
            if (!brep->IsManifold())
            {
                issues.push_back({{"id", objId}, {"name", objName},
                    {"severity", "warning"}, {"message", "Non-manifold Brep — may cause tessellation artifacts"}});
                hasWarnings = true;
            }
            if (!brep->IsSolid())
            {
                int nakedCount = 0;
                for (int i = 0; i < brep->m_E.Count(); ++i)
                {
                    if (brep->m_E[i].m_ti.Count() == 1)
                        nakedCount++;
                }
                if (nakedCount > 0)
                {
                    issues.push_back({{"id", objId}, {"name", objName},
                        {"severity", "warning"},
                        {"message", "Has " + std::to_string(nakedCount) + " naked edge(s) — geometry is not watertight"}});
                    hasWarnings = true;
                }
            }
        }

        // Check Mesh health
        if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        {
            if (!mesh->IsValid())
            {
                issues.push_back({{"id", objId}, {"name", objName},
                    {"severity", "warning"}, {"message", "Invalid mesh"}});
                hasWarnings = true;
            }
        }

        // Check material
        if (obj->Attributes().m_material_index < 0)
        {
            issues.push_back({{"id", objId}, {"name", objName},
                {"severity", "info"}, {"message", "No material assigned"}});
        }

        // Check semantic_type
        ON_wString semType;
        if (!obj->Attributes().GetUserString(L"semantic_type", semType) || semType.IsEmpty())
        {
            issues.push_back({{"id", objId}, {"name", objName},
                {"severity", "info"}, {"message", "No semantic_type set — consider running tag-from-layers first"}});
        }
    }

    nlohmann::json result;
    result["valid"] = !hasWarnings;
    result["object_count"] = static_cast<int>(objects.size());
    result["issues"] = issues;
    return result;
}

static WriteResult DoExportWithManifest(
    CRhinoDoc* pDoc,
    const nlohmann::json& body,
    const std::string& filePath)
{
    auto objects = ResolveObjects(pDoc, body);
    if (objects.empty())
        throw std::invalid_argument("No objects to export");

    nlohmann::json manifest = BuildManifest(pDoc, filePath, objects, body);

    auto pathObj = fs::path(filePath);
    auto manifestPath = pathObj.parent_path() /
        (pathObj.stem().string() + "_manifest.json");

    std::string manifestJson = manifest.dump(2);
    std::ofstream mf(manifestPath);
    if (!mf)
        throw std::runtime_error("Failed to write manifest file");
    mf << manifestJson;
    mf.close();

    ONX_Model model;

    std::set<int> usedLayerIndices;
    std::set<int> usedMaterialIndices;
    for (const auto* obj : objects)
    {
        usedLayerIndices.insert(obj->Attributes().m_layer_index);
        if (obj->Attributes().m_material_index >= 0)
            usedMaterialIndices.insert(obj->Attributes().m_material_index);
    }

    for (int layerIndex : usedLayerIndices)
    {
        const CRhinoLayer& layer = pDoc->m_layer_table[layerIndex];
        if (!layer.IsDeleted())
            model.AddModelComponent(layer, true);
    }

    for (int materialIndex : usedMaterialIndices)
    {
        const CRhinoMaterial& material = pDoc->m_material_table[materialIndex];
        if (!material.IsDeleted())
            model.AddModelComponent(material, true);
    }

    for (const auto* obj : objects)
    {
        const ON_Object* geometry = obj->Geometry();
        if (nullptr == geometry)
            continue;

        std::unique_ptr<ON_Object> geometryCopy(geometry->Duplicate());
        if (!geometryCopy)
            continue;

        std::unique_ptr<ON_3dmObjectAttributes> attrsCopy(new ON_3dmObjectAttributes(obj->Attributes()));
        model.AddManagedModelGeometryComponent(
            geometryCopy.release(),
            attrsCopy.release(),
            true);
    }

    ON_wString wFilePath = Utf8ToWide(filePath);
    const bool writeOk = model.Write(static_cast<const wchar_t*>(wFilePath), 0, nullptr);
    if (!writeOk || !fs::exists(filePath))
    {
        fs::remove(manifestPath);
        WriteResult wr;
        wr.success = false;
        wr.data["error"] = "Failed to write .3dm file";
        return wr;
    }

    auto fileSize = fs::file_size(filePath);

    int taggedCount = 0;
    for (const auto* obj : objects)
    {
        ON_wString val;
        if (obj->Attributes().GetUserString(L"semantic_type", val) && !val.IsEmpty())
            taggedCount++;
    }

    WriteResult wr;
    wr.success = true;
    wr.data["export_path"] = filePath;
    wr.data["manifest_path"] = manifestPath.string();
    wr.data["object_count"] = static_cast<int>(objects.size());
    wr.data["file_size"] = static_cast<int64_t>(fileSize);
    wr.data["manifest_summary"] = {
        {"version", manifest.value("version", "1.0")},
        {"objects_with_semantic_type", taggedCount}
    };
    return wr;
}

// ─── POST /game-export/tag ──────────────────────────────────────

void HandleGameExportTag(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    // Extract optional tag values
    std::string semanticType = body.value("semantic_type", std::string());
    std::string collision = body.value("collision", std::string());
    std::string materialIntentJson;
    if (body.contains("material_intent"))
        materialIntentJson = body["material_intent"].dump();
    bool hasNanite = body.contains("nanite");
    bool naniteVal = body.value("nanite", false);
    std::string tagsStr;
    if (body.contains("tags") && body["tags"].is_array())
    {
        for (size_t i = 0; i < body["tags"].size(); ++i)
        {
            if (i > 0) tagsStr += ",";
            tagsStr += body["tags"][i].get<std::string>();
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids, semanticType, collision, hasNanite, naniteVal,
         materialIntentJson, tagsStr]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Game export tag");

        int taggedCount = 0;
        nlohmann::json objects = nlohmann::json::array();

        for (const auto& uuid : ids)
        {
            std::string idStr = UuidToString(uuid);
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj)
            {
                objects.push_back({{"id", idStr}, {"error", "not found"}});
                continue;
            }

            nlohmann::json keysSet = nlohmann::json::array();
            ON_3dmObjectAttributes attrs = obj->Attributes();

            if (!semanticType.empty())
            {
                attrs.SetUserString(L"semantic_type", Utf8ToWide(semanticType));
                keysSet.push_back("semantic_type");
            }
            if (!collision.empty())
            {
                attrs.SetUserString(L"collision", Utf8ToWide(collision));
                keysSet.push_back("collision");
            }
            if (hasNanite)
            {
                attrs.SetUserString(L"nanite", naniteVal ? L"true" : L"false");
                keysSet.push_back("nanite");
            }
            if (!materialIntentJson.empty())
            {
                attrs.SetUserString(L"material_intent", Utf8ToWide(materialIntentJson));
                keysSet.push_back("material_intent");
            }
            if (!tagsStr.empty())
            {
                attrs.SetUserString(L"tags", Utf8ToWide(tagsStr));
                keysSet.push_back("tags");
            }

            pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
            taggedCount++;
            objects.push_back({{"id", idStr}, {"keys_set", keysSet}});
        }

        WriteResult wr;
        wr.success = true;
        wr.data["tagged_count"] = taggedCount;
        wr.data["objects"] = objects;
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

// ─── POST /game-export/tag-from-layers ──────────────────────────

void HandleGameExportTagFromLayers(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Tag from layers");

        nlohmann::json result = DoTagFromLayers(pDoc, body);

        WriteResult wr;
        wr.success = true;
        wr.data = result;
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /game-export/validate ─────────────────────────────────

void HandleGameExportValidate(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        auto objects = ResolveObjects(pDoc, body);
        if (objects.empty())
            throw std::invalid_argument("No objects to validate");

        WriteResult wr;
        wr.success = true;
        wr.data = DoValidate(pDoc, objects);
        return wr;
    });

    try
    {
        auto result = future.get();
        CRookServer::SendSuccess(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /game-export/export ───────────────────────────────────

void HandleGameExportExport(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("path") || !body["path"].is_string())
    {
        CRookServer::SendError(res, "Missing 'path' string");
        return;
    }

    std::string filePath = body["path"].get<std::string>();

    std::string pathErr = Rook::ValidateFilePath(filePath);
    if (!pathErr.empty())
    {
        CRookServer::SendError(res, pathErr);
        return;
    }

    // Ensure .3dm extension
    if (filePath.size() < 4 ||
        filePath.substr(filePath.size() - 4) != ".3dm")
        filePath += ".3dm";

    // Ensure directory exists
    auto dir = fs::path(filePath).parent_path();
    if (!dir.empty())
        fs::create_directories(dir);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, filePath]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        return DoExportWithManifest(pDoc, body, filePath);
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

// ─── POST /game-export/prepare ──────────────────────────────────

void HandleGameExportPrepare(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("path") || !body["path"].is_string())
    {
        CRookServer::SendError(res, "Missing 'path' string");
        return;
    }

    std::string filePath = body["path"].get<std::string>();

    std::string pathErr = Rook::ValidateFilePath(filePath);
    if (!pathErr.empty())
    {
        CRookServer::SendError(res, pathErr);
        return;
    }

    if (filePath.size() < 4 ||
        filePath.substr(filePath.size() - 4) != ".3dm")
        filePath += ".3dm";

    auto dir = fs::path(filePath).parent_path();
    if (!dir.empty())
        fs::create_directories(dir);

    bool skipTagging = body.value("skip_tagging", false);
    bool skipValidation = body.value("skip_validation", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, body, filePath, skipTagging, skipValidation]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        nlohmann::json taggingResult = nullptr;
        if (!skipTagging)
            taggingResult = DoTagFromLayers(pDoc, body);

        nlohmann::json validationResult = nullptr;
        if (!skipValidation)
        {
            auto objects = ResolveObjects(pDoc, body);
            if (objects.empty())
                throw std::invalid_argument("No objects to export");
            validationResult = DoValidate(pDoc, objects);
        }

        WriteResult exportResult = DoExportWithManifest(pDoc, body, filePath);

        WriteResult wr;
        wr.success = exportResult.success;
        wr.data["tagging_result"] = taggingResult;
        wr.data["validation_result"] = validationResult;
        wr.data["export_result"] = exportResult.data;
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

} // namespace Handlers
} // namespace Rook
