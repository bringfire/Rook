#include "stdafx.h"
#include "Handlers/DirectorReplayHandler.h"
#include "Handlers/DirectorFrame.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"
#include <atomic>
#include <mutex>
#include <regex>

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

} // namespace

// Stub — implemented in Task 3.
void HandleDirectorReplay(const httplib::Request& /*req*/, httplib::Response& res) {
    nlohmann::json d;
    d["code"] = "not_implemented";
    d["message"] = "replay not implemented";
    CRookServer::SendErrorData(res, d);
}

// Pure worker-thread cancel: touches only the registry + atomic. No Dispatch, no doc API.
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
