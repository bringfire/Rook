# Chat Service Launcher Hardening Design

## Goal

Harden the embedded Rhino chat panel's Python backend launcher so it consumes the runtime manifest from the loaded managed companion location, honors pinned interpreters, and avoids obvious duplicate start paths.

This slice targets `src/Rook/UI/Chat/ChatServiceManager.cs` and focused tests under `src/Rook.Tests/UI/Chat/`. It is intentionally narrow and follows PR #265, which made local deploy write `RookChatService.json` into the plugin root and each managed TFM subfolder.

## Non-Goals

- Do not change the North Star Workbench launcher.
- Do not edit `mcp_server/src/rook/workbench.py`, `rhino_workbench_launch`, `rhino_workbench_list`, or `rhino_workbench_close`.
- Do not change session ownership semantics, Work Unit or Merge Contract topology, router targeting, or Rhino process lifecycle.
- Do not run full local deploy or live Rhino verification without explicit approval.
- Do not introduce a broad process-runner abstraction unless implementation reveals a smaller path cannot meet this spec.

The Workbench launcher starts owned disposable Rhino sessions. The chat launcher starts `python -m rook.agent.chat.service_main` for the embedded panel. These planes remain separate.

## Current Behavior

`ChatServiceManager.GetManifestPath()` currently derives `RookChatService.json` from `typeof(ChatServiceManager).Assembly.Location`, which should be the loaded TFM folder such as `net48`, `net7.0`, or `net8.0`. That behavior matches the PR #265 deploy contract, but it is implicit and not directly covered by focused tests.

`LoadManifest()` reads the manifest, validates staleness, and may auto-generate a manifest when the manifest is missing or stale. Auto-generation may discover a managed private venv, and only reaches PATH or `py` discovery when `ROOK_ALLOW_USER_PYTHON_DISCOVERY` is explicitly enabled.

`StartProcess()` uses `manifest.PythonPath` as `ProcessStartInfo.FileName`, applies manifest environment values temporarily to the parent process because `UseShellExecute=true`, generates a session nonce, and starts `rook.agent.chat.service_main`. Lifecycle entry points are protected by `_gate`, and `StartProcess()` returns early when `_ownedProcess` is already live.

Before implementation, move this spec commit onto a feature branch or push/review it consciously. Do not begin code work directly on `main`.

## Risks To Address

1. **Manifest selection ambiguity.** The launcher must not prefer a stale parent/root manifest over the manifest beside the loaded assembly. The root manifest can remain a deploy compatibility artifact, but it is not launcher truth.

2. **Pinned interpreter fallback.** If a manifest file exists but declares a missing `pythonPath`, startup should fail with a clear health message. It should not silently fall back to PATH, `py`, or another interpreter. Auto-generation/discovery is only for missing manifests or stale manifests whose pinned runtime still exists. A missing pinned interpreter is a terminal invalid manifest, not a regeneration trigger.

3. **Duplicate chat-service starts.** The current semaphore and tracked-process guard are the right shape, but the behavior is buried in Rhino-bound code. This slice should prevent obvious duplicate start paths and add test coverage around the decision matrix. It does not need to prove every possible race without a broader injectable process runner.

## Proposed Design

### 1. Manifest Path Resolver

Extract a tiny internal helper:

```csharp
internal static string ResolveManifestPath(string assemblyLocation)
```

The helper returns `Path.Combine(Path.GetDirectoryName(assemblyLocation) ?? "", "RookChatService.json")`.

`GetManifestPath()` should delegate to this helper using `typeof(ChatServiceManager).Assembly.Location`.

Contract:

- `net48\Rook.rhp` resolves to `net48\RookChatService.json`.
- `net7.0\Rook.rhp` resolves to `net7.0\RookChatService.json`.
- `net8.0\Rook.rhp` resolves to `net8.0\RookChatService.json`.
- There is no parent/root fallback in the launcher.

### 2. Manifest Runtime Validation

Extract a small validation helper:

```csharp
internal static ChatServiceRuntimeValidation ValidateManifestRuntime(ChatServiceManifest manifest)
```

The result should carry:

- `bool IsValid`
- `string Message`

Initial validation should cover only the runtime fields already checked inline, plus the explicit terminal-invalid distinction for a missing pinned interpreter:

- `pythonPath` must point to an existing file.
- `workingDirectory` must point to an existing directory.
- `owner` must match `rhino-panel`.

`EnsureStartedAsync()` should keep returning the same style of `ChatServiceHealth` messages, but delegate the checks to this helper.

Important distinction:

- If a manifest exists and `pythonPath` is missing, return `Python runtime not found: <path>`.
- Do not auto-discover another Python for that manifest.
- This intentionally changes the current stale-manifest path: `IsManifestCurrent()` currently treats missing `pythonPath` as stale and allows `LoadManifest()` to regenerate. This slice should split validation so a missing pinned `pythonPath` from an existing manifest is terminal invalid.
- Missing-manifest auto-generation remains available.
- Stale-manifest auto-generation remains available only for stale cases that do not invalidate the pinned interpreter contract.

### 3. Start Decision Guard

Extract a tiny pure helper for the obvious start decision:

```csharp
internal static ChatServiceStartDecision ShouldStartChatService(
    bool trackedProcessExists,
    bool trackedProcessHasExited,
    bool existingServiceAvailable,
    bool sessionNoncePresent)
```

The helper should return an enum-like action, not a plain boolean:

```csharp
internal enum ChatServiceStartDecision
{
    ReuseHealthyService,
    RestartBecauseNonceMissing,
    WaitForTrackedProcess,
    StartNewProcess,
}
```

The helper should model only decisions already present in `EnsureStartedAsync()` and `StartProcess()`:

- Healthy existing service with a session nonce: `ReuseHealthyService`.
- Existing service without a session nonce: `RestartBecauseNonceMissing`.
- Tracked chat-service process that has not exited: `WaitForTrackedProcess`.
- No healthy existing service and no live tracked process: `StartNewProcess`.

Naming should consistently use "tracked chat-service process" and avoid Workbench-owned Rhino terminology.

This helper is not a replacement for `_gate`. `_gate` remains the lifecycle serialization mechanism. The helper makes the start/no-start matrix testable and readable.

## Testing Strategy

Add focused tests under `src/Rook.Tests/UI/Chat/`.

### Unit Tests

Manifest path tests:

- `ResolveManifestPath_UsesLoadedAssemblyDirectory_Net48`
- `ResolveManifestPath_UsesLoadedAssemblyDirectory_Net7`
- `ResolveManifestPath_UsesLoadedAssemblyDirectory_Net8`
- `ResolveManifestPath_DoesNotReturnParentRootManifest`

Runtime validation tests:

- existing `pythonPath`, existing `workingDirectory`, expected owner: valid
- missing `pythonPath`: invalid with `Python runtime not found`
- missing `workingDirectory`: invalid with `Chat service working directory not found`
- wrong owner: invalid with `Unsupported chat service owner`

Start decision tests:

- healthy service plus nonce: `ReuseHealthyService`
- healthy service without nonce: `RestartBecauseNonceMissing`
- live tracked chat-service process: `WaitForTrackedProcess`
- exited tracked chat-service process: `StartNewProcess`
- no service and no tracked process: `StartNewProcess`

### Source Guard Tests

If needed, keep source-shape guards limited to Rhino-bound behavior that is not practical to unit test in this slice:

- `EnsureStartedAsync()` still waits on `_gate`.
- `StartProcess()` still uses `manifest.PythonPath` as `ProcessStartInfo.FileName`.
- There is no parent-directory manifest fallback near `GetManifestPath()`.

Avoid asserting broad source structure unless the behavior cannot be tested through internal helpers.

## Verification

Non-mutating verification is preferred:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManager|FullyQualifiedName~ChatServiceLauncher|FullyQualifiedName~ClaudePanelMcpConfigBuilder"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
powershell -NoProfile -Command '$null = [scriptblock]::Create((Get-Content -Raw scripts\deploy-local-testing.ps1)); ''parse ok'''
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv -ManifestSmokeOnly
git diff --check
```

Do not claim live Rhino verification unless it is actually run. Full local deploy mutates AppData and Rhino install state and requires explicit approval.

## Acceptance Criteria

- The chat launcher resolves `RookChatService.json` beside the loaded `Rook` assembly and has tests proving TFM-local paths are selected.
- A manifest with a missing pinned `pythonPath` is terminal invalid, fails clearly, and does not silently discover another interpreter or auto-regenerate.
- Obvious duplicate start paths are covered by a pure action-decision helper and focused tests.
- Workbench launcher, session topology, Work Unit, Merge Contract, and Rhino process lifecycle code are untouched.
- `knowledge/contextual_mab.pkl` and `knowledge/substrate_observations.jsonl` remain local runtime artifacts and are not staged.
