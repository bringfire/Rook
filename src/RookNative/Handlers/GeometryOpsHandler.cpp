// GeometryOpsHandler.cpp
//
// POST /delete    — Delete objects by ID
// POST /transform — Move, rotate, scale, mirror objects
// POST /copy      — Copy objects with optional offset
// POST /undo      — Undo last action
// POST /redo      — Redo last undone action

#include "stdafx.h"
#include "Handlers/GeometryOpsHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Serialization/RhinoSerializer.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── POST /delete ───────────────────────────────────────────────────

void HandleDelete(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Parse IDs on worker thread
    std::vector<ON_UUID> ids;
    try
    {
        ids = ParseUuids(body, "ids");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (ids.empty())
    {
        CRookServer::SendError(res, "No object IDs provided");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids = std::move(ids)]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Delete Objects");

        int deletedCount = 0;
        int requestedCount = static_cast<int>(ids.size());
        std::vector<std::string> failedIds;

        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (obj)
            {
                CRhinoObjRef objRef(obj);
                if (pDoc->DeleteObject(objRef, true))
                {
                    ++deletedCount;
                    continue;
                }
            }
            failedIds.push_back(UuidToString(uuid));
        }

        WriteResult wr;
        wr.success = (deletedCount > 0);
        wr.data["deletedCount"] = deletedCount;
        wr.data["requestedCount"] = requestedCount;
        if (!failedIds.empty())
            wr.data["failedIds"] = failedIds;

        if (deletedCount > 0)
            pDoc->Redraw();

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

// ─── POST /transform ────────────────────────────────────────────────

void HandleTransform(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Parse on worker thread
    std::vector<ON_UUID> ids;
    std::string operation;
    try
    {
        ids = ParseUuids(body, "ids");
        if (!body.contains("operation") || !body["operation"].is_string())
            throw std::invalid_argument("Missing required field: operation");
        operation = body["operation"].get<std::string>();
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids = std::move(ids), operation, body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Transform Objects");

        // Build the transform matrix based on operation type
        ON_Xform xform = ON_Xform::IdentityTransformation;

        if (IEquals(operation, "move"))
        {
            ON_3dVector vec = ParseVector3d(body, "vector");
            xform = ON_Xform::TranslationTransformation(vec);
        }
        else if (IEquals(operation, "rotate"))
        {
            double angleDeg = body.value("angle", 0.0);
            double angleRad = angleDeg * (ON_PI / 180.0);
            ON_3dVector axis = ParseVector3dOrDefault(body, "axis", ON_3dVector(0, 0, 1));
            ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
            xform.Rotation(angleRad, axis, center);
        }
        else if (IEquals(operation, "scale"))
        {
            double factor = body.value("factor", 1.0);
            ON_3dPoint center = ParsePoint3dOrDefault(body, "center", ON_3dPoint::Origin);
            xform = ON_Xform::ScaleTransformation(center, factor);
        }
        else if (IEquals(operation, "mirror"))
        {
            ON_3dPoint planeOrigin = ParsePoint3dOrDefault(body, "planeOrigin", ON_3dPoint::Origin);
            ON_3dVector planeNormal = ParseVector3dOrDefault(body, "planeNormal", ON_3dVector(1, 0, 0));
            xform.Mirror(planeOrigin, planeNormal);
        }
        else
        {
            throw std::invalid_argument("Unknown transform operation: " + operation);
        }

        int transformedCount = 0;
        nlohmann::json resultIds = nlohmann::json::array();

        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj)
                continue;

            CRhinoObjRef objRef(obj);
            // CRhinoObjRef overload: (objRef, xform, bDeleteOriginal, bIgnoreModes, bAddHistory)
            // bDeleteOriginal=true → in-place transform (delete original, add transformed copy)
            // bIgnoreModes=false → respect locked/hidden state
            // bAddHistory=true → enable transform history for undo
            if (pDoc->TransformObject(objRef, xform, true, false, true))
            {
                ++transformedCount;
                resultIds.push_back(UuidToString(uuid));
            }
        }

        WriteResult wr;
        wr.success = (transformedCount > 0);
        wr.data["transformedCount"] = transformedCount;
        wr.data["operation"] = operation;
        wr.data["ids"] = std::move(resultIds);

        if (transformedCount > 0)
            pDoc->Redraw();

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

// ─── POST /copy ─────────────────────────────────────────────────────

void HandleCopy(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> ids;
    try
    {
        ids = ParseUuids(body, "ids");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids = std::move(ids), body]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Copy Objects");

        // Offset defaults to zero (in-place copy)
        ON_3dVector offset(0, 0, 0);
        if (body.contains("offset"))
            offset = ParseVector3d(body, "offset");

        ON_Xform translation = ON_Xform::TranslationTransformation(offset);

        int copiedCount = 0;
        nlohmann::json copies = nlohmann::json::array();

        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj)
                continue;

            // const CRhinoObject* overload returns the new object pointer.
            // Params: (obj, xform, bCopy=true, bQuiet=false, bHistory=false)
            // bCopy=true → creates a transformed duplicate, original stays intact.
            CRhinoObject* newObj = pDoc->TransformObject(obj, translation, true, false, false);
            if (newObj)
            {
                ++copiedCount;
                nlohmann::json pair;
                pair["originalId"] = UuidToString(uuid);
                pair["newId"] = UuidToString(newObj->Attributes().m_uuid);
                copies.push_back(std::move(pair));
            }
        }

        WriteResult wr;
        wr.success = (copiedCount > 0);
        wr.data["copiedCount"] = copiedCount;
        wr.data["copies"] = std::move(copies);

        if (copiedCount > 0)
            pDoc->Redraw();

        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, "No objects copied");
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /undo ─────────────────────────────────────────────────────

void HandleUndo(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        WriteResult wr;

        if (pDoc->Undo())
        {
            wr.success = true;
            wr.data = "Undo successful";
            pDoc->Redraw();
        }
        else
        {
            wr.success = false;
            wr.data = "Nothing to undo";
        }
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.data.get<std::string>());
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /redo ─────────────────────────────────────────────────────

void HandleRedo(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        WriteResult wr;

        if (pDoc->Redo())
        {
            wr.success = true;
            wr.data = "Redo successful";
            pDoc->Redraw();
        }
        else
        {
            wr.success = false;
            wr.data = "Nothing to redo";
        }
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendError(res, result.data.get<std::string>());
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
