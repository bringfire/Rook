// MainThreadDispatcher.cpp

#include "stdafx.h"
#include "Threading/MainThreadDispatcher.h"

// --- Singleton ---

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

// --- Lifecycle ---

void CMainThreadDispatcher::Start(ON_UUID plugin_id)
{
    if (m_running.load())
        return;

    {
        std::lock_guard<std::mutex> lock(m_commandMutex);
        m_commandDepth = 0;
    }

    m_watcher = std::make_unique<CIdleWatcher>(plugin_id, *this);
    m_watcher->Register();
    m_watcher->Enable(true);

    m_commandWatcher = std::make_unique<CCommandWatcher>(*this);
    m_commandWatcher->Register();
    m_commandWatcher->Enable(TRUE);

    // Install WndProc subclass for modal-loop drain path.
    // SetWindowSubclass is safe for multi-plugin environments — each plugin
    // gets its own subclass ID and removal doesn't break the chain.
    m_subclassedHwnd = RhinoApp().MainWnd();
    if (m_subclassedHwnd != nullptr)
    {
        ::SetWindowSubclass(m_subclassedHwnd, SubclassProc, SUBCLASS_ID,
                            reinterpret_cast<DWORD_PTR>(this));
    }

    m_running.store(true);
}

void CMainThreadDispatcher::Stop()
{
    // C14 fix: Set m_running=false inside the lock, synchronized with
    // Dispatch()'s m_running check. This prevents the race where Dispatch()
    // reads m_running=true, then Stop() sets it to false and drains the
    // queue, then Dispatch() pushes a task that will never be executed.
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (!m_running.load())
            return;
        m_running.store(false);
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
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (normalDispatchBlocked)
        {
            std::queue<QueuedTask> deferred;
            while (!m_queue.empty())
            {
                auto queued = std::move(m_queue.front());
                m_queue.pop();
                if (queued.policy == DispatchPolicy::CommandControl)
                    local.push(std::move(queued));
                else
                    deferred.push(std::move(queued));
            }
            std::swap(m_queue, deferred);
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
            std::queue<QueuedTask> deferredNormal;
            std::queue<QueuedTask> commandControl;
            deferredNormal.push(std::move(queued));
            while (!local.empty())
            {
                auto queued = std::move(local.front());
                local.pop();
                if (queued.policy == DispatchPolicy::CommandControl)
                    commandControl.push(std::move(queued));
                else
                    deferredNormal.push(std::move(queued));
            }

            requeueAtFront(deferredNormal);
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
            shouldPostDispatch = (current == 1 && !IsNormalDispatchBlocked());
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
