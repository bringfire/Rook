// OffsetBrepHandler.cpp
//
// POST /offset/brep — Offset brep with blend/wall surfaces.
// Uses RhinoOffsetBrep() global function.

#include "stdafx.h"
#include "Handlers/OffsetBrepHandler.h"
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

// ─── POST /offset/brep ──────────────────────────────────────────

void HandleOffsetBrep(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    ON_UUID brepId;
    try { brepId = ParseUuid(body, "brepId"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    if (!body.contains("distance") || !body["distance"].is_number())
    {
        CRookServer::SendError(res, "Missing 'distance' number");
        return;
    }

    double distance = body["distance"].get<double>();
    bool solid = body.value("solid", true);
    bool extend = body.value("extend", true);
    bool shrink = body.value("shrink", false);
    double tolerance = body.value("tolerance", 0.0);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, brepId, distance, solid, extend, shrink, tolerance]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        double tol = (tolerance > 0.0) ? tolerance : pDoc->AbsoluteTolerance();
        UndoScope undo(pDoc, L"Offset brep");

        const CRhinoObject* obj = pDoc->LookupObject(brepId);
        if (!obj)
            throw std::invalid_argument("Brep object not found");

        bool bMustDelete = false;
        const ON_Brep* brep = ExtractBrep(obj->Geometry(), bMustDelete);
        std::unique_ptr<const ON_Brep> brepGuard(bMustDelete ? brep : nullptr);
        if (!brep)
            throw std::invalid_argument("Object is not a brep/extrusion/surface");

        // Auto-detect: closed solids don't need walls
        bool actualSolid = solid;
        std::string note;
        if (brep->IsSolid() && solid)
        {
            actualSolid = false;
            note = "Input was already a closed solid; solid parameter was ignored (walls not needed)";
        }

        ON_SimpleArray<ON_Brep*> offsets;
        ON_SimpleArray<ON_Brep*> blends;
        ON_SimpleArray<ON_Brep*> walls;

        bool ok = RhinoOffsetBrep(*brep, distance, tol, actualSolid, extend, shrink,
                                   offsets, blends, walls);

        if (!ok || offsets.Count() == 0)
        {
            // Clean up
            for (int i = 0; i < offsets.Count(); ++i) delete offsets[i];
            for (int i = 0; i < blends.Count(); ++i) delete blends[i];
            for (int i = 0; i < walls.Count(); ++i) delete walls[i];

            WriteResult wr;
            wr.success = false;
            wr.data["error"] = "Offset brep failed (distance may be too large or geometry invalid)";
            return wr;
        }

        ON_3dmObjectAttributes attrs = obj->Attributes();

        nlohmann::json offsetIds = nlohmann::json::array();
        for (int i = 0; i < offsets.Count(); ++i)
        {
            if (offsets[i])
            {
                CRhinoBrepObject* newObj = pDoc->AddBrepObject(*offsets[i], &attrs);
                if (newObj)
                    offsetIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete offsets[i];
                offsets[i] = nullptr;
            }
        }

        nlohmann::json blendIds = nlohmann::json::array();
        for (int i = 0; i < blends.Count(); ++i)
        {
            if (blends[i])
            {
                CRhinoBrepObject* newObj = pDoc->AddBrepObject(*blends[i], &attrs);
                if (newObj)
                    blendIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete blends[i];
                blends[i] = nullptr;
            }
        }

        nlohmann::json wallIds = nlohmann::json::array();
        for (int i = 0; i < walls.Count(); ++i)
        {
            if (walls[i])
            {
                CRhinoBrepObject* newObj = pDoc->AddBrepObject(*walls[i], &attrs);
                if (newObj)
                    wallIds.push_back(UuidToString(newObj->Attributes().m_uuid));
                delete walls[i];
                walls[i] = nullptr;
            }
        }

        WriteResult wr;
        wr.success = true;
        wr.data["offsetCount"] = static_cast<int>(offsetIds.size());
        wr.data["offsetIds"] = std::move(offsetIds);
        wr.data["blendCount"] = static_cast<int>(blendIds.size());
        wr.data["blendIds"] = std::move(blendIds);
        wr.data["wallCount"] = static_cast<int>(wallIds.size());
        wr.data["wallIds"] = std::move(wallIds);
        if (!note.empty())
            wr.data["note"] = note;

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
