// OcctExecutor.h
//
// Task 6b (ADDITIVE): the single dedicated, serialized OCCT worker thread.
//
// WHY THIS EXISTS — the per-thread SE-translation hard crash:
//   OCCT's OSD::SetSignal (called via Rook::OcctProbeInit) installs the Windows
//   SEH -> Standard_Failure translator PER THREAD (it ultimately drives
//   _set_se_translator, which is thread-local). Before this executor, that
//   translation was installed via std::call_once on whichever single httplib
//   pool thread first hit an OCCT route. A subsequent request served by a
//   DIFFERENT pool thread had NO translation installed, so a raw access
//   violation inside OCCT could not be turned into a catchable Standard_Failure
//   — try/catch could not catch it and the whole Rhino process died. The SAME
//   face-pair op runs perfectly offline, proving the geometry/logic is correct;
//   the crash was purely the missing per-thread translation.
//
// THE FIX — route ALL in-plugin OCCT work through ONE long-lived worker thread
// that calls OcctProbeInit() ONCE at startup. This guarantees:
//   (a) SE translation is active on the only thread that ever touches OCCT, so
//       raw AVs become catchable Standard_Failure — no more process death;
//   (b) one thread == serial execution == the v1 serialization, so the old
//       per-call `static std::mutex` (and its stale-lock / EDEADLK failure
//       class) is deleted outright;
//   (c) OCCT stays off the Rhino UI thread.
//
// This header is OCCT-HEADER-FREE on purpose (only <functional>/<future>), so
// Rhino-facing handlers can submit OCCT jobs without pulling any OCCT header.
#pragma once
#include <functional>
#include <future>
#include <utility>

namespace Rook {

class OcctExecutor {
public:
    static OcctExecutor& Instance();

    // Runs fn() on the dedicated OCCT worker thread (where SE translation is
    // installed), BLOCKS the calling thread until fn returns, and returns fn()'s
    // result. Any exception thrown by fn — including an OSD-translated
    // Standard_Failure — is captured on the worker thread and rethrown on the
    // CALLER thread by future.get(). The worker thread itself survives a
    // faulting task and keeps serving the next one (see OcctExecutor.cpp).
    template <class Fn>
    auto Run(Fn&& fn) -> decltype(fn())
    {
        using R = decltype(fn());
        // packaged_task carries fn's result (or its exception) to the future.
        auto task = std::make_shared<std::packaged_task<R()>>(std::forward<Fn>(fn));
        std::future<R> fut = task->get_future();
        // The void lambda runs ON the worker thread. The per-task try/catch in
        // the worker loop keeps the worker alive on a fault; the exception is
        // already stored in the packaged_task's shared state, so future.get()
        // rethrows it here on the caller thread.
        enqueue([task]() { (*task)(); });
        return fut.get();   // blocks; rethrows fn's exception on the caller thread
    }

private:
    OcctExecutor();
    ~OcctExecutor();
    OcctExecutor(const OcctExecutor&) = delete;
    OcctExecutor& operator=(const OcctExecutor&) = delete;

    void enqueue(std::function<void()> task);
};

} // namespace Rook
