// SessionRecorder.cpp
//
// Records all commands (MCP + user) for session history.
// CRhinoEventWatcher captures OnBeginCommand/OnEndCommand on the main thread.
// Sessions are persisted to %APPDATA%/Rook/sessions/ as JSON files.

#include "stdafx.h"
#include "Interactive/SessionRecorder.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"

#include <filesystem>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <random>

namespace fs = std::filesystem;

namespace Rook {

// ════════════════════════════════════════════════════════════════════
// Singleton
// ════════════════════════════════════════════════════════════════════

CSessionRecorder::CSessionRecorder() = default;
CSessionRecorder::~CSessionRecorder() { Stop(); }

CSessionRecorder& CSessionRecorder::Instance()
{
    static CSessionRecorder instance;
    return instance;
}

// ════════════════════════════════════════════════════════════════════
// Helpers
// ════════════════════════════════════════════════════════════════════

std::string CSessionRecorder::NowIso8601()
{
    auto now = std::chrono::system_clock::now();
    auto tt = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    struct tm utc;
    gmtime_s(&utc, &tt);

    std::ostringstream oss;
    oss << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S")
        << '.' << std::setfill('0') << std::setw(3) << ms.count() << 'Z';
    return oss.str();
}

std::string CSessionRecorder::GetSessionsBasePath()
{
    // %APPDATA%/Rook/sessions/
    const char* appdata = std::getenv("APPDATA");
    if (!appdata) appdata = "C:\\Users\\Default\\AppData\\Roaming";
    return std::string(appdata) + "\\Rook\\sessions";
}

std::string CSessionRecorder::MakeSessionId()
{
    // 8 hex chars from random generator — unique enough for sessions
    static std::mt19937 rng(std::random_device{}());
    std::uniform_int_distribution<uint32_t> dist;
    std::ostringstream oss;
    oss << std::hex << std::setfill('0') << std::setw(8) << dist(rng);
    return oss.str();
}

// ════════════════════════════════════════════════════════════════════
// Lifecycle
// ════════════════════════════════════════════════════════════════════

void CSessionRecorder::Start(ON_UUID pluginId)
{
    if (m_running.load()) return;

    // Ensure sessions directory exists
    try
    {
        fs::create_directories(GetSessionsBasePath());
    }
    catch (...) {}

    m_watcher = std::make_unique<CSessionWatcher>(*this);
    m_watcher->Register();
    m_watcher->Enable(true);
    m_running.store(true);

    // Start session for current document if one is open
    CRhinoDoc* pDoc = GetDocument();
    if (pDoc)
    {
        try
        {
            StartSession(*pDoc);
        }
        catch (...)
        {
            Stop();
            throw;
        }
    }
}

void CSessionRecorder::Stop()
{
    const bool wasRunning = m_running.exchange(false);
    bool hasSession = false;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        hasSession = static_cast<bool>(m_session);
    }

    const bool hasStartupState = m_watcher != nullptr || hasSession;
    if (!wasRunning && !hasStartupState) return;

    if (m_watcher)
    {
        m_watcher->Enable(false);
        m_watcher->UnRegister();
        m_watcher.reset();
    }

    EndSession("shutdown");
}

// ════════════════════════════════════════════════════════════════════
// Session Lifecycle
// ════════════════════════════════════════════════════════════════════

void CSessionRecorder::StartSession(CRhinoDoc& doc)
{
    // C18 fix: Collect serialized JSON under lock, write outside.
    std::string oldJson, oldPath, newJson, newPath;
    {
        std::lock_guard<std::mutex> lock(m_mutex);

        // End any existing session
        if (m_session)
        {
            m_session->endedAt = NowIso8601();
            m_session->endReason = "new_document";
            oldJson = SerializeSessionLocked();
            oldPath = m_sessionFilePath;
            m_session.reset();
        }

        auto session = std::make_shared<SessionData>();
        session->id = MakeSessionId();
        session->startedAt = NowIso8601();

        // Document info
        ON_wString wName(doc.GetPathName());
        if (wName.IsEmpty())
            session->document.name = "Untitled";
        else
        {
            session->document.path = WideToUtf8(wName);
            auto pos = session->document.path.find_last_of("\\/");
            session->document.name = (pos != std::string::npos)
                ? session->document.path.substr(pos + 1)
                : session->document.path;
        }

        const auto& ut = doc.Properties().ModelUnitsAndTolerances();
        ON_wString unitName = ut.m_unit_system.ToString();
        session->document.units = WideToUtf8(unitName);

        m_session = session;
        m_sequenceNumber = 0;
        m_sessionFilePath = GetSessionsBasePath() + "\\" + session->id + ".json";

        newJson = SerializeSessionLocked();
        newPath = m_sessionFilePath;
    }

    // Disk I/O outside the lock
    if (!oldPath.empty()) WriteSessionFile(oldPath, oldJson);
    if (!newPath.empty()) WriteSessionFile(newPath, newJson);
}

void CSessionRecorder::EndSession(const std::string& reason)
{
    std::string json, path;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_session) return;

        m_session->endedAt = NowIso8601();
        m_session->endReason = reason;
        json = SerializeSessionLocked();
        path = m_sessionFilePath;
        m_session.reset();
        m_sessionFilePath.clear();
    }

    // Disk I/O outside the lock
    WriteSessionFile(path, json);
}

std::string CSessionRecorder::SerializeSessionLocked() const
{
    // Must be called with m_mutex held.
    if (!m_session) return {};

    nlohmann::json j;
    j["id"] = m_session->id;
    j["startedAt"] = m_session->startedAt;
    j["endedAt"] = m_session->endedAt;
    j["endReason"] = m_session->endReason;
    j["document"] = {
        {"name", m_session->document.name},
        {"path", m_session->document.path},
        {"units", m_session->document.units}
    };

    auto cmds = nlohmann::json::array();
    for (const auto& cmd : m_session->commands)
    {
        nlohmann::json c;
        c["id"] = cmd.id;
        c["sequenceNumber"] = cmd.sequenceNumber;
        c["timestamp"] = cmd.timestamp;
        c["source"] = cmd.source == CommandSource::Mcp ? "mcp"
                    : cmd.source == CommandSource::Script ? "script" : "user";
        c["commandName"] = cmd.commandName;
        c["success"] = cmd.success;
        c["durationMs"] = cmd.durationMs;
        c["objectsCreatedCount"] = cmd.objectsCreatedCount;
        if (!cmd.errorMessage.empty())
            c["errorMessage"] = cmd.errorMessage;
        if (!cmd.endpoint.empty())
            c["endpoint"] = cmd.endpoint;
        if (!cmd.objectIdsCreated.empty())
            c["objectIdsCreated"] = cmd.objectIdsCreated;
        cmds.push_back(c);
    }
    j["commands"] = cmds;

    return j.dump(2);
}

void CSessionRecorder::WriteSessionFile(const std::string& path,
                                         const std::string& json)
{
    // C18 fix: Pure I/O helper — no lock needed.
    if (path.empty() || json.empty()) return;
    try
    {
        std::ofstream out(path);
        if (out.is_open())
            out << json;
    }
    catch (...) {}
}

// ════════════════════════════════════════════════════════════════════
// MCP Recording
// ════════════════════════════════════════════════════════════════════

void CSessionRecorder::BeginMcpRequest()
{
    // C12 fix: Atomic increment — safe for concurrent HTTP requests.
    m_mcpRequestDepth.fetch_add(1, std::memory_order_acq_rel);
}

void CSessionRecorder::EndMcpRequest()
{
    // C12 fix: Atomic decrement.
    m_mcpRequestDepth.fetch_sub(1, std::memory_order_acq_rel);
}

void CSessionRecorder::RecordMcpCommand(const std::string& endpoint,
                                         const std::string& method,
                                         bool success,
                                         double durationMs,
                                         int objectsCreated)
{
    std::string json, path;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_session) return;

        m_sequenceNumber++;
        CommandRecord rec;
        rec.id = "cmd_" + std::to_string(m_sequenceNumber);
        rec.sequenceNumber = m_sequenceNumber;
        rec.timestamp = NowIso8601();
        rec.source = CommandSource::Mcp;
        rec.commandName = method + " " + endpoint;
        rec.endpoint = endpoint;
        rec.success = success;
        rec.durationMs = durationMs;
        rec.objectsCreatedCount = objectsCreated;

        m_session->commands.push_back(std::move(rec));

        // Auto-save every 10 commands
        if (m_session->commands.size() % 10 == 0)
        {
            json = SerializeSessionLocked();
            path = m_sessionFilePath;
        }
    }

    // Disk I/O outside the lock
    WriteSessionFile(path, json);
}

// ════════════════════════════════════════════════════════════════════
// Queries (HTTP thread safe)
// ════════════════════════════════════════════════════════════════════

std::shared_ptr<const SessionData> CSessionRecorder::GetCurrentSession() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_session) return nullptr;
    // C7 fix: Return a deep copy so HTTP threads can iterate commands
    // without holding the mutex. The original code returned a shared_ptr
    // to the LIVE session — the main thread could push_back() to commands
    // (triggering vector reallocation) while an HTTP thread iterated,
    // causing a data race and potential crash.
    return std::make_shared<const SessionData>(*m_session);
}

std::vector<CommandRecord> CSessionRecorder::GetHistory(
    int limit, int offset, const std::string& sourceFilter) const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    std::vector<CommandRecord> result;
    if (!m_session) return result;

    const auto& cmds = m_session->commands;
    int count = 0;
    int skipped = 0;

    for (auto it = cmds.rbegin(); it != cmds.rend() && count < limit; ++it)
    {
        // Apply source filter
        if (!sourceFilter.empty() && sourceFilter != "all")
        {
            if (sourceFilter == "mcp" && it->source != CommandSource::Mcp) continue;
            if (sourceFilter == "user" && it->source != CommandSource::User) continue;
            if (sourceFilter == "script" && it->source != CommandSource::Script) continue;
        }

        if (skipped < offset) { skipped++; continue; }

        result.push_back(*it);
        count++;
    }

    return result;
}

std::vector<SessionSummary> CSessionRecorder::ListSessions(int limit) const
{
    std::vector<SessionSummary> result;
    std::string basePath = GetSessionsBasePath();

    try
    {
        if (!fs::exists(basePath)) return result;

        // Collect session files sorted by modification time (newest first)
        std::vector<fs::directory_entry> entries;
        for (const auto& entry : fs::directory_iterator(basePath))
        {
            if (entry.path().extension() == ".json")
                entries.push_back(entry);
        }

        std::sort(entries.begin(), entries.end(),
            [](const fs::directory_entry& a, const fs::directory_entry& b) {
                return a.last_write_time() > b.last_write_time();
            });

        for (const auto& entry : entries)
        {
            if (static_cast<int>(result.size()) >= limit) break;

            try
            {
                std::ifstream in(entry.path());
                if (!in.is_open()) continue;

                auto j = nlohmann::json::parse(in, nullptr, false);
                if (j.is_discarded()) continue;

                SessionSummary s;
                s.id = j.value("id", "");
                s.startedAt = j.value("startedAt", "");
                s.endedAt = j.value("endedAt", "");
                if (j.contains("document") && j["document"].contains("name"))
                    s.documentName = j["document"]["name"].get<std::string>();
                if (j.contains("commands"))
                    s.commandCount = static_cast<int>(j["commands"].size());
                result.push_back(std::move(s));
            }
            catch (...) { continue; }
        }
    }
    catch (...) {}

    return result;
}

// ════════════════════════════════════════════════════════════════════
// CSessionWatcher — CRhinoEventWatcher subclass
// ════════════════════════════════════════════════════════════════════

CSessionRecorder::CSessionWatcher::CSessionWatcher(CSessionRecorder& owner)
    : m_owner(owner)
{
}

// Save commands that must suppress HTTP dispatch during execution.
// Rhino serializes to a temp file then renames — any doc.Objects access
// from a dispatched HTTP handler during that window can prevent the rename.
static bool IsSaveCommand(const wchar_t* name)
{
    return (_wcsicmp(name, L"Save") == 0
         || _wcsicmp(name, L"SaveSmall") == 0
         || _wcsicmp(name, L"SaveAs") == 0
         || _wcsicmp(name, L"IncrementalSave") == 0);
}

void CSessionRecorder::CSessionWatcher::OnBeginCommand(
    const CRhinoCommand& command, const CRhinoCommandContext& /*context*/)
{
    // Save-guard: suppress HTTP dispatch during save commands.
    if (IsSaveCommand(command.EnglishCommandName()))
        CMainThreadDispatcher::Instance().BeginSaveGuard();

    if (!m_owner.m_running.load()) return;

    // Skip if this is triggered by an MCP request (recorded separately via RecordMcpCommand)
    if (m_owner.m_mcpRequestDepth.load(std::memory_order_acquire) > 0) return;

    // C11 fix: Push onto command stack instead of overwriting single slot.
    // Nested commands (e.g., _Delete triggering _SelAll) push additional
    // entries; only when the stack goes 1→0 in OnEndCommand do we record.
    CSessionRecorder::PendingCommand pending;
    pending.name = WideToUtf8(command.EnglishCommandName());
    pending.startTime = std::chrono::steady_clock::now();
    m_owner.m_commandStack.push_back(std::move(pending));
}

void CSessionRecorder::CSessionWatcher::OnEndCommand(
    const CRhinoCommand& command,
    const CRhinoCommandContext& /*context*/,
    CRhinoCommand::result rc)
{
    // Save-guard: release the dispatch suppression.
    if (IsSaveCommand(command.EnglishCommandName()))
        CMainThreadDispatcher::Instance().EndSaveGuard();

    if (!m_owner.m_running.load()) return;
    if (m_owner.m_mcpRequestDepth.load(std::memory_order_acquire) > 0) return;

    // C11 fix: Pop from command stack. Only record when the outermost
    // command completes (stack goes from 1 → 0).
    if (m_owner.m_commandStack.empty()) return;

    auto top = std::move(m_owner.m_commandStack.back());
    m_owner.m_commandStack.pop_back();

    // Only record the outermost command — nested commands are internal
    if (!m_owner.m_commandStack.empty()) return;

    auto elapsed = std::chrono::steady_clock::now() - top.startTime;
    double durationMs = std::chrono::duration<double, std::milli>(elapsed).count();

    std::string json, path;
    {
        std::lock_guard<std::mutex> lock(m_owner.m_mutex);
        if (!m_owner.m_session) return;

        m_owner.m_sequenceNumber++;
        CommandRecord rec;
        rec.id = "cmd_" + std::to_string(m_owner.m_sequenceNumber);
        rec.sequenceNumber = m_owner.m_sequenceNumber;
        rec.timestamp = NowIso8601();
        rec.source = CommandSource::User;
        rec.commandName = top.name;
        rec.success = (rc == CRhinoCommand::success);
        rec.durationMs = durationMs;

        m_owner.m_session->commands.push_back(std::move(rec));

        // Auto-save every 10 commands
        if (m_owner.m_session->commands.size() % 10 == 0)
        {
            json = m_owner.SerializeSessionLocked();
            path = m_owner.m_sessionFilePath;
        }
    }

    // Disk I/O outside the lock
    CSessionRecorder::WriteSessionFile(path, json);
}

void CSessionRecorder::CSessionWatcher::OnCloseDocument(CRhinoDoc& /*doc*/)
{
    if (!m_owner.m_running.load()) return;
    m_owner.EndSession("document_closed");
}

void CSessionRecorder::CSessionWatcher::OnEndOpenDocument(
    CRhinoDoc& doc, const wchar_t* /*filename*/, BOOL /*bMerge*/, BOOL /*bReference*/)
{
    if (!m_owner.m_running.load()) return;
    m_owner.StartSession(doc);
}

} // namespace Rook
