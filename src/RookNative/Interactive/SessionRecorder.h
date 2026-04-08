// SessionRecorder.h
//
// Records all commands (MCP + user) for session history.
// Uses CRhinoEventWatcher for OnBeginCommand/OnEndCommand/OnCloseDocument.
// Persists sessions to %APPDATA%/Rook/sessions/.
//
// Thread safety: all event watcher callbacks fire on the main thread.
// HTTP reader threads acquire m_mutex for read access to session data.

#pragma once

#include <string>
#include <vector>
#include <mutex>
#include <atomic>
#include <chrono>

namespace Rook {

// ─── Data Models ────────────────────────────────────────────────────

enum class CommandSource { Mcp, User, Script };

struct CommandRecord
{
    std::string id;
    int sequenceNumber = 0;
    std::string timestamp;                 // ISO 8601
    CommandSource source = CommandSource::User;
    std::string commandName;
    std::string endpoint;                  // for MCP commands
    bool success = true;
    double durationMs = 0.0;
    std::string errorMessage;
    int objectsCreatedCount = 0;
    std::vector<std::string> objectIdsCreated;
    std::vector<std::string> objectIdsDeleted;
};

struct DocumentInfo
{
    std::string name;
    std::string path;
    std::string units;
};

struct SessionData
{
    std::string id;
    std::string startedAt;                 // ISO 8601
    std::string endedAt;                   // ISO 8601 or empty
    std::string endReason;
    DocumentInfo document;
    std::vector<CommandRecord> commands;
};

struct SessionSummary
{
    std::string id;
    std::string documentName;
    std::string startedAt;
    std::string endedAt;
    int commandCount = 0;
};

// ─── Session Recorder ───────────────────────────────────────────────

class CSessionRecorder
{
public:
    static CSessionRecorder& Instance();

    // Lifecycle — call from main thread (OnLoadPlugIn / OnUnloadPlugIn).
    void Start(ON_UUID pluginId);
    void Stop();

    bool IsRunning() const { return m_running.load(); }

    // ─── MCP Recording (called from HTTP handler context) ───────────
    // C10+C12 fix: Use an atomic counter instead of a bool, so concurrent
    // HTTP requests don't corrupt each other's source tagging.
    void BeginMcpRequest();
    void EndMcpRequest();
    bool IsMcpRequest() const { return m_mcpRequestDepth.load(std::memory_order_acquire) > 0; }
    void RecordMcpCommand(const std::string& endpoint,
                          const std::string& method,
                          bool success,
                          double durationMs,
                          int objectsCreated = 0);

    // ─── Queries (called from HTTP threads, acquires m_mutex) ───────
    // Returns nullptr if no active session.
    std::shared_ptr<const SessionData> GetCurrentSession() const;
    std::vector<CommandRecord> GetHistory(int limit, int offset,
                                          const std::string& sourceFilter) const;
    std::vector<SessionSummary> ListSessions(int limit) const;

private:
    CSessionRecorder();
    ~CSessionRecorder();

    // ─── CRhinoEventWatcher subclass ────────────────────────────────

    class CSessionWatcher : public CRhinoEventWatcher
    {
    public:
        explicit CSessionWatcher(CSessionRecorder& owner);

        void OnBeginCommand(const CRhinoCommand& command,
                            const CRhinoCommandContext& context) override;
        void OnEndCommand(const CRhinoCommand& command,
                          const CRhinoCommandContext& context,
                          CRhinoCommand::result rc) override;
        void OnCloseDocument(CRhinoDoc& doc) override;
        void OnEndOpenDocument(CRhinoDoc& doc, const wchar_t* filename,
                               BOOL bMerge, BOOL bReference) override;

    private:
        CSessionRecorder& m_owner;
    };

    // ─── Session Lifecycle ──────────────────────────────────────────

    void StartSession(CRhinoDoc& doc);
    void EndSession(const std::string& reason);

    // C18 fix: Split serialize (under lock) from write (outside lock).
    std::string SerializeSessionLocked() const;  // must be called with m_mutex held
    static void WriteSessionFile(const std::string& path, const std::string& json);

    // ─── Helpers ────────────────────────────────────────────────────

    static std::string NowIso8601();
    static std::string GetSessionsBasePath();
    static std::string MakeSessionId();

    // ─── State ──────────────────────────────────────────────────────

    mutable std::mutex m_mutex;
    std::unique_ptr<CSessionWatcher> m_watcher;
    std::atomic<bool> m_running{false};
    // C12 fix: Counter instead of bool — concurrent HTTP requests each
    // increment on entry and decrement on exit. OnBeginCommand checks > 0.
    std::atomic<int> m_mcpRequestDepth{0};

    // Active session (guarded by m_mutex)
    std::shared_ptr<SessionData> m_session;
    std::string m_sessionFilePath;
    int m_sequenceNumber = 0;

    // C11 fix: Command stack instead of single-slot pending command.
    // Rhino commands can nest (e.g., _Delete triggers _SelAll internally).
    // A single-slot m_pendingCommandName would be overwritten by the inner
    // command, losing the outer command's name. The stack tracks all levels;
    // only when the stack goes from 1→0 does OnEndCommand record the
    // outermost command to the session.
    struct PendingCommand
    {
        std::string name;
        std::chrono::steady_clock::time_point startTime;
    };
    std::vector<PendingCommand> m_commandStack;  // main thread only
};

// C10 fix: RAII guard that calls BeginMcpRequest/EndMcpRequest.
// Place at the top of every write-path HTTP handler so that any Rhino
// commands triggered during the request are tagged as "mcp" source.
struct McpRequestGuard
{
    McpRequestGuard()  { CSessionRecorder::Instance().BeginMcpRequest(); }
    ~McpRequestGuard() { CSessionRecorder::Instance().EndMcpRequest(); }
    McpRequestGuard(const McpRequestGuard&) = delete;
    McpRequestGuard& operator=(const McpRequestGuard&) = delete;
};

} // namespace Rook
