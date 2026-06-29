// DirectorHandler.cpp
//
// RookVisionDirector slice 1 native contracts.

#include "stdafx.h"
#include "Handlers/DirectorHandler.h"
#include "Handlers/DirectorFrame.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cwctype>
#include <cstring>
#include <deque>
#include <filesystem>
#include <iomanip>
#include <limits>
#include <mutex>
#include <set>
#include <stdexcept>
#include <sstream>
#include <unordered_map>
#include <vector>
#include <wincodec.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <wrl/client.h>

#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfreadwrite.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "windowscodecs.lib")
#pragma comment(lib, "ole32.lib")

namespace fs = std::filesystem;
using Microsoft::WRL::ComPtr;

namespace Rook {
namespace Handlers {
namespace {

constexpr int kMaxDirectorCaptureWidth = 8192;
constexpr int kMaxDirectorCaptureHeight = 8192;
constexpr int kMaxDirectorCurveSampleFrameCount = 5000;
constexpr int kMaxDirectorVideoFrameCount = 5000;
constexpr int kMaxDirectorVideoWidth = kMaxDirectorCaptureWidth;
constexpr int kMaxDirectorVideoHeight = kMaxDirectorCaptureHeight;
constexpr double kMinDirectorVideoFps = 1.0;
constexpr double kMaxDirectorVideoFps = 240.0;

nlohmann::json MakeErrorData(const std::string& code, const std::string& message)
{
    nlohmann::json data;
    data["code"] = code;
    data["message"] = message;
    return data;
}

struct FrameInstruction
{
    std::string frameId;
    int frameIndex = 0;
    int width = 0;
    int height = 0;
    fs::path runRoot;
    fs::path outputPath;
    std::string displayMode;
    FrameCamera camera;
    std::vector<FrameObjectTransform> objectTransforms;
};

struct CurveSampleRequest
{
    std::string curveId;
    ON_UUID curveUuid = ON_nil_uuid;
    int frameCount = 0;
    std::string samplingMode;
    double samplingStart = 0.0;
    double samplingEnd = 0.0;
};

struct VideoAssembleRequest
{
    std::string runId;
    fs::path runRoot;
    fs::path framesDir;
    fs::path outputPath;
    std::string inputPattern;
    int startNumber = 1;
    int frameCount = 0;
    double fps = 0.0;
    std::string fpsSource;
    int width = 0;
    int height = 0;
    std::string codec;
    std::string container;
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

nlohmann::json MakeVideoErrorData(
    const nlohmann::json& body,
    const std::string& code,
    const std::string& message,
    nlohmann::json evidence = nlohmann::json::object())
{
    nlohmann::json data;
    data["success"] = false;
    data["run_id"] = body.contains("run_id") && body["run_id"].is_string()
        ? body["run_id"].get<std::string>()
        : "";
    data["run_root"] = body.contains("run_root") && body["run_root"].is_string()
        ? body["run_root"].get<std::string>()
        : "";
    data["frames_dir"] = body.contains("frames_dir") && body["frames_dir"].is_string()
        ? body["frames_dir"].get<std::string>()
        : "";
    data["output_path"] = body.contains("output_path") && body["output_path"].is_string()
        ? body["output_path"].get<std::string>()
        : "";
    data["backend"] = "media_foundation";
    data["platform"] = "windows";
    data["evidence"] = std::move(evidence);
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

bool IsFinitePoint(const ON_3dPoint& point)
{
    return std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z);
}

bool IsFiniteVector(const ON_3dVector& vector)
{
    return std::isfinite(vector.x) && std::isfinite(vector.y) && std::isfinite(vector.z);
}

double RequireFiniteNumber(const nlohmann::json& object, const std::string& key, const std::string& displayPath)
{
    if (!object.contains(key))
        throw DirectorFrameValidationError("invalid_input", displayPath + " is required");
    if (!object[key].is_number())
        throw DirectorFrameValidationError("invalid_input", displayPath + " must be a finite number");

    const double value = object[key].get<double>();
    if (!std::isfinite(value))
        throw DirectorFrameValidationError("invalid_input", displayPath + " must be a finite number");
    return value;
}

std::string RequireString(const nlohmann::json& object, const std::string& key, const std::string& displayPath)
{
    if (!object.contains(key))
        throw DirectorFrameValidationError("invalid_input", displayPath + " is required");
    if (!object[key].is_string() || object[key].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", displayPath + " must be a non-empty string");
    return object[key].get<std::string>();
}

int RequireIntInRange(
    const nlohmann::json& object,
    const std::string& key,
    int minimum,
    int maximum,
    const std::string& code,
    const std::string& message)
{
    if (!object.contains(key) || object[key].is_boolean() || !object[key].is_number_integer())
        throw DirectorFrameValidationError(code, message);

    const auto& value = object[key];
    if (value.is_number_unsigned())
    {
        const auto numeric = value.get<nlohmann::json::number_unsigned_t>();
        if (numeric < static_cast<nlohmann::json::number_unsigned_t>(minimum) ||
            numeric > static_cast<nlohmann::json::number_unsigned_t>(maximum))
            throw DirectorFrameValidationError(code, message);
        return static_cast<int>(numeric);
    }

    const auto numeric = value.get<nlohmann::json::number_integer_t>();
    if (numeric < static_cast<nlohmann::json::number_integer_t>(minimum) ||
        numeric > static_cast<nlohmann::json::number_integer_t>(maximum))
    {
        throw DirectorFrameValidationError(code, message);
    }
    return static_cast<int>(numeric);
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

CurveSampleRequest ParseCurveSampleRequest(const nlohmann::json& body)
{
    CurveSampleRequest request;
    request.curveId = RequireString(body, "curve_id", "curve_id");
    request.curveUuid = ON_UuidFromString(request.curveId.c_str());
    if (ON_UuidIsNil(request.curveUuid))
        throw DirectorFrameValidationError("invalid_input", "curve_id must be a valid UUID string");

    if (!body.contains("frame_count") || !body["frame_count"].is_number_integer())
        throw DirectorFrameValidationError("invalid_input", "frame_count must be an integer");
    request.frameCount = body["frame_count"].get<int>();
    if (request.frameCount < 1 || request.frameCount > kMaxDirectorCurveSampleFrameCount)
        throw DirectorFrameValidationError(
            "invalid_input",
            "frame_count must be between 1 and " + std::to_string(kMaxDirectorCurveSampleFrameCount));

    if (!body.contains("sampling") || !body["sampling"].is_object())
        throw DirectorFrameValidationError("invalid_input", "sampling must be an object");
    const auto& sampling = body["sampling"];

    request.samplingMode = RequireString(sampling, "mode", "sampling.mode");
    if (request.samplingMode != "normalized_parameter")
        throw DirectorFrameValidationError("invalid_input", "sampling.mode must be normalized_parameter");

    request.samplingStart = RequireFiniteNumber(sampling, "start", "sampling.start");
    request.samplingEnd = RequireFiniteNumber(sampling, "end", "sampling.end");
    if (request.samplingStart < 0.0 || request.samplingStart > 1.0)
        throw DirectorFrameValidationError("invalid_input", "sampling.start must be between 0 and 1");
    if (request.samplingEnd < 0.0 || request.samplingEnd > 1.0)
        throw DirectorFrameValidationError("invalid_input", "sampling.end must be between 0 and 1");
    if (request.samplingEnd < request.samplingStart)
        throw DirectorFrameValidationError("invalid_input", "sampling.start must be less than or equal to sampling.end");

    return request;
}

VideoAssembleRequest ParseVideoAssembleRequest(const nlohmann::json& body)
{
    VideoAssembleRequest request;

    if (!body.contains("run_root") || !body["run_root"].is_string() || body["run_root"].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", "run_root is required");
    request.runRoot = NormalizePolicyPath(PathFromUtf8(body["run_root"].get<std::string>()));

    if (!body.contains("frames_dir") || !body["frames_dir"].is_string() || body["frames_dir"].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", "frames_dir is required");
    request.framesDir = NormalizePolicyPath(PathFromUtf8(body["frames_dir"].get<std::string>()));

    if (!body.contains("output_path") || !body["output_path"].is_string() || body["output_path"].get<std::string>().empty())
        throw DirectorFrameValidationError("invalid_input", "output_path is required");
    request.outputPath = NormalizePolicyPath(PathFromUtf8(body["output_path"].get<std::string>()));

    request.frameCount = RequireIntInRange(
        body,
        "frame_count",
        1,
        kMaxDirectorVideoFrameCount,
        "frame_count_mismatch",
        "frame_count must be a positive integer");

    if (!body.contains("fps") || !body["fps"].is_number())
        throw DirectorFrameValidationError("fps_missing", "fps must be a positive finite number");
    request.fps = body["fps"].get<double>();
    if (!std::isfinite(request.fps) || request.fps < kMinDirectorVideoFps || request.fps > kMaxDirectorVideoFps)
        throw DirectorFrameValidationError("fps_missing", "fps must be a positive finite number");

    request.width = RequireIntInRange(
        body,
        "width",
        1,
        kMaxDirectorVideoWidth,
        "unsupported_dimensions",
        "width and height must be positive even integers");
    request.height = RequireIntInRange(
        body,
        "height",
        1,
        kMaxDirectorVideoHeight,
        "unsupported_dimensions",
        "width and height must be positive even integers");
    if ((request.width % 2) != 0 || (request.height % 2) != 0)
    {
        throw DirectorFrameValidationError("unsupported_dimensions", "width and height must be positive even integers");
    }

    if (!body.contains("codec") || !body["codec"].is_string() || body["codec"].get<std::string>() != "h264")
        throw DirectorFrameValidationError("unsupported_frame_format", "codec must be h264");
    request.codec = body["codec"].get<std::string>();

    if (!body.contains("container") || !body["container"].is_string() || body["container"].get<std::string>() != "mp4")
        throw DirectorFrameValidationError("unsupported_frame_format", "container must be mp4");
    request.container = body["container"].get<std::string>();

    if (!body.contains("input_pattern") || !body["input_pattern"].is_string() ||
        body["input_pattern"].get<std::string>() != "frame_%04d.png")
    {
        throw DirectorFrameValidationError("invalid_input", "input_pattern must be frame_%04d.png");
    }
    request.inputPattern = body["input_pattern"].get<std::string>();

    if (body.contains("start_number") && !body["start_number"].is_null())
    {
        request.startNumber = RequireIntInRange(
            body,
            "start_number",
            1,
            1,
            "invalid_input",
            "start_number must be 1");
    }

    if (body.contains("run_id") && body["run_id"].is_string())
        request.runId = body["run_id"].get<std::string>();
    if (body.contains("fps_source") && body["fps_source"].is_string())
        request.fpsSource = body["fps_source"].get<std::string>();

    return request;
}

void ValidateVideoAssemblyPolicy(const VideoAssembleRequest& request)
{
    const fs::path allowedRoot = GetAllowedDirectorRoot();
    if (!IsSameOrDescendantPath(allowedRoot, request.runRoot))
        throw DirectorFrameValidationError(
            "run_root_policy_violation",
            "run_root must be inside the native director output root");

    const fs::path expectedFramesDir = request.runRoot / L"frames";
    if (!IsSamePath(expectedFramesDir, request.framesDir))
        throw DirectorFrameValidationError(
            "frames_dir_policy_violation",
            "frames_dir must be exactly run_root/frames");

    const fs::path videosDir = request.runRoot / L"videos";
    if (!IsSameOrDescendantPath(videosDir, request.outputPath) ||
        IsSamePath(videosDir, request.outputPath))
    {
        throw DirectorFrameValidationError(
            "output_policy_violation",
            "output_path must be a file below run_root/videos");
    }
}

uint8_t ClampByte(int value)
{
    if (value < 0)
        return 0;
    if (value > 255)
        return 255;
    return static_cast<uint8_t>(value);
}

void ThrowIfFailed(HRESULT hr, const std::string& code, const std::string& message)
{
    if (FAILED(hr))
        throw DirectorFrameValidationError(code, message);
}

std::wstring GuidSuffix()
{
    GUID guid = {};
    if (FAILED(CoCreateGuid(&guid)))
        return L"guid";

    wchar_t buffer[39] = {};
    if (StringFromGUID2(guid, buffer, 39) == 0)
        return L"guid";

    std::wstring suffix(buffer);
    suffix.erase(std::remove(suffix.begin(), suffix.end(), L'{'), suffix.end());
    suffix.erase(std::remove(suffix.begin(), suffix.end(), L'}'), suffix.end());
    return suffix;
}

fs::path BuildTempVideoPath(const fs::path& outputPath)
{
    const std::wstring stem = outputPath.stem().native();
    return outputPath.parent_path() / (stem + L"." + GuidSuffix() + L".tmp.mp4");
}

fs::path FramePathForIndex(const VideoAssembleRequest& request, int frameNumber)
{
    std::wostringstream name;
    name << L"frame_" << std::setw(4) << std::setfill(L'0') << frameNumber << L".png";
    return request.framesDir / name.str();
}

void FrameRateRatio(double fps, UINT32& numerator, UINT32& denominator)
{
    const double scaled = std::round(fps * 1000.0);
    numerator = static_cast<UINT32>(scaled < 1.0 ? 1.0 : scaled);
    denominator = 1000;
}

struct DecodedFrame
{
    std::vector<uint8_t> bgra;
    bool alphaSeen = false;
};

DecodedFrame DecodePngBgra(IWICImagingFactory* factory, const fs::path& path, int expectedWidth, int expectedHeight)
{
    ComPtr<IWICBitmapDecoder> decoder;
    ThrowIfFailed(
        factory->CreateDecoderFromFilename(
            path.c_str(),
            nullptr,
            GENERIC_READ,
            WICDecodeMetadataCacheOnLoad,
            &decoder),
        "unsupported_frame_format",
        "Failed to decode PNG frame");

    GUID containerFormat = {};
    ThrowIfFailed(
        decoder->GetContainerFormat(&containerFormat),
        "unsupported_frame_format",
        "Failed to inspect frame container format");
    if (!IsEqualGUID(containerFormat, GUID_ContainerFormatPng))
        throw DirectorFrameValidationError("unsupported_frame_format", "Frame must be a PNG image");

    UINT frameCount = 0;
    ThrowIfFailed(
        decoder->GetFrameCount(&frameCount),
        "unsupported_frame_format",
        "Failed to inspect PNG frame count");
    if (frameCount < 1)
        throw DirectorFrameValidationError("unsupported_frame_format", "PNG frame does not contain image data");

    ComPtr<IWICBitmapFrameDecode> frame;
    ThrowIfFailed(
        decoder->GetFrame(0, &frame),
        "unsupported_frame_format",
        "Failed to read PNG frame");

    UINT width = 0;
    UINT height = 0;
    ThrowIfFailed(
        frame->GetSize(&width, &height),
        "unsupported_frame_format",
        "Failed to inspect PNG dimensions");
    if (width != static_cast<UINT>(expectedWidth) || height != static_cast<UINT>(expectedHeight))
        throw DirectorFrameValidationError("unsupported_frame_format", "PNG dimensions do not match requested video dimensions");

    ComPtr<IWICFormatConverter> converter;
    ThrowIfFailed(
        factory->CreateFormatConverter(&converter),
        "unsupported_frame_format",
        "Failed to create PNG format converter");

    BOOL canConvert = FALSE;
    WICPixelFormatGUID sourceFormat = {};
    ThrowIfFailed(
        frame->GetPixelFormat(&sourceFormat),
        "unsupported_frame_format",
        "Failed to inspect PNG pixel format");
    ThrowIfFailed(
        converter->CanConvert(sourceFormat, GUID_WICPixelFormat32bppBGRA, &canConvert),
        "unsupported_frame_format",
        "Failed to validate PNG pixel conversion");
    if (!canConvert)
        throw DirectorFrameValidationError("unsupported_frame_format", "PNG frame cannot be converted to BGRA");

    ThrowIfFailed(
        converter->Initialize(
            frame.Get(),
            GUID_WICPixelFormat32bppBGRA,
            WICBitmapDitherTypeNone,
            nullptr,
            0.0,
            WICBitmapPaletteTypeCustom),
        "unsupported_frame_format",
        "Failed to convert PNG frame to BGRA");

    DecodedFrame decoded;
    decoded.bgra.resize(static_cast<size_t>(expectedWidth) * static_cast<size_t>(expectedHeight) * 4);
    const UINT stride = static_cast<UINT>(expectedWidth * 4);
    ThrowIfFailed(
        converter->CopyPixels(nullptr, stride, static_cast<UINT>(decoded.bgra.size()), decoded.bgra.data()),
        "unsupported_frame_format",
        "Failed to copy PNG pixels");

    for (size_t i = 3; i < decoded.bgra.size(); i += 4)
    {
        const uint8_t alpha = decoded.bgra[i];
        if (alpha < 255)
        {
            decoded.alphaSeen = true;
            decoded.bgra[i - 3] = static_cast<uint8_t>((static_cast<int>(decoded.bgra[i - 3]) * alpha) / 255);
            decoded.bgra[i - 2] = static_cast<uint8_t>((static_cast<int>(decoded.bgra[i - 2]) * alpha) / 255);
            decoded.bgra[i - 1] = static_cast<uint8_t>((static_cast<int>(decoded.bgra[i - 1]) * alpha) / 255);
            decoded.bgra[i] = 255;
        }
    }

    return decoded;
}

std::vector<uint8_t> ConvertBgraToNv12(const std::vector<uint8_t>& bgra, int width, int height)
{
    const size_t yPlaneSize = static_cast<size_t>(width) * static_cast<size_t>(height);
    std::vector<uint8_t> nv12(yPlaneSize + yPlaneSize / 2);
    uint8_t* yPlane = nv12.data();
    uint8_t* uvPlane = nv12.data() + yPlaneSize;

    for (int y = 0; y < height; ++y)
    {
        for (int x = 0; x < width; ++x)
        {
            const size_t offset = (static_cast<size_t>(y) * width + x) * 4;
            const int b = bgra[offset + 0];
            const int g = bgra[offset + 1];
            const int r = bgra[offset + 2];
            yPlane[static_cast<size_t>(y) * width + x] = ClampByte(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16);
        }
    }

    for (int y = 0; y < height; y += 2)
    {
        for (int x = 0; x < width; x += 2)
        {
            int rSum = 0;
            int gSum = 0;
            int bSum = 0;
            for (int dy = 0; dy < 2; ++dy)
            {
                for (int dx = 0; dx < 2; ++dx)
                {
                    const size_t offset = (static_cast<size_t>(y + dy) * width + (x + dx)) * 4;
                    bSum += bgra[offset + 0];
                    gSum += bgra[offset + 1];
                    rSum += bgra[offset + 2];
                }
            }

            const int r = rSum / 4;
            const int g = gSum / 4;
            const int b = bSum / 4;
            const size_t uvOffset = static_cast<size_t>(y / 2) * width + x;
            uvPlane[uvOffset + 0] = ClampByte(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128);
            uvPlane[uvOffset + 1] = ClampByte(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128);
        }
    }

    return nv12;
}

struct VideoBackendResult
{
    bool overwroteExisting = false;
    uintmax_t bytes = 0;
    bool alphaComposited = false;
};

std::string PathToUtf8(const fs::path& path);

VideoBackendResult EncodeMp4WithMediaFoundation(const VideoAssembleRequest& request)
{
    std::error_code ec;
    fs::create_directories(request.outputPath.parent_path(), ec);
    if (ec)
        throw DirectorFrameValidationError("output_policy_violation", "Failed to create videos directory: " + ec.message());

    const fs::path tempPath = BuildTempVideoPath(request.outputPath);
    fs::remove(tempPath, ec);
    if (ec)
        throw DirectorFrameValidationError("backend_encode_failed", "Failed to clear temp video output: " + ec.message());

    HRESULT coHr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool uninitializeCom = SUCCEEDED(coHr);
    if (FAILED(coHr) && coHr != RPC_E_CHANGED_MODE)
        throw DirectorFrameValidationError("backend_unavailable", "COM initialization failed");

    bool mediaFoundationStarted = false;
    HRESULT hr = MFStartup(MF_VERSION);
    if (SUCCEEDED(hr))
        mediaFoundationStarted = true;
    try
    {
        ThrowIfFailed(hr, "backend_unavailable", "Media Foundation startup failed");

        UINT32 frameRateNumerator = 0;
        UINT32 frameRateDenominator = 0;
        FrameRateRatio(request.fps, frameRateNumerator, frameRateDenominator);

        ComPtr<IWICImagingFactory> wicFactory;
        ThrowIfFailed(
            CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&wicFactory)),
            "backend_unavailable",
            "Windows Imaging Component is unavailable");

        ComPtr<IMFSinkWriter> writer;
        ThrowIfFailed(
            MFCreateSinkWriterFromURL(tempPath.c_str(), nullptr, nullptr, &writer),
            "backend_unavailable",
            "Failed to create Media Foundation MP4 sink writer");

        ComPtr<IMFMediaType> outputType;
        ThrowIfFailed(MFCreateMediaType(&outputType), "backend_unavailable", "Failed to create output media type");
        ThrowIfFailed(outputType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video), "backend_unavailable", "Failed to set output major type");
        ThrowIfFailed(outputType->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_H264), "backend_unavailable", "Failed to set H.264 output type");
        ThrowIfFailed(outputType->SetUINT32(MF_MT_AVG_BITRATE, 8000000), "backend_unavailable", "Failed to set output bitrate");
        ThrowIfFailed(outputType->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive), "backend_unavailable", "Failed to set output interlace mode");
        ThrowIfFailed(MFSetAttributeSize(outputType.Get(), MF_MT_FRAME_SIZE, request.width, request.height), "backend_unavailable", "Failed to set output frame size");
        ThrowIfFailed(MFSetAttributeRatio(outputType.Get(), MF_MT_FRAME_RATE, frameRateNumerator, frameRateDenominator), "backend_unavailable", "Failed to set output frame rate");
        ThrowIfFailed(MFSetAttributeRatio(outputType.Get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1), "backend_unavailable", "Failed to set output pixel aspect ratio");

        DWORD streamIndex = 0;
        ThrowIfFailed(writer->AddStream(outputType.Get(), &streamIndex), "backend_unavailable", "Failed to add H.264 output stream");

        ComPtr<IMFMediaType> inputType;
        ThrowIfFailed(MFCreateMediaType(&inputType), "backend_unavailable", "Failed to create input media type");
        ThrowIfFailed(inputType->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video), "backend_unavailable", "Failed to set input major type");
        ThrowIfFailed(inputType->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_NV12), "backend_unavailable", "Failed to set NV12 input type");
        ThrowIfFailed(inputType->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive), "backend_unavailable", "Failed to set input interlace mode");
        ThrowIfFailed(MFSetAttributeSize(inputType.Get(), MF_MT_FRAME_SIZE, request.width, request.height), "backend_unavailable", "Failed to set input frame size");
        ThrowIfFailed(MFSetAttributeRatio(inputType.Get(), MF_MT_FRAME_RATE, frameRateNumerator, frameRateDenominator), "backend_unavailable", "Failed to set input frame rate");
        ThrowIfFailed(MFSetAttributeRatio(inputType.Get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1), "backend_unavailable", "Failed to set input pixel aspect ratio");
        ThrowIfFailed(writer->SetInputMediaType(streamIndex, inputType.Get(), nullptr), "backend_unavailable", "Failed to set NV12 input media type");
        ThrowIfFailed(writer->BeginWriting(), "backend_unavailable", "Failed to begin Media Foundation writing");

        VideoBackendResult result;
        const LONGLONG frameDuration = static_cast<LONGLONG>((10000000.0 / request.fps) + 0.5);
        for (int i = 0; i < request.frameCount; ++i)
        {
            const fs::path framePath = FramePathForIndex(request, request.startNumber + i);
            if (!fs::exists(framePath, ec))
                throw DirectorFrameValidationError("missing_frame", "Frame does not exist: " + PathToUtf8(framePath));

            DecodedFrame decoded = DecodePngBgra(wicFactory.Get(), framePath, request.width, request.height);
            result.alphaComposited = result.alphaComposited || decoded.alphaSeen;
            std::vector<uint8_t> nv12 = ConvertBgraToNv12(decoded.bgra, request.width, request.height);

            ComPtr<IMFMediaBuffer> buffer;
            ThrowIfFailed(MFCreateMemoryBuffer(static_cast<DWORD>(nv12.size()), &buffer), "backend_encode_failed", "Failed to create frame buffer");

            BYTE* destination = nullptr;
            DWORD maxLength = 0;
            DWORD currentLength = 0;
            ThrowIfFailed(buffer->Lock(&destination, &maxLength, &currentLength), "backend_encode_failed", "Failed to lock frame buffer");
            std::memcpy(destination, nv12.data(), nv12.size());
            ThrowIfFailed(buffer->Unlock(), "backend_encode_failed", "Failed to unlock frame buffer");
            ThrowIfFailed(buffer->SetCurrentLength(static_cast<DWORD>(nv12.size())), "backend_encode_failed", "Failed to set frame buffer length");

            ComPtr<IMFSample> sample;
            ThrowIfFailed(MFCreateSample(&sample), "backend_encode_failed", "Failed to create video sample");
            ThrowIfFailed(sample->AddBuffer(buffer.Get()), "backend_encode_failed", "Failed to attach video frame buffer");
            ThrowIfFailed(sample->SetSampleTime(static_cast<LONGLONG>(i) * frameDuration), "backend_encode_failed", "Failed to set video sample time");
            ThrowIfFailed(sample->SetSampleDuration(frameDuration), "backend_encode_failed", "Failed to set video sample duration");
            ThrowIfFailed(writer->WriteSample(streamIndex, sample.Get()), "backend_encode_failed", "Failed to write video sample");
        }

        ThrowIfFailed(writer->Finalize(), "backend_encode_failed", "Failed to finalize MP4");
        writer.Reset();
        inputType.Reset();
        outputType.Reset();

        const bool tempExists = fs::exists(tempPath, ec);
        if (ec || !tempExists)
            throw DirectorFrameValidationError("backend_encode_failed", "MP4 temp output is missing after finalize");

        const uintmax_t tempBytes = fs::file_size(tempPath, ec);
        if (ec || tempBytes == 0)
            throw DirectorFrameValidationError("backend_encode_failed", "MP4 temp output is empty after finalize");

        result.overwroteExisting = fs::exists(request.outputPath, ec);
        if (!MoveFileExW(
                tempPath.c_str(),
                request.outputPath.c_str(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        {
            throw DirectorFrameValidationError(
                "output_replace_failed",
                "Failed to atomically replace preview output with temp MP4");
        }

        result.bytes = fs::file_size(request.outputPath, ec);
        if (ec || result.bytes == 0)
            throw DirectorFrameValidationError("output_replace_failed", "MP4 output is missing or empty after replacement");

        wicFactory.Reset();
        if (mediaFoundationStarted)
            MFShutdown();
        if (uninitializeCom)
            CoUninitialize();
        return result;
    }
    catch (...)
    {
        fs::remove(tempPath, ec);
        if (mediaFoundationStarted)
            MFShutdown();
        if (uninitializeCom)
            CoUninitialize();
        throw;
    }
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

    FrameCamera camera = ParseCamera(body);

    FrameInstruction instruction;
    instruction.frameId = body["frame_id"].get<std::string>();
    instruction.frameIndex = body["frame_index"].get<int>();
    instruction.width = width;
    instruction.height = height;
    instruction.runRoot = NormalizePolicyPath(PathFromUtf8(body["run_root"].get<std::string>()));
    instruction.outputPath = NormalizePolicyPath(PathFromUtf8(body["output_path"].get<std::string>()));
    instruction.camera = camera;
    ValidateOutputPolicy(instruction.runRoot, instruction.outputPath);

    if (body.contains("display") && body["display"].is_object() &&
        body["display"].contains("mode") && body["display"]["mode"].is_string())
    {
        instruction.displayMode = body["display"]["mode"].get<std::string>();
    }

    instruction.objectTransforms = ParseFrameObjectTransforms(body);
    return instruction;
}

std::string PathToUtf8(const fs::path& path)
{
    ON_wString wide(path.native().c_str());
    return WideToUtf8(wide);
}

ON_UUID ResolveDisplayModeId(const std::string& displayMode)
{
    if (displayMode.empty() || IEquals(displayMode, "current"))
        return ON_nil_uuid;

    ON_UUID modeId = ON_UuidFromString(displayMode.c_str());
    if (!ON_UuidIsNil(modeId))
    {
        if (!CRhinoDisplayAttrsMgr::FindDisplayAttrs(modeId))
            throw DirectorFrameValidationError("invalid_input", "Display mode UUID not found");
        return modeId;
    }

    ON_wString wName = Utf8ToWide(displayMode);
    DisplayAttrsMgrListDesc* pDesc =
        CRhinoDisplayAttrsMgr::FindDisplayAttrsDesc(static_cast<const wchar_t*>(wName));
    if (!pDesc || !pDesc->m_pAttrs)
        throw DirectorFrameValidationError("invalid_input", "Display mode '" + displayMode + "' not found");

    return pDesc->m_pAttrs->Id();
}

std::vector<std::string> FrameObjectIds(const std::vector<FrameObjectTransform>& objects)
{
    std::vector<std::string> ids;
    ids.reserve(objects.size());
    for (const FrameObjectTransform& object : objects)
        ids.push_back(object.objectId);
    return ids;
}

nlohmann::json FrameCameraToJson(const FrameCamera& camera)
{
    nlohmann::json data;
    data["projection"] = "perspective";
    data["location"] = PointToJson(camera.location);
    data["target"] = PointToJson(camera.target);
    data["up"] = VectorToJson(camera.up);
    data["lens_length"] = camera.hasLensLength ? nlohmann::json(RoundTo(camera.lensLength, 6)) : nlohmann::json(nullptr);
    data["fov_degrees"] = camera.hasFovDegrees ? nlohmann::json(RoundTo(camera.fovDegrees, 6)) : nlohmann::json(nullptr);
    data["aspect"] = camera.hasAspect ? nlohmann::json(RoundTo(camera.aspect, 6)) : nlohmann::json(nullptr);
    data["near_clip"] = camera.hasNearFar ? nlohmann::json(RoundTo(camera.nearClip, 6)) : nlohmann::json(nullptr);
    data["far_clip"] = camera.hasNearFar ? nlohmann::json(RoundTo(camera.farClip, 6)) : nlohmann::json(nullptr);
    return data;
}

nlohmann::json SerializeViewportCameraReadback(const ON_Viewport& vp)
{
    nlohmann::json camera = SerializeViewportCamera(vp);
    camera["direction"] = VectorToJson(vp.CameraDirection());
    return camera;
}

nlohmann::json ApplyViewportForFrame(CRhinoView* pView, const FrameInstruction& instruction, ON_UUID displayModeId)
{
    if (!pView)
        throw std::runtime_error("No active view");
    ValidateSlice1ModelRhinoView(pView);

    nlohmann::json evidence;
    evidence["display_resolved"] = DisplayModeToJson(displayModeId);

    // Apply camera (pure camera-set shared with replay; no display mode, no evidence).
    SetCameraFromFrame(pView, instruction.camera);

    // Apply display mode on top of the camera that SetCameraFromFrame already set.
    CRhinoViewport& rhinoViewport = pView->ActiveViewport();
    bool displaySetAccepted = true;
    if (!ON_UuidIsNil(displayModeId))
    {
        displaySetAccepted = rhinoViewport.SetDisplayMode(displayModeId);
    }
    pView->Redraw();

    evidence["camera_applied"] = SerializeViewportCameraReadback(rhinoViewport.VP());
    const ON_UUID appliedDisplayModeId = CurrentDisplayModeId(pView);
    const bool displayReadbackMatches = ON_UuidIsNil(displayModeId) ||
        ON_UuidCompare(appliedDisplayModeId, displayModeId) == 0;
    evidence["display_readback_mode"] = DisplayModeToJson(appliedDisplayModeId);
    evidence["display_set_accepted"] = displaySetAccepted;
    evidence["display_readback_matches"] = displayReadbackMatches;
    evidence["display_applied"] = DisplayModeToJson(appliedDisplayModeId);
    evidence["display_applied_ok"] = displayReadbackMatches;
    return evidence;
}

nlohmann::json SampleDirectorCurve(CRhinoDoc* pDoc, const CurveSampleRequest& request)
{
    if (!pDoc)
        throw std::runtime_error("No active document");

    const CRhinoObject* obj = pDoc->LookupObject(request.curveUuid);
    if (!obj || obj->IsDeleted())
        throw DirectorFrameValidationError("curve_not_found", "Curve not found: " + request.curveId);

    const ON_Curve* curve = ON_Curve::Cast(obj->Geometry());
    if (!curve)
        throw DirectorFrameValidationError("not_curve", "Object is not a curve: " + request.curveId);

    nlohmann::json samples = nlohmann::json::array();
    samples.get_ref<nlohmann::json::array_t&>().reserve(static_cast<size_t>(request.frameCount));

    for (int frameIndex = 1; frameIndex <= request.frameCount; ++frameIndex)
    {
        const double u = request.frameCount == 1
            ? 0.0
            : static_cast<double>(frameIndex - 1) / static_cast<double>(request.frameCount - 1);
        const double normalizedParameter = request.samplingStart +
            (request.samplingEnd - request.samplingStart) * u;
        const double curveParameter = curve->Domain().ParameterAt(normalizedParameter);
        if (!std::isfinite(curveParameter))
            throw DirectorFrameValidationError("invalid_curve_sample", "Mapped curve parameter is not finite");

        ON_3dPoint point = curve->PointAt(curveParameter);
        ON_3dVector tangent = curve->TangentAt(curveParameter);
        if (!IsFinitePoint(point))
            throw DirectorFrameValidationError("invalid_curve_sample", "Curve sample point is not finite");
        if (!IsFiniteVector(tangent))
            throw DirectorFrameValidationError("invalid_curve_sample", "Curve sample tangent is not finite");
        if (!tangent.Unitize())
            throw DirectorFrameValidationError("invalid_curve_sample", "Curve sample tangent is degenerate");

        nlohmann::json sample;
        sample["frame_index"] = frameIndex;
        sample["normalized_parameter"] = RoundTo(normalizedParameter, 6);
        sample["curve_parameter"] = RoundTo(curveParameter, 6);
        sample["point"] = PointToJson(point);
        sample["tangent"] = VectorToJson(tangent);
        samples.push_back(std::move(sample));
    }

    nlohmann::json provenance;
    provenance["sampling_mode"] = "normalized_parameter";
    provenance["parameter_mapping"] = "curve_domain_parameter_at";
    provenance["frame_count_source"] = "caller_canonical_frame_count";
    provenance["arc_length_sampled"] = false;
    provenance["validation_strength"] = "curve_parameter_sampled";

    nlohmann::json result;
    result["schema_version"] = 1;
    result["curve_id"] = request.curveId;
    result["frame_count"] = request.frameCount;
    result["samples"] = std::move(samples);
    result["provenance"] = std::move(provenance);
    return result;
}

fs::path BuildTempCapturePath(const fs::path& outputPath)
{
    std::wstring tempName = outputPath.filename().native() + L".tmp.png";
    return outputPath.parent_path() / tempName;
}

void CaptureViewportToFile(CRhinoDoc* pDoc, const FrameInstruction& instruction, const fs::path& tempPath)
{
    if (!pDoc)
        throw std::runtime_error("No active document");

    ON_wString wFilePath(tempPath.native().c_str());
    std::wstring captureCmd = std::wstring(L"_-ViewCaptureToFile") +
        L" _Width=" + std::to_wstring(instruction.width) +
        L" _Height=" + std::to_wstring(instruction.height) +
        L" _Scale=1" +
        L" _DrawGrid=No" +
        L" _DrawWorldAxes=No" +
        L" _DrawCPlaneAxes=No" +
        L" _TransparentBackground=No" +
        L" \"" + std::wstring(static_cast<const wchar_t*>(wFilePath)) + L"\"" +
        L" _Enter";

    RhinoApp().RunScript(pDoc->RuntimeSerialNumber(), captureCmd.c_str(), 0);
}

void ReplaceOutputFromTemp(const fs::path& tempPath, const fs::path& outputPath, bool& overwroteExisting)
{
    std::error_code ec;
    if (!fs::exists(tempPath, ec) || fs::file_size(tempPath, ec) == 0)
        throw std::runtime_error("Viewport capture did not create a non-empty temp file");

    overwroteExisting = fs::exists(outputPath, ec);
    if (overwroteExisting)
    {
        fs::remove(outputPath, ec);
        if (ec)
            throw std::runtime_error("Failed to replace existing output file: " + ec.message());
    }

    fs::rename(tempPath, outputPath, ec);
    if (ec)
        throw std::runtime_error("Failed to move temp capture into output path: " + ec.message());

    if (!fs::exists(outputPath, ec) || fs::file_size(outputPath, ec) == 0)
        throw std::runtime_error("Output file is missing or empty after capture");
}

nlohmann::json BaseFrameEvidence(const FrameInstruction& instruction)
{
    nlohmann::json data;
    data["frame_id"] = instruction.frameId;
    data["frame_index"] = instruction.frameIndex;
    data["success"] = false;
    data["dirty_partial_state"] = false;
    data["affected_object_ids"] = FrameObjectIds(instruction.objectTransforms);
    data["output_path"] = PathToUtf8(instruction.outputPath);
    data["run_root"] = PathToUtf8(instruction.runRoot);
    data["validation_strength"] = "bbox_only";
    data["capture"] = {
        { "width", instruction.width },
        { "height", instruction.height },
        { "output_path", PathToUtf8(instruction.outputPath) }
    };
    data["camera"] = {
        { "requested", FrameCameraToJson(instruction.camera) },
        { "applied", nullptr }
    };
    data["display"] = {
        { "requested_mode", instruction.displayMode.empty() ? "current" : instruction.displayMode },
        { "resolved_mode", nullptr },
        { "applied_mode", nullptr },
        { "applied", false },
        { "set_accepted", nullptr },
        { "readback_mode", nullptr },
        { "readback_matches", false },
        { "restored", false }
    };
    data["objects"] = {
        { "requested", static_cast<int>(instruction.objectTransforms.size()) },
        { "applied", 0 },
        { "restored", 0 },
        { "validation_strength", "bbox_only" },
        { "details", nlohmann::json::array() }
    };
    data["viewport"] = {
        { "active_view_resolved", false },
        { "restored", false },
        { "restore_verified", false }
    };
    return data;
}

nlohmann::json ExecuteFrameTransaction(CRhinoDoc* pDoc, const FrameInstruction& instruction)
{
    nlohmann::json data = BaseFrameEvidence(instruction);

    ValidateFrameObjects(pDoc, instruction.objectTransforms);
    ON_UUID displayModeId = ResolveDisplayModeId(instruction.displayMode);

    std::error_code ec;
    fs::create_directories(instruction.outputPath.parent_path(), ec);
    if (ec)
        throw DirectorFrameValidationError("output_policy_violation", "Failed to create output directory: " + ec.message());

    const fs::path tempPath = BuildTempCapturePath(instruction.outputPath);
    data["temp_output_path"] = PathToUtf8(tempPath);
    data["capture"]["temp_output_path"] = PathToUtf8(tempPath);

    fs::remove(tempPath, ec);
    if (ec)
        throw std::runtime_error("Failed to clear stale temp capture file: " + ec.message());

    bool overwroteExisting = false;
    DirectorObjectPoseGuard objectGuard(pDoc, instruction.objectTransforms);
    DirectorViewportGuard viewportGuard(pDoc);
    data["viewport"]["active_view_resolved"] = true;

    try
    {
        objectGuard.Apply();
        data["objects"]["applied"] = objectGuard.AppliedCount();

        nlohmann::json viewportApplyEvidence = ApplyViewportForFrame(viewportGuard.View(), instruction, displayModeId);
        data["camera"]["applied"] = std::move(viewportApplyEvidence["camera_applied"]);
        data["display"]["resolved_mode"] = std::move(viewportApplyEvidence["display_resolved"]);
        data["display"]["applied_mode"] = std::move(viewportApplyEvidence["display_applied"]);
        data["display"]["applied"] = viewportApplyEvidence["display_applied_ok"];
        data["display"]["set_accepted"] = viewportApplyEvidence["display_set_accepted"];
        data["display"]["readback_mode"] = std::move(viewportApplyEvidence["display_readback_mode"]);
        data["display"]["readback_matches"] = viewportApplyEvidence["display_readback_matches"];
        if (!data["display"]["applied"].get<bool>())
            throw DirectorFrameValidationError("invalid_input", "Applied display mode did not match requested mode");
        CaptureViewportToFile(pDoc, instruction, tempPath);
        ReplaceOutputFromTemp(tempPath, instruction.outputPath, overwroteExisting);
        data["overwrote_existing"] = overwroteExisting;

        const bool objectsRestored = objectGuard.Restore(data);
        const bool viewportRestored = viewportGuard.Restore(data);
        const bool clean = objectsRestored && viewportRestored;
        data["dirty_partial_state"] = !clean;
        data["success"] = clean;
        if (!clean)
            data["error"] = MakeErrorData("unsafe_failed", "Frame captured but restoration could not be verified");
        return data;
    }
    catch (const DirectorFrameValidationError& ex)
    {
        objectGuard.Restore(data);
        viewportGuard.Restore(data);
        data["dirty_partial_state"] = objectGuard.HasDirtyPartialState() || !viewportGuard.IsRestored();
        data["error"] = MakeErrorData(data["dirty_partial_state"].get<bool>() ? "unsafe_failed" : ex.code, ex.what());
        data["success"] = false;
        return data;
    }
    catch (const std::exception& ex)
    {
        objectGuard.Restore(data);
        viewportGuard.Restore(data);
        data["dirty_partial_state"] = objectGuard.HasDirtyPartialState() || !viewportGuard.IsRestored();
        data["error"] = MakeErrorData(data["dirty_partial_state"].get<bool>() ? "unsafe_failed" : "native_frame_failed", ex.what());
        data["success"] = false;
        return data;
    }
}

constexpr int kMaxDirectorOccurrencePageSize = 1000;
constexpr std::size_t kMaxDirectorOccurrenceInventorySessions = 32;
constexpr const char* kDirectorOccurrenceTraversalOrdering = "native_instance_definition_depth_first_v1";
constexpr int kDirectorOccurrenceTraversalOrderingVersion = 1;

struct OccurrenceInventoryRequest
{
    bool continuation = false;
    std::string inventorySessionId;
    int pageSize = 0;
    std::size_t cursor = 0;
    std::vector<ON_UUID> sourceObjectUuids;
    std::vector<std::string> sourceObjectIds;
};

struct OccurrenceInventorySession
{
    std::string inventorySessionId;
    unsigned int documentRuntimeSerial = 0;
    std::string sourceDocumentKey;
    std::string documentContextKey;
    std::string traversalOrdering;
    int traversalOrderingVersion = 0;
    int pageSize = 0;
    std::vector<ON_UUID> sourceObjectUuids;
    std::vector<std::string> sourceObjectIds;
    nlohmann::json inventoryContextFingerprint;
    std::vector<nlohmann::json> records;
    std::vector<std::string> warnings;
};

std::mutex g_occurrenceInventoryMutex;
std::unordered_map<std::string, OccurrenceInventorySession> g_occurrenceInventorySessions;
std::deque<std::string> g_occurrenceInventorySessionOrder;
std::atomic<unsigned long long> g_occurrenceInventorySessionCounter{ 1 };
std::mutex g_occurrenceDocumentKeyMutex;
std::unordered_map<unsigned int, std::string> g_unsavedOccurrenceDocumentKeys;

void ThrowOccurrenceSessionInvalid(const std::string& message)
{
    throw DirectorFrameValidationError("inventory_session_invalid", message);
}

std::string MakeOccurrenceInventorySessionId(unsigned int documentRuntimeSerial)
{
    const unsigned long long ordinal = g_occurrenceInventorySessionCounter.fetch_add(1);
    return "inv_" + std::to_string(documentRuntimeSerial) + "_" + std::to_string(ordinal);
}

uint64_t Fnv1a64ForOccurrence(const std::string& value)
{
    uint64_t hash = 14695981039346656037ULL;
    for (char c : value)
    {
        hash ^= static_cast<uint64_t>(static_cast<unsigned char>(c));
        hash *= 1099511628211ULL;
    }
    return hash;
}

std::string Hex64ForOccurrence(uint64_t value)
{
    std::ostringstream out;
    out << std::hex << std::setw(16) << std::setfill('0') << value;
    return out.str();
}

std::string NormalizeDocumentPathForOccurrenceKey(std::string path)
{
    std::replace(path.begin(), path.end(), '\\', '/');
    std::transform(path.begin(), path.end(), path.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return path;
}

std::string UnsavedSourceDocumentKeyForOccurrence(unsigned int documentRuntimeSerial)
{
    std::lock_guard<std::mutex> lock(g_occurrenceDocumentKeyMutex);
    auto existing = g_unsavedOccurrenceDocumentKeys.find(documentRuntimeSerial);
    if (existing != g_unsavedOccurrenceDocumentKeys.end())
        return existing->second;

    ON_UUID keyUuid = ON_nil_uuid;
    if (FAILED(CoCreateGuid(&keyUuid)))
        throw std::runtime_error("Could not allocate unsaved source document key");

    const std::string key = UuidToString(keyUuid);
    g_unsavedOccurrenceDocumentKeys[documentRuntimeSerial] = key;
    return key;
}

nlohmann::json XformToJson(const ON_Xform& xform)
{
    nlohmann::json rows = nlohmann::json::array();
    for (int row = 0; row < 4; ++row)
    {
        rows.push_back(nlohmann::json::array({
            RoundTo(xform.m_xform[row][0], 6),
            RoundTo(xform.m_xform[row][1], 6),
            RoundTo(xform.m_xform[row][2], 6),
            RoundTo(xform.m_xform[row][3], 6)
        }));
    }
    return rows;
}

nlohmann::json RequiredBoundingBoxJsonForOccurrence(
    const ON_BoundingBox& bbox,
    const std::string& objectId,
    const char* factName,
    std::vector<std::string>& warnings)
{
    if (bbox.IsValid())
        return BoundingBoxToJson(bbox);

    warnings.push_back(std::string(factName) + ": bbox_unavailable_zero_fallback for object " + objectId);
    return {
        {"min", {0.0, 0.0, 0.0}},
        {"max", {0.0, 0.0, 0.0}},
        {"fallback", "bbox_unavailable_zero_fallback"}
    };
}

ON_BoundingBox TransformBoundingBoxForOccurrence(const ON_BoundingBox& bbox, const ON_Xform& xform)
{
    if (!bbox.IsValid())
        return bbox;

    const ON_3dPoint minPt = bbox.Min();
    const ON_3dPoint maxPt = bbox.Max();
    const ON_3dPoint corners[8] = {
        ON_3dPoint(minPt.x, minPt.y, minPt.z),
        ON_3dPoint(maxPt.x, minPt.y, minPt.z),
        ON_3dPoint(minPt.x, maxPt.y, minPt.z),
        ON_3dPoint(maxPt.x, maxPt.y, minPt.z),
        ON_3dPoint(minPt.x, minPt.y, maxPt.z),
        ON_3dPoint(maxPt.x, minPt.y, maxPt.z),
        ON_3dPoint(minPt.x, maxPt.y, maxPt.z),
        ON_3dPoint(maxPt.x, maxPt.y, maxPt.z)
    };

    const ON_3dPoint first = xform * corners[0];
    ON_BoundingBox transformed(first, first);
    for (int i = 1; i < 8; ++i)
    {
        const ON_3dPoint point = xform * corners[i];
        transformed.m_min.x = (std::min)(transformed.m_min.x, point.x);
        transformed.m_min.y = (std::min)(transformed.m_min.y, point.y);
        transformed.m_min.z = (std::min)(transformed.m_min.z, point.z);
        transformed.m_max.x = (std::max)(transformed.m_max.x, point.x);
        transformed.m_max.y = (std::max)(transformed.m_max.y, point.y);
        transformed.m_max.z = (std::max)(transformed.m_max.z, point.z);
    }
    return transformed;
}

std::string ObjectLayerPathForOccurrence(
    CRhinoDoc* pDoc,
    const ON_3dmObjectAttributes& attrs,
    const std::string& objectId,
    std::vector<std::string>& warnings)
{
    const int layerIndex = attrs.m_layer_index;
    if (layerIndex >= 0 && layerIndex < pDoc->m_layer_table.LayerCount())
    {
        ON_wString layerPath;
        pDoc->m_layer_table.GetLayerPathName(layerIndex, layerPath);
        return WideToUtf8(layerPath);
    }

    warnings.push_back("missing_layer_path: object " + objectId + " has no resolvable layer path");
    return "Default";
}

nlohmann::json MaterialRefForOccurrence(
    CRhinoDoc* pDoc,
    const ON_3dmObjectAttributes& attrs,
    const std::string& objectId,
    std::vector<std::string>& warnings)
{
    nlohmann::json material;
    material["material_index"] = attrs.m_material_index >= 0 ? nlohmann::json(attrs.m_material_index) : nlohmann::json(nullptr);
    material["material_name"] = nullptr;

    switch (attrs.MaterialSource())
    {
    case ON::material_from_object:
        material["source"] = "object";
        if (attrs.m_material_index >= 0 && attrs.m_material_index < pDoc->m_material_table.MaterialCount())
        {
            material["material_name"] = WideToUtf8(pDoc->m_material_table[attrs.m_material_index].Name());
        }
        else if (attrs.m_material_index >= 0)
        {
            warnings.push_back("missing_material: object " + objectId + " references unavailable material index " +
                std::to_string(attrs.m_material_index));
        }
        break;
    case ON::material_from_parent:
        material["source"] = "parent";
        break;
    case ON::material_from_layer:
        material["source"] = "layer";
        break;
    default:
        material["source"] = "unknown";
        warnings.push_back("unsupported_material_source: object " + objectId + " has an unrecognized material source");
        break;
    }

    return material;
}

ON_BoundingBox ObjectLocalBoundsForOccurrence(
    const CRhinoObject* obj,
    const std::string& objectId,
    std::vector<std::string>& warnings)
{
    ON_BoundingBox bbox;
    if (obj && obj->GetTightBoundingBox(bbox) && bbox.IsValid())
        return bbox;

    if (obj)
    {
        bbox = obj->BoundingBox();
        if (bbox.IsValid())
            return bbox;
    }

    warnings.push_back("missing_bbox: object " + objectId + " did not provide a valid bounding box");
    return ON_BoundingBox::EmptyBoundingBox;
}

void AddDefinitionFieldsForOccurrence(
    nlohmann::json& target,
    const CRhinoInstanceDefinition* definition,
    int definitionObjectIndex)
{
    if (definition)
    {
        target["definition_name"] = WideToUtf8(definition->Name());
        target["definition_id"] = UuidToString(definition->Id());
        target["definition_index"] = definition->Index();
    }
    else
    {
        target["definition_name"] = nullptr;
        target["definition_id"] = nullptr;
        target["definition_index"] = nullptr;
    }

    target["definition_object_index"] =
        definitionObjectIndex >= 0 ? nlohmann::json(definitionObjectIndex) : nlohmann::json(nullptr);
}

std::string SegmentFingerprintForOccurrence(
    const std::string& kind,
    const std::string& objectId,
    const CRhinoInstanceDefinition* definition,
    int definitionObjectIndex,
    int siblingOrdinal)
{
    std::string value = kind + "|" + objectId + "|";
    value += definition ? UuidToString(definition->Id()) : "top";
    value += "|" + std::to_string(definitionObjectIndex);
    value += "|" + std::to_string(siblingOrdinal);
    return value;
}

nlohmann::json BuildOccurrencePathSegment(
    CRhinoDoc* pDoc,
    const std::string& kind,
    const CRhinoObject* obj,
    const CRhinoInstanceDefinition* definition,
    int definitionObjectIndex,
    int siblingOrdinal,
    const ON_Xform& localTransform,
    const ON_Xform& worldTransform,
    const ON_BoundingBox& localBbox,
    const ON_BoundingBox& worldBbox,
    std::vector<std::string>& warnings)
{
    const ON_3dmObjectAttributes& attrs = obj->Attributes();
    const std::string objectId = UuidToString(attrs.m_uuid);

    nlohmann::json segment;
    segment["kind"] = kind;
    AddDefinitionFieldsForOccurrence(segment, definition, definitionObjectIndex);
    segment["instance_reference_id"] = CRhinoInstanceObject::Cast(obj) ? nlohmann::json(objectId) : nlohmann::json(nullptr);
    segment["sibling_ordinal"] = siblingOrdinal;
    segment["object_id"] = objectId;
    segment["object_name"] = WideToUtf8(attrs.m_name);
    segment["object_type"] = ObjectTypeToString(obj->ObjectType());
    segment["layer_path"] = ObjectLayerPathForOccurrence(pDoc, attrs, objectId, warnings);
    segment["material_ref"] = MaterialRefForOccurrence(pDoc, attrs, objectId, warnings);
    segment["local_transform"] = XformToJson(localTransform);
    segment["world_transform"] = XformToJson(worldTransform);
    segment["local_bbox"] = RequiredBoundingBoxJsonForOccurrence(
        localBbox, objectId, "local_bbox", warnings);
    segment["world_bbox"] = RequiredBoundingBoxJsonForOccurrence(
        worldBbox, objectId, "world_bbox", warnings);
    segment["segment_fingerprint"] = SegmentFingerprintForOccurrence(
        kind, objectId, definition, definitionObjectIndex, siblingOrdinal);

    if (const CRhinoInstanceObject* instance = CRhinoInstanceObject::Cast(obj))
    {
        const CRhinoInstanceDefinition* referenced = instance->InstanceDefinition();
        if (referenced)
        {
            segment["referenced_definition_name"] = WideToUtf8(referenced->Name());
            segment["referenced_definition_id"] = UuidToString(referenced->Id());
            segment["referenced_definition_index"] = referenced->Index();
        }
        else
        {
            segment["referenced_definition_name"] = nullptr;
            segment["referenced_definition_id"] = nullptr;
            segment["referenced_definition_index"] = nullptr;
        }
    }

    return segment;
}

nlohmann::json BuildOccurrenceRecord(
    const std::string& recordKind,
    const std::string& sourceTopLevelObjectId,
    const std::string& nativeRoleHint,
    const nlohmann::json& sourceOccurrencePath)
{
    const nlohmann::json& leaf = sourceOccurrencePath.back();

    nlohmann::json record;
    record["record_kind"] = recordKind;
    record["source_top_level_object_id"] = sourceTopLevelObjectId;
    record["source_occurrence_path"] = sourceOccurrencePath;
    record["object_id"] = leaf["object_id"];
    record["object_name"] = leaf["object_name"];
    record["object_type"] = leaf["object_type"];
    record["layer_path"] = leaf["layer_path"];
    record["material_ref"] = leaf["material_ref"];
    record["local_transform"] = leaf["local_transform"];
    record["world_transform"] = leaf["world_transform"];
    record["local_bbox"] = leaf["local_bbox"];
    record["world_bbox"] = leaf["world_bbox"];
    record["definition_name"] = leaf["definition_name"];
    record["definition_id"] = leaf["definition_id"];
    record["definition_object_index"] = leaf["definition_object_index"];
    record["native_role_hint"] = nativeRoleHint;
    return record;
}

void TraverseOccurrenceDefinition(
    CRhinoDoc* pDoc,
    const CRhinoInstanceDefinition* definition,
    const ON_Xform& parentWorldTransform,
    const std::string& sourceTopLevelObjectId,
    const nlohmann::json& parentPath,
    std::vector<nlohmann::json>& records,
    std::vector<std::string>& warnings,
    std::set<int>& definitionStack)
{
    if (!definition)
    {
        warnings.push_back("missing_definition: instance reference did not resolve to a definition");
        return;
    }

    if (definitionStack.count(definition->Index()) > 0)
    {
        warnings.push_back("circular_definition_reference: skipped recursive definition " +
            WideToUtf8(definition->Name()));
        return;
    }

    definitionStack.insert(definition->Index());

    for (int objectIndex = 0; objectIndex < definition->ObjectCount(); ++objectIndex)
    {
        const CRhinoObject* obj = definition->Object(objectIndex);
        if (!obj)
        {
            warnings.push_back("missing_definition_object: definition " + WideToUtf8(definition->Name()) +
                " has null object at index " + std::to_string(objectIndex));
            continue;
        }

        const std::string objectId = UuidToString(obj->Attributes().m_uuid);
        const CRhinoInstanceObject* nestedInstance = CRhinoInstanceObject::Cast(obj);
        const ON_Xform localTransform = nestedInstance
            ? nestedInstance->InstanceXform()
            : ON_Xform::IdentityTransformation;
        const ON_Xform worldTransform = parentWorldTransform * localTransform;
        const ON_BoundingBox localBbox = ObjectLocalBoundsForOccurrence(obj, objectId, warnings);
        // CRhinoInstanceObject object-level bounds already include its local instance transform.
        const ON_BoundingBox worldBbox = nestedInstance
            ? TransformBoundingBoxForOccurrence(localBbox, parentWorldTransform)
            : TransformBoundingBoxForOccurrence(localBbox, worldTransform);

        nlohmann::json path = parentPath;
        path.push_back(BuildOccurrencePathSegment(
            pDoc,
            nestedInstance ? "nested_instance" : "definition_object",
            obj,
            definition,
            objectIndex,
            objectIndex,
            localTransform,
            worldTransform,
            localBbox,
            worldBbox,
            warnings));

        records.push_back(BuildOccurrenceRecord(
            nestedInstance ? "nested_instance" : "definition_object",
            sourceTopLevelObjectId,
            nestedInstance ? "nested_instance_reference" : "definition_leaf_object",
            path));

        if (nestedInstance)
        {
            const CRhinoInstanceDefinition* nestedDefinition = nestedInstance->InstanceDefinition();
            if (!nestedDefinition)
            {
                warnings.push_back("missing_definition: nested instance " + objectId +
                    " did not resolve to a definition");
                continue;
            }

            TraverseOccurrenceDefinition(
                pDoc,
                nestedDefinition,
                worldTransform,
                sourceTopLevelObjectId,
                path,
                records,
                warnings,
                definitionStack);
        }
    }

    definitionStack.erase(definition->Index());
}

void AppendOccurrenceActorRoot(
    CRhinoDoc* pDoc,
    const CRhinoObject* obj,
    int sourceOrdinal,
    std::vector<nlohmann::json>& records,
    std::vector<std::string>& warnings)
{
    const std::string sourceTopLevelObjectId = UuidToString(obj->Attributes().m_uuid);
    const CRhinoInstanceObject* instance = CRhinoInstanceObject::Cast(obj);
    const CRhinoInstanceDefinition* definition = instance ? instance->InstanceDefinition() : nullptr;
    const ON_Xform localTransform = instance
        ? instance->InstanceXform()
        : ON_Xform::IdentityTransformation;
    const ON_Xform worldTransform = localTransform;
    const ON_BoundingBox localBbox = ObjectLocalBoundsForOccurrence(obj, sourceTopLevelObjectId, warnings);
    // Selected instance object bounds are already in document space.
    const ON_BoundingBox worldBbox = instance
        ? localBbox
        : TransformBoundingBoxForOccurrence(localBbox, worldTransform);

    nlohmann::json path = nlohmann::json::array();
    path.push_back(BuildOccurrencePathSegment(
        pDoc,
        "actor_root",
        obj,
        definition,
        -1,
        sourceOrdinal,
        localTransform,
        worldTransform,
        localBbox,
        worldBbox,
        warnings));

    records.push_back(BuildOccurrenceRecord(
        "actor_root",
        sourceTopLevelObjectId,
        instance ? "selected_instance_root" : "selected_object_root",
        path));

    if (instance)
    {
        if (!definition)
        {
            warnings.push_back("missing_definition: selected instance " + sourceTopLevelObjectId +
                " did not resolve to a definition");
            return;
        }

        std::set<int> definitionStack;
        TraverseOccurrenceDefinition(
            pDoc,
            definition,
            worldTransform,
            sourceTopLevelObjectId,
            path,
            records,
            warnings,
            definitionStack);
    }
}

std::string SourceDocumentKeyForOccurrence(CRhinoDoc* pDoc)
{
    const std::string path = WideToUtf8(pDoc->GetPathName());
    if (path.empty())
        return "unsaved_session:" + UnsavedSourceDocumentKeyForOccurrence(pDoc->RuntimeSerialNumber());

    return "source_path_hash:" + Hex64ForOccurrence(
        Fnv1a64ForOccurrence(NormalizeDocumentPathForOccurrenceKey(path)));
}

std::string DocumentContextKeyForOccurrence(CRhinoDoc* pDoc)
{
    const std::string path = WideToUtf8(pDoc->GetPathName());
    return "document_runtime_serial:" + std::to_string(pDoc->RuntimeSerialNumber()) +
        ":path:" + (path.empty() ? "<unsaved>" : path);
}

nlohmann::json InventoryContextFingerprintForOccurrence(CRhinoDoc* pDoc)
{
    nlohmann::json fingerprint;
    fingerprint["document_runtime_serial"] = pDoc->RuntimeSerialNumber();
    fingerprint["traversal_ordering"] = kDirectorOccurrenceTraversalOrdering;
    fingerprint["traversal_ordering_version"] = kDirectorOccurrenceTraversalOrderingVersion;
    return fingerprint;
}

std::vector<ON_UUID> ParseOccurrenceSourceObjectIds(
    const nlohmann::json& body,
    std::vector<std::string>& sourceObjectIds)
{
    if (!body.contains("source_object_ids") || !body["source_object_ids"].is_array() ||
        body["source_object_ids"].empty())
    {
        ThrowOccurrenceSessionInvalid("source_object_ids must be a non-empty array on the first inventory page");
    }

    std::vector<ON_UUID> uuids;
    uuids.reserve(body["source_object_ids"].size());
    sourceObjectIds.reserve(body["source_object_ids"].size());

    for (const auto& item : body["source_object_ids"])
    {
        if (!item.is_string())
            ThrowOccurrenceSessionInvalid("source_object_ids entries must be UUID strings");

        const std::string id = item.get<std::string>();
        const ON_UUID uuid = ON_UuidFromString(id.c_str());
        if (ON_UuidIsNil(uuid))
            ThrowOccurrenceSessionInvalid("source_object_ids contains an invalid UUID: " + id);

        uuids.push_back(uuid);
        sourceObjectIds.push_back(UuidToString(uuid));
    }

    return uuids;
}

int ParseOccurrencePageSize(const nlohmann::json& body)
{
    if (!body.contains("page_size") || body["page_size"].is_boolean() ||
        !body["page_size"].is_number_integer())
    {
        ThrowOccurrenceSessionInvalid("page_size must be an integer");
    }

    const int pageSize = body["page_size"].get<int>();
    if (pageSize < 1 || pageSize > kMaxDirectorOccurrencePageSize)
    {
        ThrowOccurrenceSessionInvalid(
            "page_size must be between 1 and " + std::to_string(kMaxDirectorOccurrencePageSize));
    }

    return pageSize;
}

std::size_t ParseOccurrenceCursorString(const std::string& cursor)
{
    if (cursor.empty())
        ThrowOccurrenceSessionInvalid("cursor must be a non-empty decimal string");

    const bool allDigits = std::all_of(cursor.begin(), cursor.end(), [](unsigned char ch) {
        return std::isdigit(ch) != 0;
    });
    if (!allDigits)
        ThrowOccurrenceSessionInvalid("cursor must be a decimal offset string");

    try
    {
        return static_cast<std::size_t>(std::stoull(cursor));
    }
    catch (const std::exception&)
    {
        ThrowOccurrenceSessionInvalid("cursor is outside the supported range");
    }

    return 0;
}

OccurrenceInventoryRequest ParseOccurrenceInventoryRequest(const nlohmann::json& body)
{
    OccurrenceInventoryRequest request;
    request.pageSize = ParseOccurrencePageSize(body);

    if (body.contains("inventory_session_id"))
    {
        if (!body["inventory_session_id"].is_string() ||
            body["inventory_session_id"].get<std::string>().empty())
        {
            ThrowOccurrenceSessionInvalid("inventory_session_id must be a non-empty string");
        }
        request.inventorySessionId = body["inventory_session_id"].get<std::string>();
        request.continuation = true;
    }

    if (request.continuation)
    {
        if (!body.contains("cursor") || !body["cursor"].is_string())
            ThrowOccurrenceSessionInvalid("cursor must be a string on continuation inventory pages");
        request.cursor = ParseOccurrenceCursorString(body["cursor"].get<std::string>());
        return request;
    }

    if (body.contains("cursor") && !body["cursor"].is_null())
        ThrowOccurrenceSessionInvalid("cursor must be null on the first inventory page");

    request.sourceObjectUuids = ParseOccurrenceSourceObjectIds(body, request.sourceObjectIds);
    return request;
}

void PopulateOccurrenceInventorySession(CRhinoDoc* pDoc, OccurrenceInventorySession& session)
{
    for (std::size_t i = 0; i < session.sourceObjectUuids.size(); ++i)
    {
        const ON_UUID uuid = session.sourceObjectUuids[i];
        const std::string id = session.sourceObjectIds[i];
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj || obj->IsDeleted())
        {
            throw DirectorFrameValidationError(
                "inventory_stale",
                "missing_source_object: selected source object " + id + " was not found");
        }

        AppendOccurrenceActorRoot(
            pDoc,
            obj,
            static_cast<int>(i),
            session.records,
            session.warnings);
    }
}

nlohmann::json WarningArrayForOccurrence(const std::vector<std::string>& warnings)
{
    nlohmann::json result = nlohmann::json::array();
    for (const std::string& warning : warnings)
        result.push_back(warning);
    return result;
}

nlohmann::json BuildOccurrenceInventoryPage(
    const OccurrenceInventorySession& session,
    std::size_t cursor)
{
    if (cursor > session.records.size())
        ThrowOccurrenceSessionInvalid("cursor is outside the inventory record range");
    if (cursor != 0 && (cursor % static_cast<std::size_t>(session.pageSize)) != 0)
        ThrowOccurrenceSessionInvalid("cursor does not align with the session page size");

    const std::size_t end = (std::min)(
        cursor + static_cast<std::size_t>(session.pageSize),
        session.records.size());

    nlohmann::json records = nlohmann::json::array();
    for (std::size_t i = cursor; i < end; ++i)
        records.push_back(session.records[i]);

    nlohmann::json data;
    data["schema_version"] = 1;
    data["inventory_session_id"] = session.inventorySessionId;
    data["source_document_key"] = session.sourceDocumentKey;
    data["inventory_context_fingerprint"] = session.inventoryContextFingerprint;
    data["records"] = std::move(records);
    data["next_cursor"] = end < session.records.size()
        ? nlohmann::json(std::to_string(end))
        : nlohmann::json(nullptr);
    data["complete"] = end >= session.records.size();
    data["warnings"] = cursor == 0
        ? WarningArrayForOccurrence(session.warnings)
        : nlohmann::json::array();
    return data;
}

void EraseOccurrenceInventorySession(const std::string& inventorySessionId)
{
    g_occurrenceInventorySessions.erase(inventorySessionId);
    g_occurrenceInventorySessionOrder.erase(
        std::remove(
            g_occurrenceInventorySessionOrder.begin(),
            g_occurrenceInventorySessionOrder.end(),
            inventorySessionId),
        g_occurrenceInventorySessionOrder.end());
}

bool EvictOldestOccurrenceInventorySession()
{
    while (!g_occurrenceInventorySessionOrder.empty())
    {
        const std::string oldestSessionId = g_occurrenceInventorySessionOrder.front();
        g_occurrenceInventorySessionOrder.pop_front();
        if (g_occurrenceInventorySessions.erase(oldestSessionId) > 0)
            return true;
    }

    return false;
}

void RecordOccurrenceInventorySession(OccurrenceInventorySession&& session)
{
    const std::string inventorySessionId = session.inventorySessionId;
    EraseOccurrenceInventorySession(inventorySessionId);
    while (g_occurrenceInventorySessions.size() >= kMaxDirectorOccurrenceInventorySessions)
    {
        if (!EvictOldestOccurrenceInventorySession())
            throw std::runtime_error("Could not allocate occurrence inventory session cache slot");
    }

    g_occurrenceInventorySessionOrder.push_back(inventorySessionId);
    g_occurrenceInventorySessions[inventorySessionId] = std::move(session);
}

void ValidateOccurrenceSessionStillCurrent(
    CRhinoDoc* pDoc,
    const OccurrenceInventorySession& session)
{
    if (pDoc->RuntimeSerialNumber() != session.documentRuntimeSerial ||
        DocumentContextKeyForOccurrence(pDoc) != session.documentContextKey)
    {
        throw DirectorFrameValidationError("inventory_stale", "inventory document context changed");
    }

    for (std::size_t i = 0; i < session.sourceObjectUuids.size(); ++i)
    {
        const CRhinoObject* obj = pDoc->LookupObject(session.sourceObjectUuids[i]);
        if (!obj || obj->IsDeleted())
        {
            throw DirectorFrameValidationError(
                "inventory_stale",
                "inventory source object no longer resolves: " + session.sourceObjectIds[i]);
        }
    }
}

nlohmann::json StartOccurrenceInventory(
    CRhinoDoc* pDoc,
    const OccurrenceInventoryRequest& request)
{
    OccurrenceInventorySession session;
    session.documentRuntimeSerial = pDoc->RuntimeSerialNumber();
    session.inventorySessionId = MakeOccurrenceInventorySessionId(session.documentRuntimeSerial);
    session.sourceDocumentKey = SourceDocumentKeyForOccurrence(pDoc);
    session.documentContextKey = DocumentContextKeyForOccurrence(pDoc);
    session.traversalOrdering = kDirectorOccurrenceTraversalOrdering;
    session.traversalOrderingVersion = kDirectorOccurrenceTraversalOrderingVersion;
    session.pageSize = request.pageSize;
    session.sourceObjectUuids = request.sourceObjectUuids;
    session.sourceObjectIds = request.sourceObjectIds;
    session.inventoryContextFingerprint = InventoryContextFingerprintForOccurrence(pDoc);

    PopulateOccurrenceInventorySession(pDoc, session);

    nlohmann::json firstPage = BuildOccurrenceInventoryPage(session, 0);

    if (firstPage.value("complete", false))
        return firstPage;

    {
        std::lock_guard<std::mutex> lock(g_occurrenceInventoryMutex);
        RecordOccurrenceInventorySession(std::move(session));
    }

    return firstPage;
}

nlohmann::json ContinueOccurrenceInventory(
    CRhinoDoc* pDoc,
    const OccurrenceInventoryRequest& request)
{
    std::lock_guard<std::mutex> lock(g_occurrenceInventoryMutex);
    auto it = g_occurrenceInventorySessions.find(request.inventorySessionId);
    if (it == g_occurrenceInventorySessions.end())
        ThrowOccurrenceSessionInvalid("inventory_session_id does not match an active inventory session");

    const OccurrenceInventorySession& session = it->second;
    if (request.pageSize != session.pageSize)
        ThrowOccurrenceSessionInvalid("page_size must match the inventory session page size");
    if (session.traversalOrdering != kDirectorOccurrenceTraversalOrdering ||
        session.traversalOrderingVersion != kDirectorOccurrenceTraversalOrderingVersion)
    {
        ThrowOccurrenceSessionInvalid("inventory session traversal ordering is inconsistent");
    }

    ValidateOccurrenceSessionStillCurrent(pDoc, session);
    nlohmann::json page = BuildOccurrenceInventoryPage(session, request.cursor);
    if (page.value("complete", false))
        EraseOccurrenceInventorySession(request.inventorySessionId);
    return page;
}

nlohmann::json ExecuteOccurrenceInventory(
    CRhinoDoc* pDoc,
    const OccurrenceInventoryRequest& request)
{
    return request.continuation
        ? ContinueOccurrenceInventory(pDoc, request)
        : StartOccurrenceInventory(pDoc, request);
}

} // namespace

void HandleDirectorOccurrenceInventory(const httplib::Request& req, httplib::Response& res)
{
    try
    {
        auto [docSn, body] = ParseBodyAndDocSn(req);
        OccurrenceInventoryRequest request = ParseOccurrenceInventoryRequest(body);

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [docSn, request]() -> nlohmann::json
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);
            return ExecuteOccurrenceInventory(pDoc, request);
        });

        CRookServer::SendSuccess(res, future.get());
    }
    catch (const DirectorFrameValidationError& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData(ex.code, ex.what()));
    }
    catch (const nlohmann::json::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("inventory_session_invalid", ex.what()));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("inventory_session_invalid", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("director_read_failed", ex.what()));
    }
}

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
                ValidateSlice1ModelRhinoView(pView);
                vp = pView->ActiveViewport().VP();
                resolvedName = WideToUtf8(pView->ActiveViewport().Name());
            }
            else
            {
                const ON_3dmView* pNamedView = FindNamedView(pDoc, name);
                if (!pNamedView)
                    throw std::invalid_argument("Named view not found: " + name);
                ValidateSlice1NamedView(*pNamedView, name);
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
    catch (const DirectorFrameValidationError& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData(ex.code, ex.what()));
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

void HandleDirectorCurveSamples(const httplib::Request& req, httplib::Response& res)
{
    try
    {
        auto [docSn, body] = ParseBodyAndDocSn(req);
        CurveSampleRequest request = ParseCurveSampleRequest(body);

        auto future = CMainThreadDispatcher::Instance().Dispatch(
            [docSn, request]() -> nlohmann::json
        {
            CRhinoDoc* pDoc = ResolveDoc(docSn);
            return SampleDirectorCurve(pDoc, request);
        });

        CRookServer::SendSuccess(res, future.get());
    }
    catch (const DirectorFrameValidationError& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData(ex.code, ex.what()));
    }
    catch (const nlohmann::json::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
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

void HandleDirectorVideoAssemble(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body = nlohmann::json::object();

    try
    {
        auto parsed = ParseBodyAndDocSn(req);
        body = std::move(parsed.second);

        VideoAssembleRequest request = ParseVideoAssembleRequest(body);
        ValidateVideoAssemblyPolicy(request);

        VideoBackendResult backend = EncodeMp4WithMediaFoundation(request);
        nlohmann::json evidence;
        evidence["backend"] = "media_foundation";
        evidence["codec"] = "h264";
        evidence["container"] = "mp4";
        evidence["width"] = request.width;
        evidence["height"] = request.height;
        evidence["frame_count"] = request.frameCount;
        evidence["fps"] = request.fps;
        evidence["input_pattern"] = request.inputPattern;
        if (backend.alphaComposited)
        {
            evidence["alpha_composited"] = true;
            evidence["alpha_background"] = "#000000";
        }

        nlohmann::json data;
        data["success"] = true;
        data["backend"] = "media_foundation";
        data["platform"] = "windows";
        data["output_path"] = PathToUtf8(request.outputPath);
        data["bytes"] = backend.bytes;
        data["overwrote_existing"] = backend.overwroteExisting;
        data["evidence"] = std::move(evidence);
        CRookServer::SendSuccess(res, data);
    }
    catch (const DirectorFrameValidationError& ex)
    {
        CRookServer::SendErrorData(res, MakeVideoErrorData(body, ex.code, ex.what()));
    }
    catch (const nlohmann::json::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeVideoErrorData(body, "invalid_input", ex.what()));
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, MakeVideoErrorData(body, "invalid_input", ex.what()));
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, MakeVideoErrorData(body, "director_video_failed", ex.what()));
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
            return ExecuteFrameTransaction(pDoc, instruction);
        });

        nlohmann::json data = future.get();
        if (data.value("success", false))
            CRookServer::SendSuccess(res, data);
        else
            CRookServer::SendErrorData(res, data);
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
