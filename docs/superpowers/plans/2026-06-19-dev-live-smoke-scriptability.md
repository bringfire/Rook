# Dev Live Smoke Scriptability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the local deploy live smoke to run against the explicit dev runtime contract used by `-UseRepoVenv` and `-DevPythonRuntime`.

**Architecture:** Keep one `Test-LiveSmoke` implementation and pass it the existing `$RuntimeContract`. Add a contract `Environment` object so release and dev subprocess state is derived once, then temporarily apply that environment and working directory around the bounded Python smoke subprocess with strict `try/finally` restoration.

**Tech Stack:** PowerShell deploy script, PowerShell string/structure guard tests, existing Python `_call_tool_dispatch` live smoke body.

---

## Scope

This plan implements the approved spec:

- `docs/superpowers/specs/2026-06-19-dev-live-smoke-scriptability-design.md`

Included:

- Allow `-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke`.
- Allow `-PayloadOnly -AllowRunning -DevPythonRuntime` with an explicit Python executable and `-LiveSmoke`.
- Make live smoke use `$RuntimeContract.PythonPath`, `$RuntimeContract.WorkingDirectory`, `$RuntimeContract.PythonPathEntries`, and `$RuntimeContract.Environment`.
- Preserve release-mode live smoke behavior.
- Restore all changed process environment variables and working directory in `finally`.

Excluded:

- No stale MCP process helper.
- No process termination behavior.
- No separate `Test-DevLiveSmoke`.
- No OCCT fallback-path changes.

## File Map

- `scripts/deploy-local-testing.ps1`: remove the dev live-smoke rejection, add a runtime environment helper, include `Environment` on runtime contracts, and pass the contract into `Test-LiveSmoke`.
- `scripts/tests/deploy-local-testing-guards.tests.ps1`: replace the old release-only live smoke guard with assertions for contract-aware dev/release live smoke.
- `docs/superpowers/plans/2026-06-19-dev-live-smoke-scriptability.md`: this plan.

## Commit Strategy

Do not commit the knowingly failing red guard state. Use the guard failure as the
TDD proof, then implement the deploy-script changes and commit one passing
implementation slice after the guard suite is green.

---

### Task 1: Add Failing Guard Coverage For Contract-Aware Dev Live Smoke

**Files:**
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] **Step 1: Replace the obsolete release-only live smoke assertion**

In `Test-DeployScriptHasExplicitDevRuntimeContract`, replace this assertion:

```powershell
Assert-Contains -Text $content -Expected '-LiveSmoke cannot be combined with -UseRepoVenv or -DevPythonRuntime' -Message 'Live smoke must stay release-runtime-only until made contract-aware.'
```

with this assertion:

```powershell
Assert-NotContains -Text $content -Unexpected '-LiveSmoke cannot be combined with -UseRepoVenv or -DevPythonRuntime' -Message 'Dev runtime live smoke must be allowed when -PayloadOnly -AllowRunning are also selected.'
```

- [ ] **Step 2: Add a dedicated guard function for dev live smoke scriptability**

Insert this function after `Test-DeployScriptHasExplicitDevRuntimeContract`:

```powershell
function Test-DeployScriptAllowsDevLiveSmoke {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'Environment = New-DeployRuntimeEnvironment' -Message 'Runtime contracts must carry the environment used by live smoke subprocesses.'
    Assert-Contains -Text $content -Expected 'function New-DeployRuntimeEnvironment' -Message 'Local deploy must build runtime environment through one explicit helper.'
    Assert-Contains -Text $content -Expected 'PYTHONPATH = ($PythonPathEntries -join [IO.Path]::PathSeparator)' -Message 'Live smoke PYTHONPATH must come from contract PythonPathEntries.'
    Assert-Contains -Text $content -Expected 'if (-not [string]::IsNullOrWhiteSpace($ProjectRoot))' -Message 'ROOK_PROJECT_ROOT must only be set for non-empty project roots.'
    Assert-Contains -Text $content -Expected '$environment.ROOK_PROJECT_ROOT = $ProjectRoot.Replace(''\'', ''/'')' -Message 'Dev live smoke must pass ROOK_PROJECT_ROOT from the contract.'
    Assert-Contains -Text $content -Expected 'Test-LiveSmoke -Contract $RuntimeContract' -Message 'Live smoke must consume the resolved runtime contract.'
    Assert-Contains -Text $content -Expected 'param([Parameter(Mandatory = $true)][pscustomobject]$Contract)' -Message 'Test-LiveSmoke must require an explicit runtime contract.'
    Assert-Contains -Text $content -Expected '$environmentPropertyNames = @($Contract.Environment.PSObject.Properties.Name)' -Message 'Test-LiveSmoke must read environment values from the contract.'
    Assert-Contains -Text $content -Expected '& $Contract.PythonPath $smokePath' -Message 'Live smoke must run with the selected runtime Python.'
    Assert-NotContains -Text $content -Unexpected '& $VenvPython $smokePath' -Message 'Live smoke must not hardcode the release venv Python.'
    Assert-Contains -Text $content -Expected 'Push-Location $Contract.WorkingDirectory' -Message 'Live smoke must run from the selected runtime working directory.'
    Assert-Contains -Text $content -Expected 'Pop-Location' -Message 'Live smoke must restore the prior working directory.'
    Assert-Contains -Text $content -Expected '[Environment]::SetEnvironmentVariable($name, $null, ''Process'')' -Message 'Live smoke must remove variables that were originally absent.'
    Assert-Contains -Text $content -Expected 'Remove-Item -LiteralPath $smokePath -ErrorAction SilentlyContinue' -Message 'Live smoke must remove its temporary smoke script.'
    Assert-Contains -Text $content -Expected '-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke' -Message 'Deploy script guidance must document the dev repo-venv live smoke command.'
    Assert-Contains -Text $content -Expected 'pass -DevPythonRuntime with a Python executable path' -Message 'Deploy script guidance must document the explicit dev Python live smoke command.'
}
```

- [ ] **Step 3: Call the new guard function**

Insert this call after `Test-DeployScriptHasExplicitDevRuntimeContract` in the bottom function list:

```powershell
Test-DeployScriptAllowsDevLiveSmoke
```

The surrounding section should read:

```powershell
Test-DeployScriptHasExplicitDevRuntimeContract
Test-DeployScriptAllowsDevLiveSmoke
Test-DeployScriptCopiesOcctRuntimeClosure
```

- [ ] **Step 4: Run the guard test and verify it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected result: the command fails before implementation. The failure should mention one of the new dev live-smoke guard messages, such as:

```text
Runtime contracts must carry the environment used by live smoke subprocesses.
```

- [ ] **Step 5: Checkpoint the failing guard test without committing**

Run:

```powershell
git diff -- scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected result: only `scripts\tests\deploy-local-testing-guards.tests.ps1` is
changed, and the changes match Steps 1-3 above. Do not commit yet.

---

### Task 2: Add Environment To The Deploy Runtime Contract

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`

- [ ] **Step 1: Add a runtime environment helper**

Insert this function immediately before `Resolve-DeployRuntimeContract`:

```powershell
function New-DeployRuntimeEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$Mode,
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [Parameter(Mandatory = $true)][string]$DataRoot,
        [Parameter(Mandatory = $true)][string[]]$PythonPathEntries,
        [string]$ProjectRoot = ''
    )

    $environment = [ordered]@{
        ROOK_MODE = $Mode
        ROOK_INSTALL_ROOT = $InstallRoot.Replace('\', '/')
        ROOK_DATA_DIR = $DataRoot.Replace('\', '/')
        CHIRP_HOME = $ChirpInstallRoot.Replace('\', '/')
        PYTHONPATH = ($PythonPathEntries -join [IO.Path]::PathSeparator)
    }

    if (-not [string]::IsNullOrWhiteSpace($ProjectRoot)) {
        $environment.ROOK_PROJECT_ROOT = $ProjectRoot.Replace('\', '/')
    }

    return [pscustomobject]$environment
}
```

- [ ] **Step 2: Replace the dev branch of `Resolve-DeployRuntimeContract`**

Replace lines in the dev branch from the current `return [pscustomobject]@{` through the closing `}` of that returned object with:

```powershell
$devWorkingDirectory = (Resolve-Path $devMcpServerDir).Path
$devPythonPathEntries = @((Resolve-Path $devSrcDir).Path)
$devInstallRoot = (Resolve-Path $RepoRoot).Path
$devProjectRoot = (Resolve-Path $RepoRoot).Path

return [pscustomobject]@{
    Mode = 'dev'
    IsDev = $true
    PythonPath = $devPython
    WorkingDirectory = $devWorkingDirectory
    PythonPathEntries = $devPythonPathEntries
    InstallRoot = $devInstallRoot
    DataRoot = $DataRoot
    ProjectRoot = $devProjectRoot
    Environment = New-DeployRuntimeEnvironment `
        -Mode 'dev' `
        -InstallRoot $devInstallRoot `
        -DataRoot $DataRoot `
        -PythonPathEntries $devPythonPathEntries `
        -ProjectRoot $devProjectRoot
}
```

- [ ] **Step 3: Replace the release branch of `Resolve-DeployRuntimeContract`**

Replace the existing release `return [pscustomobject]@{ ... }` with:

```powershell
$releaseWorkingDirectory = Join-Path $InstallRoot 'mcp_server'
$releasePythonPathEntries = @((Join-Path $InstallRoot 'mcp_server\src'))

return [pscustomobject]@{
    Mode = 'release'
    IsDev = $false
    PythonPath = $VenvPython
    WorkingDirectory = $releaseWorkingDirectory
    PythonPathEntries = $releasePythonPathEntries
    InstallRoot = $InstallRoot
    DataRoot = $DataRoot
    ProjectRoot = ''
    Environment = New-DeployRuntimeEnvironment `
        -Mode 'release' `
        -InstallRoot $InstallRoot `
        -DataRoot $DataRoot `
        -PythonPathEntries $releasePythonPathEntries
}
```

This must not pass `-ProjectRoot` in release mode.

- [ ] **Step 4: Run the guard test and verify partial progress**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected result: the command still fails because `Test-LiveSmoke` is not contract-aware yet. The failure should mention one of the live-smoke function assertions, such as:

```text
Test-LiveSmoke must require an explicit runtime contract.
```

- [ ] **Step 5: Checkpoint the runtime contract change without committing**

Run:

```powershell
git diff -- scripts\deploy-local-testing.ps1
```

Expected result: `scripts\deploy-local-testing.ps1` contains
`New-DeployRuntimeEnvironment` and `Environment = New-DeployRuntimeEnvironment`
in both runtime contract branches, but `Test-LiveSmoke` is still not complete.
Do not commit yet.

---

### Task 3: Make `Test-LiveSmoke` Use The Runtime Contract

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`

- [ ] **Step 1: Remove the dev live-smoke rejection**

Delete this block from `Assert-DeployMode`:

```powershell
if ($LiveSmoke -and $hasDevRuntime) {
    throw "-LiveSmoke cannot be combined with -UseRepoVenv or -DevPythonRuntime in this PR. Live smoke remains release-runtime-only."
}
```

Keep the existing `-NativeOnly -LiveSmoke`, `-LiveSmoke` requires `-PayloadOnly -AllowRunning`, and `-UseRepoVenv` with `-DevPythonRuntime` rejections.

- [ ] **Step 2: Replace `Test-LiveSmoke` with a contract-aware version**

Replace the entire `function Test-LiveSmoke { ... }` with:

```powershell
function Test-LiveSmoke {
    param([Parameter(Mandatory = $true)][pscustomobject]$Contract)

    $smoke = @"
import asyncio
import json
from rook.server import _call_tool_dispatch

async def main():
    ping = await _call_tool_dispatch("rhino_ping", {})
    if not ping.get("success"):
        raise SystemExit(f"rhino_ping failed: {ping}")

    status = await _call_tool_dispatch("gh_status", {})
    if not status.get("success"):
        raise SystemExit(f"gh_status failed: {status}")

    chirp = await _call_tool_dispatch("chirp_create", {
        "category": "classifier",
        "name": "Rook Local Deploy Smoke",
        "pins_in": [{"name": "Input", "type": "string", "optional": True}],
        "pins_out": [{"name": "Result", "type": "string"}],
        "signature": "input -> result",
        "deterministic_code": "Result = Input ?? string.Empty;",
        "deterministic_only": True,
        "x": 40,
        "y": 40,
    })
    print(json.dumps({"rhino_ping": ping, "gh_status": status, "chirp_create": chirp}, default=str))
    if not chirp.get("success"):
        raise SystemExit(f"chirp_create failed: {chirp}")
    chirp_data = chirp.get("data") or {}
    if chirp_data.get("compilation_errors") or chirp_data.get("warning"):
        raise SystemExit(f"chirp_create produced component warnings/errors: {chirp_data}")

    component_guid = chirp_data.get("component_guid")
    errors = await _call_tool_dispatch("gh_errors", {})
    if not errors.get("success"):
        raise SystemExit(f"gh_errors failed after chirp_create: {errors}")
    for item in (errors.get("data") or {}).get("errors", []):
        if item.get("guid") == component_guid and item.get("errors"):
            raise SystemExit(f"created Chirp component has Grasshopper errors: {item}")

    undo = await _call_tool_dispatch("gh_undo", {})
    if not undo.get("success"):
        raise SystemExit(f"gh_undo cleanup failed: {undo}")

asyncio.run(main())
"@

    $smokePath = Join-Path $env:TEMP 'rook_deploy_local_testing_live_smoke.py'
    $environmentNames = @(
        'ROOK_MODE',
        'ROOK_INSTALL_ROOT',
        'ROOK_DATA_DIR',
        'CHIRP_HOME',
        'ROOK_PROJECT_ROOT',
        'PYTHONPATH'
    )
    $previousEnvironment = @{}
    foreach ($name in $environmentNames) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }

    $locationPushed = $false
    Set-Content -Path $smokePath -Value $smoke -Encoding UTF8
    try {
        $environmentPropertyNames = @($Contract.Environment.PSObject.Properties.Name)
        foreach ($name in $environmentNames) {
            if ($environmentPropertyNames -contains $name) {
                [Environment]::SetEnvironmentVariable($name, [string]$Contract.Environment.$name, 'Process')
            } else {
                [Environment]::SetEnvironmentVariable($name, $null, 'Process')
            }
        }

        Push-Location $Contract.WorkingDirectory
        $locationPushed = $true
        & $Contract.PythonPath $smokePath
        if ($LASTEXITCODE -ne 0) {
            throw "Live Rhino/Grasshopper/Chirp smoke failed."
        }
    } finally {
        if ($locationPushed) {
            Pop-Location
        }

        foreach ($name in $environmentNames) {
            [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
        }

        Remove-Item -LiteralPath $smokePath -ErrorAction SilentlyContinue
    }
}
```

- [ ] **Step 3: Pass the resolved contract into live smoke**

Replace:

```powershell
Test-LiveSmoke
```

with:

```powershell
Test-LiveSmoke -Contract $RuntimeContract
```

- [ ] **Step 4: Update the no-live-smoke guidance**

Replace:

```powershell
Write-Host "Live Rhino/Grasshopper/Chirp smoke not run. Use -PayloadOnly -AllowRunning -LiveSmoke after restarting Rhino."
```

with:

```powershell
Write-Host "Live Rhino/Grasshopper/Chirp smoke not run. Use -PayloadOnly -AllowRunning -LiveSmoke after restarting Rhino."
Write-Host "Dev runtime smoke: add -UseRepoVenv -LiveSmoke, or pass -DevPythonRuntime with a Python executable path, with -PayloadOnly -AllowRunning."
```

- [ ] **Step 5: Run the guard test and verify it passes**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected result:

```text
Local testing deploy guard tests passed.
```

- [ ] **Step 6: Commit the passing implementation slice**

Run:

```powershell
git add scripts\deploy-local-testing.ps1 scripts\tests\deploy-local-testing-guards.tests.ps1
git commit -m "feat: make dev live smoke scriptable"
```

---

### Task 4: Verify The Follow-Up PR

**Files:**
- Verify: `scripts/deploy-local-testing.ps1`
- Verify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] **Step 1: Run deploy guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected result:

```text
Local testing deploy guard tests passed.
```

- [ ] **Step 2: Run net48 companion guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\issue112-net48-companion-guards.tests.ps1
```

Expected result:

```text
Issue 112 net48 companion guard tests passed.
```

- [ ] **Step 3: Run diff whitespace check**

Run:

```powershell
git diff --check
```

Expected result: exit code `0` and no whitespace errors.

- [ ] **Step 4: Run post-restart dev live smoke when Rhino/GH are ready**

Only run this after a full deploy has completed, Rhino has been restarted, Grasshopper is open or available, and RookNative is loaded.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke
```

Expected result: deploy verification completes and `Run live Rhino/Grasshopper/Chirp smoke` does not throw `Live Rhino/Grasshopper/Chirp smoke failed.`

- [ ] **Step 5: Record live-smoke status in the final PR notes**

If Step 4 is not run, use this exact final-note wording:

```text
Live Rhino/GH/Chirp dev smoke was not run; it requires Rhino restarted with Rook loaded.
```

If Step 4 passes, use this exact final-note wording:

```text
Dev live smoke passed with -PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke.
```
