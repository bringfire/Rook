// DirectorHandler.cpp
//
// RookVisionDirector slice 1 native contracts.

#include "stdafx.h"
#include "Handlers/DirectorHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <stdexcept>

namespace Rook {
namespace Handlers {
namespace {

nlohmann::json MakeErrorData(const std::string& code, const std::string& message)
{
    nlohmann::json data;
    data["code"] = code;
    data["message"] = message;
    return data;
}

nlohmann::json PointToJson(const ON_3dPoint& point)
{
    return nlohmann::json::array({
        RoundTo(point.x, 6),
        RoundTo(point.y, 6),
        RoundTo(point.z, 6)
    });
}

nlohmann::json VectorToJson(const ON_3dVector& vector)
{
    return nlohmann::json::array({
        RoundTo(vector.x, 6),
        RoundTo(vector.y, 6),
        RoundTo(vector.z, 6)
    });
}

nlohmann::json BoundingBoxToJson(const ON_BoundingBox& bbox)
{
    nlohmann::json data;
    data["min"] = PointToJson(bbox.m_min);
    data["max"] = PointToJson(bbox.m_max);
    data["center"] = PointToJson(bbox.Center());
    return data;
}

std::vector<std::string> ParseObjectIds(const nlohmann::json& body)
{
    if (!body.contains("object_ids") || !body["object_ids"].is_array())
        throw std::invalid_argument("object_ids must be a non-empty array of UUID strings");

    std::vector<std::string> objectIds;
    objectIds.reserve(body["object_ids"].size());
    for (const auto& item : body["object_ids"])
    {
        if (!item.is_string())
            throw std::invalid_argument("object_ids must contain only UUID strings");
        objectIds.push_back(item.get<std::string>());
    }

    if (objectIds.empty())
        throw std::invalid_argument("object_ids must be a non-empty array of UUID strings");

    return objectIds;
}

const ON_3dmView* FindNamedView(CRhinoDoc* pDoc, const std::string& name)
{
    ON_wString wName = Utf8ToWide(name);
    const int count = pDoc->Properties().NamedViewCount();
    for (int i = 0; i < count; ++i)
    {
        const ON_3dmView* pView = pDoc->Properties().NamedView(i);
        if (pView && pView->m_name.CompareNoCase(wName) == 0)
            return pView;
    }
    return nullptr;
}

nlohmann::json SerializeViewportCamera(const ON_Viewport& vp)
{
    double aspect = 0.0;
    const bool hasAspect = vp.GetFrustumAspect(aspect);

    double lensLength = 0.0;
    const bool hasLensLength = vp.GetCamera35mmLensLength(&lensLength);

    nlohmann::json camera;
    if (vp.IsPerspectiveProjection())
        camera["projection"] = "perspective";
    else if (vp.IsParallelProjection())
        camera["projection"] = "parallel";
    else
        camera["projection"] = "unknown";

    camera["location"] = PointToJson(vp.CameraLocation());
    camera["target"] = PointToJson(vp.TargetPoint());
    camera["up"] = VectorToJson(vp.CameraUp());
    camera["aspect"] = hasAspect ? nlohmann::json(RoundTo(aspect, 6)) : nlohmann::json(nullptr);
    camera["lens_length"] = hasLensLength ? nlohmann::json(RoundTo(lensLength, 6)) : nlohmann::json(nullptr);

    nlohmann::json frustum;
    frustum["left"] = RoundTo(vp.FrustumLeft(), 6);
    frustum["right"] = RoundTo(vp.FrustumRight(), 6);
    frustum["bottom"] = RoundTo(vp.FrustumBottom(), 6);
    frustum["top"] = RoundTo(vp.FrustumTop(), 6);
    frustum["near"] = RoundTo(vp.FrustumNear(), 6);
    frustum["far"] = RoundTo(vp.FrustumFar(), 6);
    camera["frustum"] = std::move(frustum);

    ON_2iSize screenSize = vp.ScreenPortSize();
    camera["viewport_size"] = nlohmann::json::array({ screenSize.cx, screenSize.cy });

    return camera;
}

nlohmann::json SerializeObjectState(CRhinoDoc* pDoc, const CRhinoObject* obj)
{
    const CRhinoObjectAttributes& attrs = obj->Attributes();
    ON_BoundingBox bbox = obj->BoundingBox();
    if (!bbox.IsValid())
        throw std::runtime_error("Object has invalid bounding box: " + UuidToString(attrs.m_uuid));

    nlohmann::json state;
    state["object_id"] = UuidToString(attrs.m_uuid);
    state["id"] = state["object_id"];
    state["object_display_name"] = WideToUtf8(attrs.m_name);
    state["object_type"] = ObjectTypeToString(obj->ObjectType());
    state["bbox"] = BoundingBoxToJson(bbox);
    state["bbox_min"] = PointToJson(bbox.m_min);
    state["bbox_max"] = PointToJson(bbox.m_max);
    state["state_hash"] = nullptr;
    state["validation_strength"] = "bbox_only";

    const int layerIndex = attrs.m_layer_index;
    if (layerIndex >= 0 && layerIndex < pDoc->m_layer_table.LayerCount())
    {
        ON_wString layerPath;
        pDoc->m_layer_table.GetLayerPathName(layerIndex, layerPath);
        state["layer"] = WideToUtf8(layerPath);
    }

    return state;
}

} // namespace

void HandleDirectorObjectStates(const httplib::Request& req, httplib::Response& res)
{
    try
    {
        auto [docSn, body] = ParseBodyAndDocSn(req);
        std::vector<std::string> objectIds = ParseObjectIds(body);

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [docSn, objectIds]() -> nlohmann::json
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);

            nlohmann::json states = nlohmann::json::array();
            for (const std::string& idStr : objectIds)
            {
                ON_UUID uuid = ON_UuidFromString(idStr.c_str());
                if (ON_UuidIsNil(uuid))
                    throw std::invalid_argument("Invalid object id: " + idStr);

                const CRhinoObject* obj = pDoc->LookupObject(uuid);
                if (!obj)
                    throw std::invalid_argument("Object not found: " + idStr);

                states.push_back(SerializeObjectState(pDoc, obj));
            }

            const ON_3dmUnitsAndTolerances& ut = pDoc->Properties().ModelUnitsAndTolerances();
            nlohmann::json result;
            result["schema_version"] = 1;
            result["objects"] = std::move(states);
            result["count"] = static_cast<int>(objectIds.size());
            result["units"] = WideToUtf8(ut.m_unit_system.ToString());
            result["validation_strength"] = "bbox_only";
            return result;
        });

        CRookServer::SendSuccess(res, future.get());
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("director_read_failed", ex.what()));
    }
}

void HandleDirectorViewState(const httplib::Request& req, httplib::Response& res)
{
    try
    {
        auto [docSn, body] = ParseBodyAndDocSn(req);

        if (!body.contains("source") || !body["source"].is_object())
            throw std::invalid_argument("source must be an object");

        const auto& source = body["source"];
        if (!source.contains("kind") || !source["kind"].is_string())
            throw std::invalid_argument("source.kind must be active_view or named_view");

        std::string kind = source["kind"].get<std::string>();
        std::string name;
        if (kind == "named_view")
        {
            if (!source.contains("name") || !source["name"].is_string() || source["name"].get<std::string>().empty())
                throw std::invalid_argument("source.name is required for named_view");
            name = source["name"].get<std::string>();
        }
        else if (kind != "active_view")
        {
            throw std::invalid_argument("source.kind must be active_view or named_view");
        }

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [docSn, kind, name]() -> nlohmann::json
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);

            ON_Viewport vp;
            std::string resolvedName;
            if (kind == "active_view")
            {
                CRhinoView* pView = pDoc->ActiveView();
                if (!pView)
                    throw std::runtime_error("No active view");
                vp = pView->ActiveViewport().VP();
                resolvedName = WideToUtf8(pView->ActiveViewport().Name());
            }
            else
            {
                const ON_3dmView* pNamedView = FindNamedView(pDoc, name);
                if (!pNamedView)
                    throw std::invalid_argument("Named view not found: " + name);
                vp = pNamedView->m_vp;
                resolvedName = WideToUtf8(pNamedView->m_name);
            }

            nlohmann::json provenance;
            provenance["source"] = kind;
            provenance["name"] = resolvedName;
            provenance["document_runtime_serial_number"] = pDoc->RuntimeSerialNumber();

            nlohmann::json result;
            result["schema_version"] = 1;
            result["camera"] = SerializeViewportCamera(vp);
            result["provenance"] = std::move(provenance);
            return result;
        });

        CRookServer::SendSuccess(res, future.get());
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("director_read_failed", ex.what()));
    }
}

void HandleDirectorFrameCapture(const httplib::Request& req, httplib::Response& res)
{
    UNREFERENCED_PARAMETER(req);
    CRookServer::SendErrorData(
        res,
        MakeErrorData(
            "not_implemented",
            "/director/frame-capture is reserved for the slice 1 guarded transaction task"));
}

} // namespace Handlers
} // namespace Rook
