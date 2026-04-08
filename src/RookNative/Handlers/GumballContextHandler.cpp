// GumballContextHandler.cpp
//
// Phase 6A endpoints:
//   GET  /gumball/context    — Full context for AI consumption
//   POST /gumball/align      — Set alignment mode (world/cplane/object)
//   POST /gumball/appearance — Configure handle visibility
//
// BuildContext() runs on the main thread via Dispatch, the JSON
// serialization runs on the HTTP worker thread.

#include "stdafx.h"
#include "Handlers/GumballContextHandler.h"
#include "Interactive/GumballManager.h"
#include "Interactive/GumballContext.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helper: serialize GumballContext to JSON ─────────────────────

static nlohmann::json ContextToJson(const GumballContext& ctx)
{
    nlohmann::json j;

    // State
    j["enabled"]    = ctx.enabled;
    j["dragActive"] = ctx.dragActive;
    j["dragCount"]  = ctx.dragCount;

    // Frame
    nlohmann::json frame;
    frame["origin"] = ctx.frame.origin;
    frame["xAxis"]  = ctx.frame.xAxis;
    frame["yAxis"]  = ctx.frame.yAxis;
    frame["zAxis"]  = ctx.frame.zAxis;
    frame["alignmentMode"] = ctx.frame.alignmentMode;
    j["frame"] = frame;

    // Objects
    j["objectCount"] = ctx.objectCount;
    auto objArr = nlohmann::json::array();
    for (const auto& obj : ctx.objects)
    {
        nlohmann::json o;
        o["id"]    = obj.id;
        o["type"]  = obj.type;
        o["name"]  = obj.name;
        o["layer"] = obj.layer;
        o["bboxMin"] = obj.bboxMin;
        o["bboxMax"] = obj.bboxMax;

        // Geometry-specific fields (only include non-default values)
        if (obj.type == "Brep" || obj.type == "Extrusion")
        {
            o["isSolid"]    = obj.isSolid;
            o["faceCount"]  = obj.faceCount;
            o["edgeCount"]  = obj.edgeCount;
            o["vertexCount"] = obj.vertexCount;
            if (obj.volume > 0) o["volume"] = obj.volume;
            if (obj.area > 0)   o["area"]   = obj.area;
        }
        else if (obj.type == "Mesh")
        {
            o["vertexCount"] = obj.vertexCount;
            o["faceCount"]   = obj.faceCount;
            o["isClosed"]    = obj.isClosed;
        }
        else if (obj.type == "SubD")
        {
            o["vertexCount"] = obj.vertexCount;
            o["edgeCount"]   = obj.edgeCount;
            o["faceCount"]   = obj.faceCount;
        }
        else if (obj.type == "Curve")
        {
            o["length"]  = obj.length;
            o["isClosed"] = obj.isClosed;
            o["degree"]   = obj.degree;
        }

        if (!obj.shapeClass.empty())
            o["shapeClass"] = obj.shapeClass;

        objArr.push_back(o);
    }
    j["objects"] = objArr;

    // Operations
    nlohmann::json ops;
    ops["canTranslate"] = ctx.operations.canTranslate;
    ops["canRotate"]    = ctx.operations.canRotate;
    ops["canScale"]     = ctx.operations.canScale;
    ops["canExtrude"]   = ctx.operations.canExtrude;
    ops["enabledHandles"] = ctx.operations.enabledHandles;
    j["operations"] = ops;

    // Neighbors
    auto neighborArr = nlohmann::json::array();
    for (const auto& n : ctx.neighbors)
    {
        nlohmann::json nb;
        nb["id"]           = n.id;
        nb["name"]         = n.name;
        nb["type"]         = n.type;
        nb["relationship"] = n.relationship;
        nb["direction"]    = n.direction;
        nb["distance"]     = n.distance;
        neighborArr.push_back(nb);
    }
    j["neighbors"] = neighborArr;

    // Document context
    j["viewName"]  = ctx.viewName;
    j["units"]     = ctx.units;
    j["tolerance"] = ctx.tolerance;

    return j;
}

// ─── GET /gumball/context ─────────────────────────────────────────

void HandleGumballContext(const httplib::Request& /*req*/, httplib::Response& res)
{
    try
    {
        // BuildContext() accesses m_conduit, Rhino objects, scene graph —
        // must run on main thread. Returns plain-data struct.
        auto future = CMainThreadDispatcher::Instance().Dispatch([]() {
            return CGumballManager::Instance().BuildContext();
        });

        GumballContext ctx = future.get();
        CRookServer::SendSuccess(res, ContextToJson(ctx));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error building gumball context: ") + ex.what());
    }
}

// ─── POST /gumball/align ──────────────────────────────────────────

void HandleGumballAlign(const httplib::Request& req, httplib::Response& res)
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

    std::string modeStr = body.value("mode", "world");
    AlignmentMode mode = AlignmentModeFromString(modeStr);

    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([mode]() {
            CGumballManager::Instance().SetAlignment(mode);
        });
        future.get();

        nlohmann::json result;
        result["alignmentMode"] = AlignmentModeToString(mode);
        result["message"] = std::string("Gumball alignment set to ") + AlignmentModeToString(mode);
        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error setting alignment: ") + ex.what());
    }
}

// ─── POST /gumball/appearance ─────────────────────────────────────

void HandleGumballAppearance(const httplib::Request& req, httplib::Response& res)
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

    bool autoMode = body.value("auto", true);

    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([autoMode]() {
            CGumballManager::Instance().SetAutoAppearance(autoMode);
        });
        future.get();

        nlohmann::json result;
        result["auto"] = autoMode;
        result["message"] = autoMode
            ? "Auto appearance enabled (handles adjust to geometry type)"
            : "Auto appearance disabled (all handles visible)";
        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error setting appearance: ") + ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
