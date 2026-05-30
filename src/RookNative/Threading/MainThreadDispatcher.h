// MainThreadDispatcher.h
//
// The core threading innovation of the C++ migration.
// Worker threads (httplib) submit lambdas to a queue. Two drain paths
// execute them on the main thread:
//
//   1. CRhinoIsIdle::Notify() — fires when Rhino is idle (normal operation)
//   2. WndProc subclass       — fires on WM_ROOK_DISPATCH even during modal
//                                loops (GetPoint, GetObject, etc.)
//
// Path 2 is essential for interactive prompts: when GetPoint() runs a modal
// message loop, idle notifications stop firing, but the WndProc still sees
// posted messages. This lets cancel/timeout Dispatch calls reach the main
// thread even while a modal operation is in progress.
//
// DrainQueue() is re-entrant-safe and executes outside the queue lock, so
// redundant calls from both paths are harmless.

#pragma once

#include <commctrl.h>  // SetWindowSubclass, RemoveWindowSubclass, DefSubclassProc

// C13 fix: Use WM_APP range (0x8000–0xBFFF) instead of WM_USER (0x0400–0x7FFF).
// WM_USER messages are reserved for the window class owner (Rhino), so
// WM_USER+42 could collide with Rhino's own private messages. WM_APP is
// explicitly designated for application-level inter-component messaging.
constexpr UINT WM_ROOK_DISPATCH = WM_APP + 42;

enum class DispatchPolicy
{
    Normal,
    CommandControl
};

class CMainThreadDispatcher
{
public:
    CMainThreadDispatcher();
    ~CMainThreadDispatcher();

    // Submit a callable to execute on Rhino's main thread.
    // Returns a future that blocks the caller until the main thread completes.
    // The callable's return value (or exception) propagates through the future.
    //
    // INVARIANT: Never call future.get() on the main thread — the main thread
    // is the one that executes the task, so blocking it would deadlock.
    template<typename F>
    auto Dispatch(
        F&& func,
        DispatchPolicy policy = DispatchPolicy::Normal)
        -> std::future<std::invoke_result_t<F>>;

    // Register the idle watcher with Rhino. Must be called from the main thread.
    // Call once from OnLoadPlugIn, BEFORE CRookServer::Instance().Start().
    // This call order is load-bearing: Meyers singletons are destroyed in
    // reverse order of first access, so calling Dispatcher first ensures it
    // outlives the Server during static destruction.
    void Start(ON_UUID plugin_id);

    // Unregister and drain remaining tasks. Call from OnUnloadPlugIn.
    void Stop();

    bool IsRunning() const { return m_running.load(); }

    static CMainThreadDispatcher& Instance();

    // Save-guard: suppress dispatch while a file-save command is in progress.
    // OnBeginCommand increments when _Save/_SaveSmall/_SaveAs starts;
    // OnEndCommand decrements.  DrainQueue() defers when depth > 0.
    void BeginSaveGuard() { m_saveDepth.fetch_add(1, std::memory_order_release); }
    void EndSaveGuard();
    bool IsSaving() const { return m_saveDepth.load(std::memory_order_acquire) > 0; }

    void BeginCommandGuard();
    void EndCommandGuard();
    bool IsCommandActive() const;

private:
    // CRhinoIsIdle subclass — must be heap-allocated because the plugin GUID
    // isn't known until Start() is called, and CRhinoIsIdle's default
    // constructor is private.
    class CIdleWatcher : public CRhinoIsIdle
    {
    public:
        CIdleWatcher(ON_UUID plugin_id, CMainThreadDispatcher& owner);
        void Notify(const CRhinoIsIdle::CParameters& params) override;
    private:
        CMainThreadDispatcher& m_owner;
    };

    class CCommandWatcher : public CRhinoEventWatcher
    {
    public:
        explicit CCommandWatcher(CMainThreadDispatcher& owner);

        void OnBeginCommand(const CRhinoCommand& command,
                            const CRhinoCommandContext& context) override;
        void OnEndCommand(const CRhinoCommand& command,
                          const CRhinoCommandContext& context,
                          CRhinoCommand::result rc) override;

    private:
        CMainThreadDispatcher& m_owner;
    };

    // Called by CIdleWatcher::Notify AND SubclassProc on the main thread.
    void DrainQueue();
    bool IsAllDispatchBlocked() const { return m_saveDepth.load(std::memory_order_acquire) > 0; }
    bool IsNormalDispatchBlocked() const;

    // WndProc subclass — intercepts WM_ROOK_DISPATCH even during modal loops.
    // SetWindowSubclass chains safely in multi-plugin environments (unlike
    // SetWindowLongPtr which breaks the chain when any subclass is removed).
    static LRESULT CALLBACK SubclassProc(HWND hWnd, UINT uMsg, WPARAM wParam,
                                          LPARAM lParam, UINT_PTR uIdSubclass,
                                          DWORD_PTR dwRefData);

    // Unique ID for our subclass (per SetWindowSubclass contract).
    static constexpr UINT_PTR SUBCLASS_ID = 0x526F6F6B; // "Rook" in ASCII

    struct QueuedTask
    {
        DispatchPolicy policy = DispatchPolicy::Normal;
        std::function<void()> task;
    };

    std::queue<QueuedTask> m_queue;
    std::mutex m_mutex;
    std::unique_ptr<CIdleWatcher> m_watcher;
    std::unique_ptr<CCommandWatcher> m_commandWatcher;
    HWND m_subclassedHwnd = nullptr;
    std::atomic<bool> m_running{false};
    std::atomic<int>  m_saveDepth{0};
    mutable std::mutex m_commandMutex;
    int m_commandDepth = 0;
};

// --- Template implementation (must be in header) ---

template<typename F>
auto CMainThreadDispatcher::Dispatch(
    F&& func,
    DispatchPolicy policy)
    -> std::future<std::invoke_result_t<F>>
{
    using ReturnType = std::invoke_result_t<F>;

    // C14 fix: Check m_running INSIDE the lock to close the TOCTOU race.
    // Without this, Stop() could set m_running=false and drain the queue
    // between our check and our push, leaving the task permanently orphaned.
    // Stop() also sets m_running=false inside the lock (see .cpp).
    std::future<ReturnType> future;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_running.load(std::memory_order_acquire))
        {
            std::promise<ReturnType> p;
            p.set_exception(std::make_exception_ptr(
                std::runtime_error("RookNative dispatcher is not running")));
            return p.get_future();
        }

        auto task = std::make_shared<std::packaged_task<ReturnType()>>(
            std::forward<F>(func));
        future = task->get_future();
        m_queue.push(QueuedTask{
            policy,
            [task]() { (*task)(); }
        });
    }

    // Wake Rhino's message pump so CRhinoIsIdle::Notify fires promptly.
    // PostMessage is safe from any thread (unlike SendMessage which can deadlock).
    HWND hWnd = RhinoApp().MainWnd();
    if (hWnd != nullptr)
    {
        ::PostMessage(hWnd, WM_ROOK_DISPATCH, 0, 0);
    }

    return future;
}
