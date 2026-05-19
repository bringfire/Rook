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

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cctype>
#include <cstdlib>
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
static std::atomic<bool> s_testHookPromptUnknown{false};
static std::atomic<bool> s_testHookCommandTimeout{false};
static std::atomic<bool> s_testHookCancelPromptActive{false};
static std::atomic<bool> s_testHookPromptPollDelay{false};
static const bool s_runScriptSafetyTestHooksEnabled = []() {
    const char* env = std::getenv("ROOK_ENABLE_RUNSCRIPT_SAFETY_TEST_HOOKS");
    return env != nullptr && std::string(env) == "1";
}();

namespace Rook {
namespace Handlers {
namespace
{
    constexpr auto kCommandRunTimeout = std::chrono::seconds(10);
    constexpr auto kCommandPromptPollInterval = std::chrono::milliseconds(100);
    constexpr auto kCommandPromptPollWindow = std::chrono::seconds(3);
    constexpr auto kCommandPromptDispatchTimeout = std::chrono::milliseconds(250);

    enum class CommandPromptState
    {
        Idle,
        Active,
        Unknown
    };

    struct CommandPromptProbe
    {
        CommandPromptState state = CommandPromptState::Unknown;
        std::string prompt;
    };

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

    bool IsIdleCommandPrompt(const std::string& prompt)
    {
        return prompt.empty() || prompt == "Command" || prompt.rfind("Command:", 0) == 0;
    }

    bool IsInteractivePrompt(const std::string& prompt)
    {
        return !IsIdleCommandPrompt(prompt);
    }

    std::atomic<bool>* GetRunScriptSafetyTestHookFlag(const std::string& hookName)
    {
        if (hookName == "prompt_unknown")
            return &s_testHookPromptUnknown;
        if (hookName == "command_timeout")
            return &s_testHookCommandTimeout;
        if (hookName == "cancel_prompt_active")
            return &s_testHookCancelPromptActive;
        if (hookName == "prompt_poll_delay")
            return &s_testHookPromptPollDelay;
        return nullptr;
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
        data["recovery"] = "Inspect the Rhino command prompt and call /command/cancel "
            "to complete explicit recovery. Rook will keep refusing /command while "
            "state is uncertain; then retry through typed Rook tools or a complete "
            "scripted command.";
        return data;
    }

    nlohmann::json BuildCommandPromptUnknownError(const std::string& command)
    {
        nlohmann::json data = BuildCommandStateUncertainError(command);
        data["code"] = "native_command_prompt_unknown";
        data["error"] = "Native command execution verification is blocked because "
            "Rook could not read Rhino's command prompt after RunScript.";
        data["recovery"] = "Prompt verification was inconclusive, so execution is "
            "unverified and Rhino state is uncertain. Inspect Rhino, call "
            "/command/cancel if needed, then retry through typed Rook tools or a "
            "complete scripted command.";
        return data;
    }

    std::string TrimAscii(const std::string& value)
    {
        auto begin = std::find_if_not(value.begin(), value.end(), [](unsigned char ch) {
            return std::isspace(ch) != 0;
        });
        auto end = std::find_if_not(value.rbegin(), value.rend(), [](unsigned char ch) {
            return std::isspace(ch) != 0;
        }).base();
        if (begin >= end)
            return "";
        return std::string(begin, end);
    }

    std::string CanonicalCommandToken(std::string token)
    {
        while (!token.empty() && (token.front() == '_' || token.front() == '-' || token.front() == '!'))
            token.erase(token.begin());

        std::transform(token.begin(), token.end(), token.begin(), [](unsigned char ch) {
            return static_cast<char>(std::tolower(ch));
        });
        return token;
    }

    bool IsKnownSafeBareNoEffectCommand(const std::string& token)
    {
        return token == "selnone";
    }

    bool IsUnsafeBareNoEffectCommand(const std::string& command, int objectsCreated)
    {
        if (objectsCreated != 0)
            return false;

        const std::string trimmed = TrimAscii(command);
        if (trimmed.empty())
            return false;

        if (trimmed.find_first_of(" \t\r\n") != std::string::npos)
            return false;

        return !IsKnownSafeBareNoEffectCommand(CanonicalCommandToken(trimmed));
    }

    nlohmann::json BuildCommandBareNoEffectUnverifiedError(const std::string& command)
    {
        nlohmann::json data = BuildCommandStateUncertainError(command);
        data["code"] = "native_command_bare_no_effect_unverified";
        data["waitingFor"] = "explicit non-interactive command arguments";
        data["error"] = "Native command execution could not verify that this bare "
            "command completed non-interactively or produced an effect.";
        data["recovery"] = "Bare command names can enter Rhino prompt state after "
            "RunScript returns. Rook quarantined command execution; call "
            "/command/cancel to verify idle before continuing.";
        return data;
    }

    CommandPromptProbe TryReadCommandPrompt()
    {
        if (ConsumeRunScriptSafetyTestHook("prompt_unknown"))
            return {CommandPromptState::Unknown, ""};

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
                return {CommandPromptState::Unknown, ""};

            const std::string prompt = promptFuture.get();
            return {
                IsIdleCommandPrompt(prompt) ? CommandPromptState::Idle : CommandPromptState::Active,
                prompt,
            };
        }
        catch (...)
        {
            return {CommandPromptState::Unknown, ""};
        }
    }

    CommandPromptProbe PollForCommandPromptState()
    {
        if (ConsumeRunScriptSafetyTestHook("prompt_poll_delay"))
            std::this_thread::sleep_for(std::chrono::milliseconds(1500));

        const auto deadline = std::chrono::steady_clock::now() + kCommandPromptPollWindow;
        bool sawIdle = false;
        bool sawUnknown = false;

        while (std::chrono::steady_clock::now() < deadline)
        {
            std::this_thread::sleep_for(kCommandPromptPollInterval);

            CommandPromptProbe probe = TryReadCommandPrompt();
            if (probe.state == CommandPromptState::Active)
                return probe;
            if (probe.state == CommandPromptState::Unknown)
                sawUnknown = true;
            else
                sawIdle = true;
        }

        if (sawUnknown)
            return {CommandPromptState::Unknown, ""};
        if (sawIdle)
            return {CommandPromptState::Idle, ""};
        return {CommandPromptState::Unknown, ""};
    }
}

bool RunScriptSafetyTestHooksEnabled()
{
    return s_runScriptSafetyTestHooksEnabled;
}

bool ConsumeRunScriptSafetyTestHook(const char* hookName)
{
    if (!RunScriptSafetyTestHooksEnabled() || hookName == nullptr)
        return false;

    std::atomic<bool>* flag = GetRunScriptSafetyTestHookFlag(hookName);
    return flag != nullptr && flag->exchange(false, std::memory_order_acq_rel);
}

std::unique_lock<std::mutex> AcquireCommandRunLifecycleLock()
{
    return std::unique_lock<std::mutex>(s_commandRunMutex);
}

void ClearCommandStateUncertain()
{
    s_commandStateUncertain.store(false, std::memory_order_release);
}

void HandleRunScriptSafetyTestHook(const httplib::Request& req, httplib::Response& res)
{
    if (!RunScriptSafetyTestHooksEnabled())
    {
        nlohmann::json data;
        data["error"] = "runscript_safety_test_hooks_disabled";
        data["verified"] = false;
        CRookServer::SendErrorData(res, data);
        return;
    }

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

    if (!body.contains("hook") || !body["hook"].is_string())
    {
        CRookServer::SendError(res, "Missing required field: hook");
        return;
    }

    const std::string hookName = body["hook"].get<std::string>();
    if (hookName == "reset")
    {
        s_testHookPromptUnknown.store(false, std::memory_order_release);
        s_testHookCommandTimeout.store(false, std::memory_order_release);
        s_testHookCancelPromptActive.store(false, std::memory_order_release);
        s_testHookPromptPollDelay.store(false, std::memory_order_release);

        nlohmann::json data;
        data["reset"] = true;
        CRookServer::SendSuccess(res, data);
        return;
    }

    std::atomic<bool>* flag = GetRunScriptSafetyTestHookFlag(hookName);
    if (flag == nullptr)
    {
        CRookServer::SendError(res, "Unknown hook");
        return;
    }

    if (!body.contains("enabled") || !body["enabled"].is_boolean())
    {
        CRookServer::SendError(res, "Missing required field: enabled");
        return;
    }

    const bool enabled = body["enabled"].get<bool>();
    flag->store(enabled, std::memory_order_release);

    nlohmann::json data;
    data["hook"] = hookName;
    data["enabled"] = enabled;
    data["one_shot"] = true;
    CRookServer::SendSuccess(res, data);
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
    auto commandRunLock = AcquireCommandRunLifecycleLock();

    if (s_commandStateUncertain.load(std::memory_order_acquire))
    {
        CommandPromptProbe probe = TryReadCommandPrompt();
        CRookServer::SendErrorData(res, BuildCommandStateUncertainError(command, probe.prompt));
        return;
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
        if (ConsumeRunScriptSafetyTestHook("command_timeout")
            || future.wait_for(kCommandRunTimeout) != std::future_status::ready)
        {
            s_commandStateUncertain.store(true, std::memory_order_release);
            CRookServer::SendErrorData(res, BuildCommandTimeoutError(command));
            return;
        }

        auto result = future.get();

        CommandPromptProbe promptProbe = PollForCommandPromptState();
        if (promptProbe.state == CommandPromptState::Active)
        {
            s_commandStateUncertain.store(true, std::memory_order_release);
            CRookServer::SendErrorData(res, BuildCommandInteractiveError(command, promptProbe.prompt));
            return;
        }

        if (promptProbe.state == CommandPromptState::Unknown)
        {
            s_commandStateUncertain.store(true, std::memory_order_release);
            CRookServer::SendErrorData(res, BuildCommandPromptUnknownError(command));
            return;
        }

        int objectsCreated = 0;
        if (result.success
            && result.data.contains("objectsCreated")
            && result.data["objectsCreated"].is_number_integer())
        {
            objectsCreated = result.data["objectsCreated"].get<int>();
        }

        if (result.success && IsUnsafeBareNoEffectCommand(command, objectsCreated))
        {
            s_commandStateUncertain.store(true, std::memory_order_release);
            CRookServer::SendErrorData(res, BuildCommandBareNoEffectUnverifiedError(command));
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
