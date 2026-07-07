// DirectorWorkerPlayHandler.cpp - Director v3 Slice 3 worker playback.
//
// POST /director/worker-play: read a file-backed absolute track from a
// disposable prepared take document, prove the active document is at the
// requested source pose, then apply forward deltas without replay-session
// state, HTTP body caps, dwell pacing, or replay parser fallback.

#include "stdafx.h"
#include "Handlers/DirectorWorkerPlayHandler.h"
#include "Handlers/DirectorFrame.h"
#include "Threading/MainThreadDispatcher.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "RookServer.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace Rook {
namespace Handlers {

namespace {

constexpr int kMaxProbeFrames = 32;

std::string NormalizePathForCompare(std::string s)
{
    for (char& c : s)
    {
        if (c == '\\') c = '/';
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return s;
}

WriteResult FailureResult(const char* reason, nlohmann::json evidence = nlohmann::json::object())
{
    WriteResult wr;
    wr.success = false;
    wr.data = std::move(evidence);
    wr.data["reason"] = reason;
    return wr;
}

nlohmann::json TrackInvalidData(nlohmann::json evidence = nlohmann::json::object())
{
    evidence["reason"] = "track_invalid";
    return evidence;
}

nlohmann::json InvalidInputData(nlohmann::json evidence = nlohmann::json::object())
{
    evidence["reason"] = "invalid_input";
    return evidence;
}

// Capture-mode failures must always carry a sanctioned taxonomy reason; helper
// throws from shared code (e.g. DirectorViewportGuard's unsupported_view) map to
// capture_failed rather than escaping as untyped SendError.
std::string SanctionedCaptureReason(const DirectorFrameValidationError& ex)
{
    static const std::set<std::string> kSanctionedCaptureReasons = {
        "invalid_input", "output_policy_violation", "run_root_exists",
        "display_mode_missing", "display_mode_mismatch", "capture_failed",
    };
    if (kSanctionedCaptureReasons.count(ex.code))
        return ex.code;
    return "capture_failed";
}

std::string PathToUtf8(const fs::path& path)
{
    ON_wString wide(path.native().c_str());
    return WideToUtf8(wide);
}

fs::path PathFromUtf8(const std::string& value)
{
    ON_wString wide = Utf8ToWide(value);
    return fs::path(static_cast<const wchar_t*>(wide));
}

bool IsFiniteNumber(const nlohmann::json& value)
{
    if (!value.is_number()) return false;
    const double d = value.get<double>();
    return std::isfinite(d);
}

ON_Xform ParseXform(const nlohmann::json& m)
{
    if (!m.is_array() || m.size() != 4)
        throw std::invalid_argument("transform must be a 4x4 numeric matrix");

    ON_Xform xf = ON_Xform::IdentityTransformation;
    for (size_t row = 0; row < 4; ++row)
    {
        const auto& rowValue = m[row];
        if (!rowValue.is_array() || rowValue.size() != 4)
            throw std::invalid_argument("transform must be a 4x4 numeric matrix");
        for (size_t col = 0; col < 4; ++col)
        {
            if (!IsFiniteNumber(rowValue[col]))
                throw std::invalid_argument("transform must contain finite numbers only");
            xf.m_xform[row][col] = rowValue[col].get<double>();
        }
    }
    return xf;
}

ON_3dPoint ParsePoint3(const nlohmann::json& value, const std::string& field)
{
    if (!value.is_array() || value.size() != 3)
        throw std::invalid_argument(field + " must be a 3-number array");
    for (size_t i = 0; i < 3; ++i)
    {
        if (!IsFiniteNumber(value[i]))
            throw std::invalid_argument(field + " must be a 3-number array");
    }
    return ON_3dPoint(value[0].get<double>(), value[1].get<double>(), value[2].get<double>());
}

ON_BoundingBox BboxFromMinMax(const nlohmann::json& mn, const nlohmann::json& mx)
{
    ON_BoundingBox bbox(ParsePoint3(mn, "bbox_min"), ParsePoint3(mx, "bbox_max"));
    if (!bbox.IsValid())
        throw std::invalid_argument("source_state bbox is invalid");
    return bbox;
}

nlohmann::json PointToJson(const ON_3dPoint& point)
{
    return nlohmann::json::array({ point.x, point.y, point.z });
}

nlohmann::json BboxToJson(const ON_BoundingBox& bbox)
{
    return {
        {"min", PointToJson(bbox.Min())},
        {"max", PointToJson(bbox.Max())}
    };
}

ON_BoundingBox EnvelopeOfTransformedBbox(const ON_BoundingBox& src, const ON_Xform& xf)
{
    ON_BoundingBox envelope = ON_BoundingBox::EmptyBoundingBox;
    const ON_3dPoint mn = src.Min();
    const ON_3dPoint mx = src.Max();
    const ON_3dPoint corners[8] = {
        ON_3dPoint(mn.x, mn.y, mn.z),
        ON_3dPoint(mx.x, mn.y, mn.z),
        ON_3dPoint(mn.x, mx.y, mn.z),
        ON_3dPoint(mx.x, mx.y, mn.z),
        ON_3dPoint(mn.x, mn.y, mx.z),
        ON_3dPoint(mx.x, mn.y, mx.z),
        ON_3dPoint(mn.x, mx.y, mx.z),
        ON_3dPoint(mx.x, mx.y, mx.z)
    };

    for (const ON_3dPoint& corner : corners)
    {
        const ON_3dPoint transformed = xf * corner;
        envelope.Union(ON_BoundingBox(transformed, transformed));
    }
    return envelope;
}

ON_BoundingBox InflateBbox(ON_BoundingBox bbox, double tolerance)
{
    bbox.m_min.x -= tolerance;
    bbox.m_min.y -= tolerance;
    bbox.m_min.z -= tolerance;
    bbox.m_max.x += tolerance;
    bbox.m_max.y += tolerance;
    bbox.m_max.z += tolerance;
    return bbox;
}

bool WorkerBboxAlmostEqual(const ON_BoundingBox& a, const ON_BoundingBox& b, double tolerance)
{
    return std::fabs(a.m_min.x - b.m_min.x) <= tolerance &&
        std::fabs(a.m_min.y - b.m_min.y) <= tolerance &&
        std::fabs(a.m_min.z - b.m_min.z) <= tolerance &&
        std::fabs(a.m_max.x - b.m_max.x) <= tolerance &&
        std::fabs(a.m_max.y - b.m_max.y) <= tolerance &&
        std::fabs(a.m_max.z - b.m_max.z) <= tolerance;
}

bool BboxContains(const ON_BoundingBox& outer, const ON_BoundingBox& inner)
{
    return inner.m_min.x >= outer.m_min.x &&
        inner.m_min.y >= outer.m_min.y &&
        inner.m_min.z >= outer.m_min.z &&
        inner.m_max.x <= outer.m_max.x &&
        inner.m_max.y <= outer.m_max.y &&
        inner.m_max.z <= outer.m_max.z;
}

double BboxDiagonal(const ON_BoundingBox& bbox)
{
    const double dx = bbox.m_max.x - bbox.m_min.x;
    const double dy = bbox.m_max.y - bbox.m_min.y;
    const double dz = bbox.m_max.z - bbox.m_min.z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

double CentroidOffset(const ON_BoundingBox& a, const ON_BoundingBox& b)
{
    const ON_3dPoint ac = a.Center();
    const ON_3dPoint bc = b.Center();
    const double dx = ac.x - bc.x;
    const double dy = ac.y - bc.y;
    const double dz = ac.z - bc.z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

bool TryGetTightBbox(const CRhinoObject* obj, ON_BoundingBox& bbox)
{
    return obj && !obj->IsDeleted() && obj->GetTightBoundingBox(bbox) && bbox.IsValid();
}

struct ObjectTrack
{
    std::string id;
    ON_UUID uuid = ON_nil_uuid;
    ON_BoundingBox sourceBbox = ON_BoundingBox::EmptyBoundingBox;
    std::vector<ON_Xform> absoluteByFrame;
};

struct WorkerTrack
{
    int frameCount = 0;
    std::vector<std::string> objectIds;
    std::map<std::string, ObjectTrack> objects;
    std::vector<FrameCamera> cameraFrames;
};

struct PlayRequest
{
    std::string expectedDocumentPath;
    std::string trackPath;
    int fromFrame = 0;
    int playTo = -1;
    bool playToDefaulted = true;
    std::set<int> probeFrames;
    double driftTolerance = -1.0;
};

struct CaptureRequest
{
    bool present = false;
    fs::path runRoot;
    fs::path framesDir;
    std::string displayMode;
    int width = 0;
    int height = 0;
};

constexpr int kMaxCaptureDim = 8192;

void ValidateStringField(const nlohmann::json& body, const char* field, std::string& out)
{
    if (!body.contains(field) || !body[field].is_string())
        throw std::invalid_argument(std::string("Missing or invalid field: ") + field);
    out = body[field].get<std::string>();
    if (out.empty())
        throw std::invalid_argument(std::string("Missing or invalid field: ") + field);
}

int ParseOptionalInt(const nlohmann::json& body, const char* field, int defaultValue)
{
    if (!body.contains(field) || body[field].is_null())
        return defaultValue;
    if (!body[field].is_number_integer())
        throw std::invalid_argument(std::string(field) + " must be an integer");
    return body[field].get<int>();
}

PlayRequest ParsePlayRequest(const nlohmann::json& body)
{
    PlayRequest request;
    ValidateStringField(body, "expectedDocumentPath", request.expectedDocumentPath);
    ValidateStringField(body, "trackPath", request.trackPath);

    request.fromFrame = ParseOptionalInt(body, "fromFrame", 0);
    if (body.contains("playTo") && !body["playTo"].is_null())
    {
        if (!body["playTo"].is_number_integer())
            throw std::invalid_argument("playTo must be an integer");
        request.playTo = body["playTo"].get<int>();
        request.playToDefaulted = false;
    }

    if (body.contains("probeFrames") && !body["probeFrames"].is_null())
    {
        if (!body["probeFrames"].is_array())
            throw std::invalid_argument("probeFrames must be an array of integers");
        if (body["probeFrames"].size() > static_cast<size_t>(kMaxProbeFrames))
            throw std::invalid_argument("probeFrames exceeds maximum of 32");
        for (const auto& item : body["probeFrames"])
        {
            if (!item.is_number_integer())
                throw std::invalid_argument("probeFrames must be an array of integers");
            request.probeFrames.insert(item.get<int>());
        }
    }

    if (body.contains("driftTolerance") && !body["driftTolerance"].is_null())
    {
        if (!IsFiniteNumber(body["driftTolerance"]))
            throw std::invalid_argument("driftTolerance must be a positive finite number");
        request.driftTolerance = body["driftTolerance"].get<double>();
        if (request.driftTolerance <= 0.0)
            throw std::invalid_argument("driftTolerance must be a positive finite number");
    }

    return request;
}

CaptureRequest ParseCaptureBlock(const nlohmann::json& body)
{
    CaptureRequest capture;
    if (!body.contains("capture") || body["capture"].is_null())
        return capture;

    const nlohmann::json& block = body["capture"];
    if (!block.is_object())
        throw std::invalid_argument("capture must be an object");

    static const std::set<std::string> kAllowed =
        { "runRoot", "framesDir", "displayMode", "width", "height" };
    for (const auto& item : block.items())
    {
        if (!kAllowed.count(item.key()))
            throw std::invalid_argument("capture has unknown field: " + item.key());
    }

    std::string runRoot;
    std::string framesDir;
    ValidateStringField(block, "runRoot", runRoot);
    ValidateStringField(block, "framesDir", framesDir);
    ValidateStringField(block, "displayMode", capture.displayMode);
    if (IEquals(capture.displayMode, "current"))
        throw std::invalid_argument("capture.displayMode must name a concrete mode, not 'current'");
    if (!block.contains("width") || !block["width"].is_number_integer() ||
        !block.contains("height") || !block["height"].is_number_integer())
        throw std::invalid_argument("capture.width and capture.height must be integers");

    capture.width = block["width"].get<int>();
    capture.height = block["height"].get<int>();
    if (capture.width <= 0 || capture.height <= 0 ||
        (capture.width % 2) != 0 || (capture.height % 2) != 0 ||
        capture.width > kMaxCaptureDim || capture.height > kMaxCaptureDim)
        throw std::invalid_argument("capture.width and capture.height must be positive even integers <= 8192");

    capture.runRoot = NormalizePolicyPath(PathFromUtf8(runRoot));
    capture.framesDir = NormalizePolicyPath(PathFromUtf8(framesDir));
    capture.present = true;
    return capture;
}

WorkerTrack ParseWorkerTrack(const nlohmann::json& track)
{
    WorkerTrack parsed;
    if (!track.is_object())
        throw std::invalid_argument("track must be an object");
    if (!track.contains("transform_semantics") || !track["transform_semantics"].is_string() ||
        track["transform_semantics"].get<std::string>() != "absolute_from_source")
        throw std::invalid_argument("transform_semantics must be absolute_from_source");
    if (!track.contains("frame_count") || !track["frame_count"].is_number_integer())
        throw std::invalid_argument("frame_count must be an integer");
    parsed.frameCount = track["frame_count"].get<int>();
    if (parsed.frameCount < 1)
        throw std::invalid_argument("frame_count must be at least 1");
    if (!track.contains("animated_object_ids") || !track["animated_object_ids"].is_array())
        throw std::invalid_argument("animated_object_ids must be an array");
    if (!track.contains("object_frames") || !track["object_frames"].is_array() ||
        track["object_frames"].size() != static_cast<size_t>(parsed.frameCount))
        throw std::invalid_argument("object_frames length must equal frame_count");

    std::set<std::string> expectedIds;
    for (const auto& item : track["animated_object_ids"])
    {
        if (!item.is_string())
            throw std::invalid_argument("animated_object_ids entries must be strings");
        const std::string id = item.get<std::string>();
        const ON_UUID uuid = ON_UuidFromString(id.c_str());
        if (id.empty() || ON_UuidIsNil(uuid))
            throw std::invalid_argument("animated_object_ids entries must be valid UUID strings");
        if (!expectedIds.insert(id).second)
            throw std::invalid_argument("animated_object_ids contains duplicates");

        ObjectTrack object;
        object.id = id;
        object.uuid = uuid;
        object.absoluteByFrame.assign(static_cast<size_t>(parsed.frameCount + 1), ON_Xform::IdentityTransformation);
        parsed.objectIds.push_back(id);
        parsed.objects.emplace(id, std::move(object));
    }
    if (parsed.objectIds.empty())
        throw std::invalid_argument("animated_object_ids must not be empty");

    std::set<std::string> sourceBboxSeen;
    for (int frameIndex = 1; frameIndex <= parsed.frameCount; ++frameIndex)
    {
        const auto& frame = track["object_frames"][static_cast<size_t>(frameIndex - 1)];
        if (!frame.is_object())
            throw std::invalid_argument("object_frames entries must be objects");
        if (!frame.contains("frame_index") || !frame["frame_index"].is_number_integer() ||
            frame["frame_index"].get<int>() != frameIndex)
            throw std::invalid_argument("object_frames frame_index values must be ordered and 1-based");
        if (!frame.contains("object_transforms") || !frame["object_transforms"].is_array())
            throw std::invalid_argument("object_transforms must be an array");

        std::set<std::string> frameIds;
        for (const auto& entry : frame["object_transforms"])
        {
            if (!entry.is_object())
                throw std::invalid_argument("object_transforms entries must be objects");
            if (!entry.contains("object_id") || !entry["object_id"].is_string())
                throw std::invalid_argument("object_transforms[].object_id is required");
            const std::string id = entry["object_id"].get<std::string>();
            auto objectIt = parsed.objects.find(id);
            if (objectIt == parsed.objects.end())
                throw std::invalid_argument("object_transforms object_id is not listed in animated_object_ids");
            if (!frameIds.insert(id).second)
                throw std::invalid_argument("object_transforms contains duplicate object_id in a frame");
            if (!entry.contains("transform"))
                throw std::invalid_argument("object_transforms[].transform is required");
            objectIt->second.absoluteByFrame[static_cast<size_t>(frameIndex)] = ParseXform(entry["transform"]);

            if (!entry.contains("source_state") || !entry["source_state"].is_object())
                throw std::invalid_argument("object_transforms[].source_state is required");
            const auto& sourceState = entry["source_state"];
            if (!sourceState.contains("validation_strength") || !sourceState["validation_strength"].is_string() ||
                sourceState["validation_strength"].get<std::string>() != "tight_bbox")
                throw std::invalid_argument("source_state.validation_strength must be tight_bbox");
            if (!sourceState.contains("bbox_min") || !sourceState.contains("bbox_max"))
                throw std::invalid_argument("source_state.bbox_min/bbox_max are required");

            const ON_BoundingBox sourceBbox = BboxFromMinMax(sourceState["bbox_min"], sourceState["bbox_max"]);
            if (!sourceBboxSeen.count(id))
            {
                objectIt->second.sourceBbox = sourceBbox;
                sourceBboxSeen.insert(id);
            }
            else if (!WorkerBboxAlmostEqual(objectIt->second.sourceBbox, sourceBbox, 0.0))
            {
                throw std::invalid_argument("source_state bbox must be stable across frames");
            }
        }

        if (frameIds != expectedIds)
            throw std::invalid_argument("per-frame object id set must equal animated_object_ids");
    }

    return parsed;
}

std::vector<FrameCamera> ParseCameraFrames(const nlohmann::json& trackJson, int frameCount)
{
    if (!trackJson.contains("camera_frames") || !trackJson["camera_frames"].is_array())
        throw std::invalid_argument("capture requires track camera_frames array");

    const auto& entries = trackJson["camera_frames"];
    if (static_cast<int>(entries.size()) != frameCount)
        throw std::invalid_argument("camera_frames length must equal frame_count");

    std::vector<FrameCamera> cameras;
    cameras.reserve(entries.size());
    for (int i = 0; i < static_cast<int>(entries.size()); ++i)
    {
        const auto& entry = entries[static_cast<size_t>(i)];
        if (!entry.is_object() || !entry.contains("frame_index") ||
            !entry["frame_index"].is_number_integer() ||
            entry["frame_index"].get<int>() != i + 1)
        {
            throw std::invalid_argument(
                "camera_frames must be 1-based and contiguous (bad entry at position "
                + std::to_string(i) + ")");
        }

        try
        {
            cameras.push_back(ParseCamera(entry));
        }
        catch (const DirectorFrameValidationError& ex)
        {
            throw std::invalid_argument(std::string("camera_frames[") + std::to_string(i)
                + "]: " + ex.what());
        }
    }
    return cameras;
}

nlohmann::json LoadTrackJson(const std::string& trackPath)
{
    std::ifstream input(trackPath);
    if (!input.is_open())
        throw std::invalid_argument("track file could not be opened");

    try
    {
        nlohmann::json track = nlohmann::json::parse(input);
        if (!input.good() && !input.eof())
            throw std::invalid_argument("track file could not be read");
        return track;
    }
    catch (const nlohmann::json::exception& ex)
    {
        throw std::invalid_argument(std::string("track JSON parse failed: ") + ex.what());
    }
}

void ValidateFrameRange(const PlayRequest& request, int frameCount)
{
    if (request.fromFrame < 0 || request.playTo < 0 ||
        request.fromFrame >= request.playTo || request.playTo > frameCount)
        throw std::invalid_argument("frame range must satisfy 0 <= fromFrame < playTo <= frame_count");
    for (int probeFrame : request.probeFrames)
    {
        if (probeFrame <= request.fromFrame || probeFrame > request.playTo)
            throw std::invalid_argument("probeFrames must be within (fromFrame, playTo]");
    }
}

nlohmann::json MissingIdsJson(const std::vector<std::string>& ids)
{
    nlohmann::json arr = nlohmann::json::array();
    for (const std::string& id : ids)
        arr.push_back(id);
    return arr;
}

nlohmann::json MakePristineEvidence(
    const std::string& objectId,
    const ON_BoundingBox& observed,
    const ON_BoundingBox& expected,
    double centroidOffset)
{
    return {
        {"objectId", objectId},
        {"observed", BboxToJson(observed)},
        {"expected", BboxToJson(expected)},
        {"centroidOffset", centroidOffset}
    };
}

nlohmann::json MakeProbeObjectEvidence(const std::string& objectId, const ON_BoundingBox& bbox)
{
    return {
        {"objectId", objectId},
        {"bboxMin", PointToJson(bbox.Min())},
        {"bboxMax", PointToJson(bbox.Max())}
    };
}

} // namespace

void HandleDirectorWorkerPlay(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    PlayRequest playRequest;
    try
    {
        playRequest = ParsePlayRequest(body);
    }
    catch (const std::invalid_argument& ex)
    {
        const std::string message = ex.what();
        if (message.find("expectedDocumentPath") != std::string::npos ||
            message.find("trackPath") != std::string::npos)
        {
            CRookServer::SendError(res, message);
            return;
        }
        CRookServer::SendErrorData(res, TrackInvalidData({
            {"check", "request_parameters"},
            {"message", message}
        }));
        return;
    }

    CaptureRequest captureRequest;
    try
    {
        captureRequest = ParseCaptureBlock(body);
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, InvalidInputData({ { "message", ex.what() } }));
        return;
    }

    WorkerTrack track;
    nlohmann::json trackJson;
    try
    {
        trackJson = LoadTrackJson(playRequest.trackPath);
        track = ParseWorkerTrack(trackJson);
        if (playRequest.playToDefaulted)
            playRequest.playTo = track.frameCount;
        ValidateFrameRange(playRequest, track.frameCount);
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, TrackInvalidData({
            {"check", "track_or_frame_range"},
            {"message", ex.what()}
        }));
        return;
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendErrorData(res, TrackInvalidData({
            {"check", "track_or_frame_range"},
            {"message", ex.what()}
        }));
        return;
    }

    if (captureRequest.present &&
        (playRequest.fromFrame != 0 || playRequest.playTo != track.frameCount))
    {
        CRookServer::SendErrorData(res, InvalidInputData({
            { "message", "capture requires a full-range play: fromFrame 0 and playTo == frame_count" },
            { "fromFrame", playRequest.fromFrame },
            { "playTo", playRequest.playTo },
            { "frameCount", track.frameCount }
        }));
        return;
    }

    if (captureRequest.present)
    {
        try
        {
            track.cameraFrames = ParseCameraFrames(trackJson, track.frameCount);
        }
        catch (const std::invalid_argument& ex)
        {
            CRookServer::SendErrorData(res, TrackInvalidData({
                { "check", "camera_frames" },
                { "message", ex.what() }
            }));
            return;
        }
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, playRequest, track, captureRequest]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        const std::string docPath = WideToUtf8(pDoc->GetPathName());
        if (NormalizePathForCompare(docPath) != NormalizePathForCompare(playRequest.expectedDocumentPath))
        {
            return FailureResult("wrong_document", {
                {"expectedDocumentPath", playRequest.expectedDocumentPath},
                {"actualDocumentPath", docPath}
            });
        }

        std::map<std::string, const CRhinoObject*> objects;
        std::vector<std::string> missingIds;
        for (const std::string& objectId : track.objectIds)
        {
            const auto& objectTrack = track.objects.at(objectId);
            const CRhinoObject* obj = pDoc->LookupObject(objectTrack.uuid);
            if (!obj || obj->IsDeleted())
            {
                missingIds.push_back(objectId);
                continue;
            }
            objects[objectId] = obj;
        }
        if (!missingIds.empty())
            return FailureResult("track_objects_missing", {{"missingIds", MissingIdsJson(missingIds)}});

        ON_UUID captureModeId = ON_nil_uuid;
        std::unique_ptr<DirectorViewportGuard> viewportGuard;
        CRhinoView* captureView = nullptr;
        if (captureRequest.present)
        {
            try
            {
                const fs::path allowedRoot = GetAllowedDirectorRoot();
                if (!IsSameOrDescendantPath(allowedRoot, captureRequest.runRoot))
                    return FailureResult("output_policy_violation",
                        { { "message", "capture.runRoot must be inside the director output root" } });
                if (!IsSamePath(captureRequest.runRoot / L"frames", captureRequest.framesDir))
                    return FailureResult("output_policy_violation",
                        { { "message", "capture.framesDir must be exactly runRoot/frames" } });

                std::error_code ec;
                if (fs::exists(captureRequest.runRoot, ec))
                    return FailureResult("run_root_exists",
                        { { "runRoot", PathToUtf8(captureRequest.runRoot) } });
                fs::create_directories(captureRequest.framesDir, ec);
                if (ec)
                {
                    return FailureResult("capture_failed",
                        { { "message", "failed to create frames directory: " + ec.message() } });
                }

                try
                {
                    captureModeId = ResolveDisplayModeId(captureRequest.displayMode);
                }
                catch (const DirectorFrameValidationError& ex)
                {
                    return FailureResult("display_mode_missing", { { "message", ex.what() } });
                }

                viewportGuard = std::make_unique<DirectorViewportGuard>(pDoc);
                captureView = viewportGuard->View();
                if (!captureView)
                    return FailureResult("capture_failed", { { "message", "no active view for capture" } });

                captureView->ActiveViewport().SetDisplayMode(captureModeId);
                captureView->Redraw();
                const ON_UUID initialApplied = CurrentDisplayModeId(captureView);
                if (ON_UuidCompare(initialApplied, captureModeId) != 0)
                {
                    return FailureResult("display_mode_mismatch",
                        { { "requested", DisplayModeToJson(captureModeId) },
                          { "applied", DisplayModeToJson(initialApplied) } });
                }
            }
            catch (const DirectorFrameValidationError& ex)
            {
                const std::string reason = SanctionedCaptureReason(ex);
                return FailureResult(reason.c_str(),
                    { { "message", ex.what() }, { "sourceCode", ex.code } });
            }
            catch (const std::exception& ex)
            {
                return FailureResult("capture_failed", { { "message", ex.what() } });
            }
        }

        const double tolerance = playRequest.driftTolerance > 0.0
            ? playRequest.driftTolerance
            : 10.0 * pDoc->AbsoluteTolerance();

        nlohmann::json pristineOffenders = nlohmann::json::array();
        for (const std::string& objectId : track.objectIds)
        {
            const ObjectTrack& objectTrack = track.objects.at(objectId);
            ON_BoundingBox observed;
            if (!TryGetTightBbox(objects[objectId], observed))
            {
                pristineOffenders.push_back({
                    {"objectId", objectId},
                    {"reason", "tight_bbox_unavailable"}
                });
                continue;
            }

            if (playRequest.fromFrame == 0)
            {
                if (!WorkerBboxAlmostEqual(observed, objectTrack.sourceBbox, tolerance))
                {
                    pristineOffenders.push_back(
                        MakePristineEvidence(objectId, observed, objectTrack.sourceBbox,
                                             CentroidOffset(observed, objectTrack.sourceBbox)));
                }
            }
            else
            {
                const ON_BoundingBox expectedEnvelope = InflateBbox(
                    EnvelopeOfTransformedBbox(objectTrack.sourceBbox,
                                              objectTrack.absoluteByFrame[static_cast<size_t>(playRequest.fromFrame)]),
                    tolerance);
                if (!BboxContains(expectedEnvelope, observed))
                {
                    pristineOffenders.push_back(
                        MakePristineEvidence(objectId, observed, expectedEnvelope,
                                             CentroidOffset(observed, expectedEnvelope)));
                }
            }
        }
        if (!pristineOffenders.empty())
        {
            return FailureResult("worker_scene_not_pristine", {
                {"tolerance", tolerance},
                {"objects", std::move(pristineOffenders)}
            });
        }

        std::map<std::string, ON_Xform> prev;
        for (const std::string& objectId : track.objectIds)
        {
            prev[objectId] = playRequest.fromFrame == 0
                ? ON_Xform::IdentityTransformation
                : track.objects.at(objectId).absoluteByFrame[static_cast<size_t>(playRequest.fromFrame)];
        }

        UndoScope undo(pDoc, L"Director worker play");
        const auto totalStart = std::chrono::steady_clock::now();
        std::vector<double> perFrameMs;
        perFrameMs.reserve(static_cast<size_t>(playRequest.playTo - playRequest.fromFrame));
        std::vector<double> capturePerFrameMs;
        std::string captureBackend;
        int framesWritten = 0;
        if (captureRequest.present)
            capturePerFrameMs.reserve(static_cast<size_t>(playRequest.playTo));
        nlohmann::json probes = nlohmann::json::array();

        for (int frameIndex = playRequest.fromFrame + 1; frameIndex <= playRequest.playTo; ++frameIndex)
        {
            const auto frameStart = std::chrono::steady_clock::now();
            for (const std::string& objectId : track.objectIds)
            {
                ON_Xform inv = prev[objectId];
                if (!inv.Invert())
                {
                    return FailureResult("track_invalid", {
                        {"message", "previous absolute transform is not invertible"},
                        {"frameIndex", frameIndex},
                        {"objectId", objectId}
                    });
                }
                const ON_Xform& absolute = track.objects.at(objectId).absoluteByFrame[static_cast<size_t>(frameIndex)];
                const ON_Xform delta = absolute * inv;
                CRhinoObjRef objRef(pDoc->RuntimeSerialNumber(), track.objects.at(objectId).uuid);
                if (!pDoc->TransformObject(objRef, delta, true, false, true))
                {
                    return FailureResult("track_invalid", {
                        {"message", "TransformObject failed"},
                        {"frameIndex", frameIndex},
                        {"objectId", objectId}
                    });
                }
                prev[objectId] = absolute;
            }

            if (captureRequest.present)
            {
                try
                {
                    const auto captureStart = std::chrono::steady_clock::now();
                    SetCameraFromFrame(captureView, track.cameraFrames[static_cast<size_t>(frameIndex - 1)]);
                    const ON_UUID appliedMode = CurrentDisplayModeId(captureView);
                    if (ON_UuidCompare(appliedMode, captureModeId) != 0)
                    {
                        return FailureResult("display_mode_mismatch",
                            { { "frameIndex", frameIndex },
                              { "requested", DisplayModeToJson(captureModeId) },
                              { "applied", DisplayModeToJson(appliedMode) } });
                    }
                    captureView->Redraw();

                    wchar_t frameName[32] = {};
                    swprintf_s(frameName, L"frame_%04d.png", frameIndex);
                    const fs::path framePath = captureRequest.framesDir / frameName;
                    const DirectorCaptureResult captureResult =
                        CaptureViewToPng(pDoc, captureView, captureRequest.width,
                                         captureRequest.height, framePath);
                    captureBackend = captureResult.backend;
                    ++framesWritten;
                    const auto captureEnd = std::chrono::steady_clock::now();
                    capturePerFrameMs.push_back(
                        std::chrono::duration<double, std::milli>(captureEnd - captureStart).count());
                }
                catch (const DirectorFrameValidationError& ex)
                {
                    const std::string reason = SanctionedCaptureReason(ex);
                    return FailureResult(reason.c_str(),
                        { { "frameIndex", frameIndex },
                          { "message", ex.what() }, { "sourceCode", ex.code } });
                }
                catch (const std::exception& ex)
                {
                    return FailureResult("capture_failed",
                        { { "frameIndex", frameIndex }, { "message", ex.what() } });
                }
            }

            const auto frameEnd = std::chrono::steady_clock::now();
            perFrameMs.push_back(
                std::chrono::duration<double, std::milli>(frameEnd - frameStart).count());

            if (playRequest.probeFrames.count(frameIndex))
            {
                nlohmann::json probeObjects = nlohmann::json::array();
                for (const std::string& objectId : track.objectIds)
                {
                    ON_BoundingBox observed;
                    if (!TryGetTightBbox(pDoc->LookupObject(track.objects.at(objectId).uuid), observed))
                    {
                        return FailureResult("track_invalid", {
                            {"message", "tight bbox unavailable during probe"},
                            {"frameIndex", frameIndex},
                            {"objectId", objectId}
                        });
                    }
                    probeObjects.push_back(MakeProbeObjectEvidence(objectId, observed));
                }
                probes.push_back({
                    {"frameIndex", frameIndex},
                    {"objects", std::move(probeObjects)}
                });
            }
        }

        nlohmann::json driftOffenders = nlohmann::json::array();
        double worstCentroidOffset = 0.0;
        double worstDiagonalRatio = 0.0;
        for (const std::string& objectId : track.objectIds)
        {
            const ObjectTrack& objectTrack = track.objects.at(objectId);
            ON_BoundingBox observed;
            if (!TryGetTightBbox(pDoc->LookupObject(objectTrack.uuid), observed))
            {
                driftOffenders.push_back({
                    {"objectId", objectId},
                    {"reason", "tight_bbox_unavailable"}
                });
                continue;
            }

            const ON_BoundingBox expectedEnvelope = InflateBbox(
                EnvelopeOfTransformedBbox(objectTrack.sourceBbox,
                                          objectTrack.absoluteByFrame[static_cast<size_t>(playRequest.playTo)]),
                tolerance);
            const double centroidOffset = CentroidOffset(observed, expectedEnvelope);
            const double envelopeDiagonal = BboxDiagonal(expectedEnvelope);
            const double observedDiagonal = BboxDiagonal(observed);
            const double diagonalRatio = envelopeDiagonal > std::numeric_limits<double>::epsilon()
                ? observedDiagonal / envelopeDiagonal
                : 0.0;
            if (centroidOffset > worstCentroidOffset)
                worstCentroidOffset = centroidOffset;
            if (diagonalRatio > worstDiagonalRatio)
                worstDiagonalRatio = diagonalRatio;

            if (!BboxContains(expectedEnvelope, observed))
            {
                driftOffenders.push_back({
                    {"objectId", objectId},
                    {"observed", BboxToJson(observed)},
                    {"expectedEnvelope", BboxToJson(expectedEnvelope)},
                    {"centroidOffset", centroidOffset},
                    {"diagonalRatio", diagonalRatio}
                });
            }
        }
        if (!driftOffenders.empty())
        {
            return FailureResult("playback_drift_detected", {
                {"tolerance", tolerance},
                {"objects", std::move(driftOffenders)}
            });
        }

        pDoc->Redraw();
        const auto totalEnd = std::chrono::steady_clock::now();
        nlohmann::json perFrame = nlohmann::json::array();
        for (double ms : perFrameMs)
            perFrame.push_back(ms);

        WriteResult wr;
        wr.success = true;
        wr.data["documentPath"] = docPath;
        wr.data["playedFrom"] = playRequest.fromFrame;
        wr.data["playedTo"] = playRequest.playTo;
        wr.data["frameCount"] = track.frameCount;
        wr.data["objectCount"] = static_cast<int>(track.objectIds.size());
        wr.data["probes"] = std::move(probes);
        wr.data["drift"] = {
            {"tolerance", tolerance},
            {"worstCentroidOffset", worstCentroidOffset},
            {"worstDiagonalRatio", worstDiagonalRatio}
        };
        wr.data["timing"] = {
            {"totalMs", std::chrono::duration<double, std::milli>(totalEnd - totalStart).count()},
            {"perFrameMs", std::move(perFrame)}
        };
        if (captureRequest.present)
        {
            double captureTotal = 0.0;
            nlohmann::json capturePerFrame = nlohmann::json::array();
            for (double ms : capturePerFrameMs)
            {
                captureTotal += ms;
                capturePerFrame.push_back(ms);
            }
            wr.data["capture"] = {
                { "backend", captureBackend },
                { "runRoot", PathToUtf8(captureRequest.runRoot) },
                { "framesDir", PathToUtf8(captureRequest.framesDir) },
                { "framesWritten", framesWritten },
                { "displayModeRequested", captureRequest.displayMode },
                { "displayModeResolved", DisplayModeToJson(captureModeId) },
                { "timing", {
                    { "captureTotalMs", captureTotal },
                    { "capturePerFrameMs", std::move(capturePerFrame) }
                } }
            };
        }
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

void HandleDirectorCaptureProbe(const httplib::Request& req, httplib::Response& res)
{
    auto [docSn, body] = ParseBodyAndDocSn(req);

    std::string displayMode;
    int width = 0, height = 0;
    std::string outputPathUtf8;
    try
    {
        ValidateStringField(body, "displayMode", displayMode);
        if (IEquals(displayMode, "current"))
            throw std::invalid_argument("displayMode must name a concrete mode, not 'current'");
        if (!body.contains("width") || !body["width"].is_number_integer() ||
            !body.contains("height") || !body["height"].is_number_integer())
            throw std::invalid_argument("width and height must be integers");
        width = body["width"].get<int>();
        height = body["height"].get<int>();
        if (width <= 0 || height <= 0 || (width % 2) != 0 || (height % 2) != 0 ||
            width > 8192 || height > 8192)
            throw std::invalid_argument("width and height must be positive even integers <= 8192");
        ValidateStringField(body, "outputPath", outputPathUtf8);
    }
    catch (const std::invalid_argument& ex)
    {
        CRookServer::SendErrorData(res, nlohmann::json{
            {"reason", "invalid_input"}, {"message", ex.what()}});
        return;
    }

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, displayMode, width, height, outputPathUtf8]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        try
        {
            ON_wString wideOutputPath = Utf8ToWide(outputPathUtf8);
            const fs::path outputPath = NormalizePolicyPath(fs::path(static_cast<const wchar_t*>(wideOutputPath)));
            const fs::path allowedRoot = GetAllowedDirectorRoot();
            if (!IsSameOrDescendantPath(allowedRoot, outputPath))
                return FailureResult("output_policy_violation",
                    {{"message", "outputPath must be inside the director output root"}});
            std::error_code ec;
            fs::create_directories(outputPath.parent_path(), ec);

            ON_UUID modeId;
            try { modeId = ResolveDisplayModeId(displayMode); }
            catch (const DirectorFrameValidationError& ex)
            {
                return FailureResult("display_mode_missing", {{"message", ex.what()}});
            }

            DirectorViewportGuard guard(pDoc);
            CRhinoView* pView = guard.View();
            if (!pView)
                return FailureResult("capture_failed", {{"message", "no active view"}});
            CRhinoViewport& vp = pView->ActiveViewport();
            vp.SetDisplayMode(modeId);
            pView->Redraw();
            const ON_UUID applied = CurrentDisplayModeId(pView);
            if (ON_UuidCompare(applied, modeId) != 0)
                return FailureResult("display_mode_mismatch",
                    {{"requested", DisplayModeToJson(modeId)},
                     {"applied", DisplayModeToJson(applied)}});

            nlohmann::json data;
            const DirectorCaptureResult capture =
                CaptureViewToPng(pDoc, pView, width, height, outputPath);
            data["backend"] = capture.backend;
            data["outputPath"] = outputPathUtf8;
            data["displayModeResolved"] = DisplayModeToJson(modeId);
            data["readbackMatches"] = true;
            WriteResult wr;
            wr.success = true;
            wr.data = std::move(data);
            return wr;
        }
        catch (const DirectorFrameValidationError& ex)
        {
            const std::string reason = SanctionedCaptureReason(ex);
            return FailureResult(reason.c_str(),
                {{"message", ex.what()}, {"sourceCode", ex.code}});
        }
        catch (const std::exception& ex)
        {
            return FailureResult("capture_failed", {{"message", ex.what()}});
        }
    });

    try
    {
        auto result = future.get();
        if (result.success) CRookServer::SendSuccess(res, result.data);
        else CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
