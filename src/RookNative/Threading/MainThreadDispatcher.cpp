// MainThreadDispatcher.cpp

#include "stdafx.h"
#include "Threading/MainThreadDispatcher.h"

// --- Singleton ---

std::atomic<int> CMainThreadDispatcher::s_startupBreadcrumb{
    static_cast<int>(CMainThreadDispatcher::StartupBreadcrumb::NotStarted)
};
std::atomic<int> CMainThreadDispatcher::s_startupSetWindowSubclassStatus{
    static_cast<int>(CMainThreadDispatcher::StartupSubclassStatus::NotAttempted)
};
std::atomic<DWORD> CMainThreadDispatcher::s_startupSetWindowSubclassError{ 0 };

CMainThreadDispatcher::CMainThreadDispatcher() = default;

CMainThreadDispatcher::~CMainThreadDispatcher()
{
    Stop();
}

CMainThreadDispatcher& CMainThreadDispatcher::Instance()
{
    // Static local — constructed once, destroyed at program exit.
    static CMainThreadDispatcher instance;
    return instance;
}

void CMainThreadDispatcher::SetStartupBreadcrumb(StartupBreadcrumb breadcrumb)
{
    s_startupBreadcrumb.store(static_cast<int>(breadcrumb), std::memory_order_release);

    wchar_t line[160] = {};
    swprintf_s(
        line,
        L"RookNative: dispatcher-start: %ls\n",
        StartupBreadcrumbName(breadcrumb));
    ::OutputDebugStringW(line);
}

CMainThreadDispatcher::StartupBreadcrumb CMainThreadDispatcher::GetStartupBreadcrumb()
{
    return static_cast<StartupBreadcrumb>(
        s_startupBreadcrumb.load(std::memory_order_acquire));
}

const wchar_t* CMainThreadDispatcher::StartupBreadcrumbName(StartupBreadcrumb breadcrumb)
{
    switch (breadcrumb)
    {
    case StartupBreadcrumb::NotStarted: return L"not-started";
    case StartupBreadcrumb::InstanceRequested: return L"instance-requested";
    case StartupBreadcrumb::InstanceResolved: return L"instance-resolved";
    case StartupBreadcrumb::StartEntered: return L"start-entered";
    case StartupBreadcrumb::AlreadyRunning: return L"already-running";
    case StartupBreadcrumb::ResetCommandDepth: return L"reset-command-depth";
    case StartupBreadcrumb::ResetSaveSuspendDepth: return L"reset-save-suspend-depth";
    case StartupBreadcrumb::IdleWatcherCreate: return L"idle-watcher-create";
    case StartupBreadcrumb::IdleWatcherRegister: return L"idle-watcher-register";
    case StartupBreadcrumb::IdleWatcherEnable: return L"idle-watcher-enable";
    case StartupBreadcrumb::CommandWatcherCreate: return L"command-watcher-create";
    case StartupBreadcrumb::CommandWatcherRegister: return L"command-watcher-register";
    case StartupBreadcrumb::CommandWatcherEnable: return L"command-watcher-enable";
    case StartupBreadcrumb::RhinoMainWnd: return L"rhino-main-window";
    case StartupBreadcrumb::SetWindowSubclass: return L"set-window-subclass";
    case StartupBreadcrumb::SetWindowSubclassFailed: return L"set-window-subclass-failed";
    case StartupBreadcrumb::MarkRunning: return L"mark-running";
    case StartupBreadcrumb::Succeeded: return L"succeeded";
    default: return L"unknown";
    }
}

DWORD CMainThreadDispatcher::GetStartupSetWindowSubclassError()
{
    return s_startupSetWindowSubclassError.load(std::memory_order_acquire);
}

CMainThreadDispatcher::StartupSubclassStatus CMainThreadDispatcher::GetStartupSetWindowSubclassStatus()
{
    return static_cast<StartupSubclassStatus>(
        s_startupSetWindowSubclassStatus.load(std::memory_order_acquire));
}

// --- Lifecycle ---

void CMainThreadDispatcher::Start(ON_UUID plugin_id)
{
    if (m_running.load())
    {
        SetStartupBreadcrumb(StartupBreadcrumb::AlreadyRunning);
        return;
    }

    SetStartupBreadcrumb(StartupBreadcrumb::StartEntered);
    s_startupSetWindowSubclassStatus.store(
        static_cast<int>(StartupSubclassStatus::NotAttempted),
        std::memory_order_release);
    s_startupSetWindowSubclassError.store(0, std::memory_order_release);
    SetStartupBreadcrumb(StartupBreadcrumb::ResetCommandDepth);
    {
        std::lock_guard<std::mutex> lock(m_commandMutex);
        m_commandDepth = 0;
    }
    SetStartupBreadcrumb(StartupBreadcrumb::ResetSaveSuspendDepth);
    m_saveDepth.store(0, std::memory_order_release);
    m_suspendDepth.store(0, std::memory_order_release);

    SetStartupBreadcrumb(StartupBreadcrumb::IdleWatcherCreate);
    m_watcher = std::make_unique<CIdleWatcher>(plugin_id, *this);
    SetStartupBreadcrumb(StartupBreadcrumb::IdleWatcherRegister);
    m_watcher->Register();
    SetStartupBreadcrumb(StartupBreadcrumb::IdleWatcherEnable);
    m_watcher->Enable(true);

    SetStartupBreadcrumb(StartupBreadcrumb::CommandWatcherCreate);
    m_commandWatcher = std::make_unique<CCommandWatcher>(*this);
    SetStartupBreadcrumb(StartupBreadcrumb::CommandWatcherRegister);
    m_commandWatcher->Register();
    SetStartupBreadcrumb(StartupBreadcrumb::CommandWatcherEnable);
    m_commandWatcher->Enable(TRUE);

    // Install WndProc subclass for modal-loop drain path.
    // SetWindowSubclass is safe for multi-plugin environments — each plugin
    // gets its own subclass ID and removal doesn't break the chain.
    SetStartupBreadcrumb(StartupBreadcrumb::RhinoMainWnd);
    m_subclassedHwnd = RhinoApp().MainWnd();
    if (m_subclassedHwnd != nullptr)
    {
        SetStartupBreadcrumb(StartupBreadcrumb::SetWindowSubclass);
        if (!::SetWindowSubclass(m_subclassedHwnd, SubclassProc, SUBCLASS_ID,
                                 reinterpret_cast<DWORD_PTR>(this)))
        {
            const DWORD error = ::GetLastError();
            s_startupSetWindowSubclassStatus.store(
                static_cast<int>(StartupSubclassStatus::Failed),
                std::memory_order_release);
            s_startupSetWindowSubclassError.store(error, std::memory_order_release);
            SetStartupBreadcrumb(StartupBreadcrumb::SetWindowSubclassFailed);

            wchar_t line[192] = {};
            swprintf_s(
                line,
                L"RookNative: dispatcher-start: SetWindowSubclass failed GetLastError=%lu\n",
                error);
            ::OutputDebugStringW(line);
            m_subclassedHwnd = nullptr;
        }
        else
        {
            s_startupSetWindowSubclassStatus.store(
                static_cast<int>(StartupSubclassStatus::Installed),
                std::memory_order_release);
        }
    }

    SetStartupBreadcrumb(StartupBreadcrumb::MarkRunning);
    m_running.store(true);
    SetStartupBreadcrumb(StartupBreadcrumb::Succeeded);
}

void CMainThreadDispatcher::Stop()
{
    // C14 fix: Set m_running=false inside the lock, synchronized with
    // Dispatch()'s m_running check. This prevents the race where Dispatch()
    // reads m_running=true, then Stop() sets it to false and drains the
    // queue, then Dispatch() pushes a task that will never be executed.
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        const bool wasRunning = m_running.exchange(false);
        const bool hasStartupState =
            m_subclassedHwnd != nullptr
            || m_watcher != nullptr
            || m_commandWatcher != nullptr
            || !m_queue.empty()
            || m_saveDepth.load(std::memory_order_acquire) > 0
            || m_suspendDepth.load(std::memory_order_acquire) > 0;

        if (!wasRunning && !hasStartupState)
            return;
    }

    // Remove WndProc subclass before unregistering the idle watcher.
    if (m_subclassedHwnd != nullptr)
    {
        ::RemoveWindowSubclass(m_subclassedHwnd, SubclassProc, SUBCLASS_ID);

        // C4 fix: Drain any WM_ROOK_DISPATCH messages already in the Win32
        // message queue. Without this, a queued message could be delivered
        // after RemoveWindowSubclass returns, reaching SubclassProc with a
        // stale dwRefData pointer (this object may be partially destroyed).
        // PeekMessage is safe here because Stop() runs on the main thread.
        MSG msg;
        while (::PeekMessage(&msg, m_subclassedHwnd, WM_ROOK_DISPATCH,
                             WM_ROOK_DISPATCH, PM_REMOVE))
        {
            // Discard — subclass is removed, no handler for these.
        }

        m_subclassedHwnd = nullptr;
    }

    if (m_commandWatcher)
    {
        m_commandWatcher->Enable(FALSE);
        m_commandWatcher->UnRegister();
        m_commandWatcher.reset();
    }

    {
        std::lock_guard<std::mutex> lock(m_commandMutex);
        m_commandDepth = 0;
    }
    m_saveDepth.store(0, std::memory_order_release);
    m_suspendDepth.store(0, std::memory_order_release);

    if (m_watcher)
    {
        m_watcher->Enable(false);
        m_watcher->Unregister();
        m_watcher.reset();
    }

    // C17 fix: Discard remaining tasks instead of executing them.
    // During plugin unload, Rhino SDK objects may be partially destroyed —
    // executing queued lambdas that call RhinoApp(), access documents, or
    // iterate layer tables would crash. Discarding the queue is safe:
    // packaged_task destructors set broken_promise on their associated
    // futures, which is the correct signal for "dispatcher shut down".
    //
    // IMPORTANT: `discard` is declared BEFORE `lock` so that it is
    // destroyed AFTER the lock releases (C++ reverse destruction order).
    // If a packaged_task destructor transitively calls Dispatch(), it
    // must be able to acquire m_mutex — deadlocks if lock is still held.
    std::queue<QueuedTask> discard;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        std::swap(discard, m_queue);
    }
}

// --- Queue Processing ---

void CMainThreadDispatcher::CancelQueuedTasks(std::queue<QueuedTask>& tasks)
{
    while (!tasks.empty())
    {
        auto queued = std::move(tasks.front());
        tasks.pop();
        try
        {
            if (queued.cancel)
                queued.cancel();
        }
        catch (...)
        {
        }
    }
}

void CMainThreadDispatcher::DrainQueue()
{
    // Save-guard: while a file-save command (_Save, _SaveSmall, _SaveAs)
    // is in progress, do NOT drain the queue.  HTTP handlers access
    // doc.Objects / Geometry which can interfere with Rhino's file-save
    // serialization and prevent the temp-file rename from succeeding.
    // Tasks remain queued and drain on the next idle/WM_ROOK_DISPATCH
    // after the save command completes.
    if (IsAllDispatchBlocked())
        return;

    const bool normalDispatchBlocked = IsNormalDispatchBlocked();

    // Hold the lock only while moving tasks, then execute tasks outside the
    // lock. This prevents deadlock if a task calls Dispatch() re-entrantly
    // (which would try to acquire m_mutex).
    std::queue<QueuedTask> local;
    std::queue<QueuedTask> blockedNormal;
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (normalDispatchBlocked)
        {
            std::queue<QueuedTask> commandControl;
            while (!m_queue.empty())
            {
                auto queued = std::move(m_queue.front());
                m_queue.pop();
                if (queued.policy == DispatchPolicy::CommandControl)
                    commandControl.push(std::move(queued));
                else
                    blockedNormal.push(std::move(queued));
            }
            std::swap(local, commandControl);
        }
        else
        {
            std::swap(local, m_queue);
        }
    }

    auto requeueAtFront = [this](std::queue<QueuedTask>& tasks) {
        if (tasks.empty())
            return;

        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_queue.empty())
        {
            std::queue<QueuedTask> existing;
            std::swap(existing, m_queue);
            while (!existing.empty())
            {
                tasks.push(std::move(existing.front()));
                existing.pop();
            }
        }
        std::swap(m_queue, tasks);
    };

    if (IsAllDispatchBlocked())
    {
        while (!local.empty())
        {
            auto queued = std::move(local.front());
            local.pop();
            blockedNormal.push(std::move(queued));
        }
        requeueAtFront(blockedNormal);
        return;
    }

    CancelQueuedTasks(blockedNormal);

    while (!local.empty())
    {
        auto queued = std::move(local.front());
        local.pop();

        if (IsAllDispatchBlocked())
        {
            std::queue<QueuedTask> blocked;
            blocked.push(std::move(queued));
            while (!local.empty())
            {
                auto queued = std::move(local.front());
                local.pop();
                blocked.push(std::move(queued));
            }
            requeueAtFront(blocked);
            return;
        }

        if (queued.policy == DispatchPolicy::Normal && IsNormalDispatchBlocked())
        {
            std::queue<QueuedTask> blockedNormal;
            std::queue<QueuedTask> commandControl;
            blockedNormal.push(std::move(queued));
            while (!local.empty())
            {
                auto queued = std::move(local.front());
                local.pop();
                if (queued.policy == DispatchPolicy::CommandControl)
                    commandControl.push(std::move(queued));
                else
                    blockedNormal.push(std::move(queued));
            }

            CancelQueuedTasks(blockedNormal);
            std::swap(local, commandControl);
            continue;
        }

        try
        {
            queued.task();
        }
        catch (...)
        {
            // packaged_task captures exceptions into the future, so this
            // should never fire. Guard defensively so one rogue task can't
            // abandon the remaining tasks and leave their futures hung.
        }
    }
}

// --- Command Guard ---

void CMainThreadDispatcher::EndSaveGuard()
{
    bool shouldPostDispatch = false;
    int current = m_saveDepth.load(std::memory_order_acquire);
    while (current > 0)
    {
        if (m_saveDepth.compare_exchange_weak(current, current - 1,
                                              std::memory_order_acq_rel,
                                              std::memory_order_acquire))
        {
            shouldPostDispatch = (current == 1);
            break;
        }
    }

    if (shouldPostDispatch && m_subclassedHwnd != nullptr)
    {
        ::PostMessage(m_subclassedHwnd, WM_ROOK_DISPATCH, 0, 0);
    }
}

void CMainThreadDispatcher::EndSuspendGuard()
{
    bool shouldPostDispatch = false;
    int current = m_suspendDepth.load(std::memory_order_acquire);
    while (current > 0)
    {
        if (m_suspendDepth.compare_exchange_weak(current, current - 1,
                                                 std::memory_order_acq_rel,
                                                 std::memory_order_acquire))
        {
            shouldPostDispatch = (current == 1);
            break;
        }
    }

    if (shouldPostDispatch && m_subclassedHwnd != nullptr)
    {
        ::PostMessage(m_subclassedHwnd, WM_ROOK_DISPATCH, 0, 0);
    }
}

void CMainThreadDispatcher::BeginCommandGuard()
{
    std::lock_guard<std::mutex> lock(m_commandMutex);
    ++m_commandDepth;
}

void CMainThreadDispatcher::EndCommandGuard()
{
    bool shouldPostDispatch = false;
    {
        std::lock_guard<std::mutex> lock(m_commandMutex);
        if (m_commandDepth == 0)
            return;

        --m_commandDepth;
        shouldPostDispatch = (m_commandDepth == 0);
    }

    if (shouldPostDispatch && m_subclassedHwnd != nullptr)
    {
        ::PostMessage(m_subclassedHwnd, WM_ROOK_DISPATCH, 0, 0);
    }
}

bool CMainThreadDispatcher::IsCommandActive() const
{
    std::lock_guard<std::mutex> lock(m_commandMutex);
    return m_commandDepth > 0;
}

bool CMainThreadDispatcher::IsNormalDispatchBlocked() const
{
    if (IsCommandActive())
        return true;

    // The event watcher can miss commands that were already active when
    // RookNative loaded, including startup recent-file _Open. Check Rhino's
    // current command stack at drain time so normal work remains deferred.
    return RhinoApp().InCommand(false) > 0;
}

// --- CIdleWatcher ---

CMainThreadDispatcher::CIdleWatcher::CIdleWatcher(
    ON_UUID plugin_id, CMainThreadDispatcher& owner)
    : CRhinoIsIdle(plugin_id)
    , m_owner(owner)
{
}

void CMainThreadDispatcher::CIdleWatcher::Notify(
    const CRhinoIsIdle::CParameters& /*params*/)
{
    m_owner.DrainQueue();
}

// --- CCommandWatcher ---

CMainThreadDispatcher::CCommandWatcher::CCommandWatcher(
    CMainThreadDispatcher& owner)
    : m_owner(owner)
{
}

void CMainThreadDispatcher::CCommandWatcher::OnBeginCommand(
    const CRhinoCommand& /*command*/,
    const CRhinoCommandContext& /*context*/)
{
    m_owner.BeginCommandGuard();
}

void CMainThreadDispatcher::CCommandWatcher::OnEndCommand(
    const CRhinoCommand& /*command*/,
    const CRhinoCommandContext& /*context*/,
    CRhinoCommand::result /*rc*/)
{
    m_owner.EndCommandGuard();
}

// --- WndProc Subclass ---

LRESULT CALLBACK CMainThreadDispatcher::SubclassProc(
    HWND hWnd, UINT uMsg, WPARAM wParam, LPARAM lParam,
    UINT_PTR uIdSubclass, DWORD_PTR dwRefData)
{
    if (uMsg == WM_ROOK_DISPATCH)
    {
        // Drain the queue — this fires even during modal loops (GetPoint,
        // GetObject) because modal loops pump messages through the WndProc.
        auto* self = reinterpret_cast<CMainThreadDispatcher*>(dwRefData);
        self->DrainQueue();
        return 0;
    }

    if (uMsg == WM_NCDESTROY)
    {
        // Window is being destroyed — remove our subclass to avoid dangling.
        ::RemoveWindowSubclass(hWnd, SubclassProc, uIdSubclass);
    }

    return ::DefSubclassProc(hWnd, uMsg, wParam, lParam);
}
