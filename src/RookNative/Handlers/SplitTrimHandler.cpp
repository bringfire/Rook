// SplitTrimHandler.cpp
//
// 3 split/trim routes using direct Rhino SDK global functions.
// RhinoBrepSplit() for splitting, RhinoSplitBrepFace() for face splitting.

#include "stdafx.h"
#include "Handlers/SplitTrimHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

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

// Create a plane surface large enough to cut the target brep (2x diagonal).
static ON_PlaneSurface* CreateCuttingPlane(const ON_Plane& plane, const ON_Brep& targetBrep)
{
    ON_BoundingBox bbox = targetBrep.BoundingBox();
    double diag = bbox.Diagonal().Length();
    if (diag < 1.0) diag = 100.0;
    double size = diag * 2.0;

    ON_PlaneSurface* ps = new ON_PlaneSurface(plane);
    // ON_PlaneSurface::SetDomain takes (int dir, double t0, double t1)
    ps->SetDomain(0, -size, size);
    ps->SetDomain(1, -size, size);
    ps->SetExtents(0, ON_Interval(-size, size));
    ps->SetExtents(1, ON_Interval(-size, size));
    return ps;
}

// ─── POST /split/brep ────────────────────────────────────────────

void HandleSplitBrep(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool hasCutters = body.contains("cutterIds") && body["cutterIds"].is_array();
    bool hasPlane = body.contains("plane") && body["plane"].is_object();

    if (!hasCutters && !hasPlane)
    {
        CRookServer::SendError(res, "Need 'cutterIds' array or 'plane' object");
        return;
    }

    std::vector<ON_UUID> cutterIds;
    ON_3dPoint planeOrigin;
    ON_3dVector planeNormal;

    if (hasCutters)
    {
        try { cutterIds = ParseUuids(body, "cutterIds"); }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, ex.what());
            return;
        }
    }

    if (hasPlane)
    {
        try {
            planeOrigin = ParsePoint3d(body["plane"], "origin");
            planeNormal = ParseVector3d(body["plane"], "normal");
        }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, std::string("Invalid plane: ") + ex.what());
            return;
        }
    }

    bool deleteOriginal = body.value("deleteOriginal", true);
    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId, cutterIds = std::move(cutterIds), hasPlane,
         planeOrigin, planeNormal, deleteOriginal, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double tol = (tolerance > 0.0) ? tolerance : pDoc->AbsoluteTolerance();
        UndoScope undo(pDoc, L"Split brep");

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Brep object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Object is not a brep/extrusion/surface");

        ON_SimpleArray<ON_Brep*> pieces;

        if (hasPlane)
        {
            ON_Plane plane(planeOrigin, planeNormal);
            std::unique_ptr<ON_PlaneSurface> ps(CreateCuttingPlane(plane, *brep));

            // Convert plane surface to brep for the cutter
            ON_Brep* cutterBrep = ps->BrepForm();
            std::unique_ptr<ON_Brep> cutterGuard(cutterBrep);

            if (cutterBrep)
            {
                ON_SimpleArray<const ON_Brep*> cutters;
                cutters.Append(cutterBrep);
                RhinoBrepSplit(*brep, cutters, tol, pieces);
            }
        }
        else
        {
            // Collect cutter geometry
            ON_SimpleArray<const ON_Brep*> brepCutters;
            ON_SimpleArray<const ON_Curve*> curveCutters;
            std::vector<std::unique_ptr<ON_Brep>> tempBreps;

            for (const auto& cId : cutterIds)
            {
                const CRhinoObject* cutObj = pDoc->LookupObject(cId);
                if (!cutObj)
                    throw std::invalid_argument("Cutter object not found: " + UuidToString(cId));

                const ON_Geometry* cutGeom = cutObj->Geometry();
                if (const ON_Curve* crv = ON_Curve::Cast(cutGeom))
                {
                    curveCutters.Append(crv);
                }
                else
                {
                    bool bDelCut = false;
                    const ON_Brep* cutBrep = ExtractBrep(cutGeom, bDelCut);
                    if (cutBrep)
                    {
                        brepCutters.Append(cutBrep);
                        if (bDelCut)
                            tempBreps.emplace_back(const_cast<ON_Brep*>(cutBrep));
                    }
                }
            }

            if (brepCutters.Count() > 0)
                RhinoBrepSplit(*brep, brepCutters, tol, pieces);
            else if (curveCutters.Count() > 0)
                RhinoBrepSplit(*brep, curveCutters, tol, pieces);
        }

        if (pieces.Count() <= 1)
        {
            // Clean up pieces if split failed
            for (int i = 0; i < pieces.Count(); ++i)
                delete pieces[i];

            WriteResult wr;
            wr.success = false;
            wr.data["error"] = "Split produced no result (objects may not intersect)";
            return wr;
        }

        // Add result pieces to document
        ON_3dmObjectAttributes attrs = obj->Attributes();
        nlohmann::json resultIds = nlohmann::json::array();

        for (int i = 0; i < pieces.Count(); ++i)
        {
            if (pieces[i])
            {
                CRhinoBrepObject* newObj = pDoc->AddBrepObject(*pieces[i], &attrs);
                if (newObj)
                    resultIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete pieces[i];
                pieces[i] = nullptr;
            }
        }

        bool deleted = false;
        if (deleteOriginal && !resultIds.empty())
        {
            pDoc->DeleteObject(CRhinoObjRef(obj));
            deleted = true;
        }

        WriteResult wr;
        wr.success = true;
        wr.data["resultCount"] = static_cast<int>(resultIds.size());
        wr.data["resultIds"] = std::move(resultIds);
        wr.data["originalDeleted"] = deleted;

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

// ─── POST /trim/brep ─────────────────────────────────────────────

void HandleTrimBrep(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool hasCutter = body.contains("cutterId") && body["cutterId"].is_string();
    bool hasPlane = body.contains("plane") && body["plane"].is_object();

    if (!hasCutter && !hasPlane)
    {
        CRookServer::SendError(res, "Need 'cutterId' or 'plane' object");
        return;
    }

    ON_UUID cutterId = ON_nil_uuid;
    ON_3dPoint planeOrigin;
    ON_3dVector planeNormal;

    if (hasCutter)
    {
        try { cutterId = ParseUuid(body, "cutterId"); }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, ex.what());
            return;
        }
    }

    if (hasPlane)
    {
        try {
            planeOrigin = ParsePoint3d(body["plane"], "origin");
            planeNormal = ParseVector3d(body["plane"], "normal");
        }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendError(res, std::string("Invalid plane: ") + ex.what());
            return;
        }
    }

    int keepSide = body.value("keepSide", 0);
    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId, cutterId, hasCutter, hasPlane,
         planeOrigin, planeNormal, keepSide, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double tol = (tolerance > 0.0) ? tolerance : pDoc->AbsoluteTolerance();
        UndoScope undo(pDoc, L"Trim brep");

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Brep object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Object is not a brep/extrusion/surface");

        // Split first, then keep the desired piece
        ON_SimpleArray<ON_Brep*> pieces;
        ON_Plane splitPlane;
        bool haveSplitPlane = false;

        if (hasPlane)
        {
            splitPlane = ON_Plane(planeOrigin, planeNormal);
            haveSplitPlane = true;

            std::unique_ptr<ON_PlaneSurface> ps(CreateCuttingPlane(splitPlane, *brep));
            ON_Brep* cutterBrep = ps->BrepForm();
            std::unique_ptr<ON_Brep> cutterGuard(cutterBrep);

            if (cutterBrep)
            {
                ON_SimpleArray<const ON_Brep*> cutters;
                cutters.Append(cutterBrep);
                RhinoBrepSplit(*brep, cutters, tol, pieces);
            }
        }
        else if (hasCutter)
        {
            const CRhinoObject* cutObj = pDoc->LookupObject(cutterId);
            if (!cutObj)
                throw std::invalid_argument("Cutter object not found");

            bool bDelCut = false;
            const ON_Brep* cutBrep = ExtractBrep(cutObj->Geometry(), bDelCut);
            std::unique_ptr<const ON_Brep> cutGuard(bDelCut ? cutBrep : nullptr);

            if (cutBrep)
            {
                ON_SimpleArray<const ON_Brep*> cutters;
                cutters.Append(cutBrep);
                RhinoBrepSplit(*brep, cutters, tol, pieces);
            }
        }

        if (pieces.Count() < 2)
        {
            for (int i = 0; i < pieces.Count(); ++i)
                delete pieces[i];

            WriteResult wr;
            wr.success = false;
            wr.data["error"] = "Trim produced no split (cutter may not intersect brep)";
            return wr;
        }

        // Sort pieces by distance to split plane (if available) or by index
        int keep = (std::min)(keepSide, pieces.Count() - 1);
        if (keep < 0) keep = 0;

        if (haveSplitPlane && pieces.Count() >= 2)
        {
            // Sort: piece on normal side first (positive distance), opposite side second
            ON_PlaneEquation eq;
            eq.Create(splitPlane.origin, splitPlane.Normal());

            // Compute center distance for each piece
            std::vector<std::pair<double, int>> dists;
            for (int i = 0; i < pieces.Count(); ++i)
            {
                ON_BoundingBox pbox = pieces[i]->BoundingBox();
                ON_3dPoint center = pbox.Center();
                double d = eq.ValueAt(center);
                dists.push_back({d, i});
            }

            // Sort by distance (most positive first = normal side)
            std::sort(dists.begin(), dists.end(),
                [](const auto& a, const auto& b) { return a.first > b.first; });

            keep = (keepSide < static_cast<int>(dists.size())) ? dists[keepSide].second : dists[0].second;
        }

        // Add the kept piece
        ON_3dmObjectAttributes attrs = obj->Attributes();
        CRhinoBrepObject* newObj = pDoc->AddBrepObject(*pieces[keep], &attrs);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;

        // Delete all pieces
        for (int i = 0; i < pieces.Count(); ++i)
        {
            delete pieces[i];
            pieces[i] = nullptr;
        }

        // Delete original
        pDoc->DeleteObject(CRhinoObjRef(obj));

        WriteResult wr;
        wr.success = true;
        wr.data["resultId"] = UuidToString(resultId);
        wr.data["piecesAvailable"] = pieces.Count();
        wr.data["keptPiece"] = keepSide;

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

// ─── POST /split/face ────────────────────────────────────────────

void HandleSplitFace(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("faceIndex") || !body["faceIndex"].is_number_integer())
    {
        CRookServer::SendError(res, "Missing 'faceIndex' integer");
        return;
    }
    int faceIndex = body["faceIndex"].get<int>();

    std::vector<ON_UUID> curveIds;
    try { curveIds = ParseUuids(body, "curveIds"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId, faceIndex, curveIds = std::move(curveIds), tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double tol = (tolerance > 0.0) ? tolerance : pDoc->AbsoluteTolerance();
        UndoScope undo(pDoc, L"Split face");

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Brep object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Object is not a brep/extrusion/surface");

        if (faceIndex < 0 || faceIndex >= brep->m_F.Count())
            throw std::invalid_argument("faceIndex out of range");

        // Collect cutting curves
        ON_SimpleArray<const ON_Curve*> curves;
        for (const auto& cId : curveIds)
        {
            const CRhinoObject* crvObj = pDoc->LookupObject(cId);
            if (!crvObj)
                throw std::invalid_argument("Curve not found: " + UuidToString(cId));
            const ON_Curve* crv = ON_Curve::Cast(crvObj->Geometry());
            if (!crv)
                throw std::invalid_argument("Object is not a curve: " + UuidToString(cId));
            curves.Append(crv);
        }

        ON_Brep* splitResult = RhinoSplitBrepFace(*brep, faceIndex, curves, tol);
        if (!splitResult)
        {
            WriteResult wr;
            wr.success = false;
            wr.data["error"] = "Face split produced no result";
            return wr;
        }

        ON_3dmObjectAttributes attrs = obj->Attributes();
        CRhinoBrepObject* newObj = pDoc->AddBrepObject(*splitResult, &attrs);
        ON_UUID resultId = newObj ? newObj->Attributes().m_uuid : ON_nil_uuid;
        int newFaceCount = splitResult->m_F.Count();

        delete splitResult;

        pDoc->DeleteObject(CRhinoObjRef(obj));

        WriteResult wr;
        wr.success = true;
        wr.data["resultId"] = UuidToString(resultId);
        wr.data["newFaceCount"] = newFaceCount;

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
