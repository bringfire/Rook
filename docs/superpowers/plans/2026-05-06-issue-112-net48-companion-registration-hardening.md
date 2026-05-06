# Issue 112 net48 Companion Registration Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent every installer and registration path from selecting or registering a Rhino 8 Rook companion built from `net48`.

**Architecture:** Keep the fix in the existing PowerShell scripts. `install.ps1` becomes `net7.0`-only for deployable companion selection and validates release-package runtime metadata before deployment; `scripts/register-companion.ps1` owns final path validation before registry writes, so direct companion registration and `register-rooknative-suite.ps1` delegation share one rule.

**Tech Stack:** PowerShell, existing installer summary helpers, .NET `runtimeconfig.json`, `dotnet build -f net7.0`, no new dependencies, no native project changes.

---

## File Structure

- Modify `install.ps1`
  - Add a small runtime metadata validator for release-package `plugin\Rook.rhp`.
  - Remove `net48` fallback variables, dry-run planning, reuse, and post-build success paths from `Step-BuildCompanion`.
  - Build only `src\Rook\Rook.csproj -f net7.0 -c Release` when the companion must be built.
- Modify `scripts/register-companion.ps1`
  - Add a local path-segment validator.
  - Remove `net48` repo build candidates.
  - Delay “found/registering” output until after validation.
  - Validate the final path before any registry write.
- Create `scripts/tests/issue112-net48-companion-guards.tests.ps1`
  - Lightweight PowerShell test script with no Pester dependency.
  - Static checks fail first on the current tree, preventing unsafe pre-fix registry invocation.
  - Dynamic checks run after static guards pass and verify explicit `net48` rejection plus release-package runtime metadata rejection.

---

### Task 1: Add Safe Failing Script Tests

**Files:**
- Create: `scripts/tests/issue112-net48-companion-guards.tests.ps1`

- [ ] **Step 1: Create the script test file**

Create `scripts/tests/issue112-net48-companion-guards.tests.ps1` with this content:

```powershell
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$InstallScript = Join-Path $RepoRoot 'install.ps1'
$RegisterCompanionScript = Join-Path $RepoRoot 'scripts\register-companion.ps1'
$ExpectedNet48Message = 'net48 Rook companion builds are not supported for registration; use the net7.0 Rook.rhp output.'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Expected,
        [string]$Message
    )

    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Assert-NotContains {
    param(
        [string]$Text,
        [string]$Unexpected,
        [string]$Message
    )

    Assert-True -Condition (-not $Text.Contains($Unexpected)) -Message $Message
}

function Get-PowerShellExecutable {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwsh) {
        return $pwsh.Source
    }

    return (Get-Command powershell -ErrorAction Stop).Source
}

function ConvertTo-ProcessArgument {
    param([string]$Value)

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    return '"' + ($Value -replace '\\(?=\\*")', '$0$0' -replace '"', '\"') + '"'
}

function Invoke-ScriptProcess {
    param([string[]]$Arguments)

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = Get-PowerShellExecutable
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false

    $allArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass') + $Arguments
    $psi.Arguments = ($allArguments | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' '

    $process = [System.Diagnostics.Process]::Start($psi)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = ($stdout + "`n" + $stderr)
    }
}

function Test-InstallScriptHasNoNet48Fallbacks {
    $content = Get-Content -Path $InstallScript -Raw

    $forbidden = @(
        'src\Rook\bin\Release\net48\Rook.rhp',
        'Reuse existing companion net48 build',
        'Companion already built (net48)',
        'Companion built successfully (net48)'
    )

    foreach ($pattern in $forbidden) {
        Assert-NotContains -Text $content -Unexpected $pattern -Message "install.ps1 still contains unsafe companion fallback text: $pattern"
    }
}

function Test-RegisterScriptHasNoNet48Discovery {
    $content = Get-Content -Path $RegisterCompanionScript -Raw

    $forbidden = @(
        "src\Rook\bin\Debug\net48\Rook.rhp",
        "src\Rook\bin\Release\net48\Rook.rhp"
    )

    foreach ($pattern in $forbidden) {
        Assert-NotContains -Text $content -Unexpected $pattern -Message "register-companion.ps1 still contains unsafe discovery candidate: $pattern"
    }

    Assert-Contains -Text $content -Expected $ExpectedNet48Message -Message 'register-companion.ps1 does not contain the required net48 rejection message.'
    Assert-Contains -Text $content -Expected 'Assert-SupportedCompanionRhpPath' -Message 'register-companion.ps1 does not expose the required final path validation gate.'
}

function Test-RegisterScriptRejectsExplicitNet48Path {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-issue112-register-" + [System.Guid]::NewGuid().ToString('N'))
    $net48Dir = Join-Path $tempRoot 'bin\Release\net48'
    New-Item -ItemType Directory -Path $net48Dir -Force | Out-Null
    $fakeRhp = Join-Path $net48Dir 'Rook.rhp'
    New-Item -ItemType File -Path $fakeRhp -Force | Out-Null

    try {
        $result = Invoke-ScriptProcess -Arguments @('-File', $RegisterCompanionScript, '-RhpPath', $fakeRhp)

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Explicit net48 registration unexpectedly succeeded.'
        Assert-Contains -Text $result.Output -Expected $ExpectedNet48Message -Message "Explicit net48 registration did not report the required message. Output: $($result.Output)"
        Assert-NotContains -Text $result.Output -Unexpected 'Registering companion:' -Message 'Registration output started before net48 validation rejected the path.'
        Assert-NotContains -Text $result.Output -Unexpected 'Registration verified.' -Message 'Registration verification output appeared after a net48 rejection.'
    } finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-RegisterScriptRejectsFrameworklessNet48Package {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-issue112-register-package-" + [System.Guid]::NewGuid().ToString('N'))
    $pluginDir = Join-Path $tempRoot 'plugin'
    New-Item -ItemType Directory -Path $pluginDir -Force | Out-Null
    $fakeRhp = Join-Path $pluginDir 'Rook.rhp'
    New-Item -ItemType File -Path $fakeRhp -Force | Out-Null
    @'
{
  "runtimeOptions": {
    "tfm": "net48"
  }
}
'@ | Set-Content -Path (Join-Path $pluginDir 'Rook.runtimeconfig.json') -Encoding UTF8

    try {
        $result = Invoke-ScriptProcess -Arguments @('-File', $RegisterCompanionScript, '-RhpPath', $fakeRhp)

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Frameworkless package registration unexpectedly accepted net48 runtime metadata.'
        Assert-Contains -Text $result.Output -Expected $ExpectedNet48Message -Message "Frameworkless package registration did not report the required message. Output: $($result.Output)"
        Assert-NotContains -Text $result.Output -Unexpected 'Registering companion:' -Message 'Registration output started before runtime metadata validation rejected the path.'
        Assert-NotContains -Text $result.Output -Unexpected 'Registration verified.' -Message 'Registration verification output appeared after a runtime metadata rejection.'
    } finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-InstallReleasePackageRejectsMissingRuntimeConfig {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-issue112-install-" + [System.Guid]::NewGuid().ToString('N'))
    $pluginDir = Join-Path $tempRoot 'plugin'
    $scriptsDir = Join-Path $tempRoot 'scripts'
    New-Item -ItemType Directory -Path $pluginDir -Force | Out-Null
    New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null

    Copy-Item -LiteralPath $InstallScript -Destination (Join-Path $tempRoot 'install.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'scripts\detect-vs.ps1') -Destination (Join-Path $scriptsDir 'detect-vs.ps1') -Force
    New-Item -ItemType File -Path (Join-Path $pluginDir 'Rook.rhp') -Force | Out-Null

    try {
        $result = Invoke-ScriptProcess -Arguments @('-File', (Join-Path $tempRoot 'install.ps1'), '-DryRun', '-SkipNative', '-SkipConfig', '-SkipChirp', '-NoVerify')

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Release-package dry-run unexpectedly accepted Rook.rhp without runtime metadata.'
        Assert-Contains -Text $result.Output -Expected 'Rook companion runtime metadata missing' -Message "Missing runtimeconfig was not reported clearly. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Test-InstallScriptHasNoNet48Fallbacks
Test-RegisterScriptHasNoNet48Discovery
Test-RegisterScriptRejectsExplicitNet48Path
Test-RegisterScriptRejectsFrameworklessNet48Package
Test-InstallReleasePackageRejectsMissingRuntimeConfig

Write-Host 'Issue 112 net48 companion guard tests passed.'
```

- [ ] **Step 2: Run the script test to verify it fails safely**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\issue112-net48-companion-guards.tests.ps1
```

Expected: FAIL before invoking `register-companion.ps1`, with a message like:

```text
install.ps1 still contains unsafe companion fallback text: src\Rook\bin\Release\net48\Rook.rhp
```

- [ ] **Step 3: Commit the failing test**

Run:

```powershell
git add scripts\tests\issue112-net48-companion-guards.tests.ps1
git commit -m "Add net48 companion guard regression tests"
```

---

### Task 2: Harden register-companion.ps1 Final Path Validation

**Files:**
- Modify: `scripts/register-companion.ps1`
- Test: `scripts/tests/issue112-net48-companion-guards.tests.ps1`

- [ ] **Step 1: Add the validation message and helper functions**

In `scripts/register-companion.ps1`, after `$RegBase` is assigned, insert:

```powershell
$UnsupportedNet48CompanionMessage = 'net48 Rook companion builds are not supported for registration; use the net7.0 Rook.rhp output.'
$UnsupportedRuntimeMetadataMessage = 'Rook companion runtime metadata must identify a net7.0 build for registration.'

function Test-PathHasExactSegment {
    param(
        [string]$Path,
        [string]$Segment
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $segments = $fullPath -split '[\\/]+'
    foreach ($part in $segments) {
        if ($part -ieq $Segment) {
            return $true
        }
    }

    return $false
}

function Assert-SupportedCompanionRhpPath {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)

    if (Test-PathHasExactSegment -Path $Path -Segment 'net48') {
        throw $UnsupportedNet48CompanionMessage
    }

    if (Test-PathHasExactSegment -Path $Path -Segment 'net7.0') {
        return
    }

    $runtimeConfigPath = [System.IO.Path]::ChangeExtension($fullPath, '.runtimeconfig.json')
    if (-not (Test-Path $runtimeConfigPath)) {
        throw "$UnsupportedRuntimeMetadataMessage Missing runtime metadata at $runtimeConfigPath."
    }

    try {
        $metadata = Get-Content -Path $runtimeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "$UnsupportedRuntimeMetadataMessage Runtime metadata at $runtimeConfigPath is not valid JSON: $_"
    }

    $tfm = $metadata.runtimeOptions.tfm
    if ($tfm -eq 'net7.0') {
        return
    }

    if ($tfm -eq 'net48') {
        throw $UnsupportedNet48CompanionMessage
    }

    $reportedTfm = if ($tfm) { $tfm } else { '(missing)' }
    throw "$UnsupportedRuntimeMetadataMessage Found target framework '$reportedTfm' in $runtimeConfigPath."
}
```

- [ ] **Step 2: Narrow discovery to net7.0 and delay discovery output**

Replace the whole `if (-not $RhpPath) { ... }` resolve block with:

```powershell
if (-not $RhpPath) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoRoot  = Split-Path -Parent $ScriptDir
    $RhpSource = $null

    # Priority 1: Colocated with deployed RookNative.rhp.
    # In a deployed package, both plugins live in the same directory.
    $NativeGuid    = 'a38e0e8f-e06e-40d2-a6bd-7edbc2cb1906'
    $NativeRegPath = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$NativeGuid\PlugIn"
    $NativeReg     = Get-ItemProperty -Path $NativeRegPath -Name 'FileName' -ErrorAction SilentlyContinue

    if ($NativeReg -and $NativeReg.FileName) {
        $NativeDir = Split-Path -Parent $NativeReg.FileName
        $Colocated = Join-Path $NativeDir 'Rook.rhp'
        if (Test-Path $Colocated) {
            $RhpPath = (Resolve-Path $Colocated).Path
            $RhpSource = 'colocated with RookNative'
        }
    }

    # Priority 2: Repo build outputs (development workflow).
    if (-not $RhpPath) {
        $Candidates = @(
            (Join-Path $RepoRoot 'src\Rook\bin\Debug\net7.0\Rook.rhp'),
            (Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.rhp')
        )

        foreach ($c in $Candidates) {
            if (Test-Path $c) {
                $RhpPath = (Resolve-Path $c).Path
                $RhpSource = 'repo net7.0 build output'
                break
            }
        }
    }

    if (-not $RhpPath) {
        $msg = "Could not find Rook.rhp.`n"
        $msg += "  Checked colocated with registered RookNative (not found or native not registered).`n"
        $msg += "  Checked repo net7.0 build outputs (not built).`n`n"
        $msg += "Build the managed companion first:`n"
        $msg += "  dotnet build src\Rook\Rook.csproj -f net7.0 -c Debug`n`n"
        $msg += "Or pass -RhpPath explicitly:`n"
        $msg += "  .\scripts\register-companion.ps1 -RhpPath 'C:\path\to\Rook.rhp'"
        Write-Error $msg
        exit 1
    }
}
```

- [ ] **Step 3: Validate before any registration output or registry writes**

Replace:

```powershell
$RhpPath = (Resolve-Path $RhpPath).Path
Write-Host "Registering companion: $RhpPath"
```

with:

```powershell
$RhpPath = (Resolve-Path $RhpPath).Path
Assert-SupportedCompanionRhpPath -Path $RhpPath

if ($RhpSource) {
    Write-Host "Found companion $RhpSource`: $RhpPath"
}
Write-Host "Registering companion: $RhpPath"
```

- [ ] **Step 4: Run the guard test**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\issue112-net48-companion-guards.tests.ps1
```

Expected: still FAIL, but now on `install.ps1` fallback text or release-package runtime metadata. It must not fail on `register-companion.ps1` `net48` discovery, explicit `net48` registration, or framework-less package registration with `net48` runtime metadata.

- [ ] **Step 5: Commit register hardening**

Run:

```powershell
git add scripts\register-companion.ps1
git commit -m "Reject net48 companion registration paths"
```

---

### Task 3: Harden install.ps1 Companion Selection and Release Packages

**Files:**
- Modify: `install.ps1`
- Test: `scripts/tests/issue112-net48-companion-guards.tests.ps1`

- [ ] **Step 1: Add release-package runtime metadata validation**

In `install.ps1`, after `Add-InstallError`, insert:

```powershell
function Test-RookNet7CompanionPackage {
    param(
        [hashtable]$Summary,
        [string]$RhpPath
    )

    $runtimeConfigPath = [System.IO.Path]::ChangeExtension($RhpPath, '.runtimeconfig.json')
    if (-not (Test-Path $runtimeConfigPath)) {
        Add-InstallError -Summary $Summary -Code 'companion.runtimeconfig_missing' `
            -Message "Rook companion runtime metadata missing at $runtimeConfigPath. Rhino 8 companion deployment requires the net7.0 Rook.rhp output." `
            -Remediation "Rebuild or repackage the companion with 'dotnet build src\Rook\Rook.csproj -f net7.0 -c Release'."
        return $false
    }

    try {
        $metadata = Get-Content -Path $runtimeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Add-InstallError -Summary $Summary -Code 'companion.runtimeconfig_invalid' `
            -Message "Rook companion runtime metadata is not valid JSON at $runtimeConfigPath: $_" `
            -Remediation "Rebuild or repackage the companion with 'dotnet build src\Rook\Rook.csproj -f net7.0 -c Release'."
        return $false
    }

    $tfm = $metadata.runtimeOptions.tfm
    if ($tfm -ne 'net7.0') {
        $reportedTfm = if ($tfm) { $tfm } else { '(missing)' }
        Add-InstallError -Summary $Summary -Code 'companion.unsupported_target_framework' `
            -Message "Rook companion runtime metadata targets '$reportedTfm'. Rhino 8 companion deployment requires net7.0." `
            -Remediation "Rebuild or repackage the companion with 'dotnet build src\Rook\Rook.csproj -f net7.0 -c Release'."
        return $false
    }

    return $true
}
```

- [ ] **Step 2: Replace Step-BuildCompanion with net7.0-only logic**

Replace the full `Step-BuildCompanion` function with:

```powershell
function Step-BuildCompanion {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[6/10] Building companion plugin (C#)..." -ForegroundColor White

    $built70 = Join-Path $Context.InstallDir "src\Rook\bin\Release\net7.0\Rook.rhp"

    if ($DryRun) {
        $Summary.steps.companion.state = "planned"
        if ($Context.IsRelease) {
            $releaseCompanion = Join-Path $Context.InstallDir "plugin\Rook.rhp"
            if ((Test-Path $releaseCompanion) -and (Test-RookNet7CompanionPackage -Summary $Summary -RhpPath $releaseCompanion)) {
                $Summary.planned_actions += "Use pre-built net7.0 companion plugin from release package at $releaseCompanion"
            } elseif (Test-Path $releaseCompanion) {
                $Summary.steps.companion.state = "failed"
            } else {
                $Summary.planned_actions += "Use pre-built companion plugin from release package if present"
            }
        } else {
            if (Test-Path $built70) {
                $Summary.planned_actions += "Reuse existing companion net7.0 build at $built70"
            } else {
                $Summary.planned_actions += "Build companion C# plugin via dotnet build src/Rook/Rook.csproj -f net7.0 -c Release"
            }
        }
        Write-Host "      [PLAN] Would prepare companion plugin" -ForegroundColor Cyan
        return
    }

    if ($Context.IsRelease) {
        $releaseCompanion = Join-Path $Context.InstallDir "plugin\Rook.rhp"
        if (Test-Path $releaseCompanion) {
            if (-not (Test-RookNet7CompanionPackage -Summary $Summary -RhpPath $releaseCompanion)) {
                $Summary.steps.companion.state = "failed"
                return
            }

            $Context.CompanionBuildDir = Join-Path $Context.InstallDir "plugin"
            $Summary.steps.companion.built = $true
            $Summary.steps.companion.state = "completed"
            Write-Host "      [OK] Pre-built net7.0 companion plugin found" -ForegroundColor Green
        }
        return
    }

    if (Test-Path $built70) {
        Write-Host "      [OK] Companion already built (net7.0)" -ForegroundColor Green
        $Context.CompanionBuildDir = Split-Path -Parent $built70
        $Summary.steps.companion.built = $true
        $Summary.steps.companion.state = "completed"
        return
    }

    $dotnetCmd = Get-Command dotnet -ErrorAction SilentlyContinue
    if (-not $dotnetCmd) {
        $dotnetMissingMessage = 'dotnet SDK not found - cannot build companion plugin.'
        $dotnetMissingRemediation = 'Install .NET SDK: https://dotnet.microsoft.com/download'
        Add-InstallWarning -Summary $Summary -Code "companion.dotnet_not_found" -Message $dotnetMissingMessage -Remediation $dotnetMissingRemediation
        $Summary.steps.companion.state = "failed"
        return
    }

    $Summary.steps.companion.build_attempted = $true
    $buildTarget = Join-Path $Context.InstallDir "src\Rook\Rook.csproj"

    Write-Host "      Building from source (dotnet build src/Rook/Rook.csproj -f net7.0 -c Release)..."
    & dotnet build $buildTarget -f net7.0 -c Release --verbosity quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      Retrying with full output..." -ForegroundColor Yellow
        & dotnet build $buildTarget -f net7.0 -c Release
        if ($LASTEXITCODE -ne 0) {
            Add-InstallError -Summary $Summary -Code "companion.build_failed" `
                -Message "Companion plugin net7.0 build failed." `
                -Remediation "Run 'dotnet build src\Rook\Rook.csproj -f net7.0 -c Release' manually to see full output."
            $Summary.steps.companion.state = "failed"
            return
        }
    }

    if (Test-Path $built70) {
        $Context.CompanionBuildDir = Split-Path -Parent $built70
        $Summary.steps.companion.built = $true
        $Summary.steps.companion.state = "completed"
        Write-Host "      [OK] Companion built successfully (net7.0)" -ForegroundColor Green
    } else {
        Add-InstallError -Summary $Summary -Code "companion.build_failed" `
            -Message "Build reported success but net7.0 companion output was not found at $built70." `
            -Remediation "Run 'dotnet build src\Rook\Rook.csproj -f net7.0 -c Release' manually and check the output path."
        $Summary.steps.companion.state = "failed"
    }
}
```

- [ ] **Step 3: Update final installer next-action guidance**

In `install.ps1`, replace:

```powershell
if ($cs.state -eq "failed") {
    $Summary.next_actions += "Install .NET SDK or run dotnet build src/Rook -c Release"
}
```

with:

```powershell
if ($cs.state -eq "failed") {
    $Summary.next_actions += "Install .NET SDK or run dotnet build src\Rook\Rook.csproj -f net7.0 -c Release"
}
```

- [ ] **Step 4: Run the guard test**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\issue112-net48-companion-guards.tests.ps1
```

Expected: PASS with:

```text
Issue 112 net48 companion guard tests passed.
```

- [ ] **Step 5: Commit installer hardening**

Run:

```powershell
git add install.ps1
git commit -m "Remove net48 companion installer fallbacks"
```

---

### Task 4: Build and Final Verification

**Files:**
- Verify: `install.ps1`
- Verify: `scripts/register-companion.ps1`
- Verify: `scripts/tests/issue112-net48-companion-guards.tests.ps1`

- [ ] **Step 1: Run the Issue 112 guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\issue112-net48-companion-guards.tests.ps1
```

Expected:

```text
Issue 112 net48 companion guard tests passed.
```

- [ ] **Step 2: Run a managed net7.0 Release build**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 -c Release
```

Expected: build exits `0`. Existing repository warnings are acceptable; errors are not.

- [ ] **Step 3: Run an installer dry-run from the real checkout**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -DryRun -SkipNative -SkipConfig -SkipChirp -NoVerify
```

Expected: output does not mention `net48`, and dry-run exits `0` unless the local machine is missing a prerequisite that the dry-run explicitly reports as an error. If it exits non-zero, inspect the output and fix only Issue 112-related failures in this branch.

- [ ] **Step 4: Check the diff for forbidden fallback text**

Run:

```powershell
rg -n "bin\\Release\\net48\\Rook\\.rhp|bin\\Debug\\net48\\Rook\\.rhp|Companion already built \\(net48\\)|Companion built successfully \\(net48\\)|Reuse existing companion net48 build" install.ps1 scripts\register-companion.ps1
```

Expected: no matches. `rg` exits `1` when no matches are found.

- [ ] **Step 5: Run whitespace validation**

Run:

```powershell
git diff --check
```

Expected: no output and exit `0`.

- [ ] **Step 6: Final commit if any verification-only edits were needed**

If Task 4 caused changes, commit them:

```powershell
git add install.ps1 scripts\register-companion.ps1 scripts\tests\issue112-net48-companion-guards.tests.ps1
git commit -m "Verify net48 companion registration hardening"
```

If Task 4 caused no changes, do not create an empty commit.

---

## Self-Review Checklist

- Spec requirement: remove `install.ps1` automatic `net48` fallback/reuse/success paths. Covered by Task 3 and Task 4 static scan.
- Spec requirement: remove `register-companion.ps1` `net48` auto-discovery. Covered by Task 2 and Task 4 static scan.
- Spec requirement: reject explicit `-RhpPath` with exact `net48` path segment. Covered by Task 2 helper and Task 1 dynamic test.
- Review requirement: reject explicit framework-less package paths whose adjacent runtime metadata identifies `net48`. Covered by Task 2 helper and `Test-RegisterScriptRejectsFrameworklessNet48Package`.
- Spec requirement: match `net48` as a path segment, case-insensitive. Covered by `Test-PathHasExactSegment`.
- Spec requirement: no override. Covered by absence of an override parameter and by tests invoking the normal path.
- Spec requirement: release-package `plugin\Rook.rhp` must have adjacent `net7.0` runtime metadata. Covered by Task 3 helper and Task 1 dry-run test.
- Spec requirement: keep suite registration validation centralized in `register-companion.ps1`. Covered by Task 2; `install.ps1` continues passing `CompanionRhpPath` to `register-rooknative-suite.ps1`, which delegates to `register-companion.ps1`.
- Verification requirement: managed `net7.0` Release build. Covered by Task 4.
