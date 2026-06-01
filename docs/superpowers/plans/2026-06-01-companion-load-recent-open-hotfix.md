# Companion Load Recent-Open Hotfix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent recent-file `_Open` startup from permanently stranding native-managed companion activation when normal main-thread dispatch is cancelled while Rhino is command-active.

**Architecture:** Keep the current architecture intact: RookNative eagerly/deferred-requests the managed companion, the managed companion remains internal, and companion loading still uses normal dispatcher policy rather than `CommandControl`. The hotfix classifies companion-load outcomes explicitly so command-active dispatcher cancellation means "not safe yet, retry later" instead of "abort this session." Live readiness remains truthful through `/capabilities`; this PR does not change discovery semantics, route ownership, installer layout, or managed visibility.

**Tech Stack:** Rhino 8 C++ SDK, RookNative C++ plugin, `CMainThreadDispatcher`, xUnit source/contract tests, MSVC 14.44 Debug x64 build, live Rhino recent-file `_Open` validation.

---

## Repro Boundary

Observed failure:

- Reproduces with recent-file startup/open where RookNative loads while Rhino is already inside an active `_Open` lifecycle.
- Does not reproduce with direct file open in the same way.
- The recent-file path can make the first normal-dispatch companion-load request run while command-active dispatch is blocked.

Observed failure shape from June 1, 2026:

- RookNative startup/discovery at about `11:23:28`.
- Recent-file `_Open` active during startup/open lifecycle.
- Managed companion `OnLoad` absent until `ShowRookChat` was typed later.
- `ShowRookChat` printed "Rook Chat panel could not be shown" and then `Rook: native GH callback bridge registered.`
- Companion status later showed `startupComplete: true` and `panelsRegistered: true`, proving the companion loaded only after the command-triggered `WhenNeeded` path.

Target behavior:

- During recent-file `_Open`, normal dispatch cancellation is classified as `NotSafeYet`.
- The companion-load thread remains alive until safe idle, shutdown, actual load failure budget exhaustion, or a bounded startup deadline.
- After safe idle, the native thread attempts `LoadPlugIn`, the companion loads, panels register, and `ShowRookChat` opens without racing panel registration.

## Non-Goals

- No Phase 2 capability, diagnostics, installer, or modularity work.
- No route ownership changes.
- No managed public HTTP surface.
- No discovery/capability truth changes.
- No on-demand-only loading shift.
- No `DispatchPolicy::CommandControl` companion-load bypass.
- No `.vcxproj` or `.vcxproj.filters` edits.

## Files

- Modify: `src/RookNative/RookNativePlugin.cpp`
  - Add explicit companion-load result classification.
  - Add bounded startup deadline after `kInitialDelayMs`.
  - Treat command-active dispatcher busy as retryable `NotSafeYet`.
  - Count only real `LoadPlugIn` failures against `kLoadRetries`.
  - Add concise native diagnostics that can be captured even while normal dispatch is blocked.
- Modify: `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs`
  - Add source/contract tests for normal dispatch policy, no command-control load, busy deferral, failure-counter semantics, deadline semantics, and diagnostics.
- Optional modify only if exact existing names need adjustment:
  - `docs/superpowers/plans/2026-06-01-companion-load-recent-open-hotfix.md`
  - Add validation closeout after live testing.

---

## Task 1: Pin Companion Activation Source Contract

**Files:**

- Modify: `src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs`
- Read: `src/RookNative/RookNativePlugin.cpp`

- [ ] **Step 1: Add source tests for the companion activation contract**

Append these tests before `ExtractFunction` in `MainThreadDispatcherSourceTests.cs`:

```csharp
[Fact]
public void CompanionLoad_UsesNormalDispatchAndNeverCommandControl()
{
    var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
    var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");
    var attemptLoad = ExtractFunction(source, "AttemptCompanionLoadOnMainThread");

    Assert.Contains("CMainThreadDispatcher::Instance().Dispatch([", attemptLoad);
    Assert.DoesNotContain("DispatchPolicy::CommandControl", attemptLoad);
    Assert.DoesNotContain("CommandControl", attemptLoad);
    Assert.DoesNotContain("DispatchPolicy::CommandControl", companionLoad);
    Assert.DoesNotContain("CommandControl", companionLoad);
}

[Fact]
public void CompanionLoad_ClassifiesCommandActiveBusyAsDeferral()
{
    var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
    var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

    Assert.Contains("enum class CompanionLoadAttemptResult", source);
    Assert.Contains("NotSafeYet", source);
    Assert.Contains("ClassifyCompanionLoadException", source);
    Assert.Contains("RookNative dispatcher is busy: Rhino command is active", source);
    Assert.Contains("case CompanionLoadAttemptResult::NotSafeYet:", companionLoad);
    Assert.Contains("WriteCompanionLoadDiagnostic", companionLoad);
    Assert.Contains("continue;", companionLoad);
}

[Fact]
public void CompanionLoad_LoadFailureBudgetCountsOnlyActualLoadPlugInAttempts()
{
    var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
    var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

    Assert.Contains("int loadFailures = 0;", companionLoad);
    Assert.Contains("++loadFailures;", companionLoad);
    Assert.True(
        companionLoad.IndexOf("case CompanionLoadAttemptResult::LoadFailed:", StringComparison.Ordinal)
        < companionLoad.IndexOf("++loadFailures;", StringComparison.Ordinal),
        "The failure counter must only increment in the LoadFailed branch.");
    Assert.DoesNotContain("for (int attempt = 0; attempt < kLoadRetries; ++attempt)", companionLoad);
}

[Fact]
public void CompanionLoad_HasStartupDeadlineAfterInitialDelay()
{
    var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
    var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

    Assert.Contains("kCompanionLoadStartupWindowMs", source);
    Assert.Contains("startupDeadline", companionLoad);
    Assert.True(
        companionLoad.IndexOf("std::this_thread::sleep_for(std::chrono::milliseconds(kInitialDelayMs));", StringComparison.Ordinal)
        < companionLoad.IndexOf("startupDeadline", StringComparison.Ordinal),
        "The startup deadline must begin after the initial delay.");
}

[Fact]
public void CompanionLoad_ChecksAlreadyReadyBeforeAndInsideDispatch()
{
    var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
    var attemptLoad = ExtractFunction(source, "AttemptCompanionLoadOnMainThread");

    Assert.Contains("if (Rook::Handlers::HasGrasshopperBridgeRegistration())", attemptLoad);
    Assert.Contains("CompanionLoadAttemptResult::AlreadyReady", attemptLoad);
    Assert.True(
        attemptLoad.IndexOf("if (Rook::Handlers::HasGrasshopperBridgeRegistration())", StringComparison.Ordinal)
        < attemptLoad.IndexOf("auto scheduled = CMainThreadDispatcher::Instance().Dispatch([", StringComparison.Ordinal),
        "AlreadyReady must be checked before dispatch.");
    Assert.True(
        attemptLoad.LastIndexOf("if (Rook::Handlers::HasGrasshopperBridgeRegistration())", StringComparison.Ordinal)
        > attemptLoad.IndexOf("auto scheduled = CMainThreadDispatcher::Instance().Dispatch([", StringComparison.Ordinal),
        "AlreadyReady must also be checked inside the dispatched lambda.");
}

[Fact]
public void CompanionLoad_WritesNonDispatchDiagnosticsForCommandActiveDeferrals()
{
    var source = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
    var companionLoad = ExtractFunction(source, "StartCompanionLoadDeferred");

    Assert.Contains("ResolveCompanionLoadDiagnosticPath", source);
    Assert.Contains("companion-load-", source);
    Assert.Contains("OutputDebugStringW", source);

    var notSafeBranch = ExtractSwitchCase(
        companionLoad,
        "case CompanionLoadAttemptResult::NotSafeYet:",
        "case CompanionLoadAttemptResult::LoadFailed:");
    Assert.Contains("WriteCompanionLoadDiagnostic", notSafeBranch);
    Assert.DoesNotContain("RhinoApp().Print", notSafeBranch);
    Assert.DoesNotContain("CMainThreadDispatcher::Instance().Dispatch", notSafeBranch);
}

private static string ExtractSwitchCase(string source, string caseStart, string nextCaseStart)
{
    var start = source.IndexOf(caseStart, StringComparison.Ordinal);
    if (start < 0)
        throw new InvalidOperationException("Switch case not found: " + caseStart);

    var end = source.IndexOf(nextCaseStart, start + caseStart.Length, StringComparison.Ordinal);
    if (end < 0)
        throw new InvalidOperationException("Next switch case not found: " + nextCaseStart);

    return source.Substring(start, end - start);
}
```

- [ ] **Step 2: Run the focused source tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: FAIL. The new companion-load tests should fail because the result enum, deferral classification, startup deadline, and revised failure-budget loop do not exist yet.

- [ ] **Step 3: Commit failing tests**

```powershell
git add src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
git commit -m "test: pin companion load recent-open contract"
```

Expected: commit succeeds.

---

## Task 2: Add Companion Load Result Classification

**Files:**

- Modify: `src/RookNative/RookNativePlugin.cpp`

- [ ] **Step 1: Add required standard-library includes**

In `RookNativePlugin.cpp`, add these includes after the existing `<chrono>` include:

```cpp
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
```

- [ ] **Step 2: Add constants and result enum**

In `RookNativePlugin.cpp`, replace the retry-budget comment/constants block around `kInitialDelayMs` with:

```cpp
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
```

- [ ] **Step 3: Add local exception classifier**

Add this helper immediately after `WaitForFutureOrStop`:

```cpp
static bool ContainsText(const std::string& value, const char* needle)
{
    return value.find(needle) != std::string::npos;
}

static CompanionLoadAttemptResult ClassifyCompanionLoadException(const std::exception& ex)
{
    const std::string message = ex.what() ? ex.what() : "";

    // Coupled to CMainThreadDispatcher's deterministic busy exception. Keep
    // this match local so command-active cancellation remains a deferral for
    // companion activation, not a terminal startup failure.
    if (ContainsText(message, "RookNative dispatcher is busy: Rhino command is active"))
        return CompanionLoadAttemptResult::NotSafeYet;

    if (ContainsText(message, "dispatcher is not running"))
        return CompanionLoadAttemptResult::DispatcherStopping;

    return g_stopCompanionLoad.load()
        ? CompanionLoadAttemptResult::DispatcherStopping
        : CompanionLoadAttemptResult::NotSafeYet;
}
```

- [ ] **Step 4: Add a dispatch attempt helper**

Add these helpers after `ClassifyCompanionLoadException`:

```cpp
static std::filesystem::path ResolveCompanionLoadDiagnosticPath()
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
    return root / (L"companion-load-" + std::to_wstring(::GetCurrentProcessId()) + L".log");
}

static void WriteCompanionLoadDiagnostic(const std::wstring& message)
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

    const std::wstring debugLine = L"RookNative: " + message + L"\n";
    ::OutputDebugStringW(debugLine.c_str());

    try
    {
        std::wofstream log(ResolveCompanionLoadDiagnosticPath(), std::ios::app);
        if (log)
            log << line.str() << L" RookNative: " << message << std::endl;
    }
    catch (...)
    {
    }
}
```

Add this helper after `WriteCompanionLoadDiagnostic`:

```cpp
static CompanionLoadAttemptResult AttemptCompanionLoadOnMainThread()
{
    if (g_stopCompanionLoad.load())
        return CompanionLoadAttemptResult::DispatcherStopping;

    if (Rook::Handlers::HasGrasshopperBridgeRegistration())
        return CompanionLoadAttemptResult::AlreadyReady;

    try
    {
        CompanionLoadAttemptResult result = CompanionLoadAttemptResult::LoadFailed;
        auto scheduled = CMainThreadDispatcher::Instance().Dispatch([&result]()
        {
            if (Rook::Handlers::HasGrasshopperBridgeRegistration())
            {
                result = CompanionLoadAttemptResult::AlreadyReady;
                return;
            }

            CRhinoPlugIn::SaveLoadProtectionToRegistry(g_RookManagedPlugInId, 1);
            result = CRhinoPlugIn::LoadPlugIn(g_RookManagedPlugInId, true, true) >= 0
                ? CompanionLoadAttemptResult::Loaded
                : CompanionLoadAttemptResult::LoadFailed;
        });

        if (!WaitForFutureOrStop(scheduled))
            return CompanionLoadAttemptResult::DispatcherStopping;

        scheduled.get();
        return result;
    }
    catch (const std::exception& ex)
    {
        return ClassifyCompanionLoadException(ex);
    }
    catch (...)
    {
        return g_stopCompanionLoad.load()
            ? CompanionLoadAttemptResult::DispatcherStopping
            : CompanionLoadAttemptResult::NotSafeYet;
    }
}
```

- [ ] **Step 5: Run focused source tests and verify partial failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: still FAIL, because `StartCompanionLoadDeferred` has not yet been rewritten to use the new result enum loop.

- [ ] **Step 6: Commit classification helpers**

```powershell
git add src/RookNative/RookNativePlugin.cpp
git commit -m "fix: classify companion load dispatch outcomes"
```

Expected: commit succeeds.

---

## Task 3: Rewrite Companion Load Loop To Defer During Recent-File `_Open`

**Files:**

- Modify: `src/RookNative/RookNativePlugin.cpp`

- [ ] **Step 1: Replace the Phase 1 load loop**

Inside `StartCompanionLoadDeferred`, replace the block from:

```cpp
// ── Phase 1: Load the managed plugin ──────────────────────────
bool pluginLoaded = false;

for (int attempt = 0; attempt < kLoadRetries; ++attempt)
{
}
```

through the existing `if (!pluginLoaded)` failure block with:

```cpp
// ── Phase 1: Load the managed plugin ──────────────────────────
bool pluginLoaded = false;
int loadFailures = 0;
const auto startupDeadline = std::chrono::steady_clock::now()
    + std::chrono::milliseconds(kCompanionLoadStartupWindowMs);

while (!g_stopCompanionLoad.load()
    && std::chrono::steady_clock::now() < startupDeadline
    && loadFailures < kLoadRetries)
{
    const auto result = AttemptCompanionLoadOnMainThread();

    switch (result)
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
        WriteCompanionLoadDiagnostic(L"managed companion load deferred; Rhino command is active");
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
```

- [ ] **Step 2: Confirm normal dispatch policy remains implicit**

Run:

```powershell
rg -n "DispatchPolicy::CommandControl|AttemptCompanionLoadOnMainThread|kCompanionLoadStartupWindowMs|NotSafeYet" src/RookNative/RookNativePlugin.cpp
```

Expected:

- `DispatchPolicy::CommandControl` does not appear in `RookNativePlugin.cpp`.
- `AttemptCompanionLoadOnMainThread`, `kCompanionLoadStartupWindowMs`, and `NotSafeYet` appear.

- [ ] **Step 3: Run focused source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: PASS.

- [ ] **Step 4: Commit loop rewrite**

```powershell
git add src/RookNative/RookNativePlugin.cpp src/Rook.Tests/Threading/MainThreadDispatcherSourceTests.cs
git commit -m "fix: retry companion load after command-active startup"
```

Expected: commit succeeds.

---

## Task 4: Build And Automated Regression Checks

**Files:**

- Read/build only.

- [ ] **Step 1: Run command-active dispatcher source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests
```

Expected: PASS.

- [ ] **Step 2: Run capability/discovery source checks**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~CompanionRuntimeStatusTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests|FullyQualifiedName~BimHandlerTests"
```

Expected: PASS.

- [ ] **Step 3: Run native MSVC 14.44 Debug x64 build**

Run:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: build succeeds with 0 errors.

- [ ] **Step 4: Run whitespace check**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 5: Commit validation notes only if docs changed**

If no docs changed during validation, do not commit. If validation notes are added later, commit them separately.

---

## Task 5: Live Recent-File `_Open` Validation And Evidence Capture

**Files:**

- Optional modify: `docs/superpowers/plans/2026-06-01-companion-load-recent-open-hotfix.md`

- [ ] **Step 1: Deploy the hotfix locally**

Close Rhino first. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -NativeOnly
```

If MCP processes are still running and only native changed, `-NativeOnly` is sufficient for this hotfix.

Expected: native plugin rebuilds and deploys to `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative`.

- [ ] **Step 2: Capture before/after evidence in the PR notes**

Record the following in the PR body or in this plan's validation closeout:

Before:

```text
RookNative startup time:
recent-file _Open active window:
companion OnLoad absent until ShowRookChat or delayed after command:
native companion-load abandoned/failed message if present:
```

After:

```text
RookNative startup time:
recent-file _Open active window:
NotSafeYet / command-active companion-load deferrals:
eventual LoadPlugIn attempt after safe idle:
companion OnLoad time:
startupComplete true:
panelsRegistered true:
GH bridge registered:
ShowRookChat opens cleanly after startup:
```

The required proof is:

```text
NotSafeYet deferrals happen during recent-file _Open,
but the native activation thread remains alive and succeeds later.
```

- [ ] **Step 3: Primary live repro validation: recent-file `_Open`**

Manual sequence:

```text
1. Close Rhino.
2. Launch Rhino in the same way that triggers recent-file _Open.
3. Open the recent file from the startup/recent-files UI.
4. Do not type ShowRookChat or any Rook command.
5. Wait for file open and safe idle.
6. Watch command prompt for safe-idle native companion-load diagnostics.
7. Inspect `%LOCALAPPDATA%\Rook\discovery\companion-load-<pid>.log` for command-active deferral diagnostics.
```

Expected:

- During `_Open`, the companion-load diagnostic log shows at least one deferral such as:
  `RookNative: managed companion load deferred; Rhino command is active.`
- After safe idle, command prompt shows:
  `RookNative: managed companion LoadPlugIn succeeded.`
  or `RookNative: managed companion loaded and GH bridge ready.`
- No `managed companion LoadPlugIn failed after 3 attempts` message.

- [ ] **Step 4: Verify companion status and `/capabilities`**

Run this from PowerShell after Rhino is idle:

```powershell
$discovery = Get-ChildItem "$env:LOCALAPPDATA\Rook\discovery\instance-*-native.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$record = Get-Content $discovery.FullName | ConvertFrom-Json
$pid = $record.processId
$companion = Get-Content "$env:LOCALAPPDATA\Rook\discovery\companion-$pid.json" | ConvertFrom-Json
$capabilities = Invoke-RestMethod "http://127.0.0.1:$($record.port)/capabilities"
$chat = $capabilities.domains | Where-Object { $_.domainId -eq "chat.ui" }
[pscustomobject]@{
    pid = $pid
    startupComplete = $companion.startupComplete
    panelsRegistered = $companion.panelsRegistered
    bridgeRegistered = $companion.bridgeRegistered
    chatState = $chat.state
    chatReady = $chat.ready
    chatReason = $chat.reasonCode
    chatCompanionEvidenceCount = @($chat.companionEvidence).Count
} | ConvertTo-Json -Depth 8
```

Expected:

- `startupComplete: true`
- `panelsRegistered: true`
- `bridgeRegistered: true`
- `chatCompanionEvidenceCount` is at least 2
- `chatState` is `unknown`
- `chatReason` is `chat_service_state_not_probed_phase1`

- [ ] **Step 5: Verify `ShowRookChat` after startup**

In Rhino command prompt, run:

```text
ShowRookChat
```

Expected:

- The Rook Chat panel opens.
- The command does not print `Rook Chat panel could not be shown`.
- No new companion `OnLoad` race appears after the command.

- [ ] **Step 6: Secondary regression: direct file open**

Manual sequence:

```text
1. Close Rhino.
2. Open Rhino normally.
3. Open the same file through a direct file-open path that did not reproduce the bug.
4. Do not type ShowRookChat during startup.
5. Wait for safe idle.
6. Repeat the PowerShell companion status and /capabilities check from Step 4.
```

Expected: companion loads, panels register, and `/capabilities` shows companion evidence.

- [ ] **Step 7: Add validation closeout**

If validation succeeds, append a short closeout to this plan:

```markdown
## Hotfix Validation Closeout

Recorded on <date>.

- Automated source tests:
- Native MSVC build:
- Recent-file `_Open` before/after evidence:
- Companion status after recent-file `_Open`:
- `ShowRookChat` after startup:
- Direct-open regression:
```

Then commit:

```powershell
git add docs/superpowers/plans/2026-06-01-companion-load-recent-open-hotfix.md
git commit -m "docs: record companion load hotfix validation"
```

Expected: commit succeeds only if validation notes were added.

---

## Self-Review

## Hotfix Validation Closeout

Recorded on 2026-06-01.

Automated validation:

- `dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~MainThreadDispatcherSourceTests`: passed 14/14.
- `dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~CompanionRuntimeStatusTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests|FullyQualifiedName~BimHandlerTests"`: passed 37/37.
- Native MSVC 14.44 Debug x64 build: passed with 0 warnings and 0 errors.
- `git diff --check origin/main...HEAD`: passed.

Local deploy:

- `scripts/deploy-local-testing.ps1 -NativeOnly`: passed.
- Installed native path: `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\RookNative.rhp`.
- Native-only deploy preserved companion registration.

Recent-file `_Open` live validation:

- Rhino PID: 33280.
- Native discovery file: `%LOCALAPPDATA%\Rook\discovery\instance-33280-native.json`.
- Native discovery last write: `2026-06-01T12:00:13.6195594-04:00`.
- Recent-file `_Open` path was used by the user; no Rook command was typed before evidence capture.
- Companion-load diagnostic log: `%LOCALAPPDATA%\Rook\discovery\companion-load-33280.log`.
- Deferral during `_Open`: `2026-06-01T16:00:07.644Z pid=33280 RookNative: managed companion load deferred; Rhino command is active`.
- Later load success: `2026-06-01T16:00:09.727Z pid=33280 RookNative: managed companion LoadPlugIn succeeded`.
- Companion `OnLoadUtc`: `2026-06-01T12:00:09.6583178-04:00`.
- `startupComplete`: true at `2026-06-01T12:00:13.6432688-04:00`.
- `panelsRegistered`: true.
- `bridgeRegistered`: true.
- `/ping`: `pong`.
- `/capabilities`: schemaVersion 1, 13 domains.
- `gh.bridge`: `ready: true`, `state: ready`.
- `chat.ui`: `ready: false`, `state: unknown`, `reasonCode: chat_service_state_not_probed_phase1`, companion evidence count 2.
- MCP resolver: `source: live`, `stale: false`, `authoritative: true`, `domainCount: 13`, `chat.ui` companion evidence count 2.
- `ShowRookChat`: opened cleanly after startup per user confirmation; the old "panel could not be shown" message did not recur.

Required proof:

```text
NotSafeYet deferrals happened during recent-file _Open,
the native activation thread stayed alive,
LoadPlugIn succeeded later,
and managed companion readiness became visible without command-triggered loading.
```

Secondary direct-open regression:

- Rhino PID: 51616.
- Rhino process start time: `2026-06-01T12:05:34.4623689-04:00`.
- Native discovery file: `%LOCALAPPDATA%\Rook\discovery\instance-51616-native.json`.
- Native discovery last write: `2026-06-01T12:05:57.3114775-04:00`.
- Companion-load diagnostic log: `%LOCALAPPDATA%\Rook\discovery\companion-load-51616.log`.
- Direct-open load success: `2026-06-01T16:05:53.321Z pid=51616 RookNative: managed companion LoadPlugIn succeeded`.
- No command-active deferral was needed on the direct-open path.
- Companion `OnLoadUtc`: `2026-06-01T12:05:51.2825411-04:00`.
- `startupComplete`: true at `2026-06-01T12:05:57.3269346-04:00`.
- `panelsRegistered`: true.
- `bridgeRegistered`: true.
- `/capabilities`: schemaVersion 1, 13 domains.
- `gh.bridge`: `ready: true`, `state: ready`.
- `chat.ui`: `ready: false`, `state: unknown`, `reasonCode: chat_service_state_not_probed_phase1`, companion evidence count 2.
- MCP resolver: `source: live`, `stale: false`, `authoritative: true`, `domainCount: 13`, `gh.bridge ready: true`, `chat.ui` companion evidence count 2.

Spec coverage:

- Recent-file `_Open` repro boundary is captured.
- Companion load remains normal dispatch; `CommandControl` is forbidden by source guard.
- Dispatcher busy/command-active cancellation maps to `NotSafeYet`.
- Real load failure budget increments only after `LoadPlugIn` runs.
- Startup deadline begins after initial delay and is bounded/generous.
- AlreadyReady is checked before dispatch and inside dispatched lambda.
- Before/after live evidence is required before merge.

Marker scan:

- No pending-marker or unbounded "add tests" entries.
- Ellipsis appears only in quoted validation template? No production-code steps rely on it.

Type/name consistency:

- `CompanionLoadAttemptResult`, `AttemptCompanionLoadOnMainThread`, `ClassifyCompanionLoadException`, and `kCompanionLoadStartupWindowMs` are used consistently.
