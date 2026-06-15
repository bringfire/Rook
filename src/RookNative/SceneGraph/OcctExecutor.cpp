// OcctExecutor.cpp
//
// Task 6b (ADDITIVE): impl of the single dedicated, serialized OCCT worker
// thread. See OcctExecutor.h for the full rationale.
//
// BUILD SHAPE: this TU is compiled with /EHa (Async) and NotUsing PCH, mirroring
// OcctAdjacencyEngine.cpp — see the per-file block in RookNative.vcxproj. /EHa is
// required because the worker thread runs OCCT jobs whose SEH-translated
// Standard_Failure throws must reliably unwind the C++ stack (run the per-task
// try/catch + RAII). It includes OcctProbe.h ONLY for OcctProbeInit(); it pulls
// no other OCCT header (the OCCT work itself lives in the submitted jobs), so the
// OCCT include path is supplied per-file purely for OcctProbeInit's declaration
// surface — harmless and consistent with the sibling OCCT TUs.
//
// TEARDOWN CONTRACT (mirrors ExactAdjacencyService.h caution): this is a Meyers
// singleton constructed lazily on the first Run() call. Its destructor signals
// the worker to stop and joins it. Join is safe here because the worker loop only
// touches this object's own queue/mutex/cv (no dispatcher, no scene graph, no
// Rhino SDK) — there is no cross-singleton teardown dependency. If a future
// change makes join risky during static destruction, detaching the worker is an
// acceptable fallback (the process is exiting), but join is preferred so an
// in-flight OCCT job is allowed to finish.

#include "SceneGraph/OcctExecutor.h"
#include "SceneGraph/OcctProbe.h"   // OcctProbeInit() — the OSD::SetSignal wrapper

#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>

namespace Rook {

namespace {

// Internal state for the singleton. Held in a file-scope struct so the header
// can stay OCCT/threading-header-free (only <functional>/<future>).
struct OcctExecutorState {
    std::mutex                        mutex;
    std::condition_variable           cv;
    std::deque<std::function<void()>> queue;
    bool                              stop = false;
    std::thread                       worker;
};

OcctExecutorState& State()
{
    static OcctExecutorState s;
    return s;
}

// The worker loop. The FIRST thing it does — before serving any task — is install
// OCCT's per-thread SEH->Standard_Failure translation on THIS thread via
// OcctProbeInit(). Because every in-plugin OCCT job runs here, translation is
// always active when OCCT executes, so a raw access violation surfaces as a
// catchable Standard_Failure instead of killing the process.
void WorkerLoop()
{
    // Install SE translation ONCE on the dedicated OCCT thread.
    Rook::OcctProbeInit();

    OcctExecutorState& st = State();
    for (;;) {
        std::function<void()> task;
        {
            std::unique_lock<std::mutex> lk(st.mutex);
            st.cv.wait(lk, [&st] { return st.stop || !st.queue.empty(); });
            if (st.stop && st.queue.empty())
                return;
            task = std::move(st.queue.front());
            st.queue.pop_front();
        }
        // PER-TASK CRASH ISOLATION: a faulting task must NOT kill the worker —
        // it must keep serving. The submitted task is a packaged_task wrapper
        // (see OcctExecutor::Run); invoking it stores fn's result OR its
        // exception into the future's shared state. We still wrap in try/catch
        // so that even an exception escaping the wrapper itself (e.g. an
        // OSD-translated Standard_Failure that, under /EHa, unwinds out of the
        // job) is swallowed here and the loop continues. The caller's
        // future.get() observes the stored exception / a broken-promise error;
        // either way the worker thread survives.
        try {
            task();
        } catch (...) {
            // Worker survives. The task's future already carries fn's outcome.
        }
    }
}

} // namespace

OcctExecutor& OcctExecutor::Instance()
{
    static OcctExecutor s;   // Meyers singleton; constructs the worker thread once.
    return s;
}

OcctExecutor::OcctExecutor()
{
    OcctExecutorState& st = State();
    st.worker = std::thread(&WorkerLoop);
}

OcctExecutor::~OcctExecutor()
{
    OcctExecutorState& st = State();
    {
        std::lock_guard<std::mutex> lk(st.mutex);
        st.stop = true;
    }
    st.cv.notify_all();
    // Join so an in-flight OCCT job finishes cleanly. See the teardown contract
    // in this file's header comment for the detach fallback rationale.
    if (st.worker.joinable()) {
        try {
            st.worker.join();
        } catch (...) {
            // If join is not possible during static destruction, detach: the
            // process is exiting anyway and the worker touches only this
            // object's own queue/mutex/cv.
            try { st.worker.detach(); } catch (...) {}
        }
    }
}

void OcctExecutor::enqueue(std::function<void()> task)
{
    OcctExecutorState& st = State();
    {
        std::lock_guard<std::mutex> lk(st.mutex);
        st.queue.push_back(std::move(task));
    }
    st.cv.notify_one();
}

} // namespace Rook
