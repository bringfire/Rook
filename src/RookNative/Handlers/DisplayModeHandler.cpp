// DisplayModeHandler.cpp
//
// GET  /display-modes  — List all display modes (built-in + custom)
// POST /display-mode   — Set active viewport display mode (Tier 1 SDK)
//
// Uses CRhinoDisplayAttrsMgr for enumeration and CRhinoViewport::SetDisplayMode()
// for persistent viewport changes.  No RunScript — pure SDK calls.

#include "stdafx.h"
#include "Handlers/DisplayModeHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

static std::string UuidToString(const ON_UUID& id)
{
    ON_wString ws;
    ON_UuidToString(id, ws);
    return WideToUtf8(ws);
}

// ─── GET /display-modes ─────────────────────────────────────────────

void HandleGetDisplayModes(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);

        // Get the active viewport's current display mode for comparison
        CRhinoView* pView = pDoc->ActiveView();
        ON_UUID activeDisplayModeId = ON_nil_uuid;
        if (pView)
        {
            const CDisplayPipelineAttributes* pActive = pView->DisplayAttributes();
            if (pActive)
                activeDisplayModeId = pActive->Id();
        }

        // Enumerate all display modes via the display attributes manager
        DisplayAttrsMgrList attrsList;
        int count = CRhinoDisplayAttrsMgr::GetDisplayAttrsList(attrsList);

        nlohmann::json modes = nlohmann::json::array();

        for (int i = 0; i < count; ++i)
        {
            const CDisplayPipelineAttributes* pAttrs = attrsList[i].m_pAttrs;
            if (!pAttrs)
                continue;

            nlohmann::json mode;
            mode["name"] = WideToUtf8(pAttrs->EnglishName());
            mode["id"] = UuidToString(pAttrs->Id());
            mode["isActive"] = (ON_UuidCompare(pAttrs->Id(), activeDisplayModeId) == 0);

            modes.push_back(std::move(mode));
        }

        nlohmann::json result;
        result["count"] = static_cast<int>(modes.size());
        result["modes"] = std::move(modes);
        return result;
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

// ─── POST /display-mode ─────────────────────────────────────────────

void HandleSetDisplayMode(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    // Accept either "name" (string) or "id" (UUID string).  Name is more ergonomic.
    std::string modeName = body.value("name", "");
    std::string modeId   = body.value("id", "");

    if (modeName.empty() && modeId.empty())
    {
        CRookServer::SendError(res, "Provide 'name' (display mode name) or 'id' (UUID)");
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, modeName, modeId]() -> nlohmann::json
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        CRhinoView* pView = pDoc->ActiveView();
        if (!pView)
            throw std::runtime_error("No active view");

        ON_UUID targetId = ON_nil_uuid;

        if (!modeId.empty())
        {
            // Parse UUID directly
            targetId = ON_UuidFromString(modeId.c_str());
            if (ON_UuidIsNil(targetId))
                throw std::invalid_argument("Invalid UUID format: " + modeId);
        }
        else
        {
            // Find by name using SDK's built-in name lookup (case-insensitive)
            ON_wString wName = Utf8ToWide(modeName);
            DisplayAttrsMgrListDesc* pDesc =
                CRhinoDisplayAttrsMgr::FindDisplayAttrsDesc(static_cast<const wchar_t*>(wName));

            if (!pDesc || !pDesc->m_pAttrs)
                throw std::invalid_argument("Display mode '" + modeName + "' not found");

            targetId = pDesc->m_pAttrs->Id();
        }

        // Verify the UUID corresponds to a real display mode
        const CDisplayPipelineAttributes* pTarget =
            CRhinoDisplayAttrsMgr::FindDisplayAttrs(targetId);
        if (!pTarget)
            throw std::invalid_argument("Display mode UUID not found");

        // Apply to active viewport — this is a persistent change (not capture-only)
        pView->ActiveViewport().SetDisplayMode(targetId);
        pView->Redraw();

        nlohmann::json result;
        result["name"] = WideToUtf8(pTarget->EnglishName());
        result["id"] = UuidToString(targetId);
        result["applied"] = true;
        return result;
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
