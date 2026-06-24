#include "stdafx.h"
#include "Handlers/DirectorReplayHandler.h"
#include "Handlers/DirectorFrame.h"
#include "Threading/MainThreadDispatcher.h"
#include "Infrastructure/JsonHelpers.h"
#include "Models/DocumentHelpers.h"
#include "RookServer.h"
#include <atomic>
#include <chrono>
#include <mutex>
#include <optional>
#include <set>
#include <vector>

namespace Rook { namespace Handlers {

namespace {

struct ReplaySlot {
    std::mutex mutex;
    bool active = false;
    std::string sessionId;
    std::atomic<bool> cancel{false};
};

ReplaySlot& Slot() { static ReplaySlot s; return s; }

bool IsValidReplaySessionId(const std::string& id) {
    if (id.empty() || id.size() > 128) return false;
    for (char c : id)
        if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '.' || c == '_' || c == '-'))
            return false;
    return true;
}

// Reserve under lock; returns false if a replay is already active.
bool ReserveReplaySlot(const std::string& sessionId) {
    auto& s = Slot();
    std::lock_guard<std::mutex> lk(s.mutex);
    if (s.active) return false;
    s.active = true;
    s.sessionId = sessionId;
    s.cancel.store(false, std::memory_order_release);
    return true;
}

void ReleaseReplaySlot() {
    auto& s = Slot();
    std::lock_guard<std::mutex> lk(s.mutex);
    s.active = false;
    s.sessionId.clear();
    s.cancel.store(false, std::memory_order_release);
}

struct ReplaySlotReservation {  // RAII release on every path — non-copyable/non-movable
    bool held = false;
    ReplaySlotReservation() = default;
    ~ReplaySlotReservation() { if (held) ReleaseReplaySlot(); }
    ReplaySlotReservation(const ReplaySlotReservation&) = delete;
    ReplaySlotReservation& operator=(const ReplaySlotReservation&) = delete;
    ReplaySlotReservation(ReplaySlotReservation&&) = delete;
    ReplaySlotReservation& operator=(ReplaySlotReservation&&) = delete;
};

// Helper: SendErrorData with a code + message.
static void SendCode(httplib::Response& res, const std::string& code, const std::string& message)
{
    nlohmann::json d;
    d["code"] = code;
    d["message"] = message;
    CRookServer::SendErrorData(res, d);
}

} // namespace

// ---------------------------------------------------------------------------
// HandleDirectorReplay — worker-phase validation + guarded synchronous replay
// ---------------------------------------------------------------------------
void HandleDirectorReplay(const httplib::Request& req, httplib::Response& res)
{
    // -----------------------------------------------------------------------
    // 0. Payload size cap (before parse where practical)
    // -----------------------------------------------------------------------
    static constexpr size_t kMaxPayloadBytes = 8u * 1024u * 1024u;  // 8 MiB
    if (req.body.size() > kMaxPayloadBytes)
    {
        SendCode(res, "payload_too_large", "Request body exceeds 8 MiB limit");
        return;
    }

    // -----------------------------------------------------------------------
    // 1. Parse JSON
    // -----------------------------------------------------------------------
    nlohmann::json body;
    try { body = nlohmann::json::parse(req.body); }
    catch (...)
    {
        SendCode(res, "invalid_input", "Request body is not valid JSON");
        return;
    }

    // -----------------------------------------------------------------------
    // 2. Session id — type-safe: presence + is_string + content validation
    // -----------------------------------------------------------------------
    if (!body.contains("replay_session_id") || !body["replay_session_id"].is_string())
    {
        SendCode(res, "invalid_session_id",
                 "replay_session_id must be a 1..128 char [A-Za-z0-9._-] string");
        return;
    }
    std::string sessionId = body["replay_session_id"].get<std::string>();
    if (!IsValidReplaySessionId(sessionId))
    {
        SendCode(res, "invalid_session_id",
                 "replay_session_id must be a 1..128 char [A-Za-z0-9._-] string");
        return;
    }

    // -----------------------------------------------------------------------
    // 3. Reserve replay slot before any further work
    // -----------------------------------------------------------------------
    if (!ReserveReplaySlot(sessionId))
    {
        SendCode(res, "replay_already_active", "A replay is already in progress");
        return;
    }
    ReplaySlotReservation reservation;
    reservation.held = true;

    // -----------------------------------------------------------------------
    // 4. Extract + validate top-level track structure
    // -----------------------------------------------------------------------
    if (!body.contains("track") || !body["track"].is_object())
    {
        SendCode(res, "invalid_input", "track must be an object");
        return;
    }
    const auto& track = body["track"];

    // transform_semantics
    if (!track.contains("transform_semantics") || !track["transform_semantics"].is_string() ||
        track["transform_semantics"].get<std::string>() != "absolute_from_source")
    {
        SendCode(res, "unsupported_transform_semantics",
                 "Only transform_semantics==\"absolute_from_source\" is supported");
        return;
    }

    // loop option
    if (body.contains("loop") && body["loop"].is_boolean() && body["loop"].get<bool>())
    {
        nlohmann::json d;
        d["code"] = "unsupported_replay_option";
        d["option"] = "loop";
        d["message"] = "loop replay is not supported";
        CRookServer::SendErrorData(res, d);
        return;
    }

    // animated_object_ids — non-empty array of unique strings, count <= 256
    if (!track.contains("animated_object_ids") || !track["animated_object_ids"].is_array() ||
        track["animated_object_ids"].empty())
    {
        SendCode(res, "invalid_input", "animated_object_ids must be a non-empty array");
        return;
    }
    const auto& animatedIdsJson = track["animated_object_ids"];
    if (animatedIdsJson.size() > 256)
    {
        SendCode(res, "object_count_exceeds_cap",
                 "animated_object_ids exceeds 256 unique object limit");
        return;
    }
    std::set<std::string> animatedObjectIds;
    for (const auto& idVal : animatedIdsJson)
    {
        if (!idVal.is_string())
        {
            SendCode(res, "invalid_input", "animated_object_ids must be strings");
            return;
        }
        animatedObjectIds.insert(idVal.get<std::string>());
    }
    if (animatedObjectIds.size() != animatedIdsJson.size())
    {
        SendCode(res, "invalid_input", "animated_object_ids must be unique");
        return;
    }

    // frame_count
    if (!track.contains("frame_count") || !track["frame_count"].is_number_integer())
    {
        SendCode(res, "invalid_input", "frame_count must be an integer");
        return;
    }
    int frameCount = track["frame_count"].get<int>();
    if (frameCount < 1)
    {
        SendCode(res, "invalid_input", "frame_count must be >= 1");
        return;
    }
    if (frameCount > 3000)
    {
        SendCode(res, "frame_count_exceeds_cap", "frame_count exceeds 3000 limit");
        return;
    }

    // camera_frames / object_frames arrays
    if (!track.contains("camera_frames") || !track["camera_frames"].is_array())
    {
        SendCode(res, "track_invalid", "camera_frames must be an array");
        return;
    }
    if (!track.contains("object_frames") || !track["object_frames"].is_array())
    {
        SendCode(res, "track_invalid", "object_frames must be an array");
        return;
    }
    const auto& cameraFramesJson = track["camera_frames"];
    const auto& objectFramesJson = track["object_frames"];
    if (static_cast<int>(cameraFramesJson.size()) != frameCount)
    {
        SendCode(res, "track_invalid",
                 "camera_frames length does not match frame_count");
        return;
    }
    if (static_cast<int>(objectFramesJson.size()) != frameCount)
    {
        SendCode(res, "track_invalid",
                 "object_frames length does not match frame_count");
        return;
    }

    // Validate frame_index sequence for both arrays (1..N in order)
    for (int i = 0; i < frameCount; ++i)
    {
        const auto& cf = cameraFramesJson[i];
        if (!cf.is_object() || !cf.contains("frame_index") || !cf["frame_index"].is_number_integer() ||
            cf["frame_index"].get<int>() != i + 1)
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = "camera_frames[" + std::to_string(i) + "].frame_index out of order";
            d["frame_index"] = i + 1;
            CRookServer::SendErrorData(res, d);
            return;
        }
        const auto& of = objectFramesJson[i];
        if (!of.is_object() || !of.contains("frame_index") || !of["frame_index"].is_number_integer() ||
            of["frame_index"].get<int>() != i + 1)
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = "object_frames[" + std::to_string(i) + "].frame_index out of order";
            d["frame_index"] = i + 1;
            CRookServer::SendErrorData(res, d);
            return;
        }
    }

    // -----------------------------------------------------------------------
    // 5. Compute effective_fps + dwell_ms, apply caps
    // -----------------------------------------------------------------------
    double effectiveFps = 24.0;
    if (body.contains("fps") && !body["fps"].is_null())
    {
        if (!body["fps"].is_number())
        {
            SendCode(res, "invalid_fps", "fps must be a positive finite number");
            return;
        }
        effectiveFps = body["fps"].get<double>();
    }
    else if (track.contains("fps") && !track["fps"].is_null())
    {
        if (!track["fps"].is_number())
        {
            SendCode(res, "invalid_fps", "fps must be a positive finite number");
            return;
        }
        effectiveFps = track["fps"].get<double>();
    }
    if (!std::isfinite(effectiveFps) || effectiveFps <= 0.0)
    {
        SendCode(res, "invalid_fps", "fps must be a positive finite number");
        return;
    }
    double dwellMs = 1000.0 / effectiveFps;
    if (dwellMs > 250.0)
    {
        SendCode(res, "frame_dwell_exceeds_cap",
                 "Computed dwell_ms exceeds 250ms cap (fps too low)");
        return;
    }
    double plannedDurationMs = static_cast<double>(frameCount) * dwellMs;
    if (plannedDurationMs > 60000.0)
    {
        SendCode(res, "replay_duration_exceeds_cap",
                 "frame_count * dwell_ms exceeds 60000ms limit");
        return;
    }

    // restore_on_finish (default true)
    bool restoreOnFinish = true;
    if (body.contains("restore_on_finish") && body["restore_on_finish"].is_boolean())
        restoreOnFinish = body["restore_on_finish"].get<bool>();

    // -----------------------------------------------------------------------
    // 6. Worker-phase per-frame pre-parse (no-mutation guarantee)
    //    Parse every frame BEFORE Dispatch — if any frame is malformed we fail
    //    before touching the document.
    // -----------------------------------------------------------------------
    std::vector<FrameCamera> perFrameCameras;
    perFrameCameras.reserve(static_cast<size_t>(frameCount));
    std::vector<std::vector<FrameObjectTransform>> perFrameObjects;
    perFrameObjects.reserve(static_cast<size_t>(frameCount));

    // We'll also capture sourceBbox from frame 0 to verify consistency.
    // Key: objectId -> sourceBbox (from first frame). Used to cross-check frames 1..N.
    std::map<std::string, ON_BoundingBox> sourceBoxRef;
    static constexpr double kBboxTolerance = 1.0e-4;

    for (int i = 0; i < frameCount; ++i)
    {
        // --- Camera parse ---
        try
        {
            nlohmann::json cameraBody;
            cameraBody["camera"] = cameraFramesJson[i]["camera"];
            perFrameCameras.push_back(ParseCamera(cameraBody));
        }
        catch (const DirectorFrameValidationError& ex)
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = std::string("camera_frames[") + std::to_string(i) + "]: " + ex.what();
            d["frame_index"] = i + 1;
            CRookServer::SendErrorData(res, d);
            return;
        }
        catch (const std::exception& ex)
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = std::string("camera_frames[") + std::to_string(i) + "]: " + ex.what();
            d["frame_index"] = i + 1;
            CRookServer::SendErrorData(res, d);
            return;
        }

        // --- Object-transforms parse ---
        std::vector<FrameObjectTransform> frameObjects;
        try
        {
            nlohmann::json objBody;
            objBody["object_transforms"] = objectFramesJson[i]["object_transforms"];
            frameObjects = ParseFrameObjectTransforms(objBody);
        }
        catch (const DirectorFrameValidationError& ex)
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = std::string("object_frames[") + std::to_string(i) + "]: " + ex.what();
            d["frame_index"] = i + 1;
            if (!ex.affectedObjectIds.empty())
                d["object_id"] = ex.affectedObjectIds[0];
            CRookServer::SendErrorData(res, d);
            return;
        }
        catch (const std::exception& ex)
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = std::string("object_frames[") + std::to_string(i) + "]: " + ex.what();
            d["frame_index"] = i + 1;
            CRookServer::SendErrorData(res, d);
            return;
        }

        // --- Exact object-id set equality check ---
        std::set<std::string> frameIds;
        for (const auto& ft : frameObjects)
            frameIds.insert(ft.objectId);
        if (frameIds != animatedObjectIds)
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = "object_frames[" + std::to_string(i) +
                           "] object_id set does not exactly match animated_object_ids";
            d["frame_index"] = i + 1;
            CRookServer::SendErrorData(res, d);
            return;
        }
        // Also check no duplicates within the frame
        if (frameObjects.size() != frameIds.size())
        {
            nlohmann::json d;
            d["code"] = "track_invalid";
            d["message"] = "object_frames[" + std::to_string(i) +
                           "] contains duplicate object_id entries";
            d["frame_index"] = i + 1;
            CRookServer::SendErrorData(res, d);
            return;
        }

        // --- source_state (sourceBbox) consistency across frames ---
        if (i == 0)
        {
            for (const auto& ft : frameObjects)
                sourceBoxRef[ft.objectId] = ft.sourceBbox;
        }
        else
        {
            for (const auto& ft : frameObjects)
            {
                const auto it = sourceBoxRef.find(ft.objectId);
                if (it != sourceBoxRef.end() &&
                    !BboxAlmostEqual(ft.sourceBbox, it->second, kBboxTolerance))
                {
                    nlohmann::json d;
                    d["code"] = "track_invalid";
                    d["message"] = "source_state bbox for object " + ft.objectId +
                                   " differs across frames";
                    d["frame_index"] = i + 1;
                    d["object_id"] = ft.objectId;
                    CRookServer::SendErrorData(res, d);
                    return;
                }
            }
        }

        perFrameObjects.push_back(std::move(frameObjects));
    }

    // -----------------------------------------------------------------------
    // 7. Dispatch the loop lambda to the UI thread
    //    perFrameObjects, perFrameCameras, etc. are captured by move/value.
    //    The lambda does NO parsing or track access — only uses the pre-parsed vectors.
    // -----------------------------------------------------------------------
    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [perFrameObjects = std::move(perFrameObjects),
         perFrameCameras = std::move(perFrameCameras),
         frameCount,
         dwellMs,
         effectiveFps,
         plannedDurationMs,
         restoreOnFinish,
         sessionId]() -> nlohmann::json
    {
        // Resolve document + view
        CRhinoDoc* pDoc = GetDocument();
        if (!pDoc)
            throw std::runtime_error("No active document");

        // --- One viewport guard for the whole replay ---
        // Ctor calls ValidateSlice1ModelRhinoView; throws DirectorFrameValidationError("unsupported_view")
        DirectorViewportGuard viewportGuard(pDoc);
        CRhinoView* pView = viewportGuard.View();

        // One drain suspension for the whole loop
        DispatchDrainSuspension drainGuard;

        // --- UI-phase doc-dependent validation (frame 0 covers all, set-equality proven worker-phase) ---
        for (const auto& ft : perFrameObjects[0])
        {
            const CRhinoObject* obj = pDoc->LookupObject(ft.uuid);
            if (!obj || obj->IsDeleted())
            {
                nlohmann::json err;
                err["code"] = "object_not_found";
                err["object_id"] = ft.objectId;
                err["message"] = "Object not found in document: " + ft.objectId;
                return err;
            }
        }
        // source-state drift check — ValidateFrameObjects now fails only on bbox mismatch
        try
        {
            ValidateFrameObjects(pDoc, perFrameObjects[0]);
        }
        catch (const DirectorFrameValidationError& ex)
        {
            nlohmann::json err;
            err["code"] = "object_state_mismatch";
            err["message"] = ex.what();
            if (!ex.affectedObjectIds.empty())
                err["object_id"] = ex.affectedObjectIds[0];
            return err;
        }

        // --- Per-frame replay loop ---
        int framesPlayed = 0;
        nlohmann::json evidence;
        std::optional<DirectorObjectPoseGuard> poseGuard;

        // Cancelled result builder — objects are at source on every cancel path; camera restored.
        auto makeCancelled = [&](int played) {
            nlohmann::json r;
            r["status"] = "cancelled";
            r["cancelled"] = true;
            r["frames_played"] = played;
            r["frame_count"] = frameCount;
            r["restored"] = true;
            r["replay_session_id"] = sessionId;
            return r;
        };

        // Perform the end-of-replay restore (objects, if a pose guard is engaged, plus the
        // viewport) and CHECK both results. DirectorObjectPoseGuard::Restore /
        // DirectorViewportGuard::Restore return false when restoration is incomplete; replay
        // must surface that as a restore_failed outcome (restored:false / dirty_partial_state)
        // rather than continue from dirty state or report completed/cancelled with restored:true.
        auto restoreOrError = [&](int frameIndexForError) -> std::optional<nlohmann::json>
        {
            bool objectsOk = true;
            if (poseGuard)
                objectsOk = poseGuard->Restore(evidence);
            const bool viewportOk = viewportGuard.Restore(evidence);
            if (objectsOk && viewportOk)
                return std::nullopt;

            nlohmann::json err;
            err["code"] = "restore_failed";
            err["message"] = "Replay could not restore the document to its pre-replay state";
            err["restored"] = false;
            err["objects_restored"] = objectsOk;
            err["viewport_restored"] = viewportOk;
            err["dirty_partial_state"] =
                (poseGuard && poseGuard->HasDirtyPartialState()) || !objectsOk || !viewportOk;
            if (frameIndexForError > 0)
                err["frame_index"] = frameIndexForError;
            return err;
        };

        for (int i = 0; i < frameCount; ++i)
        {
            // Cancel BEFORE applying frame i. Objects are at source here (never applied for
            // i==0; restored after the previous frame for i>0), so only the camera needs
            // restoring. framesPlayed == i, so a cancel before frame 0 reports frames_played=0.
            if (Slot().cancel.load(std::memory_order_acquire))
            {
                if (auto err = restoreOrError(0)) return *err;
                return makeCancelled(framesPlayed);
            }

            // Apply pose + camera. A post-validation failure HERE is a runtime apply failure,
            // normalized to frame_apply_failed with frame_index (restore first).
            try
            {
                poseGuard.emplace(pDoc, perFrameObjects[i]);
                poseGuard->Apply();
                framesPlayed = i + 1;
                SetCameraFromFrame(pView, perFrameCameras[i]);
                pView->Redraw();  // caller owns the redraw (SetCameraFromFrame no longer redraws)
            }
            catch (const DirectorFrameValidationError& ex)
            {
                bool objectsOk = true;
                if (poseGuard)
                    objectsOk = poseGuard->Restore(evidence);
                const bool viewportOk = viewportGuard.Restore(evidence);
                nlohmann::json err;
                err["code"] = "frame_apply_failed";
                err["message"] = ex.what();
                err["frame_index"] = i + 1;
                if (!ex.affectedObjectIds.empty())
                    err["object_id"] = ex.affectedObjectIds[0];
                err["restored"] = objectsOk && viewportOk;
                if ((poseGuard && poseGuard->HasDirtyPartialState()) || !objectsOk || !viewportOk)
                    err["dirty_partial_state"] = true;
                return err;
            }

            // Sliced dwell — pump ~16ms slices checking cancel each slice
            using clock = std::chrono::steady_clock;
            auto dwellStart = clock::now();
            double dwellRemaining = dwellMs;
            while (dwellRemaining > 0.0)
            {
                if (Slot().cancel.load(std::memory_order_acquire))
                {
                    if (auto err = restoreOrError(i + 1)) return *err;
                    return makeCancelled(framesPlayed);
                }

                constexpr double kSliceMs = 16.0;
                double sliceMs = (std::min)(kSliceMs, dwellRemaining);
                auto sliceStart = clock::now();
                MSG msg;
                while (PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE))
                {
                    TranslateMessage(&msg);
                    DispatchMessage(&msg);
                }
                auto elapsed = std::chrono::duration<double, std::milli>(clock::now() - sliceStart).count();
                double sleepMs = sliceMs - elapsed;
                if (sleepMs > 0.0)
                    ::Sleep(static_cast<DWORD>(sleepMs));

                auto totalElapsed = std::chrono::duration<double, std::milli>(clock::now() - dwellStart).count();
                dwellRemaining = dwellMs - totalElapsed;
            }

            // Post-dwell cancel check (catches cancel that arrived during the last slice)
            if (Slot().cancel.load(std::memory_order_acquire))
            {
                if (auto err = restoreOrError(i + 1)) return *err;
                return makeCancelled(framesPlayed);
            }

            // Between non-final frames: restore objects to source for the next frame
            if (i < frameCount - 1)
            {
                if (!poseGuard->Restore(evidence))
                {
                    // Objects failed to restore to source — must NOT continue to the next
                    // frame from dirty state. Best-effort restore the camera, then fail.
                    viewportGuard.Restore(evidence);
                    nlohmann::json err;
                    err["code"] = "restore_failed";
                    err["message"] = "Failed to restore objects to source between frames";
                    err["restored"] = false;
                    err["dirty_partial_state"] = true;
                    err["frame_index"] = i + 1;
                    return err;
                }
                // Objects are now at source and this frame's guard is spent. Disengage it so a
                // cancel observed here (or at the top of the next frame, before the next
                // emplace) restores ONLY the viewport via restoreOrError — never re-running
                // DirectorObjectPoseGuard::Restore, which re-applies the inverse delta (it is
                // not idempotent for an applied object) and would corrupt the pose. The
                // destructor will not double-restore: Restore() set m_restoreAttempted.
                poseGuard.reset();
                if (Slot().cancel.load(std::memory_order_acquire))
                {
                    if (auto err = restoreOrError(i + 1)) return *err;
                    return makeCancelled(framesPlayed);
                }
            }
            // Final frame: fall through to terminal block with poseGuard still engaged
        }

        // -----------------------------------------------------------------------
        // Terminal restore (completed path) — poseGuard holds the final frame guard
        // -----------------------------------------------------------------------
        if (restoreOnFinish)
        {
            if (auto err = restoreOrError(0)) return *err;
        }
        else
        {
            poseGuard->Disarm();
            viewportGuard.Disarm();
        }

        nlohmann::json result;
        result["status"] = "completed";
        result["frames_played"] = frameCount;
        result["frame_count"] = frameCount;
        result["effective_fps"] = effectiveFps;
        result["dwell_ms"] = dwellMs;
        result["planned_duration_ms"] = plannedDurationMs;
        result["restored"] = restoreOnFinish;
        result["replay_session_id"] = sessionId;
        return result;
    });

    // -----------------------------------------------------------------------
    // 8. Block on the future (worker thread) and send response
    // -----------------------------------------------------------------------
    nlohmann::json result;
    try
    {
        result = future.get();
    }
    catch (const DirectorFrameValidationError& ex)
    {
        nlohmann::json d;
        d["code"] = ex.code;
        d["message"] = ex.what();
        if (!ex.affectedObjectIds.empty())
            d["object_id"] = ex.affectedObjectIds[0];
        CRookServer::SendErrorData(res, d);
        return;
    }
    catch (const std::exception& ex)
    {
        nlohmann::json d;
        d["code"] = "frame_apply_failed";
        d["message"] = ex.what();
        CRookServer::SendErrorData(res, d);
        return;
    }

    // The lambda may return an error object (object_not_found, object_state_mismatch, etc.)
    // or a success object (status=completed|cancelled).
    if (result.contains("code"))
    {
        CRookServer::SendErrorData(res, result);
        return;
    }

    CRookServer::SendSuccess(res, result);
}

// ---------------------------------------------------------------------------
// HandleDirectorReplayCancel — pure worker-thread: touches only registry + atomic
// ---------------------------------------------------------------------------
void HandleDirectorReplayCancel(const httplib::Request& req, httplib::Response& res) {
    nlohmann::json body;
    try { body = nlohmann::json::parse(req.body); }
    catch (...) {
        nlohmann::json d;
        d["code"] = "invalid_input";
        d["message"] = "invalid JSON";
        CRookServer::SendErrorData(res, d);
        return;
    }

    // Type-safe: check presence AND string type before get<> — a non-string yields invalid_session_id.
    if (!body.contains("replay_session_id") || !body["replay_session_id"].is_string()) {
        nlohmann::json d;
        d["code"] = "invalid_session_id";
        d["message"] = "replay_session_id must be a 1..128 char [A-Za-z0-9._-] string";
        CRookServer::SendErrorData(res, d);
        return;
    }
    std::string id = body["replay_session_id"].get<std::string>();
    if (!IsValidReplaySessionId(id)) {
        nlohmann::json d;
        d["code"] = "invalid_session_id";
        d["message"] = "replay_session_id must be a 1..128 char [A-Za-z0-9._-] string";
        CRookServer::SendErrorData(res, d);
        return;
    }

    nlohmann::json data;
    data["replay_session_id"] = id;
    auto& s = Slot();
    std::lock_guard<std::mutex> lk(s.mutex);
    if (!s.active) {
        data["cancel_requested"] = false;
        data["reason"] = "no_active_replay";
    } else if (s.sessionId != id) {
        data["cancel_requested"] = false;
        data["reason"] = "session_mismatch";
    } else {
        s.cancel.store(true, std::memory_order_release);
        data["cancel_requested"] = true;
    }
    CRookServer::SendSuccess(res, data);
}

}} // namespace Rook::Handlers
