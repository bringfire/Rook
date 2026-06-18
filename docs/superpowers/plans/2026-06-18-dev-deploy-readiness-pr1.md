# Dev Deploy Readiness PR 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make current `main` diagnosable and deployable on a prepared Windows dev machine by adding a read-only doctor, copying OCCT runtime DLLs during local deploy, registering the net8 companion, and documenting the dev convention.

**Architecture:** Keep PR 1 operational and local-deploy-only. The doctor reads the machine and repo state without mutation; deploy uses an explicit measured OCCT DLL list and a simple `OCCT_ROOT`-then-fallback resolver; registration prefers `net8.0` while preserving legacy fallback and native-only behavior.

**Tech Stack:** PowerShell 5.1-compatible scripts, lightweight PowerShell source guard tests, Rhino 8 plugin AppData layout, OCCT runtime closure from `docs/rook_docs/occt-build.md`.

---

## File Structure

- Create `scripts/rook-dev-doctor.ps1`: read-only dev-machine preflight report with default and `-Strict` exit behavior.
- Modify `scripts/deploy-local-testing.ps1`: add explicit OCCT runtime DLL list and root resolver; copy the measured OCCT runtime closure next to `RookNative.rhp`; change full deploy registration to `net8.0`.
- Modify `scripts/register-rooknative-suite.ps1`: update no-argument companion fallback order to `net8.0`, `net7.0`, root.
- Modify `scripts/register-companion.ps1`: accept `net8.0` or `net7.0` managed companion paths and runtime metadata while still rejecting `net48`.
- Modify `scripts/tests/deploy-local-testing-guards.tests.ps1`: add static guards for doctor, OCCT copy, net8 registration, and fallback order.
- Modify `AGENT_SETUP.md`: add a short developer-machine convention section and guard it in the local deploy guard script.

Do not modify `.vcxproj`, `.vcxproj.filters`, installer files, release pipeline scripts, or release guard tests in this PR.

---

### Task 1: Add Guard Tests For PR 1 Contract

**Files:**
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`
- Guarded later by: `scripts/rook-dev-doctor.ps1`
- Guarded later by: `scripts/deploy-local-testing.ps1`
- Guarded later by: `scripts/register-rooknative-suite.ps1`

- [ ] **Step 1: Add the doctor script path variable**

In `scripts/tests/deploy-local-testing-guards.tests.ps1`, near the existing path variables:

```powershell
$DoctorScript = Join-Path $RepoRoot 'scripts\rook-dev-doctor.ps1'
```

Expected surrounding block:

```powershell
$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$DeployScript = Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1'
$RegisterSuiteScript = Join-Path $RepoRoot 'scripts\register-rooknative-suite.ps1'
$DeploySkill = Join-Path $RepoRoot '.agents\skills\deploy-local-testing\SKILL.md'
$DoctorScript = Join-Path $RepoRoot 'scripts\rook-dev-doctor.ps1'
$AgentSetup = Join-Path $RepoRoot 'AGENT_SETUP.md'
```

- [ ] **Step 2: Add an order assertion helper**

Add this helper after `Assert-NotContains`:

```powershell
function Assert-Before {
    param(
        [string]$Text,
        [string]$First,
        [string]$Second,
        [string]$Message
    )

    $firstIndex = $Text.IndexOf($First, [System.StringComparison]::Ordinal)
    $secondIndex = $Text.IndexOf($Second, [System.StringComparison]::Ordinal)
    Assert-True -Condition ($firstIndex -ge 0) -Message "Missing first marker for order assertion: $First"
    Assert-True -Condition ($secondIndex -ge 0) -Message "Missing second marker for order assertion: $Second"
    Assert-True -Condition ($firstIndex -lt $secondIndex) -Message $Message
}
```

- [ ] **Step 3: Add doctor guard test**

Add this function near the other deploy-script guard functions:

```powershell
function Test-DevDoctorScriptContract {
    Assert-True -Condition (Test-Path $DoctorScript) -Message 'Dev doctor script must exist at scripts\rook-dev-doctor.ps1.'

    $content = Get-Content -Path $DoctorScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$Strict' -Message 'Dev doctor must expose a -Strict switch.'
    Assert-Contains -Text $content -Expected 'function Write-CheckResult' -Message 'Dev doctor must report checks through one explicit result helper.'
    Assert-Contains -Text $content -Expected 'PASS' -Message 'Dev doctor must print PASS statuses.'
    Assert-Contains -Text $content -Expected 'WARN' -Message 'Dev doctor must print WARN statuses.'
    Assert-Contains -Text $content -Expected 'FAIL' -Message 'Dev doctor must print FAIL statuses.'
    Assert-Contains -Text $content -Expected 'OCCT_ROOT' -Message 'Dev doctor must report OCCT_ROOT status.'
    Assert-Contains -Text $content -Expected 'fallback' -Message 'Dev doctor must report whether the existing hardcoded OCCT fallback would be used.'
    Assert-Contains -Text $content -Expected 'mcp_server\.venv\Scripts\python.exe' -Message 'Dev doctor must check the repo MCP venv path.'
    Assert-Contains -Text $content -Expected 'python -m rook' -Message 'Dev doctor must check stale rook MCP processes.'
    Assert-Contains -Text $content -Expected 'RookChatService.json' -Message 'Dev doctor must report installed chat manifest mode.'
    Assert-Contains -Text $content -Expected '$ManagedCompanionRuntimes = @(''net8.0'', ''net7.0'', ''net48'')' -Message 'Dev doctor must know the managed runtime child manifest folders.'
    Assert-Contains -Text $content -Expected 'Chat manifest net8.0' -Message 'Dev doctor must report the net8.0 runtime-child chat manifest.'
    Assert-NotContains -Text $content -Unexpected 'Set-ItemProperty -Path' -Message 'Dev doctor must not write registry values.'
    Assert-NotContains -Text $content -Unexpected 'Remove-Item -LiteralPath' -Message 'Dev doctor must not remove files.'
    Assert-NotContains -Text $content -Unexpected 'New-Item -ItemType Directory' -Message 'Dev doctor must not create directories.'
}
```

Note: the positive `Set-ItemProperty` marker above is intentionally paired with the negative check so a future reader sees why registry mutation is in scope for the guard.

- [ ] **Step 4: Add local deploy OCCT guard test**

Add this function near `Test-DeployScriptNativeOnlyIsNarrow`:

```powershell
function Test-DeployScriptCopiesOcctRuntimeClosure {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '$OcctFallbackRoot = ''C:\Users\aryan\source\repos\OCCT\build-rook''' -Message 'Local deploy must retain the existing OCCT fallback path without reading vcxproj files.'
    Assert-Contains -Text $content -Expected '$OcctRuntimeDlls = @(' -Message 'Local deploy must use an explicit OCCT runtime DLL list.'
    foreach ($dll in @(
        'TKernel.dll',
        'TKMath.dll',
        'TKG2d.dll',
        'TKG3d.dll',
        'TKGeomBase.dll',
        'TKGeomAlgo.dll',
        'TKBRep.dll',
        'TKTopAlgo.dll',
        'TKPrim.dll',
        'TKBO.dll',
        'TKShHealing.dll'
    )) {
        Assert-Contains -Text $content -Expected "'$dll'" -Message "Local deploy must include measured OCCT runtime DLL $dll."
    }
    Assert-NotContains -Text $content -Unexpected "'TKBool.dll'" -Message 'Local deploy must not add linked-but-not-loaded TKBool.dll in PR 1.'
    Assert-NotContains -Text $content -Unexpected "'TKMesh.dll'" -Message 'Local deploy must not add linked-but-not-loaded TKMesh.dll in PR 1.'
    Assert-Contains -Text $content -Expected 'function Resolve-OcctRuntimeRoot' -Message 'Local deploy must resolve OCCT root through an explicit helper.'
    Assert-Contains -Text $content -Expected '$env:OCCT_ROOT' -Message 'Local deploy must prefer OCCT_ROOT.'
    Assert-Contains -Text $content -Expected '$OcctFallbackRoot' -Message 'Local deploy must fall back to the existing hardcoded OCCT path.'
    Assert-Contains -Text $content -Expected 'OCCT root source:' -Message 'Local deploy must report whether OCCT_ROOT or fallback was used.'
    Assert-Contains -Text $content -Expected 'function Copy-OcctRuntimeDlls' -Message 'Local deploy must copy OCCT runtime DLLs through an explicit helper.'
    Assert-Contains -Text $content -Expected 'Join-Path $resolved.Root ''win64\vc14\bin''' -Message 'Local deploy must copy OCCT DLLs from the resolved runtime bin folder.'
    Assert-Contains -Text $content -Expected 'Copy-RequiredFile $source (Join-Path $PluginDir $dll)' -Message 'Local deploy must copy OCCT DLLs next to RookNative.rhp.'
    Assert-Before -Text $content -First 'Copy-RequiredFile (Join-Path $nativeDir ''RookNative.rhp'')' -Second 'Copy-OcctRuntimeDlls' -Message 'Local deploy must copy RookNative.rhp before copying the OCCT runtime closure.'
}
```

- [ ] **Step 5: Update net8 registration guard**

In `Test-DeployScriptUsesMultiRuntimeCompanionLayout`, replace this assertion:

```powershell
Assert-Contains -Text $content -Expected 'Join-Path $PluginDir ''net7.0\Rook.rhp''' -Message 'Local deploy must register the net7.0 child RHP anchor.'
```

with:

```powershell
Assert-Contains -Text $content -Expected 'Join-Path $PluginDir ''net8.0\Rook.rhp''' -Message 'Local deploy must register the net8.0 child RHP anchor.'
Assert-NotContains -Text $content -Unexpected '-CompanionRhpPath (Join-Path $PluginDir ''net7.0\Rook.rhp'')' -Message 'Full local deploy must not register the net7.0 companion anchor.'
```

- [ ] **Step 6: Add registration fallback order guard**

Add this function after `Test-RegisterSuiteSupportsNativeOnlyPreserveCompanion`:

```powershell
function Test-RegisterSuitePrefersNet8CompanionFallback {
    $content = Get-Content -Path $RegisterSuiteScript -Raw

    Assert-Contains -Text $content -Expected '$candidateCompanions = @(' -Message 'Suite registration must keep explicit companion fallback discovery.'
    Assert-Contains -Text $content -Expected 'Join-Path $nativeDir ''net8.0\Rook.rhp''' -Message 'Suite registration must discover net8.0 companion payloads.'
    Assert-Contains -Text $content -Expected 'Join-Path $nativeDir ''net7.0\Rook.rhp''' -Message 'Suite registration must preserve net7.0 fallback compatibility.'
    Assert-Contains -Text $content -Expected 'Join-Path $nativeDir ''Rook.rhp''' -Message 'Suite registration must preserve root-level fallback compatibility.'
    Assert-Before -Text $content -First 'Join-Path $nativeDir ''net8.0\Rook.rhp''' -Second 'Join-Path $nativeDir ''net7.0\Rook.rhp''' -Message 'Suite registration must prefer net8.0 before net7.0.'
    Assert-Before -Text $content -First 'Join-Path $nativeDir ''net7.0\Rook.rhp''' -Second 'Join-Path $nativeDir ''Rook.rhp''' -Message 'Suite registration must prefer runtime child payloads before root fallback.'
}
```

- [ ] **Step 7: Add AGENT_SETUP convention guard**

Add this function after `Test-RegisterSuitePrefersNet8CompanionFallback`:

```powershell
function Test-AgentSetupDocumentsDevDeployConvention {
    $content = Get-Content -Path $AgentSetup -Raw

    Assert-Contains -Text $content -Expected '## Developer Machine Convention' -Message 'AGENT_SETUP must document the developer-machine convention.'
    Assert-Contains -Text $content -Expected 'scripts\rook-dev-doctor.ps1' -Message 'AGENT_SETUP must tell developers to run the dev doctor.'
    Assert-Contains -Text $content -Expected '-UseRepoVenv' -Message 'AGENT_SETUP must document the repo-venv dev deploy command.'
    Assert-Contains -Text $content -Expected 'OCCT_ROOT' -Message 'AGENT_SETUP must document the OCCT_ROOT expectation.'
    Assert-Contains -Text $content -Expected 'python -m rook' -Message 'AGENT_SETUP must tell developers to close stale rook MCP processes before deploy.'
}
```

- [ ] **Step 8: Add test calls**

At the bottom of `scripts/tests/deploy-local-testing-guards.tests.ps1`, add the new test calls before `Write-Host`:

```powershell
Test-DevDoctorScriptContract
Test-DeployScriptCopiesOcctRuntimeClosure
Test-RegisterSuitePrefersNet8CompanionFallback
Test-AgentSetupDocumentsDevDeployConvention
```

The final call list should include:

```powershell
Test-DeployScriptSelectsExplicitMsvcToolset
Test-DeployScriptSyncsChirpFromSiblingRepo
Test-DeployScriptInstallsChirpByDefault
Test-DeployScriptVerifiesChirpRuntimeAndConfig
Test-DeployScriptVerifiesRookImportOrigin
Test-DeployScriptParsesMcpConfigs
Test-DeployScriptVerifiesChatManifest
Test-DeployScriptSeedsChatEnvWithoutOverwriting
Test-DeployScriptCopiesAllInstallerPythonModules
Test-DeployScriptHasExplicitDevRuntimeContract
Test-DeployScriptWritesChatManifestToRuntimeChildren
Test-DeployScriptLiveSmokeIsExplicit
Test-DeployScriptNativeOnlyIsNarrow
Test-DeployScriptUsesMultiRuntimeCompanionLayout
Test-RegisterSuiteSupportsNativeOnlyPreserveCompanion
Test-DeployScriptNativeOnlySkipBuildFastPath
Test-DeploySkillPointsToAuthoritativeScriptAndChirpChecks
Test-DevDoctorScriptContract
Test-DeployScriptCopiesOcctRuntimeClosure
Test-RegisterSuitePrefersNet8CompanionFallback
Test-AgentSetupDocumentsDevDeployConvention

Write-Host 'Local testing deploy guard tests passed.'
```

- [ ] **Step 9: Run guards and verify they fail**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: failure mentioning at least `Dev doctor script must exist at scripts\rook-dev-doctor.ps1.` The AGENT_SETUP convention guard may also fail until Task 5.

- [ ] **Step 10: Commit failing guard tests**

```powershell
git add scripts\tests\deploy-local-testing-guards.tests.ps1
git commit -m "test: guard dev deploy readiness contract"
```

---

### Task 2: Add Read-Only Dev Doctor

**Files:**
- Create: `scripts/rook-dev-doctor.ps1`

- [ ] **Step 1: Create the doctor script**

Create `scripts/rook-dev-doctor.ps1` with this content:

```powershell
# rook-dev-doctor.ps1
#
# Read-only preflight for local Rook development machines. Reports machine and
# repo state; does not install, register, stop processes, or edit files.

[CmdletBinding()]
param(
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir
$OcctFallbackRoot = 'C:\Users\aryan\source\repos\OCCT\build-rook'
$ManagedCompanionRuntimes = @('net8.0', 'net7.0', 'net48')
$OcctRuntimeDlls = @(
    'TKernel.dll',
    'TKMath.dll',
    'TKG2d.dll',
    'TKG3d.dll',
    'TKGeomBase.dll',
    'TKGeomAlgo.dll',
    'TKBRep.dll',
    'TKTopAlgo.dll',
    'TKPrim.dll',
    'TKBO.dll',
    'TKShHealing.dll'
)

$script:PassCount = 0
$script:WarnCount = 0
$script:FailCount = 0

function Write-CheckResult {
    param(
        [ValidateSet('PASS', 'WARN', 'FAIL')]
        [string]$Status,
        [string]$Name,
        [string]$Detail
    )

    switch ($Status) {
        'PASS' { $script:PassCount++ }
        'WARN' { $script:WarnCount++ }
        'FAIL' { $script:FailCount++ }
    }

    Write-Host ("[{0}] {1}: {2}" -f $Status, $Name, $Detail)
}

function Test-PathExists {
    param(
        [string]$Label,
        [string]$Path
    )

    if (Test-Path $Path) {
        Write-CheckResult -Status 'PASS' -Name $Label -Detail $Path
        return $true
    }

    Write-CheckResult -Status 'FAIL' -Name $Label -Detail "Missing: $Path"
    return $false
}

function Invoke-Git {
    param([string[]]$Arguments)

    $output = & git -C $RepoRoot @Arguments 2>$null
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = @($output)
    }
}

function Test-GitState {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-CheckResult -Status 'FAIL' -Name 'Git' -Detail 'git command not found.'
        return
    }

    $inside = Invoke-Git @('rev-parse', '--is-inside-work-tree')
    if ($inside.ExitCode -ne 0 -or (($inside.Output -join '').Trim()) -ne 'true') {
        Write-CheckResult -Status 'FAIL' -Name 'Git repo' -Detail 'Current directory is not inside a git worktree.'
        return
    }

    $branch = Invoke-Git @('branch', '--show-current')
    $branchName = (($branch.Output -join '').Trim())
    if (-not $branchName) {
        $branchName = '(detached)'
    }
    Write-CheckResult -Status 'PASS' -Name 'Git branch' -Detail $branchName

    $status = Invoke-Git @('status', '--short')
    if ($status.Output.Count -gt 0) {
        Write-CheckResult -Status 'WARN' -Name 'Git status' -Detail 'Working tree has local changes.'
    } else {
        Write-CheckResult -Status 'PASS' -Name 'Git status' -Detail 'Working tree is clean.'
    }

    $upstream = Invoke-Git @('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}')
    if ($upstream.ExitCode -ne 0) {
        Write-CheckResult -Status 'WARN' -Name 'Git upstream' -Detail 'No upstream configured.'
        return
    }

    $upstreamName = (($upstream.Output -join '').Trim())
    $counts = Invoke-Git @('rev-list', '--left-right', '--count', "HEAD...$upstreamName")
    if ($counts.ExitCode -ne 0) {
        Write-CheckResult -Status 'WARN' -Name 'Git divergence' -Detail "Could not compare with $upstreamName."
        return
    }

    $parts = (($counts.Output -join ' ').Trim() -split '\s+')
    $ahead = [int]$parts[0]
    $behind = [int]$parts[1]
    if ($ahead -eq 0 -and $behind -eq 0) {
        Write-CheckResult -Status 'PASS' -Name 'Git divergence' -Detail "In sync with $upstreamName."
    } else {
        Write-CheckResult -Status 'WARN' -Name 'Git divergence' -Detail "Ahead $ahead, behind $behind versus $upstreamName."
    }
}

function Test-RequiredPaths {
    Test-PathExists -Label 'Repo root' -Path $RepoRoot | Out-Null
    Test-PathExists -Label 'scripts' -Path (Join-Path $RepoRoot 'scripts') | Out-Null
    Test-PathExists -Label 'deploy-local-testing.ps1' -Path (Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1') | Out-Null
    Test-PathExists -Label 'mcp_server' -Path (Join-Path $RepoRoot 'mcp_server') | Out-Null
    Test-PathExists -Label 'repo MCP venv Python' -Path (Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe') | Out-Null
    Test-PathExists -Label 'src\RookNative' -Path (Join-Path $RepoRoot 'src\RookNative') | Out-Null
    Test-PathExists -Label 'src\Rook' -Path (Join-Path $RepoRoot 'src\Rook') | Out-Null
    Test-PathExists -Label 'src\RookBim' -Path (Join-Path $RepoRoot 'src\RookBim') | Out-Null
}

function Test-Processes {
    $rhino = @(Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' })
    if ($rhino.Count -gt 0) {
        Write-CheckResult -Status 'WARN' -Name 'Rhino process' -Detail ("Running Rhino process ids: " + (($rhino | Select-Object -ExpandProperty Id) -join ', '))
    } else {
        Write-CheckResult -Status 'PASS' -Name 'Rhino process' -Detail 'Rhino is not running.'
    }

    $rookPython = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match '(^|\s)-m\s+rook(\s|$)' })
    if ($rookPython.Count -gt 0) {
        Write-CheckResult -Status 'WARN' -Name 'python -m rook process' -Detail ("Running process ids: " + (($rookPython | Select-Object -ExpandProperty ProcessId) -join ', '))
    } else {
        Write-CheckResult -Status 'PASS' -Name 'python -m rook process' -Detail 'No stale rook MCP processes found.'
    }
}

function Resolve-OcctRuntimeRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:OCCT_ROOT)) {
        return [pscustomobject]@{
            Root = $env:OCCT_ROOT
            Source = 'OCCT_ROOT'
        }
    }

    return [pscustomobject]@{
        Root = $OcctFallbackRoot
        Source = 'fallback'
    }
}

function Test-OcctRoot {
    $resolved = Resolve-OcctRuntimeRoot
    Write-CheckResult -Status 'PASS' -Name 'OCCT root source' -Detail "$($resolved.Source): $($resolved.Root)"

    if (-not (Test-Path $resolved.Root)) {
        Write-CheckResult -Status 'FAIL' -Name 'OCCT root' -Detail "Missing: $($resolved.Root)"
        return
    }

    $header = Join-Path $resolved.Root 'inc\TKernel.hxx'
    $lib = Join-Path $resolved.Root 'win64\vc14\lib\TKernel.lib'
    $bin = Join-Path $resolved.Root 'win64\vc14\bin'

    if (Test-Path $header) {
        $headerText = Get-Content -LiteralPath $header -TotalCount 5 -ErrorAction SilentlyContinue
        if (($headerText -join "`n") -match 'C:\\Users\\aryan\\source\\repos\\OCCT') {
            Write-CheckResult -Status 'FAIL' -Name 'OCCT headers' -Detail "Forwarding header detected: $header"
        } else {
            Write-CheckResult -Status 'PASS' -Name 'OCCT headers' -Detail $header
        }
    } else {
        Write-CheckResult -Status 'FAIL' -Name 'OCCT headers' -Detail "Missing: $header"
    }

    if (Test-Path $lib) {
        Write-CheckResult -Status 'PASS' -Name 'OCCT lib' -Detail $lib
    } else {
        Write-CheckResult -Status 'FAIL' -Name 'OCCT lib' -Detail "Missing: $lib"
    }

    if (-not (Test-Path $bin)) {
        Write-CheckResult -Status 'FAIL' -Name 'OCCT bin' -Detail "Missing: $bin"
        return
    }

    $missingDlls = @()
    foreach ($dll in $OcctRuntimeDlls) {
        $candidate = Join-Path $bin $dll
        if (-not (Test-Path $candidate)) {
            $missingDlls += $dll
        }
    }

    if ($missingDlls.Count -eq 0) {
        Write-CheckResult -Status 'PASS' -Name 'OCCT runtime DLLs' -Detail "Found measured runtime closure in $bin."
    } else {
        Write-CheckResult -Status 'FAIL' -Name 'OCCT runtime DLLs' -Detail ("Missing: " + ($missingDlls -join ', '))
    }
}

function Test-MsvcMfc {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $vswhere)) {
        Write-CheckResult -Status 'WARN' -Name 'Visual Studio' -Detail 'vswhere.exe not found.'
        return
    }

    $installPath = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null) -join ''
    if (-not $installPath) {
        Write-CheckResult -Status 'FAIL' -Name 'Visual Studio' -Detail 'VS installation with C++ tools not found.'
        return
    }

    $vcTools = Join-Path $installPath 'VC\Tools\MSVC\14.44.35207'
    $mfc = Join-Path $vcTools 'atlmfc\include\afxwin.h'
    if (Test-Path $mfc) {
        Write-CheckResult -Status 'PASS' -Name 'MSVC 14.44 + MFC' -Detail $mfc
    } else {
        Write-CheckResult -Status 'FAIL' -Name 'MSVC 14.44 + MFC' -Detail "Missing: $mfc"
    }
}

function Test-RepoVenvImport {
    $python = Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        Write-CheckResult -Status 'FAIL' -Name 'repo venv import' -Detail "Missing: $python"
        return
    }

    $src = Join-Path $RepoRoot 'mcp_server\src'
    $oldPythonPath = $env:PYTHONPATH
    try {
        $env:PYTHONPATH = $src
        $output = & $python -c "import rook, sys; print(rook.__file__)" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-CheckResult -Status 'PASS' -Name 'repo venv import' -Detail (($output | Select-Object -First 1) -join '')
        } else {
            Write-CheckResult -Status 'FAIL' -Name 'repo venv import' -Detail (($output | Out-String).Trim())
        }
    } finally {
        $env:PYTHONPATH = $oldPythonPath
    }
}

function Test-ChirpSibling {
    $chirp = Join-Path (Split-Path -Parent $RepoRoot) 'Chirp'
    if ((Test-Path (Join-Path $chirp 'pyproject.toml')) -and (Test-Path (Join-Path $chirp 'src\chirp'))) {
        Write-CheckResult -Status 'PASS' -Name 'Chirp sibling' -Detail $chirp
    } else {
        Write-CheckResult -Status 'WARN' -Name 'Chirp sibling' -Detail "Missing or incomplete: $chirp"
    }
}

function Test-RevitApi {
    $revit = if (-not [string]::IsNullOrWhiteSpace($env:RevitInstallDir)) {
        $env:RevitInstallDir
    } else {
        Join-Path $env:ProgramFiles 'Autodesk\Revit 2024'
    }

    $api = Join-Path $revit 'RevitAPI.dll'
    $apiUi = Join-Path $revit 'RevitAPIUI.dll'
    if ((Test-Path $api) -and (Test-Path $apiUi)) {
        Write-CheckResult -Status 'PASS' -Name 'Revit API' -Detail $revit
    } else {
        Write-CheckResult -Status 'FAIL' -Name 'Revit API' -Detail "Missing RevitAPI.dll or RevitAPIUI.dll under $revit"
    }
}

function Test-InnoSetup {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    $found = @($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
    if ($found.Count -gt 0) {
        Write-CheckResult -Status 'PASS' -Name 'Inno Setup' -Detail $found[0]
    } else {
        Write-CheckResult -Status 'WARN' -Name 'Inno Setup' -Detail 'ISCC.exe not found.'
    }
}

function Test-ChatManifest {
    $pluginDir = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
    $manifestPaths = @((Join-Path $pluginDir 'RookChatService.json'))
    foreach ($runtime in $ManagedCompanionRuntimes) {
        $manifestPaths += Join-Path $pluginDir "$runtime\RookChatService.json"
    }

    foreach ($manifestPath in $manifestPaths) {
        $label = if ($manifestPath -match '\\net8\.0\\') {
            'Chat manifest net8.0'
        } elseif ($manifestPath -match '\\net7\.0\\') {
            'Chat manifest net7.0'
        } elseif ($manifestPath -match '\\net48\\') {
            'Chat manifest net48'
        } else {
            'Chat manifest root'
        }

        if (-not (Test-Path $manifestPath)) {
            if ($label -eq 'Chat manifest root' -or $label -eq 'Chat manifest net8.0') {
                Write-CheckResult -Status 'WARN' -Name $label -Detail "Missing: $manifestPath"
            }
            continue
        }

        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            $mode = $manifest.environment.ROOK_MODE
            if ($mode -eq 'dev' -or $mode -eq 'release') {
                Write-CheckResult -Status 'PASS' -Name $label -Detail "Mode: $mode"
            } else {
                Write-CheckResult -Status 'WARN' -Name $label -Detail "Unexpected mode: $mode"
            }
        } catch {
            Write-CheckResult -Status 'WARN' -Name $label -Detail "Could not parse $manifestPath`: $($_.Exception.Message)"
        }
    }
}

Write-Host 'Rook dev doctor'
Write-Host "Repo: $RepoRoot"
Write-Host "Strict: $Strict"
Write-Host ''

Test-GitState
Test-RequiredPaths
Test-Processes
Test-MsvcMfc
Test-OcctRoot
Test-RepoVenvImport
Test-ChirpSibling
Test-RevitApi
Test-InnoSetup
Test-ChatManifest

Write-Host ''
Write-Host "Summary: PASS=$script:PassCount WARN=$script:WarnCount FAIL=$script:FailCount"

if ($script:FailCount -gt 0) {
    exit 1
}

if ($Strict -and $script:WarnCount -gt 0) {
    exit 1
}

exit 0
```

- [ ] **Step 2: Run guards**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: still fails on deploy OCCT copy or net8 registration checks. It should no longer fail because the doctor script is missing.

- [ ] **Step 3: Run doctor in default mode**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-dev-doctor.ps1
```

Expected on this machine: a readable PASS/WARN/FAIL report. Exit may be nonzero if a core blocker is present; do not treat that as a script crash unless PowerShell reports a syntax/runtime exception.

- [ ] **Step 4: Commit doctor**

```powershell
git add scripts\rook-dev-doctor.ps1
git commit -m "feat: add read-only dev doctor"
```

---

### Task 3: Copy OCCT Runtime DLLs During Local Native Deploy

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`

- [ ] **Step 1: Add OCCT constants**

In `scripts/deploy-local-testing.ps1`, after `$ManagedCompanionRuntimes`, add:

```powershell
$OcctFallbackRoot = 'C:\Users\aryan\source\repos\OCCT\build-rook'
$OcctRuntimeDlls = @(
    'TKernel.dll',
    'TKMath.dll',
    'TKG2d.dll',
    'TKG3d.dll',
    'TKGeomBase.dll',
    'TKGeomAlgo.dll',
    'TKBRep.dll',
    'TKTopAlgo.dll',
    'TKPrim.dll',
    'TKBO.dll',
    'TKShHealing.dll'
)
```

- [ ] **Step 2: Add OCCT resolver and copy helper**

Add these functions after `Copy-OptionalFile`:

```powershell
function Resolve-OcctRuntimeRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:OCCT_ROOT)) {
        return [pscustomobject]@{
            Root = $env:OCCT_ROOT
            Source = 'OCCT_ROOT'
        }
    }

    return [pscustomobject]@{
        Root = $OcctFallbackRoot
        Source = 'fallback'
    }
}

function Copy-OcctRuntimeDlls {
    $resolved = Resolve-OcctRuntimeRoot
    Write-Host "OCCT root source: $($resolved.Source)"
    Write-Host "OCCT root:        $($resolved.Root)"

    if (-not (Test-Path $resolved.Root)) {
        throw "OCCT root not found: $($resolved.Root). Set OCCT_ROOT to a valid OCCT build root."
    }

    $sourceDir = Join-Path $resolved.Root 'win64\vc14\bin'
    if (-not (Test-Path $sourceDir)) {
        throw "OCCT runtime bin directory not found: $sourceDir"
    }

    foreach ($dll in $OcctRuntimeDlls) {
        $source = Join-Path $sourceDir $dll
        Copy-RequiredFile $source (Join-Path $PluginDir $dll)
    }
}
```

- [ ] **Step 3: Call OCCT copy from native payload deploy**

Update `Deploy-NativePayload` to:

```powershell
function Deploy-NativePayload {
    New-Item -ItemType Directory -Force -Path $PluginDir | Out-Null

    $nativeDir = Join-Path $RepoRoot "src\RookNative\bin\$Configuration\x64"

    Copy-RequiredFile (Join-Path $nativeDir 'RookNative.rhp') (Join-Path $PluginDir 'RookNative.rhp')
    Copy-OptionalFile (Join-Path $nativeDir 'RookNative.pdb') (Join-Path $PluginDir 'RookNative.pdb')
    Copy-OcctRuntimeDlls
}
```

- [ ] **Step 4: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: still fails on net8 registration and fallback order. OCCT copy checks should pass.

- [ ] **Step 5: Commit OCCT deploy copy**

```powershell
git add scripts\deploy-local-testing.ps1
git commit -m "fix: copy occt runtime dlls in local deploy"
```

---

### Task 4: Switch Full Deploy Registration To net8

**Files:**
- Modify: `scripts/deploy-local-testing.ps1`
- Modify: `scripts/register-rooknative-suite.ps1`
- Modify: `scripts/register-companion.ps1`
- Modify: `scripts/tests/deploy-local-testing-guards.tests.ps1`

- [ ] **Step 1: Update full deploy registration path**

In `scripts/deploy-local-testing.ps1`, change `Register-Plugins` to:

```powershell
function Register-Plugins {
    $register = Join-Path $RepoRoot 'scripts\register-rooknative-suite.ps1'
    & $register -NativeRhpPath (Join-Path $PluginDir 'RookNative.rhp') -CompanionRhpPath (Join-Path $PluginDir 'net8.0\Rook.rhp')
}
```

- [ ] **Step 2: Update registration fallback order**

In `scripts/register-rooknative-suite.ps1`, replace the `$candidateCompanions` block with:

```powershell
    $candidateCompanions = @(
        (Join-Path $nativeDir 'net8.0\Rook.rhp'),
        (Join-Path $nativeDir 'net7.0\Rook.rhp'),
        (Join-Path $nativeDir 'Rook.rhp')
    )
```

Do not change `-NativeOnlyPreserveCompanion` logic.

- [ ] **Step 3: Update companion registration validation**

In `scripts/register-companion.ps1`, allow both `net8.0` and `net7.0` while
continuing to reject `net48`:

```powershell
$UnsupportedRuntimeMetadataMessage = 'Rook companion runtime metadata must identify a net8.0 or net7.0 build for registration.'
```

The path segment check should return for either supported runtime:

```powershell
    if (Test-PathHasExactSegment -Path $Path -Segment 'net8.0') {
        return
    }

    if (Test-PathHasExactSegment -Path $Path -Segment 'net7.0') {
        return
    }
```

The runtime metadata check should also return for either supported TFM:

```powershell
    if ($tfm -eq 'net8.0' -or $tfm -eq 'net7.0') {
        return
    }
```

Do not weaken the `net48` rejection.

- [ ] **Step 4: Add companion registrar guard**

In `scripts/tests/deploy-local-testing-guards.tests.ps1`, add a path variable:

```powershell
$RegisterCompanionScript = Join-Path $RepoRoot 'scripts\register-companion.ps1'
```

Add this guard function:

```powershell
function Test-RegisterCompanionAcceptsNet8Runtime {
    $content = Get-Content -Path $RegisterCompanionScript -Raw

    Assert-Contains -Text $content -Expected '$UnsupportedRuntimeMetadataMessage = ''Rook companion runtime metadata must identify a net8.0 or net7.0 build for registration.''' -Message 'Companion registration must describe net8.0/net7.0 as supported runtimes.'
    Assert-Contains -Text $content -Expected 'Test-PathHasExactSegment -Path $Path -Segment ''net8.0''' -Message 'Companion registration must accept explicit net8.0 paths.'
    Assert-Contains -Text $content -Expected 'Test-PathHasExactSegment -Path $Path -Segment ''net7.0''' -Message 'Companion registration must preserve explicit net7.0 paths.'
    Assert-Contains -Text $content -Expected '$tfm -eq ''net8.0''' -Message 'Companion registration must accept net8.0 runtime metadata.'
    Assert-Contains -Text $content -Expected '$tfm -eq ''net7.0''' -Message 'Companion registration must preserve net7.0 runtime metadata.'
    Assert-Contains -Text $content -Expected '$tfm -eq ''net48''' -Message 'Companion registration must continue rejecting net48 runtime metadata.'
    Assert-Contains -Text $content -Expected '$UnsupportedNet48CompanionMessage' -Message 'Companion registration must preserve the net48 rejection message path.'
}
```

Call it near the other registration guards.

- [ ] **Step 5: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: all guard tests pass.

- [ ] **Step 6: Run net48 companion guard**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\issue112-net48-companion-guards.tests.ps1
```

Expected: pass. This protects the net48 rejection behavior while allowing `net8.0`.

- [ ] **Step 7: Commit registration change**

```powershell
git add scripts\deploy-local-testing.ps1 scripts\register-rooknative-suite.ps1 scripts\register-companion.ps1 scripts\tests\deploy-local-testing-guards.tests.ps1
git commit -m "fix: prefer net8 companion registration"
```

---

### Task 5: Document Developer Machine Convention

**Files:**
- Modify: `AGENT_SETUP.md`

- [ ] **Step 1: Add a developer-machine section**

In `AGENT_SETUP.md`, after the prerequisites table and before `## Installation`, add:

```markdown
## Developer Machine Convention

For source-tree development, use `main` as the shared source of truth and use task
branches only for isolated work. Do not maintain separate laptop and desktop source
branches.

Before a local deploy from source:

1. Pull current `main`.
2. Run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-dev-doctor.ps1
   ```

3. Close Rhino and any `python -m rook` process.
4. Deploy with the repo Python runtime:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
   ```

5. Restart Rhino.
6. Optionally run the existing payload-only live smoke flow after Rhino and
   Grasshopper are open.

Prepared dev machines should set `OCCT_ROOT` to the active OCCT build root. The
native projects still contain a hardcoded fallback path for PR 1; removing that
fallback is a follow-up change after both laptop and desktop pass the doctor from a
fresh shell.
```

- [ ] **Step 2: Run guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected: all guard tests pass.

- [ ] **Step 3: Commit docs**

```powershell
git add AGENT_SETUP.md
git commit -m "docs: document dev deploy convention"
```

---

### Task 6: Final Verification And PR Scope Check

**Files:**
- Read: `git diff --name-only origin/main...HEAD`
- Read: `git status --short --branch`

- [ ] **Step 1: Run static guard verification**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\deploy-local-testing-guards.tests.ps1
```

Expected:

```text
Local testing deploy guard tests passed.
```

- [ ] **Step 2: Run doctor**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-dev-doctor.ps1
```

Expected: the script prints `Rook dev doctor`, a list of `PASS`, `WARN`, and `FAIL` checks, and a final summary. If it exits nonzero because a real local prerequisite is missing, record the failing check in the final report instead of claiming the machine passed doctor.

- [ ] **Step 3: Optionally run full dev deploy on a prepared machine**

Run only if Rhino is closed, stale `python -m rook` processes are stopped, and doctor reports no core blockers:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -UseRepoVenv
```

Expected: deploy completes, copies `RookNative.rhp`, writes chat manifests in dev mode, copies OCCT runtime DLLs next to `RookNative.rhp`, and registers the companion as `net8.0\Rook.rhp`.

- [ ] **Step 4: Verify PR 1 file scope**

Run:

```powershell
git diff --name-only origin/main...HEAD
```

Expected output contains only:

```text
AGENT_SETUP.md
docs/superpowers/plans/2026-06-18-dev-deploy-readiness-pr1.md
docs/superpowers/specs/2026-06-18-dev-deploy-readiness-pr1-design.md
scripts/deploy-local-testing.ps1
scripts/register-companion.ps1
scripts/register-rooknative-suite.ps1
scripts/rook-dev-doctor.ps1
scripts/tests/deploy-local-testing-guards.tests.ps1
```

Do not include `.vcxproj`, `.vcxproj.filters`, installer files, release pipeline scripts, or release guard tests.

- [ ] **Step 5: Verify worktree state**

Run:

```powershell
git status --short --branch
```

Expected: branch is ahead of `origin/main` with no unstaged or staged changes.

---

## Self-Review Notes

Spec coverage:

- Doctor script: Task 2.
- Explicit local deploy paths: Task 2.
- `-Strict` behavior: Task 2.
- OCCT root resolution and measured DLL copy: Task 3.
- net8 full deploy registration and fallback order: Task 4.
- register-companion net8 validation compatibility: Task 4.
- AGENT_SETUP convention: Task 5.
- AGENT_SETUP convention guard: Task 1.
- Guard tests: Task 1 plus each task's verification.
- PR scope exclusion for project, installer, and release files: Task 6.

Plan scan:

- No implementation step relies on project-file parsing.
- No task edits `.vcxproj`, `.vcxproj.filters`, installer files, release pipeline scripts, or release guard tests.
- Native-only preserve-companion registration is read by tests but not modified.
