// RookNativePlugin.cpp
//
// CRookNativePlugin implementation.
// Phase 0: Minimal plugin that loads in Rhino and proves the toolchain works.
// Phase 1+: Will start the HTTP server and begin handling requests.

#include "stdafx.h"
#include "RookNativePlugin.h"
#include "Threading/MainThreadDispatcher.h"
#include "SceneGraph/SceneGraph.h"
#include "Interactive/SessionRecorder.h"
#include "Interactive/GumballManager.h"
#include "RookServer.h"
#include "Handlers/GrasshopperProxyHandler.h"
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <thread>

// --- Required DLL Exports (probed via GetProcAddress before plugin loads) ---
//
// Rhino loads C++ plugins in two phases:
//   Phase 1: GetProcAddress for exported C functions — validates SDK version,
//            plugin identity, and developer metadata. If any required field
//            is missing, Rhino refuses to load with a specific error message.
//   Phase 2: Instantiate the CRhinoPlugIn subclass and call OnLoadPlugIn().
//
// These macros each expand to an extern "C" __declspec(dllexport) function.
// Must appear in exactly one .cpp file.

#include "rhinoSdkPlugInDeclare.h"
RHINO_PLUG_IN_DECLARE

// Plugin identity
RHINO_PLUG_IN_NAME(L"RookNative")
RHINO_PLUG_IN_ID(L"A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906")
RHINO_PLUG_IN_VERSION(__DATE__ "  " __TIME__)
RHINO_PLUG_IN_DESCRIPTION(L"RookNative - High-performance Rhino bridge for Claude Code")

// Developer information (all required by CRhinoPlugInInfo::HasRequiredFields)
RHINO_PLUG_IN_DEVELOPER_ORGANIZATION(L"Bringfire")
RHINO_PLUG_IN_DEVELOPER_ADDRESS(L"")
RHINO_PLUG_IN_DEVELOPER_COUNTRY(L"")
RHINO_PLUG_IN_DEVELOPER_PHONE(L"")
RHINO_PLUG_IN_DEVELOPER_FAX(L"")
RHINO_PLUG_IN_DEVELOPER_EMAIL(L"")
RHINO_PLUG_IN_DEVELOPER_WEBSITE(L"https://github.com/bringfire/Rhino_AI")
RHINO_PLUG_IN_UPDATE_URL(L"https://github.com/bringfire/Rhino_AI/releases")

// --- Plugin Identity ---

// IMPORTANT: This GUID must be unique and different from the C# Rook plugin.
// Generated via Python uuid.uuid4() — RFC 4122 v4 compliant.
// {A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906}
static const GUID g_RookNativePlugInId =
{ 0xa38e0e8f, 0xe06e, 0x40d2, { 0xa6, 0xbd, 0x7e, 0xdb, 0xc2, 0xcb, 0x19, 0x06 } };

// Managed companion plug-in identity.
// This remains required for Grasshopper execution, but native now attempts to
// load it automatically so users do not have to manage it manually.
//
// IMPORTANT: The managed plug-in must not be loaded during OnLoadPlugIn().
// Rhino may report the module as loaded, but the managed plug-in's normal
// startup/idle lifecycle does not initialize correctly from that early load
// boundary. We therefore defer the load onto the dispatch queue so it runs
// once native startup has completed and Rhino is back in its normal message
// pump/idle cycle.
static const GUID g_RookManagedPlugInId =
{ 0xb7e4a8c9, 0x1f62, 0x4c7e, { 0x9a, 0x2b, 0x5d, 0x4e, 0x8f, 0x1c, 0x3a, 0x7b } };

static std::atomic<bool> g_stopCompanionLoad{ false };
static std::atomic<DWORD> g_nativeStartupSehCode{ 0 };
static std::thread g_companionLoadThread;
static constexpr DWORD kMsvcCppExceptionCode = 0xE06D7363;
static constexpr const wchar_t* kJackPrivateCanaryNote =
    L"I'd fight a chicken with hands, a real chicken!";

// ---------------------------------------------------------------------------
// Companion activation — pre-registration model
//
// The managed companion must be registered in Rhino's plugin registry BEFORE
// Rhino starts.  Rhino only scans the registry at startup to build its
// in-memory plugin record list.  Runtime self-registration is not supported
// (LoadPlugIn looks up the in-memory list, not the registry).
//
// Registration is handled by:  scripts/register-companion.ps1
// That script must be run once after deploy (before the first Rhino launch).
//
// At runtime, native:
//   1. Sets load protection to "silent" (no confirmation dialog)
//   2. Calls LoadPlugIn(companionGuid, quiet, ignoreFailure)
//   3. Retries up to kMaxRetries times with backoff if Rhino isn't ready yet
//   4. If all retries fail, logs a clear message — no crash, GH just unavailable
// ---------------------------------------------------------------------------

// Retry budget: kInitialDelayMs before the companion-load loop starts, then a
// bounded wall-clock window for command-active recent-file startup to become
// safe. kLoadRetries counts only real LoadPlugIn failures, not dispatcher busy
// deferrals while Rhino is command-active.
static constexpr int kInitialDelayMs = 2000;
static constexpr int kCompanionLoadStartupWindowMs = 120000;
static constexpr int kLoadRetries    = 3;      // actual LoadPlugIn failures
static constexpr int kLoadRetryMs    = 2000;   // after actual LoadPlugIn failure
static constexpr int kNotSafeRetryMs = 500;    // while command-active / dispatcher busy
static constexpr int kBridgeRetries  = 10;     // bridge-ready polls after load
static constexpr int kBridgePollMs   = 500;    // between bridge polls
static constexpr int kDispatchPollMs = 100;    // shutdown-aware wait slice

enum class CompanionLoadAttemptResult
{
    Loaded,
    AlreadyReady,
    NotSafeYet,
    LoadFailed,
    DispatcherStopping
};

struct CompanionLoadAttempt
{
    CompanionLoadAttemptResult result = CompanionLoadAttemptResult::NotSafeYet;
    std::wstring diagnostic;
};

template<typename T>
static bool WaitForFutureOrStop(std::future<T>& future)
{
    while (future.wait_for(std::chrono::milliseconds(kDispatchPollMs)) != std::future_status::ready)
    {
        if (g_stopCompanionLoad.load())
            return false;
    }

    return !g_stopCompanionLoad.load();
}

static bool ContainsText(const std::string& value, const char* needle)
{
    return value.find(needle) != std::string::npos;
}

static std::wstring WidenAscii(const std::string& value)
{
    return std::wstring(value.begin(), value.end());
}

static CompanionLoadAttempt ClassifyCompanionLoadException(const std::exception& ex)
{
    const std::string message = ex.what() ? ex.what() : "";

    // Coupled to CMainThreadDispatcher's deterministic busy exception. Keep
    // this match local so command-active cancellation remains a deferral for
    // companion activation, not a terminal startup failure.
    if (ContainsText(message, "RookNative dispatcher is busy: Rhino command is active"))
    {
        return {
            CompanionLoadAttemptResult::NotSafeYet,
            L"managed companion load deferred; dispatcher busy: Rhino command is active"
        };
    }

    if (ContainsText(message, "dispatcher is not running"))
        return { CompanionLoadAttemptResult::DispatcherStopping, L"" };

    if (g_stopCompanionLoad.load())
        return { CompanionLoadAttemptResult::DispatcherStopping, L"" };

    return {
        CompanionLoadAttemptResult::NotSafeYet,
        L"managed companion load deferred; unexpected exception: " + WidenAscii(message)
    };
}

static std::filesystem::path ResolveRookDiscoveryDiagnosticRoot()
{
    wchar_t localAppData[MAX_PATH] = {};
    const DWORD length = ::GetEnvironmentVariableW(L"LOCALAPPDATA", localAppData, MAX_PATH);

    std::filesystem::path root = (length > 0 && length < MAX_PATH)
        ? std::filesystem::path(localAppData)
        : std::filesystem::temp_directory_path();

    root /= L"Rook";
    root /= L"discovery";

    std::error_code error;
    std::filesystem::create_directories(root, error);
    return root;
}

static std::filesystem::path ResolveCompanionLoadDiagnosticPath()
{
    return ResolveRookDiscoveryDiagnosticRoot()
        / (L"companion-load-" + std::to_wstring(::GetCurrentProcessId()) + L".log");
}

static void WriteDiagnosticLine(
    const std::filesystem::path& path,
    const wchar_t* area,
    const std::wstring& message)
{
    try
    {
        SYSTEMTIME now{};
        ::GetSystemTime(&now);

        std::wstringstream line;
        line
            << std::setfill(L'0')
            << now.wYear << L"-" << std::setw(2) << now.wMonth << L"-" << std::setw(2) << now.wDay
            << L"T" << std::setw(2) << now.wHour << L":" << std::setw(2) << now.wMinute
            << L":" << std::setw(2) << now.wSecond << L"." << std::setw(3) << now.wMilliseconds
            << L"Z pid=" << ::GetCurrentProcessId();

        const std::wstring debugLine = L"RookNative: " + std::wstring(area) + L": " + message + L"\n";
        ::OutputDebugStringW(debugLine.c_str());

        std::wofstream log(path, std::ios::app);
        if (log)
            log << line.str() << L" RookNative: " << area << L": " << message << std::endl;
    }
    catch (...)
    {
    }
}

static void WriteCompanionLoadDiagnostic(const std::wstring& message)
{
    try
    {
        WriteDiagnosticLine(ResolveCompanionLoadDiagnosticPath(), L"companion-load", message);
    }
    catch (...)
    {
    }
}

static void OutputNativeStartupDebugLine(const wchar_t* message)
{
    wchar_t debugLine[1024] = {};
    swprintf_s(
        debugLine,
        L"RookNative: native-startup: %ls\n",
        message != nullptr ? message : L"");
    ::OutputDebugStringW(debugLine);
}

static bool AppendPathSegment(wchar_t* path, size_t pathCount, const wchar_t* segment)
{
    const size_t length = wcslen(path);
    if (length > 0 && path[length - 1] != L'\\' && path[length - 1] != L'/')
    {
        if (wcscat_s(path, pathCount, L"\\") != 0)
            return false;
    }

    return wcscat_s(path, pathCount, segment) == 0;
}

static bool BuildNativeStartupDiagnosticPath(wchar_t* path, size_t pathCount)
{
    wchar_t root[MAX_PATH] = {};
    DWORD length = ::GetEnvironmentVariableW(L"LOCALAPPDATA", root, MAX_PATH);
    if (length == 0 || length >= MAX_PATH)
    {
        length = ::GetTempPathW(MAX_PATH, root);
        if (length == 0 || length >= MAX_PATH)
            return false;
    }

    if (wcscpy_s(path, pathCount, root) != 0)
        return false;

    if (!AppendPathSegment(path, pathCount, L"Rook"))
        return false;
    ::CreateDirectoryW(path, nullptr);

    if (!AppendPathSegment(path, pathCount, L"discovery"))
        return false;
    ::CreateDirectoryW(path, nullptr);

    wchar_t fileName[80] = {};
    swprintf_s(fileName, L"native-startup-%lu.log", ::GetCurrentProcessId());
    return AppendPathSegment(path, pathCount, fileName);
}

static void AppendNativeStartupDiagnosticFileLine(const wchar_t* message)
{
    wchar_t path[MAX_PATH] = {};
    if (!BuildNativeStartupDiagnosticPath(path, _countof(path)))
        return;

    HANDLE file = ::CreateFileW(
        path,
        FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        nullptr,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        nullptr);
    if (file == INVALID_HANDLE_VALUE)
        return;

    SYSTEMTIME now{};
    ::GetSystemTime(&now);

    wchar_t wideLine[2048] = {};
    swprintf_s(
        wideLine,
        L"%04u-%02u-%02uT%02u:%02u:%02u.%03uZ pid=%lu RookNative: native-startup: %ls\r\n",
        now.wYear,
        now.wMonth,
        now.wDay,
        now.wHour,
        now.wMinute,
        now.wSecond,
        now.wMilliseconds,
        ::GetCurrentProcessId(),
        message != nullptr ? message : L"");

    char utf8Line[4096] = {};
    const int bytes = ::WideCharToMultiByte(
        CP_UTF8,
        0,
        wideLine,
        -1,
        utf8Line,
        static_cast<int>(_countof(utf8Line)),
        nullptr,
        nullptr);
    if (bytes > 1)
    {
        DWORD written = 0;
        ::WriteFile(file, utf8Line, static_cast<DWORD>(bytes - 1), &written, nullptr);
    }

    ::CloseHandle(file);
}

static void TraceNativeStartupDiagnostic(const wchar_t* message)
{
    __try
    {
        OutputNativeStartupDebugLine(message);
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
    }
}

static void TraceNativeStartupDiagnostic(const std::wstring& message)
{
    TraceNativeStartupDiagnostic(message.c_str());
}

static void CopyWideTruncated(wchar_t* destination, size_t destinationCount, const wchar_t* source)
{
    if (destination == nullptr || destinationCount == 0)
        return;

    size_t index = 0;
    if (source != nullptr)
    {
        while (source[index] != L'\0' && index + 1 < destinationCount)
        {
            destination[index] = source[index];
            ++index;
        }
    }
    destination[index] = L'\0';
}

static void AppendWideTruncated(wchar_t* destination, size_t destinationCount, const wchar_t* suffix)
{
    if (destination == nullptr || destinationCount == 0 || suffix == nullptr)
        return;

    size_t index = 0;
    while (index < destinationCount && destination[index] != L'\0')
        ++index;
    if (index >= destinationCount)
        return;

    size_t suffixIndex = 0;
    while (suffix[suffixIndex] != L'\0' && index + 1 < destinationCount)
    {
        destination[index] = suffix[suffixIndex];
        ++index;
        ++suffixIndex;
    }
    destination[index] = L'\0';
}

static void WriteNativeStartupDiagnostic(const wchar_t* message)
{
    wchar_t durableMessage[1536] = {};
    CopyWideTruncated(durableMessage, _countof(durableMessage), message);
    if (wcsstr(durableMessage, kJackPrivateCanaryNote) == nullptr)
    {
        AppendWideTruncated(durableMessage, _countof(durableMessage), L"; jack-private-canary=\"");
        AppendWideTruncated(durableMessage, _countof(durableMessage), kJackPrivateCanaryNote);
        AppendWideTruncated(durableMessage, _countof(durableMessage), L"\"");
    }

    __try
    {
        OutputNativeStartupDebugLine(durableMessage);
        AppendNativeStartupDiagnosticFileLine(durableMessage);
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
    }
}

static void WriteNativeStartupDiagnostic(const std::wstring& message)
{
    WriteNativeStartupDiagnostic(message.c_str());
}

static std::wstring DispatcherStartupBreadcrumbText()
{
    return CMainThreadDispatcher::StartupBreadcrumbName(
        CMainThreadDispatcher::GetStartupBreadcrumb());
}

static std::wstring DispatcherStartupBreadcrumbSuffix()
{
    return L"; breadcrumb=" + DispatcherStartupBreadcrumbText();
}

static std::wstring DispatcherStartupSetWindowSubclassSuffix()
{
    switch (CMainThreadDispatcher::GetStartupSetWindowSubclassStatus())
    {
    case CMainThreadDispatcher::StartupSubclassStatus::NotAttempted:
        return L"; set-window-subclass=not-attempted";
    case CMainThreadDispatcher::StartupSubclassStatus::Installed:
        return L"; set-window-subclass=installed";
    case CMainThreadDispatcher::StartupSubclassStatus::Failed:
    {
        const DWORD error = CMainThreadDispatcher::GetStartupSetWindowSubclassError();
        wchar_t message[96] = {};
        swprintf_s(message, L"; set-window-subclass=failed GetLastError=%lu", error);
        return message;
    }
    default:
        return L"; set-window-subclass=unknown";
    }
}

static void FormatHex32Buffer(DWORD value, wchar_t* buffer, size_t bufferCount)
{
    swprintf_s(buffer, bufferCount, L"0x%08lX", value);
}

static void WriteDispatcherNativeStartupFailure(DWORD code)
{
    wchar_t codeText[16] = {};
    FormatHex32Buffer(code, codeText, _countof(codeText));

    wchar_t message[512] = {};
    swprintf_s(
        message,
        L"dispatcher.start: failed with native exception %ls; breadcrumb=%ls",
        codeText,
        CMainThreadDispatcher::StartupBreadcrumbName(
            CMainThreadDispatcher::GetStartupBreadcrumb()));
    WriteNativeStartupDiagnostic(message);
}

static void WriteDispatcherCleanupNativeFailure(DWORD code)
{
    wchar_t codeText[16] = {};
    FormatHex32Buffer(code, codeText, _countof(codeText));

    wchar_t message[512] = {};
    swprintf_s(
        message,
        L"startup cleanup dispatcher: trapped native exception %ls; breadcrumb=%ls",
        codeText,
        CMainThreadDispatcher::StartupBreadcrumbName(
            CMainThreadDispatcher::GetStartupBreadcrumb()));
    WriteNativeStartupDiagnostic(message);
}

static void WriteNativeStartupSuccess()
{
    WriteNativeStartupDiagnostic(
        L"OnLoadPlugIn succeeded; dispatcher breadcrumb="
        + DispatcherStartupBreadcrumbText()
        + DispatcherStartupSetWindowSubclassSuffix());
}

static void WriteNativeStartupDispatcherSuccess()
{
    WriteNativeStartupDiagnostic(
        L"dispatcher.start: succeeded"
        + DispatcherStartupBreadcrumbSuffix()
        + DispatcherStartupSetWindowSubclassSuffix());
}

static void WriteNativeStartupDispatcherCleanupSuccess()
{
    WriteNativeStartupDiagnostic(
        L"startup cleanup dispatcher: done; breadcrumb="
        + DispatcherStartupBreadcrumbText());
}

static void WriteNativeStartupDispatcherCppFailure(const wchar_t* prefix, const std::wstring& detail)
{
    try
    {
        WriteNativeStartupDiagnostic(prefix + detail + DispatcherStartupBreadcrumbSuffix());
    }
    catch (...)
    {
    }
}

static std::wstring WidenExceptionMessage(const std::exception& ex)
{
    return WidenAscii(ex.what() ? ex.what() : "");
}

static CompanionLoadAttempt AttemptCompanionLoadOnMainThread()
{
    if (g_stopCompanionLoad.load())
        return { CompanionLoadAttemptResult::DispatcherStopping, L"" };

    if (Rook::Handlers::HasGrasshopperBridgeRegistration())
        return { CompanionLoadAttemptResult::AlreadyReady, L"" };

    try
    {
        auto scheduled = CMainThreadDispatcher::Instance().Dispatch([]() -> CompanionLoadAttemptResult
        {
            if (Rook::Handlers::HasGrasshopperBridgeRegistration())
                return CompanionLoadAttemptResult::AlreadyReady;

            CRhinoPlugIn::SaveLoadProtectionToRegistry(g_RookManagedPlugInId, 1);
            if (CRhinoPlugIn::LoadPlugIn(g_RookManagedPlugInId, true, true) >= 0)
                return CompanionLoadAttemptResult::Loaded;

            return CompanionLoadAttemptResult::LoadFailed;
        });

        if (!WaitForFutureOrStop(scheduled))
            return { CompanionLoadAttemptResult::DispatcherStopping, L"" };

        return { scheduled.get(), L"" };
    }
    catch (const std::exception& ex)
    {
        return ClassifyCompanionLoadException(ex);
    }
    catch (...)
    {
        return g_stopCompanionLoad.load()
            ? CompanionLoadAttempt{ CompanionLoadAttemptResult::DispatcherStopping, L"" }
            : CompanionLoadAttempt{
                CompanionLoadAttemptResult::NotSafeYet,
                L"managed companion load deferred; unexpected non-standard exception"
            };
    }
}

static void StartCompanionLoadDeferred()
{
    g_stopCompanionLoad.store(false);

    if (g_companionLoadThread.joinable())
        g_companionLoadThread.join();

    // Two-phase companion activation:
    //   Phase 1: Call LoadPlugIn until the managed DLL is loaded.
    //   Phase 2: Poll HasGrasshopperBridgeRegistration until the managed
    //            side's idle/startup hooks have registered the GH bridge.
    // Both phases are bounded — we never spin indefinitely.
    g_companionLoadThread = std::thread([]()
    {
        // Wait for Rhino to finish startup and enter idle.
        std::this_thread::sleep_for(std::chrono::milliseconds(kInitialDelayMs));

        // ── Phase 1: Load the managed plugin ──────────────────────────
        bool pluginLoaded = false;
        int loadFailures = 0;
        const auto startupDeadline = std::chrono::steady_clock::now()
            + std::chrono::milliseconds(kCompanionLoadStartupWindowMs);

        while (!g_stopCompanionLoad.load()
            && std::chrono::steady_clock::now() < startupDeadline
            && loadFailures < kLoadRetries)
        {
            const auto attempt = AttemptCompanionLoadOnMainThread();

            switch (attempt.result)
            {
            case CompanionLoadAttemptResult::Loaded:
                pluginLoaded = true;
                WriteCompanionLoadDiagnostic(L"managed companion LoadPlugIn succeeded");
                try
                {
                    CMainThreadDispatcher::Instance().Dispatch([]()
                    {
                        RhinoApp().Print(L"RookNative: managed companion LoadPlugIn succeeded.\n");
                    });
                }
                catch (...) {}
                break;

            case CompanionLoadAttemptResult::AlreadyReady:
                pluginLoaded = true;
                WriteCompanionLoadDiagnostic(L"managed companion already ready");
                break;

            case CompanionLoadAttemptResult::NotSafeYet:
                WriteCompanionLoadDiagnostic(attempt.diagnostic.empty()
                    ? L"managed companion load deferred; reason unavailable"
                    : attempt.diagnostic);
                std::this_thread::sleep_for(std::chrono::milliseconds(kNotSafeRetryMs));
                continue;

            case CompanionLoadAttemptResult::LoadFailed:
                ++loadFailures;
                WriteCompanionLoadDiagnostic(
                    L"managed companion LoadPlugIn attempt " + std::to_wstring(loadFailures) + L" failed");
                try
                {
                    CMainThreadDispatcher::Instance().Dispatch([loadFailures]()
                    {
                        RhinoApp().Print(
                            L"RookNative: managed companion LoadPlugIn attempt %d failed.\n",
                            loadFailures);
                    });
                }
                catch (...) {}
                if (loadFailures < kLoadRetries)
                    std::this_thread::sleep_for(std::chrono::milliseconds(kLoadRetryMs));
                continue;

            case CompanionLoadAttemptResult::DispatcherStopping:
                return;
            }

            if (pluginLoaded)
                break;
        }

        if (!pluginLoaded)
        {
            WriteCompanionLoadDiagnostic(
                L"managed companion startup window expired or LoadPlugIn failed; actual failures "
                + std::to_wstring(loadFailures) + L" of " + std::to_wstring(kLoadRetries));
            try
            {
                CMainThreadDispatcher::Instance().Dispatch([loadFailures]()
                {
                    RhinoApp().Print(
                        L"RookNative: managed companion startup window expired or LoadPlugIn failed.\n"
                        L"  Actual LoadPlugIn failures: %d of %d.\n"
                        L"  GH execution is unavailable until the companion loads.\n",
                        loadFailures,
                        kLoadRetries);
                });
            }
            catch (...) {}
            return;
        }

        // ── Phase 2: Wait for GH bridge registration ──────────────────
        // LoadPlugIn succeeded, but the managed plugin initializes
        // asynchronously (idle hooks, startup retries). Poll until the
        // bridge callbacks are registered.

        for (int poll = 0; poll < kBridgeRetries; ++poll)
        {
            if (g_stopCompanionLoad.load())
                return;

            if (Rook::Handlers::HasGrasshopperBridgeRegistration())
            {
                try
                {
                    CMainThreadDispatcher::Instance().Dispatch([]()
                    {
                        RhinoApp().Print(L"RookNative: managed companion loaded and GH bridge ready.\n");
                    });
                }
                catch (...) {}
                return;
            }

            std::this_thread::sleep_for(std::chrono::milliseconds(kBridgePollMs));
        }

        // The managed companion now defers substantial startup until Rhino is
        // quiescent. During slow document opens the bridge may register after
        // this bounded native poll window, so this is informational.
        try
        {
            CMainThreadDispatcher::Instance().Dispatch([]()
            {
                RhinoApp().Print(
                    L"RookNative: managed companion loaded; GH bridge registration is deferred until Rhino is idle.\n"
                    L"  GH execution will be unavailable until the bridge registers.\n");
            });
        }
        catch (...) {}
    });
}

static void StopCompanionLoad()
{
    g_stopCompanionLoad.store(true);
    if (g_companionLoadThread.joinable())
        g_companionLoadThread.join();
}

static int CaptureNativeStartupSehException(EXCEPTION_POINTERS* exceptionInfo)
{
    const DWORD code = exceptionInfo && exceptionInfo->ExceptionRecord
        ? exceptionInfo->ExceptionRecord->ExceptionCode
        : 0;

    if (code == kMsvcCppExceptionCode
        || code == EXCEPTION_BREAKPOINT
        || code == EXCEPTION_SINGLE_STEP)
    {
        return EXCEPTION_CONTINUE_SEARCH;
    }

    g_nativeStartupSehCode.store(code, std::memory_order_release);
    return EXCEPTION_EXECUTE_HANDLER;
}

static BOOL StartDispatcherWithSehGuard(const ON_UUID* pluginId, CMainThreadDispatcher** dispatcherOut)
{
    __try
    {
        CMainThreadDispatcher::SetStartupBreadcrumb(
            CMainThreadDispatcher::StartupBreadcrumb::InstanceRequested);
        CMainThreadDispatcher* dispatcher = &CMainThreadDispatcher::Instance();
        CMainThreadDispatcher::SetStartupBreadcrumb(
            CMainThreadDispatcher::StartupBreadcrumb::InstanceResolved);
        if (dispatcherOut != nullptr)
            *dispatcherOut = dispatcher;
        if (pluginId == nullptr)
            return FALSE;
        dispatcher->Start(*pluginId);
        return TRUE;
    }
    __except (CaptureNativeStartupSehException(GetExceptionInformation()))
    {
        return FALSE;
    }
}

static BOOL StopDispatcherWithSehGuard(CMainThreadDispatcher* dispatcher)
{
    __try
    {
        if (dispatcher != nullptr)
            dispatcher->Stop();
        return TRUE;
    }
    __except (CaptureNativeStartupSehException(GetExceptionInformation()))
    {
        return FALSE;
    }
}

static void StopDispatcherAfterStartupFailure(CMainThreadDispatcher* dispatcher)
{
    if (dispatcher == nullptr)
        return;

    TraceNativeStartupDiagnostic(L"startup cleanup dispatcher: begin");
    g_nativeStartupSehCode.store(0, std::memory_order_release);
    if (StopDispatcherWithSehGuard(dispatcher))
    {
        WriteNativeStartupDispatcherCleanupSuccess();
    }
    else
    {
        WriteDispatcherCleanupNativeFailure(g_nativeStartupSehCode.load(std::memory_order_acquire));
    }
}

static BOOL StartDispatcherForPluginLoad(ON_UUID pluginId)
{
    TraceNativeStartupDiagnostic(L"dispatcher.start: begin");
    CMainThreadDispatcher* dispatcher = nullptr;
    g_nativeStartupSehCode.store(0, std::memory_order_release);

    try
    {
        if (!StartDispatcherWithSehGuard(&pluginId, &dispatcher))
        {
            WriteDispatcherNativeStartupFailure(g_nativeStartupSehCode.load(std::memory_order_acquire));
            StopDispatcherAfterStartupFailure(dispatcher);
            return FALSE;
        }
        TraceNativeStartupDiagnostic(
            L"dispatcher.start: succeeded"
            + DispatcherStartupBreadcrumbSuffix()
            + DispatcherStartupSetWindowSubclassSuffix());
        WriteNativeStartupDispatcherSuccess();
    }
    catch (const std::exception& ex)
    {
        WriteNativeStartupDispatcherCppFailure(
            L"dispatcher.start: failed with std::exception: ",
            WidenExceptionMessage(ex));
        StopDispatcherAfterStartupFailure(dispatcher);
        return FALSE;
    }
    catch (...)
    {
        WriteNativeStartupDispatcherCppFailure(
            L"dispatcher.start: failed with non-standard exception",
            L"");
        StopDispatcherAfterStartupFailure(dispatcher);
        return FALSE;
    }

    return TRUE;
}

static BOOL StartNativeServicesCore(CRookNativePlugin& plugin)
{
    const bool rhinoInside = plugin.IsRhinoInside();
    TraceNativeStartupDiagnostic(
        L"OnLoadPlugIn begin; version "
        + std::wstring(static_cast<const wchar_t*>(plugin.PlugInVersion()))
        + (rhinoInside ? L"; Rhino.Inside=true" : L"; Rhino.Inside=false"));

    if (rhinoInside)
    {
        RhinoApp().Print(
            L"RookNative %ls: Rhino.Inside mode detected. "
            L"Interactive features (gumball, user prompts) may be unavailable.\n",
            static_cast<const wchar_t*>(plugin.PlugInVersion()));
    }

    // Dispatcher startup is the canary boundary for the Rhino/SentinelOne
    // crash report. Keep native SEH handling scoped here; later subsystems
    // retain their normal startup/unload contracts.
    if (!StartDispatcherForPluginLoad(plugin.PlugInID()))
        return FALSE;

    TraceNativeStartupDiagnostic(L"scene-graph.start: begin");
    Rook::CSceneGraph::Instance().Start();
    TraceNativeStartupDiagnostic(L"scene-graph.start: succeeded");

    TraceNativeStartupDiagnostic(L"session-recorder.start: begin");
    Rook::CSessionRecorder::Instance().Start(plugin.PlugInID());
    TraceNativeStartupDiagnostic(L"session-recorder.start: succeeded");

    TraceNativeStartupDiagnostic(L"http-server.start: begin");
    if (CRookServer::Instance().Start())
    {
        TraceNativeStartupDiagnostic(L"http-server.start: succeeded");
        RhinoApp().Print(L"RookNative %ls: HTTP server on port %d\n",
            static_cast<const wchar_t*>(plugin.PlugInVersion()),
            CRookServer::Instance().Port());
    }
    else
    {
        TraceNativeStartupDiagnostic(L"http-server.start: failed; continuing without HTTP listener");
        RhinoApp().Print(L"RookNative %ls: WARNING — HTTP server failed to start\n",
            static_cast<const wchar_t*>(plugin.PlugInVersion()));
    }

    TraceNativeStartupDiagnostic(L"companion-load.start-deferred: begin");
    StartCompanionLoadDeferred();
    TraceNativeStartupDiagnostic(L"companion-load.start-deferred: succeeded");

    WriteNativeStartupSuccess();
    return TRUE;
}

static BOOL StartNativeServices(CRookNativePlugin& plugin)
{
    return StartNativeServicesCore(plugin);
}

// --- Required Rhino SDK Declarations ---

// Rhino C++ plugins require TWO static singletons per DLL:
//   1. CRhinoPlugIn subclass — the Rhino plugin identity (name, GUID, load/unload)
//   2. CWinApp subclass      — MFC DLL module state (InitInstance/ExitInstance)
// Rhino discovers `thePlugIn` via the SDK's DLL export mechanism.
// MFC discovers `theApp` via the CWinApp constructor registering itself globally.
// Both are mandatory — without theApp, MFC resource loading and message routing break.
static CRookNativePlugin thePlugIn;

// --- Plugin Implementation ---

CRookNativePlugin::CRookNativePlugin()
    : m_plugin_version(L"1.5.15")
{
    // The constructor is called before OnLoadPlugIn.
    // Do NOT access Rhino SDK objects here.
}

CRookNativePlugin& CRookNativePlugin::Instance()
{
    return thePlugIn;
}

CRookNativePlugin& RookNativePlugIn()
{
    return CRookNativePlugin::Instance();
}

bool CRookNativePlugin::IsRhinoInside()
{
    return !RhinoApp().StartedAsRhinoExe();
}

const wchar_t* CRookNativePlugin::PlugInName() const
{
    return L"RookNative";
}

const wchar_t* CRookNativePlugin::PlugInVersion() const
{
    return static_cast<const wchar_t*>(m_plugin_version);
}

GUID CRookNativePlugin::PlugInID() const
{
    return g_RookNativePlugInId;
}

CRhinoPlugIn::plugin_load_time CRookNativePlugin::PlugInLoadTime()
{
    return CRhinoPlugIn::plugin_load_time::load_plugin_at_startup;
}

BOOL CRookNativePlugin::OnLoadPlugIn()
{
    AFX_MANAGE_STATE(AfxGetStaticModuleState());
    return StartNativeServices(*this);
}

void CRookNativePlugin::OnUnloadPlugIn()
{
    // Shutdown order is load-bearing.
    //
    // Stop the dispatcher FIRST. Once its m_running is false:
    //   - new Dispatch() calls return a future containing std::runtime_error
    //     (see Dispatch() in MainThreadDispatcher.h)
    //   - in-flight Dispatch(...).get() callers wake via broken_promise from
    //     the discarded packaged_tasks (see Stop() in MainThreadDispatcher.cpp)
    // Both paths cause the calling httplib worker thread to throw out of its
    // handler instead of waiting on the main thread.
    //
    // This unblocks the latent deadlock: in the old order CRookServer::Stop()
    // joined m_server_thread on the main thread, while httplib workers were
    // still blocked in Dispatch(...).get() waiting for the main thread to
    // drain the dispatcher queue. The main thread couldn't drain because it
    // was blocked in the join. By stopping the dispatcher first, those
    // workers fail fast and the join completes cleanly.
    //
    // After the dispatcher is stopped, the rest of teardown runs in the same
    // dependency order as before. None of these steps directly call Dispatch()
    // in their synchronous code path:
    //   - CRookServer::Stop          (no new HTTP requests, joins workers)
    //   - StopCompanionLoad          (joins the companion-load thread)
    //   - ClearGrasshopperBridgeRegistration  (clears C# callback ptrs)
    //   - CGumballManager::Deactivate (removes hooks + conduit + watcher)
    //   - CSessionRecorder::Stop     (unregisters command event watcher)
    //   - CSceneGraph::Stop          (preempted by m_running gating from
    //                                 commits 1f30238c + f2767190)
    CMainThreadDispatcher::Instance().Stop();
    CRookServer::Instance().Stop();
    StopCompanionLoad();
    Rook::Handlers::ClearGrasshopperBridgeRegistration();
    Rook::CGumballManager::Instance().Deactivate();
    Rook::CSessionRecorder::Instance().Stop();
    Rook::CSceneGraph::Instance().Stop();

    RhinoApp().Print(L"RookNative: unloaded.\n");
}

// --- MFC / DLL Support ---

// Required: MFC DLL module state management.
// Every Rhino C++ plugin must be an MFC extension DLL.
class CRookNativeApp : public CWinApp
{
public:
    CRookNativeApp() = default;

    BOOL InitInstance() override
    {
        // MFC extension DLL one-time initialization.
        CWinApp::InitInstance();
        return TRUE;
    }

    int ExitInstance() override
    {
        return CWinApp::ExitInstance();
    }
};

// See comment above thePlugIn — this is the second required singleton.
CRookNativeApp theApp;
