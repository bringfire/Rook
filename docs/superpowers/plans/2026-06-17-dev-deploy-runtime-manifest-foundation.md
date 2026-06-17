# Dev Deploy Runtime Manifest Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local deploy explicitly support a dev/runtime path for the Rhino chat panel without silently falling back to release runtime assumptions.

**Architecture:** `scripts/deploy-local-testing.ps1` gets an explicit runtime contract: release mode remains the default and still fails loudly when the private release runtime is missing; dev mode is opt-in via `-UseRepoVenv` or `-DevPythonRuntime`. The deploy writes and verifies `RookChatService.json` in the root plugin folder and every managed TFM subfolder, with dev manifests pointing at the repo venv and carrying `ROOK_PROJECT_ROOT`.

**Tech Stack:** PowerShell deploy scripts and guard tests, existing Python installer modules, existing C# chat manifest contract.

---

## Scope

This PR implements only the runtime/manifest deploy foundation:

- copy every required top-level `installer/*.py` module into the AppData install payload
- add explicit dev runtime selection to `scripts/deploy-local-testing.ps1`
- write chat manifests into root plus `net8.0`, `net7.0`, and `net48` subdirs
- set and verify `ROOK_PROJECT_ROOT` for dev manifests
- add deploy-smoke guard coverage for those regressions

Defer these to later PRs:

- OCCT DLL deploy closure
- TFM registration fix
- launcher single-spawn and pinned interpreter cleanup
- CI artifact work
- `.vcxproj` fallback cleanup

## Design Notes

Default deploy remains release-shaped. It continues to call `post_install.py`, which should fail if the bundled private Python runtime is missing. The new dev path is opt-in and explicit:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
```

For nonstandard dev layouts, the same path can be supplied directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -DevPythonRuntime "C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe"
```

The two flags are mutually exclusive. Neither flag is inferred from a missing release runtime.

## File Map

- `scripts/deploy-local-testing.ps1`: add explicit runtime-contract helpers, copy all installer Python modules, write root and TFM chat manifests, verify dev/release manifest contracts.
- `scripts/tests/deploy-local-testing-guards.tests.ps1`: add string/structure guard tests for the new deploy contract.
- `.agents/skills/deploy-local-testing/SKILL.md`: document the dev-runtime flag and reporting expectations.
- `docs/superpowers/plans/2026-06-17-dev-deploy-runtime-manifest-foundation.md`: this plan only.

---

### Task 1: Add Guard Tests For PR 1 Deploy Regressions

**Files:**
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] **Step 1: Add failing guard tests**

Append these functions before the final test invocation block:

```powershell
function Test-DeployScriptCopiesAllInstallerPythonModules {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected "Get-ChildItem (Join-Path `$RepoRoot 'installer') -Filter '*.py' -File" -Message 'Local deploy must enumerate every top-level installer Python module.'
    Assert-Contains -Text $content -Expected "Copy-RequiredFile `$_.FullName (Join-Path `$InstallRoot `$_.Name)" -Message 'Local deploy must copy every top-level installer Python module into the AppData app root.'
    Assert-Contains -Text $content -Expected 'python_runtime_install.py' -Message 'Local deploy guard must cover post_install.py sibling module copying.'
    Assert-Contains -Text $content -Expected 'process_rebuild_guard.py' -Message 'Local deploy guard must cover rebuild guard module copying.'
}

function Test-DeployScriptHasExplicitDevRuntimeContract {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$UseRepoVenv' -Message 'Local deploy must expose an explicit repo venv dev-runtime flag.'
    Assert-Contains -Text $content -Expected "[string]`$DevPythonRuntime = ''" -Message 'Local deploy must expose an explicit dev Python runtime path override.'
    Assert-Contains -Text $content -Expected 'function Resolve-DeployRuntimeContract' -Message 'Local deploy must resolve runtime paths through one explicit contract helper.'
    Assert-Contains -Text $content -Expected '-UseRepoVenv cannot be combined with -DevPythonRuntime' -Message 'Dev runtime flags must be mutually exclusive.'
    Assert-Contains -Text $content -Expected 'Dev Python runtime not found' -Message 'Dev runtime mode must fail loudly when the requested interpreter is missing.'
    Assert-Contains -Text $content -Expected 'mcp_server\.venv\Scripts\python.exe' -Message 'Repo venv mode must resolve the repository MCP venv explicitly.'
    Assert-Contains -Text $content -Expected 'ROOK_PROJECT_ROOT' -Message 'Dev runtime mode must carry ROOK_PROJECT_ROOT into generated manifests/config.'
    Assert-Contains -Text $content -Expected 'Skipping release post_install.py because an explicit dev runtime was selected.' -Message 'Dev runtime mode must be explicit about bypassing release post_install.'
}

function Test-DeployScriptWritesChatManifestToRuntimeChildren {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'function Write-ChatServiceManifests' -Message 'Local deploy must write chat manifests through an explicit helper.'
    Assert-Contains -Text $content -Expected '$targets += Join-Path (Join-Path $PluginDir $runtime) ''RookChatService.json''' -Message 'Local deploy must target every managed runtime child manifest.'
    Assert-Contains -Text $content -Expected 'Set-Content -LiteralPath $manifestPath' -Message 'Local deploy must write each manifest path.'
    Assert-Contains -Text $content -Expected 'function Test-ChatServiceManifestAtPath' -Message 'Local deploy must verify each written manifest path.'
    Assert-Contains -Text $content -Expected 'foreach ($runtime in $ManagedCompanionRuntimes)' -Message 'Manifest writing and verification must iterate the known managed runtime folders.'
    Assert-Contains -Text $content -Expected 'Chat service ROOK_PROJECT_ROOT mismatch' -Message 'Dev manifest verification must reject stale or missing ROOK_PROJECT_ROOT.'
}
```

Then add the new functions to the invocation block near the bottom:

```powershell
Test-DeployScriptCopiesAllInstallerPythonModules
Test-DeployScriptHasExplicitDevRuntimeContract
Test-DeployScriptWritesChatManifestToRuntimeChildren
```

- [ ] **Step 2: Run guard tests and confirm they fail**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: FAIL with at least one message from the new tests, such as:

```text
Local deploy must expose an explicit repo venv dev-runtime flag.
```

- [ ] **Step 3: Commit only the failing guard-test additions**

```powershell
git add scripts/tests/deploy-local-testing-guards.tests.ps1
git commit -m "test(dev-infra): guard local deploy runtime manifest contract"
```

---

### Task 2: Add An Explicit Runtime Contract To Local Deploy

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`

- [ ] **Step 1: Add explicit dev-runtime parameters**

In the parameter block, after `[switch]$SkipChirpInstall`, add:

```powershell
    [switch]$UseRepoVenv,
    [string]$DevPythonRuntime = '',
```

- [ ] **Step 2: Extend deploy-mode validation**

In `Assert-DeployMode`, after the `-PayloadOnly` / `-LiveSmoke` checks, add:

```powershell
    if ($UseRepoVenv -and -not [string]::IsNullOrWhiteSpace($DevPythonRuntime)) {
        throw "-UseRepoVenv cannot be combined with -DevPythonRuntime. Pick one explicit dev runtime source."
    }
```

- [ ] **Step 3: Add runtime-contract helpers**

Add these helpers after `Resolve-BootstrapPython`:

```powershell
function Resolve-DevPythonRuntime {
    if ($UseRepoVenv) {
        $candidate = Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe'
    } else {
        $candidate = $DevPythonRuntime
    }

    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $null
    }

    if (-not (Test-Path $candidate)) {
        throw "Dev Python runtime not found: $candidate"
    }

    return (Resolve-Path $candidate).Path
}

function Resolve-DeployRuntimeContract {
    $devPython = Resolve-DevPythonRuntime
    if ($devPython) {
        $devMcpServerDir = Join-Path $RepoRoot 'mcp_server'
        $devSrcDir = Join-Path $devMcpServerDir 'src'
        if (-not (Test-Path $devMcpServerDir)) {
            throw "Dev MCP server directory not found: $devMcpServerDir"
        }
        if (-not (Test-Path $devSrcDir)) {
            throw "Dev MCP source directory not found: $devSrcDir"
        }

        return [pscustomobject]@{
            Mode = 'dev'
            IsDev = $true
            PythonPath = $devPython
            WorkingDirectory = (Resolve-Path $devMcpServerDir).Path
            PythonPathEntries = @((Resolve-Path $devSrcDir).Path)
            InstallRoot = (Resolve-Path $RepoRoot).Path
            DataRoot = $DataRoot
            ProjectRoot = (Resolve-Path $RepoRoot).Path
        }
    }

    return [pscustomobject]@{
        Mode = 'release'
        IsDev = $false
        PythonPath = $VenvPython
        WorkingDirectory = Join-Path $InstallRoot 'mcp_server'
        PythonPathEntries = @((Join-Path $InstallRoot 'mcp_server\src'))
        InstallRoot = $InstallRoot
        DataRoot = $DataRoot
        ProjectRoot = ''
    }
}
```

- [ ] **Step 4: Initialize the contract once**

After `Assert-DeployMode`, add:

```powershell
$RuntimeContract = Resolve-DeployRuntimeContract
```

- [ ] **Step 5: Run PowerShell parse check**

Run:

```powershell
powershell -NoProfile -Command "$null = [scriptblock]::Create((Get-Content -Raw scripts\deploy-local-testing.ps1)); 'parse ok'"
```

Expected:

```text
parse ok
```

- [ ] **Step 6: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: still FAIL, because manifest writing and installer module copying are not implemented yet.

- [ ] **Step 7: Commit runtime contract scaffolding**

```powershell
git add scripts/deploy-local-testing.ps1
git commit -m "feat(dev-infra): add explicit local deploy runtime contract"
```

---

### Task 3: Copy All Installer Python Modules

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`

- [ ] **Step 1: Replace the single `post_install.py` copy**

In `Sync-AppPayload`, replace:

```powershell
    Copy-RequiredFile (Join-Path $RepoRoot 'installer\post_install.py') (Join-Path $InstallRoot 'post_install.py')
```

with:

```powershell
    Get-ChildItem (Join-Path $RepoRoot 'installer') -Filter '*.py' -File | ForEach-Object {
        Copy-RequiredFile $_.FullName (Join-Path $InstallRoot $_.Name)
    }
```

- [ ] **Step 2: Run the deploy guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: still FAIL only on manifest/dev-runtime verification checks, not on installer module copying.

- [ ] **Step 3: Commit installer module copy**

```powershell
git add scripts/deploy-local-testing.ps1
git commit -m "fix(dev-infra): copy installer python modules for local deploy"
```

---

### Task 4: Write Root And TFM Chat Manifests From The Runtime Contract

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `.agents/skills/deploy-local-testing/SKILL.md`

- [ ] **Step 1: Add manifest writer helper**

Add this function after `Register-NativeOnlyPlugins`:

```powershell
function Write-ChatServiceManifests {
    param([Parameter(Mandatory = $true)]$Contract)

    $manifest = [ordered]@{
        pythonPath = $Contract.PythonPath
        workingDirectory = $Contract.WorkingDirectory
        module = 'rook.agent.chat.service_main'
        owner = 'rhino-panel'
        pythonPathEntries = @($Contract.PythonPathEntries)
        environment = [ordered]@{
            PYTHONHOME = ''
            ROOK_INSTALL_ROOT = $Contract.InstallRoot.Replace('\', '/')
            ROOK_DATA_DIR = $Contract.DataRoot.Replace('\', '/')
            ROOK_MODE = $Contract.Mode
            DSPY_CACHEDIR = (Join-Path $Contract.DataRoot 'dspy-cache').Replace('\', '/')
            ROOK_DSPY_RESTRICT_PICKLE = '1'
            CHIRP_HOME = $ChirpInstallRoot.Replace('\', '/')
        }
    }

    if ($Contract.IsDev) {
        $manifest.environment.ROOK_PROJECT_ROOT = $Contract.ProjectRoot.Replace('\', '/')
    } else {
        $manifest.environment.PYTHONPATH = ''
    }

    $json = $manifest | ConvertTo-Json -Depth 6
    $targets = @((Join-Path $PluginDir 'RookChatService.json'))
    foreach ($runtime in $ManagedCompanionRuntimes) {
        $runtimeDir = Join-Path $PluginDir $runtime
        if (Test-Path $runtimeDir) {
            $targets += Join-Path (Join-Path $PluginDir $runtime) 'RookChatService.json'
        }
    }

    foreach ($manifestPath in $targets) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifestPath) | Out-Null
        Set-Content -LiteralPath $manifestPath -Value $json -Encoding UTF8
        Write-Host "Wrote chat service manifest: $manifestPath"
    }
}
```

- [ ] **Step 2: Call the manifest writer after config refresh**

Replace:

```powershell
Write-Step "Refresh MCP, Chirp, and config installs"
Invoke-PostInstallConfig
```

with:

```powershell
if ($RuntimeContract.IsDev) {
    Write-Step "Refresh dev chat runtime manifest"
    Write-Host "Skipping release post_install.py because an explicit dev runtime was selected."
    Write-ChatServiceManifests -Contract $RuntimeContract
} else {
    Write-Step "Refresh MCP, Chirp, and config installs"
    Invoke-PostInstallConfig
    Write-ChatServiceManifests -Contract $RuntimeContract
}
```

- [ ] **Step 3: Update the deploy skill docs**

In `.agents/skills/deploy-local-testing/SKILL.md`, add this useful variant under the existing command examples:

```markdown
# Dev chat/runtime iteration: use the repo MCP venv and write dev manifests.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv

# Dev chat/runtime iteration with an explicit venv path.
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -DevPythonRuntime "C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe"
```

Add this rule under `## Rules`:

```markdown
- `-UseRepoVenv` and `-DevPythonRuntime` are explicit dev-runtime modes; they must never be inferred from a missing release private runtime.
- Release deploy without a dev-runtime flag still runs `post_install.py` and must fail loudly when the bundled release Python runtime is missing.
```

- [ ] **Step 4: Run parse and guard tests**

Run:

```powershell
powershell -NoProfile -Command "$null = [scriptblock]::Create((Get-Content -Raw scripts\deploy-local-testing.ps1)); 'parse ok'"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected:

```text
parse ok
Local testing deploy guard tests passed.
```

- [ ] **Step 5: Commit manifest writing and docs**

```powershell
git add scripts/deploy-local-testing.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1 .agents/skills/deploy-local-testing/SKILL.md
git commit -m "feat(dev-infra): write dev chat manifests for local deploy"
```

---

### Task 5: Verify Runtime And Manifest Contracts In Dev And Release Modes

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] **Step 1: Split manifest verification into a per-path helper**

Replace the existing `Test-ChatServiceManifest` with:

```powershell
function Test-ChatServiceManifestAtPath {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)]$Contract
    )

    if (-not (Test-Path $ManifestPath)) {
        throw "Chat service manifest not found: $ManifestPath"
    }

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    $expectedPython = Normalize-PathForCompare $Contract.PythonPath
    $expectedWorkingDirectory = Normalize-PathForCompare $Contract.WorkingDirectory
    $expectedSourcePath = Normalize-PathForCompare ([string]@($Contract.PythonPathEntries)[0])

    if ((Normalize-PathForCompare ([string]$manifest.pythonPath)) -ne $expectedPython) {
        throw "Chat service pythonPath mismatch in $ManifestPath`: $($manifest.pythonPath)"
    }
    if ((Normalize-PathForCompare ([string]$manifest.workingDirectory)) -ne $expectedWorkingDirectory) {
        throw "Chat service workingDirectory mismatch in $ManifestPath`: $($manifest.workingDirectory)"
    }
    if ($manifest.module -ne 'rook.agent.chat.service_main') {
        throw "Chat service module mismatch in $ManifestPath`: $($manifest.module)"
    }

    $entries = @($manifest.pythonPathEntries)
    if ($entries.Count -lt 1 -or (Normalize-PathForCompare ([string]$entries[0])) -ne $expectedSourcePath) {
        throw "Chat service pythonPathEntries mismatch in $ManifestPath`: $($entries -join ', ')"
    }

    $envBlock = $manifest.environment
    if (-not $envBlock) {
        throw "Chat service environment missing in $ManifestPath"
    }
    if ([string]$envBlock.ROOK_MODE -ne $Contract.Mode) {
        throw "Chat service ROOK_MODE mismatch in $ManifestPath`: $($envBlock.ROOK_MODE)"
    }
    if ((Normalize-PathForCompare ([string]$envBlock.ROOK_INSTALL_ROOT)) -ne (Normalize-PathForCompare $Contract.InstallRoot)) {
        throw "Chat service ROOK_INSTALL_ROOT mismatch in $ManifestPath`: $($envBlock.ROOK_INSTALL_ROOT)"
    }
    if ((Normalize-PathForCompare ([string]$envBlock.ROOK_DATA_DIR)) -ne (Normalize-PathForCompare $Contract.DataRoot)) {
        throw "Chat service ROOK_DATA_DIR mismatch in $ManifestPath`: $($envBlock.ROOK_DATA_DIR)"
    }
    if ($Contract.IsDev) {
        if ((Normalize-PathForCompare ([string]$envBlock.ROOK_PROJECT_ROOT)) -ne (Normalize-PathForCompare $Contract.ProjectRoot)) {
            throw "Chat service ROOK_PROJECT_ROOT mismatch in $ManifestPath`: $($envBlock.ROOK_PROJECT_ROOT)"
        }
    }
}

function Test-ChatServiceManifest {
    param([Parameter(Mandatory = $true)]$Contract)

    Test-ChatServiceManifestAtPath -ManifestPath (Join-Path $PluginDir 'RookChatService.json') -Contract $Contract
    foreach ($runtime in $ManagedCompanionRuntimes) {
        $runtimeDir = Join-Path $PluginDir $runtime
        if (Test-Path $runtimeDir) {
            Test-ChatServiceManifestAtPath -ManifestPath (Join-Path $runtimeDir 'RookChatService.json') -Contract $Contract
        }
    }
}
```

- [ ] **Step 2: Make runtime import verification contract-aware**

Replace the existing `Test-EffectiveRuntime` function with:

```powershell
function Test-EffectiveRuntime {
    param([Parameter(Mandatory = $true)]$Contract)

    if (-not (Test-Path $Contract.PythonPath)) {
        throw "Runtime Python not found: $($Contract.PythonPath)"
    }

    $env:ROOK_INSTALL_ROOT = $Contract.InstallRoot.Replace('\', '/')
    $env:ROOK_DATA_DIR = $Contract.DataRoot.Replace('\', '/')
    $env:ROOK_MODE = $Contract.Mode
    if ($Contract.IsDev) {
        $env:ROOK_PROJECT_ROOT = $Contract.ProjectRoot.Replace('\', '/')
    } else {
        Remove-Item Env:\ROOK_PROJECT_ROOT -ErrorAction SilentlyContinue
    }

    $expectedRookPrefix = Join-Path $Contract.WorkingDirectory 'src\rook'
    $check = @"
import json
from rook.runtime_paths import resolve_runtime_paths
import rook
paths = resolve_runtime_paths()
payload = {
    "rook_file": rook.__file__,
    "mode": paths.mode,
    "install_root": str(paths.install_root),
    "data_root": str(paths.data_root),
    "mcp_server_dir": str(paths.mcp_server_dir),
}
print(json.dumps(payload, sort_keys=True))
if paths.mode != "$($Contract.Mode)":
    raise SystemExit("ROOK_MODE did not resolve to $($Contract.Mode)")
if str(paths.install_root).replace("\\", "/").lower() != r"$($Contract.InstallRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_INSTALL_ROOT mismatch")
if str(paths.data_root).replace("\\", "/").lower() != r"$($Contract.DataRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_DATA_DIR mismatch")
expected_rook_prefix = r"$($expectedRookPrefix.Replace('\','/').ToLowerInvariant())"
actual_rook_file = str(rook.__file__).replace("\\", "/").lower()
if not actual_rook_file.startswith(expected_rook_prefix):
    raise SystemExit(f"rook imported from stale location: {rook.__file__}")
"@

    $checkPath = Join-Path $env:TEMP 'rook_deploy_local_testing_check.py'
    Set-Content -Path $checkPath -Value $check -Encoding UTF8
    try {
        & $Contract.PythonPath $checkPath
        if ($LASTEXITCODE -ne 0) {
            throw "Runtime verification failed."
        }
    } finally {
        Remove-Item -LiteralPath $checkPath -ErrorAction SilentlyContinue
    }
}
```

- [ ] **Step 3: Branch release-only verification at the call site**

Replace:

```powershell
Write-Step "Verify effective installed runtime"
Test-EffectiveRuntime

Write-Step "Verify installed Chirp runtime"
Test-ChirpRuntime

Write-Step "Verify MCP client config and chat manifest"
Test-McpClientConfigs
Test-ChatServiceManifest -Contract $RuntimeContract
```

with:

```powershell
Write-Step "Verify effective runtime"
Test-EffectiveRuntime -Contract $RuntimeContract

if ($RuntimeContract.IsDev) {
    Write-Step "Verify dev chat manifest"
    Write-Host "Skipping release MCP client config and Chirp venv verification because an explicit dev runtime was selected."
    Test-ChatServiceManifest -Contract $RuntimeContract
} else {
    Write-Step "Verify installed Chirp runtime"
    Test-ChirpRuntime

    Write-Step "Verify MCP client config and chat manifest"
    Test-McpClientConfigs
    Test-ChatServiceManifest -Contract $RuntimeContract
}
```

This keeps release deploy strict while allowing the explicit dev runtime path to validate only the contract it owns in PR 1.

- [ ] **Step 4: Pass the runtime contract at any remaining manifest call site**

Replace:

```powershell
Test-ChatServiceManifest
```

with:

```powershell
Test-ChatServiceManifest -Contract $RuntimeContract
```

- [ ] **Step 5: Update guard test expectations**

In `Test-DeployScriptVerifiesChatManifest`, add:

```powershell
    Assert-Contains -Text $content -Expected 'Test-ChatServiceManifestAtPath' -Message 'Local deploy must verify each chat manifest path independently.'
    Assert-Contains -Text $content -Expected 'Chat service environment missing' -Message 'Local deploy must verify chat manifest environment blocks.'
    Assert-Contains -Text $content -Expected 'Chat service ROOK_MODE mismatch' -Message 'Local deploy must verify chat manifest runtime mode.'
    Assert-Contains -Text $content -Expected 'Chat service ROOK_PROJECT_ROOT mismatch' -Message 'Local deploy must verify dev chat manifests point at the repo root.'
    Assert-Contains -Text $content -Expected 'Skipping release MCP client config and Chirp venv verification because an explicit dev runtime was selected.' -Message 'Explicit dev runtime mode must not run release-only MCP/Chirp verification.'
```

- [ ] **Step 6: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected:

```text
Local testing deploy guard tests passed.
```

- [ ] **Step 7: Commit runtime and manifest verification**

```powershell
git add scripts/deploy-local-testing.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1
git commit -m "test(dev-infra): verify dev runtime manifest contract"
```

---

### Task 6: Add A Non-Mutating Dev Manifest Smoke Command

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] **Step 1: Add a smoke-only flag**

In the parameter block, after `[switch]$LiveSmoke`, add:

```powershell
    [switch]$ManifestSmokeOnly
```

In `Assert-DeployMode`, add:

```powershell
    if ($ManifestSmokeOnly -and -not ($UseRepoVenv -or -not [string]::IsNullOrWhiteSpace($DevPythonRuntime))) {
        throw "-ManifestSmokeOnly is only useful with -UseRepoVenv or -DevPythonRuntime."
    }
```

- [ ] **Step 2: Add smoke-only execution before process guards**

After `$RuntimeContract = Resolve-DeployRuntimeContract`, add:

```powershell
if ($ManifestSmokeOnly) {
    Write-Step "Dev manifest smoke"
    Write-Host "Mode:             $($RuntimeContract.Mode)"
    Write-Host "Python:           $($RuntimeContract.PythonPath)"
    Write-Host "WorkingDirectory: $($RuntimeContract.WorkingDirectory)"
    Write-Host "ProjectRoot:      $($RuntimeContract.ProjectRoot)"
    Write-Host "SourcePath:       $(@($RuntimeContract.PythonPathEntries)[0])"
    exit 0
}
```

This mode intentionally does not copy files, register plugins, write AppData, stop processes, or mutate Rhino installs.

- [ ] **Step 3: Add guard coverage for smoke-only mode**

Append this function to `scripts/tests/deploy-local-testing-guards.tests.ps1`:

```powershell
function Test-DeployScriptHasDevManifestSmokeOnlyMode {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$ManifestSmokeOnly' -Message 'Local deploy must expose a non-mutating manifest smoke mode.'
    Assert-Contains -Text $content -Expected '-ManifestSmokeOnly is only useful with -UseRepoVenv or -DevPythonRuntime' -Message 'Manifest smoke must require an explicit dev runtime.'
    Assert-Contains -Text $content -Expected 'Dev manifest smoke' -Message 'Manifest smoke mode must report the resolved contract.'
    Assert-Contains -Text $content -Expected 'exit 0' -Message 'Manifest smoke mode must exit before deploy mutation.'
}
```

Add it to the invocation block:

```powershell
Test-DeployScriptHasDevManifestSmokeOnlyMode
```

- [ ] **Step 4: Run smoke-only command**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv -ManifestSmokeOnly
```

Expected output includes:

```text
== Dev manifest smoke ==
Mode:             dev
Python:           C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe
WorkingDirectory: C:\UDEV\Rook\mcp_server
ProjectRoot:      C:\UDEV\Rook
SourcePath:       C:\UDEV\Rook\mcp_server\src
```

- [ ] **Step 5: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected:

```text
Local testing deploy guard tests passed.
```

- [ ] **Step 6: Commit smoke-only mode**

```powershell
git add scripts/deploy-local-testing.ps1 scripts/tests/deploy-local-testing-guards.tests.ps1
git commit -m "test(dev-infra): add dev manifest smoke mode"
```

---

### Task 7: Final Verification And PR Handoff

**Files:**
- Verify: `scripts/deploy-local-testing.ps1`
- Verify: `scripts/tests/deploy-local-testing-guards.tests.ps1`
- Verify: `.agents/skills/deploy-local-testing/SKILL.md`

- [ ] **Step 1: Confirm only intended files are changed**

Run:

```powershell
git status --short --branch
git diff --name-only main...HEAD
```

Expected branch-diff files for this PR:

```text
.agents/skills/deploy-local-testing/SKILL.md
scripts/deploy-local-testing.ps1
scripts/tests/deploy-local-testing-guards.tests.ps1
```

The local working tree may still show these unstaged runtime files; do not stage or revert them:

```text
knowledge/contextual_mab.pkl
knowledge/substrate_observations.jsonl
```

- [ ] **Step 2: Run static guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected:

```text
Local testing deploy guard tests passed.
```

- [ ] **Step 3: Run release-mode parse/no-dev smoke**

Run:

```powershell
powershell -NoProfile -Command "$null = [scriptblock]::Create((Get-Content -Raw scripts\deploy-local-testing.ps1)); 'parse ok'"
```

Expected:

```text
parse ok
```

- [ ] **Step 4: Run explicit dev manifest smoke**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv -ManifestSmokeOnly
```

Expected: exits 0 and reports `Mode: dev`, repo venv Python, repo `mcp_server`, repo root, and repo `mcp_server\src`.

- [ ] **Step 5: Run focused managed tests that cover chat manifest handling**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManager|FullyQualifiedName~ClaudePanelMcpConfigBuilder"
```

Expected: all selected tests pass.

- [ ] **Step 6: Do not run full deploy unless explicitly approved**

Full deploy mutates AppData plugin installs and requires Rhino/MCP process state. Do not run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
```

unless the user explicitly approves environment mutation.

- [ ] **Step 7: Prepare PR summary**

Use this PR summary:

```markdown
## Summary
- copies all top-level installer Python modules needed by `post_install.py`
- adds explicit dev-runtime selection for local deploy via `-UseRepoVenv` / `-DevPythonRuntime`
- writes `RookChatService.json` into root and managed TFM plugin folders
- carries `ROOK_PROJECT_ROOT` in dev chat manifests and verifies the contract
- adds non-mutating manifest smoke coverage for the dev runtime path

## Validation
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1`
- `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv -ManifestSmokeOnly`
- `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ChatServiceManager|FullyQualifiedName~ClaudePanelMcpConfigBuilder"`

## Notes
- Release deploy remains strict: without a dev-runtime flag, missing private release Python remains a hard failure.
- Full local deploy was not run unless explicitly noted, because it mutates AppData plugin installs and requires Rhino/MCP process coordination.
```
