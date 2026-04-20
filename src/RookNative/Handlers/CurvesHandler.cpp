// CurvesHandler.cpp
//
// Substrate: 12 routes are `direct-sdk` native; HandleBlendCurves
// (PR-1, 2026-04-20 Phase 2 extension) and HandleCurveBoolean (PR-4,
// 2026-04-20 Phase 2 extension) are `managed-bridge (reuse)` via the
// `CreateGeometry` callback. Per-route substrate is named in each
// handler's opening comment (Rule 6). The reusable normalization +
// dispatch tail (`EmitNormalized`, `DispatchToManagedCreate`) live in
// `Infrastructure/ManagedCreateDispatch.h` — promoted from
// `SurfaceHandler.cpp`'s anonymous namespace in PR-4 when
// HandleCurveBoolean became the third caller (Rule 6
// promotion-on-third-caller convention).
//
// 12 direct-sdk routes:
//   POST /curve/join, /curve/explode, /curve/divide, /curve/extend,
//   /curve/trim, /curve/split, /curve/rebuild, /curve/fillet,
//   /curve/project, /curve/pull, /curve/offset, /curve/offset-on-surface
//
// 2 managed-bridge (reuse) routes:
//   POST /curve/blend    — PR-1 (singular-contract Curve factory)
//   POST /curve/boolean  — PR-4 (plural-contract Curve[] factory,
//                          3 intent keys dispatched via `operation`)

#include "stdafx.h"
#include "Handlers/CurvesHandler.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Infrastructure/ManagedCreateDispatch.h"
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

// Extract an ON_Brep* from geometry (handles Brep, Extrusion, Surface).
// Caller must delete if bMustDelete is true.
static const ON_Brep* ExtractBrep(const ON_Geometry* geom, bool& bMustDelete)
{
    bMustDelete = false;

    if (const ON_Brep* brep = ON_Brep::Cast(geom))
        return brep;

    if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
    {
        ON_Brep* brep = ext->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    if (const ON_Surface* srf = ON_Surface::Cast(geom))
    {
        ON_Brep* brep = srf->BrepForm();
        if (brep) { bMustDelete = true; return brep; }
    }

    return nullptr;
}

// ─── POST /curve/join ──────────────────────────────────────────────

void HandleCurveJoin(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("ids") || !body["ids"].is_array() || body["ids"].size() < 2)
    {
        CRookServer::SendError(res, "Need at least 2 object IDs in 'ids' array");
        return;
    }

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids = std::move(ids)]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Join Curves");

        // Collect curves
        ON_SimpleArray<const ON_Curve*> inputCurves;
        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) throw std::invalid_argument("Object not found: " + UuidToString(uuid));

            const ON_Curve* crv = ON_Curve::Cast(obj->Geometry());
            if (!crv) throw std::invalid_argument("Object " + UuidToString(uuid) + " is not a curve");

            inputCurves.Append(crv);
        }

        double tol = pDoc->AbsoluteTolerance();
        ON_SimpleArray<ON_Curve*> outputCurves;
        RhinoMergeCurves(inputCurves, outputCurves, tol, FALSE, nullptr);

        if (outputCurves.Count() == 0)
            throw std::runtime_error("Join produced no results");

        // Add results, delete originals
        nlohmann::json resultIds = nlohmann::json::array();
        for (int i = 0; i < outputCurves.Count(); ++i)
        {
            CRhinoCurveObject* newObj = new CRhinoCurveObject();
            newObj->SetCurve(outputCurves[i]);  // takes ownership
            outputCurves[i] = nullptr;
            if (pDoc->AddObject(newObj))
                resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
            else
                delete newObj;
        }

        // Delete originals
        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (obj) pDoc->DeleteObject(CRhinoObjRef(obj));
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["createdCount"] = static_cast<int>(resultIds.size());
        wr.data["createdIds"] = std::move(resultIds);
        wr.data["originalCount"] = static_cast<int>(ids.size());
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

// ─── POST /curve/explode ───────────────────────────────────────────

void HandleCurveExplode(const httplib::Request& req, httplib::Response& res)
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
        [docSn, uuid]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Explode Curve");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        ON_SimpleArray<ON_Curve*> segments;
        int count = RhinoDuplicateCurveSegments(curve, segments);

        if (count <= 1)
        {
            // Clean up any allocated segments
            for (int i = 0; i < segments.Count(); ++i)
                delete segments[i];
            throw std::runtime_error("Curve has only one segment; nothing to explode");
        }

        nlohmann::json resultIds = nlohmann::json::array();
        ON_3dmObjectAttributes attrs = obj->Attributes();

        for (int i = 0; i < segments.Count(); ++i)
        {
            CRhinoCurveObject* newObj = new CRhinoCurveObject(attrs);
            newObj->SetCurve(segments[i]);  // takes ownership
            segments[i] = nullptr;
            if (pDoc->AddObject(newObj))
                resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
            else
                delete newObj;
        }

        pDoc->DeleteObject(CRhinoObjRef(obj));
        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["createdCount"] = static_cast<int>(resultIds.size());
        wr.data["createdIds"] = std::move(resultIds);
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

// ─── POST /curve/divide ────────────────────────────────────────────

void HandleCurveDivide(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool byCount = body.contains("count") && body["count"].is_number_integer();
    bool byLength = body.contains("length") && body["length"].is_number();
    if (!byCount && !byLength)
    {
        CRookServer::SendError(res, "Must provide 'count' (int) or 'length' (number)");
        return;
    }

    int divCount = byCount ? body["count"].get<int>() : 0;
    double divLength = byLength ? body["length"].get<double>() : 0;
    bool addPoints = body.value("addPoints", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, byCount, divCount, divLength, addPoints]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        ON_SimpleArray<ON_3dPoint> divPoints;
        ON_SimpleArray<double> params;

        if (byCount)
        {
            if (divCount < 2)
                throw std::invalid_argument("Count must be at least 2");
            if (!RhinoDivideCurve(*curve, static_cast<double>(divCount), 0.0,
                    false, true, &divPoints, &params))
                throw std::runtime_error("Division by count failed");
        }
        else
        {
            if (divLength <= 0)
                throw std::invalid_argument("Length must be positive");
            if (!RhinoDivideCurve(*curve, 0.0, divLength,
                    false, true, &divPoints, &params))
                throw std::runtime_error("Division by length failed");
        }

        if (params.Count() == 0)
            throw std::runtime_error("Division produced no results");

        // Build point and parameter arrays from RhinoDivideCurve results
        nlohmann::json points = nlohmann::json::array();
        nlohmann::json paramList = nlohmann::json::array();
        for (int i = 0; i < divPoints.Count(); ++i)
        {
            const ON_3dPoint& pt = divPoints[i];
            points.push_back({ pt.x, pt.y, pt.z });
            if (i < params.Count())
                paramList.push_back(params[i]);
        }

        WriteResult wr;
        wr.success = true;
        wr.data["pointCount"] = divPoints.Count();
        wr.data["points"] = std::move(points);
        wr.data["parameters"] = std::move(paramList);

        if (addPoints)
        {
            UndoScope undo(pDoc, L"Divide Curve");
            nlohmann::json createdIds = nlohmann::json::array();
            for (int i = 0; i < divPoints.Count(); ++i)
            {
                CRhinoPointObject* ptObj = pDoc->AddPointObject(divPoints[i]);
                if (ptObj)
                    createdIds.push_back(UuidToString(ptObj->Attributes().m_uuid));
            }
            wr.data["createdIds"] = std::move(createdIds);
            pDoc->Redraw();
        }

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

// ─── POST /curve/extend ────────────────────────────────────────────

void HandleCurveExtend(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("length") || !body["length"].is_number())
    {
        CRookServer::SendError(res, "Missing 'length' field (number)");
        return;
    }
    double length = body["length"].get<double>();

    std::string endStr = body.value("end", "end");
    std::string styleStr = body.value("style", "smooth");

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, length, endStr, styleStr]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Extend Curve");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        // Map style string to enum
        CRhinoExtend::Type extType = CRhinoExtend::Smooth;
        if (IEquals(styleStr, "line")) extType = CRhinoExtend::Line;
        else if (IEquals(styleStr, "arc")) extType = CRhinoExtend::Arc;
        else if (IEquals(styleStr, "natural")) extType = CRhinoExtend::Natural;

        // Map end string to side: 0=start, 1=end, 2=both
        int side = 1;
        if (IEquals(endStr, "start")) side = 0;
        else if (IEquals(endStr, "both")) side = 2;

        // RhinoExtendCurve takes ON_Curve*& — modifies in-place, may reallocate
        ON_Curve* crvCopy = curve->DuplicateCurve();
        if (!crvCopy) throw std::runtime_error("Failed to duplicate curve");

        bool ok = RhinoExtendCurve(crvCopy, extType, side, length);

        if (!ok)
        {
            delete crvCopy;
            throw std::runtime_error("Extend failed");
        }

        // Replace the original object
        ON_3dmObjectAttributes attrs = obj->Attributes();
        CRhinoCurveObject* newObj = pDoc->AddCurveObject(*crvCopy, &attrs);
        delete crvCopy;
        crvCopy = nullptr;
        if (!newObj)
            throw std::runtime_error("Failed to add extended curve");

        ON_UUID newUuid = newObj->Attributes().m_uuid;
        pDoc->DeleteObject(CRhinoObjRef(obj));
        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(newUuid);
        wr.data["extended"] = endStr;
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

// ─── POST /curve/trim ──────────────────────────────────────────────

void HandleCurveTrim(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("t0") || !body["t0"].is_number() ||
        !body.contains("t1") || !body["t1"].is_number())
    {
        CRookServer::SendError(res, "Missing 't0' and 't1' fields (numbers 0-1)");
        return;
    }
    double t0Norm = body["t0"].get<double>();
    double t1Norm = body["t1"].get<double>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, t0Norm, t1Norm]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Trim Curve");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        ON_Interval domain = curve->Domain();
        double param0 = domain.ParameterAt(t0Norm);
        double param1 = domain.ParameterAt(t1Norm);

        ON_Curve* trimmed = curve->DuplicateCurve();
        if (!trimmed) throw std::runtime_error("Failed to duplicate curve");

        if (!trimmed->Trim(ON_Interval(param0, param1)))
        {
            delete trimmed;
            throw std::runtime_error("Trim failed");
        }

        // Replace original
        ON_3dmObjectAttributes attrs = obj->Attributes();
        CRhinoCurveObject* newObj = pDoc->AddCurveObject(*trimmed, &attrs);
        delete trimmed;
        if (!newObj)
            throw std::runtime_error("Failed to add trimmed curve");

        ON_UUID newUuid = newObj->Attributes().m_uuid;
        pDoc->DeleteObject(CRhinoObjRef(obj));
        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(newUuid);
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

// ─── POST /curve/split ─────────────────────────────────────────────

void HandleCurveSplit(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool hasParam = body.contains("parameter") && body["parameter"].is_number();
    bool hasPoint = body.contains("point") && body["point"].is_array();

    if (!hasParam && !hasPoint)
    {
        CRookServer::SendError(res, "Must provide 'parameter' (0-1) or 'point' ([x,y,z])");
        return;
    }

    double paramNorm = hasParam ? body["parameter"].get<double>() : 0;
    ON_3dPoint splitPoint = ON_3dPoint::UnsetPoint;
    if (hasPoint)
    {
        try { splitPoint = ParsePoint3d(body["point"]); }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, ex.what());
            return;
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, hasParam, paramNorm, splitPoint]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Split Curve");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        double t = 0;
        if (hasParam)
        {
            t = curve->Domain().ParameterAt(paramNorm);
        }
        else
        {
            if (!curve->GetClosestPoint(splitPoint, &t))
                throw std::runtime_error("Failed to find closest point on curve");
        }

        ON_Curve* left = nullptr;
        ON_Curve* right = nullptr;
        if (!curve->Split(t, left, right) || (!left && !right))
        {
            delete left;
            delete right;
            throw std::runtime_error("Split failed. Parameter may be at curve endpoint.");
        }

        ON_3dmObjectAttributes attrs = obj->Attributes();
        nlohmann::json resultIds = nlohmann::json::array();

        if (left)
        {
            CRhinoCurveObject* newObj = new CRhinoCurveObject(attrs);
            newObj->SetCurve(left);
            if (pDoc->AddObject(newObj))
                resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
            else
                delete newObj;
        }
        if (right)
        {
            CRhinoCurveObject* newObj = new CRhinoCurveObject(attrs);
            newObj->SetCurve(right);
            if (pDoc->AddObject(newObj))
                resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
            else
                delete newObj;
        }

        pDoc->DeleteObject(CRhinoObjRef(obj));
        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["createdCount"] = static_cast<int>(resultIds.size());
        wr.data["createdIds"] = std::move(resultIds);
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

// ─── POST /curve/rebuild ───────────────────────────────────────────

void HandleCurveRebuild(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "id"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    int pointCount = body.value("pointCount", 10);
    int degree = body.value("degree", 3);
    bool preserveTangents = body.value("preserveTangents", false);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, pointCount, degree, preserveTangents]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Rebuild Curve");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        ON_NurbsCurve* rebuilt = RhinoRebuildCurve(*curve, degree, pointCount, preserveTangents);
        if (!rebuilt)
            throw std::runtime_error("Rebuild failed. Point count may be too low for the given degree.");

        // Replace original
        ON_3dmObjectAttributes attrs = obj->Attributes();
        CRhinoCurveObject* newObj = pDoc->AddCurveObject(*rebuilt, &attrs);
        delete rebuilt;
        if (!newObj)
            throw std::runtime_error("Failed to add rebuilt curve");

        ON_UUID newUuid = newObj->Attributes().m_uuid;
        pDoc->DeleteObject(CRhinoObjRef(obj));
        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["id"] = UuidToString(newUuid);
        wr.data["pointCount"] = pointCount;
        wr.data["degree"] = degree;
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

// ─── POST /curve/fillet ────────────────────────────────────────────

void HandleCurveFillet(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid1, uuid2;
    try
    {
        uuid1 = ParseUuid(body, "id1");
        uuid2 = ParseUuid(body, "id2");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("radius") || !body["radius"].is_number())
    {
        CRookServer::SendError(res, "Missing 'radius' field (number)");
        return;
    }
    double radius = body["radius"].get<double>();
    if (radius <= 0)
    {
        CRookServer::SendError(res, "Radius must be positive");
        return;
    }

    bool join = body.value("join", true);
    bool trim = body.value("trim", true);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid1, uuid2, radius, join, trim]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Fillet Curves");

        // Use RunScript for reliability — direct curve fillet API is complex
        // Deselect all, select the two curves
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);

        const CRhinoObject* obj1 = pDoc->LookupObject(uuid1);
        const CRhinoObject* obj2 = pDoc->LookupObject(uuid2);
        if (!obj1 || !obj2) throw std::invalid_argument("One or both curves not found");

        const_cast<CRhinoObject*>(obj1)->Select(true);
        const_cast<CRhinoObject*>(obj2)->Select(true);

        // Build command
        ON_wString joinStr = join ? L"_Yes" : L"_No";
        ON_wString trimStr = trim ? L"_Yes" : L"_No";

        wchar_t script[512];
        swprintf_s(script, 512,
            L"_-FilletCrv _Radius=%g _Join=%ls _Trim=%ls _Enter _Enter",
            radius,
            static_cast<const wchar_t*>(joinStr),
            static_cast<const wchar_t*>(trimStr));

        ObjectDiffTracker tracker(pDoc);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), script, 0);
        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        WriteResult wr;
        if (newIds.empty())
        {
            wr.success = false;
            wr.data["error"] = "Fillet produced no results. Curves may not intersect or radius may be too large.";
            return wr;
        }

        nlohmann::json resultIds = nlohmann::json::array();
        for (const auto& id : newIds)
            resultIds.push_back(UuidToString(id));

        wr.success = true;
        wr.data["createdCount"] = static_cast<int>(newIds.size());
        wr.data["createdIds"] = std::move(resultIds);
        wr.data["radius"] = radius;
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

// ─── POST /curve/project ───────────────────────────────────────────

void HandleCurveProject(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::vector<ON_UUID> curveIds, brepIds;
    try
    {
        curveIds = ParseUuids(body, "curveIds");
        brepIds = ParseUuids(body, "brepIds");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("direction"))
    {
        CRookServer::SendError(res, "Missing 'direction' field ([x,y,z])");
        return;
    }

    ON_3dVector direction;
    try { direction = ParseVector3d(body["direction"]); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, curveIds = std::move(curveIds), brepIds = std::move(brepIds),
         direction, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Project Curves");

        double tol = (tolerance > 0) ? tolerance : pDoc->AbsoluteTolerance();

        // Collect curves and breps
        ON_SimpleArray<const ON_Curve*> curves;
        ON_SimpleArray<const ON_Brep*> breps;
        std::vector<ON_Brep*> tempBreps; // for cleanup

        for (const auto& uuid : curveIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) throw std::invalid_argument("Curve not found: " + UuidToString(uuid));
            const ON_Curve* crv = ON_Curve::Cast(obj->Geometry());
            if (!crv) throw std::invalid_argument("Object is not a curve: " + UuidToString(uuid));
            curves.Append(crv);
        }

        for (const auto& uuid : brepIds)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) throw std::invalid_argument("Brep not found: " + UuidToString(uuid));

            const ON_Geometry* geom = obj->Geometry();
            if (const ON_Brep* brep = ON_Brep::Cast(geom))
            {
                breps.Append(brep);
            }
            else if (const ON_Extrusion* ext = ON_Extrusion::Cast(geom))
            {
                ON_Brep* tempBrep = ext->BrepForm();
                if (tempBrep)
                {
                    tempBreps.push_back(tempBrep);
                    breps.Append(tempBrep);
                }
            }
            else
            {
                throw std::invalid_argument("Object is not a brep: " + UuidToString(uuid));
            }
        }

        ON_SimpleArray<ON_Curve*> outCurves;
        ON_SimpleArray<int> curveIndices, brepIndices;

        bool ok = RhinoProjectCurvesToBreps(breps, curves, direction,
            outCurves, curveIndices, brepIndices, tol);

        // Clean up temp breps
        for (auto* tb : tempBreps) delete tb;

        if (!ok || outCurves.Count() == 0)
            throw std::runtime_error("Projection produced no results");

        nlohmann::json resultIds = nlohmann::json::array();
        for (int i = 0; i < outCurves.Count(); ++i)
        {
            CRhinoCurveObject* newObj = new CRhinoCurveObject();
            newObj->SetCurve(outCurves[i]);  // takes ownership
            outCurves[i] = nullptr;
            if (pDoc->AddObject(newObj))
                resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
            else
                delete newObj;
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["projectedCount"] = static_cast<int>(resultIds.size());
        wr.data["projectedIds"] = std::move(resultIds);
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

// ─── POST /curve/pull ──────────────────────────────────────────────

void HandleCurvePull(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID curveUuid, brepUuid;
    try
    {
        curveUuid = ParseUuid(body, "curveId");
        brepUuid = ParseUuid(body, "brepId");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    int faceIndex = body.value("faceIndex", -1);
    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, curveUuid, brepUuid, faceIndex, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Pull Curve");

        double tol = (tolerance > 0) ? tolerance : pDoc->AbsoluteTolerance();

        const CRhinoObject* crvObj = pDoc->LookupObject(curveUuid);
        if (!crvObj) throw std::invalid_argument("Curve not found");
        const ON_Curve* curve = ON_Curve::Cast(crvObj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        const CRhinoObject* brepObj = pDoc->LookupObject(brepUuid);
        if (!brepObj) throw std::invalid_argument("Brep not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(brepObj->Geometry(), bMustDelete);
        if (!brep) throw std::invalid_argument("Object is not a brep");
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);

        // Determine which face to pull to
        int fi = (faceIndex >= 0 && faceIndex < brep->m_F.Count())
            ? faceIndex : 0;

        ON_SimpleArray<ON_Curve*> outCurves;
        int count = RhinoPullCurveToFace(brep->m_F[fi], *curve, outCurves, tol);

        if (count == 0 || outCurves.Count() == 0)
            throw std::runtime_error("Pull produced no results");

        nlohmann::json resultIds = nlohmann::json::array();
        for (int i = 0; i < outCurves.Count(); ++i)
        {
            CRhinoCurveObject* newObj = new CRhinoCurveObject();
            newObj->SetCurve(outCurves[i]);  // takes ownership
            outCurves[i] = nullptr;
            if (pDoc->AddObject(newObj))
                resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
            else
                delete newObj;
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["pulledCount"] = static_cast<int>(resultIds.size());
        wr.data["pulledIds"] = std::move(resultIds);
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

// ─── POST /curve/offset ────────────────────────────────────────────

void HandleCurveOffset(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID uuid;
    try { uuid = ParseUuid(body, "curveId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("distance") || !body["distance"].is_number())
    {
        CRookServer::SendError(res, "Missing 'distance' field (number)");
        return;
    }
    double distance = body["distance"].get<double>();
    int cornerStyle = body.value("cornerStyle", 1); // 1 = Sharp

    // Extract plane normal before dispatch to avoid capturing full JSON body
    ON_3dVector planeNormal(0, 0, 1); // Default: World XY
    if (body.contains("plane") && body["plane"].is_object())
    {
        auto& planeJson = body["plane"];
        if (planeJson.contains("normal"))
        {
            auto n = planeJson["normal"];
            if (n.is_array() && n.size() >= 3)
                planeNormal = ON_3dVector(n[0].get<double>(), n[1].get<double>(), n[2].get<double>());
        }
    }
    planeNormal.Unitize();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, uuid, distance, cornerStyle, planeNormal]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Offset Curve");

        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) throw std::invalid_argument("Object not found");

        const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        double tol = pDoc->AbsoluteTolerance();
        ON_3dVector normal = planeNormal;

        // Compute direction point: midpoint + perpendicular * distance
        ON_3dPoint midPt;
        ON_3dVector tangent;
        curve->EvTangent(curve->Domain().Mid(), midPt, tangent);

        ON_3dVector perp = ON_CrossProduct(tangent, normal);
        if (perp.Length() < 1e-10)
            perp = ON_3dVector(0, 1, 0);
        perp.Unitize();

        ON_3dPoint directionPoint = midPt + perp * distance;

        ON_SimpleArray<ON_Curve*> outCurves;
        int count = RhinoOffsetCurve(*curve, fabs(distance), directionPoint, normal,
            cornerStyle, tol, outCurves);

        if (count == 0 || outCurves.Count() == 0)
            throw std::runtime_error("Offset produced no results");

        nlohmann::json resultIds = nlohmann::json::array();
        for (int i = 0; i < outCurves.Count(); ++i)
        {
            CRhinoCurveObject* newObj = new CRhinoCurveObject();
            newObj->SetCurve(outCurves[i]);
            outCurves[i] = nullptr;
            if (pDoc->AddObject(newObj))
                resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
            else
                delete newObj;
        }

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["offsetCount"] = static_cast<int>(resultIds.size());
        wr.data["offsetIds"] = std::move(resultIds);
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

// ─── POST /curve/offset-on-surface ─────────────────────────────────

void HandleCurveOffsetOnSurface(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID curveUuid, surfaceUuid;
    try
    {
        curveUuid = ParseUuid(body, "curveId");
        surfaceUuid = ParseUuid(body, "surfaceId");
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("distance") || !body["distance"].is_number())
    {
        CRookServer::SendError(res, "Missing 'distance' field (number)");
        return;
    }
    double distance = body["distance"].get<double>();
    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, curveUuid, surfaceUuid, distance, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Offset on Surface");

        const CRhinoObject* crvObj = pDoc->LookupObject(curveUuid);
        if (!crvObj) throw std::invalid_argument("Curve not found");
        const ON_Curve* curve = ON_Curve::Cast(crvObj->Geometry());
        if (!curve) throw std::invalid_argument("Object is not a curve");

        const CRhinoObject* srfObj = pDoc->LookupObject(surfaceUuid);
        if (!srfObj) throw std::invalid_argument("Surface not found");

        // Validate that the surface object is a brep/surface/extrusion
        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(srfObj->Geometry(), bMustDelete);
        if (!brep) throw std::invalid_argument("Object is not a surface/brep");
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);

        // Use RunScript for offset on surface — direct API is complex
        // Deselect all, select curve
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* o = clearIt.First(); o; o = clearIt.Next())
            const_cast<CRhinoObject*>(o)->Select(false);
        const_cast<CRhinoObject*>(crvObj)->Select(true);

        ON_wString wSurfaceUuid = Utf8ToWide(UuidToString(surfaceUuid));
        wchar_t script[512];
        swprintf_s(script, 512,
            L"_-OffsetCrvOnSrf %g _SelId %ls _Enter",
            distance,
            static_cast<const wchar_t*>(wSurfaceUuid));

        ObjectDiffTracker tracker(pDoc);
        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), script, 0);
        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        if (newIds.empty())
            throw std::runtime_error("Offset on surface produced no results");

        nlohmann::json resultIds = nlohmann::json::array();
        for (const auto& id : newIds)
            resultIds.push_back(UuidToString(id));

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["offsetCount"] = static_cast<int>(newIds.size());
        wr.data["offsetIds"] = std::move(resultIds);
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

// ─── POST /curve/blend ──────────────────────────────────────────────
//
// Phase 2 PR-1 worked example. Blend between two existing curves at a
// given continuity via Curve.CreateBlendCurve (overload 1:
// curveA, curveB, continuity). Singular-contract route (bare
// ObjectSnapshot on success).
//
// Substrate: `managed-bridge (reuse)` via existing CreateGeometry
// callback (NativeGhBridgeRegistrar.cs:107). New type "BLEND_CRV" in
// CreateHandler.cs:150 singular switch. Zero ABI bump. **First mixed-
// substrate route in CurvesHandler.cpp** — the 12 routes above use the
// direct-sdk substrate; this route and the future /curve/boolean (PR-4)
// delegate to managed.
//
// First strict-attribute creator whose factory returns a Curve (not a
// Brep) — managed singular path at CreateHandler.cs:246 uses
// `doc.Objects.Add(geometry, attributes)` (class-agnostic) and
// RhinoSerializer.SerializeObject handles curves the same as breps.
// Strict-curve parity pinned by test_blend_curves_live.py (f) + (h).
//
// Worker-thread validation: curve1Id + curve2Id UUID format; continuity
// enum (Position | Tangency | Curvature); attribute bundle. Managed
// re-validates object-existence and is-a-curve with structured errors
// that round-trip through EmitNormalized unchanged.
//
// Factory permissiveness: Curve.CreateBlendCurve (overload 1) empirically
// accepts coincident, zero-length, and degenerate inputs (2026-04-20
// probe against live Rhino). Per Common Plan permissiveness amendment
// (rook_docs/2026-04-17-typed-route-phase1-plan.md:257), this route
// ships with a test_factory_permissive_smoke test rather than an
// operation_failed test.
//
// Explicit rejections from PR-1 scope: reverse1/reverse2 (overload 3
// params), bulgeA/bulgeB (overload 2), asymmetric per-end continuity
// (overload 3).

void HandleBlendCurves(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // curve1Id / curve2Id: required, UUID format.
    try { (void)ParseUuid(body, "curve1Id"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    try { (void)ParseUuid(body, "curve2Id"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    // continuity: optional enum.
    if (body.contains("continuity"))
    {
        if (!body["continuity"].is_string())
        {
            invalidInput(
                "Field 'continuity' must be a string (Position | Tangency | Curvature)",
                "invalid_continuity");
            return;
        }
        const std::string cont = body["continuity"].get<std::string>();
        if (!(cont == "Position" || cont == "Tangency" || cont == "Curvature"))
        {
            invalidInput(
                std::string("Invalid continuity: '") + cont
                    + "'. Must be Position, Tangency, or Curvature.",
                "invalid_continuity");
            return;
        }
    }

    // Attribute bundle (name/layer/color/visible) — syntactic checks.
    if (body.contains("name") && !body["name"].is_string())
    {
        invalidInput("Field 'name' must be a string");
        return;
    }
    if (body.contains("layer"))
    {
        if (!body["layer"].is_string() || body["layer"].get<std::string>().empty())
        {
            invalidInput("Field 'layer' must be a non-empty string");
            return;
        }
    }
    if (body.contains("visible") && !body["visible"].is_boolean())
    {
        invalidInput("Field 'visible' must be a boolean");
        return;
    }
    if (body.contains("color"))
    {
        try { (void)ParseColor(body, "color"); }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }

    body["type"] = "BLEND_CRV";
    body["_strictAttributes"] = true;

    Rook::Infrastructure::DispatchToManagedCreate(body.dump(), res);
}

// --- POST /curve/boolean -----------------------------------------------
//
// Phase 2 PR-4. Three intent keys (curve_boolean_union /
// curve_boolean_difference / curve_boolean_intersection) dispatch to
// this ONE endpoint via an `operation` discriminator — mirrors the
// Phase 1 brep-boolean 4-intent-to-1-endpoint pattern.
//
// Substrate: managed-bridge (reuse) via the `CreateGeometry` callback.
// No ABI bump. Native owns worker-thread schema validation; managed
// (CreateHandler.CreateCurveBooleanPlural) owns curve resolution,
// factory dispatch, and {objects: [...]} plural envelope emission via
// the new InsertCurvesAsPluralResponse helper.
//
// Worker-thread validations (all rejections surface as structured errors):
//   - operation: required string; must be one of
//       "union" | "difference" | "intersection"
//   - curveIds: required array of UUID strings
//       * operation=union        => size >= 2
//       * operation=difference   => size == 2 (curveA, curveB pair)
//       * operation=intersection => size == 2 (curveA, curveB pair)
//   - tolerance: optional positive number (default doc.ModelAbsoluteTolerance
//     applied managed-side). Factory empirically does NOT silently coerce
//     non-positive tolerances — it returns an empty Curve[]. Reject on
//     worker thread for contract clarity and diagnostic specificity.
//   - attribute bundle: name / layer / color / visible syntactic checks.
//
// Managed-side validations delegated to CreateHandler.CreateCurveBooleanPlural:
//   - curveId object existence + class (Curve) check.
//   - Factory null OR empty result -> operation_failed with diagnostic
//     message. Factory produces empty for many reasons (non-coplanar
//     inputs, open curves, self-intersecting inputs, disjoint
//     intersection, "fully erased" difference) — no route-specific
//     error code attempts to classify.
//
// Factory error surface: the three `Curve.CreateBoolean*` factories
// return `Curve[]` with no `out int error` parameter. Empty result
// (Length==0) is the sole failure signal. Empirically observed failure
// branches (2026-04-20 probe): non-coplanar pair, open/closed mix,
// parallel-plane-different-Z pair, zero-length curve, self-intersecting
// figure-8, disjoint intersection, fully-erased difference
// (inner - outer), non-positive tolerance. All collapse to
// `operation_failed` per PR-3 precedent.
//
// Factory permissiveness: coincident, tangent-point-touching, and
// nested (outer containing inner) inputs all succeed. Pinned by
// test_factory_permissive_smoke (nested union absorbs inner).
//
// Explicit non-goals (deferred):
//   - Region form Curve.CreateBooleanRegions (point-picker schema)
//   - Difference 1-minuend + N-subtractor overload (asymmetric arity)
//   - combineRegions flag (region-form parameter)
//   - InsertGeometryAsPluralResponse generic over GeometryBase subclass

void HandleCurveBoolean(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);
    (void)docSn;

    auto invalidInput = [&](const std::string& message, const char* code = "invalid_input") {
        nlohmann::json err = {
            {"errorCode", code},
            {"errorMessage", message},
        };
        CRookServer::SendErrorData(res, err);
    };

    // operation: required, string, enum.
    if (!body.contains("operation"))
    {
        invalidInput("Missing required field 'operation' (union | difference | intersection)");
        return;
    }
    if (!body["operation"].is_string())
    {
        invalidInput("Field 'operation' must be a string");
        return;
    }
    const std::string operation = body["operation"].get<std::string>();
    if (!(operation == "union" || operation == "difference" || operation == "intersection"))
    {
        invalidInput(
            std::string("Invalid operation: '") + operation
                + "'. Must be union, difference, or intersection.",
            "invalid_operation");
        return;
    }

    // curveIds: required, array, UUID format per element.
    if (!body.contains("curveIds") || !body["curveIds"].is_array())
    {
        invalidInput("Missing or invalid 'curveIds' (expected array of UUID strings)");
        return;
    }
    const size_t count = body["curveIds"].size();
    if (operation == "union")
    {
        if (count < 2)
        {
            invalidInput(
                std::string("Curve boolean union requires at least 2 curves, got ")
                    + std::to_string(count),
                "invalid_curve_count");
            return;
        }
    }
    else // difference | intersection
    {
        if (count != 2)
        {
            invalidInput(
                std::string("Curve boolean ") + operation
                    + " requires exactly 2 curves, got " + std::to_string(count),
                "invalid_curve_count");
            return;
        }
    }
    try { (void)ParseUuids(body, "curveIds"); }
    catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }

    // tolerance: optional, positive number.
    if (body.contains("tolerance"))
    {
        if (!body["tolerance"].is_number() || body["tolerance"].get<double>() <= 0.0)
        {
            invalidInput("Field 'tolerance' must be a positive number");
            return;
        }
    }

    // Attribute bundle: name / layer / color / visible.
    if (body.contains("name") && !body["name"].is_string())
    {
        invalidInput("Field 'name' must be a string");
        return;
    }
    if (body.contains("layer"))
    {
        if (!body["layer"].is_string() || body["layer"].get<std::string>().empty())
        {
            invalidInput("Field 'layer' must be a non-empty string");
            return;
        }
    }
    if (body.contains("visible") && !body["visible"].is_boolean())
    {
        invalidInput("Field 'visible' must be a boolean");
        return;
    }
    if (body.contains("color"))
    {
        try { (void)ParseColor(body, "color"); }
        catch (const std::invalid_argument& ex) { invalidInput(ex.what()); return; }
    }

    body["type"] = "CURVE_BOOLEAN";
    body["_strictAttributes"] = true;

    Rook::Infrastructure::DispatchToManagedCreate(body.dump(), res);
}

} // namespace Handlers
} // namespace Rook
