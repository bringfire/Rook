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
static std::thread g_companionLoadThread;

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

// Retry budget: kInitialDelayMs before first attempt, then up to
// kBridgeRetries polls at kBridgePollMs after LoadPlugIn succeeds
// to wait for the managed side to register GH callbacks.
static constexpr int kInitialDelayMs = 2000;
static constexpr int kLoadRetries    = 3;      // LoadPlugIn attempts
static constexpr int kLoadRetryMs    = 2000;   // between LoadPlugIn attempts
static constexpr int kBridgeRetries  = 10;     // bridge-ready polls after load
static constexpr int kBridgePollMs   = 500;    // between bridge polls
static constexpr int kDispatchPollMs = 100;    // future wait slice during shutdown-aware polls

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

        for (int attempt = 0; attempt < kLoadRetries; ++attempt)
        {
            if (g_stopCompanionLoad.load())
                return;

            if (Rook::Handlers::HasGrasshopperBridgeRegistration())
                return; // Already ready (loaded independently).

            try
            {
                bool ok = false;
                auto scheduled = CMainThreadDispatcher::Instance().Dispatch([&ok]()
                {
                    if (Rook::Handlers::HasGrasshopperBridgeRegistration())
                    {
                        ok = true;
                        return;
                    }

                    CRhinoPlugIn::SaveLoadProtectionToRegistry(g_RookManagedPlugInId, 1);
                    ok = CRhinoPlugIn::LoadPlugIn(g_RookManagedPlugInId, true, true) >= 0;
                });
                if (!WaitForFutureOrStop(scheduled))
                    return;

                scheduled.get();

                if (ok)
                {
                    pluginLoaded = true;
                    break;
                }
            }
            catch (...)
            {
                return; // Dispatcher stopping or Rhino shutting down.
            }

            if (attempt + 1 < kLoadRetries)
                std::this_thread::sleep_for(std::chrono::milliseconds(kLoadRetryMs));
        }

        if (!pluginLoaded)
        {
            try
            {
                CMainThreadDispatcher::Instance().Dispatch([]()
                {
                    RhinoApp().Print(
                        L"RookNative: managed companion LoadPlugIn failed after %d attempts.\n"
                        L"  GH execution is unavailable for this session.\n"
                        L"  Run scripts/register-companion.ps1 and restart Rhino.\n",
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

        // Bridge never came up — plugin loaded but didn't register.
        try
        {
            CMainThreadDispatcher::Instance().Dispatch([]()
            {
                RhinoApp().Print(
                    L"RookNative: managed companion loaded but GH bridge did not register.\n"
                    L"  GH execution may be unavailable. Check companion startup log.\n");
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
    : m_plugin_version(L"1.5.5")
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
    const bool rhinoInside = IsRhinoInside();

    if (rhinoInside)
    {
        RhinoApp().Print(
            L"RookNative %ls: Rhino.Inside mode detected. "
            L"Interactive features (gumball, user prompts) may be unavailable.\n",
            static_cast<const wchar_t*>(m_plugin_version));
    }

    // Start the main-thread dispatcher (CRhinoIsIdle watcher).
    // IMPORTANT: Dispatcher must be accessed FIRST. Both singletons use
    // function-local statics (Meyers singletons), which are destroyed in
    // reverse order of first access. By accessing Dispatcher before Server,
    // static destruction will destroy Server first, then Dispatcher — matching
    // the shutdown dependency (server depends on dispatcher, not vice versa).
    CMainThreadDispatcher::Instance().Start(PlugInID());

    // Start the scene graph engine (background thread + event watcher).
    // Must be after dispatcher (uses Dispatch for reconcile) and before server
    // (HTTP handlers read the snapshot).
    Rook::CSceneGraph::Instance().Start();

    // Start session recorder (CRhinoEventWatcher for command tracking).
    // Must be after dispatcher (commands dispatch to main thread).
    Rook::CSessionRecorder::Instance().Start(PlugInID());

    // Phase 0: History routes (/object/{id}/history, /objects/with-history)
    // read whatever native HistoryRecord() data exists on objects.
    // We do NOT force-enable the master switch — that's the user's choice
    // via Rhino's "Record History" button. The routes work either way.

    // Start the HTTP server on a background thread.
    if (CRookServer::Instance().Start())
    {
        RhinoApp().Print(L"RookNative %ls: HTTP server on port %d\n",
            static_cast<const wchar_t*>(m_plugin_version),
            CRookServer::Instance().Port());
    }
    else
    {
        RhinoApp().Print(L"RookNative %ls: WARNING — HTTP server failed to start\n",
            static_cast<const wchar_t*>(m_plugin_version));
    }

    // Defer managed companion load until after native plugin startup returns.
    // Loading it directly inside OnLoadPlugIn() leaves the managed plug-in in
    // a half-started state where callbacks never register.
    //
    // In Rhino.Inside mode, skip the deferred load entirely — the companion
    // will load via Rhino's own plugin system if it's registered. The deferred
    // polling thread would waste ~7 seconds waiting for a load path that may
    // never succeed in a hosted context.
    if (rhinoInside)
    {
        RhinoApp().Print(
            L"RookNative: skipping companion deferred load "
            L"(companion will register via its own startup hooks if loaded).\n");
    }
    else
    {
        StartCompanionLoadDeferred();
    }

    return TRUE;
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
