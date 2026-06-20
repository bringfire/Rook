// ImportExportHandler.cpp
//
// POST /import — Import geometry from file
// POST /export — Export geometry to file

#include "stdafx.h"
#include "Handlers/ImportExportHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
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

static nlohmann::json StructuredFailure(
    const std::string& code,
    const std::string& message,
    bool retryable,
    const nlohmann::json& field = nullptr,
    const nlohmann::json& details = nlohmann::json::object())
{
    return {
        {"success", false},
        {"data", {
            {"code", code},
            {"message", message},
            {"retryable", retryable},
            {"field", field},
            {"details", details}
        }}
    };
}

static std::string JsonStringOr(
    const nlohmann::json& obj,
    const char* field,
    const std::string& fallback = "")
{
    if (obj.contains(field) && obj[field].is_string())
        return obj[field].get<std::string>();
    return fallback;
}

static void SendReconstructionImportFailure(
    httplib::Response& res,
    int status,
    const std::string& code,
    const std::string& message,
    bool retryable,
    const nlohmann::json& field = nullptr,
    const nlohmann::json& details = nlohmann::json::object())
{
    res.status = status;
    res.set_content(StructuredFailure(
        code,
        message,
        retryable,
        field,
        details).dump(), "application/json");
    res.set_header("X-Rook-Reconstruction-Op", "import_package");
}

static bool TryPrepareReconstructionImport(
    const nlohmann::json& requestBody,
    httplib::Response& res,
    nlohmann::json& data)
{
    nlohmann::json prepareBody = requestBody;
    prepareBody["op"] = "prepare_import";

    std::string responseJson;
    int statusCode = 0;
    std::string error;
    const auto result = InvokeReconstructionDispatchWithBody(
        prepareBody.dump(),
        responseJson,
        statusCode,
        error);

    if (result == ManagedCreateInvokeResult::Unavailable)
    {
        SendReconstructionImportFailure(
            res,
            503,
            "companion_unavailable",
            "Reconstruction import requires the Rook companion plugin. "
            "Ensure Rook.rhp is loaded in Rhino, then retry.",
            true);
        return false;
    }
    if (result != ManagedCreateInvokeResult::Ok)
    {
        SendReconstructionImportFailure(
            res,
            500,
            "prepare_failed",
            "Reconstruction import prepare failed: " + error,
            true);
        return false;
    }

    nlohmann::json envelope;
    try
    {
        envelope = nlohmann::json::parse(responseJson);
    }
    catch (const std::exception& ex)
    {
        SendReconstructionImportFailure(
            res,
            500,
            "prepare_failed",
            std::string("Reconstruction import prepare returned invalid JSON: ") + ex.what(),
            true);
        return false;
    }

    if (!envelope.value("success", false))
    {
        res.status = statusCode == 0 ? 400 : statusCode;
        res.set_content(responseJson, "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return false;
    }

    if (!envelope.contains("data") || !envelope["data"].is_object())
    {
        SendReconstructionImportFailure(
            res,
            500,
            "prepare_failed",
            "Reconstruction import prepare response was missing data.",
            true);
        return false;
    }

    data = envelope["data"];
    return true;
}

static bool RecordReconstructionImportHistory(
    const nlohmann::json& body,
    std::string& responseJson,
    int& statusCode,
    std::string& error)
{
    nlohmann::json recordBody = body;
    recordBody["op"] = "record_import";
    const auto result = InvokeReconstructionDispatchWithBody(
        recordBody.dump(),
        responseJson,
        statusCode,
        error);
    if (result != ManagedCreateInvokeResult::Ok)
        return false;

    try
    {
        const auto envelope = nlohmann::json::parse(responseJson);
        if (!envelope.value("success", false))
        {
            error = responseJson;
            return false;
        }
    }
    catch (const std::exception& ex)
    {
        error = std::string("record_import returned invalid JSON: ") + ex.what();
        return false;
    }

    return true;
}

static void CleanupPreparedReconstructionImport(const nlohmann::json& plan)
{
    if (!plan.contains("source_path"))
        return;

    const std::string packageId = JsonStringOr(plan, "package_id");
    const std::string importId = JsonStringOr(plan, "import_id");
    const std::string path = JsonStringOr(plan, "path");
    if (packageId.empty() || importId.empty() || path.empty())
        return;

    nlohmann::json cleanupBody = {
        {"op", "cleanup_prepared_import"},
        {"package_id", packageId},
        {"import_id", importId},
        {"path", path}
    };

    std::string responseJson;
    int statusCode = 0;
    std::string error;
    (void)InvokeReconstructionDispatchWithBody(
        cleanupBody.dump(),
        responseJson,
        statusCode,
        error);
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

// ─── POST /reconstruction/2d-to-3d/import ───────────────────────────

void HandleReconstructionImport(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("package_id") || !body["package_id"].is_string())
    {
        res.status = 400;
        res.set_content(StructuredFailure(
            "invalid_request",
            "package_id is required.",
            false,
            "package_id").dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }

    ON_UUID importUuid = ON_nil_uuid;
    if (FAILED(CoCreateGuid(&importUuid)))
    {
        res.status = 500;
        res.set_content(StructuredFailure(
            "import_failed",
            "Could not allocate reconstruction import id.",
            true).dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }
    const std::string importId = UuidToString(importUuid);
    body["import_id"] = importId;

    nlohmann::json plan;
    if (!TryPrepareReconstructionImport(body, res, plan))
        return;

    const std::string packageId = JsonStringOr(
        plan,
        "package_id",
        body["package_id"].get<std::string>());
    const std::string jobId = JsonStringOr(plan, "job_id");
    const std::string assetRole = JsonStringOr(plan, "asset_role");
    const std::string path = JsonStringOr(plan, "path");
    const std::string sourcePath = JsonStringOr(plan, "source_path");
    const std::string targetLayer = JsonStringOr(body, "targetLayer");

    if (path.empty() || assetRole.empty())
    {
        CleanupPreparedReconstructionImport(plan);
        res.status = 500;
        res.set_content(StructuredFailure(
            "invalid_package",
            "Reconstruction import plan was missing path or asset_role.",
            false).dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }

    std::string pathErr = Rook::ValidateFilePath(path);
    if (!pathErr.empty() || !fs::exists(path))
    {
        CleanupPreparedReconstructionImport(plan);
        res.status = 400;
        res.set_content(StructuredFailure(
            "invalid_package",
            pathErr.empty() ? "Reconstruction package asset file was not found." : pathErr,
            false).dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }

    const std::string format = GetExtension(path).empty()
        ? "unknown"
        : GetExtension(path).substr(1);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, path, sourcePath, targetLayer, packageId, jobId, importId, assetRole, format]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Reconstruction Import");

        ObjectDiffTracker tracker(pDoc);

        ON_wString script = L"_-Import \"";
        script += Utf8ToWide(path);
        script += L"\" _Enter";

        RhinoApp().RunScript(
            pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(script),
            0);

        std::vector<ON_UUID> newIds = tracker.GetNewObjects();
        if (newIds.empty())
        {
            WriteResult wr;
            wr.success = false;
            wr.error = "Reconstruction import produced no objects.";
            return wr;
        }

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

        bool associated = true;
        std::string associationError;
        for (const auto& uuid : newIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj)
            {
                associated = false;
                associationError = "Imported object could not be found for association.";
                continue;
            }

            ON_3dmObjectAttributes attrs = obj->Attributes();
            attrs.SetUserString(L"rook.reconstruction.package_id", Utf8ToWide(packageId));
            if (!jobId.empty())
                attrs.SetUserString(L"rook.reconstruction.job_id", Utf8ToWide(jobId));
            attrs.SetUserString(L"rook.reconstruction.import_id", Utf8ToWide(importId));
            attrs.SetUserString(L"rook.reconstruction.asset_role", Utf8ToWide(assetRole));

            if (!pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
            {
                associated = false;
                associationError = "Object association user text write failed.";
            }
        }

        nlohmann::json importedIds = nlohmann::json::array();
        for (const auto& uuid : newIds)
            importedIds.push_back(UuidToString(uuid));

        WriteResult wr;
        wr.success = associated;
        wr.error = associationError;
        wr.data["package_id"] = packageId;
        wr.data["job_id"] = jobId;
        wr.data["import_id"] = importId;
        wr.data["asset_role"] = assetRole;
        wr.data["path"] = path;
        if (!sourcePath.empty())
            wr.data["source_path"] = sourcePath;
        wr.data["format"] = format;
        wr.data["imported_ids"] = importedIds;
        wr.data["associated"] = associated;
        if (!associationError.empty())
            wr.data["association_error"] = associationError;
        return wr;
    });

    WriteResult importResult;
    try
    {
        importResult = future.get();
    }
    catch (const std::exception& ex)
    {
        CleanupPreparedReconstructionImport(plan);
        res.status = 500;
        res.set_content(StructuredFailure(
            "import_failed",
            ex.what(),
            true).dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }

    if (!importResult.data.contains("imported_ids"))
    {
        CleanupPreparedReconstructionImport(plan);
        res.status = 500;
        res.set_content(StructuredFailure(
            "import_failed",
            importResult.error.empty() ? "Reconstruction import failed." : importResult.error,
            true).dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }

    nlohmann::json recordBody = {
        {"package_id", packageId},
        {"job_id", jobId},
        {"import_id", importId},
        {"asset_role", assetRole},
        {"path", importResult.data["path"]},
        {"imported_ids", importResult.data["imported_ids"]},
        {"associated", importResult.data.value("associated", false)}
    };
    if (importResult.data.contains("source_path"))
        recordBody["source_path"] = importResult.data["source_path"];
    if (importResult.data.contains("association_error"))
        recordBody["association_error"] = importResult.data["association_error"];

    std::string recordResponse;
    int recordStatus = 0;
    std::string recordError;
    const bool recorded = RecordReconstructionImportHistory(
        recordBody,
        recordResponse,
        recordStatus,
        recordError);

    if (!recorded)
    {
        auto details = importResult.data;
        details["record_error"] = recordError;
        res.status = 500;
        res.set_content(StructuredFailure(
            "import_history_failed",
            "Import completed, but import history could not be recorded.",
            true,
            nullptr,
            details).dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }

    if (!importResult.success)
    {
        res.status = 500;
        res.set_content(StructuredFailure(
            "association_failed",
            "Import completed, but object association failed.",
            true,
            nullptr,
            importResult.data).dump(), "application/json");
        res.set_header("X-Rook-Reconstruction-Op", "import_package");
        return;
    }

    nlohmann::json response = {
        {"success", true},
        {"data", importResult.data}
    };
    res.status = 200;
    res.set_content(response.dump(), "application/json");
    res.set_header("X-Rook-Reconstruction-Op", "import_package");
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
