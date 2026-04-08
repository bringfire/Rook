// GumballHandler.cpp
//
// POST /gumball/activate    — Enable persistent gumball on selected objects
// POST /gumball/deactivate  — Disable gumball mode
// GET  /gumball/status      — Current mode, drag count, cumulative transform
// GET  /gumball/history     — Drag history records
//
// C26 note: Gumball drags are tracked here via /gumball/history, NOT in
// /session/history. Rationale: gumball drags are interactive transforms
// (mouse-driven, sub-command granularity), not Rhino commands. Mixing them
// into the session command list would pollute it with non-command entries.
// Clients that need a unified view should query both endpoints.

#include "stdafx.h"
#include "Handlers/GumballHandler.h"
#include "Interactive/GumballManager.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"
#include <memory>

namespace Rook {
namespace Handlers {

namespace {

struct GumballOpResult
{
    bool success = false;
    std::string error;
    std::string geometryType;
    std::string booleanOperation;
    std::vector<ON_UUID> createdIds;
    std::vector<ON_UUID> deletedIds;
};

static ON_3dVector ParseDirection(const nlohmann::json& body)
{
    ON_3dVector dir = ON_3dVector::ZAxis;
    if (body.contains("direction") && body["direction"].is_array() && body["direction"].size() >= 3)
    {
        dir = ON_3dVector(
            body["direction"][0].get<double>(),
            body["direction"][1].get<double>(),
            body["direction"][2].get<double>());
    }
    return dir;
}

static GumballOpResult ExtrudeCurveObject(
    CRhinoDoc* pDoc,
    const CRhinoObject* pObj,
    const ON_Curve& curve,
    const ON_3dVector& direction,
    double distance,
    bool cap)
{
    GumballOpResult result;
    result.geometryType = "curve";

    ON_3dVector unitDir = direction;
    if (!unitDir.Unitize())
    {
        result.error = "Direction must be non-zero";
        return result;
    }

    std::unique_ptr<ON_Extrusion> extrusion(ON_Extrusion::CreateFrom3dCurve(
        curve,
        nullptr,
        distance,
        cap,
        nullptr));
    if (!extrusion)
    {
        result.error = "Failed to create extrusion";
        return result;
    }

    const CRhinoExtrusionObject* added = pDoc->AddExtrusionObject(*extrusion, &pObj->Attributes());
    if (!added)
    {
        result.error = "Failed to add extrusion object";
        return result;
    }

    result.success = true;
    result.createdIds.push_back(added->Attributes().m_uuid);
    return result;
}

static const ON_Brep* ResolveBrepGeometry(const CRhinoObject* pObj, std::unique_ptr<ON_Brep>& ownedBrep)
{
    if (const ON_Brep* brep = ON_Brep::Cast(pObj->Geometry()))
        return brep;

    if (pObj->Geometry() && pObj->Geometry()->HasBrepForm())
    {
        ownedBrep.reset(pObj->Geometry()->BrepForm());
        return ownedBrep.get();
    }

    return nullptr;
}

static GumballOpResult ExtrudeBrepFace(
    CRhinoDoc* pDoc,
    const CRhinoObject* pObj,
    const ON_Brep& brep,
    int faceIndex,
    const ON_3dVector& direction)
{
    GumballOpResult result;
    result.geometryType = "face";

    if (faceIndex < 0 || faceIndex >= brep.m_F.Count())
    {
        result.error = "Face index out of range";
        return result;
    }

    std::unique_ptr<ON_Brep> newBrep(brep.Duplicate());
    if (!newBrep)
    {
        result.error = "Failed to duplicate Brep";
        return result;
    }

    ON_LineCurve pathCurve(ON_3dPoint::Origin, ON_3dPoint(direction));
    int extrudeResult = ON_BrepExtrudeFace(*newBrep, faceIndex, pathCurve, true);
    if (extrudeResult <= 0)
    {
        result.error = "Failed to extrude face";
        return result;
    }

    CRhinoObjRef objRef(pObj);
    if (!pDoc->ReplaceObject(objRef, *newBrep))
    {
        result.error = "Failed to replace object with extruded face result";
        return result;
    }

    const CRhinoObject* replaced = pDoc->LookupObject(pObj->Attributes().m_uuid);
    if (replaced)
        result.createdIds.push_back(replaced->Attributes().m_uuid);
    result.success = true;
    return result;
}

static GumballOpResult CutOrBossBrepFace(
    CRhinoDoc* pDoc,
    const CRhinoObject* pObj,
    const ON_Brep& brep,
    int faceIndex,
    const ON_3dVector& direction,
    double distance,
    bool cap)
{
    GumballOpResult result;
    const bool isCut = distance < 0.0;
    result.geometryType = "face";
    result.booleanOperation = isCut ? "difference" : "union";

    if (faceIndex < 0 || faceIndex >= brep.m_F.Count())
    {
        result.error = "Face index out of range";
        return result;
    }

    std::unique_ptr<ON_Brep> faceBrep(brep.DuplicateFace(faceIndex, false));
    if (!faceBrep || faceBrep->m_F.Count() == 0)
    {
        result.error = "Failed to duplicate face";
        return result;
    }

    ON_BrepLoop* outerLoop = faceBrep->m_F[0].OuterLoop();
    if (!outerLoop)
    {
        result.error = "Failed to find face outer loop";
        return result;
    }

    std::unique_ptr<ON_Curve> boundary(faceBrep->Loop3dCurve(*outerLoop));
    if (!boundary)
    {
        result.error = "Failed to extract face boundary curve";
        return result;
    }

    std::unique_ptr<ON_Extrusion> toolExtrusion(ON_Extrusion::CreateFrom3dCurve(
        *boundary,
        nullptr,
        distance,
        cap,
        nullptr));
    if (!toolExtrusion)
    {
        result.error = "Failed to create extrusion tool";
        return result;
    }

    std::unique_ptr<ON_Brep> toolBrep(toolExtrusion->BrepForm(nullptr));
    if (!toolBrep)
    {
        result.error = "Failed to convert extrusion tool to Brep";
        return result;
    }

    ON_SimpleArray<const ON_Brep*> in0;
    ON_SimpleArray<const ON_Brep*> in1;
    in0.Append(&brep);
    in1.Append(toolBrep.get());

    ON_SimpleArray<ON_Brep*> outBreps;
    bool boolResult = false;
    bool ok = false;
    ON_SimpleArray<int> inputIndexForOutput;
    const double tolerance = pDoc->AbsoluteTolerance();

    if (isCut)
    {
        ok = RhinoBooleanDifference(in0, in1, tolerance, &boolResult, outBreps, inputIndexForOutput, true, nullptr);
    }
    else
    {
        ON_SimpleArray<const ON_Brep*> unionInputs;
        unionInputs.Append(&brep);
        unionInputs.Append(toolBrep.get());
        ok = RhinoBooleanUnion(unionInputs, tolerance, &boolResult, outBreps, true, nullptr);
    }

    if (!ok || outBreps.Count() <= 0)
    {
        for (int i = 0; i < outBreps.Count(); ++i)
            delete outBreps[i];
        result.error = isCut
            ? "Boolean difference failed"
            : "Boolean union failed";
        return result;
    }

    ON_Brep* outBrep = outBreps[0];

    const CRhinoBrepObject* added = pDoc->AddBrepObject(*outBrep, &pObj->Attributes());
    for (int i = 1; i < outBreps.Count(); ++i)
        delete outBreps[i];
    delete outBrep;

    if (!added)
    {
        result.error = "Failed to add boolean result";
        return result;
    }

    pDoc->DeleteObject(pObj);
    result.createdIds.push_back(added->Attributes().m_uuid);
    result.deletedIds.push_back(pObj->Attributes().m_uuid);
    result.success = true;
    return result;
}

static nlohmann::json SerializeGumballOpResult(const ON_UUID& objectId, const GumballOpResult& op)
{
    nlohmann::json item;
    item["ObjectId"] = UuidToString(objectId);
    item["Success"] = op.success;
    item["Error"] = op.error.empty() ? nlohmann::json(nullptr) : nlohmann::json(op.error);
    item["GeometryType"] = op.geometryType;
    item["BooleanOperation"] = op.booleanOperation.empty() ? nlohmann::json(nullptr) : nlohmann::json(op.booleanOperation);

    auto created = nlohmann::json::array();
    for (const auto& id : op.createdIds)
        created.push_back(UuidToString(id));
    item["Created"] = std::move(created);

    auto deleted = nlohmann::json::array();
    for (const auto& id : op.deletedIds)
        deleted.push_back(UuidToString(id));
    item["Deleted"] = std::move(deleted);

    return item;
}

} // namespace

// ─── POST /gumball/activate ─────────────────────────────────────────

void HandleGumballActivate(const httplib::Request& req, httplib::Response& res)
{
    std::vector<std::string> ids;

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("ids") && body["ids"].is_array())
            {
                for (const auto& item : body["ids"])
                {
                    if (item.is_string())
                        ids.push_back(item.get<std::string>());
                }
            }
        }
    }

    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([&]() -> int {
            CGumballManager::Instance().Activate(ids);
            return static_cast<int>(ids.size());
        });

        int objectCount = future.get();

        nlohmann::json result;
        result["message"]     = "AI Gumball mode enabled. Drag handles to transform, Esc to pause.";
        result["enabled"]     = true;
        result["objectCount"] = objectCount;

        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error activating gumball: ") + ex.what());
    }
}

// ─── POST /gumball/deactivate ───────────────────────────────────────

void HandleGumballDeactivate(const httplib::Request& /*req*/, httplib::Response& res)
{
    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([]() {
            CGumballManager::Instance().Deactivate();
        });
        future.get();

        nlohmann::json result;
        result["message"] = "AI Gumball mode disabled.";
        result["enabled"] = false;

        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error deactivating gumball: ") + ex.what());
    }
}

// ─── GET /gumball/status ────────────────────────────────────────────

void HandleGumballStatus(const httplib::Request& /*req*/, httplib::Response& res)
{
    auto& mgr = CGumballManager::Instance();

    nlohmann::json result;
    result["enabled"]    = mgr.IsEnabled();
    result["dragActive"] = mgr.IsDragActive();
    result["dragCount"]  = mgr.GetDragCount();
    result["lastMode"]   = mgr.GetLastMode();

    auto xf = mgr.GetCumulativeTransform();
    auto xfArr = nlohmann::json::array();
    for (int i = 0; i < 16; i++)
        xfArr.push_back(xf[i]);
    result["cumulativeTransform"] = xfArr;

    CRookServer::SendSuccess(res, result);
}

// ─── GET /gumball/history ───────────────────────────────────────────

void HandleGumballHistory(const httplib::Request& req, httplib::Response& res)
{
    int limit = 20;
    if (req.has_param("limit"))
    {
        try { limit = std::stoi(req.get_param_value("limit")); }
        catch (...) {}
    }
    // C25 fix: Clamp invalid limits to prevent returning unbounded history.
    if (limit <= 0) limit = 20;

    auto history = CGumballManager::Instance().GetHistory(limit);

    auto arr = nlohmann::json::array();
    for (const auto& drag : history)
    {
        nlohmann::json d;
        d["dragIndex"]  = drag.dragIndex;
        d["handleMode"] = drag.handleMode;
        d["isCopy"]     = drag.isCopy;
        d["isRelocate"] = drag.isRelocate;
        d["timestamp"]  = drag.timestamp;
        d["dragDurationMs"] = drag.dragDurationMs;

        auto delta = nlohmann::json::array();
        for (int i = 0; i < 16; i++)
            delta.push_back(drag.deltaTransform[i]);
        d["deltaTransform"] = delta;

        auto cumulative = nlohmann::json::array();
        for (int i = 0; i < 16; i++)
            cumulative.push_back(drag.cumulativeTransform[i]);
        d["cumulativeTransform"] = cumulative;

        arr.push_back(d);
    }

    nlohmann::json result;
    result["count"]  = static_cast<int>(history.size());
    result["drags"]  = arr;

    CRookServer::SendSuccess(res, result);
}

// ─── POST /gumball/settings ────────────────────────────────────────

void HandleGumballSettings(const httplib::Request& req, httplib::Response& res)
{
    auto& mgr = CGumballManager::Instance();

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (body.is_discarded() || !body.is_object())
        {
            CRookServer::SendError(res, "Invalid JSON");
            return;
        }

        try
        {
            auto future = CMainThreadDispatcher::Instance().Dispatch([body, &mgr]() {
                if (body.contains("dragStrength"))
                {
                    double value = body["dragStrength"].get<double>();
                    if (value < 0.01) value = 0.01;
                    if (value > 10.0) value = 10.0;
                    mgr.SetDragStrength(value);
                }

                if (body.contains("autoReset"))
                    mgr.SetAutoReset(body["autoReset"].get<bool>());

                if (body.contains("snapEnabled"))
                    mgr.SetSnappy(body["snapEnabled"].get<bool>());

                if (body.contains("snapTranslate"))
                {
                    double value = body["snapTranslate"].get<double>();
                    mgr.SetSnapTranslate((std::max)(0.001, value));
                }

                if (body.contains("snapRotateDeg"))
                {
                    double value = body["snapRotateDeg"].get<double>();
                    mgr.SetSnapRotateDeg((std::max)(0.1, value));
                }

                if (body.contains("snapScale"))
                {
                    double value = body["snapScale"].get<double>();
                    mgr.SetSnapScale((std::max)(0.001, value));
                }

                if (body.contains("alignment"))
                {
                    const std::string alignment = body["alignment"].get<std::string>();
                    const auto mode = AlignmentModeFromString(alignment);
                    if (alignment != "world" && alignment != "cplane" && alignment != "object")
                        throw std::invalid_argument("Unknown alignment mode: '" + alignment + "'");
                    mgr.SetAlignment(mode);
                }
            });
            future.get();
        }
        catch (const std::exception& ex)
        {
            CRookServer::SendError(res, std::string("Invalid settings: ") + ex.what());
            return;
        }
    }

    nlohmann::json result;
    result["alignment"] = AlignmentModeToString(mgr.GetAlignment());
    result["dragStrength"] = mgr.GetDragStrength();
    result["autoReset"] = mgr.IsAutoReset();
    result["snapEnabled"] = mgr.IsSnappy();
    result["snapTranslate"] = mgr.GetSnapTranslate();
    result["snapRotateDeg"] = mgr.GetSnapRotateDeg();
    result["snapScale"] = mgr.GetSnapScale();

    CRookServer::SendSuccess(res, result);
}

// ─── POST /gumball/extrude ─────────────────────────────────────────

void HandleGumballExtrude(const httplib::Request& req, httplib::Response& res)
{
    if (req.body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }

    auto body = nlohmann::json::parse(req.body, nullptr, false);
    if (body.is_discarded() || !body.is_object())
    {
        CRookServer::SendError(res, "Invalid JSON");
        return;
    }

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (ids.empty())
    {
        CRookServer::SendError(res, "No valid object IDs provided");
        return;
    }

    const ON_3dVector direction = ParseDirection(body);
    const double distance = body.value("distance", 1.0);
    const bool cap = body.value("cap", true);
    const int faceIndex = body.value("faceIndex", -1);

    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([ids, direction, distance, cap, faceIndex]() {
            CRhinoDoc* pDoc = GetDocument();
            if (!pDoc)
                throw std::runtime_error("No active document");

            UndoScope undo(pDoc, L"AIGumball Extrude");
            auto results = nlohmann::json::array();

            for (const auto& objectId : ids)
            {
                GumballOpResult op;
                const CRhinoObject* pObj = pDoc->LookupObject(objectId);
                if (!pObj)
                {
                    op.error = "Object not found";
                    results.push_back(SerializeGumballOpResult(objectId, op));
                    continue;
                }

                if (const ON_Curve* curve = ON_Curve::Cast(pObj->Geometry()))
                {
                    op = ExtrudeCurveObject(pDoc, pObj, *curve, direction, distance, cap);
                }
                else
                {
                    std::unique_ptr<ON_Brep> ownedBrep;
                    const ON_Brep* brep = ResolveBrepGeometry(pObj, ownedBrep);
                    if (!brep)
                    {
                        op.error = "Object type not supported for extrude";
                    }
                    else
                    {
                        int resolvedFaceIndex = faceIndex;
                        if (resolvedFaceIndex < 0)
                            resolvedFaceIndex = 0;
                        op = ExtrudeBrepFace(pDoc, pObj, *brep, resolvedFaceIndex, direction * distance);
                    }
                }

                results.push_back(SerializeGumballOpResult(objectId, op));
            }

            pDoc->Redraw();
            return results;
        });

        CRookServer::SendSuccess(res, future.get());
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Extrude failed: ") + ex.what());
    }
}

// ─── POST /gumball/cut ─────────────────────────────────────────────

void HandleGumballCut(const httplib::Request& req, httplib::Response& res)
{
    if (req.body.empty())
    {
        CRookServer::SendError(res, "Request body required");
        return;
    }

    auto body = nlohmann::json::parse(req.body, nullptr, false);
    if (body.is_discarded() || !body.is_object())
    {
        CRookServer::SendError(res, "Invalid JSON");
        return;
    }

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (ids.empty())
    {
        CRookServer::SendError(res, "No valid object IDs provided");
        return;
    }

    const ON_3dVector direction = ParseDirection(body);
    const double distance = body.value("distance", -1.0);
    const int faceIndex = body.value("faceIndex", 0);

    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([ids, direction, distance, faceIndex]() {
            CRhinoDoc* pDoc = GetDocument();
            if (!pDoc)
                throw std::runtime_error("No active document");

            UndoScope undo(pDoc, L"AIGumball Cut");
            auto results = nlohmann::json::array();

            for (const auto& objectId : ids)
            {
                GumballOpResult op;
                const CRhinoObject* pObj = pDoc->LookupObject(objectId);
                if (!pObj)
                {
                    op.error = "Object not found";
                    results.push_back(SerializeGumballOpResult(objectId, op));
                    continue;
                }

                std::unique_ptr<ON_Brep> ownedBrep;
                const ON_Brep* brep = ResolveBrepGeometry(pObj, ownedBrep);
                if (!brep)
                {
                    op.error = "Object is not a Brep";
                }
                else
                {
                    op = CutOrBossBrepFace(pDoc, pObj, *brep, faceIndex, direction, distance, true);
                }

                results.push_back(SerializeGumballOpResult(objectId, op));
            }

            pDoc->Redraw();
            return results;
        });

        CRookServer::SendSuccess(res, future.get());
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Cut failed: ") + ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
