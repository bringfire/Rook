# RookVisionDirector Replay — Dispatch-Drain Pump Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Settle empirically whether a synchronous replay can hold the Rhino UI thread and run a bounded message pump without reentrantly draining the dispatcher, and leave behind only a validated `DispatchDrainSuspension` guard plus written evidence.

**Architecture:** Add a durable dispatch-drain suspension primitive to `CMainThreadDispatcher` (a new `m_suspendDepth` folded into `IsAllDispatchBlocked()`, wrapped in an RAII guard that wakes the pump on release — mirroring the existing save guard). Then stand up a throwaway, test-hook-gated `/director/_pumpspike` route that runs three pump strategies (S0 control / S1 filtered / S2 guarded) against a sentinel `Dispatch`, record decision-grade JSON from a live Rhino, decide the PR2 replay model, and strip all scaffolding so the only shipped code is the guard + its tests.

**Tech Stack:** C++ (RookNative plugin, `httplib`, Win32 message pump, RhinoCommon C++ SDK), C# xUnit source-analysis tests (`Rook.Tests`), Python throwaway runner using the existing `bridge.py` native-instance discovery.

**Spec:** `docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-pumpspike-design.md`

## Global Constraints

- **Native builds run via `cmd /c "scripts\build-native.bat"`** (never invoke MSBuild/cl directly). Deploy via `cmd /c "scripts\deploy-native.bat"`.
- **Durable change surface is native-only:** `src/RookNative/Threading/MainThreadDispatcher.h` + `.cpp`, plus the C# source-analysis test `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs`. No managed runtime, no Python, no `server.py` in the durable artifact.
- **Running `dotnet test` on `Rook.Tests` deploys `Rook.rhp` into `%AppData%`** (managed-build side effect) — expected, not an error.
- **Throwaway scaffolding is gated behind a test-hook env flag** (`ROOK_DIRECTOR_PUMPSPIKE`, default off, following the existing `RunScriptSafetyTestHooks` pattern in `CommandHandler.cpp`) and **must be fully removed before the PR is opened for review.** The only shipped code is the guard + its tests + the written evidence.
- **Both drain doors must be covered:** idle (`CRhinoIsIdle::Notify`) and WndProc (`WM_ROOK_DISPATCH` = `WM_APP + 42`).
- **Safe verdict (all three required):** `queued_during_pump == true`, `tasks_executed_during_pump == 0`, `executed_after_return == true`. `drain_attempt_count` may be nonzero in S2 and that is positive evidence (doors entered `DrainQueue` and bailed at the guard).
- **No SendKeys / wscript.shell / keyboard automation** anywhere.

## File Structure

| File | Responsibility | Lifetime |
|------|----------------|----------|
| `src/RookNative/Threading/MainThreadDispatcher.h` | Declares `m_suspendDepth`, `Begin/EndSuspendGuard`, `IsDispatchSuspended`, the `DispatchDrainSuspension` RAII class; updates `IsAllDispatchBlocked()` | **Durable** |
| `src/RookNative/Threading/MainThreadDispatcher.cpp` | Implements `EndSuspendGuard` (CAS-decrement + wake-on-zero) and the RAII ctor/dtor | **Durable** |
| `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs` | Source-analysis tests pinning the guard's structure | **Durable** |
| `src/RookNative/Handlers/DirectorHandler.cpp` / `.h` | Hosts the throwaway `HandleDirectorPumpSpike` route + sentinel rig + S0/S1/S2 pump bodies | **Throwaway** (route added in Task 3, removed in Task 5) |
| `src/RookNative/RookServer.cpp` | Registers `/director/_pumpspike` (gated) | **Throwaway** (added Task 3, removed Task 5) |
| `scripts/_pumpspike_run.py` | Throwaway runner: discovers the native port via `bridge.py`, POSTs the probe, prints/saves JSON | **Throwaway** (added Task 3, removed Task 5) |
| The spec's "Findings" section | Records the S0/S1/S2 JSON + the model decision | **Durable** (written in Task 4) |

**Testing strategy note (read before Task 1):** The durable guard is verified two ways. (1) **Source-analysis tests** (C#, `dotnet test`) pin its *structure* — the same idiom the codebase already uses for `EndSaveGuard` (`MainThreadDispatcherSourceTests.EndSaveGuard_PostsWhenSaveDepthReleases...`). They cannot assert runtime behavior. (2) **The live S2 run** (Task 4) validates the *runtime* behavior (queued-during + executed-after-return). Both are required; neither alone is sufficient.

---

### Task 1: Suspend depth folded into `IsAllDispatchBlocked()`

Add a second blocking counter to the dispatcher, distinct from save depth, so a future guard can freeze draining without borrowing file-save semantics. This task does **not** add the RAII wrapper yet — only the depth and the block check.

**Files:**
- Modify: `src/RookNative/Threading/MainThreadDispatcher.h` (add `m_suspendDepth`; update `IsAllDispatchBlocked()`)
- Test: `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs` (add cases)

**Interfaces:**
- Consumes: existing `m_saveDepth` (`std::atomic<int>`), existing `IsAllDispatchBlocked() const`.
- Produces: `std::atomic<int> m_suspendDepth{0}` and an `IsAllDispatchBlocked()` that returns true when **either** depth is positive. Task 2 consumes `m_suspendDepth`.

- [ ] **Step 1: Write the failing source-analysis tests**

Add to `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs`, inside the class:

```csharp
[Fact]
public void Dispatcher_DeclaresSuspendDepthDistinctFromSaveDepth()
{
    var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");

    Assert.Contains("std::atomic<int>  m_suspendDepth{0};", source);
    // Save depth still exists and is a separate field.
    Assert.Contains("std::atomic<int>  m_saveDepth{0};", source);
}

[Fact]
public void IsAllDispatchBlocked_ChecksSaveOrSuspendDepth()
{
    var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
    var fn = ExtractFunction(source, "CMainThreadDispatcher::IsAllDispatchBlocked");

    Assert.Contains("m_saveDepth.load(std::memory_order_acquire) > 0", fn);
    Assert.Contains("m_suspendDepth.load(std::memory_order_acquire) > 0", fn);
    Assert.Contains("||", fn);
}
```

Note: `IsAllDispatchBlocked()` is currently a one-line inline body in the header. The test uses `ExtractFunction` against the qualified name, so Step 3 must give it a named, brace-delimited definition `bool CMainThreadDispatcher::IsAllDispatchBlocked() const { ... }` (either still in the header as an out-of-line inline, or moved to `.cpp`). Keep it in the header as an inline definition to match where it lives today.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~MainThreadDispatcherSourceTests" --nologo`
Expected: FAIL — `Dispatcher_DeclaresSuspendDepthDistinctFromSaveDepth` and `IsAllDispatchBlocked_ChecksSaveOrSuspendDepth` fail (string not found / function-not-found), existing cases pass.

- [ ] **Step 3: Add the suspend depth and update the block check**

In `src/RookNative/Threading/MainThreadDispatcher.h`:

Add the member beside `m_saveDepth` (in the private members block near the bottom of the class):

```cpp
    std::atomic<int>  m_saveDepth{0};
    std::atomic<int>  m_suspendDepth{0};
```

Replace the existing inline one-liner:

```cpp
    bool IsAllDispatchBlocked() const { return m_saveDepth.load(std::memory_order_acquire) > 0; }
```

with a named, brace-delimited inline definition:

```cpp
    bool IsAllDispatchBlocked() const
    {
        return m_saveDepth.load(std::memory_order_acquire) > 0
            || m_suspendDepth.load(std::memory_order_acquire) > 0;
    }
```

(If the build complains the qualified name isn't matched by `ExtractFunction`, define it out-of-line in `.cpp` as `bool CMainThreadDispatcher::IsAllDispatchBlocked() const { ... }` and leave a declaration in the header. Prefer keeping it in the header.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~MainThreadDispatcherSourceTests" --nologo`
Expected: PASS — all `MainThreadDispatcherSourceTests` cases green.

- [ ] **Step 5: Build native to confirm it compiles**

Run: `cmd /c "scripts\build-native.bat"`
Expected: build succeeds (the new atomic member and OR'd check compile cleanly).

- [ ] **Step 6: Commit**

```bash
git add src/RookNative/Threading/MainThreadDispatcher.h src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
git commit -m "feat(dispatcher): add suspend depth to IsAllDispatchBlocked"
```

---

### Task 2: `DispatchDrainSuspension` RAII guard with wake-on-release

Wrap suspend depth in a nest-safe RAII guard whose outermost release posts `WM_ROOK_DISPATCH`, exactly mirroring `EndSaveGuard`. This is the durable artifact PR2's replay loop will wrap its pump in.

**Files:**
- Modify: `src/RookNative/Threading/MainThreadDispatcher.h` (declare `Begin/EndSuspendGuard`, `IsDispatchSuspended`, the RAII class)
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp` (implement `EndSuspendGuard`, RAII ctor/dtor)
- Test: `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs` (add cases)

**Interfaces:**
- Consumes: `m_suspendDepth`, `m_subclassedHwnd`, `WM_ROOK_DISPATCH` (all existing after Task 1 / already present).
- Produces:
  - `void CMainThreadDispatcher::BeginSuspendGuard()` — `m_suspendDepth.fetch_add(1, std::memory_order_release)`.
  - `void CMainThreadDispatcher::EndSuspendGuard()` — CAS-decrement; posts `WM_ROOK_DISPATCH` to `m_subclassedHwnd` only when depth releases to zero.
  - `bool CMainThreadDispatcher::IsDispatchSuspended() const`.
  - `class DispatchDrainSuspension` — ctor calls `BeginSuspendGuard()`, dtor calls `EndSuspendGuard()`, non-copyable. PR2's replay loop constructs one on the UI thread for the duration of its held pump.

- [ ] **Step 1: Write the failing source-analysis tests**

Add to `MainThreadDispatcherSourceTests.cs`:

```csharp
[Fact]
public void SuspendGuard_RaiiClassIsNonCopyableAndTogglesDepth()
{
    var header = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
    var raii = ExtractStruct(header.Replace("class DispatchDrainSuspension", "struct DispatchDrainSuspension"),
                             "DispatchDrainSuspension");

    Assert.Contains("BeginSuspendGuard()", raii);
    Assert.Contains("EndSuspendGuard()", raii);
    Assert.Contains("DispatchDrainSuspension(const DispatchDrainSuspension&) = delete;", raii);
    Assert.Contains("DispatchDrainSuspension& operator=(const DispatchDrainSuspension&) = delete;", raii);
}

[Fact]
public void BeginSuspendGuard_IncrementsDepth()
{
    var header = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
    Assert.Contains("void BeginSuspendGuard() { m_suspendDepth.fetch_add(1, std::memory_order_release); }", header);
}

[Fact]
public void EndSuspendGuard_PostsOnlyWhenSuspendDepthReleasesToZero()
{
    var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
    var fn = ExtractFunction(source, "CMainThreadDispatcher::EndSuspendGuard");

    Assert.Contains("shouldPostDispatch = (current == 1);", fn);
    Assert.Contains("PostMessage(m_subclassedHwnd, WM_ROOK_DISPATCH", fn);
    Assert.Contains("compare_exchange_weak", fn);
}

[Fact]
public void Dispatch_DoesNotConsultSuspendStateWhenEnqueueing()
{
    // Enqueue must stay allowed while suspended: only draining is deferred.
    var header = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
    var dispatch = ExtractFunction(header, "CMainThreadDispatcher::Dispatch");

    Assert.DoesNotContain("IsAllDispatchBlocked", dispatch);
    Assert.DoesNotContain("IsDispatchSuspended", dispatch);
    Assert.DoesNotContain("m_suspendDepth", dispatch);
}
```

Note: `ExtractStruct` searches for `struct <name>`; the RAII is a `class`, so the test swaps the keyword on the in-memory copy before extracting. `ExtractFunction` for `Dispatch` matches the template definition already in the header.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~MainThreadDispatcherSourceTests" --nologo`
Expected: FAIL — the four new cases fail (symbols not yet present); Task 1 cases still pass.

- [ ] **Step 3: Declare the guard API and RAII class in the header**

In `MainThreadDispatcher.h`, in the `public:` section near `BeginSaveGuard`/`EndSaveGuard`:

```cpp
    // Dispatch-drain suspension (general; NOT tied to file-save semantics).
    // While suspend depth > 0, DrainQueue defers via IsAllDispatchBlocked().
    // Worker-thread Dispatch() is unaffected — only UI-thread draining pauses.
    void BeginSuspendGuard() { m_suspendDepth.fetch_add(1, std::memory_order_release); }
    void EndSuspendGuard();
    bool IsDispatchSuspended() const { return m_suspendDepth.load(std::memory_order_acquire) > 0; }
```

After the class definition (below the closing `};` of `CMainThreadDispatcher`, before the template implementation block), declare the RAII guard:

```cpp
// RAII: suspends dispatcher draining for the lifetime of the guard on the UI
// thread. The outermost release wakes the pump (see EndSuspendGuard), so queued
// work drains promptly once the holding UI-thread lambda returns. Replay (PR2)
// wraps its per-frame pump in one of these.
class DispatchDrainSuspension
{
public:
    DispatchDrainSuspension() { CMainThreadDispatcher::Instance().BeginSuspendGuard(); }
    ~DispatchDrainSuspension() { CMainThreadDispatcher::Instance().EndSuspendGuard(); }
    DispatchDrainSuspension(const DispatchDrainSuspension&) = delete;
    DispatchDrainSuspension& operator=(const DispatchDrainSuspension&) = delete;
};
```

- [ ] **Step 4: Implement `EndSuspendGuard` in the `.cpp`**

In `MainThreadDispatcher.cpp`, directly after `EndSaveGuard`'s definition, add:

```cpp
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~MainThreadDispatcherSourceTests" --nologo`
Expected: PASS — all cases green.

- [ ] **Step 6: Build native to confirm it compiles**

Run: `cmd /c "scripts\build-native.bat"`
Expected: build succeeds (RAII references `Instance()`, which is declared above it; `EndSuspendGuard` mirrors `EndSaveGuard`).

- [ ] **Step 7: Commit**

```bash
git add src/RookNative/Threading/MainThreadDispatcher.h src/RookNative/Threading/MainThreadDispatcher.cpp src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
git commit -m "feat(dispatcher): add DispatchDrainSuspension RAII guard with wake-on-release"
```

---

### Task 3: Throwaway pump-spike probe (route + sentinel rig + S0/S1/S2)

Stand up the disposable, test-hook-gated probe that holds the UI thread, runs each pump strategy, and reports decision-grade JSON. **Everything in this task is removed in Task 5.** Commit messages are prefixed `spike:` so the throwaway commits are easy to find and drop.

**Files:**
- Modify: `src/RookNative/Handlers/DirectorHandler.h` (declare `HandleDirectorPumpSpike`)
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp` (implement the probe, sentinel rig, S0/S1/S2 bodies, gated `drain_attempt_count` hook)
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp` (gated `drain_attempt_count` increment at `DrainQueue` entry — reverted in Task 5)
- Modify: `src/RookNative/RookServer.cpp` (register `/director/_pumpspike` when the env flag is set)
- Create: `scripts/_pumpspike_run.py` (throwaway runner)

**Interfaces:**
- Consumes: `CMainThreadDispatcher::Instance().Dispatch(...)`, `DispatchDrainSuspension` (Task 2), `WM_ROOK_DISPATCH`.
- Produces: `POST /director/_pumpspike` with body `{"strategy": "S0_control" | "S1_filtered" | "S2_guarded", "pump_ms": <int>}` → JSON `{pump_strategy, queued_during_pump, executed_during_pump, executed_after_return, drain_attempt_count, tasks_executed_during_pump, idle_fired_during_pump, messages_processed}`.

**Probe shape (reference for the implementer — the worker-thread handler):**
1. Read `strategy` and `pump_ms` from the request.
2. Reset module-static atomics: `g_pumpActive=false`, `g_sentinelExecuted=false`, `g_sentinelExecutedAfterReturn=false`, `g_tasksExecutedDuringPump=0`, `g_drainAttempts=0`, `g_idleFiredDuringPump=false`, `g_holdingLambdaReturned=false`.
3. Spawn a sentinel `std::thread`: wait (spin/`condition_variable`) until `g_pumpActive`, then call `Dispatch([]{ if (!g_holdingLambdaReturned.load()) g_tasksExecutedDuringPump.fetch_add(1); g_sentinelExecuted = true; if (g_holdingLambdaReturned.load()) g_sentinelExecutedAfterReturn = true; })` and keep the future.
4. `Dispatch` the **holding** lambda and block on its future. The holding lambda, on the UI thread:
   - sets `g_pumpActive=true`;
   - optionally constructs a `DispatchDrainSuspension` (S2 only);
   - loops for `pump_ms` in ~16ms slices running the strategy's pump body (S0: drain all messages via `PeekMessage(..., PM_REMOVE)`; S1: same but `if (msg.message == WM_ROOK_DISPATCH) { re-post and skip dispatch }` — i.e. filtered; S2: same pump body as S0 but inside the guard), counting `messages_processed`;
   - **end-of-lambda assertion:** records `executed_during_pump = g_sentinelExecuted` *here*, before returning, then sets `g_holdingLambdaReturned=true` and returns. (Any sentinel execution observed at this point — during pump or after guard scope but still inside the lambda — is `executed_during_pump`.)
5. After the holding future returns, the worker thread waits (bounded, e.g. 2s) on the sentinel future, then reads `g_sentinelExecutedAfterReturn` → `executed_after_return`.
6. Assemble and return the JSON.

The idle door: register/observe via the existing idle watcher path — set `g_idleFiredDuringPump=true` from a temporary hook in `CRhinoIsIdle::Notify` (gated by the spike flag) so a "safe" S1 can be told apart from "idle never fired."

- [ ] **Step 1: Add the test-hook flag gate + route registration**

In `src/RookNative/RookServer.cpp`, beside the other `/director/...` registrations (~line 987), add a gated registration:

```cpp
    if (std::getenv("ROOK_DIRECTOR_PUMPSPIKE") != nullptr)
    {
        m_server->Post("/director/_pumpspike", [](const httplib::Request& req, httplib::Response& res) {
            Rook::Handlers::HandleDirectorPumpSpike(req, res);
        });
    }
```

In `src/RookNative/Handlers/DirectorHandler.h`, add:

```cpp
void HandleDirectorPumpSpike(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 2: Implement the probe, sentinel rig, and S0/S1/S2 bodies**

In `src/RookNative/Handlers/DirectorHandler.cpp`, implement `HandleDirectorPumpSpike` following the Probe shape above. Use module-static `std::atomic` flags/counters as listed. Pump body sketch:

```cpp
// One ~16ms slice. Returns messages processed this slice.
static int PumpSliceDrainAll(bool filterRookDispatch)
{
    int processed = 0;
    MSG msg;
    while (::PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE))
    {
        if (filterRookDispatch && msg.message == WM_ROOK_DISPATCH)
        {
            // Leave the dispatch door shut: re-post so it is delivered AFTER
            // the held lambda returns, and do not dispatch it now.
            ::PostMessage(msg.hwnd, WM_ROOK_DISPATCH, msg.wParam, msg.lParam);
            continue;
        }
        ::TranslateMessage(&msg);
        ::DispatchMessage(&msg);
        ++processed;
    }
    return processed;
}
```

S0 = `PumpSliceDrainAll(false)` no guard; S1 = `PumpSliceDrainAll(true)` no guard; S2 = `PumpSliceDrainAll(false)` with a `DispatchDrainSuspension` alive for the loop. Sleep the remainder of each 16ms slice with a short `std::this_thread::sleep_for` only to pace slices (this runs on the UI thread between pumps; keep it ≤16ms and bounded by `pump_ms`).

- [ ] **Step 3: Add the gated `drain_attempt_count` hook**

In `src/RookNative/Threading/MainThreadDispatcher.cpp`, at the very top of `DrainQueue()`, add a gated increment (reverted in Task 5):

```cpp
void CMainThreadDispatcher::DrainQueue()
{
    extern std::atomic<int> g_pumpSpikeDrainAttempts;  // defined in DirectorHandler.cpp
    if (std::getenv("ROOK_DIRECTOR_PUMPSPIKE") != nullptr)
        g_pumpSpikeDrainAttempts.fetch_add(1, std::memory_order_relaxed);
    // ... existing body unchanged ...
```

(Counts every `DrainQueue` entry while the spike flag is on. In S2 this is expected to be nonzero — proof the doors fired and the guard held.)

- [ ] **Step 4: Build native**

Run: `cmd /c "scripts\build-native.bat"`
Expected: build succeeds.

- [ ] **Step 5: Write the throwaway runner**

Create `scripts/_pumpspike_run.py`:

```python
"""THROWAWAY pump-spike runner. Removed in Task 5. Discovers the native port
via bridge.py and POSTs /director/_pumpspike for each strategy."""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server" / "src"))
from rook.bridge import discover_native_port  # type: ignore
import httpx

def main():
    port = discover_native_port()
    results = {}
    for strategy in ("S0_control", "S1_filtered", "S2_guarded"):
        r = httpx.post(f"http://127.0.0.1:{port}/director/_pumpspike",
                       json={"strategy": strategy, "pump_ms": 500}, timeout=30)
        results[strategy] = r.json()
        print(strategy, json.dumps(results[strategy], indent=2))
    Path("pumpspike-evidence.json").write_text(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
```

(Adjust the `discover_native_port` import to the actual helper name in `bridge.py` — verify with a quick grep before running; the runner is throwaway so exact ergonomics don't matter.)

- [ ] **Step 6: Commit (throwaway, clearly marked)**

```bash
git add src/RookNative/Handlers/DirectorHandler.h src/RookNative/Handlers/DirectorHandler.cpp src/RookNative/Threading/MainThreadDispatcher.cpp src/RookNative/RookServer.cpp scripts/_pumpspike_run.py
git commit -m "spike: throwaway pump-spike probe (route + sentinel + S0/S1/S2) — REVERTED in Task 5"
```

---

### Task 4: Run the live spike, record evidence, decide the model

Deploy the spike build, exercise all three strategies against a live Rhino, capture the JSON, and write the verdict into the spec. This is the empirical payload — it cannot be done by reading code.

**Files:**
- Modify: `docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-pumpspike-design.md` (add a "Findings" section with the JSON + the decision)

- [ ] **Step 1: Deploy the spike build with the flag enabled**

Confirm Rhino is running with a document open (the holding lambda does not mutate the document, so any document is fine — no fresh-document fixture needed).

Run: `cmd /c "scripts\deploy-native.bat"`
Then ensure the native plugin process sees `ROOK_DIRECTOR_PUMPSPIKE=1` (set it in the environment before Rhino launches, or per the deploy script's env hook). Verify the route is live: `rhino_ping` should return `pong`.

- [ ] **Step 2: Run the probe for all three strategies**

Run: `mcp_server/.venv/Scripts/python.exe scripts/_pumpspike_run.py`
Expected: prints three JSON blocks and writes `pumpspike-evidence.json`.

- [ ] **Step 3: Check the verdict against the decision table**

Confirm against `docs/.../2026-06-24-...-design.md`:
- **S0 control:** `executed_during_pump: true`, `tasks_executed_during_pump >= 1` (harness validated). If S0 is *clean*, STOP — the harness/pump is unrepresentative; fix before trusting anything.
- **S1 filtered:** record both result and `idle_fired_during_pump`. A "safe" S1 with `idle_fired_during_pump: false` is inconclusive for the idle door.
- **S2 guarded:** must be `queued_during_pump: true`, `tasks_executed_during_pump: 0`, `executed_after_return: true`. `drain_attempt_count` nonzero is expected and good.

- [ ] **Step 4: Write the Findings section into the spec**

Append a `## Findings (live run YYYY-MM-DD)` section to the design doc containing: the three JSON blocks verbatim, the Rhino/build identifiers, and the chosen PR2 model per the decision table:
- **S2 safe** → PR2 builds synchronous replay wrapping its per-frame pump in `DispatchDrainSuspension`.
- **S2 unsafe** → PR2 goes async start/status/cancel.

- [ ] **Step 5: Commit the evidence**

```bash
git add docs/superpowers/specs/2026-06-24-rookvisiondirector-replay-pumpspike-design.md
git commit -m "docs(spike): record live S0/S1/S2 pump-spike findings and PR2 model decision"
```

(Do **not** commit `pumpspike-evidence.json` — it is a scratch artifact; the durable record is the Findings section.)

---

### Task 5: Strip the scaffolding; confirm the durable artifact stands alone

Remove every throwaway piece so the PR ships only the guard + tests + evidence. The shipping rule is a hard gate: the route, sentinel rig, counters, pump bodies, and runner must all be gone.

**Files:**
- Modify: `src/RookNative/Handlers/DirectorHandler.h` / `.cpp` (remove probe)
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp` (remove the gated `drain_attempt_count` hook — restore `DrainQueue` to its Task-2 state)
- Modify: `src/RookNative/RookServer.cpp` (remove the gated route registration)
- Delete: `scripts/_pumpspike_run.py`

- [ ] **Step 1: Revert the throwaway commit's code surface**

Remove `HandleDirectorPumpSpike` (declaration + definition), the sentinel rig, the S0/S1/S2 pump helpers, the `g_pumpSpikeDrainAttempts` definition, the `DrainQueue` increment hook, and the `/director/_pumpspike` registration. Delete `scripts/_pumpspike_run.py`.

- [ ] **Step 2: Verify nothing throwaway remains**

Run: `grep -rn "_pumpspike\|PumpSpike\|ROOK_DIRECTOR_PUMPSPIKE\|g_pumpSpikeDrainAttempts\|PumpSliceDrainAll" src scripts`
Expected: **no matches.** (If any remain, remove them.)

- [ ] **Step 3: Confirm the durable source tests still pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~MainThreadDispatcherSourceTests" --nologo`
Expected: PASS — the guard's structure tests are unaffected by the strip.

- [ ] **Step 4: Confirm native still builds clean without the scaffolding**

Run: `cmd /c "scripts\build-native.bat"`
Expected: build succeeds with only the durable guard present.

- [ ] **Step 5: Confirm the final diff is durable-only**

Run: `git diff origin/main --stat`
Expected: only `MainThreadDispatcher.h`, `MainThreadDispatcher.cpp`, `MainThreadDispatcherSourceTests.cs`, and the spec doc (with Findings). No `DirectorHandler`, `RookServer.cpp`, or `scripts/` changes.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "spike: remove pump-spike scaffolding; ship only the dispatch-drain guard"
```

---

## Self-Review

**Spec coverage:**
- Goal / single contract → Tasks 3–4 (probe measures queued-during / not-executed-during / executed-after-return). ✅
- "after" semantics (lambda return, not guard exit) → Task 3 Step 2 end-of-lambda assertion + `g_holdingLambdaReturned`. ✅
- Durable `DispatchDrainSuspension` (m_suspendDepth, IsAllDispatchBlocked OR, nest-safe, restore-on-destruct, no enqueue block, wake-on-release) → Tasks 1–2. ✅
- Durable tests (depth, restore, enqueue-allowed, wake outermost-only) → Tasks 1–2 source-analysis cases; runtime behaviors validated by Task 4 live S2. ✅
- Throwaway scaffolding gated + removed before reviewable → Task 3 (flag-gated) + Task 5 (strip + grep gate + durable-only diff). ✅
- Both drain doors (idle + WndProc) → Task 3 (S1 filter targets WndProc; `idle_fired_during_pump` covers idle). ✅
- Metric split (`drain_attempt_count` vs `tasks_executed_during_pump`) → Task 3 Step 3 + probe shape. ✅
- Decision table → Task 4 Step 3–4. ✅
- Native-only durable surface, build via scripts → Global Constraints + every build step. ✅

**Placeholder scan:** No "TBD"/"add error handling"/"similar to". The one acknowledged uncertainty (`discover_native_port` helper name) is in throwaway code with an explicit "verify with grep" instruction, not a durable-artifact gap.

**Type consistency:** `BeginSuspendGuard`/`EndSuspendGuard`/`IsDispatchSuspended`/`m_suspendDepth`/`DispatchDrainSuspension` used identically across Tasks 1–3. `g_holdingLambdaReturned`, `g_tasksExecutedDuringPump`, `g_pumpSpikeDrainAttempts` consistent within Task 3 and removed together in Task 5. JSON field names match the spec's Output section exactly.
