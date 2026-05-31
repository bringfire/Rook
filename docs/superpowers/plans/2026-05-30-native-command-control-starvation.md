# Native Command-Control Starvation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revive PR #194 without leaving `/command/prompt`, `/command/send`, or `/command/cancel` vulnerable to starvation behind normal requests in the shared native HTTP worker pool.

**Architecture:** Keep PR #194's native command-depth dispatch policy, but change the command-active behavior for `Normal` dispatch from indefinite deferral to deterministic fast-busy cancellation. `CommandControl` work remains allowed through the main-thread dispatcher, while queued or newly posted normal main-thread work fails quickly when Rhino is command-active so `httplib::ThreadPool(8)` workers are released for command-control requests.

**Tech Stack:** Rhino 8 C++ SDK, RookNative C++17, `cpp-httplib`, Win32 `WM_ROOK_DISPATCH`, xUnit source tests, Visual Studio 2022 MSVC 14.44.

---

## Problem

PR #194 correctly identifies a missing native guard: normal Rook main-thread work must not run while Rhino is inside an active command such as startup recent-file `_Open`.

The draft PR adds:

- `DispatchPolicy::Normal`
- `DispatchPolicy::CommandControl`
- dispatcher-owned command-depth tracking through `CRhinoEventWatcher`
- command-active draining that runs only `CommandControl` tasks and leaves `Normal` tasks queued

That dispatcher-level policy is necessary but not sufficient.

All native HTTP routes share one `httplib::Server` and one fixed task queue:

- command-control routes are registered on the shared server in `src/RookNative/RookServer.cpp`
- the server task queue is `httplib::ThreadPool(8)`

If eight normal requests reach handlers and block on `Dispatch(...).get()` while Rhino is command-active, `/command/prompt`, `/command/send`, and `/command/cancel` may not get an HTTP worker. In that case the command-control request never reaches the handler and never enqueues its `DispatchPolicy::CommandControl` task.

This is a design invariant gap, not a validation-only caveat.

## Required Invariant

When Rhino is command-active:

```text
Normal Rook main-thread work must not execute.
Normal Rook HTTP requests must not occupy all native HTTP workers indefinitely.
/command/prompt, /command/send, and /command/cancel must retain a guaranteed route into CMainThreadDispatcher.
```

`/command/start` is intentionally not included in the command-control exception set. It starts a new command and remains `Normal` dispatch.

## Selected Starvation Fix

Use fast-busy cancellation for `Normal` dispatcher work while command-active.

Behavior:

1. Save guard still blocks all dispatch.
2. If Rhino is command-active, `DrainQueue()` moves `CommandControl` tasks into the local run queue.
3. If Rhino is command-active, `DrainQueue()` cancels `Normal` queued tasks with a deterministic busy exception instead of leaving their futures pending.
4. If Rhino is not command-active, `DrainQueue()` drains all tasks as before.
5. New `Normal` dispatch calls that arrive during command-active still enqueue and post `WM_ROOK_DISPATCH`; the modal message pump then cancels them quickly, releasing their HTTP workers.
6. `CommandControl` dispatch calls are never cancelled by the command-active gate.

This deliberately changes the #194 draft behavior from "normal futures may wait until command end" to "normal futures fail fast while command-active." That tradeoff is acceptable because it fixes the HTTP worker starvation invariant directly. A larger thread pool is not acceptable because it only reduces probability.

## Non-Goals

- Do not increase `httplib::ThreadPool(8)` as the starvation fix.
- Do not add command-name deny lists.
- Do not mark broad document/model routes as `CommandControl`.
- Do not change `/command/start` to `CommandControl`.
- Do not modify managed UI, Vision, WebView, Chat, Knowledge Graph, MCP Python, installer, or project files for this fix.
- Do not guess new Rhino SDK APIs; use only patterns already present in RookNative.

## File Map

- Modify `src/RookNative/Threading/MainThreadDispatcher.h`
  - Add `DispatchPolicy`.
  - Add queued-task cancellation support.
  - Keep `Dispatch(...)` source-compatible with default `DispatchPolicy::Normal`.
- Modify `src/RookNative/Threading/MainThreadDispatcher.cpp`
  - Register/unregister a dispatcher-owned command watcher.
  - Track command depth defensively.
  - Cancel normal queued work while command-active and drain command-control work.
- Modify `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
  - Mark only prompt read, command input send, and cancel as `CommandControl`.
  - Leave `/command/start` as default `Normal`.
  - Remove document object iteration from `/command/send` before making it command-control.
- Modify `src/RookNative/Interactive/PromptManager.cpp`
  - Mark prompt timeout Escape dispatch as `CommandControl`.
- Modify `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs`
  - Keep the current mainline test location.
  - Update tests to assert fast-busy cancellation rather than indefinite normal deferral.
- Remove `src/Rook.Tests/Native/MainThreadDispatcherSourceTests.cs` from the rebased PR if it exists after rebase
  - This file is a stale duplicate from the draft branch.

## Task 1: Rebase PR #194 Onto Current Main

**Files:**
- Modify through rebase only: `src/RookNative/Threading/MainThreadDispatcher.h`
- Modify through rebase only: `src/RookNative/Threading/MainThreadDispatcher.cpp`
- Modify through rebase only: `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
- Modify through rebase only: `src/RookNative/Interactive/PromptManager.cpp`
- Preserve current main changes in: `src/RookNative/RookNativePlugin.cpp`

- [ ] **Step 1: Fetch current refs**

Run:

```powershell
git fetch origin main pull/194/head:refs/remotes/origin/pr/194
```

Expected: `origin/main` and `origin/pr/194` are available locally.

- [ ] **Step 2: Create a local working branch**

Run:

```powershell
git switch -c codex/native-command-control-starvation origin/pr/194
```

Expected: local branch `codex/native-command-control-starvation` points at the PR #194 head.

- [ ] **Step 3: Rebase onto current main**

Run:

```powershell
git rebase origin/main
```

Expected: rebase completes. If conflicts occur, preserve current `origin/main` behavior for release versioning, managed startup quiescence, RookBIM, and MCP Python changes. The native dispatcher files should retain the #194 command-policy changes.

- [ ] **Step 4: Verify branch scope after rebase**

Run:

```powershell
git diff --name-status origin/main...HEAD
```

Expected changed files are limited to:

```text
docs/superpowers/plans/2026-05-26-native-dispatch-command-policy.md
docs/superpowers/specs/2026-05-26-native-dispatch-command-policy-design.md
src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
src/RookNative/Handlers/CommandInteractiveHandler.cpp
src/RookNative/Interactive/PromptManager.cpp
src/RookNative/Threading/MainThreadDispatcher.cpp
src/RookNative/Threading/MainThreadDispatcher.h
```

If `src/Rook.Tests/Native/MainThreadDispatcherSourceTests.cs` appears, remove it in Task 2.

## Task 2: Reconcile Dispatcher Source Tests

**Files:**
- Modify: `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs`
- Delete if present: `src/Rook.Tests/Native/MainThreadDispatcherSourceTests.cs`

- [ ] **Step 1: Remove the stale duplicate test file if it exists**

Run:

```powershell
if (Test-Path 'src/Rook.Tests/Native/MainThreadDispatcherSourceTests.cs') {
    git rm 'src/Rook.Tests/Native/MainThreadDispatcherSourceTests.cs'
}
```

Expected: the stale `Native` namespace duplicate is removed from the branch if rebase introduced it.

- [ ] **Step 2: Replace the mainline source tests**

Edit `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs` so it contains these tests:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Threading
{
    public class MainThreadDispatcherSourceTests
    {
        [Fact]
        public void Dispatch_DefaultsToNormalPolicy()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");

            Assert.Contains("DispatchPolicy policy = DispatchPolicy::Normal", source);
            Assert.Contains("enum class DispatchPolicy", source);
            Assert.Contains("CommandControl", source);
        }

        [Fact]
        public void QueuedTask_CarriesPolicyTaskAndCancel()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.h");
            var queuedTask = ExtractStruct(source, "QueuedTask");

            Assert.Contains("DispatchPolicy policy", queuedTask);
            Assert.Contains("std::function<void()> task", queuedTask);
            Assert.Contains("std::function<void()> cancel", queuedTask);
        }

        [Fact]
        public void DrainQueue_BlocksAllDispatchDuringSave()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var drainQueue = ExtractFunction(source, "CMainThreadDispatcher::DrainQueue");

            Assert.Contains("if (IsAllDispatchBlocked())", drainQueue);
            Assert.True(
                drainQueue.IndexOf("if (IsAllDispatchBlocked())", StringComparison.Ordinal)
                < drainQueue.IndexOf("IsNormalDispatchBlocked()", StringComparison.Ordinal),
                "Save guard must block before command-control filtering.");
        }

        [Fact]
        public void DrainQueue_CommandActiveRunsCommandControlAndCancelsNormal()
        {
            var source = ReadSourceFile("src", "RookNative", "Threading", "MainThreadDispatcher.cpp");
            var drainQueue = ExtractFunction(source, "CMainThreadDispatcher::DrainQueue");

            Assert.Contains("const bool normalDispatchBlocked = IsNormalDispatchBlocked();", drainQueue);
            Assert.Contains("queued.policy == DispatchPolicy::CommandControl", drainQueue);
            Assert.Contains("commandControl.push(std::move(queued))", drainQueue);
            Assert.Contains("blockedNormal.push(std::move(queued))", drainQueue);
            Assert.Contains("CancelQueuedTasks", drainQueue);
        }

        [Fact]
        public void CommandInteractive_OnlyPromptSendAndCancelUseCommandControl()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "CommandInteractiveHandler.cpp");
            var prompt = ExtractFunction(source, "TryReadPromptOnMain");
            var start = ExtractFunction(source, "HandleCommandStart");
            var input = ExtractFunction(source, "HandleCommandInput");
            var cancel = ExtractFunction(source, "HandleCommandCancel");

            Assert.Contains("DispatchPolicy::CommandControl", prompt);
            Assert.DoesNotContain("DispatchPolicy::CommandControl", start);
            Assert.Contains("DispatchPolicy::CommandControl", input);
            Assert.Contains("DispatchPolicy::CommandControl", cancel);
            Assert.DoesNotContain("CRhinoObjectIterator", input);
            Assert.DoesNotContain("objects_before", input);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName + "(", StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Function body not found: " + functionName);

            var bodyEnd = FindMatchingBrace(source, bodyStart);
            return source.Substring(signatureStart, bodyEnd - signatureStart + 1);
        }

        private static string ExtractStruct(string source, string structName)
        {
            var signatureStart = source.IndexOf("struct " + structName, StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Struct not found: " + structName);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Struct body not found: " + structName);

            var bodyEnd = FindMatchingBrace(source, bodyStart);
            return source.Substring(signatureStart, bodyEnd - signatureStart + 1);
        }

        private static int FindMatchingBrace(string source, int openBraceIndex)
        {
            var depth = 0;
            for (var i = openBraceIndex; i < source.Length; i++)
            {
                if (source[i] == '{')
                    depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return i;
                }
            }

            throw new InvalidOperationException("Brace did not close at index " + openBraceIndex);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException("Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
```

- [ ] **Step 3: Run the source-test filter and confirm it fails before implementation**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: tests fail because `QueuedTask` does not yet expose `cancel`, and `DrainQueue()` still defers normal tasks instead of cancelling them.

- [ ] **Step 4: Commit the test reconciliation**

Run:

```powershell
git add src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
if (Test-Path 'src/Rook.Tests/Native') {
    git add -u src/Rook.Tests/Native
}
git commit -m "test: specify native command-control starvation guard"
```

Expected: commit records the mainline test location and removes stale duplicate tests.

## Task 3: Implement Fast-Busy Cancellation For Normal Dispatch

**Files:**
- Modify: `src/RookNative/Threading/MainThreadDispatcher.h`
- Modify: `src/RookNative/Threading/MainThreadDispatcher.cpp`

- [ ] **Step 1: Add cancellable queued tasks**

In `src/RookNative/Threading/MainThreadDispatcher.h`, move `struct QueuedTask` above any private method declaration that mentions `QueuedTask`, including `CancelQueuedTasks(...)`. Keep `m_queue` below the struct. The private dispatcher section should include this ordering:

```cpp
struct QueuedTask
{
    DispatchPolicy policy = DispatchPolicy::Normal;
    std::function<void()> task;
    std::function<void()> cancel;
};

// Called by CIdleWatcher::Notify AND SubclassProc on the main thread.
void DrainQueue();
static void CancelQueuedTasks(std::queue<QueuedTask>& tasks);
bool IsAllDispatchBlocked() const { return m_saveDepth.load(std::memory_order_acquire) > 0; }
bool IsNormalDispatchBlocked() const;

std::queue<QueuedTask> m_queue;
```

Expected: each queued task can either run normally or fail its future explicitly.

- [ ] **Step 2: Replace packaged-task queueing with promise-backed queueing**

In the `Dispatch` template in `src/RookNative/Threading/MainThreadDispatcher.h`, replace the block that creates and queues `std::packaged_task` with this promise-backed implementation:

```cpp
auto promise = std::make_shared<std::promise<ReturnType>>();
future = promise->get_future();

auto taskFunc = std::make_shared<std::decay_t<F>>(std::forward<F>(func));
m_queue.push(QueuedTask{
    policy,
    [promise, taskFunc]() mutable
    {
        try
        {
            if constexpr (std::is_void_v<ReturnType>)
            {
                (*taskFunc)();
                promise->set_value();
            }
            else
            {
                promise->set_value((*taskFunc)());
            }
        }
        catch (...)
        {
            promise->set_exception(std::current_exception());
        }
    },
    [promise]()
    {
        promise->set_exception(std::make_exception_ptr(
            std::runtime_error("RookNative dispatcher is busy: Rhino command is active")));
    }
});
```

Expected: queued tasks still propagate return values and exceptions through futures, and cancelled tasks now return a deterministic busy exception instead of waiting for command end.

- [ ] **Step 3: Add a private helper to cancel queued tasks outside the queue lock**

In `src/RookNative/Threading/MainThreadDispatcher.h`, confirm this private method declaration appears after `struct QueuedTask` has been defined:

```cpp
static void CancelQueuedTasks(std::queue<QueuedTask>& tasks);
```

In `src/RookNative/Threading/MainThreadDispatcher.cpp`, implement:

```cpp
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
```

Expected: cancellation executes outside `m_mutex`, matching the existing run-outside-lock pattern, without exposing `QueuedTask` outside the dispatcher class.

- [ ] **Step 4: Replace command-active deferral with command-control run plus normal cancellation**

In `CMainThreadDispatcher::DrainQueue()`, replace the command-active filtering block with:

```cpp
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

CancelQueuedTasks(blockedNormal);
```

Keep the existing loop that executes `local` tasks after this block.

Expected: while command-active, command-control tasks run and normal tasks fail fast.

- [ ] **Step 5: Keep save guard stronger than command-control**

Confirm `DrainQueue()` still begins with:

```cpp
if (IsAllDispatchBlocked())
    return;
```

Expected: save commands still block all dispatch, including command-control, preserving the existing save serialization guard.

- [ ] **Step 6: Run the source-test filter**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: all `MainThreadDispatcherSourceTests` pass.

- [ ] **Step 7: Commit the dispatcher starvation fix**

Run:

```powershell
git add src/RookNative/Threading/MainThreadDispatcher.h src/RookNative/Threading/MainThreadDispatcher.cpp src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
git commit -m "fix: fail normal dispatch fast during active commands"
```

Expected: commit records the deterministic starvation fix.

## Task 4: Preserve Narrow Command-Control Call Sites

**Files:**
- Modify: `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
- Modify: `src/RookNative/Interactive/PromptManager.cpp`

- [ ] **Step 1: Keep prompt reads command-control**

In `TryReadPromptOnMain`, ensure dispatch is:

```cpp
auto future = CMainThreadDispatcher::Instance().Dispatch([]() -> std::string {
    ON_wString prompt;
    RhinoApp().GetCommandPrompt(prompt);
    return WideToUtf8(prompt);
}, DispatchPolicy::CommandControl);
```

Expected: `/command/prompt` can read prompt text during an active command.

- [ ] **Step 2: Keep `/command/start` normal**

In `HandleCommandStart`, ensure its `Dispatch(...)` call does not pass `DispatchPolicy::CommandControl`.

Expected: starting a new command remains blocked/busy while another Rhino command is active.

- [ ] **Step 3: Keep `/command/send` command-control without model iteration**

In `HandleCommandInput`, ensure the dispatched lambda contains only document serial lookup and `RhinoApp().RunScript(...)`:

```cpp
auto future = CMainThreadDispatcher::Instance().Dispatch([&]() {
    CRhinoDoc* pDoc = GetDocument();
    unsigned int docSn = pDoc ? pDoc->RuntimeSerialNumber() : 0;

    ON_wString wInput = Utf8ToWide(input);
    wInput += L"\n";
    RhinoApp().RunScript(docSn, static_cast<const wchar_t*>(wInput), 0);
}, DispatchPolicy::CommandControl);
```

Ensure the response omits `objects_before`.

Expected: `/command/send` does not iterate document objects while command-active.

- [ ] **Step 4: Keep `/command/cancel` command-control**

In `HandleCommandCancel`, ensure the cancel dispatch passes `DispatchPolicy::CommandControl`.

Expected: cancel can reach Rhino during an active command once an HTTP worker is available.

- [ ] **Step 5: Keep prompt timeout Escape command-control**

In `PostEscapeToRhino()` in `PromptManager.cpp`, ensure the dispatch call ends with:

```cpp
}, DispatchPolicy::CommandControl);
```

Expected: prompt timeout recovery is not cancelled by the command-active normal-dispatch gate.

- [ ] **Step 6: Run the source-test filter**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: command-control call-site assertions pass.

- [ ] **Step 7: Commit call-site scope**

Run:

```powershell
git add src/RookNative/Handlers/CommandInteractiveHandler.cpp src/RookNative/Interactive/PromptManager.cpp src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
git commit -m "fix: keep command-control dispatch scope narrow"
```

Expected: commit records the audited command-control scope.

## Task 5: Automated Validation

**Files:**
- Read only unless failures require fixes:
  - `src/RookNative/Threading/MainThreadDispatcher.h`
  - `src/RookNative/Threading/MainThreadDispatcher.cpp`
  - `src/RookNative/Handlers/CommandInteractiveHandler.cpp`
  - `src/RookNative/Interactive/PromptManager.cpp`
  - `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs`

- [ ] **Step 1: Run dispatcher source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: all filtered tests pass.

- [ ] **Step 2: Run plugin lifecycle source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RookPluginLifecycleSourceTests|FullyQualifiedName~CompanionStartupGateTests"
```

Expected: tests pass, proving #195 managed startup quiescence remains intact.

- [ ] **Step 3: Run whitespace validation**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: no whitespace errors.

- [ ] **Step 4: Run native build with MSVC 14.44**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: native build succeeds with `0 Error(s)`. Do not claim native build verification if this command was not run successfully on a machine with the Rhino/MFC toolchain.

- [ ] **Step 5: Commit validation-only test adjustments if any were needed**

If validation required test-only changes, run:

```powershell
git add src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
git commit -m "test: cover command-control starvation readiness"
```

Expected: no commit is created if no validation-only changes were needed.

## Task 6: Live Rhino Validation

**Files:**
- No file edits expected.

- [ ] **Step 1: Deploy the rebased branch locally**

Run:

```powershell
scripts\deploy-local-testing.ps1
```

Expected: Rhino loads the updated native plugin.

- [ ] **Step 2: Repeat the startup recent-file `_Open` gate**

Manual steps:

```text
1. Close Rhino.
2. Launch Rhino.
3. On the startup screen, click a recent file quickly.
4. Confirm _Open completes.
5. Confirm the command line accepts ESC and ENTER.
6. Confirm the main window closes normally.
7. Confirm resize/repaint is coherent and panels are not smeared.
8. Repeat several times, including at least one slow file if available.
```

Expected: Rhino does not wedge during startup/open.

- [ ] **Step 3: Run command-control worker saturation validation**

Manual stress procedure:

```text
1. Start an interactive Rhino command that remains active, such as _Line.
2. From a script or eight terminals, issue eight normal native HTTP requests that require main-thread document/model dispatch and wait for responses.
3. While those requests are pending or returning busy, call GET /command/prompt.
4. Confirm /command/prompt returns a prompt response instead of waiting for all normal requests to finish.
5. Call POST /command/send with a valid input for the active command.
6. Confirm the command receives the input.
7. Call POST /command/cancel.
8. Confirm the command cancels and the prompt returns to idle.
9. Confirm the normal requests return deterministic busy/error responses instead of occupying all workers until command end.
```

Expected: command-control routes remain serviceable under normal-request saturation.

- [ ] **Step 4: Record live validation in the PR body**

Add a PR validation note with:

```markdown
## Live Validation

- Rebased onto current `main`.
- Native MSVC 14.44 build passed.
- Startup recent-file `_Open` gate repeated successfully.
- Worker saturation validation passed: while Rhino command-active, eight normal dispatch requests returned busy/error responses and `/command/prompt`, `/command/send`, and `/command/cancel` remained serviceable.
```

Expected: PR #194 is not marked ready until this section is true.

## Readiness Bar

PR #194 must remain draft until all of these are true:

```text
1. Branch is rebased onto current main.
2. Duplicate stale dispatcher source tests are removed or merged.
3. Normal dispatch cannot starve command-control routes under the shared httplib worker pool.
4. Filtered source tests pass.
5. Native MSVC 14.44 build passes.
6. Live recent-file _Open startup gate passes repeatedly.
7. Live worker saturation validation proves /command/prompt, /command/send, and /command/cancel remain serviceable.
```
