// MeasureHandler.cpp
//
// GET|POST /measure/distance — Point-to-point or object-to-object distance
// GET|POST /measure/area     — Surface/brep/mesh/closed-curve area
// GET|POST /measure/volume   — Solid brep/mesh volume
// GET|POST /measure/length   — Curve length
// GET|POST /measure/bbox     — Bounding box dimensions
// GET|POST /measure/centroid — Centroid by geometry type

#include "stdafx.h"
#include "Handlers/MeasureHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// Lookup a Rhino object by UUID, throw if not found.
static const CRhinoObject* LookupObjectOrThrow(CRhinoDoc* pDoc, const ON_UUID& uuid)
{
    const CRhinoObject* obj = pDoc->LookupObject(uuid);
    if (!obj)
        throw std::invalid_argument("Object not found: " + UuidToString(uuid));
    return obj;
}

// Serialize a point as [x, y, z] rounded to 4 decimals.
static nlohmann::json PointToJson(const ON_3dPoint& pt)
{
    return nlohmann::json::array({ RoundTo(pt.x, 4), RoundTo(pt.y, 4), RoundTo(pt.z, 4) });
}

// ─── GET|POST /measure/distance ─────────────────────────────────────

void HandleMeasureDistance(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Determine mode: point-to-point (from/to) vs object-to-object (fromId/toId)
    bool hasPoints = body.contains("from") && body.contains("to");
    bool hasIds = body.contains("fromId") && body.contains("toId");

    if (!hasPoints && !hasIds)
    {
        CRookServer::SendError(res, "Provide either 'from'+'to' (points) or 'fromId'+'toId' (object IDs)");
        return;
    }

    if (hasPoints)
    {
        // Point-to-point mode: no main thread needed, just math
        ON_3dPoint from, to;
        try
        {
            from = ParsePoint3d(body, "from");
            to = ParsePoint3d(body, "to");
        }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, ex.what());
            return;
        }

        double distance = from.DistanceTo(to);

        nlohmann::json data;
        data["distance"] = RoundTo(distance, 6);
        data["from"] = PointToJson(from);
        data["to"] = PointToJson(to);
        CRookServer::SendSuccess(res, data);
        return;
    }

    // Object-to-object mode: needs main thread for geometry access
    ON_UUID fromUuid, toUuid;
    try
    {
        fromUuid = ParseUuid(body, "fromId");
        toUuid = ParseUuid(body, "toId");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, fromUuid, toUuid]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        const CRhinoObject* obj1 = LookupObjectOrThrow(pDoc, fromUuid);
        const CRhinoObject* obj2 = LookupObjectOrThrow(pDoc, toUuid);

        // Bounding-box approximation (matching C# behavior)
        ON_BoundingBox bb1 = obj1->BoundingBox();
        ON_BoundingBox bb2 = obj2->BoundingBox();
        ON_3dPoint cp1 = bb1.ClosestPoint(bb2.Center());
        ON_3dPoint cp2 = bb2.ClosestPoint(bb1.Center());
        double distance = cp1.DistanceTo(cp2);

        nlohmann::json data;
        data["distance"] = RoundTo(distance, 6);
        data["closestPointOnFrom"] = PointToJson(cp1);
        data["closestPointOnTo"] = PointToJson(cp2);
        return data;
    });

    try
    {
        auto data = future.get();
        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── GET|POST /measure/area ─────────────────────────────────────────

void HandleMeasureArea(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string idStr = body["id"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, idStr]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectOrThrow(pDoc, uuid);
        const ON_Geometry* geom = obj->Geometry();

        ON_MassProperties mp;
        bool computed = false;

        if (const ON_Brep* brep = ON_Brep::Cast(geom))
        {
            computed = brep->AreaMassProperties(mp, true, false, false, false);
        }
        else if (const ON_Surface* srf = ON_Surface::Cast(geom))
        {
            // Surface → convert to brep to compute area
            ON_Brep* brepForm = srf->BrepForm();
            if (brepForm)
            {
                computed = brepForm->AreaMassProperties(mp, true, false, false, false);
                delete brepForm;
            }
        }
        else if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        {
            // ON_Mesh::AreaMassProperties is non-const in the C++ SDK (it may
            // cache face normals internally), but the object is logically unchanged.
            computed = const_cast<ON_Mesh*>(mesh)->AreaMassProperties(mp, true, false, false, false);
        }
        else if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        {
            ON_Brep* brepForm = ext->BrepForm();
            if (brepForm)
            {
                computed = brepForm->AreaMassProperties(mp, true, false, false, false);
                delete brepForm;
            }
        }
        else if (const ON_Curve* curve = ON_Curve::Cast(geom))
        {
            if (!curve->IsClosed())
                throw std::invalid_argument("Curve must be closed to compute area");
            // Determine the curve's plane for correct area projection.
            // A circle in the YZ plane would give zero area if projected onto XY.
            ON_Plane curvePlane;
            if (!curve->IsPlanar(&curvePlane))
                curvePlane = ON_Plane::World_xy;  // fallback for non-planar curves
            computed = curve->AreaMassProperties(curvePlane.origin, curvePlane.zaxis,
                mp, true, false, false, false);
        }

        if (!computed)
            throw std::invalid_argument("Cannot compute area for " + ObjectTypeToString(obj->ObjectType()));

        nlohmann::json data;
        data["area"] = RoundTo(mp.Area(), 6);
        data["id"] = idStr;
        return data;
    });

    try
    {
        auto data = future.get();
        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── GET|POST /measure/volume ───────────────────────────────────────

void HandleMeasureVolume(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string idStr = body["id"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, idStr]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectOrThrow(pDoc, uuid);
        const ON_Geometry* geom = obj->Geometry();

        ON_MassProperties mp;
        bool computed = false;

        if (const ON_Brep* brep = ON_Brep::Cast(geom))
        {
            if (!brep->IsSolid())
                throw std::invalid_argument("Brep is not a closed solid");
            computed = brep->VolumeMassProperties(mp, true, false, false, false);
        }
        else if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        {
            if (!mesh->IsClosed())
                throw std::invalid_argument("Mesh is not closed");
            // See AreaMassProperties comment — ON_Mesh methods are non-const.
            computed = const_cast<ON_Mesh*>(mesh)->VolumeMassProperties(mp, true, false, false, false);
        }
        else if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        {
            ON_Brep* brepForm = ext->BrepForm();
            if (!brepForm || !brepForm->IsSolid())
            {
                delete brepForm;
                throw std::invalid_argument("Extrusion is not a closed solid");
            }
            computed = brepForm->VolumeMassProperties(mp, true, false, false, false);
            delete brepForm;
        }
        else
        {
            throw std::invalid_argument("Cannot compute volume for " + ObjectTypeToString(obj->ObjectType()));
        }

        if (!computed)
            throw std::invalid_argument("Failed to compute volume");

        nlohmann::json data;
        data["volume"] = RoundTo(mp.Volume(), 6);
        data["id"] = idStr;
        return data;
    });

    try
    {
        auto data = future.get();
        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── GET|POST /measure/length ───────────────────────────────────────

void HandleMeasureLength(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string idStr = body["id"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, idStr]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectOrThrow(pDoc, uuid);
        const ON_Geometry* geom = obj->Geometry();

        const ON_Curve* curve = ON_Curve::Cast(geom);
        if (!curve)
            throw std::invalid_argument("Cannot compute length for " +
                ObjectTypeToString(obj->ObjectType()) + ". Object must be a curve.");

        // ON_Curve::GetLength returns bool, length via out parameter
        double length = 0;
        if (!curve->GetLength(&length))
            throw std::invalid_argument("Failed to compute curve length");

        nlohmann::json data;
        data["length"] = RoundTo(length, 6);
        data["id"] = idStr;
        return data;
    });

    try
    {
        auto data = future.get();
        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── GET|POST /measure/bbox ─────────────────────────────────────────

void HandleMeasureBbox(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string idStr = body["id"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, idStr]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectOrThrow(pDoc, uuid);

        ON_BoundingBox bbox = obj->BoundingBox();
        if (!bbox.IsValid())
            throw std::invalid_argument("Object has no valid bounding box");

        ON_3dVector diag = bbox.Diagonal();

        nlohmann::json data;
        data["min"] = PointToJson(bbox.m_min);
        data["max"] = PointToJson(bbox.m_max);
        data["width"] = RoundTo(fabs(diag.x), 6);
        data["depth"] = RoundTo(fabs(diag.y), 6);
        data["height"] = RoundTo(fabs(diag.z), 6);
        data["id"] = idStr;
        return data;
    });

    try
    {
        auto data = future.get();
        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── GET|POST /measure/centroid ─────────────────────────────────────

void HandleMeasureCentroid(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string idStr = body["id"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, idStr]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = LookupObjectOrThrow(pDoc, uuid);
        const ON_Geometry* geom = obj->Geometry();

        ON_3dPoint centroid = ON_3dPoint::UnsetPoint;

        // Strategy matches C# MeasureHandler.GetCentroid:
        // Brep/Surface/Mesh → AreaMassProperties centroid, fallback to bbox center
        // Closed curve → AreaMassProperties centroid, fallback to midpoint
        // Open curve → midpoint by parameter
        // Point → point location
        // Everything else → bbox center
        if (const ON_Brep* brep = ON_Brep::Cast(geom))
        {
            ON_MassProperties mp;
            if (brep->AreaMassProperties(mp, true, true, false, false))
                centroid = mp.Centroid();
        }
        else if (const ON_Surface* srf = ON_Surface::Cast(geom))
        {
            ON_Brep* brepForm = srf->BrepForm();
            if (brepForm)
            {
                ON_MassProperties mp;
                if (brepForm->AreaMassProperties(mp, true, true, false, false))
                    centroid = mp.Centroid();
                delete brepForm;
            }
        }
        else if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        {
            ON_MassProperties mp;
            // See HandleMeasureArea — ON_Mesh methods are non-const.
            if (const_cast<ON_Mesh*>(mesh)->AreaMassProperties(mp, true, true, false, false))
                centroid = mp.Centroid();
        }
        else if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        {
            ON_Brep* brepForm = ext->BrepForm();
            if (brepForm)
            {
                ON_MassProperties mp;
                if (brepForm->AreaMassProperties(mp, true, true, false, false))
                    centroid = mp.Centroid();
                delete brepForm;
            }
        }
        else if (const ON_Curve* curve = ON_Curve::Cast(geom))
        {
            if (curve->IsClosed())
            {
                // Closed curve — use curve's plane for correct projection
                ON_Plane curvePlane;
                if (!curve->IsPlanar(&curvePlane))
                    curvePlane = ON_Plane::World_xy;
                ON_MassProperties mp;
                if (curve->AreaMassProperties(curvePlane.origin, curvePlane.zaxis,
                    mp, true, true, false, false))
                {
                    centroid = mp.Centroid();
                }
                else
                {
                    // Fallback to midpoint
                    centroid = curve->PointAt(curve->Domain().Mid());
                }
            }
            else
            {
                // Open curve — midpoint by arc length parameter
                centroid = curve->PointAt(curve->Domain().Mid());
            }
        }
        else if (const ON_Point* point = ON_Point::Cast(geom))
        {
            centroid = point->point;
        }

        // Final fallback: bounding box center
        if (!centroid.IsValid())
        {
            ON_BoundingBox bbox = obj->BoundingBox();
            if (bbox.IsValid())
                centroid = bbox.Center();
            else
                throw std::invalid_argument("Cannot compute centroid for this object");
        }

        nlohmann::json data;
        data["centroid"] = PointToJson(centroid);
        data["id"] = idStr;
        return data;
    });

    try
    {
        auto data = future.get();
        CRookServer::SendSuccess(res, data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
