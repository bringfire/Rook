// SessionHandler.cpp
//
// GET  /session         — Current session info + stats
// GET  /session/history — Command history (limit/offset/source filter)
// GET  /session/list    — List all saved sessions
// POST /session/export  — Export session as JSON or Markdown

#include "stdafx.h"
#include "Handlers/SessionHandler.h"
#include "Interactive/SessionRecorder.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Helpers ────────────────────────────────────────────────────────

namespace {

std::string SourceToString(CommandSource src)
{
    switch (src) {
    case CommandSource::Mcp:    return "mcp";
    case CommandSource::Script: return "script";
    default:                    return "user";
    }
}

nlohmann::json SerializeCommandRecord(const CommandRecord& cmd)
{
    nlohmann::json c;
    c["id"]                = cmd.id;
    c["sequenceNumber"]    = cmd.sequenceNumber;
    c["timestamp"]         = cmd.timestamp;
    c["source"]            = SourceToString(cmd.source);
    c["commandName"]       = cmd.commandName;
    c["success"]           = cmd.success;
    c["durationMs"]        = cmd.durationMs;
    c["objectsCreatedCount"] = cmd.objectsCreatedCount;
    if (!cmd.errorMessage.empty())
        c["errorMessage"] = cmd.errorMessage;
    if (!cmd.endpoint.empty())
        c["endpoint"] = cmd.endpoint;
    if (!cmd.objectIdsCreated.empty())
        c["objectIdsCreated"] = cmd.objectIdsCreated;
    return c;
}

} // anonymous namespace

// ─── GET /session ───────────────────────────────────────────────────

void HandleSessionCurrent(const httplib::Request& /*req*/, httplib::Response& res)
{
    auto session = CSessionRecorder::Instance().GetCurrentSession();
    if (!session)
    {
        CRookServer::SendError(res, "No active session");
        return;
    }

    // Compute stats on-demand
    int mcpCount = 0, userCount = 0, scriptCount = 0;
    int successCount = 0, failCount = 0;
    int objectsCreated = 0;
    for (const auto& cmd : session->commands)
    {
        switch (cmd.source) {
        case CommandSource::Mcp:    mcpCount++; break;
        case CommandSource::Script: scriptCount++; break;
        default:                    userCount++; break;
        }
        if (cmd.success) successCount++; else failCount++;
        objectsCreated += cmd.objectsCreatedCount;
    }

    nlohmann::json stats;
    stats["totalCommands"]      = static_cast<int>(session->commands.size());
    stats["mcpCommands"]        = mcpCount;
    stats["userCommands"]       = userCount;
    stats["scriptCommands"]     = scriptCount;
    stats["successfulCommands"] = successCount;
    stats["failedCommands"]     = failCount;
    stats["objectsCreated"]     = objectsCreated;

    nlohmann::json result;
    result["id"]           = session->id;
    result["startedAt"]    = session->startedAt;
    result["endedAt"]      = session->endedAt;
    result["document"]     = {
        {"name", session->document.name},
        {"path", session->document.path},
        {"units", session->document.units}
    };
    result["commandCount"] = static_cast<int>(session->commands.size());
    result["stats"]        = stats;

    CRookServer::SendSuccess(res, result);
}

// ─── GET /session/history ───────────────────────────────────────────

void HandleSessionHistory(const httplib::Request& req, httplib::Response& res)
{
    int limit = 100;
    int offset = 0;
    std::string sourceFilter;

    // Parse query params
    if (req.has_param("limit"))
    {
        try { limit = std::stoi(req.get_param_value("limit")); }
        catch (...) {}
    }
    if (req.has_param("offset"))
    {
        try { offset = std::stoi(req.get_param_value("offset")); }
        catch (...) {}
    }
    if (req.has_param("source"))
        sourceFilter = req.get_param_value("source");

    auto history = CSessionRecorder::Instance().GetHistory(limit, offset, sourceFilter);

    auto cmds = nlohmann::json::array();
    for (const auto& cmd : history)
        cmds.push_back(SerializeCommandRecord(cmd));

    nlohmann::json result;
    result["count"]    = static_cast<int>(history.size());
    result["offset"]   = offset;
    result["commands"] = cmds;

    CRookServer::SendSuccess(res, result);
}

// ─── GET /session/list ──────────────────────────────────────────────

void HandleSessionList(const httplib::Request& req, httplib::Response& res)
{
    int limit = 50;
    if (req.has_param("limit"))
    {
        try { limit = std::stoi(req.get_param_value("limit")); }
        catch (...) {}
    }

    auto sessions = CSessionRecorder::Instance().ListSessions(limit);

    auto arr = nlohmann::json::array();
    for (const auto& s : sessions)
    {
        nlohmann::json entry;
        entry["id"]           = s.id;
        entry["documentName"] = s.documentName;
        entry["startedAt"]    = s.startedAt;
        entry["endedAt"]      = s.endedAt;
        entry["commandCount"] = s.commandCount;
        arr.push_back(entry);
    }

    nlohmann::json result;
    result["count"]    = static_cast<int>(sessions.size());
    result["sessions"] = arr;

    CRookServer::SendSuccess(res, result);
}

// ─── POST /session/export ───────────────────────────────────────────

void HandleSessionExport(const httplib::Request& req, httplib::Response& res)
{
    auto session = CSessionRecorder::Instance().GetCurrentSession();
    if (!session)
    {
        CRookServer::SendError(res, "No active session to export");
        return;
    }

    std::string format = "json";
    if (!req.body.empty())
    {
        auto body = nlohmann::json::parse(req.body, nullptr, false);
        if (!body.is_discarded() && body.contains("format"))
            format = body.value("format", "json");
    }

    if (format == "markdown")
    {
        std::ostringstream md;
        md << "# Session: " << session->document.name << "\n\n";
        md << "- **ID**: " << session->id << "\n";
        md << "- **Started**: " << session->startedAt << "\n";
        if (!session->endedAt.empty())
            md << "- **Ended**: " << session->endedAt << "\n";
        md << "- **Commands**: " << session->commands.size() << "\n\n";
        md << "## Command History\n\n";

        for (const auto& cmd : session->commands)
        {
            const char* status = cmd.success ? "+" : "x";
            std::string source = SourceToString(cmd.source);
            for (auto& ch : source) ch = static_cast<char>(toupper(static_cast<unsigned char>(ch)));
            md << "- [" << status << "] **" << cmd.commandName
               << "** (" << source << ") - " << cmd.timestamp << "\n";
            if (cmd.objectsCreatedCount > 0)
                md << "  - Created " << cmd.objectsCreatedCount << " object(s)\n";
            if (!cmd.errorMessage.empty())
                md << "  - Error: " << cmd.errorMessage << "\n";
        }

        nlohmann::json result;
        result["markdown"] = md.str();
        CRookServer::SendSuccess(res, result);
    }
    else if (format == "json")
    {
        // Return full session as JSON
        nlohmann::json j;
        j["id"] = session->id;
        j["startedAt"] = session->startedAt;
        j["endedAt"] = session->endedAt;
        j["document"] = {
            {"name", session->document.name},
            {"path", session->document.path},
            {"units", session->document.units}
        };

        auto cmds = nlohmann::json::array();
        for (const auto& cmd : session->commands)
            cmds.push_back(SerializeCommandRecord(cmd));
        j["commands"] = cmds;

        CRookServer::SendSuccess(res, j);
    }
    else
    {
        CRookServer::SendError(res, "Unknown format: " + format);
    }
}

} // namespace Handlers
} // namespace Rook
