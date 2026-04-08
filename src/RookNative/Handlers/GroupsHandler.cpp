// GroupsHandler.cpp
//
// GET  /groups        — List all groups
// POST /group         — Create a group from object IDs
// POST /ungroup       — Delete a group by name or index
// GET  /group/members — Get objects belonging to a group

#include "stdafx.h"
#include "Handlers/GroupsHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

// Find a group by name (case-insensitive). Returns index or -1.
static int FindGroupIndex(CRhinoDoc* pDoc, const std::string& name)
{
    ON_wString wName = Utf8ToWide(name);
    // SDK provides FindGroupFromName (case-insensitive)
    int idx = pDoc->m_group_table.FindGroupFromName(wName);
    return (idx >= 0) ? idx : -1;
}

// ─── GET /groups ────────────────────────────────────────────────────

void HandleGetGroups(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        nlohmann::json groups = nlohmann::json::array();
        int count = pDoc->m_group_table.GroupCount();
        int activeCount = 0;

        for (int i = 0; i < count; ++i)
        {
            const CRhinoGroup* pGrp = pDoc->m_group_table[i];
            if (!pGrp || pGrp->IsDeleted()) continue;

            // Count members by iterating objects
            int memberCount = 0;
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
            {
                if (obj->Attributes().IsInGroup(i))
                    ++memberCount;
            }

            std::string name = WideToUtf8(pGrp->Name());
            if (name.empty())
                name = "Group_" + std::to_string(i);

            nlohmann::json g;
            g["index"] = i;
            g["name"] = name;
            g["memberCount"] = memberCount;
            groups.push_back(std::move(g));
            ++activeCount;
        }

        nlohmann::json result;
        result["count"] = activeCount;
        result["groups"] = std::move(groups);
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

// ─── POST /group ────────────────────────────────────────────────────

void HandleGroup(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    if (!body.contains("ids") || !body["ids"].is_array() || body["ids"].empty())
    {
        CRookServer::SendError(res, "Missing or empty 'ids' array");
        return;
    }

    std::vector<ON_UUID> ids;
    try { ids = ParseUuids(body, "ids"); }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendError(res, ex.what());
        return;
    }

    std::string groupName;
    if (body.contains("name") && body["name"].is_string())
        groupName = body["name"].get<std::string>();

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, ids = std::move(ids), groupName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Create Group");

        // Create group
        ON_Group grp;
        if (!groupName.empty())
            grp.SetName(Utf8ToWide(groupName));

        int groupIdx = pDoc->m_group_table.AddGroup(grp);
        if (groupIdx < 0)
            throw std::runtime_error("Failed to create group");

        // Add objects to group by modifying their attributes
        int addedCount = 0;
        for (const auto& uuid : ids)
        {
            const CRhinoObject* obj = pDoc->LookupObject(uuid);
            if (!obj) continue;

            ON_3dmObjectAttributes attrs = obj->Attributes();
            attrs.AddToGroup(groupIdx);
            pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
            ++addedCount;
        }

        // Get the final group name
        const CRhinoGroup* pCreated = pDoc->m_group_table[groupIdx];
        std::string finalName = pCreated ? WideToUtf8(pCreated->Name()) : "";
        if (finalName.empty())
            finalName = "Group_" + std::to_string(groupIdx);

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["groupIndex"] = groupIdx;
        wr.data["name"] = finalName;
        wr.data["memberCount"] = addedCount;
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

// ─── POST /ungroup ──────────────────────────────────────────────────

void HandleUngroup(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Accept either "name" or "index"
    bool hasName = body.contains("name") && body["name"].is_string();
    bool hasIndex = body.contains("index") && body["index"].is_number_integer();
    if (!hasName && !hasIndex)
    {
        CRookServer::SendError(res, "Must provide 'name' (string) or 'index' (integer)");
        return;
    }

    std::string name = hasName ? body["name"].get<std::string>() : "";
    int requestedIndex = hasIndex ? body["index"].get<int>() : -1;

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, requestedIndex, hasName]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Ungroup");

        int groupIdx = -1;
        if (hasName)
            groupIdx = FindGroupIndex(pDoc, name);
        else
            groupIdx = requestedIndex;

        if (groupIdx < 0 || groupIdx >= pDoc->m_group_table.GroupCount())
            throw std::invalid_argument("Group not found");

        const CRhinoGroup* pGrp = pDoc->m_group_table[groupIdx];
        if (!pGrp || pGrp->IsDeleted())
            throw std::invalid_argument("Group not found or already deleted");

        std::string deletedName = WideToUtf8(pGrp->Name());
        if (deletedName.empty())
            deletedName = "Group_" + std::to_string(groupIdx);

        // Remove all objects from the group before deleting it.
        // DeleteGroup marks the group as deleted but does NOT clear
        // IsInGroup(idx) from object attributes — stale indices would
        // incorrectly match if the slot is reused by a future group.
        CRhinoObjectIterator ungroupIt(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = ungroupIt.First(); obj; obj = ungroupIt.Next())
        {
            if (!obj->Attributes().IsInGroup(groupIdx)) continue;
            ON_3dmObjectAttributes attrs = obj->Attributes();
            attrs.RemoveFromGroup(groupIdx);
            pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs);
        }

        if (!pDoc->m_group_table.DeleteGroup(groupIdx))
            throw std::runtime_error("Failed to delete group");

        pDoc->Redraw();

        WriteResult wr;
        wr.success = true;
        wr.data["deletedIndex"] = groupIdx;
        wr.data["name"] = deletedName;
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

// ─── GET /group/members ─────────────────────────────────────────────

void HandleGroupMembers(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Accept either "name" or "index"
    bool hasName = body.contains("name") && body["name"].is_string();
    bool hasIndex = body.contains("index") && body["index"].is_number_integer();

    // Also check query params for GET requests
    if (!hasName && req.has_param("name"))
        hasName = true;
    if (!hasIndex && req.has_param("index"))
        hasIndex = true;

    std::string name = hasName
        ? (body.contains("name") ? body["name"].get<std::string>() : req.get_param_value("name"))
        : "";

    int requestedIndex = -1;
    if (hasIndex)
    {
        if (body.contains("index"))
        {
            requestedIndex = body["index"].get<int>();
        }
        else
        {
            try { requestedIndex = std::stoi(req.get_param_value("index")); }
            catch (...)
            {
                CRookServer::SendError(res, "Invalid 'index' parameter (must be an integer)");
                return;
            }
        }
    }

    if (!hasName && !hasIndex)
    {
        CRookServer::SendError(res, "Must provide 'name' or 'index' parameter");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, name, requestedIndex, hasName]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        int groupIdx = -1;
        if (hasName)
            groupIdx = FindGroupIndex(pDoc, name);
        else
            groupIdx = requestedIndex;

        if (groupIdx < 0 || groupIdx >= pDoc->m_group_table.GroupCount())
            throw std::invalid_argument("Group not found");

        const CRhinoGroup* pGrp = pDoc->m_group_table[groupIdx];
        if (!pGrp || pGrp->IsDeleted())
            throw std::invalid_argument("Group not found or deleted");

        std::string groupName = WideToUtf8(pGrp->Name());
        if (groupName.empty())
            groupName = "Group_" + std::to_string(groupIdx);

        nlohmann::json members = nlohmann::json::array();
        CRhinoObjectIterator it(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);

        for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
        {
            if (!obj->Attributes().IsInGroup(groupIdx))
                continue;

            nlohmann::json m;
            m["id"] = UuidToString(obj->Attributes().m_uuid);
            m["type"] = ObjectTypeToString(obj->ObjectType());

            // Layer name
            int layerIdx = obj->Attributes().m_layer_index;
            if (layerIdx >= 0 && layerIdx < pDoc->m_layer_table.LayerCount())
            {
                ON_wString fullPath;
                pDoc->m_layer_table.GetLayerPathName(layerIdx, fullPath);
                m["layer"] = WideToUtf8(fullPath);
            }

            std::string objName = WideToUtf8(obj->Attributes().m_name);
            m["name"] = objName;

            members.push_back(std::move(m));
        }

        nlohmann::json result;
        result["groupIndex"] = groupIdx;
        result["name"] = groupName;
        result["memberCount"] = members.size();
        result["members"] = std::move(members);
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
