// AnalysisHandler.cpp
//
// All 13 routes are read-only geometry queries — no undo, no mutation.

#include "stdafx.h"
#include "Handlers/AnalysisHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static nlohmann::json Point3dToJson(const ON_3dPoint& pt)
{
    return { pt.x, pt.y, pt.z };
}

static nlohmann::json Vector3dToJson(const ON_3dVector& v)
{
    return { v.x, v.y, v.z };
}

// Extract an ON_Surface* from geometry (handles Brep single-face, Extrusion, Surface).
// Returns nullptr if not surface-like.
static const ON_Surface* ExtractSurface(const ON_Geometry* geom)
{
    if (const ON_Surface* srf = ON_Surface::Cast(geom))
        return srf;

    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        return ext;  // ON_Extrusion is-a ON_Surface

    if (const ON_Brep* brep = ON_Brep::Cast(geom))
    {
        if (brep->m_F.Count() == 1)
            return brep->m_F[0].SurfaceOf();
    }
    return nullptr;
}

// Extract an ON_Brep* from geometry (handles Brep, Extrusion).
// For extrusions, converts to brep form. Caller must delete if bMustDelete is true.
static const ON_Brep* ExtractBrep(const ON_Geometry* geom, bool& bMustDelete)
{
    bMustDelete = false;

    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return brep;

    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
    {
        ON_Brep* brep = ext->BrepForm();
        if (brep)
        {
            bMustDelete = true;
            return brep;
        }
    }
    return nullptr;
}

static ON_3dPoint ParsePoint3d(const nlohmann::json& arr)
{
    if (!arr.is_array() || arr.size() < 3)
        throw std::invalid_argument("Expected [x,y,z] array");
    return ON_3dPoint(arr[0].get<double>(), arr[1].get<double>(), arr[2].get<double>());
}

static ON_3dVector ParseVector3d(const nlohmann::json& arr)
{
    if (!arr.is_array() || arr.size() < 3)
        throw std::invalid_argument("Expected [x,y,z] array");
    return ON_3dVector(arr[0].get<double>(), arr[1].get<double>(), arr[2].get<double>());
}

// ─── POST /analysis/curvature-curve ────────────────────────────────

void HandleCurvatureCurve(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("parameter") || !body["parameter"].is_number())
    {
        CRookServer::SendError(res, "Missing 'parameter' field (number 0-1)");
        return;
    }
    double param = body["parameter"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, param]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        double t = curve->Domain().ParameterAt(param);

        ON_3dPoint pt = curve->PointAt(t);
        ON_3dVector tangent = curve->TangentAt(t);
        ON_3dVector curvature = curve->CurvatureAt(t);
        double magnitude = curvature.Length();
        double radius = (magnitude > 1e-12) ? 1.0 / magnitude : 0.0;

        nlohmann::json result;
        result["point"] = Point3dToJson(pt);
        result["tangent"] = Vector3dToJson(tangent);
        result["curvature"] = Vector3dToJson(curvature);
        result["curvatureMagnitude"] = magnitude;
        result["radiusOfCurvature"] = radius;
        result["parameter"] = t;
        result["normalizedParameter"] = param;
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

// ─── POST /analysis/curvature-surface ──────────────────────────────

void HandleCurvatureSurface(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "surfaceId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("u") || !body["u"].is_number() ||
        !body.contains("v") || !body["v"].is_number())
    {
        CRookServer::SendError(res, "Missing 'u' and 'v' fields (numbers 0-1)");
        return;
    }
    double uNorm = body["u"].get<double>();
    double vNorm = body["v"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, uNorm, vNorm]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Surface* srf = ExtractSurface(obj->Geometry());
        if (!srf) throw std::invalid_argument("Object is not a surface");

        double u = srf->Domain(0).ParameterAt(uNorm);
        double v = srf->Domain(1).ParameterAt(vNorm);

        ON_3dPoint pt = srf->PointAt(u, v);
        ON_3dVector normal = srf->NormalAt(u, v);

        // Compute principal curvatures from second derivatives
        ON_3dPoint srfPt;
        ON_3dVector du, dv, duu, duv, dvv;
        if (!srf->Ev2Der(u, v, srfPt, du, dv, duu, duv, dvv))
            throw std::runtime_error("Failed to evaluate surface derivatives");

        double gaussian = 0, mean = 0, kappa1 = 0, kappa2 = 0;
        ON_3dVector dir1, dir2;
        ON_EvPrincipalCurvatures(du, dv, duu, duv, dvv, normal,
            &gaussian, &mean, &kappa1, &kappa2, dir1, dir2);

        nlohmann::json result;
        result["point"] = Point3dToJson(pt);
        result["normal"] = Vector3dToJson(normal);
        result["gaussian"] = gaussian;
        result["mean"] = mean;
        result["kappa1"] = kappa1;
        result["kappa2"] = kappa2;
        result["direction1"] = Vector3dToJson(dir1);
        result["direction2"] = Vector3dToJson(dir2);
        result["u"] = u;
        result["v"] = v;
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

// ─── POST /analysis/draft-angle ────────────────────────────────────

void HandleDraftAngle(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    ON_3dVector direction(0, 0, 1);
    if (body.contains("direction"))
        direction = ParseVector3d(body["direction"]);

    direction.Unitize();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, direction]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        if (!brep) throw std::invalid_argument("Object is not a brep");
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);

        nlohmann::json faces = nlohmann::json::array();

        for (int i = 0; i < brep->m_F.Count(); ++i)
        {
            const ON_BrepFace& face = brep->m_F[i];
            const ON_Surface* srf = face.SurfaceOf();
            if (!srf) continue;

            double midU = srf->Domain(0).Mid();
            double midV = srf->Domain(1).Mid();
            ON_3dVector faceNormal = srf->NormalAt(midU, midV);
            if (face.m_bRev)
                faceNormal = -faceNormal;

            double dot = faceNormal * direction;
            // Clamp for acos safety
            if (dot > 1.0) dot = 1.0;
            if (dot < -1.0) dot = -1.0;
            double angleRad = acos(dot);
            double draftAngle = 90.0 - (angleRad * 180.0 / ON_PI);

            nlohmann::json fj;
            fj["faceIndex"] = i;
            fj["draftAngle"] = draftAngle;
            fj["normal"] = Vector3dToJson(faceNormal);
            faces.push_back(std::move(fj));
        }

        nlohmann::json result;
        result["direction"] = Vector3dToJson(direction);
        result["faceCount"] = static_cast<int>(faces.size());
        result["faces"] = std::move(faces);
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

// ─── POST /analysis/closest-point ──────────────────────────────────

void HandleClosestPoint(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("point"))
    {
        CRookServer::SendError(res, "Missing 'point' field ([x,y,z])");
        return;
    }

    ON_3dPoint testPt;
    try { testPt = ParsePoint3d(body["point"]); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, testPt]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Geometry* geom = obj->Geometry();
        nlohmann::json result;

        if (const ON_Curve* curve = ON_Curve::Cast(geom))
        {
            double t = 0;
            if (!curve->GetClosestPoint(testPt, &t))
                throw std::runtime_error("GetClosestPoint failed on curve");

            ON_3dPoint cp = curve->PointAt(t);
            result["closestPoint"] = Point3dToJson(cp);
            result["distance"] = cp.DistanceTo(testPt);
            result["parameter"] = t;
            result["geometryType"] = "curve";
        }
        // ON_Extrusion IS-A ON_Surface, so check extrusion BEFORE surface
        else if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        {
            // Convert to brep and use face query
            std::unique_ptr<ON_Brep> tempBrep(ext->BrepForm());
            if (!tempBrep) throw std::runtime_error("Failed to convert extrusion to brep");

            ON_3dPoint cp = ON_3dPoint::UnsetPoint;
            double bestDist = 1e300;
            double bestU = 0, bestV = 0;
            int bestFace = -1;

            for (int i = 0; i < tempBrep->m_F.Count(); ++i)
            {
                const ON_Surface* faceSrf = tempBrep->m_F[i].SurfaceOf();
                if (!faceSrf) continue;
                double u = 0, v = 0;
                if (faceSrf->GetClosestPoint(testPt, &u, &v))
                {
                    ON_3dPoint facePt = faceSrf->PointAt(u, v);
                    double d = facePt.DistanceTo(testPt);
                    if (d < bestDist)
                    {
                        bestDist = d;
                        cp = facePt;
                        bestU = u;
                        bestV = v;
                        bestFace = i;
                    }
                }
            }

            if (cp == ON_3dPoint::UnsetPoint)
                throw std::runtime_error("GetClosestPoint failed on extrusion");

            result["closestPoint"] = Point3dToJson(cp);
            result["distance"] = bestDist;
            result["u"] = bestU;
            result["v"] = bestV;
            result["faceIndex"] = bestFace;
            result["geometryType"] = "extrusion";
        }
        else if (const ON_Brep* brep = ON_Brep::Cast(geom))
        {
            ON_3dPoint cp = ON_3dPoint::UnsetPoint;
            double bestDist = 1e300;
            double bestU = 0, bestV = 0;
            int bestFace = -1;

            for (int i = 0; i < brep->m_F.Count(); ++i)
            {
                const ON_BrepFace& face = brep->m_F[i];
                const ON_Surface* faceSrf = face.SurfaceOf();
                if (!faceSrf) continue;

                double u = 0, v = 0;
                if (faceSrf->GetClosestPoint(testPt, &u, &v))
                {
                    ON_3dPoint facePt = faceSrf->PointAt(u, v);
                    double d = facePt.DistanceTo(testPt);
                    if (d < bestDist)
                    {
                        bestDist = d;
                        cp = facePt;
                        bestU = u;
                        bestV = v;
                        bestFace = i;
                    }
                }
            }

            if (cp == ON_3dPoint::UnsetPoint)
                throw std::runtime_error("GetClosestPoint failed on brep");

            result["closestPoint"] = Point3dToJson(cp);
            result["distance"] = bestDist;
            result["u"] = bestU;
            result["v"] = bestV;
            result["faceIndex"] = bestFace;
            result["geometryType"] = "brep";
        }
        else if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        {
            ON_MESH_POINT mp;
            if (!mesh->GetClosestPoint(testPt, &mp))
                throw std::runtime_error("GetClosestPoint failed on mesh");

            result["closestPoint"] = Point3dToJson(mp.m_P);
            result["distance"] = mp.m_P.DistanceTo(testPt);
            result["geometryType"] = "mesh";
        }
        else if (const ON_Surface* srf = ON_Surface::Cast(geom))
        {
            double u = 0, v = 0;
            if (!srf->GetClosestPoint(testPt, &u, &v))
                throw std::runtime_error("GetClosestPoint failed on surface");

            ON_3dPoint cp = srf->PointAt(u, v);
            result["closestPoint"] = Point3dToJson(cp);
            result["distance"] = cp.DistanceTo(testPt);
            result["u"] = u;
            result["v"] = v;
            result["geometryType"] = "surface";
        }
        else
        {
            throw std::invalid_argument("Unsupported geometry type for closest point");
        }

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

// ─── POST /analysis/curve-point-at ─────────────────────────────────

void HandleCurvePointAt(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("parameter") || !body["parameter"].is_number())
    {
        CRookServer::SendError(res, "Missing 'parameter' field (number 0-1)");
        return;
    }
    double param = body["parameter"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, param]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        double t = curve->Domain().ParameterAt(param);
        ON_3dPoint pt = curve->PointAt(t);

        nlohmann::json result;
        result["point"] = Point3dToJson(pt);
        result["parameter"] = t;
        result["normalizedParameter"] = param;
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

// ─── POST /analysis/curve-tangent ──────────────────────────────────

void HandleCurveTangent(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("parameter") || !body["parameter"].is_number())
    {
        CRookServer::SendError(res, "Missing 'parameter' field (number 0-1)");
        return;
    }
    double param = body["parameter"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, param]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        double t = curve->Domain().ParameterAt(param);
        ON_3dPoint pt = curve->PointAt(t);
        ON_3dVector tangent = curve->TangentAt(t);

        nlohmann::json result;
        result["point"] = Point3dToJson(pt);
        result["tangent"] = Vector3dToJson(tangent);
        result["parameter"] = t;
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

// ─── POST /analysis/curve-frame ────────────────────────────────────

void HandleCurveFrame(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("parameter") || !body["parameter"].is_number())
    {
        CRookServer::SendError(res, "Missing 'parameter' field (number 0-1)");
        return;
    }
    double param = body["parameter"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, param]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        double t = curve->Domain().ParameterAt(param);

        ON_Plane frame;
        if (!curve->FrameAt(t, frame))
        {
            // Fallback: build frame from tangent
            ON_3dPoint pt = curve->PointAt(t);
            ON_3dVector tangent = curve->TangentAt(t);
            ON_3dVector perp(0, 0, 1);
            if (fabs(tangent * perp) > 0.99)
                perp = ON_3dVector(1, 0, 0);
            ON_3dVector yAxis = ON_CrossProduct(tangent, perp);
            yAxis.Unitize();
            ON_3dVector zAxis = ON_CrossProduct(tangent, yAxis);
            zAxis.Unitize();
            frame.CreateFromFrame(pt, tangent, yAxis);
        }

        nlohmann::json result;
        result["origin"] = Point3dToJson(frame.origin);
        result["xAxis"] = Vector3dToJson(frame.xaxis);
        result["yAxis"] = Vector3dToJson(frame.yaxis);
        result["zAxis"] = Vector3dToJson(frame.zaxis);
        result["parameter"] = t;
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

// ─── POST /analysis/surface-normal ─────────────────────────────────

void HandleSurfaceNormal(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "surfaceId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("u") || !body["u"].is_number() ||
        !body.contains("v") || !body["v"].is_number())
    {
        CRookServer::SendError(res, "Missing 'u' and 'v' fields (numbers 0-1)");
        return;
    }
    double uNorm = body["u"].get<double>();
    double vNorm = body["v"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, uNorm, vNorm]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Surface* srf = ExtractSurface(obj->Geometry());
        if (!srf) throw std::invalid_argument("Object is not a surface");

        double u = srf->Domain(0).ParameterAt(uNorm);
        double v = srf->Domain(1).ParameterAt(vNorm);

        ON_3dPoint pt = srf->PointAt(u, v);
        ON_3dVector normal = srf->NormalAt(u, v);

        nlohmann::json result;
        result["point"] = Point3dToJson(pt);
        result["normal"] = Vector3dToJson(normal);
        result["u"] = u;
        result["v"] = v;
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

// ─── POST /analysis/brep-edges ─────────────────────────────────────

void HandleBrepEdges(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        if (!brep) throw std::invalid_argument("Object is not a brep");
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);

        nlohmann::json edges = nlohmann::json::array();

        for (int i = 0; i < brep->m_E.Count(); ++i)
        {
            const ON_BrepEdge& edge = brep->m_E[i];
            const ON_Curve* edgeCurve = edge.EdgeCurveOf();

            nlohmann::json ej;
            ej["index"] = i;

            if (edgeCurve)
            {
                ej["startPoint"] = Point3dToJson(edgeCurve->PointAtStart());
                ej["endPoint"] = Point3dToJson(edgeCurve->PointAtEnd());
                double len = 0;
                edgeCurve->GetLength(&len);
                ej["length"] = len;
                ej["isClosed"] = edgeCurve->IsClosed();
                ej["degree"] = edgeCurve->Degree();
            }
            else
            {
                ej["startPoint"] = nullptr;
                ej["endPoint"] = nullptr;
                ej["length"] = 0;
                ej["isClosed"] = false;
                ej["degree"] = 0;
            }

            ej["valence"] = edge.m_ti.Count();
            edges.push_back(std::move(ej));
        }

        nlohmann::json result;
        result["edgeCount"] = static_cast<int>(edges.size());
        result["edges"] = std::move(edges);
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

// ─── POST /analysis/brep-faces ─────────────────────────────────────

void HandleBrepFaces(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        if (!brep) throw std::invalid_argument("Object is not a brep");
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);

        nlohmann::json faces = nlohmann::json::array();

        for (int i = 0; i < brep->m_F.Count(); ++i)
        {
            const ON_BrepFace& face = brep->m_F[i];
            const ON_Surface* srf = face.SurfaceOf();

            nlohmann::json fj;
            fj["index"] = i;
            fj["surfaceIndex"] = face.m_si;
            fj["loopCount"] = face.m_li.Count();

            if (srf)
            {
                double midU = srf->Domain(0).Mid();
                double midV = srf->Domain(1).Mid();
                ON_3dVector normal = srf->NormalAt(midU, midV);
                if (face.m_bRev)
                    normal = -normal;
                fj["normal"] = Vector3dToJson(normal);

                // Compute area
                ON_MassProperties mp;
                if (face.AreaMassProperties(mp, true, false, false, false))
                {
                    fj["area"] = mp.Area();
                    fj["centroid"] = Point3dToJson(mp.Centroid());
                }
                else
                {
                    fj["area"] = 0.0;
                    fj["centroid"] = nullptr;
                }

                fj["isSurface"] = brep->FaceIsSurface(i);
            }
            else
            {
                fj["normal"] = nullptr;
                fj["area"] = 0.0;
                fj["centroid"] = nullptr;
                fj["isSurface"] = false;
            }

            faces.push_back(std::move(fj));
        }

        nlohmann::json result;
        result["faceCount"] = static_cast<int>(faces.size());
        result["faces"] = std::move(faces);
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

// ─── POST /analysis/brep-vertices ──────────────────────────────────

void HandleBrepVertices(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        if (!brep) throw std::invalid_argument("Object is not a brep");
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);

        nlohmann::json vertices = nlohmann::json::array();

        for (int i = 0; i < brep->m_V.Count(); ++i)
        {
            const ON_BrepVertex& vertex = brep->m_V[i];

            nlohmann::json vj;
            vj["index"] = i;
            vj["point"] = Point3dToJson(vertex.point);

            nlohmann::json edgeIndices = nlohmann::json::array();
            for (int j = 0; j < vertex.m_ei.Count(); ++j)
                edgeIndices.push_back(vertex.m_ei[j]);
            vj["edgeIndices"] = std::move(edgeIndices);

            vertices.push_back(std::move(vj));
        }

        nlohmann::json result;
        result["vertexCount"] = static_cast<int>(vertices.size());
        result["vertices"] = std::move(vertices);
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

// ─── POST /analysis/is-closed ──────────────────────────────────────

void HandleIsClosed(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Geometry* geom = obj->Geometry();
        nlohmann::json result;
        bool isClosed = false;
        bool isSolid = false;

        if (const ON_Curve* curve = ON_Curve::Cast(geom))
        {
            isClosed = curve->IsClosed();
            result["geometryType"] = "curve";
        }
        else if (const ON_Brep* brep = ON_Brep::Cast(geom))
        {
            isClosed = brep->IsSolid();
            isSolid = brep->IsSolid();
            result["geometryType"] = "brep";
        }
        else if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
        {
            ON_Brep* tempBrep = ext->BrepForm();
            if (tempBrep)
            {
                isClosed = tempBrep->IsSolid();
                isSolid = tempBrep->IsSolid();
                delete tempBrep;
            }
            result["geometryType"] = "extrusion";
        }
        else if (const ON_Mesh* mesh = ON_Mesh::Cast(geom))
        {
            isClosed = mesh->IsClosed();
            isSolid = mesh->IsClosed();
            result["geometryType"] = "mesh";
        }
        else if (const ON_SubD* subd = ON_SubD::Cast(geom))
        {
            isClosed = subd->IsSolid();
            isSolid = subd->IsSolid();
            result["geometryType"] = "subd";
        }
        else
        {
            result["geometryType"] = ObjectTypeToString(obj->ObjectType());
        }

        result["isClosed"] = isClosed;
        result["isSolid"] = isSolid;
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

// ─── POST /analysis/is-valid ───────────────────────────────────────

void HandleIsValid(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Geometry* geom = obj->Geometry();

        ON_wString logStr;
        ON_TextLog textLog(logStr);
        bool isValid = geom->IsValid(&textLog);

        nlohmann::json result;
        result["isValid"] = isValid;
        result["geometryType"] = ObjectTypeToString(obj->ObjectType());
        result["validationLog"] = WideToUtf8(logStr);
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

} // namespace Handlers
} // namespace Rook
