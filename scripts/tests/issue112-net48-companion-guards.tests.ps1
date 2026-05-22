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

    if ($null -eq $Value) {
        return '""'
    }

    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
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
        'Reuse existing companion net48 build',
        'Companion already built (net48)',
        'Companion built successfully (net48)'
    )

    foreach ($pattern in $forbidden) {
        Assert-NotContains -Text $content -Unexpected $pattern -Message "install.ps1 still contains unsafe companion fallback text: $pattern"
    }
}

function Test-InstallScriptUsesMultiRuntimeCompanionLayout {
    $content = Get-Content -Path $InstallScript -Raw

    Assert-Contains -Text $content -Expected '$ManagedCompanionRuntimes = @(''net8.0'', ''net7.0'', ''net48'')' -Message 'install.ps1 must know every managed companion runtime folder.'
    Assert-Contains -Text $content -Expected 'dotnet build $buildTarget -c Release' -Message 'install.ps1 must build all companion target frameworks from source.'
    Assert-Contains -Text $content -Expected 'function Get-MissingCompanionRuntimePayloads' -Message 'install.ps1 must validate required files inside every runtime child.'
    Assert-Contains -Text $content -Expected 'function Copy-CompanionRuntimePayload' -Message 'install.ps1 must copy companion payloads per runtime child.'
    Assert-Contains -Text $content -Expected 'Rook.runtimeconfig.json' -Message 'install.ps1 must require runtime metadata for .NET Core companion runtime children.'
    Assert-Contains -Text $content -Expected 'Remove-StaleRootCompanionPayload' -Message 'install.ps1 must remove stale root-level companion payload files from old installs.'
    Assert-Contains -Text $content -Expected 'Join-Path $pluginDest "net7.0\Rook.rhp"' -Message 'install.ps1 must register the net7.0 child RHP anchor.'
    Assert-Contains -Text $content -Expected 'plugin\net7.0\Rook.rhp' -Message 'install.ps1 release detection must use a runtime-child companion payload.'
    Assert-NotContains -Text $content -Unexpected 'Test-Path (Join-Path $installDir "plugin\Rook.rhp")' -Message 'install.ps1 must not detect old root-level release companion packages.'
    Assert-NotContains -Text $content -Unexpected 'Copy-Item (Join-Path $Context.CompanionBuildDir "*.rhp") $pluginDest' -Message 'install.ps1 must not copy companion RHPs to the plugin root.'
    Assert-NotContains -Text $content -Unexpected 'dotnet build $buildTarget -f net7.0' -Message 'install.ps1 must not build only the net7.0 companion target.'
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

function Test-InstallReleasePackageRejectsIncompleteRuntimeLayout {
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-issue112-install-" + [System.Guid]::NewGuid().ToString('N'))
    $pluginDir = Join-Path $tempRoot 'plugin\net7.0'
    $scriptsDir = Join-Path $tempRoot 'scripts'
    New-Item -ItemType Directory -Path $pluginDir -Force | Out-Null
    New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null

    Copy-Item -LiteralPath $InstallScript -Destination (Join-Path $tempRoot 'install.ps1') -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot 'scripts\detect-vs.ps1') -Destination (Join-Path $scriptsDir 'detect-vs.ps1') -Force
    New-Item -ItemType File -Path (Join-Path $pluginDir 'Rook.rhp') -Force | Out-Null

    try {
        $result = Invoke-ScriptProcess -Arguments @('-File', (Join-Path $tempRoot 'install.ps1'), '-DryRun', '-SkipNative', '-SkipConfig', '-SkipChirp', '-NoVerify')

        Assert-True -Condition ($result.ExitCode -ne 0) -Message 'Release-package dry-run unexpectedly accepted an incomplete runtime-child layout.'
        Assert-Contains -Text $result.Output -Expected 'Release companion payload is incomplete' -Message "Incomplete runtime layout was not reported clearly. Output: $($result.Output)"
    } finally {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Test-InstallScriptHasNoNet48Fallbacks
Test-InstallScriptUsesMultiRuntimeCompanionLayout
Test-RegisterScriptHasNoNet48Discovery
Test-RegisterScriptRejectsExplicitNet48Path
Test-RegisterScriptRejectsFrameworklessNet48Package
Test-InstallReleasePackageRejectsIncompleteRuntimeLayout

Write-Host 'Issue 112 net48 companion guard tests passed.'
