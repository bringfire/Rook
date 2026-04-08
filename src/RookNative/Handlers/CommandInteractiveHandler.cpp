// CommandInteractiveHandler.cpp
//
// GET  /command/prompt  — Read current command prompt text + parse options
// POST /command/start   — Start a command via keystrokes
// POST /command/send    — Send input to an active command
// POST /command/cancel  — Cancel active command (Escape)
//
// All 4 endpoints use standard Dispatch() — no modal loops involved.
// RunScript acts as if each character were typed into the command prompt;
// when called outside a command it returns immediately and the script runs
// after control returns to Rhino's message loop.
//
// C27 note: POST /command vs POST /command/start
//
// POST /command (in CommandHandler.cpp) is fire-and-forget script execution.
// It runs the command string synchronously via RunScript and returns the
// result. Use for simple, non-interactive commands (e.g., _Box 0,0,0 10,10,10).
//
// POST /command/start (this file) is for interactive command sessions.
// It atomically cancels any active command, then starts the new one. The
// client should then poll GET /command/prompt for prompts and use
// POST /command/input to provide responses. Use for multi-step commands
// (e.g., _Line, _Polyline) where the user or AI provides input iteratively.

#include "stdafx.h"
#include "Handlers/CommandInteractiveHandler.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

namespace Rook {
namespace Handlers {

// ─── Prompt Parsing Helpers ─────────────────────────────────────────

namespace {

// Extract options from parenthesized groups in the prompt.
// e.g. "Center of circle ( Diameter Circumference )" → ["Diameter","Circumference"]
nlohmann::json ParseOptionsFromPrompt(const std::string& prompt)
{
    auto options = nlohmann::json::array();
    auto start = prompt.find('(');
    auto end = prompt.rfind(')');
    if (start == std::string::npos || end == std::string::npos || end <= start)
        return options;

    std::string inner = prompt.substr(start + 1, end - start - 1);
    std::istringstream iss(inner);
    std::string token;
    while (iss >> token)
    {
        if (!token.empty())
            options.push_back(token);
    }
    return options;
}

// Extract default value from angle brackets.
// e.g. "Radius <5.00>" → "5.00"
nlohmann::json ParseDefaultFromPrompt(const std::string& prompt)
{
    auto start = prompt.find('<');
    auto end = prompt.rfind('>');
    if (start == std::string::npos || end == std::string::npos || end <= start)
        return nullptr;

    return prompt.substr(start + 1, end - start - 1);
}

// Read the command prompt on the main thread and return as UTF-8 string.
std::string ReadPromptOnMain()
{
    auto future = CMainThreadDispatcher::Instance().Dispatch([&]() -> std::string {
        ON_wString prompt;
        RhinoApp().GetCommandPrompt(prompt);
        return WideToUtf8(prompt);
    });
    return future.get();
}

} // anonymous namespace

// ─── GET /command/prompt ────────────────────────────────────────────

void HandleCommandPrompt(const httplib::Request& /*req*/, httplib::Response& res)
{
    try
    {
        std::string prompt = ReadPromptOnMain();

        // C20 fix: Use prefix match against "Command:" (Rhino's idle prompt).
        // The old code used prompt.find("Command") which is a substring search —
        // it would false-negative on prompts containing "Command" as part of a
        // command name (e.g., "ExtrudeSurface"). Rhino's idle state always
        // starts with "Command:" (with colon), so rfind(x, 0) == prefix match.
        bool isActive = !prompt.empty() && !(prompt.rfind("Command:", 0) == 0);

        nlohmann::json result;
        result["prompt"]        = prompt;
        result["is_active"]     = isActive;
        result["options"]       = ParseOptionsFromPrompt(prompt);
        result["default_value"] = ParseDefaultFromPrompt(prompt);

        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error getting prompt: ") + ex.what());
    }
}

// ─── POST /command/start ────────────────────────────────────────────

void HandleCommandStart(const httplib::Request& req, httplib::Response& res)
{
    // Parse body on worker thread
    nlohmann::json body;
    if (!req.body.empty())
    {
        body = nlohmann::json::parse(req.body, nullptr, false);
        if (body.is_discarded() || !body.is_object())
        {
            CRookServer::SendError(res, "Invalid JSON body");
            return;
        }
    }

    if (!body.contains("command") || !body["command"].is_string())
    {
        CRookServer::SendError(res, "Missing required field: command");
        return;
    }

    std::string command = body["command"].get<std::string>();

    try
    {
        // C15 fix: Combine _Cancel and the new command into a single RunScript
        // call. Two separate RunScript calls are non-atomic — other events
        // (mouse messages, script injections) can interleave between them.
        // A single script string ensures Rhino processes both as one unit.
        auto future = CMainThreadDispatcher::Instance().Dispatch([&]() -> int {
            CRhinoDoc* pDoc = GetDocument();
            unsigned int docSn = pDoc ? pDoc->RuntimeSerialNumber() : 0;

            // Count objects before command
            int count = 0;
            if (pDoc) {
                CRhinoObjectIterator iter(*pDoc,
                    CRhinoObjectIterator::normal_or_locked_objects,
                    CRhinoObjectIterator::active_objects);
                for (const CRhinoObject* obj = iter.First(); obj; obj = iter.Next())
                    ++count;
            }

            // Atomic cancel + start: single script with both commands
            ON_wString combined(L"_Cancel ");
            combined += Utf8ToWide(command);
            combined += L"\n";
            RhinoApp().RunScript(docSn, static_cast<const wchar_t*>(combined), 0);

            return count;
        });

        int objectsBefore = future.get();

        nlohmann::json result;
        result["command"]        = command;
        result["started"]        = true;
        result["objects_before"] = objectsBefore;
        result["note"]           = "Poll /command/prompt to get actual prompt after ~100ms";

        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error starting command: ") + ex.what());
    }
}

// ─── POST /command/send ─────────────────────────────────────────────

void HandleCommandInput(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (!req.body.empty())
    {
        body = nlohmann::json::parse(req.body, nullptr, false);
        if (body.is_discarded() || !body.is_object())
        {
            CRookServer::SendError(res, "Invalid JSON body");
            return;
        }
    }

    if (!body.contains("input") || !body["input"].is_string())
    {
        CRookServer::SendError(res, "Missing required field: input");
        return;
    }

    std::string input = body["input"].get<std::string>();

    try
    {
        auto future = CMainThreadDispatcher::Instance().Dispatch([&]() -> int {
            CRhinoDoc* pDoc = GetDocument();
            unsigned int docSn = pDoc ? pDoc->RuntimeSerialNumber() : 0;
            int count = 0;
            if (pDoc) {
                CRhinoObjectIterator iter(*pDoc,
                    CRhinoObjectIterator::normal_or_locked_objects,
                    CRhinoObjectIterator::active_objects);
                for (const CRhinoObject* obj = iter.First(); obj; obj = iter.Next())
                    ++count;
            }

            ON_wString wInput = Utf8ToWide(input);
            wInput += L"\n";
            RhinoApp().RunScript(docSn, static_cast<const wchar_t*>(wInput), 0);

            return count;
        });

        int objectsBefore = future.get();

        nlohmann::json result;
        result["input_sent"]     = input;
        result["sent"]           = true;
        result["objects_before"] = objectsBefore;
        result["note"]           = "Poll /command/prompt to get actual prompt after ~100ms";

        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error sending input: ") + ex.what());
    }
}

// ─── POST /command/cancel ───────────────────────────────────────────

void HandleCommandCancel(const httplib::Request& /*req*/, httplib::Response& res)
{
    try
    {
        // C24 fix: RunScript is asynchronous — reading the prompt immediately
        // after _Cancel returns the OLD prompt because the cancel hasn't
        // processed yet. We send the cancel, wait briefly, then re-read.
        auto future = CMainThreadDispatcher::Instance().Dispatch([&]() {
            CRhinoDoc* pDoc = GetDocument();
            unsigned int docSn = pDoc ? pDoc->RuntimeSerialNumber() : 0;

            ON_wString cancelScript(L"_Cancel\n");
            RhinoApp().RunScript(docSn, static_cast<const wchar_t*>(cancelScript), 0);
        });
        future.get();

        // Allow Rhino's message loop to process the cancel
        ::Sleep(100);

        std::string prompt = ReadPromptOnMain();

        nlohmann::json result;
        result["cancelled"] = true;
        result["prompt"]    = prompt;

        CRookServer::SendSuccess(res, result);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, std::string("Error cancelling: ") + ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
