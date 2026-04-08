// FilletChamferHandler.cpp
//
// POST /fillet  — Fillet edges of a brep
// POST /chamfer — Chamfer edges of a brep
// POST /offset  — Offset a curve or brep surface
//
// Fillet and chamfer use RunScript with ObjectDiffTracker (edge selection
// by index through the direct API is complex and fragile).
// Offset also uses RunScript for consistency and reliability.

#include "stdafx.h"
#include "Handlers/FilletChamferHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── POST /fillet ───────────────────────────────────────────────────

void HandleFillet(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("id") || !body["id"].is_string())
    {
        CRookServer::SendError(res, "Missing 'id' field (object GUID)");
        return;
    }
    if (!body.contains("radius") || !body["radius"].is_number())
    {
        CRookServer::SendError(res, "Missing 'radius' field (number)");
        return;
    }

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double radius = body["radius"].get<double>();
    if (radius <= 0)
    {
        CRookServer::SendError(res, "Radius must be positive");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, radius]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Fillet Edges");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj)
            throw std::invalid_argument("Object not found");

        // Deselect all, select target
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);
        const_cast<CRhinoObject*>(obj)->Select(true);

        // Build command: _-FilletEdge _Radius=N _AllEdges _Enter
        wchar_t script[256];
        swprintf_s(script, 256,
            L"_-FilletEdge _Radius=%g _AllEdges _Enter _Enter",
            radius);

        ObjectDiffTracker tracker(pDoc);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), script, 0);
        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        WriteResult wr;
        if (newIds.empty())
        {
            wr.success = false;
            wr.data["error"] = "Fillet produced no results. Radius may be too large for the geometry.";
            return wr;
        }

        nlohmann::json resultIds = nlohmann::json::array();
        for (const auto& id : newIds)
            resultIds.push_back(UuidToString(id));

        wr.success = true;
        wr.data["resultIds"] = std::move(resultIds);
        wr.data["radius"] = radius;
        wr.data["edgeCount"] = -1; // all edges
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

// ─── POST /chamfer ──────────────────────────────────────────────────

void HandleChamfer(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("id") || !body["id"].is_string())
    {
        CRookServer::SendError(res, "Missing 'id' field (object GUID)");
        return;
    }

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    // Support symmetric (distance) or asymmetric (distance1, distance2)
    double dist1 = 0, dist2 = 0;
    if (body.contains("distance") && body["distance"].is_number())
    {
        dist1 = dist2 = body["distance"].get<double>();
    }
    else
    {
        dist1 = body.value("distance1", 0.0);
        dist2 = body.value("distance2", 0.0);
    }

    if (dist1 <= 0 || dist2 <= 0)
    {
        CRookServer::SendError(res, "Distance(s) must be positive");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, dist1, dist2]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Chamfer Edges");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj)
            throw std::invalid_argument("Object not found");

        // Deselect all, select target
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);
        const_cast<CRhinoObject*>(obj)->Select(true);

        // Build command
        wchar_t script[256];
        swprintf_s(script, 256,
            L"_-ChamferEdge _Distance1=%g _Distance2=%g _AllEdges _Enter _Enter",
            dist1, dist2);

        ObjectDiffTracker tracker(pDoc);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), script, 0);
        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        WriteResult wr;
        if (newIds.empty())
        {
            wr.success = false;
            wr.data["error"] = "Chamfer produced no results. Distance may be too large for the geometry.";
            return wr;
        }

        nlohmann::json resultIds = nlohmann::json::array();
        for (const auto& id : newIds)
            resultIds.push_back(UuidToString(id));

        wr.success = true;
        wr.data["resultIds"] = std::move(resultIds);
        wr.data["distance1"] = dist1;
        wr.data["distance2"] = dist2;
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

// ─── POST /offset ───────────────────────────────────────────────────

void HandleOffset(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("id") || !body["id"].is_string())
    {
        CRookServer::SendError(res, "Missing 'id' field (object GUID)");
        return;
    }
    if (!body.contains("distance") || !body["distance"].is_number())
    {
        CRookServer::SendError(res, "Missing 'distance' field (number)");
        return;
    }

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double distance = body["distance"].get<double>();

    // Optional: force type ("curve" or "surface")
    std::string forceType;
    if (body.contains("type") && body["type"].is_string())
        forceType = body["type"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, distance, forceType]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Offset");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj)
            throw std::invalid_argument("Object not found");

        const ON_Geometry* geom = obj->Geometry();
        bool isCurve = (ON_Curve::Cast(geom) != nullptr);
        bool isBrep = (ON_Brep::Cast(geom) != nullptr || ON_Extrusion::Cast(geom) != nullptr);

        // Determine what to offset
        bool offsetCurve = false;
        bool offsetSurface = false;
        if (!forceType.empty())
        {
            offsetCurve = IEquals(forceType, "curve");
            offsetSurface = IEquals(forceType, "surface");
        }
        else
        {
            offsetCurve = isCurve;
            offsetSurface = isBrep;
        }

        if (!offsetCurve && !offsetSurface)
            throw std::invalid_argument("Object is not a curve or surface");

        // Deselect all, select target
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);
        const_cast<CRhinoObject*>(obj)->Select(true);

        ObjectDiffTracker tracker(pDoc);

        wchar_t script[512];
        if (offsetCurve)
        {
            // _-Offset requires a "side to offset" point after the distance.
            // Compute a point on the desired side using the curve's midpoint
            // and perpendicular direction. The sign of distance controls which side.
            const ON_Curve* curve = ON_Curve::Cast(geom);
            ON_3dPoint midPt;
            ON_3dVector tangent;
            curve->EvTangent(curve->Domain().Mid(), midPt, tangent);

            // Perpendicular in the curve's plane (XY fallback)
            ON_3dVector perp(-tangent.y, tangent.x, 0.0);
            if (perp.Length() < 1e-10)
                perp = ON_3dVector(0, 0, 1); // degenerate case
            perp.Unitize();

            ON_3dPoint sidePt = midPt + perp * distance;
            double absDist = fabs(distance);

            swprintf_s(script, 512,
                L"_-Offset %g %g,%g,%g _Enter",
                absDist, sidePt.x, sidePt.y, sidePt.z);
        }
        else
        {
            // OffsetSrf for breps — distance sign controls inward/outward
            swprintf_s(script, 512,
                L"_-OffsetSrf %g _Enter", distance);
        }

        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), script, 0);
        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        WriteResult wr;
        if (newIds.empty())
        {
            wr.success = false;
            wr.data["error"] = "Offset produced no results";
            return wr;
        }

        nlohmann::json resultIds = nlohmann::json::array();
        for (const auto& id : newIds)
            resultIds.push_back(UuidToString(id));

        wr.success = true;
        wr.data["type"] = offsetCurve ? "curve" : "surface";
        wr.data["resultIds"] = std::move(resultIds);
        wr.data["distance"] = distance;
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

} // namespace Handlers
} // namespace Rook
