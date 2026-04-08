// PromptHandler.cpp
//
// POST /prompt/point      — Pick a point (optional basePoint, constrainToObject)
// POST /prompt/object     — Select one object (optional type filter)
// POST /prompt/objects    — Select multiple objects (optional type filter)
// POST /prompt/subobject  — Select a face/edge/vertex
// POST /prompt/distance   — Pick two points for distance measurement

#include "stdafx.h"
#include "Handlers/PromptHandler.h"
#include "Interactive/PromptManager.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── POST /prompt/point ─────────────────────────────────────────────

void HandlePromptPoint(const httplib::Request& req, httplib::Response& res)
{
    std::string message = "Pick a point";
    double basePt[3] = {};
    bool hasBase = false;
    std::string constrainId;

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("message"))
                message = body.value("message", message);

            if (body.contains("basePoint") && body["basePoint"].is_array()
                && body["basePoint"].size() >= 3)
            {
                basePt[0] = body["basePoint"][0].get<double>();
                basePt[1] = body["basePoint"][1].get<double>();
                basePt[2] = body["basePoint"][2].get<double>();
                hasBase = true;
            }

            if (body.contains("constrainToObject"))
                constrainId = body.value("constrainToObject", "");
        }
    }

    auto result = PromptForPoint(message, hasBase ? basePt : nullptr, constrainId);

    if (!result.error.empty())
    {
        CRookServer::SendError(res, result.error);
        return;
    }

    nlohmann::json data;
    data["cancelled"] = result.cancelled;
    if (result.success)
        data["point"] = { result.point[0], result.point[1], result.point[2] };
    else
        data["point"] = nullptr;

    CRookServer::SendSuccess(res, data);
}

// ─── POST /prompt/object ────────────────────────────────────────────

void HandlePromptObject(const httplib::Request& req, httplib::Response& res)
{
    std::string message = "Select an object";
    std::string filter;

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("message"))
                message = body.value("message", message);
            if (body.contains("filter"))
                filter = body.value("filter", "");
        }
    }

    auto result = PromptForObject(message, filter);

    if (!result.error.empty())
    {
        CRookServer::SendError(res, result.error);
        return;
    }

    nlohmann::json data;
    data["cancelled"] = result.cancelled;
    if (result.success)
    {
        nlohmann::json obj;
        obj["id"]   = result.id;
        obj["type"] = result.type;
        if (!result.name.empty())
            obj["name"] = result.name;
        data["object"] = obj;

        if (result.hasPickPoint)
            data["pickPoint"] = { result.pickPoint[0], result.pickPoint[1], result.pickPoint[2] };
    }
    else
    {
        data["object"] = nullptr;
    }

    CRookServer::SendSuccess(res, data);
}

// ─── POST /prompt/objects ───────────────────────────────────────────

void HandlePromptObjects(const httplib::Request& req, httplib::Response& res)
{
    std::string message = "Select objects";
    std::string filter;
    int minCount = 1;

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("message"))
                message = body.value("message", message);
            if (body.contains("filter"))
                filter = body.value("filter", "");
            if (body.contains("minCount"))
                minCount = body.value("minCount", 1);
        }
    }

    auto result = PromptForObjects(message, filter, minCount);

    if (!result.error.empty())
    {
        CRookServer::SendError(res, result.error);
        return;
    }

    nlohmann::json data;
    data["cancelled"] = result.cancelled;

    auto arr = nlohmann::json::array();
    for (const auto& obj : result.objects)
    {
        nlohmann::json o;
        o["id"]   = obj.id;
        o["type"] = obj.type;
        if (!obj.name.empty())
            o["name"] = obj.name;
        arr.push_back(o);
    }
    data["objects"] = arr;
    data["count"]   = static_cast<int>(result.objects.size());

    CRookServer::SendSuccess(res, data);
}

// ─── POST /prompt/subobject ─────────────────────────────────────────

void HandlePromptSubObject(const httplib::Request& req, httplib::Response& res)
{
    std::string message = "Select a subobject";
    std::string subFilter = "any";

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("message"))
                message = body.value("message", message);
            if (body.contains("filter"))
                subFilter = body.value("filter", "any");
        }
    }

    auto result = PromptForSubObject(message, subFilter);

    if (!result.error.empty())
    {
        CRookServer::SendError(res, result.error);
        return;
    }

    nlohmann::json data;
    data["cancelled"] = result.cancelled;

    if (result.success)
    {
        data["parentId"]       = result.parentId;
        data["parentType"]     = result.parentType;
        data["componentType"]  = result.componentType;
        data["componentIndex"] = result.componentIndex;

        if (result.hasArea)
            data["area"] = result.area;
        if (result.hasCentroid)
            data["centroid"] = { result.centroid[0], result.centroid[1], result.centroid[2] };
        if (result.hasNormal)
            data["normal"] = { result.normal[0], result.normal[1], result.normal[2] };
        if (result.hasLength)
            data["length"] = result.length;
        if (result.hasStartEnd)
        {
            data["startPoint"] = { result.startPoint[0], result.startPoint[1], result.startPoint[2] };
            data["endPoint"]   = { result.endPoint[0], result.endPoint[1], result.endPoint[2] };
        }
        if (result.hasLocation)
            data["location"] = { result.location[0], result.location[1], result.location[2] };
        if (result.hasPickPoint)
            data["pickPoint"] = { result.pickPoint[0], result.pickPoint[1], result.pickPoint[2] };
    }

    CRookServer::SendSuccess(res, data);
}

// ─── POST /prompt/distance ──────────────────────────────────────────

void HandlePromptDistance(const httplib::Request& req, httplib::Response& res)
{
    std::string message1 = "Pick first point";
    std::string message2 = "Pick second point";

    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.is_object())
        {
            if (body.contains("message1"))
                message1 = body.value("message1", message1);
            if (body.contains("message2"))
                message2 = body.value("message2", message2);
            // Also accept "message" as alias for message1
            if (body.contains("message") && !body.contains("message1"))
                message1 = body.value("message", message1);
        }
    }

    auto result = PromptForDistance(message1, message2);

    if (!result.error.empty())
    {
        CRookServer::SendError(res, result.error);
        return;
    }

    nlohmann::json data;
    data["cancelled"] = result.cancelled;

    if (result.success)
    {
        data["point1"]   = { result.point1[0], result.point1[1], result.point1[2] };
        data["point2"]   = { result.point2[0], result.point2[1], result.point2[2] };
        data["distance"] = result.distance;
        data["vector"]   = { result.vector[0], result.vector[1], result.vector[2] };
    }

    CRookServer::SendSuccess(res, data);
}

} // namespace Handlers
} // namespace Rook
