// DirectorHandler.cpp
//
// RookVisionDirector slice 1 native contracts.

#include "stdafx.h"
#include "Handlers/DirectorHandler.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <algorithm>
#include <cmath>
#include <cwctype>
#include <filesystem>
#include <stdexcept>
#include <vector>

namespace fs = std::filesystem;

namespace Rook {
namespace Handlers {
namespace {

constexpr int kMaxDirectorCaptureWidth = 8192;
constexpr int kMaxDirectorCaptureHeight = 8192;

nlohmann::json MakeErrorData(const std::string& code, const std::string& message)
{
    nlohmann::json data;
    data["code"] = code;
    data["message"] = message;
    return data;
}

class DirectorFrameValidationError : public std::runtime_error
{
public:
    DirectorFrameValidationError(std::string errorCode, const std::string& message)
        : std::runtime_error(message), code(std::move(errorCode))
    {
    }

    DirectorFrameValidationError(std::string errorCode, const std::string& message, std::vector<std::string> affectedIds)
        : std::runtime_error(message), code(std::move(errorCode)), affectedObjectIds(std::move(affectedIds))
    {
    }

    std::string code;
    std::vector<std::string> affectedObjectIds;
};

struct FrameObjectTransform
{
    std::string objectId;
    ON_UUID uuid = ON_nil_uuid;
    ON_Xform delta = ON_Xform::IdentityTransformation;
    ON_BoundingBox sourceBbox;
    std::string validationStrength;
};

struct FrameInstruction
{
    std::string frameId;
    int frameIndex = 0;
    fs::path runRoot;
    fs::path outputPath;
    std::string displayMode;
    std::vector<FrameObjectTransform> objectTransforms;
};

nlohmann::json MakeFrameErrorData(
    const nlohmann::json& body,
    const std::string& code,
    const std::string& message,
    const std::vector<std::string>& affectedObjectIds = {})
{
    nlohmann::json data;
    data["frame_id"] = body.contains("frame_id") && body["frame_id"].is_string()
        ? body["frame_id"].get<std::string>()
        : "";
    data["frame_index"] = body.contains("frame_index") && body["frame_index"].is_number_integer()
        ? body["frame_index"].get<int>()
        : 0;
    data["success"] = false;
    data["dirty_partial_state"] = false;
    data["affected_object_ids"] = affectedObjectIds;
    data["error"] = MakeErrorData(code, message);
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

ON_3dPoint ParsePointArray3(const nlohmann::json& value, const std::string& key)
{
    if (!value.is_array() || value.size() != 3)
        throw DirectorFrameValidationError("invalid_input", key + " must be a 3-number array");

    for (size_t i = 0; i < 3; ++i)
    {
        if (!value[i].is_number())
            throw DirectorFrameValidationError("invalid_input", key + " must be a 3-number array");
    }

    return ON_3dPoint(value[0].get<double>(), value[1].get<double>(), value[2].get<double>());
}

bool IsFinitePoint(const ON_3dPoint& point)
{
    return std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z);
}

bool IsFiniteVector(const ON_3dVector& vector)
{
    return std::isfinite(vector.x) && std::isfinite(vector.y) && std::isfinite(vector.z);
}

bool HasPositiveOptionalNumber(const nlohmann::json& object, const std::string& key)
{
    if (!object.contains(key) || object[key].is_null())
        return false;

    if (!object[key].is_number())
        throw DirectorFrameValidationError("invalid_input", key + " must be a positive number when provided");

    double value = object[key].get<double>();
    if (!std::isfinite(value) || value <= 0.0)
        throw DirectorFrameValidationError("invalid_input", key + " must be a positive finite number");

    return true;
}

bool HasValidFovDegrees(const nlohmann::json& object)
{
    if (!object.contains("fov_degrees") || object["fov_degrees"].is_null())
        return false;

    if (!object["fov_degrees"].is_number())
        throw DirectorFrameValidationError("invalid_input", "fov_degrees must be a positive number when provided");

    double value = object["fov_degrees"].get<double>();
    if (!std::isfinite(value) || value <= 0.0 || value >= 180.0)
        throw DirectorFrameValidationError("invalid_input", "fov_degrees must be finite and between 0 and 180");

    return true;
}

fs::path PathFromUtf8(const std::string& value)
{
    ON_wString wide = Utf8ToWide(value);
    return fs::path(static_cast<const wchar_t*>(wide));
}

std::wstring GetEnvironmentVariableString(const wchar_t* name)
{
    DWORD required = ::GetEnvironmentVariableW(name, nullptr, 0);
    if (required == 0)
        return {};

    std::wstring value(required, L'\0');
    DWORD written = ::GetEnvironmentVariableW(name, value.data(), required);
    if (written == 0)
        return {};

    value.resize(written);
    return value;
}

fs::path NormalizePolicyPath(const fs::path& path)
{
    std::error_code ec;
    fs::path absolute = fs::absolute(path, ec);
    if (ec)
        absolute = path;

    fs::path weak = fs::weakly_canonical(absolute, ec);
    if (!ec)
        return weak.lexically_normal();

    return absolute.lexically_normal();
}

fs::path GetAllowedDirectorRoot()
{
    std::wstring configured = GetEnvironmentVariableString(L"ROOK_DIRECTOR_OUTPUT_ROOT");
    if (!configured.empty())
        return NormalizePolicyPath(fs::path(configured));

    std::wstring localAppData = GetEnvironmentVariableString(L"LOCALAPPDATA");
    if (localAppData.empty())
        throw DirectorFrameValidationError(
            "output_policy_violation",
            "LOCALAPPDATA is required when ROOK_DIRECTOR_OUTPUT_ROOT is not set");

    return NormalizePolicyPath(fs::path(localAppData) / L"Rook" / L"rookvision_director");
}

std::wstring LowerPathPart(const fs::path& part)
{
    std::wstring text = part.native();
    std::transform(text.begin(), text.end(), text.begin(), [](wchar_t ch) {
        return static_cast<wchar_t>(std::towlower(ch));
    });
    return text;
}

bool IsSameOrDescendantPath(const fs::path& parent, const fs::path& candidate)
{
    std::vector<std::wstring> parentParts;
    std::vector<std::wstring> candidateParts;

    for (const fs::path& part : parent)
        parentParts.push_back(LowerPathPart(part));
    for (const fs::path& part : candidate)
        candidateParts.push_back(LowerPathPart(part));

    if (parentParts.size() > candidateParts.size())
        return false;

    for (size_t i = 0; i < parentParts.size(); ++i)
    {
        if (parentParts[i] != candidateParts[i])
            return false;
    }

    return true;
}

bool IsSamePath(const fs::path& a, const fs::path& b)
{
    return IsSameOrDescendantPath(a, b) && IsSameOrDescendantPath(b, a);
}

void ValidateOutputPolicy(const fs::path& runRoot, const fs::path& outputPath)
{
    fs::path allowedRoot = GetAllowedDirectorRoot();

    if (!IsSameOrDescendantPath(allowedRoot, runRoot))
        throw DirectorFrameValidationError(
            "output_policy_violation",
            "run_root must be inside the native director output root");

    if (!IsSameOrDescendantPath(runRoot, outputPath))
        throw DirectorFrameValidationError(
            "output_policy_violation",
            "output_path must be a descendant of run_root");

    if (IsSamePath(runRoot, outputPath))
        throw DirectorFrameValidationError(
            "output_policy_violation",
            "output_path must be a file path below run_root");
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

    double halfDiagonalAngle = 0.0;
    double halfVerticalAngle = 0.0;
    double halfHorizontalAngle = 0.0;
    const bool hasCameraAngle = vp.GetCameraAngle(
        &halfDiagonalAngle,
        &halfVerticalAngle,
        &halfHorizontalAngle);

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
    camera["fov_degrees"] = (vp.IsPerspectiveProjection() && hasCameraAngle)
        ? nlohmann::json(RoundTo(2.0 * halfVerticalAngle * (180.0 / ON_PI), 6))
        : nlohmann::json(nullptr);
    camera["parallel_scale"] = vp.IsParallelProjection()
        ? nlohmann::json(RoundTo(vp.FrustumHeight(), 6))
        : nlohmann::json(nullptr);
    camera["near_clip"] = RoundTo(vp.FrustumNear(), 6);
    camera["far_clip"] = RoundTo(vp.FrustumFar(), 6);

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

void ValidateCamera(const nlohmann::json& body)
{
    if (!body.contains("camera") || !body["camera"].is_object())
        throw DirectorFrameValidationError("invalid_input", "camera must be an object");

    const auto& camera = body["camera"];
    if (!camera.contains("projection") || !camera["projection"].is_string())
        throw DirectorFrameValidationError("invalid_input", "camera.projection is required");

    std::string projection = camera["projection"].get<std::string>();
    if (projection != "perspective")
        throw DirectorFrameValidationError("unsupported_projection", "Slice 1 frame-capture supports perspective cameras only");

    ON_3dPoint location = ParsePointArray3(camera.value("location", nlohmann::json()), "camera.location");
    ON_3dPoint target = ParsePointArray3(camera.value("target", nlohmann::json()), "camera.target");
    ON_3dPoint upPoint = ParsePointArray3(camera.value("up", nlohmann::json()), "camera.up");
    ON_3dVector up(upPoint.x, upPoint.y, upPoint.z);
    ON_3dVector direction = target - location;

    if (!IsFinitePoint(location) || !IsFinitePoint(target) || !IsFiniteVector(up))
        throw DirectorFrameValidationError("invalid_input", "camera vectors must be finite");
    if (!direction.Unitize())
        throw DirectorFrameValidationError("invalid_input", "camera location and target must differ");
    if (!up.Unitize())
        throw DirectorFrameValidationError("invalid_input", "camera.up must be nonzero");

    const bool hasLensLength = HasPositiveOptionalNumber(camera, "lens_length");
    const bool hasFovDegrees = HasValidFovDegrees(camera);
    if (!hasLensLength && !hasFovDegrees)
        throw DirectorFrameValidationError("invalid_input", "perspective camera requires positive lens_length or fov_degrees");
}

ON_Xform ParseTransformMatrix(const nlohmann::json& transform, const std::string& objectId)
{
    if (!transform.is_array() || transform.size() != 4)
        throw DirectorFrameValidationError("invalid_input", "transform must be a 4x4 numeric matrix", { objectId });

    ON_Xform xform = ON_Xform::IdentityTransformation;
    for (size_t rowIndex = 0; rowIndex < 4; ++rowIndex)
    {
        const auto& row = transform[rowIndex];
        if (!row.is_array() || row.size() != 4)
            throw DirectorFrameValidationError("invalid_input", "transform must be a 4x4 numeric matrix", { objectId });
        for (size_t colIndex = 0; colIndex < 4; ++colIndex)
        {
            const auto& value = row[colIndex];
            if (!value.is_number())
                throw DirectorFrameValidationError("invalid_input", "transform must be a 4x4 numeric matrix", { objectId });
            double numeric = value.get<double>();
            if (!std::isfinite(numeric))
                throw DirectorFrameValidationError("invalid_input", "transform matrix values must be finite", { objectId });
            xform.m_xform[rowIndex][colIndex] = numeric;
        }
    }

    return xform;
}

std::vector<FrameObjectTransform> ParseFrameObjectTransforms(const nlohmann::json& body)
{
    if (!body.contains("object_transforms") || !body["object_transforms"].is_array())
        throw DirectorFrameValidationError("invalid_input", "object_transforms must be a non-empty array");

    const auto& transforms = body["object_transforms"];
    if (transforms.empty())
        throw DirectorFrameValidationError("invalid_input", "object_transforms must be a non-empty array");

    std::vector<FrameObjectTransform> parsed;
    parsed.reserve(transforms.size());

    for (const auto& item : transforms)
    {
        if (!item.is_object())
            throw DirectorFrameValidationError("invalid_input", "object_transforms entries must be objects");
        if (!item.contains("object_id") || !item["object_id"].is_string())
            throw DirectorFrameValidationError("invalid_input", "object_transforms[].object_id is required");

        FrameObjectTransform frameObject;
        frameObject.objectId = item["object_id"].get<std::string>();
        frameObject.uuid = ON_UuidFromString(frameObject.objectId.c_str());
        if (ON_UuidIsNil(frameObject.uuid))
            throw DirectorFrameValidationError("invalid_input", "Invalid object id: " + frameObject.objectId, { frameObject.objectId });

        if (!item.contains("transform"))
            throw DirectorFrameValidationError("invalid_input", "object_transforms[].transform is required", { frameObject.objectId });
        frameObject.delta = ParseTransformMatrix(item["transform"], frameObject.objectId);

        if (!item.contains("source_state") || !item["source_state"].is_object())
            throw DirectorFrameValidationError("invalid_input", "object_transforms[].source_state is required", { frameObject.objectId });

        const auto& sourceState = item["source_state"];
        if (!sourceState.contains("validation_strength") || !sourceState["validation_strength"].is_string())
            throw DirectorFrameValidationError("invalid_input", "source_state.validation_strength is required", { frameObject.objectId });
        frameObject.validationStrength = sourceState["validation_strength"].get<std::string>();
        if (frameObject.validationStrength != "bbox_only")
            throw DirectorFrameValidationError("invalid_input", "source_state.validation_strength must be bbox_only for slice1", { frameObject.objectId });

        ON_3dPoint bboxMin = ParsePointArray3(sourceState.value("bbox_min", nlohmann::json()), "source_state.bbox_min");
        ON_3dPoint bboxMax = ParsePointArray3(sourceState.value("bbox_max", nlohmann::json()), "source_state.bbox_max");
        frameObject.sourceBbox = ON_BoundingBox(bboxMin, bboxMax);
        if (!frameObject.sourceBbox.IsValid())
            throw DirectorFrameValidationError("invalid_input", "source_state bbox is invalid", { frameObject.objectId });

        parsed.push_back(frameObject);
    }

    return parsed;
}

FrameInstruction ParseFrameInstruction(const nlohmann::json& body)
{
    if (!body.contains("schema_version") || !body["schema_version"].is_number_integer() ||
        body["schema_version"].get<int>() != 1)
    {
        throw DirectorFrameValidationError("invalid_input", "schema_version must be 1");
    }
    if (!body.contains("director_version") || !body["director_version"].is_string() ||
        body["director_version"].get<std::string>() != "slice1")
    {
        throw DirectorFrameValidationError("invalid_input", "director_version must be slice1");
    }
    if (!body.contains("frame_index") || !body["frame_index"].is_number_integer() || body["frame_index"].get<int>() < 1)
        throw DirectorFrameValidationError("invalid_input", "frame_index must be a positive integer");
    if (!body.contains("frame_id") || !body["frame_id"].is_string() || body["frame_id"].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", "frame_id is required");

    if (!body.contains("resolution") || !body["resolution"].is_object())
        throw DirectorFrameValidationError("invalid_input", "resolution must be an object");
    const auto& resolution = body["resolution"];
    if (!resolution.contains("width") || !resolution.contains("height") ||
        !resolution["width"].is_number_integer() || !resolution["height"].is_number_integer() ||
        resolution["width"].get<int>() <= 0 || resolution["height"].get<int>() <= 0)
    {
        throw DirectorFrameValidationError("invalid_input", "resolution width and height must be positive");
    }
    const int width = resolution["width"].get<int>();
    const int height = resolution["height"].get<int>();
    if (width > kMaxDirectorCaptureWidth || height > kMaxDirectorCaptureHeight)
    {
        throw DirectorFrameValidationError(
            "invalid_input",
            "resolution exceeds native director capture bounds");
    }

    if (!body.contains("run_root") || !body["run_root"].is_string() || body["run_root"].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", "run_root is required");
    if (!body.contains("output_path") || !body["output_path"].is_string() || body["output_path"].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", "output_path is required");

    ValidateCamera(body);

    FrameInstruction instruction;
    instruction.frameId = body["frame_id"].get<std::string>();
    instruction.frameIndex = body["frame_index"].get<int>();
    instruction.runRoot = NormalizePolicyPath(PathFromUtf8(body["run_root"].get<std::string>()));
    instruction.outputPath = NormalizePolicyPath(PathFromUtf8(body["output_path"].get<std::string>()));
    ValidateOutputPolicy(instruction.runRoot, instruction.outputPath);

    if (body.contains("display") && body["display"].is_object() &&
        body["display"].contains("mode") && body["display"]["mode"].is_string())
    {
        instruction.displayMode = body["display"]["mode"].get<std::string>();
    }

    instruction.objectTransforms = ParseFrameObjectTransforms(body);
    return instruction;
}

bool BboxAlmostEqual(const ON_BoundingBox& a, const ON_BoundingBox& b, double tolerance)
{
    return std::fabs(a.m_min.x - b.m_min.x) <= tolerance &&
        std::fabs(a.m_min.y - b.m_min.y) <= tolerance &&
        std::fabs(a.m_min.z - b.m_min.z) <= tolerance &&
        std::fabs(a.m_max.x - b.m_max.x) <= tolerance &&
        std::fabs(a.m_max.y - b.m_max.y) <= tolerance &&
        std::fabs(a.m_max.z - b.m_max.z) <= tolerance;
}

void ValidateDisplayMode(const std::string& displayMode)
{
    if (displayMode.empty() || IEquals(displayMode, "current"))
        return;

    ON_UUID modeId = ON_UuidFromString(displayMode.c_str());
    if (!ON_UuidIsNil(modeId))
    {
        if (!CRhinoDisplayAttrsMgr::FindDisplayAttrs(modeId))
            throw DirectorFrameValidationError("invalid_input", "Display mode UUID not found");
        return;
    }

    ON_wString wName = Utf8ToWide(displayMode);
    DisplayAttrsMgrListDesc* pDesc =
        CRhinoDisplayAttrsMgr::FindDisplayAttrsDesc(static_cast<const wchar_t*>(wName));
    if (!pDesc || !pDesc->m_pAttrs)
        throw DirectorFrameValidationError("invalid_input", "Display mode '" + displayMode + "' not found");
}

void ValidateFrameObjects(CRhinoDoc* pDoc, const std::vector<FrameObjectTransform>& objects)
{
    constexpr double kBboxTolerance = 1.0e-4;
    for (const FrameObjectTransform& frameObject : objects)
    {
        const CRhinoObject* obj = pDoc->LookupObject(frameObject.uuid);
        if (!obj || obj->IsDeleted())
            throw DirectorFrameValidationError("invalid_input", "Object not found: " + frameObject.objectId, { frameObject.objectId });

        ON_BoundingBox currentBbox = obj->BoundingBox();
        if (!currentBbox.IsValid())
            throw DirectorFrameValidationError("invalid_input", "Object has invalid bounding box: " + frameObject.objectId, { frameObject.objectId });

        if (!BboxAlmostEqual(currentBbox, frameObject.sourceBbox, kBboxTolerance))
            throw DirectorFrameValidationError("invalid_input", "Object source_state bbox does not match current document state", { frameObject.objectId });
    }
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
    unsigned int docSn = 0;
    nlohmann::json body = nlohmann::json::object();

    try
    {
        auto parsed = ParseBodyAndDocSn(req);
        docSn = parsed.first;
        body = std::move(parsed.second);

        FrameInstruction instruction = ParseFrameInstruction(body);

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [docSn, instruction]() -> nlohmann::json
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);
            ValidateDisplayMode(instruction.displayMode);
            ValidateFrameObjects(pDoc, instruction.objectTransforms);

            nlohmann::json data;
            data["frame_id"] = instruction.frameId;
            data["frame_index"] = instruction.frameIndex;
            data["success"] = false;
            data["dirty_partial_state"] = false;
            data["affected_object_ids"] = nlohmann::json::array();
            data["error"] = MakeErrorData(
                "not_implemented",
                "/director/frame-capture validation passed; guarded capture is implemented in the next task");
            return data;
        });

        CRookServer::SendErrorData(res, future.get());
    }
    catch (const DirectorFrameValidationError& ex)
    {
        CRookServer::SendErrorData(res, MakeFrameErrorData(body, ex.code, ex.what(), ex.affectedObjectIds));
    }
    catch (const nlohmann::json::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeFrameErrorData(body, "invalid_input", ex.what()));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeFrameErrorData(body, "invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeFrameErrorData(body, "native_frame_failed", ex.what()));
    }
}

} // namespace Handlers
} // namespace Rook
