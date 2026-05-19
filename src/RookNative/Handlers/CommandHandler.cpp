// CommandHandler.cpp
//
// POST /command — Run a Rhino scripted command
// POST /execute — Run a Python script

#include "stdafx.h"
#include "Handlers/CommandHandler.h"
#include "Infrastructure/UndoScope.h"
#include "Infrastructure/JsonHelpers.h"
#include "Infrastructure/ObjectDiffTracker.h"
#include "Infrastructure/WriteResult.h"
#include "Models/DocumentHelpers.h"
#include "Threading/MainThreadDispatcher.h"
#include "RookServer.h"

#include <atomic>
#include <chrono>
#include <filesystem>
#include <future>
#include <fstream>
#include <mutex>
#include <sstream>
#include <thread>

namespace fs = std::filesystem;

// Atomic counter for unique temp file names, preventing collisions
// when concurrent /execute requests arrive on different httplib threads.
static std::atomic<uint64_t> s_scriptCounter{0};
static std::mutex s_commandRunMutex;
static std::atomic<bool> s_commandStateUncertain{false};

namespace Rook {
namespace Handlers {
namespace
{
    constexpr auto kCommandRunTimeout = std::chrono::seconds(10);
    constexpr auto kCommandPromptPollInterval = std::chrono::milliseconds(100);
    constexpr auto kCommandPromptPollWindow = std::chrono::seconds(1);
    constexpr auto kCommandPromptDispatchTimeout = std::chrono::milliseconds(250);

    bool WriteUtf8File(const fs::path& path, const std::string& contents)
    {
        std::ofstream ofs(path, std::ios::binary);
        if (!ofs.is_open())
            return false;

        ofs.write(contents.data(), static_cast<std::streamsize>(contents.size()));
        return ofs.good();
    }

    bool TryReadJsonFile(const fs::path& path, nlohmann::json& out)
    {
        std::ifstream ifs(path, std::ios::binary);
        if (!ifs.is_open())
            return false;

        out = nlohmann::json::parse(ifs, nullptr, false);
        return !out.is_discarded();
    }

    std::string EscapePythonString(const std::string& value)
    {
        std::string escaped;
        escaped.reserve(value.size() + 16);

        for (char ch : value)
        {
            switch (ch)
            {
            case '\\':
                escaped += "\\\\";
                break;
            case '\'':
                escaped += "\\'";
                break;
            case '\r':
                escaped += "\\r";
                break;
            case '\n':
                escaped += "\\n";
                break;
            default:
                escaped.push_back(ch);
                break;
            }
        }

        return escaped;
    }

    std::string BuildExecuteWrapperScript(
        const fs::path& codeFile,
        const fs::path& resultFile)
    {
        const std::string codePath =
            EscapePythonString(WideToUtf8(codeFile.generic_wstring().c_str()));
        const std::string resultPath =
            EscapePythonString(WideToUtf8(resultFile.generic_wstring().c_str()));

        std::ostringstream script;
        script
            << "#! python 3\n"
            << "import io\n"
            << "import json\n"
            << "import os\n"
            << "import traceback\n"
            << "from contextlib import redirect_stdout, redirect_stderr\n\n"
            << "CODE_PATH = '" << codePath << "'\n"
            << "RESULT_PATH = '" << resultPath << "'\n\n"
            << "result = {\n"
            << "    'success': True,\n"
            << "    'output': '',\n"
            << "    'stderr': '',\n"
            << "    'error': '',\n"
            << "    'traceback': ''\n"
            << "}\n"
            << "_rook_stdout = io.StringIO()\n"
            << "_rook_stderr = io.StringIO()\n\n"
            << "try:\n"
            << "    with open(CODE_PATH, 'r', encoding='utf-8') as _rook_code_file:\n"
            << "        _rook_code = _rook_code_file.read()\n"
            << "    _rook_globals = {'__name__': '__main__', '__file__': CODE_PATH}\n"
            << "    with redirect_stdout(_rook_stdout), redirect_stderr(_rook_stderr):\n"
            << "        exec(compile(_rook_code, CODE_PATH, 'exec'), _rook_globals, _rook_globals)\n"
            << "except BaseException as _rook_err:\n"
            << "    result['success'] = False\n"
            << "    result['error'] = f'{type(_rook_err).__name__}: {_rook_err}'\n"
            << "    result['traceback'] = traceback.format_exc()\n"
            << "finally:\n"
            << "    result['output'] = _rook_stdout.getvalue()\n"
            << "    result['stderr'] = _rook_stderr.getvalue()\n"
            << "    _rook_dir = os.path.dirname(RESULT_PATH)\n"
            << "    try:\n"
            << "        if _rook_dir:\n"
            << "            os.makedirs(_rook_dir, exist_ok=True)\n"
            << "        with open(RESULT_PATH, 'w', encoding='utf-8') as _rook_result_file:\n"
            << "            json.dump(result, _rook_result_file)\n"
            << "    except Exception:\n"
            << "        pass\n";

        return script.str();
    }

    bool IsInteractivePrompt(const std::string& prompt)
    {
        return !prompt.empty() && prompt.find("Command") == std::string::npos;
    }

    nlohmann::json BuildCommandInteractiveError(
        const std::string& command,
        const std::string& prompt)
    {
        nlohmann::json data;
        data["command"] = command;
        data["executed"] = nullptr;
        data["execution_status"] = "unknown";
        data["execution_may_have_occurred"] = true;
        data["error"] = "Command went interactive after RunScript returned. "
            "Use typed Rook tools or complete a known-safe scripted command.";
        data["waitingFor"] = prompt;
        data["verified"] = false;
        data["state_uncertain"] = true;
        data["cancelled"] = false;
        data["recovery"] = "Rook observed an active Rhino prompt after command execution. "
            "It did not send an automatic cancel because prompt ownership is uncertain. "
            "Inspect the prompt, cancel any active command, then retry with a safe typed "
            "Rook tool or complete scripted command.";
        return data;
    }

    nlohmann::json BuildCommandTimeoutError(const std::string& command)
    {
        nlohmann::json data;
        data["code"] = "native_command_timeout";
        data["command"] = command;
        data["executed"] = nullptr;
        data["execution_status"] = "unknown";
        data["execution_may_have_occurred"] = true;
        data["verified"] = false;
        data["state_uncertain"] = true;
        data["error"] = "Native command execution_blocked: Rhino state is uncertain.";
        data["recovery"] = "This timeout did not unwind the UI-thread command. "
            "Inspect the Rhino command prompt, cancel any active command, then retry "
            "using a safe typed Rook tool or complete scripted command.";
        return data;
    }

    nlohmann::json BuildCommandStateUncertainError(
        const std::string& command,
        const std::string& prompt = "")
    {
        nlohmann::json data;
        data["code"] = "native_command_state_uncertain";
        data["command"] = command;
        data["executed"] = nullptr;
        data["execution_status"] = "unknown";
        data["execution_may_have_occurred"] = true;
        data["verified"] = false;
        data["state_uncertain"] = true;
        data["error"] = "Native command execution is blocked because Rhino state is uncertain.";
        if (!prompt.empty())
            data["waitingFor"] = prompt;
        data["recovery"] = "Inspect the Rhino command prompt and cancel any active command. "
            "Rook will keep refusing /command until it can verify the prompt is idle; "
            "then retry through typed Rook tools or a complete scripted command.";
        return data;
    }

    bool TryReadCommandPrompt(std::string& prompt)
    {
        try
        {
            auto promptFuture = CMainThreadDispatcher::Instance().Dispatch(
                []() -> std::string
            {
                ON_wString currentPrompt;
                RhinoApp().GetCommandPrompt(currentPrompt);
                return WideToUtf8(currentPrompt);
            });

            if (promptFuture.wait_for(kCommandPromptDispatchTimeout) != std::future_status::ready)
                return false;

            prompt = promptFuture.get();
            return true;
        }
        catch (...)
        {
            return false;
        }
    }

    bool PollForInteractivePrompt(std::string& prompt)
    {
        const auto deadline = std::chrono::steady_clock::now() + kCommandPromptPollWindow;

        while (std::chrono::steady_clock::now() < deadline)
        {
            std::this_thread::sleep_for(kCommandPromptPollInterval);

            std::string currentPrompt;
            if (TryReadCommandPrompt(currentPrompt) && IsInteractivePrompt(currentPrompt))
            {
                prompt = currentPrompt;
                return true;
            }
        }

        return false;
    }
}

// ─── POST /command ──────────────────────────────────────────────────

void HandleCommand(const httplib::Request& req, httplib::Response& res)
{
    // Parse body on worker thread
    nlohmann::json body;
    unsigned int docSn = 0;

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

    // Reject control characters — newlines act as command separators in
    // RunScript, enabling command chaining attacks.
    for (unsigned char c : command)
    {
        if (c < 0x20)
        {
            CRookServer::SendError(res, "Command contains invalid control characters");
            return;
        }
    }

    bool echo = body.value("echo", false);
    if (body.contains("documentSerialNumber"))
        docSn = body.value("documentSerialNumber", 0u);

    // Serialize /command lifecycles through the delayed prompt-verification
    // window. Without this, request A could read request B's prompt
    // after A's RunScript returns but before A's worker-side poll completes.
    std::unique_lock<std::mutex> commandRunLock(s_commandRunMutex);

    if (s_commandStateUncertain.load(std::memory_order_acquire))
    {
        std::string prompt;
        if (!TryReadCommandPrompt(prompt) || IsInteractivePrompt(prompt))
        {
            CRookServer::SendErrorData(res, BuildCommandStateUncertainError(command, prompt));
            return;
        }
        s_commandStateUncertain.store(false, std::memory_order_release);
    }

    // No UndoScope here: RunScript creates its own undo records per command.
    // Wrapping in another UndoScope would create unnecessary double-nesting,
    // unlike /execute which runs a script via a command wrapper.
    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, command, echo]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        unsigned int docRuntimeSn = pDoc->RuntimeSerialNumber();

        ON_wString wCommand = Utf8ToWide(command);

        // Snapshot existing object GUIDs to detect new objects
        ObjectDiffTracker tracker(pDoc);

        // Run the scripted command.
        // Note: RunScript returns CRhinoCommand::result, but it's unreliable for
        // multi-part scripted commands — it reports the result of the *last* command
        // in the script, not the overall outcome. We use prompt-based interactive
        // detection instead, which is the same approach as the C# plugin.
        RhinoApp().RunScript(docRuntimeSn,
            static_cast<const wchar_t*>(wCommand),
            echo ? 1 : 0);

        WriteResult wr;
        auto newObjects = tracker.GetNewObjects();

        nlohmann::json objectIds = nlohmann::json::array();
        for (const auto& uuid : newObjects)
            objectIds.push_back(UuidToString(uuid));

        wr.success = true;
        wr.data["command"] = command;
        wr.data["executed"] = true;
        wr.data["objectsCreated"] = static_cast<int>(newObjects.size());
        wr.data["objectIds"] = std::move(objectIds);

        pDoc->Redraw();
        return wr;
    });

    try
    {
        if (future.wait_for(kCommandRunTimeout) != std::future_status::ready)
        {
            s_commandStateUncertain.store(true, std::memory_order_release);
            CRookServer::SendErrorData(res, BuildCommandTimeoutError(command));
            return;
        }

        auto result = future.get();

        std::string interactivePrompt;
        if (PollForInteractivePrompt(interactivePrompt))
        {
            s_commandStateUncertain.store(true, std::memory_order_release);
            CRookServer::SendErrorData(res, BuildCommandInteractiveError(command, interactivePrompt));
            return;
        }

        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

// ─── POST /execute ──────────────────────────────────────────────────

void HandleExecute(const httplib::Request& req, httplib::Response& res)
{
    // Parse body on worker thread
    nlohmann::json body;
    unsigned int docSn = 0;

    if (!req.body.empty())
    {
        body = nlohmann::json::parse(req.body, nullptr, false);
        if (body.is_discarded() || !body.is_object())
        {
            CRookServer::SendError(res, "Invalid JSON body");
            return;
        }
    }

    if (!body.contains("code") || !body["code"].is_string())
    {
        CRookServer::SendError(res, "Missing required field: code");
        return;
    }

    std::string code = body["code"].get<std::string>();
    if (body.contains("documentSerialNumber"))
        docSn = body.value("documentSerialNumber", 0u);

    auto future = CMainThreadDispatcher::Instance().Dispatch(
        [docSn, code]() -> WriteResult
    {
        CRhinoDoc* pDoc = ResolveDoc(docSn);
        UndoScope undo(pDoc, L"Execute Script");
        unsigned int docRuntimeSn = pDoc->RuntimeSerialNumber();

        // Write Python code to a unique temporary file.
        // Uses PID + atomic counter to avoid collisions from concurrent requests.
        fs::path tempDir = fs::temp_directory_path() / "rook";
        fs::create_directories(tempDir);
        uint64_t seq = s_scriptCounter.fetch_add(1);
        fs::path codeFile = tempDir / ("script_" + std::to_string(::GetCurrentProcessId())
            + "_" + std::to_string(seq) + "_code.py");
        fs::path wrapperFile = tempDir / ("script_" + std::to_string(::GetCurrentProcessId())
            + "_" + std::to_string(seq) + "_wrapper.py");
        fs::path resultFile = tempDir / ("script_" + std::to_string(::GetCurrentProcessId())
            + "_" + std::to_string(seq) + "_result.json");

        if (!WriteUtf8File(codeFile, code))
            throw std::runtime_error("Failed to create temporary user script file");

        if (!WriteUtf8File(wrapperFile, BuildExecuteWrapperScript(codeFile, resultFile)))
            throw std::runtime_error("Failed to create temporary script wrapper");

        // Count objects before execution
        ObjectDiffTracker tracker(pDoc);

        // Run the wrapper via Rhino's RunPythonScript command. The wrapper
        // compiles/executes user code and writes a structured result file so
        // syntax/runtime failures come back as JSON instead of Rhino popups.
        std::wstring scriptCmd = L"_-RunPythonScript \"" +
            wrapperFile.wstring() + L"\"";
        RhinoApp().RunScript(docRuntimeSn, scriptCmd.c_str(), 0);

        ON_wString prompt;
        RhinoApp().GetCommandPrompt(prompt);
        const std::string promptStr = WideToUtf8(prompt);
        const bool isInteractive = IsInteractivePrompt(promptStr);
        if (isInteractive)
            RhinoApp().RunScript(docRuntimeSn, L"_Cancel", 0);

        // Count objects after execution
        int objectCountAfter = 0;
        {
            CRhinoObjectIterator it(*pDoc,
                CRhinoObjectIterator::normal_or_locked_objects,
                CRhinoObjectIterator::active_objects);
            for (const CRhinoObject* obj = it.First(); obj; obj = it.Next())
                ++objectCountAfter;
        }

        WriteResult wr;
        auto newObjects = tracker.GetNewObjects();
        nlohmann::json objectIds = nlohmann::json::array();
        for (const auto& uuid : newObjects)
            objectIds.push_back(UuidToString(uuid));

        wr.data["objectCount"] = objectCountAfter;
        wr.data["objectsCreated"] = static_cast<int>(newObjects.size());
        wr.data["objectIds"] = std::move(objectIds);

        nlohmann::json execResult;
        const bool hasExecResult = TryReadJsonFile(resultFile, execResult);

        if (hasExecResult)
        {
            wr.data["output"] = execResult.value("output", "");
            wr.data["stderr"] = execResult.value("stderr", "");

            if (!execResult.value("success", false))
            {
                wr.success = false;
                wr.data["error"] = execResult.value("error", "Script execution failed");

                const std::string traceback = execResult.value("traceback", "");
                if (!traceback.empty())
                    wr.data["traceback"] = traceback;
            }
            else if (isInteractive)
            {
                wr.success = false;
                wr.data["error"] = "Script requested interactive Rhino input and did not complete.";
                wr.data["waitingFor"] = promptStr;
            }
            else
            {
                wr.success = true;
            }
        }
        else
        {
            wr.success = false;
            wr.data["output"] = "";
            wr.data["stderr"] = "";
            wr.data["error"] = isInteractive
                ? "Script requested interactive Rhino input and did not complete."
                : "Script execution did not produce a result payload. Rhino likely aborted the script before completion.";

            if (isInteractive)
                wr.data["waitingFor"] = promptStr;
        }

        try { fs::remove(codeFile); } catch (...) {}
        try { fs::remove(wrapperFile); } catch (...) {}
        try { fs::remove(resultFile); } catch (...) {}

        pDoc->Redraw();
        return wr;
    });

    try
    {
        auto result = future.get();
        if (result.success)
            CRookServer::SendSuccess(res, result.data);
        else
            CRookServer::SendErrorData(res, result.data.empty() ? nlohmann::json(result.error) : result.data);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(res, ex.what());
    }
}

} // namespace Handlers
} // namespace Rook
