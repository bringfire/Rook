# Native Dispatcher Command Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent normal Rook main-thread work from executing inside active Rhino command loops while preserving explicit command-control operations.

**Architecture:** Add per-task dispatch policy to the native main-thread dispatcher. A dedicated dispatcher-owned command watcher tracks Rhino command depth; during active commands the dispatcher drains only `CommandControl` tasks and keeps `Normal` tasks queued in original order until command depth returns to zero.

**Tech Stack:** C++17, Rhino 8 C++ SDK, `CRhinoEventWatcher`, `CRhinoIsIdle`, Win32 `WM_ROOK_DISPATCH`, existing RookNative dispatcher.

---

## Scope Guard

This PR is native dispatcher lifecycle safety only.

Do not modify managed UI, WebView, Vision, Chat, Knowledge Graph, MCP Python, installer, or project files. Do not add command-name denylists. Do not mark broad HTTP/model handlers as `CommandControl`.

Expected files:

- Modify: `src/RookNative/Threading/MainThreadDispatcher.h`
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp`
- Modify: `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
- Modify: `src/RookNative/Interactive/PromptManager.cpp`
- Add/modify tests only if an existing native/unit harness can support them without project-file changes.

## Task 1: Add Dispatch Policy And Policy-Preserving Queue

**Files:**
- Modify: `src/RookNative/Threading/MainThreadDispatcher.h`
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp`

- [ ] **Step 1: Add policy enum and queued item type**

In `MainThreadDispatcher.h`, add this enum before `class CMainThreadDispatcher`:

```cpp
enum class DispatchPolicy
{
    Normal,
    CommandControl
};
```

Inside `CMainThreadDispatcher`, replace:

```cpp
std::queue<std::function<void()>> m_queue;
```

with:

```cpp
struct QueuedTask
{
    DispatchPolicy policy = DispatchPolicy::Normal;
    std::function<void()> task;
};

std::queue<QueuedTask> m_queue;
```

- [ ] **Step 2: Add policy parameter to Dispatch**

Change the declaration:

```cpp
template<typename F>
auto Dispatch(F&& func) -> std::future<std::invoke_result_t<F>>;
```

to:

```cpp
template<typename F>
auto Dispatch(
    F&& func,
    DispatchPolicy policy = DispatchPolicy::Normal)
    -> std::future<std::invoke_result_t<F>>;
```

Change the template definition signature the same way.

Replace the queue push:

```cpp
m_queue.push([task]() { (*task)(); });
```

with:

```cpp
m_queue.push(QueuedTask{
    policy,
    [task]() { (*task)(); }
});
```

- [ ] **Step 3: Update Stop discard type**

In `MainThreadDispatcher.cpp`, update the discard queue type in `Stop()`:

```cpp
std::queue<QueuedTask> discard;
```

Keep the existing `std::swap(discard, m_queue);` behavior.

- [ ] **Step 4: Update DrainQueue execution for wrapped tasks**

In `DrainQueue()`, where tasks are executed, change:

```cpp
auto task = std::move(local.front());
local.pop();
try
{
    task();
}
```

to:

```cpp
auto queued = std::move(local.front());
local.pop();
try
{
    queued.task();
}
```

- [ ] **Step 5: Build-check this compatibility slice**

Run the native build command from repo instructions:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds. If native toolchain is unavailable, stop and report the blocker; do not claim build verification.

- [ ] **Step 6: Commit**

```powershell
git add src\RookNative\Threading\MainThreadDispatcher.h src\RookNative\Threading\MainThreadDispatcher.cpp
git commit -m "feat: add native dispatch policy"
```

## Task 2: Add Dispatcher-Owned Command Lifecycle Gate

**Files:**
- Modify: `src/RookNative/Threading/MainThreadDispatcher.h`
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp`

- [ ] **Step 1: Add command-depth API and watcher declaration**

In `MainThreadDispatcher.h`, add public methods near the existing save guard:

```cpp
void BeginCommandGuard();
void EndCommandGuard();
bool IsCommandActive() const { return m_commandDepth.load(std::memory_order_acquire) > 0; }
```

Add a private watcher class next to `CIdleWatcher`:

```cpp
class CCommandWatcher : public CRhinoEventWatcher
{
public:
    explicit CCommandWatcher(CMainThreadDispatcher& owner);
    void OnBeginCommand(
        const CRhinoCommand& command,
        const CRhinoCommandContext& context) override;
    void OnEndCommand(
        const CRhinoCommand& command,
        const CRhinoCommandContext& context,
        CRhinoCommand::result rc) override;
private:
    CMainThreadDispatcher& m_owner;
};
```

Add members:

```cpp
std::unique_ptr<CCommandWatcher> m_commandWatcher;
std::atomic<int> m_commandDepth{0};
```

- [ ] **Step 2: Register, enable, disable, and unregister the watcher**

In `Start(...)`, after idle watcher registration and before `m_running.store(true);`, add:

```cpp
m_commandWatcher = std::make_unique<CCommandWatcher>(*this);
m_commandWatcher->Register();
m_commandWatcher->Enable(TRUE);
```

In `Stop()`, before unregistering the idle watcher, add:

```cpp
if (m_commandWatcher)
{
    m_commandWatcher->Enable(FALSE);
    m_commandWatcher->UnRegister();
    m_commandWatcher.reset();
}
m_commandDepth.store(0, std::memory_order_release);
```

- [ ] **Step 3: Implement command guard methods**

In `MainThreadDispatcher.cpp`, add:

```cpp
void CMainThreadDispatcher::BeginCommandGuard()
{
    m_commandDepth.fetch_add(1, std::memory_order_acq_rel);
}

void CMainThreadDispatcher::EndCommandGuard()
{
    int current = m_commandDepth.load(std::memory_order_acquire);
    while (current > 0)
    {
        if (m_commandDepth.compare_exchange_weak(
                current,
                current - 1,
                std::memory_order_acq_rel,
                std::memory_order_acquire))
        {
            if (current == 1)
            {
                HWND hWnd = RhinoApp().MainWnd();
                if (hWnd != nullptr)
                    ::PostMessage(hWnd, WM_ROOK_DISPATCH, 0, 0);
            }
            return;
        }
    }

    m_commandDepth.store(0, std::memory_order_release);
}
```

This prevents underflow and posts a deterministic wake only on transition from one active command to zero.

- [ ] **Step 4: Implement command watcher callbacks**

In `MainThreadDispatcher.cpp`, add:

```cpp
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
```

- [ ] **Step 5: Keep SessionRecorder save guard for now**

Do not remove `BeginSaveGuard()` / `EndSaveGuard()` from `SessionRecorder` in this task. The new command-depth gate protects the broader active-command lifecycle; the save guard remains as an extra conservative file-serialization guard in this PR.

- [ ] **Step 6: Build-check command watcher slice**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds.

- [ ] **Step 7: Commit**

```powershell
git add src\RookNative\Threading\MainThreadDispatcher.h src\RookNative\Threading\MainThreadDispatcher.cpp
git commit -m "feat: track native command-active dispatch gate"
```

## Task 3: Filter Command-Active Drains Without Reordering Normal Work

**Files:**
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp`
- Modify: `src/RookNative/Threading/MainThreadDispatcher.h`

- [ ] **Step 1: Add helper declarations**

In `MainThreadDispatcher.h`, add private helper declarations:

```cpp
bool IsAllDispatchBlocked() const
{
    return m_saveDepth.load(std::memory_order_acquire) > 0;
}

bool IsNormalDispatchBlocked() const
{
    return m_commandDepth.load(std::memory_order_acquire) > 0;
}
```

- [ ] **Step 2: Keep save-depth as all-dispatch block**

In `DrainQueue()`, replace the current save guard:

```cpp
if (m_saveDepth.load(std::memory_order_acquire) > 0)
    return;
```

with:

```cpp
if (IsAllDispatchBlocked())
    return;
```

Save remains stricter than command-active filtering: while save depth is active,
drain nothing and preserve all queued work. Do not allow `CommandControl` to run
during save in this PR.

- [ ] **Step 3: Replace swap block with command-active policy filtering**

Replace the existing swap block with policy-aware filtering:

```cpp
const bool normalBlocked = IsNormalDispatchBlocked();

std::queue<QueuedTask> local;
std::queue<QueuedTask> deferred;
{
    std::lock_guard<std::mutex> lock(m_mutex);
    while (!m_queue.empty())
    {
        auto queued = std::move(m_queue.front());
        m_queue.pop();

        if (normalBlocked && queued.policy == DispatchPolicy::Normal)
        {
            deferred.push(std::move(queued));
        }
        else
        {
            local.push(std::move(queued));
        }
    }

    if (!deferred.empty())
    {
        std::swap(m_queue, deferred);
    }
}
```

This preserves normal task order: during command-active drains, `Normal A` and `Normal C` stay in `deferred` in their original order while `CommandControl B` moves to `local`.

- [ ] **Step 4: Keep execution outside the lock**

Ensure the existing execution loop remains after the lock and executes only `local`.

The loop should look like:

```cpp
while (!local.empty())
{
    auto queued = std::move(local.front());
    local.pop();
    try
    {
        queued.task();
    }
    catch (...)
    {
        // packaged_task captures exceptions into the future.
    }
}
```

- [ ] **Step 5: Make save guard post wake on release**

Change `EndSaveGuard()` in `MainThreadDispatcher.h` from inline decrement to a declared method:

```cpp
void EndSaveGuard();
```

Keep `BeginSaveGuard()` inline or move it beside `EndSaveGuard()`.

In `MainThreadDispatcher.cpp`, implement:

```cpp
void CMainThreadDispatcher::EndSaveGuard()
{
    int current = m_saveDepth.load(std::memory_order_acquire);
    while (current > 0)
    {
        if (m_saveDepth.compare_exchange_weak(
                current,
                current - 1,
                std::memory_order_acq_rel,
                std::memory_order_acquire))
        {
            if (current == 1 && !IsCommandActive())
            {
                HWND hWnd = RhinoApp().MainWnd();
                if (hWnd != nullptr)
                    ::PostMessage(hWnd, WM_ROOK_DISPATCH, 0, 0);
            }
            return;
        }
    }

    m_saveDepth.store(0, std::memory_order_release);
}
```

- [ ] **Step 6: Add source-level policy tests if native test harness is absent**

If there is no native unit test harness already configured, add focused source-level tests to the managed test suite only if they do not require project-file changes. Use a test file under `src/Rook.Tests/UI` or existing test area that reads `MainThreadDispatcher.*` and verifies these strings:

```csharp
Assert.Contains("enum class DispatchPolicy", header);
Assert.Contains("DispatchPolicy::Normal", header);
Assert.Contains("DispatchPolicy::CommandControl", header);
Assert.Contains("std::queue<QueuedTask> deferred", source);
Assert.Contains("deferred.push(std::move(queued))", source);
Assert.Contains("local.push(std::move(queued))", source);
Assert.Contains("bool IsAllDispatchBlocked() const", header);
Assert.Contains("if (IsAllDispatchBlocked())", source);
Assert.Contains("m_commandWatcher->Enable(TRUE);", source);
Assert.Contains("m_commandWatcher->Enable(FALSE);", source);
Assert.Contains("PostMessage(hWnd, WM_ROOK_DISPATCH", source);
```

Do not edit `.vcxproj` or `.vcxproj.filters` to add a native test project.

- [ ] **Step 7: Build and run relevant tests**

Run native build:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

If source-level tests were added, run:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Native|FullyQualifiedName~Dispatcher"
```

- [ ] **Step 8: Commit**

```powershell
git add src\RookNative\Threading\MainThreadDispatcher.h src\RookNative\Threading\MainThreadDispatcher.cpp src\Rook.Tests
git commit -m "feat: defer normal dispatch during active commands"
```

## Task 4: Mark Only Explicit Command-Control Dispatches

**Files:**
- Modify: `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
- Modify: `src/RookNative/Interactive/PromptManager.cpp`

- [ ] **Step 1: Mark `/command/prompt` prompt read as CommandControl**

In `TryReadPromptOnMain(...)`, change:

```cpp
auto future = CMainThreadDispatcher::Instance().Dispatch([&]() -> std::string {
```

to:

```cpp
auto future = CMainThreadDispatcher::Instance().Dispatch([&]() -> std::string {
```

and add the policy argument after the lambda:

```cpp
}, DispatchPolicy::CommandControl);
```

The final call should dispatch only `RhinoApp().GetCommandPrompt(prompt);` and return the prompt string.

- [ ] **Step 2: Do not mark `/command/start` as CommandControl**

Leave `HandleCommandStart` default `Normal`. It starts a new command and counts objects; it must not run inside an active Rhino command loop.

- [ ] **Step 3: Remove `/command/send` object iteration before marking CommandControl**

In `HandleCommandInput`, change the dispatched lambda return type from `int` to `void`.

Replace:

```cpp
auto future = CMainThreadDispatcher::Instance().Dispatch([&]() -> int {
    CRhinoDoc* pDoc = GetDocument();
    unsigned int docSn = pDoc ? pDoc->RuntimeSerialNumber() : 0;
    int count = 0;
    if (pDoc) {
        CRhinoObjectIterator iter(*pDoc,
            CRhinoObjectIterator::normal_or_locked_objects,
            CRhinoObjectIterator::active_objects);
        for (const CRhinoObject* obj = iter.First(); obj; obj = iter.Next())
            ++count;
    }

    ON_wString wInput = Utf8ToWide(input);
    wInput += L"\n";
    RhinoApp().RunScript(docSn, static_cast<const wchar_t*>(wInput), 0);

    return count;
});

int objectsBefore = future.get();
```

with:

```cpp
auto future = CMainThreadDispatcher::Instance().Dispatch([&]() {
    CRhinoDoc* pDoc = GetDocument();
    unsigned int docSn = pDoc ? pDoc->RuntimeSerialNumber() : 0;

    ON_wString wInput = Utf8ToWide(input);
    wInput += L"\n";
    RhinoApp().RunScript(docSn, static_cast<const wchar_t*>(wInput), 0);
}, DispatchPolicy::CommandControl);

future.get();
```

Remove:

```cpp
result["objects_before"] = objectsBefore;
```

Keep:

```cpp
result["input_sent"] = input;
result["sent"] = true;
result["note"] = "Poll /command/prompt to get actual prompt after ~100ms";
```

- [ ] **Step 4: Mark `/command/cancel` as CommandControl**

In `HandleCommandCancel`, change the cancel dispatch call to pass `DispatchPolicy::CommandControl`:

```cpp
auto future = CMainThreadDispatcher::Instance().Dispatch([&]() {
    CRhinoDoc* pDoc = GetDocument();
    unsigned int docSn = pDoc ? pDoc->RuntimeSerialNumber() : 0;

    ON_wString cancelScript(L"_Cancel\n");
    RhinoApp().RunScript(docSn, static_cast<const wchar_t*>(cancelScript), 0);
}, DispatchPolicy::CommandControl);
```

- [ ] **Step 5: Mark prompt timeout escape as CommandControl**

In `PromptManager.cpp`, update `PostEscapeToRhino()`:

```cpp
CMainThreadDispatcher::Instance().Dispatch([]() {
    HWND hWnd = RhinoApp().MainWnd();
    if (hWnd)
        ::PostMessage(hWnd, WM_KEYDOWN, VK_ESCAPE, 0);
}, DispatchPolicy::CommandControl);
```

Do not mark the prompt-starting `PromptForPoint`, `PromptForObject`, `PromptForObjects`, or subobject prompt dispatches as `CommandControl`; those initiate Rhino modal prompts and remain default `Normal`.

- [ ] **Step 6: Add source-level audit checks**

If no native unit test harness exists, add source-level tests that verify:

```csharp
Assert.Contains("DispatchPolicy::CommandControl", commandInteractiveSource);
Assert.Contains("DispatchPolicy::CommandControl", promptManagerSource);
Assert.DoesNotContain("objects_before", ExtractMethod(commandInteractiveSource, "void HandleCommandInput"));
Assert.DoesNotContain("CRhinoObjectIterator", ExtractMethod(commandInteractiveSource, "void HandleCommandInput"));
Assert.Contains("DispatchPolicy::CommandControl", ExtractMethod(commandInteractiveSource, "PromptRead TryReadPromptOnMain"));
Assert.Contains("DispatchPolicy::CommandControl", ExtractMethod(commandInteractiveSource, "void HandleCommandCancel"));
Assert.DoesNotContain("DispatchPolicy::CommandControl", ExtractMethod(commandInteractiveSource, "void HandleCommandStart"));
```

- [ ] **Step 7: Build and run tests**

Run native build:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Run focused managed/source tests if added:

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~Native|FullyQualifiedName~Dispatcher|FullyQualifiedName~Command"
```

- [ ] **Step 8: Commit**

```powershell
git add src\RookNative\Handlers\CommandInteractiveHandler.cpp src\RookNative\Interactive\PromptManager.cpp src\Rook.Tests
git commit -m "fix: keep command-control dispatch narrow"
```

## Task 5: Final Verification And Live-Test Handoff

**Files:**
- No code changes expected unless verification exposes issues.

- [ ] **Step 1: Run whitespace check**

```powershell
git diff --check origin/main...HEAD
```

Expected: no output, exit 0.

- [ ] **Step 2: Run native build**

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds.

- [ ] **Step 3: Run managed tests if source-level tests were added**

```powershell
dotnet test .\src\Rook.Tests\Rook.Tests.csproj --no-restore
```

Expected: tests pass.

- [ ] **Step 4: Review diff scope**

Run:

```powershell
git diff --name-status origin/main...HEAD
```

Expected files are limited to:

```text
docs/superpowers/specs/2026-05-26-native-dispatch-command-policy-design.md
docs/superpowers/plans/2026-05-26-native-dispatch-command-policy.md
src/RookNative/Threading/MainThreadDispatcher.h
src/RookNative/Threading/MainThreadDispatcher.cpp
src/RookNative/Handlers/CommandInteractiveHandler.cpp
src/RookNative/Interactive/PromptManager.cpp
optional source-level tests under src/Rook.Tests
```

If managed UI/WebView/Vision/Chat/KG files appear, stop and remove them from this PR.

- [ ] **Step 5: Prepare live validation instructions**

Do not claim Vision is fixed. Live gate is:

```text
1. Deploy this branch locally.
2. Launch Rhino.
3. On the startup screen, click a recent file quickly.
4. Confirm `_Open` completes.
5. Confirm Rhino remains responsive:
   - command line accepts ESC/ENTER
   - main window closes normally
   - resize/repaint is coherent
   - no smeared panels
6. Repeat several times.
7. Verify `/command/prompt` and `/command/cancel` still work when intentionally inside an active command.
```

- [ ] **Step 6: Push/create draft PR only after verification**

Create a PR body file:

```powershell
$nativeResult = "Native build passed"
$managedResult = "Managed/source tests passed or were not needed"
$diffCheckResult = "git diff --check origin/main...HEAD passed"

$body = @'
## Summary

Adds a native dispatcher command-active policy so normal Rook main-thread work waits while Rhino is inside an active command loop. Explicit command-control work remains able to run during modal command loops.

This is a lifecycle safety PR, not a Vision panel fix. PR #193 remains paused until this guard passes live startup recent-file validation.

## What changed

- Adds `DispatchPolicy` per queued dispatcher task.
- Defaults existing dispatch calls to `Normal`.
- Tracks native command depth in a dispatcher-owned lifecycle watcher.
- Drains only `CommandControl` work while command depth is active.
- Preserves queued `Normal` task order for post-command drain.
- Marks only prompt/cancel/send/escape control paths as `CommandControl`.

## Validation

- NATIVE_RESULT
- MANAGED_RESULT
- DIFF_CHECK_RESULT

## Live gate before ready

Launch Rhino, click a recent file from the startup screen, and confirm `_Open` completes without wedging Rhino. Repeat several times. Do not use this PR to claim Vision dark-panel success.
'@

$body = $body.Replace("NATIVE_RESULT", $nativeResult)
$body = $body.Replace("MANAGED_RESULT", $managedResult)
$body = $body.Replace("DIFF_CHECK_RESULT", $diffCheckResult)
$body | Set-Content -Path $env:TEMP\rook-native-dispatch-policy-pr.md

git status --short --branch
git push -u origin codex/native-dispatch-command-policy
gh pr create --draft --base main --head codex/native-dispatch-command-policy --title "[codex] Native dispatcher command-active policy" --body-file $env:TEMP\rook-native-dispatch-policy-pr.md
```
