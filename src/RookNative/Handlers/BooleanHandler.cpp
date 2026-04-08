// BooleanHandler.cpp
//
// POST /boolean — Boolean union, difference, intersection, or split
//
// Uses RunScript with ObjectDiffTracker to capture results.
// This is more reliable than direct C++ SDK boolean functions, which
// have tricky memory ownership and uncertain signatures across SDK versions.

#include "stdafx.h"
#include "Handlers/BooleanHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── POST /boolean ──────────────────────────────────────────────────

void HandleBoolean(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("operation") || !body["operation"].is_string())
    {
        CRookServer::SendError(res, "Missing 'operation' field (union|difference|intersection|split)");
        return;
    }
    if (!body.contains("ids") || !body["ids"].is_array() || body["ids"].size() < 2)
    {
        CRookServer::SendError(res, "Need at least 2 object IDs in 'ids' array");
        return;
    }

    std::string operation = body["operation"].get<std::string>();
    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    bool keepOriginals = body.value("keepOriginals", false);

    // Validate operation name
    if (!IEquals(operation, "union") && !IEquals(operation, "difference") &&
        !IEquals(operation, "intersection") && !IEquals(operation, "split"))
    {
        CRookServer::SendError(res, "Unknown operation '" + operation +
            "'. Use: union, difference, intersection, split");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, operation, ids = std::move(ids), keepOriginals]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Boolean");

        // Validate all objects exist and are brep-like
        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj)
                throw std::invalid_argument("Object not found: " + UuidToString(uuid));

            const ON_Geometry* geom = obj->Geometry();
            if (!ON_Brep::Cast(geom) && !ON_Extrusion::Cast(geom))
                throw std::invalid_argument("Object " + UuidToString(uuid) +
                    " is not a Brep or Extrusion (type: " + ObjectTypeToString(obj->ObjectType()) + ")");
        }

        // Deselect all
        CRhinoObjectIterator clearIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = clearIt.First(); obj; obj = clearIt.Next())
            const_cast<CRhinoObject*>(obj)->Select(false);

        // Build the boolean command string.
        // Union takes a single set — pre-select all, one _Enter.
        // Difference, intersection, and split require TWO sets:
        //   Set 1 = target (ids[0]), Set 2 = cutters (ids[1..n]).
        //   Pre-select only the target, _Enter to confirm set 1,
        //   then use _SelId to select each cutter for set 2.
        ON_wString command;
        if (IEquals(operation, "union"))
        {
            // Select all objects for union (single set)
            for (const auto& uuid : ids)
            {
                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (obj)
                    const_cast<CRhinoObject*>(obj)->Select(true);
            }
            command = L"_-BooleanUnion _Enter";
        }
        else
        {
            // Two-set operations: pre-select only the target (ids[0])
            const CRhinoObject* target = pDoc->LookupObject(ids[0]);
            if (target)
                const_cast<CRhinoObject*>(target)->Select(true);

            // Start command + _Enter confirms set 1 from pre-selection
            if (IEquals(operation, "difference"))
                command = L"_-BooleanDifference _Enter";
            else if (IEquals(operation, "intersection"))
                command = L"_-BooleanIntersection _Enter";
            else if (IEquals(operation, "split"))
                command = L"_-BooleanSplit _Enter";

            // During "select set 2" prompt, use _SelId for each cutter
            for (size_t i = 1; i < ids.size(); ++i)
            {
                command += L" _SelId ";
                command += Utf8ToWide(UuidToString(ids[i]));
            }
            command += L" _Enter";
        }

        // Track new objects
        ObjectDiffTracker tracker(pDoc);

        RhinoApp().RunScript(pDoc->RuntimeSerialNumber(),
            static_cast<const wchar_t*>(command), 0);

        std::vector<ON_UUID> newIds = tracker.GetNewObjects();

        // Determine which originals were deleted
        bool deletedOriginals = false;
        if (!keepOriginals)
        {
            // Check if originals still exist (boolean commands typically delete them)
            for (const auto& uuid : ids)
            {
                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (!obj || obj->IsDeleted())
                {
                    deletedOriginals = true;
                    break;
                }
            }
        }

        WriteResult wr;
        if (newIds.empty() && !deletedOriginals)
        {
            wr.success = false;
            wr.data["error"] = "Boolean " + operation + " produced no results. "
                "Objects may not overlap or may not be valid solids.";
            wr.data["operation"] = operation;
            wr.data["inputCount"] = static_cast<int>(ids.size());
            return wr;
        }

        nlohmann::json resultIds = nlohmann::json::array();
        for (const auto& uuid : newIds)
            resultIds.push_back(UuidToString(uuid));

        wr.success = true;
        wr.data["operation"] = operation;
        wr.data["resultCount"] = static_cast<int>(newIds.size());
        wr.data["resultIds"] = std::move(resultIds);
        wr.data["deletedOriginals"] = deletedOriginals;
        wr.data["inputCount"] = static_cast<int>(ids.size());

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
