// ImportExportHandler.cpp
//
// POST /import — Import geometry from file
// POST /export — Export geometry to file

#include "stdafx.h"
#include "Handlers/ImportExportHandler.h"
#include "Infrastructure/LayerHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/PathValidation.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <filesystem>

namespace fs = std::filesystem;

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static std::string GetExtension(const std::string& path)
{
    auto ext = fs::path(path).extension().string();
    // lowercase
    for (auto& c : ext)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return ext; // includes the dot: ".3dm", ".obj", etc.
}

// ─── POST /import ───────────────────────────────────────────────────

void HandleImport(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("path") || !body["path"].is_string())
    {
        CRookServer::SendError(res, "Missing 'path' field (string)");
        return;
    }

    std::string path = body["path"].get<std::string>();
    std::string targetLayer;
    if (body.contains("targetLayer") && body["targetLayer"].is_string())
        targetLayer = body["targetLayer"].get<std::string>();

    std::string pathErr = Rook::ValidateFilePath(path);
    if (!pathErr.empty())
    {
        CRookServer::SendError(res, pathErr);
        return;
    }

    if (!fs::exists(path))
    {
        CRookServer::SendError(res, "File not found: " + path);
        return;
    }

    std::string ext = GetExtension(path);
    std::string format = ext.empty() ? "unknown" : ext.substr(1); // remove dot

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, path, targetLayer, format]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Import");

        ObjectDiffTracker tracker(pDoc);

        // Use RunScript for all formats — simplest and most reliable approach.
        // RunScript is synchronous on the main thread, so no sleep needed.
        ON_wString script = L"_-Import \"";
        script += Utf8ToWide(path);
        script += L"\" _Enter";

        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(script), 0);

        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        // Detect silent import failure
        if (newIds.empty())
        {
            WriteResult wr;
            wr.success = false;
            wr.error = "Import produced no objects. File may not exist, be unreadable, or contain no geometry: " + path;
            return wr;
        }

        // Move to target layer if specified
        if (!targetLayer.empty())
        {
            int layerIdx = -1;
            try
            {
                layerIdx = Rook::Infrastructure::ResolveLayerRef(
                    pDoc, targetLayer, "targetLayer").index;
            }
            catch (const std::invalid_argument& ex)
            {
                const std::string error = ex.what();
                if (error.find("not found") == std::string::npos)
                    throw;

                Rook::Infrastructure::ValidateNewLayerName(targetLayer);

                // Create the layer when the target does not exist yet.
                ON_Layer newLayer;
                newLayer.SetName(Utf8ToWide(targetLayer));
                layerIdx = pDoc->m_layer_table.AddLayer(newLayer);
            }

            if (layerIdx >= 0)
            {
                for (const auto& uuid : newIds)
                {
                    const CRhinoObject* obj = pDoc->LookupObject(uuid);
                    if (!obj) continue;

                    ON_3dmObjectAttributes attrs = obj->Attributes();
                    attrs.m_layer_index = layerIdx;
                    pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
                }
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["path"] = path;
        wr.data["format"] = format;
        wr.data["importedCount"] = static_cast<int>(newIds.size());

        nlohmann::json importedIds = nlohmann::json::array();
        for (const auto& uuid : newIds)
            importedIds.push_back(UuidToString(uuid));
        wr.data["importedIds"] = std::move(importedIds);

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

// ─── POST /export ───────────────────────────────────────────────────

void HandleExport(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("path") || !body["path"].is_string())
    {
        CRookServer::SendError(res, "Missing 'path' field (string)");
        return;
    }

    std::string path = body["path"].get<std::string>();
    std::string ext = GetExtension(path);
    std::string format = ext.empty() ? "unknown" : ext.substr(1);

    std::string pathErr = Rook::ValidateFilePath(path);
    if (!pathErr.empty())
    {
        CRookServer::SendError(res, pathErr);
        return;
    }

    // Collect object IDs to export (optional)
    std::vector<ON_UUID> ids;
    try
    {
        if (body.contains("ids"))
            ids = ParseUuids(body, "ids");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool selection = body.value("selection", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, path, format, ids = std::move(ids), selection]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        int exportedCount = 0;

        if (!ids.empty())
        {
            // Deselect all, then select specific objects
            CRhinoObjectIterator clearIt(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = clearIt.First(); obj; obj = clearIt.Next())
                const_cast<CRhinoObject*>(obj)->Select(false);

            for (const auto& uuid : ids)
            {
                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (!obj) continue;
                const_cast<CRhinoObject*>(obj)->Select(true);
                ++exportedCount;
            }
        }
        else if (selection)
        {
            // Count currently selected objects
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->IsSelected())
                    ++exportedCount;
            }
        }
        else
        {
            // Select all for export
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                const_cast<CRhinoObject*>(obj)->Select(true);
                ++exportedCount;
            }
        }

        // Run export command
        ON_wString script = L"_-Export \"";
        script += Utf8ToWide(path);
        script += L"\" _Enter";

        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(script), 0);

        // Deselect all after export
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = clearIt.First(); obj; obj = clearIt.Next())
            const_cast<CRhinoObject*>(obj)->Select(false);

        WriteResult wr;
        wr.success = true;
        wr.data["path"] = path;
        wr.data["format"] = format;
        wr.data["exportedCount"] = exportedCount;

        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
        {
            // Check file size on worker thread (avoids blocking Rhino main thread)
            try
            {
                if (fs::exists(path))
                    result.data["fileSize"] = static_cast<int64_t>(fs::file_size(path));
            }
            catch (...) {}
            CRookServer::SendSuccess(res, result.data);
        }
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
