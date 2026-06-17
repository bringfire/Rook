# Chat Service Launcher Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the embedded Rhino chat panel launcher so it selects the loaded-TFM manifest, treats missing pinned interpreters as terminal invalid manifests, and prevents obvious duplicate chat-service start decisions.

**Architecture:** Keep `ChatServiceManager` as the Rhino-facing lifecycle manager, but extract three tiny internal helpers that are visible to `Rook.Tests`: manifest path resolution, manifest runtime validation, and start action selection. Do not introduce a broad process abstraction, and do not touch Workbench, router, session topology, Work Unit, Merge Contract, or Rhino process lifecycle code.

**Tech Stack:** C#/.NET multi-targeted Rhino companion (`src/Rook`), xUnit net48 tests (`src/Rook.Tests`), existing deploy guard scripts for non-mutating verification.

---

## Scope

This plan implements only the chat-service launcher hardening spec:

- resolve `RookChatService.json` beside the loaded `Rook` assembly / managed TFM folder
- make a manifest with a missing pinned `pythonPath` terminal invalid instead of stale-regenerate
- expose a small start-decision action helper for duplicate-start prevention
- add focused tests under `src/Rook.Tests/UI/Chat/`

Do not implement:

- North Star Workbench launcher changes
- `mcp_server/src/rook/workbench.py`
- `rhino_workbench_launch`, `rhino_workbench_list`, or `rhino_workbench_close`
- session ownership, Work Unit, Merge Contract, router targeting, or Rhino process lifecycle changes
- full local deploy or live Rhino verification without explicit approval

## File Map

- `src/Rook/UI/Chat/ChatServiceManager.cs`: add internal helper types and helpers; delegate existing inline manifest/runtime/start decisions to them.
- `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`: create focused unit tests for helper behavior.
- `docs/superpowers/plans/2026-06-17-chat-service-launcher-hardening.md`: this plan only.

---

### Task 1: Add Focused Failing Tests For Manifest Path And Runtime Validation

**Files:**
- Create: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`

- [ ] **Step 1: Create the failing test file**

Create `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs` with:

```csharp
using System;
using System.IO;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public sealed class ChatServiceManagerTests
    {
        [Theory]
        [InlineData("net48")]
        [InlineData("net7.0")]
        [InlineData("net8.0")]
        public void ResolveManifestPath_UsesLoadedAssemblyDirectory(string runtime)
        {
            var assemblyLocation = Path.Combine(
                "C:\\Users\\dev\\AppData\\Roaming\\McNeel\\Rhinoceros\\8.0\\Plug-ins\\RookNative",
                runtime,
                "Rook.rhp");

            var path = ChatServiceManager.ResolveManifestPath(assemblyLocation);

            Assert.Equal(
                Path.Combine(
                    "C:\\Users\\dev\\AppData\\Roaming\\McNeel\\Rhinoceros\\8.0\\Plug-ins\\RookNative",
                    runtime,
                    "RookChatService.json"),
                path);
        }

        [Fact]
        public void ResolveManifestPath_DoesNotReturnParentRootManifest()
        {
            var assemblyLocation = Path.Combine("C:\\RookPlugin", "net8.0", "Rook.rhp");

            var path = ChatServiceManager.ResolveManifestPath(assemblyLocation);

            Assert.NotEqual(Path.Combine("C:\\RookPlugin", "RookChatService.json"), path);
            Assert.Equal(Path.Combine("C:\\RookPlugin", "net8.0", "RookChatService.json"), path);
        }

        [Fact]
        public void ValidateManifestRuntime_ReturnsValidForExistingRuntimeAndExpectedOwner()
        {
            var python = CreateTempFile("python.exe");
            var workingDirectory = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = python,
                    WorkingDirectory = workingDirectory,
                    Owner = "rhino-panel",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.True(result.IsValid);
                Assert.Equal("", result.Message);
            }
            finally
            {
                TryDeleteFile(python);
                TryDeleteDirectory(workingDirectory);
            }
        }

        [Fact]
        public void ValidateManifestRuntime_MissingPinnedPythonIsTerminalInvalid()
        {
            var missingPython = Path.Combine(Path.GetTempPath(), "missing-rook-python-" + Guid.NewGuid().ToString("N"), "python.exe");
            var workingDirectory = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = missingPython,
                    WorkingDirectory = workingDirectory,
                    Owner = "rhino-panel",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.False(result.IsValid);
                Assert.Equal($"Python runtime not found: {missingPython}", result.Message);
                Assert.True(result.IsTerminalInvalidManifest);
            }
            finally
            {
                TryDeleteDirectory(workingDirectory);
            }
        }

        [Fact]
        public void ValidateManifestRuntime_MissingWorkingDirectoryIsInvalid()
        {
            var python = CreateTempFile("python.exe");
            var missingDirectory = Path.Combine(Path.GetTempPath(), "missing-rook-working-dir-" + Guid.NewGuid().ToString("N"));

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = python,
                    WorkingDirectory = missingDirectory,
                    Owner = "rhino-panel",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.False(result.IsValid);
                Assert.Equal($"Chat service working directory not found: {missingDirectory}", result.Message);
                Assert.False(result.IsTerminalInvalidManifest);
            }
            finally
            {
                TryDeleteFile(python);
            }
        }

        [Fact]
        public void ValidateManifestRuntime_WrongOwnerIsInvalid()
        {
            var python = CreateTempFile("python.exe");
            var workingDirectory = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;

            try
            {
                var manifest = new ChatServiceManifest
                {
                    PythonPath = python,
                    WorkingDirectory = workingDirectory,
                    Owner = "workbench",
                };

                var result = ChatServiceManager.ValidateManifestRuntime(manifest);

                Assert.False(result.IsValid);
                Assert.Equal("Unsupported chat service owner 'workbench'. Expected 'rhino-panel'.", result.Message);
                Assert.False(result.IsTerminalInvalidManifest);
            }
            finally
            {
                TryDeleteFile(python);
                TryDeleteDirectory(workingDirectory);
            }
        }

        private static string CreateTempFile(string fileName)
        {
            var dir = Directory.CreateDirectory(
                Path.Combine(Path.GetTempPath(), "rook-chat-test-" + Guid.NewGuid().ToString("N"))).FullName;
            var path = Path.Combine(dir, fileName);
            File.WriteAllText(path, "");
            return path;
        }

        private static void TryDeleteFile(string path)
        {
            try
            {
                if (File.Exists(path))
                {
                    var dir = Path.GetDirectoryName(path);
                    File.Delete(path);
                    if (!string.IsNullOrEmpty(dir))
                        TryDeleteDirectory(dir);
                }
            }
            catch
            {
            }
        }

        private static void TryDeleteDirectory(string path)
        {
            try
            {
                if (Directory.Exists(path))
                    Directory.Delete(path, recursive: true);
            }
            catch
            {
            }
        }
    }
}
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManagerTests"
```

Expected: FAIL because `ChatServiceManager.ResolveManifestPath`, `ChatServiceManager.ValidateManifestRuntime`, and `ChatServiceRuntimeValidation.IsTerminalInvalidManifest` do not exist yet.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs
git commit -m "test(chat): cover chat service launcher manifest contracts"
```

---

### Task 2: Extract Manifest Path And Runtime Validation Helpers

**Files:**
- Modify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Test: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`

- [ ] **Step 1: Add runtime validation result type**

In `src/Rook/UI/Chat/ChatServiceManager.cs`, after `ChatServiceManifest`, add:

```csharp
    internal readonly struct ChatServiceRuntimeValidation
    {
        public ChatServiceRuntimeValidation(
            bool isValid,
            string message,
            bool isTerminalInvalidManifest)
        {
            IsValid = isValid;
            Message = message ?? "";
            IsTerminalInvalidManifest = isTerminalInvalidManifest;
        }

        public bool IsValid { get; }
        public string Message { get; }
        public bool IsTerminalInvalidManifest { get; }

        public static ChatServiceRuntimeValidation Valid =>
            new ChatServiceRuntimeValidation(true, "", false);
    }
```

- [ ] **Step 2: Add manifest path resolver helper**

Replace `GetManifestPath()` with:

```csharp
        internal static string ResolveManifestPath(string assemblyLocation)
        {
            var pluginDir = Path.GetDirectoryName(assemblyLocation) ?? "";
            return Path.Combine(pluginDir, "RookChatService.json");
        }

        private static string GetManifestPath()
        {
            return ResolveManifestPath(typeof(ChatServiceManager).Assembly.Location);
        }
```

- [ ] **Step 3: Add runtime validation helper**

After `GetManifestPath()`, add:

```csharp
        internal static ChatServiceRuntimeValidation ValidateManifestRuntime(ChatServiceManifest manifest)
        {
            if (!File.Exists(manifest.PythonPath))
            {
                return new ChatServiceRuntimeValidation(
                    false,
                    $"Python runtime not found: {manifest.PythonPath}",
                    true);
            }

            if (!Directory.Exists(manifest.WorkingDirectory))
            {
                return new ChatServiceRuntimeValidation(
                    false,
                    $"Chat service working directory not found: {manifest.WorkingDirectory}",
                    false);
            }

            if (!string.Equals(manifest.Owner, ExpectedOwner, StringComparison.OrdinalIgnoreCase))
            {
                return new ChatServiceRuntimeValidation(
                    false,
                    $"Unsupported chat service owner '{manifest.Owner}'. Expected '{ExpectedOwner}'.",
                    false);
            }

            return ChatServiceRuntimeValidation.Valid;
        }
```

- [ ] **Step 4: Delegate existing inline validation to the helper**

In `EnsureStartedAsync()`, replace:

```csharp
                if (!File.Exists(manifest.PythonPath))
                {
                    return new ChatServiceHealth
                    {
                        ServiceAvailable = false,
                        ServiceMessage = $"Python runtime not found: {manifest.PythonPath}",
                    };
                }

                if (!Directory.Exists(manifest.WorkingDirectory))
                {
                    return new ChatServiceHealth
                    {
                        ServiceAvailable = false,
                        ServiceMessage = $"Chat service working directory not found: {manifest.WorkingDirectory}",
                    };
                }

                if (!string.Equals(manifest.Owner, ExpectedOwner, StringComparison.OrdinalIgnoreCase))
                {
                    return new ChatServiceHealth
                    {
                        ServiceAvailable = false,
                        ServiceMessage = $"Unsupported chat service owner '{manifest.Owner}'. Expected '{ExpectedOwner}'.",
                    };
                }
```

with:

```csharp
                var runtimeValidation = ValidateManifestRuntime(manifest);
                if (!runtimeValidation.IsValid)
                {
                    return new ChatServiceHealth
                    {
                        ServiceAvailable = false,
                        ServiceMessage = runtimeValidation.Message,
                    };
                }
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManagerTests"
```

Expected: manifest path and runtime validation tests pass. Start decision tests have not been added yet.

- [ ] **Step 6: Commit helper extraction**

```powershell
git add src/Rook/UI/Chat/ChatServiceManager.cs src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs
git commit -m "feat(chat): expose chat service manifest runtime guards"
```

---

### Task 3: Make Missing Pinned Python Terminal Invalid Before Regeneration

**Files:**
- Modify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Modify: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`

- [ ] **Step 1: Add a source guard for the terminal-invalid load path**

Append this test to `ChatServiceManagerTests` before the helper methods:

```csharp
        [Fact]
        public void LoadManifest_DoesNotRegenerateWhenPinnedPythonIsMissing()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatServiceManager.cs");
            var loadManifest = ExtractMethod(source, "private ChatServiceManifest? LoadManifest()");

            Assert.Contains("ValidateManifestRuntime(manifest)", loadManifest);
            Assert.Contains("runtimeValidation.IsTerminalInvalidManifest", loadManifest);
            var terminalInvalidIndex = loadManifest.IndexOf(
                "runtimeValidation.IsTerminalInvalidManifest",
                StringComparison.Ordinal);
            var terminalReturnIndex = loadManifest.IndexOf(
                "return manifest;",
                terminalInvalidIndex,
                StringComparison.Ordinal);
            var staleCheckIndex = loadManifest.IndexOf(
                "IsManifestCurrent(manifest",
                StringComparison.Ordinal);
            var autoGenerateIndex = loadManifest.IndexOf(
                "TryAutoGenerateManifest(manifestPath)",
                StringComparison.Ordinal);

            Assert.True(terminalInvalidIndex >= 0);
            Assert.True(terminalReturnIndex > terminalInvalidIndex);
            Assert.True(terminalReturnIndex < staleCheckIndex);
            Assert.True(terminalReturnIndex < autoGenerateIndex);
        }
```

Add these source helper methods near the end of the test class:

```csharp
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

        private static string ExtractMethod(string source, string signatureStartText)
        {
            var signatureStart = source.IndexOf(signatureStartText, StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Method not found: " + signatureStartText);

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Method body not found: " + signatureStartText);

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
```

- [ ] **Step 2: Run focused tests and verify the new guard fails**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~LoadManifest_DoesNotRegenerateWhenPinnedPythonIsMissing"
```

Expected: FAIL because `LoadManifest()` still lets `IsManifestCurrent()` mark missing `pythonPath` as stale and then reaches `TryAutoGenerateManifest(manifestPath)`.

- [ ] **Step 3: Update `LoadManifest()` terminal invalid behavior**

In `LoadManifest()`, replace this block:

```csharp
                    if (manifest != null)
                    {
                        if (IsManifestCurrent(manifest, out var staleReason))
                        {
                            return manifest;
                        }

                        RhinoApp.WriteLine(
                            "Rook: cached chat service manifest is stale "
                            + $"({staleReason}). Regenerating.");
                    }
```

with:

```csharp
                    if (manifest != null)
                    {
                        var runtimeValidation = ValidateManifestRuntime(manifest);
                        if (!runtimeValidation.IsValid && runtimeValidation.IsTerminalInvalidManifest)
                        {
                            RhinoApp.WriteLine(
                                "Rook: chat service manifest is invalid "
                                + $"({runtimeValidation.Message}).");
                            return manifest;
                        }

                        if (IsManifestCurrent(manifest, out var staleReason))
                        {
                            return manifest;
                        }

                        RhinoApp.WriteLine(
                            "Rook: cached chat service manifest is stale "
                            + $"({staleReason}). Regenerating.");
                    }
```

This keeps `LoadManifest()` returning a manifest so `EnsureStartedAsync()` can surface the existing clear health message from `ValidateManifestRuntime()` and prevents auto-generation from masking a bad pinned interpreter.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManagerTests"
```

Expected: all `ChatServiceManagerTests` pass.

- [ ] **Step 5: Commit terminal invalid manifest behavior**

```powershell
git add src/Rook/UI/Chat/ChatServiceManager.cs src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs
git commit -m "fix(chat): treat missing pinned chat python as terminal invalid"
```

---

### Task 4: Add Start Decision Action Helper

**Files:**
- Modify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Modify: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`

- [ ] **Step 1: Add failing start decision tests**

Append these tests to `ChatServiceManagerTests` before helper methods:

```csharp
        [Theory]
        [InlineData(true, false, false, true, ChatServiceStartDecision.ReuseHealthyService)]
        [InlineData(true, false, true, true, ChatServiceStartDecision.ReuseHealthyService)]
        [InlineData(true, false, false, false, ChatServiceStartDecision.RestartBecauseNonceMissing)]
        [InlineData(true, false, true, false, ChatServiceStartDecision.RestartBecauseNonceMissing)]
        public void ShouldStartChatService_HealthyServiceDecision(
            bool existingServiceAvailable,
            bool trackedProcessExists,
            bool trackedProcessHasExited,
            bool sessionNoncePresent,
            ChatServiceStartDecision expected)
        {
            var decision = ChatServiceManager.ShouldStartChatService(
                trackedProcessExists,
                trackedProcessHasExited,
                existingServiceAvailable,
                sessionNoncePresent);

            Assert.Equal(expected, decision);
        }

        [Theory]
        [InlineData(true, false, false, false, ChatServiceStartDecision.WaitForTrackedProcess)]
        [InlineData(true, false, false, true, ChatServiceStartDecision.WaitForTrackedProcess)]
        [InlineData(true, true, false, true, ChatServiceStartDecision.StartNewProcess)]
        [InlineData(false, false, false, true, ChatServiceStartDecision.StartNewProcess)]
        public void ShouldStartChatService_TrackedProcessDecision(
            bool trackedProcessExists,
            bool trackedProcessHasExited,
            bool existingServiceAvailable,
            bool sessionNoncePresent,
            ChatServiceStartDecision expected)
        {
            var decision = ChatServiceManager.ShouldStartChatService(
                trackedProcessExists,
                trackedProcessHasExited,
                existingServiceAvailable,
                sessionNoncePresent);

            Assert.Equal(expected, decision);
        }
```

- [ ] **Step 2: Run start decision tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ShouldStartChatService"
```

Expected: FAIL because `ChatServiceStartDecision` and `ShouldStartChatService()` do not exist yet.

- [ ] **Step 3: Add enum and helper**

In `ChatServiceManager.cs`, after `ChatServiceRuntimeValidation`, add:

```csharp
    internal enum ChatServiceStartDecision
    {
        ReuseHealthyService,
        RestartBecauseNonceMissing,
        WaitForTrackedProcess,
        StartNewProcess,
    }
```

Inside `ChatServiceManager`, after `ValidateManifestRuntime()`, add:

```csharp
        internal static ChatServiceStartDecision ShouldStartChatService(
            bool trackedProcessExists,
            bool trackedProcessHasExited,
            bool existingServiceAvailable,
            bool sessionNoncePresent)
        {
            if (existingServiceAvailable)
            {
                return sessionNoncePresent
                    ? ChatServiceStartDecision.ReuseHealthyService
                    : ChatServiceStartDecision.RestartBecauseNonceMissing;
            }

            if (trackedProcessExists && !trackedProcessHasExited)
            {
                return ChatServiceStartDecision.WaitForTrackedProcess;
            }

            return ChatServiceStartDecision.StartNewProcess;
        }
```

- [ ] **Step 4: Use helper in `EnsureStartedAsync()` for healthy service decisions**

In `EnsureStartedAsync()`, replace:

```csharp
                var existing = await GetHealthInternalAsync(startIfNeeded: false, ct: ct);
                if (existing.ServiceAvailable)
                {
                    if (!string.IsNullOrEmpty(SessionNonce))
                    {
                        // Session nonce is still valid — reuse the running service.
                        return existing;
                    }

                    // Service is running but we lost the nonce (companion reload,
                    // panel recreation, etc.).  The Python process still enforces
                    // the old nonce, so every non-health request would 403.  Stop
                    // it and let the normal start path generate a fresh nonce.
                    RhinoApp.WriteLine("Rook: restarting chat service — session nonce lost after companion reload");
                    StopOwnedProcess();
                    StopDiscoveredOwnedService();
                }
```

with:

```csharp
                var existing = await GetHealthInternalAsync(startIfNeeded: false, ct: ct);
                var startDecision = ShouldStartChatService(
                    trackedProcessExists: _ownedProcess != null,
                    trackedProcessHasExited: _ownedProcess?.HasExited ?? true,
                    existingServiceAvailable: existing.ServiceAvailable,
                    sessionNoncePresent: !string.IsNullOrEmpty(SessionNonce));
                if (startDecision == ChatServiceStartDecision.ReuseHealthyService)
                {
                    // Session nonce is still valid — reuse the running service.
                    return existing;
                }

                if (startDecision == ChatServiceStartDecision.RestartBecauseNonceMissing)
                {
                    // Service is running but we lost the nonce (companion reload,
                    // panel recreation, etc.).  The Python process still enforces
                    // the old nonce, so every non-health request would 403.  Stop
                    // it and let the normal start path generate a fresh nonce.
                    RhinoApp.WriteLine("Rook: restarting chat service — session nonce lost after companion reload");
                    StopOwnedProcess();
                    StopDiscoveredOwnedService();
                }
```

This keeps the existing nonce-loss behavior while routing it through the action helper.

- [ ] **Step 5: Use helper in `StartProcess()`**

Replace the first guard in `StartProcess()`:

```csharp
            if (_ownedProcess != null && !_ownedProcess.HasExited)
            {
                return;
            }
```

with:

```csharp
            var startDecision = ShouldStartChatService(
                trackedProcessExists: _ownedProcess != null,
                trackedProcessHasExited: _ownedProcess?.HasExited ?? true,
                existingServiceAvailable: false,
                sessionNoncePresent: !string.IsNullOrEmpty(SessionNonce));
            if (startDecision == ChatServiceStartDecision.WaitForTrackedProcess)
            {
                return;
            }
```

This keeps the existing behavior while routing the duplicate-process guard through the testable action helper.

- [ ] **Step 6: Add source guard for lifecycle lock and pinned process start**

Append this test to `ChatServiceManagerTests` before helper methods:

```csharp
        [Fact]
        public void EnsureStartedAndStartProcessKeepLifecycleLockAndPinnedInterpreter()
        {
            var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ChatServiceManager.cs");
            var ensureStarted = ExtractMethod(source, "public async Task<ChatServiceHealth> EnsureStartedAsync(");
            var startProcess = ExtractMethod(source, "private void StartProcess(");

            Assert.Contains("await _gate.WaitAsync(ct);", ensureStarted);
            Assert.Contains("ShouldStartChatService(", ensureStarted);
            Assert.Contains("ChatServiceStartDecision.RestartBecauseNonceMissing", ensureStarted);
            Assert.Contains("StartProcess(manifest);", ensureStarted);
            Assert.Contains("FileName = manifest.PythonPath", startProcess);
            Assert.Contains("ShouldStartChatService(", startProcess);
            Assert.DoesNotContain("DiscoverPython()", startProcess);
            Assert.DoesNotContain("DiscoverManagedVenvPython()", startProcess);
        }
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManagerTests"
```

Expected: all `ChatServiceManagerTests` pass.

- [ ] **Step 8: Commit start decision helper**

```powershell
git add src/Rook/UI/Chat/ChatServiceManager.cs src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs
git commit -m "test(chat): cover chat service start decisions"
```

---

### Task 5: Final Verification And PR Handoff

**Files:**
- Verify: `src/Rook/UI/Chat/ChatServiceManager.cs`
- Verify: `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs`
- Verify: `docs/superpowers/specs/2026-06-17-chat-service-launcher-hardening-design.md`

- [ ] **Step 1: Confirm intended branch and local noise**

Run:

```powershell
git status --short --branch
git diff --name-only origin/main...HEAD
```

Expected branch includes the spec commit and implementation files:

```text
docs/superpowers/plans/2026-06-17-chat-service-launcher-hardening.md
docs/superpowers/specs/2026-06-17-chat-service-launcher-hardening-design.md
src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs
src/Rook/UI/Chat/ChatServiceManager.cs
```

Working tree may still show these unstaged local runtime artifacts; do not stage or revert them:

```text
knowledge/contextual_mab.pkl
knowledge/substrate_observations.jsonl
```

- [ ] **Step 2: Run focused managed tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManager|FullyQualifiedName~ChatServiceLauncher|FullyQualifiedName~ClaudePanelMcpConfigBuilder"
```

Expected: all selected tests pass.

- [ ] **Step 3: Run deploy guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected:

```text
Local testing deploy guard tests passed.
```

- [ ] **Step 4: Run deploy script parse check**

Run:

```powershell
powershell -NoProfile -Command '$null = [scriptblock]::Create((Get-Content -Raw scripts\deploy-local-testing.ps1)); ''parse ok'''
```

Expected:

```text
parse ok
```

- [ ] **Step 5: Run explicit dev manifest smoke**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv -ManifestSmokeOnly
```

Expected: exits 0 and reports `Mode: dev`, repo venv Python, repo `mcp_server`, repo root, and repo `mcp_server\src`.

- [ ] **Step 6: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output and exit 0.

- [ ] **Step 7: Do not run full deploy or live Rhino unless explicitly approved**

Do not run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
```

Do not claim live Rhino verification unless it is actually run.

- [ ] **Step 8: Prepare PR summary**

Use this PR summary:

```markdown
## Summary
- adds focused chat-service launcher helper tests
- resolves `RookChatService.json` from the loaded managed assembly directory
- treats a missing pinned manifest `pythonPath` as terminal invalid instead of auto-regenerating
- adds a small start-decision helper for obvious duplicate chat-service start paths

## Validation
- `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManager|FullyQualifiedName~ChatServiceLauncher|FullyQualifiedName~ClaudePanelMcpConfigBuilder"`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv -ManifestSmokeOnly`
- `git diff --check`

## Notes
- This PR does not touch Workbench launcher, router targeting, session ownership, Work Unit, Merge Contract, or Rhino process lifecycle code.
- Full local deploy and live Rhino verification were not run unless explicitly noted, because they mutate AppData/Rhino install state and require process coordination.
```
